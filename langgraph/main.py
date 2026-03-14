"""
Customer Service Escalation App — LangGraph

Two LangGraph agent nodes communicate via Relay:
  - front_desk_node: triages queries, DMs specialist for complex ones
  - specialist_node: processes escalations, responds via DM

Uses a StateGraph with conditional routing based on query complexity.
"""

import asyncio
import os
import sys
from typing import Annotated, TypedDict

sys.path.insert(0, "/tmp/relay-565/packages/sdk-py/src")

from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

config = RelayConfig(
    workspace=os.environ.get("RELAY_WORKSPACE", "customer-service-langgraph"),
    api_key=os.environ.get("RELAY_API_KEY", "demo-key"),
    base_url=os.environ.get("RELAY_BASE_URL", "https://api.relaycast.dev"),
)

front_relay = Relay("front-desk", config)
specialist_relay = Relay("specialist", config)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

SIMPLE_KEYWORDS = ["hours", "shipping", "return", "contact", "track", "password reset"]
COMPLEX_KEYWORDS = ["billing dispute", "account compromised", "legal", "data breach",
                     "refund denied", "unauthorized", "fraud"]

SIMPLE_RESPONSES = {
    "hours": "We are open Monday-Friday, 9 AM to 6 PM EST.",
    "shipping": "Standard shipping takes 5-7 business days. Express is 1-2 days.",
    "return": "You can return items within 30 days with a receipt.",
    "contact": "Email support@example.com or call 1-800-555-0199.",
    "track": "Use your tracking number at track.example.com.",
    "password reset": "Visit account.example.com/reset to reset your password.",
}


# --- State Definition ---

class CustomerState(TypedDict):
    customer_name: str
    query: str
    classification: str  # "simple" or "complex"
    response: str
    escalation_sent: bool
    specialist_response: str
    messages: list[BaseMessage]


# --- Graph Nodes ---

async def classify_node(state: CustomerState) -> CustomerState:
    """Classify the customer query as simple or complex."""
    query_lower = state["query"].lower()

    for keyword in COMPLEX_KEYWORDS:
        if keyword in query_lower:
            state["classification"] = "complex"
            state["messages"].append(
                AIMessage(content=f"Classified as COMPLEX: matched '{keyword}'")
            )
            return state

    state["classification"] = "simple"
    state["messages"].append(AIMessage(content="Classified as SIMPLE query."))
    return state


async def front_desk_simple_node(state: CustomerState) -> CustomerState:
    """Handle simple queries directly."""
    query_lower = state["query"].lower()
    response = None

    for keyword, resp in SIMPLE_RESPONSES.items():
        if keyword in query_lower:
            response = resp
            break

    if not response:
        prompt = f"Customer '{state['customer_name']}' asks: '{state['query']}'. Provide a brief helpful answer."
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        response = result.content

    state["response"] = response
    state["escalation_sent"] = False

    print(f"[Front Desk] Direct answer for {state['customer_name']}: {response}")

    await front_relay.post(
        "general",
        f"[{state['customer_name']}] Q: {state['query']} | A: {response}"
    )

    state["messages"].append(AIMessage(content=f"Direct response: {response}"))
    return state


async def front_desk_escalate_node(state: CustomerState) -> CustomerState:
    """Escalate complex queries to specialist via DM."""
    escalation_msg = (
        f"ESCALATION from {state['customer_name']}: {state['query']}\n"
        f"Please investigate and provide a detailed response."
    )

    print(f"[Front Desk] Escalating {state['customer_name']}'s query to specialist.")

    await front_relay.send("specialist", escalation_msg)
    await front_relay.post(
        "general",
        f"[{state['customer_name']}] Query escalated to specialist: {state['query'][:80]}..."
    )

    state["escalation_sent"] = True
    state["response"] = "Your issue has been escalated to a specialist. You'll hear back shortly."
    state["messages"].append(AIMessage(content="Escalated to specialist via Relay DM."))
    return state


