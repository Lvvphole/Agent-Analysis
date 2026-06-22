"""Chain registry (handoff Section 10, 11).

Chains are *registered configuration*: an ordered, immutable tuple of handler
names per task type. A request cannot invent, remove, or reorder a chain — it
can only name a ``task_type``, which the registry resolves. Unknown task types
resolve to ``None`` and the executor turns that into BLOCKED.

The AI_READINESS_AUDIT and IMPLEMENTATION chains are fully implemented. The
remaining chains are registered (so routing is deterministic and complete) but
reference handlers that are honestly deferred; executing them BLOCKS on the
first unimplemented handler with an explicit reason — no faked behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.constants import RunType
from app.schemas.chain import TaskType


@dataclass(frozen=True)
class ChainDefinition:
    chain_id: str
    mode: RunType
    handler_names: tuple[str, ...]


_AI_READINESS_AUDIT = ChainDefinition(
    chain_id="ai_readiness_audit_chain",
    mode=RunType.READ_ONLY_ANALYSIS,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "DefinitionOfDoneLockHandler",
        "ScopeValidationHandler",
        "RepoInventoryHandler",
        "CommandDiscoveryHandler",
        "CIInventoryHandler",
        "DependencyInventoryHandler",
        "ReadOnlyComplianceHandler",
        "AIReadinessScoringHandler",
        "StrategicProgrammingAssessmentHandler",
        "BacklogFindingGeneratorHandler",
        "EvidenceGateHandler",
        "AnalysisVerifierHandler",
        "EvaluatorHandler",
        "MemoryUpdateHandler",
        "BacklogUpdateHandler",
        "StopOrLoopHandler",
    ),
)

_IMPLEMENTATION = ChainDefinition(
    chain_id="implementation_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "DefinitionOfDoneLockHandler",
        "ScopeValidationHandler",
        "StrategicDesignGateHandler",
        "AgentInvocationHandler",
        "AgentOutputQuarantineHandler",
        "DiffCaptureHandler",
        "TestRunnerHandler",
        "StaticCheckHandler",
        "ScopeDiffHandler",
        "EvidenceGateHandler",
        "ImplementationVerifierHandler",
        "EvaluatorHandler",
        "MemoryUpdateHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

_BUG_FIX = ChainDefinition(
    chain_id="bug_fix_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "DefinitionOfDoneLockHandler",
        "ScopeValidationHandler",
        "FailureReproductionHandler",
        "StrategicDesignGateHandler",
        "AgentInvocationHandler",
        "AgentOutputQuarantineHandler",
        "DiffCaptureHandler",
        "TestRunnerHandler",
        "StaticCheckHandler",
        "ScopeDiffHandler",
        "EvidenceGateHandler",
        "ImplementationVerifierHandler",
        "EvaluatorHandler",
        "MemoryUpdateHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

_SECURITY_REVIEW = ChainDefinition(
    chain_id="security_review_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "ScopeValidationHandler",
        "SecurityReviewTestsNotApplicableHandler",
        "DiffCaptureHandler",
        "SecretScanHandler",
        "DependencyVulnerabilityHandler",
        "AuthChangeRiskHandler",
        "InputValidationRiskHandler",
        "EvidenceGateHandler",
        "SecurityVerifierHandler",
        "EvaluatorHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

_DEPENDENCY_UPDATE = ChainDefinition(
    chain_id="dependency_update_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "DefinitionOfDoneLockHandler",
        "DependencyInventoryHandler",
        "DependencyRiskHandler",
        "LicenseCheckHandler",
        "StrategicDesignGateHandler",
        "AgentInvocationHandler",
        "AgentOutputQuarantineHandler",
        "DiffCaptureHandler",
        "LockfileValidationHandler",
        "TestRunnerHandler",
        "StaticCheckHandler",
        "BuildHandler",
        "EvidenceGateHandler",
        "ImplementationVerifierHandler",
        "EvaluatorHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

_DOCUMENTATION_UPDATE = ChainDefinition(
    chain_id="documentation_update_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "DocumentationGapHandler",
        "StrategicDesignGateHandler",
        "AgentInvocationHandler",
        "AgentOutputQuarantineHandler",
        "DiffCaptureHandler",
        "LinkCheckHandler",
        "DocumentationVerifierHandler",
        "EvidenceGateHandler",
        "EvaluatorHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

_CI_FAILURE_REPAIR = ChainDefinition(
    chain_id="ci_failure_repair_chain",
    mode=RunType.IMPLEMENTATION,
    handler_names=(
        "ManifestValidationHandler",
        "ScrumMappingHandler",
        "CIFailureLogParserHandler",
        "FailureClassificationHandler",
        "ReproductionHandler",
        "StrategicDesignGateHandler",
        "AgentInvocationHandler",
        "AgentOutputQuarantineHandler",
        "DiffCaptureHandler",
        "TestRunnerHandler",
        "CIConfigValidationHandler",
        "EvidenceGateHandler",
        "ImplementationVerifierHandler",
        "EvaluatorHandler",
        "PRGateHandler",
        "StopOrLoopHandler",
    ),
)

# chain_id -> definition
CHAIN_DEFINITIONS: dict[str, ChainDefinition] = {
    d.chain_id: d
    for d in (
        _AI_READINESS_AUDIT,
        _IMPLEMENTATION,
        _BUG_FIX,
        _SECURITY_REVIEW,
        _DEPENDENCY_UPDATE,
        _DOCUMENTATION_UPDATE,
        _CI_FAILURE_REPAIR,
    )
}

# task_type -> chain_id (Section 10). REFACTOR / TEST_COVERAGE_EXPANSION reuse
# the implementation chain.
TASK_TYPE_TO_CHAIN: dict[str, str] = {
    TaskType.AI_READINESS_AUDIT.value: "ai_readiness_audit_chain",
    TaskType.IMPLEMENTATION.value: "implementation_chain",
    TaskType.BUG_FIX.value: "bug_fix_chain",
    TaskType.SECURITY_REVIEW.value: "security_review_chain",
    TaskType.DEPENDENCY_UPDATE.value: "dependency_update_chain",
    TaskType.DOCUMENTATION_UPDATE.value: "documentation_update_chain",
    TaskType.CI_FAILURE_REPAIR.value: "ci_failure_repair_chain",
    TaskType.REFACTOR.value: "implementation_chain",
    TaskType.TEST_COVERAGE_EXPANSION.value: "implementation_chain",
}


def resolve_chain(task_type: str) -> ChainDefinition | None:
    """Resolve a task type to its registered chain, or ``None`` if unknown."""
    chain_id = TASK_TYPE_TO_CHAIN.get(task_type)
    if chain_id is None:
        return None
    return CHAIN_DEFINITIONS.get(chain_id)
