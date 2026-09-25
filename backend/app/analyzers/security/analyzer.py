"""Potential security risks from inert source syntax; no snippets leave this module."""

from __future__ import annotations

import ast
from hashlib import sha256
import re
from typing import Iterable

from tree_sitter import Language, Node, Parser
import tree_sitter_c_sharp
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_typescript

from app.contracts.analysis import AnalysisFinding, FindingSource, Severity, SourceLocation


_EXTENSIONS = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".mts": "typescript",
    ".cts": "typescript", ".java": "java", ".cs": "csharp", ".cpp": "cpp",
    ".cc": "cpp", ".cxx": "cpp", ".h": "cpp", ".hpp": "cpp",
    ".hh": "cpp", ".hxx": "cpp",
}
_GRAMMARS = {
    "typescript": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
    "java": Language(tree_sitter_java.language()),
    "csharp": Language(tree_sitter_c_sharp.language()),
    "cpp": Language(tree_sitter_cpp.language()),
}
_SECRET_NAME = re.compile(r"(?i)(?:api_?key|password|passwd|secret|access_?token|auth_?token|private_?key)")
_ENV_NAME = re.compile(r"(?i)(?:secret|password|passwd|token|api_?key|private_?key)")
_SQL_TEXT = re.compile(r"(?i)\b(?:select\s+.+\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from)\b")
_DYNAMIC_CONCAT = re.compile(r"(?:\+\s*[A-Za-z_$][\w$]*\b|\b[A-Za-z_$][\w$]*\s*\+)")
_LOG_CALL = re.compile(r"(?i)\b(?:logger|log|console)\s*\.\s*(?:log|debug|info|warn|warning|error|critical|trace|LogInformation|LogWarning|LogError)\s*\(|\b(?:print|printf)\s*\(")
_ENV_ACCESS = re.compile(r"(?i)(?:\bprocess\s*\.\s*env\s*\.\s*(\w+)|\b(?:System\s*\.\s*getenv|Environment\s*\.\s*GetEnvironmentVariable|std\s*::\s*getenv|getenv)\s*\(\s*['\"]([^'\"]+)['\"])")
_SENSITIVE_ROUTE = re.compile(r"(?i)(?:^|/)(?:admin|internal|private)(?:/|$)")
_RULES = {
    "hardcoded_secret": (Severity.high, "Potential hardcoded credential in a source assignment.",
                         "Move the credential to a managed secret source and rotate it if real."),
    "dynamic_sql": (Severity.medium, "Potential SQL query construction from dynamic input.",
                    "Use bound parameters or a query builder; review the data flow."),
    "jwt_validation": (Severity.high, "Potential JWT validation bypass or decode without verification.",
                       "Require signature and claim validation before trusting the token."),
    "possible_missing_auth": (Severity.medium, "Potential missing authorization on an explicitly public sensitive route.",
                              "Review route and global middleware authorization before exposing it."),
    "sensitive_log": (Severity.medium, "Potential sensitive value passed to a logging call.",
                      "Remove or redact the sensitive argument before logging."),
    "environment_secret": (Severity.info, "Potential environment secret handling risk at this read.",
                           "Trace the secret use and prevent logging or response exposure."),
}


def _finding(path: str, line: int, kind: str) -> AnalysisFinding:
    severity, description, suggestion = _RULES[kind]
    identifier = sha256(f"security:{kind}:{path}:{line}".encode()).hexdigest()[:20]
    return AnalysisFinding(id=identifier, source=FindingSource.static,
                           issue_type=kind, severity=severity,
                           location=SourceLocation(path=path, start_line=line, end_line=line),
                           description=description, suggestion=suggestion)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + "." + node.attr
    return ""


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _dynamic_sql(node: ast.AST | None) -> bool:
    if node is None:
        return False
    sql = any(isinstance(part, ast.Constant) and isinstance(part.value, str)
              and _SQL_TEXT.search(part.value) for part in ast.walk(node))
    if not sql:
        return False
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return any(isinstance(part, (ast.Name, ast.Call, ast.Attribute, ast.Subscript))
                   for part in ast.walk(node))
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format" and bool(node.args or node.keywords))


def _secret_env(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript) and _name(node.value) in {"os.environ", "environ"}:
        return bool((key := _literal(node.slice)) and _ENV_NAME.search(key))
    if isinstance(node, ast.Call) and _name(node.func) in {"os.getenv", "os.environ.get", "getenv"}:
        return bool(node.args and (key := _literal(node.args[0])) and _ENV_NAME.search(key))
    return False


