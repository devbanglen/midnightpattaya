--!strict
-- Builds the Pattaya slice in Studio (edit time) from the generated data modules in ServerStorage.PattayaData
-- (tools/mapgen/export_roblox.py). Rebuilding replaces workspace.PattayaWorld only; nothing else is touched.
--   require(game.ServerStorage.PattayaBuilder).Build()          -- everything
--   require(game.ServerStorage.PattayaBuilder).Build({terrain = false})
local Builder = {}

Builder.ORIGIN = Vector3.new(20000, 0, 0) -- world position of gameplay (0, 0): clear of the template and RaceMap
local ROAD_TOP = 1.0
local ROAD_THICK = 1.0
local CURB = 0.6
local MARK_THICK = 0.05

local COLORS = {
	road = Color3.fromRGB(46, 47, 52),
	junction = Color3.fromRGB(46, 47, 52),
	sidewalk = Color3.fromRGB(170, 168, 160),
	centre = Color3.fromRGB(245, 200, 40),
	lane = Color3.fromRGB(235, 235, 235),
}

type Edge = {
	id: string, way: number, class: string, tier: string, name: string?, nameEn: string?, oneway: boolean,
	lanes: number, width: number, sidewalk: number, coastal: boolean, a: number, b: number, pts: {number},
}

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
	p.CanQuery = collide -- markings stay out of the car's suspension raycasts
	p.CanTouch = false
	p.CastShadow = false
	p.Parent = parent
	return p
end

local function toPoints(flat: {number}): {Vector2}
	local pts = {}
	for i = 1, #flat, 2 do
		table.insert(pts, Vector2.new(flat[i], flat[i + 1]))
	end
	return pts
end

-- one Part per polyline segment; each end is stretched by the outer-edge gap of the bend at that joint
local function stripe(parent: Instance, name: string, pts: {Vector2}, width: number, top: number, thick: number,
	color: Color3, collide: boolean)
	local n = #pts
	local ext = table.create(n, 0)
	for j = 2, n - 1 do
		local d1 = (pts[j] - pts[j - 1]).Unit
		local d2 = (pts[j + 1] - pts[j]).Unit
		local turn = math.acos(math.clamp(d1:Dot(d2), -1, 1))
		ext[j] = math.min(width / 2 * math.tan(turn / 2), width / 2)
	end
	for i = 1, n - 1 do
		local a, b = pts[i], pts[i + 1]
		local seg = b - a
		local len = seg.Magnitude
		if len > 0.05 then
			local dir = seg.Unit
			local a2 = a - dir * ext[i]
			local b2 = b + dir * ext[i + 1]
			local mid = (a2 + b2) / 2
			local y = top - thick / 2
			local cf = CFrame.lookAt(Vector3.new(mid.X, y, mid.Y), Vector3.new(b2.X, y, b2.Y))
			newPart(parent, name, Vector3.new(width, thick, (b2 - a2).Magnitude), cf, color, collide)
		end
	end
end

