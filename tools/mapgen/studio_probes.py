"""Offline replicas of the leader's two Studio road probes (docs/ROAD_AUDIT_STUDIO.md), on the exported modules.

  .venv\\Scripts\\python tools\\mapgen\\studio_probes.py [--root <repo>]

kerb  - Sidewalk Parts whose centre lies inside another edge's Road Part (more than 1 stud inside its edge) and
        outside every Junction/Joint disc + 2 studs.
kink  - two Road Parts (each >= 6 studs long) meeting end to end (end-face centres within 1.5 studs) with a heading
        change of 35-150 deg and no disc whose centre is within its radius + 2 of the meeting point.
overlap - the slab-overlap probe (docs/ROAD_AUDIT_STUDIO.md, docs/ROAD_AUDIT.md "Dual carriageways and slip roads"):
        for every pair of intersecting Road Parts whose road Models have different names, the centreline of one Part is
        sampled every 4 studs; a sample counts when it lies inside the other Part (0.5 studs inside its edge) and
        outside every Junction/Joint disc (radius + 6). Model pairs with 2+ samples are findings. Fill triangles (road_fix
        rule D, WedgeParts with the attribute RoadFill) are not sampled; they never lie inside another road by
        construction. --overlap-all also counts pairs with the same road name.
Parts are rebuilt exactly as PattayaBuilder.stripe makes them (segment + bend stretch, segments <= 0.05 skipped), from
the slab pieces (hidden edges build none; cutA / cutB / hide shorten them: road_check.slab_pieces).
"""
import argparse, math, os, sys
from collections import defaultdict
import numpy as np
import shapely
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(__file__))
import road_check as rc  # noqa: E402
import road_fix as rfx  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def stripe_parts(pts, width):
    """(centre, unit dir, length, polygon) per Part, as PattayaBuilder.stripe"""
    n = len(pts)
    ext = [0.0] * n
    for j in range(1, n - 1):
        d1, d2 = rc.unit(pts[j] - pts[j - 1]), rc.unit(pts[j + 1] - pts[j])
        turn = math.acos(max(-1.0, min(1.0, float(d1 @ d2))))
        ext[j] = min(width / 2 * math.tan(turn / 2), width / 2)
    out = []
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        if math.hypot(*(b - a)) > 0.05:
            d = rc.unit(b - a)
            a2, b2 = a - d * ext[i], b + d * ext[i + 1]
            nrm = np.array([-d[1], d[0]]) * width / 2
            out.append(((a2 + b2) / 2, d, float(np.linalg.norm(b2 - a2)),
                        shapely.Polygon([a2 + nrm, b2 + nrm, b2 - nrm, a2 - nrm])))
    return out


def sidewalk_parts(e, jr):
    """(centre, side) of every Sidewalk Part buildEdge makes"""
    if e['sidewalk'] <= 0 or e.get('hidden'):
        return []
    ra, rb = rfx.end_trims(e, jr)
    sw = rc.trim(e['pts'], ra + e['sidewalk'] if ra > 0 else 0, rb + e['sidewalk'] if rb > 0 else 0)
    if sw is None:
        return []
    out = []
    for side in (-1, 1):
        if e.get('swSide') and e['swSide'] != side:
            continue
        for c, d, L, poly in stripe_parts(rc.offset(sw, side * (e['width'] + e['sidewalk']) / 2), e['sidewalk']):
            out.append((c, side, L))
    return out


