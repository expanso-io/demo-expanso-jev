'use strict';
// The board only draws what the adapter reports: pod labels come from the
// Kubernetes API, routine counts from collected stdout, and every signal
// animation is replayed from a real stage receipt (event, judging, judged,
// applied/undone/held). A label chip changes only after Kubernetes confirms.
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const SIG = {crashloop:'#cf2e3d',restart:'#6b7280',oom:'#b8530a',squeeze:'#a21caf',probe:'#2563eb',egress:'#7c3aed',healthy:'#187a3c',attested:'#0a8f8f',batch:'#475569'};
const LABEL_COLOR = {'routing-tier':'#187a3c',health:'#cf2e3d',pressure:'#b8530a',traffic:'#2563eb',security:'#7c3aed'};
const STAGE = {queued:'QUEUED',event:'POD LOG',collected:'READ',judging:'ASKED',judged:'ANSWER',applied:'APPLIED',undone:'REMOVED',held:'NOT SUPPORTED',error:'ERROR','dry-run':'DRY RUN'};
const cube = '<svg class="pod-icon" viewBox="0 0 72 76" aria-hidden="true"><path d="M36 5 65 21v34L36 72 7 55V21Z" fill="#f1ebfe" stroke="currentColor" stroke-width="2"/><path d="m7 21 29 17 29-17M36 38v34" fill="none" stroke="currentColor" stroke-width="2"/><path d="m36 5 29 16-29 17L7 21Z" fill="white" stroke="currentColor" stroke-width="2"/></svg>';
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

let state=null,session=null,selected=null,cursor=0,initialized=false,refreshing=null;
let lane="labels",investigationPending=false;
let loggedCount=0,routineCount=0,askedCount=0,events=[],pollTimer=null;
const flows=new Map(), feed=[];
const labelHighlights=new Map();
const LABEL_HOLD_MS=6000;

const text=(id,v)=>{$(id).textContent=v??'';};
function el(tag,cls,value){const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=value;return n;}
function svg(tag,attrs={}){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n;}
const key=p=>`${p.namespace}/${p.name}`;
const podEl=id=>[...document.querySelectorAll('[data-pod]')].find(p=>p.dataset.pod===id);
const clock=v=>new Date(v*1000).toLocaleTimeString([],{hour12:false});
const scenarioOf=id=>(state?.scenarios||[]).find(s=>s.id===id);
function showError(m){text('error',m);$('error').hidden=false;setTimeout(()=>{$('error').hidden=true;},6000);}

/* ---------------------------------------------------------------- geometry */
function box(node){const b=node.getBoundingClientRect(),o=$('topology').getBoundingClientRect();return{l:b.left-o.left,r:b.right-o.left,t:b.top-o.top,b:b.bottom-o.top,x:b.left-o.left+b.width/2,y:b.top-o.top+b.height/2};}
function geometry(podKey){
  const node=podEl(podKey);if(!node||matchMedia('(max-width:1100px)').matches)return null;
  const p=box(node),cl=box($('cluster')),c=box($('cloud-node')),j=box($('jev-node')),k=box($('kube-node'));
  const l=box($('logs-node'));
  const bus=p.t-14, lane=cl.r+30, inY=c.y-16, askY=c.y-16, ansY=c.y+16;
  return{
    toCloud:`M${p.x} ${p.t} V${bus} H${lane} V${inY} H${c.l}`,
    toLogs:`M${c.x+24} ${c.b} V${c.b+24} H${l.x} V${l.b}`,
    toJev:`M${c.r} ${askY} H${j.l}`, fromJev:`M${j.l} ${ansY} H${c.r}`,
    toKube:`M${c.x-24} ${c.b} V${k.y} H${k.r}`,
    toPod:`M${p.x} ${k.t} V${p.b}`,
    mid:{ask:[(c.r+j.l)/2,askY-8],ans:[(c.r+j.l)/2,ansY+18],patch:[c.x-32,c.b+55]},
  };
}
function drawWires(){
  const o=$('topology').getBoundingClientRect();$('wires').setAttribute('viewBox',`0 0 ${o.width} ${o.height}`);
  const paths=[];let any=null;
  for(const p of state?.pods||[]){const g=geometry(key(p));if(!g)continue;any=g;paths.push(svg('path',{d:g.toCloud,class:'wire'}));if(lane==='labels')paths.push(svg('path',{d:g.toPod,class:'wire patch'}));}
  if(any){
    paths.push(svg('path',{d:any.toLogs,class:'wire general'}));
    paths.push(svg('path',{d:any.toJev,class:'wire ask'}),svg('path',{d:any.fromJev,class:'wire ask'}));if(lane==='labels')paths.push(svg('path',{d:any.toKube,class:'wire patch'}));
    for(const [label,[x,y]] of [['ask',any.mid.ask],['answer',any.mid.ans],...(lane==='labels'?[['label',any.mid.patch]]:[])]){const t=svg('text',{x,y,class:'wire-label','text-anchor':label==='label'?'end':'middle'});t.textContent=label;paths.push(t);}
  }
  $('wire-paths').replaceChildren(...paths);
}
function travel(path,color,duration,routine){
  if(!path||reduced||document.hidden)return Promise.resolve();
  const measure=svg('path',{d:path,fill:'none',stroke:'none'}),size=routine?7:16;
  const packet=svg('g',{class:routine?'routine-packet':'packet'});
  if(!routine)packet.append(svg('rect',{x:-size,y:-size,width:size*2,height:size*2,rx:4,fill:color,class:'packet-halo'}));
  packet.append(svg('rect',{x:-size/2,y:-size/2,width:size,height:size,rx:2,...(routine?{}:{fill:color})}));
  $(routine?'routine-packets':'packets').append(measure,packet);
  const length=measure.getTotalLength();
  return new Promise(resolve=>{const start=performance.now();(function frame(now){const t=Math.min(1,(now-start)/duration),pt=measure.getPointAtLength(length*t);packet.setAttribute('transform',`translate(${pt.x} ${pt.y})`);if(t<1)requestAnimationFrame(frame);else{packet.remove();measure.remove();resolve();}})(start);});
}

