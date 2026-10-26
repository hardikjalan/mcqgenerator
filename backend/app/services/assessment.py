"""Persistent assessment lifecycle, server grading and Bayesian adaptive delivery."""
from __future__ import annotations
import hashlib
import logging
import secrets
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.auth import Actor
from app.db import get_db
from app.schemas import QuizConfig
from app.services.rag.generation.models import GeneratedQuestion
from app.services.rag.generation.validation import validate_question, normalise
from app.services.rag.generation.generator import MCQGenerator
from app.services.rag.retrieval.models import RetrievedParentContext

logger = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def audit(actor: Actor, action: str, target: str) -> None:
    try:
        get_db().table("assessment_audit").insert({"actor_id": actor.id, "action": action, "target_id": target}).execute()
    except Exception:
        logger.exception("Audit write failed for %s", action)


def get_assessment(assessment_id: str, actor: Actor | None = None) -> dict:
    result = get_db().table("assessments").select("*").eq("id", assessment_id).maybe_single().execute()
    row = result.data if result else None
    if not row or (actor and row["owner_id"] != actor.id and actor.role != "admin"):
        raise HTTPException(404, "Assessment not found.")
    return row


def save_draft(actor: Actor, config: QuizConfig, questions: list[GeneratedQuestion]) -> dict:
    if not questions:
        raise ValueError("No verified questions were generated.")
    row = {"owner_id": actor.id, "title": config.subjectName.strip(), "config": config.model_dump(),
           "questions": [q.model_dump() for q in questions], "join_code": secrets.token_hex(5).upper(),
           "adaptive": config.adaptive, "duration_seconds": int(config.timeLimit) * 60 if config.timeLimit else None}
    result = get_db().table("assessments").insert(row).execute().data[0]
    audit(actor, "assessment_created", result["id"])
    return result


def check_questions(actor: Actor, questions: list[GeneratedQuestion], semantic: bool = False) -> None:
    parent_ids = list({e.parent_id for q in questions for e in q.evidence})
    contexts = []
    if parent_ids:
        rows = get_db().table("document_chunks").select("node_id,source_id,owner_id,content,metadata").in_("node_id", parent_ids).execute().data
        for row in rows:
            if row["owner_id"] != actor.id and actor.role != "admin":
                continue
            contexts.append(RetrievedParentContext(parent_id=row["node_id"], source_id=row["source_id"],
                content=row["content"], similarity=1, metadata=row["metadata"]))
    accepted = []
    for q in questions:
        errors = validate_question(q, contexts, accepted)
        if errors:
            raise HTTPException(422, f"Question {q.id}: {' '.join(errors)}")
        accepted.append(q)
    if semantic:
        passages = [{"source_id": c.source_id, "parent_id": c.parent_id, "text": c.content} for c in contexts]
        reviews = MCQGenerator().review_questions(questions, passages)
        by_id = {r.id: r for r in reviews.reviews}
        for q in questions:
            review = by_id.get(q.id)
            if not review or not review.supported:
                raise HTTPException(422, f"Question {q.id} failed evidence review. {review.reason if review else 'Review missing.'}")
            q.bloom_level, q.bloom_rationale, q.difficulty = review.bloom_level, review.bloom_rationale, review.difficulty


def update_assessment(assessment_id: str, actor: Actor, changes: dict, version: int) -> dict:
    row = get_assessment(assessment_id, actor)
    if row["status"] != "draft":
        raise HTTPException(409, "Published questions cannot be edited. Create a new assessment instead.")
    result = get_db().table("assessments").update({**changes, "version": version + 1}).eq("id", assessment_id).eq("version", version).eq("status", "draft").execute().data
    if not result:
        raise HTTPException(409, "This assessment changed in another tab. Reload before saving.")
    return result[0]


def publish_assessment(assessment_id: str, actor: Actor, version: int, closes_at: datetime | None) -> dict:
    row = get_assessment(assessment_id, actor)
    check_questions(actor, [GeneratedQuestion.model_validate(q) for q in row["questions"]])
    if closes_at and (closes_at.tzinfo is None or closes_at <= now()):
        raise HTTPException(422, "Closing time must be a future date with a timezone.")
    updated = update_assessment(assessment_id, actor, {
        "status": "published", "published_at": now().isoformat(),
        "closes_at": closes_at.isoformat() if closes_at else None,
    }, version)
    audit(actor, "assessment_published", assessment_id)
    return updated


