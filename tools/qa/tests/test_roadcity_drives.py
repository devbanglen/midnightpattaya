"""Road B city batches: which runs of build/roadcity/<id>/drives.json are Studio drives (tools/roadvis/city_batch.py,
docs/ROAD_B_CITY_ROLLOUT.md). OFFLINE ONLY. Every failed off-road Studio drive of b001 - b004 drove into a building or a
colliding pole (docs/test_results/road_b_city_studio.txt): the drive list sweeps the car body (7.9 x 16, 2.2 to 8 studs
up) along every path against the buildings and the colliding Parts of the furniture and props; a run with anything in
the way keeps its row with studio = false and its obstacles. Checks:
  - synthetic paths: through a building, past a pole inside the footprint or just ahead of the path's end -> flagged,
    in the order the car meets them; a pole just outside the footprint and a clear path -> not; the footprint turns
    with the path
  - the minimum set takes only studio = true runs: at most 48 harness runs spread evenly, every clear lane-0 spot run
  - city_batch.PARTS against the builders' source: every listed Part is built with CanCollide true (and its size where
    the source gives numbers), and every colliding Part of the props / furniture / coast builders is listed
  - the real batches (needs build/ and build/roadcity/<id>/drives.json, skipped without): every failed off-road drive
    of b001, b003 and b004 is flagged with what the leader found on its path; of the drives Studio made, as many have
    something on the path as his cross-check found; a drives.json written by this code has no flagged or
    studio = false run in its minimum set
"""
import math
import os
import re
import sys
import unittest
from types import SimpleNamespace

import _qa

sys.path.insert(0, _qa.ROOT)
_C = {}


def modules():
    try:
        import shapely  # noqa: F401
        from tools.roadvis import city, city_batch
    except ImportError as e:  # pragma: no cover
        raise unittest.SkipTest(f'needs numpy / shapely (repo .venv): {e}')
    return city, city_batch


def packed(pts):
    """a TestKit packed path (world x, z) through map-local points"""
    city, _ = modules()
    return ';'.join(f'{x + city.ORIGIN[0]:.1f},{z:.1f}' for x, z in pts)


def line(a, b, step=2.0):
    """points every `step` studs from a to b (map-local)"""
    n = max(int(math.ceil(math.dist(a, b) / step)), 1)
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def pole(x, z, w=0.7, kind='LightPole'):
    _, cb = modules()
    return dict(kind=kind, x=x, z=z, foot=cb._foot(x, z, None, w, w))


def building(x0, z0, x1, z1, name='shophouse', osm=7):
    from shapely.geometry import box
    return dict(kind='Building', x=(x0 + x1) / 2, z=(z0 + z1) / 2, foot=box(x0, z0, x1, z1), name=name, osm=osm)


def obstacles(*items):
    from shapely.strtree import STRtree
    return list(items), STRtree([o['foot'] for o in items])