local function offset(pts: {Vector2}, d: number): {Vector2}
	local out = table.create(#pts)
	for i = 1, #pts do
		local t: Vector2
		if i == 1 then
			t = pts[2] - pts[1]
		elseif i == #pts then
			t = pts[i] - pts[i - 1]
		else
			t = (pts[i + 1] - pts[i]).Unit + (pts[i] - pts[i - 1]).Unit
		end
		t = t.Unit
		out[i] = pts[i] + Vector2.new(-t.Y, t.X) * d
	end
	return out
end

-- cut d0 off the start and d1 off the end of a polyline (sidewalks stop short of junctions)
local function trim(pts: {Vector2}, d0: number, d1: number): {Vector2}?
	local total = 0
	for i = 1, #pts - 1 do
		total += (pts[i + 1] - pts[i]).Magnitude
	end
	if total <= d0 + d1 + 2 then
		return nil
	end
	local out = {}
	local s = 0
	local lo, hi = d0, total - d1
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = (b - a).Magnitude
		local s0, s1 = s, s + len
		if s1 >= lo and s0 <= hi then
			local ta = math.clamp((lo - s0) / len, 0, 1)
			local tb = math.clamp((hi - s0) / len, 0, 1)
			if #out == 0 then
				table.insert(out, a:Lerp(b, ta))
			end
			table.insert(out, a:Lerp(b, tb))
		end
		s = s1
	end
	return if #out >= 2 then out else nil
end

local function dashes(parent: Instance, pts: {Vector2}, dash: number, gap: number, width: number, color: Color3)
	local carry = 0
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = (b - a).Magnitude
		local dir = (b - a).Unit
		local s = carry
		while s + dash <= len do
			stripe(parent, "Dash", {a + dir * s, a + dir * (s + dash)}, width, ROAD_TOP + MARK_THICK, MARK_THICK, color, false)
			s += dash + gap
		end
		carry = math.max(s - len, 0)
	end
end

local function buildEdge(chunk: Instance, e: Edge, junctionR: {[number]: number})
	local pts = toPoints(e.pts)
	local road = Instance.new("Model")
	road.Name = e.nameEn or e.name or e.class
	road:SetAttribute("EdgeId", e.id)
	road:SetAttribute("OsmWay", e.way)
	road:SetAttribute("Tier", e.tier)
	road:SetAttribute("Lanes", e.lanes)
	road:SetAttribute("Oneway", e.oneway)
	road:SetAttribute("Coastal", e.coastal)
	if e.name then road:SetAttribute("NameTh", e.name) end
	stripe(road, "Road", pts, e.width, ROAD_TOP, ROAD_THICK, COLORS.road, true)

	-- markings stop short of junction discs
	local ra, rb = junctionR[e.a] or 0, junctionR[e.b] or 0
	local inner = trim(pts, ra, rb)
	if inner and e.tier ~= "soi" then
		if e.oneway then
			for k = 1, e.lanes - 1 do
				dashes(road, offset(inner, (k - e.lanes / 2) * e.width / e.lanes), 8, 12, 0.5, COLORS.lane)
			end
		else
			stripe(road, "Centre", offset(inner, -0.5), 0.45, ROAD_TOP + MARK_THICK, MARK_THICK, COLORS.centre, false)
			stripe(road, "Centre", offset(inner, 0.5), 0.45, ROAD_TOP + MARK_THICK, MARK_THICK, COLORS.centre, false)
			local perSide = math.floor(e.lanes / 2)
			for k = 1, perSide - 1 do
				local d = k * e.width / e.lanes
				dashes(road, offset(inner, d), 8, 12, 0.5, COLORS.lane)
				dashes(road, offset(inner, -d), 8, 12, 0.5, COLORS.lane)
			end
		end
	end
	if e.sidewalk > 0 then
		local sw = trim(pts, ra + e.sidewalk, rb + e.sidewalk)
		if sw then
			for _, side in {-1, 1} do
				stripe(road, "Sidewalk", offset(sw, side * (e.width + e.sidewalk) / 2), e.sidewalk, ROAD_TOP + CURB, ROAD_THICK + CURB, COLORS.sidewalk, true)
			end
		end
	end
	road.Parent = chunk
end

local function buildTerrain(man: any)
	local terrain = workspace.Terrain
	local o = Builder.ORIGIN
	local f = man.frame
	-- ground slab under the whole slice (top at y = 0, roads sit 1 stud above), then the sea carved in
	local size = Vector3.new(f.maxX - f.minX, 16, f.maxZ - f.minZ)
	local centre = o + Vector3.new((f.minX + f.maxX) / 2, -8, (f.minZ + f.maxZ) / 2)
	terrain:FillBlock(CFrame.new(centre), size, Enum.Material.Ground)
	task.wait()
	local cell = man.seaCell
	for i, row in man.sea do
		local r = row.runs
		for k = 1, #r, 2 do
			local x0, x1 = r[k], r[k + 1]
			local c = o + Vector3.new((x0 + x1) / 2, -8, row.z + cell / 2)
			terrain:FillBlock(CFrame.new(c), Vector3.new(x1 - x0, 16, cell), Enum.Material.Water)
			-- a sand step along the waterline so the beach reads from the road
			local beach = o + Vector3.new(x1 + 24, -1, row.z + cell / 2)
			terrain:FillBlock(CFrame.new(beach), Vector3.new(48, 2, cell), Enum.Material.Sand)
		end
		if i % 40 == 0 then
			task.wait()
		end
	end
end

function Builder.Build(opts: {terrain: boolean?}?)
	local options = opts or {}
	local data = game:GetService("ServerStorage"):WaitForChild("PattayaData")
	local man = require(data:WaitForChild("manifest")) :: any
	local old = workspace:FindFirstChild("PattayaWorld")
	if old then
		old:Destroy()
	end
	local world = Instance.new("Folder")
	world.Name = "PattayaWorld"
	world:SetAttribute("Attribution", man.attribution)
	world:SetAttribute("OsmBase", man.osmBase)
	world:SetAttribute("Compression", man.compression)
	world.Parent = workspace

	local junctionR: {[number]: number} = {}
	local junctions = Instance.new("Model")
	junctions.Name = "Junctions"
	for _, j in man.junctions do
		junctionR[j.id] = j.r
		local cf = CFrame.new(j.x, ROAD_TOP - ROAD_THICK / 2 - 0.01, j.z) * CFrame.Angles(0, 0, math.rad(90))
		local p = newPart(junctions, "Junction", Vector3.new(ROAD_THICK, j.r * 2, j.r * 2), cf, COLORS.junction, true)
		p.Shape = Enum.PartType.Cylinder
		p:SetAttribute("OsmNode", j.id)
	end
	junctions:PivotTo(junctions:GetPivot() + Builder.ORIGIN)
	junctions.Parent = world

	local chunksFolder = Instance.new("Folder")
	chunksFolder.Name = "Chunks"
	chunksFolder.Parent = world
	local count = 0
	for _, id in man.chunks do
		local chunkData = require(data:WaitForChild("chunk_" .. id)) :: any
		local chunk = Instance.new("Model")
		chunk.Name = "Chunk_" .. id
		chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
		for _, e in chunkData.edges do
			buildEdge(chunk, e :: Edge, junctionR)
		end
		chunk:PivotTo(chunk:GetPivot() + Builder.ORIGIN)
		for _, d in chunk:GetDescendants() do
			if d:IsA("BasePart") then count += 1 end
		end
		chunk.Parent = chunksFolder
		task.wait()
	end
	if options.terrain ~= false then
		buildTerrain(man)
	end
	return ("%d chunks, %d road parts, %d junctions"):format(#man.chunks, count, #man.junctions)
end

return Builder
