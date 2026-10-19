"""Junction aprons + sidewalk corner fills for the Pattaya city (central slice + wide world + Bira corridor).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python.exe tools\\mapgen\\junction_aprons.py tools\\mapgen\\config\\aprons.json --build-root D:\\ROBLOXRACE\\build
  ... --no-determinism      skip the second (determinism) run
  ... --audit-only          only the before-audit (no files written)

The problem (docs/ROAD_APRONS.md): the terrain beside the roads is at y = -2, road tops at 1.0, sidewalk tops at 1.6.
PattayaBuilder ends every road slab at its node (junction / joint disc of radius r on top) and starts the sidewalks
r + sidewalk studs from the node, so at every junction corner and at every soi mouth the ground lies open 3 studs
below the road between the two slab edges and the two sidewalk ends. A car that cuts the corner drops a wheel there.

The fix comes from the BUILT road data (the chunk modules after road_fix / dual, read with road_check.py, which ports
PattayaBuilder's stripe / offset / trim 1:1), not from sampling holes:
  arms     every edge with a slab at a junction node (degree >= 3, or a degree-2 bend whose sidewalks are trimmed by a
           joint disc / bend trim / slab cut) is an arm. Arm cross-section at s = r + sidewalk (where the builder
           starts its sidewalks; r = junction disc radius, else the bend trim, at least the slab cut; an edge with no
           sidewalk uses r + no_sidewalk_arm_studs): centre C, slab edge points PL / PR (+-width/2), sidewalk outer
           corners QL / QR (+-(width/2 + sidewalk), only on sides that have a sidewalk).
  throat   arms sorted by angle; for two neighbouring arms less than straight_deg apart, the triangle
           node - PL(i) - PR(i+1) (the convex hull of the two cross-sections and the node). The throat polygon is the
           union of these triangles.
  apron    throat minus road slabs, fill triangles (dual.py), sidewalk strips, an inscribed core of every disc, building
           boxes (+clearance, both yaw senses as road_fix.building_boxes), props (palms, street lights, signs, furniture
           ground parts, coast props, landmark parts, gate, corridor dressing) and earlier aprons; cleaned (opening,
           simplify), cut in triangles (constrained Delaunay) or kept as one box when it is a rectangle. Top y = 0.98
           (2 cm under the road top: no z-fighting), 4 thick, Asphalt 62,63,68, name "Road", RoadFill / Apron / JunctionId.
  corner   for every neighbouring arm pair with a sidewalk on at least one of the two facing sides: the convex hull of
           PL, QL, QR, PR (plus the node triangle for pairs >= straight_deg and < 180 deg apart: the straight side of a
           tee) minus every road surface (slabs, fills, discs, aprons), sidewalks, buildings (+clearance), earlier
           corner fills. A prop inside it (the cut would leave a hole down to the ground) -> the corner is left open
           and listed. Top 1.58, 3.6 thick, Concrete 150,148,142, name "Sidewalk", CornerFill / JunctionId.
Checks (asserted, on the rounded output rows): every apron piece inside its throat polygon; apron top below road top;
no piece intersects a building box or a prop footprint; corner fills touch no road surface or sidewalk; no two
pieces overlap. Determinism: the whole build runs twice and the outputs must be byte-identical.
Audit: points every step_studs on the line offset_studs outside the road surface (slabs + fills + discs); a point
is a drop (> drop_studs) when it lies on no sidewalk / corner fill / apron / building box / shelter pad (the terrain
is at -2 there: 3 studs under the road). Drop points closer than cluster_link_studs form a cluster; a cluster within
a handled junction's throat radius is a junction cluster, the others are mid-block (roads built without sidewalks).
Counts before / after, citywide and within focus_radius_studs of focus_world.

Writes build/aprons/: roblox/manifest.luau + roblox/chunk_a<cx>_<cz>.luau (512-stud chunks of the map-local piece
centroid, batches of <= 8 chunks; ServerStorage.PattayaApronBuilder builds them), aprons.json (counts, junctions
handled / skipped with reasons, corners left open, checks, audit), apron_check_*.png. Nothing else is touched.
Map data (c) OpenStreetMap contributors, ODbL 1.0.
"""
import argparse, hashlib, json, math, os, re, sys, time
from collections import Counter, defaultdict
import numpy as np
import shapely
from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import road_check as rc  # noqa: E402  (PattayaBuilder geometry, ported 1:1)

EPS_AREA = 1e-3


def lua_str(s):
    if s is None:
        return 'nil'
    out = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return '"' + ''.join(c if ord(c) >= 32 else f'\\{ord(c)}' for c in out) + '"'


def unit(v):
    n = math.hypot(v[0], v[1])
    return np.array([v[0] / n, v[1] / n]) if n > 1e-12 else np.array([1.0, 0.0])


def rect(cx, cz, ux, uz, hu, hn):
    """rectangle centred at (cx, cz), half extent hu along (ux, uz), hn across"""
    nx, nz = -uz, ux
    return Polygon([(cx - ux * hu - nx * hn, cz - uz * hu - nz * hn), (cx + ux * hu - nx * hn, cz + uz * hu - nz * hn),
                    (cx + ux * hu + nx * hn, cz + uz * hu + nz * hn), (cx - ux * hu + nx * hn, cz - uz * hu + nz * hn)])


def read_rows(text, key, stride):
    m = re.search(r'\b' + key + r' = \{([^}]*)\}', text)
    if not m or not m.group(1).strip():
        return []
    v = [float(t) for t in m.group(1).split(',') if t.strip()]
    return [v[i:i + stride] for i in range(0, len(v) - stride + 1, stride)]


def polys_of(g):
    """the Polygon parts of any geometry"""
    if g is None or g.is_empty:
        return []
    if g.geom_type == 'Polygon':
        return [g]
    if hasattr(g, 'geoms'):
        return [p for q in g.geoms for p in polys_of(q)]
    return []


