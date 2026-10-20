"""Runs the REAL roblox/src/ServerStorage/PattayaRoute.luau (and the pre-fix copy PattayaRoute_old.luau next to this
file) in the luau CLI on the real road graph, job stands and building footprints from build/, and returns the
routes they produce for job, GPS and sprint scenarios. Also loads the same data in Python for independent checks
(on-road samples, building crossings). Used by tools/qa/tests/test_routing.py; see docs/ROUTING.md.

Data (as tools/studio/install.ps1 installs it):
  ServerStorage.PattayaData.graph (+ graph_part_*)  build/bira/roblox_corridor/graph.luau
  ServerStorage.PattayaData.jobs                    build/pattaya_wide/roblox/jobs.luau
  ServerStorage.PattayaData / PattayaDataWide / PattayaDataCorridor chunk_* (buildings only are loaded here)
"""
import glob
import math
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(os.path.dirname(HERE), 'tests')
if TESTS not in sys.path:
    sys.path.insert(0, TESTS)
import _qa  # noqa: E402

GRAPH_DIR = ('bira', 'roblox_corridor')
JOBS = ('pattaya_wide', 'roblox', 'jobs.luau')
CHUNK_DIRS = {'PattayaData': ('central_pattaya', 'roblox'), 'PattayaDataWide': ('pattaya_wide', 'roblox'),
              'PattayaDataCorridor': ('bira', 'roblox_corridor')}
OSM_BIRA, OSM_CENTRAL = 1457068485, 423748313  # PattayaGPSServer DESTINATIONS
GPS_SNAP = 700
SNAP_MARGIN = 8  # PattayaRoute.SNAP_MARGIN
BUILDING_INSET = 1.0  # PattayaRoute.BUILDING_INSET
BIRA_PADDOCK = (45002.76 - 20000, 2796.51)  # roblox/data/circuits/bira.luau paddock (world) -> map-local
GARAGE_SPAWN = (1144.87, -191.99)  # build/central_pattaya manifest spawn (the garage ring is beside it)
GRID_FWD = (-0.393, 0.919)

_CACHE = {}


def _read(path):
    return _qa.read(path)


# ---------------------------------------------------------------------------------------------- data in Python
def graph():
    """{'nodes': [(x, z)], 'edges': [(a, b, len, tier, width, [(x, z)])], 'baseNodes', 'osm': {id: index}}"""
    if 'graph' in _CACHE:
        return _CACHE['graph']
    d = _qa.need_build(*GRAPH_DIR)
    t = _read(os.path.join(d, 'graph.luau'))
    flat = [float(x) for x in re.search(r'nodes = \{([^}]*)\}', t).group(1).split(',')]
    nodes = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
    osm = [int(x) for x in re.search(r'osmIds = \{([^}]*)\}', t).group(1).split(',')]
    pat = re.compile(r'\{ (\d+), (\d+), ([\d.]+), (\d+), ([\d.]+), \{([^}]*)\} \}')

    def edges_of(s):
        out = []
        for a, b, ln, ti, w, f in pat.findall(s):
            v = [float(x) for x in f.split(',')]
            out.append((int(a), int(b), float(ln), int(ti), float(w), [(v[i], v[i + 1]) for i in range(0, len(v), 2)]))
        return out
    edges = edges_of(t)
    parts = sorted(glob.glob(os.path.join(d, 'graph_part_*.luau')))
    for p in parts:
        edges += edges_of(_read(p))
    base = int(re.search(r'baseNodes = (\d+)', t).group(1))
    g = {'nodes': nodes, 'edges': edges, 'baseNodes': base, 'osm': {o: i + 1 for i, o in enumerate(osm)},
         'parts': [os.path.basename(p)[:-5] for p in parts], 'dir': d}
    _CACHE['graph'] = g
    return g


