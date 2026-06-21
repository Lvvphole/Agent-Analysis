"""Canonical project constants enforced by the deterministic harness.

These are *data* values validated inside run manifests and checkpoints. They
describe the canonical project identity and are intentionally independent of
wherever this code happens to be checked out at runtime.
"""

from __future__ import annotations

from enum import Enum

# --- Canonical project identity (Section 0) ---------------------------------
CANONICAL_LOCAL_PROJECT_PATH = r"C:\Users\Emory Harris\projects\agent-analysis"
CANONICAL_GITHUB_REPO_URL = "https://github.com/Lvvphole/Agent-Analysis"

# --- Retry budget defaults (Section 6.9) ------------------------------------
DEFAULT_MAX_AGENT_ATTEMPTS = 3
DEFAULT_MAX_VERIFIER_FAILURES = 2
DEFAULT_ON_EXHAUSTION = "BLOCKED"


class RunType(str, Enum):
    """Supported run types (Section 9.1)."""

    READ_ONLY_ANALYSIS = "READ_ONLY_ANALYSIS"
    IMPLEMENTATION = "IMPLEMENTATION"


class GateStatus(str, Enum):
    """Gate decision values (Section 13)."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class Decision(str, Enum):
    """Verifier / final decision values."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"


class ImplementationState(str, Enum):
    """Implementation state machine order (Section 7.1)."""

    INTAKE = "INTAKE"
    REFINE = "REFINE"
    PLAN = "PLAN"
    DESIGN_GATE = "DESIGN_GATE"
    AGENT_INVOKE = "AGENT_INVOKE"
    DIFF_CAPTURE = "DIFF_CAPTURE"
    TEST = "TEST"
    VERIFY = "VERIFY"
    EVALUATE = "EVALUATE"
    MEMORY_UPDATE = "MEMORY_UPDATE"
    PR_GATE = "PR_GATE"
    STOP_OR_LOOP = "STOP_OR_LOOP"


class AnalysisState(str, Enum):
    """Read-only analysis state machine order (Section 7.2)."""

    INTAKE = "INTAKE"
    REFINE = "REFINE"
    PLAN = "PLAN"
    DESIGN_GATE = "DESIGN_GATE"
    AGENT_INVOKE_READONLY = "AGENT_INVOKE_READONLY"
    EVIDENCE_CAPTURE = "EVIDENCE_CAPTURE"
    VERIFY_ANALYSIS = "VERIFY_ANALYSIS"
    EVALUATE = "EVALUATE"
    BACKLOG_UPDATE = "BACKLOG_UPDATE"
    STOP_OR_LOOP = "STOP_OR_LOOP"


# Ordered tuples used by the state machine module for transition validation.
IMPLEMENTATION_STATE_ORDER = tuple(s.value for s in ImplementationState)
ANALYSIS_STATE_ORDER = tuple(s.value for s in AnalysisState)
