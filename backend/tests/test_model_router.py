"""Role-aware model router tests: selection, permission, rate limit, fallback."""

from __future__ import annotations

from app.llm.base import ModelRouter
from app.llm.rate_limit import RateLimiter
from app.llm.recorder import LLMInvocationRecorder
from app.llm.stub_adapter import StubLLMAdapter
from app.schemas.model_policy import ModelRole, ModelSpec, RateLimit
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter

CODING = ModelSpec(
    model_id="claude-sonnet-4-6", provider="anthropic", role=ModelRole.CODING_AGENT,
    model_run_id="ca-1", permissions=["code"], prompt_hash="ph",
    rate_limit=RateLimit(requests_per_min=60), fallback_model_id="gpt-4o",
)
VERIFIER = ModelSpec(
    model_id="gpt-4o", provider="openai", role=ModelRole.VERIFIER,
    model_run_id="vr-1", permissions=["verify"], prompt_hash="ph",
    rate_limit=RateLimit(requests_per_min=60),
)


def _router(tmp_path, *, fail_for=(), limiters=None):
    store = ArtifactStore(tmp_path / "art")
    ev = EvidenceLedgerWriter(task_id="t", run_id="r")
    rec = LLMInvocationRecorder(store, ev, run_id="r", task_id="t")
    adapters = {
        "anthropic": StubLLMAdapter("anthropic", fail_for=fail_for),
        "openai": StubLLMAdapter("openai", fail_for=fail_for),
    }
    return ModelRouter([CODING, VERIFIER], adapters, rec, rate_limiters=limiters), ev


def test_selects_by_role_and_records(tmp_path):
    router, ev = _router(tmp_path)
    res = router.invoke_role(ModelRole.CODING_AGENT, "do work")
    assert res.status == "OK"
    assert res.model_id_used == "claude-sonnet-4-6"
    assert res.record is not None and res.record.used_as_evidence is False
    assert len(ev.ledger.ledger_entries) == 1


def test_permission_denied_blocks_invocation(tmp_path):
    router, ev = _router(tmp_path)
    res = router.invoke_role(ModelRole.CODING_AGENT, "x", require_permission="deploy")
    assert res.status == "PERMISSION_DENIED"
    assert res.record is None
    assert len(ev.ledger.ledger_entries) == 0


def test_fallback_on_adapter_failure(tmp_path):
    router, _ = _router(tmp_path, fail_for=("claude-sonnet-4-6",))
    res = router.invoke_role(ModelRole.CODING_AGENT, "x")
    assert res.status == "FALLBACK_USED"
    assert res.model_id_used == "gpt-4o"


def test_over_limit_uses_fallback(tmp_path):
    clock = lambda: 0.0  # frozen: no refill
    limiters = {
        "claude-sonnet-4-6": RateLimiter(1, clock=clock),
        "gpt-4o": RateLimiter(60, clock=clock),
    }
    router, _ = _router(tmp_path, limiters=limiters)
    assert router.invoke_role(ModelRole.CODING_AGENT, "x").status == "OK"
    second = router.invoke_role(ModelRole.CODING_AGENT, "x")
    assert second.status == "FALLBACK_USED"
    assert second.model_id_used == "gpt-4o"


def test_over_limit_without_fallback_throttles(tmp_path):
    clock = lambda: 0.0
    limiters = {
        "claude-sonnet-4-6": RateLimiter(60, clock=clock),
        "gpt-4o": RateLimiter(1, clock=clock),
    }
    router, _ = _router(tmp_path, limiters=limiters)
    assert router.invoke_role(ModelRole.VERIFIER, "x").status == "OK"
    throttled = router.invoke_role(ModelRole.VERIFIER, "x")
    assert throttled.status == "THROTTLED"
    assert throttled.record is None
