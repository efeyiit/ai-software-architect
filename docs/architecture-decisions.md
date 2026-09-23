# T01 architecture decisions

## Boundary

FastAPI is the API entry point and React/TypeScript is the client shell.
The current API defines a strict analysis payload before GitHub, parser,
RAG, database, or LLM integrations. The source design covers those later
capabilities. `/health` proves the API boots.
The frontend page proves the React bundle boots without committing to a UI
design.

## Identity and evidence

The repository ID and full commit SHA identify the analyzed snapshot. A
finding carries a repository-relative file path and one-based inclusive line
range. Static findings and AI interpretations use separate `source` values.
Structured errors preserve code, message, retryability, and optional source
location. Pending/running/succeeded/failed status is explicit. Strict runtime
validation on both sides rejects unknown fields and malformed locations.

## Reproducibility and trust

Python dependencies are pinned in `backend/pyproject.toml` and `backend/uv.lock`;
frontend dependencies are pinned in `frontend/package.json` and
`frontend/pnpm-lock.yaml`. Both contract test suites read the same JSON fixture.
Repository content remains data: neither startup shell interprets repository
files as instructions, and the current foundation does not execute analyzed code.
