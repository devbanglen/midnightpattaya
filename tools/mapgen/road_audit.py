"""Road geometry audit over the EXPORTED road surface of the whole game world (central slice + wide world + corridor).

  .venv\\Scripts\\python tools\\mapgen\\road_audit.py                       # current build/ -> build/road_audit/
  .venv\\Scripts\\python tools\\mapgen\\road_audit.py --out build/road_audit_before --label before

What Studio has is what the chunk modules say, so the audit reads them (tools/mapgen/road_check.load_dataset):
build/central_pattaya/roblox (base slice, `PattayaBuilder.Build`), build/pattaya_wide/roblox (`Extend`, WideChunks)
and build/bira/roblox_corridor (`Extend({folder = "PattayaDataCorridor"})`). Every edge is the exported polyline
(Douglas-Peucker 0.35 + split at 120 studs) and its slab is that polyline buffered by width/2 (flat ends), exactly the
road Parts PattayaBuilder makes; junction discs come from the manifests, crossing discs from `crossings` (if any).
OSM tags (bridge / tunnel / layer / oneway / highway) are read from the raw Overpass files in data/osm/raw by way id.

Classes (every finding has world x, z = map-local + PattayaBuilder.ORIGIN (20000, 0, 0), i.e. the Studio frame):
  crossing   two centrelines intersect at a point that is not a node both edges share (no junction disc there, so
             one road's markings and raised sidewalks run across the other's roadway). `grade` says whether OSM puts
             the two on different levels (bridge / tunnel / layer) - a flyover flattened onto one plane.
  parallel   two edges that share no node and whose slabs overlap along a stretch (dual carriageways and close
             parallel sois squeezed together by the x0.5 compression and the widening). overlap_len (studs, along
             the shorter edge) and gap (median centreline distance over that stretch); overlap means
             gap < (width_a + width_b) / 2.
  acute      two edges leaving one node at a small angle: their slabs keep overlapping `spike` studs past the node's
             disc (a wedge of doubled road and crossed markings).
  tee        (also a missing junction) two edges that share no node, whose slabs overlap at an angle > 30 deg:
             one road's end pokes into the other road (an unconnected T) - kerbs and markings across a roadway.
  short      an edge shorter than 15 studs between two junction discs (the discs overlap / the slab is a stub).
  kink       a vertex of the exported polyline (or a degree-2 joint between two edges) where the heading turns by
             more than 60 degrees (a zig-zag at driving speed).
  step       two edges meeting at one node whose end points are more than 0.05 studs apart (seam step).
road_fix rule D (tools/mapgen/dual.py) is read from the modules: a hidden edge has no surface (it takes part in no
finding), a cut edge's slab is its slab pieces (road_check.slab_pieces) plus its fill triangles, and a merged edge's end
points lie off its nodes on purpose (centred between the two carriageways), so it is not checked for steps.
Each overlap finding (crossing / tee / parallel / acute) also says whether it is VISIBLE: marking Parts of one road on
the other, or more than 10 studs^2 of one road's sidewalk side on the other (road_fix.py rules M and S); otherwise the
two slabs only share one flat unmarked surface (same height, same colour), which reads as one wider road.
score = rough area of bad road surface in studs^2 (crossings x3: a raised kerb across a roadway is a crash), used only
to rank the findings (x0.2 for an overlap that is not visible); severity: high >= 400, medium >= 100, else low.

Outputs in --out: findings.json, findings.csv, summary.json (counts per class per dataset) and overview.png (the
worst 30 numbered, the same numbers as rank 1..30 in the CSV).
"""
import argparse, csv, json, math, os, sys
from collections import Counter, defaultdict
import numpy as np
from shapely.geometry import LineString, MultiLineString, MultiPoint, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(__file__))
import road_check as rc  # noqa: E402
import road_fix as rfx  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
ORIGIN_X, ORIGIN_Z = 20000.0, 0.0
DATASETS = [('central', 'build/central_pattaya/roblox'), ('wide', 'build/pattaya_wide/roblox'),
            ('corridor', 'build/bira/roblox_corridor')]
RAW = ['data/osm/raw/central_pattaya_2026-10-18.json', 'data/osm/raw/pattaya_wide_north_2026-10-18.json',
       'data/osm/raw/pattaya_wide_south_2026-10-18.json', 'data/osm/raw/pattaya_wide_east_2026-10-18.json',
       'data/osm/raw/bira_corridor_2026-10-18.json']
