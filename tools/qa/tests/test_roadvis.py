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
import re
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

    def test_no_markings_inside_junction_field(self):
        """no lane / centre / edge marking inside the junction polygon (complexes + carriageways sharing asphalt at an
        angle); only stop lines and zebras at its boundary"""
        self.assertEqual(self.c['marks_in_junction'], 0.0)
        self.assertGreater(self.c['junction_field_area'], self.P['Z'].area)
        J = self.P['J'].buffer(-0.5)
        for m in self.P['marks']:
            if m['kind'] in ('stop', 'zebra'):
                self.assertLess(m['poly'].intersection(J.difference(self.P['Z'].buffer(2.0))).area, 0.5, m['kind'])

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


class TestShoulderProof(unittest.TestCase):
    """tools/roadvis/shoulder_proof.py: the shoulder pilot still carries the wheels with design B in place"""

    @classmethod
    def setUpClass(cls):
        from shapely.geometry import box
        from tools.roadvis import shoulder_proof
        W, Ps = state()
        cls.res = shoulder_proof.run(W, Ps['B'], box(4220, 650, 4820, 1250))

    def test_no_shoulder_part_replaced(self):
        self.assertEqual(self.res['untouched']['replaced_shoulder_pieces'], 0)

    def test_edges_flush_no_overlap_no_new_drop(self):
        a, b = self.res['edges_after'], self.res['edges_before']
        self.assertEqual(a['B_sidewalk_island_collision_on_shoulders'], 0.0)
        self.assertEqual(a['B_visual_sidewalk_on_shoulders'], 0.0)
        self.assertLessEqual(a['max_flush_step'], 0.02)
        self.assertLessEqual(a['max_kerb_step'], 0.62)
        self.assertLessEqual(a['drop'], b['drop'])
        self.assertLessEqual(a['slot'], b['slot'])             # the kerb collision keeps the exact edge at a shoulder
        self.assertEqual(b['ridge'], 0.0)
        self.assertLessEqual(a['ridge'], 5.0)                  # no sidewalk / island sliver in the pilot's joints (3 measured)

    def test_drive_gate_not_worse(self):
        before = {(r['dir'], r['lateral'], r['speed']): r for r in self.res['gate_before']['runs']}
        for r in self.res['gate_after']['runs']:
            k = (r['dir'], r['lateral'], r['speed'])
            self.assertLessEqual(r['wheel_drops'], before[k]['wheel_drops'], k)
            # a kerb contact tilts the car a little (up 0.998): allowed; never lower than before where that was < 0.95
            self.assertGreaterEqual(r['min_up'] + 1e-6, min(before[k]['min_up'] - 0.001, 0.95), k)
        self.assertGreaterEqual(self.res['gate_after']['min_up'], self.res['gate_before']['min_up'] - 0.001)
        self.assertEqual(self.res['gate_after']['n'], 36)

    def test_no_drop_inside_a_lane(self):
        """the owner's question: how many spot 2 drops happen inside a drivable lane (B vs today)"""
        d = self.res['drops_in_lane']
        self.assertEqual((d['after'], d['after_samples']), (0, 0))
        self.assertEqual((d['before'], d['before_samples']), (0, 0))
        before = {(r['dir'], r['lateral'], r['speed']): r for r in self.res['drops_before']}
        self.assertEqual(len(before), sum(1 for r in self.res['gate_before']['runs'] if r['wheel_drops']))
        self.assertEqual(len(self.res['drops_after']), sum(1 for r in self.res['gate_after']['runs'] if r['wheel_drops']))
        for r in self.res['drops_after']:
            k = (r['dir'], r['lateral'], r['speed'])
            self.assertIn(k, before, 'B drops a wheel on a run that has none today')
            self.assertLessEqual(r['drop_length'], before[k]['drop_length'], k)
            for t in r['stretches']:
                self.assertIn(t['where'], ('past the shoulder', 'shoulder strip', 'terrain'), (k, t['where'], t['world']))


class TestPilotA(unittest.TestCase):
    def test_design_a_generated(self):
        W, Ps = state()
        c = Ps['A']['checks']
        self.assertEqual(c['building_overlap'], 0.0)
        self.assertLessEqual(c['wheel_after']['unsupported'], c['wheel_before']['unsupported'])
        self.assertGreaterEqual(c['lane_boundary_coverage'], 0.9)


