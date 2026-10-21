"""Ground at road level: the pilot ground raise at the Road B junction and its static QA (team20/road-ground). OFFLINE.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py ground [--art]   (build/roadground/*, docs numbers)

Why (owner, 2026-10-22): road edges drop 3 studs to the terrain (y -2), the strip between the road and the buildings is
a 3-stud trench, and a car that drops in cannot climb out (the chassis box clears 1.58 studs; a 3-stud wall stops it).

Design (docs/ROAD_GROUND_PILOT.md): Road B as designed (tools/roadvis/junction.py, unchanged) PLUS the terrain of the
Road B box raised from y -2 to y +0.43: one voxel layer (y -4 .. 0, 4-stud voxels) gets a partial occupancy, so the
ground sits 0.57 under the road top everywhere in the box (every road-to-ground edge <= 0.6, drivable back up). A
4-stud flat collar and a 28-stud ramp outside the box bring it back to -2 (no new cliff). Pavement near buildings and
along every paved edge, Ground in open lots. Zero new instances for the ground; the visible edges are thin
non-colliding kerb bands along the road edges that now face the ground.

Height model (NOT measured in Studio): PattayaBuilder measured that a voxel slab filled up to the grid line Y renders at
Y + 2 (filled to -4 -> surface -2, the leader's probe: -2.00 everywhere). Assumed linear in between: surface =
-2 + 4 * occupancy of the layer -4 .. 0, so +0.43 needs occupancy 0.6075. The Studio builder measures the surface after
the write and corrects the occupancy (PattayaRoadGroundBuilder.Build calibrate), so the model only sets the start value.
Offline, the terrain surface is the bilinear interpolation of the column occupancies between column centres (a smooth
terrain approximation; exact on the flat plateau).

Map-local coordinates (world = local + (20000, 0, 0)) everywhere except where a name says world. Read only on build/.
"""
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from tools.roadvis import junction, shoulder_proof, world

VOX = 4.0
TERRAIN_TOP = -2.0                 # today's terrain surface (Ground full up to y -4)
LAYER = (-4.0, 0.0)                # the voxel layer that gets the partial occupancy
ROAD_TOP = 1.0
CHASSIS_CLEAR = 1.58               # RaceCarServer chassis 7 x 1.6 x 15, centre at the mounts, 0.88 + 1.5 above the ground
DROP = 1.5                         # a step of 1.5 studs or more counts as a drop (down) or a wall the car cannot climb (up)
WHEELS = shoulder_proof.WHEELS     # RaceCarServer mounts (lateral right, longitudinal forward)
MAT_CODES = {0: 'Air', 1: 'Ground', 2: 'Pavement'}
SHOULDER_INSTALLED = ('s10_26', 's9_1', 's10_25', 's8_2', 's8_1', 's9_25', 's8_2_2', 's8_1_2')   # in the place (leader)

GCFG = dict(
    name='sukhumvit_klang_ground',
    plateau_world=(24220.0, 648.0, 24820.0, 1252.0),   # the Road B box (z 650 / 1250 snapped outward to the voxel grid)
    top=0.43,                     # ground surface in the box: 0.57 under the road top (target step <= 0.6)
    window=(0.40, 0.46),          # accepted measured surface: step 0.54 .. 0.60, >= 0.52 under the lowest road top (0.98)
    flat=4.0,                     # columns whose centre lies this close outside the box keep the full height
    ramp=28.0,                    # then the occupancy falls linearly to 0 over 28 studs (2.43 / 28 = 8.7 % slope)
    pave_bld=20.0,                # Pavement within 20 studs of a building (frontage forecourt) ...
    pave_edge=10.0,               # ... or 10 studs of a paved edge (verge); Ground elsewhere (open lots) and on the ramp
    pavement_color=(150, 148, 142),   # Terrain:SetMaterialColor(Pavement): the Road B / apron concrete family
    kerb_w=0.8, kerb_top=1.03, kerb_bottom=0.39, kerb_out=0.02, kerb_seg=12.0, kerb_min=0.3, kerb_tol=0.08,
    kerb_color=(205, 203, 196),   # the Road B kerb colour
)


def occ_for(top):
    """layer occupancy that puts the surface at `top` (the linear model, see the module doc)"""
    return (top - TERRAIN_TOP) / VOX


def surface_for(occ):
    return TERRAIN_TOP + VOX * occ


