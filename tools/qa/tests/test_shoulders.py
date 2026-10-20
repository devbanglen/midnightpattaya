"""Road shoulders / tapers / hole fills along Sukhumvit (tools/mapgen/road_shoulders.py, docs/ROAD_SHOULDERS.md).

Offline only. Needs the generated build/shoulders (run the generator first) and the road data it reads (build/
pattaya_wide etc.); skipped when build/ is missing. Uses numpy / shapely (the repo .venv), like the generator.
  - the exported modules on disk equal a fresh in-process build (determinism + the build is up to date)
  - flush tops, chunk part caps, batch sizes, manifest counts
  - no exported piece on a building box / prop / sidewalk / corner fill / apron, none deep under a road surface
  - terrain fill boxes clear of roads, sidewalks, buildings
  - drive check: car footprints along the built Sukhumvit polylines at lateral offsets 0, +-8, +-14, +-20, +-24
    every 2 studs, supported (top within 0.3 of the road top) before vs after; the leader's two flip spots
  - the real PattayaShoulderBuilder.luau run in the luau CLI with stub Roblox types on every data module: part
    counts, tops, footprints = the generator's pieces; Remove / BuildTerrain / RemoveTerrain bookkeeping
"""
import json
import math
import os
import re
import sys
import unittest

import _qa

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'mapgen'))
CFG_PATH = os.path.join(_qa.CONFIG, 'shoulders.json')
_CACHE = {}

# offline flip spots measured by the leader in Studio (world x, z, lane offset); docs/QUALITY_AUDIT_2026-10-20.md
FLIP_SPOTS = [((25250.0, 13430.0), 24), ((24560.0, 900.0), 14)]


def world_state():
    """(cfg, W, R, rendered files) of one in-process generator run (cached)"""
    if 'W' in _CACHE:
        return _CACHE['W']
    _qa.need_build('shoulders', 'roblox', 'manifest.luau')
    _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
    try:
        import numpy  # noqa: F401
        import shapely  # noqa: F401
        import road_shoulders as rsh
    except ImportError as e:  # pragma: no cover
        raise unittest.SkipTest(f'needs numpy / shapely (repo .venv): {e}')
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    cfg = json.load(open(CFG_PATH, encoding='utf-8'))
    W = rsh.load(cfg, _qa.BUILD)
    W['broot'] = _qa.BUILD
    R = rsh.build(cfg, W)
    out = rsh.render(cfg, R)
    _CACHE['W'] = (cfg, W, R, out, rsh)
    return _CACHE['W']


def rows(text, key):
    m = re.search(r'\n  ' + key + r' = \{([^}]*)\}', text)
    return [float(v) for v in m.group(1).split(',') if v.strip()] if m else []


def exported():
    """{chunk id: dict(boxes, tris, terrain, parts)} parsed from build/shoulders/roblox"""
    if 'exp' in _CACHE:
        return _CACHE['exp']
    d = _qa.need_build('shoulders', 'roblox')
    out = {}
    for f in sorted(os.listdir(d)):
        if f.startswith('chunk_s') and f.endswith('.luau'):
            t = _qa.read(os.path.join(d, f))
            out[f[6:-5]] = dict(boxes=rows(t, 'boxes'), tris=rows(t, 'tris'), terrain=rows(t, 'terrain'),
                                parts=int(re.search(r'\n  parts = (\d+)', t).group(1)), text=t)
    _CACHE['exp'] = out
    return out


def manifest():
    return _qa.luau_table(_qa.need_build('shoulders', 'roblox', 'manifest.luau'))


