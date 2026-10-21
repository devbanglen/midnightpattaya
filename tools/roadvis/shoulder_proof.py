"""Offline proof that the approved shoulder pilot still carries the wheels with road design B in place (read only).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\shoulder_proof.py     -> build/roadvis/shoulder_proof.json

1. untouched   : the B replace list holds no ShoulderChunks part (MoveReplaced selects by name in road folders only;
                 the Luau test proves the same on a mock tree), B builds nothing into ShoulderChunks, ShoulderLook is
                 opt-in only.
2. edge audit  : every edge of every shoulder / taper / gap piece in the pilot area, sampled every 1 stud. At 0.1 stud
                 outside the edge the collision top is read (highest surface there: B asphalt 1.0, kept old road 1.0 /
                 0.99 / 0.98, other shoulder 0.985, B sidewalk 1.6, island 1.45, corner fill 1.58; nothing = terrain -2).
                 Classes: flush (road height, step <= 0.02), kerb (a 0.5-0.62 step UP to a sidewalk / island face: a
                 kerb, no drop), drop (terrain: a 3-stud drop), slot (nothing at 0.1 but a surface within 1.0 stud: a
                 narrow gap a suspension ray could fall into). Plus the shoulder area covered by B asphalt (1.5 cm above
                 it: hidden, both collide, no step) and any overlap of B sidewalk / island collision on a shoulder piece.
3. drive gate  : the Studio pilot harness geometry (spot 2 path B, both directions, TestKit lateral +-24 / +-20 / +-14
                 to the right of travel). Every 1 stud: the 4 wheel contacts of RaceCarServer (track 6.8, wheelbase 10.4)
                 read the collision top. A run "flips" here when a wheel is over terrain (the cause of every Studio flip);
                 'up' is the static up-vector Y of the plane through the 4 contacts (1 = level). Speed does not change
                 static geometry, so 100 / 150 / 200 give the same offline numbers: the dynamic proof needs physics
                 drives in Studio after an approved build. Spot 1 (25250, 13430) lies outside the pilot area: B does not
                 change its geometry, the Studio result there stands (72 runs, 0 flips, min up 0.71 over both spots).
"""
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from tools.roadvis import junction, world  # noqa: E402

SHOULDER_TOP = 0.985
# docs/ROAD_SHOULDERS.md, Studio pilot harness, flip spot 2 (world coordinates)
PATH_B = [(24596.6, 653.5), (24573.8, 735.1), (24568.6, 752.1), (24553.5, 806.2), (24554.9, 890.5), (24554.0, 898.5),
          (24549.5, 921.9), (24538.3, 969.3), (24517.5, 1038.6)]
LATERALS = (24, -24, 20, -20, 14, -14)          # TestKit lateral, + = right of travel
SPEEDS = (100, 150, 200)
WHEELS = ((-3.4, -5.2), (3.4, -5.2), (-3.4, 5.2), (3.4, 5.2))   # (lateral right, longitudinal forward)


class Heights:
    """collision top at a point: max over surface groups; -2 (terrain) where nothing collides; 99 on a building"""

    def __init__(self, groups):
        self.groups = []
        for top, polys in sorted(groups.items()):
            g = unary_union([p for p in polys if p is not None and not p.is_empty])
            if not g.is_empty:
                shapely.prepare(g)
                self.groups.append((top, g))

    def at(self, xy):
        xy = np.asarray(xy, float).reshape(-1, 2)
        h = np.full(len(xy), -2.0)
        for top, g in self.groups:
            m = shapely.contains_xy(g, xy[:, 0], xy[:, 1])
            h[m] = np.maximum(h[m], top)
        return h


def state_groups(W, P=None, with_shoulders=True):
    rep = {id(s) for s in P['replaced']} if P is not None else set()
    g = {}
    for s in W['surf']:
        if id(s) in rep:
            continue
        if s['kind'] in world.SHOULDER_KINDS and not with_shoulders:
            continue
        g.setdefault(round(float(s['top']), 3), []).append(s['poly'])
    if P is not None:
        c = P['cfg']
        g.setdefault(c['asphalt_top'], []).extend(P['tris'])
        g.setdefault(c['sidewalk_top'], []).extend(P['walk_tris'])
        g.setdefault(c['island_top'], []).extend(P['isl_tris'])
    g[99.0] = [b['poly'] for b in W['blds']]
    return g


