/* Asset sourcing, preparation and review controls for the local workshop. */
let nextCatalogOffset = null,
  activeReview = null;
function sourceSettings() {
  const settings = {
    collision: $("sourceCollision").value,
    up_axis: $("sourceAxis").value,
    lod_ratios: $("sourceLods").checked ? [0.5, 0.25] : [],
  };
  if ($("sourceSize").value)
    settings.target_size = Number($("sourceSize").value);
  if ($("sourceBudget").value)
    settings.triangle_budget = Number($("sourceBudget").value);
  return settings;
}
async function importSource(source, preview = false) {
  const name =
    source.id || source.path?.split(/[\\/]/).pop()?.split(".")[0] || "asset";
  let prefix = name
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .slice(0, 35);
  if (!/^[a-z]/.test(prefix)) prefix = "asset_" + prefix;
  const task = await api("import", {
    asset_id: prefix + "_" + Date.now().toString(36),
    source,
    settings: sourceSettings(),
    preview_only: preview,
  });
  $("tasks").parentElement.open = true;
  notice(
    preview
      ? "正在整理，完成后可查看处理前后的模型，再选择导入。"
      : "正在整理模型、材质与 LOD，完成后自动导入引擎。",
  );
  await refresh();
  return task;
}
$("pickSource").onclick = (e) =>
  act(e.target, async () => {
    $("sourcePath").value =
      (await api("pick", { kind: "asset" })).path || $("sourcePath").value;
  });
for (const [button, preview] of [
  ["importSource", false],
  ["previewSource", true],
])
  $(button).onclick = (e) =>
    act(e.target, () =>
      importSource({ provider: "local", path: $("sourcePath").value }, preview),
    );
async function searchCatalog(offset = 0) {
  const result = await api("search", {
    query: $("assetQuery").value,
    offset,
    limit: 6,
  });
  $("catalogStatus").textContent =
    `Powered by Poly Haven · 共 ${result.total} 项 · CC0` +
    (result.catalog_cached ? " · 离线缓存" : "");
  $("assetResults").replaceChildren();
  for (const asset of result.assets) {
    const card = document.createElement("div"),
      title = document.createElement("h3");
    title.textContent = asset.name;
    card.append(title);
    if (
      asset.thumbnail_url &&
      new URL(asset.thumbnail_url).hostname === "cdn.polyhaven.com"
    ) {
      const img = document.createElement("img");
      img.alt = asset.name + " · 素材库预览";
      img.src = asset.thumbnail_url;
      img.loading = "lazy";
      card.append(img);
    }
    const credit = document.createElement("p");
    credit.className = "muted";
    credit.textContent = asset.authors.join("、") + " · CC0";
    card.append(credit);
    const link = document.createElement("a");
    link.href = asset.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "查看原素材";
    card.append(link);
    for (const [label, preview] of [
      ["整理并导入", false],
      ["先预览", true],
    ]) {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = () =>
        act(b, () =>
          importSource({ provider: "polyhaven", id: asset.id }, preview),
        );
      card.append(b);
    }
    $("assetResults").append(card);
  }
  nextCatalogOffset = result.next_offset;
  $("moreAssets").classList.toggle("hidden", nextCatalogOffset == null);
}
$("searchAssets").onclick = (e) => act(e.target, () => searchCatalog());
$("assetQuery").onkeydown = (e) => {
  if (e.key === "Enter") $("searchAssets").click();
};
$("moreAssets").onclick = (e) =>
  act(e.target, () => searchCatalog(nextCatalogOffset));
function kitDescription() {
  $("kitDescription").textContent =
    library?.kits?.[$("styleKit").value]?.description || "";
}
$("styleKit").onchange = kitDescription;
$("createKit").onclick = (e) =>
  act(e.target, async () => {
    const result = await api("kit", {
      kit: $("styleKit").value,
      prefix: "kit_" + Date.now().toString(36),
    });
    notice(
      result.status === "partial"
        ? "部分道具已提交：" + result.error
        : "成套道具开始制作，完成后会分开放入场景，方便选择和布置。",
    );
    await refresh();
  });
