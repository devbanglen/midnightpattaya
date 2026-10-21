"""Studio data for PattayaRoadGroundBuilder (the ground at road level, pilot at the Road B junction). OFFLINE.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py ground       (writes build/roadground/roblox/*.luau)

manifest.luau  the voxel column box (world voxel indices, 4-stud), the ramp rule (the builder computes the occupancy
               from it, exactly as ground.ramp_factor), one material string per voxel column row, the calibration
               probe columns, the road-to-ground edge check pairs, the Road B state the ground expects, the offline
               expectation of RG.Probe
edges_<cx>_<cz>.luau   the kerb bands of one 256-stud cell (one Atomic Model each, <= 600 parts)
"""
import hashlib
import json
import math
import os
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import box

from tools.roadvis import export_luau, ground, world

CELL = 256.0
CAP = 600
MAT_CHAR = {0: '.', 1: 'g', 2: 'p'}
PROBE_STEP = 64.0           # calibration columns: every 64 studs inside the plateau, 8 studs from its edge
GRID = 2.0                  # RG.Probe raycast grid (studs)
EDGE_STEP = 8.0             # one road-to-ground edge check pair every 8 studs of edge


def r(v, n=2):
    return round(float(v), n)


def calibration_columns(G):
    """world centres of plateau columns on a 64-stud lattice, >= 8 studs inside the plateau edge"""
    x0, z0, x1, z1 = G['cfg']['plateau_world']
    out = []
    for x in np.arange(x0 + 8, x1 - 7, PROBE_STEP):
        for z in np.arange(z0 + 8, z1 - 7, PROBE_STEP):
            i, k = int(math.floor(x / 4)), int(math.floor(z / 4))
            out.append((i * 4 + 2.0, k * 4 + 2.0))
    return out


def edge_pairs(st, area):
    """road-to-ground edges of the state (road_only edge samples facing the ground), one pair every EDGE_STEP studs:
    (inside point 0.6 stud on the road, outside point 1.5 studs out on the ground), world; the expected step"""
    E = ground.edge_samples(st, area, step=1.0, road_only=True)
    face = ~E['bld'] & ~E['slot'] & ~E['kerb']
    pairs = []
    last = None
    for j in np.nonzero(face)[0]:
        p, o = E['p'][j], E['out'][j]
        if last is not None and np.hypot(*(p - last)) < EDGE_STEP:
            continue
        a, b = p - o * 0.6, p + o * 1.5
        ha, hb = st.at([a])[0], st.at([b])[0]
        if not (0.95 <= ha <= 1.01) or hb > 0.5 or hb < ground.TERRAIN_TOP + 1e-6 and st.ground.G is not None:
            continue                      # the pair must start on road and end on the raised ground
        pairs.append((a[0] + world.ORIGIN[0], a[1], b[0] + world.ORIGIN[0], b[1], ha - hb))
        last = p
    return pairs


def probe_expected(st, plateau):
    """what RG.Probe's 2-stud raycast grid should find: neighbour steps >= 1.5 between floor hits (tops <= 1.8; walls,
    props and buildings are not floors), the highest floor step"""
    x0, z0, x1, z1 = plateau.bounds
    xs = np.arange(x0 + GRID / 2, x1, GRID)
    zs = np.arange(z0 + GRID / 2, z1, GRID)
    X, Z = np.meshgrid(xs, zs, indexing='ij')
    h = st.at(np.stack([X.ravel(), Z.ravel()], axis=1)).reshape(X.shape)
    floor = h <= 1.8
    worst = 0.0
    drops = 0
    for di, dj in ((1, 0), (0, 1)):
        a, b = h[:h.shape[0] - di, :h.shape[1] - dj], h[di:, dj:]
        ok = floor[:h.shape[0] - di, :h.shape[1] - dj] & floor[di:, dj:]
        d = np.where(ok, np.abs(a - b), 0.0)
        worst = max(worst, float(d.max()))
        drops += int((d >= ground.DROP).sum())
    gmask = floor & (np.abs(h - st.ground.at(np.stack([X.ravel(), Z.ravel()], axis=1)).reshape(X.shape)) < 1e-6)
    return dict(rays=int(h.size), floorPairsOver1_5=drops, maxFloorStep=r(worst, 3), groundHits=int(gmask.sum()))


def lua(v):
    """Luau literal; floats with up to 6 decimals (export_luau.lua keeps 3, which turned occTop 0.6075 into 0.608)"""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        s = ('%.6f' % float(v)).rstrip('0').rstrip('.')
        return s if s not in ('-0', '') else '0'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, dict):
        return '{' + ', '.join(f'{k} = {lua(x)}' if str(k).isidentifier() else f'[{lua(k)}] = {lua(x)}' for k, x in v.items()) + '}'
    if isinstance(v, (list, tuple)):
        return '{' + ','.join(lua(x) for x in v) + '}'
    raise TypeError(type(v))


