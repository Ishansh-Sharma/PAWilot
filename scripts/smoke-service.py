"""Exercise the real loopback process, stdin bootstrap, persistence and shutdown.

Uses a temporary database and offline mode. Does not create or modify credentials.
"""
import json
import os
from pathlib import Path
import secrets
import select
import subprocess
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def start(directory):
    token = secrets.token_urlsafe(32)
    proc = subprocess.Popen([str(ROOT / ".venv/bin/python"), "-m", "pawilot"],
                            env={**os.environ, "PYTHONPATH": str(ROOT / "backend")},
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    proc.stdin.write(json.dumps({"token": token, "data_dir": str(directory)}) + "\n")
    proc.stdin.flush()
    if not select.select([proc.stdout], [], [], 15)[0]:
        proc.kill()
        raise RuntimeError("Service did not report a port")
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("Service exited before startup: " + proc.stderr.read()[-1000:])
    port = json.loads(line)["port"]
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", headers={"Authorization": "Bearer " + token}, trust_env=False)
    for _ in range(50):
        try:
            if client.get("/health").status_code == 200:
                return proc, client, port
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Service did not become healthy")


def stop(proc, client):
    client.close()
    proc.stdin.close()
    proc.wait(timeout=10)
    assert proc.returncode == 0, "Parent pipe closure must shut down cleanly"


with tempfile.TemporaryDirectory(prefix="pawilot-smoke-") as directory:
    proc, client, port = start(directory)
    try:
        assert httpx.get(f"http://127.0.0.1:{port}/health", trust_env=False).status_code == 401
        profile = {"name":"Sample learner", "preferences":"Use practical examples", "constraints":"30 minutes after 6 PM", "timezone":"Asia/Kolkata"}
        assert client.put("/profile", json=profile).status_code == 200
        preview = client.post("/imports/preview", content=(ROOT / "fixtures/sample-chatgpt-export.json").read_bytes()).json()
        candidate = next(c for c in preview["candidates"] if c["kind"] == "preference")
        selection = {"session_id":preview["session_id"], "selections":[{"candidate_id":candidate["id"], "record":{"kind":"preference", "title":candidate["title"], "detail":candidate["detail"]}}]}
        assert client.post("/imports/commit", json=selection).json()["created"] == 1
        assert client.post("/imports/commit", json=selection).json()["duplicates"] == 1
        assert client.post("/chat", json={"text": "/goal Build a useful desktop companion"}).status_code == 200
        action = client.get("/state").json()["actions"][0]
        assert client.post(f"/actions/{action['id']}/decision", json={"approve": True}).status_code == 200
        assert client.post("/chat", json={"text": "What are my priorities today?"}).status_code == 200
        action = client.get("/state").json()["actions"][0]
        assert action["payload"]["kind"] == "task"
        assert client.post(f"/actions/{action['id']}/decision", json={"approve": True}).status_code == 200
        before = client.get("/state").json()
        assert len(before["records"]) == 3
        task = next(r for r in before["records"] if r["kind"] == "task")
        assert task["goal_id"] == next(r["id"] for r in before["records"] if r["kind"] == "goal")
    finally:
        stop(proc, client)
    proc, client, _ = start(directory)
    try:
        after = client.get("/state").json()
        assert after["profile"] == before["profile"]
        assert after["records"] == before["records"]
        assert after["messages"] == before["messages"]
    finally:
        stop(proc, client)
print("PASS: real loopback auth, profile + reviewed import + dedup, goal → offline plan → linked approved task, restart persistence, parent-pipe shutdown (no live Gemini)")