class ShoulderData(unittest.TestCase):
    def test_modules_on_disk_equal_a_fresh_build(self):
        """determinism across processes: the generator's output for the current road data is byte-identical to the
        modules on disk (fails when build/ is stale: rerun tools/mapgen/road_shoulders.py)"""
        cfg, W, R, out, rsh = world_state()
        d = _qa.need_build('shoulders')
        disk = {}
        for k in out['files']:
            p = os.path.join(d, k)
            self.assertTrue(os.path.exists(p), f'{k} missing on disk')
            disk[k] = _qa.read(p)
        on_disk = sorted(f for f in os.listdir(os.path.join(d, 'roblox')) if f.startswith('chunk_s') or f == 'manifest.luau')
        self.assertEqual(sorted(os.path.basename(k) for k in out['files']), on_disk)
        self.assertEqual(rsh.digest(disk), rsh.digest(out['files']))
        rep = _qa.load_json(os.path.join(d, 'shoulders.json'))
        self.assertTrue(rep['deterministic'], 'the generator reported two different runs')
        self.assertEqual(rep['checks'], {}, 'generator checks must all be 0')

    def test_flush_tops(self):
        cfg = json.load(open(CFG_PATH, encoding='utf-8'))
        man = manifest()
        self.assertAlmostEqual(man['shoulder']['top'], cfg['shoulder']['top'])
        top = man['shoulder']['top']
        self.assertLessEqual(abs(top - man['roadTop']), 0.02, 'shoulder top flush with the road top (1.0)')
        self.assertLess(top, man['roadTop'], 'under the slab top: no z-fighting where a piece tucks under the edge')
        self.assertLess(top, 0.99, 'under the junction / joint discs (0.99)')
        self.assertGreater(top, 0.98, 'above the aprons (0.98)')
        self.assertGreaterEqual(man['shoulder']['thick'], 3.0, 'reaches below the terrain (-2)')
        self.assertLessEqual(man['terrain']['top'], -2.0 + 1e-9, 'terrain fill: at most half the -4 .. 0 voxel layer')

    def test_chunk_caps_and_counts(self):
        man = manifest()
        cap = man['maxPartsPerChunk']
        self.assertEqual(cap, 600)
        ex = exported()
        self.assertEqual(sorted(ex), sorted(man['chunks']))
        total = 0
        for cid, d in ex.items():
            self.assertLessEqual(d['parts'], cap, f'chunk {cid}')
            self.assertEqual(len(d['boxes']) % 7, 0)
            self.assertEqual(len(d['tris']) % 7, 0)
            self.assertEqual(len(d['terrain']) % 6, 0)
            total += d['parts']
            self.assertLess(len(d['text'].encode('utf-8')), 200 * 1024, 'WORLD_CHUNKS.md 200 KB module limit')
        self.assertEqual(total, man['counts']['parts'])
        seen = []
        for b, ids in man['batches'].items():
            self.assertLessEqual(len(ids), 8, f'batch {b}')
            seen += ids
        self.assertEqual(sorted(seen), sorted(man['chunks']))
        self.assertEqual(sorted(man['batches']), sorted(man['batchOrder']))

    def _pieces(self):
        cfg, W, R, out, rsh = world_state()
        P = []
        for cid, d in exported().items():
            b, t = d['boxes'], d['tris']
            for i in range(0, len(b), 7):
                P.append((rsh.piece_poly('box', b[i:i + 6]), int(b[i + 6])))
            for i in range(0, len(t), 7):
                P.append((rsh.piece_poly('tri', t[i:i + 6]), int(t[i + 6])))
        return P

    def test_no_overlap_with_buildings_sidewalks_props_aprons(self):
        """independent re-check of the EXPORTED rows (not the generator's own list) against the world"""
        cfg, W, R, out, rsh = world_state()
        bad = {}
        tol = cfg['clean']['road_overlap_studs'] + 0.05
        for p, kind in self._pieces():
            for key in ('blds', 'props', 'walks', 'aprons', 'corners'):
                for q in rsh.near(W, key, p):
                    if p.intersects(q) and p.intersection(q).area > 0.01:
                        bad.setdefault(key, []).append([round(p.centroid.x + 20000, 1), round(p.centroid.y, 1)])
                        break
            for q in rsh.near(W, 'roads', p) + rsh.discs_near(W, p):
                core = q.buffer(-tol, join_style=2)
                if p.intersects(q) and not core.is_empty and p.intersection(core).area > 0.05:
                    bad.setdefault('deep under a road surface', []).append([round(p.centroid.x + 20000, 1), round(p.centroid.y, 1)])
                    break
        self.assertEqual({k: (len(v), v[:3]) for k, v in bad.items()}, {})

    def test_pieces_stay_beside_the_targets(self):
        """every piece lies within width/2 + shoulder (+ taper / bridge envelope) of a target edge: the pilot touches
        Sukhumvit and its trunk_link pieces only"""
        cfg, W, R, out, rsh = world_state()
        env = R['envelope'].buffer(0.1)
        far = [p for p, _ in self._pieces() if p.difference(env).area > 0.01]
        self.assertEqual(len(far), 0)
        tg = rsh.unary_union([rsh.LineString(e['pts']) for e in W['targets']])
        reach = max(e['width'] for e in W['targets']) / 2 + cfg['shoulder']['width'] + cfg['taper']['bridge_studs']
        self.assertTrue(all(p.distance(tg) < reach for p, _ in self._pieces()))

    def test_terrain_boxes_clear(self):
        cfg, W, R, out, rsh = world_state()
        hits = 0
        n = 0
        for cid, d in exported().items():
            t = d['terrain']
            for i in range(0, len(t), 6):
                n += 1
                b = rsh.piece_poly('box', t[i:i + 6])
                for key in ('roads', 'walks', 'blds', 'aprons', 'corners'):
                    if any(b.intersects(q) and b.intersection(q).area > 0.01 for q in rsh.near(W, key, b)):
                        hits += 1
                        break
                else:
                    if any(b.intersects(q) and b.intersection(q).area > 0.01 for q in rsh.discs_near(W, b)):
                        hits += 1
        self.assertGreater(n, 0)
        self.assertEqual(hits, 0)