def assessment_summary(row: dict) -> dict:
    return {key: row.get(key) for key in (
        "id", "title", "status", "adaptive", "duration_seconds", "closes_at", "created_at", "published_at"
    )} | {"question_count": len(row["questions"]), "subject": row["config"].get("subjectName", "")}


def enroll(actor: Actor, code: str) -> dict:
    result = get_db().table("assessments").select("*").eq("join_code", code.strip().upper()).eq("status", "published").maybe_single().execute()
    row = result.data if result else None
    if not row or (row.get("closes_at") and timestamp(row["closes_at"]) <= now()):
        raise HTTPException(404, "This quiz code is invalid or the quiz has closed.")
    get_db().table("assessment_enrollments").upsert({"assessment_id": row["id"], "student_id": actor.id}, on_conflict="assessment_id,student_id").execute()
    audit(actor, "assessment_joined", row["id"])
    return assessment_summary(row)


def update_mastery(state: dict, question: dict, correct: bool) -> dict:
    """Bayesian knowledge tracing: prior, observation update, then learning transition."""
    topic = question.get("topic") or "General"
    previous = state.get(topic, {"probability": 0.35, "observations": 0})
    probability = float(previous["probability"])
    slip = 0.1 + 0.025 * (int(question.get("difficulty", 1)) - 1)
    guess = 0.5 if question.get("question_type") == "truefalse" else 0.15 if question.get("question_type") == "multiple" else 0.25
    likelihood_known, likelihood_unknown = (1 - slip, guess) if correct else (slip, 1 - guess)
    posterior = probability * likelihood_known / max(1e-9, probability * likelihood_known + (1 - probability) * likelihood_unknown)
    return {**state, topic: {"probability": round(posterior + (1 - posterior) * 0.08, 5),
                            "observations": int(previous.get("observations", 0)) + 1}}


def choose_question(questions: list[dict], presented: list[int], mastery: dict, adaptive: bool, seed: str) -> dict | None:
    remaining = [q for q in questions if q["id"] not in presented]
    if not remaining:
        return None
    if not adaptive:
        return remaining[0]
    seen = Counter(q.get("topic", "General") for q in questions if q["id"] in presented)
    def priority(q):
        topic = q.get("topic") or "General"
        probability = mastery.get(topic, {}).get("probability", 0.35)
        target = 1 + 4 * probability
        tie = hashlib.sha256(f"{seed}:{q['id']}".encode()).hexdigest()
        return seen[topic], abs(q.get("difficulty", 1) - target), probability, tie
    return min(remaining, key=priority)


def grade(question: dict, choices: list[int]) -> bool:
    correct = question["correct_answer"]
    answers = correct if isinstance(correct, list) else [correct]
    indices = {i for i, option in enumerate(question["options"]) if normalise(option) in {normalise(a) for a in answers}}
    return set(choices) == indices


def public_question(question: dict) -> dict:
    # Never serialize keys, explanations or evidence while a test is in progress.
    return {key: question[key] for key in ("id", "question", "options", "question_type")}


def initial_mastery(actor: Actor, subject: str) -> dict:
    rows = get_db().table("assessment_attempts").select("mastery,assessments(config)").eq("student_id", actor.id).eq("status", "submitted").order("submitted_at", desc=True).limit(100).execute().data
    state = {}
    for row in rows:
        assessment = row.get("assessments") or {}
        if normalise(assessment.get("config", {}).get("subjectName", "")) == normalise(subject):
            for topic, value in row.get("mastery", {}).items():
                state.setdefault(topic, value)
    return state


