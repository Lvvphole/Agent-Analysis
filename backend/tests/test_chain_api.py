"""Chain API tests (handoff Section 16.6, 17)."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.store import registry  # noqa: E402
from app.main import app  # noqa: E402

from tests.conftest import make_chain_request, make_manifest  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    registry.runs.clear()
    yield
    registry.runs.clear()


def test_list_chains_exposes_registry():
    body = client.get("/chains").json()
    ids = {c["chain_id"] for c in body}
    assert "ai_readiness_audit_chain" in ids
    assert "implementation_chain" in ids


def test_get_chain_returns_ordered_handlers():
    body = client.get("/chains/ai_readiness_audit_chain").json()
    assert body["handler_names"][0] == "ManifestValidationHandler"
    assert body["handler_names"][-1] == "StopOrLoopHandler"


def test_plan_chain_resolves_registered_plan():
    client.post("/runs", json=make_manifest(run_id="run-x").model_dump(mode="json"))
    req = make_chain_request(run_id="run-x", task_id="task-1")
    resp = client.post("/runs/run-x/chain", json=req.model_dump(mode="json"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["chain_id"] == "ai_readiness_audit_chain"
    assert resp.json()["auto_merge"] is False
    assert resp.json()["auto_deploy"] is False


def test_no_forbidden_endpoints_after_chain_routes():
    paths = client.get("/openapi.json").json()["paths"].keys()
    forbidden = ("complete", "merge", "deploy", "bypass", "force-pass")
    for path in paths:
        assert not any(f in path for f in forbidden), path
