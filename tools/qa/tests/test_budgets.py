"""Instance / memory budgets of the generated world (build/, gitignored) against the documented budgets:
docs/PERFORMANCE_BUDGET.md, docs/VISUAL_PERFORMANCE.md, docs/STREET_FURNITURE.md, docs/WORLD_CHUNKS.md and the
exporter configs in tools/mapgen/config (the configs are what the exporters enforce; the docs are what was promised).
Also the LOD / streaming profile table in PERFORMANCE_BUDGET.md vs ServerStorage/PattayaPerfProfile.luau."""
import glob
import os
import re
import unittest

import _qa

MODULE_LIMIT = 200 * 1024  # docs/WORLD_CHUNKS.md: "the 200 KB per-module limit"


def cfg(name):
    return _qa.load_json(os.path.join(_qa.CONFIG, name + '.json'))


def doc(name):
    return _qa.read(os.path.join(_qa.DOCS, name))


def num(s):
    return int(s.replace(',', ''))


class ChunkBudgets(unittest.TestCase):
    def _batches(self, batches, chunk_ids, limit):
        seen = []
        for b, v in batches.items():
            ids = v['chunks'] if isinstance(v, dict) else v
            self.assertLessEqual(len(ids), limit, f'batch {b} has {len(ids)} chunks')
            seen += ids
        self.assertEqual(sorted(seen), sorted(chunk_ids), 'every chunk in exactly one batch')

    def test_vis_slice(self):
        v = _qa.load_json(_qa.need_build('vis_slice', 'vis_slice.json'))
        c = cfg('vis_slice')
        cap, per_batch = c['max_parts_per_chunk'], c['max_chunks_per_batch']
        self.assertEqual(cap, 600, 'VISUAL_PERFORMANCE.md: <= 600 parts per chunk')
        over = {k: x['parts'] for k, x in v['chunks'].items() if x['parts'] > cap}
        self.assertEqual(over, {})
        self.assertEqual(v['over_part_cap_chunks'], [])
        budget = num(re.search(r'budget ≤ ([\d,]+)\)', doc('VISUAL_PERFORMANCE.md')).group(1))
        self.assertLessEqual(v['total_parts'], budget)
        self.assertEqual(sum(x['parts'] for x in v['chunks'].values()), v['total_parts'])
        self._batches(v['batches'], list(v['chunks']), per_batch)
        for b, x in v['batches'].items():
            self.assertEqual(x['parts'], sum(v['chunks'][k]['parts'] for k in x['chunks']), b)
        self.assertEqual({k: n for k, n in v['checks'].items() if n}, {}, 'exporter footprint checks')
        mods = {os.path.basename(p)[6:-5] for p in glob.glob(os.path.join(_qa.BUILD, 'vis_slice', 'roblox', 'chunk_*.luau'))}
        self.assertEqual(sorted(set(v['chunks']) - mods), [], 'chunk modules missing in build/vis_slice/roblox')

    def test_street_furniture(self):
        f = _qa.load_json(_qa.need_build('furniture', 'furniture.json'))
        budget = cfg('furniture')['budget']
        m = re.search(r'Total ≤ ([\d,]+) Parts, each chunk ≤ (\d+)', doc('STREET_FURNITURE.md'))
        self.assertEqual(num(m.group(1)), budget['max_total_parts'])
        self.assertEqual(int(m.group(2)), budget['max_parts_per_chunk'])
        self.assertLessEqual(f['total_parts'], num(m.group(1)))
        self.assertEqual(sum(x['parts'] for x in f['counts'].values()), f['total_parts'])
        self.assertEqual({k: n for k, n in f['stats'].items() if k.startswith('check_') and n}, {})
        self._batches(f['batches'], list(f['chunks']), budget['batch_size_chunks'])

    def test_junction_aprons(self):
        a = _qa.load_json(_qa.need_build('aprons', 'aprons.json'))
        b = cfg('aprons')['budget']
        self.assertEqual(a['chunks_over_part_cap'], [])
        self.assertEqual({k: n for k, n in a['checks'].items() if n}, {})
        for name, ids in a['batches'].items():
            self.assertLessEqual(len(ids), b['batch_size_chunks'], name)
        self.assertEqual(sum(len(x) for x in a['batches'].values()), a['chunks'])

    def test_coast(self):
        r = _qa.load_json(_qa.need_build('coast', 'coast_report.json'))
        c = cfg('coast')
        self.assertLessEqual(r['max_chunk_parts'], c['max_parts_per_chunk'])
        self.assertLessEqual(r['prop_parts'] + r['island_parts'], c['max_parts_total'])
        for name, ids in r['batches'].items():
            self.assertLessEqual(len(ids), c['batch_size'], name)
        self.assertEqual(sum(len(x) for x in r['batches'].values()), r['chunks'])
        self.assertEqual(r['terrain']['cells_touching_roads_discs_buildings'], 0)
        self.assertEqual({k: n for k, n in r['export_check'].items() if n}, {})

    def test_landmarks(self):
        L = _qa.load_json(_qa.need_build('landmarks', 'landmarks.json'))
        c = cfg('landmarks')
        for lm in L['landmarks']:
            self.assertLessEqual(lm['parts'], c['max_parts_per_landmark'], lm['id'])
        for name, ids in L['batches'].items():
            self.assertLessEqual(len(ids), c['batch_size'], name)
        self.assertEqual(sorted(sum(L['batches'].values(), [])), sorted(L['chunks']))
        self.assertTrue(all(b <= MODULE_LIMIT for b in L['module_bytes'].values()))

    def test_wide_world_buildings_per_chunk(self):
        cap = cfg('pattaya_wide')['buildings']['lod']['max_per_chunk']
        files = glob.glob(os.path.join(_qa.need_build('pattaya_wide', 'roblox'), 'chunk_*.luau'))
        self.assertGreater(len(files), 400)
        worst = (0, '')
        for p in files:
            m = re.search(r'buildings = \{([^}]*)\}', _qa.read(p))
            n = 0 if not m or not m.group(1).strip() else (m.group(1).count(',') + 1) // 8  # PattayaBuilder: 8/row
            worst = max(worst, (n, os.path.basename(p)))
        self.assertLessEqual(worst[0], cap, f'{worst[1]} has {worst[0]} buildings')

    def test_module_sizes(self):
        if not _qa.BUILD:
            self.skipTest('build/ not found')
        big = []
        files = glob.glob(os.path.join(_qa.BUILD, '*', 'roblox*', '*.luau'))
        files = [f for f in files if '_prev' not in f]
        self.assertGreater(len(files), 500)
        for p in files:
            if os.path.getsize(p) > MODULE_LIMIT:
                big.append(f'{os.path.relpath(p, _qa.BUILD)} {os.path.getsize(p) // 1024} KB')
        self.assertEqual(big, [])

    def test_vis_assets_triangles(self):
        m = _qa.load_json(_qa.need_build('vis_assets', 'manifest.json'))
        lim = m['summary']['limits']
        doc_lim = num(re.search(r'≤ ([\d,]+) per asset enforced', doc('VISUAL_PERFORMANCE.md')).group(1))
        self.assertEqual(lim['asset_tris_budget'], doc_lim)
        bad = [(a['name'], a['tris'], len(a['materials'])) for a in m['assets']
               if a['tris'] > lim['asset_tris_budget'] or len(a['materials']) > lim['materials'] or not a['ok']]
        self.assertEqual(bad, [])


