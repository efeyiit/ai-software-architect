# Java structure parser

`parse_file(path, source)` parses decoded `.java` source text with the
[`tree-sitter-java` 0.23.5 grammar](https://github.com/tree-sitter/tree-sitter-java)
and Tree-sitter's Python binding. It validates a repository-relative POSIX
path, then parses the supplied text without compiling, importing, or running
the analyzed Java code. The pinned grammar version is also published on
[PyPI](https://pypi.org/project/tree-sitter-java/0.23.5/).

`FileStructure` records the package name, imports, named classes and
interfaces, methods and constructors, method invocations, and `extends` or
`implements` relationships. Imports use the shared `name`, `alias`, and
`location` shape; Java has no import aliases, so `alias` is always `None`.
Each symbol, import, call, inheritance edge, and error carries the shared
`SourceLocation` with inclusive one-based line numbers. Qualified symbol
names include the package and nested type names. Calls and base type names
remain syntax expressions: this parser does not resolve their targets.

Malformed syntax returns empty structure lists and one non-retryable
`JAVA_SYNTAX_ERROR` at the first Tree-sitter error location, allowing analysis
of other files to continue. The package is `None` for empty or malformed
files. Anonymous classes, fields, local variables, annotations, and type
resolution are outside this parser's current extraction scope.

Run the targeted check from `backend/` with
`uv run pytest -q tests/parsers/java/test_java_parser.py`.
