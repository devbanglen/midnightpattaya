"""Offline junction pilot: new road geometry for ONE area from the road graph (preview only, nothing is built).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py pilot        (writes build/roadvis/pilot_<name>.json)

Inputs (read only): graph_game.json of central / wide / corridor (carriageway centrelines, widths, lanes, oneway: BOTH
carriageways of a dual road, the hidden ones too), the built chunk data (world.load: what stays outside the area, the
buildings, the OSM crossing evidence in build/furniture), nothing else. The graph is not changed.

Layers (docs/ROAD_VISUAL_SPEC.md):
  carriageways   chains of graph edges through degree-2 joints (same direction, turn < 50 deg); a variable-width ribbon
                 per chain (width = lanes x lane width from the graph; width changes taper over 4 studs per stud)
  junction zones per junction node (degree >= 3): the hull of the node and its arms' cross-sections at the MOUTH, the
                 first point along the arm where its ribbon no longer touches another arm (capped); zones that touch merge
                 into one junction complex
  asphalt        union of the ribbons + kerb-return fillets (morphological closing with the kerb radius, only inside the
                 junction complexes) - buildings; no discs, no fill triangles, no aprons
  islands        terrain slivers narrower than 2 x island_gap between carriageways and small enclosed holes become raised,
                 kerbed islands (no meaningless asphalt, no green slivers)
  sidewalks      a sidewalk band (with a kerb strip) along every outer asphalt edge and around islands, minus buildings,
                 minus what stays outside (the seam)
  markings       per carriageway: lane dashes (continuous along the chain, one dash phase), the centre double line of a
                 two-way road; separators where two carriageways share asphalt (double yellow between opposite
                 directions, solid white between same-direction ones) on the nearest-centreline split (Voronoi); edge
                 lines 1.2 inside every asphalt edge; nothing inside junction complexes; stop lines at every inbound mouth
  crossings      only on junction legs (OSM crossing evidence within 60 studs of the mouth, or a signalised junction),
                 perpendicular to the leg, spanning the whole asphalt section kerb to kerb (islands are refuges), both
                 ends on a sidewalk or island, just outside the junction mouth
  collision      invisible: the asphalt grown 0.3 and simplified 0.25 as constrained-Delaunay triangles (two WedgeParts
                 each, flat top at 1.0); sidewalks / islands shrunk 0.3, triangulated; collision covers the visible asphalt
  visual         triangle meshes (asphalt, sidewalk, kerb, island, markings), for MeshParts per 128-stud tile
The seam: old road parts whose footprint lies mostly inside the area are replaced (listed), the rest stay; within
`seam_band` studs of the area edge the new asphalt tapers (45 deg) to the asphalt that stays outside.
"""
import hashlib
import json
import math
import os
from collections import Counter, defaultdict

import numpy as np
import shapely
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from tools.roadvis import world

CFG = dict(
    name='sukhumvit_klang', bbox_world=(24220.0, 650.0, 24820.0, 1250.0), design='B', keep_shoulders_flush=True,
    lane_w=None,                 # None: keep the graph widths (13-stud lanes, traffic / car tuned); a number re-lanes
    kerb_r=10.0,                 # kerb-return fillet radius at junctions
    island_gap=7.0,              # gaps narrower than 2 x this between carriageways become islands
    island_hole_max=4000.0,      # enclosed holes smaller than this become islands (bigger ones stay ground + kerb)
    sidewalk_w=8.0, kerb_w=1.0, island_top=1.45, sidewalk_top=1.6, asphalt_top=1.0, visual_lift=0.01,
    seam_band=40.0, seam_step=2.0,
    mouth_cap=70.0, mouth_pad=2.0, cluster_gap=1.0,
    dash=8.0, dash_gap=12.0, line_w=0.5, centre_gap=1.0, edge_inset=1.2, stop_w=1.6,
    zebra_bar=2.0, zebra_gap=2.0, zebra_depth=10.0, zebra_inset=1.0, crossing_evidence=60.0, zebra_max_span=110.0, conflict_deg=12.0, field_close=12.0, separator_simplify=2.0,
    coll_slack=0.3, coll_simplify=0.25,
    wheels=((-3.4, -5.2), (3.4, -5.2), (-3.4, 5.2), (3.4, 5.2)), wheel_step=2.0, contact_r=0.05,
)
REPLACE_KINDS = ('road', 'fill', 'junction', 'joint', 'apron', 'sidewalk', 'corner')


def unit(v):
    n = float(np.hypot(v[0], v[1]))
    return np.asarray(v, float) / n if n > 1e-12 else np.array([1.0, 0.0])


def left_of(t):
    """driver's left of travel direction t in map x (east) / z (south)"""
    return np.array([t[1], -t[0]])


def polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    return [p for q in getattr(g, 'geoms', []) for p in polys(q)]


def lines_of(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'LineString':
        return [g]
    if g.geom_type == 'LinearRing':
        return [LineString(g.coords)]
    return [l for q in getattr(g, 'geoms', []) for l in lines_of(q)]


def clean(g, eps=0.05):
    if g is None or g.is_empty:
        return Polygon()
    g = shapely.make_valid(g)
    return unary_union([p for p in polys(g) if p.area > eps])


def resample(P, step):
    P = np.asarray(P, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    keep = np.concatenate([[True], seg > 1e-6])
    P = P[keep]
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    n = max(int(math.ceil(s[-1] / step)), 1)
    t = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], axis=1), t


def tangents(Q):
    T = np.zeros_like(Q)
    T[1:-1] = Q[2:] - Q[:-2]
    T[0] = Q[1] - Q[0]
    T[-1] = Q[-1] - Q[-2]
    n = np.linalg.norm(T, axis=1, keepdims=True)
    return T / np.maximum(n, 1e-9)


