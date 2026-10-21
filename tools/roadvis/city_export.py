"""Studio data for one city batch of Road B (PattayaRoadVisBuilder, city mode). OFFLINE.

  build/roadcity/<id>/roblox_rv/   -> ServerStorage.PattayaDataRoadVis_<id> (Folder of ModuleScripts)
      manifest.luau        batch (id, seq, box, the build order it was made for, neighbours, frontier targets), tops,
                           colours, modules, cells, counts, replace (required keys, optional keys), probe (samples +
                           the offline expectation), the same table layout as the pilot manifest plus `batch`
      cell_<cx>_<cz>[q..][_k].luau   one 256-stud cell (map-local index), <= 600 parts per module:
        tris  {x1, z1, x2, z2, x3, z3, kind}           kind 1 asphalt, 2 sidewalk, 3 island, 4 grass, 5 support
        ftris {x1, z1, x2, z2, x3, z3, kind, target}   frontier pieces (kind 1 asphalt, 2 sidewalk) outside the box;
                                                       target = index into manifest.batch.frontierFor (0 = none)
        segs  {ax, az, bx, bz, width, kind}            kind 1 lane dash, 2 centre, 3 edge line, 4 stop line, 5 zebra,
                                                       6 kerb
Replace keys {code, world x, world z} (footprint centre = the Part's Position): codes 1-9 old parts (as the pilot),
11-15 Road B triangle parts (RoadVisPilot or a city batch's frontier piece: Road, Sidewalk, Island, Grass,
RoadSupport), 21-26 Road B segment parts (Dash, Centre, EdgeLine, StopLine, ZebraStripe, Kerb).
"""
import hashlib
import math
import os
from collections import Counter, defaultdict

import numpy as np
from shapely.geometry import Point

from tools.roadvis import city, export_luau, world

CELL = export_luau.CELL
CAP = export_luau.CAP
SEG_KIND = export_luau.SEG_KIND
KIND_NAME = {1: 'asphalt', 2: 'sidewalk', 3: 'island', 4: 'grass', 5: 'support'}
SEG_NAME = {1: 'lane', 2: 'centre', 3: 'edge', 4: 'stop', 5: 'zebra', 6: 'kerb'}


def r(v, n=2):
    return round(float(v), n)


def cell_of(pt):
    return f'{math.floor(pt.x / CELL)}_{math.floor(pt.y / CELL)}'


def wedge_keys(row, code):
    """replace keys of the WedgeParts the builder makes for a triangle row: (code, world x, z) of each wedge's Position"""
    out = []
    for poly, _ in world.rs.wedge_tris(row[0:2], row[2:4], row[4:6]):
        c = export_luau.wedge_rect(poly).centroid
        out.append((code, c.x + city.ORIGIN[0], c.y))
    return out


def replace_lists(res):
    """(required keys, optional keys, counts by label) for MoveReplaced of this batch"""
    req, opt = [], []
    cnt = Counter()
    unc_old, unc_pilot = res.get('unc_old', set()), res.get('unc_pilot', set())
    for o in res['rep_old']:
        k = (o['code'], o['c'][0] + city.ORIGIN[0], o['c'][1])
        (opt if o['i'] in unc_old else req).append(k)
        cnt[city.CODE_LABEL[o['code']]] += 1
    for p in res['rep_pilot']:
        k = (p['code'], p['c'][0] + city.ORIGIN[0], p['c'][1])
        (opt if p['i'] in unc_pilot else req).append(k)
        cnt['pilot ' + city.CODE_LABEL[p['code']]] += 1
    for f in res['rep_front']:
        code = {1: 11, 2: 12}[f['kind']]
        for k in wedge_keys(f['row'], code):
            req.append(k)
            cnt['frontier ' + KIND_NAME[f['kind']]] += 1
    for o in res['opt_old']:
        opt.append((o['code'], o['c'][0] + city.ORIGIN[0], o['c'][1]))
    for p in res['opt_pilot']:
        opt.append((p['code'], p['c'][0] + city.ORIGIN[0], p['c'][1]))
    for p in res.get('opt_alt', []):                # the pilot's float32 split doubts (city.split_variants)
        opt.append((p['code'], p['c'][0] + city.ORIGIN[0], p['c'][1]))
    key = lambda k: (k[0], round(k[1], 2), round(k[2], 2))  # noqa: E731
    return sorted(req, key=key), sorted(opt, key=key), cnt


