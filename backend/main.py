import os
import sys
import tempfile
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Ensure project root is on path so loaders/extractors are importable
sys.path.insert(0, os.path.dirname(__file__))

from extractors.pdf_extractor import PDFExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.pptx_extractor import PptxExtractor
from extractors.ocr_extractor import OCRExtractor

app = FastAPI()

# ── CORS: allow requests from local Next.js frontend ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request schemas ───────────────────────────────────────────────────────────

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

class GenerateRequest(BaseModel):
    sourceType: str             # "upload" or "text"
    textContent: Optional[str] = None
    files: Optional[List[FileItem]] = None
    config: QuizConfigSchema

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_extractor_for(ext: str, file_path: str):
    """Return the correct extractor based on the file extension."""
    ext = ext.lower()
    if ext == "pdf":
        return PDFExtractor(file_path)
    elif ext == "docx":
        return DocxExtractor(file_path)
    elif ext in ("pptx", "ppt"):
        return PptxExtractor(file_path)
    elif ext in ("png", "jpg", "jpeg"):
        return OCRExtractor(file_path)
    return None

def download_and_extract(file: FileItem) -> dict:
    """Download a file from its signed URL and extract its text."""
    import traceback
    ext = file.name.rsplit(".", 1)[-1].lower()
    print(f"  [Download] URL: {file.signedUrl[:80]}...")

    try:
        response = httpx.get(file.signedUrl, timeout=30, follow_redirects=True)
        response.raise_for_status()
        print(f"  [Download] OK — {len(response.content)} bytes")
    except Exception as e:
        print(f"  [Download ERROR] {e}")
        return {"name": file.name, "status": "error", "error": f"Download failed: {str(e)}", "text": ""}

    # Write to a temp file with the correct extension
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        extractor = get_extractor_for(ext, tmp_path)
        if extractor is None:
            return {"name": file.name, "status": "error", "error": f"Unsupported file type: .{ext}", "text": ""}
        text = extractor.extract_text()
        print(f"  [Extracted] {file.name}: {len(text)} characters")
        return {"name": file.name, "status": "success", "text": text, "error": None}
    except Exception as e:
        print(f"  [Extraction ERROR] {e}")
        traceback.print_exc()
        return {"name": file.name, "status": "error", "error": f"Extraction failed: {str(e)}", "text": ""}
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"status": "Backend is running"}

@app.post("/generate-assessment")
def generate_assessment(payload: GenerateRequest):
    print("\n--- New Generate Request ---")
    print("Source type:", payload.sourceType)
    print("Config:", payload.config.model_dump())

    extracted_sources = []

    # 1. Process uploaded files (download + extract)
    if payload.sourceType == "upload" and payload.files:
        print(f"Files to process: {len(payload.files)}")
        for file in payload.files:
            print(f"  Processing: {file.name}")
            result = download_and_extract(file)
            extracted_sources.append(result)

    # 2. Process raw pasted text
    if payload.sourceType == "text" and payload.textContent:
        print(f"Text content received: {len(payload.textContent)} characters")
        extracted_sources.append({
            "name": "Pasted Text",
            "status": "success",
            "text": payload.textContent,
            "error": None,
        })

    if not extracted_sources:
        raise HTTPException(status_code=400, detail="No content provided.")

    successful = [s for s in extracted_sources if s["status"] == "success"]
    print(f"Successfully extracted {len(successful)}/{len(extracted_sources)} sources")

    return {
        "status": "success",
        "message": f"Extracted text from {len(successful)} source(s). Ready for next step.",
        "extracted_sources": extracted_sources,
    }