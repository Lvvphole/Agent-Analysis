"""PR gate tests (Sections 13.8, 6.4, 6.6, 19)."""

from __future__ import annotations

from app.constants import Decision, GateStatus
from app.gates.pr_gate import pr_gate


def test_gated_pr_after_pass_passes():
    result = pr_gate(
        verifier_decision=Decision.PASS,
        pr_url="https://github.com/Lvvphole/Agent-Analysis/pull/1",
    )
    assert result.status == GateStatus.PASS


def test_documented_skip_passes():
    result = pr_gate(verifier_decision=Decision.PASS, pr_skip_reason="no remote in CI")
    assert result.status == GateStatus.PASS


def test_missing_pr_after_pass_fails():
    result = pr_gate(verifier_decision=Decision.PASS)
    assert result.status == GateStatus.FAIL
    assert any("PR missing after verifier PASS" in r for r in result.reasons)


def test_auto_merge_prevented():
    result = pr_gate(verifier_decision=Decision.PASS, pr_url="u", auto_merge=True)
    assert result.status == GateStatus.FAIL
    assert "auto_merge must be false" in result.reasons


def test_auto_deploy_prevented():
    result = pr_gate(verifier_decision=Decision.PASS, pr_url="u", auto_deploy=True)
    assert result.status == GateStatus.FAIL
    assert "auto_deploy must be false" in result.reasons


def test_merge_inside_loop_prevented():
    result = pr_gate(verifier_decision=Decision.PASS, pr_url="u", merge_occurred=True)
    assert "merge occurred inside autonomous loop" in result.reasons


def test_deploy_inside_loop_prevented():
    result = pr_gate(verifier_decision=Decision.PASS, pr_url="u", deploy_occurred=True)
    assert "deploy occurred inside autonomous loop" in result.reasons


def test_protected_branch_push_prevented():
    result = pr_gate(
        verifier_decision=Decision.PASS, pr_url="u", pushed_to_protected_branch=True
    )
    assert "PR bypasses protected branch rules" in result.reasons
