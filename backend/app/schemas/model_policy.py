"""Controlled LLM Integration schemas.

A run may orchestrate multiple LLMs only if each model is declared, role-bound,
allowlisted, rate-limited, permissioned, and (when invoked) invocation-recorded,
hashed, and ledgered. These models capture the declaration; ``model_policy_gate``
is the authority that decides admissibility.

``protected_namespaces=()`` is set because Pydantic v2 reserves the ``model_``
prefix; ``model_id`` / ``model_run_id`` are intentional domain fields.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ModelRole(str, Enum):
    """A model is bound to exactly one controlled role per declaration."""

    CODING_AGENT = "CODING_AGENT"
    VERIFIER = "VERIFIER"
    EVALUATOR = "EVALUATOR"
    ANALYST = "ANALYST"
    ROUTER = "ROUTER"


class RateLimit(BaseModel):
    model_config = {"extra": "forbid"}

    requests_per_min: int = 0
    tokens_per_min: int = 0

    @property
    def is_set(self) -> bool:
        return self.requests_per_min > 0 or self.tokens_per_min > 0


class ModelSpec(BaseModel):
    """A single declared, role-bound model in a run's registry."""

    model_config = {"extra": "forbid", "protected_namespaces": ()}

    model_id: str = ""
    provider: str = ""
    role: ModelRole
    # Independent invocation identity — the keystone for role independence.
    model_run_id: str = ""
    permissions: list[str] = Field(default_factory=list)

    # Determinism controls (mirror the run manifest).
    temperature: float = 0
    top_p: float = 1
    seed: int = 23
    prompt_hash: str = ""
    parallel_tool_calls: bool = False

    rate_limit: RateLimit = Field(default_factory=RateLimit)
    fallback_model_id: str = ""
    max_retries: int = 0


class LLMInvocationRecord(BaseModel):
    """Evidence record for one model call.

    The response *narrative* is context only (``used_as_evidence=False``); this
    hashed, ledgered record — not the narrative — is what supports traceability.
    """

    model_config = {"extra": "forbid", "protected_namespaces": ()}

    invocation_id: str
    model_id: str
    role: ModelRole
    run_id: str
    task_id: str
    request_hash: str = ""
    response_hash: str = ""
    request_artifact_path: str = ""
    response_artifact_path: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    rate_limit_status: str = "OK"  # OK | THROTTLED | FALLBACK_USED
    used_as_evidence: bool = False
    claimed_status: str = "IGNORED"
    recorded_by: str = ""
    timestamp: str = ""
