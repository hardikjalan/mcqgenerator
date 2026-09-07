"""
config.py
=========
Every tunable the backend has, read once, in one place.

Before this module the upload limits were written down three times — in
``frontend/lib/file-upload.ts``, in ``fetcher.py`` and in ``extraction.py`` —
with a comment in each telling the next person to remember the other two. That
is not a constraint, it is a wish. Now the backend has one copy and serves it
to the frontend over ``GET /limits``.

Nothing else calls ``load_dotenv``. ``main.py`` loads ``backend/.env`` before
importing this module.
"""

from __future__ import annotations

import os

# ── Uploads ───────────────────────────────────────────────────────────────────

MAX_FILE_BYTES = 5 * 1024 * 1024

# The ceiling for one /generate-assessment request. Equal to the per-file cap
# today, which means a single maximum-size file uses the whole budget.
MAX_CUMULATIVE_BYTES = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = (
    ".pdf", ".docx", ".doc", ".pptx", ".ppt",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
)


# ── Chunking ──────────────────────────────────────────────────────────────────

# Sizes are in WORDS, not tokens. Token counting needs a tokenizer, and the
# usual one (tiktoken) downloads its vocabulary from the internet on first use
# — a network call on a deployed host, inside a request, for a number we only
# need approximately. Words are free, deterministic and offline.
#
# The conversion is roughly 1 word ≈ 1.3 tokens for English prose, so the
# default 300 words is about 400 tokens. That fits comfortably inside the
# 8k-token window of the common embedding models. If you pick a model with a
# 256-token limit (all-MiniLM and friends), set this to about 150 or the tail
# of every chunk will be silently truncated at embedding time.
CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "300"))

# Overlap repeats the tail of one chunk at the head of the next, so a fact
# sitting on a boundary is whole in at least one of them. Too little and
# answers get cut in half; too much and the store fills with near-duplicates
# that crowd out genuinely different results. A sixth of the chunk is a
# common middle.
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "50"))

# A unit (one slide, one short page) below this is too small to stand alone as
# a chunk — a 15-word slide embeds to a vague, low-signal vector that matches
# everything and answers nothing. Units this small are merged with their
# neighbours first.
MIN_MERGE_WORDS = int(os.getenv("MIN_MERGE_WORDS", "80"))

# A trailing fragment below this is folded back into the previous chunk rather
# than stored on its own.
MIN_CHUNK_WORDS = int(os.getenv("MIN_CHUNK_WORDS", "25"))


# ── OCR ───────────────────────────────────────────────────────────────────────

# Absent key ⇒ no OCR provider ⇒ images are refused with a clear message and
# scanned PDFs fail as empty. Everything else keeps working, which is the point
# of making this optional rather than required.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Vision model used for OCR. Flash-Lite is the cheapest tier that reads text
# reliably; override in .env to trade up.
#
# Model names expire. gemini-2.0-flash was the default here until Google shut
# it down — a dead name fails at the first request, not at deploy time, so
# check this against the current model list when OCR starts erroring.
GEMINI_OCR_MODEL = os.getenv("GEMINI_OCR_MODEL", "gemini-2.5-flash-lite").strip()

# Hard ceiling on OCR calls per document. A 300-page scanned book would
# otherwise issue 300 vision requests from a single upload.
MAX_OCR_PAGES_PER_DOC = int(os.getenv("MAX_OCR_PAGES_PER_DOC", "20"))

# A PDF page with fewer than this many characters in its text layer is treated
# as scanned and sent to OCR. Not zero: scanned pages often carry a stray page
# number or a header stamped by the scanner.
OCR_TEXT_LAYER_THRESHOLD = int(os.getenv("OCR_TEXT_LAYER_THRESHOLD", "32"))

# Resolution for rendering a PDF page before OCR. 200 DPI is the usual floor
# for reliable recognition of body text; higher mostly costs bytes.
OCR_RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "200"))


