"""Dual carriageways, slip roads and close parallel roads: ONE road surface where two road slabs overlap.

  .venv\\Scripts\\python tools\\mapgen\\dual.py            # after road_graph.py (central, wide): writes build/dual/plan.json

Why: at x0.5 compression with 13-stud lanes, the two carriageways of a dual road (Thep Prasit / Thepprasit Road:
14 studs between centrelines where 58.5 are needed), Sukhumvit's slip roads and some parallel sois overlap. road_fix.py
(pass 1) only hid the markings and kerbs on the overlaps; this module removes the overlaps themselves. The decision is
data-driven, per pair of overlapping edges (docs/ROAD_AUDIT.md, "Dual carriageways and slip roads"):

  (a) MERGE  two edges with the same name (normalised: case / space / '-' / '.' insensitive, Thai or English) that run
             parallel and overlap (the two carriageways of one road, its split at a shared node, or a service carriageway
             beside it). Both edges stay in the graph (indices, polylines, routing, GPS, jobs unchanged). Per merge
             component the widest edges are KEPT (greedy, no two kept edges overlap) and the others are HIDDEN: the kept
             edge's chunk line gets the merged centreline (shifted sideways towards the hidden partner by half the local
             gap, i.e. centred between the two centrelines, tapering out where the partner leaves) and stays the wider
             slab; the hidden edge builds no slab where the merged slab covers its centreline (`hidden = true`, or
             `cutA` / `cutB` + transition fill at the stretch where it leaves). Traffic lanes on merged edges are moved
             inside the merged slab (lane_adjust, traffic.py / corridor_traffic.py).
  (b) OFFSET two different roads running parallel (a soi beside another road): the minor road's polyline is shifted
             sideways in the gameplay transform (road_graph.py -> apply_offsets) just enough to clear
             width_a/2 + width_b/2 + sidewalks + 2, with smooth >= 60-stud transitions, never moving an edge's end
             nodes (they are shared with other edges). Only wide-world (non-base) edges move.
  (c) TRIM   two edges leaving one node at an acute angle (slip roads merging into Sukhumvit, Y-junctions), and slip
             roads (*_link) / any minor road whose overlap with a parallel road touches its end: the minor road's slab is
             cut back (`cutA` / `cutB`) to where it fully leaves the other road, and the part of its old slab that is not
             covered by any other road surface is rebuilt exactly as flat triangles (`fill`, two WedgeParts each), so no
             hole opens. The polyline (routing, GPS, traffic) is unchanged.

Stages: road_graph.py calls apply_offsets() (rule b) before writing graph_game.json; `dual.py` (this CLI) writes the
plan (rule a components and kept / hidden roles, rule c trims) from the gameplay graphs; traffic.py and
corridor_traffic.py read the plan for the lane fix; road_fix.py rule D applies it to the exported chunk modules.
Deterministic: every loop runs in index order; no randomness.
"""
import hashlib, json, math, os, re, sys
from collections import defaultdict
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PLAN = os.path.join('build', 'dual', 'plan.json')
GRAPHS = [('central', 'build/central_pattaya/graph_game.json'), ('wide', 'build/pattaya_wide/graph_game.json'),
          ('corridor', 'build/bira/corridor_graph_game.json')]

STEP = 1.0                 # sampling step along centrelines (studs), as road_audit.py
PARALLEL_MAX_DEG = 30.0    # two edges without a shared node overlap "in parallel" below this angle (else: a tee)
ACUTE_MAX_DEG = 60.0       # two edges leaving one node below this angle can overlap past the disc (road_audit acute)
MIN_RUN = 6.0              # studs of overlapping stretch before a pair counts (road_audit PARALLEL_MIN_LEN / ACUTE_MIN_SPIKE)
SPLIT_SPIKE = 60.0         # an acute pair overlapping longer than this is a dual-carriageway split (merge if same name)
MARGIN = 2.0               # a hidden centreline must lie this far inside the merged slab
TAPER_GAP = 20.0           # merged centreline: the shift fades out over this much extra gap
PIN_RAMP = 60.0            # ... and over this many studs before an end where the road continues un-merged
SMOOTH_SIGMA = 6.0         # studs; smoothing of the sideways shift along the kept edge
BUILDING_CLEAR = 1.0       # fill triangles keep this far from every building box
SHIFT_SLOPE = 0.3          # ... and its steepest change per stud (the merged line turns <= 17 deg off the old one)
OFFSET_CLEAR = 2.0         # rule b: extra clearance between the two slabs (+ sidewalks)
OFFSET_RAMP = 60.0         # rule b: transition length at each end of the shifted stretch
OFFSET_MAX = 30.0          # rule b: larger shifts are not done (the road would move too far from its OSM line)
LANE_W = 13.0
RANK = {'express': 0, 'main': 1, 'soi': 2}


# ---- small helpers ---------------------------------------------------------------------------------------------------
def norm_name(s):
    return re.sub(r'[\s\-\.]', '', (s or '').lower())


def names(e):
    return {norm_name(e.get('name')), norm_name(e.get('name_en') or e.get('nameEn'))} - {''}


def is_link(e):
    return str(e.get('class', '')).endswith('_link')


def priority(e, length):
    """smaller = more important: wider first, then the higher class, a link last, then the longer edge"""
    return (-e['width'], RANK.get(e['tier'], 3), is_link(e), -round(length, 1))


def plen(p):
    p = np.asarray(p, float)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else 0.0


def resample(p, step):
    """points every <= step studs along p (vertices kept), arc positions"""
    p = np.asarray(p, float)
    out, s = [p[0]], [0.0]
    acc = 0.0
    for i in range(len(p) - 1):
        a, b = p[i], p[i + 1]
        ln = float(np.linalg.norm(b - a))
        if ln < 1e-9:
            continue
        n = max(1, int(math.ceil(ln / step)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * (k / n)); s.append(acc + ln * k / n)
        acc += ln
    return np.array(out), np.array(s)


def tangents(q):
    t = np.zeros_like(q)
    if len(q) < 2:
        return t
    t[1:-1] = q[2:] - q[:-2]
    t[0] = q[1] - q[0]
    t[-1] = q[-1] - q[-2]
    return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-12)


def samples(p, step=STEP):
    p = np.asarray(p, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] <= 0:
        return p[:1], np.zeros(1)
    t = np.arange(0, s[-1] + 1e-9, step)
    if s[-1] - t[-1] > 1e-6:                    # the end point too (arc positions measured from both ends stay exact)
        t = np.append(t, s[-1])
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1), t


