"""Offline proof that the approved shoulder pilot still carries the wheels with road design B in place (read only).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\shoulder_proof.py [--map] [--md]   -> build/roadvis/shoulder_proof.json
      --map: art/roadvis/spot2_drops.png + spot2_drops_zoom.png (drop maps); --md: build/roadvis/spot2_drop_tables.md

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
4. drop rows   : every gate run with a wheel over terrain, one row per run (today and B): which wheels, where each
                 stretch was (inside a drivable lane = > 1.2 studs inside a graph carriageway; edge line = -1.2..+1.0
                 about its edge; seam band = within seam_band of the pilot-area edge; shoulder strip = between the
                 carriageway and the outer edge of the shoulder pieces on the ray from the carriageway through the
                 wheel; past the shoulder = up to 10 studs beyond that edge; terrain = the rest), drop height (the
                 surface the wheel left down to the terrain at -2), length, up. drops_in_lane counts the lane rows.
"""
import json
import math
import os
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

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
        g.setdefault(c['asphalt_top'], []).extend(P.get('support_tris') or [])      # invisible supports collide too
        g.setdefault(c['sidewalk_top'], []).extend(P['walk_tris'])
        g.setdefault(c['island_top'], []).extend(P['isl_tris'])
    g[99.0] = [b['poly'] for b in W['blds']]
    return g


def edge_audit(W, area, P=None, step=1.0):
    pieces = [s for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS and s['poly'].intersects(area)]
    shoulders = unary_union([s['poly'] for s in pieces])
    H = Heights(state_groups(W, P, with_shoulders=False))      # the neighbours of the shoulder pieces
    Hs = Heights({SHOULDER_TOP: [s['poly'] for s in pieces]})
    res = dict(flush=0.0, kerb=0.0, ridge=0.0, drop=0.0, slot=0.0, other=0.0, inner=0.0, max_flush_step=0.0, max_kerb_step=0.0)
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
        # a raised sliver with another shoulder piece within 1 stud behind it: a ridge between two flush pieces
        back = np.max(np.stack([Hs.at(out + out_dir * d) for d in (0.4, 0.7, 1.0)]), axis=0) > 0
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
            elif 0.3 <= d <= 0.7 and back[k]:
                res['ridge'] += seg
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


WHEEL_NAMES = ('RL', 'RR', 'FL', 'FR')            # the WHEELS order (rear / front, left / right of travel)
LANE_INNER = 1.2      # inside a drivable lane: more than 1.2 studs inside the carriageway edge (B's edge line sits there)
EDGE_OUT = 1.0        # the edge line / kerb band: -1.2 .. +1.0 studs about the carriageway edge
RAY = 14.0            # the shoulder strip is looked for along the ray from the carriageway through the wheel, 14 studs
PAST = 10.0           # 'past the shoulder' up to 10 studs beyond the strip's outer edge, then 'terrain'
STRIP_MIN = 3.0       # a strip on the ray narrower than this (a taper tip) does not count as the strip's outer edge
STRIP_W = 9.5         # the pilot strips run 8-9.5 studs out from the carriageway edge
GAP_NEAR = 10.0       # a strip piece within 10 studs: the wheel is in a gap of the strip, not beside a bare road


