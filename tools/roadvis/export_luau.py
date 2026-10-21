"""Design B pilot -> Luau data modules for roblox/src/ServerStorage/PattayaRoadVisBuilder.luau (OFFLINE export).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\export_luau.py      -> build/roadvis/roblox/
      manifest.luau                 tops, colours, cells, module list, counts, the EXPECTED replace list (every old part
                                    MoveReplaced must move, by kind and world position), probe samples + expected result
      cell_<cx>_<cz>[_k].luau       one 256-stud cell (map-local cell index), <= 600 parts per module:
        tris  {x1, z1, x2, z2, x3, z3, kind}  kind 1 asphalt, 2 sidewalk, 3 island (collision), 4 grass (visual, thin),
                                              5 invisible wheel support (road height, Transparency 1, CanCollide /
                                              CanQuery true)
        segs  {ax, az, bx, bz, width, kind}   kind 1 lane dash, 2 centre, 3 edge line, 4 stop line, 5 zebra bar, 6 kerb
        mesh  {x1, z1, x2, z2, x3, z3, layer} visual triangles for the opt-in EditableMesh path (no parts):
                                              layer 1 asphalt, 2 sidewalk, 3 kerb, 4 island, 5 grass, 6 white, 7 yellow
Coordinates are map-local studs (world = map + (20000, 0, 0)), like every other PattayaData module.

The replace rule (the same in Python here and in the builder's MoveReplaced): an old road part is replaced when the
centre of its horizontal footprint box (its Position) lies inside the pilot area AND at least 50 % of that footprint
box lies inside. Footprint box = the part's box spanned by its two most horizontal axes (a slab / sidewalk / dash /
centre / zebra Part: its rectangle; a WedgePart: the rectangle around its triangle; a disc Cylinder: its square).
Candidates: WideChunks / Chunks parts named Road, Sidewalk, Dash, Centre; WideJunctions / Junctions Junction, Joint;
ApronChunks Road (Apron) and Sidewalk (CornerFill); FurnitureChunks ZebraStripe. ShoulderChunks is never a candidate.
"""
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from tools.roadvis import junction, world  # noqa: E402

CELL = 256.0
CAP = 600
CODES = {'Road': 1, 'Sidewalk': 2, 'Dash': 3, 'Centre': 4, 'Junction': 5, 'Joint': 6, 'Apron': 7, 'CornerFill': 8, 'ZebraStripe': 9}
SEG_KIND = {'lane': 1, 'centre': 2, 'edge': 3, 'stop': 4, 'zebra': 5, 'kerb': 6}
SEG_W = {'lane': 0.5, 'centre': 0.45, 'edge': 0.5, 'stop': 1.6}
COLORS = dict(asphalt=[46, 47, 52], sidewalk=[170, 168, 160], island=[160, 158, 150], kerb=[205, 203, 196], grass=[86, 120, 62],
              white=[235, 235, 235], yellow=[245, 200, 40], gutter=[176, 174, 168])
TOPS = dict(asphalt=1.0, sidewalk=1.6, island=1.45, mark=1.05, kerb=1.61, grass=1.46, support=1.0, meshLift=0.01)
PROBE_OFFSETS = (0, 8, -8, 14, -14, 20, -20, 24, -24)
FOOT = (4.0, 9.0)          # width x length, 6 points (road_shoulders.drive 'spec')


def r(v, n=2):
    return round(float(v), n)


# ---- the old parts (exactly one footprint box per Part) -------------------------------------------------------------
def wedge_rect(tri):
    """the rectangle around a builder WedgePart triangle (corner, foot, apex): its box footprint"""
    c = np.asarray(tri.exterior.coords)[:3]
    corner, foot, apex = c
    return Polygon([corner, foot, apex, corner + (apex - foot)])


