# Dependency analyzer (T10)

`analyze_dependencies(structures)` accepts the `FileStructure` objects returned by
the Python, TypeScript, Java, C#, and C++ parsers. It reads parsed syntax only; it
never opens or executes repository code. Paths must be normalized relative POSIX
paths and every parser item's source location must belong to its file. Duplicate
paths and foreign locations are rejected.

The returned `DependencyGraph` contains file and symbol nodes, import/call/
inheritance edges, file-level cycles, and critical file nodes. Every edge keeps
the parser's source location, original expression, and one of these statuses:

- `resolved`: exactly one supported target is evidenced; `target` is its node ID.
- `external`: an import names a module or type absent from the supplied snapshot.
- `ambiguous`: the target is missing locally, dynamic, has multiple candidates,
  is not publicly exported, or escapes the repository root. `target` is null;
  `candidates` and `reason` explain what is known.

TypeScript relative imports and reexports follow in-snapshot file paths and
explicit exports. Python relative imports follow package depth and resolve
against in-snapshot module paths. Java package names, C# namespaces, and C++
literal include paths are matched conservatively. Bare same-named symbols in
unrelated files are never linked. Parser metadata does not distinguish a
TypeScript default import from a namespace import, so that binding stays
unresolved; it also does not preserve C++ angle versus quote include style.
Dynamic dispatch, macros, overloads, and build-system include/search paths
need richer evidence before they can become resolved edges.

Cycles are strongly connected components of **resolved cross-file** edges;
same-file calls do not create a file cycle. A critical node is a file connected
to at least two distinct other files by resolved edges. This is a simple
connectivity signal, not a severity finding or execution order.

Run the focused real-parser fixtures with:

```text
cd backend
uv run --no-sync pytest -q tests/dependencies tests/parsers
```

The graph is a T10 module result. The shared `AnalysisResult` contract has no
dependency-graph field yet; the API/persistence integration owner must map it
through the later unified analysis contract without treating ambiguity as fact.
