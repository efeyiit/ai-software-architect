"""T13 checks real parser, T11, and T12 results without executing target code."""

import pytest

from app.ai.refactoring import analyze_refactoring
from app.analyzers.architecture import analyze_architecture
from app.analyzers.dependencies import analyze_dependencies
from app.analyzers.static_quality import QualityThresholds, analyze_static_quality
from app.parsers.python import parse_file
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp


def _pipeline(sources, *, thresholds=QualityThresholds()):
    structures = [parse_file(path, source) for path, source in sources.items()]
    graph = analyze_dependencies(structures)
    quality = analyze_static_quality(structures, sources, graph, thresholds)
    architecture = analyze_architecture(structures, graph)
    return structures, quality, architecture


def test_srp_candidate_separates_observed_evidence_from_suggested_split():
    sources = {
        "application/user_service.py": (
            "class UserService:\n"
            "    def charge_payment(self): pass\n"
            "    def refund_payment(self): pass\n"
            "    def send_email(self): pass\n"
            "    def notify_email(self): pass\n"
        ),
    }
    structures, quality, architecture = _pipeline(
        sources, thresholds=QualityThresholds(class_methods=3)
    )
    assert any(item.issue_type == "large_class" for item in quality)
    report = analyze_refactoring(structures, quality, architecture)
    assert len(report.evidence) >= 6
    assert {item.kind for item in report.evidence} >= {"class", "method", "quality"}
    assert len(report.recommendations) == 1
    recommendation = report.recommendations[0]
    assert recommendation.principle == "srp"
    assert recommendation.certainty == "candidate"
    assert recommendation.origin == "deterministic"
    assert recommendation.location.path == "application/user_service.py"
    assert recommendation.location.start_line == 1
    assert {part.responsibility for part in recommendation.extractions} == {"payments", "notifications"}
    assert len(recommendation.evidence_ids) >= 5
    assert all(item.source == "static" for item in quality)
    assert report.ai_status == "unavailable"


def test_names_in_comments_and_single_role_class_do_not_create_solid_claim():
    sources = {"src/service.py": (
        "# charge_payment send_email\n"
        "class PaymentService:\n"
        "    def charge_payment(self): pass\n"
        "    def refund_payment(self): pass\n"
    )}
    structures, quality, architecture = _pipeline(sources)
    report = analyze_refactoring(structures, quality, architecture)
    assert report.recommendations == []
    assert not any(item.kind == "method" and "email" in item.description for item in report.evidence)


def test_architecture_is_context_only_and_insufficient_hypotheses_are_not_claimed():
    sources = {
        "presentation/api.py": "from application.service import run\ndef serve(): run()\n",
        "application/service.py": "from domain.entity import Entity\ndef run(): Entity()\n",
        "domain/entity.py": "class Entity: pass\n",
    }
    structures, quality, architecture = _pipeline(sources)
    report = analyze_refactoring(structures, quality, architecture)
    assert report.recommendations == []
    assert any(item.architecture == "layered" for item in report.architecture_context)
    assert all(item.assessment in {"supported", "mixed"} for item in report.architecture_context)
    assert any(item.kind == "architecture" for item in report.evidence)


def test_foreign_quality_or_architecture_locations_are_rejected():
    first, quality, architecture = _pipeline({"src/a.py": "class A: pass\n"})
    other, other_quality, other_architecture = _pipeline({
        "presentation/b.py": "from application.service import run\nclass B:\n    def charge_payment(self): pass\n    def refund_payment(self): run()\n",
        "application/service.py": "from domain.entity import Entity\ndef run(): Entity()\n",
        "domain/entity.py": "class Entity: pass\n",
    }, thresholds=QualityThresholds(class_methods=1))
    assert other_quality
    with pytest.raises(ValueError, match="quality finding"):
        analyze_refactoring(first, other_quality, architecture)
    with pytest.raises(ValueError, match="architecture evidence"):
        analyze_refactoring(first, quality, other_architecture)
    assert other


def test_broken_file_is_skipped_and_duplicate_paths_rejected():
    broken = parse_file("src/broken.py", "def broken(:\n")
    report = analyze_refactoring([broken], [], analyze_architecture([broken]))
    assert report.evidence == [] and report.recommendations == []
    with pytest.raises(ValueError, match="duplicate"):
        analyze_refactoring([broken, broken], [], analyze_architecture([broken]))


@pytest.mark.parametrize(("path", "source", "parser"), [
    ("src/Service.ts", "class Service { chargePayment() {} sendEmail() {} }", parse_typescript),
    ("src/Service.java", "class Service { void chargePayment() {} void sendEmail() {} }", parse_java),
    ("src/Service.cs", "class Service { void ChargePayment() {} void SendEmail() {} }", parse_csharp),
    ("src/service.cpp", "class Service { public: void chargePayment() {} void sendEmail() {} };", parse_cpp),
])
def test_other_real_parsers_can_supply_srp_candidates(path, source, parser):
    structure = parser(path, source)
    assert structure.errors == []
    graph = analyze_dependencies([structure])
    quality = analyze_static_quality([structure], {path: source}, graph)
    architecture = analyze_architecture([structure], graph)
    report = analyze_refactoring([structure], quality, architecture)
    assert len(report.recommendations) == 1
    assert {part.responsibility for part in report.recommendations[0].extractions} == {
        "payments", "notifications"
    }