def heading(p, from_end=False, dist=8.0):
    q = p[::-1] if from_end else p
    s, prev = 0.0, q[0]
    for pt in q[1:]:
        s += float(np.linalg.norm(pt - prev)); prev = pt
        if s >= dist:
            break
    v = prev - q[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def chunk_line(pts):
    """the polyline the exporters write for an edge (Douglas-Peucker 0.35, segments <= 120 studs)"""
    from export_roblox import douglas_peucker, split_long, DP_TOLERANCE, MAX_SEGMENT
    return split_long(douglas_peucker(np.asarray(pts, float), DP_TOLERANCE), MAX_SEGMENT)


def runs_of(mask):
    out, start = [], None
    for k, v in enumerate(list(mask) + [False]):
        if v and start is None:
            start = k
        elif not v and start is not None:
            out.append((start, k - 1)); start = None
    return out


# ---- pair analysis (same rules as road_audit.py: parallel without a shared node, acute / split at a node) ----------
def find_pairs(E, P):
    """E: edges (id, way, name, name_en, oneway, width, tier, class, a, b); P: their polylines (arrays).
    Returns pair dicts: kind 'parallel' (no shared node, angle <= 30) or 'split' (leave one node < 60 deg) with the
    overlap run (studs), the median gap, the needed gap and, for parallel pairs, where along the shorter edge."""
    L = [LineString(p) for p in P]
    slab = [l.buffer(e['width'] / 2, cap_style=2, join_style=2) for l, e in zip(L, E)]
    tree = STRtree(slab)
    inc = defaultdict(list)
    for i, e in enumerate(E):
        inc[e['a']].append((i, False)); inc[e['b']].append((i, True))
    out = []
    pa, pb = tree.query(slab, predicate='intersects')
    for i, j in sorted(zip(pa.tolist(), pb.tolist())):
        if j <= i:
            continue
        A, B = E[i], E[j]
        if {A['a'], A['b']} & {B['a'], B['b']}:
            continue
        lim = (A['width'] + B['width']) / 2
        si, li = (i, j) if L[i].length <= L[j].length else (j, i)
        sp, t = samples(P[si])
        d = shapely.distance(shapely.points(sp), L[li])
        ov = d < lim - 0.25
        if ov.sum() * STEP < MIN_RUN:
            continue
        r0, r1 = max(runs_of(ov), key=lambda r: (r[1] - r[0], -r[0]))
        if (r1 - r0 + 1) * STEP < MIN_RUN:
            continue
        cs = []
        for k in list(range(r0, r1 + 1))[::max(1, (r1 - r0 + 1) // 8)]:
            k2 = min(k + 2, len(sp) - 1); k1 = max(k2 - 2, 0)
            v = sp[k2] - sp[k1]
            s0 = L[li].project(Point(sp[k]))
            q0, q1 = L[li].interpolate(max(s0 - 1, 0)), L[li].interpolate(min(s0 + 1, L[li].length))
            u = np.array([q1.x - q0.x, q1.y - q0.y])
            if np.linalg.norm(v) > 1e-6 and np.linalg.norm(u) > 1e-6:
                cs.append(float(v @ u) / np.linalg.norm(v) / np.linalg.norm(u))
        cm = float(np.median(cs)) if cs else 1.0
        ang = math.degrees(math.acos(min(1.0, abs(cm))))
        if ang > PARALLEL_MAX_DEG:
            continue
        out.append({'kind': 'parallel', 'i': i, 'j': j, 'short': si, 'run': (r1 - r0 + 1) * STEP,
                    's0': float(t[r0]), 's1': float(t[r1]), 'len_short': float(t[-1]), 'opposite': cm < 0,
                    'gap': round(float(np.median(d[r0:r1 + 1])), 2), 'lim': lim})
    for n in sorted(inc):
        lst = inc[n]
        if len(lst) < 2:
            continue
        r = max(E[i]['width'] for i, _ in lst) / 2 if len(lst) >= 3 else 0.0
        for x in range(len(lst)):
            for y in range(x + 1, len(lst)):
                (i, ei), (j, ej) = lst[x], lst[y]
                if i == j:
                    continue
                A, B = E[i], E[j]
                ang = math.degrees(math.acos(max(-1.0, min(1.0, float(heading(P[i], ei) @ heading(P[j], ej))))))
                if ang >= ACUTE_MAX_DEG:
                    continue
                lim = (A['width'] + B['width']) / 2
                spikes = []
                for k_, ek, other in ((i, ei, j), (j, ej, i)):
                    sp, t = samples(P[k_][::-1] if ek else P[k_])
                    d = shapely.distance(shapely.points(sp), L[other])
                    k = 0
                    while k < len(d) and (d[k] < lim - 0.25 or t[k] <= r):
                        k += 1
                    spikes.append(float(t[min(k, len(t) - 1)]))
                spike = max(spikes) - r
                if spike < MIN_RUN:
                    continue
                a_, b_ = (i, j) if i < j else (j, i)
                out.append({'kind': 'split', 'i': a_, 'j': b_, 'node': n, 'angle': round(ang, 1), 'spike': round(spike, 1),
                            'disc_r': r, 'lim': lim, 'end_i': (ei if a_ == i else ej), 'end_j': (ej if a_ == i else ei)})
    return out


LINK_KINDS = ('opposite', 'same_direction', 'two_way', 'unnamed_dual')


def load_config(root=ROOT):
    """tools/mapgen/config/dual.json (optional): exclude_link_kinds (any of LINK_KINDS) and exclude_groups (group ids
    as the plan prints them, "g:<edge id>"): those pairs are not merged; they fall to rule b / c like different roads"""
    p = os.path.join(root, 'tools', 'mapgen', 'config', 'dual.json')
    cfg = json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}
    bad = set(cfg.get('exclude_link_kinds', [])) - set(LINK_KINDS)
    if bad:
        sys.exit(f'dual.json: unknown exclude_link_kinds {sorted(bad)} (known: {LINK_KINDS})')
    return {'exclude_link_kinds': set(cfg.get('exclude_link_kinds', [])), 'exclude_groups': set(cfg.get('exclude_groups', []))}


def merge_kind(A, B, pr):
    """the rule-a link kind of a pair, or None: same name (normalised) and parallel / a dual split; or an unnamed pair
    of one-way ways of one class running opposite"""
    named = bool(names(A) & names(B))
    unnamed = not names(A) and not names(B) and A['oneway'] and B['oneway'] and A['class'] == B['class'] and (
        pr['kind'] == 'parallel' and pr['opposite'] and pr['run'] >= SPLIT_SPIKE or
        pr['kind'] == 'split' and (A['a'] == pr['node']) != (B['a'] == pr['node']))
    if not (named or unnamed) or not (pr['kind'] == 'parallel' or pr['spike'] > SPLIT_SPIKE):
        return None
    if unnamed and not named:
        return 'unnamed_dual'
    if not (A['oneway'] and B['oneway']):
        return 'two_way'
    if pr['kind'] == 'parallel':
        opp = pr['opposite']
    else:                                       # both leave the node: one drives in, one out = opposite
        opp = (A['a'] == pr['node']) != (B['a'] == pr['node'])
    return 'opposite' if opp else 'same_direction'


def components(links):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i in sorted(links):
        for j in sorted(links[i]):
            parent[find(i)] = find(j)
    comps = defaultdict(list)
    for i in sorted(links):
        comps[find(i)].append(i)
    return [sorted(c) for _, c in sorted(comps.items(), key=lambda kv: min(kv[1]))]


def group_id(E, members):
    """stable id of a merge group: its member with the lowest edge index (graph order never changes)"""
    return 'g:' + E[min(members)]['id']


def classify(E, P, pairs, movable=None, cfg=None):
    """roles from the pairs: merge components (kept / hidden), trims, offsets, residual"""
    cfg = cfg if cfg is not None else load_config()
    lens = [plen(p) for p in P]
    # which pairs may merge: link kind not excluded, and their (provisional) group not excluded
    cand = defaultdict(set)
    for pr in pairs:
        pr['mkind'] = merge_kind(E[pr['i']], E[pr['j']], pr)
        if pr['mkind'] and pr['mkind'] not in cfg['exclude_link_kinds']:
            cand[pr['i']].add(pr['j']); cand[pr['j']].add(pr['i'])
    gid = {}
    for c in components(cand):
        for i in c:
            gid[i] = group_id(E, c)
    merge_links = defaultdict(set)
    trims, offsets, residual, classes = [], [], [], defaultdict(int)
    for pr in pairs:
        A, B = E[pr['i']], E[pr['j']]
        mk = pr['mkind']
        if mk and (mk in cfg['exclude_link_kinds'] or gid.get(pr['i']) in cfg['exclude_groups']):
            classes['merge_excluded_by_config'] += 1
            mk = None
        if mk:
            merge_links[pr['i']].add(pr['j']); merge_links[pr['j']].add(pr['i'])
            pr['rule'] = 'merge'
            classes['merge_' + mk] += 1
            continue
        pi, pj = priority(A, lens[pr['i']]), priority(B, lens[pr['j']])
        minor, major = (pr['j'], pr['i']) if pi <= pj else (pr['i'], pr['j'])
        if pr['kind'] == 'split':
            end = pr['end_i'] if minor == pr['i'] else pr['end_j']
            trims.append({'edge': minor, 'end': 'b' if end else 'a', 'node': pr['node'], 'major': major})
            pr['rule'] = 'trim'
            classes['trim_acute' if pr['spike'] <= SPLIT_SPIKE else 'trim_split'] += 1
            continue
        # parallel, different roads: where along the minor edge?
        M = E[minor]
        Lm = LineString(P[minor])
        if pr['short'] == minor:
            s0, s1, Lmin = pr['s0'], pr['s1'], pr['len_short']
        else:                                   # project the overlap run onto the minor edge
            sp, t = samples(P[minor])
            d = shapely.distance(shapely.points(sp), LineString(P[major]))
            ov = d < pr['lim'] - 0.25
            rr = runs_of(ov)
            if not rr:
                continue
            r0, r1 = max(rr, key=lambda r: (r[1] - r[0], -r[0]))
            s0, s1, Lmin = float(t[r0]), float(t[r1]), float(t[-1])
        near_a, near_b = s0 <= pr['lim'] + 10, Lmin - s1 <= pr['lim'] + 10
        mov = movable is not None and movable(M)
        shift = (M['width'] + E[major]['width']) / 2 + OFFSET_CLEAR - pr['gap']
        fits = s0 >= OFFSET_RAMP and Lmin - s1 >= OFFSET_RAMP
        if is_link(M) or E[major]['tier'] == 'express' and M['tier'] == 'express':
            kind = 'link'
        else:
            kind = 'road'
        if kind == 'road' and mov and fits and shift <= OFFSET_MAX:
            offsets.append({'edge': minor, 'major': major, 's0': s0, 's1': s1, 'gap': pr['gap'], 'lim': pr['lim']})
            pr['rule'] = 'offset'
            classes['offset'] += 1
        else:
            # slip road, or a road that cannot be moved (base slice, overlap too close to its end nodes, too far):
            # its slab goes where it overlaps the other road, and that part is rebuilt as fill (lossless)
            trims.append({'edge': minor, 'end': 'a' if near_a or not near_b else 'b',
                          'node': M['a'] if near_a or not near_b else M['b'], 'major': major, 'parallel': True})
            pr['rule'] = 'trim'
            if kind == 'link':
                classes['trim_slip_road'] += 1
            else:
                classes['trim_parallel_' + ('end' if near_a or near_b else 'base_edge' if not mov else
                                            'no_room_for_ramps' if not fits else 'shift_too_large')] += 1
    # merge components, then greedy kept / hidden (no two kept edges overlap)
    groups = []
    link_kinds = defaultdict(lambda: defaultdict(int))
    for pr in pairs:
        if pr.get('rule') == 'merge':
            link_kinds[min(pr['i'], pr['j'])][pr['mkind']] += 1
    for comp in components(merge_links):
        mem = sorted(comp, key=lambda i: (priority(E[i], lens[i]), i))
        kept, hidden = [], []
        for i in mem:
            (hidden if any(j in merge_links[i] for j in kept) else kept).append(i)
        kinds = defaultdict(int)
        for i in comp:
            for k, v in link_kinds.get(i, {}).items():
                kinds[k] += v
        groups.append({'kept': sorted(kept), 'hidden': sorted(hidden), 'id': group_id(E, comp), 'link_kinds': dict(kinds)})
    return {'groups': groups, 'trims': trims, 'offsets': offsets, 'residual': residual, 'classes': dict(classes),
            'links': {i: sorted(v) for i, v in merge_links.items()}}


# ---- rule a: the merged centreline ---------------------------------------------------------------------------------
def merge_line(K, W, partners, pin_a=False, pin_b=False, step=2.0):
    """kept edge polyline K (width W) shifted sideways towards its hidden partners [(polyline, width), ...]: at every
    point by half the lateral offset to the partner (centred between the two centrelines; with partners on both sides,
    centred on their extent), fading out where the partner's gap grows past min(lim, W - 2 MARGIN) (+ TAPER_GAP) and
    over PIN_RAMP studs before a pinned end (the road continues there un-merged). Returns a dense polyline."""
    q, s = resample(K, step)
    if len(q) < 2:
        return q
    tq = tangents(q)
    nq = np.stack([-tq[:, 1], tq[:, 0]], axis=1)
    o_pos, o_neg = np.zeros(len(q)), np.zeros(len(q))
    pts = shapely.points(q)
    for H, wh in partners:
        lh = LineString(H)
        sh = shapely.line_locate_point(lh, pts)
        qh = np.array([[g.x, g.y] for g in shapely.line_interpolate_point(lh, sh)])
        a_ = np.array([[g.x, g.y] for g in shapely.line_interpolate_point(lh, np.maximum(sh - 1, 0))])
        b_ = np.array([[g.x, g.y] for g in shapely.line_interpolate_point(lh, np.minimum(sh + 1, lh.length))])
        th = b_ - a_
        th /= (np.linalg.norm(th, axis=1, keepdims=True) + 1e-12)
        par = np.abs(np.sum(th * tq, axis=1)) >= math.cos(math.radians(PARALLEL_MAX_DEG))
        vec = qh - q
        d = np.linalg.norm(vec, axis=1)
        lim = (W + wh) / 2
        d1 = min(lim, W - 2 * MARGIN)
        w = smoothstep((d1 + TAPER_GAP - d) / TAPER_GAP) * par
        o = np.sum(vec * nq, axis=1) * w
        o_pos = np.maximum(o_pos, o); o_neg = np.minimum(o_neg, o)
    sh_ = 0.5 * (o_pos + o_neg)
    # smoothing (gaussian, window shrinking to zero at both ends so an end keeps its raw value: two kept edges meeting
    # at a node get the same shift there)
    if len(sh_) > 2:
        sm = np.empty_like(sh_)
        L = s[-1]
        for k in range(len(sh_)):
            sig = min(SMOOTH_SIGMA, s[k] / 2, (L - s[k]) / 2)
            if sig < 0.5:
                sm[k] = sh_[k]; continue
            w = np.exp(-0.5 * ((s - s[k]) / sig) ** 2)
            w[np.abs(s - s[k]) > 3 * sig] = 0
            sm[k] = float((w * sh_).sum() / w.sum())
        sh_ = sm
    if pin_a:
        sh_ = sh_ * smoothstep(s / PIN_RAMP)
    if pin_b:
        sh_ = sh_ * smoothstep((s[-1] - s) / PIN_RAMP)
    # the merged line may turn away from the old one by at most atan(SHIFT_SLOPE): Lipschitz minorant of each sign's
    # shift (only ever less shift, never more, so no new overlap; the hidden carriageway's fill takes up the rest)
    for sgn in (1.0, -1.0):
        mag = np.maximum(sgn * sh_, 0.0)
        if mag.any():
            lim_ = np.min(mag[None, :] + SHIFT_SLOPE * np.abs(s[:, None] - s[None, :]), axis=1)
            sh_ = np.where(sgn * sh_ > 0, sgn * np.minimum(mag, lim_), sh_)
    return q + nq * sh_[:, None]


def pins(E, P, members, i):
    """is the kept edge i pinned at a / b (the road continues there straight on into an edge that is not a member of
    the same merge component - another road -, so the merged centreline must come back to the node)?"""
    out = []
    for at_b in (False, True):
        n = E[i]['b'] if at_b else E[i]['a']
        h = -heading(P[i], at_b)                         # driving on through n
        pin = False
        for j, (e, p) in enumerate(zip(E, P)):
            if j == i or n not in (e['a'], e['b']):
                continue
            hj = heading(p, e['b'] == n)
            if float(h @ hj) > math.cos(math.radians(PARALLEL_MAX_DEG)) and j not in members:
                pin = True
        out.append(pin)
    return out


# ---- the plan (graph level) ----------------------------------------------------------------------------------------
def load_graph_edges(root=ROOT):
    """every edge the three datasets export: the wide graph (central edges flagged base, first) and the corridor edges
    left after export_corridor's wide dedupe. Each edge gets 'ds' (central / wide / corridor) and 'P' (chunk polyline)."""
    sys.path.insert(0, os.path.join(root, 'tools', 'circuit'))
    w = json.load(open(os.path.join(root, GRAPHS[1][1]), encoding='utf-8'))
    E = []
    for e in w['edges']:
        E.append(dict(e, ds='central' if e.get('base') else 'wide'))
    cp = os.path.join(root, GRAPHS[2][1])
    if os.path.exists(cp):
        import copy
        from export_corridor import wide_dedupe
        cor = json.load(open(cp, encoding='utf-8'))
        city_nodes = set(n for e in w['edges'] for n in (e['a'], e['b']))
        nodes_xy = dict(w['nodes']); nodes_xy.update(cor['nodes'])
        for e in wide_dedupe(w['edges'], copy.deepcopy(cor['edges']), city_nodes, nodes_xy, quiet=True):
            E.append(dict(e, ds='corridor'))
    return E


def graph_hashes(root=ROOT):
    out = {}
    for _, rel in GRAPHS:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            out[rel] = hashlib.sha1(open(p, 'rb').read()).hexdigest()
    return out


def refine_groups(E, P, cl, log=print):
    """two kept edges of one group must not overlap AFTER their centrelines moved (three carriageways side by side:
    both outer ones shift towards the hidden middle one). Recompute the merged lines, and hide the less important of
    every pair of kept edges whose merged slabs overlap; repeat until none is left."""
    lens = [plen(p) for p in P]
    for it in range(8):
        merged, owner = [], []
        for gi, g in enumerate(cl['groups']):
            mem = set(g['kept'] + g['hidden'])
            hid = [(P[h], E[h]['width']) for h in g['hidden']]
            for k in g['kept']:
                pa, pb = pins(E, P, mem, k)
                merged.append(chunk_line(merge_line(P[k], E[k]['width'], hid, pa, pb))); owner.append((gi, k))
        sub = [E[k] for _, k in owner]
        prs = find_pairs(sub, merged)
        demote = {}
        for pr in prs:
            (ga, a), (gb, b) = owner[pr['i']], owner[pr['j']]
            if ga != gb:
                continue
            if pr['kind'] == 'split' and pr['spike'] <= SPLIT_SPIKE:
                continue                                  # an acute touch at a node: a trim handles it
            lo = b if (priority(E[a], lens[a]), a) <= (priority(E[b], lens[b]), b) else a
            demote[lo] = ga
        if not demote:
            break
        for k, gi in sorted(demote.items()):
            g = cl['groups'][gi]
            g['kept'].remove(k); g['hidden'] = sorted(g['hidden'] + [k])
        log(f'dual plan: pass {it + 1}: {len(demote)} kept edges overlap another kept edge after the merge -> hidden')
    return cl


def build_plan(root=ROOT):
    E = load_graph_edges(root)
    P = [chunk_line(e['pts']) for e in E]
    pairs = find_pairs(E, P)
    cl = classify(E, P, pairs, movable=None)
    cl = refine_groups(E, P, cl)
    # overlaps the merge itself creates (a merged centreline moved towards a road outside its group): the kept edges'
    # merged lines replace their polylines, hidden edges are left out, and every new overlapping pair becomes a trim
    merged_P = list(P)
    hidden = set()
    for g in cl['groups']:
        mem = set(g['kept'] + g['hidden'])
        hid = [(P[h], E[h]['width']) for h in g['hidden']]
        hidden |= set(g['hidden'])
        for k in g['kept']:
            pa, pb = pins(E, P, mem, k)
            merged_P[k] = chunk_line(merge_line(P[k], E[k]['width'], hid, pa, pb))
    sub = [i for i in range(len(E)) if i not in hidden]
    have = {(t['edge'], t['major']) for t in cl['trims']} | {(t['major'], t['edge']) for t in cl['trims']}
    lens = [plen(p) for p in P]
    group_of = {i: gi for gi, g in enumerate(cl['groups']) for i in g['kept'] + g['hidden']}
    n_new = 0
    for pr in find_pairs([E[i] for i in sub], [merged_P[i] for i in sub]):
        i, j = sub[pr['i']], sub[pr['j']]
        if (i, j) in have or (i not in group_of and j not in group_of):
            continue                                 # nothing merged here: the first analysis has it
        if i in group_of and group_of.get(i) == group_of.get(j):
            continue                                 # two kept edges of one group: refine_groups has it
        minor, major = (j, i) if (priority(E[i], lens[i]), i) <= (priority(E[j], lens[j]), j) else (i, j)
        if pr['kind'] == 'split':
            end = pr['end_i'] if minor == i else pr['end_j']
            cl['trims'].append({'edge': minor, 'end': 'b' if end else 'a', 'node': pr['node'], 'major': major})
        else:
            cl['trims'].append({'edge': minor, 'end': 'a', 'node': E[minor]['a'], 'major': major, 'parallel': True})
        cl['classes']['trim_after_merge'] = cl['classes'].get('trim_after_merge', 0) + 1
        have |= {(minor, major), (major, minor)}
        n_new += 1
    groups = []
    for g in cl['groups']:
        ways = sorted({E[i]['way'] for i in g['kept'] + g['hidden']})
        kept = set(g['kept'])
        groups.append({'id': g['id'], 'link_kinds': g['link_kinds'],
                       'kept': [E[i]['id'] for i in g['kept']], 'hidden': [E[i]['id'] for i in g['hidden']],
                       'pins': {E[i]['id']: pins(E, P, set(g['kept'] + g['hidden']), i) for i in g['kept']},
                       'ways': ways, 'names': sorted({E[i].get('name_en') or E[i].get('name') or '' for i in g['kept'] + g['hidden']}),
                       'datasets': sorted({E[i]['ds'] for i in g['kept'] + g['hidden']}), 'directions': None})
    # one-way direction mix per group (for the traffic lane clamp): all one-way and all running the same way?
    for g, gg in zip(groups, cl['groups']):
        mem = gg['kept'] + gg['hidden']
        same_dir = all(E[i]['oneway'] for i in mem)
        if same_dir:
            ref = heading(P[gg['kept'][0]], False)
            for i in mem:
                # compare with the nearest kept edge's direction at this edge's middle
                mid = P[i][len(P[i]) // 2]
                k = min(gg['kept'], key=lambda k: LineString(P[k]).distance(Point(mid)))
                lk = LineString(P[k])
                s0 = lk.project(Point(mid))
                a_, b_ = lk.interpolate(max(s0 - 2, 0)), lk.interpolate(min(s0 + 2, lk.length))
                tk = np.array([b_.x - a_.x, b_.y - a_.y])
                li = LineString(P[i])
                s1 = li.project(Point(mid))
                c_, d_ = li.interpolate(max(s1 - 2, 0)), li.interpolate(min(s1 + 2, li.length))
                ti = np.array([d_.x - c_.x, d_.y - c_.y])
                if float(tk @ ti) < 0:
                    same_dir = False
        g['directions'] = 'same' if same_dir else 'both'
    trims = [{'edge': E[t['edge']]['id'], 'end': t['end'], 'node': t['node'], 'major': E[t['major']]['id'],
              'parallel': bool(t.get('parallel'))} for t in cl['trims']]
    residual = [{'edge': E[r['edge']]['id'], 'major': E[r['major']]['id'], 'why': r['why'], 'gap': r['gap'], 'lim': r['lim']}
                for r in cl['residual']]
    offsets = [{'edge': E[o['edge']]['id'], 'major': E[o['major']]['id'], 'gap': o['gap'], 'lim': o['lim']} for o in cl['offsets']]
    roles = {}
    for gi, g in enumerate(groups):
        for k in g['kept']:
            roles[k] = {'role': 'keep', 'group': gi}
        for h in g['hidden']:
            roles[h] = {'role': 'hide', 'group': gi}
    plan = {'about': 'tools/mapgen/dual.py plan: merge groups (rule a), trims (rule c); see docs/ROAD_AUDIT.md',
            'graphs': graph_hashes(root), 'groups': groups, 'roles': roles, 'trims': trims,
            'offsets_left': offsets, 'residual': residual, 'classes': cl['classes'],
            'stats': {'pairs': len(pairs), 'groups': len(groups), 'kept': sum(len(g['kept']) for g in groups),
                      'hidden': sum(len(g['hidden']) for g in groups), 'trims': len(trims), 'residual': len(residual)}}
    return plan, E, P


def load_plan(root=ROOT, check=True):
    p = os.path.join(root, PLAN)
    if not os.path.exists(p):
        return None
    plan = json.load(open(p, encoding='utf-8'))
    if check:
        now = graph_hashes(root)
        stale = [k for k, v in plan['graphs'].items() if now.get(k) != v]
        if stale:
            sys.exit(f'{PLAN} is stale ({stale} changed since): run tools/mapgen/dual.py again')
    return plan


# ---- traffic lanes on merged roads ---------------------------------------------------------------------------------
class MergeField:
    """merged centrelines of every plan group at graph resolution (for the traffic lanes): for a point of a merged
    edge, the merged centre and the merged slab width. Edges are found by id, else by OSM way (the corridor's own copies
    of city ways in corridor_traffic.py)."""

    def __init__(self, plan, edges_by_id):
        self.groups = []
        self.by_id, self.by_way = {}, {}
        for gi, g in enumerate(plan['groups']):
            hid = [(np.asarray(edges_by_id[h]['pts'], float), edges_by_id[h]['width']) for h in g['hidden'] if h in edges_by_id]
            lines = []
            for k in g['kept']:
                if k not in edges_by_id:
                    continue
                e = edges_by_id[k]
                pa, pb = g['pins'].get(k, [False, False])
                m = merge_line(np.asarray(e['pts'], float), e['width'], hid, pa, pb)
                lines.append((LineString(m), e['width']))
            self.groups.append({'lines': lines, 'same': g['directions'] == 'same'})
            for i in g['kept'] + g['hidden']:
                self.by_id[i] = gi
            for w in g['ways']:
                self.by_way.setdefault(w, gi)

    def group_of(self, e):
        gi = self.by_id.get(e['id'])
        if gi is None:
            gi = self.by_way.get(e['way'])
        return gi

    def adjust(self, e, p, left, lane):
        """lane offsets (per point, along `left`) for edge e's points p (driving order), given the lane offset the
        plain rule chose: inside a merged slab the lane is measured from the merged centre and kept inside the slab
        (opposite directions: on the left half of the merged road, Thailand drives on the left)."""
        gi = self.group_of(e)
        out = np.full(len(p), float(lane))
        if gi is None or not self.groups[gi]['lines']:
            return out
        G = self.groups[gi]
        pts = shapely.points(p)
        best_d = np.full(len(p), np.inf)
        M = np.zeros_like(p)
        Wb = np.zeros(len(p))
        for ln, W in G['lines']:
            s = shapely.line_locate_point(ln, pts)
            q = np.array([[g.x, g.y] for g in shapely.line_interpolate_point(ln, s)])
            d = np.linalg.norm(q - p, axis=1)
            better = d < best_d
            best_d[better] = d[better]; M[better] = q[better]; Wb[better] = W
        s_left = np.sum((p - M) * left, axis=1)              # own centreline relative to the merged centre
        hi = Wb / 2 - LANE_W / 4
        lo = -hi if G['same'] else np.full(len(p), LANE_W / 4)
        eff = np.clip(s_left + lane, lo, hi)
        blend = smoothstep((Wb / 2 + 10 - best_d) / (10 + MARGIN))   # 1 inside the merged slab, 0 where the edge left it
        return lane + blend * (eff - s_left - lane)


# ---- rule b: offsets in the gameplay transform ----------------------------------------------------------------------
def apply_offsets(game_edges, cfg, log=print):
    """rule b on graph_game edges (wide world): shift the minor road of every parallel pair of DIFFERENT roads
    sideways, interior points only (end nodes never move), with OFFSET_RAMP transitions. Returns {edge id: info}."""
    movable_ok = lambda e: not e.get('base')
    E = game_edges
    P = [chunk_line(e['pts']) for e in E]
    pairs = find_pairs(E, P)
    cl = classify(E, P, pairs, movable=movable_ok)
    done = {}
    by_edge = defaultdict(list)
    for o in cl['offsets']:
        by_edge[o['edge']].append(o)
    for i in sorted(by_edge):
        e = E[i]
        p = np.asarray(e['pts'], float)
        seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
        s = np.concatenate([[0], np.cumsum(seg)])
        Ltot = s[-1]
        t = tangents(p)
        nrm = np.stack([-t[:, 1], t[:, 0]], axis=1)
        disp = np.zeros(len(p))
        for o in by_edge[i]:
            M = E[o['major']]
            lm = LineString(M['pts'])
            # side of the major road, at the middle of the overlap
            mid = LineString(p).interpolate((o['s0'] + o['s1']) / 2)
            k = int(np.argmin(np.abs(s - (o['s0'] + o['s1']) / 2)))
            q = lm.interpolate(lm.project(mid))
            side = -1.0 if float((np.array([q.x, q.y]) - np.array([mid.x, mid.y])) @ nrm[k]) > 0 else 1.0
            need = (e['width'] + M['width']) / 2 + OFFSET_CLEAR + (e['sidewalk'] if e['sidewalk'] > 0 else 0) \
                + (M['sidewalk'] if M['sidewalk'] > 0 else 0)
            d_all = shapely.distance(shapely.points(p), lm)
            amt = np.clip(need - d_all, 0, OFFSET_MAX)
            amt[(s < o['s0'] - 2) | (s > o['s1'] + 2)] = 0
            peak = float(amt.max()) if len(amt) else 0.0
            if peak <= 0:
                continue
            a0, a1 = max(o['s0'] - 2, OFFSET_RAMP), min(o['s1'] + 2, Ltot - OFFSET_RAMP)
            if a1 <= a0:
                continue
            ramp = np.where(s < a0, smoothstep((s - (a0 - OFFSET_RAMP)) / OFFSET_RAMP),
                            np.where(s > a1, smoothstep(((a1 + OFFSET_RAMP) - s) / OFFSET_RAMP), 1.0))
            disp = np.where(np.abs(side * peak * ramp) > np.abs(disp), side * peak * ramp, disp)
        if not np.any(disp):
            continue
        disp[0] = disp[-1] = 0.0
        q = p + nrm * disp[:, None]
        e['pts'] = [[round(float(x), 2), round(float(z), 2)] for x, z in q]
        done[e['id']] = {'len0': round(float(Ltot), 3), 'max_shift': round(float(np.abs(disp).max()), 2),
                         'major': [E[o['major']]['id'] for o in by_edge[i]]}
    log(f"dual offsets (rule b): {len(done)} edges shifted sideways (max {max([v['max_shift'] for v in done.values()] or [0]):.1f} studs); "
        f"pairs {len(pairs)}, classes {cl['classes']}")
    return done


# ---- rule a / c on the exported chunk lines (road_fix.py rule D) ----------------------------------------------------
def fill_triangles(poly, min_area=0.5):
    """flat triangles exactly covering a polygon (constrained Delaunay), slivers dropped"""
    out = []
    geoms = getattr(poly, 'geoms', [poly])
    for g in geoms:
        if g.geom_type != 'Polygon' or g.area < 2.0:
            continue
        g = g.simplify(0.3, preserve_topology=True)
        if g.is_empty or g.area < 2.0:
            continue
        tri = shapely.constrained_delaunay_triangles(g)
        for t in getattr(tri, 'geoms', [tri]):
            if t.area < min_area:
                continue
            c = list(t.exterior.coords)[:3]
            # drop needles (height < 0.2 studs over the longest side)
            ls = [math.dist(c[k], c[(k + 1) % 3]) for k in range(3)]
            if 2 * t.area / max(ls) < 0.2:
                continue
            out.append([round(v, 2) for xy in c for v in xy])
    return out


def apply_chunk(edges, discs, plan, rc, smooth=None, keep_points=(), blockers=(), log=print):
    """road_fix.py rule D: merged centrelines / hidden edges / cuts / fills on the exported chunk edges (road_fix edge
    dicts: 'pts' arrays of the chunk line, width, ...). Sets per edge: pts (kept edges), merged, oneway, lanes, sidewalk
    (kept), hidden, cutA, cutB, fill. Returns stats."""
    by_id = {}
    for i, e in enumerate(edges):
        by_id.setdefault(e['id'], i)
    stats = defaultdict(int)
    disc_list = [(x, z, r, (k[1] if isinstance(k, tuple) else k)) for (ds, k), (x, z, r) in sorted(discs.items(), key=lambda kv: str(kv[0]))]
    # --- a: merged centrelines of the kept edges
    kept_of = {}
    for gi, g in enumerate(plan['groups']):
        hid = [(edges[by_id[h]]['pts'], edges[by_id[h]]['width']) for h in g['hidden'] if h in by_id]
        same = g['directions'] == 'same'
        for k in g['kept']:
            if k not in by_id:
                continue
            e = edges[by_id[k]]
            pa, pb = g['pins'].get(k, [False, False])
            m = merge_line(e['pts'], e['width'], hid, pa, pb)
            q = np.round(chunk_line(m), 2)
            if smooth is not None:                      # road_fix rule K on the merged line too
                q = smooth(q)
            e['pts'] = q
            e['pts_changed'] = True
            e['merged'] = True
            e['sidewalk'] = e.get('sidewalk_graph', e['sidewalk'])
            e['swSide'] = None
            if not same and e['oneway']:
                e['oneway'] = False
                e['lanes'] = max(2, int(round(e['width'] / LANE_W / 2)) * 2)
            stats['kept_edges'] += 1
            kept_of.setdefault(gi, []).append(by_id[k])
    # --- per-edge state on samples every STEP studs along the chunk line: `gone` = no slab built there, `fill` = rebuild
    # that part of the old slab as fill triangles (minus every other road surface); turned into cutA / cutB / hide
    # ranges at the end
    hidden_ids = {h for g in plan['groups'] for h in g['hidden']}
    state = {}

    def st(j):
        if j not in state:
            sp, t = samples(edges[j]['pts'])
            state[j] = {'sp': sp, 't': t, 'gone': np.zeros(len(t), bool), 'fill': np.zeros(len(t), bool)}
        return state[j]

    def ranges_of(j):
        """gone runs -> [a, b] arc ranges (boundaries on the neighbouring built samples)"""
        s_ = state[j]
        t, gone = s_['t'], s_['gone']
        L, n_ = float(t[-1]), len(t)
        out = []
        for r0, r1 in runs_of(gone):
            out.append([0.0 if r0 == 0 else float(t[r0 - 1]), L if r1 == n_ - 1 else float(t[r1 + 1])])
        return out

    def pieces_of(j):
        e = edges[j]
        if j not in state or not state[j]['gone'].any():
            return [e['pts']]
        rr = ranges_of(j)
        L = float(state[j]['t'][-1])
        ca = rr.pop(0)[1] if rr and rr[0][0] <= 0 else 0.0
        cb = L - rr.pop(-1)[0] if rr and rr[-1][1] >= L else 0.0
        return rc.slab_pieces(dict(e, cutA=ca, cutB=cb, hide=[v for r_ in rr for v in r_], hidden=False))

    def disc_r(n):
        return max([r for x, z, r, key in disc_list if key == n] or [0.0])

    def trim_one(tr, minor_ok):
        """rule c on one trim entry: the minor edge's slab goes where it overlaps the major road (from the node while
        they overlap; along the whole edge for a parallel pair), and that part is rebuilt as fill (lossless)"""
        if tr['edge'] not in by_id or tr['major'] not in by_id or not minor_ok(tr['edge']):
            return
        j = by_id[tr['edge']]
        e = edges[j]
        majors = [by_id[tr['major']]]
        g_of = plan['roles'].get(tr['major'])
        if g_of and g_of['role'] == 'hide':            # the major road is hidden: the merged slab stands in
            majors = kept_of.get(g_of['group'], []) + majors
        s_ = st(j)
        pts = shapely.points(s_['sp'])
        over = np.zeros(len(s_['t']), bool)
        for m in majors:
            if m == j:
                continue
            for q in pieces_of(m) if not (edges[m]['id'] in hidden_ids and m not in state) else []:
                over |= shapely.distance(pts, LineString(q)) < (e['width'] + edges[m]['width']) / 2 - 0.25
        if not over.any():
            return
        t = s_['t']
        if tr.get('parallel'):
            mask = over
        else:
            r = disc_r(tr['node'])
            mask = np.zeros(len(t), bool)
            idx = range(len(t)) if tr['end'] == 'a' else range(len(t) - 1, -1, -1)
            L = t[-1]
            seen = False
            for k in idx:
                dist_node = t[k] if tr['end'] == 'a' else L - t[k]
                if over[k] or dist_node <= r:
                    mask[k] = True
                    seen = seen or over[k]
                else:
                    break
            if not seen:
                return
        s_['gone'] |= mask
        s_['fill'] |= mask
        stats['trims'] += 1

    # --- c: trims of edges that are not hidden carriageways (first: a kept edge may be cut too)
    for tr in plan['trims']:
        trim_one(tr, lambda i: i not in hidden_ids)
    # --- a: hidden carriageways. Per group, in importance order, against the merged surface (the kept edges' slabs as
    # built, then every carriageway already decided): a hidden carriageway builds its slab only where it is clear of
    # that surface; the stretches where its centreline is not inside the surface (the transition where it leaves) are
    # rebuilt as fill, the covered stretches are simply not built (one slab: the merged one).
    lens_ = [plen(e['pts']) for e in edges]
    for gi, g in enumerate(plan['groups']):
        ks = kept_of.get(gi, [])
        if not ks:
            continue
        surf = [(q, edges[k]['width']) for k in ks for q in pieces_of(k)]
        hs = sorted((by_id[h] for h in g['hidden'] if h in by_id), key=lambda j: (priority(edges[j], lens_[j]), j))
        for j in hs:
            e = edges[j]
            polys = [r_ for q, w in surf for r_ in rc.stripe_rects(q, w)]
            if not polys:
                break
            kslab = shapely.union_all(polys)
            kcore = kslab.buffer(-MARGIN, join_style=2)
            shapely.prepare(kslab); shapely.prepare(kcore)
            s_ = st(j)
            t = s_['t']
            pts = shapely.points(s_['sp'])
            cov = shapely.contains(kcore, pts)          # centreline inside the merged surface (MARGIN studs in)
            for n in (e['a'], e['b']):                  # ... or inside one of its own junction discs
                for x, z, r, key in disc_list:
                    if key == n:
                        cov |= np.hypot(s_['sp'][:, 0] - x, s_['sp'][:, 1] - z) <= r - MARGIN
            hid = shapely.distance(kslab, pts) < e['width'] / 2 - 0.25      # its slab would touch the surface
            for q, w in surf:                                                # (also by the centreline-gap rule)
                hid |= shapely.distance(pts, LineString(q)) < (w + e['width']) / 2 - 0.25
            s_['gone'] |= hid
            s_['fill'] |= hid & ~cov
            surf += [(q, e['width']) for q in pieces_of(j)]  # what stays of it joins the merged surface
        # roads ending at a node of the merged carriageways (cross streets, connectors through the old median): their
        # slab end is cut back to where it is no longer fully inside the merged surface (+ that node's disc), so it
        # does not lie on the merged slab (nothing to fill: the merged slab is under it)
        members = {by_id[i] for i in g['kept'] + g['hidden'] if i in by_id}
        gnodes = {edges[i][k] for i in members for k in ('a', 'b')}
        polys = [r_ for q, w in surf for r_ in rc.stripe_rects(q, w)]
        if not polys:
            continue
        gsurf = shapely.union_all(polys)
        for j in range(len(edges)):
            e = edges[j]
            if j in members or e.get('hidden') or not ({e['a'], e['b']} & gnodes):
                continue
            s_ = st(j)
            t, sp = s_['t'], s_['sp']
            tq = tangents(sp)
            nq = np.stack([-tq[:, 1], tq[:, 0]], axis=1) * (e['width'] / 2 - 0.05)
            for end in ('a', 'b'):
                n = e[end]
                if n not in gnodes:
                    continue
                area = gsurf
                dr = [(x, z, r) for x, z, r, key in disc_list if key == n]
                if dr:
                    area = gsurf.union(Point(dr[0][0], dr[0][1]).buffer(dr[0][2], 32))
                inl = shapely.contains(area, shapely.points(sp + nq)) & shapely.contains(area, shapely.points(sp - nq))
                idx = range(len(t)) if end == 'a' else range(len(t) - 1, -1, -1)
                run = []
                for k in idx:
                    if not inl[k]:
                        break
                    run.append(k)
                if len(run) > 1:
                    s_['gone'][run] = True
                    stats['cross_street_ends_cut'] += 1
    # --- c again, every trim: the hidden carriageways (as minor or as major road) are decided now
    for tr in plan['trims']:
        trim_one(tr, lambda i: True)
    # --- masks -> cutA / cutB / hide ranges and fill zones
    fill_zone = {}
    for j in sorted(state):
        s_ = state[j]
        t, gone = s_['t'], s_['gone']
        n_ = len(t)
        for r0, r1 in runs_of(~gone):                   # short built gaps between two gone stretches: gone + fill
            if r0 > 0 and r1 < n_ - 1 and t[r1] - t[r0] < 12:
                gone[r0:r1 + 1] = True; s_['fill'][r0:r1 + 1] = True
        for r0, r1 in runs_of(gone):                    # touches shorter than 2 studs: built
            if t[r1] - t[r0] < 2 and 0 < r0 and r1 < n_ - 1:
                gone[r0:r1 + 1] = False
        if not gone.any():
            continue
        e = edges[j]
        L = float(t[-1])
        rr = ranges_of(j)
        zones = []
        for r0, r1 in runs_of(s_['fill'] & gone):
            zones.append((max(float(t[r0]) - 4.0, 0.0), min(float(t[r1]) + 4.0, L)))
        ca = rr.pop(0)[1] if rr and rr[0][0] <= 0 else 0.0
        cb = L - rr.pop(-1)[0] if rr and rr[-1][1] >= L else 0.0
        visible = (L - ca - cb) - sum(b_ - a_ for a_, b_ in rr)
        if visible <= 2.5:
            e['hidden'] = True
            e['cutA'] = e['cutB'] = 0.0
            stats['hidden_edges' if e['id'] in hidden_ids else 'trimmed_away_edges'] += 1
        else:
            e['cutA'], e['cutB'] = round(ca, 1), round(cb, 1)
            if rr:
                e['hide'] = [round(v, 1) for r_ in rr for v in r_]
                if e['sidewalk'] > 0:                   # no kerb on a carriageway in pieces
                    e['sidewalk'] = 0
                    e['swSide'] = None
            stats['partly_hidden_carriageways' if e['id'] in hidden_ids else 'cut_edges'] += 1
        if zones:
            fill_zone[j] = zones
    stats['hidden_carriageways_kept_whole'] = sum(1 for h in hidden_ids if h in by_id and by_id[h] not in fill_zone
                                                  and not edges[by_id[h]].get('hidden') and not edges[by_id[h]].get('cutA')
                                                  and not edges[by_id[h]].get('cutB') and not edges[by_id[h]].get('hide'))
    # --- fills: the old slab over each fill zone minus every other road surface (final slabs, discs, earlier fills)
    surf, owner = [], []
    for i, e in enumerate(edges):
        for vp in rc.slab_pieces(e):
            for r_ in rc.stripe_rects(vp, e['width']):
                surf.append(r_); owner.append(i)
    for x, z, r, key in disc_list:
        surf.append(Point(x, z).buffer(r, 32)); owner.append(-1)
    tree = STRtree(surf)
    # building boxes (every chunk module's buildings): fill triangles keep BUILDING_CLEAR studs away from them
    bl = [b.buffer(BUILDING_CLEAR + 0.4, join_style=2) for b in blockers]   # + the 0.3 simplify of fill_triangles
    btree = STRtree(bl) if bl else None
    # places that must stay on the road (job stands, Road Fight bosses, the race grid, the spawn: they are not moved):
    # where one would now lie off the narrower merged slab, the old slab of its edge is kept there as fill (+-25 studs)
    extra = defaultdict(list)
    if keep_points:
        now = shapely.union_all(surf)
        for kx, kz, label in keep_points:
            pt = Point(kx, kz)
            if now.buffer(-3.0).contains(pt):
                continue
            cand = [(LineString(e.get('orig_pts', e['pts'])).distance(pt), i) for i, e in enumerate(edges)
                    if e.get('merged') or e.get('hidden') or e.get('cutA') or e.get('cutB') or e.get('hide')]
            if not cand:
                continue
            d, i = min(cand)
            if d > 40:
                continue
            e = edges[i]
            op = np.asarray(e.get('orig_pts', e['pts']), float)
            ln = LineString(op)
            s0 = ln.project(pt)
            piece = rc.trim(op, max(s0 - 25, 0.0), max(ln.length - s0 - 25, 0.0))
            if piece is not None:
                extra[i] += rc.stripe_rects(piece, e['width'])
                stats['kept_on_road_points'] += 1
                log(f'dual: {label} would lie off the merged slab: old slab of {e["id"]} kept there as fill')
    fills_done = []
    for j in sorted(set(fill_zone) | set(extra)):
        e = edges[j]
        polys = list(extra.get(j, []))
        L = plen(e['pts'])
        for s0, s1 in sorted(fill_zone.get(j, [])):
            piece = rc.trim(e['pts'], max(s0, 0.0), max(L - s1, 0.0))
            if piece is None:
                continue
            polys += rc.stripe_rects(piece, e['width'])
        if not polys:
            continue
        region = shapely.union_all(polys)
        others = [surf[k] for k in tree.query(region)] + [f for f in fills_done if f.intersects(region)]
        rest = region.difference(shapely.union_all(others)) if others else region
        if btree is not None:
            near = [bl[k] for k in btree.query(rest)]
            if near:
                cut_ = rest.intersection(shapely.union_all(near)).area
                if cut_ > 0.01:
                    stats['fill_area_clipped_at_buildings'] += int(round(cut_))
                    rest = rest.difference(shapely.union_all(near))
        tris = fill_triangles(rest)
        if tris:
            e['fill'] = [v for t_ in tris for v in t_]
            fills_done.append(shapely.union_all([Polygon(np.array(t_).reshape(3, 2)) for t_ in tris]))
            stats['fill_edges'] += 1
            stats['fill_triangles'] += len(tris)
            stats['fill_area'] += int(round(sum(Polygon(np.array(t_).reshape(3, 2)).area for t_ in tris)))
    return dict(stats)


# ---- check images ----------------------------------------------------------------------------------------------------
CHECKS = [   # (file, title, world box x0, x1, z0, z1)
    ('dual_thep_prasit.png', 'Thep Prasit Road / Thepprasit Road dual carriageway', 21250, 23650, 5380, 5860),
    ('dual_slip_sukhumvit_north.png', 'Sukhumvit Road slip roads at (23,550, 4,431)', 23380, 23780, 4180, 4700),
    ('dual_slip_sukhumvit_klang.png', 'Sukhumvit Road slip roads at (24,479, 910) / (24,691, 342)', 24280, 24860, 220, 1260),
]


def render_check(before_root, after_root, box, title, path, size=1100):
    """before | after, top-down: road slabs (grey), fill triangles (orange), discs, graph centrelines (thin), merged
    centrelines (blue), hidden carriageways (red dashes along their graph line). World studs, north up."""
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, os.path.dirname(__file__))
    import road_fix as rfx
    import road_check as rc
    x0, x1, z0, z1 = box
    f = size / max(x1 - x0, z1 - z0)
    W, H = int((x1 - x0) * f), int((z1 - z0) * f)
    try:
        font = ImageFont.truetype('arial.ttf', 15)
    except OSError:
        font = ImageFont.load_default()
    panels = []
    for label, root in (('before', before_root), ('after', after_root)):
        edges, discs, _, _, _ = rfx.load(root)
        im = Image.new('RGB', (W, H), (226, 232, 220))
        d = ImageDraw.Draw(im, 'RGBA')
        T = lambda p: ((p[0] + 20000 - x0) * f, (p[1] - z0) * f)
        sel = [e for e in edges if e['pts'][:, 0].max() + 20000 > x0 - 60 and e['pts'][:, 0].min() + 20000 < x1 + 60
               and e['pts'][:, 1].max() > z0 - 60 and e['pts'][:, 1].min() < z1 + 60]
        for (x, z, r) in discs.values():
            if x0 - 80 < x + 20000 < x1 + 80 and z0 - 80 < z < z1 + 80:
                d.ellipse([T((x - r, z - r)), T((x + r, z + r))], fill=(70, 72, 80, 110))
        for e in sel:
            for q in rc.slab_pieces(e):
                for r_ in rc.stripe_rects(q, e['width']):
                    d.polygon([T(p) for p in r_.exterior.coords], fill=(70, 72, 80, 110), outline=(40, 40, 46, 140))
            for t in rc.fill_polys(e):
                d.polygon([T(p) for p in t.exterior.coords], fill=(235, 140, 30, 150))
        for e in sel:
            pts = [T(p) for p in (e.get('orig_pts') if e.get('orig_pts') is not None else e['pts'])]
            if e.get('hidden') or e.get('cutA') or e.get('cutB') or e.get('hide'):
                for k in range(0, len(pts) - 1):
                    d.line([pts[k], pts[k + 1]], fill=(200, 30, 30, 220), width=2)
            else:
                d.line(pts, fill=(20, 20, 20, 120), width=1)
            if e.get('merged'):
                d.line([T(p) for p in e['pts']], fill=(20, 60, 230, 255), width=3)
        d.rectangle([0, 0, W, 24], fill=(255, 255, 255, 200))
        d.text((8, 4), f'{label}: {title}', fill=(0, 0, 0), font=font)
        panels.append(im)
    out = Image.new('RGB', (2 * W + 10, H + 46), 'white')
    out.paste(panels[0], (0, 0)); out.paste(panels[1], (W + 10, 0))
    d = ImageDraw.Draw(out)
    d.text((8, H + 6), 'grey = road slab / disc, orange = fill triangles (rule c / transitions), blue = merged centreline (rule a), '
           'red = graph line of a hidden or cut slab (routing unchanged). World studs, north up.', fill=(0, 0, 0), font=font)
    d.text((8, H + 26), 'Map data (c) OpenStreetMap contributors, ODbL 1.0', fill=(60, 60, 60), font=font)
    out.save(path)



# ---- CLI -------------------------------------------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--png', metavar='BEFORE_ROOT', help='only write the before/after check images (docs/images/dual_*.png); '
                    'BEFORE_ROOT = a repo root whose build/ holds the modules before rule D')
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(__file__))
    if a.png:
        for fn, title, *box in CHECKS:
            render_check(a.png, a.root, box, title, os.path.join(a.root, 'docs', 'images', fn))
            print(f'docs/images/{fn}')
        return
    plan, E, P = build_plan(a.root)
    out = os.path.join(a.root, PLAN)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(plan, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
    st = plan['stats']
    print(f"dual plan: {st['pairs']} overlapping pairs -> {st['groups']} merge groups ({st['kept']} kept, {st['hidden']} hidden "
          f"edges), {st['trims']} trims, {st['residual']} residual; classes {plan['classes']} -> {PLAN}")
    for r in plan['residual'][:20]:
        print(f"  residual: {r}")


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(__file__))
    main()
