"""Build editable game item/UI assets with engine-only runtime dependencies."""

import unreal

base = "/PromptToScene/Templates/"
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([base], True)
builder = unreal.PTSTemplateBuilder
jobs = [
    ("BP_PTSGameItem", builder.build_item_template, ()),
    ("BP_PTSItemPickup", builder.build_item_pickup_template, ()),
]
for kind in ("inventory", "hud", "pause"):
    jobs.extend(
        [
            ("WBP_PTS_" + kind, builder.build_game_ui_template, (kind,)),
            ("BP_PTSUIHost_" + kind, builder.build_ui_host_template, (kind,)),
        ]
    )
for name, build, args in jobs:
    path = base + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        assert unreal.EditorAssetLibrary.delete_asset(path)
        unreal.SystemLibrary.collect_garbage()
    asset = build(path, *args)
    assert unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
    unreal.log("PTS GAME TEMPLATE " + name)
unreal.log("PTS GAME UI BUILT: editable engine-only item and UI templates")
