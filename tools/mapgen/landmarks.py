"""Landmark proxies for MIDNIGHT PATTAYA: recognisable Pattaya landmarks as handcrafted low-poly Part models.

  .venv\\Scripts\\python tools\\mapgen\\landmarks.py tools\\mapgen\\config\\landmarks.json

Every landmark is placed from REAL OSM geometry (the way / node ids in the config, read from data/osm/raw): the
footprint polygon is projected with the city's projection (EPSG:32647, origin_utm of build/central_pattaya/graph_game.json,
x0.5 compression, 0.28 m per stud, z = -northing), so a proxy lands exactly where the roads put that place. The
shapes are stylised (RayCity-like, night-neon friendly) and generic: plain colours, Parts only, names as plain text on
a SurfaceGui (Gotham). No logos, no official artwork, no trademarked design.

Placement rules
- Footprint bodies start from the OSM polygon's minimum rotated rectangle and are shrunk side by side until they are
  `margin_studs` clear of every road slab, sidewalk, junction / joint disc (central AND wide datasets, read from the
  exported chunk modules exactly as tools/mapgen/road_check.py rebuilds them), every procedural building box that
  stays, and every street prop (palms, street lights, neon signs, job stands, the Walking Street gate).
- A procedural box that a proxy replaces is listed in the config (`replaces`); the manifest lists it with its dataset
  and chunk so PattayaLandmarksBuilder.RemoveReplaced() can delete it (the removeBaseConflicts pattern).
- Heights: OSM building:levels x level_studs + ground_floor_extra_studs (the buildings.py rule), the replaced box's
  own height when OSM has no levels, or a public real-world height in metres x the city's vertical studs per metre
  (vertical_scale / meters_per_stud), stated per landmark in the config.

Export-time check (asserted): the 2-D footprint (projected oriented box) of EVERY exported part, buffered by
`check_margin_studs`, touches no road slab, sidewalk strip, junction / joint disc, kept building box or street prop.

Output (build/landmarks/): roblox/manifest.luau + roblox/chunk_l<cx>_<cz>.luau (ServerStorage.PattayaDataLandmarks),
landmarks.json (summary), check/<id>.png (top-down check per landmark over the road layout).
Map data (c) OpenStreetMap contributors, ODbL 1.0.
"""
import json, math, os, sys
from collections import Counter, defaultdict
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, polylabel, unary_union
from shapely import affinity
from shapely.strtree import STRtree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import road_check as rc                      # read-only use: exported road geometry, rebuilt like PattayaBuilder

ATTRIBUTION = 'Map data © OpenStreetMap contributors, ODbL 1.0'
MATERIALS = ['SmoothPlastic', 'Wood', 'WoodPlanks', 'Concrete', 'Glass', 'Metal', 'Marble', 'Slate', 'Foil', 'Brick',
             'Granite', 'Plastic']
SHAPES = ['Block', 'Cylinder', 'Ball', 'Wedge']
F_COLLIDE, F_QUERY, F_SHADOW = 1, 2, 4

# ---- colours (original, generic) -------------------------------------------------------------------------------------
C = dict(
    teak=(120, 78, 44), teak_dark=(84, 52, 30), teak_light=(156, 108, 64), gold=(214, 172, 64), gold_dim=(170, 132, 50),
    amber=(255, 170, 60), white=(240, 240, 236), offwhite=(226, 222, 212), concrete=(150, 150, 146),
    dark=(28, 28, 34), charcoal=(48, 50, 58), steel=(120, 124, 132), glass=(96, 140, 170), glass_n=(150, 230, 255),
    pink=(255, 70, 190), cyan=(0, 220, 255), magenta=(220, 40, 160), red=(220, 40, 40), beacon=(255, 30, 30),
    naga=(48, 128, 76), stone=(178, 170, 156), water=(46, 118, 136), terracotta=(176, 74, 44), roof_red=(160, 40, 34),
    dolphin=(150, 170, 190), cream=(236, 220, 186), plum=(70, 30, 80), navy=(26, 34, 70), warm=(255, 214, 150),
    lime=(80, 255, 120), violet=(150, 90, 255), yellow=(255, 210, 50),
)
STALL = [C['red'], (230, 120, 30), (40, 120, 200), (40, 150, 90), (180, 50, 150)]
STALL_NEON = [C['pink'], C['cyan'], C['yellow'], C['violet'], C['lime']]


# ---- rotation matrices (Roblox conventions: right-handed, +Y up; CFrame.fromEulerAnglesYXZ(rx, ry, rz) = Ry Rx Rz) ---
def Ry(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def euler_yxz(R):
    """(rx, ry, rz) with R = Ry(ry) Rx(rx) Rz(rz)"""
    rx = math.asin(max(-1.0, min(1.0, -R[1, 2])))
    ry = math.atan2(R[0, 2], R[2, 2])
    rz = math.atan2(R[1, 0], R[1, 1])
    assert np.abs(Ry(ry) @ Rx(rx) @ Rz(rz) - R).max() < 1e-6, 'gimbal case not handled'
    return rx, ry, rz


class Frame:
    """a landmark's local frame: origin o (map-local x, z), local +X = u = (cos ang, sin ang), local +Z = v =
    (-sin ang, cos ang), +Y up. Roblox rotation of the frame = Ry(-ang). The FRONT of a box landmark is its -v side."""

    def __init__(self, ox, oz, ang):
        self.o = np.array([ox, oz], float)
        self.ang = ang
        self.u = np.array([math.cos(ang), math.sin(ang)])
        self.v = np.array([-math.sin(ang), math.cos(ang)])
        self.R = Ry(-ang)

    def w(self, lx, lz):
        return self.o + self.u * lx + self.v * lz

    def local(self, x, z):
        d = np.array([x, z]) - self.o
        return float(d @ self.u), float(d @ self.v)


def face_yaw(nx, nz):
    """local yaw whose part LookVector (Front face) points along local direction (nx, nz)"""
    return math.atan2(-nx, -nz)


class Model:
    def __init__(self, lid):
        self.id = lid
        self.parts = []          # dicts
        self.texts = []          # (part index, face, text, colour, font, stroke colour or None)

    def add(self, F, name, size, lx, y, lz, color, yaw=0.0, pitch=0.0, roll=0.0, mat='SmoothPlastic', shape='Block',
            collide=True, query=None, shadow=False, neon=None, transp=0.0):
        R = F.R @ Ry(yaw) @ Rx(pitch) @ Rz(roll)
        x, z = F.w(lx, lz)
        p = dict(name=name, size=tuple(float(s) for s in size), pos=(float(x), float(y), float(z)), R=R,
                 color=tuple(color), mat=mat, shape=shape, collide=collide,
                 query=collide if query is None else query, shadow=shadow, neon=tuple(neon) if neon else None, transp=transp)
        if neon:                                   # NightNeon parts must be SmoothPlastic (the client sets it by day)
            p['mat'] = 'SmoothPlastic'
        self.parts.append(p)
        return len(self.parts) - 1

    def box(self, F, name, w, d, y0, y1, lx, lz, color, **kw):
        return self.add(F, name, (w, y1 - y0, d), lx, (y0 + y1) / 2, lz, color, **kw)

    def vcyl(self, F, name, dia, y0, y1, lx, lz, color, **kw):
        """vertical cylinder (Roblox cylinders run along local X: roll 90 deg)"""
        return self.add(F, name, (y1 - y0, dia, dia), lx, (y0 + y1) / 2, lz, color, roll=math.pi / 2, shape='Cylinder', **kw)

    def text(self, idx, txt, color, face='Front', font='GothamBlack', stroke=None):
        self.texts.append((idx, face, txt, tuple(color), font, tuple(stroke) if stroke else None))

    def board(self, F, txt, w, h, lx, y, lz, nx, nz, bg, fg, stroke=None, neon_frame=None, name='NameBoard', depth=0.6):
        """a board whose Front face (and text) looks along local (nx, nz); optional neon frame (NightNeon strips)"""
        yaw = face_yaw(nx, nz)
        i = self.add(F, name, (w, h, depth), lx, y, lz, bg, yaw=yaw, collide=False)
        self.text(i, txt, fg, stroke=stroke)
        if neon_frame:
            ux, uz = -nz, nx                       # along the board, in the landmark frame
            for s in (-1, 1):
                self.add(F, 'LandmarkNeon', (w + 0.8, 0.4, depth + 0.2), lx, y + s * (h / 2 + 0.2), lz, neon_frame,
                         yaw=yaw, collide=False, neon=neon_frame)
                self.add(F, 'LandmarkNeon', (0.4, h, depth + 0.2), lx + ux * s * (w / 2 + 0.2), y,
                         lz + uz * s * (w / 2 + 0.2), neon_frame, yaw=yaw, collide=False, neon=neon_frame)
        return i


def footprint(p):
    """2-D (x, z) footprint: a vertical cylinder or a ball is a disc, anything else the hull of its 8 corners"""
    sx, sy, sz = p['size']
    if p['shape'] == 'Ball':
        return Point(p['pos'][0], p['pos'][2]).buffer(min(p['size']) / 2, 24)
    if p['shape'] == 'Cylinder' and abs(p['R'][1, 0]) > 0.9999:      # local X (the axis) is vertical
        return Point(p['pos'][0], p['pos'][2]).buffer(min(sy, sz) / 2, 24)
    corners = np.array([[a * sx / 2, b * sy / 2, c * sz / 2] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)])
    w = corners @ p['R'].T
    pts = [(p['pos'][0] + q[0], p['pos'][2] + q[2]) for q in w]
    hull = Polygon(pts).convex_hull
    return hull if hull.area > 1e-6 else Point(pts[0]).buffer(0.05)