# ---- the Studio builder (PattayaRoadVisBuilder.luau) on the exported data, in the luau CLI with stub Roblox types ----
EXTRA_STUB = r'''
Enum.Material = {}
for _, n in {"Concrete", "Asphalt", "Ground", "SmoothPlastic", "Grass"} do Enum.Material[n] = {Name = n} end
Enum.RaycastFilterType = {Exclude = "Exclude", Include = "Include"}
function typeof(v) if type(v) == "table" and getmetatable(v) == CF then return "CFrame" end return type(v) end
function I:GetFullName()
	local names, p = {}, self
	while p do table.insert(names, 1, rawget(p, "Name") or "?") p = rawget(p, "_parent") end
	return table.concat(names, ".")
end
BASE.Part = true BASE.WedgePart = true BASE.MeshPart = true
local oldIndex = I.__index
I.__index = function(t, k) if k == "Parent" then return rawget(t, "_parent") end return oldIndex(t, k) end
'''

LUAU_TAIL = r'''
local RV = BUILDER
local man = require(DATA.manifest)
local W = workspace.PattayaWorld
local function folder(parent, name) local f = I.new("Folder") f.Name = name f.Parent = parent return f end
-- a mock city: one tiny part at every expected key, in the container the builder searches, plus decoys
local cont = {}
for _, n in {"WideChunks", "WideJunctions", "ApronChunks", "FurnitureChunks", "ShoulderChunks"} do cont[n] = folder(W, n) end
local chunk = folder(cont.WideChunks, "Chunk_8_1")
local edge = I.new("Model") edge.Name = "Sukhumvit Road" edge.Parent = chunk
local apr = folder(folder(cont.ApronChunks, "Chunk_a8_1"), "Aprons")
local fur = folder(cont.FurnitureChunks, "Chunk_f8_1")
local where = {edge, edge, edge, edge, cont.WideJunctions, cont.WideJunctions, apr, apr, fur}
local names = {"Road", "Sidewalk", "Dash", "Centre", "Junction", "Joint", "Road", "Sidewalk", "ZebraStripe"}
local K = man.replace.keys
local ORIG = {}
local function cfkey(c)
	local t = {}
	for _, v in {c.Position, c.XVector, c.YVector, c.ZVector} do
		table.insert(t, string.format("%.17g,%.17g,%.17g", v.X, v.Y, v.Z))
	end
	return table.concat(t, ";")
end
for i = 1, #K, 3 do
	-- every mock part turned about Y by its own angle: the restore must give back the full CFrame, not just X / Z
	local a = (i % 13) * 0.4137
	local p = I.new("Part") p.Name = names[K[i]] p.Size = Vector3.new(0.2, 4, 0.2)
	p.CFrame = CFrame.fromMatrix(Vector3.new(K[i + 1], -1 - (i % 5) * 0.001, K[i + 2]), Vector3.new(math.cos(a), 0, -math.sin(a)),
		Vector3.new(0, 1, 0), Vector3.new(math.sin(a), 0, math.cos(a)))
	if K[i] == 7 then p:SetAttribute("Apron", true) end
	p.Parent = where[K[i]]
	table.insert(ORIG, {p, where[K[i]], K[i + 1], K[i + 2], cfkey(p.CFrame)})
end
local function decoy(parent, name, x, z, sx, attr, sz)
	local p = I.new("Part") p.Name = name p.Size = Vector3.new(sx, 4, sz or 0.2) p.CFrame = CFrame.new(x, -1, z)
	if attr then p:SetAttribute(attr, true) end
	p.Parent = parent return p
end
local bx0, bz0 = man.bbox[1], man.bbox[2]
local D1 = decoy(edge, "Road", bx0 - 50, bz0 + 100, 1)                -- outside the area
local D2 = decoy(edge, "Road", bx0 + 1, bz0 + 1, 40, nil, 40)        -- centre inside (corner), 72 % outside
local D3 = decoy(edge, "Shoulder", bx0 + 200, bz0 + 200, 1)           -- not a candidate name
local shc = folder(cont.ShoulderChunks, "Chunk_s8_1")
local S1 = decoy(shc, "Road", bx0 + 210, bz0 + 210, 1, "Shoulder")   -- inside, but a shoulder: never selected
S1:SetAttribute("ShoulderKind", "gap") S1.CanCollide = true S1.Color = {92, 91, 88} S1.Material = Enum.Material.Concrete S1.Transparency = 0
local S2 = decoy(shc, "Shoulder", bx0 + 220, bz0 + 220, 1, "Shoulder")
S2:SetAttribute("ShoulderKind", "shoulder") S2.Color = {92, 91, 88} S2.Material = Enum.Material.Concrete S2.Transparency = 0
local function snap(p) return table.concat({tostring(p.Parent and p.Parent.Name), tostring(p.Color[1]), tostring(p.Material.Name),
	tostring(p.Transparency), tostring(p.CanCollide), tostring(p.CFrame.Position.X), tostring(p.CFrame.Position.Z)}, "|") end
local SNAP0 = {snap(S1), snap(S2)}
local function nshoulder() return #cont.ShoulderChunks:GetDescendants() end
local NSH0 = nshoulder()
print("PLAN", RV.Plan())
print("BUILD", RV.Build())
print("BUILD2", RV.Build())
local pilot = W.RoadVisPilot
local total = 0
for _, c in pilot:GetChildren() do
	local n = 0
	for _, p in c:GetDescendants() do if p:IsA("BasePart") then n += 1 end end
	total += n
	print("CELL", c.Name, n, c.ModelStreamingMode)
end
print("TOTAL", total, man.counts.parts)
local kinds = {}
for _, p in pilot:GetDescendants() do
	if not p:IsA("BasePart") then continue end
	local k = p:GetAttribute("RoadVisKind")
	kinds[k] = (kinds[k] or 0) + 1
	if (k == "asphalt" or k == "sidewalk" or k == "island" or k == "support") ~= (p.CanCollide == true) then print("BADCOLLIDE", k) end
	if k == "support" then
		local c, s = p.CFrame, p.Size
		local pts = {c * Vector3.new(0, -s.Y / 2, -s.Z / 2), c * Vector3.new(0, -s.Y / 2, s.Z / 2), c * Vector3.new(0, s.Y / 2, s.Z / 2)}
		local top = -math.huge
		for _, dx in {-1, 1} do for _, dy in {-1, 1} do for _, dz in {-1, 1} do
			top = math.max(top, (c * Vector3.new(dx * s.X / 2, dy * s.Y / 2, dz * s.Z / 2)).Y)
		end end end
		local xs = {}
		for _, q in pts do table.insert(xs, string.format("%.3f", q.X)) table.insert(xs, string.format("%.3f", q.Z)) end
		print("SUPPORT", p.Name, p.Transparency, tostring(p.CanCollide), tostring(p.CanQuery), tostring(p.CanTouch),
			string.format("%.3f", top), p.Parent.Name, table.concat(xs, " "))
	end
end
for k, n in kinds do print("KIND", k, n) end
print("MOVE", RV.MoveReplaced())
local moved, wrong = 0, 0
for _, o in ORIG do if o[1]:IsDescendantOf(ServerStorage.RoadVisBackup) then moved += 1 else wrong += 1 end end
print("MOVED", moved, wrong, D1.Parent == edge, D2.Parent == edge, D3.Parent == edge, S1.Parent == shc, S2.Parent == shc)
print("MOVE2", RV.MoveReplaced())
print("SHOULDERS_AFTER_BUILD_MOVE", snap(S1) == SNAP0[1] and snap(S2) == SNAP0[2])
print("SHOULDERCOUNT_AFTER_BUILD_MOVE", NSH0, nshoulder())
print("PROBE", RV.Probe())
print("LOOK", RV.ShoulderLook({recolour = true, hideGapFills = true}))
print("LOOKSTATE", S1.Transparency, S1.CanCollide, S2.Color[1], S2:GetAttribute("RVOrigColor")[1])
print("LOOKREV", RV.ShoulderLookRevert())
print("LOOKBACK", S1.Transparency, S2.Color[1], S2:GetAttribute("RVOrigColor") == nil)
print("REMOVE", RV.Remove())
print("SHOULDERS_AFTER_REMOVE", snap(S1) == SNAP0[1] and snap(S2) == SNAP0[2])
print("SHOULDERCOUNT_AFTER_REMOVE", NSH0, nshoulder())
local back, cfok = 0, 0
for _, o in ORIG do
	if o[1].Parent == o[2] then back += 1 end
	-- exact: all 12 CFrame components identical, the builder's attributes gone, the part's own attributes kept
	if cfkey(o[1].CFrame) == o[5] and o[1]:GetAttribute("OriginalCFrame") == nil and o[1]:GetAttribute("OriginalParent") == nil
		and o[1]:GetAttribute("RoadVisMoved") == nil and (o[1].Name ~= "Road" or o[2] ~= apr or o[1]:GetAttribute("Apron") == true) then
		cfok += 1
	end
end
print("RESTORED", back, cfok, #ORIG, W:FindFirstChild("RoadVisPilot") == nil, ServerStorage:FindFirstChild("RoadVisBackup") == nil)
-- abort: one expected part missing -> nothing moves
ORIG[1][1].Parent = nil
print("ABORT", RV.MoveReplaced())
print("ABORTSTATE", ServerStorage:FindFirstChild("RoadVisBackup") == nil, ORIG[2][1].Parent == ORIG[2][2])
print("MESH", RV.Build({mesh = true}))
for _, w in WARN do print("WARN", w) end
-- the seam rule (Studio 2026-10-22, sample 220): road everywhere except a 0.001-stud crack through the first footprint
-- point of probe sample 1 at offset 0 (a seam: its 4 neighbours 0.05 away hit road) and a 0.2-stud hole at the first
-- point of sample 3 (a real drop)
local PS, foot = man.probe.samples, man.probe.foot
local function fp(k)
	local i = 6 * (k - 1) + 1
	local cx, cz, tx, tz = PS[i] + 20000, PS[i + 1], PS[i + 2], PS[i + 3]
	return cx + (-tz) * (-foot[1] / 2) + tx * (-foot[2] / 2), cz + tx * (-foot[1] / 2) + tz * (-foot[2] / 2)
end
local cx1, cz1 = fp(1)
local cx3, cz3 = fp(3)
function workspace:Raycast(origin)
	if math.abs(origin.X - cx1) < 0.0005 and math.abs(origin.Z - cz1) < 0.0005 then return nil end
	if math.abs(origin.X - cx3) < 0.1 and math.abs(origin.Z - cz3) < 0.1 then return nil end
	return {Position = Vector3.new(origin.X, 1.0, origin.Z)}
end
local pr = RV.Probe()
print("SEAMPROBE", (string.gsub(string.match(pr, "^[^\n]*"), "\t", " ")))
print("SEAMOFF0", (string.match(pr, "offset 0: [^\n]*")))
'''


