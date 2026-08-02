"""
config.py
=========
Single place where the backend reads its environment and declares the limits
that more than one module needs.

Anything defined here was previously duplicated across modules (the debug output
path lived in four extractors) or buried in main.py (the upload cap). Import
from here instead of recomputing paths relative to __file__.

Environment
-----------
Loads ``backend/.env`` — server-side secrets only. The frontend has its own
``frontend/.env.local`` and never shares this file.
"""

import os

from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
# __file__ is: backend/app/core/config.py → three levels up is backend/
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENV_PATH = os.path.join(BACKEND_DIR, ".env")
load_dotenv(dotenv_path=ENV_PATH)

# Where extractors dump their last raw extraction when LOG_LEVEL=DEBUG.
# Gitignored — it is a debugging aid, not an artifact.
DEBUG_OUTPUT_PATH = os.path.join(BACKEND_DIR, "debug_extraction.txt")

# ── Secrets ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TESSERACT_CMD_PATH = os.getenv("TESSERACT_CMD_PATH")

# ── Upload limits ─────────────────────────────────────────────────────────────
# Cumulative cap across ALL files in one generate request. This is the
# source-of-truth enforcement; the frontend check in
# frontend/lib/file-upload.ts (MAX_CUMULATIVE_SIZE) is a UX convenience that
# avoids pointless Supabase uploads. Keep the two in sync.
MAX_CUMULATIVE_SIZE_MB = 5

# Mirrors ALLOWED_EXTENSIONS in frontend/lib/file-upload.ts. Legacy binary
# ".ppt" is deliberately absent: python-pptx cannot read it, so accepting it
# only bought a download followed by a parse failure. The frontend never
# offered it either.
SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "png", "jpg", "jpeg"}

# Cap on Gemini OCR calls per document — keeps API cost predictable.
MAX_IMAGES_PER_DOC = 5

# ── CORS ──────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = ["http://localhost:3000"]
