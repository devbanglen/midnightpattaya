"""Road B for the whole city, batch by batch (team20/road-city, 2026-10-22). OFFLINE: nothing here touches Studio.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py plan          -> build/roadcity/plan.json (+ numbers)
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py batch b001    -> build/roadcity/b001/ (Studio data, QA)

Why a city version: the pilot generator (junction.generate) builds ONE area and tapers its new asphalt toward the old
roads outside it. Batches built one after the other must instead meet exactly. So:

1. The ideal road. Every batch draws the same ideal Road B surface (design B, docs/ROAD_VISUAL_SPEC.md): asphalt
   ribbons from the WHOLE-city carriageway chains (one dash phase per chain city-wide), kerb returns, islands, kerbed
   sidewalks, lane / centre / edge markings, stop lines and zebras on junction legs. It is computed in a window (the
   batch box + 300 studs, wider than any rule reaches), then cut at the batch box. Two batches that share an edge cut
   the same ideal road at the same line, so they meet with no hole and no step. Cuts keep their vertices exactly on
   the box edge (simplification never moves a vertex that lies on the edge). Markings: a dash, stop line or zebra bar
   belongs to the batch that holds its midpoint; continuous lines and kerb strips are cut at the box edge.
2. Who owns an old part. A batch replaces every old road-layer part (WideChunks / Chunks road, sidewalk, dash, centre;
   junction and joint discs; aprons and corner fills; zebra bars) that is still in the place and whose footprint
   centre lies in its box, or whose footprint overlaps the box by 1 stud^2 or more. So the first batch built over a
   part that straddles a box edge replaces it whole. The part of its footprint outside the box is rebuilt at once as
   "frontier" pieces (asphalt at 1.0, sidewalk at 1.6), cut per neighbouring box and tagged with that box's batch id,
   so the old road outside keeps every stud it had. The batch of that box replaces those pieces when it is built.
   ShoulderChunks is never a candidate. The pilot (RoadVisPilot) is treated like old parts where it reaches into a
   batch box (its parts that overlap the box are replaced, and the part of them inside the pilot box is rebuilt).
3. The pilot seam. The pilot box tapers toward the old roads in its 40-stud seam band. The batch next to it completes
   that band: ideal asphalt and sidewalk the pilot left out there (pieces owned by the batch, inside the pilot box).
4. Order. A batch's data is made for one build order (the plan). The Studio builder checks the order (which
   neighbours must be built and which must not) before it does anything. Remove is last-in first-out per
   neighbourhood.

Map-local studs everywhere (world = local + (20000, 0, 0)) unless a name says world. Map data (c) OpenStreetMap
contributors, ODbL 1.0.
"""
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from tools.roadvis import export_luau, ground, junction, world  # noqa: E402
from tools.roadvis.junction import clean, closing, lines_of, polys  # noqa: E402

ORIGIN = world.ORIGIN
GRID0 = (24220.0, 650.0)          # world: the pilot box corner. Batch cells are CELL x CELL on this grid
CELL = 600.0
PILOT_BOX_WORLD = (24220.0, 650.0, 24820.0, 1250.0)
WINDOW = 300.0                    # the ideal is computed in the batch box + WINDOW
OVERLAP_MIN = 1.0                 # an old part overlapping a box by this much (studs^2) is replaced by that box's batch
UNCERTAIN = 0.15                  # +- band around OVERLAP_MIN (and 0.01 around a box edge for centres): optional keys
SEAM_BAND = 40.0                  # the pilot's seam band (junction.CFG seam_band)
PROBE_PAD = 30.0                  # probe samples reach this far past the box (the seams are probed)
CFG = dict(junction.CFG, design='B',
           # markings (docs/ROAD_B_CITY_ROLLOUT.md, parts): the defaults are the pilot's / batch 1's design
           mark_simplify=0.25,      # polyline tolerance of continuous lines (edge, centre)
           kerb_simplify=0.3,       # polyline tolerance of the kerb strips
           edge_lines=True,         # white edge lines along kerbed edges
           kerb_strips=True,        # light kerb-stone strips on the sidewalk edge
           centre_double=True,      # two yellow centre lines (False: one line of the same width on the centre)
           # option B: no invisible RoadSupport wedge where the ground is raised to the plateau (+0.9): a wheel there
           # meets the ground 0.1 below the asphalt, so the old part the support stood in for is no longer a drop
           drop_supports_on_ground=False)
MAIN_CLASSES = ('trunk', 'trunk_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link')
# instance budget variants (docs/ROAD_B_CITY_ROLLOUT.md, budget): 'full' = the pilot's design everywhere (kerbed
# sidewalks and a double centre line on every road); 'lean' = sidewalks and centre lines only on the main classes
# (residential / unclassified sois meet the raised ground; most Thai sois have neither); 'lean2' = lean with the
# collision outlines simplified 0.5 instead of 0.25
VARIANTS = {
    'full': dict(drop_supports_on_ground=True),
    'lean': dict(walk_classes=MAIN_CLASSES, centre_classes=MAIN_CLASSES, drop_supports_on_ground=True),
    'lean2': dict(walk_classes=MAIN_CLASSES, centre_classes=MAIN_CLASSES, coll_simplify=0.5, drop_supports_on_ground=True),
}
DEFAULT_VARIANT = 'lean'
# batches whose data is frozen (shipped and checked by the leader): their own settings win over the variant, so their
# data stays byte for byte the same (b001: rv 021dd07c..., ground ab0c4b22..., made before option B)
FROZEN = {'b001': dict(walk_classes=MAIN_CLASSES, centre_classes=MAIN_CLASSES, drop_supports_on_ground=False,
                       mark_simplify=0.25, kerb_simplify=0.3, edge_lines=True, kerb_strips=True, centre_double=True,
                       dash=8.0, dash_gap=12.0, zebra_bar=2.0, zebra_gap=2.0, coll_simplify=0.25)}
SECOND = ('b003',)                # build right after b001 (b003 finishes the owner's second screenshot spot); ids stay
ROAD_CODES = (1, 5, 6, 7)         # Road (slab, fill), Junction, Joint, Apron: asphalt class (rebuilt at 1.0)
WALK_CODES = (2, 8)               # Sidewalk, CornerFill: sidewalk class (rebuilt at 1.6)
MARK_CODES = (3, 4, 9)            # Dash, Centre, ZebraStripe: paint (not rebuilt)
OLD_TOP = {1: 1.0, 2: 1.6, 5: 0.99, 6: 0.99, 7: 0.98, 8: 1.58}
TRI_CODE = {1: 11, 2: 12, 3: 13, 4: 14, 5: 15}          # RoadVis triangle parts (pilot / city): 10 + tri kind
SEG_CODE = {k: 20 + k for k in range(1, 7)}             # RoadVis segment parts: 20 + seg kind
CODE_LABEL = {v: k for k, v in export_luau.CODES.items()}
CODE_LABEL.update({11: 'RV Road', 12: 'RV Sidewalk', 13: 'RV Island', 14: 'RV Grass', 15: 'RV RoadSupport',
                   21: 'RV Dash', 22: 'RV Centre', 23: 'RV EdgeLine', 24: 'RV StopLine', 25: 'RV ZebraStripe', 26: 'RV Kerb'})
TRI_TOP = {1: 1.0, 2: 1.6, 3: 1.45, 4: 1.46, 5: 1.0}


def wloc(b):
    """world box -> local box"""
    return (b[0] - ORIGIN[0], b[1] - ORIGIN[1], b[2] - ORIGIN[0], b[3] - ORIGIN[1])


def cell_box_world(i, k):
    x0, z0 = GRID0[0] + CELL * i, GRID0[1] + CELL * k
    return (x0, z0, x0 + CELL, z0 + CELL)


def cell_of_world(x, z):
    return int(math.floor((x - GRID0[0]) / CELL)), int(math.floor((z - GRID0[1]) / CELL))


def in_box(x, z, b):
    """half-open box test (x0 <= x < x1, z0 <= z < z1): every point belongs to exactly one grid box"""
    return b[0] <= x < b[2] and b[1] <= z < b[3]


def near_edge(x, z, b, tol=0.01):
    return min(abs(x - b[0]), abs(x - b[2]), abs(z - b[1]), abs(z - b[3])) < tol


