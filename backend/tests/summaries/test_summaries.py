import pytest

from app.ai.summaries import summarize_repository, SummaryError
from app.ai.summaries.service import Citation, ProviderClaim, ProviderOutput
from app.contracts.analysis import SourceLocation
from app.parsers.python import parse_file as parse_python
from app.parsers.typescript import parse_file as parse_typescript
from app.parsers.java import parse_file as parse_java
from app.parsers.csharp import parse_file as parse_csharp
from app.parsers.cpp import parse_file as parse_cpp
from app.services.github_public import RepositoryFile, RepositorySnapshot


SHA = "a" * 40
SOURCES = {
    "src/a.py": "import json\nclass A:\n    pass\n",
    "src/b.ts": "export class B {}\n",
    "src/C.java": "class C {}\n",
    "src/D.cs": "class D {}\n",
    "src/e.cpp": "class E {};\n",
}
PARSERS = (parse_python, parse_typescript, parse_java, parse_csharp, parse_cpp)
LANGUAGES = ("Python", "TypeScript", "Java", "C#", "C++")


def fixture():
    files = tuple(RepositoryFile(path, "b" * 40, len(source), language, True, None)
                  for (path, source), language in zip(SOURCES.items(), LANGUAGES))
    snapshot = RepositorySnapshot("42", "https://github.com/example/repo", "repo", "main",
                                  SHA, "c" * 40, files, (), ())
    structures = [parser(path, source) for parser, (path, source) in zip(PARSERS, SOURCES.items())]
    return snapshot, structures


def test_five_real_parsers_have_source_linked_structural_summary():
    snapshot, structures = fixture()
    result = summarize_repository(snapshot, structures)
    assert result.snapshot.commit_sha == SHA
    assert {claim.text for claim in result.technologies} == {
        f"Contains {language} source files." for language in LANGUAGES}
    assert len(result.files) == 5
    assert result.ai_status == "unavailable"
    assert result.purpose.startswith("Unknown")
    assert all(file.responsibility.startswith("Unknown") and not file.ai_claims
               for file in result.files)
    assert all(claim.citations[0].location.path == file.path
               for file in result.files for claim in file.structural_facts)
    assert all(claim.origin == "static" for claim in result.main_modules)


def test_parser_error_keeps_file_unknown_and_other_files_available():
    snapshot, structures = fixture()
    structures[0] = parse_python("src/a.py", "def broken(:\n")
    result = summarize_repository(snapshot, structures)
    files = {file.path: file for file in result.files}
    assert files["src/a.py"].structural_facts == []
    assert "Parser reported an error" in files["src/a.py"].uncertainties[0]
    assert files["src/b.ts"].structural_facts


def test_rejects_missing_or_foreign_parser_path():
    snapshot, structures = fixture()
    with pytest.raises(SummaryError, match="exactly match"):
        summarize_repository(snapshot, structures[:-1])
    structures[0] = parse_python("elsewhere/a.py", SOURCES["src/a.py"])
    with pytest.raises(SummaryError, match="exactly match"):
        summarize_repository(snapshot, structures)


class Provider:
    def __init__(self, quote="class A:", line=2):
        self.quote = quote
        self.line = line
        self.seen = None

    def summarize(self, *, repository_id, commit_sha, sources):
        self.seen = (repository_id, commit_sha, set(sources))
        return ProviderOutput(claims=[ProviderClaim(
            path="src/a.py", category="responsibility", text="This class may coordinate work.", citations=[Citation(
                location=SourceLocation(path="src/a.py", start_line=self.line,
                                        end_line=self.line), quote=self.quote)])])


def test_opt_in_provider_claim_requires_matching_source_quote_and_snapshot():
    snapshot, structures = fixture()
    provider = Provider()
    result = summarize_repository(snapshot, structures, source_texts=SOURCES, provider=provider)
    assert provider.seen == ("42", SHA, set(SOURCES))
    assert result.ai_status == "validated"
    claim = next(file for file in result.files if file.path == "src/a.py").ai_claims[0]
    assert claim.origin == "ai"
    assert claim.citations[0].quote == "class A:"
    file = next(file for file in result.files if file.path == "src/a.py")
    assert file.responsibility == claim.text
    assert file.responsibility_citations == claim.citations


def test_invalid_ai_citation_is_rejected_without_losing_static_facts():
    snapshot, structures = fixture()
    result = summarize_repository(snapshot, structures, source_texts=SOURCES,
                                  provider=Provider("invented", 2))
    assert result.ai_status == "rejected"
    file = next(file for file in result.files if file.path == "src/a.py")
    assert file.ai_claims == []
    assert file.structural_facts


def test_provider_requires_complete_text_and_never_receives_excluded_content():
    snapshot, structures = fixture()
    with pytest.raises(SummaryError, match="every supported"):
        summarize_repository(snapshot, structures, source_texts={"src/a.py": SOURCES["src/a.py"]},
                             provider=Provider())
    with pytest.raises(SummaryError, match="outside"):
        summarize_repository(snapshot, structures, source_texts={**SOURCES, "secret.txt": "secret"})
