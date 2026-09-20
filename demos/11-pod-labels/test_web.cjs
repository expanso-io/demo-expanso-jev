// Browser regression tests with synthetic HTTP fixtures; never call Cloud/Jev.
// Requires Playwright and Chrome installed. Run: node test_web.cjs
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const root=__dirname;
const fonts=path.join(root,'../01-log-triage/fonts');
const base={app:'x',team:'payments',version:'v1.0.0','istio.io/rev':'default'};
const pod=(name,labels={})=>({name,namespace:'jev-label-demo',status:'Running',event_enabled:true,logs:[],labels:{...base,app:name.split('-')[0],...labels}});
const scenarios=[['crashloop','Crash loop',[['undo','routing-tier','stable'],['add','health','degraded']]],['restart','One restart',[['add','health','degraded']]],['healthy','Back to healthy',[['undo','health','degraded'],['add','routing-tier','stable']]]]
  .map(([id,title,prefer])=>({id,title,prefer,why:`why ${id}`,message:`log line for ${id}`}));
const baseState={mode:'live',apply_enabled:true,threshold:0.8,auto:true,cluster_context:'test',namespace:'jev-label-demo',scenarios,
  available_labels:[{key:'routing-tier',value:'stable',meaning:'m'},{key:'health',value:'degraded',meaning:'m'}],
  pods:[pod('analytics-worker'),pod('checkout-api',{'routing-tier':'stable'}),pod('orders-api')],cloud:{state:'running'}};
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
  const file=req.url==='/'?path.join(root,'web/index.html'):req.url.startsWith('/web/')?path.join(root,req.url):req.url.startsWith('/fonts/')?path.join(fonts,path.basename(req.url)):null;
  if(!file||!fs.existsSync(file)){res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(fs.readFileSync(file));});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({headless:true,channel:'chrome'});let page,errors=[],posted=[],events=[];try{
 page=await browser.newPage({viewport:{width:1600,height:900}});page.on('pageerror',e=>errors.push(e.message));
 let state=structuredClone(baseState),seq=0,autoCalls=[],investigationCalls=[],outcome='applied',decisionDelay=0;
 const run=(podName,scenario,op,key,value,noul)=>{const request_id='r'+(posted.length+seq);const common={request_id,pod:podName,namespace:'jev-label-demo'};
   const stages=[['queued',{scenario}],['event',{scenario}],['collected',{key,value,operation:op}],['judging',{key,value,operation:op}],['judged',{key,value,operation:op,noul}],[['held','review'].includes(outcome)?'held':op==='undo'?'undone':'applied',{key,value,operation:op,noul}]];
   stages.forEach(([stage,extra],i)=>setTimeout(()=>{if(stage==='applied')state.pods.find(p=>p.name===podName).labels[key]=value;if(stage==='undone')delete state.pods.find(p=>p.name===podName).labels[key];
     events.push({...common,...extra,stage,seq:++seq,at:Date.now()/1000,message:stage});},i*60+(i>=4?decisionDelay:0)));return request_id;};
 await page.route('**/api/**',async route=>{const url=new URL(route.request().url());let body;
  if(url.pathname==='/api/session')body={csrf_token:'t'};
  else if(url.pathname==='/api/state')body={...state,events};
  else if(url.pathname==='/api/events')body={events:events.filter(e=>e.seq>Number(url.searchParams.get('after'))),cursor:seq};
  else if(url.pathname==='/api/auto'){const b=route.request().postDataJSON();autoCalls.push(b);state.auto=b.on;body={auto:b.on};}
  else if(url.pathname==='/api/investigate'){
    const b=route.request().postDataJSON();investigationCalls.push(b);
    const request_id='investigation-'+investigationCalls.length;
    let incident=(state.investigations||[]).find(i=>i.pod===b.pod);
    if(!incident||b.phase==='restart')incident={id:'incident-'+b.pod,namespace:b.namespace,pod:b.pod,evidence:[]};
    incident.phase=b.phase;incident.status='queued';incident.evidence.push({id:'E'+investigationCalls.length,kind:b.phase,text:b.phase==='evidence'?'OOMKilled: OrderCache.load:212 after release cache limit change':'Pod restart context',source:'pod stdout',synthetic:true});
    state.investigations=[incident];
    const enough=b.phase==='evidence';
    const stages=['event','collected','judging','judged',enough?'investigation_ready':'investigation_waiting'];
    stages.forEach((stage,i)=>setTimeout(()=>{
      incident.status=stage==='investigation_waiting'?'waiting':stage==='investigation_ready'?'ready':'judging';
      incident.score=enough?.98:.12;
      events.push({request_id,namespace:b.namespace,pod:b.pod,scenario:'investigate_'+b.phase,operation:'investigate',stage,seq:++seq,at:Date.now()/1000,noul:incident.score,investigation:structuredClone(incident)});
    },i*90));body={request_id,stage:'queued'};
  }
  else if(url.pathname==='/api/event'){const b=route.request().postDataJSON();posted.push(b);const s=scenarios.find(x=>x.id===b.scenario);const target=state.pods.find(p=>p.name===b.pod);
    const [op,key,value]=s.prefer.find(([o,k,v])=>o==='undo'?target.labels[k]===v:!(k in target.labels))||s.prefer[0];const request_id=run(b.pod,b.scenario,outcome==='review'?'review':op,key,value,['held','review'].includes(outcome)?0.08:0.93);body={request_id,stage:'queued'};}
  else{await route.fulfill({status:404,body:'{}'});return;}
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});});
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.locator('[data-pod]').first().waitFor();

 assert.equal(await page.locator('[data-pod]').count(),3);
 assert.equal(await page.locator('.legend-item').count(),scenarios.length);
 assert.equal(await page.locator('.processor img').count(),2);
 const checkout=page.locator('[data-pod="jev-label-demo/checkout-api"]');
 assert.equal(await checkout.locator('.label').count(),4);
 assert.equal(await checkout.locator('.label.managed').count(),0,'refresh never highlights existing labels');
 assert.ok(await checkout.locator('.label').first().evaluate(n=>parseFloat(getComputedStyle(n).fontSize)<=13),'labels stay small');
 assert.match(await page.locator('#mode').textContent(),/acts at ≥ 80% yes/);
 console.log('PASS pods render base and managed labels as small chips, with a legend entry per event');

 for(const p of state.pods)events.push({seq:++seq,stage:'routine',destination:'general_logs',pod:p.name,namespace:p.namespace,count:6,at:Date.now()/1000});
 await page.waitForFunction(()=>document.querySelectorAll('.routine-packet').length>=3);
 assert.equal(await page.locator('#packets .packet').count(),0);assert.equal(posted.length,0);
 assert.equal(await page.locator('#routine-count').textContent(),'18');assert.equal(await page.locator('#asked-count').textContent(),'0');
 assert.equal(await page.locator('#logged-count').textContent(),'18');
 assert.equal(await page.locator('#logs-node').isVisible(),true);
 assert.ok(await page.locator('.wire.general').count());
 console.log('PASS routine lines animate and are counted without any Jev question');

 await page.evaluate(()=>{window.signalDurations=[];const original=travel;travel=(path,color,duration,routine)=>{if(!routine)window.signalDurations.push(duration);return original(path,color,duration,routine);};});
 await checkout.click();await page.locator('[data-scenario="crashloop"]').click();
 await page.waitForTimeout(500);
 assert.equal(state.pods.find(p=>p.name==='checkout-api').labels['routing-tier'],undefined,'backend completed while visual replay continues');
 assert.ok(await page.locator('#packets .packet').count(),'visual replay is still running');

 await page.waitForFunction(()=>document.querySelector('#feed li .did')?.textContent.includes('− routing-tier=stable'),{},{timeout:5000});
 assert.deepEqual(posted[0],{namespace:'jev-label-demo',pod:'checkout-api',scenario:'crashloop'});
 await page.waitForFunction(()=>!document.querySelector('[data-pod="jev-label-demo/checkout-api"] .label[data-key="routing-tier"]:not(.removed):not(.leaving)'));
 assert.match(await page.locator('#feed li .said').first().textContent(),/no longer true\? Jev 93% yes/);
 assert.match(await page.locator('#api-line').textContent(),/PATCH .*checkout-api.*− routing-tier=stable/);
 assert.deepEqual(await page.evaluate(()=>window.signalDurations),[400,900,500,500,800,600]);
 console.log('PASS a removal is shown only after the confirmed receipt, with the question and answer');

 await page.locator('[data-scenario="crashloop"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-pod="jev-label-demo/checkout-api"] .label[data-key="health"]'),{},{timeout:5000});
 assert.equal(await page.locator('#asked-count').textContent(),'2');
 const color=await checkout.locator('.label[data-key="health"]').evaluate(n=>n.style.getPropertyValue('--lc'));
 assert.equal(color,'#cf2e3d');
 assert.equal(await checkout.locator('.label[data-key="health"] i').textContent(),'health=');
 assert.equal(await checkout.locator('.label[data-key="health"] i').isVisible(),true);
 await page.waitForTimeout(5100);
 assert.equal(await checkout.locator('.label[data-key="health"]').count(),1,'highlight lasts at least five full seconds');
 await page.waitForFunction(()=>!document.querySelector('[data-pod="jev-label-demo/checkout-api"] .label[data-key="health"]'),{},{timeout:7500});
 assert.equal(state.pods.find(p=>p.name==='checkout-api').labels.health,'degraded');
 console.log('PASS label highlight expires after six seconds without changing Kubernetes state');

 outcome='held';const before=await checkout.locator('.label:not(.leaving)').count();
 await page.locator('[data-scenario="restart"]').click();
 await page.waitForFunction(()=>document.querySelector('#feed li .did')?.textContent==='not supported',{},{timeout:5000});
 assert.equal(await checkout.locator('.label:not(.leaving)').count(),before);
 assert.equal(await page.locator('#packets .packet').count(),0);
 console.log('PASS a low answer changes nothing and sends nothing to Kubernetes');
 outcome='review';
 await page.locator('[data-scenario="restart"]').click();
 await page.waitForFunction(()=>document.querySelector('.pod.selected .pod-event').textContent==='Already set');
 assert.equal(await checkout.locator('.label[data-key="health"]').textContent(),'health=degraded');
 assert.equal(state.pods.find(p=>p.name==='checkout-api').labels.health,'degraded');
 outcome='held';
 decisionDelay=2000;
 const noise=setInterval(()=>{for(const pod of state.pods)events.push({seq:++seq,stage:'routine',destination:'general_logs',pod:pod.name,namespace:pod.namespace,count:3,at:Date.now()/1000});},200);
 try{
   await page.waitForFunction(()=>document.querySelectorAll('.routine-packet').length>0);
   const beforeLogs=Number((await page.locator('#logged-count').textContent()).replaceAll(',',''));
   await page.locator('[data-scenario="restart"]').click();
   await page.waitForFunction(()=>document.getElementById('jev-status').textContent==='…');
   for(let i=0;i<12;i++){await page.waitForTimeout(100);assert.ok(await page.locator('.routine-packet').count(),'gray stream continues during Jev');}
   assert.ok(Number((await page.locator('#logged-count').textContent()).replaceAll(',',''))>beforeLogs);
   await page.waitForFunction(()=>!document.querySelector('.pod.busy'));
 }finally{clearInterval(noise);decisionDelay=0;}
 console.log('PASS gray traffic continues throughout a delayed Jev decision');


 await page.locator('#auto-toggle').click();await page.waitForFunction(()=>document.getElementById('auto-toggle').textContent==='Resume events');
 assert.deepEqual(autoCalls,[{on:false}]);
 console.log('PASS events can be paused');

 await page.locator('[data-lane="investigation"]').click();
 assert.equal(await page.locator('#agent-node').count(),0);
