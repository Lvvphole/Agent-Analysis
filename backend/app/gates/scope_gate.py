"""Scope gate (Section 13.5).

Ensures a diff only touches approved files. Scope must never expand silently.
"""

from __future__ import annotations

from fnmatch import fnmatch

from app.schemas.gate_result import GateResult

GATE_NAME = "scope_gate"


def _matches_any(path: str, patterns: list[str]) -> bool:
    norm = path.replace("\\", "/")
    return any(fnmatch(norm, p.replace("\\", "/")) for p in patterns)


def scope_gate(
    changed_files: list[str],
    *,
    files_in_scope: list[str],
    files_out_of_scope: list[str] | None = None,
    approved_scope_changes: list[str] | None = None,
    protected_files: list[str] | None = None,
    harness_files: list[str] | None = None,
    is_framework_change_task: bool = False,
) -> GateResult:
    """Return PASS only if every changed file is within approved scope."""
    files_out_of_scope = files_out_of_scope or []
    approved = approved_scope_changes or []
    protected_files = protected_files or []
    harness_files = harness_files or []

    reasons: list[str] = []

    for path in changed_files:
        approved_change = _matches_any(path, approved)

        # Harness files require a dedicated framework-change task (Section 6.10).
        if _matches_any(path, harness_files) and not is_framework_change_task:
            reasons.append(f"harness file modified without framework-change task: {path}")
            continue

        # Protected files require explicit approval.
        if _matches_any(path, protected_files) and not approved_change:
            reasons.append(f"protected file modified without approval: {path}")
            continue

        # Explicitly out-of-scope files require an approved scope-change record.
        if _matches_any(path, files_out_of_scope) and not approved_change:
            reasons.append(f"out-of-scope change without approved record: {path}")
            continue

        # Anything not matching the in-scope allowlist is silent scope creep.
        if not _matches_any(path, files_in_scope) and not approved_change:
            reasons.append(f"file outside scope: {path}")

    return GateResult.of(GATE_NAME, reasons)
