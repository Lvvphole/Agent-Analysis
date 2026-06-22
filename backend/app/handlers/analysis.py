"""Analysis handlers (handoff Section 11.1, 15).

These reuse the existing read-only analysis logic from
``workflows/analysis_workflow`` rather than re-implementing it, so the proven
inventory / discovery / scoring behavior stays the single source of truth.
"""

from __future__ import annotations

import json

from app.chains.context import ChainContext, snapshot_repo
from app.handlers.base import Handler
from app.schemas.chain import ChainRequest, HandlerType
from app.workflows.analysis_workflow import (
    _assess_readiness,
    _discover_commands,
    _inventory,
)


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
    AIReadinessScoringHandler(),
    StrategicProgrammingAssessmentHandler(),
    BacklogFindingGeneratorHandler(),
    BacklogUpdateHandler(),
]