KINK_DEG = 60.0
SHORT_STUDS = 15.0
ACUTE_MIN_SPIKE = 6.0          # studs of doubled slab past the disc before an acute merge is reported
ACUTE_MAX_SPIKE = 60.0         # longer: the two run side by side (a dual carriageway split), reported as parallel
PARALLEL_MIN_LEN = 6.0         # studs of overlapping stretch before a parallel overlap is reported
HIDDEN_WEIGHT = 0.2            # score factor for an overlap with nothing visible on it (no marks / kerbs on the other road)
STEP = 1.0                     # sampling step along centrelines (studs)


def way_tags(root=ROOT):
    tags = {}
    for f in RAW:
        p = os.path.join(root, f)
        if not os.path.exists(p):
            continue
        for e in json.load(open(p, encoding='utf-8'))['elements']:
            if e['type'] == 'way' and 'highway' in e.get('tags', {}) and e['id'] not in tags:
                t = e['tags']
                tags[e['id']] = {k: t.get(k) for k in ('highway', 'bridge', 'tunnel', 'layer', 'oneway', 'name', 'name:en')}
    return tags


def level(t):
    """OSM vertical level of a way: layer if given, else +1 for a bridge, -1 for a tunnel, 0 on the ground."""
    if not t:
        return 0
    try:
        if t.get('layer') is not None:
            return int(float(str(t['layer']).split(';')[0]))
    except ValueError:
        pass
    if t.get('bridge') not in (None, 'no'):
        return 1
    if t.get('tunnel') not in (None, 'no'):
        return -1
    return 0


def load_world(root=ROOT):
    """every exported edge of every dataset (with 'ds', 'noMarks'), all discs {(ds, key): (x, z, r)}, per-dataset
    junction radii (what trims markings / sidewalks) and dash gaps - the same loader road_fix.py uses"""
    edges, discs, jrs, _, gaps = rfx.load(root)
    return edges, discs, jrs, gaps


def visible_conflicts(edges, discs, jrs, gaps):
    """what a player sees where two road surfaces overlap: marking Parts (centre points, built exactly like
    PattayaBuilder.buildEdge) lying on another road of the same or a higher class or on a foreign disc, and sidewalk
    strips lying on another road. Returns (marks {(i, j): parts}, kerb {(i, j, side): studs^2}); j = -1 for a disc."""
    import shapely
    W = rfx.World(edges, discs)
    marks, kerb = defaultdict(int), defaultdict(float)
    for i, e in enumerate(edges):
        pts = rfx.marking_parts(e, jrs[e['ds']], gaps[e['ds']])
        if pts:
            P = np.array(pts)
            pi, si = W.inner_tree.query(shapely.points(P[:, 0], P[:, 1]), predicate='within')
            seen = set()
            for a_, b_ in zip(pi, si):
                if a_ not in seen and W.suppresses(i, b_):
                    seen.add(a_)
                    marks[(i, W.slab_edge[b_])] += 1
        if e['sidewalk'] > 0 and not e.get('hidden'):
            jr = jrs[e['ds']]
            ra, rb = rfx.end_trims(e, jr)
            sw = rc.trim(e['pts'], ra + e['sidewalk'] if ra > 0 else 0, rb + e['sidewalk'] if rb > 0 else 0)
            if sw is None:
                continue
            for side in (-1, 1):
                if e.get('swSide') and e['swSide'] != side:
                    continue
                strip = unary_union(rc.stripe_rects(rc.offset(sw, side * (e['width'] + e['sidewalk']) / 2), e['sidewalk']))
                for k in W.tree.query(strip):
                    if W.foreign(i, k):
                        a_ = W.slabs[k].intersection(strip).area
                        if a_ > 0:
                            kerb[(i, W.slab_edge[k], side)] += a_
    return marks, kerb


def heading(p, from_end=False, dist=8.0):
    """unit direction of the first `dist` studs of polyline p leaving its start (or its end)"""
    q = p[::-1] if from_end else p
    s, prev = 0.0, q[0]
    for pt in q[1:]:
        s += float(np.linalg.norm(pt - prev)); prev = pt
        if s >= dist:
            break
    v = prev - q[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def sample(p, step=STEP):
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] <= 0:
        return p[:1], np.zeros(1)
    t = np.arange(0, s[-1] + 1e-9, step)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1), t