def probes(edges, discs, jrs, min_len=6.0, end_tol=1.5, turn_lo=35.0, turn_hi=150.0):
    road, owner = [], []
    for i, e in enumerate(edges):
        for sp in rc.slab_pieces(e):
            for part in stripe_parts(sp, e['width']):
                road.append(part); owner.append(i)
    D = np.array([(x, z, r) for (x, z, r) in discs.values()])
    dtree = STRtree([shapely.Point(x, z).buffer(r + 2, 16) for x, z, r in D])
    inner = [p[3].buffer(-1.0) for p in road]
    itree = STRtree(inner)
    kerbs = []
    for i, e in enumerate(edges):
        for c, side, L in sidewalk_parts(e, jrs[e['ds']]):
            pt = shapely.Point(*c)
            hits = [k for k in itree.query(pt, predicate='within') if owner[k] != i]
            if hits and not len(dtree.query(pt, predicate='within')):
                kerbs.append({'edge': i, 'side': side, 'x': float(c[0]), 'z': float(c[1]), 'len': L, 'in': owner[hits[0]]})
    # kinks
    ends = []
    for k, (c, d, L, poly) in enumerate(road):
        if L >= min_len:
            ends.append((c - d * L / 2, k, -1))
            ends.append((c + d * L / 2, k, 1))
    E = np.array([p for p, _, _ in ends])
    etree = STRtree([shapely.Point(*p) for p in E])
    kinks, seen = [], set()
    for a_, (p, k, s) in enumerate(ends):
        for b_ in etree.query(shapely.Point(*p).buffer(end_tol)):
            q, k2, s2 = ends[b_]
            if k2 <= k or (k, k2) in seen or np.linalg.norm(q - p) > end_tol:
                continue
            d1 = road[k][1] * (1 if s == 1 else -1)          # direction arriving at the joint along part k
            d2 = road[k2][1] * (1 if s2 == -1 else -1)       # direction leaving the joint along part k2
            turn = math.degrees(math.acos(max(-1.0, min(1.0, float(d1 @ d2)))))
            if not (turn_lo <= turn <= turn_hi):
                continue
            m = (p + q) / 2
            if len(dtree.query(shapely.Point(*m), predicate='within')):
                continue
            seen.add((k, k2))
            kinks.append({'x': float(m[0]), 'z': float(m[1]), 'turn': turn, 'a': owner[k], 'b': owner[k2]})
    return kerbs, kinks


def overlaps(edges, discs, step=4.0, inset=0.5, disc_pad=6.0, same_name=False):
    """the slab-overlap probe (module docstring). Returns findings [{a, b, samples, x, z}] per model (edge) pair with
    2+ samples, a = the edge whose Part centreline was sampled (world x/z of the first sample)."""
    road, owner = [], []
    for i, e in enumerate(edges):
        for sp in rc.slab_pieces(e):
            for part in stripe_parts(sp, e['width']):
                road.append(part); owner.append(i)
    polys = [p[3] for p in road]
    inner = [p.buffer(-inset, join_style=2) for p in polys]
    tree = STRtree(polys)
    D = [(x, z, r) for (x, z, r) in discs.values()]
    dtree = STRtree([shapely.Point(x, z).buffer(r + disc_pad, 16) for x, z, r in D])
    hits = defaultdict(list)
    pa, pb = tree.query(polys, predicate='intersects')
    for k, k2 in zip(pa.tolist(), pb.tolist()):
        i, j = owner[k], owner[k2]
        if i == j:
            continue
        if not same_name and edges[i].get('label') == edges[j].get('label'):
            continue
        c, d, L, _ = road[k]
        ts = np.arange(-L / 2, L / 2 + 1e-9, step)
        P = c[None, :] + d[None, :] * ts[:, None]
        pts = shapely.points(P)
        inside = shapely.contains(inner[k2], pts)
        if not inside.any():
            continue
        free = np.ones(len(P), bool)
        di = dtree.query(pts, predicate='within')
        free[di[0]] = False
        for q in np.nonzero(inside & free)[0]:
            hits[(i, j)].append((float(P[q][0]), float(P[q][1])))
    out = []
    for (i, j), v in sorted(hits.items()):
        if len(v) >= 2:
            out.append({'a': i, 'b': j, 'samples': len(v), 'x': v[0][0] + 20000, 'z': v[0][1]})
    return out


