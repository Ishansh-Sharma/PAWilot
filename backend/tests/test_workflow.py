from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from pawilot.app import create_app
from pawilot.models import RecordInput
from pawilot.store import Store
from conftest import HEADERS, TOKEN


def test_full_goal_plan_approve_restart_workflow(client, tmp_path, vault):
    response = client.post("/chat", json={"text": "/goal Prepare for an engineering interview"})
    assert response.status_code == 200
    state = client.get("/state").json()
    assert state["records"] == []
    goal_proposal = state["actions"][0]["id"]
    assert client.post(f"/actions/{goal_proposal}/decision", json={"approve": True}).json()["status"] == "approved"
    response = client.post("/chat", json={"text": "What are my priorities today?"}).json()
    assert "engineering interview" in response["message"]
    state = client.get("/state").json()
    task_proposal = next(a for a in state["actions"] if a["status"] == "pending")
    assert task_proposal["payload"]["kind"] == "task"
    client.post(f"/actions/{task_proposal['id']}/decision", json={"approve": True})
    with TestClient(create_app(tmp_path / "test.sqlite3", TOKEN, vault), headers=HEADERS) as restarted:
        persisted = restarted.get("/state").json()
        assert sorted(r["kind"] for r in persisted["records"]) == ["goal", "task"]
        assert len(persisted["messages"]) == 4
        assert all(a["status"] == "approved" for a in persisted["actions"])


def test_rejection_and_idempotent_decisions(client):
    client.post("/chat", json={"text": "/task Do something"})
    action = client.get("/state").json()["actions"][0]
    endpoint = f"/actions/{action['id']}/decision"
    assert client.post(endpoint, json={"approve": False}).json()["status"] == "rejected"
    assert client.post(endpoint, json={"approve": True}).json()["status"] == "rejected"
    assert client.get("/state").json()["records"] == []


def test_concurrent_approval_creates_one_record(app):
    store = app.state.store
    ident = store.propose(RecordInput(kind="task", title="Only once"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: store.decide(ident, True), range(16)))
    assert len({result["result_id"] for result in outcomes}) == 1
    assert len(store.records()) == 1


def test_edit_complete_delete_and_clear_history(client):
    original = {"kind": "memory", "title": "Short explanations", "detail": "Start from first principles"}
    created = client.post("/records", json=original).json()
    assert client.put("/records/" + created["id"], json={**original, "title": "Use examples"}).json()["title"] == "Use examples"
    assert client.delete("/records/" + created["id"]).status_code == 200
    assert client.delete("/records/" + created["id"]).status_code == 404
    assert client.put("/records/missing", json=original).status_code == 404
    client.post("/chat", json={"text": "/task Draft my plan"})
    assert client.delete("/history").status_code == 200
    state = client.get("/state").json()
    assert state["messages"] == []
    assert state["actions"][0]["status"] == "rejected"
    assert state["actions"][0]["payload"] == {}


def test_delete_memory_redacts_action_copy(client):
    client.post("/chat", json={"text": "/remember Private preference"})
    action = client.get("/state").json()["actions"][0]
    approved = client.post(f"/actions/{action['id']}/decision", json={"approve": True}).json()
    client.delete("/records/" + approved["result_id"])
    assert client.get("/state").json()["actions"][0]["payload"] == {}


def test_retrieval_is_bounded_and_fts_updates(tmp_path):
    store = Store(tmp_path / "memory.sqlite3")
    for i in range(80):
        store.put(RecordInput(kind="memory", title=f"Unrelated record {i}"))
    target = store.put(RecordInput(kind="memory", title="Bartlett differentiator window", detail="Explain accumulator first"))
    context = store.context("Bartlett")
    assert context[0]["id"] == target["id"]
    assert len(context) <= 14
    store.put(RecordInput(kind="memory", title="Hann window"), target["id"])
    with store.db() as db:
        assert db.execute("SELECT count(*) FROM record_search WHERE record_search MATCH 'Bartlett'").fetchone()[0] == 0
    store.delete(target["id"])
    assert all(row["id"] != target["id"] for row in store.context("Hann"))


def test_credential_delete_disables_ai_and_never_returns_secret(client, vault):
    key = "sk-test-never-log-this-secret"
    assert client.put("/credentials/gemini", json={"value": key}).status_code == 200
    assert vault.get("gemini") == key
    client.put("/settings", json={"ai_enabled": True})
    state = client.get("/state")
    assert key not in state.text
    assert state.json()["has_api_key"]
    assert client.delete("/credentials/gemini").status_code == 200
    assert not client.get("/state").json()["settings"]["ai_enabled"]


def test_offline_planning_does_not_duplicate_pending_tasks(client):
    client.post("/records", json={"kind": "goal", "title": "Learn Swift"})
    client.post("/chat", json={"text": "Plan my day"})
    client.post("/chat", json={"text": "Plan my day"})
    assert len(client.get("/state").json()["actions"]) == 1

