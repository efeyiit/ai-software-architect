"""T25 API operations; repository bytes remain inert data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha1
import logging
import os
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.ai.orchestration import Coordinator, SnapshotMaterial, make_job_handler
from app.ai.summaries import summarize_repository
from app.api.router import ApiError
from app.cache import AnalysisCache, CacheKey, config_digest
from app.contracts.analysis import AnalysisResult, SourceLocation
from app.database import Store
from app.diagrams import render_diagrams
from app.jobs import JobStore, Worker
from app.local_inference import (LocalAnswerProvider, LocalEmbeddingProvider,
                                 LocalRuntimeUnavailable)
from app.rag.chat import RepositoryChat
from app.rag.indexing import IndexingError, QdrantIndex
from app.security.identity import IdentityError
from app.services.github_private import GitHubPrivateService
from app.services.github_private.service import PrivateRepositorySnapshot
from app.services.github_private.scope import LiveRepositoryScopeResolver
from app.services.github_private.scope import ScopeResolutionError
from app.services.github_public.service import GitHubPublicError, GitHubPublicService
from app.parsers.python import parse_file as parse_python
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp


PARSER_SUFFIXES = (".py", ".ts", ".tsx", ".mts", ".cts", ".java", ".cs",
                   ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx")
ANALYSIS_VERSION = "t25-v2"
PARSERS = {".py": parse_python, ".ts": parse_typescript, ".tsx": parse_typescript,
           ".mts": parse_typescript, ".cts": parse_typescript, ".java": parse_java,
           ".cs": parse_csharp, ".cpp": parse_cpp, ".cc": parse_cpp,
           ".cxx": parse_cpp, ".h": parse_cpp, ".hpp": parse_cpp,
           ".hh": parse_cpp, ".hxx": parse_cpp}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportingMaterial(SnapshotMaterial):
    """T24 input plus the actual owner-bound private read capability."""

    private_document_snapshot: PrivateRepositorySnapshot | None = None


class ApiRuntime:
    def __init__(self, dsn: str, identity, *, public=None, private=None, chat=None,
                 rag_index: QdrantIndex | None = None,
                 search_path: str | None = None, scope_resolver=None):
        if not dsn or identity is None:
            raise ValueError("database and configured identity are required")
        self.dsn = dsn
        self.identity = identity
        self.public = public or GitHubPublicService()
        self.private = private or GitHubPrivateService(identity.oauth)
        self.chat_service = chat
        self.rag_index = rag_index
        self.search_path = search_path
        self.scope_resolver = scope_resolver

    @classmethod
    def from_env(cls, identity):
        dsn = os.getenv("ARIADNE_DATABASE_URL", "")
        if not dsn:
            raise ValueError("ARIADNE_DATABASE_URL is required")
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
            if not all(connection.execute("SELECT to_regclass('repositories'), to_regclass('analysis_jobs'), to_regclass('analysis_cache')").fetchone()):
                raise ValueError("analysis database schema is unavailable")
        runtime = cls(dsn, identity)
        qdrant_url = os.getenv("ARIADNE_QDRANT_URL", "")
        qdrant_key = os.getenv("ARIADNE_QDRANT_API_KEY", "")
        model_token = os.getenv("ARIADNE_LOCAL_RUNTIME_TOKEN", "")
        if qdrant_url or qdrant_key or model_token:
            parsed = urlsplit(qdrant_url)
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                    or parsed.port != 6333 or parsed.path not in ("", "/")
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or not model_token or not qdrant_key):
                raise ValueError("local model token, Qdrant key and loopback URL are required together")
            index = QdrantIndex(QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=30),
                                runtime._scope, LocalEmbeddingProvider(token=model_token),
                                collection_prefix="ariadne_code_docs_v1")
            runtime.rag_index = index
            runtime.chat_service = RepositoryChat(index, LocalAnswerProvider(token=model_token),
                                                  max_hits=3, max_context_chars=5000)
        return runtime

    def _connect(self):
        connection = psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)
        if self.search_path is not None:
            connection.execute("SELECT set_config('search_path', %s, false)", (self.search_path,))
        return connection

    def _scope(self, owner: str, repository_id: str):
        try:
            if self.scope_resolver is None:
                with self._connect() as connection:
                    scope = LiveRepositoryScopeResolver(Store(connection), self.identity.oauth)(owner, repository_id)
            else:
                scope = self.scope_resolver(owner, repository_id)
        except ScopeResolutionError as exc:
            raise ApiError(503 if exc.retryable else 502, exc.code.lower()) from None
        if scope is None:
            raise ApiError(404, "repository_unavailable")
        return scope

    def _fetch(self, owner: str, github_url: str):
        try:
            return self.public.fetch_repository(github_url), None
        except GitHubPublicError as exc:
            if exc.code not in ("ACCESS_DENIED", "REPOSITORY_NOT_FOUND"):
                raise ApiError(422 if not exc.retryable else 503, exc.code.lower()) from None
        try:
            private_snapshot = self.private.fetch_repository(owner, github_url)
            return private_snapshot.repository, private_snapshot
        except IdentityError as exc:
            if exc.code == "CONFIGURATION_ERROR" or exc.retryable:
                raise ApiError(503, exc.code.lower()) from None
            raise ApiError(404, "repository_unavailable") from None
        except GitHubPublicError as exc:
            if exc.retryable:
                raise ApiError(503, exc.code.lower()) from None
            raise ApiError(404, "repository_unavailable") from None

    def _authorized_snapshot(self, owner: str, repository_id: str):
        scope = self._scope(owner, repository_id)
        with self._connect() as connection:
            row = Store(connection).get_repository(owner, repository_id)
        if row is None:
            raise ApiError(404, "repository_unavailable")
        snapshot, private_snapshot = self._fetch(owner, row["github_url"])
        after = self._scope(owner, repository_id)
        if (snapshot.repository_id != scope.source_repository_id or snapshot.commit_sha != scope.commit_sha
                or after != scope or bool(private_snapshot) != scope.private):
            raise ApiError(409, "snapshot_changed")
        selected = tuple(replace(file, included=False, exclusion_reason="unsupported_parser")
                         if file.included and not file.path.endswith(PARSER_SUFFIXES) else file
                         for file in snapshot.files)
        snapshot = replace(snapshot, repository_id=repository_id, files=selected)
        return snapshot, private_snapshot

    def create_repository(self, owner: str, github_url: str):
        snapshot, _ = self._fetch(owner, github_url)
        with self._connect() as connection:
            store = Store(connection)
            try:
                with connection.transaction():
                    repository_id = store.create_repository(owner, snapshot.github_url, snapshot.name)
                    store.create_snapshot(owner, repository_id, snapshot.commit_sha)
            except psycopg.errors.UniqueViolation:
                raise ApiError(409, "repository_exists") from None
        return {"id": repository_id, "github_url": snapshot.github_url,
                "name": snapshot.name, "commit_sha": snapshot.commit_sha}

    def list_repositories(self, owner: str):
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id::text, github_url, name FROM repositories
                   WHERE user_id=%s ORDER BY created_at DESC, id DESC LIMIT 100""",
                (owner,)).fetchall()
        result = []
        for repository_id, github_url, name in rows:
            try:
                scope = self._scope(owner, repository_id)
            except ApiError as exc:
                if exc.status_code == 404:
                    continue
                raise
            result.append({"id": repository_id, "github_url": github_url,
                           "name": name, "commit_sha": scope.commit_sha})
        return result

    def repository(self, owner: str, repository_id: str):
        snapshot, _ = self._authorized_snapshot(owner, repository_id)
        return {"id": repository_id, "github_url": snapshot.github_url, "name": snapshot.name,
                "branch": snapshot.default_branch, "commit_sha": snapshot.commit_sha,
                "languages": dict(snapshot.languages), "frameworks": list(snapshot.frameworks)}

    def files(self, owner: str, repository_id: str):
        snapshot, _ = self._authorized_snapshot(owner, repository_id)
        return {"snapshot": {"repository_id": repository_id, "commit_sha": snapshot.commit_sha},
                "files": [{"path": file.path, "language": file.language, "included": file.included,
                           "size": file.size, "exclusion_reason": file.exclusion_reason}
                          for file in snapshot.files]}

    def file_summary(self, owner: str, repository_id: str, path: str):
        try:
            SourceLocation(path=path, start_line=1, end_line=1)
        except ValueError:
            raise ApiError(422, "invalid_path") from None
        snapshot, private_snapshot = self._authorized_snapshot(owner, repository_id)
        file = next((item for item in snapshot.included_files if item.path == path), None)
        if file is None:
            raise ApiError(404, "file_unavailable")
        parser = next((function for suffix, function in PARSERS.items() if path.endswith(suffix)), None)
        if parser is None:
            raise ApiError(422, "unsupported_language")
        if private_snapshot is None:
            source = self.public.fetch_file(snapshot, file)
        else:
            original = next(item for item in private_snapshot.repository.files if item.path == path)
            source = self.private.fetch_file(owner, private_snapshot, original)
        raw = source.encode("utf-8")
        if sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != file.blob_sha:
            raise ApiError(409, "snapshot_changed")
        subset = replace(snapshot, files=tuple(item if item.path == path else
                         replace(item, included=False, exclusion_reason="not_selected_for_summary")
                         for item in snapshot.files))
        report = summarize_repository(subset, [parser(path, source)])
        if self._scope(owner, repository_id).commit_sha != snapshot.commit_sha:
            raise ApiError(409, "snapshot_changed")
        summary = report.files[0]
        return {"snapshot": report.snapshot.model_dump(mode="json"), "ai_status": report.ai_status,
                **summary.model_dump(mode="json")}

    def _cache_key(self, owner: str, snapshot):
        return CacheKey(owner, snapshot.repository_id, snapshot.default_branch,
                        snapshot.commit_sha, config_digest({"pipeline": ANALYSIS_VERSION}),
                        "unavailable", ANALYSIS_VERSION)

    def analyze(self, owner: str, repository_id: str, idempotency_key: str | None):
        snapshot, _ = self._authorized_snapshot(owner, repository_id)
        if not snapshot.included_files:
            raise ApiError(422, "unsupported_language")
        key = self._cache_key(owner, snapshot)
        with self._connect() as connection:
            store = Store(connection)
            store.create_snapshot(owner, repository_id, snapshot.commit_sha)
            cache = AnalysisCache(connection, lambda user, repo: self._scope(user, repo).commit_sha == snapshot.commit_sha)
            hit = cache.get(key)
            if hit is not None:
                try:
                    indexed = self.rag_index is None or self._has_index(owner, repository_id)
                except (ResponseHandlingException, UnexpectedResponse, ConnectionError, TimeoutError):
                    raise ApiError(503, "repository_index_unavailable") from None
                if indexed:
                    return {"status": "cached", "analysis_id": hit.analysis_id, "commit_sha": snapshot.commit_sha}
                # The durable result survived but local vectors did not. Rebuild in
                # the worker, never in an HTTP request; reuse an active rebuild.
                existing = connection.execute(
                    """SELECT id FROM analysis_jobs WHERE user_id=%s AND repository_id=%s
                       AND snapshot_id=(SELECT id FROM repository_snapshots
                                        WHERE repository_id=%s AND commit_sha=%s)
                       AND status IN ('queued', 'running')
                       ORDER BY created_at DESC LIMIT 1""",
                    (owner, repository_id, repository_id, snapshot.commit_sha)).fetchone()
                if existing is not None:
                    return {"status": "queued", "job_id": str(existing[0]),
                            "commit_sha": snapshot.commit_sha}
            try:
                job = JobStore(connection).enqueue(owner, repository_id, snapshot.commit_sha,
                                                   str(uuid4()) if hit is not None else
                                                   (idempotency_key or str(uuid4())))
            except ValueError:
                raise ApiError(409, "idempotency_conflict") from None
        if job is None:
            raise ApiError(409, "snapshot_changed")
        return {"status": job.status, "job_id": job.id, "commit_sha": snapshot.commit_sha}

    def _job(self, owner: str, repository_id: str, job_id: str):
        try:
            UUID(job_id)
        except ValueError:
            raise ApiError(404, "job_unavailable") from None
        scope = self._scope(owner, repository_id)
        with self._connect() as connection:
            job = JobStore(connection).get(owner, job_id)
        if job is None or job.repository_id != repository_id:
            raise ApiError(404, "job_unavailable")
        if job.commit_sha != scope.commit_sha or self._scope(owner, repository_id) != scope:
            raise ApiError(409, "snapshot_changed")
        return job

    def job(self, owner: str, repository_id: str, job_id: str):
        job = self._job(owner, repository_id, job_id)
        return {"job_id": job.id, "status": job.status, "commit_sha": job.commit_sha,
                "attempts": job.attempts, "error_code": job.error_code,
                "analysis_id": job.result_analysis_id}

    def cancel(self, owner: str, repository_id: str, job_id: str):
        self._job(owner, repository_id, job_id)
        with self._connect() as connection:
            job = JobStore(connection).cancel(owner, job_id)
        return {"job_id": job.id, "status": job.status, "cancel_requested": job.cancel_requested}

    def analysis(self, owner: str, repository_id: str, analysis_id: str):
        scope = self._scope(owner, repository_id)
        with self._connect() as connection:
            result = Store(connection).get_analysis(owner, analysis_id)
        if result is None or result.snapshot.repository_id != repository_id:
            raise ApiError(404, "analysis_unavailable")
        if result.snapshot.commit_sha != scope.commit_sha or self._scope(owner, repository_id) != scope:
            raise ApiError(409, "snapshot_changed")
        return result.model_dump(mode="json")

    def _latest(self, owner: str, repository_id: str) -> AnalysisResult:
        scope = self._scope(owner, repository_id)
        with self._connect() as connection:
            row = connection.execute(
                """SELECT a.result FROM analyses a JOIN repositories r ON r.id=a.repository_id
                   JOIN repository_snapshots s ON s.id=a.snapshot_id
                   WHERE r.id=%s AND r.user_id=%s AND s.commit_sha=%s
                   ORDER BY a.created_at DESC, a.id DESC LIMIT 1""",
                (repository_id, owner, scope.commit_sha)).fetchone()
        if row is None:
            raise ApiError(404, "analysis_unavailable")
        if self._scope(owner, repository_id) != scope:
            raise ApiError(409, "snapshot_changed")
        return AnalysisResult.model_validate(row[0])

    def issues(self, owner: str, repository_id: str):
        result = self._latest(owner, repository_id)
        return {"analysis_id": result.analysis_id, "status": result.status,
                "commit_sha": result.snapshot.commit_sha,
                "findings": [finding.model_dump(mode="json") for finding in result.findings]}

    def dependencies(self, owner: str, repository_id: str):
        result = self._latest(owner, repository_id)
        return {"analysis_id": result.analysis_id, "status": result.status,
                "commit_sha": result.snapshot.commit_sha,
                "graph": result.dependencies.model_dump(mode="json") if result.dependencies else None}

    def diagrams(self, owner: str, repository_id: str):
        result = self._latest(owner, repository_id)
        if result.dependencies is None:
            raise ApiError(404, "diagram_unavailable")
        material = self.load_material(owner, repository_id, result.snapshot.commit_sha)
        if material is None:
            raise ApiError(409, "snapshot_changed")
        structures = []
        for file in material.snapshot.included_files:
            source = material.sources[file.path]
            raw = source.encode("utf-8")
            if sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != file.blob_sha:
                raise ApiError(409, "snapshot_changed")
            parser = next((function for suffix, function in PARSERS.items()
                           if file.path.endswith(suffix)), None)
            if parser is None:
                raise ApiError(422, "unsupported_language")
            structures.append(parser(file.path, source))
        try:
            bundle = render_diagrams(result.dependencies.model_dump(mode="json"), structures)
        except ValueError:
            raise ApiError(422, "diagram_limit_or_invalid_graph") from None
        if self._scope(owner, repository_id).commit_sha != result.snapshot.commit_sha:
            raise ApiError(409, "snapshot_changed")
        return {"snapshot": result.snapshot.model_dump(mode="json"), "status": result.status,
                "diagrams": {format_name: vars(value) for format_name, value in bundle.items()}}

    def chat(self, owner: str, repository_id: str, question: str):
        scope = self._scope(owner, repository_id)
        if self.chat_service is None:
            return {"status": "unavailable", "answer": "AI yanıt sağlayıcısı yapılandırılmamış.",
                    "origin": "none", "claims": [], "commit_sha": scope.commit_sha}
        try:
            if self.rag_index is not None and not self._has_index(owner, repository_id):
                return {"status": "unavailable", "answer": "Kaynak dizini henüz hazır değil.",
                        "origin": "none", "claims": [], "commit_sha": scope.commit_sha}
            answer = self.chat_service.ask(owner, repository_id, question)
        except (LocalRuntimeUnavailable, ResponseHandlingException, UnexpectedResponse,
                ConnectionError, TimeoutError):
            return {"status": "unavailable", "answer": "Yerel AI hizmeti şu anda kullanılamıyor.",
                    "origin": "none", "claims": [], "commit_sha": scope.commit_sha}
        return {"status": answer.status, "answer": answer.answer, "origin": answer.origin,
                "claims": [{"text": claim.text, "citations": [vars(c) for c in claim.citations]}
                           for claim in answer.claims], "commit_sha": answer.commit_sha}

    def _has_index(self, owner: str, repository_id: str) -> bool:
        if self.rag_index is None:
            return False
        scope = self._scope(owner, repository_id)
        index = self.rag_index
        if not index.client.collection_exists(index.collection_name):
            return False
        fields = {"owner_id": owner, "repository_id": repository_id,
                  "source_repository_id": scope.source_repository_id,
                  "commit_sha": scope.commit_sha, "private": scope.private}
        conditions = [models.FieldCondition(key=key, match=models.MatchValue(value=value))
                      for key, value in fields.items()]
        points, _ = index.client.scroll(index.collection_name,
            scroll_filter=models.Filter(must=conditions), limit=1,
            with_payload=False, with_vectors=False)
        if self._scope(owner, repository_id) != scope:
            raise ApiError(409, "snapshot_changed")
        return bool(points)

    def load_material(self, owner: str, repository_id: str, commit_sha: str):
        snapshot, private_snapshot = self._authorized_snapshot(owner, repository_id)
        if snapshot.commit_sha != commit_sha:
            return None
        sources = {}
        for file in snapshot.included_files:
            if private_snapshot is None:
                sources[file.path] = self.public.fetch_file(snapshot, file)
            else:
                original = next(item for item in private_snapshot.repository.files if item.path == file.path)
                sources[file.path] = self.private.fetch_file(owner, private_snapshot, original)
        documents = {}
        if private_snapshot is None:
            for file in self.public.document_files(snapshot):
                if file.path.lower().rsplit("/", 1)[-1].startswith(".env."):
                    continue
                documents[file.path] = self.public.fetch_document_file(snapshot, file)
        else:
            for file in self.private.document_files(owner, private_snapshot):
                if file.path.lower().rsplit("/", 1)[-1].startswith(".env."):
                    continue
                documents[file.path] = self.private.fetch_document_file(owner, private_snapshot, file)
        return ReportingMaterial(snapshot, sources, documents, {}, private_snapshot)

    def _index_material(self, owner: str, repository_id: str, commit_sha: str) -> int:
        if self.rag_index is None:
            return 0
        material = self.load_material(owner, repository_id, commit_sha)
        if material is None:
            raise ApiError(409, "snapshot_changed")
        scope = self._scope(owner, repository_id)
        if scope.commit_sha != commit_sha:
            raise ApiError(409, "snapshot_changed")
        source_snapshot = replace(material.snapshot, repository_id=scope.source_repository_id)
        current_snapshot, private_snapshot = self._authorized_snapshot(owner, repository_id)
        if (current_snapshot != material.snapshot or
                private_snapshot != material.private_document_snapshot):
            raise ApiError(409, "snapshot_changed")
        trusted_private = (replace(material.private_document_snapshot, repository=source_snapshot)
                           if material.private_document_snapshot is not None else None)
        return self.rag_index.index_snapshot(owner, repository_id,
                                             source_snapshot, dict(material.sources),
                                             document_texts=dict(material.document_sources),
                                             private_document_snapshot=trusted_private)

    def worker(self):
        return CachingWorker(self)


