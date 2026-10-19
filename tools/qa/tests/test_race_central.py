"""Street racing on the city roads: the Central Loop checkpoint race (PattayaRaceServer reads the gates PattayaBuilder
builds from build/central_pattaya race data), Street Sprint / Street Challenge / event route parameters and the road
graph they route on (PattayaRoute)."""
import math
import re
import unittest

import _qa


def race_of(dataset):
    return _qa.load_json(_qa.need_build(dataset, 'layout.json'))['race']


def path_pts(race):
    p = race['path']
    return [tuple(x) for x in p] if p and isinstance(p[0], list) else [(p[i], p[i + 1]) for i in range(0, len(p), 2)]


class CentralLoopRace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.race = race_of('central_pattaya')
        cls.path = path_pts(cls.race)
        cls.cps = cls.race['checkpoints']

    def test_start_finish_defined(self):
        r = self.race
        self.assertEqual(r['id'], 'central_loop')
        self.assertGreaterEqual(r['laps'], 1)
        self.assertGreaterEqual(len(self.cps), 8)
        # gate 1 is the start/finish: the race server starts a run on gates[1] and finishes a lap on it
        self.assertLess(_qa.dist2((self.cps[0]['x'], self.cps[0]['z']), self.path[0]), 5,
                        'checkpoint 1 must sit at the start of the race path')

    def test_path_closed_and_length(self):
        self.assertLess(_qa.dist2(self.path[0], self.path[-1]), 40, 'race path is not a closed loop')
        L = _qa.polyline_length(self.path, closed=True)
        self.assertAlmostEqual(L, self.race['length_studs'], delta=0.02 * L)

    def test_checkpoints_on_path_in_order(self):
        pts = self.path
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + _qa.dist2(pts[i - 1], pts[i]))

        def arc(p):
            best, bs = 1e18, 0
            for i in range(len(pts) - 1):
                d = _qa.point_seg_dist(p, pts[i], pts[i + 1])
                if d < best:
                    seg = _qa.dist2(pts[i], pts[i + 1])
                    a, b = pts[i], pts[i + 1]
                    t = 0 if seg == 0 else max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / seg ** 2))
                    best, bs = d, cum[i] + seg * t
            return best, bs

        s_prev = -1
        for i, c in enumerate(self.cps, 1):
            d, s = arc((c['x'], c['z']))
            self.assertLess(d, c['w'] / 2, f'checkpoint {i} is {d:.1f} studs off the race path')
            self.assertGreater(s, s_prev, f'checkpoint {i} is not after checkpoint {i - 1} along the path')
            s_prev = s

    def test_checkpoint_spacing_and_unique(self):
        cps = self.cps
        gaps = [_qa.dist2((cps[i]['x'], cps[i]['z']), (cps[(i + 1) % len(cps)]['x'], cps[(i + 1) % len(cps)]['z']))
                for i in range(len(cps))]
        # PattayaRaceServer: more than 260 studs/s between two gates = invalid run; a nitro car (240) must be able to
        # make every leg, and no two gates may coincide (a duplicate would count twice in one crossing)
        self.assertGreater(min(gaps), 60, f'two checkpoints only {min(gaps):.0f} studs apart')
        self.assertLess(max(gaps), 900, f'checkpoint gap {max(gaps):.0f} studs')

    def test_checkpoint_facing_along_route(self):
        pts = self.path
        for i, c in enumerate(self.cps, 1):
            k = min(range(len(pts) - 1), key=lambda j: _qa.point_seg_dist((c['x'], c['z']), pts[j], pts[j + 1]))
            tx, tz = pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]
            tl = math.hypot(tx, tz)
            dl = math.hypot(c['dx'], c['dz'])
            dot = (tx * c['dx'] + tz * c['dz']) / (tl * dl)
            self.assertGreater(dot, 0.8, f'checkpoint {i} faces {dot:.2f} against the route direction')

    def test_grid_behind_start_and_facing_forward(self):
        c0 = self.cps[0]
        fx, fz = c0['dx'], c0['dz']
        fl = math.hypot(fx, fz)
        for i, g in enumerate(self.race['grid'], 1):
            rx, rz = g['x'] - c0['x'], g['z'] - c0['z']
            along = (rx * fx + rz * fz) / fl
            self.assertTrue(-120 < along < 0, f'grid slot {i} is {along:.0f} studs along the start direction')
            dot = (g['dx'] * fx + g['dz'] * fz) / (math.hypot(g['dx'], g['dz']) * fl)
            self.assertGreater(dot, 0.9, f'grid slot {i} not facing the start line')

    def test_route_edges_exist_in_graph(self):
        g = _qa.load_json(_qa.need_build('central_pattaya', 'graph_game.json'))
        ids = {e['id'] for e in g['edges']}
        missing = [e for e in self.race['route_edges'] if e not in ids]
        self.assertEqual(missing, [])

    def test_manifest_and_wide_layout_carry_same_race(self):
        man = _qa.read(_qa.need_build('central_pattaya', 'roblox', 'manifest.luau'))
        m = re.search(r'race = \{ id = "(\w+)".*?laps = (\d+), lengthStuds = (\d+),\s*checkpoints = \{(.*?)\n\s*\},',
                      man, re.S)
        self.assertIsNotNone(m, 'race block not found in build/central_pattaya/roblox/manifest.luau')
        self.assertEqual(m.group(1), self.race['id'])
        self.assertEqual(int(m.group(2)), self.race['laps'])
        self.assertEqual(int(m.group(3)), self.race['length_studs'])
        self.assertEqual(len(re.findall(r'\{ x = ', m.group(4))), len(self.cps))
        wide = race_of('pattaya_wide')
        self.assertEqual(wide['checkpoints'], self.cps, 'the wide world must keep the tested Central Loop')

    def test_race_server_reads_what_builder_writes(self):
        b = _qa.src('ServerStorage/PattayaBuilder.luau')
        s = _qa.src('ServerScriptService/PattayaRaceServer.server.luau')
        for attr in ('Laps', 'LengthStuds'):
            self.assertIn(f'SetAttribute("{attr}"', b)
            self.assertIn(f'GetAttribute("{attr}")', s)
        self.assertIn('gate:SetAttribute("Index", i)', b)
        self.assertIn('GetAttribute("Index")', s)
        self.assertIn('cps.Name = "Checkpoints"', b)
        self.assertIn('race.Checkpoints', s)