def world(x, z):
    return round(float(x) + ORIGIN_X, 1), round(float(z) + ORIGIN_Z, 1)


def severity(score):
    return 'high' if score >= 400 else 'medium' if score >= 100 else 'low'


def audit(edges, discs, tags):
    C = 512
    for i, e in enumerate(edges):
        e['idx'] = i
        e['line'] = LineString(e['pts'])
        e['len'] = e['line'].length
        pieces = [q for q in rc.slab_pieces(e) if len(q) > 1]
        e['pieces'] = pieces                          # slab lines (none: hidden edge, no surface)
        e['sline'] = (LineString(pieces[0]) if len(pieces) == 1 else MultiLineString([LineString(q) for q in pieces])) \
            if pieces else None
        rects = rc.slab_rects(e)
        e['slab'] = unary_union(rects) if rects else e['line'].buffer(e['width'] / 2)
        e['lvl'] = level(tags.get(e['way']))
    node_pos = defaultdict(list)
    inc = defaultdict(list)                      # node -> [(edge index, at_end)]
    for i, e in enumerate(sorted(range(len(edges)), key=lambda k: bool(edges[k].get('merged')))):
        e = edges[e]                             # node positions from unmerged edges first (merged ends lie off the node)
        node_pos[e['a']].append(e['pts'][0]); node_pos[e['b']].append(e['pts'][-1])
    for i, e in enumerate(edges):
        inc[e['a']].append((i, False)); inc[e['b']].append((i, True))
    deg = {n: len(v) for n, v in inc.items()}
    disc_r = defaultdict(float)                  # node -> disc radius actually built (junction or joint)
    disc_pts = []
    for (ds, k), (x, z, r) in discs.items():
        if isinstance(k, tuple) and k[0] == 'joint':
            disc_r[k[1]] = max(disc_r[k[1]], r)
        elif isinstance(k, tuple) and k[0] == 'crossing':
            disc_pts.append((x, z, r))
        else:
            disc_r[k] = max(disc_r[k], r)
    cross_tree = STRtree([Point(x, z).buffer(r) for x, z, r in disc_pts]) if disc_pts else None
    findings = []

    def add(cls, score, x, z, ea, eb=None, **kw):
        wx, wz = world(x, z)
        f = {'class': cls, 'score': round(float(score), 1), 'severity': severity(score), 'x': wx, 'z': wz,
             'chunk': f'{math.floor(x / C)}_{math.floor(z / C)}',
             'dataset': ea['ds'] if eb is None or ea['ds'] == eb['ds'] else '+'.join(sorted({ea['ds'], eb['ds']})),
             'edge_a': ea['id'], 'way_a': ea['way'], 'name_a': tags.get(ea['way'], {}).get('name:en') or tags.get(ea['way'], {}).get('name'),
             'tier_a': ea['tier'], 'width_a': ea['width'], 'chunk_a': ea['chunk'], 'set_a': ea['ds'],
             'edge_b': eb['id'] if eb else None, 'way_b': eb['way'] if eb else None,
             'name_b': (tags.get(eb['way'], {}).get('name:en') or tags.get(eb['way'], {}).get('name')) if eb else None,
             'tier_b': eb['tier'] if eb else None, 'width_b': eb['width'] if eb else None,
             'chunk_b': eb['chunk'] if eb else None, 'set_b': eb['ds'] if eb else None}
        f.update(kw)
        f['_i'], f['_j'] = ea['idx'], (eb['idx'] if eb is not None else None)
        findings.append(f)

    def tagstr(e):
        t = tags.get(e['way'], {})
        return ';'.join(f'{k}={t[k]}' for k in ('highway', 'bridge', 'tunnel', 'layer', 'oneway') if t.get(k) is not None)

    # ---- a + b: pairs of edges whose slabs touch ------------------------------------------------------------------
    tree = STRtree([e['slab'] for e in edges])
    pa, pb = tree.query([e['slab'] for e in edges], predicate='intersects')
    for i, j in zip(pa, pb):
        if j <= i:
            continue
        A, B = edges[i], edges[j]
        if A.get('hidden') or B.get('hidden'):
            continue
        shared = {A['a'], A['b']} & {B['a'], B['b']}
        # crossings: centreline intersections away from any shared node
        inter = A['sline'].intersection(B['sline']) if A['sline'] is not None and B['sline'] is not None else A['line'].intersection(B['line'])
        pts = []
        if not inter.is_empty:
            geoms = getattr(inter, 'geoms', [inter])
            for g_ in geoms:
                if g_.geom_type == 'Point':
                    pts.append(np.array(g_.coords[0]))
                elif g_.geom_type == 'LineString':           # collinear: treat as overlap (b), not a crossing
                    pass
        cross_pts = []
        for p in pts:
            near = False
            for n in shared:
                q = np.array(node_pos[n][0])
                if np.linalg.norm(p - q) <= max(A['width'], B['width']) / 2 + 1.0:
                    near = True
            if not near:
                cross_pts.append(p)
        # merge crossing points closer than the road width (a slab polyline wiggling over a centreline)
        merged = []
        for p in cross_pts:
            if all(np.linalg.norm(p - q) > max(A['width'], B['width']) for q in merged):
                merged.append(p)
        for p in merged:
            ha = A['pts'][min(range(len(A['pts']) - 1), key=lambda k: LineString(A['pts'][k:k + 2]).distance(Point(p)))]
            # crossing angle from the two segments that hold p
            def seg_dir(e):
                k = min(range(len(e['pts']) - 1), key=lambda k: LineString(e['pts'][k:k + 2]).distance(Point(p)))
                v = e['pts'][k + 1] - e['pts'][k]
                return v / (np.linalg.norm(v) + 1e-9)
            ang = math.degrees(math.acos(min(1.0, abs(float(seg_dir(A) @ seg_dir(B))))))
            area = A['width'] * B['width'] / max(math.sin(math.radians(max(ang, 5))), 0.1)
            grade = 'separated' if A['lvl'] != B['lvl'] else 'same'
            covered = bool(cross_tree is not None and len(cross_tree.query(Point(p), predicate='intersects')))
            add('crossing', 3 * area * (0.3 if covered else 1), p[0], p[1], A, B, angle=round(ang, 1), grade=grade,
                level_a=A['lvl'], level_b=B['lvl'], tags_a=tagstr(A), tags_b=tagstr(B), covered_by_disc=covered,
                detail=f'centrelines cross at {ang:.0f} deg, no shared node' + (' (OSM: different levels)' if grade == 'separated' else ''))
        if shared:
            continue                                         # adjacent pairs: see acute / short below
        # parallel overlap: samples of the shorter edge whose distance to the other centreline < (wa + wb) / 2
        # (both measured on the slab lines: a cut slab is shorter than its centreline)
        if A['sline'] is None or B['sline'] is None:
            continue
        S, L = (A, B) if A['sline'].length <= B['sline'].length else (B, A)
        sp = np.vstack([sample(q)[0] for q in S['pieces']])
        if len(sp) < 2:
            continue
        import shapely
        d = shapely.distance(shapely.points(sp[:, 0], sp[:, 1]), L['sline'])
        lim = (A['width'] + B['width']) / 2
        ov = d < lim - 0.25
        for p in merged:                                     # not the crossing patch itself
            ov &= np.linalg.norm(sp - p, axis=1) > lim + 2
        if ov.sum() * STEP < PARALLEL_MIN_LEN:
            continue
        # longest run of overlapping samples
        runs, cur = [], []
        for k, v in enumerate(ov):
            if v:
                cur.append(k)
            elif cur:
                runs.append(cur); cur = []
        if cur:
            runs.append(cur)
        run = max(runs, key=len)
        olen = len(run) * STEP
        if olen < PARALLEL_MIN_LEN:
            continue
        gap = float(np.median(d[run]))
        depth = lim - gap
        mid = sp[run[len(run) // 2]]
        # parallel or end-on? angle between the shorter edge and the other centreline over the run
        cosv = []
        for k in run[::max(1, len(run) // 8)]:
            k2 = min(k + 2, len(sp) - 1) if k + 2 < len(sp) else k
            k1 = k2 - 2 if k2 >= 2 else 0
            v = sp[k2] - sp[k1]
            s0 = L['line'].project(Point(sp[k]))
            q0, q1 = L['line'].interpolate(max(s0 - 1, 0)), L['line'].interpolate(min(s0 + 1, L['len']))
            w = np.array([q1.x - q0.x, q1.y - q0.y])
            if np.linalg.norm(v) > 1e-6 and np.linalg.norm(w) > 1e-6:
                cosv.append(abs(float(v @ w)) / np.linalg.norm(v) / np.linalg.norm(w))
        ang = math.degrees(math.acos(min(1.0, float(np.median(cosv))))) if cosv else 0.0
        if ang > 30:
            add('tee', float(np.sum(lim - d[ov])) * STEP * 2, mid[0], mid[1], S, L, angle=round(ang, 1), overlap_len=round(olen, 1),
                gap=round(gap, 2), needed_gap=round(lim, 2), tags_a=tagstr(S), tags_b=tagstr(L),
                detail=f'slab pokes into another road at {ang:.0f} deg without a junction ({olen:.0f} studs, gap {gap:.1f} < {lim:.1f})')
            continue
        add('parallel', float(np.sum(lim - d[ov])) * STEP, mid[0], mid[1], S, L, overlap_len=round(olen, 1),
            overlap_total=round(float(ov.sum() * STEP), 1), gap=round(gap, 2), min_gap=round(float(d[run].min()), 2),
            needed_gap=round(lim, 2), depth=round(depth, 2), oneway_a=S['oneway'], oneway_b=L['oneway'],
            same_name=bool(tags.get(S['way'], {}).get('name') and tags.get(S['way'], {}).get('name') == tags.get(L['way'], {}).get('name')),
            tags_a=tagstr(S), tags_b=tagstr(L),
            detail=f'slabs overlap {olen:.0f} studs, centreline gap {gap:.1f} < {lim:.1f}')

    # ---- c: acute merges and short edges --------------------------------------------------------------------------
    import shapely
    for n, lst in inc.items():
        if len(lst) < 2:
            continue
        npos = np.array(node_pos[n][0])
        r = disc_r.get(n, 0.0)
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                (i, ei), (j, ej) = lst[x], lst[y]
                if i == j:
                    continue
                A, B = edges[i], edges[j]
                if A.get('hidden') or B.get('hidden'):
                    continue
                ha, hb = heading(A['pts'], ei), heading(B['pts'], ej)
                ang = math.degrees(math.acos(max(-1.0, min(1.0, float(ha @ hb)))))
                if ang >= 60:
                    continue
                lim = (A['width'] + B['width']) / 2
                spikes = []
                for S, es, L in ((A, ei, B), (B, ej, A)):
                    # overlap of the two slabs: S's samples from the node, beyond S's own slab cut at this end, against
                    # L's slab line
                    sp, t = sample(S['pts'][::-1] if es else S['pts'])
                    d = shapely.distance(shapely.points(sp[:, 0], sp[:, 1]), L['sline'])
                    c = (S.get('cutB') if es else S.get('cutA')) or 0.0
                    k = int(np.searchsorted(t, c - 1e-9)) if c > 0 else 0
                    k0 = k
                    while k < len(d) and (d[k] < lim - 0.25 or t[k] <= r):
                        k += 1
                    spikes.append(t[min(k, len(t) - 1)] - max(r, t[min(k0, len(t) - 1)] if c > 0 else r) + r)
                spike = max(spikes) - r
                if spike < ACUTE_MIN_SPIKE:
                    continue
                if spike > ACUTE_MAX_SPIKE:              # a dual carriageway splitting at a node: parallel overlap
                    add('parallel', spike * lim * 0.5, npos[0], npos[1], A, B, node=n, overlap_len=round(spike, 1),
                        needed_gap=round(lim, 2), angle=round(ang, 1), shared_node=True, oneway_a=A['oneway'], oneway_b=B['oneway'],
                        same_name=bool(tags.get(A['way'], {}).get('name') and tags.get(A['way'], {}).get('name') == tags.get(B['way'], {}).get('name')),
                        detail=f'two edges leave node {n} {ang:.0f} deg apart and overlap {spike:.0f} studs (dual carriageway split)')
                    continue
                add('acute', spike * lim * 0.5, npos[0], npos[1], A, B, node=n, degree=deg[n], angle=round(ang, 1),
                    spike=round(spike, 1), disc_r=round(r, 2),
                    detail=f'{ang:.0f} deg merge at node {n}: slabs overlap {spike:.0f} studs past the disc (r {r:.1f})')
    for i, e in enumerate(edges):
        if e.get('hidden'):
            continue
        if e['len'] < SHORT_STUDS and deg.get(e['a'], 0) >= 3 and deg.get(e['b'], 0) >= 3:
            ra, rb = disc_r.get(e['a'], 0), disc_r.get(e['b'], 0)
            ov = ra + rb - e['len']
            m = e['line'].interpolate(0.5, normalized=True)
            add('short', max(ov, 0) * e['width'] + 20, m.x, m.y, e, None, length=round(e['len'], 1), disc_overlap=round(ov, 1),
                node_a=e['a'], node_b=e['b'], detail=f'{e["len"]:.1f}-stud edge between two junctions (discs r {ra:.1f} + {rb:.1f})')

    # ---- d: kinks inside an edge, kinks at degree-2 joints, seam steps ---------------------------------------------
    for e in edges:
        if e.get('hidden'):
            continue
        p = e['pts']
        for k in range(1, len(p) - 1):
            v1, v2 = p[k] - p[k - 1], p[k + 1] - p[k]
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 < 1e-6 or n2 < 1e-6:
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, float(v1 @ v2 / n1 / n2)))))
            if ang > KINK_DEG:
                add('kink', e['width'] ** 2 * ang / 90, p[k][0], p[k][1], e, None, angle=round(ang, 1),
                    seg_in=round(float(n1), 1), seg_out=round(float(n2), 1), where='inside',
                    detail=f'heading turns {ang:.0f} deg inside the edge (segments {n1:.1f} / {n2:.1f} studs)')
    for n, lst in inc.items():
        st = [(i, at) for i, at in lst if not edges[i].get('merged') and not edges[i].get('hidden')]
        if st:
            P = np.array([edges[i]['pts'][-1 if at else 0] for i, at in st])
            spread = float(np.max(np.linalg.norm(P - P[0], axis=1)))
            if spread > 0.05:
                i, _ = st[0]
                j = next(jj for jj, _ in st if np.linalg.norm(np.array(edges[jj]['pts'][0 if edges[jj]['a'] == n else -1]) - P[0]) > 0.05)
                add('step', spread * 50, P[0][0], P[0][1], edges[i], edges[j], node=n, step=round(spread, 2),
                    detail=f'end points at node {n} are {spread:.2f} studs apart')
        if len(lst) == 2 and any(edges[i].get('hidden') for i, _ in lst):
            continue                                 # a degree-2 joint of the graph with a hidden edge: nothing built
        P = np.array([edges[i]['pts'][-1 if at else 0] for i, at in lst])
        if len(lst) == 2:
            (i, ei), (j, ej) = lst
            if i == j:
                continue
            A, B = edges[i], edges[j]
            ha, hb = heading(A['pts'], ei, 6), heading(B['pts'], ej, 6)
            turn = 180 - math.degrees(math.acos(max(-1.0, min(1.0, float(ha @ hb)))))
            if turn > KINK_DEG:
                add('kink', min(A['width'], B['width']) ** 2 * (turn - KINK_DEG) / 120, P[0][0], P[0][1], A, B, angle=round(turn, 1),
                    node=n, where='joint', detail=f'heading turns {turn:.0f} deg at the degree-2 joint {n}')
    findings.sort(key=lambda f: (-f['score'], f['x'], f['z']))
    for k, f in enumerate(findings, 1):
        f['rank'] = k
    return findings


