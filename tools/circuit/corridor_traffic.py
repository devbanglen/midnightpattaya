"""Stage E2 - ambient traffic for the Bira access corridor, appended to the wide world's traffic module.

  .venv\\Scripts\\python tools\\circuit\\corridor_traffic.py tools\\circuit\\config\\bira.json

Inputs: build/bira/corridor_graph_game.json (access_corridor.py; both carriageways, city join -> venue junction) and
build/pattaya_wide/roblox/traffic.luau (export_roblox.py; its loops are copied verbatim first).
Output: build/bira/roblox_corridor/traffic.luau -> ReplicatedStorage.PattayaTraffic (replaces the wide one; same
format, map-local studs, PattayaTraffic.client adds PattayaBuilder.ORIGIN), and build/bira/corridor_traffic.json.

Loops (config corridor_life.traffic.loops, pairs of OSM node ids [from, to]): drive from -> to and back to -> from on
the directed corridor graph (one-way edges only a -> b, so a dual carriageway is driven out on one carriageway and
back on the other), offset into the left-hand lane exactly like tools/mapgen/traffic.py (including its dual-carriageway
lane fix, tools/mapgen/dual.py: on a merged slab the lane stays inside it; the corridor's own copies of city ways are
matched by OSM way; car counts use the unmerged lane length so every random draw stays the same). The route helpers here
are also used by export_corridor.py for the direction signs (remaining distance along the outbound route).
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


def lane_polyline(edges, steps, rng, field=None, unmerged=None):
    """the loop's polyline offset into the left-hand lane (same rule as tools/mapgen/traffic.py). With a dual.MergeField
    the lanes on merged carriageways are moved inside the merged slab; `unmerged` (a list) then receives the polyline
    without that fix."""
    pts, pts0 = [], []
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
        # same rule as tools/mapgen/traffic.py (2026-10-20): outer lane of a wide one-way road at 3W/8, not W/2 (the
        # road edge); the plan polyline (car counts, de-dup) keeps the old lane and the same random draw.
        if not e['oneway'] or e['width'] < 30:
            lane_plan = lane = e['width'] / 4
        else:
            outer = rng.choice([0, 1])
            lane_plan = e['width'] / 4 + outer * e['width'] / 4
            lane = e['width'] / 4 + outer * e['width'] / 8
        q0 = p + left * lane_plan
        q = p + left * field.adjust(e, p, left, lane)[:, None] if field is not None else p + left * lane
        for k, (pt, pt0) in enumerate(zip(q.tolist(), q0.tolist())):
            if pts0 and k == 0 and np.linalg.norm(np.array(pts0[-1]) - pt0) < 1:
                continue
            pts.append(pt); pts0.append(pt0)
    pts, pts0 = dp(pts, 0.8), dp(pts0, 0.8)
    if np.linalg.norm(np.array(pts[0]) - np.array(pts[-1])) > 0.5:
        pts.append(pts[0])
    if np.linalg.norm(np.array(pts0[0]) - np.array(pts0[-1])) > 0.5:
        pts0.append(pts0[0])
    if unmerged is not None:
        unmerged[:] = pts0
    return pts


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    T = cfg['corridor_life']['traffic']
    bira = os.path.join(ROOT, 'build', 'bira')
    g = json.load(open(os.path.join(bira, 'corridor_graph_game.json'), encoding='utf-8'))
    edges = g['edges']
    rng = random.Random(T['seed'])
    import dual
    plan = dual.load_plan(ROOT)
    field = None
    if plan:
        known = {e['id']: e for e in json.load(open(os.path.join(ROOT, 'build', 'pattaya_wide', 'graph_game.json'), encoding='utf-8'))['edges']}
        known.update({e['id']: e for e in edges})
        field = dual.MergeField(plan, known)
    routes = []
    for src, dst in T['loops']:
        out_p, back_p = directed_path(edges, src, dst), directed_path(edges, dst, src)
        if out_p is None or back_p is None:
            sys.exit(f'corridor loop {src} <-> {dst}: no directed path')
        pts0 = []
        pts = lane_polyline(edges, out_p + back_p, rng, field, pts0)
        L = plen(pts)
        cars = max(1, int(plen(pts0) // T['studs_per_car']))   # as without the dual merge: same random draws after
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
