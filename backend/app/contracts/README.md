# Analysis wire contract v1 and v2

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

V2 retains the same identity, findings and errors while adding `partial`,
`ai_status`, five role states, source-linked merge items/conflicts, and typed
architecture, testing, refactoring, documentation and dependency reports.
`status=partial` requires `partial=true`, at least one successful and one failed
or timed-out role, and structured errors. A succeeded v2 report requires all
five roles to succeed and no errors. `ai_status=unavailable` is explicit: the
deterministic role results are not represented as model output. Optional typed
sections are `null` when their role did not return a result. Dependency edges
preserve `resolved`, `external` and `ambiguous` status from T10.

Stored v1 JSON is accepted and serialized back without injected v2 fields.
Unknown fields and invalid status/partial combinations remain rejected on
both sides. The queue stores partial/failed/cancelled terminal records, while
the completed-result cache accepts only succeeded records.