def modules_of(res, targets):
    """cell modules: [(name, dict(cell, tris, ftris, segs, parts))]"""
    items = []                                      # (cell id, field, row, parts, centroid)
    for t in res['tris'] + res['comp']:
        items.append((cell_of(t['c']), 'tris', t['row'] + [t['kind']], t['n'], t['c']))
    for t in res['front']:
        items.append((cell_of(t['c']), 'ftris', t['row'] + [t['kind'], targets.index(t['target']) + 1 if t['target'] else 0], t['n'], t['c']))
    for a, b, w, kind in res['segs']:
        pm = Point((np.asarray(a) + np.asarray(b)) / 2)
        row = [r(a[0]), r(a[1]), r(b[0]), r(b[1]), r(w), SEG_KIND[kind]]
        if math.hypot(row[2] - row[0], row[3] - row[1]) < 0.05 + city.AMBIG:
            continue                                # the builder skips 0.05 or less; float32 may decide a hair either way
        items.append((cell_of(pm), 'segs', row, 1, pm))
    tot = Counter()
    for it in items:
        tot[it[0]] += it[3]
    big = {c for c, n in tot.items() if n > CAP}

    def quad(cid, pt):
        if cid not in big:
            return cid
        return f'{cid}q{int((pt.x % CELL) // (CELL / 2))}{int((pt.y % CELL) // (CELL / 2))}'
    by_cell = defaultdict(list)
    for c, f, row, n, pt in items:
        by_cell[quad(c, pt)].append((f, row, n))
    mods = []
    for cid in sorted(by_cell):
        groups, cur, n = [], [], 0
        for it in by_cell[cid]:
            if n + it[2] > CAP and cur:
                groups.append(cur)
                cur, n = [], 0
            cur.append(it)
            n += it[2]
        groups.append(cur)
        for gi, g in enumerate(groups):
            name = f'cell_{cid}' + ('' if gi == 0 else f'_{gi + 1}')
            mods.append((name, dict(cell=cid, tris=[x for f, row, _ in g if f == 'tris' for x in row],
                                    ftris=[x for f, row, _ in g if f == 'ftris' for x in row],
                                    segs=[x for f, row, _ in g if f == 'segs' for x in row],
                                    parts=sum(n_ for _, _, n_ in g))))
    return mods


def counts_of(mods):
    c = Counter()
    for _, m in mods:
        t = m['tris']
        for i in range(0, len(t), 7):
            c[KIND_NAME[int(t[i + 6])]] += len(world.rs.wedge_tris(t[i:i + 2], t[i + 2:i + 4], t[i + 4:i + 6]))
        t = m['ftris']
        for i in range(0, len(t), 8):
            c['frontier_' + KIND_NAME[int(t[i + 6])]] += len(world.rs.wedge_tris(t[i:i + 2], t[i + 2:i + 4], t[i + 4:i + 6]))
        s = m['segs']
        for i in range(0, len(s), 6):
            c[SEG_NAME[int(s[i + 5])]] += 1
    return c