def stands():
    p = _qa.need_build(*JOBS)
    rows = re.findall(r'id = "(\w+)", kind = "(\w+)", label = "([^"]*)", x = ([-\d.]+), z = ([-\d.]+), dx = ([-\d.]+), '
                      r'dz = ([-\d.]+), kx = ([-\d.]+), kz = ([-\d.]+)', _read(p))
    return [dict(id=r[0], kind=r[1], label=r[2], x=float(r[3]), z=float(r[4]), dx=float(r[5]), dz=float(r[6]))
            for r in rows]


def chunk_buildings():
    """{folder: {chunk module name: [x, z, w, d, h, yaw, palette, osmId, ...]}} (non-empty only)"""
    if 'chunks' in _CACHE:
        return _CACHE['chunks']
    res = {}
    for folder, rel in CHUNK_DIRS.items():
        d = _qa.need_build(*rel)
        res[folder] = {}
        for f in sorted(glob.glob(os.path.join(d, 'chunk_*.luau'))):
            m = re.search(r'buildings = \{([^}]*)\}', _read(f))
            if m and m.group(1).strip():
                res[folder][os.path.basename(f)[:-5]] = [float(x) for x in m.group(1).split(',')]
    _CACHE['chunks'] = res
    return res


class Geo:
    """Spatial lookups on the Python copy of the data: distance to the road graph, building crossings."""
    CELL = 64.0

    def __init__(self):
        g = graph()
        self.edges = g['edges']
        self.seg_grid = {}
        for ei, e in enumerate(self.edges):
            pts = e[5]
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                r = e[4] / 2 + SNAP_MARGIN
                for cx, cz in self._cells(min(a[0], b[0]) - r, max(a[0], b[0]) + r, min(a[1], b[1]) - r,
                                          max(a[1], b[1]) + r):
                    self.seg_grid.setdefault((cx, cz), []).append((a, b, e[4], ei))
        self.boxes = []
        for folder in chunk_buildings().values():
            for rows in folder.values():
                for i in range(0, len(rows) - 7, 8):
                    self.boxes.append(rows[i:i + 6] + [rows[i + 7]])
        self.box_grid = {}
        for bi, bx in enumerate(self.boxes):
            r = math.hypot(bx[2], bx[3]) / 2
            for c in self._cells(bx[0] - r, bx[0] + r, bx[1] - r, bx[1] + r):
                self.box_grid.setdefault(c, []).append(bi)

    def _cells(self, x0, x1, z0, z1):
        C = self.CELL
        for cx in range(int(math.floor(x0 / C)), int(math.floor(x1 / C)) + 1):
            for cz in range(int(math.floor(z0 / C)), int(math.floor(z1 / C)) + 1):
                yield cx, cz

    def road_slack(self, p):
        """min over edges of (distance to the edge centreline - half its width); <= SNAP_MARGIN = on that road"""
        best = math.inf
        for a, b, w, _ in self.seg_grid.get((int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))), ()):
            best = min(best, _qa.point_seg_dist(p, a, b) - w / 2)
        return best

    def centreline_dist(self, p):
        best = math.inf
        for a, b, _, _ in self.seg_grid.get((int(math.floor(p[0] / self.CELL)), int(math.floor(p[1] / self.CELL))), ()):
            best = min(best, _qa.point_seg_dist(p, a, b))
        return best

    @staticmethod
    def seg_hits_box(a, b, bx, inset=BUILDING_INSET):
        x, z, w, d, _h, yaw = bx[:6]
        r = math.radians(yaw)
        c, s = math.cos(r), math.sin(r)

        def loc(p):
            dx, dz = p[0] - x, p[1] - z
            return dx * c + dz * s, -dx * s + dz * c
        p, q = loc(a), loc(b)
        hx, hz = w / 2 - inset, d / 2 - inset
        if hx <= 0 or hz <= 0:
            return False
        t0, t1 = 0.0, 1.0
        for p0, dp, lim in ((p[0], q[0] - p[0], hx), (p[1], q[1] - p[1], hz)):
            if abs(dp) < 1e-12:
                if abs(p0) > lim:
                    return False
            else:
                ta, tb = (-lim - p0) / dp, (lim - p0) / dp
                if ta > tb:
                    ta, tb = tb, ta
                t0, t1 = max(t0, ta), min(t1, tb)
                if t0 > t1:
                    return False
        return True

    def buildings_crossed(self, a, b):
        seen, hits = set(), []
        for c in self._cells(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])):
            for bi in self.box_grid.get(c, ()):
                if bi not in seen:
                    seen.add(bi)
                    if self.seg_hits_box(a, b, self.boxes[bi]):
                        hits.append(int(self.boxes[bi][6]))
        return hits

    def off_road_runs(self, pts, step=4.0):
        """lengths of the stretches of the polyline whose samples are off every road slab (> half width + margin)"""
        runs, cur = [], 0.0
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            L = _qa.dist2(a, b)
            n = max(1, int(L / step))
            for k in range(n):
                t = (k + 0.5) / n
                p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                if self.road_slack(p) > SNAP_MARGIN:
                    cur += L / n
                elif cur > 0:
                    runs.append(cur)
                    cur = 0.0
        if cur > 0:
            runs.append(cur)
        return runs


