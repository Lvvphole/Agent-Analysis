"""The manifest gate folds in the model policy gate when models are declared."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.manifest_gate import manifest_gate
from app.schemas.model_policy import ModelRole, ModelSpec, RateLimit

from tests.conftest import make_manifest

RL = RateLimit(requests_per_min=60)


def _specs(coding_perms=("code",)):
    return [
        ModelSpec(model_id="claude-sonnet-4-6", provider="anthropic", role=ModelRole.CODING_AGENT,
                  model_run_id="ca-1", permissions=list(coding_perms), prompt_hash="ph", rate_limit=RL),
        ModelSpec(model_id="gpt-4o", provider="openai", role=ModelRole.VERIFIER,
                  model_run_id="vr-1", permissions=["verify"], prompt_hash="ph", rate_limit=RL),
    ]


def test_empty_models_preserves_behavior():
    assert manifest_gate(make_manifest()).status == GateStatus.PASS


def test_valid_registry_passes():
    m = make_manifest(models=_specs(), allowed_model_ids=["claude-sonnet-4-6", "gpt-4o"])
    r = manifest_gate(m)
    assert r.status == GateStatus.PASS, r.reasons


def test_invalid_registry_fails_via_fold():
    m = make_manifest(models=_specs(coding_perms=()), allowed_model_ids=["claude-sonnet-4-6", "gpt-4o"])
    r = manifest_gate(m)
    assert r.status == GateStatus.FAIL
    assert any("not permissioned" in x for x in r.reasons)
