"""Static QA of city batches (OFFLINE model, not physics): what the place's collision tops are after a set of batches,
the raised ground of several batches together, and the checks (lane holes, drops, steps, spot and off-road runs, the
seams). Same model as tools/roadvis/ground.py (ground.State): the highest colliding top at a point, the terrain
surface below everything, buildings as walls. Map-local studs.
"""
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from tools.roadvis import city, ground, junction, shoulder_proof, world

VOX = 4.0
TERRAIN_TOP = -2.0


class CityGround:
    """terrain surface of the union of raised batches: per voxel column the highest occupancy any raised batch gives
    it (the builder's max rule), surface = -2 + 4 * occupancy, bilinear between column centres (ground.GroundField)"""

    def __init__(self, plans):
        plans = [p for p in plans if p is not None]
        self.plans = plans
        if not plans:
            self.o = None
            return
        i0 = min(p['i0'] for p in plans) - 1
        k0 = min(p['k0'] for p in plans) - 1
        i1 = max(p['i0'] + p['ni'] for p in plans) + 1
        k1 = max(p['k0'] + p['nk'] for p in plans) + 1
        o = np.zeros((i1 - i0, k1 - k0))
        m = np.zeros((i1 - i0, k1 - k0), np.uint8)
        for p in plans:
            a, b = p['i0'] - i0, p['k0'] - k0
            sub = o[a:a + p['ni'], b:b + p['nk']]
            msub = m[a:a + p['ni'], b:b + p['nk']]
            new = np.maximum(sub, p['occ'])
            msub[p['occ'] > sub] = p['mat'][p['occ'] > sub]
            o[a:a + p['ni'], b:b + p['nk']] = new
        self.o, self.mat, self.i0, self.k0 = o, m, i0, k0
        self.ox = i0 * VOX + VOX / 2 - city.ORIGIN[0]
        self.oz = k0 * VOX + VOX / 2

    def occ_at_column(self, i, k):
        if self.o is None:
            return 0.0
        a, b = i - self.i0, k - self.k0
        if 0 <= a < self.o.shape[0] and 0 <= b < self.o.shape[1]:
            return float(self.o[a, b])
        return 0.0

    def at(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        if self.o is None:
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


def built_pieces(st, region=None):
    """[(polygon, top)] of every Road B piece standing in the place after the batches in st (own and completion pieces
    of every built city batch; frontier pieces whose target box is not built yet); grass is visual only"""
    out = []
    built = set(st['built'])
    for bid, res in st['pieces'].items():
        for t in res['tris'] + res['comp']:
            if t['kind'] == 4:
                continue
            if region is None or t['tri'].intersects(region):
                out.append((t['tri'], city.TRI_TOP[t['kind']]))
        for t in res['front']:
            if t['target'] in built:
                continue
            if region is None or t['tri'].intersects(region):
                out.append((t['tri'], city.TRI_TOP[t['kind']]))
    return out


class CityState:
    """collision tops after the batches in st, around `region` (duck-typed like ground.State for the ground.py checks):
    remaining old parts (real shapes and tops; paint left out), remaining pilot parts, the built Road B pieces, the
    installed shoulder pieces (0.985), buildings (walls, 99); `field` = the terrain (CityGround or None for -2)"""

    def __init__(self, CW, st, region, field=None):
        groups = defaultdict(list)
        for j in CW.old_tree.query(region):
            o = CW.old[int(j)]
            if o['i'] in st['replaced_old'] or o['cls'] == 'mark':
                continue
            groups[round(float(o['top']), 3)].append(o['shape'])
        if 'pilot' in st['built']:
            for j in CW.pilot_tree.query(region):
                p = CW.pilot['parts'][int(j)]
                if p['i'] in st['replaced_pilot'] or p['seg'] or p['code'] == 14:
                    continue
                groups[round(float(p['top']), 3)].append(p['shape'])
        for poly, top in built_pieces(st, region):
            groups[round(float(top), 3)].append(poly)
        if CW.sh_tree is not None:
            for j in CW.sh_tree.query(region):
                groups[0.985].append(CW.shoulders[int(j)]['poly'])
        self.groups = {k: v for k, v in groups.items() if k < 50}
        self.H = shoulder_proof.Heights(self.groups)
        blds = [b['poly'] for b in CW.buildings(region)]
        self.bld_union = unary_union(blds) if blds else Polygon()
        shapely.prepare(self.bld_union)
        self.ground = field if field is not None else CityGround([])
        self.P, self.G = None, None

    def surf(self, xy):
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


def foot_points(rows, o):
    """the 6 footprint points (RV.Probe: 4 x 9 car, corners + mid sides) of every probe row at lateral offset o"""
    A = np.asarray(rows, float)
    m = np.abs(o) <= A[:, 4]
    hw_, hl = city.export_luau.FOOT[0] / 2, city.export_luau.FOOT[1] / 2
    rel = [(-hl, -hw_), (-hl, hw_), (hl, -hw_), (hl, hw_), (0, -hw_), (0, hw_)]
    Q, T = A[m, 0:2], A[m, 2:4]
    N = np.stack([-T[:, 1], T[:, 0]], axis=1)
    C = Q + N * o
    pts = np.stack([C + T * lo + N * la for lo, la in rel], axis=1)
    return m, pts


def probe_expected(state, rows, offsets=None):
    """what RV.Probe(<id>) should count (offline): per offset and per split (inBox: the lane sample's centre in the box;
    seam: within PROBE_PAD outside it), the worst of the 6 footprint points: flat (a road part 0.9..1.1), kerb
    (1.1..1.8), blocked (> 1.8: a building), ground (no Road part: the ray reaches the terrain)"""
    offsets = offsets or city.export_luau.PROBE_OFFSETS
    A = np.asarray(rows, float)
    out = {}
    for o in offsets:
        m, pts = foot_points(rows, o)
        n = pts.shape[0]
        flat = pts.reshape(-1, 2)
        s = state.surf(flat).reshape(n, 6)
        b = state.is_bld(flat).reshape(n, 6)
        cls = np.where(b, 2, np.where(s > 1.8, 2, np.where(s > 1.1, 1, np.where(s >= 0.9, 0, 3))))
        worst = np.zeros(n, int)
        # RV.Probe order: ground (3) beats blocked (2) beats kerb (1) beats flat (0)
        worst = cls.max(axis=1)
        inbox = A[m, 6] > 0.5
        d = {}
        for split, sel in (('inBox', inbox), ('seam', ~inbox)):
            w = worst[sel]
            d[split] = dict(samples=int(sel.sum()), flat=int((w == 0).sum()), kerb=int((w == 1).sum()),
                            blocked=int((w == 2).sum()), ground=int((w == 3).sum()))
        out[str(o)] = d
    return out


def lane_check(state, I, region, step_k=1):
    """the Road B lane check (junction.wheel_check) on a state: every lane centre of every carriageway chain of the
    ideal whose car centre lies in `region`, every 2 studs, the 4 wheels of RaceCarServer: holes = a wheel with no
    road-height part under it (part top below 0.9: the terrain); drops = a wheel 1.5 or more below the lane top"""
    out = dict(samples=0, holes=0, drops=0, min_wheel=99.0, bad=[])
    shapely.prepare(region)
    reach = max(abs(lo) for _, lo in junction.CFG['wheels']) + 1.0
    for c in I['chains']:
        poly, Q, T, hw, s = I['rib'][c['id']]
        nl = max(min(c['lanes']), 1)
        mm = shapely.contains_xy(region, Q[:, 0], Q[:, 1]) & (s >= reach) & (s <= s[-1] - reach)
        if not mm.any():
            continue
        Qm, Tm, hm = Q[mm][::step_k], T[mm][::step_k], hw[mm][::step_k]
        N = np.stack([-Tm[:, 1], Tm[:, 0]], axis=1)
        for li in range(nl):
            o = -hm + (li + 0.5) * 2 * hm / nl
            C = Qm + N * o[:, None]
            hs = np.stack([state.surf(C + N * la + Tm * lo) for la, lo in junction.CFG['wheels']], axis=1)
            ha = np.stack([state.at(C + N * la + Tm * lo) for la, lo in junction.CFG['wheels']], axis=1)
            out['samples'] += int(len(C))
            bad = (hs < 0.9).any(axis=1)
            out['holes'] += int(bad.sum())
            out['drops'] += int((ha <= ground.ROAD_TOP - ground.DROP).any(axis=1).sum())
            out['min_wheel'] = min(out['min_wheel'], float(ha.min()))
            for q in C[bad][:max(0, 30 - len(out['bad']))]:
                out['bad'].append([round(float(q[0]) + city.ORIGIN[0], 1), round(float(q[1]), 1), c['id'], li])
    out['min_wheel'] = round(out['min_wheel'], 3)
    return out


def pseudo_pilot(res, region):
    """a junction.generate-like dict for ground.offroad_runs (area, chains, rib) from a batch's ideal"""
    I = res['ideal']
    return dict(area=region, chains=I['chains'], rib=I['rib'], cfg=I['cfg'])
