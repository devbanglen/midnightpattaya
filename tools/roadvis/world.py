"""The BUILT road layers as polygons (map-local studs; world = map + (20000, 0, 0)), read only from build/.

Every layer is rebuilt with the existing builder ports, so the numbers describe what Studio has:
  road / fill        PattayaBuilder.buildEdge slabs (road_check.slab_pieces + stripe_rects) and rule-D fill triangles
  junction / joint   manifest junction discs and joints.luau joint discs (cylinders, top 0.99)
  sidewalk           buildEdge sidewalk strips (road_check.sidewalk_rects: swSide, trims at discs / bends), top 1.6
  apron / corner     build/aprons (PattayaApronBuilder): asphalt aprons top 0.98, concrete corner fills top 1.58
  shoulder / taper / gap   build/shoulders (PattayaShoulderBuilder, the approved Sukhumvit pilot), concrete, top 0.985
  markings           buildEdge centre lines / lane dashes (road_fix.mark_pieces / mark_offsets / dash_segments)
  crossings          the zebra rows of the BUILT furniture modules (build/furniture/roblox/chunk_f*, furniture.crossing_bars)
  buildings          chunk `buildings` rows (box rotated by +yaw in x/z, as CFrame.Angles(0, -yaw, 0))
"""
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
for p in (os.path.join(REPO, 'tools', 'mapgen'), os.path.join(REPO, 'tools', 'qa')):
    if p not in sys.path:
        sys.path.insert(0, p)
import road_check as rc  # noqa: E402
import road_fix as rf  # noqa: E402
import junction_aprons as ja  # noqa: E402
import road_seams as rs  # noqa: E402

ORIGIN = (20000.0, 0.0)
ROAD_TOP = 1.0
TOPS = {'sidewalk': 1.6, 'corner': 1.58, 'road': 1.0, 'fill': 1.0, 'junction': 0.99, 'joint': 0.99,
        'shoulder': 0.985, 'taper': 0.985, 'gap': 0.985, 'apron': 0.98}
ROAD_KINDS = ('road', 'fill', 'junction', 'joint', 'apron')          # asphalt at road height
SHOULDER_KINDS = ('shoulder', 'taper', 'gap')                         # concrete strips of the Sukhumvit pilot
SHOULDER_CODE = {1: 'shoulder', 2: 'taper', 3: 'gap'}
CAR = dict(width=7.0, length=15.0, body_length=16.0, track=6.8, wheelbase=10.4)   # RaceCarServer chassis / mounts


def find_build_root(arg=None):
    if arg:
        return os.path.abspath(arg)
    env = os.environ.get('MP_BUILD_DIR')
    if env and os.path.isdir(env):
        return env
    p = REPO
    for _ in range(6):                      # a worktree under <main>/.claude/worktrees/<name> has no build/ of its own
        if os.path.isdir(os.path.join(p, 'build', 'pattaya_wide')):
            return os.path.join(p, 'build')
        p = os.path.dirname(p)
    raise FileNotFoundError('build/ not found (pass --build-root or set MP_BUILD_DIR)')


def to_local(xw, zw):
    return xw - ORIGIN[0], zw - ORIGIN[1]


def to_world(x, z):
    return x + ORIGIN[0], z + ORIGIN[1]


def world_bbox_local(b):
    """(x0, z0, x1, z1) world -> local"""
    return (b[0] - ORIGIN[0], b[1] - ORIGIN[1], b[2] - ORIGIN[0], b[3] - ORIGIN[1])


def _shoulders(sdir):
    out = []
    if not os.path.isdir(sdir):
        return out
    for f in sorted(os.listdir(sdir)):
        if not (f.startswith('chunk_s') and f.endswith('.luau')):
            continue
        t = open(os.path.join(sdir, f), encoding='utf-8').read()
        mod = f[6:-5]
        for r in ja.read_rows(t, 'boxes', 7):
            cx, cz, ux, uz, ln, w, k = r
            n = math.hypot(ux, uz)
            out.append(dict(kind=SHOULDER_CODE[int(k)], poly=ja.rect(cx, cz, ux / n, uz / n, ln / 2, w / 2), module=mod, parts=1))
        for r in ja.read_rows(t, 'tris', 7):
            tris = rs.wedge_tris(r[0:2], r[2:4], r[4:6])
            if tris:
                out.append(dict(kind=SHOULDER_CODE[int(r[6])], poly=Polygon([r[0:2], r[2:4], r[4:6]]), module=mod, parts=len(tris)))
    return out


def _markings(e, jr, gap):
    """[(kind, a, b, width)] for every marking Part buildEdge makes on edge e"""
    out = []
    offs = rf.mark_offsets(e)
    if not offs:
        return out
    total = rf.plen(e['pts'])
    for lo, hi in rf.mark_pieces(e, jr):
        inner = rc.trim(e['pts'], lo, total - hi)
        if inner is None:
            continue
        for d, kind in offs:
            q = rc.offset(inner, d)
            if kind == 'centre':
                out += [('centre', q[i], q[i + 1], 0.45) for i in range(len(q) - 1) if np.linalg.norm(q[i + 1] - q[i]) > 0.05]
            else:
                out += [('lane', a, b, 0.5) for a, b in rf.dash_segments(q, 8, gap)]
    return out


