"""Read-only public repo acceptance through real local retrieval and chat.

Run inside the launcher child environment while the one E5 worker is ready.
No repository source or generated answer is executed.
"""

import json
import hashlib
from pathlib import Path
import subprocess

from qdrant_client import QdrantClient

from app.local_inference import (LocalAnswerProvider, LocalEmbeddingProvider,
                                 runtime_health)
from app.rag.chat import RepositoryChat
from app.rag.indexing import AuthorizedScope, QdrantIndex
from app.services.github_public.service import (GitHubPublicService, LANGUAGES,
                                                RepositoryFile, RepositorySnapshot)


REPO = "https://github.com/efeyiit/ariadne"
SHA = "85bd9826539a4865f059c2671ba5041d05e4cb28"
OWNER = "acceptance-public-owner"
LOCAL_ID = "acceptance-public-repository"
QUESTIONS = (
    ("purpose_tr", "Bu depo ne yapıyor?", "README.md"),
    ("code_tr", "SourceLocation sınıfında hangi alanlar var?",
     "backend/app/contracts/analysis.py"),
    ("status_tr", "README'ye göre projenin mevcut uygulama durumu nedir?",
     "README.md"),
    ("validation_tr", "SourceLocation path doğrulaması hangi yolları reddeder?",
     "backend/app/contracts/analysis.py"),
)
OUTPUT = Path(__file__).resolve().parents[3] / "training" / "reports" / "public-repo-live-acceptance.json"
ROOT = Path(__file__).resolve().parents[3]


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                            check=True)
    return result.stdout


def pinned_public_snapshot():
    """Use already-fetched Git objects after verifying the SHA against origin."""
    tree_sha = git("rev-parse", SHA + "^{tree}").decode().strip()
    files, blobs = [], {}
    for line in git("ls-tree", "-r", "-l", SHA).decode("utf-8").splitlines():
        metadata, _, path = line.partition("\t")
        _, kind, blob_sha, size_text = metadata.split()
        if kind != "blob":
            continue
        size = int(size_text)
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        language = LANGUAGES.get(suffix)
        included = language is not None and size <= 512_000
        files.append(RepositoryFile(path, blob_sha, size, language, included,
                                    None if included else "unsupported_type"))
        blobs[path] = (blob_sha, size)
    snapshot = RepositorySnapshot(
        "public-git-object:efeyiit/ariadne", REPO, "ariadne", "main", SHA,
        tree_sha, tuple(files), (), ())
    public = GitHubPublicService()
    code_paths = [item.path for item in snapshot.included_files]
    document_paths = [item.path for item in public.document_files(snapshot)]
    texts = {}
    for path in set(code_paths + document_paths):
        raw = git("show", f"{SHA}:{path}")
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if (digest, len(raw)) != blobs[path]:
            raise RuntimeError("pinned local Git blob verification failed")
        texts[path] = raw.decode("utf-8")
    return snapshot, {p: texts[p] for p in code_paths}, {
        p: texts[p] for p in document_paths}


class RecordingProvider:
    execution_location = "local"

    def __init__(self, provider):
        self.provider = provider
        self.prompt = None
        self.raw = None

    def answer(self, prompt):
        self.prompt = prompt
        self.raw = self.provider.answer(prompt)
        return self.raw


def main():
    health = runtime_health()
    if health.get("embedding_model_id") != "intfloat/multilingual-e5-small":
        raise RuntimeError("running worker is not the pinned multilingual E5 version")
    worker_source = ROOT / "training" / "local_runtime_server.py"
    local_worker_hash = hashlib.sha256(worker_source.read_bytes()).hexdigest()
    if health.get("runtime_code_sha256") != local_worker_hash:
        raise RuntimeError("running worker code differs from the tested local source")
    snapshot, code, documents = pinned_public_snapshot()
    if "README.md" not in documents:
        raise RuntimeError("README document is not available to the index")
    scope = AuthorizedScope(OWNER, LOCAL_ID, snapshot.repository_id, SHA, False)
    resolve = lambda caller, repo: scope if (caller, repo) == (OWNER, LOCAL_ID) else None
    index = QdrantIndex(QdrantClient(":memory:"), resolve, LocalEmbeddingProvider())
    indexed = index.index_snapshot(OWNER, LOCAL_ID, snapshot, code,
                                   document_texts=documents)
    recorder = RecordingProvider(LocalAnswerProvider())
    chat = RepositoryChat(index, recorder, max_hits=3, max_context_chars=5000)
    cases = []
    for case_id, question, expected in QUESTIONS:
        hits = index.search(OWNER, LOCAL_ID, question, limit=50)
        recorder.prompt = None
        recorder.raw = None
        answer = chat.ask(OWNER, LOCAL_ID, question)
        cases.append({
            "id": case_id, "question": question, "expected_source": expected,
            "retrieval": [{"path": hit.chunk.location.path,
                           "start_line": hit.chunk.location.start_line,
                           "end_line": hit.chunk.location.end_line,
                           "kind": hit.chunk.kind, "score": hit.score}
                          for hit in hits],
            "provider_received_evidence": [
                {"id": e.id, "path": e.path, "start_line": e.start_line,
                 "end_line": e.end_line, "text_preview": e.text[:180]}
                for e in recorder.prompt.evidence] if recorder.prompt else [],
            "provider_output": recorder.raw.model_dump(mode="json") if recorder.raw else None,
            "chat_status": answer.status, "chat_answer": answer.answer,
            "verified_citations": [
                {"path": c.path, "start_line": c.start_line, "end_line": c.end_line,
                 "commit_sha": c.commit_sha, "quote": c.quote}
                for claim in answer.claims for c in claim.citations],
        })
        print(f"{case_id}: top={hits[0].chunk.location.path if hits else 'none'} "
              f"status={answer.status}", flush=True)
    result = {"repository": REPO, "commit_sha": SHA,
              "source_method": "pinned local Git objects; remote HEAD checked previously; no live GitHub API or OAuth claim",
              "runtime_health": health,
              "embedding_model_id": index.embedding.model_id,
              "indexed_chunks": indexed, "document_paths": sorted(documents),
              "cases": cases}
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    if any(not case["retrieval"] or case["retrieval"][0]["path"] != case["expected_source"]
           or case["chat_status"] != "answered"
           or not any(c["path"] == case["expected_source"] for c in case["verified_citations"])
           for case in cases):
        raise SystemExit("public-repository Turkish acceptance did not meet all criteria")


if __name__ == "__main__":
    main()
