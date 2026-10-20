"""Road shoulders, width tapers and carriageway hole fills along Sukhumvit Road (pilot; target list in the config).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python.exe tools\\mapgen\\road_shoulders.py tools\\mapgen\\config\\shoulders.json
  ... --build-root D:\\ROBLOXRACE\\build    (default: this checkout's build/, else the main checkout's build/)
  ... --no-determinism                      skip the second (determinism) run
  ... --analysis-only                       only the edge analysis + the before drive check (no files written)

The problem (docs/ROAD_SHOULDERS.md): Sukhumvit Road is built with no sidewalks, so its slab edges (road top 1.0,
slab Parts 4 thick) drop straight to the terrain (y -2): a wheel that leaves the slab falls about 3 studs. And the
carriageway changes width abruptly at some nodes (52 -> 26 / 39 near the skipped underpass, world z 990 .. 1060):
a car holding its lane runs off the narrower slab. Studio drive (leader, physics, 150 studs/s): lane offset 24 at
world (25250, 13430) and lane offset 14 at about (24560, 900) flipped; the centre line was clean.

Input: the BUILT road data that the Studio builders consume (as junction_aprons.py: road_check.py ports
PattayaBuilder's stripe / offset / trim and road_fix rule D 1:1), the apron layer (build/aprons/roblox, read with
tools/qa/road_seams.load_aprons), buildings, props and furniture (junction_aprons.load_world). Nothing that exists is
changed: the layer only ADDS parts in its own folder (workspace.PattayaWorld.ShoulderChunks).

Targets: built (not hidden) edges whose Studio name is in targets.names and class in targets.classes (Sukhumvit, the
trunk), plus edges of a near_classes class (trunk_link) within that distance of a target trunk edge. Pieces, in order
(each later kind is clipped by the earlier ones):
  shoulder  per slab segment and side, the band from width/2 - road_overlap to width/2 + shoulder.width, stretched
            at joints like Builder.stripe (min(h tan(turn/2), h) with h = the outer half width), minus exclusions.
  taper     at a node where a target edge of width W1 continues (turn <= max_turn_deg) into a target edge of width
            W2 <= W1 - min_width_change: a variable-width strip along the narrower edge (and its continuation) whose
            half width goes linearly from W1/2 + shoulder to W2/2 + shoulder over L = clamp(len_per_stud x (W1-W2)/2,
            min_len, max_len), both sides, plus the fan triangle at the node; minus exclusions.
  gap       holes inside the nominal carriageway (the full exported polyline's stripe at its width) that no road part
            covers (end gaps at slab cuts, bend wedges, seams), minus exclusions.
Exclusions: road surfaces (slabs, fill triangles, junction / joint discs) shrunk by road_overlap (the piece tucks
0.1 under a slab edge, so there is no ray gap and no visible seam: shoulder top 0.985 is under the road 1.00 and the
discs 0.99), aprons and corner fills (+0.02), sidewalks (+0.02), building boxes (+0.5), props (+0.3), earlier pieces
(shrunk 0.05: neighbouring pieces overlap by 0.05, same height and style). Cleaned (opening 0.08), cut into one box
when a piece is a rectangle, else constrained-Delaunay triangles (two WedgeParts each, as PattayaBuilder.roadTriangle).
Terrain (optional, separate batch): Terrain:FillBlock boxes from the shoulder's outer edge outwards (terrain.width),
in slices of slice_len, kept only where the whole slice is clear of every road / sidewalk / apron / corner / building
(+2) / prop (+1); contiguous slices merge into one box. Fill y from bottom to top: half of the voxel layer -4 .. 0
(a full layer would render at +2, above the road; see terrain.note in the config).

Checks (asserted, on the rounded output rows): every piece inside the target envelope; no piece on a building box,
prop, sidewalk, corner fill or apron (> 0.01 studs^2); no piece deeper than road_overlap + 0.02 under a road surface;
no two pieces overlapping outside the 0.1 rim of one of them; tops flush (|top - road_top| <= 0.02); chunk parts <= max_parts_per_chunk;
determinism (two runs, byte-identical modules).
Drive check (before / after): the built Sukhumvit edges' polylines sampled every drive.step studs, lateral offsets
drive.offsets, a car_width x car_length footprint (6 wheel points: 4 corners + the 2 side middles); a sample is
supported when every point lies on a surface whose top is within height_tol of the road top (slab, fill, disc,
apron, shoulder; a sidewalk 1.6 or corner fill 1.58 is not, the terrain -2 is not).
Writes <build-root>/shoulders/: roblox/manifest.luau + roblox/chunk_s<cx>_<cz>[_k].luau (512-stud chunks of the
map-local piece centroid, <= 600 parts each, batches of <= 8 chunks nearest focus_world first), shoulders.json
(analysis, counts, checks, drive before / after, top spots), shoulder_check_*.png. Nothing else is touched.
Map data (c) OpenStreetMap contributors, ODbL 1.0.
"""
import argparse, hashlib, json, math, os, re, sys, time
from collections import Counter, defaultdict

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools', 'qa'))
import road_check as rc  # noqa: E402  (PattayaBuilder geometry, ported 1:1)
import junction_aprons as ja  # noqa: E402  (world loader: roads, sidewalks, discs, buildings, props, furniture)
import road_seams as rs  # noqa: E402  (apron layer loader: the PattayaApronBuilder pieces)

CLASS_RE = re.compile(r'\{ id = "([^"]+)", way = \d+, class = "([^"]*)"')
KIND_CODE = {'shoulder': 1, 'taper': 2, 'gap': 3}
CODE_KIND = {v: k for k, v in KIND_CODE.items()}


def find_build_root(arg=None):
    if arg:
        return os.path.abspath(arg)
    p = ROOT
    for _ in range(6):                      # a worktree under <main>/.claude/worktrees/<name> has no build/ of its own
        if os.path.isdir(os.path.join(p, 'build', 'pattaya_wide')):
            return os.path.join(p, 'build')
        p = os.path.dirname(p)
    sys.exit('build/ not found; pass --build-root')


def unit(v):
    n = math.hypot(v[0], v[1])
    return np.array([v[0] / n, v[1] / n]) if n > 1e-12 else np.array([1.0, 0.0])


def polys_of(g):
    return ja.polys_of(g)


def world(cfg, x, z):
    o = cfg['origin_world']
    return [round(float(x) + o[0], 1), round(float(z) + o[2], 1)]


def diff(a, b):
    """a - b, robust (snap to a 0.001 grid when GEOS finds a non-noded intersection)"""
    if b is None or b.is_empty:
        return a
    try:
        return a.difference(b)
    except shapely.errors.GEOSException:
        a, b = shapely.make_valid(a), shapely.make_valid(b)
        try:
            return a.difference(b)
        except shapely.errors.GEOSException:
            return shapely.difference(a, b, grid_size=0.001)