CLASSES = ['crossing', 'tee', 'parallel', 'acute', 'short', 'kink', 'step']


def annotate(findings, edges, marks, kerb):
    """visible = the overlap shows: marking Parts of one road on the other, or more than 10 studs^2 of one road's
    sidewalk side on the other (the road_fix rules); hidden = the two slabs only share one flat, unmarked surface"""
    for f in findings:
        i, j = f.pop('_i'), f.pop('_j')
        if j is None or f['class'] not in ('crossing', 'tee', 'parallel', 'acute'):
            continue
        m = marks.get((i, j), 0) + marks.get((j, i), 0)
        k = max([kerb.get((i, j, sd), 0) for sd in (-1, 1)] + [kerb.get((j, i, sd), 0) for sd in (-1, 1)])
        f['marks_on_other'] = m
        f['kerb_on_other'] = round(k, 1)
        f['visible'] = bool(m > 0 or k > rfx.KERB_STUDS2)
        if not f['visible']:                         # a hidden overlap ranks lower: nothing shows on the road
            f['score'] = round(f['score'] * HIDDEN_WEIGHT, 1)
            f['severity'] = severity(f['score'])
    findings.sort(key=lambda f: (-f['score'], f['x'], f['z']))
    for k, f in enumerate(findings, 1):
        f['rank'] = k


