"""Model policy gate tests (Controlled LLM Integration Layer).

One assertion per hard rule: a declared model registry is admissible only if
every model is declared, role-bound, allowlisted, rate-limited, permissioned,
determinism-pinned, with a declared/allowlisted fallback, and the VERIFIER model
is independent from the CODING_AGENT model.
"""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.model_policy_gate import model_policy_gate
from app.schemas.model_policy import ModelRole, ModelSpec, RateLimit

from tests.conftest import make_manifest

RL = RateLimit(requests_per_min=60)


def _coding(**o) -> ModelSpec:
    base = dict(
        model_id="claude-sonnet-4-6", provider="anthropic", role=ModelRole.CODING_AGENT,
        model_run_id="ca-1", permissions=["code"], prompt_hash="ph", rate_limit=RL,
    )
    base.update(o)
    return ModelSpec(**base)


def _verifier(**o) -> ModelSpec:
    base = dict(
        model_id="gpt-4o", provider="openai", role=ModelRole.VERIFIER,
        model_run_id="vr-1", permissions=["verify"], prompt_hash="ph", rate_limit=RL,
    )
    base.update(o)
    return ModelSpec(**base)


def _manifest(models, **o):
    allow = o.pop("allowed_model_ids", [m.model_id for m in models if m.model_id])
    return make_manifest(models=models, allowed_model_ids=allow, **o)


def test_empty_registry_passes():
    assert model_policy_gate(make_manifest()).status == GateStatus.PASS


def test_valid_registry_passes():
    r = model_policy_gate(_manifest([_coding(), _verifier()]))
    assert r.status == GateStatus.PASS, r.reasons


def test_undeclared_model_fails():
    r = model_policy_gate(_manifest([_coding(model_id=""), _verifier()], allowed_model_ids=["gpt-4o"]))
    assert r.status == GateStatus.FAIL
    assert any("undeclared" in x for x in r.reasons)


def test_not_role_bound_fails():
    r = model_policy_gate(_manifest([_coding(model_run_id=""), _verifier()]))
    assert any("role-bound" in x for x in r.reasons)


def test_not_allowlisted_fails():
    r = model_policy_gate(_manifest([_coding(), _verifier()], allowed_model_ids=["gpt-4o"]))
    assert any("not allowlisted" in x for x in r.reasons)


def test_not_rate_limited_fails():
    r = model_policy_gate(_manifest([_coding(rate_limit=RateLimit()), _verifier()]))
    assert any("not rate-limited" in x for x in r.reasons)


def test_not_permissioned_fails():
    r = model_policy_gate(_manifest([_coding(permissions=[]), _verifier()]))
    assert any("not permissioned" in x for x in r.reasons)


def test_determinism_not_pinned_fails():
    r = model_policy_gate(_manifest([_coding(prompt_hash=""), _verifier()]))
    assert any("determinism not pinned" in x for x in r.reasons)


def test_parallel_tool_calls_fails():
    r = model_policy_gate(_manifest([_coding(parallel_tool_calls=True), _verifier()]))
    assert any("parallel_tool_calls must be false" in x for x in r.reasons)


def test_fallback_not_declared_fails():
    r = model_policy_gate(_manifest([_coding(fallback_model_id="ghost"), _verifier()]))
    assert any("fallback model not declared" in x for x in r.reasons)


def test_fallback_not_allowlisted_fails():
    r = model_policy_gate(
        _manifest([_coding(fallback_model_id="gpt-4o"), _verifier()],
                  allowed_model_ids=["claude-sonnet-4-6"])
    )
    assert any("fallback model not allowlisted" in x for x in r.reasons)


def test_missing_required_role_fails():
    r = model_policy_gate(_manifest([_coding()]))
    assert any("required role missing: VERIFIER" in x for x in r.reasons)


def test_verifier_equals_coding_run_id_fails():
    r = model_policy_gate(_manifest([_coding(), _verifier(model_run_id="ca-1")]))
    assert r.status == GateStatus.FAIL
    assert any("model_run_id must not equal" in x for x in r.reasons)