# ---- the column plan -------------------------------------------------------------------------------------------------
def plan(W, P=None, cfg=None):
    """the voxel columns the builder writes (layer y -4 .. 0): world voxel index box, occupancy and material per column.
    Materials need the state's surfaces and buildings (P = the Road B pilot; None = today's surfaces)."""
    cfg = dict(GCFG, **(cfg or {}))
    x0, z0, x1, z1 = cfg['plateau_world']
    if any(abs(v / VOX - round(v / VOX)) > 1e-9 for v in (x0, z0, x1, z1)):
        raise ValueError('plateau must lie on the 4-stud voxel grid')
    pad = int(math.ceil((cfg['flat'] + cfg['ramp']) / VOX))
    i0, i1 = int(round(x0 / VOX)) - pad, int(round(x1 / VOX)) + pad          # columns i0 .. i1 - 1 (world x = 4 i)
    k0, k1 = int(round(z0 / VOX)) - pad, int(round(z1 / VOX)) + pad
    ii, kk = np.meshgrid(np.arange(i0, i1), np.arange(k0, k1), indexing='ij')
    cx, cz = ii * VOX + VOX / 2, kk * VOX + VOX / 2                         # column centres (world)
    d = column_distance(cx, cz, cfg)
    o_top = occ_for(cfg['top'])
    occ = o_top * ramp_factor(d, cfg)
    plateau = d <= 0.0
    mat = np.zeros(occ.shape, np.uint8)
    mat[occ > 0] = 1
    st = State(W, P)
    loc = np.stack([cx.ravel() - world.ORIGIN[0], cz.ravel()], axis=1)
    paved = st.paved_union()
    blds = st.bld_union
    dp = shapely.distance(paved, shapely.points(loc)) if not paved.is_empty else np.full(len(loc), 1e9)
    db = shapely.distance(blds, shapely.points(loc)) if not blds.is_empty else np.full(len(loc), 1e9)
    pave = ((db <= cfg['pave_bld']) | (dp <= cfg['pave_edge'])).reshape(occ.shape) & plateau
    mat[pave] = 2
    return dict(cfg=cfg, i0=i0, k0=k0, ni=i1 - i0, nk=k1 - k0, occ=occ, mat=mat, plateau=plateau, dist=d,
                o_top=o_top, counts=dict(columns=int(occ.size), written=int((occ > 0).sum()), plateau=int(plateau.sum()),
                                         ramp=int(((occ > 0) & ~plateau).sum()), pavement=int((mat == 2).sum()),
                                         ground=int((mat == 1).sum()),
                                         pavement_studs2=float((mat == 2).sum() * VOX * VOX),
                                         ground_studs2=float(((mat == 1) & plateau).sum() * VOX * VOX)))


def column_distance(cx, cz, cfg):
    """distance (studs) of a column centre (world) from the plateau rectangle, 0 inside"""
    x0, z0, x1, z1 = cfg['plateau_world']
    dx = np.maximum(np.maximum(x0 - cx, cx - x1), 0.0)
    dz = np.maximum(np.maximum(z0 - cz, cz - z1), 0.0)
    return np.hypot(dx, dz)


def ramp_factor(d, cfg):
    """1 in the plateau and the flat collar, then linear to 0 over `ramp` studs (the Luau builder uses the same formula)"""
    f = 1.0 - (d - cfg['flat']) / cfg['ramp']
    return np.where(d <= cfg['flat'], 1.0, np.clip(f, 0.0, 1.0))


