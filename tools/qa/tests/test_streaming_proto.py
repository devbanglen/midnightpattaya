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
                'CoastChunks': 48, 'LandmarkChunks': 12, 'ShoulderChunks': 8}
        self.assertEqual({k: f[k]['chunks'] for k in want}, want)
        self.assertLess(abs(f['WideChunks']['max'] - 2142), 2142 * 0.03)
        self.assertEqual(f['Junctions']['total'], 495)
        self.assertEqual(f['ShoulderChunks']['road'], 2536)  # the Sukhumvit shoulder pilot: 8 chunks, 2,536 parts
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
        """C: the client layer holds only non-colliding detail (owner rule: no client-only collision for anything a
        car can hit); every colliding item stays engine-streamed"""
        p = plan('C')
        moved = 0
        for k, name in p['assign']:
            it = p['source'][k]
            if p['containers'][name]['mode'] == 'client':
                self.assertEqual(it.cat, 'detail')
                self.assertFalse(SA.collides(it), it.name)
                moved += 1
            elif it.cat in ('road', 'marking', 'building') or SA.collides(it):
                self.assertNotEqual(p['containers'][name]['mode'], 'client')
        self.assertGreater(moved, 0)

    def test_luau_client_layer_never_collides(self):
        """the Luau planner puts a part with CanCollide / CanTouch into the client layer never; the client clones get
        CanCollide / CanTouch / CanQuery = false; Build fails on a colliding template (CollisionAudit)"""
        s = _qa.strip_comments(_qa.read(PROTO))
        self.assertIn('elseif variant == "C" and not it.collide then', s)
        self.assertIn('collide = d.CanCollide or d.CanTouch', s)
        for prop in ('CanCollide', 'CanTouch', 'CanQuery'):
            self.assertIn('c.%s = false' % prop, s)
        self.assertIn('local audit = P.CollisionAudit()', s)
        self.assertIn('P.Server.check()', s)

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
                rows.append('{x=%r,z=%r,n=%d,cat="%s",root="%s",chunk="%s",collide=%s}' % (
                    it.x + SA.ORIGIN_X, it.z, it.n, it.cat, root, chunk, 'true' if SA.collides(it) else 'false'))
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


def district_rows(p):
    rows = []
    for it in p['source']:
        root = it.chunk.split('/')[0]
        chunk = it.chunk if it.chunk in SA.LOOSE else it.chunk.replace('/', '_')
        rows.append('{x=%r,z=%r,n=%d,cat="%s",root="%s",chunk="%s",collide=%s}' % (
            it.x + SA.ORIGIN_X, it.z, it.n, it.cat, root, chunk, 'true' if SA.collides(it) else 'false'))
    return 'local items = {' + ',\n'.join(rows) + '}\n'


# a minimal Instance tree for the luau CLI (Name / Parent / children / attributes)
MOCK = r"""
local Inst = {}
Inst.__index = Inst
local function new(name, parent)
	local o = setmetatable({Name = name, children = {}, attrs = {}, Parent = nil}, Inst)
	if parent then o.Parent = parent; table.insert(parent.children, o) end
	return o
end
function Inst:FindFirstChild(n) for _, c in self.children do if c.Name == n then return c end end return nil end
function Inst:GetDescendants()
	local out = {}
	local function rec(x) for _, c in x.children do table.insert(out, c); rec(c) end end
	rec(self)
	return out
end
function Inst:Destroy()
	local p = self.Parent
	if p then for i, c in p.children do if c == self then table.remove(p.children, i) break end end end
	self.Parent = nil
end
function Inst:GetFullName()
	local s, p = self.Name, self.Parent
	while p and p.Name ~= "game" do s = p.Name .. "." .. s; p = p.Parent end
	return s
end
function Inst:GetAttributes() return self.attrs end
function Inst:SetAttribute(k, v) self.attrs[k] = v end
local gameRoot = new("game")
workspace = new("Workspace", gameRoot)
local services = {Workspace = workspace, ReplicatedStorage = new("ReplicatedStorage", gameRoot),
	ServerScriptService = new("ServerScriptService", gameRoot), StarterPlayer = new("StarterPlayer", gameRoot),
	RunService = {IsRunning = function() return false end}, HttpService = {}, Players = {}}
new("StarterPlayerScripts", services.StarterPlayer)
game = {GetService = function(_, n) return services[n] end}
script = new("StreamingPrototype")
"""


