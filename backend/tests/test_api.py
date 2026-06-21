"""Control API tests (Sections 11, 16.2, 19).

Asserts the safe surface works *and* that the forbidden endpoints do not exist.
"""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.store import registry  # noqa: E402
from app.main import app  # noqa: E402

from tests.conftest import make_manifest  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.runs.clear()
    yield
    registry.runs.clear()


def test_health_declares_no_auto_actions():
    body = client.get("/health").json()
    assert body["auto_merge"] is False
    assert body["auto_deploy"] is False
    assert body["self_certification_allowed"] is False


def test_create_run_with_valid_manifest():
    resp = client.post("/runs", json=make_manifest().model_dump(mode="json"))
    assert resp.status_code == 201, resp.text
    assert resp.json()["state"] == "INTAKE"


def test_create_run_rejects_auto_merge():
    resp = client.post(
        "/runs", json=make_manifest(auto_merge=True).model_dump(mode="json")
    )
    assert resp.status_code == 422
    assert any("auto_merge" in r for r in resp.json()["detail"]["reasons"])


def test_no_forbidden_endpoints_exist():
    # Use the OpenAPI schema: it enumerates every real operation path and is
    # stable across Starlette route-object changes.
    paths = client.get("/openapi.json").json()["paths"].keys()
    forbidden_fragments = ("complete", "merge", "deploy", "bypass", "force-pass")
    for path in paths:
        assert not any(frag in path for frag in forbidden_fragments), path


def test_same_agent_verifier_pass_is_downgraded():
    # Register a run.
    client.post("/runs", json=make_manifest(run_id="run-x").model_dump(mode="json"))

    verifier_report = {
        "task_id": "task-1",
        "run_id": "run-x",
        "verifier_id": "v",
        "verifier_run_id": "same",
        "coding_agent_run_id": "same",  # same as verifier => self-certification
        "decision": "PASS",
    }
    ledger = {
        "task_id": "task-1",
        "run_id": "run-x",
        "ledger_entries": [
            {
                "entry_id": "E1",
                "artifact_type": "DIFF",
                "artifact_path": "artifacts/run-x/diff.patch",
                "hash": "a" * 64,
            }
        ],
    }
    resp = client.post(
        "/runs/run-x/verify",
        json={"verifier_report": verifier_report, "evidence_ledger": ledger},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reported_decision"] == "PASS"
    # The reported PASS is not honoured because the same agent certified itself.
    assert body["effective_decision"] == "FAIL"


def test_pr_requires_verifier_pass():
    client.post("/runs", json=make_manifest(run_id="run-y").model_dump(mode="json"))
    resp = client.post("/runs/run-y/pr", json={"pr_url": "http://x"})
    assert resp.status_code == 409  # verifier PASS required first
