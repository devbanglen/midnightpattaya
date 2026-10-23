"""Road B for the whole city, batch by batch (tools/roadvis/city*.py, PattayaRoadVisBuilder / PattayaRoadGroundBuilder
city mode, docs/ROAD_B_CITY_ROLLOUT.md). OFFLINE ONLY. Needs the generated build/ (skipped without it) and, for the
batch tests, build/roadcity (tools/roadvis/city_cli.py plan / batch b001). Checks:
  - the pilot's Studio data is unchanged (the generalised generator leaves junction.generate / export_luau alone)
  - the plan: disjoint batch boxes on the 600-stud grid, b001 = the owner's box, every content cell in one batch
  - ownership: every old road-layer part over b001's box goes, nothing of ShoulderChunks, outside portions rebuilt
  - two city batches that share an edge meet with no hole: lane wheels across the shared edge all on road parts
  - batch 1 targets with the ground (static model): 0 lane holes, 0 drops, road-to-ground steps <= 0.6, the runs
  - the Studio data on disk equals a fresh export (determinism)
  - PattayaRoadVisBuilder city mode in the luau CLI: order check, Plan matches, Build counts, MoveReplaced moves the
    exact list (old parts by their real footprint boxes, pilot parts, frontier pieces), shoulders and decoys stay,
    Remove is last-in first-out and restores parents and CFrames exactly, Leftovers none
  - PattayaRoadGroundBuilder city mode with a voxel Terrain mock: the hand-made pilot raise adopted, b001 raised to
    the higher of both (no ramp between), never-raise and wrong terrain abort with nothing written, LIFO, exact restores
"""
import json
import math
import os
import re
import sys
import unittest

import _qa

sys.path.insert(0, _qa.ROOT)
_C = {}
FROZEN_B001 = ('021dd07cc78287368c19ee828d4f2b7e3cc2f9d1', 'ab0c4b2209e0d4d4bd25c71d79d0bfc6acd153fe')          # batch 1 as shipped: (rv sha1, ground sha1)


def city_world():
    if 'CW' in _C:
        return _C['CW'], _C['plan']
    _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
    _qa.need_build('roadvis', 'roblox', 'manifest.luau')
    try:
        import shapely  # noqa: F401
        from tools.roadvis import city
    except ImportError as e:  # pragma: no cover
        raise unittest.SkipTest(f'needs numpy / shapely (repo .venv): {e}')
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    CW = city.CityWorld(_qa.BUILD, log=lambda *a: None)
    plan = city.plan_city(CW, log=lambda *a: None)
    _C.update(CW=CW, plan=plan)
    return CW, plan


def cli_runs(upto, cfg=None, key=None):
    """city_cli.run_batches up to `upto` (the ground plans and option B as the CLI makes them): (st, results)"""
    k = ('cli', upto, key)
    if k in _C:
        return _C[k]
    from tools.roadvis import city, city_cli, city_ground
    CW, plan = city_world()
    if 'nr' not in _C:
        _C['nr'] = city_ground.NoRaise(_qa.BUILD, log=lambda *a: None)
    st, rows, results, gplans = city_cli.run_batches(CW, plan, _C['nr'], upto=upto, log=lambda *a: None,
                                                     cfg=cfg or city.VARIANTS[city.DEFAULT_VARIANT])
    _C[k] = (st, results)
    return st, results


def first_batches(n):
    """the state after the first n batches of the plan (and their results)"""
    key = f'run{n}'
    if key in _C:
        return _C[key]
    from tools.roadvis import city
    CW, plan = city_world()
    st = city.new_state(CW)
    cfg = city.VARIANTS[city.DEFAULT_VARIANT]          # the design that ships (lean)
    res = [city.make_batch(CW, plan, st, plan['batches'][i], cfg=cfg) for i in range(n)]
    _C[key] = (st, res)
    return st, res


class PilotUnchanged(unittest.TestCase):
    def test_pilot_export_equals_disk(self):
        """the pilot's 8 modules in the place: a fresh export of junction.generate design B equals build/roadvis/roblox"""
        import tempfile
        d = _qa.need_build('roadvis', 'roblox')
        from tools.roadvis import export_luau, junction, world
        cfg = dict(junction.CFG, design='B', name=junction.CFG['name'] + '_B')
        W = world.load(_qa.BUILD, bbox=world.world_bbox_local(cfg['bbox_world']), margin=900.0)
        P = junction.generate(W, cfg, log=lambda *a: None)
        with tempfile.TemporaryDirectory() as t:
            x = export_luau.export(W, P, t)
            for f in x['files']:
                self.assertEqual(_qa.read(os.path.join(t, f)), _qa.read(os.path.join(d, f)), f)
        self.assertEqual(x['replace'], 782)


class Plan(unittest.TestCase):
    def test_boxes(self):
        from shapely.geometry import box
        from tools.roadvis import city
        CW, plan = city_world()
        B = plan['batches']
        self.assertEqual(B[0]['id'], 'b001')
        self.assertEqual(tuple(B[0]['box']), (24220.0, 50.0, 24820.0, 650.0))
        seen = {(0, 0)}
        for b in B:
            x0, z0, x1, z1 = b['box']
            self.assertEqual(((x0 - 24220) % 600, (z0 - 650) % 600, (x1 - x0) % 600, (z1 - z0) % 600), (0, 0, 0, 0), b['id'])
            for c in b['cells']:
                self.assertNotIn(tuple(c), seen, b['id'])
                seen.add(tuple(c))
                self.assertTrue(box(*city.cell_box_world(*c)).within(box(*b['box']).buffer(0.01)))
        self.assertEqual(len({b['id'] for b in B}), len(B))
        groups = [b['group'] for b in B]
        self.assertEqual(groups[0], 'Sukhumvit Road')
        # main roads first, then the rest, then the corridor
        order = ['Sukhumvit Road', 'Beach Road', 'Second Road', 'Pattaya Klang / Central Road', 'North Pattaya Road',
                 'South Pattaya Road', 'Thepprasit Road', 'Jomtien Beach Road', 'rest', 'corridor']
        idx = [order.index(g) for g in groups]
        self.assertEqual(idx, sorted(idx))

    def test_build_order(self):
        """b003 (z -550..50, the owner's second screenshot spot at b001's north edge) builds second, then b002; every
        id keeps its first number, the rest of the order is unchanged"""
        CW, plan = city_world()
        B = plan['batches']
        self.assertEqual([b['id'] for b in B[:3]], ['b001', 'b003', 'b002'])
        self.assertEqual(tuple(B[1]['box']), (24220.0, -550.0, 24820.0, 50.0))
        nums = [int(b['id'][1:]) for b in B]
        self.assertEqual(nums, [1, 3, 2] + list(range(4, len(B) + 1)))


