"""Extract C++ syntax as inert text with the native Tree-sitter grammar."""

from __future__ import annotations

from typing import Literal

import tree_sitter_cpp
from tree_sitter import Language, Node, Parser

from app.contracts.analysis import AnalysisError, SourceLocation, WireModel


class Symbol(WireModel):
    kind: Literal["namespace", "class", "struct", "function", "method"]
    name: str
    qualified_name: str
    location: SourceLocation


class Import(WireModel):
    name: str
    alias: str | None
    location: SourceLocation


class Call(WireModel):
    callee: str
    scope: str | None
    location: SourceLocation


class Inheritance(WireModel):
    class_name: str
    base_name: str
    location: SourceLocation


class MacroUncertainty(WireModel):
    name: str
    reason: Literal["definition", "invocation", "dynamic_include", "conditional"]
    location: SourceLocation


class FileStructure(WireModel):
    path: str
    symbols: list[Symbol]
    imports: list[Import]
    calls: list[Call]
    inheritance: list[Inheritance]
    macro_uncertainties: list[MacroUncertainty]
    errors: list[AnalysisError]


_CPP = Language(tree_sitter_cpp.language())
_EXTENSIONS = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h")
_CONDITIONALS = {"preproc_if", "preproc_ifdef", "preproc_else", "preproc_elif", "preproc_elifdef"}


class _Collector:
    def __init__(self, path: str, source: bytes, macro_names: set[str]) -> None:
        self.path = path
        self.source = source
        self.macro_names = macro_names
        self.scope: list[str] = []
        self.class_names: set[str] = set()
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.inheritance: list[Inheritance] = []
        self.macro_uncertainties: list[MacroUncertainty] = []

    def text(self, node: Node) -> str:
        return self.source[node.start_byte:node.end_byte].decode("utf-8")

    def location(self, node: Node, *, full_range: bool = False) -> SourceLocation:
        start = node.start_point.row + 1
        end = max(start, node.end_point.row + (1 if node.end_point.column else 0)) if full_range else start
        return SourceLocation(path=self.path, start_line=start, end_line=end)

    def qualified(self, name: str) -> str:
        if not self.scope:
            return name.lstrip(":")
        prefix = "::".join(self.scope)
        if name.startswith("::"):
            return name[2:]
        if name.startswith(prefix + "::"):
            return name
        return prefix + "::" + name

    def visit_children(self, node: Node) -> None:
        for child in node.named_children:
            self.visit(child)

    def visit(self, node: Node) -> None:
        kind = node.type
        if kind == "preproc_include":
            path = node.child_by_field_name("path")
            if path is not None:
                raw = self.text(path)
                literal = path.type in ("system_lib_string", "string_literal")
                self.imports.append(Import(name=raw[1:-1] if literal else raw,
                                           alias=None, location=self.location(node)))
                if not literal:
                    self._uncertain(raw, "dynamic_include", node)
            return
        if kind in ("preproc_def", "preproc_function_def"):
            name = node.child_by_field_name("name")
            if name is not None:
                self._uncertain(self.text(name), "definition", node)
            return
        if kind in _CONDITIONALS:
            name = node.child_by_field_name("name")
            self._uncertain(self.text(name) if name is not None else self.text(node).splitlines()[0],
                            "conditional", node)
            return
        if kind == "namespace_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = self.text(name_node)
                self.symbols.append(Symbol(kind="namespace", name=name,
                                           qualified_name=self.qualified(name),
                                           location=self.location(node, full_range=True)))
                self.scope.append(name)
                body = node.child_by_field_name("body")
                if body is not None:
                    self.visit_children(body)
                self.scope.pop()
            return
        if kind in ("class_specifier", "struct_specifier"):
            self._type(node)
            return
        if kind == "function_definition":
            self._function(node)
            return
        if kind in ("declaration", "field_declaration"):
            if self._function(node):
                return
        if kind == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                callee = self.text(function)
                if callee in self.macro_names:
                    self._uncertain(callee, "invocation", node)
                else:
                    self.calls.append(Call(callee=callee, scope="::".join(self.scope) or None,
                                           location=self.location(node)))
        self.visit_children(node)

    def _uncertain(self, name: str, reason: Literal["definition", "invocation", "dynamic_include", "conditional"],
                   node: Node) -> None:
        self.macro_uncertainties.append(MacroUncertainty(name=name, reason=reason,
                                                          location=self.location(node)))

    def _type(self, node: Node) -> None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            self.visit_children(node)
            return
        name = self.text(name_node)
        qualified = self.qualified(name)
        self.class_names.add(qualified)
        self.symbols.append(Symbol(kind="class" if node.type == "class_specifier" else "struct",
                                   name=name, qualified_name=qualified,
                                   location=self.location(node, full_range=True)))
        base_clause = next((child for child in node.named_children
                            if child.type == "base_class_clause"), None)
        if base_clause is not None:
            for base in base_clause.named_children:
                if base.type not in ("access_specifier", "virtual_specifier"):
                    self.inheritance.append(Inheritance(class_name=qualified, base_name=self.text(base),
                                                        location=self.location(base)))
        self.scope.append(name)
        body = node.child_by_field_name("body")
        if body is not None:
            self.visit_children(body)
        self.scope.pop()

    def _function(self, node: Node) -> bool:
        declarator = node.child_by_field_name("declarator")
        while declarator is not None and declarator.type != "function_declarator":
            declarator = declarator.child_by_field_name("declarator")
        if declarator is None:
            return False
        name_node = declarator.child_by_field_name("declarator")
        if name_node is None:
            return False
        raw_name = self.text(name_node)
        qualified = self.qualified(raw_name)
        name = raw_name.split("::")[-1]
        parent_name = qualified.rpartition("::")[0]
        kind = "method" if parent_name in self.class_names or any(
            item in self.class_names for item in self._scope_classes()
        ) else "function"
        self.symbols.append(Symbol(kind=kind, name=name, qualified_name=qualified,
                                   location=self.location(node, full_range=True)))
        body = node.child_by_field_name("body")
        if body is not None:
            previous_scope = self.scope
            self.scope = qualified.split("::")
            self.visit(body)
            self.scope = previous_scope
        return True

    def _scope_classes(self) -> list[str]:
        return ["::".join(self.scope[:index]) for index in range(1, len(self.scope) + 1)]


