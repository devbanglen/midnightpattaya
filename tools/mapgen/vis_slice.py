"""VIS-4 visual slice - modular facades for the procedural buildings between Pattaya Nuea and Pattaya Tai.

  .venv\\Scripts\\python tools\\mapgen\\vis_slice.py tools\\mapgen\\config\\vis_slice.json

What it does
- Slice: the stretch of Beach Road (Pattaya Sai Nueng) and Second Road (Pattaya Sai Song) between Pattaya Nuea and
  Pattaya Tai, the sois between them and `frontage_studs` of frontage outside them (beachfront included). Every
  procedural building box whose centre lies in that area is upgraded IN PLACE, except categories in `skip_categories`
  (temples), boxes a landmark proxy replaces (build/landmarks) and boxes whose every face is a party wall.
- The upgrade keeps the box exactly: an invisible collision "VisHull" with the box's size/CFrame (so collisions,
  raycasts and the road clearance are unchanged), a visible "VisCore" inset only on the decorated faces, and facade
  modules from a small KIT (config `kit`, exported to manifest.luau) placed between the core face and the original box
  face. No facade part ever leaves the original box; roof modules (AC, water tank, plant room) sit on the roof.
- Only placements are exported per building (face, module, span, bays, floors); the builder makes the Parts from the
  kit at build time. This script makes the same Parts in Python to count them and to run the overlap checks.
- Checks (shapely, must all be 0): facade parts outside their own box, on a road + sidewalk corridor, on a junction or
  joint disc, on street furniture, on coast props, on a landmark proxy, on the Walking Street gate, on a city prop
  (palm / street light / neon sign), inside another building box.
Inputs (copies of the main build, read-only): build/central_pattaya (graph, buildings, roblox chunk modules = what is
built in Studio), build/landmarks, build/furniture, build/coast. Output: build/vis_slice/roblox/manifest.luau +
chunk_v<cx>_<cz>[_k].luau (ServerStorage.PattayaDataVisSlice), build/vis_slice/vis_slice.json (report),
build/vis_slice/vis_slice_check.png.
"""
import glob, json, math, os, re, sys
from collections import Counter, defaultdict
import numpy as np
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import unary_union
from shapely import affinity
from shapely.strtree import STRtree

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PALETTES = ['hotel', 'condo', 'apartment', 'mall', 'commercial', 'shophouse', 'house', 'temple', 'parking']
FACE_NAMES = {1: 'Right', 2: 'Left', 3: 'Back', 4: 'Front'}     # Roblox NormalId of the box face
# face -> (local outward normal (x, z), local U axis (x, z), half extent key, span key)
FACES = {1: ((1, 0), (0, 1), 'w', 'd'), 2: ((-1, 0), (0, -1), 'w', 'd'),
         3: ((0, 1), (-1, 0), 'd', 'w'), 4: ((0, -1), (1, 0), 'd', 'w')}
ADJ = {1: (4, 3), 2: (3, 4), 3: (1, 2), 4: (2, 1)}             # faces at the u = -span/2 and u = +span/2 ends