class Ownership(unittest.TestCase):
    def test_b001_takes_every_old_part_over_its_box(self):
        from shapely.geometry import box
        from tools.roadvis import city
        CW, plan = city_world()
        st, res = first_batches(1)
        r = res[0]
        BX = box(*city.wloc(r['box']))
        rep = {o['i'] for o in r['rep_old']}
        for j in CW.old_tree.query(BX):
            o = CW.old[int(j)]
            if o['i'] in CW.pilot_replaced:
                continue
            inside = city.in_box(o['c'][0], o['c'][1], city.wloc(r['box']))
            ov = o['key'].intersection(BX).area
            if inside or ov >= city.OVERLAP_MIN + city.UNCERTAIN:
                self.assertIn(o['i'], rep, (city.CODE_LABEL[o['code']], o['c']))
            if not inside and ov < city.OVERLAP_MIN - city.UNCERTAIN:
                self.assertNotIn(o['i'], rep)
        self.assertGreater(len(rep), 400)
        self.assertEqual(len(r['unc_old']), 0, 'no part of b001 sits on the overlap threshold')

    def test_outside_portions_rebuilt(self):
        """every stud of a replaced old road part outside the box is covered again: by frontier pieces (old roads go on),
        or, inside the pilot box, by the pilot's own parts / the band completion / an invisible support"""
        from shapely.geometry import box
        from shapely.ops import unary_union
        from tools.roadvis import city
        CW, plan = city_world()
        st, res = first_batches(1)
        r = res[0]
        BX = box(*city.wloc(r['box']))
        out = unary_union([o['shape'] for o in r['rep_old'] if o['cls'] == 'road']).difference(BX)
        pl = box(*city.wloc(city.PILOT_BOX_WORLD))
        front = unary_union([t['tri'] for t in r['front'] if t['kind'] == 1])
        miss = out.difference(pl).difference(front.buffer(0.02))
        self.assertLess(miss.area, 0.5)
        pilot_asph = unary_union([p['shape'] for p in CW.pilot['parts'] if p['code'] in (11, 15) and p['i'] not in st['replaced_pilot']]
                                 + [t['tri'] for t in r['comp'] if t['kind'] in (1, 5)])
        inpl = out.intersection(pl).difference(pilot_asph.buffer(0.02))
        # what is left in the pilot box is old asphalt outside the ideal road and > 2 studs from any asphalt (or under a
        # sidewalk): the pilot design left it out on purpose
        self.assertLess(inpl.intersection(pilot_asph.buffer(2.0)).area, 5.0, inpl.area)

    def test_no_shoulder_part_and_pilot_parts_handled(self):
        st, res = first_batches(1)
        r = res[0]
        self.assertTrue(all(o['code'] in range(1, 10) for o in r['rep_old']))
        self.assertGreater(len(r['rep_pilot']), 0)
        self.assertTrue(all(p['code'] in (11, 12, 13, 15, 21, 22, 23, 24, 25, 26) for p in r['rep_pilot']))


class Seams(unittest.TestCase):
    def test_city_batches_meet_without_a_hole(self):
        """b001 and b003 (its z0 neighbour) built in plan order: every lane wheel of every carriageway within 60 studs of
        their shared edge stands on a road part (away from the open east and west edges: the cells there are not built
        yet, so the old road goes on there, as in b001's frontier band)"""
        from shapely.geometry import box
        from tools.roadvis import city, city_qa
        CW, plan = city_world()
        ids = [b['id'] for b in plan['batches']]
        n = ids.index('b003') + 1
        st, res = first_batches(n)
        r1, r3 = res[0], res[n - 1]
        self.assertEqual(tuple(r3['box']), (24220.0, -550.0, 24820.0, 50.0))
        edge = box(4240.0, -10.0, 4800.0, 110.0)       # z 50 +- 60; x without the 20-stud bands at the open edges
        S = city_qa.CityState(CW, st, edge.buffer(30))
        lc = city_qa.lane_check(S, r3['ideal'], edge)
        self.assertGreater(lc['samples'], 100)
        self.assertEqual(lc['holes'], 0, lc['bad'][:5])
        # the two batches' asphalt on the shared line z = 50: same crossing points (no step, no notch)
        from shapely.geometry import LineString
        from shapely.ops import unary_union
        line = LineString([(4220.0, 50.0), (4820.0, 50.0)])
        a1 = unary_union([t['tri'] for t in r1['tris'] if t['kind'] == 1]).buffer(1e-6)
        a3 = unary_union([t['tri'] for t in r3['tris'] if t['kind'] == 1]).buffer(1e-6)
        l1, l3 = a1.intersection(line), a3.intersection(line)
        self.assertGreater(l1.length, 50)
        self.assertLess(l1.symmetric_difference(l3).length, 0.05)


class Frozen(unittest.TestCase):
    def test_b001_data_byte_identical(self):
        """batch 1 is shipped (the leader checked rv 021dd07c..., ground ab0c4b22... in main): the generator must still
        write it byte for byte, whatever the build order or the options of later batches"""
        import tempfile
        _qa.need_build('roadcity')
        from tools.roadvis import city, city_batch, city_ground
        CW, plan = city_world()
        if 'nr' not in _C:
            _C['nr'] = city_ground.NoRaise(_qa.BUILD, log=lambda *a: None)
        ctx = city_batch.prepare('b001', _qa.BUILD, log=lambda *a: None, loaded=(CW, plan, _C['nr']))
        with tempfile.TemporaryDirectory() as t:
            exp, x, gx, nx = city_batch.studio_data(ctx, t)
        self.assertEqual((x['sha1'], gx['sha1']), FROZEN_B001)
        self.assertEqual((x['parts'], x['replace']), (1057, 539))
        self.assertIn('b001', city.FROZEN)


class OptionB(unittest.TestCase):
    """no invisible RoadSupport wedge where the ground is raised to +0.9, from b003 on (b001 keeps its 9)"""

    def test_only_invisible_supports_go(self):
        from tools.roadvis import city
        st_b, res_b = cli_runs('b003')
        st_n, res_n = cli_runs('b003', cfg=dict(city.VARIANTS[city.DEFAULT_VARIANT], drop_supports_on_ground=False), key='noB')
        b, n = res_b['b003'], res_n['b003']

        def rows(res, field, kinds=None):
            return sorted(tuple(t['row']) + (t['kind'],) for t in res[field] if kinds is None or t['kind'] in kinds)
        for field in ('tris', 'comp'):
            self.assertEqual(rows(b, field, (1, 2, 3, 4)), rows(n, field, (1, 2, 3, 4)), field)     # every visible piece
            self.assertTrue(set(rows(b, field, (5,))) <= set(rows(n, field, (5,))), field)
        self.assertEqual(rows(b, 'front'), rows(n, 'front'))
        key = lambda sg: (round(float(sg[0][0]), 3), round(float(sg[0][1]), 3), round(float(sg[1][0]), 3), round(float(sg[1][1]), 3), sg[3])  # noqa: E731
        self.assertEqual(sorted(map(key, b['segs'])), sorted(map(key, n['segs'])))
        self.assertGreater(len(rows(n, 'tris', (5,))), len(rows(b, 'tris', (5,))))
        self.assertEqual((len(res_b['b001']['tris']), len(rows(res_b['b001'], 'tris', (5,)))),
                         (len(res_n['b001']['tris']), len(rows(res_n['b001'], 'tris', (5,)))), 'b001 keeps its supports')

    def test_b003_targets(self):
        q = qa_of('b003')
        bg = q['B_ground']
        self.assertEqual((bg['lanes_core']['holes'], bg['lanes_core']['drops']), (0, 0), bg['lanes_core'].get('bad'))
        self.assertEqual(bg['lanes_box']['drops'], 0)
        self.assertEqual(bg['grid_box']['drop_cells'], 0, bg['grid_box']['drops'][:5])
        # every run a car can drive (no wheel in a building): no drop, no climb; a hang (wheels 1.5 apart) only where
        # the car straddles an open edge (the neighbour is not built yet): a short static tilt
        sc = bg['spot_clear']
        self.assertGreater(sc['runs'], 30)
        self.assertEqual((sc['drops'], sc['climbs'], sc['with_climb']), (0, 0, 0))
        self.assertLessEqual(sc['hang'], 30)
        self.assertGreaterEqual(sc['min_up'], 0.95)
        for k, v in bg['offroad'].items():
            self.assertGreater(v['runs'], 5, k)
            self.assertEqual((v['with_drop'], v['with_climb']), (0, 0), k)
        seam = bg['seams']['b001']
        self.assertGreater(seam['lanes']['samples'], 100)
        self.assertEqual((seam['lanes']['holes'], seam['lanes']['drops'], seam['grid']['drop_cells']), (0, 0, 0))
        self.assertGreater(q['supports_dropped'], 0)

    def test_b002_pilot_seam(self):
        q = qa_of('b002')
        bg = q['B_ground']
        seam = bg['seams']['pilot']
        self.assertGreater(seam['lanes']['samples'], 100)
        self.assertEqual((seam['lanes']['holes'], seam['lanes']['drops'], seam['grid']['drop_cells']), (0, 0, 0))
        self.assertEqual((bg['lanes_core']['holes'], bg['lanes_core']['drops']), (0, 0), bg['lanes_core'].get('bad'))
        self.assertEqual(bg['grid_box']['drop_cells'], 0)


