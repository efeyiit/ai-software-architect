# Static quality analyzer

`analyze_static_quality(structures, sources, graph=None, thresholds=QualityThresholds())`
accepts the five parser `FileStructure` results and their exact source text by
repository-relative path. It returns shared `AnalysisFinding` records with
`source=static`, stable source locations, and configurable thresholds. It parses
source as inert syntax; it never imports or executes analyzed repository code.

Checks: long functions, large classes, whole-function duplicate bodies, magic
numbers, deep control nesting, too many parameters, resolved dependency cycles,
and unused Python imports. A cycle needs a `DependencyGraph` from the same file
snapshot. Syntax-error files are skipped. No finding is created by words inside
comments or strings. Defaults are 80 function lines, 500 class lines or 20
methods, depth 4, 6 parameters, and 24 syntax tokens for duplicates. `-1`, `0`,
`1`, and `2` are permitted numeric literals by default.

Python uses the standard AST. TypeScript/TSX, Java, C#, and C++ use their native
Tree-sitter grammars together with symbols from the existing parsers. Import-use
analysis is intentionally Python-only: Java/C# wildcard imports, TypeScript
reexports and type-only references, and C++ preprocessing/build paths need more
evidence before a definite unused-import claim. Python star imports and dynamic
namespace access also suppress that check. These are static indicators rather
than proof of a defect; duplicate detection requires matching syntax bodies and
does not infer semantic equivalence.

Focused test command, for a trusted development environment:

```text
cd backend
uv run --no-sync pytest -q tests/static_quality
```

The tests contain positive and negative fixtures from all five real parsers and
the resolved dependency graph. The analyzer is a module result; a later API
integration task must attach the returned findings to `AnalysisResult` for the
same repository snapshot.
