"""Workflows: deterministic orchestration of the state machines.

For the MVP these are plain, dependency-free Python so the loop is fully
testable. They are structured to lift into Temporal workflows later: pure
orchestration here, side effects delegated to runners/storage (activities).
"""

from app.workflows.analysis_workflow import AnalysisResult, run_readonly_analysis

__all__ = ["AnalysisResult", "run_readonly_analysis"]
