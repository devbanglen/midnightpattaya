"""Offline road-seam scan (team12/quality, 2026-10-20): where can a car's suspension rays find a step, a gap or a tilt?

  .venv\\Scripts\\python tools\\qa\\road_seams.py                      # whole map, Sukhumvit at full resolution
  .venv\\Scripts\\python tools\\qa\\road_seams.py --build-root D:\\ROBLOXRACE\\build --out D:\\ROBLOXRACE\\build\\qa

Read-only: rebuilds the road surface exactly as the Studio builders do, from the EXPORTED data modules they consume,
and writes `road_seams.json` + `road_seams.csv` (ranked) to <build-root>/qa/. Nothing in build/ is changed.

Geometry (same ports as tools/mapgen/road_check.py, imported from there; Builder = ServerStorage.PattayaBuilder,
Aprons = ServerStorage.PattayaApronBuilder):
  slab      Builder.stripe: one Part per polyline segment, stretched at joints; top 1.00 (ROAD_TOP), 4 thick
            (slab pieces honour hidden / cutA / cutB / hide of road_fix rule D)
  fill      Builder.roadTriangle: flat triangle as two WedgeParts, top 1.00 (pieces <= 0.05 studs skipped as there)
  disc      Junction / Joint cylinders, top 0.99 (ROAD_TOP - ROAD_THICK/2 - 0.01 + 2)
  apron     Aprons.triangle / boxes, top 0.98 (manifest `apron.top`)
  sidewalk  Builder sidewalk strips, top 1.60 (ROAD_TOP + CURB)
  corner    Aprons corner fills, top 1.58 (manifest `corner.top`)
  terrain   everywhere else, surface y = -2 (3 studs below the road top)
Datasets: build/central_pattaya/roblox, build/pattaya_wide/roblox, build/bira/roblox_corridor, build/aprons/roblox.
World coordinates = map-local + ORIGIN (20000, 0, 0) (Builder.ORIGIN, Aprons.ORIGIN); y of the road top = 1.0.

Checks (classes in the output):
  tilt         every built Part's up axis vs vertical (stripes are CFrame.lookAt between two points at the same y,
               wedges CFrame.fromMatrix(xv = yv x zv) with horizontal yv / zv): roll / pitch > 2 deg
  step         consecutive Parts of one edge (and the parts meeting at every node) with different top heights > 0.3,
               or slope change > 6 deg between neighbours (the data has no y / elevation at all: tops are constants)
  gap          an ENCLOSED hole in the road-height surface (union of slab + fill + disc + apron) that no sidewalk /
               corner fill covers, at most 3 studs wide and 400 studs² (wider / larger holes are city blocks and
               medians): a suspension ray there falls to the terrain 3 studs lower. width = 2 x max inscribed radius.
               width > 0.5 -> `gap`, 0.05 .. 0.5 -> `sliver` (a ray can slip through; a wheel feels a twitch)
  end_gap      the end of a built slab piece (node, or cutA / cutB / hide boundary) followed by > 0.5 studs of open
               ground and then road again, on drive lines across the inner 90 % of the width (19 lines, marched
               4 studs in 0.05 steps); dead ends (degree 1) skipped
  narrowing    the same, but the open drive lines never meet road within 4 studs: the surface narrows or steps
               sideways at the end of the slab (one wheel runs off the edge if the car holds its lane)
  kerb         a raised surface (sidewalk 1.60 / corner fill 1.58) on a lane of a BUILT slab piece: wheel-track
               samples (Sukhumvit: every 1 stud along, every 1.5 studs across; other roads: every 2 studs along,
               5 tracks; tracks stay 1.5 studs inside the slab edge; piece ends excluded) 0.6 above the road.
               Clusters of samples (6-stud grid) are one finding; the raising surface is named.
  drop         wheel-track samples inside a built slab piece with no surface at all (should be 0 by construction)
               Hidden carriageways (road_fix rule D) are not scanned: their lane lines are traffic paths, the built
               surface there is the merged slab + fill triangles.
  zfight       overlapping road-height surfaces with tops < 0.05 apart but different (disc 0.99 / apron 0.98 under a
               slab 1.00): no bump, possible flicker; reported as a summary and per Sukhumvit spot, low rank
Sukhumvit = an edge whose Studio name (nameEn or name) is "Sukhumvit Road" / "ถนนสุขุมวิท" (the trunk); findings
within 60 studs of it are flagged `near_sukhumvit`. Ranking: severity x size, Sukhumvit x 3.
"""
import argparse, csv, json, math, os, re, sys
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'tools', 'mapgen'))
import road_check as rc  # noqa: E402  (PattayaBuilder ports: load_dataset, slab_pieces, stripe_rects, sidewalk_rects)

