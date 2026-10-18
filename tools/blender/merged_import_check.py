"""Blender-side check of the merged kit modules (mesh-opt): import every <dir>/*.glb with Blender's glTF importer and
compare object names, triangle counts and world bboxes with <dir>/manifest.json (gen_merged.py). A second, independent
glTF reader: a file Blender cannot read the way gen_merged.py wrote it fails here before it goes to Roblox.
  blender -b --factory-startup --python-exit-code 1 -P tools/blender/merged_import_check.py -- <merged dir>
Blender imports glTF Y-up into Z-up: Blender (x, y, z) = glTF (x, -z, y)."""
import json
import os
import sys

import bpy

d = sys.argv[sys.argv.index('--') + 1]
man = {a['name']: a for a in json.load(open(os.path.join(d, 'manifest.json')))['assets']}
bad = 0
for name in sorted(man):
    a = man[name]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(d, name + '.glb'))
    fails = []
    got = {o.name: o for o in bpy.data.objects if o.type == 'MESH'}
    want = {p['name']: p for p in a['parts']}
    if set(got) != set(want):
        fails.append(f'objects {sorted(got)} != {sorted(want)}')
    for n, p in want.items():
        o = got.get(n)
        if not o:
            continue
        me = o.data
        me.calc_loop_triangles()
        tris = len(me.loop_triangles)
        ws = [o.matrix_world @ v.co for v in me.vertices]
        lo = [min(v[i] for v in ws) for i in range(3)]
        hi = [max(v[i] for v in ws) for i in range(3)]
        size = [hi[0] - lo[0], hi[2] - lo[2], hi[1] - lo[1]]          # back to glTF / Roblox axes
        if tris != p['tris']:
            fails.append(f'{n}: {tris} tris != {p["tris"]}')
        if max(abs(size[i] - p['size'][i]) for i in range(3)) > 0.01:
            fails.append(f'{n}: size {[round(v, 3) for v in size]} != {p["size"]}')
        if not me.uv_layers:
            fails.append(f'{n}: no UVs')
        if len(me.materials) != 1 or me.materials[0].name != p['material']:
            fails.append(f'{n}: materials {[m.name for m in me.materials]} != {p["material"]}')
    bad += bool(fails)
    print(('IMPORT_OK ' if not fails else 'IMPORT_FAIL ') + name + ' ' + '; '.join(fails), flush=True)
print(f'DONE merged import check: {len(man) - bad}/{len(man)} ok', flush=True)
sys.exit(1 if bad else 0)
