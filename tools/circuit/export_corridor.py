"""Stage E - city -> Bira access corridor as a PattayaBuilder.Extend() dataset, plus the merged runtime road graph.

  .venv\\Scripts\\python tools\\circuit\\export_corridor.py tools\\circuit\\config\\bira.json

Inputs: build/bira/corridor_graph_game.json (access_corridor.py), build/central_pattaya/graph_game.json and
build/central_pattaya/roblox/manifest.luau (the tested slice; nothing in it is changed).
Outputs (build/bira/roblox_corridor/):
  manifest.luau, chunk_<cx>_<cz>.luau   -> ServerStorage.PattayaDataCorridor, built with
                                           require(ServerStorage.PattayaBuilder).Extend({folder = "PattayaDataCorridor"})
  graph.luau                             -> replaces ServerStorage.PattayaData.graph: the city graph first (same node
                                           and edge order as before, so nothing tested moves), then the corridor;
                                           baseNodes/baseEdges mark the split so routes never pick corridor nodes as
                                           sprint or boss destinations (PattayaRoute).
Ground: flat terrain strips along the corridor (groundRects), clipped to stay outside the slice frame and the venue.
"""
import json, math, os, re, sys
from collections import defaultdict
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'mapgen'))
from export_roblox import douglas_peucker, split_long, lua_str, LineString_len, DP_TOLERANCE, MAX_SEGMENT  # noqa: E402


def road_tree(edges, margin, buildings=()):
    """obstacles for props: every road (width/2 + margin) and the city's building boxes"""
    from shapely.geometry import LineString, Polygon
    from shapely import affinity
    from shapely.strtree import STRtree
    polys = [LineString(e['pts']).buffer(e['width'] / 2 + margin) for e in edges]
    for b in buildings:
        r = Polygon([(-b['w'] / 2, -b['d'] / 2), (b['w'] / 2, -b['d'] / 2), (b['w'] / 2, b['d'] / 2), (-b['w'] / 2, b['d'] / 2)])
        polys.append(affinity.translate(affinity.rotate(r, b['yaw']), b['x'], b['z']))
    return polys, STRtree(polys)


def city_buildings(city_dir):
    out = []
    for d in {city_dir, os.path.join(ROOT, 'build', 'central_pattaya')}:
        fp = os.path.join(d, 'buildings_game.json')
        if os.path.exists(fp):
            out += json.load(open(fp, encoding='utf-8'))['buildings']
    return out


def is_free(polys, tree, x, z, r):
    from shapely.geometry import Point
    c = Point(x, z).buffer(r)
    return not any(polys[i].intersects(c) for i in tree.query(c))


def corridor_lights(step, city_edges, cor_edges, signs, buildings):
    """street lights along the corridor's main / express roads: the city layout rule (tools/mapgen/gameplay_layout.py:
    every `step` studs, width/2 + sidewalk/2 (or 4) from the centreline, facing the road, clear of every road by 1.5 +
    1 studs and of every building). Two-way roads get both sides; a one-way edge (one carriageway of a dual road) only its kerb side (left of
    travel; Thailand drives on the left), so the median is not lit twice. Returns {edge id: [(x, z, dx, dz)]}."""
    from shapely.geometry import LineString
    polys, tree = road_tree(city_edges + cor_edges, 1.5, buildings)
    out = defaultdict(list)
    for e in cor_edges:
        if e['tier'] not in ('main', 'express'):
            continue
        ln = LineString(e['pts'])
        if ln.length < 30:
            continue
        off = e['width'] / 2 + (e['sidewalk'] / 2 if e['sidewalk'] >= 4 else 4)
        s = step / 2
        while s < ln.length - step / 3:
            p = ln.interpolate(s); q = ln.interpolate(min(s + 2, ln.length))
            t = np.array([q.x - p.x, q.y - p.y]); t /= (np.linalg.norm(t) + 1e-9)
            nrm = np.array([-t[1], t[0]])                 # right of travel; left = -nrm
            for sd in ([-1] if e['oneway'] else [1, -1]):
                pos = np.array([p.x, p.y]) + nrm * sd * off
                if is_free(polys, tree, pos[0], pos[1], 1.0) and all(math.hypot(pos[0] - x, pos[1] - z) > 10 for x, z, *_ in signs):
                    out[e['id']].append((round(pos[0], 2), round(pos[1], 2), round(-nrm[0] * sd, 3), round(-nrm[1] * sd, 3)))
            s += step
    return out


