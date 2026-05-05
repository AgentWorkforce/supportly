# Customer Service Escalation

Two agents (Front Desk + Specialist) triage customer queries. Simple ones answered directly, complex ones escalated via Relay DM.

**Agents:** Front Desk, Specialist
**Integrations:** Zendesk, Intercom, Freshdesk, HubSpot, Salesforce, Slack, Stripe, Shopify + 10 more

## Prerequisites

- Python 3.10+
- Agent Relay SDK: `pip install 'agent-relay-sdk[communicate]>=6.0.9'`

## Framework Variants

Each variant implements the same app with a different AI/agent framework:

| Variant | Path | Framework | LLM Required |
|---------|------|-----------|-------------|
| Vanilla | `vanilla/main.py` | Pure Python asyncio | No (simulated) |
| CrewAI | `crewai/main.py` | CrewAI task orchestration | Optional |
| OpenAI Agents | `openai_agents/main.py` | OpenAI function-calling | Optional |
| LangGraph | `langgraph/main.py` | LangGraph state machine | Optional |
| Google ADK | `google_adk/main.py` | Google Agent Dev Kit | Optional |

## Quick Start

### 1. Set environment variables

```bash
# Required — Relay SDK connection
export RELAY_API_KEY=rk_live_YOUR_KEY
export RELAY_WORKSPACE=your-workspace
export RELAY_BASE_URL=https://api.relaycast.dev

# Optional — LLM provider (choose one)
export OPENROUTER_API_KEY=sk-or-...          # OpenRouter (100+ models)
export OPENROUTER_MODEL=anthropic/claude-3.5-sonnet  # default: openai/gpt-4o-mini

# OR
export OPENAI_API_KEY=sk-...                 # OpenAI directly

# No LLM key? App runs with simulated/mock responses.
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the live demo (browser UI)

```bash
python3 server.py
# open http://localhost:8081
```

Five agents register on Relay (~10s), then submit a ticket via the UI to
watch the live event feed: triage → channel post → specialist pickup →
resolution → QA score, with cost comparison vs single-agent.

### 4. Run the vanilla CLI variant

```bash
python3 vanilla/main.py
```

### 5. Run other framework variants

```bash
python3 crewai/main.py
python3 openai_agents/main.py
python3 langgraph/main.py
python3 google_adk/main.py
```

## Nango Integrations

### Start the integration server

```bash
pip install -r integrations/requirements.txt
cd integrations && uvicorn server:app --host 0.0.0.0 --port 8080
```

### Set Nango credentials

```bash
export NANGO_SECRET_KEY=your-nango-secret-key
```

### Open the frontend

Open `index.html` in a browser. Click "Connect" on any integration card to launch the Nango Connect UI.

### Backend endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/nango/session-token` | POST | Generate Connect session token |
| `/api/nango/webhook` | POST | Handle auth webhooks |
| `/api/nango/connections` | GET | List active connections |
| `/api/nango/reconnect` | POST | Reconnect expired connection |
| `/api/nango/connection/{id}` | GET | Check connection health |

## Testing

### Run with live Relay

```bash
export RELAY_API_KEY=rk_live_YOUR_KEY_HERE
export RELAY_WORKSPACE=kjgbot
export RELAY_BASE_URL=https://api.relaycast.dev
python3 vanilla/main.py
```

### Run with mock (no API key needed)

```bash
python3 vanilla/main.py
# Uses demo defaults — agents register, communicate, and clean up
```

### Test all variants

```bash
for variant in vanilla crewai openai_agents langgraph google_adk; do
  echo "=== $variant ==="
  timeout 60 python3 $variant/main.py
  echo "EXIT: $?"
  sleep 5
done
```

## Project Structure

```
relay-poc-customer-service/
├── vanilla/main.py        # Pure Python implementation
├── crewai/main.py         # CrewAI variant
├── openai_agents/main.py  # OpenAI Agents variant
├── langgraph/main.py      # LangGraph variant
├── google_adk/main.py     # Google ADK variant


├── integrations/
│   ├── nango_integrations.py  # Integration configs
│   ├── server.py              # FastAPI backend
│   └── requirements.txt
├── index.html                 # Tailwind CSS frontend
├── assets/                    # Logos
└── README.md
```

