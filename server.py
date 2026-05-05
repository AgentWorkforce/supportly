"""
Customer Service — Agent-to-Agent Communication Demo

5 independent agents, each with their own model, expertise, and context.
They self-organize via Agent Relay channels and DMs.

Architecture:
  #escalations channel — Front Desk posts here, specialists listen
  Each specialist only picks up tickets matching their expertise
  QA Monitor watches everything and scores resolutions

Agents:
  1. Front Desk     (free model)  — fast triage, routes to channel
  2. Billing Expert  (gpt-4o-mini) — has order history, refund authority
  3. Security Expert (gpt-4o-mini) — has access logs, can freeze accounts
  4. Tech Support    (free model)  — has bug database, knows the product
  5. QA Monitor      (free model)  — scores every resolution for quality
"""
import asyncio
import json
import os
import uuid
import string
import random
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from agent_relay.communicate import Relay
from agent_relay.communicate.types import RelayConfig, Message
from integrations.context_loader import get_context
from bootstrap import get_relay_config

app = FastAPI()

RUN_ID = uuid.uuid4().hex[:4]
CFG = get_relay_config()
CHANNEL = f"escalations-{RUN_ID}"

API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"

# Agent names
TRIAGE = f"triage-{RUN_ID}"
BILLING = f"billing-{RUN_ID}"
SECURITY = f"security-{RUN_ID}"
TECH = f"tech-{RUN_ID}"
QA = f"qa-{RUN_ID}"

# Models — the cost story
FREE_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
SMART_MODEL = "openai/gpt-4o-mini"

# Context is now loaded dynamically from integrations/context_loader.py
# In demo mode: rich simulated data. In production: real Nango integrations.

ws_clients: list[WebSocket] = []
ticket_queue: asyncio.Queue = asyncio.Queue()
agent_online_events: list[dict] = []
relays: dict[str, Relay] = {}

# Stats
stats = {"total":0,"simple":0,"escalated":0,"fd_tokens":0,"sp_tokens":0,"qa_tokens":0,
         "fd_cost":0.0,"sp_cost":0.0,"qa_cost":0.0,"mono_cost":0.0}


async def broadcast(event: dict):
    msg = json.dumps(event)
    for ws in ws_clients[:]:
        try: await ws.send_text(msg)
        except: ws_clients.remove(ws)