/* -------------------------------------------------------------------- pods */
function labelChip(k,v,managed){
  const chip=el('span','label'+(managed?' managed':''));chip.dataset.key=k;
  if(managed)chip.style.setProperty('--lc',LABEL_COLOR[k]||'#6d3aed');
  chip.append(el('i','',k+'='),el('b','',v));const meaning=state?.available_labels?.find(l=>l.key===k&&l.value===v)?.meaning;chip.title=`${k}=${v}${meaning?' — '+meaning:''}`;return chip;
}
function highlightLabel(podKey,k,v,color,removed=false){
  const id=podKey+'/'+k,entry={key:k,value:v,color,removed,until:Date.now()+LABEL_HOLD_MS};
  labelHighlights.set(id,entry);
  setTimeout(()=>{if(labelHighlights.get(id)!==entry)return;labelHighlights.delete(id);const pod=state?.pods.find(p=>key(p)===podKey),node=podEl(podKey);if(pod&&node)renderLabels(node,pod);},LABEL_HOLD_MS);
}
function renderLabels(node,pod){
  const managedKeys=new Set((state?.available_labels||[]).map(l=>l.key));
  const holder=node.querySelector('.pod-labels');
  const base=Object.entries(pod.labels||{}).filter(([k])=>!managedKeys.has(k)).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>labelChip(k,v,false));
  const highlights=[...labelHighlights.entries()].filter(([id,h])=>id.startsWith(key(pod)+'/')&&h.until>Date.now()).map(([,h])=>{
    const chip=labelChip(h.key,h.value,true);chip.classList.toggle('removed',h.removed);chip.style.setProperty('--lc',h.color);return chip;
  });
  holder.replaceChildren(...base,...highlights);
}
function renderPods(confirmedKey=null){
  const pods=state?.pods||[];
  if(!pods.length){$('pods').replaceChildren(el('p','empty','No pods found in the configured namespace.'));return;}
  $('pods').querySelector('.empty')?.remove();
  for(const pod of pods){
    const id=key(pod);let node=podEl(id);
    if(!node){node=el('button','pod');node.dataset.pod=id;node.innerHTML=cube;node.append(el('span','pod-name',pod.name),el('span','pod-phase'),el('span','pod-event'),el('span','pod-labels'));node.addEventListener('click',()=>{selected=id;renderLogs();renderInvestigation();document.querySelectorAll('.pod').forEach(n=>n.classList.toggle('selected',n===node));});$('pods').append(node);}
    node.querySelector('.pod-phase').textContent=pod.status||'Unknown';
    if(confirmedKey===id||![...flows.values()].some(f=>f.podKey===id))renderLabels(node,pod);
  }
  if(!selected)selected=key(pods[0]);
  document.querySelectorAll('.pod').forEach(n=>n.classList.toggle('selected',n.dataset.pod===selected));
  text('target-name',selected?.split('/').pop()||'Select a pod');
  text('pod-count',`${pods.length} pods`);requestAnimationFrame(drawWires);
}
function renderLogs(){
  const pod=state?.pods.find(p=>key(p)===selected);$('actual-labels').replaceChildren(...Object.entries(pod?.labels||{}).map(([k,v])=>labelChip(k,v,false)));text('selected-name',pod?`· ${pod.name}`:'');
  const logs=(pod?.logs||[]).slice(-12);
  $('logs').replaceChildren(...(logs.length?logs.map(line=>{const s=typeof line==='string'?line:JSON.stringify(line);return el('div','log-line'+(/routine_heartbeat/.test(s)?'':' signal'),s);}):[el('p','empty','No log lines yet.')]));
}

