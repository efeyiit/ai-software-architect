"""Qdrant storage with server-composed ownership and current-SHA filters."""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Callable, Mapping, Protocol, Sequence
from uuid import uuid5, NAMESPACE_URL

from qdrant_client import QdrantClient, models

from app.contracts.analysis import SourceLocation
from app.services.github_private.service import PrivateRepositorySnapshot
from app.services.github_public.service import RepositorySnapshot
from .chunker import CodeChunk, chunk_snapshot


class IndexingError(ValueError):
    """Invalid configuration, authorization, or vector-index contract."""


@dataclass(frozen=True)
class AuthorizedScope:
    """Returned by a trusted live resolver, never built from query parameters."""

    owner_id: str
    repository_id: str
    source_repository_id: str
    commit_sha: str
    private: bool


class EmbeddingProvider(Protocol):
    """A configured local model. Test vectors are not semantic embeddings."""

    model_id: str
    dimension: int
    execution_location: str

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...
    def embed_query(self, text: str) -> Sequence[float]: ...


ScopeResolver = Callable[[str, str], AuthorizedScope | None]


@dataclass(frozen=True)
class SearchHit:
    chunk: CodeChunk
    score: float


def _related_terms(token: str) -> tuple[str, ...]:
    """Small bilingual repository vocabulary, independent of any one question."""
    if token.startswith("depo") or token.startswith("proje"):
        return (token, "repository", "project", "repo")
    if token in {"repository", "repo", "project"}:
        return (token, "repository", "project", "depo", "proje")
    return (token,)


def _lexical_content(hit: SearchHit) -> str:
    """Ignore repeated Markdown question prompts, retaining code and FAQ answers."""
    lines = hit.chunk.text.casefold().splitlines()
    if hit.chunk.kind != "document":
        return "\n".join(lines)
    is_prompt = [bool(re.fullmatch(r"\s*(?:[-*+]\s+|\d+[.)]\s+)[^?]+\?\s*", line))
                 for line in lines]
    keep = [True] * len(lines)
    start = 0
    while start < len(lines):
        if not is_prompt[start]:
            start += 1
            continue
        end = start + 1
        while end < len(lines) and is_prompt[end]:
            end += 1
        if end - start >= 3:
            for position in range(start, end):
                keep[position] = False
        start = end
    return "\n".join(line for line, included in zip(lines, keep, strict=True)
                     if included)


def _rerank_hits(question: str, hits: list[SearchHit], limit: int) -> tuple[SearchHit, ...]:
    """Counter long-file crowding; prefer actual query terms and distinct files."""
    if not hits:
        return ()
    tokens = set(re.findall(r"(?u)[^\W_]{3,}", question.casefold()))
    weights = {token: min(len(token), 16) for token in tokens}
    total_weight = sum(weights.values()) or 1
    file_counts = Counter(hit.chunk.location.path for hit in hits)
    scored = []
    for rank, hit in enumerate(hits):
        path = hit.chunk.location.path.casefold()
        content = _lexical_content(hit)
        text_match = sum(weight for token, weight in weights.items()
                         if any(term in content for term in _related_terms(token)))
        path_match = sum(weight for token, weight in weights.items() if token in path)
        basename = path.rsplit("/", 1)[-1].split(".", 1)[0]
        named_file = len(basename) >= 4 and basename in tokens
        score = (hit.score - 0.012 * math.log2(file_counts[hit.chunk.location.path])
                 + 0.10 * text_match / total_weight
                 + 0.04 * path_match / total_weight
                 + (0.08 if named_file else 0.0))
        scored.append((score, rank, hit))
    selected: list[SearchHit] = []
    chosen_per_file: Counter[str] = Counter()
    while scored and len(selected) < limit:
        best = max(range(len(scored)), key=lambda index: (
            scored[index][0] - 0.045 * chosen_per_file[scored[index][2].chunk.location.path],
            -scored[index][1]))
        _, _, hit = scored.pop(best)
        selected.append(hit)
        chosen_per_file[hit.chunk.location.path] += 1
    return tuple(selected)


