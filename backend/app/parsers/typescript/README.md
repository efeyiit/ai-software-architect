# TypeScript and TSX structure parser

`parse_file(path, source)` parses decoded TypeScript text with Tree-sitter's
TypeScript or TSX grammar, selected from the repository-relative file extension.
It accepts `.ts`, `.tsx`, `.mts`, and `.cts` paths. The analyzed source is data:
the parser does not import, compile, or run it.

`FileStructure` follows the Python parser's `symbols`, `imports`, `calls`,
`inheritance`, and `errors` fields and adds `exports`. Each item has the shared
`SourceLocation` with a normalized relative POSIX path and inclusive one-based
line numbers. Symbols include named classes, functions, methods, and simple
variable declarations. Imports retain the module specifier; named imports
append the imported name and record the local binding as `alias`. Export names
record declarations, named exports and re-exports, default exports, and star
exports. `alias="default"` marks a default export; `source` retains a re-export's
module specifier. Calls and base-class names
remain syntax expressions rather than resolved references.

An invalid syntax tree returns empty lists and one non-retryable
`TYPESCRIPT_SYNTAX_ERROR` with a file location. The parser can continue with
other files. It does not resolve types, module targets, inheritance targets, or
runtime call targets. Anonymous expressions and destructured bindings are not
recorded as named symbols.

Run the targeted check from `backend/` with
`uv run pytest -q tests/parsers/typescript/test_typescript_parser.py`.
