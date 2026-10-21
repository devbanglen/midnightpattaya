"""Road visual analysis + offline junction pilot (tools/roadvis, docs/ROAD_VISUAL_SPEC.md). OFFLINE ONLY.

Needs the generated build/ (pattaya_wide, aprons, shoulders, furniture); skipped when it is missing. Checks:
  - the loader reproduces the built layers of the Sukhumvit / Pattaya Klang area (slabs, discs, fills, shoulders)
  - the root-cause metrics are what the report says (disc overhang, overlaps, crossings off the legs, lane lines)
  - design B (separate collision / visual): no wheel drop on any lane of any carriageway (outside the seam band),
    collision covers the visible asphalt, no overlap with buildings, no meaningless asphalt, markings on the asphalt
    and continuous (>= 95 % of the lane boundaries), every crossing on a junction leg (perpendicular, kerb to kerb,
    both ends on a sidewalk / island), the shoulder pilot's anti-flip support kept (drops after <= before at every
    lateral offset), the graph untouched, deterministic output
  - design A (existing parts, fixed rules) is generated too (for the comparison), with no building overlap
"""
import json
import math
import os
import sys
import unittest

import _qa

sys.path.insert(0, _qa.ROOT)
_C = {}


def state():
    if 'W' in _C:
        return _C['W'], _C['P']
    _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
    _qa.need_build('shoulders', 'roblox', 'manifest.luau')
    _qa.need_build('aprons', 'roblox', 'manifest.luau')
    try:
        import shapely  # noqa: F401
        from tools.roadvis import junction, world
    except ImportError as e:  # pragma: no cover
        raise unittest.SkipTest(f'needs numpy / shapely (repo .venv): {e}')
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    bl = world.world_bbox_local(junction.CFG['bbox_world'])
    W = world.load(_qa.BUILD, bbox=bl)
    P = {d: junction.generate(W, dict(design=d)) for d in ('A', 'B')}
    _C['W'], _C['P'] = W, P
    return W, P


class TestLoaderAndRootCause(unittest.TestCase):
    def test_area_layers(self):
        from shapely.geometry import box
        from tools.roadvis import world
        W, _ = state()
        B = box(4220, 650, 4820, 1250)
        kinds = {}
        for s in W['surf']:
            if s['poly'].intersects(B):
                kinds[s['kind']] = kinds.get(s['kind'], 0) + 1
        for k in ('road', 'fill', 'junction', 'joint', 'apron', 'shoulder', 'taper', 'gap'):
            self.assertGreater(kinds.get(k, 0), 0, k)
        ids = {e['id'] for e in W['edges']}
        self.assertIn('709043850:w1140', ids)        # the Sukhumvit edge under the owner's look ray (24494.9, 962.3)
        self.assertEqual(world.ORIGIN, (20000.0, 0.0))

    def test_root_cause_numbers(self):
        from shapely.geometry import box
        from tools.roadvis import analyze
        W, _ = state()
        m = analyze.measure(W, box(4220, 650, 4820, 1250))
        self.assertGreater(m['disc_overhang_area'], 0.25 * m['disc_area'])     # discs stick out past the slabs
        self.assertGreater(m['overlap_ge2'], 0.15 * m['asphalt'])              # stacked road surfaces
        self.assertGreater(m['carriageway_overlap'], 0.1 * m['asphalt'])       # carriageways pressed into each other
        self.assertGreater(m['crossings']['no_landing_either_end'], m['crossings']['n'] // 2)
        self.assertLess(m['lane_lines']['coverage_visible'], 0.5)
        self.assertAlmostEqual(m['proportions']['road_widening_vs_city'], 2.08, places=2)


class TestPilotB(unittest.TestCase):
    def setUp(self):
        self.W, Ps = state()
        self.P = Ps['B']
        self.c = self.P['checks']

    def test_no_wheel_drop_on_lanes(self):
        self.assertGreater(self.c['wheel_after']['samples'], 2000)
        self.assertEqual(self.c['wheel_after']['unsupported'], 0, self.c['wheel_after_bad'][:5])
        self.assertLess(self.c['wheel_after_incl_seam']['unsupported'], self.c['wheel_before_incl_seam']['unsupported'])

    def test_collision_covers_visual(self):
        self.assertLess(self.c['visual_without_collision'], 1.0)
        self.assertLess(self.c['collision_outside_visual'], 50.0)

    def test_no_buildings_no_meaningless_asphalt(self):
        self.assertEqual(self.c['building_overlap'], 0.0)
        self.assertEqual(self.c['meaningless_asphalt'], 0.0)
        self.assertLess(self.c['layer_overlap'], 0.5)

    def test_markings(self):
        self.assertGreaterEqual(self.c['lane_boundary_coverage'], 0.95)
        self.assertLess(self.c['marking_off_asphalt'], 1.0)
        kinds = {m['kind'] for m in self.P['marks']}
        self.assertTrue({'lane', 'centre', 'edge', 'stop', 'zebra'} <= kinds, kinds)

    def test_crossings_on_legs(self):
        xs = self.c['crossings']
        self.assertGreaterEqual(len(xs), 3)
        for x in xs:
            self.assertTrue(all(x['lands']), x)
            self.assertLess(x['perp_err_deg'], 1.0, x)
            self.assertGreaterEqual(x['bars'], 3, x)

    def test_shoulder_support_kept(self):
        from shapely.geometry import box
        from tools.roadvis import shoulders_view
        area = box(4220, 650, 4820, 1250)
        before = shoulders_view.offset_drive(self.W, area)
        after = shoulders_view.offset_drive(self.W, area, self.P)
        for o in shoulders_view.OFFSETS:
            self.assertLessEqual(after[str(o)]['drop'], before[str(o)]['drop'], o)
            self.assertEqual(after[str(o)]['in_lane_drop'], 0, o)

    def test_shoulder_pilot_not_replaced(self):
        self.assertFalse(any(s['kind'] in ('shoulder', 'taper', 'gap') for s in self.P['replaced']))

    def test_graph_untouched(self):
        import hashlib
        p = os.path.join(_qa.BUILD, 'pattaya_wide', 'graph_game.json')
        h1 = hashlib.sha1(open(p, 'rb').read()).hexdigest()
        from tools.roadvis import junction
        junction.generate(self.W, dict(design='B'))
        self.assertEqual(h1, hashlib.sha1(open(p, 'rb').read()).hexdigest())

    def test_deterministic(self):
        import tempfile
        from tools.roadvis import junction
        P2 = junction.generate(self.W, dict(design='B'))
        with tempfile.TemporaryDirectory() as d:
            a = junction.export(self.W, self.P, os.path.join(d, 'a.json'))
            b = junction.export(self.W, P2, os.path.join(d, 'b.json'))
        self.assertEqual(a['sha1'], b['sha1'])

    def test_fewer_asphalt_parts(self):
        from tools.roadvis import junction
        pc = junction.part_counts(self.W, self.P)
        old_asphalt = sum(pc['before_replaced'].get(k, 0) for k in ('road', 'fill', 'junction', 'joint', 'apron'))
        self.assertLess(pc['after']['collision_wedges'], old_asphalt)


class TestPilotA(unittest.TestCase):
    def test_design_a_generated(self):
        W, Ps = state()
        c = Ps['A']['checks']
        self.assertEqual(c['building_overlap'], 0.0)
        self.assertLessEqual(c['wheel_after']['unsupported'], c['wheel_before']['unsupported'])
        self.assertGreaterEqual(c['lane_boundary_coverage'], 0.9)


if __name__ == '__main__':
    unittest.main()
