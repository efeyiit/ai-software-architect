# Account-free local runtime

`python -m app.local.main` (from `backend`) binds only to 127.0.0.1:8080.
It uses SQLite and the existing parser/coordinator pipeline without PostgreSQL
or OAuth. Public GitHub imports retain their actual commit. Local-folder reports
retain their explicit content identity, including documentation drafts.

Local API requests use a same-site HttpOnly cookie and a CSRF token acquired
without a user login. Host/origin checks and bounded request buffering apply.
An OS lock prevents a second process from recovering another process's live
jobs. Analysis runs in a bounded queue with status and cancellation endpoints.

Validation on 2026-09-25:

- Full backend regression: 320 passed, 37 PostgreSQL-dependent skips.
- Additional real-coordinator local/public pipeline tests: 2 passed.
- Local API tests cover persisted source import/read, restart, Host/Origin and
  fetch metadata rejection, missing session/CSRF, body limit and process lock.
- Deterministic reports explicitly state AI is unavailable.

Browser integration and actual model acceptance remain separate checks.