class DriveCheck(unittest.TestCase):
    """support under a car along the built Sukhumvit polylines, before / after the patch"""

    @classmethod
    def setUpClass(cls):
        cfg, W, R, out, rsh = world_state()
        polys = [rsh.piece_poly(pk, v) for _, pk, v, _ in R['pieces']]
        cls.res = {}
        for fp in ('spec', 'car'):
            cls.res[fp] = (rsh.drive(cfg, W, footprint=fp), rsh.drive(cfg, W, polys, footprint=fp))
        cls.cfg = cfg
        lines = []
        for fp in ('spec', 'car'):
            b, a = cls.res[fp]
            for o in cfg['drive']['offsets']:
                lines.append(f'{fp:4} offset {o:+3}: samples {b[o]["samples"]:5d} unsupported {b[o]["unsupported"]:5d} -> '
                             f'{a[o]["unsupported"]:5d}; centre on the slab {b[o]["in_lane"]["samples"]:5d}: '
                             f'{b[o]["in_lane"]["unsupported"]:5d} -> {a[o]["in_lane"]["unsupported"]:5d}')
        cls.table = '\n'.join(lines)

    def test_parameters(self):
        D = self.cfg['drive']
        self.assertEqual(sorted(D['offsets']), [-24, -20, -14, -8, 0, 8, 14, 20, 24])
        self.assertEqual((D['step'], D['car_width'], D['car_length'], D['height_tol']), (2.0, 4.0, 9.0, 0.3))

    def test_never_worse(self):
        for fp, (b, a) in self.res.items():
            for o in b:
                self.assertLessEqual(a[o]['unsupported'], b[o]['unsupported'], f'{fp} offset {o}\n{self.table}')
                self.assertEqual(a[o]['samples'], b[o]['samples'])

    def test_lanes_supported_after(self):
        """car centre on the slab (|offset| <= width/2): every sample supported at offsets 0 .. +-20 (both
        footprints), and at +-24 at most 0.5 % of samples left (spots where a building or prop stands right at the
        slab edge, listed in shoulders.json)"""
        for fp, (b, a) in self.res.items():
            for o in a:
                r = a[o]['in_lane']
                if abs(o) <= 20:
                    self.assertEqual(r['unsupported'], 0, f'{fp} offset {o}\n{self.table}')
                else:
                    self.assertLessEqual(r['unsupported'], 0.005 * r['samples'], f'{fp} offset {o}\n{self.table}')

    def test_patch_fixes_the_outer_lanes(self):
        """with the real wheel track (mounts at +-3.4) the outer lanes were unsupported over thousands of samples"""
        b, a = self.res['car']
        before = sum(b[o]['in_lane']['unsupported'] for o in (24, -24))
        after = sum(a[o]['in_lane']['unsupported'] for o in (24, -24))
        self.assertGreater(before, 5000, self.table)
        self.assertLess(after, 0.01 * before, self.table)

    def test_leader_flip_spots(self):
        """the two Studio flips: unsupported before (real wheel track), supported after"""
        for (wx, wz), lane in FLIP_SPOTS:
            x, z = wx - 20000.0, wz
            for fp in ('car',):
                b, a = self.res[fp]
                nb = sum(1 for o in (lane, -lane) for p in b[o]['bad_in'] if math.hypot(p[0] - x, p[1] - z) < 120)
                na = sum(1 for o in (lane, -lane) for p in a[o]['bad_in'] if math.hypot(p[0] - x, p[1] - z) < 120)
                self.assertGreater(nb, 0, f'{fp}: expected the flip spot ({wx}, {wz}) lane {lane} to be unsupported before')
                self.assertEqual(na, 0, f'{fp}: ({wx}, {wz}) lane {lane} still unsupported after')


