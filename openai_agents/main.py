"""
Customer Service Escalation App — OpenAI Agents SDK

Two OpenAI Agents communicate via Relay:
  - front-desk: triages queries, uses relay tools to DM specialist
  - specialist: processes escalations, responds via DM
"""

import asyncio
import os
import sys

sys.path.insert(0, "/tmp/relay-565/packages/sdk-py/src")

from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

from agents import Agent, Runner, function_tool, RunConfig

config = RelayConfig(
    workspace=os.environ.get("RELAY_WORKSPACE", "customer-service-openai"),
    api_key=os.environ.get("RELAY_API_KEY", "demo-key"),
    base_url=os.environ.get("RELAY_BASE_URL", "https://api.relaycast.dev"),
)

front_relay = Relay("front-desk", config)
specialist_relay = Relay("specialist", config)


# --- Relay Tools for Front Desk ---

@function_tool
async def front_send_to_specialist(message: str) -> str:
    """Send a DM to the specialist agent for complex issue escalation."""
    await front_relay.send("specialist", message)
    return "Escalation sent to specialist."

@function_tool
async def front_post_to_channel(message: str) -> str:
    """Post a status update to the general channel."""
    await front_relay.post("general", message)
    return "Posted to general channel."

@function_tool
async def front_check_inbox() -> str:
    """Check inbox for replies from the specialist."""
    messages = await front_relay.inbox()
    if not messages:
        return "No new messages."
    return "\n".join(f"From {m.sender}: {m.text}" for m in messages)


# --- Relay Tools for Specialist ---

@function_tool
async def specialist_send_to_front(message: str) -> str:
    """Send a DM response back to the front-desk agent."""
    await specialist_relay.send("front-desk", message)
    return "Response sent to front-desk."

@function_tool
async def specialist_post_to_channel(message: str) -> str:
    """Post a resolution update to the general channel."""
    await specialist_relay.post("general", message)
    return "Posted to general channel."

@function_tool
async def specialist_check_inbox() -> str:
    """Check inbox for escalations from front-desk."""
    messages = await specialist_relay.inbox()
    if not messages:
        return "No new messages."
    return "\n".join(f"From {m.sender}: {m.text}" for m in messages)


# --- OpenAI Agent Definitions ---

front_desk_agent = Agent(
    name="front-desk",
    instructions=(
        "You are a front desk customer service representative. "
        "For simple questions (hours, shipping, returns, general inquiries), "
        "answer directly and post to the general channel. "
        "For complex issues (billing disputes, account security, legal matters, "
        "refund denials), escalate to the specialist via DM using "
        "front_send_to_specialist, then post an escalation notice to the channel."
    ),
    tools=[front_send_to_specialist, front_post_to_channel, front_check_inbox],
)

specialist_agent = Agent(
    name="specialist",
    instructions=(
        "You are a senior customer service specialist. "
        "Check your inbox for escalations from front-desk. "
        "For each escalation, investigate the issue, create a detailed resolution "
        "with a case number (format: XX-2024-NNNN), and send it back to front-desk "
        "via DM using specialist_send_to_front. "
        "Also post a summary to the general channel."
    ),
    tools=[specialist_send_to_front, specialist_post_to_channel, specialist_check_inbox],
)


async def run_front_desk_triage(customer_name: str, query: str) -> str:
    """Run front desk agent to triage a single customer query."""
    prompt = (
        f"Customer '{customer_name}' asks: '{query}'\n\n"
        "Triage this query. If simple, answer directly and post to channel. "
        "If complex, escalate to specialist via DM and post escalation notice."
    )
    result = await Runner.run(front_desk_agent, prompt)
    return result.final_output


async def run_specialist_processing() -> str:
    """Run specialist agent to process all pending escalations."""
    prompt = (
        "Check your inbox for escalations from front-desk. "
        "Process each one: analyze the issue, create a resolution with a case number, "
        "send it back to front-desk via DM, and post a summary to the channel."
    )
    result = await Runner.run(specialist_agent, prompt)
    return result.final_output


async def run_front_desk_followup() -> str:
    """Run front desk to check specialist responses."""
    prompt = (
        "Check your inbox for responses from the specialist. "
        "Summarize all resolutions received and post a final update to the channel."
    )
    result = await Runner.run(front_desk_agent, prompt)
    return result.final_output


async def run_demo():
    print("=" * 60)
    print("Customer Service Escalation App — OpenAI Agents SDK")
    print("=" * 60)

    async with front_relay, specialist_relay:

        customer_queries = [
            ("Alice", "What are your business hours?"),
            ("Bob", "I have a billing dispute — I was charged twice for order #12345"),
            ("Carol", "My account was compromised and someone made unauthorized purchases"),
        ]

        # Phase 1: Front desk triages all queries
        print("\n--- Phase 1: Front Desk Triage ---")
        for customer_name, query in customer_queries:
            print(f"\n[Triaging] {customer_name}: {query}")
            result = await run_front_desk_triage(customer_name, query)
            print(f"[Result] {result}")

        await asyncio.sleep(2)

        # Phase 2: Specialist processes escalations
        print("\n--- Phase 2: Specialist Processing ---")
        result = await run_specialist_processing()
        print(f"[Specialist] {result}")

        await asyncio.sleep(2)

        # Phase 3: Front desk checks for responses
        print("\n--- Phase 3: Front Desk Follow-up ---")
        result = await run_front_desk_followup()
        print(f"[Follow-up] {result}")

        print("\n" + "=" * 60)
        print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