def _jwt_bypass(node: ast.Call) -> bool:
    if _name(node.func).lower() not in {"jwt.decode", "pyjwt.decode", "jwt.api_jwt.decode"}:
        return False
    for keyword in node.keywords:
        if keyword.arg in {"verify", "verify_signature"} and isinstance(keyword.value, ast.Constant):
            if keyword.value.value is False:
                return True
        if keyword.arg == "options" and isinstance(keyword.value, ast.Dict):
            for key, value in zip(keyword.value.keys, keyword.value.values):
                if key is not None and _literal(key) == "verify_signature":
                    if isinstance(value, ast.Constant) and value.value is False:
                        return True
    return False


def _public_sensitive_route(node: ast.FunctionDef | ast.AsyncFunctionDef, middleware: bool) -> bool:
    if middleware or not any(_name(dec).lower().endswith(("public", "allow_anonymous", "permit_all"))
                             for dec in node.decorator_list if not isinstance(dec, ast.Call)):
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call) and dec.args and _name(dec.func).lower().endswith(
                (".get", ".post", ".put", ".patch", ".delete", ".route")):
            route = _literal(dec.args[0])
            if route and re.search(r"(?i)(?:^|/)(?:admin|internal|private)(?:/|$)", route):
                return True
    return False


def _scan_python(path: str, source: str, global_middleware: bool) -> set[tuple[str, int]]:
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    found: set[tuple[str, int]] = set()
    middleware = global_middleware or any(
        isinstance(node, ast.Call) and _name(node.func).endswith("add_middleware")
        and node.args and "auth" in _name(node.args[0]).lower()
        for node in ast.walk(tree))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                value = _literal(node.value)
                if _SECRET_NAME.search(_name(target)) and value and len(value) >= 8:
                    if not value.startswith(("${", "{{")):
                        found.add(("hardcoded_secret", node.lineno))
            if _dynamic_sql(node.value):
                found.add(("dynamic_sql", node.lineno))
        if isinstance(node, ast.Call):
            callee = _name(node.func)
            if _jwt_bypass(node):
                found.add(("jwt_validation", node.lineno))
            if callee.endswith(("execute", "executemany", "query")) and node.args and _dynamic_sql(node.args[0]):
                found.add(("dynamic_sql", node.lineno))
            if _LOG_CALL.search(callee + "(") and any(
                    isinstance(part, ast.Name) and _SECRET_NAME.search(part.id) or _secret_env(part)
                    for arg in node.args for part in ast.walk(arg)):
                found.add(("sensitive_log", node.lineno))
        if isinstance(node, ast.Return) and node.value and any(_secret_env(part) for part in ast.walk(node.value)):
            found.add(("environment_secret", node.lineno))
        if isinstance(node, ast.Call) and _LOG_CALL.search(_name(node.func) + "("):
            if any(_secret_env(part) for arg in node.args for part in ast.walk(arg)):
                found.add(("environment_secret", node.lineno))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _public_sensitive_route(node, middleware):
            found.add(("possible_missing_auth", node.lineno))
    return found


def _walk(node: Node) -> Iterable[Node]:
    stack = [node]
    while stack:
        part = stack.pop()
        if part.type != "ERROR" and not part.is_missing:
            yield part
            stack.extend(reversed(part.named_children))


def _code_mask(root: Node, raw: bytes) -> str:
    mask = bytearray(raw)
    for node in _walk(root):
        if "comment" in node.type or "string" in node.type or node.type in {"character_literal", "raw_string_literal"}:
            for index in range(node.start_byte, node.end_byte):
                if mask[index] not in (10, 13):
                    mask[index] = 32
    return mask.decode("utf-8", errors="replace")