# ── Embeddings ────────────────────────────────────────────────────────────────

# The same key as OCR. On Google's free tier embeddings cost nothing, and that
# is what this project runs on by default.
#
# One consequence to be aware of: under Google's API terms, content sent
# through the *unpaid* quota is used to improve Google's products and may be
# read by human reviewers, while content sent through the paid quota is not.
# Course material uploaded by faculty goes through this path. Enabling billing
# on the same key switches the terms without any code change here.
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001").strip()

# Vector width. A float is 4 bytes, so 3072 dimensions is 12KB per chunk and
# 768 is 3KB — four times as many documents inside Supabase's free 500MB.
# Retrieval quality barely moves at this corpus size, and the value is baked
# into the database column, so changing it later means re-embedding
# everything. Chosen deliberately rather than left at the model default.
EMBED_DIMENSIONS = int(os.getenv("EMBED_DIMENSIONS", "768"))

# Chunks sent per embedding request. Larger batches mean fewer requests, which
# is what the free tier limits; too large and one oversized batch is rejected
# whole.
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))

# Free-tier quota is per minute, so a burst gets refused rather than queued.
# Retries back off; beyond this the upload fails with a message that says so.
EMBED_MAX_RETRIES = int(os.getenv("EMBED_MAX_RETRIES", "3"))


# ── Vector store (Supabase pgvector) ──────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")

# The service-role key bypasses row-level security, so it must never reach the
# browser. It lives here, server-side, and nowhere else.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

# Tokens are verified against Supabase itself rather than by decoding them
# here, so no JWT secret is needed. Results are cached briefly; see auth.py.
AUTH_CACHE_SECONDS = int(os.getenv("AUTH_CACHE_SECONDS", "60"))

# How many chunks a search returns. Enough to cover a topic, few enough that
# the model is not handed a haystack.
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# Cosine similarity below this is not a match, it is the closest of a bad set.
# Without a floor, a question about a topic absent from the material still
# returns the eight least-irrelevant chunks and the model writes from them.
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.35"))


# ── Generation ────────────────────────────────────────────────────────────────

GEMINI_GENERATION_MODEL = os.getenv("GEMINI_GENERATION_MODEL", "gemini-2.5-flash").strip()

# Low but not zero. Questions should be reproducible enough to debug, varied
# enough that four questions on one topic are not four rephrasings.
GENERATION_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.4"))

# Questions asked of the model in one call. Asking for forty at once produces
# noticeably worse questions towards the end of the list, and one refusal loses
# the whole batch.
GENERATION_BATCH_SIZE = int(os.getenv("GENERATION_BATCH_SIZE", "5"))

# Ceiling per request, whatever the quiz config asks for.
MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS", "30"))

# Chunks handed to the model per batch of questions. More context is not
# better — the model starts writing questions from whatever is most quotable
# rather than what the objective asked for.
GENERATION_CONTEXT_CHUNKS = int(os.getenv("GENERATION_CONTEXT_CHUNKS", "6"))


def generation_enabled() -> bool:
    """True when questions can be generated."""
    return bool(GEMINI_API_KEY)


def auth_required() -> bool:
    """True when the API must identify the caller.

    Tied to Supabase being configured rather than to a separate switch: if
    there is a real project behind this deployment there are real users, and
    an endpoint that accepts anonymous uploads alongside them is how one
    teacher ends up reading another's material.
    """
    return bool(SUPABASE_URL)


def embeddings_enabled() -> bool:
    """True when chunks can be embedded."""
    return bool(GEMINI_API_KEY)


def vector_store_enabled() -> bool:
    """True when embedded chunks have somewhere to be stored."""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def ocr_enabled() -> bool:
    """True when an OCR provider is configured.

    Read through a function rather than a constant so a test can monkeypatch
    the key and see the change without reimporting the module.
    """
    return bool(GEMINI_API_KEY)
