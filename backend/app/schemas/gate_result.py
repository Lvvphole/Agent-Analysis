"""Canonical gate output (Section 13).

Every gate is a pure function returning this typed structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.constants import GateStatus


class GateResult(BaseModel):
    """Typed output of every gate.

    A gate never mutates state; it only reports a decision and the reasons
    behind it. The orchestrator is responsible for acting on the result.
    """

    model_config = {"frozen": True}

    gate_name: str
    status: GateStatus
    reasons: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS

    @classmethod
    def of(
        cls,
        gate_name: str,
        reasons: list[str],
        *,
        blocked: bool = False,
        required_corrections: list[str] | None = None,
    ) -> "GateResult":
        """Build a result from a list of failure reasons.

        Empty ``reasons`` => PASS. Non-empty => FAIL (or BLOCKED if ``blocked``).
        This keeps every gate body to a single ``reasons`` accumulator and
        designs the PASS/FAIL branching out of the call sites.
        """
        if reasons:
            status = GateStatus.BLOCKED if blocked else GateStatus.FAIL
        else:
            status = GateStatus.PASS
        return cls(
            gate_name=gate_name,
            status=status,
            reasons=reasons,
            required_corrections=required_corrections or [],
        )
