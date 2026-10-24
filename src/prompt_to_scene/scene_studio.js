/* Scene creation controls shared by the local app and inline MCP workbench. */
(() => {
  const P=window.PTS, {$,workflowAction:run,bind,notice,option,textNode:node,waitAction}=P;
  let project=null,asset=null,trial=null,usageDirty=false,usageEdits=0,usageRow=null,profileDirty=false,historyKey="",displaySequence=0;
  const vector=id=>{const s=$(id).value.trim();return s?s.split(/[,，\s]+/).map(Number):null;};
  const ticket=()=>P.canvasTicket();
  const valid=t=>P.canvasCurrent(t);
  function identity(){const c=P.context();return c?.kind==="image"?{kind:"image",id:c.id,revision:c.revision}:c?.model||c?.kind==="model"?{kind:"model",id:c.model||c.id}:$("asset").value?{kind:"model",id:$("asset").value}:null;}
  function history(){const c=identity();return (P.state().scene_previews||[]).filter(r=>r.asset_id===c?.id);}
  function controls(){
    const online=!!P.state().target?.editor_responding&&!P.state().target?.editor?.playing;
    const c=identity(),model=c?.kind==="model",image=c?.kind==="image";
    const failed=t=>t&&["error","cancelled"].includes(t.status);
    const disabled=(id,value)=>{$(id).disabled=value||$(id).getAttribute("aria-busy")==="true";};
    disabled("referenceScene",!online);
    disabled("previewSceneAsset",!c||(model&&!online));
    disabled("fitSceneModel",!model||!online);disabled("padSceneImage",!image);
    disabled("adoptSceneTrial",!trial||trial.discarded||(!!trial.adopt&&!failed(trial.adopt))||!online);
    disabled("discardSceneTrial",!trial||trial.discarded||(!!trial.adopt&&!failed(trial.adopt)));
    disabled("undoSceneTrial",trial?.adopt?.status!=="completed"||(!!trial.undo&&!failed(trial.undo))||!online||(image&&!trial.previous_revision));
    disabled("repairScenePart",!model||!trial||!online);disabled("restoreSceneModel",!model||!trial||!online);
    for(const id of ["rememberSceneAccepted","rememberSceneAvoid"])disabled(id,!trial||trial.discarded);
    $("trialPlacement").disabled=!model;$("trialResize").disabled=!model;$("trialReplace").disabled=!model;
  }
  async function images(row,t,sequence){
    const views=row.kind==="model"?[["before","试放前 · 游戏镜头"],["trial","试放后 · 临时模型"]]:[["scene","实际像素 · 叠到场景参考"],["sizes","32 / 64 / 128 像素"],["ui","九宫格与文字安全区 · 排版预览"]];
    const pictures=[];
    for(const [view,label] of views){
      const value=await P.call("image",{kind:"scene_trial",request_id:row.plan_id,view});
      if(!valid(t)||sequence!==displaySequence)return;
      const figure=document.createElement("figure"),img=document.createElement("img");img.src=value.url;img.alt=label;
      if(row.kind==="image")figure.className="pixel-scene-preview";
      figure.append(img,node("figcaption",label));pictures.push(figure);
    }
    if(!valid(t)||sequence!==displaySequence)return;
    P.beginVisual();P.clearVisual?.();$("regionEditor").hidden=true;$("previews").replaceChildren(...pictures);$("previewEmpty").hidden=true;
    if(row.kind==="image"){
      const tools=node("div","");tools.className="row visual-controls";
      tools.append(P.button("框选修改此版图片",()=>P.openImageEdit(row.asset_id,row.image_revision)));$("previews").append(tools);
    }
    $("previewCaption").textContent=row.kind==="model"?"同一游戏镜头 · 试放不会保存到场景":"图片按像素显示，可横向滚动；这里不模拟引擎字体与材质";
    $("previewMeta").textContent=row.kind==="model"?"采用后可撤销":"图片比例保持不变";
  }
  async function show(row){
    const t=ticket(),sequence=++displaySequence;
    await images(row,t,sequence);if(!valid(t)||sequence!==displaySequence)return;
    trial=row;$("sceneTrialHistory").value=row.plan_id;
    const missing=Object.entries(row.report?.states||{}).filter(([,ok])=>!ok).map(([name])=>name);
    $("sceneTrialStatus").textContent=row.discarded?"已放弃此预览。":row.undo?.status==="completed"?"已撤销采用。":row.undo?.status==="error"?"撤销失败："+row.undo.error:row.undo?"正在撤销。":row.adopt?.status==="completed"?"已采用，可撤销。":row.adopt?.status==="error"?"采用失败："+row.adopt.error:row.adopt?"正在采用。":row.kind==="model"?`临时试放，缩放比例 ${((row.scale_factor??1)*100).toFixed(1)}%。${row.framing?.outside_frame?"部分范围超出镜头。":""}`:`显示尺寸 ${(row.display_size_px||[]).join(" × ")} 像素。${missing.length?"尚缺状态："+missing.join("、"):""}`;
    $("sceneTrialBadge").textContent=row.discarded?"已放弃":row.undo?.status==="completed"?"已撤销":row.adopt?.status==="completed"?"已采用":row.adopt?.status==="error"?"采用失败":row.adopt?"采用中":"待采用";
    if(row.kind==="model"){
      const info=await P.call("inspect_asset",{asset_id:row.asset_id});if(!valid(t)||sequence!==displaySequence)return;
      const names=Object.keys(info.metadata?.report?.parts||{});
      $("sceneRepairPart").replaceChildren(...names.map(n=>option(n,n)));
    }
    controls();return row;
  }
  async function preview(resize=false){
    const t=ticket(),c=identity();if(!c)throw Error("先从作品展廊打开模型或图片。");
    await P.ensureSceneContext();if(!valid(t))return;
    await P.ensureAssetUsage(c.id);if(!valid(t))return;
    let row;
    if(c.kind==="model"){
      const capture=await waitAction(await run("capture_scene_context",{}));if(!valid(t)||capture.status!=="completed")return capture;
      const pending=await run("preview_scene_model",{asset_id:c.id,inspection_id:capture.request_id,placement:$("trialPlacement").value,resize:resize||$("trialResize").checked,replace_target:$("trialReplace").checked});
      const result=await waitAction(pending);if(!valid(t)||result.status!=="completed")return result;
      const saved=await run("scene_previews",{asset_id:c.id});if(!valid(t))return;
      row=saved.previews.find(r=>r.plan_id===pending.plan_id);if(!row)throw Error("预览记录尚未返回，请刷新。");
    }else{
      if(!c.revision)throw Error("先打开一个确定版本的图片。");
      row=await run("preview_scene_image",{asset_id:c.id,revision:c.revision,display_size_px:vector("sceneDisplay"),position:vector("trialImagePosition"),text:$("trialImageText").value});
    }
    if(valid(t)){trial=row;await P.refresh();if(valid(t))return show(row);}
  }
  P.previewInScene=preview;
  bind("previewSceneAsset",()=>preview(false));bind("fitSceneModel",()=>preview(true));
  $("trialReplace").onchange=()=>{if($("trialReplace").checked)$("trialPlacement").value="volume";};
  bind("padSceneImage",async()=>{
    const c=identity(),t=ticket();if(c?.kind!=="image")throw Error("先打开图标或立绘。");
    const repaired=await run("repair_image_padding",{asset_id:c.id,revision:c.revision,margin:Number($("sceneMargin").value)/100});if(!valid(t))return;
    const row=await run("preview_scene_image",{asset_id:c.id,revision:repaired.revision,display_size_px:vector("sceneDisplay"),position:vector("trialImagePosition"),text:$("trialImageText").value});
    if(valid(t)){trial=row;await P.refresh();if(valid(t))return show(row);}
  });
  for(const [id,mode] of [["adoptSceneTrial","adopt"],["discardSceneTrial","discard"],["undoSceneTrial","undo"]])bind(id,async()=>{
    if(!trial)throw Error("先完成一次预览。");const row=trial,t=ticket();
    const result=await run("scene_preview_action",{plan_id:row.plan_id,mode});
    const state=result.request_id?await waitAction(result):result;if(!valid(t))return state;
    if(result.request_id&&state.status!=="completed")return state;
    if(mode==="adopt"){try{await run("remember_scene_example",{plan_id:row.plan_id,notes:$("sceneExampleNotes").value.trim()||"用户在场景预览中采用此版本；后续参考可见的轮廓与配色。",verdict:"accepted"});}catch(e){notice("已采用，但样本尚未保存："+e.message,true);}}
    if(!valid(t))return state;
    await P.refresh();if(valid(t)){const saved=history().find(r=>r.plan_id===row.plan_id);if(saved)await show(saved);notice(mode==="adopt"?"已采用。":mode==="undo"?"已恢复采用前的状态。":"已放弃预览，项目没有变化。");}return state;
  });
  $("sceneTrialHistory").onchange=()=>P.action($("sceneTrialHistory"),async()=>{const row=history().find(r=>r.plan_id===$("sceneTrialHistory").value);if(row)return show(row);});
  for(const [id,verdict] of [["rememberSceneAccepted","accepted"],["rememberSceneAvoid","avoid"]])bind(id,()=>{if(!trial)throw Error("先查看预览。");return run("remember_scene_example",{plan_id:trial.plan_id,notes:$("sceneExampleNotes").value,verdict});});
  bind("repairScenePart",async()=>{
    if(!trial)throw Error("先查看模型预览。");const changes={};
    if($("sceneRepairUseColor").checked)changes.color=$("sceneRepairColor").value.slice(1).match(/../g).map(v=>{const n=parseInt(v,16)/255;return n<=.04045?n/12.92:Math.pow((n+.055)/1.055,2.4);});
    if($("sceneRepairUseRoughness").checked)changes.roughness=Number($("sceneRepairRoughness").value);
    const result=await run("repair_scene_part",{plan_id:trial.plan_id,part:$("sceneRepairPart").value,changes});
    notice("部件修改已提交，完成后重新预览；其他部件继续保留。");return result;
  });
  bind("restoreSceneModel",async()=>{if(!trial||trial.kind!=="model")throw Error("先查看模型预览。");return run("restore_scene_part",{plan_id:trial.plan_id});});
  function fillUsage(row){
    usageRow=row||{};const c=row?.settings||{};
    $("usageAsset").value=asset||"";$("usageKind").value=c.kind||"prop";
    for(const [id,key,fallback] of [["usageMinimum","min_size_m",[0,0,0]],["usageClearance","clearance_m",[0,0,0]],["usageSafeArea","safe_area",[.1,.1,.8,.8]]])$(id).value=(c[key]||fallback).join(", ");
    $("usageLockScale").checked=!!c.lock_scale;$("usageNotes").value=c.notes||"";$("usageMoving").value=c.moving_asset_id||"";
    $("usagePivot").value=c.pivot?.join(", ")||"";$("usageAxis").value=c.axis?.join(", ")||"";$("usageAngle").value=c.angle??90;
    $("usageStates").value=(c.states||["normal"]).join(", ");
    const socket=c.sockets?.[0];$("usageSocket").value=socket?.name||"";$("usageSocketPosition").value=(socket?.position||[0,0,0]).join(", ");$("usageSocketRotation").value=(socket?.rotation||[0,0,0]).join(", ");
    usageDirty=false;
  }
  $("usagePanel").addEventListener("input",()=>{usageDirty=true;++usageEdits;});
  $("usageKind").onchange=()=>{
    const ue=P.state().target?.engine==="unreal",kind=$("usageKind").value;
    if(kind==="door"||kind==="chest"){const axis=kind==="door"?(ue?[0,0,1]:[0,1,0]):(ue?[0,1,0]:[-1,0,0]);$("usageAxis").value=axis.join(", ");}
  };
  async function saveUsage(name){
    const t=ticket(),version=usageEdits,id=name||$("usageAsset").value.trim()||identity()?.id;
    if(!id)throw Error("填写资产 ID，或先从展廊打开作品。");
    const old=usageRow?.settings?.sockets||[],socket=$("usageSocket").value.trim(),sockets=old.slice(1);
    if(socket)sockets.unshift({name:socket,position:vector("usageSocketPosition"),rotation:vector("usageSocketRotation")});
    const row=await run("asset_requirements",{asset_id:id,settings:{kind:$("usageKind").value,min_size_m:vector("usageMinimum"),clearance_m:vector("usageClearance"),lock_scale:$("usageLockScale").checked,notes:$("usageNotes").value,moving_asset_id:$("usageMoving").value.trim(),pivot:vector("usagePivot"),axis:vector("usageAxis"),angle:Number($("usageAngle").value),sockets,safe_area:vector("usageSafeArea"),states:$("usageStates").value.split(/[,，\s]+/).filter(Boolean)}});
    if(!valid(t))throw Error("作品或项目已切换，请在当前作品重新保存。");
    if(version!==usageEdits)throw Error("保存期间用途要求发生变化，请再保存一次。");
    usageRow=row;usageDirty=false;$("usageAsset").value=id;if(!P.context()&&!name)$("creationId").value=id;$("usageStatus").textContent="已保存，将用于这件资产的下一次制作和试放。";return row;
  }
  P.ensureAssetUsage=async id=>{if(usageDirty||(!P.context()&&usageRow?.revision&&usageRow.asset_id!==id))await saveUsage(id);};
  bind("saveAssetUsage",()=>saveUsage());
  bind("applyAssetUsage",async()=>{const row=await saveUsage();return run("apply_asset_requirements",{asset_id:row.asset_id});});
  $("sceneArtPanel").addEventListener("input",()=>{profileDirty=true;});
  const locks={sceneLockSilhouette:"silhouette",sceneLockPalette:"palette",sceneLockProportions:"proportions",sceneLockMaterials:"materials",sceneLockDetail:"detail"};
  function fillProfile(row){$("sceneProfileName").value=row?.name||"";$("sceneProfileNotes").value=row?.notes||"";for(const [id,key] of Object.entries(locks))$(id).value=row?.locks?.[key]||"";profileDirty=false;}
  $("sceneProfileChoice").onchange=()=>fillProfile(P.state().scene_profiles?.profiles.find(r=>r.profile_id===$("sceneProfileChoice").value));
  async function saveProfile(update){
    const values={name:$("sceneProfileName").value,notes:$("sceneProfileNotes").value,locks:Object.fromEntries(Object.entries(locks).map(([id,key])=>[key,$(id).value]).filter(([,v])=>v))};
    if(update){if(!$("sceneProfileChoice").value)throw Error("先选择要更新的区域。");values.profile_id=$("sceneProfileChoice").value;}
    const t=ticket(),result=await run("save_scene_profile",values);
    if(valid(t)){await P.refresh();if(valid(t)){$("sceneProfileChoice").value=result.profile_id;fillProfile(result);notice("已保存区域要求。选择「使用这组要求」后，新作品会沿用。");}}return result;
  }
  bind("saveSceneProfile",()=>saveProfile(false));bind("updateSceneProfile",()=>saveProfile(true));
  bind("activateSceneProfile",async()=>{if(!$("sceneProfileChoice").value)throw Error("先选择区域。");const row=await run("activate_scene_profile",{profile_id:$("sceneProfileChoice").value});notice("已切换美术要求，请重新选择场景位置。旧作品没有变化。");return row;});
  function sync(){
    const s=P.state(),id=identity()?.id||null;
    if(project!==s.active){project=s.active;asset=null;trial=null;++displaySequence;historyKey="";usageDirty=false;profileDirty=false;$("sceneExampleNotes").value="";fillProfile(null);}
    if(asset!==id){asset=id;trial=null;++displaySequence;historyKey="";fillUsage(s.usage_requirements?.find(r=>r.asset_id===id));$("sceneTrialStatus").textContent="";$("sceneTrialBadge").textContent="先预览";}
    else if(!usageDirty&&asset){const row=s.usage_requirements?.find(r=>r.asset_id===asset);if(row?.revision!==usageRow?.revision)fillUsage(row);}
    const rows=history(),key=JSON.stringify(rows.map(r=>[r.plan_id,r.adopt,r.undo,r.discarded]));
    if(key!==historyKey){historyKey=key;$("sceneTrialHistory").replaceChildren(option("","选择一次预览"),...rows.map(r=>option(r.plan_id,new Date(r.created_utc).toLocaleString()+" · "+(r.kind==="model"?"模型":"图片"))));if(trial){trial=rows.find(r=>r.plan_id===trial.plan_id)||trial;$("sceneTrialHistory").value=trial.plan_id;}}
    const choice=$("sceneProfileChoice").value,profiles=s.scene_profiles?.profiles||[];
    $("sceneProfileChoice").replaceChildren(option("","选择区域"),...profiles.map(r=>option(r.profile_id,r.name+(r.profile_id===s.scene_profiles?.active?.profile_id?" · 使用中":""))));
    $("sceneProfileChoice").value=profiles.some(r=>r.profile_id===choice)?choice:s.scene_profiles?.active?.profile_id||"";
    if(!profileDirty)fillProfile(profiles.find(r=>r.profile_id===$("sceneProfileChoice").value));controls();
  }
  for(const event of ["pts:state","pts:tab","pts:gallery"])window.addEventListener(event,sync);
  window.addEventListener("pts:idle",controls);
  document.addEventListener("click",()=>queueMicrotask(controls));
})();
