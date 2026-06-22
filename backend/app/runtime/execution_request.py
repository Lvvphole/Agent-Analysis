"""Execution request schema for the safe runtime endpoint.

Wraps the routing ``ChainRequest`` with the real, server-validated execution
path. The execution path is deliberately separate from ``ChainRequest.repo_path``
(which is canonical identity only) and is validated by the workspace policy.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.chain import ChainRequest


class ChainExecuteRequest(BaseModel):
    model_config = {"extra": "forbid"}

    request: ChainRequest
    # Optional real filesystem path; when omitted the server default workspace is
    # used. Either way it is validated by the WorkspacePolicy before execution.
    execution_path: str = ""
