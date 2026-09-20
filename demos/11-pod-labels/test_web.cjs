// Browser regression tests with synthetic HTTP fixtures; never call Cloud/Jev.
// Requires Playwright and Chrome installed. Run: node test_web.cjs
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require('playwright');
const root=__dirname;
const baseState={mode:'live',apply_enabled:true,cluster_context:'test-fixture',namespace:'jev-label-demo',available_labels:[{key:'routing-tier',value:'stable',meaning:'Eligible for healthy HTTP traffic'},{key:'routing-tier',value:'batch',meaning:'Eligible for batch processing'}],cloud:{state:'running'},pods:['analytics-worker','checkout-api','orders-api'].map(name=>({name,namespace:'jev-label-demo',event_enabled:true,status:'Running',node:'test-node',labels:{app:name.includes('analytics')?'analytics':'checkout'},logs:[]})),events:[]};
const server=http.createServer((req,res)=>{const known={'/':'web/index.html','/web/style.css':'web/style.css','/web/app.js':'web/app.js'};let file=known[req.url];if(req.url.startsWith('/fonts/')&&/^[\w-]+\.woff2$/.test(req.url.slice(7)))file='../01-log-triage/fonts/'+req.url.slice(7);if(!file){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',req.url.endsWith('.js')?'text/javascript':req.url.endsWith('.css')?'text/css':req.url.endsWith('.woff2')?'font/woff2':'text/html');res.end(fs.readFileSync(path.join(root,file)));});
(async()=>{await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const browser=await chromium.launch({headless:true,channel:'chrome'});try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let state=structuredClone(baseState),events=[],seq=0,posted=[],stageDelay=65;
 await page.route('**/api/**',async route=>{const url=new URL(route.request().url());let body;
  if(url.pathname==='/api/session')body={csrf_token:'test-csrf'};
  else if(url.pathname==='/api/state')body={...state,events};
  else if(url.pathname==='/api/events')body={events:events.filter(e=>e.seq>Number(url.searchParams.get('after'))),cursor:seq};
  else if(url.pathname==='/api/event'){
   const request=route.request().postDataJSON();posted.push(request);const request_id='test-'+posted.length;
   const stages=['queued','event','collected','judging','judged','applied'];
   for(const [index,stage] of stages.entries())setTimeout(()=>{const event={...request,request_id,seq:++seq,stage,at:Date.now()/1000,message:stage,noul:stage==='judged'||stage==='applied'?.96:undefined};if(stage==='applied'){event.key='routing-tier';event.value='stable';event.elapsed_ms=400;state.pods.find(p=>p.name===request.pod).labels['routing-tier']='stable';}events.push(event);},index*stageDelay);
   body={request_id,stage:'queued'};
  }else{await route.fulfill({status:404,body:'{}'});return;}
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.locator('[data-pod]').first().waitFor();
 assert.equal(await page.locator('.label-choice').count(),2);
 assert.equal(await page.locator('.pod-phase').filter({hasText:'Running'}).count(),3);
 assert.equal(await page.locator('[data-scenario]').count(),5);assert.equal(await page.locator('[data-pod]:enabled').count(),3);
 await page.evaluate(()=>{window.testRoutes=[];new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)if(n.dataset?.route)window.testRoutes.push(n.dataset.route);}).observe(document.getElementById('packets'),{childList:true});});
 const target=page.locator('[data-pod="jev-label-demo/checkout-api"]');await target.click();
 await page.waitForFunction(()=>document.querySelector('.packet[data-route="event-to-pod"]'),{},{timeout:500});
 assert.equal(await target.locator('.label').filter({hasText:'routing-tier=stable'}).count(),0,'No optimistic label before confirmed return');
 await page.waitForFunction(()=>document.getElementById('result-title').textContent.includes('label added'),{},{timeout:5000});
 assert.deepEqual(await page.evaluate(()=>window.testRoutes),['event-to-pod','pod-to-cloud','cloud-to-jev','jev-to-cloud','cloud-to-pod']);
 await page.waitForFunction(()=>document.querySelector('[data-pod="jev-label-demo/checkout-api"]').textContent.includes('routing-tier=stable'));
 console.log('PASS immediate injection, five-leg particle flow, and confirmation-gated labels');
 for(const [pod,scenario] of [['analytics-worker','analytics'],['orders-api','security']]){await page.locator(`[data-scenario="${scenario}"]`).click();await page.locator(`[data-pod="jev-label-demo/${pod}"]`).click();await page.waitForFunction(p=>document.getElementById('result-title').textContent.startsWith(p+': label added'),pod);}
 assert.deepEqual(posted.map(e=>[e.pod,e.scenario]),[['checkout-api','checkout'],['analytics-worker','analytics'],['orders-api','security']]);
 console.log('PASS all three pod targets and multiple event types');
 stageDelay=300;
 const startCount=posted.length;
 for(const [index,pod] of ['checkout-api','analytics-worker','orders-api'].entries()){
  const button=page.locator(`[data-pod="jev-label-demo/${pod}"]`);
  assert.equal(await button.isEnabled(),true,`${pod} remains clickable while other pods process`);
  await button.click();
  assert.equal(await page.locator('[data-pod]:disabled').count(),index+1);
 }
 await page.waitForFunction(()=>document.querySelectorAll('[data-pod]:enabled').length===3);
 assert.deepEqual(posted.slice(startCount).map(e=>e.pod),['checkout-api','analytics-worker','orders-api']);
 console.log('PASS simultaneous injection into all three pods and re-enabled controls');
 for(const width of [1440,1024,768,390]){await page.setViewportSize({width,height:1100});await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow at ${width}`);
  const geometry=await page.evaluate(()=>{const top=document.getElementById('topology').getBoundingClientRect(),c=document.getElementById('cloud-node').getBoundingClientRect(),j=document.getElementById('jev-node').getBoundingClientRect(),label=[...document.querySelectorAll('.wire-label')].find(x=>x.textContent==='evidence');return {expected:(c.right+j.left)/2-top.x,actual:Number(label.getAttribute('x')),anchor:label.getAttribute('class'),source:document.getElementById('event-source').getBoundingClientRect().bottom,pod:document.querySelector('[data-pod]').getBoundingClientRect().top};});assert.ok(Math.abs(geometry.expected-geometry.actual)<1);assert.ok(geometry.source<geometry.pod);console.log('PASS layout and centered arrow label at '+width);}
 await page.emulateMedia({reducedMotion:'reduce'});await page.locator('[data-scenario="recovery"]').focus();await page.keyboard.press('Enter');assert.equal(await page.locator('[data-scenario="recovery"]').getAttribute('aria-pressed'),'true');assert.deepEqual(errors,[]);console.log('PASS keyboard selection, reduced motion, no browser errors');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