class PrototypeParityAndRemove(unittest.TestCase):
    def test_parity_a_b(self):
        par = SA.proto_parity(items(), *centre())
        self.assertEqual(par['A'], par['B'])
        self.assertEqual(par['A'], par['C'])
        self.assertEqual(par['A'], par['D'])
        self.assertIn('ShoulderChunks', par['A'])
        self.assertGreater(par['A']['ShoulderChunks'][1], 500)  # the narrowing at about (24550, 900) is in the copy
        for v in ('A', 'B', 'C', 'D'):
            self.assertEqual(sum(n for _, n in par[v].values()), sum(c['n'] for c in plan(v)['containers'].values()))

    def test_shoulders_are_road_layer(self):
        p = plan('B')
        sh = [(k, name) for k, name in p['assign'] if p['source'][k].chunk.startswith('ShoulderChunks/')]
        self.assertTrue(sh)
        for k, name in sh:
            self.assertEqual(p['source'][k].cat, 'road')
            self.assertEqual(p['containers'][name]['layer'], 'road')
            self.assertTrue(name.startswith('Roads/'), name)

    def test_luau_parity_and_leftovers(self):
        """luau CLI: P.Parity / P.ParityText on the district (== Python), then a mock place with every prototype
        instance: Leftovers() lists them, Remove() deletes them and nothing else, Leftovers() is empty after"""
        if not _qa.find_luau('luau'):
            self.skipTest('luau CLI not found')
        src = _qa.read(PROTO)
        main = (_qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau')) + '\n' + MOCK +
                'local P = (function()\n' + src + '\nend)()\n' + district_rows(plan('A')) + r"""
local par = P.Parity(items)
local roots = {}
for r in par.A do table.insert(roots, r) end
table.sort(roots)
for _, r in roots do print("PAR\t" .. r .. "\t" .. par.A[r][2] .. "\t" .. par.B[r][2]) end
local text = P.ParityText(items)
print("PARTEXT\t" .. (string.find(text, "PARITY OK", 1, true) and "ok" or "failed"))
for _, v in {"C", "D"} do
	local same = true
	for r, x in par.A do same = same and par[v][r] ~= nil and par[v][r][2] == x[2] and par[v][r][1] == x[1] end
	print("PARCD\t" .. v .. "\t" .. tostring(same))
end
-- a place with the prototype built (+ things that are not the prototype's)
local RS = game:GetService("ReplicatedStorage")
local world = new("PattayaWorld", workspace)
new("Chunk_1_1", world)
new("PattayaRemotes", RS)
local root = new("StreamingProto", workspace)
new("Ground", root); new("Roads", root)
new("StreamingProtoClient", workspace)
new("StreamingPrototype", RS); new("StreamingProtoRemote", RS); new("StreamingProtoDetail", RS)
new("StreamingProtoBoot", game:GetService("ServerScriptService"))
new("StreamingProtoBootClient", game:GetService("StarterPlayer"):FindFirstChild("StarterPlayerScripts"))
workspace:SetAttribute("StreamProtoTest", 1)
workspace:SetAttribute("LOD_Enabled", true)
local before = P.Leftovers()
local n = 0
for _ in string.gmatch(before, "[^\n]+") do n += 1 end
print("BEFORE\t" .. n)
print("REMOVE\t" .. P.Remove())
print("AFTER\t[" .. P.Leftovers() .. "]")
print("KEPT\t" .. tostring(workspace:FindFirstChild("PattayaWorld") ~= nil and RS:FindFirstChild("PattayaRemotes") ~= nil
    and workspace.attrs.LOD_Enabled == true))
""")
        code, out = _qa.run_luau(main)
        self.assertEqual(code, 0, out[-2000:])
        lines = [ln.split('\t') for ln in out.strip().splitlines()]
        got = {ln[1]: (int(ln[2]), int(ln[3])) for ln in lines if ln[0] == 'PAR'}
        want = SA.proto_parity(items(), *centre())
        self.assertEqual(got, {k: (want['A'][k][1], want['B'][k][1]) for k in want['A']})
        tags = {ln[0]: ln[1:] for ln in lines if ln[0] not in ('PAR', 'PARCD')}
        self.assertEqual([ln[1:] for ln in lines if ln[0] == 'PARCD'], [['C', 'true'], ['D', 'true']])
        self.assertEqual(tags['PARTEXT'], ['ok'])
        self.assertEqual(tags['BEFORE'], ['8'])  # 7 instances + 1 attribute
        self.assertEqual(tags['AFTER'], ['[]'])
        self.assertEqual(tags['KEPT'], ['true'])



