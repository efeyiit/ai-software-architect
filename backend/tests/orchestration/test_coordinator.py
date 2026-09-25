"""T24 exercises real parser, graph, quality, security, test and draft modules."""

from hashlib import sha1
from threading import Event
from time import sleep
from types import SimpleNamespace

import pytest

from app.ai.orchestration import Coordinator, ScopeChanged, SnapshotMaterial, make_job_handler, to_analysis_result
from app.ai.orchestration.coordinator import RoleState, _merge
from app.analyzers.architecture.detector import ArchitectureEvidence, ArchitectureHypothesis, ArchitectureReport
from app.contracts.analysis import AnalysisFinding, SourceLocation
from app.jobs.worker import JobFailure
from app.services.github_public.service import RepositoryFile, RepositorySnapshot


def _blob(text):
    raw = text.encode()
    return sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def _material():
    sources = {
        "application/user_service.py": (
            "class UserService:\n"
            "    def charge_payment(self): pass\n"
            "    def send_email(self): pass\n"
            "password = 'unsafe-hardcoded-value'\n"),
        "tests/test_user_service.py": (
            "from application.user_service import UserService\n"
            "def test_user_service(): assert UserService()\n"),
    }
    documents = {"pyproject.toml": '[project]\nrequires-python = ">=3.12"\n'}
    files = tuple(RepositoryFile(path=path, blob_sha=_blob(text),
                                 size=len(text.encode()), language="python" if path.endswith(".py") else None,
                                 included=path in sources, exclusion_reason=None if path in sources else "document")
                  for path, text in {**sources, **documents}.items())
    snapshot = RepositorySnapshot(repository_id="repo-1", github_url="https://github.com/a/b",
                                  name="b", default_branch="main", commit_sha="a" * 40,
                                  tree_sha="b" * 40, files=files, languages=(("python", 2),),
                                  frameworks=())
    return SnapshotMaterial(snapshot, sources, documents, {})


def test_real_roles_merge_source_linked_results_without_ai_claim():
    material = _material()
    coordinator = Coordinator(lambda caller, repo: material.snapshot)
    report = coordinator.run("owner", material)
    assert report.status == "succeeded"
    assert report.ai_status == "unavailable"
    assert [role.status for role in report.roles] == ["succeeded"] * 5
    assert report.architecture is not None
    assert report.dependency_graph is not None
    assert any(edge.status == "resolved" for edge in report.dependency_graph.edges)
    assert report.testing.services[0].status == "associated_with_test"
    assert report.refactoring.recommendations[0].certainty == "candidate"
    assert report.documentation.snapshot.commit_sha == "a" * 40
    assert any(item.kind == "static_finding" and item.finding.issue_type for item in report.items)
    assert all(item.location is None or item.location.path in material.sources | material.document_sources
               for item in report.items)


def test_wrong_blob_and_revoked_scope_fail_closed():
    material = _material()
    bad = SnapshotMaterial(material.snapshot, {**material.sources,
                           "application/user_service.py": "changed"}, material.document_sources, {})
    with pytest.raises(ValueError, match="blob"):
        Coordinator(lambda caller, repo: material.snapshot).run("owner", bad)
    with pytest.raises(ScopeChanged):
        Coordinator(lambda caller, repo: None).run("owner", material)


def test_scope_change_after_analysis_rejects_entire_report():
    material = _material()
    calls = 0
    def current(caller, repo):
        nonlocal calls
        calls += 1
        return material.snapshot if calls < 4 else None
    with pytest.raises(ScopeChanged):
        Coordinator(current).run("owner", material)


def test_duplicate_merge_is_stable_and_conflict_preserves_variants():
    location = SourceLocation(path="src/a.py", start_line=2, end_line=2)
    first = AnalysisFinding(id="one", source="static", issue_type="risk",
                            severity="high", location=location, description="First", suggestion=None)
    second = first.model_copy(update={"id": "two", "description": "Second"})
    items, conflicts = _merge({"security": [first, first, second]}, [])
    assert len(items) == 2
    assert len(conflicts) == 1
    assert conflicts[0].item_ids == [item.id for item in items]


def test_architecture_counterevidence_remains_visible():
    location = SourceLocation(path="src/a.py", start_line=2, end_line=2)
    report = ArchitectureReport(hypotheses=[ArchitectureHypothesis(
        architecture="layered", assessment="mixed", confidence="low",
        reasons=[ArchitectureEvidence(description="forward dependency", location=location)],
        contradictions=[ArchitectureEvidence(description="reverse dependency", location=location)],
        uncertainties=[])], summary="mixed", primary=None)
    items, conflicts = _merge({"architect": report}, [])
    assert {item.kind for item in items} == {"architecture_support", "architecture_contradiction"}
    assert len(conflicts) == 1
    assert conflicts[0].key == "architecture:layered"


