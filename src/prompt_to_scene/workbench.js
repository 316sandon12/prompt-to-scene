/* Shared UI: loopback API in the local app, MCP Apps JSON-RPC when embedded. */
(() => {
  const $ = id => document.getElementById(id);
  const embedded = window.parent !== window;
  const token = location.hash.slice(1);
  let seq = 0, snapshot = {}, currentAsset = null, activeReview = null, refreshing = false;
  const pending = new Map();
  function notice(message, error = false) { $("notice").textContent = message; $("notice").classList.toggle("error", error); }
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
  function output(result) {
    $("result").textContent = JSON.stringify(result, (key, value) => key === "url" && String(value).startsWith("data:") ? "[图像已显示]" : value, 2);
  }
  async function action(button, fn) {
    button.disabled = true;
    try { const result = await fn(); if (result) output(result); await refresh(); }
    catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
  }
  function bind(id, fn) { $(id).onclick = event => action(event.currentTarget, fn); }
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
    for (let i = 0; i < 45; i++) {
      if (["completed", "imported"].includes(task.status)) return task;
      if (["error", "cancelled", "unknown", "superseded"].includes(task.status)) throw Error(task.error || humanStatus(task.status));
      await new Promise(resolve => setTimeout(resolve, 800));
      task = await call("task", {request_id:task.request_id});
    }
    notice("编辑器仍在等待。打开项目、退出播放模式后可重新读取结果。");
    return task;
  }
  async function showImage(values, caption, append = false) {
    const data = await call("image", values);
    if (!append) $("previews").replaceChildren();
    const figure = document.createElement("figure"), img = document.createElement("img");
    img.src = data.url; img.alt = caption; figure.append(img, textNode("figcaption", caption)); $("previews").append(figure);
  }
  async function showReview(task) {
    const record = task.review || await call("review", {review_id:task.review_id});
    activeReview = task.request_id; $("previews").replaceChildren();
    for (const stage of ["before", "after"]) {
      const capture = record.captures?.[stage];
      if (capture?.status === "completed") await showImage({kind:"engine",request_id:capture.request_id}, stage === "before" ? "修改前 · 引擎画面" : "修改后 · 同一机位", true);
    }
    if (snapshot.art_brief?.image) await showImage({kind:"reference"}, "保存的美术参考", true);
    output(task); notice("已显示真实引擎对照。检查外观后，可继续具体的部件修复。");
  }
  async function loadAsset() {
    const name = $("asset").value;
    if (!name) { currentAsset = null; $("part").replaceChildren(option("", "先选择资产")); return; }
    currentAsset = await call("inspect_asset", {asset_id:name});
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
    snapshot = state;
    $("version").textContent = "v" + state.version;
    $("connection").textContent = state.target ? `${state.target.engine || ""} · ${state.active}` : (state.connection_message || "尚未连接项目，请先打开连接与设置。");
    const selected = $("asset").value, assets = state.assets || [];
    $("asset").replaceChildren(option("", "选择已导入的资产"), ...assets.map(asset => option(asset.asset_id, asset.asset_id)));
    if (assets.some(a => a.asset_id === selected)) $("asset").value = selected;
    const layout = $("layouts").value;
    $("layouts").replaceChildren(option("", "选择已保存布局"), ...(state.layouts || []).map(item => option(item.name, item.name)));
    if ((state.layouts || []).some(item => item.name === layout)) $("layouts").value = layout;
    if (!$("briefNotes").matches(":focus") && !$("briefNotes").dataset.dirty) $("briefNotes").value = state.art_brief?.notes || "";
    for (const node of $("provider").options) { const provider = (state.providers || []).find(p => p.provider === node.value); node.textContent = (node.value === "meshy" ? "Meshy" : "自托管服务") + (provider?.configured ? " · 已配置" : " · 未配置"); }
    const signature = JSON.stringify((state.tasks || []).map(t => [t.request_id,t.status,t.stage,t.updated_utc]));
    if ($("tasks").dataset.signature === signature) return;
    $("tasks").dataset.signature = signature; $("tasks").replaceChildren();
    for (const task of state.tasks || []) {
      const card = document.createElement("article"); card.className = "card";
      card.append(textNode("small", humanStatus(task.status)), textNode("h3", task.asset_id || task.kind || "任务"), textNode("p", task.error || task.stage || ""));
      card.append(button("查看详情", () => { output(task); return task; }));
      if (task.kind && ["error","cancelled"].includes(task.status)) card.append(button("恢复", () => call("resume", {request_id:task.request_id})));
      if (["building","queued"].includes(task.status)) card.append(button("取消", () => call("cancel", {request_id:task.request_id})));
      if (task.kind === "quality" && task.status === "completed") card.append(button("查看前后对照", () => showReview(task)));
      if (task.undo_id) card.append(button("撤销布置", () => call("undo", {undo_id:task.undo_id})));
      const candidates = task.candidates || (task.preview_only && task.status === "completed" ? [{asset_task:task,result:task}] : []);
      candidates.forEach((candidate, index) => {
        const model = candidate.asset_task;
        if (!model || candidate.result?.status !== "completed") return;
        card.append(button(`候选 ${index+1} · 查看`, () => showImage({kind:"studio",asset_id:model.asset_id,request_id:model.request_id}, "Blender 工作室预览")));
        card.append(button(`候选 ${index+1} · 导入`, () => call("publish", {asset_id:model.asset_id, request_id:model.request_id})));
      });
      $("tasks").append(card);
    }
    if (!(state.tasks || []).length) $("tasks").append(textNode("p", "还没有任务。从描述、模型或一套场景开始。"));
  }
  async function refresh() { if (refreshing) return; refreshing = true; try { render(await call("state")); } finally { refreshing = false; } }
  async function submitted(actionName, values) { const task = await call(actionName, values); notice("任务已开始，可在下方查看进度。"); return task; }
  for (const tab of document.querySelectorAll("[data-tab]")) tab.onclick = () => { document.querySelectorAll("[data-tab]").forEach(t => t.setAttribute("aria-selected", String(t === tab))); document.querySelectorAll(".pane").forEach(p => {p.hidden = p.id !== tab.dataset.tab;}); };
  $("asset").onchange = () => loadAsset().catch(error => notice(error.message,true)); $("part").onchange = partInfo;
  $("briefNotes").oninput = () => { $("briefNotes").dataset.dirty = "1"; };
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
  bind("createLocal", () => submitted("create", {kind:$("recipeKind").value, asset_id:id($("generationName").value, $("recipeKind").value)}));
  bind("importLocal", () => submitted("import", {asset_id:id($("generationName").value,"model"), source:{provider:"local",path:$("sourcePath").value}}));
  bind("generateButton", () => submitted("generate", {asset_id:id($("generationName").value,"model"),prompt:$("prompt").value,provider:$("provider").value,image_paths:$("generationImages").value.split(/\n/).map(x=>x.trim()).filter(Boolean),candidate_count:Number($("candidateCount").value),allow_paid:$("paid").checked,preview_only:true}));
  bind("askAI", async () => { const prompt = $("prompt").value.trim(); if (!prompt) throw Error("请先写下希望制作或修改的内容。"); await rpc("ui/message", {role:"user",content:[{type:"text",text:prompt + ($("asset").value ? "\n当前选中的资产："+$("asset").value : "")}]}); notice("已把描述和当前资产发给本次聊天的 AI。"); });
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
  bind("qualityButton", () => submitted("quality", {asset_id:requiredAsset(),auto_fix:$("autoFix").checked,preset:$("usage").value}));
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
  if (!embedded) {
    $("setupLink").href = "/#" + token;
    for (const [control,target,kind] of [["pickSource","sourcePath","asset"],["pickReference","referencePath","reference"],["pickGenerationImage","generationImages","reference"],["pickReplacement","replacementPath","asset"]]) bind(control, async () => { const chosen=await local("pick",{kind}); if(chosen.path) $(target).value=chosen.path; });
    bind("saveProvider", async () => { const key=$("providerKey").value; $("providerKey").value=""; const result=await local("provider",{provider:$("provider").value,endpoint:$("providerEndpoint").value || null,api_key:key || null}); notice("生成服务配置已保存。"); return result; });
  }
  async function start() {
    document.querySelectorAll(".localOnly").forEach(node => {node.hidden=embedded;});
    document.querySelectorAll(".inlineOnly").forEach(node => {node.hidden=!embedded;});
    if (embedded) {
      await rpc("ui/initialize", {appInfo:{name:"Prompt-to-Scene",version:"0.6.0"},appCapabilities:{},protocolVersion:"2026-01-26"});
      notify("ui/notifications/initialized", {});
      new ResizeObserver(() => notify("ui/notifications/size-changed",{height:Math.min(900,document.documentElement.scrollHeight)})).observe(document.body);
    }
    await refresh(); notice(snapshot.target ? "已连接。可以直接制作，或读取编辑器中当前选中的对象。" : "先在本地应用连接 Unity 或 Unreal 项目，再回到创作台。");
    setInterval(() => { if (!document.hidden) refresh().catch(error => notice(error.message,true)); }, 5000);
  }
  start().catch(error => notice(error.message,true));
})();
