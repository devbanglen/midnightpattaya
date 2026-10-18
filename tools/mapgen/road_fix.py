"""Road fix pass over the EXPORTED chunk modules of the whole world (central slice + wide world + Bira corridor).

  .venv\\Scripts\\python tools\\mapgen\\road_fix.py            # after export_roblox.py (central, wide) and export_corridor.py
  .venv\\Scripts\\python tools\\mapgen\\road_fix.py --dry-run  # report only

Why a pass after the exporters: the problems found by road_audit.py (docs/ROAD_AUDIT.md) are where two exported road
surfaces meet each other, often across datasets (a central-slice kerb on a wide-world road at the seam, a corridor
edge next to a wide one). Only this stage sees all three exports at once. It changes nothing in graph_game.json, so
the runtime graph (node/edge indices, polylines), jobs, Road Fight, traffic, layout and buildings stay byte-identical;
only the road lines of the chunk modules that need a fix are rewritten, plus one new module per dataset (joints).

Rules (deterministic; same input -> same output; an edge that needs no fix keeps its line byte for byte):
  K  kinks   a vertex of an exported polyline turning by more than 60 deg (inside one edge) is replaced by a short
             quadratic fillet (cut <= 6 studs and <= 45 % of the shorter neighbour segment; end points never move).
  S  kerbs   a sidewalk SIDE is dropped when its strip (as PattayaBuilder builds it) lies on more than 10 studs^2 of
             another road's slab or of a disc not on this edge (the edge continuing through a degree-2 joint does not
             count). Same rule as the wide world's export (export_roblox.sidewalk_sides), now over all three datasets
             together (the central slice had never had it; seam and corridor neighbours were not seen before).
             Chunk fields as before: `swSide = -1 | 1` (one side kept) or `sidewalk = 0`.
  M  marks   lane / centre markings are not drawn where they would lie on another road of the same or a higher
             class (express > main > soi) or on a disc not on this edge (dual carriageways and close parallel roads
             squeezed together at x0.5, acute merges, roads poking into another road): there the two slabs read as
             one wide surface, as a real boulevard without a median would. New chunk field `noMarks = {s0, s1, ...}`
             = arc-length ranges along the edge's exported polyline (PattayaBuilder.buildEdge skips them). Markings
             of a higher-class road over a minor road stay.
  J  joints  the central slice gets joint discs (joints.luau, same rule as the wide world: degree-1/2 nodes, radius =
             narrowest incident half-width) where neither it nor the wide world has a disc yet.
Left out on purpose (see docs/ROAD_AUDIT.md): moving centrelines apart (would move traffic lanes, GPS lines, job-stand
kerbs, props and buildings of the tested slice), junction nodes at crossings (the audit found no crossing without a
shared node), raising bridges (no bridge / tunnel / layer pair crosses another road in the game graph).

Writes build/road_fix/changes.json (per dataset: changed chunk ids, per-edge changes) and, unless --dry-run,
rewrites the chunk modules in place. Run it once per export: it refuses to run on modules it already rewrote
(their sha1 is in build/road_fix/written.json) - rerun the exporters first.
"""
import argparse, hashlib, json, math, os, re, sys
from collections import defaultdict
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, os.path.dirname(__file__))
import road_check as rc  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATASETS = [('central', 'build/central_pattaya/roblox'), ('wide', 'build/pattaya_wide/roblox'),
            ('corridor', 'build/bira/roblox_corridor')]
KINK_DEG = 35.0            # rule K: interior vertices turning more than this get a fillet
BEND_DEG = 20.0            # rule B: degree-2 joints turning more than this get a full-width disc + end trims
BEND_TRIM_MAX = 60.0
KERB_STUDS2 = 10.0
MARK_SHRINK = 0.3          # a marking point counts as "on another road" only this far inside its slab / disc
MARK_STEP = 1.0            # sampling step (studs) for the noMarks ranges
MARK_PAD = 1.0             # each suppressed stretch grows by this much at both ends
MARK_MERGE = 6.0           # kept marking pieces shorter than this between two ranges are dropped too
RANK = {'express': 0, 'main': 1, 'soi': 2}
LINE_RE = re.compile(r'^  \{ id = "([^"]+)", way = .*\},$')


