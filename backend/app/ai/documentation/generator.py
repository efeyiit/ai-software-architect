"""Build inert, source-linked README and API drafts from one authorized snapshot."""

from __future__ import annotations

import ast
import json
import re
import tomllib
from collections.abc import Mapping
from typing import Literal

from pydantic import Field

from app.contracts.analysis import RepositorySnapshot as SnapshotIdentity, SourceLocation, WireModel
from app.services.github_public.service import RepositorySnapshot


class DocumentationError(ValueError):
    """Input does not belong to the declared repository snapshot."""


class Evidence(WireModel):
    path: str
    line: int = Field(ge=1)


class DraftFact(WireModel):
    text: str
    evidence: Evidence


class APIField(WireModel):
    name: str
    type: str = "Unknown"


class APIRoute(WireModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    request_fields: list[APIField]
    response_fields: list[APIField]
    evidence: Evidence
    status: Literal["draft"] = "draft"


class DocumentationResult(WireModel):
    snapshot: SnapshotIdentity
    ai_status: Literal["unavailable"] = "unavailable"
    readme: str
    api_markdown: str
    facts: list[DraftFact]
    routes: list[APIRoute]
    uncertainties: list[str]


_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
_ENV_IDENT = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_ROUTE = re.compile(r"^/(?:[A-Za-z0-9._~{}-]+/?)*$")
_SENSITIVE = re.compile(r"(?i)(?:password|passwd|secret|token|api_?key|authorization|auth|cookie|credential|private_?key)")
_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "null"})


def _safe_path(path: str) -> bool:
    try:
        SourceLocation(path=path, start_line=1, end_line=1)
    except Exception:
        return False
    return all((part in {".env.example", ".env.sample", ".env.template"} or _IDENT.fullmatch(part))
               and not _SENSITIVE.search(part)
               for part in path.split("/"))


def _evidence(path: str, source: str, needle: str) -> Evidence:
    offset = source.find(needle)
    return Evidence(path=path, line=source.count("\n", 0, max(0, offset)) + 1)


def _fields(schema: object) -> list[APIField]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    fields = []
    for name, detail in sorted(properties.items()):
        if not isinstance(name, str) or not _IDENT.fullmatch(name) or _SENSITIVE.search(name):
            continue
        kind = detail.get("type") if isinstance(detail, dict) else None
        fields.append(APIField(name=name, type=kind if kind in _TYPES else "Unknown"))
    return fields


def _content_schema(value: object) -> object:
    if not isinstance(value, dict):
        return None
    content = value.get("content")
    if not isinstance(content, dict):
        return None
    for mime in ("application/json", "application/*+json"):
        media = content.get(mime)
        if isinstance(media, dict):
            return media.get("schema")
    return None


def _openapi_routes(path: str, source: str, uncertainties: list[str]) -> list[APIRoute]:
    try:
        document = json.loads(source)
    except (ValueError, UnicodeError):
        uncertainties.append(f"Malformed OpenAPI JSON at {path}; routes unknown.")
        return []
    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        uncertainties.append(f"OpenAPI paths unknown at {path}.")
        return []
    routes = []
    for route, methods in sorted(paths.items()):
        if not isinstance(route, str) or not _ROUTE.fullmatch(route) or _SENSITIVE.search(route):
            continue
        if not isinstance(methods, dict):
            continue
        for method, operation in sorted(methods.items()):
            if method.lower() not in _METHODS or not isinstance(operation, dict):
                continue
            request = _fields(_content_schema(operation.get("requestBody")))
            responses = operation.get("responses")
            response = None
            if isinstance(responses, dict):
                for status in sorted(responses):
                    if isinstance(status, str) and status.startswith("2"):
                        response = _content_schema(responses[status])
                        break
            routes.append(APIRoute(method=method.upper(), path=route,
                                   request_fields=request, response_fields=_fields(response),
                                   evidence=_evidence(path, source, '"' + route + '"')))
    return routes


def _python_routes(path: str, source: str, uncertainties: list[str]) -> list[APIRoute]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        uncertainties.append(f"Malformed Python source at {path}; routes unknown.")
        return []
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.lower()
            if method not in _METHODS or not decorator.args:
                continue
            literal = decorator.args[0]
            if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
                continue
            route = literal.value
            if not _ROUTE.fullmatch(route) or _SENSITIVE.search(route):
                continue
            routes.append(APIRoute(method=method.upper(), path=route,
                                   request_fields=[], response_fields=[],
                                   evidence=Evidence(path=path, line=decorator.lineno)))
    return routes


