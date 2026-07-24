"""
assessment.py
=============
Request/response shapes for the assessment endpoints.

These mirror the payload the faculty dashboard sends
(frontend/app/dashboard/faculty/page.tsx). Field names are camelCase to match
the frontend as-is — do not rename one side without the other.
"""

from typing import List, Optional

from pydantic import BaseModel


class QuizConfigSchema(BaseModel):
    subjectName: str
    topicsCovered: str
    learningObjective: str
    gradeLevel: str
    questionType: str
    questionCount: int
    timeLimit: str


class FileItem(BaseModel):
    name: str        # original filename e.g. "lecture.pdf"
    signedUrl: str   # temporary Supabase signed URL to download the file
    size_bytes: int  # original File.size from the browser (bytes) — used for cumulative cap


class GenerateRequest(BaseModel):
    sourceType: str              # "upload" or "text"
    textContent: Optional[str] = None
    files: Optional[List[FileItem]] = None
    config: QuizConfigSchema
