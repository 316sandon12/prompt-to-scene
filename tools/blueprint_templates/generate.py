"""Run in UE with the maintainer-only builder plugin enabled; then copy the uasset."""

import unreal

path = "/PromptToScene/Templates/BP_PTSInteraction"
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(
    ["/PromptToScene/Templates"], force_rescan=True
)
if unreal.EditorAssetLibrary.does_asset_exist(path):
    assert unreal.EditorAssetLibrary.delete_asset(path)
    unreal.SystemLibrary.collect_garbage()

blueprint = unreal.PTSTemplateBuilder.build_interactive_template(path)
assert unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
unreal.log("PTS TEMPLATE BUILT: engine-only Blueprint, no builder runtime dependency")
