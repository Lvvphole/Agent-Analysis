"""LLM invocation recorder tests.

The response narrative is context only: it is stored and hashed but NOT ledgered
as proof. Only the structured, hashed invocation record is appended to the
evidence ledger, and it carries ``used_as_evidence=False``.
"""

from __future__ import annotations

from app.llm.base import LLMResponse
from app.llm.recorder import LLMInvocationRecorder
from app.schemas.model_policy import ModelRole, ModelSpec, RateLimit
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter

SPEC = ModelSpec(
    model_id="claude-sonnet-4-6", provider="anthropic", role=ModelRole.CODING_AGENT,
    model_run_id="ca-1", permissions=["code"], prompt_hash="ph",
    rate_limit=RateLimit(requests_per_min=60),
)


def _recorder(tmp_path):
    store = ArtifactStore(tmp_path / "art")
    ev = EvidenceLedgerWriter(task_id="t", run_id="r")
    return LLMInvocationRecorder(store, ev, run_id="r", task_id="t"), ev


def test_record_is_hashed_and_quarantined(tmp_path):
    rec, ev = _recorder(tmp_path)
    response = LLMResponse(text="secret narrative", tokens_in=3, tokens_out=8)

    record = rec.record(SPEC, "implement X", response)

    assert record.used_as_evidence is False
    assert len(record.request_hash) == 64
    assert len(record.response_hash) == 64

    # Exactly one ledger entry: the structured invocation record, not the narrative.
    entries = ev.ledger.ledger_entries
    assert len(entries) == 1
    assert entries[0].artifact_type == "LLM_INVOCATION"
    assert "llm_invocation_" in entries[0].artifact_path

    # The response narrative artifact exists but is NOT ledgered as evidence.
    ledgered_paths = {e.artifact_path for e in entries}
    assert record.response_artifact_path not in ledgered_paths
