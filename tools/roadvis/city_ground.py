"""The ground at road level for city batches (PattayaRoadGroundBuilder, city mode). OFFLINE.

Studio facts (leader, 2026-10-22, the pilot box): the terrain surface is the centre of the top filled voxel plus 4 x its
occupancy. Cell -1 (y -4 .. 0, centre -2) with occupancy (h + 2) / 4 over a full cell -2 puts the surface at h:
0.725 -> +0.9 (measured 0.91). Terrain:FillBlock overshoots, so the builder writes voxels with explicit occupancies.
With the ground at +0.4 a car driving from the ground back onto the road at 70 studs/s flipped at the 0.6 step; at
+0.9 (steps about 0.1, largest 0.24) every drive on / off the road at 70 and 100 stayed upright. So every batch raises
its box to +0.9 and ramps down to -2 over 20 studs only where no other raised box continues (the builder writes the
highest occupancy any raised batch gives a column: neighbouring boxes merge with no ramp between them).

Never raised (data the builder enforces, `PattayaDataRoadGroundNoRaise`): sea and beach sand (the manifests' sea runs
and the coast modules' shoreline cells), the coast islands, landmarks with parts a raise would bury (top below
+1.2), everything outside the city terrain frame (the Bira corridor and venue have their own terrain). Toward a
never-raise zone the ground ramps down to -2 inside the raised side (no cliff at the beach).

Map-local studs (world = local + (20000, 0, 0)) unless a name says world; voxel indices are world / 4.
"""
import math
import os

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from tools.roadvis import city, ground, ground_audit, world

VOX = 4.0
TOP = 0.9
OCC = (TOP + 2.0) / VOX                 # 0.725
RAMP = 20.0
FLAT = 0.0
WINDOW = (0.85, 0.95)                   # accepted measured surface (Studio measured 0.91 for 0.725)
LEVELS = 63                             # occupancy levels in the data: level / 63 x OCC (plateau = 63 = OCC exactly)
ALPHA = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_+'   # 64 characters, index = level
PAVE_BLD, PAVE_EDGE = 20.0, 10.0
LANDMARK_MARGIN = 8.0
ISLAND_MARGIN = 16.0
PILOT_PLATEAU_WORLD = (24220.0, 648.0, 24820.0, 1252.0)   # the leader's +0.9 raise (box snapped to the voxel grid)


