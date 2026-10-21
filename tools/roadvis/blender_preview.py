"""Blender preview of the road pilot (PREVIEW ONLY, offline render, not the game, not Studio).

Inside a Blender binary:
  blender -b --python-exit-code 1 --python blender_preview.py -- <scene.json> <out_dir> <tag> [samples] [scale] [engine] [cams]
or with the PyPI bpy module (Blender as a Python module, no GPU box needed):
  <bpy venv>\\Scripts\\python.exe blender_preview.py -- <scene.json> <out_dir> <tag> 16 0.6 EEVEE

Builds the scene (tools/roadvis/scene.py output), day lighting (Nishita sky + sun), renders every camera in the file
(or the comma list `cams`) to <out_dir>/<tag>_<camera>.png. Roblox (x, y, z) -> Blender (x, -z, y).
engine: CYCLES (default; GPU when available), EEVEE (rasteriser, same sky + sun, low resource) or WORKBENCH (flat
studio light, material colours, shadows; the cheapest). The same engine for every state keeps them comparable.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
scene_path, out_dir, tag = argv[0], argv[1], argv[2]
out_dir = os.path.abspath(out_dir)   # Blender resolves a relative render path against the drive root, not the cwd
samples = int(argv[3]) if len(argv) > 3 else 64
scale = float(argv[4]) if len(argv) > 4 else 1.0
engine = (argv[5] if len(argv) > 5 else 'CYCLES').upper()
only = set(argv[6].split(',')) if len(argv) > 6 and argv[6] else None
threads = int(os.environ.get('ROADVIS_THREADS', '4'))
os.makedirs(out_dir, exist_ok=True)
data = json.load(open(scene_path, encoding='utf-8'))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, rgb, rough=0.85):
    m = bpy.data.materials.new(name)
    lin = (srgb_to_lin(rgb[0]), srgb_to_lin(rgb[1]), srgb_to_lin(rgb[2]), 1.0)
    m.diffuse_color = lin                      # the Workbench (viewport) colour
    m.roughness = rough
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = lin
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
world.color = (0.42, 0.56, 0.75)              # Workbench background
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

sc.render.threads_mode = 'FIXED'
sc.render.threads = threads
vt = [v.identifier for v in sc.view_settings.bl_rna.properties['view_transform'].enum_items]
if engine == 'WORKBENCH':
    sc.render.engine = 'BLENDER_WORKBENCH'
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'MATERIAL'
    sh.show_shadows = True
    sh.shadow_intensity = 0.45
    sh.show_cavity = False
    sh.show_specular_highlight = False
    sc.display.light_direction = (0.45, -0.35, 0.82)       # roughly the sun of the Cycles / EEVEE light
    sc.display.render_aa = '8'
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.exposure = 0.0
elif engine == 'EEVEE':
    sc.render.engine = 'BLENDER_EEVEE'
    ee = sc.eevee
    for k, v in (('taa_render_samples', samples), ('use_shadows', True), ('use_raytracing', False),
                 ('shadow_resolution_scale', 1.0), ('use_gtao', True)):
        try:
            setattr(ee, k, v)
        except Exception:
            pass
    sun.energy = 4.0
    sc.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
    sc.view_settings.exposure = -0.6
else:
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
    sc.view_settings.view_transform = 'AgX' if 'AgX' in vt else 'Filmic'
    sc.view_settings.exposure = -0.9
sc.render.film_transparent = False
sc.view_settings.look = 'None'

for name, cam in data['cameras'].items():
    if only and name not in only:
        continue
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