async def specialist_node(state: CustomerState) -> CustomerState:
    """Specialist processes the escalation and responds."""
    messages = await specialist_relay.inbox()
    escalation_messages = [m for m in messages if m.sender == "front-desk" and "ESCALATION" in m.text]

    if not escalation_messages:
        state["specialist_response"] = "No escalations found."
        return state

    for msg in escalation_messages:
        print(f"[Specialist] Processing escalation: {msg.text[:80]}...")

        prompt = (
            f"You are a senior customer service specialist. "
            f"Investigate this escalation and provide a detailed resolution with a case number:\n\n"
            f"{msg.text}"
        )
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        resolution = result.content

        await specialist_relay.send("front-desk", f"SPECIALIST RESPONSE: {resolution}")
        await specialist_relay.post("general", f"[Specialist] Resolved: {resolution[:100]}...")

        state["specialist_response"] = resolution
        state["messages"].append(AIMessage(content=f"Specialist resolution: {resolution}"))
        print(f"[Specialist] Sent resolution: {resolution[:80]}...")

    return state


async def followup_node(state: CustomerState) -> CustomerState:
    """Front desk checks for specialist responses."""
    responses = await front_relay.inbox()
    specialist_msgs = [m for m in responses if m.sender == "specialist"]

    if specialist_msgs:
        for msg in specialist_msgs:
            print(f"[Front Desk] Got specialist response: {msg.text[:80]}...")
            await front_relay.post(
                "general",
                f"[{state['customer_name']}] Issue resolved: {msg.text[:100]}..."
            )
        state["messages"].append(AIMessage(content="Specialist response received and forwarded."))
    else:
        state["messages"].append(AIMessage(content="No specialist response yet."))

    return state


# --- Routing ---

def route_by_classification(state: CustomerState) -> str:
    if state["classification"] == "complex":
        return "escalate"
    return "simple"


# --- Build the Graph ---

def build_triage_graph() -> StateGraph:
    graph = StateGraph(CustomerState)

    graph.add_node("classify", classify_node)
    graph.add_node("simple", front_desk_simple_node)
    graph.add_node("escalate", front_desk_escalate_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", route_by_classification, {
        "simple": "simple",
        "escalate": "escalate",
    })
    graph.add_edge("simple", END)
    graph.add_edge("escalate", END)

    return graph.compile()


def build_specialist_graph() -> StateGraph:
    graph = StateGraph(CustomerState)

    graph.add_node("process", specialist_node)

    graph.set_entry_point("process")
    graph.add_edge("process", END)

    return graph.compile()


def build_followup_graph() -> StateGraph:
    graph = StateGraph(CustomerState)

    graph.add_node("followup", followup_node)

    graph.set_entry_point("followup")
    graph.add_edge("followup", END)

    return graph.compile()


async def run_demo():
    print("=" * 60)
    print("Customer Service Escalation App — LangGraph")
    print("=" * 60)

    async with front_relay, specialist_relay:

        customer_queries = [
            ("Alice", "What are your business hours?"),
            ("Bob", "I have a billing dispute — I was charged twice for order #12345"),
            ("Carol", "My account was compromised and someone made unauthorized purchases"),
        ]

        triage_graph = build_triage_graph()
        specialist_graph = build_specialist_graph()
        followup_graph = build_followup_graph()

        # Phase 1: Triage all queries
        print("\n--- Phase 1: Front Desk Triage ---")
        escalated_states = []

        for customer_name, query in customer_queries:
            print(f"\n[Triaging] {customer_name}: {query}")
            initial_state: CustomerState = {
                "customer_name": customer_name,
                "query": query,
                "classification": "",
                "response": "",
                "escalation_sent": False,
                "specialist_response": "",
                "messages": [HumanMessage(content=query)],
            }
            result = await triage_graph.ainvoke(initial_state)
            print(f"[Result] Classification: {result['classification']}, Response: {result['response'][:80]}...")
            if result["escalation_sent"]:
                escalated_states.append(result)

        await asyncio.sleep(2)

        # Phase 2: Specialist processes
        print("\n--- Phase 2: Specialist Processing ---")
        for state in escalated_states:
            result = await specialist_graph.ainvoke(state)
            print(f"[Specialist] {result.get('specialist_response', 'No response')[:80]}...")

        await asyncio.sleep(2)

        # Phase 3: Follow-up
        print("\n--- Phase 3: Front Desk Follow-up ---")
        for state in escalated_states:
            result = await followup_graph.ainvoke(state)

        print("\n--- Summary ---")
        print(f"Total queries: {len(customer_queries)}")
        print(f"Escalated: {len(escalated_states)}")
        print("=" * 60)
        print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