def _scan_tree(source: str, language: str, global_middleware: bool) -> set[tuple[str, int]]:
    raw = source.encode("utf-8")
    root = Parser(_GRAMMARS[language]).parse(raw).root_node
    if root.has_error and language != "cpp":
        return set()
    found: set[tuple[str, int]] = set()
    raw_lines = source.splitlines()
    code_lines = _code_mask(root, raw).splitlines()
    for number, (line, executable) in enumerate(zip(raw_lines, code_lines), 1):
        for match in re.finditer(r"(?i)\b(api_?key|password|passwd|secret|access_?token|auth_?token|private_?key)\b\s*=\s*(['\"])(.{8,}?)\2", line):
            if executable[match.start():match.start() + len(match.group(1))].strip():
                found.add(("hardcoded_secret", number))
        dynamic = bool(_DYNAMIC_CONCAT.search(executable) or
                       ("${" in line and "`" in line) or
                       ('$"' in line and "{" in line))
        if _SQL_TEXT.search(line) and dynamic:
            if re.search(r"(?i)\b(?:query|execute\w*|commandtext|sql)\b", executable):
                found.add(("dynamic_sql", number))
        log_match = _LOG_CALL.search(executable)
        if log_match and _SECRET_NAME.search(executable[log_match.end():]):
            found.add(("sensitive_log", number))
        for env_match in _ENV_ACCESS.finditer(line):
            if _ENV_NAME.search(env_match.group(1) or env_match.group(2) or "") and \
                    executable[env_match.start():env_match.start() + 3].strip() and \
                    (log_match or re.search(r"\breturn\b", executable)):
                found.add(("environment_secret", number))
        if language in {"typescript", "tsx"} and re.search(r"\bjwt\s*\.\s*decode\s*\(", executable):
            found.add(("jwt_validation", number))
        if re.search(r"(?i)\b(?:verify_signature|verifySignature)\s*[:=]\s*false\b", executable):
            if "jwt" in executable.lower() or "token" in executable.lower():
                found.add(("jwt_validation", number))
        if re.search(r"(?i)\b(?:ignoreExpiration|ValidateLifetime|verify_exp)\s*[:=]\s*(?:true|false)\b", executable):
            if ("jwt" in executable.lower() or "token" in executable.lower()) and \
                    re.search(r"(?i)\b(?:ignoreExpiration\s*:\s*true|ValidateLifetime\s*=\s*false|verify_exp\s*[:=]\s*false)\b", executable):
                found.add(("jwt_validation", number))
    if not global_middleware and language in {"typescript", "tsx", "java", "csharp"}:
        for index, executable in enumerate(code_lines):
            public = (re.search(r"@\s*(?:Public|PermitAll|AllowAnonymous)\b", executable)
                      if language != "csharp" else re.search(r"\[\s*AllowAnonymous\s*\]", executable))
            if not public:
                continue
            window = raw_lines[index:index + 5]
            code_window = code_lines[index:index + 5]
            for raw_route, code_route in zip(window, code_window):
                marker = (re.search(r"@\s*(?:Get|Post|Put|Patch|Delete|Path)\s*\(", code_route)
                          if language != "csharp" else re.search(r"\[\s*Http(?:Get|Post|Put|Patch|Delete)\s*\(", code_route))
                if marker and _SENSITIVE_ROUTE.search(raw_route):
                    if language != "java" or any(re.search(r"@\s*(?:GET|POST|PUT|PATCH|DELETE)\b", item)
                                                     for item in code_window):
                        found.add(("possible_missing_auth", index + 1))
                    break
    return found


def analyze_security(structures: Iterable[object], sources: dict[str, str]) -> list[AnalysisFinding]:
    """Analyze source corresponding to five real parser structures without executing it."""
    files = list(structures)
    if len({file.path for file in files}) != len(files):
        raise ValueError("duplicate source path")
    if set(sources) != {file.path for file in files}:
        raise ValueError("sources must exactly match parsed files")
    global_middleware = any(
        call.callee.endswith("add_middleware") and
        re.search(r"\bAuthenticationMiddleware\b",
                  sources[file.path].splitlines()[call.location.start_line - 1])
        for file in files for call in file.calls
        if not file.errors and call.location.path == file.path and
        call.location.start_line <= len(sources[file.path].splitlines()))
    findings: list[AnalysisFinding] = []
    for file in sorted(files, key=lambda item: item.path):
        path = file.path
        language = _EXTENSIONS.get("." + path.rsplit(".", 1)[-1])
        if language is None:
            raise ValueError("unsupported source path")
        SourceLocation(path=path, start_line=1, end_line=1)
        if file.errors:
            continue
        if any(item.location.path != path for group in (file.symbols, file.imports, file.calls)
               for item in group):
            raise ValueError("foreign source location")
        signals = (_scan_python(path, sources[path], global_middleware) if language == "python"
                   else _scan_tree(sources[path], language, global_middleware))
        findings.extend(_finding(path, line, kind) for kind, line in sorted(signals, key=lambda x: (x[1], x[0])))
    return findings
