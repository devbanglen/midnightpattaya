"""Stage 7 - ambient traffic routes on the gameplay graph.

  .venv\\Scripts\\python tools\\mapgen\\traffic.py tools\\mapgen\\config\\central_pattaya.json

Writes build/<name>/traffic.json: closed driving loops (random walk on the directed road graph, preferring main
roads, closed with a shortest path back), already offset into the left-hand lane (Thailand drives on the left).
The client moves cars along them as a pure function of server time, so every player sees the same traffic with no
network traffic. One-way roads are respected (edge a -> b).
With a "base" block (wide world) the base build's loops are copied verbatim first and the new loops start on new
(non-base) main roads; they may run through the base slice like real traffic does.
"""
import hashlib, heapq, json, math, os, random, sys
from collections import defaultdict
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def plen(p):
    p = np.asarray(p)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def dp(pts, eps):
    """Douglas-Peucker on a list of (x, z)."""
    pts = np.asarray(pts)
    if len(pts) < 3:
        return pts.tolist()
    a, b = pts[0], pts[-1]
    ab = b - a
    n = np.linalg.norm(ab)
    d = (np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / n) if n > 1e-9 else np.linalg.norm(pts - a, axis=1)
    i = int(np.argmax(d))
    if d[i] > eps:
        return dp(pts[:i + 1], eps)[:-1] + dp(pts[i:], eps)
    return [a.tolist(), b.tolist()]


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    T = cfg['traffic']
    gpath = os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json')
    g = json.load(open(gpath, encoding='utf-8'))
    edges = g['edges']
    rng = random.Random(T.get('seed', 11))

    # directed links: node -> [(edge index, to node, forward?)]
    out = defaultdict(list)
    for i, e in enumerate(edges):
        out[e['a']].append((i, e['b'], True))
        if not e['oneway']:
            out[e['b']].append((i, e['a'], False))
    elen = [plen(e['pts']) for e in edges]
    main_edges = [i for i, e in enumerate(edges) if e['tier'] == 'main' and elen[i] > 40]
    if 'base' in cfg:
        main_edges = [i for i in main_edges if not edges[i].get('base')]

    def back_path(src, dst):
        """directed Dijkstra src -> dst; sois cost more."""
        dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
        while pq:
            d, n = heapq.heappop(pq)
            if n == dst:
                break
            if d > dist[n]:
                continue
            for i, m, fwd in out[n]:
                c = d + elen[i] * (1 if edges[i]['tier'] == 'main' else 2.5)
                if c < dist.get(m, 1e18):
                    dist[m] = c; prev[m] = (n, i, fwd); heapq.heappush(pq, (c, m))
        if dst not in prev and src != dst:
            return None
        path, n = [], dst
        while n != src:
            p, i, fwd = prev[n]
            path.append((i, fwd)); n = p
        return list(reversed(path))

    routes = []
    tries = 0
    while len(routes) < T['routes'] and tries < T['routes'] * 30:
        tries += 1
        i0 = rng.choice(main_edges)
        e0 = edges[i0]
        fwd0 = True if e0['oneway'] else rng.random() < 0.5
        start = e0['a'] if fwd0 else e0['b']
        steps = [(i0, fwd0)]
        node = e0['b'] if fwd0 else e0['a']
        length = elen[i0]
        target = rng.uniform(T['min_loop_studs'], T['max_loop_studs']) * 0.6
        while length < target:
            opts = [(i, m, f) for i, m, f in out[node] if i != steps[-1][0]]
            if not opts:
                break
            mains = [o for o in opts if edges[o[0]]['tier'] == 'main']
            pool = mains if mains and rng.random() < T['main_road_bias'] else opts
            i, m, f = rng.choice(pool)
            steps.append((i, f)); node = m; length += elen[i]
        back = back_path(node, start)
        if back is None:
            continue
        steps += back
        total = sum(elen[i] for i, _ in steps)
        if not (T['min_loop_studs'] <= total <= T['max_loop_studs'] * 1.6):
            continue
        # polyline in driving direction, offset into the left lane (left of travel = (dz, -dx))
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
        L = plen(pts)
        cars = max(1, int(L // T['studs_per_car']))
        routes.append({'pts': [[round(x, 1), round(z, 1)] for x, z in pts], 'length': round(L, 1),
                       'speed': round(rng.uniform(*T['speed_studs_s']), 1), 'cars': cars,
                       'kinds': [rng.choices(range(len(T['kind_weights'])), T['kind_weights'])[0] for _ in range(cars)],
                       'phase': round(rng.uniform(0, L), 1)})
    if 'base' in cfg:
        base_routes = json.load(open(os.path.join(ROOT, cfg['base']['build'], 'traffic.json'), encoding='utf-8'))['routes']
        print(f'{len(base_routes)} base loops copied from {cfg["base"]["build"]}; {len(routes)} new loops')
        routes = base_routes + routes
    ghash = hashlib.sha1(open(gpath, 'rb').read()).hexdigest()
    out_path = os.path.join(ROOT, 'build', cfg['name'], 'traffic.json')
    json.dump({'graph_sha1': ghash, 'routes': routes}, open(out_path, 'w', encoding='utf-8'))
    ncars = sum(r['cars'] for r in routes)
    print(f"traffic: {len(routes)} loops ({tries} tries), {sum(r['length'] for r in routes):,.0f} studs of lanes, {ncars} cars, "
          f"{sum(len(r['pts']) for r in routes)} points")


if __name__ == '__main__':
    main(sys.argv[1])
