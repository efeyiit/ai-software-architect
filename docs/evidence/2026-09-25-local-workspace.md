# Account-free local workspace acceptance — 2026-09-25

## Delivered behavior

The loopback application accepts a public GitHub URL or browser-selected local source files without OAuth. Immutable sources, reports, and jobs use SQLite. Optional local retrieval uses embedded Qdrant with repository and snapshot filters. Existing authenticated server routes remain separate.

## Automated verification

- Backend: `pytest -q` — **327 passed, 37 skipped**. Skips require the alternate PostgreSQL integration environment.
- Frontend: `pnpm test --run` — **70 passed**, 17 files.
- Frontend: `pnpm build` — passed. The existing large diagram bundle warning remains.
- Model worker: `python -m unittest test_local_runtime -q` — **5 passed**.
- After the final empty-answer wording change, local backend subset: **41 passed**.

Checks cover immutable identity, restart persistence, cross-repository lookup rejection, input/path/size restrictions, session/origin/CSRF checks, interrupted jobs, single-instance locking, real analysis conversion, cancellation queue bounds, retries, persisted retrieval scope, exact citation validation, inert source rendering, and merged security finding identity.

## Observed browser and live-runtime checks

- Imported `pypa/sampleproject` without credentials at commit `621e4974ca25ce531773def586ba3ed8e736b3fc`. Its real report has five succeeded roles, 2 findings, 12 source nodes, and 22 relationships.
- Selected the application's local Python source directory through the browser folder chooser. Real analysis completed with five succeeded roles; saved report and source lines reopened after application restart.
- The first local import exposed a false-positive private-key filter on the detector's own code. A full PEM-header match and regression test now fix that behavior. The old snapshot is deliberately unchanged.
- Fixed report polling that previously cancelled its own completed-report fetch. The final report is now visible in the local workspace.
- Reopened the saved public report after restart. Followed a dependency link into `src/sample/__init__.py:3`; the source view displays the real code and retains the analyzed commit in its URL.
- A 390 × 844 viewport showed saved source lines without page-width overflow (375px document width within 390px viewport). Browser error log was empty during that check.

## Optional AI: explicit remaining limitation

The installed local Qwen2.5-Coder-1.5B and multilingual-E5 worker reached ready state. Real public-repository questions about `main` and `add_one` returned `no_evidence`; a Turkish question naming the source file returned `rejected`. No successful real-model answer is claimed. The interface does not substitute a fabricated answer. Citation acceptance/rejection and persistent retrieval isolation passed controlled tests, but useful real-model answer quality remains unfinished.

The model protocol now accepts explicit local content identities without inventing Git commits; public evidence retains its actual 40-character commit. Model setup is optional and is not required for source analysis.

## Scope limits

Single-user loopback use only. GitHub unauthenticated rate limits apply. Static analysis never executes imported code or project tests. Common secret/generated files are excluded; this is not a complete secret-discovery guarantee. Older source links remain immutable across imports. The broader roadmap and hosted OAuth flow are not fully accepted by these local checks.