# ---- never raise -----------------------------------------------------------------------------------------------------
class NoRaise:
    """boolean voxel-column raster over the city terrain frame: True = never raise (sea, sand, coast cells, landmark
    footprints with low parts); plus rectangles outside the frame (islands)"""

    def __init__(self, broot, log=print):
        mask = ground_audit.TerrainMask(broot)
        self.x0, self.z0 = mask.x0, mask.z0                  # local frame corner (voxel aligned: -4608, -10160)
        self.nx, self.nz = mask.nx, mask.nz
        self.i0 = int(round((self.x0 + city.ORIGIN[0]) / VOX))
        self.k0 = int(round(self.z0 / VOX))
        self.m = mask.m > 0
        self.kind = mask.m.copy()                            # 1 water, 2 sand, 3 landmark
        self.landmarks = []
        low = ground_audit.landmark_low_parts(broot, raise_to=TOP, margin=0.3)
        d = os.path.join(broot, 'landmarks', 'roblox')
        for f in sorted(os.listdir(d)):
            if not f.startswith('chunk_'):
                continue
            cd = ground_audit._luau(os.path.join(d, f))
            for lm in ground_audit._lst(cd, 'landmarks'):
                if not low.get(lm['id'], {}).get('buried_by_a_raise'):
                    continue
                r = ground_audit._lst(lm, 'parts')
                xs, zs = [], []
                for i in range(0, len(r) - 14, 15):
                    sx, sz, x, z = r[i + 2], r[i + 4], r[i + 5], r[i + 7]
                    rr = max(sx, sz) / 2
                    xs += [x - rr, x + rr]
                    zs += [z - rr, z + rr]
                bb = (min(xs) - LANDMARK_MARGIN, min(zs) - LANDMARK_MARGIN, max(xs) + LANDMARK_MARGIN, max(zs) + LANDMARK_MARGIN)
                self.landmarks.append(dict(id=lm['id'], box_local=[round(v, 1) for v in bb], low_parts=low[lm['id']]['buried_by_a_raise']))
                self._mark(bb, 3)
        self.islands = []
        cm = ground_audit._luau(os.path.join(broot, 'coast', 'roblox', 'manifest.luau'))
        for isl in ground_audit._lst(cm, 'islands'):
            xs, zs = [], []
            for p in ground_audit._lst(isl, 'parts'):
                x, z, w, dd = p[0], p[1], p[2], p[3]
                xs += [x - w / 2, x + w / 2]
                zs += [z - dd / 2, z + dd / 2]
            if xs:
                bb = (min(xs) - ISLAND_MARGIN, min(zs) - ISLAND_MARGIN, max(xs) + ISLAND_MARGIN, max(zs) + ISLAND_MARGIN)
                self.islands.append(dict(name=isl['name'], box_local=[round(v, 1) for v in bb]))
                self._mark(bb, 4)
        log(f'never raise: water {int((self.kind == 1).sum())}, sand {int((self.kind == 2).sum())}, landmark '
            f'{int((self.kind == 3).sum())} voxel columns; {len(self.landmarks)} landmarks, {len(self.islands)} islands')

    def _mark(self, bb, v):
        a0 = max(0, int(math.floor((bb[0] - self.x0) / VOX)))
        a1 = min(self.nx, int(math.ceil((bb[2] - self.x0) / VOX)))
        b0 = max(0, int(math.floor((bb[1] - self.z0) / VOX)))
        b1 = min(self.nz, int(math.ceil((bb[3] - self.z0) / VOX)))
        if a1 > a0 and b1 > b0:
            self.m[a0:a1, b0:b1] = True
            self.kind[a0:a1, b0:b1] = v

    def at_columns(self, ii, kk):
        """True where a world voxel column (i, k) must never be raised (outside the frame: True)"""
        a = np.asarray(ii) - self.i0
        b = np.asarray(kk) - self.k0
        ok = (a >= 0) & (b >= 0) & (a < self.nx) & (b < self.nz)
        out = np.ones(np.broadcast(a, b).shape, bool)
        out[ok] = self.m[a[ok], b[ok]]
        return out

    def runs(self):
        """[(i, k0, k1)] world voxel rows (i) with runs of never-raise columns k0..k1 (inclusive), inside the frame"""
        out = []
        for a in range(self.nx):
            col = self.m[a]
            if not col.any():
                continue
            dd = np.diff(np.r_[0, col.astype(np.int8), 0])
            for s, e in zip(np.nonzero(dd == 1)[0], np.nonzero(dd == -1)[0]):
                out.append((self.i0 + a, self.k0 + int(s), self.k0 + int(e) - 1))
        return out


# ---- the column plan of one batch ----------------------------------------------------------------------------------
def snap_out(bw):
    """a world box snapped outward to the voxel grid -> (i0, k0, i1, k1) voxel columns, inclusive"""
    return (int(math.floor(bw[0] / VOX)), int(math.floor(bw[1] / VOX)), int(math.ceil(bw[2] / VOX)) - 1, int(math.ceil(bw[3] / VOX)) - 1)


