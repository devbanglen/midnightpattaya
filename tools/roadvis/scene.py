"""Export the 'before' (current built data) and 'after' (pilot) states of the area as triangle scenes for Blender.

Each scene is JSON: {origin: [cx, cz], objects: [{name, color [r, g, b] 0..255, verts [[x, y, z]...], faces [[i, j, k]...]}],
cameras: {...}}. Coordinates are Roblox studs relative to the area centre (x east, y up, z south); blender_preview.py
maps them to Blender (X = x, Y = -z, Z = y). Everything is an extruded footprint (top face + side walls) or a flat
decal (markings), so the preview shows exactly the footprints and heights the builders make. PREVIEW ONLY.
"""
import json
import math
import os
import zlib

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from tools.roadvis import world

PAL = {
    'asphalt': (46, 47, 52), 'sidewalk': (170, 168, 160), 'corner': (150, 148, 142), 'shoulder': (92, 91, 88),
    'kerb': (205, 203, 196), 'island': (160, 158, 150), 'grass': (86, 120, 62), 'terrain': (126, 118, 104),
    'lane': (235, 235, 235), 'centre': (245, 200, 40), 'edge': (235, 235, 235), 'stop': (245, 245, 245), 'zebra': (245, 245, 245),
}
BLD = [(232, 224, 200), (214, 205, 186), (226, 206, 198), (180, 196, 214), (198, 210, 222), (236, 230, 214)]


class Mesh:
    def __init__(self, name, color):
        self.name, self.color, self.v, self.f = name, color, [], []

    def tri(self, a, b, c):
        n = len(self.v)
        self.v += [a, b, c]
        self.f.append([n, n + 1, n + 2])

    def quad(self, a, b, c, d):
        n = len(self.v)
        self.v += [a, b, c, d]
        self.f += [[n, n + 1, n + 2], [n, n + 2, n + 3]]

    def extrude(self, poly, top, bottom, o, walls=True):
        """top face (constrained Delaunay) at `top`, side walls down to `bottom`"""
        cx, cz = o
        for p in _polys(poly):
            if p.area < 0.01:
                continue
            tri = shapely.constrained_delaunay_triangles(p)
            for t in getattr(tri, 'geoms', []):
                c = np.asarray(t.exterior.coords)[:3]
                # Roblox x / z, viewed from above with y up: counter-clockwise in (x, -z) faces up
                pts = [(float(x - cx), float(top), float(z - cz)) for x, z in c]
                a, b, cc = c
                cross = (b[0] - a[0]) * (-(cc[1] - a[1])) - (-(b[1] - a[1])) * (cc[0] - a[0])
                self.tri(*(pts if cross > 0 else pts[::-1]))
            if walls and top - bottom > 0.02:
                for ring in [p.exterior] + list(p.interiors):
                    r = np.asarray(ring.coords)
                    for i in range(len(r) - 1):
                        (x1, z1), (x2, z2) = r[i], r[i + 1]
                        self.quad((x1 - cx, bottom, z1 - cz), (x2 - cx, bottom, z2 - cz), (x2 - cx, top, z2 - cz), (x1 - cx, top, z1 - cz))

    def out(self):
        return dict(name=self.name, color=list(self.color), verts=[[round(a, 2), round(b, 3), round(c, 2)] for a, b, c in self.v], faces=self.f)


def _polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for q in getattr(g, 'geoms', []) for p in _polys(q)]


def cameras(o):
    """Roblox-world camera specs -> local (relative to the area centre). fov = vertical degrees."""
    cx, cz = o

    def L(x, y, z):
        return [x - world.ORIGIN[0] - cx, y, z - cz]
    return {
        # the owner's screenshot camera (Studio edit mode, 2026-10-21 04:59): same position, direction, FOV and aspect
        'owner_view': dict(pos=L(24609.8, 115.9, 713.3), dir=[-0.386, -0.386, 0.837], fov=70, res=[1831, 1074]),
        'aerial': dict(pos=L(24820.0, 340.0, 1300.0), look=L(24520.0, 0.0, 930.0), fov=50, res=[1600, 1000]),
        # a pedestrian (eye 6 studs over the sidewalk top) on the east kerb of Sukhumvit, looking at the junction
        'street': dict(pos=L(24540.0, 7.6, 1040.0), look=L(24470.0, 4.0, 960.0), fov=60, res=[1600, 1000]),
        # a chase camera 8 studs up behind a car in the northbound carriageway (709043297, the west one: Thailand drives
        # on the left), looking up the road into the junction
        'driver': dict(pos=L(24396.0, 9.0, 1262.0), look=L(24445.0, 2.0, 1110.0), fov=65, res=[1600, 1000]),
    }


def context(W, area, o, meshes):
    """terrain + buildings around the area (both scenes)"""
    T = Mesh('terrain', PAL['terrain'])
    T.extrude(area.buffer(700, join_style='mitre'), -2.0, -2.0, o, walls=False)
    meshes.append(T)
    bm = [Mesh(f'buildings_{i}', c) for i, c in enumerate(BLD)]
    for b in W['blds']:
        if b['poly'].intersects(area.buffer(650)):
            bm[b['id'] % len(BLD)].extrude(b['poly'], b['h'], 0.0, o)
    meshes += bm


