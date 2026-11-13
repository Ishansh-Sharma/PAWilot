import pytest
from fastapi.testclient import TestClient

from pawilot.app import create_app
from pawilot.vault import MemoryVault

TOKEN = "test-session-token-" + "x" * 40
HEADERS = {"Authorization": "Bearer " + TOKEN}


@pytest.fixture
def vault():
    return MemoryVault()


@pytest.fixture
def app(tmp_path, vault):
    return create_app(tmp_path / "test.sqlite3", TOKEN, vault)


@pytest.fixture
def client(app):
    with TestClient(app, headers=HEADERS) as client:
        yield client



def text_output(text):
    return {"candidates":[{"finishReason":"STOP", "content":{"role":"model", "parts":[{"text":text}]}}]}


def call_output(name, arguments):
    return {"candidates":[{"finishReason":"STOP", "content":{"role":"model", "parts":[{
        "functionCall":{"name":name,"args":arguments,"id":"call1"}, "thoughtSignature":"test-signature"}]}}]}
