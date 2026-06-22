"""Dependency-update chain tests (handoff Section 11.5).

The DEPENDENCY_UPDATE chain reuses the proven implementation pipeline + verifier
and adds four deterministic steps: lockfile validation, caller-supplied advisory
risk, caller-supplied license policy, and a build step. Like every chain it ends
in an independent-verifier PASS and a gated PR.
"""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision, RunType
from app.schemas.chain import PrStatus, TaskType

from tests.conftest import MANUAL_CANDIDATE, STRATEGIC_DESIGN, make_chain_request

DEP_SCOPE = {"files_in_scope": ["backend/**"], "files_out_of_scope": []}
DEP_SCRUM = {
    "product_backlog_item_id": "PBI-5",
    "sprint_goal": "update project dependencies safely",
    "sprint_backlog_task_id": "T-5",
    "definition_of_done_version": "dod-v1",
    "acceptance_criteria": ["dependency bump must keep the suite green"],
}


def _candidate(changed_files, *, agent_run_id="dep-agent"):
    return {
        "agent_run_id": agent_run_id,
        "summary": "bumped dependencies",
        "raw_output": "...agent narrative...",
        "diff": "--- a/backend/requirements.txt\n+++ b/backend/requirements.txt\n@@\n-x==1\n+x==2\n",
        "changed_files": changed_files,
        "git_status": " M " + changed_files[0],
        "diff_check": "",
    }


def _dep_request(metadata):
    return make_chain_request(
        task_type=TaskType.DEPENDENCY_UPDATE,
        mode=RunType.IMPLEMENTATION,
        scope=DEP_SCOPE,
        scrum=DEP_SCRUM,
        metadata=metadata,
    )


def _run(store, repo, metadata):
    return ChainExecutor().execute(_dep_request(metadata), store=store, repo_fs_path=repo)


def _base_metadata(changed_files=("backend/requirements.txt",), **overrides):
    meta = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": _candidate(list(changed_files)),
        "test_outcomes": [{"command": "python -m pytest", "exit_code": 0}],
    }
    meta.update(overrides)
    return meta


def test_full_path_gates_pr(temp_repo, artifact_store):
    # requirements.txt alone needs no lockfile; risk/license/build SKIP-with-reason.
    result = _run(artifact_store, temp_repo, _base_metadata())
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False
    skipped = {
        h.handler_name
        for h in result.handler_results
        if h.status.value == "SKIPPED"
    }
    assert {"DependencyRiskHandler", "LicenseCheckHandler", "BuildHandler"} <= skipped


def test_manifest_without_lockfile_fails(temp_repo, artifact_store):
    meta = _base_metadata(changed_files=("backend/package.json",))
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status != "PASS"
    lock = next(h for h in result.handler_results if h.handler_name == "LockfileValidationHandler")
    assert lock.status.value == "FAIL"
    assert any("package-lock.json" in r for r in lock.failure_reasons)


def test_manifest_with_lockfile_passes(temp_repo, artifact_store):
    meta = _base_metadata(changed_files=("backend/package.json", "backend/package-lock.json"))
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]


def test_blocking_advisory_fails(temp_repo, artifact_store):
    meta = _base_metadata(dependency_risk={
        "advisories": [{"package": "x", "id": "CVE-1", "severity": "CRITICAL"}]
    })
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status != "PASS"
    risk = next(h for h in result.handler_results if h.handler_name == "DependencyRiskHandler")
    assert risk.status.value == "FAIL"
    assert any("CVE-1" in r for r in risk.failure_reasons)


def test_waived_advisory_passes(temp_repo, artifact_store):
    meta = _base_metadata(dependency_risk={
        "advisories": [{"package": "x", "id": "CVE-1", "severity": "CRITICAL", "waived": True}]
    })
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status == "PASS"
    risk = next(h for h in result.handler_results if h.handler_name == "DependencyRiskHandler")
    assert risk.status.value == "PASS"


def test_denied_license_fails(temp_repo, artifact_store):
    meta = _base_metadata(license_check={
        "licenses": {"x": "GPL-3.0"}, "denied": ["GPL-3.0"]
    })
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status != "PASS"
    lic = next(h for h in result.handler_results if h.handler_name == "LicenseCheckHandler")
    assert lic.status.value == "FAIL"
    assert any("GPL-3.0" in r for r in lic.failure_reasons)


def test_failing_build_fails(temp_repo, artifact_store):
    meta = _base_metadata(build_outcomes=[{"command": "make build", "exit_code": 1}])
    result = _run(artifact_store, temp_repo, meta)
    assert result.final_status != "PASS"
    build = next(h for h in result.handler_results if h.handler_name == "BuildHandler")
    assert build.status.value == "FAIL"


def test_dependency_handlers_registered():
    from app.handlers.base import build_default_registry

    registry = build_default_registry()
    for name in (
        "LockfileValidationHandler",
        "DependencyRiskHandler",
        "LicenseCheckHandler",
        "BuildHandler",
    ):
        assert registry.has(name), name
