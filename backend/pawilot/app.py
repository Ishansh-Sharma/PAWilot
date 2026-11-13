import hmac
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from .connections import Connections

Provider = Literal["gmail", "slack"]

class Registration(BaseModel):
    client_id: str = Field(min_length=1,max_length=512)
    client_secret: str = Field(default="",max_length=1024)


from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent, AgentError
import httpx
from .models import ActivitySample, ChatInput, Decision, KeyInput, RecordInput, SettingsInput, ProfileInput, ImportCommit
from .store import Store
from .importer import ImportSessions, MAX_UPLOAD


def create_app(data_path: Path, token: str, vault, model_client=None, connector_transport=None):
    if len(token) < 32:
        raise ValueError("A strong per-launch token is required")
    app = FastAPI(title="PAWilot local agent", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    store = Store(data_path)
    agent = Agent(store, vault, model_client)
    accounts = Connections(vault, connector_transport)
    agent.accounts = accounts
    app.state.store = store
    app.state.agent = agent
    imports = ImportSessions()

    @app.middleware("http")
    async def protect(request: Request, call_next):
        if request.headers.get("origin") or request.headers.get("sec-fetch-site"):
            return JSONResponse({"detail": "Browser requests are not permitted"}, status_code=403)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        limit = MAX_UPLOAD if request.url.path == "/imports/preview" else 600_000 if request.url.path == "/imports/commit" else 100_000
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(KeyError)
    async def not_found(request, error):
        return JSONResponse({"detail": "Record or action not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/state")
    def state():
        return {"records": store.records(), "messages": store.messages(), "actions": store.actions(),
                "settings": store.settings().model_dump(), "has_api_key": bool(vault.get("gemini")),
                "connections": accounts.status(), "profile": store.profile(),
                "retrieval": store.setting("last_retrieval", {}), "activity": store.activity(40)}

    @app.put("/connections/{provider}/registration")
    async def registration(provider: Provider, value: Registration):
        async with accounts.lock:
            accounts.configure(provider,value.client_id.strip(),value.client_secret.strip())
        return {"status":"configured"}

    @app.post("/connections/{provider}/authorize")
    async def authorize(provider: Provider):
        async with accounts.lock:
            return {"url":await accounts.start(provider)}

    @app.delete("/connections/{provider}")
    async def disconnect(provider: Provider):
        async with accounts.lock:
            await accounts.disconnect(provider)
        return {"status":"disconnected"}

    @app.put("/profile")
    async def profile(value: ProfileInput):
        async with agent.lock:
            store.set_setting("profile", value.model_dump())
        return value

    @app.post("/imports/preview")
    async def preview(request: Request):
        async with agent.lock:
            return imports.preview(await request.body())

    @app.get("/imports/{session_id}")
    def import_page(session_id: str, offset: int = Query(default=0, ge=0, le=10000)):
        return imports.page(session_id, offset)

    @app.post("/imports/commit")
    async def commit(value: ImportCommit):
        async with agent.lock:
            session = imports.get(value.session_id)
            return store.import_records(value.selections, {c["id"]:c for c in session["candidates"]})

    @app.delete("/imports")
    async def cancel_import():
        async with agent.lock:
            imports.cancel()
        return {"status":"discarded"}

    @app.post("/records")
    async def create(record: RecordInput):
        async with agent.lock:
            return store.put(record)

    @app.put("/records/{record_id}")
    async def update(record_id: str, record: RecordInput):
        async with agent.lock:
            return store.put(record, record_id)

    @app.delete("/records/{record_id}")
    async def delete(record_id: str):
        async with agent.lock:
            store.delete(record_id)
            store.set_setting("last_retrieval", {})
        return {"status": "deleted"}

    @app.post("/chat")
    async def chat(message: ChatInput):
        return await agent.respond(message.text)

    @app.post("/actions/{action_id}/decision")
    async def decide(action_id: str, decision: Decision):
        async with agent.lock:
            return store.decide(action_id, decision.approve)

    @app.post("/activity")
    async def observe(sample: ActivitySample):
        # Observation only: the native app reports the foreground app and window title.
        if not store.settings().activity_awareness:
            return {"recorded": False, "nudge": None}
        store.record_activity(sample)
        return {"recorded": True, "nudge": await agent.check_in()}

    @app.delete("/activity")
    async def clear_activity():
        async with agent.lock:
            store.clear_activity()
        return {"status": "deleted"}

    @app.delete("/history")
    async def clear_history():
        async with agent.lock:
            store.clear_history()
        return {"status": "deleted"}

    @app.delete("/actions")
    async def clear_actions():
        async with agent.lock:
            with store.db() as db:
                db.execute("DELETE FROM actions")
        return {"status": "deleted"}

    @app.put("/settings")
    async def settings(value: SettingsInput):
        async with agent.lock:
            store.set_setting("preferences", value.model_dump())
        return value

    @app.put("/credentials/gemini")
    async def set_key(key: KeyInput):
        async with agent.lock:
            try:
                vault.set("gemini", key.value)
            except Exception:
                raise HTTPException(503, "Keychain could not save the credential. Check macOS Keychain access.")
            current = store.settings()
            current.ai_enabled = True
            store.set_setting("preferences", current.model_dump())
        return {"status": "saved"}

    @app.delete("/credentials/gemini")
    async def delete_key():
        async with agent.lock:
            vault.delete("gemini")
            current = store.settings()
            current.ai_enabled = False
            store.set_setting("preferences", current.model_dump())
        return {"status": "deleted"}

    @app.post("/credentials/gemini/check")
    async def check_key():
        async with agent.lock:
            try:
                await agent.check_connection()
            except httpx.HTTPStatusError as error:
                code = error.response.status_code
                reason = {400:"Check the key and model ID", 401:"Invalid API key", 403:"Key or model access denied", 404:"Model unavailable", 429:"Quota or rate limit reached"}.get(code, "Gemini is unavailable")
                raise HTTPException(502, f"{reason} (HTTP {code}). Your key remains saved; retry after fixing the issue.")
            except (httpx.HTTPError, AgentError, ValueError, KeyError, TypeError, IndexError):
                raise HTTPException(502, "Gemini did not complete the connection test. Check your key, model and network.")
        return {"status":"connected"}

    return app

