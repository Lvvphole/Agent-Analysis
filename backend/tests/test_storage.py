"""Storage primitive tests (Sections 12.4, 9.5, 19)."""

from __future__ import annotations

import pytest

from app.constants import Decision
from app.storage.artifact_store import ArtifactStore
from app.storage.evidence_writer import EvidenceLedgerWriter
from app.storage.hashing import hash_text


def test_hash_is_sha256_hex():
    digest = hash_text("hello")
    assert len(digest) == 64
    # Known SHA-256 of "hello".
    assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_artifact_store_writes_and_hashes(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.write(
        run_id="run-1",
        task_id="task-1",
        name="diff.patch",
        data="--- a\n+++ b\n",
        artifact_type="DIFF",
    )
    assert artifact.hash == hash_text("--- a\n+++ b\n")
    assert (tmp_path / "run-1" / "diff.patch").exists()


def test_evidence_writer_requires_hash():
    writer = EvidenceLedgerWriter(task_id="task-1", run_id="run-1")
    with pytest.raises(ValueError):
        writer.append(artifact_type="DIFF", artifact_path="x", hash="")


def test_evidence_writer_generates_unique_ids():
    writer = EvidenceLedgerWriter(task_id="task-1", run_id="run-1")
    e1 = writer.append(artifact_type="DIFF", artifact_path="a", hash="1" * 64)
    e2 = writer.append(artifact_type="TEST", artifact_path="b", hash="2" * 64)
    assert e1.entry_id != e2.entry_id
    ledger = writer.finalize(Decision.PASS)
    assert ledger.final_status == Decision.PASS
    assert len(ledger.ledger_entries) == 2


def test_append_artifact_from_store(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.write(
        run_id="run-1",
        task_id="task-1",
        name="test_output.log",
        data="2 passed",
        artifact_type="TEST",
    )
    writer = EvidenceLedgerWriter(task_id="task-1", run_id="run-1")
    entry = writer.append_artifact(artifact, result="PASS", command="pytest")
    assert entry.hash == artifact.hash
    assert entry.artifact_type == "TEST"
