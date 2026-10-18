"""Stage E2 - ambient traffic for the Bira access corridor, appended to the wide world's traffic module.

  .venv\\Scripts\\python tools\\circuit\\corridor_traffic.py tools\\circuit\\config\\bira.json

Inputs: build/bira/corridor_graph_game.json (access_corridor.py; both carriageways, city join -> venue junction) and
build/pattaya_wide/roblox/traffic.luau (export_roblox.py; its loops are copied verbatim first).
Output: build/bira/roblox_corridor/traffic.luau -> ReplicatedStorage.PattayaTraffic (replaces the wide one; same
format, map-local studs, PattayaTraffic.client adds PattayaBuilder.ORIGIN), and build/bira/corridor_traffic.json.

Loops (config corridor_life.traffic.loops, pairs of OSM node ids [from, to]): drive from -> to and back to -> from on
the directed corridor graph (one-way edges only a -> b, so a dual carriageway is driven out on one carriageway and
back on the other), offset into the left-hand lane exactly like tools/mapgen/traffic.py. The route helpers here are
also used by export_corridor.py for the direction signs (remaining distance along the outbound route).
"""
import heapq, json, os, random, sys
from collections import defaultdict
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'mapgen'))
from traffic import dp, plen  # noqa: E402


def directed_path(edges, src, dst):
    """shortest directed path src -> dst: [(edge index, forward?)] (one-way edges only a -> b)."""
    out = defaultdict(list)
    for i, e in enumerate(edges):
        out[e['a']].append((i, e['b'], True))
        if not e['oneway']:
            out[e['b']].append((i, e['a'], False))
    elen = [plen(e['pts']) for e in edges]
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        d, n = heapq.heappop(pq)
        if n == dst:
            break
        if d > dist[n]:
            continue
        for i, m, f in out[n]:
            if d + elen[i] < dist.get(m, 1e18):
                dist[m] = d + elen[i]; prev[m] = (n, i, f); heapq.heappush(pq, (dist[m], m))
    if dst not in prev:
        return None
    path, n = [], dst
    while n != src:
        p, i, f = prev[n]
        path.append((i, f)); n = p
    return path[::-1]


def path_polyline(edges, path):
    """centreline of a directed path in driving order, plus the edge index of every point."""
    pts, owner = [], []
    for i, f in path:
        p = edges[i]['pts'] if f else edges[i]['pts'][::-1]
        for k, q in enumerate(p):
            if pts and k == 0 and np.hypot(pts[-1][0] - q[0], pts[-1][1] - q[1]) < 1:
                continue
            pts.append(list(q)); owner.append(i)
    return np.array(pts, float), owner


def lane_polyline(edges, steps, rng):
    """the loop's polyline offset into the left-hand lane (same rule as tools/mapgen/traffic.py)."""
    pts = []
    for i, f in steps:
        e = edges[i]
        p = np.array(e['pts'] if f else list(reversed(e['pts'])), dtype=float)
        if len(p) < 2:
            continue
        seg = np.diff(p, axis=0)
        seg /= (np.linalg.norm(seg, axis=1, keepdims=True) + 1e-9)
        nrm = np.zeros_like(p)
        nrm[:-1] += seg; nrm[1:] += seg
        nrm /= (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9)
        left = np.stack([nrm[:, 1], -nrm[:, 0]], axis=1)
        lane = e['width'] / 4 if (not e['oneway'] or e['width'] < 30) else e['width'] / 4 + rng.choice([0, e['width'] / 4])
        q = p + left * lane
        for k, pt in enumerate(q.tolist()):
            if pts and k == 0 and np.linalg.norm(np.array(pts[-1]) - pt) < 1:
                continue
            pts.append(pt)
    pts = dp(pts, 0.8)
    if np.linalg.norm(np.array(pts[0]) - np.array(pts[-1])) > 0.5:
        pts.append(pts[0])
    return pts


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    T = cfg['corridor_life']['traffic']
    bira = os.path.join(ROOT, 'build', 'bira')
    g = json.load(open(os.path.join(bira, 'corridor_graph_game.json'), encoding='utf-8'))
    edges = g['edges']
    rng = random.Random(T['seed'])
    routes = []
    for src, dst in T['loops']:
        out_p, back_p = directed_path(edges, src, dst), directed_path(edges, dst, src)
        if out_p is None or back_p is None:
            sys.exit(f'corridor loop {src} <-> {dst}: no directed path')
        pts = lane_polyline(edges, out_p + back_p, rng)
        L = plen(pts)
        cars = max(1, int(L // T['studs_per_car']))
        routes.append({'from': src, 'to': dst, 'pts': [[round(x, 1), round(z, 1)] for x, z in pts], 'length': round(L, 1),
                       'speed': round(rng.uniform(*T['speed_studs_s']), 1), 'cars': cars,
                       'kinds': [rng.choices(range(len(T['kind_weights'])), T['kind_weights'])[0] for _ in range(cars)],
                       'phase': round(rng.uniform(0, L), 1)})
        print(f'loop {src} <-> {dst}: {L:,.0f} studs, {cars} cars, {len(pts)} points, {routes[-1]["speed"]} studs/s')
    json.dump({'routes': routes}, open(os.path.join(bira, 'corridor_traffic.json'), 'w', encoding='utf-8'))

    # combined module: the wide loops verbatim (byte for byte), then the corridor loops in the same line format
    wide = open(os.path.join(ROOT, 'build', 'pattaya_wide', 'roblox', 'traffic.luau'), encoding='utf-8').read().rstrip('\n')
    assert wide.endswith('\n}'), 'unexpected wide traffic.luau layout'
    n_wide = wide.count('\n  { length = ')
    lines = [wide[:-2], f'  -- Bira access corridor loops (tools/circuit/corridor_traffic.py), after the {n_wide} wide loops']
    for r in routes:
        lines.append(f'  {{ length = {r["length"]}, speed = {r["speed"]}, phase = {r["phase"]}, '
                     f'kinds = {{{",".join(str(k) for k in r["kinds"])}}}, '
                     f'pts = {{{",".join(f"{x},{z}" for x, z in r["pts"])}}} }},')
    lines.append('}')
    out = os.path.join(bira, 'roblox_corridor', 'traffic.luau')
    open(out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'{out}: {n_wide} wide + {len(routes)} corridor loops, {os.path.getsize(out) / 1024:.0f} KB, '
          f'{sum(r["cars"] for r in routes)} corridor cars')


if __name__ == '__main__':
    main(sys.argv[1])
