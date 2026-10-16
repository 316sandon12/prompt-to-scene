/* Browser-only regression. Simulated API; never starts Blender, Unity or UE.
   Run with Playwright available: node tools/ui_smoke.cjs
   Optional: --screenshots .local/ui-smoke (only final gallery/canvas/setup views).
   PTS_BROWSER_CHANNEL defaults to an installed Chrome, no browser downloads. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'src/prompt_to_scene');
const outIndex = process.argv.indexOf('--screenshots');
const screenshots = outIndex >= 0 ? path.resolve(process.argv[outIndex + 1]) : null;
if (screenshots) fs.mkdirSync(screenshots, {recursive:true});
const image = file => 'data:image/png;base64,' + fs.readFileSync(path.join(root, file)).toString('base64');
const art = {
  potion: image('examples/images/healing-potion.png'),
  chair: image('docs/images/authoring-chair.png'),
  barrel: image('docs/images/authoring-barrel.png'),
  forest: image('docs/images/apothecary-scene-v0.14.png')
};
const rev = 'a'.repeat(32);
const settings = {kind:'icon',width:512,height:512,fit:'contain',transparent:true,border:[0,0,0,0]};
const gameImage = asset_id => ({asset_id,current:{revision:rev},revisions:[{revision:rev,settings,created_utc:'2026-10-16T08:00:00Z',report:{has_alpha:true}}]});
const item = {item_id:'forest_potion',name:'林间 · 恢复药剂',description:'温暖的森林药剂师风格，关联模型、透明图标与拾取物。',model_asset_id:'potion_model',icon_asset_id:'potion_icon',icon_revision:rev,item_path:'Assets/Game/Items/ForestPotion.asset'};
const fixture = () => ({
  version:'0.15.0',active:'/ui-fixture/森林药剂师 · 界面演示',target:{engine:'unity',editor_responding:true,editor:{playing:false}},
  assets:['potion_model','mint_reading_chair','oak_barrel'].map(asset_id=>({asset_id,request_id:rev,status:'imported'})),
  images:[gameImage('potion_icon'),gameImage('forest_reference')],
  creations:{'game-items':[item],'game-screens':[{screen_id:'forest_inventory',title:'药剂师的行囊',kind:'inventory',item_ids:[item.item_id],prefab_path:'Assets/UI/Inventory.prefab'}]},
  layouts:[],providers:[],game_art:{world:'森林药剂师'},
  tasks:[{request_id:'run',status:'building',kind:'production',description:'制作草药架',stage:'准备模型'}, {request_id:'done',status:'completed',description:'导入恢复药剂'},{request_id:'failed',status:'error',description:'导入旧木柜',error:'源文件不存在'}]
});
let state=fixture(), delayWorkspace=null, failState=false, requests=[];
const profile={organization:{destination:'Assets/GameAssets',rules:{}},preparation:{triangle_budget:50000,texture_size:1024,collision:'convex',lod_ratios:[.5,.25]},intake:{folder:'AssetInbox',enabled:false}};
async function api(action, values={}) {
  requests.push({action,values});
  if(action==='state') { if(failState)throw Error('UI test: connection unavailable'); return structuredClone(state); }
  if(action==='inspect_asset')return {asset_id:values.asset_id,current:{request_id:rev},history:[],metadata:{report:{parts:{body:{objects:['body']}}},recipe:{}}};
  if(action==='profile')return profile;
  if(action==='image')return {url: values.kind==='studio' ? (values.asset_id==='oak_barrel'?art.barrel:art.chair) : values.asset_id==='forest_reference'?art.forest:art.potion};
  if(action==='workflow'){
    const v=values.values||{};
    switch(values.action){
      case 'creation_workspace':
        if(delayWorkspace)await new Promise(resolve=>{delayWorkspace.release=resolve;});
        return {item,images:[gameImage(item.icon_asset_id)],screens:state.creations?.['game-screens']||[]};
      case 'view_model': return {status:'completed',model_revision:rev};
      case 'model_view_data': return {bounds:[[0,0,0],[1,1,1]],parts:[{name:'body',position:[0,0,0,1,0,0,0,0,1],normal:[0,-1,0,0,-1,0,0,-1,0],color:[.2,.4,.3,.2,.4,.3,.2,.4,.3]}]};
      case 'gameplay_flows':return {flows:[]};
      case 'creative_tasks':return {plans:[]};
      case 'art_directions':return {directions:[]};
      case 'creation_updates':return {updates:[]};
      case 'adapter_plans':return {adapters:[]};
      case 'game_deliveries':return {deliveries:[]};
      case 'art_samples':return {theme:{},samples:[]};
      default:throw Error('Unexpected workflow (must explicitly test mutations): '+values.action+' '+JSON.stringify(v));
    }
  }
  throw Error('Unexpected action: '+action);
}
let embeddedHtml=fs.readFileSync(path.join(source,'workbench.html'),'utf8').replace('<link rel="stylesheet" href="/studio.css">','<style>'+fs.readFileSync(path.join(source,'studio.css'),'utf8')+'</style>');
for(const name of ['model_viewer.js','workbench.js','creations.js','gameplay.js','creative_tasks.js'])embeddedHtml=embeddedHtml.replace(`<script src="/${name}" defer></script>`,()=>'<script>'+fs.readFileSync(path.join(source,name),'utf8')+'</script>');
const server=http.createServer(async(req,res)=>{
  try{
    if(req.url==='/api/state'){res.setHeader('Content-Type','application/json');res.end(JSON.stringify({...state,projects:[],blender:'/fixture/Blender',clients:{codex:'/fixture/codex',harness:'/fixture/dsh',harness_profiles:['web']},reviews:[]}));return;}
    if(req.url==='/api/workbench'){
      let body='';for await(const chunk of req)body+=chunk;
      const data=JSON.parse(body);res.setHeader('Content-Type','application/json');res.end(JSON.stringify(await api(data.action,data.values)));return;
    }
    if(req.url==='/embed'){
      res.setHeader('Content-Type','text/html');res.end(`<style>body{margin:0}iframe{width:100%;height:1100px;border:0}</style><iframe title="MCP App" src="/embedded"></iframe><script>window.addEventListener('message',async e=>{const m=e.data;if(!m.id)return;let result={};if(m.method==='ui/initialize')result={hostCapabilities:{}};if(m.method==='tools/call'){const r=await fetch('/api/workbench',{method:'POST',body:JSON.stringify(m.params.arguments)});result={structuredContent:await r.json()};}e.source.postMessage({jsonrpc:'2.0',id:m.id,result},'*');});</script>`);return;
    }
    if(req.url==='/embedded'){res.setHeader('Content-Type','text/html');res.end(embeddedHtml);return;}
    const name = req.url==='/'?'setup.html':req.url==='/workbench'?'workbench.html':req.url.slice(1);
    if(!/^[a-z_]+\.(html|css|js)$/.test(name)){res.writeHead(404).end();return;}
    res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');
    res.end(fs.readFileSync(path.join(source,name)));
  }catch(e){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:e.message}));}
});
const visible=async(page,selector)=>page.locator(selector).waitFor({state:'visible',timeout:10000});
async function noOverflow(page,label){assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),label+' horizontal overflow');}
async function shot(page,name){if(screenshots)await page.screenshot({path:path.join(screenshots,name+'.png'),fullPage:false});}
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base='http://127.0.0.1:'+server.address().port;
  const browser=await chromium.launch({headless:true,channel:process.env.PTS_BROWSER_CHANNEL||'chrome'});
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
  const page=await context.newPage(), errors=[];page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(base+'/workbench#ui-test');
    await page.waitForSelector('.creation-card');await page.locator('.gallery-art img').first().waitFor();
    assert.equal(await page.locator('.creation-card').count(),5);
    assert.equal(await page.locator('.studio-nav button').count(),5);
    assert.equal(await page.locator('body').getAttribute('data-view'),'gallery');
    assert.equal(await page.locator('#workspaceGrid').isVisible(),false);
    assert(requests.every(r=>['state','image'].includes(r.action)),'Browsing gallery must not render/generate');
    assert.deepEqual(await page.evaluate(()=>{const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return ids.filter((id,i)=>ids.indexOf(id)!==i);}),[],'Duplicate IDs');
    await shot(page,'gallery');
    await page.locator('[data-gallery-filter=model]').click();assert.equal(await page.locator('.creation-card').count(),2);
    await page.locator('#gallerySearch').fill('mint');assert.equal(await page.locator('.creation-card').count(),1);
    await page.locator('#gallerySearch').fill('missing');await visible(page,'.gallery-empty');
    await page.getByRole('button',{name:'清除筛选',exact:true}).click();assert.equal(await page.locator('.creation-card').count(),5);
    // Open model uses only retained image. Explicit viewer button reads geometry.
    await page.getByRole('button',{name:'打开作品：mint_reading_chair',exact:true}).click();
    await page.waitForSelector('#previews img');await visible(page,'#creationComposer');
    assert.equal(await page.locator('#asset').inputValue(),'mint_reading_chair');
    assert(!requests.some(r=>r.values.action==='view_model'));
    await page.locator('#creationPrompt').fill('保留椅子轮廓，把坐垫改成暖灰色。');
    await page.locator('#creationPrompt').blur();
    const createBox=await page.locator('#creationBrief').boundingBox();assert(createBox.y+createBox.height<=1000,'Canvas composer must fit desktop viewport');
    await shot(page,'canvas');
    await page.locator('#expandPreview').click();assert.equal(await page.locator('.controls-panel').isVisible(),false);
    await page.keyboard.press('Escape');await visible(page,'.controls-panel');
    await page.locator('#creationPrompt').press('Control+Enter');await visible(page,'#creationHandoffBox');
    const brief=await page.locator('#creationHandoff').inputValue();assert(brief.includes('mint_reading_chair')&&brief.includes('保持已有 ID'));
    await page.getByRole('button',{name:'旋转模型 / 点选部件',exact:true}).click();
    await page.waitForSelector('canvas.visual-canvas');
    await page.locator('[aria-label="预览部件"]').selectOption('body');
    await page.waitForSelector('#edit:not([hidden])');
    assert.equal(await page.locator('#part').inputValue(),'body');await visible(page,'canvas.visual-canvas');
    // Every old tool remains reachable, keyboard tabs only cycle through this group.
    await page.locator('#tab-edit').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#review').isVisible(),true);
    await page.locator('#backGallery').click();await page.getByRole('button',{name:'打开作品：林间 · 恢复药剂',exact:true}).click();
    await page.waitForSelector('#creationFocus button');await visible(page,'#previews img');
    await page.getByRole('button',{name:'局部修改图标',exact:true}).click();await visible(page,'#regionEditor');
    await page.locator('#regionRect').fill('0.1, 0.2, 0.3, 0.4');await page.locator('#setRegion').click();
    assert.equal(await page.locator('#regionRect').inputValue(),'0.1, 0.2, 0.3, 0.4');
    await page.locator('#backGallery').click();await page.getByRole('button',{name:'打开作品：药剂师的行囊',exact:true}).click();
    await visible(page,'.screen-structure');assert.equal(await page.locator('#screenId').inputValue(),'forest_inventory');
    for(const [view,tabs] of Object.entries({create:['creations','generate','images','edit','review','performance'],scene:['compose','level','gameplay','flows'],tasks:['missions'],project:['samples','library','organizer','pipeline']})){
      await page.locator(`.studio-nav [data-view=${view}]`).click();
      for(const tab of tabs){await page.locator('#tab-'+tab).click();await visible(page,'#'+tab);await noOverflow(page,tab);}
    }
    assert.equal(await page.locator('#notice.error').count(),0,'Unexpected tool error');
    await page.evaluate(()=>window.PTS.showImage({kind:'engine',request_id:'fixture'},'材质适配预览'));
    await visible(page,'#pipeline');await visible(page,'#previews img');
    assert.equal(await page.locator('body').getAttribute('data-view'),'project');
    await page.locator('#tab-pipeline').click();
    await shot(page,'project');
    await page.locator('.studio-nav [data-view=tasks]').click();await visible(page,'#taskTray');await shot(page,'tasks');
    await page.locator('[data-task-filter=attention]').click();assert.equal(await page.locator('#tasks .task-card').count(),1);
    assert((await page.locator('#tasks').innerText()).includes('源文件不存在'));
    await page.locator('#tasks button').first().click();assert(await page.locator('#resultDetails').evaluate(n=>n.open));
    await page.evaluate(()=>window.PTS.showImage({kind:'game_image',asset_id:'forest_reference',request_id:'fixture'},'任务图片'));
    assert.equal(await page.evaluate(()=>window.PTS.context().id),'forest_reference','Task previews must not retain another artwork edit target');
    // Navigating away or switching projects must discard late artwork responses.
    await page.locator('.studio-nav [data-view=gallery]').click();delayWorkspace={};
    await page.getByRole('button',{name:'打开作品：林间 · 恢复药剂',exact:true}).click({noWaitAfter:true});
    await page.waitForFunction(()=>document.body.dataset.view==='create');
    while(!delayWorkspace.release)await new Promise(r=>setTimeout(r,10));
    state={...fixture(),active:'/ui-fixture/Other',assets:[],images:[],creations:{}};
    await page.evaluate(()=>window.PTS.refresh());delayWorkspace.release();delayWorkspace=null;
    await page.waitForFunction(()=>document.body.dataset.view==='gallery');
    assert.equal(await page.locator('#creationFocus').isVisible(),false);
    assert.equal(await page.locator('#previews img').count(),0);
    await visible(page,'.gallery-empty');
    state=fixture();await page.evaluate(()=>window.PTS.refresh());
    for(const width of [1024,768,390,320]){
      await page.setViewportSize({width,height:900});await noOverflow(page,'gallery '+width);
      await page.getByRole('button',{name:'打开作品：mint_reading_chair',exact:true}).click();await page.waitForSelector('#previews img');await noOverflow(page,'canvas '+width);
      await visible(page,'#creationBrief');await page.locator('#backGallery').click();
    }
    for(const [view,tabs] of Object.entries({scene:['compose','level','gameplay','flows'],tasks:['missions'],project:['samples','library','organizer','pipeline']})){
      await page.locator(`.studio-nav [data-view=${view}]`).click();
      for(const tab of tabs){await page.locator('#tab-'+tab).click();await noOverflow(page,'320px '+tab);}
    }
    state={...fixture(),active:null,target:null,assets:[],images:[],creations:{},tasks:[]};await page.evaluate(()=>window.PTS.refresh());
    await visible(page,'.gallery-empty a');
    failState=true;await page.locator('#refreshGallery').click();await visible(page,'#notice.error');failState=false;
    assert((await page.locator('#notice').textContent()).includes('connection unavailable'));
    state=fixture();await page.setViewportSize({width:1440,height:1000});
    await page.goto(base+'/embed');const app=page.frameLocator('iframe');await app.locator('.creation-card').first().waitFor();
    assert.equal(await app.locator('#setupLink').isVisible(),false);
    await app.getByRole('button',{name:'打开作品：mint_reading_chair',exact:true}).click();await app.locator('#previews img').waitFor();
    await app.locator('#creationPrompt').fill('保留模型');await app.locator('#creationBrief').click();await app.locator('#creationHandoffBox').waitFor();
    await page.goto(base+'/#ui-test');await page.waitForFunction(()=>document.getElementById('editorState').textContent.includes('编辑器已连接'));
    assert.equal(await page.locator('#notice.error').count(),0,'Setup must load with shared styles');
    await noOverflow(page,'setup desktop');await shot(page,'setup');
    await page.setViewportSize({width:390,height:900});await noOverflow(page,'setup mobile');
    assert((await page.locator('#workbenchLink').getAttribute('href')).endsWith('#ui-test'));
    assert.deepEqual(errors,[],'Uncaught browser errors');
    console.log('PASS: gallery/search/filter; retained previews; contextual commands; 3D parts; image regions; UI config; all 15 tools; queue/errors; project-switch race; 320–1440px; inline MCP App.');
  }finally{await context.close();await browser.close();await new Promise(r=>server.close(r));}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