# ---- the city: old parts, the pilot as built, global chains ------------------------------------------------------------
class CityWorld:
    """everything the batches are made from, loaded once: the built world (world.load, whole city, only the shoulder
    chunks installed in the place), every old road-layer part with its footprint box (the replace key) and its real
    shape, the pilot's parts exactly as built (its installed cell modules) and its replace list, the city-wide
    carriageway chains and ribbons"""

    def __init__(self, broot=None, log=print):
        W = world.load(broot, bbox=None)
        W['surf'] = [s for s in W['surf'] if not (s['kind'] in world.SHOULDER_KINDS and s.get('module') not in ground.SHOULDER_INSTALLED)]
        self.W = W
        self.broot = W['broot']
        self.old = old_parts_full(W)
        self.old_tree = STRtree([o['key'] for o in self.old])
        self.blds = W['blds']
        self.bld_tree = STRtree([b['poly'] for b in self.blds])
        sh = [s for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS]
        self.shoulders = sh
        self.sh_tree = STRtree([s['poly'] for s in sh]) if sh else None
        self.pilot = pilot_parts(self.broot)
        self.pilot_tree = STRtree([p['shape'] for p in self.pilot['parts']])
        self.pilot_replaced = match_keys(self.old, self.pilot['keys'])
        G = W['graph']
        self.chains = junction.chains_of(G, box(-1e7, -1e7, 1e7, 1e7))
        self.rib = {c['id']: junction.ribbon(c) for c in self.chains}
        self.rib_tree = STRtree([self.rib[c['id']][0] for c in self.chains])
        self.evidence = [np.array(c['row'][:2]) for c in W['crossings']]
        log(f"city world: {len(W['edges'])} edges, {len(self.old)} old parts, {len(self.chains)} chains, "
            f"{len(self.pilot['parts'])} pilot parts, pilot replaced {len(self.pilot_replaced)} of {len(self.pilot['keys'])} keys")

    def buildings(self, g):
        return [self.blds[i] for i in self.bld_tree.query(g) if self.blds[int(i)]['poly'].intersects(g)]

    def shoulder_union(self, g):
        if self.sh_tree is None:
            return Polygon()
        return unary_union([self.shoulders[int(i)]['poly'] for i in self.sh_tree.query(g)])

    def chains_near(self, g):
        idx = sorted(int(i) for i in self.rib_tree.query(g))
        return [self.chains[i] for i in idx if self.rib[self.chains[i]['id']][0].intersects(g)]


def old_parts_full(W):
    """every candidate Part of the old road layers: dict(code, key = footprint box (what RV.MoveReplaced measures),
    shape = the real footprint (triangle for a WedgePart, circle for a disc), cls 'road' | 'walk' | 'mark', top).
    Same enumeration and order as export_luau.old_parts."""
    rc, rf, rs = world.rc, world.rf, world.rs
    import road_fix
    root = os.path.dirname(W['broot'])
    edges, discs, jrs, _f, gaps = road_fix.load(root)
    out = []

    def add(code, key, shape, cls):
        if key is None or shape is None:
            return
        out.append(dict(code=code, key=key, shape=shape, cls=cls, top=OLD_TOP.get(code)))

    seen = set()
    for e in edges:
        if e['id'] in seen:
            continue
        seen.add(e['id'])
        jr = jrs[e['ds']]
        for q in rc.slab_pieces(e):
            for p in rc.stripe_rects(q, e['width']):
                add(1, p, p, 'road')
        for t in rc.fill_polys(e):
            c = np.asarray(t.exterior.coords)[:3]
            for p, _ in rs.wedge_tris(c[0], c[1], c[2]):
                add(1, export_luau.wedge_rect(p), p, 'road')
        for p in rc.sidewalk_rects(e, jr):
            add(2, p, p, 'walk')
        offs = rf.mark_offsets(e)
        if offs:
            total = rf.plen(e['pts'])
            for lo, hi in rf.mark_pieces(e, jr):
                inner = rc.trim(e['pts'], lo, total - hi)
                if inner is None:
                    continue
                for d, kind in offs:
                    q = rc.offset(inner, d)
                    if kind == 'centre':
                        for p in rc.stripe_rects(q, 0.45):
                            add(4, p, p, 'mark')
                    else:
                        for a, b in rf.dash_segments(q, 8, gaps[e['ds']]):
                            p = world.seg_poly(a, b, 0.5)
                            add(3, p, p, 'mark')
    dseen = set()
    for (ds, k), (x, z, rr) in sorted(discs.items(), key=lambda kv: str(kv[0])):
        kind = 'Joint' if isinstance(k, tuple) else 'Junction'
        n = k[1] if isinstance(k, tuple) else k
        if (kind, n) in dseen:
            continue
        dseen.add((kind, n))
        add(export_luau.CODES[kind], box(x - rr, z - rr, x + rr, z + rr), Point(x, z).buffer(rr, 32), 'road')
    adir = os.path.join(W['broot'], 'aprons', 'roblox')
    if os.path.isdir(adir):
        for poly, top, kind, jn, tilt in rs.load_aprons(adir):
            code = export_luau.CODES['Apron'] if kind == 'apron' else export_luau.CODES['CornerFill']
            key = export_luau.wedge_rect(poly) if len(poly.exterior.coords) == 4 else poly
            add(code, key, poly, 'road' if kind == 'apron' else 'walk')
    for c in W['crossings']:
        for b in c['bars']:
            add(9, b, b, 'mark')
    for i, o in enumerate(out):
        o['i'] = i
        o['c'] = (o['key'].centroid.x, o['key'].centroid.y)
    return out


def match_keys(parts, keys, tol=0.3):
    """indices of `parts` matched one to one to replace keys [(code, x local, z)] (RV.Plan's rule: same code, centre
    within tol in x and z)"""
    grid = defaultdict(list)
    for p in parts:
        grid[(p['code'], math.floor(p['c'][0]), math.floor(p['c'][1]))].append(p['i'])
    used = set()
    for code, x, z in keys:
        hit = None
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for j in grid.get((code, math.floor(x) + dx, math.floor(z) + dz), []):
                    if hit is None and j not in used and abs(parts[j]['c'][0] - x) <= tol and abs(parts[j]['c'][1] - z) <= tol:
                        hit = j
        if hit is not None:
            used.add(hit)
    return used


def pilot_parts(broot):
    """the pilot as built in the place: every Part its installed modules make (build/roadvis/roblox, the 7 cell modules
    in ServerStorage.PattayaDataRoadVis), with its exact footprint (wedge triangle / marking rectangle), the key centre
    (the Part's Position) and the code; plus the pilot's replace keys (782)"""
    sys.path.insert(0, os.path.join(REPO, 'tools', 'circuit'))
    try:
        import luau_table
    finally:
        sys.path.pop(0)
    d = os.path.join(broot, 'roadvis', 'roblox')
    man = luau_table.load(os.path.join(d, 'manifest.luau'))
    parts = []

    def lst(v):
        return v.get('_list', []) if isinstance(v, dict) else (v or [])

    alts = []                                   # wedges / marks Studio's float32 split may have made instead
    for name in lst(man['modules']):
        m = luau_table.load(os.path.join(d, name + '.luau'))
        t = lst(m.get('tris'))
        for i in range(0, len(t), 7):
            k = int(t[i + 6])
            row = [float(v) for v in t[i:i + 6]]
            amb = split_ambiguous(row)
            mine = []
            for poly, _ in world.rs.wedge_tris(row[0:2], row[2:4], row[4:6]):
                r = export_luau.wedge_rect(poly)
                mine.append((r.centroid.x, r.centroid.y))
                parts.append(dict(code=TRI_CODE[k], kind=k, shape=poly, key=r, c=(r.centroid.x, r.centroid.y), top=TRI_TOP[k],
                                  module=name, seg=False, amb=amb))
            if amb:
                for poly in split_variants(row):
                    r = export_luau.wedge_rect(poly)
                    if all(math.hypot(r.centroid.x - x, r.centroid.y - z) > 0.01 for x, z in mine):
                        alts.append(dict(code=TRI_CODE[k], shape=poly, c=(r.centroid.x, r.centroid.y), module=name))
        s = lst(m.get('segs'))
        for i in range(0, len(s), 6):
            a, b, w, k = (s[i], s[i + 1]), (s[i + 2], s[i + 3]), s[i + 4], int(s[i + 5])
            p = world.seg_poly(a, b, w)
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            if p is None:
                continue
            if ln < 0.05:
                if ln > 0.05 - AMBIG:
                    alts.append(dict(code=SEG_CODE[k], shape=p, c=(p.centroid.x, p.centroid.y), module=name))
                continue
            parts.append(dict(code=SEG_CODE[k], kind=k, shape=p, key=p, c=(p.centroid.x, p.centroid.y), top=None,
                              module=name, seg=True, row=[a[0], a[1], b[0], b[1], w], amb=ln < 0.05 + AMBIG))
    for i, p in enumerate(parts):
        p['i'] = i
    K = lst(man['replace']['keys'])
    keys = [(int(K[i]), K[i + 1] - ORIGIN[0], K[i + 2]) for i in range(0, len(K), 3)]
    return dict(parts=parts, keys=keys, counts=man['counts'], bbox=list(lst(man['bbox'])), alts=alts)


