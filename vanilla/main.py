"""
Customer Service Escalation — Pure Python (asyncio + Relay SDK)

Two agents collaborate: Front Desk handles simple queries directly,
escalates complex issues to a Specialist via Relay DM.
"""

import asyncio
import os
import random
import string
from datetime import datetime

from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

import uuid
from dotenv import load_dotenv
load_dotenv()
RUN_ID = uuid.uuid4().hex[:6]


def get_llm_config():
    """Detect LLM provider: OpenRouter > OpenAI > None (use mock responses)."""
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if openrouter_key:
        return {
            'api_key': openrouter_key,
            'base_url': 'https://openrouter.ai/api/v1',
            'model': os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini'),
        }
    openai_key = os.environ.get('OPENAI_API_KEY')
    if openai_key:
        return {'api_key': openai_key, 'model': os.environ.get('MODEL', 'gpt-4o-mini')}
    return None


LLM_CONFIG = get_llm_config()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

config = RelayConfig(
    workspace=os.environ.get("RELAY_WORKSPACE", "demo"),
    api_key=os.environ.get("RELAY_API_KEY", "demo-key"),
    base_url=os.environ.get("RELAY_BASE_URL", "https://api.relaycast.dev"),
)

CHANNEL = "general"

SIMPLE_TOPICS = {"hours", "shipping", "returns", "tracking", "faq"}
COMPLEX_TOPICS = {"billing_dispute", "security_incident", "legal", "fraud"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def case_id() -> str:
    tag = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CASE-{tag}"


def classify(query: str) -> str:
    lower = query.lower()
    for topic in COMPLEX_TOPICS:
        if topic.replace("_", " ") in lower:
            return "complex"
    return "simple"


def simple_response(query: str) -> str:
    lower = query.lower()
    if "hours" in lower or "open" in lower:
        return "Our business hours are Mon-Fri 9 AM to 6 PM EST."
    if "shipping" in lower:
        return "Standard shipping takes 3-5 business days. Express is 1-2 days."
    if "return" in lower:
        return "You can return items within 30 days with a receipt."
    return "Please visit our FAQ at help.example.com for more details."


# ---------------------------------------------------------------------------
# Customer interactions
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"name": "Alice", "query": "What are your business hours?"},
    {"name": "Bob", "query": "I have a billing dispute — I was charged twice for order #1042."},
    {"name": "Carol", "query": "Security incident: my account appears compromised, unauthorized purchases."},
]


# ---------------------------------------------------------------------------
# Front Desk Agent
# ---------------------------------------------------------------------------

async def front_desk(relay: Relay) -> list[str]:
    """Triage customer queries. Returns list of escalated case descriptions."""
    escalated = []
    for customer in CUSTOMERS:
        name, query = customer["name"], customer["query"]
        category = classify(query)
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Front Desk — {name}: {query}")

        if category == "simple":
            answer = simple_response(query)
            await relay.post(CHANNEL, f"[Front Desk] {name} asked: {query}\nAnswer: {answer}")
            print(f"[{ts}] Front Desk — answered {name} directly.")
        else:
            cid = case_id()
            escalation_msg = (
                f"ESCALATION {cid}\n"
                f"Customer: {name}\n"
                f"Issue: {query}\n"
                f"Priority: HIGH"
            )
            await relay.send(f"specialist-{RUN_ID}", escalation_msg)
            await relay.post(
                CHANNEL,
                f"[Front Desk] {name}'s issue ({cid}) escalated to specialist.",
            )
            escalated.append(cid)
            print(f"[{ts}] Front Desk — escalated {name} → specialist ({cid}).")

    return escalated


# ---------------------------------------------------------------------------
# Specialist Agent
# ---------------------------------------------------------------------------

