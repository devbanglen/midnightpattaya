"""Render a textured OBJ from 6 angles (3/4, side, front, rear, top-down, high rear 3/4 like the game camera) into one
PNG strip, studio light so dark paint still reads.
  blender -b -P bl_turntable.py -- <in.obj> <out.png>
"""
import sys, math, bpy
from mathutils import Vector

src, dst = sys.argv[sys.argv.index('--') + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
if src.lower().endswith('.glb'):
    bpy.ops.import_scene.gltf(filepath=src)
else:
    bpy.ops.wm.obj_import(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
centre, size = (lo + hi) / 2, max(hi - lo)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'TEXTURE'
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new('w')
sc.world.color = (1, 1, 1)
sc.render.resolution_x = sc.render.resolution_y = 512

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = 'ORTHO'
cam.data.ortho_scale = size * 1.15

import numpy as np
tiles = []
for k, (az, el) in enumerate([(35, 20), (90, 0), (0, 0), (180, 0), (0, 89), (215, 45)]):
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = centre + d * size * 3
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = dst + f'.v{k}.png'
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    tiles.append(np.array(img.pixels[:]).reshape(512, 512, 4))
strip = np.concatenate(tiles, axis=1)
out = bpy.data.images.new('strip', strip.shape[1], 512, alpha=True)
out.pixels = strip.ravel()
out.filepath_raw, out.file_format = dst, 'PNG'
out.save()
