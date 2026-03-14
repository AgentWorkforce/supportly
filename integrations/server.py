"""
Nango Connect UI Backend — FastAPI server for managing OAuth connections.

Provides session token creation, webhook handling, and connection management
for the Supportly AI customer service POC.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from nango_integrations import get_available_integrations

app = FastAPI(title="Supportly Integrations", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

NANGO_SECRET_KEY = os.environ.get("NANGO_SECRET_KEY", "")
NANGO_API_URL = "https://api.nango.dev"

# In-memory connection store (use a database in production)
connections: dict[str, dict] = {}


@app.get("/api/integrations")
async def list_integrations():
    """Return all available integration definitions for the frontend."""
    integrations = get_available_integrations()
    return {
        "integrations": [
            {
                "name": i.name,
                "provider_id": i.provider_id,
                "auth_mode": i.auth_mode.value,
                "description": i.description,
                "use_cases": i.use_cases,
            }
            for i in integrations
        ]
    }


@app.post("/api/nango/session-token")
async def create_session_token(request: Request):
    """Generate a Nango Connect session token for the frontend."""
    if not NANGO_SECRET_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "NANGO_SECRET_KEY not configured"},
        )

    body = await request.json()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{NANGO_API_URL}/connect/sessions",
            headers={
                "Authorization": f"Bearer {NANGO_SECRET_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "tags": {
                    "end_user_id": body.get("user_id", "demo-user"),
                    "end_user_email": body.get("email", "demo@example.com"),
                },
                "allowed_integrations": body.get("integrations", []),
            },
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return resp.json()


@app.post("/api/nango/webhook")
async def handle_webhook(request: Request):
    """Handle Nango auth webhooks — store connection metadata."""
    body = await request.json()

    if body.get("type") == "auth" and body.get("success"):
        conn_id = body["connectionId"]
        provider = body.get("providerConfigKey", "unknown")
        tags = body.get("tags", {})
        connections[conn_id] = {
            "connection_id": conn_id,
            "provider": provider,
            "user_id": tags.get("end_user_id"),
            "status": "connected",
            "created_at": body.get("createdAt", datetime.now(timezone.utc).isoformat()),
        }

    return {"status": "ok"}


@app.get("/api/nango/connections")
async def list_connections():
    """List all active connections."""
    return {"connections": list(connections.values())}


@app.post("/api/nango/reconnect")
async def create_reconnect_session(request: Request):
    """Generate a reconnect session token for an expired connection."""
    if not NANGO_SECRET_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "NANGO_SECRET_KEY not configured"},
        )

    body = await request.json()
    connection_id = body.get("connection_id")
    integration_id = body.get("integration_id")

    if not connection_id or not integration_id:
        return JSONResponse(
            status_code=400,
            content={"error": "connection_id and integration_id are required"},
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{NANGO_API_URL}/connect/sessions/reconnect",
            headers={
                "Authorization": f"Bearer {NANGO_SECRET_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "connection_id": connection_id,
                "integration_id": integration_id,
            },
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return resp.json()


@app.get("/api/nango/connection/{connection_id}")
async def get_connection(connection_id: str, integration_id: str = ""):
    """Check the health/status of a specific connection."""
    if not NANGO_SECRET_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "NANGO_SECRET_KEY not configured"},
        )

    params = {}
    if integration_id:
        params["provider_config_key"] = integration_id

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{NANGO_API_URL}/connection/{connection_id}",
            params=params,
            headers={"Authorization": f"Bearer {NANGO_SECRET_KEY}"},
        )
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        return resp.json()
