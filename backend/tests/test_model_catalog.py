"""Model catalog tests: entries are well-formed and selectable into a passing spec."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.model_policy_gate import model_policy_gate
from app.llm.catalog import MODEL_CATALOG, to_model_spec
from app.schemas.model_policy import ModelRole, RateLimit

from tests.conftest import make_manifest


def test_catalog_is_well_formed():
    providers = {e.provider for e in MODEL_CATALOG}
    assert {"anthropic", "openai"} <= providers
    for e in MODEL_CATALOG:
        assert e.model_id and e.label and e.suggested_roles
        assert e.live_calls_available is False


def test_catalog_entry_selectable_into_passing_registry():
    coding_entry = next(e for e in MODEL_CATALOG if ModelRole.CODING_AGENT in e.suggested_roles)
    verifier_entry = next(
        e for e in MODEL_CATALOG
        if ModelRole.VERIFIER in e.suggested_roles and e.model_id != coding_entry.model_id
    )
    rl = RateLimit(requests_per_min=60)
    coding = to_model_spec(
        coding_entry, role=ModelRole.CODING_AGENT, model_run_id="ca-1",
        prompt_hash="ph", permissions=["code"], rate_limit=rl,
    )
    verifier = to_model_spec(
        verifier_entry, role=ModelRole.VERIFIER, model_run_id="vr-1",
        prompt_hash="ph", permissions=["verify"], rate_limit=rl,
    )
    m = make_manifest(
        models=[coding, verifier],
        allowed_model_ids=[coding.model_id, verifier.model_id],
    )
    r = model_policy_gate(m)
    assert r.status == GateStatus.PASS, r.reasons
