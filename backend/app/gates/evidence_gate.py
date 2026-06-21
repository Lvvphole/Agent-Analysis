"""Evidence gate (Section 13.3).

Decides whether the evidence ledger can support a PASS. Agent narrative is
never evidence; every supporting artifact must be hashed and linked.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.schemas.evidence_ledger import EvidenceLedger
from app.schemas.gate_result import GateResult

GATE_NAME = "evidence_gate"

# Agent output is context only and must never appear as a ledger evidence
# entry (Section 6.2 quarantine rule).
_QUARANTINED_BASENAMES = ("agent_summary.md", "raw_agent_output.log")


def _basename(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def evidence_gate(
    ledger: EvidenceLedger,
    *,
    run_id: str,
    task_id: str,
    required_artifact_types: Iterable[str] = (),
) -> GateResult:
    """Return PASS only if the ledger is complete, hashed, and linked."""
    reasons: list[str] = []

    # The whole ledger must be linked to this run/task.
    if not ledger.run_id or ledger.run_id != run_id:
        reasons.append("ledger not linked to run_id")
    if not ledger.task_id or ledger.task_id != task_id:
        reasons.append("ledger not linked to task_id")

    # Self-certification can never support PASS.
    if ledger.agent_self_certification_used:
        reasons.append("agent self-certification used as evidence")

    seen_entry_ids: set[str] = set()
    present_types: set[str] = set()

    for entry in ledger.ledger_entries:
        present_types.add(entry.artifact_type)
        label = entry.entry_id or entry.artifact_path or entry.artifact_type

        # Quarantine: agent narrative is not evidence.
        if _basename(entry.artifact_path) in _QUARANTINED_BASENAMES:
            reasons.append(f"agent summary used as proof: {label}")

        # Every artifact must be hashed. INFO entries that merely annotate are
        # still required to carry a hash so they cannot masquerade as proof.
        if not entry.hash:
            reasons.append(f"artifact hash missing: {label}")

        # A claimed command must have captured output.
        if entry.command and not entry.artifact_path:
            reasons.append(f"command output missing for claimed command: {label}")

        # In-place mutation (duplicate entry id) without a correction entry.
        if entry.entry_id and entry.entry_id in seen_entry_ids:
            reasons.append(f"ledger mutated in place without correction: {label}")
        if entry.entry_id:
            seen_entry_ids.add(entry.entry_id)

    for required in required_artifact_types:
        if required not in present_types:
            reasons.append(f"required artifact missing: {required}")

    return GateResult.of(GATE_NAME, reasons)
