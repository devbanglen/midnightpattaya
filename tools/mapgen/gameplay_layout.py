"""Stage 6 - gameplay layer on top of the graph: the first loop race, the spawn/start grid, street props, landmarks.

  .venv\\Scripts\\python tools\\mapgen\\gameplay_layout.py tools\\mapgen\\config\\central_pattaya.json

Writes build/<name>/layout.json and layout_check.png. Everything is derived from graph_game.json (road names + OSM
ids), so it follows the data when the config changes.
"""
import heapq, json, math, os, sys
from collections import Counter, defaultdict
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely import affinity
from shapely.strtree import STRtree
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def plen(p):
    p = np.asarray(p)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    L = cfg['layout']
    g = json.load(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), encoding='utf-8'))
    edges = g['edges']
    adj = defaultdict(list)
    for i, e in enumerate(edges):
        adj[e['a']].append((i, e['b']))
        adj[e['b']].append((i, e['a']))

    def named(e, names):
        return (e['name_en'] or '') in names or (e['name'] or '') in names

    def nodes_of(names):
        return {n for e in edges if named(e, names) for n in (e['a'], e['b'])}

    def shortest(src, dst, prefer):
        """Dijkstra; edges on the preferred road(s) cost their length, others 25x (allowed for tiny gaps)."""
        dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == dst:
                break
            if d > dist[n]:
                continue
            for i, m in adj[n]:
                e = edges[i]
                c = plen(e['pts']) * (1 if named(e, prefer) else 25)
                if d + c < dist.get(m, 1e18):
                    dist[m] = d + c; prev[m] = (n, i); heapq.heappush(pq, (d + c, m))
        path, n = [], dst
        while n != src:
            p, i = prev[n]
            path.append((i, n)); n = p
        return list(reversed(path))

    # --- loop race: corners = junctions of consecutive legs ----------------------------------------------------
    legs = L['race_legs']                                   # [{"names": [...]}, ...] in driving order, closed loop
    corners = []
    for k in range(len(legs)):
        a, b = nodes_of(legs[k]['names']), nodes_of(legs[(k + 1) % len(legs)]['names'])
        common = a & b
        if not common:
            sys.exit(f'race legs {k} and {k + 1} do not meet: {legs[k]["names"]} / {legs[(k + 1) % len(legs)]["names"]}')
        # several shared nodes (dual carriageways, offsets): take the one nearest the previous corner, else any
        pick = sorted(common, key=lambda n: (np.linalg.norm(np.array(g['nodes'][str(n)]) - np.array(g['nodes'][str(corners[-1])]))
                                             if corners else 0))[0]
        corners.append(pick)
    route_pts, route_edges = [], []
    for k in range(len(corners)):
        src, dst = corners[k - 1], corners[k]                # leg k runs from corner k-1 to corner k
        for i, n in shortest(src, dst, legs[k]['names']):
            e = edges[i]
            pts = e['pts'] if e['b'] == n else list(reversed(e['pts']))
            route_pts.extend(pts if not route_pts else pts[1:])
            route_edges.append(e['id'])
    line = LineString(route_pts)
    total = line.length
    n_cp = max(4, int(total // L['checkpoint_spacing_studs']))
    # gates must not sit on a junction: a gate is judged by crossing its plane, and a car turning in from the crossing
    # road can already be past that plane (found in test: gate 1 on the Klang/Beach junction never counted a lap)
    jpts = [Point(g['nodes'][str(n)]) for n, d in Counter([e['a'] for e in edges] + [e['b'] for e in edges]).items() if d >= 3]
    jtree = STRtree(jpts)
    clear = L.get('gate_junction_clearance_studs', 35)
    gate_s = []
    for j in range(n_cp):
        s = j * total / n_cp
        for _ in range(20):
            p = line.interpolate(s)
            if jpts[jtree.nearest(p)].distance(p) >= clear:
                break
            s = (s + 10) % total
        gate_s.append(s)
    checkpoints = []
    for j, s in enumerate(gate_s):
        p = line.interpolate(s); q = line.interpolate(min(s + 4, total))
        checkpoints.append({'x': round(p.x, 2), 'z': round(p.y, 2), 'dx': round(q.x - p.x, 3), 'dz': round(q.y - p.y, 3)})
    # width at each checkpoint = width of the route edge that contains its arc-length position (at a junction the
    # nearest edge may be the crossing road)
    widths = {e['id']: e['width'] for e in edges}
    plen_by = {e['id']: plen(e['pts']) for e in edges}
    bounds, acc = [], 0.0
    for eid in route_edges:
        bounds.append((acc, acc + plen_by[eid], widths[eid])); acc += plen_by[eid]
    for j, c in enumerate(checkpoints):
        s = gate_s[j] + 1.0                              # just past the gate, inside the edge it leads into
        w = next((w for a, b, w in bounds if a <= s < b), bounds[-1][2])
        c['w'] = round(w + 6, 1)

    # start grid: just after checkpoint 0, two columns, cars facing along the route
    s0 = checkpoints[0]
    fwd = np.array([s0['dx'], s0['dz']]); fwd /= np.linalg.norm(fwd)
    right = np.array([-fwd[1], fwd[0]])
    grid = []
    for k in range(L['grid_slots']):
        row, col = divmod(k, 2)
        p = np.array([s0['x'], s0['z']]) - fwd * (14 + row * 24) + right * (-1 if col == 0 else 1) * min(c['w'] for c in checkpoints[:1]) * 0.22
        grid.append({'x': round(p[0], 2), 'z': round(p[1], 2), 'dx': round(fwd[0], 3), 'dz': round(fwd[1], 3)})
    spawn = np.array([s0['x'], s0['z']]) - fwd * (14 + (L['grid_slots'] // 2) * 24 + 30)

    # --- props: palms on the sea side of coastal roads, street lights along main roads -------------------------
    bpath = os.path.join(ROOT, 'build', cfg['name'], 'buildings_game.json')
    bpolys = []
    for b in json.load(open(bpath, encoding='utf-8'))['buildings']:
        r = Polygon([(-b['w'] / 2, -b['d'] / 2), (b['w'] / 2, -b['d'] / 2), (b['w'] / 2, b['d'] / 2), (-b['w'] / 2, b['d'] / 2)])
        bpolys.append(affinity.translate(affinity.rotate(r, b['yaw']), b['x'], b['z']))
    btree = STRtree(bpolys)
    road_polys = [LineString(e['pts']).buffer(e['width'] / 2 + 1.5) for e in edges]
    rtree = STRtree(road_polys)
    sea_side_x = -1                                          # Pattaya: the sea is west of Beach Road

    def free(p, r):
        c = Point(p).buffer(r)
        return not any(bpolys[i].intersects(c) for i in btree.query(c)) and not any(road_polys[i].intersects(c) for i in rtree.query(c))

    palms, lights = [], []
    for e in edges:
        ln = LineString(e['pts'])
        if ln.length < 30:
            continue
        if e['coastal']:
            step, kind = L['palm_spacing_studs'], 'palm'
        elif e['tier'] in ('main', 'express'):
            step, kind = L['light_spacing_studs'], 'light'
        else:
            continue
        # sidewalk centre; roads without sidewalks get the pole just outside their own clearance buffer
        off = e['width'] / 2 + (e['sidewalk'] / 2 if e['sidewalk'] >= 4 else 4)
        s = step / 2
        while s < ln.length - step / 3:
            p = ln.interpolate(s); q = ln.interpolate(min(s + 2, ln.length))
            t = np.array([q.x - p.x, q.y - p.y]); t /= (np.linalg.norm(t) + 1e-9)
            nrm = np.array([-t[1], t[0]])
            sides = [1, -1] if kind == 'light' else [1 if nrm[0] * sea_side_x > 0 else -1]
            for sd in sides:
                pos = np.array([p.x, p.y]) + nrm * sd * off
                if free(pos, 1.0):
                    item = {'x': round(pos[0], 2), 'z': round(pos[1], 2)}
                    if kind == 'light':
                        item['dx'], item['dz'] = round(-nrm[0] * sd, 3), round(-nrm[1] * sd, 3)   # arm points at the road
                        lights.append(item)
                    else:
                        palms.append(item)
            s += step

    # --- neon shop signs in the nightlife district (around a POI), on the building face that looks at the road ----
    signs = []
    sc = L.get('signs')
    if sc:
        from pyproj import Transformer as _T
        _tf = _T.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
        _poi = next((p for p in json.load(open(os.path.join(ROOT, 'data', 'osm', 'normalized', cfg['name'] + '.json'),
                                              encoding='utf-8'))['pois'] if p['id'] == sc['centre_osm_id']), None)
        if _poi is None:
            print(f"signs: centre OSM node {sc['centre_osm_id']} not in the data, no signs")
            sc = None
    if sc:
        _x, _y = _tf.transform(_poi['lon'], _poi['lat'])
        _k = cfg['compression'] / cfg['meters_per_stud']
        centre = Point((_x - g['origin_utm'][0]) * _k, -(_y - g['origin_utm'][1]) * _k)
        road_lines = [LineString(e['pts']) for e in edges]
        ltree = STRtree(road_lines)
        rng = np.random.default_rng(7)
        for b in json.load(open(bpath, encoding='utf-8'))['buildings']:
            if b['palette'] not in ('shophouse', 'commercial', 'hotel') or len(signs) >= sc['max']:
                continue
            c = Point(b['x'], b['z'])
            if c.distance(centre) > sc['radius_studs'] or rng.random() > sc['probability']:
                continue
            near = road_lines[ltree.nearest(c)]
            rp = near.interpolate(near.project(c))
            to_road = np.array([rp.x - c.x, rp.y - c.y])
            if np.linalg.norm(to_road) > max(b['w'], b['d']) / 2 + 40:
                continue
            yaw = math.radians(b['yaw'])
            ax_w = np.array([math.cos(yaw), math.sin(yaw)])           # local +X (width)
            ax_d = np.array([-math.sin(yaw), math.cos(yaw)])          # local +Z (depth)
            faces = [(ax_w, b['w'], b['d']), (-ax_w, b['w'], b['d']), (ax_d, b['d'], b['w']), (-ax_d, b['d'], b['w'])]
            n, half, span = max(faces, key=lambda f: f[0] @ to_road)   # face normal most aligned with the road
            pos = np.array([b['x'], b['z']]) + n * (half / 2 + 0.6)
            h_sign = min(6.0, b['h'] * 0.25)
            signs.append({'x': round(pos[0], 2), 'z': round(pos[1], 2), 'nx': round(n[0], 3), 'nz': round(n[1], 3),
                          'w': round(min(span * 0.7, 26), 1), 'h': round(h_sign, 1),
                          'y': round(min(b['h'] - h_sign, 12 + rng.random() * 6), 1), 'color': int(rng.integers(1, 6))})

    # --- landmarks (proxies) ------------------------------------------------------------------------------------
    landmarks = []
    src = json.load(open(os.path.join(ROOT, 'data', 'osm', 'normalized', cfg['name'] + '.json'), encoding='utf-8'))
    from pyproj import Transformer
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    ox, oy = g['origin_utm']
    kk = cfg['compression'] / cfg['meters_per_stud']
    for lm in L['landmarks']:
        if lm['at'] == 'poi':
            poi = next((p for p in src['pois'] if p['id'] == lm['osm_id']), None)
            if poi is None:
                print(f"landmark {lm['id']}: OSM node {lm['osm_id']} not in the data, skipped")
                continue
            x, y = tf.transform(poi['lon'], poi['lat'])
            pt = Point((x - ox) * kk, -(y - oy) * kk)
            e = min(edges, key=lambda e: LineString(e['pts']).distance(pt))
            ln = LineString(e['pts'])
            s = ln.project(pt)
            p = ln.interpolate(s)
            a_, b_ = ln.interpolate(max(s - 3, 0)), ln.interpolate(min(s + 3, ln.length))   # tangent works at the ends too
            d = np.array([b_.x - a_.x, b_.y - a_.y]); d /= np.linalg.norm(d)
            landmarks.append({'id': lm['id'], 'kind': lm['kind'], 'label': lm['label'], 'x': round(p.x, 2), 'z': round(p.y, 2),
                              'dx': round(d[0], 3), 'dz': round(d[1], 3), 'span': round(e['width'] + 2 * e['sidewalk'] + 4, 1),
                              'source': f"OSM node {lm['osm_id']} ({poi['name']}) snapped to way {e['way']}",
                              'snap_studs': round(ln.distance(pt), 1)})
            continue
        if lm['at'] == 'road_end_near':
            cand = [e for e in edges if named(e, lm['road'])]
            other = nodes_of(lm['near_road'])
            ends = [(e, n) for e in cand for n in (e['a'], e['b']) if n in other]
            if not ends:
                print(f"landmark {lm['id']}: {lm['road']} does not meet {lm['near_road']} in this slice, skipped")
                continue
            e, n = ends[0]
            pts = e['pts'] if e['a'] == n else list(reversed(e['pts']))
            p0, p1 = np.array(pts[0]), np.array(pts[min(3, len(pts) - 1)])
            d = (p1 - p0) / np.linalg.norm(p1 - p0)
            pos = p0 + d * lm.get('inset_studs', 30)
            landmarks.append({'id': lm['id'], 'kind': lm['kind'], 'label': lm['label'], 'x': round(pos[0], 2), 'z': round(pos[1], 2),
                              'dx': round(d[0], 3), 'dz': round(d[1], 3), 'span': round(e['width'] + 2 * e['sidewalk'] + 4, 1),
                              'source': f"OSM way {e['way']} ({e['name_en'] or e['name']})"})

    # --- job stands (taxi pick-up / delivery depots, RayCity-style missions) at real POIs ---------------------------
    # the stand sits in the kerb lane of the nearest road, on the side the POI is on
    stands = []
    for js in L.get('job_stands', []):
        poi = next((p for p in src['pois'] if p['id'] == js['osm_id']), None)
        if poi is None:
            print(f"job stand {js['id']}: OSM node {js['osm_id']} not in the data, skipped")
            continue
        x, y = tf.transform(poi['lon'], poi['lat'])
        pt = Point((x - ox) * kk, -(y - oy) * kk)
        e = min((e for e in edges if e['tier'] != 'express'), key=lambda e: LineString(e['pts']).distance(pt))
        ln = LineString(e['pts'])
        snap = ln.distance(pt)
        if snap > L.get('job_stand_max_snap_studs', 120):
            print(f"job stand {js['id']}: nearest road is {snap:.0f} studs away, skipped")
            continue
        s = min(max(ln.project(pt), 8), max(ln.length - 8, 8))   # keep off the junction at the edge ends
        p = ln.interpolate(s)
        a_, b_ = ln.interpolate(max(s - 3, 0)), ln.interpolate(min(s + 3, ln.length))
        d = np.array([b_.x - a_.x, b_.y - a_.y]); d /= np.linalg.norm(d)
        nrm = np.array([-d[1], d[0]])
        side = 1 if (np.array([pt.x - p.x, pt.y - p.y]) @ nrm) >= 0 else -1
        pos = np.array([p.x, p.y]) + nrm * side * max(e['width'] / 2 - 6, 0)
        stands.append({'id': js['id'], 'kind': js['kind'], 'label': js['label'], 'x': round(pos[0], 2), 'z': round(pos[1], 2),
                       'dx': round(d[0], 3), 'dz': round(d[1], 3),
                       'kx': round(nrm[0] * side, 3), 'kz': round(nrm[1] * side, 3),   # towards the kerb / the POI
                       'source': f"OSM node {js['osm_id']} ({poi['name_en'] or poi['name']}) snapped to way {e['way']}",
                       'snap_studs': round(snap, 1)})

    # route centreline for GPS / minimap / test autopilot: resampled every 20 studs
    # starts at gate 1 so path[1] is the start/finish line
    path = [[round(line.interpolate(s % total).x, 1), round(line.interpolate(s % total).y, 1)]
            for s in np.arange(gate_s[0], gate_s[0] + total, 20.0)]
    import hashlib
    ghash = hashlib.sha1(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), 'rb').read()).hexdigest()
    out = {'graph_sha1': ghash, 'race': {'id': L['race_id'], 'name': L['race_name'], 'laps': L['laps'], 'length_studs': round(total), 'path': path,
                    'route_edges': route_edges, 'checkpoints': checkpoints, 'grid': grid,
                    'legs': [l['names'][0] for l in legs]},
           'spawn': {'x': round(spawn[0], 2), 'z': round(spawn[1], 2)},
           'palms': palms, 'lights': lights, 'signs': signs, 'landmarks': landmarks, 'job_stands': stands}
    out_dir = os.path.join(ROOT, 'build', cfg['name'])
    json.dump(out, open(os.path.join(out_dir, 'layout.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"race '{L['race_name']}': {total:,.0f} studs per lap ({total * cfg['meters_per_stud']:,.0f} m in-game), "
          f"{len(route_edges)} edges, {len(checkpoints)} checkpoints, {len(grid)} grid slots")
    print(f'props: {len(palms)} palms, {len(lights)} street lights, {len(signs)} neon signs; landmarks: {[l["id"] for l in landmarks]}')
    print(f'job stands: {len(stands)} ' + ', '.join(f"{s['id']} ({s['snap_studs']})" for s in stands))

    # check image
    allp = np.array([p for e in edges for p in e['pts']])
    lo, hi = allp.min(0), allp.max(0)
    sc = 1400 / (hi - lo).max()
    im = Image.new('RGB', (int((hi[0] - lo[0]) * sc) + 20, int((hi[1] - lo[1]) * sc) + 20), (240, 238, 232))
    dr = ImageDraw.Draw(im)
    tr = lambda p: (10 + (p[0] - lo[0]) * sc, 10 + (p[1] - lo[1]) * sc)
    for e in edges:
        dr.line([tr(p) for p in e['pts']], fill=(170, 170, 175), width=2)
    dr.line([tr(p) for p in route_pts], fill=(230, 40, 40), width=5)
    for c in checkpoints:
        x, y = tr((c['x'], c['z'])); dr.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(20, 120, 230))
    for p in palms:
        x, y = tr((p['x'], p['z'])); dr.point((x, y), fill=(30, 150, 50))
    x, y = tr((checkpoints[0]['x'], checkpoints[0]['z'])); dr.rectangle([x - 7, y - 7, x + 7, y + 7], outline=(0, 0, 0), width=3)
    for l in landmarks:
        x, y = tr((l['x'], l['z'])); dr.polygon([(x, y - 9), (x - 7, y + 6), (x + 7, y + 6)], fill=(200, 0, 200))
    for s_ in stands:
        x, y = tr((s_['x'], s_['z']))
        dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(250, 200, 0) if s_['kind'] == 'taxi' else (0, 170, 120), outline=(0, 0, 0))
    im.save(os.path.join(out_dir, 'layout_check.png'))


if __name__ == '__main__':
    main(sys.argv[1])