class Sweep(unittest.TestCase):
    """city_batch.path_obstacles: the 7.9 x 16 car body along a straight path from (0, 0) to (100, 0), map-local"""

    def setUp(self):
        self.city, self.cb = modules()
        self.path = packed(line((0, 0), (100, 0)))

    def hit(self, *items, path=None):
        return self.cb.path_obstacles(path or self.path, obstacles(*items))

    def test_path_through_a_building_is_flagged(self):
        o = self.hit(building(40, 2, 60, 30))                      # the body reaches 3.95 to the side: 1.95 into it
        self.assertEqual(o, [dict(kind='Building', world=[self.city.ORIGIN[0] + 50, 16.0], name='shophouse', osm=7)])

    def test_pole_inside_the_footprint_is_flagged(self):
        self.assertEqual([x['kind'] for x in self.hit(pole(50, 3.5))], ['LightPole'])         # 3.15 .. 3.85 < 3.95
        self.assertEqual([x['kind'] for x in self.hit(pole(50, -3.5, 0.9, 'UtilityPole'))], ['UtilityPole'])
        self.assertEqual(len(self.hit(pole(107, 0))), 1, 'the car front is 8 studs ahead of the last point')
        self.assertEqual(len(self.hit(pole(-7.5, 0))), 1, 'and its rear 8 behind the first')

    def test_clear_path_is_not_flagged(self):
        self.assertEqual(self.hit(pole(50, 4.5), pole(50, -4.5), pole(108.6, 0), building(40, 4.2, 60, 30)), [])
        self.assertEqual(self.hit(), [])

    def test_order_the_car_meets_them(self):
        a, b = pole(30, 0, kind='NameSignPost'), building(60, -2, 70, 20, name='hotel', osm=9)
        self.assertEqual([x['kind'] for x in self.hit(b, a)], ['NameSignPost', 'Building'])
        back = packed(line((100, 0), (0, 0)))
        self.assertEqual([x['kind'] for x in self.hit(a, b, path=back)], ['Building', 'NameSignPost'])
        self.assertEqual(self.hit(a, dict(a)), self.hit(a)[:1], 'one Part exported twice: listed once')

    def test_footprint_turns_with_the_path(self):
        north = packed(line((0, 0), (0, 100)))
        self.assertEqual(self.hit(pole(6, 50), path=north), [], '6 studs to the side: outside the 7.9-wide body')
        self.assertEqual(len(self.hit(pole(3.5, 50), path=north)), 1)
        diag = packed(line((0, 0), (70, 70)))
        side = (50 + 4.5 / math.sqrt(2), 50 - 4.5 / math.sqrt(2))        # 4.5 studs right of the diagonal
        self.assertEqual(self.hit(pole(*side, w=0.6), path=diag), [])
        self.assertEqual(len(self.hit(pole(50 + 2, 50 - 2, w=0.6), path=diag)), 1)

    def test_parts_turn_with_their_row(self):
        """PattayaBuilder / PattayaFurnitureBuilder frames: right = (-look z, look x), back = -look"""
        f = self.cb._foot(10, 20, (0, 1), 12, 0.3, 0, 2.2)              # a ShelterWall: 2.2 behind a stand facing +z
        self.assertAlmostEqual(f.centroid.x, 10)
        self.assertAlmostEqual(f.centroid.y, 17.8)
        b = f.bounds
        self.assertAlmostEqual(b[2] - b[0], 12)
        self.assertAlmostEqual(b[3] - b[1], 0.3)
        g = self.cb._foot(0, 0, (1, 0), 1.4, 1.4, 34.5, 0)              # a GantryPost span / 2 to the right of +x
        self.assertAlmostEqual(g.centroid.x, 0)
        self.assertAlmostEqual(g.centroid.y, 34.5)


class MinimumSet(unittest.TestCase):
    """city_batch.minimum_set: the short Studio set only from runs with studio = true"""

    def rows(self, n_harness, flag_every):
        rows = []
        for k in range(5):
            for lat in (0, 14):
                bad = k == 2
                rows.append(dict(set='spot', lateral=lat, studio=not bad, obstacles=[{'kind': 'LightPole'}] if bad else []))
        for k in range(n_harness):
            bad = flag_every and k % flag_every == 0
            rows.append(dict(set='offroad_harness', lateral=24, studio=not bad, obstacles=[{'kind': 'Building'}] if bad else []))
            rows.append(dict(set='offroad_deep', lateral='+edge8', studio=True, obstacles=[]))
        return rows

    def test_minimum_set_has_no_flagged_row(self):
        _, cb = modules()
        rows = cb.minimum_set(self.rows(160, 5))                         # 128 clear harness runs: every third
        mn = [r for r in rows if r['minimum']]
        self.assertTrue(mn)
        self.assertFalse([r for r in mn if r['obstacles'] or not r['studio']])
        spot = [r for r in mn if r['set'] == 'spot']
        self.assertEqual(len(spot), 4, 'every clear lane-0 spot run, the flagged one not')
        self.assertTrue(all(r['lateral'] == 0 for r in spot))
        clear = [r for r in rows if r['set'] == 'offroad_harness' and r['studio']]
        self.assertEqual(len(clear), 128)
        self.assertEqual([r['minimum'] for r in clear], [k % 3 == 0 for k in range(128)], 'spread evenly')
        self.assertLessEqual(sum(r['minimum'] for r in clear), 48)
        self.assertFalse([r for r in rows if r['set'] == 'offroad_deep' and r['minimum']])

    def test_all_clear_harness_runs_when_48_or_fewer(self):
        _, cb = modules()
        rows = cb.minimum_set(self.rows(50, 10))                         # 45 clear
        h = [r for r in rows if r['set'] == 'offroad_harness']
        self.assertEqual([r['minimum'] for r in h], [r['studio'] for r in h])
        self.assertEqual(sum(r['minimum'] for r in h), 45)