def bare_bends(edges, discs, limit=35.0):
    """the leader's Studio kink probe, offline: places where two Road parts meet with a heading change over `limit`
    degrees and no disc fills the outside wedge - interior vertices of an exported polyline (no disc is ever built
    there) and degree-2 joints whose disc is missing or narrower than the wider road's half-width"""
    r_at = defaultdict(float)
    for (ds, k), (x, z, r) in discs.items():
        r_at[k[1] if isinstance(k, tuple) else k] = max(r_at[k[1] if isinstance(k, tuple) else k], r)
    out = Counter()
    for e in edges:
        p = e['pts']
        for k in range(1, len(p) - 1):
            if rfx.turn_deg(p, k) > limit:
                out[(e['ds'], 'inside')] += 1
    for n, (turn, lst) in rfx.joint_turns(edges).items():
        if turn > limit:
            w = max(edges[i]['width'] for i, _ in lst) / 2
            if r_at.get(n, 0) < w - 0.01:
                out[(edges[lst[0][0]]['ds'], 'joint')] += 1
    return {f'{ds}_{kind}': v for (ds, kind), v in sorted(out.items())}


def conflict_totals(edges, marks, kerb):
    out = {}
    for ds in ('central', 'wide', 'corridor'):
        mk = sum(v for (i, j), v in marks.items() if edges[i]['ds'] == ds)
        side_area = defaultdict(float)
        for (i, j, sd), a_ in kerb.items():
            if edges[i]['ds'] == ds:
                side_area[(i, sd)] += a_
        out[ds] = {'marking_parts_on_other_road': mk,
                   'sidewalk_sides_on_other_road_gt10': sum(1 for v in side_area.values() if v > rfx.KERB_STUDS2),
                   'sidewalk_area_on_other_road': round(sum(side_area.values()), 1)}
    return out


