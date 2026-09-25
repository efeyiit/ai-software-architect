"""Real Qdrant local filtering and broad-candidate retrieval mechanics.

Vectors here are controlled ranking fixtures, not semantic embeddings.
"""

from hashlib import sha256
from math import sqrt

from qdrant_client import QdrantClient, models

from app.rag.indexing import AuthorizedScope, QdrantIndex


SHA = "a" * 40


class MechanicalVectors:
    model_id = "controlled-ranking-fixture"
    dimension = 3
    execution_location = "local"

    def embed_documents(self, texts):
        raise AssertionError("ranking fixture preloads its own Qdrant vectors")

    def embed_query(self, text):
        return [1.0, 0.0, 0.0]


class RecordingQdrant(QdrantClient):
    def __init__(self):
        super().__init__(":memory:")
        self.query_limit = None

    def query_points(self, collection_name, **kwargs):
        self.query_limit = kwargs["limit"]
        return super().query_points(collection_name, **kwargs)


def point(number, path, text, cosine, *, owner="alice", sha=SHA, kind="document"):
    return models.PointStruct(id=number, vector=[cosine, sqrt(1 - cosine * cosine), 0.0],
        payload={"owner_id": owner, "repository_id": "local-1",
                 "source_repository_id": "github-42", "commit_sha": sha,
                 "private": False, "path": path, "start_line": number,
                 "end_line": number, "text": text,
                 "content_sha256": sha256(text.encode()).hexdigest(),
                 "ordinal": number, "kind": kind})


def fixture():
    client = RecordingQdrant()
    scope = AuthorizedScope("alice", "local-1", "github-42", SHA, False)
    index = QdrantIndex(client, lambda user, repo: scope if (user, repo) ==
                        ("alice", "local-1") else None, MechanicalVectors())
    client.create_collection(index.collection_name,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    points = [point(n, "docs/large-design.md",
                    "- Proje ne yapıyor?\n- Mimari nasıl?\n- Testler nerede?\n"
                    "A repository design section.\n",
                    0.844 - n * 0.001) for n in range(1, 49)]
    points += [
        point(49, "README.md", "Ariadne is a developer tool for exploring a repository.\n", 0.795),
        point(50, "backend/app/contracts/analysis.py",
              "class SourceLocation:\n    path: str\n    start_line: int\n    end_line: int\n",
              0.828, kind="code"),
        point(51, "docs/architecture-decisions.md",
              "Architecture detection uses parsed dependencies.\n", 0.800),
        point(52, "docs/product-roadmap.md", "Future milestones and releases.\n", 0.790),
        point(53, "README.md", "Status: early implementation.\n", 0.760),
        point(54, "backend/app/contracts/analysis.py",
              "SourceLocation rejects absolute and non-normalized paths.\n", 0.810,
              kind="code"),
        point(55, "README.md", "wrong owner's private repository\n", 0.999, owner="bob"),
        point(56, "README.md", "stale SHA repository\n", 0.998, sha="b" * 40),
    ]
    client.upsert(index.collection_name, points=points, wait=True)
    return index, client


def test_broad_pool_reranks_duplicate_document_crowding_without_changing_scope():
    index, client = fixture()
    purpose = index.search("alice", "local-1", "Bu depo ne yapıyor?", limit=3)
    assert purpose[0].chunk.location.path == "README.md"
    assert len({hit.chunk.location.path for hit in purpose}) == 3
    assert client.query_limit <= 128
    assert all(hit.chunk.owner_id == "alice" and hit.chunk.commit_sha == SHA
               for hit in purpose)
    code = index.search("alice", "local-1", "SourceLocation sınıfında hangi alanlar var?",
                        limit=3)
    assert code[0].chunk.location.path == "backend/app/contracts/analysis.py"
    assert code[0].chunk.location.start_line in (50, 54)
    assert {hit.chunk.location.path for hit in code} != {"docs/large-design.md"}


def test_rerank_generalizes_to_status_validation_and_another_subject():
    index, _ = fixture()
    status = index.search("alice", "local-1", "README'ye göre projenin mevcut durumu nedir?",
                          limit=3)
    assert status[0].chunk.location.path == "README.md"
    validation = index.search("alice", "local-1",
                              "SourceLocation path doğrulaması hangi yolları reddeder?",
                              limit=3)
    assert validation[0].chunk.location.path == "backend/app/contracts/analysis.py"
    architecture = index.search("alice", "local-1", "How is architecture detection done?",
                                limit=3)
    assert architecture[0].chunk.location.path == "docs/architecture-decisions.md"


def test_code_operators_and_same_line_faq_answers_keep_lexical_evidence():
    client = RecordingQdrant()
    scope = AuthorizedScope("alice", "local-1", "github-42", SHA, False)
    index = QdrantIndex(client, lambda user, repo: scope if (user, repo) ==
                        ("alice", "local-1") else None, MechanicalVectors())
    client.create_collection(index.collection_name,
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    client.upsert(index.collection_name, points=[
        point(1, "docs/general.md", "Generic process notes.\n", 0.810),
        point(2, "src/branch.ts", "return retry ? fallback : error;\n", 0.790,
              kind="code"),
        point(3, "docs/faq.md",
              "Q: What is cache freshness? A: It checks the current snapshot.\n",
              0.790),
    ], wait=True)
    code = index.search("alice", "local-1", "How does retry fallback work?", limit=1)
    assert code[0].chunk.location.path == "src/branch.ts"
    faq = index.search("alice", "local-1", "What is cache freshness?", limit=1)
    assert faq[0].chunk.location.path == "docs/faq.md"
