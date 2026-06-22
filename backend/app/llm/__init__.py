"""Controlled LLM Integration Layer.

Declared, role-bound, allowlisted, rate-limited, permissioned, invocation-
recorded, hashed, ledgered, and independently gated multi-LLM orchestration.
Ships with a deterministic stub adapter; real provider adapters plug into the
same ``LLMAdapter`` interface later.
"""

from app.llm.base import LLMAdapter, LLMResponse, ModelRouter, RouterResult
from app.llm.catalog import MODEL_CATALOG, CatalogEntry, to_model_spec
from app.llm.rate_limit import RateLimiter
from app.llm.recorder import LLMInvocationRecorder
from app.llm.stub_adapter import StubLLMAdapter

__all__ = [
    "LLMAdapter",
    "LLMResponse",
    "ModelRouter",
    "RouterResult",
    "MODEL_CATALOG",
    "CatalogEntry",
    "to_model_spec",
    "RateLimiter",
    "LLMInvocationRecorder",
    "StubLLMAdapter",
]
