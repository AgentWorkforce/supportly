"""
Context Loader — Bridges Nango integrations to agent context.

In demo mode: returns rich simulated data.
In production: fetches real data from Nango-connected services.

Each specialist agent calls get_context(agent_role, customer_id) to get
their relevant data. The data comes from different integrations:

  Billing Expert  → Stripe (charges, refunds) + QuickBooks (invoices)
  Security Expert → Auth0 (login logs) + Datadog (alerts)
  Tech Support    → GitHub Issues (bugs) + Jira (tickets)
  Front Desk      → Zendesk (ticket history) + HubSpot (customer profile)
"""
import os
import json
from datetime import datetime, timedelta

NANGO_SECRET = os.environ.get("NANGO_SECRET_KEY")
NANGO_URL = os.environ.get("NANGO_API_URL", "https://api.nango.dev")


def _demo_mode():
    """True if no Nango key configured — use simulated data."""
    return not NANGO_SECRET


async def get_context(agent_role: str, customer_id: str = "default", query: str = "") -> dict:
    """
    Get agent-specific context. Returns:
    {
        "context_text": str,      # formatted text for LLM system prompt
        "sources": list[str],     # which integrations provided data
        "is_live": bool,          # True if from real Nango integrations
    }
    """
    if _demo_mode():
        return _get_demo_context(agent_role, customer_id, query)
    else:
        return await _get_live_context(agent_role, customer_id, query)


def _get_demo_context(role: str, cid: str, query: str) -> dict:
    """Rich simulated context — shows what real data would look like."""
    
    if role == "billing":
        return {
            "context_text": f"""## Billing System Data (via Stripe + QuickBooks)

### Customer Profile
- Name: {cid}
- Account: PRO plan ($29/mo), active since Jan 2024
- Lifetime value: $847.50 across 47 orders
- VIP status: Yes (>$500 LTV)
- Payment method: Visa ending 4242

### Recent Orders (Stripe)
| Order | Date | Amount | Status |
|-------|------|--------|--------|
| #1042 | Mar 12 | $89.99 | ⚠️ CHARGED 2x (duplicate detected) |
| #1038 | Mar 10 | $149.99 | Shipped, tracking: 1Z999AA10123456784 |
| #1035 | Mar 8 | $24.99 | Refunded (customer request) |
| #1029 | Mar 1 | $199.99 | Delivered |

### Open Disputes (Stripe)
- Dispute #disp_1042a: $89.99, filed Mar 13, reason: "duplicate charge"
- Auto-detected: payment_intent pi_3O... was processed twice due to timeout

### Refund Authority
- You can issue refunds up to $500 without manager approval
- Customer has 1 previous refund (good standing)

### QuickBooks Invoice Status
- INV-2024-0342: $89.99, unpaid (matches duplicate charge)
- Credit memo ready to issue""",
            "sources": ["Stripe (charges, disputes)", "QuickBooks (invoices)"],
            "is_live": False,
        }
    
    elif role == "security":
        now = datetime.now()
        return {
            "context_text": f"""## Security Data (via Auth0 + Datadog)

### Account Security Status: 🔴 COMPROMISED
Last known good session: {(now - timedelta(days=1)).strftime('%b %d, %I:%M %p')} from Oslo, Norway

### Login History (Auth0)
| Time | IP | Location | Status |
|------|-----|----------|--------|
| {(now - timedelta(hours=2)).strftime('%b %d %I:%M %p')} | 185.23.xx.xx | Oslo, Norway | ✅ Normal |
| {(now - timedelta(hours=33)).strftime('%b %d %I:%M %p')} | 91.108.xx.xx | St Petersburg, Russia | 🔴 Suspicious |
| {(now - timedelta(hours=34)).strftime('%b %d %I:%M %p')} | 91.108.xx.xx | St Petersburg, Russia | 🔴 3 purchases made |
| {(now - timedelta(days=3)).strftime('%b %d %I:%M %p')} | 185.23.xx.xx | Oslo, Norway | ✅ Normal |

### Unauthorized Transactions (Datadog Alert)
- Alert #SEC-4821: 3 purchases from suspicious IP
  - $299.99 — Electronics (Mar 13, 3:17 AM)
  - $199.99 — Gift cards (Mar 13, 3:22 AM)
  - $347.52 — Software license (Mar 13, 3:28 AM)
  - Total: $847.50

### Account Settings
- MFA: Email only (no authenticator — VULNERABILITY)
- Password last changed: 67 days ago
- Recovery email: verified

### Available Actions
- 🔒 Freeze account (immediate)
- 🔑 Force password reset
- 🚫 Revoke all active sessions
- 📋 Flag for fraud review team
- 💰 Initiate chargeback for unauthorized transactions""",
            "sources": ["Auth0 (login history, MFA)", "Datadog (security alerts)"],
            "is_live": False,
        }
    
    elif role == "technical":
        return {
            "context_text": f"""## Technical Data (via GitHub Issues + Jira)

### System Status (Datadog)
| Service | Status | Uptime |
|---------|--------|--------|
| API Gateway | 🟢 Operational | 99.97% |
| Auth Service | 🟢 Operational | 99.99% |
| File Upload Service | 🟡 Degraded | 98.2% |
| Payment Service | 🟢 Operational | 99.95% |
| CDN | 🟢 Operational | 99.99% |

### Known Issues (GitHub)
- **#4521** [HIGH] File uploads >10MB fail on Chrome 121+
  - Status: Fix in progress, PR #892 merged to staging
  - ETA: v3.2.1 release on Mar 18
  - Workaround: Use Firefox, or compress files below 10MB
  - Affected: ~340 users reported
  
- **#4498** [MEDIUM] Intermittent checkout timeout
  - Status: Monitoring, likely database connection pool
  - ETA: Investigating
  - Workaround: Retry after 30 seconds

### Customer's Environment (Jira)
- App version: 3.1.8 (latest stable)
- Browser: Chrome 121.0.6167.85
- OS: macOS 14.3
- Last crash: {datetime.now().strftime('%b %d, %I:%M %p')} — file upload timeout

### Similar Tickets (Jira)
- SUPPORT-1247: Same file upload crash (resolved: known issue #4521)
- SUPPORT-1239: Same issue, customer switched to Firefox (resolved)""",
            "sources": ["GitHub Issues (bugs, PRs)", "Jira (tickets)", "Datadog (status)"],
            "is_live": False,
        }
    
    elif role == "triage":
        return {
            "context_text": f"""## Customer Profile (via Zendesk + HubSpot)

### Contact
- Name: {cid}
- Email: {cid.lower().replace(' ','')}@example.com
- Plan: PRO ($29/mo)
- Customer since: Jan 2024
- Satisfaction score: 4.2/5.0

### Recent Tickets (Zendesk)
- #T-8821: "Slow loading times" — Resolved, 2 days ago
- #T-8790: "How to export data" — Resolved, 1 week ago
- No open tickets

### Sentiment (HubSpot)
- Overall: Positive
- NPS: 8/10 (Promoter)
- Last survey: 2 weeks ago""",
            "sources": ["Zendesk (tickets)", "HubSpot (CRM)"],
            "is_live": False,
        }
    
    return {"context_text": "No context available", "sources": [], "is_live": False}


