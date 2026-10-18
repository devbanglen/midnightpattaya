"""Stage 5 - OSM building footprints -> gameplay building boxes that never touch a road.

  .venv\\Scripts\\python tools\\mapgen\\buildings.py tools\\mapgen\\config\\central_pattaya.json

Each footprint goes through the same projection + compression as the roads, then the widened road corridors
(road + sidewalks + margin) are cut out of it. What is left becomes one oriented box (minimum rotated rectangle,
shrunk until it clears the corridors). Height comes from OSM height / building:levels, else a category default.
Writes build/<name>/buildings_game.json and buildings_check.png. Source ids are kept on every box.

Wide-world options (absent in central_pattaya.json, so that build is unchanged):
  "clip_polygon_lat_lon"     footprints must lie inside it (and the bbox)
  "base"                     footprints wholly inside the base slice belong to the base build and are skipped; new
                             boxes that would overlap a base box are dropped (the tested slice is never changed)
  buildings.lod = {          thinning for a big map (see docs/PERFORMANCE_BUDGET.md)
    "merge_below_area_studs2": 900,  small neighbours (shophouse rows, houses) closer than "merge_gap_studs" are
    "merge_gap_studs": 3,            merged into one box when the box covers "merge_min_fill" of their union and
    "merge_min_fill": 0.72,          still clears every road corridor
    "max_per_chunk": 140,            keep at most this many boxes per 512-stud chunk (named / OSM-height / biggest
                                     first)
    "facade_min_height_studs": 0 }   read by export_roblox.py: lower boxes get no facade Textures
"""
import json, math, os, random, sys
from collections import Counter
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from shapely import affinity
from shapely.strtree import STRtree
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# category -> (default levels range, palette name)
CATEGORIES = {
    'hotel': ((8, 22), 'hotel'), 'condo': ((10, 28), 'condo'), 'apartments': ((5, 12), 'apartment'),
    'mall': ((3, 5), 'mall'), 'commercial': ((3, 6), 'commercial'), 'shophouse': ((2, 4), 'shophouse'),
    'house': ((1, 2), 'house'), 'temple': ((1, 2), 'temple'), 'parking': ((3, 5), 'parking'),
    'public': ((2, 4), 'commercial'), 'industrial': ((1, 2), 'commercial'),
}


def categorise(b):
    k, t, a, s, n = b['kind'], b.get('tourism'), b.get('amenity'), b.get('shop'), (b.get('name_en') or b.get('name') or '').lower()
    if t in ('hotel', 'hostel', 'guest_house', 'apartment') or k == 'hotel' or 'hotel' in n or 'resort' in n:
        return 'hotel'
    if 'condo' in n or 'residence' in n or 'tower' in n:
        return 'condo'
    if k in ('apartments', 'dormitory', 'residential') and 'house' not in k:
        return 'apartments'
    if s in ('mall', 'department_store') or k in ('retail', 'supermarket') and ('mall' in n or 'central' in n or 'plaza' in n):
        return 'mall'
    if k in ('parking',) or a == 'parking':
        return 'parking'
    if k in ('temple', 'church', 'mosque', 'shrine') or a == 'place_of_worship':
        return 'temple'
    if k in ('commercial', 'retail', 'office', 'supermarket') or s or a in ('restaurant', 'bank', 'cafe', 'bar', 'pub', 'nightclub'):
        return 'commercial'
    if k in ('house', 'detached', 'bungalow', 'hut', 'semidetached_house'):
        return 'house'
    if k in ('terrace',):
        return 'shophouse'
    if k in ('school', 'hospital', 'public', 'government', 'university', 'civic'):
        return 'public'
    if k in ('industrial', 'warehouse', 'shed', 'garage', 'garages', 'roof'):
        return 'industrial'
    return None                      # building=yes etc.: decided by size/location below


def box_poly(x):
    r = Polygon([(-x['w'] / 2, -x['d'] / 2), (x['w'] / 2, -x['d'] / 2), (x['w'] / 2, x['d'] / 2), (-x['w'] / 2, x['d'] / 2)])
    return affinity.translate(affinity.rotate(r, x['yaw']), x['x'], x['z'])