class GroundField:
    """terrain surface height (local x / z): -2 + 4 * occupancy, bilinear between column centres; -2 without a plan"""

    def __init__(self, G=None, occ_scale=1.0):
        self.G = G
        if G is not None:
            o = G['occ'] * occ_scale
            self.o = np.pad(o, 1)                          # zero ring: the terrain outside the written box is today's
            self.ox = (G['i0'] - 1) * VOX + VOX / 2 - world.ORIGIN[0]
            self.oz = (G['k0'] - 1) * VOX + VOX / 2

    def at(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        if self.G is None:
            return np.full(len(xy), TERRAIN_TOP)
        u = (xy[:, 0] - self.ox) / VOX
        v = (xy[:, 1] - self.oz) / VOX
        n0, n1 = self.o.shape
        iu = np.floor(u).astype(int)
        iv = np.floor(v).astype(int)
        fu, fv = u - iu, v - iv
        ok = (iu >= 0) & (iv >= 0) & (iu < n0 - 1) & (iv < n1 - 1)
        o = np.zeros(len(xy))
        a, b = iu[ok], iv[ok]
        g = self.o
        o[ok] = (g[a, b] * (1 - fu[ok]) * (1 - fv[ok]) + g[a + 1, b] * fu[ok] * (1 - fv[ok])
                 + g[a, b + 1] * (1 - fu[ok]) * fv[ok] + g[a + 1, b + 1] * fu[ok] * fv[ok])
        return TERRAIN_TOP + VOX * o


class State:
    """collision tops of one state (today: P None; Road B: P; with or without the raised ground G): every colliding
    surface (its top), the terrain surface below everything, buildings (walls, 99)"""

    def __init__(self, W, P=None, G=None, occ_scale=1.0, shoulders=SHOULDER_INSTALLED):
        groups = shoulder_proof.state_groups(W, P)
        if shoulders is not None:                   # only the shoulder chunks built in the place
            rep = {id(s) for s in P['replaced']} if P is not None else set()
            groups = {}
            for s in W['surf']:
                if id(s) in rep or (s['kind'] in world.SHOULDER_KINDS and s.get('module') not in shoulders):
                    continue
                groups.setdefault(round(float(s['top']), 3), []).append(s['poly'])
            if P is not None:
                c = P['cfg']
                groups.setdefault(c['asphalt_top'], []).extend(P['tris'] + list(P.get('support_tris') or []))
                groups.setdefault(c['sidewalk_top'], []).extend(P['walk_tris'])
                groups.setdefault(c['island_top'], []).extend(P['isl_tris'])
        blds = [b['poly'] for b in W['blds']]
        self.groups = {k: v for k, v in groups.items() if k < 50}
        self.H = shoulder_proof.Heights(self.groups)
        self.bld_union = unary_union(blds) if blds else Polygon()
        shapely.prepare(self.bld_union)
        self.ground = GroundField(G, occ_scale)
        self.P, self.G = P, G

    def surf(self, xy):
        """highest colliding surface top, -2 where none (no surface has a top at -2)"""
        return self.H.at(xy)

    def is_bld(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        return shapely.contains_xy(self.bld_union, xy[:, 0], xy[:, 1])

    def at(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        h = np.maximum(self.surf(xy), self.ground.at(xy))
        h[self.is_bld(xy)] = 99.0
        return h

    def paved_union(self):
        if not hasattr(self, '_paved'):
            self._paved = unary_union([g for _, g in self.H.groups])
        return self._paved


# ---- edges, trench and grid (one area) -------------------------------------------------------------------------------
def classify_top(h):
    if h >= 1.55:
        return 'sidewalk'           # sidewalk 1.6, corner fill 1.58, kerb 1.61
    if h >= 1.3:
        return 'island'             # Road B island 1.45
    if h >= 0.95:
        return 'road'               # asphalt 1.0, discs 0.99, shoulder 0.985, apron 0.98, support 1.0
    return 'other'


def edge_samples(st, area, step=1.0, pad=0.25, road_only=False):
    """every boundary of the colliding surfaces inside `area` (road_only: of the road-height surfaces only), every
    `step` studs: point, outward normal, top inside, what lies 0.25 outside (building / slot = a surface within 1 stud
    / ground), the step down to it. Hairline gaps between pieces (< 0.1 stud) are closed first."""
    if road_only:
        U = unary_union([g for top, g in st.H.groups if 0.95 <= top <= 1.01])
    else:
        U = st.paved_union()
    U = U.intersection(area.buffer(5.0)).buffer(0.05, join_style='mitre').buffer(-0.05, join_style='mitre')
    rings = []
    for p in junction.polys(U):
        rings += [p.exterior] + list(p.interiors)
    pts, nrm = [], []
    for ring in rings:
        L = LineString(ring.coords)
        n = max(int(L.length / step), 1)
        s = (np.arange(n) + 0.5) * L.length / n
        a = shapely.line_interpolate_point(L, s)
        b = shapely.line_interpolate_point(L, np.minimum(s + 0.05, L.length))
        pa, pb = shapely.get_coordinates(a), shapely.get_coordinates(b)
        t = pb - pa
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        pts.append(pa)
        nrm.append(np.stack([-t[:, 1], t[:, 0]], axis=1))
    if not pts:
        return dict(n=0)
    p = np.vstack(pts)
    nm = np.vstack(nrm)
    keep = shapely.contains_xy(area, p[:, 0], p[:, 1])
    p, nm = p[keep], nm[keep]
    a_in = shapely.contains_xy(U, p[:, 0] + nm[:, 0] * pad, p[:, 1] + nm[:, 1] * pad)
    out = np.where(a_in[:, None], -nm, nm)                   # outward normal
    q_out = p + out * pad
    q_in = p - out * pad
    h_in = st.surf(q_in)
    bld = st.is_bld(q_out)
    s_out = st.surf(q_out)                                     # road_only: a sidewalk / island 0.25 outside = a kerb up
    near = np.max(np.stack([st.surf(p + out * d) for d in (0.6, 1.0)]), axis=0)
    kerb = ~bld & (s_out > h_in + 0.3)
    slot = ~bld & ~kerb & (near > -1.9)                        # another surface within 1 stud: a slot, not an edge
    h_out = np.where(kerb, s_out, st.ground.at(q_out))
    return dict(n=len(p), p=p, out=out, h_in=h_in, h_out=h_out, bld=bld, slot=slot, kerb=kerb, step=h_in - h_out, seg=step)


def edge_report(E, st=None, rays=False, ray_len=60.0):
    """lengths per class of every surface edge sample (see edge_samples); road-to-ground steps; drops >= 1.5;
    optional trench rays: from every edge that faces the ground, the distance to the first building face / other
    surface along the outward normal (60 studs)"""
    if not E.get('n'):
        return dict(samples=0)
    seg = E['seg']
    face = ~E['bld'] & ~E['slot'] & ~E['kerb']
    kinds = np.array([classify_top(h) for h in E['h_in']])
    res = dict(samples=int(E['n']), length=round(float(E['n'] * seg), 1),
               building_face=round(float(E['bld'].sum() * seg), 1), slot=round(float(E['slot'].sum() * seg), 1),
               kerb_up=round(float(E['kerb'].sum() * seg), 1), facing_ground=round(float(face.sum() * seg), 1),
               share_facing_ground=round(float(face.sum()) / max(int(E['n']), 1), 3),
               share_kerb_up=round(float(E['kerb'].sum()) / max(int(E['n']), 1), 3))
    by = {}
    for k in ('road', 'island', 'sidewalk', 'other'):
        m = face & (kinds == k)
        if not m.any():
            continue
        st_ = E['step'][m]
        by[k] = dict(length=round(float(m.sum() * seg), 1), step_min=round(float(st_.min()), 3),
                     step_max=round(float(st_.max()), 3), drop_ge_1_5=round(float((st_ >= DROP).sum() * seg), 1),
                     le_0_6=round(float((st_ <= 0.6 + 1e-9).sum() * seg), 1))
    res['by_top'] = by
    res['drop_ge_1_5'] = round(float((face & (E['step'] >= DROP)).sum() * seg), 1)
    res['share_drop_ge_1_5'] = round(float((face & (E['step'] >= DROP)).sum()) / max(int(E['n']), 1), 3)
    rmask = face & (kinds == 'road')
    res['road_to_ground_max_step'] = round(float(E['step'][rmask].max()), 3) if rmask.any() else None
    res['road_to_ground_le_0_6'] = bool(rmask.any() and E['step'][rmask].max() <= 0.6 + 1e-9)
    if rays and st is not None:
        res['trench'] = trench_rays(st, E, face, ray_len)
    return res


def trench_rays(st, E, face, ray_len=60.0, bins=(8, 16, 24, 40, 60)):
    """for every edge sample that faces the ground: what the outward ray meets first within ray_len studs"""
    idx = np.nonzero(face)[0]
    other = st.paved_union()
    hit_b, hit_s = [], []
    for i in idx:
        p, o = E['p'][i], E['out'][i]
        ray = LineString([tuple(p + o * 0.3), tuple(p + o * ray_len)])
        db = _first(ray, st.bld_union, p)
        ds = _first(ray, other, p)
        hit_b.append(db)
        hit_s.append(ds)
    hit_b, hit_s = np.array(hit_b), np.array(hit_s)
    seg = E['seg']
    out = dict(rays=int(len(idx)))
    b_first = hit_b < hit_s
    lo = 0
    for hi in bins:
        m = b_first & (hit_b > lo) & (hit_b <= hi)
        out[f'building_{lo}_{hi}'] = int(m.sum())
        lo = hi
    out['surface_first'] = int((~b_first & np.isfinite(hit_s)).sum())
    out['open'] = int((~np.isfinite(hit_b) & ~np.isfinite(hit_s)).sum())
    near = b_first & (hit_b <= 40)
    out['trench_area_to_buildings_le_40'] = round(float(hit_b[near].sum() * seg), 0)    # ray-swept studs^2
    out['building_widths'] = [round(float(v), 1) for v in np.sort(hit_b[b_first & np.isfinite(hit_b)])]
    return out


def _first(ray, geom, p):
    if geom.is_empty or not ray.intersects(geom):
        return math.inf
    g = ray.intersection(geom)
    c = shapely.get_coordinates(g)
    if not len(c):
        return math.inf
    return float(np.min(np.hypot(c[:, 0] - p[0], c[:, 1] - p[1])))


def worst_grid(st, area, res=1.0):
    """height raster of `area` (cell centres every `res` studs) and, per cell, the largest step to a neighbour (right,
    down, both diagonals) where neither cell is a building"""
    x0, z0, x1, z1 = area.bounds
    xs = np.arange(x0 + res / 2, x1, res)
    zs = np.arange(z0 + res / 2, z1, res)
    X, Z = np.meshgrid(xs, zs, indexing='ij')
    xy = np.stack([X.ravel(), Z.ravel()], axis=1)
    h = st.at(xy).reshape(X.shape)
    inside = shapely.contains_xy(area, X.ravel(), Z.ravel()).reshape(X.shape)
    bld = h > 50
    worst = np.zeros(X.shape)
    n0, n1 = h.shape
    for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
        ra, rb = slice(0, n0 - di), slice(di, n0)
        ca, cb = (slice(0, n1 - dj), slice(dj, n1)) if dj >= 0 else (slice(-dj, n1), slice(0, n1 + dj))
        a, b = h[ra, ca], h[rb, cb]
        d = np.where((a < 50) & (b < 50), np.abs(a - b), 0.0)
        worst[ra, ca] = np.maximum(worst[ra, ca], d)          # both cells of the pair carry the step
        worst[rb, cb] = np.maximum(worst[rb, cb], d)
    worst[~inside | bld] = 0.0
    return dict(X=X, Z=Z, xy=xy, h=h, inside=inside, bld=bld, worst=worst)


def grid_steps(st, area, res=1.0):
    """every neighbour pair in `area` that steps 1.5 or more is a drop (buildings are walls, not drops)"""
    g = worst_grid(st, area, res)
    X, Z, h, inside, bld, worst = g['X'], g['Z'], g['h'], g['inside'], g['bld'], g['worst']
    m = worst >= DROP
    drops = [[round(float(X[i, j]) + world.ORIGIN[0], 1), round(float(Z[i, j]), 1), round(float(worst[i, j]), 2)]
             for i, j in list(zip(*np.nonzero(m)))[:50]]
    ok = inside & ~bld
    hist = dict(flat=int(((worst <= 0.05) & ok).sum()), le_0_6=int(((worst > 0.05) & (worst <= 0.6 + 1e-9) & ok).sum()),
                le_1_2=int(((worst > 0.6 + 1e-9) & (worst <= 1.2) & ok).sum()),
                lt_1_5=int(((worst > 1.2) & (worst < DROP) & ok).sum()), ge_1_5=int((m & inside).sum()))
    ground_cells = int(((np.abs(h - st.ground.at(g['xy']).reshape(X.shape)) < 1e-6) & ok).sum())
    return dict(cells=int(ok.sum()), res=res, max_step=round(float(worst.max()), 3), drop_cells=int(m.sum()),
                hist=hist, drops=drops, ground_cells=ground_cells)


# ---- car runs (static model) -----------------------------------------------------------------------------------------
def wheels_at(C, T):
    R = np.stack([-T[:, 1], T[:, 0]], axis=1)                 # right of travel (x east, z south)
    return np.stack([C + R * la + T * lo for la, lo in WHEELS], axis=1)       # (n, 4, 2)


def run_metrics(st, C, T):
    """the 4 wheel contacts every sample of a car path: collision tops; steps between consecutive samples (per wheel,
    1 stud apart); the spread between wheels; static up; wheels on the ground (no surface under them)"""
    P4 = wheels_at(C, T)
    hs = np.stack([st.at(P4[:, w]) for w in range(4)], axis=1)
    sf = np.stack([st.surf(P4[:, w]) for w in range(4)], axis=1)
    blocked = (hs > 50).any(axis=1)
    hh = np.where(hs > 50, np.nan, hs)
    dh = np.diff(hh, axis=0)
    down = np.nan_to_num(-dh, nan=0.0)
    up_ = np.nan_to_num(dh, nan=0.0)
    some = ~np.isnan(hh).all(axis=1)                         # a sample with all 4 wheels in a building has no spread
    spread = np.zeros(len(hh))
    spread[some] = np.nanmax(hh[some], axis=1) - np.nanmin(hh[some], axis=1)
    hc = np.clip(np.nan_to_num(hh, nan=2.0), -2.0, 2.0)
    gx = ((hc[:, 1] + hc[:, 3]) - (hc[:, 0] + hc[:, 2])) / 2 / 6.8
    gz = ((hc[:, 2] + hc[:, 3]) - (hc[:, 0] + hc[:, 1])) / 2 / 10.4
    upv = 1 / np.sqrt(1 + gx ** 2 + gz ** 2)
    on_ground = (sf <= TERRAIN_TOP + 1e-9) & ~(hs > 50)
    return dict(samples=int(len(C)), wheel_on_ground=int(on_ground.sum()), on_terrain_m2=int(((hs <= TERRAIN_TOP + 1e-6)).sum()),
                max_step_down=round(float(down.max()) if len(down) else 0.0, 3), max_step_up=round(float(up_.max()) if len(up_) else 0.0, 3),
                drops=int((down >= DROP).sum()), climbs=int((up_ >= DROP).sum()), hang=int((spread >= DROP).sum()),
                max_spread=round(float(spread.max()), 3), min_up=round(float(upv.min()), 3), blocked=int(blocked.sum()),
                _hs=hs, _P4=P4)


def path_frame(pts, step=1.0, trim=6):
    Q = world.rc.probes_of(np.asarray(pts, float), step)
    if trim:
        Q = Q[trim:-trim]
    T = np.gradient(Q, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    return Q, T


def spot2_runs(st):
    """the Studio shoulder harness geometry (flip spot 2, path B, both directions, TestKit lateral +-24 / +-20 / +-14 to
    the right of travel; 100 / 150 / 200 studs/s give identical static rows): one row per run"""
    path = np.array([(x - world.ORIGIN[0], z) for x, z in shoulder_proof.PATH_B])
    rows = []
    for direction in ('fwd', 'rev'):
        Q, T = path_frame(path if direction == 'fwd' else path[::-1])
        R = np.stack([-T[:, 1], T[:, 0]], axis=1)
        for lat in shoulder_proof.LATERALS:
            m = run_metrics(st, Q + R * lat, T)
            for v in shoulder_proof.SPEEDS:
                rows.append(dict(dir=direction, lateral=lat, speed=v, **{k: val for k, val in m.items() if not k.startswith('_')}))
    return rows


def excursion(Q, T, s, start, lat, out_len=30.0, hold=40.0, back_len=30.0):
    """car centre path that leaves the base path at arc `start`, moves `lat` studs to the side (+ = right of travel;
    a number, or an array over s) over out_len, holds for `hold`, comes back over back_len; heading = dC/ds"""
    e = start + out_len + hold + back_len
    m = (s >= start - 10) & (s <= e + 10)
    if m.sum() < 10:
        return None
    ss = s[m]
    f = np.zeros(len(ss))
    a = (ss - start) / out_len
    f = np.where((ss >= start) & (ss < start + out_len), 3 * np.clip(a, 0, 1) ** 2 - 2 * np.clip(a, 0, 1) ** 3, f)
    f = np.where((ss >= start + out_len) & (ss <= start + out_len + hold), 1.0, f)
    b = (e - ss) / back_len
    f = np.where((ss > start + out_len + hold) & (ss <= e), 3 * np.clip(b, 0, 1) ** 2 - 2 * np.clip(b, 0, 1) ** 3, f)
    R = np.stack([-T[m][:, 1], T[m][:, 0]], axis=1)
    lv = np.asarray(lat, float)[m] if np.ndim(lat) else float(lat)
    C = Q[m] + R * (lv * f)[:, None]
    Tc = np.gradient(C, axis=0)
    Tc /= np.maximum(np.linalg.norm(Tc, axis=1, keepdims=True), 1e-9)
    return C, Tc, f


OFFROAD_SETS = (('harness', (24, -24, 20, -20)), ('deep', ('+edge8', '-edge8')))


def offroad_runs(st, P, sets=OFFROAD_SETS, spacing=60.0, min_len=140.0, inset=50.0):
    """leave the road into the frontage, then turn back: excursions from the centreline of every carriageway chain of
    the pilot (both directions of a two-way chain, wheels inside the area minus `inset`), one every `spacing` studs.
    'harness': lateral +-20 / +-24 = the TestKit lateral of the Studio harness, from the carriageway centreline (on
    Sukhumvit the car is then partly or fully past the carriageway edge); 'deep': the car centre 8 studs past the
    carriageway edge (the inner wheels 4.6 studs past it), both sides, on every chain"""
    area = P['area']
    inner = area.buffer(-inset)
    rows = []
    for c in P['chains']:
        poly, Q, T, hw, s = P['rib'][c['id']]
        m = shapely.contains_xy(inner, Q[:, 0], Q[:, 1])
        if m.sum() * 2.0 < min_len:
            continue
        for direction in ('fwd',) if c['oneway'] else ('fwd', 'rev'):
            Qd, Td, sd, hd = (Q, T, s, hw) if direction == 'fwd' else (Q[::-1], -T[::-1], s[-1] - s[::-1], hw[::-1])
            md = m if direction == 'fwd' else m[::-1]
            idx = np.nonzero(md)[0]
            s_lo, s_hi = sd[idx[0]], sd[idx[-1]]
            for set_name, lats in sets:
                for lat in lats:
                    lv = (hd + 8.0) * (1 if lat.startswith('+') else -1) if isinstance(lat, str) else lat
                    start = s_lo
                    while start + 100.0 <= s_hi:
                        ex = excursion(Qd, Td, sd, start, lv)
                        if ex is not None:
                            C, Tc, f = ex
                            r = run_metrics(st, C, Tc)
                            k = int(np.argmax(f))
                            rows.append(dict(set=set_name, chain=c['id'], name=c['name'], cls=c['cls'], dir=direction,
                                             lateral=lat, start=round(float(start), 1),
                                             world=[round(float(C[k][0]) + world.ORIGIN[0], 1), round(float(C[k][1]), 1)],
                                             **{kk: v for kk, v in r.items() if not kk.startswith('_')}))
                        start += spacing
    return rows


def ramp_band(states, plateau, width=40.0, res=1.0):
    """the band just outside the plateau (flat collar + ramp + 8): no new cliff. Per cell, the largest neighbour step
    with B + ground against B alone (same surfaces): the raise may only lower a step, apart from the ramp's own slope"""
    band = plateau.buffer(width, join_style='mitre').difference(plateau)
    out = {name: grid_steps(states[name], band, res=res) for name in ('today', 'B', 'B_ground')}
    gb, gg = worst_grid(states['B'], band, res), worst_grid(states['B_ground'], band, res)
    ok = gb['inside'] & ~gb['bld'] & ~gg['bld']
    inc = np.where(ok, gg['worst'] - gb['worst'], 0.0)
    new_drop = ok & (gg['worst'] >= DROP) & (gb['worst'] < DROP)
    out['max_step_increase'] = round(float(inc.max()), 4)
    out['cells_step_increased_over_0_1'] = int((inc > 0.1).sum())
    out['new_drop_cells'] = int(new_drop.sum())
    out['cells_step_lowered'] = int((inc < -0.05).sum())
    xy = gg['xy']
    g = states['B_ground'].ground.at(xy)
    slope = np.maximum(np.abs(states['B_ground'].ground.at(xy + [res, 0]) - g), np.abs(states['B_ground'].ground.at(xy + [0, res]) - g)) / res
    inside = gg['inside'].ravel()
    out['terrain_max_slope'] = round(float(slope[inside].max()), 4)
    out['terrain_min_in_band'] = round(float(g[inside].min()), 3)
    out['terrain_max_in_band'] = round(float(g[inside].max()), 3)
    return out


def visible_materials(G, st):
    """terrain that shows (no colliding surface, no building over it) inside the plateau, per material (studs^2)"""
    cfg = G['cfg']
    res = 1.0
    x0, z0, x1, z1 = cfg['plateau_world']
    xs = np.arange(x0 + res / 2, x1, res) - world.ORIGIN[0]
    zs = np.arange(z0 + res / 2, z1, res)
    X, Z = np.meshgrid(xs, zs, indexing='ij')
    xy = np.stack([X.ravel(), Z.ravel()], axis=1)
    free = (st.surf(xy) <= TERRAIN_TOP + 1e-9) & ~st.is_bld(xy)
    i = np.floor((xy[:, 0] + world.ORIGIN[0]) / VOX).astype(int) - G['i0']
    k = np.floor(xy[:, 1] / VOX).astype(int) - G['k0']
    mat = G['mat'][i, k]
    return dict(visible_ground_studs2=int(free.sum()), pavement=int((free & (mat == 2)).sum()), ground=int((free & (mat == 1)).sum()),
                plateau_studs2=int(len(xy)))


def summarize_runs(rows):
    if not rows:
        return dict(runs=0)
    return dict(runs=len(rows), with_drop=sum(1 for r in rows if r['drops'] or r['hang']),
                with_climb=sum(1 for r in rows if r['climbs']), drops=sum(r['drops'] for r in rows),
                climbs=sum(r['climbs'] for r in rows), hang=sum(r['hang'] for r in rows),
                wheel_on_ground=sum(r['wheel_on_ground'] for r in rows),
                max_step_down=max(r['max_step_down'] for r in rows), max_step_up=max(r['max_step_up'] for r in rows),
                min_up=min(r['min_up'] for r in rows), blocked_runs=sum(1 for r in rows if r['blocked']))


def lane_wheels(st, P, inset=20.0, seam=False):
    """the Road B lane check (junction.wheel_check: every lane centre of every carriageway every 2 studs, the 4 wheels)
    on a state: holes = a wheel with no road-height surface under it (below 0.9); drops = a wheel 1.5 or more below
    the lane top (1.0)"""
    cfg = P['cfg']
    area = P['area']
    inner = area.buffer(-inset)
    out = dict(samples=0, holes=0, drops=0, min_wheel=99.0)
    for c in P['chains']:
        poly, Q, T, hw, s = P['rib'][c['id']]
        nl = max(min(c['lanes']), 1)
        reach = max(abs(lo) for _, lo in junction.CFG['wheels']) + 1.0
        mm = shapely.contains_xy(inner, Q[:, 0], Q[:, 1]) & (s >= reach) & (s <= s[-1] - reach)
        if seam:
            mm &= ~shapely.contains_xy(area.buffer(-(cfg['seam_band'] + 10)), Q[:, 0], Q[:, 1])
        else:
            mm &= shapely.contains_xy(area.buffer(-(cfg['seam_band'] + 10)), Q[:, 0], Q[:, 1])
        if not mm.any():
            continue
        Qm, Tm, hm = Q[mm], T[mm], hw[mm]
        N = np.stack([-Tm[:, 1], Tm[:, 0]], axis=1)
        for li in range(nl):
            o = -hm + (li + 0.5) * 2 * hm / nl
            C = Qm + N * o[:, None]
            hs = np.stack([st.at(C + N * la + Tm * lo) for la, lo in junction.CFG['wheels']], axis=1)
            out['samples'] += int(len(C))
            out['holes'] += int((hs < 0.9).any(axis=1).sum())
            out['drops'] += int((hs <= ROAD_TOP - DROP).any(axis=1).sum())
            out['min_wheel'] = min(out['min_wheel'], float(hs.min()))
    out['min_wheel'] = round(out['min_wheel'], 3)
    return out


# ---- what the raise does to objects in the pilot -----------------------------------------------------------------------
def buried(items, field, st=None):
    """items [dict(kind, x, z, base, top)] (local) -> per item: the ground height under it, how much of it the ground
    buries, what stays visible, and the gap under its foot (to the highest surface or the ground: `st` gives the
    surfaces; a foot inside a sidewalk or road part has no gap)"""
    out = []
    for it in items:
        xy = [[it['x'], it['z']]]
        g = float(field.at(xy)[0])
        sup = g
        on = 'ground'
        if st is not None:
            s = float(st.surf(xy)[0])
            if s > sup:
                sup, on = s, ('road' if s < 1.3 else 'sidewalk')
        b = max(0.0, g - it['base'])
        out.append(dict(it, ground=round(g, 3), stands_on=on, buried=round(b, 3),
                        visible=round(max(0.0, it['top'] - max(g, it['base'])), 2), float_gap=round(max(0.0, it['base'] - sup), 3)))
    return out


# ---- the visible edges: kerb bands where a road-height edge now faces the raised ground --------------------------------
def kerb_bands(W, P, G, cfg=None, st=None):
    """non-colliding kerb bands along every road-height edge (Road B asphalt, kept old road, shoulder strips) inside the
    plateau that faces the raised ground (not a sidewalk / island / building / slot): straight pieces <= kerb_seg
    studs, kerb_w wide, their outer face kerb_out outside the edge, top kerb_top (just above the road), bottom under
    the ground. Returns [dict(a, b, w, kind)] (local) and the edge length covered."""
    cfg = dict(GCFG, **(cfg or {}))
    st = st or State(W, P, G)
    x0, z0, x1, z1 = cfg['plateau_world']
    plateau = box(x0 - world.ORIGIN[0], z0, x1 - world.ORIGIN[0], z1)
    road_groups = [g for top, g in st.H.groups if 0.95 <= top <= 1.01]
    R = unary_union(road_groups).intersection(plateau.buffer(2))
    high = [g for top, g in st.H.groups if top > 1.01]
    Hh = unary_union(high) if high else Polygon()
    shapely.prepare(Hh)
    segs = []
    covered = 0.0
    for poly in junction.polys(R):
        for ring in [poly.exterior] + list(poly.interiors):
            c = np.asarray(LineString(ring.coords).simplify(0.02).coords)
            for a, b in chords(c, cfg['kerb_seg'], cfg['kerb_tol']):
                ln = float(np.hypot(*(b - a)))
                if ln < cfg['kerb_min']:
                    continue
                t = (b - a) / ln
                n = np.array([-t[1], t[0]])
                pm = (a + b) / 2
                # outward = the side not covered by a road-height surface
                if shapely.contains_xy(R, *(pm + n * 0.3)):
                    n = -n
                if not plateau.buffer(-1.0).contains(Point(*pm)):
                    continue
                inner = np.array([pm - n * 0.4, pm - n * 1.0])
                if not shapely.contains_xy(R, inner[:, 0], inner[:, 1]).all():
                    continue                     # a road tip narrower than the band: no band
                probe = np.array([pm + n * 0.25, pm + n * 0.5, pm + n * 1.0])
                if st.is_bld(probe).any() or shapely.contains_xy(Hh, probe[:, 0], probe[:, 1]).any():
                    continue                     # a sidewalk / island / building face: no band
                if (st.surf(probe) > -1.9).any():
                    continue                     # a slot (another surface within 1 stud)
                off = n * (cfg['kerb_out'] - cfg['kerb_w'] / 2)        # band centre: kerb_w / 2 inside the edge
                segs.append(dict(a=[float(v) for v in a + off], b=[float(v) for v in b + off], w=cfg['kerb_w'], kind='kerb'))
                covered += ln
    return segs, covered


def chords(c, max_len, tol):
    """straight pieces along the polyline c: from each start vertex to the farthest later vertex such that the chord is
    <= max_len and every vertex between stays within tol of it (so a straight Part hugs a curved kerb return)"""
    out = []
    i = 0
    n = len(c)
    while i < n - 1:
        j = i + 1
        while j + 1 < n:
            a, b = c[i], c[j + 1]
            L = float(np.hypot(*(b - a)))
            if L > max_len:
                break
            t = (b - a) / max(L, 1e-9)
            mid = c[i + 1:j + 1] - a
            dev = np.abs(mid[:, 0] * t[1] - mid[:, 1] * t[0])
            if len(dev) and dev.max() > tol:
                break
            j += 1
        a, b = c[i], c[j]
        L = float(np.hypot(*(b - a)))
        if L > max_len:                          # one long straight edge: split evenly
            k = int(math.ceil(L / max_len))
            for q in range(k):
                out.append((a + (b - a) * q / k, a + (b - a) * (q + 1) / k))
        else:
            out.append((a, b))
        i = j
    return out


# ---- option (b) / (c): what paving Parts would cost instead of the terrain ---------------------------------------------
def paving_cost(st, plateau, frontage=40.0, cell=256.0):
    """option (b): pave every patch of open terrain in the box with Road B-style flat WedgePart triangles at sidewalk
    height (1.6, kerbed against the road), so nothing drops; option (c): pave only the frontage (terrain within
    `frontage` studs of a building) and raise the terrain for the rest. Counted like the Road B export: constrained-
    Delaunay triangles of the area simplified 0.25, two WedgeParts each (one where the altitude foot is a corner),
    plus one kerb Part per 12 studs of road edge that meets the paving. Returns counts and the fullest 256-stud cell."""
    from collections import Counter
    surf = st.paved_union()
    free = plateau.difference(surf).difference(st.bld_union)
    out = {}
    for name, area in (('b_all_open_terrain', free), ('c_frontage_only', free.intersection(st.bld_union.buffer(frontage)))):
        tris = junction.triangles(area.simplify(0.25), simplify=0)
        wedges = sum(junction.wedge_parts(t) for t in tris)
        per = Counter()
        for t in tris:
            c = t.centroid
            per[(math.floor(c.x / cell), math.floor(c.y / cell))] += junction.wedge_parts(t)
        road_edge = area.boundary.intersection(unary_union([g for top, g in st.H.groups if 0.95 <= top <= 1.01]).buffer(0.5))
        kerbs = int(math.ceil(road_edge.length / 2 / 12.0))     # the boundary runs on both sides of the 0.5 buffer
        out[name] = dict(area=round(area.area, 0), triangles=len(tris), wedge_parts=int(wedges), kerb_parts=kerbs,
                         parts=int(wedges + kerbs), max_parts_in_a_256_cell=int(max(per.values()) if per else 0),
                         cells_over_600=int(sum(1 for v in per.values() if v > 600)))
    return out


# ---- one call: plan + QA for today / B / B + ground ------------------------------------------------------------------
def pilot(W, PB, cfg=None, log=print, details=True):
    """the ground plan on Road B and the static QA of today, B, B + ground (and today + ground, for reference)"""
    cfg = dict(GCFG, **(cfg or {}))
    G = plan(W, PB, cfg)
    x0, z0, x1, z1 = cfg['plateau_world']
    plateau = box(x0 - world.ORIGIN[0], z0, x1 - world.ORIGIN[0], z1)
    area = PB['area']
    states = dict(today=State(W, None), B=State(W, PB), B_ground=State(W, PB, G), today_ground=State(W, None, G))
    res = dict(cfg={k: v for k, v in cfg.items()}, plan=dict(G['counts'], i0=G['i0'], k0=G['k0'], ni=G['ni'], nk=G['nk'],
                                                             o_top=round(G['o_top'], 6)))
    for name, st in states.items():
        rays = details and name in ('today', 'B', 'B_ground')
        E = edge_samples(st, area)
        Er = edge_samples(st, area, road_only=True)
        r = dict(edges=edge_report(E, st), road_edges=edge_report(Er, st, rays=rays),
                 grid=grid_steps(st, plateau, res=1.0),
                 lanes=lane_wheels(st, PB), lanes_seam=lane_wheels(st, PB, seam=True))
        sp = spot2_runs(st)
        r['spot2'] = summarize_runs(sp)
        r['spot2_rows'] = sp
        orr = offroad_runs(st, PB)
        r['offroad'] = {k: summarize_runs([o for o in orr if o['set'] == k]) for k, _ in OFFROAD_SETS}
        r['offroad_rows'] = orr
        res[name] = r
        log(f"{name}: edges facing ground {r['edges']['facing_ground']} studs, drop>=1.5 {r['edges']['drop_ge_1_5']}, "
            f"road->ground max {r['road_edges']['road_to_ground_max_step']}; grid max step {r['grid']['max_step']} drops {r['grid']['drop_cells']}; "
            f"lanes holes {r['lanes']['holes']} drops {r['lanes']['drops']} of {r['lanes']['samples']}; "
            f"spot2 runs with drop {r['spot2']['with_drop']} / climb {r['spot2']['with_climb']}; "
            + '; '.join(f"offroad {k} {v['runs']} runs, drop {v['with_drop']}, climb {v['with_climb']}" for k, v in r['offroad'].items()))
    res['review_lanes'] = dict(today=PB['checks']['wheel_before'], B=PB['checks']['wheel_after'],
                               today_incl_seam=PB['checks']['wheel_before_incl_seam'], B_incl_seam=PB['checks']['wheel_after_incl_seam'])
    res['ramp_band'] = ramp_band(states, plateau)
    res['materials'] = visible_materials(G, states['B_ground'])
    segs, covered = kerb_bands(W, PB, G, cfg, st=states['B_ground'])
    res['kerbs'] = dict(parts=len(segs), edge_covered=round(covered, 1))
    res['paving_cost'] = paving_cost(states['B'], plateau)
    G['kerbs'] = segs
    log(f"ramp band: {dict((k, v['drop_cells'] if isinstance(v, dict) else v) for k, v in res['ramp_band'].items())}; "
        f"materials {res['materials']}; kerb bands {res['kerbs']}")
    return G, states, res
