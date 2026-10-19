-- Circuit definitions -> ready-to-judge circuits. Loads every ModuleScript under ServerStorage.PattayaData.circuits
-- (data only, see docs/CIRCUIT_RACE_SYSTEM.md "Data interface") and precomputes:
--   pts/cum/len    centerline re-indexed so pts[1] is the start/finish line; cum[i] = arc length from it (studs)
--   gates          hidden timing gates every ~90 studs (60-120), gate 1 = start/finish, sector lines are gates too;
--                  each has a CFrame facing the driving direction (forward = -Z, like the loop race gates)
--   sectorS        arc length of the two sector lines
--   pit            pit lane polyline, its entry/exit gates, which track gates it bypasses and where it crosses them
-- and answers nearest-point queries (arc length, signed lateral offset, track width there).
local Registry = {}

Registry.GATE_SPACING = 90
local DEFAULT_WIDTH = 40
local DEFAULT_PIT_WIDTH = 20

local circuits = {} -- [id] = circuit
local list = {}

local function flatUnit(v: Vector3): Vector3
	local f = Vector3.new(v.X, 0, v.Z)
	return if f.Magnitude > 1e-4 then f.Unit else Vector3.new(0, 0, -1)
end

local function readPoints(flat): {Vector3}
	local out = {}
	for i = 1, #flat - 2, 3 do
		table.insert(out, Vector3.new(flat[i], flat[i + 1], flat[i + 2]))
	end
	return out
end

-- index of the segment containing arc length s (cum[k] <= s < cum[k+1]), binary search
local function segmentAt(cum: {number}, s: number): number
	local lo, hi = 1, #cum
	while hi - lo > 1 do
		local mid = (lo + hi) // 2
		if cum[mid] <= s then
			lo = mid
		else
			hi = mid
		end
	end
	return lo
end

function Registry.pointAt(c, s: number): (Vector3, Vector3, number)
	s = s % c.len
	local k = segmentAt(c.cum, s)
	local j = k % c.n + 1
	local segLen = (if k == c.n then c.len else c.cum[k + 1]) - c.cum[k]
	local f = if segLen > 1e-6 then (s - c.cum[k]) / segLen else 0
	local pos = c.pts[k]:Lerp(c.pts[j], f)
	local width = c.widths[k] + (c.widths[j] - c.widths[k]) * f
	return pos, flatUnit(c.pts[j] - c.pts[k]), width
end

-- signed forward distance from a to b along a loop of length len, in (-len/2, len/2]
function Registry.wrapDelta(c, a: number, b: number): number
	local d = (b - a) % c.len
	if d > c.len / 2 then
		d -= c.len
	end
	return d
end

local function project(a: Vector3, b: Vector3, p: Vector3): (number, number, Vector3)
	-- ground-plane projection of p on segment a-b: returns (fraction, distance, dir)
	local ab = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
	local ap = Vector3.new(p.X - a.X, 0, p.Z - a.Z)
	local len2 = ab:Dot(ab)
	local t = if len2 > 1e-8 then math.clamp(ap:Dot(ab) / len2, 0, 1) else 0
	return t, (ap - ab * t).Magnitude, ab
end

-- Nearest centerline point to pos. `hint` = index from the previous call (searches +-60 points around it first).
-- Returns {index, s, lateral (+ = right of the driving direction), dist, width}
function Registry.nearest(c, pos: Vector3, hint: number?)
	local n = c.n
	local function scan(from: number, to: number)
		local best, bestD, bestT = 1, math.huge, 0
		for i = from, to do
			local k = (i - 1) % n + 1
			local t, d = project(c.pts[k], c.pts[k % n + 1], pos)
			if d < bestD then
				best, bestD, bestT = k, d, t
			end
		end
		return best, bestD, bestT
	end
	local k, d, t
	if hint then
		k, d, t = scan(hint - 60, hint + 60)
		if d > 80 then
			k, d, t = scan(1, n)
		end
	else
		k, d, t = scan(1, n)
	end
	local j = k % n + 1
	local a, b = c.pts[k], c.pts[j]
	local dir = flatUnit(b - a)
	local right = dir:Cross(Vector3.yAxis)
	local on = a:Lerp(b, t)
	local segLen = (if k == n then c.len else c.cum[k + 1]) - c.cum[k]
	return {
		index = k,
		s = (c.cum[k] + segLen * t) % c.len,
		lateral = Vector3.new(pos.X - on.X, 0, pos.Z - on.Z):Dot(right),
		dist = d,
		width = c.widths[k] + (c.widths[j] - c.widths[k]) * t,
		y = on.Y,
		dir = dir,
	}
