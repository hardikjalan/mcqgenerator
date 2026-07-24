# Cognira
> AI‑powered adaptive assessment platform for automated quiz generation

## Overview
Cognira transforms static study materials (PDF, DOCX, PPTX, images) into personalized multiple‑choice quizzes. Faculty upload reference documents, configure quiz parameters, and the system uses Gemini Vision OCR plus LLM generation to produce curriculum‑aligned questions, delivering a premium, glass‑morphic UI for students.

## Tech Stack
| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, Lucide icons, Google Fonts (Inter, Space Grotesk) |
| **Backend** | FastAPI, Python 3.13, `google-genai` (Gemini Vision OCR), PyMuPDF, python‑docx, python‑pptx |
| **Auth & Storage** | Supabase (PostgreSQL, Auth, Storage) |
| **CI/CD** | GitHub Actions (test, lint, deploy) |
| **Deployment** | Vercel (frontend) • Railway / Render (backend) |
| **Other tools** | python‑dotenv, pytest, uvicorn |

## Architecture
Cognira follows a clear client‑server split:

1. **Authentication** – Google OAuth via Supabase.
2. **File Upload** – Validated (PDF/DOCX/PPTX/Image ≤ 10 MB) and stored in a private Supabase bucket (`faculty‑documents`).
3. **Extraction** – FastAPI extracts text layers; large images (> 1000 px in either dimension) are sent to Gemini Vision OCR.
4. **Quiz Generation** – Combined text and user‑provided configuration are sent to Gemini 2.0 Flash (future: Claude).
5. **Delivery** – Frontend renders questions, tracks answers, and stores results.

```mermaid
graph TD
    User([User]) -->|OAuth| Auth[Supabase Auth]
    Auth -->|Session| Proxy[Next.js Proxy Middleware]
    Proxy -->|Role Check| Dashboard[Dashboard (Faculty / Student / Admin)]
    Dashboard -->|Upload| Storage[Supabase Storage]
    Dashboard -->|Config| ConfigForm[Quiz Config Form]
    ConfigForm -->|Submit| Backend[FastAPI Backend]
    Backend -->|Extract Text| Extractors[PDF / DOCX / PPTX / Image Extractors]
    Extractors -->|Compiled Text| Gemini[Gemini Vision OCR (gemini‑2.0‑flash)]
    Gemini -->|Text| Backend
    Backend -->|Generate| LLM[Gemini / Claude (future)]
    LLM -->|Questions| Dashboard
```

## Features
### Completed ✅
- Dark glass‑morphic UI with custom fonts and micro‑animations.
- Secure Google OAuth flow with role‑based routing (faculty, student, admin).
- Multi‑format file ingestion (PDF, DOCX, PPTX, images) with progress UI and deletion.
- Smart document extraction: text‑layer reading, image‑area heuristics, Gemini OCR fallback.
- 7‑step quiz‑builder wizard (subject, audience, topics, objectives, type, count, time).
- Structured debug logging saved to `debug_extraction.txt`.

### In Progress 🔄
- **AI Quiz Generation API** – wiring extracted text to Gemini/Claude for MCQ creation (V1 uses Gemini 1.5‑Flash).
- **Student Assessment Engine** – timer, auto‑save drafts, answer validation, scoring.

### Planned 📋
- Student quiz player with timer and scoring UI.
- Analytics dashboard & adaptive difficulty engine.
- Admin control panel (user & content management).
- LMS export formats (QTI, CSV).
- Multilingual question generation.
- Local‑storage draft auto‑save.
- Async/parallel processing for large documents (future performance boost).

## Project Structure
Frontend and backend are separate deployables with no shared root, no shared
`node_modules`, and no shared env file.

```
mcqgenerator/
├─ frontend/                   # Next.js 16 → Vercel
│   ├─ app/                    # App Router
│   │   ├─ page.tsx            # Landing / login
│   │   ├─ auth/callback/      # Supabase OAuth callback
│   │   ├─ onboarding/         # Role‑selection flow
│   │   └─ dashboard/          # faculty / student / admin
│   ├─ components/             # Placement is by AUDIENCE — see components/README.md
│   │   ├─ ui/                 # Style‑only primitives (form fields, buttons)
│   │   ├─ shared/             # Used by more than one role
│   │   ├─ faculty/            # Faculty‑only
│   │   └─ student/            # Student‑only
│   ├─ lib/                    # Runtime helpers & constants (role‑agnostic)
│   │   ├─ supabase/           # Browser + server clients
│   │   ├─ file-upload.ts      # Size caps, allowed types, validators
│   │   └─ quiz-config.ts      # Question type / count option lists
│   ├─ types/                  # Type‑only declarations
│   │   ├─ database.ts         # Mirrors Supabase tables & enums
│   │   ├─ quiz.ts             # QuizConfig, QuestionType
│   │   └─ upload.ts           # UploadedFile, ContentTab
│   ├─ proxy.ts                # Auth + role routing middleware
│   └─ .env.local              # NEXT_PUBLIC_* only (not committed)
├─ backend/                    # FastAPI → Railway / Render
│   ├─ app/
│   │   ├─ main.py             # App setup only — middleware, handlers, routers
│   │   ├─ core/               # config, logger, exceptions, responses
│   │   ├─ api/routes/         # health.py, assessments.py
│   │   ├─ schemas/            # Pydantic request/response shapes
│   │   └─ services/extraction/# pipeline.py + extractors/ + loaders/
│   ├─ .env                    # Server‑side secrets (not committed)
│   └─ requirements.txt
├─ supabase/migrations/        # Numbered — run in order, 01 → 05
├─ docs/                       # project.md, notes-qa.md
└─ README.md                   # High‑level project overview
```