BUILDERS = ('PattayaBuilder.luau', 'PattayaFurnitureBuilder.luau', 'PattayaCoastBuilder.luau')
# colliding Parts of those builders that are not in city_batch.PARTS: read on their own (PalmTrunk leans, the gantry
# posts and gate pillars stand span / 2 apart), above the car body (the gate beam at y 31 .. 34) or road surfaces
OWN, HIGH, SURFACE = ('PalmTrunk', 'GantryPost', 'Pillar'), ('Beam',), ('Joint', 'Junction')


def builder_parts():
    """every newPart / cyl call with a literal name in the builders: {name: [(size or None, collide)]}"""
    out = {}
    for f in BUILDERS:
        for m in re.finditer(r'\b(newPart|cyl)\(\s*\w+,\s*"(\w+)",\s*(.*), (true|false)\)\s*$',
                             _qa.src(os.path.join('ServerStorage', f)), re.M):
            kind, name, args, collide = m.groups()
            size = None
            if kind == 'cyl':                                            # cyl(parent, name, length, dia, cf, color, collide)
                v = args.split(',')[:2]
                if all(re.fullmatch(r'\s*[\d.]+\s*', x) for x in v):
                    size = (float(v[1]), float(v[0]), float(v[1]))
            else:
                s = re.match(r'Vector3\.new\(([\d.]+), ([\d.]+), ([\d.]+)\)', args)
                size = tuple(float(x) for x in s.groups()) if s else None
            out.setdefault(name, []).append((size, collide == 'true'))
    return out


class BuilderSync(unittest.TestCase):
    def test_parts_match_the_builders(self):
        _, cb = modules()
        built = builder_parts()
        listed = {}
        for stride, frame, parts in cb.PARTS.values():
            for name, w, d, ox, oz, y0, y1 in parts:
                listed.setdefault(name, set()).add((w, round(y1 - y0, 3), d))
        for name, sizes in listed.items():
            self.assertIn(name, built, f'{name} is not built by {BUILDERS}')
            self.assertTrue(all(c for _, c in built[name]), f'{name} is built with CanCollide false: not an obstacle')
            known = {tuple(round(v, 3) for v in s) for s, _ in built[name] if s}
            if known:
                self.assertTrue(sizes <= known, f'{name}: PARTS {sizes} != builder {known}')
        colliding = {n for n, calls in built.items() if any(c for _, c in calls)}
        self.assertEqual(colliding - set(listed) - set(OWN + HIGH + SURFACE), set(),
                         'a builder makes a colliding Part the drive check does not know: add it to city_batch.PARTS')
        self.assertTrue(set(OWN) <= colliding)


# the failed Studio drives (docs/test_results/road_b_city_studio.txt): run id -> (set, lateral, what the leader found
# on the path: its kinds, and world x, z where he gave them)
B003 = ('Building', 'UtilityPole'), ()                        # "a building (shophouse or hotel) or a Poles.UtilityPole"
B004 = ('Building', 'NameSignPost'), ((24950, -350), (25030, -340), (24923, -345), (24923, -335))
FAILED = {
    'b001': {114: ('offroad_harness', -24, ('LightPole',), ((24655.9, 249.5),)),
             126: ('offroad_harness', -24, ('LightPole',), ((24773.0, 204.5),)),
             127: ('offroad_harness', -24, ('Building',), ())},                  # the shophouse wall at x 24762
    'b003': {106: ('offroad_harness', 24, *B003), 110: ('offroad_harness', -24, *B003), 114: ('offroad_harness', 20, *B003),
             146: ('offroad_harness', 24, *B003), 158: ('offroad_harness', -20, *B003), 172: ('offroad_harness', 24, *B003),
             176: ('offroad_harness', 24, *B003), 218: ('offroad_harness', 20, *B003), 248: ('offroad_harness', 24, *B003),
             256: ('offroad_harness', -24, *B003), 260: ('offroad_harness', 20, *B003), 264: ('offroad_harness', 20, *B003),
             310: ('offroad_harness', 24, *B003)},
    'b004': {52: ('offroad_harness', -24, *B004), 53: ('offroad_harness', -24, *B004), 56: ('offroad_harness', -20, *B004),
             57: ('offroad_harness', -20, *B004), 63: ('offroad_harness', 24, *B004), 67: ('offroad_harness', 20, *B004),
             86: ('offroad_harness', 24, ('Building',), ((24939, -212),)),
             96: ('offroad_harness', -20, ('UtilityPole',), ((25012, -255),)),
             111: ('offroad_harness', 20, ('UtilityPole',), ((25012, -255),)),
             112: ('offroad_harness', 20, ('UtilityPole',), ((24930, -282),))},
}
# the leader's cross-check (the car footprint swept along every driven path in Studio): drives with an obstacle on the
# path (b001 3 PASS + 3 FAIL, b002 1 PASS, b003 8 PASS + 13 FAIL, b004 9 PASS + 10 FAIL) of all drives
CROSS_CHECK = {'b001': (6, 66), 'b002': (1, 58), 'b003': (21, 70), 'b004': (19, 62)}


