"""Fictional-brand red sports car (docs/CAR_IMPORT_RED_SPORTS.md, "Fictional-brand version").

Offline checks of art/cars3d/roblox/red_sports_fictional*: the separated-wheel rig is unchanged from red_sports
(same wheel geometry, pivots at the axle, wheels round about X), triangle budgets, no yellow badge texels left,
the MP emblem is on the wheel caps, no brand words in the files, and upload stays marked as blocked.
Needs numpy + Pillow (the repo .venv has both); skipped otherwise.
"""
import json
import math
import os
import sys
import unittest

import _qa

try:
    import numpy as np
    from PIL import Image  # noqa: F401
    sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'gpu'))
    import car_debrand as cd
except ImportError as e:            # pragma: no cover
    cd = None
    _why = str(e)

CARS = os.path.join(_qa.ROOT, 'art', 'cars3d', 'roblox')
SRC_ID, ID = 'red_sports', 'red_sports_fictional'
BRAND_WORDS = (b'ferrari', b'prancing', b'cavallino', b'scuderia', b'maranello', b'scudetto')


@unittest.skipIf(cd is None, 'numpy / Pillow not available')
class FictionalCar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lay, cls.body, cls.wheels = cd.load_car(CARS, ID)
        cls.slay, cls.sbody, cls.swheels = cd.load_car(CARS, SRC_ID)

    def test_files_exist(self):
        for f in [f'{ID}.glb', f'{ID}_wheels.json', f'{ID}.fbx'] + \
                 [f'{ID}_wheel_{k}.{e}' for k in cd.WHEELS for e in ('glb', 'fbx')]:
            self.assertTrue(os.path.isfile(os.path.join(CARS, f)), f)

    def test_triangle_budget(self):
        body_tris = len(self.body['mesh'][3])
        self.assertLessEqual(body_tris, 20000)
        self.assertEqual(body_tris, len(self.sbody['mesh'][3]))
        for k in cd.WHEELS:
            self.assertLessEqual(len(self.wheels[k]['mesh'][3]), 2000, k)

    def test_wheel_geometry_and_layout_unchanged(self):
        for k in cd.WHEELS:
            a, b = self.wheels[k]['mesh'], self.swheels[k]['mesh']
            for x, y in zip(a, b):
                self.assertTrue(np.array_equal(x, y), k)
        self.assertEqual(self.lay['wheels'], self.slay['wheels'])
        self.assertEqual(self.lay['radius'], self.slay['radius'])

    def test_body_only_moved_at_reliefs(self):
        p, q = self.body['mesh'][0], self.sbody['mesh'][0]
        moved = np.linalg.norm(p - q, axis=1) > 1e-6
        self.assertTrue(moved.any())
        self.assertLess(float(np.abs(p - q).max()), 0.04)
        ok = np.zeros(len(p), bool)
        for rf in cd.RELIEFS:
            c = np.asarray(rf['centre'])
            ok |= np.hypot(q[:, 0] - c[0], q[:, 1] - c[1]) < rf['radius'] + 1e-6
        self.assertFalse((moved & ~ok).any(), 'vertices moved outside the badge reliefs')
        self.assertTrue(np.array_equal(self.body['mesh'][2], self.sbody['mesh'][2]), 'UVs changed')
        self.assertTrue(np.array_equal(self.body['mesh'][3], self.sbody['mesh'][3]), 'topology changed')

    def test_wheels_pivot_on_axle_and_spin_true(self):
        r_game = self.lay['radius']
        for k in cd.WHEELS:
            pos = self.wheels[k]['mesh'][0]
            lo, hi = pos.min(0), pos.max(0)
            c = (lo + hi) / 2
            self.assertLess(math.hypot(c[1], c[2]), 0.01, f'{k} bbox centre off the axle (wobble)')
            self.assertLess(hi[0] - lo[0], min(hi[1] - lo[1], hi[2] - lo[2]), f'{k} axle is not X')
            rho = np.hypot(pos[:, 1], pos[:, 2])
            ang = np.degrees(np.arctan2(pos[:, 2], pos[:, 1])) % 360
            sector_max = [rho[(ang >= a) & (ang < a + 10)].max() for a in range(0, 360, 10)]
            self.assertLess(max(sector_max) - min(sector_max), 0.03, f'{k} tread not round about X')
            self.assertLess(abs(np.median(sector_max) - r_game), 0.02, k)

    def test_no_yellow_badges_left(self):
        img = np.asarray(self.body['img']) / 255.0
        P, N, M = cd.raster(*self.body['mesh'], self.body['img'].size)
        big = [c for c in cd.clusters(P, M & cd.is_yellow(img)) if c['n_texels'] >= 4]
        self.assertEqual(big, [], 'yellow (shield-coloured) texel clusters remain on the body')
        for k in cd.WHEELS:
            w = self.wheels[k]
            wi = np.asarray(w['img']) / 255.0
            P2, N2, M2 = cd.raster(*w['mesh'], w['img'].size)
            rho = np.hypot(P2[..., 1], P2[..., 2])
            self.assertEqual(int((M2 & cd.is_yellow(wi) & (rho < 0.12)).sum()), 0, k)
            side = -1 if k[1] == 'L' else 1
            cap = M2 & (rho < 0.05) & (P2[..., 0] * side > 0.07)
            navy = np.linalg.norm(np.asarray(w['img'], float)[cap] - cd.NAVY, axis=1) < 40
            self.assertGreater(navy.mean(), 0.3, f'{k}: MP emblem field missing on the centre cap')

    def test_no_brand_words_in_files(self):
        for f in os.listdir(CARS):
            if f.startswith(ID) and f.endswith(('.glb', '.fbx', '_wheels.json')):    # the files that would ship
                data = open(os.path.join(CARS, f), 'rb').read().lower()
                for w in BRAND_WORDS:
                    self.assertFalse(w in data, f'{f} contains {w!r}')

    def test_upload_marked_blocked(self):
        self.assertIn('BLOCKED', self.lay['fictional_brand']['upload'])
        doc = open(os.path.join(_qa.DOCS, 'CAR_IMPORT_RED_SPORTS.md'), encoding='utf-8').read()
        self.assertIn('## Fictional-brand version', doc)


if __name__ == '__main__':
    unittest.main()
