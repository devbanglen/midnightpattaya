"""Offline road-surface check: what a raycast probe along each road centreline would hit in Studio.

  .venv\\Scripts\\python tools\\mapgen\\road_check.py tools\\mapgen\\config\\pattaya_wide.json
  .venv\\Scripts\\python tools\\mapgen\\road_check.py tools\\mapgen\\config\\pattaya_wide.json --corridor
  .venv\\Scripts\\python tools\\mapgen\\road_check.py tools\\mapgen\\config\\central_pattaya.json

Reproduces the leader's Studio probe (a ray straight down every 25 studs along every new edge) without Studio:
- probes: the centreline of every new edge in build/<name>/graph_game.json (base edges skipped for a wide config),
  at s = 0, 25, 50, ... along the smoothed polyline (the same points the Studio probe used);
- geometry: rebuilt exactly as PattayaBuilder builds it, from the EXPORTED data modules (so exporter rules such as
  dropped sidewalks are checked too): every chunk_*.luau of the build, of its base build, and (--corridor) of
  build/bira/roblox_corridor. Per edge: one slab per segment of its exported polyline (width = edge width,
  stretched at each joint by min(w/2 * tan(turn/2), w/2), segments <= 0.05 studs skipped), and two sidewalk strips
  (centre offset (width + sidewalk) / 2, width = sidewalk, trimmed by disc radius + sidewalk at junction discs,
  top 1.6 = road top + curb). Junction discs from each manifest's `junctions`.
A ray hits the highest surface: sidewalk (top 1.6) > road slab / disc (top 1.0). So every probe is one of
  road      - on a slab or disc and on no sidewalk strip
  sidewalk  - inside some edge's sidewalk strip (the 0.6-stud bump: parallel roads / dual carriageways at x0.5)
  hairline  - only on the bare boundary between two slabs that touch without overlapping (a node with no disc):
              a ray there can slip through in Studio (the leader's 62 misses were nearly all at such nodes)
  none      - no road part under it (a gap)
Joint discs (joints.luau) and one-sided sidewalks (swSide) are read from the exported data, and so are road_fix rule D's
hidden edges (no slab), slab cuts (cutA / cutB) and fill triangles (tools/mapgen/dual.py).
--json <file> writes every non-road probe (edge id, way, name, point, kind, chunk, the covering edge) for review.
"""
import argparse, json, math, os, re, sys
from collections import Counter, defaultdict
import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
EDGE_RE = re.compile(r'\{ id = "([^"]+)", way = (\d+), class = "[^"]*", tier = "(\w+)", .*?oneway = (true|false), '
                     r'lanes = (\d+), width = ([\d.]+), sidewalk = ([\d.]+), coastal = \w+, a = (\d+), b = (\d+), pts = \{([^}]*)\}'
                     r'(?:, swSide = (-?1))?')
DISC_RE = re.compile(r'\{ id = (\d+), x = (-?[\d.]+), z = (-?[\d.]+), r = ([\d.]+) \}')
SEAM_RE = re.compile(r'\{ id = (\d+), r = ([\d.]+) \}')
NAME_RE = re.compile(r'class = "([^"]*)", tier = "\w+", name = (nil|"(?:[^"\\]|\\.)*"), nameEn = (nil|"(?:[^"\\]|\\.)*")')


def lua_unquote(s):
    """a lua_str() literal back to text (None for nil)"""
    if s is None or s == 'nil':
        return None
    return re.sub(r'\\(\d+|.)', lambda m: chr(int(m.group(1))) if m.group(1).isdigit() else m.group(1), s[1:-1])


def section(src, key):
    """text of `key = { ... }` in a manifest (balanced braces)."""
    i = src.find(f'\n  {key} = {{')
    if i < 0:
        return ''
    j = src.index('{', i)
    d = 0
    for k in range(j, len(src)):
        d += src[k] == '{'
        d -= src[k] == '}'
        if d == 0:
            return src[j:k + 1]
    return ''