def corridor_signs(sc, city_edges, cor_edges, bira_dir, buildings):
    """direction signs at given REAL distances (km) before the end of the outbound route (to the venue junction) and
    of the return route (to the city join): on the driver's left, outside the sidewalk, only on stretches the corridor
    dataset builds (the city part has its own streets). Returns [(x, z, dx, dz, text)]."""
    from corridor_traffic import directed_path, path_polyline
    full = json.load(open(os.path.join(bira_dir, 'corridor_graph_game.json'), encoding='utf-8'))
    E = full['edges']
    J0, J1 = full['join_nodes']['city'], full['join_nodes']['facility']
    m_per_stud = full['meters_per_stud'] / full['compression']
    from shapely.geometry import LineString, Point
    built = [LineString(e['pts']) for e in cor_edges]     # what the corridor dataset builds (after the wide dedupe)
    polys, tree = road_tree(city_edges + cor_edges, 1.5, buildings)
    out = []
    for src, dst, text, kms in ((J0, J1, sc['outbound_text'], sc['outbound_km']), (J1, J0, sc['return_text'], sc['return_km'])):
        pts, owner = path_polyline(E, directed_path(E, src, dst))
        cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
        total = cum[-1]
        for km in kms:
            s = total - km * 1000 / m_per_stud
            if s <= 0:
                print(f'  sign "{text} {km} km": route is only {total * m_per_stud / 1000:.1f} km, skipped')
                continue
            k = int(np.searchsorted(cum, s)) - 1
            e = E[owner[k + 1]]
            f = (s - cum[k]) / (cum[k + 1] - cum[k])
            p = pts[k] + (pts[k + 1] - pts[k]) * f
            if min(l.distance(Point(*p)) for l in built) > 1:
                print(f'  sign "{text} {km} km": on {e["name_en"]} in the city part (built by the wide world), skipped')
                continue
            t = (pts[k + 1] - pts[k]) / np.linalg.norm(pts[k + 1] - pts[k])
            left = np.array([t[1], -t[0]])
            for extra in (3, 6, 10, 15):
                pos = p + left * (e['width'] / 2 + e['sidewalk'] + extra)
                if is_free(polys, tree, pos[0], pos[1], 1.0):
                    out.append((round(pos[0], 1), round(pos[1], 1), round(t[0], 3), round(t[1], 3), f'{text} {km} km'))
                    break
            else:
                print(f'  sign "{text} {km} km": no free spot beside {e["name_en"]}, skipped')
    return out


def frame_max_x_wide(city_dir, slice_frame):
    """east edge of the terrain the city build lays (the wide manifest's `frame`, else the slice frame)"""
    src = open(os.path.join(city_dir, 'roblox', 'manifest.luau'), encoding='utf-8').read()
    m = re.search(r'\n  frame = \{ minX = -?[\d.]+, maxX = (-?[\d.]+)', src)
    return float(m.group(1)) if m else slice_frame['maxX']