def seg_poly(a, b, w):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    n = np.linalg.norm(d)
    if n < 1e-9:
        return None
    d /= n
    nn = np.array([-d[1], d[0]]) * w / 2
    return Polygon([a + nn, b + nn, b - nn, a - nn])


def built_crossings(broot, keep=None, stats=None):
    """the zebra crossings PattayaFurnitureBuilder BUILDS: the `crossings` rows {x, z, tx, tz, n, barW, gap, depth} of
    build/furniture/roblox/chunk_f*.luau (the modules the place is built from), as [dict(row, bars, edge, src, ds,
    chunk)]. furniture.json is only furniture.py's side-car: on 2026-10-19 the dual-pass-2 modules (4,321 bars) were
    copied into build/furniture/roblox from another worktree without it, so it still held the first pass (4,906 bars;
    155 instead of 133 in the Road B box; Studio RV.Plan 2026-10-22 matched 70 of 155). Its edge / src / ds metadata is
    kept where a row is unchanged (same x, z, tangent and bar count), else edge = None, src = 'modules'."""
    import furniture as fm
    sys.path.insert(0, os.path.join(REPO, 'tools', 'circuit'))
    try:
        import luau_table
    finally:
        sys.path.pop(0)
    meta = {}
    fp = os.path.join(broot, 'furniture', 'furniture.json')
    n_json = 0
    if os.path.exists(fp):
        fur = json.load(open(fp, encoding='utf-8'))
        for c in fur['chunks']:
            for it in fur['chunks'][c].get('crossings', []):
                n_json += 1
                meta[_xkey(it['row'])] = it
    out = []
    d = os.path.join(broot, 'furniture', 'roblox')
    n_mod = matched = 0
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if not (f.startswith('chunk_f') and f.endswith('.luau')):
                continue
            cd = luau_table.load(os.path.join(d, f))
            r = cd.get('crossings') or []
            if isinstance(r, dict):
                r = r.get('_list', [])
            for i in range(0, len(r) - 7, 8):
                row = [float(v) for v in r[i:i + 8]]
                n_mod += 1
                bars = fm.crossing_bars(row)
                m = meta.get(_xkey(row))
                matched += m is not None
                if keep is None or any(b.intersects(keep) for b in bars):
                    out.append(dict(row=row, bars=bars, edge=m['edge'] if m else None, src=m['src'] if m else 'modules',
                                    ds=m['ds'] if m else None, chunk=f[6:-5]))
    if stats is not None:
        stats['crossing rows in the built furniture modules'] = n_mod
        stats['crossing rows in furniture.json'] = n_json
        stats['built crossing rows also in furniture.json'] = matched
    return out


def _xkey(row):
    """a crossing row's identity: centre, tangent and bar count (rounded as furniture.py writes them)"""
    return tuple(round(float(v), 2) for v in row[:5])


