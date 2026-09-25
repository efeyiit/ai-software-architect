"""T22 worker handler adapter; richer role output remains with T25 reporting."""

from collections.abc import Callable

from app.contracts.analysis import AnalysisResult
from app.jobs.worker import JobContext, JobFailure

from .coordinator import Coordinator, OrchestrationReport, ScopeChanged, SnapshotMaterial


def to_analysis_result(report: OrchestrationReport, analysis_id: str) -> AnalysisResult:
    """Preserve every T24 role result in the shared v2 wire contract.

    Cancellation is controlled by T22's cancellation transition, never persisted
    as a completed analysis. Errors use stable codes without source text.
    """
    errors = [{"code": state.error_code or "ROLE_FAILED",
               "message": f"{state.role} analysis {state.status}.",
               "retryable": state.status == "timed_out", "location": None}
              for state in report.roles if state.status != "succeeded"]
    findings = [item.finding.model_copy(update={"id": item.id}).model_dump(mode="json")
                for item in report.items if item.finding is not None]
    return AnalysisResult.model_validate({
        "schema_version": 2, "analysis_id": analysis_id,
        "snapshot": report.snapshot.model_dump(mode="json"),
        "status": report.status, "partial": report.status == "partial",
        "ai_status": report.ai_status, "findings": findings, "errors": errors,
        "roles": [state.model_dump(mode="json") for state in report.roles],
        "items": [item.model_dump(mode="json") for item in report.items],
        "conflicts": [item.model_dump(mode="json") for item in report.conflicts],
        "dependencies": report.dependency_graph.model_dump(mode="json") if report.dependency_graph else None,
        "architecture": report.architecture.model_dump(mode="json") if report.architecture else None,
        "testing": report.testing.model_dump(mode="json") if report.testing else None,
        "refactoring": report.refactoring.model_dump(mode="json") if report.refactoring else None,
        "documentation": report.documentation.model_dump(mode="json") if report.documentation else None,
    })


def make_job_handler(coordinator: Coordinator,
                     load_material: Callable[[str, str, str], SnapshotMaterial | None]
                     ) -> Callable[[JobContext], AnalysisResult]:
    """Load exactly the claimed owner's commit; never acknowledge partial as success."""
    def handle(context: JobContext) -> AnalysisResult:
        job = context.job
        material = load_material(job.user_id, job.repository_id, job.commit_sha)
        if (material is None or material.snapshot.repository_id != job.repository_id
                or material.snapshot.commit_sha != job.commit_sha):
            raise JobFailure("SNAPSHOT_UNAVAILABLE", retryable=False)
        try:
            report = coordinator.run(job.user_id, material, context.should_stop)
        except ScopeChanged as exc:
            raise JobFailure("SCOPE_CHANGED", retryable=False) from exc
        except ValueError as exc:
            raise JobFailure("INVALID_SNAPSHOT", retryable=False) from exc
        return to_analysis_result(report, job.id)
    return handle