# ---- inputs ----------------------------------------------------------------------------------------------------------
def load_world(cfg, broot):
    """built road geometry of every dataset (as PattayaBuilder makes it), building boxes and prop footprints"""
    W = dict(edges=[], roads=[], road_sw=[], walks=[], discs=[], blds=[], props=[], pads=[], stats=Counter())
    seen = set()
    for ds, rel in cfg['inputs']['datasets']:
        d = os.path.join(broot, rel)
        if not os.path.exists(os.path.join(d, 'manifest.luau')):
            W['stats'][f'dataset missing: {ds}'] += 1
            continue
        es, dd, jr = rc.load_dataset(d)
        for e in es:
            e['ds'] = ds
            e['jr_a'], e['jr_b'] = jr.get(e['a'], 0.0), jr.get(e['b'], 0.0)
            ws = [r for r in rc.sidewalk_rects(e, jr) if r.area > EPS_AREA]
            for r in [r for q in rc.slab_pieces(e) for r in rc.stripe_rects(q, e['width'])] + rc.fill_polys(e):
                if r.area > EPS_AREA:
                    W['roads'].append(r)
                    W['road_sw'].append(bool(ws))                 # the edge builds a sidewalk (on at least one side)
            W['walks'] += ws
            if e['id'] in seen:                                       # same edge exported twice (built twice too)
                W['stats']['edge exported by two datasets'] += 1
                continue
            seen.add(e['id'])
            W['edges'].append(e)
        for k in sorted(dd, key=lambda k: (isinstance(k, tuple), k if not isinstance(k, tuple) else k[1])):
            x, z, r = dd[k]
            nid = k if not isinstance(k, tuple) else k[1]
            W['discs'].append(dict(ds=ds, node=int(nid), kind='joint' if isinstance(k, tuple) else 'junction', x=x, z=z, r=r))
        # buildings (both yaw senses, as road_fix.building_boxes) and the props of the chunk modules
        for f in sorted(os.listdir(d)):
            if not (f.startswith('chunk_') and f.endswith('.luau')):
                continue
            t = open(os.path.join(d, f), encoding='utf-8').read()
            for b in read_rows(t, 'buildings', 8):
                x, z, w, dd_, h, yaw = b[:6]
                for sg in (1, -1):
                    a = math.radians(sg * yaw)
                    W['blds'].append(rect(x, z, math.cos(a), math.sin(a), w / 2, dd_ / 2))
            pc = cfg['props']
            for p in read_rows(t, 'palms', 2):
                W['props'].append(Point(p).buffer(pc['palm_radius'], 8))
            for p in read_rows(t, 'lights', 4):
                W['props'].append(Point(p[:2]).buffer(pc['light_radius'], 8))     # pole only: arm and lamp are 19 up
            for p in read_rows(t, 'signs', 8):                                    # neon sign + frame (face of a building)
                W['props'].append(rect(p[0], p[1], -p[3], p[2], p[4] / 2 + 0.4, 0.6))
            for p in read_rows(t, 'trees', 3):                                    # corridor dressing
                W['props'].append(Point(p[:2]).buffer(2.0, 8))
            for p in read_rows(t, 'poles', 5):
                W['props'].append(Point(p[:2]).buffer(0.8, 8))
            m = re.search(r'\bgantries = \{(.*?)\},\n', t, re.S)
            if m:
                for g in re.findall(r'\{([^{}]*)\}', m.group(1)):
                    v = [float(u) for u in g.split(',')[:5]]
                    x, z, dx, dz, span = v
                    pr = np.array([-dz, dx])
                    for sg in (-1, 1):
                        c = np.array([x, z]) + pr * sg * span / 2
                        W['props'].append(Point(c).buffer(2.0, 8))
        man = open(os.path.join(d, 'manifest.luau'), encoding='utf-8').read()
        gate = re.search(r'id = "walking_street_gate".*?x = (-?[\d.]+), z = (-?[\d.]+), dx = (-?[\d.]+), dz = (-?[\d.]+), span = ([\d.]+)', man)
        if gate:
            gx, gz, gdx, gdz, span = (float(gate[i]) for i in range(1, 6))
            W['props'].append(rect(gx, gz, -gdz, gdx, (span + 3) / 2 + 1, 2.5))
    # furniture layer: every part that reaches down to the sidewalk / ground (arms, boards, roofs hang 4+ studs up)
    fp = os.path.join(broot, cfg['inputs']['furniture'])
    if os.path.exists(fp):
        import furniture as fm
        low = set(fm.GROUND) | {'ShelterPost', 'ShelterWall', 'ShelterBench'}
        fur = json.load(open(fp, encoding='utf-8'))
        for c in sorted(fur['chunks']):
            for kind, lst in sorted(fur['chunks'][c].items()):
                if kind == 'crossings':
                    continue
                for it in lst:
                    for name, poly in fm.parts_of(kind, it['row']):
                        if name in low:
                            (W['pads'] if name == 'ShelterPad' else W['props']).append(poly)
    else:
        W['stats']['furniture data missing'] += 1
    cd = os.path.join(broot, cfg['inputs']['coast'])
    if os.path.isdir(cd):
        for f in sorted(os.listdir(cd)):
            if f.startswith('chunk_b'):
                t = open(os.path.join(cd, f), encoding='utf-8').read()
                for kind, (stride, rad) in cfg['props']['coast_stride_radius'].items():
                    for r in read_rows(t, kind, int(stride)):
                        W['props'].append(Point(r[0], r[1]).buffer(rad, 8))
    ld = os.path.join(broot, cfg['inputs']['landmarks'])
    if os.path.isdir(ld):
        for f in sorted(os.listdir(ld)):
            if f.startswith('chunk_l'):
                t = open(os.path.join(ld, f), encoding='utf-8').read()
                for r in read_rows(t, 'parts', 15):
                    sx, sz, x, z, rx, ry, rz = r[2], r[4], r[5], r[7], r[8], r[9], r[10]
                    if abs(rx) < 1e-3 and abs(rz) < 1e-3:
                        W['props'].append(rect(x, z, math.cos(-ry), math.sin(-ry), sx / 2, sz / 2))
                    else:
                        W['props'].append(Point(x, z).buffer(math.sqrt(r[2] ** 2 + r[3] ** 2 + r[4] ** 2) / 2, 8))
    W['props'] += W['pads']
    for k in ('roads', 'walks', 'blds', 'props', 'pads'):
        W[k + '_tree'] = STRtree(W[k]) if W[k] else None
    W['disc_polys'] = [Point(q['x'], q['z']).buffer(q['r'], 16) for q in W['discs']]
    W['disc_tree'] = STRtree(W['disc_polys'])
    return W


