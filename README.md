# Ariadne

Ariadne is a developer tool for exploring a GitHub repository through its architecture, dependencies, code quality, tests, security findings, and source-linked explanations. Its name comes from Ariadne's thread through the labyrinth: each finding should lead back to the code and evidence that explains it.

**Status: early implementation.** The FastAPI and React shells, a shared analysis-result contract, and targeted contract tests are in place. Repository ingestion, automated analysis, AI features, and a complete product demo are still planned.

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

The API currently exposes `/health`; the frontend displays a minimal application shell. An owner-scoped PostgreSQL store is also available as a building block. See the [change log](CHANGELOG.md) for what each delivered step added, how it was checked, and what remains open.

## Product direction

The [product roadmap](docs/product-roadmap.md) summarizes the planned capabilities. The [source design](docs/source-design.md) gives the full intended scope, and [architecture decisions](docs/architecture-decisions.md) describe the implemented foundation.

The design calls for source evidence to remain distinct from AI interpretation and for analyzed repository code not to run by default. These are product requirements; future capabilities need their own implementation and verification.
