"""CI failure-repair handlers (handoff Section 11.7).

The CI_FAILURE_REPAIR chain's previously-deferred handlers, implemented as
pure / read-only deterministic steps with no live CI access and no network. The
failing CI log is *caller-supplied* via ``request.metadata`` (the same
ManualAdapter evidence path every chain uses); with no log the parser BLOCKS
with an explicit reason rather than fabricate one.

- ``CIFailureLogParserHandler`` (READ_ONLY_COMMAND): parse a supplied CI log
  into a structured failure summary (failing markers extracted deterministically).
- ``FailureClassificationHandler`` (PURE_CHECK): classify the failure category
  from the parsed summary; FAIL on UNKNOWN (never route a blind fix).
- ``ReproductionHandler`` (READ_ONLY_COMMAND): reproduce the failure locally
  before the fix — shares ``run_reproduction`` with the BUG_FIX precondition.
- ``CIConfigValidationHandler`` (PURE_CHECK): validate that the repo's workflow
  YAML parses (FAIL on a broken workflow); NOT_APPLICABLE when there is no CI.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.chains.context import ChainContext
from app.handlers.base import Handler
from app.handlers.implementation import run_reproduction
from app.schemas.chain import ChainRequest, HandlerType
from app.workflows.analysis_workflow import _inventory

# Deterministic failure markers, longest/most-specific first.
_FAILURE_MARKERS = ("##[error]", "Traceback", "FAILED", "Error:", "error:", "exit code")

# Keyword -> category. Ordered: first category whose keywords appear wins, so
# more specific signals (type/lint) are checked before the generic test signal.
_CLASSIFIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TYPE", ("mypy", "pyright", "type error", "incompatible type")),
    ("LINT", ("flake8", "ruff", "eslint", "lint", "pycodestyle", "black --check")),
    ("DEPENDENCY", ("modulenotfounderror", "no module named", "could not find a version",
                    "npm err", "pip install", "unresolved dependency")),
    ("BUILD", ("build failed", "compilation", "webpack", "tsc ", "make:")),
    ("CONFIG", ("yaml", "invalid workflow", "actions/", "workflow file")),
    ("TEST", ("pytest", "failed", "assertionerror", "test session", "npm test")),
)

_WORKFLOW_DIR = ".github/workflows/"
_WORKFLOW_SUFFIXES = (".yml", ".yaml")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CIFailureLogParserHandler(Handler):
    name = "CIFailureLogParserHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        ci = request.metadata.get("ci_failure") or {}
        log = (ci.get("log") or "").strip()
        if not log:
            return self._fail(
                ["CI failure log required; cannot repair a CI failure without it"],
                blocked=True,
                corrections=[
                    "supply request.metadata.ci_failure with {workflow, job, log}"
                ],
            )

        failing_lines = [
            line.strip()
            for line in log.splitlines()
            if any(m.lower() in line.lower() for m in _FAILURE_MARKERS)
        ]
        parsed = {
            "workflow": ci.get("workflow", ""),
            "job": ci.get("job", ""),
            "failing_lines": failing_lines,
            "log_lines": len(log.splitlines()),
        }
        context.shared["ci_failure"] = parsed
        art = context.record_artifact(
            name="ci_failure_parsed.log",
            data=json.dumps(parsed, indent=2),
            artifact_type="COMMAND_OUTPUT",
            command="ci_failure_log_parse",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path])


class FailureClassificationHandler(Handler):
    name = "FailureClassificationHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        parsed = context.shared.get("ci_failure", {})
        haystack = " ".join(parsed.get("failing_lines", [])).lower()

        category = "UNKNOWN"
        for cat, keywords in _CLASSIFIERS:
            if any(k in haystack for k in keywords):
                category = cat
                break

        context.shared["ci_failure_category"] = category
        context.record_artifact(
            name="ci_failure_classification.log",
            data=json.dumps(
                {"category": category, "evidence": parsed.get("failing_lines", [])},
                indent=2,
            ),
            artifact_type="ANALYSIS_REPORT",
            command="ci_failure_classify",
            result="INFO" if category != "UNKNOWN" else "FAIL",
            recorded_by=self.name,
        )
        if category == "UNKNOWN":
            return self._fail(
                ["unable to classify CI failure; manual triage required (no blind fix)"],
            )
        return self._ok(metadata={"category": category})


class ReproductionHandler(Handler):
    """Reproduce the classified CI failure locally before the fix. Shares
    ``run_reproduction`` with the BUG_FIX precondition (same validity rule)."""

    name = "ReproductionHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        result, _reproduced, _logs = run_reproduction(
            self,
            request,
            context,
            request.metadata.get("reproduction"),
            artifact_name="ci_failure_reproduction.log",
            missing_reason=(
                "reproduction required; a CI failure must be reproduced locally "
                "before repair"
            ),
        )
        return result


class CIConfigValidationHandler(Handler):
    name = "CIConfigValidationHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        files = context.shared.get("files")
        if not files:
            files = set(_inventory(context.repo_fs_path))
            context.shared["files"] = files
        workflows = sorted(
            f
            for f in files
            if f.replace("\\", "/").startswith(_WORKFLOW_DIR)
            and f.lower().endswith(_WORKFLOW_SUFFIXES)
        )

        if not workflows:
            context.record_artifact(
                name="ci_config_validation.log",
                data=json.dumps({"workflows": [], "status": "NOT_APPLICABLE"}, indent=2),
                artifact_type="COMMAND_OUTPUT",
                command="ci_config_validate",
                recorded_by=self.name,
            )
            return self._ok()

        broken: list[str] = []
        checked: list[str] = []
        for rel in workflows:
            path = Path(context.repo_fs_path) / rel
            try:
                yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
                checked.append(rel)
            except yaml.YAMLError as exc:
                broken.append(f"{rel}: {str(exc).splitlines()[0]}")

        context.record_artifact(
            name="ci_config_validation.log",
            data=json.dumps({"checked": checked, "broken": broken}, indent=2),
            artifact_type="COMMAND_OUTPUT",
            command="ci_config_validate",
            result="FAIL" if broken else "PASS",
            recorded_by=self.name,
        )
        if broken:
            return self._fail([f"invalid CI workflow: {b}" for b in broken])
        return self._ok()


HANDLERS = [
    CIFailureLogParserHandler(),
    FailureClassificationHandler(),
    ReproductionHandler(),
    CIConfigValidationHandler(),
]
