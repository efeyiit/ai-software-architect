"""Minimal API bootstrap; analysis endpoints belong to later tasks."""

from fastapi import FastAPI

app = FastAPI(title="Ariadne API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
