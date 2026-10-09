'use strict';
// Uses the supervisor's existing same-origin API and CSRF token.
let observed={subjects:[]}, auditEvents=[],auditCursor=0,auditSubject='factory',auditTab='timeline',auditEpoch=0,comparisonEpoch=0;
const pretty=value=>JSON.stringify(value,null,2);
function verdict(status){return `<span class="badge tone-${status==='pass'?'green':status==='fail'||status==='error'?'red':'neutral'}">${esc(status||'unknown')}</span>`}
async function loadObservatory(){
  observed=await api('/api/observability');
  $('#audit-connection').textContent=`Collector ${observed.collector.state} · last success ${observed.collector.lastSuccessAt?new Date(observed.collector.lastSuccessAt).toLocaleTimeString():'not yet'}`;
  const role=$('#audit-role').value;
  const subjects=observed.subjects.filter(s=>!role||s.role===role);
  $('#audit-subject').innerHTML=(!role?'<option value="factory">Factory supervisor</option>':'')+subjects.map(s=>`<option value="${esc(s.id)}">${esc(s.role)} · ${esc(s.title||s.id)}${s.executionKind?' · probe':''}</option>`).join('');
  if([...$('#audit-subject').options].some(o=>o.value===auditSubject))$('#audit-subject').value=auditSubject;
  else auditSubject=$('#audit-subject').value;
  $('#run-probe').disabled=observed.benchmarkRunning;
  $('#probe-status').textContent=observed.benchmarkRunning?'A real role probe is running. Refresh to inspect its result.':'Consumes your selected provider’s allowance. One probe at a time; 10 minute limit.';
  renderRelations();
}
function renderRelations(){
  const s=observed.subjects.find(x=>x.id===auditSubject),related=observed.subjects.filter(x=>x.parentId===auditSubject);
  $('#run-evidence').disabled=!s;
  $('#audit-relations').innerHTML=s?`<div class="trace-summary"><div><span class="tag">${esc(s.role)}</span> <span class="tag agent">${esc(agentLabel(s.harness))}</span> <code>${esc(s.id)}</code></div><small>Model: ${esc(s.model||s.settings?.model||'not reported')} · Native status: ${esc(s.status||'not reported')}</small><p>Conversation coverage: ${esc(s.conversationCoverage||'not available for this component')}${s.coverageError?` · ${esc(s.coverageError)}`:''}</p>${s.parentId?`<p>Linked parent: <button class="text-button" data-audit-subject="${esc(s.parentId)}">${esc(s.parentId)}</button><small>${esc(s.parentEvidence||'Native review/component or benchmark link')}</small></p>`:''}${related.length?`<div class="trace-children">${related.map(x=>`<button class="secondary" data-audit-subject="${esc(x.id)}">${esc(x.role)} · ${esc(x.title||x.id)}</button>`).join('')}</div>`:''}<small>Same project does not imply delegation. Parent links show their provenance.</small></div>`:'<p>Supervisor requests and outcomes, correlated with native actions.</p>';
  bindSubjectLinks();
}
function bindSubjectLinks(){document.querySelectorAll('[data-audit-subject]').forEach(b=>b.onclick=async()=>{auditSubject=b.dataset.auditSubject;$('#audit-role').value='';await loadObservatory();await loadAudit(true)})}
async function loadAudit(reset=false){
  const epoch=++auditEpoch,subject=auditSubject;
  if(reset){auditEvents=[];auditCursor=0}
  if(!subject){renderAudit();if(auditTab==='evals')await loadEvals();return}
  const d=await api(`/api/audit?subject=${encodeURIComponent(subject)}&after=${auditCursor}&limit=100&scope=${$('#audit-trace').checked?'trace':'agent'}`);
  if(epoch!==auditEpoch||subject!==auditSubject)return;
  auditEvents.push(...d.events);auditCursor=d.nextCursor;
  $('#audit-more').hidden=!d.hasMore;
  renderAudit();
  if(auditTab==='evals')await loadEvals();
}
function renderAudit(){
  const kind=$('#audit-kind').value.toLowerCase(),query=$('#audit-search').value.toLowerCase();
  const rows=auditEvents.filter(e=>e.kind.toLowerCase().includes(kind)&&(!query||pretty(e).toLowerCase().includes(query)));
  $('#audit-events').innerHTML=rows.map(e=>`<details class="audit-event"><summary><span class="event-sequence">#${e.seq}</span><strong>${esc(e.kind)}</strong><span class="tag">${esc(e.subjectId)}</span><time>${esc(new Date(e.observedAt).toLocaleString())}</time></summary><div class="event-meta">${esc(e.source)} · ${esc(e.actor)}<br>Trace at capture: ${esc(e.traceId)}<br>Correlation: ${esc(e.correlationId||'native observation')}<br>Hash: ${esc(e.hash)}</div><pre>${esc(pretty(e.data))}</pre></details>`).join('')||'<p>No matching captured events.</p>';
}
async function loadEvals(){
  const epoch=auditEpoch,subject=auditSubject,s=observed.subjects.find(x=>x.id===subject);
  if(!s){$('#eval-results').innerHTML='<p>Select an agent or component to inspect its evaluations.</p>';await loadComparison();return}
  const d=await api(`/api/evals?subject=${encodeURIComponent(subject)}`);
  if(epoch!==auditEpoch||subject!==auditSubject)return;
  const e=d.operational,m=e.metrics;
  $('#eval-results').innerHTML=`<h3>${s.executionKind?'Role probe evidence':'Operational evidence'} ${verdict(e.status)}</h3><small>${esc(e.suite)} · ${esc(new Date(e.assessedAt).toLocaleString())}</small><p>${esc(e.meaning)}</p><div class="eval-metrics"><div><b>${m.turns??'—'}</b><small>Observed turns</small></div><div><b>${m.activities??'—'}</b><small>Activities</small></div><div><b>${m.usage?.totalTokens?.toLocaleString()??'Unknown'}</b><small>Reported tokens · cumulative</small></div><div><b>Unknown</b><small>Cost USD</small></div></div>${e.checks.map(c=>`<details class="eval-check"><summary>${verdict(c.status)} ${esc(c.name)}</summary><pre>${esc(pretty(c.evidence))}</pre></details>`).join('')}<small>${d.history.length} saved evaluation runs. Use “Run evidence checks” to save a new result.</small>${d.history.length?`<details class="eval-check"><summary>Saved evaluations</summary>${d.history.slice().reverse().map(h=>`<details><summary>#${h.seq} · ${esc(h.observedAt)} · ${esc(h.data.status)}</summary><pre>${esc(pretty(h.data))}</pre></details>`).join('')}</details>`:''}`;
  await loadComparison();
}
async function loadComparison(){
  const epoch=++comparisonEpoch;
  const probes=observed.subjects.filter(s=>s.executionKind==='benchmark-worker');
  const results=await Promise.all(probes.map(async s=>({subject:s,data:await api(`/api/evals?subject=${encodeURIComponent(s.id)}`)})));
  if(epoch!==comparisonEpoch)return;
  $('#probe-comparison').innerHTML=results.length?`<h3>Recorded role probes</h3><div class="probe-results">${results.map(({subject:s,data:d})=>{const end=d.benchmarks.filter(e=>e.kind==='benchmark.completed').at(-1),result=end?.data;return `<details class="eval-check"><summary>${verdict(result?.status||'running')} ${esc(s.role)} · ${esc(agentLabel(s.harness))} · ${result?.score==null?'Unscored':`${Math.round(result.score*100)}%`}</summary><p>${esc(s.id)}</p><button class="secondary" data-audit-subject="${esc(s.id)}">Inspect probe audit</button>${s.parentId?` <button class="secondary" data-audit-subject="${esc(s.parentId)}">Inspect execution</button>`:''}<pre>${esc(pretty(result||{status:'running'}))}</pre></details>`}).join('')}</div>`:'<p>No benchmark results yet. No scores are simulated.</p>';
  bindSubjectLinks();
}
$('#audit-role').onchange=async()=>{await busy($('#audit-refresh'),async()=>{await loadObservatory();await loadAudit(true)})};
$('#audit-subject').onchange=async()=>{auditSubject=$('#audit-subject').value;renderRelations();await busy($('#audit-refresh'),()=>loadAudit(true))};
$('#audit-trace').onchange=()=>busy($('#audit-refresh'),()=>loadAudit(true));
$('#audit-kind').oninput=renderAudit;$('#audit-search').oninput=renderAudit;
$('#audit-refresh').onclick=e=>busy(e.currentTarget,async()=>{await loadObservatory();await loadAudit(true)});
$('#audit-more').onclick=e=>busy(e.currentTarget,()=>loadAudit());
$('#show-timeline').onclick=()=>{auditTab='timeline';$('#audit-timeline').hidden=false;$('#audit-evals').hidden=true;$('#show-timeline').className='';$('#show-evals').className='secondary'};
$('#show-evals').onclick=e=>busy(e.currentTarget,async()=>{auditTab='evals';$('#audit-timeline').hidden=true;$('#audit-evals').hidden=false;$('#show-timeline').className='secondary';$('#show-evals').className='';await loadEvals()});
$('#run-evidence').onclick=e=>busy(e.currentTarget,async()=>{await api('/api/evals/run',{subjectId:auditSubject});await loadEvals();notice('Evidence evaluation saved to the agent audit trail')});
$('#audit-verify').onclick=e=>busy(e.currentTarget,async()=>{const v=await api('/api/audit/verify');$('#audit-integrity').textContent=v.valid?`Journal verified · ${v.events} events · checkpoint ${v.headHash}`:`Journal verification failed at event ${v.brokenAt}`});
$('#audit-export').onclick=e=>busy(e.currentTarget,async()=>{const result=await api('/api/audit/export'),blob=new Blob([pretty(result)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`factory-audit-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;a.click();URL.revokeObjectURL(url);notice('Journal exported with checkpoint. Keep it private; redaction is best effort.')});
$('#run-probe').onclick=e=>busy(e.currentTarget,async()=>{const r=await api('/api/benchmarks',{role:$('#probe-role').value,harness:$('#probe-harness').value});auditSubject=r.subjectId;$('#audit-role').value='';await loadObservatory();await loadAudit(true);notice('Real agent role probe started')});
loadObservatory().then(()=>loadAudit(true)).catch(e=>notice(e.message,true));
setInterval(async()=>{try{if(!$('#observatory').contains(document.activeElement)){await loadObservatory();if(auditTab==='evals')await loadEvals();else await loadAudit()}}catch(e){$('#audit-connection').textContent=`Collector unavailable · ${e.message}`}},10000);
