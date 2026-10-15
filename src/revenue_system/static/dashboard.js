'use strict';
const $ = selector => document.querySelector(selector);
const $$ = selector => Array.from(document.querySelectorAll(selector));
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const human = value => String(value ?? '').replaceAll('_', ' ');
const cls = value => String(value ?? '').toLowerCase().replace(/[^a-z_]/g, '');
const badge = (value, text) => `<span class="badge ${cls(value)}">${esc(text ?? human(value))}</span>`;
const num = (value, digits=2) => Number(value || 0).toLocaleString(undefined, {maximumFractionDigits: digits});
const MAIN_PATH = ['new','enriched','scored','outreach','engaged','meeting','qualified','proposal','contracting','closed_won'];
const MAIL = ['send_first_touch','send_follow_up'];

const titles = {
  explain: ['Present', 'How the system works', 'Follow one lead from first signal to signed IO, and see where AI judgment ends and code control begins.'],
  lab: ['Present', 'Demo lab', 'Run the real pipeline and exercise each agent, rule, and validator live.'],
  overview: ['Operate', 'Revenue command center', 'Observe proposals, govern risk, and trace approved work.'],
  pipeline: ['Operate', 'Pipeline workspace', 'Inspect accounts, qualification evidence, scores, and lifecycle stages.'],
  approvals: ['Operate', 'Approval center', 'Review the exact recipient and message before deciding.'],
  outbox: ['Operate', 'Outbox operations', 'Inspect queued work, deliver permitted actions, and track the results.'],
  lessons: ['Operate', 'Lesson library', 'Curate what the system learns from calls and rejections before agents may use it.'],
  audit: ['Operate', 'Audit trail', 'Trace scoring, decisions, rejection reasons, and provider delivery.'],
};
const LIVE_VIEWS = new Set(['overview','pipeline','approvals','outbox','lessons','audit']);
const state = {data:null, system:null, loading:false, busy:false, review:null, search:'', stageFilter:'', auditFilter:'', auditActor:'',
  step:0, labTab:'run', lab:{score:{segment:'brand', fit:88, intent:70, engagement:0}, policy:{action_type:'send_first_touch', tier:'A', injection_detected:false, kill_switch:false}}};
const selectedView = () => Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
const table = (headers, body) => `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
const empty = message => `<div class="empty">${esc(message)}</div>`;
function notice(message, error=false) { $('#notice').textContent=message; $('#notice').className=`banner ${error?'error':'success'}`; $('#notice').hidden=false; }
async function request(url, options={}) {
  const response=await fetch(url, {cache:'no-store', ...options});
  const data=await response.json().catch(()=>({detail:`Server returned ${response.status}.`}));
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Check the form values and try again.');
  return data;
}
const post = (url, body={}) => request(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

/* ---------- shared fragments ---------- */
function pipeline(deals) {
  if(!deals.length) return empty('No deals match this view.');
  return table(['Account / contact','Segment','Score / tier','Stage','Evidence',''], deals.map(d=>`<tr class="clickable" data-command="deal" data-id="${esc(d.id)}"><td><strong>${esc(d.company)}</strong><small>${esc(d.contact)}</small><small class="mono">${esc(d.id)}</small></td><td>${esc(d.segment)}</td><td><strong>${num(Math.round(d.score))}</strong> ${badge(d.tier)}</td><td>${badge('stage', human(d.stage))}</td><td>${esc(d.score_reason)}</td><td><button type="button" class="button secondary small" data-command="deal" data-id="${esc(d.id)}">Open</button></td></tr>`).join(''));
}
function reviewButton(kind, id, label='Review details') {
  return `<button type="button" class="button secondary" data-command="review" data-kind="${kind}" data-id="${esc(id)}">${label}</button>`;
}
function approvals(items) {
  return items.length?items.map(item=>`<div class="row"><div><strong>${esc(item.company)}</strong> ${badge(item.tier)} ${badge('require_approval', human(item.action_type))}<p>To: ${esc(item.payload.recipient || 'Recipient required')} · ${esc(item.payload.subject || (item.action_type==='send_contract'?'Insertion order for signature':'No subject'))}</p><p>${esc(item.policy_reason)}</p></div>${reviewButton('approvals',item.id)}</div>`).join(''):empty('No pending approvals. Decided requests appear in the history below.');
}
function audit(items) {
  return items.length?table(['Time (UTC)','Actor','Action','Deal','Detail'], items.map(a=>`<tr><td class="mono">${esc(a.created_at)}</td><td>${esc(a.actor)}</td><td>${badge(a.action)}</td><td class="mono">${esc(a.deal_id || 'System')}</td><td>${esc(a.detail)}</td></tr>`).join('')):empty('No audit events match this view.');
}
const actorKind = actor => actor.startsWith('agent')?'agent':actor.startsWith('human')?'human':['policy','delivery'].includes(actor)?actor:'system';
function timeline(items) {
  if(!items.length) return empty('No activity yet.');
  return `<ul class="timeline">${items.map(a=>`<li><span class="pip ${actorKind(a.actor)}"></span><div><div class="meta">${esc(a.created_at)} · ${esc(a.actor)}${a.deal_id?` · ${esc(a.deal_id)}`:''}</div><div class="what">${badge(a.action)}</div><div class="detail">${esc(a.detail)}</div></div></li>`).join('')}</ul>`;
}
function bars(entries, kind='') {
  const max=Math.max(1,...entries.map(e=>e[1]));
  return `<div class="bars">${entries.map(([name,value])=>`<div class="bar-row"><span class="label">${esc(human(name))}</span><div class="bar-track"><div class="bar-fill ${kind?cls(name):''}" style="width:${(value/max)*100}%"></div></div><span class="value">${esc(value)}</span></div>`).join('')}</div>`;
}
function emptyWorkspace() {
  if(state.data?.runtime.demo_enabled===false) return `<section class="panel hero-empty"><div class="eyebrow">Production workspace</div><h2>Ready for incoming leads</h2><p>Import approved lead data or connect your signed event gateway, then run the event worker. Fixture seeding and reset are disabled in this environment.</p></section>`;
  return `<section class="panel hero-empty"><div class="eyebrow">Empty workspace</div><h2>Run the demo pipeline to populate the workspace</h2><p>This sends ten fixture leads, a reply, a prompt-injection attempt, and a discovery call through the real orchestrator, agents, and policy engine.</p><div class="actions" style="justify-content:center"><button type="button" class="button" data-command="run-demo">Run demo pipeline</button><a class="button secondary" href="#explain">How it works</a></div></section>`;
}

/* ---------- operate views ---------- */
function viewOverview(d) {
  if(!d.deals.length) return emptyWorkspace();
  const stages=MAIN_PATH.filter(s=>d.stage_counts[s]).map(s=>[s,d.stage_counts[s]]);
  if(d.stage_counts.closed_lost) stages.push(['closed_lost',d.stage_counts.closed_lost]);
  const pd=d.policy_decisions||{};
  const decisions=['AUTO','REQUIRE_APPROVAL','DENY','KILL_SWITCH'].map(k=>[k,pd[k]||0]);
  return `<div class="grid-2"><section class="panel"><div class="panel-heading"><div><h2>Pipeline by stage</h2><p class="hint">Stages are owned by the orchestrator's state machine.</p></div><a class="button secondary small" href="#pipeline">View pipeline</a></div>${bars(stages)}</section>
  <section class="panel"><div class="panel-heading"><div><h2>Policy decisions</h2><p class="hint">Every proposed action, routed by code.</p></div><a class="button secondary small" href="#lab" data-lab-tab="policy">Simulate</a></div>${bars(decisions,true)}<p class="hint" style="margin:14px 0 0">${d.scenarios.map(s=>`<b>${esc(human(s.decision))}</b>: ${esc(s.reason)}`).join('<br>')}</p></section></div>
  <div class="columns"><section class="panel"><div class="panel-heading"><div><h2>Pending reviews</h2><p class="hint">High-risk actions waiting for a human.</p></div><a class="button secondary small" href="#approvals">Open approvals</a></div>${approvals(d.approvals.slice(0,4))}</section>
  <section class="panel"><div class="panel-heading"><div><h2>Recent activity</h2><p class="hint">Latest audit events.</p></div><a class="button secondary small" href="#audit">Full trail</a></div>${timeline(d.audit.slice(0,7))}</section></div>`;
}
function filteredDeals(d) {
  return d.deals.filter(x=>(!state.stageFilter||x.stage===state.stageFilter)&&`${x.company} ${x.contact} ${x.segment}`.toLowerCase().includes(state.search.toLowerCase()));
}
function viewPipeline(d) {
  const stages=Object.keys(d.stage_counts).sort((a,b)=>MAIN_PATH.indexOf(a)-MAIN_PATH.indexOf(b));
  const chips=[['','All',d.deals.length],...stages.map(s=>[s,human(s),d.stage_counts[s]])].map(([v,l,n])=>`<button type="button" class="filter" data-command="stage-filter" data-stage="${esc(v)}" aria-pressed="${state.stageFilter===v}">${esc(l)} · ${n}</button>`).join('');
  return `<section class="panel"><div class="panel-heading"><div><h2>All deals</h2><p class="hint">${d.deals.length} accounts. Open a deal to see its stage history, score breakdown, and audit trail.</p></div><input class="search" id="pipeline-search" aria-label="Search pipeline" placeholder="Search account, contact, or segment" value="${esc(state.search)}"></div><div class="filters" style="margin-bottom:14px">${chips}</div><div id="pipeline-results">${pipeline(filteredDeals(d))}</div></section>`;
}
function viewApprovals(d) {
  return `<section class="panel"><div class="panel-heading"><div><h2>Pending approvals</h2><p class="hint">Open a proposal to inspect the recipient, full message, score, and policy reason.</p></div></div>${approvals(d.approvals)}</section><section class="panel"><h2>Decision history</h2><p class="hint">Rejections retain the operator's explanation.</p>${d.approval_history.length?table(['Account','Action','Decision','Reason','Details'],d.approval_history.map(x=>`<tr><td>${esc(x.company)}</td><td>${esc(human(x.action_type))}</td><td>${badge(x.status)}</td><td>${esc(x.rejection_reason || 'Approved for delivery')}</td><td>${reviewButton('history',x.id,'View decision')}</td></tr>`).join('')):empty('No decisions yet.')}</section>`;
}
function viewOutbox(d) {
  const pending=d.outbox.filter(x=>x.status==='pending');
  return `<section class="panel"><div class="panel-heading"><div><h2>Delivery queue and history</h2><p class="hint">Mail: ${esc(d.runtime.mail_mode)} · External sending ${d.runtime.live_side_effects_enabled?'enabled':'disabled'}. Rows are marked sent only after the provider confirms.</p></div><button class="button" type="button" data-command="delivery" ${!pending.length||state.busy||d.runtime.kill_switch?'disabled':''}>${state.busy?'Working...':'Review delivery batch'}</button></div>${d.outbox.length?table(['Account','Action','Recipient','Status','Details'],d.outbox.map(x=>`<tr><td>${esc(x.company)}<small class="mono">${esc(x.deal_id)}</small></td><td>${esc(human(x.action_type))}</td><td>${esc(x.payload.recipient || (x.action_type==='send_contract'?'E-signature signer':'Recipient required'))}</td><td>${badge(x.status)}</td><td>${reviewButton('outbox',x.id)}</td></tr>`).join('')):empty('No queued or delivered actions.')}</section>`;
}
function viewLessons(d) {
  const counts={proposed:0,active:0,retired:0}; d.lessons.forEach(l=>counts[l.status]=(counts[l.status]||0)+1);
  const actionsFor=l=>l.status==='proposed'?`<button class="button success small" data-command="lesson" data-id="${esc(l.id)}" data-status="active">Promote</button> <button class="button danger small" data-command="lesson" data-id="${esc(l.id)}" data-status="retired">Retire</button>`:l.status==='active'?`<button class="button danger small" data-command="lesson" data-id="${esc(l.id)}" data-status="retired">Retire</button>`:`<button class="button secondary small" data-command="lesson" data-id="${esc(l.id)}" data-status="proposed">Restore</button>`;
  return `<section class="panel"><div class="panel-heading"><div><h2>How the learning loop works</h2><p class="hint">Call transcripts and rejection reasons create <b>proposed</b> lessons. Only <b>active</b> lessons are retrieved by the outreach agent, and every draft records which ones it used in <span class="mono">lessons_used</span>. Promotion is a human step so untrusted text never becomes an instruction automatically.</p></div></div><div class="kv-grid"><div><small>Proposed</small><strong>${counts.proposed}</strong></div><div><small>Active</small><strong>${counts.active}</strong></div><div><small>Retired</small><strong>${counts.retired||0}</strong></div></div></section>
  <section class="panel"><h2>Lessons</h2><p class="hint">Promote a lesson, then re-run the pipeline from the Demo lab to see it appear in new drafts.</p>${d.lessons.length?table(['Lesson','Scope','Status','Evidence','Actions'],d.lessons.map(l=>`<tr><td><strong>${esc(l.statement)}</strong><small class="mono">${esc(l.id)}</small></td><td>${esc(l.segment)}</td><td>${badge(l.status)}</td><td>${(l.evidence||[]).map(e=>`<span class="chip">${esc(e)}</span>`).join('')}</td><td style="white-space:nowrap">${actionsFor(l)}</td></tr>`).join('')):empty('No lessons yet. Run the demo pipeline or digest a call in the Demo lab.')}</section>`;
}
function filteredAudit(d) {
  return d.audit.filter(x=>(!state.auditFilter||x.action===state.auditFilter)&&(!state.auditActor||actorKind(x.actor)===state.auditActor));
}
function viewAudit(d) {
  return `<section class="panel"><div class="panel-heading"><div><h2>Audit evidence</h2><p class="hint">Showing the latest ${d.audit.length} events. Total: ${d.metrics.audit_events}.</p></div><div class="actions"><select id="audit-actor" aria-label="Filter by actor" style="width:auto"><option value="">All actors</option><option value="agent">Agents</option><option value="policy">Policy</option><option value="human">Humans</option><option value="delivery">Delivery</option><option value="system">Orchestrator</option></select><select id="audit-filter" aria-label="Filter audit events" style="width:auto"><option value="">All events</option><option value="approval_rejected">Rejections</option><option value="outbox_failed">Delivery failures</option><option value="outbox_sent">Successful deliveries</option><option value="DENY">Policy denials</option><option value="KILL_SWITCH">Emergency stops</option><option value="stage_changed">Stage changes</option></select></div></div><div id="audit-results">${audit(filteredAudit(d))}</div></section>`;
}