def inter(a, b):
    """a & b, robust (as diff)"""
    try:
        return a.intersection(b)
    except shapely.errors.GEOSException:
        a, b = shapely.make_valid(a), shapely.make_valid(b)
        try:
            return a.intersection(b)
        except shapely.errors.GEOSException:
            return shapely.intersection(a, b, grid_size=0.001)


def shrink_prev(polys, d=0.05):
    """the union of earlier pieces, each shrunk by d (so a new piece overlaps them by <= d: same height and style, no
    seam for a ray); a sliver that the shrink would eat is kept whole"""
    out = []
    for p in polys:
        q = p.buffer(-d, join_style=2)
        out.append(q if not q.is_empty and q.area > 0.5 * p.area else p)
    return unary_union(out)


def plen(p):
    return float(np.linalg.norm(np.diff(np.asarray(p, float), axis=0), axis=1).sum())


# ---- inputs ----------------------------------------------------------------------------------------------------------
def load(cfg, broot):
    """the world as the builders build it (junction_aprons.load_world), the apron layer, edge classes and targets"""
    # landmarks are read here (exact rotated footprints of the parts that reach down to the road), not by
    # junction_aprons.load_world (it uses a bounding circle for every rotated part: a market roof 16 studs up became
    # a 38-stud circle over the road edge)
    W = ja.load_world(dict(cfg, inputs=dict(cfg['inputs'], landmarks='__landmarks_read_by_road_shoulders__')), broot)
    lm = landmark_footprints(cfg, broot)
    W['props'] += lm
    W['props_tree'] = STRtree(W['props']) if W['props'] else None
    W['stats']['landmark part footprints'] = len(lm)
    cls = {}
    for ds, rel in cfg['inputs']['datasets']:
        d = os.path.join(broot, rel)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.startswith('chunk_') and f.endswith('.luau'):
                for m in CLASS_RE.finditer(open(os.path.join(d, f), encoding='utf-8').read()):
                    cls[m.group(1)] = m.group(2)
    W['aprons'], W['corners'] = [], []
    adir = os.path.join(broot, cfg['inputs']['aprons'])
    if os.path.isdir(adir):
        for poly, top, kind, junction, tilt in rs.load_aprons(adir):
            W['aprons' if kind == 'apron' else 'corners'].append(poly)
    else:
        W['stats']['apron layer missing'] += 1
    W['aprons_tree'] = STRtree(W['aprons']) if W['aprons'] else None
    W['corners_tree'] = STRtree(W['corners']) if W['corners'] else None
    W['class'] = cls
    T = cfg['targets']
    names, classes = set(T['names']), set(T['classes'])
    trunk = [e for e in W['edges'] if (e.get('label') or '') in names and cls.get(e['id']) in classes]
    tl = unary_union([LineString(e['pts']) for e in trunk]) if trunk else None
    near = []
    for e in W['edges']:
        c = cls.get(e['id'])
        if c in T['near_classes'] and e not in trunk and tl is not None and LineString(e['pts']).distance(tl) <= T['near_classes'][c]:
            near.append(e)
    tg = trunk + near
    if T.get('bboxes_world'):
        o = cfg['origin_world']
        bxs = [box(b[0] - o[0], b[1] - o[2], b[2] - o[0], b[3] - o[2]) for b in T['bboxes_world']]
        tg = [e for e in tg if any(LineString(e['pts']).intersects(b) for b in bxs)]
    tg = sorted(tg, key=lambda e: e['id'])
    for e in tg:
        e['target_kind'] = 'trunk' if e in trunk else cls.get(e['id'])
    W['targets'] = tg
    W['trunk_ids'] = {e['id'] for e in trunk}
    return W


def euler_yxz(rx, ry, rz):
    """rotation matrix of CFrame.fromEulerAnglesYXZ(rx, ry, rz) = Ry * Rx * Rz"""
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Ry @ Rx @ Rz


def landmark_footprints(cfg, broot):
    """footprint (convex hull of the rotated box, x / z) of every landmark part whose lowest point is less than
    landmark_reach studs above the road top (rows: name, shape, sx, sy, sz, x, y, z, rx, ry, rz, ...)"""
    d = os.path.join(broot, cfg['inputs']['landmarks'])
    out = []
    if not os.path.isdir(d):
        return out
    reach = cfg['clearance'].get('landmark_reach_studs', 4.0)
    corners = np.array([[i, j, k] for i in (-0.5, 0.5) for j in (-0.5, 0.5) for k in (-0.5, 0.5)])
    for f in sorted(os.listdir(d)):
        if not f.startswith('chunk_l'):
            continue
        for r in ja.read_rows(open(os.path.join(d, f), encoding='utf-8').read(), 'parts', 15):
            size, pos = np.array(r[2:5]), np.array(r[5:8])
            c = (euler_yxz(r[8], r[9], r[10]) @ (corners * size).T).T + pos
            if c[:, 1].min() > cfg['road_top'] + reach:
                continue
            out.append(shapely.MultiPoint([tuple(v) for v in c[:, [0, 2]]]).convex_hull.buffer(0))
    return [p for p in out if not p.is_empty]


def near(W, key, geom):
    return ja.near(W, key, geom)


def discs_near(W, geom):
    return [W['disc_polys'][i] for i in sorted(W['disc_tree'].query(geom))]


class Excl:
    """exclusion geometry around a query region (local unions from the STR trees)"""

    def __init__(self, cfg, W):
        self.cfg, self.W = cfg, W
        self.CL, self.C = cfg['clearance'], cfg['clean']

    def roads(self, g):
        return unary_union(near(self.W, 'roads', g) + discs_near(self.W, g))

    def hard(self, g, terrain=False):
        """everything a shoulder must stay clear of (with clearance), except road surfaces"""
        W, CL = self.W, self.CL
        bl_c = self.cfg['terrain']['building_studs'] if terrain else CL['building_studs']
        pr_c = self.cfg['terrain']['prop_studs'] if terrain else CL['prop_studs']
        parts = [b.buffer(bl_c, join_style=2) for b in near(W, 'blds', g)]
        parts += [p.buffer(pr_c, quad_segs=4) for p in near(W, 'props', g)]
        parts += [w.buffer(CL['walk_studs'], join_style=2) for w in near(W, 'walks', g)]
        parts += [a.buffer(CL['apron_studs'], join_style=2) for a in near(W, 'aprons', g) + near(W, 'corners', g)]
        return unary_union(parts) if parts else None

    def region(self, g):
        """g minus road surfaces (shrunk by road_overlap: the piece tucks under the slab edge) minus hard exclusions"""
        r = self.roads(g.buffer(1.0))
        out = g
        if not r.is_empty:
            core = r.buffer(-self.C['road_overlap_studs'], join_style=2)
            if not core.is_empty:
                out = diff(out, core)
        h = self.hard(g.buffer(1.0))
        if h is not None and not h.is_empty:
            out = diff(out, h)
        return out


