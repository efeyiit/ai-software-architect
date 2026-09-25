"""Bounded, inert browser-folder import. Never reads arbitrary disk paths."""

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from pathlib import PurePosixPath
import unicodedata
from uuid import uuid4

from pydantic import Field

from app.contracts.analysis import SourceLocation, WireModel
from app.local.models import LocalSnapshot
from app.services.github_public.service import SKIP_DIRS


@dataclass(frozen=True)
class ImportLimits:
    max_files: int = 2_000
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 20_971_520


class UploadedSource(WireModel):
    path: str = Field(min_length=1, max_length=1024, strict=True)
    content: str = Field(strict=True)


TEXT_SUFFIXES = {".py", ".pyi", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx",
                 ".java", ".cs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx",
                 ".json", ".toml", ".md", ".rst", ".txt", ".yaml", ".yml", ".xml", ".ini", ".cfg"}
SKIP_NAMES = {"id_rsa", "id_ed25519", "id_dsa", "id_ecdsa", ".npmrc", ".pypirc", "credentials", "credentials.json"}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
GENERATED_DIRS = SKIP_DIRS | {".idea", ".next", ".nuxt", "target", "bin", "obj", ".pytest_cache"}


def exclusion_reason(path: str, content: str) -> str | None:
    parts = [part.lower() for part in path.split("/")]
    name, suffix = parts[-1], PurePosixPath(parts[-1]).suffix
    if any(part in GENERATED_DIRS for part in parts[:-1]):
        return "generated_or_dependency_directory"
    if name == ".env" or name.startswith(".env.") or name in SKIP_NAMES or suffix in PRIVATE_SUFFIXES:
        return "sensitive_file"
    if re.search(r"(?m)^\s*-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----\s*$", content):
        return "private_key_content"
    if "\x00" in content:
        return "binary_content"
    if suffix not in TEXT_SUFFIXES and name not in {"dockerfile", "makefile", "license"}:
        return "unsupported_file_type"
    return None


def import_files(name: str, files: list[UploadedSource], *, repository_id: str | None = None,
                 limits: ImportLimits = ImportLimits()) -> LocalSnapshot:
    if len(files) > limits.max_files:
        raise ValueError("file count limit exceeded")
    sources, excluded, seen = {}, {}, set()
    total = 0
    for file in files:
        path = unicodedata.normalize("NFC", file.path)
        SourceLocation(path=path, start_line=1, end_line=1)
        if path in seen:
            raise ValueError("duplicate normalized source path")
        seen.add(path)
        raw = file.content.encode("utf-8")
        total += len(raw)
        if len(raw) > limits.max_file_bytes or total > limits.max_total_bytes:
            raise ValueError("source byte limit exceeded")
        reason = exclusion_reason(path, file.content)
        if reason:
            excluded[path] = reason
        else:
            sources[path] = file.content
    manifest = {"sources": {path: sha256(text.encode("utf-8")).hexdigest() for path, text in sources.items()},
                "excluded": excluded}
    digest = sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return LocalSnapshot(repository_id=repository_id or str(uuid4()), snapshot_id="local:" + digest,
                         name=name, sources=sources, excluded=excluded)
