# Product roadmap

**Current state:** The account-free local workspace imports public GitHub repositories and local source folders, saves immutable snapshots and reports in SQLite, runs static analysis, and links findings back to saved source lines. It includes architecture, dependency, findings, security, testing, refactoring, documentation, and optional local AI chat views. See the [workspace acceptance record](evidence/2026-09-25-local-workspace.md) and [focused AI checks](evidence/2026-09-25-focused-local-ai.md) for the demonstrated behavior and limitations. The latest [regression check](evidence/2026-09-26-regression-baseline.md) revalidates the automated suite after interface changes.

## Capability areas and remaining work

These areas describe the full intended scope. Some are implemented in the local workspace; this list does not claim that every item is complete.

1. **Repository intake and identity:** public GitHub import and local/private source-folder import are available without login. Public snapshots retain a full commit SHA; local snapshots use a content identity. Hosted private GitHub access remains part of the separate authenticated-server work.
2. **Code structure:** parse Python, TypeScript, Java, C#, and C++; build symbol, module, and dependency relationships; detect cycles and infer architecture from traceable evidence.
3. **Analysis outputs:** generate dependency and UML views; identify code smells, SOLID concerns, refactoring opportunities, test gaps, and security risks; propose tests, README text, API documentation, and technical-debt summaries.
4. **Source-linked assistance:** optional local chat currently answers from one highest-ranked source excerpt, with source-line and quote validation. Broad and multi-file reasoning remains limited; one supported question in the live acceptance probes still abstained. File/project explanations and wider-context retrieval remain development areas. Rule-based findings stay separate from AI interpretations.
5. **Application and scale:** persist analyses, run jobs asynchronously, cache by branch and commit, expose report APIs, and present findings, diagrams, tests, security, documentation, and chat in the web interface.
6. **Change tracking and delivery:** support incremental analysis, pull-request diffs and webhooks, issue drafts with an explicit publish action, architecture history, containerized operation, CI, evaluation, and an end-to-end demo.

## Verification boundaries

Analyzed repository content is data, not instructions. Running that code is outside the default analysis path. Test discovery and measured coverage are different results; coverage requires an existing coverage artifact. Each planned capability needs behavior tests and evidence before it is described as implemented.

The [source design](source-design.md) contains the full intended scope. This roadmap expresses implementation areas without narrowing that scope or claiming a release date.
