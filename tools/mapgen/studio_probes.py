"""Offline replicas of the leader's two Studio road probes (docs/ROAD_AUDIT_STUDIO.md), on the exported modules.

  .venv\\Scripts\\python tools\\mapgen\\studio_probes.py [--root <repo>]

kerb  - Sidewalk Parts whose centre lies inside another edge's Road Part (more than 1 stud inside its edge) and
        outside every Junction/Joint disc + 2 studs.
kink  - two Road Parts (each >= 6 studs long) meeting end to end (end-face centres within 1.5 studs) with a heading
        change of 35-150 deg and no disc whose centre is within its radius + 2 of the meeting point.
Parts are rebuilt exactly as PattayaBuilder.stripe makes them (segment + bend stretch, segments <= 0.05 skipped).
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
    if e['sidewalk'] <= 0:
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
        for part in stripe_parts(e['pts'], e['width']):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT)
    a = ap.parse_args()
    edges, discs, jrs, _, _ = rfx.load(a.root)
    kerbs, kinks = probes(edges, discs, jrs)
    print(f'kerb parts inside another road: {len(kerbs)}; kinks without disc: {len(kinks)}')
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