def generate_documentation(
    snapshot: RepositorySnapshot,
    source_texts: Mapping[str, str],
) -> DocumentationResult:
    """Produce deterministic drafts; caller binds supplied text to authorized blob SHAs.

    No analyzed source is run or transmitted. Only allowlisted facts and identifiers
    leave this boundary; source values, descriptions, examples, snippets and headers
    are never copied into generated output.
    """
    try:
        identity = SnapshotIdentity(repository_id=snapshot.repository_id,
                                    commit_sha=snapshot.commit_sha)
        paths = {file.path for file in snapshot.files}
        if len(paths) != len(snapshot.files) or not set(source_texts).issubset(paths):
            raise ValueError("source paths differ from snapshot")
        if any(not _safe_path(path) or not isinstance(source, str) or len(source) > 512_000
               for path, source in source_texts.items()):
            raise ValueError("unsafe source or path")
    except Exception as exc:
        raise DocumentationError("sources must belong to a valid snapshot") from exc

    facts: list[DraftFact] = []
    uncertainties = ["Drafts are limited to supplied files from the declared repository commit.",
                     "Caller must verify each source text against its snapshot blob SHA and repository permission.",
                     "No analyzed repository code, install command, test, or Docker build was executed."]
    requirements = "Unknown from supplied manifests."
    installation = "Unknown; review project-specific setup before running any command."
    running = "Unknown from supplied manifests."
    testing = "Unknown from supplied manifests."
    docker = "Unknown; no Dockerfile was supplied."
    env_names: list[str] = []
    routes: list[APIRoute] = []
    for path, source in sorted(source_texts.items()):
        name = path.rsplit("/", 1)[-1].lower()
        if name == "pyproject.toml":
            try:
                manifest = tomllib.loads(source)
                project = manifest.get("project", {})
                version = project.get("requires-python") if isinstance(project, dict) else None
                if isinstance(version, str) and re.fullmatch(r"[<>=!~.,0-9 ]+", version):
                    requirements = f"Python {version} (manifest: {path})."
                    facts.append(DraftFact(text=requirements, evidence=_evidence(path, source, "requires-python")))
                installation = f"Draft: Python project manifest at {path}; installation command unknown."
            except (ValueError, TypeError):
                uncertainties.append(f"Malformed Python manifest at {path}; setup unknown.")
        elif name == "package.json":
            try:
                manifest = json.loads(source)
                if isinstance(manifest, dict):
                    installation = f"Draft: package manifest at {path}; dependency installation command requires review."
                    scripts = manifest.get("scripts")
                    if isinstance(scripts, dict):
                        if "start" in scripts:
                            evidence = _evidence(path, source, '"start"')
                            running = f"Draft: npm run start (declared at {path}:{evidence.line}; script body was not reviewed or run)."
                            facts.append(DraftFact(text="start script declared.", evidence=evidence))
                        if "test" in scripts:
                            evidence = _evidence(path, source, '"test"')
                            testing = f"Draft: npm run test (declared at {path}:{evidence.line}; script body was not reviewed or run)."
                            facts.append(DraftFact(text="test script declared.", evidence=evidence))
            except (ValueError, UnicodeError):
                uncertainties.append(f"Malformed package manifest at {path}; setup unknown.")
        elif name in {".env.example", ".env.sample", ".env.template"}:
            for line in source.splitlines():
                match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
                if match and _ENV_IDENT.fullmatch(match.group(1)):
                    env_names.append(match.group(1))
                    facts.append(DraftFact(text=f"Environment variable {match.group(1)} declared.",
                                           evidence=_evidence(path, source, line)))
        elif name == "dockerfile":
            docker = f"Draft: Dockerfile exists at {path}; build and run commands unknown."
            facts.append(DraftFact(text="Dockerfile present.", evidence=Evidence(path=path, line=1)))
        elif name == "openapi.json":
            routes.extend(_openapi_routes(path, source, uncertainties))
        elif name.endswith(".py"):
            routes.extend(_python_routes(path, source, uncertainties))
    env_facts = {fact.text.removeprefix("Environment variable ").removesuffix(" declared."): fact.evidence
                 for fact in facts if fact.text.startswith("Environment variable ")}
    env_text = ", ".join(f"`{name}` ({env_facts[name].path}:{env_facts[name].line})"
                         for name in sorted(set(env_names))) or "Unknown; no example env names supplied."
    structure = ", ".join(f"`{path}`" for path in sorted(source_texts) if not _SENSITIVE.search(path)) or "Unknown."
    route_lines = []
    seen = set()
    for route in sorted(routes, key=lambda item: (item.path, item.method, item.evidence.path)):
        key = route.method, route.path
        if key in seen:
            continue
        seen.add(key)
        route_lines.extend([f"### {route.method} {route.path}",
                            f"Source: `{route.evidence.path}:{route.evidence.line}`. Draft route; authorization unknown.",
                            "Request: " + (", ".join(f"`{field.name}` ({field.type})" for field in route.request_fields)
                                           if route.request_fields else "Unknown."),
                            "Response: " + (", ".join(f"`{field.name}` ({field.type})" for field in route.response_fields)
                                            if route.response_fields else "Unknown."), ""])
    api_markdown = "# API Documentation (draft)\n\nRepository commit: `" + identity.commit_sha + "`.\n\n" + (
        "\n".join(route_lines) if route_lines else "No source-backed routes found; API unknown.\n")
    readme = "\n".join([
        "# Repository README (draft)", "", f"Repository commit: `{identity.commit_sha}`.", "",
        "## Project Description", "Unknown from supplied evidence.", "",
        "## Requirements", requirements, "", "## Installation", installation, "",
        "## Environment Variables", env_text + ". Values are omitted.", "",
        "## Running Locally", running, "", "## Docker Setup", docker, "",
        "## API Documentation", "See the source-linked API draft.", "",
        "## Project Structure", structure, "", "## Testing", testing, "",
    ])
    return DocumentationResult(snapshot=identity, readme=readme, api_markdown=api_markdown,
                               facts=facts, routes=routes, uncertainties=uncertainties)
