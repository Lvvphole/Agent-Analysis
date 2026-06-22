"""Git runner tests (handoff Section 12.7, 16).

Capture only — the runner exposes no merge and no push to a protected branch.
"""

from __future__ import annotations

from app.runners.git_runner import GitRunner


def test_is_repo_true_for_git_repo(git_repo):
    assert GitRunner(git_repo).is_repo() is True


def test_is_repo_false_for_plain_dir(tmp_path):
    assert GitRunner(tmp_path).is_repo() is False


def test_capture_modified_file(git_repo):
    (git_repo / "backend" / "app" / "x.py").write_text("x = 2\n")
    cap = GitRunner(git_repo).capture()
    assert "x = 2" in cap.diff
    assert "backend/app/x.py" in cap.changed_files
    assert cap.diff_check_ok is True
    assert cap.status.strip() != ""


def test_capture_new_untracked_file(git_repo):
    (git_repo / "backend" / "app" / "new.py").write_text("y = 9\n")
    cap = GitRunner(git_repo).capture()
    # intent-to-add surfaces untracked files in the diff.
    assert "backend/app/new.py" in cap.changed_files


def test_capture_empty_when_no_changes(git_repo):
    cap = GitRunner(git_repo).capture()
    assert cap.diff.strip() == ""
    assert cap.changed_files == []


def test_runner_exposes_no_merge_or_push():
    # The capture-only surface must not grow merge/push affordances.
    public = {m for m in dir(GitRunner) if not m.startswith("_")}
    assert "merge" not in public
    assert "push" not in public
