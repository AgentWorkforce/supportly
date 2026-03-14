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
            await relay.send("specialist", escalation_msg)
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

async def specialist_process(relay: Relay) -> None:
    """Check inbox for escalations and resolve them."""
    await asyncio.sleep(0.5)  # allow messages to arrive
    messages = await relay.inbox()

    for msg in messages:
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

        await relay.send("front-desk", f"RESOLUTION {cid}\n{resolution}")
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

async def follow_up(relay: Relay) -> None:
    """Front desk checks inbox for specialist resolutions."""
    await asyncio.sleep(0.5)
    messages = await relay.inbox()

    for msg in messages:
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

    front = Relay("front-desk", config)
    spec = Relay("specialist", config)

    await front.connect()
    await spec.connect()
    print("Agents connected.\n")

    # Phase 1 — triage
    print("--- Phase 1: Triage ---")
    escalated = await front_desk(front)
    print(f"\nEscalated cases: {escalated}\n")

    # Phase 2 — specialist handles escalations
    print("--- Phase 2: Specialist Processing ---")
    await specialist_process(spec)
    print()

    # Phase 3 — front desk reads resolutions
    print("--- Phase 3: Follow-up ---")
    await follow_up(front)
    print()

    # Cleanup
    await front.close()
    await spec.close()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