def test_timeout_and_cancel_are_explicit(monkeypatch):
    material = _material()
    from app.ai.orchestration import coordinator as module
    original = module.analyze_security
    def slow(*args):
        sleep(.1)
        return original(*args)
    monkeypatch.setattr(module, "analyze_security", slow)
    report = Coordinator(lambda caller, repo: material.snapshot,
                         timeout_seconds=.01).run("owner", material)
    assert report.status == "partial"
    assert any(role.status == "timed_out" for role in report.roles)
    assert report.ai_status == "unavailable"
    stopped = Event()
    stopped.set()
    cancelled = Coordinator(lambda caller, repo: material.snapshot).run(
        "owner", material, stopped.is_set)
    assert cancelled.status == "cancelled"
    assert cancelled.items == []
    assert cancelled.dependency_graph is None


def test_t22_handler_returns_shared_contract_only_on_full_success(monkeypatch):
    material = _material()
    context = SimpleNamespace(job=SimpleNamespace(id="job-1", user_id="owner",
                               repository_id="repo-1", commit_sha="a" * 40),
                              should_stop=lambda: False)
    coordinator = Coordinator(lambda caller, repo: material.snapshot)
    handler = make_job_handler(coordinator, lambda owner, repo, sha: material)
    result = handler(context)
    assert result.analysis_id == "job-1"
    assert result.snapshot.commit_sha == "a" * 40
    assert result.status == "succeeded"
    assert result.schema_version == 2
    assert result.dependencies is not None
    assert result.roles and result.items
    assert result.findings and all(finding.source == "static" for finding in result.findings)

    from app.ai.orchestration import coordinator as module
    def broken(*args):
        raise RuntimeError("untrusted source text must not leak")
    monkeypatch.setattr(module, "analyze_security", broken)
    partial = handler(context)
    assert partial.status == "partial"
    assert partial.partial is True
    assert any(role.status == "failed" for role in partial.roles)
    assert partial.dependencies is not None
    assert partial.items
    assert partial.model_validate_json(partial.model_dump_json()) == partial


def test_adapter_preserves_report_roundtrip_and_never_completes_cancelled():
    material = _material()
    report = Coordinator(lambda caller, repo: material.snapshot).run("owner", material)
    result = to_analysis_result(report, "analysis-1")
    assert result.dependencies.model_dump() == report.dependency_graph.model_dump()
    assert result.architecture.model_dump() == report.architecture.model_dump()
    assert result.testing.model_dump() == report.testing.model_dump()
    assert result.refactoring.model_dump() == report.refactoring.model_dump()
    assert result.documentation.model_dump() == report.documentation.model_dump()
    assert [item.model_dump() for item in result.items] == [item.model_dump() for item in report.items]
    assert [item.model_dump() for item in result.conflicts] == [item.model_dump() for item in report.conflicts]
    cancelled = Coordinator(lambda caller, repo: material.snapshot).run("owner", material, lambda: True)
    cancelled_result = to_analysis_result(cancelled, "analysis-2")
    assert cancelled_result.status == "cancelled"
    assert cancelled_result.analysis_id == "analysis-2"
    assert len(cancelled_result.roles) == 5
    assert cancelled_result.items == []
    context = SimpleNamespace(job=SimpleNamespace(id="job-cancel", user_id="owner",
                              repository_id="repo-1", commit_sha="a" * 40),
                              should_stop=lambda: True)
    handler = make_job_handler(Coordinator(lambda caller, repo: material.snapshot),
                               lambda owner, repo, sha: material)
    assert handler(context).status == "cancelled"


def test_all_role_failures_remain_failed_with_safe_errors():
    material = _material()
    failed = Coordinator._report(material.snapshot, {},
                                 [RoleState(role=role, status="failed", error_code="ROLE_FAILED")
                                  for role in ("architect", "security", "testing", "refactoring", "documentation")],
                                 [], None)
    result = to_analysis_result(failed, "analysis-failed")
    assert result.status == "failed"
    assert result.partial is False
    assert len(result.errors) == 5
    assert all(error.code == "ROLE_FAILED" for error in result.errors)
    assert result.dependencies is None


def test_coverage_is_accepted_only_from_same_blob():
    material = _material()
    coverage = '<coverage lines-covered="1" lines-valid="2" />'
    file = RepositoryFile(path="coverage.xml", blob_sha=_blob(coverage), size=len(coverage),
                          language=None, included=False, exclusion_reason="coverage")
    snapshot = material.snapshot.__class__(**{**material.snapshot.__dict__,
                                               "files": (*material.snapshot.files, file)})
    current = SnapshotMaterial(snapshot, material.sources, material.document_sources,
                               {"coverage.xml": coverage})
    report = Coordinator(lambda caller, repo: snapshot).run("owner", current)
    assert report.testing.coverage_status == "available"
    assert report.testing.coverage.percent == 50
    bad = SnapshotMaterial(snapshot, material.sources, material.document_sources,
                           {"coverage.xml": coverage + "changed"})
    with pytest.raises(ValueError, match="coverage artifact"):
        Coordinator(lambda caller, repo: snapshot).run("owner", bad)
