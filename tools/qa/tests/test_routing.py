"""Routing (ServerStorage.PattayaRoute): how routes join the road graph, run on the REAL module in the luau CLI with the
real graph, job stands and building footprints (tools/qa/routing_harness/route_harness.py), next to the pre-fix copy
of the module (tools/qa/routing_harness/PattayaRoute_old.luau) for before/after numbers. Docs: docs/ROUTING.md.

Owner rule: a route never takes a straight line through buildings as a shortcut onto the road graph."""
import os
import re
import subprocess
import sys
import unittest

import _qa

sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'qa', 'routing_harness'))
import route_harness as H  # noqa: E402

CONNECTOR_MAX = 39 / 2 + 8 + 15  # widest road (78) / 2 + SNAP_MARGIN, + slack for a stand on the kerb lane
OFFROAD_MAX = 6  # studs of a route (interior) outside every road slab
ON_CENTRELINE = 0.6  # interior route points/segments lie on an edge polyline
LEADER_STANDS = ('central_festival', 'terminal21')  # the two jobs the leader tested in Play


def setUpModule():
    H.graph()
    H.stands()


class Harness(unittest.TestCase):
    def test_runs_clean(self):
        res = H.run()
        self.assertEqual(res['code'], 0, res['raw'][-2000:])
        self.assertTrue(res['DONE'], res['raw'][-2000:])
        self.assertEqual(res['JOBERR'], [])
        self.assertEqual(res['GPSERR'], {'old': {}, 'new': {}})
        self.assertEqual(res['SPRERR'], {'old': {}, 'new': {}})
        self.assertIn('WARN_COUNT\t0', res['raw'])

    def test_harness_luau_compiles(self):
        exe = _qa.find_luau('luau-compile')
        if not exe:
            self.skipTest('luau-compile not found')
        for f in ('env.luau', 'tail.luau', 'PattayaRoute_old.luau'):
            p = os.path.join(_qa.ROOT, 'tools', 'qa', 'routing_harness', f)
            r = subprocess.run([exe, '--null', p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + ': ' + (r.stderr or r.stdout))

    def test_old_module_reproduces_the_central_festival_bug(self):
        """the pre-fix module gives the leader's route: stand -> a junction ~149 studs away through buildings"""
        res = H.run()
        routes = [r for (f, _t), r in res['JOB']['old'].items() if f == 'central_festival']
        self.assertTrue(routes)
        m = H.job_metrics(routes[0])
        self.assertGreater(m['first'], 100)
        self.assertTrue(H.geo().buildings_crossed(routes[0]['pts'][0], routes[0]['pts'][1]))
        # the leader saw the line cross terrain to world (21338, 308): that point is on the old connector
        a, b = routes[0]['pts'][0], routes[0]['pts'][1]
        self.assertLess(_qa.point_seg_dist((1338, 308), a, b), 3)

    def test_luau_building_check_agrees_with_python(self):
        """Route.crossesBuilding (Luau, chunk modules) == the Python footprint check, on the old stand connectors"""
        res = H.run()
        G, g = H.geo(), H.graph()
        self.assertTrue(res['XB'])
        for s in H.stands():
            x = res['XB'][s['id']]
            p = (s['x'], s['z'])
            # the old connector end = nearest junction; recompute it in Python
            n = min(g['nodes'], key=lambda q: _qa.dist2(q, p))
            self.assertAlmostEqual(_qa.dist2(n, p), x['length'], delta=0.05)
            self.assertEqual(x['crosses'], bool(G.buildings_crossed(p, n)), s['id'])
        self.assertTrue(res['XB']['central_festival']['crosses'])


class Jobs(unittest.TestCase):
    """PattayaJobsServer's flow (nearestNode -> dijkstra -> polylineOf + stand positions), every stand to every
    destination it can be given"""

    @classmethod
    def setUpClass(cls):
        cls.res = H.run()
        cls.new = {k: H.job_metrics(r) for k, r in cls.res['JOB']['new'].items()}

    def test_every_stand_has_an_anchor_on_its_road(self):
        G = H.geo()
        for s in H.stands():
            a = self.res['ANCHOR'][s['id']]
            self.assertLessEqual(a['d'], CONNECTOR_MAX, s['id'])
            self.assertEqual(G.buildings_crossed((s['x'], s['z']), a['q']), [], s['id'])
            self.assertLess(G.centreline_dist(a['q']), ON_CENTRELINE, s['id'])

    def test_leader_stands_still_get_jobs(self):
        for sid in LEADER_STANDS:
            self.assertGreater(self.res['JOBN']['new'].get(sid, 0), 0, sid)

    def test_connectors_short(self):
        self.assertTrue(self.new)
        bad = [(k, round(m['first'], 1), round(m['last'], 1)) for k, m in self.new.items()
               if m['first'] > CONNECTOR_MAX or m['last'] > CONNECTOR_MAX]
        self.assertEqual(bad, [])

    def test_no_building_crossed(self):
        bad = [(k, m['crossed']) for k, m in self.new.items() if m['crossed']]
        self.assertEqual(bad, [])

    def test_no_offroad_stretch(self):
        bad = [(k, round(m['offroad'], 1)) for k, m in self.new.items() if m['offroad'] > OFFROAD_MAX]
        self.assertEqual(bad, [])

    def test_continuity_on_the_graph(self):
        """between the two stand connectors every point and every segment midpoint is on an edge polyline"""
        G = H.geo()
        for k, r in self.res['JOB']['new'].items():
            pts = r['pts'][1:-1]
            self.assertGreaterEqual(len(pts), 2, k)
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                self.assertLess(G.centreline_dist(a), ON_CENTRELINE, (k, i, a))
                self.assertLess(G.centreline_dist(mid), ON_CENTRELINE, (k, i, mid))
            self.assertAlmostEqual(_qa.polyline_length(r['pts']), r['length'], delta=0.1)

    def test_central_festival_fixed(self):
        routes = {k: m for k, m in self.new.items() if k[0] == 'central_festival' or k[1] == 'central_festival'}
        self.assertTrue(routes)
        for k, m in routes.items():
            end = m['first'] if k[0] == 'central_festival' else m['last']
            self.assertLess(end, 5, k)  # the stand is on edge #4 (13-stud soi), 0.5 studs from its centreline


class GPS(unittest.TestCase):
    """Route.routeTo with GPS_SNAP from the garage, the Bira paddock, every stand and 40 cars on random roads"""

    @classmethod
    def setUpClass(cls):
        cls.res = H.run()

    def test_all_scenarios_route(self):
        self.assertEqual(set(self.res['GPS']['new']), {g['name'] for g in H.gps_scenarios()})

    def test_unchanged_where_the_old_route_was_clean(self):
        """routeTo already projected onto edges; the fix must not move any of these GPS routes"""
        old, new = self.res['GPS']['old'], self.res['GPS']['new']
        moved = []
        for name, r in new.items():
            o = old[name]
            if H.gps_metrics(o)['crossed']:
                continue  # allowed to change: the old start crossed a building
            if len(o['pts']) != len(r['pts']) or any(_qa.dist2(a, b) > 0.01 for a, b in zip(o['pts'], r['pts'])):
                moved.append(name)
        self.assertEqual(moved, [])

    def test_on_road_starts_join_their_road(self):
        bad = []
        for name, r in self.res['GPS']['new'].items():
            m = H.gps_metrics(r)
            if m['start_slack'] <= H.SNAP_MARGIN and m['first'] > CONNECTOR_MAX:
                bad.append((name, round(m['first'], 1)))
            if m['crossed']:
                bad.append((name, 'buildings', m['crossed']))
            if m['offroad'] > OFFROAD_MAX:
                bad.append((name, 'offroad', round(m['offroad'], 1)))
        self.assertEqual(bad, [])

    def test_bira_paddock(self):
        """the paddock is off the graph (docs/CIRCUIT_ACCESS_ROUTES.md: 233 studs): a straight leg over the apron, no
        building of the exported map on it"""
        r = self.res['GPS']['new']['bira_paddock>central']
        m = H.gps_metrics(r)
        self.assertTrue(225 <= m['first'] <= 240, m['first'])
        self.assertEqual(m['crossed'], [])
        self.assertGreater(r['length'], 20000)

    def test_garage_to_central_and_bira(self):
        for name in ('garage_spawn>bira', 'garage_spawn>central', 'garage_left20>bira', 'garage_right20>central'):
            m = H.gps_metrics(self.res['GPS']['new'][name])
            self.assertLessEqual(m['first'], CONNECTOR_MAX, name)
            self.assertEqual(m['crossed'], [], name)


class Snap(unittest.TestCase):
    """off-road points whose nearest edge projection crosses a building (route_harness.snap_scenarios)"""

    def test_snap_avoids_buildings_when_it_can(self):
        res = H.run()
        G = H.geo()
        self.assertEqual(len(res['SNAP']), len(H.snap_scenarios()))
        fixed = kept = 0
        for name, s in res['SNAP'].items():
            self.assertTrue(G.buildings_crossed(s['p'], s['old']), name)  # by construction
            if G.buildings_crossed(s['p'], s['new']):
                # fallback: the same nearest edge as before (the point is boxed in by buildings)
                self.assertLess(_qa.dist2(s['new'], s['old']), 0.01, name)
                kept += 1
            else:
                self.assertLessEqual(s['dNew'], 700, name)
                fixed += 1
        self.assertGreater(fixed, len(res['SNAP']) // 3, f'{fixed} fixed, {kept} boxed in')

    def test_snap_is_nearest_edge_on_roads(self):
        """for a point on a road (every job stand) Route.snap picks the nearest edge centreline"""
        res = H.run()
        G = H.geo()
        for s in H.stands():
            a = res['ANCHOR'][s['id']]
            self.assertAlmostEqual(a['d'], G.centreline_dist((s['x'], s['z'])), delta=0.05, msg=s['id'])


class SprintAndRaces(unittest.TestCase):
    def test_point_to_point_identical(self):
        """sprints / street races / events (Route.pointToPoint): same courses as before, also after the job anchors
        exist (the harness runs them after the jobs)"""
        res = H.run()
        old, new = res['SPR']['old'], res['SPR']['new']
        self.assertEqual(len(old), len(H.sprint_scenarios()))
        self.assertEqual(sorted(old), sorted(new))
        diff = [i for i in old if old[i]['blob'] != new[i]['blob']]
        self.assertEqual(diff, [])


class ModuleContract(unittest.TestCase):
    def test_api_kept(self):
        old = set(re.findall(r'^function Route\.(\w+)', _qa.read(os.path.join(H.HERE, 'PattayaRoute_old.luau')), re.M))
        new = set(re.findall(r'^function Route\.(\w+)', _qa.src('ServerStorage/PattayaRoute.luau'), re.M))
        self.assertEqual(old - new, set())
        for f in ('Route.nodes', 'Route.baseNodes', 'Route.osmIndex', 'Route.ORIGIN'):
            self.assertIn(f + ' =', _qa.src('ServerStorage/PattayaRoute.luau'))

    def test_graph_has_no_oneway_flag(self):
        """PattayaRoute treats every graph edge as two-way (graph.luau rows are {a, b, len, tier, width, pts}). The
        anchor pieces and routeTo follow the adjacency, so dropping a b -> a link would make an edge one-way; if the
        export ever adds a one-way field, PattayaRoute must read it (docs/ROUTING.md)"""
        g = H.graph()
        d = g['dir']
        rows = re.findall(r'^\s*\{ (\d+, \d+, [\d.]+, \d+, [\d.]+), \{', _qa.read(os.path.join(d, 'graph.luau')), re.M)
        self.assertGreater(len(rows), 100)
        self.assertEqual(len(rows) + sum(len(re.findall(r'^\s*\{ \d+, \d+, ', _qa.read(os.path.join(d, p + '.luau')),
                                                       re.M)) for p in g['parts']), len(g['edges']))

    def test_before_after_summary(self):
        res = H.run()
        rows = []
        for v in ('old', 'new'):
            ms = [H.job_metrics(r) for r in res['JOB'][v].values()]
            rows.append((v, len(ms), max(m['first'] for m in ms), max(m['last'] for m in ms),
                         sum(1 for m in ms if m['crossed']), max(m['offroad'] for m in ms)))
        if '-v' in sys.argv:
            for r in rows:
                print('  jobs %s: %d routes, max first %.1f, max last %.1f, crossing buildings %d, max off-road %.0f'
                      % r)
        (_, _, f0, l0, x0, _), (_, _, f1, l1, x1, o1) = rows
        self.assertGreater(x0, 0)
        self.assertEqual(x1, 0)
        self.assertLess(f1, f0)
        self.assertLess(l1, l0)


if __name__ == '__main__':
    unittest.main()