def load_dataset(rdir):
    """(edges, discs {id: (x, z, r)}, junctionR {id: r}) of one exported folder (manifest + chunk modules)."""
    man = open(os.path.join(rdir, 'manifest.luau'), encoding='utf-8').read()
    discs = {int(m[0]): (float(m[1]), float(m[2]), float(m[3])) for m in DISC_RE.findall(section(man, 'junctions'))}
    jr = {int(m[0]): float(m[1]) for m in SEAM_RE.findall(section(man, 'seamJunctions'))}
    jr.update({int(m[0]): float(m[3]) for m in DISC_RE.findall(section(man, 'seamJunctions'))})
    jr.update({n: r for n, (_, _, r) in discs.items()})
    jp = os.path.join(rdir, 'joints.luau')        # joint discs (osmNode, x, z, r): they trim nothing, so not in jr
    if os.path.exists(jp):
        v = [float(t) for t in open(jp, encoding='utf-8').read().split('return {')[1].split('}')[0].split(',') if t.strip()]
        for k in range(0, len(v), 4):
            discs[('joint', int(v[k]))] = (v[k + 1], v[k + 2], v[k + 3])
    edges = []
    for f in sorted(os.listdir(rdir)):
        if not (f.startswith('chunk_') and f.endswith('.luau')):
            continue
        text = open(os.path.join(rdir, f), encoding='utf-8').read()
        for m in EDGE_RE.finditer(text):
            flat = [float(v) for v in m.group(10).split(',') if v]
            rest = text[m.end():text.find(chr(10), m.end())]       # road_fix fields after swSide: jA / jB bend trims
            ja, jb = re.search(r', jA = ([\d.]+)', rest), re.search(r', jB = ([\d.]+)', rest)
            # road_fix rule D (tools/mapgen/dual.py): hidden edge, slab cuts at a / b, fill triangles, merged centreline
            ca, cb = re.search(r', cutA = ([\d.]+)', rest), re.search(r', cutB = ([\d.]+)', rest)
            fl = re.search(r', fill = \{([^}]*)\}', rest)
            hd = re.search(r', hide = \{([^}]*)\}', rest)
            line = text[text.rfind(chr(10), 0, m.start()) + 1:m.end()]
            nm = NAME_RE.search(line)
            edges.append({'id': m.group(1), 'way': int(m.group(2)), 'tier': m.group(3), 'oneway': m.group(4) == 'true',
                          'lanes': int(m.group(5)), 'width': float(m.group(6)), 'sidewalk': float(m.group(7)),
                          'a': int(m.group(8)), 'b': int(m.group(9)), 'pts': np.array(flat).reshape(-1, 2), 'chunk': f[6:-5],
                          'swSide': int(m.group(11)) if m.group(11) else None,
                          'jA': float(ja.group(1)) if ja else 0.0, 'jB': float(jb.group(1)) if jb else 0.0,
                          'hidden': ', hidden = true' in rest, 'merged': ', merged = true' in rest,
                          'cutA': float(ca.group(1)) if ca else 0.0, 'cutB': float(cb.group(1)) if cb else 0.0,
                          'fill': [float(v) for v in fl.group(1).split(',') if v.strip()] if fl else [],
                          'hide': [float(v) for v in hd.group(1).split(',') if v.strip()] if hd else [],
                          # the road Model's name in Studio (PattayaBuilder.buildEdge: nameEn or name or class)
                          'label': lua_unquote(nm.group(3)) or lua_unquote(nm.group(2)) or nm.group(1) if nm else None,
                          'set': os.path.basename(os.path.dirname(rdir.rstrip('/\\'))) + '/' + os.path.basename(rdir.rstrip('/\\'))})
    return edges, discs, jr


# ---- PattayaBuilder geometry, ported 1:1 (stripe / offset / trim) ----------------------------------------------------
def unit(v):
    n = math.hypot(v[0], v[1])
    return v / n if n > 0 else v * 0


def stripe_rects(pts, width):
    n = len(pts)
    ext = [0.0] * n
    for j in range(1, n - 1):
        d1, d2 = unit(pts[j] - pts[j - 1]), unit(pts[j + 1] - pts[j])
        turn = math.acos(max(-1.0, min(1.0, float(d1 @ d2))))
        ext[j] = min(width / 2 * math.tan(turn / 2), width / 2)
    out = []
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        seg = b - a
        if math.hypot(*seg) > 0.05:
            d = unit(seg)
            a2, b2 = a - d * ext[i], b + d * ext[i + 1]
            nrm = np.array([-d[1], d[0]]) * width / 2
            out.append(Polygon([a2 + nrm, b2 + nrm, b2 - nrm, a2 - nrm]))
    return out


