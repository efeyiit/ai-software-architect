# Focused local AI acceptance — 2026-09-25

## Diagnosis and change

The exact dense-ranking baseline selected the correct source first for both `add_one` and `main`. Sending all six hits introduced unrelated README and packaging content: the real small local model abstained. A two-hit experiment also failed (abstention and invalid passage selection). Supplying only the relevant `add_one` excerpt produced correct English and Turkish answers in isolated generation.

Local chat now sends the highest-ranked source excerpt to the model. Retrieval remains repository/snapshot-scoped, and exact quote/line checks remain mandatory. The UI explicitly describes this focused scope. This is a deliberate precision/context tradeoff for the installed small model, not general repository-wide reasoning.

## Live application acceptance

Model: installed Qwen2.5-Coder-1.5B-Instruct, 4-bit. Embeddings: multilingual-E5-small. No cloud inference.

Public source: `pypa/sampleproject`, commit `621e4974ca25ce531773def586ba3ed8e736b3fc`.

| Question | Result | Checked source | Seconds |
| --- | --- | --- | --- |
| What does add_one return? | Answered correctly | src/sample/simple.py:1–2, number + 1 | 2.09 |
| add_one fonksiyonu ne döndürüyor? | Answered in Turkish | Same source and exact quote | 1.89 |
| Where is the main function defined and what does it print? | no_evidence | Abstained despite relevant source | 4.80 |
| What does greeting return? | Answered correctly | Local synthetic greeting.py:1–2, Hello plus name | 2.06 |
| Where does this code configure a PostgreSQL connection? | no_evidence | Correct abstention: local fixture has no database code | 6.45 |

The local fixture is explicitly synthetic, imported through the same local API. Its content identity is `local:474e7321c2cb057042262a8abb3df98dd3697b9fec9cbafe851ab7242d020c76`. The positive answers retained their true public commit or local identity and exact saved-source citations.

These five probes show a bounded improvement, not a general accuracy benchmark: 3/4 supported questions answered, one supported question still abstained, and the unsupported question abstained. Broad and multi-file questions remain a limitation. Source-quote correspondence does not establish semantic correctness by itself; the positive answers above were manually checked.

## Regression checks

A new controlled test first failed with both relevant and distracting evidence sent to the provider; it passes with focused evidence. Persistent isolation and forged-citation rejection tests remain passing.

- Backend full suite: **328 passed, 37 PostgreSQL-dependent skips**.
- Frontend: **70 passed**, 17 test files.
- Frontend production build: passed; existing large diagram-chunk warning remains.

This record supersedes the earlier no-successful-live-answer limitation in the [workspace acceptance record](2026-09-25-local-workspace.md), while retaining the explicit limitations above.

Browser verification: the Turkish add_one question displayed an answered result, exact code quote, and a source link pinned to the public commit. Browser error log was empty.
