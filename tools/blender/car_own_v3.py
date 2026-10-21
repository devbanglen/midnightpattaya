"""Own body v3 for the test car: red_sports_own_v3 (+ _red, _white). Modelled from scratch in this Blender script.

docs/CAR_IMPORT_RED_SPORTS.md, "Own body v3". No third-party mesh, texture or reference image: every vertex and every
texel comes from the numbers and functions in this file. Deterministic: the same script on the same Blender build gives
byte-identical GLBs (own GLB and PNG writers, no timestamps, fixed operator settings, sorted JSON).

  blender -b --factory-startup --python-exit-code 1 -P tools/blender/car_own_v3.py -- build <out_dir> [--v2-dir <dir>]
  <bpy venv>/python tools/blender/bpy_local.py tools/blender/car_own_v3.py -- build <out_dir>
      -> <id>.glb (midnight blue), <id>_red.glb, <id>_white.glb, <id>_wheels.json, <id>_build.json, <id>_emblem.png
  ... -- fbx <dir>                                       one FBX per body GLB (+ <id>_fbx.json)
  ... -- render <car_dir> <id> <out_dir> <tag> [--views views.json] [--engine workbench|eevee|cycles] [--res 900]
                [--wheels <wheels.json>] [--steer <deg>]   QA renders of any built car (body + its 4 wheel GLBs)
  ... -- preview <out_dir>                                build + quick Workbench views (design iteration)
  tools/blender/run_own_v3.sh does build / render on the GPU box through gslot.sh.

How the body is made (frame N: X right, Y up, front -Z, metres; the body is centred on its bounding box because
Roblox centres a MeshPart on it, and the red_sports wheel layout is given in that frame):
  1. a quad control cage: 17 rings (cross-sections, RINGS) x 12 points per half section, mirrored, closed at the
     nose by a quad grid (Coons patch); the last ring stays open. Edge creases (CREASES) keep the intended lines
     sharp: the floor edge, the Kamm edge, the shoulder character line, the roof and rear-window edges, the buttresses;
  2. Catmull-Clark subdivision (Blender Subdivision Surface modifier, 2 levels, creases on); the open tail ring is
     then closed by one flat Kamm face (constrained Delaunay triangulation, fill_tail), and the flat floor and the
     flat underside strips are merged (dissolve) to save triangles;
  3. centring on the bounding box (length 4.50145 m = red_sports, so the game's 16-stud scaling is unchanged),
     then exact booleans at the red_sports wheel layout: four wheel tubs (room for full steering lock at the front),
     two side intakes ahead of the rear wheels, two exhaust pockets. Every cut stays a closed shell;
  4. closed detail parts (lamp bars, LED fangs, stepped gills, mirrors, tail light blade, outlet rims, diffuser fins,
     splitter, MP emblems): each part is its own closed solid, oriented outward, sunk into the body;
  5. smooth-by-angle normals (32 degrees: sharp only at the creases and part edges), own UVs (box projection, the left
     and right halves share texels) and a procedural 1024^2 texture: paint, dark glass, black trim, panel gaps, vents,
     plus a decal strip for the lamp, blade, gill and emblem graphics. One material, one texture per MeshPart;
  6. own GLB writer (generator = this script).
The wheels are the v2 turbine wheels, used as they are (red_sports_original_v2_wheel_*.glb).
"""
import hashlib
import json
import math
import os
import struct
import sys
import zlib

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Vector
except ImportError:          # imported by the offline tests (numpy only)
    bpy = None

CID = 'red_sports_own_v3'
GENERATOR = 'MIDNIGHT PATTAYA tools/blender/car_own_v3.py'
UPLOAD = 'BLOCKED until the owner approves (own design v3; nothing uploaded or imported)'
V2_ID = 'red_sports_original_v2'
LENGTH = 4.5014486           # = red_sports bbox length: the game scales every body to 16 studs by it (3.554 studs/m)
WHEEL_R = 0.3848
TYRE_W = 0.344
STEER_DEG = 28.0
# red_sports wheel layout (body space, metres): the v2 wheels and the game integration use exactly these numbers
LAYOUT = {'FL': (-0.8878, -0.3235, -1.2939), 'FR': (0.8782, -0.3229, -1.2939),
          'RL': (-0.8879, -0.3276, 1.3498), 'RR': (0.8783, -0.3279, 1.3498)}
AXLE_F = (-1.2939, -0.3232)  # (z, y), mean of left and right
AXLE_R = (1.3498, -0.3278)
TRACK_X = 0.883              # mean |x| of the wheel centres (the body is mirror-symmetric)

# ------------------------------------------------------------------------------------------------ the cage --
# One ring = one cross-section, 12 points per half (x >= 0), from the floor centre round the side to the top centre:
#   c0 floor centre (x = 0)  c1 floor edge (crease)  c2 sill bottom  c3 sill top  c4 widest  c5 shoulder (the
#   character crease)  c6 fender top outer / glass base / buttress base  c7 fender top / glass mid / buttress outer top
#   c8 fender inner / roof edge / buttress inner top  c9 deck outer / roof outer / deck edge  c10 deck / roof inner
#   c11 top centre (x = 0)
# Each point: (x, y, dz); the ring's z is z0 + dz. These are cage positions: the subdivided surface lies a little
# inside the cage on convex parts.
RINGS = [
    # 0: front face outline (nose cap boundary): lip at the bottom, deck front edge at the top
    (-2.2557, [(0, -.37, 0), (.34, -.37, .005), (.66, -.373, .02), (.80, -.36, .045), (.88, -.325, .07),
               (.91, -.275, .09), (.91, -.225, .10), (.88, -.19, .105), (.82, -.172, .10), (.72, -.165, .10),
               (.36, -.16, .10), (0, -.16, .10)]),
    # 1: nose corners, lower bumper, deck front
    (-1.98, [(0, -.59, -.05), (.45, -.59, -.05), (.82, -.57, -.03), (.98, -.47, 0), (1.03, -.32, .02),
             (1.03, -.11, .02), (.96, -.05, .02), (.86, -.035, .02), (.68, -.055, .03), (.52, -.08, .03),
             (.26, -.095, .03), (0, -.10, .03)]),
    # 2: front arch front
    (-1.80, [(0, -.61, 0), (.60, -.61, 0), (.95, -.58, 0), (1.055, -.47, 0), (1.08, -.30, 0),
             (1.08, .05, 0), (1.0, .105, 0), (.89, .12, 0), (.70, .085, 0), (.54, .045, 0), (.27, .015, 0),
             (0, .01, 0)]),
    (-1.55, [(0, -.61, 0), (.60, -.61, 0), (.97, -.58, 0), (1.065, -.47, 0), (1.09, -.29, 0),
             (1.09, .14, 0), (1.01, .185, 0), (.90, .20, 0), (.70, .17, 0), (.54, .12, 0), (.27, .075, 0),
             (0, .07, 0)]),
    # 4: front axle
    (-1.29, [(0, -.61, 0), (.60, -.61, 0), (.97, -.58, 0), (1.065, -.47, 0), (1.09, -.28, 0),
             (1.09, .165, 0), (1.01, .205, 0), (.90, .215, 0), (.70, .19, 0), (.54, .15, 0), (.27, .11, 0),
             (0, .105, 0)]),
    # 5: cowl (windscreen base), A-pillar foot at c8
    (-1.08, [(0, -.61, 0), (.60, -.61, 0), (.96, -.58, 0), (1.05, -.47, 0), (1.075, -.27, 0),
             (1.075, .175, 0), (.97, .22, 0), (.86, .23, 0), (.72, .235, .08), (.53, .175, .02),
             (.265, .135, -.02), (0, .125, -.03)]),
    # 6: windscreen
    (-0.78, [(0, -.61, 0), (.60, -.61, 0), (.94, -.58, 0), (.975, -.47, 0), (.98, -.26, 0),
             (1.045, .18, 0), (.89, .225, 0), (.78, .30, 0), (.64, .375, 0), (.48, .395, -.02), (.24, .415, -.04),
             (0, .42, -.05)]),
    # 7: windscreen header
    (-0.47, [(0, -.61, 0), (.60, -.61, 0), (.935, -.58, 0), (.965, -.47, 0), (.97, -.25, 0),
             (1.035, .18, 0), (.86, .225, 0), (.74, .375, 0), (.58, .525, 0), (.42, .575, -.01), (.21, .595, -.02),
             (0, .60, -.02)]),
    # 8: roof
    (-0.16, [(0, -.61, 0), (.60, -.61, 0), (.935, -.58, 0), (.965, -.47, 0), (.97, -.24, 0),
             (1.035, .185, 0), (.86, .23, 0), (.73, .385, 0), (.575, .54, 0), (.415, .595, 0), (.21, .615, 0),
             (0, .62, 0)]),
    # 9: roof rear edge (B-pillar)
    (0.14, [(0, -.61, 0), (.60, -.61, 0), (.945, -.58, 0), (.975, -.47, 0), (.98, -.23, 0),
            (1.05, .20, 0), (.88, .245, 0), (.76, .395, 0), (.585, .525, 0), (.425, .57, 0), (.215, .585, 0),
            (0, .59, 0)]),
    # 10: rear window base, buttresses start
    (0.38, [(0, -.61, 0), (.60, -.61, 0), (.96, -.58, 0), (1.0, -.47, 0), (1.015, -.22, 0),
            (1.065, .225, 0), (.93, .27, 0), (.84, .465, 0), (.70, .49, 0), (.56, .43, 0), (.28, .43, 0),
            (0, .43, 0)]),
    # 11: side intake; the shoulder starts to kick up over the rear wheel
    (0.75, [(0, -.61, 0), (.60, -.61, 0), (.97, -.58, 0), (1.05, -.47, 0), (1.08, -.21, 0),
            (1.085, .26, 0), (.97, .30, 0), (.90, .44, 0), (.77, .46, 0), (.60, .39, 0), (.30, .39, 0),
            (0, .39, 0)]),
    # 12: rear arch front
    (1.05, [(0, -.61, 0), (.60, -.61, 0), (.98, -.58, 0), (1.07, -.47, 0), (1.10, -.21, 0),
            (1.105, .29, 0), (1.0, .32, 0), (.94, .415, 0), (.81, .43, 0), (.62, .355, 0), (.31, .355, 0),
            (0, .355, 0)]),
    # 13: rear axle (haunch peak)
    (1.36, [(0, -.61, 0), (.60, -.61, 0), (.98, -.58, 0), (1.075, -.47, 0), (1.105, -.21, 0),
            (1.105, .30, 0), (1.0, .33, 0), (.945, .395, 0), (.82, .40, 0), (.63, .325, 0), (.315, .325, 0),
            (0, .325, 0)]),
    # 14: rear arch rear; the diffuser ramp starts
    (1.72, [(0, -.61, 0), (.60, -.61, 0), (.97, -.57, 0), (1.06, -.45, 0), (1.09, -.20, 0),
            (1.09, .285, 0), (.99, .31, 0), (.94, .365, 0), (.82, .375, 0), (.64, .295, 0), (.32, .295, 0),
            (0, .295, 0)]),
    (2.06, [(0, -.50, 0), (.60, -.50, 0), (.92, -.47, 0), (1.03, -.37, 0), (1.06, -.18, 0),
            (1.06, .265, 0), (.96, .29, 0), (.93, .34, 0), (.82, .35, 0), (.645, .265, 0), (.32, .265, 0),
            (0, .265, 0)]),
    # 16: tail ring = the outline of the flat Kamm face (+ the buttress ends, c6..c9)
    (2.2387, [(0, -.36, 0), (.60, -.36, 0), (.88, -.345, 0), (.98, -.27, 0), (1.02, -.13, 0),
              (1.02, .25, 0), (.93, .275, 0), (.91, .325, 0), (.80, .335, 0), (.645, .25, 0), (.32, .245, 0),
              (0, .245, 0)]),
]
NCOL = 12
NOSE_BULGE = 0.02            # the nose cap's centre sits this far ahead of its ring (along -Z)
# creases: ('col', j, i0, i1, w) = column j between rings i0..i1; ('ring', i, j0, j1, w) = ring i between columns
CREASES = [
    ('col', 1, 0, 14, 1.0),          # floor edge (flat floor = the bounding-box bottom)
    ('ring', 14, 0, 1, 1.0),         # floor / diffuser kink
    ('ring', 0, 0, 2, 0.8),          # nose lip
    ('ring', 16, 0, NCOL - 1, 1.0),  # Kamm tail: the whole tail ring (flat tail face, sharp edge)
    ('col', 5, 1, 16, 1.0),          # shoulder: the one character line, nose corner to tail
    ('ring', 0, 9, NCOL - 1, 0.5),   # nose top edge (lamp line)
    ('col', 6, 5, 10, 0.4),          # glass base
    ('ring', 9, 8, NCOL - 1, 0.7),   # roof rear edge
    ('ring', 10, 9, NCOL - 1, 0.9),  # rear window base
    ('col', 7, 10, 16, 0.5),         # buttress outer top
    ('col', 8, 10, 16, 0.7),         # buttress inner top
    ('col', 9, 10, 16, 0.6),         # deck edge (buttress inner wall foot)
]


