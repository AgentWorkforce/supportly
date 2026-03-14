"""
Customer Service Escalation — CrewAI + Relay SDK

Two CrewAI agents (Front Desk, Specialist) collaborate via Relay DMs
to triage and resolve customer issues.
"""

import asyncio
import os
import random
import string
from datetime import datetime

from crewai import Agent, Crew, Task, Process
from crewai.tools import tool

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
    for topic in COMPLEX_TOPICS:
        if topic.replace("_", " ") in lower:
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
            f"Case {cid}: Reviewed billing records for {customer}. "
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
# CrewAI Tools — backed by Relay
# ---------------------------------------------------------------------------

@tool("escalate_to_specialist")
def escalate_to_specialist(customer_name: str, issue: str) -> str:
    """Escalate a complex customer issue to the specialist agent via Relay DM."""
    cid = case_id()
    escalation = (
        f"ESCALATION {cid}\nCustomer: {customer_name}\n"
        f"Issue: {issue}\nPriority: HIGH"
    )
    asyncio.get_event_loop().run_until_complete(
        front_relay.send("specialist", escalation)
    )
    asyncio.get_event_loop().run_until_complete(
        front_relay.post(CHANNEL, f"[Front Desk] {customer_name}'s issue ({cid}) escalated.")
    )
    return f"Escalated as {cid}"


@tool("post_direct_answer")
def post_direct_answer(customer_name: str, query: str, answer: str) -> str:
    """Post a direct answer to the general channel for a simple customer query."""
    asyncio.get_event_loop().run_until_complete(
        front_relay.post(CHANNEL, f"[Front Desk] {customer_name} asked: {query}\nAnswer: {answer}")
    )
    return f"Answered {customer_name} directly."


@tool("check_specialist_inbox")
def check_specialist_inbox() -> str:
    """Check the specialist inbox for new escalations via Relay."""
    messages = asyncio.get_event_loop().run_until_complete(spec_relay.inbox())
    escalations = [m for m in messages if "ESCALATION" in m.text]
    if not escalations:
        return "No escalations in inbox."
    return "\n---\n".join(m.text for m in escalations)


@tool("send_resolution")
def send_resolution(case_id: str, customer_name: str, resolution_text: str) -> str:
    """Send a resolution back to front desk via Relay DM and post summary."""
    asyncio.get_event_loop().run_until_complete(
        spec_relay.send("front-desk", f"RESOLUTION {case_id}\n{resolution_text}")
    )
    asyncio.get_event_loop().run_until_complete(
        spec_relay.post(CHANNEL, f"[Specialist] Resolved {case_id} for {customer_name}.")
    )
    return f"Resolution sent for {case_id}."


@tool("check_frontdesk_inbox")
def check_frontdesk_inbox() -> str:
    """Check the front desk inbox for specialist resolutions via Relay."""
    messages = asyncio.get_event_loop().run_until_complete(front_relay.inbox())
    resolutions = [m for m in messages if "RESOLUTION" in m.text]
    if not resolutions:
        return "No resolutions in inbox."
    return "\n---\n".join(m.text for m in resolutions)


# ---------------------------------------------------------------------------
# CrewAI Agents
# ---------------------------------------------------------------------------

front_desk_agent = Agent(
    role="Front Desk Agent",
    goal="Triage customer queries: answer simple ones directly, escalate complex ones.",
    backstory="You are the first point of contact for customer service.",
    tools=[escalate_to_specialist, post_direct_answer],
    verbose=True,
)

specialist_agent = Agent(
    role="Specialist Agent",
    goal="Resolve escalated customer issues with detailed resolutions.",
    backstory="You are a senior specialist handling billing disputes and security incidents.",
    tools=[check_specialist_inbox, send_resolution],
    verbose=True,
)

followup_agent = Agent(
    role="Follow-up Agent",
    goal="Retrieve specialist resolutions and post them to the channel.",
    backstory="You close the loop by relaying specialist responses.",
    tools=[check_frontdesk_inbox],
    verbose=True,
)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def build_triage_description() -> str:
    lines = ["Triage the following customer queries:\n"]
    for c in CUSTOMERS:
        cat = classify(c["query"])
        lines.append(f"- {c['name']}: \"{c['query']}\" → {cat}")
        if cat == "simple":
            lines.append(f"  Answer: {simple_answer(c['query'])}")
    return "\n".join(lines)


triage_task = Task(
    description=build_triage_description(),
    expected_output="Each customer handled or escalated.",
    agent=front_desk_agent,
)

specialist_task = Task(
    description="Check your inbox for escalations and resolve each one.",
    expected_output="All escalations resolved with case numbers.",
    agent=specialist_agent,
)

followup_task = Task(
    description="Check the front-desk inbox for resolutions and report them.",
    expected_output="All resolutions retrieved and posted.",
    agent=followup_agent,
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — CrewAI")
    print("=" * 60)

    await front_relay.connect()
    await spec_relay.connect()
    print("Relay agents connected.\n")

    crew = Crew(
        agents=[front_desk_agent, specialist_agent, followup_agent],
        tasks=[triage_task, specialist_task, followup_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()
    print("\n--- Crew Result ---")
    print(result)

    await front_relay.close()
    await spec_relay.close()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
