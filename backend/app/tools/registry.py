"""Read-only local tool registry.

Tools are deterministic, read-only inspections of a working tree. Each returns a
string payload that the executor hashes and ledgers. Mutating, network, or
release tools are intentionally absent — and the policy blocks any that try.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.workflows.analysis_workflow import _discover_commands, _inventory

# Tool names that must never be registered or run, even if some caller tries.
FORBIDDEN_TOOL_NAMES = frozenset(
    {
        "merge",
        "deploy",
        "push_to_main",
        "force_pass",
        "delete_repo",
        "publish_package",
    }
)


@dataclass(frozen=True)
class Tool:
    name: str
    run: Callable[[Path], str]
    mutating: bool = False


def _list_repo_tree(repo: Path) -> str:
    return "\n".join(_inventory(repo)) + "\n"


def _discover_commands_tool(repo: Path) -> str:
    return json.dumps(_discover_commands(set(_inventory(repo))), indent=2)


def _inspect_ci_config(repo: Path) -> str:
    files = _inventory(repo)
    ci = sorted(f for f in files if f.replace("\\", "/").startswith(".github/workflows/"))
    return json.dumps({"workflows": ci, "has_ci": bool(ci)}, indent=2)


_DEP_MARKERS = ("pyproject.toml", "requirements.txt", "package.json", "package-lock.json", "poetry.lock")


def _inspect_dependencies(repo: Path) -> str:
    files = _inventory(repo)
    deps = sorted(f for f in files if f.rsplit("/", 1)[-1] in _DEP_MARKERS)
    return json.dumps({"dependency_files": deps}, indent=2)


_DEFAULT_TOOLS = (
    Tool("list_repo_tree", _list_repo_tree),
    Tool("discover_commands", _discover_commands_tool),
    Tool("inspect_ci_config", _inspect_ci_config),
    Tool("inspect_dependencies", _inspect_dependencies),
)


class ToolRegistry:
    """An immutable-by-construction set of allowed read-only tools."""

    def __init__(self, tools=_DEFAULT_TOOLS) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in FORBIDDEN_TOOL_NAMES:
            raise ValueError(f"forbidden tool name cannot be registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_default_tool_registry() -> ToolRegistry:
    return ToolRegistry()
