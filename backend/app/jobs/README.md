# PostgreSQL analysis jobs

This module stores analysis requests in PostgreSQL. An authenticated caller
provides its trusted user ID, repository ID, exact commit SHA, and an opaque
idempotency key to `JobStore.enqueue`. The repository snapshot must already
exist for that owner and SHA. Repeating the same request returns the same job;
reusing a key for a different request raises `IdempotencyConflict`. Only a
hash of the key is stored. `get` and `cancel` are owner scoped.

Call `app.database.apply_schema(connection)` and then
`app.jobs.apply_jobs_schema(connection)` when provisioning a database. Both
schema functions are additive initial setup, not a migration system. Jobs
require a PostgreSQL connection with `autocommit=True`; each transition uses
a short transaction. The application database role must be restricted to this
data layer. Do not accept a user ID from request data as proof of identity.

A separate process runs `Worker(connection_factory, handler).run_forever(stop)`.
The factory returns a fresh autocommit connection on each call. `handler`
accepts a `JobContext` and returns an `AnalysisResult` whose
`analysis_id` is the job ID and whose repository and SHA match the job. It
should check `context.should_stop()` between bounded stages. The worker keeps
its lease alive while the handler runs. Multiple workers claim with PostgreSQL
row locks and `SKIP LOCKED`; an expired lease may be reclaimed. The old worker
cannot store its result after its claim token expires. Results and job
completion commit together. The handler must be safe to run more than once,
since a crash can cause at-least-once execution before a result is committed.

The job states are `queued`, `running`, `completed`, `partial`, `failed`, and
`cancelled`. A `completed` job has a succeeded analysis. A `partial` job has a
durably stored partial analysis with its available findings and safe errors;
it is terminal but must not be treated as a complete success by a cache.
Retryable failures return to `queued` with bounded backoff and an attempt
limit. A final failed `AnalysisResult`, including its available role findings
and safe errors, is saved atomically with the `failed` job state. Retryable
intermediate attempt reports are not retained; only the final report is
stored. A queued cancellation is immediate. A running cancellation is
cooperative: the handler should stop, and the worker discards any returned
result unless it is a matching `cancelled` analysis, which is saved atomically
with the cancelled job. The queue does not execute repository
code. Logs include job IDs, attempts, and state events;
exception messages, source content, tokens, and repository URLs are omitted.

This module has no HTTP route or OAuth callback. An API integration must
authenticate the caller, enqueue and return promptly, expose owner-scoped
status, and run the actual repository pipeline in a separate worker process.

For the real PostgreSQL tests, set `ARIADNE_TEST_DATABASE_URL` to a disposable
database whose role can create schemas, then run from `backend/`:

```powershell
uv run pytest tests/jobs -q
```

Each test creates and drops only its own uniquely named schema. A skipped
test does not verify PostgreSQL behavior.