def old_parts(W):
    """[(name_code, footprint box polygon (map-local))] for every candidate Part of the old road layers"""
    rc, rf, rs = world.rc, world.rf, world.rs
    out = []
    import road_fix
    root = os.path.dirname(W['broot'])
    _edges, discs, jrs, _f, gaps = road_fix.load(root)
    seen = set()
    for e in _edges:
        if e['id'] in seen:
            continue
        seen.add(e['id'])
        jr = jrs[e['ds']]
        for q in rc.slab_pieces(e):
            out += [(CODES['Road'], p) for p in rc.stripe_rects(q, e['width'])]
        for t in rc.fill_polys(e):
            c = np.asarray(t.exterior.coords)[:3]
            out += [(CODES['Road'], wedge_rect(p)) for p, _ in rs.wedge_tris(c[0], c[1], c[2])]
        out += [(CODES['Sidewalk'], p) for p in rc.sidewalk_rects(e, jr)]
        offs = rf.mark_offsets(e)
        if offs:
            total = rf.plen(e['pts'])
            for lo, hi in rf.mark_pieces(e, jr):
                inner = rc.trim(e['pts'], lo, total - hi)
                if inner is None:
                    continue
                for d, kind in offs:
                    q = rc.offset(inner, d)
                    if kind == 'centre':
                        out += [(CODES['Centre'], p) for p in rc.stripe_rects(q, 0.45)]
                    else:
                        out += [(CODES['Dash'], world.seg_poly(a, b, 0.5)) for a, b in rf.dash_segments(q, 8, gaps[e['ds']])]
    dseen = set()
    for (ds, k), (x, z, rr) in sorted(discs.items(), key=lambda kv: str(kv[0])):
        kind = 'Joint' if isinstance(k, tuple) else 'Junction'
        n = k[1] if isinstance(k, tuple) else k
        if (kind, n) in dseen:
            continue
        dseen.add((kind, n))
        out.append((CODES[kind], box(x - rr, z - rr, x + rr, z + rr)))
    adir = os.path.join(W['broot'], 'aprons', 'roblox')
    if os.path.isdir(adir):
        for poly, top, kind, jn, tilt in rs.load_aprons(adir):
            code = CODES['Apron'] if kind == 'apron' else CODES['CornerFill']
            out.append((code, wedge_rect(poly) if len(poly.exterior.coords) == 4 else poly))
    for c in W['crossings']:
        out += [(CODES['ZebraStripe'], b) for b in c['bars']]
    return [(c, p) for c, p in out if p is not None]


def replace_rule(parts, area):
    """the parts MoveReplaced moves: centre inside the area and >= 50 % of the footprint box inside"""
    sel = []
    for code, p in parts:
        c = p.centroid
        if not area.contains(c):
            continue
        if p.intersection(area).area >= 0.5 * p.area - 1e-9:
            sel.append((code, c.x, c.y, p))
    return sel


# ---- new geometry -> rows -------------------------------------------------------------------------------------------
def tri_rows(tris, kind):
    out = []
    for t in tris:
        c = np.asarray(t.exterior.coords)[:3]
        row = [r(v) for v in c.flatten()]
        n = len(world.rs.wedge_tris(row[0:2], row[2:4], row[4:6]))      # on the rounded row, as the builder sees it
        if n:
            out.append((row + [kind], n, t.centroid))
    return out


def rect_axis(p):
    """(a, b, width) of a near-rectangle polygon (its long axis), or None"""
    c = np.asarray(p.exterior.coords)
    if len(c) != 5:
        return None
    e = [c[i + 1] - c[i] for i in range(4)]
    L = [float(np.linalg.norm(v)) for v in e]
    if min(L) < 1e-6 or abs(float(e[0] @ e[1])) > 1e-3 * L[0] * L[1] + 1e-6:
        return None
    if L[0] >= L[1]:
        m1, m2, w = (c[0] + c[3]) / 2, (c[1] + c[2]) / 2, L[1]
    else:
        m1, m2, w = (c[0] + c[1]) / 2, (c[2] + c[3]) / 2, L[0]
    return m1, m2, w


