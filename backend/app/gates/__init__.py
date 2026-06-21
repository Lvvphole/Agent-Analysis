"""Deterministic gates (Section 13).

Every gate is a pure function: typed input -> ``GateResult``. Gates never
mutate state, perform I/O, or trust agent narrative.
"""

from app.gates.evidence_gate import evidence_gate
from app.gates.manifest_gate import manifest_gate
from app.gates.no_self_certification_gate import no_self_certification_gate
from app.gates.pr_gate import pr_gate
from app.gates.scope_gate import scope_gate
from app.gates.scrum_gate import scrum_gate
from app.gates.strategic_programming_gate import strategic_programming_gate
from app.gates.test_gate import test_gate

__all__ = [
    "evidence_gate",
    "manifest_gate",
    "no_self_certification_gate",
    "pr_gate",
    "scope_gate",
    "scrum_gate",
    "strategic_programming_gate",
    "test_gate",
]