def lua(v, ind=''):
    """Python value -> Luau literal (numbers rounded to 3 decimals)."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return 'nil'
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        r = round(float(v), 3)
        return str(int(r)) if r == int(r) else repr(r)
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    if isinstance(v, (list, tuple)):
        return '{' + ', '.join(lua(x, ind) for x in v) + '}'
    if isinstance(v, dict):
        items = []
        for k, x in v.items():
            key = k if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', k) else '[' + lua(k) + ']'
            items.append(f'{key} = {lua(x, ind)}')
        return '{' + ', '.join(items) + '}'
    raise TypeError(type(v))


def lit_hash(osm, face, mod, k, j, pi, mod_n):
    """Deterministic per-window number; PattayaVisSliceBuilder.litHash is the same integer formula."""
    return (osm % mod_n) * 7919 + face * 104729 + mod * 1009 + k * 131 + j * 31 + pi * 7


def read_rows(path, key, stride):
    s = open(path, encoding='utf-8').read()
    m = re.search(key + r' = \{([^}]*)\}', s)
    if not m or not m.group(1).strip():
        return []
    v = [float(t) for t in m.group(1).split(',') if t.strip()]
    return [v[i:i + stride] for i in range(0, len(v) - stride + 1, stride)]


def rect(cx, cz, ux, uz, hu, hn):
    """rectangle centred at (cx, cz) with half extent hu along (ux, uz) and hn along the perpendicular"""
    nx, nz = -uz, ux
    return Polygon([(cx - ux * hu - nx * hn, cz - uz * hu - nz * hn), (cx + ux * hu - nx * hn, cz + uz * hu - nz * hn),
                    (cx + ux * hu + nx * hn, cz + uz * hu + nz * hn), (cx - ux * hu + nx * hn, cz - uz * hu + nz * hn)])


def box_poly(b):
    r = Polygon([(-b['w'] / 2, -b['d'] / 2), (b['w'] / 2, -b['d'] / 2), (b['w'] / 2, b['d'] / 2), (-b['w'] / 2, b['d'] / 2)])
    return affinity.translate(affinity.rotate(r, b['yaw']), b['x'], b['z'])


class Kit:
    def __init__(self, cfg):
        self.mods = list(cfg['kit'].keys())
        self.kit = cfg['kit']
        self.roof_mods = list(cfg['roof_kit'].keys())
        self.roof = cfg['roof_kit']
        self.lit_cfg = cfg['lit']

    def face_parts(self, b, pl, style):
        """Parts of one placement: the Python twin of PattayaVisSliceBuilder's placement loop."""
        face, mi, u0, u1, nb, v0, vh, nv, dv, flags = pl
        mod = self.kit[self.mods[mi - 1]]
        ins = b['ins'][face - 1]
        span = u1 - u0
        bw = span / nb
        out = []
        for k in range(nv):
            vb = v0 + k * dv
            for pi, sp in enumerate(mod['parts']):
                if sp.get('neon') and not (flags & 1):
                    continue
                if (sp.get('text') or sp.get('neon')) and (flags & 2):
                    continue
                rep = sp['rep']
                cells = [(u0, span)] if rep == 0 else [(u0 + j * bw, bw) for j in range(nb)] if rep == 1 else \
                    [(u0 + j * bw, bw) for j in range(nb + 1)]
                for j, (cs, cw) in enumerate(cells):
                    fa, oa, fb, ob = sp['u']
                    if rep == 2:
                        ua, ub = cs + oa, cs + ob
                    else:
                        ua, ub = cs + fa * cw + oa, cs + fb * cw + ob
                    ua, ub = max(ua, u0), min(ub, u1)
                    ga, goa, gb, gob = sp['v']
                    va, vbb = vb + ga * vh + goa, vb + gb * vh + gob
                    if 'n' in sp:
                        n1 = min(-ins + sp['n'][1], 0.0)
                        n0 = -ins + sp['n'][0]
                    else:
                        n1 = min(sp['nh'][1], 0.0)
                        n0 = max(sp['nh'][0], -ins)
                    if ub - ua < 0.1 or vbb - va < 0.05 or n1 - n0 < 0.05:
                        continue
                    lit = False
                    if sp.get('lit'):
                        pct = style['lit_' + sp['lit']]
                        pct = max(0, min(100, pct + b['osm'] % (2 * self.lit_cfg['spread'] + 1) - self.lit_cfg['spread']))
                        hsh = lit_hash(b['osm'], face, mi, k, j, pi, self.lit_cfg['hash_mod'])
                        lit = hsh % 100 < pct
                        if sp.get('litOnly') and not lit:
                            continue
                    out.append({'k': sp['k'], 'face': face, 'u': (ua, ub), 'v': (va, vbb), 'n': (n0, n1), 'lit': lit,
                                'neon': bool(sp.get('neon')), 'text': bool(sp.get('text')), 'mod': self.mods[mi - 1]})
        return out

    def roof_parts(self, b, rr):
        mi, fx, fz = rr
        mod = self.roof[self.roof_mods[mi - 1]]
        return [{'k': sp['k'], 'roof': True, 'c': (fx + sp['c'][0], b['h'] + sp['c'][1], fz + sp['c'][2]), 's': sp['s'],
                 'mod': self.roof_mods[mi - 1]} for sp in mod['parts']]


def part_footprint(b, p):
    """world footprint polygon of a generated part (+ its y range)"""
    yaw = math.radians(b['yaw'])
    X = (math.cos(yaw), math.sin(yaw))           # local +X in world x/z
    Z = (-math.sin(yaw), math.cos(yaw))          # local +Z
    if p.get('roof'):
        lx, ly, lz = p['c']
        sx, sy, sz = p['s']
        cx = b['x'] + X[0] * lx + Z[0] * lz
        cz = b['z'] + X[1] * lx + Z[1] * lz
        return rect(cx, cz, X[0], X[1], sx / 2, sz / 2), (ly - sy / 2, ly + sy / 2)
    (nx, nz), (ux, uz), half, _ = FACES[p['face']]
    dist = b[half] / 2
    um = (p['u'][0] + p['u'][1]) / 2
    nm = dist + (p['n'][0] + p['n'][1]) / 2
    lx, lz = nx * nm + ux * um, nz * nm + uz * um
    cx = b['x'] + X[0] * lx + Z[0] * lz
    cz = b['z'] + X[1] * lx + Z[1] * lz
    Uw = (X[0] * ux + Z[0] * uz, X[1] * ux + Z[1] * uz)
    return rect(cx, cz, Uw[0], Uw[1], (p['u'][1] - p['u'][0]) / 2, (p['n'][1] - p['n'][0]) / 2), p['v']


