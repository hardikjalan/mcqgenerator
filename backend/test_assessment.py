import json
import httpx
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.auth import Actor, current_actor, faculty
from app.main import app
from app.schemas import QuizConfig
from app.services import assessment as service
from app.services.rag.pipeline import validate_download_url
from supabase_auth.errors import AuthApiError


def question(index=1, difficulty=2, topic="Cells", kind="single"):
    return {"id": index, "question": "Which molecule stores genetic information?", "options": ["DNA", "Water", "Salt", "Sugar"],
            "correct_answer": "DNA", "question_type": kind, "difficulty": difficulty, "topic": topic,
            "bloom_level": "Remember", "explanation": "DNA stores genetic information.", "evidence": []}


class AssessmentDomainTests(unittest.TestCase):
    def test_single_and_multi_select_grade_exactly(self):
        q = question()
        self.assertTrue(service.grade(q, [0]))
        self.assertFalse(service.grade(q, [0, 1]))
        self.assertFalse(service.grade(q, []))
        q["correct_answer"] = ["DNA", "Water"]
        self.assertTrue(service.grade(q, [1, 0]))
        self.assertFalse(service.grade(q, [0]))

    def test_mastery_increases_after_correct_and_decreases_after_incorrect(self):
        previous = {"Cells": {"probability": 0.5, "observations": 3}}
        self.assertGreater(service.update_mastery(previous, question(), True)["Cells"]["probability"], 0.5)
        self.assertLess(service.update_mastery(previous, question(), False)["Cells"]["probability"], 0.5)
        self.assertEqual(service.update_mastery(previous, question(), True)["Cells"]["observations"], 4)
        self.assertEqual(previous["Cells"]["probability"], 0.5)

    def test_adaptation_selects_harder_items_for_higher_mastery(self):
        bank = [question(1, 1), question(2, 5)]
        low = service.choose_question(bank, [], {"Cells": {"probability": 0.1}}, True, "attempt")
        high = service.choose_question(bank, [], {"Cells": {"probability": 0.95}}, True, "attempt")
        self.assertEqual(low["id"], 1)
        self.assertEqual(high["id"], 2)

    def test_adaptation_covers_unseen_topics_and_never_repeats(self):
        bank = [question(1, 1), question(2, 2), question(3, 5, "Genetics")]
        self.assertEqual(service.choose_question(bank, [1], {}, True, "attempt")["id"], 3)
        self.assertIsNone(service.choose_question(bank, [1, 2, 3], {}, True, "attempt"))
        self.assertEqual(service.choose_question(bank, [1], {}, False, "attempt")["id"], 2)

    def test_public_question_contains_no_answer_keys_or_source_evidence(self):
        public = service.public_question(question())
        self.assertEqual(set(public), {"id", "question", "options", "question_type"})
        self.assertNotIn("correct_answer", json.dumps(public))

    def test_finish_counts_only_committed_answers(self):
        attempt = {"id": "a", "status": "active", "version": 1, "answers": {"1": {"correct": True}}, "draft_answers": [0]}
        with patch.object(service, "write_attempt", side_effect=lambda a, c: {**a, **c}) as write:
            result = service.finish(attempt, {"questions": [question(), question(2)]})
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["draft_answers"], [])
        self.assertEqual(write.call_count, 1)

    def test_expiry_uses_server_time(self):
        self.assertTrue(service.expired({"expires_at": (service.now() - timedelta(seconds=1)).isoformat()}))
        self.assertFalse(service.expired({"expires_at": (service.now() + timedelta(seconds=60)).isoformat()}))
        self.assertFalse(service.expired({"expires_at": None}))

    def test_concurrent_answer_is_rejected(self):
        database = MagicMock()
        database.table.return_value.update.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        with patch.object(service, "get_db", return_value=database), self.assertRaises(HTTPException) as error:
            service.write_attempt({"id": "a", "version": 2}, {"answers": {}})
        self.assertEqual(error.exception.status_code, 409)

    def test_stale_or_out_of_sequence_answers_do_not_write(self):
        attempt = {"id": "a", "status": "active", "version": 2, "presented": [1], "answers": {}, "expires_at": None}
        with patch.object(service, "load_attempt", return_value=(attempt, {"questions": [question()]})), patch.object(service, "write_attempt") as write:
            for version, question_id in [(1, 1), (2, 2)]:
                with self.subTest(version=version, question_id=question_id), self.assertRaises(HTTPException) as error:
                    service.record_answer(Actor("s", "student", ""), "a", version, question_id, [0])
                self.assertEqual(error.exception.status_code, 409)
            write.assert_not_called()

    def test_invalid_choices_do_not_write(self):
        attempt = {"id": "a", "status": "active", "version": 1, "presented": [1], "answers": {}, "expires_at": None}
        with patch.object(service, "load_attempt", return_value=(attempt, {"questions": [question()]})), patch.object(service, "write_attempt") as write:
            for choices in ([5], [-1], [0, 0], [0, 1], []):
                with self.subTest(choices=choices), self.assertRaises(HTTPException) as error:
                    service.record_answer(Actor("s", "student", ""), "a", 1, 1, choices)
                self.assertEqual(error.exception.status_code, 422)
            write.assert_not_called()

    def test_feedback_counts_unanswered_items_in_topic_accuracy(self):
        result = service.feedback({"presented": [1], "answers": {"1": {"choices": [0], "correct": True}}, "mastery": {}}, {"questions": [question(), question(2)]})
        self.assertEqual(result["topics"]["Cells"], {"correct": 1, "total": 2})
        self.assertEqual(len(result["recommendations"]), 1)

    def test_unowned_assessment_returns_not_found(self):
        database = MagicMock()
        database.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"owner_id": "someone-else"}
        with patch.object(service, "get_db", return_value=database), self.assertRaises(HTTPException) as error:
            service.get_assessment("id", Actor("teacher", "faculty", ""))
        self.assertEqual(error.exception.status_code, 404)