def _scope_filter(scope: AuthorizedScope, *, include_sha: bool) -> models.Filter:
    fields = {"owner_id": scope.owner_id, "repository_id": scope.repository_id}
    if include_sha:
        fields["commit_sha"] = scope.commit_sha
        fields["source_repository_id"] = scope.source_repository_id
    return models.Filter(must=[models.FieldCondition(key=key,
                         match=models.MatchValue(value=value)) for key, value in fields.items()])


def _vector(values: Sequence[float], dimension: int) -> list[float]:
    if len(values) != dimension:
        raise IndexingError("embedding dimension mismatch")
    result = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise IndexingError("embedding contains an invalid number")
        result.append(float(value))
    return result


class QdrantIndex:
    def __init__(self, client: QdrantClient, resolve_scope: ScopeResolver,
                 embedding: EmbeddingProvider | None, *, collection_prefix: str = "ariadne_code"):
        if embedding is None:
            raise IndexingError("a real, locally configured embedding provider is required")
        if not callable(resolve_scope):
            raise IndexingError("a trusted live scope resolver is required")
        if (not isinstance(embedding.model_id, str) or not embedding.model_id
                or type(embedding.dimension) is not int or embedding.dimension < 1):
            raise IndexingError("embedding model id and positive dimension are required")
        if embedding.execution_location != "local":
            raise IndexingError("repository code may only be embedded by a local provider")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", collection_prefix):
            raise IndexingError("invalid collection prefix")
        self.client = client
        self.resolve_scope = resolve_scope
        self.embedding = embedding
        model_key = sha256(embedding.model_id.encode("utf-8")).hexdigest()[:16]
        self.collection_name = f"{collection_prefix}_{model_key}_{embedding.dimension}"

    def _scope(self, caller_id: str, repository_id: str) -> AuthorizedScope:
        if not caller_id or not repository_id:
            raise IndexingError("authenticated caller and repository are required")
        scope = self.resolve_scope(caller_id, repository_id)
        if (not isinstance(scope, AuthorizedScope) or scope.owner_id != caller_id
                or scope.repository_id != repository_id
                or not isinstance(scope.source_repository_id, str)
                or not scope.source_repository_id
                or not re.fullmatch(r"[0-9a-f]{40}", scope.commit_sha)
                or type(scope.private) is not bool):
            raise IndexingError("repository access denied or current snapshot unavailable")
        return scope

    def current_scope(self, caller_id: str, repository_id: str) -> AuthorizedScope:
        """Recheck live access/SHA for a downstream answer before it is returned."""
        return self._scope(caller_id, repository_id)

    def _collection(self) -> None:
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(self.collection_name,
                vectors_config=models.VectorParams(size=self.embedding.dimension,
                                                   distance=models.Distance.COSINE))
        actual = self.client.get_collection(self.collection_name).config.params.vectors
        if not isinstance(actual, models.VectorParams) or actual.size != self.embedding.dimension or actual.distance != models.Distance.COSINE:
            raise IndexingError("existing Qdrant collection has an incompatible vector configuration")

    def index_snapshot(self, caller_id: str, repository_id: str,
                       snapshot: RepositorySnapshot, source_texts: Mapping[str, str], *,
                       document_texts: Mapping[str, str] | None = None,
                       private_document_snapshot: PrivateRepositorySnapshot | None = None) -> int:
        scope = self._scope(caller_id, repository_id)
        if (snapshot.repository_id != scope.source_repository_id
                or snapshot.commit_sha != scope.commit_sha):
            raise IndexingError("snapshot differs from current authorized repository")
        if private_document_snapshot is not None:
            if (not scope.private or not isinstance(private_document_snapshot,
                    PrivateRepositorySnapshot)
                    or private_document_snapshot.local_user_id != caller_id
                    or private_document_snapshot.repository != snapshot):
                raise IndexingError("private document snapshot differs from authorized scope")
        elif scope.private and document_texts:
            raise IndexingError("private document input requires an authorized snapshot")
        chunks = chunk_snapshot(scope.owner_id, snapshot, source_texts,
                                repository_id=scope.repository_id,
                                document_texts=document_texts)
        if len(chunks) > 20_000:
            raise IndexingError("snapshot exceeds the chunk limit")
        points: list[models.PointStruct] = []
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset:offset + 64]
            vectors = self.embedding.embed_documents([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise IndexingError("embedding provider returned the wrong vector count")
            for chunk, values in zip(batch, vectors, strict=True):
                location = chunk.location
                point_id = str(uuid5(NAMESPACE_URL, "\0".join((chunk.owner_id,
                    chunk.repository_id, chunk.source_repository_id,
                    chunk.commit_sha, self.embedding.model_id,
                    chunk.kind,
                    location.path, str(location.start_line), str(location.end_line),
                    str(chunk.ordinal), chunk.content_sha256))))
                points.append(models.PointStruct(id=point_id,
                    vector=_vector(values, self.embedding.dimension), payload={
                        "owner_id": chunk.owner_id, "repository_id": chunk.repository_id,
                        "source_repository_id": chunk.source_repository_id,
                        "commit_sha": chunk.commit_sha, "private": scope.private,
                        "path": location.path,
                        "start_line": location.start_line, "end_line": location.end_line,
                        "text": chunk.text, "content_sha256": chunk.content_sha256,
                        "ordinal": chunk.ordinal, "kind": chunk.kind,
                    }))
        # Recheck after potentially slow embedding work, before any storage mutation.
        if self._scope(caller_id, repository_id) != scope:
            raise IndexingError("repository authorization or current SHA changed")
        self._collection()
        wanted = {point.id for point in points}
        stale: list[str | int] = []
        offset = None
        while True:
            records, offset = self.client.scroll(self.collection_name,
                scroll_filter=_scope_filter(scope, include_sha=False), limit=256,
                offset=offset, with_payload=False, with_vectors=False)
            stale.extend(record.id for record in records if record.id not in wanted)
            if offset is None:
                break
        if stale:
            self.client.delete(self.collection_name,
                points_selector=models.PointIdsList(points=stale), wait=True)
        for offset in range(0, len(points), 64):
            self.client.upsert(self.collection_name, points=points[offset:offset + 64], wait=True)
        return len(points)

    def search(self, caller_id: str, repository_id: str, question: str,
               *, limit: int = 10) -> tuple[SearchHit, ...]:
        scope = self._scope(caller_id, repository_id)
        if not isinstance(question, str) or not question.strip() or not 1 <= limit <= 50:
            raise IndexingError("question and limit must be valid")
        vector = _vector(self.embedding.embed_query(question), self.embedding.dimension)
        if self._scope(caller_id, repository_id) != scope:
            raise IndexingError("repository authorization or current SHA changed")
        if not self.client.collection_exists(self.collection_name):
            return ()
        self._collection()
        # A bounded wider pool prevents one long document from occupying every
        # answer slot. The trusted scope filter still applies inside Qdrant.
        candidate_limit = min(128, max(96, limit * 2))
        result = self.client.query_points(self.collection_name, query=vector,
            query_filter=_scope_filter(scope, include_sha=True), limit=candidate_limit,
            with_payload=True, with_vectors=False)
        if self._scope(caller_id, repository_id) != scope:
            raise IndexingError("repository authorization or current SHA changed")
        hits = []
        for point in result.points:
            payload = point.payload or {}
            if (payload.get("owner_id") != scope.owner_id
                    or payload.get("repository_id") != scope.repository_id
                    or payload.get("source_repository_id") != scope.source_repository_id
                    or payload.get("commit_sha") != scope.commit_sha
                    or payload.get("private") is not scope.private):
                raise IndexingError("Qdrant returned a point outside the authorized scope")
            location = SourceLocation(path=payload["path"],
                start_line=payload["start_line"], end_line=payload["end_line"])
            text = payload["text"]
            digest = sha256(text.encode("utf-8")).hexdigest()
            if digest != payload.get("content_sha256"):
                raise IndexingError("Qdrant chunk content digest mismatch")
            ordinal = payload.get("ordinal")
            if type(ordinal) is not int or ordinal < 0:
                raise IndexingError("Qdrant chunk ordinal is invalid")
            kind = payload.get("kind", "code")
            if kind not in ("code", "document"):
                raise IndexingError("Qdrant chunk kind is invalid")
            hits.append(SearchHit(CodeChunk(scope.owner_id, scope.repository_id,
                scope.source_repository_id, scope.commit_sha, location, text, digest,
                ordinal, kind),
                point.score))
        ranked = _rerank_hits(question, hits, limit)
        if self._scope(caller_id, repository_id) != scope:
            raise IndexingError("repository authorization or current SHA changed")
        return ranked