def qa_of(bid):
    p = _qa.need_build('roadcity', bid, 'qa.json')
    return _qa.load_json(p)


class Batch1Targets(unittest.TestCase):
    def setUp(self):
        self.qa = qa_of('b001')

    def test_lanes_and_drops(self):
        """0 lane holes in the box away from its frontier edges and across the seam with the pilot; at a frontier edge
        (the old road goes on, offset) a lane may leave the asphalt, but onto the ground at +0.9: no drop"""
        bg = self.qa['B_ground']
        self.assertGreater(bg['lanes_core']['samples'], 1500)
        self.assertEqual((bg['lanes_core']['holes'], bg['lanes_core']['drops']), (0, 0), bg['lanes_core'].get('bad'))
        self.assertEqual(bg['lanes_box']['drops'], 0, bg['lanes_box'].get('bad'))
        self.assertLessEqual(bg['lanes_box']['holes'], 10)
        self.assertEqual((bg['lanes_pilot_seam']['holes'], bg['lanes_pilot_seam']['drops']), (0, 0), bg['lanes_pilot_seam'].get('bad'))
        self.assertEqual(bg['grid_box']['drop_cells'], 0, bg['grid_box']['drops'][:5])
        self.assertEqual(bg['grid_pilot_seam']['drop_cells'], 0)
        self.assertLessEqual(bg['road_edges']['road_to_ground_max_step'], 0.6)

    def test_runs(self):
        bg = self.qa['B_ground']
        self.assertGreater(bg['spot']['runs'], 10)
        # every run a car can drive (no wheel in a building) has no drop, no climb and no hang
        self.assertGreater(bg['spot_clear']['runs'], 0.8 * bg['spot']['runs'])
        self.assertEqual((bg['spot_clear']['with_drop'], bg['spot_clear']['with_climb']), (0, 0))
        self.assertEqual(bg['spot']['drops'] + bg['spot']['climbs'], 0)
        self.assertEqual((bg['spot2_pilot_path_B']['with_drop'], bg['spot2_pilot_path_B']['with_climb']), (0, 0))
        for k, v in bg['offroad'].items():
            self.assertGreater(v['runs'], 5, k)
            self.assertEqual((v['with_drop'], v['with_climb']), (0, 0), k)

    def test_today_shows_the_problem(self):
        t = self.qa['today']
        self.assertGreater(t['grid_box']['drop_cells'], 1000)
        self.assertGreater(t['lanes_box']['holes'], 0)

    def test_probe_expectation(self):
        e = self.qa['probe_expected']
        self.assertEqual(e['0']['inBox']['ground'], 0, 'no lane centre over the terrain in the box')
        self.assertGreater(e['0']['inBox']['samples'], 300)


