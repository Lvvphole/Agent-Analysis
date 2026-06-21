"""Manifest gate (Section 13.1).

Validates that a run manifest is admissible. This is the first hard gate: a run
cannot start on an invalid manifest.
"""

from __future__ import annotations

from app.constants import (
    CANONICAL_GITHUB_REPO_URL,
    CANONICAL_LOCAL_PROJECT_PATH,
    RunType,
)
from app.schemas.gate_result import GateResult
from app.schemas.run_manifest import RunManifest

GATE_NAME = "manifest_gate"


def manifest_gate(manifest: RunManifest) -> GateResult:
    """Return PASS only if every hard manifest rule holds."""
    reasons: list[str] = []

    if not manifest.model:
        reasons.append("model missing")
    if not manifest.prompt_hash:
        reasons.append("prompt_hash missing")
    if manifest.schema_mode != "strict":
        reasons.append("schema_mode must be 'strict'")
    if manifest.tools != "allowlisted":
        reasons.append("tools must be 'allowlisted'")
    if manifest.parallel_tool_calls is not False:
        reasons.append("parallel_tool_calls must be false")

    # Release safety
    if manifest.auto_merge is not False:
        reasons.append("auto_merge must be false")
    if manifest.auto_deploy is not False:
        reasons.append("auto_deploy must be false")

    if not manifest.definition_of_done_version:
        reasons.append("definition_of_done_version missing")
    if not manifest.files_in_scope:
        reasons.append("files_in_scope empty")

    # Verifier identity must exist...
    if not manifest.verifier_id or not manifest.verifier_run_id:
        reasons.append("verifier identity missing")
    # ...and must be independent from the coding agent run (Section 6.3).
    if (
        manifest.coding_agent_run_id
        and manifest.verifier_run_id
        and manifest.coding_agent_run_id == manifest.verifier_run_id
    ):
        reasons.append("coding_agent_run_id must not equal verifier_run_id")

    # run_type must be a known value.
    if manifest.run_type not in (
        RunType.READ_ONLY_ANALYSIS,
        RunType.IMPLEMENTATION,
    ):
        reasons.append("run_type invalid")

    # Canonical identity (Section 0).
    if manifest.local_project_path != CANONICAL_LOCAL_PROJECT_PATH:
        reasons.append(
            "local_project_path must equal " + CANONICAL_LOCAL_PROJECT_PATH
        )
    if manifest.github_repo_url != CANONICAL_GITHUB_REPO_URL:
        reasons.append(
            "github_repo_url must equal " + CANONICAL_GITHUB_REPO_URL
        )

    return GateResult.of(GATE_NAME, reasons)
