# Cognira implementation checklist

Scope: the six functional modules and requirements in Review_2_Cognira_1.pptx.
Existing user data and unrelated workspace changes must be preserved.

- [x] Strict format detection, PDF/DOCX/PPTX/DOC/PPT/image ingestion, vision OCR
- [x] Cleaning, line-wrap repair, deterministic owner-scoped chunks and replacement
- [x] Task-specific embeddings, topic retrieval and similarity threshold
- [x] Structured question validation, evidence/citations, semantic verification
- [x] Bloom classification, difficulty and topic metadata
- [x] Authenticated assessment persistence, teacher review/edit/publish/close
- [x] Student enrollment, resumable timed attempts and server-side scoring
- [x] Adaptive selection, persistent knowledge tracing and feedback
- [x] Teacher topic analytics and admin management
- [x] Ownership policies, role security, bounded requests and safe downloads
- [x] Regression tests, live lifecycle checks, frontend type/lint/build checks
- [x] Setup documentation, limitations and repeatable database upgrades

Decisions: use Supabase Auth and the existing assessment tables, preserve answer
keys on the server during attempts, use optimistic version checks for concurrent
requests, and label mastery as a Bayesian estimate rather than a measured fact.

## Verification on 26 October 2026

- 40 backend unit tests passed.
- TypeScript, ESLint and the production Next.js build passed.
- Five frontend onboarding regressions cover stalled sessions, request timeouts,
  plain-object errors, unexpected roles and deadline cleanup. Live JavaScript
  onboarding verified role assignment, retry safety and Google-name preservation.
- The complete checked-in database upgrade applied successfully, including a repeat run.
- Live PDF upload, extraction, 768-dimensional embeddings, atomic indexing,
  retrieval, evidence validation, independent semantic/Bloom review, draft save
  and publication passed using the configured services.
- Live vision OCR, atomic reupload replacement, draft editing and rejection of
  an unsupported edited explanation passed.
- Live enrollment, resume/autosave, stale-version conflicts, all three scoring
  formats, persistent mastery, analytics, expiry, closure, account suspension,
  administrator restrictions, storage isolation and answer-key protection passed.
- All isolated test accounts and test data were removed after verification.
- CI configuration was added; its hosted GitHub run has not been observed here.

Manual browser acceptance testing remains: the computer-use service could not
validate the active browser URL in this session. The implementation and API
checks above passed, but visual rendering and keyboard interaction need a final
browser walkthrough. Deployment to a public hosting environment was not part of
this local verification.

The measured cleaning benchmark and educational effectiveness claims in the
presentation require separate experiments; they are not inferred from these tests.
