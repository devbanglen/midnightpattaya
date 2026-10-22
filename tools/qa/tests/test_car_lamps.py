"""Car lamps in the game (docs/CAR_IMPORT_RED_SPORTS.md, "Lamps"; team23/car-lamps).

Static checks of the wiring in ServerScriptService/RaceCarServer.server.luau (LampMesh_* never taken as the body, lamp
clones massless / non-colliding / non-query / non-touch and welded like the wheel meshes, anchors on the Body and never
on the chassis, whose Attachments the parked-car spring uses as wheel mounts) and in
StarterPlayerScripts/PattayaNightLights.client.luau (lamp path only with all four anchors, the generic lights kept
verbatim for every other car, the meshes given back by day, the seat only read). Plus a numeric check of the placement
math with the real red_sports_own_v3 numbers: a lamp MeshPart placed with RaceCarServer's CFrame lands every vertex
exactly where the same point of the body mesh lands (Roblox's glTF import bakes a 180 degree yaw and centres each
MeshPart on its own box), and the anchors land on the lamps, about 1.4 studs lower than the old generic head flares.
Needs numpy for the numeric part (skipped otherwise)."""
import json
import math
import os
import re
import sys
import unittest

import _qa

try:
    import numpy as np
    sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'gpu'))
    import car_debrand as cd
except ImportError:                 # pragma: no cover
    np = cd = None

SERVER = os.path.join(_qa.SRC, 'ServerScriptService', 'RaceCarServer.server.luau')
CLIENT = os.path.join(_qa.SRC, 'StarterPlayer', 'StarterPlayerScripts', 'PattayaNightLights.client.luau')
CARS = os.path.join(_qa.ROOT, 'art', 'cars3d', 'roblox')
ID = 'red_sports_own_v3'
BODY_LENGTH, SUSPENSION_REST, SAG = 16, 1.6, 0.45      # RaceCarServer constants (checked below)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def func(src, name):
    """Source of a top-level `local function name(...)` up to the next top-level function / end of its block."""
    m = re.search(r'^local function ' + re.escape(name) + r'\b.*?^end$', src, re.S | re.M)
    if not m:
        raise AssertionError(f'local function {name} not found')
    return m.group(0)


class ServerWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(SERVER)

    def test_constants_unchanged(self):
        self.assertIn(f'local BODY_LENGTH = {BODY_LENGTH} ', self.src)
        self.assertIn(f'local SUSPENSION_REST, SAG = {SUSPENSION_REST}, {SAG}', self.src)

    def test_lamp_meshes_are_never_the_body(self):
        f = func(self.src, 'bodyMeshOf')
        self.assertIn('not isWheelMesh(d) and not isLampMesh(d)', f)
        self.assertIn('return string.sub(inst.Name, 1, 9) == "LampMesh_"', func(self.src, 'isLampMesh'))
        body = func(self.src, 'attachBody')
        self.assertIn('if isWheelMesh(d) or isLampMesh(d) then d:Destroy() end', body)

    def test_lamp_clones_like_the_wheel_meshes(self):
        f = func(self.src, 'attachLamps')
        for line in ('m.Anchored = false', 'm.CanCollide = false', 'm.CanQuery = false', 'm.CanTouch = false',
                     'm.Massless = true', 'm.CastShadow = false', 'weld(chassis, m)', 'm.Size = d.Size * s',
                     'm.Parent = model'):
            self.assertIn(line, f)
        # the placement the numeric test below verifies
        self.assertIn('local bodyFrame = chassis.CFrame * CFrame.new(0, offsetY, 0)', f)
        self.assertIn('m.CFrame = bodyFrame * CFrame.new(off * s) * yaw', f)
        self.assertIn('src:GetAttribute("LampYawFix") or src:GetAttribute("YawFix") or 0', f)
        self.assertIn('typeof(off) == "Vector3"', f)
        self.assertIn('attachLamps(model, chassis, body, src, s, offsetY)', func(self.src, 'attachBody'))

    def test_anchors_on_the_body_never_on_the_chassis(self):
        """The parked-car Heartbeat treats EVERY Attachment child of the chassis as a wheel mount (spring + ray):
        lamp anchors must go on the Body MeshPart, or parked cars would get four extra springs."""
        self.assertRegex(self.src, r'for _, mount in ipairs\(chassis:GetChildren\(\)\) do\s+if mount:IsA\("Attachment"\)')
        f = func(self.src, 'attachLamps')
        self.assertIn('a.Parent = body', f)
        self.assertIn('a.Name = "LampAnchor_" .. name', f)
        self.assertNotRegex(f, r'Parent\s*=\s*chassis')
        self.assertIn('local at = bodyFrame * (p * s)', f)
        self.assertIn('a.CFrame = body.CFrame:ToObjectSpace(CFrame.lookAt(at, at + bodyFrame:VectorToWorldSpace(dir)))',
                      f)
        self.assertIn('local LAMP_ANCHORS = {"HeadL", "HeadR", "TailL", "TailR"}', self.src)
        # the only Attachments made on the chassis are still the four wheel mounts
        self.assertEqual(len(re.findall(r'Instance\.new\("Attachment"\)', self.src)), 2)

    def test_no_driving_code_touched(self):
        """The lamp code only reads attributes and makes visual parts; nothing in the car's physics setup refers to
        lamps (chassis size / mass / mounts / welds / network owner as before)."""
        for k in ('chassis.Size = Vector3.new(7, 1.6, 15)', 'PhysicalProperties.new(0.7, 0, 0, 100, 1)',
                  'att.Name = "Mount_" .. name', 'w.Name = "WheelWeld"', 'chassis:SetNetworkOwner(nil)'):
            self.assertIn(k, self.src)
        build = func(self.src, 'buildCar')
        self.assertNotIn('Lamp', build)


class ClientWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = read(CLIENT)

    def test_generic_lights_kept_for_cars_without_lamps(self):
        f = func(self.src, 'addLights')
        i = f.index('local anchors = lampAnchors(chassis)')
        j = f.index('-- front is -Z (LookVector); the beam is tilted 8 degrees down')
        self.assertLess(i, j)
        self.assertIn('addLampLights(chassis, mine, anchors, att, HEAD_COLOR)', f[i:j])
        self.assertIn('return', f[i:j])
        generic = f[j:]
        for line in ('local head = att("PattayaHeadBeam", CFrame.new(0, 0.6, -half - 0.3) * CFrame.Angles(math.rad(-8), 0, 0))',
                     'flare(att("PattayaHeadFlare", CFrame.new(s * w, 0.9, -half - 0.1)), HEAD_COLOR, 1.3)',
                     'flare(att("PattayaTailFlare", CFrame.new(s * w, 1.1, half + 0.1)), TAIL_COLOR, 1.0)',
                     'local tail = att("PattayaTailGlow", CFrame.new(0, 0.8, half + 0.4))',
                     'lit[chassis] = made'):
            self.assertIn(line, generic)
        self.assertIn('f.BackgroundTransparency = 0.15', func(self.src, 'flare'))

    def test_lamp_path_needs_all_four_anchors(self):
        f = func(self.src, 'lampAnchors')
        self.assertIn('for _, n in {"HeadL", "HeadR", "TailL", "TailR"} do', f)
        self.assertIn('body:FindFirstChild("LampAnchor_" .. n)', f)
        self.assertRegex(f, r'if not \(a and a:IsA\("Attachment"\)\) then\s+return nil')

    def test_lamp_lights(self):
        f = func(self.src, 'addLampLights')
        for k in ('m.Material = Enum.Material.Neon', 'table.insert(rig.meshes, {part = m, material = m.Material, '
                  'color = m.Color})', 'string.sub(m.Name, 1, 9) == "LampMesh_"', 'beam.Angle = 65',
                  'CFrame.Angles(math.rad(-8), 0, 0)', 'glow.Brightness = 0.5', 'rigs[chassis] = rig'):
            self.assertIn(k, f)
        # soft layered glare, no hard 1.3-stud disc: three layers, the outer ones mostly transparent
        m = re.search(r'local GLARE_LAYERS = (\{\{.*?\}\})', self.src)
        layers = [tuple(float(x) for x in t.split(',')) for t in re.findall(r'\{([^{}]*)\}', m.group(1))]
        self.assertEqual(len(layers), 3)
        self.assertGreaterEqual(layers[0][1], 0.85, 'halo must be faint')
        sizes = re.search(r'local HEAD_GLARE, TAIL_GLARE = Vector2.new\(([\d.]+), ([\d.]+)\), '
                          r'Vector2.new\(([\d.]+), ([\d.]+)\)', self.src)
        self.assertTrue(sizes and max(float(v) for v in sizes.groups()) <= 1.2, 'glare sprites must stay small')
        rm = func(self.src, 'removeLights')
        self.assertIn('e.part.Material = e.material', rm)
        self.assertIn('e.part.Color = e.color', rm)

    def test_glare_fade_and_brake_light_read_only(self):
        self.assertIn('local f = if d > 1e-3 then wc.LookVector:Dot(to / d) else 1', self.src)
        self.assertIn('seat.ThrottleFloat < -0.1', self.src)
        self.assertNotRegex(self.src, r'ThrottleFloat\s*=[^=]', 'the client must never write the seat')
        self.assertIn('if q ~= g.last then', self.src)