# ---- world data ------------------------------------------------------------------------------------------------------
class World:
    def __init__(self, cfg):
        g = json.load(open(os.path.join(ROOT, cfg['graph']), encoding='utf-8'))
        self.origin = g['origin_utm']
        self.k = g['compression'] / g['meters_per_stud']
        self.mps, self.compression = g['meters_per_stud'], g['compression']
        self.tf = Transformer.from_crs('EPSG:4326', g['crs'], always_xy=True)
        self.vs = cfg['vertical_scale'] / g['meters_per_stud']          # vertical studs per real metre
        self.level = cfg['level_height_m'] * self.vs
        self.extra = cfg['ground_floor_extra_studs']
        self.osm, self.osm_base = {}, {}
        for path in cfg['raw']:
            raw = json.load(open(os.path.join(ROOT, path), encoding='utf-8'))
            self.osm_base[os.path.basename(path)] = raw.get('osm3s', {}).get('timestamp_osm_base')
            for e in raw['elements']:
                self.osm.setdefault((e['type'], e['id']), e)
        # roads (exported chunk modules, PattayaBuilder geometry), building boxes, street props
        self.roads, self.road_only, self.buildings = [], [], []
        for ds, d in cfg['datasets'].items():
            rdir = os.path.join(ROOT, d, 'roblox')
            edges, discs, jr = rc.load_dataset(rdir)
            for e in edges:
                for r in rc.stripe_rects(e['pts'], e['width']):
                    self.roads.append(('road', ds, e['id'], r))
                    self.road_only.append((e, r))
                for r in rc.sidewalk_rects(e, jr):
                    self.roads.append(('sidewalk', ds, e['id'], r))
            for kk, (x, z, r) in discs.items():
                self.roads.append(('joint' if isinstance(kk, tuple) else 'junction', ds, str(kk), Point(x, z).buffer(r, 24)))
            for f in sorted(os.listdir(rdir)):
                if f.startswith('chunk_') and f.endswith('.luau'):
                    src = open(os.path.join(rdir, f), encoding='utf-8').read()
                    i = src.find('buildings = {')
                    if i < 0:
                        continue
                    body = src[i + 13:src.index('}', i)]
                    v = [float(t) for t in body.split(',') if t.strip()]
                    for j in range(0, len(v), 8):
                        x, z, w, dd, h, yaw, pal, bid = v[j:j + 8]
                        r = Polygon([(-w / 2, -dd / 2), (w / 2, -dd / 2), (w / 2, dd / 2), (-w / 2, dd / 2)])
                        self.buildings.append(dict(ds=ds, chunk=f[6:-5], id=int(bid), h=h, x=x, z=z,
                                                   poly=affinity.translate(affinity.rotate(r, yaw), x, z)))
            lay = json.load(open(os.path.join(ROOT, d, 'layout.json'), encoding='utf-8'))
            props = []
            for p in lay.get('palms', []):
                props.append(('palm', Point(p['x'], p['z']).buffer(2.0, 8)))
            for p in lay.get('lights', []):     # pole + the 7-stud arm towards the road
                props.append(('light', LineString([(p['x'], p['z']), (p['x'] + p['dx'] * 7, p['z'] + p['dz'] * 7)]).buffer(1.2)))
            for p in lay.get('signs', []):
                tx, tz = -p['nz'], p['nx']
                props.append(('sign', LineString([(p['x'] - tx * p['w'] / 2, p['z'] - tz * p['w'] / 2),
                                                  (p['x'] + tx * p['w'] / 2, p['z'] + tz * p['w'] / 2)]).buffer(1.0)))
            for p in lay.get('job_stands', []):
                props.append(('job_stand', Point(p['x'], p['z']).buffer(12, 12)))
            for p in lay.get('landmarks', []):
                props.append(('gate', Point(p['x'], p['z']).buffer(p.get('span', 20) / 2 + 6, 12)))
            for kind, geom in props:
                self.roads.append((kind, ds, '', geom))
        self.rtree = STRtree([r[3] for r in self.roads])
        self.btree = STRtree([b['poly'] for b in self.buildings])
        self.rotree = STRtree([r for _, r in self.road_only])

    def P(self, lat, lon):
        x, y = self.tf.transform(lon, lat)
        return ((x - self.origin[0]) * self.k, -(y - self.origin[1]) * self.k)

    def way(self, wid):
        e = self.osm[('way', wid)]
        pts = [self.P(p['lat'], p['lon']) for p in e['geometry']]
        if len(pts) >= 4 and e['geometry'][0] == e['geometry'][-1]:
            return Polygon(pts).buffer(0)
        return LineString(pts)

    def node(self, nid):
        e = self.osm[('node', nid)]
        return Point(*self.P(e['lat'], e['lon']))

    def tags(self, kind, i):
        return self.osm[(kind, i)].get('tags', {})

    def levels_h(self, n):
        return n * self.level + self.extra

    def obstacles(self, area, keep_out=()):
        """union of everything a proxy must stay clear of near `area`: roads, sidewalks, discs, props, kept boxes"""
        geoms = [self.roads[i][3] for i in self.rtree.query(area)]
        geoms += [self.buildings[i]['poly'] for i in self.btree.query(area) if self.buildings[i]['id'] not in keep_out]
        return unary_union(geoms) if geoms else Polygon()

    def nearest_road_dir(self, x, z, maxd=800):
        """(unit vector from (x, z) to the nearest road slab, distance)"""
        p = Point(x, z)
        best = None
        for i in self.rotree.query(p.buffer(maxd)):
            d = self.road_only[i][1].distance(p)
            if best is None or d < best[0]:
                best = (d, i)
        if best is None:
            return None, None
        a, b = nearest_points(p, self.road_only[best[1]][1])
        v = np.array([b.x - a.x, b.y - a.y])
        n = np.linalg.norm(v)
        return (v / n if n > 1e-6 else np.array([0.0, -1.0])), best[0]


# ---- fitting ---------------------------------------------------------------------------------------------------------
def rect(F, u0, u1, v0, v1):
    return Polygon([F.w(u0, v0), F.w(u1, v0), F.w(u1, v1), F.w(u0, v1)])


def mrr_frame(poly):
    """frame at the minimum rotated rectangle of `poly` (long side = u) and its half extents"""
    m = poly.minimum_rotated_rectangle
    c = list(m.exterior.coords)[:4]
    e1, e2 = np.subtract(c[1], c[0]), np.subtract(c[2], c[1])
    if np.linalg.norm(e1) < np.linalg.norm(e2):
        e1, e2 = e2, e1
    cen = m.centroid
    return Frame(cen.x, cen.y, math.atan2(e1[1], e1[0])), np.linalg.norm(e1) / 2, np.linalg.norm(e2) / 2


def fit_rect(F, u0, u1, v0, v1, avoid, margin, min_side=6.0):
    """shrink the rectangle side by side until it is `margin` clear of `avoid`; None when it gets too small"""
    for _ in range(200):
        r = rect(F, u0, u1, v0, v1)
        hit = avoid.intersection(r.buffer(margin, join_style=2))
        if hit.is_empty or hit.area < 1e-4:
            return u0, u1, v0, v1
        pieces = [g for g in getattr(hit, 'geoms', [hit]) if g.geom_type == 'Polygon' and g.area > 1e-6]
        piece = max(pieces, key=lambda g: g.area)
        loc = np.array([F.local(x, z) for x, z in piece.exterior.coords])
        a0, a1, b0, b1 = loc[:, 0].min(), loc[:, 0].max(), loc[:, 1].min(), loc[:, 1].max()
        opts = []
        for side, val in (('u1', a0 - margin - 0.01), ('u0', a1 + margin + 0.01), ('v1', b0 - margin - 0.01),
                          ('v0', b1 + margin + 0.01)):
            nu0, nu1, nv0, nv1 = u0, u1, v0, v1
            if side == 'u1': nu1 = min(u1, val)
            if side == 'u0': nu0 = max(u0, val)
            if side == 'v1': nv1 = min(v1, val)
            if side == 'v0': nv0 = max(v0, val)
            if nu1 - nu0 >= min_side and nv1 - nv0 >= min_side:
                opts.append(((u1 - u0) * (v1 - v0) - (nu1 - nu0) * (nv1 - nv0), (nu0, nu1, nv0, nv1)))
        if not opts:
            return None
        u0, u1, v0, v1 = min(opts)[1]
    return None


def recenter(F, b):
    u0, u1, v0, v1 = b
    cx, cz = F.w((u0 + u1) / 2, (v0 + v1) / 2)
    return Frame(cx, cz, F.ang), (u1 - u0) / 2, (v1 - v0) / 2


def orient_front(W, F, hu, hv):
    """rotate the frame so the side nearest a road is the -v side (the front)"""
    best = None
    for rot, (lu, lv), swap in ((0.0, (0, -hv), False), (math.pi / 2, (hu, 0), True), (math.pi, (0, hv), False),
                                (-math.pi / 2, (-hu, 0), True)):
        _, d = W.nearest_road_dir(*F.w(lu, lv))
        score = d if d is not None else 1e9
        if best is None or score < best[0]:
            best = (score, rot, swap)
    _, rot, swap = best
    G = Frame(F.o[0], F.o[1], F.ang + rot)
    return (G, hv, hu) if swap else (G, hu, hv)


def fit_footprint(W, poly, keep_out, margin):
    F, hu, hv = mrr_frame(poly)
    avoid = W.obstacles(poly.buffer(40), keep_out=keep_out)
    b = fit_rect(F, -hu, hu, -hv, hv, avoid, margin)
    if b is None:
        raise RuntimeError('footprint does not fit')
    return recenter(F, b)


def fit_wings(W, poly, used, keep_out, margin, min_frac=0.12, max_wings=2):
    """extra boxes for the parts of an OSM footprint that the main box could not cover (a kept building or a road cuts
    into it): the minimum rotated rectangle of each big leftover piece, shrunk clear like the main box"""
    out = []
    avoid = W.obstacles(poly.buffer(40), keep_out=keep_out)
    for _ in range(max_wings):
        left = poly.difference(unary_union(used).buffer(margin + 1.0, join_style=2))
        pieces = sorted(getattr(left, 'geoms', [left]), key=lambda g: -g.area)
        added = False
        for piece in pieces:
            if piece.is_empty or piece.area < min_frac * used[0].area:
                break
            F, hu, hv = mrr_frame(piece)
            b = fit_rect(F, -hu, hu, -hv, hv, unary_union([avoid] + used), margin, min_side=14.0)
            if b is None:
                continue
            F, hu, hv = recenter(F, b)
            r = rect(F, -hu, hu, -hv, hv)
            if r.area < min_frac * used[0].area:
                continue
            out.append((F, hu, hv))
            used = used + [r]
            added = True
            break
        if not added:
            break
    return out


