"""FastAPI control-plane application (Section 12.1).

The backend is the authority layer. The API exposes state and evidence and
*requested* actions; it never merges, deploys, or marks work complete. Those
endpoints do not exist by construction.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import routes_chains, routes_models, routes_runs
from app.api.store import configure_from_env


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bind the durable run store when AGENT_ANALYSIS_DATABASE_URL is set;
    # otherwise the in-memory adapter, so dev and tests need no database.
    configure_from_env()
    yield


app = FastAPI(
    title="Agent-Analysis Control API",
    description=(
        "Deterministic control system around autonomous AI-generated code. "
        "No auto-merge. No auto-deploy. No self-certification."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(routes_runs.router)
app.include_router(routes_chains.router)
app.include_router(routes_models.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "auto_merge": False,
        "auto_deploy": False,
        "self_certification_allowed": False,
    }
