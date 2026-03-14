/**
 * Customer Service Escalation — Pi SDK + Relay Communicate
 *
 * Demonstrates the Pi coding agent + Relay adapter pattern:
 * - In production, use onRelay() from @agent-relay/sdk to inject
 *   relay_send, relay_inbox, relay_post, relay_agents as Pi custom tools
 * - Incoming Relay messages route via session.steer() (streaming) or followUp() (idle)
 *
 * Usage with real Pi SDK:
 *   import { createAgentSession, AuthStorage, ModelRegistry, SessionManager } from "@mariozechner/pi-coding-agent";
 *   import { onPiRelay } from "@agent-relay/sdk/communicate/adapters";
 *
 *   const config = onPiRelay("front-desk", { sessionManager: SessionManager.inMemory() });
 *   const { session } = await createAgentSession(config);
 *   await session.prompt("Triage this customer query: ...");
 */

const RUN_ID = Math.random().toString(36).slice(2, 8);

// Simulated relay message queues (in production, backed by Relaycast WebSocket)
const messageQueues: Record<string, Array<{ from: string; text: string }>> = {};

function relaySend(from: string, to: string, text: string) {
  if (!messageQueues[to]) messageQueues[to] = [];
  messageQueues[to].push({ from, text });
}

function relayInbox(agent: string): Array<{ from: string; text: string }> {
  const msgs = messageQueues[agent] ?? [];
  messageQueues[agent] = [];
  return msgs;
}

// ─── Customer Data ──────────────────────────────────────────
const CUSTOMERS = [
  { name: "Alice", query: "What are your business hours?" },
  { name: "Bob", query: "I have a billing dispute — I was charged twice for order #1042." },
  { name: "Carol", query: "Security incident: my account appears compromised, unauthorized purchases." },
];

// ─── Main ───────────────────────────────────────────────────
async function main() {
  console.log("=".repeat(60));
  console.log("Customer Service Escalation — Pi SDK + Relay");
  console.log("=".repeat(60));

  const frontDesk = `front-desk-${RUN_ID}`;
  const specialist = `specialist-${RUN_ID}`;

  // Phase 1: Triage
  console.log("\n--- Phase 1: Triage ---");
  const escalated: string[] = [];

  for (const customer of CUSTOMERS) {
    const isComplex = /billing|security|compromised/i.test(customer.query);

    if (isComplex) {
      const caseId = `CASE-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
      escalated.push(caseId);
      // Pi agent would call relay_send tool here
      relaySend(frontDesk, specialist, `ESCALATION ${caseId}\nCustomer: ${customer.name}\nIssue: ${customer.query}`);
      console.log(`  [Front Desk] ${customer.name}: ${customer.query.slice(0, 60)}`);
      console.log(`  [Front Desk] → escalated to specialist (${caseId})`);
    } else {
      console.log(`  [Front Desk] ${customer.name}: ${customer.query}`);
      console.log(`  [Front Desk] → answered directly.`);
    }
  }

  console.log(`\nEscalated: [${escalated.join(", ")}]\n`);

  // Phase 2: Specialist processes (would be a separate Pi session with onRelay)
  console.log("--- Phase 2: Specialist Processing ---");
  const inbox = relayInbox(specialist);
  for (const msg of inbox) {
    const caseId = msg.text.match(/ESCALATION (CASE-\w+)/)?.[1] ?? "UNKNOWN";
    console.log(`  [Specialist] Processing ${caseId}`);
    // Pi agent would call relay_send back to front-desk
    relaySend(specialist, frontDesk, `RESOLUTION ${caseId}\nStatus: Resolved\nAction: Credited account, flagged for review.`);
    console.log(`  [Specialist] → resolved ${caseId}`);
  }

  // Phase 3: Follow-up
  console.log("\n--- Phase 3: Follow-up ---");
  const resolutions = relayInbox(frontDesk);
  for (const msg of resolutions) {
    const caseId = msg.text.match(/RESOLUTION (CASE-\w+)/)?.[1] ?? "UNKNOWN";
    console.log(`  [Front Desk] Received resolution for ${caseId}`);
  }

  console.log("\n" + "=".repeat(60));
  console.log("Done.");
}

main().catch(console.error);
