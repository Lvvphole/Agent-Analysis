"""Agent runtime tests (runtime spine).

A controlled, role-bound invocation: declared model required, provider must be
available, every call recorded (hashed, ledgered, used_as_evidence=False), and
provider-unavailable BLOCKs instead of fabricating a PASS.
"""

from __future__ import annotations

import json

from app.agents.fake_provider import FakeAnalysisAdapter
from app.agents.manual_provider import ManualAnalysisAdapter
from app.agents.provider import AgentInvocationRequest
from app.agents.runtime import AgentRuntime
from app.llm.recorder import LLMInvocationRecorder
from app.schemas.model_policy import ModelRole, ModelSpec
from app.storage.evidence_writer import EvidenceLedgerWriter


def _recorder(store):
    return LLMInvocationRecorder(
        store, EvidenceLedgerWriter(task_id="task-1", run_id="run-1"), run_id="run-1", task_id="task-1"
    )


def _analyst(provider="fake"):
    return ModelSpec(model_id=f"{provider}-analyst", provider=provider, role=ModelRole.ANALYST)


def _req():
    return AgentInvocationRequest(role=ModelRole.ANALYST, prompt="assess the repo")


def test_invocation_ok_and_recorded(artifact_store):
    runtime = AgentRuntime([_analyst()], {"fake": FakeAnalysisAdapter()}, _recorder(artifact_store))
    result = runtime.invoke(_req())
    assert result.ok
    # Output is valid structured JSON.
    assert json.loads(result.text)["confidence"] == 0.5
    # The invocation record is hashed and marked not-evidence.
    assert result.record is not None
    assert result.record.request_hash and result.record.response_hash
    assert result.record.used_as_evidence is False


def test_no_model_for_role_blocks(artifact_store):
    runtime = AgentRuntime([], {"fake": FakeAnalysisAdapter()}, _recorder(artifact_store))
    result = runtime.invoke(_req())
    assert result.status == "BLOCKED"
    assert "no model bound" in result.reason


def test_provider_unavailable_blocks(artifact_store):
    # Declared model but no adapter for its provider -> BLOCKED, not PASS.
    runtime = AgentRuntime([_analyst()], {}, _recorder(artifact_store))
    result = runtime.invoke(_req())
    assert result.status == "BLOCKED"
    assert "provider unavailable" in result.reason


def test_provider_failure_blocks(artifact_store):
    # Manual provider with no supplied output raises -> BLOCKED.
    runtime = AgentRuntime([_analyst("manual")], {"manual": ManualAnalysisAdapter()}, _recorder(artifact_store))
    result = runtime.invoke(_req())
    assert result.status == "BLOCKED"
    assert "provider invocation failed" in result.reason


def test_request_prompt_hash_is_set():
    req = _req()
    assert req.prompt_hash and len(req.prompt_hash) == 64
