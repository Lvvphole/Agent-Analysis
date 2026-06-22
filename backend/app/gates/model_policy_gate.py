"""Model policy gate (Controlled LLM Integration Layer).

Pure function: a run's model registry is admissible only if every declared model
is declared, role-bound, allowlisted, rate-limited, permissioned, determinism-
pinned, and the VERIFIER model is independent from the CODING_AGENT model
(model-level extension of the same-agent-verifier ban, Section 6.3).
"""

from __future__ import annotations

from app.constants import RunType
from app.schemas.gate_result import GateResult
from app.schemas.model_policy import ModelRole
from app.schemas.run_manifest import RunManifest

GATE_NAME = "model_policy_gate"

# Roles each run type must cover for a controlled multi-LLM run.
_REQUIRED_ROLES = {
    RunType.IMPLEMENTATION: {ModelRole.CODING_AGENT, ModelRole.VERIFIER},
    RunType.READ_ONLY_ANALYSIS: {ModelRole.VERIFIER},
}


def model_policy_gate(manifest: RunManifest) -> GateResult:
    """Return PASS only if the declared model registry holds every hard rule.

    An empty registry is a PASS here (single-model runs are governed by the
    manifest gate); the manifest gate only folds this gate in when ``models`` is
    non-empty.
    """
    models = manifest.models
    if not models:
        return GateResult.of(GATE_NAME, [])

    reasons: list[str] = []
    allowlist = set(manifest.allowed_model_ids)
    declared_ids = {m.model_id for m in models if m.model_id}

    for m in models:
        label = m.model_id or f"<{m.role.value}>"
        if not m.model_id or not m.provider:
            reasons.append(f"model undeclared (model_id/provider missing): {label}")
        if not m.model_run_id:
            reasons.append(f"model not role-bound (model_run_id missing): {label}")
        if m.model_id and m.model_id not in allowlist:
            reasons.append(f"model not allowlisted: {label}")
        if not m.rate_limit.is_set:
            reasons.append(f"model not rate-limited: {label}")
        if not m.permissions:
            reasons.append(f"model not permissioned: {label}")
        if not m.prompt_hash:
            reasons.append(f"determinism not pinned (prompt_hash missing): {label}")
        if m.parallel_tool_calls is not False:
            reasons.append(f"parallel_tool_calls must be false: {label}")
        if m.fallback_model_id:
            if m.fallback_model_id not in declared_ids:
                reasons.append(f"fallback model not declared: {m.fallback_model_id}")
            elif m.fallback_model_id not in allowlist:
                reasons.append(f"fallback model not allowlisted: {m.fallback_model_id}")

    # Required role coverage.
    present_roles = {m.role for m in models}
    for role in _REQUIRED_ROLES.get(manifest.run_type, set()):
        if role not in present_roles:
            reasons.append(f"required role missing: {role.value}")

    # Role independence: no model_run_id may back both CODING_AGENT and VERIFIER.
    coding = {m.model_run_id for m in models if m.role == ModelRole.CODING_AGENT and m.model_run_id}
    verifying = {m.model_run_id for m in models if m.role == ModelRole.VERIFIER and m.model_run_id}
    overlap = coding & verifying
    if overlap:
        reasons.append(
            "verifier model_run_id must not equal coding agent model_run_id: "
            + ", ".join(sorted(overlap))
        )

    return GateResult.of(GATE_NAME, reasons)
