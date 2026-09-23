# Product roadmap

**Current state:** FastAPI and React start, and Python and TypeScript validate the same analysis-result fixture. The [verification record](evidence/T01.md) describes the checks. The capabilities below are planned unless that record explicitly verifies them.

## Planned capabilities

1. **Repository intake and identity:** fetch public GitHub repositories, add scoped private-repository access, and associate results with a full commit SHA and repository owner.
2. **Code structure:** parse Python, TypeScript, Java, C#, and C++; build symbol, module, and dependency relationships; detect cycles and infer architecture from traceable evidence.
3. **Analysis outputs:** generate dependency and UML views; identify code smells, SOLID concerns, refactoring opportunities, test gaps, and security risks; propose tests, README text, API documentation, and technical-debt summaries.
4. **Source-linked assistance:** create file and project explanations, index relevant code for retrieval, answer repository questions with citations, and keep rule-based findings separate from AI interpretations.
5. **Application and scale:** persist analyses, run jobs asynchronously, cache by branch and commit, expose report APIs, and present findings, diagrams, tests, security, documentation, and chat in the web interface.
6. **Change tracking and delivery:** support incremental analysis, pull-request diffs and webhooks, issue drafts with an explicit publish action, architecture history, containerized operation, CI, evaluation, and an end-to-end demo.

## Verification boundaries

Analyzed repository content is data, not instructions. Running that code is outside the default analysis path. Test discovery and measured coverage are different results; coverage requires an existing coverage artifact. Each planned capability needs behavior tests and evidence before it is described as implemented.

The [source design](source-design.md) contains the full intended scope. This roadmap expresses implementation areas without narrowing that scope or claiming a release date.