assert.equal(await page.locator('#evidence-cards').isVisible(),false);
 assert.equal(await page.locator('.legend').isVisible(),false);
 await page.locator('[data-phase="restart"]').click();
 await page.waitForFunction(()=>document.getElementById('gate-status').textContent==='Wait');
 await page.waitForFunction(()=>!document.querySelector('[data-phase="context"]').disabled);
 assert.equal(await page.locator('.evidence-card').count(),1);
 await page.locator('[data-phase="context"]').click();
 await page.waitForFunction(()=>document.querySelectorAll('.evidence-card').length===2&&!document.querySelector('[data-phase="evidence"]').disabled);
 await page.locator('[data-phase="evidence"]').click();
 await page.waitForFunction(()=>document.getElementById('gate-status').textContent==='Investigate');
 await page.waitForFunction(()=>!document.querySelector('[data-phase="restart"]').disabled);
 assert.equal(await page.locator('.evidence-card').count(),3);
 assert.deepEqual(investigationCalls.map(x=>x.phase),['restart','context','evidence']);
 assert.ok(investigationCalls.every(x=>x.pod==='checkout-api'));
 assert.match(await page.locator('#jev-question').textContent(),/Investigate/);
 assert.equal(await page.locator('#api-line').textContent().then(t=>t.includes('investigate')),false);
 console.log('PASS investigation holds on sparse evidence, accumulates context, shows a decision without another provider, never animates a Kubernetes patch');
 if(process.env.POD_UI_SCREENSHOT){await page.locator('#mode').evaluate(n=>n.textContent='BROWSER TEST');await page.locator('.provenance').evaluate(n=>n.textContent='BROWSER TEST · MOCK RESPONSES');await page.locator('#connection').evaluate(n=>n.textContent='No Cloud connection');await page.screenshot({path:process.env.POD_UI_SCREENSHOT,fullPage:true});}
 for(const width of [1600,1280,1024,768,390]){await page.setViewportSize({width,height:1000});await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`investigation overflow at ${width}`);}
 await page.locator('[data-lane="labels"]').click();
 for(const width of [1600,1280,1024,768,390]){await page.setViewportSize({width,height:900});await page.waitForTimeout(80);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`no horizontal scroll at ${width}`);}
 await page.setViewportSize({width:1280,height:720});await page.waitForTimeout(80);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),'fits one 1280x720 screen');
 const positions=await page.evaluate(()=>['cloud-node','jev-node','logs-node','kube-node'].map(id=>{const r=document.getElementById(id).getBoundingClientRect();return{top:r.top,bottom:r.bottom,height:r.height};}));
 assert.equal(positions[0].height,positions[1].height);assert.equal(positions[0].height,positions[2].height);
 assert.ok(positions.slice(0,3).every(p=>p.bottom<positions[3].bottom));
 const header=await checkout.evaluate(n=>{const p=n.getBoundingClientRect();return [...n.querySelectorAll('.pod-icon,.pod-name,.pod-phase')].every(x=>{const r=x.getBoundingClientRect();return Math.abs(r.left+r.width/2-p.left-p.width/2)<2;});});
 assert.ok(header,'pod header is centered');

 assert.deepEqual(errors,[]);
 console.log('PASS no page errors, no horizontal scroll at any width, fits one screen');
}catch(e){console.error('page errors:',errors,'\nfeed:',await page.locator('#feed').innerText().catch(()=>'?'),'\nposted:',JSON.stringify(posted),'\nevents:',events.map(x=>x.stage).join(','));throw e;}finally{await browser.close();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