# ---- geometry helpers ------------------------------------------------------------------------------------------------
def simplify_locked(g, tol, lock):
    """simplify every ring of g with tolerance tol, but never move or drop a vertex that lies on `lock` (a line
    geometry, e.g. the batch box boundary): two batches that cut the same polygon at a shared edge keep the same edge"""
    if g is None or g.is_empty:
        return Polygon()
    shapely.prepare(lock)
    out = []
    for p in polys(g):
        rings = []
        for ring in [p.exterior] + list(p.interiors):
            c = np.asarray(ring.coords)[:-1]
            if len(c) < 3:
                continue
            on = shapely.dwithin(lock, shapely.points(c), 1e-6)
            if not on.any():
                s = np.asarray(LineString(np.vstack([c, c[:1]])).simplify(tol).coords)[:-1]
                if len(s) >= 3:
                    rings.append(s)
                continue
            k0 = int(np.argmax(on))
            c = np.roll(c, -k0, axis=0)
            on = np.roll(on, -k0)
            idx = list(np.nonzero(on)[0]) + [len(c)]
            cc = np.vstack([c, c[:1]])
            pts = []
            for a, b in zip(idx[:-1], idx[1:]):
                seg = cc[a:b + 1]
                if b - a >= 2:
                    seg = np.asarray(LineString(seg).simplify(tol).coords)
                pts += [tuple(q) for q in seg[:-1]]
            if len(pts) >= 3:
                rings.append(np.asarray(pts))
        if not rings:
            continue
        try:
            q = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3])
        except Exception:
            continue
        out.append(q if q.is_valid else shapely.make_valid(q))
    return clean(unary_union(out)) if out else Polygon()


def triangles_of(g):
    """constrained-Delaunay triangles of g (no further simplification)"""
    return junction.triangles(g, simplify=0)


def clip_line(line, B):
    g = line.intersection(B)
    return lines_of(g)