/* ------------------------------------------------------------------ legend */
function renderLegend(){
  if($('legend').childElementCount||!(state?.scenarios||[]).length)return;
  for(const s of state.scenarios.filter(s=>s.prefer?.length&&!s.id.startsWith('investigate_'))){
    const item=el('button','legend-item');item.dataset.scenario=s.id;item.style.setProperty('--sig',SIG[s.id]||'#6d3aed');
    const title=el('b','',s.title);const [op,k,v]=s.prefer[s.prefer.length-1];title.append(el('code','',`${op==='add'?'+':'−'} ${k}=${v}`));
    item.append(el('i','sw'),title,el('span','',s.why));item.title=s.message;
    item.addEventListener('click',()=>sendEvent(s.id));$('legend').append(item);
  }
}

/* --------------------------------------------------------------- decisions */
function renderFeed(){
  $('feed').replaceChildren(...feed.map(f=>{
    const li=el('li');li.style.setProperty('--sig',SIG[f.scenario]||'#6d3aed');
    li.append(el('time','',clock(f.at)),el('span','who',f.pod),el('span','what',scenarioOf(f.scenario)?.title||f.scenario||'event'),el('span','said',f.said),el('span','did '+f.cls,f.did));return li;}));
}
function renderTrail(){text('event-count',`${events.length} receipts`);$('trail').replaceChildren(...events.slice(-16).reverse().map(e=>{const li=el('li');li.append(el('time','',clock(e.at)),el('span','',STAGE[e.stage]||e.stage),el('span','',`${e.pod||''} ${e.key?e.key+'='+e.value:''} ${e.message&&e.message!==e.stage?e.message:''}`));return li;}));}

