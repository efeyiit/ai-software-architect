"""Owner-bound, authenticated reads of private GitHub source."""

from .service import GitHubPrivateService, PrivateRepositorySnapshot

__all__ = ["GitHubPrivateService", "PrivateRepositorySnapshot"]