# ---- 1. the ideal road in a window ------------------------------------------------------------------------------------
def ideal(CW, win, cfg=None):
    """design B with no seam: the layers of junction.generate (design B) for every carriageway chain near the window
    polygon `win`, from the city-wide chains; nothing is tapered, nothing depends on old parts. Returns dict of
    shapely layers + marks + crossings (map-local)."""
    cfg = dict(CFG, **(cfg or {}))
    G = CW.W['graph']
    area = win
    chains = CW.chains_near(win.buffer(150))
    rib = CW.rib
    ALL = CW.chains                                    # index = chain id
    zones = junction.junction_zones(G, chains, rib, area, cfg)
    zones.sort(key=lambda z: min(z['nodes']))
    Z = unary_union([z['poly'] for z in zones]) if zones else Polygon()
    blds = unary_union([b['poly'] for b in CW.buildings(area.buffer(50))])
    ends = defaultdict(list)
    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        for node, k in ((c['a'], 0), (c['b'], -1)):
            nrm = np.array([-T[k][1], T[k][0]])
            ends[node] += [tuple(Q[k] + nrm * hw[k]), tuple(Q[k] - nrm * hw[k])]
    hulls = [MultiPoint(v).convex_hull for n, v in sorted(ends.items()) if len(v) >= 4]
    S0 = unary_union([rib[c['id']][0] for c in chains] + hulls).intersection(area.buffer(120))
    lane_corr = S0
    base = S0
    fil = closing(base, cfg['kerb_r']).difference(base).intersection(Z.buffer(cfg['kerb_r']))
    S1 = clean(unary_union([base, fil]))
    gaps = closing(S1, cfg['island_gap']).difference(S1)
    holes = [Polygon(r) for p in polys(S1) for r in p.interiors]
    small = unary_union([h for h in holes if h.area < cfg['island_hole_max']] + [gaps]) if holes or not gaps.is_empty else Polygon()
    islands = clean(small.difference(blds.buffer(0.5)))
    S1 = clean(S1.difference(blds.buffer(1.0)))
    S = clean(S1.intersection(area))
    islands = clean(islands.intersection(area).difference(S))
    paved = unary_union([S, islands])
    walk = paved.buffer(cfg['sidewalk_w'], quad_segs=8).difference(paved).difference(blds.buffer(0.5))
    walk = clean(walk.intersection(area))
    if cfg.get('walk_classes'):
        # budget option: sidewalks only along carriageways of these classes (and islands); other roads meet the ground
        keep = unary_union([rib[c['id']][0] for c in chains if (c.get('cls') or '') in cfg['walk_classes']] + [islands])
        walk = clean(walk.intersection(keep.buffer(cfg['sidewalk_w'] + 1.0, quad_segs=4)))
    shoulders = CW.shoulder_union(area.buffer(5)).intersection(area.buffer(5))
    if cfg['keep_shoulders_flush'] and not shoulders.is_empty:
        sh_closed = shoulders.buffer(cfg['shoulder_joint'], join_style='mitre').buffer(-cfg['shoulder_joint'], join_style='mitre')
        sh_closed = unary_union([sh_closed, shoulders])
        walk = clean(walk.difference(sh_closed.difference(S)))
        islands = clean(islands.difference(sh_closed))
        islands = clean(unary_union([q for q in polys(islands) if q.area > 4.0]))
        walk = clean(unary_union([q for q in polys(walk) if q.area > 4.0]))
        near_paved = unary_union([S, islands]).buffer(0.5)
        walk = clean(unary_union([q for q in polys(walk) if q.intersects(near_paved)]))
    kerb = clean(walk.intersection(paved.buffer(cfg['kerb_w'])))
    island_kerb = clean(islands.difference(islands.buffer(-cfg['kerb_w'])))
    green = clean(unary_union([q for q in polys(islands.buffer(-(cfg['kerb_w'] + 2.0))) if q.area > 60]))

    # ---- markings (junction.generate, without the seam cut)
    seeds, labels, have = [], [], set()
    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        for k in range(1, len(Q) - 1, 2):
            key = (round(float(Q[k][0]), 1), round(float(Q[k][1]), 1))
            if key in have:
                continue
            have.add(key)
            seeds.append(tuple(Q[k]))
            labels.append(c['id'])
    own = {}
    if seeds:
        vor = shapely.voronoi_polygons(MultiPoint(seeds), extend_to=area.buffer(400), ordered=True)
        cells = defaultdict(list)
        for lab, cell in zip(labels, vor.geoms):
            cells[lab].append(cell)
        own = {lab: clean(unary_union(v).buffer(0.05, join_style='mitre').buffer(-0.05, join_style='mitre').intersection(rib[lab][0]))
               for lab, v in cells.items()}
    inner_asph = S.buffer(-1.0)
    J = junction.junction_field(chains, rib, Z, cfg)
    noZ = J.buffer(1.0)
    marks = []

    def add(kind, geom, w):
        g = geom.intersection(inner_asph).difference(noZ).difference(islands.buffer(0.5))
        for l in lines_of(g):
            if l.length > (0.6 if kind in ('stop', 'zebra') else 3.0 if kind == 'lane' else 5.0):
                marks.append(dict(kind=kind, poly=l.buffer(w / 2, cap_style='flat', join_style='mitre', mitre_limit=2.0), line=l))

    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        own_c = own.get(c['id'], Polygon()).buffer(-0.8)
        nl = max(min(c['lanes']), 1)
        if c['oneway']:
            bounds = [('lane', (lambda k: (lambda a, k=k: (k - nl / 2) * 2 * np.interp(a, s, hw) / nl))(k)) for k in range(1, nl)]
        else:
            bounds = []
            if cfg.get('centre_classes') is None or (c.get('cls') or '') in cfg['centre_classes']:
                if cfg.get('centre_double', True):
                    bounds = [('centre', lambda a: cfg['centre_gap'] / 2), ('centre', lambda a: -cfg['centre_gap'] / 2)]
                else:
                    bounds = [('centre', lambda a: 0.0)]
            bounds += [('lane', (lambda k, sg: (lambda a, k=k, sg=sg: sg * k * 2 * np.interp(a, s, hw) / nl))(k, sg))
                       for k in range(1, nl // 2) for sg in (1, -1)]
        for kind, off in bounds:
            f = junction.offset_point_fn(Q, T, s, off)
            if kind == 'centre':
                g = LineString([tuple(f(a)) for a in s]).intersection(own_c)
                add('centre', g, 0.45)
            else:
                segs = junction.dash_line(Q, s, f, cfg['dash'], cfg['dash_gap'])
                g = unary_union([LineString([tuple(a), tuple(b)]) for a, b in segs]).intersection(own_c) if segs else Polygon()
                add('lane', g, cfg['line_w'])
    ids = sorted(own)
    if ids:
        tree = STRtree([own[i] for i in ids])
        for ii, i in enumerate(ids):
            for jj in tree.query(own[i].buffer(0.5)):
                j = ids[int(jj)]
                if j <= i:
                    continue
                A, B = ALL[i], ALL[j]
                shared = own[i].boundary.intersection(own[j].buffer(0.05)).intersection(own[j].boundary.buffer(0.05))
                shared = shapely.line_merge(unary_union(lines_of(shared))) if not shared.is_empty else shared
                if shared.is_empty:
                    continue
                mid = shared.interpolate(0.5, normalized=True) if hasattr(shared, 'interpolate') else None
                if mid is None:
                    continue
                ta = rib[i][2][int(np.argmin(np.linalg.norm(rib[i][1] - [mid.x, mid.y], axis=1)))]
                tb = rib[j][2][int(np.argmin(np.linalg.norm(rib[j][1] - [mid.x, mid.y], axis=1)))]
                opposite = (not A['oneway']) or (not B['oneway']) or float(ta @ tb) < 0
                if opposite:
                    for d in ((-cfg['centre_gap'] / 2, cfg['centre_gap'] / 2) if cfg.get('centre_double', True) else (0.0,)):
                        for l in lines_of(shared):
                            try:
                                ls_ = l.simplify(cfg['separator_simplify'])
                                add('centre', ls_ if d == 0.0 else ls_.offset_curve(d), 0.45)
                            except Exception:
                                pass
    walk_or_island = unary_union([walk, islands])
    kerbside = walk_or_island.buffer(cfg['edge_inset'] + 1.5)
    for q in polys(S.buffer(-cfg['edge_inset'])):
        for ring in [q.exterior] + list(q.interiors):
            add('edge', LineString(ring.coords).intersection(kerbside), cfg['line_w'])

    # ---- crossings + stop lines (junction.generate, legs inside the window)
    evidence = CW.evidence
    crossings, stops, quads = [], [], []
    paved_ok = unary_union([S, islands]).buffer(0.1)
    inner_win = area.buffer(-10)
    for zi, z in enumerate(zones):
        others = unary_union([q['poly'] for qi, q in enumerate(zones) if qi != zi]) if len(zones) > 1 else Polygon()
        others = unary_union([others, J.difference(z['poly'].buffer(2.0))])
        for a in z['arms']:
            c = ALL[a['chain']]
            poly, Q, T, hw, s = rib[c['id']]
            if a['end'] == 'b':
                Qa, Ta, sa, ha = Q[::-1], -T[::-1], (s[-1] - s)[::-1], hw[::-1]
            else:
                Qa, Ta, sa, ha = Q, T, s, hw
            k = a['k']
            while k < len(Qa) - 1 and z['poly'].buffer(1.0).contains(Point(Qa[k])):
                k += 1
            mouth_s = float(sa[k])
            dist = mouth_s + 1.0 + cfg['zebra_depth'] / 2
            has_ev = any(np.linalg.norm(e - Qa[k]) < cfg['crossing_evidence'] for e in evidence)
            kk = int(np.searchsorted(sa, dist))
            keep_x, rec = False, None
            if has_ev and kk < len(Qa) - 1 and inner_win.contains(Point(Qa[kk])):
                p, t = Qa[kk], Ta[kk]
                across = np.array([-t[1], t[0]])
                ray = LineString([tuple(p - across * 220), tuple(p + across * 220)])
                segs = sorted([g for g in lines_of(ray.intersection(S)) if g.length > 0.5], key=lambda g: ray.project(Point(g.coords[0])))
                idx = [i for i, g in enumerate(segs) if g.distance(Point(p)) < 0.6]
                if idx:
                    lo = hi = idx[0]
                    gap = lambda u, v: LineString([segs[u].coords[-1], segs[v].coords[0]])  # noqa: E731
                    while lo > 0 and gap(lo - 1, lo).length < 30 and islands.buffer(0.6).contains(gap(lo - 1, lo)):
                        lo -= 1
                    while hi < len(segs) - 1 and gap(hi, hi + 1).length < 30 and islands.buffer(0.6).contains(gap(hi, hi + 1)):
                        hi += 1
                    e1, e2 = np.array(segs[lo].coords[0]), np.array(segs[hi].coords[-1])
                    span = float(np.linalg.norm(e2 - e1))
                    quad = Polygon([e1 - t * cfg['zebra_depth'] / 2, e2 - t * cfg['zebra_depth'] / 2,
                                    e2 + t * cfg['zebra_depth'] / 2, e1 + t * cfg['zebra_depth'] / 2])
                    lands = [walk_or_island.buffer(1.5).contains(Point(q)) for q in (e1, e2)]
                    rec = dict(zone=z['nodes'][0], chain=c['id'], name=c['name'], p=p, t=t, e1=e1, e2=e2, span=span,
                               lands=lands, evidence=True, mouth_s=mouth_s, quad=quad)
                    keep_x = (all(lands) and span <= cfg['zebra_max_span'] and quad.intersection(others).area < 1.0
                              and quad.difference(paved_ok).area < 2.0 and not any(quad.buffer(2.0).intersects(q) or (quad.distance(q) < 25 and abs(float(t @ x['t'])) > 0.9)
                                          for q, x in zip(quads, crossings)))
            inbound = (a['end'] == 'b') if c['oneway'] else True
            sdist = (dist + cfg['zebra_depth'] / 2 + 2.0) if keep_x else mouth_s + 2.0
            for step in range(31):
                ks = int(np.searchsorted(sa, sdist + 2.0 * step))
                if not (inbound and ks < len(Qa) - 1 and inner_win.contains(Point(Qa[ks]))):
                    break
                ps, ts = Qa[ks], Ta[ks]
                nrm = np.array([-ts[1], ts[0]])
                h = float(ha[ks])
                if c['oneway']:
                    q1, q2 = ps + nrm * (h - 1.2), ps - nrm * (h - 1.2)
                else:
                    lft = junction.left_of(-ts)
                    q1, q2 = ps + lft * (cfg['centre_gap'] / 2 + 0.3), ps + lft * (h - 1.2)
                sp = LineString([tuple(q1), tuple(q2)]).buffer(cfg['stop_w'] / 2, cap_style='flat')
                if any(sp.intersects(q) for q in quads) or not S.buffer(0.05).contains(sp):
                    break
                if sp.intersection(others).area < 0.5:
                    stops.append(dict(kind='stop', poly=sp, line=LineString([tuple(q1), tuple(q2)])))
                    break
            if keep_x:
                crossings.append(rec)
                quads.append(rec['quad'])
    xmarks = []
    for x in crossings:
        across = junction.unit(x['e2'] - x['e1'])
        t = x['t']
        L = x['span'] - 2 * cfg['zebra_inset']
        n = int((L + cfg['zebra_gap']) // (cfg['zebra_bar'] + cfg['zebra_gap']))
        used = n * (cfg['zebra_bar'] + cfg['zebra_gap']) - cfg['zebra_gap']
        start = x['e1'] + across * (cfg['zebra_inset'] + (L - used) / 2)
        bars = []
        for i in range(n):
            c0 = start + across * (i * (cfg['zebra_bar'] + cfg['zebra_gap']) + cfg['zebra_bar'] / 2)
            bar = world.seg_poly(c0 - t * cfg['zebra_depth'] / 2, c0 + t * cfg['zebra_depth'] / 2, cfg['zebra_bar'])
            if bar is not None and S.buffer(0.05).contains(bar):
                bars.append(bar)
        x['bars'] = bars
        xmarks += [dict(kind='zebra', poly=b) for b in bars]
    block = unary_union([m['poly'] for m in xmarks + stops]).buffer(1.0) if xmarks or stops else Polygon()
    out_marks = []
    for m in marks:
        p = m['poly'].difference(block)
        if p.is_empty or p.area <= 0.2:
            continue
        line = m.get('line')
        if line is not None and not block.is_empty:
            line = line.difference(block)
        out_marks.append(dict(m, poly=p, line=line))
    marks = out_marks + stops + xmarks
    return dict(win=win, chains=chains, rib=rib, zones=zones, Z=Z, J=J, S=S, walk=walk, islands=islands, kerb=kerb,
                island_kerb=island_kerb, green=green, marks=marks, crossings=crossings, shoulders=shoulders, blds=blds,
                lane_corridor=lane_corr, own=own, cfg=cfg)


# ---- 2. one batch ------------------------------------------------------------------------------------------------------
def new_state(CW):
    """the build state of the place before the first city batch: the pilot built (782 parts moved, its own parts in
    RoadVisPilot), nothing else"""
    return dict(built=['pilot'], replaced_old=set(CW.pilot_replaced), uncertain_old=set(), replaced_pilot=set(),
                uncertain_pilot=set(), frontier=defaultdict(list), pilot_completed=Polygon(), pieces={}, seq=0)


def plan_cell_owner(plan):
    """cell (i, k) -> batch id ('pilot' for the pilot cell)"""
    own = {(0, 0): 'pilot'}
    for b in plan['batches']:
        for c in b['cells']:
            own[tuple(c)] = b['id']
    return own


def cells_of_geom(g):
    """grid cells (i, k) whose box intersects the geometry's bounds"""
    x0, z0, x1, z1 = g.bounds
    i0, k0 = cell_of_world(x0 + ORIGIN[0], z0)
    i1, k1 = cell_of_world(x1 + ORIGIN[0], z1)
    return [(i, k) for i in range(i0, i1 + 1) for k in range(k0, k1 + 1)]


def cell_poly(i, k):
    return box(*wloc(cell_box_world(i, k)))


# ---- the builders' triangle split, made the same in Studio --------------------------------------------------------------
# The builders split a triangle into two WedgeParts at the foot of the height on its longest side and skip a side of
# 0.05 stud or less. Studio does that in float32 (Vector2), here it is float64: a triangle whose two longest sides are
# nearly equal, or whose base / height / wedge length is within a hair of 0.05, may be split differently there (other
# part count, other Positions; a later batch finds its frontier pieces by Position). Every row written is made clear of
# both (robust_row); the pilot's built rows that are not clear get extra optional keys (pilot_parts).
TIE = 0.002
AMBIG = 0.004


def split_dims(row):
    """(gap between the two longest sides, base length, height, the two wedge lengths) of the builders' split"""
    a, b, c = (np.asarray(row[i:i + 2], float) for i in (0, 2, 4))
    ab, bc, ca = float(np.linalg.norm(b - a)), float(np.linalg.norm(c - b)), float(np.linalg.norm(a - c))
    s = sorted((ab, bc, ca))
    if bc > ab and bc >= ca:
        a, b, c = b, c, a
    elif ca > ab and ca > bc:
        a, b, c = c, a, b
    ln = float(np.linalg.norm(b - a))
    if ln < 1e-9:
        return s[2] - s[1], 0.0, 0.0, 0.0, 0.0
    d = (b - a) / ln
    foot = a + d * float((c - a) @ d)
    return s[2] - s[1], ln, float(np.linalg.norm(c - foot)), float(np.linalg.norm(foot - a)), float(np.linalg.norm(foot - b))


def split_ambiguous(row):
    """True when Studio's float32 split of triangle row could differ from the one computed here"""
    gap, ln, h, la, lb = split_dims(row)

    def near(v):
        return abs(v - 0.05) < AMBIG
    if near(ln):
        return True
    if ln < 0.05:
        return False                       # skipped either way
    if near(h):
        return True
    if h < 0.05:
        return False
    return gap < TIE or near(la) or near(lb)


def _on_grid(v, axis):
    """a coordinate on a batch grid line (box edges, cell cuts): kept exactly, so seams stay exact"""
    g = (GRID0[0] - ORIGIN[0]) if axis == 0 else (GRID0[1] - ORIGIN[1])
    q = (v - g) / CELL
    return abs(q - round(q)) * CELL < 0.005


_NUDGE = [(dx, dz) for s_ in (0.01, 0.02, 0.03) for dx, dz in ((s_, 0.0), (-s_, 0.0), (0.0, s_), (0.0, -s_))]


def split_variants(row):
    """every WedgePart (corner, foot, apex) a float32 split of triangle row might make"""
    pts = [np.asarray(row[i:i + 2], float) for i in (0, 2, 4)]
    sides = []
    for i in range(3):
        a, b, c = pts[i], pts[(i + 1) % 3], pts[(i + 2) % 3]
        sides.append((float(np.linalg.norm(b - a)), a, b, c))
    top = max(x[0] for x in sides)
    out = []
    for ln, a, b, c in sides:
        if ln < top - TIE or ln < 0.05 - AMBIG:
            continue
        d = (b - a) / ln
        foot = a + d * float((c - a) @ d)
        if float(np.linalg.norm(c - foot)) < 0.05 - AMBIG:
            continue
        for corner in (a, b):
            if float(np.linalg.norm(foot - corner)) > 0.05 - AMBIG:
                out.append(Polygon([corner, foot, c]))
    return out


def robust_row(row):
    """row, or a copy with one vertex moved 0.01 - 0.03 stud (never off a grid line) so the split is clear of the
    float32 doubts; None when no such move exists (the caller drops the triangle: it is a sliver)"""
    if not split_ambiguous(row):
        return row
    for v in (4, 0, 2):
        for dx, dz in _NUDGE:
            if (dx and _on_grid(row[v], 0)) or (dz and _on_grid(row[v + 1], 1)):
                continue
            r2 = list(row)
            r2[v] = export_luau.r(r2[v] + dx)
            r2[v + 1] = export_luau.r(r2[v + 1] + dz)
            if not split_ambiguous(r2):
                return r2
    return None


ROBUST = Counter()                          # nudged / dropped rows (diagnostics)


def _rows_of_tris(tris, kind):
    out = []
    for t in tris:
        c = np.asarray(t.exterior.coords)[:3]
        row = [export_luau.r(v) for v in c.flatten()]
        r2 = robust_row(row)
        if r2 is None:
            ROBUST['dropped'] += 1
            continue
        if r2 is not row:
            ROBUST['nudged'] += 1
            row = r2
        n = len(world.rs.wedge_tris(row[0:2], row[2:4], row[4:6]))
        if n:
            out.append(dict(row=row, kind=kind, n=n, c=t.centroid, tri=Polygon([row[0:2], row[2:4], row[4:6]])))
    return out


def _line_segs(m, tol):
    """export_luau.mark_segs with another polyline tolerance for the continuous lines (the same rules otherwise)"""
    if tol == 0.25:
        return export_luau.mark_segs(m)
    out = []
    kind = m['kind']
    for p in polys(m['poly']):
        ax = export_luau.rect_axis(p.simplify(0.001))
        if ax is not None and (kind in ('zebra', 'stop', 'lane') or p.length < 40):
            out.append((ax[0], ax[1], ax[2]))
            continue
        line = m.get('line')
        if line is None:
            continue
        for l in lines_of(line.intersection(p.buffer(0.05))):
            q = np.asarray(l.simplify(tol).coords)
            for i in range(len(q) - 1):
                if np.linalg.norm(q[i + 1] - q[i]) > 0.3:
                    out.append((q[i], q[i + 1], export_luau.SEG_W.get(kind, 0.5)))
    return [(a, b, w, kind) for a, b, w in out]


def batch_segs(I, BX, bl, cfg):
    """the marking and kerb-strip Parts of a batch (a, b, width, kind): dashes, stop lines and zebra bars by their
    midpoint, continuous lines and kerb strips cut at the box edge. cfg options: mark_simplify, kerb_simplify,
    edge_lines, kerb_strips (the defaults give the pilot's / batch 1's design)"""
    segs = []
    for m in I['marks']:
        if m['kind'] in ('lane', 'stop', 'zebra'):
            for a, bb, w, kind in export_luau.mark_segs(m):
                mid = (np.asarray(a) + np.asarray(bb)) / 2
                if in_box(mid[0], mid[1], bl):
                    segs.append((np.asarray(a), np.asarray(bb), w, kind))
        else:
            if m['kind'] == 'edge' and not cfg.get('edge_lines', True):
                continue
            p = m['poly'].intersection(BX)
            if p.is_empty or p.area < 0.05:
                continue
            line = m.get('line')
            mm = dict(m, poly=p, line=line.intersection(BX) if line is not None else None)
            for a, bb, w, kind in _line_segs(mm, cfg.get('mark_simplify', 0.25)):
                if np.linalg.norm(np.asarray(bb) - np.asarray(a)) > 0.3:
                    segs.append((np.asarray(a), np.asarray(bb), w, kind))
    paved = unary_union([I['S'], I['islands']])
    kerb = I['kerb']
    if not kerb.is_empty and cfg.get('kerb_strips', True):
        tol = cfg.get('kerb_simplify', 0.3)
        for p in polys(paved.buffer(0.5, join_style='mitre')):
            for ring in [p.exterior] + list(p.interiors):
                g = LineString(ring.coords).intersection(kerb.buffer(0.05))
                for l in lines_of(g):
                    for lc in clip_line(l, BX):
                        q = np.asarray(lc.simplify(tol).coords)
                        for i in range(len(q) - 1):
                            if np.linalg.norm(q[i + 1] - q[i]) > 0.5:
                                segs.append((q[i], q[i + 1], 1.0, 'kerb'))
    return segs


def make_batch(CW, plan, st, b, cfg=None, log=print, ground_full=None):
    """the Road B pieces of batch b for the current build state st (st is updated: b becomes built). Returns dict with
    the pieces (own triangles by kind, frontier triangles by target batch, completion triangles in the pilot box,
    segments), the replace selection (required / optional), probe samples, counts. ground_full(poly) -> True where
    every voxel column under poly is raised to the plateau (option B drops the invisible supports there)."""
    cfg = dict(CFG, **(cfg or {}))
    cfg.update(FROZEN.get(b['id'], {}))
    owner = plan_cell_owner(plan)
    bl = wloc(b['box'])
    BX = box(*bl)
    lock = BX.exterior
    win = BX.buffer(WINDOW, join_style='mitre')
    I = ideal(CW, win, cfg)
    built_after = set(st['built']) | {b['id']}

    # ---- replace selection: old parts, pilot parts, frontier pieces tagged for this batch
    rep_old, opt_old = [], []
    for j in CW.old_tree.query(BX):
        o = CW.old[int(j)]
        if o['i'] in st['replaced_old']:
            if o['i'] in st['uncertain_old'] and (o['key'].intersection(BX).area > 0 or in_box(*o['c'], bl)):
                opt_old.append(o)              # an earlier batch may or may not have taken it in Studio
            continue
        cx, cz = o['c']
        inside = in_box(cx, cz, bl)
        ov = o['key'].intersection(BX).area
        if inside or ov >= OVERLAP_MIN - UNCERTAIN:
            o['_unc'] = near_edge(cx, cz, bl) or (not inside and abs(ov - OVERLAP_MIN) < UNCERTAIN)
            rep_old.append(o)
    rep_pilot, opt_pilot = [], []
    if 'pilot' in st['built']:
        for j in CW.pilot_tree.query(BX):
            p = CW.pilot['parts'][int(j)]
            if p['i'] in st['replaced_pilot']:
                if p['i'] in st['uncertain_pilot'] and p['shape'].intersection(BX).area > 0:
                    opt_pilot.append(p)
                continue
            cx, cz = p['c']
            inside = in_box(cx, cz, bl)
            ov = p['shape'].intersection(BX).area
            if inside or ov >= OVERLAP_MIN - UNCERTAIN:
                p['_unc'] = near_edge(cx, cz, bl) or (not inside and abs(ov - OVERLAP_MIN) < UNCERTAIN) or bool(p.get('amb'))
                rep_pilot.append(p)
        # the pilot's float32 split doubts: the other wedges Studio may have built, optional keys of every box they touch
        opt_alt = [a for a in CW.pilot.get('alts', []) if a['shape'].intersection(BX).area > 0 or in_box(*a['c'], bl)]
    else:
        opt_alt = []
    rep_front = list(st['frontier'].pop(b['id'], []))

    # ---- the ideal pieces inside the box
    S_b = clean(I['S'].intersection(BX))
    paved_all = unary_union([I['S'], I['walk'], I['islands']])
    grown = I['S'].buffer(0.45, join_style='mitre').intersection(paved_all.buffer(cfg['coll_slack']))
    asph = simplify_locked(clean(grown.intersection(BX)), cfg['coll_simplify'], lock)
    sh = I['shoulders']

    def flat_coll(g):
        base = clean(g.difference(I['S'].buffer(cfg['coll_slack'], join_style='mitre')).intersection(BX))
        c = simplify_locked(base, cfg['coll_simplify'], lock)
        if sh.is_empty:
            return clean(c)
        near = base.intersection(sh.buffer(0.5, join_style='mitre'))
        return clean(unary_union([c, near]).difference(sh))

    walk_c = flat_coll(I['walk'])
    isl_c = flat_coll(I['islands'])
    green_v = simplify_locked(clean(I['green'].intersection(BX)), 0.15, lock)
    # invisible wheel supports: where a replaced road part held a wheel within 2 studs of the new asphalt and B puts no
    # sidewalk / island / kerb there (junction.generate's no-regression rule), inside the box
    rep_road_shapes = [o['shape'] for o in rep_old if o['cls'] == 'road'] + [p['shape'] for p in rep_pilot if p['code'] in (11, 15)]
    old_rep_in = clean(unary_union(rep_road_shapes).intersection(BX)) if rep_road_shapes else Polygon()
    no_go = unary_union([unary_union([I['walk'], I['islands'], I['kerb'], I['island_kerb']]).buffer(cfg['support_clear'], join_style='mitre'), sh])
    room = clean(old_rep_in.intersection(I['S'].buffer(cfg['support_reach'])).difference(I['S']).difference(no_go), 0.05)
    pieces = []
    for q in polys(room):
        if q.area < cfg['support_min_area']:
            continue
        ext = unary_union([q, q.buffer(0.5, join_style='mitre').intersection(I['S'])]).difference(no_go).intersection(BX)
        near = ext.intersection(sh.buffer(0.3, join_style='mitre')) if not sh.is_empty else Polygon()
        pieces.append(clean(unary_union([ext.simplify(0.1), near]).difference(no_go).intersection(BX), 0.05))
    support = clean(unary_union(pieces)) if pieces else Polygon()

    # ---- frontier pieces: the parts of replaced old / pilot parts outside the box, cut per grid cell
    PLB = box(*wloc(PILOT_BOX_WORLD))
    front = []                                    # dict(tri, kind, target, cell)
    pilot_rebuild = {1: [], 2: [], 3: [], 5: []}  # exact rebuild of replaced pilot parts inside the pilot box
    out_road = [o['shape'].difference(BX) for o in rep_old if o['cls'] == 'road']
    out_walk = [o['shape'].difference(BX) for o in rep_old if o['cls'] == 'walk']
    for p in rep_pilot:
        if p['code'] in (11, 12, 13, 15):
            rest = p['shape'].difference(BX)
            if rest.area < 0.01:
                continue
            inpl = rest.intersection(PLB)
            if inpl.area > 0.01:
                pilot_rebuild[{11: 1, 12: 2, 13: 3, 15: 5}[p['code']]].append(inpl)
            outpl = rest.difference(PLB)
            if outpl.area > 0.01:
                (out_road if p['code'] in (11, 15) else out_walk).append(outpl)
    old_in_pilot = []
    for kind, shapes in ((1, out_road), (2, out_walk)):
        g = clean(unary_union([s for s in shapes if not s.is_empty]), 0.01) if shapes else Polygon()
        if g.is_empty:
            continue
        for (i, k) in cells_of_geom(g):
            cp = cell_poly(i, k)
            part = clean(g.intersection(cp), 0.01)
            if part.is_empty:
                continue
            tgt = owner.get((i, k))
            if tgt == 'pilot':
                if kind == 1:
                    old_in_pilot.append(part)     # old asphalt the pilot tapered to: see the pilot completion
                continue
            if tgt in built_after:
                continue                          # a built batch replaced every old part over its box (slivers only)
            for t in triangles_of(part):
                front.append(dict(tri=t, kind=kind, target=tgt or '', cell=(i, k)))

    # ---- the pilot seam band: complete the ideal where the pilot tapered toward old roads that are now gone
    comp = {1: Polygon(), 2: Polygon(), 5: Polygon()}
    region = Polygon()
    if 'pilot' in st['built'] and BX.buffer(1.0).intersects(PLB):
        band = PLB.difference(PLB.buffer(-SEAM_BAND))
        unbuilt = []
        for (i, k) in cells_of_geom(PLB.buffer(SEAM_BAND + 1)):
            if (i, k) == (0, 0):
                continue
            if owner.get((i, k)) not in built_after:
                unbuilt.append(cell_poly(i, k).buffer(SEAM_BAND, join_style='mitre'))
        region = clean(band.difference(unary_union(unbuilt) if unbuilt else Polygon()).difference(st['pilot_completed']))
        rest_pilot = [p for p in CW.pilot['parts'] if p['i'] not in st['replaced_pilot'] and not any(p is q for q in rep_pilot)]
        pil_asph = unary_union([p['shape'] for p in rest_pilot if p['code'] in (11, 15)] + pilot_rebuild[1] + pilot_rebuild[5])
        pil_high = unary_union([p['shape'] for p in rest_pilot if p['code'] in (12, 13)] + pilot_rebuild[2] + pilot_rebuild[3])
        if not region.is_empty:
            a = clean(I['S'].intersection(region).difference(pil_asph.buffer(0.05, join_style='mitre')), 0.05)
            a = clean(a.buffer(-0.25, join_style='mitre').buffer(0.25, join_style='mitre').intersection(region), 0.05)
            a = clean(unary_union([q for q in polys(a) if q.area >= 1.0]))
            comp[1] = a
            w = clean(I['walk'].intersection(region).difference(pil_high)
                      .difference(unary_union([pil_asph, a]).buffer(cfg['coll_slack'], join_style='mitre')), 0.05)
            w = clean(w.buffer(-0.5, join_style='mitre').buffer(0.5, join_style='mitre').intersection(region), 0.05)
            comp[2] = clean(unary_union([q for q in polys(w) if q.area >= 4.0]))
        # old asphalt the pilot leaned on inside its box (now replaced): where it held a wheel next to the asphalt and
        # nothing else covers it, an invisible support keeps that support (the no-regression rule)
        if old_in_pilot:
            pa = unary_union([pil_asph, comp[1]])
            ph = unary_union([pil_high, comp[2]])
            g = clean(unary_union(old_in_pilot).difference(pa).difference(ph.buffer(cfg['support_clear'])), 0.05)
            g = clean(g.intersection(pa.buffer(cfg['support_reach'])), 0.05)
            comp[5] = clean(unary_union([q for q in polys(g) if q.area >= 0.5]))

    # ---- markings: dashes / stops / zebra bars by midpoint, continuous lines and kerb strips cut at the box edge
    segs = batch_segs(I, BX, bl, cfg)

    # option B: invisible supports only where the ground is not at the plateau (the ramp at an open edge, never-raise
    # zones, the corridor)
    dropped = Counter()

    def keep_supports(tris_):
        if not (cfg.get('drop_supports_on_ground') and ground_full is not None):
            return tris_
        out = [t for t in tris_ if not ground_full(t)]
        dropped['support'] += len(tris_) - len(out)
        return out

    # ---- triangles -> rows
    tris = (_rows_of_tris(triangles_of(asph), 1) + _rows_of_tris(triangles_of(walk_c), 2) + _rows_of_tris(triangles_of(isl_c), 3)
            + _rows_of_tris(triangles_of(green_v), 4) + _rows_of_tris(keep_supports(triangles_of(support)), 5))
    comp_rows = []
    for kind, shapes in pilot_rebuild.items():
        for g in shapes:
            comp_rows += _rows_of_tris(triangles_of(clean(g, 0.01)), kind)
    for kind in (1, 2, 5):
        if not comp[kind].is_empty:
            t_ = triangles_of(comp[kind])
            comp_rows += _rows_of_tris(keep_supports(t_) if kind == 5 else t_, kind)
    for r_ in comp_rows:
        r_['completion'] = True
    front_rows = []
    for f in front:
        for r_ in _rows_of_tris([f['tri']], f['kind']):
            r_['target'] = f['target']
            front_rows.append(r_)

    # ---- probe samples: lane centres every 4 studs, the car footprint centre inside the box + PROBE_PAD
    reach_box = BX.buffer(PROBE_PAD, join_style='mitre')
    rows, legs = [], []
    for c in I['chains']:
        poly, Q, T, hw, s = I['rib'][c['id']]
        got = 0
        for k in range(0, len(Q), 2):
            if s[k] < 6.2 or s[k] > s[-1] - 6.2 or not reach_box.contains(Point(Q[k])):
                continue
            rows.append([export_luau.r(Q[k][0]), export_luau.r(Q[k][1]), export_luau.r(T[k][0], 4), export_luau.r(T[k][1], 4),
                         export_luau.r(hw[k]), c['id'], 1 if BX.contains(Point(Q[k])) else 0])
            got += 1
        if got:
            legs.append(dict(id=c['id'], name=c['name'], oneway=c['oneway'], lanes=int(min(c['lanes']))))

    # ---- state update
    unc_old, unc_pilot = set(), set()
    for o in rep_old:
        st['replaced_old'].add(o['i'])
        if o.pop('_unc', False):
            st['uncertain_old'].add(o['i'])
            unc_old.add(o['i'])
    for p in rep_pilot:
        st['replaced_pilot'].add(p['i'])
        if p.pop('_unc', False):
            st['uncertain_pilot'].add(p['i'])
            unc_pilot.add(p['i'])
    for f in front_rows:
        st['frontier'][f['target']].append(dict(f, owner=b['id']))
    if not region.is_empty:
        st['pilot_completed'] = clean(unary_union([st['pilot_completed'], region]))
    assumes = sorted(x for x in st['built'])
    st['built'].append(b['id'])
    st['seq'] += 1
    res = dict(id=b['id'], seq=st['seq'], box=b['box'], ideal=I, tris=tris, comp=comp_rows, front=front_rows, segs=segs,
               rep_old=rep_old, opt_old=opt_old, rep_pilot=rep_pilot, opt_pilot=opt_pilot, rep_front=rep_front,
               unc_old=unc_old, unc_pilot=unc_pilot, opt_alt=opt_alt, dropped=dict(dropped),
               probe_rows=rows, probe_legs=legs, region=region, S=S_b, walk=clean(I['walk'].intersection(BX)),
               islands=clean(I['islands'].intersection(BX)), support=support, comp_geom=comp, built_before=assumes,
               neighbours=neighbours_of(plan, b))
    st['pieces'][b['id']] = res
    return res


def neighbours_of(plan, b):
    """batch ids whose box touches b's box (edge or corner), plus 'pilot'"""
    bx = box(*b['box']).buffer(1.0, join_style='mitre')
    out = []
    if bx.intersects(box(*PILOT_BOX_WORLD)):
        out.append('pilot')
    for o in plan['batches']:
        if o['id'] != b['id'] and bx.intersects(box(*o['box'])):
            out.append(o['id'])
    return out


# ---- 3. the city plan --------------------------------------------------------------------------------------------------
# the owner's main roads (2026-10-22), in order, by their OSM names in the graph
MAIN_ROADS = [
    ('Sukhumvit Road', ('Sukhumvit Road',)),
    ('Beach Road', ('Pattaya Sai Nueng Road',)),
    ('Second Road', ('Pattaya Sai Song Road',)),
    ('Pattaya Klang / Central Road', ('Pattaya Klang Road',)),
    ('North Pattaya Road', ('Pattaya Nuea Road',)),
    ('South Pattaya Road', ('Pattaya Tai Road',)),
    ('Thepprasit Road', ('Thepprasit Road', 'Thep Prasit Road')),
    ('Jomtien Beach Road', ('Jomtien Sai Nueng',)),
]
FIRST = ('b001', (0, -1))                # the owner's batch 1: x 24220..24820, z 50..650 (the pilot's z0 edge)
REST_BLOCK_MAX_OLD = 2400                # a 2 x 2 block of the rest is split when its old road-layer parts exceed this


def cell_content(CW):
    """per grid cell: old road-layer parts (footprint centre in the cell, per class) and graph road length per name /
    class (samples every 10 studs)"""
    parts = defaultdict(Counter)
    for o in CW.old:
        c = cell_of_world(o['c'][0] + ORIGIN[0], o['c'][1])
        parts[c][o['cls']] += 1
    length = defaultdict(Counter)
    cls = defaultdict(Counter)
    for e in CW.W['graph']['edges']:
        P = np.asarray(e['pts'], float)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        for a, b, L in zip(P[:-1], P[1:], seg):
            n = max(int(L // 10), 1)
            for t in (np.arange(n) + 0.5) / n:
                q = a + (b - a) * t
                c = cell_of_world(q[0] + ORIGIN[0], q[1])
                length[c][e.get('name_en') or e.get('name') or ''] += L / n
                cls[c][e.get('class') or ''] += L / n
    return parts, length, cls


def plan_city(CW, log=print):
    """the ordered batch list: b001 (the owner's), the main roads cell by cell (Sukhumvit both ways from the pilot, then
    the other main roads, each from the end nearest to what is built), then the rest in 2 x 2 blocks (split where dense)
    growing outward from what is built, then the Bira corridor east of the city terrain frame"""
    parts, length, cls = cell_content(CW)
    frame = CW.W.get('frame_world')
    import tools.roadvis.ground_audit as ga
    man = ga._luau(os.path.join(CW.broot, 'pattaya_wide', 'roblox', 'manifest.luau'))
    fr = man['frame']
    frame = (fr['minX'] + ORIGIN[0], fr['minZ'], fr['maxX'] + ORIGIN[0], fr['maxZ'])
    content = {c for c in set(parts) | set(length) if parts[c]['road'] + parts[c]['walk'] > 0 or sum(length[c].values()) > 20}
    content.discard((0, 0))
    assigned = {(0, 0): 'pilot'}
    batches = []

    def add(cells, group):
        bid = f'b{len(batches) + 1:03d}'
        i0, k0 = min(c[0] for c in cells), min(c[1] for c in cells)
        i1, k1 = max(c[0] for c in cells), max(c[1] for c in cells)
        bw = (GRID0[0] + CELL * i0, GRID0[1] + CELL * k0, GRID0[0] + CELL * (i1 + 1), GRID0[1] + CELL * (k1 + 1))
        cl = [(i, k) for i in range(i0, i1 + 1) for k in range(k0, k1 + 1)]
        for c in cl:
            assert c not in assigned, (c, assigned.get(c))
            assigned[c] = bid
        batches.append(dict(id=bid, cells=cl, box=bw, group=group,
                            old_parts=int(sum(parts[c]['road'] + parts[c]['walk'] + parts[c]['mark'] for c in cl)),
                            road_len=round(sum(sum(length[c].values()) for c in cl), 0)))

    add([FIRST[1]], 'Sukhumvit Road')

    def near_assigned(c):
        return any((c[0] + di, c[1] + dk) in assigned for di in (-1, 0, 1) for dk in (-1, 0, 1) if di or dk)

    def bfs_order(cells):
        """cells ordered by steps from what is assigned (8-neighbourhood inside `cells`); ties by (k, i)"""
        cells = set(cells)
        out, layer = [], sorted((c for c in cells if near_assigned(c)), key=lambda c: (c[1], c[0]))
        if not layer and cells:
            def dist(c):
                return min(max(abs(c[0] - a[0]), abs(c[1] - a[1])) for a in assigned)
            layer = [min(cells, key=lambda c: (dist(c), c[1], c[0]))]
        seen = set(layer)
        while layer:
            out += layer
            nxt = set()
            for c in layer:
                for di in (-1, 0, 1):
                    for dk in (-1, 0, 1):
                        q = (c[0] + di, c[1] + dk)
                        if q in cells and q not in seen:
                            nxt.add(q)
            seen |= nxt
            layer = sorted(nxt, key=lambda c: (c[1], c[0]))
            if not layer and len(out) < len(cells):
                rest = cells - set(out)
                layer = [min(rest, key=lambda c: (min(max(abs(c[0] - a[0]), abs(c[1] - a[1])) for a in list(assigned) + out), c[1], c[0]))]
                seen.add(layer[0])
        return out

    # Sukhumvit: both directions from the pilot, alternating (north first: b001 is north of the pilot)
    names = dict(MAIN_ROADS)
    suk = sorted((c for c in content if sum(length[c][n] for n in names['Sukhumvit Road']) >= 20 and c not in assigned),
                 key=lambda c: (abs(c[1]), 0 if c[1] < 0 else 1, c[0]))
    for c in suk:
        add([c], 'Sukhumvit Road')
    for group, nm in MAIN_ROADS[1:]:
        cells = [c for c in content if sum(length[c][n] for n in nm) >= 20 and c not in assigned]
        for c in bfs_order(cells):
            add([c], group)
    # the rest inside the city terrain frame: 2 x 2 blocks of the 1,200-stud grid, split where dense or partly taken
    def in_frame(c):
        x0, z0, x1, z1 = cell_box_world(*c)
        return x0 >= frame[0] and x1 <= frame[2] and z0 >= frame[1] and z1 <= frame[3]
    rest = [c for c in content if c not in assigned and in_frame(c)]
    blocks = defaultdict(list)
    for c in rest:
        blocks[(c[0] // 2, c[1] // 2)].append(c)
    units = []
    for bk, cs in blocks.items():
        full = [(2 * bk[0] + a, 2 * bk[1] + b) for a in (0, 1) for b in (0, 1)]
        dense = sum(parts[c]['road'] + parts[c]['walk'] + parts[c]['mark'] for c in full) > REST_BLOCK_MAX_OLD
        if not dense and not any(c in assigned for c in full):
            units.append(full)
            continue
        # rows of the block: a 2 x 1 pair when both are free and not dense, else single cells
        left = set(cs)
        for b2 in (0, 1):
            row = [(2 * bk[0] + a, 2 * bk[1] + b2) for a in (0, 1)]
            if all(c not in assigned for c in row) and not dense and all(c in left for c in row):
                units.append(row)
                left -= set(row)
        for c in sorted(left, key=lambda c: (c[1], c[0])):
            units.append([c])
    # order the units by steps from what is built (unit adjacency), so the built area grows without islands
    pending = units
    while pending:
        def dist(u):
            return min(max(abs(c[0] - a[0]), abs(c[1] - a[1])) for c in u for a in assigned)
        pending.sort(key=lambda u: (dist(u), min(c[1] for c in u), min(c[0] for c in u)))
        add(pending[0], 'rest')
        pending = pending[1:]
    # the Bira corridor (outside the city terrain frame: Road B only, the ground there is not the city ground)
    corr = [c for c in content if c not in assigned and not in_frame(c)]
    blocks = defaultdict(list)
    for c in corr:
        blocks[(c[0] // 2, c[1] // 2)].append(c)
    for bk in sorted(blocks, key=lambda b: (b[0], b[1])):
        full = [(2 * bk[0] + a, 2 * bk[1] + b) for a in (0, 1) for b in (0, 1)]
        if any(c in assigned for c in full):
            for c in sorted(blocks[bk], key=lambda c: (c[1], c[0])):
                add([c], 'corridor')
        else:
            add(full, 'corridor')
    # the build order: SECOND builds right after b001 (leader 2026-10-22: b003 finishes the owner's second screenshot
    # spot at b001's north edge); every id keeps the number of the first ordering, the rest keeps its order
    for bid in reversed(SECOND):
        i = next(k for k, x in enumerate(batches) if x['id'] == bid)
        batches.insert(1, batches.pop(i))
    log(f'plan: {len(batches)} batches ({Counter(b["group"] for b in batches)}), {len(assigned) - 1} cells')
    return dict(grid=dict(origin=list(GRID0), cell=CELL), pilot=dict(id='pilot', box=list(PILOT_BOX_WORLD)), frame=list(frame),
                batches=batches)
