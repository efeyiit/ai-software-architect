from time import monotonic, sleep

from app.local.importer import UploadedSource, import_files
from app.local.runtime import LocalRuntime
from app.local.store import LocalStore


def test_real_local_analysis_has_content_identity_and_survives_restart(tmp_path):
    path = tmp_path / "data.sqlite3"
    store = LocalStore(path)
    source = import_files("Example", [UploadedSource(path="main.py", content="import os\n\ndef hello():\n    return 'world'\n")])
    store.save_snapshot(source)
    runtime = LocalRuntime(store)
    try:
        job = runtime.analyze(source.repository_id, source.snapshot_id)
        assert runtime.analyze(source.repository_id, source.snapshot_id).job_id == job.job_id
        deadline = monotonic() + 10
        while store.load_job(job.job_id).status in ("queued", "running") and monotonic() < deadline:
            sleep(.02)
        completed = store.load_job(job.job_id)
        assert completed.status == "succeeded", completed
        report = store.load_analysis(completed.analysis_id)["report"]
        assert report["snapshot"]["snapshot_id"] == source.snapshot_id
        assert report["snapshot"]["commit_sha"] is None
        assert report["ai_status"] == "unavailable"
        assert len(report["roles"]) == 5
        assert "Local snapshot:" in report["documentation"]["readme"]
        assert LocalStore(path).load_analysis(completed.analysis_id)["report"] == report
    finally:
        runtime.close()


def test_public_reader_preserves_real_commit_without_credentials(tmp_path):
    from hashlib import sha1
    import base64
    from app.services.github_public import GitHubPublicService
    raw = b"def hello():\n    return 'public'\n"
    blob = sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    class API:
        def get_json(self, path, max_bytes):
            if path == "/repos/example/project":
                return {"id": 42, "name": "project", "private": False, "default_branch": "main"}
            if "/commits/" in path:
                return {"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}}
            if "/git/trees/" in path:
                return {"truncated": False, "tree": [{"type": "blob", "path": "main.py", "sha": blob, "size": len(raw)}]}
            if "/git/blobs/" in path:
                return {"sha": blob, "encoding": "base64", "content": base64.b64encode(raw).decode()}
            raise AssertionError(path)
    store = LocalStore(tmp_path / "data.sqlite3")
    runtime = LocalRuntime(store)
    try:
        source = runtime.import_github("https://github.com/example/project", GitHubPublicService(API()))
        assert source.commit_sha == "a" * 40
        assert source.source_kind == "github"
        job = runtime.analyze(source.repository_id, source.snapshot_id)
        deadline = monotonic() + 10
        while store.load_job(job.job_id).status in ("queued", "running") and monotonic() < deadline:
            sleep(.02)
        final = store.load_job(job.job_id)
        assert final.status == "succeeded"
        assert store.load_analysis(final.analysis_id)["report"]["snapshot"] == {
            "repository_id": source.repository_id, "commit_sha": "a" * 40}
    finally:
        runtime.close()
