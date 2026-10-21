"""Blender preview of the road pilot (runs INSIDE Blender; PREVIEW ONLY, offline render, not the game).

  blender -b --python-exit-code 1 --python blender_preview.py -- <scene.json> <out_dir> <tag> [samples] [scale]

Builds the scene (tools/roadvis/scene.py output), day lighting (Nishita sky + sun), renders every camera in the file
with Cycles (GPU when available) to <out_dir>/<tag>_<camera>.png. Roblox (x, y, z) -> Blender (x, -z, y).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
scene_path, out_dir, tag = argv[0], argv[1], argv[2]
samples = int(argv[3]) if len(argv) > 3 else 64
scale = float(argv[4]) if len(argv) > 4 else 1.0
os.makedirs(out_dir, exist_ok=True)
data = json.load(open(scene_path, encoding='utf-8'))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, rgb, rough=0.85):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (srgb_to_lin(rgb[0]), srgb_to_lin(rgb[1]), srgb_to_lin(rgb[2]), 1.0)
    b.inputs['Roughness'].default_value = rough
    return m


for ob in data['objects']:
    me = bpy.data.meshes.new(ob['name'])
    verts = [(x, -z, y) for x, y, z in ob['verts']]
    me.from_pydata(verts, [], ob['faces'])
    me.validate()
    me.update()
    o = bpy.data.objects.new(ob['name'], me)
    rough = 0.55 if ob['name'].startswith('buildings') else 0.9
    o.data.materials.append(material(ob['name'], ob['color'], rough))
    sc.collection.objects.link(o)

# day light: Nishita sky + sun
world = bpy.data.worlds.new('sky')
sc.world = world
world.use_nodes = True
nt = world.node_tree
nt.nodes.clear()
sky = nt.nodes.new('ShaderNodeTexSky')
try:
    sky.sky_type = 'NISHITA'
    sky.sun_elevation = math.radians(52)
    sky.sun_rotation = math.radians(210)
except Exception:
    pass
bg = nt.nodes.new('ShaderNodeBackground')
bg.inputs['Strength'].default_value = 0.3
out = nt.nodes.new('ShaderNodeOutputWorld')
nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
nt.links.new(bg.outputs['Background'], out.inputs['Surface'])
sun = bpy.data.lights.new('sun', 'SUN')
sun.energy = 3.0
sun.angle = math.radians(1.0)
so = bpy.data.objects.new('sun', sun)
so.rotation_euler = (math.radians(38), 0, math.radians(30))
sc.collection.objects.link(so)

sc.render.engine = 'CYCLES'
sc.cycles.samples = samples
sc.cycles.use_denoising = True
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dev in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev
                sc.cycles.device = 'GPU'
                break
        except Exception:
            continue
except Exception:
    pass
sc.view_settings.view_transform = 'AgX' if 'AgX' in [v.identifier for v in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'
sc.render.film_transparent = False
sc.view_settings.exposure = -0.9
sc.view_settings.look = 'None'

for name, cam in data['cameras'].items():
    cd = bpy.data.cameras.new(name)
    cd.sensor_fit = 'VERTICAL'
    cd.angle_y = math.radians(cam['fov'])
    cd.clip_start = 0.5
    cd.clip_end = 20000
    co = bpy.data.objects.new(name, cd)
    sc.collection.objects.link(co)
    x, y, z = cam['pos']
    co.location = Vector((x, -z, y))
    if 'dir' in cam:
        dx, dy, dz = cam['dir']
        d = Vector((dx, -dz, dy))
    else:
        lx, ly, lz = cam['look']
        d = Vector((lx, -lz, ly)) - co.location
    co.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.camera = co
    sc.render.resolution_x = int(cam['res'][0] * scale)
    sc.render.resolution_y = int(cam['res'][1] * scale)
    sc.render.resolution_percentage = 100
    sc.render.filepath = os.path.join(out_dir, f'{tag}_{name}.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', sc.render.filepath)
