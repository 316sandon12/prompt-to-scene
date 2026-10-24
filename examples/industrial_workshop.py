# ruff: noqa: F821
# Shared Blender primitives are prepended by art_directions.source.
"""Appended to the shared Blender primitives by art_directions.source. MIT original geometry."""

orbital = globals().get("PTS_DIRECTION") == "orbital_workshop"
panel = material(
    "Ceramic panel" if orbital else "Worn orange panel",
    (0.52, 0.65, 0.72) if orbital else (0.36, 0.12, 0.035),
    0.38 if orbital else 0.72,
    0.25,
)
frame = material("Graphite frame", (0.025, 0.044, 0.06), 0.42, 0.7)
trim = material(
    "Cyan indicator trim" if orbital else "Brass trim",
    (0.04, 0.52, 0.65) if orbital else (0.45, 0.25, 0.06),
    0.3,
    0.55,
)
rubber = material("Rubber seals", (0.018, 0.022, 0.025), 0.8)
white = material("Instruction markings", (0.75, 0.82, 0.79), 0.6)


def plate(part, position, size):
    box(part, position, size, panel, 0.035 if orbital else 0.012)
    if not orbital:
        x, y, z = position
        for dx in (-size[0] * 0.39, size[0] * 0.39):
            for dz in (-size[2] * 0.36, size[2] * 0.36):
                rod(
                    "rivet",
                    (x + dx, y - size[1] / 2 - 0.005, z + dz),
                    (x + dx, y - size[1] / 2 - 0.013, z + dz),
                    0.012,
                    frame,
                )


def cell(location, scale=1, medicine=False):
    x, y, z = location
    lathe(
        "capsule_body",
        [(0, 0.07), (0.02, 0.09), (0.23, 0.09), (0.27, 0.06), (0.31, 0.06)],
        panel if not medicine else trim,
        location,
        segments=24,
    )
    for h in (0.035, 0.24):
        ring("collar", (x, y, z + h), 0.092, 0.012, frame)
    for dx in (-0.027, 0.027):
        rod("contacts", (x + dx, y, z + 0.30), (x + dx, y, z + 0.34), 0.012, trim)
    box("status_label", (x, y - 0.092, z + 0.13), (0.08, 0.008, 0.09), white, 0.004)
    if medicine:
        box("medical_mark", (x, y - 0.10, z + 0.13), (0.018, 0.008, 0.065), frame, 0.002)
        box("medical_mark", (x, y - 0.10, z + 0.13), (0.055, 0.008, 0.018), frame, 0.002)


if kind == "cottage":
    for i in range(6):
        box("floor_panels", (-1.9 + i * 0.76, 0, -0.06), (0.75, 3.5, 0.12), frame, 0.012)
    for x in (-1.8, -0.6, 0.6, 1.8):
        plate("wall_module", (x, 1.7, 1.4), (1.15, 0.16, 2.8))
        box("wall_inset", (x, 1.60, 1.55), (0.83, 0.08, 1.1), rubber, 0.05)
        for z in (1.02, 2.08):
            box("indicator_strip", (x, 1.54, z), (0.75, 0.018, 0.026), trim, 0.006)
    for x in (-2.25, 2.25):
        rod(
            "braced_support",
            (x, -1.4, 0),
            (x - 0.12 if x > 0 else x + 0.12, -1.4, 2.75),
            0.085,
            frame,
        )
        box("roof_support", (x, 0, 2.75), (0.15, 3.5, 0.15), frame, 0.02)
    if not orbital:
        patch = box("salvage_patch", (-1.8, 1.58, 0.65), (0.55, 0.05, 0.45), trim, 0.01)
        patch.rotation_euler[1] = 0.14
