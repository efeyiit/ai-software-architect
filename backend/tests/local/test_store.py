import sqlite3

import pytest
from pydantic import ValidationError

from app.local.models import LocalSnapshot, StoredJob
from app.local.store import LocalStore


def snapshot(revision="a", text="print('hello')"):
    return LocalSnapshot(repository_id="repo-1", snapshot_id="local:" + revision * 64,
                         name="Example", sources={"main.py": text})


def test_sources_and_report_survive_reopening(tmp_path):
    path = tmp_path / "data" / "ariadne.sqlite3"
    first = snapshot()
    LocalStore(path).save_snapshot(first)
    LocalStore(path).save_analysis("report-1", first.repository_id, first.snapshot_id, {"status": "succeeded"})
    reopened = LocalStore(path)
    assert reopened.load_snapshot("repo-1", first.snapshot_id) == first
    assert reopened.load_analysis("report-1")["report"] == {"status": "succeeded"}
    assert reopened.list_repositories()[0]["snapshot_id"] == first.snapshot_id


def test_reimport_preserves_old_sources_and_rejects_overwrite(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    old, new = snapshot(), snapshot("b", "print('changed')")
    store.save_snapshot(old)
    store.save_snapshot(new)
    assert store.load_snapshot("repo-1", old.snapshot_id) == old
    assert store.list_repositories()[0]["snapshot_id"] == new.snapshot_id
    with pytest.raises(ValueError, match="immutable"):
        store.save_snapshot(snapshot(text="overwrite"))
    assert store.list_repositories()[0]["snapshot_id"] == new.snapshot_id


def test_foreign_key_failure_rolls_back(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_analysis("bad", "missing", "local:" + "a" * 64, {})
    assert store.load_analysis("bad") is None
    assert store.list_repositories() == []


def test_only_unfinished_jobs_recovered(tmp_path):
    path = tmp_path / "data.sqlite3"
    store = LocalStore(path)
    source = snapshot()
    store.save_snapshot(source)
    for state in ("queued", "running", "succeeded", "cancelled"):
        store.save_job(StoredJob(job_id=state, repository_id=source.repository_id,
                                snapshot_id=source.snapshot_id, status=state))
    reopened = LocalStore(path)
    assert reopened.recover_interrupted_jobs() == 2
    assert reopened.recover_interrupted_jobs() == 0
    assert reopened.load_job("running").status == "failed"
    assert reopened.load_job("running").error_code == "INTERRUPTED"
    assert reopened.load_job("succeeded").status == "succeeded"
    assert reopened.load_job("cancelled").status == "cancelled"


def test_no_repository_or_snapshot_aliasing(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    source = snapshot()
    store.save_snapshot(source)
    assert store.load_snapshot("other", source.snapshot_id) is None
    assert store.load_snapshot(source.repository_id, "local:" + "b" * 64) is None


def test_job_cannot_be_rebound_to_another_snapshot(tmp_path):
    store = LocalStore(tmp_path / "data.sqlite3")
    old, new = snapshot(), snapshot("b")
    store.save_snapshot(old)
    store.save_snapshot(new)
    job = StoredJob(job_id="one", repository_id="repo-1", snapshot_id=old.snapshot_id, status="queued")
    store.save_job(job)
    with pytest.raises(ValueError, match="identity"):
        store.save_job(job.model_copy(update={"snapshot_id": new.snapshot_id}))
    assert store.load_job("one") == job


@pytest.mark.parametrize("updates", [
    {"snapshot_id": "a" * 40}, {"sources": {"../secret.py": "secret"}},
    {"sources": {"C:/secret.py": "secret"}}, {"sources": {"a\\b.py": "text"}},
])
def test_invalid_local_identity_or_path_is_rejected(updates):
    with pytest.raises(ValidationError):
        LocalSnapshot.model_validate(snapshot().model_dump() | updates)
