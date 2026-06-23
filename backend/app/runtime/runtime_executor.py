"""Runtime executor — the execution spine.

Ties the workspace policy, the controlled agent provider config, and the
read-only tool runtime to the existing ``ChainExecutor`` (the outer authority).
It *executes* a registered chain end-to-end and returns a real
``ChainExecutionResult`` — it does not merge, deploy, or create a PR.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.fake_provider import FakeAnalysisAdapter
from app.agents.provider import AgentRuntimeConfig
from app.chains.chain_executor import ChainExecutor
from app.runtime.workspace_policy import WorkspacePolicy
from app.schemas.chain import ChainExecutionResult, ChainRequest
from app.schemas.model_policy import ModelRole, ModelSpec
from app.storage.artifact_store import ArtifactStore
from app.tools.policy import ToolPolicy
from app.tools.registry import ToolRegistry, build_default_tool_registry

_REPO_ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_AGENT_RUN_ID = "analysis-agent-run"


def fake_analysis_config() -> AgentRuntimeConfig:
    """A keyless, deterministic analyst provider (stub) for the runtime path."""
    spec = ModelSpec(
        model_id="fake-analyst",
        provider="fake",
        role=ModelRole.ANALYST,
        model_run_id=ANALYSIS_AGENT_RUN_ID,
    )
    return AgentRuntimeConfig(specs=[spec], adapters={"fake": FakeAnalysisAdapter()})


@dataclass
class RuntimeSettings:
    """Server-side runtime configuration (the controlled execution settings)."""

    # Artifacts live OUTSIDE the workspace so writing evidence never mutates the
    # repo under audit (the read-only compliance check snapshots the workspace).
    workspace_root: Path = _REPO_ROOT
    artifacts_root: Path = Path(tempfile.gettempdir()) / "agent_analysis_artifacts"
    provider_mode: str = "fake"  # fake | none
    # When True the server owns workspace allocation and a caller-supplied
    # execution_path is refused (Epic 3). Default False keeps dev/test behavior.
    production_mode: bool = False

    def agent_config(self) -> AgentRuntimeConfig:
        if self.provider_mode == "fake":
            return fake_analysis_config()
        return AgentRuntimeConfig()  # none: agent step SKIPs


# Module singleton used by the API. Tests construct RuntimeExecutor directly.
_SETTINGS = RuntimeSettings()


def configure(**overrides) -> RuntimeSettings:
    """Update and return the module runtime settings (used by the API/tests)."""
    for key, value in overrides.items():
        setattr(_SETTINGS, key, value)
    return _SETTINGS


def get_settings() -> RuntimeSettings:
    return _SETTINGS


@dataclass
class RuntimeExecutor:
    workspace_policy: WorkspacePolicy
    artifacts_root: Path
    agent_config: AgentRuntimeConfig = field(default_factory=AgentRuntimeConfig)
    tool_registry: ToolRegistry = field(default_factory=build_default_tool_registry)
    executor: ChainExecutor = field(default_factory=ChainExecutor)

    def execute(
        self,
        request: ChainRequest,
        *,
        execution_path: str | Path | None,
        attempt_id: str | None = None,
    ) -> ChainExecutionResult:
        repo_path = self.workspace_policy.resolve(execution_path)
        store = ArtifactStore(self.artifacts_root, attempt_id=attempt_id)
        tool_policy = ToolPolicy(self.tool_registry)
        return self.executor.execute(
            request,
            store=store,
            repo_fs_path=repo_path,
            agent_specs=self.agent_config.specs,
            agent_adapters=self.agent_config.adapters,
            tool_registry=self.tool_registry,
            tool_policy=tool_policy,
        )


def build_runtime_executor(settings: RuntimeSettings | None = None) -> RuntimeExecutor:
    settings = settings or _SETTINGS
    return RuntimeExecutor(
        workspace_policy=WorkspacePolicy(settings.workspace_root),
        artifacts_root=settings.artifacts_root,
        agent_config=settings.agent_config(),
    )
