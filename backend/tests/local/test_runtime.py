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
    assert not runtime._stop
    restarted = LocalRuntime(LocalStore(path))
    try:
        assert restarted.analyze(source.repository_id, source.snapshot_id).job_id == completed.job_id
    finally:
        restarted.close()


def test_failed_worker_releases_active_slot_and_can_retry(tmp_path, monkeypatch):
    from app.local import runtime as module
    def broken_material(source):
        raise ValueError('invalid material')
    monkeypatch.setattr(module, 'material_for', broken_material)
    store = LocalStore(tmp_path / 'data.sqlite3')
    source = import_files('Broken', [UploadedSource(path='main.py', content='x = 1')])
    store.save_snapshot(source)
    runtime = LocalRuntime(store)
    try:
        first = runtime.analyze(source.repository_id, source.snapshot_id)
        deadline = monotonic() + 10
        while store.load_job(first.job_id).status in ('queued', 'running') and monotonic() < deadline:
            sleep(.02)
        assert store.load_job(first.job_id).status == 'failed'
        with runtime._lock:
            assert first.job_id not in runtime._stop
        assert runtime.analyze(source.repository_id, source.snapshot_id).job_id != first.job_id
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

def test_cancelled_queue_slots_remain_bounded_and_terminal_jobs_can_retry(tmp_path):
    import pytest
    class HeldPool:
        def submit(self, *args):
            pass
        def shutdown(self, **kwargs):
            pass
    store = LocalStore(tmp_path / 'data.sqlite3')
    runtime = LocalRuntime(store)
    runtime._pool.shutdown()
    runtime._pool = HeldPool()
    jobs = []
    for i in range(9):
        source = import_files(str(i), [UploadedSource(path='main.py', content=f'x = {i}')])
        store.save_snapshot(source)
        if i == 8:
            with pytest.raises(ValueError, match='queue is full'):
                runtime.analyze(source.repository_id, source.snapshot_id)
        else:
            job = runtime.analyze(source.repository_id, source.snapshot_id)
            jobs.append(job)
            runtime.cancel(job.job_id)
    job = jobs[0]
    job.status = 'cancelled'
    store.save_job(job)
    retried = runtime.analyze(job.repository_id, job.snapshot_id)
    assert retried.job_id != job.job_id
    runtime.close()


def test_submission_failure_does_not_leave_a_queued_job_or_active_slot(tmp_path):
    import pytest
    class RejectedPool:
        def submit(self, *args):
            raise RuntimeError('executor unavailable')
        def shutdown(self, **kwargs):
            pass
    store = LocalStore(tmp_path / 'data.sqlite3')
    source = import_files('Example', [UploadedSource(path='main.py', content='x = 1')])
    store.save_snapshot(source)
    runtime = LocalRuntime(store)
    runtime._pool.shutdown()
    runtime._pool = RejectedPool()
    try:
        with pytest.raises(RuntimeError, match='executor unavailable'):
            runtime.analyze(source.repository_id, source.snapshot_id)
        assert not runtime._stop
        assert store.latest_job(source.repository_id, source.snapshot_id).status == 'failed'
    finally:
        runtime.close()
