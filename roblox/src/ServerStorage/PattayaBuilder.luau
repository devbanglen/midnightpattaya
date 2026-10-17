--!strict
-- Builds the Pattaya slice in Studio (edit time) from the generated data modules in ServerStorage.PattayaData
-- (tools/mapgen/export_roblox.py). Rebuilding replaces workspace.PattayaWorld only; nothing else is touched.
--   require(game.ServerStorage.PattayaBuilder).Build()          -- everything
--   require(game.ServerStorage.PattayaBuilder).Build({terrain = false})
local Builder = {}

Builder.ORIGIN = Vector3.new(20000, 0, 0) -- world position of gameplay (0, 0): clear of the template and RaceMap
local ROAD_TOP = 1.0
local ROAD_THICK = 4.0 -- reaches below the terrain surface (y = -2) so road edges don't float
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
		-- at a junction disc the sidewalk stops where the crossing road's edge is (disc radius + this sidewalk);
		-- at a plain joint (no disc) it runs to the end so it meets the next edge's sidewalk
		local sa = if ra > 0 then ra + e.sidewalk else 0
		local sb = if rb > 0 then rb + e.sidewalk else 0
		local sw = trim(pts, sa, sb)
		if sw then
			for _, side in {-1, 1} do
				stripe(road, "Sidewalk", offset(sw, side * (e.width + e.sidewalk) / 2), e.sidewalk, ROAD_TOP + CURB, ROAD_THICK + CURB, COLORS.sidewalk, true)
			end
		end
	end
	road.Parent = chunk
end

-- Buildings: one box Part each (+ a roof slab on taller ones), facades as Texture instances on the four sides so
-- windows cost no Parts. Wall colour is picked per palette from the OSM id, so rebuilds give the same city.
local WALLS = {
	hotel = {Color3.fromRGB(236, 232, 222), Color3.fromRGB(214, 226, 236), Color3.fromRGB(242, 222, 196), Color3.fromRGB(200, 214, 220)},
	condo = {Color3.fromRGB(220, 224, 230), Color3.fromRGB(190, 200, 214), Color3.fromRGB(235, 235, 235)},
	apartment = {Color3.fromRGB(226, 214, 190), Color3.fromRGB(205, 196, 180), Color3.fromRGB(230, 220, 205)},
	mall = {Color3.fromRGB(230, 230, 235), Color3.fromRGB(210, 220, 230)},
	commercial = {Color3.fromRGB(200, 205, 210), Color3.fromRGB(176, 190, 200), Color3.fromRGB(222, 214, 200)},
	shophouse = {Color3.fromRGB(232, 210, 170), Color3.fromRGB(214, 190, 160), Color3.fromRGB(240, 226, 190), Color3.fromRGB(205, 170, 150), Color3.fromRGB(190, 205, 190)},
	house = {Color3.fromRGB(240, 232, 214), Color3.fromRGB(226, 206, 180)},
	temple = {Color3.fromRGB(200, 60, 40)},
	parking = {Color3.fromRGB(150, 150, 152)},
}
local FACADE_OF = {hotel = "tower", condo = "tower", apartment = "tower", mall = "office", commercial = "office",
	parking = "office", shophouse = "shophouse"}
local FACES = {Enum.NormalId.Front, Enum.NormalId.Back, Enum.NormalId.Left, Enum.NormalId.Right}

local function buildBuildings(chunk: Instance, rows: {number}, man: any)
	if #rows == 0 then
		return
	end
	local folder = Instance.new("Model")
	folder.Name = "Buildings"
	local level = man.levelStuds
	for i = 1, #rows, 8 do
		local x, z, w, d, h, yaw = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 4], rows[i + 5]
		local palette = man.palettes[rows[i + 6]]
		local id = rows[i + 7]
		local colors = WALLS[palette]
		local base = ROAD_TOP - 1 -- footings below the road top so buildings sit in the ground
		local cf = CFrame.new(x, base + h / 2, z) * CFrame.Angles(0, -math.rad(yaw), 0)
		local body = newPart(folder, palette, Vector3.new(w, h, d), cf, colors[id % #colors + 1], true)
		body.CastShadow = h > 20
		body:SetAttribute("OsmBuilding", id)
		local facade = FACADE_OF[palette]
		if facade then
			for _, face in FACES do
				local t = Instance.new("Texture")
				t.Texture = man.facades[facade]
				t.Face = face
				t.StudsPerTileV = level
				t.StudsPerTileU = if facade == "shophouse" then level * 1.3 else level * 1.1
				t.OffsetStudsV = (h % level) -- full floors line up with the top
				t.Parent = body
			end
		end
		if h > 30 then
			local roof = newPart(folder, "Roof", Vector3.new(math.max(w - 3, 1), 1, math.max(d - 3, 1)),
				cf * CFrame.new(0, h / 2 + 0.5, 0), colors[1]:Lerp(Color3.new(0.3, 0.3, 0.32), 0.55), false)
			roof.CanQuery = false
		end
	end
	folder.Parent = chunk
end

local function buildTerrain(man: any)
	local terrain = workspace.Terrain
	local o = Builder.ORIGIN
	local f = man.frame
	-- Measured: a voxel slab filled up to the grid line y = Y renders/collides at Y + 2, and filling the same block a
	-- second time does not overwrite existing voxels. So: clear the frame's top layers first, fill ground up to
	-- y = -4 (surface at -2, under the roads), then carve sea and beach with ReplaceMaterial on grid-aligned regions.
	local function replace(x0: number, x1: number, z0: number, z1: number, y0: number, y1: number, from: Enum.Material, to: Enum.Material)
		local region = Region3.new(o + Vector3.new(x0, y0, z0), o + Vector3.new(x1, y1, z1)):ExpandToGrid(4)
		terrain:ReplaceMaterial(region, 4, from, to)
	end
	for _, m in {Enum.Material.Ground, Enum.Material.Sand, Enum.Material.Water} do
		replace(f.minX, f.maxX, f.minZ, f.maxZ, -16, 8, m, Enum.Material.Air)
		task.wait()
	end
	local size = Vector3.new(f.maxX - f.minX, 12, f.maxZ - f.minZ)
	local centre = o + Vector3.new((f.minX + f.maxX) / 2, -10, (f.minZ + f.maxZ) / 2)
	terrain:FillBlock(CFrame.new(centre), size, Enum.Material.Ground)
	task.wait()
	local cell = man.seaCell
	for i, row in man.sea do
		local r = row.runs
		for k = 1, #r, 2 do
			local x0, x1 = r[k], r[k + 1]
			replace(x0, x1, row.z, row.z + cell, -16, -4, Enum.Material.Ground, Enum.Material.Water)
			-- a sand strip along the waterline so the beach reads from the road
			replace(x1, x1 + 48, row.z, row.z + cell, -8, -4, Enum.Material.Ground, Enum.Material.Sand)
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
		buildBuildings(chunk, chunkData.buildings or {}, man)
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
