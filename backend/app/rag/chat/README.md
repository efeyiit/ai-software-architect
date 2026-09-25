# T21 — Source-cited repository chat

`RepositoryChat(index, provider).ask(authenticated_caller_id, local_repository_id, question)`
uses T20's `QdrantIndex.search` and `current_scope`. T04's
`LiveRepositoryScopeResolver` is the available trusted resolver for the index: it
checks local ownership, live private-repository permission and the current GitHub
commit SHA on every call. Request input cannot choose the search filter or SHA. If
permission is revoked, the repository changes, or a resolver fails, the operation
fails closed. The chat service checks scope again before and after answer generation.

The provider is injectable and must be a trusted **local** implementation with
`execution_location = "local"` and `answer(ChatPrompt) -> ChatProviderAnswer`.
No production model or external LLM client is installed here. Without a provider,
the result has `status="unavailable"`; fixture answers in tests are not represented
as actual AI. The only provider input is the bounded question and up to six retrieved
source chunks (12,000 characters by default). Obvious credentials are redacted,
and chunks containing PEM private keys are omitted. This redaction is defense in
depth, not a guarantee that every possible secret format is recognized. Because
there is no vetted external-provider policy, private repository code must not be
sent to an external provider.

Repository files, comments and README text are untrusted data. The prompt tells
the provider to ignore their instructions. The service accepts structured claims
only when every citation points to a selected Qdrant chunk and quotes exact text
within its path, line interval and current SHA. Redacted text cannot be cited.
Invalid citations reject the entire answer. Empty search results or an answer
without claims produce `status="no_evidence"` and an explicit “Bilmiyorum” message.
Provider failure is `unavailable`. A validated answer is marked `origin="ai"` and
includes citations in both the answer text and structured `claims` field. Exact
quote validation proves source provenance, but does not prove that a model's
interpretation follows logically from the quote; clients must retain the AI label
and show the quote so a person can inspect it.

T17 summaries are not passed directly to the model: parser-derived summary facts
do not carry independently verified source text, and their repository/SHA binding
must be supplied by an authorized caller. T21 cites the original T20 chunks. A
future orchestrator can add T17 facts only after binding them to the same current
snapshot and validating their underlying source excerpts.

The tests use a controlled local provider and the real `qdrant-client` local mode:

```text
uv run --directory backend pytest tests/rag/chat -q
```

They cover positive source citation, no evidence, invalid citations, README
prompt injection data, secret redaction, owner isolation, permission revocation,
SHA changes, provider absence/failure and context budget. One integration test
composes the actual T04 resolver, T20 local Qdrant index and T21 chat with
controlled GitHub/identity fixtures. These tests do not establish semantic answer
accuracy for a production LLM. The HTTP route, production model, UI presentation
and end-to-end OAuth wiring remain separate integration work.
