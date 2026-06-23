"""Runtime workspace policy.

The API must never execute against an arbitrary filesystem path. ``repo_path`` on
the ``ChainRequest`` is canonical *identity* only (validated elsewhere); the real
execution path is supplied separately and validated here against a single allowed
workspace root.

Blocks:
- empty repo path
- nonexistent repo path
- path outside the allowed workspace root
- nested duplicate root segments (e.g. ``agent-analysis/agent-analysis``)
"""

from __future__ import annotations

from pathlib import Path


class WorkspacePolicyError(ValueError):
    """Raised when an execution path violates the workspace policy."""


class WorkspacePolicy:
    def __init__(self, allowed_root: str | Path) -> None:
        self.allowed_root = Path(allowed_root).resolve()

    def resolve(self, execution_path: str | Path | None) -> Path:
        """Validate and resolve an execution path, or raise WorkspacePolicyError."""
        if execution_path is None or not str(execution_path).strip():
            raise WorkspacePolicyError("empty repo path")

        raw = Path(execution_path)

        # Nested duplicate root like .../agent-analysis/agent-analysis.
        parts = raw.parts
        for a, b in zip(parts, parts[1:]):
            if a == b and a not in ("/", "\\"):
                raise WorkspacePolicyError(f"nested duplicate path segment: {a}")

        resolved = raw.resolve()
        root = self.allowed_root
        if resolved != root and root not in resolved.parents:
            raise WorkspacePolicyError(
                f"path outside allowed workspace ({root}): {resolved}"
            )
        if not resolved.exists():
            raise WorkspacePolicyError(f"repo path does not exist: {resolved}")
        return resolved