def geo():
    if 'geo' not in _CACHE:
        _CACHE['geo'] = Geo()
    return _CACHE['geo']


# ---------------------------------------------------------------------------------------------- scenarios
def gps_scenarios():
    g = graph()
    out = []
    left = (GRID_FWD[1], -GRID_FWD[0])
    for name, k in (('garage_spawn', 0), ('garage_left20', 20), ('garage_right20', -20)):
        p = (GARAGE_SPAWN[0] + left[0] * k, GARAGE_SPAWN[1] + left[1] * k)
        out.append(dict(name=name + '>bira', x=p[0], z=p[1], target=OSM_BIRA))
        out.append(dict(name=name + '>central', x=p[0], z=p[1], target=OSM_CENTRAL))
    out.append(dict(name='bira_paddock>central', x=BIRA_PADDOCK[0], z=BIRA_PADDOCK[1], target=OSM_CENTRAL))
    out.append(dict(name='bira_paddock>bira', x=BIRA_PADDOCK[0], z=BIRA_PADDOCK[1], target=OSM_BIRA))
    for s in stands():
        out.append(dict(name=f'stand:{s["id"]}>bira', x=s['x'], z=s['z'], target=OSM_BIRA))
        out.append(dict(name=f'stand:{s["id"]}>central', x=s['x'], z=s['z'], target=OSM_CENTRAL))
    rng = random.Random(15)
    edges = g['edges']
    for i in range(40):  # cars on random roads (city and corridor), anywhere across the road width
        e = edges[rng.randrange(len(edges))]
        pts = e[5]
        j = rng.randrange(len(pts) - 1)
        a, b = pts[j], pts[j + 1]
        t = rng.random()
        L = _qa.dist2(a, b) or 1
        nx, nz = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        off = (rng.random() * 2 - 1) * e[4] / 2 * 0.85
        p = (a[0] + (b[0] - a[0]) * t + nx * off, a[1] + (b[1] - a[1]) * t + nz * off)
        out.append(dict(name=f'car{i:02d}>{"bira" if i % 2 else "central"}', x=p[0], z=p[1],
                        target=OSM_BIRA if i % 2 else OSM_CENTRAL))
    for d in out:
        d.setdefault('snap', GPS_SNAP)
    return out


def snap_scenarios(limit=30):
    """points off the road (not inside a building, <= 120 studs from the graph) whose NEAREST edge projection crosses a
    building: Route.snap must pick another edge (or report the fallback)"""
    if 'snap' in _CACHE:
        return _CACHE['snap']
    G = geo()
    out = []
    rng = random.Random(21)
    tries = 0
    while len(out) < limit and tries < 20000:
        tries += 1
        p = (rng.uniform(-1400, 3000), rng.uniform(-3100, 3100))  # the central slice (densest buildings)
        if G.road_slack(p) <= SNAP_MARGIN + 4:
            continue
        if any(G.seg_hits_box(p, p, G.boxes[bi], inset=0) for bi in G.box_grid.get(
                (int(math.floor(p[0] / G.CELL)), int(math.floor(p[1] / G.CELL))), ())):
            continue  # inside a building
        best = None
        cx, cz = int(math.floor(p[0] / G.CELL)), int(math.floor(p[1] / G.CELL))
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for a, b, _w, ei in G.seg_grid.get((cx + dx, cz + dz), ()):
                    d = _qa.point_seg_dist(p, a, b)
                    if best is None or d < best[0]:
                        best = (d, a, b, ei)
        if not best or best[0] > 120:
            continue
        d, a, b = best[:3]
        abx, abz = b[0] - a[0], b[1] - a[1]
        l2 = abx * abx + abz * abz
        t = 0 if l2 <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * abz) / l2))
        q = (a[0] + abx * t, a[1] + abz * t)
        if G.buildings_crossed(p, q):
            out.append(dict(name=f'snap{len(out):02d}', x=p[0], z=p[1]))
    _CACHE['snap'] = out
    return out