def near(W, key, geom):
    t = W[key + '_tree']
    if t is None:
        return []
    return [W[key][i] for i in sorted(t.query(geom))]


# ---- arms and junctions ------------------------------------------------------------------------------------------------
def arm_of(e, end, cfg):
    """the cross-section of edge e at node end 'a' / 'b' where its sidewalks start (see module doc)"""
    if e['hidden']:
        return None
    P = e['pts'] if end == 'a' else e['pts'][::-1]
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    total = float(seg.sum())
    if total < 2.0:
        return None
    ra = (e['jr_a'] or e['jA']) if end == 'a' else (e['jr_b'] or e['jB'])
    ra = max(ra or 0.0, (e['cutA'] if end == 'a' else e['cutB']) or 0.0)
    # sidewalks as PattayaBuilder.buildEdge: trimmed by r + sidewalk at a disc / bend trim, built on swSide only
    sw = e['sidewalk']
    ra_e = max(e['jr_a'] or e['jA'] or 0.0, e['cutA'] or 0.0)
    rb_e = max(e['jr_b'] or e['jB'] or 0.0, e['cutB'] or 0.0)
    built = sw > 0 and rc.trim(e['pts'], ra_e + sw if ra_e > 0 else 0, rb_e + sw if rb_e > 0 else 0) is not None
    lside, rside = (1, -1) if end == 'a' else (-1, 1)                # builder side (a->b frame) of the arm's left / right
    sw_l = built and (e['swSide'] is None or e['swSide'] == lside)
    sw_r = built and (e['swSide'] is None or e['swSide'] == rside)
    s = ra + (sw if (sw_l or sw_r) else cfg['throat']['no_sidewalk_arm_studs'])
    s = min(s, total - 1.0)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    k = int(min(max(np.searchsorted(cum, s, side='right') - 1, 0), len(seg) - 1))
    while k < len(seg) - 1 and seg[k] < 1e-6:
        k += 1
    t = unit(P[k + 1] - P[k])
    C = P[k] + t * (s - cum[k])
    n = np.array([-t[1], t[0]])
    w2 = e['width'] / 2
    node = P[0]
    v = C - node
    ang = math.atan2(v[1], v[0]) if math.hypot(*v) > 0.5 else math.atan2(t[1], t[0])
    return dict(edge=e['id'], ds=e['ds'], node_pt=node, s=s, r=ra, C=C, t=t, n=n, w=e['width'], sw=sw, ang=ang,
                PL=C + n * w2, PR=C - n * w2, QL=C + n * (w2 + sw) if sw_l else None, QR=C - n * (w2 + sw) if sw_r else None)


def junctions_of(W, cfg):
    inc = defaultdict(list)
    for e in W['edges']:
        inc[e['a']].append((e, 'a'))
        inc[e['b']].append((e, 'b'))                                # a loop edge gives two arms at its node
    disc_at = {}
    for q in W['discs']:
        disc_at.setdefault(q['node'], q)
    J, skipped = [], Counter()
    for nid in sorted(inc):
        lst = inc[nid]
        deg = len(lst)
        if deg == 1:
            skipped['dead end (degree 1): no corner'] += 1
            continue
        arms = [a for a in (arm_of(e, end, cfg) for e, end in lst) if a is not None]
        if deg == 2:
            trimmed = any(a['r'] > 0 and (a['QL'] is not None or a['QR'] is not None) for a in arms)
            if not trimmed:
                skipped['degree-2 joint without sidewalk trim (sidewalks run through)'] += 1
                continue
        if len(arms) < 2:
            skipped['fewer than 2 arms with a slab (hidden / too short edges)'] += 1
            continue
        arms.sort(key=lambda a: (a['ang'], a['edge']))
        q = disc_at.get(nid)
        N = np.array([q['x'], q['z']]) if q else np.mean([a['node_pt'] for a in arms], axis=0)
        J.append(dict(node=nid, deg=deg, kind='junction' if deg >= 3 else 'bend', N=N, arms=arms, disc=q))
    return J, skipped


def pairs_of(j):
    arms = j['arms']
    out = []
    for i in range(len(arms)):
        A, B = arms[i], arms[(i + 1) % len(arms)]
        d = (B['ang'] - A['ang']) % (2 * math.pi)
        out.append((A, B, math.degrees(d)))
    return out


def cleanup(g, T):
    """opening (drops slivers thinner than 2 x open_studs; mitre joins keep straight edges), clipped back to the region,
    then shrunk by shrink_studs so the 0.01-stud rounding of the rows never pushes a piece onto a neighbour"""
    if g.is_empty:
        return g
    o = T['open_studs']
    h = g.buffer(-o, join_style=2).buffer(o, join_style=2).intersection(g)
    h = h.buffer(-T['shrink_studs'], join_style=2)
    return h.simplify(0.01, preserve_topology=True).intersection(h) if not h.is_empty else h


def small_holes(p, T):
    """True when every interior ring is a small prop pit (a palm / pole / post cut out, area <= max_pit_area)"""
    return all(Polygon(r).area <= T['max_pit_area'] for r in p.interiors)


