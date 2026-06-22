"""LLM invocation recorder.

Writes the request and response as hashed artifacts (the response narrative is
context only — it is stored and hashed but NOT appended to the evidence ledger
as proof), and appends the structured, hashed ``LLM_INVOCATION`` record to the
ledger. Mirrors the agent-output quarantine rule at the model layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.schemas.model_policy import LLMInvocationRecord, ModelSpec
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter

if TYPE_CHECKING:  # pragma: no cover
    from app.llm.base import LLMResponse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LLMInvocationRecorder:
    def __init__(
        self,
        store: ArtifactStore,
        evidence: EvidenceLedgerWriter,
        *,
        run_id: str,
        task_id: str,
    ) -> None:
        self.store = store
        self.evidence = evidence
        self.run_id = run_id
        self.task_id = task_id
        self._counter = 0

    def record(
        self,
        spec: ModelSpec,
        prompt: str,
        response: "LLMResponse",
        *,
        rate_limit_status: str = "OK",
    ) -> LLMInvocationRecord:
        self._counter += 1
        inv_id = f"LLM{self._counter:04d}"

        # Request + response narrative: stored and hashed for traceability, but
        # NOT ledgered as proof (narrative is context, never evidence).
        req = self.store.write(
            run_id=self.run_id, task_id=self.task_id,
            name=f"llm_request_{inv_id}.txt", data=prompt,
            artifact_type="LLM_INVOCATION", recorded_by="model_router",
        )
        resp = self.store.write(
            run_id=self.run_id, task_id=self.task_id,
            name=f"llm_response_{inv_id}.txt", data=response.text,
            artifact_type="LLM_INVOCATION", recorded_by="model_router",
        )

        record = LLMInvocationRecord(
            invocation_id=inv_id,
            model_id=spec.model_id,
            role=spec.role,
            run_id=self.run_id,
            task_id=self.task_id,
            request_hash=req.hash,
            response_hash=resp.hash,
            request_artifact_path=req.path,
            response_artifact_path=resp.path,
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
            rate_limit_status=rate_limit_status,
            used_as_evidence=False,
            recorded_by="model_router",
            timestamp=_now(),
        )

        # The structured record IS evidence: hashed + ledgered.
        rec_art = self.store.write(
            run_id=self.run_id, task_id=self.task_id,
            name=f"llm_invocation_{inv_id}.json",
            data=record.model_dump_json(indent=2),
            artifact_type="LLM_INVOCATION", recorded_by="model_router",
        )
        self.evidence.append_artifact(rec_art, result="INFO", command=f"llm:{spec.model_id}")
        return record