def export(CW, plan, res, out_dir, expected=None, write=True):
    """writes the batch's Luau modules (when write) and returns the summary (counts, sha1, files)"""
    targets = sorted({t['target'] for t in res['front'] if t['target']})
    mods = modules_of(res, targets)
    counts = counts_of(mods)
    req, opt, cnt = replace_lists(res)
    b = next(x for x in plan['batches'] if x['id'] == res['id'])
    later_nb = [n for n in res['neighbours'] if n not in res['built_before']]
    man = dict(
        name=f"roadcity_{res['id']}", attribution='Map data (c) OpenStreetMap contributors, ODbL 1.0',
        note='generated by tools/roadvis/city_export.py (Road B, city batch); OFFLINE data, install needs owner approval',
        origin=[20000, 0, 0], bbox=[float(v) for v in res['box']], cellSize=CELL, maxPartsPerModule=CAP,
        tops=export_luau.TOPS, colors=export_luau.COLORS,
        thick=dict(asphalt=4.0, sidewalk=4.6, island=4.45, mark=0.05, kerb=0.02, grass=0.02, support=4.0),
        batch=dict(id=res['id'], seq=res['seq'], group=b['group'], cells=[list(c) for c in b['cells']],
                   box=[float(v) for v in res['box']], overlapMin=city.OVERLAP_MIN,
                   builtBefore=list(res['built_before']), notBuilt=later_nb, neighbours=list(res['neighbours']),
                   frontierFor=targets),
        modules=[n for n, _ in mods], cells=sorted({m['cell'] for _, m in mods}),
        counts=dict(parts=int(sum(m['parts'] for _, m in mods)), byKind=dict(counts),
                    own=int(sum(t['n'] for t in res['tris'])), completion=int(sum(t['n'] for t in res['comp'])),
                    frontier=int(sum(t['n'] for t in res['front'])), segs=len(res['segs']), meshTriangles=0),
        replace=dict(total=len(req), optional=len(opt), byName=dict(cnt), keys=[v for k in req for v in (k[0], r(k[1]), r(k[2]))],
                     optionalKeys=[v for k in opt for v in (k[0], r(k[1]), r(k[2]))], tolerance=0.3,
                     rule='old road-layer parts in the old containers, RoadVisPilot parts and frontier pieces tagged for '
                          'this batch whose footprint centre lies in the box (x0 <= x < x1) or which overlap it by >= overlapMin studs^2'),
        probe=dict(offsets=list(export_luau.PROBE_OFFSETS), foot=list(export_luau.FOOT),
                   samples=[x for row in res['probe_rows'] for x in row], stride=7,
                   legs=[dict(id=l['id'], name=l['name'], oneway=l['oneway'], lanes=l['lanes']) for l in res['probe_legs']],
                   expected=expected or {}),
    )
    hdr = ('-- generated by tools/roadvis/city_export.py (Road B city batch ' + res['id'] + ', OFFLINE data; Map data (c) '
           'OpenStreetMap contributors, ODbL 1.0); do not edit\n')
    files = {'manifest.luau': hdr + 'return ' + export_luau.lua(man) + '\n'}
    for name, m in mods:
        files[name + '.luau'] = hdr + 'return ' + export_luau.lua(dict(id=name[5:], cell=m['cell'], parts=m['parts'], tris=m['tris'],
                                                                      ftris=m['ftris'], segs=m['segs'], mesh=[])) + '\n'
    if write:
        os.makedirs(out_dir, exist_ok=True)
        for f in os.listdir(out_dir):
            if f.endswith('.luau'):
                os.remove(os.path.join(out_dir, f))
        for name, text in files.items():
            with open(os.path.join(out_dir, name), 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    digest = hashlib.sha1(''.join(files[k] for k in sorted(files)).encode('utf-8')).hexdigest()
    cell_parts = Counter()
    for _, m in mods:
        cell_parts[m['cell']] += m['parts']
    return dict(modules=len(mods), parts=man['counts']['parts'], byKind=dict(counts), own=man['counts']['own'],
                completion=man['counts']['completion'], frontier=man['counts']['frontier'], segs=len(res['segs']),
                replace=len(req), optional=len(opt), replaceByName=dict(cnt), cells=len(cell_parts),
                maxCellParts=max(cell_parts.values()) if cell_parts else 0, maxModuleParts=max((m['parts'] for _, m in mods), default=0),
                maxModuleKB=round(max(len(t) for t in files.values()) / 1024, 1), probeSamples=len(res['probe_rows']),
                frontierFor=targets, sha1=digest, files=sorted(files))
