# Customer Service Escalation App

A proof-of-concept demonstrating agent-to-agent communication via the **Relay Communicate SDK**. The same customer service escalation pattern is implemented across 5 different frameworks.

## Concept

Two agents collaborate to handle customer inquiries:

- **Front Desk Agent** — first point of contact. Handles simple queries (hours, shipping, returns) directly. Escalates complex issues (billing disputes, security incidents, legal matters) to the specialist via Relay DM.
- **Specialist Agent** — receives escalated issues via DM, investigates, and sends back detailed resolutions with case numbers.

### Demo Flow

Each implementation processes 3 customer interactions:

1. **Alice** asks about business hours → handled directly by front desk
2. **Bob** reports a billing dispute → escalated to specialist via DM
3. **Carol** reports a compromised account → escalated to specialist via DM

## Implementations

| Directory | Framework | Description |
|-----------|-----------|-------------|
| `vanilla/` | Pure Python | No framework — raw asyncio + Relay SDK |
| `crewai/` | CrewAI | CrewAI agents with relay tools |
| `openai_agents/` | OpenAI Agents SDK | OpenAI function-calling agents with relay tools |
| `langgraph/` | LangGraph | StateGraph with conditional routing + relay |
| `google_adk/` | Google ADK | Google Agent Development Kit with relay tools |

## Running

### Prerequisites

Set environment variables (or use defaults for demo mode):

```bash
export RELAY_WORKSPACE="my-workspace"
export RELAY_API_KEY="rk_live_..."
export RELAY_BASE_URL="https://api.relaycast.dev"
```

The Relay SDK is expected at `/tmp/relay-565/packages/sdk-py`.

### Run Each Implementation

```bash
# Pure Python (no framework dependencies)
python vanilla/main.py

# CrewAI
python crewai/main.py

# OpenAI Agents SDK
python openai_agents/main.py

# LangGraph
python langgraph/main.py

# Google ADK
python google_adk/main.py
```

## Architecture

All implementations follow the same 3-phase pattern:

```
Phase 1: Triage
  Customer → Front Desk → classify query
    ├─ Simple  → respond directly, post to #general
    └─ Complex → DM specialist via relay.send(), post escalation notice

Phase 2: Specialist Processing
  Specialist → check relay.inbox() → process escalations
    → DM resolution back to front-desk via relay.send()
    → post resolution summary to #general

Phase 3: Follow-up
  Front Desk → check relay.inbox() → receive specialist responses
    → post final resolution to #general
```

## Relay SDK Usage

All implementations use the same core SDK:

```python
from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

config = RelayConfig(workspace="...", api_key="...", base_url="...")
relay = Relay("agent-name", config)

await relay.send("other-agent", "message")   # DM
await relay.post("channel", "message")        # Channel broadcast
messages = await relay.inbox()                 # Check inbox
await relay.close()                           # Disconnect
```