class CachingWorker(Worker):
    """Publish a cache reference only after T22 commits a successful result."""

    def __init__(self, runtime: ApiRuntime):
        self.runtime = runtime
        coordinator = Coordinator(lambda owner, repository_id:
                                  runtime._authorized_snapshot(owner, repository_id)[0])
        super().__init__(runtime._connect, make_job_handler(coordinator, runtime.load_material))

    def process_one(self):
        claimed = super().process_one()
        if claimed is None:
            return None
        try:
            with self.runtime._connect() as connection:
                current = JobStore(connection).get(claimed.user_id, claimed.id)
            if current is None or current.status != "completed" or current.result_analysis_id is None:
                return claimed
            snapshot, _ = self.runtime._authorized_snapshot(claimed.user_id, claimed.repository_id)
            if snapshot.commit_sha != claimed.commit_sha:
                return claimed
            if self.runtime.rag_index is not None:
                try:
                    self.runtime._index_material(claimed.user_id, claimed.repository_id,
                                                 claimed.commit_sha)
                except Exception:
                    logger.warning("ariadne_rag_index_unavailable", extra={"job_id": claimed.id})
            key = self.runtime._cache_key(claimed.user_id, snapshot)
            with self.runtime._connect() as connection:
                cache = AnalysisCache(connection, lambda user, repo:
                                      self.runtime._scope(user, repo).commit_sha == snapshot.commit_sha)
                cache.put(key, current.result_analysis_id, ttl_seconds=3600)
        except Exception:
            # Cache publication is best effort; the durable job/result is authoritative.
            pass
        return claimed