elif kind == "workbench":
    if orbital:
        plate("central_pedestal", (0, 0.10, 0.39), (0.78, 0.52, 0.78))
        box("foot", (0, 0.10, 0.06), (1.15, 0.7, 0.12), frame, 0.04)
    else:
        for x in (-0.68, 0.68):
            for y in (-0.28, 0.28):
                box("steel_legs", (x, y, 0.42), (0.10, 0.1, 0.84), frame, 0.01)
            rod("cross_brace", (x, -0.28, 0.2), (x, 0.28, 0.7), 0.027, trim)
    box("worktop", (0, 0, 0.86), (1.65, 0.85, 0.1), frame, 0.035)
    plate("worktop_surface", (0, 0, 0.92), (1.55, 0.75, 0.025))
    for x in (-0.42, 0.42):
        plate("drawer", (x, -0.28, 0.73), (0.66, 0.22, 0.17))
        box("recessed_handle", (x, -0.40, 0.73), (0.24, 0.018, 0.028), rubber, 0.008)
    display = box("console_screen", (0, 0.27, 1.13), (0.50, 0.04, 0.32), frame, 0.025)
    display.rotation_euler[0] = -0.22
    for z in (1.06, 1.11, 1.16):
        box("readout", (0, 0.237, z), (0.37, 0.008, 0.012), trim, 0.003)
    cell((0.5, 0.10, 0.935))
    box("instrument_case", (-0.48, -0.08, 0.98), (0.32, 0.28, 0.09), panel, 0.025)
elif kind == "shelf":
    for x in (-0.66, 0.66):
        box("frame_uprights", (x, 0, 0.97), (0.10, 0.4, 1.94), frame, 0.02)
    plate("cabinet_back", (0, 0.20, 1.0), (1.25, 0.07, 1.9))
    for z in (0.17, 0.71, 1.25, 1.8):
        box("storage_tray", (0, -0.04, z), (1.42, 0.58, 0.065), frame, 0.02)
        box("tray_strip", (0, -0.34, z + 0.02), (1.30, 0.018, 0.025), trim, 0.004)
    for z in (0.22, 0.76, 1.30):
        for i in range(4):
            cell((-0.46 + i * 0.30, -0.02, z), medicine=i == 2)
elif kind == "lantern":
    box("weighted_base", (0, 0, 0.045), (0.30, 0.24, 0.09), frame, 0.025)
    rod("mast", (0, 0.04, 0.08), (0, 0.04, 0.48), 0.025, trim)
    plate("lamp_housing", (0, 0.01, 0.43), (0.28, 0.15, 0.22))
    box("diffuser", (0, -0.08, 0.43), (0.22, 0.02, 0.15), white, 0.014)
    if not orbital:
        for x in (-0.09, 0, 0.09):
            rod("lamp_cage", (x, -0.1, 0.34), (x, -0.1, 0.52), 0.008, frame)
elif kind == "herb":
    if orbital:
        for x, y in ((-0.095, 0), (0.095, 0), (0, 0.16)):
            cell((x, y, 0))
        box("cell_harness", (0, 0.06, 0.12), (0.36, 0.3, 0.04), frame, 0.016)
    else:
        for i in range(5):
            ring("salvaged_coil", (0, 0, 0.035 + i * 0.045), 0.12, 0.012, trim)
        box("mounting_plate", (0, 0, 0.015), (0.31, 0.25, 0.03), frame, 0.01)
        rod("copper_contact", (-0.15, 0, 0.26), (0.15, 0, 0.26), 0.018, trim)
elif kind == "bottle":
    cell((0, 0, 0))
elif kind == "potion":
    if orbital:
        cell((0, 0, 0), medicine=True)
        rod("injector_tip", (0, 0, 0.34), (0, 0, 0.43), 0.015, frame)
        ring("grip", (0, 0, 0.10), 0.11, 0.012, trim)
    else:
        plate("medical_pack", (0, 0, 0.18), (0.32, 0.17, 0.36))
        for x in (-0.12, 0.12):
            box("webbing", (x, -0.095, 0.18), (0.04, 0.025, 0.34), rubber, 0.005)
        box("medical_mark", (0, -0.10, 0.20), (0.06, 0.015, 0.17), white, 0.004)
        box("medical_mark", (0, -0.10, 0.20), (0.17, 0.015, 0.06), white, 0.004)
else:
    raise ValueError("Unknown kit asset kind")

for obj in list(export.objects):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
