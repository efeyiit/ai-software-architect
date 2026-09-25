# Test discovery and coverage separation (T14)

`analyze_testing(structures, graph=None, coverage_artifacts=None)` accepts the
five existing parser `FileStructure` outputs and optionally a T10 dependency
graph for the same file snapshot. It reads parser data only. It never imports,
builds, or runs analyzed repository code or its tests. The caller must bind
structures, graph, and artifacts to one repository ID and commit SHA; those IDs
are not present in the current parser or graph contracts. A mismatched graph
file set is rejected.

Test files are discovered through test directories or filenames. A test
declaration must also be visible in the parser output before an association is
made: `test_` functions for Python; `test()` or `it()` calls for TypeScript;
`test*` methods for Java/C#; and GoogleTest, Catch2, or doctest macro symbols
with corresponding framework imports for C++. Framework imports are reported
but alone do not prove a test exists. Java/C# annotation-only tests with names
that do not start with `test` remain unknown because the current parser
contracts do not expose annotations. Dynamic references and unresolved graph
edges also remain unknown.

Service candidates are parsed classes, structs, or interfaces ending in
`Service` outside test files. A service is `associated_with_test` only when a
test file containing a detected declaration has a resolved import or call edge
to that service's file. This association does not prove that the test runs or
asserts the service's behavior. Otherwise it is `potentially_untested`, never
definitively untested. Counts of files, declarations, or service associations
are **not coverage percentages**.

`coverage_artifacts` is a mapping of repository-relative `coverage.xml` or
`jacoco.xml` paths to bytes or text already obtained from the same snapshot.
The analyzer does no filesystem access. It accepts bounded Cobertura/coverage.py
root line counters and JaCoCo root `LINE` counters. DTD, entities, NUL/UTF-16,
oversized, malformed, ambiguous, and inconsistent inputs are rejected. The
report has `coverage_status=missing` and `coverage=None` when absent, or
`invalid` with errors when parsing fails; it never fills in zero. A valid
artefact is separate `CoverageEvidence` with source path, line counts, format,
and computed percentage. The XML value is repository-supplied evidence, not
independent proof that tests were executed at the analyzed commit.

Focused verification from `backend/`:

```text
uv run --no-sync pytest -q tests/testing
```

The current shared `AnalysisResult` has no test discovery or coverage fields.
This module has not yet been connected to the API or UI; T25 and T29 own that
integration.
