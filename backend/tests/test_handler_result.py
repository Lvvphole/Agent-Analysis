"""HandlerResult validation tests (handoff Section 7, 16.2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chain import HandlerDecision, HandlerResult, HandlerStatus, HandlerType


def _valid(**overrides):
    base = dict(
        handler_name="X",
        handler_type=HandlerType.PURE_CHECK,
        status=HandlerStatus.PASS,
        decision=HandlerDecision.CONTINUE,
    )
    base.update(overrides)
    return base


def test_valid_handler_result_constructs():
    HandlerResult(**_valid())


@pytest.mark.parametrize("forbidden", ["DONE", "MERGE", "DEPLOY", "FORCE_PASS", "AUTO_PASS"])
def test_forbidden_decision_rejected(forbidden):
    with pytest.raises(ValidationError):
        HandlerResult(**_valid(decision=forbidden))


def test_missing_status_rejected():
    data = _valid()
    del data["status"]
    with pytest.raises(ValidationError):
        HandlerResult(**data)


def test_missing_handler_type_rejected():
    data = _valid()
    del data["handler_type"]
    with pytest.raises(ValidationError):
        HandlerResult(**data)


def test_unknown_handler_type_rejected():
    with pytest.raises(ValidationError):
        HandlerResult(**_valid(handler_type="SUPER_ADMIN"))


def test_decision_enum_excludes_forbidden_values():
    values = {d.value for d in HandlerDecision}
    assert values.isdisjoint({"DONE", "MERGE", "DEPLOY", "FORCE_PASS", "AUTO_PASS"})