class LuauRoadVis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = _qa.need_build('roadvis', 'roblox')
        if not os.path.exists(os.path.join(d, 'manifest.luau')):
            raise unittest.SkipTest('build/roadvis/roblox missing (run tools/roadvis/export_luau.py)')
        import test_shoulders
        src = _qa.src(os.path.join('ServerStorage', 'PattayaRoadVisBuilder.luau'))
        parts = [test_shoulders.STUB, EXTRA_STUB, 'local DATA = I.new("Folder") DATA.Name = "PattayaDataRoadVis" DATA.Parent = ServerStorage\n']
        mods = ['manifest'] + [f[:-5] for f in sorted(os.listdir(d)) if f.startswith('cell_')]
        for m in mods:
            body = _qa.read(os.path.join(d, m + '.luau'))
            parts.append(f'moduleScript("{m}", function()\n{body}\nend).Parent = DATA\n')
        parts.append('local require = function(m) return m._load() end\n')
        parts.append('local BUILDER = (function()\n' + src + '\nend)()\n')
        parts.append(LUAU_TAIL)
        cls.code, cls.out = _qa.run_luau(''.join(parts), timeout=600)
        cls.lines = cls.out.splitlines()
        try:                      # evidence for docs/ROAD_B_OWNER_REVIEW.md (build/ is not committed)
            with open(os.path.join(d, '..', 'luau_cli_output.txt'), 'w', encoding='utf-8') as f:
                f.write(cls.out)
        except OSError:
            pass
        cls.man = _qa.luau_table(os.path.join(d, 'manifest.luau'))

    def line(self, tag):
        got = [l for l in self.lines if l.startswith(tag + '\t') or l.startswith(tag + ' ')]
        self.assertTrue(got, f'{tag} missing; output tail: {self.out[-1500:]}')
        return got[0]

    def test_runs(self):
        self.assertEqual(self.code, 0, self.out[-2500:])

    def test_build_counts_and_cells(self):
        tot = self.line('TOTAL').split()
        self.assertEqual(int(tot[1]), int(tot[2]))
        self.assertEqual(int(tot[1]), self.man['counts']['parts'])
        cells = [l.split() for l in self.lines if l.startswith('CELL')]
        self.assertEqual(len(cells), len(self.man['cells']))
        self.assertTrue(all(c[3] == 'Atomic' for c in cells))
        self.assertTrue(all(int(c[2]) <= 600 for c in cells), [c[1:3] for c in cells])   # every Atomic cell <= 600 parts
        self.assertIn('already exists', self.line('BUILD2'))
        self.assertFalse([l for l in self.lines if l.startswith('BADCOLLIDE')])
        kinds = {l.split()[1]: int(l.split()[2]) for l in self.lines if l.startswith('KIND')}
        for k, n in self.man['counts']['byKind'].items():
            self.assertEqual(kinds.get(k), n, k)

    def test_modules_capped(self):
        d = os.path.join(_qa.BUILD, 'roadvis', 'roblox')
        for f in os.listdir(d):
            if f.startswith('cell_'):
                m = _qa.luau_table(os.path.join(d, f))
                self.assertLessEqual(m['parts'], 600, f)
                self.assertLess(os.path.getsize(os.path.join(d, f)), 200 * 1024, f)

    def test_plan_matches(self):
        self.assertIn('MATCHES the data', self.out)

    def test_move_and_restore_round_trip(self):
        self.assertIn(f"moved {self.man['replace']['total']} parts", self.line('MOVE'))
        f = self.line('MOVED').split()
        self.assertEqual((int(f[1]), int(f[2])), (self.man['replace']['total'], 0))
        self.assertEqual(f[3:], ['true'] * 5, 'decoys and shoulder parts stay')
        self.assertIn('already exists', self.line('MOVE2'))
        r = self.line('RESTORED').split()
        n = self.man['replace']['total']
        self.assertEqual(r[1:], [str(n), str(n), str(n), 'true', 'true'])
        self.assertIn(f'restored {n} of {n}', self.line('REMOVE'))

    def test_shoulder_chunks_untouched(self):
        self.assertEqual(self.line('SHOULDERS_AFTER_BUILD_MOVE').split()[1], 'true')
        self.assertEqual(self.line('SHOULDERS_AFTER_REMOVE').split()[1], 'true')
        for tag in ('SHOULDERCOUNT_AFTER_BUILD_MOVE', 'SHOULDERCOUNT_AFTER_REMOVE'):
            a, b = self.line(tag).split()[1:3]
            self.assertEqual(a, b, tag)

    def test_supports_invisible_and_queryable(self):
        sup = [l.split() for l in self.lines if l.startswith('SUPPORT')]
        self.assertEqual(len(sup), self.man['counts']['byKind']['support'])
        for f in sup:
            self.assertEqual(f[1:6], ['RoadSupport', '1', 'true', 'true', 'false'], f)
            self.assertAlmostEqual(float(f[6]), 1.0, places=3)          # flush with the asphalt top

    def test_supports_geometry_from_built_parts(self):
        """the footprints of the RoadSupport WedgeParts the builder made (luau CLI) against the Python data: inside the
        planned support area, never on a shoulder piece, never under a kerb / sidewalk / island, <= 2 studs from the
        visible asphalt"""
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union
        _, Ps = state()
        P = Ps['B']
        tris = []
        for f in (l.split() for l in self.lines if l.startswith('SUPPORT')):
            c = [float(v) for v in f[8:14]]
            tris.append(Polygon([(c[0] - 20000, c[1]), (c[2] - 20000, c[3]), (c[4] - 20000, c[5])]))
        self.assertTrue(tris)
        U = unary_union([t.buffer(1e-4) for t in tris])
        self.assertLess(U.difference(P['keep_support'].buffer(0.05)).area, 0.05)
        self.assertLess(U.intersection(P['shoulders'].buffer(-0.01)).area, 0.01)
        kerbs = unary_union([P['walk'], P['islands'], P['kerb'], P['island_kerb']] + P['walk_tris'] + P['isl_tris'])
        self.assertLess(U.intersection(kerbs.buffer(-0.01)).area, 0.01)
        vis = unary_union(P['tris'])
        far = max(vis.distance(Point(x, z)) for t in tris for x, z in list(t.exterior.coords)[:3])
        self.assertLessEqual(far, 2.0)

    def test_abort_on_mismatch(self):
        self.assertIn('ABORTED, nothing moved', self.line('ABORT'))
        self.assertEqual(self.line('ABORTSTATE').split()[1:], ['true', 'true'])

    def test_shoulder_look_round_trip(self):
        self.assertIn('1 strips / tapers recoloured, 1 gap fills hidden', self.line('LOOK'))
        st = self.line('LOOKSTATE').split()
        self.assertEqual(st[1:4], ['1', 'true', '176'])
        self.assertEqual(st[4], '92')
        self.assertEqual(self.line('LOOKBACK').split()[1:], ['0', '92', 'true'])

    def test_probe_runs(self):
        p = self.line('PROBE')
        self.assertIn(f"{len(self.man['probe']['legs'])} legs", p)
        self.assertIn(f"{len(self.man['probe']['samples']) // 6} samples", p)

    def test_probe_seam_rule(self):
        """a ray through a hairline crack (neighbours 0.05 away hit road) is a seam, a 0.2-stud hole is a drop"""
        head = self.line('SEAMPROBE')
        self.assertIn('total drops 1; hairline seams 1', head)
        off0 = self.line('SEAMOFF0')
        self.assertIn('drop 1, blocked 0, hairline seams 1', off0)

    def test_mesh_opt_in_falls_back(self):
        self.assertTrue(any('EditableMesh' in l for l in self.lines if l.startswith('WARN')))
        self.assertIn('(Parts)', self.line('MESH'))

    def test_expected_probe_offline(self):
        for o, v in self.man['probe']['expected'].items():
            self.assertEqual(v['drop'], 0, o)

    def test_replace_rule_never_selects_shoulders(self):
        codes = set(self.man['replace']['keys'][0::3])
        self.assertTrue(codes <= set(range(1, 10)))
        self.assertGreater(self.man['replace']['total'], 700)


