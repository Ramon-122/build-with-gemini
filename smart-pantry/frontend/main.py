"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from google.protobuf import json_format

from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    SendMessageRequest,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card_data = resp.json()
        if hasattr(AgentCard, "model_validate"):
            card = AgentCard.model_validate(card_data)
        else:
            card = json_format.ParseDict(card_data, AgentCard(), ignore_unknown_fields=True)
        card.url = A2A_BASE
        _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI."""
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        text_val = getattr(root, "text", None)
        if text_val:
            out.append({"kind": "text", "text": text_val})
            continue

        data_val = getattr(root, "data", None)
        if data_val is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else getattr(meta, "mime_type", None)
            if mime == _A2UI_MIME:
                out.append({"kind": "a2ui", "data": data_val})
                continue

        file_obj = getattr(root, "file", None)
        uri = getattr(root, "uri", None) or getattr(file_obj, "uri", None)
        if uri:
            out.append({"kind": "text", "text": uri})

    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        user_role = getattr(Role, "ROLE_USER", getattr(Role, "user", 1))
        part_obj = Part(text=message)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=user_role,
            parts=[part_obj],
            context_id=_contexts.get(user_id),
        )

        try:
            from a2a.types import MessageSendParams
            params = MessageSendParams(message=msg)
        except (ImportError, Exception):
            params = {"message": msg}

        try:
            send_req = SendMessageRequest(id=str(uuid.uuid4()), params=params)
        except Exception:
            send_req = SendMessageRequest(message=msg)

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(send_req):
            if isinstance(event, tuple):
                task, update = event
            else:
                task, update = event, None

            if task is not None:
                last_task = task
                ctx_id = getattr(task, "context_id", None) or getattr(task, "contextId", None)
                if ctx_id:
                    _contexts[user_id] = ctx_id

            if update is not None:
                art = getattr(update, "artifact", None)
                if art:
                    got_artifact_update = True
                    parts.extend(_extract_parts(getattr(art, "parts", [])))

        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(getattr(artifact, "parts", [])))

    if not parts:
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
app.mount("/", StaticFiles(directory="frontend/static" if os.path.exists("frontend/static") else "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
