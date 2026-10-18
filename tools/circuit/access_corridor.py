"""Bira access corridor - real road route central Pattaya -> Bira Circuit, as a road graph in the city schema.

  .venv\\Scripts\\python tools\\circuit\\access_corridor.py tools\\circuit\\config\\bira.json

Routes on the OSM corridor download (data/osm/raw/bira_corridor_*.json + the service roads of the circuit download)
from the east end of Pattaya Klang Road in the central slice graph to the CBI.2081 / Bira junction, both directions
(dual carriageways are separate one-way ways). Travel-time weights by road class, no invented roads.

Source layer  build/bira/corridor_graph_source.json : UTM metres from the CITY origin_utm, OSM way/node ids
Gameplay layer build/bira/corridor_graph_game.json   : same schema and transform as build/<city>/graph_game.json
                                                      (origin_utm, compression 0.5, 0.28 m/stud, chaikin + resample)
so it can be merged with the city graph: node ids are OSM node ids, the join node exists in both graphs.
"""
import heapq, json, math, os, sys
from collections import defaultdict
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'mapgen'))
from road_graph import chaikin, resample, length          # same smoothing as the city graph (read-only import)

SPEED_KMH = {'motorway': 90, 'trunk': 80, 'trunk_link': 40, 'primary': 50, 'primary_link': 30, 'secondary': 45,
             'secondary_link': 30, 'tertiary': 40, 'tertiary_link': 30, 'unclassified': 30, 'service': 15}


def city_frame(cfg):
    """origin_utm / compression / m-per-stud of the city graph (falls back to the values copied into the config)."""
    p = os.path.normpath(os.path.join(ROOT, cfg['city_graph']))
    if os.path.exists(p):
        g = json.load(open(p, encoding='utf-8'))
        return g['origin_utm'], g['compression'], g['meters_per_stud'], set(g['nodes']), g['nodes']
    print('city graph not found, using city_origin_utm from the config (join node not cross-checked)')
    return cfg['city_origin_utm'], cfg['city_compression'], cfg['city_meters_per_stud'], set(), {}


def load_ways(paths):
    ways = {}
    for f in paths:
        for e in json.load(open(os.path.join(ROOT, f), encoding='utf-8'))['elements']:
            if e['type'] == 'way' and 'highway' in e.get('tags', {}) and 'geometry' in e:
                ways[e['id']] = e
    return ways