/* ---------- deal record ---------- */
function openDeal(id) {
  const d=state.data, deal=d.deals.find(x=>x.id===id); if(!deal) return;
  const idx=MAIN_PATH.indexOf(deal.stage);
  const steps=MAIN_PATH.map((s,i)=>`<div class="stage-step ${i<idx?'done':i===idx?'current':''}">${esc(human(s))}</div>`).join('');
  const related=[...d.approvals,...d.approval_history,...d.outbox].filter(x=>x.deal_id===id);
  const events=d.audit.filter(a=>a.deal_id===id);
  const qual=Object.entries(deal.fields).filter(([k])=>['budget','timeline','decision_maker','monthly_impressions','current_ssp','last_reply','enrichment_status'].includes(k));
  const raw=d.deals.find(x=>x.id===id);
  $('#deal-title').textContent=`${deal.company} · ${deal.contact}`;
  $('#deal-content').innerHTML=`<div class="panel" style="box-shadow:none"><div class="panel-heading"><div><h3>Lifecycle</h3><p class="hint">Current stage ${badge('stage',human(deal.stage))}. Transitions are guarded by <span class="mono">domain/stages.py</span>.</p></div>${badge(deal.segment,deal.segment)}</div><div class="stages">${steps}</div></div>
  <div class="grid-2"><div class="panel" style="box-shadow:none"><h3>Score ${num(raw.score)} ${badge(raw.tier)}</h3><p class="hint">${esc(raw.score_reason)}</p><div class="score-bars">${['fit','intent','engagement'].map(k=>`<div class="bar-row"><span class="label">${k}</span><div class="bar-track"><div class="bar-fill" style="width:${Number(deal.fields[k]??0)}%"></div></div><span class="value">${esc(deal.fields[k]??0)}</span></div>`).join('')}</div></div>
  <div class="panel" style="box-shadow:none"><h3>Deal fields</h3>${qual.length?`<dl class="details">${qual.map(([k,v])=>`<div><dt>${esc(human(k))}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`:'<p class="hint">No qualification fields captured yet.</p>'}<details><summary>Raw lead record</summary><pre class="code">${esc(JSON.stringify(deal.fields,null,2))}</pre></details></div></div>
  <div class="grid-2"><div class="panel" style="box-shadow:none"><h3>Actions</h3>${related.length?related.map(x=>`<div class="row"><div><strong>${esc(human(x.action_type))}</strong><p>${esc(x.payload.subject||'')}</p></div>${badge(x.status)}</div>`).join(''):'<p class="hint">No actions routed.</p>'}</div>
  <div class="panel" style="box-shadow:none"><h3>Audit trail</h3>${timeline(events.slice(0,12))}</div></div>`;
  if(!$('#deal-dialog').open) $('#deal-dialog').showModal();
}

/* ---------- how it works ---------- */
const FLOW = [
  {name:'Sources', sub:'Where data comes from', body:'Leads arrive from HubSpot, replies from the mail provider, and call transcripts from Fireflies. In this demo the same payload shapes are loaded from fixtures.',
   in:'HubSpot webhook · inbound email · Fireflies transcript', out:'Raw JSON or text payload',
   points:['Webhook payloads are HMAC-verified before they are stored','All inbound text is treated as untrusted data from this point on','Demo fixtures: leads.json, replies/, transcripts/'],
   files:['webhooks.py','fixtures/leads.json','fixtures/replies/','fixtures/transcripts/'], say:'Everything starts as an external event. Nothing the outside world sends is trusted or executed.'},
  {name:'Durable event', sub:'Normalise and de-duplicate', body:'Each trigger becomes a DomainEvent with a source idempotency key such as hubspot:<eventId>, written to the events table before any work happens.',
   in:'Raw payload', out:'events row (pending → processed)',
   points:['The event id is a primary key, so a duplicate webhook returns "duplicate" and is never processed twice','SLA timers become the same kind of event, so one processing path covers everything','A crash before processing leaves the event pending for retry'],
   files:['orchestration/events.py','adapters/db.py · add_event_once','orchestration/worker.py'], say:'If HubSpot retries the same webhook five times, we process it exactly once.'},
  {name:'Orchestrator', sub:'Owns deal state', body:'The DealOrchestrator creates the deal, enriches it, scores it using the segment pack, and moves it through the lifecycle. Only allowed transitions are possible.',
   in:'Event', out:'Deal row, score, stage',
   points:['Scoring is deterministic: weights, tiers and the fit gate come from pack.yaml','Every score carries a human-readable reason','transition() raises on any illegal stage jump','Exit criteria: a deal reaches "qualified" only when every pack qualification field is captured'],
   files:['orchestration/orchestrator.py','domain/stages.py','skills/scoring.py'], say:'The orchestrator is the only component allowed to change a deal stage. Agents never move deals.'},
  {name:'Agents', sub:'Judgment, not authority', body:'LLM agents handle language: drafting outreach, classifying replies, digesting calls and mapping IO fields. Each returns a typed Pydantic object, never an action.',
   in:'Deal context and wrapped untrusted text', out:'Typed, schema-validated proposal',
   points:['Each agent has its own tool scope; none can send, sign, price or move stages','Untrusted text is wrapped in <untrusted_data> tags','Malformed model output fails schema validation and is rejected','Runner is swappable: live Claude/OpenRouter, record, replay or test'],
   files:['agents/*.py','agents/tools.py · TOOL_SCOPES','agents/prompts/*.md','adapters/claude_runner.py'], say:'The model can be wrong or even manipulated. The worst it can do is produce a bad proposal, and proposals still have to pass policy.'},
  {name:'Policy gate', sub:'Autonomy enforced in code', body:'Every proposed action is evaluated by the PolicyEngine. The decision and the rule that produced it are written to the audit log.',
   in:'Action, deal and segment pack', out:'AUTO · REQUIRE_APPROVAL · DENY · KILL_SWITCH',
   points:['Tier A first touch, pricing and contracts always need a human','Injection-flagged or unsafe payloads are denied outright','Anything without an explicit rule defaults to approval: fail safe','AUTO goes straight to the outbox; APPROVAL goes to the queue'],
   files:['governance/policy.py','orchestration/actions.py · route_action'], say:'Safety lives in an if-statement, not in a prompt. You cannot talk your way past it.'},
  {name:'Human approval', sub:'Review the exact payload', body:'High-risk actions land in the approvals table. An operator sees the exact recipient, message, score and policy reason before deciding.',
   in:'approvals row (pending)', out:'Outbox row, or a proposed lesson',
   points:['Approve: decision, audit entry and outbox row commit in one transaction','Reject: a reason is mandatory and becomes a proposed lesson','A decision can be made only once (UPDATE … WHERE status = pending)'],
   files:['governance/approvals.py','dashboard.py'], say:'Rejections are not wasted. The reason feeds the learning loop.'},
  {name:'Outbox delivery', sub:'Side effects, done safely', body:'The delivery service reads pending outbox rows and calls the provider adapter. A row is marked sent only after the provider succeeds.',
   in:'outbox row (pending)', out:'Provider call, then status sent',
   points:['A unique action key prevents duplicate emails or envelopes','The kill switch and unsafe flags are re-checked at send time','Live mail is restricted to an allowlist plus an explicit opt-in','Failures stay pending and are audited'],
   files:['orchestration/delivery.py','adapters/mail.py','adapters/esign.py'], say:'Agents never touch the email or e-sign APIs. Only the outbox does, after policy and approval.'},
  {name:'Providers & audit', sub:'Every step is traceable', body:'Mail, Dropbox Sign, Fireflies and HubSpot sit behind ports. Every score, decision, approval, delivery and failure is written to audit_log.',
   in:'Provider response', out:'audit_log, CRM state, lessons',
   points:['Adapters switch between live, record, replay and test per integration','Replay mode makes the demo deterministic without credentials','The audit trail answers who did what, when, and why for each deal'],
   files:['adapters/','container.py','audit_log table'], say:'For any deal I can show exactly why the system did what it did.'},
];
const LOOP = [['Capture','Call intelligence proposes a lesson; rejection reasons become lessons too.'],['Propose','Stored with segment scope and evidence, status proposed.'],['Curate','A human promotes it to active, or retires it.'],['Retrieve','Outreach retrieves active lessons for its segment plus global ones.'],['Trace','Each draft reports lessons_used, so outcomes can be measured per lesson.']];
const LAYERS = [['Scoped tools','Each agent receives only its own tools. Reply triage has none.'],['Untrusted data wrapping','Emails and transcripts are delimited and labelled as data, never instructions.'],['Typed outputs','Pydantic schemas reject malformed or extra-field responses.'],['Policy engine','AUTO, APPROVAL, DENY or KILL_SWITCH decided in Python, with a rule id.'],['Human approval','Tier A first touch, pricing and contracts always wait for a person.'],['Outbox controls','Idempotent keys, recipient allowlist, explicit live side-effect opt-in.'],['Kill switch','A database flag checked at routing time and again at delivery.'],['Audit log','Every decision and side effect is recorded with actor and reason.']];
const TABLES = [['events','Every inbound trigger, keyed for idempotency'],['deals','Deal state, stage, fields and score'],['approvals','High-risk actions waiting for, or decided by, a human'],['outbox','Approved or automatic side effects awaiting delivery'],['audit_log','Append-only trail of every decision and delivery'],['lessons','Proposed, active and retired lessons with evidence'],['system_flags','Operational switches such as the global kill switch']];
const TRADEOFFS = [['Modular monolith','Microservices','One deployable, easy to test and demo. Ports keep a later split open.','Less independent scaling.'],['SQLite now','PostgreSQL','Durable local state with zero setup.','Single-writer concurrency; Postgres is the production target.'],['Rule-based scoring','Trained model','Transparent reasons; no win/loss data exists yet.','Weights are hand-tuned until outcome data exists.'],['Typed proposals','Agents with action tools','Model mistakes cannot cause side effects.','More orchestration code.'],['Templates for documents','Generated contracts','The model never writes prices or legal language.','Templates must be maintained per segment.'],['Replay mode','Live only','Deterministic demos and regression tests.','Recordings must be refreshed when prompts change.']];

function flowStep() {
  const s=FLOW[state.step];
  return `<div class="step-detail"><div><div class="eyebrow">Step ${state.step+1} of ${FLOW.length} · ${esc(s.sub)}</div><h3>${esc(s.name)}</h3><p>${esc(s.body)}</p><div class="io-pair"><div class="io-box"><small>Data in</small>${esc(s.in)}</div><div class="io-box"><small>Data out</small>${esc(s.out)}</div></div><div class="say"><small>Say this</small>“${esc(s.say)}”</div></div><div><h3>Guarantees</h3><ul class="checks">${s.points.map(p=>`<li>${esc(p)}</li>`).join('')}</ul><h3 style="margin-top:16px">Where it lives</h3>${s.files.map(f=>`<span class="chip">${esc(f)}</span>`).join('')}</div></div>
  <div class="step-nav"><button type="button" class="button secondary" data-command="step" data-step="${state.step-1}" ${state.step===0?'disabled':''}>← Previous</button><span class="hint">Use <span class="kbd">←</span> <span class="kbd">→</span> to step through</span><button type="button" class="button" data-command="step" data-step="${state.step+1}" ${state.step===FLOW.length-1?'disabled':''}>Next →</button></div>`;
}
function renderFlow() {
  $$('.flow-node').forEach((node,i)=>{node.classList.toggle('done',i<state.step); i===state.step?node.setAttribute('aria-current','step'):node.removeAttribute('aria-current');});
  $('#flow-step').innerHTML=flowStep();
}
function viewExplain() {
  const sys=state.system;
  if(!sys) return `<section class="panel empty">Loading system description...</section>`;
  const counts=state.data?.stage_counts||{};
  const lifecycle=MAIN_PATH.map(s=>`<span class="node ${s==='closed_won'?'won':''}">${esc(human(s))}${counts[s]?`<span class="count">${counts[s]}</span>`:''}</span>`).join('<span class="arrow">→</span>');
  const lostFrom=sys.transitions.filter(t=>t[1]==='closed_lost').map(t=>human(t[0]));
  const [a,b]=sys.segments;
  const segRow=(label,fn)=>{const va=fn(a),vb=b?fn(b):'';return `<tr class="${va!==vb?'diff':''}"><td><strong>${esc(label)}</strong></td><td>${esc(va)}</td>${b?`<td>${esc(vb)}</td>`:''}</tr>`;};
  return `<section class="hero"><div class="eyebrow">Cool AI · Agentic Revenue System</div><h2>Agents propose. Code decides.</h2><p>An AI-assisted revenue lifecycle that turns leads, replies and call transcripts into governed revenue actions, from first signal to signed IO. Language models do the reading and writing; deterministic Python owns state, policy, approvals, delivery and the audit trail.</p>
  <div class="principles"><div class="principle"><b>Single-responsibility agents</b><span>Six agents, each with one job, a typed output and its own tool scope.</span></div><div class="principle"><b>Autonomy enforced in code</b><span>A policy engine routes every action to AUTO, APPROVAL or DENY.</span></div><div class="principle"><b>Segments as configuration</b><span>Brands and publishers share all code; only the YAML pack differs.</span></div></div></section>

  <div class="section-title"><span class="n">01</span><h2>The journey of one lead</h2></div>
  <section class="panel"><div class="flow" role="tablist" aria-label="System flow">${FLOW.map((s,i)=>`<button type="button" class="flow-node" data-command="step" data-step="${i}" role="tab"><span class="num">${String(i+1).padStart(2,'0')}</span><span class="name">${esc(s.name)}</span></button>`).join('')}</div><div id="flow-step">${flowStep()}</div></section>

  <div class="section-title"><span class="n">02</span><h2>Deal lifecycle</h2><span class="hint">Live counts from this workspace</span></div>
  <section class="panel"><div class="lifecycle">${lifecycle}</div><p class="hint" style="margin:12px 0 0">Any other jump raises <span class="mono">Invalid stage transition</span>. A deal can move to <span class="badge c">closed lost</span> from: ${esc(lostFrom.join(', '))}.</p></section>

  <div class="section-title"><span class="n">03</span><h2>The agents</h2><span class="hint">Tool scopes are read from the code</span></div>
  <div class="grid-3">${sys.agents.map(ag=>`<article class="agent-card ${ag.untrusted?'untrusted':''}"><header><h3>${esc(ag.title)}</h3>${badge(ag.status)}</header><p class="hint" style="margin:0">${esc(ag.job)}</p><div class="kv"><b>Reads</b>${esc(ag.input)}${ag.untrusted?' <span class="badge deny plain">untrusted</span>':''}</div><div class="kv"><b>Returns</b>${esc(ag.output)}</div><div class="kv"><b>Tools</b>${ag.tools.length?ag.tools.map(t=>`<span class="chip">${esc(t)}</span>`).join(''):'<span class="no-tools">No tools: reads untrusted input</span>'}</div></article>`).join('')}</div>
  <p class="hint" style="margin-top:10px">No agent has a tool that sends email, requests a signature, changes price or moves a stage. Deterministic skills (scoring, IO validation, templating, lessons, SLA tracking) do the non-judgment work.</p>

  <div class="section-title"><span class="n">04</span><h2>Autonomy policy</h2><span class="hint">Evaluated top to bottom; first match wins</span></div>
  <div class="grid-2"><section class="panel"><div class="rule-list">${sys.policy_rules.map(r=>`<div class="rule"><div><strong>${esc(r.when)}</strong><div class="rid">${esc(r.rule_id)}</div></div>${badge(r.decision)}</div>`).join('')}</div></section>
  <section class="panel"><h3>Why this matters</h3><ul class="checks"><li>The policy is Python, not a prompt. A prompt injection cannot change it.</li><li>It runs after the agent, so even a fully manipulated model only produces a proposal.</li><li>The default is approval: a new action type is safe before anyone writes a rule for it.</li><li>The decision and rule id are audited for every action.</li></ul><div class="actions" style="margin-top:16px"><a class="button" href="#lab" data-lab-tab="policy">Try the policy simulator</a></div></section></div>

  <div class="section-title"><span class="n">05</span><h2>Segment packs</h2><span class="hint">Highlighted rows differ between segments</span></div>
  <section class="panel">${table(['Setting',...sys.segments.map(s=>`${s.display_name} · packs/${s.segment}/pack.yaml`)],[
    segRow('Products',s=>(s.messaging.products||[]).join(', ')), segRow('Pillars',s=>(s.messaging.pillars||[]).join(', ')),
    segRow('Qualification fields',s=>s.qualification_fields.join(', ')), segRow('Scoring weights',s=>Object.entries(s.weights).map(([k,v])=>`${k} ${v}`).join(' · ')),
    segRow('Tier thresholds',s=>Object.entries(s.tiers).map(([k,v])=>`${k} ≥ ${v}`).join(' · ')+` · fit gate ${s.fit_gate_for_a}`),
    segRow('Contract template',s=>s.contract_template), segRow('Always needs approval',s=>s.require_approval.join(', ')),
  ].join(''))}<p class="hint" style="margin:14px 0 0"><b>Adding a segment such as Agencies</b> means adding <span class="mono">packs/agency/pack.yaml</span>, its templates and fixtures. No agent or orchestrator code changes. Packs are validated at startup.</p></section>

  <div class="section-title"><span class="n">06</span><h2>Learning loop</h2></div>
  <section class="panel"><div class="loop">${LOOP.map(([t,s])=>`<div class="loop-step"><b>${esc(t)}</b><span>${esc(s)}</span></div>`).join('')}</div><div class="actions" style="margin-top:14px"><a class="button secondary" href="#lessons">Open lesson library</a></div></section>

  <div class="section-title"><span class="n">07</span><h2>Defence in depth</h2></div>
  <div class="grid-2"><section class="panel">${LAYERS.slice(0,4).map((l,i)=>`<div class="layer"><span class="ln">${i+1}</span><div><b>${esc(l[0])}</b><span>${esc(l[1])}</span></div></div>`).join('')}</section><section class="panel">${LAYERS.slice(4).map((l,i)=>`<div class="layer"><span class="ln">${i+5}</span><div><b>${esc(l[0])}</b><span>${esc(l[1])}</span></div></div>`).join('')}</section></div>

  <div class="section-title"><span class="n">08</span><h2>Data model</h2></div>
  <div class="grid-2"><section class="panel">${table(['Table','Purpose'],TABLES.map(t=>`<tr><td class="mono">${esc(t[0])}</td><td>${esc(t[1])}</td></tr>`).join(''))}</section>
  <section class="panel"><h3>Ownership</h3><ul class="checks"><li>HubSpot is the intended source of CRM records; full synchronization is deployment work.</li><li>The operational store owns events, approvals, outbox, scores, lessons and audit.</li><li>The orchestrator owns transitions and qualification checks. CRM edit-conflict handling still needs an integration contract.</li><li>Adapters isolate integrations; a PostgreSQL migration also needs queue and transaction testing.</li></ul></section></div>

  <div class="section-title"><span class="n">09</span><h2>Trade-offs and roadmap</h2></div>
  <section class="panel">${table(['Chose','Over','Why','Cost we accept'],TRADEOFFS.map(t=>`<tr><td><strong>${esc(t[0])}</strong></td><td>${esc(t[1])}</td><td>${esc(t[2])}</td><td class="muted">${esc(t[3])}</td></tr>`).join(''))}
  <h3 style="margin-top:18px">Operational hardening implemented</h3><ul class="checks"><li>Signed normalized events feed a durable worker for leads, replies, transcripts, deliveries and signatures.</li><li>Database claims, bounded retries, recovery controls and SLA timers survive restarts.</li><li>Authenticated operator actions are audited; unsubscribed contacts are blocked at routing and delivery.</li></ul><h3 style="margin-top:18px">Remaining release work</h3><ul class="checks"><li>Verify native provider signatures and map provider payloads at an ingress gateway.</li><li>Connect real research evidence and CRM synchronization; fixtures do not demonstrate external research.</li><li>Confirm the exact approved document is the artifact sent for signature.</li><li>Deploy HTTPS, backups, supervision and alerts. Move to PostgreSQL for multi-host scale.</li></ul></section>
  <div class="actions" style="justify-content:center;margin:26px 0 10px"><a class="button" href="#lab">Open the demo lab →</a></div>`;
}

/* ---------- demo lab ---------- */
const LAB_TABS = [['run','1 · Run pipeline'],['score','2 · Lead scoring'],['policy','3 · Policy gate'],['triage','4 · Reply triage'],['call','5 · Call intelligence'],['io','6 · IO & contract']];
function viewLab() {
  const sys=state.system;
  if(!sys) return `<section class="panel empty">Loading lab...</section>`;
  return `<div class="banner"><strong>Agent runner: ${esc(sys.runner)}.</strong> Every panel calls the production code path: the same scoring function, policy engine, agents, validators and routing used by the pipeline.</div>
  <div class="tabs" role="tablist">${LAB_TABS.map(([k,l])=>`<button type="button" class="tab" role="tab" data-command="lab-tab" data-tab="${k}" aria-selected="${state.labTab===k}">${esc(l)}</button>`).join('')}</div><div id="lab-body">${labBody()}</div>`;
}
function labBody() {
  const t=state.labTab, sys=state.system;
  if(t==='run') return `<div class="lab-grid"><section class="panel"><h2>Run the vertical slice</h2><p class="hint">Sends every fixture through the governed lifecycle and writes the results to this workspace.</p><ol class="steps-list"><li>10 leads (brand and publisher) are ingested as idempotent events, enriched and scored.</li><li>The outreach agent drafts a message for each, using active lessons.</li><li>Policy routes each draft: 2 AUTO, 4 REQUIRE_APPROVAL, 4 DENY.</li><li>An interested reply moves Example Foods to <i>engaged</i>; an injection attempt is flagged.</li><li>The discovery call is digested; exit criteria move the deal to <i>qualified</i> and a lesson is proposed.</li><li>An IO is generated, validated, rendered, and the contract is routed for approval.</li></ol><div class="actions" style="margin-top:16px"><button type="button" class="button" data-command="run-demo">Run demo pipeline</button><button type="button" class="button ghost-danger" data-command="reset-demo">Reset workspace</button></div><p class="hint" style="margin-top:10px">Safe to run more than once: events, approvals and outbox rows are idempotent.</p></section>
  <section class="panel"><h2>Run output</h2><div class="console" id="run-console">${state.lab.runLines?state.lab.runLines.map(consoleLine).join('<br>'):'<span class="dim">$ python -m revenue_system.cli demo  # output appears here</span>'}</div>${state.lab.runLines?`<div class="actions" style="margin-top:12px"><a class="button secondary" href="#pipeline">Pipeline</a><a class="button secondary" href="#approvals">Approvals</a><a class="button secondary" href="#audit">Audit trail</a></div>`:''}</section></div>`;
  if(t==='score') { const s=state.lab.score;
    return `<div class="lab-grid"><section class="panel"><h2>Deterministic lead scoring</h2><p class="hint">The model extracts evidence; these pack-defined rules calculate the score. Move the sliders.</p><div class="field"><label for="score-segment">Segment pack</label><select id="score-segment">${sys.segments.map(x=>`<option value="${esc(x.segment)}" ${x.segment===s.segment?'selected':''}>${esc(x.display_name)}</option>`).join('')}</select></div>${['fit','intent','engagement'].map(k=>`<div class="slider"><label for="score-${k}">${k}</label><input type="range" min="0" max="100" id="score-${k}" data-score="${k}" value="${s[k]}"><input type="number" min="0" max="100" data-score="${k}" value="${s[k]}" aria-label="${k} value"></div>`).join('')}<p class="hint">Fit: ICP match. Intent: buying signals. Engagement: replies, opens and meetings. Before any engagement exists, its weight is redistributed so new leads are not penalised.</p></section><section class="panel" id="score-result">${empty('Calculating...')}</section></div>`; }
  if(t==='policy') { const p=state.lab.policy;
    return `<div class="lab-grid"><section class="panel"><h2>Policy simulator</h2><p class="hint">Calls <span class="mono">PolicyEngine.evaluate()</span> with a simulated deal. The global kill switch is simulated here and is not changed.</p><div class="field"><label for="policy-action">Proposed action</label><select id="policy-action">${['enrich','score','send_first_touch','send_follow_up','change_pricing','generate_io','send_contract'].map(a=>`<option value="${a}" ${a===p.action_type?'selected':''}>${esc(human(a))}</option>`).join('')}</select></div><div class="field"><label>Lead tier</label><div class="segmented">${['A','B','C'].map(x=>`<button type="button" data-command="policy-tier" data-tier="${x}" aria-pressed="${p.tier===x}">Tier ${x}</button>`).join('')}</div></div><label class="checkline"><input type="checkbox" id="policy-injection" ${p.injection_detected?'checked':''}> Payload flagged as prompt injection</label><label class="checkline"><input type="checkbox" id="policy-kill" ${p.kill_switch?'checked':''}> Global kill switch enabled</label></section><section class="panel" id="policy-result">${empty('Evaluating...')}</section></div>`; }
  if(t==='triage') return `<div class="lab-grid"><section class="panel"><h2>Reply triage agent</h2><p class="hint">Inbound email is untrusted. This agent has <b>no tools</b>; it can only return a classification.</p><div class="actions" style="margin-bottom:10px"><button type="button" class="button secondary small" data-command="preset" data-target="triage-text" data-preset="interested">Interested reply</button><button type="button" class="button secondary small" data-command="preset" data-target="triage-text" data-preset="injection">Prompt injection</button></div><textarea id="triage-text" rows="8">${esc(state.lab.triageText ?? sys.fixtures.interested)}</textarea><div class="actions" style="margin-top:12px"><button type="button" class="button" data-command="run-triage">Classify reply</button></div></section><section class="panel" id="triage-result">${state.lab.triage?triageResult(state.lab.triage):empty('Choose a sample or paste a reply, then classify it.')}</section></div>`;
  if(t==='call') return `<div class="lab-grid"><section class="panel"><h2>Call intelligence agent</h2><p class="hint">Digests a Fireflies transcript into the segment's qualification fields, objections, next steps and a lesson candidate.</p><div class="field"><label for="call-segment">Segment pack</label><select id="call-segment">${sys.segments.map(x=>`<option value="${esc(x.segment)}" ${x.segment===(state.lab.callSegment||'brand')?'selected':''}>${esc(x.display_name)} · needs ${esc(x.qualification_fields.join(', '))}</option>`).join('')}</select></div><textarea id="call-text" rows="9">${esc(state.lab.callText ?? sys.fixtures.transcript)}</textarea><div class="actions" style="margin-top:12px"><button type="button" class="button" data-command="run-call">Digest transcript</button></div></section><section class="panel" id="call-result">${state.lab.call?callResult(state.lab.call):empty('Digest the transcript to see extracted deal fields.')}</section></div>`;
  if(t==='io') return ioPanel();
  return '';
}
function consoleLine(line) {
  const m=line.match(/^\[(\w+)\]\s*(.*)$/); if(!m) return esc(line);
  let body=esc(m[2]).replace(/(AUTO|valid=True|lesson_created=True)/g,'<span class="ok">$1</span>').replace(/(REQUIRE_APPROVAL)/g,'<span class="warn">$1</span>').replace(/(DENY|flagged=True|suspicious)/g,'<span class="bad">$1</span>');
  return `<span class="t">[${esc(m[1])}]</span> ${body}`;
}
async function refreshScore() {
  const el=$('#score-result'); if(!el) return;
  try {
    const r=await post('/api/lab/score', state.lab.score); const s=state.lab.score;
    const parts=['fit','intent','engagement'].filter(k=>r.weights[k]!==undefined);
    el.innerHTML=`<div class="big-score"><strong>${num(r.total)}</strong>${badge(r.tier,`Tier ${r.tier}`)}</div><p class="hint">${esc(r.reason)}</p>
    <div class="stack">${parts.map(k=>`<div class="${k}" style="width:${r.contributions[k]}%" title="${k}: ${r.contributions[k]}"></div>`).join('')}</div>
    <div class="thresholds">${Object.entries(r.thresholds).map(([k,v])=>`<span style="left:${v}%">▲ ${k} ${v}</span>`).join('')}</div>
    <div class="legend">${parts.map(k=>`<span><i style="background:${{fit:'#6366f1',intent:'#0ea5e9',engagement:'#10b981'}[k]}"></i>${k} × ${num(r.weights[k],3)} = ${num(r.contributions[k])}</span>`).join('')}</div>
    <div class="formula">${parts.map(k=>`${s[k]} × ${num(r.weights[k],3)}`).join(' + ')} = <b>${num(r.total)}</b></div>
    <ul class="checks" style="margin-top:14px"><li>Tier A needs total ≥ ${r.thresholds.A} <b>and</b> fit ≥ ${r.fit_gate_for_a} (fit gate)</li><li>Tier B needs total ≥ ${r.thresholds.B}</li>${r.engagement_redistributed?'<li>Engagement is 0, so its weight was redistributed across fit and intent</li>':''}<li>Weights come from <span class="mono">packs/${esc(s.segment)}/pack.yaml</span>; no code change to retune</li></ul>`;
  } catch(e) { el.innerHTML=`<p class="form-error">${esc(e.message)}</p>`; }
}
async function refreshPolicy() {
  const el=$('#policy-result'); if(!el) return;
  try {
    const r=await post('/api/lab/policy', state.lab.policy);
    const rules=state.system.policy_rules, hit=rules.findIndex(x=>x.rule_id===r.rule_id);
    el.innerHTML=`<div class="decision-big">${badge(r.decision)}<span class="hint">${esc(r.reason)}</span></div><p class="hint">${r.decision==='AUTO'?'Goes straight to the outbox for delivery.':r.decision==='REQUIRE_APPROVAL'?'Lands in the approval center. Nothing is sent until a human approves.':r.decision==='DENY'?'Blocked and audited. It never reaches the outbox.':'Paused. Nothing routes or delivers until the switch is released.'}</p><div class="rule-list">${rules.map((x,i)=>`<div class="rule ${i===hit?'matched':i<hit?'skipped':''}"><div><strong>${esc(x.when)}</strong><div class="rid">${esc(x.rule_id)}${i<hit?' · not matched':i===hit?' · matched':''}</div></div>${badge(x.decision)}</div>`).join('')}</div>`;
  } catch(e) { el.innerHTML=`<p class="form-error">${esc(e.message)}</p>`; }
}
function triageResult(r) {
  const x=r.result;
  return `<h2>Classification</h2><div class="kv-grid"><div><small>Label</small>${badge(x.label)}</div><div><small>Confidence</small><strong>${num(x.confidence)}</strong></div><div><small>Injection flag</small>${x.injection_detected?badge('deny','detected'):badge('ok','clear')}</div></div><p>${esc(x.summary)}</p>
  ${r.consequence?`<div class="banner error"><strong>If anything tried to act on this reply:</strong> policy returns ${esc(r.consequence.decision)}. ${esc(r.consequence.reason)}.</div>`:''}
  <h3>Tools available to this agent</h3><p>${r.tools.length?r.tools.map(t=>`<span class="chip">${esc(t)}</span>`).join(''):'<span class="no-tools">None. It cannot send, sign or change anything.</span>'}</p>
  <h3>What the model receives</h3><pre class="code">${esc(r.wrapped)}</pre><p class="hint" style="margin-top:8px">Runner: ${esc(r.runner)}. The injection override in <span class="mono">reply_triage.py</span> is deterministic code and applies regardless of what the model returns.</p>`;
}
function callResult(r) {
  const x=r.digest;
  return `<h2>Call digest</h2><p class="hint">Runner: ${esc(r.runner)}</p>${table(['Qualification field','Value','Required'],r.required.map(f=>`<tr><td class="mono">${esc(f)}</td><td>${esc(x.qualification_fields[f]||'—')}</td><td>${x.qualification_fields[f]?badge('ok','captured'):badge('deny','missing')}</td></tr>`).join(''))}
  <div class="banner ${r.exit_criteria_met?'success':'error'}" style="margin-top:12px">${r.exit_criteria_met?'Exit criteria met: the orchestrator may move this deal from meeting to qualified.':`Exit criteria not met: missing ${esc(r.missing.join(', '))}. The deal stays in meeting.`}</div>
  <div class="grid-2"><div><h3>Objections</h3>${x.objections.length?`<ul class="steps-list">${x.objections.map(o=>`<li>${esc(o)}</li>`).join('')}</ul>`:'<p class="hint">None raised.</p>'}</div><div><h3>Next steps</h3>${x.next_steps.length?`<ul class="steps-list">${x.next_steps.map(o=>`<li>${esc(o)}</li>`).join('')}</ul>`:'<p class="hint">None.</p>'}</div></div>
  <h3>Lesson candidate</h3>${x.lesson_candidate?`<div class="message" style="margin:6px 0 10px">${esc(x.lesson_candidate)}</div><button type="button" class="button secondary" data-command="save-lesson">Save as proposed lesson</button>`:'<p class="hint">No reusable insight found.</p>'}`;
}
function ioDefaults() {
  return {deal_id:(state.data?.deals.find(d=>d.id==='lead-brand-001')||state.data?.deals[0]||{}).id||'', legal_entity:'Example Foods', budget:250000, start_date:'2026-11-01', end_date:'2027-01-31', line_items:[{name:'Activate',amount:150000},{name:'Optimize',amount:100000}]};
}
function ioPanel() {
  const io=state.lab.io||(state.lab.io=ioDefaults());
  const deals=state.data?.deals||[];
  return `<div class="lab-grid"><section class="panel"><h2>IO generation and validation</h2><p class="hint">The deal desk agent only maps CRM data into these fields. Trusted upstream numbers override it, deterministic validators check it, and a reviewed template renders it.</p>
  <div class="actions" style="margin-bottom:12px"><button type="button" class="button secondary small" data-command="io-preset" data-preset="valid">Valid IO</button><button type="button" class="button secondary small" data-command="io-preset" data-preset="mismatch">Line items ≠ budget</button><button type="button" class="button secondary small" data-command="io-preset" data-preset="dates">End before start</button></div>
  <div class="field"><label for="io-deal">Deal</label><select id="io-deal" data-io="deal_id">${deals.length?deals.map(d=>`<option value="${esc(d.id)}" ${d.id===io.deal_id?'selected':''}>${esc(d.company)} · ${esc(d.segment)} · ${esc(human(d.stage))}</option>`).join(''):'<option value="">Run the demo pipeline first</option>'}</select></div>
  <div class="grid-2" style="gap:12px"><div class="field"><label for="io-entity">Legal entity</label><input id="io-entity" data-io="legal_entity" value="${esc(io.legal_entity)}"></div><div class="field"><label for="io-budget">Budget (USD)</label><input id="io-budget" type="number" data-io="budget" value="${esc(io.budget)}"></div><div class="field"><label for="io-start">Start date</label><input id="io-start" type="date" data-io="start_date" value="${esc(io.start_date)}"></div><div class="field"><label for="io-end">End date</label><input id="io-end" type="date" data-io="end_date" value="${esc(io.end_date)}"></div></div>
  <label>Line items</label><div class="line-items">${io.line_items.map((li,i)=>`<div class="line-item"><input aria-label="Line item ${i+1} name" data-li="${i}" data-key="name" value="${esc(li.name)}"><input aria-label="Line item ${i+1} amount" type="number" data-li="${i}" data-key="amount" value="${esc(li.amount)}"><button type="button" class="button secondary small" data-command="li-remove" data-index="${i}" aria-label="Remove line item">×</button></div>`).join('')}</div><button type="button" class="button secondary small" data-command="li-add">+ Add line item</button>
  <p class="hint" style="margin-top:10px">Line item total: <b>${num(io.line_items.reduce((t,x)=>t+Number(x.amount||0),0))}</b> · Budget: <b>${num(io.budget)}</b></p>
  <div class="actions" style="margin-top:14px"><button type="button" class="button secondary" data-command="io-validate">Validate and render</button><button type="button" class="button" data-command="io-submit">Request signature</button></div></section>
  <section class="panel" id="io-result">${state.lab.ioResult?ioResult(state.lab.ioResult):empty('Validate the IO to see deterministic checks and the rendered document.')}</section></div>`;
}
function ioResult(r) {
  return r.errors.length?`<h2>Validation failed</h2><p class="hint">These checks are Python in <span class="mono">skills/io_validation.py</span>; the model cannot override them.</p><ul class="steps-list">${r.errors.map(e=>`<li style="color:var(--red)">${esc(e)}</li>`).join('')}</ul><p class="hint" style="margin-top:12px">A contract cannot be routed for signature until validation passes.</p>`
  :`<div class="panel-heading"><div><h2>Rendered insertion order</h2><p class="hint">Template: <span class="mono">${esc(r.template)}</span>. The model never writes legal language.</p></div>${badge('ok','valid')}</div><div class="doc">${esc(r.rendered)}</div><p class="hint" style="margin-top:12px">Request signature routes a <span class="mono">send_contract</span> action through policy. Contracts always require approval; after approval the outbox calls Dropbox Sign (test mode).</p>`;
}

/* ---------- render ---------- */
function renderHeader() {
  const d=state.data; if(!d) return;
  document.querySelectorAll('[data-metric]').forEach(el=>{el.textContent=d.metrics[el.dataset.metric]??0;});
  const counts={approvals:d.metrics.pending_approvals, outbox:d.metrics.outbox_pending, lessons:d.lessons.filter(l=>l.status==='proposed').length};
  $$('[data-nav-count]').forEach(el=>{const n=counts[el.dataset.navCount]; el.textContent=n; el.hidden=!n;});
  const live=d.runtime.mode==='live';
  $('#runtime').className=`status ${live?'live':'replay'}`;
  $('#runtime-text').textContent=`${d.runtime.provider} · ${d.runtime.mode}`;
  $('#runtime-detail').innerHTML=`<span>LLM <b>${esc(d.runtime.provider)}</b></span><span>Mode <b>${esc(d.runtime.mode)}</b></span><span>Mail <b>${esc(d.runtime.mail_mode)}</b></span><span>Side effects <b>${d.runtime.live_side_effects_enabled?'enabled':'off'}</b></span>`;
  $('#emergency').hidden=!d.runtime.kill_switch;
  const k=$('#kill-toggle'); k.textContent=d.runtime.kill_switch?'Resume operations':'Emergency stop'; k.className=`button ${d.runtime.kill_switch?'success':'ghost-danger'}`;
}
function render() {
  const view=selectedView();
  document.querySelectorAll('[data-view]').forEach(a=>a.getAttribute('data-view')===view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));
  $('#page-eyebrow').textContent=titles[view][0]; $('#page-title').textContent=titles[view][1]; $('#page-description').textContent=titles[view][2];
  const present=view==='explain'||view==='lab';
  $('#metrics').hidden=view==='explain'; $('#sync-status').hidden=present;
  renderHeader();
  if(view==='explain') { $('#page-view').innerHTML=viewExplain(); return; }
  if(view==='lab') { $('#page-view').innerHTML=viewLab(); afterLabRender(); return; }
  if(!state.data) { $('#page-view').innerHTML=empty('Loading workspace...'); return; }
  const d=state.data;
  const views={overview:viewOverview,pipeline:viewPipeline,approvals:viewApprovals,outbox:viewOutbox,lessons:viewLessons,audit:viewAudit};
  $('#page-view').innerHTML=views[view](d);
  if(view==='audit'||view==='outbox') $('#page-view').insertAdjacentHTML('beforeend',queueRecovery(d));
  restrictDemoControls();
  if($('#audit-filter')) { $('#audit-filter').value=state.auditFilter; $('#audit-actor').value=state.auditActor; }
}
function afterLabRender() {
  restrictDemoControls();
  if(state.labTab==='score') refreshScore();
  if(state.labTab==='policy') refreshPolicy();
}
function restrictDemoControls() {
  if(state.data?.runtime.demo_enabled===false) {
    $$('[data-command="run-demo"],[data-command="reset-demo"]').forEach(button=>{button.disabled=true;button.title='Demo seeding and reset are disabled in production.';});
  }
}
function queueRecovery(d) {
  const h=d.health||{};
  const failed=[...(d.failed_events||[]).map(x=>({...x,queue:'events'})),...d.outbox.filter(x=>x.last_error).map(x=>({...x,queue:'outbox'}))];
  return `<section class="panel"><h2>Queue health and recovery</h2><p class="hint">Events in progress: ${h.events_processing||0} · Dead events: ${h.events_dead||0} · Deliveries in progress: ${h.outbox_delivering||0} · Failed deliveries: ${h.outbox_failed||0} · SLA timers: ${h.timers_scheduled||0}</p>${failed.length?table(['Queue / item','Status / attempts','Error','Retry after (UTC)','Recovery'],failed.map(x=>`<tr><td>${esc(x.queue)}<small class="mono">${esc(x.id)}</small></td><td>${badge(x.status)}<small>${x.attempts} attempts</small></td><td>${esc(x.last_error)}</td><td>${esc(x.next_attempt_at||'—')}</td><td>${['dead','failed'].includes(x.status)?`<button type="button" class="button secondary small" data-command="queue-retry" data-queue="${x.queue}" data-id="${esc(x.id)}">Schedule retry</button>`:'Waiting for retry'}</td></tr>`).join('')):empty('No failed work. Retries and failures will appear here.')}</section>`;
}
function renderLabBody() { $('#lab-body').innerHTML=labBody(); $$('[data-command=lab-tab]').forEach(b=>b.setAttribute('aria-selected',b.dataset.tab===state.labTab)); afterLabRender(); }
async function load() {
  if(state.loading) return;
  state.loading=true; $('#refresh').disabled=true;
  try {
    state.data=await request('/api/overview');
    // Presenter pages hold form state; refresh only their header, not their content.
    if(LIVE_VIEWS.has(selectedView())) render(); else renderHeader();
    $('#sync-status').textContent=`Updated ${new Date().toLocaleTimeString()} · Refreshes every 10 seconds`;
  } catch(error) { notice(`Unable to refresh: ${error.message}`,true); $('#sync-status').textContent='Connection failed. Last available data remains visible.'; }
  finally {state.loading=false; $('#refresh').disabled=false;}
}
async function loadSystem() {
  try { state.system=await request('/api/system'); if(!LIVE_VIEWS.has(selectedView())) render(); }
  catch(error) { notice(`Unable to load system description: ${error.message}`,true); }
}

