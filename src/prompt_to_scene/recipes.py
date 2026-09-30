"""Small deterministic prop recipes; values remain editable across AI clients."""

import json
import math

DEFAULTS = {
    "crate": {"width": 1.0, "depth": 1.0, "height": 1.0, "planks": 5},
    "table": {"width": 1.5, "depth": 0.8, "height": 0.75, "thickness": 0.08},
    "chair": {"width": 0.5, "depth": 0.5, "height": 0.9, "seat_height": 0.45},
    "sign": {"width": 0.8, "depth": 0.08, "height": 1.5, "board_height": 0.4},
}


def prepare(kind: str, parameters: dict | None = None) -> tuple[str, dict]:
    if kind not in DEFAULTS:
        raise ValueError("Recipe must be crate, table, chair or sign")
    defaults = {
        **DEFAULTS[kind],
        "color": [0.24, 0.085, 0.025],
        "metal_color": [0.08, 0.09, 0.11],
        "roughness": 0.72,
    }
    parameters = parameters or {}
    if parameters.keys() - defaults.keys():
        raise ValueError(
            "Unknown recipe parameters: " + ", ".join(parameters.keys() - defaults.keys())
        )
    data = {**defaults, **parameters}
    for key, value in data.items():
        if key.endswith("color"):
            if (
                not isinstance(value, list)
                or len(value) != 3
                or any(
                    not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1
                    for v in value
                )
            ):
                raise ValueError(key + " must contain three linear RGB values between 0 and 1")
        elif key == "roughness":
            if (
                not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("roughness must be between 0 and 1")
        elif (
            not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 100
        ):
            raise ValueError(key + " must be positive and at most 100")
    if kind == "crate" and (int(data["planks"]) != data["planks"] or not 2 <= data["planks"] <= 32):
        raise ValueError("planks must be an integer between 2 and 32")
    if kind == "table" and data["thickness"] >= data["height"]:
        raise ValueError("thickness must be less than height")
    if kind == "chair" and data["seat_height"] >= data["height"]:
        raise ValueError("seat_height must be less than height")
    if kind == "sign" and data["board_height"] >= data["height"]:
        raise ValueError("board_height must be less than height")
    recipe = {"kind": kind, "parameters": data}
    script = (
        "import json\np = json.loads("
        + repr(json.dumps(data))
        + ")\nkind = "
        + repr(kind)
        + "\n"
        + BODY
    )
    return script, recipe


BODY = """
import bpy
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
collection = bpy.data.collections.new("Export")
bpy.context.scene.collection.children.link(collection)
def material(name, color, metal, rough):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Metallic"].default_value = metal
    node.inputs["Roughness"].default_value = rough
    return mat
wood = material("Wood", p["color"], 0, p["roughness"])
metal = material("Metal", p["metal_color"], .85, .3)
def box(name, center, size, mat=wood):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    for owner in list(obj.users_collection): owner.objects.unlink(obj)
    collection.objects.link(obj)
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    mod = obj.modifiers.new("Soft edges", "BEVEL")
    mod.width = min(size) * .08
    mod.segments = 2
    bpy.ops.object.modifier_apply(modifier=mod.name)
w, d, h = p["width"], p["depth"], p["height"]
if kind == "crate":
    n = int(p["planks"])
    for i in range(n): box("Plank_%02d" % i, (-w/2 + (i+.5)*w/n, 0, h/2), (w/n*.96, d*.96, h*.96))
    for x in (-w*.36, w*.36):
        for y in (-d*.49, d*.49): box("Side_strap", (x,y,h/2), (w*.075,d*.025,h), metal)
        for z in (h*.0125,h*.9875): box("Top_strap", (x,0,z), (w*.075,d*.98,h*.025), metal)
elif kind in ("table", "chair"):
    top = h if kind == "table" else p["seat_height"]
    thick = p.get("thickness", min(w,d)*.12)
    leg = min(w,d)*.12
    box("Top", (0,0,top-thick/2), (w,d,thick))
    for x in (-w/2+leg, w/2-leg):
        for y in (-d/2+leg,d/2-leg): box("Leg", (x,y,(top-thick)/2), (leg,leg,top-thick))
    if kind == "chair":
        for x in (-w/2+leg, w/2-leg): box("Back_post", (x,d/2-leg,(top+h)/2), (leg,leg,h-top))
        box("Backrest", (0,d/2-leg,h-(h-top)*.2), (w,leg,(h-top)*.4))
else:
    board = p["board_height"]
    box("Post", (0,0,(h-board)/2), (min(w*.1,.1),d*1.4,h-board))
    box("Sign_board", (0,0,h-board/2), (w,d,board))
"""
