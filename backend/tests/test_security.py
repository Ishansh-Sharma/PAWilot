import pytest
from fastapi.testclient import TestClient

from pawilot.app import create_app
from conftest import HEADERS


def test_auth_required_even_for_health(app):
    with TestClient(app) as client:
        for path in ["/health", "/state", "/records", "/settings"]:
            assert client.get(path).status_code == 401
        assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/health", headers=HEADERS).status_code == 200


def test_origin_and_host_protection(client):
    assert client.get("/state", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/state", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/state", headers={"Host": "evil.example"}).status_code == 400


def test_no_arbitrary_action_types_or_invalid_data(client):
    assert client.post("/records", json={"kind": "shell", "title": "rm -rf"}).status_code == 422
    assert client.post("/records", json={"kind": "task", "title": "Send", "command": "curl"}).status_code == 422
    assert client.post("/records", json={"kind": "task", "title": "  "}).status_code == 422
    assert client.post("/records", json={"kind": "task", "title": "Deadline", "due": "2026-02-30"}).status_code == 422
    assert client.post("/chat", json={"text": "x" * 8001}).status_code == 422
    assert client.post("/chat", content=b"x" * 100001).status_code == 413
    assert client.post("/actions/missing/decision", json={"approve": True}).status_code == 404


def test_weak_bootstrap_token_rejected(tmp_path, vault):
    with pytest.raises(ValueError):
        create_app(tmp_path / "test.sqlite3", "weak", vault)