/* ---------- review dialog (approvals, outbox) ---------- */
function findReview() {
  const list={approvals:state.data.approvals,history:state.data.approval_history,outbox:state.data.outbox};
  return list[state.review?.kind]?.find(x=>x.id===state.review.id);
}
function openReview(kind,id) {
  state.review={kind,id};
  const item=findReview(); if(!item) return notice('This action changed. Refresh and try again.',true);
  const canDecide=kind==='approvals'&&item.status==='pending';
  const mail=MAIL.includes(item.action_type);
  const canSet=mail&&item.status==='pending'&&(kind==='approvals'||!item.payload.recipient);
  $('#review-title').textContent=`${canDecide?'Review':'Details'}: ${item.company}`;
  const p=item.payload;
  const body=mail?`<div class="message"><h3>${esc(p.subject || 'Subject missing')}</h3><pre>${esc(p.body || 'Message body missing')}</pre></div>`
    :p.document?`<div class="doc" style="margin:12px 0 18px">${esc(p.document)}</div>`:`<div class="message"><pre>${esc(JSON.stringify(p,null,2))}</pre></div>`;
  $('#review-content').innerHTML=`<dl class="details"><div><dt>Account / contact</dt><dd>${esc(item.company)} / ${esc(item.contact)}</dd></div><div><dt>Action / status</dt><dd>${esc(human(item.action_type))} ${badge(item.status)}</dd></div><div><dt>Recipient</dt><dd>${esc(p.recipient || (item.action_type==='send_contract'?'Configured e-signature signer':'Not configured'))}</dd></div><div><dt>Segment / score / tier</dt><dd>${esc(item.segment)} · ${esc(num(item.score))} · ${badge(item.tier)}</dd></div><div><dt>Created (UTC)</dt><dd>${esc(item.created_at)}</dd></div><div><dt>Policy reason</dt><dd>${esc(item.policy_reason)}</dd></div></dl><p class="hint">${esc(item.score_reason)}</p>${p.lessons_used?.length?`<p class="hint">Lessons used: ${p.lessons_used.map(l=>`<span class="chip">${esc(l)}</span>`).join('')}</p>`:''}${p.injection_detected?'<div class="banner error">This payload is flagged as unsafe. It cannot be approved or delivered.</div>':''}${item.rejection_reason?`<div class="banner error">Rejected: ${esc(item.rejection_reason)}</div>`:''}${body}${canSet?`<form id="recipient-form" class="recipient-form"><label for="recipient">Recipient email</label><input id="recipient" type="email" required maxlength="254" value="${esc(p.recipient || '')}" placeholder="Select a configured test recipient"><p class="hint">Allowed for live delivery: ${esc(state.data.runtime.allowed_recipients.join(', ')||'None configured')}. Saving the recipient does not send the message.</p><button type="submit" class="button secondary">Save recipient</button></form>`:''}`;
  $('#rejection-form').hidden=true; $('#rejection-reason').value=''; $('#review-error').hidden=true;
  $('#review-actions').hidden=false;
  $('#review-actions').innerHTML=canDecide?`<button class="button danger" type="button" data-command="reject-form">Reject with reason</button><button class="button" type="button" data-command="approve" ${mail&&(!p.recipient||!p.subject||!p.body)?'disabled':''}>Approve and queue</button>`:'<button class="button secondary" type="button" data-command="close">Done</button>';
  if(!$('#review-dialog').open) $('#review-dialog').showModal();
}
function closeReview(){if(state.busy)return;if($('#review-dialog').open)$('#review-dialog').close();state.review=null;}
async function mutate(url,body={},method='POST') {
  if(state.busy)return false;
  state.busy=true; $('#review-error').hidden=true;
  const buttons=Array.from(document.querySelectorAll('dialog button, [data-command]')).filter(b=>b.tagName==='BUTTON').map(button=>[button,button.disabled]);
  buttons.forEach(([button])=>button.disabled=true);
  try {
    const result=await request(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const failures=result.failures||[];
    notice(result.message+(failures.length?'\n'+failures.map(f=>`${f.id}: ${f.reason}`).join('\n'):''),!!failures.length);
    return result;
  } catch(error) {
    if($('#review-dialog').open){$('#review-error').textContent=error.message;$('#review-error').hidden=false;}else notice(error.message,true);
    return false;
  } finally {state.busy=false;buttons.forEach(([button,disabled])=>button.disabled=disabled);await load();}
}
function openDelivery() {
  const pending=state.data.outbox.filter(x=>x.status==='pending');
  state.review={kind:'batch'}; $('#review-title').textContent='Review delivery batch';
  $('#review-content').innerHTML=`<p>You are about to deliver ${pending.length} queued action(s). Mail mode: <strong>${esc(state.data.runtime.mail_mode)}</strong>.</p>${table(['Account','Action','Recipient'],pending.map(x=>`<tr><td>${esc(x.company)}</td><td>${esc(human(x.action_type))}</td><td>${esc(x.payload.recipient || (x.action_type==='send_contract'?'E-signature signer':'Missing — open action details to set it'))}</td></tr>`).join(''))}<p class="hint">Successful actions are marked sent. Failed actions remain pending and are recorded in the audit trail.</p>`;
  $('#rejection-form').hidden=true;$('#review-error').hidden=true;$('#review-actions').hidden=false;
  const missing=pending.some(x=>MAIL.includes(x.action_type)&&!x.payload.recipient);
  $('#review-actions').innerHTML=`<button class="button secondary" type="button" data-command="close">Cancel</button><button class="button" type="button" data-command="deliver" ${missing||state.data.runtime.kill_switch?'disabled':''}>Deliver approved work</button>`;
  $('#review-dialog').showModal();
}

/* ---------- confirm dialog ---------- */
function confirmAction({eyebrow='Confirm',title,body,ok='Confirm',danger=false,typed=null}) {
  return new Promise(resolve=>{
    const dialog=$('#confirm-dialog');
    $('#confirm-eyebrow').textContent=eyebrow; $('#confirm-title').textContent=title; $('#confirm-body').innerHTML=body;
    $('#confirm-ok').textContent=ok; $('#confirm-ok').className=`button ${danger?'danger':''}`;
    $('#confirm-input-wrap').hidden=!typed; $('#confirm-input').value=''; $('#confirm-input-label').textContent=typed?`Type ${typed} to confirm`:'';
    const finish=value=>{dialog.close();$('#confirm-form').onsubmit=null;$('#confirm-cancel').onclick=null;dialog.oncancel=null;resolve(value);};
    $('#confirm-form').onsubmit=e=>{e.preventDefault(); if(typed&&$('#confirm-input').value.trim()!==typed){$('#confirm-input').focus();return;} finish(true);};
    $('#confirm-cancel').onclick=()=>finish(false); dialog.oncancel=()=>finish(false);
    dialog.showModal(); if(typed) $('#confirm-input').focus();
  });
}

/* ---------- events ---------- */
async function labCall(url, body, key, target) {
  const el=$(target); if(el) el.innerHTML=empty('Running agent...');
  try { state.lab[key]=await post(url, body); }
  catch(e) { state.lab[key]=null; if(el) el.innerHTML=`<p class="form-error">${esc(e.message)}</p>`; return; }
  if(selectedView()==='lab') renderLabBody();
}
function ioBody() { const io=state.lab.io; const deal=state.data?.deals.find(d=>d.id===io.deal_id); return {...io, segment:deal?.segment||'brand', budget:Number(io.budget||0), line_items:io.line_items.map(x=>({name:x.name, amount:Number(x.amount||0)}))}; }
document.addEventListener('click',async event=>{
  const tabLink=event.target.closest('a[data-lab-tab]'); if(tabLink) state.labTab=tabLink.dataset.labTab;
  const button=event.target.closest('[data-command]'); if(!button||state.busy)return;
  const command=button.dataset.command;
  if(command==='review') { event.stopPropagation(); openReview(button.dataset.kind,button.dataset.id); }
  if(command==='close') closeReview();
  if(command==='deal') { if($('#deal-dialog').open && button.tagName==='TR') return; openDeal(button.dataset.id); }
  if(command==='close-deal') $('#deal-dialog').close();
  if(command==='reject-form'){$('#rejection-form').hidden=false;$('#review-actions').hidden=true;$('#rejection-reason').focus();}
  if(command==='approve') {const id=state.review.id;if(await mutate(`/api/approvals/${encodeURIComponent(id)}/approve`))closeReview();}
  if(command==='delivery')openDelivery();
  if(command==='deliver'){if(await mutate('/api/outbox/deliver'))closeReview();}
  if(command==='queue-retry'){
    if(await confirmAction({title:'Retry this failed action?',ok:'Schedule retry',body:'Resolve the reported cause first. The original action identifier is retained; check provider evidence if a previous attempt may have been accepted.'}))
      await mutate(`/api/queues/${button.dataset.queue}/${encodeURIComponent(button.dataset.id)}/retry`);
  }
  if(command==='stage-filter'){state.stageFilter=button.dataset.stage;render();}
  if(command==='lesson') await mutate(`/api/lessons/${encodeURIComponent(button.dataset.id)}/status`,{status:button.dataset.status});
  if(command==='step'){state.step=Math.max(0,Math.min(FLOW.length-1,Number(button.dataset.step)));renderFlow();}
  if(command==='lab-tab'){state.labTab=button.dataset.tab;renderLabBody();}
  if(command==='run-demo') {
    if(selectedView()==='lab'&&$('#run-console')) $('#run-console').innerHTML='<span class="dim">Running pipeline...</span>';
    const result=await mutate('/api/demo/run');
    if(result){state.lab.runLines=result.lines; if(selectedView()==='lab') renderLabBody();}
    else if($('#run-console')) $('#run-console').innerHTML='<span class="bad">Run failed. See the message above.</span>';
  }
  if(command==='reset-demo') {
    if(await confirmAction({eyebrow:'Reset workspace',title:'Clear all workspace data?',danger:true,ok:'Reset workspace',typed:'RESET',body:'This deletes every deal, event, approval, outbox row, lesson and audit entry in the configured database and releases the kill switch. It cannot be undone.'}))
    { const r=await mutate('/api/demo/reset',{confirm:'RESET'}); if(r){state.lab.runLines=null; state.lab.io=null; renderLabBody();} }
  }
  if(command==='policy-tier'){state.lab.policy.tier=button.dataset.tier;$$('[data-command=policy-tier]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.tier===state.lab.policy.tier));refreshPolicy();}
  if(command==='preset'){const t=$('#'+button.dataset.target);t.value=state.system.fixtures[button.dataset.preset];state.lab.triageText=t.value;}
  if(command==='run-triage'){state.lab.triageText=$('#triage-text').value;await labCall('/api/lab/triage',{text:state.lab.triageText},'triage','#triage-result');}
  if(command==='run-call'){state.lab.callText=$('#call-text').value;state.lab.callSegment=$('#call-segment').value;await labCall('/api/lab/call',{text:state.lab.callText,segment:state.lab.callSegment},'call','#call-result');}
  if(command==='save-lesson'){const r=await mutate('/api/lessons',{statement:state.lab.call.digest.lesson_candidate,segment:state.lab.callSegment||'brand',evidence:'demo lab call digest'});if(r)button.disabled=true;}
  if(command==='li-add'){state.lab.io.line_items.push({name:'',amount:0});renderLabBody();}
  if(command==='li-remove'){state.lab.io.line_items.splice(Number(button.dataset.index),1);renderLabBody();}
  if(command==='io-preset'){const io={...ioDefaults(),deal_id:state.lab.io.deal_id};if(button.dataset.preset==='mismatch')io.line_items=[{name:'Activate',amount:150000},{name:'Optimize',amount:60000}];if(button.dataset.preset==='dates'){io.start_date='2027-02-01';io.end_date='2026-11-01';}state.lab.io=io;state.lab.ioResult=null;renderLabBody();}
  if(command==='io-validate'){try{state.lab.ioResult=await post('/api/lab/io',ioBody());renderLabBody();}catch(e){notice(e.message,true);}}
  if(command==='io-submit'){try{state.lab.ioResult=await post('/api/lab/io',ioBody());renderLabBody();if(state.lab.ioResult.errors.length)return notice('Validation failed. Fix the IO before requesting signature.',true);}catch(e){return notice(e.message,true);}await mutate('/api/lab/io/submit',ioBody());}
});
document.addEventListener('submit',async event=>{
  if(event.target.id==='rejection-form') {
    event.preventDefault(); const reason=$('#rejection-reason').value.trim();
    if(!reason){$('#review-error').textContent='Please explain why this action should be rejected.';$('#review-error').hidden=false;return;}
    if(await mutate(`/api/approvals/${encodeURIComponent(state.review.id)}/reject`,{reason}))closeReview();
  }
  if(event.target.id==='recipient-form') {
    event.preventDefault();const {kind,id}=state.review;
    if(await mutate(`/api/${kind}/${encodeURIComponent(id)}/recipient`,{recipient:$('#recipient').value.trim()},'PATCH'))openReview(kind,id);
  }
});
let scoreTimer;
document.addEventListener('input',event=>{
  const t=event.target;
  if(t.id==='pipeline-search'){state.search=t.value;$('#pipeline-results').innerHTML=pipeline(filteredDeals(state.data));}
  if(t.dataset.score){state.lab.score[t.dataset.score]=Math.max(0,Math.min(100,Number(t.value)||0));$$(`[data-score=${t.dataset.score}]`).forEach(x=>{if(x!==t)x.value=state.lab.score[t.dataset.score];});clearTimeout(scoreTimer);scoreTimer=setTimeout(refreshScore,120);}
  if(t.dataset.io&&state.lab.io){state.lab.io[t.dataset.io]=t.value;}
  if(t.dataset.li!==undefined&&state.lab.io){state.lab.io.line_items[Number(t.dataset.li)][t.dataset.key]=t.value;}
});
document.addEventListener('change',event=>{
  const t=event.target;
  if(t.id==='audit-filter'||t.id==='audit-actor'){state.auditFilter=$('#audit-filter').value;state.auditActor=$('#audit-actor').value;$('#audit-results').innerHTML=audit(filteredAudit(state.data));}
  if(t.id==='score-segment'){state.lab.score.segment=t.value;refreshScore();}
  if(t.id==='policy-action'){state.lab.policy.action_type=t.value;refreshPolicy();}
  if(t.id==='policy-injection'){state.lab.policy.injection_detected=t.checked;refreshPolicy();}
  if(t.id==='policy-kill'){state.lab.policy.kill_switch=t.checked;refreshPolicy();}
  if(t.dataset.io==='deal_id'||t.dataset.li!==undefined||t.dataset.io==='budget') renderLabBody();
});
document.addEventListener('keydown',event=>{
  if(selectedView()!=='explain'||document.querySelector('dialog[open]')||['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)) return;
  if(event.key==='ArrowRight'&&state.step<FLOW.length-1){state.step++;renderFlow();}
  if(event.key==='ArrowLeft'&&state.step>0){state.step--;renderFlow();}
});
$('#kill-toggle').addEventListener('click',async()=>{
  if(!state.data||state.busy) return;
  const on=!state.data.runtime.kill_switch;
  const ok=await confirmAction(on?{eyebrow:'Emergency stop',title:'Pause all automated actions?',danger:true,ok:'Enable emergency stop',body:'Policy will route every new action to KILL_SWITCH and delivery will refuse to send. Queued work stays pending and nothing is lost.'}
    :{eyebrow:'Resume',title:'Resume operations?',ok:'Resume operations',body:'Policy routing and outbox delivery will work normally again.'});
  if(ok) await mutate('/api/kill-switch',{enabled:on});
});
$('#close-review').addEventListener('click',closeReview);
$('#review-dialog').addEventListener('cancel',event=>{if(state.busy)event.preventDefault();else state.review=null;});
$('#cancel-rejection').addEventListener('click',()=>{$('#rejection-form').hidden=true;$('#review-actions').hidden=false;$('#review-error').hidden=true;});
$('#refresh').addEventListener('click',load);
window.addEventListener('hashchange',()=>{closeReview();if($('#deal-dialog').open)$('#deal-dialog').close();render();window.scrollTo(0,0);});
// One refresh owner. Do not replace review content or draft rejection reasons while editing.
setInterval(()=>{if(!state.busy&&!document.querySelector('dialog[open]'))load();},10000);
render();load();loadSystem();