def main(cfg_path, city_build='build/central_pattaya'):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    C = 512
    city_dir = os.path.join(ROOT, city_build)   # the slice, or the wide world (edges flagged base=true stay first)
    bira_dir = os.path.join(ROOT, 'build', 'bira')
    out_dir = os.path.join(bira_dir, 'roblox_corridor')
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.startswith('chunk_') or f in ('manifest.luau', 'graph.luau', 'joints.luau'):
            os.remove(os.path.join(out_dir, f))
    city = json.load(open(os.path.join(city_dir, 'graph_game.json'), encoding='utf-8'))
    cor = json.load(open(os.path.join(bira_dir, 'corridor_graph_game.json'), encoding='utf-8'))
    assert cor['origin_utm'] == city['origin_utm'] and cor['compression'] == city['compression'], 'corridor/city transform differ'
    man_src = open(os.path.join(city_dir, 'roblox', 'manifest.luau'), encoding='utf-8').read()
    frame = {k: float(v) for k, v in re.findall(r'(minX|maxX|minZ|maxZ) = (-?[\d.]+)', man_src.split('frame = ')[1].split('}')[0])}
    dash_gap = int(re.search(r'dashGap = (\d+)', man_src).group(1)) if 'dashGap' in man_src else 12

    city_edges, cor_edges = city['edges'], cor['edges']
    wide = any(e.get('base') for e in city_edges)
    if wide:   # wide world: the tested slice's edges first (same order as its own export), then the new districts
        city_edges = [e for e in city_edges if e.get('base')] + [e for e in city_edges if not e.get('base')]
    base_edges = [e for e in city_edges if e.get('base')] if wide else city_edges
    city_nodes = set(n for e in city_edges for n in (e['a'], e['b']))
    nodes_xy = dict(city['nodes']); nodes_xy.update(cor['nodes'])
    cor_nodes = set(n for e in cor_edges for n in (e['a'], e['b']))
    joins = sorted(city_nodes & cor_nodes)
    print(f'corridor: {len(cor_edges)} edges, {len(cor_nodes)} nodes, joins with the city at {joins}')

    # Wide world: the corridor's city-side stretch (Pattaya Klang, Sukhumvit) is already part of the wide graph.
    # Drop corridor edges with both ends in the city graph; cut an edge that leaves the city graph where the city's
    # own copy of that way ends (the wide graph stops a road at its bbox / pruning point, not at a corridor node).
    if wide:
        way_nodes = defaultdict(set)
        for e in city_edges:
            way_nodes[e['way']].update((e['a'], e['b']))
        kept = []
        for e in cor_edges:
            a_in, b_in = e['a'] in city_nodes, e['b'] in city_nodes
            if a_in and b_in:
                continue
            if a_in != b_in:
                pts = np.array(e['pts'])
                inside_end = e['a'] if a_in else e['b']
                best = None   # (arc position, node) of the city node on this way that lies on the corridor polyline
                for n in way_nodes.get(e['way'], ()):
                    xy = np.array(nodes_xy[str(n)]) if str(n) in nodes_xy else None
                    if xy is None:
                        continue
                    d = np.linalg.norm(pts - xy, axis=1)
                    k = int(d.argmin())
                    if d[k] < 3 and n != inside_end:
                        arc = k if a_in else len(pts) - 1 - k
                        if best is None or arc > best[0]:
                            best = (arc, n, k)
                if best:
                    _, n, k = best
                    if a_in:
                        e['pts'] = [list(nodes_xy[str(n)])] + pts[k + 1:].tolist(); e['a'] = n
                    else:
                        e['pts'] = pts[:k].tolist() + [list(nodes_xy[str(n)])]; e['b'] = n
                    print(f"  corridor edge {e['id']} cut at city node {n} (city already has the way up to there)")
            kept.append(e)
        dropped = len(cor_edges) - len(kept)
        cor_edges = kept
        cor_nodes = set(n for e in cor_edges for n in (e['a'], e['b']))
        joins = sorted(city_nodes & cor_nodes)
        print(f'  wide dedupe: dropped {dropped} corridor edges already in the city graph; corridor now {len(cor_edges)} edges, joins at {joins}')

    # junction discs: new ones where the combined degree reaches 3 and the city had none; seam ones keep the city radius
    deg, base_deg = defaultdict(int), defaultdict(int)
    for e in city_edges + cor_edges:
        deg[e['a']] += 1; deg[e['b']] += 1
    for e in city_edges:
        base_deg[e['a']] += 1; base_deg[e['b']] += 1
    radius, base_radius = defaultdict(float), defaultdict(float)
    for e in city_edges + cor_edges:
        for n in (e['a'], e['b']):
            radius[n] = max(radius[n], e['width'] / 2)
    for e in city_edges:
        for n in (e['a'], e['b']):
            if base_deg[n] >= 3:
                base_radius[n] = max(base_radius[n], e['width'] / 2)
    touched = cor_nodes
    new_discs = {n: radius[n] for n in touched if deg[n] >= 3 and base_deg[n] < 3}
    seam_discs = {n: base_radius[n] for n in touched if base_deg[n] >= 3}
    # joint discs at degree-1/2 nodes (same rule as export_roblox.main_wide; joints.luau, they trim nothing)
    min_half = {}
    for e in city_edges + cor_edges:
        for n in (e['a'], e['b']):
            min_half[n] = min(min_half.get(n, 1e9), e['width'] / 2)
    joints = {n: min_half[n] for n in touched if deg[n] <= 2}

    sw0 = {e['id']: e['sidewalk'] for e in cor_edges}   # OSM-rule sidewalks, for the dressing's clearance (corridor_dress)
    # dual carriageways (paired one-way edges, e.g. Thammasat Rd) sit so close at x0.5 that each one's sidewalk would lie
    # on the other's roadway (252 of 1,385 probes hit a sidewalk in Studio): corridor one-ways get no sidewalk
    for e in cor_edges:
        if e['oneway']:
            e['sidewalk'] = 0
    chunks = defaultdict(list)
    seg_total = 0
    edge_chunk = {}
    for e in cor_edges:
        q = split_long(douglas_peucker(np.array(e['pts']), DP_TOLERANCE), MAX_SEGMENT)
        seg_total += len(q) - 1
        mid = q[len(q) // 2]
        cid = (int(math.floor(mid[0] / C)), int(math.floor(mid[1] / C)))
        chunks[cid].append((e, q))
        edge_chunk[e['id']] = cid
    life = cfg.get('corridor_life', {})
    blds = city_buildings(city_dir) if life else []
    signs = corridor_signs(life['signs'], city_edges, cor_edges, bira_dir, blds) if life.get('signs') else []
    lights = corridor_lights(life['light_spacing_studs'], city_edges, cor_edges, signs, blds) if life.get('light_spacing_studs') else {}
    for (cx, cz), items in sorted(chunks.items()):
        ll = [p for e, _ in items for p in lights.get(e['id'], [])]
        lines = [f'-- generated by tools/circuit/export_corridor.py from OSM ({cor["attribution"]}); do not edit',
                 f'return {{ id = "{cx}_{cz}",', '  buildings = {},', '  palms = {},',
                 '  lights = {' + ','.join(f'{x:.1f},{z:.1f},{dx:.2f},{dz:.2f}' for x, z, dx, dz in ll) + '},', '  signs = {},', '  edges = {']
        for e, q in items:
            flat = ','.join(f'{x:.2f},{z:.2f}' for x, z in q)
            lines.append(f'  {{ id = "{e["id"]}", way = {e["way"]}, class = "{e["class"]}", tier = "{e["tier"]}", '
                         f'name = {lua_str(e["name"])}, nameEn = {lua_str(e["name_en"])}, oneway = {str(e["oneway"]).lower()}, '
                         f'lanes = {e["lanes"]}, width = {e["width"]}, sidewalk = {e["sidewalk"]}, coastal = false, '
                         f'a = {e["a"]}, b = {e["b"]}, pts = {{{flat}}} }},')
        lines.append('} }')
        open(os.path.join(out_dir, f'chunk_{cx}_{cz}.luau'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    # ground strips: one rect per road segment (+ margin), outside the slice frame and short of the venue
    venue_min_x = cfg.get('venue_min_x_local', 24700)
    rects = []
    GM = 70
    for e in cor_edges:
        p = np.array(e['pts'])
        for i in range(0, len(p) - 1, 4):
            seg = p[i:i + 5]
            x0, z0 = seg.min(0) - GM; x1, z1 = seg.max(0) + GM
            x0 = max(x0, frame['maxX'])                   # never inside the tested slice (it has its own terrain)
            x1 = min(x1, venue_min_x)
            if x1 - x0 > 8 and z1 - z0 > 8:
                rects.append((x0, x1, z0, z1))
    # roadside dressing (tools/circuit/corridor_dress.py): OSM buildings + rule-based props in separate chunk modules
    # chunk_d<cx>_<cz>, so the road chunk modules above stay byte-identical
    dress = None
    if 'corridor_dress' in cfg and os.path.exists(os.path.join(ROOT, cfg['corridor_dress']['raw'])):
        import corridor_dress
        flat_lights = [p for v in lights.values() for p in v]
        dress = corridor_dress.build(cfg, cor, city_edges, cor_edges, sw0, city_dir, flat_lights, signs,
                                     frame_max_x_wide(city_dir, frame), rects, C)
        palettes = corridor_dress.PALETTES
        corridor_dress.check_image(os.path.join(bira_dir, 'corridor_dress_check.png'), cor_edges, city_edges, dress,
                                   crops=cfg['corridor_dress'].get('check_crops'))
        for did, ch in dress['chunks'].items():
            dl = [f'-- generated by tools/circuit/export_corridor.py (corridor dressing, tools/circuit/corridor_dress.py) from OSM '
                  f'(Map data (c) OpenStreetMap contributors, ODbL 1.0; OSM base {dress["osm_base"]}) and stated rules; do not edit',
                  f'return {{ id = "{did}",',
                  '  buildings = {' + ','.join(f'{b["x"]:.1f},{b["z"]:.1f},{b["w"]:.1f},{b["d"]:.1f},{b["h"]:.1f},{b["yaw"]:.1f},'
                                              f'{palettes.index(b["palette"]) + 1},{b["id"]}' for b in ch['buildings']) + '},',
                  '  palms = {' + ','.join(f'{x:.1f},{z:.1f}' for x, z in ch['palms']) + '},',
                  '  lights = {},', '  signs = {},',
                  '  -- dressing: trees {x, z, variant}, utility poles {x, z, ax, az, wire} (a = unit direction to the next pole,',
                  '  -- wire = its distance, 0 = none), road signs {x, z, dx, dz, text}, gantries {x, z, dx, dz, span, text, subText}',
                  '  trees = {' + ','.join(f'{x:.1f},{z:.1f},{v}' for x, z, v in ch['trees']) + '},',
                  '  poles = {' + ','.join(f'{x:.1f},{z:.1f},{ax:.3f},{az:.3f},{w:.1f}' for x, z, ax, az, w in ch['poles']) + '},',
                  '  roadSigns = {' + ', '.join(f'{{ {x:.1f}, {z:.1f}, {dx:.3f}, {dz:.3f}, {lua_str(t)} }}'
                                                for x, z, dx, dz, t in ch['roadSigns']) + '},',
                  '  gantries = {' + ', '.join(f'{{ {x:.1f}, {z:.1f}, {dx:.3f}, {dz:.3f}, {sp:.1f}, {lua_str(t)}, {lua_str(st)} }}'
                                               for x, z, dx, dz, sp, t, st in ch['gantries']) + '},',
                  '  edges = {},', '}']
            open(os.path.join(out_dir, f'chunk_{did}.luau'), 'w', encoding='utf-8').write('\n'.join(dl) + '\n')
    rects_lua = ',\n'.join(f'  {{ {a:.0f}, {b:.0f}, {c:.0f}, {d:.0f} }}' for a, b, c, d in rects)
    junc = ',\n'.join(f'  {{ id = {n}, x = {nodes_xy[str(n)][0]:.2f}, z = {nodes_xy[str(n)][1]:.2f}, r = {r:.2f} }}' for n, r in sorted(new_discs.items()))
    seam = ',\n'.join(f'  {{ id = {n}, x = {nodes_xy[str(n)][0]:.2f}, z = {nodes_xy[str(n)][1]:.2f}, r = {r:.2f} }}' for n, r in sorted(seam_discs.items()))
    chunk_ids = [f'"{cx}_{cz}"' for cx, cz in sorted(chunks)]
    dress_ids = [f'"{d}"' for d in dress['chunks']] if dress else []
    if dress:   # batches of <= 8 chunks (one 69-chunk Extend crashed Studio; 8-chunk calls never did)
        groups = [dress_ids[i:i + 8] for i in range(0, len(dress_ids), 8)]
        batches_lua = (f'{{ all = {{ {", ".join(chunk_ids + dress_ids)} }}, roads = {{ {", ".join(chunk_ids)} }}, '
                       + ', '.join(f'dress{k} = {{ {", ".join(g)} }}' for k, g in enumerate(groups, 1)) + ' }')
        facades = json.load(open(os.path.join(ROOT, 'tools', 'mapgen', 'config', 'facade_assets.json'), encoding='utf-8'))
        lvl = json.load(open(os.path.join(ROOT, 'tools', 'mapgen', 'config', 'pattaya_wide.json'), encoding='utf-8'))['buildings']
        dress_lua = (f'''  -- roadside dressing (chunk_d* modules): buildings from OSM; trees, palms, poles, approach signs, gantry by rule
  dressAttribution = "Buildings, landuse, trees: (c) OpenStreetMap contributors, ODbL 1.0 ({cfg['corridor_dress']['raw'].split('/')[-1]})",
  dressOsmBase = "{dress['osm_base']}",
  batchOrder = {{ {', '.join(f'"dress{k}"' for k in range(1, len(groups) + 1))} }},
  levelStuds = {lvl['level_height_m'] * lvl['vertical_scale'] / cfg['city_meters_per_stud']:.3f},
  palettes = {{ {', '.join(f'"{p}"' for p in corridor_dress.PALETTES)} }},
  facades = {{ tower = "{facades['tower']}", office = "{facades['office']}", shophouse = "{facades['shophouse']}" }},
  facadesNight = {{ tower = "{facades['tower_night']}", office = "{facades['office_night']}", shophouse = "{facades['shophouse_night']}" }},
  facadeMinHeight = {lvl.get('lod', {}).get('facade_min_height_studs', 0)},
  -- extra ground under the dressing (outside the wide frame, the strips above and the venue terrain), built with
  -- Extend({{folder = "PattayaDataCorridor", roads = false, groundKey = "dressGroundRects"}})
  dressGroundRects = {{
'''
                     + ',\n'.join(f'  {{ {a:.0f}, {b:.0f}, {c:.0f}, {d:.0f} }}' for a, b, c, d in dress['ground']) + '\n  },\n')
    else:
        batches_lua = f'{{ all = {{ {", ".join(chunk_ids)} }} }}'
        dress_lua = ''
    signs_lua = ',\n'.join(f'  {{ {x:.1f}, {z:.1f}, {dx:.3f}, {dz:.3f}, {lua_str(t)} }}' for x, z, dx, dz, t in signs)
    manifest = f'''-- generated by tools/circuit/export_corridor.py; do not edit
return {{
  name = "bira_corridor",
  attribution = "{cor['attribution']}",
  osmBase = "{cor.get('osm_base', '')}",
  chunkSize = {C},
  dashGap = {dash_gap},
  baseFrame = {{ minX = {frame['minX']:.0f}, maxX = {frame['maxX']:.0f}, minZ = {frame['minZ']:.0f}, maxZ = {frame['maxZ']:.0f} }},
  chunks = {{ {', '.join(chunk_ids + dress_ids)} }},
  batches = {batches_lua},
  junctions = {{
{junc}
  }},
  seamJunctions = {{
{seam}
  }},
  groundRects = {{
{rects_lua}
  }},
  seaCell = 16,
  sea = {{}},
  joinNodes = {{ {', '.join(str(n) for n in joins)} }},
  venueNode = {cor.get('join_nodes', {}).get('facility', 1457068485)},
  -- direction signs {{x, z, dx, dz, text}} (map-local; dx, dz = direction of travel, the board faces the drivers):
  -- built by PattayaBuilder.Extend into workspace.PattayaWorld.RoadSigns_<name>
  signs = {{
{signs_lua}
  }},
{dress_lua}}}
'''
    open(os.path.join(out_dir, 'manifest.luau'), 'w', encoding='utf-8').write(manifest)
    open(os.path.join(out_dir, 'joints.luau'), 'w', encoding='utf-8').write(
        '-- generated by tools/circuit/export_corridor.py; do not edit. Joint discs (osmNode, x, z, r) at degree-1/2 nodes\n'
        'return {' + ','.join(f'{n},{nodes_xy[str(n)][0]:.2f},{nodes_xy[str(n)][1]:.2f},{r:.2f}' for n, r in sorted(joints.items())) + '}\n')

    # merged runtime graph: city first (same order as export_roblox: sorted node ids), then the corridor
    base_ids = sorted(set(n for e in base_edges for n in (e['a'], e['b'])))
    wide_ids = sorted(city_nodes - set(base_ids))
    extra_ids = sorted(cor_nodes - city_nodes)
    all_ids = base_ids + wide_ids + extra_ids
    idx = {n: i + 1 for i, n in enumerate(all_ids)}
    tiers = {'express': 1, 'main': 2, 'soi': 3}

    def edge_line(e):
        q = douglas_peucker(np.array(e['pts']), 1.0)
        return (f'    {{ {idx[e["a"]]}, {idx[e["b"]]}, {LineString_len(q):.1f}, {tiers[e["tier"]]}, {e["width"]}, '
                f'{{{",".join(f"{x:.1f},{z:.1f}" for x, z in q)}}} }},')
    # base edges inline; the rest (new districts, corridor) in sibling graph_part_<k> modules under ~150 KB each,
    # appended at require time, so require(PattayaData.graph) still returns one table
    rest = [e for e in city_edges if not (wide and e.get('base'))] if wide else []
    rest += cor_edges
    parts, cur, size = [], [], 0
    for e in rest:
        ln = edge_line(e)
        if size + len(ln) > 150 * 1024 and cur:
            parts.append(cur); cur, size = [], 0
        cur.append(ln); size += len(ln) + 1
    if cur:
        parts.append(cur)
    for f in os.listdir(out_dir):
        if f.startswith('graph_part_'):
            os.remove(os.path.join(out_dir, f))
    for k, pl in enumerate(parts, 1):
        open(os.path.join(out_dir, f'graph_part_{k}.luau'), 'w', encoding='utf-8').write(
            '-- generated by tools/circuit/export_corridor.py; do not edit (edges appended by graph.luau)\nreturn {\n' + '\n'.join(pl) + '\n}\n')
    lines = ['-- generated by tools/circuit/export_corridor.py (city graph + Bira access corridor); do not edit',
             '-- entries 1..baseNodes / 1..baseEdges are the tested central slice in its original order',
             'local graph = {',
             f'  baseNodes = {len(base_ids)}, baseEdges = {len(base_edges)},',
             '  nodes = {' + ','.join(f'{nodes_xy[str(n)][0]:.1f},{nodes_xy[str(n)][1]:.1f}' for n in all_ids) + '},',
             '  osmIds = {' + ','.join(str(n) for n in all_ids) + '},',
             '  edges = {']
    for e in base_edges:
        lines.append(edge_line(e))
    lines.append('  },\n}')
    lines.append('for _, part in {' + ', '.join(f'"graph_part_{k}"' for k in range(1, len(parts) + 1)) + '} do')
    lines.append('\tfor _, e in require(script.Parent:WaitForChild(part)) :: any do')
    lines.append('\t\ttable.insert(graph.edges, e)')
    lines.append('\tend')
    lines.append('end')
    lines.append('return graph')
    open(os.path.join(out_dir, 'graph.luau'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    # client map data for the corridor (ReplicatedStorage.PattayaCorridorMap): world studs, simplified
    cm = ['-- generated by tools/circuit/export_corridor.py; do not edit. Road to the Bira Circuit for the client map.',
          f'-- {cor["attribution"]}', 'return {']
    xs = [p[0] for e in cor_edges for p in e['pts']]; zs = [p[1] for e in cor_edges for p in e['pts']]
    cm.append(f'  bounds = {{ minX = {min(xs) + 20000:.0f}, maxX = {max(xs) + 20000:.0f}, minZ = {min(zs):.0f}, maxZ = {max(zs):.0f} }},')
    cm.append('  roads = {')
    for e in cor_edges:
        q = douglas_peucker(np.array(e['pts']), 6.0)
        cm.append(f'    {{ tier = {1 if e["tier"] == "express" else 2}, name = {lua_str(e["name_en"] or e["name"] or "")}, pts = {{{",".join(f"{x + 20000:.0f},{z:.0f}" for x, z in q)}}} }},')
    cm.append('  },\n}')
    open(os.path.join(out_dir, 'corridormap.luau'), 'w', encoding='utf-8').write('\n'.join(cm) + '\n')
    print(f'graph: base {len(base_ids)} nodes / {len(base_edges)} edges, wide {len(wide_ids)} nodes, corridor {len(extra_ids)} nodes, {len(parts)} part modules')
    print(f'corridor life: {sum(len(v) for v in lights.values())} street lights, {len(signs)} direction signs: '
          + '; '.join(t for *_, t in signs))
    if dress:
        st = dress['stats']
        allc = dress['chunks'].values()
        print(f"dressing (OSM base {dress['osm_base']}): {sum(len(c['buildings']) for c in allc)} buildings, "
              f"{sum(len(c['trees']) for c in allc)} trees, {sum(len(c['palms']) for c in allc)} palms, "
              f"{sum(len(c['poles']) for c in allc)} poles, {sum(len(c['roadSigns']) for c in allc)} approach signs, "
              f"{sum(len(c['gantries']) for c in allc)} gantry; {len(dress['chunks'])} chunks, {dress['total_parts']} parts "
              f"(max {max(c['parts'] for c in allc)} per chunk), {len(dress['ground'])} ground rects")
        print('  ' + ', '.join(f'{k} {v}' for k, v in sorted(st.items())))
        print('  parts per chunk: ' + ', '.join(f"{d} {c['parts']}" for d, c in dress['chunks'].items()))
    print(f'{len(chunks)} corridor chunks, {seg_total} segments, {len(new_discs)} new discs, {len(seam_discs)} seam discs, {len(joints)} joint discs, '
          f'{len(rects)} ground rects; graph: {len(base_ids)}+{len(extra_ids)} nodes, {len(city_edges)}+{len(cor_edges)} edges')


if __name__ == '__main__':
    main(sys.argv[1], *sys.argv[2:])
