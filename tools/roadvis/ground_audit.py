"""City-wide ground audit (team20/road-ground, OFFLINE, read only on build/): road edges that drop to the terrain, the
trench between road edges and building faces, floating buildings, objects a ground raise would bury, and the areas that
must not be raised. docs/ROAD_GROUND_PILOT.md section 2.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py ground --city      (build/roadground/city_audit.json)

State = what the place has (docs/STREAMING_ARCHITECTURE.md, checked against Studio counts): central + wide + corridor
chunks (slabs, fill triangles, sidewalks, buildings, props, corridor dressing), junction / joint discs, all 375 apron
chunks (aprons + corner fills), the 8 installed ShoulderChunks, all furniture chunks, the landmarks, the vis slice.
Terrain: Ground surface at y -2 on land (PattayaBuilder: filled up to -4); sea = the manifests' sea runs (Water up to
-4, 16-stud rows) and the coast modules' shoreline cells (4-stud, Water / Sand / Mud). Map-local studs.
"""
import json
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from tools.roadvis import ground, junction, world

TILE = 512.0
RAY = 60.0
CLASS_ORDER = ('trunk', 'trunk_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link', 'unclassified',
               'residential', 'none')


# ---- terrain material mask (sea / beach) -------------------------------------------------------------------------
class TerrainMask:
    """4-stud cell raster over the world frame: 0 land (Ground, surface -2), 1 water, 2 sand / wet sand (beach)"""

    def __init__(self, broot):
        man = _luau(os.path.join(broot, 'pattaya_wide', 'roblox', 'manifest.luau'))
        f = man['frame']
        self.x0, self.z0 = float(f['minX']), float(f['minZ'])
        self.nx = int(math.ceil((f['maxX'] - f['minX']) / 4))
        self.nz = int(math.ceil((f['maxZ'] - f['minZ']) / 4))
        self.m = np.zeros((self.nx, self.nz), np.uint8)
        # central slice sea: rows z .. z + seaCell, runs pairs x0, x1 (water), sand 48 studs east of x1
        cman = _luau(os.path.join(broot, 'central_pattaya', 'roblox', 'manifest.luau'))
        cell = cman.get('seaCell', 16)
        for row in _lst(cman, 'sea'):
            r = _lst(row, 'runs')
            for k in range(0, len(r) - 1, 2):
                self._rect(r[k], r[k + 1], row['z'], row['z'] + cell, 1)
                self._rect(r[k + 1], r[k + 1] + 48, row['z'], row['z'] + cell, 2)
        for row in _lst(man, 'sea'):
            r = _lst(row, 'runs')
            h = row.get('h', man.get('seaCell', 16))
            for k in range(0, len(r) - 2, 3):
                self._rect(r[k], r[k + 1], row['z'], row['z'] + h, 1)
                if r[k + 2] == 1:
                    self._rect(r[k + 1], r[k + 1] + 48, row['z'], row['z'] + h, 2)
        # coast shoreline modules (4-stud cells): the NEW top-voxel material of every listed cell
        cdir = os.path.join(broot, 'coast', 'roblox')
        self.coast_cells = 0
        if os.path.isdir(cdir):
            cm = _luau(os.path.join(cdir, 'manifest.luau'))
            states = [s[0] for s in cm['terrain']['states']]
            code = {'Water': 1, 'Sand': 2, 'Mud': 2, 'Ground': 0, 'Air': 0}
            for mod in cm['terrain']['modules']:
                t = open(os.path.join(cdir, mod[0] + '.luau'), encoding='utf-8').read()
                for z, x0, new in re.findall(r'(-?\d+),(-?\d+),"([a-z]+)","[a-z]*"', t):
                    z, x0 = float(z), float(x0)
                    for c, ch in enumerate(new):
                        v = code.get(states[ord(ch) - 97], 0)
                        self._rect(x0 + 4 * c, x0 + 4 * c + 4, z, z + 4, v, force=True)
                        self.coast_cells += 1

    def _rect(self, x0, x1, z0, z1, v, force=False):
        i0, i1 = int(max(0, math.floor((x0 - self.x0) / 4))), int(min(self.nx, math.ceil((x1 - self.x0) / 4)))
        k0, k1 = int(max(0, math.floor((z0 - self.z0) / 4))), int(min(self.nz, math.ceil((z1 - self.z0) / 4)))
        if i1 <= i0 or k1 <= k0:
            return
        if force:
            self.m[i0:i1, k0:k1] = v
        else:
            sub = self.m[i0:i1, k0:k1]
            sub[sub == 0] = v                       # water wins over a later sand strip
            if v == 1:
                sub[sub == 2] = 1

    def at(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        i = np.floor((xy[:, 0] - self.x0) / 4).astype(int)
        k = np.floor((xy[:, 1] - self.z0) / 4).astype(int)
        ok = (i >= 0) & (k >= 0) & (i < self.nx) & (k < self.nz)
        out = np.zeros(len(xy), np.uint8)
        out[ok] = self.m[i[ok], k[ok]]
        return out

    def area(self, v):
        return float((self.m == v).sum() * 16.0)

    def polygon(self, v, simplify=8.0):
        """union of the cells with value v (row runs), simplified"""
        rects = []
        for i in range(self.nx):
            col = self.m[i] == v
            if not col.any():
                continue
            d = np.diff(np.r_[0, col.astype(np.int8), 0])
            for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
                rects.append(box(self.x0 + 4 * i, self.z0 + 4 * a, self.x0 + 4 * i + 4, self.z0 + 4 * b))
        return unary_union(rects).simplify(simplify) if rects else Polygon()


def _luau(path):
    import sys
    sys.path.insert(0, os.path.join(world.REPO, 'tools', 'circuit'))
    try:
        import luau_table
    finally:
        sys.path.pop(0)
    return luau_table.load(path)


def _lst(d, k):
    v = d.get(k) if isinstance(d, dict) else None
    if v is None:
        return []
    if isinstance(v, dict):
        return v.get('_list', [])
    return v


# ---- road edges, per street class --------------------------------------------------------------------------------------
def installed_surfaces(W):
    """W['surf'] as built in the place: shoulder pieces only from the 8 installed ShoulderChunks"""
    return [s for s in W['surf'] if not (s['kind'] in world.SHOULDER_KINDS and s.get('module') not in ground.SHOULDER_INSTALLED)]


def city_edges(W, mask, step=2.0, log=print):
    """every boundary of the road-height surfaces (slab, fill, disc, apron, shoulder) and of the sidewalks / corner fills,
    tile by tile, every `step` studs: what lies 0.25 outside (building face, kerb up to a sidewalk / island, another
    surface within 1 stud = slot, terrain, water, sand), the drop to it, the street class (nearest graph edge within 60
    studs); for terrain-facing road edges a 60-stud outward ray: first building face / other surface / water / open"""
    surf = installed_surfaces(W)
    road = [s for s in surf if s['kind'] in world.ROAD_KINDS or s['kind'] in world.SHOULDER_KINDS]
    walk = [s for s in surf if s['kind'] in ('sidewalk', 'corner')]
    rt, wt = STRtree([s['poly'] for s in road]), STRtree([s['poly'] for s in walk])
    bt = STRtree([b['poly'] for b in W['blds']])
    gl = [LineString(e['pts']) for e in W['graph']['edges']]
    gcls = [e.get('class') or 'none' for e in W['graph']['edges']]
    gt = STRtree(gl)
    xs = [s['poly'].bounds for s in surf]
    bx0, bz0 = min(b[0] for b in xs), min(b[1] for b in xs)
    bx1, bz1 = max(b[2] for b in xs), max(b[3] for b in xs)
    tot = defaultdict(Counter)
    trench = defaultdict(Counter)
    widths = defaultdict(list)
    trench_area = Counter()
    ntile = 0
    for cx in range(int(math.floor(bx0 / TILE)), int(math.floor(bx1 / TILE)) + 1):
        for cz in range(int(math.floor(bz0 / TILE)), int(math.floor(bz1 / TILE)) + 1):
            T = box(cx * TILE, cz * TILE, (cx + 1) * TILE, (cz + 1) * TILE)
            ri = rt.query(T.buffer(4))
            if not len(ri):
                continue
            ntile += 1
            B = T.buffer(RAY + 4)
            R = unary_union([road[i]['poly'] for i in rt.query(B)])
            Wk = unary_union([walk[i]['poly'] for i in wt.query(B)]) if len(wt.query(B)) else Polygon()
            Bl = unary_union([W['blds'][i]['poly'] for i in bt.query(B)]) if len(bt.query(B)) else Polygon()
            R = R.buffer(0.05, join_style='mitre').buffer(-0.05, join_style='mitre')       # hairlines between pieces
            ALL = unary_union([R, Wk])
            for g in (R, Wk, Bl, ALL):
                shapely.prepare(g)
            for kind, U in (('road', R), ('sidewalk', Wk)):
                p, out = _ring_samples(U, T, step)
                if not len(p):
                    continue
                q = p + out * 0.25
                if kind == 'road':
                    up = shapely.contains_xy(Wk, q[:, 0], q[:, 1])
                else:
                    up = np.zeros(len(p), bool)
                    inr = shapely.contains_xy(R, q[:, 0], q[:, 1])          # sidewalk edge onto a road: a kerb, counted on the road side
                bld = shapely.contains_xy(Bl, q[:, 0], q[:, 1])
                insurf = shapely.contains_xy(ALL, q[:, 0], q[:, 1])
                near = np.zeros(len(p), bool)
                for d in (0.6, 1.0):
                    qq = p + out * d
                    near |= shapely.contains_xy(ALL, qq[:, 0], qq[:, 1])
                wm = mask.at(q)
                cls = _classes(gt, gcls, p)
                what = np.where(bld, 'building', np.where(up, 'kerb', np.where(insurf, 'surface', np.where(near, 'slot', np.where(
                    wm == 1, 'water', np.where(wm == 2, 'sand', 'terrain'))))))
                skip = inr if kind == 'sidewalk' else np.zeros(len(p), bool)
                for j in np.nonzero(~skip)[0]:
                    tot[(kind, cls[j])][str(what[j])] += step
                if kind != 'road':
                    continue
                face = what == 'terrain'
                fi = np.nonzero(face)[0]
                dws = _ray_water_many(mask, p[fi], out[fi])
                for j, dw in zip(fi, dws):
                    o, a = out[j], p[j]
                    ray = LineString([tuple(a + o * 0.3), tuple(a + o * RAY)])
                    db = ground._first(ray, Bl, a)
                    ds = ground._first(ray, ALL, a)
                    c = cls[j]
                    if db < ds and db < dw:
                        b = '0-8' if db <= 8 else '8-16' if db <= 16 else '16-24' if db <= 24 else '24-40' if db <= 40 else '40-60'
                        trench[c][b] += 1
                        if db <= 40:
                            widths[c].append(round(db, 1))
                            trench_area[c] += db * step
                    elif ds < dw:
                        trench[c]['surface'] += 1
                    elif math.isfinite(dw):
                        trench[c]['water'] += 1
                    else:
                        trench[c]['open'] += 1
    log(f'city edges: {ntile} tiles')
    rows = {}
    for (kind, c), cnt in tot.items():
        rows.setdefault(kind, {})[c] = {k: round(v, 0) for k, v in cnt.items()}
    return dict(step=step, tiles=ntile, edges=rows, trench={c: dict(v) for c, v in trench.items()},
                trench_area={c: round(v, 0) for c, v in trench_area.items()},
                trench_width_pct={c: _pct(v) for c, v in widths.items()})


def _pct(v):
    if not v:
        return {}
    a = np.asarray(v)
    return dict(n=int(len(a)), p10=round(float(np.percentile(a, 10)), 1), p50=round(float(np.percentile(a, 50)), 1),
                p90=round(float(np.percentile(a, 90)), 1))


def _ray_water_many(mask, a, o):
    """distance along each outward ray (2-stud steps) to the first water cell, inf when none within RAY"""
    if not len(a):
        return []
    ds = np.arange(1.0, RAY, 2.0)
    pts = a[:, None, :] + o[:, None, :] * ds[None, :, None]
    w = mask.at(pts.reshape(-1, 2)).reshape(len(a), len(ds)) == 1
    first = np.where(w.any(axis=1), ds[np.argmax(w, axis=1)], np.inf)
    return [float(v) for v in first]


def _classes(gt, gcls, p):
    pts = shapely.points(p)
    idx, dist = gt.query_nearest(pts, max_distance=60.0, return_distance=True, all_matches=False)
    out = ['none'] * len(p)
    for a, b in zip(idx[0], idx[1]):
        out[int(a)] = gcls[int(b)]
    return out


def _ring_samples(U, T, step):
    """boundary samples of U inside tile T: points and outward unit normals"""
    pts, outs = [], []
    if U.is_empty:
        return np.zeros((0, 2)), np.zeros((0, 2))
    for poly in junction.polys(U):
        if not poly.intersects(T):
            continue
        for ring in [poly.exterior] + list(poly.interiors):
            L = LineString(ring.coords)
            if not L.intersects(T):
                continue
            n = max(int(L.length / step), 1)
            s = (np.arange(n) + 0.5) * L.length / n
            a = shapely.get_coordinates(shapely.line_interpolate_point(L, s))
            b = shapely.get_coordinates(shapely.line_interpolate_point(L, np.minimum(s + 0.05, L.length)))
            t = b - a
            t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
            nm = np.stack([-t[:, 1], t[:, 0]], axis=1)
            inT = shapely.contains_xy(T, a[:, 0], a[:, 1])
            a, nm = a[inT], nm[inT]
            if not len(a):
                continue
            ina = shapely.contains_xy(U, a[:, 0] + nm[:, 0] * 0.25, a[:, 1] + nm[:, 1] * 0.25)
            pts.append(a)
            outs.append(np.where(ina[:, None], -nm, nm))
    if not pts:
        return np.zeros((0, 2)), np.zeros((0, 2))
    return np.vstack(pts), np.vstack(outs)


# ---- buildings ---------------------------------------------------------------------------------------------------------
def city_buildings(W, mask, step=2.0):
    """every PattayaBuilder building box (base y 0 = ROAD_TOP - 1): its perimeter sampled every `step` studs, 0.3
    outside: over terrain (the box floats 2.0 above the y -2 ground: a visible slit), over a road / sidewalk / shoulder
    (the base is inside that part: no gap), over another building, over sand / water"""
    surf = installed_surfaces(W)
    st = STRtree([s['poly'] for s in surf])
    bt = STRtree([b['poly'] for b in W['blds']])
    n_any = 0
    tot = Counter()
    float_len = []
    for bi, b in enumerate(W['blds']):
        ring = LineString(b['poly'].exterior.coords)
        n = max(int(ring.length / step), 1)
        s = (np.arange(n) + 0.5) * ring.length / n
        a = shapely.get_coordinates(shapely.line_interpolate_point(ring, s))
        c = np.array(b['poly'].centroid.coords[0])
        v = a - c
        v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        q = a + v * 0.3
        near = st.query(b['poly'].buffer(1.0))
        U = unary_union([surf[i]['poly'] for i in near]) if len(near) else Polygon()
        ob = [W['blds'][i]['poly'] for i in bt.query(b['poly'].buffer(1.0)) if i != bi]
        UB = unary_union(ob) if ob else Polygon()
        on_s = shapely.contains_xy(U, q[:, 0], q[:, 1]) if not U.is_empty else np.zeros(len(q), bool)
        on_b = shapely.contains_xy(UB, q[:, 0], q[:, 1]) if not UB.is_empty else np.zeros(len(q), bool)
        wm = mask.at(q)
        terr = ~on_s & ~on_b & (wm == 0)
        tot['perimeter'] += n * step
        tot['over_surface'] += float(on_s.sum() * step)
        tot['over_building'] += float((on_b & ~on_s).sum() * step)
        tot['over_terrain'] += float(terr.sum() * step)
        tot['over_sand'] += float((~on_s & ~on_b & (wm == 2)).sum() * step)
        tot['over_water'] += float((~on_s & ~on_b & (wm == 1)).sum() * step)
        if terr.any():
            n_any += 1
            float_len.append(float(terr.sum() * step))
    return dict(buildings=len(W['blds']), base_y=0.0, terrain_y=ground.TERRAIN_TOP, gap_over_terrain=2.0,
                with_terrain_perimeter=n_any, share_buildings=round(n_any / max(len(W['blds']), 1), 3),
                perimeter={k: round(v, 0) for k, v in tot.items()},
                share_perimeter_over_terrain=round(tot['over_terrain'] / max(tot['perimeter'], 1), 3),
                float_len_pct=_pct(float_len))


# ---- objects at terrain level ----------------------------------------------------------------------------------------
# base / top heights exactly as the builders place them (PattayaBuilder, PattayaFurnitureBuilder, PattayaCoastBuilder,
# PattayaLandmarksBuilder, PattayaVisSliceBuilder / VisMeshBuilder): (kind, base y, top y, colliding)
OBJ = {
    'PalmTrunk': (0.0, 26.0, True),          # PattayaBuilder props: trunk foot at ROAD_TOP - 1, 26 .. 34 tall
    'LightPole': (1.0, 21.0, True),          # foot at ROAD_TOP
    'RoadSign': (0.0, 16.0, True),           # PattayaBuilder buildRoadSigns post foot at ROAD_TOP - 1
    'TreeTrunk': (-2.0, 7.0, True),          # corridor dressing GROUND_Y (trunk 9 .. 13.5)
    'UtilityPole': (-2.0, 24.0, True),       # corridor dressing + furniture poles: GROUND_Y, 26 tall
    'Gantry': (-2.0, 29.0, True),            # corridor gantry posts
    'SignalPole': (-2.0, 16.0, True),        # furniture: GROUND_Y + 9, 18 tall
    'NameSignPost': (-2.0, 7.4, True),       # furniture: GROUND_Y + 4.7, 9.4 tall (board 7.4 .. 10.6)
    'ShelterPad': (-2.0, 1.6, True),         # furniture: pad from GROUND_Y to the kerb top 1.6, shelter on top
    'BusSignPole': (-2.0, 8.0, True),
    'TaxiPost': (-2.0, 6.0, True),           # canopy at GROUND_Y + 8.15
    'CoastProp': (-2.0, 6.0, False),         # beach props on the sand (GROUND_Y)
    'Building': (0.0, 30.0, True),
}


def city_objects(broot, W, mask, field=None, bbox=None, state=None):
    """every object whose foot stands at or near the terrain, from the exported data, with the builder's foot height;
    counts per kind (city / inside `bbox`) and what a raise to the pilot height would bury"""
    rows = []

    def add(kind, x, z, src):
        b, t, c = OBJ[kind]
        rows.append(dict(kind=kind, x=float(x), z=float(z), base=b, top=t, collide=c, src=src))

    for rel in ('central_pattaya/roblox', 'pattaya_wide/roblox', 'bira/roblox_corridor'):
        d = os.path.join(broot, *rel.split('/'))
        for f in sorted(os.listdir(d)):
            if not (f.startswith('chunk_') and f.endswith('.luau')):
                continue
            cd = _luau(os.path.join(d, f))
            p = _lst(cd, 'palms')
            for i in range(0, len(p) - 1, 2):
                add('PalmTrunk', p[i], p[i + 1], rel)
            p = _lst(cd, 'lights')
            for i in range(0, len(p) - 3, 4):
                add('LightPole', p[i], p[i + 1], rel)
            p = _lst(cd, 'trees')
            for i in range(0, len(p) - 2, 3):
                add('TreeTrunk', p[i], p[i + 1], rel)
            p = _lst(cd, 'poles')
            for i in range(0, len(p) - 4, 5):
                add('UtilityPole', p[i], p[i + 1], rel)
            for s in _lst(cd, 'roadSigns'):
                add('RoadSign', s[0], s[1], rel)
            for g in _lst(cd, 'gantries'):
                add('Gantry', g[0], g[1], rel)
        man = _luau(os.path.join(d, 'manifest.luau'))
        for s in _lst(man, 'signs'):
            add('RoadSign', s[0], s[1], rel)
    fd = os.path.join(broot, 'furniture', 'roblox')
    for f in sorted(os.listdir(fd)):
        if not (f.startswith('chunk_') and f.endswith('.luau')):
            continue
        cd = _luau(os.path.join(fd, f))
        r = _lst(cd, 'signals')
        for i in range(0, len(r) - 7, 8):
            add('SignalPole', r[i], r[i + 1], 'furniture')
        for s in _lst(cd, 'nameSigns'):
            add('NameSignPost', s[0], s[1], 'furniture')
        for s in _lst(cd, 'shelters'):
            add('ShelterPad', s[0], s[1], 'furniture')
            add('BusSignPole', s[0], s[1], 'furniture')
        r = _lst(cd, 'taxis')
        for i in range(0, len(r) - 4, 5):
            add('TaxiPost', r[i], r[i + 1], 'furniture')
        r = _lst(cd, 'poles')
        for i in range(0, len(r) - 4, 5):
            add('UtilityPole', r[i], r[i + 1], 'furniture')
    cdir = os.path.join(broot, 'coast', 'roblox')
    if os.path.isdir(cdir):
        cm = _luau(os.path.join(cdir, 'manifest.luau'))
        for cid in _lst(cm, 'chunks'):
            cd = _luau(os.path.join(cdir, f'chunk_{cid}.luau'))
            for kind, stride in (('umbrellas', 5), ('lamps', 4), ('towers', 4), ('boats', 5), ('huts', 5), ('kites', 6)):
                r = _lst(cd, kind)
                for i in range(0, len(r) - stride + 1, stride):
                    add('CoastProp', r[i], r[i + 1], 'coast')
    for b in W['blds']:
        c = b['poly'].centroid
        rows.append(dict(kind='Building', x=c.x, z=c.y, base=0.0, top=b['h'], collide=True, src='buildings'))
    xy = np.array([[r['x'], r['z']] for r in rows])
    wm = mask.at(xy)
    for r, w in zip(rows, wm):
        r['zone'] = 'water' if w == 1 else 'sand' if w == 2 else 'land'
    out = dict(city=Counter(), city_on_land=Counter())
    for r in rows:
        out['city'][r['kind']] += 1
        if r['zone'] == 'land':
            out['city_on_land'][r['kind']] += 1
    if bbox is not None:
        B = box(*bbox)
        inside = [r for r in rows if B.contains(Point(r['x'], r['z']))]
        out['area'] = Counter(r['kind'] for r in inside)
        if field is not None:
            bu = ground.buried(inside, field, state)
            out['area_buried'] = {}
            for k in sorted(set(r['kind'] for r in bu)):
                sel = [r for r in bu if r['kind'] == k]
                out['area_buried'][k] = dict(n=len(sel), base=sel[0]['base'], top=sel[0]['top'],
                                             buried_max=max(r['buried'] for r in sel), buried_min=min(r['buried'] for r in sel),
                                             float_gap_max=max(r['float_gap'] for r in sel),
                                             on=dict(Counter(r['stands_on'] for r in sel)),
                                             visible_min=min(r['visible'] for r in sel))
            out['area_rows'] = [dict(r, x=round(r['x'] + world.ORIGIN[0], 1), z=round(r['z'], 1)) for r in bu if r['kind'] != 'Building']
    out['city'] = dict(out['city'])
    out['city_on_land'] = dict(out['city_on_land'])
    if 'area' in out:
        out['area'] = dict(out['area'])
    return out, rows


# ---- areas that must not be raised ----------------------------------------------------------------------------------------
def landmark_low_parts(broot, raise_to=0.43, margin=0.3):
    """per landmark: parts whose top lies below the raised ground + margin (a raise would bury them: floating market
    water, plazas, steps), from the landmark chunk rows {name, shape, sx, sy, sz, x, y, z, rx, ry, rz, ...}"""
    d = os.path.join(broot, 'landmarks', 'roblox')
    out = {}
    for f in sorted(os.listdir(d)):
        if not f.startswith('chunk_'):
            continue
        cd = _luau(os.path.join(d, f))
        for lm in _lst(cd, 'landmarks'):
            r = _lst(lm, 'parts')
            low, lowest, n = 0, 99.0, 0
            for i in range(0, len(r) - 14, 15):
                sx, sy, sz, y, rz = r[i + 2], r[i + 3], r[i + 4], r[i + 6], r[i + 10]
                h = sx if abs(abs(rz) - math.pi / 2) < 0.05 else sy          # a vertical cylinder is rolled 90 deg
                bottom, top = y - h / 2, y + h / 2
                n += 1
                lowest = min(lowest, bottom)
                if top < raise_to + margin:
                    low += 1
            out[lm['id']] = dict(parts=n, buried_by_a_raise=low, lowest_bottom=round(lowest, 2), x=lm['x'], z=lm['z'])
    return out


def no_raise_zones(broot, W, mask):
    """the places a city-wide raise has to leave alone (map-local unless noted), with sizes"""
    lm = _luau(os.path.join(broot, 'landmarks', 'roblox', 'manifest.luau'))
    marks = [dict(id=l['id'], x=l['x'], z=l['z']) for l in _lst(lm, 'landmarks')]
    vb = None
    vd = os.path.join(broot, 'vis_slice', 'roblox')
    xs, zs = [], []
    for f in sorted(os.listdir(vd)) if os.path.isdir(vd) else []:
        if f.startswith('chunk_'):
            for b in _lst(_luau(os.path.join(vd, f)), 'buildings'):
                xs.append(b['x'])
                zs.append(b['z'])
    if xs:
        vb = [round(min(xs)), round(min(zs)), round(max(xs)), round(max(zs))]
    cm = _luau(os.path.join(broot, 'coast', 'roblox', 'manifest.luau')) if os.path.isdir(os.path.join(broot, 'coast', 'roblox')) else {}
    wide = _luau(os.path.join(broot, 'pattaya_wide', 'roblox', 'manifest.luau'))
    return dict(
        frame_local=dict(wide['frame']), base_frame_local=dict(wide['baseFrame']),
        water_studs2=round(mask.area(1), 0), sand_studs2=round(mask.area(2), 0), coast_cells=mask.coast_cells,
        coast_prop_chunks=len(_lst(cm, 'chunks')), coast_islands=[i['name'] for i in _lst(cm, 'islands')],
        landmarks=marks, landmark_low_parts=landmark_low_parts(broot), vis_slice_bbox_local=vb,
        race_map_world=[6000, 100, 0], streaming_proto_world_x=60000, template_world=[0, 0, 0],
    )


def run(broot=None, log=print, field=None, pilot_bbox=None):
    W = world.load(broot)
    mask = TerrainMask(W['broot'])
    out = dict(edges=city_edges(W, mask, log=log))
    out['buildings'] = city_buildings(W, mask)
    out['objects'], rows = city_objects(W['broot'], W, mask, field=field, bbox=pilot_bbox)
    out['no_raise'] = no_raise_zones(W['broot'], W, mask)
    return W, mask, out
