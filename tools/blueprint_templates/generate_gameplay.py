"""Rebuild gameplay dependencies before interaction and UI templates (UE 5.7)."""

import os

import unreal

base = "/PromptToScene/Templates/"
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous([base], True)
builder = unreal.PTSTemplateBuilder
for name, build in [
    ("BP_PTSGameRule", builder.build_game_rule_template),
    ("BP_PTSGameSave", builder.build_game_save_template),
    ("BPI_PTSProjectAdapter", builder.build_project_adapter_interface),
    ("BP_PTSGameSession", builder.build_game_session_template),
    ("BP_PTSInteraction", builder.build_interactive_template),
]:
    if os.environ.get("PTS_TEMPLATE_ONLY") not in (None, name):
        continue
    path = base + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        assert unreal.EditorAssetLibrary.delete_asset(path)
        unreal.SystemLibrary.collect_garbage()
    asset = build(path)
    assert unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
    unreal.log("PTS GAMEPLAY TEMPLATE " + name)
unreal.log("PTS GAMEPLAY BUILT")
