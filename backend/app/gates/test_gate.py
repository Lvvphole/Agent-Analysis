"""Test gate (Section 13.4).

Verifies that required commands actually ran and produced verifiable output.
"Passing tests are required for verifier PASS, but test completion alone does
not equal Done" (Section 7.7).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.constants import RunType
from app.schemas.gate_result import GateResult

GATE_NAME = "test_gate"


class TestOutcome(BaseModel):
    """A single captured command outcome the test gate evaluates."""

    model_config = {"extra": "forbid"}

    command: str
    ran: bool = False
    exit_code: int | None = None
    output_path: str = ""
    truncated: bool = False
    skipped: bool = False
    skip_approved: bool = False


def test_gate(
    outcomes: list[TestOutcome],
    *,
    run_type: RunType,
    tests_applicable: bool,
) -> GateResult:
    """Return PASS only if required tests ran, were captured, and passed."""
    reasons: list[str] = []

    ran_any = any(o.ran for o in outcomes)

    if (
        tests_applicable
        and run_type == RunType.IMPLEMENTATION
        and not ran_any
    ):
        reasons.append(
            "implementation mode attempts PASS without tests where applicable"
        )

    for o in outcomes:
        label = o.command or o.output_path or "<command>"

        if o.skipped and not o.skip_approved:
            reasons.append(f"required test skipped without approved reason: {label}")
            continue
        if o.skipped:
            continue

        if not o.ran:
            # A non-skipped command that did not run cannot be claimed.
            reasons.append(f"test result claimed without running: {label}")
            continue
        if o.exit_code is None:
            reasons.append(f"exit code missing: {label}")
        if not o.output_path:
            reasons.append(f"test result claimed without output: {label}")
        if o.truncated:
            reasons.append(
                f"output truncated so PASS/FAIL cannot be verified: {label}"
            )
        if o.exit_code is not None and o.exit_code != 0:
            reasons.append(f"command failed with exit code {o.exit_code}: {label}")

    return GateResult.of(GATE_NAME, reasons)
