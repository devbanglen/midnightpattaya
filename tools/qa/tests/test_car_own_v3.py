"""Own body v3 of the test car (docs/CAR_IMPORT_RED_SPORTS.md, "Own body v3").

Offline checks of art/cars3d/roblox/red_sports_own_v3*: the files and the QA sheets exist; triangle budgets (FBX = GLB);
one material and one 1024^2 texture per body; the wheel layout is red_sports' and the v2 wheels are used as they are;
the bounding box is centred, has red_sports' length and stays within 5 % of red_sports; the tyres clear the body at
rest and over the full steering range; closed shells; our own generator, and the GLBs are the output of the committed
script; no mesh or image data shared with the Tripo / Meshy / older bodies; the MP emblem is the v2 decal; no brand
words; upload marked BLOCKED and nothing in the game; the default and white paints have no red; the side and top
silhouettes differ from the fictional body; and every original red_sports* file is byte-identical to main 8df1a8c.
Needs numpy + Pillow (the repo .venv has both); skipped otherwise.
"""
import hashlib
import io
import json
import os
import re
import sys
import unittest

import _qa

try:
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'gpu'))
    sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'blender'))
    import car_debrand as cd
    import car_own_v3 as v3          # numpy only outside Blender (bpy = None): constants, decal rectangles
    import car_own_v3_qa as q
except ImportError as e:            # pragma: no cover
    cd = v3 = q = None
    _why = str(e)

ART = os.path.join(_qa.ROOT, 'art', 'cars3d')
CARS = os.path.join(ART, 'roblox')
QA = os.path.join(ART, 'qa')
ID, V2, REF, BADGE, MESHY = 'red_sports_own_v3', 'red_sports_original_v2', 'red_sports_fictional', 'red_sports', \
    'red_sports_meshy'
PAINT_IDS = (ID, ID + '_red', ID + '_white')
QA_SHEETS = ('compare', 'closeups', 'paints', 'silhouette', 'clearance', 'looks')
BRAND_WORDS = (b'ferrari', b'prancing', b'cavallino', b'scuderia', b'maranello', b'scudetto', b'superfast')
AI_WORDS = (b'tripo', b'meshy')     # the generator must be ours: no AI service named in our files
MODEL_WORDS = (b'812',)             # too short for binary data: checked in the GLB JSON chunk and the json files only
BODY_MAX = 20000
WHEELS = ('FL', 'FR', 'RL', 'RR')

