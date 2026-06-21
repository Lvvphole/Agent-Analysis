"""Run manifest schema (Section 9.1).

The manifest is the immutable contract for a run. The ``manifest_gate`` is the
authority that decides whether a manifest is admissible; this model only
captures shape and field-level types. Keeping structural validation here and
*policy* validation in the gate avoids scattering the hard rules.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.constants import (
    CANONICAL_GITHUB_REPO_URL,
    CANONICAL_LOCAL_PROJECT_PATH,
    DEFAULT_MAX_AGENT_ATTEMPTS,
    DEFAULT_MAX_VERIFIER_FAILURES,
    DEFAULT_ON_EXHAUSTION,
    RunType,
)


class RunManifest(BaseModel):
    """Deterministic run manifest.

    Note on defaults: ``auto_merge`` / ``auto_deploy`` default to ``False`` and
    ``parallel_tool_calls`` to ``False`` so that an under-specified manifest is
    safe-by-default. The manifest gate still re-checks these explicitly because
    a caller may set them to ``True``.
    """

    model_config = {"extra": "forbid"}

    run_id: str = ""
    goal_id: str = ""
    task_id: str = ""
    sprint_id: str = ""
    product_backlog_item_id: str = ""
    run_type: RunType

    # Determinism controls
    temperature: float = 0
    top_p: float = 1
    seed: int = 23
    model: str = ""
    prompt_hash: str = ""
    schema_mode: str = "strict"
    tools: str = "allowlisted"
    parallel_tool_calls: bool = False

    # Release safety (Sections 6.4)
    auto_merge: bool = False
    auto_deploy: bool = False

    created_at: str = ""

    # Authority identities (Section 3)
    executor_id: str = ""
    coding_agent_id: str = ""
    coding_agent_run_id: str = ""
    verifier_id: str = ""
    verifier_run_id: str = ""

    definition_of_done_version: str = ""

    allowed_commands: list[str] = Field(default_factory=list)
    forbidden_commands: list[str] = Field(default_factory=list)
    files_in_scope: list[str] = Field(default_factory=list)
    files_out_of_scope: list[str] = Field(default_factory=list)

    # Retry budget (Section 6.9)
    max_agent_attempts: int = DEFAULT_MAX_AGENT_ATTEMPTS
    max_verifier_failures: int = DEFAULT_MAX_VERIFIER_FAILURES
    on_exhaustion: str = DEFAULT_ON_EXHAUSTION

    # Canonical identity (Section 0)
    local_project_path: str = CANONICAL_LOCAL_PROJECT_PATH
    github_repo_url: str = CANONICAL_GITHUB_REPO_URL