class AuthorizationTests(unittest.TestCase):
    def test_auth_transport_outage_is_not_reported_as_an_expired_session(self):
        database = MagicMock()
        database.auth.get_user.side_effect = httpx.ConnectError("Authentication service is unavailable")
        with patch("app.auth.get_db", return_value=database), self.assertRaises(HTTPException) as error:
            current_actor(SimpleNamespace(credentials="token"))
        self.assertEqual(error.exception.status_code, 503)

    def test_auth_provider_server_errors_are_retryable(self):
        database = MagicMock()
        database.auth.get_user.side_effect = AuthApiError("Upstream failure", 503, None)
        with patch("app.auth.get_db", return_value=database), self.assertRaises(HTTPException) as error:
            current_actor(SimpleNamespace(credentials="token"))
        self.assertEqual(error.exception.status_code, 503)

    def test_invalid_tokens_still_return_unauthorized(self):
        database = MagicMock()
        database.auth.get_user.side_effect = AuthApiError("Invalid JWT", 401, "bad_jwt")
        with patch("app.auth.get_db", return_value=database), self.assertRaises(HTTPException) as error:
            current_actor(SimpleNamespace(credentials="token"))
        self.assertEqual(error.exception.status_code, 401)

    def test_protected_endpoints_require_authentication(self):
        client = TestClient(app)
        for path in ("/assessments", "/student/assessments", "/admin/people"):
            self.assertEqual(client.get(path).status_code, 401)

    def test_role_comes_from_database_not_editable_user_metadata(self):
        database = MagicMock()
        database.auth.get_user.return_value.user = SimpleNamespace(id="user", email="test@example.invalid", user_metadata={"role": "admin"})
        database.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"role": "student", "suspended": False}
        with patch("app.auth.get_db", return_value=database):
            actor = current_actor(SimpleNamespace(credentials="token"))
        self.assertEqual(actor.role, "student")
        with self.assertRaises(HTTPException):
            faculty(actor)

    def test_suspended_accounts_are_denied_with_valid_token(self):
        database = MagicMock()
        database.auth.get_user.return_value.user = SimpleNamespace(id="user", email="")
        database.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"role": "faculty", "suspended": True}
        with patch("app.auth.get_db", return_value=database), self.assertRaises(HTTPException) as error:
            current_actor(SimpleNamespace(credentials="token"))
        self.assertEqual(error.exception.status_code, 403)

    def test_download_urls_are_bound_to_project_and_owner(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "https://project.supabase.co"}):
            validate_download_url("https://project.supabase.co/storage/v1/object/sign/faculty-documents/owner/file.pdf?token=x", "owner")
            for url in ("http://127.0.0.1/private", "https://evil.example/file.pdf", "https://project.supabase.co/storage/v1/object/sign/faculty-documents/other/file.pdf", "https://project.supabase.co/storage/v1/object/sign/faculty-documents/owner/%2e%2e/other/file.pdf"):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    validate_download_url(url, "owner")

    def test_config_enforces_request_limits(self):
        valid = dict(subjectName="Biology", topicsCovered="Cells", learningObjective="Recall", gradeLevel="School", questionType="single", questionCount=1, timeLimit="")
        for change in ({"questionCount": 100000}, {"questionType": "invalid"}, {"subjectName": " "}, {"timeLimit": "9999"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                QuizConfig(**(valid | change))
