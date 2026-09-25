# T13 — SOLID and refactoring review

`analyze_refactoring(structures, quality_findings, architecture)` accepts real
T05–T09 parser results, T11 `AnalysisFinding` records, and a T12
`ArchitectureReport`. It returns a `RefactoringReport` with separate `evidence`,
`recommendations`, and `architecture_context` lists. It neither executes
analyzed repository code nor changes that code.

The current rule identifies classes whose parsed method names suggest at least
two distinct concerns: payments, notifications, documents, or persistence. It
returns a **candidate** SRP review with source location, cited parser evidence,
and concrete extraction options. A T11 `large_class` finding can support the
candidate and is cited separately. T12 supported or mixed hypotheses appear
only as context; architecture labels do not prove a SOLID violation.

Method names alone do not establish separate reasons to change. Ambiguous
names are ignored for grouping. The analyzer does not assert definite SRP,
open/closed, substitution, interface segregation, or dependency inversion
violations. The suggested extraction requires a human to inspect behavior and
dependencies, then add behavior tests before editing the target code.

No LLM provider is configured. `ai_status="unavailable"` and
`origin="deterministic"` make clear that these suggestions are rule based,
not AI generated. No source or evidence is sent to an external provider. A
future provider integration would need an explicit data sharing boundary and
separate validation; this module has no provider adapter today.

Paths in all inputs must belong to one file set, and T11 findings must have
`source=static`. Current upstream types do not carry repository identity or
commit SHA, so the caller must bind all parser, quality, and architecture
results to the same authorized snapshot. File path checks alone cannot prove
that identity. A syntax-error file is skipped for class suggestions.

This is a module result. It is **not connected to the API or UI**; T25 and
later integration work must map it to the product result contract. No public
report should describe these candidates as verified SOLID violations.

Focused verification from `backend/`:

```text
uv run --no-sync pytest -q tests/refactoring
```

Fixtures exercise the real T11 and T12 outputs and real parsers for Python,
TypeScript, Java, C#, and C++, including missing evidence, irrelevant comments,
cross-snapshot paths, and syntax errors.
