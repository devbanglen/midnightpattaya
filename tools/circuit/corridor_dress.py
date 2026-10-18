"""Stage E3 - roadside dressing for the Pattaya -> Bira corridor (called by export_corridor.py; no own entry point).

Everything comes from OSM or from a rule stated here (config `corridor_dress` in tools/circuit/config/bira.json):
- Buildings: OSM footprints from data/osm/raw/bira_corridor_buildings_<date>.json (query written by
  corridor_dress_query.py) whose centre is within `building_band_m` (real metres) of a road the corridor dataset builds.
  Same pipeline as tools/mapgen/buildings.py for the wide world: the city's x0.5 projection, every road corridor
  (width/2 + sidewalk + 3 studs, of the wide world AND the corridor) and every node disc cut out of the footprint, the
  minimum rotated rectangle shrunk until it clears them, category / height from OSM tags (height, building:levels) or
  the category default (capped at `default_levels_max`: the city's 8-22 storey hotel default does not fit a
  suburban strip), then the wide world's LOD (merge of small neighbours, cap per chunk). Footprints inside the
  wide world's clip polygon belong to the wide build and are skipped; boxes overlapping a wide/central box or the
  venue's terrain grid are dropped.
- Trees: a roadside row every `tree_step_studs` on both sides where the point lies inside an OSM wood / forest /
  scrub / orchard / park / garden / golf course / cemetery / grass area (a second row 22 studs further out in
  wood/forest/orchard), plus every OSM natural=tree node and natural=tree_row way (every 20 studs).
- Palms: every `palm_step_studs`, just outside the sidewalk, where the point lies inside OSM landuse=residential /
  commercial / retail (Thai housing-estate and shop frontages).
- Utility poles: every `pole_step_studs` on the driver's left of every built corridor road (kerb side of a one-way
  carriageway), `pole_offset_studs` outside the sidewalk, with a wire to the next pole on the same stretch.
- Venue approach (last km of the outbound route): "BIRA CIRCUIT 1 km" / "BIRA CIRCUIT 500 m" boards (the
  PattayaBuilder road-sign look) and one generic gantry over the road `gantry_before_venue_m` before the venue
  junction: plain text, the descriptive venue name and the placeholder sponsor "MIDNIGHT PATTAYA", no logos.
Every prop is clear of every road + sidewalk, junction disc, building, street light and sign (is_free). Items go
into separate chunk modules `chunk_d<cx>_<cz>` (id "d<cx>_<cz>", by the item's own position), so the road chunk
modules stay byte-identical and the leader only builds the new ids.
"""
import json, math, os, random, re, zlib
from collections import Counter, defaultdict
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely import affinity
from shapely.strtree import STRtree
from shapely.prepared import prep

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PALETTES = ['hotel', 'condo', 'apartment', 'mall', 'commercial', 'shophouse', 'house', 'temple', 'parking']
TREE_AREAS = {'wood', 'forest', 'scrub', 'orchard', 'park', 'garden', 'golf_course', 'cemetery', 'grass', 'grassland',
              'meadow', 'plantation', 'heath'}
DENSE = {'wood', 'forest', 'orchard', 'plantation'}
PALM_AREAS = {'residential', 'commercial', 'retail'}
FILL = {'wood': 34, 'forest': 34, 'orchard': 30, 'plantation': 30, 'park': 48, 'golf_course': 60}   # grid step, studs
CANOPY_R = 7.0          # PattayaBuilder tree canopy radius (studs); the canopy never hangs over a road or sidewalk


def h32(*a):
    return zlib.crc32('|'.join(str(x) for x in a).encode())


def venue_box(margin=16.0):
    """the venue's DEM terrain grid (roblox/data/circuits/bira.luau `ground`), map-local: nothing is placed inside"""
    src = open(os.path.join(ROOT, 'roblox', 'data', 'circuits', 'bira.luau'), encoding='utf-8').read()
    m = re.search(r'ground = \{ x0 = (-?[\d.]+), z0 = (-?[\d.]+), cell = (\d+), nx = (\d+), nz = (\d+)', src)
    x0, z0, cell, nx, nz = float(m[1]) - 20000, float(m[2]), int(m[3]), int(m[4]), int(m[5])
    return (x0 - margin, z0 - margin, x0 + cell * nx + margin, z0 + cell * nz + margin)


