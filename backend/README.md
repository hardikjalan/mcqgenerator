# Backend (FastAPI)

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows — use source .venv/bin/activate elsewhere
pip install -r requirements.txt
uvicorn app.main:app --reload   # run from this directory, not the repo root
```

Interactive API docs: http://localhost:8000/docs 

## Layout

```
backend/
├─ app/
│  ├─ main.py              # App setup only: middleware, exception handlers, router mounting
│  ├─ core/                # Cross-cutting concerns
│  │  ├─ config.py         # Env loading + every shared limit/path
│  │  ├─ logger.py         # get_logger / is_debug_mode
│  │  ├─ exceptions.py     # DocumentProcessingError hierarchy
│  │  └─ responses.py      # success_response / error_response
│  ├─ api/routes/          # One module per resource — routes stay thin
│  │  ├─ health.py
│  │  └─ assessments.py
│  ├─ schemas/             # Pydantic request/response shapes
│  └─ services/            # The actual work — importable without FastAPI
│     └─ extraction/
│        ├─ pipeline.py       # download → temp file → LlamaIndex reader → Documents
│        ├─ ocr_fallback.py   # Scanned-PDF OCR — the gap the readers leave
│        └─ extractors/
│           └─ gemini_ocr.py  # Gemini Vision, with local Tesseract fallback
├─ .env                    # Server-side secrets (not committed)
└─ requirements.txt
```

## Conventions

- **Imports are absolute from the package root** — `from app.core.logger import
  get_logger`. No `sys.path` manipulation anywhere; that is what the `app`
  package is for.
- **Constants live in `core/config.py`**, not next to their first use. Anything
  two modules need — size caps, the debug output path, allowed origins — goes
  there so it cannot drift.
- **Routes don't do work.** A route validates, calls a service, and shapes a
  response. If a route grows a `try/except` around processing logic, that logic
  belongs in `services/`.
- **Parsing is LlamaIndex's job.** `pipeline.py` picks a reader per extension
  (`PyMuPDFReader`, `DocxReader`, `PptxReader`) and gets `Document` objects
  back. Don't hand-roll a parser for a new format — check for a reader in
  `llama-index-readers-file` first. Two deliberate exceptions live outside it:
  images go straight to `gemini_ocr` because `ImageReader`'s default parser
  pulls torch + transformers, and scanned PDFs go through `ocr_fallback`
  because `PyMuPDFReader` only reads the text layer.
- **Documents are the unit, text is the projection.** `download_and_extract`
  returns both; the route strips `documents` before serialising because
  `Document` is not JSON-safe. Keep it that way — those Documents are what the
  RAG pipeline indexes.
- **Errors are logged once, at the point of first catch.** Callers do not
  re-log. Clients only ever see `user_message`, never internals. Readers raise
  whatever their backing library raises, so `pipeline.py` maps anything
  unrecognised to `CorruptedFileError`.
- **Adding an endpoint:** new module in `api/routes/`, schemas in `schemas/`,
  logic in `services/`, then `include_router` in `main.py`.

## Notes

- `MAX_CUMULATIVE_SIZE_MB` in `core/config.py` is the source-of-truth upload cap.
  `MAX_CUMULATIVE_SIZE` in `frontend/lib/file-upload.ts` mirrors it as a UX
  convenience — change both together.
- `debug_extraction.txt` is written at the backend root when `LOG_LEVEL=DEBUG`.
  It is gitignored; it is a debugging aid, not an artifact.