class StudioData(unittest.TestCase):
    def test_float32_split_and_counts(self):
        """every triangle row of the written city data splits the same way in Studio's float32 as offline (no near-tie
        of its two longest sides, no side within 0.004 of the builders' 0.05 skip), and every module's part count is
        what the builders' own rules make of its rows (the Luau `triangle` / `segment` skips)"""
        import glob
        from tools.roadvis import city
        from tools.qa import road_seams
        dirs = [_qa.need_build('roadcity', 'b001', 'roblox_rv')]
        dirs += sorted(glob.glob(os.path.join(_qa.BUILD, 'roadcity', 'data', '*', 'roblox_rv')))[:12]
        rows = 0
        for d in dirs:
            for f in sorted(os.listdir(d)):
                if not f.startswith('cell_'):
                    continue
                m = _qa.luau_table(os.path.join(d, f))
                n = 0
                for key, stride in (('tris', 7), ('ftris', 8)):
                    v = m.get(key) or []
                    v = v.get('_list', []) if isinstance(v, dict) else v
                    for i in range(0, len(v), stride):
                        row = [float(x) for x in v[i:i + 6]]
                        rows += 1
                        self.assertFalse(city.split_ambiguous(row), (d, f, row))
                        n += len(road_seams.wedge_tris(row[0:2], row[2:4], row[4:6]))
                v = m.get('segs') or []
                v = v.get('_list', []) if isinstance(v, dict) else v
                for i in range(0, len(v), 6):
                    ln = math.hypot(v[i + 2] - v[i], v[i + 3] - v[i + 1])
                    self.assertGreaterEqual(ln, 0.05 + city.AMBIG, (d, f, v[i:i + 6]))
                    n += 1
                self.assertEqual(n, m['parts'], (d, f))
        # not vacuous: every triangle row on disk was parsed and checked (a plain count of the numbers in the files)
        on_disk = 0
        for d in dirs:
            for f in os.listdir(d):
                if f.startswith('cell_'):
                    t = _qa.read(os.path.join(d, f))
                    for key, stride in (('tris', 7), ('ftris', 8)):
                        mm = re.search(r'\b' + key + r' = \{([^}]*)\}', t)
                        if mm:
                            on_disk += len([v for v in mm.group(1).split(',') if v.strip()]) // stride
        self.assertEqual(rows, on_disk)
        self.assertGreater(rows, 0)

    def test_install_bundle_is_current(self):
        """build/roadcity/b001/install (city_cli.py bundle b001): the builders in it are the repo's, the data is the
        batch's data on disk"""
        p = os.path.join(_qa.BUILD, 'roadcity', 'b001', 'install', 'roadcity_b001.json')
        if not os.path.exists(p):
            raise unittest.SkipTest('no bundle (tools/roadvis/city_cli.py bundle b001)')
        b = _qa.load_json(p)
        for name in ('PattayaRoadVisBuilder', 'PattayaRoadGroundBuilder'):
            self.assertEqual(b['ServerStorage/' + name], _qa.src(os.path.join('ServerStorage', name + '.luau')),
                             f'{name} in the bundle is stale: run city_cli.py bundle b001')
        d = os.path.join(_qa.BUILD, 'roadcity', 'b001', 'roblox_rv')
        for f in os.listdir(d):
            self.assertEqual(b['ServerStorage/PattayaDataRoadVis_b001/' + f[:-5]], _qa.read(os.path.join(d, f)), f)
        self.assertEqual(b['ServerStorage/PattayaDataRoadGround_b001/manifest'],
                         _qa.read(os.path.join(_qa.BUILD, 'roadcity', 'b001', 'roblox_ground', 'manifest.luau')))
        self.assertTrue(all(len(v) < 200 * 1024 for v in b.values()))

    def test_b003_bundle_is_current(self):
        """build/roadcity/b003/install (city_cli.py bundle b003 --no-builders): the data only (the builders were installed
        with b001), every module equal to the batch's data on disk"""
        p = os.path.join(_qa.BUILD, 'roadcity', 'b003', 'install', 'roadcity_b003.json')
        if not os.path.exists(p):
            raise unittest.SkipTest('no b003 bundle (tools/roadvis/city_cli.py bundle b003 --no-builders)')
        b = _qa.load_json(p)
        self.assertFalse([k for k in b if k.endswith('Builder')], 'the b003 bundle must not carry the builders')
        d = os.path.join(_qa.BUILD, 'roadcity', 'b003', 'roblox_rv')
        want = {'ServerStorage/PattayaDataRoadVis_b003/' + f[:-5]: os.path.join(d, f) for f in os.listdir(d)}
        want['ServerStorage/PattayaDataRoadGround_b003/manifest'] = os.path.join(_qa.BUILD, 'roadcity', 'b003', 'roblox_ground', 'manifest.luau')
        want['ServerStorage/PattayaDataRoadGroundNoRaise'] = os.path.join(_qa.BUILD, 'roadcity', 'noraise', 'PattayaDataRoadGroundNoRaise.luau')
        self.assertEqual(sorted(b), sorted(want))
        for k, f in want.items():
            self.assertEqual(b[k], _qa.read(f), f'{k} in the bundle is stale: run city_cli.py bundle b003 --no-builders')

    def test_caps_and_counts(self):
        d = _qa.need_build('roadcity', 'b001', 'roblox_rv')
        man = _qa.luau_table(os.path.join(d, 'manifest.luau'))
        tot = 0
        per_cell = {}
        for f in os.listdir(d):
            self.assertLess(os.path.getsize(os.path.join(d, f)), 200 * 1024, f)
            if f.startswith('cell_'):
                m = _qa.luau_table(os.path.join(d, f))
                self.assertLessEqual(m['parts'], 600, f)
                tot += m['parts']
                per_cell[m['cell']] = per_cell.get(m['cell'], 0) + m['parts']
        self.assertEqual(tot, man['counts']['parts'])
        self.assertTrue(all(v <= 600 for v in per_cell.values()), per_cell)
        self.assertEqual(man['batch']['id'], 'b001')
        self.assertEqual(man['batch']['builtBefore'], ['pilot'])
        self.assertEqual(man['replace']['total'], len(man['replace']['keys']) // 3)
        g = _qa.luau_table(os.path.join(_qa.need_build('roadcity', 'b001', 'roblox_ground'), 'manifest.luau'))
        self.assertAlmostEqual(g['occTop'], 0.725, places=6)
        self.assertEqual(len(g['columns']), g['region']['ni'])
        self.assertTrue(all(len(c) == 2 * g['region']['nk'] for c in g['columns']))
        self.assertEqual(g['probe']['expected']['floorPairsOver1_5'], 0)


# ---- the Road B builder, city mode, in the luau CLI --------------------------------------------------------------------
RV_TAIL = r'''
local RV = BUILDER
local W = workspace.PattayaWorld
local function folder(parent, name) local f = I.new("Folder") f.Name = name f.Parent = parent return f end
local cont = {}
for _, n in {"WideChunks", "WideJunctions", "ApronChunks", "FurnitureChunks", "ShoulderChunks"} do cont[n] = folder(W, n) end
local edge = I.new("Model") edge.Name = "Sukhumvit Road" edge.Parent = folder(cont.WideChunks, "Chunk_8_1")
local apr = folder(folder(cont.ApronChunks, "Chunk_a8_1"), "Aprons")
local fur = folder(cont.FurnitureChunks, "Chunk_f8_1")
local where = {edge, edge, edge, edge, cont.WideJunctions, cont.WideJunctions, apr, apr, fur}
local names = {"Road", "Sidewalk", "Dash", "Centre", "Junction", "Joint", "Road", "Sidewalk", "ZebraStripe"}
local function cfkey(c)
	local t = {}
	for _, v in {c.Position, c.XVector, c.YVector, c.ZVector} do table.insert(t, string.format("%.17g,%.17g,%.17g", v.X, v.Y, v.Z)) end
	return table.concat(t, ";")
end
-- the old parts of the fixtures with their real footprint boxes
local ORIG = {}
for _, o in OLD do
	local code = o[1]
	local c0, c1, c3 = Vector3.new(o[2], 0, o[3]), Vector3.new(o[4], 0, o[5]), Vector3.new(o[8], 0, o[9])
	local c2 = Vector3.new(o[6], 0, o[7])
	local ctr = (c0 + c1 + c2 + c3) / 4
	local ex, ez = c1 - c0, c3 - c0
	local p = I.new("Part") p.Name = names[code]
	p.Size = Vector3.new(ex.Magnitude, 4, ez.Magnitude)
	p.CFrame = CFrame.fromMatrix(Vector3.new(ctr.X, -1, ctr.Z), ex / ex.Magnitude, Vector3.new(0, 1, 0), ez / ez.Magnitude)
	if code == 7 then p:SetAttribute("Apron", true) end
	p.Parent = where[code]
	table.insert(ORIG, {p, where[code], cfkey(p.CFrame)})
end
-- a shoulder piece inside b001: never selected
local shc = folder(cont.ShoulderChunks, "Chunk_s8_1")
local S1 = I.new("Part") S1.Name = "Road" S1.Size = Vector3.new(4, 4, 4) S1.CFrame = CFrame.new(24500, -1, 400) S1:SetAttribute("Shoulder", true) S1.Parent = shc
-- the pilot as built
print("PILOT", RV.Build())
local function count(f) local n = 0 for _, p in f:GetDescendants() do if p:IsA("BasePart") then n += 1 end end return n end
local PILOT0 = count(W.RoadVisPilot)
local PILOTCF = {}
for _, p in W.RoadVisPilot:GetDescendants() do if p:IsA("BasePart") then PILOTCF[p] = {p.Parent, cfkey(p.CFrame)} end end
for _, id in BATCHES do
	print("PLAN_" .. id, (string.gsub(RV.Plan(id), "\n", " | ")))
	print("BUILD_" .. id, RV.Build(id))
	print("BUILDAGAIN_" .. id, RV.Build(id))
	local f = W.RoadVisCity[id]
	local n, front, bad = 0, 0, 0
	for _, c in f:GetChildren() do
		if c.ModelStreamingMode ~= "Atomic" then bad += 1 end
		for _, p in c:GetDescendants() do
			if p:IsA("BasePart") then
				n += 1
				if p:GetAttribute("RoadVisBatch") ~= id then bad += 1 end
				if p:GetAttribute("RoadVisFor") ~= nil then front += 1 end
			end
		end
	end
	print("COUNT_" .. id, n, front, bad, f:GetAttribute("Seq"))
	print("MOVE_" .. id, RV.MoveReplaced(id))
	print("MOVEAGAIN_" .. id, RV.MoveReplaced(id))
end
print("SHOULDER", S1.Parent == shc)
print("PROBE", (string.gsub(RV.Probe(BATCHES[1]), "\n", " | ")))
print("STATUS", (string.gsub(RV.Status(), "\n", " | ")))
print("PILOTREMOVE", RV.Remove())
for i = #BATCHES, 1, -1 do
	-- once, while every later batch is still built: the first batch is refused (b003 is its later neighbour)
	if i == #BATCHES and #BATCHES > 2 then print("EARLY_" .. BATCHES[1], RV.Remove(BATCHES[1])) end
	print("REMOVE_" .. BATCHES[i], RV.Remove(BATCHES[i]))
end
local back, cfok = 0, 0
for _, o in ORIG do
	if o[1].Parent == o[2] then back += 1 end
	if cfkey(o[1].CFrame) == o[3] and o[1]:GetAttribute("OriginalCFrame") == nil and o[1]:GetAttribute("RoadVisMoved") == nil then cfok += 1 end
end
local pback, pcf = 0, 0
for p, v in PILOTCF do
	if p.Parent == v[1] then pback += 1 end
	if cfkey(p.CFrame) == v[2] then pcf += 1 end
end
print("RESTORED", back, cfok, #ORIG, pback, pcf, PILOT0, count(W.RoadVisPilot))
print("LEFT", RV.Leftovers())
-- the order check: the last batch alone (its earlier batches are not built) is refused, nothing built
if #BATCHES > 1 then
	print("ORDER", RV.Build(BATCHES[#BATCHES]))
	print("ORDERSTATE", W:FindFirstChild("RoadVisCity") == nil)
end
for _, w in WARN do print("WARN", w) end
'''


def _rv_mods(d):
    return ['manifest'] + sorted(f[:-5] for f in os.listdir(d) if f.startswith('cell_'))


class LuauRoadVisCity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pd = _qa.need_build('roadvis', 'roblox')
        b1 = _qa.need_build('roadcity', 'b001', 'roblox_rv')
        root = os.path.join(_qa.BUILD, 'roadcity')
        batches = [('b001', b1, os.path.join(root, 'b001', 'fixture.json'))]
        for bid in ('b002', 'b003'):                 # b003 (b001's z0 side), b002 (the pilot's z1 side)
            d = os.path.join(root, 'data', bid, 'roblox_rv')
            fx = os.path.join(root, 'data', bid, 'fixture.json')
            if os.path.exists(os.path.join(d, 'manifest.luau')) and os.path.exists(fx):
                batches.append((bid, d, fx))
        if not os.path.exists(batches[0][2]):
            raise unittest.SkipTest('build/roadcity/b001/fixture.json missing (run tools/roadvis/city_cli.py batch b001)')
        # build in plan order (b001, b003, b002 since 2026-10-22): the manifests' seq
        batches.sort(key=lambda bt: _qa.luau_table(os.path.join(bt[1], 'manifest.luau'))['batch']['seq'])
        import test_roadvis
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadVisBuilder.luau'))
        parts = [test_shoulders.STUB, test_roadvis.EXTRA_STUB,
                 'local DATA = I.new("Folder") DATA.Name = "PattayaDataRoadVis" DATA.Parent = ServerStorage\n']
        for m in _rv_mods(pd):
            parts.append(f'moduleScript("{m}", function()\n{_qa.read(os.path.join(pd, m + ".luau"))}\nend).Parent = DATA\n')
        olds, seen = [], set()
        for bid, d, fx in batches:
            parts.append(f'do local D = I.new("Folder") D.Name = "PattayaDataRoadVis_{bid}" D.Parent = ServerStorage\n')
            for m in _rv_mods(d):
                parts.append(f'moduleScript("{m}", function()\n{_qa.read(os.path.join(d, m + ".luau"))}\nend).Parent = D\n')
            parts.append('end\n')
            for o in _qa.load_json(fx)['old']:
                k = (o['code'], tuple(tuple(c) for c in o['corners']))
                if k in seen:
                    continue
                seen.add(k)
                olds.append('{' + ','.join([str(o['code'])] + [repr(float(v)) for c in o['corners'] for v in c]) + '}')
        parts.append('OLD = {' + ',\n'.join(olds) + '}\n')
        parts.append('BATCHES = {' + ','.join(f'"{b[0]}"' for b in batches) + '}\n')
        parts.append('local require = function(m) return m._load() end\n')
        parts.append('local BUILDER = (function()\n' + src + '\nend)()\n')
        parts.append(RV_TAIL)
        cls.batches = [b[0] for b in batches]
        cls.mans = {b[0]: _qa.luau_table(os.path.join(b[1], 'manifest.luau')) for b in batches}
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=900)
        cls.lines = cls.out.splitlines()

    def line(self, tag):
        # the tail prints "TAG<tab>value"; the builders' own prints (e.g. "ORDER OK: ...") never start with a tag + tab
        got = [l for l in self.lines if l.startswith(tag + '\t')]
        self.assertTrue(got, f'{tag} missing; output tail: {self.out[-2500:]}')
        return got[0]

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-3000:])

    def test_plan_build_move(self):
        for bid in self.batches:
            man = self.mans[bid]
            p = self.line('PLAN_' + bid)
            self.assertIn('ORDER OK', p)
            self.assertIn('MATCHES the data', p)
            self.assertIn(f"built 0 cells" if False else 'built', self.line('BUILD_' + bid))
            self.assertIn('already built', self.line('BUILDAGAIN_' + bid))
            c = self.line('COUNT_' + bid).split()
            self.assertEqual(int(c[1]), man['counts']['parts'], bid)
            self.assertEqual(int(c[3]), 0, 'every cell Atomic, every part tagged with its batch')
            self.assertEqual(int(c[4]), man['batch']['seq'])
            m = self.line('MOVE_' + bid)
            moved = int(re.search(r'moved (\d+) parts', m).group(1))
            # every required key, plus the optional ones (parts within the float32 doubt of a box edge) that are there
            self.assertGreaterEqual(moved, man['replace']['total'], m)
            self.assertLessEqual(moved, man['replace']['total'] + man['replace']['optional'], m)
            self.assertIn('unmatched selected 0, required but not found 0', m)
            self.assertIn('already exists', self.line('MOVEAGAIN_' + bid))
        self.assertEqual(self.line('SHOULDER').split()[1], 'true')

    def test_frontier_pieces_tagged(self):
        man = self.mans['b001']
        front = int(self.line('COUNT_b001').split()[2])
        self.assertEqual(front, man['counts']['frontier'])
        if 'b003' in self.batches:
            m3 = self.line('MOVE_b003')
            self.assertIn('frontier RV Road', m3, 'b003 takes the frontier pieces b001 built in its box')

    def test_probe_and_status(self):
        p = self.line('PROBE')
        self.assertIn('road vis probe b001', p)
        self.assertIn(f"{len(self.mans['b001']['probe']['legs'])} legs", p)
        self.assertIn(f'{len(self.batches)} city batches built', self.line('STATUS'))

    def test_lifo_and_exact_restore(self):
        self.assertIn('pilot NOT removed', self.line('PILOTREMOVE'))
        if len(self.batches) > 2:
            self.assertIn('NOT removed', self.line('EARLY_b001'))
        for bid in self.batches:
            self.assertIn('backup removed', self.line('REMOVE_' + bid))
        r = self.line('RESTORED').split()
        self.assertEqual(r[1], r[3], 'every old part back in its parent')
        self.assertEqual(r[2], r[3], 'every CFrame exactly as before, builder attributes gone')
        self.assertEqual(r[4], r[5])
        self.assertEqual(r[6], r[7], 'every pilot part back')
        self.assertEqual(int(r[5]), int(r[7]))
        self.assertIn('leftovers: none', self.line('LEFT'))
        if len(self.batches) > 1:
            self.assertIn('ABORTED, nothing built', self.line('ORDER'))
            self.assertEqual(self.line('ORDERSTATE').split()[1], 'true')
        self.assertFalse([l for l in self.lines if l.startswith('WARN') and 'part-count mismatch' in l])


