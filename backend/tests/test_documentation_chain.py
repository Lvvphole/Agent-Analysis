"""Documentation update chain tests (handoff Section 11.6).

The chain runs end-to-end with pure/read-only handlers: diff required, tests
NOT_APPLICABLE, repo-relative links validated, verifier independent, PR gated.
"""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision, RunType
from app.schemas.chain import PrStatus, TaskType

from tests.conftest import STRATEGIC_DESIGN, make_chain_request

DOC_SCOPE = {"files_in_scope": ["README.md", "docs/**"], "files_out_of_scope": []}
DOC_SCRUM = {
    "product_backlog_item_id": "PBI-9",
    "sprint_goal": "improve project documentation",
    "sprint_backlog_task_id": "T-9",
    "definition_of_done_version": "dod-v1",
    "acceptance_criteria": ["README must document the setup steps"],
}


def _candidate(*, agent_run_id: str = "doc-agent"):
    return {
        "agent_run_id": agent_run_id,
        "summary": "updated docs",
        "raw_output": "...agent narrative...",
        "diff": "--- a/README.md\n+++ b/README.md\n@@\n-old\n+new\n",
        "changed_files": ["README.md"],
        "git_status": " M README.md",
        "diff_check": "",
    }


def _doc_request(metadata):
    return make_chain_request(
        task_type=TaskType.DOCUMENTATION_UPDATE,
        mode=RunType.IMPLEMENTATION,
        scope=DOC_SCOPE,
        scrum=DOC_SCRUM,
        metadata=metadata,
    )


def _doc_repo(tmp_path, *, link="docs/guide.md", create_target=True):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    if create_target:
        (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "README.md").write_text(
        f"# Project\n\nSee [the guide]({link}) and [the site](https://example.com).\n"
    )
    return repo


def _run(store, repo, metadata):
    return ChainExecutor().execute(_doc_request(metadata), store=store, repo_fs_path=repo)


def test_passes_with_diff_and_evidence(tmp_path, artifact_store):
    repo = _doc_repo(tmp_path)
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": _candidate(),
        "tests_not_applicable": True,
        "tests_not_applicable_reason": "documentation only",
    }
    result = _run(artifact_store, repo, metadata)
    assert result.final_status == "PASS", [
        (h.handler_name, h.status.value, h.failure_reasons) for h in result.handler_results
    ]
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False
    # Agent narrative is context only: written to the store, never ledgered.
    assert (artifact_store.run_dir("run-1") / "agent_summary.md").exists()
    quarantine = next(
        h for h in result.handler_results if h.handler_name == "AgentOutputQuarantineHandler"
    )
    assert quarantine.status.value == "PASS"


def test_broken_internal_link_fails(tmp_path, artifact_store):
    repo = _doc_repo(tmp_path, link="docs/missing.md", create_target=False)
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": _candidate(),
        "tests_not_applicable": True,
    }
    result = _run(artifact_store, repo, metadata)
    assert result.final_status == "FAIL"
    assert result.verifier_decision != Decision.PASS
    link = next(h for h in result.handler_results if h.handler_name == "LinkCheckHandler")
    assert link.status.value == "FAIL"
    assert any("missing.md" in r for r in link.failure_reasons)


def test_requires_independent_verifier(tmp_path, artifact_store):
    # Coding-agent run id collides with the doc verifier id -> verifier FAIL.
    repo = _doc_repo(tmp_path)
    metadata = {
        "strategic_design": STRATEGIC_DESIGN,
        "manual_candidate": _candidate(agent_run_id="doc-verifier"),
        "tests_not_applicable": True,
    }
    result = _run(artifact_store, repo, metadata)
    assert result.verifier_decision == Decision.FAIL
    assert result.final_status != "PASS"


def test_documentation_handlers_registered():
    from app.handlers.base import build_default_registry

    registry = build_default_registry()
    for name in ("DocumentationGapHandler", "LinkCheckHandler", "DocumentationVerifierHandler"):
        assert registry.has(name), name
    # With the SECURITY_REVIEW chain implemented, no chain handler remains deferred:
    # every handler referenced by every registered chain now resolves.
    for name in (
        "SecretScanHandler",
        "DependencyVulnerabilityHandler",
        "AuthChangeRiskHandler",
        "InputValidationRiskHandler",
        "SecurityVerifierHandler",
    ):
        assert registry.has(name), name
