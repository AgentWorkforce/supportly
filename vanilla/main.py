"""
Customer Service Escalation App — Pure Python (No Framework)

Two agents communicate via Relay:
  - front-desk: handles simple queries, escalates complex ones via DM
  - specialist: responds to escalated issues via DM
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, "/tmp/relay-565/packages/sdk-py/src")

from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message

config = RelayConfig(
    workspace=os.environ.get("RELAY_WORKSPACE", "customer-service-vanilla"),
    api_key=os.environ.get("RELAY_API_KEY", "demo-key"),
    base_url=os.environ.get("RELAY_BASE_URL", "https://api.relaycast.dev"),
)

SIMPLE_RESPONSES = {
    "hours": "We are open Monday-Friday, 9 AM to 6 PM EST.",
    "return": "You can return items within 30 days with a receipt. Visit our Returns page.",
    "shipping": "Standard shipping takes 5-7 business days. Express is 1-2 days.",
    "contact": "You can reach us at support@example.com or call 1-800-555-0199.",
}

COMPLEX_KEYWORDS = ["billing dispute", "account compromised", "legal", "data breach", "refund denied"]


def classify_query(query: str) -> tuple[bool, str | None]:
    """Return (is_simple, response_or_None)."""
    lower = query.lower()
    for keyword, response in SIMPLE_RESPONSES.items():
        if keyword in lower:
            return True, response
    for keyword in COMPLEX_KEYWORDS:
        if keyword in lower:
            return False, None
    return True, f"Thank you for your question. A general answer: please check our FAQ at help.example.com."


class FrontDeskAgent:
    def __init__(self, relay: Relay):
        self.relay = relay
        self.pending_escalations: dict[str, str] = {}

    async def handle_customer(self, customer_name: str, query: str) -> str:
        print(f"\n{'='*60}")
        print(f"[Front Desk] Customer '{customer_name}' asks: {query}")

        is_simple, response = classify_query(query)

        if is_simple:
            print(f"[Front Desk] Simple query — responding directly.")
            await self.relay.post("general", f"[{customer_name}] Q: {query} | A: {response}")
            return response

        print(f"[Front Desk] Complex query detected — escalating to specialist.")
        escalation_msg = (
            f"ESCALATION from {customer_name}: {query}\n"
            f"Please investigate and provide a detailed response."
        )
        await self.relay.send("specialist", escalation_msg)
        await self.relay.post(
            "general",
            f"[{customer_name}] Query escalated to specialist: {query[:80]}..."
        )
        self.pending_escalations[customer_name] = query
        return "ESCALATED"

    async def check_specialist_responses(self) -> list[tuple[str, str]]:
        messages = await self.relay.inbox()
        responses = []
        for msg in messages:
            if msg.sender == "specialist":
                print(f"[Front Desk] Received specialist response: {msg.text[:100]}...")
                responses.append((msg.sender, msg.text))
        return responses


class SpecialistAgent:
    def __init__(self, relay: Relay):
        self.relay = relay

    def generate_response(self, escalation_text: str) -> str:
        lower = escalation_text.lower()
        if "billing dispute" in lower:
            return (
                "SPECIALIST RESPONSE: I've reviewed the billing dispute. "
                "The charge appears to be from a subscription renewal. "
                "I've initiated a refund of $49.99 and added a 20% discount code "
                "for their next purchase: LOYAL20. Case #BD-2024-0847."
            )
        elif "account compromised" in lower:
            return (
                "SPECIALIST RESPONSE: Security incident flagged. "
                "I've locked the account, forced a password reset, "
                "revoked all active sessions, and enabled 2FA. "
                "The customer should check their email for recovery steps. "
                "Case #SEC-2024-0312."
            )
        elif "refund denied" in lower:
            return (
                "SPECIALIST RESPONSE: Reviewed the refund denial. "
                "The item was outside the return window but given the customer's "
                "loyalty (5+ years), I'm approving a store credit of full value. "
                "Case #RF-2024-0156."
            )
        else:
            return (
                "SPECIALIST RESPONSE: I've investigated this issue thoroughly. "
                "It requires further review by the legal team. "
                "I've filed an internal ticket and the customer will be "
                "contacted within 24 hours. Case #GEN-2024-0999."
            )

    async def process_inbox(self) -> int:
        messages = await self.relay.inbox()
        processed = 0
        for msg in messages:
            if msg.sender == "front-desk" and "ESCALATION" in msg.text:
                print(f"\n[Specialist] Received escalation: {msg.text[:80]}...")
                response = self.generate_response(msg.text)
                print(f"[Specialist] Sending response: {response[:80]}...")
                await self.relay.send("front-desk", response)
                await self.relay.post("general", f"[Specialist] Resolved escalation: {response[:100]}...")
                processed += 1
        return processed


async def run_demo():
    print("=" * 60)
    print("Customer Service Escalation App — Vanilla Python")
    print("=" * 60)

    front_relay = Relay("front-desk", config)
    specialist_relay = Relay("specialist", config)

    async with front_relay, specialist_relay:
        front_desk = FrontDeskAgent(front_relay)
        specialist = SpecialistAgent(specialist_relay)

        customer_queries = [
            ("Alice", "What are your business hours?"),
            ("Bob", "I have a billing dispute — I was charged twice for order #12345"),
            ("Carol", "My account was compromised and someone made unauthorized purchases"),
        ]

        print("\n--- Processing Customer Queries ---")
        for customer_name, query in customer_queries:
            result = await front_desk.handle_customer(customer_name, query)
            if result != "ESCALATED":
                print(f"[Front Desk] Direct response to {customer_name}: {result}")

        await asyncio.sleep(1)

        print("\n--- Specialist Processing Escalations ---")
        processed = await specialist.process_inbox()
        print(f"[Specialist] Processed {processed} escalation(s)")

        await asyncio.sleep(1)

        print("\n--- Front Desk Checking Specialist Responses ---")
        responses = await front_desk.check_specialist_responses()
        for sender, text in responses:
            print(f"[Front Desk] Got from {sender}: {text}")

        print("\n--- Final Summary ---")
        print(f"Total queries: {len(customer_queries)}")
        print(f"Direct answers: {len(customer_queries) - processed}")
        print(f"Escalated & resolved: {processed}")
        print("=" * 60)
        print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(run_demo())