# ---- loading -------------------------------------------------------------------------------------------------------
def dash_gap_of(rdir, ds):
    if ds == 'central':
        return 12                                    # Build() passes no dashGap: buildEdge's default
    m = re.search(r'dashGap = (\d+)', open(os.path.join(rdir, 'manifest.luau'), encoding='utf-8').read())
    return int(m.group(1)) if m else 12


def load(root=ROOT):
    """edges of all datasets with their file/line position, discs, per-dataset junction radii and dash gaps"""
    edges, discs, jrs, files, gaps = [], {}, {}, {}, {}
    for ds, rel in DATASETS:
        d = os.path.join(root, rel)
        es, dd, jr = rc.load_dataset(d)
        jrs[ds] = jr
        gaps[ds] = dash_gap_of(d, ds)
        for k, v in dd.items():
            discs[(ds, k)] = v
        by_id = {e['id']: e for e in es}
        for f in sorted(os.listdir(d)):
            if not (f.startswith('chunk_') and f.endswith('.luau')):
                continue
            lines = open(os.path.join(d, f), encoding='utf-8').read().split('\n')
            files[(ds, f)] = lines
            for li, ln in enumerate(lines):
                m = LINE_RE.match(ln)
                if m:
                    e = by_id[m.group(1)]
                    nm = re.search(r', noMarks = \{([^}]*)\}', ln)
                    ja = re.search(r', jA = ([\d.]+)', ln)
                    jb = re.search(r', jB = ([\d.]+)', ln)
                    e.update(ds=ds, file=f, line=li, orig_pts=e['pts'].copy(),
                             noMarks=[float(v) for v in nm.group(1).split(',') if v] if nm else [],
                             jA=float(ja.group(1)) if ja else 0.0, jB=float(jb.group(1)) if jb else 0.0)
                    edges.append(e)
    return edges, discs, jrs, files, gaps


def end_trims(e, jr):
    """what PattayaBuilder.buildEdge trims markings by at end a / b: the junction disc radius, else the bend trim"""
    return jr.get(e['a'], 0) or e.get('jA', 0) or 0, jr.get(e['b'], 0) or e.get('jB', 0) or 0


def degrees(edges):
    deg = defaultdict(int)
    for e in edges:
        deg[e['a']] += 1; deg[e['b']] += 1
    return deg


def plen(p):
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


