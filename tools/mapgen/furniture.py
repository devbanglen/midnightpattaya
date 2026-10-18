"""Street furniture layer for the Pattaya city (central slice + wide world): traffic lights, zebra crossings,
bilingual road name signs, bus shelters, motorbike-taxi ("win") / taxi stands, utility poles along sois.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python.exe tools\\mapgen\\furniture.py tools\\mapgen\\config\\furniture.json [--build-root D:\\ROBLOXRACE\\build]

One-command rerun: it reads only generated road/building/prop outputs and one OSM node file, and rewrites
build/furniture/ (roblox/manifest.luau + roblox/chunk_f<cx>_<cz>.luau, furniture.json, furniture_check*.png).
Nothing else is written. After a road-geometry change (graph_game.json, layout.json, buildings_game.json) just
rerun it: every position is computed from the current edges (centreline + width + sidewalk).

Positions come from OSM nodes or from the rules below (config tools/mapgen/config/furniture.json):
- Traffic lights: OSM highway=traffic_signals nodes snapped to the nearest junction (degree >= 3) within
  `snap_to_junction_studs`; junction nodes closer than `cluster_studs` form one signalised junction (dual
  carriageways). Junctions with >= `rule_min_major_edges` incident trunk/primary/secondary edges and no OSM signal
  within `rule_min_gap_to_signal_studs` get lights by rule. One mast per inbound approach, on the driver's LEFT kerb
  (Thailand drives on the left), `kerb_margin_studs` outside the sidewalk, arm over the inbound lane, 3-lamp head
  facing the oncoming drivers; red / green alternate by approach order around the junction (no logic). OSM signals
  away from junctions are mid-block (pedestrian) signals: one mast per direction.
- Zebra crossings: OSM highway=crossing nodes (not crossing=no/unmarked, not crossing:markings=no) snapped to the
  nearest edge, plus one per signalised approach where OSM has none within `rule_skip_if_osm_within_studs`. Flat
  white bars on the slab (top y = ROAD_TOP + 0.07, 0.05 thick, CanCollide/CanQuery false), kept clear of junction
  discs, inset from the slab edge. The only furniture on the road (`onRoad = true`). Dual carriageways
  (tools/mapgen/dual.py, road_fix rule D): on an edge whose chunk line is merged / hidden / cut, the crossing is
  centred on the merged (kept) centreline of its group and spans that slab; bars are dropped (in pairs) until every
  bar lies on the BUILT road surface; a crossing with no built slab under it is skipped.
- Road name signs: at junctions (degree >= 3) with >= 2 distinct road names where at least one road is main /
  express tier: one blue board per name (Thai OSM `name` on top, OSM `name:en` below, exactly as tagged), on the
  kerb of that road near the junction, board parallel to the road it names.
- Bus shelters: OSM highway=bus_stop / public_transport=platform nodes; motorbike-taxi stands ("WIN"): OSM
  amenity=taxi (or motorcycle_taxi) with motorcycle=yes / taxi_vehicle=motorcycle; other amenity=taxi nodes get a
  plain "TAXI" stand (no operator names or brands). Both on the nearest edge's kerb on the node's side.
- Utility poles: residential / unclassified sois (none have poles yet), every `step_studs` on the a->b driver's left
  (kerb side), wired to the next pole of the same run; edges are taken central slice first, then outward, until the
  part target is reached.
Every non-crossing footprint keeps `kerb_margin_studs` beyond width/2 + sidewalk of every road (wide world, central
slice and the Bira corridor) and of every node disc, and stays clear of buildings, street lights, palms, signs,
landmarks, corridor dressing and other furniture. Export-time shapely checks (assertions) repeat that on the final
data; the road surface for the on-road checks is the BUILT one, read from the fixed chunk modules (after road_fix:
cut / hidden slabs, fill triangles, discs) besides the graph corridors. Map data (c) OpenStreetMap contributors, ODbL 1.0.
"""
import argparse, json, math, os, sys, zlib
from collections import Counter, defaultdict
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree
from shapely.ops import unary_union

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'circuit'))
import luau_table  # noqa: E402  (reader for the generated Luau data modules)

ROAD_TOP = 1.0
GROUND_Y = -2.0
CROSS_THICK = 0.05
CROSS_Y = ROAD_TOP + 0.045        # centre: bars span 1.02 .. 1.07 (lane markings end at 1.05)
MAIN_TIERS = {'main', 'express'}
OVER_ROAD = {'SignalArm', 'SignalHead', 'SignalLamp'}          # hang over the road by design (y >= 11)
GROUND = {'SignalPole', 'NameSignPost', 'ShelterPad', 'BusSignPole', 'TaxiPost', 'UtilityPole'}
THAI = lambda s: s is not None and any('\u0e00' <= c <= '\u0e7f' for c in s)


def lua_str(s):
    """same escaping as tools/mapgen/export_roblox.py: UTF-8 kept as is, quotes / backslashes / control chars escaped"""
    if s is None:
        return 'nil'
    out = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return '"' + ''.join(c if ord(c) >= 32 else f'\\{ord(c)}' for c in out) + '"'


def h32(*a):
    return zlib.crc32('|'.join(str(x) for x in a).encode())


def unit(v):
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def left_of(d):
    """driver's left of travel direction d (x east, z south)"""
    return np.array([d[1], -d[0]])


