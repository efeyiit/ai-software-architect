"""Source-bound repository summaries. Analyzed source is data, never executed."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, Protocol

from pydantic import Field

from app.contracts.analysis import RepositorySnapshot as SnapshotIdentity, SourceLocation, WireModel
from app.services.github_public.service import RepositorySnapshot


class Citation(WireModel):
    location: SourceLocation
    quote: str | None = Field(default=None, strict=True)


class SummaryClaim(WireModel):
    text: str = Field(min_length=1, max_length=500, strict=True)
    origin: Literal["static", "ai"]
    citations: list[Citation] = Field(min_length=1, max_length=5)


class FileSummary(WireModel):
    path: str
    responsibility: str
    responsibility_citations: list[Citation]
    structural_facts: list[SummaryClaim]
    ai_claims: list[SummaryClaim]
    uncertainties: list[str]


class ProjectSummary(WireModel):
    snapshot: SnapshotIdentity
    files: list[FileSummary]
    main_modules: list[SummaryClaim]
    technologies: list[SummaryClaim]
    purpose: str
    purpose_citations: list[Citation]
    ai_status: Literal["unavailable", "validated", "rejected"]
    uncertainties: list[str]


class ProviderClaim(WireModel):
    path: str
    category: Literal["responsibility", "purpose", "module", "technology"]
    text: str = Field(min_length=1, max_length=500, strict=True)
    citations: list[Citation] = Field(min_length=1, max_length=5)


class ProviderOutput(WireModel):
    claims: list[ProviderClaim] = Field(max_length=100)


class SummaryProvider(Protocol):
    def summarize(self, *, repository_id: str, commit_sha: str,
                  sources: Mapping[str, str]) -> ProviderOutput: ...


class SummaryError(ValueError):
    """Input or provider result crosses the summary evidence boundary."""


_LANGUAGE_SUFFIXES = {
    ".py": "Python", ".pyi": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".cs": "C#", ".cpp": "C++", ".cc": "C++",
    ".cxx": "C++", ".h": "C++", ".hpp": "C++", ".hh": "C++", ".hxx": "C++",
}
_PARSER_SUFFIXES = frozenset(_LANGUAGE_SUFFIXES)
_FRAMEWORK_MARKERS = {
    "manage.py": "Django", "angular.json": "Angular", "next.config.js": "Next.js",
    "next.config.mjs": "Next.js", "next.config.ts": "Next.js",
    "vite.config.ts": "Vite", "vite.config.js": "Vite", "pom.xml": "Maven",
    "build.gradle": "Gradle",
}


def _claim(text: str, path: str, line: int = 1) -> SummaryClaim:
    return SummaryClaim(text=text, origin="static", citations=[Citation(
        location=SourceLocation(path=path, start_line=line, end_line=line))])


def _check_structure(structure: object, paths: set[str]) -> None:
    if structure.path not in paths:
        raise SummaryError("parser output is outside the authorized snapshot")
    for group in (structure.symbols, structure.imports, structure.calls, structure.inheritance,
                  getattr(structure, "exports", ()), getattr(structure, "macro_uncertainties", ())):
        if any(item.location.path != structure.path for item in group):
            raise SummaryError("parser location differs from its file")
    if any(error.location is not None and error.location.path != structure.path
           for error in structure.errors):
        raise SummaryError("parser error location differs from its file")


def _validate_provider(output: ProviderOutput, sources: Mapping[str, str]) -> list[ProviderClaim]:
    validated: list[ProviderClaim] = []
    singleton_claims: set[tuple[str, str]] = set()
    for claim in output.claims:
        if claim.path not in sources:
            raise SummaryError("AI claim targets a file outside the supplied source snapshot")
        if claim.category in {"responsibility", "purpose"}:
            key = (claim.path if claim.category == "responsibility" else "*", claim.category)
            if key in singleton_claims:
                raise SummaryError("AI output has conflicting singleton summary claims")
            singleton_claims.add(key)
        for citation in claim.citations:
            loc = citation.location
            lines = sources.get(loc.path, "").splitlines()
            if (loc.path not in sources or loc.path != claim.path or loc.end_line > len(lines)
                    or not citation.quote or not citation.quote.strip()
                    or citation.quote not in "\n".join(lines[loc.start_line - 1:loc.end_line])):
                raise SummaryError("AI citation does not match supplied source lines")
        validated.append(claim)
    return validated


def summarize_repository(
    snapshot: RepositorySnapshot,
    structures: Iterable[object],
    *,
    source_texts: Mapping[str, str] | None = None,
    provider: SummaryProvider | None = None,
) -> ProjectSummary:
    """Summarize one caller-authorized GitHub snapshot and its parser results.

    Parser results lack SHA, so the caller must obtain them from exactly this
    snapshot. A provider is explicit opt-in and receives only supplied source
    texts; no network client or provider credentials live in this module.
    """
    identity = SnapshotIdentity.from_source(snapshot)
    selected = {item.path: item for item in snapshot.included_files}
    parsable = {path for path in selected if "." + path.rsplit(".", 1)[-1].lower() in _PARSER_SUFFIXES}
    parsed = list(structures)
    if len({item.path for item in parsed}) != len(parsed):
        raise SummaryError("duplicate parser path")
    if {item.path for item in parsed} != parsable:
        raise SummaryError("parser files do not exactly match supported snapshot files")
    for item in parsed:
        _check_structure(item, set(selected))
    sources = dict(source_texts or {})
    if any(path not in selected for path in sources):
        raise SummaryError("source text is outside the included snapshot files")
    if provider is not None and set(sources) != parsable:
        raise SummaryError("AI provider requires source text for every supported file")

    files: list[FileSummary] = []
    modules: list[SummaryClaim] = []
    technologies: list[SummaryClaim] = []
    seen_tech: set[str] = set()
    for item in sorted(parsed, key=lambda structure: structure.path):
        path = item.path
        errors = bool(item.errors)
        facts: list[SummaryClaim] = []
        if not errors:
            for symbol in item.symbols:
                if symbol.kind in {"class", "interface", "struct", "function", "method", "namespace"}:
                    facts.append(_claim(f"Defines {symbol.kind} {symbol.qualified_name}.", path,
                                        symbol.location.start_line))
            for imported in item.imports:
                facts.append(_claim(f"Imports {imported.name}.", path, imported.location.start_line))
            declaration = next((symbol for symbol in item.symbols
                                if symbol.kind in {"class", "interface", "struct", "function"}), None)
            if declaration is not None:
                modules.append(_claim(f"{path} contains named declarations.", path,
                                      declaration.location.start_line))
        uncertainty = (["Parser reported an error; file behavior is unknown."] if errors else
                       ["Business responsibility cannot be established from syntax alone."])
        files.append(FileSummary(path=path, responsibility="Unknown from parsed structure alone.",
                                 responsibility_citations=[],
                                 structural_facts=facts, ai_claims=[], uncertainties=uncertainty))
        suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        language = _LANGUAGE_SUFFIXES.get(suffix)
        if language and language == selected[path].language and language not in seen_tech:
            technologies.append(_claim(f"Contains {language} source files.", path))
            seen_tech.add(language)
    # Marker files belong to the same immutable tree, even when ingestion excludes them.
    for file in snapshot.files:
        marker = file.path.rsplit("/", 1)[-1].lower()
        framework = _FRAMEWORK_MARKERS.get(marker)
        if framework and framework in snapshot.frameworks and framework not in seen_tech:
            technologies.append(_claim(f"{framework} marker file is present.", file.path))
            seen_tech.add(framework)

    ai_status: Literal["unavailable", "validated", "rejected"] = "unavailable"
    uncertainties = ["Project purpose and file responsibilities require source-level evidence.",
                     "Named declarations are module candidates, not proof that a module is central.",
                     "Parser output has no repository ID or SHA; caller must bind it to this authorized snapshot.",
                     "Excluded, unsupported, or failed files may hide modules and technologies."]
    if provider is not None:
        try:
            output = ProviderOutput.model_validate(provider.summarize(
                repository_id=identity.repository_id, commit_sha=identity.commit_sha, sources=sources))
            claims = _validate_provider(output, sources)
        except Exception:
            # Invalid or unavailable provider output never replaces source-backed facts.
            ai_status = "rejected"
            uncertainties.append("AI output was unavailable or failed source citation validation.")
        else:
            by_path = {item.path: item for item in files}
            purpose = "Unknown from parsed structure alone."
            purpose_citations: list[Citation] = []
            for claim in claims:
                ai_claim = SummaryClaim(text=claim.text, origin="ai", citations=claim.citations)
                by_path[claim.path].ai_claims.append(ai_claim)
                if claim.category == "responsibility":
                    by_path[claim.path].responsibility = claim.text
                    by_path[claim.path].responsibility_citations = claim.citations
                elif claim.category == "purpose":
                    purpose = claim.text
                    purpose_citations = claim.citations
                elif claim.category == "module":
                    modules.append(ai_claim)
                elif claim.category == "technology":
                    technologies.append(ai_claim)
            ai_status = "validated"
            uncertainties.append("AI claims are cited interpretations; matching quotes do not prove their meaning.")
            return ProjectSummary(snapshot=identity, files=files, main_modules=modules,
                                  technologies=technologies, purpose=purpose,
                                  purpose_citations=purpose_citations,
                                  ai_status=ai_status, uncertainties=uncertainties)
    return ProjectSummary(snapshot=identity, files=files, main_modules=modules,
                          technologies=technologies, purpose="Unknown from parsed structure alone.",
                          purpose_citations=[],
                          ai_status=ai_status, uncertainties=uncertainties)