def plan(bw, nr, paved=None, blds=None, frame_ok=True):
    """the voxel columns a batch raises: the plateau = the box snapped outward to the voxel grid, then a 20-stud ramp.
    Occupancy per column = OCC x ramp factor, lowered toward never-raise columns (the ramp sits on the raised side),
    0 on never-raise columns. Materials: Pavement within 20 studs of a building or 10 studs of a paved edge on the
    plateau (opt-in in the builder), Ground elsewhere. Returns dict like ground.plan (i0, k0, ni, nk, occ, mat, level,
    plateau)."""
    pi0, pk0, pi1, pk1 = snap_out(bw)
    pad = int(math.ceil((FLAT + RAMP) / VOX))
    i0, k0, i1, k1 = pi0 - pad, pk0 - pad, pi1 + pad, pk1 + pad
    ii, kk = np.meshgrid(np.arange(i0, i1 + 1), np.arange(k0, k1 + 1), indexing='ij')
    cx, cz = ii * VOX + VOX / 2, kk * VOX + VOX / 2
    px0, pz0, px1, pz1 = pi0 * VOX, pk0 * VOX, (pi1 + 1) * VOX, (pk1 + 1) * VOX
    dx = np.maximum(np.maximum(px0 - cx, cx - px1), 0.0)
    dz = np.maximum(np.maximum(pz0 - cz, cz - pz1), 0.0)
    d = np.hypot(dx, dz)
    f = np.where(d <= FLAT, 1.0, np.clip(1.0 - (d - FLAT) / RAMP, 0.0, 1.0))
    plateau = d <= 0.0
    bad = nr.at_columns(ii, kk)
    if bad.any():
        # distance (studs) from each column centre to the nearest never-raise column (a square of 4 studs)
        bi, bk = np.nonzero(bad)
        cells = unary_union([box(ii[a, b] * VOX, kk[a, b] * VOX, ii[a, b] * VOX + VOX, kk[a, b] * VOX + VOX) for a, b in zip(bi, bk)])
        # never-raise columns just outside the region matter too (the ramp toward them)
        ring_i, ring_k = np.meshgrid(np.arange(i0 - pad, i1 + pad + 1), np.arange(k0 - pad, k1 + pad + 1), indexing='ij')
        rb = nr.at_columns(ring_i, ring_k)
        extra = [box(ring_i[a, b] * VOX, ring_k[a, b] * VOX, ring_i[a, b] * VOX + VOX, ring_k[a, b] * VOX + VOX) for a, b in zip(*np.nonzero(rb))]
        cells = unary_union([cells] + extra)
        dn = shapely.distance(cells, shapely.points(np.stack([cx.ravel(), cz.ravel()], axis=1))).reshape(cx.shape)
        f = np.minimum(f, np.clip(dn / RAMP, 0.0, 1.0))
        f[bad] = 0.0
    else:
        ring_i, ring_k = np.meshgrid(np.arange(i0 - pad, i1 + pad + 1), np.arange(k0 - pad, k1 + pad + 1), indexing='ij')
        rb = nr.at_columns(ring_i, ring_k)
        if rb.any():
            cells = unary_union([box(ring_i[a, b] * VOX, ring_k[a, b] * VOX, ring_i[a, b] * VOX + VOX, ring_k[a, b] * VOX + VOX) for a, b in zip(*np.nonzero(rb))])
            dn = shapely.distance(cells, shapely.points(np.stack([cx.ravel(), cz.ravel()], axis=1))).reshape(cx.shape)
            f = np.minimum(f, np.clip(dn / RAMP, 0.0, 1.0))
    level = np.rint(f * LEVELS).astype(int)
    occ = OCC * level / LEVELS
    G = dict(i0=i0, k0=k0, ni=i1 - i0 + 1, nk=k1 - k0 + 1, occ=occ, level=level, plateau=plateau,
             plateau_vox=(pi0, pk0, pi1, pk1), box_world=list(bw),
             counts=dict(columns=int(occ.size), written=int((level > 0).sum()), plateau=int((plateau & (level == LEVELS)).sum()),
                         ramp=int(((level > 0) & ~(plateau & (level == LEVELS))).sum()), never_raise=int(bad.sum()),
                         plateau_lowered=int((plateau & (level < LEVELS)).sum())))
    return add_materials(G, paved, blds)


def add_materials(G, paved=None, blds=None):
    """the material of every raised column (1 Ground, 2 Pavement: within 20 studs of a building or 10 studs of a paved
    edge, on the plateau; opt-in in the builder); the levels of G are not touched. Returns G."""
    level, plateau = G['level'], G['plateau']
    mat = np.zeros(level.shape, np.uint8)
    mat[level > 0] = 1
    if paved is not None or blds is not None:
        ii, kk = np.meshgrid(np.arange(G['i0'], G['i0'] + G['ni']), np.arange(G['k0'], G['k0'] + G['nk']), indexing='ij')
        cx, cz = ii * VOX + VOX / 2, kk * VOX + VOX / 2
        loc = np.stack([cx.ravel() - city.ORIGIN[0], cz.ravel()], axis=1)
        pts = shapely.points(loc)
        near = np.zeros(len(loc), bool)
        if blds is not None and not blds.is_empty:
            near |= shapely.distance(blds, pts) <= PAVE_BLD
        if paved is not None and not paved.is_empty:
            near |= shapely.distance(paved, pts) <= PAVE_EDGE
        pave = near.reshape(level.shape) & plateau & (level == LEVELS)
        mat[pave] = 2
    G['mat'] = mat
    G['counts'] = dict(G['counts'], pavement=int((mat == 2).sum()), ground=int((mat == 1).sum()))
    return G


