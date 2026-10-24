/* Gallery and contextual canvas for retained 3D, images and native game UI. */
(() => {
  const P=window.PTS, {$,call,workflowAction:run,bind,button,textNode:node,option,notice,waitAction,refresh}=P;
  let selected=null, visual=null, region=null, samplesLoaded=false, signature="", project="";
  let galleryFilter="all", entries=[];
  const clearVisual=()=>{visual?.dispose();visual=null;}; P.clearVisual=clearVisual;
  const nextId=(value,prefix)=>value.trim()||prefix+"_"+Date.now().toString(36);
  const done=task=>["completed","imported"].includes(task.status);
  const values=id=>$(id).value.split(/[,，\s]+/).filter(Boolean).map(Number);
  const kinds={item:"物品套件",model:"3D 模型",image:"图片素材",ui:"游戏界面"};
  async function handoff(text){text+=P.sceneHandoff();$("creationHandoffBox").hidden=false;$("creationHandoff").value=text;notice(await P.handoff(text)?"任务已交给当前 AI，可在任务页查看进度。":"制作指令已准备。复制给 Codex / Harness，完成后会回到当前项目。");}
  bind("copyCreationBrief",async()=>{try{await navigator.clipboard.writeText($("creationHandoff").value);notice("已复制制作指令。");}catch(_){$("creationHandoff").focus();$("creationHandoff").select();notice("请复制已选中的指令。");}});
  bind("creationBrief",async()=>{
    await P.ensureSceneContext();
    const prompt=$("creationPrompt").value.trim(); if(!prompt)throw Error("先描述作品的用途与外观，或要调整的地方。");
    const context=P.context(), id=nextId($("creationId").value,"creation"); $("creationId").value=id;
    await P.ensureAssetUsage(context?.model || (context?.kind === "image" ? context.id : $("creationKind").value === "item" ? id+"_model" : id));
    const kind=$("creationKind").value,reference=$("creationReference").value.trim();
    if(context){
      await handoff(`请修改 Prompt-to-Scene 当前项目已有的${kinds[context.kind]}：${context.title}\n当前作品：${JSON.stringify(context)}\n修改要求：${prompt}\n额外参考：${reference||"沿用项目样本"}\n先读取 game_workflow context / art_samples，describe 对应操作契约，并 inspect_asset / creation_workspace / image_catalog 核实当前版本。保持已有 ID，不创建替代作品。模型优先 edit_part / plan_creation_update，再 update_creation；关联图标按实际需要更新。图片用 plan_image_edit 或 plan_image → 宿主生图 → import_image(preview_only=true)，对照后采用。原生界面保留已修改的布局、事件与绑定。更新前核对用户明确要修改的范围；保留其他部件、手工字段与玩法。等待真实任务结果，反馈保留版本与撤销入口。`);
      return;
    }
    const routes={item:"create_game_item：提供 item_id、name、description 和 model（method=custom 与真实 bpy script，或已有 model_asset_id）。模型需有命名 pts_part，游戏尺寸、材质与细节符合设定。会自动渲染透明图标、创建原生物品数据与拾取物。",model:"produce：提供 items，以 custom bpy script 建模或复用项目内的设计。",image:"plan_image → 宿主可用的图片生成工具 → import_image。没有图片工具就使用已配置的图片服务并遵循费用许可；不要编造结果。",ui:"create_game_ui：选择 inventory、hud 或 pause，传 screen_id、title、item_ids；使用普通可编辑控件。需要其他 UI 时先说明这三种模板的范围。"};
    await handoff(`请在 Prompt-to-Scene 当前项目制作：${prompt}\n作品 ID：${id}\n参考图片：${reference||"沿用当前项目样本"}\n先用 game_workflow context / art_samples 读取玩法、背景和已接受/避免的美术样本，实际查看参考图。按用途决定轮廓、材质和细节，不用通用方块替代。\n用 game_workflow describe 查对应操作契约，然后执行 ${routes[kind]}\n检查 creation_workspace / image_preview / review_images 的真实结果，再继续具体修改。关联资源沿用相同 ID；修改已有物品时保留手工字段和 UI 布局。等待任务成功，反馈真实路径与可用事件。`);
  });
  bind("creationExample",()=>run("game_item_example",{item_id:nextId("","herbalist_potion")}));
  bind("linkItem",()=>run("create_game_item",{item_id:nextId($("itemId").value,"item"),model_asset_id:$("itemModel").value,name:$("itemName").value,description:$("itemDescription").value}));
  bind("makeScreen",()=>run("create_game_ui",{screen_id:nextId($("screenId").value,"screen"),kind:$("screenKind").value,title:$("screenTitle").value,item_ids:Array.from($("screenItems").selectedOptions).map(o=>o.value),update_theme:$("screenTheme").checked}));
  function options(select,rows,empty){const current=new Set([...select.selectedOptions].map(o=>o.value));select.replaceChildren(...(empty?[option("",empty)]:[]),...rows.map(([id,label])=>{const o=option(id,label);o.selected=current.has(id);return o;}));}
  function revisionFor(id,fallback){return (P.state().images||[]).find(x=>x.asset_id===id)?.current?.revision||fallback;}
  const thumbnails=new IntersectionObserver(records=>{
    for(const record of records){if(!record.isIntersecting)continue;thumbnails.unobserve(record.target);loadThumbnail(record.target);}
  },{rootMargin:"160px"});
  async function loadThumbnail(frame){
    try{
      const result=await P.cachedImage(JSON.parse(frame.dataset.preview));
      if(!frame.isConnected)return;
      const img=document.createElement("img");img.src=result.url;img.alt=frame.dataset.title;img.loading="lazy";
      img.onerror=()=>{if(frame.isConnected)frame.replaceChildren(node("span","预览暂不可用"));};
      frame.replaceChildren(img);
    }catch(_){if(frame.isConnected)frame.querySelector("span").textContent="暂无保留预览";}
  }
  function galleryCard(entry){
    const card=node("article","");card.className="creation-card";card.dataset.kind=entry.kind;
    const open=button("",()=>openEntry(entry));open.className="creation-open";open.setAttribute("aria-label","打开作品："+entry.title);
    const frame=node("div","");frame.className="gallery-art "+entry.kind;
    if(entry.preview){frame.dataset.preview=JSON.stringify(entry.preview);frame.dataset.title=entry.title;frame.append(node("span","读取预览…"));thumbnails.observe(frame);}
    else{const mark=node("div",entry.kind==="ui"?"▤":"◇");mark.className="gallery-placeholder";frame.append(mark,node("span",entry.kind==="ui"?"可编辑原生界面":"暂无保留预览"));}
    const info=node("div","");info.className="gallery-card-info";
    info.append(node("small",kinds[entry.kind]),node("h2",entry.title),node("p",entry.description||entry.id));
    const footer=node("div","");footer.className="gallery-card-footer";footer.append(node("span",entry.kind==="item"?"模型 · 图标 · 拾取物":entry.kind==="ui"?"保留布局与事件":"保留源文件与版本"),node("span","打开 ↗"));
    open.append(frame,info,footer);card.append(open);return card;
  }
  function drawGallery(){
    thumbnails.disconnect();
    const query=$("gallerySearch").value.trim().toLocaleLowerCase();
    const filtered=entries.filter(e=>(galleryFilter==="all"||e.kind===galleryFilter)&&`${e.title} ${e.id} ${e.description}`.toLocaleLowerCase().includes(query));
    $("galleryCount").textContent=`${filtered.length} 件作品`+(filtered.length!==entries.length?` / 共 ${entries.length} 件`:"");
    const gallery=$("creationGallery");gallery.replaceChildren(...filtered.map(galleryCard));
    if(!filtered.length){
      const empty=node("div","");empty.className="gallery-empty";
      empty.append(node("small",entries.length?"NO MATCHES":"A PLACE FOR YOUR IDEAS"),node("h2",entries.length?"没有找到这件作品":"你的世界，从第一件作品开始"),node("p",entries.length?"试试其他关键词，或查看全部作品。":P.state().target?"描述一个想法，或导入已有素材。模型、图片和游戏界面会一起留在这里。":"连接 Unity 或 Unreal 项目，再把你的想法变成可以使用的作品。"));
      if(entries.length)empty.append(button("清除筛选",()=>{$("gallerySearch").value="";setFilter("all");}));
      else{
        const create=button("＋ 开始创作",()=>{P.openCanvas();$("creationPrompt").focus();});create.className="primary";empty.append(create);
        if(!P.state().target&&!P.embedded){const link=node("a","连接游戏项目 →");link.href="/"+location.hash;empty.append(link);}
      }
      gallery.append(empty);
    }
  }
  function setFilter(value){galleryFilter=value;document.querySelectorAll("[data-gallery-filter]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.galleryFilter===value)));drawGallery();}
  $("gallerySearch").oninput=drawGallery;
  document.querySelectorAll("[data-gallery-filter]").forEach(b=>b.onclick=()=>setFilter(b.dataset.galleryFilter));
  function render(state){
    if(project!==state.active){project=state.active;selected=null;signature="";region=null;samplesLoaded=false;clearVisual();$("creationFocus").hidden=true;$("regionEditor").hidden=true;$("creationHandoffBox").hidden=true;$("sampleGallery").replaceChildren();$("gallerySearch").value="";galleryFilter="all";document.querySelectorAll("[data-gallery-filter]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.galleryFilter==="all")));}
    const items=state.creations?.["game-items"]||[],screens=state.creations?.["game-screens"]||[];
    options($("itemModel"),(state.assets||[]).map(a=>[a.asset_id,a.asset_id]),"选择已经导入的模型");
    options($("screenItems"),items.map(i=>[i.item_id,i.name||i.item_id]));
    const key=JSON.stringify([items,screens,state.images,state.assets,!!state.target]);if(signature===key)return;signature=key;
    entries=[];
    for(const item of items)entries.push({kind:"item",id:item.item_id,title:item.name||item.item_id,description:item.description,model:item.model_asset_id,preview:{kind:"game_image",asset_id:item.icon_asset_id,request_id:revisionFor(item.icon_asset_id,item.icon_revision)}});
    for(const screen of screens)entries.push({kind:"ui",id:screen.screen_id,title:screen.title||screen.screen_id,description:`${{inventory:"背包",hud:"HUD",pause:"暂停菜单"}[screen.kind]||screen.kind} · ${screen.item_ids.length} 件关联物品`,screen});
    const linked=new Set(items.map(i=>i.model_asset_id));
    for(const asset of (state.assets||[]).filter(a=>!linked.has(a.asset_id)))entries.push({kind:"model",id:asset.asset_id,title:asset.asset_id,description:"可旋转查看、选择部件与精修材质",revision:asset.request_id,preview:asset.request_id?{kind:"studio",asset_id:asset.asset_id,request_id:asset.request_id}:null});
    const icons=new Set(items.map(i=>i.icon_asset_id));
    for(const image of (state.images||[]).filter(i=>!icons.has(i.asset_id))){const revision=image.current?.revision||image.revisions?.[0]?.revision;if(revision)entries.push({kind:"image",id:image.asset_id,title:image.asset_id,description:"图片预览 · 框选局部修改",revision,preview:{kind:"game_image",asset_id:image.asset_id,request_id:revision}});}
    drawGallery();
  }
  async function openEntry(entry){
    if(entry.kind==="item")return focus(entry.id);
    if(entry.kind==="image")return imageEdit(entry.id,entry.revision);
    if(entry.kind==="ui")return screenView(entry);
    return openModel(entry);
  }
  async function openModel(entry){
    closeRegion();const ticket=P.openCanvas(entry);
    const box=$("creationFocus");box.hidden=false;
    const actions=node("div","");actions.className="inspector-actions";box.replaceChildren(actions);
    actions.append(button("旋转模型 / 点选部件",()=>modelView(entry.id)),button("制作配套物品",()=>{$("itemModel").value=entry.id;$("itemId").value=entry.id+"_item";$("itemModel").closest("details").open=true;$("itemModel").focus();}));
    if(entry.preview)try{await P.showImage(entry.preview,entry.title+" · 保留的模型渲染");}catch(_){if(P.canvasCurrent(ticket))$("previewCaption").textContent="尚无保留渲染，可点击「旋转模型 / 点选部件」准备预览。";}
  }
  function screenView(entry){
    closeRegion();P.openCanvas(entry);const screen=entry.screen;
    $("screenId").value=screen.screen_id;$("screenKind").value=screen.kind;$("screenTitle").value=screen.title;
    for(const o of $("screenItems").options)o.selected=screen.item_ids.includes(o.value);
    $("screenId").closest("details").open=true;
    const layout=node("div","");layout.className="screen-structure";layout.append(node("small","界面结构示意 · 实际排版以引擎为准"),node("h2",entry.title));
    const slots=node("div","");slots.className="screen-slots";
    const items=P.state().creations?.["game-items"]||[];
    for(const id of screen.item_ids)slots.append(node("div",items.find(i=>i.item_id===id)?.name||id));
    if(!screen.item_ids.length)slots.append(node("div",{inventory:"背包物品栏",hud:"生命值 · 快捷栏",pause:"继续游戏 · 设置"}[screen.kind]));
    layout.append(slots);$("previews").append(layout);$("previewEmpty").hidden=true;$("previewCaption").textContent="原生可编辑界面";$("previewMeta").textContent="更新会保留已有布局与事件";
  }
  window.addEventListener("pts:state",event=>render(event.detail));
  window.addEventListener("pts:tab",event=>{if(event.detail==="samples"&&!samplesLoaded&&P.state().target)loadSamples().catch(e=>notice(e.message,true));});
  function canvas(label){P.beginVisual();clearVisual();$("previews").replaceChildren();$("previewEmpty").hidden=true;const c=document.createElement("canvas");c.className="visual-canvas";c.tabIndex=0;c.setAttribute("aria-label",label);$("previews").append(c);$("previewCaption").textContent=label;return c;}
  function closeRegion(){region=null;$("regionEditor").hidden=true;}
  async function focus(id){
    closeRegion();selected=id;
    const known=(P.state().creations?.["game-items"]||[]).find(i=>i.item_id===id);
    const ticket=P.openCanvas({kind:"item",id,title:known?.name||id,description:known?.description,model:known?.model_asset_id});
    const result=await run("creation_workspace",{creation_id:id});if(!P.canvasCurrent(ticket))return;
    const item=result.item,box=$("creationFocus");box.hidden=false;box.replaceChildren();
    const actions=node("div","");actions.className="inspector-actions";
    actions.append(button("查看 3D 模型",()=>modelView(item.model_asset_id)),button("局部修改图标",()=>imageEdit(item.icon_asset_id,revisionFor(item.icon_asset_id,item.icon_revision))),button("更新配套图标与物品",()=>run("create_game_item",{item_id:id,model_asset_id:item.model_asset_id,icon_asset_id:item.icon_asset_id,name:item.name,description:item.description})));box.append(actions);
    const details=node("details","");details.append(node("summary","版本与关联"));
    const versions=document.createElement("select");versions.setAttribute("aria-label","图标版本");const history=result.images[0]?.revisions||[];
    for(const row of history)versions.append(option(row.revision,new Date(row.created_utc).toLocaleString()+" · "+row.revision.slice(0,8)));
    details.append(versions,button("查看此版图标",()=>P.showImage({kind:"game_image",asset_id:item.icon_asset_id,request_id:versions.value},"保留的图标版本")),button("恢复此版图标",()=>run("publish_image",{asset_id:item.icon_asset_id,revision:versions.value})),node("p",result.screens.length?"已用于："+result.screens.map(s=>s.title||s.screen_id).join("、"):"可将此物品加入背包或 HUD。"),node("small","原生数据 · "+item.item_path));box.append(details);
    await P.showImage({kind:"game_image",asset_id:item.icon_asset_id,request_id:revisionFor(item.icon_asset_id,item.icon_revision)},item.name+" · 配套透明图标");return result;
  }
  async function modelView(asset){closeRegion();const context=P.context();const ticket=context&&(context.id===asset||context.model===asset)?P.canvasTicket():P.openCanvas({kind:"model",id:asset,title:asset});notice("正在读取模型几何，保留源文件。首次查看需要 Blender 准备预览。");const task=await waitAction(await run("view_model",{asset_id:asset}));if(!done(task)||!P.canvasCurrent(ticket))return task;const data=await run("model_view_data",{asset_id:asset,revision:task.model_revision});if(!P.canvasCurrent(ticket))return;const c=canvas(asset+" · 旋转 / 点选部件");visual=new window.PTSModelViewer(c,data,name=>{list.value=name;notice("选中部件："+name+"。可以修改颜色、尺寸、位置，已有锁定继续生效。");P.choosePart(asset,name).catch(e=>notice(e.message,true));});const toolbar=document.createElement("div");toolbar.className="row visual-controls";const list=document.createElement("select");list.setAttribute("aria-label","预览部件");const names=[...new Set(data.parts.map(p=>p.name))];list.append(option("","点击模型或选择部件"),...names.map(n=>option(n,n)));list.onchange=()=>{if(list.value){visual.selected=list.value;visual.draw();P.choosePart(asset,list.value).catch(e=>notice(e.message,true));}};toolbar.append(list,button("重置视角",()=>{visual.yaw=.55;visual.pitch=.3;visual.zoom=1;visual.draw();}));$("previews").append(toolbar);
    const info=await call("inspect_asset",{asset_id:asset}),history=[...(info.history||[])].reverse();if(!P.canvasCurrent(ticket))return;
    if(history.length>1){const versions=document.createElement("select");versions.setAttribute("aria-label","模型源版本");history.forEach(r=>versions.append(option(r.request_id,(r.request_id===info.current.request_id?"当前 · ":"")+new Date(r.completed_utc).toLocaleString())));const row=document.createElement("div");row.className="row visual-controls";row.append(versions,button("恢复模型源版本",async()=>{if(versions.value===info.current.request_id)throw Error("这已经是当前版本。");const task=await run("restore_asset",{asset_id:asset,revision:versions.value});notice("正在恢复保留的模型源文件；完成后可更新物品套件的配套图标。");return task;}));$("previews").append(row);}
    $("previewMeta").textContent="拖动旋转 · 滚轮缩放 · 单击部件 · 方向键也可旋转";notice("显示真实几何与近似材质；最终光照、透明和贴图请查看引擎画面。"+(data.simplified?"大模型已为预览简化。":""));return task;}
  async function imageEdit(asset,revision){closeRegion();const ticket=P.openCanvas({kind:"image",id:asset,title:asset,revision});const result=await call("image",{kind:"game_image",asset_id:asset,request_id:revision});if(!P.canvasCurrent(ticket))return;const c=canvas(asset+" · 框选局部修改");c.classList.add("alphaPreview");region={asset,revision,rectangle:null,plan:null};visual=new window.PTSImageSelection(c,result.url,rect=>{region.rectangle=rect;$("regionRect").value=rect.map(n=>n.toFixed(4)).join(", ");$("regionStatus").textContent="选区已保存，请描述要修改的内容。";});$("regionEditor").hidden=false;$("regionImport").disabled=true;$("regionStatus").textContent="拖动框选，或使用坐标选择区域。";$("previewMeta").textContent="矩形局部编辑 · 保留选区外像素";}
  P.openImageEdit=imageEdit;
  bind("setRegion",()=>{if(!region||!visual?.select)throw Error("先打开图片的局部修改。");const r=values("regionRect");if(r.length!==4||r.some(x=>!Number.isFinite(x))||r[0]<0||r[1]<0||r[2]<=0||r[3]<=0||r[0]+r[2]>1.000001||r[1]+r[3]>1.000001)throw Error("输入图片内的 x, y, 宽, 高，范围为 0–1。");region.rectangle=r;visual.select(r);});
  bind("regionBrief",async()=>{if(!region?.rectangle)throw Error("先框选要修改的区域。");const prompt=$("regionPrompt").value.trim();if(!prompt)throw Error("描述选区内需要修改的内容。");const plan=await run("plan_image_edit",{asset_id:region.asset,revision:region.revision,rectangle:region.rectangle,prompt});region.plan=plan;$("regionImport").disabled=false;await handoff(`请用当前宿主的图片编辑工具完成 Prompt-to-Scene 局部修改。\n${plan.effective_prompt}\n原图：${plan.region_edit.source_path}\n遮罩（透明区域可改）：${plan.region_edit.mask_path}\n裁剪参考：${plan.region_edit.crop_path}\n完成后 game_workflow import_image，asset_id=${plan.asset_id}，plan_id=${plan.plan_id}，source 为实际文件路径，preview_only=true。用 image_preview 查看结果，对照原图，再询问是否采用。不具备图片工具时使用已配置的 generate_image；没有服务则说明，不能假装已生成。`);return plan;});
  bind("regionImport",async()=>{if(!region?.plan)throw Error("先准备局部修改计划。");const r=await run("import_image",{asset_id:region.asset,plan_id:region.plan.plan_id,source:$("regionSource").value.trim(),preview_only:true});const base={...region};await P.showImage({kind:"game_image",asset_id:base.asset,request_id:base.revision},"修改前");await P.showImage({kind:"game_image",asset_id:base.asset,request_id:r.revision},"修改后 · 选区外像素保留",true);const controls=document.createElement("div");controls.className="row";controls.append(button("采用这次修改",()=>run("publish_image",{asset_id:base.asset,revision:r.revision})),button("恢复原版",()=>run("publish_image",{asset_id:base.asset,revision:base.revision})));$("previews").append(controls);$("regionStatus").textContent="新版本尚未导入。查看对照后选择是否采用。";return r;});
  async function loadSamples(){const result=await run("art_samples");samplesLoaded=true;const gallery=$("sampleGallery");gallery.replaceChildren();for(const [key,value] of Object.entries(result.theme)){if($("theme-"+key))$("theme-"+key).value=value;}
    for(const sample of result.samples){const card=document.createElement("article");card.className="card sample-card";card.append(node("small",(sample.verdict==="accepted"?"✓ 保留":"↗ 避免")+" · "+sample.category),node("h3",sample.name),node("p",sample.notes),button("修改说明 / 新版本",()=>{$("sampleId").value=sample.sample_id;$("sampleName").value=sample.name;$("sampleSource").value=sample.path;$("sampleNotes").value=sample.notes;$("sampleCategory").value=sample.category;$("sampleVerdict").value=sample.verdict;notice("保存时会新增版本，旧样本仍然保留。");}));const versions=document.createElement("select");versions.setAttribute("aria-label",sample.name+"样本版本");for(const r of sample.versions)versions.append(option(r,r.slice(0,8)+(r===sample.revision?" · 当前":"")));versions.value=sample.revision;card.append(versions,button("恢复样本版本",async()=>{await run("restore_art_sample",{sample_id:sample.sample_id,revision:versions.value});return loadSamples();}));gallery.append(card);const result=await call("image",{kind:"art_sample",asset_id:sample.sample_id,request_id:sample.revision});const img=document.createElement("img");img.src=result.url;img.alt=sample.name;card.prepend(img);}
    if(!result.samples.length)gallery.append(node("p","保存第一张满意的参考图，告诉 AI 哪些地方值得延续。"));return result;
  }
  bind("loadSamples",loadSamples);bind("saveSample",async()=>{await run("save_art_sample",{name:$("sampleName").value,category:$("sampleCategory").value,source:$("sampleSource").value,notes:$("sampleNotes").value,verdict:$("sampleVerdict").value,sample_id:$("sampleId").value||null});$("sampleId").value="";$("sampleName").value="";return loadSamples();});
  bind("saveTheme",async()=>{const settings=Object.fromEntries(["background","surface","accent","text","muted","font_size","spacing"].map(k=>[k,["font_size","spacing"].includes(k)?Number($("theme-"+k).value):$("theme-"+k).value]));const result=await run("art_theme",{settings});notice("项目主题已保存，新的 UI 与制作计划会沿用。");return result;});
  if(P.state().version)render(P.state());
})();
