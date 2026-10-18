"""Stage 4 - gameplay graph -> Luau data modules for the Studio builder (roblox/PattayaBuilder.luau).

  .venv\\Scripts\\python tools\\mapgen\\export_roblox.py tools\\mapgen\\config\\central_pattaya.json

Writes build/<name>/roblox/manifest.luau and chunk_<cx>_<cz>.luau. Road centrelines are simplified first
(Douglas-Peucker): straight stretches become one long segment, curves keep their short pieces, so the Part count
follows the curvature instead of the road length.
Configs with a "base" block (pattaya_wide) go through main_wide(): an extension of the base build (new chunks only,
combined runtime modules, worldmap.luau for the client map UI); see docs/WORLD_CHUNKS.md and docs/WORLD_MAP_INTEGRATION.md.
"""
import json, math, os, sys
from collections import defaultdict
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DP_TOLERANCE = 0.35        # studs of sideways error allowed when merging segments
MAX_SEGMENT = 120          # studs; very long parts are split so streaming can drop them per chunk


def douglas_peucker(p, tol):
    if len(p) < 3:
        return p
    a, b = p[0], p[-1]
    ab = b - a
    n = np.linalg.norm(ab)
    r = p - a
    d = np.abs(ab[0] * r[:, 1] - ab[1] * r[:, 0]) / n if n > 1e-9 else np.linalg.norm(r, axis=1)
    i = int(np.argmax(d))
    if d[i] <= tol:
        return np.vstack([a, b])
    return np.vstack([douglas_peucker(p[:i + 1], tol)[:-1], douglas_peucker(p[i:], tol)])


def LineString_len(p):
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())


def split_long(p, max_len):
    out = [p[0]]
    for q in p[1:]:
        seg = q - out[-1]
        n = int(math.ceil(np.linalg.norm(seg) / max_len))
        for k in range(1, n + 1):
            out.append(out[-1] + seg / n if k < n else q)
    return np.array(out)


def lua_str(s):
    if s is None:
        return 'nil'
    out = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return '"' + ''.join(c if ord(c) >= 32 else f'\\{ord(c)}' for c in out) + '"'   # newlines/control chars escaped


