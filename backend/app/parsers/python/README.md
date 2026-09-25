# Python structure parser

`parse_file(path, source)` reads Python source text with the standard library
`ast` module. It never imports or runs the analyzed file. Pass a normalized,
repository-relative POSIX path and decoded source text from the selected
repository snapshot.

The returned `FileStructure` contains `symbols` (classes, functions, methods,
and variable bindings), `imports`, `calls`, `inheritance`, and `errors`. Every
item carries the shared analysis contract's `SourceLocation`: repository path
and inclusive, one-based line numbers. `AnalysisError` also comes from that
contract. These field names and location rules are the shape other language
parsers can follow without changing the API-wide `AnalysisResult` contract.

Names and relationships reflect syntax only. A call's `callee` and a base
class's `base_name` are source expressions, not resolved targets. Variable
bindings include assignment targets such as loop variables, but exclude
instance attributes and function parameters. Repeated bindings remain separate
entries at their source locations. A syntax error returns empty structure lists
and one non-retryable `PYTHON_SYNTAX_ERROR` with a file location; it does not
prevent another file from being parsed. Invalid paths are rejected by the
shared location validator.

Run the targeted check from `backend/` with
`uv run pytest -q tests/parsers/python/test_parser.py`.