def is_rect(p, tol_deg=1.0):
    if p.interiors:
        return None
    c = list(p.exterior.simplify(0.02).coords)[:-1]
    if len(c) != 4 or p.interiors:
        return None
    c = [np.array(v) for v in c]
    for i in range(4):
        a, b, d = c[i - 1], c[i], c[(i + 1) % 4]
        u, v = unit(a - b), unit(d - b)
        if abs(float(u @ v)) > math.sin(math.radians(tol_deg)):
            return None
    ctr = sum(c) / 4
    e1, e2 = c[1] - c[0], c[2] - c[1]
    L, Wd = math.hypot(*e1), math.hypot(*e2)
    if L < Wd:
        e1, e2, L, Wd = e2, e1, Wd, L
    u = unit(e1)
    return [ctr[0], ctr[1], u[0], u[1], L, Wd]


def pieces_of(poly, T):
    """convex pieces of one cleaned polygon: one box when it is a rectangle, else constrained Delaunay triangles"""
    r = is_rect(poly)
    if r:
        return [('box', r)]
    out = []
    for t in polys_of(shapely.constrained_delaunay_triangles(poly)):
        c = list(t.exterior.coords)[:3]
        if t.area < T['min_tri_area']:
            continue
        longest = max(math.dist(c[i], c[(i + 1) % 3]) for i in range(3))
        if 2 * t.area / longest < T['min_tri_altitude']:
            continue
        out.append(('tri', [c[0][0], c[0][1], c[1][0], c[1][1], c[2][0], c[2][1]]))
    return out


def wedge_count(tri):
    """Parts PattayaApronBuilder makes for a triangle (as PattayaBuilder.roadTriangle: split at the altitude foot)"""
    a, b, c = np.array(tri[0:2]), np.array(tri[2:4]), np.array(tri[4:6])
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    if bc > ab and bc >= ca:
        a, b, c = b, c, a
    elif ca > ab and ca > bc:
        a, b, c = c, a, b
    L = np.linalg.norm(b - a)
    if L < 0.05:
        return 0
    d = (b - a) / L
    foot = a + d * float((c - a) @ d)
    if np.linalg.norm(c - foot) < 0.05:
        return 0
    return sum(1 for corner in (a, b) if np.linalg.norm(foot - corner) > 0.05)


def piece_poly(kind, v):
    if kind == 'box':
        return rect(v[0], v[1], v[2], v[3], v[4] / 2, v[5] / 2)
    return Polygon([(v[0], v[1]), (v[2], v[3]), (v[4], v[5])])


def rnd(kind, v):
    if kind == 'box':
        return [round(v[0], 3), round(v[1], 3), round(v[2], 5), round(v[3], 5), round(v[4], 3), round(v[5], 3)]
    return [round(x, 3) for x in v]


