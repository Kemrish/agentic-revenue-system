"""Small operator dashboard for the governed revenue workflow."""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .container import build_container
from .governance.approvals import ApprovalService
from .orchestration.delivery import OutboxDeliveryService
from .settings import Settings


app = FastAPI(title="Agentic Revenue System Dashboard")


HTML = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agentic Revenue System</title>
<style>
:root{--ink:#172033;--muted:#667085;--line:#e5e7eb;--panel:#fff;--bg:#f5f7fb;--blue:#365cf5;--green:#11875d;--amber:#b86b00;--red:#c23b4a;--shadow:0 12px 32px #1720330d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px Inter,Segoe UI,Arial,sans-serif}button{font:inherit;cursor:pointer;border:0}.shell{display:flex;min-height:100vh}.side{width:245px;background:#10182b;color:#dce5ff;padding:26px 18px}.brand{font-weight:800;font-size:18px;line-height:1.2;margin-bottom:35px}.brand span{display:block;color:#8fa8ff;font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-top:8px}.nav{display:grid;gap:8px}.nav div{padding:11px 12px;border-radius:9px;color:#aebbd8}.nav .active{background:#273760;color:white}.main{flex:1;padding:28px 34px;max-width:1500px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:25px}.eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.title{font-size:30px;font-weight:800;margin:6px 0}.sub{color:var(--muted)}.status{display:flex;align-items:center;gap:9px;background:white;padding:10px 14px;border:1px solid var(--line);border-radius:20px}.dot{width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px #11875d1c}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin-bottom:22px}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}.card{padding:18px}.label{color:var(--muted);font-size:12px}.metric{font-size:29px;font-weight:800;margin-top:8px}.content{display:grid;grid-template-columns:1.35fr 1fr;gap:18px}.panel{padding:20px;margin-bottom:18px}.panel h2{font-size:16px;margin:0 0 5px}.panel .hint{color:var(--muted);font-size:12px;margin-bottom:16px}.table{width:100%;border-collapse:collapse}.table th{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:10px 8px;border-bottom:1px solid var(--line)}.table td{padding:13px 8px;border-bottom:1px solid #eef0f4}.badge{display:inline-flex;padding:5px 9px;border-radius:999px;font-size:11px;font-weight:800}.auto{background:#e6f7ef;color:var(--green)}.approval{background:#fff1d9;color:var(--amber)}.deny{background:#ffe6e9;color:var(--red)}.neutral{background:#eef1f7;color:#566176}.actions{display:flex;gap:7px}.btn{padding:7px 10px;border-radius:7px;background:#edf1ff;color:#2948c5;font-weight:700}.btn.danger{background:#fff0f1;color:var(--red)}.scenario{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:13px 0;border-bottom:1px solid var(--line)}.scenario:last-child{border:0}.scenario strong{display:block;margin-bottom:4px}.scenario p{margin:0;color:var(--muted);font-size:12px}.empty{color:var(--muted);padding:18px 0}.toast{position:fixed;right:25px;bottom:25px;background:#10182b;color:white;border-radius:9px;padding:12px 16px;display:none}@media(max-width:950px){.side{display:none}.main{padding:20px}.grid{grid-template-columns:repeat(2,1fr)}.content{grid-template-columns:1fr}}@media(max-width:560px){.grid{grid-template-columns:1fr}.top{display:block}.status{margin-top:15px;width:max-content}}
</style></head><body><div class="shell"><aside class="side"><div class="brand">Agentic<br>Revenue System<span>Governed revenue operations</span></div><div class="nav"><div class="active">Overview</div><div>Pipeline</div><div>Approvals</div><div>Outbox</div><div>Audit trail</div></div></aside><main class="main"><header class="top"><div><div class="eyebrow">Operations control center</div><div class="title">Revenue command center</div><div class="sub">Observe proposals, govern risk, and execute approved work.</div></div><div class="status"><span class="dot"></span><span id="runtime">Loading runtime…</span></div></header><section class="grid" id="metrics"></section><div class="content"><div><section class="panel"><h2>Pipeline and governance</h2><div class="hint">Every action is visible before it reaches an external provider.</div><div id="deals"></div></section><section class="panel"><h2>Recent audit activity</h2><div class="hint">Policy, approval, delivery, and safety evidence.</div><div id="audit"></div></section></div><div><section class="panel"><h2>Policy simulator</h2><div class="hint">The three outcomes used by the Rulebook.</div><div id="scenarios"></div></section><section class="panel"><h2>Pending approvals</h2><div class="hint">Human review is required before high-impact actions.</div><div id="approvals"></div></section><section class="panel"><h2>Outbox</h2><div class="hint">Approved work waiting for provider delivery.</div><div id="outbox"></div></section></div></div></main></div><div class="toast" id="toast"></div><script>
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge=x=>`<span class="badge ${x==='AUTO'?'auto':x==='DENY'?'deny':x==='REQUIRE_APPROVAL'?'approval':'neutral'}">${esc(x)}</span>`;
function toast(s){const t=document.querySelector('#toast');t.textContent=s;t.style.display='block';setTimeout(()=>t.style.display='none',2500)}
async function action(url,method='POST'){const r=await fetch(url,{method});const d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');toast(d.message||'Updated');await load()}
async function load(){const d=await fetch('/api/overview').then(r=>r.json());document.querySelector('#runtime').textContent=`${d.runtime.provider} · ${d.runtime.mode}`;document.querySelector('#metrics').innerHTML=[['Deals',d.metrics.deals],['Pending approvals',d.metrics.pending_approvals],['Outbox pending',d.metrics.outbox_pending],['Audit events',d.metrics.audit_events]].map(x=>`<div class="card"><div class="label">${x[0]}</div><div class="metric">${x[1]}</div></div>`).join('');document.querySelector('#deals').innerHTML=d.deals.length?`<table class="table"><tr><th>Account</th><th>Segment</th><th>Score</th><th>Tier</th><th>Stage</th></tr>${d.deals.map(x=>`<tr><td><strong>${esc(x.company)}</strong><br><span class="label">${esc(x.contact)}</span></td><td>${esc(x.segment)}</td><td>${x.score}</td><td>${badge(x.tier)}</td><td>${esc(x.stage)}</td></tr>`).join('')}</table>`:'<div class="empty">No deals yet. Run the demo to populate the dashboard.</div>';document.querySelector('#approvals').innerHTML=d.approvals.length?d.approvals.map(x=>`<div class="scenario"><div><strong>${esc(x.action)}</strong><p>${esc(x.deal_id)}</p></div><div class="actions"><button class="btn" onclick="action('/api/approvals/${encodeURIComponent(x.id)}/approve')">Approve</button><button class="btn danger" onclick="action('/api/approvals/${encodeURIComponent(x.id)}/reject')">Reject</button></div></div>`).join(''):'<div class="empty">No pending approvals.</div>';document.querySelector('#outbox').innerHTML=d.outbox.length?d.outbox.map(x=>`<div class="scenario"><div><strong>${esc(x.action)}</strong><p>${esc(x.deal_id)} · ${esc(x.status)}</p></div></div>`).join(''):'<div class="empty">Outbox is clear.</div>';document.querySelector('#audit').innerHTML=d.audit.length?`<table class="table"><tr><th>Actor</th><th>Action</th><th>Detail</th></tr>${d.audit.slice(0,8).map(x=>`<tr><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td>${esc(x.detail)}</td></tr>`).join('')}</table>`:'<div class="empty">No audit events yet.</div>';document.querySelector('#scenarios').innerHTML=d.scenarios.map(x=>`<div class="scenario"><div><strong>${esc(x.name)}</strong><p>${esc(x.reason)}</p></div>${badge(x.decision)}</div>`).join('')}
load();setInterval(load,10000);
</script></body></html>"""


def _rows(store, query: str, params: tuple = ()):
    return [dict(row) for row in store.connection.execute(query, params)]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML


@app.get("/api/overview")
def overview() -> dict:
    settings = Settings()
    container = build_container(settings)
    store = container.store
    deals = []
    for row in _rows(store, "SELECT id, company_name, contact_name, segment, stage, payload FROM deals ORDER BY updated_at DESC"):
        payload = json.loads(row.pop("payload"))
        score = payload.get("score") or {}
        deals.append({**row, "score": round(score.get("total", 0)), "tier": score.get("tier", "-"), "stage": row["stage"]})
    approvals = _rows(store, "SELECT id, deal_id, action_type FROM approvals WHERE status='pending' ORDER BY created_at DESC")
    outbox = _rows(store, "SELECT id, deal_id, action_type, status FROM outbox WHERE status='pending' ORDER BY created_at DESC")
    audit = _rows(store, "SELECT actor, action, detail, created_at FROM audit_log ORDER BY id DESC LIMIT 20")
    return {"runtime": {"provider": settings.llm_provider, "mode": settings.runtime_mode}, "metrics": {"deals": len(deals), "pending_approvals": len(approvals), "outbox_pending": len(outbox), "audit_events": store.connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]}, "deals": deals, "approvals": approvals, "outbox": outbox, "audit": audit, "scenarios": [{"name": "Auto", "decision": "AUTO", "reason": "Low-risk enrichment, scoring, or follow-up is allowed."}, {"name": "Human approval", "decision": "REQUIRE_APPROVAL", "reason": "Tier-A first touch or commercial action needs review."}, {"name": "Denied", "decision": "DENY", "reason": "Kill switch or unsafe policy condition blocks execution."}]}


@app.post("/api/approvals/{approval_id}/approve")
def approve(approval_id: str) -> dict:
    container = build_container(Settings())
    if not container.store.get_approval(approval_id):
        raise HTTPException(404, "approval not found")
    ApprovalService(container.store).decide(approval_id, True)
    return {"message": "Approval granted and action queued for delivery"}


@app.post("/api/approvals/{approval_id}/reject")
def reject(approval_id: str) -> dict:
    container = build_container(Settings())
    if not container.store.get_approval(approval_id):
        raise HTTPException(404, "approval not found")
    ApprovalService(container.store).decide(approval_id, False)
    return {"message": "Approval rejected"}


@app.post("/api/outbox/deliver")
async def deliver() -> dict:
    container = build_container(Settings())
    delivered = await OutboxDeliveryService(container.store, container.mail).deliver_pending()
    return {"message": f"Delivered {len(delivered)} item(s)", "delivered": delivered}
