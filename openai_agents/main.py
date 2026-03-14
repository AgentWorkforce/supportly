"""
Customer Service Escalation — OpenAI Agents SDK + Relay SDK

Two OpenAI function-calling agents (Front Desk, Specialist) collaborate
via Relay DMs to triage and resolve customer issues.

NOTE: Agent definitions are kept for demonstration purposes.
Instead of Runner.run() (which requires the OpenAI API), we directly
execute the tool functions to simulate the agent workflow.
"""

import asyncio
import os
import random
import string
from datetime import datetime

from agents import Agent, function_tool

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
# Wire into OpenAI Agents: set openai.api_key / openai.base_url from LLM_CONFIG
if LLM_CONFIG:
    import openai
    openai.api_key = LLM_CONFIG['api_key']
    if 'base_url' in LLM_CONFIG:
        openai.base_url = LLM_CONFIG['base_url']

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
# OpenAI Function Tools — backed by Relay (kept for demonstration)
# ---------------------------------------------------------------------------

@function_tool
async def escalate_to_specialist(customer_name: str, issue: str) -> str:
    """Escalate a complex customer issue to the specialist agent via Relay DM."""
    cid = make_case_id()
    escalation = (
        f"ESCALATION {cid}\nCustomer: {customer_name}\n"
        f"Issue: {issue}\nPriority: HIGH"
    )
    await front_relay.send(f"specialist-{RUN_ID}", escalation)
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
    escalations = []
    received = asyncio.Event()

    def handler(msg):
        if "ESCALATION" in msg.text:
            escalations.append(msg)
            received.set()

    unsub = spec_relay.on_message(handler)
    try:
        await asyncio.wait_for(received.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass
    finally:
        unsub()
    if not escalations:
        return "No escalations found."
    return "\n---\n".join(m.text for m in escalations)


@function_tool
async def send_resolution(case_id: str, customer_name: str, resolution_text: str) -> str:
    """Send a resolution back to front desk via Relay DM and post summary."""
    await spec_relay.send(f"front-desk-{RUN_ID}", f"RESOLUTION {case_id}\n{resolution_text}")
    await spec_relay.post(
        CHANNEL, f"[Specialist] Resolved {case_id} for {customer_name}."
    )
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Specialist — resolved {case_id} for {customer_name}")
    return f"Resolution sent for {case_id}."


@function_tool
async def check_frontdesk_inbox() -> str:
    """Check the front desk Relay inbox for specialist resolutions."""
    resolutions = []
    received = asyncio.Event()

    def handler(msg):
        if "RESOLUTION" in msg.text:
            resolutions.append(msg)
            received.set()

    unsub = front_relay.on_message(handler)
    try:
        await asyncio.wait_for(received.wait(), timeout=5)
    except asyncio.TimeoutError:
        pass
    finally:
        unsub()
    if not resolutions:
        return "No resolutions found."
    return "\n---\n".join(m.text for m in resolutions)


@function_tool
async def post_followup(resolution_detail: str) -> str:
    """Post a resolution follow-up to the general channel."""
    await front_relay.post(CHANNEL, f"[Front Desk] Resolution received:\n{resolution_detail}")
    return "Follow-up posted."


# ---------------------------------------------------------------------------
# OpenAI Agents (kept for demonstration — not executed via Runner.run)
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
# Main — direct execution (bypasses LLM via Runner.run)
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — OpenAI Agents SDK")
    print("=" * 60)

    print("Relay agents ready.\n")

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

    # Phase 1 — triage (direct execution)
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
                CHANNEL, f"[Front Desk] {name}'s issue ({cid}) escalated to specialist."
            )
            print(f"[{ts}] Front Desk — escalated {name} → specialist ({cid})")
    print()

    # Phase 2 — specialist (direct execution)
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

    # Phase 3 — follow-up (direct execution)
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
