"""Source-linked, owner-scoped repository vector indexing."""

from .chunker import CodeChunk, chunk_snapshot
from .store import AuthorizedScope, EmbeddingProvider, IndexingError, QdrantIndex, SearchHit

__all__ = ["AuthorizedScope", "CodeChunk", "EmbeddingProvider", "IndexingError",
           "QdrantIndex", "SearchHit", "chunk_snapshot"]