# sha256 of every red_sports* file under art/cars3d on main 8df1a8c (the originals this team must not touch)
ORIGINALS = {
    'qa/red_sports_fictional_badges_before_after.png': '8adfc20130fe386552929fe9822bbc383e39d86d042255b0543954841f8cae04',
    'qa/red_sports_fictional_overall_before_after.png': '91fee3efdfe7b28718b2ee384175f6dac7045b82c69fe86d76deb80e8ee953ef',
    'qa/red_sports_fictional_turntable.png': '02c0c127a34c5225b97bad2d2143a9a35b01955446fa803e6671cef58dc1e6dd',
    'qa/red_sports_original_v2_closeups_front.png': 'f6582e5a3af15135e79193975b81a5e9517210c3b5f7546960819f8ef3e89bfd',
    'qa/red_sports_original_v2_closeups_rear.png': '575a8747dc21548a76e0a45726f9cfca5f35cff66737578dc2fcac6dacc091fe',
    'qa/red_sports_original_v2_closeups_wheel.png': 'f156e866c14bb9163c96242cca150245e138113fb130fb6a620c6698b512d89a',
    'qa/red_sports_original_v2_overall_before_after.png': '6a897f71e5e1efb94d230c875551215f5e97197e507a5acdfcb1ecf01aa7ccfd',
    'qa/red_sports_original_v2_paints.png': 'f2d4d1893465e16bd32b9a529f749c1f831f6fc1f7698d80dd5b36b334b63735',
    'roblox/qa/red_sports_after.png': 'c3cbc3f80c087fe6d1cd10df226bd4183cf972fb4413bd58bb2c64bfb4b8cc48',
    'roblox/qa/red_sports_before.png': 'cb210e58b4aa64c9cc72ede6ba33a92dfa947b50235ec98a1234363e2baa1f00',
    'roblox/qa/red_sports_body_only.png': '858218a92d97476c71c4748359c4aeb6aaccc4b38f34a847222ec856e0fa1d8f',
    'roblox/qa/red_sports_meshy_after.png': '7294f03fecc28a6866765235917dd047dfd5072f996fd79a2f4aec91a3a26966',
    'roblox/qa/red_sports_meshy_before.png': '69d170128ac319910e293b907859862d6edc533616df3e7cea841592be3079a3',
    'roblox/qa/red_sports_meshy_body_only.png': 'ad88648b93f2fa9795fea5214bb33170c5294fcce3e7fdbe8f883e6340eba82e',
    'roblox/qa/red_sports_meshy_qa.json': 'bbd0caee0067b14ed4464bf8bb4e433f8c3e15cea5b479b2c3aa0905cbe2e357',
    'roblox/qa/red_sports_meshy_source_splat_side.png': 'c6fc6bd1a1e84600ed3681c8cad7240b2817ad6e9c9ec9a00414ee6aa5437088',
    'roblox/qa/red_sports_meshy_sweeps.png': '412e40dcb252d74d93c4fbfba9f7e789ed27e4776e8231e314589269c431310f',
    'roblox/qa/red_sports_meshy_wheels.png': '752c966a976dbd5797f160abf22772def7f79af5771665e7e2cb75629bf30981',
    'roblox/qa/red_sports_qa.json': '76b284379847c17adfcf3c105a3eabe82067e2e5380de7b83fc11ef1240efed6',
    'roblox/qa/red_sports_source_splat_side.png': 'c255a37f3ba9e0f19d92dff85ce498fcc5ffcf075997d4836b18bc61d1a2b63f',
    'roblox/qa/red_sports_sweeps.png': 'b9d843c22025d523b9ec1dd5e70f7c43c5710dc4460f6aa2a8b822a0c2329834',
    'roblox/qa/red_sports_wheels.png': 'fbebb6a34193a841cae35864bbeec7abf45fd18c6aa49cd774515b87921320cf',
    'roblox/red_sports.glb': 'cfc75701c12a6f6a1d3cee8949f3c9720366f5c4bd870937ad17c7c771943513',
    'roblox/red_sports_build.json': '10a4cd50d913615c1d0d551fe43eaddc2aebef98ff5e59db2d54bd66d5745649',
    'roblox/red_sports_detect.json': 'c0b0f06a7f68dcd7776ff13a299e4f02746128c6ef3a2df4fd3e41efcf95c2e3',
    'roblox/red_sports_fictional.fbx': 'c1f9e5fea962eeb0f78e4fb322df83410d4fcb255d23429a2a235f077ac8878e',
    'roblox/red_sports_fictional.glb': 'bdc0fb287e53f994daaed1027529599e13ae66bde1f01f8a125e47776958c883',
    'roblox/red_sports_fictional_debrand.json': '4821b6a4825b3f7f9a62d1420c6b8c29fa5bb8dea0b4f2347a11de49c3cab347',
    'roblox/red_sports_fictional_emblem.png': '2a87d218fa199c3470f7a9df7686f9d330a2aa4d36e8618ceb92be62f73792d1',
    'roblox/red_sports_fictional_fbx.json': 'ba00db97eae252c508c3068bd36caf8fed38b684df5e35c1e51cbfc0b13969c6',
    'roblox/red_sports_fictional_wheel_FL.fbx': '66b26335ef468d92c00f201b8ec98955d1adbfb5f88d2a643b1c11a92c515dc1',
    'roblox/red_sports_fictional_wheel_FL.glb': '23e6467f38773fa6f4de0b7951e2fb5262f9c1dde1ebf94d753434ba50e3f526',
    'roblox/red_sports_fictional_wheel_FR.fbx': '86e8744ed4c4fcb59af502ed5f6cf08592564a0cab9f609faf8d3b677a970935',
    'roblox/red_sports_fictional_wheel_FR.glb': '06b2c81bb8340cf311dc99224d197061a04a42fec841b0ebb5ee7d33e4862fe4',
    'roblox/red_sports_fictional_wheel_RL.fbx': 'e6edf7dad5e0a9e1053f9d38ca7102739dd7fc2d03be62da81d57bd58203dc79',
    'roblox/red_sports_fictional_wheel_RL.glb': '11f6582e3b928a02b3b9882ea486b46d3f8b7b57461830da2d94534ddaf4c06f',
    'roblox/red_sports_fictional_wheel_RR.fbx': '89326c0194f545d72d24975cc702fabe05f5c0ab3fa6b8b4e62b00f461f83c4d',
    'roblox/red_sports_fictional_wheel_RR.glb': 'fdf801ece6ef1e299675f46d01620ffd6d334744b8520e3ddd7dc546984c1fd4',
    'roblox/red_sports_fictional_wheels.json': '09704323aa1093196c23233325da9d2f4ec8e5461100eb0363a8d87a5372a958',
    'roblox/red_sports_meshy.glb': '31cb1af7e9cee8975ad4693f3f7faff58d9e91cc0c0ed21b8c8feeed7db9ca93',
    'roblox/red_sports_meshy_build.json': '473dd2439cede8328cc7486049971da05f0d9ad97e38883950edea900d6238f1',
    'roblox/red_sports_meshy_detect.json': '099762f0ba364ce6ad50f4a78a4da51562a2f65554707730bedb760fea41b71b',
    'roblox/red_sports_meshy_wheel_FL.glb': '91dec26d1ed916c3dfcb27264331d41779fb9085049fedf20b25efe40f4c6dd7',
    'roblox/red_sports_meshy_wheel_FR.glb': '50373446dca3af78aa35cfe54acd28e0a810b3693dc1897f734f820af23c74af',
    'roblox/red_sports_meshy_wheel_RL.glb': '221d2e50feccc3e594ae32192dbc3a61eaf14186735aa2140b3169692f547ace',
    'roblox/red_sports_meshy_wheel_RR.glb': '4569c699003e1f3aaf4afdd6984c02b8b3442b0bff6eaec4dbbd3954f4692044',
    'roblox/red_sports_meshy_wheels.json': 'd8934f56244d37293aa27009640da8316f057f94b7027ce77041685f42548441',
    'roblox/red_sports_original_v2.fbx': '1a953046f79dd8060a5a63470a8d31a4fa1c754bfd40187c73a16ec96b47481d',
    'roblox/red_sports_original_v2.glb': '800f12e2e54c86a238a017033d39cbb71ec537816c4ff51ebe2dd3427611ebad',
    'roblox/red_sports_original_v2_build.json': '9685624f2f1ab4a3737b2884e7227112316e9b5b91d3c8ed6208a60e66577428',
    'roblox/red_sports_original_v2_emblem.png': 'e00b4497357e7edb5d2775ce47b1f4b4694d0b81ddb12dd4095f8b3fd884f197',
    'roblox/red_sports_original_v2_fbx.json': '04b85651ea73808e95ae968a955a087b7c80df3df6b09abde674f9f7e190634e',
    'roblox/red_sports_original_v2_red.fbx': '2f65dff023b42d36229a555c775943af60b2bab29376b25bd7f062e24f2b8c96',
    'roblox/red_sports_original_v2_red.glb': 'd0061186535c87d04a03957d9e5edc529779d63b750e0f92fbc589ea8ef51e1f',
    'roblox/red_sports_original_v2_wheel_FL.fbx': '6146fac826653ee1edff4b02e1d20095ad474bc2caf4c0d6b5ee32d9671d08f7',
    'roblox/red_sports_original_v2_wheel_FL.glb': '430f58dec592f42be1bb4650da3b13ccba3af8eb5d251bde04830bfa0d7d3b56',
    'roblox/red_sports_original_v2_wheel_FR.fbx': '15a160de8febdef70d245ba170e27ae115f2463b97c99031779c2332d35149e4',
    'roblox/red_sports_original_v2_wheel_FR.glb': '388076b30116fd8833ee1be2458d25db9b7fd610fe1d773acc60d85a5b4454b7',
    'roblox/red_sports_original_v2_wheel_RL.fbx': '49c75b697c9f020473eec736d2aeaf055be6e3328935522db11cc332c7f39322',
    'roblox/red_sports_original_v2_wheel_RL.glb': '2aed4bc5d044b16e5ae609a5066c79005e3c74abae98bb0a94046700762079a6',
    'roblox/red_sports_original_v2_wheel_RR.fbx': 'ce8dfb7aa7d5bfaab47ba94b94e9cecf04188ed0086dee30d98b5c678846e0a6',
    'roblox/red_sports_original_v2_wheel_RR.glb': 'faf5ed9bac9cdb776560e5a7b7918a77d80c279f37ca18c9b98805e7867e0c44',
    'roblox/red_sports_original_v2_wheels.json': 'de6b9dcc4f8d7940b010234693ce4f37fa99921db51944c79c258f3bcdddd465',
    'roblox/red_sports_original_v2_white.fbx': '06f88749c8f8bfa890d0ad314d1990490510ca4e0984bd820ff270de8e831d73',
    'roblox/red_sports_original_v2_white.glb': 'd087d1070e56e2878d9c7aa862015d7eae60edcb370ad5c601a90c7ab1d81342',
    'roblox/red_sports_wheel_FL.glb': 'cbbe2e2d6868433d14a20354e8da8bc2f970f03538a673821d7d5976a81ef6de',
    'roblox/red_sports_wheel_FR.glb': 'f2188b50cb0e9f695a083d9d5459c2b700b02e118735eddf7a50a34a0f8dc981',
    'roblox/red_sports_wheel_RL.glb': '6b8b729de8531e9ca225ed590311fa0aa8475e454d86e863a5f421f4880415e6',
    'roblox/red_sports_wheel_RR.glb': 'a8b70a8106e4eadcf8cfd98ebbc8be1631c7914cbd2a91b133da72c80dc1ba03',
    'roblox/red_sports_wheels.json': 'b97acfc0a4e308d47448d9bd8ab1e9063bc8168fd618827c331db4348cc5a888',
}


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def jload(path):
    return json.loads(read(path))


