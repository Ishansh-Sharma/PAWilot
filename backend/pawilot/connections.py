"""Read-only provider clients. Only the short-lived OAuth return listener accepts browser traffic."""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit, quote

import httpx
from fastapi import HTTPException

GMAIL = "https://www.googleapis.com/auth/gmail.readonly"
SLACK = "search:read"
SCOPES = {"gmail": GMAIL, "slack": SLACK}
AUTH = {"gmail":"https://accounts.google.com/o/oauth2/v2/auth", "slack":"https://slack.com/oauth/v2/authorize"}
TOKEN = {"gmail":"https://oauth2.googleapis.com/token", "slack":"https://slack.com/api/oauth.v2.access"}


class Connections:
    def __init__(self, vault, transport=None):
        self.vault = vault
        self.transport = transport
        self.pending = {}
        self.notice = {}
        self.lock = asyncio.Lock()

    def load(self, provider, kind):
        return json.loads(self.vault.get(provider+"."+kind) or "{}")

    def save(self, provider, kind, value):
        self.vault.set(provider+"."+kind, json.dumps(value))

    def status(self):
        return {p: self.notice.get(p) or ("Connected" if self.load(p,"token") else
                "Ready to connect" if self.load(p,"config") else "Setup required") for p in SCOPES}

    def configure(self, p, client_id, secret):
        if self.load(p,"token") or p in self.pending:
            raise HTTPException(409,"Disconnect first to change the app registration.")
        pattern = r"[\w.-]+\.apps\.googleusercontent\.com" if p=="gmail" else r"[0-9]+\.[0-9]+"
        if not re.fullmatch(pattern,client_id) or (p=="gmail" and not secret):
            raise HTTPException(422,"Check the provider client ID and desktop client credentials.")
        self.save(p,"config", {"client_id":client_id, **({"client_secret":secret} if p=="gmail" else {})})
        self.notice.pop(p,None)

    async def request(self, method, url, **kwargs):
        async with httpx.AsyncClient(transport=self.transport,timeout=15,trust_env=False) as client:
            try:
                res = await client.request(method,url,**kwargs)
                if res.status_code == 429:
                    raise HTTPException(429,"Provider rate limit reached. Retry later.")
                if res.status_code in (400,401,403):
                    raise HTTPException(403,"Provider denied access. Check app configuration, API enablement and account consent.")
                res.raise_for_status()
                body = res.json() if res.content else {}
                if body.get("ok") is False:
                    raise HTTPException(403,"Slack denied this request. Check the workspace, permissions and app approval.")
                return body
            except (httpx.HTTPError,ValueError):
                raise HTTPException(502,"Provider unavailable. Check your network and retry.")

    def stop(self,p):
        flow = self.pending.pop(p,None)
        if flow:
            flow["server"].close()
            flow["timer"].cancel()

    async def start(self,p):
        cfg = self.load(p,"config")
        if not cfg:
            raise HTTPException(409,"Configure the app registration first.")
        self.stop(p)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        async def receive(reader,writer):
            message = "Invalid or expired authorization. Return to Paw."
            try:
                header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"),5)
                method,target,_ = header.split(b"\r\n",1)[0].decode("ascii").split()
                parts = urlsplit(target)
                args = parse_qs(parts.query)
                async with self.lock:
                    flow = self.pending.get(p)
                    if method=="GET" and parts.path=="/paw/oauth" and flow and flow["state"]==state and hmac.compare_digest(args.get("state",[""])[0],state):
                        self.stop(p)
                        if args.get("code") and not args.get("error"):
                            try:
                                await self.exchange(p,dict(cfg,grant_type="authorization_code",code=args["code"][0],redirect_uri=redirect,code_verifier=verifier))
                                self.notice.pop(p,None)
                                message = "Connected. Return to Paw."
                            except Exception:
                                self.notice[p] = "Authorization failed. Check provider settings and reconnect."
                                message = self.notice[p]
                        else:
                            self.notice[p] = "Authorization cancelled. Connect again when ready."
                            message = self.notice[p]
                writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n"+message).encode())
                await writer.drain()
            except (ValueError, UnicodeError, OSError, EOFError, asyncio.LimitOverrunError, TimeoutError):
                pass
            finally:
                writer.close()
        try:
            server = await asyncio.start_server(receive,"127.0.0.1",8766 if p=="slack" else 0,limit=8192)
        except OSError:
            raise HTTPException(409,"Local sign-in port unavailable. Close other Paw sign-in attempts and retry.")
        port = server.sockets[0].getsockname()[1]
        host = "localhost" if p=="slack" else "127.0.0.1"
        redirect = f"http://{host}:{port}/paw/oauth"
        def expire():
            self.stop(p)
            self.notice[p] = "Sign-in expired. Connect again."
        self.pending[p] = {"state":state,"server":server,"timer":asyncio.get_running_loop().call_later(180,expire)}
        self.notice[p] = "Waiting for browser approval"
        params = {"client_id":cfg["client_id"],"state":state,"redirect_uri":redirect,"response_type":"code",
                  "code_challenge_method":"S256","code_challenge":base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")}
        params.update({"scope":GMAIL,"access_type":"offline","prompt":"consent"} if p=="gmail" else {"user_scope":SLACK})
        return AUTH[p]+"?"+urlencode(params)

    async def exchange(self,p,form,previous=None):
        body = await self.request("POST",TOKEN[p],data=form)
        token = body.get("authed_user",body) if p=="slack" else body
        scope = token.get("scope",(previous or {}).get("scope",""))
        if set(re.split(r"[, ]+",scope)) != {SCOPES[p]} or not token.get("access_token"):
            raise HTTPException(403,"Provider returned unexpected permissions. Check the app registration.")
        fresh = {"access_token":token["access_token"],"scope":scope,"refresh_token":token.get("refresh_token",(previous or {}).get("refresh_token")),
                 "expires":time.time()+int(token["expires_in"]) if "expires_in" in token else 0}
        self.save(p,"token",fresh)
        return fresh

    async def access(self,p):
        token = self.load(p,"token")
        if not token:
            raise HTTPException(409,"Connect "+p.capitalize()+" in Paw Settings first.")
        if token["expires"] and token["expires"] < time.time()+60:
            if not token.get("refresh_token"):
                raise HTTPException(403,"Authorization expired. Reconnect in Settings.")
            token = await self.exchange(p,dict(self.load(p,"config"),grant_type="refresh_token",refresh_token=token["refresh_token"]),token)
        return token["access_token"]

    async def disconnect(self,p):
        self.stop(p)
        token = self.load(p,"token")
        if token:
            if p=="gmail":
                await self.request("POST","https://oauth2.googleapis.com/revoke",data={"token":token.get("refresh_token") or token["access_token"]})
            else:
                await self.request("POST","https://slack.com/api/auth.revoke",headers={"Authorization":"Bearer "+await self.access(p)})
        self.vault.delete(p+".token")
        self.notice.pop(p,None)

    async def search(self,p,query):
        async with self.lock:
            headers = {"Authorization":"Bearer "+await self.access(p)}
            if p=="slack":
                res = await self.request("GET","https://slack.com/api/search.messages",headers=headers,params={"query":query or "after:"+time.strftime("%Y-%m-%d",time.localtime(time.time()-7*86400)),"count":5,"sort":"timestamp"})
                rows = []
                for item in res.get("messages",{}).get("matches",[])[:5]:
                    link = urlsplit(item.get("permalink",""))
                    if link.scheme=="https" and (link.hostname or "").endswith(".slack.com"):
                        rows.append("#"+item.get("channel",{}).get("name","channel")+" — "+item.get("text","")[:600]+"\n"+link.geturl())
                return rows
            base = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
            listing = await self.request("GET",base,headers=headers,params={"q":query or "in:inbox","maxResults":5})
            rows = []
            for item in listing.get("messages",[])[:5]:
                msg = await self.request("GET",base+"/"+quote(item["id"],safe=""),headers=headers,
                                         params={"format":"metadata","metadataHeaders":["Subject","From"],"fields":"threadId,snippet,payload/headers"})
                fields = {h["name"].lower():h["value"] for h in msg.get("payload",{}).get("headers",[])}
                rows.append(fields.get("subject","(no subject)")+" — "+fields.get("from","")+"\n"+msg.get("snippet","")[:600]+"\nhttps://mail.google.com/mail/u/0/#all/"+quote(msg["threadId"],safe=""))
            return rows
