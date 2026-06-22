"""Documentation handlers (handoff Section 11.6).

The DOCUMENTATION_UPDATE chain's previously-deferred handlers, implemented as
pure / read-only deterministic steps with no side effects and no network:

- ``DocumentationGapHandler`` (READ_ONLY_COMMAND): inventory the repo's docs.
- ``LinkCheckHandler`` (PURE_CHECK): validate *repo-relative* markdown links in
  the changed docs; external ``http(s)``/``mailto`` links are recorded as
  NOT_APPLICABLE (never fetched).
- ``DocumentationVerifierHandler`` (VERIFIER): the independent verifier for doc
  changes — diff required, tests NOT_APPLICABLE, never downgrades a gate FAIL.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.chains.context import ChainContext
from app.gates.evidence_gate import evidence_gate
from app.gates.no_self_certification_gate import no_self_certification_gate
from app.gates.scope_gate import scope_gate
from app.handlers.base import Handler
from app.schemas.chain import ChainRequest, HandlerType
from app.schemas.gate_result import GateResult
from app.workflows.analysis_workflow import _inventory

_DOC_SUFFIXES = (".md", ".rst", ".txt")
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_doc(path: str) -> bool:
    norm = path.replace("\\", "/")
    base = norm.rsplit("/", 1)[-1].lower()
    return norm.startswith("docs/") or base.startswith("readme") or norm.lower().endswith(_DOC_SUFFIXES)


class DocumentationGapHandler(Handler):
    name = "DocumentationGapHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files")
        if not files:
            files = set(_inventory(context.repo_fs_path))
            context.shared["files"] = files
        docs = sorted(f for f in files if _is_doc(f))
        report = {"doc_files": docs, "has_docs": bool(docs), "doc_count": len(docs)}
        art = context.record_artifact(
            name="documentation_gap.log",
            data=json.dumps(report, indent=2),
            artifact_type="ANALYSIS_REPORT",
            command="documentation_gap",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class LinkCheckHandler(Handler):
    name = "LinkCheckHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        repo = context.repo_fs_path.resolve()
        broken: list[str] = []
        external: list[str] = []
        checked: list[str] = []

        for rel in context.changed_files:
            norm = rel.replace("\\", "/")
            if not norm.lower().endswith(".md"):
                continue
            doc_path = (context.repo_fs_path / norm)
            if not doc_path.is_file():
                continue
            text = doc_path.read_text(encoding="utf-8", errors="replace")
            for raw in _LINK_RE.findall(text):
                target = raw.strip().split()[0] if raw.strip() else ""
                link = target.split("#", 1)[0]
                if not link:
                    continue
                if link.startswith(("http://", "https://", "mailto:")):
                    external.append(f"{norm} -> {target}")
                    continue
                resolved = (doc_path.parent / link).resolve()
                checked.append(f"{norm} -> {link}")
                if not resolved.is_relative_to(repo) or not resolved.exists():
                    broken.append(f"{norm} -> {link}")

        context.record_artifact(
            name="link_check.log",
            data=json.dumps(
                {"checked_internal": checked, "external_not_applicable": external,
                 "broken_internal": broken},
                indent=2,
            ),
            artifact_type="COMMAND_OUTPUT",
            command="link_check",
            recorded_by=self.name,
        )
        if broken:
            return self._fail([f"broken internal documentation link: {b}" for b in broken])
        return self._ok()


class DocumentationVerifierHandler(Handler):
    name = "DocumentationVerifierHandler"
    handler_type = HandlerType.VERIFIER

    def handle(self, request: ChainRequest, context: ChainContext):
        context.verifier_run_id = context.verifier_run_id or "doc-verifier"
        gates: list[GateResult] = [
            no_self_certification_gate(
                coding_agent_run_id=context.coding_agent_run_id,
                verifier_run_id=context.verifier_run_id,
                agent_summary_used_as_evidence=not context.agent_summary_quarantined,
            ),
            evidence_gate(
                context.evidence.ledger,
                run_id=context.run_id,
                task_id=context.task_id,
                required_artifact_types=("DIFF",),
            ),
            scope_gate(
                context.changed_files,
                files_in_scope=request.scope.files_in_scope,
                files_out_of_scope=request.scope.files_out_of_scope,
            ),
        ]
        result = self._from_gates(gates)
        context.record_artifact(
            name="verifier_report.json",
            data=json.dumps(
                {
                    "task_id": context.task_id,
                    "run_id": context.run_id,
                    "verifier_run_id": context.verifier_run_id,
                    "coding_agent_run_id": context.coding_agent_run_id,
                    "test_status": "NOT_APPLICABLE",
                    "decision": "PASS" if result.status.value == "PASS" else "FAIL",
                    "failure_reasons": [r for g in gates if not g.passed for r in g.reasons],
                    "timestamp": _now(),
                },
                indent=2,
            ),
            artifact_type="VERIFIER_REPORT",
            result="PASS" if result.status.value == "PASS" else "FAIL",
            recorded_by=self.name,
        )
        return result


HANDLERS = [
    DocumentationGapHandler(),
    LinkCheckHandler(),
    DocumentationVerifierHandler(),
]