# ---- the city match: slivers a few tenths apart, in the place's order --------------------------------------------------
MATCH_TAIL = r'''
local RV = BUILDER
local W = workspace.PattayaWorld
local function folder(parent, name) local f = I.new("Folder") f.Name = name f.Parent = parent return f end
local apr = folder(folder(folder(W, "ApronChunks"), "Chunk_a9_-1"), "Aprons")
-- three apron slivers of b004 (Studio, 2026-10-23) in the order the place lists them: the first two are each within the
-- tolerance of two keys, and taking the first key in range left the third one without a key
for _, q in {{24839.467, -89.418}, {24839.670, -89.612}, {24839.309, -89.560}} do
	local p = I.new("Part") p.Name = "Road" p.Size = Vector3.new(0.4, 4, 0.4)
	p.CFrame = CFrame.new(q[1], -1, q[2])
	p:SetAttribute("Apron", true)
	p.Parent = apr
end
print("PLAN", (string.gsub(RV.Plan("t001"), "\n", " | ")))
'''


class LuauRoadVisCityMatch(unittest.TestCase):
    """matchCity pairs each part with its nearest key: keys closer together than the tolerance (b004's apron slivers at
    (24839.3, -89.6)) match whatever order the place lists the parts in."""

    def test_slivers_match_in_the_place_order(self):
        import test_roadvis
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadVisBuilder.luau'))
        man = ('return {batch = {id = "t001", seq = 1, group = "test", box = {24830, -100, 24850, -80}, overlapMin = 1, '
               'builtBefore = {}}, modules = {}, cells = {}, counts = {parts = 0, own = 0, completion = 0, frontier = 0, '
               'segs = 0}, replace = {keys = {7, 24839.31, -89.56, 7, 24839.47, -89.42, 7, 24839.67, -89.61}, '
               'optionalKeys = {}, tolerance = 0.3, total = 3, optional = 0}}')
        code, out = _qa.run_luau(''.join([
            test_shoulders.STUB, test_roadvis.EXTRA_STUB,
            'do local D = I.new("Folder") D.Name = "PattayaDataRoadVis_t001" D.Parent = ServerStorage\n',
            f'moduleScript("manifest", function()\n{man}\nend).Parent = D\nend\n',
            'local require = function(m) return m._load() end\n',
            'local BUILDER = (function()\n' + src + '\nend)()\n',
            MATCH_TAIL]))
        self.assertEqual(code, 0, out[-3000:])
        plan = [l for l in out.splitlines() if l.startswith('PLAN\t')]
        self.assertTrue(plan, out[-2500:])
        self.assertIn('MATCHES the data', plan[0])
        self.assertIn('selected 3 (required keys 3, optional keys 0 of 0 matched); unmatched selected 0, '
                      'required but not found 0', plan[0])


