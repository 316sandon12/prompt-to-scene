/* Shared scene brief for model and image creation; measurements remain project-scoped. */
(() => {
  const P=window.PTS, {$,workflowAction:run,bind,option,notice,waitAction,textNode:node}=P;
  let project=null, revision=null, dirty=false, current={}, edits=0;
  const fields={sceneUse:"usage",sceneAvoid:"avoid",sceneTarget:"target_id",sceneCamera:"camera_id",sceneFitMode:"fit"};
  const parse=id=>{const value=$(id).value.trim();return value?value.split(/[,，\s]+/).map(Number):null;};
  const ticket=()=>P.state().active;
  const same=p=>p===P.state().active;
  function draw(row={},force=false){
    if(dirty&&!force)return;
    current=row;revision=row.revision||null;dirty=false;
    const saved=row.settings||{},snapshot=row.snapshot||{},objects=new Map();
    for(const o of [...(snapshot.context||[]),...(snapshot.selected_context||[])])objects.set(o.id,o);
    $("sceneTarget").replaceChildren(option("","不指定对象"),...[...objects.values()].map(o=>option(o.id,o.name)));
    $("sceneCamera").replaceChildren(option("","不指定相机"),...(snapshot.cameras||[]).map(c=>option(c.id,c.name)));
    for(const [id,key] of Object.entries(fields))$(id).value=saved[key]||(key==="fit"?"reference":"");
    $("sceneEnabled").checked=saved.enabled!==false;
    $("sceneSize").value=saved.size_m?.join(", ")||"";
    $("sceneDisplay").value=saved.display_size_px?.join(", ")||"";
    $("sceneMargin").value=Math.round((saved.image_margin??.08)*100);
    $("sceneReference").value=row.reference?.source||"";
    $("sceneUnitHint").textContent=snapshot.engine==="unreal"?"Unreal：X / Y / Z（Z 为高度），全部使用米。":"Unity：X / Y / Z（Y 为高度），全部使用米。";
    const target=objects.get(saved.target_id),size=saved.size_m||(saved.fit==="fit"&&target?target.bounds_max.map((v,i)=>v-target.bounds_min[i]):null);
    const camera=(snapshot.cameras||[]).find(c=>c.id===saved.camera_id);
    const details=[];
    if(snapshot.scene)details.push(snapshot.scene);
    if(target)details.push("目标："+target.name);
    if(size)details.push("最大尺寸："+size.map(v=>Number(v.toFixed(3))).join(" × ")+" 米");
    details.push(camera?"相机："+camera.name:"未指定相机，不能判断构图");
    if(snapshot.captured_utc)details.push("读取于 "+new Date(snapshot.captured_utc).toLocaleString());
    $("sceneContextStatus").textContent=!row.revision?"先选中引擎里的目标或占位物，再读取场景。也可直接填写尺寸与用途。":saved.enabled===false?"已暂停沿用场景设定。":details.join(" · ");
    $("sceneBriefBadge").textContent=!row.revision?"未设置":saved.enabled===false?"已暂停":"已沿用";
    $("sceneFitResults").replaceChildren();
  }
  $("sceneBriefPanel").addEventListener("input",()=>{dirty=true;++edits;$("sceneBriefBadge").textContent="待保存";});
  async function save(){
    const origin=ticket(),settings=Object.fromEntries(Object.entries(fields).map(([id,key])=>[key,$(id).value]));
    Object.assign(settings,{enabled:$("sceneEnabled").checked,size_m:parse("sceneSize"),display_size_px:parse("sceneDisplay"),image_margin:Number($("sceneMargin").value)/100});
    const reference=$("sceneReference").value.trim(),values={settings};
    if(reference!==(current.reference?.source||""))values.reference_path=reference;
    const version=edits,row=await run("save_scene_context",values);
    if(!same(origin))throw Error("项目已切换，请在当前项目里重新准备创作。");
    if(version===edits){draw(row,true);notice("场景设定已保存，后续模型与图片会沿用。");}
    else{current=row;revision=row.revision;throw Error("保存过程中设定发生了变化，请再次准备创作以沿用最新内容。");}
    return row;
  }
  P.ensureSceneContext=async()=>{if(dirty)await save();};
  P.captureSceneReference=async()=>{
    const origin=ticket(),version=edits;
    const state=await waitAction(await run("reference_scene",{camera_id:$("sceneCamera").value}));
    if(!same(origin)||state.status!=="completed")return state;
    if(version!==edits)throw Error("读取过程中场景设定有变化，请重新读取。");
    const settings={enabled:$("sceneEnabled").checked,usage:$("sceneUse").value,avoid:$("sceneAvoid").value,
      fit:$("sceneFitMode").value,size_m:parse("sceneSize"),display_size_px:parse("sceneDisplay"),image_margin:Number($("sceneMargin").value)/100};
    if($("sceneCamera").value)settings.camera_id=$("sceneCamera").value;
    if(settings.fit==="fit"&&!settings.size_m&&(state.selected_context||[]).length!==1)settings.fit="reference";
    const row=await run("save_scene_context",{inspection_id:state.request_id,settings});
    if(same(origin)&&version===edits){draw(row,true);notice("已保存游戏镜头、目标尺寸和材质参考，可以开始描述作品。");}
    return row;
  };
  bind("referenceScene",async()=>{const t=P.canvasTicket(),row=await P.captureSceneReference();if(P.canvasCurrent(t)&&row?.reference)await P.showImage({kind:"scene_reference"},"制作参考 · 游戏镜头截图");return row;});
  P.sceneHandoff=()=>current.settings?.enabled===false||!current.revision?"":`\n沿用当前场景制作依据（版本 ${current.revision}）：用 context 读取 scene_context。模型先 design_asset 保存本次场景约束再建模；严格核对引擎 XYZ 米制尺寸和相机，保留接触面与交互空间。有场景参考时调用 match_game_style(use_scene=true)，实际查看返回图像后保存可信的风格分析；场景参考不能直接当作图生 3D 的主体。图片由 plan_image 继承场景参考与显示要求。导入模型后 capture_scene_context 并 check_scene_fit；图片检查导入报告的 scene_fit 与实际预览。场景已变化时刷新依据，不凭文件名推断风格。需要试放时使用 preview_scene_model；图片使用 preview_scene_image，然后查看 scene_preview_images 的真实图像再 scene_preview_action 采用或撤销。读取当前资产的 asset_requirements 与区域 scene_profile；只修改具体问题，保留尺寸下限、挂点及已锁定特征。采用成功后 remember_scene_example 保存到当前区域。`;
  bind("saveSceneContext",save);
  bind("captureSceneContext",async()=>{
    const origin=ticket();
    const state=await waitAction(await run("capture_scene_context",{}));
    if(!same(origin)||state.status!=="completed")return state;
    // Preserve unsaved text constraints, but let the new capture resolve its own selection.
    const settings={enabled:$("sceneEnabled").checked,usage:$("sceneUse").value,avoid:$("sceneAvoid").value,
      fit:$("sceneFitMode").value,size_m:parse("sceneSize"),display_size_px:parse("sceneDisplay"),image_margin:Number($("sceneMargin").value)/100};
    if(settings.fit==="fit"&&!settings.size_m&&(state.selected_context||[]).length!==1)settings.fit="reference";
    const reference=$("sceneReference").value.trim();
    const version=edits,row=await run("save_scene_context",{inspection_id:state.request_id,settings,...(reference!==(current.reference?.source||"")?{reference_path:reference}:{})});
    if(same(origin)&&version===edits){draw(row,true);notice("已读取场景。选择「尺寸上限」可让模型适配占位物大小。");}
    return row;
  });
  bind("checkSceneFit",async()=>{
    const origin=ticket(),canvas=P.canvasTicket(),context=P.context(),asset=context?.model||$("asset").value;
    if(!asset)throw Error("先从作品展廊打开已导入的模型。");
    const state=await waitAction(await run("capture_scene_context",{}));
    if(!same(origin)||!P.canvasCurrent(canvas)||state.status!=="completed")return state;
    const report=await run("check_scene_fit",{asset_id:asset,inspection_id:state.request_id});
    if(!same(origin)||!P.canvasCurrent(canvas))return report;
    const items=report.stale.map(s=>node("p","依据已变化："+s));
    for(const row of report.instances){
      let text="实际尺寸 "+row.size_m.map(v=>Number(v.toFixed(3))).join(" × ")+" 米。";
      text+=row.oversized_axes.length?` ${row.oversized_axes.join(" / ")} 方向超出范围；可考虑等比缩放至 ${(row.uniform_scale_to_fit*100).toFixed(1)}%。`:report.max_size_m?" 尺寸在范围内。":" 未设置尺寸上限。";
      if(row.framing?.outside_frame)text+=" 包围盒超出相机画面。";
      if(row.outside_target_axes?.length)text+=` ${row.outside_target_axes.join(" / ")} 方向超出目标位置范围。`;
      if(row.framing?.status==="near_plane")text+=" 模型位于相机背后或穿过近裁剪面。";
      if(!row.framing)text+=" 暂无可用的构图估算。";
      items.push(node("p",text));
    }
    items.push(node("p","尺寸和构图估算不代表外观、遮挡或碰撞检查通过，请对照真实游戏画面。"));
    const fix=P.button("调整尺寸并试放",()=>P.previewInScene(true));items.push(fix);
    $("sceneFitResults").replaceChildren(...items);return report;
  });
  window.addEventListener("pts:state",event=>{
    const state=event.detail||P.state(),row=state.scene_context||{};
    if(project!==state.active){project=state.active;dirty=false;draw(row,true);}
    else if(revision!==(row.revision||null))draw(row);
  });
})();