def mark_segs(m):
    out = []
    kind = m['kind']
    for p in junction.polys(m['poly']):
        ax = rect_axis(p.simplify(0.001))
        if ax is not None and (kind in ('zebra', 'stop', 'lane') or p.length < 40):
            out.append((ax[0], ax[1], ax[2]))
            continue
        line = m.get('line')
        if line is None:
            continue
        g = line.intersection(p.buffer(0.05))
        for l in junction.lines_of(g):
            q = np.asarray(l.simplify(0.25).coords)
            for i in range(len(q) - 1):
                if np.linalg.norm(q[i + 1] - q[i]) > 0.3:
                    out.append((q[i], q[i + 1], SEG_W.get(kind, 0.5)))
    return [(a, b, w, kind) for a, b, w in out]


def kerb_segs(P):
    out = []
    paved = unary_union([P['S'], P['islands']])
    kerb = P['kerb']
    if kerb.is_empty:
        return out
    for p in junction.polys(paved.buffer(0.5, join_style='mitre')):
        for ring in [p.exterior] + list(p.interiors):
            g = LineString(ring.coords).intersection(kerb.buffer(0.05))
            for l in junction.lines_of(g):
                q = np.asarray(l.simplify(0.3).coords)
                for i in range(len(q) - 1):
                    if np.linalg.norm(q[i + 1] - q[i]) > 0.5:
                        out.append((q[i], q[i + 1], 1.0, 'kerb'))
    return out


def probe_samples(P):
    """lane-centre probe rows {x, z, tx, tz, hw, leg} every 4 studs on every leg (chain) outside the seam band"""
    inner = P['area'].buffer(-(P['cfg']['seam_band'] + 10))
    rows, legs = [], []
    for c in P['chains']:
        poly, Q, T, hw, s = P['rib'][c['id']]
        reach = 6.2
        got = 0
        for k in range(0, len(Q), 2):
            if s[k] < reach or s[k] > s[-1] - reach or not inner.contains(Point(Q[k])):
                continue
            rows.append([r(Q[k][0]), r(Q[k][1]), r(T[k][0], 4), r(T[k][1], 4), r(hw[k]), c['id']])
            got += 1
        if got:
            legs.append(dict(id=c['id'], name=c['name'], oneway=c['oneway'], lanes=int(min(c['lanes'])), edges=c['edges']))
    return rows, legs


def probe_expected(W, P, rows):
    """what Probe should find (offline): per offset, flat / kerb / drop / blocked counts of the 6-point footprint,
    in-lane only, read from the COLLISION tops (ground.State: B asphalt grown 0.45 under the kerbs, sidewalk / island
    collision pulled back 0.3 from it, kept old parts, the installed shoulder chunks, buildings). The first export used
    the visual sidewalk outline and expected 15 / 20 kerb contacts at +24 / -24; Studio RV.Probe 2026-10-22 found 4 / 0
    (and 3 at -20), which is what the collision tops give."""
    from tools.roadvis import ground
    st = ground.State(W, P)
    hw_, hl = FOOT[0] / 2, FOOT[1] / 2
    pts_rel = [(-hl, -hw_), (-hl, hw_), (hl, -hw_), (hl, hw_), (0, -hw_), (0, hw_)]
    A = np.asarray(rows, float)
    out = {}
    for o in PROBE_OFFSETS:
        m = np.abs(o) <= A[:, 4]
        Q, T = A[m, 0:2], A[m, 2:4]
        N = np.stack([-T[:, 1], T[:, 0]], axis=1)
        C = Q + N * o
        worst = np.zeros(len(C), int)                 # 0 flat, 1 kerb, 2 blocked, 3 drop (RV.Probe's order)
        for lo, la in pts_rel:
            y = st.at(C + T * lo + N * la)
            worst = np.maximum(worst, np.where(y > 1.8, 2, np.where(y > 1.1, 1, np.where(y >= 0.9, 0, 3))))
        out[str(o)] = dict(samples=int(len(C)), drop=int((worst == 3).sum()), kerb=int((worst == 1).sum()),
                           blocked=int((worst == 2).sum()))
    return out