def sprint_scenarios():
    """pointToPoint calls like PattayaSprintServer (from a car), PattayaStreetRace (1500-2600) and the events (from
    a junction), each with a fixed seed"""
    g = graph()
    rng = random.Random(7)
    out = []
    starts = [(GARAGE_SPAWN, GRID_FWD)] + [((s['x'], s['z']), (s['dx'], s['dz'])) for s in stands()[:8]]
    for k in range(8):
        n = g['nodes'][rng.randrange(g['baseNodes'])]
        starts.append((n, (1.0, 0.0)))
    for i, (p, look) in enumerate(starts):
        for minLen, maxLen, spacing in ((1200, 2400, 160), (1500, 2600, 150)):
            out.append(dict(x=p[0], z=p[1], lx=look[0], lz=look[1], minLen=minLen, maxLen=maxLen, spacing=spacing,
                            seed=1000 + i))
    return out


def _lua(v):
    if isinstance(v, dict):
        return '{' + ', '.join(f'{k} = {_lua(x)}' for k, x in v.items()) + '}'
    if isinstance(v, (list, tuple)):
        return '{' + ', '.join(_lua(x) for x in v) + '}'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return repr(v)


def _module(name, source, head='local require, game = REQ, GAME\n'):
    return f'{name} = (function(...)\n{head}{source}\nend)()\n'


def build_script(new_source=None):
    g = graph()
    d = g['dir']
    parts = [_read(os.path.join(TESTS, 'luau', 'prelude.luau')), _read(os.path.join(HERE, 'env.luau'))]
    parts.append('local PD = SERVER_STORAGE:add(NewInst("PattayaData", "Folder"))\n')
    parts.append('local FOLDERS = {PattayaData = PD, PattayaDataWide = SERVER_STORAGE:add(NewInst("PattayaDataWide", '
                 '"Folder")), PattayaDataCorridor = SERVER_STORAGE:add(NewInst("PattayaDataCorridor", "Folder"))}\n')
    parts.append('PD:add(NewInst("graph", "ModuleScript", function(script)\nlocal require = REQ\n'
                 + _read(os.path.join(d, 'graph.luau')) + '\nend))\n')
    for p in g['parts']:
        parts.append(f'PD:add(NewInst("{p}", "ModuleScript", function(script)\n'
                     + _read(os.path.join(d, p + '.luau')) + '\nend))\n')
    parts.append('PD:add(NewInst("jobs", "ModuleScript", function(script)\n' + _read(_qa.need_build(*JOBS))
                 + '\nend))\n')
    for folder, chunks in chunk_buildings().items():
        for name, rows in chunks.items():
            nums = ','.join(f'{x:g}' for x in rows)
            parts.append(f'FOLDERS.{folder}:add(NewInst("{name}", "ModuleScript", function() return {{buildings = '
                         f'{{{nums}}}}} end))\n')
    parts.append(_module('OLD_ROUTE', _read(os.path.join(HERE, 'PattayaRoute_old.luau'))))
    parts.append(_module('NEW_ROUTE', new_source if new_source is not None
                         else _qa.src(os.path.join('ServerStorage', 'PattayaRoute.luau'))))
    parts.append('SCEN = ' + _lua({'gps': gps_scenarios(), 'sprint': sprint_scenarios(), 'snap': snap_scenarios()})
                 + '\n')
    parts.append(_read(os.path.join(HERE, 'tail.luau')))
    return ''.join(parts)


