'use strict';
const $ = (id) => document.getElementById(id);
let state = null, session = null, scenario = 'checkout', selected = null;
let refreshing = false;
let lastSeq = 0, busy = false, previousLabels = new Map(), lastPods = '';
const NS = 'http://www.w3.org/2000/svg';
const cube = '<svg class="pod-icon" viewBox="0 0 72 76" aria-hidden="true"><path d="M36 5 65 21v34L36 72 7 55V21Z" fill="#f1ebfe" stroke="currentColor" stroke-width="1.5"/><path d="m7 21 29 17 29-17M36 38v34" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m36 5 29 16-29 17L7 21Z" fill="white" stroke="currentColor" stroke-width="1.5"/><path d="m22 20 14-8 14 8-14 8Z" fill="currentColor" opacity=".12"/><path d="m16 36 10 6m-10 3 10 6m20-9 10-6m-10 15 10-6" fill="none" stroke="currentColor" opacity=".45" stroke-width="2"/></svg>';
const names = {event:'EVENT',collected:'CLOUD',judging:'JEV',judged:'JUDGED',applied:'APPLIED',undone:'UNDONE',held:'HELD',error:'ERROR'};
function text(id, value) { $(id).textContent = value ?? ''; }
function el(tag, cls, value) { const node=document.createElement(tag); if(cls)node.className=cls; if(value!==undefined)node.textContent=value; return node; }
function error(message) { text('error',message); $('error').hidden=false; }
function key(pod) { return `${pod.namespace}/${pod.name}`; }
function timeLabel(value) { const d=new Date(typeof value==='number' ? value*1000 : value); return Number.isNaN(d.getTime())?'—':d.toLocaleTimeString([], {hour12:false}); }
function podByKey() { return state?.pods?.find(p=>key(p)===selected); }
function renderPods() {
  const pods=state.pods || [];
  if(!pods.length) { lastPods='';selected=null;$('pods').replaceChildren(el('p','empty','No pods found in the configured namespace.'));text('pod-count','0 pods');$('logs').replaceChildren();text('selected-name','/ no workload');return; }
  if(!selected || !pods.some(p=>key(p)===selected)) selected=key(pods.find(p=>p.name==='checkout-new') || pods[0]);
  const signature=JSON.stringify([pods.map(p=>[key(p),p.labels,p.status,p.event_enabled]),selected,busy]);
  if(signature===lastPods)return;
  lastPods=signature;
  const fragment=document.createDocumentFragment();
  for(const pod of pods) {
    const button=el('button','pod'+(key(pod)===selected?' selected':'')+(pod.name.includes('analytics')?' dim':''));
    button.dataset.pod=key(pod); button.setAttribute('aria-label',`Trigger ${scenario} on ${pod.name}`);
    button.setAttribute('aria-pressed',String(key(pod)===selected));
    button.disabled=busy || pod.event_enabled===false;
    button.innerHTML=cube;
    button.append(el('span','pod-name',pod.name));
    const labels=el('span','pod-labels');
    const old=previousLabels.get(key(pod));
    for(const [name,value] of Object.entries(pod.labels||{})) {
      if(name.startsWith('jev.expanso.io/') || name==='pod-template-hash')continue;
      const changed=old && old[name]!==value;
      const label=el('span','label'+(name==='routing-tier'||name==='team'?' managed':'')+(changed?' new':''),`${name}=${value}`);
      labels.append(label);
    }
    button.append(labels,el('span','pod-hint',pod.event_enabled===false?'Reference workload':'Click to send event'));
    button.addEventListener('click',()=>sendEvent(pod));
    fragment.append(button);
    previousLabels.set(key(pod),{...pod.labels});
  }
  $('pods').replaceChildren(fragment);
  text('pod-count',`${pods.length} pods`);
  text('node-name',[...new Set(pods.map(p=>p.node).filter(Boolean))].join(' · ') || 'Kubernetes workloads');
  requestAnimationFrame(drawWires);
}
function point(id) { const box=$(id).getBoundingClientRect(), base=$('topology').getBoundingClientRect(); return {x:box.x-base.x+box.width/2,y:box.y-base.y+box.height/2,w:box.width,h:box.height}; }
function drawWires() {
  const box=$('topology').getBoundingClientRect(); $('wires').setAttribute('viewBox',`0 0 ${box.width} ${box.height}`);
  const p=point('cluster'),c=point('cloud-node'),j=point('jev-node');
  const small=box.width<720;
  $('to-cloud').setAttribute('d',small?`M${p.x} ${p.y+p.h/2} C${p.x} ${c.y-110} ${c.x} ${c.y-110} ${c.x} ${c.y-c.h/2}`:`M${p.x+p.w/2} ${p.y} L${c.x-c.w/2} ${c.y}`);
  $('to-jev').setAttribute('d',`M${c.x+c.w/2} ${c.y} L${j.x-j.w/2} ${j.y}`);
  const bottom=box.height-24;
  $('to-pod').setAttribute('d',`M${j.x} ${j.y+j.h/2} V${bottom-12} Q${j.x} ${bottom} ${j.x-12} ${bottom} H${p.x+12} Q${p.x} ${bottom} ${p.x} ${bottom-12} V${p.y+p.h/2}`);
}
function pulse(id,path,color) {
  $(id).classList.remove('pulse'); void $(id).offsetWidth; $(id).classList.add('pulse');
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const dot=document.createElementNS(NS,'circle'); dot.setAttribute('r','4'); dot.setAttribute('fill',color);
  const motion=document.createElementNS(NS,'animateMotion');motion.setAttribute('dur','.85s');motion.setAttribute('path',$(path).getAttribute('d')||'');motion.setAttribute('fill','freeze');
  dot.append(motion);$('packets').append(dot);motion.beginElement();setTimeout(()=>dot.remove(),900);
}
function describe(event) { if(event.key)return `${event.pod || ''} · ${event.key}=${event.value}${Number.isFinite(event.noul)?` · ${(event.noul*100).toFixed(0)}% yes`:''}`; return event.message || event.pod || 'Observed pipeline event'; }
function renderEvents() {
  const events=state.events || [];
  text('event-count',`${events.length} EVENTS`);
  if(events.length) {
    $('trail').replaceChildren(...events.slice(-12).reverse().map(event=>{
      const row=el('li');row.append(el('time','',timeLabel(event.at)),el('span',`stage ${event.stage}`,names[event.stage]||event.stage),el('span','trail-description',describe(event)));return row;
    }));
  }
  for(const event of events.filter(e=>e.seq>lastSeq)) {
    lastSeq=Math.max(lastSeq,event.seq);
    if(event.stage==='collected')pulse('cloud-node','to-cloud','#6d3aed');
    if(event.stage==='judging') {pulse('jev-node','to-jev','#b8530a');text('jev-status','READING LOGS');}
    if(event.stage==='judged') {text('jev-status',Number.isFinite(event.noul)?`${(event.noul*100).toFixed(0)}% YES`:'ANSWER RECEIVED');}
    if(['applied','undone'].includes(event.stage)) {
      pulse('cluster','to-pod','#187a3c');text('result-mark',event.stage==='applied'?'+':'−');
      text('result-title',`${event.pod}: label ${event.stage==='applied'?'added':'removed'}.`);
      text('result-detail',`${event.key}=${event.value} · Kubernetes confirmed the change.`);
    } else if(event.stage==='held') {text('result-mark','◎');text('result-title','A decision to wait.');text('result-detail',event.message || 'Jev did not justify a change. Existing labels are preserved.');}
  }
}
function renderLogs() {
  const pod=podByKey();if(!pod)return;
  text('selected-name',`/ ${pod.name}`);
  const logs=pod.logs || [];
  $('logs').replaceChildren(...(logs.length?logs.slice(-8).map(line=>el('div','log-line'+(/error|failure|denied/i.test(typeof line==='string'?line:JSON.stringify(line))?' error':''),typeof line==='string'?line:JSON.stringify(line))):[el('p','placeholder','No workload logs collected yet. Send an event to this pod.')]));
}
function render() {
  const cloud=state.cloud || {};
  text('connection',state.mode==='preview'?'Preview · synthetic state':cloud.state==='running'?'Cloud execution running':cloud.state==='stopped'?'Cloud job stopped':'Cloud execution unverified');
  $('connection-dot').className='dot'+(cloud.state==='running'&&state.mode!=='preview'?' live':'');
  text('mode',state.mode==='preview'?'PREVIEW · SYNTHETIC STATE':state.apply_enabled?'LIVE · WRITES ENABLED':'DRY RUN · NO LABEL WRITES');
  $('mode').classList.toggle('dry',!state.apply_enabled || state.mode==='preview');
  text('cluster-name',state.cluster_context || 'k3s cluster');text('namespace',state.namespace || 'Target namespace');
  text('cloud-status',(cloud.state || 'unknown').toUpperCase());
  text('cloud-detail',cloud.state==='running'?'Collect → ask → apply':cloud.state==='stopped'?'Start the job in Cloud':'Verify node and job assignment');
  text('last-tick',cloud.last_tick_at?`Last collection ${timeLabel(cloud.last_tick_at)}`:'No Cloud tick observed');
  renderPods();renderLogs();renderEvents();
  const fields={'Kubernetes context':state.cluster_context,'Cloud job':cloud.job_id,'Execution':cloud.execution_id,'Edge node':cloud.node_id,'Adapter':state.mode==='preview'?'Synthetic preview':location.origin,'Label writes':state.apply_enabled?'Enabled':'Disabled (dry run)'};
  $('runtime-fields').replaceChildren(...Object.entries(fields).flatMap(([k,v])=>[el('dt','',k),el('dd','',v || 'Not verified')]));
}
async function sendEvent(pod) {
  selected=key(pod);busy=true;lastPods='';render();$('error').hidden=true;
  try {
    if(!session){const res=await fetch('/api/session',{cache:'no-store'});if(!res.ok)throw Error('Could not establish a local session.');session=await res.json();}
    const res=await fetch('/api/event',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token || session.token},body:JSON.stringify({namespace:pod.namespace,pod:pod.name,scenario})});
    const result=await res.json();if(!res.ok)throw Error(result.message || result.error || 'The workload event could not be generated.');
    text('result-mark','↗');text('result-title',`Event sent to ${pod.name}.`);text('result-detail','Waiting for Cloud to collect its logs. No label change has been claimed.');
    await refresh();
  } catch(err) {error(err.message);} finally {busy=false;lastPods='';if(state)renderPods();}
}
async function refresh() {
  if(refreshing)return;refreshing=true;
  try {const res=await fetch('/api/state',{cache:'no-store'});if(!res.ok)throw Error('The adapter could not read cluster state.');state=await res.json();render();}
  catch(err){text('connection','Adapter unavailable');$('connection-dot').className='dot error';text('cloud-status','UNVERIFIED');}
  finally {refreshing=false;}
}
for(const button of document.querySelectorAll('[data-scenario]'))button.addEventListener('click',()=>{scenario=button.dataset.scenario;for(const b of document.querySelectorAll('[data-scenario]')){b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));}lastPods='';if(state)renderPods();});
$('details-toggle').addEventListener('click',()=>{const hidden=!$('runtime-details').hidden;$('runtime-details').hidden=hidden;$('details-toggle').setAttribute('aria-expanded',String(!hidden));$('details-toggle').textContent=hidden?'Inspect runtime +':'Close runtime −';});
window.addEventListener('resize',drawWires);
refresh();setInterval(refresh,1800);
