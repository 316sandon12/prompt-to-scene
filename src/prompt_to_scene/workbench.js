/* Shared UI: loopback API in the local app, MCP Apps JSON-RPC when embedded. */
(() => {
  const $ = id => document.getElementById(id);
  const embedded = window.parent !== window;
  const token = location.hash.slice(1);
  let seq = 0, snapshot = {}, currentAsset = null, activeReview = null, refreshing = false;
  let organizationPlan = null;
  let hostCapabilities = {};
  let activeTab = "creations", taskFilter = "all", previewSequence = 0, previewIsExample = true;
  let canvasContext = null, canvasEpoch = 0, noticeTimer;
  const groups = {
    create: ["creations", "generate", "images", "edit", "review", "performance"],
    scene: ["compose", "level", "gameplay", "flows"],
    tasks: ["missions"],
    project: ["samples", "library", "organizer", "pipeline"]
  };
  const previewCache = new Map();
  const tabs = {
    missions: ["CREATE / CONTINUE", "开发任务", "从需求出发，把下一步做到游戏里。"],
    flows: ["BUILD / GAMEPLAY", "玩法与套件", "让美术、物品和游戏规则一起工作。"],
    creations: ["CREATE / WORKSPACE", "我的作品", "描述、查看、修改，让作品走进游戏。"],
    samples: ["REFINE / ART LIBRARY", "美术样本", "记住每一次选择，让新作品延续同一种风格。"],
    generate: ["CREATE / 3D ASSETS", "模型创作", "从一个想法，到游戏里的下一件作品。"],
    images: ["CREATE / GAME ART", "图片与 UI", "让每一张素材，都属于同一个游戏世界。"],
    compose: ["CREATE / SCENE", "场景布置", "把单件作品，组合成有生活感的场景。"],
    level: ["CREATE / LEVEL", "关卡搭建", "先让空间与路径成立，再填入你的世界。"],
    edit: ["REFINE / PARTS", "部件编辑", "保留满意的部分，精修需要改变的细节。"],
    review: ["REFINE / ART DIRECTION", "视觉与风格", "对照真实画面，统一作品的外观与气质。"],
    performance: ["REFINE / PERFORMANCE", "性能优化", "按实际用途，找到细节与性能的平衡。"],
    gameplay: ["BUILD / INTERACTION", "玩法交互", "让场景中的道具，成为可以参与的玩法。"],
    library: ["MANAGE / LIBRARY", "素材库", "先找到已有的好素材，再开始新的创作。"],
    organizer: ["MANAGE / ORGANIZE", "命名与整理", "让资源有清晰的名字，也有自己的位置。"],
    pipeline: ["MANAGE / PROJECT", "项目管家", "保存一次规范，让后续制作自然地沿用。"]
  };
  const pending = new Map();
  const gameFields = {gameWorld:"world",gameLoop:"gameplay",gameStyle:"style_notes",gameView:"view",gameCraft:"construction"};
  async function saveGameArt() {
    const result = await call("game_art", {settings:Object.fromEntries(Object.entries(gameFields).map(([id,key])=>[key,$(id).value]))});
    delete $("gameContext").dataset.dirty;
    notice("已保存游戏设定，后续新资产会沿用。");
    return result;
  }
  async function ensureGameArt() { await window.PTS.ensureSceneContext(); if ($("gameContext").dataset.dirty) await saveGameArt(); }
  function notice(message, error = false) {
    clearTimeout(noticeTimer);
    $("notice").textContent = message;
    $("notice").classList.toggle("error", error);
    $("notice").setAttribute("role", error ? "alert" : "status");
    $("noticeToast").hidden = !message;
    if (!error) noticeTimer = setTimeout(() => { $("noticeToast").hidden = true; }, 9000);
  }
  $("dismissNotice").onclick = () => { clearTimeout(noticeTimer); $("noticeToast").hidden = true; };
  function rpc(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      const timer = setTimeout(() => { pending.delete(id); reject(Error("宿主没有回应，请刷新或改用本地创作台。")); }, 30000);
      pending.set(id, {resolve, reject, timer});
      window.parent.postMessage({jsonrpc:"2.0", id, method, params}, "*");
    });
  }
  function notify(method, params) { window.parent.postMessage({jsonrpc:"2.0", method, params}, "*"); }
  window.addEventListener("message", event => {
    if (!embedded || event.source !== window.parent || event.data?.jsonrpc !== "2.0") return;
    const message = event.data;
    if (pending.has(message.id)) {
      const task = pending.get(message.id); clearTimeout(task.timer); pending.delete(message.id);
      if (message.error) task.reject(Error(message.error.message)); else task.resolve(message.result);
    } else if (message.method === "ui/notifications/tool-result" && message.params?.structuredContent?.tasks) {
      render(message.params.structuredContent);
    } else if (message.method === "ui/resource-teardown" && message.id != null) {
      window.parent.postMessage({jsonrpc:"2.0",id:message.id,result:{}}, "*");
    }
  });
  async function local(path, values) {
    const response = await fetch("/api/" + path, {method:"POST", headers:{"Content-Type":"application/json", "X-PTS-Token":token}, body:JSON.stringify(values)});
    const result = await response.json();
    if (!response.ok || result.error) throw Error(result.error || "操作失败");
    return result;
  }
  async function call(action, values = {}) {
    if (!embedded) return local("workbench", {action, values});
    const response = await rpc("tools/call", {name:"workbench_action", arguments:{action, values}});
    if (response.isError) throw Error(response.content?.find(c => c.type === "text")?.text || "操作失败");
    return response.structuredContent || JSON.parse(response.content.find(c => c.type === "text").text);
  }
  async function workflowAction(action, values = {}) {
    return call("workflow", {operation:"execute", action, values});
  }
  function output(result) {
    $("result").textContent = JSON.stringify(result, (key, value) => key === "url" && String(value).startsWith("data:") ? "[图像已显示]" : value, 2);
  }
  async function action(button, fn) {
    button.disabled = true; button.setAttribute("aria-busy", "true");
    try { const result = await fn(); if (result) output(result); await refresh(); }
    catch (error) { notice(error.message, true); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); selectionAvailability(); if(organizationPlan)organizationButtons(); window.dispatchEvent(new CustomEvent("pts:idle")); }
  }
  function bind(id, fn) { $(id).onclick = event => action(event.currentTarget, fn); }
  document.querySelector(".skip-link").onclick = event => { event.preventDefault(); $("workspaceContent").focus(); };
  function selectionAvailability() {
    const online = !!snapshot.target?.editor_responding && !snapshot.target?.editor?.playing;
    for (const id of ["captureSceneContext", "checkSceneFit"]) {
      const control=$(id);
      control.disabled=!online || control.getAttribute("aria-busy")==="true" || (id==="checkSceneFit"&&!$("asset").value);
      control.title=online?"":"请保持目标编辑器打开并退出 Play 模式。";
    }
    $("scene").disabled = !online;
    $("preview").disabled = !online || !$("asset").value;
    $("scene").title = online ? "读取当前编辑器中的对象" : "编辑器在线且退出 Play 后可用";
    $("preview").title = !online ? "编辑器在线且退出 Play 后可用" : "预览选中的已导入资产";
  }
  function requiredAsset() { if (!$("asset").value) throw Error("先选择一个已经导入的资产。"); return $("asset").value; }
  function requiredPart() { if (!$("part").value) throw Error("先选择一个部件。"); return $("part").value; }
  function id(value, fallback) { return value.trim() || fallback + "_" + Date.now().toString(36); }
  function position() {
    const text = $("position").value.trim(); if (!text) return null;
    const values = text.split(/[,，\s]+/).map(Number);
    if (values.length !== 3 || values.some(v => !Number.isFinite(v))) throw Error("位置需要三个数字，例如 3, 0, 2。");
    return values;
  }
  function option(value, label) { const node = document.createElement("option"); node.value = value; node.textContent = label; return node; }
  function button(text, fn) { const node = document.createElement("button"); node.textContent = text; node.onclick = event => action(event.currentTarget, fn); return node; }
  function textNode(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
  function humanStatus(status) { return {building:"处理中", queued:"等待编辑器", completed:"已完成", imported:"已导入", error:"需要处理", cancelled:"已取消", superseded:"已被新版替代"}[status] || status; }
  async function waitAction(task) {
    for (let i = 0; i < 125; i++) {
      if (["completed", "imported"].includes(task.status)) return task;
      if (["error", "cancelled", "unknown", "superseded"].includes(task.status)) throw Error(task.error || humanStatus(task.status));
      await new Promise(resolve => setTimeout(resolve, 800));
      task = await call("task", {request_id:task.request_id});
    }
    notice("任务仍在运行。请保持编辑器打开，可在任务卡查看进度；试玩检查会自动返回编辑模式。");
    return task;
  }
  async function cachedImage(values) {
    // Project references can change in place; only cache immutable previews.
    if (values.kind === "reference" || (values.kind !== "example" && !values.request_id)) return call("image", values);
    const key = JSON.stringify([snapshot.active, values]);
    if (!previewCache.has(key)) {
      const pending = call("image", values).catch(error => { previewCache.delete(key); throw error; });
      previewCache.set(key, pending);
      if (previewCache.size > 24) previewCache.delete(previewCache.keys().next().value);
    }
    return previewCache.get(key);
  }
  async function showImage(values, caption, append = false) {
    if (document.body.dataset.view === "project" && activeTab !== "organizer") document.body.classList.add("project-preview");
    else if (!["create", "scene"].includes(document.body.dataset.view) || document.body.classList.contains("flow-workspace")) {
      const kind = {game_image:"image", studio:"model"}[values.kind];
      openCanvas(kind && values.asset_id ? {kind,id:values.asset_id,title:values.asset_id,revision:values.request_id} : null);
      if (!kind || !values.asset_id) {
        $("canvasTitle").textContent = "任务结果预览";
        $("inspectorTitle").textContent = "结果预览";
        $("inspectorDescription").textContent = "继续修改时，从作品展廊打开对应作品。";
        for (const name of ["creationComposer", "creationAdvanced", "exampleDetails", "itemDetails", "screenDetails"]) $(name).hidden = true;
      }
    }
    const sequence = append ? previewSequence : ++previewSequence;
    const data = await cachedImage(values);
    if (sequence !== previewSequence) return;
    if (!append) { window.PTS?.clearVisual?.(); $("previews").replaceChildren(); }
    $("previewEmpty").hidden = true;
    const figure = document.createElement("figure"), img = document.createElement("img");
    img.src = data.url; img.alt = caption;
    if(values.kind === "game_image" || (values.kind === "example" && values.view === "image")) img.classList.add("alphaPreview");
    figure.append(img, textNode("figcaption", caption)); $("previews").append(figure);
    previewIsExample = values.kind === "example";
    $("previewCaption").textContent = previewIsExample ? "内置示例 · 尚未导入项目" : "实际文件预览";
    $("previewMeta").textContent = img.classList.contains("alphaPreview") ? "棋盘格表示透明" : values.kind === "engine" ? "当前引擎画面" : "原始渲染图";
  }
  async function showExample() {
    const isImage = activeTab === "images";
    await showImage({kind:"example", view:isImage ? "image" : "model"}, isImage ? "治疗药水 · AI 生成的透明图标示例" : "薄荷阅读椅 · Blender 实际渲染示例");
  }
  $("showExample").onclick = () => showExample().catch(error => notice(error.message,true));
  function expandPreview(expand) {
    $("workspaceContent").classList.toggle("is-expanded", expand);
    $("expandPreview").setAttribute("aria-pressed", String(expand));
    $("expandPreview").textContent = expand ? "收起预览" : "展开预览";
  }
  $("expandPreview").onclick = () => expandPreview($("expandPreview").getAttribute("aria-pressed") !== "true");
  document.addEventListener("keydown", event => { if(event.key === "Escape" && $("expandPreview").getAttribute("aria-pressed") === "true") { expandPreview(false); $("expandPreview").focus(); } });
  async function showReview(task) {
    const record = task.review || await call("review", {review_id:task.review_id});
    activeReview = task.request_id; ++previewSequence; $("previews").replaceChildren();
    for (const stage of ["before", "after"]) {
      const capture = record.captures?.[stage];
      if (capture?.status === "completed") await showImage({kind:"engine",request_id:capture.request_id}, stage === "before" ? "修改前 · 引擎画面" : "修改后 · 同一机位", true);
    }
    if (snapshot.art_brief?.image) await showImage({kind:"reference"}, "保存的美术参考", true);
    output(task); notice("已显示真实引擎对照。检查外观后，可继续具体的部件修复。");
  }
  async function loadAsset() {
    const name = $("asset").value, project = snapshot.active; selectionAvailability();
    if (!name) { currentAsset = null; $("part").replaceChildren(option("", "先选择资产")); return; }
    const inspected = await call("inspect_asset", {asset_id:name});
    if (name !== $("asset").value || project !== snapshot.active) return;
    currentAsset = inspected;
    const parts = Object.keys(currentAsset.metadata?.report?.parts || {}), selected = $("part").value;
    $("part").replaceChildren(...parts.map(name => option(name, name)));
    if (parts.includes(selected)) $("part").value = selected;
    partInfo();
    if (embedded) await rpc("ui/update-model-context", {content:[{type:"text",text:JSON.stringify({selected_asset:name,parts})}]}).catch(() => {});
  }
  function partInfo() {
    const part = currentAsset?.metadata?.report?.parts?.[$("part").value] || {};
    $("geometryLock").checked = !!(part.locks?.geometry || currentAsset?.metadata?.recipe?.locks?.[$("part").value]?.geometry); $("materialLock").checked = !!(part.locks?.material || currentAsset?.metadata?.recipe?.locks?.[$("part").value]?.material);
    $("partInfo").textContent = (part.objects?.length ? `${part.objects.length} 个网格 · ` : "") + ($("geometryLock").checked ? "形状已锁定" : "可修改形状") + " · " + ($("materialLock").checked ? "材质已锁定" : "可修改材质");
  }
  function render(state) {
    if (snapshot.active && snapshot.active !== state.active) { organizationPlan=null; $("organizationRows").replaceChildren(); $("organizationSummary").textContent="项目已切换，请重新扫描。"; $("organizationPage").textContent="尚未扫描"; for(const id of ["applyOrganization","undoOrganization","organizationPrevious","organizationNext"])$(id).disabled=true; $("organizationHistoryList").replaceChildren(); }
    if (snapshot.active && snapshot.active !== state.active) {
      canvasContext = null; ++canvasEpoch; showGallery();
      previewCache.clear(); ++previewSequence; previewIsExample = true;
      $("previews").replaceChildren(); $("previewEmpty").hidden = false;
      $("previewCaption").textContent = "项目已切换，请选择作品";
      $("objectList").replaceChildren(textNode("p", "点击「读取编辑器选择」，查看场景对象。"));
      currentAsset = null;
    }
    snapshot = state;
    window.dispatchEvent(new CustomEvent("pts:state",{detail:state}));
    const online = !!state.target?.editor_responding;
    $("editorStatus").classList.toggle("online", online);
    $("editorStatus").querySelector("span").textContent = !state.target ? "未连接项目" : online ? (state.target.editor?.playing ? "引擎运行中" : "编辑器在线") : "编辑器离线";
    $("modelCount").textContent = (state.assets || []).length;
    $("imageCount").textContent = (state.images || []).length;
    const children = new Set((state.tasks || []).flatMap(task => task.children || []));
    $("runningCount").textContent = (state.tasks || []).filter(task => !children.has(task.request_id) && ["building", "queued"].includes(task.status)).length;
    $("navTaskCount").textContent = $("runningCount").textContent;
    $("navTaskCount").hidden = $("runningCount").textContent === "0";
    renderImageLibrary(state.images || []);
    $("version").textContent = "v" + state.version;
    $("connection").textContent = state.target ? `${state.target.engine || ""} · ${(state.active || "").split(/[/\\]/).filter(Boolean).pop()}` : (state.connection_message || "尚未连接项目，请先打开连接与设置。");
    $("connection").title=state.active || "";
    const selected = $("asset").value, assets = state.assets || [];
    $("asset").replaceChildren(option("", "选择已导入的资产"), ...assets.map(asset => option(asset.asset_id, asset.asset_id)));
    if (assets.some(a => a.asset_id === selected)) $("asset").value = selected;
    selectionAvailability();
    const furnished = new Set(Array.from($("furnishAssets").selectedOptions).map(o=>o.value));
    $("furnishAssets").replaceChildren(...assets.map(a=>{const o=option(a.asset_id,a.asset_id);o.selected=furnished.has(a.asset_id);return o;}));
    const layout = $("layouts").value;
    $("layouts").replaceChildren(option("", "选择已保存布局"), ...(state.layouts || []).map(item => option(item.name, item.name)));
    if ((state.layouts || []).some(item => item.name === layout)) $("layouts").value = layout;
    if (!$("briefNotes").matches(":focus") && !$("briefNotes").dataset.dirty) $("briefNotes").value = state.art_brief?.notes || "";
    if (!$("gameContext").dataset.dirty) {
      for (const [id,key] of Object.entries(gameFields)) if (!$(id).matches(":focus")) $(id).value = state.game_art?.[key] || ({view:"third_person",construction:"handcrafted"}[key] || "");
    }
    $("gameArtSummary").textContent = state.game_art?.world || state.game_art?.gameplay ? "已记住游戏设定。制作时自动沿用，已有资产保留原设计。" : "尚未填写游戏设定。";
    if (state.style_match) $("gameArtSummary").textContent += " 已保存 AI 对参考画面的风格分析。";
    for (const node of $("provider").options) { const provider = (state.providers || []).find(p => p.provider === node.value); node.textContent = (node.value === "meshy" ? "Meshy" : "自托管服务") + (provider?.configured ? " · 已配置" : " · 未配置"); }
    const signature = JSON.stringify([state.active, taskFilter, (state.tasks || []).map(t => [t.request_id,t.status,t.stage,t.updated_utc])]);
    if ($("tasks").dataset.signature === signature) return;
    $("tasks").dataset.signature = signature; $("tasks").replaceChildren();
    const childIds=new Set((state.tasks || []).flatMap(t=>t.children || []));
    const imageTasks = new Map((state.images || []).flatMap(asset => asset.revisions.filter(version => version.task).map(version => [version.task.request_id, {asset_id:asset.asset_id,revision:version.revision}])));
    const tasks = (state.tasks || []).filter(t => !childIds.has(t.request_id));
    const filtered = tasks.filter(t => taskFilter === "all" || ({active:["building","queued"],done:["completed","imported"],attention:["error","cancelled"]}[taskFilter] || []).includes(t.status));
    $("taskCount").textContent = `${filtered.length} / ${tasks.length}`;
    for (const task of filtered) {
      const card = document.createElement("article"); card.className = "card task-card"; card.dataset.status = task.status;
      const imageInfo = imageTasks.get(task.request_id);
      const commandNames={interaction:"交互配置",protection:"保留设置",update_review:"更新预检",look:"场景风格",level:"模块关卡",playcheck:"试玩检查",library:"项目素材",organize:"资源命名与分类"};
      const summary=imageInfo&&task.status==="queued"?"图片已准备，等待编辑器导入。":task.image?.revision&&task.status==="completed"?"图片已导入，可用于游戏 UI。":task.status==="imported"?"原生资产已导入。":task.development?.command==="playcheck"&&task.status==="completed"?(task.development.passed?"试玩检查通过，已回到编辑模式。":"检查完成，有项目未通过。请查看详情。"):task.error || task.stage || task.development?.message || "";
      card.append(textNode("small", humanStatus(task.status)), textNode("h3", task.image?.asset_id || imageInfo?.asset_id || task.description || (task.kind==="production"?"制作任务":task.kind==="dressing"?"场景布置":task.asset_id) || commandNames[task.development?.command] || task.kind || "编辑器任务"), textNode("p",summary));
      card.append(button("查看详情", () => { output(task); $("resultDetails").open = true; $("resultDetails").scrollIntoView({behavior:"smooth",block:"nearest"}); return task; }));
      if (task.development?.command === "organize" && task.development?.plan_id) card.append(button("查看整理记录", () => loadOrganization(task.development.plan_id)));
      if (task.kind && ["error","cancelled"].includes(task.status)) card.append(button("恢复", () => call("resume", {request_id:task.request_id})));
      if (["building","queued"].includes(task.status)) card.append(button("取消", () => call("cancel", {request_id:task.request_id})));
      if (task.kind === "semantic" && task.status === "completed") card.append(button("查看识别与纠正", () => semanticResults(task)));
      if (task.kind === "adaptation" && task.status === "completed") card.append(button("查看材质前后对照", () => adaptationResults(task)));
      if (task.kind === "quality" && task.status === "completed") card.append(button("查看前后对照", () => showReview(task)));
      const imageRevision=task.image_revision || task.image?.revision || imageInfo?.revision;
      const imageAsset=task.image?.asset_id || task.asset_id || imageInfo?.asset_id;
      if(imageRevision) {
        card.append(button("查看图片",()=>showImage({kind:"game_image",asset_id:imageAsset,request_id:imageRevision},imageAsset+" · 图片素材")));
        if(task.preview_only)card.append(button("导入这张图片",()=>workflowAction("publish_image",{asset_id:imageAsset,revision:imageRevision})));
      }
      if (task.kind === "production" && task.status === "completed") {
        if(task.review) card.append(button("查看游戏效果",()=>showReview(task.review)));
        if(task.dressing?.undo_id)card.append(button("撤销本次布置",()=>call("undo",{undo_id:task.dressing.undo_id})));
      }
      if (task.development?.command === "playcheck" && task.status === "completed" && task.development.screenshots?.length) card.append(button("查看试玩前后", async () => {await showImage({kind:"play_before",request_id:task.request_id},"交互前");await showImage({kind:"engine",request_id:task.request_id},"交互后",true);return task;}));
      if (task.undo_id) card.append(button("撤销布置", () => call("undo", {undo_id:task.undo_id})));
      const candidates = task.candidates || (task.preview_only && task.status === "completed" && task.kind!=="image_generation" ? [{asset_task:task,result:task}] : []);
      candidates.forEach((candidate, index) => {
        const model = candidate.asset_task;
        if (!model || candidate.result?.status !== "completed") return;
        card.append(button(`候选 ${index+1} · 查看`, () => showImage({kind:"studio",asset_id:model.asset_id,request_id:model.request_id}, "Blender 工作室预览")));
        card.append(button(`候选 ${index+1} · 导入`, () => call("publish", {asset_id:model.asset_id, request_id:model.request_id})));
      });
      $("tasks").append(card);
    }
    if (!filtered.length) {
      const empty = textNode("div", ""); empty.className = "tasks-empty";
      const copy = textNode("div", "");
      copy.append(textNode("strong", tasks.length ? "这个分类下还没有任务" : "你的下一件作品，从这里开始"), textNode("p", tasks.length ? "切换到「全部」查看历史记录。" : "生成、导入与修改的进度会保留在这里，随时回来继续。"));
      empty.append(copy); $("tasks").append(empty);
    }
  }
  async function refresh() { if (refreshing) return; refreshing = true; try { render(await call("state")); } finally { refreshing = false; } }
  async function submitted(actionName, values) { const task = await call(actionName, values); notice("任务已开始，可在左侧「任务」查看进度。"); return task; }
  let adaptationPlan = null, semanticIndex = null;
  const chosenPaths = () => $("semanticPaths").value.split(/\n/).map(x=>x.trim()).filter(Boolean);
  function fillProfile(profile) {
    $("profileDestination").value=profile.organization.destination;
    $("profileModelPrefix").value=profile.organization.rules?.model?.prefix || "SM_";
    $("profileTriangles").value=profile.preparation.triangle_budget;
    $("profileTexture").value=profile.preparation.texture_size;
    $("profileCollision").value=profile.preparation.collision;
    $("profileLods").value=profile.preparation.lod_ratios.join(", ");
    $("profileInbox").value=profile.intake.folder;$("profileAuto").checked=profile.intake.enabled;
  }
  bind("loadProfile",async()=>{const value=await call("profile");fillProfile(value);return value;});
  bind("saveProfile",async()=>{const old=await call("profile");const value=await call("profile",{mode:"save",settings:{
    organization:{...old.organization,destination:$("profileDestination").value.trim(),rules:{...old.organization.rules,model:{...old.organization.rules?.model,prefix:$("profileModelPrefix").value.trim()}}},
    preparation:{...old.preparation,triangle_budget:Number($("profileTriangles").value),texture_size:Number($("profileTexture").value),collision:$("profileCollision").value,lod_ratios:$("profileLods").value.split(/[,，\s]+/).filter(Boolean).map(Number)},
    intake:{...old.intake,folder:$("profileInbox").value.trim(),enabled:$("profileAuto").checked}}});fillProfile(value);notice("项目规范已保存。新任务会使用这些设置。");return value;});
  bind("suggestProfile",async()=>{const scan=await waitAction(await call("organize",{mode:"scan"}));const value=await call("profile",{mode:"suggest",scan_id:scan.development.scan_id});$("profileSuggestions").replaceChildren();for(const [kind,row] of Object.entries(value.suggestions)){const card=textNode("p",`${kind}：${row.prefix} · ${row.count}/${row.total} 项，置信度 ${Math.round(row.confidence*100)}%`);$("profileSuggestions").append(card);}$("profileSuggestions").append(button("采用这些前缀",async()=>{const current=await call("profile");const rules={...current.organization.rules};for(const [kind,row] of Object.entries(value.suggestions))if(row.confidence>=.6)rules[kind]={...rules[kind],prefix:row.prefix};const saved=await call("profile",{mode:"save",settings:{organization:{...current.organization,rules}}});fillProfile(saved);return saved;}));return value;});
  async function inboxStatus() {
    const data=await call("intake");$("inboxEntries").replaceChildren(textNode("p",data.folder+(data.enabled?" · 自动入库已开启":" · 手动扫描")));
    for(const row of Object.values(data.entries)){const card=document.createElement("article");card.className="card";card.append(textNode("h3",row.path),textNode("p",humanStatus(row.task?.status)+" · "+(row.task?.error||row.task?.stage||row.asset_id)));if(["error","cancelled"].includes(row.task?.status))card.append(button("重试此项",()=>call("intake",{mode:"retry",paths:[row.path]})));$("inboxEntries").append(card);}
    return data;
  }
  bind("loadInbox",inboxStatus);
  for(const [id,mode] of [["scanInbox","scan"],["retryInbox","retry"]])bind(id,async()=>{const result=await call("intake",{mode});await inboxStatus();notice(`${result.tasks.length} 个任务开始，${result.skipped.length} 项跳过，${result.errors.length} 项需处理。`);for(const e of [...result.errors,...result.skipped])$("inboxEntries").append(textNode("p",e.path+" · "+(e.error||e.reason)));return result;});
  bind("semanticSearch",async()=>{
    if(!semanticIndex){const index=await waitAction(await call("library"));semanticIndex=index.request_id;}
    const result=await call("library",{request_id:semanticIndex,query:$("semanticQuery").value,limit:100});$("semanticPicker").replaceChildren();
    for(const row of result.development.entries){const card=document.createElement("article");card.className="card";const label=document.createElement("label"),check=document.createElement("input");check.type="checkbox";check.checked=chosenPaths().includes(row.path);check.onchange=()=>{const set=new Set(chosenPaths());check.checked?set.add(row.path):set.delete(row.path);$("semanticPaths").value=[...set].join("\n");};label.append(check,document.createTextNode(" "+(row.semantic?.name||row.name)));card.append(label,textNode("small",row.path),textNode("p",row.tags.join(" · ")));card.append(button("设为外观参考",()=>{$("adaptReference").value=row.path;return row;}));$("semanticPicker").append(card);}
    return result;
  });
  bind("captureSemantics",()=>submitted("semantic",{paths:chosenPaths()}));
  bind("providerSemantics",()=>submitted("semantic",{paths:chosenPaths(),use_provider:true,allow_remote:$("visionRemote").checked}));
  bind("saveVision",async()=>{const result=await call("vision",{endpoint:$("visionEndpoint").value,model:$("visionModel").value,api_key:$("visionKey").value||null});$("visionKey").value="";notice("视觉模型配置已保存。");return result;});
  async function semanticResults(task) {
    selectTab("pipeline");document.querySelectorAll("#pipeline details").forEach(d=>d.open=d.contains($("semanticEvidence")));$("semanticEvidence").replaceChildren();
    for(const row of task.results||[]){const card=document.createElement("article");card.className="card";const picture=document.createElement("img");picture.alt="引擎捕获的素材图";picture.style.width="100%";picture.src=(await call("image",{kind:"engine",request_id:row.request_id})).url;card.append(textNode("h3",row.path),picture);
      const description=row.description?.semantic || {name:"",object_type:"",description:"",materials:[],style:"",uses:[],confidence:0};const inputs={};
      for(const [key,title] of [["name","建议名称"],["object_type","物体类型"],["description","描述"],["materials","材质（逗号分隔）"],["style","风格"],["uses","用途（逗号分隔）"],["confidence","置信度 0–1"]]){const label=textNode("label",title),input=document.createElement("input");input.value=Array.isArray(description[key])?description[key].join(", "):description[key];label.append(input);card.append(label);inputs[key]=input;}
      card.append(button("保存我的识别与纠正",()=>call("semantic_save",{evidence_id:row.request_id,corrected:true,description:{...Object.fromEntries(Object.entries(inputs).map(([k,v])=>[k,v.value])),materials:inputs.materials.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),uses:inputs.uses.value.split(/[,，]/).map(x=>x.trim()).filter(Boolean),confidence:Number(inputs.confidence.value)}})));
      card.append(button("按此名称预览整理",async()=>{const scan=await waitAction(await call("organize",{mode:"scan"}));const plan=await call("organize",{mode:"plan",scan_id:scan.development.scan_id,settings:{include:[row.path],overrides:{[row.path]:inputs.name.value}}});selectTab("organizer");await loadOrganization(plan.plan_id);return plan;}));
      if(embedded)card.append(button("请当前 AI 识别这张图",()=>rpc("ui/message",{role:"user",content:[{type:"text",text:`请调用 get_asset_evidence 查看证据 ${row.request_id}，描述 ${row.path} 的实际内容，并用 save_asset_description 保存含置信度的建议。`}] })));
      $("semanticEvidence").append(card);
    }return task;
  }
  bind("previewAdaptation",()=>submitted("adaptation",{paths:chosenPaths().filter(p=>p!==$("adaptReference").value.trim()),reference:$("adaptReference").value.trim(),fields:[["adaptColor","color"],["adaptRoughness","roughness"],["adaptScale","texture_scale"]].filter(([id])=>$(id).checked).map(([,value])=>value)}));
  async function adaptationResults(task) {
    selectTab("pipeline");document.querySelectorAll("#pipeline details").forEach(d=>d.open=d.contains($("previewAdaptation")));adaptationPlan=task.plan_id;$("adaptationRows").replaceChildren();++previewSequence;$("previews").replaceChildren();
    const plan=await call("adaptation",{mode:"inspect",plan_id:adaptationPlan});for(const warning of plan.warnings||[])$("adaptationRows").append(textNode("p",warning));
    for(const row of plan.entries){const label=textNode("label",`${row.path} · 槽 ${row.slot} · ${row.fields.join(", ")}`),check=document.createElement("input");check.type="checkbox";check.checked=true;check.dataset.adaptationRow=row.id;label.prepend(check);$("adaptationRows").append(label);}
    for(const row of task.previews||[]){await showImage({kind:"engine",request_id:row.before},row.path+" · 原始",true);await showImage({kind:"engine",request_id:row.after},row.path+" · 参考适配",true);}
    $("applyAdaptation").disabled=!plan.entries.length;$("undoAdaptation").disabled=false;$("adaptationRows").scrollIntoView({behavior:"smooth",block:"center"});return plan;
  }
  bind("applyAdaptation",async()=>{const selected=[...document.querySelectorAll("[data-adaptation-row]:checked")].map(x=>x.dataset.adaptationRow);if(!selected.length)throw Error("请先勾选要应用的材质槽。");return submitted("adaptation",{mode:"apply",plan_id:adaptationPlan,selected});});
  bind("undoAdaptation",()=>submitted("adaptation",{mode:"undo",plan_id:adaptationPlan}));

  function workspaceView(view) {
    const previous = document.body.dataset.view;
    if (previous !== view && !["create", "scene"].includes(view)) {
      ++canvasEpoch; ++previewSequence;
    }
    document.body.dataset.view = view;
    document.querySelectorAll("[data-view]").forEach(node => {
      if (node.tagName !== "BUTTON") return;
      if (node.dataset.view === view) node.setAttribute("aria-current", "page");
      else node.removeAttribute("aria-current");
    });
    $("creationLibraryPanel").hidden = view !== "gallery";
    $("workspaceGrid").hidden = view === "gallery";
    $("taskTray").hidden = view !== "tasks";
    $("contextBar").hidden = !["create", "scene"].includes(view);
    $("creationComposer").hidden = view !== "create" || activeTab !== "creations";
    document.querySelector(".context-nav").hidden = view === "gallery";
    document.querySelectorAll("[data-tab]").forEach(tab => { tab.hidden = !(groups[view] || []).includes(tab.dataset.tab); });
    $("resultDetails").open = false;
    expandPreview(false);
  }
  function showGallery() {
    workspaceView("gallery");
    document.body.classList.remove("flow-workspace", "project-workspace");
    document.querySelector(".toolbar").hidden = true;
    $("imageLibraryPanel").hidden = true;
    [$("sectionLabel").textContent, $("pageTitle").textContent, $("pageSubtitle").textContent] = ["YOUR COLLECTION", "作品展廊", "从想法到游戏，让每件作品继续生长。"];
    window.dispatchEvent(new CustomEvent("pts:gallery"));
  }
  function selectTab(name) {
    if (!tabs[name]) return;
    activeTab = name;
    const view = Object.keys(groups).find(key => groups[key].includes(name));
    workspaceView(view);
    document.body.classList.remove("project-preview");
    document.body.classList.toggle("flow-workspace", ["flows", "missions"].includes(name));
    document.body.classList.toggle("project-workspace", view === "project" && name !== "organizer");
    if(name === "pipeline" && snapshot.target && !$("profileDestination").value) call("profile").then(fillProfile).catch(e => notice(e.message,true));
    document.querySelectorAll("[data-tab]").forEach(tab => {
      const selected = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(selected)); tab.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll(".pane").forEach(p => {p.hidden = p.id !== name;});
    $("scenePreview").hidden = name === "organizer";
    $("organizationPreview").hidden = name !== "organizer";
    document.querySelector(".toolbar").hidden = !["edit", "review", "performance", "compose", "level", "gameplay"].includes(name);
    $("objectDetails").hidden = ["images", "creations"].includes(name);
    $("imageLibraryPanel").hidden = name !== "images";
    [$("sectionLabel").textContent, $("pageTitle").textContent, $("pageSubtitle").textContent] = tabs[name];
    if (view === "scene") { $("canvasTitle").textContent = tabs[name][1]; $("canvasType").textContent = "场景工具"; }
    else if (view === "create") { $("canvasTitle").textContent = canvasContext?.title || "新的作品"; $("canvasType").textContent = canvasContext ? "创作画布" : "新建"; }
    $("scenePreview").querySelector("h2").textContent = name === "images" ? "图片与 UI 预览" : "作品预览";
    window.dispatchEvent(new CustomEvent("pts:tab",{detail:name}));
    if (name === "images") loadImageThumbnails();
  }
  function openCanvas(context = null) {
    canvasContext = context; ++canvasEpoch; ++previewSequence;
    window.PTS?.clearVisual?.();
    $("previews").replaceChildren(); $("previewEmpty").hidden = false;
    $("showExample").hidden = !!context;
    $("previewCaption").textContent = context ? "正在打开作品…" : "等待你的第一个想法";
    $("previewMeta").textContent = "模型 / 图片 / 游戏 UI";
    $("creationFocus").hidden = true; $("regionEditor").hidden = true; $("creationHandoffBox").hidden = true;
    $("creationPrompt").value = "";
    for (const name of ["itemId", "itemName", "itemDescription", "screenId", "screenTitle", "creationReference"]) $(name).value = "";
    $("screenTheme").checked = false;
    $("creationId").value = context?.id || ""; $("creationId").readOnly = !!context;
    $("creationKind").value = context?.kind || "item"; $("creationKind").disabled = !!context;
    $("creationBrief").textContent = context ? "准备修改 ↗" : "准备创作 ↗";
    $("composerLabel").textContent = context ? "描述想调整的地方" : "描述你的下一件作品";
    $("creationPrompt").placeholder = context ? "例如：保留轮廓，把材质改得温暖一些，沿用现有玩法与布局…" : "例如：为森林药剂师制作一瓶恢复药水，配套背包图标与拾取效果…";
    $("inspectorTitle").textContent = context?.title || "作品设置";
    $("inspectorDescription").textContent = context?.description || (context ? "选择要调整的部分，已有资源与关联继续沿用。" : "从下方描述开始。模型、图标与游戏界面会沿用项目风格。");
    $("exampleDetails").hidden = !!context;
    $("creationAdvanced").hidden = false;
    $("itemDetails").hidden = !!context && !["item", "model"].includes(context.kind);
    $("screenDetails").hidden = !!context && !["item", "ui"].includes(context.kind);
    for (const name of ["creationAdvanced", "itemDetails", "screenDetails"]) $(name).open = false;
    $("asset").value = context?.model || (context?.kind === "model" ? context.id : "");
    loadAsset().catch(error => notice(error.message,true));
    selectTab("creations");
    return {epoch:canvasEpoch, project:snapshot.active};
  }
  function canvasCurrent(ticket) { return ticket.epoch === canvasEpoch && ticket.project === snapshot.active; }
  $("backGallery").onclick = showGallery;
  $("newCreation").onclick = () => { openCanvas(); $("creationPrompt").focus(); };
  $("refreshGallery").onclick = event => action(event.currentTarget, refresh);
  document.querySelectorAll(".studio-nav [data-view]").forEach(button => {
    button.onclick = () => {
      const view = button.dataset.view;
      if (view === "gallery") showGallery();
      else if (view === "create") { openCanvas(); $("creationPrompt").focus(); }
      else selectTab({scene:"compose",tasks:"missions",project:"pipeline"}[view]);
    };
  });
  $("creationPrompt").onkeydown = event => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); $("creationBrief").click(); }
  };
  const imageDefaults={icon:[256,256,true],button:[512,256,true],panel:[512,512,true],portrait:[768,1024,true],background:[1920,1080,false],texture:[1024,1024,false]};
  function imageDefaultsChanged() {
    const kind=$("imageKind").value,[width,height,alpha]=imageDefaults[kind];
    $("imageWidth").value=width;$("imageHeight").value=height;$("imageAlpha").checked=alpha;
    $("imageFit").value=alpha?"contain":"cover";
    $("imageBorder").value=["button","panel"].includes(kind)?Array(4).fill(Math.floor(Math.min(width,height)/8)).join(", "):"0, 0, 0, 0";
  }
  $("imageKind").onchange=imageDefaultsChanged;
  async function imagePlan() {
    await ensureGameArt();
    $("imageName").value=id($("imageName").value,$("imageKind").value);
    await window.PTS.ensureAssetUsage($("imageName").value);
    const border=$("imageBorder").value.split(/[,，\s]+/).filter(Boolean).map(Number);
    const values={asset_id:$("imageName").value,prompt:$("imagePrompt").value.trim()||$("imageName").value,
      kind:$("imageKind").value,width:Number($("imageWidth").value),height:Number($("imageHeight").value),
      transparent:$("imageAlpha").checked,pixel_art:$("imagePixel").checked,fit:$("imageFit").value,border};
    const references=$("imageReferences").value.split(/\n/).map(x=>x.trim()).filter(Boolean);
    if(references.length)values.reference_paths=references;
    return workflowAction("plan_image",values);
  }
  bind("imageBrief",async()=>{
    const plan=await imagePlan();
    const message=`请用当前客户端可用的图片生成工具，按 Prompt-to-Scene 的图片计划 ${plan.plan_id} 为 ${plan.asset_id} 生成素材。\n${plan.effective_prompt}\n参考图片：${plan.references.map(r=>r.path).join("、")||"无"}\n生成后调用 game_workflow 执行 import_image，asset_id=${plan.asset_id}，plan_id=${plan.plan_id}，source 填实际图片的本地路径。检查 image_preview；等待导入任务成功。没有图片工具时说明并使用已配置的图片服务，不要编造文件路径。`;
    $("imageHandoff").value=message;$("imageHandoffBox").hidden=false;
    if(embedded){await rpc("ui/message",{role:"user",content:[{type:"text",text:message}]});notice("已把图片任务交给当前 AI。");}
    else notice("图片指令已准备好，可复制给 Codex 或 Harness。生成后会自动接回导入流程。");
    return plan;
  });
  bind("copyImageBrief",async()=>{await navigator.clipboard.writeText($("imageHandoff").value);notice("已复制图片生成指令。");});
  bind("pickGameImage",async()=>{$("imageSource").value=await local("pick",{kind:"reference"});});
  async function takeImage(previewOnly) {
    if(!$("imageSource").value.trim())throw Error("请选择生成好的图片，或用「交给 AI 生成」准备指令。");
    const plan=await imagePlan();
    const result=await workflowAction("import_image",{asset_id:plan.asset_id,source:$("imageSource").value.trim(),plan_id:plan.plan_id,preview_only:previewOnly});
    await showImage({kind:"game_image",asset_id:plan.asset_id,request_id:result.revision},plan.asset_id+" · 实际准备后的图片");
    notice(previewOnly?"预览已准备，可从图片库导入。":"图片已排队导入，请保持目标编辑器打开。");return result;
  }
  bind("importGameImage",()=>takeImage(false));bind("previewGameImage",()=>takeImage(true));
  bind("exampleGameImage",async()=>{
    const task=await workflowAction("image_example");
    await showImage({kind:"game_image",asset_id:task.asset_id,request_id:task.revision},"示例药水 · AI 生成的实际透明图标");
    notice("示例图标已排队导入，无需配置图片服务。");return task;
  });
  bind("saveImageProvider",async()=>{
    const result=await workflowAction("image_provider",{endpoint:$("imageEndpoint").value.trim(),model:$("imageModel").value.trim(),api_style:$("imageApiStyle").value,api_key:$("imageKey").value||null});
    $("imageKey").value="";notice("图片服务配置已保存。");return result;
  });
  bind("loadImageProvider",async()=>{
    const data=await workflowAction("image_provider");$("imageEndpoint").value=data.endpoint||"";$("imageModel").value=data.model||"";$("imageApiStyle").value=data.api_style||"gpt_image";
    notice(data.configured?"已读取图片服务配置。":"尚未配置，可先用当前 AI 客户端生成图片。");return data;
  });
  bind("generateGameImage",async()=>{
    const plan=await imagePlan();const task=await workflowAction("generate_image",{plan_id:plan.plan_id,allow_remote:$("imageRemote").checked,preview_only:$("imageReviewFirst").checked});
    notice("图片任务已开始，可在「任务」查看进度。");return task;
  });
  function renderImageLibrary(rows) {
    const signature=JSON.stringify(rows);
    if($("imageAssets").dataset.signature===signature)return;
    $("imageAssets").dataset.signature=signature;$("imageAssets").replaceChildren();
    for(const row of rows) {
      const card=document.createElement("article");card.className="card";
      const thumbnail=textNode("div", ""); thumbnail.className="image-thumbnail";
      thumbnail.dataset.imageAsset=row.asset_id; thumbnail.dataset.imageRevision=row.revisions[0].revision;
      thumbnail.append(textNode("span", "载入预览…")); card.append(thumbnail);
      const path=textNode("small",row.current?.texture_path||"已准备，尚未导入");path.className="asset-path";path.title=path.textContent;
      card.append(textNode("h3",row.asset_id),path);
      const revisions=document.createElement("select");revisions.setAttribute("aria-label",row.asset_id+" 的图片版本");
      for(const version of row.revisions)revisions.append(option(version.revision,`${new Date(version.created_utc).toLocaleString()} · ${version.settings.width}×${version.settings.height}${row.current?.revision===version.revision?" · 当前使用":""}`));
      revisions.onchange=()=>{thumbnail.dataset.imageRevision=revisions.value;delete thumbnail.dataset.loaded;loadImageThumbnails();};
      card.append(revisions);
      card.append(button("查看",async()=>{const v=row.revisions.find(r=>r.revision===revisions.value);await showImage({kind:"game_image",asset_id:row.asset_id,request_id:v.revision},row.asset_id+" · 实际图片");return v;}));
      card.append(button("导入／恢复此版",()=>workflowAction("publish_image",{asset_id:row.asset_id,revision:revisions.value})));
      card.append(button("以此图继续制作",()=>{
        const version=row.revisions.find(r=>r.revision===revisions.value),s=version.settings;
        $("imageName").value=row.asset_id;$("imageKind").value=s.kind;$("imagePrompt").value=version.prompt;
        $("imageWidth").value=s.width;$("imageHeight").value=s.height;$("imageFit").value=s.fit;
        $("imageAlpha").checked=s.transparent;$("imagePixel").checked=s.pixel_art;$("imageBorder").value=s.border.join(", ");
        $("imageReferences").value=version.reference_path;$("imagePrompt").focus();
        notice("已沿用这张图的尺寸与风格参考。描述修改后，点「交给 AI 生成」。");
      }));
      const report=row.revisions[0]?.report;
      card.append(textNode("p",`${report?.has_alpha?"带透明通道":"不透明"} · ${row.revisions.length} 个版本`));
      for(const warning of report?.warnings||[])card.append(textNode("small",warning));
      $("imageAssets").append(card);
    }
    if(!rows.length)$("imageAssets").append(textNode("p","生成并导入后的图片会保留在这里，可以查看和恢复旧版。"));
    if(activeTab === "images") loadImageThumbnails();
  }
  function loadImageThumbnails() {
    document.querySelectorAll("[data-image-asset]").forEach(node => {
      if(node.dataset.loaded === node.dataset.imageRevision) return;
      const revision = node.dataset.imageRevision; node.dataset.loaded = revision;
      cachedImage({kind:"game_image",asset_id:node.dataset.imageAsset,request_id:revision}).then(data => {
        if(!node.isConnected || node.dataset.imageRevision !== revision) return;
        const img=document.createElement("img");img.src=data.url;img.alt=node.dataset.imageAsset+" 的实际图片";img.className="alphaPreview";img.loading="lazy";node.replaceChildren(img);
      }).catch(() => { if(node.isConnected && node.dataset.imageRevision === revision) node.replaceChildren(textNode("small","预览暂不可用，可点击「查看」重试。")); });
    });
  }
  const navigation = [...document.querySelectorAll("[data-tab]")];
  for (const tab of navigation) {
    tab.onclick = () => selectTab(tab.dataset.tab);
    tab.onkeydown = event => {
      const visible = navigation.filter(node => !node.hidden);
      const index = visible.indexOf(tab);
      const next = {ArrowDown:(index+1)%visible.length, ArrowRight:(index+1)%visible.length, ArrowUp:(index-1+visible.length)%visible.length, ArrowLeft:(index-1+visible.length)%visible.length, Home:0, End:visible.length-1}[event.key];
      if(next == null) return;
      event.preventDefault(); visible[next].focus(); selectTab(visible[next].dataset.tab);
    };
  }
  for (const node of document.querySelectorAll("[data-task-filter]")) node.onclick = () => {
    taskFilter = node.dataset.taskFilter;
    document.querySelectorAll("[data-task-filter]").forEach(button => button.setAttribute("aria-pressed",String(button === node)));
    render(snapshot);
  };
  for (const node of document.querySelectorAll("[data-model-prompt]")) node.onclick = () => { $("prompt").value = node.dataset.modelPrompt; $("prompt").focus(); };
  for (const node of document.querySelectorAll("[data-image-prompt]")) node.onclick = () => {
    $("imageKind").value = node.dataset.imageKind || "icon"; imageDefaultsChanged();
    $("imagePrompt").value = node.dataset.imagePrompt; $("imagePrompt").focus();
  };
  $("asset").onchange = () => loadAsset().catch(error => notice(error.message,true)); $("part").onchange = partInfo;
  $("briefNotes").oninput = () => { $("briefNotes").dataset.dirty = "1"; };
  for (const id of Object.keys(gameFields)) $(id).oninput = () => { $("gameContext").dataset.dirty = "1"; };
  bind("saveGameArt", saveGameArt);
  bind("refresh", async () => { await refresh(); await loadAsset(); notice("已刷新项目状态。"); });
  bind("scene", async () => {
    const scene = await waitAction(await call("scene")); if (scene.status !== "completed") return scene;
    $("objectList").replaceChildren();
    for (const obj of scene.context || []) $("objectList").append(button(obj.name + (obj.asset_id ? " · " + obj.asset_id : ""), async () => {
      const selected = await waitAction(await call("select", {object_id:obj.id}));
      if (obj.asset_id) { $("asset").value = obj.asset_id; await loadAsset(); }
      notice("已在编辑器中选择「" + obj.name + "」。后续布局可使用它作为参照。");
      if (embedded) await rpc("ui/update-model-context", {content:[{type:"text",text:JSON.stringify({selected_object:obj})}]}).catch(() => {});
      return selected;
    }));
    const selected = scene.selected?.[0]?.asset_id;
    if (selected) { $("asset").value = selected; await loadAsset(); }
    return scene;
  });
  bind("preview", async () => { const task = await waitAction(await call("preview", {asset_id:requiredAsset()})); if (task.status === "completed") await showImage({kind:"engine",request_id:task.request_id}, "当前引擎画面"); return task; });
  bind("createLocal", async () => {
    await ensureGameArt();
    const kind=$("recipeKind").value, asset_id=id($("generationName").value,kind);
    const task=await workflowAction("produce",{description:$("prompt").value.trim()||kind,items:[{asset_id,method:"recipe",kind}]});
    notice("制作、材质准备和导入已合并为一个任务，可在下方查看进度。");return task;
  });
  bind("importLocal", () => submitted("import", {asset_id:id($("generationName").value,"model"), source:{provider:"local",path:$("sourcePath").value}}));
  bind("generateButton", async () => {
    await ensureGameArt();
    const asset_id=id($("generationName").value,"model"),prompt=$("prompt").value;
    await call("design",{asset_id,description:prompt,role:$("assetRole").value});
    return submitted("generate", {asset_id,prompt,provider:$("provider").value,image_paths:$("generationImages").value.split(/\n/).map(x=>x.trim()).filter(Boolean),candidate_count:Number($("candidateCount").value),allow_paid:$("paid").checked,preview_only:true});
  });
  bind("askAI", async () => {
    const prompt = $("prompt").value.trim(); if(!prompt) throw Error("请先写下希望制作或修改的内容。");
    await ensureGameArt();
    const message = prompt + "\n请通过 Prompt-to-Scene 的 game_workflow 读取当前项目的游戏方向，使用 produce 统一制作、导入；结合玩法与背景设计具体造型，并从游戏摄像机检查实际效果。资产用途：" + $("assetRole").selectedOptions[0].textContent + ($("asset").value ? "\n当前选中的资产：" + $("asset").value : "") + window.PTS.sceneHandoff();
    if (embedded) {
      await rpc("ui/message", {role:"user",content:[{type:"text",text:message}]});
      notice("已把描述和当前资产发给本次聊天的 AI。");
    } else {
      $("modelHandoffBox").hidden = false; $("modelHandoff").value = message;
      notice("制作指令已准备好。复制给已连接的 Codex 或 Harness，即可继续制作。");
    }
  });
  bind("copyModelBrief",async()=>{await navigator.clipboard.writeText($("modelHandoff").value);notice("已复制制作指令。");});
  bind("composeButton", () => submitted("compose", {kit:$("kit").value,prefix:id($("kitPrefix").value,"corner"),position:position(),yaw:Number($("yaw").value)}));
  bind("saveLayout", () => submitted("compose", {mode:"save",template:$("templateName").value.trim()}));
  bind("placeLayout", () => submitted("compose", {mode:"place",template:$("layouts").value,position:position(),yaw:Number($("yaw").value)}));
  function changePart(changes) { return submitted("part", {asset_id:requiredAsset(),part:requiredPart(),changes}); }
  bind("editPart", () => {
    const changes = {};
    if ($("partScale").value) changes.scale = Array(3).fill(Number($("partScale").value));
    if ($("roughness").value) changes.roughness = Number($("roughness").value);
    if ($("applyColor").checked) changes.color = $("partColor").value.slice(1).match(/../g).map(x => {const c = parseInt(x,16)/255; return c <= .04045 ? c/12.92 : ((c+.055)/1.055)**2.4;});
    if (!Object.keys(changes).length) throw Error("填写一项修改即可。"); return changePart(changes);
  });
  bind("saveLocks", () => submitted("part", {asset_id:requiredAsset(),part:requiredPart(),lock_geometry:$("geometryLock").checked,lock_material:$("materialLock").checked}));
  bind("applyPartChanges", () => changePart(JSON.parse($("partChanges").value)));
  bind("groupParts", () => submitted("external_part", {asset_id:requiredAsset(),part:$("groupName").value,members:$("groupMembers").value.split(/\n/).map(x=>x.trim()).filter(Boolean)}));
  bind("replacePart", () => submitted("external_part", {asset_id:requiredAsset(),part:requiredPart(),replacement_path:$("replacementPath").value}));
  bind("saveBrief", async () => { const result = await call("art_brief", {notes:$("briefNotes").value,image_path:$("referencePath").value || null}); delete $("briefNotes").dataset.dirty; if (result.image) await showImage({kind:"reference"},"保存的美术参考"); notice("美术参考已保存到当前项目。"); return result; });
  bind("qualityButton", () => submitted("quality", {asset_id:requiredAsset(),auto_fix:$("autoFix").checked,preset:$("usage").value,view:$("reviewView").value}));
  bind("acceptVisual",async()=>{if(!activeReview)throw Error("先打开一组已完成的画面对照。");const proof=await workflowAction("review_images",{request_id:activeReview});return workflowAction("feedback",{request_id:activeReview,token:proof.token,accepted:true,observations:"用户在创作台查看对照后接受此版本。",preference:$("visualPreference").value});});
  bind("saveDesign",()=>workflowAction("save_design",{name:$("designName").value.trim(),asset_id:requiredAsset(),description:$("designDescription").value}));
  bind("listDesigns",async()=>{const result=await workflowAction("find_designs");$("savedDesigns").replaceChildren();for(const row of result.templates){const card=document.createElement("article");card.className="card";card.append(textNode("h3",row.name),textNode("p",row.notes),button("制作同系列新资产",()=>workflowAction("reuse_design",{name:row.name,asset_id:id("",row.name),family_style:true})));$("savedDesigns").append(card);}return result;});
  bind("furnishRoomButton",()=>workflowAction("furnish",{level_id:$("levelName").value.trim(),asset_ids:Array.from($("furnishAssets").selectedOptions).map(o=>o.value),room_index:Number($("furnishRoom").value)}));
  bind("configureCurrentInteraction",()=>{const kind=$("interactionKind").value;if(["door","chest"].includes(kind))throw Error("请在聊天中指定门或宝箱的独立活动部件。");return workflowAction("interaction",{asset_id:requiredAsset(),kind,uses:Number($("resourceUses").value),label:$("interactionLabel").value,event_id:$("interactionEvent").value.trim(),demo_input:$("interactionDemo").checked});});
  bind("repairButton", () => { if (!activeReview) throw Error("先打开一个已完成任务的前后对照。"); return submitted("repair", {request_id:activeReview,part:requiredPart(),changes:JSON.parse($("partChanges").value)}); });
  bind("analyze", async () => {
    let result = await call("performance", {asset_id:requiredAsset(),preset:$("usage").value});
    if (result.status !== "completed") { const task = await waitAction(result); if (task.status !== "completed") return task; result = await call("performance", {request_id:task.request_id,preset:$("usage").value}); }
    const table = document.createElement("table");
    for (const row of result.metrics || []) {
      for (const [label,value] of [["三角面 / 顶点",`${row.triangles} / ${row.vertices}`],["材质槽 / 纹理",`${row.material_slots} / ${row.texture_count}`],["纹理估算",`${(row.texture_bytes_estimate/1048576).toFixed(1)} MiB · RGBA8 + mip`],["各 LOD 面数",row.lod_triangles?.join(" → ")]]) { const tr=document.createElement("tr"); tr.append(textNode("th",label),textNode("td",value)); table.append(tr); }
    }
    $("metrics").replaceChildren(table, textNode("p",`${result.recommendations.length} 项建议；不据此推算 FPS 或 Draw Call。`)); return result;
  });
  bind("optimize", () => submitted("optimize", {asset_id:requiredAsset(),preset:$("usage").value}));
  function vectorInput(name, fallback = [0,0,0]) {
    const text = $(name).value.trim(); if (!text) return fallback;
    const values = text.split(/[,，\s]+/).map(Number);
    if (values.length !== 3 || values.some(v => !Number.isFinite(v))) throw Error("位置需要三个有限数字。");
    return values;
  }
  async function native(actionName, values, panel) {
    const result = await waitAction(await call(actionName, values));
    if (result.status !== "completed") return result;
    const data = result.development || {};
    if (panel) {
      const content = [];
      if (data.command === "playcheck") {
        content.push(textNode("h3", data.passed ? "试玩检查通过" : "有检查未通过"));
        for (const check of data.checks || []) content.push(textNode("p", `${check.passed ? "✓" : "✕"} ${check.asset_id} · ${check.check}${check.detail ? " · " + check.detail : ""}`));
        content.push(textNode("p", `${data.frames || 0} 帧 · 平均 ${(data.mean_frame_ms || 0).toFixed(1)} ms · P95 ${(data.p95_frame_ms || 0).toFixed(1)} ms。仅代表当前编辑器和电脑。`));
        if (data.screenshots?.length) {
          await showImage({kind:"play_before",request_id:result.request_id}, "试玩前 · 同一机位");
          await showImage({kind:"engine",request_id:result.request_id}, "执行交互后", true);
        }
      } else if (data.command === "protection") {
        for (const b of data.bindings || []) content.push(textNode("p", `${b.slot} → ${b.material_path}`));
        for (const s of data.sockets || []) content.push(textNode("p", `挂点 ${s.name} · ${(s.position || []).join(", ")}`));
        if (!content.length) content.push(textNode("p", "当前没有自定义材质覆盖或挂点。"));
      } else if (data.command === "level") {
        content.push(textNode("p", data.passed ? `净空通过 · ${data.module_count || 0} 个模块 · ${data.samples || 0} 个检查位置` : (data.conflicts || []).join("、") || "操作已完成"));
      }
      $(panel).replaceChildren(...content);
    }
    notice(data.command === "playcheck" ? (data.passed ? "试玩检查完成，已返回编辑模式。" : "试玩发现需要处理的项目，请查看检查结果。") : "操作已完成。", data.command === "playcheck" && !data.passed);
    return result;
  }
  bind("createInteractive", () => submitted("interactive", {kind:$("interactionKind").value,asset_id:id($("interactionName").value,$("interactionKind").value),position:vectorInput("interactionPosition")}));
  bind("inspectProtection", () => native("protection", {asset_id:requiredAsset()}, "protectionSummary"));
  bind("saveMaterialOverride", () => native("protection", {asset_id:requiredAsset(),mode:"set",bindings:[{slot:$("protectedSlot").value.trim(),material_path:$("protectedMaterial").value.trim()}]}, "protectionSummary"));
  bind("saveSocket", () => native("protection", {asset_id:requiredAsset(),mode:"set",sockets:[{name:$("socketName").value.trim(),position:vectorInput("socketPosition")}]}, "protectionSummary"));
  bind("playcheck", () => native("playcheck", {asset_ids:[requiredAsset()]}, "playcheckSummary"));
  bind("applyLook", () => native("look", {preset:$("sceneLook").value}));
  bind("captureLook", async () => {const result=await native("look",{mode:"capture"});if(result.status==="completed")await showImage({kind:"engine",request_id:result.request_id},"当前场景 · 展示机位");return result;});
  bind("restoreLook", () => native("look", {mode:"restore"}));
  function levelValues(mode) {
    const room=cell=>({cell,kind:"room"}), corridor=(cell,direction=2)=>({cell,kind:"corridor",direction});
    const modules=$("levelPreset").value==="stairs" ? [room([0,0,0]),{cell:[0,1,0],kind:"stair",direction:2},room([0,2,1])] : $("levelPreset").value==="corner" ? [room([0,0,0]),corridor([0,1,0]),room([0,2,0]),corridor([1,2,0],1),room([2,2,0])] : [room([0,0,0]),corridor([0,1,0]),room([0,2,0])];
    return {level_id:$("levelName").value.trim(),mode,...(["build","plan"].includes(mode)?{modules,position:vectorInput("levelPosition",[20,0,0]),door_width:Number($("levelDoorWidth").value),player_height:Number($("levelPlayerHeight").value)}:{})};
  }
  bind("planLevel", async () => {const plan=await call("level",levelValues("plan"));$("levelSummary").replaceChildren(textNode("p",`计划：${plan.module_count} 个模块、${plan.connections.length} 个连接口、${plan.boxes.length} 块几何。可在搭建后检查实际净空。`));return plan;});
  bind("buildLevel", () => native("level", levelValues("build"), "levelSummary"));
  bind("checkLevel", () => native("level", levelValues("check"), "levelSummary"));
  bind("removeLevel", () => native("level", levelValues("remove"), "levelSummary"));
  bind("playLevel", () => native("playcheck", {level_id:$("levelName").value.trim()}, "levelSummary"));
  bind("searchLibrary", async () => {
    const indexed=await waitAction(await call("library",{query:$("libraryQuery").value}));if(indexed.status!=="completed")return indexed;
    const result=await call("library",{request_id:indexed.request_id,query:$("libraryQuery").value,limit:12});$("libraryResults").replaceChildren();
    for(const entry of result.development?.entries || []) {
      const card=document.createElement("article");card.className="card";
      card.append(textNode("h3",entry.name),textNode("small",entry.path),textNode("p",`${(entry.size || []).map(v=>v.toFixed(2)).join(" × ")} m · ${entry.triangles || 0} 三角面`),textNode("p",entry.license || "许可证待确认"));
      card.append(button("预览",async()=>{const task=await waitAction(await call("reuse",{path:entry.path,mode:"preview"}));if(task.status==="completed"){const data=await call("image",{kind:"engine",request_id:task.request_id});let img=card.querySelector("img");if(!img){img=document.createElement("img");card.prepend(img);}img.alt=entry.name;img.src=data.url;}return task;}));
      card.append(button("放入场景",()=>native("reuse",{path:entry.path,position:vectorInput("libraryPosition")})));
      card.append(button("编辑说明",()=>{$("libraryPath").value=entry.path;$("libraryTags").value=(entry.tags || []).join(", ");$("libraryNotes").value=entry.notes || "";$("libraryLicense").value=entry.license?.startsWith("Unknown")?"":entry.license || "";$("librarySource").value=entry.source || "";$("libraryPath").closest("details").open=true;}));
      $("libraryResults").append(card);
    }
    if(!result.development?.entries?.length)$("libraryResults").append(textNode("p","没有匹配项。可换一个关键词，或为现有资源补充标签。"));
    notice(result.development?.truncated?"当前索引到 2,000 个资源；大型项目可先按文件夹整理再查找。":"项目素材已读取。");return result;
  });
  bind("tagLibrary", () => call("tag",{path:$("libraryPath").value,tags:$("libraryTags").value.split(/[,，]/).map(t=>t.trim()).filter(Boolean),notes:$("libraryNotes").value,license:$("libraryLicense").value,source:$("librarySource").value}));
  const organizationKinds={model:"模型",skeletal_mesh:"骨骼模型",prefab:"预制体",blueprint:"蓝图",material:"材质",material_instance:"材质实例",texture:"贴图",sprite:"精灵",audio:"音频",animation:"动画",controller:"动画控制器",vfx:"特效",font:"字体",scene:"场景",script:"代码",shader:"着色器",data:"数据",redirector:"重定向",other:"其他"};
  const organizationStatuses={planned:"等待应用",applying:"正在整理",applied:"已整理",undoing:"正在撤销",undone:"已恢复原位置",rolled_back:"失败后已恢复原位置",cancelled:"已取消并恢复",recovery_required:"需要恢复原位置"};
  function organizationButtons() {$("applyOrganization").disabled=organizationPlan.status!=="planned" || !organizationPlan.summary.move;$("undoOrganization").disabled=!["applied","applying","undoing","recovery_required"].includes(organizationPlan.status);}
  function organizationReason(reason) {
    return {"Protected engine/plugin folder":"特殊目录或插件管理的资源，保持原位","Material path retained by a generated source revision":"源模型修订需要此材质路径，保持原位","Excluded by project rule":"已加入排除列表","Classified for review; this type stays in its original location":"已分类，此类型保持原位","Read-only asset":"资源为只读","AssetBundle address stays stable":"保持 AssetBundle 加载地址","Addressable address stays stable":"保持 Addressables 加载地址","External source dependencies require their original relative paths":"外部源文件依赖相对路径，保持原位","Save this asset before organizing":"先保存此资源","Destination path too long; shorten the folder or name":"目标路径过长，请缩短名称"}[reason] || reason;
  }
  function showOrganization(plan) {
    organizationPlan=plan; selectTab("organizer");
    $("organizeScope").value=plan.scope;$("organizeDestination").value=plan.destination;
    $("organizeGrouping").value=plan.settings.group_by||"type";$("organizeRename").checked=plan.settings.rename!==false;
    $("organizeExclude").value=(plan.settings.exclude||[]).join("\n");$("organizeNames").value=Object.entries(plan.settings.overrides||{}).map(([path,name])=>path+" => "+name).join("\n");
    const s=plan.summary;
    $("organizationSummary").className="";
    $("organizationSummary").replaceChildren(textNode("h3",organizationStatuses[plan.status] || plan.status),textNode("p",`扫描 ${s.scanned} 项 · 计划整理 ${s.move} 项 · 保持原位 ${s.skip} 项 · 已符合规则 ${s.keep} 项`),textNode("p",`已处理 ${plan.moved || 0} / ${s.move} 项 · ${s.collisions_resolved} 处重名已自动编号`));
    if(plan.journal?.error) $("organizationSummary").append(textNode("p",plan.journal.error));
    if(plan.metadata_error) $("organizationSummary").append(textNode("p","素材说明同步需要处理："+plan.metadata_error));
    organizationButtons();
    $("organizationRows").replaceChildren();
    for(const row of plan.entries) {
      const tr=document.createElement("tr");
      const action=row.action==="move"?(plan.status==="applied"?"已整理":plan.status==="undone"?"已撤销":"将命名并归类") : row.action==="keep"?"已符合规则":organizationReason(row.reason);
      const paths=document.createElement("td");paths.className="organization-paths";paths.style.overflowWrap="anywhere";
      paths.append(textNode("small",row.source),textNode("strong","→ "+row.destination));
      tr.append(textNode("td",organizationKinds[row.kind] || row.kind),paths,textNode("td",action+(row.collision_resolved?" · 自动编号":"")));
      $("organizationRows").append(tr);
    }
    $("organizationPage").textContent=plan.total?`${plan.offset+1}–${plan.offset+plan.entries.length} / ${plan.total} 项`:"没有资源";
    $("organizationPrevious").disabled=plan.offset===0;$("organizationNext").disabled=!plan.has_more;
  }
  async function loadOrganization(planId,offset=0) {
    const plan=await call("organize",{mode:"inspect",plan_id:planId,offset,limit:100});showOrganization(plan);return plan;
  }
  bind("planOrganization",async()=>{
    const overrides={};
    for(const line of $("organizeNames").value.split(/\r?\n/).filter(l=>l.trim())) {
      const parts=line.split("=>");if(parts.length!==2||!parts[0].trim()||!parts[1].trim())throw Error("自定义名称格式：原路径 => 新名称，每行一项。");
      overrides[parts[0].trim()]=parts[1].trim();
    }
    const settings={rename:$("organizeRename").checked,group_by:$("organizeGrouping").value,exclude:$("organizeExclude").value.split(/\r?\n/).map(p=>p.trim()).filter(Boolean),overrides};
    if($("organizeDestination").value.trim())settings.destination=$("organizeDestination").value.trim();
    const scan=await waitAction(await call("organize",{mode:"scan",scope:$("organizeScope").value.trim()||null}));if(scan.status!=="completed")return scan;
    const plan=await call("organize",{mode:"plan",scan_id:scan.request_id,settings,limit:100});showOrganization(plan);
    notice("整理方案已生成，项目资源尚未移动。查看下方原路径与目标路径，点击「应用此方案」完成整理。");return plan;
  });
  async function applyOrganization(mode) {
    if(!organizationPlan)throw Error("先扫描并生成整理方案。");
    const planId=organizationPlan.plan_id;
    notice(mode==="apply"?"正在整理资源，请保持编辑器打开。":"正在恢复原来的名称和目录，请保持编辑器打开。");
    try {
      const task=await waitAction(await call("organize",{mode,plan_id:planId}));
      if(task.status==="completed")notice(mode==="apply"?"资源命名与分类已完成，可以从整理记录撤销。":"已恢复资源原来的名称和位置。");
      return task;
    } finally {await loadOrganization(planId);}
  }
  bind("applyOrganization",()=>applyOrganization("apply"));bind("undoOrganization",()=>applyOrganization("undo"));
  bind("organizationPrevious",()=>loadOrganization(organizationPlan.plan_id,Math.max(0,organizationPlan.offset-100)));
  bind("organizationNext",()=>loadOrganization(organizationPlan.plan_id,organizationPlan.offset+100));
  bind("organizationHistory",async()=>{
    const history=await call("organize",{mode:"history"});$("organizationHistoryList").replaceChildren();
    for(const plan of history.plans){const card=document.createElement("article");card.className="card";card.append(textNode("h3",organizationStatuses[plan.status]||plan.status),textNode("p",plan.scope),textNode("small",`${plan.summary.move} 项 · ${new Date(plan.created_utc).toLocaleString()}`),button("查看记录",()=>loadOrganization(plan.plan_id)));$("organizationHistoryList").append(card);}
    if(!history.plans.length)$("organizationHistoryList").append(textNode("p","还没有整理记录。"));return history;
  });
  if (!embedded) {
    $("setupLink").href = "/#" + token;
    for (const [control,target,kind] of [["pickSource","sourcePath","asset"],["pickReference","referencePath","reference"],["pickGenerationImage","generationImages","reference"],["pickReplacement","replacementPath","asset"]]) bind(control, async () => { const chosen=await local("pick",{kind}); if(chosen.path) $(target).value=chosen.path; });
    bind("saveProvider", async () => { const key=$("providerKey").value; $("providerKey").value=""; const result=await local("provider",{provider:$("provider").value,endpoint:$("providerEndpoint").value || null,api_key:key || null}); notice("生成服务配置已保存。"); return result; });
  }
  async function start() {
    document.querySelectorAll(".localOnly").forEach(node => {node.hidden=embedded;});
    document.querySelectorAll(".inlineOnly").forEach(node => {node.hidden=!embedded;});
    if (embedded) {
      const initialized = await rpc("ui/initialize", {appInfo:{name:"Prompt-to-Scene",version:"0.15.0"},appCapabilities:{},protocolVersion:"2026-01-26"});
      hostCapabilities = initialized?.hostCapabilities || {};
      notify("ui/notifications/initialized", {});
      new ResizeObserver(() => notify("ui/notifications/size-changed",{height:Math.min(900,document.documentElement.scrollHeight)})).observe(document.body);
    }
    await refresh();
    if (!embedded) $("askAI").textContent = "生成制作指令";
    showGallery();
    setInterval(() => { if (!document.hidden) refresh().catch(error => notice(error.message,true)); }, 5000);
  }
  window.PTS={$,call,workflowAction,action,bind,button,textNode,option,notice,showImage,waitAction,refresh,selectTab,output,
    state:()=>snapshot,cachedImage,local,embedded,canvasTicket:()=>({epoch:canvasEpoch,project:snapshot.active}),showGallery,openCanvas,canvasCurrent,context:()=>canvasContext,beginVisual(){previewIsExample=false;++previewSequence;},
    async choosePart(asset,part){$("asset").value=asset;await loadAsset();if(part){$("part").value=part;partInfo();}selectTab("edit");},
    async handoff(message){if(!embedded || !hostCapabilities.message)return false;try{await rpc("ui/message",{role:"user",content:[{type:"text",text:message}]});return true;}catch(_){return false;}}
  };
  showGallery();
  start().catch(error => notice(error.message,true));
})();
