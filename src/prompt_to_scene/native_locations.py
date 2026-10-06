"""Stable managed asset locations: adopting conventions never silently moves old assets."""

from . import core, organization, project_profiles, registry


def layout(project, name):
    target = registry.resolve(project)
    core.asset_id(name)
    root = core.state_root(target.root)
    path = root / "locations" / (name + ".json")
    saved = core.read_optional_json(path)
    if saved:
        return saved
    legacy = core.read_optional_json(root / "receipts" / (name + ".json"))
    configured = (target.root / project_profiles.FILE).is_file() and not legacy
    if configured:
        config = project_profiles.read(project)["organization"]
        rules = organization.rules_for(config)
        folder = config["destination"] + "/PromptToScene/" + name
        label = organization.clean_name(name)
        result = dict(
            folder=folder,
            model=rules["model"][0] + "/" + rules["model"][1] + label,
            prefab=rules["prefab"][0] + "/" + rules["prefab"][1] + label,
            blueprint=rules["blueprint"][0] + "/" + rules["blueprint"][1] + label,
            materials=rules["material"][0] + "/",
            textures=rules["texture"][0] + "/",
            material_prefix=rules["material"][1],
            texture_prefix=rules["texture"][1],
        )
    else:
        result = dict(
            folder=("Assets" if target.engine == "unity" else "/Game") + "/PromptToScene/" + name,
            model="model" if target.engine == "unity" else "SM_" + name,
            prefab=name,
            blueprint="BP_" + name,
            materials="",
            textures="",
            material_prefix="mat_" if target.engine == "unity" else "M_",
            texture_prefix="tex_" if target.engine == "unity" else "T_",
        )
    core.atomic_json(path, result)
    return result
