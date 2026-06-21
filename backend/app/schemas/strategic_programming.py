"""Strategic Programming schema (Section 9.3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ComplexityRisks(BaseModel):
    model_config = {"extra": "forbid"}

    change_amplification: str = ""
    cognitive_load: str = ""
    unknown_unknowns: str = ""


class DesignOption(BaseModel):
    model_config = {"extra": "forbid"}

    option_id: str
    summary: str = ""
    tradeoffs: str = ""
    # "rejected" | "selected"
    rejected_or_selected: str = ""


class StrategicProgramming(BaseModel):
    """Design-quality contract for a task.

    "A task is not Done just because it works." This model captures the design
    reasoning that ``strategic_programming_gate`` evaluates.
    """

    model_config = {"extra": "forbid"}

    responsibility_owner: str = ""
    complexity_risks: ComplexityRisks = Field(default_factory=ComplexityRisks)
    design_options: list[DesignOption] = Field(default_factory=list)
    selected_design: str = ""
    interface_contract: str = ""
    complexity_hidden_where: str = ""
    errors_designed_out: list[str] = Field(default_factory=list)
    known_design_debt: list[str] = Field(default_factory=list)

    # Explicit self-assessment flags the gate consults. Defaults reflect the
    # safe ("no smell present") position; the verifier/author sets them true
    # when a smell is knowingly introduced so the gate can fail loudly.
    introduces_shallow_passthrough: bool = False
    complexity_leaks_into_callers: bool = False
    error_handling_scattered: bool = False
    invalid_states_unhandled: bool = False
    unjustified_duplication: bool = False
    increases_change_amplification: bool = False
    works_but_harder_to_change: bool = False