# ---- 1. carriageway chains ----------------------------------------------------------------------------------------
def chains_of(G, area, margin=80.0):
    """[chain dict]: edges joined through degree-2 joints (turn < 50 deg, same oneway sense, oriented a->b)"""
    Bb = area.buffer(margin)
    E = [e for e in G['edges'] if LineString(e['pts']).intersects(Bb)]
    at = defaultdict(list)
    for i, e in enumerate(E):
        at[e['a']].append((i, 'a'))
        at[e['b']].append((i, 'b'))

    def head(i, end):
        P = np.asarray(E[i]['pts'], float)
        return unit(P[min(3, len(P) - 1)] - P[0]) if end == 'a' else unit(P[max(-4, -len(P))] - P[-1])

    nxt = {}
    for n, lst in at.items():
        if G['deg'][n] != 2 or len(lst) != 2:
            continue
        (i, ei), (j, ej) = lst
        A, B = E[i], E[j]
        if A['oneway'] != B['oneway'] or i == j:
            continue
        if A['oneway'] and ei == ej:                   # two one-ways meeting head to head / tail to tail
            continue
        turn = math.degrees(math.acos(max(-1.0, min(1.0, float(-head(i, ei) @ head(j, ej))))))
        if turn > 50:
            continue
        nxt[(i, ei)] = (j, ej)
        nxt[(j, ej)] = (i, ei)
    seen, chains = set(), []
    for i0 in range(len(E)):
        if i0 in seen:
            continue
        # walk back to the start of the chain
        i, end = i0, 'a'
        guard = 0
        while (i, end) in nxt and guard < 500:
            j, ej = nxt[(i, end)]
            if j == i0:
                break
            i, end = j, ('b' if ej == 'a' else 'a')
            guard += 1
        start_rev = end == 'b'
        seq, cur, rev = [], i, start_rev
        while cur is not None and cur not in seen:
            seen.add(cur)
            seq.append((cur, rev))
            out_end = 'a' if rev else 'b'
            if (cur, out_end) in nxt:
                j, ej = nxt[(cur, out_end)]
                cur, rev = j, (ej == 'b')
            else:
                cur = None
        if E[seq[0][0]]['oneway'] and any(r for _, r in seq):      # keep the traffic direction of one-way chains
            seq = [(k, not r) for k, r in reversed(seq)]
        pts, wid, eids, ends_s = [], [], [], [0.0]
        for k, r in seq:
            P = np.asarray(E[k]['pts'], float)
            P = P[::-1] if r else P
            if pts:
                P = P[1:]
            pts += [tuple(p) for p in P]
            eids.append(E[k]['id'])
            L = LineString(np.asarray(E[k]['pts'], float)).length
            ends_s.append(ends_s[-1] + L)
            wid.append(E[k]['width'])
        e0 = E[seq[0][0]]
        first, last = seq[0], seq[-1]
        node_a = E[first[0]]['b'] if first[1] else E[first[0]]['a']
        node_b = E[last[0]]['a'] if last[1] else E[last[0]]['b']
        chains.append(dict(id=len(chains), edges=eids, pts=np.asarray(pts), widths=wid, joints_s=ends_s,
                           lanes=[E[k]['lanes'] for k, _ in seq], oneway=e0['oneway'], tier=e0['tier'], cls=e0['class'],
                           name=e0.get('name_en') or e0.get('name') or e0['class'], a=node_a, b=node_b,
                           way=[E[k]['way'] for k, _ in seq]))
    return chains


def ribbon(c, step=2.0):
    """variable-width ribbon of a chain: (polygon, Q samples, T tangents, half widths, s)"""
    Q, s = resample(c['pts'], step)
    T = tangents(Q)
    # width per sample: the edge it belongs to, linear tapers of 4 studs per stud of change centred on each joint
    J = c['joints_s']
    tot = s[-1]
    scale = tot / J[-1] if J[-1] > 0 else 1.0
    Js = [j * scale for j in J]
    w = np.zeros(len(s))
    for k in range(len(c['widths'])):
        m = (s >= Js[k] - 1e-6) & (s <= Js[k + 1] + 1e-6)
        w[m] = c['widths'][k]
    for k in range(1, len(c['widths'])):
        dw = c['widths'][k] - c['widths'][k - 1]
        if abs(dw) < 0.5:
            continue
        L = min(max(abs(dw) * 4.0, 20.0), 90.0)
        lo, hi = Js[k] - L / 2, Js[k] + L / 2
        m = (s > lo) & (s < hi)
        f = np.clip((s[m] - lo) / L, 0, 1)
        f = f * f * (3 - 2 * f)
        w[m] = c['widths'][k - 1] + dw * f
    N = np.stack([-T[:, 1], T[:, 0]], axis=1)
    Lft = Q + N * (w[:, None] / 2)
    Rgt = Q - N * (w[:, None] / 2)
    poly = clean(Polygon(np.vstack([Lft, Rgt[::-1]])))
    # bends sharper than the ribbon allows fold the inner offset: make_valid keeps the folded loops; the union with the
    # centreline buffer guarantees the full corridor
    core = LineString(Q).buffer(float(w.min()) / 2, cap_style='flat', join_style='round')
    return clean(unary_union([poly, core])), Q, T, w / 2, s


def arm_dir(rib, cid, end, d=12.0):
    poly, Q, T, hw, s = rib[cid]
    if end == 'a':
        k = int(min(np.searchsorted(s, d), len(Q) - 1))
        return unit(Q[k] - Q[0])
    k = int(max(np.searchsorted(s, s[-1] - d), 0))
    return unit(Q[k] - Q[-1])


def is_intersection(G, n, arms, rib, lo=50.0, hi=130.0):
    """a node is an intersection (gets a junction zone, kerb returns, stop lines, crossings) when two of its arms meet
    at 50..130 deg; merges / diverges / carriageway splits (all arms within 50 deg of a continuation or sibling) are
    not: their markings run through and the gore becomes an island"""
    ds = [arm_dir(rib, c, e) for c, e in arms]
    for i in range(len(ds)):
        for j in range(i + 1, len(ds)):
            a = math.degrees(math.acos(max(-1.0, min(1.0, float(ds[i] @ ds[j])))))
            if lo <= a <= hi:
                return True
    return False


