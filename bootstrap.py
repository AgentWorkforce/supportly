"""Auto-provision a Relaycast workspace on first run.

Supportly is a zero-config demo: clone, install, run. If RELAY_API_KEY
and RELAY_WORKSPACE are not set in the environment, this module
provisions a fresh workspace via the public Relaycast API and caches
the credentials in `.relay-state.json` so subsequent runs reuse it.

Set RELAY_API_KEY (and optionally RELAY_WORKSPACE) in the environment
to override and point at an existing workspace instead.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx

from agent_relay.communicate.types import RelayConfig

DEFAULT_BASE_URL = "https://api.relaycast.dev"
STATE_FILE = Path(__file__).parent / ".relay-state.json"


def _provision_workspace(base_url: str) -> dict:
    """POST /v1/workspaces with no auth and return {workspace, api_key}."""
    name = f"supportly-{uuid.uuid4().hex[:8]}"
    response = httpx.post(
        f"{base_url}/v1/workspaces",
        json={"name": name},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Failed to create workspace: {payload}")
    data = payload["data"]
    return {
        "workspace": name,
        "workspace_id": data["workspace_id"],
        "api_key": data["api_key"],
        "base_url": base_url,
    }


def get_relay_config() -> RelayConfig:
    """Return a RelayConfig, bootstrapping a workspace if needed.

    Resolution order:
      1. Env vars (RELAY_API_KEY + RELAY_WORKSPACE) — use as-is.
      2. Cached state in `.relay-state.json` — reuse.
      3. Provision a fresh workspace and cache it.
    """
    base_url = os.environ.get("RELAY_BASE_URL", DEFAULT_BASE_URL)

    api_key = os.environ.get("RELAY_API_KEY")
    workspace = os.environ.get("RELAY_WORKSPACE")
    if api_key and workspace:
        return RelayConfig(workspace=workspace, api_key=api_key, base_url=base_url)

    if STATE_FILE.exists():
        cached = json.loads(STATE_FILE.read_text())
        if cached.get("api_key") and cached.get("workspace") and cached.get("base_url") == base_url:
            return RelayConfig(
                workspace=cached["workspace"],
                api_key=cached["api_key"],
                base_url=base_url,
            )

    print(f"No RELAY_API_KEY set — provisioning a fresh workspace on {base_url}...")
    state = _provision_workspace(base_url)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    observer = f"https://agentrelay.com/observer?key={state['api_key']}"
    print(f"  workspace: {state['workspace']}")
    print(f"  observer:  {observer}")
    print(f"  cached to: {STATE_FILE.name} (delete to re-provision)")
    return RelayConfig(
        workspace=state["workspace"],
        api_key=state["api_key"],
        base_url=base_url,
    )