def export(W, PB, G, states, res, out_dir):
    cfg = G['cfg']
    x0, z0, x1, z1 = cfg['plateau_world']
    plateau = box(x0 - world.ORIGIN[0], z0, x1 - world.ORIGIN[0], z1)
    st = states['B_ground']
    cols = [''.join(MAT_CHAR[int(m)] for m in G['mat'][i]) for i in range(G['ni'])]
    # columns that the rule gives occupancy > 0 must carry a material, the others '.'
    assert all((G['mat'][i] > 0).sum() == (G['occ'][i] > 0).sum() for i in range(G['ni']))
    probes = calibration_columns(G)
    pairs = edge_pairs(st, plateau)
    exp = probe_expected(st, plateau)
    exp_today = probe_expected(states['B'], plateau)
    # kerb bands per 256-stud cell
    cells = defaultdict(list)
    for s in G['kerbs']:
        a, b = np.asarray(s['a']), np.asarray(s['b'])
        m = (a + b) / 2
        cid = f'{int(math.floor(m[0] / CELL))}_{int(math.floor(m[1] / CELL))}'
        cells[cid] += [r(a[0]), r(a[1]), r(b[0]), r(b[1]), r(s['w'])]
    mods = {}
    for cid, v in sorted(cells.items()):
        n = len(v) // 5
        if n > CAP:
            raise ValueError(f'kerb cell {cid}: {n} parts > {CAP}')
        mods[f'edges_{cid}'] = dict(id=cid, cell=cid, parts=n, segs=v)
    i1, k1 = G['i0'] + G['ni'], G['k0'] + G['nk']
    man = dict(
        name=cfg['name'], attribution='Map data (c) OpenStreetMap contributors, ODbL 1.0',
        note='generated by tools/roadvis/ground_export.py (ground at road level, pilot at the Road B junction); OFFLINE '
             'data; the terrain write needs the owner\'s explicit permission and a fresh place backup',
        origin=[20000, 0, 0], plateau=[float(v) for v in cfg['plateau_world']], flat=cfg['flat'], ramp=cfg['ramp'],
        top=cfg['top'], window=list(cfg['window']), terrainTop=ground.TERRAIN_TOP, occTop=round(G['o_top'], 6),
        layer=[-4, 0], region=dict(i0=G['i0'], k0=G['k0'], ni=G['ni'], nk=G['nk']),
        # inclusive voxel box copied before the first write: the written columns plus one voxel all round, y -8 .. 4
        backup=dict(i0=G['i0'] - 1, k0=G['k0'] - 1, i1=i1, k1=k1, y0=-2, y1=0),
        expected=dict(below='Ground', belowOcc=1, layer='Air', above='Air'),
        materials=['Ground', 'Pavement'], pavementColor=list(cfg['pavement_color']), columns=cols,
        calibrate=dict(probes=[v for p in probes for v in p], tol=0.015, flat=0.03, maxWrites=4),
        edgeChecks=[r(v, 3) if k == 4 else r(v) for p in pairs for k, v in enumerate(p)],
        kerb=dict(top=cfg['kerb_top'], bottom=cfg['kerb_bottom'], color=list(cfg['kerb_color']), out=cfg['kerb_out']),
        modules=sorted(mods), cells=sorted(cells),
        roadB=dict(folder='RoadVisPilot', cells=7, parts=1822, backup='RoadVisBackup', moved=782),
        counts=dict(columns=G['counts']['columns'], written=G['counts']['written'], plateau=G['counts']['plateau'],
                    ramp=G['counts']['ramp'], pavement=G['counts']['pavement'], ground=G['counts']['ground'],
                    kerbParts=sum(m['parts'] for m in mods.values()), edgeChecks=len(pairs), probes=len(probes)),
        probe=dict(grid=GRID, expected=exp, expectedWithoutGround=exp_today,
                   edgeStepMax=r(max(p[4] for p in pairs), 3) if pairs else None,
                   edgeStepMin=r(min(p[4] for p in pairs), 3) if pairs else None),
    )
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith('.luau'):
            os.remove(os.path.join(out_dir, f))
    hdr = ('-- generated by tools/roadvis/ground_export.py (ground at road level pilot, OFFLINE data; Map data (c) '
           'OpenStreetMap contributors, ODbL 1.0); do not edit\n')
    files = {'manifest.luau': hdr + 'return ' + lua(man) + '\n'}
    for name, m in mods.items():
        files[name + '.luau'] = hdr + 'return ' + lua(m) + '\n'
    for name, text in files.items():
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
    digest = hashlib.sha1(''.join(files[k] for k in sorted(files)).encode('utf-8')).hexdigest()
    return dict(files=sorted(files), sha1=digest, kerbParts=man['counts']['kerbParts'], cells=len(mods),
                edgeChecks=len(pairs), probes=len(probes), expected=exp, maxKB=round(max(len(t) for t in files.values()) / 1024, 1))
