"""GLB -> FBX for a built car (body + 4 wheels), one FBX per GLB, textures embedded. Offline only.

  blender -b --factory-startup --python-exit-code 1 -P car_glb_to_fbx.py -- <car_dir> <id> <out_dir>

Each object keeps its own origin (body: bounding-box centre; wheel: the axle centre, axle along X), so the wheel
pivots survive the conversion. Axes: -Z forward, Y up (the same frame as the GLBs / Roblox), scale 1 = metres.
Prints per file: triangle count, bounding-box centre and size, so the FBX can be compared with the GLB.
"""
import json
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
CAR_DIR, CID, OUT = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)
lay = json.load(open(os.path.join(CAR_DIR, f'{CID}_wheels.json')))
files = [f'{CID}.glb'] + [lay['wheel_meshes'][k] for k in ('FL', 'FR', 'RL', 'RR')]
report = {}
for f in files:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(CAR_DIR, f))
    obs = [o for o in bpy.data.objects if o.type == 'MESH']
    assert len(obs) == 1, (f, len(obs))
    ob = obs[0]
    ob.parent = None
    ob.location = (0, 0, 0)
    for o in list(bpy.data.objects):
        if o is not ob:
            bpy.data.objects.remove(o)
    me = ob.data
    me.calc_loop_triangles()
    bb = [Vector(c) for c in ob.bound_box]
    lo = Vector([min(c[i] for c in bb) for i in range(3)])
    hi = Vector([max(c[i] for c in bb) for i in range(3)])
    out = os.path.join(OUT, f[:-4] + '.fbx')
    bpy.ops.export_scene.fbx(filepath=out, use_selection=False, object_types={'MESH'}, path_mode='COPY',
                             embed_textures=True, axis_forward='-Z', axis_up='Y', apply_unit_scale=True,
                             mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False)
    report[os.path.basename(out)] = {'tris': len(me.loop_triangles),
                                     'bbox_centre_blender': [round(v, 4) for v in (lo + hi) / 2],
                                     'bbox_size_blender': [round(v, 4) for v in hi - lo],
                                     'bytes': os.path.getsize(out)}
json.dump(report, open(os.path.join(OUT, f'{CID}_fbx.json'), 'w'), indent=1)
print(json.dumps(report, indent=1))