# ---- 2. junction zones -------------------------------------------------------------------------------------------
def junction_zones(G, chains, rib, area, cfg):
    """[zone dict(nodes, poly, arms=[(chain, end, mouth_s, point, dir_into_junction, half_width)])]"""
    by_node = defaultdict(list)
    for c in chains:
        by_node[c['a']].append((c['id'], 'a'))
        by_node[c['b']].append((c['id'], 'b'))
    # also chains passing THROUGH a junction node in their middle cannot happen (chains break at deg != 2)
    zones = []
    for n, arms in by_node.items():
        if G['deg'][n] < 3 or n not in G['nodes']:
            continue
        c0 = np.asarray(G['nodes'][n], float)
        if not area.buffer(60).contains(Point(c0)):
            continue
        if not is_intersection(G, n, arms, rib):
            continue
        out = []
        for cid, end in arms:
            poly, Q, T, hw, s = rib[cid]
            if end == 'b':
                Q, T, hw, s = Q[::-1], -T[::-1], hw[::-1], (s[-1] - s)[::-1]
            others = [rib[o][0] for o, _ in arms if o != cid]
            oth = unary_union(others).buffer(cfg['mouth_pad']) if others else Polygon()
            ms = 0.0
            for k in range(len(Q)):
                if s[k] > cfg['mouth_cap']:
                    break
                nrm = np.array([-T[k][1], T[k][0]])
                cs = LineString([tuple(Q[k] + nrm * hw[k]), tuple(Q[k] - nrm * hw[k])])
                ms = s[k]
                if not cs.intersects(oth) and s[k] >= hw.max() * 0.5:
                    break
            k = int(np.searchsorted(s, ms))
            k = min(k, len(Q) - 1)
            out.append(dict(chain=cid, end=end, s=float(ms), p=Q[k], t=-T[k], hw=float(hw[k]), k=k))
        pts = [tuple(c0)]
        for a in out:
            nrm = np.array([-a['t'][1], a['t'][0]])
            pts += [tuple(a['p'] + nrm * a['hw']), tuple(a['p'] - nrm * a['hw'])]
        zones.append(dict(nodes=[n], poly=MultiPoint(pts).convex_hull, arms=out))
    # merge touching zones into complexes (dual carriageway junctions, slip-road clusters)
    merged = True
    while merged:
        merged = False
        for i in range(len(zones)):
            for j in range(i + 1, len(zones)):
                if zones[i]['poly'].buffer(cfg['cluster_gap']).intersects(zones[j]['poly']):
                    zi, zj = zones[i], zones.pop(j)
                    zi['nodes'] += zj['nodes']
                    zi['poly'] = unary_union([zi['poly'], zj['poly']])
                    zi['arms'] += zj['arms']
                    merged = True
                    break
            if merged:
                break
    for z in zones:
        # arms whose chain has both ends in the same complex are internal links (no mouth)
        cnt = Counter(a['chain'] for a in z['arms'])
        z['internal'] = sorted(c for c, k in cnt.items() if k > 1)
        z['arms'] = [a for a in z['arms'] if cnt[a['chain']] == 1 and not z['poly'].buffer(-0.5).contains(Point(a['p']))]
        z['poly'] = clean(z['poly'])
    return zones


def junction_field(chains, rib, Z, cfg):
    """the junction polygon for the marking rule: the intersection complexes Z plus every place where two carriageways
    share asphalt while running at more than `conflict_deg` to each other (merging slip roads, crossing links, the
    merged field between Pattaya Klang and the slip roads). No lane / centre / edge markings inside it; stop lines and
    zebras sit at its boundary."""
    parts = [Z]
    ids = [c['id'] for c in chains]
    tree = STRtree([rib[i][0] for i in ids])
    for a, i in enumerate(ids):
        for b in tree.query(rib[i][0]):
            j = ids[int(b)]
            if j <= i:
                continue
            inter = rib[i][0].intersection(rib[j][0])
            for q in polys(inter):
                if q.area < 2.0:
                    continue
                c = np.array([q.centroid.x, q.centroid.y])
                ti = rib[i][2][int(np.argmin(np.linalg.norm(rib[i][1] - c, axis=1)))]
                tj = rib[j][2][int(np.argmin(np.linalg.norm(rib[j][1] - c, axis=1)))]
                ang = math.degrees(math.acos(min(1.0, abs(float(ti @ tj)))))
                if ang > cfg['conflict_deg']:
                    parts.append(q)
    J = unary_union(parts)
    return clean(closing(J, cfg['field_close']))


# ---- 3. surfaces ---------------------------------------------------------------------------------------------------
def closing(g, r):
    return g.buffer(r, quad_segs=8).buffer(-r, quad_segs=8)


def replace_sets(W, bbox_poly):
    """(old surfaces replaced, old surfaces kept) of the replaceable kinds: replaced = centroid inside and >= 50 %
    of the footprint inside the area"""
    rep, keep = [], []
    for s in W['surf']:
        if s['kind'] not in REPLACE_KINDS:
            continue
        p = s['poly']
        if not p.intersects(bbox_poly.buffer(200)):
            continue
        inside = p.intersection(bbox_poly).area
        if bbox_poly.contains(p.centroid) and inside >= 0.5 * p.area:
            rep.append(s)
        else:
            keep.append(s)
    return rep, keep


def seam_taper(S, area, kept_asphalt, cfg, keep_lanes=None):
    """inside `seam_band` of the area edge the new asphalt may only reach d studs (d = depth inside the area) beyond
    the asphalt that stays outside: a 45 deg taper to the old road ends"""
    band, step = cfg['seam_band'], cfg['seam_step']
    edge = area.exterior
    out = [S.intersection(area.buffer(-band))]
    outside = kept_asphalt.difference(area.buffer(-0.01))
    for k in range(int(band / step)):
        d0, d1 = k * step, (k + 1) * step
        ring = area.buffer(-d0).difference(area.buffer(-d1))
        allowed = outside.buffer(d1 + 0.5, quad_segs=4) if not outside.is_empty else Polygon()
        if keep_lanes is not None:
            allowed = allowed.union(keep_lanes)        # never less lane surface than the old road had at the seam
        out.append(S.intersection(ring).intersection(allowed))
    res = clean(unary_union(out))
    # smooth the 2-stud steps of the taper (opening then closing, 3 studs): a straight 45 deg edge
    near = area.exterior.buffer(band + 4)
    work = res.intersection(area.exterior.buffer(band + 12))          # smoothed beyond `near`, so its cut edge never shows
    sm = work.buffer(-3, join_style='round').buffer(3, join_style='round')
    sm = closing(sm, 3).intersection(work.buffer(0.01).union(sm))
    res = clean(unary_union([res.difference(near.buffer(-0.01)), sm.intersection(near)]))
    # overlap the kept parts by 0.5 at the edge so no hairline opens at the seam
    res = clean(unary_union([res, outside.buffer(0.5).intersection(area).intersection(edge.buffer(0.6)).intersection(S.buffer(4))]))
    return res


