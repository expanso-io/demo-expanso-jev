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
 let state=structuredClone(baseState),seq=0,autoCalls=[],outcome='applied';
 const run=(podName,scenario,op,key,value,noul)=>{const request_id='r'+(posted.length+seq);const common={request_id,pod:podName,namespace:'jev-label-demo'};
   const stages=[['queued',{scenario}],['event',{scenario}],['collected',{key,value,operation:op}],['judging',{key,value,operation:op}],['judged',{key,value,operation:op,noul}],[outcome==='held'?'held':op==='undo'?'undone':'applied',{key,value,operation:op,noul}]];
   stages.forEach(([stage,extra],i)=>setTimeout(()=>{if(stage==='applied')state.pods.find(p=>p.name===podName).labels[key]=value;if(stage==='undone')delete state.pods.find(p=>p.name===podName).labels[key];
     events.push({...common,...extra,stage,seq:++seq,at:Date.now()/1000,message:stage});},i*60));};
 await page.route('**/api/**',async route=>{const url=new URL(route.request().url());let body;
  if(url.pathname==='/api/session')body={csrf_token:'t'};
  else if(url.pathname==='/api/state')body={...state,events};
  else if(url.pathname==='/api/events')body={events:events.filter(e=>e.seq>Number(url.searchParams.get('after'))),cursor:seq};
  else if(url.pathname==='/api/auto'){const b=route.request().postDataJSON();autoCalls.push(b);state.auto=b.on;body={auto:b.on};}
  else if(url.pathname==='/api/event'){const b=route.request().postDataJSON();posted.push(b);const s=scenarios.find(x=>x.id===b.scenario);const target=state.pods.find(p=>p.name===b.pod);
    const [op,key,value]=s.prefer.find(([o,k,v])=>o==='undo'?target.labels[k]===v:!(k in target.labels))||s.prefer[0];run(b.pod,b.scenario,op,key,value,outcome==='held'?0.08:0.93);body={request_id:'x',stage:'queued'};}
  else{await route.fulfill({status:404,body:'{}'});return;}
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});});
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.locator('[data-pod]').first().waitFor();

 assert.equal(await page.locator('[data-pod]').count(),3);
 assert.equal(await page.locator('.legend-item').count(),scenarios.length);
 assert.equal(await page.locator('.processor img').count(),2);
 const checkout=page.locator('[data-pod="jev-label-demo/checkout-api"]');
 assert.equal(await checkout.locator('.label').count(),5);
 assert.equal(await checkout.locator('.label.managed').count(),1,'only catalog labels are marked as managed');
 assert.ok(await checkout.locator('.label').first().evaluate(n=>parseFloat(getComputedStyle(n).fontSize)<=13),'labels stay small');
 assert.match(await page.locator('#mode').textContent(),/acts at ≥ 80% yes/);
 console.log('PASS pods render base and managed labels as small chips, with a legend entry per event');

 for(const p of state.pods)events.push({seq:++seq,stage:'routine',pod:p.name,namespace:p.namespace,count:6,at:Date.now()/1000});
 await page.waitForFunction(()=>document.querySelectorAll('.routine-packet').length>=3);
 assert.equal(await page.locator('#packets .packet').count(),0);assert.equal(posted.length,0);
 assert.equal(await page.locator('#routine-count').textContent(),'18');assert.equal(await page.locator('#asked-count').textContent(),'0');
 console.log('PASS routine lines animate and are counted without any Jev question');

 await checkout.click();await page.locator('[data-scenario="crashloop"]').click();
 await page.waitForFunction(()=>document.querySelector('#feed li .did')?.textContent.includes('− routing-tier=stable'),{},{timeout:5000});
 assert.deepEqual(posted[0],{namespace:'jev-label-demo',pod:'checkout-api',scenario:'crashloop'});
 await page.waitForFunction(()=>!document.querySelector('[data-pod="jev-label-demo/checkout-api"] .label[data-key="routing-tier"]:not(.leaving)'));
 assert.match(await page.locator('#feed li .said').first().textContent(),/no longer true\? Jev 93% yes/);
 assert.match(await page.locator('#api-line').textContent(),/PATCH .*checkout-api.*− routing-tier=stable/);
 console.log('PASS a removal is shown only after the confirmed receipt, with the question and answer');

 await page.locator('[data-scenario="crashloop"]').click();
 await page.waitForFunction(()=>document.querySelector('[data-pod="jev-label-demo/checkout-api"] .label[data-key="health"]'),{},{timeout:5000});
 assert.equal(await page.locator('#asked-count').textContent(),'2');
 console.log('PASS the next event adds the warning label');

 outcome='held';const before=await checkout.locator('.label:not(.leaving)').count();
 await page.locator('[data-scenario="restart"]').click();
 await page.waitForFunction(()=>document.querySelector('#feed li .did')?.textContent==='no change',{},{timeout:5000});
 assert.equal(await checkout.locator('.label:not(.leaving)').count(),before);
 assert.equal(await page.locator('#packets .packet').count(),0);
 console.log('PASS a low answer changes nothing and sends nothing to Kubernetes');

 await page.locator('#auto-toggle').click();await page.waitForFunction(()=>document.getElementById('auto-toggle').textContent==='Resume events');
 assert.deepEqual(autoCalls,[{on:false}]);
 console.log('PASS events can be paused');

 for(const width of [1600,1280,1024,768,390]){await page.setViewportSize({width,height:900});await page.waitForTimeout(80);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`no horizontal scroll at ${width}`);}
 await page.setViewportSize({width:1600,height:900});await page.waitForTimeout(80);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight),'fits one 1600x900 screen');
 assert.deepEqual(errors,[]);
 console.log('PASS no page errors, no horizontal scroll at any width, fits one screen');
}catch(e){console.error('page errors:',errors,'\nfeed:',await page.locator('#feed').innerText().catch(()=>'?'),'\nposted:',JSON.stringify(posted),'\nevents:',events.map(x=>x.stage).join(','));throw e;}finally{await browser.close();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
