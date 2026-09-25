# Changes

This page records product changes that are available in the public repository. Entries link to their source or verification records.

## T03 — Public GitHub repository reader

[Reader details](backend/app/services/github_public/README.md) · [Tests](backend/tests/github_public/test_service.py)

- Added a reader for canonical public GitHub repository URLs. It resolves a commit and complete tree, filters bounded source and document files, and reads selected content by pinned Git blob SHA.
- Added path, response-size, and file-count limits; disabled API redirects; and verified returned blob size and digest. Example environment-file values are removed from document output. Repository code is treated as data and is not executed.
- Verification: 40 targeted reader tests passed. A live public GitHub blob was also checked against its declared Git SHA. The reader currently has no user-facing API route, persistence, or private-repository access.

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
