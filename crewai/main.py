"""
Customer Service Escalation App — CrewAI Framework

Two CrewAI agents communicate via Relay:
  - front-desk: triages queries, uses relay_send tool to DM specialist
  - specialist: processes escalations, responds via relay_send
"""

import asyncio
import os
import sys

sys.path.insert(0, "/tmp/relay-565/packages/sdk-py/src")

from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

from crewai import Agent, Task, Crew, Process
from crewai.tools import tool

config = RelayConfig(
    workspace=os.environ.get("RELAY_WORKSPACE", "customer-service-crewai"),
    api_key=os.environ.get("RELAY_API_KEY", "demo-key"),
    base_url=os.environ.get("RELAY_BASE_URL", "https://api.relaycast.dev"),
)

front_relay = Relay("front-desk", config)
specialist_relay = Relay("specialist", config)


# --- Relay Tools for Front Desk ---

@tool
def front_send_to_specialist(message: str) -> str:
    """Send a DM to the specialist agent for complex issue escalation."""
    front_relay.send_sync("specialist", message)
    return "Escalation sent to specialist."

@tool
def front_post_to_channel(message: str) -> str:
    """Post a status update to the general channel."""
    front_relay.post_sync("general", message)
    return "Posted to general channel."

@tool
def front_check_inbox() -> str:
    """Check inbox for replies from the specialist."""
    messages = front_relay.inbox_sync()
    if not messages:
        return "No new messages."
    return "\n".join(f"From {m.sender}: {m.text}" for m in messages)


# --- Relay Tools for Specialist ---

@tool
def specialist_send_to_front(message: str) -> str:
    """Send a DM response back to the front-desk agent."""
    specialist_relay.send_sync("front-desk", message)
    return "Response sent to front-desk."

@tool
def specialist_post_to_channel(message: str) -> str:
    """Post a resolution update to the general channel."""
    specialist_relay.post_sync("general", message)
    return "Posted to general channel."

@tool
def specialist_check_inbox() -> str:
    """Check inbox for escalations from front-desk."""
    messages = specialist_relay.inbox_sync()
    if not messages:
        return "No new messages."
    return "\n".join(f"From {m.sender}: {m.text}" for m in messages)


# --- CrewAI Agent Definitions ---

front_desk_agent = Agent(
    role="Front Desk Customer Service Representative",
    goal=(
        "Handle simple customer queries directly. "
        "For complex issues (billing disputes, security, legal), "
        "escalate to the specialist via relay DM."
    ),
    backstory=(
        "You are the first point of contact for customers. "
        "You handle routine questions about hours, shipping, and returns. "
        "Complex issues must be escalated to the specialist agent."
    ),
    tools=[front_send_to_specialist, front_post_to_channel, front_check_inbox],
    verbose=True,
    allow_delegation=False,
)

specialist_agent = Agent(
    role="Customer Service Specialist",
    goal=(
        "Receive escalated issues from front-desk, investigate thoroughly, "
        "and send detailed resolutions back via relay DM."
    ),
    backstory=(
        "You are a senior specialist who handles complex customer issues "
        "including billing disputes, security incidents, and policy exceptions. "
        "You always provide case numbers and concrete next steps."
    ),
    tools=[specialist_send_to_front, specialist_post_to_channel, specialist_check_inbox],
    verbose=True,
    allow_delegation=False,
)


def build_triage_task(customer_name: str, query: str) -> Task:
    return Task(
        description=(
            f"Customer '{customer_name}' asks: '{query}'\n\n"
            "If this is a simple question (hours, shipping, returns, general), "
            "answer directly and post the answer to the general channel.\n"
            "If this is complex (billing dispute, account security, legal, refund denied), "
            "use the front_send_to_specialist tool to escalate, "
            "then post an escalation notice to the general channel."
        ),
        expected_output="A direct answer or confirmation that the query was escalated.",
        agent=front_desk_agent,
    )


def build_specialist_task() -> Task:
    return Task(
        description=(
            "Check your inbox for escalations from front-desk. "
            "For each escalation:\n"
            "1. Analyze the issue\n"
            "2. Generate a detailed resolution with a case number\n"
            "3. Send the resolution back to front-desk via DM\n"
            "4. Post a summary to the general channel"
        ),
        expected_output="Resolution details for all processed escalations.",
        agent=specialist_agent,
    )


def build_followup_task() -> Task:
    return Task(
        description=(
            "Check your inbox for specialist responses. "
            "Summarize any resolutions received and post a final update "
            "to the general channel confirming the issues are resolved."
        ),
        expected_output="Summary of all resolved escalations.",
        agent=front_desk_agent,
    )


async def run_demo():
    print("=" * 60)
    print("Customer Service Escalation App — CrewAI")
    print("=" * 60)

    async with front_relay, specialist_relay:

        customer_queries = [
            ("Alice", "What are your business hours?"),
            ("Bob", "I have a billing dispute — I was charged twice for order #12345"),
            ("Carol", "My account was compromised and someone made unauthorized purchases"),
        ]

        # Phase 1: Front desk triages all queries
        print("\n--- Phase 1: Front Desk Triage ---")
        triage_tasks = [build_triage_task(name, query) for name, query in customer_queries]

        triage_crew = Crew(
            agents=[front_desk_agent],
            tasks=triage_tasks,
            process=Process.sequential,
            verbose=True,
        )
        triage_result = triage_crew.kickoff()
        print(f"\nTriage result: {triage_result}")

        await asyncio.sleep(2)

        # Phase 2: Specialist processes escalations
        print("\n--- Phase 2: Specialist Processing ---")
        specialist_task = build_specialist_task()

        specialist_crew = Crew(
            agents=[specialist_agent],
            tasks=[specialist_task],
            process=Process.sequential,
            verbose=True,
        )
        specialist_result = specialist_crew.kickoff()
        print(f"\nSpecialist result: {specialist_result}")

        await asyncio.sleep(2)

        # Phase 3: Front desk checks for responses
        print("\n--- Phase 3: Front Desk Follow-up ---")
        followup_task = build_followup_task()

        followup_crew = Crew(
            agents=[front_desk_agent],
            tasks=[followup_task],
            process=Process.sequential,
            verbose=True,
        )
        followup_result = followup_crew.kickoff()
        print(f"\nFollow-up result: {followup_result}")

        print("\n" + "=" * 60)
        print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