ORIGIN = (20000.0, 0.0, 0.0)
ROAD_TOP, DISC_TOP, TERRAIN = 1.0, 0.99, -2.0
SIDEWALK_TOP = 1.6
MAX_SEAM_W, MAX_SEAM_AREA = 3.0, 400.0   # enclosed holes wider / larger than this are blocks or medians
SUKHUMVIT = {'Sukhumvit Road', 'ถนนสุขุมวิท'}
DATASETS = [('central', 'central_pattaya/roblox'), ('wide', 'pattaya_wide/roblox'), ('corridor', 'bira/roblox_corridor')]


def find_build_root(arg):
    if arg:
        return os.path.abspath(arg)
    p = REPO
    for _ in range(6):                      # a worktree under <main>/.claude/worktrees/<name> has no build/ of its own
        if os.path.isdir(os.path.join(p, 'build', 'pattaya_wide')):
            return os.path.join(p, 'build')
        p = os.path.dirname(p)
    sys.exit('build/ not found; pass --build-root')


def world(x, z):
    return round(x + ORIGIN[0], 1), round(z + ORIGIN[2], 1)


# ---- Builder.roadTriangle / Aprons.triangle, ported (two right-triangle WedgeParts, skips <= 0.05) ------------------
def wedge_tris(a, b, c):
    """[(polygon, up_tilt_deg)] of the WedgeParts the builders make for triangle a-b-c"""
    a, b, c = np.asarray(a, float), np.asarray(b, float), np.asarray(c, float)
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    if bc > ab and bc >= ca:
        a, b, c = b, c, a
    elif ca > ab and ca > bc:
        a, b, c = c, a, b
    ln = np.linalg.norm(b - a)
    if ln < 0.05:
        return []
    d = (b - a) / ln
    foot = a + d * float((c - a) @ d)
    h = np.linalg.norm(c - foot)
    if h < 0.05:
        return []
    yv = np.array([c[0] - foot[0], 0.0, c[1] - foot[1]]) / h
    out = []
    for corner in (a, b):
        l = np.linalg.norm(foot - corner)
        if l > 0.05:
            zv = np.array([foot[0] - corner[0], 0.0, foot[1] - corner[1]]) / l
            xv = np.cross(yv, zv)
            n = np.linalg.norm(xv)
            tilt = math.degrees(math.acos(min(1.0, abs(xv[1]) / n))) if n > 0 else 90.0
            out.append((Polygon([corner, foot, c]), tilt))
    return out


def tri_rows(text, key):
    m = re.search(r'\n  ' + key + r' = \{([^}]*)\}', text)
    return [float(v) for v in m.group(1).split(',') if v.strip()] if m else []


def load_aprons(adir):
    man = open(os.path.join(adir, 'manifest.luau'), encoding='utf-8').read()
    tops = {k: float(re.search(k + r' = \{ top = ([\d.]+)', man).group(1)) for k in ('apron', 'corner')}
    out = []                                   # (poly, top, kind, junction, tilt)
    for f in sorted(os.listdir(adir)):
        if not (f.startswith('chunk_a') and f.endswith('.luau')):
            continue
        t = open(os.path.join(adir, f), encoding='utf-8').read()
        for kind, key, bkey in (('apron', 'aprons', 'apronBoxes'), ('corner', 'corners', 'cornerBoxes')):
            r = tri_rows(t, key)
            for i in range(0, len(r) - 6, 7):
                for poly, tilt in wedge_tris(r[i:i + 2], r[i + 2:i + 4], r[i + 4:i + 6]):
                    out.append((poly, tops[kind], kind, int(r[i + 6]), tilt))
            r = tri_rows(t, bkey)
            for i in range(0, len(r) - 6, 7):
                cx, cz, ux, uz, ln, w = r[i:i + 6]
                u = np.array([ux, uz]) / math.hypot(ux, uz)
                v = np.array([-u[1], u[0]])
                c = np.array([cx, cz])
                poly = Polygon([c + u * ln / 2 + v * w / 2, c - u * ln / 2 + v * w / 2, c - u * ln / 2 - v * w / 2, c + u * ln / 2 - v * w / 2])
                out.append((poly, tops[kind], kind, int(r[i + 6]), 0.0))
    return out