# ---- the real builder in the luau CLI ---------------------------------------------------------------------------------
STUB = r'''
local V3 = {}
local function v3(x, y, z) return setmetatable({X = x or 0, Y = y or 0, Z = z or 0}, V3) end
V3.__index = function(t, k)
	if k == "Magnitude" then return math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z) end
	if k == "Unit" then local m = math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z) return v3(t.X / m, t.Y / m, t.Z / m) end
	return V3[k]
end
V3.__add = function(a, b) return v3(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
V3.__sub = function(a, b) return v3(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
V3.__mul = function(a, b) if type(a) == "number" then return v3(a * b.X, a * b.Y, a * b.Z) end return v3(a.X * b, a.Y * b, a.Z * b) end
V3.__div = function(a, b) return v3(a.X / b, a.Y / b, a.Z / b) end
function V3.Dot(a, b) return a.X * b.X + a.Y * b.Y + a.Z * b.Z end
function V3.Cross(a, b) return v3(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X) end
Vector3 = {new = v3}
local V2 = {}
local function v2(x, y) return setmetatable({X = x or 0, Y = y or 0}, V2) end
V2.__index = function(t, k)
	if k == "Magnitude" then return math.sqrt(t.X * t.X + t.Y * t.Y) end
	return V2[k]
end
V2.__add = function(a, b) return v2(a.X + b.X, a.Y + b.Y) end
V2.__sub = function(a, b) return v2(a.X - b.X, a.Y - b.Y) end
V2.__mul = function(a, b) if type(a) == "number" then return v2(a * b.X, a * b.Y) end return v2(a.X * b, a.Y * b) end
V2.__div = function(a, b) return v2(a.X / b, a.Y / b) end
function V2.Dot(a, b) return a.X * b.X + a.Y * b.Y end
Vector2 = {new = v2}
Vector3int16 = {new = function(x, y, z) return {X = x, Y = y, Z = z} end}
Region3int16 = {new = function(a, b) return {Min = a, Max = b} end}
local CF = {}
CF.__index = CF
local function cf(p, x, y, z) return setmetatable({Position = p, XVector = x, YVector = y, ZVector = z}, CF) end
CF.__mul = function(c, v) return c.Position + c.XVector * v.X + c.YVector * v.Y + c.ZVector * v.Z end
CF.__add = function(c, v) return cf(c.Position + v, c.XVector, c.YVector, c.ZVector) end
CFrame = {
	fromMatrix = function(p, x, y, z) return cf(p, x, y, z) end,
	lookAt = function(at, target)
		local look = (target - at).Unit
		local right = look:Cross(v3(0, 1, 0)).Unit
		local up = right:Cross(look)
		return cf(at, right, up, look * -1)
	end,
	new = function(x, y, z) return cf(v3(x, y, z), v3(1, 0, 0), v3(0, 1, 0), v3(0, 0, 1)) end,
}
Color3 = {fromRGB = function(r, g, b) return {r, g, b} end}
local function enum(names) local t = {} for _, n in names do t[n] = n end return t end
Enum = {Material = enum({"Concrete", "Asphalt", "Ground", "SmoothPlastic"}), SurfaceType = enum({"Smooth"}),
	ModelStreamingMode = enum({"Atomic"}), RaycastFilterType = enum({"Exclude", "Include"})}
WARN = {}
function warn(s) table.insert(WARN, s) end
task = {wait = function() end}
OverlapParams = {new = function() return {} end}
RaycastParams = {new = function() return {} end}
local I = {}
I.__index = function(t, k)
	local v = rawget(I, k)
	if v ~= nil then return v end
	if k == "Position" then local c = rawget(t, "CFrame") return c and c.Position end
	for _, c in rawget(t, "_kids") do if rawget(c, "Name") == k then return c end end
	return nil
end
local BASE = {Part = true, WedgePart = true}
function I.new(class)
	return setmetatable({ClassName = class, Name = class, _kids = {}, _attr = {}, _parent = nil}, I)
end
function I:__newindex(k, v)
	if k == "Parent" then
		if self._parent then
			local kids = self._parent._kids
			for i, c in kids do if c == self then table.remove(kids, i) break end end
		end
		rawset(self, "_parent", v)
		if v then table.insert(v._kids, self) end
	else
		rawset(self, k, v)
	end
end
function I:IsA(c) if c == "BasePart" then return BASE[self.ClassName] == true end return self.ClassName == c end
function I:GetChildren() local t = {} for _, c in self._kids do table.insert(t, c) end return t end
function I:GetDescendants()
	local out = {}
	local function walk(n) for _, c in n._kids do table.insert(out, c) walk(c) end end
	walk(self)
	return out
end
function I:FindFirstChild(n) for _, c in self._kids do if c.Name == n then return c end end return nil end
function I:WaitForChild(n) return self:FindFirstChild(n) or error("WaitForChild: no " .. n) end
function I:Destroy() self.Parent = nil end
function I:SetAttribute(k, v) self._attr[k] = v end
function I:GetAttribute(k) return self._attr[k] end
function I:IsDescendantOf(a) local p = self._parent while p do if p == a then return true end p = p._parent end return false end
function I:GetPivot() return CFrame.new(0, 0, 0) end
function I:PivotTo(c)
	for _, d in self:GetDescendants() do if d.CFrame then d.CFrame = d.CFrame + c.Position end end
end
function I:Clone()
	local o = I.new(self.ClassName) o.Name = self.Name rawset(o, "_load", self._load) return o
end
Instance = {new = I.new}
local function moduleScript(name, load) local m = I.new("ModuleScript") m.Name = name rawset(m, "_load", load) return m end
ServerStorage = I.new("ServerStorage")
game = {GetService = function() return ServerStorage end}
workspace = I.new("Workspace")
local W = I.new("Folder") W.Name = "PattayaWorld" W.Parent = workspace
TERRAIN = {copies = 0, fills = 0, pastes = {}, cells = {}}
local terrain = I.new("Terrain")
function terrain:CopyRegion(r) TERRAIN.copies += 1 local t = I.new("TerrainRegion") rawset(t, "_r", r) return t end
function terrain:FillBlock(c, size, mat) TERRAIN.fills += 1 TERRAIN.last = {c, size, mat} end
function terrain:PasteRegion(t, corner, empty) table.insert(TERRAIN.pastes, t:GetAttribute("Seq")) end
rawset(workspace, "Terrain", terrain)
function workspace:GetPartsInPart() return {} end
function workspace:Raycast() return nil end
'''