# ---- the ground builder, city mode, with the voxel Terrain mock --------------------------------------------------------
RG_TAIL = r'''
local RG = BUILDER
local man = require(DATA.manifest)
local oldClone = I.Clone
function I:Clone()
	local o = oldClone(self)
	if self.ClassName == "TerrainRegion" then
		rawset(o, "_cells", rawget(self, "_cells")) rawset(o, "SizeInCells", rawget(self, "SizeInCells"))
		for k, v in self._attr do o:SetAttribute(k, v) end
	end
	return o
end
function I:GetFullName() return "ServerStorage." .. self.Name end
-- the leader's hand raise of the pilot box (2026-10-22): backup first, then the box at occupancy 0.725 with a
-- 20-stud ramp (the model in tools/roadvis/city_ground.pilot_plan)
local PB = {24220, 648, 24820, 1252}
local bk = terrain:CopyRegion(Region3int16.new(Vector3int16.new(6048, -3, 156), Vector3int16.new(6212, 2, 319)))
bk.Name = "RoadGroundBackup_20261022" bk:SetAttribute("CornerCell", Vector3.new(6048, -3, 156)) bk.Parent = ServerStorage
local function pilotOcc(i, k)
	local cx, cz = 4 * i + 2, 4 * k + 2
	local dx = math.max(PB[1] - cx, cx - PB[3], 0)
	local dz = math.max(PB[2] - cz, cz - PB[4], 0)
	local d = math.sqrt(dx * dx + dz * dz)
	local f = if d <= 0 then 1 else math.clamp(1 - d / 20, 0, 1)
	return math.floor(f * 63 + 0.5) / 63 * 0.725
end
for i = 6050, 6210 do for k = 157, 318 do
	local o = pilotOcc(i, k)
	if o > 0 then vset(i, -1, k, Enum.Material.Ground, o) end
end end
local function snapAll()
	local t = {}
	for i = 6030, 6230 do for y = -3, 2 do for k = 0, 330 do
		local m, o = vget(i, y, k)
		if o > 0 or m ~= Enum.Material.Air then t[i .. "," .. y .. "," .. k] = m.Name .. o end
	end end end
	return t
end
local function diff(a, b)
	local n = 0
	for k, v in a do if b[k] ~= v then n += 1 end end
	for k, v in b do if a[k] ~= v then n += 1 end end
	return n
end
local RAISED = snapAll()
print("ADOPT", RG.Adopt("pilot", bk))
print("PLAN", (string.gsub(RG.Plan("b001"), "\n", " | ")))
-- 1. wrong terrain in the region (a water voxel): refused, nothing written
local g = man.region
vset(g.i0 + 30, -1, g.k0 + 30, Enum.Material.Water, 1)
print("WATER", RG.Build("b001"))
VOXELS[(g.i0 + 30) .. ",-1," .. (g.k0 + 30)] = nil
print("WATER_DIFF", diff(RAISED, snapAll()), WRITES)
-- 2. a never-raise column inside the data: refused, nothing written
local nr = ServerStorage[NRNAME]
local real = nr._load
nr._load = function() local t = real() local r = table.clone(t.runs) table.insert(r, g.i0 + 40) table.insert(r, g.k0 + 40) table.insert(r, g.k0 + 40) t.runs = r return t end
print("NORAISE", RG.Build("b001"))
nr._load = real
print("NORAISE_DIFF", diff(RAISED, snapAll()), WRITES)
-- 3. the build: every column the higher of the pilot raise and the data
WRITES = 0
print("BUILD", RG.Build("b001"))
print("BUILD2", RG.Build("b001"))
local bad, raisedCols, merged = 0, 0, 0
local alpha = man.alphabet
for a = 1, g.ni do
	local row = man.columns[a]
	for b = 1, g.nk do
		local i, k = g.i0 + a - 1, g.k0 + b - 1
		local lv = (string.find(alpha, string.sub(row, 2 * b, 2 * b), 1, true) or 1) - 1
		local want = math.max(lv / 63 * 0.725, pilotOcc(i, k))
		local m, o = vget(i, -1, k)
		if math.abs(o - math.floor(want * 255 + 0.5) / 255) > 1 / 255 + 1e-9 then bad += 1 end
		if lv > 0 then raisedCols += 1 end
		if lv > 0 and pilotOcc(i, k) >= lv / 63 * 0.725 then merged += 1 end
		local m2, o2 = vget(i, -2, k)
		local m0, o0 = vget(i, 0, k)
		if o2 ~= 1 or o0 ~= 0 then bad += 1 end
	end
end
print("COLUMNS", bad, raisedCols, merged, WRITES)
print("PROBE", (string.gsub(RG.Probe("b001"), "\n", " | ")))
print("STATUS", (string.gsub(RG.Status(), "\n", " | ")))
-- 4. last in, first out
print("PILOT_FIRST", RG.Remove("pilot"))
-- 5. the box changed after the build: refused until it is put back
local m9, o9 = vget(g.i0 + 50, -1, g.k0 + 50)
vset(g.i0 + 50, -1, g.k0 + 50, Enum.Material.Ground, 0.2)
print("CHANGED", RG.Remove("b001"))
vset(g.i0 + 50, -1, g.k0 + 50, m9, o9)
print("REMOVE", RG.Remove("b001"))
print("REMOVE_DIFF", diff(RAISED, snapAll()))
print("REMOVE_PILOT", RG.Remove("pilot"))
local pristine = 0
for i = 6040, 6220 do for k = 140, 330 do
	local m, o = vget(i, -1, k)
	if o ~= 0 then pristine += 1 end
end end
print("PRISTINE", pristine)
print("LEFT", RG.Leftovers())
for _, w in WARN do print("WARN", w) end
'''


