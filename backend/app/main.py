from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .core.logging import configure_logging, jlog

configure_logging(logging.INFO)
app = FastAPI(title="Compliance Screenshot Archiver", version="0.1.0")

# Configure CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
    ],  # Vite and CRA default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """
    Lightweight liveness endpoint.

    Returns:
        dict[str, str]: Health status.
    """
    jlog(logging.getLogger(__name__), "healthcheck", status="ok")
    return {"status": "ok"}