def traffic_probe(edges, discs, traffic_path, step=10.0, inset=2.0):
    """ambient traffic (ReplicatedStorage.PattayaTraffic = build/bira/roblox_corridor/traffic.luau): every loop sampled
    every `step` studs; a sample is OFF when it lies on no road surface (slab, fill triangle or disc) and EDGE when it is
    within `inset` studs of the surface border (a car there hangs over the kerb). Returns (samples, off, edge, worst)."""
    import re
    surf = []
    for e in edges:
        surf += rc.slab_rects(e)
    surf += [shapely.Point(x, z).buffer(r, 32) for (x, z, r) in discs.values()]
    tree = STRtree(surf)
    inner = STRtree([g.buffer(-inset) for g in surf])
    text = open(traffic_path, encoding='utf-8').read()
    n = off = edge = 0
    worst = []
    for m in re.finditer(r'pts = \{([^}]*)\}', text):
        v = np.array([float(t) for t in m.group(1).split(',')]).reshape(-1, 2)
        P, _ = rfx_samples(v, step)
        pts = shapely.points(P)
        on = np.zeros(len(P), bool); on[tree.query(pts, predicate='intersects')[0]] = True
        ok = np.zeros(len(P), bool); ok[inner.query(pts, predicate='intersects')[0]] = True
        n += len(P); off += int((~on).sum()); edge += int((on & ~ok).sum())
        worst += [(float(P[k][0]) + 20000, float(P[k][1])) for k in np.nonzero(~on)[0][:3]]
    return n, off, edge, worst[:12]


def rfx_samples(p, step):
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1] + 1e-9, step)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1), t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--overlap-all', action='store_true', help='slab-overlap probe: also pairs with the same road name')
    a = ap.parse_args()
    edges, discs, jrs, _, _ = rfx.load(a.root)
    kerbs, kinks = probes(edges, discs, jrs)
    ov = overlaps(edges, discs, same_name=a.overlap_all)
    names = defaultdict(lambda: [0, 0])
    for f in ov:
        key = ' x '.join(sorted([edges[f['a']].get('label') or '?', edges[f['b']].get('label') or '?']))
        names[key][0] += 1; names[key][1] += f['samples']
    print(f'kerb parts inside another road: {len(kerbs)}; kinks without disc: {len(kinks)}; slab-overlap pairs '
          f'({"all names" if a.overlap_all else "different road names"}): {len(ov)} edge pairs, {sum(f["samples"] for f in ov)} samples '
          f'(~{4 * sum(f["samples"] for f in ov):,} studs), {len(names)} road-name pairs')
    for k, (n, smp) in sorted(names.items(), key=lambda kv: -kv[1][1])[:12]:
        print(f'  overlap {k}: {n} edge pairs, {smp * 4} studs')
    tp = os.path.join(a.root, 'build', 'bira', 'roblox_corridor', 'traffic.luau')
    if os.path.exists(tp):
        n, off, edge, worst = traffic_probe(edges, discs, tp)
        print(f'traffic loops (PattayaTraffic) sampled every 10 studs: {n:,} samples, {off} on no road surface, {edge} within 2 '
              f'studs of the road edge; first off-road samples: {[(round(x), round(z)) for x, z in worst[:6]]}')
    by = defaultdict(int)
    for k in kerbs:
        by[(edges[k['edge']]['ds'], edges[k['edge']]['id'], edges[k['in']]['id'])] += 1
    for k in kerbs[:10]:
        print(f"  kerb {edges[k['edge']]['id']} side {k['side']} in {edges[k['in']]['id']} at ({k['x'] + 20000:.0f}, {k['z']:.0f}) len {k['len']:.0f}")
    for k in sorted(kinks, key=lambda k: -k['turn'])[:10]:
        print(f"  kink {k['turn']:.0f} deg at ({k['x'] + 20000:.0f}, {k['z']:.0f}) {edges[k['a']]['id']} / {edges[k['b']]['id']}")
    return kerbs, kinks


if __name__ == '__main__':
    main()