class LuauRoadGroundCity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _qa.need_build('roadcity', 'b001', 'roblox_ground')
        nrp = _qa.need_build('roadcity', 'noraise', 'PattayaDataRoadGroundNoRaise.luau')
        import test_roadground
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadGroundBuilder.luau'))
        parts = [test_shoulders.STUB, test_roadground.MOCK,
                 'local DATA = I.new("Folder") DATA.Name = "PattayaDataRoadGround_b001" DATA.Parent = ServerStorage\n',
                 f'moduleScript("manifest", function()\n{_qa.read(os.path.join(d, "manifest.luau"))}\nend).Parent = DATA\n',
                 f'NRNAME = "PattayaDataRoadGroundNoRaise"\nmoduleScript(NRNAME, function()\n{_qa.read(nrp)}\nend).Parent = ServerStorage\n',
                 'local require = function(m) return m._load() end\n',
                 'local BUILDER = (function()\n' + src + '\nend)()\n', RG_TAIL]
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=900)
        cls.lines = cls.out.splitlines()
        cls.man = _qa.luau_table(os.path.join(d, 'manifest.luau'))

    def line(self, tag):
        got = [l for l in self.lines if l.startswith(tag + '\t') or l.startswith(tag + ' ')]
        self.assertTrue(got, f'{tag} missing; output tail: {self.out[-2500:]}')
        return got[0]

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-3000:])

    def test_adopt_and_plan(self):
        self.assertIn('adopted pilot', self.line('ADOPT'))
        p = self.line('PLAN')
        self.assertIn('READY', p)
        self.assertIn('pilot (seq 0)', p)

    def test_aborts_write_nothing(self):
        self.assertIn('ABORTED, nothing written', self.line('WATER'))
        self.assertEqual(self.line('WATER_DIFF').split()[1], '0')
        self.assertIn('never-raise zone (must be 0)', self.line('NORAISE'))
        self.assertIn('ABORTED, nothing written', self.line('NORAISE'))
        self.assertEqual(self.line('NORAISE_DIFF').split()[1], '0')

    def test_build_merges_with_the_pilot(self):
        self.assertIn('road ground b001: raised', self.line('BUILD'))
        self.assertIn('already built', self.line('BUILD2'))
        c = self.line('COLUMNS').split()
        self.assertEqual(c[1], '0', 'every column = the higher of the pilot raise and the data; layers -2 / 0 untouched')
        self.assertGreater(int(c[2]), 20000)
        self.assertGreater(int(c[3]), 100, 'the columns the pilot raise already holds as high are left alone')
        m = re.search(r'to y ([\d.]+)', self.line('BUILD'))
        self.assertAlmostEqual(float(m.group(1)), 0.9, delta=0.02)

    def test_probe_runs(self):
        p = self.line('PROBE')
        self.assertIn('road ground probe b001', p)
        self.assertIn('floor steps >= 1.5', p)

    def test_lifo_and_exact_restores(self):
        self.assertIn('NOT removed, remove these later raised batches first', self.line('PILOT_FIRST'))
        self.assertIn('changed since the build', self.line('CHANGED'))
        self.assertIn('restored EXACTLY', self.line('REMOVE'))
        self.assertEqual(self.line('REMOVE_DIFF').split()[1], '0', 'the pilot raise is back exactly as before b001')
        self.assertIn('restored EXACTLY', self.line('REMOVE_PILOT'))
        self.assertEqual(self.line('PRISTINE').split()[1], '0')
        self.assertIn('road ground leftovers: none', self.line('LEFT'))


# b003 builds second (2026-10-22): its ground after b001's, as in Studio (pilot adopted as seq 0, b001 built as seq 1)
RG3_TAIL = r"""
local RG = BUILDER
local oldClone = I.Clone
function I:Clone()
	local o = oldClone(self)
	if self.ClassName == "TerrainRegion" then
		rawset(o, "_cells", rawget(self, "_cells")) rawset(o, "SizeInCells", rawget(self, "SizeInCells"))
		for k, v in self._attr do o:SetAttribute(k, v) end
	end
	return o
end
function I:GetFullName() return "ServerStorage." .. self.Name end
local PB = {24220, 648, 24820, 1252}
local bk = terrain:CopyRegion(Region3int16.new(Vector3int16.new(6048, -3, 156), Vector3int16.new(6212, 2, 319)))
bk.Name = "RoadGroundBackup_20261022" bk:SetAttribute("CornerCell", Vector3.new(6048, -3, 156)) bk.Parent = ServerStorage
local function pilotOcc(i, k)
	local cx, cz = 4 * i + 2, 4 * k + 2
	local dx = math.max(PB[1] - cx, cx - PB[3], 0)
	local dz = math.max(PB[2] - cz, cz - PB[4], 0)
	local d = math.sqrt(dx * dx + dz * dz)
	local f = if d <= 0 then 1 else math.clamp(1 - d / 20, 0, 1)
	return math.floor(f * 63 + 0.5) / 63 * 0.725
end
for i = 6050, 6210 do for k = 157, 318 do
	local o = pilotOcc(i, k)
	if o > 0 then vset(i, -1, k, Enum.Material.Ground, o) end
end end
local function snapAll()
	local t = {}
	for i = 6030, 6230 do for y = -3, 2 do for k = -165, 185 do
		local m, o = vget(i, y, k)
		if o > 0 or m ~= Enum.Material.Air then t[i .. "," .. y .. "," .. k] = m.Name .. o end
	end end end
	return t
end
local function diff(a, b)
	local n = 0
	for k, v in a do if b[k] ~= v then n += 1 end end
	for k, v in b do if a[k] ~= v then n += 1 end end
	return n
end
local function level(man, i, k)
	local g = man.region
	local a, b = i - g.i0 + 1, k - g.k0 + 1
	if a < 1 or a > g.ni or b < 1 or b > g.nk then return 0 end
	return (string.find(man.alphabet, string.sub(man.columns[a], 2 * b, 2 * b), 1, true) or 1) - 1
end
local m1 = require(ServerStorage.PattayaDataRoadGround_b001.manifest)
local m3 = require(ServerStorage.PattayaDataRoadGround_b003.manifest)
local RAISED = snapAll()
print("ADOPT", RG.Adopt("pilot", bk))
print("BUILD1", RG.Build("b001"))
local AFTER1 = snapAll()
print("PLAN3", (string.gsub(RG.Plan("b003"), "\n", " | ")))
WRITES = 0
print("BUILD3", RG.Build("b003"))
-- every column of b003's region: the highest of the pilot raise, b001's data and b003's data
local g = m3.region
local bad, cols, kept = 0, 0, 0
for a = 1, g.ni do for b = 1, g.nk do
	local i, k = g.i0 + a - 1, g.k0 + b - 1
	local l3 = level(m3, i, k)
	local before = math.max(level(m1, i, k) / 63 * 0.725, pilotOcc(i, k))
	local want = math.max(l3 / 63 * 0.725, before)
	local m, o = vget(i, -1, k)
	if math.abs(o - math.floor(want * 255 + 0.5) / 255) > 1 / 255 + 1e-9 then bad += 1 end
	if l3 > 0 then cols += 1 end
	if l3 > 0 and before >= l3 / 63 * 0.725 then kept += 1 end
	local m2, o2 = vget(i, -2, k)
	local m0, o0 = vget(i, 0, k)
	if o2 ~= 1 or o0 ~= 0 then bad += 1 end
end end
print("COLUMNS3", bad, cols, kept, WRITES)
print("PROBE3", (string.gsub(RG.Probe("b003"), "\n", " | ")))
print("STATUS3", (string.gsub(RG.Status(), "\n", " | ")))
print("REMOVE1EARLY", RG.Remove("b001"))
print("REMOVE3", RG.Remove("b003"))
print("DIFF3", diff(AFTER1, snapAll()))
print("REMOVE1", RG.Remove("b001"))
print("DIFF1", diff(RAISED, snapAll()))
print("LEFT", RG.Leftovers())
for _, w in WARN do print("WARN", w) end
"""