class Where:
    """where a wheel contact is. The carriageways are those of the road graph (both carriageways of every road, the
    lanes GPS / traffic / checkpoints use); design B keeps the graph lane widths (lane_w None), so today and B share
    them: P = the design B pilot, whose chain ribbons ARE those carriageways"""

    def __init__(self, W, P, area):
        self.area = area
        self.road = unary_union([P['rib'][c['id']][0] for c in P['chains']])
        self.edge = self.road.boundary
        self.sh = unary_union([s['poly'] for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS
                               and s['poly'].intersects(area.buffer(60))])
        self.band = P['cfg']['seam_band']
        self.inner = area.buffer(-self.band)
        for g in (self.road, self.sh, self.inner):
            shapely.prepare(g)

    def label(self, xy):
        x, z = float(xy[0]), float(xy[1])
        pt = Point(x, z)
        inside = shapely.contains_xy(self.road, x, z)
        d = self.edge.distance(pt)
        d_c = -d if inside else d                       # signed distance to the carriageway edge (- inside)
        seam = not shapely.contains_xy(self.inner, x, z)
        if d_c < -LANE_INNER:
            return 'lane', d_c
        if d_c <= EDGE_OUT:
            return ('edge line (seam band)' if seam else 'edge line'), d_c
        if seam:
            return 'seam band', d_c
        # the shoulder strip's outer extent along the ray from the nearest carriageway point through the wheel
        c = nearest_points(self.road, pt)[0]
        v = np.array([x - c.x, z - c.y])
        v /= max(np.linalg.norm(v), 1e-9)
        ray = LineString([(c.x, c.y), (c.x + v[0] * RAY, c.y + v[1] * RAY)])
        hit = ray.intersection(self.sh)
        outer = 0.0 if hit.is_empty else max(Point(q).distance(c) for g in getattr(hit, 'geoms', [hit]) for q in g.coords)
        if outer >= STRIP_MIN:
            if d_c <= outer:
                return 'shoulder strip', d_c                 # a joint / gap inside the strip
            return ('past the shoulder' if d_c <= outer + PAST else 'terrain'), d_c
        # no strip on this ray: within the strip's width beside the carriageway, with strip pieces close by, it is a gap
        # in the strip (its end, a taper tip); anything else beside the road is terrain
        if d_c <= STRIP_W and self.sh.distance(pt) <= GAP_NEAR:
            return 'shoulder strip', d_c
        return 'terrain', d_c


