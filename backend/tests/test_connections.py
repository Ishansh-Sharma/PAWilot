import json
import time
from urllib.parse import parse_qs
import httpx
import pytest
from fastapi.testclient import TestClient
from conftest import TOKEN,HEADERS
from pawilot.app import create_app
from pawilot.connections import SCOPES


@pytest.mark.parametrize("provider",["gmail","slack"])
def test_search_refresh_and_disconnect(tmp_path,vault,provider):
    calls = []
    def respond(req):
        calls.append(req.url.path)
        if req.url.path.endswith(("/token","/oauth.v2.access")):
            assert parse_qs(req.content.decode())["refresh_token"] == ["refresh-private"]
            data = {"access_token":"access-private","expires_in":600,"scope":SCOPES[provider]}
        elif req.url.path.endswith("/revoke"):
            data = {}
        else:
            assert req.headers["Authorization"] == "Bearer access-private"
            assert "access-private" not in str(req.url)
            if req.url.path.endswith("auth.revoke"):
                data = {"ok":True}
            elif req.url.path.endswith("search.messages"):
                data = {"ok":True,"messages":{"matches":[{"channel":{"name":"team"},"text":"Deadline Friday","permalink":"https://team.slack.com/archives/C1/p1"}]}}
            elif req.url.path.endswith("/messages"):
                data = {"messages":[{"id":"a1"}]}
            else:
                data = {"threadId":"a2","snippet":"Deadline Friday","payload":{"headers":[{"name":"Subject","value":"Proposal"}]}}
        return httpx.Response(200,json=data)
    with TestClient(create_app(tmp_path/"db",TOKEN,vault,connector_transport=httpx.MockTransport(respond)),headers=HEADERS) as client:
        command = {"text":"/"+provider+" deadline"}
        assert client.post("/chat",json=command).json()["mode"]=="error"
        cfg = {"client_id":"123.apps.googleusercontent.com","client_secret":"private"} if provider=="gmail" else {"client_id":"123.456"}
        assert client.put("/connections/"+provider+"/registration",json=cfg).is_success
        vault.set(provider+".token",json.dumps({"expires":time.time()-10,"refresh_token":"refresh-private","scope":SCOPES[provider],"access_token":"expired"}))
        result = client.post("/chat",json=command).json()
        assert "Deadline Friday" in result["message"] and "https://" in result["message"]
        assert result["mode"]==provider and "access-private" not in client.get("/state").text
        assert client.delete("/connections/"+provider).is_success
        assert vault.get(provider+".token") is None and len(calls)>=3
