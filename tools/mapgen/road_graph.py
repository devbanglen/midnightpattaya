"""Stages 2-3 - normalised OSM -> connected road graph (source layer, metres) -> gameplay layer (studs).

  .venv\\Scripts\\python tools\\mapgen\\road_graph.py tools\\mapgen\\config\\central_pattaya.json

Source layer  build/<name>/graph_source.json : UTM metres, original OSM way/node ids, unmodified geometry
Gameplay layer build/<name>/graph_game.json   : compressed + smoothed + widened, every edge keeps its source ids
Check image   build/<name>/compare.png        : source (left) vs gameplay (right), same scale per panel
"""
import json, math, os, sys
from collections import defaultdict
import numpy as np
from pyproj import Transformer
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TIER_COLORS = {'express': (230, 70, 40), 'main': (240, 170, 30), 'soi': (150, 150, 160)}


def chaikin(pts, iterations):
    """Corner cutting with fixed end points (they are junctions shared with other edges)."""
    p = np.asarray(pts, float)
    for _ in range(iterations):
        if len(p) < 3:
            break
        q = np.empty((2 * (len(p) - 1), 2))
        q[0::2] = 0.75 * p[:-1] + 0.25 * p[1:]
        q[1::2] = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.vstack([p[:1], q[1:-1], p[-1:]])
    return p


def resample(pts, step):
    p = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    total = seg.sum()
    if total < 1e-6:
        return p
    n = max(int(round(total / step)), 1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, total, n + 1)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], axis=1)


