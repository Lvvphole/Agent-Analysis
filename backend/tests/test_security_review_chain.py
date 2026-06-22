"""Security-review chain tests (handoff Section 11.4).

SECURITY_REVIEW has no agent stage: ``DiffCaptureHandler`` captures the working
tree via the git runner, and the scan handlers review the changed files. The
chain runs deterministically — secrets / dangerous sinks / unacknowledged auth
changes FAIL, a clean diff reaches an independent verifier PASS and a gated PR.
"""

from __future__ import annotations

import subprocess

import pytest

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision, RunType
from app.schemas.chain import PrStatus, TaskType

from tests.conftest import make_chain_request

SEC_SCOPE = {"files_in_scope": ["backend/**"], "files_out_of_scope": []}
SEC_SCRUM = {
    "product_backlog_item_id": "PBI-4",
    "sprint_goal": "review changes for security risks",
    "sprint_backlog_task_id": "T-4",
    "definition_of_done_version": "dod-v1",
    "acceptance_criteria": ["the diff must contain no hardcoded secrets"],
}


@pytest.fixture
def review_repo(tmp_path):
    """An initialised git repo with a committed baseline; tests add a changed
    file under backend/app/ to drive the working-tree capture."""
    repo = tmp_path / "repo"
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "backend" / "app" / "base.py").write_text("x = 1\n")

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
            check=True,
            capture_output=True,
        )

    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return repo


def _change(repo, name, content):
    (repo / "backend" / "app" / name).write_text(content)


def _request(metadata):
    return make_chain_request(
        task_type=TaskType.SECURITY_REVIEW,
        mode=RunType.IMPLEMENTATION,
        scope=SEC_SCOPE,
        scrum=SEC_SCRUM,
        metadata=metadata,
    )


def _run(store, repo, metadata):
    return ChainExecutor().execute(_request(metadata), store=store, repo_fs_path=repo)


def _meta(**overrides):
    # Caller does NOT set tests_not_applicable: the chain's
    # SecurityReviewTestsNotApplicableHandler declares it before the evidence gate.
    meta = {}
    meta.update(overrides)
    return meta


def test_clean_diff_gates_pr(review_repo, artifact_store):
    _change(review_repo, "feature.py", "def add(a, b):\n    return a + b\n")
    result = _run(artifact_store, review_repo, _meta())
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False


def test_hardcoded_secret_fails(review_repo, artifact_store):
    _change(review_repo, "creds.py", 'API_KEY = "abcd1234efgh5678ijkl"\n')
    result = _run(artifact_store, review_repo, _meta())
    assert result.final_status != "PASS"
    scan = next(h for h in result.handler_results if h.handler_name == "SecretScanHandler")
    assert scan.status.value == "FAIL"
    assert any("creds.py" in r for r in scan.failure_reasons)


def test_dangerous_sink_fails(review_repo, artifact_store):
    _change(review_repo, "run.py", "def go(cmd):\n    return eval(cmd)\n")
    result = _run(artifact_store, review_repo, _meta())
    assert result.final_status != "PASS"
    risk = next(h for h in result.handler_results if h.handler_name == "InputValidationRiskHandler")
    assert risk.status.value == "FAIL"
    assert any("eval()" in r for r in risk.failure_reasons)


def test_unacknowledged_auth_change_fails(review_repo, artifact_store):
    _change(review_repo, "auth.py", "def check(session):\n    return session.permission\n")
    result = _run(artifact_store, review_repo, _meta())
    assert result.final_status != "PASS"
    auth = next(h for h in result.handler_results if h.handler_name == "AuthChangeRiskHandler")
    assert auth.status.value == "FAIL"


def test_acknowledged_auth_change_passes(review_repo, artifact_store):
    _change(review_repo, "auth.py", "def check(session):\n    return session.permission\n")
    result = _run(artifact_store, review_repo, _meta(security_ack={"auth_change_reviewed": True}))
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    auth = next(h for h in result.handler_results if h.handler_name == "AuthChangeRiskHandler")
    assert auth.status.value == "PASS"


def test_blocking_vulnerability_fails(review_repo, artifact_store):
    _change(review_repo, "feature.py", "def add(a, b):\n    return a + b\n")
    result = _run(artifact_store, review_repo, _meta(dependency_vulnerabilities={
        "advisories": [{"package": "x", "id": "CVE-9", "severity": "CRITICAL"}]
    }))
    assert result.final_status != "PASS"
    vuln = next(h for h in result.handler_results if h.handler_name == "DependencyVulnerabilityHandler")
    assert vuln.status.value == "FAIL"
    assert any("CVE-9" in r for r in vuln.failure_reasons)


def test_requires_independent_verifier(review_repo, artifact_store):
    # Colliding coding-agent / verifier run ids would fail no-self-certification;
    # here there is no agent, so the gate passes on independence by construction.
    _change(review_repo, "feature.py", "def add(a, b):\n    return a + b\n")
    result = _run(artifact_store, review_repo, _meta())
    verifier = next(h for h in result.handler_results if h.handler_name == "SecurityVerifierHandler")
    assert verifier.status.value == "PASS"


def test_reaches_verifier_without_caller_test_flag(review_repo, artifact_store):
    # Regression for the P2 review: a SECURITY_REVIEW request that supplies NO
    # test evidence and does NOT set tests_not_applicable must still pass the
    # evidence gate and reach the independent verifier — the chain handler
    # declares tests NOT_APPLICABLE before EvidenceGateHandler.
    _change(review_repo, "feature.py", "def add(a, b):\n    return a + b\n")
    result = _run(artifact_store, review_repo, {})  # no metadata at all

    by_name = {h.handler_name: h for h in result.handler_results}
    decl = by_name["SecurityReviewTestsNotApplicableHandler"]
    assert decl.status.value == "PASS"
    assert decl.metadata.get("tests_not_applicable") is True
    # Evidence gate did NOT fail for a missing TEST artifact.
    assert by_name["EvidenceGateHandler"].status.value == "PASS"
    # The independent verifier ran and certified.
    assert "SecurityVerifierHandler" in by_name
    assert by_name["SecurityVerifierHandler"].status.value == "PASS"
    assert result.verifier_decision == Decision.PASS
    assert result.final_status == "PASS"
    # The declaration is recorded as a hashed artifact (not a fabricated test).
    assert any("security_review_tests_not_applicable" in a for a in decl.artifacts_created)
    # Preserved hard rules: gated PR, never auto-merged/deployed.
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False


def test_declaration_scoped_to_security_review():
    # The handler must not weaken non-security chains: on any other task type it
    # is a no-op (SKIPPED) and never sets tests_not_applicable.
    from app.handlers.security import SecurityReviewTestsNotApplicableHandler
    from app.schemas.chain import ChainRequest

    handler = SecurityReviewTestsNotApplicableHandler()

    class _Ctx:
        pass

    req = ChainRequest(task_type=TaskType.IMPLEMENTATION, mode=RunType.IMPLEMENTATION)
    result = handler.handle(req, _Ctx())
    assert result.status.value == "SKIPPED"
    assert "tests_not_applicable" not in req.metadata


def test_security_handlers_registered():
    from app.handlers.base import build_default_registry

    registry = build_default_registry()
    for name in (
        "SecurityReviewTestsNotApplicableHandler",
        "SecretScanHandler",
        "DependencyVulnerabilityHandler",
        "AuthChangeRiskHandler",
        "InputValidationRiskHandler",
        "SecurityVerifierHandler",
    ):
        assert registry.has(name), name
