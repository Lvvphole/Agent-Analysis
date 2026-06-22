"""Static model catalog — frontend-selectable placeholders.

Known Anthropic + OpenAI models the user can pick from a dropdown. These are
**editable placeholders**: ``model_id`` values should be confirmed/pinned by the
operator, and ``live_calls_available`` is ``False`` until provider API keys + the
network policy are provisioned and a real adapter is wired. Selecting a catalog
entry produces a ``ModelSpec`` that still passes through ``model_policy_gate``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.model_policy import ModelRole, ModelSpec, RateLimit


class CatalogEntry(BaseModel):
    model_config = {"extra": "forbid", "protected_namespaces": ()}

    provider: str
    model_id: str
    label: str
    suggested_roles: list[ModelRole] = Field(default_factory=list)
    default_temperature: float = 0
    default_top_p: float = 1
    live_calls_available: bool = False
    note: str = "editable placeholder — confirm the exact pinned model id"


MODEL_CATALOG: list[CatalogEntry] = [
    CatalogEntry(
        provider="anthropic", model_id="claude-sonnet-4-6", label="Claude Sonnet 4.6",
        suggested_roles=[ModelRole.CODING_AGENT, ModelRole.ANALYST],
    ),
    CatalogEntry(
        provider="anthropic", model_id="claude-haiku-4-5", label="Claude Haiku 4.5",
        suggested_roles=[ModelRole.EVALUATOR, ModelRole.ANALYST],
    ),
    CatalogEntry(
        provider="anthropic", model_id="claude-opus-latest", label="Claude Opus (latest)",
        suggested_roles=[ModelRole.CODING_AGENT, ModelRole.VERIFIER],
    ),
    CatalogEntry(
        provider="anthropic", model_id="claude-fable-5", label="Claude Fable 5",
        suggested_roles=[ModelRole.ANALYST],
    ),
    CatalogEntry(
        provider="openai", model_id="gpt-4o", label="OpenAI GPT-4o",
        suggested_roles=[ModelRole.CODING_AGENT, ModelRole.VERIFIER],
    ),
    CatalogEntry(
        provider="openai", model_id="gpt-4o-mini", label="OpenAI GPT-4o mini",
        suggested_roles=[ModelRole.EVALUATOR],
    ),
    CatalogEntry(
        provider="openai", model_id="o4-mini", label="OpenAI o4-mini",
        suggested_roles=[ModelRole.VERIFIER, ModelRole.ANALYST],
    ),
]


def to_model_spec(
    entry: CatalogEntry,
    *,
    role: ModelRole,
    model_run_id: str,
    prompt_hash: str,
    permissions: list[str],
    rate_limit: RateLimit,
    fallback_model_id: str = "",
) -> ModelSpec:
    """Build a declared ``ModelSpec`` from a catalog choice and run-time policy."""
    return ModelSpec(
        model_id=entry.model_id,
        provider=entry.provider,
        role=role,
        model_run_id=model_run_id,
        permissions=permissions,
        temperature=entry.default_temperature,
        top_p=entry.default_top_p,
        prompt_hash=prompt_hash,
        rate_limit=rate_limit,
        fallback_model_id=fallback_model_id,
    )
