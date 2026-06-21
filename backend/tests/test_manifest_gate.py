"""Manifest gate tests (Sections 13.1, 19)."""

from __future__ import annotations

from app.constants import CANONICAL_GITHUB_REPO_URL, GateStatus
from app.gates.manifest_gate import manifest_gate

from tests.conftest import make_manifest


def test_valid_manifest_passes(manifest):
    result = manifest_gate(manifest)
    assert result.status == GateStatus.PASS, result.reasons


def test_missing_model_fails():
    result = manifest_gate(make_manifest(model=""))
    assert result.status == GateStatus.FAIL
    assert "model missing" in result.reasons


def test_missing_prompt_hash_fails():
    result = manifest_gate(make_manifest(prompt_hash=""))
    assert "prompt_hash missing" in result.reasons


def test_auto_merge_true_fails():
    result = manifest_gate(make_manifest(auto_merge=True))
    assert result.status == GateStatus.FAIL
    assert "auto_merge must be false" in result.reasons


def test_auto_deploy_true_fails():
    result = manifest_gate(make_manifest(auto_deploy=True))
    assert result.status == GateStatus.FAIL
    assert "auto_deploy must be false" in result.reasons


def test_parallel_tool_calls_true_fails():
    result = manifest_gate(make_manifest(parallel_tool_calls=True))
    assert "parallel_tool_calls must be false" in result.reasons


def test_schema_mode_not_strict_fails():
    result = manifest_gate(make_manifest(schema_mode="lenient"))
    assert "schema_mode must be 'strict'" in result.reasons


def test_tools_not_allowlisted_fails():
    result = manifest_gate(make_manifest(tools="all"))
    assert "tools must be 'allowlisted'" in result.reasons


def test_missing_dod_version_fails():
    result = manifest_gate(make_manifest(definition_of_done_version=""))
    assert "definition_of_done_version missing" in result.reasons


def test_empty_files_in_scope_fails():
    result = manifest_gate(make_manifest(files_in_scope=[]))
    assert "files_in_scope empty" in result.reasons


def test_missing_verifier_identity_fails():
    result = manifest_gate(make_manifest(verifier_id="", verifier_run_id=""))
    assert "verifier identity missing" in result.reasons


def test_same_agent_verifier_fails():
    result = manifest_gate(
        make_manifest(coding_agent_run_id="same", verifier_run_id="same")
    )
    assert result.status == GateStatus.FAIL
    assert "coding_agent_run_id must not equal verifier_run_id" in result.reasons


def test_incorrect_local_path_fails():
    result = manifest_gate(make_manifest(local_project_path="/tmp/wrong"))
    assert result.status == GateStatus.FAIL
    assert any("local_project_path" in r for r in result.reasons)


def test_incorrect_github_url_fails():
    result = manifest_gate(
        make_manifest(github_repo_url="https://github.com/evil/repo")
    )
    assert result.status == GateStatus.FAIL
    assert any("github_repo_url" in r for r in result.reasons)


def test_canonical_url_constant_is_enforced(manifest):
    assert manifest.github_repo_url == CANONICAL_GITHUB_REPO_URL
