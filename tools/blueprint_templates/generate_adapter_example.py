"""An editable interface example; replace its storage functions with the game's API."""

import unreal

path = "/PromptToScene/Examples/BP_PTSProjectAdapterExample"
unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/PromptToScene"], True)
if unreal.EditorAssetLibrary.does_asset_exist(path):
    assert unreal.EditorAssetLibrary.delete_asset(path)
    unreal.SystemLibrary.collect_garbage()
asset = unreal.PTSTemplateBuilder.build_project_adapter_example(path)
assert unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
unreal.log("PTS ADAPTER EXAMPLE BUILT")
