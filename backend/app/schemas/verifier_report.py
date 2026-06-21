"""Verifier report schema (Section 9.6).

The verifier is the *only* authority that decides PASS. Its run id must differ
from the coding agent's run id (Section 6.3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.constants import Decision

PassFail = Literal["PASS", "FAIL"]
PassFailNA = Literal["PASS", "FAIL", "NOT_APPLICABLE"]


class StrategicProgrammingGate(BaseModel):
    model_config = {"extra": "forbid"}

    change_amplification: PassFail = "PASS"
    cognitive_load: PassFail = "PASS"
    unknown_unknowns: PassFail = "PASS"
    deep_module: PassFail = "PASS"
    interface_simplicity: PassFail = "PASS"
    error_design: PassFail = "PASS"
    duplication: PassFail = "PASS"
    scope_control: PassFail = "PASS"


class VerifierReport(BaseModel):
    model_config = {"extra": "forbid"}

    task_id: str
    run_id: str
    verifier_id: str
    verifier_run_id: str
    coding_agent_run_id: str
    same_agent_verifier_check: PassFail = "PASS"
    functional_acceptance: PassFail = "FAIL"
    test_status: PassFailNA = "NOT_APPLICABLE"
    lint_status: PassFailNA = "NOT_APPLICABLE"
    typecheck_status: PassFailNA = "NOT_APPLICABLE"
    build_status: PassFailNA = "NOT_APPLICABLE"
    scope_status: PassFail = "FAIL"
    strategic_programming_gate: StrategicProgrammingGate = Field(
        default_factory=StrategicProgrammingGate
    )
    evidence_status: PassFail = "FAIL"
    pr_gate_status: Literal["PASS", "FAIL", "NOT_READY"] = "NOT_READY"
    decision: Decision = Decision.PENDING
    failure_reasons: list[str] = Field(default_factory=list)
    required_corrections: list[str] = Field(default_factory=list)
    timestamp: str = ""