def _vid_factory():
    verts, index = [], {}

    def vid(i, j, side):
        """Vertex of ring i, column j on side +1 / -1 (the first and last columns are shared, on the centre plane)."""
        key = (i, j, 0 if j in (0, NCOL - 1) else side)
        if key not in index:
            z0, pts = RINGS[i]
            x, y, dz = pts[j]
            index[key] = len(verts)
            verts.append((0.0 if key[2] == 0 else side * x, y, z0 + dz))
        return index[key]
    return verts, vid


def _coons(verts, bot, top, lef, rig, bulge=None):
    """Quad grid (len(bot) x len(lef)) filling four boundary chains; returns the grid of vertex ids (u, v)."""
    P = np.array(verts, float)
    nu, nv = len(bot) - 1, len(lef) - 1
    grid = [[None] * (nv + 1) for _ in range(nu + 1)]
    for u in range(nu + 1):
        grid[u][0], grid[u][nv] = bot[u], top[u]
    for v in range(nv + 1):
        grid[0][v], grid[nu][v] = lef[v], rig[v]
    for u in range(1, nu):
        for v in range(1, nv):
            s, t = u / nu, v / nv
            p = ((1 - t) * P[bot[u]] + t * P[top[u]] + (1 - s) * P[lef[v]] + s * P[rig[v]]
                 - ((1 - s) * (1 - t) * P[bot[0]] + s * (1 - t) * P[bot[nu]] + (1 - s) * t * P[top[0]]
                    + s * t * P[top[nu]]))
            if 2 * u == nu:
                p[0] = 0.0
            if bulge is not None:
                p = p + np.asarray(bulge) * math.sin(math.pi * s) * math.sin(math.pi * t) ** 0.5
            grid[u][v] = len(verts)
            verts.append(tuple(p))
    return grid


def cage():
    """Control cage: vertices, faces (outward winding), crease weights per edge, param (ring, column) per vertex."""
    verts, vid = _vid_factory()
    faces = []
    nring = len(RINGS)
    for i in range(nring - 1):
        for j in range(NCOL - 1):
            for side in (1, -1):
                a, b, c, d = vid(i, j, side), vid(i + 1, j, side), vid(i + 1, j + 1, side), vid(i, j + 1, side)
                faces.append((a, d, c, b) if side > 0 else (a, b, c, d))
    param = {}
    for (i, j, s), v in list(_index_items(vid, nring)):
        param[v] = (float(i), float(j))
    # nose: 4 x 7 quad grid on ring 0 (bottom c2'..c2, sides c2..c9, top c9'..c9), bulging forward
    i, tj = 0, NCOL - 3
    n0 = len(verts)
    grid = _coons(verts, [vid(i, 2, -1), vid(i, 1, -1), vid(i, 0, 1), vid(i, 1, 1), vid(i, 2, 1)],
                  [vid(i, tj, -1), vid(i, tj + 1, -1), vid(i, NCOL - 1, 1), vid(i, tj + 1, 1), vid(i, tj, 1)],
                  [vid(i, j, -1) for j in range(2, tj + 1)], [vid(i, j, 1) for j in range(2, tj + 1)],
                  bulge=(0, 0, -NOSE_BULGE))
    for v in range(n0, len(verts)):
        param[v] = (-0.5, -1.0)
    for u in range(len(grid) - 1):
        for v in range(len(grid[0]) - 1):
            faces.append((grid[u][v + 1], grid[u + 1][v + 1], grid[u + 1][v], grid[u][v]))      # faces -Z
    # tail: no faces on the last ring. Subdivision keeps the open ring as a sharp boundary in the plane z = z_tail,
    # and fill_tail() closes it with a flat constrained-Delaunay face (a Coons grid folds at the buttress ears).
    crease = {}
    for kind, a, b0, b1, w in CREASES:
        if kind == 'col':
            for i in range(b0, b1):
                for s in (1, -1):
                    crease[_ek(vid(i, a, s), vid(i + 1, a, s))] = w
        else:
            for j in range(b0, b1):
                for s in (1, -1):
                    crease[_ek(vid(a, j, s), vid(a, j + 1, s))] = w
    return np.array(verts, float), faces, crease, param


def _index_items(vid, nring):
    for i in range(nring):
        for j in range(NCOL):
            for s in ((0,) if j in (0, NCOL - 1) else (1, -1)):
                yield (i, j, s), vid(i, j, s if s else 1)


def _ek(a, b):
    return (a, b) if a < b else (b, a)


# ------------------------------------------------------------------------------------------- Blender helpers --
def new_object(name, verts, faces, mat_names=('skin',), face_mats=None, crease=None, param=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    for m in mat_names:
        me.materials.append(bpy.data.materials.get(m) or bpy.data.materials.new(m))
    if face_mats is not None:
        me.polygons.foreach_set('material_index', [int(k) for k in face_mats])
    uvl = me.uv_layers.new(name='param')
    if param is not None:
        data = []
        for p in me.polygons:
            for li in p.loop_indices:
                data += list(param.get(me.loops[li].vertex_index, (-9.0, -9.0)))
        uvl.data.foreach_set('uv', data)
    else:
        uvl.data.foreach_set('uv', [-9.0] * (2 * len(me.loops)))
    if crease:
        att = me.attributes.new('crease_edge', 'FLOAT', 'EDGE')
        vals = [crease.get(_ek(*e.vertices), 0.0) for e in me.edges]
        att.data.foreach_set('value', vals)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def evaluated_copy(ob, name):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    out = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(out)
    return out


def subdivided_body():
    V, F, crease, param = cage()
    ob = new_object('cage', V, F, crease=crease, param=param)
    mod = ob.modifiers.new('sub', 'SUBSURF')
    mod.levels = mod.render_levels = 2
    mod.use_creases = True
    mod.uv_smooth = 'NONE'
    mod.boundary_smooth = 'ALL'
    mod.use_limit_surface = True
    mod.quality = 3
    body = evaluated_copy(ob, 'body_sub')
    bpy.data.objects.remove(ob)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    fill_tail(bm)
    # the flat floor and the flat underside strips need no subdivision: merge their coplanar faces (only those, so
    # the cage parameters stay accurate everywhere the texture uses them)

    def flat(f):
        n = f.normal
        return n.y < -0.99999
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and all(flat(f) for f in e.link_faces)]
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.02), use_dissolve_boundaries=False,
                             verts=[], edges=edges)
    edges = [e for e in bm.edges if len(e.link_faces) == 2 and all(f.normal.y < -0.75 for f in e.link_faces)]
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.5), use_dissolve_boundaries=False,
                             verts=[], edges=edges)
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return body


def fill_tail(bm):
    """Close the open tail ring of the subdivided body with one flat face, triangulated by a constrained Delaunay
    triangulation in the tail plane (no slivers on the long straight edges), wound to face +Z."""
    from mathutils.geometry import delaunay_2d_cdt
    bm.verts.ensure_lookup_table()
    bnd = [e for e in bm.edges if e.is_boundary]
    if not bnd:
        raise RuntimeError('no open tail ring')
    nxt = {}
    for e in bnd:
        a, b = e.verts
        f = e.link_faces[0]
        # walk the boundary opposite to the adjacent face's winding, so the new face winds consistently
        loop = [lp for lp in f.loops if lp.edge == e][0]
        u, v = (loop.vert, loop.link_loop_next.vert)
        nxt[v.index] = u.index
    start = min(nxt)
    ring = [start]
    while nxt[ring[-1]] != start:
        ring.append(nxt[ring[-1]])
        if len(ring) > len(nxt):
            raise RuntimeError('tail ring is not one loop')
    if len(ring) != len(bnd):
        raise RuntimeError(f'open boundary is not one loop ({len(ring)} of {len(bnd)} edges)')
    zs = [bm.verts[i].co.z for i in ring]
    if max(zs) - min(zs) > 1e-6 or abs(zs[0] - TAIL_Z) > 1e-6:
        raise RuntimeError('the tail ring is not flat')
    xy = [Vector((bm.verts[i].co.x, bm.verts[i].co.y)) for i in ring]
    out_v, _, out_f, orig_v, _, _ = delaunay_2d_cdt(xy, [], [list(range(len(ring)))], 1, 1e-9)
    if len(out_v) != len(ring):
        raise RuntimeError('tail triangulation added vertices')
    vmap = [ring[o[0]] for o in orig_v]
    uvl = bm.loops.layers.uv['param']
    mat = 0
    for tri in out_f:
        a, b, c = (out_v[k] for k in tri)
        ccw = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x) > 0
        idx = [vmap[k] for k in (tri if ccw else tri[::-1])]           # counter-clockwise in (x, y) = faces +Z
        f = bm.faces.new([bm.verts[i] for i in idx])
        f.material_index = mat
        for lp in f.loops:
            lp[uvl].uv = (float(len(RINGS) - 1) + 0.5, -1.0)
    bm.normal_update()


