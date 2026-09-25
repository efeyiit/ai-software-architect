"""HTTP routes receive owner identity only from the host's verified session."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
import psycopg

from app.rag.indexing import IndexingError
from app.services.github_public.service import GitHubPublicError


class RepositoryInput(BaseModel):
    github_url: str = Field(min_length=1, max_length=300)


class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value


class ApiError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code


class RuntimeProxy:
    """Configured during FastAPI lifespan; unavailable installations fail closed."""

    def __init__(self):
        self.runtime: Any | None = None

    def __getattr__(self, name: str):
        if self.runtime is None:
            raise ApiError(503, "configuration_unavailable")
        return getattr(self.runtime, name)


def create_api_router(require_session_user: Callable[..., str], services: Any) -> APIRouter:
    """Mount only with T04's server-side session dependency and a configured service.

    A caller-supplied header or body field is never accepted as user identity.
    """
    router = APIRouter(prefix="/api")

    def invoke(method: str, *args):
        try:
            return getattr(services, method)(*args)
        except ApiError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
        except psycopg.Error:
            raise HTTPException(status_code=503, detail="database_unavailable") from None
        except GitHubPublicError as exc:
            raise HTTPException(status_code=503 if exc.retryable else 422,
                                detail=exc.code.lower()) from None
        except IndexingError:
            raise HTTPException(status_code=409, detail="repository_index_unavailable") from None

    @router.get("/repositories")
    def list_repositories(owner: str = Depends(require_session_user)):
        return invoke("list_repositories", owner)

    @router.post("/repositories", status_code=201)
    def create_repository(body: RepositoryInput, owner: str = Depends(require_session_user)):
        return invoke("create_repository", owner, body.github_url)

    @router.get("/repositories/{repository_id}")
    def repository(repository_id: str, owner: str = Depends(require_session_user)):
        return invoke("repository", owner, repository_id)

    @router.get("/repositories/{repository_id}/files")
    def files(repository_id: str, owner: str = Depends(require_session_user)):
        return invoke("files", owner, repository_id)

    @router.get("/repositories/{repository_id}/files/summary")
    def file_summary(repository_id: str, path: str = Query(min_length=1, max_length=1000),
                     owner: str = Depends(require_session_user)):
        return invoke("file_summary", owner, repository_id, path)

    @router.post("/repositories/{repository_id}/analyze", status_code=202)
    def analyze(repository_id: str, owner: str = Depends(require_session_user),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        return invoke("analyze", owner, repository_id, idempotency_key)

    @router.get("/repositories/{repository_id}/jobs/{job_id}")
    def job(repository_id: str, job_id: str, owner: str = Depends(require_session_user)):
        return invoke("job", owner, repository_id, job_id)

    @router.post("/repositories/{repository_id}/jobs/{job_id}/cancel")
    def cancel(repository_id: str, job_id: str, owner: str = Depends(require_session_user)):
        return invoke("cancel", owner, repository_id, job_id)

    @router.get("/repositories/{repository_id}/analyses/{analysis_id}")
    def analysis(repository_id: str, analysis_id: str, owner: str = Depends(require_session_user)):
        return invoke("analysis", owner, repository_id, analysis_id)

    @router.get("/repositories/{repository_id}/issues")
    def issues(repository_id: str, owner: str = Depends(require_session_user)):
        return invoke("issues", owner, repository_id)

    @router.get("/repositories/{repository_id}/dependencies")
    def dependencies(repository_id: str, owner: str = Depends(require_session_user)):
        return invoke("dependencies", owner, repository_id)

    @router.get("/repositories/{repository_id}/diagrams")
    def diagrams(repository_id: str, owner: str = Depends(require_session_user)):
        return invoke("diagrams", owner, repository_id)

    @router.post("/repositories/{repository_id}/chat")
    def chat(repository_id: str, body: ChatInput, owner: str = Depends(require_session_user)):
        return invoke("chat", owner, repository_id, body.question)

    return router