# ---- writer -------------------------------------------------------------------------------------------------------
def lua(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, float):
        s = ('%.3f' % v).rstrip('0').rstrip('.')
        return s if s not in ('-0', '') else '0'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return '{' + ', '.join(f'{k} = {lua(x)}' if str(k).isidentifier() else f'[{lua(k)}] = {lua(x)}' for k, x in v.items()) + '}'
    if isinstance(v, (list, tuple)):
        return '{' + ','.join(lua(x) for x in v) + '}'
    raise TypeError(type(v))


def cell_of(pt):
    return f'{math.floor(pt.x / CELL)}_{math.floor(pt.y / CELL)}'


def export(W, P, out_dir):
    area = P['area']
    cells = defaultdict(lambda: dict(tris=[], segs=[], mesh=[], parts=0))
    items = []                                # (cell, kind 'tris'|'segs', row, parts)
    for tris, kind in ((P['tris'], 1), (P['walk_tris'], 2), (P['isl_tris'], 3), (junction.triangles(P['green']), 4),
                       (P.get('support_tris') or [], 5)):
        for row, n, c in tri_rows(tris, kind):
            items.append((cell_of(c), 'tris', row, n, c))
    segs = [s for m in P['marks'] for s in mark_segs(m)] + kerb_segs(P)
    for a, b, w, kind in segs:
        pm = Point((a + b) / 2)
        items.append((cell_of(pm), 'segs', [r(a[0]), r(a[1]), r(b[0]), r(b[1]), r(w), SEG_KIND[kind]], 1, pm))
    layers = [(P['S'], 1), (P['walk'], 2), (P['kerb'], 3), (P['islands'], 4), (P['green'], 5),
              (unary_union([m['poly'] for m in P['marks'] if m['kind'] != 'centre']), 6),
              (unary_union([m['poly'] for m in P['marks'] if m['kind'] == 'centre']), 7)]
    mesh_items = []
    for g, layer in layers:
        for t in junction.triangles(g, simplify=0.02):
            c = np.asarray(t.exterior.coords)[:3]
            mesh_items.append((cell_of(t.centroid), [r(v) for v in c.flatten()] + [layer], t.centroid))
    # an Atomic cell over CAP parts is split into its four 128-stud quadrants (<cx>_<cz>q<qx><qz>), each its own Model
    tot = Counter()
    for it in items:
        tot[it[0]] += it[3]
    big = {c for c, n in tot.items() if n > CAP}

    def quad(cid, pt):
        if cid not in big:
            return cid
        return f'{cid}q{int((pt.x % CELL) // (CELL / 2))}{int((pt.y % CELL) // (CELL / 2))}'
    items = [(quad(c, pt), k, row, n, pt) for c, k, row, n, pt in items]
    mesh_items = [(quad(c, pt), row) for c, row, pt in mesh_items]
    # modules: per cell, split at CAP parts
    mods = {}
    by_cell = defaultdict(list)
    for it in items:
        by_cell[it[0]].append(it)
    mesh_by = defaultdict(list)
    for cid, row in mesh_items:
        mesh_by[cid].append(row)
    for cid in sorted(set(by_cell) | set(mesh_by)):
        groups, cur, n = [], [], 0
        for it in by_cell.get(cid, []):
            if n + it[3] > CAP and cur:
                groups.append(cur)
                cur, n = [], 0
            cur.append(it)
            n += it[3]
        groups.append(cur)
        for gi, g in enumerate(groups):
            name = f'cell_{cid}' + ('' if gi == 0 else f'_{gi + 1}')
            mods[name] = dict(cell=cid, tris=[x for it in g if it[1] == 'tris' for x in it[2]],
                              segs=[x for it in g if it[1] == 'segs' for x in it[2]],
                              mesh=[x for row in mesh_by.get(cid, []) for x in row] if gi == 0 else [],
                              parts=sum(it[3] for it in g))
    # replace list
    sel = replace_rule(old_parts(W), area)
    keys = []
    cnt = Counter()
    inv = {v: k for k, v in CODES.items()}
    for code, x, z, p in sorted(sel, key=lambda s: (s[0], round(s[1], 2), round(s[2], 2))):
        keys += [code, r(x + world.ORIGIN[0]), r(z)]
        cnt[inv[code]] += 1
    rows, legs = probe_samples(P)
    expected = probe_expected(W, P, rows)
    bw = P['cfg']['bbox_world']
    counts = Counter()
    for m in mods.values():
        t = m['tris']
        for i in range(0, len(t), 7):
            n = len(world.rs.wedge_tris(t[i:i + 2], t[i + 2:i + 4], t[i + 4:i + 6]))
            counts[{1: 'asphalt', 2: 'sidewalk', 3: 'island', 4: 'grass', 5: 'support'}[int(t[i + 6])]] += n
        s = m['segs']
        for i in range(0, len(s), 6):
            counts[{1: 'lane', 2: 'centre', 3: 'edge', 4: 'stop', 5: 'zebra', 6: 'kerb'}[int(s[i + 5])]] += 1
    man = dict(name=P['cfg']['name'], attribution='Map data (c) OpenStreetMap contributors, ODbL 1.0',
               note='generated by tools/roadvis/export_luau.py from the design B pilot; OFFLINE data, install needs owner approval',
               origin=[20000, 0, 0], bbox=[float(v) for v in bw], cellSize=CELL, maxPartsPerModule=CAP,
               tops=TOPS, colors=COLORS, thick=dict(asphalt=4.0, sidewalk=4.6, island=4.45, mark=0.05, kerb=0.02, grass=0.02, support=4.0),
               modules=sorted(mods), cells=sorted({m['cell'] for m in mods.values()}),
               counts=dict(parts=int(sum(m['parts'] for m in mods.values())), byKind=dict(counts),
                           meshTriangles=len(mesh_items)),
               # zebraSource: the ZebraStripe keys are the bars of the BUILT furniture modules (world.built_crossings), not
               # furniture.json (stale since 2026-10-19: Studio RV.Plan 2026-10-22 matched only 70 of its 155 keys)
               replace=dict(total=len(sel), byName=dict(cnt), keys=keys, tolerance=0.3,
                            zebraSource='build/furniture/roblox chunk_f* crossings (built modules)'),
               probe=dict(offsets=list(PROBE_OFFSETS), foot=list(FOOT), samples=[x for row in rows for x in row],
                          legs=[dict(id=l['id'], name=l['name'], oneway=l['oneway'], lanes=l['lanes']) for l in legs], expected=expected))
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith('.luau'):
            os.remove(os.path.join(out_dir, f))
    hdr = '-- generated by tools/roadvis/export_luau.py (design B road pilot, OFFLINE data; Map data (c) OpenStreetMap contributors, ODbL 1.0); do not edit\n'
    files = {}
    files['manifest.luau'] = hdr + 'return ' + lua(man) + '\n'
    for name, m in sorted(mods.items()):
        files[name + '.luau'] = hdr + 'return ' + lua(dict(id=name[5:], cell=m['cell'], parts=m['parts'], tris=m['tris'], segs=m['segs'], mesh=m['mesh'])) + '\n'
    for name, text in files.items():
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    digest = hashlib.sha1(''.join(files[k] for k in sorted(files)).encode('utf-8')).hexdigest()
    return dict(modules=len(mods), parts=man['counts']['parts'], byKind=dict(counts), replace=len(sel), replaceByName=dict(cnt),
                probeSamples=len(rows), expected=expected, maxModuleKB=round(max(len(t) for t in files.values()) / 1024, 1),
                maxModuleParts=max(m['parts'] for m in mods.values()), sha1=digest, files=sorted(files))


def main():
    from tools.roadvis import cli  # noqa: F401  (path setup)
    cfg = dict(junction.CFG, design='B', name=junction.CFG['name'] + '_B')
    bl = world.world_bbox_local(cfg['bbox_world'])
    W = world.load(None, bbox=bl)
    P = junction.generate(W, cfg)
    out = os.path.join(W['broot'], 'roadvis', 'roblox')
    res = export(W, P, out)
    print(json.dumps({k: v for k, v in res.items() if k != 'files'}, indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
