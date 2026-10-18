--!strict
-- Builds a circuit venue in Studio (edit time) from a data-driven definition (roblox/data/circuits/<id>.luau, made by
-- tools/circuit/bira_circuit.py). Definition coordinates are WORLD studs (no ORIGIN offset is added here).
-- Rebuilding replaces workspace.Circuit_<id> only; terrain under the venue is refilled when terrain ~= false.
--   local def = require(game.ServerStorage.CircuitData.bira)
--   require(game.ServerStorage.CircuitBuilder).Build(def)
--   require(game.ServerStorage.CircuitBuilder).Build(def, {terrain = false, lights = false})
-- Everything is anchored SmoothPlastic (the template's MaterialService overrides Asphalt/Concrete). Not yet run in
-- Studio: see docs/BIRA_CIRCUIT_DESIGN.md "Builder assumptions" before the first build.
local Builder = {}

local SLAB = 4.0 -- thickness of track / run-off / road slabs (their tops are what the cars ride on)
local RUNOFF_DROP = 0.6 -- run-off top below the asphalt: grass verge, never above the track (see EXT_MAX)
local PIT_DROP = 0.02 -- pit lane top below the asphalt where they overlap at the merges
local SERVICE_DROP = 0.04
local CURB_H = 0.1 -- curb top above the asphalt: low and flat so raycast wheels roll over it
local CURB_THICK = 0.6
local WALL_H = 3.6 -- ~1 m concrete barrier
local WALL_T = 1.2
local OVERLAP = 0.3 -- studs each strip part is lengthened at both ends so joints never open
local EXT_MAX = 12 -- studs: cap on the bend extension of a strip part. A wide slab extended by half its width keeps its
-- own pitch, so on a sloping bend its tail rose up to 4 studs above the next part (seen at Bira T2 in Studio)
local MERGE_TOL = 0.08 -- studs: consecutive centreline points this close to a straight 3D line share one part
local MERGE_MAX = 60 -- studs: longest merged part
local POLE_H = 70
local BATCH = 200 -- parts per task.wait()
local SHOULDER_W = 16 -- studs: sloped plank from a road/plaza edge down to the verge (render_venue.py SHOULDER)
local SHOULDER_DROP = 2.5 -- studs it falls over SHOULDER_W (about 9 degrees): a car that runs off rolls back up
-- Roblox lights reach at most 60 studs, so a 70-stud pole head can't light the asphalt by itself: each pole also gets
-- invisible beam emitters over the near track edge (FloodLight=true like the head, so the night script enables them)
local BEAM_H = 32 -- emitter height above the track
local BEAM_SPREAD = 70 -- studs between the emitters of one pole, along the track

local COLORS: {[string]: Color3} = {
	track = Color3.fromRGB(52, 53, 58),
	pit = Color3.fromRGB(62, 63, 68),
	runoff = Color3.fromRGB(96, 140, 72),
	curbRed = Color3.fromRGB(200, 30, 35),
	curbWhite = Color3.fromRGB(240, 240, 240),
	wall = Color3.fromRGB(196, 196, 190),
	pitWall = Color3.fromRGB(230, 230, 230),
	line = Color3.fromRGB(245, 245, 245),
	road = Color3.fromRGB(46, 47, 52),
	parking = Color3.fromRGB(78, 79, 84),
	paddock = Color3.fromRGB(150, 150, 150),
	pit_garage = Color3.fromRGB(225, 228, 232),
	race_control = Color3.fromRGB(40, 60, 90),
	grandstand = Color3.fromRGB(170, 175, 185),
	seats = Color3.fromRGB(30, 90, 170),
	roof = Color3.fromRGB(120, 124, 130),
	pole = Color3.fromRGB(70, 72, 78),
	lamp = Color3.fromRGB(255, 244, 214),
	board = Color3.fromRGB(250, 250, 250),
	verge = Color3.fromRGB(104, 146, 78),
	bay = Color3.fromRGB(235, 235, 235),
	roadSign = Color3.fromRGB(0, 105, 62),
	pylon = Color3.fromRGB(24, 32, 64),
	paddockSign = Color3.fromRGB(0, 150, 190),
	tent = Color3.fromRGB(235, 236, 240),
	glassDay = Color3.fromRGB(46, 58, 72), -- window bands by day; NightNeon turns them into warm light at night
	glassNight = Color3.fromRGB(255, 214, 150),
	lampDay = Color3.fromRGB(200, 200, 192),
}
local FLAG_COLORS = {Color3.fromRGB(220, 30, 40), Color3.fromRGB(245, 245, 245), Color3.fromRGB(20, 60, 160),
	Color3.fromRGB(255, 200, 0)}

-- NightNeon: PattayaNightLights sets Material = Neon and Color = NightColor at night, and SmoothPlastic + DayColor by
-- day, for every BasePart with this attribute (window bands, lamp heads)
local function nightNeon(p: BasePart, dayColor: Color3, nightColor: Color3)
	p.Color = dayColor
	p:SetAttribute("NightNeon", true)
	p:SetAttribute("DayColor", dayColor)
	p:SetAttribute("NightColor", nightColor)
end

local built = 0
local function newPart(parent: Instance, name: string, size: Vector3, cf: CFrame, color: Color3, collide: boolean): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Material = Enum.Material.SmoothPlastic
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.CanCollide = collide
	p.CanQuery = collide -- decoration stays out of the car's suspension raycasts
	p.CanTouch = false
	p.CastShadow = false
	p.Parent = parent
	built += 1
	if built % BATCH == 0 then
		task.wait() -- keep Studio responsive during the build
	end
	return p
end

local function model(parent: Instance, name: string): Model
	local m = Instance.new("Model")
	m.Name = name
	m.Parent = parent
	return m
end

local function toV3(flat: {number}): {Vector3}
	local pts = table.create(#flat // 3)
	for i = 1, #flat, 3 do
		table.insert(pts, Vector3.new(flat[i], flat[i + 1], flat[i + 2]))
	end
	return pts
end

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

-- horizontal right-hand normals (side = 1) of a polyline; closed loops wrap around
local function normals(pts: {Vector3}, closed: boolean): {Vector3}
	local n = #pts
	local out = table.create(n)
	for i = 1, n do
		local a = if i > 1 then pts[i - 1] elseif closed then pts[n] else pts[i]
		local b = if i < n then pts[i + 1] elseif closed then pts[1] else pts[i]
		local t = flat(b - a)
		t = if t.Magnitude > 1e-6 then t.Unit else Vector3.xAxis
		out[i] = Vector3.new(-t.Z, 0, t.X)
	end
	return out
end

-- indices of the points kept after merging nearly straight runs (3D), never longer than MERGE_MAX or across a width
-- change; first and last are always kept (for closed loops the caller appends the first point again)
local function simplify(pts: {Vector3}, widths: {number}?): {number}
	local keep = {1}
	local i, n = 1, #pts
	while i < n do
		local j = i + 1
		while j < n do
			local a, c = pts[i], pts[j + 1]
			local ac = c - a
			local len = ac.Magnitude
			if len > MERGE_MAX then break end
			local ok = true
			for k = i + 1, j do
				local ap = pts[k] - a
				local off = (ap - ac.Unit * ap:Dot(ac.Unit)).Magnitude
				if off > MERGE_TOL or (widths and math.abs(widths[k] - widths[i]) > 0.3) then
					ok = false
					break
				end
			end
			if not ok or (widths and math.abs(widths[j + 1] - widths[i]) > 0.3) then break end
			j += 1
		end
		table.insert(keep, j)
		i = j
	end
	return keep
end

-- slab strip along a 3D polyline: one part per (merged) segment, top face through the points, pitched with the
-- slope, no roll. Each end is lengthened by the outer-edge gap of the horizontal bend (+ OVERLAP), so curved joints
-- stay closed and consecutive tops meet without a step (they cross exactly at the shared point).
local function strip(parent: Instance, name: string, pts: {Vector3}, widths: {number}, drop: number, thick: number,
	color: Color3, collide: boolean): {Part}
	local made = {}
	local keep = simplify(pts, widths)
	local m = #keep
	local q = table.create(m)
	for k, idx in keep do
		q[k] = pts[idx]
	end
	local ext = table.create(m, OVERLAP)
	for k = 2, m - 1 do
		local d1, d2 = flat(q[k] - q[k - 1]), flat(q[k + 1] - q[k])
		if d1.Magnitude > 1e-6 and d2.Magnitude > 1e-6 then
			local turn = math.acos(math.clamp(d1.Unit:Dot(d2.Unit), -1, 1))
			ext[k] = math.min(widths[keep[k]] / 2 * math.tan(turn / 2), widths[keep[k]] / 2, EXT_MAX) + OVERLAP
		end
	end
	for k = 1, m - 1 do
		local a, b = q[k], q[k + 1]
		local seg = b - a
		if seg.Magnitude > 0.05 then
			local dir = seg.Unit
			local a2, b2 = a - dir * ext[k], b + dir * ext[k + 1]
			local mid = (a2 + b2) / 2 - Vector3.new(0, drop, 0)
			local w = math.max(widths[keep[k]], widths[keep[k + 1]])
			local cf = CFrame.lookAt(mid, mid + dir) * CFrame.new(0, -thick / 2, 0)
			table.insert(made, newPart(parent, name, Vector3.new(w, thick, (b2 - a2).Magnitude), cf, color, collide))
		end
	end
	return made
end

-- Lowers each slab so its top never rises above any of the given surface points inside the slab's footprint (plus
-- `margin`). Wide pitched rectangles on a bend that also climbs or drops can't follow both: a far corner can end up
-- above the track (seen at Bira T2: a run-off slab 4 studs over the asphalt). Points are checked with their lateral
-- offsets (centre and both track edges).
local function sinkBelow(parts: {Part}, pts: {Vector3}, nrm: {Vector3}, halfWidths: {number}, margin: number)
	for _, part in parts do
		local cf, sz = part.CFrame, part.Size
		local lower = 0
		for i, p in pts do
			local hw = halfWidths[i]
			for _, off in {0, hw, -hw} do
				local q = p + nrm[i] * off
				local l = cf:PointToObjectSpace(q)
				if math.abs(l.X) <= sz.X / 2 + 1 and math.abs(l.Z) <= sz.Z / 2 + 1 then
					local excess = (sz.Y / 2 - l.Y) + margin -- top plane above the point by this much (along the part's up)
					if excess > lower then lower = excess end
				end
			end
		end
		if lower > 0 then
			part.CFrame = cf * CFrame.new(0, -lower, 0)
		end
	end
end

-- wall/curb piece between two offset points (thin things: shared end points + OVERLAP, no bend extension)
local function piece(parent: Instance, name: string, a: Vector3, b: Vector3, w: number, h: number, color: Color3,
	collide: boolean): Part?
	local seg = b - a
	if seg.Magnitude < 0.05 then return nil end
	local dir = seg.Unit
	local mid = (a + b) / 2
	local cf = CFrame.lookAt(mid, mid + dir) * CFrame.new(0, h / 2, 0)
	return newPart(parent, name, Vector3.new(w, h, seg.Magnitude + OVERLAP * 2), cf, color, collide)
end

local function closedRange(from: number, to: number, n: number): {number}
	local out = {}
	local i = from
	while true do
		table.insert(out, i)
		if i == to then break end
		i = i % n + 1
		if #out > n then break end
	end
	return out
end

-- track surface, run-off underneath (one wide slab per segment, shifted to cover both barrier offsets), lines
local function buildTrack(root: Instance, def: any, c: {Vector3}, nrm: {Vector3})
	local n = #c
	local loopPts = table.clone(c)
	table.insert(loopPts, c[1])
	local widths = table.clone(def.width)
	table.insert(widths, def.width[1])
	local track = model(root, "Track")
	track:SetAttribute("LengthStuds", def.lengthStuds)
	strip(track, "Asphalt", loopPts, widths, 0, SLAB, COLORS.track, true)

	-- run-off: from barrier to barrier (or the default run-off where a side has no barrier)
	local runoff = model(root, "Runoff")
	local rp, rw = table.create(n + 1), table.create(n + 1)
	for i = 1, n do
		local w = def.width[i] / 2
		local r = if def.barrierRight[i] > 0 then def.barrierRight[i] else w + def.runoffDefault
		local l = if def.barrierLeft[i] > 0 then def.barrierLeft[i] else w + def.runoffDefault
		rp[i] = c[i] + nrm[i] * ((r - l) / 2)
		rw[i] = r + l + 2
	end
	rp[n + 1], rw[n + 1] = rp[1], rw[1]
	local runoffParts = strip(runoff, "Runoff", rp, rw, RUNOFF_DROP, SLAB, COLORS.runoff, true)
	local hw = table.create(n)
	for i = 1, n do hw[i] = def.width[i] / 2 end
	sinkBelow(runoffParts, c, nrm, hw, RUNOFF_DROP)
	task.wait()

	-- white edge lines (decoration, not queried)
	local lines = model(root, "Lines")
	for _, side in {-1, 1} do
		local lp = table.create(n + 1)
		local lw = table.create(n + 1, 0.8)
		for i = 1, n do
			lp[i] = c[i] + nrm[i] * side * (def.width[i] / 2 - 1.2) + Vector3.new(0, 0.03, 0)
		end
		lp[n + 1] = lp[1]
		for _, p in strip(lines, "EdgeLine", lp, lw, 0, 0.05, COLORS.line, false) do
			p.CanQuery = false
		end
	end
	-- start/finish line + sector lines on the asphalt
	local function across(i: number, name: string, color: Color3, thick: number)
		local j = i % n + 1
		local dir = (c[j] - c[i]).Unit
		local cf = CFrame.lookAt(c[i], c[i] + dir) * CFrame.new(0, 0.03, 0)
		local p = newPart(lines, name, Vector3.new(def.width[i], 0.05, thick), cf, color, false)
		p.CanQuery = false
	end
	across(def.startFinish.index, "StartFinish", COLORS.line, 3)
	for k, i in def.sectors do
		across(i, "Sector" .. k, Color3.fromRGB(255, 210, 0), 1)
	end
end

local function buildCurbs(root: Instance, def: any, c: {Vector3}, nrm: {Vector3})
	local n = #c
	local curbs = model(root, "Curbs")
	local cw = def.curbWidth
	for ci, k in def.curbs do
		local idx = closedRange(k.from, k.to, n)
		local function at(i: number): Vector3
			-- inner edge overlaps the asphalt edge by 0.5 stud; top CURB_H above the local surface
			return c[i] + nrm[i] * k.side * (def.width[i] / 2 + cw / 2 - 0.5) + Vector3.new(0, CURB_H - CURB_THICK, 0)
		end
		for t = 1, #idx - 1 do
			local color = if t % 2 == 0 then COLORS.curbWhite else COLORS.curbRed
			piece(curbs, "Curb" .. ci, at(idx[t]), at(idx[t + 1]), cw, CURB_THICK, color, true)
		end
	end
end

local function buildBarriers(root: Instance, def: any, c: {Vector3}, nrm: {Vector3})
	local n = #c
	local walls = model(root, "Barriers")
	for _, side in {1, -1} do
		local off = if side == 1 then def.barrierRight else def.barrierLeft
		local run: {Vector3} = {}
		local function flush()
			if #run >= 2 then
				local keep = simplify(run, nil)
				for k = 1, #keep - 1 do
					piece(walls, "Barrier", run[keep[k]], run[keep[k + 1]], WALL_T, WALL_H, COLORS.wall, true)
				end
			end
			run = {}
		end
		-- start scanning at a gap if there is one, so runs don't break at index 1
		local start = 1
		for i = 1, n do
			if off[i] <= 0 then
				start = i
				break
			end
		end
		for t = 0, n do
			local i = (start - 1 + t) % n + 1
			if off[i] > 0 then
				table.insert(run, c[i] + nrm[i] * side * off[i] - Vector3.new(0, RUNOFF_DROP + 0.5, 0))
			else
				flush()
			end
		end
		flush()
	end
end

local function buildPit(root: Instance, def: any)
	local pts = toV3(def.pitLane)
	if #pts < 2 then return end
	local pit = model(root, "PitLane")
	pit:SetAttribute("PitSpeedLimit", def.pitSpeedLimit)
	pit:SetAttribute("PitEntryIndex", def.pitEntryIndex)
	pit:SetAttribute("PitExitIndex", def.pitExitIndex)
	strip(pit, "PitLane", pts, table.create(#pts, def.pitLaneWidth), PIT_DROP, SLAB, COLORS.pit, true)
	-- garage-side white line
	local nrm = normals(pts, false)
	local lp = table.create(#pts)
	for i, p in pts do
		lp[i] = p + nrm[i] * def.pitSide * (def.pitLaneWidth / 2 - 1.5) + Vector3.new(0, 0.03 - PIT_DROP, 0)
	end
	for _, p in strip(pit, "PitLine", lp, table.create(#lp, 0.8), 0, 0.05, COLORS.line, false) do
		p.CanQuery = false
	end
end

local function buildGrid(root: Instance, def: any)
	local grid = model(root, "Grid")
	grid.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	for i, s in def.grid do
		local pos = Vector3.new(s.x, s.y + 0.06, s.z)
		local slot = newPart(grid, "Slot" .. i, Vector3.new(9, 0.1, 17), CFrame.lookAt(pos, pos + Vector3.new(s.dx, 0, s.dz)), COLORS.line, false)
		slot.Transparency = 0.5
		slot.CanQuery = false
		slot:SetAttribute("Slot", i)
	end
end

local function sign(part: BasePart, text: string, face: Enum.NormalId, textColor: Color3?, glow: boolean?)
	local gui = Instance.new("SurfaceGui")
	gui.Face = face
	gui.CanvasSize = Vector2.new(math.max(part.Size.X, 1) * 20, math.max(part.Size.Y, 1) * 20)
	gui.LightInfluence = if glow then 0 else 1 -- glowing signs stay readable at night
	gui.Parent = part
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(0.92, 0.84)
	label.Position = UDim2.fromScale(0.04, 0.08)
	label.BackgroundTransparency = 1
	label.Text = text
	label.TextScaled = true
	label.Font = Enum.Font.GothamBold
	label.TextColor3 = textColor or Color3.fromRGB(20, 20, 20)
	label.Parent = gui
end

local function buildBoards(root: Instance, def: any, c: {Vector3})
	local n = #c
	local boards = model(root, "BrakeBoards")
	for _, b in def.brakeMarkers do
		local i = b.index
		local fwd = flat(c[i % n + 1] - c[i]).Unit
		local base = Vector3.new(b.x, b.y, b.z)
		-- the post reaches 2 studs under the track height: the run-off it stands on is 0.6 lower than the asphalt
		newPart(boards, "Post", Vector3.new(0.6, 10, 0.6), CFrame.new(base + Vector3.new(0, 3, 0)), COLORS.pole, true)
		local pos = base + Vector3.new(0, 8, 0)
		local board = newPart(boards, "Board" .. b.dist, Vector3.new(7, 5, 0.4), CFrame.lookAt(pos, pos - fwd), COLORS.board, false)
		board.CanQuery = false
		sign(board, tostring(b.dist), Enum.NormalId.Front)
	end
end

local function buildLights(root: Instance, def: any)
	local lights = model(root, "Floodlights")
	for i, f in def.floodlights do
		local base = Vector3.new(f.x, f.y, f.z)
		newPart(lights, "Pole", Vector3.new(1.6, POLE_H + 6, 1.6), CFrame.new(base + Vector3.new(0, POLE_H / 2 - 3, 0)), COLORS.pole, true)
		local head = base + Vector3.new(0, POLE_H, 0)
		local aim = head + Vector3.new(f.dx, -1.1, f.dz) -- towards the track and down
		local lamp = newPart(lights, "FloodLight", Vector3.new(10, 4, 1.5), CFrame.lookAt(head, aim), COLORS.lamp, false)
		lamp.CanQuery = false
		lamp:SetAttribute("FloodLight", true) -- the night system enables the SpotLight in parts with this attribute
		lamp:SetAttribute("Index", i)
		nightNeon(lamp, COLORS.lampDay, COLORS.lamp) -- the lamp face glows at night
		local spot = Instance.new("SpotLight")
		spot.Face = Enum.NormalId.Front
		spot.Angle = 100
		spot.Range = 60
		spot.Brightness = 3
		spot.Color = COLORS.lamp
		spot.Shadows = false
		spot.Enabled = false
		spot.Parent = lamp
		-- beam emitters over the near track edge (reach = pole to centreline, hw = half track width, from the data)
		local dir = Vector3.new(f.dx, 0, f.dz).Unit
		local along = Vector3.new(-dir.Z, 0, dir.X)
		local edge = base + dir * ((f.reach or 60) - (f.hw or 21))
		for k = -1, 1 do
			local at = edge + along * k * BEAM_SPREAD + Vector3.new(0, BEAM_H, 0)
			local target = at + dir * (f.hw or 21) - Vector3.new(0, BEAM_H, 0)
			local beam = newPart(lights, "FloodBeam", Vector3.new(1, 1, 1), CFrame.lookAt(at, target), COLORS.lamp, false)
			beam.Transparency = 1
			beam.CanQuery = false
			beam:SetAttribute("FloodLight", true)
			beam:SetAttribute("Index", i)
			local s = Instance.new("SpotLight")
			s.Face = Enum.NormalId.Front
			s.Angle = 110
			s.Range = 60
			s.Brightness = 1.6
			s.Color = COLORS.lamp
			s.Shadows = false
			s.Enabled = false
			s.Parent = beam
		end
	end
end

local FOOTING = 14 -- buildings reach this far below their base so slopes never leave them floating

local function buildBuildings(root: Instance, def: any, c: {Vector3})
	local blds = model(root, "Buildings")
	local pit = toV3(def.pitLane)
	for _, b in def.buildings do
		local rot = CFrame.Angles(0, -math.rad(b.yaw), 0)
		local m = model(blds, b.kind)
		m:SetAttribute("Verified", b.verified)
		m:SetAttribute("Source", b.source)
		if b.kind == "paddock" then
			newPart(m, "Apron", Vector3.new(b.w, SLAB, b.d), CFrame.new(b.x, b.y + 0.05 - SLAB / 2, b.z) * rot, COLORS.paddock, true)
		elseif b.kind == "grandstand" then
			-- base block + seating wedge; the wedge's sloped face looks toward the nearest track point (low side front)
			local centre = Vector3.new(b.x, b.y, b.z)
			local best, bd = c[1], math.huge
			for _, p in c do
				local d = (flat(p) - flat(centre)).Magnitude
				if d < bd then best, bd = p, d end
			end
			local u = (rot * Vector3.xAxis)
			local v = (rot * Vector3.zAxis)
			local toTrack = flat(best - centre).Unit
			local front = if math.abs(toTrack:Dot(u)) > math.abs(toTrack:Dot(v)) then u * math.sign(toTrack:Dot(u)) else v * math.sign(toTrack:Dot(v))
			local depth = if front == u or front == -u then b.w else b.d
			local width = if front == u or front == -u then b.d else b.w
			local baseH = b.h * 0.3
			local bcf = CFrame.lookAt(centre, centre + front) * CFrame.new(0, (baseH - FOOTING) / 2, 0)
			newPart(m, "Base", Vector3.new(width, baseH + FOOTING, depth), bcf, COLORS.grandstand, true)
			local wcf = CFrame.lookAt(centre, centre + front) * CFrame.new(0, baseH + (b.h - baseH) / 2, 0)
			local wedge = Instance.new("WedgePart")
			wedge.Name = "Seats"
			wedge.Anchored = true
			wedge.Size = Vector3.new(width, b.h - baseH, depth)
			wedge.CFrame = wcf
			wedge.Color = COLORS.seats
			wedge.Material = Enum.Material.SmoothPlastic
			wedge.CastShadow = false
			wedge.Parent = m
			-- roof over the back 70% of the seats (local +Z is the back, away from the track), carried by columns that
			-- stand on the ground just behind the back edge (they used to hang in the air 5% of the depth behind it)
			local look = CFrame.lookAt(centre, centre + front)
			local roofCf = look * CFrame.new(0, b.h + 10, depth * 0.15 + 1.5)
			local roof = newPart(m, "Roof", Vector3.new(width + 4, 1, depth * 0.7 + 3), roofCf, COLORS.roof, false)
			roof.CanQuery = false
			local colH = b.h + 10 + FOOTING
			for _, s in {-1, 0, 1} do
				newPart(m, "Column", Vector3.new(1.5, colH, 1.5),
					look * CFrame.new(s * (width / 2 - 1), b.h + 9.5 - colH / 2, depth / 2 + 1), COLORS.pole, true)
			end
		else
			local color = COLORS[b.kind] or COLORS.pit_garage
			local cf = CFrame.new(b.x, b.y + (b.h - FOOTING) / 2, b.z) * rot
			newPart(m, "Body", Vector3.new(b.w, b.h + FOOTING, b.d), cf, color, true)
			local roof = newPart(m, "Roof", Vector3.new(b.w + 2, 1, b.d + 2), CFrame.new(b.x, b.y + b.h + 0.5, b.z) * rot, COLORS.roof, false)
			roof.CanQuery = false
			local base = CFrame.new(b.x, b.y, b.z) * rot
			local function band(name: string, s: number, y0: number, hgt: number, color: Color3): Part
				local p = newPart(m, name, Vector3.new(b.w - 4, hgt, 0.2), base * CFrame.new(0, y0 + hgt / 2, s * (b.d / 2 + 0.1)), color, false)
				p.CanQuery = false
				return p
			end
			if b.kind == "pit_garage" then
				-- garage doors open toward the pit lane (or the track for a garage far from it, e.g. the kart pit);
				-- an office window band above the doors and along the back, lit at night
				local ctr = Vector3.new(b.x, 0, b.z)
				local target, best = nil :: Vector3?, 150
				for _, p in pit do
					local dd = (flat(p) - ctr).Magnitude
					if dd < best then target, best = flat(p), dd end
				end
				if not target then
					local bd = math.huge
					for _, p in c do
						local dd = (flat(p) - ctr).Magnitude
						if dd < bd then target, bd = flat(p), dd end
					end
				end
				local v = rot * Vector3.zAxis
				local s = if ((target :: Vector3) - ctr):Dot(v) > 0 then 1 else -1
				m:SetAttribute("DoorSide", s)
				band("Doors", s, 0, b.h * 0.55, Color3.fromRGB(60, 64, 72))
				nightNeon(band("Windows", s, b.h * 0.66, b.h * 0.16, COLORS.glassDay), COLORS.glassDay, COLORS.glassNight)
				nightNeon(band("Windows", -s, b.h * 0.5, b.h * 0.2, COLORS.glassDay), COLORS.glassDay, COLORS.glassNight)
			elseif b.kind == "race_control" then
				-- glazed control room on all four sides
				for _, s in {-1, 1} do
					nightNeon(band("Windows", s, b.h * 0.55, b.h * 0.3, COLORS.glassDay), COLORS.glassDay, COLORS.glassNight)
					local side = newPart(m, "Windows", Vector3.new(0.2, b.h * 0.3, b.d - 4),
						base * CFrame.new(s * (b.w / 2 + 0.1), b.h * 0.7, 0), COLORS.glassDay, false)
					side.CanQuery = false
					nightNeon(side, COLORS.glassDay, COLORS.glassNight)
				end
			end
		end
	end
end

local function buildAccess(root: Instance, def: any)
	local access = model(root, "Access")
	access:SetAttribute("JoinNode", def.access.joinNode)
	access:SetAttribute("CorridorGraph", def.access.corridorGraph)
	local pts = toV3(def.access.pts)
	if #pts >= 2 then
		strip(access, "TransitionRoad", pts, table.create(#pts, def.access.width), 0, SLAB, COLORS.road, true)
	end
	for _, r in def.serviceRoads do
		local sp = toV3(r.pts)
		if #sp >= 2 then
			strip(access, "ServiceRoad", sp, table.create(#sp, r.width), SERVICE_DROP, SLAB, COLORS.road, true)
		end
	end
	for _, p in def.parking do
		local cf = CFrame.new(p.x, p.y + 0.02 - SLAB / 2, p.z) * CFrame.Angles(0, -math.rad(p.yaw), 0)
		local slab = newPart(access, "Parking", Vector3.new(p.w, SLAB, p.d), cf, COLORS.parking, true)
		slab:SetAttribute("Verified", p.verified)
	end
	-- entrance arch over the transition road at the gate (descriptive name only, no logos)
	local e = def.entrance
	local pos = Vector3.new(e.x, e.y, e.z)
	local fwd = Vector3.new(e.dx, 0, e.dz).Unit
	local side = Vector3.new(-fwd.Z, 0, fwd.X)
	local span = def.access.width + 8
	for _, s in {-1, 1} do
		newPart(access, "GatePost", Vector3.new(2, 24, 2), CFrame.new(pos + side * s * span / 2 + Vector3.new(0, 12, 0)), COLORS.pole, true)
	end
	local beamPos = pos + Vector3.new(0, 24, 0)
	local beam = newPart(access, "GateSign", Vector3.new(span + 2, 5, 1), CFrame.lookAt(beamPos, beamPos - fwd), COLORS.board, false)
	beam.CanQuery = false
	sign(beam, def.name, Enum.NormalId.Front)
end

local function yawCf(x: number, y: number, z: number, yaw: number): CFrame
	return CFrame.new(x, y, z) * CFrame.Angles(0, -math.rad(yaw), 0)
end

-- sloped plank along an edge: its top runs from just under the edge (y - 0.05) down SHOULDER_DROP over SHOULDER_W,
-- outward. A plain pitched Part (no WedgePart orientation to get wrong).
local function shoulder(parent: Instance, sh: any)
	local a = Vector3.new(sh.ax, sh.y - 0.05, sh.az)
	local b = Vector3.new(sh.bx, sh.y - 0.05, sh.bz)
	local len = (b - a).Magnitude
	if len < 1 then return end
	local o = Vector3.new(sh.ox, 0, sh.oz).Unit
	local hi = (a + b) / 2 - o * 0.3
	local lo = hi + o * SHOULDER_W - Vector3.new(0, SHOULDER_DROP, 0)
	local dir = (lo - hi).Unit
	local mid = (hi + lo) / 2
	local cf = CFrame.lookAt(mid, mid + dir) * CFrame.new(0, -0.5, 0) -- top face through the hi -> lo line
	newPart(parent, "Shoulder", Vector3.new(len + 2, 1, (lo - hi).Magnitude), cf, COLORS.verge, true)
end

-- arrival area (all gameplay): verge ground and shoulders, visitor paddock + service road, car park with bays,
-- signs, flag poles, lamp posts. Every field is optional so older definitions still build.
local function buildArrival(root: Instance, def: any)
	local arr = model(root, "Arrival")
	-- verge slabs: top 1 stud under the road, so a car that leaves the road edge rolls down the shoulder onto them
	for _, v in def.verge or {} do
		newPart(arr, "Verge", Vector3.new(v.w, SLAB, v.d), yawCf(v.x, v.y - SLAB / 2, v.z, v.yaw), COLORS.verge, true)
	end
	for _, sh in def.shoulders or {} do
		shoulder(arr, sh)
	end
	local pd = def.paddock
	if pd then
		local pm = model(arr, "Paddock")
		pm:SetAttribute("Verified", pd.verified)
		local apron = newPart(pm, "Apron", Vector3.new(pd.w, SLAB, pd.d), yawCf(pd.x, pd.y + 0.01 - SLAB / 2, pd.z, pd.yaw), COLORS.paddock, true)
		apron:SetAttribute("Paddock", true)
		-- two team tents along the back edge; dx/dz is the paddock's front (toward the plaza road)
		local base = yawCf(pd.x, pd.y, pd.z, pd.yaw)
		local toBack = -Vector3.new(pd.dx, 0, pd.dz).Unit
		for _, sx in {-0.25, 0.25} do
			local tpos = Vector3.new(pd.x, pd.y, pd.z) + base.RightVector * sx * pd.w + toBack * (pd.d / 2 - 11)
			local tc = CFrame.lookAt(tpos, tpos - toBack)
			local roof = newPart(pm, "TentRoof", Vector3.new(30, 0.6, 20), tc * CFrame.new(0, 10, 0), COLORS.tent, false)
			roof.CanQuery = false
			for _, cx in {-14, 14} do
				for _, cz in {-9, 9} do
					newPart(pm, "TentPost", Vector3.new(0.5, 10, 0.5), tc * CFrame.new(cx, 5, cz), COLORS.pole, true)
				end
			end
		end
	end
	if def.paddockRoad then
		local pts = toV3(def.paddockRoad.pts)
		if #pts >= 2 then
			strip(arr, "PaddockRoad", pts, table.create(#pts, def.paddockRoad.width), SERVICE_DROP, SLAB, COLORS.road, true)
		end
	end
	for _, cp in def.carPark or {} do
		local cm = model(arr, "CarPark")
		cm:SetAttribute("Bays", cp.bays)
		newPart(cm, "CarPark", Vector3.new(cp.w, SLAB, cp.d), yawCf(cp.x, cp.y + 0.015 - SLAB / 2, cp.z, cp.yaw), COLORS.parking, true)
		local base = yawCf(cp.x, cp.y + 0.04, cp.z, cp.yaw)
		local nb = math.floor(cp.w / cp.bayW + 0.5)
		for _, row in {-1, 1} do
			local zc = row * (cp.d / 2 - cp.bayD / 2)
			for k = 0, nb do
				local line = newPart(cm, "BayLine", Vector3.new(0.5, 0.05, cp.bayD - 1), base * CFrame.new(-cp.w / 2 + k * cp.bayW, 0, zc), COLORS.bay, false)
				line.CanQuery = false
			end
			local back = newPart(cm, "BayLine", Vector3.new(cp.w, 0.05, 0.5), base * CFrame.new(0, 0, row * (cp.d / 2 - 0.6)), COLORS.bay, false)
			back.CanQuery = false
		end
	end
	for _, s in def.signs or {} do
		local at = Vector3.new(s.x, s.y, s.z)
		local face = Vector3.new(s.dx, 0, s.dz).Unit
		local right = Vector3.new(-face.Z, 0, face.X)
		if s.kind == "pylon" then
			-- destination marker: a tall double-sided column, readable from the corridor and from the plaza
			local cf = CFrame.lookAt(at + Vector3.new(0, s.h / 2, 0), at + Vector3.new(0, s.h / 2, 0) + face)
			local p = newPart(arr, "DestinationPylon", Vector3.new(s.w, s.h + 4, 3), cf * CFrame.new(0, -2, 0), COLORS.pylon, true)
			sign(p, s.text, Enum.NormalId.Front, Color3.fromRGB(255, 255, 255), true)
			sign(p, s.text, Enum.NormalId.Back, Color3.fromRGB(255, 255, 255), true)
			local cap = newPart(arr, "PylonCap", Vector3.new(s.w + 1, 1.5, 3.6), cf * CFrame.new(0, s.h / 2 + 0.8, 0), COLORS.paddockSign, false)
			cap.CanQuery = false
			nightNeon(cap, COLORS.paddockSign, COLORS.paddockSign)
		else
			local color = if s.kind == "board" then COLORS.paddockSign else COLORS.roadSign
			for _, sx in {-1, 1} do
				newPart(arr, "SignPost", Vector3.new(0.5, s.post + s.h / 2 + 2, 0.5),
					CFrame.new(at + right * sx * (s.w / 2 - 1) + Vector3.new(0, (s.post + s.h / 2 - 2) / 2, 0)), COLORS.pole, true)
			end
			local c0 = at + Vector3.new(0, s.post + s.h / 2, 0)
			local board = newPart(arr, "Sign", Vector3.new(s.w, s.h, 0.4), CFrame.lookAt(c0, c0 + face), color, false)
			board.CanQuery = false
			sign(board, s.text, Enum.NormalId.Front, Color3.fromRGB(255, 255, 255), true)
		end
	end
	for _, f in def.flagPoles or {} do
		local at = Vector3.new(f.x, f.y, f.z)
		newPart(arr, "FlagPole", Vector3.new(0.5, 32, 0.5), CFrame.new(at + Vector3.new(0, 15, 0)), COLORS.pole, true)
		-- plain coloured flags (no logos), hung toward the road direction
		local fl = newPart(arr, "Flag", Vector3.new(0.15, 5, 8), CFrame.new(at + Vector3.new(0, 27.5, 4.2)), FLAG_COLORS[(f.color or 0) % #FLAG_COLORS + 1], false)
		fl.CanQuery = false
	end
	for i, l in def.lampPosts or {} do
		local at = Vector3.new(l.x, l.y, l.z)
		local inward = Vector3.new(l.dx, 0, l.dz).Unit
		newPart(arr, "LampPost", Vector3.new(0.8, 26, 0.8), CFrame.new(at + Vector3.new(0, 12, 0)), COLORS.pole, true)
		local hp = at + Vector3.new(0, 24.5, 0) + inward * 2
		local head = newPart(arr, "LampHead", Vector3.new(3, 0.8, 4), CFrame.lookAt(hp, hp + inward), COLORS.lampDay, false)
		head.CanQuery = false
		head:SetAttribute("FloodLight", true)
		head:SetAttribute("Index", i)
		nightNeon(head, COLORS.lampDay, COLORS.lamp)
		local s = Instance.new("SpotLight")
		s.Face = Enum.NormalId.Bottom
		s.Angle = 120
		s.Range = 45
		s.Brightness = 2
		s.Color = COLORS.lamp
		s.Shadows = false
		s.Enabled = false
		s.Parent = head
	end
end

-- terrain under the venue: grass columns from ground.base up to each cell's height (the generator keeps cells under
-- the track 1.5 studs below its surface). Like PattayaBuilder: clear the frame first, then fill; a fill up to y renders
-- about 2 studs higher, so columns stop 2 studs short.
local function buildTerrain(def: any)
	local g = def.ground
	local terrain = workspace.Terrain
	local x1, z1 = g.x0 + g.nx * g.cell, g.z0 + g.nz * g.cell
	local top = g.base
	for _, h in g.h do
		if h > top then top = h end
	end
	local tile = 512
	for x = g.x0, x1, tile do
		for z = g.z0, z1, tile do
			local region = Region3.new(Vector3.new(x, g.base - 8, z), Vector3.new(math.min(x + tile, x1), top + 16, math.min(z + tile, z1))):ExpandToGrid(4)
			terrain:ReplaceMaterial(region, 4, Enum.Material.Grass, Enum.Material.Air)
			task.wait()
		end
	end
	for jz = 0, g.nz - 1 do
		for jx = 0, g.nx - 1 do
			local h = g.h[jz * g.nx + jx + 1] - 2
			local height = h - g.base
			if height > 1 then
				local cx, cz = g.x0 + (jx + 0.5) * g.cell, g.z0 + (jz + 0.5) * g.cell
				terrain:FillBlock(CFrame.new(cx, g.base + height / 2, cz), Vector3.new(g.cell, height, g.cell), Enum.Material.Grass)
			end
		end
		if jz % 4 == 0 then
			task.wait()
		end
	end
end

function Builder.Build(def: any, opts: {terrain: boolean?, lights: boolean?}?): string
	local options: {terrain: boolean?, lights: boolean?} = opts or {}
	local name = "Circuit_" .. def.id
	local old = workspace:FindFirstChild(name)
	if old then
		old:Destroy()
	end
	built = 0
	local root = Instance.new("Model")
	root.Name = name
	root:SetAttribute("CircuitId", def.id)
	root:SetAttribute("DisplayName", def.name)
	root:SetAttribute("LengthStuds", def.lengthStuds)
	root:SetAttribute("StudsPerMetre", def.studsPerMetre)
	root:SetAttribute("Attribution", def.attribution)
	root.Parent = workspace

	local c = toV3(def.centerline)
	local nrm = normals(c, true)
	buildTrack(root, def, c, nrm)
	buildCurbs(root, def, c, nrm)
	buildBarriers(root, def, c, nrm)
	buildPit(root, def)
	buildGrid(root, def)
	buildBoards(root, def, c)
	if options.lights ~= false then
		buildLights(root, def)
	end
	buildBuildings(root, def, c)
	buildAccess(root, def)
	buildArrival(root, def)
	if options.terrain ~= false and def.ground then
		buildTerrain(def)
	end
	return ("%s: %d parts, %d centreline points, lap %d studs"):format(name, built, #c, def.lengthStuds)
end

return Builder