end

-- Distance from pos to the pit lane polyline (math.huge without a pit lane), and the arc length along it.
function Registry.nearestPit(c, pos: Vector3): (number, number)
	local pit = c.pit
	if not pit then
		return math.huge, 0
	end
	local bestD, bestS = math.huge, 0
	for i = 1, #pit.pts - 1 do
		local t, d = project(pit.pts[i], pit.pts[i + 1], pos)
		if d < bestD then
			bestD, bestS = d, pit.cum[i] + (pit.cum[i + 1] - pit.cum[i]) * t
		end
	end
	return bestD, bestS
end

local function makeGate(index: number, pos: Vector3, dir: Vector3, halfWidth: number)
	return {index = index, pos = pos, dir = dir, halfWidth = halfWidth, cf = CFrame.lookAt(pos, pos + dir)}
end

function Registry.compile(def)
	assert(type(def.id) == "string", "circuit def needs an id")
	local raw = readPoints(def.centerline or {})
	assert(#raw >= 8, def.id .. ": centerline needs at least 8 points")
	if (raw[#raw] - raw[1]).Magnitude < 0.5 then
		table.remove(raw) -- closing point repeated
	end
	local n = #raw
	local sf = math.clamp((def.startFinish and def.startFinish.index) or 1, 1, n)
	local function remap(i: number): number
		return (i - sf) % n + 1
	end
	local c = {id = def.id, name = def.name or def.id, def = def, n = n, pts = {}, widths = {}, cum = {}}
	for k = 1, n do
		local i = (sf + k - 2) % n + 1
		c.pts[k] = raw[i]
		c.widths[k] = (def.width and def.width[i]) or def.trackWidth or DEFAULT_WIDTH
	end
	c.cum[1] = 0
	for k = 2, n do
		c.cum[k] = c.cum[k - 1] + (c.pts[k] - c.pts[k - 1]).Magnitude
	end
	c.len = c.cum[n] + (c.pts[1] - c.pts[n]).Magnitude
	c.lengthStuds = def.lengthStuds or math.floor(c.len)

	-- sectors: two lines -> three sectors; default thirds
	local s1, s2 = c.len / 3, c.len * 2 / 3
	if def.sectors and #def.sectors >= 2 then
		s1, s2 = c.cum[remap(def.sectors[1])], c.cum[remap(def.sectors[2])]
		if s1 > s2 then
			s1, s2 = s2, s1
		end
	end
	c.sectorS = {s1, s2}

	-- gates: each sector span is split evenly, so every sector line is exactly a gate
	c.gates = {}
	local spans = {{0, s1}, {s1, s2}, {s2, c.len}}
	for sector, span in spans do
		local a, b = span[1], span[2]
		local m = math.max(1, math.floor((b - a) / Registry.GATE_SPACING + 0.5))
		for j = 0, m - 1 do
			local s = a + (b - a) * j / m
			local pos, dir, width = Registry.pointAt(c, s)
			local g = makeGate(#c.gates + 1, pos, dir, width / 2)
			g.s = s
			if j == 0 then
				g.line = sector -- 1 = start/finish (ends sector 3 and the lap), 2 = ends sector 1, 3 = ends sector 2
			end
			table.insert(c.gates, g)
		end
	end

	-- grid slots: {x, y, z, dx, dz}, y = surface height
	c.grid = {}
	for _, s in def.grid or {} do
		local at = Vector3.new(s.x or s[1], s.y or s[2], s.z or s[3]) -- named (bira.luau) or positional slots
		local dir = flatUnit(Vector3.new(s.dx or s[4] or 0, 0, s.dz or s[5] or -1))
		table.insert(c.grid, CFrame.lookAt(at, at + dir))
	end
	if #c.grid == 0 then -- fallback: two columns behind the line
		local _, dir = Registry.pointAt(c, 0)
		for i = 1, 12 do
			local row, col = (i - 1) // 2, (i - 1) % 2
			local at = Registry.pointAt(c, c.len - 14 - row * 18)
			at += dir:Cross(Vector3.yAxis) * (if col == 0 then -8 else 8)
			table.insert(c.grid, CFrame.lookAt(at, at + dir))
		end
	end

	if def.entrance then
		local e = def.entrance
		local at = Vector3.new(e.x, (e.y or c.pts[1].Y), e.z)
		c.entrance = CFrame.lookAt(at, at + flatUnit(Vector3.new(e.dx or 1, 0, e.dz or 0)))
	else
		c.entrance = c.grid[#c.grid]
	end

	-- pit lane
	local pitPts = if def.pitLane then readPoints(def.pitLane) else {}
	if #pitPts >= 2 then
		local pit = {pts = pitPts, cum = {0}, width = def.pitWidth or def.pitLaneWidth or DEFAULT_PIT_WIDTH,
			limit = def.pitSpeedLimit or 60}
		for i = 2, #pitPts do
			pit.cum[i] = pit.cum[i - 1] + (pitPts[i] - pitPts[i - 1]).Magnitude
		end
		pit.len = pit.cum[#pitPts]
		-- entry/exit gates sit where the pit lane is clearly away from the track (so a car running wide on the
		-- track can't trip them): the first/last pit point farther than track half width + pit width + 8
		local function clearOfTrack(p: Vector3): boolean
			local near = Registry.nearest(c, p)
			return near.dist > near.width / 2 + pit.width / 2 + 8
		end
		local entryI, exitI = nil, nil
		for i = 1, #pitPts do
			if clearOfTrack(pitPts[i]) then
				entryI = i
				break
			end
		end
		for i = #pitPts, 1, -1 do
			if clearOfTrack(pitPts[i]) then
				exitI = i
				break
			end
		end
		entryI = entryI or math.max(1, #pitPts // 4)
		exitI = exitI or math.max(entryI, #pitPts - #pitPts // 4)
		local function pitGate(i: number)
			local a = pitPts[math.max(1, i - 1)]
			local b = pitPts[math.min(#pitPts, i + 1)]
			return makeGate(0, pitPts[i], flatUnit(b - a), pit.width / 2 + 3)
		end
		pit.entryGate = pitGate(entryI)
		pit.exitGate = pitGate(exitI)
		pit.entryS, pit.exitS = pit.cum[entryI], pit.cum[exitI]
		-- track part bypassed by the pit lane (between the centerline points where it leaves and rejoins)
		local entryIdx = def.pitEntryIndex and remap(def.pitEntryIndex) or Registry.nearest(c, pitPts[1]).index
		local exitIdx = def.pitExitIndex and remap(def.pitExitIndex) or Registry.nearest(c, pitPts[#pitPts]).index
		pit.trackEntryS, pit.trackExitS = c.cum[entryIdx], c.cum[exitIdx]
		local bypassLen = (pit.trackExitS - pit.trackEntryS) % c.len
		for _, g in c.gates do
			local d = (g.s - pit.trackEntryS) % c.len
			if d > 0 and d < bypassLen then
				g.inBypass = true
				-- where the pit lane crosses this gate's plane (lateral offset in the gate's frame), if near
				local best = nil
				for i = 1, #pitPts - 1 do
					local ra = g.cf:PointToObjectSpace(pitPts[i])
					local rb = g.cf:PointToObjectSpace(pitPts[i + 1])
					if (ra.Z > 0) ~= (rb.Z > 0) then
						local hit = ra:Lerp(rb, ra.Z / (ra.Z - rb.Z))
						if math.abs(hit.X) < 150 and (not best or math.abs(hit.X) < math.abs(best)) then
							best = hit.X
						end
					end
				end
				g.pitLat = best
			end
		end
		c.pit = pit
	end
	return c
end

-- Loads every circuit ModuleScript in `folder` (bad ones are skipped with a warning). Returns the list.
function Registry.load(folder: Instance)
	for _, m in folder:GetChildren() do
		if m:IsA("ModuleScript") then
			local ok, res = pcall(function()
				return Registry.compile(require(m))
			end)
			if ok then
				circuits[res.id] = res
				table.insert(list, res)
			else
				warn("[Circuit] skipped " .. m.Name .. ": " .. tostring(res))
			end
		end
	end
	table.sort(list, function(a, b) return a.id < b.id end)
	return list
end

function Registry.get(id: string)
	return circuits[id]
end

function Registry.all()
	return list
end

-- The circuit a position is at (within `range` studs of its centerline or paddock entrance), or nil.
function Registry.at(pos: Vector3, range: number)
	for _, c in list do
		if (c.entrance.Position - pos).Magnitude < range then
			return c
		end
		local near = Registry.nearest(c, pos)
		if near.dist < range then
			return c
		end
	end
	return nil
end

return Registry