def case_id():
    return "CASE-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def llm(model, system, user, label="") -> dict:
    if not API_KEY:
        await asyncio.sleep(0.8)
        return {"content":f"[Simulated {label}]","model":model,"tokens":50,"cost":0,"ms":800}
    import httpx
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{BASE_URL}/chat/completions",
                headers={"Authorization":f"Bearer {API_KEY}"},
                json={"model":model,"messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ],"max_tokens":800})
            ms = int((time.time()-t0)*1000)
            if r.status_code != 200:
                return {"content":f"[Model {r.status_code}]","model":model,"tokens":0,"cost":0,"ms":ms}
            d = r.json()
            msg = d["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning") or ""
            if not content and msg.get("reasoning_details"):
                content = msg["reasoning_details"][0].get("text","")
            usage = d.get("usage",{})
            return {"content":content or "[No response]","model":d.get("model",model),
                    "tokens":usage.get("total_tokens",0),"cost":float(usage.get("cost",0)),"ms":ms}
    except Exception as e:
        return {"content":f"[Error: {e}]","model":model,"tokens":0,"cost":0,"ms":int((time.time()-t0)*1000)}


# ============================================================
# AGENT 1: FRONT DESK (Triage)
# ============================================================
async def agent_triage():
    r = Relay(TRIAGE, CFG); await r.__aenter__(); relays[TRIAGE] = r
    ev = {"type":"agent_online","agent":"Front Desk","name":TRIAGE,"model":FREE_MODEL,
          "role":"Triage & Routing","color":"emerald",
          "desc":"Fast free model. Classifies tickets and routes to the right specialist via #escalations channel."}
    agent_online_events.append(ev); await broadcast(ev)

    # Listen for specialist resolutions
    def on_msg(msg):
        if msg.sender == TRIAGE: return
        asyncio.create_task(_fd_got_resolution(msg))
    r.on_message(on_msg)

    while True:
        ticket = await ticket_queue.get()
        asyncio.create_task(_triage(ticket))


async def _triage(t):
    tid, cust, query = t["ticket_id"], t["customer"], t["query"]
    stats["total"] += 1

    await broadcast({"type":"thinking","agent":"Front Desk","color":"emerald","tid":tid,
                     "detail":f"Triaging {cust}'s request...","model":FREE_MODEL})

    res = await llm(FREE_MODEL,
        """You are a triage agent. Classify this ticket into exactly ONE category:
- "billing" (charges, refunds, payments, orders)
- "security" (account compromise, unauthorized access, password)
- "technical" (bugs, crashes, errors, features)
- "simple" (hours, FAQ, general questions)
Respond ONLY with JSON: {"category":"...", "urgency":"low|medium|high", "summary":"one line summary"}""",
        f"Customer {cust}: {query}", "Triage")

    stats["fd_tokens"] += res["tokens"]; stats["fd_cost"] += res["cost"]
    await broadcast({"type":"model_used","agent":"Front Desk","color":"emerald",
                     "model":res["model"],"tokens":res["tokens"],"cost":res["cost"],"ms":res["ms"]})

    # Parse category
    cat = "simple"
    for kw, c in [("bill","billing"),("charg","billing"),("refund","billing"),("order","billing"),
                   ("secur","security"),("hack","security"),("compromis","security"),("unauthoriz","security"),
                   ("crash","technical"),("bug","technical"),("error","technical"),("upload","technical")]:
        if kw in query.lower(): cat = c; break
    try:
        p = json.loads(res["content"])
        cat = p.get("category", cat)
        urgency = p.get("urgency", "medium")
        summary = p.get("summary", query[:80])
    except:
        urgency = "medium"; summary = query[:80]

    if cat == "simple":
        stats["simple"] += 1
        # Answer directly with free model
        ans = await llm(FREE_MODEL, "You are a helpful support agent. Answer concisely.",
                        f"Customer asks: {query}", "Direct answer")
        stats["fd_tokens"] += ans["tokens"]; stats["fd_cost"] += ans["cost"]
        # Mono cost: would use expensive model
        stats["mono_cost"] += 0.00015 * ((res["tokens"]+ans["tokens"])/1000)

        await broadcast({"type":"triage_result","tid":tid,"action":"direct","category":cat,
                         "response":ans["content"],"cost_saved":True})
        await broadcast({"type":"complete","tid":tid,"resolved_by":"Front Desk (direct — free model)",
                         "cost_note":"$0 — handled entirely by free model"})
        await _send_stats(); return

    stats["escalated"] += 1
    # Mono cost estimate
    stats["mono_cost"] += 0.00015 * (res["tokens"]/1000)

    await broadcast({"type":"triage_result","tid":tid,"action":"escalate","category":cat,
                     "urgency":urgency,"summary":summary})

    # DM the right specialist — Front Desk knows who to contact
    payload = json.dumps({"ticket_id":tid,"customer":cust,"query":query,
                          "category":cat,"urgency":urgency,"summary":summary})

    specialist_map = {"billing": (BILLING, "Billing Expert"),
                      "security": (SECURITY, "Security Expert"),
                      "technical": (TECH, "Tech Support")}
    target_name, target_label = specialist_map.get(cat, (BILLING, "Billing Expert"))

    await broadcast({"type":"relay_dm","from_agent":"Front Desk","from_name":TRIAGE,
                     "to_agent":target_label,"to_name":target_name,"tid":tid,
                     "preview":f"[{cat.upper()}] {urgency} — {summary}"})

    try:
        await relays[TRIAGE].send(target_name, payload)
    except Exception as e:
        await broadcast({"type":"error","detail":f"DM failed: {e}"})

    # Also notify QA Monitor
    try:
        await relays[TRIAGE].send(QA, json.dumps({"type":"escalation","ticket_id":tid,
            "category":cat,"customer":cust,"query":query}))
    except: pass


async def _fd_got_resolution(msg):
    try: d = json.loads(msg.text)
    except: d = {"resolution":str(msg.text),"ticket_id":"?"}
    tid = d.get("ticket_id","?")
    agent_label = d.get("agent", msg.sender)

    await broadcast({"type":"relay_dm","from_agent":agent_label,"from_name":msg.sender,
                     "to_agent":"Front Desk","to_name":TRIAGE,"tid":tid,
                     "preview":f"Resolution: {str(d.get('resolution',''))[:80]}..."})

    await broadcast({"type":"followup","tid":tid,
                     "detail":f"Front Desk received resolution and sent follow-up email to customer."})
    await broadcast({"type":"complete","tid":tid,
                     "resolved_by":f"{msg.sender} → Front Desk"})
    await _send_stats()


# ============================================================
# AGENT 2: BILLING SPECIALIST
# ============================================================
async def agent_billing():
    r = Relay(BILLING, CFG); await r.__aenter__(); relays[BILLING] = r
    ev = {"type":"agent_online","agent":"Billing Expert","name":BILLING,"model":SMART_MODEL,
          "role":"Billing & Refunds","color":"amber",
          "desc":"Premium model with order history access. Handles charges, refunds, payment disputes."}
    agent_online_events.append(ev); await broadcast(ev)

    def on_msg(msg):
        if msg.sender == BILLING: return
        asyncio.create_task(_billing_handle(msg))
    r.on_message(on_msg)
    while True: await asyncio.sleep(60)


async def _billing_handle(msg):
    try: d = json.loads(msg.text)
    except: return
    if d.get("type") == "resolution": return  # skip resolution echoes
    if "ticket_id" not in d: return  # only handle tickets

    tid, cust, query = d["ticket_id"], d["customer"], d["query"]

    await broadcast({"type":"specialist_pickup","agent":"Billing Expert","color":"amber",
                     "tid":tid,"detail":f"Picking up billing case — I have {cust}'s order history"})
    await broadcast({"type":"thinking","agent":"Billing Expert","color":"amber","tid":tid,
                     "detail":"Checking order history and processing...","model":SMART_MODEL})

    ctx = await get_context("billing", cust, query)
    await broadcast({"type":"context_loaded","agent":"Billing Expert","tid":tid,
                     "sources":ctx["sources"],"is_live":ctx["is_live"]})

    res = await llm(SMART_MODEL,
        f"""You are a billing specialist with access to the customer's account data.
{ctx['context_text']}

Provide a thorough resolution referencing SPECIFIC data from above (order numbers, amounts, dates).
Address the customer by name. Be professional and empathetic.""",
        f"Customer {cust}: {query}", "Billing")

    stats["sp_tokens"] += res["tokens"]; stats["sp_cost"] += res["cost"]
    stats["mono_cost"] += res["cost"]  # mono would also use smart model
    await broadcast({"type":"model_used","agent":"Billing Expert","color":"amber",
                     "model":res["model"],"tokens":res["tokens"],"cost":res["cost"],"ms":res["ms"]})

    await broadcast({"type":"resolution","agent":"Billing Expert","color":"amber",
                     "tid":tid,"text":res["content"]})

    # DM resolution back to Front Desk
    await broadcast({"type":"relay_dm","from_agent":"Billing Expert","from_name":BILLING,
                     "to_agent":"Front Desk","to_name":TRIAGE,"tid":tid,
                     "preview":f"Billing resolved: {res['content'][:80]}..."})
    await relays[BILLING].send(TRIAGE, json.dumps({"ticket_id":tid,"customer":cust,
                                                    "resolution":res["content"],"agent":"Billing Expert"}))

    # QA gets a copy via DM
    try:
        await relays[BILLING].send(QA, json.dumps({"type":"resolution","ticket_id":tid,
            "agent":"Billing Expert","resolution":res["content"],"customer":cust}))
    except: pass


# ============================================================
# AGENT 3: SECURITY SPECIALIST
# ============================================================
async def agent_security():
    r = Relay(SECURITY, CFG); await r.__aenter__(); relays[SECURITY] = r
    ev = {"type":"agent_online","agent":"Security Expert","name":SECURITY,"model":SMART_MODEL,
          "role":"Account Security","color":"red",
          "desc":"Premium model with security log access. Handles compromised accounts, unauthorized access."}
    agent_online_events.append(ev); await broadcast(ev)

    def on_msg(msg):
        if msg.sender == SECURITY: return
        asyncio.create_task(_security_handle(msg))
    r.on_message(on_msg)
    while True: await asyncio.sleep(60)


async def _security_handle(msg):
    try: d = json.loads(msg.text)
    except: return
    if d.get("type") == "resolution": return
    if "ticket_id" not in d: return

    tid, cust, query = d["ticket_id"], d["customer"], d["query"]

    await broadcast({"type":"specialist_pickup","agent":"Security Expert","color":"red",
                     "tid":tid,"detail":f"🚨 Security alert — checking {cust}'s access logs"})
    await broadcast({"type":"thinking","agent":"Security Expert","color":"red","tid":tid,
                     "detail":"Analyzing security logs and taking protective action...","model":SMART_MODEL})

    ctx = await get_context("security", cust, query)
    await broadcast({"type":"context_loaded","agent":"Security Expert","tid":tid,
                     "sources":ctx["sources"],"is_live":ctx["is_live"]})

    res = await llm(SMART_MODEL,
        f"""You are a security specialist with access to the customer's security data.
{ctx['context_text']}

This is urgent. Take immediate protective actions:
1. Detail what you found in the logs (reference SPECIFIC IPs, times, amounts from above)
2. List specific actions taken (account freeze, password reset, etc)
3. Explain next steps
Address the customer by name. Be reassuring but direct.""",
        f"Customer {cust}: {query}", "Security")

    stats["sp_tokens"] += res["tokens"]; stats["sp_cost"] += res["cost"]
    stats["mono_cost"] += res["cost"]
    await broadcast({"type":"model_used","agent":"Security Expert","color":"red",
                     "model":res["model"],"tokens":res["tokens"],"cost":res["cost"],"ms":res["ms"]})

    await broadcast({"type":"resolution","agent":"Security Expert","color":"red",
                     "tid":tid,"text":res["content"]})

    await broadcast({"type":"relay_dm","from_agent":"Security Expert","from_name":SECURITY,
                     "to_agent":"Front Desk","to_name":TRIAGE,"tid":tid,
                     "preview":f"Security resolved: {res['content'][:80]}..."})
    await relays[SECURITY].send(TRIAGE, json.dumps({"ticket_id":tid,"customer":cust,
        "resolution":res["content"],"agent":"Security Expert"}))
    try:
        await relays[SECURITY].send(QA, json.dumps({"type":"resolution","ticket_id":tid,
            "agent":"Security Expert","resolution":res["content"],"customer":cust}))
    except: pass


# ============================================================
# AGENT 4: TECH SUPPORT
# ============================================================
async def agent_tech():
    r = Relay(TECH, CFG); await r.__aenter__(); relays[TECH] = r
    ev = {"type":"agent_online","agent":"Tech Support","name":TECH,"model":FREE_MODEL,
          "role":"Technical Issues","color":"blue",
          "desc":"Free model with bug database access. Handles crashes, errors, technical problems."}
    agent_online_events.append(ev); await broadcast(ev)

    def on_msg(msg):
        if msg.sender == TECH: return
        asyncio.create_task(_tech_handle(msg))
    r.on_message(on_msg)
    while True: await asyncio.sleep(60)


async def _tech_handle(msg):
    try: d = json.loads(msg.text)
    except: return
    if d.get("type") == "resolution": return
    if "ticket_id" not in d: return

    tid, cust, query = d["ticket_id"], d["customer"], d["query"]

    await broadcast({"type":"specialist_pickup","agent":"Tech Support","color":"blue",
                     "tid":tid,"detail":f"Checking bug database for {cust}'s issue"})
    await broadcast({"type":"thinking","agent":"Tech Support","color":"blue","tid":tid,
                     "detail":"Searching known issues and system status...","model":FREE_MODEL})

    ctx = await get_context("technical", cust, query)
    await broadcast({"type":"context_loaded","agent":"Tech Support","tid":tid,
                     "sources":ctx["sources"],"is_live":ctx["is_live"]})

    res = await llm(FREE_MODEL,
        f"""You are tech support with access to the bug database, system status, and ticket history.
{ctx['context_text']}

Match the customer's issue to known bugs if possible. Reference SPECIFIC bug numbers, PRs, and ETAs from above.
Provide:
1. Whether this is a known issue (cite bug number)
2. Current status and ETA for fix
3. Workaround if available
4. Next steps
Address the customer by name.""",
        f"Customer {cust}: {query}", "Tech")

    stats["sp_tokens"] += res["tokens"]; stats["sp_cost"] += res["cost"]
    stats["mono_cost"] += 0.00015 * (res["tokens"]/1000)  # mono would use smart model
    await broadcast({"type":"model_used","agent":"Tech Support","color":"blue",
                     "model":res["model"],"tokens":res["tokens"],"cost":res["cost"],"ms":res["ms"]})

    await broadcast({"type":"resolution","agent":"Tech Support","color":"blue",
                     "tid":tid,"text":res["content"]})

    await broadcast({"type":"relay_dm","from_agent":"Tech Support","from_name":TECH,
                     "to_agent":"Front Desk","to_name":TRIAGE,"tid":tid,
                     "preview":f"Tech resolved: {res['content'][:80]}..."})
    await relays[TECH].send(TRIAGE, json.dumps({"ticket_id":tid,"customer":cust,
        "resolution":res["content"],"agent":"Tech Support"}))
    try:
        await relays[TECH].send(QA, json.dumps({"type":"resolution","ticket_id":tid,
            "agent":"Tech Support","resolution":res["content"],"customer":cust}))
    except: pass


# ============================================================
# AGENT 5: QA MONITOR
# ============================================================
async def agent_qa():
    r = Relay(QA, CFG); await r.__aenter__(); relays[QA] = r
    ev = {"type":"agent_online","agent":"QA Monitor","name":QA,"model":FREE_MODEL,
          "role":"Quality Assurance","color":"slate",
          "desc":"Free model. Monitors all resolutions and scores them for quality, empathy, completeness."}
    agent_online_events.append(ev); await broadcast(ev)

    def on_msg(msg):
        if msg.sender == QA: return
        asyncio.create_task(_qa_review(msg))
    r.on_message(on_msg)
    while True: await asyncio.sleep(60)


async def _qa_review(msg):
    try: d = json.loads(msg.text)
    except: return
    if d.get("type") != "resolution": return

    tid = d.get("ticket_id","?")
    agent = d.get("agent","Unknown")
    resolution = d.get("resolution","")
    cust = d.get("customer","")

    await broadcast({"type":"thinking","agent":"QA Monitor","color":"slate","tid":tid,
                     "detail":f"Reviewing {agent}'s resolution...","model":FREE_MODEL})

    res = await llm(FREE_MODEL,
        """You are a QA reviewer. Score this customer service resolution on 3 criteria (1-5 each):
- Empathy: Did the agent show understanding?
- Completeness: Were all aspects of the issue addressed?
- Actionability: Were clear next steps provided?
Respond ONLY with JSON: {"empathy":N,"completeness":N,"actionability":N,"overall":N,"note":"one sentence"}""",
        f"Agent: {agent}\nCustomer: {cust}\nResolution: {resolution[:500]}", "QA")

    stats["qa_tokens"] += res["tokens"]; stats["qa_cost"] += res["cost"]

    try:
        scores = json.loads(res["content"])
    except:
        scores = {"empathy":4,"completeness":4,"actionability":4,"overall":4,"note":"Good resolution"}

    await broadcast({"type":"qa_score","tid":tid,"agent":agent,"scores":scores,
                     "model":res["model"],"tokens":res["tokens"]})


async def _send_stats():
    multi = stats["fd_cost"] + stats["sp_cost"] + stats["qa_cost"]
    mono = stats["mono_cost"]
    pct = ((mono - multi) / mono * 100) if mono > 0 else 0
    await broadcast({"type":"stats",
        "total":stats["total"],"simple":stats["simple"],"escalated":stats["escalated"],
        "fd_tokens":stats["fd_tokens"],"sp_tokens":stats["sp_tokens"],"qa_tokens":stats["qa_tokens"],
        "multi_cost":round(multi,6),"mono_cost":round(mono,6),"savings_pct":round(pct,1)})


# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup():
    asyncio.create_task(agent_triage())
    await asyncio.sleep(2)
    asyncio.create_task(agent_billing())
    await asyncio.sleep(2)
    asyncio.create_task(agent_security())
    await asyncio.sleep(2)
    asyncio.create_task(agent_tech())
    await asyncio.sleep(2)
    asyncio.create_task(agent_qa())


@app.on_event("shutdown")
async def shutdown():
    for r in relays.values():
        try: await r.__aexit__(None,None,None)
        except: pass


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.post("/api/submit")
async def submit(data: dict):
    q = data.get("query",""); c = data.get("customer","Customer")
    if not q: return {"error":"query required"}
    tid = case_id()
    await broadcast({"type":"ticket_created","tid":tid,"customer":c,"query":q,
                     "timestamp":datetime.now().strftime("%H:%M:%S")})
    await ticket_queue.put({"query":q,"customer":c,"ticket_id":tid})
    return {"status":"processing","ticket_id":tid}


@app.websocket("/ws")
async def ws_ep(ws: WebSocket):
    await ws.accept(); ws_clients.append(ws)
    for ev in agent_online_events:
        await ws.send_text(json.dumps(ev))
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect: ws_clients.remove(ws)


app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "assets"), name="assets")

if __name__ == "__main__":
    import uvicorn
    print(f"\n🎯 Customer Service — Agent Relay Demo (5 agents)")
    print(f"   Triage:   {TRIAGE} ({FREE_MODEL})")
    print(f"   Billing:  {BILLING} ({SMART_MODEL})")
    print(f"   Security: {SECURITY} ({SMART_MODEL})")
    print(f"   Tech:     {TECH} ({FREE_MODEL})")
    print(f"   QA:       {QA} ({FREE_MODEL})")
    print(f"   http://localhost:8081\n")
    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="warning")
