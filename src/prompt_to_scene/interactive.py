"""Retained Blender source for the three small interactive templates."""

import json


def script(kind, role, dimensions, color):
    config = json.dumps(dict(kind=kind, role=role, dimensions=dimensions, color=color))
    return "CONFIG = " + repr(config) + "\n" + SOURCE


SOURCE = """
import bpy, json, math
c = json.loads(CONFIG)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
collection = bpy.data.collections.new('Export')
bpy.context.scene.collection.children.link(collection)
w, d, h = c['dimensions']
def material(name, color, metal=0, rough=.5):
    m=bpy.data.materials.new(name); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Metallic'].default_value=metal
    p.inputs['Roughness'].default_value=rough
    return m
wood=material('Body',c['color'])
metal=material('Hardware',[.09,.11,.14],.8,.28)
# Retained, deterministic wood grain; the exporter bakes portable PBR maps.
nodes,links=wood.node_tree.nodes,wood.node_tree.links
p=nodes.get('Principled BSDF')
coord=nodes.new('ShaderNodeTexCoord')
wave=nodes.new('ShaderNodeTexWave'); wave.bands_direction='X'
wave.inputs['Scale'].default_value=5; wave.inputs['Distortion'].default_value=2
links.new(coord.outputs['Generated'],wave.inputs['Vector'])
ramp=nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].color=(*(v*.85 for v in c['color']),1)
ramp.color_ramp.elements[1].color=(*(min(1,v*1.12+.01) for v in c['color']),1)
links.new(wave.outputs['Color'],ramp.inputs['Fac'])
links.new(ramp.outputs['Color'],p.inputs['Base Color'])
bump=nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=.09
bump.inputs['Distance'].default_value=.0015
links.new(wave.outputs['Color'],bump.inputs['Height'])
links.new(bump.outputs['Normal'],p.inputs['Normal'])
bpy.context.scene['pts_bake_needed']=True
bpy.context.scene['pts_texture_size']=512
def box(name, center, size, mat):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    o=bpy.context.object; o.name=name; o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    for col in list(o.users_collection): col.objects.unlink(o)
    collection.objects.link(o); o.data.materials.append(mat); o['pts_part']=name
    bevel=o.modifiers.new('Soft edges','BEVEL'); bevel.width=min(size)*.10; bevel.segments=3
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return o
if c['kind']=='door':
    if c['role']=='base':
        t=max(.06,w*.075)
        for name,x in [('FrameLeft',-w/2-t/2),('FrameRight',w/2+t/2)]:
            box(name,(x,0,h/2),(t,d*1.6,h),wood)
        box('Lintel',(0,0,h+t/2),(w+2*t,d*1.6,t),wood)
    else:
        box('Leaf',(0,0,h/2),(w-.025,d,h-.03),wood)
        for z in (.25*h,.75*h): box('Rail',(0,-d*.56,z),(w*.83,d*.25,h*.055),metal)
        box('Handle',(w*.32,-d*.9,h*.46),(w*.13,d*.7,h*.035),metal)
elif c['kind']=='chest':
    if c['role']=='base':
        t=min(w,d,h)*.12
        box('Bottom',(0,0,t/2),(w,d,t),wood)
        for x in (-w/2+t/2,w/2-t/2): box('Side',(x,0,h*.4),(t,d,h*.8),wood)
        for y in (-d/2+t/2,d/2-t/2): box('Side',(0,y,h*.4),(w-2*t,t,h*.8),wood)
        for x in (-w*.32,w*.32): box('Band',(x,-d*.51,h*.4),(w*.065,.025,h*.8),metal)
    else:
        box('Lid',(0,0,h*.10),(w,d,h*.20),wood)
        for x in (-w*.32,w*.32): box('Band',(x,0,h*.205),(w*.065,d,.025),metal)
        box('Latch',(0,-d*.52,h*.035),(w*.12,.035,h*.1),metal)
else:
    o=box('Pickup',(0,0,h/2),(w*.72,d*.72,h*.72),metal)
    o.rotation_euler[2]=math.pi/4
    box('Core',(0,0,h/2),(w*.4,d*.4,h),wood)
"""
