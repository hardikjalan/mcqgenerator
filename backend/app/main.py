"""
main.py
=======
FastAPI application entry point.

Run from the backend/ directory:
    uvicorn app.main:app --reload

Interactive docs: http://localhost:8000/docs

This module owns app setup only — environment, CORS, error handlers, routers.
The endpoints live in routes.py and the request/response shapes in schemas.py.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routes import router

# backend/.env — server-side only. Resolved from this file rather than the
# working directory so it loads the same way however uvicorn is started.
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# A browser refuses a cross-origin response unless the server names the calling
# origin. The Next.js app runs on :3000 and this API on :8000 — different ports
# are different origins, so without this every fetch from the dashboard fails,
# and it surfaces as a generic network error rather than a CORS one.
#
# Comma-separated in .env so a deploy can add its Vercel URL without a code
# change. Do not put "*" here: it is invalid alongside allow_credentials.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app = FastAPI(title="MCQ Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Error shape ───────────────────────────────────────────────────────────────
# Every failure leaves as {"error": "<one sentence>"}, whatever raised it.
# FastAPI's own defaults are two different shapes — {"detail": "..."} for
# HTTPException and {"detail": [ ...list of field errors... ]} for validation —
# and the dashboard prints whatever it finds straight into an alert, so an
# unconverted validation error would render as "[object Object]".

@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # The field-level detail is for us, not the user — log it, send a sentence.
    print(f"[validation] {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"error": "The request was not in the format the server expected."},
    )


app.include_router(router)
