"""Coast pass (team4/coast): a smoother beach edge, beach props and a distant island horizon for the Pattaya world.

    .venv\\Scripts\\python tools\\mapgen\\coast.py tools\\mapgen\\config\\coast.json

Reads only existing outputs (build/central_pattaya, build/pattaya_wide: graph_game.json, buildings_game.json,
layout.json, roblox/manifest.luau, roblox/joints.luau), raw OSM (data/osm/raw) and Terrarium DEM tiles. Writes only
build/coast/ (roblox/manifest.luau, roblox/terrain_<n>.luau, roblox/chunk_b<cx>_<cz>.luau, check images, report).
Nothing else in the pipeline is changed; roblox/src/ServerStorage/PattayaCoastBuilder.luau builds the output.

1. Terrain (4-stud cells). The existing sea was carved by PattayaBuilder on a 16-stud raster (rows of water runs,
   a 48-stud sand strip east of each run's end: the stair-stepped beach). This script SIMULATES those exact writes
   (Build() then Extend({roads = false}), same Region3:ExpandToGrid(4) snapping) to know the material of every
   4 x 4-stud column in the three voxel layers y -16..-4, then re-classifies the cells near the REAL OSM coastline
   by their signed distance d to it (sea < 0): deep / mid (8-stud water over sand) / shallow (4-stud water over
   sand) / wet sand / dry sand. Only cells that change are written (Terrain:WriteVoxels on contiguous runs of one
   4-stud row). A cell is writable only when (a) its old top voxel is Water or Sand (the sea and the old sand
   strip; Air only for sea cells of the base/wide seam row, see the report), (b) the next `landward_keep_cells`
   cells to its east are still Water/Sand, so every write stays seaward of the strip's landward edge with a margin,
   and (c) it is clear of every road + sidewalk, junction/joint disc and building (+ clearance) and of the other
   teams' areas. All three are asserted after planning. The old state of every written cell is exported as well
   (PattayaCoastBuilder.RemoveTerrain).
2. Props (rule-based, from OSM natural=beach + the coastline): umbrella/lounger rows on Pattaya Beach and Jomtien
   Beach, promenade lamps along the sea side of the coastal roads (clear of the existing palms and street lights),
   lifeguard towers, moored boat proxies, beach-bar huts (NightNeon) and parasail kites at Jomtien. Every prop is
   checked against roads / sidewalks / discs / buildings (shapely, asserted 0).
3. Horizon: Koh Larn, Ko Sak and Ko Krok from OSM coastline ways (data/osm/raw/koh_larn_2026-10-19.json), as a few
   low strip Parts with heights from Terrarium DEM (x vertical_scale), at their real position.
"""
import json, math, os, re, sys
from collections import defaultdict
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import linemerge, split, unary_union
from shapely import affinity
from shapely.strtree import STRtree
from pyproj import Transformer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
AIR, G, S, W, M = 0, 1, 2, 3, 4                      # voxel material codes (Air, Ground, Sand, Water, Mud = wet sand)
MAT_NAMES = {AIR: 'Air', G: 'Ground', S: 'Sand', W: 'Water', M: 'Mud'}


def rp(p):
    return os.path.join(ROOT, p)


def jload(p):
    return json.load(open(rp(p), encoding='utf-8'))


def f4(v):
    return math.floor(v / 4) * 4


def c4(v):
    return math.ceil(v / 4) * 4


# ---------------------------------------------------------------------------------------------------------------
# inputs
def parse_manifest(path):
    src = open(rp(path), encoding='utf-8').read()
    out = {}
    m = re.search(r'\n  frame = \{ minX = (-?\d+), maxX = (-?\d+), minZ = (-?\d+), maxZ = (-?\d+) \}', src)
    out['frame'] = tuple(int(v) for v in m.groups())
    m = re.search(r'\n  baseFrame = \{ minX = (-?\d+), maxX = (-?\d+), minZ = (-?\d+), maxZ = (-?\d+) \}', src)
    out['baseFrame'] = tuple(int(v) for v in m.groups()) if m else None
    m = re.search(r'\n  groundRects = \{(.*)\},\n', src)
    out['groundRects'] = [tuple(int(v) for v in r.split(',')) for r in re.findall(r'\{ ([-\d, ]+) \}', m.group(1))] if m else []
    out['seaCell'] = int(re.search(r'\n  seaCell = (\d+)', src).group(1))
    rows = []
    for z, h, runs in re.findall(r'\n  \{ z = (-?\d+),(?: h = (\d+),)? runs = \{ ([-\d, ]*) \} \}', src):
        rows.append((int(z), int(h) if h else None, [int(v) for v in runs.replace(' ', '').split(',') if v]))
    out['sea'] = rows
    out['junctions'] = [(int(i), float(x), float(z), float(r)) for i, x, z, r in
                        re.findall(r'\{ id = (\d+), x = (-?[\d.]+), z = (-?[\d.]+), r = ([\d.]+) \}', src)]
    return out