def _macro_names(root: Node, source: bytes) -> set[str]:
    names: set[str] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in ("preproc_def", "preproc_function_def"):
            name = node.child_by_field_name("name")
            if name is not None:
                names.add(source[name.start_byte:name.end_byte].decode("utf-8"))
        stack.extend(node.named_children)
    return names


def _first_error(node: Node, macro_names: set[str], source: bytes) -> Node | None:
    if node.type == "ERROR":
        return node
    if node.is_missing:
        return node
    for child in node.children:
        if not (child.has_error or child.is_missing):
            continue
        if child.type == "expression_statement":
            call = next((part for part in child.named_children if part.type == "call_expression"), None)
            name = call.child_by_field_name("function") if call is not None else None
            if (name is not None and source[name.start_byte:name.end_byte].decode("utf-8") in macro_names
                    and all(part.is_missing and part.type == ";" for part in child.children if part != call)):
                continue
        result = _first_error(child, macro_names, source)
        if result is not None:
            return result
    return None


def parse_file(path: str, source: str) -> FileStructure:
    """Parse one normalized repository-relative C++ source or header without execution."""
    SourceLocation(path=path, start_line=1, end_line=1)
    if not path.endswith(_EXTENSIONS):
        raise ValueError("C++ parser requires a C++ source or header path")
    data = source.encode("utf-8")
    root = Parser(_CPP).parse(data).root_node
    macros = _macro_names(root, data)
    collector = _Collector(path, data, macros)
    error_node = _first_error(root, macros, data) if root.has_error else None
    if error_node is not None:
        error = AnalysisError(code="CPP_SYNTAX_ERROR", message="Invalid C++ syntax",
                              retryable=False, location=collector.location(error_node))
        return FileStructure(path=path, symbols=[], imports=[], calls=[], inheritance=[],
                             macro_uncertainties=[], errors=[error])
    collector.visit(root)
    return FileStructure(path=path, symbols=collector.symbols, imports=collector.imports,
                         calls=collector.calls, inheritance=collector.inheritance,
                         macro_uncertainties=collector.macro_uncertainties, errors=[])