class PickRoute(unittest.TestCase):
    """StreamingPrototype.PickRoute on a mock road graph in the luau CLI: the longest route fully inside the
    district with 100% of its 4-stud samples on road wins; a route over a gap is skipped; < 99% fails"""
    GRAPH = r"""
-- 5 x 5 grid, 200 studs apart, map-local (0..800); edges between neighbours
local Route = {nodes = {}, ORIGIN = Vector3.new(20000, 0, 0)}
local idx = {}
for i = 0, 4 do for j = 0, 4 do
	table.insert(Route.nodes, {X = i * 200, Y = j * 200}); idx[i .. "_" .. j] = #Route.nodes
end end
local adj = {}
for i = 0, 4 do for j = 0, 4 do
	local a = idx[i .. "_" .. j]; adj[a] = adj[a] or {}
	for _, d in {{1, 0}, {0, 1}, {-1, 0}, {0, -1}} do
		local b = idx[(i + d[1]) .. "_" .. (j + d[2])]
		if b then table.insert(adj[a], b) end
	end
end end
function Route.toWorld(p, y) return Vector3.new(p.X + 20000, y or 1, p.Y) end
function Route.nearestNode(p, maxDist)
	local best, bd = nil, maxDist
	for i, n in Route.nodes do
		local d = math.sqrt((n.X - p.X) ^ 2 + (n.Y - p.Y) ^ 2)
		if d <= bd then best, bd = i, d end
	end
	return best
end
function Route.dijkstra(s)
	local dist, prev, done = {[s] = 0}, {}, {}
	while true do
		local u, ud = nil, math.huge
		for n, d in dist do if not done[n] and d < ud then u, ud = n, d end end
		if not u then break end
		done[u] = true
		for _, v in adj[u] do
			local nd = ud + 200
			if nd < (dist[v] or math.huge) then dist[v] = nd; prev[v] = u end
		end
	end
	return dist, prev
end
function Route.polylineOf(prev, s, t)
	local pts, n = {}, t
	while n do table.insert(pts, 1, Route.nodes[n]); if n == s then break end; n = prev[n] end
	return pts
end
"""

    def run_pick(self, hole, need=0.99):
        if not _qa.find_luau('luau'):
            self.skipTest('luau CLI not found')
        src = _qa.read(PROTO)
        main = (_qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau')) + '\n' + MOCK +
                'local P = (function()\n' + src + '\nend)()\n' + self.GRAPH + r"""
local hole = %s
local function onRoad(p)  -- p in proto world coordinates (+60000 X, +20000 ORIGIN)
	local x, z = p.X - 80000, p.Z
	for _, h in hole do
		if x >= h[1] and x <= h[2] and z >= h[3] and z <= h[4] then return false end
	end
	return true
end
local r, why = P.PickRoute(Route, onRoad, {-100, 900, -100, 900}, {need = %r, minLen = 200, margin = 40})
if r then
	local ok = true
	for _, q in r.pts do ok = ok and q.X >= -60 and q.X <= 860 and q.Y >= -60 and q.Y <= 860 end
	print("OK\t" .. math.floor(r.len + 0.5) .. "\t" .. r.frac .. "\t" .. tostring(ok))
else
	print("FAIL\t" .. why)
end
""" % (hole, need))
        code, out = _qa.run_luau(main)
        self.assertEqual(code, 0, out[-1500:])
        return out.strip().splitlines()[-1].split('\t')

    def test_longest_full_route(self):
        res = self.run_pick('{}')
        self.assertEqual(res[0], 'OK')
        self.assertEqual(int(res[1]), 1600)  # corner to corner on the grid
        self.assertEqual(float(res[2]), 1.0)
        self.assertEqual(res[3], 'true')

    def test_route_over_a_gap_is_skipped(self):
        # a gap in the road around node (400, 400): the chosen route must avoid it and still be 100% on road
        res = self.run_pick('{{390, 410, 390, 410}}')
        self.assertEqual(res[0], 'OK')
        self.assertEqual(float(res[2]), 1.0)

    def test_fails_below_99_percent(self):
        # every road has a gap somewhere: no route reaches 99%
        res = self.run_pick('{{-200, 1000, 95, 105}, {-200, 1000, 295, 305}, {-200, 1000, 495, 505}, {-200, 1000, 695, 705},'
                            ' {95, 105, -200, 1000}, {295, 305, -200, 1000}, {495, 505, -200, 1000}, {695, 705, -200, 1000}}')
        self.assertEqual(res[0], 'FAIL')
        self.assertIn('on road', res[1])


if __name__ == '__main__':
    unittest.main()