class Placed:
    """pieces placed so far, on a 64-stud grid"""
    G = 64.0

    def __init__(self):
        self.polys, self.grid = [], defaultdict(list)

    def add(self, poly):
        x0, z0, x1, z1 = poly.bounds
        for gx in range(math.floor(x0 / self.G), math.floor(x1 / self.G) + 1):
            for gz in range(math.floor(z0 / self.G), math.floor(z1 / self.G) + 1):
                self.grid[(gx, gz)].append(len(self.polys))
        self.polys.append(poly)

    def near(self, geom):
        x0, z0, x1, z1 = geom.bounds
        ids = set()
        for gx in range(math.floor(x0 / self.G), math.floor(x1 / self.G) + 1):
            for gz in range(math.floor(z0 / self.G), math.floor(z1 / self.G) + 1):
                ids.update(self.grid.get((gx, gz), ()))
        return [self.polys[i] for i in sorted(ids)]


# ---- geometry helpers ------------------------------------------------------------------------------------------------
def joint_ext(pts, half):
    """Builder.stripe's stretch at each joint for a stripe of half width `half`"""
    n = len(pts)
    ext = [0.0] * n
    for j in range(1, n - 1):
        d1, d2 = unit(pts[j] - pts[j - 1]), unit(pts[j + 1] - pts[j])
        turn = math.acos(max(-1.0, min(1.0, float(d1 @ d2))))
        ext[j] = min(half * math.tan(turn / 2), half)
    return ext


def band_rects(pts, width, S, overlap):
    """[(side, segment index, Polygon)] of the shoulder bands of one slab piece"""
    pts = np.asarray(pts, float)
    H = width / 2 + S
    ext = joint_ext(pts, H)
    out = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        if math.hypot(*(b - a)) <= 0.05:
            continue
        d = unit(b - a)
        n = np.array([-d[1], d[0]])
        a2, b2 = a - d * ext[i], b + d * ext[i + 1]
        for side in (-1, 1):
            lo, hi = side * (width / 2 - overlap), side * H
            out.append((side, i, Polygon([a2 + n * lo, b2 + n * lo, b2 + n * hi, a2 + n * hi])))
    return out


def resample(pts, step=1.0):
    p = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    keep = np.concatenate([[True], seg > 1e-6])
    p = p[keep]
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.unique(np.concatenate([np.arange(0, s[-1], step), [s[-1]]]))
    xy = np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1)
    return xy, t


def normals(xy):
    t = np.gradient(xy, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1), 1e-9)[:, None]
    return np.stack([-t[:, 1], t[:, 0]], axis=1)


def cleanup(g, T):
    """opening (drops slivers thinner than 2 x open_studs), clipped back to the region"""
    if g is None or g.is_empty:
        return g
    o = T['open_studs']
    g = shapely.make_valid(g) if not g.is_valid else g
    h = inter(g.buffer(-o, join_style=2).buffer(o, join_style=2), g)
    return inter(h.simplify(0.01, preserve_topology=True), h) if not h.is_empty else h


def pieces_of(poly, T):
    """junction_aprons.pieces_of (one box for a rectangle, else constrained-Delaunay triangles), but a box only when
    the fitted rectangle really matches the polygon: is_rect accepts corners within 1 deg of square, which on a
    100-stud shoulder strip can put the far end 0.9 studs off (onto the neighbour)"""
    out = ja.pieces_of(poly, T)
    if len(out) == 1 and out[0][0] == 'box':
        if ja.piece_poly('box', out[0][1]).hausdorff_distance(poly) <= 0.02:
            return out
        out = []
        for t in polys_of(shapely.constrained_delaunay_triangles(poly)):
            c = list(t.exterior.coords)[:3]
            longest = max(math.dist(c[i], c[(i + 1) % 3]) for i in range(3))
            if t.area >= T['min_tri_area'] and 2 * t.area / longest >= T['min_tri_altitude']:
                out.append(('tri', [c[0][0], c[0][1], c[1][0], c[1][1], c[2][0], c[2][1]]))
    return out


def piece_poly(kind, v):
    return ja.piece_poly(kind, v)


def rnd(kind, v):
    return ja.rnd(kind, v)


def wedge_count(v):
    return ja.wedge_count(v)


# ---- topology: ends, continuations, width changes --------------------------------------------------------------------
def ends_at(W):
    """{node: [(edge, end, dir_away_from_node, centre point)]} for the built target edges"""
    E = defaultdict(list)
    for e in W['targets']:
        if e['hidden']:
            continue
        p = e['pts']
        if len(p) < 2:
            continue
        E[e['a']].append((e, 'a', unit(p[1] - p[0]), p[0]))
        E[e['b']].append((e, 'b', unit(p[-2] - p[-1]), p[-1]))
    return E


def oriented(e, end):
    """the edge's polyline pointing away from its `end` node"""
    return e['pts'] if end == 'a' else e['pts'][::-1]


def width_changes(cfg, W, E):
    """every node where a target edge continues (turn <= max_turn_deg) into a narrower target edge"""
    Tp = cfg['taper']
    out = []
    for node in sorted(E):
        arms = E[node]
        for i, (ei, endi, di, pi) in enumerate(arms):
            for j, (ej, endj, dj, pj) in enumerate(arms):
                if i == j or ej is ei:
                    continue
                din = -di                     # travel direction arriving at the node along ei
                turn = math.degrees(math.acos(max(-1.0, min(1.0, float(din @ dj)))))
                if turn > Tp['max_turn_deg'] or ei['width'] - ej['width'] < Tp['min_width_change']:
                    continue
                out.append(dict(node=int(node), wide=ei['id'], narrow=ej['id'], w1=ei['width'], w2=ej['width'],
                                turn=round(turn, 1), x=float(pj[0]), z=float(pj[1]), din=din, dout=dj,
                                wide_end=endi, narrow_end=endj, ei=ei, ej=ej))
    return out


def chain(W, E, e, end, L, max_turn):
    """polyline of length <= L starting at e's `end` node, continuing through the best target continuation"""
    pts = [np.asarray(oriented(e, end), float)]
    total = plen(pts[0])
    cur, cur_end, seen = e, end, {e['id']}
    while total < L:
        far = cur['b'] if cur_end == 'a' else cur['a']
        tail = pts[-1]
        dlast = unit(tail[-1] - tail[-2])
        best = None
        for (ek, endk, dk, pk) in E.get(far, []):
            if ek['id'] in seen:
                continue
            turn = math.degrees(math.acos(max(-1.0, min(1.0, float(dlast @ dk)))))
            if turn <= max_turn and (best is None or turn < best[0]):
                best = (turn, ek, endk)
        if best is None:
            break
        _, ek, endk = best
        q = np.asarray(oriented(ek, endk), float)
        pts.append(q[1:])
        total += plen(q)
        cur, cur_end = ek, endk
        seen.add(ek['id'])
    line = np.vstack(pts)
    if plen(line) > L:
        xy, t = resample(line, 0.5)
        line = xy[t <= L + 1e-9]
    return line


