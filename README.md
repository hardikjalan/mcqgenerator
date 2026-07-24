# Cognira

AI-powered adaptive assessment platform. Faculty upload course material and
configure a quiz; the system extracts the text and generates MCQs. Students take
the generated assessments.

Full detail — architecture, features, roadmap — lives in [docs/project.md](docs/project.md).

## Layout

Two independently deployable apps in one repo:

```
mcqgenerator/
├─ frontend/            # Next.js 16 (App Router) → deploys to Vercel
├─ backend/             # FastAPI + Gemini OCR    → deploys to Railway / Render
├─ supabase/migrations/ # Numbered SQL — run 01 → 05 in order
└─ docs/                # project.md, notes-qa.md
```

Nothing outside `frontend/` is needed to build the frontend, and nothing outside
`backend/` is needed to run the API. Each owns its own env file — they never
share one.

## Running it

Two terminals. **Backend first** — the faculty dashboard calls it on port 8000.

**Backend** (from `backend/`):

```bash
python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt && uvicorn app.main:app --reload
```

**Frontend** (from `frontend/`):

```bash
npm install && npm run dev
```

Open http://localhost:3000.

## Environment

Neither env file is committed. Create both:

| File | Variables |
|------|-----------|
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
| `backend/.env` | `GEMINI_API_KEY`, `TESSERACT_CMD_PATH` |

Only `NEXT_PUBLIC_*` values reach the browser — server-side secrets belong in
`backend/.env` and nowhere else.

## Database

Run the files in `supabase/migrations/` in the Supabase SQL Editor in numeric
order (`01_schema.sql` → `05_onboarding.sql`). They are idempotent, so re-running
is safe.

## Where things go

Both a faculty and a student flow live here, so placement follows **who uses a
file**, not what it does:

- `frontend/components/` — see [components/README.md](frontend/components/README.md) for the
  `ui/` vs `shared/` vs `faculty/` vs `student/` rule.
- `frontend/lib/`, `frontend/types/` — role-agnostic. Anything both roles import
  belongs here, never inside a role folder.
- `backend/app/api/routes/` — one module per resource; routes stay thin.
- `backend/app/services/` — the actual work. Reusable without importing FastAPI.
