# T19 — README and API documentation drafts

`generate_documentation(snapshot, source_texts)` returns a structured
`DocumentationResult` containing README and API Markdown drafts, route records,
source locations, the repository ID and commit SHA, and explicit uncertainties.
It has no LLM provider and reports `ai_status="unavailable"`; these are
deterministic source-derived drafts, not AI prose.

The caller must authorize the repository and obtain each supplied text from the
declared commit with blob-SHA verification. Public ingestion now exposes
`document_files(snapshot)` and `fetch_document_file(snapshot, file)` for
explicitly allowlisted manifests, OpenAPI JSON, Dockerfiles and env templates.
It redacts env values before returning text. The caller can pass those retrieved
texts into this generator; a synthetic end-to-end fixture tests that path.
This module checks that paths occur in the snapshot, but cannot independently
prove that arbitrary caller-supplied text matches a blob SHA. It does not run analyzed code,
install dependencies, invoke package scripts, build Docker images, or send code
to an external provider. There is no API or UI integration in this module.

The public retrieval boundary allows at most 64 document files, 2 MB in total,
and 512 KB per file. It excludes actual `.env` files and sensitive paths. Private
repository authorization and API/UI wiring remain the responsibility of higher
layers; passing a fabricated snapshot or text mapping directly to this function
does not grant those guarantees.

The README contains the source-design headings: description, requirements,
installation, environment variables, local run, Docker, API, structure, and
testing. `pyproject.toml` can establish a Python version; `package.json` can
establish script names; `.env.example`, `.env.sample`, and `.env.template` can establish variable
names; a Dockerfile establishes only its presence. Commands and behavior that
cannot be proved remain `Unknown` or `Draft`, and a declared script is never
treated as safe to execute. OpenAPI JSON supplies routes and simple request and
success-response property names/types. Literal Python route decorators supply
method and path only; their request and response shape remain unknown. Dynamic
routes, malformed files, references and complex schemas remain outside this
small extractor's evidence. Every route cites a file and line; cited syntax
does not establish runtime behavior, access rules, or deployed configuration.

Source values, OpenAPI descriptions, examples, auth headers, response examples,
and source snippets are not copied to any output field. Sensitive request and
response property names are omitted. Environment variable names are listed but
their values are omitted, including placeholders. Generated text remains a
reviewable draft; do not publish it without inspecting permissions and source
provenance.

Focused verification, using synthetic repository fixtures only:

```text
cd backend
uv run --no-sync pytest -q tests/documentation
```
