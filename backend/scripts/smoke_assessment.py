"""Opt-in live lifecycle test. Creates isolated accounts/data and removes them.

Run from backend: .venv/Scripts/python.exe scripts/smoke_assessment.py --live-generation
Requires the local API, root .env and frontend/.env.local. Never prints tokens.
"""
import argparse
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
import pymupdf
from dotenv import load_dotenv, dotenv_values
from supabase import ClientOptions, create_client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")
from app.auth import Actor
from app.db import get_db
from app.schemas import QuizConfig
from app.services.assessment import save_draft
from app.services.rag.generation.models import GeneratedQuestion, Evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-generation", action="store_true")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    url = os.environ["SUPABASE_URL"]
    db = get_db()
    front = dotenv_values(ROOT / "frontend/.env.local")
    public_key = front.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or front["NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"]
    users, storage_paths = {}, []
    run_id = uuid.uuid4().hex[:12]
    http = httpx.Client(base_url=args.api_url, timeout=300)
    def call(role, method, path, body=None, expected=200):
        headers = {"Authorization": "Bearer " + users[role]["token"]} if role else {}
        response = http.request(method, path, json=body, headers=headers)
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}: {response.text[:1200]}")
        return response.json()
    try:
        for label, role in [("teacher", "faculty"), ("student", "student"), ("other_student", "student"), ("other_teacher", "faculty"), ("admin", "admin")]:
            email = f"cognira-smoke-{run_id}-{label}@example.com"
            password = secrets.token_urlsafe(24)
            user = db.auth.admin.create_user({"email": email, "password": password, "email_confirm": True,
                "user_metadata": {"full_name": f"Smoke test {label}"}}).user
            users[label] = {"id": str(user.id)}
            db.table("profiles").update({"role": role}).eq("id", user.id).execute()
            client = create_client(url, public_key, options=ClientOptions(httpx_client=httpx.Client(
                transport=httpx.HTTPTransport(retries=2, http2=False), timeout=30)))
            session = client.auth.sign_in_with_password({"email": email, "password": password}).session
            users[label].update(token=session.access_token, client=client)
        print("Created isolated test accounts.", flush=True)
        call(None, "GET", "/assessments", expected=401)
        call("student", "GET", "/assessments", expected=403)
        # An authenticated student cannot promote themselves via RPC or column writes.
        for operation in (
            lambda: users["student"]["client"].rpc("set_profile_role", {"p_role": "admin", "p_full_name": "", "p_institution": ""}).execute(),
            lambda: users["student"]["client"].table("profiles").update({"role": "admin"}).eq("id", users["student"]["id"]).execute(),
            lambda: users["student"]["client"].rpc("upsert_profile_on_login", {"p_id": users["teacher"]["id"], "p_email": "spoof@example.com", "p_full_name": "Spoof", "p_avatar": ""}).execute(),
        ):
            try:
                operation()
            except Exception:
                pass
            else:
                raise AssertionError("A privilege escalation operation succeeded")
        print("Role and profile isolation passed.", flush=True)
        source_id, parent_id = str(uuid.uuid4()), str(uuid.uuid4())
        passage = "DNA stores genetic information. DNA and RNA are nucleic acids. Ribosomes make proteins."
        db.table("document_chunks").insert({"node_id": parent_id, "source_id": source_id, "owner_id": users["teacher"]["id"],
            "file_name": "biology.pdf", "chunk_index": 0, "content": passage, "embedding": None,
            "metadata": {"file_name": "biology.pdf", "page_or_slide_num": 1, "page_numbers": [1]}}).execute()
        evidence = [Evidence(source_id=source_id, parent_id=parent_id, quote=passage, file_name="biology.pdf", page=1, pages=[1])]
        fixtures = [
            GeneratedQuestion(id=1, question="Which molecule stores genetic information?", options=["DNA", "Salt", "Water", "Sugar"], correct_answer="DNA", explanation="DNA stores genetic information.", topic="Cells", bloom_rationale="Recall a fact.", difficulty=1, evidence=evidence),
            GeneratedQuestion(id=2, question="Which of these are nucleic acids?", options=["DNA", "RNA", "Salt", "Water"], correct_answer=["DNA", "RNA"], question_type="multiple", explanation="DNA and RNA are nucleic acids.", topic="Cells", bloom_level="Understand", bloom_rationale="Classify molecules.", difficulty=3, evidence=evidence),
            GeneratedQuestion(id=3, question="Ribosomes make proteins.", options=["True", "False"], correct_answer="True", question_type="truefalse", explanation="Ribosomes make proteins.", topic="Cells", bloom_rationale="Recall a fact.", difficulty=2, evidence=evidence),
        ]
        config = QuizConfig(subjectName="Biology", topicsCovered="Cells", learningObjective="Identify cellular molecules", gradeLevel="School", questionType="all", questionCount=3, timeLimit="1")
        teacher = Actor(users["teacher"]["id"], "faculty", "")
        quiz = save_draft(teacher, config, fixtures)
        call("other_teacher", "GET", f"/assessments/{quiz['id']}", expected=404)
        call("teacher", "POST", "/generate-assessment", {"sourceType": "upload", "files": [{"name": "bad.pdf", "signedUrl": "http://127.0.0.1/private", "size_bytes": 1}], "config": config.model_dump()}, expected=422)
        published = call("teacher", "POST", f"/assessments/{quiz['id']}/publish", {"version": quiz["version"]})
        call("student", "POST", "/student/join", {"code": published["join_code"]})
        call("other_student", "POST", f"/student/assessments/{quiz['id']}/start", expected=403)
        state = call("student", "POST", f"/student/assessments/{quiz['id']}/start")
        attempt_id = state["id"]
        assert set(state["question"]) == {"id", "question", "options", "question_type"}
        call("other_student", "GET", f"/student/attempts/{attempt_id}", expected=404)
        qid = state["question"]["id"]
        old_version = state["version"]
        state = call("student", "POST", f"/student/attempts/{attempt_id}/answer", {"version": state["version"], "question_id": qid, "choices": [0], "draft": True})
        resumed = call("student", "GET", f"/student/attempts/{attempt_id}")
        assert resumed["draft_answers"] == [0] and resumed["answered"] == 0
        call("student", "POST", f"/student/attempts/{attempt_id}/answer", {"version": old_version, "question_id": qid, "choices": [0]}, expected=409)
        while state["status"] == "active":
            qid = state["question"]["id"]
            choices = [0, 1] if qid == 2 else [1] if qid == 3 else [0]
            state = call("student", "POST", f"/student/attempts/{attempt_id}/answer", {"version": state["version"], "question_id": qid, "choices": choices})
        assert state["score"] == 2 and state["total"] == 3
        assert state["feedback"]["mastery"]["Cells"]["observations"] == 3
        assert state["feedback"]["recommendations"]
        again = call("student", "POST", f"/student/assessments/{quiz['id']}/start")
        assert again["id"] == attempt_id and again["status"] == "submitted"
        analytics = call("teacher", "GET", f"/assessments/{quiz['id']}/analytics")
        assert analytics["completed"] == 1 and analytics["topics"]["Cells"] == {"correct": 2, "total": 3}
        assert len(call("student", "GET", "/student/progress")) == 1
        print("Publishing, enrollment, autosave/resume, concurrency checks, all formats of scoring, mastery and analytics passed.", flush=True)
        timed = save_draft(teacher, config, fixtures)
        timed = call("teacher", "POST", f"/assessments/{timed['id']}/publish", {"version": timed["version"]})
        call("student", "POST", "/student/join", {"code": timed["join_code"]})
        timed_state = call("student", "POST", f"/student/assessments/{timed['id']}/start")
        db.table("assessment_attempts").update({"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}).eq("id", timed_state["id"]).execute()
        timed_state = call("student", "GET", f"/student/attempts/{timed_state['id']}")
        assert timed_state["status"] == "submitted" and timed_state["score"] == 0
        call("admin", "PATCH", f"/admin/people/{users['student']['id']}", {"role": "student", "suspended": True})
        call("student", "GET", "/student/progress", expected=403)
        call("admin", "PATCH", f"/admin/people/{users['student']['id']}", {"role": "student", "suspended": False})
        call("admin", "PATCH", f"/admin/people/{users['admin']['id']}", {"role": "student", "suspended": False}, expected=422)
        call("admin", "GET", "/admin/audit")
        call("teacher", "POST", f"/assessments/{quiz['id']}/close")
        call("other_student", "POST", "/student/join", {"code": published["join_code"]}, expected=404)
        try:
            users["student"]["client"].table("assessments").select("questions").execute()
        except Exception:
            pass
        else:
            raise AssertionError("Browser client could access answer keys")
        print("Expiry, account suspension, admin restrictions, closing and answer-key protection passed.", flush=True)
        pdf = pymupdf.open(); pdf.new_page().insert_text((40, 50), passage); pdf_bytes = pdf.tobytes(); pdf.close()
        storage_path = f"{teacher.id}/{run_id}.pdf"
        storage_paths.append(storage_path)
        users["teacher"]["client"].storage.from_("faculty-documents").upload(storage_path, pdf_bytes, {"content-type": "application/pdf"})
        try:
            users["other_teacher"]["client"].storage.from_("faculty-documents").create_signed_url(storage_path, 60)
        except Exception:
            pass
        else:
            raise AssertionError("Another teacher could read an uploaded file")
        print("Storage ownership passed.", flush=True)
        if args.live_generation:
            signed = users["teacher"]["client"].storage.from_("faculty-documents").create_signed_url(storage_path, 300)["signedURL"]
            live_config = config.model_copy(update={"questionCount": 2, "questionType": "single", "bloomLevels": ["Remember", "Understand"]})
            result = call("teacher", "POST", "/generate-assessment", {"sourceType": "upload", "files": [{"name": "biology.pdf", "signedUrl": signed, "size_bytes": len(pdf_bytes)}], "config": live_config.model_dump()})
            assert result["assessmentId"] and len(result["questions"]) == 2
            for q in result["questions"]:
                assert q["evidence"] and q["explanation"] and q["bloom_rationale"]
            live = call("teacher", "GET", f"/assessments/{result['assessmentId']}")
            call("teacher", "POST", f"/assessments/{live['id']}/publish", {"version": live["version"]})
            print("LIVE AI PASSED: signed PDF download, extraction, owned atomic indexing, retrieval, quoted evidence checks, independent semantic/Bloom review, saved draft and publication.", flush=True)
        print("ALL LIVE LIFECYCLE CHECKS PASSED.", flush=True)
    finally:
        ids = [u["id"] for u in users.values()]
        try:
            if storage_paths:
                db.storage.from_("faculty-documents").remove(storage_paths)
            if ids:
                owned = db.table("assessments").select("id").in_("owner_id", ids).execute().data
                quiz_ids = [q["id"] for q in owned]
                if quiz_ids:
                    db.table("assessment_attempts").delete().in_("assessment_id", quiz_ids).execute()
                    db.table("assessment_enrollments").delete().in_("assessment_id", quiz_ids).execute()
                db.table("assessment_audit").delete().in_("actor_id", ids).execute()
                db.table("assessments").delete().in_("owner_id", ids).execute()
                db.table("document_chunks").delete().in_("owner_id", ids).execute()
                for user_id in ids:
                    db.auth.admin.delete_user(user_id)
        finally:
            http.close()
        print("Removed isolated test accounts and data.", flush=True)


if __name__ == "__main__":
    main()