const hist=new Map();
function remember(event){
  if(!event.request_id)return null;
  const h=hist.get(event.request_id)||{pod:event.pod};hist.set(event.request_id,h);
  if(event.scenario)h.scenario=event.scenario;
  if(event.stage==='judging'||event.stage==='collected'){h.key=event.key;h.value=event.value;h.op=event.operation;}
  if(event.stage==='judged')h.noul=event.noul;
  if(hist.size>200)hist.delete(hist.keys().next().value);
  return h;
}
function pushFeed(event,h){
  const pct=Number.isFinite(h.noul)?`Jev ${Math.round(h.noul*100)}% yes`:'Jev not asked';
  const asked=h.key?`“${h.key}=${h.value}” ${h.op==='undo'?'no longer true?':'true now?'} `:'';
  feed.unshift({at:event.at,pod:h.pod||event.pod,scenario:h.scenario,said:`${asked}${pct}`,
    did:event.already_set?'already set':event.stage==='applied'?`+ ${event.key}=${event.value}`:event.stage==='undone'?`− ${event.key}=${event.value}`:event.stage==='error'?'error':event.stage==='dry-run'?'dry run':'not supported',
    cls:event.stage==='applied'?'add':event.stage==='undone'?'rm':event.stage==='error'?'err':''});
  feed.length=Math.min(feed.length,6);renderFeed();
}
const TERMINAL=['applied','undone','held','error','dry-run','investigation_waiting','investigation_ready','investigation_error'];
function flowFor(event){
  let f=flows.get(event.request_id);
  if(!f){f={id:event.request_id,podKey:`${event.namespace}/${event.pod}`,pod:event.pod,scenario:event.scenario,chain:Promise.resolve(),steps:new Set()};flows.set(event.request_id,f);}
  if(event.scenario)f.scenario=event.scenario;return f;
}
function acceptEvents(incoming,live=true){
  for(const event of [...incoming].sort((a,b)=>a.seq-b.seq)){
    if(event.seq<=cursor)continue;cursor=event.seq;
    if(event.stage==='routine'){if(live)showRoutine(event);else {routineCount+=Number(event.count)||0;if(event.destination==='general_logs')loggedCount+=Number(event.count)||0;}continue;}
    events.push(event);const h=remember(event);
    if(event.investigation){const current=(state.investigations||[]).find(i=>i.namespace===event.namespace&&i.pod===event.pod);if((current?.revision||0)>(event.investigation.revision||0)){flows.delete(event.request_id);continue;}state.investigations=(state.investigations||[]).filter(i=>!(i.namespace===event.namespace&&i.pod===event.pod));state.investigations.push(event.investigation);}
    if(event.stage==='judging')askedCount++;
    if(!live&&h&&TERMINAL.includes(event.stage))pushFeed(event,h);
    if(!live||!event.request_id)continue;
    const f=flowFor(event);if(f.steps.has(event.stage))continue;f.steps.add(event.stage);
    const isInvestigation=event.operation==='investigate'||event.investigation||f.scenario?.startsWith('investigate_');
    const color=isInvestigation?'#087f8c':SIG[f.scenario]||'#6d3aed',node=podEl(f.podKey),g=()=>geometry(f.podKey);
    const then=fn=>{f.chain=f.chain.then(fn).catch(()=>{});};
    if(event.stage==='event')then(async()=>{
      const s=scenarioOf(f.scenario);
      if(node){node.classList.add('busy');node.style.setProperty('--sig',color);node.dataset.receipt=f.id;node.querySelector('.pod-event').classList.remove('result');node.querySelector('.pod-event').textContent=s?.title||'';}
      document.querySelectorAll('.legend-item').forEach(n=>n.classList.toggle('live',n.dataset.scenario===f.scenario));
      const source=document.querySelector(`[data-scenario="${CSS.escape(f.scenario||'')}"]`);
      if(source&&node&&g()){const a=box(source),b=box(node);await travel(`M${a.x} ${a.b} V${b.t-7} H${b.x} V${b.t}`,color,400);}
      await travel(g()?.toCloud,color,900);$('cloud-node').classList.add('processing');});
    if(event.stage==='collected'&&isInvestigation)then(()=>renderInvestigation());
    if(event.stage==='judging')then(async()=>{
      f.key=event.key;f.value=event.value;f.op=event.operation;
      text('jev-question',isInvestigation?'Investigate?':event.key?`${event.key}=${event.value} ${event.operation==='undo'?'no longer true?':'true?'}`:'');text('jev-status','…');
      await travel(g()?.toJev,color,500);$('jev-node').classList.add('processing');});
    if(event.stage==='judged')then(async()=>{
      f.noul=event.noul;text('jev-status',Number.isFinite(event.noul)?`${Math.round(event.noul*100)}% YES`:'ANSWERED');
      $('jev-node').classList.remove('processing');await travel(g()?.fromJev,color,500);});
    if(['investigation_waiting','investigation_ready','investigation_error'].includes(event.stage))then(async()=>{
      $('cloud-node').classList.remove('processing');
      node?.classList.remove('busy');investigationPending=false;flows.delete(f.id);
      renderInvestigation();await refreshState();
    });
    if(['applied','undone','held','error','dry-run'].includes(event.stage))then(async()=>{
      const changed=event.stage==='applied'||event.stage==='undone';
      if(changed){
        text('api-line',`PATCH /api/v1/namespaces/${event.namespace}/pods/${event.pod}  ${event.stage==='applied'?'+':'−'} ${event.key}=${event.value}`);
        await travel(g()?.toKube,color,800);$('kube-node').classList.add('fire');await travel(g()?.toPod,color,600);
        setTimeout(()=>$('kube-node').classList.remove('fire'),600);
        const pod=state?.pods.find(p=>key(p)===f.podKey);
        if(pod){
          highlightLabel(f.podKey,event.key,event.value,color,event.stage==='undone');
          if(event.stage==='applied')pod.labels[event.key]=event.value;else delete pod.labels[event.key];
          renderPods(f.podKey);
        }

      }
      const alreadySet=event.stage==='held'&&event.operation==='review'&&state.pods.some(p=>key(p)===f.podKey&&p.labels?.[event.key]===event.value)&&(scenarioOf(f.scenario)?.prefer||[]).some(([op,k,v])=>op==='add'&&k===event.key&&v===event.value);
      if(alreadySet){highlightLabel(f.podKey,event.key,event.value,color);renderPods(f.podKey);}
      pushFeed({...event,already_set:alreadySet},h||{pod:f.pod,scenario:f.scenario});
      $('cloud-node').classList.toggle('processing',[...flows.values()].some(x=>x!==f));
      if(node){node.classList.remove('busy');
        const outcome=node.querySelector('.pod-event');
        if(event.stage==='undone'||event.stage==='held'){outcome.classList.add('result');outcome.textContent=event.stage==='undone'?'Removed':alreadySet?'Already set':event.operation==='review'?'Protected':'Not supported';}
        setTimeout(()=>{if(node.dataset.receipt!==f.id)return;outcome.textContent='';outcome.classList.remove('result');document.querySelectorAll('.legend-item.live').forEach(n=>n.classList.remove('live'));},5000);
      }
      flows.delete(f.id);refreshState();});
  }
  events=events.slice(-100);text('logged-count',loggedCount.toLocaleString());text('routine-count',routineCount.toLocaleString());text('asked-count',askedCount.toLocaleString());renderTrail();
}
function showRoutine(event){
  const id=`${event.namespace}/${event.pod}`,n=Number(event.count)||0;routineCount+=n;
  if(event.destination==='general_logs')loggedCount+=n;
  for(let i=0;i<Math.min(n,14);i++)setTimeout(async()=>{const g=geometry(id);if(!g)return;await travel(g.toCloud,null,800,true);if(event.destination==='general_logs')await travel(g.toLogs,null,650,true);},Math.random()*950);
}

