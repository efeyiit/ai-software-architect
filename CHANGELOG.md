# Changes

This page records product changes that are available in the public repository. Each entry links to its commit and verification record.

## T02 — PostgreSQL storage boundary

Commit: [`a2444ef`](https://github.com/efeyiit/ariadne/commit/a2444efbabb901e45c2b045d61532e6641ca584d) · [Verification](docs/evidence/T02.md)

- Added tables for users, repositories, commit-pinned snapshots, analyses, files, dependencies, and code issues. Relational constraints prevent child records from pointing across repository or snapshot boundaries.
- Added owner-scoped repository, snapshot, and analysis operations. Analysis writes require the exact repository and commit SHA. Added PostgreSQL integration tests and pinned `psycopg`.
- Verification recorded on a disposable PostgreSQL 16.15 database: 16 tests passed with none skipped. A later security review ran without a database: 14 passed and 6 database tests skipped. The latter run does not replace the PostgreSQL result.
- Still needed: authentication, GitHub permission checks, API routes, and schema migrations. Callers must supply a trusted user ID; privileged direct SQL can bypass the application's owner checks.

## T01 — Application and analysis contract foundation

Commit: [`109e21f`](https://github.com/efeyiit/ariadne/commit/109e21f) · [Verification](docs/evidence/T01.md)

- Added the FastAPI `/health` endpoint, a minimal React application, and a shared Python/TypeScript analysis-result contract with source locations and structured errors.
- Verification recorded 12 passing backend tests, 12 passing frontend tests, and a successful frontend build.
- Repository fetching, automated analysis, AI calls, and persisted results were not part of this foundation.
