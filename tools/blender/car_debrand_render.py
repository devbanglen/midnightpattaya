"""Close-up and turntable renders of a built car (body GLB + 4 wheel GLBs at the layout centres).

  blender -b --factory-startup --python-exit-code 1 -P car_debrand_render.py -- <car_dir> <id> <out_dir> \
      [--views views.json] [--res 900] [--tag before]

<car_dir>/<id>_wheels.json gives the wheel files and centres (frame N: X right, Y up, front -Z, metres; Blender
(bx, by, bz) = N (x, -z, y), like tools/blender/import_car.py). Workbench, textured, back faces culled (Roblox).

views.json: list of
  {"name": "nose", "target": [x, y, z], "dir": [dx, dy, dz], "dist": 0.8, "lens": 50}      perspective close-up
  {"name": "front34", "az": -140, "el": 18, "ortho": true}                                  whole car, fitted
(target / dir in frame N; dir points from the target to the camera). Output: <out_dir>/<id>_<tag>_<name>.png
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
CAR_DIR, CID, OUT = argv[0], argv[1], argv[2]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


RES = opt('--res', 900, int)
TAG = opt('--tag', 'view')
WHEELS = ('FL', 'FR', 'RL', 'RR')
DEFAULT_VIEWS = [
    {'name': 'front34', 'az': -140, 'el': 16, 'ortho': True},
    {'name': 'rear34', 'az': 40, 'el': 16, 'ortho': True},
    {'name': 'side', 'az': -90, 'el': 0, 'ortho': True},
    {'name': 'front', 'az': 180, 'el': 4, 'ortho': True},
    {'name': 'rear', 'az': 0, 'el': 4, 'ortho': True},
]


def n2b(v):
    return Vector((v[0], -v[2], v[1]))


def import_glb(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    obs = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    ob = obs[0]
    ob.name = name
    ob.parent = None
    return ob


def main():
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lay = json.load(open(os.path.join(CAR_DIR, f'{CID}_wheels.json')))
    body = import_glb(os.path.join(CAR_DIR, f'{CID}.glb'), 'body')
    objs = [body]
    for k in WHEELS:
        w = import_glb(os.path.join(CAR_DIR, lay['wheel_meshes'][k]), 'w_' + k)
        w.location = n2b(lay['wheels'][k])
        w.rotation_euler = (0, 0, 0)
        objs.append(w)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.show_backface_culling = True
    sc.world = bpy.data.worlds.new('w')
    sc.world.color = (0.82, 0.84, 0.88)
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = RES
    sc.render.resolution_y = RES if '--wide' not in argv else int(RES * 0.62)
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.clip_start = 0.01
    views = json.load(open(opt('--views', ''))) if '--views' in argv else DEFAULT_VIEWS
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, (hi - lo).length
    for v in views:
        if v.get('ortho'):
            a, e = math.radians(v['az']), math.radians(v['el'])
            d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.data.type = 'ORTHO'
            cam.location = centre + d * size * 3
            cam.data.ortho_scale = size * v.get('scale', 0.95) * max(1.0, RES / sc.render.resolution_y) / \
                max(1.0, RES / sc.render.resolution_y)
            cam.data.clip_end = size * 10
        else:
            d = n2b(v['dir']).normalized()
            t = n2b(v['target'])
            cam.data.type = 'PERSP'
            cam.data.lens = v.get('lens', 50)
            cam.location = t + d * v.get('dist', 0.8)
            cam.data.clip_end = 100
        cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(OUT, f'{CID}_{TAG}_{v["name"]}.png')
        bpy.ops.render.render(write_still=True)
        print('wrote', sc.render.filepath)


main()
