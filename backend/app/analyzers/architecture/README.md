# Architecture hypotheses (T12)

`analyze_architecture(structures, graph=None)` accepts the five parser modules'
`FileStructure` results. It uses T10's `analyze_dependencies` output, building the
graph when one is not supplied. It reads parsed structures only and never opens
or executes repository files. A supplied graph must contain the same file paths.
The caller must keep the structures and graph tied to one repository commit:
their current types carry neither repository ID nor SHA.

The report lists MVC, layered, Clean, hexagonal, microservices, modular
monolith, and event driven hypotheses in a stable order. Each has an assessment
(`supported`, `mixed`, or `insufficient`), an ordinal evidence strength (`low`,
`medium`, `high`), source locations for reasons and contradictions, and explicit
uncertainties. These labels are **not calibrated probabilities**. `primary` is
set only when exactly one hypothesis is supported; otherwise the summary is
`mixed` or `unknown`. A missing edge never becomes evidence.

Role paths locate candidates, but support requires resolved T10 import/call/
inheritance edges in the expected direction. Reverse dependencies provide
counterevidence. Service and module hypotheses additionally require separate
connected units plus their expected entry point topology. The service label
stays low strength without process or deployment evidence. Event flow requires
resolved publish and subscribe calls into an event component, and cannot prove
broker delivery or asynchrony. Overlapping patterns can both be supported.

This is a deterministic, explainable static baseline; no LLM key is needed.
Future AI interpretation must remain separate from these verified graph facts.
The shared `AnalysisResult` has no architecture field yet, so API, persistence,
and UI mapping belong to the later integration owner. A later evaluation set
is needed before treating evidence strength as statistically calibrated.

Focused verification from `backend/`:

```text
uv run --no-sync pytest -q tests/architecture
```

The fixtures use the real Python parser and T10 graph for positive, missing,
and contradictory dependencies, including source locations and graph mismatch.
