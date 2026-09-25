# C# structure parser

`parse_file(path, source)` parses decoded `.cs` text with the native
`tree-sitter-c-sharp` grammar. The path must be normalized, repository-relative,
and POSIX-style. Source text is parsed as data; it is never compiled or run.

`FileStructure` follows the other language parsers with `symbols`, `imports`,
`calls`, `inheritance`, and `errors`. Symbols include namespaces, classes,
interfaces, and methods, with qualified names based on lexical nesting. Imports
represent `using` directives; aliases retain their local names. `using static`
retains the imported type name. Each class or interface base gets an inheritance
entry, and calls retain their source expression and enclosing scope. All entries
use the shared `SourceLocation` contract with one-based, inclusive line numbers.

This is syntax extraction. The parser does not resolve namespace aliases, types,
interface implementations, overloads, or call targets. A syntax error returns
empty structure lists and one non-retryable `CSHARP_SYNTAX_ERROR` at a source
location, so another file can still be parsed.

Run the targeted check from `backend/` with
`uv run pytest -q tests/parsers/csharp/test_csharp_parser.py`.
