"""
Customer Service Escalation — LangGraph + Relay SDK

A StateGraph routes customer queries through triage → specialist → follow-up
nodes, using Relay DMs for inter-agent communication.
"""

import asyncio
import os
import random
import string
from datetime import datetime
from typing import TypedDict

from langgraph.graph import StateGraph, END

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
# State
# ---------------------------------------------------------------------------

class CustomerQuery(TypedDict):
    name: str
    query: str
    category: str
    case_id: str
    resolution: str


class ServiceState(TypedDict):
    customers: list[CustomerQuery]
    escalated_ids: list[str]
    resolutions: list[str]
    phase: str


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
# Graph Nodes
# ---------------------------------------------------------------------------

async def triage_node(state: ServiceState) -> ServiceState:
    """Classify and handle each customer query."""
    ts = datetime.now().strftime("%H:%M:%S")
    escalated_ids = []
    updated_customers = []

    for cust in state["customers"]:
        name, query = cust["name"], cust["query"]
        category = classify(query)
        cid = ""

        if category == "simple":
            answer = simple_answer(query)
            await front_relay.post(
                CHANNEL, f"[Front Desk] {name} asked: {query}\nAnswer: {answer}"
            )
            print(f"[{ts}] Triage — answered {name} directly.")
        else:
            cid = make_case_id()
            escalation = (
                f"ESCALATION {cid}\nCustomer: {name}\n"
                f"Issue: {query}\nPriority: HIGH"
            )
            await front_relay.send("specialist", escalation)
            await front_relay.post(
                CHANNEL, f"[Front Desk] {name}'s issue ({cid}) escalated."
            )
            escalated_ids.append(cid)
            print(f"[{ts}] Triage — escalated {name} → specialist ({cid}).")

        updated_customers.append({
            **cust,
            "category": category,
            "case_id": cid,
        })

    return {
        **state,
        "customers": updated_customers,
        "escalated_ids": escalated_ids,
        "phase": "specialist",
    }


async def specialist_node(state: ServiceState) -> ServiceState:
    """Process escalated issues from Relay inbox."""
    ts = datetime.now().strftime("%H:%M:%S")
    await asyncio.sleep(0.5)
    messages = await spec_relay.inbox()
    resolutions = []

    for msg in messages:
        if "ESCALATION" not in msg.text:
            continue
        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        customer_line = next((l for l in lines if l.startswith("Customer:")), "")
        issue_line = next((l for l in lines if l.startswith("Issue:")), "")
        customer = customer_line.replace("Customer:", "").strip()
        issue = issue_line.replace("Issue:", "").strip()

        resolution = generate_resolution(cid, customer, issue)
        await spec_relay.send("front-desk", f"RESOLUTION {cid}\n{resolution}")
        await spec_relay.post(CHANNEL, f"[Specialist] Resolved {cid} for {customer}.")
        resolutions.append(resolution)
        print(f"[{ts}] Specialist — resolved {cid} for {customer}.")

    return {**state, "resolutions": resolutions, "phase": "followup"}


async def followup_node(state: ServiceState) -> ServiceState:
    """Front desk reads resolutions and posts follow-ups."""
    ts = datetime.now().strftime("%H:%M:%S")
    await asyncio.sleep(0.5)
    messages = await front_relay.inbox()

    for msg in messages:
        if "RESOLUTION" not in msg.text:
            continue
        lines = msg.text.strip().splitlines()
        cid = lines[0].split()[-1] if lines else "UNKNOWN"
        detail = "\n".join(lines[1:]).strip()
        await front_relay.post(CHANNEL, f"[Front Desk] Resolution received:\n{detail}")
        print(f"[{ts}] Follow-up — posted resolution for {cid}.")

    return {**state, "phase": "done"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_triage(state: ServiceState) -> str:
    if state.get("escalated_ids"):
        return "specialist"
    return "followup"


def route_after_specialist(state: ServiceState) -> str:
    return "followup"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(ServiceState)

    graph.add_node("triage", triage_node)
    graph.add_node("specialist", specialist_node)
    graph.add_node("followup", followup_node)

    graph.set_entry_point("triage")
    graph.add_conditional_edges("triage", route_after_triage)
    graph.add_edge("specialist", "followup")
    graph.add_edge("followup", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"name": "Alice", "query": "What are your business hours?",
     "category": "", "case_id": "", "resolution": ""},
    {"name": "Bob", "query": "I have a billing dispute — I was charged twice for order #1042.",
     "category": "", "case_id": "", "resolution": ""},
    {"name": "Carol", "query": "Security incident: my account appears compromised, unauthorized purchases.",
     "category": "", "case_id": "", "resolution": ""},
]


async def main() -> None:
    print("=" * 60)
    print("Customer Service Escalation — LangGraph")
    print("=" * 60)

    await front_relay.connect()
    await spec_relay.connect()
    print("Agents connected.\n")

    app = build_graph()

    initial_state: ServiceState = {
        "customers": CUSTOMERS,
        "escalated_ids": [],
        "resolutions": [],
        "phase": "triage",
    }

    final_state = await app.ainvoke(initial_state)
    print(f"\nFinal phase: {final_state['phase']}")
    print(f"Resolutions: {len(final_state['resolutions'])}")

    await front_relay.close()
    await spec_relay.close()
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
