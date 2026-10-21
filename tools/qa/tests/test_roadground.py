"""Ground at road level, pilot at the Road B junction (tools/roadvis/ground*.py, PattayaRoadGroundBuilder.luau,
docs/ROAD_GROUND_PILOT.md). OFFLINE ONLY. Needs the generated build/ (skipped without it). Checks:
  - the plan: the plateau is the Road B box on the voxel grid, one voxel layer, the occupancy rule, the ramp slope, no
    water / sand / coast / landmark in the written box
  - the targets with Road B + ground (static model): 0 lane holes, 0 drops >= 1.5 anywhere in the box (1-stud grid),
    every road-to-ground edge <= 0.6, the 36 spot 2 runs and every off-road run without a drop or a climb >= 1.5, the
    ramp band without a new cliff; and that today / B alone do show the problem (the checks can fail)
  - the Studio data on disk equals a fresh export (determinism, data up to date)
  - the real PattayaRoadGroundBuilder.luau in the luau CLI on the exported data, with a voxel-level Terrain mock:
    Plan matches, every written column = the Python plan, the backup (TerrainRegion + checksum) comes first, the
    calibration converges for a non-linear occupancy-to-height map and aborts + restores for a dead one, Remove puts
    back EXACTLY every voxel, the aborts write nothing (no Road B, wrong terrain, a shoulder backup in the box), the
    kerb bands are non-colliding, the Pavement colour is opt-in and restored, Leftovers says none
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


def state():
    if 'G' in _C:
        return _C['W'], _C['PB'], _C['G'], _C['states'], _C['res']
    _qa.need_build('pattaya_wide', 'roblox', 'manifest.luau')
    _qa.need_build('shoulders', 'roblox', 'manifest.luau')
    _qa.need_build('aprons', 'roblox', 'manifest.luau')
    try:
        import shapely  # noqa: F401
        from tools.roadvis import ground, junction, world
    except ImportError as e:  # pragma: no cover
        raise unittest.SkipTest(f'needs numpy / shapely (repo .venv): {e}')
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    cfg = dict(junction.CFG)
    bl = world.world_bbox_local(cfg['bbox_world'])
    W = world.load(_qa.BUILD, bbox=bl, margin=900.0)          # the world the exports are made from (cli.py)
    PB = junction.generate(W, dict(cfg, design='B', name=f"{cfg['name']}_B"), log=lambda *a: None)
    G, states, res = ground.pilot(W, PB, log=lambda *a: None)
    _C.update(W=W, PB=PB, G=G, states=states, res=res)
    return W, PB, G, states, res


class Plan(unittest.TestCase):
    def test_plateau_and_columns(self):
        from tools.roadvis import ground, junction
        W, PB, G, states, res = state()
        x0, z0, x1, z1 = G['cfg']['plateau_world']
        bx0, bz0, bx1, bz1 = junction.CFG['bbox_world']
        self.assertTrue(x0 <= bx0 and z0 <= bz0 and x1 >= bx1 and z1 >= bz1, 'the plateau covers the Road B box')
        self.assertTrue(all(v % 4 == 0 for v in (x0, z0, x1, z1)), 'on the 4-stud voxel grid')
        self.assertLessEqual(max(bx0 - x0, bz0 - z0, x1 - bx1, z1 - bz1), 2.0)
        self.assertAlmostEqual(G['o_top'], (G['cfg']['top'] + 2.0) / 4.0, places=12)
        occ = G['occ']
        self.assertTrue(((occ[G['plateau']] - G['o_top']) == 0).all(), 'the whole box at the full height')
        self.assertTrue(((G['mat'] > 0) == (occ > 0)).all())
        self.assertTrue(set(G['mat'][G['plateau']].ravel()) <= {1, 2})
        self.assertTrue((G['mat'][(occ > 0) & ~G['plateau']] == 1).all(), 'the collar and the ramp are Ground')
        self.assertEqual(G['counts']['written'], int((occ > 0).sum()))
        # the target height: every road top (0.98 .. 1.0) at most 0.6 above it, at least 0.52 above it
        lo, hi = G['cfg']['window']
        self.assertTrue(lo <= G['cfg']['top'] <= hi)
        self.assertLessEqual(1.0 - lo, 0.6 + 1e-9)
        self.assertGreaterEqual(0.98 - hi, 0.52 - 1e-9)

    def test_ramp_is_gentle_and_ends_at_today(self):
        W, PB, G, states, res = state()
        rb = res['ramp_band']
        self.assertLessEqual(rb['terrain_max_slope'], 0.09)
        self.assertAlmostEqual(rb['terrain_min_in_band'], -2.0, places=6)
        self.assertEqual(rb['new_drop_cells'], 0, 'no new cliff at the box edge')
        self.assertLessEqual(rb['max_step_increase'], rb['terrain_max_slope'] * math.sqrt(2) + 0.01,
                             'a step may only grow by the ramp slope between diagonal neighbours')

    def test_nothing_that_must_not_be_raised(self):
        from tools.roadvis import ground_audit, world
        W, PB, G, states, res = state()
        mask = ground_audit.TerrainMask(W['broot'])
        import numpy as np
        ii, kk = np.nonzero(G['occ'] > 0)
        xy = np.stack([(G['i0'] + ii) * 4 + 2.0 - world.ORIGIN[0], (G['k0'] + kk) * 4 + 2.0], axis=1)
        self.assertEqual(int((mask.at(xy) != 0).sum()), 0, 'water / beach cells in the written box')
        lm = _qa.luau_table(_qa.need_build('landmarks', 'roblox', 'manifest.luau'))
        lst = lm['landmarks'] if isinstance(lm['landmarks'], list) else lm['landmarks'].get('_list', [])
        x0, z0 = (G['i0'] * 4) - world.ORIGIN[0], G['k0'] * 4
        x1, z1 = x0 + G['ni'] * 4, z0 + G['nk'] * 4
        for l in lst:
            self.assertFalse(x0 - 200 <= l['x'] <= x1 + 200 and z0 - 200 <= l['z'] <= z1 + 200, l['id'])


class Targets(unittest.TestCase):
    def setUp(self):
        self.W, self.PB, self.G, self.states, self.res = state()
        self.bg = self.res['B_ground']

    def test_no_lane_holes(self):
        self.assertGreater(self.bg['lanes']['samples'], 3000)
        self.assertEqual((self.bg['lanes']['holes'], self.bg['lanes']['drops']), (0, 0))
        self.assertEqual(self.bg['lanes_seam']['drops'], 0)

    def test_no_drop_in_the_box(self):
        g = self.bg['grid']
        self.assertGreater(g['cells'], 300000)
        self.assertEqual(g['drop_cells'], 0, g['drops'][:5])
        self.assertLess(g['max_step'], 1.5)
        self.assertEqual(self.bg['edges']['drop_ge_1_5'], 0.0)

    def test_road_to_ground_edges(self):
        r = self.bg['road_edges']
        self.assertGreater(r['facing_ground'], 500)
        self.assertTrue(r['road_to_ground_le_0_6'])
        self.assertLessEqual(r['road_to_ground_max_step'], 0.6)
        self.assertGreaterEqual(r['by_top']['road']['step_min'], 0.52)       # the ground stays under every road top

    def test_spot2_and_offroad_runs(self):
        sp = self.bg['spot2']
        self.assertEqual(sp['runs'], 36)
        self.assertEqual((sp['with_drop'], sp['with_climb'], sp['hang']), (0, 0, 0))
        for k, v in self.bg['offroad'].items():
            self.assertGreater(v['runs'], 20, k)
            self.assertEqual((v['with_drop'], v['with_climb'], v['hang']), (0, 0, 0), k)
            self.assertLess(v['max_step_up'], 1.5, k)
            self.assertGreater(v['wheel_on_ground'], 100, f'{k}: the runs do leave the road')

    def test_today_and_b_show_the_problem(self):
        """the same checks find the owner's complaint without the ground (so they can fail)"""
        for name in ('today', 'B'):
            r = self.res[name]
            self.assertGreater(r['edges']['drop_ge_1_5'], 1000, name)
            self.assertGreater(r['grid']['drop_cells'], 1000, name)
            self.assertGreater(r['offroad']['harness']['with_climb'], 10, name)
        self.assertEqual(self.res['today']['spot2']['with_drop'], 15)       # docs/ROAD_B_OWNER_REVIEW.md section 1
        self.assertEqual(self.res['B']['spot2']['with_drop'], 12)
        self.assertEqual(self.res['B']['lanes']['holes'], 0)
        self.assertEqual(self.res['review_lanes']['B']['unsupported'], 0)
        self.assertEqual(self.res['review_lanes']['today']['unsupported'], 250)

    def test_kerb_bands(self):
        from shapely.geometry import LineString
        from tools.roadvis import ground, world
        segs = self.G['kerbs']
        self.assertGreater(len(segs), 100)
        self.assertGreater(self.res['kerbs']['edge_covered'], 0.85 * self.bg['road_edges']['by_top']['road']['length'])
        st = self.states['B_ground']
        import numpy as np
        for s in segs:
            a, b = np.asarray(s['a']), np.asarray(s['b'])
            m = (a + b) / 2
            t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
            n = np.array([-t[1], t[0]])
            # one side of the band's outer edge is road-height asphalt / shoulder, the other the raised ground
            sides = [st.at([m + n * d])[0] for d in (-0.6, 0.6)]
            self.assertTrue(any(0.95 <= h <= 1.01 for h in sides), (s, sides))
            self.assertTrue(any(abs(h - self.G['cfg']['top']) < 1e-6 for h in sides), (s, sides))