def before_scene(W, area, o):
    meshes = []
    context(W, area, o, meshes)
    m = {k: Mesh(k, PAL[k]) for k in ('asphalt', 'sidewalk', 'corner', 'shoulder')}
    near = area.buffer(650)
    for s in W['surf']:
        if not s['poly'].intersects(near):
            continue
        k = s['kind']
        tgt = 'asphalt' if k in world.ROAD_KINDS else 'shoulder' if k in world.SHOULDER_KINDS else k
        if tgt in m:
            m[tgt].extrude(s['poly'], s['top'], -3.0, o)
    meshes += m.values()
    mk = {k: Mesh('mark_' + k, PAL[k]) for k in ('lane', 'centre', 'zebra')}
    for x in W['marks']:
        if x['poly'].intersects(near):
            mk[x['kind']].extrude(x['poly'], 1.05, 1.05, o, walls=False)
    for c in W['crossings']:
        for b in c['bars']:
            if b.intersects(near):
                mk['zebra'].extrude(b, 1.07, 1.07, o, walls=False)
    meshes += mk.values()
    return meshes


def after_scene(W, P, area, o, shoulder_color=None):
    """outside the area: the kept old geometry (exactly as before); inside: the pilot. Shoulders stay everywhere."""
    meshes = []
    context(W, area, o, meshes)
    near = area.buffer(650)
    rep = {id(s) for s in P['replaced']}
    m = {k: Mesh(k, PAL[k]) for k in ('asphalt', 'sidewalk', 'corner', 'shoulder')}
    if shoulder_color:
        m['shoulder'].color = shoulder_color
    for s in W['surf']:
        if not s['poly'].intersects(near) or id(s) in rep:
            continue
        k = s['kind']
        tgt = 'asphalt' if k in world.ROAD_KINDS else 'shoulder' if k in world.SHOULDER_KINDS else k
        if tgt in m:
            m[tgt].extrude(s['poly'], s['top'], -3.0, o)
    cfg = P['cfg']
    lift = cfg['visual_lift']
    m['asphalt'].extrude(P['S'], cfg['asphalt_top'] + lift, -3.0, o)
    m['sidewalk'].extrude(P['walk'], cfg['sidewalk_top'], -3.0, o)
    kerb = Mesh('kerb', PAL['kerb'])
    kerb.extrude(P['kerb'], cfg['sidewalk_top'] + 0.004, cfg['sidewalk_top'] + 0.004, o, walls=False)
    isl = Mesh('island', PAL['island'])
    isl.extrude(P['islands'], cfg['island_top'], -3.0, o)
    grass = Mesh('grass', PAL['grass'])
    grass.extrude(P['green'], cfg['island_top'] + 0.004, cfg['island_top'] + 0.004, o, walls=False)
    meshes += list(m.values()) + [kerb, isl, grass]
    mk = {k: Mesh('mark_' + k, PAL[k]) for k in ('lane', 'centre', 'edge', 'stop', 'zebra')}
    for x in W['marks']:                                    # old markings outside the area stay
        if x['poly'].intersects(near) and not area.contains(x['poly'].centroid):
            mk[x['kind']].extrude(x['poly'], 1.05, 1.05, o, walls=False)
    for c in W['crossings']:
        if not area.contains(Point(c['row'][0], c['row'][1])):
            for b in c['bars']:
                if b.intersects(near):
                    mk['zebra'].extrude(b, 1.07, 1.07, o, walls=False)
    for x in P['marks']:
        mk[x['kind']].extrude(x['poly'], cfg['asphalt_top'] + lift + 0.03, 0, o, walls=False)
    meshes += mk.values()
    return meshes


def export(W, pilots, out_dir):
    """pilots: {'A': P, 'B': P}; writes scene_before.json and scene_<design>.json with the shoulder pieces in today's
    colour (Build never touches ShoulderChunks), plus scene_B_look.json: design B with the opt-in ShoulderLook (the
    shoulder pieces recoloured as a concrete gutter, kerb grey; reverted by ShoulderLookRevert)."""
    P0 = next(iter(pilots.values()))
    area = P0['area']
    c = area.centroid
    o = (round(c.x, 1), round(c.y, 1))
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    states = [('before', before_scene(W, area, o))]
    for d, P in pilots.items():
        states.append((d, after_scene(W, P, area, o)))
    if 'B' in pilots:
        states.append(('B_look', after_scene(W, pilots['B'], area, o, shoulder_color=(176, 174, 168))))
    for name, ms in states:
        data = dict(note='PREVIEW ONLY (offline render input, tools/roadvis/scene.py)', origin=list(o),
                    objects=[x.out() for x in ms if x.f], cameras=cameras(o))
        p = os.path.join(out_dir, f'scene_{name}.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
        paths[name] = p
    return paths