# ---- builder ports: markings exactly as PattayaBuilder.buildEdge draws them ----------------------------------------
def mark_offsets(e):
    if e['tier'] == 'soi':
        return []
    w, n = e['width'], e['lanes']
    if e['oneway']:
        return [((k - n / 2) * w / n, 'dash') for k in range(1, n)]
    out = [(-0.5, 'centre'), (0.5, 'centre')]
    for k in range(1, n // 2):
        out += [(k * w / n, 'dash'), (-k * w / n, 'dash')]
    return out


def mark_pieces(e, jr):
    """arc ranges (lo, hi) along e['pts'] where buildEdge draws markings (junction trim minus noMarks)"""
    total = plen(e['pts'])
    ta, tb = end_trims(e, jr)
    lo, hi = ta, total - tb
    cuts = e.get('noMarks') or []
    pieces, s = [], lo
    for k in range(0, len(cuts), 2):
        a, b = cuts[k], cuts[k + 1]
        if a > s:
            pieces.append((s, min(a, hi)))
        s = max(s, b)
    pieces.append((s, hi))
    return [(a, b) for a, b in pieces if b - a > 2]           # trim() returns nil for pieces of 2 studs or less


def dash_segments(pts, dash, gap):
    out, carry = [], 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ln = float(np.linalg.norm(b - a))
        if ln <= 0:
            continue
        d = (b - a) / ln
        s = carry
        while s + dash <= ln:
            out.append((a + d * s, a + d * (s + dash)))
            s += dash + gap
        carry = max(s - ln, 0)
    return out


def marking_parts(e, jr, gap):
    """centre points of every marking Part buildEdge makes (dashes: one per dash; centre lines: one per segment)"""
    out = []
    total = plen(e['pts'])
    for lo, hi in mark_pieces(e, jr) if mark_offsets(e) else []:
        inner = rc.trim(e['pts'], lo, total - hi)
        if inner is None:
            continue
        for d, kind in mark_offsets(e):
            q = rc.offset(inner, d)
            if kind == 'centre':
                out += [(q[i] + q[i + 1]) / 2 for i in range(len(q) - 1) if np.linalg.norm(q[i + 1] - q[i]) > 0.05]
            else:
                out += [(a + b) / 2 for a, b in dash_segments(q, 8, gap)]
    return out


# ---- geometry of the world -----------------------------------------------------------------------------------------
class World:
    def __init__(self, edges, discs):
        self.edges, self.discs = edges, discs
        self.deg = degrees(edges)
        self.rebuild()

    def rebuild(self):
        self.slabs, self.slab_edge = [], []
        for i, e in enumerate(self.edges):
            for r in rc.stripe_rects(e['pts'], e['width']):
                self.slabs.append(r); self.slab_edge.append(i)
        self.disc_nodes = []
        for (ds, k), (x, z, r) in self.discs.items():
            n = k[1] if isinstance(k, tuple) else k
            self.slabs.append(Point(x, z).buffer(r, 32)); self.slab_edge.append(-1); self.disc_nodes.append(n)
        self.n_edge_slabs = len(self.slabs) - len(self.disc_nodes)
        # bend discs at interior vertices (rule V, negative synthetic ids) belong to the edge(s) passing through them
        lines = [LineString(e['pts']) for e in self.edges]
        ltree = STRtree(lines)
        self.disc_owner = {}
        for d, n in enumerate(self.disc_nodes):
            if n < 0:
                c = self.slabs[self.n_edge_slabs + d].centroid
                self.disc_owner[d] = {int(j) for j in ltree.query(c.buffer(1.0)) if lines[j].distance(c) < 1.0}
        self.tree = STRtree(self.slabs)
        self.inner = [s.buffer(-MARK_SHRINK) for s in self.slabs]
        self.inner_tree = STRtree(self.inner)

    def foreign(self, i, k):
        """is slab/disc k 'another road' for edge i? (not itself, not its continuation at a degree-2 joint,
        not a disc on one of its own nodes)"""
        e = self.edges[i]
        j = self.slab_edge[k]
        if j < 0:
            d = k - self.n_edge_slabs
            if self.disc_nodes[d] < 0:
                return i not in self.disc_owner.get(d, ())
            return self.disc_nodes[d] not in (e['a'], e['b'])
        if j == i:
            return False
        o = self.edges[j]
        return not any(self.deg[n] == 2 for n in {o['a'], o['b']} & {e['a'], e['b']})

    def suppresses(self, i, k):
        """would slab/disc k hide edge i's markings? (foreign, and a disc or a road of the same or a higher class)"""
        if not self.foreign(i, k):
            return False
        j = self.slab_edge[k]
        return j < 0 or RANK[self.edges[j]['tier']] <= RANK[self.edges[i]['tier']]


# ---- rule K: kinks ---------------------------------------------------------------------------------------------------
def turn_deg(p, k):
    v1, v2 = p[k] - p[k - 1], p[k + 1] - p[k]
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, float(v1 @ v2 / n1 / n2)))))