def offset(pts, dist):
    out = []
    for i in range(len(pts)):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[i] - pts[i - 1]
        else:
            t = unit(pts[i + 1] - pts[i]) + unit(pts[i] - pts[i - 1])
        t = unit(t)
        out.append(pts[i] + np.array([-t[1], t[0]]) * dist)
    return np.array(out)


def trim(pts, d0, d1):
    seg = [math.hypot(*(pts[i + 1] - pts[i])) for i in range(len(pts) - 1)]
    total = sum(seg)
    if total <= d0 + d1 + 2:
        return None
    out, s, lo, hi = [], 0.0, d0, total - d1
    for i in range(len(pts) - 1):
        a, b, ln = pts[i], pts[i + 1], seg[i]
        s0, s1 = s, s + ln
        if s1 >= lo and s0 <= hi:
            ta = min(max((lo - s0) / ln, 0), 1) if ln > 0 else 0
            tb = min(max((hi - s0) / ln, 0), 1) if ln > 0 else 0
            if not out:
                out.append(a + (b - a) * ta)
            out.append(a + (b - a) * tb)
        s = s1
    return np.array(out) if len(out) >= 2 else None


def slab_pieces(e):
    """the polylines PattayaBuilder builds the edge's Road slab from (road_fix rule D): none for a hidden edge, the
    stretch cutA .. length - cutB minus the `hide` arc ranges otherwise (pieces of 2 studs or less are not built, as
    trim() returns nil for them). The edge's pts stay the full line (markings / sidewalks are measured on them)."""
    if e.get('hidden'):
        return []
    ca, cb, hide = e.get('cutA') or 0.0, e.get('cutB') or 0.0, e.get('hide') or []
    if not (ca or cb or hide):
        return [e['pts']]
    total = float(np.linalg.norm(np.diff(e['pts'], axis=0), axis=1).sum())
    out, lo = [], ca
    for k in range(0, len(hide) - 1, 2):
        if hide[k] > lo:
            out.append((lo, min(hide[k], total - cb)))
        lo = max(lo, hide[k + 1])
    out.append((lo, total - cb))
    pieces = [trim(e['pts'], a, total - b) for a, b in out if b > a]
    return [q for q in pieces if q is not None]


def slab_pts(e):
    """the first slab piece (None when the edge builds no slab); see slab_pieces"""
    p = slab_pieces(e)
    return p[0] if p else None


def slab_rects(e):
    """every Road Part footprint of the edge: its slab pieces' stripes plus its fill triangles"""
    return [r for q in slab_pieces(e) for r in stripe_rects(q, e['width'])] + fill_polys(e)


def fill_polys(e):
    """the edge's fill triangles (road_fix rule D: old slab parts no other road covers, rebuilt as flat triangles)"""
    v = e.get('fill') or []
    return [Polygon([(v[k], v[k + 1]), (v[k + 2], v[k + 3]), (v[k + 4], v[k + 5])]) for k in range(0, len(v) - 5, 6)]


def end_cuts(e, ra, rb):
    """marking / sidewalk trims at a / b as PattayaBuilder.buildEdge: junction disc or bend trim, at least the slab cut"""
    return max(ra, e.get('cutA') or 0.0), max(rb, e.get('cutB') or 0.0)


def sidewalk_rects(e, jr):
    if e['sidewalk'] <= 0 or e.get('hidden'):
        return []
    ra, rb = jr.get(e['a'], 0) or e.get('jA', 0), jr.get(e['b'], 0) or e.get('jB', 0)   # as PattayaBuilder.buildEdge
    ra, rb = end_cuts(e, ra, rb)
    sw = trim(e['pts'], ra + e['sidewalk'] if ra > 0 else 0, rb + e['sidewalk'] if rb > 0 else 0)
    if sw is None:
        return []
    return [r for side in (-1, 1) if not e.get('swSide') or e['swSide'] == side
            for r in stripe_rects(offset(sw, side * (e['width'] + e['sidewalk']) / 2), e['sidewalk'])]


def probes_of(pts, step):
    p = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1] + 1e-9, step)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1)


