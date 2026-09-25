# Repository analysis API (T25)

The FastAPI application mounts GitHub login and the repository routes together.
Every `/api` route takes its owner from T04's server-side, HttpOnly session.
Client-supplied user headers and body fields have no authority. `GET /auth/me`
returns a CSRF token; send it as `X-Ariadne-CSRF` on POST requests. Missing
identity configuration or database schema returns 503; missing/expired session
returns 401. The browser must use HTTPS for the `__Host-` session cookie.

The available routes are:

| Route | Behavior |
| --- | --- |
| `GET /api/repositories` | Return up to 100 owned repositories with current live-access SHA; inaccessible repositories are omitted. |
| `POST /api/repositories` | Validate a GitHub URL and create an owned repository/snapshot. |
| `GET /api/repositories/{id}` | Recheck current GitHub access and return current metadata/SHA. |
| `GET /api/repositories/{id}/files` | Return current-SHA file manifest metadata without source contents. |
| `GET /api/repositories/{id}/files/summary?path=...` | Verify the selected blob and return T17 static, cited file facts with `ai_status=unavailable`. Unknown or excluded paths are rejected. |
| `POST /api/repositories/{id}/analyze` | Recheck access/SHA, check the successful-result cache, enqueue and return promptly. `Idempotency-Key` is optional. |
| `GET /api/repositories/{id}/jobs/{job_id}` | Return owner-scoped queued/running/completed/partial/failed/cancelled state and result ID. |
| `POST /api/repositories/{id}/jobs/{job_id}/cancel` | Request cooperative cancellation. |
| `GET /api/repositories/{id}/analyses/{analysis_id}` | Return the shared `AnalysisResult` JSON after current access/SHA recheck. |
| `GET /api/repositories/{id}/issues` | Project findings from the newest current-SHA result, retaining its actual status. |
| `GET /api/repositories/{id}/dependencies` | Project the typed T10 graph from the newest current-SHA result. |
| `GET /api/repositories/{id}/diagrams` | Render T18 Mermaid and PlantUML class, inferred sequence and component diagrams from the persisted graph and freshly verified parser structures. |
| `POST /api/repositories/{id}/chat` | Use T21 source-cited chat when a vetted local embedding and answer provider are configured; otherwise return `unavailable`. |

`POST /analyze` uses T22's durable PostgreSQL queue. Run a separate worker
process with `python -m app.api.worker`. The worker re-fetches exact Git blob
content, validates its immutable manifest, checks ownership and current GitHub
permission before/during/after T24 coordination, and stores the shared v2
result. It never runs repository code. A changed branch, SHA, tree or permission
causes a safe failure. A partial report remains a terminal `partial` job with
its role errors, typed outputs, conflicts and dependency graph; it is not a
completed success or a T23 cache hit. Final failed/cancelled job results are
also preserved by T22 when available. V1 stored JSON remains readable.

The deployment must set `ARIADNE_DATABASE_URL` and the T04 OAuth configuration
documented in `app/security/identity/README.md`, and provision core, identity,
jobs and cache schemas before starting HTTP or worker processes. A registered
GitHub OAuth app and HTTPS callback are required for real login. To enable
source-cited local chat, give both HTTP and worker processes the same
`ARIADNE_QDRANT_URL=http://127.0.0.1:6333` and
`ARIADNE_QDRANT_API_KEY` (read from the ignored, owner-restricted Qdrant key file),
and `ARIADNE_LOCAL_RUNTIME_TOKEN` for the separately running local model worker at
`127.0.0.1:8766`. Qdrant must be a persistent server accessible to both
processes. Each completed analysis indexes its verified current-SHA sources
after the durable report is saved. If the index is missing on a cached
analysis, another analysis request queues a worker rebuild; chat reports
`unavailable` until indexed. Index failure does not change a saved analysis
into a false success claim for chat. No in-memory fallback is used in production.

The API checks current permission on every read, including cache hits. The
default branch's current SHA must match any returned analysis. Repository
source is never imported, executed, or treated as instructions. Public
`.env.example` documents are deliberately omitted from T24's blob-verified
document handoff because the public reader redacts their contents. Private
documents are currently omitted from that handoff.

The file summary route parses only the selected supported source file after
checking its Git blob SHA. It returns T17 `FileSummary` fields, repository and
commit identity, and explicit AI unavailability. It does not expose source
contents or claim a business responsibility from syntax alone.

The diagram route returns `{snapshot, status, diagrams}`. `diagrams` contains
`mermaid` and `plantuml`, each with `class_diagram`, `sequence_diagram`, and
`component_diagram` source strings. It uses the newest current-SHA analysis
graph and re-fetches verified source blobs to preserve class evidence. These
are static, inferred diagrams, not runtime traces. T18's 500-node/2,000-edge
render limit returns a classified error; the endpoint does not invoke a remote
renderer.

Focused tests use a disposable PostgreSQL database in
`ARIADNE_TEST_DATABASE_URL` and a local Qdrant fixture:

```text
uv run --no-sync pytest -q tests/api tests/contracts tests/orchestration
```

An unset test database skips the PostgreSQL HTTP tests and does not establish
database behavior. The local Qdrant embedding and answer fixture is not a
production AI model. The production API cannot answer chat questions until a
reviewed local provider and indexing lifecycle are configured.