def summarise(findings):
    out = {}
    for c in CLASSES:
        row = Counter()
        for f in findings:
            if f['class'] == c:
                row[f['dataset']] += 1
        out[c] = dict(sorted(row.items()))
        out[c]['total'] = sum(1 for f in findings if f['class'] == c)
        out[c]['high'] = sum(1 for f in findings if f['class'] == c and f['severity'] == 'high')
        out[c]['medium'] = sum(1 for f in findings if f['class'] == c and f['severity'] == 'medium')
        if c in ('crossing', 'tee', 'parallel', 'acute'):
            vis = Counter(f['dataset'] for f in findings if f['class'] == c and f.get('visible'))
            out[c]['visible'] = sum(vis.values())
            out[c]['visible_by_dataset'] = dict(sorted(vis.items()))
    xs = [f for f in findings if f['class'] == 'crossing']
    out['crossing']['grade_separated'] = sum(1 for f in xs if f['grade'] == 'separated')
    out['crossing']['covered_by_disc'] = sum(1 for f in xs if f.get('covered_by_disc'))
    return out


def render(edges, findings, path, top=30, size=2400):
    from PIL import Image, ImageDraw, ImageFont
    allp = np.vstack([e['pts'] for e in edges])
    lo, hi = allp.min(0) - 200, allp.max(0) + 200
    f = (size - 80) / (hi - lo).max()
    W, H = int((hi[0] - lo[0]) * f) + 80, int((hi[1] - lo[1]) * f) + 80
    im = Image.new('RGB', (W, H), (250, 250, 247))
    dr = ImageDraw.Draw(im)
    tr = lambda p: (40 + (p[0] - lo[0]) * f, 40 + (p[1] - lo[1]) * f)
    col = {'central': (120, 120, 130), 'wide': (165, 165, 175), 'corridor': (150, 130, 190)}
    for e in edges:
        dr.line([tr(p) for p in e['pts']], fill=col[e['ds']], width=max(1, int(e['width'] * f)))
    cls_col = {'crossing': (220, 30, 30), 'tee': (200, 0, 120), 'parallel': (230, 140, 0), 'acute': (160, 40, 200), 'short': (0, 140, 200),
               'kink': (0, 160, 90), 'step': (0, 0, 0)}
    try:
        font = ImageFont.truetype('arial.ttf', 22); small = ImageFont.truetype('arial.ttf', 18)
    except OSError:
        font = small = ImageFont.load_default()
    for fd in findings:
        if fd['severity'] != 'low':
            x, y = tr((fd['x'] - ORIGIN_X, fd['z'] - ORIGIN_Z))
            dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=cls_col[fd['class']])
    for fd in findings[:top]:
        x, y = tr((fd['x'] - ORIGIN_X, fd['z'] - ORIGIN_Z))
        dr.ellipse([x - 13, y - 13, x + 13, y + 13], outline=cls_col[fd['class']], width=4)
        dr.text((x + 15, y - 12), str(fd['rank']), fill=(0, 0, 0), font=font, stroke_width=3, stroke_fill=(255, 255, 255))
    ly = 50
    dr.text((50, ly), 'Road audit: worst 30 numbered (rank = findings.csv), dots = high/medium findings. North up, world studs.',
            fill=(0, 0, 0), font=small); ly += 28
    for c in CLASSES:
        dr.ellipse([50, ly + 3, 64, ly + 17], fill=cls_col[c]); dr.text((72, ly), c, fill=(0, 0, 0), font=small); ly += 26
    dr.text((50, ly + 6), 'Map data (c) OpenStreetMap contributors, ODbL 1.0', fill=(60, 60, 60), font=small)
    im.save(path)