class ZebraKeysFromBuiltFurniture(unittest.TestCase):
    """Studio 2026-10-22: RV.Plan matched only 70 of the export's 155 ZebraStripe keys; the place has 133 (Chunk_f8_1 /
    f8_2 / f9_1). furniture.json was stale (first pass), the place is built from the dual-pass-2 chunk modules. The
    replace list must hold exactly the bars the built modules put in the box, and the B geometry must not depend on it."""

    def test_replace_zebras_equal_the_built_modules(self):
        d = _qa.need_build('roadvis', 'roblox')
        man = _qa.luau_table(os.path.join(d, 'manifest.luau'))
        if 'zebraSource' not in man['replace']:
            raise unittest.SkipTest('build/roadvis/roblox is an export from before the zebra-source fix: rerun tools/roadvis/cli.py pilot')
        sys.path.insert(0, os.path.join(_qa.ROOT, 'tools', 'mapgen'))
        import furniture as fm
        from shapely.geometry import box
        from tools.roadvis import export_luau, world
        fd = _qa.need_build('furniture', 'roblox')
        bars = []
        for f in sorted(os.listdir(fd)):
            if f.startswith('chunk_f') and f.endswith('.luau'):
                r = _qa.luau_table(os.path.join(fd, f)).get('crossings') or []
                r = r.get('_list', []) if isinstance(r, dict) else r
                bars += [b for i in range(0, len(r) - 7, 8) for b in fm.crossing_bars(r[i:i + 8])]
        bw = man['bbox']
        sel = export_luau.replace_rule([(9, b) for b in bars], box(*world.world_bbox_local(bw)))
        want = sorted((round(x + world.ORIGIN[0], 2), round(z, 2)) for _, x, z, _ in sel)
        K = man['replace']['keys']
        got = sorted((round(K[i + 1], 2), round(K[i + 2], 2)) for i in range(0, len(K), 3) if K[i] == 9)
        self.assertEqual(len(got), len(want))
        for a, b in zip(got, want):
            self.assertLessEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 0.011, (a, b))
        self.assertEqual(man['replace']['byName']['ZebraStripe'], len(want))
        self.assertEqual(man['replace']['total'], sum(man['replace']['byName'].values()))


class BuilderSource(unittest.TestCase):
    def test_conventions(self):
        s = _qa.strip_comments(_qa.src(os.path.join('ServerStorage', 'PattayaRoadVisBuilder.luau')))
        self.assertIn(':Clone())', s)
        self.assertIn('ModelStreamingMode.Atomic', s)
        self.assertIn('Vector3.new(20000, 0, 0)', s)
        for bad in ('RunService', 'CarController', 'PathfindingService'):
            self.assertNotIn(bad, s)
        # nothing in ShoulderChunks is ever destroyed or re-parented; only pilot / backup are destroyed, and in city
        # mode the batch's own folder (built), its backup (backup) and the emptied containers (root, bk)
        destroys = re.findall(r'(\w+):Destroy\(\)', s)
        self.assertEqual(sorted(set(destroys)), ['backup', 'bk', 'built', 'pilot', 'root'])


if __name__ == '__main__':
    unittest.main()