def _pts(text):
    v = [float(x) for x in text.split()]
    return [(v[i], v[i + 1]) for i in range(0, len(v), 2)]


def run():
    if 'run' in _CACHE:
        return _CACHE['run']
    code, out = _qa.run_luau(build_script(), timeout=600)
    res = {'code': code, 'raw': out, 'JOB': {'old': {}, 'new': {}}, 'JOBN': {'old': {}, 'new': {}},
           'JOBERR': [], 'GPS': {'old': {}, 'new': {}}, 'GPSERR': {'old': {}, 'new': {}},
           'SPR': {'old': {}, 'new': {}}, 'SPRERR': {'old': {}, 'new': {}}, 'XB': {}, 'ANCHOR': {}, 'TIME': {},
           'CHUNKREQ': {}, 'SNAP': {}, 'DONE': False}
    for line in out.splitlines():
        f = line.split('\t')
        k = f[0]
        if k == 'JOB':
            res['JOB'][f[1]][(f[2], f[3])] = dict(length=float(f[4]), pts=_pts(f[5]))
        elif k == 'JOBN':
            res['JOBN'][f[1]][f[2]] = int(f[3])
        elif k == 'JOBERR':
            res['JOBERR'].append(f[1:])
        elif k == 'GPS':
            res['GPS'][f[1]][f[2]] = dict(start=_pts(f[3])[0], length=float(f[4]), pts=_pts(f[5]))
        elif k == 'GPSERR':
            res['GPSERR'][f[1]][f[2]] = f[3]
        elif k == 'SPR':
            res['SPR'][f[1]][int(f[2])] = dict(length=float(f[3]), blob=f[4])
        elif k == 'SPRERR':
            res['SPRERR'][f[1]][int(f[2])] = f[3]
        elif k == 'XB':
            res['XB'][f[1]] = dict(crosses=f[2] == '1', length=float(f[3]))
        elif k == 'ANCHOR':
            res['ANCHOR'][f[1]] = dict(node=int(f[2]), q=_pts(f[3])[0], d=float(f[4]))
        elif k == 'TIME':
            res['TIME'][(f[1], f[2])] = float(f[3])
        elif k == 'SNAP':
            res['SNAP'][f[1]] = dict(p=_pts(f[2])[0], old=_pts(f[3])[0], new=_pts(f[4])[0], dOld=float(f[5]),
                                     dNew=float(f[6]))
        elif k == 'CHUNKREQ':
            res['CHUNKREQ'][f[1]] = int(f[2])
        elif k == 'DONE':
            res['DONE'] = True
    _CACHE['run'] = res
    return res


# ---------------------------------------------------------------------------------------------- route metrics
def job_metrics(r):
    """first / last connector (stand <-> graph), the longest off-road stretch, buildings crossed"""
    G = geo()
    pts = r['pts']
    crossed = sorted({b for i in range(len(pts) - 1) for b in G.buildings_crossed(pts[i], pts[i + 1])})
    runs = G.off_road_runs(pts)
    return dict(first=_qa.dist2(pts[0], pts[1]), last=_qa.dist2(pts[-2], pts[-1]), offroad=max(runs, default=0.0),
                crossed=crossed, length=r['length'])


def gps_metrics(r):
    G = geo()
    pts = [r['start']] + r['pts']  # the car, then the route (the client draws car -> first point)
    crossed = sorted({b for i in range(len(pts) - 1) for b in G.buildings_crossed(pts[i], pts[i + 1])})
    runs = G.off_road_runs(r['pts'])
    return dict(first=_qa.dist2(pts[0], pts[1]), offroad=max(runs, default=0.0), crossed=crossed,
                start_slack=G.road_slack(r['start']), length=r['length'])


if __name__ == '__main__':
    res = run()
    print(res['code'], res['DONE'], res['TIME'])
    if not res['DONE']:
        print(res['raw'][-3000:])
