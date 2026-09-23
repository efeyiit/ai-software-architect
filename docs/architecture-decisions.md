# T01 architecture decisions

## Boundary

FastAPI is the API entry point and React/TypeScript is the client shell.
T01 defines a strict version 1 analysis payload before adding GitHub, parser,
RAG, database, or LLM integrations. The source design lists those services;
their ownership belongs to later task cards. `/health` proves the API boots.
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
files as instructions, and no user code is executed by this task.

`frontend/index.html` and `frontend/src/main.tsx` are the two minimum files
outside T01's listed ownership needed to make the requested React startup
buildable. `backend/uv.lock`, `frontend/pnpm-lock.yaml`, and this task's
`docs/evidence/T01.md` are similarly required deliverables. These files do
not overlap another worker's named files.