class StudioData(unittest.TestCase):
    def test_export_on_disk_is_current(self):
        """build/roadground/roblox equals a fresh export (rerun tools/roadvis/cli.py ground when this fails)"""
        import hashlib
        import tempfile
        from tools.roadvis import ground_export
        d = _qa.need_build('roadground', 'roblox')
        W, PB, G, states, res = state()
        with tempfile.TemporaryDirectory() as t:
            x = ground_export.export(W, PB, G, states, res, t)
            for f in x['files']:
                self.assertEqual(_qa.read(os.path.join(t, f)), _qa.read(os.path.join(d, f)), f)
        self.assertEqual(sorted(f for f in os.listdir(d) if f.endswith('.luau')), sorted(x['files']))

    def test_caps(self):
        d = _qa.need_build('roadground', 'roblox')
        man = _qa.luau_table(os.path.join(d, 'manifest.luau'))
        tot = 0
        for f in os.listdir(d):
            self.assertLess(os.path.getsize(os.path.join(d, f)), 200 * 1024, f)
            if f.startswith('edges_'):
                m = _qa.luau_table(os.path.join(d, f))
                self.assertLessEqual(m['parts'], 600, f)
                tot += m['parts']
        self.assertEqual(tot, man['counts']['kerbParts'])
        self.assertEqual(len(man['columns']), man['region']['ni'])
        self.assertTrue(all(len(c) == man['region']['nk'] for c in man['columns']))
        self.assertEqual(man['probe']['expected']['floorPairsOver1_5'], 0)
        self.assertLessEqual(man['probe']['edgeStepMax'], 0.6)