class TeleportLimitsConsistent(unittest.TestCase):
    """Every server's 'too fast = teleport' limit must stay above the fastest legal car (CarSpecs.NITRO_LIMIT)."""

    def test_max_speed_above_nitro_limit(self):
        nitro = int(re.search(r'NITRO_LIMIT = (\d+)', _qa.src('ReplicatedStorage/CarSpecs.luau')).group(1))
        files = ['ServerScriptService/PattayaRaceServer.server.luau', 'ServerScriptService/PattayaSprintServer.server.luau',
                 'ServerStorage/CheckpointValidator.luau', 'ServerScriptService/PattayaJobsServer.server.luau',
                 'ServerStorage/PattayaStreetRace.luau']
        found = {}
        for f in files:
            m = re.search(r'MAX_SPEED\s*=\s*(\d+)', _qa.src(f))
            self.assertIsNotNone(m, f)
            found[f] = int(m.group(1))
        for f, v in found.items():
            self.assertGreaterEqual(v, nitro + 10, f'{f}: MAX_SPEED {v} vs NITRO_LIMIT {nitro}')


class SprintRoutes(unittest.TestCase):
    """PattayaSprintServer's route request vs the road graph (the server routes on PattayaData.graph)."""

    def test_sprint_parameters_sane(self):
        s = _qa.src('ServerScriptService/PattayaSprintServer.server.luau')
        lo, hi = map(int, re.search(r'MIN_LEN, MAX_LEN = (\d+), (\d+)', s).groups())
        sp = int(re.search(r'CP_SPACING = (\d+)', s).group(1))
        tl = int(re.search(r'TIME_LIMIT = (\d+)', s).group(1))
        self.assertLess(lo, hi)
        self.assertGreaterEqual(lo / sp, 4, 'a sprint should have at least 4 checkpoints')
        # the longest sprint at the hatch's top speed (160) must fit the time limit with margin
        self.assertLess(hi / 160 * 1.5, tl, f'{hi} studs in {tl} s')

    def test_graph_integrity_and_connectivity(self):
        for ds in ('central_pattaya', 'pattaya_wide'):
            g = _qa.load_json(_qa.need_build(ds, 'graph_game.json'))
            with self.subTest(ds):
                nodes = g['nodes']
                ids = [e['id'] for e in g['edges']]
                self.assertEqual(len(ids), len(set(ids)), 'duplicate edge ids')
                adj = {}
                bad = []
                for e in g['edges']:
                    if str(e['a']) not in nodes or str(e['b']) not in nodes:
                        bad.append(e['id'])
                    if len(e['pts']) < 2 or _qa.polyline_length([tuple(p) for p in e['pts']]) <= 0:
                        bad.append(e['id'] + ' (no length)')
                    adj.setdefault(str(e['a']), set()).add(str(e['b']))
                    adj.setdefault(str(e['b']), set()).add(str(e['a']))
                self.assertEqual(bad, [])
                # largest connected component (sprints start at the nearest junction ahead: a car on a cut-off
                # fragment could get no route)
                seen, best = set(), 0
                for n in adj:
                    if n in seen:
                        continue
                    comp, todo = {n}, [n]
                    while todo:
                        for m in adj[todo.pop()]:
                            if m not in comp:
                                comp.add(m)
                                todo.append(m)
                    seen |= comp
                    best = max(best, len(comp))
                self.assertGreaterEqual(best / len(adj), 0.97, f'largest component {best}/{len(adj)} nodes')


if __name__ == '__main__':
    unittest.main()