def smooth_kinks(p):
    p = np.array(p, float)
    for _ in range(4):
        ks = [k for k in range(1, len(p) - 1) if turn_deg(p, k) > KINK_DEG]
        if not ks:
            break
        out = [p[0]]
        for k in range(1, len(p) - 1):
            if k not in ks:
                out.append(p[k]); continue
            a, v, b = p[k - 1], p[k], p[k + 1]
            n1, n2 = np.linalg.norm(v - a), np.linalg.norm(b - v)
            c = min(6.0, 0.45 * min(n1, n2))
            p1, p2 = v + (a - v) / n1 * c, v + (b - v) / n2 * c
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):     # quadratic Bezier p1 -> p2 with control point v
                out.append((1 - t) ** 2 * p1 + 2 * (1 - t) * t * v + t ** 2 * p2)
        out.append(p[-1])
        p = np.array(out)
    return np.round(p, 2)


# ---- rule S: kerbs -------------------------------------------------------------------------------------------------
def kerb_conflicts(W, i, jr):
    """{side: area of that side's strip on other roads} for the sides edge i builds now"""
    e = W.edges[i]
    out = {}
    if e['sidewalk'] <= 0:
        return out
    ra, rb = end_trims(e, jr)
    sw = rc.trim(e['pts'], ra + e['sidewalk'] if ra > 0 else 0, rb + e['sidewalk'] if rb > 0 else 0)
    if sw is None:
        return out
    for side in (-1, 1):
        if e.get('swSide') and e['swSide'] != side:
            continue
        strip = unary_union(rc.stripe_rects(rc.offset(sw, side * (e['width'] + e['sidewalk']) / 2), e['sidewalk']))
        area = 0.0
        for k in W.tree.query(strip):
            if W.foreign(i, k):
                area += W.slabs[k].intersection(strip).area
        out[side] = area
    return out


# ---- rule M: marking ranges ----------------------------------------------------------------------------------------
def mark_ranges(W, i, jr):
    e = W.edges[i]
    offs = [d for d, _ in mark_offsets(e)]
    if not offs:
        return []
    p = e['pts']
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = cum[-1]
    ta, tb = end_trims(e, jr)
    lo, hi = ta, total - tb
    if hi - lo <= 2:
        return []
    s = np.arange(lo, hi + 1e-9, MARK_STEP)
    k = np.clip(np.searchsorted(cum, s, side='right') - 1, 0, len(p) - 2)
    t = ((s - cum[k]) / np.maximum(seg[k], 1e-9))[:, None]
    c = p[k] + (p[k + 1] - p[k]) * t
    d = (p[k + 1] - p[k]) / np.maximum(seg[k], 1e-9)[:, None]
    nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
    bad = np.zeros(len(s), bool)
    for off in offs:
        q = c + nrm * off
        pi, si = W.inner_tree.query(shapely.points(q[:, 0], q[:, 1]), predicate='within')
        for a_, b_ in zip(pi, si):
            if not bad[a_] and W.suppresses(i, b_):
                bad[a_] = True
    if not bad.any():
        return []
    runs, start = [], None
    for idx, v in enumerate(list(bad) + [False]):
        if v and start is None:
            start = idx
        elif not v and start is not None:
            runs.append([max(s[start] - MARK_PAD, lo), min(s[idx - 1] + MARK_PAD, hi)]); start = None
    merged = [runs[0]]
    for r in runs[1:]:
        if r[0] - merged[-1][1] < MARK_MERGE:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    if merged[0][0] - lo < MARK_MERGE:
        merged[0][0] = 0.0                                    # nothing worth drawing before it
    if hi - merged[-1][1] < MARK_MERGE:
        merged[-1][1] = round(total + 1, 1)
    return [round(v, 1) for r in merged for v in r]


