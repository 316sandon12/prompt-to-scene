"""Selection-scoped adapter discovery and editable Blueprint starters."""

import json
import re

import unreal

from . import actions, gameplay
from .game_creations import TEMPLATES, generated, mark


def execute(request, command, root):
    spec = json.loads(command.get("content_json", "{}"))
    mode = command.get("mode")
    interface = generated(TEMPLATES + "BPI_PTSProjectAdapter")
    if mode == "inspect":
        providers = []
        for actor in actions.actors().get_selected_level_actors():
            providers.append(
                dict(
                    target=actor.get_path_name(),
                    name=actor.get_actor_label(),
                    type=actor.get_class().get_path_name(),
                    compatible=unreal.SystemLibrary.does_implement_interface(actor, interface),
                    required_functions=[
                        "ReadQuantity(ItemId) → Quantity",
                        "ReadHealth() → Current, Maximum",
                        "CommitGameplay(Costs, Rewards, Heal) → Success",
                    ],
                )
            )
        return gameplay.result(
            dict(flow_id=spec["flow_id"], providers=providers),
            "Selected Blueprint systems inspected",
        )
    if mode == "starter":
        name = spec.get("name", "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,63}", name):
            raise ValueError("Invalid adapter name")
        path = "/Game/PromptToScene/Adapters/BP_" + name
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            raise ValueError("Adapter already exists; edit the existing Blueprint")
        bp = unreal.EditorAssetLibrary.duplicate_asset(
            "/PromptToScene/Examples/BP_PTSProjectAdapterExample", path
        )
        if not bp:
            raise ValueError("Reinstall the plugin's adapter example")
        unreal.get_default_object(generated(path)).set_editor_property("AllowTransactions", False)
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        mark(bp, "adapter:" + name)
        return gameplay.result(
            dict(
                path=path,
                required_functions=["ReadQuantity", "ReadHealth", "CommitGameplay"],
                enabled=False,
            ),
            "Editable Blueprint adapter created; connect the actual project API before binding",
        )
    if mode != "bind":
        raise ValueError(
            "UE adapters use native Blueprint interfaces; complete the mapping before binding"
        )
    provider = spec["provider"]
    actor = next(
        (
            a
            for a in actions.actors().get_all_level_actors()
            if a.get_path_name() == provider["target"]
        ),
        None,
    )
    if (
        not actor
        or actor.get_class().get_path_name() != provider["type"]
        or not unreal.SystemLibrary.does_implement_interface(actor, interface)
    ):
        raise ValueError("Selected Blueprint provider changed; inspect it again")
    return gameplay.execute(
        request,
        dict(
            mode="bind",
            content_json=json.dumps(dict(flow_id=spec["flow_id"], target=provider["target"])),
        ),
        root,
    )
