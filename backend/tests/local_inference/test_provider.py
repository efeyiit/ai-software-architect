"""Targeted loopback boundary and failure semantics tests."""

from io import BytesIO
from unittest.mock import patch

import pytest

from app.local_inference import (LocalAnswerProvider, LocalEmbeddingProvider,
                                 LocalRuntimeConfigError, LocalRuntimeUnavailable)
from app.rag.chat import ChatPrompt, Evidence, ProviderRejected


class Response:
    def __init__(self, body):
        self.body = BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size=-1):
        return self.body.read(size)


PROMPT = ChatPrompt("Use evidence", "What returns 1?", (
    Evidence("E1", "src/a.py", 1, 2, "a" * 40,
             "def one():\n    return 1\n"),
))


def test_provider_rejects_nonloopback_and_missing_token():
    with pytest.raises(LocalRuntimeConfigError):
        LocalAnswerProvider(endpoint="https://example.com", token="private")
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(LocalRuntimeConfigError, match="token"):
            LocalAnswerProvider()
    with patch.dict("os.environ", {"ARIADNE_LOCAL_RUNTIME_URL": "http://127.0.0.1:8767",
                                "ARIADNE_LOCAL_RUNTIME_TOKEN": "private"}):
        assert LocalAnswerProvider().endpoint == "http://127.0.0.1:8767"


def test_answer_decodes_strict_cited_schema_and_malformed_response_rejects():
    provider = LocalAnswerProvider(token="private")
    valid = (b'{"claims":[{"text":"one returns 1","citations":['
             b'{"evidence_id":"E1","start_line":2,"end_line":2,'
             b'"quote":"return 1"}]}]}')
    with patch("app.local_inference.provider.urlopen", return_value=Response(valid)):
        answer = provider.answer(PROMPT)
    assert answer.claims[0].citations[0].quote == "return 1"
    with patch("app.local_inference.provider.urlopen", return_value=Response(b"not json")):
        with pytest.raises(ProviderRejected):
            provider.answer(PROMPT)


def test_embedding_shape_is_real_384_contract():
    provider = LocalEmbeddingProvider(token="private")
    import json
    body = json.dumps({"model_id": provider.model_id,
                       "vectors": [[0.0] * 383 + [1.0]]}).encode()
    with patch("app.local_inference.provider.urlopen", return_value=Response(body)):
        vector = provider.embed_query("Which function returns one?")
    assert len(vector) == 384
    with patch("app.local_inference.provider.urlopen", return_value=Response(b"{}")):
        with pytest.raises(LocalRuntimeUnavailable):
            provider.embed_query("Which function returns one?")


def test_full_embedding_batch_has_its_own_bounded_response_limit():
    provider = LocalEmbeddingProvider(token="private")
    import json
    texts = [f"passage {number}" for number in range(64)]
    body = json.dumps({"model_id": provider.model_id,
                       "vectors": [[0.12345678901234568] * 384 for _ in texts]}).encode()
    assert 64_000 < len(body) < 1_000_000
    with patch("app.local_inference.provider.urlopen", return_value=Response(body)):
        vectors = provider.embed_documents(texts)
    assert len(vectors) == 64
    assert all(len(vector) == 384 for vector in vectors)

    with patch("app.local_inference.provider.urlopen",
               return_value=Response(b" " * 1_000_001)):
        with pytest.raises(ProviderRejected, match="bounded limit"):
            provider.embed_documents(texts)
