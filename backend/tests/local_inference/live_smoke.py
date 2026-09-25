"""Manual bounded live local-model smoke; only authored synthetic source text."""

import json
from hashlib import sha1
from pathlib import Path

from qdrant_client import QdrantClient

from app.local_inference import (LocalAnswerProvider, LocalEmbeddingProvider,
                                 LocalRuntimeConfigError, runtime_health)
from app.rag.chat import RepositoryChat
from app.rag.indexing import AuthorizedScope, QdrantIndex
from app.services.github_public.service import RepositoryFile, RepositorySnapshot


SHA = "a" * 40
OWNER = "local-demo-user"
REPOSITORY = "local-demo-repository"
SOURCE = "synthetic-repository"
PATH = "src/example.py"
TEXT = "def answer_to_everything():\n    return 42\n"
OUTPUT = Path(__file__).resolve().parents[3] / "training" / "reports" / "local-live-smoke.json"


def main():
    health = runtime_health()
    embedding = LocalEmbeddingProvider()
    provider = LocalAnswerProvider()
    scope = AuthorizedScope(OWNER, REPOSITORY, SOURCE, SHA, False)
    resolve = lambda caller, repository: scope if (caller, repository) == (OWNER, REPOSITORY) else None
    blob = sha1(b"blob " + str(len(TEXT.encode())).encode() + b"\0" + TEXT.encode()).hexdigest()
    snapshot = RepositorySnapshot(SOURCE, "https://example.invalid/synthetic",
                                  "synthetic", "main", SHA, "b" * 40,
                                  (RepositoryFile(PATH, blob, len(TEXT.encode()),
                                                  "Python", True, None),), (), ())
    client = QdrantClient(":memory:")
    index = QdrantIndex(client, resolve, embedding)
    indexed = index.index_snapshot(OWNER, REPOSITORY, snapshot, {PATH: TEXT})
    chat = RepositoryChat(index, provider)
    answer = chat.ask(OWNER, REPOSITORY,
                      "What number does answer_to_everything return?")
    empty = QdrantIndex(QdrantClient(":memory:"), resolve, embedding)
    no_evidence = RepositoryChat(empty, provider).ask(
        OWNER, REPOSITORY, "What number does answer_to_everything return?")
    config_failed = False
    try:
        LocalAnswerProvider(token="")
    except LocalRuntimeConfigError:
        config_failed = True
    report = {
        "health": health,
        "indexed_chunks": indexed,
        "embedding_model_id": embedding.model_id,
        "embedding_dimension": embedding.dimension,
        "answer_status": answer.status,
        "answer": answer.answer,
        "answer_citations": [
            {"path": cited.path, "start_line": cited.start_line,
             "end_line": cited.end_line, "commit_sha": cited.commit_sha,
             "quote": cited.quote}
            for claim in answer.claims for cited in claim.citations
        ],
        "no_evidence_status": no_evidence.status,
        "config_failure_refused": config_failed,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if (answer.status != "answered" or not any(
            c.path == PATH and c.quote in TEXT and c.commit_sha == SHA
            for claim in answer.claims for c in claim.citations)
            or no_evidence.status != "no_evidence" or not config_failed):
        raise SystemExit("live local-model smoke did not meet all conditions")


if __name__ == "__main__":
    main()
