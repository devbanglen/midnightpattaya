--!strict
-- Coast pass for the Pattaya world (tools/mapgen/coast.py -> build/coast/roblox -> ServerStorage.PattayaDataCoast).
-- Adds, never rebuilds: beach props in workspace.PattayaWorld.CoastChunks (Atomic chunk Models "Coast_b<cx>_<cz>"),
-- the 4-stud shoreline in Terrain, and a distant island silhouette in workspace.PattayaWorld.CoastIslands.
-- PattayaBuilder, its chunks, roads, discs, buildings and the rest of the terrain are not touched.
-- WRITTEN, NOT RUN IN STUDIO YET (2026-10-19). Map data (c) OpenStreetMap contributors, ODbL 1.0.
--
--   local C = require(game.ServerStorage.PattayaCoastBuilder)
--   C.Build({batch = "b1"})        -- props, one batch (<= 8 chunks) per call: b1 .. b6 (manifest.batchOrder)
--   C.Build({only = {"b1_0"}})     -- props, chosen chunks; built chunks are skipped (resumable)
--   C.Remove()                     -- props + islands (terrain is separate: RemoveTerrain)
--   C.BuildTerrain({tile = 1})     -- shoreline, one terrain module (one <= 2048-stud tile) per call: 1 .. #modules
--   C.BuildTerrain()               -- every module, task.wait() between runs and modules (slow: tens of seconds)
--   C.BuildTerrain({fill = true})  -- OPTIONAL landward beach fill (moves the sand strip's landward edge; see COAST.md)
--   C.RemoveTerrain()              -- writes the old voxel states back (RemoveTerrain({fill = true}) for the fill)
--   C.BuildIsland()                -- horizon islands; refuses when anything else stands in their boxes ({force = true})
--   C.RemoveIsland()
--   C.Probe()                      -- overlap + voxel checks (also printed)
local Coast = {}

Coast.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN: world = map-local + ORIGIN
local ROAD_TOP = 1.0
local GROUND_Y = ROAD_TOP - 3 -- terrain surface (ground / sand) renders at y = -2
local WATER_Y = -2 -- water surface
local ISLAND_BASE_Y = -6
local DATA = "PattayaDataCoast"

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
	p.CanQuery = collide -- decor stays out of the car's suspension raycasts
	p.CanTouch = false
	p.CastShadow = false
	p.Parent = parent
	return p
end

local function cyl(parent: Instance, name: string, length: number, dia: number, cf: CFrame, color: Color3, collide: boolean): Part
	-- vertical cylinder: a Part cylinder's axis is X, turned to Y
	local p = newPart(parent, name, Vector3.new(length, dia, dia), cf * CFrame.Angles(0, 0, math.rad(90)), color, collide)
	p.Shape = Enum.PartType.Cylinder
	return p
end

local function data(): Instance
	return game:GetService("ServerStorage"):WaitForChild(DATA)
end

local function manifest(): any
	return require(data():WaitForChild("manifest")) :: any
end

local function world(): Instance
	local w = workspace:FindFirstChild("PattayaWorld")
	if not w then
		error("PattayaCoastBuilder: build the Pattaya world first (PattayaBuilder.Build / Extend)")
	end
	return w
end

-- facing frame on the ground: LookVector = (nx, 0, nz) (towards the sea for beach props)
local function facing(x: number, z: number, nx: number, nz: number, y: number): CFrame
	return CFrame.lookAt(Vector3.new(x, y, z), Vector3.new(x + nx, y, z + nz))
end

-- props ----------------------------------------------------------------------------------------------------------
local UMBRELLA = {Color3.fromRGB(30, 110, 200), Color3.fromRGB(235, 120, 30), Color3.fromRGB(40, 160, 90),
	Color3.fromRGB(220, 50, 60), Color3.fromRGB(245, 205, 40), Color3.fromRGB(0, 170, 180)}
local NEON = {Color3.fromRGB(255, 50, 170), Color3.fromRGB(0, 220, 255), Color3.fromRGB(255, 200, 40),
	Color3.fromRGB(140, 90, 255), Color3.fromRGB(80, 255, 120)}
local POLE = Color3.fromRGB(205, 205, 200)
local LOUNGER = Color3.fromRGB(242, 240, 232)
local WOOD = Color3.fromRGB(140, 102, 66)
local THATCH = Color3.fromRGB(176, 140, 82)
local LAMP_POLE = Color3.fromRGB(48, 58, 56)
local LAMP = Color3.fromRGB(255, 236, 190)

local function umbrella(m: Instance, x: number, z: number, nx: number, nz: number, ci: number)
	local base = facing(x, z, nx, nz, GROUND_Y)
	cyl(m, "UmbrellaPole", 10, 0.35, base * CFrame.new(0, 4, 0), POLE, false)
	local canopy = newPart(m, "UmbrellaCanopy", Vector3.new(0.5, 9, 9), base * CFrame.new(0, 8.6, 0) * CFrame.Angles(math.rad(-6), 0, 0)
		* CFrame.Angles(0, 0, math.rad(90)), UMBRELLA[ci] or UMBRELLA[1], false)
	canopy.Shape = Enum.PartType.Cylinder
	for _, side in {-1.7, 1.7} do -- two loungers on the sea side of the pole, heads towards the pole
		newPart(m, "Lounger", Vector3.new(2.3, 0.7, 6.4), base * CFrame.new(side, 0.55, -3.9) * CFrame.Angles(math.rad(4), 0, 0), LOUNGER, false)
	end
end

local function promenadeLamp(m: Instance, x: number, z: number, nx: number, nz: number, withLight: boolean)
	local base = facing(x, z, nx, nz, GROUND_Y)
	newPart(m, "PromenadeLampBase", Vector3.new(1.3, 1, 1.3), base * CFrame.new(0, 0.5, 0), LAMP_POLE, true)
	cyl(m, "PromenadePole", 14, 0.5, base * CFrame.new(0, 7, 0), LAMP_POLE, true)
	-- named "Lamp": PattayaNightLights turns it Neon after dark and runs its SpotLight in the lamp budget
	local lamp = newPart(m, "Lamp", Vector3.new(1.8, 1.8, 1.8), base * CFrame.new(0, 14.6, 0), LAMP, false)
	lamp.Shape = Enum.PartType.Ball
	if withLight then
		local light = Instance.new("SpotLight")
		light.Face = Enum.NormalId.Bottom
		light.Angle = 120
		light.Range = 30
		light.Brightness = 1.8
		light.Color = Color3.fromRGB(255, 220, 170)
		light.Shadows = false
		light.Enabled = false
		light.Parent = lamp
	end
end

local function lifeguardTower(m: Instance, x: number, z: number, nx: number, nz: number)
	local base = facing(x, z, nx, nz, GROUND_Y)
	for _, side in {-2.4, 2.4} do
		newPart(m, "TowerLeg", Vector3.new(0.5, 8.5, 4.6), base * CFrame.new(side, 3.75, 0), Color3.fromRGB(235, 235, 230), true)
	end
	newPart(m, "TowerDeck", Vector3.new(6, 0.5, 6), base * CFrame.new(0, 8.2, 0), WOOD, false)
	newPart(m, "TowerCabin", Vector3.new(4.6, 3.6, 3.6), base * CFrame.new(0, 10.25, 0.6), Color3.fromRGB(205, 40, 40), false)
	newPart(m, "TowerRoof", Vector3.new(6, 0.4, 5.4), base * CFrame.new(0, 12.3, 0.3), Color3.fromRGB(245, 245, 240), false)
	newPart(m, "TowerFlagPole", Vector3.new(0.25, 5, 0.25), base * CFrame.new(2.6, 14.8, 2.4), POLE, false)
	newPart(m, "TowerFlag", Vector3.new(0.1, 1.5, 2.4), base * CFrame.new(2.6, 16.4, 1.15), Color3.fromRGB(240, 200, 30), false)
end

local function boat(m: Instance, x: number, z: number, dx: number, dz: number, kind: number)
	local base = facing(x, z, dx, dz, WATER_Y)
	if kind == 1 then -- longtail: long painted wooden hull, raised bow, engine pole at the stern
		newPart(m, "BoatHull", Vector3.new(3, 1.6, 15), base * CFrame.new(0, -0.3, 0), Color3.fromRGB(40, 120, 140), false)
		newPart(m, "BoatBow", Vector3.new(2.2, 1.1, 5), base * CFrame.new(0, 0.9, -8.6) * CFrame.Angles(math.rad(22), 0, 0), WOOD, false)
		newPart(m, "BoatEngine", Vector3.new(0.5, 0.5, 6), base * CFrame.new(0, 0.6, 9.4) * CFrame.Angles(math.rad(-12), 0, 0), Color3.fromRGB(60, 60, 64), false)
	else -- speedboat: white hull, bow, console
		newPart(m, "BoatHull", Vector3.new(3.6, 1.4, 11), base * CFrame.new(0, -0.2, 0), Color3.fromRGB(240, 240, 240), false)
		newPart(m, "BoatBow", Vector3.new(3, 1.1, 4), base * CFrame.new(0, 0.6, -6.6) * CFrame.Angles(math.rad(14), 0, 0), Color3.fromRGB(230, 232, 236), false)
		newPart(m, "BoatConsole", Vector3.new(2, 1.4, 1.6), base * CFrame.new(0, 1.2, 0.5), Color3.fromRGB(35, 40, 48), false)
	end
end

local function neonPart(p: BasePart, color: Color3)
	-- PattayaNightLights: NightNeon parts turn Neon + NightColor after dark, SmoothPlastic + DayColor by day
	p:SetAttribute("NightNeon", true)
	p:SetAttribute("NightColor", color)
	p:SetAttribute("DayColor", color:Lerp(Color3.fromRGB(70, 70, 76), 0.55))
	p.Color = p:GetAttribute("DayColor") :: Color3
end

local function beachHut(m: Instance, x: number, z: number, nx: number, nz: number, ci: number)
	local base = facing(x, z, nx, nz, GROUND_Y)
	local neon = NEON[ci] or NEON[1]
	newPart(m, "HutFloor", Vector3.new(12, 0.6, 8), base * CFrame.new(0, 0.3, 0), WOOD, true)
	newPart(m, "HutBar", Vector3.new(12, 3.5, 1.4), base * CFrame.new(0, 2.35, -3.2), WOOD, true)
	newPart(m, "HutBack", Vector3.new(12, 7.4, 0.6), base * CFrame.new(0, 4.3, 3.7), WOOD:Lerp(Color3.new(0, 0, 0), 0.2), true)
	newPart(m, "HutRoof", Vector3.new(14, 0.8, 10), base * CFrame.new(0, 8.4, -0.2) * CFrame.Angles(math.rad(-8), 0, 0), THATCH, false)
	local trim = newPart(m, "HutNeonTrim", Vector3.new(12.2, 0.4, 0.3), base * CFrame.new(0, 3.9, -3.95), neon, false)
	neonPart(trim, neon)
	local sign = newPart(m, "HutNeonSign", Vector3.new(6, 1.6, 0.3), base * CFrame.new(0, 7.0, -4.4), neon, false)
	neonPart(sign, neon)
	local gui = Instance.new("SurfaceGui") -- generic text, no brand
	gui.Face = Enum.NormalId.Front
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 24
	gui.LightInfluence = 0.2
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Text = "BEACH BAR"
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.Font = Enum.Font.GothamBold
	label.TextScaled = true
	label.Parent = gui
	gui.Parent = sign
end

local function parasail(m: Instance, x: number, z: number, dx: number, dz: number, height: number, ci: number)
	boat(m, x, z, dx, dz, 2)
	local dir = Vector3.new(dx, 0, dz).Unit
	local stern = Vector3.new(x, WATER_Y + 1, z) - dir * 5.5
	local top = Vector3.new(x, WATER_Y, z) - dir * 60 + Vector3.new(0, height, 0)
	local canopy = newPart(m, "ParasailCanopy", Vector3.new(14, 0.4, 6), CFrame.lookAt(top, top + dir) * CFrame.Angles(math.rad(10), 0, 0),
		UMBRELLA[ci] or UMBRELLA[2], false)
	canopy.CanQuery = false
	local mid = (stern + top) / 2
	newPart(m, "ParasailLine", Vector3.new(0.15, 0.15, (top - stern).Magnitude), CFrame.lookAt(mid, top), Color3.fromRGB(30, 30, 30), false)
end

local function buildChunk(m: Instance, d: any)
	local u = d.umbrellas or {}
	for i = 1, #u, 5 do umbrella(m, u[i], u[i + 1], u[i + 2], u[i + 3], u[i + 4]) end
	local l = d.lamps or {}
	for i = 1, #l, 4 do promenadeLamp(m, l[i], l[i + 1], l[i + 2], l[i + 3], ((i - 1) / 4) % 2 == 0) end
	local t = d.towers or {}
	for i = 1, #t, 4 do lifeguardTower(m, t[i], t[i + 1], t[i + 2], t[i + 3]) end
	local b = d.boats or {}
	for i = 1, #b, 5 do boat(m, b[i], b[i + 1], b[i + 2], b[i + 3], b[i + 4]) end
	local h = d.huts or {}
	for i = 1, #h, 5 do beachHut(m, h[i], h[i + 1], h[i + 2], h[i + 3], h[i + 4]) end
	local k = d.kites or {}
	for i = 1, #k, 6 do parasail(m, k[i], k[i + 1], k[i + 2], k[i + 3], k[i + 4], k[i + 5]) end
end

function Coast.Build(opts: {only: {string}?, batch: string?}?): string
	local options = (opts or {}) :: any
	local man = manifest()
	local w = world()
	local only = options.only
	if options.batch then
		only = man.batches[options.batch] or error("unknown batch " .. tostring(options.batch))
	end
	local folder = w:FindFirstChild("CoastChunks")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "CoastChunks"
		folder:SetAttribute("Attribution", man.attribution)
		folder:SetAttribute("OsmBase", man.osmBase)
		folder.Parent = w
	end
	local wanted: {[string]: boolean} = {}
	for _, id in only or {} do
		wanted[id] = true
	end
	local built, parts = 0, 0
	for _, id in man.chunks do
		if (only == nil or wanted[id]) and not (folder :: Instance):FindFirstChild("Coast_" .. id) then
			local d = require(data():WaitForChild("chunk_" .. id)) :: any
			local m = Instance.new("Model")
			m.Name = "Coast_" .. id
			m.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
			buildChunk(m, d)
			m:PivotTo(m:GetPivot() + Coast.ORIGIN)
			for _, p in m:GetDescendants() do
				if p:IsA("BasePart") then parts += 1 end
			end
			m.Parent = folder
			built += 1
			task.wait()
		end
	end
	return ("coast: %d chunks built now (%d parts); %d chunks in manifest"):format(built, parts, #man.chunks)
end

function Coast.RemoveIsland()
	local w = workspace:FindFirstChild("PattayaWorld")
	local f = w and w:FindFirstChild("CoastIslands")
	if f then f:Destroy() end
end

function Coast.Remove()
	local w = workspace:FindFirstChild("PattayaWorld")
	local f = w and w:FindFirstChild("CoastChunks")
	if f then f:Destroy() end
	Coast.RemoveIsland()
end

-- terrain --------------------------------------------------------------------------------------------------------
-- Each run is one 4-stud row (z .. z+4) of n 4-stud cells from x0, voxel layers y -16..-4 (3 voxels). One letter per
-- cell indexes manifest.terrain.states = {top, mid, low} materials. Terrain:WriteVoxels writes exactly those cells
-- (full occupancy, Air = 0), nothing else; every region is on the 4-stud grid (x0, z and ORIGIN are multiples of 4).
local function stateTable(man: any): {[string]: {Enum.Material}}
	local out = {}
	for i, tr in man.terrain.states do
		out[string.char(96 + i)] = {(Enum.Material :: any)[tr[1]], (Enum.Material :: any)[tr[2]], (Enum.Material :: any)[tr[3]]}
	end
	return out
end

local function writeRuns(runs: {any}, states: {[string]: {Enum.Material}}, useOld: boolean): number
	local terrain = workspace.Terrain
	local o = Coast.ORIGIN
	local n = 0
	for i = 1, #runs, 4 do
		local z, x0, codes = runs[i], runs[i + 1], if useOld then runs[i + 3] else runs[i + 2]
		local len = #codes
		local mats, occ = table.create(len), table.create(len)
		for c = 1, len do
			local st = states[string.sub(codes, c, c)]
			-- y index 1 = -16..-12 (low), 2 = -12..-8 (mid), 3 = -8..-4 (top)
			local col = {{st[3]}, {st[2]}, {st[1]}}
			local oc = {}
			for y = 1, 3 do
				oc[y] = {if col[y][1] == Enum.Material.Air then 0 else 1}
			end
			mats[c] = col
			occ[c] = oc
		end
		local region = Region3.new(o + Vector3.new(x0, -16, z), o + Vector3.new(x0 + 4 * len, -4, z + 4))
		terrain:WriteVoxels(region, 4, mats, occ)
		n += 1
		if n % 250 == 0 then
			task.wait()
		end
	end
	return n
end

local function terrainModules(man: any, fill: boolean?): {any}
	return if fill then man.terrain.fillModules else man.terrain.modules
end

function Coast.BuildTerrain(opts: {tile: number?, fill: boolean?}?): string
	local options = (opts or {}) :: any
	local man = manifest()
	local terrain = workspace.Terrain
	if terrain:GetAttribute("CoastMudColorBefore") == nil then
		terrain:SetAttribute("CoastMudColorBefore", terrain:GetMaterialColor(Enum.Material.Mud))
	end
	local c = man.terrain.wetSandColor
	terrain:SetMaterialColor(Enum.Material.Mud, Color3.fromRGB(c[1], c[2], c[3])) -- wet sand (Mud is unused elsewhere)
	local states = stateTable(man)
	local mods = terrainModules(man, options.fill)
	local runs, done = 0, 0
	local t0 = os.clock()
	for i, mod in mods do
		if options.tile == nil or options.tile == i then
			local d = require(data():WaitForChild(mod[1])) :: any
			runs += writeRuns(d.runs, states, false)
			done += 1
			task.wait()
		end
	end
	return ("coast terrain%s: %d modules, %d runs written in %.1f s"):format(if options.fill then " (fill)" else "", done, runs, os.clock() - t0)
end

function Coast.RemoveTerrain(opts: {tile: number?, fill: boolean?}?): string
	local options = (opts or {}) :: any
	local man = manifest()
	local states = stateTable(man)
	local runs = 0
	for i, mod in terrainModules(man, options.fill) do
		if options.tile == nil or options.tile == i then
			local d = require(data():WaitForChild(mod[1])) :: any
			runs += writeRuns(d.runs, states, true)
			task.wait()
		end
	end
	local terrain = workspace.Terrain
	local before = terrain:GetAttribute("CoastMudColorBefore")
	if not options.fill and typeof(before) == "Color3" then
		terrain:SetMaterialColor(Enum.Material.Mud, before)
		terrain:SetAttribute("CoastMudColorBefore", nil)
	end
	return ("coast terrain%s: %d runs restored"):format(if options.fill then " (fill)" else "", runs)
end

-- horizon islands --------------------------------------------------------------------------------------------------
-- parts {cx, cz, sx, sz, top}: boxes from y = ISLAND_BASE_Y to `top`, map-local; no terrain, no collision.
function Coast.BuildIsland(opts: {force: boolean?}?): string
	local options = (opts or {}) :: any
	local man = manifest()
	local w = world()
	Coast.RemoveIsland()
	local model = Instance.new("Model")
	model.Name = "CoastIslands"
	model.ModelStreamingMode = Enum.ModelStreamingMode.Persistent -- a horizon must stay visible from far away
	model:SetAttribute("Attribution", man.attribution)
	local n = 0
	for _, isl in man.islands do
		for k, p in isl.parts do
			local top = p[5]
			local size = Vector3.new(p[3], top - ISLAND_BASE_Y, p[4])
			local cf = CFrame.new(Coast.ORIGIN + Vector3.new(p[1], (top + ISLAND_BASE_Y) / 2, p[2]))
			local part = newPart(model, "Island", size, cf, Color3.fromRGB(58, 78, 60):Lerp(Color3.fromRGB(40, 54, 44), math.clamp(top / 400, 0, 1)), false)
			part:SetAttribute("IslandName", isl.name)
			part:SetAttribute("OsmWay", isl.osmWay)
			n += 1
		end
	end
	-- anything else inside an island box (template content near the world origin, RaceMap, ...) -> refuse
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = {model}
	local hits: {string} = {}
	for _, part in model:GetChildren() do
		local p = part :: BasePart
		for _, h in workspace:GetPartBoundsInBox(p.CFrame, p.Size, params) do
			if #hits < 12 then table.insert(hits, h:GetFullName()) end
		end
	end
	if #hits > 0 and not options.force then
		model:Destroy()
		return "island NOT built: " .. #hits .. "+ parts are inside its boxes, e.g. " .. table.concat(hits, ", ")
			.. " (BuildIsland({force = true}) builds it anyway)"
	end
	model.Parent = w
	return ("islands: %d parts built (%d other parts overlapped)"):format(n, #hits)
end

-- probe ----------------------------------------------------------------------------------------------------------
local function isBlocker(p: BasePart): boolean
	local n = p.Name
	return n == "Road" or n == "Sidewalk" or n == "Junction" or n == "Joint" or n == "Roof" or p:GetAttribute("OsmBuilding") ~= nil
end

function Coast.Probe(): string
	local man = manifest()
	local w = world()
	local lines = {}
	-- 1. coast parts touching a road / sidewalk / junction / joint / building part
	local include = {}
	for _, name in {"Chunks", "WideChunks", "Junctions", "WideJunctions"} do
		local f = w:FindFirstChild(name)
		if f then table.insert(include, f) end
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = include
	local checked, touching, examples = 0, 0, {}
	for _, folderName in {"CoastChunks", "CoastIslands"} do
		local f = w:FindFirstChild(folderName)
		for _, d in (if f then f:GetDescendants() else {}) do
			if d:IsA("BasePart") then
				checked += 1
				for _, h in workspace:GetPartsInPart(d, params) do
					if isBlocker(h) then
						touching += 1
						if #examples < 8 then table.insert(examples, d:GetFullName() .. " x " .. h:GetFullName()) end
						break
					end
				end
				if checked % 500 == 0 then task.wait() end
			end
		end
	end
	table.insert(lines, ("parts: %d coast parts checked, %d touch a Road/Sidewalk/Junction/Joint/building part %s")
		:format(checked, touching, table.concat(examples, "; ")))
	-- 2. the sand strip's landward edge (last sand cell, first land cell) is unchanged at the exported sample points
	local o = Coast.ORIGIN
	local ok, bad, badEx = 0, 0, {}
	for _, s in man.terrain.probe do
		local x, z, want = s[1], s[2], s[3]
		local region = Region3.new(o + Vector3.new(x - 2, -8, z - 2), o + Vector3.new(x + 2, -4, z + 2))
		local mats = workspace.Terrain:ReadVoxels(region, 4)
		local got = mats[1][1][1]
		if got == (Enum.Material :: any)[want] then
			ok += 1
		else
			bad += 1
			if #badEx < 8 then table.insert(badEx, ("(%d, %d) want %s got %s"):format(x, z, want, got.Name)) end
		end
	end
	table.insert(lines, ("landward edge: %d of %d sample cells unchanged %s"):format(ok, ok + bad, table.concat(badEx, "; ")))
	-- 3. the default pass is in place: first cell of every 40th run has its new top material
	local states = stateTable(man)
	local applied, total = 0, 0
	for _, mod in man.terrain.modules do
		local runs = (require(data():WaitForChild(mod[1])) :: any).runs
		for i = 1, #runs, 160 do
			local z, x0, code = runs[i], runs[i + 1], string.sub(runs[i + 2], 1, 1)
			local mats = workspace.Terrain:ReadVoxels(Region3.new(o + Vector3.new(x0, -8, z), o + Vector3.new(x0 + 4, -4, z + 4)), 4)
			total += 1
			if mats[1][1][1] == states[code][1] then applied += 1 end
		end
	end
	table.insert(lines, ("shoreline: %d of %d sampled runs carry the new top material"):format(applied, total))
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

return Coast