# ---- rule B: bends at degree-2 joints -------------------------------------------------------------------------------
def heading(p, from_end=False, dist=6.0):
    q = p[::-1] if from_end else p
    s_, prev = 0.0, q[0]
    for pt in q[1:]:
        s_ += float(np.linalg.norm(pt - prev)); prev = pt
        if s_ >= dist:
            break
    v = prev - q[0]
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def joint_turns(edges):
    """{node: (turn deg, [(edge index, at_b), (edge index, at_b)])} for every degree-2 node of the world"""
    inc = defaultdict(list)
    for i, e in enumerate(edges):
        inc[e['a']].append((i, False)); inc[e['b']].append((i, True))
    out = {}
    for n, lst in inc.items():
        if len(lst) != 2 or lst[0][0] == lst[1][0]:
            continue
        (i, ei), (j, ej) = lst
        ha, hb = heading(edges[i]['pts'], ei), heading(edges[j]['pts'], ej)
        out[n] = (180 - math.degrees(math.acos(max(-1.0, min(1.0, float(ha @ hb))))), lst)
    return out


def bend_rule(edges, discs):
    """degree-2 joints turning > BEND_DEG: the joint disc gets the WIDER half-width (it then fills the open wedge on
    the outside of the bend, whose corners lie at width/2 from the node), and both edge ends get a trim
    jA / jB = (other width / 2) * tan(turn / 2) (<= 60 studs) so markings and sidewalks stop where the two roads stop
    overlapping, as at a junction disc. Returns {node: radius} of the bend discs."""
    bends = {}
    for n, (turn, lst) in sorted(joint_turns(edges).items()):
        if turn <= BEND_DEG:
            continue
        (i, ei), (j, ej) = lst
        A, B = edges[i], edges[j]
        bends[n] = max(A['width'], B['width']) / 2
        for E, at_b, O in ((A, ei, B), (B, ej, A)):
            if not mark_offsets(E) and E['sidewalk'] <= 0:
                continue                                      # nothing to trim (a soi without sidewalks): line unchanged
            t = round(min(O['width'] / 2 * math.tan(math.radians(min(turn, 150)) / 2), BEND_TRIM_MAX), 2)
            E['jB' if at_b else 'jA'] = max(E.get('jB' if at_b else 'jA', 0.0), t)
    return bends


# ---- rule J: central joint discs -----------------------------------------------------------------------------------
def central_joints(edges, discs):
    have = {k[1] if isinstance(k, tuple) else k for (ds, k) in discs}
    deg = degrees(edges)
    min_half, pos = {}, {}
    for e in edges:
        for n, p in ((e['a'], e['pts'][0]), (e['b'], e['pts'][-1])):
            min_half[n] = min(min_half.get(n, 1e9), e['width'] / 2)
            if e['ds'] == 'central':
                pos.setdefault(n, p)
    return {n: (pos[n][0], pos[n][1], min_half[n]) for n in sorted(pos) if deg[n] <= 2 and n not in have}


# ---- edge line rewrite ---------------------------------------------------------------------------------------------
def rewrite_line(ln, e):
    out = re.sub(r', swSide = -?1', '', ln)
    out = re.sub(r', noMarks = \{[^}]*\}', '', out)
    out = re.sub(r', j[AB] = [\d.]+', '', out)
    if e['sidewalk_new'] != e['sidewalk_orig']:
        out = re.sub(r'sidewalk = [\d.]+,', 'sidewalk = 0,', out, count=1)
    flat = ','.join(f'{x:.2f},{z:.2f}' for x, z in e['pts'])
    out = re.sub(r'pts = \{[^}]*\}', 'pts = {' + flat + '}', out, count=1) if e['pts_changed'] else out
    extra = ''
    if e.get('swSide'):
        extra += f', swSide = {e["swSide"]}'
    if e.get('jA'):
        extra += f', jA = {e["jA"]:g}'
    if e.get('jB'):
        extra += f', jB = {e["jB"]:g}'
    if e.get('noMarks'):
        extra += ', noMarks = {' + ','.join(f'{v:.1f}' for v in e['noMarks']) + '}'
    assert out.endswith(' },')
    return out[:-3] + extra + ' },'