/* --------------------------------------------------------- investigations */
function renderInvestigation(){
  const pod=state?.pods.find(p=>key(p)===selected);text('target-name',pod?.name||'Select a pod');
  const incident=(state?.investigations||[]).filter(i=>`${i.namespace}/${i.pod}`===selected).at(-1);
  const status=incident?.status||'empty';
  const labels={empty:'Restart',queued:'Queued',collecting:'Collecting',collected:'Checking',judging:'Checking',waiting:'Wait',ready:'Investigate',error:'Unavailable'};
  text('gate-status',labels[status]||status);
  text('gate-detail',Number.isFinite(incident?.score)?`${Math.round(incident.score*100)}%`:'');
  $('evidence-cards').replaceChildren(...(incident?.evidence||[]).filter(e=>e.kind==='logs'||['restart','context','evidence'].includes(e.kind)).map(e=>{
    let message=e.text||e.message||'',title=e.kind;try{const record=JSON.parse(message);message=record.message||message;title=record.event?.replace('investigation_','')||title;}catch{}
    const card=el('article','evidence-card');card.append(el('b','',title||e.id),el('p','',message),el('small','',`${e.id||''} · ${e.source||'pod evidence'}${e.synthetic?' · simulated':''}`));return card;
  }));
  for(const b of document.querySelectorAll('[data-phase]')){
    b.disabled=investigationPending||['queued','collecting','judging','investigating'].includes(status)||!pod||(b.dataset.phase!=='restart'&&['ready'].includes(status));
    b.classList.toggle('active',b.dataset.phase===incident?.phase);
  }
}
async function setLane(next){
  lane=next;document.body.dataset.lane=lane;
  for(const b of document.querySelectorAll('[data-lane]'))b.setAttribute('aria-pressed',String(b.dataset.lane===lane));
  $('investigation-panel').hidden=lane!=='investigation';
  document.querySelector('.legend').hidden=lane!=='labels';document.querySelector('.feed').hidden=lane!=='labels';
  if(lane==='investigation'&&state?.auto){try{await post('/api/auto',{on:false});state.auto=false;}catch(e){showError(e.message);}}
  renderState();requestAnimationFrame(drawWires);
}
async function investigate(phase){
  const pod=state?.pods.find(p=>key(p)===selected);if(!pod||investigationPending)return;
  investigationPending=true;renderInvestigation();
  try{await post('/api/investigate',{namespace:pod.namespace,pod:pod.name,phase});await refreshState();}
  catch(e){investigationPending=false;showError(e.message);renderInvestigation();}
}
for(const b of document.querySelectorAll('[data-lane]'))b.addEventListener('click',()=>setLane(b.dataset.lane));
for(const b of document.querySelectorAll('[data-phase]'))b.addEventListener('click',()=>investigate(b.dataset.phase));

