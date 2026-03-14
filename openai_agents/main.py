"""
Customer Service Escalation — OpenAI Agents SDK + Relay SDK

Two OpenAI function-calling agents (Front Desk, Specialist) collaborate
via Relay DMs to triage and resolve customer issues.
"""

import asyncio
import os
import random
import string
from datetime import datetime

from agents import Agent, Runner, function_tool

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
COMPLEX_KEYWORDS = ["billing dispute", "security incident", "legal", "fraud"]

front_relay = Relay("front-desk", config)
spec_relay = Relay("specialist", config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def case_id() -> str:
    tag = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CASE-{tag}"


def classify(query: str) -> str:
    lower = query.lower()
    for kw in COMPLEX_KEYWORDS:
        if kw in lower:
            return "complex"
    return "simple"


def simple_answer(query: str) -> str:
    lower = query.lower()
    if "hours" in lower or "open" in lower:
        return "Our business hours are Mon-Fri 9 AM to 6 PM EST."
    if "shipping" in lower:
        return "Standard shipping takes 3-5 business days. Express is 1-2 days."
    if "return" in lower:
        return "You can return items within 30 days with a receipt."
    return "Please visit our FAQ at help.example.com for more details."


def generate_resolution(cid: str, customer: str, issue: str) -> str:
    lower = issue.lower()
    if "billing" in lower or "charged" in lower:
        return (
            f"Case {cid}: Reviewed billing for {customer}. "
            "Duplicate charge confirmed. Refund of $49.99 initiated — "
            "expect 3-5 business days."
        )
    if "security" in lower or "compromised" in lower:
        return (
            f"Case {cid}: Account for {customer} locked. "
            "Unauthorized transactions reversed. Temporary credentials "
            "sent to verified email. Reset password within 24h."
        )
    return f"Case {cid}: Issue for {customer} reviewed and resolved."


# ---------------------------------------------------------------------------
# Customer interactions
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"name": "Alice", "query": "What are your business hours?"},
    {"name": "Bob", "query": "I have a billing dispute — I was charged twice for order #1042."},
    {"name": "Carol", "query": "Security incident: my account appears compromised, unauthorized purchases."},
]


# ---------------------------------------------------------------------------
# OpenAI Function Tools — backed by Relay
# ---------------------------------------------------------------------------

@function_tool
async def escalate_to_specialist(customer_name: str, issue: str) -> str:
    """Escalate a complex customer issue to the specialist agent via Relay DM."""
    cid = case_id()
    escalation = (
        f"ESCALATION {cid}\nCustomer: {customer_name}\n"
        f"Issue: {issue}\nPriority: HIGH"
    )
    await front_relay.send("specialist", escalation)
    await front_relay.post(
        CHANNEL, f"[Front Desk] {customer_name}'s issue ({cid}) escalated to specialist."
    )
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Front Desk — escalated {customer_name} → specialist ({cid})")
    return f"Escalated {customer_name}'s issue as {cid}."


@function_tool
async def post_direct_answer(customer_name: str, query: str, answer: str) -> str:
    """Post a direct answer to the general channel for a simple query."""
    await front_relay.post(
        CHANNEL, f"[Front Desk] {customer_name} asked: {query}\nAnswer: {answer}"
    )
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Front Desk — answered {customer_name} directly.")
    return f"Answered {customer_name}."


@function_tool
async def check_specialist_inbox() -> str:
    """Check the specialist agent's Relay inbox for new escalations."""
    messages = await spec_relay.inbox()
    escalations = [m for m in messages if "ESCALATION" in m.text]
    if not escalations:
        return "No escalations found."
    return "\n---\n".join(m.text for m in escalations)


@function_tool
async def send_resolution(case_id: str, customer_name: str, resolution_text: str) -> str:
    """Send a resolution back to front desk via Relay DM and post summary."""
    await spec_relay.send("front-desk", f"RESOLUTION {case_id}\n{resolution_text}")
    await spec_relay.post(
        CHANNEL, f"[Specialist] Resolved {case_id} for {customer_name}."
    )
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Specialist — resolved {case_id} for {customer_name}")
    return f"Resolution sent for {case_id}."


@function_tool
async def check_frontdesk_inbox() -> str:
    """Check the front desk Relay inbox for specialist resolutions."""
    messages = await front_relay.inbox()
    resolutions = [m for m in messages if "RESOLUTION" in m.text]
    if not resolutions:
        return "No resolutions found."
    return "\n---\n".join(m.text for m in resolutions)


@function_tool
async def post_followup(resolution_detail: str) -> str:
    """Post a resolution follow-up to the general channel."""
    await front_relay.post(CHANNEL, f"[Front Desk] Resolution received:\n{resolution_detail}")
    return "Follow-up posted."


# ---------------------------------------------------------------------------
# OpenAI Agents
# ---------------------------------------------------------------------------

front_desk_agent = Agent(
    name="Front Desk Agent",
    instructions=(
        "You are a customer service front desk agent. For each customer query, "
        "classify it as simple or complex. Answer simple queries directly using "
        "post_direct_answer. Escalate complex queries (billing disputes, security "
        "incidents) using escalate_to_specialist."
    ),
    tools=[escalate_to_specialist, post_direct_answer],
)

specialist_agent = Agent(
    name="Specialist Agent",
    instructions=(
        "You are a senior specialist. Check your inbox for escalations, then "
        "resolve each one with a detailed resolution including the case ID."
    ),
    tools=[check_specialist_inbox, send_resolution],
)

followup_agent = Agent(
    name="Follow-up Agent",
    instructions=(
        "You retrieve specialist resolutions from the front desk inbox and "
        "post follow-up summaries to the channel."
    ),
    tools=[check_frontdesk_inbox, post_followup],
)


# ---------------------------------------------------------------------------
# Build prompts
# ---------------------------------------------------------------------------

def triage_prompt() -> str:
    lines = ["Process these customer queries:\n"]
    for c in CUSTOMERS:
        cat = classify(c["query"])
        lines.append(f"- {c['name']}: \"{c['query']}\" (category: {cat})")
        if cat == "simple":
            lines.append(f"  Suggested answer: {simple_answer(c['query'])}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — OpenAI Agents SDK")
    print("=" * 60)

    await front_relay.connect()
    await spec_relay.connect()
    print("Relay agents connected.\n")

    # Phase 1 — triage
    print("--- Phase 1: Triage ---")
    result1 = await Runner.run(front_desk_agent, triage_prompt())
    print(f"Triage result: {result1.final_output}\n")

    # Phase 2 — specialist
    print("--- Phase 2: Specialist Processing ---")
    await asyncio.sleep(0.5)
    result2 = await Runner.run(specialist_agent, "Check inbox and resolve all escalations.")
    print(f"Specialist result: {result2.final_output}\n")

    # Phase 3 — follow-up
    print("--- Phase 3: Follow-up ---")
    await asyncio.sleep(0.5)
    result3 = await Runner.run(followup_agent, "Check inbox for resolutions and post follow-ups.")
    print(f"Follow-up result: {result3.final_output}\n")

    await front_relay.close()
    await spec_relay.close()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
