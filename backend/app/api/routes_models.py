"""Model endpoints (Controlled LLM Integration Layer).

Safe, read-only introspection: the model catalog that the (deferred) frontend
dropdown consumes, a roles/providers summary, and a run's recorded LLM
invocations. No invocation, merge, deploy, or other state-changing action.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.store import registry
from app.llm.catalog import MODEL_CATALOG
from app.schemas.model_policy import ModelRole

router = APIRouter(tags=["models"])


@router.get("/models")
def models_summary() -> dict:
    return {
        "roles": [r.value for r in ModelRole],
        "providers": sorted({e.provider for e in MODEL_CATALOG}),
        "catalog_size": len(MODEL_CATALOG),
        "live_calls_available": any(e.live_calls_available for e in MODEL_CATALOG),
    }


@router.get("/models/catalog")
def models_catalog() -> list[dict]:
    """Known Anthropic + OpenAI models as frontend-selectable placeholders."""
    return [e.model_dump() for e in MODEL_CATALOG]


@router.get("/runs/{run_id}/llm-invocations")
def run_llm_invocations(run_id: str) -> list[dict]:
    record = registry.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run not found")
    return list(record.llm_invocations)
