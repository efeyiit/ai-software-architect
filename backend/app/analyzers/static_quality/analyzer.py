"""Conservative syntax-based quality signals; analyzed source is never executed."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

from tree_sitter import Language, Node, Parser
import tree_sitter_c_sharp
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_typescript

from app.contracts.analysis import AnalysisFinding, FindingSource, Severity, SourceLocation
from app.analyzers.dependencies.graph import DependencyGraph


@dataclass(frozen=True)
class QualityThresholds:
    function_lines: int = 80
    class_lines: int = 500
    class_methods: int = 20
    nesting_depth: int = 4
    parameters: int = 6
    duplicate_tokens: int = 24
    magic_numbers: frozenset[str] = frozenset({"-1", "0", "1", "2"})

    def __post_init__(self) -> None:
        for name in ("function_lines", "class_lines", "class_methods", "nesting_depth",
                     "parameters", "duplicate_tokens"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")


_EXTENSIONS = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
    ".mts": "typescript", ".cts": "typescript", ".java": "java",
    ".cs": "csharp", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".h": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp",
}
_TS_LANGUAGES = {
    "typescript": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
    "java": Language(tree_sitter_java.language()),
    "csharp": Language(tree_sitter_c_sharp.language()),
    "cpp": Language(tree_sitter_cpp.language()),
}
_FUNCTION_NODES = {
    "typescript": {"function_declaration", "generator_function_declaration", "method_definition"},
    "java": {"method_declaration", "constructor_declaration"},
    "csharp": {"method_declaration"},
    "cpp": {"function_definition"},
}
_CONTROL_NODES = {
    "typescript": {"if_statement", "for_statement", "for_in_statement", "while_statement", "do_statement", "switch_statement", "catch_clause"},
    "java": {"if_statement", "for_statement", "enhanced_for_statement", "while_statement", "do_statement", "switch_expression", "catch_clause"},
    "csharp": {"if_statement", "for_statement", "foreach_statement", "while_statement", "do_statement", "switch_statement", "catch_clause"},
    "cpp": {"if_statement", "for_statement", "for_range_loop", "while_statement", "do_statement", "switch_statement", "catch_clause"},
}
_NUMBER_NODES = {"number", "number_literal", "decimal_integer_literal", "decimal_floating_point_literal",
                 "integer_literal", "floating_point_literal"}
_IGNORED_LEAVES = {"comment", "line_comment", "block_comment", "string", "string_literal", "string_fragment",
                   "raw_string_literal", "template_string", "character_literal", "char_literal"}


def _language(path: str) -> str:
    extension = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if extension not in _EXTENSIONS:
        raise ValueError(f"unsupported source path: {path}")
    return _EXTENSIONS[extension]


def _location(path: str, node: Node) -> SourceLocation:
    end = node.end_point.row + (1 if node.end_point.column else 0)
    return SourceLocation(path=path, start_line=node.start_point.row + 1,
                          end_line=max(node.start_point.row + 1, end))


def _walk(node: Node) -> Iterable[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type == "ERROR" or current.is_missing:
            continue
        yield current
        stack.extend(reversed(current.named_children))


def _tokens(node: Node, source: bytes) -> tuple[str, ...]:
    """Named syntax leaves only; comments and strings cannot mimic executable code."""
    result: list[str] = []
    for part in _walk(node):
        if part.type in _IGNORED_LEAVES or "comment" in part.type or "string" in part.type:
            continue
        if not part.named_children:
            result.append(source[part.start_byte:part.end_byte].decode("utf-8"))
    return tuple(result)


def _body(node: Node) -> Node | None:
    direct = node.child_by_field_name("body")
    if direct is not None:
        return direct
    return next((part for part in node.named_children if part.type in
                 {"statement_block", "block", "compound_statement", "class_body", "declaration_list"}), None)


def _parameter_count(node: Node) -> int | None:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        declarator = node.child_by_field_name("declarator")
        for part in _walk(declarator) if declarator is not None else ():
            if part.type == "function_declarator":
                parameters = part.child_by_field_name("parameters")
                break
    if parameters is None:
        return None
    return len([part for part in parameters.named_children if part.type not in
                {"type_parameters", "comment", "line_comment", "block_comment"}])


def _named_constant(node: Node, source: bytes) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type in {"const_declaration", "constant_declaration", "enum_member_declaration"}:
        return True
    if parent.type == "variable_declarator":
        name = parent.child_by_field_name("name")
        if name is not None:
            return source[name.start_byte:name.end_byte].decode("utf-8").isupper()
    return False


def _deepest(node: Node, controls: set[str]) -> tuple[int, Node]:
    best = (0, node)
    stack = [(node, 0)]
    while stack:
        part, depth = stack.pop()
        if part.type in controls:
            depth += 1
            if depth > best[0]:
                best = (depth, part)
        # A nested function has its own nesting count.
        stack.extend((child, depth) for child in part.named_children
                     if child.type not in {"function_declaration", "method_definition", "lambda_expression"})
    return best


def _python_imports(tree: ast.AST, structure: object) -> list[object]:
    """Only definite lexical non-use; star imports and dynamic namespace access abstain."""
    if any(isinstance(node, (ast.ImportFrom, ast.Import)) and any(alias.name == "*" for alias in node.names)
           for node in ast.walk(tree)):
        return []
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id in {"eval", "exec", "globals", "locals", "vars", "__import__"}
           for node in ast.walk(tree)):
        return []
    loads = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    public = {item.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
              for item in ast.walk(node.value) if isinstance(item, ast.Constant) and isinstance(item.value, str)}
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    unused = []
    for parsed in imports:
        for alias in parsed.names:
            binding = alias.asname or (alias.name.split(".", 1)[0] if isinstance(parsed, ast.Import) else alias.name)
            if (binding in loads or binding in public or alias.name == "*" or
                    (isinstance(parsed, ast.ImportFrom) and parsed.module == "__future__")):
                continue
            match = next((item for item in structure.imports if item.location.start_line == parsed.lineno
                          and item.alias == alias.asname and
                          (item.name == alias.name or item.name.endswith("." + alias.name))), None)
            if match is not None:
                unused.append(match)
    return unused


def analyze_static_quality(structures: Iterable[object], sources: dict[str, str],
                           graph: DependencyGraph | None = None,
                           thresholds: QualityThresholds = QualityThresholds()) -> list[AnalysisFinding]:
    """Analyze exact source text matching the supplied parser results.

    Caller owns snapshot consistency. Parser errors suppress all checks for that file.
    The graph must be built from the same structures; only its resolved cycles count.
    """
    files = list(structures)
    if len({file.path for file in files}) != len(files):
        raise ValueError("duplicate source path")
    if set(sources) != {file.path for file in files}:
        raise ValueError("sources must exactly match parsed files")
    findings: list[AnalysisFinding] = []
    duplicates: dict[tuple[str, ...], list[SourceLocation]] = defaultdict(list)

    def add(kind: str, location: SourceLocation, description: str, suggestion: str) -> None:
        key = f"{kind}:{location.path}:{location.start_line}:{location.end_line}:{description}:{len(findings)}"
        findings.append(AnalysisFinding(id=sha256(key.encode()).hexdigest()[:20],
                                        source=FindingSource.static, issue_type=kind,
                                        severity=Severity.medium, location=location,
                                        description=description, suggestion=suggestion))

    for file in sorted(files, key=lambda item: item.path):
        path = file.path
        language = _language(path)
        SourceLocation(path=path, start_line=1, end_line=1)
        if file.errors:
            continue
        if any(item.location.path != path for group in (file.symbols, file.imports)
               for item in group):
            raise ValueError(f"foreign source location in {path}")
        source = sources[path]
        if language == "python":
            tree = ast.parse(source, filename=path)
            _analyze_python(path, tree, file, thresholds, add, duplicates)
        else:
            grammar = "tsx" if path.endswith(".tsx") else language
            raw = source.encode("utf-8")
            root = Parser(_TS_LANGUAGES[grammar]).parse(raw).root_node
            if root.has_error and language != "cpp":
                continue
            _analyze_tree(path, language, root, raw, file, thresholds, add, duplicates)

    for locations in duplicates.values():
        if len(locations) > 1:
            for location in locations:
                add("duplicate_code", location, "Equivalent function body appears more than once.",
                    "Extract shared behavior where appropriate.")
    if graph is not None:
        valid_paths = {file.path for file in files}
        node_paths = {node.id: node.location.path for node in graph.nodes}
        for cycle in graph.cycles:
            paths = sorted({node.removeprefix("file:") for node in cycle})
            if not paths or not set(paths) <= valid_paths:
                raise ValueError("graph cycle refers to a different snapshot")
            for path in paths:
                edge = next((edge for edge in graph.edges if edge.status == "resolved" and
                             edge.location.path == path and edge.target is not None and
                             node_paths.get(edge.target) in paths and
                             node_paths.get(edge.target) != path), None)
                if edge is not None:
                    add("circular_dependency", edge.location,
                        "Resolved dependency cycle includes " + ", ".join(paths) + ".",
                        "Remove one dependency or move shared code to a separate module.")
    return sorted(findings, key=lambda item: (item.location.path, item.location.start_line, item.issue_type))


def _analyze_python(path: str, tree: ast.AST, file: object, limits: QualityThresholds,
                    add: object, duplicates: dict[tuple[str, ...], list[SourceLocation]]) -> None:
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            location = SourceLocation(path=path, start_line=node.lineno, end_line=node.end_lineno)
            if node.end_lineno - node.lineno + 1 > limits.function_lines:
                add("long_function", location, "Function exceeds the line threshold.", "Split into focused functions.")
            count = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
            if node.args.vararg:
                count += 1
            if node.args.kwarg:
                count += 1
            if node.args.args and node.args.args[0].arg in {"self", "cls"}:
                count -= 1
            if count > limits.parameters:
                add("too_many_parameters", location, "Function exceeds the parameter threshold.",
                    "Group related inputs into a value object.")
            depth, deepest = _python_depth(node)
            if depth > limits.nesting_depth:
                add("deep_nesting", SourceLocation(path=path, start_line=deepest.lineno,
                                                    end_line=deepest.lineno),
                    "Control flow exceeds the nesting threshold.", "Extract a helper or return early.")
            normalized = ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)
            if sum(isinstance(part, (ast.Name, ast.Constant, ast.Call, ast.BinOp, ast.Compare,
                                     ast.Return, ast.Assign)) for statement in node.body
                   for part in ast.walk(statement)) >= limits.duplicate_tokens:
                duplicates[("python", normalized)].append(location)
        elif isinstance(node, ast.ClassDef):
            methods = sum(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) for item in node.body)
            if node.end_lineno - node.lineno + 1 > limits.class_lines or methods > limits.class_methods:
                add("large_class", SourceLocation(path=path, start_line=node.lineno, end_line=node.end_lineno),
                    "Class exceeds the size or method threshold.", "Separate distinct responsibilities.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            parent = parents.get(node)
            named_constant = isinstance(parent, (ast.Assign, ast.AnnAssign)) and any(
                isinstance(target, ast.Name) and target.id.isupper()
                for target in (parent.targets if isinstance(parent, ast.Assign) else [parent.target]))
            if str(node.value) not in limits.magic_numbers and not named_constant:
                add("magic_number", SourceLocation(path=path, start_line=node.lineno, end_line=node.lineno),
                    f"Numeric literal {node.value} has no descriptive name.", "Use a named constant.")
    for item in _python_imports(tree, file):
        add("unused_import", item.location, f"Import {item.name} has no lexical use.", "Remove the import.")


def _python_depth(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, ast.AST]:
    controls = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)
    best: tuple[int, ast.AST] = (0, function)
    stack = [(child, 0) for child in function.body]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, controls):
            depth += 1
            if depth > best[0]:
                best = (depth, node)
        stack.extend((child, depth) for child in ast.iter_child_nodes(node))
    return best


def _analyze_tree(path: str, language: str, root: Node, source: bytes, file: object,
                  limits: QualityThresholds, add: object,
                  duplicates: dict[tuple[str, ...], list[SourceLocation]]) -> None:
    symbols = {(item.location.start_line, item.kind) for item in file.symbols}
    for node in _walk(root):
        if node.type in _FUNCTION_NODES[language]:
            start = node.start_point.row + 1
            if not any((start, kind) in symbols for kind in ("function", "method")):
                continue
            location = _location(path, node)
            if location.end_line - location.start_line + 1 > limits.function_lines:
                add("long_function", location, "Function exceeds the line threshold.", "Split into focused functions.")
            count = _parameter_count(node)
            if count is not None and count > limits.parameters:
                add("too_many_parameters", location, "Function exceeds the parameter threshold.",
                    "Group related inputs into a value object.")
            body = _body(node)
            if body is not None:
                depth, deepest = _deepest(body, _CONTROL_NODES[language])
                if depth > limits.nesting_depth:
                    add("deep_nesting", _location(path, deepest), "Control flow exceeds the nesting threshold.",
                        "Extract a helper or return early.")
                tokens = _tokens(body, source)
                if len(tokens) >= limits.duplicate_tokens:
                    duplicates[(language, *tokens)].append(location)
        elif node.type in {"class_declaration", "abstract_class_declaration", "class_specifier"}:
            location = _location(path, node)
            class_symbol = next((item for item in file.symbols if item.kind == "class" and
                                 item.location.start_line == location.start_line), None)
            if class_symbol is None:
                continue
            separator = "::" if language == "cpp" else "."
            methods = sum(item.kind == "method" and
                          item.qualified_name.rpartition(separator)[0] == class_symbol.qualified_name
                          for item in file.symbols)
            if location.end_line - location.start_line + 1 > limits.class_lines or methods > limits.class_methods:
                add("large_class", location, "Class exceeds the size or method threshold.",
                    "Separate distinct responsibilities.")
        elif node.type in _NUMBER_NODES:
            literal = source[node.start_byte:node.end_byte].decode("utf-8")
            if literal not in limits.magic_numbers and not _named_constant(node, source):
                add("magic_number", _location(path, node), f"Numeric literal {literal} has no descriptive name.",
                    "Use a named constant.")
