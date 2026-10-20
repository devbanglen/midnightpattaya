"""Offline tests for the streaming architecture work (team16/streaming-arch): tools/mapgen/streaming_analysis.py and
roblox/src/ServerStorage/StreamingPrototype.luau. Read-only; needs build/ (skipped without it)."""
import os
import re
import subprocess
import sys
import unittest

import _qa

sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'mapgen'))
import streaming_analysis as SA  # noqa: E402

PROTO = os.path.join(_qa.SRC, 'ServerStorage', 'StreamingPrototype.luau')
_CACHE = {}


def items():
    if 'items' not in _CACHE:
        _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
        _CACHE['items'] = SA.collect(_qa.BUILD)
    return _CACHE['items']


def centre():
    return SA.PROTO_CENTRE_WORLD[0] - SA.ORIGIN_X, SA.PROTO_CENTRE_WORLD[1]


def plan(variant):
    key = 'plan' + variant
    if key not in _CACHE:
        _CACHE[key] = SA.proto_plan(items(), variant, *centre())
    return _CACHE[key]


class Analysis(unittest.TestCase):
    def test_deterministic(self):
        a = SA.chunk_table(items())
        b = SA.chunk_table(SA.collect(_qa.BUILD))
        self.assertEqual(a, b)
        p1 = SA.proto_plan(items(), 'B', *centre())
        p2 = SA.proto_plan(items(), 'B', *centre())
        self.assertEqual(p1['assign'], p2['assign'])
        self.assertEqual(p1['containers'], p2['containers'])
        lay = SA.layout(items(), 'b')
        path = SA.road_chain(_qa.BUILD, 'Sukhumvit Road', 2000.0)
        self.assertGreater(len(path), 2)
        r1 = SA.simulate(lay, path, 200.0, 'b', warm=True)
        r2 = SA.simulate(SA.layout(items(), 'b'), path, 200.0, 'b', warm=True)
        self.assertEqual(r1, r2)

    def test_model_matches_studio_counts(self):
        """chunk model counts per PattayaWorld folder as the leader counted them in Studio (2026-10-20); the
        largest WideChunks model was 2,142 descendants there"""
        f = SA.folder_table(SA.chunk_table(items()))
        want = {'Chunks': 93, 'WideChunks': 522, 'ApronChunks': 375, 'FurnitureChunks': 282, 'VisSliceChunks': 59,
                'CoastChunks': 48, 'LandmarkChunks': 12}
        self.assertEqual({k: f[k]['chunks'] for k in want}, want)
        self.assertLess(abs(f['WideChunks']['max'] - 2142), 2142 * 0.03)
        self.assertEqual(f['Junctions']['total'], 495)
        total = sum(v['total'] for v in f.values())
        self.assertLess(abs(total - 184000) / 184000, 0.05, total)  # PattayaWorld about 184k descendants

    def test_layout_partitions_every_instance(self):
        base = sum(i.n for i in items() if i.cat != 'model')
        for v in ('a', 'b', 'b2', 'c', 'd'):
            units = SA.layout(items(), v)
            got = sum(sum(it.n for it in u.items if it.cat != 'model') for u in units)
            self.assertEqual(got, base, v)
            ids = [id(it) for u in units for it in u.items if it.cat != 'model']
            self.assertEqual(len(ids), len(set(ids)), v)

    def test_roads_only_in_road_layer(self):
        for v in ('b', 'b2', 'c', 'd'):
            for u in SA.layout(items(), v):
                if u.layer != 'road':
                    self.assertEqual(u.roadn, 0, (v, u.uid))
                    self.assertFalse(any(it.cat == 'marking' for it in u.items), (v, u.uid))
                else:
                    self.assertIn(u.mode, ('atomic', 'persistent'), (v, u.uid))

    def test_layout_caps(self):
        for v in ('b', 'c', 'd'):
            for u in SA.layout(items(), v):
                if u.mode in ('atomic', 'atomic_lod'):
                    self.assertTrue(u.n <= 1501 or len(u.items) == 1, (v, u.uid, u.n))
                    self.assertLessEqual(u.maxx - u.minx, 256, u.uid)
                    self.assertLessEqual(u.maxz - u.minz, 256, u.uid)


class ProtoPlan(unittest.TestCase):
    def test_every_part_placed_once(self):
        for v in ('A', 'B', 'C', 'D'):
            p = plan(v)
            idx = [k for k, _ in p['assign']]
            self.assertEqual(sorted(idx), list(range(len(p['source']))), v)
            roads = [k for k, it in enumerate(p['source']) if it.cat == 'road']
            self.assertGreater(len(roads), 500)
            placed = [k for k, _ in p['assign'] if p['source'][k].cat == 'road']
            self.assertEqual(sorted(placed), roads, v)

    def test_roads_never_decorative(self):
        for v in ('B', 'C', 'D'):
            p = plan(v)
            for k, name in p['assign']:
                c = p['containers'][name]
                if p['source'][k].cat in ('road', 'marking'):
                    self.assertEqual((c['mode'], c['layer']), ('atomic', 'road'), (v, name))
                    self.assertTrue(name.startswith('Roads/'), name)
                else:
                    self.assertNotEqual(c['layer'], 'road', (v, name))
        # control: the road parts stay in their source chunk (the Atomic mixed models of today)
        for k, name in plan('A')['assign']:
            self.assertTrue(name.startswith('Control/') or name.startswith('Loose/'), name)

    def test_chunk_caps(self):
        for v in ('B', 'C', 'D'):
            for name, c in plan(v)['containers'].items():
                if c['mode'].startswith('atomic'):
                    self.assertTrue(c['n'] <= SA.PROTO_CAP or c['items'] == 1, (v, name, c['n']))

    def test_variant_c_moves_only_detail(self):
        p = plan('C')
        for k, name in p['assign']:
            if p['containers'][name]['mode'] == 'client':
                self.assertEqual(p['source'][k].cat, 'detail')

    def test_district_is_dense(self):
        """the district covers TargetRadius around its centre and holds a city-centre amount of instances"""
        self.assertGreaterEqual(SA.PROTO_HALF, SA.PC['target_radius'])
        self.assertGreater(sum(it.n for it in plan('A')['source']), 15000)