# ---- the builder in the luau CLI with a voxel Terrain mock ---------------------------------------------------------------
MOCK = r'''
local MATS = {"Air", "Ground", "Pavement", "Concrete", "Water", "Sand", "Mud", "Asphalt", "SmoothPlastic", "Grass"}
Enum.Material = {}
for i, n in MATS do Enum.Material[n] = {Name = n, Value = 1000 + i} end
local C3 = {}
C3.__index = C3
Color3 = {fromRGB = function(r, g, b) return setmetatable({R = r / 255, G = g / 255, B = b / 255}, C3) end}
function typeof(v)
	if type(v) == "table" then
		local mt = getmetatable(v)
		if mt == C3 then return "Color3" end
		if mt and rawget(v, "X") and rawget(v, "Y") and rawget(v, "Z") then return "Vector3" end
	end
	return type(v)
end
Region3 = {new = function(a, b) return {Min = a, Max = b} end}
local BASE2 = {Part = true, WedgePart = true}
local terrain = workspace.Terrain
-- voxels: key -> {material, occupancy (8-bit, like the engine)}; the city ground = Ground full up to y -4
VOXELS = {}
local function key(x, y, z) return x .. "," .. y .. "," .. z end
function vget(x, y, z)
	local v = VOXELS[key(x, y, z)]
	if v then return v[1], v[2] end
	if y <= -2 then return Enum.Material.Ground, 1 end
	return Enum.Material.Air, 0
end
function vset(x, y, z, m, o)
	o = math.floor(o * 255 + 0.5) / 255
	if o <= 0 then m = Enum.Material.Air end
	VOXELS[key(x, y, z)] = {m, o}
end
local function box(region)
	for _, v in {region.Min.X, region.Min.Y, region.Min.Z, region.Max.X, region.Max.Y, region.Max.Z} do
		assert(v % 4 == 0, "region not on the 4-stud grid")
	end
	return region.Min.X // 4, region.Min.Y // 4, region.Min.Z // 4, region.Max.X // 4 - 1, region.Max.Y // 4 - 1, region.Max.Z // 4 - 1
end
WRITES, LASTWRITE = 0, nil
function terrain:ReadVoxels(region, res)
	assert(res == 4)
	local x0, y0, z0, x1, y1, z1 = box(region)
	local mats, occs = {}, {}
	for x = x0, x1 do
		local mx, ox = {}, {}
		for y = y0, y1 do
			local my, oy = {}, {}
			for z = z0, z1 do
				local m, o = vget(x, y, z)
				table.insert(my, m) table.insert(oy, o)
			end
			table.insert(mx, my) table.insert(ox, oy)
		end
		table.insert(mats, mx) table.insert(occs, ox)
	end
	mats.Size = Vector3.new(x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1)
	occs.Size = mats.Size
	return mats, occs
end
function terrain:WriteVoxels(region, res, mats, occs)
	assert(res == 4)
	local x0, y0, z0, x1, y1, z1 = box(region)
	assert(#mats == x1 - x0 + 1 and #mats[1] == y1 - y0 + 1 and #mats[1][1] == z1 - z0 + 1, "array size")
	for x = x0, x1 do for y = y0, y1 do for z = z0, z1 do
		vset(x, y, z, mats[x - x0 + 1][y - y0 + 1][z - z0 + 1], occs[x - x0 + 1][y - y0 + 1][z - z0 + 1])
	end end end
	WRITES += 1
	LASTWRITE = {x0 = x0, z0 = z0, mats = mats, occs = occs}
end
function terrain:CopyRegion(r)
	local t = I.new("TerrainRegion")
	local cells = {}
	for x = r.Min.X, r.Max.X do for y = r.Min.Y, r.Max.Y do for z = r.Min.Z, r.Max.Z do
		local m, o = vget(x, y, z)
		table.insert(cells, {x - r.Min.X, y - r.Min.Y, z - r.Min.Z, m, o})
	end end end
	rawset(t, "_cells", cells)
	rawset(t, "SizeInCells", Vector3.new(r.Max.X - r.Min.X + 1, r.Max.Y - r.Min.Y + 1, r.Max.Z - r.Min.Z + 1))
	return t
end
function terrain:PasteRegion(t, corner, pasteEmpty)
	for _, c in rawget(t, "_cells") do
		if pasteEmpty or c[5] > 0 then
			VOXELS[key(corner.X + c[1], corner.Y + c[2], corner.Z + c[3])] = {c[4], c[5]}
		end
	end
end
PAVEMENT = Color3.fromRGB(148, 148, 140)
function terrain:GetMaterialColor(m) assert(m == Enum.Material.Pavement) return PAVEMENT end
function terrain:SetMaterialColor(m, c) assert(m == Enum.Material.Pavement) PAVEMENT = c end
-- the terrain surface of a column: the top voxel with occupancy > 0 at layer vy renders at 4 vy + 2 + 4 MAPPING(o)
-- (full to grid line Y -> Y + 2, the measured PattayaBuilder rule); MAPPING is what the test makes the engine do
MAPPING = function(o) return o end
PARTS = nil
local function surfaceAt(x, z)
	local vx, vz = math.floor(x / 4), math.floor(z / 4)
	for vy = 2, -6, -1 do
		local m, o = vget(vx, vy, vz)
		if o > 0 then return 4 * vy + 2 + 4 * MAPPING(o), m end
	end
	return -24, Enum.Material.Air
end
function workspace:Raycast(origin, dir, params)
	local s, m = surfaceAt(origin.X, origin.Z)
	if not (params and params.FilterType == Enum.RaycastFilterType.Include) and PARTS then
		local py = PARTS(origin.X, origin.Z)
		if py and py > s then return {Position = Vector3.new(origin.X, py, origin.Z)} end
	end
	return {Position = Vector3.new(origin.X, s, origin.Z), Material = m, Instance = terrain}
end
'''

