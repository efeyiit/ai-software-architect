# Repository security analyzer (T16)

`analyze_security(structures, sources)` accepts the five existing parser
`FileStructure` results and source text keyed by normalized repository-relative
path. It returns shared `AnalysisFinding` values (`source=static`) with stable
`SourceLocation` line numbers. The caller must supply one consistent repository
snapshot; this function checks the path set and skips parser-error files, but it
does not independently prove that the supplied text matches a parser result or
commit SHA. It parses text as inert syntax and never imports or executes the
analyzed repository.

Every description is explicitly a **potential** risk. The analyzer emits no
source snippets, literal values, environment variable names, or parser exception
text. IDs hash only rule, path and line. Review access to file paths separately
under the repository permission boundary. Secret literals are never used as
finding text or IDs.

| Signal | Python | TypeScript/TSX | Java | C# | C++ |
| --- | --- | --- | --- | --- | --- |
| Hardcoded API key/password | Direct literal assignment | Direct literal assignment | Direct literal assignment | Direct literal assignment | Direct literal assignment |
| Dynamic SQL | f-string, variable concat/format | Template interpolation, variable concat | Variable concat | Interpolation, variable concat | Variable concat |
| JWT validation | Explicit `verify_signature=False` | `jwt.decode` or explicit disabled validation | Explicit disabled validation flag only | Explicit disabled validation flag only | Explicit disabled validation flag only |
| Missing auth | Explicit public sensitive route | Explicit public sensitive decorator | `@PermitAll` sensitive route | `[AllowAnonymous]` sensitive route | No general framework route rule |
| Sensitive log | Direct sensitive argument | Direct sensitive argument | Direct sensitive argument | Direct sensitive argument | Direct sensitive argument |
| Environment secret | Direct return/log exposure | Direct return/log exposure | Direct return/log exposure | Direct return/log exposure | Direct return/log exposure |

Rules are deliberately local. SQL placeholders/bound arguments and concatenation
of literal-only SQL pieces are quiet. Comments and quoted examples cannot act as
code. Reading an environment secret without direct log/return exposure is quiet.
An ordinary route without an explicit public marker is quiet because framework
middleware may authorize it. Recognized `add_middleware(AuthenticationMiddleware)`
registration anywhere in the supplied snapshot suppresses the route signal. Data flow through helper
functions, aliases, macros, ORM internals, full JWT claim semantics, and C++
route frameworks are outside these local checks; absence of a finding does not
mean code is secure. C++ parser macro uncertainty has the same limitation as its
source parser. Findings are review leads, never confirmed vulnerabilities.

Focused verification using only synthetic repository fixtures:

```text
cd backend
uv run --no-sync pytest -q tests/security
```

The fixtures exercise all five real parsers, six signal categories, serialized
redaction, malformed files, parameterized SQL, literal-only concatenation,
comments/strings, verified JWT, and middleware uncertainty. This module is not
yet connected to an analysis API or security screen; the later API/report and UI
tasks must attach findings to the authorized repository snapshot.