def edge_audit(W, area, P=None, step=1.0):
    pieces = [s for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS and s['poly'].intersects(area)]
    shoulders = unary_union([s['poly'] for s in pieces])
    H = Heights(state_groups(W, P, with_shoulders=False))      # the neighbours of the shoulder pieces
    Hs = Heights({SHOULDER_TOP: [s['poly'] for s in pieces]})
    res = dict(flush=0.0, kerb=0.0, drop=0.0, slot=0.0, other=0.0, inner=0.0, max_flush_step=0.0, max_kerb_step=0.0)
    for ring in [shoulders.exterior] if shoulders.geom_type == 'Polygon' else []:
        pass
    rings = []
    for p in junction.polys(shoulders):
        rings += [p.exterior] + list(p.interiors)
    for ring in rings:
        L = LineString(ring.coords)
        n = max(int(L.length / step), 1)
        s = (np.arange(n) + 0.5) * L.length / n
        pts = np.array([[L.interpolate(v).x, L.interpolate(v).y] for v in s])
        nxt = np.array([[L.interpolate(min(v + 0.05, L.length)).x, L.interpolate(min(v + 0.05, L.length)).y] for v in s])
        t = nxt - pts
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)
        # outward = the side NOT covered by a shoulder piece
        a, b = pts + nrm * 0.1, pts - nrm * 0.1
        ina = Hs.at(a) > 0
        out = np.where(ina[:, None], b, a)
        out_dir = np.where(ina[:, None], -nrm, nrm)
        inside_area = shapely.contains_xy(area, pts[:, 0], pts[:, 1])
        h0 = H.at(out)
        h1 = np.max(np.stack([H.at(out + out_dir * d) for d in (0.4, 0.7, 1.0)]), axis=0)
        both_sh = (Hs.at(a) > 0) & (Hs.at(b) > 0)
        seg = L.length / n
        for k in range(n):
            if not inside_area[k]:
                continue
            if both_sh[k]:
                res['inner'] += seg
                continue
            d = h0[k] - SHOULDER_TOP
            if h0[k] > 50:
                res['other'] += seg              # a building face
            elif -0.03 <= d <= 0.03:
                res['flush'] += seg
                res['max_flush_step'] = max(res['max_flush_step'], abs(d))
            elif 0.3 <= d <= 0.7:
                res['kerb'] += seg
                res['max_kerb_step'] = max(res['max_kerb_step'], d)
            elif h0[k] <= -1.0:
                if h1[k] > 0.5:
                    res['slot'] += seg
                else:
                    res['drop'] += seg
            else:
                res['other'] += seg
    res = {k: round(v, 3 if 'step' in k else 1) for k, v in res.items()}
    if P is not None:
        res['shoulder_area_under_B_asphalt'] = round(shoulders.intersection(P['S']).area, 0)
        res['B_sidewalk_island_collision_on_shoulders'] = round(unary_union(P['walk_tris'] + P['isl_tris']).intersection(shoulders.buffer(-0.05)).area, 2)
        res['B_visual_sidewalk_on_shoulders'] = round(P['walk'].intersection(shoulders.buffer(-0.05)).area, 2)
    res['shoulder_pieces'] = len(pieces)
    return res


def drive_gate(W, P=None, step=1.0):
    H = Heights(state_groups(W, P))
    path = np.array([(x - world.ORIGIN[0], z) for x, z in PATH_B])
    runs = []
    for direction in ('fwd', 'rev'):
        pts = path if direction == 'fwd' else path[::-1]
        Q = world.rc.probes_of(pts, step)
        Q = Q[6:-6]               # the car stays on the path: no wheel past either end (as junction.wheel_check)
        T = np.gradient(Q, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        R = np.stack([-T[:, 1], T[:, 0]], axis=1)          # right of travel (x east, z south)
        for lat in LATERALS:
            C = Q + R * lat
            hs = np.stack([H.at(C + R * la + T * lo) for la, lo in WHEELS], axis=1)
            drop = (hs < 0.5).any(axis=1)
            blocked = (hs > 50).any(axis=1)
            hh = np.clip(hs, -2.0, 2.0)
            gx = ((hh[:, 1] + hh[:, 3]) - (hh[:, 0] + hh[:, 2])) / 2 / 6.8
            gz = ((hh[:, 2] + hh[:, 3]) - (hh[:, 0] + hh[:, 1])) / 2 / 10.4
            up = 1 / np.sqrt(1 + gx ** 2 + gz ** 2)
            kerb = ((hs > 1.2) & (hs < 2)).any(axis=1)
            for v in SPEEDS:
                runs.append(dict(dir=direction, lateral=lat, speed=v, samples=int(len(C)), wheel_drops=int(drop.sum()),
                                 blocked=int(blocked.sum()), kerb=int(kerb.sum()), min_up=round(float(up.min()), 3),
                                 flip=bool(drop.any() or blocked.any())))
    return dict(runs=runs, flips=sum(r['flip'] for r in runs), min_up=min(r['min_up'] for r in runs), n=len(runs))


def untouched(W, P):
    shoulder_ids = {id(s) for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS}
    return dict(replaced_shoulder_pieces=sum(1 for s in P['replaced'] if id(s) in shoulder_ids),
                shoulder_pieces_total=len(shoulder_ids))


def run(W, P, area):
    return dict(untouched=untouched(W, P), edges_before=edge_audit(W, area), edges_after=edge_audit(W, area, P),
                gate_before=drive_gate(W), gate_after=drive_gate(W, P))


def main():
    from shapely.geometry import box
    cfg = dict(junction.CFG, design='B', name=junction.CFG['name'] + '_B')
    bl = world.world_bbox_local(cfg['bbox_world'])
    W = world.load(None, bbox=bl)
    P = junction.generate(W, cfg)
    res = run(W, P, box(*bl))
    out = os.path.join(W['broot'], 'roadvis', 'shoulder_proof.json')
    json.dump(res, open(out, 'w', encoding='utf-8'), indent=1)
    s = {k: v for k, v in res.items() if not k.startswith('gate')}
    for k in ('gate_before', 'gate_after'):
        g = res[k]
        s[k] = dict(n=g['n'], flips=g['flips'], min_up=g['min_up'],
                    worst=[r for r in g['runs'] if r['speed'] == 150 and (r['flip'] or r['min_up'] < 0.99)])
    print(json.dumps(s, indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