TAIL = r'''
local RG = BUILDER
local man = require(DATA.manifest)
local W = workspace.PattayaWorld
local b = man.backup
local function snap()
	local t = {}
	for x = b.i0 - 2, b.i1 + 2 do for y = b.y0 - 1, b.y1 + 1 do for z = b.k0 - 2, b.k1 + 2 do
		local m, o = vget(x, y, z)
		table.insert(t, m.Name .. o)
	end end end
	return t
end
local function diff(a, c)
	local n = 0
	for i = 1, #a do if a[i] ~= c[i] then n += 1 end end
	return n
end
local S0 = snap()
print("PLAN0", (string.gsub(RG.Plan(), "\n", " | ")))
-- 1. no Road B: refused, nothing written
print("NOROADB", RG.Build())
print("NOROADB_DIFF", diff(S0, snap()), WRITES)
-- the built Road B of the place (7 cells, 1,822 parts; 782 moved)
local rv = I.new("Folder") rv.Name = "RoadVisPilot" rv.Parent = W
for c = 1, 7 do
	local cell = I.new("Model") cell.Name = "Cell_" .. c cell.Parent = rv
	for p = 1, (if c < 7 then 260 else 262) do local part = I.new("Part") part.Parent = cell end
end
local rvb = I.new("Folder") rvb.Name = "RoadVisBackup" rvb:SetAttribute("Count", 782) rvb.Parent = ServerStorage
-- 2. wrong terrain in the box (a water voxel): refused, nothing written
vset(b.i0 + 10, -1, b.k0 + 10, Enum.Material.Water, 1)
print("WATER", RG.Build())
VOXELS[b.i0 + 10 .. ",-1," .. b.k0 + 10] = nil
print("WATER_DIFF", diff(S0, snap()), WRITES)
-- 3. a shoulder terrain backup over the box: refused
local sb = I.new("Folder") sb.Name = "PattayaShoulderTerrainBackup" sb.Parent = ServerStorage
local tr = I.new("TerrainRegion") tr:SetAttribute("Corner", Vector3.new(b.i0 + 5, -2, b.k0 + 5)) rawset(tr, "SizeInCells", Vector3.new(3, 3, 3)) tr.Parent = sb
print("SHOULDER", RG.Build())
sb.Parent = nil
print("SHOULDER_DIFF", diff(S0, snap()), WRITES)
print("PLAN1", (string.gsub(RG.Plan(), "\n", " | ")))
-- 4. the build (linear engine)
local out = RG.Build()
print("BUILD", out)
print("BUILD2", RG.Build())
local bk = ServerStorage:FindFirstChild("RoadGroundBackup")
print("BACKUP", bk ~= nil, bk and bk:FindFirstChild("Voxels") ~= nil, bk and bk:GetAttribute("Checksum"), bk and bk:GetAttribute("Writes"))
-- every written column (layer -1) and the layers around it
local g = man.region
local bad = 0
for i = g.i0, g.i0 + g.ni - 1 do
	for k = g.k0, g.k0 + g.nk - 1 do
		local m, o = vget(i, -1, k)
		if o > 0 then print("C", i, k, m.Name, string.format("%.6f", o)) end
		local m2, o2 = vget(i, -2, k)
		local m0, o0 = vget(i, 0, k)
		if m2 ~= Enum.Material.Ground or o2 ~= 1 or o0 ~= 0 then bad += 1 end
	end
end
print("LAYERS_UNCHANGED", bad)
local outside = 0
for _, kv in {{g.i0 - 1, g.k0 + 5}, {g.i0 + g.ni, g.k0 + 5}, {g.i0 + 5, g.k0 - 1}, {g.i0 + 5, g.k0 + g.nk}} do
	local m, o = vget(kv[1], -1, kv[2])
	if o ~= 0 then outside += 1 end
end
print("OUTSIDE_UNCHANGED", outside)
local edges = W:FindFirstChild("RoadGroundEdges")
local kp, badp, cells = 0, 0, 0
for _, c in edges:GetChildren() do
	cells += 1
	if c.ModelStreamingMode ~= "Atomic" then badp += 1 end
	for _, p in c:GetDescendants() do
		if p:IsA("BasePart") then
			kp += 1
			if p.CanCollide or p.CanQuery or p.CanTouch or not p.Anchored or p:GetAttribute("RoadGround") ~= "kerb" then badp += 1 end
			local top = p.CFrame.Position.Y + p.Size.Y / 2
			if math.abs(top - man.kerb.top) > 1e-6 then badp += 1 end
		end
	end
end
print("KERBS", kp, cells, badp)
print("PROBE", (string.gsub(RG.Probe(), "\n", " | ")))
-- road parts (top 1.0) under every edge check's inside point: the probe's road-to-ground step = 1.0 - the ground
local EC = man.edgeChecks
PARTS = function(x, z)
	for i = 1, #EC, 5 do
		if math.abs(x - EC[i]) < 0.3 and math.abs(z - EC[i + 1]) < 0.3 then return 1.0 end
	end
	return nil
end
print("PROBE_EDGES", string.match(RG.Probe(), "road%-to%-ground edges: [^\n]*"))
PARTS = nil
-- 5. remove: exact
print("REMOVE", RG.Remove())
print("REMOVE_DIFF", diff(S0, snap()), W:FindFirstChild("RoadGroundEdges") == nil, ServerStorage:FindFirstChild("RoadGroundBackup") == nil)
print("LEFT", RG.Leftovers())
print("REMOVE2", RG.Remove())
-- 6. a non-linear engine: calibrated
MAPPING = function(o) return o ^ 1.3 end
WRITES = 0
print("CURVED", RG.Build())
print("CURVED_WRITES", WRITES)
print("CURVED_REMOVE", RG.Remove())
print("CURVED_DIFF", diff(S0, snap()))
-- 7. a dead engine (writes do not move the surface): aborted, restored exactly
MAPPING = function(o) return 0 end
print("DEAD", RG.Build())
print("DEAD_DIFF", diff(S0, snap()), ServerStorage:FindFirstChild("RoadGroundBackup") == nil, W:FindFirstChild("RoadGroundEdges") == nil)
print("DEAD_LEFT", RG.Leftovers())
MAPPING = function(o) return o end
-- 8. the Pavement colour: opt-in, restored
local before = PAVEMENT
print("COLOUR", RG.Build({pavementColor = true}) ~= nil, math.floor(PAVEMENT.R * 255 + 0.5), PAVEMENT ~= before)
print("COLOUR_REMOVE", RG.Remove())
print("COLOUR_BACK", PAVEMENT == before)
-- 9. the ground alone (no kerb bands), without Road B
rv.Parent = nil
print("ALONE", RG.Build({edges = false}))
print("ALONE_EDGES", W:FindFirstChild("RoadGroundEdges") == nil)
print("ALONE_REMOVE", RG.Remove())
print("FINAL", diff(S0, snap()), RG.Leftovers())
for _, w in WARN do print("WARN", w) end
'''


