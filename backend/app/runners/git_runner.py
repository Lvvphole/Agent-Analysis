"""Git runner (handoff Section 12.7) — capture only.

Captures evidence from a working tree: ``git status --short``, ``git diff``,
``git diff --check``, and changed file names. It deliberately implements **no**
merge and **no** push to a protected branch — the release boundary stays with
the PR gate and lives outside this autonomous loop.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitCapture:
    status: str
    diff: str
    diff_check: str
    diff_check_ok: bool
    changed_files: list[str] = field(default_factory=list)


class GitRunner:
    """Read-only git capture over a working tree. No merge, no push."""

    def __init__(self, repo_path: str | Path, *, timeout: int = 60) -> None:
        self.repo = Path(repo_path)
        self.timeout = timeout

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

    def is_repo(self) -> bool:
        try:
            r = self._run("rev-parse", "--is-inside-work-tree")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        return r.returncode == 0 and r.stdout.strip() == "true"

    def head_commit(self) -> str | None:
        """Return the HEAD commit SHA, or ``None`` when not a repo / on error.

        Used by per-attempt isolation (Epic 3) to record the ``base_commit`` an
        attempt ran against. Capture-only, like the rest of this runner.
        """
        if not self.is_repo():
            return None
        try:
            r = self._run("rev-parse", "HEAD")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if r.returncode != 0:
            return None
        return r.stdout.strip() or None

    def capture(self) -> GitCapture:
        """Capture the current diff against HEAD, including new files.

        ``git add -N`` records intent-to-add so untracked files appear in the
        diff without changing the working tree's file contents.
        """
        self._run("add", "-N", ".")
        status = self._run("status", "--short").stdout
        diff = self._run("diff").stdout
        check = self._run("diff", "--check")
        names = self._run("diff", "--name-only").stdout
        changed = [line.strip() for line in names.splitlines() if line.strip()]
        return GitCapture(
            status=status,
            diff=diff,
            diff_check=check.stdout,
            diff_check_ok=(check.returncode == 0),
            changed_files=changed,
        )
