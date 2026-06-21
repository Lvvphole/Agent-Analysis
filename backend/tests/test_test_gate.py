"""Test gate tests (Sections 13.4, 19)."""

from __future__ import annotations

from app.constants import GateStatus, RunType
# Alias on import so pytest does not try to collect the imported ``test_gate``
# function or the ``TestOutcome`` model as test items.
from app.gates.test_gate import TestOutcome as Outcome
from app.gates.test_gate import test_gate as run_test_gate


def _passing_outcome(**kw) -> Outcome:
    base = dict(
        command="python -m pytest -q",
        ran=True,
        exit_code=0,
        output_path="artifacts/run-1/test_output.log",
    )
    base.update(kw)
    return Outcome(**base)


def test_passing_tests_pass():
    result = run_test_gate(
        [_passing_outcome()], run_type=RunType.IMPLEMENTATION, tests_applicable=True
    )
    assert result.status == GateStatus.PASS


def test_implementation_without_tests_fails():
    result = run_test_gate([], run_type=RunType.IMPLEMENTATION, tests_applicable=True)
    assert result.status == GateStatus.FAIL
    assert any("without tests where applicable" in r for r in result.reasons)


def test_missing_exit_code_fails():
    result = run_test_gate(
        [_passing_outcome(exit_code=None)],
        run_type=RunType.IMPLEMENTATION,
        tests_applicable=True,
    )
    assert any("exit code missing" in r for r in result.reasons)


def test_claimed_without_output_fails():
    result = run_test_gate(
        [_passing_outcome(output_path="")],
        run_type=RunType.IMPLEMENTATION,
        tests_applicable=True,
    )
    assert any("without output" in r for r in result.reasons)


def test_truncated_output_fails():
    result = run_test_gate(
        [_passing_outcome(truncated=True)],
        run_type=RunType.IMPLEMENTATION,
        tests_applicable=True,
    )
    assert any("truncated" in r for r in result.reasons)


def test_nonzero_exit_fails():
    result = run_test_gate(
        [_passing_outcome(exit_code=1)],
        run_type=RunType.IMPLEMENTATION,
        tests_applicable=True,
    )
    assert any("exit code 1" in r for r in result.reasons)


def test_unapproved_skip_fails():
    result = run_test_gate(
        [_passing_outcome(skipped=True, skip_approved=False)],
        run_type=RunType.IMPLEMENTATION,
        tests_applicable=True,
    )
    assert any("skipped without approved reason" in r for r in result.reasons)


def test_readonly_without_tests_is_fine():
    # Read-only analysis with no applicable tests must not be forced to run them.
    result = run_test_gate([], run_type=RunType.READ_ONLY_ANALYSIS, tests_applicable=False)
    assert result.status == GateStatus.PASS