def rect(c, ax, w, d):
    """rectangle centred at c: w along unit ax, d across it"""
    ax = unit(ax)
    pz = np.array([-ax[1], ax[0]])
    c = np.asarray(c, float)
    pts = [c + ax * sx * w / 2 + pz * sz * d / 2 for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return Polygon(pts)


def seg(a, b, r):
    return LineString([tuple(a), tuple(b)]).buffer(r, cap_style=2)


def circ(c, r):
    return Point(float(c[0]), float(c[1])).buffer(r, 12)


# ---- part lists (one entry per Part the Luau builder makes; must match PattayaFurnitureBuilder.luau) -------------------
def parts_of(kind, it):
    """[(name, footprint polygon)] for one item. Footprints are the Parts' ground projections (slightly padded)."""
    if kind == 'signals':
        x, z, ax, az, arm, hx, hz, lit = it
        p, a, h = np.array([x, z]), np.array([ax, az]), np.array([hx, hz])
        head = p + a * arm
        out = [('SignalPole', circ(p, 0.6)), ('SignalArm', seg(p, head, 0.3)), ('SignalHead', rect(head, h, 1.0, 1.5))]
        out += [('SignalLamp', circ(head + unit(h) * 0.55, 0.6))] * 3
        return out
    if kind == 'crossings':
        return [('ZebraStripe', poly) for poly in crossing_bars(it)]
    if kind == 'nameSigns':
        x, z, tx, tz = it[:4]
        p = np.array([x, z])
        return [('NameSignPost', circ(p, 0.45)), ('NameSignBoard', rect(p, (tx, tz), 10.2, 0.5))]
    if kind == 'shelters':
        x, z, nx, nz = it[:4]
        W, D = SHELTER
        S, n = np.array([x, z]), unit((nx, nz))
        right = np.array([-n[1], n[0]])
        L = lambda lx, lz: S + right * lx - n * lz
        pole = L(W / 2 + 1.0, -(D / 2 - 0.4))
        return [('ShelterPad', rect(S, right, W, D)), ('ShelterWall', rect(L(0, D / 2 - 0.3), right, W, 0.4)),
                ('ShelterPost', circ(L(-(W / 2 - 0.5), -(D / 2 - 0.5)), 0.35)), ('ShelterPost', circ(L(W / 2 - 0.5, -(D / 2 - 0.5)), 0.35)),
                ('ShelterRoof', rect(S, right, W + 1, D + 1.2)), ('ShelterBench', rect(L(0, D / 2 - 1.3), right, W - 3, 1.4)),
                ('BusSignPole', circ(pole, 0.35)), ('BusSign', rect(pole, n, 2.4, 0.4))]
    if kind == 'taxis':
        x, z, nx, nz, k = it
        W, D = TAXI
        S, n = np.array([x, z]), unit((nx, nz))
        right = np.array([-n[1], n[0]])
        L = lambda lx, lz: S + right * lx - n * lz
        out = [('TaxiPost', circ(L(-(W / 2 - 0.3), 0), 0.35)), ('TaxiPost', circ(L(W / 2 - 0.3, 0), 0.35)),
               ('TaxiCanopy', rect(S, right, W + 0.6, D + 0.6)), ('TaxiRack', rect(S, right, W - 1, 0.4))]
        if k == 1:
            out += [('TaxiVest', rect(L(-1.2, 0), right, 1.3, 0.4)), ('TaxiVest', rect(L(1.2, 0), right, 1.3, 0.4))]
        out.append(('TaxiSign', rect(L(0, -D / 2), right, 3.2, 0.3)))
        return out
    if kind == 'poles':
        x, z, ax, az, wire = it
        p, a = np.array([x, z]), unit((ax, az))
        out = [('UtilityPole', circ(p, 0.65)), ('PoleArm', rect(p, (-a[1], a[0]), 6.0, 0.5))]
        if wire > 0:
            out.append(('PoleWire', seg(p, p + a * wire, 0.1)))
        return out
    raise KeyError(kind)


SHELTER = (12.0, 5.0)
TAXI = (6.0, 3.0)


def crossing_bars(it):
    x, z, tx, tz, n, bw, gap, depth = it
    t = unit((tx, tz))
    across = np.array([-t[1], t[0]])
    c = np.array([x, z])
    return [rect(c + across * (i - (n + 1) / 2) * (bw + gap), t, depth, bw) for i in range(1, int(n) + 1)]


# ---- inputs -------------------------------------------------------------------------------------------------------------
def load_inputs(cfg, broot):
    I = cfg['inputs']
    rd = lambda *p: os.path.join(broot, *p)
    jl = lambda p: json.load(open(p, encoding='utf-8'))
    wide = jl(rd(I['wide'], 'graph_game.json'))
    central = jl(rd(I['central'], 'graph_game.json'))
    edges = {e['id']: e for e in wide['edges']}
    for e in central['edges']:                      # the wide graph already holds the central edges (base: true)
        if e['id'] not in edges:
            edges[e['id']] = dict(e, base=True)
    city = [edges[k] for k in sorted(edges)]
    cor_path = rd(I['corridor_graph'])
    cor = jl(cor_path)['edges'] if os.path.exists(cor_path) else []
    nodes = {int(k): v for k, v in wide['nodes'].items()}
    for k, v in central['nodes'].items():
        nodes.setdefault(int(k), v)
    central_nodes = {int(k) for k in central['nodes']}
    # buildings
    blds = []
    for ds in (I['central'], I['wide']):
        p = rd(ds, 'buildings_game.json')
        if os.path.exists(p):
            blds += [rect((b['x'], b['z']), (math.cos(math.radians(b['yaw'])), math.sin(math.radians(b['yaw']))), b['w'], b['d'])
                     for b in jl(p)['buildings']]
    # existing props (layout outputs) and the corridor's dressing / lights / signs
    props = []
    layouts = {}
    for ds in (I['central'], I['wide']):
        p = rd(ds, 'layout.json')
        if not os.path.exists(p):
            continue
        L = layouts[ds] = jl(p)
        for q in L.get('lights', []):
            props.append(circ((q['x'], q['z']), 0.5))
            props.append(seg((q['x'], q['z']), (q['x'] + q['dx'] * 7.5, q['z'] + q['dz'] * 7.5), 1.0))
        for q in L.get('palms', []):
            props.append(circ((q['x'], q['z']), 3.0))
        for q in L.get('signs', []):
            props.append(rect((q['x'], q['z']), (-q['nz'], q['nx']), q['w'] + 0.8, 1.2))
        for lm in L.get('landmarks', []):
            props.append(circ((lm['x'], lm['z']), lm.get('span', 20) / 2 + 4))
    crd = rd(I['corridor_roblox'])
    cor_signs = []
    if os.path.isdir(crd):
        man = luau_table.loads(open(os.path.join(crd, 'manifest.luau'), encoding='utf-8').read())
        cor_signs += man.get('signs', [])
        for f in sorted(os.listdir(crd)):
            if not f.startswith('chunk_'):
                continue
            ch = luau_table.loads(open(os.path.join(crd, f), encoding='utf-8').read())
            lt = ch.get('lights', [])
            for i in range(0, len(lt), 4):
                props.append(circ(lt[i:i + 2], 0.5))
                props.append(seg(lt[i:i + 2], (lt[i] + lt[i + 2] * 7.5, lt[i + 1] + lt[i + 3] * 7.5), 1.0))
            pa = ch.get('palms', [])
            for i in range(0, len(pa), 2):
                props.append(circ(pa[i:i + 2], 3.0))
            tr = ch.get('trees', [])
            for i in range(0, len(tr), 3):
                props.append(circ(tr[i:i + 2], 7.0))
            po = ch.get('poles', [])
            for i in range(0, len(po), 5):
                x, z, ax, az, w = po[i:i + 5]
                props.append(circ((x, z), 0.8))
                props.append(rect((x, z), (-az, ax), 6.5, 1.0))
                if w > 0:
                    props.append(seg((x, z), (x + ax * w, z + az * w), 0.4))
            cor_signs += ch.get('roadSigns', [])
            for g in ch.get('gantries', []):
                x, z, dx, dz, span = g[:5]
                pr = np.array([-dz, dx])
                props.append(seg(np.array([x, z]) - pr * span / 2, np.array([x, z]) + pr * span / 2, 1.5))
            b = ch.get('buildings', [])
            for i in range(0, len(b), 8):
                x, z, w, d, hh, yaw = b[i:i + 6]
                blds.append(rect((x, z), (math.cos(math.radians(yaw)), math.sin(math.radians(yaw))), w, d))
    for s in cor_signs:
        x, z, dx, dz = s[:4]
        props.append(rect((x, z), (-dz, dx), 17, 2.0))
    # Studio discs (junctions of every manifest + joint modules) for the slab check
    discs = []
    for sub in ((I['central'], 'roblox'), (I['wide'], 'roblox'), (I['corridor_roblox'],)):
        d = rd(*sub)
        mp = os.path.join(d, 'manifest.luau')
        if os.path.exists(mp):
            m = luau_table.loads(open(mp, encoding='utf-8').read())
            discs += [(j['x'], j['z'], j['r']) for j in m.get('junctions', []) + m.get('seamJunctions', []) if 'x' in j]
        jp = os.path.join(d, 'joints.luau')
        if os.path.exists(jp):
            rows = luau_table.loads(open(jp, encoding='utf-8').read())
            discs += [(rows[i + 1], rows[i + 2], rows[i + 3]) for i in range(0, len(rows), 4)]
    # the BUILT road surface (what PattayaBuilder makes from the fixed chunk modules: slab pieces after road_fix rule D,
    # fill triangles, junction / joint discs) and the chunk line of every edge (merged / hidden / cut flags)
    sys.path.insert(0, os.path.dirname(__file__))
    import road_check as rc
    built_polys, built_edges = [], {}
    for sub in ((I['central'], 'roblox'), (I['wide'], 'roblox'), (I['corridor_roblox'],)):
        d = rd(*sub)
        if not os.path.exists(os.path.join(d, 'manifest.luau')):
            continue
        es, dd, _ = rc.load_dataset(d)
        for e in es:
            built_edges.setdefault(e['id'], e)
            built_polys += rc.slab_rects(e)
        built_polys += [circ((x, z), r) for (x, z, r) in dd.values()]
    pp = rd('dual', 'plan.json')
    plan = jl(pp) if os.path.exists(pp) else {'groups': [], 'roles': {}}
    osm_base = {'central': central.get('osm_base'), 'wide': wide.get('osm_base')}
    return dict(city=city, cor=cor, nodes=nodes, central_nodes=central_nodes, blds=blds, props=props, discs=discs,
                osm_base=osm_base, origin=wide['origin_utm'], built_polys=built_polys, built_edges=built_edges, plan=plan)


def load_osm(cfg, origin):
    raw = json.load(open(os.path.join(ROOT, cfg['raw']), encoding='utf-8'))
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    k = cfg['compression'] / cfg['meters_per_stud']
    out = defaultdict(list)
    for e in sorted(raw['elements'], key=lambda e: (e['type'], e['id'])):
        t = e.get('tags', {})
        if e['type'] == 'node':
            la, lo = e['lat'], e['lon']
        elif 'center' in e:
            la, lo = e['center']['lat'], e['center']['lon']
        else:
            continue
        x, y = tf.transform(lo, la)
        it = {'osm': f"{e['type']} {e['id']}", 'id': e['id'], 'xy': np.array([(x - origin[0]) * k, -(y - origin[1]) * k]), 'tags': t}
        hw, am = t.get('highway'), t.get('amenity')
        if hw == 'traffic_signals':
            out['signals'].append(it)
        if hw == 'crossing' or ('crossing' in t and e['type'] == 'node' and hw != 'traffic_signals'):
            out['crossings'].append(it)
        if hw == 'bus_stop' or t.get('public_transport') == 'platform' or (am == 'shelter' and t.get('shelter_type') == 'public_transport'):
            out['bus'].append(it)
        if am in ('taxi', 'motorcycle_taxi'):
            moto = am == 'motorcycle_taxi' or t.get('motorcycle') == 'yes' or t.get('taxi_vehicle') == 'motorcycle'
            it['moto'] = moto
            out['taxi'].append(it)
    return out, raw.get('osm3s', {}).get('timestamp_osm_base')


# ---- the layer ----------------------------------------------------------------------------------------------------------
def build(cfg, broot):
    D = load_inputs(cfg, broot)
    osm, furn_base = load_osm(cfg, D['origin'])
    M = cfg['kerb_margin_studs']
    PC = cfg['prop_clearance_studs']
    BC = cfg['building_clearance_studs']
    city, cor, nodes = D['city'], D['cor'], D['nodes']
    stats = Counter()
    lines = [LineString(e['pts']) for e in city]
    ltree = STRtree(lines)
    allE = city + cor
    deg = Counter()
    inc = defaultdict(list)
    for i, e in enumerate(city):
        deg[e['a']] += 1; deg[e['b']] += 1
        inc[e['a']].append(i); inc[e['b']].append(i)
    rkeep, jr = defaultdict(float), defaultdict(float)
    nxy = dict(nodes)
    for e in allE:
        for n, p in ((e['a'], e['pts'][0]), (e['b'], e['pts'][-1])):
            rkeep[n] = max(rkeep[n], e['width'] / 2 + e['sidewalk'])
            nxy.setdefault(n, p)
    for e in city:
        for n in (e['a'], e['b']):
            jr[n] = max(jr[n], e['width'] / 2)
    # static obstacles
    keep = [LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'] + M, cap_style=1) for e in allE]
    keep += [circ(nxy[n], rkeep[n] + M) for n in sorted(rkeep)]
    slabs = [LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'], cap_style=1) for e in allE]
    slabs += [circ(nxy[n], rkeep[n]) for n in sorted(rkeep)] + [circ((x, z), r) for x, z, r in D['discs']]
    roads_only = [LineString(e['pts']).buffer(e['width'] / 2, cap_style=2, join_style=1) for e in allE]
    roads_only += [circ((x, z), r) for x, z, r in D['discs']]
    T_keep, T_slab, T_road = STRtree(keep), STRtree(slabs), STRtree(roads_only)
    built = D['built_polys']                       # the built road surface (chunk modules after road_fix)
    T_built = STRtree(built)

    def on_built(g):
        near = [built[k] for k in T_built.query(g)]
        return bool(near) and unary_union(near).contains(g)
    blds, props = D['blds'], D['props']
    T_bld, T_prop = STRtree(blds), STRtree(props)
    placed = defaultdict(list)          # 64-stud grid -> [(poly, item key)]

    def hits(tree, geoms, g):
        return any(geoms[i].intersects(g) for i in tree.query(g))

    def near_placed(g):
        x0, z0, x1, z1 = g.bounds
        for gx in range(int(x0 // 64), int(x1 // 64) + 1):
            for gz in range(int(z0 // 64), int(z1 // 64) + 1):
                yield from placed[(gx, gz)]

    def free(kind, it):
        for name, g in parts_of(kind, it):
            if name in GROUND and hits(T_keep, keep, g):
                return False
            if name not in OVER_ROAD and hits(T_slab, slabs, g):
                return False
            gb = g.buffer(BC)
            if hits(T_bld, blds, gb):
                return False
            if hits(T_prop, props, g.buffer(PC)):
                return False
            gp = g.buffer(1.0)
            if any(q.intersects(gp) for q, _ in near_placed(gp)):
                return False
        return True

    items = defaultdict(list)           # kind -> [(row, meta)]

    def place(kind, it, meta):
        key = (kind, len(items[kind]))
        for _, g in parts_of(kind, it):
            x0, z0, x1, z1 = g.bounds
            for gx in range(int(x0 // 64), int(x1 // 64) + 1):
                for gz in range(int(z0 // 64), int(z1 // 64) + 1):
                    placed[(gx, gz)].append((g, key))
        items[kind].append((it, meta))

    def edge_at(i, s):
        ln = lines[i]
        s = min(max(s, 0.0), ln.length)
        p = ln.interpolate(s)
        a, b = ln.interpolate(max(s - 1.0, 0)), ln.interpolate(min(s + 1.0, ln.length))
        return np.array([p.x, p.y]), unit((b.x - a.x, b.y - a.y))

    def from_node(i, n, dist):
        """point and direction AWAY from node n at `dist` studs along edge i"""
        e = city[i]
        L = lines[i].length
        if e['a'] == n:
            p, t = edge_at(i, dist)
            return p, t
        p, t = edge_at(i, L - dist)
        return p, -t

    def dataset(i=None, n=None):
        if n is not None:
            return 'central' if n in D['central_nodes'] else 'wide'
        return 'central' if city[i].get('base') else 'wide'

    def R(v, k=2):
        return round(float(v), k)

    # ---- 1. traffic signals ----------------------------------------------------------------------------------------
    sc = cfg['signals']
    J = sorted(n for n, d in deg.items() if d >= 3 and n in nxy)
    jpts = [Point(*nxy[n]) for n in J]
    jtree = STRtree(jpts)
    signalised = defaultdict(list)
    midblock = []
    for s in osm['signals']:
        pt = Point(*s['xy'])
        idx = jtree.query_nearest(pt, max_distance=sc['snap_to_junction_studs'], all_matches=False)
        if len(idx):
            signalised[J[int(idx[0])]].append(s['osm'])
            continue
        ei = ltree.query_nearest(pt, max_distance=40, all_matches=False)
        if len(ei) and lines[int(ei[0])].distance(pt) <= city[int(ei[0])]['width'] / 2 + sc['midblock_snap_studs']:
            midblock.append((int(ei[0]), lines[int(ei[0])].project(pt), s['osm']))
        else:
            stats['signal_osm_unsnapped'] += 1
    major = set(sc['rule_major_classes'])
    sig_pts = [Point(*nxy[n]) for n in signalised]
    stree = STRtree(sig_pts) if sig_pts else None
    rule_nodes = []
    for n in J:
        if n in signalised:
            continue
        if sum(1 for i in inc[n] if city[i]['class'] in major) < sc['rule_min_major_edges']:
            continue
        if stree is not None and len(stree.query_nearest(Point(*nxy[n]), max_distance=sc['rule_min_gap_to_signal_studs'], all_matches=False)):
            continue
        rule_nodes.append(n)
    # clusters (union-find over signalised + rule nodes within cluster_studs)
    sn = sorted(set(signalised) | set(rule_nodes))
    par = {n: n for n in sn}

    def find(n):
        while par[n] != n:
            par[n] = par[par[n]]
            n = par[n]
        return n
    for i, a in enumerate(sn):
        for b in sn[i + 1:]:
            if math.dist(nxy[a], nxy[b]) <= sc['cluster_studs']:
                par[find(a)] = find(b)
    clusters = defaultdict(list)
    for n in sn:
        clusters[find(n)].append(n)
    approaches = []                    # (edge index, node, cluster key) for the crossing rule
    for ck in sorted(clusters):
        cn = set(clusters[ck])
        src = 'osm' if any(n in signalised for n in cn) else 'rule'
        cen = np.mean([nxy[n] for n in cn], axis=0)
        appr = []
        for n in sorted(cn):
            for i in inc[n]:
                e = city[i]
                other = e['b'] if e['a'] == n else e['a']
                if other in cn and lines[i].length < 2 * sc['cluster_studs']:
                    continue                                   # inside the junction
                if e['oneway'] and e['b'] != n:
                    continue                                   # one-way leaving the junction: no inbound traffic
                p, away = from_node(i, n, rkeep[n] + 1)
                appr.append((math.atan2(*(p - cen)[::-1]), i, n))
        appr.sort()
        stats[f'signal_junctions_{src}'] += 1
        for k, (_, i, n) in enumerate(appr):
            e = city[i]
            ok = False
            for ds in range(0, 84, 4):
                p, away = from_node(i, n, rkeep[n] + sc['setback_studs'] + ds)
                if math.dist(p, nxy[n]) > lines[i].length:
                    break
                d = -away                                       # inbound travel direction
                lf = left_of(d)
                for extra in (0.0, 1.5, 3.0, 4.5, 6.0):
                    off = e['width'] / 2 + e['sidewalk'] + M + 0.6 + extra
                    pos = p + lf * off
                    arm = min(off - e['width'] / 2 + min(e['width'] / 4, 7.0), sc['arm_max_studs'])
                    it = (R(pos[0]), R(pos[1]), R(-lf[0], 3), R(-lf[1], 3), R(arm, 1), R(-d[0], 3), R(-d[1], 3), 1 if k % 2 == 0 else 3)
                    if free('signals', it):
                        place('signals', it, {'src': src, 'osm': signalised.get(n, []), 'node': n, 'edge': e['id'], 'ds': dataset(n=n)})
                        approaches.append((i, n))
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                stats['signal_mast_blocked'] += 1
    # mid-block signals: one mast per direction, a little before the stop line
    mb_done = []
    mid_cross = []
    for i, s0, src in sorted(midblock, key=lambda m: (m[0], m[1])):
        if any(j == i and abs(s0 - t) < 20 for j, t in mb_done):
            continue
        mb_done.append((i, s0))
        e = city[i]
        mid_cross.append((i, s0, src))
        for sgn in ((1,) if e['oneway'] else (1, -1)):
            ok = False
            for ds in range(0, 40, 4):
                p, t = edge_at(i, s0 - sgn * (cfg['crossings']['depth_studs'] / 2 + 3 + ds))
                d = t * sgn
                lf = left_of(d)
                for extra in (0.0, 1.5, 3.0, 4.5, 6.0):
                    off = e['width'] / 2 + e['sidewalk'] + M + 0.6 + extra
                    pos = p + lf * off
                    arm = min(off - e['width'] / 2 + min(e['width'] / 4, 7.0), sc['arm_max_studs'])
                    it = (R(pos[0]), R(pos[1]), R(-lf[0], 3), R(-lf[1], 3), R(arm, 1), R(-d[0], 3), R(-d[1], 3), 1 if sgn > 0 else 3)
                    if free('signals', it):
                        place('signals', it, {'src': 'osm_midblock', 'osm': [src], 'edge': e['id'], 'ds': dataset(i=i)})
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                stats['signal_mast_blocked'] += 1
        stats['signal_midblock'] += 1

    # ---- 2. zebra crossings -----------------------------------------------------------------------------------------
    cc = cfg['crossings']
    dep, bw, gap, inset = cc['depth_studs'], cc['bar_width_studs'], cc['bar_gap_studs'], cc['edge_inset_studs']
    cands = []                         # (edge, s, src)
    for c in osm['crossings']:
        t = c['tags']
        if any(t.get(k) in v for k, v in cc['skip_tags'].items()):
            stats['crossing_osm_skipped_tag'] += 1
            continue
        pt = Point(*c['xy'])
        ei = ltree.query_nearest(pt, max_distance=40, all_matches=False)
        if not len(ei) or lines[int(ei[0])].distance(pt) > city[int(ei[0])]['width'] / 2 + cc['snap_studs']:
            stats['crossing_osm_off_road'] += 1
            continue
        i = int(ei[0])
        cands.append((i, lines[i].project(pt), c['osm']))
    for i, s0, src in mid_cross:
        if not any(j == i and abs(s - s0) < 20 for j, s, _ in cands):
            cands.append((i, s0, 'rule_midblock_signal ' + src))
    if cc['rule_at_signal_approaches']:
        for i, n in sorted(set(approaches)):
            e = city[i]
            dist = jr[n] + dep / 2 + 2
            s0 = dist if e['a'] == n else lines[i].length - dist
            if any(j == i and abs(s - s0) < cc['rule_skip_if_osm_within_studs'] for j, s, _ in cands):
                continue
            cands.append((i, s0, f'rule_signal_approach node {n}'))
    cands.sort(key=lambda c: (c[0], c[1]))
    taken, centres = [], []
    BE, plan = D['built_edges'], D['plan']
    kept_of = {}                                   # edge id -> chunk lines of the kept (merged) edges of its dual group
    for g in plan.get('groups', []):
        ks = [BE[k] for k in g['kept'] if k in BE and not BE[k].get('hidden')]
        for m in g['kept'] + g['hidden']:
            kept_of[m] = ks
    for i, s0, src in cands:
        e = city[i]
        L = lines[i].length
        lo = (jr[e['a']] if deg[e['a']] >= 3 else 0) + dep / 2 + 1
        hi = L - (jr[e['b']] if deg[e['b']] >= 3 else 0) - dep / 2 - 1
        if hi < lo:
            stats['crossing_edge_too_short'] += 1
            continue
        s = min(max(s0, lo), hi)
        if any(j == i and abs(s - t) < cc['merge_studs'] for j, t in taken):
            stats['crossing_merged'] += 1
            continue
        p, t = edge_at(i, s)
        width = e['width']
        be = BE.get(e['id'])
        changed = be is not None and (be.get('merged') or be.get('hidden') or be.get('cutA') or be.get('cutB')
                                      or be.get('hide') or be.get('fill'))
        if changed and (be.get('merged') or be.get('hidden') or kept_of.get(e['id'])):
            # dual carriageway: centre the crossing on the merged (kept) centreline of the group, spanning that slab
            best = None
            for k in ([be] if be.get('merged') else []) + kept_of.get(e['id'], []):
                kl = LineString(k['pts'])
                d_ = kl.distance(Point(*p))
                if d_ <= k['width'] / 2 + width / 2 and (best is None or d_ < best[0]):
                    best = (d_, kl, k)
            if best is not None:
                _, kl, k = best
                s2 = kl.project(Point(*p))
                q, a_, b_ = kl.interpolate(s2), kl.interpolate(max(s2 - 1.0, 0)), kl.interpolate(min(s2 + 1.0, kl.length))
                p, t, width = np.array([q.x, q.y]), unit((b_.x - a_.x, b_.y - a_.y)), k['width']
                stats['crossing_on_merged_slab'] += 1
            elif be.get('hidden'):
                stats['crossing_hidden_edge_no_kept_twin'] += 1
                continue
        if any(np.hypot(p[0] - x, p[1] - z) < cc['merge_studs'] for x, z in centres):
            stats['crossing_merged'] += 1                  # both carriageways of a merged road had one here
            continue
        n = int((width - 2 * inset + gap) // (bw + gap))
        ok = False
        while n >= 3:
            it = (R(p[0]), R(p[1]), R(t[0], 3), R(t[1], 3), n, bw, gap, dep)
            bars = crossing_bars(it)
            inside = all(any(roads_only[k].contains(b) for k in T_road.query(b)) or unary_union([roads_only[k] for k in T_road.query(b)]).contains(b)
                         for b in bars) and all(on_built(b) for b in bars)
            if inside:
                ok = True
                break
            n -= 2
        if not ok:
            stats['crossing_not_on_slab'] += 1
            continue
        taken.append((i, s))
        centres.append((p[0], p[1]))
        place('crossings', it, {'src': src, 'edge': e['id'], 'ds': dataset(i=i)})

    # ---- 3. bus shelters, taxi stands -------------------------------------------------------------------------------
    def kerb_item(kind, osm_it, depth, snap, row):
        pt = Point(*osm_it['xy'])
        ei = ltree.query_nearest(pt, max_distance=snap, all_matches=False)
        if not len(ei):
            stats[f'{kind}_unsnapped'] += 1
            return False
        i = int(ei[0])
        e = city[i]
        s0 = lines[i].project(pt)
        p0, t0 = edge_at(i, s0)
        lf = left_of(t0)
        rel = osm_it['xy'] - p0
        side = 1 if (abs(rel @ lf) < e['width'] / 2 or rel @ lf > 0) else -1   # on the road way: a->b driver's left
        for ds in [0] + [k * sg for k in range(4, 44, 4) for sg in (1, -1)]:
            p, t = edge_at(i, s0 + ds)
            sv = left_of(t) * side
            for extra in (0, 2, 4, 6):
                pos = p + sv * (e['width'] / 2 + e['sidewalk'] + M + depth / 2 + 0.7 + extra)
                it = row(pos, -sv)
                if free(kind, it):
                    place(kind, it, {'src': osm_it['osm'], 'edge': e['id'], 'ds': dataset(i=i), 'shift': ds})
                    return True
        stats[f'{kind}_blocked'] += 1
        return False

    seen = []
    for b in osm['bus']:
        if any(np.linalg.norm(b['xy'] - q) < 20 for q in seen):
            stats['bus_duplicate'] += 1
            continue
        seen.append(b['xy'])
        nm = b['tags'].get('name')
        label = nm if THAI(nm) else ''               # only a real Thai OSM stop name (no operators / brands)
        kerb_item('shelters', b, SHELTER[1] + 1.2, cfg['bus']['snap_studs'],
                  lambda pos, n, label=label: (R(pos[0]), R(pos[1]), R(n[0], 3), R(n[1], 3), label))
    seen = []
    for tx in osm['taxi']:
        if any(np.linalg.norm(tx['xy'] - q) < 12 for q in seen):
            stats['taxi_duplicate'] += 1
            continue
        seen.append(tx['xy'])
        k = 1 if tx['moto'] else 2
        kerb_item('taxis', tx, TAXI[1] + 0.6, cfg['taxi']['snap_studs'],
                  lambda pos, n, k=k: (R(pos[0]), R(pos[1]), R(n[0], 3), R(n[1], 3), k))

    # ---- 4. road name signs ------------------------------------------------------------------------------------------
    ns = cfg['name_signs']
    key_of = lambda e: e.get('name') or e.get('name_en')
    sign_at = defaultdict(list)
    for n in J:
        es = [i for i in inc[n] if key_of(city[i])]
        keys = sorted({key_of(city[i]) for i in es})
        if len(keys) < ns['min_distinct_names']:
            continue
        if ns['require_main_tier'] and not any(city[i]['tier'] in MAIN_TIERS for i in inc[n]):
            continue
        for key in keys:
            if any(math.dist(q, nxy[n]) < 60 for q in sign_at[key]):
                stats['name_sign_same_name_nearby'] += 1
                continue
            ok = False
            for i in sorted((i for i in es if key_of(city[i]) == key), key=lambda i: city[i]['id']):
                e = city[i]
                th = e.get('name') if THAI(e.get('name')) else None
                en = e.get('name_en') or (e.get('name') if not THAI(e.get('name')) else None)
                for dist in np.arange(rkeep[n] + M + 5.5, rkeep[n] + M + 40, 3.0):
                    if dist > lines[i].length - 6:
                        break
                    p, away = from_node(i, n, dist)
                    for side in (1, -1):
                        pos = p + left_of(away) * side * (e['width'] / 2 + e['sidewalk'] + M + 0.6)
                        it = (R(pos[0]), R(pos[1]), R(away[0], 3), R(away[1], 3), th or '', en or '')
                        if free('nameSigns', it):
                            place('nameSigns', it, {'src': f'junction {n}', 'way': e['way'], 'edge': e['id'], 'ds': dataset(n=n)})
                            sign_at[key].append(nxy[n])
                            ok = True
                            break
                    if ok:
                        break
                if ok:
                    break
            if not ok:
                stats['name_sign_blocked'] += 1

    # ---- 5. utility poles along sois (budget permitting) -------------------------------------------------------------
    pc, bud = cfg['poles'], cfg['budget']
    count_parts = lambda: sum(len(parts_of(k, it)) for k, lst in items.items() for it, _ in lst)
    used = count_parts()
    cen = np.mean([nxy[n] for n in D['central_nodes'] if n in nxy], axis=0)
    soi = [i for i, e in enumerate(city) if e['class'] in pc['classes'] and e['tier'] == 'soi' and not e.get('coastal')
           and lines[i].length >= pc['min_edge_length_studs']]
    soi.sort(key=lambda i: (0 if city[i].get('base') else 1, round(float(np.linalg.norm(np.array(lines[i].interpolate(0.5, normalized=True).coords[0]) - cen))), city[i]['id']))
    runs = []
    step = pc['step_studs']
    for i in soi:
        if used >= bud['pole_target_total_parts']:
            stats['pole_edges_skipped_budget'] += 1
            continue
        e = city[i]
        run = []
        s = step / 2
        while s < lines[i].length - step / 3:
            p, t = edge_at(i, s)
            pos = p + left_of(t) * (e['width'] / 2 + e['sidewalk'] + M + 0.7)
            it = (R(pos[0], 1), R(pos[1], 1), R(t[0], 3), R(t[1], 3), 0.0)
            if free('poles', it):
                place('poles', it, {'src': 'rule', 'edge': e['id'], 'ds': dataset(i=i), 'run': len(runs)})
                run.append(len(items['poles']) - 1)
                used += 3
            else:
                stats['pole_blocked'] += 1
                run.append(None)
            s += step
        runs.append(run)

    # ---- chunks, budget, wires ---------------------------------------------------------------------------------------
    C = cfg['chunk_size_studs']
    cid = lambda x, z: f'f{int(math.floor(x / C))}_{int(math.floor(z / C))}'
    alive = {k: [True] * len(v) for k, v in items.items()}

    def wire_of(pi):
        """wire from pole pi to the next living pole of its run (0 if none / too far / not clear)"""
        it, meta = items['poles'][pi]
        run = runs[meta['run']]
        k = run.index(pi)
        nxt = run[k + 1] if k + 1 < len(run) else None
        if nxt is None or not alive['poles'][nxt]:
            return None
        a, b = np.array(it[:2]), np.array(items['poles'][nxt][0][:2])
        L = float(np.linalg.norm(b - a))
        if L <= 0 or L > step * pc['max_wire_factor']:
            return None
        w = seg(a, b, 0.1)
        if hits(T_slab, slabs, w) or hits(T_bld, blds, w.buffer(BC)) or hits(T_prop, props, w.buffer(PC)) or                 any(key[0] != 'poles' and q.intersects(w) for q, key in near_placed(w)):
            stats['wire_blocked'] += 1
            return None
        d = (b - a) / L
        return (it[0], it[1], R(d[0], 3), R(d[1], 3), R(L, 1))

    def finalize():
        rows = defaultdict(lambda: defaultdict(list))
        for kind, lst in items.items():
            for j, (it, meta) in enumerate(lst):
                if not alive[kind][j]:
                    continue
                if kind == 'poles':
                    w = wire_of(j)
                    it = w if w is not None else (it[0], it[1], it[2], it[3], 0.0)
                rows[cid(it[0], it[1])][kind].append((it, meta))
        return rows
    rows = finalize()
    cap = bud['max_parts_per_chunk']
    chunk_parts = lambda ch: sum(len(parts_of(k, it)) for k, lst in ch.items() for it, _ in lst)
    for _ in range(6):
        over = [c for c in rows if chunk_parts(rows[c]) > cap]
        if not over:
            break
        for c in over:
            for kind in ('poles', 'nameSigns'):
                if chunk_parts(rows[c]) <= cap:
                    break
                lst = [j for j, (it, m) in enumerate(items[kind]) if alive[kind][j] and cid(it[0], it[1]) == c]
                for j in lst[1::2]:
                    alive[kind][j] = False
                    stats[f'{kind}_thinned_for_chunk_cap'] += 1
        rows = finalize()
    total = sum(chunk_parts(ch) for ch in rows.values())
    assert total <= bud['max_total_parts'], f'furniture {total} parts > budget'
    assert all(chunk_parts(ch) <= cap for ch in rows.values()), 'chunk over cap'

    # ---- export-time checks (shapely, asserted) ------------------------------------------------------------------------
    chk = Counter()
    chk_ex = []
    allparts = []                       # (chunk, kind, j, name, poly)
    for c, ch in rows.items():
        for kind, lst in ch.items():
            for j, (it, _) in enumerate(lst):
                for name, g in parts_of(kind, it):
                    allparts.append((c, kind, j, name, g, it))
    slab_tight = [LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'], cap_style=1) for e in allE] + \
                 [circ((x, z), r) for x, z, r in D['discs']]
    T_tight = STRtree(slab_tight)
    fpolys = [(c, kind, j, g, name) for c, kind, j, name, g, it in allparts if kind != 'crossings']
    T_f = STRtree([f[3] for f in fpolys])
    for c, kind, j, name, g, it in allparts:
        if kind == 'crossings':
            near = [roads_only[k] for k in T_road.query(g)]
            if not near or not unary_union(near).contains(g):
                chk['crossing_bar_off_slab'] += 1
            if not on_built(g):                      # the road PattayaBuilder actually builds (road_fix rule D)
                chk['crossing_bar_off_built_road'] += 1
            continue
        if name not in OVER_ROAD and (hits(T_tight, slab_tight, g) or hits(T_slab, slabs, g)):
            chk['on_road_slab_sidewalk_or_disc'] += 1
        if name not in OVER_ROAD and hits(T_built, built, g):
            chk['on_built_road'] += 1
        if name in GROUND and hits(T_keep, keep, g):
            chk['ground_part_inside_kerb_margin'] += 1
        if hits(T_bld, blds, g):
            chk['inside_building'] += 1
        if hits(T_prop, props, g):
            chk['on_existing_prop'] += 1
        for k in T_f.query(g):
            c2, kind2, j2, g2, name2 = fpolys[k]
            if kind == kind2 == 'poles' and 'PoleWire' in (name, name2):
                continue                                # a wire ends at the next pole of its run
            if (c2, kind2, j2) != (c, kind, j) and g.intersects(g2):
                chk['furniture_overlap'] += 1
                chk_ex.append((kind, name, kind2, it[:2]))
                break
    assert CROSS_THICK <= 0.1 and CROSS_Y + CROSS_THICK / 2 <= ROAD_TOP + 0.1
    bad = {k: v for k, v in chk.items() if v}
    assert not bad, f'furniture export check failed: {bad} {Counter((a, b, c) for a, b, c, _ in chk_ex)} {chk_ex[:5]}'
    stats.update({'check_' + k: 0 for k in ('on_road_slab_sidewalk_or_disc', 'ground_part_inside_kerb_margin', 'inside_building',
                                             'on_existing_prop', 'furniture_overlap', 'crossing_bar_off_slab',
                                             'crossing_bar_off_built_road', 'on_built_road')})
    return dict(rows=rows, stats=stats, total=total, D=D, furn_base=furn_base, cen=cen, chunk_parts=chunk_parts)


# ---- output ---------------------------------------------------------------------------------------------------------------
KINDS = ('signals', 'crossings', 'nameSigns', 'shelters', 'taxis', 'poles')
FLAT = {'signals': '{x, z, ax, az, arm, hx, hz, lit}: pole base, arm direction (unit, into the road), arm length, head facing (towards the oncoming drivers), lit lamp (1 red, 3 green)',
        'crossings': '{x, z, tx, tz, n, barW, gap, depth}: centre on the centreline, road tangent, bar count, bar width, gap, bar length along the road',
        'taxis': '{x, z, nx, nz, kind}: centre, unit vector towards the road, 1 = motorbike taxi (WIN), 2 = taxi',
        'poles': '{x, z, ax, az, wire}: base, unit direction to the next pole, wire length (0 = none)'}
TABLES = {'nameSigns': '{{x, z, tx, tz, nameTh, nameEn}}: post, tangent of the named road (board plane), OSM name / name:en ("" = not tagged)',
          'shelters': '{{x, z, nx, nz, label}}: pad centre, unit vector towards the road, Thai OSM stop name or ""'}


def fmt(v):
    if isinstance(v, str):
        return lua_str(v)
    if isinstance(v, float):
        s = f'{v:.3f}'.rstrip('0').rstrip('.')
        return s if s not in ('-0', '') else '0'
    return str(v)


def write(cfg, res, broot):
    out = os.path.join(broot, cfg['out_dir'])
    rdir = os.path.join(out, 'roblox')
    os.makedirs(rdir, exist_ok=True)
    for f in os.listdir(rdir):
        if f.startswith('chunk_f') or f == 'manifest.luau':
            os.remove(os.path.join(rdir, f))
    rows, D = res['rows'], res['D']
    attr = cfg['attribution']
    base = f"OSM nodes {res['furn_base']}, road graph {D['osm_base']['wide']}"
    order = sorted(rows, key=lambda c: (np.hypot((int(c[1:].split('_')[0]) + 0.5) * cfg['chunk_size_studs'] - res['cen'][0],
                                                 (int(c.split('_')[1]) + 0.5) * cfg['chunk_size_studs'] - res['cen'][1]), c))
    counts = defaultdict(Counter)
    sizes = []
    for c in order:
        ch = rows[c]
        L = [f'-- generated by tools/mapgen/furniture.py from {cfg["raw"]} + the road graph ({attr}; {base}) and stated rules; do not edit',
             f'return {{ id = "{c}",']
        for kind in KINDS:
            lst = [it for it, _ in ch.get(kind, [])]
            for it, m in ch.get(kind, []):
                counts[m['ds']][kind] += 1
                counts[m['ds']]['parts'] += len(parts_of(kind, it))
            if kind in FLAT:
                L.append(f'  -- {kind} {FLAT[kind]}')
                L.append(f'  {kind} = {{' + ','.join(fmt(v) for it in lst for v in it) + '},')
            else:
                L.append(f'  -- {kind} {TABLES[kind]}')
                L.append(f'  {kind} = {{' + ','.join('{' + ','.join(fmt(v) for v in it) + '}' for it in lst) + '},')
        L.append(f'  parts = {res["chunk_parts"](ch)},')
        L.append('}')
        src = '\n'.join(L) + '\n'
        open(os.path.join(rdir, f'chunk_{c}.luau'), 'w', encoding='utf-8', newline='\n').write(src)
        sizes.append(len(src.encode('utf-8')))
    B = cfg['budget']['batch_size_chunks']
    batches = {f'f{k // B + 1}': order[k:k + B] for k in range(0, len(order), B)}
    border = sorted(batches, key=lambda b: int(b[1:]))
    tot = Counter()
    for ds in counts.values():
        tot.update(ds)
    man = ['-- generated by tools/mapgen/furniture.py; do not edit. Street furniture layer (traffic lights, zebra crossings,',
           '-- road name signs, bus shelters, taxi stands, utility poles). Built by ServerStorage.PattayaFurnitureBuilder.',
           'return {',
           '  name = "furniture",',
           f'  attribution = {lua_str(attr)},',
           f'  osmBase = {lua_str(res["furn_base"])},',
           f'  graphOsmBase = {lua_str(D["osm_base"]["wide"])},',
           f'  source = {lua_str(cfg["raw"] + " (OSM nodes) + build/pattaya_wide, build/central_pattaya road graph")},',
           f'  roadTop = {ROAD_TOP}, groundY = {GROUND_Y}, chunkSize = {cfg["chunk_size_studs"]},',
           '  onRoadParts = {"ZebraStripe"}, -- the only furniture parts on the slab (the leader\'s probe skips them)',
           '  chunks = {' + ','.join(lua_str(c) for c in order) + '},',
           '  batchOrder = {' + ','.join(lua_str(b) for b in border) + '},',
           '  batches = {']
    for b in border:
        man.append(f'    {b} = {{' + ','.join(lua_str(c) for c in batches[b]) + '},')
    man.append('  },')
    man.append('  counts = {' + ', '.join(f'{k} = {tot[k]}' for k in KINDS) + f', parts = {res["total"]}' + ' },')
    man.append('}')
    open(os.path.join(rdir, 'manifest.luau'), 'w', encoding='utf-8', newline='\n').write('\n'.join(man) + '\n')
    js = {'attribution': attr, 'osm_base': res['furn_base'], 'graph_osm_base': D['osm_base'], 'total_parts': res['total'],
          'counts': {ds: dict(c) for ds, c in sorted(counts.items())}, 'stats': dict(sorted(res['stats'].items())),
          'chunks': {c: {k: [{'row': list(it), **m} for it, m in rows[c].get(k, [])] for k in KINDS} for c in order},
          'batches': batches}
    json.dump(js, open(os.path.join(out, 'furniture.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=str)
    return dict(order=order, batches=batches, counts=counts, tot=tot, sizes=sizes, out=out)


def check_image(cfg, res, broot, path):
    from PIL import Image, ImageDraw
    D = res['D']
    central = [e for e in D['city'] if e.get('base')]
    xs = [p[0] for e in central for p in e['pts']]; zs = [p[1] for e in central for p in e['pts']]
    full = (min(xs) - 100, min(zs) - 100, max(xs) + 100, max(zs) + 100)
    cx, cz = res['cen']
    crops = [full, (cx - 450, cz - 450, cx + 450, cz + 450)]
    # a busy signalised junction: the chunk with the most signals
    sig = [(it[0], it[1]) for ch in res['rows'].values() for it, m in ch.get('signals', []) if m['ds'] == 'central']
    if sig:
        best = max(sig, key=lambda p: sum(1 for q in sig if math.dist(p, q) < 150))
        crops.append((best[0] - 160, best[1] - 160, best[0] + 160, best[1] + 160))
    col = {'signals': (220, 30, 30), 'crossings': (255, 255, 255), 'nameSigns': (20, 80, 200), 'shelters': (250, 160, 0),
           'taxis': (255, 110, 0), 'poles': (0, 0, 0)}
    for k, (x0, z0, x1, z1) in enumerate(crops):
        s = (3600 if k == 0 else 1800) / (x1 - x0)
        im = Image.new('RGB', (int((x1 - x0) * s) + 1, int((z1 - z0) * s) + 1), (226, 222, 210))
        d = ImageDraw.Draw(im)
        tr = lambda p: ((p[0] - x0) * s, (p[1] - z0) * s)

        def poly(g, fill, outline=None):
            if g.is_empty:
                return
            for q in (g.geoms if hasattr(g, 'geoms') else [g]):
                if q.geom_type == 'Polygon' and q.bounds[2] >= x0 and q.bounds[0] <= x1 and q.bounds[3] >= z0 and q.bounds[1] <= z1:
                    d.polygon([tr(p) for p in q.exterior.coords], fill=fill, outline=outline)
        for e in D['city'] + D['cor']:
            ln = LineString(e['pts'])
            b = ln.bounds
            if b[2] < x0 or b[0] > x1 or b[3] < z0 or b[1] > z1:
                continue
            if e['sidewalk']:
                poly(ln.buffer(e['width'] / 2 + e['sidewalk'], cap_style=2), (175, 172, 165))
        for e in D['city'] + D['cor']:
            ln = LineString(e['pts'])
            b = ln.bounds
            if b[2] < x0 or b[0] > x1 or b[3] < z0 or b[1] > z1:
                continue
            poly(ln.buffer(e['width'] / 2, cap_style=2), (70, 72, 80))
        for x, z, r in D['discs']:
            if x0 <= x <= x1 and z0 <= z <= z1:
                poly(circ((x, z), r), (70, 72, 80))
        for g in D['blds']:
            poly(g, (205, 190, 160), (120, 110, 90))
        for g in D['props']:
            poly(g, (40, 150, 60))
        for ch in res['rows'].values():
            for kind in KINDS:
                for it, _ in ch.get(kind, []):
                    for name, g in parts_of(kind, it):
                        poly(g, col[kind], None if kind == 'crossings' else (0, 0, 0))
        d.text((10, 10), 'furniture check: red signals, white crossings, blue name signs, amber shelters, orange taxi, black poles; '
                         'green existing props; grey road / sidewalk', fill=(0, 0, 0))
        im.save(path if k == 0 else path.replace('.png', f'_{k}.png'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--build-root', default=os.path.join(ROOT, 'build'))
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding='utf-8'))
    res = build(cfg, a.build_root)
    w = write(cfg, res, a.build_root)
    check_image(cfg, res, a.build_root, os.path.join(w['out'], 'furniture_check.png'))
    print(f"furniture: {len(w['order'])} chunks, {res['total']} parts, {len(w['batches'])} batches (<= {cfg['budget']['batch_size_chunks']} chunks), "
          f"largest chunk {max(res['chunk_parts'](c) for c in res['rows'].values())} parts, largest module {max(w['sizes']) / 1024:.1f} KB")
    for ds in sorted(w['counts']):
        print(f'  {ds}: ' + ', '.join(f'{k} {w["counts"][ds][k]}' for k in KINDS + ('parts',)))
    print('  total: ' + ', '.join(f'{k} {w["tot"][k]}' for k in KINDS + ('parts',)))
    print('  stats: ' + ', '.join(f'{k} {v}' for k, v in sorted(res['stats'].items())))


if __name__ == '__main__':
    main()
