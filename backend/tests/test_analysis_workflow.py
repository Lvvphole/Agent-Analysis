"""Read-only analysis workflow tests (Sections 4.1, 17.1, 19)."""

from __future__ import annotations

from app.storage.artifact_store import ArtifactStore
from app.workflows.analysis_workflow import run_readonly_analysis


def _make_repo(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n")
    pkg = root / "pkg"
    pkg.mkdir()
    (pkg / "module.py").write_text("x = 1\n")
    return root


def test_analysis_produces_hashed_evidence(tmp_path):
    repo = _make_repo(tmp_path / "repo")
    store = ArtifactStore(tmp_path / "artifacts")

    result = run_readonly_analysis(
        repo_path=repo, store=store, run_id="run-1", task_id="task-1"
    )

    assert result.evidence_ledger is not None
    assert len(result.artifacts) >= 3
    # Every evidence entry is hashed (Section 9.5).
    for entry in result.evidence_ledger.ledger_entries:
        assert len(entry.hash) == 64


def test_analysis_does_not_modify_repo(tmp_path):
    repo = _make_repo(tmp_path / "repo")
    before = {p.name for p in repo.iterdir()}

    store = ArtifactStore(tmp_path / "artifacts")
    run_readonly_analysis(repo_path=repo, store=store, run_id="run-1", task_id="task-1")

    after = {p.name for p in repo.iterdir()}
    assert before == after  # read-only: repo untouched


def test_analysis_generates_findings_without_diff(tmp_path):
    # A repo with no tests/CI yields findings — and no diff.patch is required.
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")

    store = ArtifactStore(tmp_path / "artifacts")
    result = run_readonly_analysis(
        repo_path=repo, store=store, run_id="run-1", task_id="task-1"
    )

    titles = {f.title for f in result.findings}
    assert "No automated tests detected" in titles
    # Findings are evidence-backed.
    for f in result.findings:
        assert f.evidence_artifact_paths
    # Read-only mode never produced a diff.
    assert not (store.run_dir("run-1") / "diff.patch").exists()