def write(findings, edges, out_dir, label, totals=None):
    os.makedirs(out_dir, exist_ok=True)
    summ = summarise(findings)
    if totals:
        summ['visible_conflicts'] = totals
    json.dump({'label': label, 'summary': summ, 'findings': findings}, open(os.path.join(out_dir, 'findings.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump(summ, open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8'), indent=1)
    keys = ['rank', 'class', 'severity', 'score', 'dataset', 'x', 'z', 'chunk', 'name_a', 'way_a', 'edge_a', 'tier_a', 'width_a',
            'chunk_a', 'name_b', 'way_b', 'edge_b', 'tier_b', 'width_b', 'chunk_b', 'detail', 'angle', 'grade', 'tags_a', 'tags_b',
            'overlap_len', 'gap', 'needed_gap', 'spike', 'length', 'node', 'marks_on_other', 'kerb_on_other', 'visible']
    with open(os.path.join(out_dir, 'findings.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction='ignore')
        w.writeheader()
        for f in findings:
            w.writerow(f)
    render(edges, findings, os.path.join(out_dir, 'overview.png'))
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT, help='repo root whose build/ is audited')
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'road_audit'))
    ap.add_argument('--label', default='current')
    a = ap.parse_args()
    tags = way_tags()
    edges, discs, jrs, gaps = load_world(a.root)
    findings = audit(edges, discs, tags)
    marks, kerb = visible_conflicts(edges, discs, jrs, gaps)
    annotate(findings, edges, marks, kerb)
    totals = conflict_totals(edges, marks, kerb)
    totals['bare_bends_over_35deg'] = bare_bends(edges, discs)
    summ = write(findings, edges, a.out, a.label, totals)
    print(f'{len(edges)} exported edges audited ({Counter(e["ds"] for e in edges)}); {len(findings)} findings -> {a.out}')
    for c in CLASSES:
        print(f'  {c:9s} ' + ', '.join(f'{k} {v}' for k, v in summ[c].items()))
    print(f"  visible conflicts: {summ['visible_conflicts']}")
    for f in findings[:10]:
        print(f"  #{f['rank']} {f['class']} {f['severity']} ({f['x']}, {f['z']}) {f['name_a']} / {f['name_b']}: {f['detail']}")


if __name__ == '__main__':
    main()