def box_poly(x):
    r = Polygon([(-x['w'] / 2, -x['d'] / 2), (x['w'] / 2, -x['d'] / 2), (x['w'] / 2, x['d'] / 2), (-x['w'] / 2, x['d'] / 2)])
    return affinity.translate(affinity.rotate(r, x['yaw']), x['x'], x['z'])


def load_osm(path, cfg, origin):
    raw = json.load(open(os.path.join(ROOT, path), encoding='utf-8'))
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    ox, oy = origin
    k = cfg['city_compression'] / cfg['city_meters_per_stud']

    def P(la, lo):
        x, y = tf.transform(lo, la)
        return ((x - ox) * k, -(y - oy) * k)
    out = {'osm_base': raw.get('osm3s', {}).get('timestamp_osm_base'), 'buildings': [], 'areas': [], 'trees': [], 'tree_rows': [],
           'k': k, 'P': P}
    for e in sorted(raw['elements'], key=lambda e: (e['type'], e['id'])):
        t = e.get('tags', {})
        if e['type'] == 'way' and 'geometry' in e:
            ll = [(p['lat'], p['lon']) for p in e['geometry']]
            if 'building' in t:
                out['buildings'].append({'id': e['id'], 'coords': ll, 'kind': t['building'], 'levels': t.get('building:levels'),
                                         'height': t.get('height'), 'name': t.get('name'), 'name_en': t.get('name:en'),
                                         'tourism': t.get('tourism'), 'amenity': t.get('amenity'), 'shop': t.get('shop')})
            elif t.get('natural') == 'tree_row':
                out['tree_rows'].append({'id': e['id'], 'pts': [P(*c) for c in ll]})
            elif any(x in t for x in ('landuse', 'natural', 'leisure')) and len(ll) >= 4 and ll[0] == ll[-1]:
                kind = t.get('landuse') or t.get('natural') or t.get('leisure')
                try:
                    poly = Polygon([P(*c) for c in ll]).buffer(0)
                except ValueError:
                    continue
                if not poly.is_empty:
                    out['areas'].append({'id': e['id'], 'kind': kind, 'poly': poly})
        elif e['type'] == 'node' and t.get('natural') == 'tree':
            out['trees'].append({'id': e['id'], 'xy': P(e['lat'], e['lon'])})
    return out