class LuauRoadGroundCityB003(unittest.TestCase):
    """b003's ground after b001's in the voxel Terrain mock (the Studio order since 2026-10-22: pilot adopted as seq 0,
    b001 seq 1, b003 seq 2): READY with b001 as a raised neighbour, every column the highest of the pilot raise, b001
    and b003, b001 cannot be removed first, both restore exactly. (The ground builder has no order check of its own:
    its max rule makes the result the same in any order, and the registry seq is the order of the builds.)"""

    @classmethod
    def setUpClass(cls):
        d1 = _qa.need_build('roadcity', 'b001', 'roblox_ground')
        d3 = os.path.join(_qa.BUILD, 'roadcity', 'b003', 'roblox_ground')
        if not os.path.exists(os.path.join(d3, 'manifest.luau')):
            raise unittest.SkipTest('build/roadcity/b003/roblox_ground missing (run tools/roadvis/city_cli.py batch b003)')
        nrp = _qa.need_build('roadcity', 'noraise', 'PattayaDataRoadGroundNoRaise.luau')
        import test_roadground
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadGroundBuilder.luau'))
        parts = [test_shoulders.STUB, test_roadground.MOCK]
        for bid, d in (('b001', d1), ('b003', d3)):
            parts += [f'do local D = I.new("Folder") D.Name = "PattayaDataRoadGround_{bid}" D.Parent = ServerStorage\n',
                      f'moduleScript("manifest", function()\n{_qa.read(os.path.join(d, "manifest.luau"))}\nend).Parent = D end\n']
        parts += [f'NRNAME = "PattayaDataRoadGroundNoRaise"\nmoduleScript(NRNAME, function()\n{_qa.read(nrp)}\nend).Parent = ServerStorage\n',
                  'local require = function(m) return m._load() end\n',
                  'local BUILDER = (function()\n' + src + '\nend)()\n', RG3_TAIL]
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=900)
        cls.lines = cls.out.splitlines()
        cls.man = _qa.luau_table(os.path.join(d3, 'manifest.luau'))

    def line(self, tag):
        got = [l for l in self.lines if l.startswith(tag + '\t')]
        self.assertTrue(got, f'{tag} missing; output tail: {self.out[-2500:]}')
        return got[0]

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-3000:])

    def test_plan_and_build_merge_with_b001(self):
        p = self.line('PLAN3')
        self.assertIn('READY', p)
        self.assertNotIn('NOT READY', p)
        self.assertIn('b001 (seq 1)', p)
        b = self.line('BUILD3')
        m = re.search(r'raised (\d+) columns to y ([\d.]+).*?; (\d+) data columns already as high or higher', b)
        self.assertTrue(m, b)
        n, y, k = int(m.group(1)), float(m.group(2)), int(m.group(3))
        self.assertAlmostEqual(y, 0.9, delta=0.02)
        self.assertIn('(seq 2)', b)
        c = self.line('COLUMNS3').split()
        self.assertEqual(c[1], '0', 'every column = the highest of the pilot raise, b001 and b003; layers -2 / 0 untouched')
        self.assertEqual(n + k, int(c[2]))
        self.assertEqual(k, int(c[3]), 'the columns b001 (or the pilot) already hold as high are left alone')
        self.assertEqual(n + k, self.man['counts']['written'])

    def test_probe(self):
        p = self.line('PROBE3')
        self.assertIn('road ground probe b003', p)
        self.assertIn('floor steps >= 1.5: 0', p)

    def test_lifo_and_exact_restores(self):
        self.assertIn('NOT removed', self.line('REMOVE1EARLY'))
        self.assertIn('restored EXACTLY', self.line('REMOVE3'))
        self.assertEqual(self.line('DIFF3').split()[1], '0', 'b001 and the pilot raise exactly as before b003')
        self.assertIn('restored EXACTLY', self.line('REMOVE1'))
        self.assertEqual(self.line('DIFF1').split()[1], '0')
        self.assertIn('road ground leftovers', self.line('LEFT'))

class BuilderSource(unittest.TestCase):
    def test_city_conventions(self):
        rv = _qa.strip_comments(_qa.src(os.path.join('ServerStorage', 'PattayaRoadVisBuilder.luau')))
        for k in ('RoadVisCity', 'RoadVisCityBackup', 'PattayaDataRoadVis_', 'RoadVisFor', 'RoadVisBatch'):
            self.assertIn(k, rv)
        self.assertNotIn('EditableMesh', rv.split('CITY BATCHES')[-1] if 'CITY BATCHES' in rv else '')
        rg = _qa.strip_comments(_qa.src(os.path.join('ServerStorage', 'PattayaRoadGroundBuilder.luau')))
        for k in ('RoadGroundCity', 'PattayaDataRoadGround_', 'PattayaDataRoadGroundNoRaise', 'WriteVoxels', 'PasteRegion'):
            self.assertIn(k, rg)
        self.assertNotIn('FillBlock', rg)


class GroundProbeFields(unittest.TestCase):
    """b018 has no road-to-ground edge pair: its manifest leaves the edge steps out instead of failing the export"""

    def test_no_edge_pairs(self):
        from tools.roadvis import city_ground
        p = city_ground.probe_fields({'rays': 4}, [])
        self.assertEqual(sorted(p), ['expected', 'grid'])
        self.assertNotIn('edgeStep', city_ground.lua(p))

    def test_edge_pairs(self):
        from tools.roadvis import city_ground
        p = city_ground.probe_fields({'rays': 4}, [(0, 0, 1, 1, 0.21), (0, 0, 1, 1, 0.1)])
        self.assertEqual((p['edgeStepMin'], p['edgeStepMax']), (0.1, 0.21))


if __name__ == '__main__':
    unittest.main()
