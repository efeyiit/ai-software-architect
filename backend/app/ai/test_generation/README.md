# T15 — Test scenarios and draft code

`generate_test_drafts(structures, testing_report, graph=None, *, contexts=())`
consumes T05–T09 parser structures and the corresponding T14 `TestingReport`.
Pass the same T10 graph to T14 and T15 if one was used. T15 recomputes test
discovery and rejects differing service or test-file facts. Only T14
`potentially_untested` services receive drafts; this status is a discovery hint,
not proof that no test exists. Coverage remains separate T14 evidence.

Without an authoring context, each parsed method (or a class without parsed
methods) receives source-linked success and error **review scenarios**.
`expectation_source=unknown`, `code=None`, and `framework=None` identify facts
that are missing. The generator does not invent a business rule, callable
signature, expected value, exception, or test framework.

To generate code, supply one `TestAuthoringContext` for a candidate service:

- `source_text`, `service_path`, `service_name`, `method_name`, and
  `signature_text` identify a real parsed method. T15 reparses the supplied
  text, compares parser facts, and checks the signature text at the method's
  source line. The caller still has to bind this text to the authorized
  repository ID and commit SHA; parser/T14 contracts do not carry those IDs.
- `framework_test_path` points to a T14-discovered test file with at least one
  declaration and the matching `framework`. Supported pairs are Python/pytest,
  TypeScript/Vitest, Java/JUnit, C#/xUnit, and C++/GoogleTest. The source design
  does not prescribe these frameworks; they are accepted only when T14 finds
  evidence in the supplied repository snapshot.
- `call_kind=sync_instance_value` states the supported call form. The caller
  supplies `target_import`, `constructor_expression`, success and error
  arguments, a success expected expression, and an error type. Java also needs
  `result_type` confirmed on the source signature line. `additional_imports`
  can supply dependencies needed by the chosen expressions. The generator does
  not infer setup, asynchronous behavior, or exceptions from a method name.

With this context, the structured scenarios record the supplied input and
expected result or error (`expectation_source=supplied`). `code` contains two
API-bound test drafts using the discovered framework. The drafts invoke the
actual named method and assert the supplied outcome; they do not contain an
unconditional failure. All code remains `verification=draft_unverified` and
requires human review. Supplying expectations does not establish that the
service implements them or that the generated code compiles in the user's
project. T15 never executes generated tests or analyzed repository code.

The output is deterministic (`origin=deterministic`, `ai_status=unavailable`).
No LLM provider is configured, no code is transmitted externally, and these
drafts must not be described as AI generated. A future provider would need a
separate injection boundary, source citation validation, and privacy review.
The structured result is local to this module; T25/T29 own API/UI integration.

Focused verification from `backend/` runs Ariadne's own fixture tests only:

```text
uv run --no-sync pytest -q tests/test_generation tests/testing
```