def build(cfg, cor, city_edges, cor_edges, sw0, city_dir, lights, signs, frame_maxx, ground_rects, C=512):
    """returns {'chunks': {id: {...}}, 'ground': [(x0, x1, z0, z1)], 'stats': {...}, 'osm_base': str}"""
    dc = cfg['corridor_dress']
    wcfg = json.load(open(os.path.join(ROOT, 'tools', 'mapgen', 'config', 'pattaya_wide.json'), encoding='utf-8'))
    bc = wcfg['buildings']
    import buildings as bmod                      # tools/mapgen (on sys.path via export_corridor)
    osm = load_osm(dc['raw'], cfg, cor['origin_utm'])
    k = osm['k']
    studs_per_m = k
    level_studs = bc['level_height_m'] * bc['vertical_scale'] / cfg['city_meters_per_stud']
    vb = venue_box()
    vpoly = Polygon([(vb[0], vb[1]), (vb[2], vb[1]), (vb[2], vb[3]), (vb[0], vb[3])])
    stats = Counter()

    # ---- obstacles -------------------------------------------------------------------------------------------------
    all_edges = city_edges + cor_edges
    cor_ids = {e['id'] for e in cor_edges}
    sw_of = lambda e: sw0[e['id']] if e['id'] in cor_ids else e['sidewalk']
    margin = bc['road_margin_studs']
    corridors = [LineString(e['pts']).buffer(e['width'] / 2 + sw_of(e) + margin, cap_style=2, join_style=1) for e in all_edges]
    widest = {}
    nodes_xy = {}
    for e in all_edges:
        for n, p in ((e['a'], e['pts'][0]), (e['b'], e['pts'][-1])):
            widest[n] = max(widest.get(n, 0), e['width'] / 2 + sw_of(e))
            nodes_xy[n] = p
    discs = [Point(*nodes_xy[n]).buffer(widest[n] + margin) for n in sorted(nodes_xy)]
    blockers = corridors + discs
    btree = STRtree(blockers)
    city_boxes = [box_poly(x) for x in bmod_city_boxes(city_dir)]
    ctree = STRtree(city_boxes)
    built_lines = [LineString(e['pts']) for e in cor_edges]
    band = unary_union([l.buffer(dc['building_band_m'] * studs_per_m) for l in built_lines])
    band_p = prep(band)
    clip = prep(Polygon([(lo, la) for la, lo in wcfg['clip_polygon_lat_lon']]))
    S, W, N, E = wcfg['slice_bbox_s_w_n_e']

    # ---- buildings (tools/mapgen/buildings.py rules) --------------------------------------------------------------
    rng = random.Random('bira_corridor_dress')
    boxes = []
    for b in osm['buildings']:
        cla = sum(c[0] for c in b['coords']) / len(b['coords']); clo = sum(c[1] for c in b['coords']) / len(b['coords'])
        if S <= cla <= N and W <= clo <= E and clip.contains(Polygon([(lo, la) for la, lo in b['coords']]).centroid):
            stats['wide_world_owns'] += 1
            continue
        try:
            poly = Polygon([osm['P'](*c) for c in b['coords']]).buffer(0)
        except ValueError:
            stats['bad'] += 1
            continue
        if poly.is_empty or not band_p.contains(poly.centroid):
            stats['outside_band'] += 1
            continue
        if poly.intersects(vpoly):
            stats['venue_terrain'] += 1
            continue
        if poly.area < bc['min_area_studs2']:
            stats['tiny'] += 1
            continue
        near = [blockers[i] for i in btree.query(poly)]
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
        for _ in range(8):
            hits = [blockers[i] for i in btree.query(rect)]
            if not any(rect.intersects(h) and rect.intersection(h).area > 0.5 for h in hits):
                ok = True
                break
            rect = affinity.scale(rect, 0.88, 0.88, origin=rect.centroid)
        if not ok or rect.area < bc['min_area_studs2']:
            stats['no_fit'] += 1
            continue
        if any(rect.intersects(city_boxes[i]) for i in ctree.query(rect)):
            stats['overlaps_city_box'] += 1
            continue
        c = np.array(rect.exterior.coords[:4])
        e1, e2 = c[1] - c[0], c[2] - c[1]
        cat = bmod.categorise(b)
        if cat is None:
            area_m2 = rect.area / k / k
            cat = 'commercial' if area_m2 > 900 else 'shophouse' if area_m2 > 60 else 'house'
        levels = None
        try:
            if b.get('height'):
                levels = max(1, round(float(str(b['height']).replace('m', ' ').split()[0]) / bc['level_height_m']))
        except ValueError:
            pass
        if levels is None:
            try:
                if b.get('levels'):
                    levels = max(1, round(float(str(b['levels']).split(';')[0])))
            except ValueError:
                pass
        src = 'osm'
        if levels is None:
            lo, hi = bmod.CATEGORIES[cat][0]
            levels = min(rng.randint(lo, hi), dc['default_levels_max'])   # suburban / rural strip: no default towers
            src = 'default'
        boxes.append({'id': b['id'], 'cat': cat, 'palette': bmod.CATEGORIES[cat][1], 'levels': levels, 'levels_src': src,
                      'name': b.get('name_en') or b.get('name'), 'x': round(rect.centroid.x, 2), 'z': round(rect.centroid.y, 2),
                      'w': round(float(np.linalg.norm(e1)), 2), 'd': round(float(np.linalg.norm(e2)), 2),
                      'h': round(levels * level_studs + bc['ground_floor_extra_studs'], 2),
                      'yaw': round(math.degrees(math.atan2(e1[1], e1[0])), 2), 'beachfront': False})
        stats['kept'] += 1
    # overlapping OSM footprints (duplicates / nested parts): keep the bigger box
    boxes.sort(key=lambda x: (-x['w'] * x['d'], x['id']))
    keep, kp = [], []
    for x in boxes:
        p = box_poly(x)
        if any(p.intersects(q) and p.intersection(q).area > 0.5 for q in kp):
            stats['overlaps_other_footprint'] += 1
            continue
        keep.append(x); kp.append(p)
    boxes = sorted(keep, key=lambda x: x['id'])
    lod = dict(bc.get('lod', {}), max_per_chunk=dc['max_building_parts_per_chunk'])
    boxes = bmod.thin(boxes, lod, btree, blockers, C, level_studs, bc, stats)
    boxes.sort(key=lambda x: x['id'])
    bpolys = [box_poly(x) for x in boxes]

    # ---- prop obstacles: roads + sidewalks (+1.5), junction discs, every building, lights, signs --------------------
    road_polys = [LineString(e['pts']).buffer(e['width'] / 2 + sw_of(e) + 1.5) for e in all_edges]
    road_polys += [Point(*nodes_xy[n]).buffer(widest[n] + 1.5) for n in sorted(nodes_xy)]
    rtree = STRtree(road_polys)
    solid = bpolys + city_boxes
    solid += [Point(x, z).buffer(3.0) for x, z, *_ in lights] + [Point(s[0], s[1]).buffer(4.0) for s in signs]
    for d in sorted({city_dir, os.path.join(ROOT, 'build', 'central_pattaya')}):    # the city's palms / lights / signs
        fp = os.path.join(d, 'layout.json')
        if os.path.exists(fp):
            lay = json.load(open(fp, encoding='utf-8'))
            solid += [Point(q['x'], q['z']).buffer(3.0) for kind in ('palms', 'lights', 'signs') for q in lay.get(kind, [])
                      if 'x' in q and q['x'] > frame_maxx - 6000]
    placed = []                      # props placed so far (circles), rebuilt into a tree lazily

    def free(x, z, r_road, r_solid):
        if vpoly.contains(Point(x, z)):
            return False
        c = Point(x, z).buffer(r_road)
        if any(road_polys[i].intersects(c) for i in rtree.query(c)):
            return False
        c2 = Point(x, z).buffer(r_solid)
        if any(solid[i].intersects(c2) for i in stree.query(c2)):
            return False
        return all((x - px) ** 2 + (z - pz) ** 2 > (pr + r_solid) ** 2 for px, pz, pr in near_placed(x, z))

    grid = defaultdict(list)

    def near_placed(x, z):
        gx, gz = int(x // 64), int(z // 64)
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                yield from grid[(gx + i, gz + j)]

    def place(x, z, r):
        grid[(int(x // 64), int(z // 64))].append((x, z, r))

    stree = STRtree(solid)
    areas = osm['areas']
    atree = STRtree([a['poly'] for a in areas])

    def area_at(x, z, near=0.0):
        """OSM area kinds at (x, z), or within `near` studs of it; inside water nothing grows (empty list)"""
        p = Point(x, z)
        q = p.buffer(near) if near else p
        kinds = [areas[i]['kind'] for i in atree.query(q) if (areas[i]['poly'].intersects(q) if near else areas[i]['poly'].contains(p))]
        if any(areas[i]['kind'] == 'water' and areas[i]['poly'].contains(p) for i in atree.query(p)):
            return []
        return kinds

    def walk(e, step, start):
        ln = LineString(e['pts'])
        s = start
        while s < ln.length - 1:
            p = ln.interpolate(s); q = ln.interpolate(min(s + 2, ln.length))
            if q.distance(p) < 1e-6:
                break
            t = np.array([q.x - p.x, q.y - p.y]); t /= np.linalg.norm(t)
            yield s, np.array([p.x, p.y]), t, np.array([-t[1], t[0]])
            s += step

    # utility poles: driver's left (Thailand drives on the left), outside the sidewalk, wired to the next pole
    poles = []
    for e in sorted(cor_edges, key=lambda e: e['id']):
        if LineString(e['pts']).length < 60:
            continue
        run = []
        for s, p, t, nrm in walk(e, dc['pole_step_studs'], dc['pole_step_studs'] / 4):
            pos = p - nrm * (e['width'] / 2 + e['sidewalk'] + dc['pole_offset_studs'])
            if free(pos[0], pos[1], 0.8, 1.0):
                run.append((t, pos))
                place(pos[0], pos[1], 1.0)
            else:
                stats['pole_blocked'] += 1
                run.append(None)
        for i, it in enumerate(run):
            if it is None:
                continue
            nxt = run[i + 1] if i + 1 < len(run) else None
            d = (nxt[1] - it[1]) if nxt is not None else None
            L = float(np.linalg.norm(d)) if d is not None else 0.0
            if 0 < L <= dc['pole_step_studs'] * 1.6:
                ax, az, wire = d[0] / L, d[1] / L, L       # wire to the next pole
            else:
                ax, az, wire = it[0][0], it[0][1], 0.0     # last pole of a run: crossarm across the road tangent
            poles.append((round(it[1][0], 1), round(it[1][1], 1), round(float(ax), 3), round(float(az), 3), round(wire, 1)))

    # trees (OSM green areas, tree nodes, tree rows) and palms (residential / commercial landuse)
    trees, palms = [], []
    lo_off, hi_off = dc['tree_offset_studs']
    for e in sorted(cor_edges, key=lambda e: e['id']):
        kerb = e['width'] / 2 + e['sidewalk']
        for s, p, t, nrm in walk(e, dc['tree_step_studs'], dc['tree_step_studs'] / 2):
            for sd in (1, -1):
                o = lo_off + h32(e['id'], round(s), sd) % (hi_off - lo_off + 1)
                for row in (0, 22):
                    pos = p + nrm * sd * (kerb + o + row)
                    kinds = area_at(*pos)
                    if not any(kd in TREE_AREAS for kd in kinds) or (row and not any(kd in DENSE for kd in kinds)):
                        continue
                    if free(pos[0], pos[1], CANOPY_R, 2.0):
                        trees.append((round(pos[0], 1), round(pos[1], 1), h32('t', round(pos[0]), round(pos[1])) % 4))
                        place(pos[0], pos[1], 2.0)
                    else:
                        stats['tree_blocked'] += 1
        for s, p, t, nrm in walk(e, dc['palm_step_studs'], dc['palm_step_studs'] / 3):
            for sd in (1, -1):
                pos = p + nrm * sd * (kerb + 6)
                if any(kd in PALM_AREAS for kd in area_at(*pos, near=dc['palm_near_studs'])) and band_p.contains(Point(*pos)):
                    if free(pos[0], pos[1], 3.0, 2.0):
                        palms.append((round(pos[0], 1), round(pos[1], 1)))
                        place(pos[0], pos[1], 2.0)
                    else:
                        stats['palm_blocked'] += 1
    # woods behind the roadside row: a jittered grid inside wood / forest / orchard / park / golf course, up to
    # `tree_fill_depth_studs` beyond the kerb (a belt along the road, not the whole forest)
    belt = unary_union([LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'] + dc['tree_fill_depth_studs']) for e in cor_edges])
    for a in sorted(areas, key=lambda a: a['id']):
        if a['kind'] not in FILL:
            continue
        reg = a['poly'].intersection(belt)
        if reg.is_empty:
            continue
        g = FILL[a['kind']]
        x0, z0, x1, z1 = reg.bounds
        rp = prep(reg)
        for gx in range(int(x0 // g), int(x1 // g) + 1):
            for gz in range(int(z0 // g), int(z1 // g) + 1):
                hh = h32(a['id'], gx, gz)
                x, z = gx * g + (hh % 1000) / 1000 * g, gz * g + (hh // 1000 % 1000) / 1000 * g
                if rp.contains(Point(x, z)) and area_at(x, z) and free(x, z, CANOPY_R, 2.5):
                    trees.append((round(x, 1), round(z, 1), hh % 4)); place(x, z, 2.5); stats['fill_trees'] += 1
    for tr in osm['trees']:
        x, z = tr['xy']
        if band_p.contains(Point(x, z)) and free(x, z, CANOPY_R, 2.0):
            trees.append((round(x, 1), round(z, 1), tr['id'] % 4)); place(x, z, 2.0); stats['osm_tree_nodes'] += 1
    for row in osm['tree_rows']:
        ln = LineString(row['pts'])
        s = 0.0
        while s <= ln.length:
            p = ln.interpolate(s)
            if band_p.contains(p) and free(p.x, p.y, CANOPY_R, 2.0):
                trees.append((round(p.x, 1), round(p.y, 1), h32(row['id'], round(s)) % 4)); place(p.x, p.y, 2.0)
            s += 20

    # ---- venue approach: boards at 1 km / 500 m and a gantry before the venue junction ------------------------------
    road_signs, gantries = approach(cfg, cor, dc, free, place, road_polys, rtree, stats)

    # ---- chunks + budget ---------------------------------------------------------------------------------------------
    chunks = defaultdict(lambda: {'buildings': [], 'palms': [], 'trees': [], 'poles': [], 'roadSigns': [], 'gantries': []})
    cid = lambda x, z: f'd{int(math.floor(x / C))}_{int(math.floor(z / C))}'
    for b in boxes:
        chunks[cid(b['x'], b['z'])]['buildings'].append(b)
    for kind, items in (('palms', palms), ('trees', trees), ('poles', poles), ('roadSigns', road_signs), ('gantries', gantries)):
        for it in items:
            chunks[cid(it[0], it[1])][kind].append(it)

    def parts(ch):
        return (sum(1 + (b['h'] > 30) for b in ch['buildings']) + 6 * len(ch['palms']) + 2 * len(ch['trees'])
                + sum(2 + (p[4] > 0) for p in ch['poles']) + 2 * len(ch['roadSigns']) + 5 * len(ch['gantries']))
    cap = dc['max_parts_per_chunk']
    for i in sorted(chunks):
        ch = chunks[i]
        while parts(ch) > cap and ch['trees']:          # thin trees first (deterministic: every other one)
            ch['trees'] = ch['trees'][::2] if len(ch['trees']) > 1 else []
            stats['trees_thinned_for_budget'] += 1
        while parts(ch) > cap and ch['palms']:
            ch['palms'] = ch['palms'][::2] if len(ch['palms']) > 1 else []
            stats['palms_thinned_for_budget'] += 1
    total = sum(parts(c) for c in chunks.values())
    assert total <= dc['max_total_parts'], f'dressing {total} parts > budget {dc["max_total_parts"]}'
    out = {}
    for i in sorted(chunks, key=lambda s: tuple(int(v) for v in s[1:].split('_'))):
        ch = chunks[i]
        ch['parts'] = parts(ch)
        out[i] = ch

    # ---- terrain under the dressing where neither the wide frame, the corridor strips nor the venue has ground ------
    ground = dress_ground(out, frame_maxx, ground_rects, vb)

    # ---- export-time overlap check (shapely): 0 building / prop footprints touching a road part ----------------------
    slabs = [LineString(e['pts']).buffer(e['width'] / 2 + sw_of(e)) for e in all_edges]
    slabs += [Point(*nodes_xy[n]).buffer(widest[n]) for n in sorted(nodes_xy)]
    stree2 = STRtree(slabs)
    fin = [box_poly(b) for c in out.values() for b in c['buildings']]
    hit_b = sum(any(slabs[j].intersects(p) for j in stree2.query(p)) for p in fin)
    props_xy = [(t[0], t[1], 1.2) for c in out.values() for t in c['trees']] + [(p[0], p[1], 0.8) for c in out.values() for p in c['palms']] + \
               [(p[0], p[1], 0.4) for c in out.values() for p in c['poles']]
    hit_p = 0
    for x, z, r in props_xy:
        q = Point(x, z).buffer(r)
        hit_p += any(slabs[j].intersects(q) for j in stree2.query(q))
    ftree = STRtree(fin)
    hit_bb = sum(1 for i, p in enumerate(fin) for j in ftree.query(p) if j > i and p.intersection(fin[j]).area > 0.5)
    hit_city = sum(any(p.intersects(city_boxes[j]) for j in ctree.query(p)) for p in fin)
    stats.update({'check_buildings_on_road': hit_b, 'check_props_on_road': hit_p, 'check_building_overlaps': hit_bb,
                  'check_overlaps_city_buildings': hit_city})
    assert hit_b == 0 and hit_p == 0 and hit_bb == 0 and hit_city == 0, 'dressing overlaps a road or building'
    return {'chunks': out, 'ground': ground, 'stats': stats, 'osm_base': osm['osm_base'], 'total_parts': total}


def bmod_city_boxes(city_dir):
    out = []
    for d in sorted({city_dir, os.path.join(ROOT, 'build', 'central_pattaya')}):
        fp = os.path.join(d, 'buildings_game.json')
        if os.path.exists(fp):
            out += json.load(open(fp, encoding='utf-8'))['buildings']
    return out


def approach(cfg, cor, dc, free, place, road_polys, rtree, stats):
    from corridor_traffic import directed_path, path_polyline
    full = json.load(open(os.path.join(ROOT, 'build', 'bira', 'corridor_graph_game.json'), encoding='utf-8'))
    E = full['edges']           # unmodified (export_corridor cuts one edge in place for the wide dedupe)
    J0, J1 = cor['join_nodes']['city'], cor['join_nodes']['facility']
    m_per_stud = cor['meters_per_stud'] / cor['compression']
    pts, owner = path_polyline(E, directed_path(E, J0, J1))
    cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    total = cum[-1]

    def at(s):
        k = max(0, min(int(np.searchsorted(cum, s)) - 1, len(pts) - 2))
        f = (s - cum[k]) / max(cum[k + 1] - cum[k], 1e-9)
        p = pts[k] + (pts[k + 1] - pts[k]) * f
        t = (pts[k + 1] - pts[k]) / np.linalg.norm(pts[k + 1] - pts[k])
        return p, t, E[owner[k + 1]]
    signs = []
    for km in dc['approach_km']:
        p, t, e = at(total - km * 1000 / m_per_stud)
        left = np.array([t[1], -t[0]])
        label = f"{dc['approach_text']} {km:g} km" if km >= 1 else f"{dc['approach_text']} {km * 1000:.0f} m"
        for extra in (3, 6, 10, 15):
            pos = p + left * (e['width'] / 2 + e['sidewalk'] + extra)
            if free(pos[0], pos[1], 1.0, 3.0):
                signs.append((round(pos[0], 1), round(pos[1], 1), round(t[0], 3), round(t[1], 3), label))
                place(pos[0], pos[1], 3.0)
                break
        else:
            stats['approach_sign_skipped'] += 1
    gantries = []
    s0 = total - dc['gantry_before_venue_m'] / m_per_stud
    for ds in [0] + [d * sg for d in range(20, 301, 20) for sg in (-1, 1)]:
        p, t, e = at(s0 + ds)
        left = np.array([t[1], -t[0]])
        L = next((o for o in np.arange(e['width'] / 2 + e['sidewalk'] + 3, e['width'] / 2 + e['sidewalk'] + 16, 1.5)
                  if free(*(p + left * o), 1.0, 2.0)), None)
        R = next((o for o in np.arange(e['width'] / 2 + 3, 90, 1.5) if free(*(p - left * o), 1.0, 2.0)), None)
        if L is None or R is None:
            continue
        a, b = p + left * L, p - left * R
        mid = (a + b) / 2
        # the beam's line must only cross road (no building / sign between the posts): free() at the posts is enough
        # because everything else near the road was placed outside the sidewalk band.
        gantries.append((round(mid[0], 1), round(mid[1], 1), round(t[0], 3), round(t[1], 3), round(float(L + R), 1),
                         dc['gantry_text'], dc['gantry_sub_text']))
        place(a[0], a[1], 2.0); place(b[0], b[1], 2.0)
        stats['gantry_shift_studs'] = ds
        break
    else:
        stats['gantry_skipped'] += 1
    return signs, gantries


def dress_ground(chunks, frame_maxx, ground_rects, vb, cell=64):
    """64-stud cells under every dressing item (+ 24 studs), skipping cells inside the wide frame (x < frame_maxx),
    inside one existing corridor ground strip, or touching the venue terrain box; merged into row runs, then runs
    with the same x span stacked into rectangles."""
    cells = set()

    def mark(x0, z0, x1, z1):
        for gx in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
            for gz in range(int(math.floor(z0 / cell)), int(math.floor(z1 / cell)) + 1):
                cells.add((gx, gz))
    for ch in chunks.values():
        for b in ch['buildings']:
            r = math.hypot(b['w'], b['d']) / 2 + 24
            mark(b['x'] - r, b['z'] - r, b['x'] + r, b['z'] + r)
        for kind in ('palms', 'trees', 'poles', 'roadSigns', 'gantries'):
            for it in ch[kind]:
                r = 24 + (it[4] / 2 if kind == 'gantries' else 0)
                mark(it[0] - r, it[1] - r, it[0] + r, it[1] + r)

    def covered(gx, gz):
        x0, z0, x1, z1 = gx * cell, gz * cell, gx * cell + cell, gz * cell + cell
        if x1 <= frame_maxx:
            return True
        if x1 > vb[0] and x0 < vb[2] and z1 > vb[1] and z0 < vb[3]:
            return True
        return any(a <= x0 and x1 <= b and c <= z0 and z1 <= d for a, b, c, d in ground_rects)
    keep = sorted(c for c in cells if not covered(*c))
    rows = defaultdict(list)
    for gx, gz in keep:
        rows[gz].append(gx)
    runs = []
    for gz in sorted(rows):
        xs = sorted(rows[gz])
        st = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            runs.append((st, prev, gz))
            if x is not None:
                st = prev = x
    rects = {}
    for st, en, gz in runs:
        key = (st, en, gz - 1)
        if key in rects:
            z0 = rects.pop(key)
            rects[(st, en, gz)] = z0
        else:
            rects[(st, en, gz)] = gz
    out = []
    for (st, en, gz1), gz0 in sorted(rects.items(), key=lambda kv: (kv[1], kv[0][0])):
        out.append((max(st * cell, frame_maxx), (en + 1) * cell, gz0 * cell, (gz1 + 1) * cell))
    return out


def check_image(path, cor_edges, city_edges, dress, areas_src=None, crops=None):
    """top-down check image: roads grey, buildings by palette colour, trees green, palms lime, poles black,
    approach signs / gantry red. `crops` = [(x0, z0, x1, z1)] writes zoomed copies next to it (_1.png, ...)."""
    from PIL import Image, ImageDraw
    xs = [p[0] for e in cor_edges for p in e['pts']]; zs = [p[1] for e in cor_edges for p in e['pts']]
    full = (min(xs) - 300, min(zs) - 300, max(xs) + 300, max(zs) + 300)
    col = {'hotel': (230, 120, 60), 'condo': (200, 80, 160), 'apartment': (120, 120, 210), 'mall': (240, 200, 40),
           'commercial': (90, 170, 200), 'shophouse': (170, 150, 120), 'house': (150, 190, 120), 'temple': (220, 60, 60),
           'parking': (140, 140, 140)}
    for n, (x0, z0, x1, z1) in enumerate([full] + list(crops or [])):
        s = (4000 if n == 0 else 1600) / (x1 - x0)
        im = Image.new('RGB', (int((x1 - x0) * s) + 1, int((z1 - z0) * s) + 1), (235, 232, 225))
        d = ImageDraw.Draw(im)
        tr = lambda p: ((p[0] - x0) * s, (p[1] - z0) * s)
        for e in city_edges + cor_edges:
            if max(p[0] for p in e['pts']) < x0 or min(p[0] for p in e['pts']) > x1:
                continue
            d.line([tr(p) for p in e['pts']], fill=(60, 60, 70) if e in cor_edges else (130, 130, 140), width=max(1, int(e['width'] * s)))
        r = max(1.0, 3 * s)
        for ch in dress['chunks'].values():
            for b in ch['buildings']:
                d.polygon([tr(p) for p in box_poly(b).exterior.coords], fill=col[b['palette']], outline=(0, 0, 0))
            for x, z, _ in ch['trees']:
                d.ellipse([tr((x - CANOPY_R, z - CANOPY_R)), tr((x + CANOPY_R, z + CANOPY_R))], fill=(40, 130, 50))
            for x, z in ch['palms']:
                d.ellipse([tr((x - 5, z - 5)), tr((x + 5, z + 5))], fill=(150, 210, 40))
            for x, z, ax, az, w in ch['poles']:
                d.ellipse([tr((x - 1.5, z - 1.5)), tr((x + 1.5, z + 1.5))], fill=(0, 0, 0))
                if w:
                    d.line([tr((x, z)), tr((x + ax * w, z + az * w))], fill=(0, 0, 0), width=1)
            for it in ch['roadSigns'] + ch['gantries']:
                d.ellipse([tr((it[0] - 8, it[1] - 8)), tr((it[0] + 8, it[1] + 8))], fill=(220, 30, 30))
        im.save(path if n == 0 else path.replace('.png', f'_{n}.png'))