def parse_joints(path):
    src = open(rp(path), encoding='utf-8').read()
    body = src[src.index('return'):]
    nums = [float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', body)]
    return [(nums[i + 1], nums[i + 2], nums[i + 3]) for i in range(0, len(nums) - 3, 4)]


# ---------------------------------------------------------------------------------------------------------------
# 1. terrain
class Raster:
    """Material of every 4x4-stud column in the voxel layers top (-8..-4), mid (-12..-8), low (-16..-12)."""

    def __init__(self, x0, z0, x1, z1):
        self.x0, self.z0 = x0, z0
        self.nx, self.nz = (x1 - x0) // 4, (z1 - z0) // 4
        self.m = np.zeros((3, self.nz, self.nx), np.uint8)

    def sl(self, xa, xb, za, zb):
        """Region3(min, max):ExpandToGrid(4) -> index slices (clipped to the raster)."""
        i0, i1 = (f4(xa) - self.x0) // 4, (c4(xb) - self.x0) // 4
        j0, j1 = (f4(za) - self.z0) // 4, (c4(zb) - self.z0) // 4
        return slice(max(j0, 0), max(min(j1, self.nz), 0)), slice(max(i0, 0), max(min(i1, self.nx), 0))

    def replace(self, xa, xb, za, zb, layers, frm, to):
        js, is_ = self.sl(xa, xb, za, zb)
        for L in layers:
            v = self.m[L, js, is_]
            for f in frm:
                v[v == f] = to

    def fill(self, xa, xb, za, zb, mat):
        """FillBlock (possibly unaligned bounds): every touched voxel gets the material (partial occupancy at edges)."""
        js, is_ = self.sl(xa, xb, za, zb)
        v = self.m[:, js, is_]
        v[v == AIR] = mat


def simulate_old_terrain(base, wide):
    """Replays PattayaBuilder buildTerrain (Build) then extendTerrain (Extend roads=false) on the 4-stud raster."""
    fx0, fx1, fz0, fz1 = wide['frame']
    R = Raster(fx0, fz0, fx1, fz1)
    ALL = (0, 1, 2)
    # Build(): clear the base frame, fill ground -16..-4, then the 16-stud sea rows (pairs) + 48-stud sand strips
    bx0, bx1, bz0, bz1 = base['frame']
    R.replace(bx0, bx1, bz0, bz1, ALL, (G, S, W), AIR)
    R.fill(bx0, bx1, bz0, bz1, G)
    cell = base['seaCell']
    for z, _, r in base['sea']:
        for k in range(0, len(r), 2):
            x0, x1 = r[k], r[k + 1]
            R.replace(x0, x1, z, z + cell, ALL, (G,), W)
            R.replace(x1, x1 + 48, z, z + cell, (0,), (G,), S)
    # Extend({roads = false}): ground rectangles (clear + fill, aligned), then the wide sea rows (triples)
    for rx0, rx1, rz0, rz1 in wide['groundRects']:
        R.replace(rx0, rx1, rz0, rz1, ALL, (G, S, W), AIR)
        R.fill(rx0, rx1, rz0, rz1, G)
    for z, h, r in wide['sea']:
        z1 = z + (h or wide['seaCell'])
        for k in range(0, len(r), 3):
            x0, x1, sand = r[k], r[k + 1], r[k + 2]
            R.replace(x0, x1, z, z1, ALL, (G,), W)
            if sand == 1:
                R.replace(x1, x1 + 48, z, z1, (0,), (G,), S)
    return R


def sea_polygon(graph, frame):
    """The wide exporter's sea mask (frame split by the main coastline, minus the islets) on the given frame."""
    minx, minz, maxx, maxz = frame
    fr = box(minx, minz, maxx, maxz)
    merged = linemerge([LineString(c['pts']) for c in graph['coastline']])
    glines = list(merged.geoms) if merged.geom_type == 'MultiLineString' else [merged]
    islets = [Polygon(l.coords) for l in glines if l.is_ring]
    main = max((l for l in glines if not l.is_ring), key=lambda l: l.length)
    p = np.array(main.coords)
    a = p[0] + (p[0] - p[1]) / np.linalg.norm(p[0] - p[1]) * 20000
    b = p[-1] + (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2]) * 20000
    pieces = list(split(fr, LineString(np.vstack([a, p, b]))).geoms)
    sea = [q for q in pieces if q.bounds[0] <= minx + 1 and q.representative_point().x < (minx + maxx) / 2]
    sea = unary_union(sea)
    if islets:
        sea = sea.difference(unary_union(islets))
    return sea, unary_union([LineString(c['pts']) for c in graph['coastline']])


def box_poly(b, grow=0.0):
    r = Polygon([(-b['w'] / 2 - grow, -b['d'] / 2 - grow), (b['w'] / 2 + grow, -b['d'] / 2 - grow),
                 (b['w'] / 2 + grow, b['d'] / 2 + grow), (-b['w'] / 2 - grow, b['d'] / 2 + grow)])
    return affinity.translate(affinity.rotate(r, b['yaw']), b['x'], b['z'])


class Blockers:
    """Roads + sidewalks (both sides, conservative), junction/joint discs and building boxes of central + wide."""

    def __init__(self, graphs, manifests, joints, buildings):
        self.roads, seen = [], set()
        for g in graphs:
            for e in g['edges']:
                key = (e['id'], tuple(map(tuple, e['pts'][:2])), len(e['pts']))
                if key in seen:
                    continue
                seen.add(key)
                self.roads.append((LineString(e['pts']), e['width'] / 2 + e.get('sidewalk', 0)))
        self.discs = []
        for man in manifests:
            self.discs += [(x, z, r) for _, x, z, r in man['junctions']]
        self.discs += list(joints)
        self.buildings = buildings

    def polys(self, road_clear, disc_clear, building_clear):
        out = [ln.buffer(hw + road_clear, quad_segs=4) for ln, hw in self.roads]
        out += [Point(x, z).buffer(r + disc_clear, quad_segs=6) for x, z, r in self.discs]
        out += [box_poly(b, building_clear) for b in self.buildings]
        return out


def other_team_zones(cfg, osm_ways, to_game):
    zones = []
    for w in cfg['other_teams']['ways']:
        e = osm_ways.get(w['id'])
        if e is None:
            print(f"other team area {w['what']} (way {w['id']}) not in the raw data")
            continue
        pts = to_game(e['geometry'])
        geom = Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else LineString(pts)
        zones.append((w['what'], geom.buffer(w['buffer'])))
    return zones


