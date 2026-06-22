"""Dependency-update handlers (handoff Section 11.5).

The DEPENDENCY_UPDATE chain's previously-deferred handlers, implemented as pure
/ deterministic steps. The chain otherwise reuses the proven implementation
pipeline (agent invocation → quarantine → diff capture → tests →
ImplementationVerifier), so only these four are added:

- ``LockfileValidationHandler`` (PURE_CHECK): a manifest change must be matched
  by its lockfile change (real, deterministic gate over the diff's changed set).
- ``DependencyRiskHandler`` (PURE_CHECK): evaluate *caller-supplied* advisories;
  no live CVE feed — SKIP with an explicit reason when none are provided.
- ``LicenseCheckHandler`` (PURE_CHECK): evaluate *caller-supplied* license data
  against an allow/deny policy; SKIP with a reason when none is provided.
- ``BuildHandler`` (READ_ONLY_COMMAND): mirrors ``TestRunnerHandler`` — a
  caller-supplied ``build_outcomes`` (ManualAdapter) or a real allowlisted build
  command run; SKIP when not applicable / no evidence.
"""

from __future__ import annotations

import json

from app.chains.context import ChainContext
from app.constants import RunType
from app.handlers.base import Handler
from app.runners.command_runner import CommandRunner
from app.runners.sandbox_policy import build_policy
from app.schemas.chain import ChainRequest, HandlerType

# A manifest whose dependency graph is pinned in a separate lockfile that must
# move with it. ``requirements.txt`` is intentionally absent: it is itself the
# pinned list, so it needs no companion lock.
_MANIFEST_LOCKS = {
    "package.json": "package-lock.json",
    "pyproject.toml": "poetry.lock",
}

_BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


def _basenames(paths) -> set[str]:
    return {str(p).replace("\\", "/").rsplit("/", 1)[-1] for p in paths}


class LockfileValidationHandler(Handler):
    name = "LockfileValidationHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        changed = _basenames(context.changed_files)
        missing = [
            f"{manifest} changed without updating {lock}"
            for manifest, lock in _MANIFEST_LOCKS.items()
            if manifest in changed and lock not in changed
        ]
        context.record_artifact(
            name="lockfile_validation.log",
            data=json.dumps(
                {"changed": sorted(changed), "lockfile_violations": missing}, indent=2
            ),
            artifact_type="COMMAND_OUTPUT",
            command="lockfile_validation",
            result="FAIL" if missing else "PASS",
            recorded_by=self.name,
        )
        if missing:
            return self._fail(missing)
        return self._ok()


class DependencyRiskHandler(Handler):
    name = "DependencyRiskHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        risk = request.metadata.get("dependency_risk")
        if not risk:
            return self._skip(
                "no advisory feed configured; dependency risk assessment deferred"
            )
        advisories = risk.get("advisories", [])
        blocking = [
            a
            for a in advisories
            if str(a.get("severity", "")).upper() in _BLOCKING_SEVERITIES
            and not a.get("waived")
        ]
        context.record_artifact(
            name="dependency_risk.log",
            data=json.dumps({"advisories": advisories, "blocking": blocking}, indent=2),
            artifact_type="ANALYSIS_REPORT",
            command="dependency_risk",
            result="FAIL" if blocking else "INFO",
            recorded_by=self.name,
        )
        if blocking:
            return self._fail(
                [
                    f"blocking advisory {a.get('id', '?')} ({a.get('severity')}) for "
                    f"{a.get('package', '?')}"
                    for a in blocking
                ]
            )
        return self._ok()


class LicenseCheckHandler(Handler):
    name = "LicenseCheckHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        lc = request.metadata.get("license_check")
        if not lc:
            return self._skip("no license data provided; license check deferred")
        licenses = lc.get("licenses", {})
        allowed = set(lc.get("allowed", []))
        denied = set(lc.get("denied", []))
        violations = [
            f"{pkg}: {lic}"
            for pkg, lic in licenses.items()
            if lic in denied or (allowed and lic not in allowed)
        ]
        context.record_artifact(
            name="license_check.log",
            data=json.dumps(
                {"licenses": licenses, "allowed": sorted(allowed),
                 "denied": sorted(denied), "violations": violations},
                indent=2,
            ),
            artifact_type="COMMAND_OUTPUT",
            command="license_check",
            result="FAIL" if violations else "PASS",
            recorded_by=self.name,
        )
        if violations:
            return self._fail([f"disallowed license: {v}" for v in violations])
        return self._ok()


class BuildHandler(Handler):
    name = "BuildHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        meta = request.metadata
        if meta.get("build_not_applicable"):
            return self._skip(meta.get("build_not_applicable_reason", "build not applicable"))

        outcomes = meta.get("build_outcomes")
        if outcomes:
            # ManualAdapter path: caller-supplied build outcomes.
            logs = outcomes
            command = meta.get("build_command", "build")
        else:
            commands = meta.get("build_commands")
            if not commands:
                return self._skip("no build command or build evidence provided; build deferred")
            policy = build_policy(
                RunType.IMPLEMENTATION,
                files_in_scope=request.scope.files_in_scope,
                allowed_commands=meta.get("allowed_commands", commands),
                forbidden_commands=meta.get("forbidden_commands", []),
            )
            runner = CommandRunner(policy, cwd=context.repo_fs_path)
            logs, rejected = [], []
            for cmd in commands:
                res = runner.run(cmd)
                if res.rejected:
                    rejected.append(f"{cmd}: {res.reason}")
                    continue
                logs.append(
                    {
                        "command": cmd,
                        "exit_code": res.exit_code,
                        "timed_out": res.timed_out,
                        "stdout": res.stdout,
                        "stderr": res.stderr,
                    }
                )
            if rejected:
                return self._fail(
                    [f"command not allowed: {r}" for r in rejected], blocked=True
                )
            command = "; ".join(commands)

        failed = [o for o in logs if o.get("exit_code") not in (0, None)]
        art = context.record_artifact(
            name="build_output.log",
            data=json.dumps(logs, indent=2),
            artifact_type="BUILD",
            command=command,
            result="PASS" if not failed else "FAIL",
            recorded_by=self.name,
        )
        if failed:
            return self._fail(
                [f"build failed with exit code {o.get('exit_code')}: {o.get('command', command)}"
                 for o in failed]
            )
        return self._ok(artifacts=[art.path])


HANDLERS = [
    LockfileValidationHandler(),
    DependencyRiskHandler(),
    LicenseCheckHandler(),
    BuildHandler(),
]