def sha(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--root', default=ROOT)
    a = ap.parse_args()
    root = a.root
    state_dir = os.path.join(root, 'build', 'road_fix')
    written_p = os.path.join(state_dir, 'written.json')
    edges, discs, jrs, files, gaps = load(root)
    if os.path.exists(written_p):
        written = json.load(open(written_p, encoding='utf-8'))
        again = [k for k, h in written.items() if (tuple(k.split('/', 1)) in files and sha('\n'.join(files[tuple(k.split('/', 1))])) == h)]
        if again:
            sys.exit(f'road_fix: {len(again)} chunk modules are already the fixed version (e.g. {again[0]}); '
                     'rerun export_roblox.py / export_corridor.py first')
    for e in edges:
        e['sidewalk_orig'] = e['sidewalk']
        e['swSide_orig'] = e.get('swSide')
        e['noMarks_orig'] = list(e['noMarks'])

    # K: kinks (before anything else: the other rules use the final polylines)
    n_kink = 0
    for e in edges:
        q = smooth_kinks(e['pts'])
        e['pts_changed'] = len(q) != len(e['pts']) or bool(np.abs(q - e['pts']).max() > 1e-9)
        if e['pts_changed']:
            n_kink += 1
            e['pts'] = q
    J = central_joints(edges, discs)
    for n, v in J.items():
        discs[('central', ('joint', n))] = v
    for e in edges:
        e['jA_orig'], e['jB_orig'] = e.get('jA', 0.0), e.get('jB', 0.0)
    bends = bend_rule(edges, discs)
    n_bend_disc = 0
    for (ds, k), (x, z, r) in list(discs.items()):
        if isinstance(k, tuple) and k[0] == 'joint' and k[1] in bends and bends[k[1]] > r + 1e-9:
            discs[(ds, k)] = (x, z, round(bends[k[1]], 2)); n_bend_disc += 1
    W = World(edges, discs)

    # S: kerbs
    n_side = 0
    for i, e in enumerate(edges):
        conf = kerb_conflicts(W, i, jrs[e['ds']])
        keep = [s for s, area in sorted(conf.items()) if area <= KERB_STUDS2]
        if len(keep) == len(conf):
            continue
        n_side += len(conf) - len(keep)
        if keep:
            e['swSide'] = keep[0]
        else:
            e['sidewalk'] = 0
            e['swSide'] = None

    # M: markings
    n_marks = 0
    for i, e in enumerate(edges):
        e['noMarks'] = mark_ranges(W, i, jrs[e['ds']])
        n_marks += bool(e['noMarks'])

    # V: bend discs where Road Parts still meet end to end at a sharp angle with no disc (pass 2: the Studio kink
    # probe found them next to short fillet pieces and next to 5-6 stud segments, all interior vertices of one edge).
    # A joint disc (synthetic negative id) of the wider road's half-width at the meeting point fills the wedge; it
    # changes only the joints modules, never a chunk line. Looser than the Studio probe (parts >= 5 studs, ends within
    # 3 studs, 30-150 deg) so small differences between the replica and Studio are covered too.
    import zlib
    import studio_probes as sp
    _, vk = sp.probes(edges, discs, jrs, min_len=5.0, end_tol=3.0, turn_lo=30.0, turn_hi=150.0)
    n_vdisc = 0
    for k in vk:
        A, B = edges[k['a']], edges[k['b']]
        if k['a'] == k['b']:                              # inside one edge: put the disc on its centreline
            ln = LineString(A['pts'])
            q = ln.interpolate(ln.project(Point(k['x'], k['z'])))
            k = dict(k, x=q.x, z=q.y)
        vid = -(zlib.crc32(f"{A['id']}|{B['id']}|{k['x']:.1f}|{k['z']:.1f}".encode()) + 1)
        key = (A['ds'], ('joint', vid))
        if key not in discs:
            discs[key] = (round(k['x'], 2), round(k['z'], 2), max(A['width'], B['width']) / 2)
            n_vdisc += 1

    # write
    changes = {ds: {'chunks': [], 'edges': {}} for ds, _ in DATASETS}
    new_files = {}
    for e in edges:
        e['sidewalk_new'] = e['sidewalk']
        what = []
        if e['pts_changed']:
            what.append('kink fillet')
        if e['sidewalk'] != e['sidewalk_orig'] or e.get('swSide') != e['swSide_orig']:
            what.append(f"kerb {e['swSide_orig'] or ('both' if e['sidewalk_orig'] > 0 else 'none')} -> "
                        f"{e.get('swSide') or ('both' if e['sidewalk'] > 0 else 'none')}")
        if (e.get('jA', 0), e.get('jB', 0)) != (e['jA_orig'], e['jB_orig']):
            what.append(f"bend trim a {e.get('jA', 0):g} b {e.get('jB', 0):g}")
        if e['noMarks'] != e['noMarks_orig']:
            what.append(f"noMarks {len(e['noMarks']) // 2} ranges, {sum(e['noMarks'][k + 1] - e['noMarks'][k] for k in range(0, len(e['noMarks']), 2)):.0f} studs")
        if not what:
            continue
        lines = new_files.setdefault((e['ds'], e['file']), list(files[(e['ds'], e['file'])]))
        lines[e['line']] = rewrite_line(lines[e['line']], e)
        changes[e['ds']]['edges'][e['id']] = '; '.join(what)
    for (ds, f), lines in sorted(new_files.items()):
        if lines != files[(ds, f)]:
            changes[ds]['chunks'].append(f[6:-5])
    os.makedirs(state_dir, exist_ok=True)
    stats = {'kink_edges': n_kink, 'kerb_sides_dropped': n_side, 'edges_with_noMarks': n_marks, 'central_joint_discs': len(J),
             'bend_joints': len(bends), 'vertex_bend_discs': n_vdisc, 'bend_discs_widened': n_bend_disc,
             'edges_with_bend_trim': sum(1 for e in edges if e.get('jA') or e.get('jB'))}
    json.dump({'stats': stats, 'changes': changes}, open(os.path.join(state_dir, 'changes.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'road_fix: {stats}')
    for ds, _ in DATASETS:
        print(f"  {ds}: {len(changes[ds]['chunks'])} chunks, {len(changes[ds]['edges'])} edges changed")
    if a.dry_run:
        return
    rel = dict(DATASETS)
    written = {}
    for (ds, f), lines in sorted(new_files.items()):
        text = '\n'.join(lines)
        if text != '\n'.join(files[(ds, f)]):
            open(os.path.join(root, rel[ds], f), 'w', encoding='utf-8', newline='\n').write(text)
            written[f'{ds}/{f}'] = sha(text)
    for ds, _ in DATASETS:
        rows = sorted((k[1], v) for (d_, k), v in discs.items() if d_ == ds and isinstance(k, tuple) and k[0] == 'joint')
        jp = os.path.join(root, rel[ds], 'joints.luau')
        old = open(jp, encoding='utf-8').read() if os.path.exists(jp) else None
        body = 'return {' + ','.join(f'{n},{x:.2f},{z:.2f},{r:.2f}' for n, (x, z, r) in rows) + '}\n'
        if old is not None and old.split('return {')[1] == body[len('return {'):]:
            continue                                         # unchanged: keep the file byte for byte
        head = (old.split('return {')[0] if old else
                '-- generated by tools/mapgen/road_fix.py; do not edit. Joint discs (osmNode, x, z, r) at degree-1/2 nodes of the\n'
                '-- central slice that had no disc (same rule as the wide world); they trim no markings or sidewalks\n')
        if old is not None and 'road_fix' not in head:
            head += '-- road_fix.py: discs at bends over 20 deg widened to the wider road half-width\n'
        open(jp, 'w', encoding='utf-8', newline='\n').write(head + body)
        changes[ds]['joints_module'] = True
    json.dump(written, open(written_p, 'w', encoding='utf-8'), indent=1)
    json.dump({'stats': stats, 'changes': changes}, open(os.path.join(state_dir, 'changes.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
