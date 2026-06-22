"""Analysis handlers (handoff Section 11.1, 15).

These reuse the existing read-only analysis logic from
``workflows/analysis_workflow`` rather than re-implementing it, so the proven
inventory / discovery / scoring behavior stays the single source of truth.
"""

from __future__ import annotations

import json

from app.agents.provider import AgentInvocationRequest
from app.agents.runtime import AgentRuntime
from app.chains.context import ChainContext, snapshot_repo
from app.handlers.base import Handler
from app.llm.recorder import LLMInvocationRecorder
from app.parsing.quarantine import quarantine_agent_output
from app.parsing.structured_parser import parse_structured_output
from app.schemas.chain import ChainRequest, HandlerType
from app.schemas.model_policy import ModelRole
from app.tools.executor import ToolExecutor
from app.workflows.analysis_workflow import (
    _assess_readiness,
    _discover_commands,
    _inventory,
)

# Read-only tools the analysis agent step runs through the controlled tool
# runtime to build its (advisory) prompt context.
_AGENT_TOOLS = ("list_repo_tree", "discover_commands", "inspect_ci_config", "inspect_dependencies")


class RepoInventoryHandler(Handler):
    name = "RepoInventoryHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        rows = _inventory(context.repo_fs_path)
        context.shared["files"] = set(rows)
        art = context.record_artifact(
            name="repo_tree.log",
            data="\n".join(rows) + "\n",
            artifact_type="ANALYSIS_REPORT",
            command="inventory",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class CommandDiscoveryHandler(Handler):
    name = "CommandDiscoveryHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files", set())
        commands = _discover_commands(files)
        context.shared["commands"] = commands
        art = context.record_artifact(
            name="command_discovery.log",
            data=json.dumps(commands, indent=2),
            artifact_type="ANALYSIS_REPORT",
            command="discover_commands",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class CIInventoryHandler(Handler):
    name = "CIInventoryHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files", set())
        ci = sorted(f for f in files if f.replace("\\", "/").startswith(".github/workflows/"))
        art = context.record_artifact(
            name="ci_inventory.log",
            data=json.dumps({"workflows": ci, "has_ci": bool(ci)}, indent=2),
            artifact_type="ANALYSIS_REPORT",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class DependencyInventoryHandler(Handler):
    name = "DependencyInventoryHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    _MARKERS = (
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "poetry.lock",
    )

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files", set())
        deps = sorted(f for f in files if f.rsplit("/", 1)[-1] in self._MARKERS)
        art = context.record_artifact(
            name="dependency_inventory.log",
            data=json.dumps({"dependency_files": deps}, indent=2),
            artifact_type="ANALYSIS_REPORT",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class ReadOnlyComplianceHandler(Handler):
    name = "ReadOnlyComplianceHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        current = snapshot_repo(context.repo_fs_path)
        if current != context.repo_snapshot:
            changed = sorted(
                set(current) ^ set(context.repo_snapshot)
                | {k for k in current if context.repo_snapshot.get(k) != current[k]}
            )
            return self._fail(
                ["read-only mode modified repository files: " + ", ".join(changed)]
            )
        return self._ok()


class AnalysisAgentInvocationHandler(Handler):
    """Optional controlled analyst step. Runs read-only tools through the tool
    runtime, invokes the declared ANALYST model via the agent runtime, and
    quarantines the raw output. The agent only informs context — it never
    decides PASS and never enters the evidence ledger as proof.

    Read-only authority (not AGENT_INVOCATION) so repo mutation is forbidden. If
    no agent is configured for the run it SKIPs; if a provider is configured but
    unavailable it BLOCKs (never a fabricated PASS).
    """

    name = "AnalysisAgentInvocationHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        if not context.agent_specs:
            return self._skip("no analysis agent configured; deterministic analysis only")

        # Run read-only repo tools through the controlled tool runtime.
        tool_summaries: list[str] = []
        if context.tool_registry is not None and context.tool_policy is not None:
            executor = ToolExecutor(context.tool_registry, context.tool_policy)
            for tool_name in _AGENT_TOOLS:
                if not context.tool_registry.has(tool_name):
                    continue
                res = executor.run(context, tool_name, request.mode)
                tool_summaries.append(f"{tool_name}: {res.status} ({res.artifact_hash[:12]})")

        prompt = (
            "Assess this repository's AI-readiness. Respond as strict JSON with keys "
            "summary, risks, recommended_actions, confidence.\n"
            f"tool_runs: {json.dumps(tool_summaries)}\n"
            f"readiness: {json.dumps(context.readiness_report)}"
        )

        recorder = LLMInvocationRecorder(
            context.store, context.evidence, run_id=context.run_id, task_id=context.task_id
        )
        runtime = AgentRuntime(context.agent_specs, context.agent_adapters, recorder)
        result = runtime.invoke(
            AgentInvocationRequest(role=ModelRole.ANALYST, prompt=prompt)
        )
        if not result.ok:
            return self._fail([result.reason], blocked=True)

        quarantine_agent_output(
            context,
            raw_output=result.text,
            summary="Advisory analyst output (context only, never evidence).",
            recorded_by=self.name,
        )
        context.shared["agent_raw_output"] = result.text
        # Independence: the analyst's run id must differ from the verifier's.
        context.coding_agent_run_id = result.model_id_used or "analysis-agent"
        return self._ok(metadata={"used_as_evidence": False, "model_id": result.model_id_used})


class StructuredOutputParserHandler(Handler):
    """Validate the analyst's raw output against a strict schema. Malformed
    output BLOCKs. The parsed structure is advisory context only (stored
    quarantined, never ledgered as proof). Skips when no agent output exists."""

    name = "StructuredOutputParserHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        raw = context.shared.get("agent_raw_output")
        if raw is None:
            return self._skip("no agent output to parse (agent step skipped)")
        parsed = parse_structured_output(raw)
        if parsed is None:
            return self._fail(
                ["malformed structured model output; cannot validate analyst response"],
                blocked=True,
            )
        context.shared["analysis_agent"] = parsed.model_dump()
        # Advisory context: stored + hashed, but NOT ledgered as proof.
        context.write_quarantined(
            name="structured_agent_output.json",
            data=parsed.model_dump_json(indent=2),
            recorded_by=self.name,
        )
        return self._ok(metadata={"confidence": parsed.confidence})


class AIReadinessScoringHandler(Handler):
    name = "AIReadinessScoringHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files", set())
        commands = context.shared.get("commands", {"test": [], "lint": [], "build": []})
        report, findings = _assess_readiness(files, commands)
        context.readiness_report = report
        context.findings = findings
        art = context.record_artifact(
            name="codebase_ai_readiness_report.json",
            data=json.dumps(report, indent=2),
            artifact_type="ANALYSIS_REPORT",
            command="assess_readiness",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class StrategicProgrammingAssessmentHandler(Handler):
    name = "StrategicProgrammingAssessmentHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        assessment = {
            "responsibility_owner": "analysis_verifier",
            "summary": "Read-only Strategic Programming assessment of AI readiness.",
            "readiness": context.readiness_report,
        }
        art = context.record_artifact(
            name="strategic_programming_assessment.json",
            data=json.dumps(assessment, indent=2),
            artifact_type="STRATEGIC_REVIEW",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class BacklogFindingGeneratorHandler(Handler):
    name = "BacklogFindingGeneratorHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        evidence_paths = [a.path for a in context.artifacts]
        for f in context.findings:
            f.run_id = context.run_id
            f.evidence_artifact_paths = evidence_paths
        art = context.record_artifact(
            name="ai_safety_gap_backlog.json",
            data=json.dumps([f.model_dump() for f in context.findings], indent=2),
            artifact_type="ANALYSIS_REPORT",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class BacklogUpdateHandler(Handler):
    name = "BacklogUpdateHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        items = [
            {
                "item_id": f"BLI-{i + 1}",
                "source_finding_id": f.finding_id,
                "title": f.title,
                "acceptance_criteria": [f.recommended_action] if f.recommended_action else [],
                "status": "DRAFT",
            }
            for i, f in enumerate(context.findings)
        ]
        art = context.record_artifact(
            name="recommended_sprint_plan.json",
            data=json.dumps({"backlog_items": items}, indent=2),
            artifact_type="ANALYSIS_REPORT",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


HANDLERS = [
    RepoInventoryHandler(),
    CommandDiscoveryHandler(),
    CIInventoryHandler(),
    DependencyInventoryHandler(),
    ReadOnlyComplianceHandler(),
    AnalysisAgentInvocationHandler(),
    StructuredOutputParserHandler(),
    AIReadinessScoringHandler(),
    StrategicProgrammingAssessmentHandler(),
    BacklogFindingGeneratorHandler(),
    BacklogUpdateHandler(),
]