# ---- the layer ---------------------------------------------------------------------------------------------------------
def build(cfg, W):
    T, CL = cfg['throat'], cfg['clearance']
    J, skipped = junctions_of(W, cfg)
    stats = Counter()
    jinfo = {}
    aprons = []                 # (node, kind, row)
    placed_a = []               # apron polygons (STR-less list, local unions via a grid)
    grid_a = defaultdict(list)
    G = 64.0

    def grid_add(grid, poly, idx):
        x0, z0, x1, z1 = poly.bounds
        for gx in range(math.floor(x0 / G), math.floor(x1 / G) + 1):
            for gz in range(math.floor(z0 / G), math.floor(z1 / G) + 1):
                grid[(gx, gz)].append(idx)

    def grid_near(grid, store, geom):
        x0, z0, x1, z1 = geom.bounds
        ids = set()
        for gx in range(math.floor(x0 / G), math.floor(x1 / G) + 1):
            for gz in range(math.floor(z0 / G), math.floor(z1 / G) + 1):
                ids.update(grid.get((gx, gz), ()))
        return [store[i] for i in sorted(ids)]

    straight = T['straight_deg']
    throats = {}
    # pass 1: aprons (road height) in the throats
    for j in J:
        N = j['N']
        tris = []
        for A, B, d in pairs_of(j):
            if d < straight:
                t = Polygon([tuple(N), tuple(A['PL']), tuple(B['PR'])])
                if t.is_valid and t.area > EPS_AREA:
                    tris.append(t)
        rad = max(a['s'] for a in j['arms']) + max(a['w'] for a in j['arms']) + 12
        j['radius'] = rad
        info = jinfo[j['node']] = dict(node=j['node'], kind=j['kind'], deg=j['deg'], x=round(float(N[0]), 1), z=round(float(N[1]), 1),
                                       arms=len(j['arms']), aprons=0, corners=0, exposed=0.0, notes=[])
        if not tris:
            info['notes'].append('no throat: neighbouring arms >= straight_deg apart')
            continue
        throat = unary_union(tris)
        throats[j['node']] = throat
        area_box = box(N[0] - rad, N[1] - rad, N[0] + rad, N[1] + rad)
        road_u = unary_union(near(W, 'roads', area_box))
        walk_u = unary_union(near(W, 'walks', area_box))
        disc_u = unary_union([W['disc_polys'][i] for i in sorted(W['disc_tree'].query(area_box))])
        exposed = throat.difference(road_u).difference(disc_u).difference(walk_u)
        info['exposed'] = round(exposed.area, 1)
        if exposed.area < T['min_piece_area']:
            continue
        core = unary_union([W['disc_polys'][i].centroid.buffer(W['discs'][i]['r'], T['disc_core_segments'])
                            for i in sorted(W['disc_tree'].query(area_box))])
        bl = unary_union([b.buffer(CL['building_studs'], join_style=2) for b in near(W, 'blds', area_box)])
        pr_list = near(W, 'props', area_box)
        pr = unary_union([p.buffer(CL['prop_studs']) for p in pr_list])
        prev = unary_union(grid_near(grid_a, placed_a, area_box))
        reg = throat.difference(road_u).difference(walk_u).difference(core).difference(bl).difference(prev)
        reg_np = reg
        reg = reg.difference(pr)
        reg = cleanup(reg, T)
        for p in sorted(polys_of(reg), key=lambda p: (round(p.centroid.x, 2), round(p.centroid.y, 2))):
            if p.area < T['min_piece_area'] or p.difference(disc_u).area < T['min_piece_area']:
                continue
            if p.interiors and not small_holes(p, T):
                info['notes'].append(f'apron piece at ({p.centroid.x:.1f}, {p.centroid.y:.1f}) left open: a large prop stands inside it')
                stats['apron pieces left open (large prop inside)'] += 1
                continue
            for kind, v in pieces_of(p, T):
                v = rnd(kind, v)
                aprons.append((j['node'], kind, v))
                poly = piece_poly(kind, v)
                grid_add(grid_a, poly, len(placed_a))
                placed_a.append(poly)
                info['aprons'] += 1
        if reg_np.area - reg.area > 1.0 and not reg_np.difference(pr).equals(reg_np):
            stats['throats touched by a prop (clipped)'] += 1

    # pass 2: corner fills (sidewalk height) beyond the throat chords
    corners, open_corners = [], []
    placed_c, grid_c = [], defaultdict(list)
    for j in J:
        N = j['N']
        rad = j['radius']
        area_box = box(N[0] - rad, N[1] - rad, N[0] + rad, N[1] + rad)
        road_u = None
        info = jinfo[j['node']]
        for pi, (A, B, d) in enumerate(pairs_of(j)):
            QL, QR = A['QL'], B['QR']
            if QL is None and QR is None:
                continue
            pts = [tuple(A['PL'])] + ([tuple(QL)] if QL is not None else []) + ([tuple(QR)] if QR is not None else []) + [tuple(B['PR'])]
            hull = MultiPoint(pts).convex_hull
            if straight <= d < 180.0:
                t = Polygon([tuple(N), tuple(A['PL']), tuple(B['PR'])])
                if t.is_valid:
                    hull = hull.union(t)
            if hull.geom_type != 'Polygon' or hull.area < T['min_corner_area']:
                continue
            if road_u is None:
                roads_l = near(W, 'roads', area_box) + [W['disc_polys'][i] for i in sorted(W['disc_tree'].query(area_box))] \
                    + grid_near(grid_a, placed_a, area_box)
                road_u = unary_union(roads_l).buffer(CL['road_studs'], join_style=2)
                walk_u = unary_union(near(W, 'walks', area_box))
                bl_raw = unary_union(near(W, 'blds', area_box))
                bl = unary_union([b.buffer(CL['building_studs'], join_style=2) for b in near(W, 'blds', area_box)])
                pr_u = unary_union([p.buffer(CL['prop_studs']) for p in near(W, 'props', area_box)])
            gap = hull.difference(road_u).difference(walk_u).difference(bl_raw)
            if gap.area < T['min_corner_area']:
                continue
            where = (round(float(gap.centroid.x), 1), round(float(gap.centroid.y), 1))
            if gap.area > T['max_corner_area']:
                open_corners.append(dict(node=j['node'], x=where[0], z=where[1], area=round(gap.area, 1),
                                         hull=round(hull.area, 1), reason='open area > max_corner_area (acute / long corner: a block, not a kerb corner)'))
                continue
            prev = unary_union(grid_near(grid_c, placed_c, hull))
            reg = gap.difference(bl).difference(prev)
            hit = pr_u.intersection(reg)
            reg2 = cleanup(reg.difference(pr_u), T)
            ps = [p for p in polys_of(reg2) if p.area >= T['min_corner_area']]
            if hit.area > 0.01 and any(not small_holes(p, T) for p in ps):
                open_corners.append(dict(node=j['node'], x=where[0], z=where[1], area=round(gap.area, 1),
                                         reason='a large prop stands inside the corner (the cut would leave a big hole to the ground)'))
                continue
            if not ps:
                open_corners.append(dict(node=j['node'], x=where[0], z=where[1], area=round(gap.area, 1),
                                         reason='nothing left after building / prop clearance'))
                continue
            done = 0
            for p in sorted(ps, key=lambda p: (round(p.centroid.x, 2), round(p.centroid.y, 2))):
                for kind, v in pieces_of(p, T):
                    v = rnd(kind, v)
                    corners.append((j['node'], kind, v))
                    poly = piece_poly(kind, v)
                    grid_add(grid_c, poly, len(placed_c))
                    placed_c.append(poly)
                    done += 1
            info['corners'] += done
            if hit.area > 0.01:
                stats['corner fills clipped around a prop at the edge'] += 1
    return dict(J=J, skipped=skipped, jinfo=jinfo, aprons=aprons, corners=corners, open_corners=open_corners,
                stats=stats, throats=throats)


# ---- checks ------------------------------------------------------------------------------------------------------------
def checks(cfg, W, R):
    T = cfg['throat']
    bad = Counter()
    ex = defaultdict(list)
    ap = [(n, k, v, piece_poly(k, v)) for n, k, v in R['aprons']]
    co = [(n, k, v, piece_poly(k, v)) for n, k, v in R['corners']]

    def note(key, n, poly):
        bad[key] += 1
        if len(ex[key]) < 5:
            ex[key].append([n, round(poly.centroid.x, 1), round(poly.centroid.y, 1)])

    for n, k, v, p in ap:
        th = R['throats'].get(n)
        if th is None or p.difference(th.buffer(0.02)).area > 0.01:
            note('apron outside its throat polygon', n, p)
        if cfg['apron']['top'] >= cfg['road_top']:
            note('apron top not below road top', n, p)
        for w in near(W, 'walks', p):
            if p.intersection(w).area > 0.01:
                note('apron on a sidewalk strip', n, p); break
    for n, k, v, p in co:
        for r in near(W, 'roads', p) + [W['disc_polys'][i] for i in sorted(W['disc_tree'].query(p))]:
            if p.intersection(r).area > 0.01:
                note('corner fill on a road surface / disc', n, p); break
        for w in near(W, 'walks', p):
            if p.intersection(w).area > 0.01:
                note('corner fill on a sidewalk strip', n, p); break
    allp = ap + co
    tree = STRtree([p for *_, p in allp])
    for i, (n, k, v, p) in enumerate(allp):
        for b in near(W, 'blds', p):
            if p.intersects(b) and p.intersection(b).area > 1e-6:
                note('piece intersects a building box', n, p); break
        for q in near(W, 'props', p):
            if p.intersects(q) and p.intersection(q).area > 1e-6:
                note('piece intersects a prop footprint', n, p); break
        for jx in tree.query(p):
            if jx > i and p.intersection(allp[jx][3]).area > 0.01:
                note('two pieces overlap', n, p); break
    for n, k, v, p in ap:
        if p.area < 0.04:
            note('degenerate apron piece', n, p)
    return bad, ex


