# PostgreSQL data boundary (T02)

The database schema is in `schema.sql`. Call `apply_schema(connection)` once
against a new PostgreSQL database or an isolated schema before serving data.
The function creates the initial tables and indexes transactionally. It is
idempotent for this initial version, but is not a migration system for later
changes. Future schema changes need numbered migrations.

`Store` requires the already authenticated user's ID on every repository,
snapshot, and analysis operation. Missing or foreign resources return `None`.
The caller must not accept a user ID from untrusted request data as proof of
identity. Authentication, GitHub permission checks, token handling, and API
routing belong to later tasks.

Repository URLs are unique **per user**. A snapshot belongs to one repository
and one 40-character lowercase commit SHA. Analysis JSON is stored only after
both the owner and exact SHA match. Composite foreign keys prevent analyses,
files, dependencies, and code issues from referencing a different repository's
snapshot; code issues also require a file from that snapshot. The application
database role should be limited to this data access layer; direct SQL access by
a privileged role can bypass application-level ownership checks.

To run the PostgreSQL integration tests, set
`ARIADNE_TEST_DATABASE_URL` to a **disposable** PostgreSQL database whose
role can create and drop schemas, then run:

```powershell
uv run pytest tests/database tests/contracts -q
```

Each integration test creates and drops its own schema. Without the variable,
the database tests skip and do not prove PostgreSQL behavior. The test DSN
must never point to a production or user-data database.
