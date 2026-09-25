# Local storage validation

The local storage adapter persists immutable source snapshots, reports and job
states in a versioned SQLite database. Reopening the database preserves source
history; explicit startup recovery marks queued/running jobs as interrupted.
Transactions and foreign keys reject orphan reports and snapshot rebinding.

Local source identities use `local:<sha256>` and carry no Git commit. Existing
GitHub report JSON remains unchanged. Python accepts both identity forms;
TypeScript exposes matching schemas and a revision helper. Local report routing
and the account-free UI are not connected yet.

Validation on 2026-09-25:

- Backend: 302 passed, 37 skipped (PostgreSQL integration prerequisites absent).
- Frontend: 65 passed; production build passed (existing large chunk warning).
- New tests first failed for missing storage/identity support, then passed.
- Covered reopening, immutable history, transaction rollback, scoped lookup,
  interrupted jobs, job identity rebinding, unsafe source paths and legacy wire compatibility.

This is storage-level evidence, not an end-to-end local application acceptance.