def start_attempt(actor: Actor, assessment_id: str) -> dict:
    quiz = get_assessment(assessment_id)
    enrollment = get_db().table("assessment_enrollments").select("assessment_id").eq("assessment_id", assessment_id).eq("student_id", actor.id).execute().data
    if not enrollment:
        raise HTTPException(403, "Join this quiz using its code first.")
    previous = get_db().table("assessment_attempts").select("*").eq("assessment_id", assessment_id).eq("student_id", actor.id).execute().data
    if previous:
        return attempt_state(previous[0], quiz)
    if quiz["status"] != "published" or (quiz.get("closes_at") and timestamp(quiz["closes_at"]) <= now()):
        raise HTTPException(409, "This assessment is closed.")
    mastery = initial_mastery(actor, quiz["config"].get("subjectName", ""))
    attempt_id = str(uuid.uuid4())
    first = choose_question(quiz["questions"], [], mastery, quiz["adaptive"], attempt_id)
    deadline = now() + timedelta(seconds=quiz["duration_seconds"]) if quiz.get("duration_seconds") else None
    if quiz.get("closes_at"):
        closing = timestamp(quiz["closes_at"])
        deadline = min(deadline, closing) if deadline else closing
    record = {"id": attempt_id, "assessment_id": assessment_id, "student_id": actor.id,
              "total": len(quiz["questions"]), "presented": [first["id"]], "mastery": mastery,
              "expires_at": deadline.isoformat() if deadline else None}
    try:
        row = get_db().table("assessment_attempts").insert(record).execute().data[0]
    except Exception:
        # A simultaneous start in another tab must resume the same attempt.
        rows = get_db().table("assessment_attempts").select("*").eq("assessment_id", assessment_id).eq("student_id", actor.id).execute().data
        if not rows:
            raise
        row = rows[0]
    audit(actor, "attempt_started", row["id"])
    return attempt_state(row, quiz)


def load_attempt(attempt_id: str, actor: Actor) -> tuple[dict, dict]:
    result = get_db().table("assessment_attempts").select("*").eq("id", attempt_id).eq("student_id", actor.id).maybe_single().execute()
    row = result.data if result else None
    if not row:
        raise HTTPException(404, "Attempt not found.")
    return row, get_assessment(row["assessment_id"])


def expired(attempt: dict) -> bool:
    return bool(attempt.get("expires_at") and timestamp(attempt["expires_at"]) <= now())


def write_attempt(attempt: dict, changes: dict) -> dict:
    rows = get_db().table("assessment_attempts").update({**changes, "version": attempt["version"] + 1}).eq("id", attempt["id"]).eq("version", attempt["version"]).eq("status", "active").execute().data
    if not rows:
        raise HTTPException(409, "This attempt changed in another tab. Reload to continue.")
    return rows[0]


def finish(attempt: dict, quiz: dict) -> dict:
    if attempt["status"] == "submitted":
        return attempt
    answers = attempt["answers"]
    # Unsubmitted draft answers never count as committed responses.
    return write_attempt(attempt, {"status": "submitted", "submitted_at": now().isoformat(),
        "score": sum(bool(a["correct"]) for a in answers.values()), "draft_answers": []})


def attempt_state(attempt: dict, quiz: dict) -> dict:
    if attempt["status"] == "active" and expired(attempt):
        attempt = finish(attempt, quiz)
    base = {key: attempt.get(key) for key in ("id", "assessment_id", "status", "started_at", "expires_at", "submitted_at", "version", "total", "score")}
    base.update(title=quiz["title"], answered=len(attempt["answers"]), adaptive=quiz["adaptive"], server_time=now().isoformat())
    if attempt["status"] == "active":
        current = next(q for q in quiz["questions"] if q["id"] == attempt["presented"][-1])
        base.update(question=public_question(current), draft_answers=attempt.get("draft_answers", []))
    else:
        base.update(feedback=feedback(attempt, quiz), question=None)
    return base


