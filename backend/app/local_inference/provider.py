"""Fail-closed AnswerProvider and EmbeddingProvider clients over loopback HTTP."""

from __future__ import annotations

import json
import math
import os
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.rag.chat import ChatPrompt, ChatProviderAnswer, ProviderRejected


DEFAULT_ENDPOINT = "http://127.0.0.1:8766"
ENDPOINT_ENV = "ARIADNE_LOCAL_RUNTIME_URL"
TOKEN_ENV = "ARIADNE_LOCAL_RUNTIME_TOKEN"


class LocalRuntimeConfigError(ValueError):
    """Missing token or endpoint outside the fixed loopback trust boundary."""


class LocalRuntimeUnavailable(ConnectionError):
    """The local worker could not serve the request."""


def _endpoint(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise LocalRuntimeConfigError("invalid local model endpoint") from None
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or port not in (8766, 8767) or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise LocalRuntimeConfigError("local model endpoint must be loopback port 8766 or 8767")
    return f"http://127.0.0.1:{port}"


class _Client:
    def __init__(self, endpoint: str | None = None, token: str | None = None,
                 timeout_seconds: float = 120.0):
        self.endpoint = _endpoint(endpoint or os.environ.get(ENDPOINT_ENV, DEFAULT_ENDPOINT))
        self.token = token if token is not None else os.environ.get(TOKEN_ENV)
        if not isinstance(self.token, str) or not self.token:
            raise LocalRuntimeConfigError("local runtime token is missing")
        if not 1 <= timeout_seconds <= 300:
            raise LocalRuntimeConfigError("invalid local runtime timeout")
        self.timeout_seconds = timeout_seconds

    def _post(self, path: str, payload: dict, *, max_response_bytes: int = 64_000) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > 64_000:
            raise LocalRuntimeConfigError("local model request exceeds 64 KB")
        request = Request(self.endpoint + path, data=body, method="POST",
                          headers={"Content-Type": "application/json",
                                   "Authorization": "Bearer " + self.token})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(max_response_bytes + 1)
        except HTTPError as exc:
            if exc.code == 422:
                raise ProviderRejected("local model output rejected after one repair") from None
            raise LocalRuntimeUnavailable("local worker rejected request") from None
        except (URLError, TimeoutError, OSError):
            raise LocalRuntimeUnavailable("local worker unavailable") from None
        if len(raw) > max_response_bytes:
            raise ProviderRejected("local model response exceeds its bounded limit")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderRejected("local model response is malformed JSON") from None
        if not isinstance(result, dict):
            raise ProviderRejected("local model response must be an object")
        return result


class LocalAnswerProvider(_Client):
    execution_location = "local"

    def answer(self, prompt: ChatPrompt) -> ChatProviderAnswer:
        if not isinstance(prompt, ChatPrompt):
            raise LocalRuntimeConfigError("expected ChatPrompt")
        payload = {
            "instructions": prompt.instructions,
            "question": prompt.question,
            "evidence": [{"id": item.id, "path": item.path,
                          "start_line": item.start_line, "end_line": item.end_line,
                          "commit_sha": item.commit_sha, "text": item.text}
                         for item in prompt.evidence],
        }
        raw = self._post("/answer", payload)
        try:
            return ChatProviderAnswer.model_validate(raw)
        except Exception:
            raise ProviderRejected("local model answer failed schema validation") from None


class LocalEmbeddingProvider(_Client):
    model_id = "intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 384
    execution_location = "local"

    def _embed(self, texts: Sequence[str], kind: str) -> list[list[float]]:
        if not 1 <= len(texts) <= 64 or any(not isinstance(t, str) or not t or
                                             len(t) > 8000 for t in texts):
            raise LocalRuntimeConfigError("embedding request requires 1-64 bounded texts")
        # 64 x 384 JSON floats can exceed 64 KB while remaining a valid batch.
        raw = self._post("/embed", {"texts": list(texts), "kind": kind},
                         max_response_bytes=1_000_000)
        vectors = raw.get("vectors")
        if (raw.get("model_id") != self.model_id or
                not isinstance(vectors, list) or len(vectors) != len(texts)):
            raise LocalRuntimeUnavailable("embedding worker returned incompatible vectors")
        result = []
        for vector in vectors:
            if (not isinstance(vector, list) or len(vector) != self.dimension or
                    any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                        not math.isfinite(x) for x in vector)):
                raise LocalRuntimeUnavailable("embedding worker returned invalid vector")
            result.append([float(value) for value in vector])
        return result

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> Sequence[float]:
        return self._embed([text], "query")[0]


def runtime_health(endpoint: str | None = None, *, timeout_seconds: float = 2.0) -> dict:
    endpoint = _endpoint(endpoint or os.environ.get(ENDPOINT_ENV, DEFAULT_ENDPOINT))
    try:
        with urlopen(endpoint + "/health", timeout=timeout_seconds) as response:
            result = json.loads(response.read(4096))
    except (URLError, TimeoutError, OSError, ValueError):
        raise LocalRuntimeUnavailable("local worker health unavailable") from None
    if not isinstance(result, dict) or result.get("status") != "ready":
        raise LocalRuntimeUnavailable("local worker is not ready")
    return result
