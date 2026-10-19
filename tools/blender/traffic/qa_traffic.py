"""QA renders of the traffic GLBs (inside Blender; reuses qa_render.py by import, no edit):
  blender -b --factory-startup -P tools/blender/traffic/qa_traffic.py -- <vis_out_dir>/traffic <png_dir> --views A,B
writes <png_dir>/views/<NAME>_{front,34,back,34flip}.png (back-face culling on; 34flip = every triangle's winding
reversed), <png_dir>/traffic_lineup.png (all vehicles side by side, each inside a green wire frame of its client
collision box) and <png_dir>/traffic_night.png (EEVEE, rear 3/4: tail and head lamps)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import qa_render as Q              # noqa: E402  (parses the same argv: SRC DST --views)
import bpy                         # noqa: E402
from mathutils import Vector       # noqa: E402

Q.find_glb = lambda n: os.path.join(Q.SRC, n + '.glb')


def wire_box(W, H, L, ox, z0, mat):
    """12 thin bars along the edges of the collision box (Blender axes: x across, y along, z up)"""
    hx, hy = W / 2, L / 2
    t = 0.08
    edges = []
    for x in (-hx, hx):
        for z in (z0, z0 + H):
            edges.append(((ox + x, -hy, z), (ox + x, hy, z)))
    for y in (-hy, hy):
        for z in (z0, z0 + H):
            edges.append(((ox - hx, y, z), (ox + hx, y, z)))
        for x in (-hx, hx):
            edges.append(((ox + x, y, z0), (ox + x, y, z0 + H)))
    for a, b in edges:
        a, b = Vector(a), Vector(b)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(a + b) / 2)
        o = bpy.context.active_object
        d = b - a
        o.scale = (max(abs(d.x), t), max(abs(d.y), t), max(abs(d.z), t))
        o.data.materials.append(mat)


def lineup(names, night=False):
    Q.reset()
    x = 0.0
    insts = []
    wire = Q.mat('wire', (0.2, 1.0, 0.4, 1))
    for n in names:
        col, _root, _objs = Q.import_glb(Q.find_glb(n))
        a = Q.MAN.get(n, {})
        W, H, L = a.get('footprint') or (7, 3, 16)
        insts.append(Q.instance(col, (x, 0, 0)))
        if not night:
            wire_box(W, H, L, x, 1.4, wire)          # the client's Body: bottom 1.4 above the road
            Q.label(n.split('_', 1)[1] + '\n' + f"{a.get('tris', '?')} tris", (x, -L / 2 - 2, -2.6), 1.0)
        x += max(W, 7) + 4.0
    bpy.context.view_layer.update()
    extra = [o for o in bpy.context.scene.objects
             if o.type in ('MESH', 'FONT') and o.users_collection and o.users_collection[0] == bpy.context.scene.collection]
    lo, hi = Q.inst_bounds(insts, extra)
    if night:
        Q.night_setup(lo, hi)
        Q.render(os.path.join(Q.DST, 'traffic_night.png'), lo, hi, az=-150, el=14, pad=1.1, res=1800)
    else:
        Q.render(os.path.join(Q.DST, 'traffic_lineup.png'), lo, hi, az=-35, el=24, pad=1.06, res=2200)


if __name__ == '__main__':
    names = Q.VIEWS or sorted(Q.MAN)
    for n in names:
        Q.asset_views(n)
    lineup(names)
    lineup(names, night=True)
    print('QA DONE', flush=True)
