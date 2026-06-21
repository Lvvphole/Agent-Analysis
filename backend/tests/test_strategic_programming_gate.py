"""Strategic Programming gate tests (Sections 13.6, 19)."""

from __future__ import annotations

from app.constants import GateStatus
from app.gates.strategic_programming_gate import strategic_programming_gate

from tests.conftest import make_strategic


def test_valid_review_passes():
    assert strategic_programming_gate(make_strategic()).status == GateStatus.PASS


def test_unclear_owner_fails():
    result = strategic_programming_gate(make_strategic(responsibility_owner="  "))
    assert "responsibility owner unclear" in result.reasons


def test_single_design_option_fails():
    review = make_strategic(design_options=[])
    result = strategic_programming_gate(review)
    assert "only one design option considered" in result.reasons


def test_unjustified_selected_design_fails():
    result = strategic_programming_gate(make_strategic(selected_design="Z"))
    assert "selected design not justified" in result.reasons


def test_works_but_harder_to_change_blocks_done():
    result = strategic_programming_gate(
        make_strategic(works_but_harder_to_change=True)
    )
    assert result.status == GateStatus.FAIL
    assert "code works but makes future change harder" in result.reasons


def test_shallow_passthrough_fails():
    result = strategic_programming_gate(
        make_strategic(introduces_shallow_passthrough=True)
    )
    assert "shallow pass-through layers introduced" in result.reasons


def test_scattered_error_handling_fails():
    result = strategic_programming_gate(make_strategic(error_handling_scattered=True))
    assert "error handling scattered" in result.reasons