TAIL = r'''
local Sh = BUILDER
local function fmt(v) return string.format("%.3f", v) end
print("BUILD", Sh.Build())
print("BUILD2", Sh.Build())
for _, w in WARN do print("WARN", w) end
local root = workspace.PattayaWorld.ShoulderChunks
for _, chunk in root:GetChildren() do
	local n = 0
	for _, p in chunk:GetDescendants() do
		if p:IsA("BasePart") then
			n += 1
			local c, s = p.CFrame, p.Size
			local pts
			if p.ClassName == "WedgePart" then
				pts = {c * Vector3.new(0, -s.Y / 2, -s.Z / 2), c * Vector3.new(0, -s.Y / 2, s.Z / 2), c * Vector3.new(0, s.Y / 2, s.Z / 2)}
			else
				pts = {c * Vector3.new(-s.X / 2, 0, -s.Z / 2), c * Vector3.new(s.X / 2, 0, -s.Z / 2), c * Vector3.new(s.X / 2, 0, s.Z / 2), c * Vector3.new(-s.X / 2, 0, s.Z / 2)}
			end
			local top = -math.huge
			for _, dx in {-1, 1} do for _, dy in {-1, 1} do for _, dz in {-1, 1} do
				top = math.max(top, (c * Vector3.new(dx * s.X / 2, dy * s.Y / 2, dz * s.Z / 2)).Y)
			end end end
			local xs = {}
			for _, q in pts do table.insert(xs, fmt(q.X)) table.insert(xs, fmt(q.Z)) end
			print("P", chunk.Name, p:GetAttribute("ShoulderKind"), fmt(top), p.Name, tostring(p.CanCollide), tostring(p:GetAttribute("RoadFill")), table.concat(xs, " "))
		end
	end
	print("C", chunk.Name, n, chunk.ModelStreamingMode)
end
print("PROBE", Sh.Probe())
print("TERRAIN", Sh.BuildTerrain({batch = "s1"}))
print("TERRAIN2", Sh.BuildTerrain({batch = "s1"}))
print("TCOUNT", TERRAIN.copies, TERRAIN.fills)
print("REMOVE", Sh.Remove())
print("PASTES", table.concat(TERRAIN.pastes, ","))
print("AFTER", workspace.PattayaWorld:FindFirstChild("ShoulderChunks") == nil, ServerStorage:FindFirstChild("PattayaShoulderTerrainBackup") == nil)
'''


class LuauBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _qa.need_build('shoulders', 'roblox')
        src = _qa.src(os.path.join('ServerStorage', 'PattayaShoulderBuilder.luau'))
        parts = [STUB, 'local DATA = I.new("Folder") DATA.Name = "PattayaDataShoulders" DATA.Parent = ServerStorage\n']
        mods = ['manifest'] + [f[:-5] for f in sorted(os.listdir(d)) if f.startswith('chunk_s')]
        for m in mods:
            body = _qa.read(os.path.join(d, m + '.luau'))
            parts.append(f'moduleScript("{m}", function()\n{body}\nend).Parent = DATA\n')
        parts.append('local BUILDER = (function()\nlocal require = function(m) return m._load() end\n' + src + '\nend)()\n')
        parts.append(TAIL)
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=600)
        cls.lines = cls.out.splitlines()

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-2000:])
        self.assertFalse([l for l in self.lines if l.startswith('WARN')], 'Build warned (part count / cap)')

    def test_counts_match_data(self):
        man = manifest()
        n = sum(1 for l in self.lines if l.startswith('P\t') or l.startswith('P '))
        self.assertEqual(n, man['counts']['parts'])
        chunks = {l.split()[1][6:]: int(l.split()[2]) for l in self.lines if l.split() and l.split()[0] == 'C'}
        ex = exported()
        self.assertEqual(sorted(chunks), sorted(ex))
        for cid, n in chunks.items():
            self.assertEqual(n, ex[cid]['parts'], cid)
            self.assertLessEqual(n, 600)
        self.assertTrue(all(l.split()[3] == 'Atomic' for l in self.lines if l.split() and l.split()[0] == 'C'))
        b2 = [l for l in self.lines if l.startswith('BUILD2')][0]
        self.assertIn('0 chunks built now', b2, 'a second Build skips built chunks')

    def test_tops_flush_and_flags(self):
        man = manifest()
        top = man['shoulder']['top']
        bad = [l for l in self.lines if l.split() and l.split()[0] == 'P'
               and (abs(float(l.split()[3]) - top) > 0.005 or l.split()[4] != 'Shoulder' or l.split()[5] != 'true'
                    or l.split()[6] != 'true')]
        self.assertEqual(bad[:3], [])

    def test_footprints_equal_generator_pieces(self):
        """the union of the Luau parts' footprints (world - ORIGIN) per chunk = the generator's piece polygons"""
        cfg, W, R, out, rsh = world_state()
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        got = {}
        for l in self.lines:
            f = l.split()
            if f and f[0] == 'P' and len(f) >= 13:
                v = [float(x) for x in f[7:]]
                pts = [(v[i] - 20000.0, v[i + 1]) for i in range(0, len(v), 2)]
                got.setdefault(f[1][6:], []).append(Polygon(pts))
        for cid, d in exported().items():
            want = [rsh.piece_poly('box', d['boxes'][i:i + 6]) for i in range(0, len(d['boxes']), 7)]
            t = d['tris']        # the builder's two-wedge split (road_seams.wedge_tris ports roadTriangle, skips <= 0.05)
            want += [poly for i in range(0, len(t), 7) for poly, _ in rsh.rs.wedge_tris(t[i:i + 2], t[i + 2:i + 4], t[i + 4:i + 6])]
            a, b = unary_union(got.get(cid, [])), unary_union(want)
            # the Luau corners are printed to 0.001: allow 0.001 x the total outline length
            self.assertLess(a.symmetric_difference(b).area, 0.01 + 0.001 * sum(p.length for p in want), cid)
            self.assertAlmostEqual(a.area, b.area, delta=0.5 + 0.001 * b.area)

    def test_probe_and_rollback(self):
        probe = [l for l in self.lines if l.startswith('PROBE')][0]
        self.assertIn('not flush 0; above road top 0; obstacle hits 0', probe)
        tc = [l for l in self.lines if l.startswith('TCOUNT')][0].split()
        self.assertEqual(tc[1], tc[2], 'one terrain backup per filled box')
        self.assertIn('0 chunks, 0 boxes', [l for l in self.lines if l.startswith('TERRAIN2')][0], 'terrain chunks not filled twice')
        pastes = [int(x) for x in [l for l in self.lines if l.startswith('PASTES')][0].split()[1].split(',') if x]
        self.assertEqual(len(pastes), int(tc[1]))
        self.assertEqual(pastes, sorted(pastes, reverse=True), 'restored newest first')
        self.assertIn('AFTER\ttrue\ttrue', [l for l in self.lines if l.startswith('AFTER')][0].replace(' ', '\t'))


class BuilderSource(unittest.TestCase):
    def test_conventions(self):
        s = _qa.strip_comments(_qa.src(os.path.join('ServerStorage', 'PattayaShoulderBuilder.luau')))
        self.assertIn(':Clone())', s, 'data modules are required through a Clone (Studio require cache)')
        self.assertIn('ModelStreamingMode.Atomic', s)
        self.assertIn('"ShoulderChunks"', s)
        self.assertIn('Vector3.new(20000, 0, 0)', s)
        for bad in ('RunService', 'IsRunning', 'CarController', 'ApronChunks', 'WideChunks'):
            self.assertFalse(bad in s, f'the shoulder builder must not depend on / touch {bad}')
        reqs = re.findall(r'require\(([^)]*\))', s)
        self.assertEqual(sorted(set(reqs)), ['m:Clone()', 'manModule:Clone()'], 'requires only its own data modules')
        self.assertNotIn(':Destroy()', s.replace('folder:Destroy()', '').replace('bf:Destroy()', '')
                         .replace('models[k]:Destroy()', ''), 'only its own folder / backup / empty models are destroyed')


if __name__ == '__main__':
    unittest.main()
