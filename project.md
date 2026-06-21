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
```
mcqgenerator/
├─ app/                # Next.js frontend
│   ├─ dashboard/      # Faculty / Student / Admin pages
│   ├─ onboarding/     # Role‑selection flow
│   └─ globals.css
├─ backend/            # FastAPI API
│   ├─ extractors/     # PDF / DOCX / PPTX / OCR services
│   ├─ loaders/        # File loaders (PDF, DOCX, PPTX)
│   ├─ main.py         # FastAPI entry point
│   └─ requirements.txt
├─ supabase/           # Database schema & RLS policies
│   ├─ schema.sql
│   ├─ policies.sql
│   └─ onboarding.sql
├─ .env.local          # API keys (not committed)
└─ README.md           # High‑level project overview
```

## Setup & Installation
1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/cognira.git
   cd cognira
   ```
2. **Create a `.env.local`** (copy the example and fill in real values).
3. **Backend**
   ```bash
   cd backend
   python -m venv venv
   . venv/Scripts/activate   # Windows
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
4. **Frontend**
   ```bash
   cd ../app
   npm install
   npm run dev      # Vercel dev server on http://localhost:3000
   ```
5. **Supabase** – set up a project, enable Auth & Storage, and add the URL/ANON key to `.env.local`.
6. **Test** – run `pytest` in `backend` to verify extractors.

## API / Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/extract` | Accepts a file upload, returns combined extracted text and image‑OCR stats. |
| `POST` | `/api/generate` | Takes extracted text + quiz config, returns structured MCQs. |
| `GET`  | `/api/health` | Simple health‑check. |

*(Endpoints are defined in `backend/main.py`.)*

## Environment Variables
| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini Vision API key (backend). |
| `SUPABASE_URL` | Supabase project URL (backend). |
| `SUPABASE_ANON_KEY` | Supabase anon key (backend). |
| `NEXT_PUBLIC_SUPABASE_URL` | Same URL exposed to the frontend. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Same anon key exposed to the frontend. |

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
