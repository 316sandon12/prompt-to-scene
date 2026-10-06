"""Build only the native editor panel, keeping the interaction template untouched."""

import unreal

path = "/PromptToScene/Templates/EUW_PTSWorkshop"
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(
    ["/PromptToScene/Templates"], force_rescan=True
)
if unreal.EditorAssetLibrary.does_asset_exist(path):
    assert unreal.EditorAssetLibrary.delete_asset(path)
    unreal.SystemLibrary.collect_garbage()
blueprint = unreal.PTSTemplateBuilder.build_workshop_template(path)
assert unreal.EditorAssetLibrary.save_loaded_asset(blueprint, only_if_is_dirty=False)
unreal.log("PTS WORKSHOP BUILT: native Editor Utility Widget, no builder dependency")