class LuauRoadGround(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _qa.need_build('roadground', 'roblox')
        if not os.path.exists(os.path.join(d, 'manifest.luau')):
            raise unittest.SkipTest('build/roadground/roblox missing (run tools/roadvis/cli.py ground)')
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadGroundBuilder.luau'))
        parts = [test_shoulders.STUB, MOCK, 'local DATA = I.new("Folder") DATA.Name = "PattayaDataRoadGround" DATA.Parent = ServerStorage\n']
        mods = ['manifest'] + [f[:-5] for f in sorted(os.listdir(d)) if f.startswith('edges_')]
        for m in mods:
            body = _qa.read(os.path.join(d, m + '.luau'))
            parts.append(f'moduleScript("{m}", function()\n{body}\nend).Parent = DATA\n')
        parts.append('local require = function(m) return m._load() end\n')
        parts.append('local BUILDER = (function()\n' + src + '\nend)()\n')
        parts.append(TAIL)
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=900)
        cls.lines = cls.out.splitlines()
        try:
            with open(os.path.join(d, '..', 'luau_cli_output.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(l for l in cls.lines if not l.startswith('C\t')))
        except OSError:
            pass
        cls.man = _qa.luau_table(os.path.join(d, 'manifest.luau'))

    def line(self, tag):
        got = [l for l in self.lines if l.startswith(tag + '\t') or l.startswith(tag + ' ')]
        self.assertTrue(got, f'{tag} missing; output tail: {self.out[-2000:]}')
        return got[0]

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-3000:])

    def test_plan(self):
        p0 = self.line('PLAN0')
        self.assertIn('MATCHES the expected state', p0)
        self.assertIn('RoadVisPilot NOT built', p0)
        p1 = self.line('PLAN1')
        self.assertIn('RoadVisPilot built (7 cells, 1822 parts', p1)
        self.assertIn('present (Count 782', p1)
        self.assertIn('overlapping the box: 0', p1)

    def test_aborts_write_nothing(self):
        self.assertIn('RoadVisPilot is not built', self.line('NOROADB'))
        self.assertEqual(self.line('NOROADB_DIFF').split()[1:], ['0', '0'])
        self.assertIn('not the expected state', self.line('WATER'))
        self.assertIn('Water 1.00 at y -4 x1', self.line('WATER'))
        self.assertEqual(self.line('WATER_DIFF').split()[1:], ['0', '0'])
        self.assertIn('terrain backups overlap the box', self.line('SHOULDER'))
        self.assertEqual(self.line('SHOULDER_DIFF').split()[1:], ['0', '0'])

    def test_build_writes_the_plan(self):
        """every column the builder wrote = the Python plan (material, occupancy to the engine's 8 bits)"""
        W, PB, G, states, res = state()
        self.assertIn('road ground: raised', self.line('BUILD'))
        self.assertIn('already built', self.line('BUILD2'))
        got = {}
        for l in self.lines:
            if l.startswith('C\t'):
                _, i, k, m, o = l.split('\t')
                got[(int(i), int(k))] = (m, float(o))
        import numpy as np
        ii, kk = np.nonzero(G['occ'] > 0)
        self.assertEqual(len(got), len(ii))
        names = {1: 'Ground', 2: 'Pavement'}
        for a, c in zip(ii, kk):
            m, o = got[(G['i0'] + int(a), G['k0'] + int(c))]
            self.assertEqual(m, names[int(G['mat'][a, c])])
            self.assertLessEqual(abs(o - G['occ'][a, c]), 0.5 / 255 + 1e-9)
        self.assertEqual(self.line('LAYERS_UNCHANGED').split()[1], '0')
        self.assertEqual(self.line('OUTSIDE_UNCHANGED').split()[1], '0')
        bk = self.line('BACKUP').split()
        self.assertEqual(bk[1:3], ['true', 'true'])
        self.assertEqual(bk[4], '1', 'the linear engine needs one write')
        m = re.search(r'to y ([\d.]+)', self.line('BUILD'))
        self.assertAlmostEqual(float(m.group(1)), self.man['top'], delta=0.01)

    def test_kerb_bands(self):
        k = self.line('KERBS').split()
        self.assertEqual(int(k[1]), self.man['counts']['kerbParts'])
        self.assertEqual(int(k[2]), len(self.man['cells']))
        self.assertEqual(k[3], '0', 'every band anchored, non-colliding, non-queryable, CanTouch off, tagged, at the kerb top')

    def test_probe_runs(self):
        p = self.line('PROBE')
        self.assertIn(f"{self.man['counts']['probes']} calibration columns", p)
        self.assertIn('floor steps >= 1.5: 0', p)
        self.assertIn('rays that hit nothing 0', p)
        e = self.line('PROBE_EDGES')
        m = re.search(r'(\d+) pairs, step ([\d.]+) \.\. ([\d.]+), over 0\.6: (\d+)', e)
        self.assertTrue(m, e)
        self.assertEqual(int(m.group(1)), self.man['counts']['edgeChecks'])
        self.assertAlmostEqual(float(m.group(2)), 1.0 - 0.431, delta=0.005)     # the mock ground: 155 / 255 occupancy
        self.assertEqual(m.group(4), '0')

    def test_remove_is_exact_and_leaves_nothing(self):
        self.assertIn('restored EXACTLY', self.line('REMOVE'))
        self.assertEqual(self.line('REMOVE_DIFF').split()[1:], ['0', 'true', 'true'])
        self.assertIn('road ground leftovers: none', self.line('LEFT'))
        self.assertIn('nothing to restore', self.line('REMOVE2'))

    def test_calibration_and_abort(self):
        self.assertIn('road ground: raised', self.line('CURVED'))
        w = int(self.line('CURVED_WRITES').split()[1])
        self.assertGreaterEqual(w, 2)
        self.assertLessEqual(w, self.man['calibrate']['maxWrites'])
        y = float(re.search(r'to y ([\d.]+)', self.line('CURVED')).group(1))
        self.assertLessEqual(abs(y - self.man['top']), self.man['calibrate']['tol'] + 1e-9)
        self.assertIn('restored EXACTLY', self.line('CURVED_REMOVE'))
        self.assertEqual(self.line('CURVED_DIFF').split()[1], '0')
        self.assertIn('ABORTED after 1 writes', self.line('DEAD'))
        self.assertIn('restored exactly (checksum), backup removed', self.line('DEAD'))
        self.assertEqual(self.line('DEAD_DIFF').split()[1:], ['0', 'true', 'true'])
        self.assertIn('leftovers: none', self.line('DEAD_LEFT'))

    def test_pavement_colour_opt_in(self):
        c = self.line('COLOUR').split()
        self.assertEqual(c[1:], ['true', str(self.man['pavementColor'][0]), 'true'])
        self.assertIn('Pavement colour restored', self.line('COLOUR_REMOVE'))
        self.assertEqual(self.line('COLOUR_BACK').split()[1], 'true')

    def test_ground_alone_and_final_state(self):
        self.assertIn('0 kerb band parts', self.line('ALONE'))
        self.assertEqual(self.line('ALONE_EDGES').split()[1], 'true')
        self.assertIn('restored EXACTLY', self.line('ALONE_REMOVE'))
        f = self.line('FINAL')
        self.assertTrue(f.split()[1] == '0' and 'leftovers: none' in f, f)
        warns = [l for l in self.lines if l.startswith('WARN')]
        expected = [w for w in warns if 'not the expected state' in w or 'ABORTED after 1 writes' in w]
        self.assertEqual(len(expected), 2, warns)                  # the water abort and the dead-engine abort warn
        self.assertEqual(warns, expected, 'no other warning (kerb module part counts, restore)')


class BuilderSource(unittest.TestCase):
    def test_conventions(self):
        s = _qa.strip_comments(_qa.src(os.path.join('ServerStorage', 'PattayaRoadGroundBuilder.luau')))
        self.assertIn(':Clone())', s)
        self.assertIn('ModelStreamingMode.Atomic', s)
        self.assertIn('Vector3.new(20000, 0, 0)', s)
        for bad in ('RunService', 'CarController', 'PathfindingService', 'FillBlock', 'ReplaceMaterial', 'ShoulderChunks'):
            self.assertNotIn(bad, s)
        destroys = re.findall(r'(\w+):Destroy\(\)', s)
        self.assertEqual(sorted(set(destroys)), ['edges', 'folder'])        # only its own kerb folder and its backup
        self.assertIn('PasteRegion', s)
        self.assertIn('CopyRegion', s)
        # nothing outside its own two containers is parented or moved
        self.assertEqual(sorted(set(re.findall(r'(\w+)\.Parent = ', s))), ['cell', 'folder', 'p', 'region', 'root'])


if __name__ == '__main__':
    unittest.main()
