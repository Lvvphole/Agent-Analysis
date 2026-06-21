"""Read-only AI-readiness analysis workflow (Sections 4.1, 17.1).

Proves the core read-only loop:

    inventory repo -> discover commands -> capture hashed evidence ->
    generate AI-readiness findings -> write evidence ledger + checkpoint

Hard rule honoured here: READ_ONLY_ANALYSIS must not modify repository files.
All artifacts are written to the *artifact store* directory, never back into
the analysed repository.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.constants import RunType
from app.schemas.artifact import Artifact
from app.schemas.backlog import BacklogFinding
from app.schemas.evidence_ledger import EvidenceLedger
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter

# Directories that are never worth walking for an inventory.
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


@dataclass
class AnalysisResult:
    run_id: str
    task_id: str
    artifacts: list[Artifact] = field(default_factory=list)
    findings: list[BacklogFinding] = field(default_factory=list)
    evidence_ledger: EvidenceLedger | None = None
    readiness_report: dict = field(default_factory=dict)


def _inventory(repo_path: Path) -> list[str]:
    rows: list[str] = []
    for path in sorted(repo_path.rglob("*")):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_path).parts):
            continue
        if path.is_file():
            rows.append(str(path.relative_to(repo_path)))
    return rows


def _discover_commands(files: set[str]) -> dict[str, list[str]]:
    """Best-effort, deterministic command discovery from marker files."""
    commands: dict[str, list[str]] = {"test": [], "lint": [], "build": []}
    if "pyproject.toml" in files or "requirements.txt" in files:
        commands["test"].append("python -m pytest")
    if "package.json" in files:
        commands["test"].append("npm test")
        commands["lint"].append("npm run lint")
        commands["build"].append("npm run build")
    return commands


def _assess_readiness(files: set[str], commands: dict[str, list[str]]) -> tuple[dict, list[BacklogFinding]]:
    has_tests = bool(commands["test"]) or any(
        f.startswith(("tests/", "test/")) or f.endswith("_test.py") for f in files
    )
    has_ci = any(f.startswith(".github/workflows/") for f in files)
    has_lint = bool(commands["lint"]) or any(
        f in {".flake8", ".eslintrc", ".eslintrc.json", "ruff.toml"} for f in files
    )

    report = {
        "has_tests": has_tests,
        "has_ci": has_ci,
        "has_lint": has_lint,
        "file_count": len(files),
        "discovered_commands": commands,
    }

    findings: list[BacklogFinding] = []
    if not has_tests:
        findings.append(
            BacklogFinding(
                finding_id="F-NO-TESTS",
                run_id="",  # filled by caller
                title="No automated tests detected",
                description="No test command or test directory was discovered.",
                severity="HIGH",
                category="ai_safety_gap",
                recommended_action="Add a test suite so the harness can require passing tests.",
            )
        )
    if not has_ci:
        findings.append(
            BacklogFinding(
                finding_id="F-NO-CI",
                run_id="",
                title="No CI workflow detected",
                description="No .github/workflows pipeline was found.",
                severity="MEDIUM",
                category="ai_safety_gap",
                recommended_action="Add CI to run tests and static checks on every change.",
            )
        )
    return report, findings


def run_readonly_analysis(
    *,
    repo_path: str | Path,
    store: ArtifactStore,
    run_id: str,
    task_id: str,
) -> AnalysisResult:
    """Run the read-only analysis loop and return hashed evidence + findings."""
    repo_path = Path(repo_path)
    writer = EvidenceLedgerWriter(task_id=task_id, run_id=run_id)
    result = AnalysisResult(run_id=run_id, task_id=task_id)

    # 1. Inventory (evidence artifact, never written into the repo).
    inventory_rows = _inventory(repo_path)
    files = set(inventory_rows)
    repo_tree = store.write(
        run_id=run_id,
        task_id=task_id,
        name="repo_tree.log",
        data="\n".join(inventory_rows) + "\n",
        artifact_type="ANALYSIS_REPORT",
        recorded_by="analysis_workflow",
    )
    result.artifacts.append(repo_tree)
    writer.append_artifact(repo_tree, result="INFO", command="inventory")

    # 2. Command discovery.
    commands = _discover_commands(files)
    discovery = store.write(
        run_id=run_id,
        task_id=task_id,
        name="command_discovery.log",
        data=json.dumps(commands, indent=2),
        artifact_type="ANALYSIS_REPORT",
        recorded_by="analysis_workflow",
    )
    result.artifacts.append(discovery)
    writer.append_artifact(discovery, result="INFO", command="discover_commands")

    # 3. AI-readiness assessment + findings.
    report, findings = _assess_readiness(files, commands)
    for f in findings:
        f.run_id = run_id
        f.evidence_artifact_paths = [repo_tree.path, discovery.path]
    result.readiness_report = report
    result.findings = findings

    readiness = store.write(
        run_id=run_id,
        task_id=task_id,
        name="codebase_ai_readiness_report.json",
        data=json.dumps(report, indent=2),
        artifact_type="ANALYSIS_REPORT",
        recorded_by="analysis_workflow",
    )
    result.artifacts.append(readiness)
    writer.append_artifact(readiness, result="INFO", command="assess_readiness")

    result.evidence_ledger = writer.ledger
    return result


# Documented invariant for callers/tests.
ANALYSIS_RUN_TYPE = RunType.READ_ONLY_ANALYSIS