def face_segment(b, f):
    yaw = math.radians(b['yaw'])
    X = np.array([math.cos(yaw), math.sin(yaw)])
    Z = np.array([-math.sin(yaw), math.cos(yaw)])
    (nx, nz), (ux, uz), half, spank = FACES[f]
    c = np.array([b['x'], b['z']])
    N = X * nx + Z * nz
    U = X * ux + Z * uz
    mid = c + N * b[half] / 2
    return mid - U * b[spank] / 2, mid + U * b[spank] / 2, N, U


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    inp = {k: os.path.join(ROOT, v) for k, v in cfg['inputs'].items()}
    out_dir = os.path.join(ROOT, cfg['out'])
    rb_dir = os.path.join(out_dir, 'roblox')
    os.makedirs(rb_dir, exist_ok=True)
    kit = Kit(cfg)
    L = cfg['level_studs']
    G0 = L + cfg['ground_extra_studs']
    C = cfg['chunk_size_studs']
    stats = Counter()

    # --- inputs ------------------------------------------------------------------------------------------------------
    g = json.load(open(os.path.join(inp['central'], 'graph_game.json'), encoding='utf-8'))
    meta = {b['id']: b for b in json.load(open(os.path.join(inp['central'], 'buildings_game.json'), encoding='utf-8'))['buildings']}
    man_src = open(os.path.join(inp['central'], 'roblox', 'manifest.luau'), encoding='utf-8').read()
    level_check = float(re.search(r'levelStuds = ([\d.]+)', man_src).group(1))
    assert abs(level_check - L) < 0.01, f'levelStuds {level_check} != config {L}'
    rows, props = [], {'palms': [], 'lights': [], 'signs': []}
    for f in sorted(glob.glob(os.path.join(inp['central'], 'roblox', 'chunk_*.luau'))):
        cid = re.search(r'chunk_(.*)\.luau$', f).group(1)
        for r in read_rows(f, 'buildings', 8):
            rows.append({'src': cid, 'x': r[0], 'z': r[1], 'w': r[2], 'd': r[3], 'h': r[4], 'yaw': r[5],
                         'palette': PALETTES[int(r[6]) - 1], 'osm': int(r[7])})
        props['palms'] += read_rows(f, 'palms', 2)
        props['lights'] += read_rows(f, 'lights', 4)
        props['signs'] += read_rows(f, 'signs', 8)
    rows_by_osm = {r['osm']: r for r in rows}
    ids = Counter(r['osm'] for r in rows)
    assert max(ids.values()) == 1, 'duplicate OSM ids in the building rows'
    lm = json.load(open(os.path.join(inp['landmarks'], 'landmarks.json'), encoding='utf-8'))
    replaced = {r['osm'] for r in lm['replaces'] if r['dataset'] == 'central'}

    # --- obstacles -----------------------------------------------------------------------------------------------------
    obst = defaultdict(list)                                         # class -> [polygon]
    for e in g['edges']:
        obst['road+sidewalk'].append(LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'], cap_style=2, join_style=1))
    for m in re.finditer(r'\{ id = -?\d+, x = (-?[\d.]+), z = (-?[\d.]+), r = ([\d.]+) \}', man_src):
        obst['junction disc'].append(Point(float(m[1]), float(m[2])).buffer(float(m[3])))
    jv = [float(t) for t in re.search(r'return \{([^}]*)\}', open(os.path.join(inp['central'], 'roblox', 'joints.luau'),
                                                                encoding='utf-8').read()).group(1).split(',') if t.strip()]
    for i in range(0, len(jv), 4):
        obst['joint disc'].append(Point(jv[i + 1], jv[i + 2]).buffer(jv[i + 3]))
    gate = re.search(r'id = "walking_street_gate".*?x = (-?[\d.]+), z = (-?[\d.]+), dx = (-?[\d.]+), dz = (-?[\d.]+), span = ([\d.]+)',
                     man_src)
    if gate:                                                         # PattayaBuilder gate: 2 pillars + beam across
        gx, gz, gdx, gdz, gspan = (float(gate[i]) for i in range(1, 6))
        obst['walking street gate'].append(rect(gx, gz, -gdz, gdx, (gspan + 3) / 2 + cfg['obstacles']['gate_pad_studs'],
                                                1.5 + cfg['obstacles']['gate_pad_studs']))
    for x, z in props['palms']:
        obst['city prop'].append(Point(x, z).buffer(1.0))
    for r in props['lights']:
        obst['city prop'].append(Point(r[0], r[1]).buffer(0.6))
    for r in props['signs']:                                         # city neon sign: w wide, 0.6 thick, outside a face
        obst['city prop'].append(rect(r[0], r[1], -r[3], r[2], r[4] / 2 + 0.4, 0.5))
    fur = json.load(open(inp['furniture'], encoding='utf-8'))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import furniture as furniture_mod                                # exact part footprints of the furniture layer
    for ch in fur['chunks'].values():
        for kind, lst in ch.items():
            if kind == 'crossings':                                  # zebra bars lie on the road slab
                continue
            for it in lst:
                for _, poly in furniture_mod.parts_of(kind, it['row']):
                    obst['furniture'].append(poly)
    for f in glob.glob(os.path.join(inp['coast'], 'chunk_b*.luau')):
        for kind, (stride, rad) in cfg['obstacles']['coast_stride_radius'].items():
            for r in read_rows(f, kind, stride):
                obst['coast prop'].append(Point(r[0], r[1]).buffer(rad))
    for f in glob.glob(os.path.join(inp['landmarks'], 'roblox', 'chunk_l*.luau')):
        for r in read_rows(f, 'parts', 15):
            sx, sz, x, z, rx, ry, rz = r[2], r[4], r[5], r[7], r[8], r[9], r[10]
            if abs(rx) < 1e-3 and abs(rz) < 1e-3:
                obst['landmark'].append(rect(x, z, math.cos(-ry), math.sin(-ry), sx / 2, sz / 2))
            else:
                obst['landmark'].append(Point(x, z).buffer(math.sqrt(r[2] ** 2 + r[3] ** 2 + r[4] ** 2) / 2))
    otrees = {k: STRtree(v) for k, v in obst.items()}
    hulls = [box_poly(r) for r in rows]
    htree = STRtree(hulls)
    road_polys = obst['road+sidewalk']
    rtree = otrees['road+sidewalk']
    main_road_names = set(cfg['slice']['roads'])
    main_roads = unary_union([LineString(e['pts']) for e in g['edges'] if e.get('name_en') in main_road_names])
    coast_lines = [LineString(c['pts']) for c in g.get('coastline', []) if len(c['pts']) > 1]

    # --- slice area ----------------------------------------------------------------------------------------------------
    sc = cfg['slice']

    def named(n):
        return unary_union([LineString(e['pts']) for e in g['edges'] if e.get('name_en') == n])
    north, south = named(sc['north_road']), named(sc['south_road'])
    pts = []
    for n in sc['roads']:
        road = named(n)
        pn = np.array(min(((p.x, p.y) for p in [Point(c) for ln in getattr(road, 'geoms', [road]) for c in ln.coords]),
                          key=lambda c: north.distance(Point(c))))
        ps = np.array(min(((p.x, p.y) for p in [Point(c) for ln in getattr(road, 'geoms', [road]) for c in ln.coords]),
                          key=lambda c: south.distance(Point(c))))
        axis = (ps - pn) / np.linalg.norm(ps - pn)
        span = float(np.linalg.norm(ps - pn))
        for ln in getattr(road, 'geoms', [road]):
            for c in ln.coords:
                t = float((np.array(c) - pn) @ axis)
                if -1 <= t <= span + 1:
                    pts.append(c)
        pts += [tuple(pn), tuple(ps)]
        stats[f'slice end {n}'] = f'{pn.round(1).tolist()} -> {ps.round(1).tolist()}'
    core_area = MultiPoint(pts).convex_hull
    area = core_area.buffer(sc['frontage_studs'], join_style=2)

    # --- buildings in the slice ----------------------------------------------------------------------------------------
    cats = {c: s for s, st in cfg['styles'].items() for c in st['cats']}
    style_names = list(cfg['styles'].keys())
    sel = []
    for i, r in enumerate(rows):
        if not area.contains(Point(r['x'], r['z'])):
            continue
        stats['in slice area'] += 1
        m = meta.get(r['osm'])
        cat = m['cat'] if m else r['palette']
        if r['osm'] in replaced:
            stats['skip: replaced by a landmark proxy'] += 1
            continue
        if cat in sc['skip_categories']:
            stats[f'skip: category {cat}'] += 1
            continue
        if min(r['w'], r['d']) < sc['min_side_studs']:
            stats['skip: thinner than min_side_studs'] += 1
            continue
        lev = m['levels'] if m else max(1, round((r['h'] - cfg['ground_extra_studs']) / L))
        if abs(lev * L + cfg['ground_extra_studs'] - r['h']) > 0.2:
            lev = max(1, round((r['h'] - cfg['ground_extra_studs']) / L))
            stats['levels re-derived from h'] += 1
        sel.append(dict(r, cat=cat, levels=lev, idx=i, beachfront=bool(m and m.get('beachfront'))))

    # --- faces ---------------------------------------------------------------------------------------------------------
    fc = cfg['faces']

    blockers = [(hulls[j], 'box', rows[j]['osm']) for j in range(len(rows))]
    for cls, lst in obst.items():
        blockers += [(poly, cls, None) for poly in lst]
    btree = STRtree([x[0] for x in blockers])

    def free_span(b, f, ins):
        """[lo, hi] along U (face-centred) where the facade band (box face .. ins inside) touches no other box and no
        obstacle; None when less than min_span / half the face stays free"""
        a, z, N, U = face_segment(b, f)
        span = b[FACES[f][3]]
        band = Polygon([a, z, z - N * (ins + 0.05), a - N * (ins + 0.05)])
        mid = (a + z) / 2
        cuts = []
        for j in btree.query(band):
            poly, cls, osm = blockers[j]
            if osm is not None and (osm == b['osm'] or osm in replaced):
                continue
            if poly.intersects(band):
                inter = poly.intersection(band)
                if inter.area < 1e-4:
                    continue
                ts = [float((np.array(c) - mid) @ U) for geom in getattr(inter, 'geoms', [inter])
                      for c in getattr(geom, 'exterior', geom).coords]
                cuts.append((max(min(ts), -span / 2), min(max(ts), span / 2), cls))
        if not cuts:
            return (-span / 2, span / 2), []
        cuts.sort()
        free, cur = [], -span / 2
        for lo, hi, _ in cuts:
            if lo > cur:
                free.append((cur, lo))
            cur = max(cur, hi)
        if cur < span / 2:
            free.append((cur, span / 2))
        best = max(free, key=lambda t: t[1] - t[0], default=None)
        if best is None or best[1] - best[0] < max(fc['min_span_studs'], span / 2):
            return None, [c[2] for c in cuts]
        return (best[0] + 0.3, best[1] - 0.3), [c[2] for c in cuts]

    def face_info(b, f, ins):
        a, z, N, U = face_segment(b, f)
        seg = LineString([a, z])
        span = b[FACES[f][3]]
        lim, cut_by = free_span(b, f, ins)
        for cls in set(cut_by):
            stats[f'face band cut by {cls}'] += 1
        probe = Polygon([a, z, z + N * fc['see_studs'], a + N * fc['see_studs']])
        wall = Polygon([a, z, z + N * fc['party_wall_probe_studs'], a + N * fc['party_wall_probe_studs']])
        blocked = 0.0
        for j in htree.query(wall):
            if j != b['idx'] and hulls[j].intersects(wall):
                blocked += hulls[j].intersection(wall).area
        party = blocked / max(wall.area, 1e-6) >= fc['party_wall_min_fraction']
        best = None
        for j in rtree.query(probe):
            if road_polys[j].intersects(probe):
                d = seg.distance(road_polys[j].intersection(probe))
                best = d if best is None else min(best, d)
        sees_main = bool(probe.intersects(main_roads))
        if best is not None and sees_main:
            best -= fc['main_road_bonus_studs']
        if best is None and b['beachfront'] and any(probe.intersects(cl) for cl in coast_lines):
            best = fc['see_studs']
        if lim is None:
            party = True
        return {'face': f, 'span': span, 'party': party, 'dist': best, 'main': sees_main, 'lim': lim}

    # --- placements ----------------------------------------------------------------------------------------------------
    neon_left = cfg['neon']['max_total_strips']
    sign_pts = [(r[0], r[1]) for r in props['signs']]
    sign_tree = STRtree([Point(p) for p in sign_pts]) if sign_pts else None
    built, skipped_party = [], 0
    texts_cfg = cfg['texts']
    text_list, text_index = [], {}
    for key, lst in texts_cfg.items():
        for t in lst:
            text_index[(key, t)] = len(text_list) + 1
            text_list.append(t)
    # neon goes first to the buildings on the two main roads (sorted by OSM id for determinism)
    sel.sort(key=lambda b: b['osm'])
    for b in sel:
        st = cfg['styles'][cats[b['cat']]]
        infos = [face_info(b, f, st['ins']) for f in (1, 2, 3, 4)]
        cand = [fi for fi in infos if not fi['party'] and fi['span'] >= fc['min_span_studs']]
        seeing = sorted([fi for fi in cand if fi['dist'] is not None], key=lambda fi: fi['dist'])
        if seeing:
            faces = [seeing[0]]
            for fi in seeing[1:]:
                if len(faces) >= st['max_faces']:
                    break
                if st.get('second_face_needs_main_road') and not fi['main']:
                    continue
                faces.append(fi)
        elif cand:
            faces = [max(cand, key=lambda fi: fi['span'])]
            stats['front face picked by span (no road within see_studs)'] += 1
        else:
            skipped_party += 1
            continue
        G = min(G0, b['h'])
        fl = (b['h'] - G) / (b['levels'] - 1) if b['levels'] > 1 else L
        osm = b['osm']
        neon_on = 0
        if st['neon_pct'] and b['cat'] in st.get('neon_cats', st['cats']) and (osm * 2654435761) % 100 < st['neon_pct'] \
                and neon_left > 0:
            neon_on = 1 + (osm // 7) % 2                      # 1 cyan, 2 magenta
        bay_scale = 1.0
        for attempt in range(4):
            ins = [0.0, 0.0, 0.0, 0.0]
            for fi in faces:
                ins[fi['face'] - 1] = st['ins']
            bd = dict(b, ins=ins)
            pls, roofs = [], []
            for fi in faces:
                f = fi['face']
                a_, b_ = ADJ[f]
                u0 = max(-fi['span'] / 2 + ins[a_ - 1], fi['lim'][0])
                u1 = min(fi['span'] / 2 - ins[b_ - 1], fi['lim'][1])
                span = u1 - u0
                a, z, N, U = face_segment(b, f)
                has_sign = False
                if sign_tree is not None:
                    seg = LineString([a, z])
                    has_sign = any(seg.distance(Point(sign_pts[j])) < 1.5 for j in sign_tree.query(seg.buffer(1.5)))
                flags = (1 if neon_on else 0) | (2 if has_sign else 0)
                if has_sign:
                    stats['faces with a city neon sign: own signboard/neon skipped'] += 1
                gb = max(1, round(span / (st['ground_bay'] * bay_scale)))
                pls.append([f, kit.mods.index(st['ground']) + 1, u0, u1, gb, 0.0, G, 1, 0.0, flags])
                if b['levels'] > 1:
                    midh = b['h'] - G
                    for wname, wbay in st['whole']:
                        nbw = 1 if wbay == 0 else max(1, round(span / (wbay * bay_scale)))
                        pls.append([f, kit.mods.index(wname) + 1, u0, u1, nbw, G, midh, 1, 0.0, flags])
                    for mname in st['mid']:
                        mb = max(1, round(span / (st['mid_bay'] * bay_scale)))
                        pls.append([f, kit.mods.index(mname) + 1, u0, u1, mb, G, fl, b['levels'] - 1, fl, flags])
                if st['parapet'] and b['h'] >= 10:
                    pls.append([f, kit.mods.index('parapet_a') + 1, u0, u1, 1, b['h'] - 1.2, 1.2, 1, 0.0, flags])
            # roof modules on the core top, placed along the local x axis
            cw = b['w'] - ins[0] - ins[1]
            cd = b['d'] - ins[2] - ins[3]
            ccx = (ins[1] - ins[0]) / 2                        # core centre offset in local x (left inset - right inset)
            ccz = (ins[3] - ins[2]) / 2
            free_x = cw
            slots = []
            for rname in st['roof']:
                need = cfg['roof_kit'][rname]['need']
                if need[0] <= cw - 2 and need[1] <= cd - 2 and b['h'] >= 14 and sum(s[1] for s in slots) + need[0] <= free_x - 2:
                    slots.append((rname, need[0]))
            xpos = ccx - (sum(s[1] for s in slots) + 2 * (len(slots) - 1)) / 2
            for rname, wneed in slots:
                roofs.append([kit.roof_mods.index(rname) + 1, round(xpos + wneed / 2, 2), round(ccz, 2)])
                xpos += wneed + 2
            # the builder gets these numbers rounded to 3 decimals: generate from exactly the same values
            pls = [[round(v, 3) if isinstance(v, float) else v for v in pl] for pl in pls]
            keep = []
            for rr in roofs:                                    # a roof module must not stick into a taller box / prop
                ok = True
                for p in kit.roof_parts(bd, rr):
                    fp, _ = part_footprint(bd, p)
                    for j in btree.query(fp):
                        poly, cls, bo = blockers[j]
                        if bo is not None and (bo == b['osm'] or bo in replaced or rows_by_osm[bo]['h'] <= b['h']):
                            continue
                        if poly.intersects(fp) and poly.intersection(fp).area > 1e-6:
                            ok = False
                if ok:
                    keep.append(rr)
                else:
                    stats['roof module dropped (taller box / prop over the roof)'] += 1
            roofs = keep
            parts = []
            for pl in pls:
                parts += kit.face_parts(bd, pl, st)
            for rr in roofs:
                parts += kit.roof_parts(bd, rr)
            n_parts = len(parts) + 2                              # + VisHull + VisCore
            if n_parts <= st['cap'] or attempt == 3:
                break
            if attempt == 1 and len(faces) > 1:
                faces = faces[:1]                                 # drop the secondary face before coarsening further
            else:
                bay_scale *= 1.5
        if n_parts > st['cap']:
            stats['over style cap after coarsening'] += 1
        neon_strips = sum(1 for p in parts if p.get('neon'))
        if neon_strips:
            neon_left -= neon_strips
        elif neon_on:
            neon_on = 0
        tkey = st['texts']
        txt = 0
        if tkey:
            lst = texts_cfg[tkey]
            txt = text_index[(tkey, lst[(osm // 3) % len(lst)])]
        built.append({'b': b, 'style': cats[b['cat']], 'ins': ins, 'pls': pls, 'roofs': roofs, 'parts': parts,
                      'n': n_parts, 'faces': [fi['face'] for fi in faces], 'G': G, 'fl': fl, 'neon': neon_on,
                      'acc': osm % len(cfg['accents']) + 1, 'sc': (osm // 11) % len(cfg['sign_combos']) + 1, 'txt': txt,
                      'bd': bd})
    stats['skip: every face a party wall / too narrow'] = skipped_party

    # --- checks --------------------------------------------------------------------------------------------------------
    checks = Counter({k: 0 for k in ['outside own box', 'above own box (facade, not roof)', *obst.keys(), 'other building box']})
    examples = defaultdict(list)
    total_parts = 0
    for B in built:
        b = B['b']
        own = hulls[b['idx']].buffer(0.02, join_style=2)
        for p in B['parts']:
            fp, (y0, y1) = part_footprint(b, p)
            if p.get('roof'):
                stats['roof parts (above the box, non-colliding)'] += 1
                if not fp.within(own):
                    checks['outside own box'] += 1
            else:
                if not fp.within(own):
                    checks['outside own box'] += 1
                    examples['outside own box'].append((b['osm'], p['k']))
                if y1 > b['h'] + 1e-6 or y0 < -1e-6:
                    checks['above own box (facade, not roof)'] += 1
                    examples['above own box'].append((b['osm'], p['k'], round(y1, 2), b['h']))
            for cls, tree in otrees.items():
                for j in tree.query(fp):
                    if obst[cls][j].intersects(fp) and obst[cls][j].intersection(fp).area > 1e-6:
                        checks[cls] += 1
                        if len(examples[cls]) < 5:
                            examples[cls].append((b['osm'], p['k']))
                        break
            for j in htree.query(fp):
                if j != b['idx'] and hulls[j].intersects(fp) and hulls[j].intersection(fp).area > 1e-6 \
                        and rows[j]['osm'] not in replaced and y0 < rows[j]['h'] - 1e-6:
                    checks['other building box'] += 1
                    if len(examples['other building box']) < 5:
                        examples['other building box'].append((b['osm'], p['k'], rows[j]['osm']))
                    break
        total_parts += B['n']
    bad = {k: v for k, v in checks.items() if v}

    # --- chunks + batches ----------------------------------------------------------------------------------------------
    by_src = defaultdict(list)
    for B in built:
        by_src[B['b']['src']].append(B)
    chunks = []
    for src in sorted(by_src, key=lambda s: (int(s.split('_')[1]), int(s.split('_')[0]))):     # north -> south
        lst = sorted(by_src[src], key=lambda B: (B['b']['z'], B['b']['x']))
        groups, cur, n = [], [], 0
        for B in lst:
            if cur and n + B['n'] > cfg['max_parts_per_chunk']:
                groups.append(cur)
                cur, n = [], 0
            cur.append(B)
            n += B['n']
        if cur:
            groups.append(cur)
        for k, grp in enumerate(groups):
            cid = f'v{src}' if k == 0 else f'v{src}_{k + 1}'
            chunks.append({'id': cid, 'src': src, 'items': grp, 'parts': sum(B['n'] for B in grp)})
    over = [c['id'] for c in chunks if c['parts'] > cfg['max_parts_per_chunk']]
    batches, order = {}, []
    for i in range(0, len(chunks), cfg['max_chunks_per_batch']):
        name = f's{i // cfg["max_chunks_per_batch"] + 1}'
        batches[name] = [c['id'] for c in chunks[i:i + cfg['max_chunks_per_batch']]]
        order.append(name)

    # --- write Luau ----------------------------------------------------------------------------------------------------
    for f in glob.glob(os.path.join(rb_dir, '*.luau')):
        os.remove(f)
    attribution = g['attribution']
    head = ('-- generated by tools/mapgen/vis_slice.py from build/central_pattaya (' + attribution +
            '; OSM base ' + g.get('osm_base', '?') + '); do not edit\n')
    for c in chunks:
        blds = []
        for B in c['items']:
            b = B['b']
            blds.append({'osm': b['osm'], 'x': b['x'], 'z': b['z'], 'w': b['w'], 'd': b['d'], 'h': b['h'], 'yaw': b['yaw'],
                         'style': style_names.index(B['style']) + 1, 'cat': b['cat'], 'ins': B['ins'], 'acc': B['acc'],
                         'sc': B['sc'], 'txt': B['txt'], 'neon': B['neon'], 'parts': B['n'],
                         'p': [v for pl in B['pls'] for v in pl],
                         'r': [v for rr in B['roofs'] for v in rr]})
        body = (head + f'-- vis slice chunk {c["id"]}: {len(blds)} buildings, {c["parts"]} Parts (map-local studs; the builder adds '
                'the ORIGIN). Placement rows p (10 numbers): face, module, u0, u1, bays, v0, height, count, step, flags (1 neon, '
                '2 no own signboard: a city neon sign hangs there). Roof rows r (3): module, x, z.\n'
                f'return {{ id = {lua(c["id"])}, src = {lua(c["src"])}, parts = {c["parts"]},\n  buildings = {{\n' +
                ''.join('    ' + lua(x) + ',\n' for x in blds) + '  },\n}\n')
        open(os.path.join(rb_dir, f'chunk_{c["id"]}.luau'), 'w', encoding='utf-8', newline='\n').write(body)
    mods_out = []
    for name in kit.mods:
        m = cfg['kit'][name]
        mods_out.append({'name': name, 'slot': m['slot'], 'parts': m['parts']})
    roof_out = [{'name': n, 'slot': cfg['roof_kit'][n]['slot'], 'parts': cfg['roof_kit'][n]['parts']} for n in kit.roof_mods]
    style_out = [{'name': s, 'cats': cfg['styles'][s]['cats'], 'litWin': cfg['styles'][s]['lit_win'],
                  'litShop': cfg['styles'][s]['lit_shop']} for s in style_names]
    manifest = {
        'name': 'vis_slice', 'attribution': attribution, 'osmBase': g.get('osm_base', '?'),
        'chunkSize': C, 'levelStuds': L, 'totalParts': total_parts, 'buildings': len(built),
        'chunks': [c['id'] for c in chunks], 'batchOrder': order, 'batches': batches,
        'chunkParts': {c['id']: c['parts'] for c in chunks},
        'lit': cfg['lit'], 'colors': cfg['colors'], 'accents': cfg['accents'], 'signCombos': cfg['sign_combos'],
        'texts': text_list, 'materials': cfg['materials'], 'styles': style_out, 'modules': mods_out, 'roofModules': roof_out,
    }
    open(os.path.join(rb_dir, 'manifest.luau'), 'w', encoding='utf-8', newline='\n').write(
        head + '-- ServerStorage.PattayaDataVisSlice.manifest: the facade KIT (module definitions; the builder makes every Part '
        'from these), colours, materials (MaterialLibrary name -> fallback Enum.Material), sign texts (generic, no brands), '
        'chunks and batches.\nreturn ' + lua(manifest) + '\n')

    # --- report + check image ------------------------------------------------------------------------------------------
    cat_counts = Counter(B['b']['cat'] for B in built)
    style_parts = Counter()
    mod_parts = Counter()
    for B in built:
        style_parts[B['style']] += B['n']
        for p in B['parts']:
            mod_parts[p['mod']] += 1
    lit_n = sum(1 for B in built for p in B['parts'] if p.get('lit'))
    neon_n = sum(1 for B in built for p in B['parts'] if p.get('neon'))
    text_n = sum(1 for B in built for p in B['parts'] if p.get('text'))
    bounds = area.bounds
    report = {
        'attribution': attribution, 'osm_base': g.get('osm_base'), 'slice_area_bounds_xz': [round(v, 1) for v in bounds],
        'slice_area_world_x': [round(bounds[0] + 20000, 1), round(bounds[2] + 20000, 1)],
        'buildings_upgraded': len(built), 'categories': dict(cat_counts.most_common()),
        'total_parts': total_parts, 'hull_core_parts': 2 * len(built), 'style_parts': dict(style_parts.most_common()),
        'module_parts': dict(mod_parts.most_common()), 'lit_windows': lit_n, 'neon_strips': neon_n, 'signboards': text_n,
        'chunks': {c['id']: {'src': c['src'], 'buildings': len(c['items']), 'parts': c['parts']} for c in chunks},
        'batches': {k: {'chunks': v, 'parts': sum(next(c['parts'] for c in chunks if c['id'] == i) for i in v)} for k, v in batches.items()},
        'checks': dict(checks), 'check_examples': {k: v[:5] for k, v in examples.items()},
        'stats': {k: v for k, v in stats.items()}, 'over_part_cap_chunks': over,
    }
    json.dump(report, open(os.path.join(out_dir, 'vis_slice.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    check_image(os.path.join(out_dir, 'vis_slice_check.png'), g, area, core_area, rows, built)

    print(f'slice area bounds x {bounds[0]:.0f}..{bounds[2]:.0f}, z {bounds[1]:.0f}..{bounds[3]:.0f} (map-local)')
    print(f'buildings upgraded {len(built)}: ' + ', '.join(f'{k} {v}' for k, v in cat_counts.most_common()))
    print('; '.join(f'{k}: {v}' for k, v in stats.items()))
    print(f'parts {total_parts:,} (budget {cfg["part_budget"]:,}); per style ' + ', '.join(f'{k} {v}' for k, v in style_parts.most_common()))
    print(f'lit windows {lit_n}, neon strips {neon_n}, signboards {text_n}')
    print(f'{len(chunks)} chunks (max {max(c["parts"] for c in chunks)} parts), {len(order)} batches: ' +
          ', '.join(f'{k}={report["batches"][k]["parts"]}' for k in order))
    print('checks: ' + ', '.join(f'{k} {v}' for k, v in checks.items()))
    if bad or over or total_parts > cfg['part_budget']:
        print('FAILED:', bad, over, total_parts)
        sys.exit(1)


def check_image(path, g, area, core_area, rows, built):
    from PIL import Image, ImageDraw
    x0, z0, x1, z1 = area.bounds
    s = 1800 / max(x1 - x0, z1 - z0)
    im = Image.new('RGB', (int((x1 - x0) * s) + 20, int((z1 - z0) * s) + 20), (236, 233, 226))
    d = ImageDraw.Draw(im)
    tr = lambda p: (10 + (p[0] - x0) * s, 10 + (p[1] - z0) * s)
    d.polygon([tr(p) for p in area.exterior.coords], outline=(120, 120, 200))
    for e in g['edges']:
        d.line([tr(p) for p in e['pts']], fill=(70, 70, 80), width=max(1, int(e['width'] * s)))
    done = {B['b']['osm'] for B in built}
    col = {'shophouse': (205, 150, 90), 'hotel': (230, 90, 60), 'condo': (190, 70, 160), 'commercial': (60, 150, 200),
           'industrial': (130, 130, 130), 'house': (120, 180, 100)}
    for r in rows:
        if r['osm'] not in done and area.intersects(Point(r['x'], r['z']).buffer(200)):
            d.polygon([tr(p) for p in box_poly(r).exterior.coords], outline=(170, 170, 170))
    for B in built:
        b = B['b']
        d.polygon([tr(p) for p in box_poly(b).exterior.coords], fill=col[B['style']])
        for f in B['faces']:
            a, z, N, U = face_segment(b, f)
            d.line([tr(a), tr(z)], fill=(0, 220, 255) if B['neon'] else (20, 20, 20), width=3)
    im.save(path)


if __name__ == '__main__':
    main(sys.argv[1])