def main(cfg_path):
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    (ox, oy), comp, mps, city_nodes, city_pos = city_frame(cfg)
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    raw = json.load(open(os.path.join(ROOT, cfg['corridor_raw']), encoding='utf-8'))
    ways = load_ways([cfg['corridor_raw'], cfg['circuit_raw']])
    classes = cfg['corridor_road_classes']

    pos, adj = {}, defaultdict(list)                      # directed graph honouring oneway tags
    for w in ways.values():
        t = w['tags']
        if t['highway'] not in SPEED_KMH or t.get('tunnel') == 'yes' or t.get('access') == 'no':
            continue
        for n, g in zip(w['nodes'], w['geometry']):
            x, y = tf.transform(g['lon'], g['lat'])
            pos[n] = (x - ox, y - oy)
        ow = t.get('oneway')
        fwd_only = ow in ('yes', 'true', '1') or t.get('junction') == 'roundabout'
        for a, b in zip(w['nodes'], w['nodes'][1:]):
            c = math.dist(pos[a], pos[b]) / SPEED_KMH[t['highway']]
            if ow != '-1':
                adj[a].append((b, c, w['id']))
            if not fwd_only:
                adj[b].append((a, c, w['id']))

    def dijkstra(src, dst, allowed=None):
        D, P, q = {src: 0.0}, {}, [(0.0, src)]
        while q:
            d, u = heapq.heappop(q)
            if u == dst:
                break
            if d > D[u]:
                continue
            for v, c, wid in adj[u]:
                if allowed is not None and v not in allowed:
                    continue
                if d + c < D.get(v, 1e18):
                    D[v], P[v] = d + c, (u, wid)
                    heapq.heappush(q, (d + c, v))
        if dst not in D:
            sys.exit(f'no route {src} -> {dst}')
        path, used = [dst], []
        while path[-1] != src:
            u, wid = P[path[-1]]
            used.append((u, path[-1], wid)); path.append(u)
        return path[::-1], used[::-1]

    J0, J1 = cfg['join_node_city'], cfg['facility_junction_node']
    out_path, out_used = dijkstra(J0, J1)
    # return trip: the opposite carriageways of the same roads (search limited to a band around the outward route,
    # otherwise one-way pairs and U-turn rules send it round Highway 36, a different road)
    band = LineString([pos[n] for n in out_path]).buffer(cfg['return_band_m'])
    back_path, back_used = dijkstra(J1, J0, {n for n, p in pos.items() if band.contains(Point(p))})
    segs = {(a, b): wid for a, b, wid in out_used + back_used}   # directed segments actually driven

    # undirected degree on the union -> graph nodes where the routes split/merge, ways change, or at the ends
    nb = defaultdict(set)
    for a, b in segs:
        nb[a].add(b); nb[b].add(a)
    seg_way = {}
    for (a, b), wid in segs.items():
        seg_way[frozenset((a, b))] = wid
    edges = []
    for wid in sorted({w for w in segs.values()}):
        w = ways[wid]
        t, nodes = w['tags'], w['nodes']
        run = []
        for i in range(len(nodes) - 1):
            a, b = nodes[i], nodes[i + 1]
            if seg_way.get(frozenset((a, b))) == wid:
                if not run:
                    run = [a]
                run.append(b)
                is_node = len(nb[b]) != 2 or b in (J0, J1) or any(seg_way.get(frozenset((b, c))) != wid for c in nb[b])
                if is_node or i == len(nodes) - 2:
                    edges.append((w, run)); run = []
            elif run:
                edges.append((w, run)); run = []
        if len(run) > 1:
            edges.append((w, run))

    src_edges = []
    for w, run in edges:
        t = w['tags']
        oneway = t.get('oneway') in ('yes', 'true', '1') or t.get('junction') == 'roundabout'
        src_edges.append({'id': f"{w['id']}:c{len(src_edges)}", 'way': w['id'], 'class': t['highway'],
                          'tier': classes[t['highway']]['tier'], 'name': t.get('name'), 'name_en': t.get('name:en'),
                          'ref': t.get('ref'), 'oneway': oneway, 'lanes_tag': t.get('lanes'),
                          'junction': t.get('junction'), 'bridge': t.get('bridge') == 'yes', 'a': run[0], 'b': run[-1],
                          'pts': [[round(pos[n][0], 2), round(pos[n][1], 2)] for n in run]})

    out_dir = os.path.join(ROOT, 'build', cfg['name'])
    os.makedirs(out_dir, exist_ok=True)
    meta = {'name': 'bira_corridor', 'attribution': 'Map data (c) OpenStreetMap contributors, ODbL 1.0',
            'osm_base': raw['osm3s']['timestamp_osm_base'], 'crs': cfg['crs'], 'origin_utm': [ox, oy],
            'join_nodes': {'city': J0, 'facility': J1},
            'note': 'route central Pattaya (Pattaya Klang Rd east end) -> Bira junction on CBI.2081, both directions'}
    json.dump({**meta, 'units': 'metres, x east / y north from origin_utm', 'edges': src_edges, 'coastline': []},
              open(os.path.join(out_dir, 'corridor_graph_source.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # --- gameplay transformation: identical to tools/mapgen/road_graph.py --------------------------------------
    k = comp / mps
    lane_w = cfg['lane_width_studs']
    game_edges = []
    for e in src_edges:
        pts = resample(chaikin([[x * k, -y * k] for x, y in e['pts']], cfg['smoothing']['chaikin_iterations']),
                       cfg['smoothing']['resample_studs'])
        lanes = classes[e['class']]['lanes']
        try:
            if e['lanes_tag']:
                lanes = max(int(str(e['lanes_tag']).split(';')[0]), 1)
        except ValueError:
            pass
        game_edges.append({'id': e['id'], 'way': e['way'], 'class': e['class'], 'tier': e['tier'], 'name': e['name'],
                           'name_en': e['name_en'], 'oneway': e['oneway'], 'lanes': lanes, 'junction': e['junction'],
                           'width': round(max(lanes * lane_w, cfg['min_lane_width_studs'] * 2 if not e['oneway'] else lane_w), 2),
                           'sidewalk': cfg['sidewalk_studs'][e['tier']], 'a': e['a'], 'b': e['b'], 'coastal': False,
                           'corridor': 'bira', 'pts': [[round(x, 2), round(z, 2)] for x, z in pts]})
    nodes = {}
    for e in game_edges:
        nodes[e['a']] = e['pts'][0]; nodes[e['b']] = e['pts'][-1]
    json.dump({**meta, 'slice_bbox_s_w_n_e': cfg['city_slice_bbox_s_w_n_e'], 'units': 'studs, +X east / +Z south',
               'compression': comp, 'meters_per_stud': mps, 'nodes': {str(n): p for n, p in nodes.items()},
               'edges': game_edges, 'coastline': []},
              open(os.path.join(out_dir, 'corridor_graph_game.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # --- report -----------------------------------------------------------------------------------------------
    def route_names(used):
        seq = []
        for _, _, wid in used:
            t = ways[wid]['tags']
            nm = f"{t.get('name:en') or t.get('name') or t.get('ref') or '(unnamed)'} [{t['highway']}]"
            if not seq or seq[-1] != nm:
                seq.append(nm)
        return seq
    for lbl, path, used in (('out', out_path, out_used), ('back', back_path, back_used)):
        L = sum(math.dist(pos[a], pos[b]) for a, b in zip(path, path[1:]))
        print(f"{lbl}: {L:,.0f} m real -> {L * k:,.0f} studs; " + ' > '.join(route_names(used)))
    jc = str(J0)
    if jc in city_nodes:
        d = math.dist(city_pos[jc], nodes[J0])
        print(f"join node {J0} in city graph at {city_pos[jc]}, corridor {nodes[J0]} (offset {d:.2f} studs)")
    elif city_nodes:
        print(f"WARNING join node {J0} not in the city graph")
    inside = [n for n in nodes if n != J0 and str(n) in city_nodes]
    print(f"edges {len(game_edges)}, nodes {len(nodes)}, other nodes shared with the city graph: {inside}")
    print(f"facility junction {J1} at {nodes[J1]} studs (map-local)")


if __name__ == '__main__':
    main(sys.argv[1])
