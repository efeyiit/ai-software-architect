"""Source-bound documentation drafts for an analyzed repository."""

from .generator import DocumentationError, DocumentationResult, generate_documentation

__all__ = ["DocumentationError", "DocumentationResult", "generate_documentation"]
