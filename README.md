# Cognira

AI-powered adaptive assessment platform. Faculty upload course material and
configure a quiz; a RAG pipeline extracts the text and (eventually) generates
MCQs. Students take the generated assessments.

**Status:** the pipeline is complete end to end — upload, extract, chunk,
embed, retrieve, generate. Generated quizzes are not yet saved for students to
take.

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

Run the tests with `pytest` from `backend/` — no network or API key needed.

**Frontend** (from `frontend/`):

```bash
npm install && npm run dev
```

Open http://localhost:3000.

## Environment

Neither env file is committed — copy the templates:

```bash
cp frontend/.env.example frontend/.env.local
```

| File | Variables |
|------|-----------|
| `frontend/.env.local` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL` |
| `backend/.env` | `ALLOWED_ORIGINS`, `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` — all optional. See `backend/.env.example`. |

Setting `SUPABASE_URL` turns on authentication: every request must then carry
a signed-in user's token, and uploads, indexing and search are scoped to that
user. Leaving it unset leaves the API open — fine on your own machine, never
on anything a second person can reach.

The backend runs with no API key at all. `GEMINI_API_KEY` switches on OCR and
embeddings; the two Supabase values switch on the vector store. Without them
files are still read and chunked — they just are not searchable. The
service-role key bypasses row-level security, so it must never reach the
browser.

Only `NEXT_PUBLIC_*` values reach the browser — server-side secrets belong in
`backend/.env` and nowhere else.

## Database

Run the files in `supabase/migrations/` in the Supabase SQL Editor in numeric
order (`01_schema.sql` → `09_chunk_scoping.sql`). They are idempotent, so
re-running is safe.

**`08_ownership_hardening.sql` is a security fix — run it on any existing
project.** Before it, any faculty member could read and delete any other
faculty member's files, and the admin role could be self-assigned through the
onboarding RPC. It depends only on `01`-`06`, so it applies whether or not the
RAG work is in. `07` enables pgvector and `09` scopes retrieval by owner; both
are only needed once search is switched on.

## Deploying

The frontend and backend deploy separately. **This repo has no `package.json` at
its root** — it's at `frontend/package.json`, so the host has to be told where
to look or it won't find Next.js at all.

### Vercel (frontend)

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` |
| Framework Preset | Next.js (auto-detected once the root is right) |
| Build Command | leave default |

Then add the three `NEXT_PUBLIC_*` variables under **Settings → Environment
Variables**. The build reads them, so a deploy started before they were added
will fail — add them, then redeploy.

Set `NEXT_PUBLIC_API_URL` to the deployed backend address, not localhost.

### Backend (Railway / Render)

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

Set `ALLOWED_ORIGINS` to the deployed frontend address — otherwise the browser
blocks every request as a cross-origin violation. It is read in `app/main.py`
and is comma-separated, so staging and production can share a deploy.

`.doc` and `.ppt` uploads fall back to binary text salvage on these hosts —
neither Microsoft Word nor `antiword` is installed, so fidelity is lower than
on a Windows desktop. `.docx` and `.pptx` are unaffected.

## Where things go

Both a faculty and a student flow live here, so placement follows **who uses a
file**, not what it does:

- `frontend/components/` — see [components/README.md](frontend/components/README.md) for the
  `ui/` vs `shared/` vs `faculty/` vs `student/` rule.
- `frontend/lib/`, `frontend/types/` — role-agnostic. Anything both roles import
  belongs here, never inside a role folder.
- `backend/app/routes.py` — endpoints stay thin: validate, delegate, shape.
- `backend/app/services/rag/` — the pipeline, in numbered layers. Imports no
  FastAPI and is usable from a script or a worker.
- `backend/app/services/extraction.py` — the only module that knows about both
  HTTP and the pipeline.