/* -------------------------------------------------------------------- I/O */
async function post(path,body){
  if(!session){const r=await fetch('/api/session',{cache:'no-store'});if(!r.ok)throw Error('Could not establish a local session.');session=await r.json();}
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify(body)});
  const out=await r.json().catch(()=>({}));if(!r.ok)throw Error(out.message||out.error||'Request rejected.');return out;
}
async function sendEvent(scenario){
  const busy=new Set([...flows.values()].map(f=>f.podKey)),idle=(state?.pods||[]).filter(p=>p.event_enabled!==false&&!busy.has(key(p)));
  const pod=selected?idle.find(p=>key(p)===selected):idle[0];
  if(!pod)return showError('This pod is still processing its event.');
  try{const result=await post('/api/event',{namespace:pod.namespace,pod:pod.name,scenario});if(result.request_id)flowFor({...result,pod:pod.name,namespace:pod.namespace,scenario});}catch(e){showError(e.message);}
}
function renderState(){
  const cloud=state.cloud||{},running=cloud.state==='running';
  text('traffic-members',state.routing?.state==='observed'?(state.routing.pods.length?state.routing.pods.join(' · '):'No ready endpoints'):'Unverified');
  text('connection',running?'Pipeline running in Expanso Cloud':cloud.state==='stopped'?'Cloud job stopped':'Cloud job unverified');$('connection-dot').className='dot'+(running?' live':'');
  text('mode',(state.apply_enabled?'LIVE · labels are really patched':'DRY RUN · no patches')+(Number.isFinite(state.threshold)?` · acts at ≥ ${Math.round(state.threshold*100)}% yes`:''));$('mode').classList.toggle('dry',!state.apply_enabled);
  text('cluster-name','Kubernetes cluster');text('namespace','namespace '+(state.namespace||''));text('cloud-status',(cloud.state||'unknown').toUpperCase());
  $('auto-toggle').textContent=state.auto?'Pause events':'Resume events';$('auto-toggle').setAttribute('aria-pressed',String(Boolean(state.auto)));
  renderPods();renderLogs();renderLegend();renderInvestigation();
  $('label-inventory').replaceChildren(...(state.observed_label_inventory||[]).map(l=>el('p','',`${l.key}=${l.value} · ${(l.source_pods||[]).map(p=>typeof p==='string'?p:p.name).join(', ')}`)));
  $('available-labels').replaceChildren(...(state.available_labels||[]).map(l=>{const row=el('div','label-choice');row.append(el('code','',`${l.key}=${l.value}`),el('span','',l.meaning));return row;}));
  const fields={'Kubernetes context':state.cluster_context,'Cloud job':cloud.job_id,'Execution':cloud.execution_id,'Edge node':cloud.node_id,'Label writes':state.apply_enabled?'Enabled':'Disabled'};
  $('runtime-fields').replaceChildren(...Object.entries(fields).flatMap(([k,v])=>[el('dt','',k),el('dd','',v||'Not verified')]));
}
function refreshState(){
  if(refreshing)return refreshing;
  refreshing=(async()=>{try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error();state=await r.json();if(!initialized){acceptEvents(state.events||[],false);renderState();initialized=true;}else renderState();}
    catch{text('connection','Adapter unavailable');$('connection-dot').className='dot error';}finally{refreshing=null;}})();
  return refreshing;
}
async function pollEvents(){
  try{if(initialized){const r=await fetch(`/api/events?after=${cursor}`,{cache:'no-store'});if(r.ok){const body=await r.json();
    if(Number.isFinite(body.cursor)&&body.cursor<cursor){cursor=0;events=[];flows.clear();session=null;document.querySelectorAll('.pod.busy').forEach(n=>n.classList.remove('busy'));await refreshState();}
    else acceptEvents(body.events||[]);}}}
  catch{}finally{pollTimer=setTimeout(pollEvents,60);}
}
$('auto-toggle').addEventListener('click',async()=>{try{const out=await post('/api/auto',{on:!state?.auto});state.auto=out.auto;renderState();}catch(e){showError(e.message);}});
$('details-toggle').addEventListener('click',()=>{const hide=!$('runtime-details').hidden;$('runtime-details').hidden=hide;$('details-toggle').setAttribute('aria-expanded',String(!hide));$('details-toggle').textContent=hide?'Details':'Close details';});
new ResizeObserver(drawWires).observe($('topology'));
window.addEventListener('pagehide',()=>clearTimeout(pollTimer));
refreshState().then(pollEvents);setInterval(refreshState,2500);