$("loadSelection").onclick = (e) =>
  act(e.target, async () => {
    const task = await api("action", { operation: "inspect" });
    const result = await wait(task.request_id);
    const ids = [
      ...new Set(
        (result.selected || []).map((x) => x.asset_id).filter(Boolean),
      ),
    ];
    if (ids.length !== 1) throw Error("请在引擎里选中一个受管理的道具");
    await refresh();
    $("editAsset").value = ids[0];
    await loadAsset();
    notice("已载入 " + ids[0] + "。部件修改会更新这款资产的所有实例。");
  });
$("prepareCurrent").onclick = (e) =>
  act(e.target, async () => {
    if (!$("editAsset").value) throw Error("先选择道具");
    await api("prepare", {
      asset_id: $("editAsset").value,
      settings: sourceSettings(),
    });
    notice("正在重新整理，成功后更新同一资产。");
  });
async function preparedViews(task) {
  $("sourceViews").replaceChildren();
  const grid = document.createElement("div");
  grid.className = "grid";
  $("sourceViews").append(grid);
  for (const [view, label] of [
    ["before", "原始模型（尺寸对齐）"],
    ["studio", "整理后的模型"],
  ]) {
    if (!task.previews?.includes(view + ".png")) continue;
    const card = document.createElement("div"),
      p = document.createElement("p"),
      img = document.createElement("img");
    p.textContent = label;
    img.alt = label + " · Blender 工作室";
    img.src = await studioImage(task.asset_id, task.request_id, view);
    card.append(p, img);
    grid.append(card);
  }
  $("sourceViews").scrollIntoView({ behavior: "smooth", block: "center" });
}
async function nativeImage(id) {
  const key = "engine/" + id;
  if (!previewCache.has(key)) {
    const r = await fetch("/api/preview/" + id, {
      headers: { "X-PTS-Token": token },
    });
    if (!r.ok) throw Error("引擎图片尚未就绪");
    previewCache.set(key, URL.createObjectURL(await r.blob()));
  }
  return previewCache.get(key);
}
async function refreshReviews(s) {
  const list = s.reviews || [],
    area = $("reviewGallery"),
    signature = JSON.stringify(list);
  if (area.dataset.signature === signature) return;
  area.replaceChildren();
  for (const review of list) {
    const title = document.createElement("h4");
    title.textContent = review.asset_id + " · " + review.engine;
    const grid = document.createElement("div");
    grid.className = "grid";
    area.append(title, grid);
    for (const stage of ["before", "after"]) {
      const capture = review.captures[stage],
        card = document.createElement("div"),
        p = document.createElement("p");
      p.textContent =
        (stage === "before" ? "修改前" : "修改后") +
        " · " +
        (capture?.status === "completed"
          ? "已记录"
          : capture?.error || "等待拍摄");
      card.append(p);
      grid.append(card);
      if (capture?.status === "completed") {
        const img = document.createElement("img");
        img.alt = review.engine + " " + p.textContent;
        img.src = await nativeImage(review[stage]);
        card.append(img);
      }
    }
    if (review.captures.before?.status === "completed" && !review.after) {
      const resume = document.createElement("button");
      resume.textContent = "拍摄这组的修改后";
      resume.onclick = () =>
        act(resume, async () => {
          const task = await api("review", {
            asset_id: review.asset_id,
            review_id: review.review_id,
            view: review.view,
            stage: "after",
          });
          await wait(task.request_id);
          await refresh();
        });
      area.append(resume);
    }
  }
  area.dataset.signature = signature;
}
$("reviewBefore").onclick = (e) =>
  act(e.target, async () => {
    if (!$("editAsset").value) throw Error("先选择道具");
    activeReview = {
      asset_id: $("editAsset").value,
      view: $("reviewView").value,
    };
    const task = await api("review", { ...activeReview, stage: "before" });
    activeReview.review_id = task.review_id;
    await wait(task.request_id);
    $("reviewAfter").disabled = false;
    notice("修改前已记录。完成修改后，点击拍摄修改后。");
    await refresh();
  });
$("reviewAfter").onclick = (e) =>
  act(e.target, async () => {
    if (!activeReview) throw Error("先记录修改前");
    const task = await api("review", { ...activeReview, stage: "after" });
    await wait(task.request_id);
    notice("同一相机视角的引擎对比已生成。");
    await refresh();
  });
