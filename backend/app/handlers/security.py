"""Security-review handlers (handoff Section 11.4).

The SECURITY_REVIEW chain's previously-deferred handlers. Unlike the
implementation-style chains, this chain has **no agent stage**: it captures the
working-tree diff (``DiffCaptureHandler`` via the git runner) and reviews the
changed files. The handlers are pure / read-only and deterministic:

- ``SecretScanHandler`` (READ_ONLY_COMMAND): scan changed-file content for
  hardcoded secrets; FAIL with locations on any match.
- ``DependencyVulnerabilityHandler`` (PURE_CHECK): evaluate *caller-supplied*
  advisories (no live CVE feed); SKIP with a reason when none are provided.
- ``AuthChangeRiskHandler`` (PURE_CHECK): flag auth-affecting changes; such a
  change must be explicitly acknowledged (``security_ack``) or it FAILs.
- ``InputValidationRiskHandler`` (PURE_CHECK): flag dangerous injection sinks
  (``eval``/``exec``/``os.system``/``shell=True``/...); FAIL with locations.
- ``SecurityVerifierHandler`` (VERIFIER): the independent verifier for security
  reviews — diff required, tests NOT_APPLICABLE, never downgrades a gate FAIL.
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
from app.schemas.chain import ChainRequest, HandlerType, TaskType
from app.schemas.gate_result import GateResult

_BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}

_SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("aws access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "hardcoded credential",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*"
            r"['\"][^'\"]{8,}['\"]"
        ),
    ),
)

_DANGEROUS_SINKS = (
    ("eval()", re.compile(r"\beval\s*\(")),
    ("exec()", re.compile(r"\bexec\s*\(")),
    ("os.system()", re.compile(r"\bos\.system\s*\(")),
    ("subprocess shell=True", re.compile(r"shell\s*=\s*True")),
    ("pickle.loads()", re.compile(r"\bpickle\.loads\s*\(")),
    ("yaml.load() without SafeLoader", re.compile(r"\byaml\.load\s*\((?!.*SafeLoader)")),
)

_AUTH_KEYWORDS = re.compile(
    r"(?i)\b(?:password|passwd|login|logout|authenticate|authorization|"
    r"session|permission|privilege|jwt|oauth|credential)\b"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_changed_text(context: ChainContext):
    """Yield (relpath, text) for each changed file that exists on disk."""
    for rel in context.changed_files:
        norm = rel.replace("\\", "/")
        path = context.repo_fs_path / norm
        if not path.is_file():
            continue
        try:
            yield norm, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def _scan(context: ChainContext, patterns) -> list[str]:
    """Return ``file:line: label`` findings for the given (label, regex) set."""
    findings: list[str] = []
    for norm, text in _iter_changed_text(context):
        for lineno, line in enumerate(text.splitlines(), start=1):
            for label, rx in patterns:
                if rx.search(line):
                    findings.append(f"{norm}:{lineno}: {label}")
    return findings


class SecurityReviewTestsNotApplicableHandler(Handler):
    """Declare, *before* the evidence gate, that SECURITY_REVIEW has no test
    runner in this chain, so tests are NOT_APPLICABLE.

    ``EvidenceGateHandler`` requires a ``TEST`` artifact for implementation-mode
    requests unless ``metadata.tests_not_applicable`` is set. SECURITY_REVIEW
    reviews an existing diff and never runs tests; this handler makes that an
    explicit, auditable declaration (recorded as hashed evidence) rather than a
    hidden requirement the caller must remember. It is scoped to SECURITY_REVIEW
    only, so chains that include ``TestRunnerHandler`` keep their full
    ``(DIFF, TEST)`` evidence requirement.
    """

    name = "SecurityReviewTestsNotApplicableHandler"
    handler_type = HandlerType.PURE_CHECK

    _REASON = (
        "SECURITY_REVIEW has no test runner in this chain; security evidence is "
        "supplied by security scan/risk handlers."
    )

    def handle(self, request: ChainRequest, context: ChainContext):
        if request.task_type != TaskType.SECURITY_REVIEW:
            # Never weakens chains that legitimately run tests.
            return self._skip("only applies to SECURITY_REVIEW")
        # The evidence gate reads request.metadata; declare tests NOT_APPLICABLE
        # without overwriting a caller-supplied reason.
        request.metadata["tests_not_applicable"] = True
        request.metadata.setdefault("tests_not_applicable_reason", self._REASON)
        context.shared["tests_not_applicable"] = True
        art = context.record_artifact(
            name="security_review_tests_not_applicable.json",
            data=json.dumps(
                {
                    "task_type": request.task_type.value,
                    "tests_not_applicable": True,
                    "reason": self._REASON,
                },
                indent=2,
            ),
            artifact_type="ANALYSIS_REPORT",
            command="security_review_tests_not_applicable",
            recorded_by=self.name,
        )
        return self._ok(artifacts=[art.path], metadata={"tests_not_applicable": True})


class SecretScanHandler(Handler):
    name = "SecretScanHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        findings = _scan(context, _SECRET_PATTERNS)
        context.record_artifact(
            name="secret_scan.log",
            data=json.dumps({"findings": findings}, indent=2),
            artifact_type="COMMAND_OUTPUT",
            command="secret_scan",
            result="FAIL" if findings else "PASS",
            recorded_by=self.name,
        )
        if findings:
            return self._fail([f"hardcoded secret detected: {f}" for f in findings])
        return self._ok()


class DependencyVulnerabilityHandler(Handler):
    name = "DependencyVulnerabilityHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        vuln = request.metadata.get("dependency_vulnerabilities")
        if not vuln:
            return self._skip(
                "no vulnerability feed configured; dependency vulnerability scan deferred"
            )
        advisories = vuln.get("advisories", [])
        blocking = [
            a
            for a in advisories
            if str(a.get("severity", "")).upper() in _BLOCKING_SEVERITIES
            and not a.get("waived")
        ]
        context.record_artifact(
            name="dependency_vulnerability.log",
            data=json.dumps({"advisories": advisories, "blocking": blocking}, indent=2),
            artifact_type="ANALYSIS_REPORT",
            command="dependency_vulnerability_scan",
            result="FAIL" if blocking else "INFO",
            recorded_by=self.name,
        )
        if blocking:
            return self._fail(
                [
                    f"blocking vulnerability {a.get('id', '?')} ({a.get('severity')}) for "
                    f"{a.get('package', '?')}"
                    for a in blocking
                ]
            )
        return self._ok()


class AuthChangeRiskHandler(Handler):
    name = "AuthChangeRiskHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        touched = sorted(
            {norm for norm, text in _iter_changed_text(context) if _AUTH_KEYWORDS.search(text)}
        )
        acknowledged = bool(
            (request.metadata.get("security_ack") or {}).get("auth_change_reviewed")
        )
        context.record_artifact(
            name="auth_change_risk.log",
            data=json.dumps(
                {"auth_touching_files": touched, "acknowledged": acknowledged}, indent=2
            ),
            artifact_type="ANALYSIS_REPORT",
            command="auth_change_risk",
            result="FAIL" if (touched and not acknowledged) else "PASS",
            recorded_by=self.name,
        )
        if touched and not acknowledged:
            return self._fail(
                [
                    "auth-affecting change requires reviewer acknowledgment "
                    "(security_ack.auth_change_reviewed): " + ", ".join(touched)
                ],
            )
        return self._ok()


class InputValidationRiskHandler(Handler):
    name = "InputValidationRiskHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        findings = _scan(context, _DANGEROUS_SINKS)
        context.record_artifact(
            name="input_validation_risk.log",
            data=json.dumps({"findings": findings}, indent=2),
            artifact_type="COMMAND_OUTPUT",
            command="input_validation_risk",
            result="FAIL" if findings else "PASS",
            recorded_by=self.name,
        )
        if findings:
            return self._fail([f"dangerous input sink: {f}" for f in findings])
        return self._ok()


class SecurityVerifierHandler(Handler):
    """Independent verifier for security reviews. The scan handlers enforce the
    actual security FAILs; this verifier independently re-affirms that the diff
    evidence is present, hashed, and in scope, and that creation and
    certification are not the same authority. Never downgrades a gate FAIL."""

    name = "SecurityVerifierHandler"
    handler_type = HandlerType.VERIFIER

    def handle(self, request: ChainRequest, context: ChainContext):
        context.verifier_run_id = context.verifier_run_id or "security-verifier"
        gates: list[GateResult] = [
            no_self_certification_gate(
                coding_agent_run_id=context.coding_agent_run_id,
                verifier_run_id=context.verifier_run_id,
                # No agent stage in this chain: there is no agent narrative.
                agent_summary_used_as_evidence=False,
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
    SecurityReviewTestsNotApplicableHandler(),
    SecretScanHandler(),
    DependencyVulnerabilityHandler(),
    AuthChangeRiskHandler(),
    InputValidationRiskHandler(),
    SecurityVerifierHandler(),
]
