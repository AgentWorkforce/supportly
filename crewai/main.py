"""
Customer Service Escalation — CrewAI + Relay SDK

Two CrewAI agents (Front Desk, Specialist) collaborate via Relay DMs
to triage and resolve customer issues.

NOTE: Agent/Task/Crew definitions are kept for demonstration purposes.
Instead of crew.kickoff() (which requires an LLM), we directly execute
the tool functions to simulate the crew workflow.
"""

import asyncio
import os
import random
import re
import string
from datetime import datetime

from crewai import Agent, Crew, Task, Process
from crewai.tools import tool

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
# Wire into CrewAI agents: Agent(llm=LLM_CONFIG['model'], ...) when LLM_CONFIG is set

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

front_relay = Relay(f"front-desk-{RUN_ID}", config)
spec_relay = Relay(f"specialist-{RUN_ID}", config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_case_id() -> str:
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
# CrewAI Tools — backed by Relay (kept for demonstration)
# ---------------------------------------------------------------------------

@tool("escalate_to_specialist")
def escalate_to_specialist(customer_name: str, issue: str) -> str:
    """Escalate a complex customer issue to the specialist agent via Relay DM."""
    cid = make_case_id()
    escalation = (
        f"ESCALATION {cid}\nCustomer: {customer_name}\n"
        f"Issue: {issue}\nPriority: HIGH"
    )
    asyncio.get_event_loop().run_until_complete(
        front_relay.send(f"specialist-{RUN_ID}", escalation)
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
        spec_relay.send(f"front-desk-{RUN_ID}", f"RESOLUTION {case_id}\n{resolution_text}")
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
# CrewAI Agents (kept for demonstration — not executed via crew.kickoff)
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
# Tasks (kept for demonstration)
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
# Main — direct execution (bypasses LLM via crew.kickoff)
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — CrewAI")
    print("=" * 60)

    print("Relay agents ready.\n")

    # Crew definition kept for demonstration
    crew = Crew(
        agents=[front_desk_agent, specialist_agent, followup_agent],
        tasks=[triage_task, specialist_task, followup_task],
        process=Process.sequential,
        verbose=True,
    )
    print(f"Crew defined with {len(crew.agents)} agents, {len(crew.tasks)} tasks.\n")

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

    unsub_esc = spec_relay.on_message(capture_escalations)
    unsub_res = front_relay.on_message(capture_resolutions)

    # --- Phase 1: Triage (direct execution instead of crew.kickoff) ---
    print("--- Phase 1: Triage ---")
    for c in CUSTOMERS:
        name, query = c["name"], c["query"]
        category = classify(query)
        ts = datetime.now().strftime("%H:%M:%S")
        if category == "simple":
            answer = simple_answer(query)
            await front_relay.post(
                CHANNEL, f"[Front Desk] {name} asked: {query}\nAnswer: {answer}"
            )
            print(f"[{ts}] Front Desk — answered {name} directly.")
        else:
            cid = make_case_id()
            escalation = (
                f"ESCALATION {cid}\nCustomer: {name}\n"
                f"Issue: {query}\nPriority: HIGH"
            )
            await front_relay.send(f"specialist-{RUN_ID}", escalation)
            await front_relay.post(
                CHANNEL, f"[Front Desk] {name}'s issue ({cid}) escalated."
            )
            print(f"[{ts}] Front Desk — escalated {name} → specialist ({cid})")
    print()

    # --- Phase 2: Specialist ---
    print("--- Phase 2: Specialist Processing ---")
    if expected_escalations > 0:
        await asyncio.wait_for(escalations_done.wait(), timeout=30)
    unsub_esc()
    for msg in escalation_msgs:
        if "ESCALATION" not in msg.text:
            continue
        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        customer_line = next((l for l in lines if l.startswith("Customer:")), "")
        issue_line = next((l for l in lines if l.startswith("Issue:")), "")
        customer = customer_line.replace("Customer:", "").strip()
        issue = issue_line.replace("Issue:", "").strip()

        resolution = generate_resolution(cid, customer, issue)
        await spec_relay.send(f"front-desk-{RUN_ID}", f"RESOLUTION {cid}\n{resolution}")
        await spec_relay.post(CHANNEL, f"[Specialist] Resolved {cid} for {customer}.")
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Specialist — resolved {cid} for {customer}.")
    print()

    # --- Phase 3: Follow-up ---
    print("--- Phase 3: Follow-up ---")
    if expected_escalations > 0:
        await asyncio.wait_for(resolutions_done.wait(), timeout=30)
    unsub_res()
    for msg in resolution_msgs:
        if "RESOLUTION" not in msg.text:
            continue
        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        detail = "\n".join(lines[1:]).strip()
        await front_relay.post(CHANNEL, f"[Front Desk] Resolution received:\n{detail}")
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] Follow-up — posted resolution for {cid}.")

    await asyncio.wait_for(front_relay.close(), timeout=5)
    await asyncio.wait_for(spec_relay.close(), timeout=5)
    print()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