class StudioFailures(unittest.TestCase):
    """the real batches: every failed off-road drive of b001 - b004 is flagged, with what the leader found on its path"""

    @classmethod
    def setUpClass(cls):
        _, cb = modules()
        _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
        import warnings
        from shapely.geometry import box
        from tools.roadvis import world
        warnings.filterwarnings('ignore', category=RuntimeWarning)
        if 'obs' not in _C:
            bb = (24000.0, -800.0, 25600.0, 2100.0)                     # b001 - b004 and 200 studs around (world)
            W = world.load(_qa.BUILD, bbox=world.world_bbox_local(bb), margin=50.0, with_furniture=False)
            CW = SimpleNamespace(broot=W['broot'], buildings=lambda g: [b for b in W['blds'] if b['poly'].intersects(g)])
            _C['obs'] = cb.drive_obstacles(CW, box(*world.world_bbox_local(bb)))
        cls.cb, cls.obs = cb, _C['obs']

    def runs(self, bid):
        d = _qa.load_json(_qa.need_build('roadcity', bid, 'drives.json'))
        return {r['id']: r for r in d['runs']}

    def test_failed_drives_flagged(self):
        for bid, want in FAILED.items():
            runs = self.runs(bid)
            for i, (set_, lat, kinds, at) in want.items():
                r = runs[i]
                self.assertEqual((r['set'], r['lateral']), (set_, lat), f'{bid} run {i} is not the run Studio drove')
                o = self.cb.path_obstacles(r['packed'], self.obs)
                self.assertTrue(any(x['kind'] in kinds and (not at or any(math.dist(x['world'], p) < 2.0 for p in at))
                                    for x in o), f'{bid} run {i}: {o}')

    def test_cross_check_counts(self):
        """the drives Studio made (the minimum set as chosen then: the lane-0 spot runs clear of buildings at 70 and 100,
        every k-th harness run at 35): as many have something on the path as the leader's cross-check found"""
        for bid, (want, drives) in CROSS_CHECK.items():
            runs = list(self.runs(bid).values())
            spot = [r for r in runs if r['set'] == 'spot' and r['lateral'] == 0 and not r['blocked']]
            harness = [r for r in runs if r['set'] == 'offroad_harness']
            harness = harness[::max(1, -(-len(harness) // 48))]
            self.assertEqual(2 * len(spot) + len(harness), drives, f'{bid}: not the drive list Studio drove')
            hit = 2 * sum(1 for r in spot if self.cb.path_obstacles(r['packed'], self.obs))
            hit += sum(1 for r in harness if self.cb.path_obstacles(r['packed'], self.obs))
            self.assertEqual(hit, want, bid)

    def test_written_drives_skip_flagged_runs(self):
        """a drives.json written by this code: studio = false exactly where a wheel is in a building (spot runs) or
        something is in the way; no such run in the minimum set; at most 48 harness runs in it"""
        seen = 0
        for bid in ('b001', 'b002', 'b003', 'b004'):
            p = os.path.join(_qa.BUILD, 'roadcity', bid, 'drives.json')
            if not os.path.exists(p):
                continue
            runs = _qa.load_json(p)['runs']
            if 'obstacles' not in runs[0]:
                continue                                                 # written before the obstacle check
            seen += 1
            for r in runs:
                self.assertEqual(r['studio'], r.get('blocked', 0) == 0 and not r['obstacles'], f"{bid} run {r['id']}")
                if r['minimum']:
                    self.assertTrue(r['studio'], f"{bid} run {r['id']}")
            self.assertLessEqual(sum(1 for r in runs if r['minimum'] and r['set'] == 'offroad_harness'), 48)
        if not seen:
            raise unittest.SkipTest('no drives.json with obstacles (tools/roadvis/city_cli.py batch <id>)')


if __name__ == '__main__':
    unittest.main()