### Placement rules
Both a faculty and a student flow live in this repo, so the boundary that
matters is **who consumes a file**, not what it does:

- Anything imported by both roles belongs in `lib/`, `types/`, `components/ui/`
  or `components/shared/` — never inside `components/faculty/`.
- A cross-role import (`app/dashboard/student` reaching into
  `components/faculty/`) means the file is in the wrong folder. Promote it.
- Role folders may only be imported by their own dashboard route.
- On the backend, routes validate and delegate; the work lives in `services/`,
  and every shared constant lives in `core/config.py`.

## Setup & Installation
1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/cognira.git
   cd cognira
   ```
2. **Backend** — start this first; the faculty dashboard calls it on port 8000.
   ```bash
   cd backend
   python -m venv .venv
   . .venv/Scripts/activate   # Windows
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   Create `backend/.env` with `GEMINI_API_KEY` (and `TESSERACT_CMD_PATH` if the
   Tesseract fallback is used).
3. **Frontend**
   ```bash
   cd ../frontend
   npm install
   npm run dev      # http://localhost:3000
   ```
   Create `frontend/.env.local` with the two `NEXT_PUBLIC_SUPABASE_*` values.
4. **Supabase** – create a project, enable Auth & Storage, then run
   `supabase/migrations/01_schema.sql` → `05_onboarding.sql` in order.

## API / Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Liveness check — `{ success, data: { status } }`. |
| `POST` | `/generate-assessment` | Takes `sourceType` + files/text + quiz config; downloads each signed URL, extracts text, returns `extracted_sources`. |

Routes are defined in `backend/app/api/routes/`; interactive docs at
`http://localhost:8000/docs`. MCQ generation from the extracted text is still
in progress — the endpoint currently returns extraction results only.

## Environment Variables
Two files, no overlap. Neither is committed.

| File | Variable | Description |
|------|----------|-------------|
| `backend/.env` | `GEMINI_API_KEY` | Gemini Vision API key. |
| `backend/.env` | `TESSERACT_CMD_PATH` | Optional path to the Tesseract binary (local OCR fallback). |
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL. |
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key. |

Only `NEXT_PUBLIC_*` values reach the browser. The backend reads its `.env`
once, in `app/core/config.py` — no other module calls `load_dotenv`.

**Never commit real values**; keep them in `.env.local`.

## Known Issues & Limitations
- No batching or delayed processing in V1 – documents are handled sequentially.
- `MAX_IMAGES_PER_DOC = 20` caps image‑OCR calls to control cost.
- Image‑area heuristic: OCR runs only when an image occupies **> 75 %** of page area **and** its dimensions are ≥ 1000 px (width or height).
- Small logos, bullet‑point graphics, or background images are ignored, but edge‑cases may still trigger OCR.
- Only Gemini Vision OCR is integrated; other providers are not yet supported.

## Changelog
### v1.0 — 2026‑06‑22
- Restructured `PROJECT.md` to the new canonical template.
- Consolidated tech‑stack, architecture diagram, and feature lists.
- Added explicit setup instructions, API table, environment variables, known issues, and notes for future development.

## Notes for Future Me
- **SDK choice:** `google-genai` replaces the deprecated `google-generativeai`; keep it updated to the latest version.
- **Image limits:** The 75 % area rule and `MAX_IMAGES_PER_DOC` were introduced to keep Gemini API costs predictable. Re‑evaluate thresholds if OCR quality suffers.
- **Sequential processing:** Simpler for early testing; consider a background task queue (e.g., Celery or RQ) when scaling.
- **Styling:** Tailwind CSS v4 is locked; avoid mixing with other CSS frameworks to maintain the glass‑morphic aesthetic.
- **Security:** Supabase RLS policies are critical; any new storage bucket must inherit the same user‑scoped policy.
