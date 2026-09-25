# T24 — Repository analysis coordination

`Coordinator.run(caller_id, SnapshotMaterial, should_stop)` connects the real
T10–T16/T19 modules. Its five bounded roles are architect, security, testing,
refactoring, and documentation. The architect role uses the real dependency
graph and architecture detector. Security uses the static security analyzer.
Testing uses parser test discovery and, when supplied, existing coverage XML.
Refactoring combines static quality, architecture context and the deterministic
T13 advisor. Documentation uses T19's inert draft generator. T21 chat remains
a separate interactive service; it is not misrepresented as a sixth batch agent.

The caller supplies an authorized `RepositorySnapshot` from T03/T04 and text
retrieved at that snapshot's immutable blob SHAs. `current_snapshot(caller_id,
repository_id)` must check live ownership and return the currently authorized
snapshot on **every call**. The coordinator checks repository ID, commit SHA,
tree SHA and file manifest before, during and after analysis. It also verifies
every supplied UTF-8 source/document/coverage blob against the manifest using
the Git blob SHA. A changed permission, commit or manifest raises `ScopeChanged`
and no report is returned. This callback and text loader are the T25 trust
boundary; passing a fabricated callback grants no authorization. Public
`fetch_document_file` redacts example env values, so such redacted text cannot
pass this blob check; T25 should omit those files until a verified, sanitized
document handoff exists.

The report keeps the full T10 dependency graph (including ambiguous/external
edges, cycles and critical nodes) and typed architecture, testing, refactoring and documentation
results alongside a deterministic source-linked merge. Static findings retain
`source=static`; rule-based candidate suggestions retain their tentative status;
`ai_status=unavailable` is explicit. Exact duplicates collapse to one item ID.
Different static findings at the same path/line/type and architecture support
plus contradiction remain separate and are listed as conflicts. Repository text
is data: it is parsed and scanned, never imported, executed, used as coordinator
instructions or sent to a provider. No production LLM adapter exists here.

Limits: 2,000 files, 20 MB verified input, one coverage artifact, at most five
concurrent roles, and a configurable role deadline (30 seconds by default).
Failures and timeouts produce `partial` or `failed` with per-role status; cancel
produces `cancelled`. Running Python threads cannot be forcibly killed on
timeout, so callers should isolate worker processes for a hard CPU deadline.
No timeout result is promoted to a successful report.

`make_job_handler(coordinator, load_material)` adapts the real T22
`Worker(handler: Callable[[JobContext], AnalysisResult])` contract. The loader
receives `(user_id, repository_id, commit_sha)` from the claimed job.
`to_analysis_result` maps complete, partial, failed and cancelled reports to shared v2 without
flattening away roles, graph, typed reports, merge items or conflicts. Static
findings retain stable merged IDs. Invalid and changed-scope runs raise safe
`JobFailure` codes. T22 persists a cancelled report only under a live claim
with an explicit cancellation request; it never marks that job completed.

T25 owns the shared v2 contract. It must expose the complete dependency graph,
architecture hypotheses and contradictions, test discovery versus coverage,
refactoring candidates, documentation drafts, role status, merge items,
conflict groups and `partial` status. T24 does not change that shared schema.

Focused verification from `backend/`:

```text
uv run --no-sync pytest -q tests/orchestration
```

The fixture invokes the real Python parser and downstream modules, verifies
blob/SHA and authorization rejection, source-linked merge, conflict retention,
coverage, timeout, cancellation, and the T22 adapter.