def plan_terrain(R, sea, coast_lines, blockers, zones, tc):
    """Per-cell new state near the real coastline; returns (changed mask, new materials, report)."""
    cell = tc['cell']
    band = tc['band_studs']
    old = R.m
    top = old[0]
    # candidate cells: within `band` studs of the coastline (row blocks, x range from the buffer's bounds)
    buf = coast_lines.buffer(band + 3)
    cand = np.zeros(top.shape, bool)
    for j0 in range(0, R.nz, 256):
        j1 = min(j0 + 256, R.nz)
        zb = (R.z0 + j0 * cell, R.z0 + j1 * cell)
        part = buf.intersection(box(R.x0, zb[0], R.x0 + R.nx * cell, zb[1]))
        if part.is_empty:
            continue
        i0 = max(int((part.bounds[0] - R.x0) // cell) - 1, 0)
        i1 = min(int((part.bounds[2] - R.x0) // cell) + 2, R.nx)
        xs = R.x0 + (np.arange(i0, i1) + 0.5) * cell
        zs = R.z0 + (np.arange(j0, j1) + 0.5) * cell
        X, Z = np.meshgrid(xs, zs)
        cand[j0:j1, i0:i1] = shapely.contains_xy(buf, X, Z)
    # the seam row with no terrain at all (base frame top edge, see report): its sea cells are candidates too
    air_sea_rows = []
    for j in np.where((top == AIR).any(axis=1))[0]:
        air_sea_rows.append(int(j))
    for j in air_sea_rows:
        nb = j + 1 if j + 1 < R.nz else j - 1
        cand[j] |= (top[j] == AIR) & (top[nb] == W)
    J, I = np.nonzero(cand)
    xs = R.x0 + (I + 0.5) * cell
    zs = R.z0 + (J + 0.5) * cell
    pts = shapely.points(xs, zs)
    in_sea = shapely.contains_xy(sea, xs, zs)
    # distance to the coastline: nearest segment via STRtree
    segs = []
    for ln in getattr(coast_lines, 'geoms', [coast_lines]):
        c = np.asarray(ln.coords)
        segs += [LineString([c[k], c[k + 1]]) for k in range(len(c) - 1)]
    stree = STRtree(segs)
    _, dist = stree.query_nearest(pts, return_distance=True, all_matches=False)
    d = np.where(in_sea, -dist, dist)
    # blockers (roads, discs, buildings, other teams): a cell is blocked when its square touches one
    half = cell / 2 * math.sqrt(2) + 0.01
    bpolys = blockers.polys(tc['road_clear_studs'] + half, tc['road_clear_studs'] + half, tc['building_clear_studs'] + half)
    bpolys += [z.buffer(half) for _, z in zones]
    btree = STRtree(bpolys)
    hit = btree.query(pts, predicate='intersects')
    blocked = np.zeros(len(pts), bool)
    blocked[np.unique(hit[0])] = True
    # old state + writability
    o_top = top[J, I]
    K = tc['landward_keep_cells']
    east_ok = np.ones(len(J), bool)
    for k in range(1, K + 1):
        ii = np.minimum(I + k, R.nx - 1)
        jj = np.where(o_top == AIR, np.minimum(J + 1, R.nz - 1), J)    # the Air seam row: judge by the row below
        east_ok &= np.isin(top[jj, ii], (W, S))
    air_sea = (o_top == AIR) & in_sea & (top[np.minimum(J + 1, R.nz - 1), I] == W)
    writable = (np.isin(o_top, (W, S)) | air_sea) & east_ok & ~blocked
    # new state
    new = np.stack([old[L][J, I] for L in range(3)])
    sh, md, wt = tc['shallow_studs'], tc['mid_studs'], tc['wet_studs']
    def setv(mask, trip):
        for L in range(3):
            new[L][mask] = trip[L]
    setv(in_sea & (d <= -md), (W, W, W))
    setv(in_sea & (d > -md) & (d <= -sh), (W, W, S))
    setv(in_sea & (d > -sh), (W, S, S))
    land = ~in_sea
    setv(land & (d < wt), (M, S, S))
    setv(land & (d >= wt) & np.isin(o_top, (W, AIR)), (S, S, S))   # old water that is really beach (the strip keeps its state)
    oldv = np.stack([old[L][J, I] for L in range(3)])
    changed = writable & (new != oldv).any(axis=0)
    rep = {
        'candidates': int(len(J)), 'writable': int(writable.sum()), 'changed_cells': int(changed.sum()),
        'blocked_cells': int(blocked.sum()), 'not_seaward_cells': int((np.isin(o_top, (W, S)) & ~east_ok).sum()),
        'seam_air_cells_in_band_or_row': int(((o_top == AIR)).sum()), 'seam_air_sea_cells_filled': int((air_sea & changed).sum()),
        'wanted_but_blocked_or_landward': int(((new != oldv).any(axis=0) & ~writable).sum()),
    }
    by = defaultdict(int)
    for L0, L1, L2 in zip(*[new[L][changed] for L in range(3)]):
        by['/'.join(MAT_NAMES[v] for v in (L0, L1, L2))] += 1
    rep['changed_by_new_state'] = dict(sorted(by.items()))
    return dict(J=J[changed], I=I[changed], new=new[:, changed], old=oldv[:, changed], d=d[changed]), rep, (J, I, d, in_sea)


def plan_beach_fill(R, newtop, beach_polys, coast_lines, blockers, zones, tc, fc):
    """OPTIONAL landward pass (off unless the leader runs BuildTerrain({fill = true})): Ground -> Sand in the TOP voxel
    only, for cells inside OSM natural=beach polygons that the 48-stud strip did not reach, clear of every road +
    sidewalk, disc and building (+ clearance). This moves the sand strip's landward edge, which the default pass never
    does, so it is a separate, explicitly opt-in step."""
    cell = 4
    area = unary_union(beach_polys).intersection(coast_lines.buffer(fc['max_dist_studs']))
    i0 = max(int((area.bounds[0] - R.x0) // cell), 0)
    i1 = min(int((area.bounds[2] - R.x0) // cell) + 1, R.nx)
    j0 = max(int((area.bounds[1] - R.z0) // cell), 0)
    j1 = min(int((area.bounds[3] - R.z0) // cell) + 1, R.nz)
    X, Z = np.meshgrid(R.x0 + (np.arange(i0, i1) + 0.5) * cell, R.z0 + (np.arange(j0, j1) + 0.5) * cell)
    inside = shapely.contains_xy(area, X, Z) & (newtop[j0:j1, i0:i1] == G) & (R.m[0][j0:j1, i0:i1] == G)
    jj, ii = np.nonzero(inside)
    J, I = jj + j0, ii + i0
    boxes = shapely.box(R.x0 + I * 4, R.z0 + J * 4, R.x0 + I * 4 + 4, R.z0 + J * 4 + 4)
    bp = blockers.polys(tc['road_clear_studs'], tc['road_clear_studs'], tc['building_clear_studs']) + [z for _, z in zones]
    hit = STRtree(bp).query(boxes, predicate='intersects')
    ok = np.ones(len(J), bool)
    ok[np.unique(hit[0])] = False
    J, I = J[ok], I[ok]
    old = np.stack([R.m[L][J, I] for L in range(3)])
    new = old.copy()
    new[0][:] = S
    return dict(J=J, I=I, new=new, old=old), {'fill_cells': int(len(J)), 'fill_blocked_cells': int((~ok).sum())}


# ---------------------------------------------------------------------------------------------------------------
# 2. props
def rect(cx, cz, ux, uz, half_len, half_wid):
    """Rectangle centred at (cx, cz), long axis along unit (ux, uz)."""
    vx, vz = -uz, ux
    return Polygon([(cx + ux * half_len + vx * half_wid, cz + uz * half_len + vz * half_wid),
                    (cx - ux * half_len + vx * half_wid, cz - uz * half_len + vz * half_wid),
                    (cx - ux * half_len - vx * half_wid, cz - uz * half_len - vz * half_wid),
                    (cx + ux * half_len - vx * half_wid, cz + uz * half_len - vz * half_wid)])


def hash01(*vals):
    """Deterministic 0..1 from numbers (FNV-1a over their 2-decimal text): stable jitter, no RNG state."""
    h = 2166136261
    for v in vals:
        for ch in f'{v:.2f}'.encode():
            h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


class Placer:
    """Collision bookkeeping for props: blockers (roads etc.), existing palms / lights, already placed props, and
    the terrain the prop needs under its footprint (the NEW terrain state: dry sand for beach props, water for boats)."""

    def __init__(self, blocker_polys, palms, lights, terrain_top, R):
        self.bpolys = blocker_polys
        self.btree = STRtree(blocker_polys)
        self.palm_pts = [Point(p['x'], p['z']) for p in palms]
        self.palms = STRtree(self.palm_pts)
        self.light_pts = [Point(p['x'], p['z']) for p in lights]
        self.lights = STRtree(self.light_pts)
        self.placed = []
        self.top, self.R = terrain_top, R
        self.rejects = defaultdict(int)

    def top_at(self, x, z):
        i, j = int((x - self.R.x0) // 4), int((z - self.R.z0) // 4)
        if 0 <= i < self.R.nx and 0 <= j < self.R.nz:
            return int(self.top[j, i])
        return AIR

    def ok(self, kind, foot, ground=(S,), palm_clear=6.0, light_clear=6.0, samples=None, gap=1.0):
        if any(self.bpolys[i].intersects(foot) for i in self.btree.query(foot)):
            self.rejects[kind + ':blocker'] += 1
            return False
        if any(self.palm_pts[i].distance(foot) < palm_clear for i in self.palms.query(foot.buffer(palm_clear))):
            self.rejects[kind + ':palm'] += 1
            return False
        if any(self.light_pts[i].distance(foot) < light_clear for i in self.lights.query(foot.buffer(light_clear))):
            self.rejects[kind + ':light'] += 1
            return False
        if ground is not None:
            pts = samples if samples is not None else list(foot.exterior.coords)[:-1] + [foot.centroid.coords[0]]
            if any(self.top_at(x, z) not in ground for x, z in pts):
                self.rejects[kind + ':terrain'] += 1
                return False
        g = foot.buffer(gap)
        b = g.bounds
        for p in self.placed:
            pb = p.bounds
            if not (pb[0] > b[2] or pb[2] < b[0] or pb[1] > b[3] or pb[3] < b[1]) and p.intersects(g):
                self.rejects[kind + ':prop'] += 1
                return False
        self.placed.append(foot)
        return True


def shore_stations(coast_lines, area, sea, step, phase=0.0):
    """Points every `step` studs along the coastline inside `area`, with unit tangent and landward normal."""
    part = coast_lines.intersection(area)
    if part.is_empty:
        return []
    merged = linemerge(part) if part.geom_type == 'MultiLineString' else part
    lines = list(getattr(merged, 'geoms', [merged]))
    out = []
    for ln in sorted(lines, key=lambda l: -l.length):
        if ln.geom_type != 'LineString' or ln.length < step:
            continue
        s = step / 2 + phase
        while s < ln.length - step / 4:
            p, q = ln.interpolate(max(s - 3, 0)), ln.interpolate(min(s + 3, ln.length))
            t = np.array([q.x - p.x, q.y - p.y])
            t /= np.linalg.norm(t) + 1e-9
            n = np.array([-t[1], t[0]])
            c = ln.interpolate(s)
            if shapely.contains_xy(sea, c.x + n[0] * 10, c.y + n[1] * 10):
                n = -n
            out.append((c.x, c.y, t, n, s))
            s += step
    return out


def place_props(cfg, beaches, coast_lines, sea, placer, coastal_edges, piers):
    pc = cfg['props']
    items = defaultdict(list)    # kind -> rows
    for bi, bid in enumerate(pc['beaches']):
        area = beaches[bid]['poly'].buffer(25)
        # 1) lifeguard towers every `step` studs, d studs inland of the waterline (first: they have priority)
        lc = pc['lifeguard']
        for x, z, t, n, s in shore_stations(coast_lines, area, sea, lc['step']):
            for dd in (lc['d'], lc['d'] + 6, lc['d'] - 4, lc['d'] + 12):
                cx, cz = x + n[0] * dd, z + n[1] * dd
                if placer.ok('tower', rect(cx, cz, n[0], n[1], 3.5, 3.5)):
                    items['towers'].append((cx, cz, -n[0], -n[1]))       # faces the sea
                    break
        # 2) beach-bar huts (NightNeon trim at night)
        hc = pc['huts']
        for x, z, t, n, s in shore_stations(coast_lines, area, sea, hc['step'], phase=hc['step'] / 2):
            for dd in (hc['d'], hc['d'] - 6, hc['d'] + 4, hc['d'] - 12):
                cx, cz = x + n[0] * dd, z + n[1] * dd
                if placer.ok('hut', rect(cx, cz, t[0], t[1], 6.5, 4.5)):
                    items['huts'].append((cx, cz, -n[0], -n[1], 1 + int(hash01(cx, cz) * 5) % 5))
                    break
        # 3) umbrella + 2 loungers, in rows parallel to the waterline
        uc = pc['umbrella']
        for r, dd in enumerate(uc['rows_d']):
            for x, z, t, n, s in shore_stations(coast_lines, area, sea, uc['step'], phase=(uc['step'] / 2) * r):
                j = (hash01(x, z, r) - 0.5) * 2 * uc['jitter']
                cx, cz = x + n[0] * (dd + j), z + n[1] * (dd + j)
                # footprint: canopy disc (r 4.5) + the loungers on the sea side; the sand check covers the set
                foot = rect(cx - n[0] * 2.0, cz - n[1] * 2.0, n[0], n[1], 5.5, 4.6)
                if placer.ok('umbrella', foot, gap=0.5):
                    items['umbrellas'].append((cx, cz, -n[0], -n[1], 1 + int(hash01(z, x) * 6) % 6))
        # 4) boats moored offshore (water under the hull, clear of piers)
        nb = pc['boats']['per_beach'][bi]
        sts = shore_stations(coast_lines, area, sea, 20)
        for k in range(nb if sts else 0):
            x, z, t, n, s = sts[int((k + 0.5) * len(sts) / nb)]
            d0, d1 = pc['boats']['d']
            dd = d0 + (d1 - d0) * hash01(x, z, k)
            cx, cz = x + n[0] * dd, z + n[1] * dd
            ang = (hash01(z, x, k) - 0.5) * 1.2
            ca, sa = math.cos(ang), math.sin(ang)
            dx, dz = -n[0] * ca + n[1] * sa, -n[0] * sa - n[1] * ca      # bow roughly out to sea
            kind = 1 + (k % 2)                                             # 1 longtail, 2 speedboat
            foot = rect(cx, cz, dx, dz, 9 if kind == 1 else 7, 2.5)
            if any(p.intersects(foot.buffer(20)) for p in piers):
                placer.rejects['boat:pier'] += 1
                continue
            if placer.ok('boat', foot, ground=(W,), gap=10):
                items['boats'].append((cx, cz, dx, dz, kind))
    # 5) promenade lamps along the sea side of the coastal roads, just outside the sidewalk
    lc = pc['lamp']
    for e in coastal_edges:
        ln = LineString(e['pts'])
        if ln.length < lc['step'] / 2:
            continue
        off = e['width'] / 2 + e['sidewalk'] + lc['out_of_sidewalk']
        s = lc['step'] / 2
        while s < ln.length:
            p, q = ln.interpolate(max(s - 2, 0)), ln.interpolate(min(s + 2, ln.length))
            t = np.array([q.x - p.x, q.y - p.y])
            t /= np.linalg.norm(t) + 1e-9
            n = np.array([-t[1], t[0]])
            c = ln.interpolate(s)
            far1, far2 = Point(c.x + n[0] * 60, c.y + n[1] * 60), Point(c.x - n[0] * 60, c.y - n[1] * 60)
            if sea.distance(far2) < sea.distance(far1):                    # the sea side
                n = -n
            cx, cz = c.x + n[0] * off, c.y + n[1] * off
            if coast_lines.distance(Point(cx, cz)) < 160 and placer.ok(
                    'lamp', Point(cx, cz).buffer(0.8, quad_segs=4), ground=(G, S, M), palm_clear=lc['palm_clear'],
                    light_clear=lc['light_clear'], samples=[(cx, cz)]):
                items['lamps'].append((cx, cz, -n[0], -n[1]))
            s += lc['step']
    # 6) parasail kites off Jomtien: canopy high over the sea, tow line down to a small boat
    kc = pc.get('kites')
    if kc and kc['beach'] in beaches:
        sts = shore_stations(coast_lines, beaches[kc['beach']]['poly'].buffer(25), sea, 40)
        for k in range(kc['count']):
            x, z, t, n, s = sts[int((k + 0.5) * len(sts) / kc['count'])]
            dd = -220 - 60 * hash01(x, z)
            cx, cz = x + n[0] * dd, z + n[1] * dd
            dx, dz = (t if k % 2 == 0 else -t)
            if placer.ok('kite', rect(cx, cz, dx, dz, 6, 2.5), ground=(W,), gap=10):
                items['kites'].append((cx, cz, float(dx), float(dz), 70 + int(25 * hash01(z, x)), 1 + k % 5))
    return items


# ---------------------------------------------------------------------------------------------------------------
# 3. horizon islands
class Dem:
    """Terrarium PNG tiles: height = R*256 + G + B/256 - 32768 (metres), bilinear sampling."""

    def __init__(self, folder, zoom):
        from PIL import Image
        self.z, self.tiles, self.folder, self.Image = zoom, {}, folder, Image

    def tile(self, tx, ty):
        k = (tx, ty)
        if k not in self.tiles:
            p = rp(os.path.join(self.folder, f'{self.z}_{tx}_{ty}.png'))
            if not os.path.exists(p):
                raise SystemExit(f'DEM tile missing: {p} (https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{self.z}/{tx}/{ty}.png)')
            a = np.asarray(self.Image.open(p).convert('RGB'), np.float64)
            self.tiles[k] = a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256 - 32768
        return self.tiles[k]

    def h(self, lon, lat):
        n = 2 ** self.z * 256
        px = (lon + 180) / 360 * n
        r = math.radians(lat)
        py = (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n
        x0, y0 = math.floor(px - 0.5), math.floor(py - 0.5)
        fx, fy = px - 0.5 - x0, py - 0.5 - y0
        def at(x, y):
            return self.tile(x // 256, y // 256)[y % 256, x % 256]
        return ((at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx) * (1 - fy) +
                (at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx) * fy)


def build_islands(cfg, raw, to_game, to_lonlat):
    ic = cfg['island']
    dem = Dem(cfg['dem_tiles'], cfg['dem_zoom'])
    vs = ic['vertical_scale'] / 0.28                  # metres -> studs (same 0.28 m/stud as everything else)
    out, w = [], ic['strip_studs']
    for e in raw['elements']:
        t = e.get('tags', {})
        if t.get('natural') != 'coastline' or e['type'] != 'way' or e['nodes'][0] != e['nodes'][-1]:
            continue
        poly = Polygon(to_game(e['geometry'])).buffer(0)
        name = t.get('name:en') or t.get('name')
        parts = []
        z0 = math.floor(poly.bounds[1] / w) * w
        for zs in np.arange(z0, poly.bounds[3], w):
            band = poly.intersection(box(poly.bounds[0] - 1, zs, poly.bounds[2] + 1, zs + w))
            for comp in getattr(band, 'geoms', [band]):
                if comp.is_empty or comp.geom_type != 'Polygon' or comp.area < 0.12 * w * w:
                    continue
                bx0, bz0, bx1, bz1 = comp.bounds
                xs, zz = np.meshgrid(np.arange(bx0 + 20, bx1, 40), np.arange(bz0 + 20, bz1, 40))
                inside = shapely.contains_xy(comp, xs, zz)
                if not inside.any():
                    continue
                pts = [(x, z) for x, z in zip(xs[inside], zz[inside])]
                hs = np.array([max(dem.h(*to_lonlat(x, z)), 0.0) for x, z in pts])
                h80 = max(float(np.percentile(hs, 80)) * vs, ic['min_height_studs'])
                parts.append((round((bx0 + bx1) / 2, 1), round((bz0 + bz1) / 2, 1), round(bx1 - bx0, 1), round(bz1 - bz0, 1), round(h80, 1)))
                hmax = float(hs.max()) * vs
                if hmax > h80 * 1.25:
                    ridge = [x for (x, z), hh in zip(pts, hs) if hh * vs > 0.6 * hmax]
                    if ridge and max(ridge) - min(ridge) >= 40:
                        parts.append((round((min(ridge) + max(ridge)) / 2, 1), round((bz0 + bz1) / 2, 1),
                                      round(max(ridge) - min(ridge) + 40, 1), round((bz1 - bz0) * 0.7, 1), round(hmax, 1)))
        out.append({'id': e['id'], 'name': name, 'parts': parts, 'bounds': [round(v) for v in poly.bounds],
                    'peak_m': round(max(p[4] for p in parts) / vs, 1) if parts else 0})
    return out


# ---------------------------------------------------------------------------------------------------------------
# export
PARTS_PER = {'umbrellas': 4, 'lamps': 3, 'towers': 7, 'boats': 3, 'huts': 6, 'kites': 5}
FIELDS = {'umbrellas': 5, 'lamps': 4, 'towers': 4, 'boats': 5, 'huts': 5, 'kites': 6}


def lua_num(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def export(cfg, R, plan, fill, items, islands, probes, attribution, osm_bases, out_dir):
    rdir = os.path.join(out_dir, 'roblox')
    os.makedirs(rdir, exist_ok=True)
    for f in os.listdir(rdir):
        if f.endswith('.luau'):
            os.remove(os.path.join(rdir, f))
    header = f'-- generated by tools/mapgen/coast.py; do not edit. {attribution}. OSM base: {" / ".join(osm_bases)}\n'
    # --- terrain runs: one 4-stud row each, contiguous changed cells; codes index manifest.terrain.states ----------
    plans = [plan] + ([fill] if fill is not None else [])
    triples = sorted({tuple(int(v) for v in q[w][:, k]) for q in plans for w in ('new', 'old') for k in range(q[w].shape[1])})
    letter = {tr: chr(97 + i) for i, tr in enumerate(triples)}
    T = cfg['terrain']['tile_studs']

    def write_runs(q, prefix, what):
        order = np.lexsort((q['I'], q['J']))
        J, I = q['J'][order], q['I'][order]
        new, old = q['new'][:, order], q['old'][:, order]
        runs, k, n = [], 0, len(J)
        while k < n:
            e = k
            while e + 1 < n and J[e + 1] == J[k] and I[e + 1] == I[e] + 1:
                e += 1
            ns = ''.join(letter[(int(new[0, c]), int(new[1, c]), int(new[2, c]))] for c in range(k, e + 1))
            os_ = ''.join(letter[(int(old[0, c]), int(old[1, c]), int(old[2, c]))] for c in range(k, e + 1))
            runs.append((R.z0 + int(J[k]) * 4, R.x0 + int(I[k]) * 4, ns, os_))
            k = e + 1
        tiles = defaultdict(list)
        for r in runs:
            tiles[(math.floor(r[1] / T), math.floor(r[0] / T))].append(r)
        modules = []
        for (tx, tz) in sorted(tiles, key=lambda t: (t[1], t[0])):    # north -> south, west -> east
            cur, size = [], 0                                          # <= 150 KB of source per module
            for r in tiles[(tx, tz)]:
                line = f'{r[0]},{r[1]},"{r[2]}","{r[3]}",'
                if size + len(line) > 150_000 and cur:
                    modules.append(((tx, tz), cur)); cur, size = [], 0
                cur.append(line); size += len(line)
            if cur:
                modules.append(((tx, tz), cur))
        mods = []
        for idx, ((tx, tz), lines) in enumerate(modules, 1):
            name = f'{prefix}_{idx}'
            body = '\n'.join(' '.join(lines[i:i + 6]) for i in range(0, len(lines), 6))
            open(os.path.join(rdir, name + '.luau'), 'w', encoding='utf-8', newline='\n').write(
                header + f'-- {what}, tile x {tx * T}..{(tx + 1) * T}, z {tz * T}..{(tz + 1) * T} (map-local studs): runs of\n'
                '-- 4-stud cells, one 4-stud row each: z, x0, new states, old states (one letter per cell, manifest.terrain.states)\n'
                f'return {{ tile = {{ {tx * T}, {tz * T} }}, runs = {{\n{body}\n}} }}\n')
            mods.append((name, tx * T, tz * T, len(lines)))
        return mods, len(runs)

    tmods, nruns = write_runs(plan, 'terrain', 'coast terrain (default pass, seaward of the sand strip edge)')
    fmods, nfill = write_runs(fill, 'fill', 'OPTIONAL beach fill (landward: Ground -> Sand inside OSM beaches)') if fill is not None else ([], 0)
    # --- prop chunks ---------------------------------------------------------------------------------------------
    C = cfg['chunk_size_studs']
    chunks = defaultdict(lambda: defaultdict(list))
    for kind, rows in items.items():
        for row in rows:
            chunks[(math.floor(row[0] / C), math.floor(row[1] / C))][kind].append(row)
    cap = cfg['max_parts_per_chunk']
    chunk_parts = {}
    for key, kinds in chunks.items():
        parts = sum(PARTS_PER[k] * len(v) for k, v in kinds.items())
        while parts > cap and kinds['umbrellas']:            # thin umbrellas first (never happened in the 2026-10-19 run)
            kinds['umbrellas'] = kinds['umbrellas'][::2] if len(kinds['umbrellas']) > 1 else []
            parts = sum(PARTS_PER[k] * len(v) for k, v in kinds.items())
        assert parts <= cap, (key, parts)
        chunk_parts[key] = parts
    ids = sorted(chunks, key=lambda k: (k[1], k[0]))          # north -> south
    total_parts = sum(chunk_parts.values())
    island_parts = sum(len(i['parts']) for i in islands)
    assert total_parts + island_parts <= cfg['max_parts_total'], total_parts + island_parts
    for key in ids:
        cid = f'b{key[0]}_{key[1]}'
        kinds = chunks[key]
        lines = [header.rstrip('\n'), f'-- coast props chunk {cid}: {chunk_parts[key]} Parts (map-local studs; PattayaCoastBuilder adds the ORIGIN)',
                 'return {']
        for kind in ('umbrellas', 'lamps', 'towers', 'boats', 'huts', 'kites'):
            flat = [lua_num(v) for row in kinds.get(kind, []) for v in row]
            lines.append(f'  {kind} = {{ {", ".join(flat)} }},')
        lines.append('}')
        open(os.path.join(rdir, f'chunk_{cid}.luau'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    B = cfg['batch_size']
    batches = {f'b{i // B + 1}': [f'b{k[0]}_{k[1]}' for k in ids[i:i + B]] for i in range(0, len(ids), B)}
    # --- manifest ----------------------------------------------------------------------------------------------
    st = ', '.join('{ ' + ', '.join(f'"{MAT_NAMES[v]}"' for v in tr) + ' }' for tr in triples)
    wet = cfg['terrain']['wet_sand_color']
    lines = [header.rstrip('\n'),
             '-- PattayaCoastBuilder: Build({batch = "b1"}) ... props; BuildTerrain({tile = n}) the 4-stud shoreline; BuildIsland()',
             'return {', '  name = "coast",', f'  attribution = "{attribution}",', f'  osmBase = "{" / ".join(osm_bases)}",',
             f'  chunkSize = {C},', '  chunks = { ' + ', '.join(f'"b{k[0]}_{k[1]}"' for k in ids) + ' },',
             '  batchOrder = { ' + ', '.join(f'"{b}"' for b in batches) + ' },', '  batches = {']
    for b, v in batches.items():
        lines.append(f'    {b} = {{ ' + ', '.join(f'"{c}"' for c in v) + ' },')
    lines += ['  },', '  partsPerChunk = { ' + ', '.join(f'["b{k[0]}_{k[1]}"] = {chunk_parts[k]}' for k in ids) + ' },',
              '  terrain = {',
              '    -- voxel layers top (y -8..-4), mid (-12..-8), low (-16..-12); state letters a, b, ... index this list',
              f'    states = {{ {st} }},', f'    wetSandColor = {{ {wet[0]}, {wet[1]}, {wet[2]} }}, -- Terrain:SetMaterialColor(Mud) (Mud is unused elsewhere)',
              '    modules = { ' + ', '.join(f'{{ "{n}", {x}, {z}, {c} }}' for n, x, z, c in tmods) + ' }, -- name, tile x, tile z, runs',
              f'    cells = {plan["J"].size}, runs = {nruns},',
              '    -- OPTIONAL landward beach fill (BuildTerrain({fill = true})): moves the strip edge; NOT part of the default pass',
              '    fillModules = { ' + ', '.join(f'{{ "{n}", {x}, {z}, {c} }}' for n, x, z, c in fmods) + ' },',
              f'    fillCells = {fill["J"].size if fill is not None else 0}, fillRuns = {nfill},',
              '    -- landward-edge probe: map-local cell centres and the material the TOP voxel must still have after BuildTerrain',
              '    probe = { ' + ', '.join(f'{{ {x}, {z}, "{m}" }}' for x, z, m in probes) + ' },',
              '  },', '  islands = {']
    for isl in islands:
        lines.append(f'    {{ name = "{isl["name"]}", osmWay = {isl["id"]}, parts = {{ ' +
                     ', '.join('{ ' + ', '.join(lua_num(v) for v in p) + ' }' for p in isl['parts']) + ' } },')
    lines += ['  },', '}']
    open(os.path.join(rdir, 'manifest.luau'), 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    return dict(runs=nruns, terrain_modules=tmods, fill_modules=fmods, fill_runs=nfill, chunks=len(ids), batches=batches, chunk_parts=chunk_parts,
                prop_parts=total_parts, island_parts=island_parts, triples=triples)


def verify_export(R, plan, fill, rdir, triples):
    """Reads the written terrain modules back the way PattayaCoastBuilder does (letters -> states, one 4-stud row per
    run) and checks that the new codes reproduce the plan and the old codes the simulated old terrain, cell by cell."""
    names = {v: k for k, v in MAT_NAMES.items()}
    def apply(prefix, use_old):
        m = R.m.copy()
        n = 0
        for f in sorted(os.listdir(rdir)):
            if not (f.startswith(prefix + '_') and f.endswith('.luau')):
                continue
            src = open(os.path.join(rdir, f), encoding='utf-8').read()
            for z, x0, new, old in re.findall(r'(-?\d+),(-?\d+),"([a-z]+)","([a-z]+)"', src):
                z, x0 = int(z), int(x0)
                assert z % 4 == 0 and x0 % 4 == 0
                j, i = (z - R.z0) // 4, (x0 - R.x0) // 4
                for c, ch in enumerate(old if use_old else new):
                    tr = triples[ord(ch) - 97]
                    m[:, j, i + c] = tr
                n += 1
        return m, n
    for prefix, q in (('terrain', plan), ('fill', fill)):
        if q is None:
            continue
        want = R.m.copy()
        want[:, q['J'], q['I']] = q['new']
        got, n = apply(prefix, False)
        assert (got == want).all(), f'{prefix}: modules do not reproduce the plan'
        back, _ = apply(prefix, True)
        assert (back == R.m).all(), f'{prefix}: old codes do not restore the old terrain'
    return True


# ---------------------------------------------------------------------------------------------------------------
# check images
PAL = np.array([[0, 0, 0], [112, 94, 66], [232, 214, 160], [38, 92, 190], [150, 126, 92]], np.uint8)


def colour(top, mid):
    a = PAL[top].copy()
    a[(top == W) & (mid == S)] = [78, 176, 214]          # 4-stud water over sand
    return a


def render(R, newtop, newmid, graphs, items, win, path, scale, title):
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = win
    j0, j1, i0, i1 = (z0 - R.z0) // 4, (z1 - R.z0) // 4, (x0 - R.x0) // 4, (x1 - R.x0) // 4
    step = max(1, int(round(1 / scale))) if scale < 1 else 1
    A = colour(R.m[0][j0:j1:step, i0:i1:step], R.m[1][j0:j1:step, i0:i1:step])
    Bn = colour(newtop[j0:j1:step, i0:i1:step], newmid[j0:j1:step, i0:i1:step])
    px = scale * step if scale < 1 else scale       # pixels per 4-stud cell (after subsampling)
    h, w = A.shape[:2]
    up = max(1, int(scale)) if scale >= 1 else 1
    imgs = []
    for k, arr in enumerate((A, Bn)):
        im = Image.fromarray(arr).resize((w * up, h * up), Image.NEAREST)
        dr = ImageDraw.Draw(im)
        f = up / (4 * step)                          # pixels per stud
        for g in graphs[1:]:
            for e in g['edges']:
                pts = [((x - x0) * f, (z - z0) * f) for x, z in e['pts']]
                if all(p[0] < -50 or p[0] > im.width + 50 or p[1] < -50 or p[1] > im.height + 50 for p in pts):
                    continue
                dr.line(pts, fill=(70, 70, 76), width=max(1, int(e['width'] * f)))
        if k == 1:
            cols = {'umbrellas': (255, 90, 160), 'lamps': (255, 240, 120), 'towers': (230, 40, 40), 'boats': (255, 255, 255),
                    'huts': (160, 60, 255), 'kites': (255, 150, 0)}
            for kind, rows in items.items():
                for row in rows:
                    cx, cz = (row[0] - x0) * f, (row[1] - z0) * f
                    if 0 <= cx < im.width and 0 <= cz < im.height:
                        r = max(1.5, (4.5 if kind == 'umbrellas' else 3) * f)
                        dr.ellipse([cx - r, cz - r, cx + r, cz + r], fill=cols[kind])
        dr.rectangle([0, 0, im.width, 14], fill=(255, 255, 255))
        dr.text((4, 1), ('OLD (16-stud raster)' if k == 0 else 'NEW (4-stud cells + props)') + f'  {title}', fill=(0, 0, 0))
        imgs.append(im)
    out = Image.new('RGB', (imgs[0].width * 2 + 6, imgs[0].height), (255, 255, 255))
    out.paste(imgs[0], (0, 0))
    out.paste(imgs[1], (imgs[0].width + 6, 0))
    out.save(path)


# ---------------------------------------------------------------------------------------------------------------
def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    out_dir = rp(cfg['out_dir'])
    graphs = [jload(p) for p in cfg['graphs']]
    ox, oy = graphs[0]['origin_utm']
    for g in graphs[1:]:
        assert g['origin_utm'] == [ox, oy] and g['compression'] == graphs[0]['compression'], 'datasets differ in origin'
    k = graphs[0]['compression'] / graphs[0]['meters_per_stud']
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    tb = Transformer.from_crs(cfg['crs'], 'EPSG:4326', always_xy=True)

    def to_game(geom):
        E, N = tf.transform([q['lon'] for q in geom], [q['lat'] for q in geom])
        return [((e - ox) * k, -(n - oy) * k) for e, n in zip(E, N)]

    def to_lonlat(x, z):
        return tb.transform(x / k + ox, -z / k + oy)

    base, wide = parse_manifest(cfg['manifests']['base']), parse_manifest(cfg['manifests']['wide'])
    joints = []
    for p in cfg['joints']:
        joints += parse_joints(p)
    buildings = []
    for p in cfg['buildings']:
        buildings += jload(p)['buildings']
    layouts = [jload(p) for p in cfg['layouts']]
    palms, lights, landmarks = [], [], []
    for L in layouts:
        palms += L.get('palms', [])
        lights += L.get('lights', [])
        landmarks += L.get('landmarks', [])
    raw_ways, osm_bases = {}, []
    for p in cfg['osm_raw']:
        d = jload(p)
        osm_bases.append(d['osm3s']['timestamp_osm_base'])
        for e in d['elements']:
            if e['type'] == 'way' and 'geometry' in e:
                raw_ways[e['id']] = e
    print(f'inputs: {sum(len(g["edges"]) for g in graphs)} edges, {len(buildings)} buildings, {len(palms)} palms, '
          f'{len(lights)} street lights, {len(joints)} joint discs, {len(base["junctions"]) + len(wide["junctions"])} junction discs')

    # --- 1. terrain ------------------------------------------------------------------------------------------------
    R = simulate_old_terrain(base, wide)
    fx0, fx1, fz0, fz1 = wide['frame']
    sea, coast_lines = sea_polygon(graphs[-1], (fx0, fz0, fx1, fz1))
    blockers = Blockers(graphs, [base, wide], joints, buildings)
    zones = other_team_zones(cfg, raw_ways, to_game)
    tc = cfg['terrain']
    plan, rep_t, _ = plan_terrain(R, sea, coast_lines, blockers, zones, tc)
    J, I = plan['J'], plan['I']
    top = R.m[0]
    # assert (a) + (b): old top Water/Sand (or the Air seam row in the sea) and K Water/Sand cells to the east
    o_top = top[J, I]
    seam = o_top == AIR
    assert np.isin(o_top[~seam], (W, S)).all()
    assert (top[np.minimum(J[seam] + 1, R.nz - 1), I[seam]] == W).all()
    for kk in range(1, tc['landward_keep_cells'] + 1):
        jj = np.where(seam, np.minimum(J + 1, R.nz - 1), J)
        assert np.isin(top[jj, np.minimum(I + kk, R.nx - 1)], (W, S)).all(), 'a write reaches the landward edge'
    # measured landward edge: per row, every Sand cell whose east neighbour is not Water/Sand (strip ends)
    se_j, se_i = np.nonzero((top[:, :-1] == S) & ~np.isin(top[:, 1:], (W, S)))
    edge_by_row = defaultdict(list)
    for jj, ii in zip(se_j, se_i):
        edge_by_row[int(jj)].append(int(ii))
    margins = []
    for jj, ii in zip(J, I):
        ends = [e for e in edge_by_row.get(int(jj), []) if e >= ii]
        if ends:
            margins.append(min(ends) - ii)
    min_margin = min(margins) if margins else None
    assert min_margin is None or min_margin >= tc['landward_keep_cells'], min_margin
    # assert (c): no written cell square touches a road + sidewalk, disc, building (+clearance) or another team's area
    cell_boxes = shapely.box(R.x0 + I * 4, R.z0 + J * 4, R.x0 + I * 4 + 4, R.z0 + J * 4 + 4)
    bp = blockers.polys(tc['road_clear_studs'], tc['road_clear_studs'], tc['building_clear_studs']) + [z for _, z in zones]
    hits = STRtree(bp).query(cell_boxes, predicate='intersects')
    assert hits.shape[1] == 0, f'{hits.shape[1]} terrain cells touch a road/disc/building'
    rep_t.update({'landward_edge_strip_ends_measured': int(len(se_j)), 'min_cells_between_write_and_landward_edge': min_margin,
                  'cells_touching_roads_discs_buildings': 0})
    newtop, newmid = top.copy(), R.m[1].copy()
    newtop[J, I], newmid[J, I] = plan['new'][0], plan['new'][1]
    # probe samples: strip ends (last Sand cell, first landward cell) spread along the coast, none of them written
    written = set(zip(J.tolist(), I.tolist()))
    cand = [(int(a), int(b)) for a, b in zip(se_j, se_i) if (int(a), int(b)) not in written and (int(a), int(b) + 1) not in written]
    cand.sort()
    N = tc['probe_samples'] // 2
    probes = []
    for q in range(N):
        jj, ii = cand[int((q + 0.5) * len(cand) / N)]
        x, z = R.x0 + ii * 4 + 2, R.z0 + jj * 4 + 2
        probes.append((x, z, MAT_NAMES[int(top[jj, ii])]))
        probes.append((x + 4, z, MAT_NAMES[int(top[jj, ii + 1])]))

    # --- 2. props ------------------------------------------------------------------------------------------------
    pc = cfg['props']
    beaches = {}
    for bid in pc['beaches']:
        e = raw_ways[bid]
        beaches[bid] = {'name': e['tags'].get('name:en') or e['tags'].get('name'), 'poly': Polygon(to_game(e['geometry'])).buffer(0)}
    piers = [Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else LineString(pts)
             for e in raw_ways.values() if e.get('tags', {}).get('man_made') == 'pier' for pts in [to_game(e['geometry'])]]
    lm_polys = [Point(l['x'], l['z']).buffer(l.get('span', 20) / 2 + 10) for l in landmarks]
    prop_block = blockers.polys(pc['roads_clear'], pc['roads_clear'], pc['building_clear']) + [z for _, z in zones] + lm_polys \
        + [p.buffer(4) for p in piers]
    placer = Placer(prop_block, palms, lights, newtop, R)
    seen, coastal = set(), []
    for g in graphs:
        for e in g['edges']:
            if e['coastal'] and e['id'] not in seen:
                seen.add(e['id'])
                coastal.append(e)
    items = place_props(cfg, beaches, coast_lines, sea, placer, coastal, piers)
    # export-time check: footprints vs roads + sidewalks / discs / buildings with NO clearance, palms >= palm_clear
    bare = STRtree(blockers.polys(0, 0, 0))
    bad = 0
    for foot in placer.placed:
        bad += len(bare.query(foot, predicate='intersects'))
    palm_tree = STRtree([Point(p['x'], p['z']) for p in palms])
    near_palm = sum(1 for foot in placer.placed if len(palm_tree.query(foot, predicate='dwithin', distance=pc['lamp']['palm_clear'])))
    assert bad == 0 and near_palm == 0, (bad, near_palm)

    # --- 3. islands ----------------------------------------------------------------------------------------------
    islands, island_base = [], None
    if cfg.get('island_raw') and os.path.exists(rp(cfg['island_raw'])):
        iraw = jload(cfg['island_raw'])
        island_base = iraw['osm3s']['timestamp_osm_base']
        islands = build_islands(cfg, iraw, to_game, to_lonlat)
    bases = sorted(set(osm_bases)) + ([island_base] if island_base else [])

    # --- optional landward beach fill (separate opt-in step in the builder) ------------------------------------------
    fill = None
    if cfg.get('beach_fill'):
        bpolys = [Polygon(to_game(e['geometry'])).buffer(0) for e in raw_ways.values()
                  if e.get('tags', {}).get('natural') == 'beach' and len(e['geometry']) >= 4 and e['nodes'][0] == e['nodes'][-1]]
        fill, rep_f = plan_beach_fill(R, newtop, bpolys, coast_lines, blockers, zones, tc, cfg['beach_fill'])
        rep_t.update(rep_f)
        rep_t['fill_beach_polygons'] = len(bpolys)

    res = export(cfg, R, plan, fill, items, islands, probes, cfg['attribution'], bases, out_dir)
    verify_export(R, plan, fill, os.path.join(out_dir, 'roblox'), res['triples'])

    # --- images + report -----------------------------------------------------------------------------------------
    views = [((-4608, -10160, 9072, 16176), 'coast_check.png', 0.25, 'whole frame'),
             ((400, -1400, 1500, -300), 'coast_check_pattaya_n.png', 2, 'Pattaya Beach north'),
             ((-700, 1100, 400, 2200), 'coast_check_pattaya_s.png', 2, 'Pattaya Beach south / Bali Hai'),
             ((800, -5400, 1600, -4200), 'coast_check_wongamat.png', 2, 'Wong Amat / Naklua'),
             ((-1600, 9000, -400, 10200), 'coast_check_jomtien.png', 2, 'Jomtien Beach'),
             ((-2200, -3900, 1200, -3640), 'coast_check_seam.png', 1, 'seam row z -3776')]
    for win, name, sc, title in views:
        render(R, newtop, newmid, graphs, items, win, os.path.join(out_dir, name), sc, title)
    if fill is not None:                               # what the optional fill would add (NEW panel = default + fill)
        ft = newtop.copy()
        ft[fill['J'], fill['I']] = S
        for win, name, sc, title in views[1:5]:
            render(R, ft, newmid, graphs, items, win, os.path.join(out_dir, name.replace('coast_check_', 'coast_fill_')), sc,
                   title + ' + OPTIONAL beach fill')
    counts = {k: len(v) for k, v in items.items()}
    report = {'terrain': rep_t, 'terrain_runs': res['runs'], 'terrain_modules': [m[0] for m in res['terrain_modules']],
              'states': [[MAT_NAMES[v] for v in tr] for tr in res['triples']], 'props': counts,
              'prop_parts': res['prop_parts'], 'island_parts': res['island_parts'], 'chunks': res['chunks'],
              'max_chunk_parts': max(res['chunk_parts'].values()), 'batches': res['batches'],
              'rejects': dict(sorted(placer.rejects.items())), 'islands': [{k2: v for k2, v in i.items() if k2 != 'parts'} | {'parts': len(i['parts'])} for i in islands],
              'probe_samples': len(probes), 'osm_base': bases, 'modules_round_trip': 'ok', 'fill_runs': res['fill_runs'],
              'fill_modules': [m[0] for m in res['fill_modules']],
              'export_check': {'prop_footprints_touching_road_sidewalk_disc_building': bad, 'props_within_palm_clear': near_palm}}
    json.dump(report, open(os.path.join(out_dir, 'coast_report.json'), 'w', encoding='utf-8'), indent=1, default=int)
    print(json.dumps(report, indent=1, default=int))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else rp('tools/mapgen/config/coast.json'))