def length(pts):
    p = np.asarray(pts, float)
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) if len(p) > 1 else 0.0


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    src = json.load(open(os.path.join(ROOT, 'data', 'osm', 'normalized', cfg['name'] + '.json'), encoding='utf-8'))
    S, W, N, E = cfg['slice_bbox_s_w_n_e']
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    ox, oy = tf.transform((W + E) / 2, (S + N) / 2)
    classes = cfg['road_classes']

    def proj(lat, lon):
        x, y = tf.transform(lon, lat)
        return x - ox, y - oy

    def inside(lat, lon):
        return S <= lat <= N and W <= lon <= E

    # --- runs of kept roads inside the slice ------------------------------------------------------------------
    runs = []
    for r in src['roads']:
        c = classes.get(r['class'])
        if not c or not c['keep'] or r['tunnel']:
            continue
        cur = []
        for nid, (lat, lon) in zip(r['nodes'], r['coords']):
            if inside(lat, lon):
                cur.append((nid, proj(lat, lon)))
            else:
                if len(cur) > 1:
                    runs.append((r, cur))
                cur = []
        if len(cur) > 1:
            runs.append((r, cur))

    # graph nodes: run end points and nodes shared by several runs (junctions)
    use = defaultdict(int)
    for _, cur in runs:
        for nid, _ in cur:
            use[nid] += 1
    edges = []
    for r, cur in runs:
        start = 0
        for i in range(1, len(cur)):
            if i == len(cur) - 1 or use[cur[i][0]] > 1:
                seg = cur[start:i + 1]
                edges.append({'id': f"{r['id']}:{len(edges)}", 'way': r['id'], 'class': r['class'],
                              'tier': classes[r['class']]['tier'], 'name': r['name'], 'name_en': r['name_en'],
                              'oneway': r['oneway'], 'lanes_tag': r['lanes'], 'junction': r['junction'],
                              'bridge': r['bridge'], 'a': seg[0][0], 'b': seg[-1][0],
                              'pts': [list(map(float, p)) for _, p in seg]})
                start = i

    # --- connectivity: keep the largest component, prune short dead-end sois ---------------------------------
    def components(es):
        parent = {}
        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for e in es:
            parent[find(e['a'])] = find(e['b'])
        comp = defaultdict(list)
        for e in es:
            comp[find(e['a'])].append(e)
        return sorted(comp.values(), key=lambda c: -sum(length(e['pts']) for e in c))

    comps = components(edges)
    main_comp, dropped_disconnected = comps[0], sum(len(c) for c in comps[1:])
    pruned = 0
    while True:
        deg = defaultdict(int)
        for e in main_comp:
            deg[e['a']] += 1; deg[e['b']] += 1
        keep = [e for e in main_comp if not (e['tier'] == 'soi' and (deg[e['a']] == 1 or deg[e['b']] == 1)
                                             and length(e['pts']) < cfg['drop_dead_end_sois_shorter_m'])]
        if len(keep) == len(main_comp):
            break
        pruned += len(main_comp) - len(keep)
        main_comp = components(keep)[0]
    edges = main_comp

    # coastline clipped to the slice
    coast = []
    for c in src['coastline']:
        pts = [proj(lat, lon) for lat, lon in c['coords'] if inside(lat, lon)]
        if len(pts) > 1:
            coast.append({'id': c['id'], 'pts': [list(map(float, p)) for p in pts]})

    out_dir = os.path.join(ROOT, 'build', cfg['name'])
    os.makedirs(out_dir, exist_ok=True)
    meta = {'name': cfg['name'], 'attribution': src['attribution'], 'osm_base': src['osm_base'], 'crs': cfg['crs'],
            'origin_utm': [ox, oy], 'slice_bbox_s_w_n_e': cfg['slice_bbox_s_w_n_e']}
    json.dump({**meta, 'units': 'metres, x east / y north from origin_utm', 'edges': edges, 'coastline': coast},
              open(os.path.join(out_dir, 'graph_source.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # --- gameplay transformation -------------------------------------------------------------------------------
    k = cfg['compression'] / cfg['meters_per_stud']           # metres -> studs (after compression)
    lane_w = cfg['lane_width_studs']

    def to_game(pts):                                         # Roblox: +X east, +Z south
        return [[x * k, -y * k] for x, y in pts]

    game_edges = []
    for e in edges:
        pts = resample(chaikin(to_game(e['pts']), cfg['smoothing']['chaikin_iterations']), cfg['smoothing']['resample_studs'])
        lanes = classes[e['class']]['lanes']
        try:
            if e['lanes_tag']:
                lanes = max(int(str(e['lanes_tag']).split(';')[0]), 1)
        except ValueError:
            pass
        game_edges.append({'id': e['id'], 'way': e['way'], 'class': e['class'], 'tier': e['tier'], 'name': e['name'],
                           'name_en': e['name_en'], 'oneway': e['oneway'], 'lanes': lanes, 'junction': e['junction'],
                           'width': round(max(lanes * lane_w, cfg['min_lane_width_studs'] * 2 if not e['oneway'] else lane_w), 2),
                           'sidewalk': cfg['sidewalk_studs'][e['tier']], 'a': e['a'], 'b': e['b'],
                           'coastal': (e['name_en'] or '') in cfg['coastal_road_names_en'],
                           'pts': [[round(x, 2), round(z, 2)] for x, z in pts]})
    game_coast = [{'id': c['id'], 'pts': [[round(x, 2), round(z, 2)] for x, z in to_game(c['pts'])]} for c in coast]
    nodes = {}
    for e in game_edges:
        nodes[e['a']] = e['pts'][0]; nodes[e['b']] = e['pts'][-1]
    json.dump({**meta, 'units': 'studs, +X east / +Z south', 'compression': cfg['compression'],
               'meters_per_stud': cfg['meters_per_stud'], 'nodes': {str(n): p for n, p in nodes.items()},
               'edges': game_edges, 'coastline': game_coast},
              open(os.path.join(out_dir, 'graph_game.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # --- report + comparison image -----------------------------------------------------------------------------
    by_tier = defaultdict(float)
    for e in game_edges:
        by_tier[e['tier']] += length(e['pts'])
    allp = np.array([p for e in game_edges for p in e['pts']])
    print(f"runs {len(runs)} -> edges {len(game_edges)} (dropped {dropped_disconnected} disconnected, pruned {pruned} short dead-end sois), "
          f"junction nodes {len(nodes)}")
    print('road length (studs): ' + ', '.join(f'{t} {v:,.0f}' for t, v in sorted(by_tier.items())))
    print(f"gameplay extent X {allp[:, 0].min():.0f}..{allp[:, 0].max():.0f}, Z {allp[:, 1].min():.0f}..{allp[:, 1].max():.0f} studs")

    def panel(edges_pts, coast_pts, widths, scale, size=900):
        im = Image.new('RGB', (size, size), (245, 245, 240))
        dr = ImageDraw.Draw(im)
        allq = np.array([p for pts in edges_pts for p in pts] + [p for pts in coast_pts for p in pts])
        c = (allq.min(0) + allq.max(0)) / 2
        f = (size - 40) / (allq.max(0) - allq.min(0)).max()
        tr = lambda p: (size / 2 + (p[0] - c[0]) * f, size / 2 + (p[1] - c[1]) * f)
        for pts in coast_pts:
            dr.line([tr(p) for p in pts], fill=(40, 120, 220), width=3)
        for pts, (tier, w) in zip(edges_pts, widths):
            dr.line([tr(p) for p in pts], fill=TIER_COLORS[tier], width=max(1, int(w * scale * f)))
        return im

    src_pts = [[[x, -y] for x, y in e['pts']] for e in edges]           # flip y so north is up in both panels
    src_coast = [[[x, -y] for x, y in c['pts']] for c in coast]
    left = panel(src_pts, src_coast, [(e['tier'], e['width'] / k) for e in game_edges], 1.0)
    right = panel([e['pts'] for e in game_edges], [c['pts'] for c in game_coast], [(e['tier'], e['width']) for e in game_edges], 1.0)
    im = Image.new('RGB', (1820, 940), 'white')
    im.paste(left, (10, 30)); im.paste(right, (910, 30))
    d = ImageDraw.Draw(im)
    d.text((20, 8), 'SOURCE (OSM, UTM metres, real road widths implied by game lanes)', fill=(0, 0, 0))
    d.text((920, 8), f"GAMEPLAY (x{cfg['compression']} distance, smoothed, {lane_w}-stud lanes)", fill=(0, 0, 0))
    im.save(os.path.join(out_dir, 'compare.png'))


if __name__ == '__main__':
    main(sys.argv[1])