def record_answer(actor: Actor, attempt_id: str, version: int, question_id: int, choices: list[int], draft: bool = False) -> dict:
    attempt, quiz = load_attempt(attempt_id, actor)
    if attempt["status"] != "active" or expired(attempt):
        return attempt_state(attempt, quiz)
    if version != attempt["version"]:
        raise HTTPException(409, "This attempt changed. Reload before answering.")
    if question_id != attempt["presented"][-1] or str(question_id) in attempt["answers"]:
        raise HTTPException(409, "Only the current unanswered question can be submitted.")
    question = next(q for q in quiz["questions"] if q["id"] == question_id)
    if len(set(choices)) != len(choices) or any(i < 0 or i >= len(question["options"]) for i in choices):
        raise HTTPException(422, "Invalid answer choices.")
    if question["question_type"] != "multiple" and len(choices) > 1:
        raise HTTPException(422, "Choose only one answer.")
    if draft:
        return attempt_state(write_attempt(attempt, {"draft_answers": choices}), quiz)
    if not choices:
        raise HTTPException(422, "Choose an answer before continuing.")
    correct = grade(question, choices)
    answers = {**attempt["answers"], str(question_id): {"choices": choices, "correct": correct,
        "topic": question["topic"], "bloom_level": question["bloom_level"], "answered_at": now().isoformat()}}
    mastery = update_mastery(attempt.get("mastery", {}), question, correct)
    next_question = choose_question(quiz["questions"], attempt["presented"], mastery, quiz["adaptive"], attempt["id"])
    changes = {"answers": answers, "mastery": mastery, "draft_answers": []}
    if next_question:
        changes["presented"] = attempt["presented"] + [next_question["id"]]
    else:
        changes.update(status="submitted", submitted_at=now().isoformat(), score=sum(a["correct"] for a in answers.values()))
    updated = write_attempt(attempt, changes)
    if updated["status"] == "submitted":
        audit(actor, "attempt_completed", updated["id"])
    return attempt_state(updated, quiz)


def feedback(attempt: dict, quiz: dict) -> dict:
    topics = defaultdict(lambda: {"correct": 0, "total": 0})
    details = []
    by_id = {q["id"]: q for q in quiz["questions"]}
    for question_id in attempt["presented"]:
        q = by_id[question_id]
        answer = attempt["answers"].get(str(question_id))
        details.append({**q, "selected": answer["choices"] if answer else [], "correct": bool(answer and answer["correct"])})
    # All unanswered items count towards the final score and topic coverage.
    for q in quiz["questions"]:
        topic = q.get("topic") or "General"
        topics[topic]["total"] += 1
        answer = attempt["answers"].get(str(q["id"]))
        topics[topic]["correct"] += int(bool(answer and answer["correct"]))
    recommendations = []
    for topic, stats in topics.items():
        if stats["correct"] / stats["total"] < 0.7:
            citations = [e for q in quiz["questions"] if q.get("topic") == topic for e in q.get("evidence", [])]
            recommendations.append({"topic": topic, "message": f"Review {topic}, explain the key ideas in your own words, then practise another question.", "sources": citations[:3]})
    return {"topics": dict(topics), "mastery": attempt.get("mastery", {}), "recommendations": recommendations,
            "questions": details, "mastery_method": "Bayesian estimate; limited evidence until several questions have been answered."}


def analytics(assessment_id: str, actor: Actor) -> dict:
    quiz = get_assessment(assessment_id, actor)
    attempts = get_db().table("assessment_attempts").select("*").eq("assessment_id", assessment_id).order("started_at", desc=True).limit(5000).execute().data
    attempts = [finish(a, quiz) if a["status"] == "active" and expired(a) else a for a in attempts]
    topics, blooms = defaultdict(lambda: {"correct": 0, "total": 0}), defaultdict(lambda: {"correct": 0, "total": 0})
    finished = [a for a in attempts if a["status"] == "submitted"]
    for a in finished:
        for q in quiz["questions"]:
            answer = a["answers"].get(str(q["id"]))
            for bucket, key in ((topics, q.get("topic", "General")), (blooms, q.get("bloom_level", "Remember"))):
                bucket[key]["total"] += 1
                bucket[key]["correct"] += int(bool(answer and answer["correct"]))
    student_ids = list({a["student_id"] for a in attempts})
    profiles = get_db().table("profiles").select("id,full_name,email").in_("id", student_ids).execute().data if student_ids else []
    people = {p["id"]: p for p in profiles}
    return {"assessment": assessment_summary(quiz), "started": len(attempts), "completed": len(finished),
        "average_percent": round(sum(100 * a["score"] / a["total"] for a in finished) / len(finished), 1) if finished else None,
        "topics": dict(topics), "bloom_levels": dict(blooms),
        "students": [{"attempt_id": a["id"], "name": people.get(a["student_id"], {}).get("full_name") or "Student",
                      "email": people.get(a["student_id"], {}).get("email", ""), "status": a["status"],
                      "score": a["score"], "total": a["total"], "submitted_at": a["submitted_at"]} for a in attempts]}