def sha(path):
    return hashlib.sha256(read(path)).hexdigest()


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
    P, N, UV, T = cd.mesh_arrays(js, b)
    imgs = [cd._view(js, b, im['bufferView']) for im in js.get('images', [])]
    return {'js': js, 'P': P, 'N': N, 'UV': UV, 'T': T, 'png': imgs}


def tiles(a, n=16, min_colours=9):
    """Byte strings of the n x n tiles (aligned grid) of an RGB array with at least min_colours colours. Tiles of a
    few flat colours (patches, edges, stripes on the black gutter) can match by construction (v2 and v3 share the
    paint colours and the stepped-gill stripes); a copied piece of texture cannot."""
    h, w = a.shape[0] // n * n, a.shape[1] // n * n
    t = np.ascontiguousarray(a[:h, :w].reshape(h // n, n, w // n, n, 3).swapaxes(1, 2)).reshape(-1, n * n, 3)
    t32 = t.astype(np.int32)
    packed = np.sort((t32[..., 0] << 16) | (t32[..., 1] << 8) | t32[..., 2], axis=1)
    colours = (np.diff(packed, axis=1) != 0).sum(1) + 1
    return {t[i].tobytes() for i in np.nonzero(colours >= min_colours)[0]}


@unittest.skipIf(cd is None, 'numpy / Pillow not available')
class OwnBodyV3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lay = jload(os.path.join(CARS, f'{ID}_wheels.json'))
        cls.build = jload(os.path.join(CARS, f'{ID}_build.json'))
        cls.qa = jload(os.path.join(CARS, f'{ID}_qa.json'))
        cls.bodies = {i: load_glb(os.path.join(CARS, f'{i}.glb')) for i in PAINT_IDS}
        cls.imgs = {i: Image.open(io.BytesIO(b['png'][0])).convert('RGB') for i, b in cls.bodies.items()}

    def test_files_exist(self):
        need = [f'{ID}_wheels.json', f'{ID}_build.json', f'{ID}_emblem.png', f'{ID}_fbx.json', f'{ID}_qa.json'] + \
               [f'{i}.{e}' for i in PAINT_IDS for e in ('glb', 'fbx')] + list(self.lay['wheel_meshes'].values())
        for f in need:
            self.assertTrue(os.path.isfile(os.path.join(CARS, f)), f)
        for f in QA_SHEETS:
            self.assertTrue(os.path.isfile(os.path.join(QA, f'{ID}_{f}.png')), f)
        for f in ('tools/blender/car_own_v3.py', 'tools/blender/run_own_v3.sh', 'tools/blender/own_v3_views.json',
                  'tools/gpu/car_own_v3_qa.py'):
            self.assertTrue(os.path.isfile(os.path.join(_qa.ROOT, f)), f)

    def test_triangle_budgets(self):
        fbx = jload(os.path.join(CARS, f'{ID}_fbx.json'))
        self.assertEqual(sorted(fbx), sorted(f'{i}.fbx' for i in PAINT_IDS))
        for i, b in self.bodies.items():
            n = len(b['T'])
            self.assertLessEqual(n, BODY_MAX, i)
            self.assertGreaterEqual(n, 8000, f'{i}: fewer triangles than the 8k target floor')
            self.assertEqual(n, self.build['tris']['total'], i)
            self.assertEqual(fbx[f'{i}.fbx']['tris'], n, f'{i}: the FBX lost or gained triangles')
        self.assertEqual(self.build['tris']['body_shell'] + self.build['tris']['parts'], self.build['tris']['total'])

    def test_one_material_one_texture_opaque(self):
        for i, b in self.bodies.items():
            js = b['js']
            self.assertEqual(len(js['meshes']), 1, i)
            self.assertEqual(len(js['meshes'][0]['primitives']), 1, i)
            self.assertEqual(len(js['materials']), 1, i)
            self.assertEqual(len(js['textures']), 1, i)
            self.assertEqual(len(b['png']), 1, i)
            self.assertEqual(self.imgs[i].size, (1024, 1024), i)
            m = js['materials'][0]
            self.assertEqual(m.get('alphaMode', 'OPAQUE'), 'OPAQUE', f'{i}: glass must be opaque')
            self.assertFalse(m.get('doubleSided', False), f'{i}: nothing may depend on back faces')
        p0 = self.bodies[ID]
        for i in PAINT_IDS[1:]:                     # the paints share one geometry and one UV layout
            for k in ('P', 'N', 'UV', 'T'):
                self.assertTrue(np.array_equal(self.bodies[i][k], p0[k]), f'{i} {k}')

    def test_layout_same_as_red_sports(self):
        slay = jload(os.path.join(CARS, f'{BADGE}_wheels.json'))
        v2lay = jload(os.path.join(CARS, f'{V2}_wheels.json'))
        self.assertEqual(self.lay['wheels'], slay['wheels'])
        self.assertEqual(self.lay['radius'], slay['radius'])
        self.assertEqual(self.lay['front'], '-Z')
        self.assertEqual(self.lay['wheel_meshes'], v2lay['wheel_meshes'], 'the v2 wheels, used as they are')
        for k in ('width', 'rim', 'per_wheel'):
            self.assertEqual(self.lay[k], v2lay[k], k)
        for k, c in v3.LAYOUT.items():               # the script builds the tubs on the same numbers
            self.assertEqual(list(c), slay['wheels'][k], k)
        self.assertEqual(v3.WHEEL_R, slay['radius'])

    def test_studio_snippet_takes_the_shared_v2_wheels(self):
        """car_import_wheels.py --luau: v3 lists the v2 wheel files, so its snippet also accepts the v2 wheel part
        names; the v2 snippet itself is unchanged."""
        import car_import_wheels as ciw
        own = ciw.luau_snippet(os.path.join(CARS, f'{ID}_wheels.json'), ID)
        self.assertIn(f'(d.Name == "{ID}" or string.match(d.Name, "^{ID}_wheel_%u+$") or '
                      f'string.match(d.Name, "^{V2}_wheel_%u+$")) then', own)
        for k in WHEELS:
            self.assertIn(f'f:SetAttribute("Wheel{k}", Vector3.new(', own)
        v2s = ciw.luau_snippet(os.path.join(CARS, f'{V2}_wheels.json'), V2)
        self.assertNotIn('shared wheels', v2s)
        self.assertIn(f'(d.Name == "{V2}" or string.match(d.Name, "^{V2}_wheel_%u+$")) then', v2s)

    def test_bbox_centred_same_length_within_5_percent(self):
        P0 = load_glb(os.path.join(CARS, f'{BADGE}.glb'))['P']
        s0 = P0.max(0) - P0.min(0)
        for i, b in self.bodies.items():
            lo, hi = b['P'].min(0), b['P'].max(0)
            self.assertLess(float(np.abs((lo + hi) / 2).max()), 1e-4, f'{i}: not centred on its bounding box')
            s = hi - lo
            for ax in range(3):
                self.assertLess(abs(s[ax] / s0[ax] - 1), 0.05, f'{i}: axis {ax} {s[ax]:.4f} vs {s0[ax]:.4f}')
            self.assertLess(abs(s[2] - s0[2]), 1e-4, f'{i}: length differs (the game scales by the length)')
            self.assertLess(float(np.abs(np.array(self.lay['size']) - s).max()), 1e-4, f'{i}: wheels.json size')
            self.assertLess(float(np.abs(np.array(self.build['bbox']['size']) - s).max()), 1e-4, i)

    def test_tyre_clearance(self):
        """Closed cylinder round the v2 tyre (r 0.3848, width 0.344) vs the body: at rest, over +-28 deg of steering
        at the front, and the free bump travel. Recomputed here and compared with the stored QA numbers."""
        w = load_glb(os.path.join(CARS, self.lay['wheel_meshes']['FL']))['P']
        self.assertLessEqual(float(np.hypot(w[:, 1], w[:, 2]).max()), self.lay['radius'] + 1e-4)
        self.assertLessEqual(float(np.abs(w[:, 0]).max()), q.TYRE_W / 2 + 1e-4, 'wheel wider than the envelope')
        cl = q.clearance_qa(CARS, ID)
        st = self.qa['clearance']
        self.assertEqual(st['measured_glb_sha256'], sha(os.path.join(CARS, f'{ID}.glb')), 'stale clearance QA')
        for k in WHEELS:
            self.assertEqual(cl[k]['rest_points_inside'], 0, k)
            self.assertGreater(cl[k]['rest_min_clearance_m'], 0.03, k)
            self.assertGreater(cl[k]['free_bump_travel_m'], 0.03, k)
            if k[0] == 'F':
                self.assertGreater(cl[k]['steer_min_clearance_m'], 0.015, f'{k} at steering lock')
            for f, v in cl[k].items():
                if isinstance(v, float):
                    self.assertAlmostEqual(v, st[k][f], delta=1e-3, msg=f'{k} {f}')

    def test_closed_shells(self):
        b = self.bodies[ID]
        r = q.shell_check(b['P'], b['T'])
        self.assertEqual(r['open_edge_uses'], 0, 'open edges')
        self.assertEqual(r['duplicate_directed_edges'], 0, 'inconsistent winding or non-manifold edges')
        self.assertEqual(r['components_with_negative_volume'], 0, 'a shell wound inside out')
        st = self.qa['shells']
        self.assertEqual(st['measured_glb_sha256'], sha(os.path.join(CARS, f'{ID}.glb')), 'stale shell QA')
        self.assertEqual(st['components'], r['components'])

    def test_generator_ours_and_build_matches_script(self):
        for i, b in self.bodies.items():
            self.assertEqual(b['js']['asset'].get('generator'), v3.GENERATOR, i)
        self.assertEqual(self.build['generator'], v3.GENERATOR)
        self.assertEqual(self.build['script_sha256'], sha(os.path.join(_qa.ROOT, 'tools', 'blender', 'car_own_v3.py')),
                         'tools/blender/car_own_v3.py changed after the build: rebuild the outputs')
        for name, rec in self.build['paints'].items():
            self.assertEqual(sha(os.path.join(CARS, rec['file'])), rec['sha256'],
                             f'{name}: the GLB is not the build output')

    def test_no_foreign_mesh_or_image_data(self):
        """No vertex and no texture tile of ours comes from the Tripo / Meshy / fictional / v2 files."""
        own_keys = {tuple(k) for k in np.round(self.bodies[ID]['P'] / 1e-5).astype(np.int64)}
        own_png = {bytes(p) for b in self.bodies.values() for p in b['png']}
        x0, y0, x1, y1 = v3.DECALS['emblem']        # the MP emblem is the v2 decal on purpose (own design)
        own_tiles = set()
        for img in self.imgs.values():
            a = np.array(img)
            a[y0:y1, x0:x1] = 0
            own_tiles |= tiles(a)
        foreign = [f for f in sorted(os.listdir(CARS)) if f.endswith('.glb') and
                   f.startswith((f'{BADGE}.', f'{BADGE}_wheel_', MESHY, REF, V2))]
        self.assertGreaterEqual(len(foreign), 20)
        for f in foreign:
            b = load_glb(os.path.join(CARS, f))
            keys = {tuple(k) for k in np.round(b['P'] / 1e-5).astype(np.int64)}
            self.assertLess(len(own_keys & keys), 0.001 * len(own_keys), f'{f}: shared vertex positions')
            for p in b['png']:
                self.assertNotIn(bytes(p), own_png, f'{f}: same image bytes')
                a = np.asarray(Image.open(io.BytesIO(p)).convert('RGB'))
                self.assertEqual(len(own_tiles & tiles(a)), 0, f'{f}: shared texture tiles')

    def test_emblem_is_the_v2_decal(self):
        own = np.asarray(Image.open(os.path.join(CARS, f'{ID}_emblem.png')).convert('RGB'), float)
        ref = np.asarray(Image.open(os.path.join(CARS, f'{V2}_emblem.png')).convert('RGB'), float)
        ref = ref[154:154 + own.shape[0], 10:10 + own.shape[1]]  # v2 sheet: body decal x2 at (10, 154)
        self.assertEqual(own.shape, (224, 448, 3))
        self.assertLess(float(np.abs(own - ref).mean()), 2.0, 'emblem differs from the v2 MP decal')
        x0, y0, x1, y1 = v3.DECALS['emblem']
        a = np.asarray(self.imgs[ID], float)[y0:y1, x0:x1]
        self.assertTrue(np.array_equal(np.repeat(np.repeat(a, 2, 0), 2, 1), own), 'emblem png is not the shipped decal')
        for i, b in self.bodies.items():
            a = np.asarray(self.imgs[i], float)[y0:y1, x0:x1]
            self.assertGreater((np.linalg.norm(a - v3.NAVY, axis=2) < 30).mean(), 0.25, f'{i}: emblem navy field')
            self.assertGreater((np.linalg.norm(a - v3.SILVER, axis=2) < 30).mean(), 0.08, f'{i}: emblem glyph / rim')
            uv = b['UV'] * 1024
            inside = (uv[:, 0] >= x0) & (uv[:, 0] <= x1) & (uv[:, 1] >= y0) & (uv[:, 1] <= y1)
            self.assertGreater(int(inside.sum()), 100, f'{i}: no emblem shells map into the decal')

    def test_paints(self):
        def red_share(img):
            a = np.asarray(img, float)[:v3.DECAL_Y] / 255
            h, s, v = cd.hsv(a)
            return float((((h < 15) | (h > 340)) & (s > 0.55) & (v > 0.3)).mean())
        self.assertLess(red_share(self.imgs[ID]), 0.002, 'default paint has red in it')
        self.assertLess(red_share(self.imgs[ID + '_white']), 0.002, 'white paint has red in it')
        self.assertGreater(red_share(self.imgs[ID + '_red']), 0.15, 'red variant lost its paint')
        paints = self.lay['own_v3']['paints']
        self.assertEqual(paints['default']['paint'], 'midnight blue')
        self.assertEqual({k: v['body'] for k, v in paints.items()},
                         {'default': f'{ID}.glb', '_red': f'{ID}_red.glb', '_white': f'{ID}_white.glb'})

    def test_no_brand_words_in_files(self):
        own = [f for f in os.listdir(CARS) if f.startswith(ID) and f.endswith(('.glb', '.fbx', '.json'))]
        self.assertGreaterEqual(len(own), 10)
        for f in own:
            data = read(os.path.join(CARS, f)).lower()
            for w in BRAND_WORDS + AI_WORDS:
                self.assertFalse(w in data, f'{f} contains {w!r}')
            if f.endswith('.fbx'):
                continue
            js = cd.glb_read(os.path.join(CARS, f))[0] if f.endswith('.glb') else json.loads(data)
            # names / keys / text; not numbers and not sha256 digests ('...812...' in a hash is no model name)
            text = ' '.join(s for s in strings(js) if not re.fullmatch('[0-9a-f]{64}', s)).lower().encode()
            for w in MODEL_WORDS:
                self.assertFalse(w in text, f'{f} (json strings) contains {w!r}')

    def test_upload_blocked_and_not_in_game(self):
        self.assertIn('BLOCKED until the owner approves', self.lay['own_v3']['upload'])
        self.assertIn('BLOCKED until the owner approves', self.build['upload'])
        for root, _, files in os.walk(_qa.SRC):
            for f in files:
                if f.endswith(('.luau', '.lua', '.json', '.txt')):
                    with open(os.path.join(root, f), encoding='utf-8', errors='replace') as fh:
                        self.assertNotIn('own_v3', fh.read(), f'{f}: v3 is not in the game yet')
        doc = read(os.path.join(_qa.DOCS, 'CAR_IMPORT_RED_SPORTS.md')).decode('utf-8')
        self.assertTrue('## Own body v3' in doc, 'docs: section "Own body v3" missing')
        self.assertTrue('upload BLOCKED until the owner approves' in doc, 'docs: upload BLOCKED note missing')

    def test_silhouette_differs_from_fictional(self):
        s = self.qa['silhouette']
        self.assertEqual(s['measured_glb_sha256'], sha(os.path.join(CARS, f'{ID}.glb')), 'stale silhouette QA')
        self.assertLess(s['side_iou_vs_fictional'], 0.90, 'side silhouette too close to the fictional body')
        self.assertLess(s['side_iou_vs_fictional'], s['side_iou_v2_vs_fictional'] - 0.10)
        # the fictional side view has see-through window holes: also with every hole filled
        self.assertLess(s['side_iou_vs_fictional_holes_filled'], 0.92)
        self.assertLess(s['side_iou_vs_fictional_holes_filled'], s['side_iou_v2_vs_fictional_holes_filled'] - 0.08)
        self.assertLess(s['top_iou_vs_fictional'], s['top_iou_v2_vs_fictional'])
        peak = s['roofline']['roof_peak_z']
        self.assertLess(peak[ID], peak['fictional'] - 0.3, 'cabin not forward of the fictional cabin')
        self.assertGreater(s['roofline']['share_of_length_diff_over_5cm'], 0.4)

    def test_originals_untouched(self):
        self.assertEqual(len(ORIGINALS), 70)
        for rel, h in ORIGINALS.items():
            self.assertEqual(sha(os.path.join(ART, rel)), h, f'{rel} changed (originals must stay as on main)')
        orig = set(ORIGINALS.values())
        for f in os.listdir(CARS):
            if f.startswith(ID):
                self.assertNotIn(sha(os.path.join(CARS, f)), orig, f'{f} is a copy of an original file')


if __name__ == '__main__':
    unittest.main()
