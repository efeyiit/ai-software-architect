"""Optional embedded retrieval with explicit repository/content scope."""

from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.local.store import LocalStore
from app.rag.chat.service import ChatPrompt, ChatProviderAnswer, Evidence, INSTRUCTIONS, _redact


class LocalRetrieval:
    def __init__(self, data_dir: Path, store: LocalStore, embedding, answer_provider=None):
        if getattr(embedding, "execution_location", None) != "local" or (answer_provider is not None and getattr(answer_provider, "execution_location", None) != "local"):
            raise ValueError("Only local inference providers are supported")
        self.store, self.embedding, self.provider = store, embedding, answer_provider
        self._lock = RLock()
        self.client = QdrantClient(path=str(data_dir), force_disable_check_same_thread=True)
        self.collection = "local_" + sha256((embedding.model_id + str(embedding.dimension)).encode()).hexdigest()[:20]
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(self.collection, vectors_config=models.VectorParams(size=embedding.dimension, distance=models.Distance.COSINE))

    def close(self):
        with self._lock:
            self.client.close()

    def _source(self, repository_id, snapshot_id):
        source = self.store.load_snapshot(repository_id, snapshot_id)
        if source is None:
            raise KeyError("snapshot not found")
        return source

    @staticmethod
    def _filter(repository_id, snapshot_id):
        return models.Filter(must=[models.FieldCondition(key="repository_id", match=models.MatchValue(value=repository_id)),
                                   models.FieldCondition(key="snapshot_id", match=models.MatchValue(value=snapshot_id))])

    def index_snapshot(self, repository_id: str, snapshot_id: str) -> int:
        with self._lock:
            source = self._source(repository_id, snapshot_id)
            chunks = []
            for path, text in sorted(source.sources.items()):
                lines = text.splitlines()
                for start in range(0, len(lines), 42):
                    selected = lines[start:start + 48]
                    excerpt = _redact("\n".join(selected))[:8000]
                    if excerpt.strip():
                        chunks.append({"repository_id": repository_id, "snapshot_id": snapshot_id, "path": path,
                                       "start_line": start + 1, "end_line": start + len(selected), "text": excerpt})
                    if len(chunks) > 2048:
                        raise ValueError("Optional AI indexing is limited to 2048 source chunks")
            if self.client.count(self.collection, count_filter=self._filter(repository_id, snapshot_id), exact=True).count == len(chunks):
                return len(chunks)
            for start in range(0, len(chunks), 4):
                batch = chunks[start:start + 4]
                vectors = self.embedding.embed_documents([chunk["text"] for chunk in batch])
                if len(vectors) != len(batch):
                    raise ValueError("Embedding count mismatch")
                points = [models.PointStruct(id=str(uuid5(NAMESPACE_URL, f"{repository_id}/{snapshot_id}/{chunk['path']}/{chunk['start_line']}")),
                                             vector=list(vector), payload=chunk) for chunk, vector in zip(batch, vectors, strict=True)]
                self.client.upsert(self.collection, points=points, wait=True)
            return len(chunks)

    def search(self, repository_id: str, snapshot_id: str, question: str) -> list[dict]:
        if not question.strip() or len(question) > 1000:
            raise ValueError("Question must contain 1 to 1000 characters")
        with self._lock:
            self._source(repository_id, snapshot_id)
            if not self.client.count(self.collection, count_filter=self._filter(repository_id, snapshot_id), exact=True).count:
                return []
            result = self.client.query_points(self.collection, query=list(self.embedding.embed_query(question)),
                                             query_filter=self._filter(repository_id, snapshot_id), limit=6, with_payload=True)
            return [point.payload for point in result.points]

    def ask(self, repository_id: str, snapshot_id: str, question: str) -> dict:
        source = self._source(repository_id, snapshot_id)
        unavailable = {"status": "unavailable", "answer": "Local AI is not available. Static analysis remains usable.", "claims": [], "snapshot_id": snapshot_id}
        if self.provider is None:
            return unavailable
        try:
            self.index_snapshot(repository_id, snapshot_id)
            hits = self.search(repository_id, snapshot_id, question)
            evidence = []
            budget = 12000
            for hit in hits:
                text = hit["text"][:budget]
                if not text:
                    break
                evidence.append(Evidence(f"E{len(evidence) + 1}", hit["path"], hit["start_line"], hit["end_line"], source.commit_sha or snapshot_id, text))
                budget -= len(text)
            if not evidence:
                return unavailable | {"status": "no_evidence", "answer": "No source evidence is available for this snapshot."}
            output = ChatProviderAnswer.model_validate(self.provider.answer(ChatPrompt(INSTRUCTIONS, _redact(question), tuple(evidence))))
            known = {item.id: item for item in evidence}
            claims = []
            for claim in output.claims:
                citations = []
                for citation in claim.citations:
                    item = known.get(citation.evidence_id)
                    if item is None or not item.start_line <= citation.start_line <= citation.end_line <= item.end_line:
                        raise ValueError("Citation outside supplied evidence")
                    excerpt = "\n".join(source.sources[item.path].splitlines()[citation.start_line - 1:citation.end_line])
                    if citation.quote not in excerpt or citation.quote not in item.text or _redact(citation.quote) != citation.quote:
                        raise ValueError("Citation quote does not match supplied source")
                    citations.append({"path": item.path, "start_line": citation.start_line, "end_line": citation.end_line,
                                      "quote": citation.quote, "snapshot_id": snapshot_id})
                claims.append({"text": _redact(claim.text), "citations": citations})
            return {"status": "answered" if claims else "no_evidence", "answer": "\n".join(claim["text"] for claim in claims) if claims else "The model did not find enough source evidence to answer this question.",
                    "claims": claims, "snapshot_id": snapshot_id}
        except ValueError:
            return unavailable | {"status": "rejected", "answer": "The model response could not be verified against the selected source."}
        except Exception:
            return unavailable
