"""Architecture fixtures use real parsers and the T10 dependency resolver."""

import pytest

from app.analyzers.architecture import analyze_architecture
from app.analyzers.dependencies import analyze_dependencies
from app.parsers import python


def parsed(sources):
    structures = [python.parse_file(path, source) for path, source in sources.items()]
    assert all(not item.errors for item in structures)
    return structures


def hypothesis(report, name):
    return next(item for item in report.hypotheses if item.architecture == name)


def test_clean_and_layered_have_source_linked_directional_evidence():
    structures = parsed({
        "presentation/endpoint.py": "from application.service import handle\ndef endpoint(): handle()\n",
        "application/service.py": "from domain.entity import Entity\ndef handle(): Entity()\n",
        "domain/entity.py": "class Entity: pass\n",
        "infrastructure/store.py": "from domain.entity import Entity\ndef load(): Entity()\n",
    })
    graph = analyze_dependencies(structures)
    report = analyze_architecture(structures, graph)
    assert report.summary == "mixed" and report.primary is None
    clean = hypothesis(report, "clean")
    assert clean.assessment == "supported" and clean.confidence == "high"
    assert {item.location.path for item in clean.reasons} == {
        "presentation/endpoint.py", "application/service.py", "infrastructure/store.py"
    }
    assert hypothesis(report, "layered").assessment == "supported"


def test_mvc_and_hexagonal_need_edges_beyond_folder_names():
    mvc = analyze_architecture(parsed({
        "controllers/shop.py": "from models.item import Item\nfrom views.page import render\ndef show(): Item(); render()\n",
        "models/item.py": "class Item: pass\n",
        "views/page.py": "def render(): pass\n",
    }))
    assert hypothesis(mvc, "mvc").assessment == "supported"
    hexagonal = analyze_architecture(parsed({
        "adapters/http.py": "from ports.gateway import send\ndef serve(): send()\n",
        "application/usecase.py": "from ports.gateway import send\ndef run(): send()\n",
        "ports/gateway.py": "def send(): pass\n",
    }))
    assert hypothesis(hexagonal, "hexagonal").assessment == "supported"
    empty = analyze_architecture(parsed({
        "controllers/shop.py": "def show(): pass\n", "models/item.py": "class Item: pass\n",
        "views/page.py": "def render(): pass\n",
    }))
    assert empty.summary == "unknown"
    assert hypothesis(empty, "mvc").assessment == "insufficient"


def test_reverse_dependency_is_counterevidence_and_unresolved_is_ignored():
    report = analyze_architecture(parsed({
        "presentation/endpoint.py": "from application.service import handle\ndef endpoint(): handle()\n",
        "application/service.py": "from domain.entity import Entity\ndef handle(): Entity()\n",
        "domain/entity.py": "from presentation.endpoint import endpoint\nclass Entity: pass\n",
        "infrastructure/store.py": "from domain.entity import Entity\ndef load(): Entity()\n",
    }))
    clean = hypothesis(report, "clean")
    assert clean.assessment == "mixed"
    assert clean.contradictions[0].location.path == "domain/entity.py"
    unresolved = analyze_architecture(parsed({
        "presentation/endpoint.py": "from application.missing import handle\n",
        "application/service.py": "from domain.absent import Entity\n",
        "domain/entity.py": "class Entity: pass\n",
    }))
    assert hypothesis(unresolved, "layered").assessment == "insufficient"


def test_service_and_module_topologies_are_tentative():
    services = analyze_architecture(parsed({
        "services/orders/main.py": "from .core import run\nrun()\n",
        "services/orders/core.py": "def run(): pass\n",
        "services/payments/main.py": "from .core import run\nrun()\n",
        "services/payments/core.py": "def run(): pass\n",
    }))
    service = hypothesis(services, "microservices")
    assert (service.assessment, service.confidence) == ("supported", "low")
    assert "Deployment" in service.uncertainties[0]
    modules = analyze_architecture(parsed({
        "main.py": "from modules.orders.api import run as orders\nfrom modules.payments.api import run as payments\norders(); payments()\n",
        "modules/orders/api.py": "from .core import work\ndef run(): work()\n",
        "modules/orders/core.py": "def work(): pass\n",
        "modules/payments/api.py": "from .core import work\ndef run(): work()\n",
        "modules/payments/core.py": "def work(): pass\n",
    }))
    assert hypothesis(modules, "modular_monolith").assessment == "supported"


def test_cross_service_dependency_conflicts_with_service_separation():
    report = analyze_architecture(parsed({
        "services/orders/main.py": "from .core import run\nfrom services.payments.core import pay\nrun(); pay()\n",
        "services/orders/core.py": "def run(): pass\n",
        "services/payments/main.py": "from .core import pay\npay()\n",
        "services/payments/core.py": "def pay(): pass\n",
    }))
    service = hypothesis(report, "microservices")
    assert service.assessment == "mixed"
    assert service.contradictions[0].location.path == "services/orders/main.py"


def test_event_flow_requires_resolved_publish_and_subscribe_calls():
    report = analyze_architecture(parsed({
        "events/bus.py": "def publish(): pass\ndef subscribe(): pass\n",
        "producer.py": "from events.bus import publish\ndef send(): publish()\n",
        "consumer.py": "from events.bus import subscribe\ndef listen(): subscribe()\n",
    }))
    event = hypothesis(report, "event_driven")
    assert event.assessment == "supported"
    assert {item.location.path for item in event.reasons} == {"producer.py", "consumer.py"}
    unresolved = analyze_architecture(parsed({
        "events/bus.py": "def publish(): pass\n",
        "producer.py": "from events.bus import publish\ndef send(): publish()\n",
        "consumer.py": "from events.missing import subscribe\ndef listen(): subscribe()\n",
    }))
    assert hypothesis(unresolved, "event_driven").assessment == "insufficient"


def test_graph_snapshot_mismatch_is_rejected():
    first = parsed({"one.py": "def one(): pass\n"})
    second = parsed({"two.py": "def two(): pass\n"})
    with pytest.raises(ValueError, match="snapshot"):
        analyze_architecture(first, analyze_dependencies(second))
