"""Model endpoints: safe, read-only, no forbidden surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_models_summary():
    body = client.get("/models").json()
    assert "anthropic" in body["providers"]
    assert "openai" in body["providers"]
    assert body["live_calls_available"] is False


def test_models_catalog_lists_placeholders():
    items = client.get("/models/catalog").json()
    assert any(e["provider"] == "anthropic" for e in items)
    assert any(e["provider"] == "openai" for e in items)
    assert all(e["live_calls_available"] is False for e in items)


def test_llm_invocations_unknown_run_is_404():
    assert client.get("/runs/does-not-exist/llm-invocations").status_code == 404


def test_no_forbidden_endpoints_after_models_routes():
    # OpenAPI schema enumerates every real operation path (stable across
    # Starlette route-object changes), matching test_api's forbidden scan.
    paths = client.get("/openapi.json").json()["paths"].keys()
    forbidden_fragments = ("complete", "merge", "deploy", "bypass", "force-pass")
    for path in paths:
        assert not any(frag in path for frag in forbidden_fragments), path
    assert "/models/catalog" in paths
