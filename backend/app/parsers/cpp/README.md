# C++ structure parser

`parse_file(path, source)` parses decoded C++ source and header text with the
native [`tree-sitter-cpp` 0.23.4 grammar](https://github.com/tree-sitter/tree-sitter-cpp).
Accepted repository-relative paths end in `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`,
`.hxx`, or `.h`. The source is parsed as data; it is never compiled or run.

`FileStructure` has `symbols`, `imports`, `calls`, `inheritance`, `errors`, and
`macro_uncertainties`. Symbols cover namespaces, classes, structs, free
functions, and methods. Qualified names and call scopes use `::`. Imports hold
literal `#include` targets without delimiters, or the raw expression for a
computed include. Inheritance entries retain the declared base type text. All
entries use shared `SourceLocation` values with normalized relative paths and
inclusive one-based line numbers.

Macro definitions, known macro invocations, computed includes, and conditional
compilation blocks receive `macro_uncertainties` entries. Conditional branches
are excluded from definite symbols and calls. A known macro invocation is
excluded from ordinary calls even if the grammar needs to recover an omitted
semicolon that expansion would supply. Unknown macros, external definitions,
and preprocessor expansion cannot be resolved from a single file, so extracted
symbols and call targets remain syntax observations rather than compiler facts.
Out-of-class methods are recognized when their class is declared earlier in
the same file; otherwise they may appear as functions. This parser does not
resolve includes, templates, overloads, aliases, or virtual dispatch.

Invalid syntax returns empty structure lists and one non-retryable
`CPP_SYNTAX_ERROR` at a source location. Another file can still be parsed.

Run the targeted check from `backend/` with
`uv run pytest -q tests/parsers/cpp/test_cpp_parser.py`.