@unittest.skipIf(np is None, 'numpy not available')
class PlacementMath(unittest.TestCase):
    """Roblox CFrame algebra in numpy: CFrame = (R, p), (R1, p1) * (R2, p2) = (R1 R2, R1 p2 + p1)."""

    @staticmethod
    def ry(deg):
        a = math.radians(deg)
        return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])

    @staticmethod
    def mul(a, b):
        return a[0] @ b[0], a[0] @ b[1] + a[1]

    def setUp(self):
        with open(os.path.join(CARS, f'{ID}_lamps.json'), encoding='utf-8') as f:
            self.lj = json.load(f)
        with open(os.path.join(CARS, f'{ID}_wheels.json'), encoding='utf-8') as f:
            self.lay = json.load(f)
        js, b = cd.glb_read(os.path.join(CARS, f'{ID}.glb'))
        P = cd.mesh_arrays(js, b)[0]
        self.s = BODY_LENGTH / float(P[:, 2].max() - P[:, 2].min())
        rest_ext = SUSPENSION_REST * (1 - SAG)
        self.offY = -rest_ext - sum(self.lay['wheels'][k][1] * self.s for k in ('FL', 'FR', 'RL', 'RR')) / 4
        rng = np.random.default_rng(7)
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        w, x, y, z = q
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        self.chassis = (R, np.array([1234.5, 6.7, -890.1]))

    def test_lamp_mesh_lands_where_the_body_point_lands(self):
        yaw = 180.0                                       # YawFix of CarBodies.red_sports_own_v3
        I = np.eye(3)
        body_frame = self.mul(self.chassis, (I, np.array([0, self.offY, 0])))
        body_cf = self.mul(body_frame, (self.ry(yaw), np.zeros(3)))
        for kind, rec in self.lj['meshes'].items():
            js, b = cd.glb_read(os.path.join(CARS, rec['file']))
            V = cd.mesh_arrays(js, b)[0]                   # centred on its own box
            o = np.array(rec['offset'])
            g = V + o                                     # the same points in body space
            imported = (self.ry(180) @ V.T).T * self.s    # Roblox import: 180 deg yaw baked, MeshPart.Size scaled
            lamp_cf = self.mul(self.mul(body_frame, (I, o * self.s)), (self.ry(yaw), np.zeros(3)))
            got = (lamp_cf[0] @ imported.T).T + lamp_cf[1]
            body_model = (body_cf[0] @ ((self.ry(180) @ g.T).T * self.s).T).T + body_cf[1]
            self.assertLess(float(np.abs(got - body_model).max()), 1e-9, kind)

    def test_anchors_in_chassis_space(self):
        """bodyFrame * (p * s) in chassis space = (0, offsetY, 0) + p * s: the head anchors sit about 1.4 studs lower
        than the old generic head flares (0.9 up) and in front of the nose, the tail ones behind the tail."""
        a = self.lj['anchors']
        head = np.array([0, self.offY, 0]) + np.array(a['HeadR']['pos']) * self.s
        tail = np.array([0, self.offY, 0]) + np.array(a['TailR']['pos']) * self.s
        self.assertAlmostEqual(self.offY, 0.277, delta=0.01)
        self.assertGreater(0.9 - head[1], 1.2, head)
        self.assertLess(head[2], -7.6)
        self.assertGreater(tail[2], 7.6)
        self.assertLess(abs(head[0]), 2.7, 'on the real lamp, not at the old generic x')
        self.assertGreater(tail[0], 2.9)


if __name__ == '__main__':
    unittest.main()