class FullTest:
    """option B's test: is every voxel column under a (map-local) shape raised to the plateau (+0.9) by at least one of
    the plans (the batch's own plan, the pilot's hand raise, batches raised before)? Conservative: every column that the
    shape's bounding box touches must be at the plateau."""

    def __init__(self, plans):
        self.plans = [p for p in plans if p is not None]

    def __call__(self, poly):
        x0, z0, x1, z1 = poly.bounds
        i0, i1 = int(math.floor((x0 + city.ORIGIN[0]) / VOX)), int(math.floor((x1 + city.ORIGIN[0]) / VOX))
        k0, k1 = int(math.floor(z0 / VOX)), int(math.floor(z1 / VOX))
        ok = np.zeros((i1 - i0 + 1, k1 - k0 + 1), bool)
        for P in self.plans:
            a0, b0 = max(i0, P['i0']), max(k0, P['k0'])
            a1, b1 = min(i1, P['i0'] + P['ni'] - 1), min(k1, P['k0'] + P['nk'] - 1)
            if a1 < a0 or b1 < b0:
                continue
            sub = P['level'][a0 - P['i0']:a1 - P['i0'] + 1, b0 - P['k0']:b1 - P['k0'] + 1] >= LEVELS
            ok[a0 - i0:a1 - i0 + 1, b0 - k0:b1 - k0 + 1] |= sub
        return bool(ok.all())


def pilot_plan(nr):
    """the leader's hand-made +0.9 raise in the pilot box (the model: the box snapped to the voxel grid, 20-stud ramp)"""
    return plan(PILOT_PLATEAU_WORLD, nr)


def encode_rows(G):
    """one string per voxel row (x index): 2 characters per column (material . / g / p, level 0..63)"""
    out = []
    for a in range(G['ni']):
        s = []
        for b in range(G['nk']):
            lv = int(G['level'][a, b])
            m = '.' if lv == 0 else ('p' if G['mat'][a, b] == 2 else 'g')
            s.append(m + ALPHA[lv])
        out.append(''.join(s))
    return out


def calibration_columns(G, avoid=None, step=64.0):
    """world centres of plateau columns on a 64-stud lattice, >= 8 studs inside the plateau, at the full height, away
    from roads / buildings (avoid: local geometry): terrain-only raycasts measure the surface there"""
    pi0, pk0, pi1, pk1 = G['plateau_vox']
    x0, z0, x1, z1 = pi0 * VOX, pk0 * VOX, (pi1 + 1) * VOX, (pk1 + 1) * VOX
    out = []
    for x in np.arange(x0 + 8, x1 - 7, step):
        for z in np.arange(z0 + 8, z1 - 7, step):
            i, k = int(math.floor(x / VOX)), int(math.floor(z / VOX))
            a, b = i - G['i0'], k - G['k0']
            if G['level'][a, b] != LEVELS:
                continue
            out.append((i * VOX + 2.0, k * VOX + 2.0))
    return out


def edge_pairs(st, area, step=8.0):
    """road-to-ground edge check pairs (ground_export.edge_pairs): (inside 0.6 on the road, outside 1.5 on the ground),
    world, and the expected step"""
    E = ground.edge_samples(st, area, step=1.0, road_only=True)
    if not E.get('n'):
        return []
    face = ~E['bld'] & ~E['slot'] & ~E['kerb']
    pairs, last = [], None
    for j in np.nonzero(face)[0]:
        p, o = E['p'][j], E['out'][j]
        if last is not None and np.hypot(*(p - last)) < step:
            continue
        a, b = p - o * 0.6, p + o * 1.5
        ha, hb = st.at([a])[0], st.at([b])[0]
        if not (0.95 <= ha <= 1.01) or hb > 0.95 or st.surf([b])[0] > -1.9:
            continue
        pairs.append((a[0] + city.ORIGIN[0], a[1], b[0] + city.ORIGIN[0], b[1], ha - hb))
        last = p
    return pairs


def grid_expected(st, area, res=2.0):
    """what RG.Probe(<id>)'s 2-stud raycast grid should find over the box (ground_export.probe_expected)"""
    x0, z0, x1, z1 = area.bounds
    xs = np.arange(x0 + res / 2, x1, res)
    zs = np.arange(z0 + res / 2, z1, res)
    X, Z = np.meshgrid(xs, zs, indexing='ij')
    h = st.at(np.stack([X.ravel(), Z.ravel()], axis=1)).reshape(X.shape)
    floor = h <= 1.8
    worst, drops = 0.0, 0
    for di, dj in ((1, 0), (0, 1)):
        a, b = h[:h.shape[0] - di, :h.shape[1] - dj], h[di:, dj:]
        ok = floor[:h.shape[0] - di, :h.shape[1] - dj] & floor[di:, dj:]
        d = np.where(ok, np.abs(a - b), 0.0)
        worst = max(worst, float(d.max()))
        drops += int((d >= ground.DROP).sum())
    return dict(rays=int(h.size), floorPairsOver1_5=drops, maxFloorStep=round(worst, 3))


def lua(v):
    from tools.roadvis import ground_export
    return ground_export.lua(v)


