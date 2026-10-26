# Cognira

Source-grounded, adaptive assessments for faculty and students.

Faculty can upload PDF, DOCX, PPTX, DOC, PPT, PNG or JPEG files, or paste source
text; generate and review questions; publish a timed quiz; and inspect results.
Students join with a code, resume saved attempts, and receive scores, explanations,
source citations and topic feedback. Administrators manage accounts and content.

See [the implementation guide](docs/project.md) for architecture, limitations and
verification, and [the completed checklist](docs/implementation-progress.md) for
the six modules from the review presentation.

The latest [end-to-end QA report](docs/qa-report.md) records tested flows, fixes,
screenshots and the remaining verification limits.

## Local setup

Use Python 3.12 and Node.js 20.9 or newer.

1. Copy the root `.env.example` to `.env` and fill in your server credentials.
2. Copy `frontend/.env.example` to `frontend/.env.local` and fill in the public
   Supabase URL/key and API address.
3. In Supabase SQL Editor, run `supabase/migrations/01_schema.sql` through
   `06_signin_hardening.sql` in order, then **run `backend/schema.sql` last**.
   Existing installations can run `backend/schema.sql` alone. It upgrades tables,
   retrieval, assessment persistence and access policies without dropping data.
4. Enable Google OAuth in Supabase Auth. Allow
   `http://localhost:3000/auth/callback` as a redirect URL.

Start the API in one PowerShell terminal:

```powershell
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Start the frontend in another:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. API documentation is at http://localhost:8000/docs.
On first sign-in choose faculty or student. To create your first administrator
after that person has signed in:

```powershell
cd backend
.venv/Scripts/python.exe scripts/bootstrap_admin.py person@example.com
```

The service role key and Gemini key belong only in the root server `.env` or
backend hosting environment. Never put them in `NEXT_PUBLIC_*` variables.

## Use

- Faculty: upload material or paste text, configure topics, formats, Bloom levels,
  count and duration, then generate. Review/edit the saved draft, publish and
  share its join code. The Assessments tab holds saved drafts and results.
- Students: join with the code, start or resume, then submit each answer to move
  on. Selections autosave; only committed answers count towards the score.
- Admins: manage roles and suspension, inspect assessments and review audit events.

## Verification

```powershell
cd backend
.venv/Scripts/python.exe -m unittest discover -p 'test_*.py'
```

From `frontend`, run `npm test`, `npx tsc --noEmit`, `npx eslint` and `npm run build`.
Stop `next dev` before a production build because they share `.next`.

The opt-in live integration test requires a running local API and real service
credentials. It creates isolated test accounts and removes their data afterwards:

```powershell
cd backend
.venv/Scripts/python.exe scripts/smoke_assessment.py --live-generation
```

## Deployment

Deploy `frontend/` to Vercel (root directory: `frontend`). Set its public
environment variables before building; `NEXT_PUBLIC_API_URL` must point to the
deployed API.

Deploy `backend/` separately using
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Supply
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY` and
`ALLOWED_ORIGINS=https://your-frontend-domain`. Add the deployed OAuth callback
to Supabase's redirect allowlist. Set the host request timeout high enough for
document extraction, embeddings, generation and independent review.
