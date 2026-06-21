"""Scope gate tests (Sections 13.5, 19)."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.scope_gate import scope_gate


def test_in_scope_change_passes():
    result = scope_gate(
        ["backend/app/gates/manifest_gate.py"],
        files_in_scope=["backend/app/**"],
    )
    assert result.status == GateStatus.PASS


def test_out_of_scope_change_rejected():
    result = scope_gate(
        ["frontend/app/page.tsx"],
        files_in_scope=["backend/app/**"],
    )
    assert result.status == GateStatus.FAIL
    assert any("outside scope" in r for r in result.reasons)


def test_explicit_out_of_scope_rejected():
    result = scope_gate(
        ["backend/app/secrets.py"],
        files_in_scope=["backend/app/**"],
        files_out_of_scope=["backend/app/secrets.py"],
    )
    assert any("out-of-scope change without approved record" in r for r in result.reasons)


def test_approved_scope_change_allowed():
    result = scope_gate(
        ["backend/app/secrets.py"],
        files_in_scope=["backend/app/**"],
        files_out_of_scope=["backend/app/secrets.py"],
        approved_scope_changes=["backend/app/secrets.py"],
    )
    assert result.status == GateStatus.PASS


def test_harness_file_without_framework_task_rejected():
    result = scope_gate(
        ["backend/app/gates/pr_gate.py"],
        files_in_scope=["backend/app/**"],
        harness_files=["backend/app/gates/**"],
        is_framework_change_task=False,
    )
    assert any("harness file modified" in r for r in result.reasons)


def test_protected_file_without_approval_rejected():
    result = scope_gate(
        ["backend/app/constants.py"],
        files_in_scope=["backend/app/**"],
        protected_files=["backend/app/constants.py"],
    )
    assert any("protected file modified" in r for r in result.reasons)
