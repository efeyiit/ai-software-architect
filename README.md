# Ariadne

Ariadne is a developer tool for exploring a GitHub repository through its architecture, dependencies, code quality, tests, security findings, and source-linked explanations. Its name comes from Ariadne's thread through the labyrinth: each finding should lead back to the code and evidence that explains it.

**Status: development, not ready for end-to-end use.** Repository readers, five language parsers, analysis modules, source-cited retrieval, PostgreSQL persistence, a job queue, authenticated API routes, and React screens are implemented. Real GitHub login through persisted analysis and source-cited chat has not passed end-to-end acceptance. See the [current verification record](docs/evidence/2026-09-25-baseline.md) for tested behavior and remaining setup requirements.

## Run the current foundation

From `backend/`:

```sh
uv sync
uv run uvicorn app.main:app --reload
uv run pytest -q
```

From `frontend/`:

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm test
pnpm build
```

The API exposes `/health` for process liveness. Authentication and repository routes return 503 until their database and OAuth configuration are available; `/health` alone does not establish product readiness. The frontend includes repository, file, architecture, dependency, and finding screens with explicit unavailable states. The [local application launcher](deployment/local-app/README.md) documents the HTTPS, PostgreSQL, OAuth, Qdrant, and model prerequisites. Current local setup is blocked by missing configuration and filesystem permission checks.

## Product direction

The [product roadmap](docs/product-roadmap.md) summarizes the planned capabilities. The [source design](docs/source-design.md) gives the full intended scope, and [architecture decisions](docs/architecture-decisions.md) describe the implemented foundation.

The design calls for source evidence to remain distinct from AI interpretation and for analyzed repository code not to run by default. These are product requirements; future capabilities need their own implementation and verification.
