'use strict';
const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const colors = {source:'#6d3aed',cloud:'#6d3aed',jev:'#b8530a',return:'#187a3c',held:'#a06a22'};
const scenarios = {checkout:'Checkout',failure:'Route failure',analytics:'Batch job',recovery:'Recovery',security:'Security'};
const names = {queued:'QUEUED',event:'POD LOG',collected:'CLOUD',judging:'JEV',judged:'VERDICT',applied:'APPLIED',undone:'UNDONE',held:'HELD',error:'ERROR','dry-run':'DRY RUN'};
const cube = '<svg class="pod-icon" viewBox="0 0 72 76" aria-hidden="true"><path d="M36 5 65 21v34L36 72 7 55V21Z" fill="#f1ebfe" stroke="currentColor" stroke-width="1.5"/><path d="m7 21 29 17 29-17M36 38v34" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="m36 5 29 16-29 17L7 21Z" fill="white" stroke="currentColor" stroke-width="1.5"/><path d="m22 20 14-8 14 8-14 8Z" fill="currentColor" opacity=".12"/><path d="m16 36 10 6m-10 3 10 6m20-9 10-6m-10 15 10-6" fill="none" stroke="currentColor" opacity=".45" stroke-width="2"/></svg>';
let state=null,session=null,scenario='checkout',selected=null,cursor=0,initialized=false,refreshing=null,stateGeneration=0;
const flows=new Map(),pending=new Map(),shownLabels=new Map();
let events=[],eventPollTimer=null;
const text=(id,value)=>{$(id).textContent=value??'';};
function el(tag,cls,value){const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=value;return n;}
function svg(tag,attrs={}){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n;}
const key=pod=>`${pod.namespace}/${pod.name}`;
const podButton=id=>[...document.querySelectorAll('[data-pod]')].find(p=>p.dataset.pod===id);
const timeLabel=value=>new Date(typeof value==='number'?value*1000:value).toLocaleTimeString([],{hour12:false});
function showError(message){text('error',message);$('error').hidden=false;}
function point(node){const box=node.getBoundingClientRect(),base=$('topology').getBoundingClientRect();return{x:box.x-base.x+box.width/2,y:box.y-base.y+box.height/2,w:box.width,h:box.height};}
function geometry(podKey,chosenScenario=scenario){
  const pod=podButton(podKey);if(!pod)return null;
  const p=point(pod),cluster=point($('cluster')),c=point($('cloud-node')),j=point($('jev-node')),k=point($('kube-node'));
  const source=point(document.querySelector(`[data-scenario="${chosenScenario}"]`));
  const mobile=matchMedia('(max-width:850px)').matches;
  const injectionY=cluster.y-cluster.h/2-20;
  const inject=`M${source.x} ${source.y+source.h/2+2} V${injectionY} H${p.x} V${p.y-p.h/2-4}`;
  const cLeft=c.x-c.w/2,cRight=c.x+c.w/2,jLeft=j.x-j.w/2;
  const busY=p.y+p.h/2+12;
  const outboundY=c.y-20,returnY=c.y+28;
  const outside=cluster.x+cluster.w/2+20;
  const toCloud=mobile
    ?`M${p.x} ${p.y+p.h/2+2} V${busY} H${cluster.x+cluster.w/2+9} V${cluster.y+cluster.h/2+29} H${c.x} V${c.y-c.h/2-3}`
    :`M${p.x} ${p.y+p.h/2+2} V${busY} H${outside} V${outboundY} H${cLeft-3}`;
  const bottom=$('topology').clientHeight-27;
  const toKube=mobile
    ?`M${c.x-c.w/2} ${returnY} H9 V${k.y} H${k.x-k.w/2-3}`
    :`M${c.x} ${c.y+c.h/2+3} V${bottom} H${k.x} V${k.y+k.h/2+3}`;
  const toPod=`M${k.x} ${k.y-k.h/2-3} V${p.y+p.h/2+26} H${p.x} V${p.y+p.h/2+2}`;
  return{inject,toCloud,toJev:`M${cRight+3} ${outboundY} H${jLeft-3}`,fromJev:`M${jLeft-3} ${returnY} H${cRight+3}`,toKube,toPod,
    labels:[['pod logs',mobile?c.x+34:(outside+cLeft)/2,mobile?cluster.y+cluster.h/2+42:outboundY-11,false],['evidence',(cRight+jLeft)/2,outboundY-11,false],['interpretation',(cRight+jLeft)/2,returnY+18,true],['update request',mobile?64:(k.x+c.x)/2,mobile?cluster.y+cluster.h/2+8:bottom-10,true]]};
}
function drawWires(){
  const box=$('topology').getBoundingClientRect();$('wires').setAttribute('viewBox',`0 0 ${box.width} ${box.height}`);
  const g=geometry(selected);if(!g)return;
  for(const [id,path] of [['to-cloud',g.toCloud],['to-jev',g.toJev],['from-jev',g.fromJev],['to-kube',g.toKube],['to-pod',g.toPod]])$(id).setAttribute('d',path);
  $('wire-labels').replaceChildren(...g.labels.map(([label,x,y,back])=>{const n=svg('text',{x,y,class:'wire-label'+(back?' return':'')});n.textContent=label;return n;}));
  $('injection-wires').replaceChildren(...(state?.pods||[]).map(p=>geometry(key(p))).filter(Boolean).map(p=>svg('path',{d:p.inject,class:'injection-wire'})));
}
function travel(path,color,route,duration=220){
  if(!path||matchMedia('(prefers-reduced-motion: reduce)').matches)return Promise.resolve();
  const measure=svg('path',{d:path,fill:'none',stroke:'none'});
  const packet=svg('g',{class:'packet','data-route':route,style:`color:${color}`});
  packet.append(svg('circle',{r:12,fill:color,class:'packet-halo'}),svg('circle',{r:5,fill:color,class:'packet-core'}));
  $('packets').append(measure,packet);
  const length=measure.getTotalLength();
  const first=measure.getPointAtLength(0);packet.setAttribute('transform',`translate(${first.x} ${first.y})`);
  return new Promise(resolve=>{const start=performance.now();function frame(now){const progress=Math.min(1,(now-start)/duration),p=measure.getPointAtLength(length*progress);packet.setAttribute('transform',`translate(${p.x} ${p.y})`);if(progress<1)requestAnimationFrame(frame);else{packet.remove();measure.remove();resolve();}}requestAnimationFrame(frame);});
}
function animate(flow,stage){
  flow.chain=flow.chain.then(async()=>{
    const g=geometry(flow.podKey,flow.scenario);if(!g)return;
    const steps={inject:[g.inject,colors.source,'event-to-pod',120],event:[g.toCloud,colors.cloud,'pod-to-cloud',160],judging:[g.toJev,colors.jev,'cloud-to-jev',120],judged:[g.fromJev,colors.return,'jev-to-cloud',120],request:[g.toKube,colors.return,'cloud-to-kubernetes',100],terminal:[g.toPod,colors.return,'kubernetes-to-pod',100]};
    const args=steps[stage];if(args)await travel(...args);
  });
  return flow.chain;
}
function updateBusy(){
  for(const button of document.querySelectorAll('[data-pod]')){
    const flow=pending.get(button.dataset.pod);
    button.disabled=Boolean(flow)||button.dataset.enabled==='false';
    button.classList.toggle('busy',Boolean(flow));button.classList.toggle('selected',button.dataset.pod===selected);
    button.setAttribute('aria-pressed',String(button.dataset.pod===selected));
    button.setAttribute('aria-label',`Send ${scenarios[scenario]} to ${button.dataset.name}`);
    button.querySelector('.pod-hint').textContent=flow?flow.hint:'Click to inject ↓';
  }
  $('jev-node').classList.toggle('processing',[...pending.values()].some(f=>f.hint==='Jev is judging…'));
  $('cloud-node').classList.toggle('processing',pending.size>0);
}
function renderPods(){
  const pods=state?.pods||[];
  if(!pods.length){$('pods').replaceChildren(el('p','empty','No pods found in the configured namespace.'));text('pod-count','0 pods');selected=null;return;}
  if(!pods.some(p=>key(p)===selected))selected=key(pods.find(p=>p.name==='checkout-api')||pods[0]);
  const keys=pods.map(key);
  for(const old of $('pods').querySelectorAll('[data-pod]'))if(!keys.includes(old.dataset.pod))old.remove();
  $('pods').querySelector('.empty')?.remove();
  for(const pod of pods){
    const id=key(pod);let button=podButton(id);
    if(!button){button=el('button','pod');button.dataset.pod=id;button.dataset.name=pod.name;button.innerHTML=cube;button.append(el('span','pod-name',pod.name),el('span','pod-phase'),el('span','pod-labels'),el('span','pod-hint'));button.addEventListener('click',()=>sendEvent(pod));$('pods').append(button);}
    button.dataset.enabled=String(pod.event_enabled!==false);
    button.querySelector('.pod-phase').textContent=pod.status||'Unknown';
    const prior=shownLabels.get(id)||{};
    const labels=pending.has(id)&&shownLabels.has(id)?prior:(pod.labels||{});
    if(button.dataset.labels!==JSON.stringify(labels)){
      button.querySelector('.pod-labels').replaceChildren(...Object.entries(labels).filter(([k])=>!k.startsWith('jev.expanso.io/')&&!['pod-template-hash','controller-revision-hash'].includes(k)).map(([k,v])=>el('span','label'+(['team','routing-tier'].includes(k)?' managed':'')+(k in labels&&prior[k]!==v&&shownLabels.has(id)?' new':''),`${k}=${v}`)));
      button.dataset.labels=JSON.stringify(labels);shownLabels.set(id,{...labels});
    }
  }
  text('pod-count',`${pods.length} pods`);text('node-name',[...new Set(pods.map(p=>p.node).filter(Boolean))].join(' · ')||'Kubernetes workloads');updateBusy();requestAnimationFrame(drawWires);
}
function renderLogs(){
  const pod=state?.pods.find(p=>key(p)===selected);text('selected-name',pod?`/ ${pod.name}`:'/ no workload');
  const logs=pod?.logs||[];
  $('logs').replaceChildren(...(logs.length?logs.slice(-8).map(line=>{const s=typeof line==='string'?line:JSON.stringify(line);return el('div','log-line'+(/error|failure|denied/i.test(s)?' error':''),s);}):[el('p','placeholder','Inject an event to see this pod’s logs.')]));
}
function describe(event){if(event.key)return `${event.pod} · ${event.key}=${event.value}${Number.isFinite(event.noul)?` · ${(event.noul*100).toFixed(0)}% yes`:''}`;return `${event.pod||''}${event.pod?' · ':''}${event.message||names[event.stage]||event.stage}`;}
function renderTrail(){text('event-count',`${events.length} EVENTS`);$('trail').replaceChildren(...events.slice(-16).reverse().map(event=>{const row=el('li');row.append(el('time','',timeLabel(event.at)),el('span',`stage ${event.stage}`,names[event.stage]||event.stage),el('span','trail-description',describe(event)));return row;}));}
function acceptEvents(incoming,animateNew=true){
  for(const event of [...incoming].sort((a,b)=>a.seq-b.seq)){
    if(event.seq<=cursor)continue;
    const id=`${event.namespace}/${event.pod}`,localFlow=pending.get(id);
    if(animateNew&&localFlow&&!localFlow.requestId)break;
    cursor=event.seq;events.push(event);if(!animateNew)continue;
    let flow=flows.get(event.request_id);
    if(!flow&&localFlow&&localFlow.requestId===event.request_id)flow=localFlow;
    if(!flow&&localFlow)continue;
    if(!flow&&event.request_id){flow={podKey:id,scenario:event.scenario||'checkout',requestId:event.request_id,started:performance.now(),chain:Promise.resolve(),hint:'Queued for Cloud',steps:new Set()};pending.set(id,flow);}
    if(!flow)continue;
    if(event.request_id){flow.requestId=event.request_id;flows.set(event.request_id,flow);}
    if(flow.steps.has(event.stage))continue;flow.steps.add(event.stage);
    if(event.stage==='queued'){flow.hint='Queued for Cloud';}
    if(event.stage==='event'){flow.hint='Logs → Expanso';animate(flow,'event');text('activity',`${event.pod}: workload log emitted`);refreshState();}
    if(event.stage==='collected'){flow.hint='Cloud collected logs';text('cloud-detail','Evidence collected');}
    if(event.stage==='judging'){flow.hint='Jev is judging…';animate(flow,'judging');text('jev-status','JUDGING');text('activity',`${event.pod}: waiting for Jev`);}
    if(event.stage==='judged'){flow.hint='Interpretation → Expanso';animate(flow,'judged');text('jev-status',Number.isFinite(event.noul)?`${Math.round(event.noul*100)}% YES`:'VERDICT');text('cloud-detail','Checking Jev’s interpretation');}
    if(['applied','undone','held','error','dry-run'].includes(event.stage)){
      flow.outcome=event.stage;flow.hint=event.stage==='error'?'Event failed':'Expanso checks result';
      if(['applied','undone'].includes(event.stage)){flow.hint='Expanso → Kubernetes → pod';animate(flow,'request');animate(flow,'terminal');}
      flow.chain=flow.chain.then(()=>finish(flow,event));
    }
  }
  events=events.slice(-100);renderTrail();updateBusy();
}
async function finish(flow,event){
  if(pending.get(flow.podKey)===flow)pending.delete(flow.podKey);
  if(flow.requestId)flows.delete(flow.requestId);
  const applied=event.stage==='applied',undone=event.stage==='undone';
  if((applied||undone)&&event.key){const pod=state?.pods.find(p=>key(p)===flow.podKey);if(pod){if(applied)pod.labels[event.key]=event.value;else delete pod.labels[event.key];}stateGeneration++;renderPods();}
  text('result-mark',applied?'+':undone?'−':event.stage==='error'?'!':'◎');
  text('result-title',`${event.pod}: ${applied?'label added':undone?'label removed':event.stage==='error'?'event failed':event.stage==='dry-run'?'dry run completed':'labels unchanged'}.`);
  const explanation=event.message&&event.message!==event.stage?event.message:(event.stage==='held'?(Number.isFinite(event.noul)?`Jev returned ${Math.round(event.noul*100)}% yes; the threshold is 90%.`:'No safe label change for this evidence.'):event.stage==='dry-run'?'Expanso evaluated the request; no Kubernetes change was submitted.':event.stage==='error'?'The request failed; no pod change is confirmed.':'Kubernetes confirmed Expanso’s requested change.');
  text('result-detail',(event.key?`${event.key}=${event.value} · `:'')+explanation);
  const elapsed=Number.isFinite(event.elapsed_ms)?event.elapsed_ms:performance.now()-flow.started;
  text('timing',`${(elapsed/1000).toFixed(2)}s end to end`);text('activity',`${event.pod}: ${names[event.stage].toLowerCase()}`);text('cloud-detail','Read logs → ask → request');
  if(event.stage==='error')showError(explanation);
  updateBusy();await refreshState();renderPods();renderLogs();
}
async function sendEvent(pod){
  const id=key(pod);if(pending.has(id))return;
  selected=id;$('error').hidden=true;
  const flow={podKey:id,scenario,started:performance.now(),chain:Promise.resolve(),hint:'Injecting event…',steps:new Set()};pending.set(id,flow);
  updateBusy();drawWires();animate(flow,'inject');renderLogs();
  text('result-mark','↓');text('result-title',`${scenarios[scenario]} → ${pod.name}`);text('result-detail','Sending the event. Follow the particle into the pod.');text('timing','In flight');
  try{
    if(!session){const r=await fetch('/api/session',{cache:'no-store'});if(!r.ok)throw Error('Could not establish a local session.');session=await r.json();}
    const r=await fetch('/api/event',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token},body:JSON.stringify({namespace:pod.namespace,pod:pod.name,scenario:flow.scenario})});
    const body=await r.json();if(!r.ok)throw Error(body.message||body.error||'Event rejected.');
    if(!body.request_id)throw Error('Restart the adapter to load the event-driven backend.');flow.requestId=body.request_id;flows.set(body.request_id,flow);
    flow.hint='Queued for Cloud';updateBusy();
  }catch(err){pending.delete(id);updateBusy();showError(err.message);text('result-title','Event was not accepted.');text('result-detail',err.message);text('timing','Not submitted');}
}
function renderState(){
  const cloud=state.cloud||{};
  $('available-labels').replaceChildren(...(state.available_labels||[]).map(label=>{const item=el('div','label-choice');item.append(el('code','',`${label.key}=${label.value}`),el('span','',label.meaning));return item;}));
  text('connection',cloud.state==='running'?'Cloud execution running':cloud.state==='stopped'?'Cloud job stopped':'Cloud execution unverified');$('connection-dot').className='dot'+(cloud.state==='running'?' live':'');
  text('mode',state.apply_enabled?'LIVE · WRITES ENABLED':'DRY RUN · NO LABEL WRITES');$('mode').classList.toggle('dry',!state.apply_enabled);
  text('cluster-name',state.cluster_context||'k3s cluster');text('namespace',state.namespace||'Target namespace');text('cloud-status',(cloud.state||'unknown').toUpperCase());renderPods();renderLogs();
  const fields={'Kubernetes context':state.cluster_context,'Cloud job':cloud.job_id,'Execution':cloud.execution_id,'Edge node':cloud.node_id,'Adapter':location.origin,'Label writes':state.apply_enabled?'Enabled':'Disabled'};
  $('runtime-fields').replaceChildren(...Object.entries(fields).flatMap(([k,v])=>[el('dt','',k),el('dd','',v||'Not verified')]));
}
function refreshState(){
  if(refreshing)return refreshing;
  const generation=stateGeneration;
  refreshing=(async()=>{try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw Error('State unavailable');const observed=await r.json();if(generation!==stateGeneration)return;state=observed;if(!initialized){acceptEvents(state.events||[],false);initialized=true;}renderState();}catch{ text('connection','Adapter unavailable');$('connection-dot').className='dot error';text('cloud-status','UNVERIFIED');}finally{refreshing=null;if(generation!==stateGeneration)refreshState();}})();
  return refreshing;
}
async function pollEvents(){
  try{if(initialized){const r=await fetch(`/api/events?after=${cursor}`,{cache:'no-store'});if(!r.ok)throw Error('Event feed unavailable');const body=await r.json();if(Number.isFinite(body.cursor)&&body.cursor<cursor){cursor=0;initialized=false;events=[];flows.clear();pending.clear();session=null;shownLabels.clear();stateGeneration++;text('result-title','Adapter reconnected.');text('result-detail','Ready for a new event. Previous in-flight results are unverified.');text('timing','Ready to inject');await refreshState();}else acceptEvents(body.events||[]);}}
  catch{if(pending.size)text('activity','Event feed disconnected; waiting to reconnect.');}
  finally{eventPollTimer=setTimeout(pollEvents,200);}
}
for(const button of document.querySelectorAll('[data-scenario]'))button.addEventListener('click',()=>{scenario=button.dataset.scenario;for(const b of document.querySelectorAll('[data-scenario]')){b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',String(b===button));}updateBusy();drawWires();});
$('details-toggle').addEventListener('click',()=>{const hidden=!$('runtime-details').hidden;$('runtime-details').hidden=hidden;$('details-toggle').setAttribute('aria-expanded',String(!hidden));$('details-toggle').textContent=hidden?'Inspect runtime +':'Close runtime −';});
window.addEventListener('resize',drawWires);new ResizeObserver(drawWires).observe($('topology'));
window.addEventListener('pagehide',()=>clearTimeout(eventPollTimer));
refreshState().then(pollEvents);setInterval(refreshState,2500);