def strips(F, region, du, dv, ext):
    """cells du x dv (in frame F) fully inside `region`, merged along u -> [(u0, u1, v0, v1)]"""
    u0, u1, v0, v1 = ext
    out = []
    for j in range(int(math.floor(v0 / dv)), int(math.ceil(v1 / dv))):
        run = None
        for i in range(int(math.floor(u0 / du)), int(math.ceil(u1 / du)) + 1):
            if region.contains(rect(F, i * du, (i + 1) * du, j * dv, (j + 1) * dv)):
                run = (run[0], (i + 1) * du) if run else (i * du, (i + 1) * du)
            elif run:
                out.append((run[0], run[1], j * dv, (j + 1) * dv))
                run = None
        if run:
            out.append((run[0], run[1], j * dv, (j + 1) * dv))
    return out


# ---- generators: each returns (frame whose origin is the landmark anchor, info dict) ---------------------------------
def gen_theatre(W, L, M, cfg):
    poly = W.way(L['way'])
    F, hu, hv = orient_front(W, *fit_footprint(W, poly, set(L['replaces']), cfg['margin_studs']))
    old = [b for b in W.buildings if b['id'] in L['replaces']]
    h = max(b['h'] for b in old)                         # OSM has no levels: the replaced box's height
    pink = L.get('theme') == 'pink'
    wall = C['cream'] if pink else C['offwhite']
    accent = C['pink'] if pink else C['yellow']
    accent2 = C['cyan'] if pink else C['magenta']
    porch = min(12.0, hv * 0.35)
    M.box(F, 'TheatreBody', 2 * hu, 2 * hv - porch, -2.5, h, 0, porch / 2, wall, shadow=True)
    M.box(F, 'TheatreRoof', 2 * hu - 2, 2 * hv - porch - 2, h, h + 1.2, 0, porch / 2, C['charcoal'], collide=False)
    fw = 2 * hu * 0.86
    M.box(F, 'TheatreFacade', fw, 2.0, -2.5, h + 10, 0, -hv + porch + 1.0, wall, shadow=True)
    M.box(F, 'FacadeCrown', fw + 1, 2.4, h + 10, h + 11.5, 0, -hv + porch + 1.0, C['white'] if pink else C['gold'],
          collide=False)
    ncol = max(4, min(10, int(fw // 14)))
    for i in range(ncol):
        M.vcyl(F, 'Column', 3.0, -2.5, 17, -fw / 2 + 4 + i * (fw - 8) / (ncol - 1), -hv + 2.5, C['white'])
    M.box(F, 'PorchCanopy', fw, porch, 17, 18.5, 0, -hv + porch / 2, C['charcoal'], collide=False)
    M.box(F, 'MarqueeBulbs', fw, 0.5, 16.2, 17, 0, -hv + 0.35, accent, collide=False, neon=accent)
    bw = min(fw * 0.8, 70.0)
    M.board(F, L['label'], bw, 9, 0, 25, -hv + porch - 0.2, 0, -1, C['dark'], accent, stroke=accent2, neon_frame=accent2,
            name='Marquee', depth=1.0)
    M.box(F, 'RoofNeon', fw + 1, 0.5, h + 11.6, h + 12.1, 0, -hv + porch + 1.0, accent2, collide=False, neon=accent2)
    for s in (-1, 1):                                    # vertical neon blades at the facade corners
        M.box(F, 'BladeNeon', 1.0, 1.2, 4, h + 9, s * (fw / 2 - 0.6), -hv + porch - 0.2, accent, collide=False, neon=accent)
    return F, dict(w=2 * hu, d=2 * hv, h=h, height_rule='replaced procedural box height (OSM has no levels)')


def gen_mall(W, L, M, cfg):
    poly = W.way(L['way'])
    F, hu, hv = orient_front(W, *fit_footprint(W, poly, set(L['replaces']), cfg['margin_studs']))
    lv = int(W.tags('way', L['way'])['building:levels'])
    h = W.levels_h(lv)
    M.box(F, 'MallBody', 2 * hu - 1, 2 * hv - 1, -2.5, h, 0, 0, C['offwhite'], shadow=True)
    M.box(F, 'MallRoof', 2 * hu - 6, 2 * hv - 6, h, h + 1.5, 0, 0, C['concrete'], collide=False)
    for k in range(1, lv):                               # glass bands on all four faces: day glass, night pale cyan
        y = k * W.level + W.extra - 1.5
        for (lu, lz, w, d) in ((0, -hv + 0.25, 2 * hu - 2, 0.5), (0, hv - 0.25, 2 * hu - 2, 0.5),
                               (-hu + 0.25, 0, 0.5, 2 * hv - 2), (hu - 0.25, 0, 0.5, 2 * hv - 2)):
            M.box(F, 'GlassBand', w, d, y, y + 3.2, lu, lz, C['glass'], collide=False, neon=C['glass_n'])
    ew = min(2 * hu * 0.4, 60.0)
    M.box(F, 'EntranceCanopy', ew, 6, 13, 14.5, 0, -hv + 3, C['charcoal'], collide=False)
    M.box(F, 'EntranceGlow', ew, 0.6, 12.3, 13, 0, -hv + 0.6, C['warm'], collide=False, neon=C['warm'])
    bw = min(2 * hu * 0.7, 120.0)
    M.board(F, L['label'], bw, 14, 0, h + 9, -hv + 1.5, 0, -1, C['dark'], C['white'], stroke=C['cyan'],
            neon_frame=C['cyan'], name='RoofBoard', depth=1.0)
    for s in (-1, 1):
        M.box(F, 'BoardPost', 1.2, 1.2, h, h + 2.2, s * bw * 0.35, -hv + 2.6, C['steel'], collide=False)
    wings = fit_wings(W, poly, [rect(F, -hu, hu, -hv, hv)], set(L['replaces']), cfg['margin_studs'])
    for G, gu, gv in wings:                              # one level lower, same glass bands on the long faces
        wh = W.levels_h(lv - 1)
        M.box(G, 'MallWing', 2 * gu - 1, 2 * gv - 1, -2.5, wh, 0, 0, C['offwhite'], shadow=True)
        M.box(G, 'MallRoof', 2 * gu - 6, 2 * gv - 6, wh, wh + 1.5, 0, 0, C['concrete'], collide=False)
        for k in range(1, lv - 1):
            y = k * W.level + W.extra - 1.5
            for lz in (-gv + 0.25, gv - 0.25):
                M.box(G, 'GlassBand', 2 * gu - 2, 0.5, y, y + 3.2, 0, lz, C['glass'], collide=False, neon=C['glass_n'])
    return F, dict(w=2 * hu, d=2 * hv, h=h, levels=lv, wings=[f'{2 * a:.0f} x {2 * b:.0f}' for _, a, b in wings])


def gen_terminal(W, L, M, cfg):
    poly = W.way(L['way'])
    F, hu, hv = orient_front(W, *fit_footprint(W, poly, set(L['replaces']), cfg['margin_studs']))
    lv = int(W.tags('way', L['way'])['building:levels'])
    h = W.levels_h(lv)
    M.box(F, 'TerminalBody', 2 * hu - 1, 2 * hv - 1, -2.5, h, 0, 0, C['offwhite'], shadow=True)
    n = 5                                                # a generic vaulted roof: 5 pitched strips across the depth
    for i in range(n):
        t = (i + 0.5) / n * 2 - 1
        M.add(F, 'VaultRoof', (2 * hu - 3, 1.4, (2 * hv - 3) / n + 1.5), 0, h + 0.7 + 6 * (1 - t * t), t * (hv - 1.5),
              C['steel'], pitch=math.atan(12 * t / (hv - 1.5)), collide=False, mat='Metal')
    M.box(F, 'CurtainWall', 2 * hu - 6, 0.6, 2, h - 2, 0, -hv + 0.4, C['glass'], collide=False, neon=C['glass_n'])
    for k in range(1, lv):
        y = k * W.level + W.extra
        M.box(F, 'Mullion', 2 * hu - 6, 0.8, y - 0.4, y + 0.4, 0, -hv + 0.6, C['charcoal'], collide=False)
    tu, tv = hu - 10, hv * 0.3                           # a generic control-tower element (no real design copied)
    M.vcyl(F, 'TowerShaft', 7, h, h + 34, tu, tv, C['offwhite'])
    M.vcyl(F, 'TowerCab', 13, h + 34, h + 41, tu, tv, C['glass'], collide=False, neon=C['glass_n'])
    M.vcyl(F, 'TowerCap', 14, h + 41, h + 42.5, tu, tv, C['charcoal'], collide=False)
    M.box(F, 'TowerBeacon', 1.5, 1.5, h + 42.5, h + 45, tu, tv, C['beacon'], collide=False, neon=C['beacon'])
    bw = min(2 * hu * 0.5, 100.0)
    M.board(F, L['label'], bw, 11, -hu * 0.25, h - 7, -hv + 0.7, 0, -1, C['navy'], C['white'], stroke=C['cyan'],
            neon_frame=C['cyan'], name='NameBoard', depth=0.8)
    wings = fit_wings(W, poly, [rect(F, -hu, hu, -hv, hv)], set(L['replaces']), cfg['margin_studs'])
    for G, gu, gv in wings:
        M.box(G, 'TerminalWing', 2 * gu - 1, 2 * gv - 1, -2.5, h - W.level, 0, 0, C['offwhite'], shadow=True)
        M.box(G, 'WingRoof', 2 * gu - 4, 2 * gv - 4, h - W.level, h - W.level + 1.4, 0, 0, C['steel'], collide=False, mat='Metal')
        for lz in (-gv + 0.4, gv - 0.4):
            M.box(G, 'CurtainWall', 2 * gu - 6, 0.6, 2, h - W.level - 2, 0, lz, C['glass'], collide=False, neon=C['glass_n'])
    return F, dict(w=2 * hu, d=2 * hv, h=h, levels=lv, wings=[f'{2 * a:.0f} x {2 * b:.0f}' for _, a, b in wings])


def gen_sanctuary(W, L, M, cfg):
    poly = W.way(L['way'])
    F, hu, hv = orient_front(W, *fit_footprint(W, poly, set(L['replaces']), cfg['margin_studs']))
    H = L['height_m'] * W.vs
    s = min(hu, hv)
    M.box(F, 'Terrace', 2 * hu, 2 * hv, -2.5, 3, 0, 0, C['stone'], mat='Slate', shadow=True)
    M.box(F, 'Terrace', 2 * hu * 0.86, 2 * hv * 0.86, 3, 8, 0, 0, C['teak_dark'], mat='WoodPlanks', shadow=True)
    for sgn in (-1, 1):                                  # amber floodlit edge of the upper terrace (night)
        M.box(F, 'TerraceGlow', 2 * hu * 0.86, 0.5, 7.6, 8.1, 0, sgn * hv * 0.86, C['teak_light'], collide=False, neon=C['amber'])
        M.box(F, 'TerraceGlow', 0.5, 2 * hv * 0.86, 7.6, 8.1, sgn * hu * 0.86, 0, C['teak_light'], collide=False, neon=C['amber'])
    arm_w = 2 * s * 0.42
    wall_top = 8 + 0.12 * H
    for axis in (0, 1):                                  # the cross-shaped hall with stepped roofs
        ln = (2 * hu if axis == 0 else 2 * hv) * 0.8
        w, d = (ln, arm_w) if axis == 0 else (arm_w, ln)
        M.box(F, 'Hall', w, d, 8, wall_top, 0, 0, C['teak'], mat='Wood', shadow=True)
        for t, sc in enumerate((1.0, 0.72, 0.45)):
            y0 = wall_top + t * 7
            ww, dd = (ln * (1 - 0.08 * t), arm_w * sc) if axis == 0 else (arm_w * sc, ln * (1 - 0.08 * t))
            M.box(F, 'HallRoof', ww, dd, y0, y0 + 7, 0, 0, C['teak_dark'] if t % 2 == 0 else C['teak'], mat='Wood', shadow=True)
    base, tiers = wall_top + 21, 9                       # central prang: tiers alternating 0 / 45 deg
    for t in range(tiers):
        w = s * 0.62 * (1 - t / tiers) ** 1.15 + 3
        y0 = base + (H * 0.86 - base) * t / tiers
        y1 = base + (H * 0.86 - base) * (t + 1) / tiers
        M.add(F, 'Prang', (w, y1 - y0, w), 0, (y0 + y1) / 2, 0, C['teak'] if t % 2 == 0 else C['teak_dark'],
              yaw=(math.pi / 4 if t % 2 else 0), mat='Wood', shadow=True)
    M.vcyl(F, 'Finial', 2.0, H * 0.86, H, 0, 0, C['gold'], collide=False, neon=C['amber'])
    top = wall_top + 0.38 * H                            # four smaller prangs over the arm ends
    for lu, lz in ((hu * 0.62, 0), (-hu * 0.62, 0), (0, hv * 0.62), (0, -hv * 0.62)):
        for t in range(5):
            w = arm_w * 0.55 * (1 - t / 5) + 2
            y0 = wall_top + 14 + (top - wall_top - 14) * t / 5
            y1 = wall_top + 14 + (top - wall_top - 14) * (t + 1) / 5
            M.add(F, 'SidePrang', (w, y1 - y0, w), lu, (y0 + y1) / 2, lz, C['teak_dark'] if t % 2 == 0 else C['teak'],
                  yaw=(math.pi / 4 if t % 2 else 0), mat='Wood', collide=t == 0)
        M.vcyl(F, 'SideFinial', 1.2, top, top + 10, lu, lz, C['gold'], collide=False, neon=C['amber'])
    for (lu, lz, yaw) in ((hu * 0.8, 0, math.pi / 2), (-hu * 0.8, 0, math.pi / 2), (0, hv * 0.8, 0), (0, -hv * 0.8, 0)):
        for t in range(4):                               # stepped gable at each arm end (carved-front silhouette)
            w = arm_w * (1.0 - 0.22 * t)
            M.add(F, 'Gable', (w, 6, 1.6), lu, wall_top + 3 + t * 6, lz, C['teak_light'] if t % 2 == 0 else C['teak'],
                  yaw=yaw, mat='Wood', collide=False)
        M.add(F, 'GableGlow', (arm_w * 0.3, 0.5, 1.8), lu, wall_top + 26, lz, C['gold_dim'], yaw=yaw, collide=False,
              neon=C['amber'])
    for su in (-1, 1):                                   # small spired pavilions on the terrace corners
        for sv in (-1, 1):
            lu, lz = su * hu * 0.7, sv * hv * 0.7
            M.box(F, 'CornerPavilion', 9, 9, 8, 20, lu, lz, C['teak'], mat='Wood')
            for t in range(3):
                w = 8 - t * 2.4
                M.add(F, 'CornerSpire', (w, 6, w), lu, 23 + t * 6, lz, C['teak_dark'] if t % 2 == 0 else C['teak'],
                      yaw=(math.pi / 4 if t % 2 else 0), mat='Wood', collide=False)
            M.vcyl(F, 'CornerFinial', 0.8, 38, 46, lu, lz, C['gold'], collide=False)
    M.board(F, L['label'], min(2 * hu * 0.5, 54.0), 4.5, 0, 5.6, -hv * 0.86 - 0.35, 0, -1, C['teak_dark'], C['warm'],
            name='NameBoard', depth=0.5)
    return F, dict(w=2 * hu, d=2 * hv, h=H)


def gen_buddha(W, L, M, cfg):
    area = W.way(L['way'])
    steps = W.way(L['steps_way'])
    a, b = np.array(steps.coords[0]), np.array(steps.coords[-1])
    if Point(*a).distance(area) < Point(*b).distance(area):
        a, b = b, a                                      # b = the top of the stair (at the temple area)
    up = (b - a) / np.linalg.norm(b - a)
    across = np.array([-up[1], up[0]])
    avoid = W.obstacles(area.buffer(150))
    H = L['height_m'] * W.vs                             # statue height above the plinth
    plinth_top = 12.0
    best = None                                          # plinth disc inside the temple area, clear of everything
    for dist in np.arange(10, 90, 2):
        for lat in np.arange(-24, 25, 3):
            c = b + up * dist + across * lat
            p = Point(*c)
            if not area.buffer(4).contains(p):
                continue
            r = min(avoid.distance(p) - cfg['margin_studs'], 26.0)
            if r >= 16 and (best is None or r > best[0] + 0.5 or (abs(r - best[0]) <= 0.5 and dist < best[2])):
                best = (r, c, dist)
    r, c, _ = best
    ang = math.atan2(up[1], up[0])
    F = Frame(c[0], c[1], ang + math.pi / 2)            # v = up the stair: the front (-v) looks down the stair
    side = r * 2 / math.sqrt(2) * 0.98                   # octagon from two squares inscribed in the disc
    for yaw in (0, math.pi / 4):
        M.add(F, 'Plinth', (side, plinth_top + 2.5, side), 0, (plinth_top - 2.5) / 2, 0, C['stone'], yaw=yaw, mat='Marble', shadow=True)
        M.add(F, 'PlinthGlow', (side, 0.5, side), 0, plinth_top + 0.25, 0, C['gold_dim'], yaw=yaw, collide=False, neon=C['amber'])
    y = plinth_top + 0.5
    g = C['gold']

    def fig(name, w, h, d, ly, lz, lx=0.0, **kw):
        return M.add(F, name, (w, h, d), lx, ly, lz, g, shadow=True, **kw)
    M.vcyl(F, 'Lotus', min(0.78 * H, side * 0.95), y, y + 0.08 * H, 0, 0, C['gold_dim'])
    y += 0.08 * H
    fig('Legs', 0.64 * H, 0.17 * H, 0.42 * H, y + 0.085 * H, 0.02 * H)
    fig('Hands', 0.2 * H, 0.06 * H, 0.12 * H, y + 0.2 * H, -0.08 * H)
    fig('Torso', 0.34 * H, 0.38 * H, 0.22 * H, y + 0.36 * H, 0.06 * H)
    for sgn in (-1, 1):
        fig('Arm', 0.09 * H, 0.32 * H, 0.14 * H, y + 0.34 * H, 0.0, lx=sgn * 0.2 * H, roll=sgn * 0.12)
        fig('Ear', 0.03 * H, 0.1 * H, 0.05 * H, y + 0.64 * H, 0.06 * H, lx=sgn * 0.1 * H)
    fig('Neck', 0.1 * H, 0.06 * H, 0.1 * H, y + 0.58 * H, 0.06 * H)
    M.add(F, 'Head', (0.2 * H, 0.2 * H, 0.2 * H), 0, y + 0.7 * H, 0.06 * H, g, shape='Ball', shadow=True)
    M.add(F, 'Ushnisha', (0.09 * H, 0.09 * H, 0.09 * H), 0, y + 0.82 * H, 0.06 * H, g, shape='Ball', collide=False)
    M.vcyl(F, 'Flame', 0.03 * H, y + 0.85 * H, y + 0.95 * H, 0, 0.06 * H, g, collide=False, neon=C['amber'])
    # the stair along the OSM steps way, with naga balustrades; a step that would touch a road is left out
    ln = float(np.linalg.norm(b - a))
    sf = Frame(a[0], a[1], ang)                         # u = up the stair
    # extend the stair from the end of the OSM steps way to the plinth edge (inside the temple area)
    plinth_u = float((c - a) @ up) - r * 0.92
    top_u = max(ln, plinth_u)
    hw, rail = 5.0, 6.0
    n = max(6, int(top_u // 6))
    sm = 1.5                                             # stairs and rails keep the prop clearance, not the building one
    steps_ok = [i for i in range(n) if not rect(sf, i * top_u / n, (i + 1) * top_u / n, -hw, hw)
                .buffer(sm).intersects(avoid)]
    s0 = steps_ok[0] if steps_ok else n             # the stair starts at the first clear step (the foot is at a road)
    run = [i for i in steps_ok if i >= s0]
    for k, i in enumerate(run):
        M.box(sf, 'Step', top_u / n + 0.2, 2 * hw, -2.5, (k + 1) / len(run) * plinth_top, (i + 0.5) * top_u / n, 0, C['stone'],
              mat='Marble')
    kept = len(run)
    lo = s0 * top_u / n + 1.0
    pitch = math.atan2(plinth_top, top_u - lo)
    for sgn in (-1, 1):
        end = next((e for e in np.arange(top_u, lo + 12, -2.0) if not rect(sf, lo - 1.6, e, sgn * rail - 0.8, sgn * rail + 0.8)
                    .buffer(sm).intersects(avoid)), None)
        if end is None:
            continue
        mid = (lo + end) / 2                             # naga body rising with the stair (as far as it is clear)
        M.add(sf, 'NagaRail', ((end - lo) / math.cos(pitch), 1.6, 1.6), mid, 2.5 + (mid - lo) * math.tan(pitch), sgn * rail,
              C['naga'], roll=pitch, collide=False)
        M.box(sf, 'NagaHead', 3.2, 2.4, -2.5, 6.5, lo, sgn * rail, C['naga'])
        M.box(sf, 'NagaCrest', 1.2, 2.0, 6.5, 9.5, lo, sgn * rail, C['gold'], collide=False, neon=C['amber'])
    # board beside the foot of the stair (outside the naga rails), facing down the stair; first clear spot upwards
    for bx in np.arange(lo - 8.0, top_u * 0.7, 1.0):
        for lat in (13.0, -13.0):
            fp = rect(sf, bx - 0.5, bx + 0.5, lat - 7.5, lat + 7.5)
            if not fp.buffer(cfg['margin_studs']).intersects(avoid):
                M.board(sf, L['label'], 14, 3.2, bx, 4.5, lat, -1, 0, C['plum'], C['gold'], name='NameBoard', depth=0.4)
                M.box(sf, 'BoardPost', 0.8, 0.8, -2.5, 2.9, bx, lat, C['charcoal'])
                break
        else:
            continue
        break
    return F, dict(plinth_r=r, w=2 * r, d=2 * r, h=plinth_top + H + 0.5, steps=kept, osm_steps_studs=ln, stair_studs=top_u)


GLYPHS = {
    'P': [(0, 0, 0, 1), (0, 1, 1, 1), (1, 1, 1, .5), (0, .5, 1, .5)],
    'A': [(0, 0, .5, 1), (1, 0, .5, 1), (.22, .4, .78, .4)],
    'T': [(0, 1, 1, 1), (.5, 0, .5, 1)],
    'Y': [(0, 1, .5, .5), (1, 1, .5, .5), (.5, 0, .5, .5)],
    'C': [(0, 0, 0, 1), (0, 1, 1, 1), (0, 0, 1, 0)],
    'I': [(.5, 0, .5, 1)],
}


def gen_letters(W, L, M, cfg):
    lines = [(W.way(wid), ch) for wid, ch in L['letter_ways']]
    first = np.array(lines[0][0].centroid.coords[0])
    last = np.array(lines[-1][0].centroid.coords[0])
    rdir = (last - first) / np.linalg.norm(last - first)        # reading direction P -> CITY
    H0 = L['letter_height_studs']
    widths = []
    for line, ch in lines:
        a, b = np.array(line.coords[0]), np.array(line.coords[-1])
        if (b - a) @ rdir < 0:
            a, b = b, a
        w = float(np.linalg.norm(b - a))
        c = (a + b) / 2
        F = Frame(c[0], c[1], math.atan2(b[1] - a[1], b[0] - a[0]))   # u = reading direction, viewer's left -> right
        chars = list(ch.upper())
        single = len(chars) == 1
        H = H0 if single else H0 * 0.6
        t = 2.2 if single else 1.3
        cw = w / len(chars)
        M.box(F, 'LetterBase', w + 1, 3.0, -2.5, -0.6, 0, 0, C['charcoal'])
        for k, gch in enumerate(chars):
            x0 = -w / 2 + k * cw + (0 if single else 0.12 * cw)
            gw = cw * (1.0 if single else 0.76)
            for (gx0, gy0, gx1, gy1) in GLYPHS[gch]:
                p0 = np.array([x0 + t / 2 + gx0 * (gw - t), -0.6 + t / 2 + gy0 * (H - t)])
                p1 = np.array([x0 + t / 2 + gx1 * (gw - t), -0.6 + t / 2 + gy1 * (H - t)])
                m = (p0 + p1) / 2
                M.add(F, 'Letter', (float(np.linalg.norm(p1 - p0)) + t, t, 1.8), m[0], m[1], 0, C['white'],
                      roll=math.atan2(p1[1] - p0[1], p1[0] - p0[0]), neon=C['white'])
        widths.append(f'{ch} {w:.1f}')
    cen = (first + last) / 2
    return Frame(cen[0], cen[1], math.atan2(rdir[1], rdir[0])), dict(letter_widths=widths, h=H0)


def cover_rects(region, angles, cell=2.0, min_area=120.0, min_side=6.0):
    """cover `region` with few oriented rectangles: for each angle, grid cells (cell x cell) fully inside the region are
    merged into row runs and then into rectangles; rectangles are then picked greedily by area while each adds at least
    half of its own area as new coverage -> ([(Frame, u0, u1, v0, v1)] largest first, covered polygon)"""
    import shapely
    shapely.prepare(region)
    cx, cz = region.centroid.x, region.centroid.y
    hull = list(region.convex_hull.exterior.coords)
    cands = []
    for ang in angles:
        F = Frame(cx, cz, ang)
        loc = np.array([F.local(x, z) for x, z in hull])
        us = np.arange(math.floor(loc[:, 0].min() / cell) * cell, loc[:, 0].max() + cell, cell)
        vs = np.arange(math.floor(loc[:, 1].min() / cell) * cell, loc[:, 1].max() + cell, cell)
        U, V = np.meshgrid(us, vs)
        inside = np.ones(U.shape, bool)
        for du, dv in ((0, 0), (cell, 0), (0, cell), (cell, cell), (cell / 2, cell / 2)):
            X = cx + (U + du) * F.u[0] + (V + dv) * F.v[0]
            Z = cz + (U + du) * F.u[1] + (V + dv) * F.v[1]
            inside &= shapely.contains_xy(region, X, Z)
        open_ = {}
        for j in range(len(vs) + 1):
            runs = set()
            if j < len(vs):
                row, i = inside[j], 0
                while i < len(us):
                    if row[i]:
                        k = i
                        while k < len(us) and row[k]:
                            k += 1
                        runs.add((i, k))
                        i = k
                    else:
                        i += 1
            for key in list(open_):
                if key not in runs:
                    j0 = open_.pop(key)
                    r = (us[key[0]], us[key[0]] + (key[1] - key[0]) * cell, vs[j0], vs[j0] + (j - j0) * cell)
                    if r[1] - r[0] >= min_side and r[3] - r[2] >= min_side and (r[1] - r[0]) * (r[3] - r[2]) >= min_area:
                        cands.append(((r[1] - r[0]) * (r[3] - r[2]), F, r))
            for key in runs:
                open_.setdefault(key, j)
    cands.sort(key=lambda c: -c[0])
    chosen, covered = [], Polygon()
    for a, F, r in cands:
        p = rect(F, *r)
        if p.difference(covered).area >= 0.5 * a:
            chosen.append((F,) + tuple(float(x) for x in r))
            covered = covered.union(p)
    return chosen, covered


def gen_pier(W, L, M, cfg):
    poly = W.way(L['way'])
    keep = set(L['replaces'])
    avoid = W.obstacles(poly.buffer(60), keep_out=keep)
    free = poly.difference(avoid.buffer(cfg['margin_studs']))
    if free.geom_type == 'MultiPolygon':
        free = max(free.geoms, key=lambda g: g.area)
    angles = []                                          # the pier's own edge directions (arms, stem, connectors)
    ext = list(poly.exterior.coords)
    for (x0, z0), (x1, z1) in zip(ext[:-1], ext[1:]):
        if math.hypot(x1 - x0, z1 - z0) > 30:
            a = math.atan2(z1 - z0, x1 - x0) % math.pi
            if all(min(abs(a - b), math.pi - abs(a - b)) > math.radians(2) for b in angles):
                angles.append(a)
    rects, deck = cover_rects(free, angles)
    land = W.obstacles(poly.buffer(900), keep_out=keep)   # land end = the outline point nearest a road or building
    land_pt, land_d = None, 1e9
    for x, z in ext:
        d = land.distance(Point(x, z))
        if d < land_d:
            land_pt, land_d = np.array([x, z]), d
    _, road_d = W.nearest_road_dir(*land_pt, maxd=2000)
    posts = lamps = 0
    for k, (F, u0, u1, v0, v1) in enumerate(rects):
        top = 1.0 - 0.04 * k                             # overlapping deck pieces never share a top face (no z-fight)
        long_u = (u1 - u0) >= (v1 - v0)
        M.box(F, 'PierDeck', u1 - u0, v1 - v0, -0.4, top, (u0 + u1) / 2, (v0 + v1) / 2, C['concrete'], mat='Concrete')
        a0, a1 = (u0, u1) if long_u else (v0, v1)
        mid = (v0 + v1) / 2 if long_u else (u0 + u1) / 2
        for s in np.arange(a0 + 24, a1 - 4, 48):         # posts under the deck on the long axis
            lu, lz = (s, mid) if long_u else (mid, s)
            M.vcyl(F, 'PierPost', 2.2, -12, -0.4, lu, lz, C['charcoal'], collide=False)
            posts += 1
        if a1 - a0 >= 80 and min(u1 - u0, v1 - v0) >= 5:  # lamps every 96 studs on long pieces
            for s in np.arange(a0 + 30, a1 - 20, 96):
                lu, lz = (s, mid) if long_u else (mid, s)
                M.vcyl(F, 'PierLampPost', 0.8, top, 16, lu, lz, C['charcoal'])
                M.box(F, 'PierLamp', 2.4, 2.4, 16, 17.4, lu, lz, C['warm'], collide=False, neon=C['warm'])
                lamps += 1
    rails = 0                                            # rails on the deck outline, open at the land end
    outline = deck if deck.geom_type == 'Polygon' else max(deck.geoms, key=lambda g: g.area)
    coords = list(outline.exterior.coords)
    for (x0, z0), (x1, z1) in zip(coords[:-1], coords[1:]):
        seg = LineString([(x0, z0), (x1, z1)])
        if seg.length < 3 or seg.distance(Point(*land_pt)) < 30:
            continue
        nseg = int(seg.length // 60) + 1
        for k in range(nseg):
            pa = seg.interpolate(k / nseg, normalized=True)
            pb = seg.interpolate((k + 1) / nseg, normalized=True)
            ln = math.hypot(pb.x - pa.x, pb.y - pa.y)
            mx, mz = (pa.x + pb.x) / 2, (pa.y + pb.y) / 2
            nx, nz = -(pb.y - pa.y) / ln, (pb.x - pa.x) / ln
            if not outline.contains(Point(mx + nx * 0.6, mz + nz * 0.6)):
                nx, nz = -nx, -nz                        # inset 0.5 into the deck
            G = Frame(mx + nx * 0.5, mz + nz * 0.5, math.atan2(pb.y - pa.y, pb.x - pa.x))
            M.box(G, 'PierRail', ln, 0.6, 0.5, 3.6, 0, 0, C['white'])
            rails += 1
    pav = W.way(L['pavilion_way'])                      # ferry pavilion on the OSM roof footprint (replaces its box)
    PF, phu, phv = mrr_frame(pav)
    PF, phu, phv = recenter(PF, fit_rect(PF, -phu, phu, -phv, phv, W.obstacles(pav.buffer(40), keep_out=keep), cfg['margin_studs']))
    ph = 15.0
    for su in (-1, 1):
        for sv in (-1, 1):
            M.vcyl(PF, 'PavilionPost', 1.6, -0.4, ph, su * (phu - 1.5), sv * (phv - 1.5), C['white'])
    pitch = math.radians(28)
    for sv in (-1, 1):
        M.add(PF, 'PavilionRoof', (2 * phu, 1.0, phv / math.cos(pitch)), 0, ph + phv * math.tan(pitch) / 2, sv * phv / 2,
              C['roof_red'], pitch=sv * pitch, collide=False, shadow=True)
    rt = ph + phv * math.tan(pitch)
    M.box(PF, 'RoofRidge', 2 * phu, 1.0, rt, rt + 0.8, 0, 0, C['gold'], collide=False, neon=C['amber'])
    # name gate across the deck piece nearest the land end, 14 studs in from that end, facing the land
    F, u0, u1, v0, v1 = min(rects, key=lambda r: rect(*r).distance(Point(*land_pt)))
    lu, lv = F.local(*land_pt)
    gate = False
    if (u1 - u0) >= (v1 - v0):
        end = u0 if abs(lu - u0) < abs(lu - u1) else u1
        gu, sgn = (end + 14, -1) if end == u0 else (end - 14, 1)
        span, cv = max(v1 - v0, 22.0), (v0 + v1) / 2   # posts may stand in the water beside a narrow stem
        for sv in (cv - span / 2 + 1.2, cv + span / 2 - 1.2):
            M.box(F, 'GatePost', 2.0, 2.0, -6, 24, gu, sv, C['white'])
        M.box(F, 'GateBeam', 2.0, span, 24, 26, gu, cv, C['white'], collide=False)
        M.board(F, L['label'], min(span - 6, 40.0), 5.5, gu + sgn * 1.4, 21, cv, sgn, 0, C['navy'], C['white'],
                stroke=C['cyan'], neon_frame=C['cyan'], name='NameBoard', depth=0.5)
        gate = True
    cen = poly.centroid
    return Frame(cen.x, cen.y, 0.0), dict(deck_pieces=len(rects), deck_area=round(deck.area), osm_area=round(poly.area),
                                          posts=posts, rails=rails, lamps=lamps, gate=gate,
                                          land_end_to_land=round(land_d, 1), land_end_to_road=round(road_d, 1), pavilion=f'{2 * phu:.1f} x {2 * phv:.1f}')


def gen_dolphin(W, L, M, cfg):
    ring = W.way(L['way'])
    island = Polygon(ring.coords) if ring.geom_type == 'LineString' else ring
    avoid = W.obstacles(island.buffer(40))
    free = island.difference(avoid.buffer(1.5))
    if free.geom_type == 'MultiPolygon':
        free = max(free.geoms, key=lambda g: g.area)
    c = polylabel(free, tolerance=0.1)
    r = min(free.exterior.distance(c), 14.0)
    F = Frame(c.x, c.y, 0.0)
    M.vcyl(F, 'Basin', 2 * r * 0.97, -2.5, 1.6, 0, 0, C['offwhite'], mat='Marble')
    M.vcyl(F, 'BasinWater', 2 * r * 0.97 - 1.6, 1.6, 1.8, 0, 0, C['water'], collide=False, neon=C['cyan'])
    M.vcyl(F, 'Pedestal', r * 0.55, 1.8, 9.5, 0, 0, C['offwhite'], mat='Marble')
    rho = max(r - 2.2, 2.5)
    for k in range(3):                                   # three dolphins leaping out from the centre
        G = Frame(c.x, c.y, k * 2 * math.pi / 3)        # u = radial direction of this dolphin
        y0 = 15.0
        for j, phi in enumerate((200, 150, 100, 55, 15)):
            ph = math.radians(phi)
            thick = 2.4 if 0 < j < 4 else 1.7
            M.add(G, 'Dolphin', (3.4, thick, thick * 0.9), rho * math.cos(ph), y0 + 5.5 * math.sin(ph), 0, C['dolphin'],
                  roll=math.atan2(5.5 * math.cos(ph), -rho * math.sin(ph)) + math.pi, collide=False, shadow=True)
        M.add(G, 'DolphinFin', (1.2, 1.4, 0.4), 0, y0 + 5.5 + 1.4, 0, C['dolphin'], collide=False)
    M.vcyl(F, 'Spout', 0.6, 9.5, 21, 0, 0, C['cyan'], collide=False, neon=C['cyan'])
    d, _ = W.nearest_road_dir(c.x, c.y)                  # plaque on the pedestal, facing the nearest road
    M.board(F, L['label'], r * 0.5, 1.2, d[0] * (r * 0.275 + 0.25), 6.0, d[1] * (r * 0.275 + 0.25), d[0], d[1], C['navy'],
            C['white'], name='NameBoard', depth=0.2)
    return F, dict(island_r=r, w=2 * r, d=2 * r, h=22)


def pavilion(M, F, hu, hv, roof, neon, stilts, deck_y=2.0, ph=10.0):
    if stilts:
        for su in (-1, 1):
            for sv in (-1, 1):
                M.vcyl(F, 'Stilt', 1.0, -2.5, deck_y, su * (hu - 0.8), sv * (hv - 0.8), C['teak_dark'], mat='Wood')
    M.box(F, 'PavilionDeck', 2 * hu, 2 * hv, deck_y if stilts else -2.5, deck_y + 0.8, 0, 0, C['teak'], mat='WoodPlanks')
    M.box(F, 'PavilionWall', 2 * hu - 2, 2 * hv - 2, deck_y + 0.8, deck_y + ph * 0.55, 0, 0, C['teak_light'], mat='Wood',
          collide=False)
    pitch = math.radians(34)
    y = deck_y + ph
    for sv in (-1, 1):
        M.add(F, 'PavilionRoof', (2 * hu, 0.8, hv / math.cos(pitch)), 0, y + hv * math.tan(pitch) / 2, sv * hv / 2, roof,
              pitch=sv * pitch, collide=False, shadow=True)
    rt = y + hv * math.tan(pitch)
    M.box(F, 'RoofRidge', 2 * hu, 0.6, rt, rt + 0.6, 0, 0, C['gold'], collide=False, neon=neon)


def gen_floating_market(W, L, M, cfg):
    area = W.way(L['way'])
    water = W.way(L['water_way'])
    houses = []                                          # the OSM houses of the market (stalls on the water)
    for (t, i), e in W.osm.items():
        if t == 'way' and e.get('tags', {}).get('building') == 'house' and 'geometry' in e:
            g = W.way(i)
            if g.geom_type == 'Polygon' and area.contains(g.centroid):
                houses.append((i, g))
    house_ids = {i for i, _ in houses}
    L['replaces'] = sorted({b['id'] for b in W.buildings if b['id'] in house_ids and area.contains(Point(b['x'], b['z']))})
    keep = set(L['replaces'])
    avoid = W.obstacles(area.buffer(40), keep_out=keep)
    wreg = water.intersection(area).difference(avoid.buffer(cfg['margin_studs']))
    WF = Frame(0, 0, 0)                                  # thin water surface (no collision) on the OSM water
    bb = wreg.bounds
    cells = strips(WF, wreg, 16.0, 16.0, (bb[0], bb[2], bb[1], bb[3]))
    for c in cells:
        M.box(WF, 'MarketWater', c[1] - c[0], c[3] - c[2], -1.95, -1.75, (c[0] + c[1]) / 2, (c[2] + c[3]) / 2, C['water'],
              collide=False, transp=0.15)
    built, dropped, stilted = 0, 0, 0
    for k, (i, g) in enumerate(sorted(houses)):
        PF, hu, hv = mrr_frame(g)
        fb = fit_rect(PF, -hu, hu, -hv, hv, avoid, 1.5, min_side=4.0)
        if fb is None:
            dropped += 1
            continue
        PF, hu, hv = recenter(PF, fb)
        st = water.contains(Point(*PF.o)) and min(hu, hv) > 2.5
        pavilion(M, PF, hu, hv, C['terracotta'] if k % 3 else C['roof_red'], STALL_NEON[k % 5] if k % 4 == 0 else C['amber'], st)
        built += 1
        stilted += st
    nd = W.node(L['node'])                               # gate at the OSM attraction node, slid inwards until clear
    cen = area.centroid
    gate = None
    pav = unary_union([footprint(p) for p in M.parts if p['name'] in ('PavilionDeck', 'Stilt', 'PavilionRoof')])
    for rr in np.arange(0, 240, 4):                    # nearest clear spot to the node (rings of growing radius)
        for a in np.arange(0, 360, 10 if rr else 360):
            x, z = nd.x + rr * math.cos(math.radians(a)), nd.y + rr * math.sin(math.radians(a))
            d, _ = W.nearest_road_dir(x, z)
            G = Frame(x, z, math.atan2(d[1], d[0]) + math.pi / 2)   # -v faces the road
            fp = rect(G, -17, 17, -2.5, 2.5)
            if not fp.buffer(cfg['margin_studs']).intersects(avoid) and not fp.buffer(2).intersects(pav):
                gate = (G, rr)
                break
        if gate:
            break
    if gate:
        G, f = gate
        for s in (-1, 1):
            M.box(G, 'GatePost', 2.4, 2.4, -2.5, 22, s * 14, 0, C['teak_dark'], mat='Wood')
        M.box(G, 'GateBeam', 32, 2.4, 22, 24, 0, 0, C['teak_dark'], mat='Wood', collide=False)
        pitch = math.radians(30)
        for sv in (-1, 1):
            M.add(G, 'GateRoof', (34, 0.8, 2.6 / math.cos(pitch)), 0, 25.2, sv * 1.1, C['roof_red'], pitch=sv * pitch, collide=False)
        M.board(G, L['label'], 26, 4.5, 0, 19, -1.5, 0, -1, C['teak_dark'], C['warm'], neon_frame=C['amber'], name='NameBoard',
                depth=0.5)
    return Frame(cen.x, cen.y, 0), dict(houses=len(houses), pavilions=built, on_stilts=int(stilted), dropped=dropped,
                                        water_strips=len(cells), gate_from_node_studs=round(float(gate[1]), 1) if gate else None)


def gen_night_market(W, L, M, cfg):
    area = W.way(L['way'])
    F, hu, hv = mrr_frame(area)
    avoid = W.obstacles(area.buffer(40))
    free = area.difference(avoid.buffer(cfg['margin_studs']))
    d, _ = W.nearest_road_dir(*area.centroid.coords[0])  # entrance arch: last clear spot from the centre to the road
    c0 = np.array(area.centroid.coords[0])
    ang = math.atan2(d[1], d[0]) + math.pi / 2
    placed = None
    for back in np.arange(0, 400, 2):
        G = Frame(*(c0 + d * back), ang)
        if free.contains(rect(G, -16, 16, -2.5, 2.5)):
            placed = G
        elif placed is not None:
            break
    keep_free = rect(placed, -22, 22, -10, 14) if placed else Polygon()
    k = 0
    for j, v in enumerate(np.arange(-hv + 4, hv, 26.0)):  # rows: two stalls back to back, then a 10-stud aisle
        for side, sv in ((-1, v), (1, v + 8)):
            for u in np.arange(-hu + 4, hu - 4, 12):
                if not free.contains(rect(F, u, u + 10, sv, sv + 8)) or rect(F, u, u + 10, sv, sv + 8).intersects(keep_free):
                    continue
                cu, cv = u + 5, sv + 4
                ci = (k * 7 + j * 3) % 5
                front = side                            # the stall opens to its aisle
                M.box(F, 'StallCounter', 10, 3, -2.5, 2.2, cu, cv - front * 2.5, C['teak'], mat='Wood')
                M.add(F, 'StallCanopy', (10.4, 0.4, 8.2), cu, 8.6, cv, STALL[ci], pitch=front * math.radians(12), collide=False)
                M.vcyl(F, 'StallPost', 0.5, -2.5, 8.6, cu + (4.8 if k % 2 else -4.8), cv + front * 3.6, C['steel'])
                M.box(F, 'NeonSign', 10.2, 0.4, 7.4, 7.8, cu, cv + front * 3.9, STALL_NEON[ci], collide=False, neon=STALL_NEON[ci])
                k += 1
    if placed:
        for s in (-1, 1):
            M.box(placed, 'ArchPost', 2, 2, -2.5, 20, s * 14, 0, C['charcoal'])
        M.box(placed, 'ArchBeam', 30, 2, 20, 22, 0, 0, C['charcoal'], collide=False)
        M.board(placed, L['label'], 24, 4.5, 0, 17, -1.2, 0, -1, C['dark'], C['yellow'], stroke=C['pink'], neon_frame=C['pink'],
                name='NameBoard', depth=0.5)
    return F, dict(stalls=k, arch=bool(placed), w=2 * hu, d=2 * hv)


def gen_tower(W, L, M, cfg):
    shaft, deck, mast, podium = (W.way(L[k]) for k in ('shaft_way', 'deck_way', 'mast_way', 'podium_way'))
    keep = set(L['replaces'])
    tg = lambda key: W.tags('way', L[key])
    PF, phu, phv = orient_front(W, *fit_footprint(W, podium, keep, cfg['margin_studs']))
    plv = int(tg('podium_way')['building:levels'])     # podium: the 24-level hotel block the tower rises from
    ph = W.levels_h(plv)
    M.box(PF, 'Podium', 2 * phu, 2 * phv, -2.5, ph, 0, 0, C['offwhite'], shadow=True)
    for k in range(2, plv, 4):
        y = k * W.level + W.extra
        M.box(PF, 'WindowBand', 2 * phu - 3, 0.5, y, y + 2.4, 0, -phv + 0.25, C['glass'], collide=False, neon=C['warm'])
    SF, shu, shv = mrr_frame(shaft)                      # shaft: levels 0..51
    sh_top = int(tg('shaft_way')['building:levels']) * W.level + W.extra
    dia = min(shu, shv) * 2 * 0.9
    M.vcyl(SF, 'TowerShaft', dia, ph - 1, sh_top, 0, 0, C['offwhite'], shadow=True)
    for k in range(4):                                   # vertical light strips on the shaft (night)
        a = k * math.pi / 2
        M.add(SF, 'ShaftStrip', (0.6, sh_top - ph - 20, 0.6), math.cos(a) * dia / 2, (ph + sh_top) / 2, math.sin(a) * dia / 2,
              C['offwhite'], collide=False, neon=C['cyan'])
    DF, dhu, dhv = mrr_frame(deck)                       # deck: building:min_level 51 .. building:levels 55
    S = min(dhu, dhv) * 2
    d0 = int(tg('deck_way')['building:min_level']) * W.level + W.extra
    d1 = int(tg('deck_way')['building:levels']) * W.level + W.extra
    for yaw, side in ((0.0, S * 0.94), (math.pi / 4, S * 0.69)):
        M.add(DF, 'Deck', (side, d1 - d0, side), 0, (d0 + d1) / 2, 0, C['offwhite'], yaw=yaw, shadow=True)
        M.add(DF, 'DeckGlass', (side + 0.3, 6, side + 0.3), 0, (d0 + d1) / 2 + 2, 0, C['glass'], yaw=yaw, collide=False,
              neon=C['glass_n'])
    roof_top = 57 * W.level + W.extra                    # roof:levels 2 above the deck, mast from min_level 57
    M.vcyl(DF, 'DeckRoof', S * 0.6, d1, roof_top, 0, 0, C['concrete'])
    jx = -S * 0.34                                       # jump deck: a small platform under the deck
    M.box(DF, 'JumpDeck', 9, 7, d0 - 3, d0 - 1.6, jx, 0, C['yellow'], collide=False)
    M.box(DF, 'JumpRail', 0.4, 7, d0 - 1.6, d0 + 0.8, jx - 4.3, 0, C['charcoal'], collide=False)
    top = float(tg('mast_way')['height']) * W.vs
    m0 = max(int(tg('mast_way')['building:min_level']) * W.level + W.extra, roof_top)
    for t, (dd, f0, f1) in enumerate(((4.5, 0, 0.35), (3.0, 0.35, 0.7), (1.6, 0.7, 1.0))):
        M.vcyl(DF, 'Mast', dd, m0 + (top - m0) * f0, m0 + (top - m0) * f1, 0, 0, C['white'] if t % 2 == 0 else C['red'],
               collide=False)
    M.box(DF, 'Beacon', 2.2, 2.2, top, top + 2.2, 0, 0, C['beacon'], collide=False, neon=C['beacon'])
    for sgn in (-1, 1):                                  # name boards under the deck, both sides
        M.board(DF, L['label'], S * 0.6, 4.2, 0, d0 - 4.5, sgn * (S * 0.3), 0, sgn, C['navy'], C['white'], stroke=C['cyan'],
                name='NameBoard', depth=0.4)
    return SF, dict(podium_h=ph, shaft_top=sh_top, deck=f'{d0:.1f}-{d1:.1f}', top=top, w=2 * phu, d=2 * phv, h=top)


GEN = dict(theatre=gen_theatre, mall=gen_mall, terminal=gen_terminal, sanctuary=gen_sanctuary, buddha=gen_buddha,
           letters=gen_letters, pier=gen_pier, dolphin=gen_dolphin, floating_market=gen_floating_market,
           night_market=gen_night_market, tower=gen_tower)


# ---- checks ----------------------------------------------------------------------------------------------------------
def check(W, M, keep_out, margin):
    """every part footprint (buffered by margin) against roads / sidewalks / discs / props and kept buildings"""
    hits = []
    for i, p in enumerate(M.parts):
        fp = footprint(p).buffer(margin)
        for j in W.rtree.query(fp):
            if W.roads[j][3].intersects(fp):
                hits.append((i, p['name'], W.roads[j][0], W.roads[j][1], W.roads[j][2]))
        for j in W.btree.query(fp):
            b = W.buildings[j]
            if b['id'] not in keep_out and b['poly'].intersects(fp):
                hits.append((i, p['name'], 'building', b['ds'], b['id']))
    return hits


# ---- export ----------------------------------------------------------------------------------------------------------
def lua_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def fmt(v, nd=2):
    s = f'{v:.{nd}f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def export_landmark(M, meta):
    pal, names = [], []

    def ci(c):
        if c not in pal:
            pal.append(c)
        return pal.index(c) + 1

    def ni(n):
        if n not in names:
            names.append(n)
        return names.index(n) + 1
    rows, neon = [], []
    for i, p in enumerate(M.parts):
        rx, ry, rz = euler_yxz(p['R'])
        flags = (F_COLLIDE if p['collide'] else 0) | (F_QUERY if p['query'] else 0) | (F_SHADOW if p['shadow'] else 0)
        vals = [ni(p['name']), SHAPES.index(p['shape']) + 1] + [fmt(s) for s in p['size']] + [fmt(x) for x in p['pos']] + \
               [fmt(rx, 4), fmt(ry, 4), fmt(rz, 4), ci(p['color']), MATERIALS.index(p['mat']) + 1, flags, fmt(p['transp'])]
        rows.append(','.join(str(v) for v in vals))
        if p['neon']:
            neon.append(f'{i + 1},{ci(p["color"])},{ci(p["neon"])}')
    texts = ['{ ' + f'{i + 1}, {lua_str(face)}, {lua_str(txt)}, {ci(col)}, {lua_str(font)}, {ci(stroke) if stroke else 0}' + ' }'
             for (i, face, txt, col, font, stroke) in M.texts]
    out = ['  {']
    for k in ('id', 'name', 'label', 'source'):
        out.append(f'    {k} = {lua_str(meta[k])},')
    out.append(f'    x = {fmt(meta["x"])}, z = {fmt(meta["z"])},')
    out.append('    colors = { ' + ', '.join(f'{c[0]},{c[1]},{c[2]}' for c in pal) + ' },')
    out.append('    names = { ' + ', '.join(lua_str(n) for n in names) + ' },')
    out.append('    -- per part: name, shape, sx, sy, sz, x, y, z (map-local), rx, ry, rz (CFrame.fromEulerAnglesYXZ), '
               'color, material, flags (1 collide, 2 query, 4 shadow), transparency')
    out.append('    parts = {')
    out += ['      ' + r + ',' for r in rows]
    out.append('    },')
    out.append('    neon = { ' + ', '.join(neon) + ' }, -- part, day colour, night colour (NightNeon)')
    out.append('    texts = {')
    out += ['      ' + t + ',' for t in texts]
    out.append('    },')
    out.append('  },')
    return '\n'.join(out)


def check_image(path, W, M, keep_out, osm_geoms, title):
    """top-down check (north up): roads dark grey, sidewalks light grey, discs dark, street props coloured dots, kept
    building boxes tan, replaced boxes red outline, OSM geometry blue outline, proxy parts in their (night) colour"""
    from PIL import Image, ImageDraw
    fps = [footprint(p) for p in M.parts]
    x0, z0, x1, z1 = unary_union(fps + osm_geoms).bounds
    pad = max(60, 0.15 * max(x1 - x0, z1 - z0))
    x0, z0, x1, z1 = x0 - pad, z0 - pad, x1 + pad, z1 + pad
    s = 1000 / max(x1 - x0, z1 - z0)
    im = Image.new('RGB', (int((x1 - x0) * s) + 1, int((z1 - z0) * s) + 1 + 60), (236, 233, 224))
    d = ImageDraw.Draw(im, 'RGBA')
    tr = lambda x, z: ((x - x0) * s, (z - z0) * s + 60)

    def draw(g, fill=None, outline=None, width=1):
        for gg in getattr(g, 'geoms', [g]):
            if gg.geom_type == 'Polygon' and not gg.is_empty:
                d.polygon([tr(*c) for c in gg.exterior.coords], fill=fill, outline=outline, width=width)
            elif gg.geom_type in ('LineString', 'LinearRing'):
                d.line([tr(*c) for c in gg.coords], fill=outline, width=max(width, 2))
    colors = dict(road=(85, 90, 99), sidewalk=(185, 181, 168), junction=(63, 67, 74), joint=(63, 67, 74), palm=(46, 139, 58),
                  light=(216, 160, 32), sign=(192, 64, 192), job_stand=(32, 80, 208), gate=(208, 32, 96))
    view = box(x0, z0, x1, z1)
    order = {'sidewalk': 0, 'road': 1, 'junction': 2, 'joint': 2}
    for j in sorted(W.rtree.query(view), key=lambda j: order.get(W.roads[j][0], 3)):
        draw(W.roads[j][3], fill=colors.get(W.roads[j][0], (128, 128, 128)))
    for j in W.btree.query(view):
        b = W.buildings[j]
        if b['id'] in keep_out:
            draw(b['poly'], outline=(224, 32, 32), width=2)
        else:
            draw(b['poly'], fill=(232, 216, 176), outline=(160, 136, 96))
    for p, fp in sorted(zip(M.parts, fps), key=lambda t: t[0]['pos'][1]):
        c = p['neon'] or p['color']
        draw(fp, fill=(c[0], c[1], c[2], 190), outline=(32, 32, 32, 160))
    for g in osm_geoms:
        draw(g.boundary if g.geom_type == 'Polygon' else g, outline=(16, 96, 255), width=2)
    for k, line in enumerate(title.splitlines()):
        d.text((6, 4 + k * 14), line, fill=(20, 20, 20))
    bar = 10 ** math.floor(math.log10((x1 - x0) / 4))
    d.line([(10, im.height - 12), (10 + bar * s, im.height - 12)], fill=(0, 0, 0), width=3)
    d.text((14 + bar * s, im.height - 20), f'{bar:g} studs ({bar * 0.56:g} m real)   north up', fill=(0, 0, 0))
    im.save(path)


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    W = World(cfg)
    out = os.path.join(ROOT, cfg['out'])
    rdir = os.path.join(out, 'roblox')
    os.makedirs(rdir, exist_ok=True)
    os.makedirs(os.path.join(out, 'check'), exist_ok=True)
    for f in os.listdir(rdir):
        if f.endswith('.luau'):
            os.remove(os.path.join(rdir, f))
    CS = cfg['chunk_size_studs']
    chunks = defaultdict(list)
    summary, replaces, total = [], [], 0
    for L in cfg['landmarks']:
        L = dict(L)
        M = Model(L['id'])
        F, info = GEN[L['kind']](W, L, M, cfg)
        keep_out = set(L.get('replaces', []))
        hits = check(W, M, keep_out, cfg['check_margin_studs'])
        assert not hits, f'{L["id"]}: {len(hits)} overlaps, e.g. {hits[:5]}'
        n = len(M.parts)
        assert n <= cfg['max_parts_per_landmark'], f'{L["id"]}: {n} parts'
        total += n
        x, z = float(F.o[0]), float(F.o[1])
        cid = f'l{math.floor(x / CS)}_{math.floor(z / CS)}'
        src_ids = [f'way {L[k]}' for k in ('way', 'shaft_way', 'deck_way', 'mast_way', 'podium_way', 'steps_way',
                                           'pavilion_way', 'water_way', 'area_way') if k in L]
        src_ids += [f'node {L[k]}' for k in ('node', 'ferry_node') if k in L]
        src_ids += [f'way {w}' for w, _ in L.get('letter_ways', [])]
        meta = dict(id=L['id'], name=L['name'], label=L['label'], source='OSM ' + ', '.join(src_ids), x=x, z=z)
        chunks[cid].append(export_landmark(M, meta))
        rep = []
        for bid in L.get('replaces', []):
            found = [b for b in W.buildings if b['id'] == bid]
            assert found, f'{L["id"]}: replaced box {bid} not in any chunk module'
            rep += [dict(osm=bid, dataset=b['ds'], chunk=b['chunk'], h=round(b['h'], 1)) for b in found]
        replaces += [dict(r, landmark=L['id']) for r in rep]
        osm_geoms = []
        for s in src_ids:
            kind, i = s.split()
            if kind == 'way':
                osm_geoms.append(W.way(int(i)))
            else:
                osm_geoms.append(W.node(int(i)).buffer(3))
        summary.append(dict(id=L['id'], name=L['name'], label=L['label'], chunk=cid, x=round(x, 1), z=round(z, 1),
                            world=[round(x + 20000, 1), round(z, 1)], parts=n, neon=sum(1 for p in M.parts if p['neon']),
                            texts=len(M.texts), source=meta['source'],
                            info={k: (round(float(v), 1) if isinstance(v, (float, np.floating)) else v) for k, v in info.items()},
                            replaces=rep, counts=dict(Counter(p['name'] for p in M.parts)), height_src=L.get('height_src')))
        check_image(os.path.join(out, 'check', f'{L["id"]}.png'), W, M, keep_out, osm_geoms,
                    f'{L["name"]}: {n} parts, chunk {cid}, world ({x + 20000:.0f}, {z:.0f})\n{meta["source"]}\n'
                    f'export check: 0 part footprints touch a road / sidewalk / disc / prop / kept building (margin {cfg["check_margin_studs"]})')
        print(f'{L["id"]:22s} {n:4d} parts  chunk {cid:8s} world ({x + 20000:8.1f}, {z:8.1f})  replaces {len(rep)}  {summary[-1]["info"]}')
    assert total <= cfg['max_total_parts'], total
    ids = sorted(chunks, key=lambda c: (int(c[1:].split('_')[0]), int(c.split('_')[1])))
    bs = cfg['batch_size']
    batches = {f'l{k // bs + 1}': ids[k:k + bs] for k in range(0, len(ids), bs)}
    sizes = {}
    for cid in ids:
        src = '\n'.join([f'-- generated by tools/mapgen/landmarks.py; do not edit. Landmark proxies in chunk {cid}.',
                         f'-- {ATTRIBUTION}', 'return {', f'  id = {lua_str(cid)},', '  landmarks = {'] +
                        chunks[cid] + ['  },', '}', ''])
        open(os.path.join(rdir, f'chunk_{cid}.luau'), 'w', encoding='utf-8', newline='\n').write(src)
        sizes[cid] = len(src.encode('utf-8'))
        assert sizes[cid] < 200_000, (cid, sizes[cid])
    man = ['-- generated by tools/mapgen/landmarks.py; do not edit', 'return {', f'  name = {lua_str(cfg["name"])},',
           f'  attribution = {lua_str(ATTRIBUTION)},',
           '  osmBase = { ' + ', '.join(f'[{lua_str(k)}] = {lua_str(v or "")}' for k, v in sorted(W.osm_base.items())) + ' },',
           f'  compression = {W.compression}, metersPerStud = {W.mps}, chunkSize = {CS}, totalParts = {total},',
           '  chunks = { ' + ', '.join(lua_str(c) for c in ids) + ' },',
           '  batchOrder = { ' + ', '.join(lua_str(b) for b in batches) + ' },',
           '  batches = {']
    man += [f'    {b} = {{ ' + ', '.join(lua_str(c) for c in v) + ' },' for b, v in batches.items()]
    man += ['  },', '  landmarks = {']
    for s in summary:
        man.append('    { ' + f'id = {lua_str(s["id"])}, chunk = {lua_str(s["chunk"])}, x = {fmt(s["x"])}, z = {fmt(s["z"])}, '
                   f'parts = {s["parts"]}, label = {lua_str(s["label"])}' + ' },')
    man += ['  },', '  -- procedural building boxes that a proxy replaces: PattayaLandmarksBuilder.RemoveReplaced()',
            '  -- dataset "central" = workspace.PattayaWorld.Chunks, "wide" = workspace.PattayaWorld.WideChunks', '  replaces = {']
    for r in replaces:
        man.append('    { ' + f'osm = {r["osm"]}, dataset = {lua_str(r["dataset"])}, chunk = {lua_str(r["chunk"])}, '
                   f'landmark = {lua_str(r["landmark"])}' + ' },')
    man += ['  },', '}', '']
    open(os.path.join(rdir, 'manifest.luau'), 'w', encoding='utf-8', newline='\n').write('\n'.join(man))
    json.dump(dict(attribution=ATTRIBUTION, osm_base=W.osm_base, total_parts=total, chunks=ids, batches=batches,
                   module_bytes=sizes, landmarks=summary, replaces=replaces),
              open(os.path.join(out, "landmarks.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=lambda o: o.item())
    print(f'{len(summary)} landmarks, {total} parts, {len(ids)} chunks {ids}, batches {batches}; '
          f'{len(replaces)} procedural boxes to remove; largest module {max(sizes.values())} bytes')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'tools', 'mapgen', 'config', 'landmarks.json'))
