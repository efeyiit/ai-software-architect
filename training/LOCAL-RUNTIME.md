# Local inference worker

The application launcher starts one worker on loopback and its API
separately. The default worker port is 8766; a launcher can use 8767 through
child env `ARIADNE_LOCAL_RUNTIME_PORT=8767` and point backend clients to it
with `ARIADNE_LOCAL_RUNTIME_URL=http://127.0.0.1:8767`. Only those two ports
are accepted. The worker uses the pinned Qwen2.5-Coder-1.5B-Instruct
**base** weights in 4-bit CUDA and does not attach either training adapter.
It loads the pinned intfloat/multilingual-e5-small embedding model on CPU. No paid
API, cloud inference, or external repository code execution is involved.

The launcher must create a fresh `secrets.token_urlsafe(32)` value and pass it
only in the child environment variable `ARIADNE_LOCAL_RUNTIME_TOKEN` to the
worker and API. The worker refuses to start without it. Never log the
value or place it in command arguments, the frontend, metadata, or Git files.

Start the worker as `training/.venv/Scripts/python.exe
training/local_runtime_server.py` with that child environment. The worker
loads both models before binding its port. `GET /health` is tokenless and
returns `status: ready`, model IDs, embedding dimension 384, and `local`
execution location. `POST /answer` and `POST /embed` require the token.
The server is single threaded, so one request runs at a time. Answer context
is bounded to 4,096 tokens with up to 384 generated tokens. The input body is
bounded to 64 KB. The `opaque-passage-selection-v4` prompt asks the model to
select supplied passage IDs; the server derives source coordinates and exact
quotes from those passages. One repair generation is allowed. Invalid output then
becomes `rejected`, with no invented answer fallback. Transport failures are
`unavailable`. T21 independently rechecks live authorization and citations.

`LocalAnswerProvider` and `LocalEmbeddingProvider` in
`backend/app/local_inference` are the backend adapters. Both read the loopback
endpoint and token from their child environment.
The multilingual E5 provider emits 384-dimensional normalized mean-pooled
embeddings. Query and source passages use the publisher's `query: ` and
`passage: ` prefixes. Its pinned model ID creates a separate Qdrant collection
from the earlier BGE index. Existing repositories need reindexing with E5.
The small public-repository diagnostic showed README rank 1 for a Turkish
purpose question with E5 versus rank 5 with English-focused BGE. This does
not by itself establish end-to-end answer quality.

No completed live acceptance run establishes answer quality for the current
prompt version. The deterministic passage-selection tests verify source
mapping and rejection behavior without loading or evaluating the model.

Sources: [Qwen model](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct),
[multilingual E5 model and usage](https://huggingface.co/intfloat/multilingual-e5-small).
