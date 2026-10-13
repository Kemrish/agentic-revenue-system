'use strict';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge = value => `<span class="badge ${String(value).toLowerCase().replace(/[^a-z_]/g, '')}">${esc(value)}</span>`;
const titles = {
  overview: ['Revenue command center', 'Observe proposals, govern risk, and trace approved work.'],
  pipeline: ['Pipeline workspace', 'Inspect accounts, qualification evidence, scores, and lifecycle stages.'],
  approvals: ['Approval center', 'Review the exact recipient and message before deciding.'],
  outbox: ['Outbox operations', 'Inspect queued work, deliver permitted actions, and track the results.'],
  audit: ['Audit trail', 'Trace scoring, decisions, rejection reasons, and provider delivery.'],
};
const state = {data:null, loading:false, busy:false, review:null, search:'', auditFilter:''};
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
function pipeline(deals) {
  if(!deals.length) return empty('No deals match this view.');
  return table(['Account / contact','Segment','Score / tier','Stage','Evidence'], deals.map(d=>`<tr><td><strong>${esc(d.company)}</strong><small>${esc(d.contact)}</small><small>${esc(d.id)}</small></td><td>${esc(d.segment)}</td><td>${esc(d.score)} ${badge(d.tier)}</td><td>${esc(d.stage)}</td><td>${esc(d.score_reason)}<details><summary>Lead details</summary><pre class="mono">${esc(JSON.stringify(d.fields,null,2))}</pre></details></td></tr>`).join(''));
}
function reviewButton(kind, id, label='Review details') {
  return `<button type="button" class="button secondary" data-command="review" data-kind="${kind}" data-id="${esc(id)}">${label}</button>`;
}
function approvals(items) {
  return items.length?items.map(item=>`<div class="row"><div><strong>${esc(item.company)}</strong><p>${esc(item.contact)} · ${esc(item.action_type)}</p><p>To: ${esc(item.payload.recipient || 'Recipient required')}</p><p>${esc(item.payload.subject || 'No subject')}</p><p>${esc(item.policy_reason)}</p></div>${reviewButton('approvals',item.id)}</div>`).join(''):empty('No pending approvals. Decided requests appear in the history below.');
}
function audit(items) {
  return items.length?table(['Time (UTC)','Actor','Action','Deal','Detail'], items.map(a=>`<tr><td>${esc(a.created_at)}</td><td>${esc(a.actor)}</td><td>${badge(a.action)}</td><td>${esc(a.deal_id || 'System')}</td><td>${esc(a.detail)}</td></tr>`).join('')):empty('No audit events match this view.');
}
function policies(data) {
  return data.scenarios.map(s=>`<div class="row"><div><strong>${esc(s.name)}</strong><p>${esc(s.reason)}</p></div>${badge(s.decision)}</div>`).join('');
}
function render() {
  const view=selectedView();
  document.querySelectorAll('[data-view]').forEach(a=>a.getAttribute('data-view')===view?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));
  $('#page-title').textContent=titles[view][0]; $('#page-description').textContent=titles[view][1];
  if(!state.data) { $('#page-view').innerHTML=empty('Loading workspace...'); return; }
  const d=state.data;
  // These five cards exist once in the document. Refresh only changes their text.
  document.querySelectorAll('[data-metric]').forEach(el=>{el.textContent=d.metrics[el.dataset.metric]??0;});
  $('#runtime').textContent=`${d.runtime.provider} · ${d.runtime.mode}`;
  $('#emergency').hidden=!d.runtime.kill_switch;
  if(view==='overview') $('#page-view').innerHTML=`<div class="columns"><div><section class="panel"><div class="panel-heading"><div><h2>Pipeline and qualification</h2><p class="hint">Persisted deals and deterministic scores.</p></div><a class="button secondary" href="#pipeline">View pipeline</a></div>${pipeline(d.deals.slice(0,5))}</section><section class="panel"><h2>Recent audit activity</h2>${audit(d.audit.slice(0,6))}</section></div><div><section class="panel"><h2>Pending reviews</h2>${approvals(d.approvals.slice(0,3))}</section><section class="panel"><h2>Policy reference</h2><p class="hint">Rule descriptions. Actual decisions appear in the audit trail.</p>${policies(d)}</section></div></div>`;
  if(view==='pipeline') $('#page-view').innerHTML=`<section class="panel"><div class="panel-heading"><div><h2>All deals</h2><p class="hint">${d.deals.length} accounts in this workspace.</p></div><input class="search" id="pipeline-search" aria-label="Search pipeline" placeholder="Search account, contact, or segment" value="${esc(state.search)}"></div><div id="pipeline-results">${pipeline(d.deals.filter(x=>`${x.company} ${x.contact} ${x.segment}`.toLowerCase().includes(state.search.toLowerCase())))}</div></section>`;
  if(view==='approvals') $('#page-view').innerHTML=`<section class="panel"><h2>Pending approvals</h2><p class="hint">Open a proposal to inspect the recipient, full message, score, and policy reason.</p>${approvals(d.approvals)}</section><section class="panel"><h2>Decision history</h2><p class="hint">Rejections retain the operator's explanation.</p>${d.approval_history.length?table(['Account','Action','Decision','Reason','Details'],d.approval_history.map(x=>`<tr><td>${esc(x.company)}</td><td>${esc(x.action_type)}</td><td>${badge(x.status)}</td><td>${esc(x.rejection_reason || 'Approved for delivery')}</td><td>${reviewButton('history',x.id,'View decision')}</td></tr>`).join('')):empty('No decisions yet.')}</section>`;
  if(view==='outbox') {
    const pending=d.outbox.filter(x=>x.status==='pending');
    $('#page-view').innerHTML=`<section class="panel"><div class="panel-heading"><div><h2>Delivery queue and history</h2><p class="hint">Mail: ${esc(d.runtime.mail_mode)} · External sending ${d.runtime.live_side_effects_enabled?'enabled':'disabled'}. Review recipients before delivery.</p></div><button class="button" type="button" data-command="delivery" ${!pending.length||state.busy||d.runtime.kill_switch?'disabled':''}>${state.busy?'Working...':'Review delivery batch'}</button></div>${d.outbox.length?table(['Account','Action','Recipient','Status','Details'],d.outbox.map(x=>`<tr><td>${esc(x.company)}<small>${esc(x.deal_id)}</small></td><td>${esc(x.action_type)}</td><td>${esc(x.payload.recipient || 'Recipient required')}</td><td>${badge(x.status)}</td><td>${reviewButton('outbox',x.id)}</td></tr>`).join('')):empty('No queued or delivered actions.')}</section>`;
  }
  if(view==='audit') $('#page-view').innerHTML=`<section class="panel"><div class="panel-heading"><div><h2>Audit evidence</h2><p class="hint">Showing the latest ${d.audit.length} events. Total: ${d.metrics.audit_events}.</p></div><select id="audit-filter" aria-label="Filter audit events"><option value="">All events</option><option value="approval_rejected">Rejections</option><option value="outbox_failed">Delivery failures</option><option value="outbox_sent">Successful deliveries</option><option value="DENY">Policy denials</option><option value="KILL_SWITCH">Emergency stops</option></select></div><div id="audit-results">${audit(d.audit.filter(x=>!state.auditFilter||x.action===state.auditFilter))}</div></section>`;
  if($('#audit-filter')) $('#audit-filter').value=state.auditFilter;
}
async function load() {
  if(state.loading) return;
  state.loading=true; $('#refresh').disabled=true;
  try {
    state.data=await request('/api/overview');
    render(); $('#sync-status').textContent=`Updated ${new Date().toLocaleTimeString()} · Refreshes every 10 seconds`;
  } catch(error) { notice(`Unable to refresh: ${error.message}`,true); $('#sync-status').textContent='Connection failed. Last available data remains visible.'; }
  finally {state.loading=false; $('#refresh').disabled=false;}
}
function findReview() {
  const list={approvals:state.data.approvals,history:state.data.approval_history,outbox:state.data.outbox};
  return list[state.review?.kind]?.find(x=>x.id===state.review.id);
}
function openReview(kind,id) {
  state.review={kind,id};
  const item=findReview(); if(!item) return notice('This action changed. Refresh and try again.',true);
  const canDecide=kind==='approvals'&&item.status==='pending';
  const mail=['send_first_touch','send_follow_up'].includes(item.action_type);
  const canSet=mail&&item.status==='pending'&&(kind==='approvals'||!item.payload.recipient);
  $('#review-title').textContent=`${canDecide?'Review':'Details'}: ${item.company}`;
  const p=item.payload;
  $('#review-content').innerHTML=`<dl class="details"><div><dt>Account / contact</dt><dd>${esc(item.company)} / ${esc(item.contact)}</dd></div><div><dt>Action / status</dt><dd>${esc(item.action_type)} ${badge(item.status)}</dd></div><div><dt>Recipient</dt><dd>${esc(p.recipient || 'Not configured')}</dd></div><div><dt>Segment / score / tier</dt><dd>${esc(item.segment)} · ${esc(item.score)} · ${esc(item.tier)}</dd></div><div><dt>Created (UTC)</dt><dd>${esc(item.created_at)}</dd></div><div><dt>Policy reason</dt><dd>${esc(item.policy_reason)}</dd></div></dl><p class="hint">${esc(item.score_reason)}</p>${item.rejection_reason?`<div class="banner error">Rejected: ${esc(item.rejection_reason)}</div>`:''}${mail?`<div class="message"><h3>${esc(p.subject || 'Subject missing')}</h3><pre>${esc(p.body || 'Message body missing')}</pre></div>`:`<div class="message"><pre>${esc(JSON.stringify(p,null,2))}</pre></div>`}${canSet?`<form id="recipient-form" class="recipient-form"><label for="recipient">Recipient email</label><input id="recipient" type="email" required maxlength="254" value="${esc(p.recipient || '')}" placeholder="Select a configured test recipient"><p class="hint">Allowed for live delivery: ${esc(state.data.runtime.allowed_recipients.join(', ')||'None configured')}. Saving the recipient does not send the message.</p><button type="submit" class="button secondary">Save recipient</button></form>`:''}`;
  $('#rejection-form').hidden=true; $('#rejection-reason').value=''; $('#review-error').hidden=true;
  $('#review-actions').hidden=false;
  $('#review-actions').innerHTML=canDecide?`<button class="button danger" type="button" data-command="reject-form">Reject with reason</button><button class="button" type="button" data-command="approve" ${mail&&(!p.recipient||!p.subject||!p.body)?'disabled':''}>Approve and queue</button>`:'<button class="button secondary" type="button" data-command="close">Done</button>';
  if(!$('#review-dialog').open) $('#review-dialog').showModal();
}
function closeReview(){if(state.busy)return;$('#review-dialog').close();state.review=null;}
async function mutate(url,body={},method='POST') {
  if(state.busy)return false;
  state.busy=true; $('#review-error').hidden=true;
  const buttons=Array.from(document.querySelectorAll('dialog button')).map(button=>[button,button.disabled]);
  buttons.forEach(([button])=>button.disabled=true);
  try {
    const result=await request(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const failures=result.failures||[];
    notice(result.message+(failures.length?'\n'+failures.map(f=>`${f.id}: ${f.reason}`).join('\n'):''),!!failures.length);
    return true;
  } catch(error) {
    if($('#review-dialog').open){$('#review-error').textContent=error.message;$('#review-error').hidden=false;}else notice(error.message,true);
    return false;
  } finally {state.busy=false;buttons.forEach(([button,disabled])=>button.disabled=disabled);await load();}
}
function openDelivery() {
  const pending=state.data.outbox.filter(x=>x.status==='pending');
  state.review={kind:'batch'}; $('#review-title').textContent='Review delivery batch';
  $('#review-content').innerHTML=`<p>You are about to deliver ${pending.length} queued action(s). Mail mode: <strong>${esc(state.data.runtime.mail_mode)}</strong>.</p>${table(['Account','Action','Recipient'],pending.map(x=>`<tr><td>${esc(x.company)}</td><td>${esc(x.action_type)}</td><td>${esc(x.payload.recipient || 'Missing — open action details to set it')}</td></tr>`).join(''))}<p class="hint">Successful actions are marked sent. Failed actions remain pending and are recorded in the audit trail.</p>`;
  $('#rejection-form').hidden=true;$('#review-error').hidden=true;$('#review-actions').hidden=false;
  const missing=pending.some(x=>['send_first_touch','send_follow_up'].includes(x.action_type)&&!x.payload.recipient);
  $('#review-actions').innerHTML=`<button class="button secondary" type="button" data-command="close">Cancel</button><button class="button" type="button" data-command="deliver" ${missing||state.data.runtime.kill_switch?'disabled':''}>Deliver approved work</button>`;
  $('#review-dialog').showModal();
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-command]'); if(!button||state.busy)return;
  const command=button.dataset.command;
  if(command==='review') openReview(button.dataset.kind,button.dataset.id);
  if(command==='close') closeReview();
  if(command==='reject-form'){$('#rejection-form').hidden=false;$('#review-actions').hidden=true;$('#rejection-reason').focus();}
  if(command==='approve') {const id=state.review.id;if(await mutate(`/api/approvals/${encodeURIComponent(id)}/approve`))closeReview();}
  if(command==='delivery')openDelivery();
  if(command==='deliver'){if(await mutate('/api/outbox/deliver'))closeReview();}
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
document.addEventListener('input',event=>{if(event.target.id==='pipeline-search'){state.search=event.target.value;$('#pipeline-results').innerHTML=pipeline(state.data.deals.filter(x=>`${x.company} ${x.contact} ${x.segment}`.toLowerCase().includes(state.search.toLowerCase())));}});
document.addEventListener('change',event=>{if(event.target.id==='audit-filter'){state.auditFilter=event.target.value;$('#audit-results').innerHTML=audit(state.data.audit.filter(x=>!state.auditFilter||x.action===state.auditFilter));}});
$('#close-review').addEventListener('click',closeReview);
$('#review-dialog').addEventListener('cancel',event=>{if(state.busy)event.preventDefault();else state.review=null;});
$('#cancel-rejection').addEventListener('click',()=>{$('#rejection-form').hidden=true;$('#review-actions').hidden=false;$('#review-error').hidden=true;});
$('#refresh').addEventListener('click',load);
window.addEventListener('hashchange',()=>{closeReview();render();});
// One refresh owner. Do not replace review content or draft rejection reasons while editing.
setInterval(()=>{if(!state.busy&&!$('#review-dialog').open)load();},10000);
render();load();