async def _get_live_context(role: str, cid: str, query: str) -> dict:
    """
    Fetch real data from Nango-connected services.
    
    Production flow:
    1. Check which Nango connections are active for this workspace
    2. Fetch relevant data from each connected service
    3. Format into agent context
    
    When Relayfile is integrated:
    - Data is pre-synced to Relayfile mounts
    - Agent reads from /mnt/billing/stripe/charges.json etc
    - Much faster than API calls per request
    """
    import httpx
    
    headers = {"Authorization": f"Bearer {NANGO_SECRET}"}
    
    if role == "billing":
        sources = []
        context_parts = []
        
        # Try Stripe via Nango
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{NANGO_URL}/connection/stripe",
                                headers=headers)
                if r.status_code == 200:
                    # Fetch recent charges
                    charges = await c.get(
                        f"{NANGO_URL}/proxy/v1/charges?limit=10",
                        headers={**headers, "Connection-Id": "stripe", "Provider-Config-Key": "stripe"})
                    if charges.status_code == 200:
                        context_parts.append(f"### Stripe Charges\n```json\n{charges.text[:2000]}\n```")
                        sources.append("Stripe (live)")
        except Exception:
            pass
        
        # Fallback to demo if no live data
        if not context_parts:
            demo = _get_demo_context(role, cid, query)
            demo["sources"] = [s + " (demo fallback)" for s in demo["sources"]]
            return demo
        
        return {
            "context_text": "\n\n".join(context_parts),
            "sources": sources,
            "is_live": True,
        }
    
    # For other roles, fall back to demo for now
    demo = _get_demo_context(role, cid, query)
    demo["sources"] = [s + " (demo fallback)" for s in demo["sources"]]
    return demo
