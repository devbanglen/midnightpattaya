"""Original design v2 of the red sports car (docs/CAR_IMPORT_RED_SPORTS.md, "Original design v2").

Offline checks of art/cars3d/roblox/red_sports_original_v2*: triangle budgets, the separated-wheel rig (pivot on
the axle, bounding box centred, round about X, radius = layout radius, layout unchanged), the body bounding box
unchanged (Roblox centres the MeshPart on it, so the wheel layout stays valid), the shape edits stay in their
regions, the new parts and the sharp emblem are present, the paints, no brand words, upload marked BLOCKED, and the
files are distinct from the originals (which must still be the exact inputs the build used).
Needs numpy + Pillow (the repo .venv has both); skipped otherwise.
"""
import hashlib
import json
import os
import sys
import unittest

import _qa

try:
    import numpy as np
    from PIL import Image  # noqa: F401
    sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'gpu'))
    import car_debrand as cd
    import car_original_v2 as v2
except ImportError as e:            # pragma: no cover
    cd = v2 = None
    _why = str(e)

CARS = os.path.join(_qa.ROOT, 'art', 'cars3d', 'roblox')
QA = os.path.join(_qa.ROOT, 'art', 'cars3d', 'qa')
ID, SRC, BADGE = 'red_sports_original_v2', 'red_sports_fictional', 'red_sports'
PAINT_IDS = (ID, ID + '_red', ID + '_white')
BRAND_WORDS = (b'ferrari', b'prancing', b'cavallino', b'scuderia', b'maranello', b'scudetto', b'superfast')
MODEL_WORDS = (b'812',)             # too short for binary data: checked in the GLB JSON chunk and the json files only
BODY_MAX, WHEEL_MAX = 20000, 2500


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def strings(o):
    """Every key and string value in a JSON tree (numbers are skipped: '0.812' is not a model name)."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)
    elif isinstance(o, str):
        yield o


def load_glb(path):
    js, b = cd.glb_read(path)
    return js, b, cd.mesh_arrays(js, b), cd.image_of(js, b)


@unittest.skipIf(cd is None, 'numpy / Pillow not available')
class OriginalV2Car(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lay = json.load(open(os.path.join(CARS, f'{ID}_wheels.json')))
        cls.build = json.load(open(os.path.join(CARS, f'{ID}_build.json')))
        cls.bodies = {i: load_glb(os.path.join(CARS, f'{i}.glb')) for i in PAINT_IDS}
        cls.wheels = {k: load_glb(os.path.join(CARS, cls.lay['wheel_meshes'][k])) for k in cd.WHEELS}
        cls.slay, cls.sbody, cls.swheels = cd.load_car(CARS, SRC)

    def test_files_exist(self):
        need = [f'{ID}_wheels.json', f'{ID}_build.json', f'{ID}_emblem.png', f'{ID}_fbx.json'] + \
               [f'{i}.{e}' for i in PAINT_IDS for e in ('glb', 'fbx')] + \
               [f'{ID}_wheel_{k}.{e}' for k in cd.WHEELS for e in ('glb', 'fbx')]
        for f in need:
            self.assertTrue(os.path.isfile(os.path.join(CARS, f)), f)
        for f in ('overall_before_after', 'closeups_front', 'closeups_rear', 'closeups_wheel', 'paints'):
            self.assertTrue(os.path.isfile(os.path.join(QA, f'{ID}_{f}.png')), f)

    def test_triangle_budgets(self):
        for i, (_, _, mesh, _) in self.bodies.items():
            self.assertLessEqual(len(mesh[3]), BODY_MAX, i)
            self.assertGreater(len(mesh[3]), len(self.sbody['mesh'][3]), f'{i}: no new parts?')
        for k, (_, _, mesh, _) in self.wheels.items():
            self.assertLessEqual(len(mesh[3]), WHEEL_MAX, k)
        fbx = json.load(open(os.path.join(CARS, f'{ID}_fbx.json')))
        for f, r in fbx.items():
            self.assertLessEqual(r['tris'], BODY_MAX if '_wheel_' not in f else WHEEL_MAX, f)

    def test_body_bbox_unchanged(self):
        """Roblox centres a MeshPart on its bounding box: same box = the wheel layout still fits."""
        p0 = self.sbody['mesh'][0]
        for i, (_, _, mesh, _) in self.bodies.items():
            p = mesh[0]
            self.assertLess(float(np.abs(p.min(0) - p0.min(0)).max()), 0.001, i)
            self.assertLess(float(np.abs(p.max(0) - p0.max(0)).max()), 0.001, i)

    def test_layout_same_as_red_sports(self):
        self.assertEqual(self.lay['wheels'], self.slay['wheels'])
        self.assertEqual(self.lay['radius'], self.slay['radius'])
        self.assertEqual(self.lay['front'], '-Z')

    def test_wheels_pivot_round_and_spin_true(self):
        r_game = self.lay['radius']
        for k, (_, _, mesh, _) in self.wheels.items():
            pos = mesh[0]
            lo, hi = pos.min(0), pos.max(0)
            c = (lo + hi) / 2
            self.assertLess(float(np.abs(c).max()), 0.001, f'{k} bbox centre off the axle (wobble)')
            self.assertLess(hi[0] - lo[0], min(hi[1] - lo[1], hi[2] - lo[2]), f'{k} axle is not X')
            rho = np.hypot(pos[:, 1], pos[:, 2])
            self.assertLess(abs(float(rho.max()) - r_game), 0.001, f'{k} radius != layout radius')
            ang = np.degrees(np.arctan2(pos[:, 2], pos[:, 1])) % 360
            sector_max = [rho[(ang >= a) & (ang < a + 10)].max() for a in range(0, 360, 10)]
            self.assertLess(max(sector_max) - min(sector_max), 0.003, f'{k} tread not round about X')
            # outer face (hub cap) on the outside of the car: -X for left wheels, +X for right
            cap = (rho < 0.07) & (np.abs(pos[:, 0]) > 0.1)
            side = -1 if k[1] == 'L' else 1
            self.assertGreater(float(np.mean(pos[cap, 0])) * side, 0.1, f'{k} hub cap on the wrong side')

    def test_wheels_are_new_geometry(self):
        for k in cd.WHEELS:
            self.assertNotEqual(len(self.wheels[k][2][0]), len(self.swheels[k]['mesh'][0]), k)

    def test_shape_edits_stay_in_their_regions(self):
        p0 = self.sbody['mesh'][0]
        p = self.bodies[ID][2][0][:len(p0)]                # the old vertices come first, same order
        d = np.linalg.norm(p - p0, axis=1)
        moved = d > 0.002
        self.assertGreater(int(moved.sum()), 1000)
        self.assertLess(int(moved.sum()), 0.25 * len(p0))
        mid = (p0[:, 2] > -0.15) & (p0[:, 2] < 1.75)       # doors, cabin, rear wheels: untouched
        self.assertEqual(int((moved & mid).sum()), 0, 'vertices moved outside the edited regions')
        self.assertTrue(np.array_equal(self.bodies[ID][2][3][:len(self.sbody['mesh'][3])], self.sbody['mesh'][3]),
                        'old topology changed')
        for name, box in (('tail pods L', (-0.95, -0.5, 0.05, 0.21, 1.8)), ('tail pods R', (0.5, 0.95, 0.05, 0.21, 1.8))):
            x0, x1, y0, y1, z0 = box
            m = (p0[:, 0] > x0) & (p0[:, 0] < x1) & (p0[:, 1] > y0) & (p0[:, 1] < y1) & (p0[:, 2] > z0)
            self.assertGreater(int((m & moved).sum()), 100, name)
        for side in (-1, 1):
            m = (p0[:, 0] * side > 0.8) & (p0[:, 2] > -0.95) & (p0[:, 2] < -0.25) & (p0[:, 1] > -0.42)
            self.assertGreater(int((m & moved).sum()), 50, f'side scallop {side}')
        names = {g['name']: g for g in self.build['geometry']}
        for n in ('side_scallop_L', 'side_scallop_R', 'headlight_recess_L', 'headlight_recess_R', 'tail_pods_L',
                  'tail_pods_R', 'exhaust_housing_L', 'exhaust_housing_R', 'fog_lamp'):
            self.assertGreater(names[n]['verts_moved'], 20, n)
        self.assertEqual(self.build['bbox_shift_m'], [0.0, 0.0, 0.0])

    def test_new_parts_present(self):
        pieces = {p['name'] for p in self.build['parts']['pieces']}
        for n in ('headlight_L', 'headlight_R', 'drl_L', 'drl_R', 'gill0_L', 'gill2_R', 'tail_blade', 'outlet_0',
                  'outlet_1', 'grille_blade', 'emblem_nose', 'emblem_tail'):
            self.assertIn(n, pieces)

    def test_emblem_is_sharp_in_its_own_decal(self):
        x0, y0, x1, y1 = v2.DECALS['emblem']
        self.assertGreaterEqual(x1 - x0, 200, 'emblem decal narrower than 200 px')
        for i, (_, _, mesh, img) in self.bodies.items():
            a = np.asarray(img, float)[y0:y1, x0:x1]
            navy = np.linalg.norm(a - cd.NAVY, axis=2) < 30
            silver = np.linalg.norm(a - cd.SILVER, axis=2) < 30
            self.assertGreater(navy.mean(), 0.25, f'{i}: emblem navy field missing')
            self.assertGreater(silver.mean(), 0.08, f'{i}: emblem glyph / rim missing')
            uv = mesh[2] * 1024                               # the emblem shells map into this decal
            inside = (uv[:, 0] >= x0) & (uv[:, 0] <= x1) & (uv[:, 1] >= y0) & (uv[:, 1] <= y1)
            self.assertGreater(int(inside.sum()), 100, i)
        w = np.asarray(self.wheels['FL'][3], float)
        cx0, cy0, cx1, cy1 = v2.WT['cap']
        self.assertGreaterEqual(cx1 - cx0, 256)
        self.assertGreater((np.linalg.norm(w[cy0:cy1, cx0:cx1] - cd.NAVY, axis=2) < 30).mean(), 0.3)

    def test_paints(self):
        def red_share(img):
            a = np.asarray(img, float)[:v2.DECAL_Y] / 255
            h, s, v = cd.hsv(a)
            return float((((h < 15) | (h > 340)) & (s > 0.55) & (v > 0.3)).mean())
        self.assertLess(red_share(self.bodies[ID][3]), 0.02, 'default paint should not be red')
        self.assertLess(red_share(self.bodies[ID + '_white'][3]), 0.02)
        self.assertGreater(red_share(self.bodies[ID + '_red'][3]), 0.15, 'red variant lost its paint')
        self.assertEqual(self.lay['original_v2']['paints']['default']['paint'], 'midnight blue')

    def test_no_brand_words_in_files(self):
        for f in os.listdir(CARS):
            if f.startswith(ID) and f.endswith(('.glb', '.fbx', '_wheels.json')):
                data = open(os.path.join(CARS, f), 'rb').read().lower()
                for w in BRAND_WORDS:
                    self.assertFalse(w in data, f'{f} contains {w!r}')
                if f.endswith('.fbx'):
                    continue
                js = cd.glb_read(os.path.join(CARS, f))[0] if f.endswith('.glb') else json.loads(data)
                text = ' '.join(strings(js)).lower().encode()        # names / keys / text, not numbers
                for w in MODEL_WORDS:
                    self.assertFalse(w in text, f'{f} (json strings) contains {w!r}')

    def test_upload_marked_blocked(self):
        self.assertIn('BLOCKED', self.lay['original_v2']['upload'])
        self.assertIn('BLOCKED', self.build['upload'])
        doc = open(os.path.join(_qa.DOCS, 'CAR_IMPORT_RED_SPORTS.md'), encoding='utf-8').read()
        self.assertIn('## Original design v2', doc)
        self.assertIn('### Tripo rights evidence', doc)

    def test_distinct_from_originals_and_inputs_untouched(self):
        for f, h in self.build['inputs'].items():
            self.assertEqual(sha(os.path.join(CARS, f)), h, f'{f} changed since the v2 build (inputs must stay)')
        orig = {sha(os.path.join(CARS, f)) for f in os.listdir(CARS)
                if f.startswith(('red_sports.', 'red_sports_wheel_', 'red_sports_fictional'))}
        for f in os.listdir(CARS):
            if f.startswith(ID):
                self.assertNotIn(sha(os.path.join(CARS, f)), orig, f'{f} is a copy of an original file')


if __name__ == '__main__':
    unittest.main()
