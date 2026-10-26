# Cognira implementation guide

Cognira implements the six functional modules described in
`Review_2_Cognira_1.pptx`. The frontend is Next.js 16 / React 19; the API uses
FastAPI, Python 3.12, Google GenAI, LlamaIndex and Supabase.

## 1. Document ingestion

Files are detected by content signatures, including inspection of Office ZIP/OLE
containers. PDF, DOCX, PPTX, native Word 97+ DOC and legacy PPT text, PNG and JPEG
are supported. Renaming an unsupported file does not bypass detection.

Text-layer extraction is preferred. Gemini vision transcribes raw images, scanned
PDF pages, and image-only modern Office documents. Uploads go to the private
faculty-documents bucket. The API accepts only signed HTTPS links on the configured
Supabase host under the authenticated faculty member's own folder. Redirects are
disabled and streaming downloads enforce the byte limit.

Limits: ten files and 5 MB combined per request; 100 PDF pages or PowerPoint
slides; twenty scanned pages/images per document; 20 million pixels per image;
100 MB expanded Office archive; 500,000 extracted characters and 1,000 child
chunks per document. Oversized or unreadable inputs return errors.

Encrypted Office documents and uncommon pre-Word-97 variants need conversion.
Legacy Office support extracts stored text; convert scanned legacy files to PDF
for OCR. Vision transcription can make mistakes, particularly in equations and
complex layouts.

## 2. Cleaning and chunking

Cleaning removes recurring headers/footers, normalizes whitespace, repairs prose
line wrapping and joins line-end hyphenation while protecting code-like content.
Semantic chunks retain headings, tables, code and mathematical blocks. Small
adjacent chunks merge where structure and size allow. Parent contexts retain
page provenance and overlapping children support retrieval.

Source and node identifiers are deterministic and owner-scoped. Reuploading
identical bytes replaces that owner's source atomically through a database RPC.
Other owners' material is never replaced.

## 3. Grounded generation

Gemini embeddings use 768 dimensions with RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY
task types. PostgreSQL pgvector/HNSW searches indexed children and returns their
parent contexts. Each requested topic must pass a cosine similarity floor of
0.35; at least one relevant parent per topic survives context selection.

Structured outputs support single-answer, multi-select and true/false items.
Questions carry explanations, source IDs, parent IDs, quoted evidence, trusted
file/page citations, topic, Bloom classification and difficulty. Deterministic
checks reject missing/nonmatching evidence, invalid keys/options, near-duplicates,
and conspicuous answer-length giveaways. A separate model pass verifies answer
and explanation support, ambiguity, cognitive level and difficulty. Failed items
are regenerated up to three times. An incomplete verified set is reported as an
error rather than silently returned.

The default generation model is gemini-3.5-flash-lite with gemini-3.8-flash
fallback; see GenerationConfig. OCR uses the same provider. Provider access,
quotas and response times vary. Calls have timeouts and bounded retries. A
second model pass reduces errors but does not guarantee factual correctness;
faculty review is part of the workflow.

## 4. Bloom classification

The generator and independent reviewer use a six-level rubric: Remember,
Understand, Apply, Analyze, Evaluate and Create. Faculty select allowed levels
and see the classifier's rationale. Prompts request balanced coverage where the
material supports it. Distribution is not a calibrated educational guarantee.

A Create-level MCQ asks a student to judge or select a proposed design. It does
not measure the student's ability to produce an original artifact. Difficulty
(1–5) is an AI estimate, not an empirically calibrated item parameter.

## 5. Adaptive delivery and knowledge tracing

The API persists drafts, publication state, enrollment, attempts, committed
answers and draft selections. Publishing freezes questions and yields a join code.
Teachers can close enrollment. Existing attempts retain their recorded deadline.

Students have one resumable attempt per assessment. The server owns deadlines,
validates the current question and scores exact option sets. Multi-select has no
partial credit. Draft selections autosave but do not count until submitted;
unanswered questions count as incorrect. Server checks enforce expiry even when
the browser timer or network is interrupted. Expired active records finalize
when accessed, answered or inspected through analytics.

Adaptive sequencing selects from the existing question bank, balancing topic
coverage and choosing estimated difficulty near the student's mastery estimate.
All bank questions remain part of the quiz; adaptation changes order, not the
final number of questions. Fixed sequencing is also available.

Bayesian knowledge tracing starts at 0.35, uses question-format guessing rates
and difficulty-dependent slip, then an 0.08 learning transition. It persists
per-topic probabilities and observation counts across completed assessments
with the same normalized subject. Parameters are heuristics and require student
data to calibrate. Sparse observations are explicitly labelled estimates.

## 6. Analysis and feedback

Submitted attempts show scores, selected/correct answers, explanations,
source quotes, topic accuracy, mastery estimates and targeted review suggestions.
Teachers see completion counts, average scores, topic/Bloom accuracy and student
results, with CSV export. Assessment content can be exported as JSON.
The student progress view lists completed assessments and recent feedback.

Administrators can inspect content, change roles, suspend users and inspect
audit events. Audit writes are best effort and never invalidate an otherwise
successful user action.

## Authentication and database security

Every API action validates the Supabase bearer token and database profile role.
Editable authentication metadata is not trusted for authorization. Suspension is
checked per request. Faculty ownership and student enrollment/attempt ownership
are enforced server-side. Version checks protect concurrent edits and responses.

Assessment tables are inaccessible to authenticated browser database clients:
answer keys travel through the API only after submission. Upload policies enforce
owner folders and faculty/admin status. Onboarding can choose student/faculty
once; administrator access requires a trusted server operation. Profile RPCs
bind the caller to auth.uid(), and browser grants exclude role and suspension.

Run the original six SQL setup files, then backend/schema.sql last. The latter
is the authoritative upgrade and hardening script, including pgvector dimensions,
parent_id, atomic replacement, attempt state and access policies. It is repeatable
and preserves existing data. Do not subsequently run an older setup file alone.

## Validation and operational limits

Unit tests cover parser signatures and Office formats, OCR dispatch, cleaning,
stable IDs, embedding dimensions, retrieval, evidence rejection, independent
review, scoring, adaptive selection, mastery, expiry, concurrency and access checks.
The opt-in smoke script exercises real Supabase authentication/storage and API
lifecycle operations; --live-generation also invokes real embeddings and Gemini.

TypeScript, ESLint and a production Next.js build are required checks. Browser
interaction testing was unavailable in this implementation session because the
computer-use service could not validate the active URL; API and build checks do
not substitute for final manual browser acceptance testing.

List endpoints currently cap results at 100–5,000 rows depending on the resource.
Large institutions need pagination, background ingestion/jobs, rate limits and
calibrated mastery parameters before scaling beyond this project deployment.
No LMS integration, plagiarism/proctoring system or multilingual accuracy
guarantee is claimed. The presentation's illustrative extraction benchmark is
not a measured result of this repository.