class PrototypeLuau(unittest.TestCase):
    def test_compiles(self):
        exe = _qa.find_luau('luau-compile')
        if not exe:
            self.skipTest('luau-compile not found')
        r = subprocess.run([exe, '--null', PROTO], capture_output=True, text=True, encoding='utf-8', errors='replace')
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)

    def test_constants_match_python(self):
        s = _qa.read(PROTO)
        num = lambda k: float(re.search(rf'\b{k} = (-?[\d.]+)', s).group(1))
        self.assertEqual(num('cell'), SA.PROTO_CELL)
        self.assertEqual(num('cap'), SA.PROTO_CAP)
        self.assertEqual(num('half'), SA.PROTO_HALF)
        self.assertEqual(num('offsetX'), SA.PROTO_OFFSET_X)
        self.assertEqual(num('nearRadius'), SA.NEAR_RADIUS)
        self.assertEqual(num('clientBudget'), SA.CLIENT_BUDGET)
        self.assertEqual(num('minRadius'), SA.PC['min_radius'])
        self.assertEqual(num('targetRadius'), SA.PC['target_radius'])
        c = re.search(r'centre = Vector3\.new\(([-\d.]+), 0, ([-\d.]+)\)', s)
        self.assertEqual((float(c.group(1)), float(c.group(2))), SA.PROTO_CENTRE_WORLD)
        roads = set(re.findall(r'(\w+) = true', re.search(r'local ROAD_NAMES = \{([^}]*)\}', s).group(1)))
        self.assertEqual(roads, {'Road', 'Sidewalk', 'Junction', 'Joint'})

    def test_main_world_is_only_read(self):
        """the builder clones source parts and never moves, edits or destroys them"""
        s = _qa.strip_comments(_qa.read(PROTO))
        self.assertIn('it.part:Clone()', s)
        for bad in (r'it\.part\.Parent\s*=', r'it\.part:Destroy', r'it\.part:PivotTo', r'it\.part\.CFrame\s*=',
                    r'it\.part:SetAttribute', r'\.part\.\w+\s*=[^=]'):
            self.assertIsNone(re.search(bad, s), bad)
        # Destroy() only on the prototype's own containers
        receivers = re.findall(r'([\w.]+)(?: :: \w+\))?:Destroy\(\)', s)
        self.assertTrue(receivers)
        self.assertLessEqual(set(receivers), {'old', 'inst', 't.live', 'folder'}, receivers)
        self.assertIn('function P.Remove', s)
        self.assertIn('assert(isEdit()', s)

    def test_luau_plan_matches_python(self):
        """StreamingPrototype.MakePlan (run in the luau CLI on the district's items) == streaming_analysis.proto_plan"""
        if not _qa.find_luau('luau'):
            self.skipTest('luau CLI not found')
        src = _qa.read(PROTO)
        for v in ('A', 'B', 'C', 'D'):
            p = plan(v)
            rows = []
            for it in p['source']:
                root = it.chunk.split('/')[0]
                chunk = it.chunk if it.chunk in SA.LOOSE else it.chunk.replace('/', '_')
                rows.append('{x=%r,z=%r,n=%d,cat="%s",root="%s",chunk="%s"}' % (it.x + SA.ORIGIN_X, it.z, it.n, it.cat, root, chunk))
            main = (_qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau')) + '\n'
                    'game = {GetService = function() return {} end}\nscript = {}\n'
                    'local P = (function()\n' + src + '\nend)()\n'
                    'local items = {' + ',\n'.join(rows) + '}\n'
                    'local conts = P.MakePlan("' + v + '", items)\n'
                    'local keys = {}\nfor k in conts do table.insert(keys, k) end\ntable.sort(keys)\n'
                    'for _, k in keys do local c = conts[k]; print(k .. "\\t" .. c.n .. "\\t" .. #c.items .. "\\t" .. c.mode) end\n')
            code, out = _qa.run_luau(main)
            self.assertEqual(code, 0, out[-2000:])
            got = {}
            for line in out.strip().splitlines():
                k, n, cnt, mode = line.split('\t')
                got[k] = (int(n), int(cnt), mode.lower().replace('atomiclod', 'atomic_lod'))
            want = {k: (c['n'], c['items'], c['mode']) for k, c in p['containers'].items()}
            self.assertEqual(got, want, v)


if __name__ == '__main__':
    unittest.main()
