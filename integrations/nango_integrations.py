"""
Nango Integration Stubs for Customer Service POC

Defines integration configs and helper functions for 18 SaaS services
commonly used in customer service workflows. Each integration specifies
its auth mode, description, and typical use cases an agent would perform.

Usage:
    from integrations import NangoClient, get_available_integrations

    client = NangoClient(base_url="https://api.nango.dev", secret_key="...")
    await client.connect("zendesk")
    tickets = await client.fetch("zendesk", "/api/v2/tickets.json")
    await client.push("zendesk", "/api/v2/tickets.json", {"ticket": {...}})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthMode(str, Enum):
    OAUTH2 = "OAUTH2"
    BASIC = "BASIC"
    API_KEY = "API_KEY"


@dataclass
class NangoIntegration:
    """Configuration for a single Nango-managed SaaS integration."""

    name: str
    provider_id: str
    auth_mode: AuthMode
    description: str
    use_cases: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Integration definitions
# ---------------------------------------------------------------------------

INTEGRATIONS: list[NangoIntegration] = [
    NangoIntegration(
        name="Zendesk",
        provider_id="zendesk",
        auth_mode=AuthMode.OAUTH2,
        description="Customer support ticketing and profile management",
        use_cases=[
            "Fetch open tickets for a customer",
            "Create new support tickets from agent conversations",
            "Sync customer profiles and contact details",
        ],
    ),
    NangoIntegration(
        name="Intercom",
        provider_id="intercom",
        auth_mode=AuthMode.OAUTH2,
        description="Live chat, user segments, and conversation history",
        use_cases=[
            "Retrieve live chat transcripts",
            "Query user segments for targeting",
            "Pull full conversation history for context",
        ],
    ),
    NangoIntegration(
        name="Freshdesk",
        provider_id="freshdesk",
        auth_mode=AuthMode.BASIC,
        description="Ticket management and contact synchronization",
        use_cases=[
            "List and filter support tickets by status",
            "Create and update ticket fields",
            "Sync contacts between CRM and helpdesk",
        ],
    ),
    NangoIntegration(
        name="HubSpot",
        provider_id="hubspot",
        auth_mode=AuthMode.OAUTH2,
        description="CRM contacts, deals, and ticket pipeline",
        use_cases=[
            "Look up CRM contact by email",
            "Fetch deal stage and history",
            "Create tickets in the support pipeline",
        ],
    ),
    NangoIntegration(
        name="Salesforce",
        provider_id="salesforce",
        auth_mode=AuthMode.OAUTH2,
        description="Cases, contacts, and knowledge articles",
        use_cases=[
            "Query open cases for a contact",
            "Search knowledge articles for resolution steps",
            "Create or update case records",
        ],
    ),
    NangoIntegration(
        name="Slack",
        provider_id="slack",
        auth_mode=AuthMode.OAUTH2,
        description="Notifications, escalation alerts, and channel updates",
        use_cases=[
            "Post escalation alerts to support channels",
            "Send resolution notifications to agents",
            "Update channel topics with queue status",
        ],
    ),
    NangoIntegration(
        name="Discord",
        provider_id="discord",
        auth_mode=AuthMode.OAUTH2,
        description="Community support channels",
        use_cases=[
            "Post updates to community support channels",
            "Monitor channels for customer questions",
            "Send direct messages for private follow-ups",
        ],
    ),
    NangoIntegration(
        name="Help Scout",
        provider_id="helpscout",
        auth_mode=AuthMode.BASIC,
        description="Mailbox conversations and customer profiles",
        use_cases=[
            "Fetch mailbox conversations by status",
            "Look up customer profile and history",
            "Create new conversations from inbound requests",
        ],
    ),
    NangoIntegration(
        name="Jira",
        provider_id="jira",
        auth_mode=AuthMode.OAUTH2,
        description="Bug tickets created from customer reports",
        use_cases=[
            "Create bug tickets from customer-reported issues",
            "Link support tickets to Jira issues",
            "Check issue status for customer follow-up",
        ],
    ),
    NangoIntegration(
        name="Linear",
        provider_id="linear",
        auth_mode=AuthMode.OAUTH2,
        description="Issue tracking for escalated bugs",
        use_cases=[
            "File engineering issues for escalated bugs",
            "Track issue progress for customer updates",
            "Query team workload before assigning",
        ],
    ),
    NangoIntegration(
        name="Twilio",
        provider_id="twilio",
        auth_mode=AuthMode.BASIC,
        description="SMS notifications and call routing",
        use_cases=[
            "Send SMS status updates to customers",
            "Initiate outbound calls for urgent issues",
            "Look up call logs for a customer number",
        ],
    ),
    NangoIntegration(
        name="SendGrid",
        provider_id="sendgrid",
        auth_mode=AuthMode.API_KEY,
        description="Email notifications and templates",
        use_cases=[
            "Send transactional emails for ticket updates",
            "Trigger templated resolution emails",
            "Check email delivery status",
        ],
    ),
    NangoIntegration(
        name="Microsoft Teams",
        provider_id="microsoft-teams",
        auth_mode=AuthMode.OAUTH2,
        description="Internal escalation channels",
        use_cases=[
            "Post to internal escalation channels",
            "Notify on-call engineers via Teams",
            "Create group chats for incident response",
        ],
    ),
    NangoIntegration(
        name="Shopify",
        provider_id="shopify",
        auth_mode=AuthMode.OAUTH2,
        description="Order lookup and customer purchase history",
        use_cases=[
            "Look up order status by order number",
            "Fetch customer purchase history",
            "Check refund and return eligibility",
        ],
    ),
    NangoIntegration(
        name="Stripe",
        provider_id="stripe",
        auth_mode=AuthMode.OAUTH2,
        description="Payment and refund lookup, billing disputes",
        use_cases=[
            "Look up payment status by charge ID",
            "Initiate refunds for approved cases",
            "Retrieve billing dispute details",
        ],
    ),
    NangoIntegration(
        name="Notion",
        provider_id="notion",
        auth_mode=AuthMode.OAUTH2,
        description="Knowledge base and runbooks",
        use_cases=[
            "Search knowledge base for troubleshooting steps",
            "Fetch runbook pages for known issues",
            "Update documentation with new resolutions",
        ],
    ),
    NangoIntegration(
        name="WhatsApp Business",
        provider_id="whatsapp-business",
        auth_mode=AuthMode.API_KEY,
        description="Customer messaging channel",
        use_cases=[
            "Send templated messages to customers",
            "Receive and respond to inbound messages",
            "Share media attachments (receipts, screenshots)",
        ],
    ),
    NangoIntegration(
        name="Front",
        provider_id="front",
        auth_mode=AuthMode.OAUTH2,
        description="Shared inbox and conversation routing",
        use_cases=[
            "Fetch conversations from shared inboxes",
            "Route conversations to the right team",
            "Add internal comments for agent handoff",
        ],
    ),
]


def get_available_integrations() -> list[NangoIntegration]:
    """Return all configured Nango integration definitions."""
    return list(INTEGRATIONS)


def get_integration(provider_id: str) -> NangoIntegration | None:
    """Look up a single integration by provider ID."""
    for integration in INTEGRATIONS:
        if integration.provider_id == provider_id:
            return integration
    return None


# ---------------------------------------------------------------------------
# Stub client
# ---------------------------------------------------------------------------


class NangoClient:
    """Stub Nango client for the customer-service POC.

    In production this would call the Nango Proxy API to execute
    authenticated requests against each provider's API.

    Example API calls an agent might make through this client:

        # Zendesk — list recent tickets
        await client.fetch("zendesk", "/api/v2/tickets/recent.json")

        # Shopify — look up an order
        await client.fetch("shopify", "/admin/api/2024-01/orders/{id}.json")

        # Stripe — retrieve a charge
        await client.fetch("stripe", "/v1/charges/{charge_id}")

        # Salesforce — SOQL query for open cases
        await client.fetch("salesforce", "/services/data/v59.0/query",
                           params={"q": "SELECT Id,Subject FROM Case WHERE Status='Open'"})

        # Jira — create an issue
        await client.push("jira", "/rest/api/3/issue",
                          payload={"fields": {"project": {"key": "SUP"}, "summary": "..."}})

        # SendGrid — send a transactional email
        await client.push("sendgrid", "/v3/mail/send",
                          payload={"personalizations": [...], "from": {...}, "content": [...]})

        # Slack — post a message
        await client.push("slack", "/api/chat.postMessage",
                          payload={"channel": "C0123", "text": "Escalation alert: ..."})
    """

    def __init__(self, base_url: str = "https://api.nango.dev", secret_key: str = ""):
        self.base_url = base_url
        self.secret_key = secret_key
        self._connections: dict[str, bool] = {}

    async def connect(self, provider_id: str, connection_id: str = "default") -> dict[str, Any]:
        """Establish (or verify) an authenticated connection to a provider.

        Returns connection metadata on success.
        """
        integration = get_integration(provider_id)
        if integration is None:
            raise ValueError(f"Unknown provider: {provider_id}")
        self._connections[provider_id] = True
        return {
            "provider": provider_id,
            "connection_id": connection_id,
            "auth_mode": integration.auth_mode.value,
            "status": "connected",
        }

    async def fetch(
        self,
        provider_id: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Proxy a GET request through Nango to the provider's API.

        Returns the upstream JSON response.
        """
        self._ensure_connected(provider_id)
        return {
            "stub": True,
            "provider": provider_id,
            "endpoint": endpoint,
            "params": params or {},
            "data": [],
        }

    async def push(
        self,
        provider_id: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Proxy a POST/PUT request through Nango to the provider's API.

        Returns the upstream JSON response.
        """
        self._ensure_connected(provider_id)
        return {
            "stub": True,
            "provider": provider_id,
            "endpoint": endpoint,
            "payload": payload or {},
            "status": "accepted",
        }

    def _ensure_connected(self, provider_id: str) -> None:
        if provider_id not in self._connections:
            raise RuntimeError(
                f"Not connected to {provider_id}. Call connect() first."
            )
