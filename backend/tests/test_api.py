"""HTTP API tests with TestClient and an injected fake model (owner: agents builder)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel

from app.main import create_app
from test_pipeline import HARBOR, RIVERBEND, FakeLLM

BODY = {"charities": [{"ein": RIVERBEND}, {"ein": HARBOR}], "donor_note": "literacy in New Haven"}


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        lines = [line for line in block.split("\n") if line and not line.startswith(":")]
        if not lines:
            continue
        assert lines[0].startswith("event: "), block
        assert lines[1].startswith("data: "), block
        event = json.loads(lines[1][len("data: "):])
        assert event["type"] == lines[0][len("event: "):]
        assert set(event) == {"type", "ts", "data"}
        events.append(event)
    return events


@pytest.fixture
def client():
    with TestClient(create_app(model_override=FunctionModel(FakeLLM()))) as c:
        yield c


@pytest.fixture
def keyless_client():
    with TestClient(create_app()) as c:
        yield c


def test_health_reports_settings_without_key(keyless_client):
    data = keyless_client.get("/api/health").json()
    assert data["ok"] is True
    assert data["model"] == "gpt-6-luna"
    assert data["portkey_key_set"] is False
    assert data["offline_mode"] is True
    assert "PORTKEY_API_KEY" in data["setup_help"]
    for key in ("allow_defense_toggle", "run_budget_usd", "daily_budget_usd", "daily_spent_usd"):
        assert key in data


def test_featured_lists_demo_fixtures_first(client):
    results = client.get("/api/featured").json()["results"]
    assert [r["ein"] for r in results[:2]] == [RIVERBEND, HARBOR]
    assert results[0]["is_demo"] is True
    assert len(results) > 2


def test_org_profile_and_metrics(client):
    data = client.get(f"/api/org/{RIVERBEND}").json()
    assert data["profile"]["name"].startswith("Riverbend")
    assert "surplus_margin" in data["metrics"]["metrics"]
    assert client.get("/api/org/12345").status_code in (400, 404)
    assert client.get("/api/org/abc").status_code == 400
    assert client.get("/api/org/999999999").status_code == 404


def test_search_offline(client):
    results = client.get("/api/search", params={"q": "riverbend"}).json()["results"]
    assert any(r["ein"] == RIVERBEND for r in results)
    assert client.get("/api/search", params={"q": ""}).json() == {"results": []}


def test_pricing(client):
    data = client.get("/api/pricing").json()
    assert data["model"] == "gpt-6-luna"
    assert data["prices_per_million"]["input"] > 0
    assert data["source"].startswith("https://")


def test_diligence_stream_and_saved_run(client):
    resp = client.post("/api/diligence/stream", json=BODY)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-1] == "final"
    assert {"stage", "agent_started", "agent_step", "tool_call", "agent_done", "spend", "security"} <= set(types)
    final = events[-1]["data"]
    assert final["status"] == "complete"
    run_id = final["run_id"]

    runs = client.get("/api/runs").json()["runs"]
    assert any(r["run_id"] == run_id for r in runs)
    saved = client.get(f"/api/runs/{run_id}").json()
    assert saved["run_id"] == run_id and saved["memo"]["headline"]
    logged = client.get(f"/api/runs/{run_id}/events").json()["events"]
    assert [e["type"] for e in logged] == types

    assert client.get("/api/runs/run-does-not-exist").status_code == 404
    assert client.get("/api/runs/run-does-not-exist/events").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fetc%2Fpasswd").status_code == 404


def test_diligence_json_endpoint(client):
    data = client.post("/api/diligence", json={"charities": [{"ein": HARBOR}]}).json()
    assert data["status"] == "complete"
    assert data["scorecards"][0]["ein"] == HARBOR


def test_invalid_request_is_rejected(client):
    assert client.post("/api/diligence/stream", json={"charities": []}).status_code == 422
    assert client.post("/api/diligence/stream", json={"charities": [{"ein": "12-34"}]}).status_code == 422


def test_stream_without_key_explains_setup(keyless_client):
    resp = keyless_client.post("/api/diligence/stream", json=BODY)
    events = parse_sse(resp.text)
    assert [e["type"] for e in events] == ["error"]
    assert "PORTKEY_API_KEY" in events[0]["data"]["message"]
    assert keyless_client.post("/api/diligence", json=BODY).status_code == 503


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    with TestClient(create_app(model_override=FunctionModel(FakeLLM()))) as c:
        assert c.post("/api/diligence", json={"charities": [{"ein": HARBOR}]}).status_code == 200
        resp = c.post("/api/diligence/stream", json=BODY)
        assert resp.status_code == 429


def test_demo_pages_served_and_traversal_blocked(client):
    resp = client.get("/demo/riverbend-pantry.html")
    assert resp.status_code == 200 and "text/html" in resp.headers["content-type"]
    assert "Riverbend" in resp.text
    for bad in ("/demo/..%2Fapp%2Fconfig.py", "/demo/..%2F..%2F.env", "/demo/%2E%2E", "/demo/missing.html",
                "/demo/run.py"):
        assert client.get(bad).status_code == 404, bad


def test_root_serves_ui_or_placeholder(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()
    assert client.get("/api/unknown").status_code == 404


def test_attack_pages_served_from_attacks_folder_only(client):
    assert client.get("/demo/attacks/fake-role-tags.html").status_code == 200
    assert client.get("/demo/attacks/..%2Friverbend-pantry.html").status_code == 404
    assert client.get("/demo/attacks/missing.html").status_code == 404
