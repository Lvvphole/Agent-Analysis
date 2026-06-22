"""Handler type authority matrix (handoff Section 8).

Encoded as data + pure predicates so the executor and the tests share one source
of truth. merge and deploy are False for every handler type — by construction,
nothing in this system can merge or deploy.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.chain import HandlerType


@dataclass(frozen=True)
class Authority:
    modify_repo: bool
    decide_pass: bool
    create_pr: bool
    merge: bool
    deploy: bool


AUTHORITY: dict[HandlerType, Authority] = {
    HandlerType.PURE_CHECK: Authority(False, False, False, False, False),
    HandlerType.READ_ONLY_COMMAND: Authority(False, False, False, False, False),
    HandlerType.WRITE_COMMAND: Authority(True, False, False, False, False),
    HandlerType.AGENT_INVOCATION: Authority(True, False, False, False, False),
    HandlerType.VERIFIER: Authority(False, True, False, False, False),
    HandlerType.PR_ACTION: Authority(False, False, True, False, False),
    HandlerType.EVALUATOR: Authority(False, False, False, False, False),
}


def can_modify_repo(handler_type: HandlerType) -> bool:
    return AUTHORITY[handler_type].modify_repo


def can_decide_pass(handler_type: HandlerType) -> bool:
    return AUTHORITY[handler_type].decide_pass


def can_create_pr(handler_type: HandlerType) -> bool:
    return AUTHORITY[handler_type].create_pr


def can_merge(handler_type: HandlerType) -> bool:  # always False
    return AUTHORITY[handler_type].merge


def can_deploy(handler_type: HandlerType) -> bool:  # always False
    return AUTHORITY[handler_type].deploy
