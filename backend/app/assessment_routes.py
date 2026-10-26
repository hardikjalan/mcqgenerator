from datetime import datetime
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from app.auth import Actor, faculty, student, administrator
from app.db import get_db
from app.services import assessment as service
from app.services.rag.generation.models import GeneratedQuestion

router = APIRouter()


class EditDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=30)


class Publish(BaseModel):
    version: int = Field(ge=1)
    closes_at: datetime | None = None


class Join(BaseModel):
    code: str = Field(min_length=4, max_length=30, pattern=r"^[A-Za-z0-9 -]+$")


class Answer(BaseModel):
    version: int = Field(ge=1)
    question_id: int = Field(ge=1, le=30)
    choices: list[int] = Field(max_length=4)
    draft: bool = False


class Finish(BaseModel):
    version: int = Field(ge=1)


class PersonUpdate(BaseModel):
    role: Literal["student", "faculty", "admin"]
    suspended: bool


@router.get("/assessments")
def list_assessments(actor: Actor = Depends(faculty)):
    query = get_db().table("assessments").select("*").order("created_at", desc=True).limit(1000)
    if actor.role != "admin":
        query = query.eq("owner_id", actor.id)
    return [{**service.assessment_summary(q), "join_code": q["join_code"], "version": q["version"]} for q in query.execute().data]


@router.get("/assessments/{assessment_id}")
def assessment(assessment_id: UUID, actor: Actor = Depends(faculty)):
    return service.get_assessment(str(assessment_id), actor)


@router.patch("/assessments/{assessment_id}")
def edit(assessment_id: UUID, payload: EditDraft, actor: Actor = Depends(faculty)):
    current = service.get_assessment(str(assessment_id), actor)
    if current["status"] != "draft":
        raise HTTPException(409, "Only draft assessments can be edited.")
    for index, question in enumerate(payload.questions, 1):
        question.id = index
    service.check_questions(actor, payload.questions, semantic=True)
    config = {**current["config"], "questionCount": len(payload.questions)}
    result = service.update_assessment(str(assessment_id), actor, {"title": payload.title.strip(),
        "questions": [q.model_dump() for q in payload.questions], "config": config}, payload.version)
    service.audit(actor, "assessment_edited", str(assessment_id))
    return result


@router.post("/assessments/{assessment_id}/publish")
def publish(assessment_id: UUID, payload: Publish, actor: Actor = Depends(faculty)):
    return service.publish_assessment(str(assessment_id), actor, payload.version, payload.closes_at)


@router.post("/assessments/{assessment_id}/close")
def close(assessment_id: UUID, actor: Actor = Depends(faculty)):
    row = service.get_assessment(str(assessment_id), actor)
    result = get_db().table("assessments").update({"status": "archived", "version": row["version"] + 1}).eq("id", str(assessment_id)).eq("version", row["version"]).execute().data
    if not result:
        raise HTTPException(409, "This quiz changed. Reload and try again.")
    service.audit(actor, "assessment_closed", str(assessment_id))
    return result[0]


@router.get("/assessments/{assessment_id}/analytics")
def analytics(assessment_id: UUID, actor: Actor = Depends(faculty)):
    return service.analytics(str(assessment_id), actor)


@router.post("/student/join")
def join(payload: Join, actor: Actor = Depends(student)):
    return service.enroll(actor, payload.code)


@router.get("/student/assessments")
def student_assessments(actor: Actor = Depends(student)):
    enrollments = get_db().table("assessment_enrollments").select("assessments(*)").eq("student_id", actor.id).limit(1000).execute().data
    attempts = get_db().table("assessment_attempts").select("id,assessment_id,status,score,total").eq("student_id", actor.id).limit(1000).execute().data
    by_quiz = {a["assessment_id"]: a for a in attempts}
    return [{**service.assessment_summary(e["assessments"]), "attempt": by_quiz.get(e["assessments"]["id"])}
            for e in enrollments if e.get("assessments")]


@router.post("/student/assessments/{assessment_id}/start")
def start(assessment_id: UUID, actor: Actor = Depends(student)):
    return service.start_attempt(actor, str(assessment_id))


@router.get("/student/attempts/{attempt_id}")
def attempt(attempt_id: UUID, actor: Actor = Depends(student)):
    row, quiz = service.load_attempt(str(attempt_id), actor)
    return service.attempt_state(row, quiz)


@router.post("/student/attempts/{attempt_id}/answer")
def answer(attempt_id: UUID, payload: Answer, actor: Actor = Depends(student)):
    return service.record_answer(actor, str(attempt_id), payload.version, payload.question_id, payload.choices, payload.draft)


@router.post("/student/attempts/{attempt_id}/finish")
def finish(attempt_id: UUID, payload: Finish, actor: Actor = Depends(student)):
    row, quiz = service.load_attempt(str(attempt_id), actor)
    if row["status"] == "active" and payload.version != row["version"]:
        raise HTTPException(409, "This attempt changed. Reload before submitting.")
    updated = service.finish(row, quiz)
    service.audit(actor, "attempt_submitted", str(attempt_id))
    return service.attempt_state(updated, quiz)


@router.get("/student/progress")
def progress(actor: Actor = Depends(student)):
    rows = get_db().table("assessment_attempts").select("*,assessments(*)").eq("student_id", actor.id).eq("status", "submitted").order("submitted_at", desc=True).limit(100).execute().data
    return [{"id": row["id"], "title": row["assessments"]["title"], "score": row["score"], "total": row["total"],
             "submitted_at": row["submitted_at"], "feedback": service.feedback(row, row["assessments"])} for row in rows]


@router.get("/admin/people")
def people(actor: Actor = Depends(administrator)):
    return get_db().table("profiles").select("id,email,full_name,role,suspended,created_at").order("created_at", desc=True).limit(1000).execute().data


@router.patch("/admin/people/{person_id}")
def person(person_id: UUID, payload: PersonUpdate, actor: Actor = Depends(administrator)):
    if str(person_id) == actor.id and (payload.suspended or payload.role != "admin"):
        raise HTTPException(422, "You cannot suspend or demote your own administrator account.")
    rows = get_db().table("profiles").update(payload.model_dump()).eq("id", str(person_id)).execute().data
    if not rows:
        raise HTTPException(404, "Account not found.")
    service.audit(actor, "account_updated", str(person_id))
    return {key: rows[0].get(key) for key in ("id", "email", "full_name", "role", "suspended")}


@router.get("/admin/audit")
def audit(actor: Actor = Depends(administrator)):
    return get_db().table("assessment_audit").select("*").order("created_at", desc=True).limit(100).execute().data