def run(cfg_path, corridor=False, step=25.0, json_out=None, quiet=False):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    bdir = os.path.join(ROOT, 'build', cfg['name'])
    dirs = []
    if 'base' in cfg:
        dirs.append(os.path.join(ROOT, cfg['base']['build'], 'roblox'))
    dirs.append(os.path.join(bdir, 'roblox'))
    if corridor:
        dirs.append(os.path.join(ROOT, 'build', 'bira', 'roblox_corridor'))
    slabs, slab_edge, walks, walk_edge, edges_all = [], [], [], [], []
    for d in dirs:
        edges, discs, jr = load_dataset(d)
        for e in edges:
            k = len(edges_all); edges_all.append(e)
            for r in slab_rects(e):
                slabs.append(r); slab_edge.append(k)
            for r in sidewalk_rects(e, jr):
                walks.append(r); walk_edge.append(k)
        for n, (x, z, r) in discs.items():
            slabs.append(Point(x, z).buffer(r, 32)); slab_edge.append(-1)
    by_id = {(e['set'], e['id']): e for e in edges_all}

    g = json.load(open(os.path.join(bdir, 'graph_game.json'), encoding='utf-8'))
    probe_edges = [e for e in g['edges'] if not e.get('base')]
    if corridor:
        cg = json.load(open(os.path.join(ROOT, 'build', 'bira', 'corridor_graph_game.json'), encoding='utf-8'))
        have = {e['id'] for e in probe_edges}
        probe_edges += [dict(e, corridor_probe=True) for e in cg['edges'] if e['id'] not in have]
    P, owner = [], []
    for i, e in enumerate(probe_edges):
        q = probes_of(e['pts'], step)
        P.append(q); owner += [i] * len(q)
    P = np.vstack(P); owner = np.array(owner)
    pts = shapely.points(P[:, 0], P[:, 1])
    on_slab = np.zeros(len(P), bool)
    s_idx = STRtree(slabs).query(pts, predicate='intersects')
    on_slab[s_idx[0]] = True
    inner = np.zeros(len(P), bool)          # strictly inside (0.01 stud margin): a ray on a bare boundary may slip through
    inner[STRtree([s.buffer(-0.01) for s in slabs]).query(pts, predicate='intersects')[0]] = True
    w_idx = STRtree(walks).query(pts, predicate='intersects') if walks else np.zeros((2, 0), int)
    on_walk = np.zeros(len(P), bool)
    walk_by = defaultdict(set)
    for pi, wi in zip(*w_idx):
        on_walk[pi] = True; walk_by[pi].add(walk_edge[wi])
    kind = np.where(on_walk, 'sidewalk', np.where(inner, 'road', np.where(on_slab, 'hairline', 'none')))
    cnt = Counter(kind.tolist())
    C = cfg['chunk_size_studs']
    bad = []
    for pi in np.nonzero(kind != 'road')[0]:
        e = probe_edges[owner[pi]]
        x, z = P[pi]
        cov = [edges_all[k] for k in walk_by.get(pi, ())]
        bad.append({'kind': str(kind[pi]), 'edge': e['id'], 'way': e['way'], 'name': e.get('name_en') or e.get('name'),
                    'oneway': e['oneway'], 'x': round(float(x), 1), 'z': round(float(z), 1),
                    'chunk': f'{math.floor(x / C)}_{math.floor(z / C)}',
                    'by': [{'edge': c['id'], 'way': c['way'], 'oneway': c['oneway'], 'chunk': c['chunk'], 'set': c['set']} for c in cov]})
    if not quiet:
        n = len(P)
        print(f'{len(probe_edges)} edges probed every {step:g} studs: {n:,} probes; road {cnt["road"]:,} ({cnt["road"] / n:.1%}), '
              f'sidewalk {cnt["sidewalk"]:,}, hairline {cnt["hairline"]:,}, none {cnt["none"]:,}; edges with a non-road probe: {len({b["edge"] for b in bad})}')
        sw_ch = Counter(c['chunk'] for b in bad for c in b['by'] if c['set'].endswith(cfg['name'] + '/roblox'))
        print(f'sidewalk hits caused by: ' + ', '.join(f'{s} {v}' for s, v in Counter(c['set'] for b in bad for c in b['by']).items()))
        if sw_ch:
            print(f'  chunks holding the offending sidewalks ({len(sw_ch)}): {" ".join(sorted(sw_ch))}')
    if json_out:
        json.dump({'counts': dict(cnt), 'probes': int(len(P)), 'bad': bad}, open(json_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return cnt, bad


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--corridor', action='store_true', help='also load build/bira/roblox_corridor and probe the corridor edges')
    ap.add_argument('--step', type=float, default=25.0)
    ap.add_argument('--json')
    a = ap.parse_args()
    run(a.config, a.corridor, a.step, a.json)
