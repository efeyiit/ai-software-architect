"""Deterministic line chunks from a complete, immutable repository snapshot."""

from dataclasses import dataclass
from hashlib import sha1, sha256
import re
from typing import Literal, Mapping

from app.contracts.analysis import SourceLocation
from app.services.github_public.service import RepositorySnapshot


@dataclass(frozen=True)
class CodeChunk:
    owner_id: str
    repository_id: str
    source_repository_id: str
    commit_sha: str
    location: SourceLocation
    text: str
    content_sha256: str
    ordinal: int
    kind: Literal["code", "document"] = "code"


_DOCUMENT_NAMES = frozenset({"pyproject.toml", "package.json", "openapi.json", "dockerfile"})
_README_NAMES = frozenset({"readme.md", "readme.rst", "readme.txt"})
_DOCUMENT_EXTENSIONS = frozenset({".md", ".rst", ".txt"})
_SKIP_DIRS = frozenset({"node_modules", "dist", "build", "vendor", ".git", ".venv",
                        "venv", "__pycache__", "coverage"})
_SENSITIVE_COMPONENT = re.compile(
    r"(?:password|passwd|secret|token|credential|private|key|authorization|auth)", re.I)
_SECRET_VALUE = re.compile(
    r"(?i)(?:-----BEGIN [^-]*PRIVATE KEY-----|"
    r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|"
    r"Bearer\s+[A-Za-z0-9._~+/-]{12,})\b|"
    r"\b(?:api[_-]?key|secret|token|password|credential)\b\s*[:=]\s*[^\s#]{8,})")


def _allowed_document(path: str) -> bool:
    SourceLocation(path=path, start_line=1, end_line=1)
    parts = path.lower().split("/")
    if any(part in _SKIP_DIRS or part.startswith(".") or
           _SENSITIVE_COMPONENT.search(part) for part in parts):
        return False
    name = parts[-1]
    if name in _DOCUMENT_NAMES:
        return True
    in_docs = len(parts) > 1 and parts[0] in {"docs", "doc"}
    if name in _README_NAMES:
        return len(parts) == 1 or in_docs
    return in_docs and any(name.endswith(suffix) for suffix in _DOCUMENT_EXTENSIONS)


def chunk_snapshot(owner_id: str, snapshot: RepositorySnapshot,
                   source_texts: Mapping[str, str], *, lines_per_chunk: int = 48,
                   overlap_lines: int = 6,
                   repository_id: str | None = None,
                   max_chars: int = 8_000,
                   document_texts: Mapping[str, str] | None = None) -> tuple[CodeChunk, ...]:
    """Require every selected source; never silently index a partial snapshot."""
    if (not isinstance(owner_id, str) or not owner_id
            or not snapshot.repository_id
            or not re.fullmatch(r"[0-9a-f]{40}", snapshot.commit_sha)):
        raise ValueError("owner, repository and SHA are required")
    if repository_id is None:
        repository_id = snapshot.repository_id
    if not isinstance(repository_id, str) or not repository_id:
        raise ValueError("local repository id is required")
    if lines_per_chunk < 1 or not 0 <= overlap_lines < lines_per_chunk or max_chars < 1:
        raise ValueError("invalid chunk size or overlap")
    all_files = {file.path: file for file in snapshot.files}
    if len(all_files) != len(snapshot.files):
        raise ValueError("snapshot has duplicate paths")
    files = {file.path: file for file in snapshot.included_files}
    expected = set(files)
    if set(source_texts) != expected:
        raise ValueError("source texts must exactly match selected snapshot files")
    documents = {} if document_texts is None else dict(document_texts)
    if len(documents) > 64:
        raise ValueError("document count exceeds the limit")
    for path in documents:
        if path not in all_files or path in expected or not _allowed_document(path):
            raise ValueError("document path is not an allowed snapshot document")
    if sum(all_files[path].size for path in documents) > 2_000_000:
        raise ValueError("document bytes exceed the limit")
    chunks: list[CodeChunk] = []
    for path in sorted(expected | set(documents)):
        kind: Literal["code", "document"] = "code" if path in expected else "document"
        source = source_texts[path] if kind == "code" else documents[path]
        if not isinstance(source, str):
            raise ValueError("source text must be a string")
        encoded = source.encode("utf-8")
        blob_sha = sha1(b"blob " + str(len(encoded)).encode("ascii") + b"\0" + encoded).hexdigest()
        file = files[path] if kind == "code" else all_files[path]
        if blob_sha != file.blob_sha or len(encoded) != file.size:
            raise ValueError("source text does not match the pinned Git blob")
        if kind == "document" and (len(encoded) > 512_000 or _SECRET_VALUE.search(source)):
            raise ValueError("document contains secret-like content or exceeds the size limit")
        SourceLocation(path=path, start_line=1, end_line=1)
        segments = [(line_number, line[offset:offset + max_chars])
                    for line_number, line in enumerate(source.splitlines(keepends=True), 1)
                    for offset in range(0, len(line), max_chars)]
        position = ordinal = 0
        while position < len(segments):
            end = position
            chars = 0
            while (end < len(segments) and end - position < lines_per_chunk
                   and chars + len(segments[end][1]) <= max_chars):
                chars += len(segments[end][1])
                end += 1
            selected = segments[position:end]
            text = "".join(part for _, part in selected)
            chunks.append(CodeChunk(owner_id, repository_id, snapshot.repository_id,
                                    snapshot.commit_sha,
                                    SourceLocation(path=path, start_line=selected[0][0],
                                                   end_line=selected[-1][0]),
                                    text, sha256(text.encode("utf-8")).hexdigest(),
                                    ordinal, kind))
            ordinal += 1
            if end >= len(segments):
                break
            position = end - min(overlap_lines, end - position - 1)
    return tuple(chunks)