async def specialist_process(relay: Relay, escalation_messages: list[Message]) -> None:
    """Process pre-captured escalation messages."""
    for msg in escalation_messages:
        if "ESCALATION" not in msg.text:
            continue

        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        customer_line = next((l for l in lines if l.startswith("Customer:")), "")
        issue_line = next((l for l in lines if l.startswith("Issue:")), "")
        customer_name = customer_line.replace("Customer:", "").strip()
        issue = issue_line.replace("Issue:", "").strip()

        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Specialist — processing {cid} for {customer_name}")

        resolution = generate_resolution(cid, customer_name, issue)

        await relay.send(f"front-desk-{RUN_ID}", f"RESOLUTION {cid}\n{resolution}")
        await relay.post(CHANNEL, f"[Specialist] Resolved {cid} for {customer_name}.")
        print(f"[{ts}] Specialist — resolved {cid}.")


def generate_resolution(cid: str, customer: str, issue: str) -> str:
    lower = issue.lower()
    if "billing" in lower or "charged" in lower:
        return (
            f"Case {cid}: Reviewed billing records for {customer}. "
            "Duplicate charge confirmed. Refund of $49.99 initiated — "
            "expect 3-5 business days. Apologies for the inconvenience."
        )
    if "security" in lower or "compromised" in lower:
        return (
            f"Case {cid}: Account for {customer} has been locked. "
            "Unauthorized transactions reversed. Temporary credentials "
            "sent to verified email. Please reset password within 24h."
        )
    return f"Case {cid}: Issue for {customer} reviewed and resolved."


# ---------------------------------------------------------------------------
# Follow-up — Front Desk reads specialist responses
# ---------------------------------------------------------------------------

async def follow_up(relay: Relay, resolution_messages: list[Message]) -> None:
    """Process pre-captured resolution messages."""
    for msg in resolution_messages:
        if "RESOLUTION" not in msg.text:
            continue
        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        detail = "\n".join(lines[1:]).strip()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Front Desk — received resolution for {cid}")
        await relay.post(CHANNEL, f"[Front Desk] Resolution received:\n{detail}")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — Vanilla Python")
    print("=" * 60)
    print(f"LLM provider: {LLM_CONFIG['base_url'] if LLM_CONFIG and 'base_url' in LLM_CONFIG else 'OpenAI' if LLM_CONFIG else 'mock'}")

    front = Relay(f"front-desk-{RUN_ID}", config)
    spec = Relay(f"specialist-{RUN_ID}", config)

    await front.join("general")
    await spec.join("general")
    print("Agents ready.\n")

    # Set up message capture via on_message
    escalation_msgs = []
    resolution_msgs = []
    escalations_done = asyncio.Event()
    resolutions_done = asyncio.Event()
    expected_escalations = sum(1 for c in CUSTOMERS if classify(c["query"]) == "complex")

    def capture_escalations(msg):
        if "ESCALATION" in msg.text:
            escalation_msgs.append(msg)
            if len(escalation_msgs) >= expected_escalations:
                escalations_done.set()

    def capture_resolutions(msg):
        if "RESOLUTION" in msg.text:
            resolution_msgs.append(msg)
            if len(resolution_msgs) >= expected_escalations:
                resolutions_done.set()

    unsub_esc = spec.on_message(capture_escalations)
    unsub_res = front.on_message(capture_resolutions)

    # Phase 1 — triage
    print("--- Phase 1: Triage ---")
    escalated = await front_desk(front)
    print(f"\nEscalated cases: {escalated}\n")

    # Phase 2 — wait for escalations to arrive, then process
    print("--- Phase 2: Specialist Processing ---")
    if expected_escalations > 0:
        await asyncio.wait_for(escalations_done.wait(), timeout=30)
    unsub_esc()
    await specialist_process(spec, escalation_msgs)
    print()

    # Phase 3 — wait for resolutions to arrive, then process
    print("--- Phase 3: Follow-up ---")
    if expected_escalations > 0:
        await asyncio.wait_for(resolutions_done.wait(), timeout=30)
    unsub_res()
    await follow_up(front, resolution_msgs)
    print()

    # Cleanup
    await asyncio.wait_for(front.close(), timeout=5)
    await asyncio.wait_for(spec.close(), timeout=5)
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
