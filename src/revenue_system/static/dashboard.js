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
  overview: ['Operate', 'Revenue command center', 'Observe proposals, govern risk, and trace approved work.'],
  pipeline: ['Operate', 'Pipeline workspace', 'Inspect accounts, qualification evidence, scores, and lifecycle stages.'],
  approvals: ['Operate', 'Approval center', 'Review the exact recipient and message before deciding.'],
  outbox: ['Operate', 'Outbox operations', 'Inspect queued work, deliver permitted actions, and track the results.'],
  lessons: ['Operate', 'Lesson library', 'Curate what the system learns from calls and rejections before agents may use it.'],
  audit: ['Operate', 'Audit trail', 'Trace scoring, decisions, rejection reasons, and provider delivery.'],
};
const state = {data:null, loading:false, busy:false, review:null, search:'', stageFilter:'', auditFilter:'', auditActor:''};
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
  return `<section class="panel hero-empty"><div class="eyebrow">Workspace ready</div><h2>Ready for incoming leads</h2><p>Import lead data or connect the signed event gateway, then run the event worker.</p></section>`;
}

/* ---------- operate views ---------- */
function viewOverview(d) {
  if(!d.deals.length) return emptyWorkspace();
  const stages=MAIN_PATH.filter(s=>d.stage_counts[s]).map(s=>[s,d.stage_counts[s]]);
  if(d.stage_counts.closed_lost) stages.push(['closed_lost',d.stage_counts.closed_lost]);
  const pd=d.policy_decisions||{};
  const decisions=['AUTO','REQUIRE_APPROVAL','DENY','KILL_SWITCH'].map(k=>[k,pd[k]||0]);
  return `<div class="grid-2"><section class="panel"><div class="panel-heading"><div><h2>Pipeline by stage</h2><p class="hint">Stages are owned by the orchestrator's state machine.</p></div><a class="button secondary small" href="#pipeline">View pipeline</a></div>${bars(stages)}</section>
  <section class="panel"><div class="panel-heading"><div><h2>Policy decisions</h2><p class="hint">Every proposed action, routed by code.</p></div></div>${bars(decisions,true)}<p class="hint" style="margin:14px 0 0">${d.scenarios.map(s=>`<b>${esc(human(s.decision))}</b>: ${esc(s.reason)}`).join('<br>')}</p></section></div>
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
  return `<section class="panel"><div class="panel-heading"><div><h2>Delivery queue and history</h2><p class="hint">Mail: ${esc(d.runtime.mail_mode)} · External sending ${d.runtime.live_side_effects_enabled?'enabled':'disabled'}. Rows are marked sent only after the provider confirms.</p></div><button class="button" type="button" data-command="delivery" ${!pending.length||state.busy||d.runtime.kill_switch?'disabled':''}>${state.busy?'Working...':'Review delivery batch'}</button></div>${d.outbox.length?table(['Account','Action','Recipient','Status','Details'],d.outbox.map(x=>`<tr><td>${esc(x.company)}<small class="mono">${esc(x.deal_id)}</small></td><td>${esc(human(x.action_type))}</td><td>${esc(x.payload.recipient || x.payload.signer_email || (x.action_type==='sync_crm'?'CRM contact':'Recipient required'))}</td><td>${badge(x.status)}</td><td>${reviewButton('outbox',x.id)}</td></tr>`).join('')):empty('No queued or delivered actions.')}</section>`;
}
function viewLessons(d) {
  const counts={proposed:0,active:0,retired:0}; d.lessons.forEach(l=>counts[l.status]=(counts[l.status]||0)+1);
  const actionsFor=l=>l.status==='proposed'?`<button class="button success small" data-command="lesson" data-id="${esc(l.id)}" data-status="active">Promote</button> <button class="button danger small" data-command="lesson" data-id="${esc(l.id)}" data-status="retired">Retire</button>`:l.status==='active'?`<button class="button danger small" data-command="lesson" data-id="${esc(l.id)}" data-status="retired">Retire</button>`:`<button class="button secondary small" data-command="lesson" data-id="${esc(l.id)}" data-status="proposed">Restore</button>`;
  return `<section class="panel"><div class="panel-heading"><div><h2>How the learning loop works</h2><p class="hint">Call transcripts and rejection reasons create <b>proposed</b> lessons. Only <b>active</b> lessons are retrieved by the outreach agent, and every draft records which ones it used in <span class="mono">lessons_used</span>. Promotion is a human step so untrusted text never becomes an instruction automatically.</p></div></div><div class="kv-grid"><div><small>Proposed</small><strong>${counts.proposed}</strong></div><div><small>Active</small><strong>${counts.active}</strong></div><div><small>Retired</small><strong>${counts.retired||0}</strong></div></div></section>
  <section class="panel"><h2>Lessons</h2><p class="hint">Active lessons are retrieved when new outreach proposals are drafted.</p>${d.lessons.length?table(['Lesson','Scope','Status','Evidence','Actions'],d.lessons.map(l=>`<tr><td><strong>${esc(l.statement)}</strong><small class="mono">${esc(l.id)}</small></td><td>${esc(l.segment)}</td><td>${badge(l.status)}</td><td>${(l.evidence||[]).map(e=>`<span class="chip">${esc(e)}</span>`).join('')}</td><td style="white-space:nowrap">${actionsFor(l)}</td></tr>`).join('')):empty('No lessons yet. Process a call transcript or capture an operator rejection to propose one.')}</section>`;
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
  renderHeader();
  if(!state.data) { $('#page-view').innerHTML=empty('Loading workspace...'); return; }
  const d=state.data;
  const views={overview:viewOverview,pipeline:viewPipeline,approvals:viewApprovals,outbox:viewOutbox,lessons:viewLessons,audit:viewAudit};
  $('#page-view').innerHTML=views[view](d);
  if(view==='audit'||view==='outbox') $('#page-view').insertAdjacentHTML('beforeend',queueRecovery(d));
  if($('#audit-filter')) { $('#audit-filter').value=state.auditFilter; $('#audit-actor').value=state.auditActor; }
}
function queueRecovery(d) {
  const h=d.health||{};
  const failed=[...(d.failed_events||[]).map(x=>({...x,queue:'events'})),...d.outbox.filter(x=>x.last_error).map(x=>({...x,queue:'outbox'}))];
  return `<section class="panel"><h2>Queue health and recovery</h2><p class="hint">Events in progress: ${h.events_processing||0} · Dead events: ${h.events_dead||0} · Deliveries in progress: ${h.outbox_delivering||0} · Failed deliveries: ${h.outbox_failed||0} · SLA timers: ${h.timers_scheduled||0}</p>${failed.length?table(['Queue / item','Status / attempts','Error','Retry after (UTC)','Recovery'],failed.map(x=>`<tr><td>${esc(x.queue)}<small class="mono">${esc(x.id)}</small></td><td>${badge(x.status)}<small>${x.attempts} attempts</small></td><td>${esc(x.last_error)}</td><td>${esc(x.next_attempt_at||'—')}</td><td>${['dead','failed'].includes(x.status)?`<button type="button" class="button secondary small" data-command="queue-retry" data-queue="${x.queue}" data-id="${esc(x.id)}">Schedule retry</button>`:'Waiting for retry'}</td></tr>`).join('')):empty('No failed work. Retries and failures will appear here.')}</section>`;
}
async function load() {
  if(state.loading) return;
  state.loading=true; $('#refresh').disabled=true;
  try {
    state.data=await request('/api/overview');
    render();
    $('#sync-status').textContent=`Updated ${new Date().toLocaleTimeString()} · Refreshes every 10 seconds`;
  } catch(error) { notice(`Unable to refresh: ${error.message}`,true); $('#sync-status').textContent='Connection failed. Last available data remains visible.'; }
  finally {state.loading=false; $('#refresh').disabled=false;}
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
    :p.document?`<dl class="details"><div><dt>Signer</dt><dd>${esc(p.signer_name || 'Missing')} &lt;${esc(p.signer_email || 'Missing')}&gt;</dd></div><div><dt>Document SHA-256</dt><dd class="mono">${esc(p.artifact_sha256 || 'Unbound legacy contract — regenerate before approval')}</dd></div></dl>${p.artifact_sha256?`<a class="button secondary" href="/api/${kind==='history'?'approvals':kind}/${encodeURIComponent(id)}/document">Download reviewed DOCX</a>`:''}<div class="doc" style="margin:12px 0 18px">${esc(p.document)}</div>`:`<div class="message"><pre>${esc(JSON.stringify(p,null,2))}</pre></div>`;
  $('#review-content').innerHTML=`<dl class="details"><div><dt>Account / contact</dt><dd>${esc(item.company)} / ${esc(item.contact)}</dd></div><div><dt>Action / status</dt><dd>${esc(human(item.action_type))} ${badge(item.status)}</dd></div><div><dt>Recipient</dt><dd>${esc(p.recipient || p.signer_email || 'Not configured')}</dd></div><div><dt>Segment / score / tier</dt><dd>${esc(item.segment)} · ${esc(num(item.score))} · ${badge(item.tier)}</dd></div><div><dt>Created (UTC)</dt><dd>${esc(item.created_at)}</dd></div><div><dt>Policy reason</dt><dd>${esc(item.policy_reason)}</dd></div></dl><p class="hint">${esc(item.score_reason)}</p>${p.lessons_used?.length?`<p class="hint">Lessons used: ${p.lessons_used.map(l=>`<span class="chip">${esc(l)}</span>`).join('')}</p>`:''}${p.injection_detected?'<div class="banner error">This payload is flagged as unsafe. It cannot be approved or delivered.</div>':''}${item.rejection_reason?`<div class="banner error">Rejected: ${esc(item.rejection_reason)}</div>`:''}${body}${canSet?`<form id="recipient-form" class="recipient-form"><label for="recipient">Recipient email</label><input id="recipient" type="email" required maxlength="254" value="${esc(p.recipient || '')}" placeholder="Select a configured test recipient"><p class="hint">Allowed for live delivery: ${esc(state.data.runtime.allowed_recipients.join(', ')||'None configured')}. Saving the recipient does not send the message.</p><button type="submit" class="button secondary">Save recipient</button></form>`:''}`;
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
  $('#review-content').innerHTML=`<p>You are about to deliver ${pending.length} queued action(s). Mail mode: <strong>${esc(state.data.runtime.mail_mode)}</strong>.</p>${table(['Account','Action','Recipient'],pending.map(x=>`<tr><td>${esc(x.company)}</td><td>${esc(human(x.action_type))}</td><td>${esc(x.payload.recipient || x.payload.signer_email || (x.action_type==='sync_crm'?'CRM contact':'Missing — open action details to set it'))}</td></tr>`).join(''))}<p class="hint">Successful actions are marked sent. Failed actions remain pending and are recorded in the audit trail.</p>`;
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
document.addEventListener('click',async event=>{
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
document.addEventListener('input',event=>{
  const t=event.target;
  if(t.id==='pipeline-search'){state.search=t.value;$('#pipeline-results').innerHTML=pipeline(filteredDeals(state.data));}
});
document.addEventListener('change',event=>{
  const t=event.target;
  if(t.id==='audit-filter'||t.id==='audit-actor'){state.auditFilter=$('#audit-filter').value;state.auditActor=$('#audit-actor').value;$('#audit-results').innerHTML=audit(filteredAudit(state.data));}
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
render();load();
