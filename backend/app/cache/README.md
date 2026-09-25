# Completed analysis cache

Install `apply_cache_schema(connection)` after the core database and job schemas
in a fresh database or isolated schema. `schema.sql` is additive; deployment
migrations for an existing database remain an integration responsibility.

`AnalysisCache` uses an autocommit psycopg connection and a mandatory
`revalidate_access(user_id, repository_id) -> bool` callback. The caller must
derive `user_id` from the authenticated session. For private repositories the
callback must check the user's **current** GitHub permission on every `get`
and `put`, using a valid token and a fresh GitHub request. A stored OAuth link,
past permission, or cached boolean is insufficient. A false result is a miss;
an exception stops the operation without returning cached content. The cache
cannot provide this GitHub check itself because it has no token or repository
reader. Public repository callers may validate current repository availability.
Never expose the cache directly through an endpoint that accepts an arbitrary
user ID or caller supplied access callback.

Build a `CacheKey` with the local owner and repository IDs, exact branch and
40-character commit SHA, `config_digest(config)`, model version, and analysis
pipeline version. The config must contain every behavior-changing option and
version; `config_digest` uses canonical JSON and SHA-256. Changing any key
part yields a miss. A pipeline can call `get` before queueing work, and call
`put(key, analysis_id, ttl_seconds=...)` only after `JobStore.complete` returns
success. `put` also checks in PostgreSQL that the analysis belongs to a
completed job with this owner, repository, and SHA, and that the stored result
is successful, has `partial=false` (or no v1 partial field), and has no errors.
Thus failed, cancelled, running, and partial reports cannot become hits,
including when those terminal reports are stored for display. Results remain
in the existing `analyses` table;
the cache stores only a scoped reference and expiration time.

Concurrent writes for one key resolve through a PostgreSQL primary key and
atomic upsert. The last committed writer wins if multiple successful analyses
share a key. Reads exclude expired rows immediately; `prune_expired()` removes
them physically. `invalidate(user_id, repository_id, branch=...)` removes
entries for an owned repository, optionally one branch. A write after
invalidation can create a new entry, so a permission revocation must also be
enforced by the live access callback. Deleting an analysis or repository
cascades to its cache entries.

Run the real PostgreSQL checks against a **disposable** database whose role
can create and drop schemas:

```powershell
$env:ARIADNE_TEST_DATABASE_URL = 'postgresql://user@127.0.0.1:port/disposable_db'
uv run pytest tests/cache -q
```

Without this variable the tests skip and establish no PostgreSQL behavior.
The tests use a fresh schema per case and drop it afterward. This module is
not yet wired into an API or worker pipeline; that caller must provide the
permission callback and include the full analysis configuration in the key.