def export(res_id, seq, G, st, area, out_dir, raised_before=(), neighbours=(), write=True):
    """build/roadcity/<id>/roblox_ground/manifest.luau for PattayaRoadGroundBuilder city mode"""
    probes = calibration_columns(G)
    pairs = edge_pairs(st, area)
    exp = grid_expected(st, area)
    pi0, pk0, pi1, pk1 = G['plateau_vox']
    man = dict(
        name=f'roadground_{res_id}', attribution='Map data (c) OpenStreetMap contributors, ODbL 1.0',
        note='generated by tools/roadvis/city_ground.py (ground at road level, city batch); OFFLINE data; the terrain write '
             'needs the owner\'s go-ahead and a fresh place backup',
        origin=[20000, 0, 0], batch=dict(id=res_id, seq=seq, box=[float(v) for v in G['box_world']],
                                         plateauVox=[pi0, pk0, pi1, pk1], raisedBefore=list(raised_before), neighbours=list(neighbours)),
        top=TOP, occTop=OCC, levels=LEVELS, alphabet=ALPHA, ramp=RAMP, flat=FLAT, window=list(WINDOW), terrainTop=ground.TERRAIN_TOP,
        layer=[-4, 0], region=dict(i0=G['i0'], k0=G['k0'], ni=G['ni'], nk=G['nk']),
        snapshot=dict(y0=-2, y1=0),
        materials=['Ground', 'Pavement'], columns=encode_rows(G),
        calibrate=dict(probes=[v for p in probes for v in p], flat=0.03),
        edgeChecks=[export_r(v, 3) if k == 4 else export_r(v) for p in pairs for k, v in enumerate(p)],
        counts=dict(G['counts'], edgeChecks=len(pairs), probes=len(probes)),
        probe=dict(grid=2.0, expected=exp, edgeStepMax=export_r(max(p[4] for p in pairs), 3) if pairs else None,
                   edgeStepMin=export_r(min(p[4] for p in pairs), 3) if pairs else None),
    )
    hdr = ('-- generated by tools/roadvis/city_ground.py (ground at road level, city batch ' + res_id + ', OFFLINE data; '
           'Map data (c) OpenStreetMap contributors, ODbL 1.0); do not edit\n')
    text = hdr + 'return ' + lua(man) + '\n'
    if write:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, 'manifest.luau'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    import hashlib
    return dict(sha1=hashlib.sha1(text.encode('utf-8')).hexdigest(), KB=round(len(text) / 1024, 1), counts=man['counts'],
                expected=exp, edgeStepMax=man['probe']['edgeStepMax'], edgeChecks=len(pairs), probes=len(probes))


def export_r(v, n=2):
    return round(float(v), n)


def export_noraise(nr, out_path, write=True):
    """ServerStorage.PattayaDataRoadGroundNoRaise: never-raise voxel columns as runs {i, k0, k1} (world voxel indices),
    plus the frame (columns outside it are never raised) and the landmark / island boxes for the report"""
    runs = nr.runs()
    man = dict(
        name='roadground_noraise', attribution='Map data (c) OpenStreetMap contributors, ODbL 1.0',
        note='generated by tools/roadvis/city_ground.py: sea, beach sand, coast cells, landmarks with parts a raise would '
             'bury, the coast islands; columns outside the frame are never raised either',
        frame=dict(i0=nr.i0, k0=nr.k0, i1=nr.i0 + nr.nx - 1, k1=nr.k0 + nr.nz - 1),
        runs=[v for r_ in runs for v in r_],
        landmarks=[dict(id=l['id'], box=[v + (city.ORIGIN[0] if j % 2 == 0 else 0) for j, v in enumerate(l['box_local'])],
                        lowParts=l['low_parts']) for l in nr.landmarks],
        islands=[dict(name=i['name'], box=[v + (city.ORIGIN[0] if j % 2 == 0 else 0) for j, v in enumerate(i['box_local'])]) for i in nr.islands],
        counts=dict(runs=len(runs), columns=int(nr.m.sum()), water=int((nr.kind == 1).sum()), sand=int((nr.kind == 2).sum()),
                    landmark=int((nr.kind == 3).sum()), island=int((nr.kind == 4).sum())),
    )
    hdr = '-- generated by tools/roadvis/city_ground.py (never-raise zones of the city ground, OFFLINE data); do not edit\n'
    text = hdr + 'return ' + lua(man) + '\n'
    if write:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    return dict(runs=len(runs), KB=round(len(text) / 1024, 1), counts=man['counts'])