def load(broot=None, bbox=None, margin=200.0, with_furniture=True):
    """the built world. bbox (x0, z0, x1, z1) in LOCAL studs limits what is kept (edges whose line comes within
    `margin` of it); None = the whole city. Returns dict:
      edges [edge dicts from road_fix.load: id, ds, pts, width, lanes, oneway, tier, hidden, merged, cutA/B, fill, ...]
      surf  [dict(kind, poly, edge=i | node=n, top, parts)]  every road-height / sidewalk / shoulder surface
      marks [dict(kind, poly, a, b, edge)]   crossings [dict(poly bars, row, edge, src)]   blds [dict(poly, h, id)]
      graph {'nodes': {id: (x, z)}, 'edges': [graph_game edge dicts of wide + central], 'deg': {node: n}}
    """
    broot = find_build_root(broot)
    root = os.path.dirname(broot)
    edges_all, discs, jrs, _files, gaps = rf.load(root)
    keep = box(*bbox).buffer(margin) if bbox else None
    W = dict(broot=broot, bbox=bbox, edges=[], surf=[], marks=[], crossings=[], blds=[], stats=Counter())
    seen = set()
    for e in edges_all:
        if e['id'] in seen:                     # same edge exported by two datasets (built twice, identical parts)
            W['stats']['duplicate edge exports'] += 1
            continue
        if keep is not None and not LineString(e['pts']).intersects(keep):
            continue
        seen.add(e['id'])
        i = len(W['edges'])
        e['label'] = e.get('label')
        W['edges'].append(e)
        jr = jrs[e['ds']]
        for q in rc.slab_pieces(e):
            for r in rc.stripe_rects(q, e['width']):
                W['surf'].append(dict(kind='road', poly=r, edge=i, top=1.0, parts=1))
        for r in rc.fill_polys(e):
            W['surf'].append(dict(kind='fill', poly=r, edge=i, top=1.0, parts=2))
        for r in rc.sidewalk_rects(e, jr):
            W['surf'].append(dict(kind='sidewalk', poly=r, edge=i, top=1.6, parts=1))
        for kind, a, b, w in _markings(e, jr, gaps[e['ds']]):
            p = seg_poly(a, b, w)
            if p is not None:
                W['marks'].append(dict(kind=kind, poly=p, a=a, b=b, edge=i, gap=gaps[e['ds']]))
    dseen = set()
    for (ds, k), (x, z, r) in sorted(discs.items(), key=lambda kv: str(kv[0])):
        kind = 'joint' if isinstance(k, tuple) else 'junction'
        n = k[1] if isinstance(k, tuple) else k
        if (kind, n) in dseen:
            continue
        dseen.add((kind, n))
        c = Point(x, z)
        if keep is not None and not c.intersects(keep):
            continue
        W['surf'].append(dict(kind=kind, poly=c.buffer(r, 32), node=int(n), top=0.99, parts=1, r=r, x=x, z=z))
    adir = os.path.join(broot, 'aprons', 'roblox')
    if os.path.isdir(adir):
        for poly, top, kind, junction, tilt in rs.load_aprons(adir):
            if keep is None or poly.intersects(keep):
                W['surf'].append(dict(kind=kind, poly=poly, node=junction, top=top, parts=1))
    for s in _shoulders(os.path.join(broot, 'shoulders', 'roblox')):
        if keep is None or s['poly'].intersects(keep):
            W['surf'].append(dict(s, top=0.985))
    if with_furniture:
        W['crossings'] = built_crossings(broot, keep, W['stats'])
    for ds, rel in rf.DATASETS:
        d = os.path.join(root, rel)
        for f in sorted(os.listdir(d)):
            if not (f.startswith('chunk_') and f.endswith('.luau')):
                continue
            t = open(os.path.join(d, f), encoding='utf-8').read()
            for b in ja.read_rows(t, 'buildings', 8):
                x, z, w, dd, h, yaw = b[:6]
                if keep is not None and not keep.intersects(Point(x, z).buffer(max(w, dd))):
                    continue
                a = math.radians(yaw)
                W['blds'].append(dict(poly=ja.rect(x, z, math.cos(a), math.sin(a), w / 2, dd / 2), h=h, id=int(b[7]), w=w, d=dd))
    # graph (connectivity, unchanged by everything here)
    nodes, gedges = {}, {}
    for name in ('central_pattaya/graph_game.json', 'pattaya_wide/graph_game.json', 'bira/corridor_graph_game.json'):
        gp = os.path.join(broot, *name.split('/'))
        if not os.path.exists(gp):
            continue
        g = json.load(open(gp, encoding='utf-8'))
        for k, v in g['nodes'].items():
            nodes[int(k)] = tuple(v)
        by_way = defaultdict(list)
        for e in gedges.values():
            by_way[e['way']].append(e)
        for e in g['edges']:
            if name.startswith('bira') and e['way'] in by_way:
                # the corridor graph re-exports Sukhumvit / city edges that the wide graph already has (':c' ids on the
                # same OSM way and line): one carriageway, not two
                L = LineString(e['pts'])
                same = unary_union([LineString(o['pts']) for o in by_way[e['way']]]).buffer(4.0)
                if same.intersection(L).length >= 0.9 * L.length:
                    W['stats']['corridor graph duplicates skipped'] += 1
                    continue
            gedges.setdefault(e['id'], e)
    deg = Counter()
    for e in gedges.values():
        deg[e['a']] += 1
        deg[e['b']] += 1
    src = {}
    sp = os.path.join(broot, 'pattaya_wide', 'graph_source.json')
    if os.path.exists(sp):
        for e in json.load(open(sp, encoding='utf-8'))['edges']:
            src.setdefault(e['way'], e)
    W['graph'] = dict(nodes=nodes, edges=list(gedges.values()), deg=deg, source_by_way=src)
    W['edge_index'] = {e['id']: i for i, e in enumerate(W['edges'])}
    return W


def crop(W, bbox):
    """shallow copy of W with every layer cut to the polygons that intersect bbox (local)"""
    B = box(*bbox)
    out = dict(W)
    out['bbox'] = bbox
    out['surf'] = [s for s in W['surf'] if s['poly'].intersects(B)]
    out['marks'] = [m for m in W['marks'] if m['poly'].intersects(B)]
    out['crossings'] = [c for c in W['crossings'] if any(b.intersects(B) for b in c['bars'])]
    out['blds'] = [b for b in W['blds'] if b['poly'].intersects(B)]
    return out


def tree_of(polys):
    return STRtree(polys) if polys else None