def is_sukhumvit(e):
    return (e.get('label') or '') in SUKHUMVIT


def polyline_samples(pts, step):
    """points every `step` along pts with unit tangents"""
    p = np.asarray(pts, float)
    seg = np.diff(p, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    keep = ln > 1e-6
    if not keep.any():
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
    s = np.concatenate([[0], np.cumsum(ln)])
    t = np.arange(0, s[-1] + 1e-9, step)
    xy = np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1)
    k = np.clip(np.searchsorted(s, t, side='right') - 1, 0, len(seg) - 1)
    tan = seg[k] / np.maximum(ln[k], 1e-9)[:, None]
    return xy, tan, t


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--build-root')
    ap.add_argument('--out', help='output folder (default <build-root>/qa)')
    ap.add_argument('--suk-step', type=float, default=1.0)
    ap.add_argument('--step', type=float, default=2.0)
    ap.add_argument('--top', type=int, default=40, help='findings printed')
    a = ap.parse_args()
    broot = find_build_root(a.build_root)
    out_dir = os.path.abspath(a.out or os.path.join(broot, 'qa'))
    os.makedirs(out_dir, exist_ok=True)

    # ---- load every surface -------------------------------------------------------------------------------------
    edges, surf = [], []                       # surf: dict(poly, top, kind, edge, info)
    discs_all, deg = [], defaultdict(int)
    tilt_max, tilt_bad = 0.0, []
    for tag, rel in DATASETS:
        d = os.path.join(broot, rel)
        if not os.path.isdir(d):
            print('missing dataset', d)
            continue
        es, discs, jr = rc.load_dataset(d)
        for e in es:
            e['ds'] = tag
            k = len(edges)
            edges.append(e)
            deg[e['a']] += 1
            deg[e['b']] += 1
            for pi, q in enumerate(rc.slab_pieces(e)):
                for si, r in enumerate(rc.stripe_rects(q, e['width'])):
                    surf.append({'poly': r, 'top': ROAD_TOP, 'kind': 'slab', 'edge': k, 'piece': pi, 'seg': si})
            v = e.get('fill') or []
            for i in range(0, len(v) - 5, 6):
                for poly, tilt in wedge_tris(v[i:i + 2], v[i + 2:i + 4], v[i + 4:i + 6]):
                    surf.append({'poly': poly, 'top': ROAD_TOP, 'kind': 'fill', 'edge': k})
                    if tilt > tilt_max:
                        tilt_max = tilt
                    if tilt > 2:
                        tilt_bad.append((poly.centroid, tilt, k))
            for r in rc.sidewalk_rects(e, jr):
                surf.append({'poly': r, 'top': SIDEWALK_TOP, 'kind': 'sidewalk', 'edge': k})
        for nid, (x, z, r) in discs.items():
            surf.append({'poly': Point(x, z).buffer(r, 32), 'top': DISC_TOP, 'kind': 'joint' if isinstance(nid, tuple) else 'disc',
                         'edge': -1, 'node': nid[1] if isinstance(nid, tuple) else nid})
            discs_all.append((x, z, r))
    adir = os.path.join(broot, 'aprons', 'roblox')
    if os.path.isdir(adir):
        for poly, top, kind, junction, tilt in load_aprons(adir):
            surf.append({'poly': poly, 'top': top, 'kind': kind, 'edge': -1, 'node': junction})
            tilt_max = max(tilt_max, tilt)
            if tilt > 2:
                tilt_bad.append((poly.centroid, tilt, -1))
    print(f'loaded {len(edges):,} edges, {len(surf):,} surface pieces from {broot}')
    polys = [s['poly'] for s in surf]
    tops = np.array([s['top'] for s in surf])
    tree = STRtree(polys)
    road_idx = np.nonzero(tops < 1.3)[0]
    raised_idx = np.nonzero(tops >= 1.3)[0]

    suk_edges = [k for k, e in enumerate(edges) if is_sukhumvit(e)]
    suk_lines = shapely.union_all([shapely.LineString(edges[k]['pts']) for k in suk_edges]) if suk_edges else None
    suk_zone = suk_lines.buffer(60) if suk_lines is not None else None
    print(f'Sukhumvit edges: {len(suk_edges)} ({sum(1 for k in suk_edges if edges[k]["hidden"])} hidden carriageways), '
          f'{sum(shapely.length(shapely.LineString(edges[k]["pts"])) for k in suk_edges):,.0f} studs of centreline')

    def top_at(P, inset=0.0):
        """highest surface top over each point (terrain -2 where none); inset > 0 ignores a boundary band"""
        pts = shapely.points(P[:, 0], P[:, 1])
        res = np.full(len(P), TERRAIN)
        qi, si = tree.query(pts, predicate='intersects')
        if inset > 0 and len(qi):
            ok = shapely.distance(shapely.boundary(np.array(polys, dtype=object)[si]), pts[qi]) > inset
            qi, si = qi[ok], si[ok]
        np.maximum.at(res, qi, tops[si])
        return res

    def top_owner(P):
        """(highest top, index into surf of the surface giving it or -1) per point"""
        pts = shapely.points(P[:, 0], P[:, 1])
        res = np.full(len(P), TERRAIN)
        who = np.full(len(P), -1)
        qi, si = tree.query(pts, predicate='intersects')
        order = np.argsort(tops[si], kind='stable')      # ascending: the last write per point is the highest
        qi, si = qi[order], si[order]
        res[qi] = tops[si]
        who[qi] = si
        return res, who

    findings = []

    def add(cls, x, z, size, severity, why, e=None, extra=None):
        near = bool(suk_zone is not None and suk_zone.contains(Point(x, z)))
        on = bool(e is not None and is_sukhumvit(e))
        wx, wz = world(x, z)
        f = {'class': cls, 'world_x': wx, 'world_z': wz, 'world_y': 1.0, 'local_x': round(x, 2), 'local_z': round(z, 2),
             'size': round(float(size), 3), 'score': 0.0, 'sukhumvit': on, 'near_sukhumvit': near or on,
             'road': (e.get('label') if e else None), 'edge': (e['id'] if e else None), 'way': (e['way'] if e else None),
             'dataset': (e['ds'] if e else None), 'chunk': f'{math.floor(x / 512)}_{math.floor(z / 512)}', 'why': why,
             'teleport': f'CFrame.new({wx}, 6, {wz})'}
        if extra:
            f.update(extra)
        f['score'] = round(severity * float(size) * (3 if f['near_sukhumvit'] else 1), 3)
        findings.append(f)

    # ---- 1. tilt / roll of every Part ----------------------------------------------------------------------------
    for c, tilt, k in tilt_bad:
        add('tilt', c.x, c.y, tilt, 5, f'WedgePart up axis {tilt:.2f} deg off vertical', edges[k] if k >= 0 else None)
    # stripes / discs / boxes: CFrame.lookAt(y, y) and Angles(0, 0, 90) -> exactly level (0 deg) by construction

    # ---- 2. step / slope between consecutive Parts (constant tops: computed for the record) -----------------------
    by_edge = defaultdict(list)
    for s in surf:
        if s['kind'] == 'slab':
            by_edge[s['edge']].append(s)
    step_max = 0.0
    for k, parts in by_edge.items():
        for p, q in zip(parts, parts[1:]):
            if p['piece'] == q['piece']:
                step_max = max(step_max, abs(p['top'] - q['top']))
    node_tops = defaultdict(set)
    for s in surf:
        if s['kind'] in ('disc', 'joint'):
            node_tops[s['node']].add(s['top'])
    for e in edges:
        for n in (e['a'], e['b']):
            node_tops[n].add(ROAD_TOP)
    node_step_max = max((max(t) - min(t) for t in node_tops.values()), default=0.0)

    # ---- 3. holes in the road-height surface ---------------------------------------------------------------------
    # an enclosed hole wider than MAX_SEAM_W is a city block / median between roads (ground by design), not a seam
    print('union of the road-height surface ...')
    road_union = shapely.union_all(np.array([polys[i] for i in road_idx], dtype=object), grid_size=0.001)
    raised_union = shapely.union_all(np.array([polys[i] for i in raised_idx], dtype=object), grid_size=0.001) if len(raised_idx) else None
    holes = []
    for g in getattr(road_union, 'geoms', [road_union]):
        for ring in g.interiors:
            holes.append(Polygon(ring))
    hole_stats = {'holes': len(holes), 'gap': 0, 'sliver': 0, 'micro': 0, 'under_raised': 0, 'block_or_median': 0}
    edge_tree = STRtree([shapely.LineString(e['pts']) for e in edges])
    built = [k for k, e in enumerate(edges) if not e['hidden']]
    built_tree = STRtree([shapely.LineString(edges[k]['pts']) for k in built])
    for h in holes:
        if h.area > MAX_SEAM_AREA:
            hole_stats['block_or_median'] += 1
            continue
        open_ground = h.difference(raised_union) if raised_union is not None else h
        if open_ground.is_empty or open_ground.area < 1e-4:
            hole_stats['under_raised'] += 1
            continue
        try:
            mic = shapely.maximum_inscribed_circle(open_ground, tolerance=0.005)
            width = 2 * shapely.length(mic)
            cx, cz = shapely.get_coordinates(mic)[0]
        except Exception:
            width = 2 * open_ground.area / max(open_ground.length, 1e-9)
            cx, cz = open_ground.representative_point().x, open_ground.representative_point().y
        if width > MAX_SEAM_W:
            hole_stats['block_or_median'] += 1
            continue
        if width < 0.05:
            hole_stats['micro'] += 1
            continue
        cls = 'gap' if width > 0.5 else 'sliver'
        hole_stats[cls] += 1
        near = built_tree.query_nearest(Point(cx, cz))
        e = edges[built[int(near[0])]] if len(near) else None
        add(cls, cx, cz, width * (1 + open_ground.area) ** 0.5, 10 if cls == 'gap' else 3,
            f'enclosed hole in the road surface: {open_ground.area:.2f} studs², width {width:.2f}, '
            f'length ~{open_ground.length / 2:.1f} (terrain 3 studs below)', e,
            {'area': round(open_ground.area, 3), 'width': round(width, 3)})

    # ---- 4. open slab ends --------------------------------------------------------------------------------------
    end_stats = {'ends': 0, 'end_gap': 0, 'narrowing': 0}
    march = np.arange(0.05, 4.01, 0.05)
    for k, e in enumerate(edges):
        pieces = rc.slab_pieces(e)
        for pi, q in enumerate(pieces):
            for end in (0, 1):
                p, prev = (q[0], q[1]) if end == 0 else (q[-1], q[-2])
                dvec = p - prev
                n = np.linalg.norm(dvec)
                if n < 1e-6:
                    continue
                d = dvec / n
                at_node = (end == 0 and pi == 0 and not e['cutA']) or (end == 1 and pi == len(pieces) - 1 and not e['cutB'])
                node = e['a'] if end == 0 else e['b']
                if at_node and deg[node] <= 1:
                    continue                       # dead end: the road just stops (joint disc rounds it off)
                end_stats['ends'] += 1
                nrm = np.array([-d[1], d[0]])
                lat = np.linspace(-0.45, 0.45, 19) * e['width']
                P = (p[None, None, :] + lat[:, None, None] * nrm[None, None, :] + march[None, :, None] * d[None, None, :]).reshape(-1, 2)
                cov = (top_at(P) > 0.9).reshape(len(lat), len(march))
                gaps = []                          # per drive line: open length right after the end (99 = never closes)
                for row in cov:
                    if row[0]:
                        gaps.append(0.0)
                    else:
                        gaps.append(float(march[np.argmax(row)]) if row.any() else 99.0)
                gaps = np.array(gaps)
                open_lines = gaps > 0.5
                if not open_lines.any():
                    continue
                frac = float(open_lines.mean())
                where = f'node {node} (degree {deg[node]})' if at_node else 'slab cut / hide boundary'
                lo, hi = lat[open_lines].min(), lat[open_lines].max()
                side = 'left' if hi < 0 else ('right' if lo > 0 else 'across')
                closes = gaps[open_lines & (gaps < 99)]
                if (gaps[open_lines] >= 99).all():
                    end_stats['narrowing'] += 1
                    add('narrowing', *(p + nrm * (lo + hi) / 2), frac * e['width'], 5,
                        f'slab ends at {where}; {frac:.0%} of its width ({side}, offsets {lo:+.1f}..{hi:+.1f}) has no road '
                        f'surface for > 4 studs after it: the drivable surface narrows / steps sideways here', e,
                        {'open_fraction': round(frac, 2)})
                else:
                    end_stats['end_gap'] += 1
                    g = float(closes.max()) if len(closes) else 4.0
                    add('end_gap', *(p + nrm * (lo + hi) / 2), g * frac * e['width'], 8,
                        f'{g:.2f} studs of open ground after the slab end at {where} on {frac:.0%} of the width '
                        f'({side}), then road again: a wheel drops into it', e,
                        {'open_fraction': round(frac, 2), 'gap_length': round(g, 2)})

    # ---- 5. wheel tracks on every BUILT slab piece: kerbs (and drops at interior bends) ---------------------------
    # hidden carriageways (road_fix rule D) are skipped: their lane lines are traffic paths, the built surface is the
    # merged slab (+ fill triangles), which is scanned as its own edge
    print('wheel-track scan ...')
    track_stats = defaultdict(int)
    cells = {}
    for k, e in enumerate(edges):
        suk = is_sukhumvit(e)
        step = a.suk_step if suk else a.step
        half = e['width'] / 2 - 1.5                # a wheel's contact patch stays this far inside the slab edge
        if half <= 0:
            continue
        lat = np.arange(-half, half + 1e-6, 1.5) if suk else np.array([-half, -half / 2, 0, half / 2, half])
        for q in rc.slab_pieces(e):
            xy, tan, s = polyline_samples(q, step)
            inside = (s > 0.3) & (s < np.linalg.norm(np.diff(q, axis=0), axis=1).sum() - 0.3)   # piece ends: see end_gap / narrowing
            xy, tan, s = xy[inside], tan[inside], s[inside]
            if not len(xy):
                continue
            nrm = np.stack([-tan[:, 1], tan[:, 0]], axis=1)
            for o in lat:
                P = xy + nrm * o
                t, who = top_owner(P)
                track_stats['samples'] += len(P)
                track_stats['suk_samples'] += len(P) if suk else 0
                for i in np.nonzero((t > 1.3) | (t < 0.5))[0]:
                    kind = 'kerb' if t[i] > 1.3 else 'drop'
                    track_stats[kind] += 1
                    src = surf[who[i]] if who[i] >= 0 else None
                    by = (src['kind'], src['edge'] if src['edge'] >= 0 else src.get('node')) if src else ('terrain', None)
                    key = (kind, int(P[i, 0] // 6), int(P[i, 1] // 6))
                    c = cells.setdefault(key, {'n': 0, 'x': 0.0, 'z': 0.0, 'edge': k, 'by': defaultdict(int)})
                    c['n'] += 1
                    c['x'] += P[i, 0]
                    c['z'] += P[i, 1]
                    c['by'][by] += 1
    seen = set()
    for key in cells:
        if key in seen:
            continue
        kind = key[0]
        stack, comp = [key], []
        seen.add(key)
        while stack:
            c = stack.pop()
            comp.append(c)
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nb = (kind, c[1] + dx, c[2] + dz)
                    if nb in cells and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        n = sum(cells[c]['n'] for c in comp)
        x = sum(cells[c]['x'] for c in comp) / n
        z = sum(cells[c]['z'] for c in comp) / n
        e = edges[cells[max(comp, key=lambda c: cells[c]['n'])]['edge']]
        by = defaultdict(int)
        for c in comp:
            for b, v in cells[c]['by'].items():
                by[b] += v
        (bkind, bown), _ = max(by.items(), key=lambda t: t[1])
        if kind == 'kerb':
            owner = edges[bown] if bkind == 'sidewalk' else None
            own = owner is e
            add('kerb', x, z, n, 4, f'{n} wheel-track samples on a raised {bkind} (+0.6) inside the lanes of {e.get("label")}'
                + (f' - the {bkind} of {owner.get("label")} ({owner["id"]})' if owner is not None and not own else '')
                + (' - its OWN sidewalk (inner side of a bend)' if own else '')
                + (f' - corner fill of junction {bown}' if bkind == 'corner' else ''), e,
                {'samples': n, 'raised_by': f'{bkind}:{owner["id"] if owner is not None else bown}'})
        else:
            add('drop', x, z, n, 6, f'{n} wheel-track samples with no road under them (terrain -2) inside a built slab '
                f'piece of {e.get("label")} (open wedge at a bend / missing piece)', e, {'samples': n})

    # ---- 6. z-fighting summary ----------------------------------------------------------------------------------
    zf = {'pairs': 0, 'area': 0.0, 'by_kind': defaultdict(float)}
    sl = np.nonzero(np.array([s['kind'] in ('slab', 'fill') for s in surf]))[0]
    low = np.nonzero(np.array([s['kind'] in ('disc', 'joint', 'apron') for s in surf]))[0]
    low_tree = STRtree([polys[i] for i in low])
    qi, li = low_tree.query(np.array([polys[i] for i in sl], dtype=object), predicate='intersects')
    suk_zf = defaultdict(float)
    for a_i, b_i in zip(qi, li):
        A, B = surf[sl[a_i]], surf[low[b_i]]
        ar = A['poly'].intersection(B['poly']).area
        if ar < 0.01:
            continue
        zf['pairs'] += 1
        zf['area'] += ar
        zf['by_kind'][B['kind']] += ar
        if is_sukhumvit(edges[A['edge']]):
            c = B['poly'].centroid
            suk_zf[(round(c.x, 1), round(c.y, 1), B['kind'])] += ar
    for (x, z, kind), ar in sorted(suk_zf.items(), key=lambda t: -t[1])[:15]:
        add('zfight', x, z, ar, 0.0005, f'{kind} (top {DISC_TOP if kind != "apron" else 0.98}) under a Sukhumvit slab '
            f'(top 1.00): {ar:.0f} studs² coplanar within 0.02 - flicker only, no bump', None)

    # ---- output -------------------------------------------------------------------------------------------------
    findings.sort(key=lambda f: -f['score'])
    for i, f in enumerate(findings, 1):
        f['rank'] = i
    summary = {
        'build_root': broot, 'origin': ORIGIN, 'edges': len(edges), 'surface_pieces': len(surf),
        'sukhumvit_edges': len(suk_edges),
        'tilt': {'max_part_tilt_deg': round(tilt_max, 4), 'parts_over_2deg': len(tilt_bad),
                 'note': 'slabs / discs / boxes are level by construction (CFrame.lookAt at one y, Angles(0,0,90))'},
        'step': {'max_top_step_consecutive_parts': step_max, 'max_top_step_at_nodes': round(node_step_max, 3),
                 'max_slope_change_deg': 0.0,
                 'note': 'the exported road data has no elevation: every road part top is a constant (1.00 slab/fill, '
                         '0.99 disc, 0.98 apron); steps > 0.3 can only come from kerbs (1.60/1.58) or terrain (-2)'},
        'holes': hole_stats, 'ends': end_stats, 'tracks': dict(track_stats),
        'zfight': {'pairs': zf['pairs'], 'area_studs2': round(zf['area']), 'by_kind': {k: round(v) for k, v in zf['by_kind'].items()}},
        'counts': {c: sum(1 for f in findings if f['class'] == c) for c in sorted({f['class'] for f in findings})},
        'counts_sukhumvit': {c: sum(1 for f in findings if f['class'] == c and f['near_sukhumvit']) for c in sorted({f['class'] for f in findings})},
    }
    json.dump({'summary': summary, 'findings': findings}, open(os.path.join(out_dir, 'road_seams.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    cols = ['rank', 'class', 'score', 'world_x', 'world_z', 'size', 'sukhumvit', 'near_sukhumvit', 'road', 'edge', 'way',
            'dataset', 'chunk', 'why', 'teleport']
    with open(os.path.join(out_dir, 'road_seams.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(findings)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for f in findings[:a.top]:
        print(f"{f['rank']:3d} {f['class']:8s} {f['score']:9.2f} ({f['world_x']}, {f['world_z']}) {f['road']} "
              f"{'SUK' if f['sukhumvit'] else ('near' if f['near_sukhumvit'] else '')} - {f['why']}")
    print('wrote', os.path.join(out_dir, 'road_seams.json'))


if __name__ == '__main__':
    main()