def thin(boxes, lod, tree, blockers, C, level_studs, bc, stats):
    """LOD for big maps: merge small neighbouring boxes, then cap the count per chunk."""
    polys = [box_poly(x) for x in boxes]
    below = lod.get('merge_below_area_studs2', 0)
    if below:
        cand = [i for i, x in enumerate(boxes) if x['w'] * x['d'] < below and x['cat'] in ('shophouse', 'house', 'commercial')]
        grown = [polys[i].buffer(lod.get('merge_gap_studs', 3) / 2) for i in cand]
        ctree = STRtree(grown)
        parent = list(range(len(cand)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a
        for k, g in enumerate(grown):
            for j in ctree.query(g):
                if j != k and g.intersects(grown[j]):
                    parent[find(j)] = find(k)
        groups = {}
        for k in range(len(cand)):
            groups.setdefault(find(k), []).append(cand[k])
        all_tree = STRtree(polys)
        drop, add = set(), []
        for members in groups.values():
            if len(members) < 2:
                continue
            u = unary_union([polys[i] for i in members])
            rect = u.minimum_rotated_rectangle
            if u.area / rect.area < lod.get('merge_min_fill', 0.72):
                continue
            if any(rect.intersects(blockers[i]) and rect.intersection(blockers[i]).area > 0.5 for i in tree.query(rect)):
                continue
            ms = set(members)
            if any(j not in ms and rect.intersects(polys[j]) and rect.intersection(polys[j]).area > 0.5 for j in all_tree.query(rect)):
                continue
            c = np.array(rect.exterior.coords[:4])
            e1, e2 = c[1] - c[0], c[2] - c[1]
            area = sum(boxes[i]['w'] * boxes[i]['d'] for i in members)
            levels = max(1, round(sum(boxes[i]['levels'] * boxes[i]['w'] * boxes[i]['d'] for i in members) / area))
            first = boxes[min(members, key=lambda i: boxes[i]['id'])]
            add.append({**first, 'cat': Counter(boxes[i]['cat'] for i in members).most_common(1)[0][0],
                        'levels': levels, 'levels_src': 'merged', 'name': None,
                        'x': round(rect.centroid.x, 2), 'z': round(rect.centroid.y, 2),
                        'w': round(float(np.linalg.norm(e1)), 2), 'd': round(float(np.linalg.norm(e2)), 2),
                        'h': round(levels * level_studs + bc['ground_floor_extra_studs'], 2),
                        'yaw': round(math.degrees(math.atan2(e1[1], e1[0])), 2),
                        'merged': sorted(boxes[i]['id'] for i in members)})
            add[-1]['palette'] = CATEGORIES[add[-1]['cat']][1]
            drop |= ms
        stats['merged_away'] += len(drop) - len(add)
        boxes = [x for i, x in enumerate(boxes) if i not in drop] + add
    cap = lod.get('max_per_chunk')
    if cap:
        by_chunk = {}
        for x in boxes:
            by_chunk.setdefault((math.floor(x['x'] / C), math.floor(x['z'] / C)), []).append(x)
        kept = []
        for cid in sorted(by_chunk):
            xs = sorted(by_chunk[cid], key=lambda x: (not x.get('name'), x['levels_src'] != 'osm', -x['w'] * x['d'] * x['h'], x['id']))
            stats['chunk_cap'] += max(0, len(xs) - cap)
            kept += xs[:cap]
        boxes = kept
    return boxes


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    bc = cfg['buildings']
    src = json.load(open(os.path.join(ROOT, 'data', 'osm', 'normalized', cfg['name'] + '.json'), encoding='utf-8'))
    g = json.load(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), encoding='utf-8'))
    S, W, N, E = cfg['slice_bbox_s_w_n_e']
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    ox, oy = g['origin_utm']
    k = cfg['compression'] / cfg['meters_per_stud']
    level_studs = bc['level_height_m'] * bc['vertical_scale'] / cfg['meters_per_stud']

    # road corridors (game space)
    corridors = [LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'] + bc['road_margin_studs'], cap_style=2, join_style=1)
                 for e in g['edges']]
    junctions = []
    deg = Counter([e['a'] for e in g['edges']] + [e['b'] for e in g['edges']])
    widest = {}
    for e in g['edges']:
        for n in (e['a'], e['b']):
            widest[n] = max(widest.get(n, 0), e['width'] / 2 + e['sidewalk'])
    for n, p in g['nodes'].items():
        junctions.append(LineString([p, p]).buffer(widest[int(n)] + bc['road_margin_studs']))
    blockers = corridors + junctions
    tree = STRtree(blockers)
    coastal = unary_union([LineString(e['pts']) for e in g['edges'] if e['coastal']])

    boxes, stats = [], Counter()
    rng = random.Random(cfg['name'])
    clip = None
    if 'clip_polygon_lat_lon' in cfg:
        from shapely.prepared import prep
        clip = prep(Polygon([(lo, la) for la, lo in cfg['clip_polygon_lat_lon']]))
    base_boxes = None
    if 'base' in cfg:
        bS, bW, bN, bE = cfg['base']['slice_bbox_s_w_n_e']
        base_boxes = [box_poly(x) for x in json.load(open(os.path.join(ROOT, cfg['base']['build'], 'buildings_game.json'),
                                                           encoding='utf-8'))['buildings']]
        base_tree = STRtree(base_boxes)
    for b in src['buildings']:
        if not all(S <= la <= N and W <= lo <= E for la, lo in b['coords']):
            stats['outside'] += 1
            continue
        if clip is not None and not clip.contains(Polygon([(lo, la) for la, lo in b['coords']]).centroid):
            stats['outside'] += 1
            continue
        if base_boxes is not None and all(bS <= la <= bN and bW <= lo <= bE for la, lo in b['coords']):
            stats['base_slice'] += 1
            continue
        pts = []
        for la, lo in b['coords']:
            x, y = tf.transform(lo, la)
            pts.append(((x - ox) * k, -(y - oy) * k))
        try:
            poly = Polygon(pts).buffer(0)
        except ValueError:
            stats['bad'] += 1
            continue
        if poly.area < bc['min_area_studs2']:
            stats['tiny'] += 1
            continue
        near = [blockers[i] for i in tree.query(poly)]
        if near:
            poly = poly.difference(unary_union(near))
        if poly.is_empty:
            stats['on_road'] += 1
            continue
        if poly.geom_type == 'MultiPolygon':
            poly = max(poly.geoms, key=lambda q: q.area)
        if poly.area < bc['min_area_studs2']:
            stats['clipped_away'] += 1
            continue
        rect = poly.minimum_rotated_rectangle
        ok = False
        for _ in range(8):                             # shrink about the centroid until the box clears every corridor
            hits = [blockers[i] for i in tree.query(rect)]
            if not any(rect.intersects(h) and rect.intersection(h).area > 0.5 for h in hits):
                ok = True
                break
            rect = affinity.scale(rect, 0.88, 0.88, origin=rect.centroid)
        if not ok or rect.area < bc['min_area_studs2']:
            stats['no_fit'] += 1
            continue
        if base_boxes is not None and any(rect.intersects(base_boxes[i]) for i in base_tree.query(rect)):
            stats['overlaps_base_box'] += 1
            continue
        c = np.array(rect.exterior.coords[:4])
        e1, e2 = c[1] - c[0], c[2] - c[1]
        w, d = np.linalg.norm(e1), np.linalg.norm(e2)
        yaw = math.degrees(math.atan2(e1[1], e1[0]))
        cx, cz = rect.centroid.x, rect.centroid.y

        cat = categorise(b)
        front = coastal.distance(rect.centroid) < bc['beachfront_studs']
        if cat is None:
            area_m2 = rect.area / k / k
            cat = 'hotel' if front and area_m2 > 400 else 'commercial' if area_m2 > 900 else 'shophouse' if area_m2 > 60 else 'house'
        levels = None
        try:                                           # height first ("15", "15 m", "15m")...
            if b.get('height'):
                levels = max(1, round(float(str(b['height']).replace('m', ' ').split()[0]) / bc['level_height_m']))
        except ValueError:
            pass
        if levels is None:                             # ...then building:levels, parsed on its own
            try:
                if b.get('levels'):
                    levels = max(1, round(float(str(b['levels']).split(';')[0])))
            except ValueError:
                pass
        source = 'osm'
        if levels is None:
            lo, hi = CATEGORIES[cat][0]
            if front and cat in ('hotel', 'condo', 'commercial'):
                lo, hi = lo + 4, hi + 8
            levels = rng.randint(lo, hi)
            source = 'default'
        boxes.append({'id': b['id'], 'cat': cat, 'palette': CATEGORIES[cat][1], 'levels': levels, 'levels_src': source,
                      'name': b.get('name_en') or b.get('name'), 'x': round(cx, 2), 'z': round(cz, 2), 'w': round(w, 2),
                      'd': round(d, 2), 'h': round(levels * level_studs + bc['ground_floor_extra_studs'], 2),
                      'yaw': round(yaw, 2), 'beachfront': front})
        stats['kept'] += 1

    lod = bc.get('lod')
    if lod:
        boxes = thin(boxes, lod, tree, blockers, cfg['chunk_size_studs'], level_studs, bc, stats)
    out_dir = os.path.join(ROOT, 'build', cfg['name'])
    import hashlib
    ghash = hashlib.sha1(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), 'rb').read()).hexdigest()
    json.dump({'attribution': g['attribution'], 'graph_sha1': ghash, 'level_studs': level_studs, 'buildings': boxes},
              open(os.path.join(out_dir, 'buildings_game.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print(', '.join(f'{a} {b}' for a, b in stats.most_common()))
    print('categories: ' + ', '.join(f'{a} {b}' for a, b in Counter(x['cat'] for x in boxes).most_common()))
    hs = sorted(x['h'] for x in boxes)
    print(f'height studs: median {hs[len(hs) // 2]:.0f}, p95 {hs[int(len(hs) * .95)]:.0f}, max {hs[-1]:.0f}; '
          f'levels from OSM for {sum(x["levels_src"] == "osm" for x in boxes)}')

    # check image: roads + boxes, top-down
    allp = np.array([p for e in g['edges'] for p in e['pts']])
    lo_, hi_ = allp.min(0), allp.max(0)
    s = 1600 / (hi_ - lo_).max()
    im = Image.new('RGB', (int((hi_[0] - lo_[0]) * s) + 20, int((hi_[1] - lo_[1]) * s) + 20), (235, 232, 225))
    d = ImageDraw.Draw(im)
    tr = lambda p: (10 + (p[0] - lo_[0]) * s, 10 + (p[1] - lo_[1]) * s)
    for e in g['edges']:
        d.line([tr(p) for p in e['pts']], fill=(60, 60, 70), width=max(1, int(e['width'] * s)))
    col = {'hotel': (230, 120, 60), 'condo': (200, 80, 160), 'apartment': (120, 120, 210), 'mall': (240, 200, 40),
           'commercial': (90, 170, 200), 'shophouse': (170, 150, 120), 'house': (150, 190, 120), 'temple': (220, 60, 60),
           'parking': (140, 140, 140)}
    for x in boxes:
        r = Polygon([(-x['w'] / 2, -x['d'] / 2), (x['w'] / 2, -x['d'] / 2), (x['w'] / 2, x['d'] / 2), (-x['w'] / 2, x['d'] / 2)])
        r = affinity.translate(affinity.rotate(r, x['yaw']), x['x'], x['z'])
        d.polygon([tr(p) for p in r.exterior.coords], fill=col[x['palette']])
    im.save(os.path.join(out_dir, 'buildings_check.png'))


if __name__ == '__main__':
    main(sys.argv[1])