# ---- 4. markings ---------------------------------------------------------------------------------------------------
def dash_line(Q, s, offs_fn, dash, gap, phase=0.0):
    """dash segments along the offset polyline (one phase along the whole chain): [(a, b)]"""
    out = []
    period = dash + gap
    k0 = math.floor((s[0] - phase) / period)
    t = phase + k0 * period
    while t < s[-1]:
        a0, a1 = max(t, s[0]), min(t + dash, s[-1])
        if a1 - a0 > 1.0:
            out.append((offs_fn(a0), offs_fn(a1)))
        t += period
    return out


def offset_point_fn(Q, T, s, off):
    """f(arc) -> point at lateral offset off(arc) (callable or number) from the chain centreline"""
    def f(a):
        k = int(np.clip(np.searchsorted(s, a) - 1, 0, len(s) - 2))
        u = (a - s[k]) / max(s[k + 1] - s[k], 1e-9)
        p = Q[k] * (1 - u) + Q[k + 1] * u
        t = unit(T[k] * (1 - u) + T[k + 1] * u)
        o = off(a) if callable(off) else off
        return p + np.array([-t[1], t[0]]) * o
    return f


def seg_poly(a, b, w):
    p = world.seg_poly(a, b, w)
    return p


def line_polys(geom, w):
    out = []
    for l in lines_of(geom):
        if l.length > 0.6:
            out.append(l.buffer(w / 2, cap_style='flat', join_style='mitre', mitre_limit=2.0))
    return out


# ---- 5. collision --------------------------------------------------------------------------------------------------
def triangles(g, simplify=0.15):
    out = []
    for p in polys(g):
        p = p.simplify(simplify, preserve_topology=True)
        if p.is_empty or p.area < 0.05:
            continue
        tri = shapely.constrained_delaunay_triangles(p)
        for t in getattr(tri, 'geoms', []):
            if t.area > 0.02:
                out.append(t)
    return out


def wedge_parts(tri):
    """WedgeParts the builders make for a triangle (two, or one when the altitude foot is a corner)"""
    c = np.asarray(tri.exterior.coords)[:3]
    return max(1, len(world.rs.wedge_tris(c[0], c[1], c[2])))


# ---- 6. checks -----------------------------------------------------------------------------------------------------
def wheel_check(chains, rib, surfaces, area, cfg, inset=20.0):
    """car footprints (the 4 wheel contact points of RaceCarServer's DEFAULT_LAYOUT) on every lane centre of every
    chain, every wheel_step studs, inside the area minus `inset`: supported when a road-height surface is under every
    wheel (contact radius 0.05)"""
    inner = area.buffer(-inset)
    U = unary_union(surfaces).buffer(cfg['contact_r'])
    shapely.prepare(U)
    shapely.prepare(inner)
    res = dict(samples=0, unsupported=0, legs=0, bad=[], inset=inset)
    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        nl = max(min(c['lanes']), 1)
        # the car stays on its own carriageway: samples whose wheels would reach past the chain's end node (where the
        # lane turns into another chain) are left out, before and after alike
        reach = max(abs(lo) for _, lo in cfg['wheels']) + 1.0
        m = shapely.contains_xy(inner, Q[:, 0], Q[:, 1]) & (s >= reach) & (s <= s[-1] - reach)
        if not m.any():
            continue
        Qm, Tm, hm = Q[m], T[m], hw[m]
        N = np.stack([-Tm[:, 1], Tm[:, 0]], axis=1)
        for li in range(nl):
            res['legs'] += 1
            o = -hm + (li + 0.5) * 2 * hm / nl
            C = Qm + N * o[:, None]
            ok = np.ones(len(C), bool)
            for la, lo in cfg['wheels']:
                P = C + N * la + Tm * lo
                ok &= shapely.contains_xy(U, P[:, 0], P[:, 1])
            res['samples'] += int(len(C))
            res['unsupported'] += int((~ok).sum())
            for q in C[~ok][:max(0, 200 - len(res['bad']))]:
                res['bad'].append([round(float(q[0]), 1), round(float(q[1]), 1), c['id'], li])
    return res