def taper_polys(cfg, W, E, wc):
    """the taper region (both sides) of one width change"""
    S, Tp = cfg['shoulder']['width'], cfg['taper']
    h1, h2 = wc['w1'] / 2 + S, wc['w2'] / 2 + S
    L = min(max(Tp['len_per_stud'] * (h1 - h2), Tp['min_len']), Tp['max_len'])
    line = chain(W, E, wc['ej'], wc['narrow_end'], L, Tp['max_turn_deg'])
    if len(line) < 2:
        return None, L
    xy, t = resample(line, 1.0)
    n = normals(xy)
    h = h1 + (h2 - h1) * np.clip(t / L, 0, 1)
    N = np.array([wc['x'], wc['z']])
    din = wc['din']
    nin = np.array([-din[1], din[0]])
    out = []
    for side in (-1, 1):
        edge = xy + n * (side * h)[:, None]
        ring = np.vstack([edge, xy[::-1]])
        p = shapely.make_valid(Polygon(ring))
        fan = shapely.make_valid(Polygon([N, N + nin * side * h1, N + n[0] * side * h1]))
        out += polys_of(p) + polys_of(fan)
    return unary_union(out), L


# ---- the layer -------------------------------------------------------------------------------------------------------
def build(cfg, W):
    S, ov, T = cfg['shoulder']['width'], cfg['clean']['road_overlap_studs'], cfg['clean']
    X = Excl(cfg, W)
    P = Placed()
    pieces = []                 # (kind, piece kind box/tri, row, edge id)
    stats = Counter()
    envelope = []               # nominal + shoulder envelope polygons (for the checks)

    def place(region, kind, eid):
        if region is None or region.is_empty:
            return 0
        reg = region
        prev = P.near(region)
        if prev:
            reg = diff(reg, shrink_prev(prev))
        reg = cleanup(reg, T)
        n = 0
        for p in sorted(polys_of(reg), key=lambda p: (round(p.centroid.x, 2), round(p.centroid.y, 2))):
            if p.area < (T['min_gap_area'] if kind == 'gap' else T['min_piece_area']):
                continue
            if p.interiors and not ja.small_holes(p, T):
                stats[f'{kind} pieces with a large hole (kept, triangulated)'] += 1
            for pk, v in pieces_of(p, T):
                v = rnd(pk, v)
                pieces.append((kind, pk, v, eid))
                P.add(piece_poly(pk, v))
                n += 1
        return n

    # 1. shoulder bands along every built slab piece of the targets
    for e in W['targets']:
        if e['hidden']:
            continue
        for q in rc.slab_pieces(e):
            for side, si, r in band_rects(q, e['width'], S, ov):
                envelope.append(r)
                n = place(X.region(r), 'shoulder', e['id'])
                stats['bands'] += 1
                stats['bands with nothing left'] += n == 0
    # 2. tapers at abrupt narrowings
    E = ends_at(W)
    WC = width_changes(cfg, W, E)
    tapers = []
    for wc in WC:
        tp, L = taper_polys(cfg, W, E, wc)
        if tp is None or tp.is_empty:
            continue
        envelope.append(tp)
        n = place(X.region(tp), 'taper', wc['narrow'])
        tapers.append(dict(node=wc['node'], wide=wc['wide'], narrow=wc['narrow'], w1=wc['w1'], w2=wc['w2'], turn=wc['turn'],
                           length=round(L, 1), world=world(cfg, wc['x'], wc['z']), pieces=n))
    # 3. fills: what is still open inside the full exported polyline's stripe at width + 2 x shoulder (holes in the
    #    carriageway, the stretch of a cut slab end (cutA / cutB) that no other road covers, the shoulder beside it),
    #    and the end bridges: for two target edge ends within bridge_studs whose directions continue (turn <=
    #    max_turn_deg; also two ends at one node) the convex hull of their end cross-sections (+- width/2 + shoulder)
    #    closes the wedge on the outer side of a bend and the seam between two merged slabs that end at different
    #    nodes (no disc there: road_seams end_gap)
    gaps = []
    big = []
    regions = []
    for e in W['targets']:
        if e['hidden']:
            continue
        regions += [(e['id'], r) for r in rc.stripe_rects(e['pts'], e['width'] + 2 * S)]
    ends = [t for node in sorted(E) for t in E[node]]
    bridge = cfg['taper'].get('bridge_studs', 30.0)
    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            (ei, _, di, pi), (ej, _, dj, pj) = ends[i], ends[j]
            if ei is ej or math.hypot(*(pi - pj)) > bridge:
                continue
            turn = math.degrees(math.acos(max(-1.0, min(1.0, float(-di @ dj)))))
            if turn > cfg['taper']['max_turn_deg']:
                continue
            cs = []
            for e_, d_, p_ in ((ei, di, pi), (ej, dj, pj)):
                nn = np.array([-d_[1], d_[0]]) * (e_['width'] / 2 + S)
                cs += [tuple(p_ + nn), tuple(p_ - nn)]
            hull = shapely.MultiPoint(cs).convex_hull
            if hull.geom_type == 'Polygon' and hull.area > 0.25:
                regions.append((ei['id'], hull))
    for eid, r in regions:
        envelope.append(r)
        reg = X.region(r)
        if reg.is_empty:
            continue
        prev = P.near(r)
        if prev:
            reg = diff(reg, shrink_prev(prev))
        reg = cleanup(reg, T)
        for p in polys_of(reg):
            if p.area < 0.25:
                continue
            if p.area > T['max_fill_area']:
                big.append(dict(edge=eid, area=round(p.area, 1), world=world(cfg, p.centroid.x, p.centroid.y)))
                continue
            n = place(p, 'gap', eid)
            if n:
                gaps.append(dict(edge=eid, area=round(p.area, 2), world=world(cfg, p.centroid.x, p.centroid.y)))
    # 4. optional terrain fill boxes outside the shoulders
    terrain = terrain_boxes(cfg, W, X, P)
    return dict(pieces=pieces, tapers=tapers, width_changes=WC, gaps=gaps, big_uncovered=big, terrain=terrain,
                stats=stats, envelope=unary_union(envelope))