def fix_winding(V, F):
    """Orient a closed mesh outward (signed volume > 0)."""
    P = np.asarray(V, float)
    vol = 0.0
    for f in F:
        for k in range(1, len(f) - 1):
            vol += np.dot(P[f[0]], np.cross(P[f[k]], P[f[k + 1]]))
    return list(F) if vol > 0 else [tuple(reversed(f)) for f in F]


def rounded_polygon(pts, r, nseg=4):
    """2D polygon (counter-clockwise) with every corner replaced by an arc of radius r."""
    pts = np.asarray(pts, float)
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        d0 = (p0 - p1) / np.linalg.norm(p0 - p1)
        d2 = (p2 - p1) / np.linalg.norm(p2 - p1)
        ang = math.acos(max(-1.0, min(1.0, float(d0 @ d2))))
        t = r / math.tan(ang / 2)
        bis = (d0 + d2) / np.linalg.norm(d0 + d2)
        c = p1 + bis * r / math.sin(ang / 2)
        a, b = p1 + d0 * t - c, p1 + d2 * t - c
        a0, a1 = math.atan2(a[1], a[0]), math.atan2(b[1], b[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(nseg + 1):
            q = a0 + da * k / nseg
            out.append(c + r * np.array((math.cos(q), math.sin(q))))
    return np.array(out)


def prism(profile, a0, a1, embed):
    """Closed prism: a 2D profile extruded from a0 to a1; embed(u, v, a) -> (x, y, z)."""
    n = len(profile)
    V = [embed(u, v, a0) for u, v in profile] + [embed(u, v, a1) for u, v in profile]
    F = [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    F += [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    return V, fix_winding(V, F)


def cylinder_x(zc, yc, r, x0, x1, seg=48):
    prof = [(zc + r * math.sin(2 * math.pi * k / seg), yc + r * math.cos(2 * math.pi * k / seg)) for k in range(seg)]
    return prism(prof, x0, x1, lambda u, v, a: (a, v, u))


# Booleans (frame N, metres). Tubs: cylinders about the wheel axles, from an inner wall to outside the body; the
# front ones leave room for the wheel at full steering lock (28 degrees).
TUBS = {'front': (AXLE_F[0], AXLE_F[1], 0.445, 0.50), 'rear': (AXLE_R[0], AXLE_R[1], 0.43, 0.62)}
SCOOP = {'profile': [(0.52, -0.17), (0.93, -0.17), (0.93, 0.10), (0.61, 0.10)], 'r': 0.05, 'x_in': 1.0}
OUTLETS = {'x': 0.30, 'y': -0.235, 'hw': 0.085, 'hh': 0.036, 'r': 0.02}
TAIL_Z = RINGS[-1][0]


def cutter_meshes():
    """[(name, material, V, F)]: closed solids subtracted from the body."""
    out = []
    for key, (zc, yc, r, xi) in TUBS.items():
        for s in (1, -1):
            V, F = cylinder_x(zc, yc, r, min(s * xi, s * 1.45), max(s * xi, s * 1.45))
            out.append((f'tub_{key}_{s}', 'tub', V, F))
    prof = rounded_polygon(SCOOP['profile'], SCOOP['r'])
    for s in (1, -1):
        V, F = prism(prof, s * SCOOP['x_in'], s * 1.45, lambda u, v, a: (a, v, u))
        out.append((f'scoop_{s}', 'scoop', V, fix_winding(V, F)))
    o = OUTLETS
    for s in (1, -1):
        cx = s * o['x']
        prof = rounded_polygon([(cx - o['hw'], o['y'] - o['hh']), (cx + o['hw'], o['y'] - o['hh']),
                                (cx + o['hw'], o['y'] + o['hh']), (cx - o['hw'], o['y'] + o['hh'])], o['r'])
        V, F = prism(prof, TAIL_Z - 0.16, TAIL_Z + 0.2, lambda u, v, a: (u, v, a))
        out.append((f'outlet_{s}', 'outlet', V, F))
    return out


def cut_body(body):
    coll = bpy.data.collections.new('cutters')
    bpy.context.scene.collection.children.link(coll)
    obs = []
    for name, mat, V, F in cutter_meshes():
        ob = new_object(name, V, F, mat_names=(mat,))
        bpy.context.scene.collection.objects.unlink(ob)
        coll.objects.link(ob)
        obs.append(ob)
    mod = body.modifiers.new('cut', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.operand_type = 'COLLECTION'
    mod.collection = coll
    mod.solver = 'EXACT'
    mod.material_mode = 'TRANSFER'
    out = evaluated_copy(body, 'body_cut')
    for ob in obs:
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(coll)
    bpy.data.objects.remove(body)
    return out


TAG = {'skin': 0, 'tub': 1, 'scoop': 2, 'outlet': 3}


def body_arrays(ob):
    """Triangles of the cut body: P (n,3), T (m,3), param (m,3,2) per corner, tag (m,)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method='BEAUTY', ngon_method='BEAUTY')
    bm.to_mesh(ob.data)
    bm.free()
    me = ob.data
    me.calc_loop_triangles()
    m = len(me.loop_triangles)
    tv = np.empty(m * 3, np.int64)
    me.loop_triangles.foreach_get('vertices', tv)
    tl = np.empty(m * 3, np.int64)
    me.loop_triangles.foreach_get('loops', tl)
    tm = np.empty(m, np.int64)
    me.loop_triangles.foreach_get('material_index', tm)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers['param'].data.foreach_get('uv', uv)
    names = [mt.name.split('.')[0] for mt in me.materials]
    tag = np.array([TAG[names[k]] for k in tm], np.int64)
    return co.reshape(-1, 3), tv.reshape(-1, 3), uv.reshape(-1, 2)[tl.reshape(-1, 3)], tag


# --------------------------------------------------------------------------------------------- the parts --
ATLAS = 1024
DECAL_Y = 896                # rows DECAL_Y..1023: graphics of the parts and the flat colour patches
DECALS = {                   # (x0, y0, x1, y1) px; the emblem field is the v2 one (224 x 112)
    'emblem': (4, 900, 228, 1012),
    'lamp': (240, 900, 752, 948),
    'tail': (240, 952, 1020, 976),
    'fang': (760, 900, 1020, 916),
    'gill': (760, 920, 1020, 944),
    'metal': (240, 982, 330, 1018),
    'black': (340, 982, 400, 1018),
    'wall': (410, 982, 470, 1018),
    'paint': (480, 982, 560, 1018),
    'teal': (570, 982, 610, 1018),
    'mirror': (620, 982, 670, 1018),
    'dark': (680, 982, 730, 1018),
    'under': (740, 982, 790, 1018),
    'grille': (800, 982, 1020, 1018),
}
FLAT = ('metal', 'black', 'wall', 'paint', 'teal', 'mirror', 'dark', 'under')


def decal_uv(name, u, v, inset=1.5):
    x0, y0, x1, y1 = DECALS[name]
    u, v = np.asarray(u, float), np.asarray(v, float)
    return np.stack([(x0 + inset + u * (x1 - x0 - 2 * inset)) / ATLAS,
                     (y0 + inset + v * (y1 - y0 - 2 * inset)) / ATLAS], -1)


def flat_uv(name):
    return decal_uv(name, 0.5, 0.5)


class Parts:
    """Closed solids: triangles with per-corner UVs (decals / flat patches); each part is oriented outward."""

    def __init__(self):
        self.P, self.T, self.UV, self.G = [], [], [], []
        self.n = 0
        self.log = []

    def add(self, V, faces, uvs, name):
        V = np.asarray(V, float)
        tris, tuv = [], []
        for f, u in zip(faces, uvs):
            for k in range(1, len(f) - 1):
                tris.append((f[0], f[k], f[k + 1]))
                tuv.append((u[0], u[k], u[k + 1]))
        tris, tuv = np.array(tris, np.int64), np.array(tuv, float)
        tp = V[tris]
        vol = float(np.einsum('ij,ij->i', tp[:, 0], np.cross(tp[:, 1], tp[:, 2])).sum())
        if vol < 0:
            tris, tuv = tris[:, ::-1], tuv[:, ::-1]
        self.P.append(V)
        self.T.append(tris + self.n)
        self.UV.append(tuv)
        self.G.append(np.full(len(tris), len(self.log)))
        self.n += len(V)
        self.log.append({'name': name, 'verts': int(len(V)), 'tris': int(len(tris)),
                         'volume_m3': round(abs(vol) / 6, 6)})

    def arrays(self):
        return (np.concatenate(self.P), np.concatenate(self.T), np.concatenate(self.UV), np.concatenate(self.G))


def tube(parts, stations, face_uv, name, cap='wall', closed=False):
    """Solid swept through stations (each a ring of m points, same order). face_uv(i, k) -> 4 UVs for the quad
    between stations i, i+1 and ring edge k (k, k+1). Open paths get end caps."""
    S = np.asarray(stations, float)
    L, m = S.shape[:2]
    V = S.reshape(-1, 3)
    F, U = [], []
    for i in range(L - 1 if not closed else L):
        i2 = (i + 1) % L
        for k in range(m):
            k2 = (k + 1) % m
            F.append((i * m + k, i * m + k2, i2 * m + k2, i2 * m + k))
            U.append(face_uv(i, k))
    if not closed:
        c = flat_uv(cap)
        F.append(tuple(range(m - 1, -1, -1)))
        U.append([c] * m)
        F.append(tuple((L - 1) * m + k for k in range(m)))
        U.append([c] * m)
    parts.add(V, F, U, name)


def ring_box(a, b, n, h, sink):
    """Cross-section of a raised strip: a, b = its two surface edge points, n = surface normal (shared)."""
    return [a + n * h, b + n * h, b - n * sink, a - n * sink]


def strip_uv(decal, L, wall='wall'):
    w = flat_uv(wall)

    def f(i, k):
        if k == 0:                         # the raised face: u along the strip, v across
            return list(decal_uv(decal, np.array([i, i, i + 1, i + 1]) / (L - 1), np.array([0, 1, 1, 0])))
        return [w] * 4
    return f


def solid_uv(name):
    c = flat_uv(name)
    return lambda i, k: [c] * 4


def ray_hit(bvh, o, d):
    d = Vector(d).normalized()
    loc, nrm, idx, dist = bvh.ray_cast(Vector(o), d)
    if loc is None:
        raise RuntimeError(f'part ray missed the body: {tuple(o)} {tuple(d)}')
    return np.array(loc), np.array(nrm)


def surface_strip(bvh, pts, half_w, direction, across=(0, 1, 0), samples=None):
    """Two edge lines of a strip along polyline pts (3D guide points in front of the surface), projected onto the
    body along `direction`. Returns lists of (edge a, edge b, normal)."""
    pts = np.asarray(pts, float)
    if samples:
        t = np.linspace(0, 1, samples)
        seg = np.linspace(0, 1, len(pts))
        pts = np.stack([np.interp(t, seg, pts[:, k]) for k in range(3)], 1)
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    acr = np.asarray(across, float)
    out = []
    for p in pts:
        a, na = ray_hit(bvh, p + acr * half_w - d * 2.0, d)
        b, nb = ray_hit(bvh, p - acr * half_w - d * 2.0, d)
        n = na + nb
        out.append((a, b, n / np.linalg.norm(n)))
    return out


def lamp_parts(parts, bvh):
    """Straight lamp bars along the nose top edge and the vertical LED fangs at the corners (v2 language)."""
    for s in (1, -1):
        tag = 'L' if s < 0 else 'R'
        xs = np.linspace(0.36, 0.80, 9)
        guide = np.stack([s * xs, np.full(9, -0.212), np.full(9, -2.3)], 1)
        st = surface_strip(bvh, guide, 0.019, (0, -0.25, 1), across=(0, 1, 0))
        rings = [ring_box(a, b, n, 0.006, 0.02) for a, b, n in st]
        tube(parts, rings, strip_uv('lamp', len(rings)), f'headlight_{tag}')
        guide = np.array([[s * 0.888, -0.248, -2.3], [s * 0.874, -0.335, -2.3]])
        d = (-0.55 * s, 0.0, 1.0)
        st = surface_strip(bvh, guide, 0.009, d, across=(1, 0, 0), samples=5)
        rings = [ring_box(a, b, n, 0.006, 0.02) for a, b, n in st]
        tube(parts, rings, strip_uv('fang', len(rings)), f'fang_{tag}')


def blade_part(parts):
    """Full-width tail light blade on the flat Kamm face, ends turned down."""
    path = np.array([(-0.92, 0.02), (-0.92, 0.175), (0.92, 0.175), (0.92, 0.02)])
    hw, front, back = 0.02, TAIL_Z + 0.008, TAIL_Z - 0.01
    dense = [path[0]]
    for a, b in zip(path[:-1], path[1:]):
        k = max(1, int(math.ceil(np.linalg.norm(b - a) / 0.12)))
        dense += [a + (b - a) * (i / k) for i in range(1, k + 1)]
    dense = np.array(dense)
    L = len(dense)
    seg = np.diff(dense, axis=0)
    seg /= np.linalg.norm(seg, axis=1, keepdims=True)
    tang = np.zeros_like(dense)
    tang[0], tang[-1] = seg[0], seg[-1]
    tang[1:-1] = seg[:-1] + seg[1:]
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    perp = np.stack([-tang[:, 1], tang[:, 0]], 1)
    miter = np.ones(L)
    miter[1:-1] = 1 / np.maximum(0.5, (perp[1:-1] * np.stack([-seg[:-1, 1], seg[:-1, 0]], 1)).sum(1))
    rings = []
    for p, q, mt in zip(dense, perp, miter):
        a, b = p + q * hw * mt, p - q * hw * mt
        rings.append([(a[0], a[1], front), (b[0], b[1], front), (b[0], b[1], back), (a[0], a[1], back)])
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    u = arc / arc[-1]
    w = flat_uv('wall')

    def fuv(i, k):
        if k == 0:
            return list(decal_uv('tail', np.array([u[i], u[i], u[i + 1], u[i + 1]]), np.array([0, 1, 1, 0])))
        return [w] * 4
    tube(parts, rings, fuv, 'tail_blade')


def outlet_rims(parts):
    o = OUTLETS
    for s in (1, -1):
        cx = s * o['x']
        loop = rounded_polygon([(cx - o['hw'], o['y'] - o['hh']), (cx + o['hw'], o['y'] - o['hh']),
                                (cx + o['hw'], o['y'] + o['hh']), (cx - o['hw'], o['y'] + o['hh'])], o['r'])
        cen = np.array([cx, o['y']])
        rings = []
        for p in loop:
            nrm = (p - cen) / np.array([o['hw'], o['hh']]) ** 2
            nrm /= np.linalg.norm(nrm)
            q = p + nrm * 0.016
            rings.append([(q[0], q[1], TAIL_Z + 0.012), (p[0], p[1], TAIL_Z + 0.012), (p[0], p[1], TAIL_Z - 0.006),
                          (q[0], q[1], TAIL_Z - 0.006)])
        tube(parts, rings, solid_uv('metal'), f'outlet_rim_{"L" if s < 0 else "R"}', closed=True)


GILLS = [((-0.84, 0.045), (-0.50, 0.062)), ((-0.82, -0.025), (-0.53, -0.010)), ((-0.79, -0.095), (-0.56, -0.082))]


def gill_parts(parts, bvh):
    """Three stepped horizontal gills behind each front wheel (the v2 gills: black slot, teal top edge), raised on
    the flat side surface; no recess (a scallop behind the front wheel would be an 812 cue)."""
    for s in (1, -1):
        for k, ((z0, y0), (z1, y1)) in enumerate(GILLS):
            n = 7
            t = np.linspace(0, 1, n)
            hw = 0.011 * np.interp(t, [0, 0.15, 1], [0.55, 1, 1])
            st = []
            for z, y, w in zip(z0 + (z1 - z0) * t, y0 + (y1 - y0) * t, hw):
                a, na = ray_hit(bvh, (s * 2.0, y + w, z), (-s, 0, 0))
                b, nb = ray_hit(bvh, (s * 2.0, y - w, z), (-s, 0, 0))
                nn = na + nb
                st.append((a, b, nn / np.linalg.norm(nn)))
            rings = [ring_box(a, b, nn, 0.005, 0.015) for a, b, nn in st]
            tube(parts, rings, strip_uv('gill', len(rings), wall='black'), f'gill{k}_{"L" if s < 0 else "R"}',
                 cap='black')


def splitter_part(parts):
    prof = rounded_polygon([(-0.70, -1.94), (0.70, -1.94), (0.70, -2.075), (-0.70, -2.075)], 0.06, 5)
    prof = prof[::-1] if _area2(prof) < 0 else prof
    V, F = prism(prof, -0.605, -0.585, lambda u, v, a: (u, a, v))
    P = np.asarray(V)
    U = []
    for f in F:
        q = P[list(f)]
        n = np.cross(q[1] - q[0], q[2] - q[0])
        n = n / max(np.linalg.norm(n), 1e-12)
        U.append([flat_uv('teal' if n[2] < -0.6 and len(f) == 4 else 'black')] * len(f))
    parts.add(V, F, U, 'splitter')


def _area2(p):
    p = np.asarray(p)
    return float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def fin_parts(parts, bvh):
    for x in (-0.52, -0.20, 0.20, 0.52):
        rings = []
        for z in np.linspace(1.86, TAIL_Z - 0.006, 7):
            hit, _ = ray_hit(bvh, (x, -1.5, z), (0, 1, 0))
            top, bot = hit[1] + 0.012, max(-0.565, hit[1] - 0.075)
            if top - bot < 0.025:
                continue
            rings.append([(x - 0.006, top, z), (x + 0.006, top, z), (x + 0.006, bot, z), (x - 0.006, bot, z)])
        tube(parts, rings, solid_uv('black'), f'fin_{x:+.2f}', cap='black')


def superellipsoid(c, r, e=0.4, nu=8, nv=16):
    """Closed rounded box (poles on +-Y): returns V, F."""
    V = [(c[0], c[1] - r[1], c[2])]
    for i in range(1, nu):
        th = -math.pi / 2 + math.pi * i / nu
        ct, stt = math.cos(th), math.sin(th)
        for j in range(nv):
            ph = 2 * math.pi * j / nv
            cp, sp = math.cos(ph), math.sin(ph)
            f = lambda a: math.copysign(abs(a) ** e, a)
            V.append((c[0] + r[0] * f(ct) * f(cp), c[1] + r[1] * f(stt), c[2] + r[2] * f(ct) * f(sp)))
    V.append((c[0], c[1] + r[1], c[2]))
    top = len(V) - 1
    F = [(0, 1 + (j + 1) % nv, 1 + j) for j in range(nv)]
    for i in range(nu - 2):
        a, b = 1 + i * nv, 1 + (i + 1) * nv
        F += [(a + j, a + (j + 1) % nv, b + (j + 1) % nv, b + j) for j in range(nv)]
    a = 1 + (nu - 2) * nv
    F += [(a + j, a + (j + 1) % nv, top) for j in range(nv)]
    return V, fix_winding(V, F)


def mirror_parts(parts):
    for s in (1, -1):
        V, F = superellipsoid((s * 1.0, 0.30, -0.80), (0.052, 0.034, 0.085))
        P = np.asarray(V)
        U = []
        cen = np.array((s * 1.0, 0.30, -0.80))
        for f in F:
            n = P[list(f)].mean(0) - cen
            n = n / np.array((0.052, 0.034, 0.085)) ** 2
            n /= np.linalg.norm(n)
            U.append([flat_uv('mirror' if n[2] > 0.75 else 'paint')] * len(f))
        parts.add(V, F, U, f'mirror_{"L" if s < 0 else "R"}')
        a, b = np.array((s * 0.88, 0.25, -0.80)), np.array((s * 0.97, 0.29, -0.80))
        rings = []
        for p in (a, b):
            rings.append([p + (0, 0.01, -0.018), p + (0, 0.01, 0.018), p + (0, -0.01, 0.018),
                          p + (0, -0.01, -0.018)])
        tube(parts, rings, solid_uv('black'), f'mirror_arm_{"L" if s < 0 else "R"}', cap='black')


def emblem_part(parts, bvh, centre, direction, size, name, nb=32, rings=2):
    """The MP capsule emblem (v2 decal) as a closed raised badge conformed to the surface."""
    hl, r = 0.29, 0.21
    ang = np.linspace(0, 2 * np.pi, nb, endpoint=False)
    outline = np.array([((hl if math.cos(a) >= 0 else -hl) + r * math.cos(a), r * math.sin(a)) for a in ang])
    pts = [np.zeros(2)] + [p * (k / rings) for k in range(1, rings + 1) for p in outline]
    pts = np.array(pts)
    d = np.asarray(direction, float)
    d /= np.linalg.norm(d)
    e1 = np.cross((0, 1, 0), -d) if abs(d[1]) < 0.9 else np.array((1.0, 0, 0))
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(-d, e1)
    top, bot = [], []
    for p in pts:
        o = np.asarray(centre) + e1 * p[0] * size + e2 * p[1] * size - d * 2.0
        h, n = ray_hit(bvh, o, d)
        top.append(h + n * 0.003)
        bot.append(h - n * 0.006)
    V = top + bot
    nt = len(top)
    uvs_top = decal_uv('emblem', pts[:, 0] + 0.5, 0.5 - pts[:, 1] * 2, inset=0.0)
    F, U = [], []
    for i in range(nb):
        F.append((0, 1 + i, 1 + (i + 1) % nb))
        U.append([uvs_top[0], uvs_top[1 + i], uvs_top[1 + (i + 1) % nb]])
    for k in range(1, rings):
        b0, b1 = 1 + (k - 1) * nb, 1 + k * nb
        for i in range(nb):
            i2 = (i + 1) % nb
            F.append((b0 + i, b1 + i, b1 + i2, b0 + i2))
            U.append([uvs_top[b0 + i], uvs_top[b1 + i], uvs_top[b1 + i2], uvs_top[b0 + i2]])
    w = flat_uv('wall')
    ob = 1 + (rings - 1) * nb
    for i in range(nb):
        i2 = (i + 1) % nb
        F.append((ob + i2, ob + i, nt + ob + i, nt + ob + i2))
        U.append([w] * 4)
    for i in range(nb):
        F.append((nt, nt + ob + (i + 1) % nb, nt + ob + i))
        U.append([w] * 3)
    # the bottom is a fan over the outer ring only (inner bottom rings are not needed for a closed solid)
    keep = list(range(nt)) + [nt] + list(range(nt + ob, 2 * nt))
    remap = {v: k for k, v in enumerate(keep)}
    parts.add([V[v] for v in keep], [tuple(remap[v] for v in f) for f in F], U, name)


def build_parts(P, T):
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([tuple(map(float, p)) for p in P], [tuple(map(int, t)) for t in T])
    parts = Parts()
    lamp_parts(parts, bvh)
    blade_part(parts)
    outlet_rims(parts)
    gill_parts(parts, bvh)
    splitter_part(parts)
    fin_parts(parts, bvh)
    mirror_parts(parts)
    emblem_part(parts, bvh, (0.0, -0.212, -2.3), (0, -0.25, 1), 0.105, 'emblem_nose')
    emblem_part(parts, bvh, (0.0, 0.06, TAIL_Z + 1.0), (0, 0, -1), 0.12, 'emblem_tail')
    return parts


# ------------------------------------------------------------------------------------------------ normals --
def smooth_normals(P, T, angle_deg=32.0):
    """Per-corner normals (m, 3, 3): angle-weighted, smooth across corners whose faces differ by < angle."""
    tp = P[T]
    fn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
    ln = np.linalg.norm(fn, axis=1)
    fu = np.where(ln[:, None] > 1e-14, fn / np.maximum(ln, 1e-30)[:, None], 0.0)
    w = np.zeros((len(T), 3))
    for k in range(3):
        a = tp[:, (k + 1) % 3] - tp[:, k]
        b = tp[:, (k + 2) % 3] - tp[:, k]
        c = np.einsum('ij,ij->i', a, b) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-30)
        w[:, k] = np.arccos(np.clip(c, -1, 1))
    w[ln <= 1e-14] = 0.0
    corners = T.ravel()
    order = np.argsort(corners, kind='stable')
    vs = corners[order]
    nv = int(T.max()) + 1
    starts = np.searchsorted(vs, np.arange(nv + 1))
    deg = np.diff(starts)
    dd = deg * deg
    tot = int(dd.sum())
    vrep = np.repeat(np.arange(nv), dd)
    base = np.repeat(np.cumsum(dd) - dd, dd)
    loc = np.arange(tot) - base
    drep = deg[vrep]
    c1 = order[starts[vrep] + loc // drep]
    c2 = order[starts[vrep] + loc % drep]
    t1, t2 = c1 // 3, c2 // 3
    ok = np.einsum('ij,ij->i', fu[t1], fu[t2]) >= math.cos(math.radians(angle_deg))
    acc = np.zeros((len(T) * 3, 3))
    np.add.at(acc, c1[ok], fu[t2[ok]] * w.ravel()[c2[ok]][:, None])
    nrm = acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-30)
    bad = np.linalg.norm(acc, axis=1) < 1e-20
    nrm[bad] = np.repeat(fu, 3, axis=0)[bad]
    return nrm.reshape(-1, 3, 3)


# ------------------------------------------------------------------------------------------------- the atlas --
PROJ = {'side': 0, 'side_in': 1, 'top': 2, 'front': 3, 'rear': 4, 'under': 5}
GUTTER = 3


def skin_projection(P, T):
    tp = P[T]
    fn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
    fn = np.round(fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-30), 6)
    ax, ay, az = np.abs(fn).T
    cx = tp[:, :, 0].mean(1)
    outward = fn[:, 0] * np.where(cx < 0, -1.0, 1.0) >= 0
    proj = np.where(ay >= np.maximum(ax, az), np.where(fn[:, 1] > 0, PROJ['top'], PROJ['under']),
                    np.where(ax >= az, np.where(outward, PROJ['side'], PROJ['side_in']),
                             np.where(fn[:, 2] < 0, PROJ['front'], PROJ['rear'])))
    return proj


def _proj2(p, kind):
    """3D points -> island coordinates (metres), u right, v down; |x| so both halves share texels."""
    x, y, z = np.abs(p[..., 0]), p[..., 1], p[..., 2]
    if kind in (PROJ['side'], PROJ['side_in']):
        return np.stack([z, -y], -1)
    if kind == PROJ['top']:
        return np.stack([z, x], -1)
    return np.stack([x, -y], -1)


def atlas_layout(P, T, proj, tag):
    """Places the islands (side, top / front, rear, side_in) in rows above DECAL_Y at one texel density.
    Returns {kind: (lo (2,), origin px (2,))} and the density (px per metre)."""
    ext = {}
    for kind in (PROJ['side'], PROJ['top'], PROJ['front'], PROJ['rear'], PROJ['side_in']):
        m = (proj == kind) & (tag == TAG['skin'])
        if not m.any():
            continue
        q = _proj2(P[T[m]], kind).reshape(-1, 2)
        ext[kind] = (q.min(0), q.max(0) - q.min(0))
    small = [k for k in (PROJ['front'], PROJ['rear'], PROJ['side_in']) if k in ext]
    layouts = [[[PROJ['side']], [PROJ['top']], small],
               [[PROJ['side']], [PROJ['top']], small[:2], small[2:]],
               [[PROJ['side']], [PROJ['top']], small[:1] + small[2:], small[1:2]]]

    def fits(rows, d):
        h = GUTTER
        for row in rows:
            if not row:
                continue
            if sum(ext[k][1][0] * d + 2 * GUTTER for k in row) > ATLAS:
                return False
            h += max(ext[k][1][1] for k in row) * d + 2 * GUTTER
        return h <= DECAL_Y
    best = None
    for rows in layouts:
        for d10 in range(2400, 1000, -5):
            if fits(rows, d10 / 10.0):
                if best is None or d10 > best[0]:
                    best = (d10, rows)
                break
    d, rows = best[0] / 10.0, best[1]
    place = {}
    y = GUTTER
    for row in rows:
        if not row:
            continue
        x = GUTTER
        for kind in row:
            place[kind] = (ext[kind][0], np.array([x, y], float))
            x += ext[kind][1][0] * d + 2 * GUTTER
        y += max(ext[k][1][1] for k in row) * d + 2 * GUTTER
    return place, d


def skin_uvs(P, T, proj, tag, place, d):
    uv = np.zeros((len(T), 3, 2))
    flat = {TAG['tub']: 'dark', TAG['scoop']: 'dark', TAG['outlet']: 'dark'}
    for t, name in flat.items():
        uv[tag == t] = flat_uv(name)
    for kind, (lo, org) in place.items():
        m = (proj == kind) & (tag == TAG['skin'])
        if kind == PROJ['side']:
            m |= (proj == kind) & (tag == TAG['scoop'])         # the intake's back wall gets a mesh grille
        q = _proj2(P[T[m]], kind)
        uv[m] = ((q - lo) * d + org) / ATLAS
    uv[(tag == TAG['skin']) & (proj == PROJ['under'])] = flat_uv('under')
    return uv


# ------------------------------------------------------------------------------------------------ the texture --
PAINTS = {                   # suffix -> (name, rgb); v2's paint colours
    '': ('midnight blue', (34, 52, 112)),
    '_red': ('red', (213, 9, 35)),
    '_white': ('white', (226, 228, 230)),
}
COL = {'glass_lo': (13, 17, 25), 'glass_hi': (56, 68, 88), 'black': (15, 15, 17), 'sill': (22, 22, 25),
       'under': (26, 26, 28), 'dark': (11, 11, 13), 'grille': (17, 18, 21), 'slat': (44, 46, 51),
       'teal': (0, 168, 170)}
K_PAINT, K_GLASS, K_FIXED = 0, 1, 2


def raster(uvt, W=ATLAS, H=ATLAS):
    """Per texel: triangle index (-1 = none) and barycentric weights (texel centre inside the UV triangle)."""
    Tid = -np.ones((H, W), np.int64)
    B = np.zeros((H, W, 3))
    t = uvt * (W, H)
    for k in range(len(t)):
        (x0, y0), (x1, y1), (x2, y2) = t[k]
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-9:
            continue
        lx, hx = int(max(0, math.floor(min(x0, x1, x2) - 0.5))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        ly, hy = int(max(0, math.floor(min(y0, y1, y2) - 0.5))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if hx < lx or hy < ly:
            continue
        xs, ys = np.meshgrid(np.arange(lx, hx + 1) + 0.5, np.arange(ly, hy + 1) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
        c = 1 - a - b
        ins = (a >= -0.02) & (b >= -0.02) & (c >= -0.02)
        if not ins.any():
            continue
        ii, jj = np.nonzero(ins)
        Tid[ii + ly, jj + lx] = k
        B[ii + ly, jj + lx] = np.stack([a[ins], b[ins], c[ins]], 1)
    return Tid, B


def _line(dist, half=0.0045):
    return np.abs(dist) < half


def _gap_shade(dist, half=0.0045):
    """Soft panel gap: 0.32 on the line, 1.0 at half-width (anti-aliased over about two texels)."""
    return np.clip(0.32 + 0.68 * (np.abs(dist) / half) ** 2, 0.32, 1.0)


def classify(P, N, S, C, tg):
    """Texel paint plan from 3D position P, normal N and cage parameters S (ring) / C (column).
    Returns kind (paint / glass / fixed colour), fixed rgb, shade (paint multiplier) and the glass gradient."""
    n = len(P)
    x, y, z = P.T
    ax = np.abs(x)
    kind = np.full(n, K_PAINT)
    rgb = np.zeros((n, 3))
    shade = np.ones(n)
    glass_g = np.zeros(n)

    def fixed(m, name):
        kind[m] = K_FIXED
        rgb[m] = COL[name]
    scoop = tg == TAG['scoop']
    nose = (S < -1e-3) & ~scoop
    tail = (S > len(RINGS) - 1 - 1e-4) & (z > TAIL_Z - 0.004) & ~scoop
    body = ~nose & ~tail & ~scoop
    fixed(scoop, 'grille')                          # side intake: dark mesh, diamond pattern
    fixed(scoop & ((((z + y) * 36) % 1 < 0.16) | (((z - y) * 36) % 1 < 0.16)), 'slat')
    # underside and black sills (the lower bumper and the diffuser sides too)
    fixed(body & (C < 1.0), 'under')
    fixed(body & (C >= 1.0) & (C < 3.0), 'sill')
    fixed(body & (C >= 3.0) & (C < 3.03) & (S > 5.3) & (S < 11.0), 'teal')
    # canopy: windscreen, side glass, rear window (glass); roof and A-pillars (black)
    side_glass = body & (C >= 6.03) & (C < 8.0) & (S >= 5.15) & (S <= 9.45)
    screen = body & (C >= 8.0) & (S >= 5.0) & (S <= 7.0)
    rear_glass = body & (C >= 9.0) & (S > 9.05) & (S <= 9.97)
    roof = body & (C >= 7.85) & (S > 7.0) & (S <= 9.05)
    pillar = body & (C >= 7.75) & (C < 8.2) & (S >= 5.0) & (S <= 7.0)
    cpillar = body & (C >= 8.0) & (C < 9.0) & (S > 9.05) & (S <= 9.5)
    glass = side_glass | screen | rear_glass
    kind[glass] = K_GLASS
    glass_g[glass] = np.clip((y[glass] - 0.20) / 0.42, 0, 1) ** 1.6
    streak = screen & (np.abs((z + 0.9 * x) - (-0.55)) < 0.06)
    glass_g[streak] = np.maximum(glass_g[streak], 0.55)
    fixed(roof | pillar | cpillar, 'black')
    # two long vents in the engine cover between the buttresses, and the front-deck vents (top camera)
    deck = body & (z > 0.5) & (N[:, 1] > 0.6)
    vent = deck & (ax > 0.16) & (ax < 0.40) & (z > 0.62) & (z < 1.62)
    fixed(vent & ~(((ax - 0.16) % 0.06) < 0.016), 'dark')       # four long slots per vent, along the car
    fvent = body & (ax > 0.10) & (ax < 0.36) & (z > -1.66) & (z < -1.30) & (N[:, 1] > 0.6)
    fixed(fvent & (((z + 1.66) % 0.072) < 0.024), 'dark')
    # panel gaps (doors, front lid, engine lid, tail shut line): soft lines, distance to the nearest shut line
    top = N[:, 1] > 0.45
    dgap = np.ones(n)

    def gapline(mask, d):
        dgap[mask] = np.minimum(dgap[mask], np.abs(d[mask]))
    sidef = (np.abs(N[:, 0]) > 0.5) & (C >= 3.0) & (C < 6.0) & body & (y < 0.24) & (y > -0.47)
    gapline(sidef, z - (-0.42 + 0.06 * (y + 0.47)))
    gapline(sidef, z - 0.43)
    flid = body & top & (S < 5.0)
    gapline(flid & (z > -2.05) & (z < -1.16), ax - 0.60)
    gapline(flid & (ax < 0.60), z + 1.16)
    gapline(flid & (ax < 0.60), z + 2.05)
    rlid = body & top & (S > 10.0)
    gapline(rlid & (z > 0.50) & (z < 1.85), ax - 0.50)
    gapline(rlid & (ax < 0.50), z - 1.85)
    gapline(tail, y + 0.10)
    # nose: grille mouth with slats; black lip below it
    mouth = nose & (ax < 0.56) & (y > -0.345) & (y < -0.262)
    fixed(mouth, 'grille')
    fixed(mouth & (((y + 0.345) % 0.0205) < 0.006), 'slat')
    fixed(nose & (y < -0.355), 'sill')
    # tail: black lower panel (diffuser zone) with a shut line
    fixed(tail & (y < -0.14), 'sill')
    pm = kind == K_PAINT
    shade[pm] *= _gap_shade(dgap[pm])
    # soft shading in the paint: lower body, round the wheel arches
    shade *= 1.0 - 0.16 * np.clip((-0.28 - y) / 0.25, 0, 1)
    for zc, yc, r, _ in TUBS.values():
        dd = np.hypot(z - zc, y - yc) - r
        near = (dd > 0) & (dd < 0.05) & (ax > 0.9)
        shade[near] *= 0.78 + 0.22 * dd[near] / 0.05
    return kind, rgb, shade, glass_g


def smoothstep(e0, e1, t):
    t = np.clip((t - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# MP emblem (Midnight Pattaya), the v2 decal: same shapes and colours as tools/gpu/car_debrand.py emblem_rgba
NAVY = np.array((22, 30, 62), float)
SILVER = np.array((206, 210, 220), float)
GLYPH = np.array(((-0.27, -0.13), (-0.135, 0.15), (0.0, -0.05), (0.135, 0.15), (0.27, -0.13)))


def _seg_dist(x, y, a, b):
    px, py = x - a[0], y - a[1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - t * dx, py - t * dy)


def emblem_rgba(x, y, aa):
    d_out = _seg_dist(x, y, (-0.29, 0.0), (0.29, 0.0)) - 0.21
    gl, stroke, rim = GLYPH * (0.9, 0.62), 0.032, 0.045
    glyph = np.min([_seg_dist(x, y, gl[i], gl[i + 1]) for i in range(len(gl) - 1)], 0) - stroke

    def cov(d):
        return np.clip(0.5 - d / max(aa, 1e-4), 0, 1)
    a_all = cov(d_out)
    field = cov(d_out + rim)
    col = SILVER[None] * (1 - field[:, None]) + NAVY[None] * field[:, None]
    g = (cov(glyph) * field)[:, None]
    col = col * (1 - g) + SILVER[None] * g
    return col, a_all


def draw_decals(img, paint):
    def region(name):
        x0, y0, x1, y1 = DECALS[name]
        ys, xs = np.mgrid[y0:y1, x0:x1]
        return (slice(y0, y1), slice(x0, x1)), (xs + 0.5 - x0) / (x1 - x0), (ys + 0.5 - y0) / (y1 - y0)
    pr = np.asarray(paint, float)
    # lamp bar: smoked housing, LED line on top, two square projectors, teal accent line at the bottom (v2 graphic)
    sl, u, v = region('lamp')
    W = DECALS['lamp'][2] - DECALS['lamp'][0]
    H_ = DECALS['lamp'][3] - DECALS['lamp'][1]
    c = np.zeros(u.shape + (3,))
    c[:] = (22, 25, 32)
    c += (np.array((38, 40, 48)) * (1 - v)[..., None]) * 0.6
    led = np.exp(-((v - 0.14) / 0.055) ** 2)
    c = c * (1 - led[..., None]) + np.array((246, 250, 255)) * led[..., None]
    for uc in (0.30, 0.52):
        du = np.abs(u - uc) * W / H_
        dv = np.abs(v - 0.58)
        sq = np.maximum(du, dv)
        c[(sq < 0.24) & (sq > 0.17)] = (150, 156, 166)
        c[sq <= 0.17] = (60, 66, 80)
        c[np.hypot(du, dv) < 0.07] = (228, 236, 250)
    c[v > 0.88] = (0, 168, 170)
    img[sl] = c
    # fang: white LED with a grey frame
    sl, u, v = region('fang')
    core = smoothstep(0.2, 0.32, v) * (1 - smoothstep(0.68, 0.8, v))
    img[sl] = np.array((70, 74, 82.0)) * (1 - core[..., None]) + np.array((250, 252, 255.0)) * core[..., None]
    # tail blade: dark red lens, bright red core line, dark edges
    sl, u, v = region('tail')
    c = np.zeros(u.shape + (3,))
    c[:] = (60, 6, 10)
    core = np.exp(-((v - 0.5) / 0.16) ** 2)
    c = c * (1 - core[..., None]) + np.array((255, 40, 44)) * core[..., None]
    c[(v < 0.17) | (v > 0.83)] = (24, 22, 24)
    img[sl] = c
    # gill: black slot with a teal top edge
    sl, u, v = region('gill')
    c = np.zeros(u.shape + (3,))
    c[:] = (12, 12, 14)
    c[v < 0.22] = COL['teal']
    c[(v >= 0.22) & (v < 0.4)] = (36, 38, 42)
    img[sl] = c
    sl, u, v = region('metal')
    img[sl] = np.array((95, 98, 104.0)) + np.array((90, 90, 92.0)) * np.exp(-((v - 0.5) / 0.3) ** 2)[..., None]
    for name, col in (('black', COL['black']), ('wall', (28, 29, 32)), ('paint', pr), ('teal', COL['teal']),
                      ('mirror', (34, 40, 52)), ('dark', COL['dark']), ('under', COL['under'])):
        sl, u, v = region(name)
        img[sl] = col
    sl, u, v = region('grille')
    img[sl] = COL['grille']
    # emblem: the MP capsule on the paint colour (the anti-aliased rim blends into the paint)
    sl, u, v = region('emblem')
    cw = DECALS['emblem'][2] - DECALS['emblem'][0]
    col, a = emblem_rgba((u - 0.5).ravel(), ((0.5 - v) * 0.5).ravel(), 1.2 / cw)
    a = a.reshape(u.shape)[..., None]
    img[sl] = col.reshape(u.shape + (3,)) * a + pr[None, None] * (1 - a)
    return img


def pad_gutters(img, M, steps=6):
    cover = M.copy()
    out = img.copy()
    for _ in range(steps):
        acc = np.zeros_like(out)
        cnt = np.zeros(M.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            s = np.roll(np.roll(cover, dy, 0), dx, 1)
            acc += np.roll(np.roll(out, dy, 0), dx, 1) * s[..., None]
            cnt += s
        g = (cnt > 0) & ~cover
        out[g] = acc[g] / cnt[g][:, None]
        cover |= g
    return out


def texture_plan(P, T, nrm, prm, uv, sel, tag):
    """Rasterises the body islands once: per texel the paint plan (kind, rgb, shade, glass gradient) + coverage."""
    Tid, B = raster(uv[sel])
    M = Tid >= 0
    idx = np.nonzero(sel)[0][Tid[M]]
    w = np.clip(B[M], 0, None)
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    Pt = (w[:, :, None] * P[T[idx]]).sum(1)
    Nt = (w[:, :, None] * nrm[idx]).sum(1)
    Nt /= np.maximum(np.linalg.norm(Nt, axis=1, keepdims=True), 1e-12)
    St = (w * prm[idx, :, 0]).sum(1)
    Ct = (w * prm[idx, :, 1]).sum(1)
    kind, rgb, shade, gg = classify(Pt, Nt, St, Ct, tag[idx])
    return {'M': M, 'kind': kind, 'rgb': rgb, 'shade': shade, 'glass': gg,
            'stats': {'texels_body': int(M.sum()), 'glass': int((kind == K_GLASS).sum()),
                      'paint': int((kind == K_PAINT).sum()), 'fixed': int((kind == K_FIXED).sum())}}


def texture(plan, paint):
    img = np.zeros((ATLAS, ATLAS, 3))
    M = plan['M']
    col = plan['rgb'].copy()
    k = plan['kind']
    col[k == K_PAINT] = np.asarray(paint, float)[None] * plan['shade'][k == K_PAINT][:, None]
    g = plan['glass'][k == K_GLASS][:, None]
    col[k == K_GLASS] = np.asarray(COL['glass_lo'], float) * (1 - g) + np.asarray(COL['glass_hi'], float) * g
    img[M] = col
    img = pad_gutters(img, M, 6)
    img = draw_decals(img, paint)
    return np.clip(np.round(img), 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------------------------- PNG and GLB writers --
def png_bytes(img):
    """RGB uint8 image -> PNG (Sub filter on every row, zlib level 9): deterministic, no metadata."""
    H, W, _ = img.shape
    a = img.astype(np.int16)
    sub = a.reshape(H, W * 3).copy()
    sub[:, 3:] = (a.reshape(H, W * 3)[:, 3:] - a.reshape(H, W * 3)[:, :-3]) % 256
    raw = np.concatenate([np.ones((H, 1), np.uint8), sub.astype(np.uint8)], 1).tobytes()

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def glb_write(path, name, pos, nrm, uv, idx, png, mat_name):
    """One node, one mesh, one primitive, one material with an embedded PNG base colour."""
    pos = np.ascontiguousarray(pos, np.float32)
    nrm = np.ascontiguousarray(nrm, np.float32)
    uv = np.ascontiguousarray(uv, np.float32)
    ib = np.ascontiguousarray(idx, np.uint32).ravel()
    parts = [pos.tobytes(), nrm.tobytes(), uv.tobytes(), ib.tobytes(), png]
    views, binc = [], bytearray()
    for i, p in enumerate(parts):
        binc += b'\0' * ((-len(binc)) % 4)
        v = {'buffer': 0, 'byteOffset': len(binc), 'byteLength': len(p)}
        if i < 3:
            v['target'] = 34962
        elif i == 3:
            v['target'] = 34963
        views.append(v)
        binc += p
    binc += b'\0' * ((-len(binc)) % 4)
    js = {'asset': {'version': '2.0', 'generator': GENERATOR}, 'scene': 0, 'scenes': [{'nodes': [0]}],
          'nodes': [{'name': name, 'mesh': 0}],
          'meshes': [{'name': name, 'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2},
                                                    'indices': 3, 'material': 0}]}],
          'accessors': [
              {'bufferView': 0, 'componentType': 5126, 'count': len(pos), 'type': 'VEC3',
               'min': [float(v) for v in pos.min(0)], 'max': [float(v) for v in pos.max(0)]},
              {'bufferView': 1, 'componentType': 5126, 'count': len(nrm), 'type': 'VEC3'},
              {'bufferView': 2, 'componentType': 5126, 'count': len(uv), 'type': 'VEC2'},
              {'bufferView': 3, 'componentType': 5125, 'count': len(ib), 'type': 'SCALAR'}],
          'materials': [{'name': mat_name, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0},
                                                                     'metallicFactor': 0.0, 'roughnessFactor': 0.5}}],
          'textures': [{'sampler': 0, 'source': 0}], 'samplers': [{'magFilter': 9729, 'minFilter': 9987}],
          'images': [{'name': mat_name + '_basecolor', 'mimeType': 'image/png', 'bufferView': 4}],
          'bufferViews': views, 'buffers': [{'byteLength': len(binc)}]}
    jb = json.dumps(js, separators=(',', ':'), sort_keys=True).encode()
    jb += b' ' * ((-len(jb)) % 4)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(jb) + 8 + len(binc)))
        f.write(struct.pack('<II', len(jb), 0x4E4F534A) + jb)
        f.write(struct.pack('<II', len(binc), 0x004E4942) + bytes(binc))


def vertex_buffers(P, T, nrm, uv):
    """Unique (position, normal, uv) per corner -> vertex arrays + indices (deterministic order)."""
    corner = np.concatenate([P[T].reshape(-1, 3), nrm.reshape(-1, 3), uv.reshape(-1, 2)], 1)
    key = np.concatenate([np.round(corner[:, :3] * 1e6), np.round(corner[:, 3:6] * 1e5),
                          np.round(corner[:, 6:] * 1e7)], 1).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    v = corner[first]
    tri = inv.reshape(-1, 3)
    # a triangle whose corners weld into one vertex is a zero-area sliver (collinear points on a merged flat face):
    # drop it, as importers do (Blender's glTF importer removes them)
    ok = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
    return v[:, :3], v[:, 3:6], v[:, 6:], tri[ok], ok


def write_json(path, obj):
    """JSON with LF line endings on every OS (the build output must not depend on the machine)."""
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=1)
        f.write('\n')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------------- build --
def transform_object(ob, centre, zscale):
    me = ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    co = (co.reshape(-1, 3) - centre) * (1.0, 1.0, zscale)
    me.vertices.foreach_set('co', co.ravel())
    me.update()


def build_geometry():
    """Subdivided body -> parts on it -> centre on the bounding box (exact length) -> booleans at the layout."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sub = subdivided_body()
    P0, T0, _, _ = body_arrays(sub)
    parts = build_parts(P0, T0)
    pP, pT, pUV, pG = parts.arrays()
    allp = np.concatenate([P0, pP])
    lo, hi = allp.min(0), allp.max(0)
    centre = (lo + hi) / 2
    centre[0] = 0.0                                 # mirror-symmetric by construction
    zscale = LENGTH / float(hi[2] - lo[2])
    raw = {'bbox_min': [round(float(v), 5) for v in lo], 'bbox_max': [round(float(v), 5) for v in hi],
           'centre_shift_m': [round(float(v), 5) for v in centre], 'z_scale': round(zscale, 6)}
    transform_object(sub, centre, zscale)
    pP = (pP - centre) * (1.0, 1.0, zscale)
    body = cut_body(sub)
    P, T, prm, tag = body_arrays(body)
    return P, T, prm, tag, pP, pT, pUV, pG, parts.log, raw


def build(out_dir, cid=CID):
    os.makedirs(out_dir, exist_ok=True)
    P, T, prm, tag, pP, pT, pUV, pG, plog, raw = build_geometry()
    n_body = len(T)
    # normals: the body, then each part on its own
    nb = smooth_normals(P, T)
    npart = np.zeros((len(pT), 3, 3))
    for g in np.unique(pG):
        m = pG == g
        vids = np.unique(pT[m])
        remap = -np.ones(len(pP), np.int64)
        remap[vids] = np.arange(len(vids))
        npart[m] = smooth_normals(pP[vids], remap[pT[m]])
    proj = skin_projection(P, T)
    place, dens = atlas_layout(P, T, proj, tag)
    uvb = skin_uvs(P, T, proj, tag, place, dens)
    sel = ((tag == TAG['skin']) & (proj != PROJ['under'])) | ((tag == TAG['scoop']) & (proj == PROJ['side']))
    plan = texture_plan(P, T, nb, prm, uvb, sel, tag)
    allP = np.concatenate([P, pP])
    allT = np.concatenate([T, pT + len(P)])
    allN = np.concatenate([nb, npart])
    allUV = np.concatenate([uvb, pUV])
    vp, vn, vu, vi, kept = vertex_buffers(allP, allT, allN, allUV)
    lo, hi = vp.min(0), vp.max(0)
    report = {'id': cid, 'generator': GENERATOR, 'upload': UPLOAD,
              'script_sha256': sha256_file(os.path.abspath(__file__)),
              'blender': bpy.app.version_string,
              'method': 'control cage (RINGS) -> Catmull-Clark x2 with creases -> exact booleans (tubs, side '
                        'intakes, exhaust pockets) -> closed parts -> own UVs and procedural texture -> own GLB',
              'cage': {'rings': len(RINGS), 'points_per_half_section': NCOL, 'subdivision_levels': 2},
              'raw_bbox_before_centring': raw,
              'bbox': {'min': [round(float(v), 5) for v in lo], 'max': [round(float(v), 5) for v in hi],
                       'size': [round(float(v), 5) for v in hi - lo],
                       'centre': [round(float(v), 6) for v in (lo + hi) / 2]},
              'tris': {'body_shell': int(kept[:n_body].sum()), 'parts': int(kept[n_body:].sum()), 'total': int(len(vi)),
                       'welded_slivers_dropped': int(len(allT) - len(vi))},
              'vertices': int(len(vp)),
              'parts': plog,
              'atlas': {'size': ATLAS, 'density_px_per_m': dens, 'decal_rows': ATLAS - DECAL_Y,
                        'islands': {k: [int(v) for v in np.round(place[PROJ[k]][1])] for k in PROJ if PROJ[k] in place},
                        'mirrored_halves': True, **plan['stats']},
              'tubs': {k: {'centre_zy': [v[0], v[1]], 'radius': v[2], 'inner_x': v[3]} for k, v in TUBS.items()},
              'paints': {}}
    outputs = {}
    for suffix, (pname, rgb) in PAINTS.items():
        img = texture(plan, rgb)
        png = png_bytes(img)
        name = cid + suffix
        path = os.path.join(out_dir, name + '.glb')
        glb_write(path, name, vp, vn, vu, vi, png, name + '_paint')
        outputs[suffix or 'default'] = {'paint': pname, 'rgb': list(rgb), 'body': name + '.glb'}
        report['paints'][pname] = {'file': name + '.glb', 'bytes': os.path.getsize(path), 'sha256': sha256_file(path),
                                   'texture_png_bytes': len(png)}
        if not suffix:
            x0, y0, x1, y1 = DECALS['emblem']
            crop = np.repeat(np.repeat(img[y0:y1, x0:x1], 2, 0), 2, 1)
            with open(os.path.join(out_dir, f'{cid}_emblem.png'), 'wb') as f:
                f.write(png_bytes(crop))
    report['outputs'] = outputs
    write_json(os.path.join(out_dir, f'{cid}_build.json'), report)
    print(json.dumps({k: report[k] for k in ('raw_bbox_before_centring', 'bbox', 'tris', 'atlas')}, indent=1))
    return report


def wheels_json(out_dir, v2_dir, cid=CID):
    """Layout for the game / Studio snippet: red_sports' numbers, the v2 wheels used as they are."""
    lay = json.load(open(os.path.join(v2_dir, f'{V2_ID}_wheels.json')))
    rep = json.load(open(os.path.join(out_dir, f'{cid}_build.json')))
    out = {'size': rep['bbox']['size'], 'radius': lay['radius'], 'width': lay['width'], 'rim': lay['rim'],
           'wheels': lay['wheels'], 'per_wheel': lay['per_wheel'], 'wheel_meshes': lay['wheel_meshes'],
           'front': '-Z', 'units': 'metres, body space (centre of the body mesh bounding box)',
           'own_v3': {'design': 'own body, modelled from scratch in tools/blender/car_own_v3.py',
                      'wheels': 'the v2 turbine wheels (red_sports_original_v2_wheel_*.glb), used as they are',
                      'paints': rep['outputs'], 'emblem': 'MP (Midnight Pattaya), own design (v2 decal)',
                      'upload': UPLOAD}}
    write_json(os.path.join(out_dir, f'{cid}_wheels.json'), out)
    return out


# ------------------------------------------------------------------------------------------- renders, FBX --
def n2b(v):
    return Vector((v[0], -v[2], v[1]))


def import_glb(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    obs = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    ob = obs[0]
    ob.name = name
    ob.parent = None
    ob.rotation_mode = 'XYZ'                 # the glTF importer uses quaternions: switch, so steering works
    ob.rotation_euler = (0, 0, 0)
    return ob


# Game chase camera (MidnightCamera.client.luau): 17 studs behind, 6 up, aim 2.6 up, FOV 70; 3.554 studs per metre
CHASE = {'dist': 17 / 3.554, 'height': 6.0 / 3.554, 'look': 2.6 / 3.554, 'fov': 70.0}
VIEWS = [
    {'name': 'side', 'az': -90, 'el': 0}, {'name': 'front34', 'az': -140, 'el': 16},
    {'name': 'rear34', 'az': 40, 'el': 16},
    {'name': 'front', 'az': 180, 'el': 4}, {'name': 'rear', 'az': 0, 'el': 4}, {'name': 'top', 'az': 0, 'el': 90},
]


def setup_scene(car_dir, body_glb, wheels_json_path, engine, res, aspect, steer=0.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    lay = json.load(open(wheels_json_path))
    objs = [import_glb(os.path.join(car_dir, body_glb), 'body')]
    for k in ('FL', 'FR', 'RL', 'RR'):
        w = import_glb(os.path.join(car_dir, lay['wheel_meshes'][k]), 'w_' + k)
        w.location = n2b(lay['wheels'][k])
        if k[0] == 'F' and steer:                 # front wheels turned about the vertical axis (Blender Z)
            w.rotation_euler = (0, 0, math.radians(steer))
        objs.append(w)
    sc = bpy.context.scene
    sc.render.resolution_x = res
    sc.render.resolution_y = int(res * aspect)
    sc.view_settings.view_transform = 'Standard'
    sc.world = bpy.data.worlds.new('w')
    if engine == 'WORKBENCH':
        sc.render.engine = 'BLENDER_WORKBENCH'
        sc.display.shading.light = 'STUDIO'
        sc.display.shading.color_type = 'TEXTURE'
        sc.display.shading.show_backface_culling = True
        sc.world.color = (0.82, 0.84, 0.88)
    else:                                       # EEVEE (GPU) or Cycles on the CPU: sky, sun, ground
        if engine == 'CYCLES':
            sc.render.engine = 'CYCLES'
            sc.cycles.device = 'CPU'
            sc.cycles.samples = 48
            sc.cycles.use_denoising = True
            sc.cycles.max_bounces = 6
        else:
            sc.render.engine = 'BLENDER_EEVEE'
        sc.world.use_nodes = True
        bg = sc.world.node_tree.nodes['Background']
        bg.inputs[0].default_value = (0.62, 0.68, 0.78, 1)
        bg.inputs[1].default_value = 0.9
        sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
        sun.data.energy = 3.2
        sun.data.angle = math.radians(4)
        sun.rotation_euler = (math.radians(42), math.radians(8), math.radians(35))
        sc.collection.objects.link(sun)
        g = bpy.data.meshes.new('ground')
        gy = -0.71
        g.from_pydata([(-30, -30, gy), (30, -30, gy), (30, 30, gy), (-30, 30, gy)], [], [(0, 1, 2, 3)])
        gm = bpy.data.materials.new('ground')
        gm.diffuse_color = (0.42, 0.43, 0.45, 1)
        gm.use_nodes = True
        gm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.36, 0.37, 0.39, 1)
        gm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.9
        g.materials.append(gm)
        go = bpy.data.objects.new('ground', g)
        sc.collection.objects.link(go)
        for o in objs:
            for s in o.material_slots:
                if s.material and s.material.use_nodes:
                    p = s.material.node_tree.nodes.get('Principled BSDF')
                    if p:
                        p.inputs['Roughness'].default_value = 0.35 if o.name == 'body' else 0.6
                        if 'Specular IOR Level' in p.inputs:
                            p.inputs['Specular IOR Level'].default_value = 0.5
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.clip_start = 0.01
    bpy.context.view_layer.update()
    pts = np.concatenate([np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices]) for o in objs])
    return sc, cam, Vector(pts.min(0)), Vector(pts.max(0))


def render_views(car_dir, cid, out_dir, tag, views=None, engine='WORKBENCH', res=900, aspect=0.62,
                 wheels_json_path=None, steer=0.0):
    from mathutils import Matrix
    os.makedirs(out_dir, exist_ok=True)
    wj = wheels_json_path or os.path.join(car_dir, f'{cid}_wheels.json')
    sc, cam, lo, hi = setup_scene(car_dir, f'{cid}.glb', wj, engine, res, aspect, steer)
    centre, size = (lo + hi) / 2, (hi - lo).length
    for v in views or VIEWS:
        if v.get('chase'):
            yaw = math.radians(v.get('yaw', 0))
            back = Vector((math.sin(yaw), -math.cos(yaw), 0))             # behind the car (Blender -Y is the rear)
            eye = Vector((0, 0, 0)) + back * CHASE['dist'] + Vector((0, 0, CHASE['height']))
            aim = Vector((0, 0, CHASE['look']))
            d = (eye - aim).normalized()
            cam.data.type = 'PERSP'
            cam.data.sensor_fit = 'VERTICAL'
            cam.data.angle_y = math.radians(CHASE['fov'])
            cam.location = eye
            cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        elif 'az' in v:
            a, e = math.radians(v['az']), math.radians(v['el'])
            d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.data.type = 'ORTHO'
            cam.data.sensor_fit = 'AUTO'
            cam.location = centre + d * size * 3
            cam.data.ortho_scale = size * v.get('scale', 1.0)
            cam.data.clip_end = size * 10
            if v['el'] >= 89.99:
                cam.matrix_world = Matrix.Translation(cam.location) @ Matrix(((0, 1, 0, 0), (-1, 0, 0, 0),
                                                                               (0, 0, 1, 0), (0, 0, 0, 1)))
            else:
                cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        else:
            d = n2b(v['dir']).normalized()
            cam.data.type = 'PERSP'
            cam.data.sensor_fit = 'AUTO'
            cam.data.lens = v.get('lens', 50)
            cam.location = n2b(v['target']) + d * v.get('dist', 0.8)
            cam.data.clip_end = 100
            cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(out_dir, f'{cid}_{tag}_{v["name"]}.png')
        bpy.ops.render.render(write_still=True)
        print('wrote', sc.render.filepath)


def fbx(car_dir, cid=CID):
    """One FBX per body GLB (the wheels are v2's and already have FBX files): -Z forward, Y up, origin kept."""
    report = {}
    for suffix in PAINTS:
        f = f'{cid}{suffix}.glb'
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(car_dir, f))
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
        out = os.path.join(car_dir, f[:-4] + '.fbx')
        bpy.ops.export_scene.fbx(filepath=out, use_selection=False, object_types={'MESH'}, path_mode='COPY',
                                 embed_textures=True, axis_forward='-Z', axis_up='Y', apply_unit_scale=True,
                                 mesh_smooth_type='FACE', add_leaf_bones=False, bake_anim=False)
        report[os.path.basename(out)] = {'tris': len(me.loop_triangles),
                                         'bbox_centre_blender': [round(v, 4) for v in (lo + hi) / 2],
                                         'bbox_size_blender': [round(v, 4) for v in hi - lo],
                                         'bytes': os.path.getsize(out)}
    write_json(os.path.join(car_dir, f'{cid}_fbx.json'), report)
    print(json.dumps(report, indent=1))


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    here = os.path.dirname(os.path.abspath(__file__))
    v2_dir = opt('--v2-dir', os.path.join(here, '..', '..', 'art', 'cars3d', 'roblox'))
    cmd = argv[0]
    if cmd == 'build':
        build(argv[1])
        wheels_json(argv[1], v2_dir)
    elif cmd == 'preview':                     # build into <dir>, then quick Workbench views of the default paint
        build(argv[1])
        wheels_json(argv[1], v2_dir)
        for name in os.listdir(v2_dir):
            if name.startswith(V2_ID + '_wheel_') and name.endswith('.glb'):
                import shutil
                shutil.copyfile(os.path.join(v2_dir, name), os.path.join(argv[1], name))
        views = VIEWS + [{'name': 'chase', 'chase': True}] + [
            {'name': n, 'target': t, 'dir': d, 'dist': s} for n, t, d, s in PREVIEW_CLOSEUPS]
        render_views(argv[1], CID, argv[1], 'pv', views, opt('--engine', 'WORKBENCH').upper(),
                     int(opt('--res', 700)))
    elif cmd == 'render':   # <car_dir> <id> <out_dir> <tag> [--views json] [--engine e] [--wheels json] [--steer deg]
        views = json.load(open(opt('--views'))) if opt('--views') else VIEWS
        render_views(argv[1], argv[2], argv[3], argv[4], views, opt('--engine', 'WORKBENCH').upper(),
                     int(opt('--res', 900)), float(opt('--aspect', 0.62)), opt('--wheels'),
                     float(opt('--steer', 0.0)))
    elif cmd == 'fbx':
        fbx(argv[1])
    else:
        sys.exit(__doc__)


PREVIEW_CLOSEUPS = [  # name, target (frame N), direction to the camera, distance
    ('arch_f', (-1.0, -0.1, -1.29), (-1.0, 0.25, -0.35), 2.2),
    ('nose', (0.0, -0.25, -2.2), (-0.35, 0.3, -1.0), 2.4),
    ('tail', (0.0, 0.0, 2.25), (0.35, 0.3, 1.0), 2.6),
    ('scoop', (-1.05, -0.03, 0.72), (-1.0, 0.2, 0.2), 1.6),
    ('gills', (-1.06, -0.01, -0.67), (-1.0, 0.25, -0.35), 1.3),
]


if __name__ == '__main__' and bpy is not None:
    main(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