# ---- main --------------------------------------------------------------------------------------------------------
def generate(W, cfg=None, log=print):
    cfg = dict(CFG, **(cfg or {}))
    bl = world.world_bbox_local(cfg['bbox_world'])
    area = box(*bl)
    G = W['graph']
    chains = chains_of(G, area)
    if cfg['lane_w']:
        for c in chains:
            c['widths'] = [l * cfg['lane_w'] if not (c['oneway'] is False and l == 1) else max(l * cfg['lane_w'], 2 * cfg['lane_w'])
                           for l in c['lanes']]
    rib = {c['id']: ribbon(c) for c in chains}
    zones = junction_zones(G, chains, rib, area, cfg)
    Z = unary_union([z['poly'] for z in zones]) if zones else Polygon()
    blds = unary_union([b['poly'] for b in W['blds'] if b['poly'].intersects(area.buffer(50))])
    # node hulls: where chains meet, the convex hull of their end cross-sections closes the notch that two flat ends
    # at different angles leave (inside the lane corridors, never wider than the arms)
    ends = defaultdict(list)
    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        for node, k in ((c['a'], 0), (c['b'], -1)):
            nrm = np.array([-T[k][1], T[k][0]])
            ends[node] += [tuple(Q[k] + nrm * hw[k]), tuple(Q[k] - nrm * hw[k])]
    hulls = [MultiPoint(v).convex_hull for n, v in ends.items() if len(v) >= 4]
    S0 = unary_union([rib[c['id']][0] for c in chains] + hulls).intersection(area.buffer(120))
    lane_corr = S0
    rep, keep = replace_sets(W, area)
    if cfg['design'] == 'A':
        # design A: keep the existing generator's parts (slab Parts = visual = collision) and fix its rules: discs,
        # aprons and fill triangles clipped to the lane corridor (no overhang, no blobs), node hulls close the notches;
        # merged slabs stay merged (the graph's hidden carriageways keep only what the old surface covered)
        old_slabs = [s_['poly'] for s_ in rep if s_['kind'] == 'road']
        fills = [s_['poly'] for s_ in rep if s_['kind'] == 'fill']
        discs = [s_['poly'] for s_ in rep if s_['kind'] in ('junction', 'joint', 'apron')]
        core = clean(unary_union(old_slabs + [unary_union(fills + discs).intersection(S0.buffer(0.5))] +
                                 [h.intersection(unary_union(old_slabs).buffer(13)) for h in hulls]))
        core = clean(core.union(unary_union([s_['poly'] for s_ in keep if s_['kind'] == 'road']).intersection(area.buffer(5))))
        base = core
    else:
        old_slabs = []
        base = S0
    # kerb-return fillets inside the junction complexes only
    fil = closing(base, cfg['kerb_r']).difference(base).intersection(Z.buffer(cfg['kerb_r']))
    S1 = clean(unary_union([base, fil]))
    # islands: slivers between carriageways and small enclosed holes
    gaps = closing(S1, cfg['island_gap']).difference(S1)
    holes = [Polygon(r) for p in polys(S1) for r in p.interiors]
    small = unary_union([h for h in holes if h.area < cfg['island_hole_max']] + [gaps]) if holes or not gaps.is_empty else Polygon()
    islands = clean(small.difference(blds.buffer(0.5)))
    S1 = clean(S1.difference(blds.buffer(1.0)))
    bld_cut = float(unary_union([rib[c['id']][0] for c in chains]).intersection(area).intersection(blds.buffer(1.0)).area)
    # the seam
    kept_asphalt = unary_union([s['poly'] for s in keep if s['kind'] in world.ROAD_KINDS])
    old_all = unary_union([s_['poly'] for s_ in rep + keep if s_['kind'] in world.ROAD_KINDS])
    S = seam_taper(S1.intersection(area), area, kept_asphalt, cfg, keep_lanes=old_all.intersection(S0).buffer(0.3))
    islands = clean(islands.intersection(area.buffer(-2)).difference(S))
    kept_walk = unary_union([s['poly'] for s in keep if s['kind'] in ('sidewalk', 'corner')])
    kept_any = unary_union([kept_asphalt, kept_walk])
    # sidewalks + kerbs
    paved = unary_union([S, islands])
    walk = paved.buffer(cfg['sidewalk_w'], quad_segs=8).difference(paved).difference(blds.buffer(0.5))
    walk = walk.difference(kept_any.difference(area.buffer(-0.01)).buffer(0.2)).intersection(area)
    # never pave the far side of the area edge seam where the old road continues
    walk = clean(walk.difference(kept_asphalt.buffer(cfg['sidewalk_w'] + 1).intersection(area.exterior.buffer(cfg['seam_band']))))
    # the approved shoulder pilot stays flush: no sidewalk on top of a shoulder / taper / gap piece (it reads as a
    # concrete gutter between the asphalt and the kerb, and every wheel footprint it supports keeps its support)
    shoulders = unary_union([s_['poly'] for s_ in W['surf'] if s_['kind'] in world.SHOULDER_KINDS and s_['poly'].intersects(area)])
    if cfg['keep_shoulders_flush'] and not shoulders.is_empty:
        walk = clean(walk.difference(shoulders.difference(S).buffer(0.05)))
        walk = clean(unary_union([q for q in polys(walk) if q.area > 4.0]))
    kerb = clean(walk.intersection(paved.buffer(cfg['kerb_w'])))
    island_kerb = clean(islands.difference(islands.buffer(-cfg['kerb_w'])))
    # islands wider than 2 x (kerb + 2) get a planted (grass) middle, the rest is paved
    green = clean(unary_union([q for q in polys(islands.buffer(-(cfg['kerb_w'] + 2.0))) if q.area > 60]))

    # ---- markings
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
    vor = shapely.voronoi_polygons(MultiPoint(seeds), extend_to=area.buffer(400), ordered=True)
    cells = defaultdict(list)
    for lab, cell in zip(labels, vor.geoms):
        cells[lab].append(cell)
    own = {lab: clean(unary_union(v).buffer(0.05, join_style='mitre').buffer(-0.05, join_style='mitre').intersection(rib[lab][0]))
           for lab, v in cells.items()}
    inner_asph = S.buffer(-1.0)
    J = junction_field(chains, rib, Z, cfg)
    noZ = J.buffer(1.0)
    seam_cut = area.exterior.buffer(3.0)
    marks = []

    def add(kind, geom, w):
        g = geom.intersection(inner_asph).difference(noZ).difference(seam_cut).difference(islands.buffer(0.5))
        for l in lines_of(g):
            if l.length > (0.6 if kind in ('stop', 'zebra') else 3.0 if kind == 'lane' else 5.0):
                marks.append(dict(kind=kind, poly=l.buffer(w / 2, cap_style='flat', join_style='mitre', mitre_limit=2.0), line=l))

    for c in chains:
        poly, Q, T, hw, s = rib[c['id']]
        own_c = own.get(c['id'], Polygon()).buffer(-0.8)
        nl = max(min(c['lanes']), 1)
        bounds = []
        if c['oneway']:
            bounds = [('lane', (lambda k: (lambda a, k=k: (k - nl / 2) * 2 * np.interp(a, s, hw) / nl))(k)) for k in range(1, nl)]
        else:
            bounds = [('centre', lambda a: cfg['centre_gap'] / 2), ('centre', lambda a: -cfg['centre_gap'] / 2)]
            bounds += [('lane', (lambda k, sg: (lambda a, k=k, sg=sg: sg * k * 2 * np.interp(a, s, hw) / nl))(k, sg))
                       for k in range(1, nl // 2) for sg in (1, -1)]
        for kind, off in bounds:
            f = offset_point_fn(Q, T, s, off)
            if kind == 'centre':
                pts = [tuple(f(a)) for a in s]
                g = LineString(pts).intersection(own_c)
                add('centre', g, 0.45)
            else:
                segs = dash_line(Q, s, f, cfg['dash'], cfg['dash_gap'])
                g = unary_union([LineString([tuple(a), tuple(b)]) for a, b in segs]).intersection(own_c) if segs else Polygon()
                add('lane', g, cfg['line_w'])
    # separators between carriageways that share asphalt
    ids = sorted(own)
    tree = STRtree([own[i] for i in ids])
    for ii, i in enumerate(ids):
        for jj in tree.query(own[i].buffer(0.5)):
            j = ids[int(jj)]
            if j <= i:
                continue
            A, B = chains[i], chains[j]
            shared = own[i].boundary.intersection(own[j].buffer(0.05)).intersection(own[j].boundary.buffer(0.05))
            shared = shapely.line_merge(unary_union(lines_of(shared))) if not shared.is_empty else shared
            if shared.is_empty:
                continue
            # direction sense: compare tangents near the shared line
            mid = shared.interpolate(0.5, normalized=True) if hasattr(shared, 'interpolate') else None
            if mid is None:
                continue
            ta = rib[i][2][int(np.argmin(np.linalg.norm(rib[i][1] - [mid.x, mid.y], axis=1)))]
            tb = rib[j][2][int(np.argmin(np.linalg.norm(rib[j][1] - [mid.x, mid.y], axis=1)))]
            opposite = (not A['oneway']) or (not B['oneway']) or float(ta @ tb) < 0
            if opposite:
                for d in (-cfg['centre_gap'] / 2, cfg['centre_gap'] / 2):
                    for l in lines_of(shared):
                        try:
                            # the Voronoi split is a zigzag at seed spacing: straightened before it is drawn
                            add('centre', l.simplify(cfg['separator_simplify']).offset_curve(d), 0.45)
                        except Exception:
                            pass
            # same-direction carriageways sharing asphalt (a slip road beside the main road): no separator line; each
            # keeps its own lane dashes (a jagged split line read as stray fragments)
    # edge lines: only along kerbs (asphalt edges that meet a sidewalk or an island), never along the seam taper
    walk_or_island = unary_union([walk, islands, kept_walk])
    kerbside = walk_or_island.buffer(cfg['edge_inset'] + 1.5)
    for q in polys(S.buffer(-cfg['edge_inset'])):
        for ring in [q.exterior] + list(q.interiors):
            add('edge', LineString(ring.coords).intersection(kerbside), cfg['line_w'])

    # ---- crossings + stop lines (junction legs only)
    evidence = [np.array(c['row'][:2]) for c in W['crossings']]
    crossings, stops, quads = [], [], []
    paved_ok = unary_union([S, islands]).buffer(0.1)
    for zi, z in enumerate(zones):
        others = unary_union([q['poly'] for qi, q in enumerate(zones) if qi != zi]) if len(zones) > 1 else Polygon()
        # stop lines and zebras stand at this zone's boundary, never inside the rest of the junction field
        others = unary_union([others, J.difference(z['poly'].buffer(2.0))])
        for a in z['arms']:
            c = chains[a['chain']]
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
            if has_ev and kk < len(Qa) - 1 and area.buffer(-cfg['seam_band'] / 2).contains(Point(Qa[kk])):
                p, t = Qa[kk], Ta[kk]
                across = np.array([-t[1], t[0]])
                ray = LineString([tuple(p - across * 220), tuple(p + across * 220)])
                segs = sorted([g for g in lines_of(ray.intersection(S)) if g.length > 0.5], key=lambda g: ray.project(Point(g.coords[0])))
                idx = [i for i, g in enumerate(segs) if g.distance(Point(p)) < 0.6]
                if idx:
                    lo = hi = idx[0]
                    gap = lambda u, v: LineString([segs[u].coords[-1], segs[v].coords[0]])
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
            # stop line: inbound lanes, 2 studs before the crossing (or 2 studs outside the mouth)
            inbound = (a['end'] == 'b') if c['oneway'] else True
            sdist = (dist + cfg['zebra_depth'] / 2 + 2.0) if keep_x else mouth_s + 2.0
            # the stop line moves out along the leg (up to 60 studs) until it is clear of the junction field
            for step in range(31):
                ks = int(np.searchsorted(sa, sdist + 2.0 * step))
                if not (inbound and ks < len(Qa) - 1 and area.buffer(-cfg['seam_band'] / 2).contains(Point(Qa[ks]))):
                    break
                ps, ts = Qa[ks], Ta[ks]
                nrm = np.array([-ts[1], ts[0]])
                h = float(ha[ks])
                if c['oneway']:
                    q1, q2 = ps + nrm * (h - 1.2), ps - nrm * (h - 1.2)
                else:
                    lft = left_of(-ts)          # drive on the left: inbound lanes are on the driver's left
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
        across = unit(x['e2'] - x['e1'])
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
    # remove lane marks under zebras / stop lines
    block = unary_union([m['poly'] for m in xmarks + stops]).buffer(1.0) if xmarks or stops else Polygon()
    marks = [dict(m, poly=m['poly'].difference(block)) for m in marks]
    marks = [m for m in marks if not m['poly'].is_empty and m['poly'].area > 0.2]
    marks += stops + xmarks

    # ---- collision
    # collision (invisible): the asphalt grown 0.3 (it tucks under the kerb / sidewalk edge) and simplified 0.25, as
    # constrained-Delaunay triangles (two WedgeParts each, flat top at 1.0); sidewalks and islands shrunk 0.3 (they
    # never reach over the asphalt) and simplified the same way. Fewer, larger parts than slabs + discs + fills.
    if cfg['design'] == 'A':
        # A: the kept slab Parts plus visible flat triangles (WedgeParts) for the rest: visual = collision, as today
        slab_u = unary_union(old_slabs) if old_slabs else Polygon()
        tris = triangles(S.difference(slab_u).buffer(0.05, join_style='mitre').simplify(cfg['coll_simplify']), simplify=0)
    else:
        tris = triangles(S.buffer(cfg['coll_slack'], join_style='mitre').simplify(cfg['coll_simplify']), simplify=0)
    walk_tris = triangles(walk.buffer(-cfg['coll_slack'], join_style='mitre').simplify(cfg['coll_simplify']), simplify=0)
    isl_tris = triangles(islands.buffer(-cfg['coll_slack'], join_style='mitre').simplify(cfg['coll_simplify']), simplify=0)
    coll_asphalt = unary_union(tris + old_slabs)
    pilot = dict(cfg={k: v for k, v in cfg.items() if k != 'wheels'}, area=area, chains=chains, rib=rib, zones=zones,
                 layers=dict(asphalt=[S], sidewalk=[walk], kerb=[kerb, island_kerb], island=[islands], median=[green]),
                 S=S, walk=walk, kerb=kerb, islands=islands, green=green, marks=marks, crossings=crossings, tris=tris,
                 walk_tris=walk_tris, isl_tris=isl_tris, coll_asphalt=coll_asphalt, replaced=rep, kept=keep,
                 kept_asphalt=kept_asphalt, lane_corridor=lane_corr, design=cfg['design'], old_slabs=old_slabs, shoulders=shoulders, blds=blds, Z=Z, J=J, bld_cut=bld_cut, own=own)
    pilot['checks'] = checks(W, pilot, cfg)
    return pilot


def part_counts(W, P):
    rep = P['replaced']
    area = P['area']
    before = Counter()
    for s in rep:
        before[s['kind']] += s.get('parts', 1)
    rep_marks = [m for m in W['marks'] if area.contains(m['poly'].centroid)]
    rep_x = [c for c in W['crossings'] if area.contains(Point(c['row'][0], c['row'][1]))]
    before['markings'] = len(rep_marks)
    before['zebra'] = sum(len(c['bars']) for c in rep_x)
    after = Counter()
    after['collision_wedges'] = sum(wedge_parts(t) for t in P['tris'])
    after['sidewalk_wedges'] = sum(wedge_parts(t) for t in P['walk_tris'])
    after['island_wedges'] = sum(wedge_parts(t) for t in P['isl_tris'])
    tiles = set()
    for g in [P['S'], P['walk'], P['islands']] + [m['poly'] for m in P['marks']]:
        for p in polys(g):
            x0, z0, x1, z1 = p.bounds
            for tx in range(math.floor(x0 / 128), math.floor(x1 / 128) + 1):
                for tz in range(math.floor(z0 / 128), math.floor(z1 / 128) + 1):
                    if box(tx * 128, tz * 128, tx * 128 + 128, tz * 128 + 128).intersects(p):
                        tiles.add((tx, tz))
    if P['design'] == 'A':
        after['slab_parts'] = len(P['old_slabs'])          # visual = collision Parts, markings are Parts too
        after['marking_parts'] = len(P['marks'])
    else:
        after['visual_meshparts'] = len(tiles) * 2      # one asphalt+markings mesh, one sidewalk/kerb/island mesh per tile
    after_parts_alt = Counter(markings_as_parts=sum(1 for m in P['marks']))
    shoulders = sum(s.get('parts', 1) for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS and area.intersects(s['poly']))
    return dict(before_replaced=dict(before), before_replaced_total=int(sum(before.values())),
                after=dict(after), after_total=int(sum(after.values())),
                after_if_markings_are_parts=int(sum(after.values()) + after_parts_alt['markings_as_parts']),
                shoulder_parts_kept_untouched=int(shoulders),
                visual_triangles=int(sum(len(triangles(g)) for g in [P['S'], P['walk'], P['islands']])))


def checks(W, P, cfg):
    area, S = P['area'], P['S']
    inner = area.buffer(-20)
    # wheel support: new collision + kept old road surfaces + shoulders, vs before: old surfaces + shoulders
    should = [s['poly'] for s in W['surf'] if s['kind'] in world.SHOULDER_KINDS]
    old_road = [s['poly'] for s in W['surf'] if s['kind'] in world.ROAD_KINDS]
    kept_road = [s['poly'] for s in P['kept'] if s['kind'] in world.ROAD_KINDS]
    after_surf = [P['coll_asphalt']] + kept_road + should
    before_surf = old_road + should
    ins = cfg['seam_band'] + 10.0         # outside the seam band (+ the car's half length): the lanes the pilot owns
    wa = wheel_check(P['chains'], P['rib'], after_surf, area, cfg, inset=ins)
    wb = wheel_check(P['chains'], P['rib'], before_surf, area, cfg, inset=ins)
    wa_all = wheel_check(P['chains'], P['rib'], after_surf, area, cfg, inset=4.0)
    wb_all = wheel_check(P['chains'], P['rib'], before_surf, area, cfg, inset=4.0)
    vis_no_coll = S.intersection(inner).difference(P['coll_asphalt'].buffer(0.05)).area
    coll_outside_vis = P['coll_asphalt'].difference(unary_union([S, P['walk'], P['islands']]).buffer(0.35)).area
    paved = unary_union([S, P['walk'], P['islands']])
    bld_overlap = paved.intersection(P['blds']).area
    # meaningless asphalt: outside every lane corridor and outside the junction complexes (fillets are in the complex)
    meaningless = S.difference(P['lane_corridor'].buffer(1.0)).difference(P['Z'].buffer(P['cfg']['kerb_r'])).area
    fillet = S.difference(P['lane_corridor'].buffer(1.0)).area
    # overlaps between visual pieces: by construction one polygon per layer; check layer pairs
    ov = sum(a.intersection(b).area for a, b in ((S, P['walk']), (S, P['islands']), (P['walk'], P['islands'])))
    # markings: on asphalt, coverage of expected lane boundaries outside junction complexes
    bridged = []
    for m in P['marks']:
        l = m.get('line')
        if l is None or m['kind'] not in ('lane', 'centre', 'edge'):
            continue
        c0, c1 = np.asarray(l.coords[0]), np.asarray(l.coords[-1])
        ext = cfg['dash_gap'] / 2 + 0.5 if m['kind'] == 'lane' else 0.5
        if len(l.coords) == 2:
            d = unit(c1 - c0)
            bridged.append(LineString([tuple(c0 - d * ext), tuple(c1 + d * ext)]))
        else:
            bridged.append(l)
    mk = unary_union(bridged).buffer(1.5, cap_style='flat') if bridged else Polygon()
    shapely.prepare(mk)
    Zc = P['J'].buffer(cfg['zebra_depth'] + 6)
    S2 = S.buffer(-2)
    for g in (inner, Zc, S2):
        shapely.prepare(g)
    off_asphalt = sum(m['poly'].difference(S.buffer(0.05)).area for m in P['marks'])
    cov_n = cov_k = 0
    runs = []
    for c in P['chains']:
        poly, Q, T, hw, s = P['rib'][c['id']]
        nl = max(min(c['lanes']), 1)
        offs = [lambda a, k=k: (k - nl / 2) * 2 * np.interp(a, s, hw) / nl for k in range(1, nl)] if c['oneway'] else \
            [lambda a: 0.5] + [lambda a, k=k, sg=sg: sg * k * 2 * np.interp(a, s, hw) / nl for k in range(1, nl // 2) for sg in (1, -1)]
        for off in offs:
            f = offset_point_fn(Q, T, s, off)
            own_c = P['own'].get(c['id'], Polygon()).buffer(-1.0)
            shapely.prepare(own_c)
            for a in np.arange(s[0], s[-1], 4.0):
                p = Point(f(a))
                if not inner.contains(p) or Zc.contains(p) or not S2.contains(p):
                    continue
                if not own_c.contains(p):
                    continue       # this boundary lies inside another carriageway's share (shared asphalt): separator drawn instead
                cov_n += 1
                cov_k += int(mk.contains(p))
    xs = []
    for x in P['crossings']:
        ang = math.degrees(math.acos(min(1.0, abs(float(unit(x['e2'] - x['e1']) @ x['t'])))))
        xs.append(dict(name=x['name'], world=[round(float(x['p'][0]) + world.ORIGIN[0], 1), round(float(x['p'][1]), 1)],
                       span=round(x['span'], 1), bars=len(x['bars']), lands=x['lands'], perp_err_deg=round(abs(90 - ang), 2),
                       mouth_s=round(x['mouth_s'], 1), evidence=x['evidence']))
    return dict(
        wheel_after=dict((k, v) for k, v in wa.items() if k != 'bad'), wheel_before=dict((k, v) for k, v in wb.items() if k != 'bad'),
        wheel_after_bad=wa['bad'][:50], wheel_before_bad=wb['bad'][:50],
        wheel_after_incl_seam=dict((k, v) for k, v in wa_all.items() if k != 'bad'),
        wheel_before_incl_seam=dict((k, v) for k, v in wb_all.items() if k != 'bad'),
        visual_without_collision=round(vis_no_coll, 2), collision_outside_visual=round(coll_outside_vis, 2),
        building_overlap=round(bld_overlap, 2), lane_corridor_cut_by_buildings=round(P['bld_cut'], 1),
        meaningless_asphalt=round(meaningless, 1), fillet_and_seam_asphalt=round(fillet, 1),
        asphalt=round(S.area, 0), sidewalk=round(P['walk'].area, 0), islands=round(P['islands'].area, 0),
        layer_overlap=round(ov, 2), marking_off_asphalt=round(off_asphalt, 2),
        marks_in_junction=round(sum(m['poly'].intersection(P['J'].buffer(-0.5)).area for m in P['marks'] if m['kind'] in ('lane', 'centre', 'edge')), 2),
        junction_field_area=round(P['J'].area, 0),
        lane_boundary_samples=cov_n, lane_boundary_covered=cov_k, lane_boundary_coverage=round(cov_k / cov_n, 3) if cov_n else None,
        crossings=xs, crossings_all_on_legs=all(all(x['lands']) for x in xs) if xs else None,
        zones=[dict(nodes=z['nodes'], arms=len(z['arms']), area=round(z['poly'].area)) for z in P['zones']],
    )


# ---- export ----------------------------------------------------------------------------------------------------
def rnd(v, n=2):
    return round(float(v), n)


def poly_rings(p):
    return dict(ext=[[rnd(x), rnd(z)] for x, z in p.exterior.coords[:-1]], holes=[[[rnd(x), rnd(z)] for x, z in r.coords[:-1]] for r in p.interiors])


def tri_rows(tris):
    out = []
    for t in tris:
        c = np.asarray(t.exterior.coords)[:3]
        out.append([rnd(v) for v in c.flatten()])
    return out


def export(W, P, path):
    cfg = P['cfg']
    pc = part_counts(W, P)
    data = dict(
        note='OFFLINE PREVIEW DATA (tools/roadvis/junction.py). Not built in Studio. Map-local studs; world = map + (20000, 0, 0). '
             'Map data (c) OpenStreetMap contributors, ODbL 1.0.',
        name=cfg['name'], bbox_world=list(cfg['bbox_world']), origin=list(world.ORIGIN),
        tops=dict(asphalt=cfg['asphalt_top'], visual_lift=cfg['visual_lift'], sidewalk=cfg['sidewalk_top'], island=cfg['island_top']),
        collision=dict(
            asphalt_tris=tri_rows(P['tris']), sidewalk_tris=tri_rows(P['walk_tris']), island_tris=tri_rows(P['isl_tris'])),
        visual=dict(asphalt=[poly_rings(p) for p in polys(P['S'])], sidewalk=[poly_rings(p) for p in polys(P['walk'])],
                    kerb=[poly_rings(p) for p in polys(unary_union(P['layers']['kerb']))], island=[poly_rings(p) for p in polys(P['islands'])],
                    marks=[dict(kind=m['kind'], **poly_rings(p)) for m in P['marks'] for p in polys(m['poly'])]),
        crossings=[dict(name=x['name'], p=[rnd(v) for v in x['p']], t=[rnd(v, 4) for v in x['t']], e1=[rnd(v) for v in x['e1']],
                        e2=[rnd(v) for v in x['e2']], bars=len(x['bars'])) for x in P['crossings']],
        replace=dict(note='old parts the pilot replaces (footprint centroid inside the area and >= 50 % inside); shoulder pieces are NOT replaced',
                     edges=sorted({W['edges'][s['edge']]['id'] for s in P['replaced'] if 'edge' in s}),
                     discs=sorted({f"{s['kind']}:{s['node']}" for s in P['replaced'] if s['kind'] in ('junction', 'joint')}),
                     aprons=sorted({int(s['node']) for s in P['replaced'] if s['kind'] in ('apron', 'corner')})),
        chains=[dict(id=c['id'], name=c['name'], edges=c['edges'], oneway=c['oneway'], lanes=c['lanes'], widths=c['widths']) for c in P['chains']],
        parts=pc, checks=P['checks'],
    )
    txt = json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    data['sha1'] = hashlib.sha1(txt.encode('utf-8')).hexdigest()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'), default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    return data