class PerfProfiles(unittest.TestCase):
    """The profile table in PERFORMANCE_BUDGET.md == PattayaPerfProfile.PROFILES; client defaults == pc profile."""

    @classmethod
    def setUpClass(cls):
        src = _qa.src('ServerStorage/PattayaPerfProfile.luau')
        cls.prof = {}
        for name, body in re.findall(r'\n\t(\w+) = \{\n(.*?)\n\t\},', src, re.S):
            cls.prof[name] = {k: v.strip('"') for k, v in re.findall(r'(\w+) = ("?\w+"?)', body)}

    def test_doc_table(self):
        rows = re.findall(r'^\| `(\w+)`[^|]*\| (\d+) \| (\d+) \| (\w+) \| (\w+) \| (\d+)[^|]*\| (\d+) \| (\d+) \| (\d+) / (\d+) \|$',
                          doc('PERFORMANCE_BUDGET.md'), re.M)
        self.assertEqual(sorted(r[0] for r in rows), sorted(self.prof), 'doc lists every profile')
        keys = ['StreamingMinRadius', 'StreamingTargetRadius', 'StreamOutBehavior', 'ModelStreamingBehavior',
                'LOD_FacadeRange', 'LOD_PropRange', 'LOD_SpotCap', 'LOD_LampLightRange', 'LOD_FloodLightRange']
        for r in rows:
            p = self.prof[r[0]]
            for k, want in zip(keys, r[1:]):
                self.assertEqual(p[k], want, f'{r[0]}.{k}: code {p[k]} vs doc {want}')

    def test_client_defaults_are_pc(self):
        pc = self.prof['pc']
        lod = _qa.src('StarterPlayer/StarterPlayerScripts/PattayaLOD.client.luau')
        lights = _qa.src('StarterPlayer/StarterPlayerScripts/PattayaNightLights.client.luau')
        d = dict(re.findall(r'(LOD_\w+) = (\d+)', re.search(r'local DEFAULTS = \{(.*?)\}', lod).group(1)))
        d.update(re.findall(r'(LOD_\w+) = (\d+)', re.search(r'local SPOT_DEFAULTS = \{(.*?)\}', lights).group(1)))
        for k, v in d.items():
            self.assertEqual(pc[k], v, f'{k}: client default {v} vs pc profile {pc[k]}')

    def test_mobile_is_lighter_than_pc(self):
        pc, mob = self.prof['pc'], self.prof['mobile']
        for k in ('StreamingMinRadius', 'StreamingTargetRadius', 'LOD_FacadeRange', 'LOD_PropRange', 'LOD_Budget',
                  'LOD_SpotCap', 'LOD_LampLightRange', 'LOD_FloodLightRange'):
            self.assertLessEqual(int(mob[k]), int(pc[k]), k)
        # streaming must keep ~1,000 studs of road ahead on pc (doc), min radius = one 512 chunk
        self.assertGreaterEqual(int(pc['StreamingTargetRadius']), 1000)
        self.assertGreaterEqual(int(pc['StreamingMinRadius']), 512)


if __name__ == '__main__':
    unittest.main()
