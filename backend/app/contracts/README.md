# Analysis wire contract v1

`AnalysisResult` is the JSON boundary between FastAPI and React. The backend
validates it with Pydantic; the frontend validates untrusted API JSON with Zod.
Both sides reject unknown fields. The canonical test payload is
`backend/tests/contracts/analysis.json`, read by both test suites.

An analysis identifies its repository with `snapshot.repository_id` and the
exact 40-character lowercase Git commit SHA in `snapshot.commit_sha`.
`status` is `pending`, `running`, `succeeded`, or `failed`. A failed result
requires an `errors` item; a succeeded result has none. Each error has a
machine-readable `code`, user-readable `message`, `retryable` boolean, and
nullable `location`.

Each finding has an ID unique within its analysis, `source` (`static` or
`ai`), `issue_type`, `severity`, `description`, nullable `suggestion`, and
`location`. The location is a normalized, repository-relative POSIX path and
inclusive one-based `start_line`/`end_line`. Absolute paths, backslashes,
empty or traversal segments, zero lines, and reversed ranges are invalid.

`source=ai` marks interpretation, not a verified static fact. Repository text
in descriptions or future prompt context is untrusted data. This contract
does not execute repository content or call any model. A later task owns
retrieval and analysis endpoints; T01 only boots `/health`.

The versioned schema is intentionally small. Changes to field names, enum
values, nullability, or validation need synchronized Python and TypeScript
updates plus the shared fixture tests.