def main(cfg_path):
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    g = json.load(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), encoding='utf-8'))
    if 'base' in cfg:
        return main_wide(cfg, g)
    C = cfg['chunk_size_studs']
    out_dir = os.path.join(ROOT, 'build', cfg['name'], 'roblox')
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                    # only what this script writes (other files may be staged here)
        p = os.path.join(out_dir, f)
        if os.path.isfile(p) and (f.startswith('chunk_') or f in ('manifest.luau', 'graph.luau', 'jobs.luau', 'roadfight.luau', 'traffic.luau')):
            os.remove(p)
    # stage-5/6 outputs must have been made from this exact gameplay graph
    import hashlib
    ghash = hashlib.sha1(open(os.path.join(ROOT, 'build', cfg['name'], 'graph_game.json'), 'rb').read()).hexdigest()
    for fn in ('buildings_game.json', 'layout.json'):
        fp = os.path.join(ROOT, 'build', cfg['name'], fn)
        if os.path.exists(fp) and json.load(open(fp, encoding='utf-8')).get('graph_sha1') != ghash:
            sys.exit(f'{fn} is stale (made from another graph_game.json): re-run buildings.py and gameplay_layout.py')

    chunks = defaultdict(list)
    seg_total, pts_before = 0, 0
    # junction discs only where 3+ edges meet; degree-2 nodes (a road changing class or name) need none, and a disc
    # there showed up as a blob on straight roads. Radius = widest road half-width, sidewalks stop at the disc.
    degree = defaultdict(int)
    for e in g['edges']:
        degree[e['a']] += 1; degree[e['b']] += 1
    node_radius = defaultdict(float)
    for e in g['edges']:
        p = np.array(e['pts'])
        pts_before += len(p)
        q = split_long(douglas_peucker(p, DP_TOLERANCE), MAX_SEGMENT)
        seg_total += len(q) - 1
        mid = q[len(q) // 2]
        cid = (int(math.floor(mid[0] / C)), int(math.floor(mid[1] / C)))
        chunks[cid].append((e, q))
        for n in (e['a'], e['b']):
            if degree[n] >= 3:
                node_radius[n] = max(node_radius[n], e['width'] / 2)

    # buildings (stage 5), by the chunk of their centre: flat rows x, z, w, d, h, yaw, paletteIndex, osmId
    bpath = os.path.join(ROOT, 'build', cfg['name'], 'buildings_game.json')
    palettes = ['hotel', 'condo', 'apartment', 'mall', 'commercial', 'shophouse', 'house', 'temple', 'parking']
    bchunks = defaultdict(list)
    level_studs = 8.0
    if os.path.exists(bpath):
        bdata = json.load(open(bpath, encoding='utf-8'))
        level_studs = bdata['level_studs']
        for b in bdata['buildings']:
            cid = (int(math.floor(b['x'] / C)), int(math.floor(b['z'] / C)))
            bchunks[cid].append(b)
            chunks.setdefault(cid, [])
    # stage 6 layout: props go to chunks (flat x, z[, dx, dz]); race, spawn and landmarks go to the manifest
    lpath = os.path.join(ROOT, 'build', cfg['name'], 'layout.json')
    layout = json.load(open(lpath, encoding='utf-8')) if os.path.exists(lpath) else None
    pchunks = defaultdict(lambda: {'palms': [], 'lights': [], 'signs': []})
    if layout:
        for kind in ('palms', 'lights', 'signs'):
            for p in layout.get(kind, []):
                cid = (int(math.floor(p['x'] / C)), int(math.floor(p['z'] / C)))
                pchunks[cid][kind].append(p)
                chunks.setdefault(cid, [])
    facades = json.load(open(os.path.join(ROOT, 'tools', 'mapgen', 'config', 'facade_assets.json'), encoding='utf-8'))

    for (cx, cz), items in sorted(chunks.items()):
        lines = [f'-- generated by tools/mapgen/export_roblox.py from {cfg["source"]} ({g["attribution"]}); do not edit',
                 f'return {{ id = "{cx}_{cz}",',
                 '  buildings = {' + ','.join(f'{b["x"]:.1f},{b["z"]:.1f},{b["w"]:.1f},{b["d"]:.1f},{b["h"]:.1f},{b["yaw"]:.1f},'
                                             f'{palettes.index(b["palette"]) + 1},{b["id"]}' for b in bchunks.get((cx, cz), [])) + '},',
                 '  palms = {' + ','.join(f'{p["x"]:.1f},{p["z"]:.1f}' for p in pchunks[(cx, cz)]['palms']) + '},',
                 '  lights = {' + ','.join(f'{p["x"]:.1f},{p["z"]:.1f},{p["dx"]:.2f},{p["dz"]:.2f}' for p in pchunks[(cx, cz)]['lights']) + '},',
                 '  signs = {' + ','.join(f'{p["x"]:.1f},{p["z"]:.1f},{p["nx"]:.2f},{p["nz"]:.2f},{p["w"]},{p["h"]},{p["y"]},{p["color"]}'
                                        for p in pchunks[(cx, cz)]['signs']) + '},',
                 '  edges = {']
        for e, q in items:
            flat = ','.join(f'{x:.2f},{z:.2f}' for x, z in q)
            lines.append(f'  {{ id = "{e["id"]}", way = {e["way"]}, class = "{e["class"]}", tier = "{e["tier"]}", '
                         f'name = {lua_str(e["name"])}, nameEn = {lua_str(e["name_en"])}, oneway = {str(e["oneway"]).lower()}, '
                         f'lanes = {e["lanes"]}, width = {e["width"]}, sidewalk = {e["sidewalk"]}, coastal = {str(e["coastal"]).lower()}, '
                         f'a = {e["a"]}, b = {e["b"]}, pts = {{{flat}}} }},')
        lines.append('} }')
        open(os.path.join(out_dir, f'chunk_{cx}_{cz}.luau'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    # sea mask: the slice rectangle (plus margin) split by the coastline; the pieces touching the west edge are sea
    # (Pattaya faces the Gulf to the west). Rasterised to rows of [x0, x1] runs on a SEA_CELL grid for Terrain.
    from shapely.geometry import LineString, Point, box
    from shapely.ops import linemerge, split
    allp0 = np.array([p for e in g['edges'] for p in e['pts']])
    M = 600
    frame = box(allp0[:, 0].min() - M, allp0[:, 1].min() - M, allp0[:, 0].max() + M, allp0[:, 1].max() + M)
    coast_line = linemerge([LineString(c['pts']) for c in g['coastline']])
    lines = list(coast_line.geoms) if coast_line.geom_type == 'MultiLineString' else [coast_line]
    pieces = [frame]
    for ln in lines:                                       # extend each coast line to the frame so it cuts it
        p = np.array(ln.coords)
        a = p[0] + (p[0] - p[1]) / np.linalg.norm(p[0] - p[1]) * 5000
        b = p[-1] + (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2]) * 5000
        cut = LineString(np.vstack([a, p, b]))
        pieces = [q for piece in pieces for q in split(piece, cut).geoms]
    west = frame.bounds[0]
    sea = [q for q in pieces if q.bounds[0] <= west + 1 and q.representative_point().x < allp0[:, 0].mean()]
    SEA_CELL = 16
    sea_rows = []
    minx, minz, maxx, maxz = frame.bounds
    for z in np.arange(minz, maxz, SEA_CELL):
        runs, start = [], None
        for x in np.arange(minx, maxx + SEA_CELL, SEA_CELL):
            wet = x < maxx and any(q.contains(Point(x + SEA_CELL / 2, z + SEA_CELL / 2)) for q in sea)
            if wet and start is None:
                start = x
            elif not wet and start is not None:
                runs.append((start, x)); start = None
        if runs:
            sea_rows.append((z, runs))
    sea_lua = ',\n'.join(f'  {{ z = {z:.0f}, runs = {{ {", ".join(f"{a:.0f},{b:.0f}" for a, b in runs)} }} }}' for z, runs in sea_rows)

    coast = ',\n'.join('  {' + ','.join(f'{x:.1f},{z:.1f}' for x, z in douglas_peucker(np.array(c['pts']), 1.0)) + '}' for c in g['coastline'])
    junctions = ',\n'.join(f'  {{ id = {n}, x = {g["nodes"][str(n)][0]:.2f}, z = {g["nodes"][str(n)][1]:.2f}, r = {r:.2f} }}'
                           for n, r in sorted(node_radius.items()))
    allp = np.array([p for e in g['edges'] for p in e['pts']])
    race_lua = 'nil'
    if layout:
        r = layout['race']
        cps = ',\n'.join(f'    {{ x = {c["x"]}, z = {c["z"]}, dx = {c["dx"]}, dz = {c["dz"]}, w = {c["w"]} }}' for c in r['checkpoints'])
        grid = ', '.join(f'{{ x = {s["x"]}, z = {s["z"]}, dx = {s["dx"]}, dz = {s["dz"]} }}' for s in r['grid'])
        lms = ', '.join(f'{{ id = "{l["id"]}", kind = "{l["kind"]}", label = {lua_str(l["label"])}, x = {l["x"]}, z = {l["z"]}, '
                        f'dx = {l["dx"]}, dz = {l["dz"]}, span = {l["span"]}, source = {lua_str(l["source"])} }}' for l in layout['landmarks'])
        race_lua = (f'{{ id = "{r["id"]}", name = {lua_str(r["name"])}, laps = {r["laps"]}, lengthStuds = {r["length_studs"]},\n'
                    f'    checkpoints = {{\n{cps}\n    }},\n    grid = {{ {grid} }},\n'
                    f'    path = {{ {",".join(f"{x},{z}" for x, z in r["path"])} }} }},\n'
                    f'  spawn = {{ x = {layout["spawn"]["x"]}, z = {layout["spawn"]["z"]} }},\n'
                    f'  landmarks = {{ {lms} }}')
    manifest = f'''-- generated by tools/mapgen/export_roblox.py; do not edit
return {{
  name = "{cfg['name']}",
  attribution = "{g['attribution']}",
  osmBase = "{g['osm_base']}",
  compression = {cfg['compression']},
  metersPerStud = {cfg['meters_per_stud']},
  chunkSize = {C},
  bounds = {{ minX = {allp[:, 0].min():.1f}, maxX = {allp[:, 0].max():.1f}, minZ = {allp[:, 1].min():.1f}, maxZ = {allp[:, 1].max():.1f} }},
  chunks = {{ {', '.join(f'"{cx}_{cz}"' for cx, cz in sorted(chunks))} }},
  junctions = {{
{junctions}
  }},
  race = {race_lua},
  levelStuds = {level_studs:.3f},
  palettes = {{ {', '.join(f'"{p}"' for p in palettes)} }},
  facades = {{ tower = "{facades['tower']}", office = "{facades['office']}", shophouse = "{facades['shophouse']}" }},
  facadesNight = {{ tower = "{facades['tower_night']}", office = "{facades['office_night']}", shophouse = "{facades['shophouse_night']}" }},
  frame = {{ minX = {minx:.0f}, maxX = {maxx:.0f}, minZ = {minz:.0f}, maxZ = {maxz:.0f} }},
  seaCell = {SEA_CELL},
  sea = {{
{sea_lua}
  }},
  coastline = {{
{coast}
  }},
}}
'''
    open(os.path.join(out_dir, 'manifest.luau'), 'w', encoding='utf-8').write(manifest)

    # runtime road graph for route finding (street sprints, GPS): nodes + edges with simplified polylines
    node_ids = sorted({n for e in g['edges'] for n in (e['a'], e['b'])})
    idx = {n: i + 1 for i, n in enumerate(node_ids)}
    glines = ['-- generated by tools/mapgen/export_roblox.py; do not edit',
              'return {',
              '  nodes = {' + ','.join(f'{g["nodes"][str(n)][0]:.1f},{g["nodes"][str(n)][1]:.1f}' for n in node_ids) + '},',
              '  edges = {']
    tiers = {'express': 1, 'main': 2, 'soi': 3}
    for e in g['edges']:
        q = douglas_peucker(np.array(e['pts']), 1.0)
        glines.append(f'    {{ {idx[e["a"]]}, {idx[e["b"]]}, {LineString_len(q):.1f}, {tiers[e["tier"]]}, {e["width"]}, '
                      f'{{{",".join(f"{x:.1f},{z:.1f}" for x, z in q)}}} }},')
    glines.append('  },\n}')
    open(os.path.join(out_dir, 'graph.luau'), 'w', encoding='utf-8').write('\n'.join(glines) + '\n')

    # taxi / delivery stands at real POIs (missions)
    if layout and layout.get('job_stands'):
        jl = ['-- generated by tools/mapgen/export_roblox.py; do not edit', 'return {']
        rl = ['-- generated by tools/mapgen/export_roblox.py; do not edit (Road Fight bosses)', 'return {']
        for s in layout['job_stands']:
            line = (f'  {{ id = "{s["id"]}", kind = "{s["kind"]}", label = {lua_str(s["label"])}, x = {s["x"]}, z = {s["z"]}, '
                    f'dx = {s["dx"]}, dz = {s["dz"]}, kx = {s["kx"]}, kz = {s["kz"]}, source = {lua_str(s["source"])}')
            if s['kind'] == 'boss':
                rl.append(line + f', order = {s["order"]}, boss = {lua_str(s["boss"])}, district = {lua_str(s["district"])}, '
                          f'car = "{s["car"]}", vmax = {s["vmax"]}, grip = {s["grip"]}, courseMin = {s["course_min"]}, '
                          f'courseMax = {s["course_max"]}, line = {lua_str(s["line"])} }},')
            else:
                jl.append(line + ' },')
        jl.append('}')
        rl.append('}')
        open(os.path.join(out_dir, 'jobs.luau'), 'w', encoding='utf-8').write('\n'.join(jl) + '\n')
        open(os.path.join(out_dir, 'roadfight.luau'), 'w', encoding='utf-8').write('\n'.join(rl) + '\n')

    # ambient traffic loops (stage 7, traffic.py) for the client: goes to ReplicatedStorage
    tpath = os.path.join(ROOT, 'build', cfg['name'], 'traffic.json')
    if os.path.exists(tpath):
        tr = json.load(open(tpath, encoding='utf-8'))
        if tr.get('graph_sha1') != ghash:
            sys.exit('traffic.json was made from an older graph_game.json: run traffic.py again')
        tl = ['-- generated by tools/mapgen/export_roblox.py from traffic.py; do not edit', 'return {']
        for r in tr['routes']:
            tl.append(f'  {{ length = {r["length"]}, speed = {r["speed"]}, phase = {r["phase"]}, '
                      f'kinds = {{{",".join(str(k) for k in r["kinds"])}}}, '
                      f'pts = {{{",".join(f"{x},{z}" for x, z in r["pts"])}}} }},')
        tl.append('}')
        open(os.path.join(out_dir, 'traffic.luau'), 'w', encoding='utf-8').write('\n'.join(tl) + '\n')
    sizes = [os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir)]
    print(f'{len(chunks)} chunks, {seg_total} road segments (from {pts_before} smoothed points), '
          f'{len(node_radius)} junctions; largest module {max(sizes) / 1024:.0f} KB, total {sum(sizes) / 1024:.0f} KB')


# ---------------------------------------------------------------------------------------------------------------------
# Wide world (config with a "base" block): an EXTENSION of a tested base build. Chunk modules hold only the new roads,
# buildings and props; the base chunks are never rewritten. Runtime modules (graph, jobs, roadfight, traffic) are the
# combined base + new data with every base entry first and unchanged. See docs/WORLD_CHUNKS.md (import plan).
# ---------------------------------------------------------------------------------------------------------------------
WORLD_ORIGIN = (20000.0, 0.0)          # PattayaBuilder.ORIGIN (x, z)
GRAPH_DP_NEW = 3.0                     # studs; GPS/route polylines of the new edges in graph.luau


def frame_of(edges, margin=600):
    allp0 = np.array([p for e in edges for p in e['pts']])
    return (allp0[:, 0].min() - margin, allp0[:, 1].min() - margin, allp0[:, 0].max() + margin, allp0[:, 1].max() + margin)


SIDEWALK_CONFLICT_STUDS2 = 10.0       # a sidewalk side lying on more than this area of another road's slab is dropped


def sidewalk_sides(edges, qs, junction_r, deg):
    """Which sidewalk sides of the new edges to build (wide world).

    At x0.5, close parallel roads (dual carriageways above all: Jomtien Second Rd, Thappraya, Pattaya Nuea) lie so near
    that one road's sidewalk strip (width/2 .. width/2 + sidewalk, top 0.6 above the road) covers the other's roadway:
    the Studio probe hit a sidewalk on 966 of 24,994 points. Rule: rebuild each side's strip exactly as PattayaBuilder
    does (trimmed at junction discs) and drop that side when it overlaps another edge's road slab by more than
    SIDEWALK_CONFLICT_STUDS2 studs^2 (the continuing edge at a degree-2 joint does not count). Returns
    ({edge id: kept side (-1 / 1), or 0 = no sidewalk}, stats text); edges that keep both sides are not listed, so
    their chunk lines are unchanged."""
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    import road_check as rc
    slabs, own = [], []
    for i, e in enumerate(edges):
        q = qs.get(e['id'])
        if q is None:   # base edge: the same polyline its own export wrote
            q = split_long(douglas_peucker(np.array(e['pts']), DP_TOLERANCE), MAX_SEGMENT)
        for r in rc.stripe_rects(q, e['width']):
            slabs.append(r); own.append(i)
    tree = STRtree(slabs)
    out, n_sides, n_drop = {}, 0, 0
    for i, e in enumerate(edges):
        if e.get('base') or e['sidewalk'] <= 0:
            continue
        ra, rb = junction_r.get(e['a'], 0), junction_r.get(e['b'], 0)
        sw = rc.trim(qs[e['id']], ra + e['sidewalk'] if ra > 0 else 0, rb + e['sidewalk'] if rb > 0 else 0)
        if sw is None:
            continue
        keep = []
        for side in (-1, 1):
            n_sides += 1
            strip = unary_union(rc.stripe_rects(rc.offset(sw, side * (e['width'] + e['sidewalk']) / 2), e['sidewalk']))
            area = 0.0
            for k in tree.query(strip):
                j = own[k]
                o = edges[j]
                if j == i or any(deg[n] == 2 for n in {o['a'], o['b']} & {e['a'], e['b']}):
                    continue
                area += slabs[k].intersection(strip).area
            if area > SIDEWALK_CONFLICT_STUDS2:
                n_drop += 1
            else:
                keep.append(side)
        if len(keep) < 2:
            out[e['id']] = keep[0] if keep else 0
    both = sum(1 for v in out.values() if v == 0)
    return out, f'{n_drop} of {n_sides} sides dropped ({both} edges lose both, {len(out) - both} keep one side)'


def sw_field(e, sw_side):
    s = sw_side.get(e['id'])
    return f', swSide = {s}' if s else ''


def main_wide(cfg, g):
    import hashlib
    import shapely
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely.ops import linemerge, split, unary_union
    C = cfg['chunk_size_studs']
    name = cfg['name']
    bdir = os.path.join(ROOT, 'build', name)
    out_dir = os.path.join(bdir, 'roblox')
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        p = os.path.join(out_dir, f)
        if os.path.isfile(p) and (f.startswith('chunk_') or f.startswith('graph_part_') or f in (
                'manifest.luau', 'graph.luau', 'jobs.luau', 'roadfight.luau', 'traffic.luau', 'worldmap.luau', 'joints.luau')):
            os.remove(p)
    ghash = hashlib.sha1(open(os.path.join(bdir, 'graph_game.json'), 'rb').read()).hexdigest()
    for fn in ('buildings_game.json', 'layout.json', 'traffic.json'):
        if json.load(open(os.path.join(bdir, fn), encoding='utf-8')).get('graph_sha1') != ghash:
            sys.exit(f'{fn} is stale (made from another graph_game.json): re-run the earlier stages')
    edges = g['edges']
    base_edges = [e for e in edges if e.get('base')]
    new_edges = [e for e in edges if not e.get('base')]
    bc = cfg['buildings']
    lod = bc.get('lod', {})

    # --- junction discs: new ones where the combined degree reaches 3 and the base build had none --------------------
    deg, base_deg = defaultdict(int), defaultdict(int)
    for e in edges:
        deg[e['a']] += 1; deg[e['b']] += 1
    for e in base_edges:
        base_deg[e['a']] += 1; base_deg[e['b']] += 1
    radius = defaultdict(float)
    for e in edges:
        for n in (e['a'], e['b']):
            radius[n] = max(radius[n], e['width'] / 2)
    base_radius = defaultdict(float)
    for e in base_edges:
        for n in (e['a'], e['b']):
            if base_deg[n] >= 3:
                base_radius[n] = max(base_radius[n], e['width'] / 2)
    touched = {n for e in new_edges for n in (e['a'], e['b'])}
    new_discs = {n: radius[n] for n in touched if deg[n] >= 3 and base_deg[n] < 3}
    seam_discs = {n: base_radius[n] for n in touched if base_deg[n] >= 3}    # existing base discs (radius only)
    # joint discs where no junction disc is: degree-2 joints (a road changing name/class, a seam node) and dead ends.
    # Two slabs meeting at such a node only touch (no overlap), so a ray exactly at the node can slip between them
    # (Studio probe: 62 misses, nearly all at a node) and a bend leaves a wedge open on its outer side. The disc
    # (radius = narrowest incident half-width, so it never sticks out of the road) closes both. Unlike junction discs
    # it does not trim markings or sidewalks, so no chunk module changes because of it (docs/ROAD_SYSTEM.md).
    min_half = {}
    for e in edges:
        for n in (e['a'], e['b']):
            min_half[n] = min(min_half.get(n, 1e9), e['width'] / 2)
    joints = {n: min_half[n] for n in touched if deg[n] <= 2}

    # --- chunk contents (new things only) ------------------------------------------------------------------------------
    chunks = defaultdict(list)
    seg_total = 0
    qs = {}
    for e in new_edges:
        q = split_long(douglas_peucker(np.array(e['pts']), DP_TOLERANCE), MAX_SEGMENT)
        qs[e['id']] = q
        seg_total += len(q) - 1
        mid = q[len(q) // 2]
        chunks[(int(math.floor(mid[0] / C)), int(math.floor(mid[1] / C)))].append((e, q))
    sw_side, sw_stats = sidewalk_sides(edges, qs, {**seam_discs, **new_discs}, deg)
    palettes = ['hotel', 'condo', 'apartment', 'mall', 'commercial', 'shophouse', 'house', 'temple', 'parking']
    bdata = json.load(open(os.path.join(bdir, 'buildings_game.json'), encoding='utf-8'))
    bchunks = defaultdict(list)
    for b in bdata['buildings']:
        cid = (int(math.floor(b['x'] / C)), int(math.floor(b['z'] / C)))
        bchunks[cid].append(b); chunks.setdefault(cid, [])
    layout = json.load(open(os.path.join(bdir, 'layout.json'), encoding='utf-8'))
    pchunks = defaultdict(lambda: {'palms': [], 'lights': []})
    for kind in ('palms', 'lights'):
        for p in layout[kind]:
            cid = (int(math.floor(p['x'] / C)), int(math.floor(p['z'] / C)))
            pchunks[cid][kind].append(p); chunks.setdefault(cid, [])
    facades = json.load(open(os.path.join(ROOT, 'tools', 'mapgen', 'config', 'facade_assets.json'), encoding='utf-8'))
    parts_est = {'road': 0, 'buildings': 0, 'roofs': 0, 'textures': 0, 'props': 0}
    fmin = lod.get('facade_min_height_studs', 0)
    dash_gap = cfg.get('roads_lod', {}).get('dash_gap_studs', 12)
    for (cx, cz), items in sorted(chunks.items()):
        bl = bchunks.get((cx, cz), [])
        pl = pchunks[(cx, cz)]
        lines = [f'-- generated by tools/mapgen/export_roblox.py ({cfg["name"]}, extension of {cfg["base"]["build"]}) from OSM ({g["attribution"]}); do not edit',
                 f'return {{ id = "{cx}_{cz}",',
                 '  buildings = {' + ','.join(f'{b["x"]:.1f},{b["z"]:.1f},{b["w"]:.1f},{b["d"]:.1f},{b["h"]:.1f},{b["yaw"]:.1f},'
                                             f'{palettes.index(b["palette"]) + 1},{b["id"]}' for b in bl) + '},',
                 '  palms = {' + ','.join(f'{p["x"]:.1f},{p["z"]:.1f}' for p in pl['palms']) + '},',
                 '  lights = {' + ','.join(f'{p["x"]:.1f},{p["z"]:.1f},{p["dx"]:.2f},{p["dz"]:.2f}' for p in pl['lights']) + '},',
                 '  signs = {},',
                 '  edges = {']
        for e, q in items:
            flat = ','.join(f'{x:.2f},{z:.2f}' for x, z in q)
            lines.append(f'  {{ id = "{e["id"]}", way = {e["way"]}, class = "{e["class"]}", tier = "{e["tier"]}", '
                         f'name = {lua_str(e["name"])}, nameEn = {lua_str(e["name_en"])}, oneway = {str(e["oneway"]).lower()}, '
                         f'lanes = {e["lanes"]}, width = {e["width"]}, sidewalk = {0 if sw_side.get(e["id"]) == 0 else e["sidewalk"]}, '
                         f'coastal = {str(e["coastal"]).lower()}, a = {e["a"]}, b = {e["b"]}, pts = {{{flat}}}{sw_field(e, sw_side)} }},')
            # part estimate as PattayaBuilder builds it: slab per segment, 2 sidewalks, markings on non-soi roads
            nseg = len(q) - 1
            parts_est['road'] += nseg * (1 + ({None: 2, 0: 0}.get(sw_side.get(e['id']), 1) if e['sidewalk'] > 0 else 0))
            if e['tier'] != 'soi':
                L_ = LineString_len(q)
                lanes_marks = (e['lanes'] - 1) if e['oneway'] else 2 + 2 * max(e['lanes'] // 2 - 1, 0)
                parts_est['road'] += int(L_ / (8 + dash_gap)) * max(lanes_marks - (0 if e['oneway'] else 2), 0) + (0 if e['oneway'] else 2 * nseg)
        lines.append('} }')
        open(os.path.join(out_dir, f'chunk_{cx}_{cz}.luau'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        for b in bl:
            parts_est['buildings'] += 1
            parts_est['roofs'] += b['h'] > 30
            if b['palette'] not in ('house', 'temple') and b['h'] >= fmin:
                parts_est['textures'] += 4
        parts_est['props'] += 6 * len(pl['palms']) + 3 * len(pl['lights'])

    # --- base buildings that a new road surface cuts into (at the seam): listed so the leader can decide -----------
    from shapely.strtree import STRtree
    from shapely import affinity
    bb = json.load(open(os.path.join(ROOT, cfg['base']['build'], 'buildings_game.json'), encoding='utf-8'))['buildings']
    bpolys = [affinity.translate(affinity.rotate(Polygon([(-x['w'] / 2, -x['d'] / 2), (x['w'] / 2, -x['d'] / 2), (x['w'] / 2, x['d'] / 2),
                                                          (-x['w'] / 2, x['d'] / 2)]), x['yaw']), x['x'], x['z']) for x in bb]
    btree = STRtree(bpolys)
    conflicts = set()
    for e in new_edges:
        c = LineString(e['pts']).buffer(e['width'] / 2 + e['sidewalk'])
        conflicts |= {bb[i]['id'] for i in btree.query(c) if bpolys[i].intersection(c).area > 0.5}

    # --- import batches: seam chunks first (next to a base chunk), then one batch per district ----------------------
    base_ids_c = set()
    for f in os.listdir(os.path.join(ROOT, cfg['base']['build'], 'roblox')):
        if f.startswith('chunk_'):
            cx_, cz_ = f[6:-5].split('_')
            base_ids_c.add((int(cx_), int(cz_)))
    dpolys = [(d['id'], Polygon(d['poly'])) for d in layout.get('districts', [])]
    batches = defaultdict(list)
    for cid in sorted(chunks):
        if any((cid[0] + dx, cid[1] + dz) in base_ids_c for dx in (-1, 0, 1) for dz in (-1, 0, 1)):
            batches['seam'].append(cid); continue
        c = Point((cid[0] + 0.5) * C, (cid[1] + 0.5) * C)
        batches[min(dpolys, key=lambda t: t[1].distance(c))[0] if dpolys else 'other'].append(cid)
    batch_order = ['seam'] + [d for d, _ in dpolys if d in batches]
    batch_lua = ',\n'.join(f'    {b_} = {{ {", ".join(f"{chr(34)}{cx}_{cz}{chr(34)}" for cx, cz in batches[b_])} }}' for b_ in batch_order)

    # --- terrain: wide frame minus the base frame (the base terrain is never touched) -------------------------------
    minx, minz, maxx, maxz = frame_of(edges)
    bminx, bminz, bmaxx, bmaxz = frame_of(base_edges)
    SEA_CELL = 16
    snap = lambda v, up: (math.ceil(v / SEA_CELL) if up else math.floor(v / SEA_CELL)) * SEA_CELL
    minx, minz, maxx, maxz = snap(minx, False), snap(minz, False), snap(maxx, True), snap(maxz, True)
    # ground rectangles around the base frame: north, south (full width), then west/east strips beside it
    # (edges next to the base frame snapped to the 4-stud voxel grid AWAY from it: the builder's clear pass expands
    # regions to that grid and must never eat into base terrain)
    f4, c4 = (lambda v: math.floor(v / 4) * 4), (lambda v: math.ceil(v / 4) * 4)
    rects = [(minx, maxx, minz, f4(bminz)), (minx, maxx, c4(bmaxz), maxz), (minx, f4(bminx), f4(bminz), c4(bmaxz)),
             (c4(bmaxx), maxx, f4(bminz), c4(bmaxz))]
    rects = [r for r in rects if r[1] - r[0] > 1 and r[3] - r[2] > 1]
    frame = box(minx, minz, maxx, maxz)
    merged = linemerge([LineString(c['pts']) for c in g['coastline']])
    glines = list(merged.geoms) if merged.geom_type == 'MultiLineString' else [merged]
    islets = [Polygon(l.coords) for l in glines if l.is_ring]
    main_coast = max((l for l in glines if not l.is_ring), key=lambda l: l.length)
    p = np.array(main_coast.coords)
    a = p[0] + (p[0] - p[1]) / np.linalg.norm(p[0] - p[1]) * 20000
    b = p[-1] + (p[-1] - p[-2]) / np.linalg.norm(p[-1] - p[-2]) * 20000
    pieces = list(split(frame, LineString(np.vstack([a, p, b]))).geoms)
    sea = [q for q in pieces if q.bounds[0] <= minx + 1 and q.representative_point().x < (minx + maxx) / 2]
    sea = unary_union(sea).difference(unary_union(islets)) if islets else unary_union(sea)
    xs = np.arange(minx, maxx, SEA_CELL) + SEA_CELL / 2
    # the base frame snapped outward to the voxel grid (bx0..bx1, bz0..bz1) belongs to the base terrain. Rows that
    # cross its z edges are split into sub-bands (h = 4..12) so the new sea meets the base sea with no gap.
    bx0, bx1, bz0, bz1 = f4(bminx), c4(bmaxx), f4(bminz), c4(bmaxz)
    sea_rows = []
    for z in np.arange(minz, maxz, SEA_CELL):
        wet = shapely.contains_xy(sea, xs, np.full_like(xs, z + SEA_CELL / 2))
        runs, start = [], None
        for i, w in enumerate(list(wet) + [False]):
            x = minx + i * SEA_CELL
            if w and start is None:
                start = x
            elif not w and start is not None:
                runs.append((start, x)); start = None
        if not runs:
            continue
        cuts = sorted({z, z + SEA_CELL} | {c for c in (bz0, bz1) if z < c < z + SEA_CELL})
        for za, zb in zip(cuts[:-1], cuts[1:]):
            if zb <= bz0 or za >= bz1:                     # band outside the base frame's z range: runs as they are
                sea_rows.append((za, zb - za, [(a_, b_, 1) for a_, b_ in runs]))
                continue
            clipped = []
            for a_, b_ in runs:                            # keep the parts west / east of the base frame
                if a_ < bx0:
                    e_ = min(b_, bx0)
                    clipped.append((a_, e_, 1 if e_ + 48 <= bx0 else 0))
                if b_ > bx1:
                    clipped.append((max(a_, bx1), b_, 1))
            if clipped:
                sea_rows.append((za, zb - za, clipped))
    sea_lua = ',\n'.join(f'  {{ z = {z:.0f}, h = {h:.0f}, runs = {{ {", ".join(f"{a_:.0f},{b_:.0f},{s_}" for a_, b_, s_ in runs)} }} }}'
                         for z, h, runs in sea_rows)
    coast = ',\n'.join('  {' + ','.join(f'{x:.1f},{z:.1f}' for x, z in douglas_peucker(np.array(c['pts']), 1.0)) + '}' for c in g['coastline'])

    jl = ',\n'.join(f'  {{ id = {n}, x = {g["nodes"][str(n)][0]:.2f}, z = {g["nodes"][str(n)][1]:.2f}, r = {r:.2f} }}'
                    for n, r in sorted(new_discs.items()))
    sl = ',\n'.join(f'  {{ id = {n}, r = {r:.2f} }}' for n, r in sorted(seam_discs.items()))
    # joint discs in their own module (the manifest is close to the 200 KB module limit): flat quadruples
    # osmNode, x, z, r, built by PattayaBuilder.Extend when the data folder has a `joints` module
    open(os.path.join(out_dir, 'joints.luau'), 'w', encoding='utf-8').write(
        '-- generated by tools/mapgen/export_roblox.py; do not edit. Joint discs (osmNode, x, z, r) at degree-2 joints\n'
        '-- and dead ends (no junction disc there): they close hairline gaps and bend wedges and do not trim markings or sidewalks\n'
        'return {' + ','.join(f'{n},{g["nodes"][str(n)][0]:.2f},{g["nodes"][str(n)][1]:.2f},{r:.2f}' for n, r in sorted(joints.items())) + '}\n')
    allp = np.array([p for e in edges for p in e['pts']])
    manifest = f'''-- generated by tools/mapgen/export_roblox.py; do not edit
-- EXTENSION of {cfg['base']['build']}: build with PattayaBuilder.Extend("PattayaDataWide"); the base world is not touched
return {{
  name = "{name}",
  extends = "{os.path.basename(cfg['base']['build'])}",
  attribution = "{g['attribution']}",
  osmBase = "{g['osm_base']}",
  compression = {cfg['compression']},
  metersPerStud = {cfg['meters_per_stud']},
  chunkSize = {C},
  bounds = {{ minX = {allp[:, 0].min():.1f}, maxX = {allp[:, 0].max():.1f}, minZ = {allp[:, 1].min():.1f}, maxZ = {allp[:, 1].max():.1f} }},
  chunks = {{ {', '.join(f'"{cx}_{cz}"' for cx, cz in sorted(chunks))} }},
  -- import order for PattayaBuilder.Extend({{batch = "<name>"}}): seam chunks touch the base slice, then districts
  batchOrder = {{ {', '.join(f'"{b_}"' for b_ in batch_order)} }},
  batches = {{
{batch_lua}
  }},
  junctions = {{
{jl}
  }},
  seamJunctions = {{
{sl}
  }},
  -- base-slice buildings (OsmBuilding ids) that a new road surface cuts into at the seam; Extend removes them only
  -- when called with {{removeBaseConflicts = true}}
  baseBuildingConflicts = {{ {', '.join(str(i) for i in sorted(conflicts))} }},
  levelStuds = {bdata['level_studs']:.3f},
  palettes = {{ {', '.join(f'"{p}"' for p in palettes)} }},
  facades = {{ tower = "{facades['tower']}", office = "{facades['office']}", shophouse = "{facades['shophouse']}" }},
  facadesNight = {{ tower = "{facades['tower_night']}", office = "{facades['office_night']}", shophouse = "{facades['shophouse_night']}" }},
  facadeMinHeight = {fmin},
  dashGap = {dash_gap},
  frame = {{ minX = {minx:.0f}, maxX = {maxx:.0f}, minZ = {minz:.0f}, maxZ = {maxz:.0f} }},
  baseFrame = {{ minX = {bminx:.0f}, maxX = {bmaxx:.0f}, minZ = {bminz:.0f}, maxZ = {bmaxz:.0f} }},
  groundRects = {{ {', '.join(f'{{ {r[0]:.0f}, {r[1]:.0f}, {r[2]:.0f}, {r[3]:.0f} }}' for r in rects)} }},
  seaCell = {SEA_CELL},
  -- sea rows z..z+h: runs are TRIPLES x0, x1, sand (1 = add the 48-stud sand strip east of x1); nothing inside
  -- baseFrame (snapped outward to the 4-stud voxel grid) is written
  sea = {{
{sea_lua}
  }},
  coastline = {{
{coast}
  }},
}}
'''
    open(os.path.join(out_dir, 'manifest.luau'), 'w', encoding='utf-8').write(manifest)

    # --- runtime graph: base nodes/edges first in the base build's order (indices unchanged), new ones after ----------
    base_ids = sorted({n for e in base_edges for n in (e['a'], e['b'])})
    new_ids = sorted({n for e in edges for n in (e['a'], e['b'])} - set(base_ids))
    node_ids = base_ids + new_ids
    idx = {n: i + 1 for i, n in enumerate(node_ids)}
    tiers = {'express': 1, 'main': 2, 'soi': 3}
    def edge_line(e):
        # base lines exactly as the base build wrote them; new lines a little coarser to keep the modules small
        q = douglas_peucker(np.array(e['pts']), 1.0 if e.get('base') else GRAPH_DP_NEW)
        return (f'    {{ {idx[e["a"]]}, {idx[e["b"]]}, {LineString_len(q):.1f}, {tiers[e["tier"]]}, {e["width"]}, '
                f'{{{",".join(f"{x:.1f},{z:.1f}" for x, z in q)}}} }},')
    # new edges go to sibling modules graph_part_<k> (each under ~150 KB); graph.luau appends them in order, so
    # require(PattayaData.graph) still returns one {nodes, edges} table and PattayaRoute needs no change
    parts, cur, size = [], [], 0
    for e in new_edges:
        ln = edge_line(e)
        if size + len(ln) > 150 * 1024 and cur:
            parts.append(cur); cur, size = [], 0
        cur.append(ln); size += len(ln) + 1
    if cur:
        parts.append(cur)
    for k, pl in enumerate(parts, 1):
        open(os.path.join(out_dir, f'graph_part_{k}.luau'), 'w', encoding='utf-8').write(
            '-- generated by tools/mapgen/export_roblox.py; do not edit (new edges, appended by graph.luau)\nreturn {\n'
            + '\n'.join(pl) + '\n}\n')
    gl = ['-- generated by tools/mapgen/export_roblox.py; do not edit',
          f'-- {name}: entries 1..baseNodes / 1..baseEdges are exactly {os.path.basename(cfg["base"]["build"])}\'s graph (same order);',
          '-- the new edges follow from the graph_part_<k> modules (same folder)',
          'local graph = {',
          f'  baseNodes = {len(base_ids)}, baseEdges = {len(base_edges)},',
          '  nodes = {' + ','.join(f'{g["nodes"][str(n)][0]:.1f},{g["nodes"][str(n)][1]:.1f}' for n in node_ids) + '},',
          '  edges = {']
    gl += [edge_line(e) for e in base_edges]
    gl.append('  },\n}')
    gl.append('for _, part in {' + ', '.join(f'"graph_part_{k}"' for k in range(1, len(parts) + 1)) + '} do')
    gl.append('\tfor _, e in require(script.Parent:WaitForChild(part)) :: any do')
    gl.append('\t\ttable.insert(graph.edges, e)')
    gl.append('\tend')
    gl.append('end')
    gl.append('return graph')
    open(os.path.join(out_dir, 'graph.luau'), 'w', encoding='utf-8').write('\n'.join(gl) + '\n')

    # --- jobs / Road Fight / traffic (base entries verbatim first) ---------------------------------------------------
    jl_, rl = ['-- generated by tools/mapgen/export_roblox.py; do not edit', 'return {'], \
        ['-- generated by tools/mapgen/export_roblox.py; do not edit (Road Fight bosses)', 'return {']
    for s in layout['job_stands']:
        line = (f'  {{ id = "{s["id"]}", kind = "{s["kind"]}", label = {lua_str(s["label"])}, x = {s["x"]}, z = {s["z"]}, '
                f'dx = {s["dx"]}, dz = {s["dz"]}, kx = {s["kx"]}, kz = {s["kz"]}, source = {lua_str(s["source"])}')
        if s['kind'] == 'boss':
            rl.append(line + f', order = {s["order"]}, boss = {lua_str(s["boss"])}, district = {lua_str(s["district"])}, '
                      f'car = "{s["car"]}", vmax = {s["vmax"]}, grip = {s["grip"]}, courseMin = {s["course_min"]}, '
                      f'courseMax = {s["course_max"]}, line = {lua_str(s["line"])} }},')
        else:
            jl_.append(line + (f', district = "{s["district"]}"' if s.get('new') and s.get('district') else '') + ' },')
    jl_.append('}'); rl.append('}')
    open(os.path.join(out_dir, 'jobs.luau'), 'w', encoding='utf-8').write('\n'.join(jl_) + '\n')
    open(os.path.join(out_dir, 'roadfight.luau'), 'w', encoding='utf-8').write('\n'.join(rl) + '\n')
    tr = json.load(open(os.path.join(bdir, 'traffic.json'), encoding='utf-8'))
    tl = ['-- generated by tools/mapgen/export_roblox.py from traffic.py; do not edit', 'return {']
    for r in tr['routes']:
        tl.append(f'  {{ length = {r["length"]}, speed = {r["speed"]}, phase = {r["phase"]}, '
                  f'kinds = {{{",".join(str(k) for k in r["kinds"])}}}, '
                  f'pts = {{{",".join(f"{x},{z}" for x, z in r["pts"])}}} }},')
    tl.append('}')
    open(os.path.join(out_dir, 'traffic.luau'), 'w', encoding='utf-8').write('\n'.join(tl) + '\n')

    # --- world map for the client UI (world coordinates) ---------------------------------------------------------------
    write_worldmap(cfg, g, layout, out_dir, idx)

    sizes = {f: os.path.getsize(os.path.join(out_dir, f)) for f in os.listdir(out_dir)}
    chunk_sizes = [v for f, v in sizes.items() if f.startswith('chunk_')]
    total_parts = sum(v for k, v in parts_est.items() if k != 'textures')
    print(f'{len(chunks)} new chunks, {len(new_edges)} new edges -> {seg_total} road segments, {len(new_discs)} new junction discs '
          f'({len(seam_discs)} base discs touched); largest chunk module {max(chunk_sizes) / 1024:.0f} KB, chunks total '
          f'{sum(chunk_sizes) / 1024:.0f} KB')
    total_parts += len(new_discs) + len(joints)
    print(f'{len(joints)} joint discs; sidewalks on another road: {sw_stats}')
    print(f'base buildings cut by new road surfaces: {len(conflicts)} {sorted(conflicts)}')
    print(f"estimated new Parts {total_parts:,} incl. {len(new_discs)} junction discs (roads+markings {parts_est['road']:,}, buildings {parts_est['buildings']:,}, "
          f"roofs {parts_est['roofs']:,}, props {parts_est['props']:,}), facade Textures {parts_est['textures']:,}")
    print('runtime modules: ' + ', '.join(f'{f} {v / 1024:.0f} KB' for f, v in sorted(sizes.items()) if not f.startswith('chunk_')))
    print('import batches: ' + ', '.join(f'{b_} {len(batches[b_])}' for b_ in batch_order))
    big = [f for f, v in sizes.items() if v > 200 * 1024]
    if big:
        print(f'WARNING: chunk modules over 200 KB: {big}')


def write_worldmap(cfg, g, layout, out_dir, idx):
    """build/<name>/roblox/worldmap.luau: simplified main roads, coast, districts, POIs - world studs (map-local + ORIGIN)."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import linemerge
    OX, OZ = WORLD_ORIGIN
    W = lambda x, z: f'{x + OX:.0f},{z + OZ:.0f}'
    edges = g['edges']
    tiers = {'express': 1, 'main': 2}
    groups = defaultdict(list)
    for e in edges:
        if e['tier'] in tiers:
            groups[(e['tier'], e['name_en'] or e['name'] or '')].append(LineString(e['pts']))
    roads = []
    for (tier, nm), ls in sorted(groups.items(), key=lambda t: (tiers[t[0][0]], t[0][1])):
        m = linemerge(ls)
        for l in (m.geoms if m.geom_type == 'MultiLineString' else [m]):
            q = douglas_peucker(np.array(l.coords), 6.0)
            if LineString_len(q) >= 60:
                roads.append((tiers[tier], nm, q))
    coast = [douglas_peucker(np.array(c['pts']), 8.0) for c in g['coastline']]
    districts = layout.get('districts', [])
    dpolys = [(d['id'], Polygon(d['poly'])) for d in districts]

    def district_at(x, z):
        return next((i for i, p in dpolys if p.contains(Point(x, z))), None)
    pois = []
    for s in layout['job_stands']:
        pois.append({'id': s['id'], 'kind': s['kind'], 'label': s['label'], 'x': s['x'], 'z': s['z'],
                     'district': s.get('district') if s['kind'] != 'boss' and s.get('new') else district_at(s['x'], s['z']),
                     'order': s.get('order')})
    r = layout['race']
    pois.append({'id': r['id'], 'kind': 'race', 'label': r['name'], 'x': r['grid'][0]['x'], 'z': r['grid'][0]['z'],
                 'district': district_at(r['grid'][0]['x'], r['grid'][0]['z'])})
    be = cfg['layout'].get('bira_entrance')
    if be:
        n = str(be['osm_node'])
        if n in g['nodes']:
            x, z = g['nodes'][n]
            pois.append({'id': 'bira_entrance', 'kind': 'bira', 'label': be['label'], 'x': x, 'z': z, 'status': be['status'],
                         'district': district_at(x, z), 'node': idx[int(n)]})
        else:
            print(f'bira_entrance: node {n} not in the graph, skipped')
    allp = np.array([p for e in edges for p in e['pts']])
    L = ['-- generated by tools/mapgen/export_roblox.py; do not edit. World map data for the client map UI.',
         f'-- {g["attribution"]}. Coordinates are WORLD studs (x east, z south) = map-local + PattayaBuilder.ORIGIN.',
         'return {',
         '  version = 1,',
         f'  attribution = {lua_str(g["attribution"])},',
         f'  origin = {{ x = {OX:.0f}, z = {OZ:.0f} }},',
         f'  bounds = {{ minX = {allp[:, 0].min() + OX:.0f}, maxX = {allp[:, 0].max() + OX:.0f}, '
         f'minZ = {allp[:, 1].min() + OZ:.0f}, maxZ = {allp[:, 1].max() + OZ:.0f} }},',
         '  -- tier 1 = express (Sukhumvit), 2 = main road; pts = flat x,z list',
         '  roads = {']
    for t, nm, q in roads:
        L.append(f'    {{ tier = {t}, name = {lua_str(nm or None)}, pts = {{{",".join(W(x, z) for x, z in q)}}} }},')
    L.append('  },')
    L.append('  coast = {')
    for q in coast:
        L.append(f'    {{{",".join(W(x, z) for x, z in q)}}},')
    L.append('  },')
    L.append('  -- game districts (approximate latitude bands, not official boundaries)')
    L.append('  districts = {')
    for d in districts:
        L.append(f'    {{ id = "{d["id"]}", name = {lua_str(d["name"])}, nameTh = {lua_str(d.get("name_th"))}, '
                 f'x = {d["x"] + OX:.0f}, z = {d["z"] + OZ:.0f}, poly = {{{",".join(W(x, z) for x, z in d["poly"])}}} }},')
    L.append('  },')
    L.append('  -- kind: taxi | delivery | boss | race | bira. status = "pending corridor" until the Bira corridor is imported')
    L.append('  pois = {')
    for p in pois:
        extra = ''
        if p.get('order'):
            extra += f', order = {p["order"]}'
        if p.get('status'):
            extra += f', status = {lua_str(p["status"])}'
        if p.get('node'):
            extra += f', graphNode = {p["node"]}'
        L.append(f'    {{ id = "{p["id"]}", kind = "{p["kind"]}", label = {lua_str(p["label"])}, x = {p["x"] + OX:.0f}, '
                 f'z = {p["z"] + OZ:.0f}, district = {lua_str(p.get("district"))}{extra} }},')
    L.append('  },')
    L.append('}')
    open(os.path.join(out_dir, 'worldmap.luau'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print(f'worldmap: {len(roads)} road polylines ({sum(len(q) for _, _, q in roads)} points), {len(districts)} districts, '
          f'{len(pois)} POIs')


if __name__ == '__main__':
    main(sys.argv[1])