# ---- audit -------------------------------------------------------------------------------------------------------------
def audit(cfg, W, R=None):
    """drop points 2 studs outside the road surface; before (R None) or after (with aprons + corner fills)"""
    A = cfg['audit']
    C = cfg['chunk_size_studs']
    surf = W['roads'] + W['disc_polys']
    st = STRtree(surf)
    cells = set()
    for p in surf:
        x0, z0, x1, z1 = p.bounds
        for cx in range(math.floor(x0 / C), math.floor(x1 / C) + 1):
            for cz in range(math.floor(z0 / C), math.floor(z1 / C) + 1):
                cells.add((cx, cz))
    P = []
    for cx, cz in sorted(cells):
        cb = box(cx * C, cz * C, (cx + 1) * C, (cz + 1) * C)
        loc = [surf[i] for i in sorted(st.query(cb.buffer(A['offset_studs'] + 2)))]
        if not loc:
            continue
        ring = unary_union(loc).buffer(A['offset_studs'], quad_segs=4).boundary.intersection(cb)
        for ln in [g for g in (ring.geoms if hasattr(ring, 'geoms') else [ring]) if g.geom_type == 'LineString']:
            L = ln.length
            if L < 1e-6:
                continue
            q = shapely.line_interpolate_point(ln, np.arange(0, L, A['step_studs']))
            xy = shapely.get_coordinates(q)
            keep = (np.floor(xy[:, 0] / C) == cx) & (np.floor(xy[:, 1] / C) == cz)
            P.append(xy[keep])
    P = np.unique(np.round(np.vstack(P), 2), axis=0)
    pts = shapely.points(P[:, 0], P[:, 1])
    ok = np.zeros(len(P), bool)
    cover = [W['walks'], W['blds'], W['pads']]
    if R is not None:
        cover += [[piece_poly(k, v) for _, k, v in R['aprons']], [piece_poly(k, v) for _, k, v in R['corners']]]
    for polys in cover:
        if polys:
            ok[STRtree(polys).query(pts, predicate='intersects')[0]] = True
    D = P[~ok]
    # clusters (single linkage at cluster_link_studs)
    parent = np.arange(len(D))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    if len(D):
        dp = shapely.points(D[:, 0], D[:, 1])
        ii, jj = STRtree(dp).query(dp, predicate='dwithin', distance=A['cluster_link_studs'])
        for i, j in zip(ii, jj):
            if i < j:
                a, b = find(i), find(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    roots = np.array([find(i) for i in range(len(D))], int)
    # beside a road that has sidewalks (a junction / kerb gap: the hazard) or beside a road built without sidewalks
    sw_side = np.zeros(len(D), bool)
    if len(D):
        dp = shapely.points(D[:, 0], D[:, 1])
        ii, jj = STRtree(W['roads']).query(dp, predicate='dwithin', distance=A['offset_studs'] + 0.3)
        has, bare = np.zeros(len(D), bool), np.zeros(len(D), bool)
        flag = np.array(W['road_sw'])
        has[ii[flag[jj]]] = True
        bare[ii[~flag[jj]]] = True
        sw_side = has & ~bare
    return P, D, roots, sw_side


def audit_summary(cfg, P, D, roots, sw_side, J):
    A = cfg['audit']
    fx, fz = A['focus_world'][0] - cfg['origin_world'][0], A['focus_world'][1] - cfg['origin_world'][2]
    jc = [Point(j['N']).buffer(j['radius'] + A['junction_pad_studs'], 8) for j in J if j['kind'] == 'junction']
    jt = STRtree(jc)
    out = {}
    for scope in ('citywide', 'focus'):
        if scope == 'focus':
            m = np.hypot(D[:, 0] - fx, D[:, 1] - fz) <= A['focus_radius_studs'] if len(D) else np.zeros(0, bool)
            mp = np.hypot(P[:, 0] - fx, P[:, 1] - fz) <= A['focus_radius_studs']
        else:
            m = np.ones(len(D), bool)
            mp = np.ones(len(P), bool)
        d, r, sws = D[m], roots[m], sw_side[m]
        cl = sorted(set(r.tolist()))
        if len(d):
            near_j = np.zeros(len(d), bool)
            near_j[jt.query(shapely.points(d[:, 0], d[:, 1]), predicate='intersects')[0]] = True
            jcl = set(r[near_j].tolist())
        else:
            jcl = set()
        swc = set(r[sws].tolist())
        out[scope] = dict(samples=int(mp.sum()), drop_samples=int(len(d)), clusters=len(cl), junction_clusters=len(jcl),
                          midblock_clusters=len(cl) - len(jcl),
                          sidewalk_road_drop_samples=int(sws.sum()), sidewalk_road_clusters=len(swc),
                          bare_road_drop_samples=int((~sws).sum()))
    return out


# ---- output ------------------------------------------------------------------------------------------------------------
def fmt(v):
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    s = f'{float(v):.5f}'.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def render(cfg, R):
    """module texts {path: text} + report bits; pure function of R (determinism)"""
    C = cfg['chunk_size_studs']
    ch = defaultdict(lambda: dict(aprons=[], apronBoxes=[], corners=[], cornerBoxes=[]))
    parts = Counter()
    for kind_set, lst in (('apron', R['aprons']), ('corner', R['corners'])):
        for node, kind, v in lst:
            p = piece_poly(kind, v).centroid
            c = f'a{math.floor(p.x / C)}_{math.floor(p.y / C)}'
            key = {('apron', 'tri'): 'aprons', ('apron', 'box'): 'apronBoxes', ('corner', 'tri'): 'corners',
                   ('corner', 'box'): 'cornerBoxes'}[(kind_set, kind)]
            ch[c][key].append(v + [node])
            parts[(c, kind_set)] += 1 if kind == 'box' else wedge_count(v)
    fx, fz = cfg['audit']['focus_world'][0] - cfg['origin_world'][0], cfg['audit']['focus_world'][1] - cfg['origin_world'][2]
    order = sorted(ch, key=lambda c: (math.hypot((int(c[1:].split('_')[0]) + 0.5) * C - fx, (int(c.split('_')[1]) + 0.5) * C - fz), c))
    files = {}
    attr = cfg['attribution']
    ap, cp = cfg['apron'], cfg['corner']
    total = 0
    per_chunk = {}
    for c in order:
        d = ch[c]
        n = parts[(c, 'apron')] + parts[(c, 'corner')]
        per_chunk[c] = n
        total += n
        L = [f'-- generated by tools/mapgen/junction_aprons.py from the built road data (build/central_pattaya, build/pattaya_wide, '
             f'build/bira/roblox_corridor chunk modules; {attr}); do not edit',
             f'return {{ id = "{c}",',
             f'  -- aprons {{x1, z1, x2, z2, x3, z3, junction}}: road-height triangles (top {ap["top"]}), junction = OSM node id',
             '  aprons = {' + ','.join(fmt(x) for r in d['aprons'] for x in r) + '},',
             '  -- apronBoxes {cx, cz, ux, uz, length, width, junction}: road-height rectangles (length along (ux, uz))',
             '  apronBoxes = {' + ','.join(fmt(x) for r in d['apronBoxes'] for x in r) + '},',
             f'  -- corners {{x1, z1, x2, z2, x3, z3, junction}}: sidewalk-height corner fill triangles (top {cp["top"]})',
             '  corners = {' + ','.join(fmt(x) for r in d['corners'] for x in r) + '},',
             '  -- cornerBoxes {cx, cz, ux, uz, length, width, junction}: sidewalk-height corner fill rectangles',
             '  cornerBoxes = {' + ','.join(fmt(x) for r in d['cornerBoxes'] for x in r) + '},',
             f'  parts = {n},',
             '}']
        files[f'roblox/chunk_{c}.luau'] = '\n'.join(L) + '\n'
    B = cfg['budget']['batch_size_chunks']
    batches = {f'a{k // B + 1}': order[k:k + B] for k in range(0, len(order), B)}
    border = sorted(batches, key=lambda b: int(b[1:]))
    na = sum(1 for _ in R['aprons'])
    nc = sum(1 for _ in R['corners'])
    pa = sum(v for (c, k), v in parts.items() if k == 'apron')
    pc = sum(v for (c, k), v in parts.items() if k == 'corner')
    jh = sum(1 for i in R['jinfo'].values() if i['aprons'] or i['corners'])
    man = ['-- generated by tools/mapgen/junction_aprons.py; do not edit. Junction aprons (road height) and sidewalk corner',
           '-- fills at junction corners / soi mouths. Built by ServerStorage.PattayaApronBuilder (Build / Remove / Probe).',
           'return {',
           '  name = "aprons",',
           f'  attribution = {lua_str(attr)},',
           '  source = "build/central_pattaya/roblox, build/pattaya_wide/roblox, build/bira/roblox_corridor (built road data after road_fix)",',
           f'  roadTop = {fmt(cfg["road_top"])}, groundY = {fmt(cfg["ground_y"])}, chunkSize = {C},',
           f'  apron = {{ top = {fmt(ap["top"])}, thick = {fmt(ap["thick"])}, material = "{ap["material"]}", color = {{{",".join(map(str, ap["color"]))}}} }},',
           f'  corner = {{ top = {fmt(cp["top"])}, thick = {fmt(cp["thick"])}, material = "{cp["material"]}", color = {{{",".join(map(str, cp["color"]))}}} }},',
           '  chunks = {' + ','.join(lua_str(c) for c in order) + '},',
           '  batchOrder = {' + ','.join(lua_str(b) for b in border) + '},',
           '  batches = {']
    for b in border:
        man.append(f'    {b} = {{' + ','.join(lua_str(c) for c in batches[b]) + '},')
    man.append('  },')
    man.append(f'  counts = {{ junctions = {jh}, apronPieces = {na}, cornerPieces = {nc}, apronParts = {pa}, cornerParts = {pc}, parts = {total} }},')
    man.append('}')
    files['roblox/manifest.luau'] = '\n'.join(man) + '\n'
    return dict(files=files, order=order, batches=batches, per_chunk=per_chunk, total=total,
                counts=dict(junctions_with_pieces=jh, apron_pieces=na, corner_pieces=nc, apron_parts=pa, corner_parts=pc, parts=total))


def digest(files):
    h = hashlib.sha1()
    for k in sorted(files):
        h.update(k.encode()); h.update(files[k].encode())
    return h.hexdigest()


def check_image(cfg, W, R, name, cx, cz, rad, path, drops=None):
    from PIL import Image, ImageDraw
    S = max(1, int(900 / (2 * rad)))
    win = box(cx - rad, cz - rad, cx + rad, cz + rad)
    im = Image.new('RGB', (int(2 * rad * S), int(2 * rad * S)), (96, 74, 52))
    dr = ImageDraw.Draw(im)
    Tf = lambda p: ((p[0] - cx + rad) * S, (p[1] - cz + rad) * S)

    def fill(polys, col, outline=None):
        for p in polys:
            for q in polys_of(p.intersection(win.buffer(5))):
                dr.polygon([Tf(c) for c in q.exterior.coords], fill=col, outline=outline)
    fill(near(W, 'blds', win), (120, 120, 150))
    fill(near(W, 'roads', win), (55, 56, 62))
    fill([W['disc_polys'][i] for i in sorted(W['disc_tree'].query(win))], (55, 56, 62))
    fill(near(W, 'walks', win), (170, 168, 160))
    fill([piece_poly(k, v) for _, k, v in R['aprons'] if piece_poly(k, v).intersects(win)], (230, 120, 30), (255, 200, 120))
    fill([piece_poly(k, v) for _, k, v in R['corners'] if piece_poly(k, v).intersects(win)], (90, 200, 220), (200, 255, 255))
    fill(near(W, 'props', win), (40, 160, 60))
    for oc in R['open_corners']:
        if win.contains(Point(oc['x'], oc['z'])):
            x, y = Tf((oc['x'], oc['z']))
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 0, 0), width=2)
    if drops is not None and len(drops):
        for x, z in drops[(abs(drops[:, 0] - cx) < rad) & (abs(drops[:, 1] - cz) < rad)]:
            u, v = Tf((x, z))
            dr.rectangle([u - 1, v - 1, u + 1, v + 1], fill=(255, 40, 40))
    dr.text((6, 6), f'{name}: aprons orange, corner fills cyan, props green, open corners red rings, drops left red dots (map ({cx}, {cz}) +-{rad})',
            fill=(255, 255, 255))
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--build-root', default=os.path.join(ROOT, 'build'))
    ap.add_argument('--no-determinism', action='store_true')
    ap.add_argument('--audit-only', action='store_true')
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))
    t0 = time.time()
    W = load_world(cfg, a.build_root)
    print(f'loaded: {len(W["edges"])} edges, {len(W["roads"])} road parts, {len(W["walks"])} sidewalk strips, '
          f'{len(W["discs"])} discs, {len(W["blds"]) // 2} building boxes, {len(W["props"])} prop footprints ({time.time() - t0:.0f} s)')
    P0, D0, r0, s0 = audit(cfg, W)
    if a.audit_only:
        J, _ = junctions_of(W, cfg)
        for j in J:
            j['radius'] = max(x['s'] for x in j['arms']) + max(x['w'] for x in j['arms']) + 12
        print(json.dumps(audit_summary(cfg, P0, D0, r0, s0, J), indent=1))
        return
    R = build(cfg, W)
    out = render(cfg, R)
    bad, ex = checks(cfg, W, R)
    det = None
    if not a.no_determinism:
        R2 = build(cfg, load_world(cfg, a.build_root))
        det = digest(render(cfg, R2)['files']) == digest(out['files'])
    P1, D1, r1, s1 = audit(cfg, W, R)
    before, after = audit_summary(cfg, P0, D0, r0, s0, R['J']), audit_summary(cfg, P1, D1, r1, s1, R['J'])
    # write
    od = os.path.join(a.build_root, cfg['out_dir'])
    rd = os.path.join(od, 'roblox')
    os.makedirs(rd, exist_ok=True)
    for f in os.listdir(rd):
        if f.startswith('chunk_a') or f == 'manifest.luau':
            os.remove(os.path.join(rd, f))
    for k, txt in out['files'].items():
        open(os.path.join(od, k), 'w', encoding='utf-8', newline='\n').write(txt)
    jl = list(R['jinfo'].values())
    handled = [i for i in jl if i['aprons'] or i['corners']]
    covered = [i for i in jl if not (i['aprons'] or i['corners'])]
    big = [c for c, n in out['per_chunk'].items() if n > cfg['budget']['max_parts_per_chunk']]
    rep = dict(attribution=cfg['attribution'], counts=out['counts'], digest=digest(out['files']), deterministic=det,
               junction_nodes=dict(considered=len(jl), junctions=sum(1 for i in jl if i['kind'] == 'junction'),
                                   bends=sum(1 for i in jl if i['kind'] == 'bend'), handled=len(handled),
                                   nothing_exposed_or_no_piece=len(covered)),
               skipped=dict(R['skipped']), stats=dict(R['stats']), load_stats=dict(W['stats']),
               open_corners=dict(count=len(R['open_corners']), by_reason=dict(Counter(o['reason'] for o in R['open_corners'])),
                                 list=R['open_corners']),
               checks={k: bad.get(k, 0) for k in ('apron outside its throat polygon', 'apron top not below road top',
                                                   'apron on a sidewalk strip', 'corner fill on a road surface / disc',
                                                   'corner fill on a sidewalk strip', 'piece intersects a building box',
                                                   'piece intersects a prop footprint', 'two pieces overlap', 'degenerate apron piece')},
               check_examples=dict(ex), audit=dict(before=before, after=after, params=cfg['audit']),
               chunks=len(out['order']), batches=out['batches'], chunks_over_part_cap=big,
               junctions=sorted(jl, key=lambda i: i['node']))
    json.dump(rep, open(os.path.join(od, 'aprons.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=str)
    for name, cx, cz, rad in cfg.get('check_images', []):
        check_image(cfg, W, R, name, cx, cz, rad, os.path.join(od, f'apron_check_{name}.png'), D1)
    c = out['counts']
    print(f'junction nodes considered {len(jl)} (junctions {rep["junction_nodes"]["junctions"]}, bends {rep["junction_nodes"]["bends"]}); '
          f'handled {len(handled)}; nothing to fill {len(covered)}; skipped {sum(R["skipped"].values())}: {dict(R["skipped"])}')
    print(f'apron pieces {c["apron_pieces"]} ({c["apron_parts"]} parts), corner pieces {c["corner_pieces"]} ({c["corner_parts"]} parts), '
          f'total {c["parts"]} parts in {len(out["order"])} chunks / {len(out["batches"])} batches; over part cap: {big}')
    print(f'open corners {len(R["open_corners"])}: {rep["open_corners"]["by_reason"]}')
    print(f'stats {dict(R["stats"])}')
    print(f'checks {rep["checks"]}  examples {dict(ex)}')
    print(f'determinism: {det}  digest {rep["digest"]}')
    print(f'audit before {before}')
    print(f'audit after  {after}')
    print(f'done in {time.time() - t0:.0f} s -> {od}')
    if any(bad.values()) or det is False:
        sys.exit(1)


if __name__ == '__main__':
    main()