def terrain_boxes(cfg, W, X, P):
    Tc, S, ov = cfg['terrain'], cfg['shoulder']['width'], cfg['clean']['road_overlap_studs']
    out = []
    for e in W['targets']:
        if e['hidden']:
            continue
        H = e['width'] / 2 + S
        for q in rc.slab_pieces(e):
            q = np.asarray(q, float)
            for i in range(len(q) - 1):
                a, b = q[i], q[i + 1]
                L = math.hypot(*(b - a))
                if L < Tc['slice_len']:
                    continue
                d = unit(b - a)
                n = np.array([-d[1], d[0]])
                k = int(L // Tc['slice_len'])
                s0 = (L - k * Tc['slice_len']) / 2
                for side in (-1, 1):
                    run = []
                    for j in range(k + 1):
                        ok = False
                        if j < k:
                            c0, c1 = a + d * (s0 + j * Tc['slice_len']), a + d * (s0 + (j + 1) * Tc['slice_len'])
                            r = Polygon([c0 + n * side * H, c1 + n * side * H, c1 + n * side * (H + Tc['width']), c0 + n * side * (H + Tc['width'])])
                            rr = r.buffer(0.5)
                            hit = any(g.intersects(r) for g in near(W, 'roads', rr) + discs_near(W, rr))
                            if not hit:
                                h = X.hard(rr, terrain=True)
                                hit = h is not None and h.intersects(r)
                            ok = not hit
                        if ok:
                            run.append(j)
                        elif run:
                            j0, j1 = run[0], run[-1] + 1
                            ln = (j1 - j0) * Tc['slice_len']
                            cm = a + d * (s0 + (j0 + j1) / 2 * Tc['slice_len']) + n * side * (H + Tc['width'] / 2)
                            out.append([round(cm[0], 3), round(cm[1], 3), round(d[0], 5), round(d[1], 5), round(ln, 3), round(Tc['width'], 3)])
                            run = []
    return out


# ---- checks ----------------------------------------------------------------------------------------------------------
def checks(cfg, W, R):
    bad = Counter()
    ex = defaultdict(list)
    tol = cfg['clean']['road_overlap_studs'] + 0.05
    polys = [piece_poly(pk, v) for _, pk, v, _ in R['pieces']]

    def note(key, p):
        bad[key] += 1
        if len(ex[key]) < 5:
            ex[key].append(world(cfg, p.centroid.x, p.centroid.y))

    env = R['envelope'].buffer(0.05)
    tree = STRtree(polys) if polys else None
    cores = [p.buffer(-0.1, join_style=2) for p in polys]
    for i, p in enumerate(polys):
        if p.area < 0.04:
            note('degenerate piece', p)
        if p.difference(env).area > 0.01:
            note('piece outside the target envelope', p)
        for key, label in (('blds', 'piece on a building box'), ('props', 'piece on a prop footprint'),
                           ('walks', 'piece on a sidewalk strip'), ('aprons', 'piece on an apron'),
                           ('corners', 'piece on a corner fill')):
            for q in near(W, key, p):
                if p.intersects(q) and p.intersection(q).area > 0.01:
                    note(label, p)
                    break
        for q in near(W, 'roads', p) + discs_near(W, p):
            if p.intersects(q):
                core = q.buffer(-tol, join_style=2)
                if not core.is_empty and p.intersection(core).area > 0.05:
                    note('piece deeper than road_overlap under a road surface', p)
                    break
        for j in tree.query(p):          # neighbours may overlap in the 0.05 rim of one of the two (+ rounding)
            if j > i and p.intersects(polys[j]):
                ci, cj = cores[i], cores[j]
                if (not ci.is_empty and ci.intersection(polys[j]).area > 0.01) and (not cj.is_empty and cj.intersection(p).area > 0.01):
                    note('two pieces overlap', p)
                    break
    if abs(cfg['shoulder']['top'] - cfg['road_top']) > 0.02:
        note('shoulder top not flush with the road top', Point(0, 0))
    return bad, ex


# ---- edge analysis (deliverable 1) -----------------------------------------------------------------------------------
class Surface:
    """highest-top lookup over the built surfaces (+ optional extra pieces)"""

    def __init__(self, cfg, W, extra=None):
        polys, tops, kinds = [], [], []
        for key, top in (('roads', 1.0), ('aprons', 0.98), ('corners', 1.58), ('walks', 1.6)):
            polys += W[key]
            tops += [top] * len(W[key])
            kinds += [key] * len(W[key])
        polys += W['disc_polys']
        tops += [0.99] * len(W['disc_polys'])
        kinds += ['discs'] * len(W['disc_polys'])
        for p in extra or []:
            polys.append(p)
            tops.append(cfg['shoulder']['top'])
            kinds.append('shoulder')
        self.polys, self.tops, self.kinds = polys, np.array(tops), kinds
        self.tree = STRtree(polys)
        self.bld_tree = STRtree(W['blds']) if W['blds'] else None
        self.ground = cfg['ground_y']

    def top(self, P, contact=0.0):
        """highest surface top over each point; contact > 0: any surface within that distance (a tyre's patch)"""
        pts = shapely.points(P[:, 0], P[:, 1])
        res = np.full(len(P), self.ground)
        if contact > 0:
            qi, si = self.tree.query(pts, predicate='dwithin', distance=contact)
        else:
            qi, si = self.tree.query(pts, predicate='intersects')
        np.maximum.at(res, qi, self.tops[si])
        return res

    def in_building(self, P):
        out = np.zeros(len(P), bool)
        if self.bld_tree is not None:
            out[self.bld_tree.query(shapely.points(P[:, 0], P[:, 1]), predicate='intersects')[0]] = True
        return out


def samples(pts, step):
    return rs.polyline_samples(pts, step)


def runs_of(mask):
    """[(i0, i1)] of the True runs of a boolean array (i1 exclusive)"""
    out, i0 = [], None
    for i, v in enumerate(mask):
        if v and i0 is None:
            i0 = i
        elif not v and i0 is not None:
            out.append((i0, i))
            i0 = None
    if i0 is not None:
        out.append((i0, len(mask)))
    return out


def analysis(cfg, W, R=None, step=2.0):
    """where the built target slab edges meet the terrain, width changes, slab cuts and hole candidates"""
    Sf = Surface(cfg, W)
    tg = [e for e in W['targets'] if not e['hidden']]
    edge_stats = Counter()
    exposed_runs = []
    for e in tg:
        for q in rc.slab_pieces(e):
            xy, tan, s = samples(q, step)
            L = plen(q)
            keep = (s > 0.5) & (s < L - 0.5)
            xy, tan = xy[keep], tan[keep]
            if not len(xy):
                continue
            n = np.stack([-tan[:, 1], tan[:, 0]], axis=1)
            for side in (-1, 1):
                P = xy + n * side * (e['width'] / 2 + 1.0)
                t = Sf.top(P)
                bl = Sf.in_building(P)
                cls = np.where(t > 1.3, 'raised', np.where(t > 0.5, 'road', np.where(bl, 'building', 'terrain')))
                for c, v in Counter(cls.tolist()).items():
                    edge_stats[c] += v * step
                    edge_stats[f'{e["target_kind"]}:{c}'] += v * step
                for i0, i1 in runs_of(cls == 'terrain'):
                    m = P[(i0 + i1) // 2]
                    exposed_runs.append(dict(edge=e['id'], kind=e['target_kind'], width=e['width'], side=side,
                                             length=round((i1 - i0) * step, 1), world=world(cfg, m[0], m[1])))
    exposed_runs.sort(key=lambda r: -r['length'])
    total = sum(edge_stats[k] for k in ('raised', 'road', 'building', 'terrain'))
    cuts = []
    for e in tg:
        for end, key in (('a', 'cutA'), ('b', 'cutB')):
            c = e.get(key) or 0.0
            if c > 0:
                L = plen(e['pts'])
                xy, _ = resample(e['pts'], 0.5)
                s = np.linspace(0, L, len(xy))
                at = c if end == 'a' else L - c
                k = int(np.argmin(abs(s - at)))
                cuts.append(dict(edge=e['id'], kind=e['target_kind'], end=end, cut=c, width=e['width'],
                                 world=world(cfg, xy[k][0], xy[k][1])))
    E = ends_at(W)
    WC = width_changes(cfg, W, E)
    seams = {}
    sp = os.path.join(W.get('broot', ''), cfg['inputs']['road_seams'])
    if os.path.exists(sp):
        js = json.load(open(sp, encoding='utf-8'))
        near_s = [f for f in js['findings'] if f.get('near_sukhumvit')]
        seams = dict(counts=dict(Counter(f['class'] for f in near_s)),
                     top=[dict(cls=f['class'], world=[f['world_x'], f['world_z']], why=f['why'][:110]) for f in near_s
                          if f['class'] in ('gap', 'end_gap', 'narrowing', 'sliver')][:15])
    return dict(
        target_edges=dict(built=len(tg), hidden=sum(1 for e in W['targets'] if e['hidden']),
                          by_kind=dict(Counter(e['target_kind'] for e in tg)),
                          built_length=round(sum(plen(e['pts']) for e in tg)),
                          sidewalk_edges=sum(1 for e in tg if e['sidewalk'] > 0),
                          widths=dict(Counter(str(e['width']) for e in tg))),
        edge_sides_studs={k: round(v) for k, v in sorted(edge_stats.items())},
        edge_sides_exposed_fraction=round(edge_stats['terrain'] / total, 3) if total else None,
        exposed_runs=dict(count=len(exposed_runs), longest=exposed_runs[:12]),
        width_changes=dict(count=len(WC), list=[dict(node=w['node'], w1=w['w1'], w2=w['w2'], turn=w['turn'], wide=w['wide'],
                                                       narrow=w['narrow'], world=world(cfg, w['x'], w['z'])) for w in WC]),
        slab_cuts=dict(count=len(cuts), list=sorted(cuts, key=lambda c: -c['cut'])[:20]),
        road_seams_near_sukhumvit=seams)


# ---- drive check -----------------------------------------------------------------------------------------------------
def drive(cfg, W, extra=None, which='trunk', footprint='spec'):
    """per lateral offset: samples, supported, unsupported (+ positions) along the built target polylines.
    footprint 'spec': car_width x car_length, 6 points (4 corners + 2 side middles); 'car': the 4 suspension ray
    origins of the default race car (RaceCarServer DEFAULT_LAYOUT mounts, lateral x longitudinal)"""
    D = cfg['drive']
    Sf = Surface(cfg, W, extra)
    if which == 'trunk':
        lines = [e for e in W['targets'] if not e['hidden'] and e['id'] in W['trunk_ids']]
    elif which == 'link':
        lines = [e for e in W['targets'] if not e['hidden'] and e['id'] not in W['trunk_ids']]
    else:
        lines = [e for e in W['targets'] if e['hidden'] and e['id'] in W['trunk_ids']]
    hw, hl, tol, top = D['car_width'] / 2, D['car_length'] / 2, D['height_tol'], cfg['road_top']
    cr = D.get('contact_radius', 0.0)
    wheels = [(-hl, -hw), (-hl, hw), (hl, -hw), (hl, hw), (0, -hw), (0, hw)]
    if footprint == 'car':
        wheels = [(lo, la) for la, lo in D['car_wheels']]
    res = {}
    for o in D['offsets']:
        n_s, bad_xy, in_s, in_b, bad_in = 0, [], 0, 0, []
        for e in lines:
            xy, tan, s = samples(e['pts'], D['step'])
            if not len(xy):
                continue
            nrm = np.stack([-tan[:, 1], tan[:, 0]], axis=1)
            C = xy + nrm * o
            ok = np.ones(len(C), bool)
            for lo, la in wheels:
                t = Sf.top(C + tan * lo + nrm * la, cr)
                ok &= np.abs(t - top) <= tol
            n_s += len(C)
            bad_xy.append(C[~ok])
            if abs(o) <= e['width'] / 2:          # the car centre is on the slab: a lane position the road has
                in_s += len(C)
                in_b += int((~ok).sum())
                bad_in.append(C[~ok])
        B = np.vstack(bad_xy) if bad_xy else np.zeros((0, 2))
        res[o] = dict(samples=n_s, supported=n_s - len(B), unsupported=len(B), bad=B,
                      bad_in=np.vstack(bad_in) if bad_in else np.zeros((0, 2)),
                      in_lane=dict(samples=in_s, unsupported=in_b))
    return res


def spots(cfg, res, k=12, cell=40.0, key='bad'):
    """unsupported sample clusters (cell grid), biggest first, with world coordinates and offsets
    (key 'bad_in': only samples whose centre is on the slab)"""
    cnt, xs, offs = Counter(), defaultdict(list), defaultdict(set)
    for o, r in res.items():
        for x, z in r[key]:
            c = (int(x // cell), int(z // cell))
            cnt[c] += 1
            xs[c].append((x, z))
            offs[c].add(o)
    out = []
    for c, n in cnt.most_common(k):
        m = np.mean(xs[c], axis=0)
        out.append(dict(samples=n, world=world(cfg, m[0], m[1]), offsets=sorted(offs[c])))
    return out


def drive_summary(res):
    return {str(o): dict(samples=r['samples'], supported=r['supported'], unsupported=r['unsupported'],
                         in_lane_samples=r['in_lane']['samples'], in_lane_unsupported=r['in_lane']['unsupported'])
            for o, r in res.items()}


# ---- output ----------------------------------------------------------------------------------------------------------
def fmt(v):
    return ja.fmt(v)


def lua_str(s):
    return ja.lua_str(s)


def render(cfg, R):
    """module texts {path: text}; pure function of R (determinism)"""
    C = cfg['chunk_size_studs']
    cap = cfg['budget']['max_parts_per_chunk']
    ch = defaultdict(list)
    for kind, pk, v, eid in R['pieces']:
        p = piece_poly(pk, v).centroid
        ch[f's{math.floor(p.x / C)}_{math.floor(p.y / C)}'].append((kind, pk, v))
    terr = defaultdict(list)
    for v in R['terrain']:
        terr[f's{math.floor(v[0] / C)}_{math.floor(v[1] / C)}'].append(v)
    # split a chunk over the part cap into _2, _3 ... modules (same 512 cell)
    mods = {}
    for c in sorted(set(ch) | set(terr)):
        lst, cur, n, k = ch.get(c, []), [], 0, 1
        groups = []
        for item in lst:
            m = 1 if item[1] == 'box' else wedge_count(item[2])
            if n + m > cap and cur:
                groups.append(cur)
                cur, n = [], 0
            cur.append(item)
            n += m
        groups.append(cur)
        for gi, g in enumerate(groups):
            mods[c if gi == 0 else f'{c}_{gi + 1}'] = dict(cell=c, items=g, terrain=terr.get(c, []) if gi == 0 else [])
    fx, fz = cfg['focus_world'][0] - cfg['origin_world'][0], cfg['focus_world'][1] - cfg['origin_world'][2]

    def cell_xy(c):
        a, b = c[1:].split('_')[:2]
        return (int(a) + 0.5) * C, (int(b) + 0.5) * C
    order = sorted(mods, key=lambda c: (round(math.hypot(cell_xy(c)[0] - fx, cell_xy(c)[1] - fz), 3), c))
    sh, tc = cfg['shoulder'], cfg['terrain']
    files, per_chunk, counts = {}, {}, Counter()
    for c in order:
        d = mods[c]
        boxes = [v + [KIND_CODE[k]] for k, pk, v in d['items'] if pk == 'box']
        tris = [v + [KIND_CODE[k]] for k, pk, v in d['items'] if pk == 'tri']
        n = len(boxes) + sum(wedge_count(v) for v in tris)
        for k, pk, v in d['items']:
            counts[f'{k}_pieces'] += 1
            counts[f'{k}_parts'] += 1 if pk == 'box' else wedge_count(v)
        counts['terrain_boxes'] += len(d['terrain'])
        per_chunk[c] = n
        L = [f'-- generated by tools/mapgen/road_shoulders.py from the built road data (build/pattaya_wide etc. chunk modules, '
             f'build/aprons; {cfg["attribution"]}); do not edit',
             f'return {{ id = "{c}",',
             f'  -- boxes {{cx, cz, ux, uz, length, width, kind}}: road-height rectangles (top {sh["top"]}); kind 1 shoulder, 2 taper, 3 gap fill',
             '  boxes = {' + ','.join(fmt(x) for r in boxes for x in r) + '},',
             '  -- tris {x1, z1, x2, z2, x3, z3, kind}: road-height triangles (two WedgeParts each)',
             '  tris = {' + ','.join(fmt(x) for r in tris for x in r) + '},',
             f'  -- terrain {{cx, cz, ux, uz, length, width}}: optional Terrain:FillBlock boxes, y {tc["bottom"]} .. {tc["top"]} (BuildTerrain only)',
             '  terrain = {' + ','.join(fmt(x) for r in d['terrain'] for x in r) + '},',
             f'  parts = {n},',
             '}']
        files[f'roblox/chunk_{c}.luau'] = '\n'.join(L) + '\n'
    B = cfg['budget']['batch_size_chunks']
    batches = {f's{k // B + 1}': order[k:k + B] for k in range(0, len(order), B)}
    border = sorted(batches, key=lambda b: int(b[1:]))
    total = sum(per_chunk.values())
    man = ['-- generated by tools/mapgen/road_shoulders.py; do not edit. Road shoulders, width tapers and carriageway hole',
           '-- fills along Sukhumvit Road (pilot). Built by ServerStorage.PattayaShoulderBuilder (Build / BuildTerrain / Probe / Remove).',
           'return {',
           '  name = "shoulders",',
           f'  attribution = {lua_str(cfg["attribution"])},',
           '  source = "build/pattaya_wide/roblox (+ central, corridor), build/aprons/roblox, furniture / coast / landmarks",',
           f'  roadTop = {fmt(cfg["road_top"])}, groundY = {fmt(cfg["ground_y"])}, chunkSize = {C}, maxPartsPerChunk = {cap},',
           f'  shoulder = {{ top = {fmt(sh["top"])}, thick = {fmt(sh["thick"])}, material = "{sh["material"]}", '
           f'color = {{{",".join(map(str, sh["color"]))}}}, name = "{sh["name"]}", overlap = {fmt(cfg["clean"]["road_overlap_studs"])} }},',
           f'  terrain = {{ top = {fmt(tc["top"])}, bottom = {fmt(tc["bottom"])}, material = "{tc["material"]}" }},',
           '  kinds = {"shoulder", "taper", "gap"},',
           '  chunks = {' + ','.join(lua_str(c) for c in order) + '},',
           '  batchOrder = {' + ','.join(lua_str(b) for b in border) + '},',
           '  batches = {']
    for b in border:
        man.append(f'    {b} = {{' + ','.join(lua_str(c) for c in batches[b]) + '},')
    man.append('  },')
    man.append(f'  counts = {{ pieces = {len(R["pieces"])}, parts = {total}, shoulderParts = {counts["shoulder_parts"]}, '
               f'taperParts = {counts["taper_parts"]}, gapParts = {counts["gap_parts"]}, terrainBoxes = {counts["terrain_boxes"]} }},')
    man.append('}')
    files['roblox/manifest.luau'] = '\n'.join(man) + '\n'
    return dict(files=files, order=order, batches=batches, per_chunk=per_chunk, total=total, counts=dict(counts))


def digest(files):
    h = hashlib.sha1()
    for k in sorted(files):
        h.update(k.encode())
        h.update(files[k].encode())
    return h.hexdigest()


def check_image(cfg, W, R, name, cx, cz, rad, path, bad_before=None, bad_after=None):
    from PIL import Image, ImageDraw
    Sc = max(1, int(900 / (2 * rad)))
    win = box(cx - rad, cz - rad, cx + rad, cz + rad)
    im = Image.new('RGB', (int(2 * rad * Sc), int(2 * rad * Sc)), (96, 74, 52))
    dr = ImageDraw.Draw(im)
    Tf = lambda p: ((p[0] - cx + rad) * Sc, (cz + rad - p[1]) * Sc)   # north (+z) up

    def fill(polys, col, outline=None):
        for p in polys:
            for q in polys_of(p.intersection(win.buffer(5))):
                dr.polygon([Tf(c) for c in q.exterior.coords], fill=col, outline=outline)
    fill(near(W, 'blds', win), (120, 120, 150))
    fill(near(W, 'roads', win), (55, 56, 62))
    fill(discs_near(W, win), (55, 56, 62))
    fill(near(W, 'aprons', win), (230, 120, 30))
    fill(near(W, 'walks', win) + near(W, 'corners', win), (170, 168, 160))
    col = {'shoulder': (240, 220, 60), 'taper': (230, 60, 230), 'gap': (60, 220, 240)}
    for kind, pk, v, _ in R['pieces']:
        p = piece_poly(pk, v)
        if p.intersects(win):
            fill([p], col[kind], (40, 40, 40))
    for v in R['terrain']:
        p = piece_poly('box', v)
        if p.intersects(win):
            for q in polys_of(p.intersection(win)):
                dr.polygon([Tf(c) for c in q.exterior.coords], outline=(150, 255, 120))
    fill(near(W, 'props', win), (40, 160, 60))
    for B, colr in ((bad_before, (255, 140, 140)), (bad_after, (255, 0, 0))):
        if B is not None and len(B):
            for x, z in B[(abs(B[:, 0] - cx) < rad) & (abs(B[:, 1] - cz) < rad)]:
                u, v = Tf((x, z))
                dr.rectangle([u - 1, v - 1, u + 1, v + 1], fill=colr)
    o = cfg['origin_world']
    dr.text((6, 6), f'{name}: world ({cx + o[0]}, {cz + o[2]}) +-{rad}, north up. shoulder yellow, taper magenta, gap fill cyan, '
            f'terrain boxes green outline, aprons orange; unsupported car samples: before pink, after red', fill=(255, 255, 255))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--build-root')
    ap.add_argument('--no-determinism', action='store_true')
    ap.add_argument('--analysis-only', action='store_true')
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))
    broot = find_build_root(a.build_root)
    t0 = time.time()
    W = load(cfg, broot)
    W['broot'] = broot
    print(f'loaded: {len(W["edges"])} edges, {len(W["roads"])} road parts, {len(W["aprons"])} apron / {len(W["corners"])} corner '
          f'pieces, {len(W["targets"])} target edges ({sum(1 for e in W["targets"] if not e["hidden"])} built) ({time.time() - t0:.0f} s)')
    A = analysis(cfg, W)
    before = drive(cfg, W)
    if a.analysis_only:
        print(json.dumps(A, ensure_ascii=False, indent=1))
        print(json.dumps(drive_summary(before), indent=1))
        return
    R = build(cfg, W)
    out = render(cfg, R)
    bad, ex = checks(cfg, W, R)
    over = [c for c, n in out['per_chunk'].items() if n > cfg['budget']['max_parts_per_chunk']]
    if over:
        bad['chunk over the part cap'] += len(over)
    det = None
    if not a.no_determinism:
        W2 = load(cfg, broot)
        det = digest(render(cfg, build(cfg, W2))['files']) == digest(out['files'])
    polys = [piece_poly(pk, v) for _, pk, v, _ in R['pieces']]
    after = drive(cfg, W, polys)
    link_b, link_a = drive(cfg, W, which='link'), drive(cfg, W, polys, which='link')
    hid_b, hid_a = drive(cfg, W, which='hidden'), drive(cfg, W, polys, which='hidden')
    car_b, car_a = drive(cfg, W, footprint='car'), drive(cfg, W, polys, footprint='car')
    od = os.path.join(broot, cfg['out_dir'])
    rd = os.path.join(od, 'roblox')
    os.makedirs(rd, exist_ok=True)
    for f in os.listdir(rd):
        if f.startswith('chunk_s') or f == 'manifest.luau':
            os.remove(os.path.join(rd, f))
    for k, txt in out['files'].items():
        open(os.path.join(od, k), 'w', encoding='utf-8', newline='\n').write(txt)
    area = Counter()
    for kind, pk, v, _ in R['pieces']:
        area[kind] += piece_poly(pk, v).area
    rep = dict(attribution=cfg['attribution'], counts=out['counts'], parts=out['total'], chunks=len(out['order']),
               batches=out['batches'], batch_order=sorted(out['batches'], key=lambda b: int(b[1:])),
               largest_chunk=max(out['per_chunk'].items(), key=lambda t: t[1]) if out['per_chunk'] else None,
               area_studs2={k: round(v) for k, v in area.items()}, digest=digest(out['files']), deterministic=det,
               analysis=A, tapers=R['tapers'], gaps=dict(count=len(R['gaps']), list=sorted(R['gaps'], key=lambda g: -g['area'])[:20]),
               big_uncovered=R['big_uncovered'], stats=dict(R['stats']), load_stats=dict(W['stats']),
               checks=dict(bad), check_examples=dict(ex), chunks_over_part_cap=over,
               drive=dict(params=cfg['drive'], sukhumvit=dict(before=drive_summary(before), after=drive_summary(after)),
                          sukhumvit_car_wheels=dict(before=drive_summary(car_b), after=drive_summary(car_a)),
                          spots_after_car_wheels=spots(cfg, car_a), spots_in_lane_before_car_wheels=spots(cfg, car_b, key='bad_in'),
                          spots_in_lane_after_car_wheels=spots(cfg, car_a, key='bad_in'),
                          spots_in_lane_after=spots(cfg, after, key='bad_in'),
                          trunk_link=dict(before=drive_summary(link_b), after=drive_summary(link_a)),
                          hidden_carriageways=dict(before=drive_summary(hid_b), after=drive_summary(hid_a)),
                          spots_before=spots(cfg, before), spots_after=spots(cfg, after)))
    json.dump(rep, open(os.path.join(od, 'shoulders.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    bb = np.vstack([r['bad'] for r in before.values()])
    ba = np.vstack([r['bad'] for r in after.values()])
    for name, cx, cz, rad in cfg.get('check_images', []):
        check_image(cfg, W, R, name, cx, cz, rad, os.path.join(od, f'shoulder_check_{name}.png'), bb, ba)
    c = out['counts']
    print(f'pieces: shoulder {c.get("shoulder_pieces", 0)} ({c.get("shoulder_parts", 0)} parts), taper {c.get("taper_pieces", 0)} '
          f'({c.get("taper_parts", 0)} parts), gap {c.get("gap_pieces", 0)} ({c.get("gap_parts", 0)} parts); total {out["total"]} parts in '
          f'{len(out["order"])} chunks / {len(out["batches"])} batches; terrain boxes {c.get("terrain_boxes", 0)}; over cap {over}')
    print(f'width changes {len(R["width_changes"])}, tapers {len(R["tapers"])}, gap fills {len(R["gaps"])}, big uncovered {len(R["big_uncovered"])}')
    print(f'checks {dict(bad)} examples {dict(ex)}')
    print(f'determinism {det} digest {rep["digest"]}')
    for o in cfg['drive']['offsets']:
        b, f = before[o], after[o]
        cb, ca = car_b[o], car_a[o]
        print(f'drive offset {o:+4}: samples {b["samples"]:6d} unsupported before {b["unsupported"]:6d} after {f["unsupported"]:6d}'
              f' | in lane {b["in_lane"]["samples"]:6d}: {b["in_lane"]["unsupported"]:5d} -> {f["in_lane"]["unsupported"]:5d}'
              f' | car wheels: {cb["unsupported"]:5d} -> {ca["unsupported"]:5d}, in lane {cb["in_lane"]["unsupported"]:5d} -> {ca["in_lane"]["unsupported"]:5d}')
    print(f'done in {time.time() - t0:.0f} s -> {od}')
    if any(bad.values()) or det is False:
        sys.exit(1)


if __name__ == '__main__':
    main()