def drop_rows(W, P_state, Wh, step=1.0):
    """the spot 2 gate runs with a wheel over terrain, one row per run: which wheels, where they were (location class
    per stretch), the drop height (the surface the wheel left, down to the terrain at -2), the drop length (studs of
    path with that wheel down; the run's total: samples with any wheel down) and the up value (run minimum and at the
    drops). Every contiguous stretch of one wheel is listed with its arc start, length, class and world position."""
    H = Heights(state_groups(W, P_state))
    path = np.array([(x - world.ORIGIN[0], z) for x, z in PATH_B])
    rows = []
    for direction in ('fwd', 'rev'):
        pts = path if direction == 'fwd' else path[::-1]
        Q = world.rc.probes_of(pts, step)[6:-6]
        T = np.gradient(Q, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
        R = np.stack([-T[:, 1], T[:, 0]], axis=1)
        for lat in LATERALS:
            C = Q + R * lat
            P4 = np.stack([C + R * la + T * lo for la, lo in WHEELS], axis=1)            # (n, 4, 2)
            hs = np.stack([H.at(P4[:, w]) for w in range(4)], axis=1)
            down = hs < 0.5
            blocked = hs > 50
            hh = np.clip(hs, -2.0, 2.0)
            gx = ((hh[:, 1] + hh[:, 3]) - (hh[:, 0] + hh[:, 2])) / 2 / 6.8
            gz = ((hh[:, 2] + hh[:, 3]) - (hh[:, 0] + hh[:, 1])) / 2 / 10.4
            up = 1 / np.sqrt(1 + gx ** 2 + gz ** 2)
            if not down.any():
                continue
            stretches = []
            for w in range(4):
                idx = np.nonzero(down[:, w])[0]
                if not len(idx):
                    continue
                br = np.nonzero(np.diff(idx) > 1)[0]
                for a, b in zip(np.r_[idx[0], idx[br + 1]], np.r_[idx[br], idx[-1]]):
                    a, b = int(a), int(b)
                    labs = [Wh.label(P4[j, w]) for j in range(a, b + 1)]
                    names = [l for l, _ in labs]
                    lab = max(set(names), key=names.count)
                    left = [hs[j, w] for j in (a - 1, b + 1) if 0 <= j < len(hs) and -1.0 < hs[j, w] < 50]
                    mid = P4[(a + b) // 2, w]
                    stretches.append(dict(
                        wheel=WHEEL_NAMES[w], s=a * step, length=(b - a + 1) * step, where=lab,
                        where_samples={n: names.count(n) for n in sorted(set(names))},
                        off_carriageway=[round(min(d for _, d in labs), 1), round(max(d for _, d in labs), 1)],
                        from_height=round(float(max(left)), 3) if left else None,
                        drop=round(float(max(left)) + 2.0, 3) if left else None,
                        up_min=round(float(up[a:b + 1].min()), 3),
                        world=[round(float(mid[0]) + world.ORIGIN[0], 1), round(float(mid[1]), 1)],
                        pts=[[round(float(P4[j, w, 0]) + world.ORIGIN[0], 1), round(float(P4[j, w, 1]), 1)]
                             for j in range(a, b + 1)]))
            stretches.sort(key=lambda r: (r['s'], r['wheel']))
            where = {}
            for r in stretches:
                for n, k in r['where_samples'].items():
                    where[n] = where.get(n, 0) + k
            drops = [r['drop'] for r in stretches if r['drop'] is not None]
            for v in SPEEDS:
                rows.append(dict(dir=direction, lateral=lat, speed=v,
                                 wheels=[n for n in WHEEL_NAMES if any(r['wheel'] == n for r in stretches)],
                                 where=where, lane_samples=where.get('lane', 0),
                                 drop_height=max(drops) if drops else None,
                                 drop_length=int(down.any(axis=1).sum() * step),
                                 longest=max(r['length'] for r in stretches),
                                 blocked=int(blocked.any(axis=1).sum()),
                                 min_up=round(float(up.min()), 3),
                                 up_at_drops=round(float(up[down.any(axis=1)].min()), 3),
                                 stretches=stretches))
    return rows


CLASS_COLORS = {'lane': (255, 0, 0), 'edge line': (255, 150, 0), 'edge line (seam band)': (255, 150, 0),
                'seam band': (255, 150, 0), 'shoulder strip': (255, 240, 0), 'past the shoulder': (0, 230, 255),
                'terrain': (255, 0, 255)}


def group(where):
    """the owner's five location classes"""
    if where == 'lane':
        return 'lane'
    if where.startswith(('edge', 'seam')):
        return 'edge line'
    return where


def drop_map(W, P, res, path, pad=40.0, px=3.0, bb=None):
    """top-down 'what the eye sees' (raster.render_look, the same renderer for both) of spot 2, today | B: the graph
    carriageways (thin cyan), the gate centre lines (white = path B, grey = laterals) and every wheel-over-terrain
    sample of the 36 runs, coloured by where it was. Offline preview, not Studio."""
    from PIL import Image, ImageDraw, ImageFont
    from tools.roadvis import raster
    xs = [x - world.ORIGIN[0] for x, _ in PATH_B]
    zs = [z for _, z in PATH_B]
    bb = bb or (min(xs) - pad, min(zs) - pad, max(xs) + pad, max(zs) + pad)
    path_l = np.array([(x - world.ORIGIN[0], z) for x, z in PATH_B])
    Q = world.rc.probes_of(path_l, 1.0)
    T = np.gradient(Q, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    R = np.stack([-T[:, 1], T[:, 0]], axis=1)
    road = unary_union([P['rib'][c['id']][0] for c in P['chains']])
    ims = []
    for key, PP, title in (('drops_before', None, 'TODAY: spot 2 wheel-over-terrain samples (offline preview, not Studio)'),
                           ('drops_after', P, 'DESIGN B: spot 2 wheel-over-terrain samples (offline preview, not Studio)')):
        img = raster.render_look(W, bb, None, P=PP, px=px, title=title)
        c = raster.Canvas(bb, px, None, title)
        c.img, c.d = img, ImageDraw.Draw(img)
        for q in junction.polys(road):
            for ring in [q.exterior] + list(q.interiors):
                c.line(list(ring.coords), (0, 200, 220), 1)
        for lat in LATERALS:
            c.line(list(map(tuple, Q + R * lat)), (150, 150, 150), 1)
        c.line(list(map(tuple, Q)), (255, 255, 255), 1)
        n = {}
        seen = set()
        for r in res[key]:
            if r['speed'] != SPEEDS[0]:
                continue
            for t in r['stretches']:
                col = CLASS_COLORS.get(t['where'], (255, 255, 255))
                n[t['where']] = n.get(t['where'], 0) + t['length']
                for x, z in t['pts']:
                    if (x, z) in seen:
                        continue
                    seen.add((x, z))
                    u, v = c.xy((x - world.ORIGIN[0], z))
                    c.d.ellipse([u - 2, v - 2, u + 2, v + 2], fill=col, outline=(0, 0, 0))
        f = ImageFont.load_default()
        y = 26 + 10                     # top left, under the title: no drop sample lies there in either view
        c.d.rectangle([4, y - 4, 300, y + 16 * 7 + 4], fill=(255, 255, 255), outline=(0, 0, 0))
        rows = [('lane', 'inside a drivable lane'), ('edge line', 'edge line / seam band'), ('shoulder strip', 'shoulder strip'),
                ('past the shoulder', 'past the shoulder'), ('terrain', 'terrain')]
        for i, (k, lab) in enumerate(rows):
            cnt = sum(v for kk, v in n.items() if group(kk) == k)
            c.d.ellipse([10, y + 16 * i + 2, 20, y + 16 * i + 12], fill=CLASS_COLORS[k], outline=(0, 0, 0))
            c.d.text((26, y + 16 * i + 1), f'{lab}: {int(cnt)} wheel-studs', fill=(0, 0, 0), font=f)
        c.d.text((10, y + 16 * len(rows) + 1), 'cyan = graph carriageways, white = path B, grey = laterals', fill=(0, 0, 0), font=f)
        c.d.text((10, y + 16 * (len(rows) + 1) + 1), 'wheel-studs over the 12 dir x lateral runs (any speed)', fill=(0, 0, 0), font=f)
        ims.append(img)
    gap = 12
    out = Image.new('RGB', (sum(i.width for i in ims) + gap, max(i.height for i in ims)), (255, 255, 255))
    out.paste(ims[0], (0, 0))
    out.paste(ims[1], (ims[0].width + gap, 0))
    out.save(path)
    return path


def _where_txt(where):
    order = ['lane', 'edge line', 'edge line (seam band)', 'seam band', 'shoulder strip', 'past the shoulder', 'terrain']
    return ', '.join(f'{k} {where[k]}' for k in sorted(where, key=lambda k: order.index(k) if k in order else 99))


def drop_tables_md(res):
    """the drop rows as markdown (docs/ROAD_B_OWNER_REVIEW.md): one row per run, today then B, and the stretches"""
    out = ['| State | Dir | Lateral | Speed | Wheels down | Where (wheel-studs) | Drop height | Length (studs of path / longest) | Min up | Building samples |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for key, lab in (('drops_before', 'today'), ('drops_after', 'B')):
        for r in res[key]:
            h = f"{r['drop_height']:.3f}" if r['drop_height'] is not None else 'n/a'
            out.append(f"| {lab} | {r['dir']} | {r['lateral']:+d} | {r['speed']} | {'+'.join(r['wheels'])} | {_where_txt(r['where'])} | "
                       f"{h} | {r['drop_length']} / {int(r['longest'])} | {r['min_up']:.3f} | {r['blocked']} |")
    st = ['| State | Dir | Lateral | Wheel | Path s | Length | Where | Off the carriageway edge | From surface -> drop | Min up | World (x, z) |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for key, lab in (('drops_before', 'today'), ('drops_after', 'B')):
        for r in res[key]:
            if r['speed'] != SPEEDS[0]:
                continue
            for t in r['stretches']:
                fr = f"{t['from_height']:.3f} -> {t['drop']:.3f}" if t['drop'] is not None else 'n/a (next to a building / path end)'
                st.append(f"| {lab} | {r['dir']} | {r['lateral']:+d} | {t['wheel']} | {int(t['s'])} | {int(t['length'])} | {t['where']} | "
                          f"{t['off_carriageway'][0]:.1f} .. {t['off_carriageway'][1]:.1f} | {fr} | {t['up_min']:.3f} | "
                          f"({t['world'][0]:.1f}, {t['world'][1]:.1f}) |")
    return '\n'.join(out) + '\n\n' + '\n'.join(st) + '\n'


def untouched(W, P):
    shoulder_ids = {id(s) for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS}
    return dict(replaced_shoulder_pieces=sum(1 for s in P['replaced'] if id(s) in shoulder_ids),
                shoulder_pieces_total=len(shoulder_ids))


def run(W, P, area, details=True):
    res = dict(untouched=untouched(W, P), edges_before=edge_audit(W, area), edges_after=edge_audit(W, area, P),
               gate_before=drive_gate(W), gate_after=drive_gate(W, P))
    if details:
        Wh = Where(W, P, area)
        res['drops_before'] = drop_rows(W, None, Wh)
        res['drops_after'] = drop_rows(W, P, Wh)
        res['drops_in_lane'] = dict(before=sum(r['lane_samples'] > 0 for r in res['drops_before']),
                                    after=sum(r['lane_samples'] > 0 for r in res['drops_after']),
                                    before_samples=sum(r['lane_samples'] for r in res['drops_before']),
                                    after_samples=sum(r['lane_samples'] for r in res['drops_after']))
    return res


def main():
    from shapely.geometry import box
    cfg = dict(junction.CFG, design='B', name=junction.CFG['name'] + '_B')
    bl = world.world_bbox_local(cfg['bbox_world'])
    W = world.load(None, bbox=bl)
    P = junction.generate(W, cfg)
    res = run(W, P, box(*bl))
    out = os.path.join(W['broot'], 'roadvis', 'shoulder_proof.json')
    json.dump(res, open(out, 'w', encoding='utf-8'), indent=1)
    if '--md' in sys.argv:
        md = os.path.join(W['broot'], 'roadvis', 'spot2_drop_tables.md')
        open(md, 'w', encoding='utf-8').write(drop_tables_md(res))
        print('wrote', md)
    if '--map' in sys.argv:
        print('wrote', drop_map(W, P, res, os.path.join(REPO, 'art', 'roadvis', 'spot2_drops.png')))
        # the drop zone up close (world x 24525..24600, z 900..1045)
        print('wrote', drop_map(W, P, res, os.path.join(REPO, 'art', 'roadvis', 'spot2_drops_zoom.png'), px=6.0,
                                bb=(24525.0 - world.ORIGIN[0], 900.0, 24600.0 - world.ORIGIN[0], 1045.0)))
    s = {k: v for k, v in res.items() if not k.startswith(('gate', 'drops_b', 'drops_a'))}
    for k in ('gate_before', 'gate_after'):
        g = res[k]
        s[k] = dict(n=g['n'], flips=g['flips'], min_up=g['min_up'],
                    worst=[r for r in g['runs'] if r['speed'] == 150 and (r['flip'] or r['min_up'] < 0.99)])
    print(json.dumps(s, indent=1))
    for k in ('drops_before', 'drops_after'):
        print(k, 'runs', len(res[k]))
        for r in res[k]:
            if r['speed'] == 150:
                print('  ', r['dir'], r['lateral'], '+'.join(r['wheels']), r['where'], 'drop', r['drop_height'],
                      'len', r['drop_length'], 'up', r['min_up'])
    print('wrote', out)


if __name__ == '__main__':
    main()
