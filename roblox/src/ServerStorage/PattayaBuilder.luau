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
	swSide: number?, -- wide world: only this side (-1 / 1) gets a sidewalk (the other lies on a parallel road)
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

local function buildEdge(chunk: Instance, e: Edge, junctionR: {[number]: number}, dashGap: number?)
	local gap = dashGap or 12 -- the wide-world extension uses sparser dashes (manifest.dashGap)
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
				dashes(road, offset(inner, (k - e.lanes / 2) * e.width / e.lanes), 8, gap, 0.5, COLORS.lane)
			end
		else
			stripe(road, "Centre", offset(inner, -0.5), 0.45, ROAD_TOP + MARK_THICK, MARK_THICK, COLORS.centre, false)
			stripe(road, "Centre", offset(inner, 0.5), 0.45, ROAD_TOP + MARK_THICK, MARK_THICK, COLORS.centre, false)
			local perSide = math.floor(e.lanes / 2)
			for k = 1, perSide - 1 do
				local d = k * e.width / e.lanes
				dashes(road, offset(inner, d), 8, gap, 0.5, COLORS.lane)
				dashes(road, offset(inner, -d), 8, gap, 0.5, COLORS.lane)
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
				if e.swSide == nil or e.swSide == side then
					stripe(road, "Sidewalk", offset(sw, side * (e.width + e.sidewalk) / 2), e.sidewalk, ROAD_TOP + CURB, ROAD_THICK + CURB, COLORS.sidewalk, true)
				end
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
		local facade = if h >= (man.facadeMinHeight or 0) then FACADE_OF[palette] else nil
		if facade then
			for _, face in FACES do
				local t = Instance.new("Texture")
				t.Texture = man.facades[facade]
				t.Face = face
				t.StudsPerTileV = level
				t.StudsPerTileU = if facade == "shophouse" then level * 1.3 else level * 1.1
				t.OffsetStudsV = (h % level) -- full floors line up with the top
				t:SetAttribute("Facade", facade) -- PattayaNightLights swaps to the lit night tile after dark
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

-- Props: palms (trunk + 5 fronds) on the sea side of Beach Road, street lights (pole + arm + lamp) on main roads.
-- No collision on fronds/arms/lamps; trunks and poles collide so cars can't drive through them.
local PALM_TRUNK = Color3.fromRGB(120, 92, 64)
local PALM_LEAF = Color3.fromRGB(58, 140, 60)
local POLE = Color3.fromRGB(70, 72, 78)
local LAMP = Color3.fromRGB(255, 236, 190)

local SIGN_COLORS = {Color3.fromRGB(255, 50, 170), Color3.fromRGB(0, 220, 255), Color3.fromRGB(255, 200, 40),
	Color3.fromRGB(140, 90, 255), Color3.fromRGB(80, 255, 120)}

local function buildProps(chunk: Instance, palms: {number}, lights: {number}, signs: {number})
	if #palms == 0 and #lights == 0 and #signs == 0 then
		return
	end
	local folder = Instance.new("Model")
	folder.Name = "Props"
	for i = 1, #palms, 2 do
		local x, z = palms[i], palms[i + 1]
		local h = 26 + ((x * 7 + z * 13) % 9) -- deterministic height variation
		local lean = math.rad(((x + z) % 10) - 5)
		local base = CFrame.new(x, ROAD_TOP - 1, z) * CFrame.Angles(lean, (x * 3) % 6.28, 0)
		local trunk = newPart(folder, "PalmTrunk", Vector3.new(h, 1.6, 1.6), base * CFrame.new(0, h / 2, 0) * CFrame.Angles(0, 0, math.rad(90)), PALM_TRUNK, true)
		trunk.Shape = Enum.PartType.Cylinder
		local top = base * CFrame.new(0, h, 0)
		for k = 0, 4 do
			local frond = newPart(folder, "PalmFrond", Vector3.new(2.2, 0.4, 13), top * CFrame.Angles(0, k * math.rad(72), 0) * CFrame.Angles(math.rad(-22), 0, 0) * CFrame.new(0, 0, -6), PALM_LEAF, false)
			frond.CanQuery = false
		end
	end
	for i = 1, #lights, 4 do
		local x, z, dx, dz = lights[i], lights[i + 1], lights[i + 2], lights[i + 3]
		local base = CFrame.lookAt(Vector3.new(x, ROAD_TOP, z), Vector3.new(x + dx, ROAD_TOP, z + dz))
		newPart(folder, "LightPole", Vector3.new(0.7, 20, 0.7), base * CFrame.new(0, 10, 0), POLE, true)
		local arm = newPart(folder, "LightArm", Vector3.new(0.4, 0.4, 7), base * CFrame.new(0, 19.8, -3.5), POLE, false)
		arm.CanQuery = false
		local lamp = newPart(folder, "Lamp", Vector3.new(1.6, 0.5, 2.6), base * CFrame.new(0, 19.4, -6.6), LAMP, false)
		lamp.Material = Enum.Material.SmoothPlastic -- PattayaNightLights makes it Neon and lights it after dark
		lamp.CanQuery = false
		if (i - 1) / 4 % 2 == 0 then -- a real light on every second lamp keeps the light count down
			local light = Instance.new("SpotLight")
			light.Face = Enum.NormalId.Bottom
			light.Angle = 110
			light.Range = 38
			light.Brightness = 2.2
			light.Color = Color3.fromRGB(255, 220, 170)
			light.Shadows = false
			light.Enabled = false
			light.Parent = lamp
		end
	end
	for i = 1, #signs, 8 do
		local x, z, nx, nz, w, h, y, ci = signs[i], signs[i + 1], signs[i + 2], signs[i + 3], signs[i + 4], signs[i + 5], signs[i + 6], signs[i + 7]
		local cf = CFrame.lookAt(Vector3.new(x, ROAD_TOP - 1 + y + h / 2, z), Vector3.new(x + nx, ROAD_TOP - 1 + y + h / 2, z + nz))
		local sign = newPart(folder, "NeonSign", Vector3.new(w, h, 0.6), cf, SIGN_COLORS[ci], false)
		sign.Material = Enum.Material.Neon
		sign.CanQuery = false
		local frame = newPart(folder, "SignFrame", Vector3.new(w + 0.8, h + 0.8, 0.4), cf * CFrame.new(0, 0, 0.35), Color3.fromRGB(25, 25, 30), false)
		frame.CanQuery = false
	end
	folder.Parent = chunk
end

-- Roadside direction signs (manifest.signs = {{x, z, dx, dz, text}}, map-local; dx, dz = direction of travel): a
-- grey post and a green board facing the oncoming drivers, text on a SurfaceGui. Original artwork (plain colours and
-- text, no real-world sign design copied). Built anchored, the board does not collide.
local SIGN_BOARD = Color3.fromRGB(18, 96, 60)
local function buildRoadSigns(folder: Instance, signs: {any})
	for _, s in signs do
		local x, z, dx, dz, text = s[1], s[2], s[3], s[4], s[5]
		local pos = Vector3.new(x, ROAD_TOP - 1, z)
		local face = CFrame.lookAt(pos, pos - Vector3.new(dx, 0, dz)) -- front face looks back down the road
		local sign = Instance.new("Model")
		sign.Name = "RoadSign"
		sign:SetAttribute("Text", text)
		newPart(sign, "SignPost", Vector3.new(0.8, 16, 0.8), face * CFrame.new(0, 8, 0), POLE, true)
		local board = newPart(sign, "SignBoard", Vector3.new(16, 5, 0.4), face * CFrame.new(0, 13.5, -0.6), SIGN_BOARD, false)
		board.CanQuery = false
		local gui = Instance.new("SurfaceGui")
		gui.Face = Enum.NormalId.Front
		gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
		gui.PixelsPerStud = 32
		gui.LightInfluence = 0.2 -- readable at night without its own light
		local label = Instance.new("TextLabel")
		label.Size = UDim2.fromScale(1, 1)
		label.BackgroundTransparency = 1
		label.Text = text
		label.TextColor3 = Color3.fromRGB(255, 255, 255)
		label.Font = Enum.Font.GothamBold
		label.TextScaled = true
		label.Parent = gui
		local pad = Instance.new("UIPadding")
		pad.PaddingLeft = UDim.new(0.05, 0)
		pad.PaddingRight = UDim.new(0.05, 0)
		pad.PaddingTop = UDim.new(0.12, 0)
		pad.PaddingBottom = UDim.new(0.12, 0)
		pad.Parent = label
		local stroke = Instance.new("UIStroke") -- white border line around the board
		stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		stroke.Color = Color3.fromRGB(255, 255, 255)
		stroke.Thickness = 4
		local frame = Instance.new("Frame")
		frame.Size = UDim2.new(1, -12, 1, -12)
		frame.Position = UDim2.fromOffset(6, 6)
		frame.BackgroundTransparency = 1
		stroke.Parent = frame
		frame.Parent = gui
		gui.Parent = board
		sign.Parent = folder
	end
end

-- Landmark proxies (handcrafted, separate from procedural buildings).
local function buildLandmarks(world: Instance, man: any)
	if not man.landmarks then
		return
	end
	local folder = Instance.new("Folder")
	folder.Name = "Landmarks"
	for _, lm in man.landmarks do
		local model = Instance.new("Model")
		model.Name = lm.id
		model:SetAttribute("Source", lm.source)
		if lm.kind == "gate" then
			-- an arch spanning the road with a neon name board, like the Walking Street entrance sign
			local fwd = Vector3.new(lm.dx, 0, lm.dz).Unit
			local cf = CFrame.lookAt(Vector3.new(lm.x, ROAD_TOP, lm.z), Vector3.new(lm.x, ROAD_TOP, lm.z) + fwd)
			local half = lm.span / 2
			for _, s in {-1, 1} do
				newPart(model, "Pillar", Vector3.new(3, 30, 3), cf * CFrame.new(s * half, 15, 0), Color3.fromRGB(40, 40, 48), true)
			end
			newPart(model, "Beam", Vector3.new(lm.span + 3, 3, 3), cf * CFrame.new(0, 31.5, 0), Color3.fromRGB(40, 40, 48), true)
			local board = newPart(model, "Board", Vector3.new(lm.span * 0.7, 7, 1), cf * CFrame.new(0, 26, 0), Color3.fromRGB(20, 20, 30), false)
			for _, face in {Enum.NormalId.Front, Enum.NormalId.Back} do
				local gui = Instance.new("SurfaceGui")
				gui.Face = face
				gui.LightInfluence = 0
				gui.Brightness = 2
				gui.PixelsPerStud = 20
				local label = Instance.new("TextLabel")
				label.Size = UDim2.fromScale(1, 1)
				label.BackgroundTransparency = 1
				label.Text = lm.label
				label.TextScaled = true
				label.Font = Enum.Font.GothamBlack
				label.TextColor3 = Color3.fromRGB(255, 70, 200)
				label.TextStrokeColor3 = Color3.fromRGB(120, 230, 255)
				label.TextStrokeTransparency = 0.2
				label.Parent = gui
				gui.Parent = board
			end
			for _, s in {-1, 1} do
				local strip = newPart(model, "Neon", Vector3.new(lm.span * 0.72, 0.4, 1.2), cf * CFrame.new(0, 26 + s * 3.8, 0), Color3.fromRGB(120, 230, 255), false)
				strip.Material = Enum.Material.Neon
			end
		end
		model:PivotTo(model:GetPivot() + Builder.ORIGIN)
		model.Parent = folder
	end
	folder.Parent = world
end

-- Race infrastructure from the generated layout: checkpoint gates (invisible trigger plane + visible arch posts),
-- start grid slots and the Pattaya spawn. The race logic itself lives in PattayaRaceServer / PattayaRaceClient.
local function buildRace(world: Instance, man: any)
	local race = man.race
	if not race then
		return
	end
	local folder = Instance.new("Folder")
	folder.Name = "Race"
	folder:SetAttribute("RaceId", race.id)
	folder:SetAttribute("RaceName", race.name)
	folder:SetAttribute("Laps", race.laps)
	folder:SetAttribute("LengthStuds", race.lengthStuds)
	-- route centreline (world coordinates) for GPS / minimap / tests: packed x,z pairs in a buffer-free string
	local packed = table.create(#race.path)
	for i = 1, #race.path, 2 do
		table.insert(packed, ("%.1f,%.1f"):format(race.path[i] + Builder.ORIGIN.X, race.path[i + 1] + Builder.ORIGIN.Z))
	end
	folder:SetAttribute("Path", table.concat(packed, ";"))
	-- the place has instance streaming on: checkpoint gates must always exist on every client (HUD + next-gate glow)
	local cps = Instance.new("Model")
	cps.Name = "Checkpoints"
	cps.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	cps.Parent = folder
	for i, c in race.checkpoints do
		local fwd = Vector3.new(c.dx, 0, c.dz).Unit
		local cf = CFrame.lookAt(Vector3.new(c.x, ROAD_TOP + 10, c.z), Vector3.new(c.x, ROAD_TOP + 10, c.z) + fwd)
		local gate = newPart(cps, "CP" .. i, Vector3.new(c.w, 20, 2), cf, Color3.fromRGB(0, 200, 255), false)
		gate.Transparency = 1
		gate.CanQuery = false
		gate:SetAttribute("Index", i)
		for _, s in {-1, 1} do
			local post = newPart(gate, "Post", Vector3.new(1.2, 18, 1.2), cf * CFrame.new(s * c.w / 2, -1, 0), if i == 1 then Color3.fromRGB(255, 255, 255) else Color3.fromRGB(0, 200, 255), false)
			post.Material = Enum.Material.Neon
			post.CanQuery = false
		end
	end
	local grid = Instance.new("Model")
	grid.Name = "StartGrid"
	grid.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	grid.Parent = folder
	for i, s in race.grid do
		local slot = newPart(grid, "Slot" .. i, Vector3.new(9, 0.1, 17), CFrame.lookAt(Vector3.new(s.x, ROAD_TOP + 0.06, s.z), Vector3.new(s.x + s.dx, ROAD_TOP + 0.06, s.z + s.dz)), Color3.fromRGB(255, 255, 255), false)
		slot.Transparency = 0.5
		slot.CanQuery = false
	end
	local spawn = Instance.new("SpawnLocation")
	spawn.Name = "PattayaSpawn"
	spawn.Anchored = true
	spawn.Size = Vector3.new(12, 1, 12)
	spawn.CFrame = CFrame.new(man.spawn.x, ROAD_TOP + 0.5, man.spawn.z)
	spawn.Color = Color3.fromRGB(0, 170, 255)
	spawn.Material = Enum.Material.SmoothPlastic -- Neon bloomed over the whole screen at night
	spawn.Transparency = 0.3
	spawn.Duration = 0
	spawn.CanQuery = false -- cars drive over it on their suspension rays
	spawn.Parent = folder
	for _, d in folder:GetDescendants() do
		if d:IsA("BasePart") then
			d.CFrame += Builder.ORIGIN
		end
	end
	folder.Parent = world
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
	for kind, id in man.facades do world:SetAttribute("Facade_" .. kind, id) end
	for kind, id in man.facadesNight do world:SetAttribute("FacadeNight_" .. kind, id) end
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
		buildProps(chunk, chunkData.palms or {}, chunkData.lights or {}, chunkData.signs or {})
		chunk:PivotTo(chunk:GetPivot() + Builder.ORIGIN)
		for _, d in chunk:GetDescendants() do
			if d:IsA("BasePart") then count += 1 end
		end
		chunk.Parent = chunksFolder
		task.wait()
	end
	buildLandmarks(world, man)
	buildRace(world, man)
	if options.terrain ~= false then
		buildTerrain(man)
	end
	return ("%d chunks, %d road parts, %d junctions"):format(#man.chunks, count, #man.junctions)
end

-- Wide world (tools/mapgen config pattaya_wide): ADDS new chunks around the tested slice. Nothing that Build() made
-- is rebuilt or moved; terrain is written only outside manifest.baseFrame (in 2048-stud tiles).
-- NOT TESTED IN STUDIO YET. Data: ServerStorage.PattayaDataWide (manifest + chunk_* from build/pattaya_wide/roblox).
--   local B = require(game.ServerStorage.PattayaBuilder)
--   B.Extend({roads = false})                              -- terrain only (ground + sea outside the base frame)
--   B.Extend({terrain = false, batch = "seam"})            -- chunks touching the slice, then each district batch
--   B.Extend({terrain = false})                            -- everything left; built chunks are skipped (resumable)
--   B.Extend({roads = false, terrain = false, removeBaseConflicts = true}) -- remove the seam buildings it lists
--   B.RemoveExtension()                                    -- undo: wide chunks, discs and wide terrain
--   B.Extend({terrain = false, only = {}})                 -- no chunks: adds missing junction/joint discs and road signs
--   (an existing WideJunctions model only gets the discs it lacks; a data folder with `signs` gets RoadSigns_<name>)
local function extendTerrain(man: any)
	local terrain = workspace.Terrain
	local o = Builder.ORIGIN
	local function replace(x0: number, x1: number, z0: number, z1: number, y0: number, y1: number, from: Enum.Material, to: Enum.Material)
		local region = Region3.new(o + Vector3.new(x0, y0, z0), o + Vector3.new(x1, y1, z1)):ExpandToGrid(4)
		terrain:ReplaceMaterial(region, 4, from, to)
	end
	local TILE = 2048
	for _, r in man.groundRects do
		local rx0, rx1, rz0, rz1 = r[1], r[2], r[3], r[4]
		for x0 = rx0, rx1 - 1, TILE do
			for z0 = rz0, rz1 - 1, TILE do
				local x1, z1 = math.min(x0 + TILE, rx1), math.min(z0 + TILE, rz1)
				for _, m in {Enum.Material.Ground, Enum.Material.Sand, Enum.Material.Water} do
					replace(x0, x1, z0, z1, -16, 8, m, Enum.Material.Air)
				end
				terrain:FillBlock(CFrame.new(o + Vector3.new((x0 + x1) / 2, -10, (z0 + z1) / 2)), Vector3.new(x1 - x0, 12, z1 - z0), Enum.Material.Ground)
				task.wait()
			end
		end
	end
	for i, row in man.sea do
		local r = row.runs -- triples: x0, x1, sand strip (1/0); rows are row.h tall (16, or 4..12 at the base frame edge)
		local z1 = row.z + (row.h or man.seaCell)
		for k = 1, #r, 3 do
			local x0, x1 = r[k], r[k + 1]
			replace(x0, x1, row.z, z1, -16, -4, Enum.Material.Ground, Enum.Material.Water)
			if r[k + 2] == 1 then
				replace(x1, x1 + 48, row.z, z1, -8, -4, Enum.Material.Ground, Enum.Material.Sand)
			end
		end
		if i % 40 == 0 then
			task.wait()
		end
	end
end

function Builder.Extend(opts: {folder: string?, terrain: boolean?, roads: boolean?, only: {string}?, batch: string?,
	removeBaseConflicts: boolean?}?)
	local options = opts or {}
	local data = game:GetService("ServerStorage"):WaitForChild(options.folder or "PattayaDataWide")
	local man = require(data:WaitForChild("manifest")) :: any
	if options.batch then -- "seam", then the districts in man.batchOrder
		options.only = man.batches[options.batch] or error("unknown batch " .. options.batch)
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	if not world then
		error("PattayaBuilder.Extend: build the base slice first (PattayaBuilder.Build())")
	end
	world:SetAttribute("WideWorld", man.name)
	world:SetAttribute("WideOsmBase", man.osmBase)
	local junctionR: {[number]: number} = {}
	for _, j in man.seamJunctions do
		junctionR[j.id] = j.r
	end
	for _, j in man.junctions do
		junctionR[j.id] = j.r
	end
	local built, parts = 0, 0
	if options.roads ~= false then
		-- junction discs (manifest.junctions) and joint discs (optional `joints` module: osmNode, x, z, r) go into
		-- WideJunctions. When it already exists (an earlier Extend, or another data folder such as the corridor),
		-- only the discs it does not have yet are added, so a later dataset's discs are no longer skipped.
		local existing = world:FindFirstChild("WideJunctions")
		local have: {[string]: boolean} = {}
		if existing then
			for _, p in existing:GetChildren() do
				local id = p:GetAttribute("OsmNode")
				if id then
					have[p.Name .. ":" .. tostring(id)] = true
				end
			end
		end
		local junctions = Instance.new("Model")
		junctions.Name = "WideJunctions"
		local function disc(kind: string, id: number, x: number, z: number, r: number)
			if have[kind .. ":" .. tostring(id)] then
				return
			end
			local cf = CFrame.new(x, ROAD_TOP - ROAD_THICK / 2 - 0.01, z) * CFrame.Angles(0, 0, math.rad(90))
			local p = newPart(junctions, kind, Vector3.new(ROAD_THICK, r * 2, r * 2), cf, COLORS.junction, true)
			p.Shape = Enum.PartType.Cylinder
			p:SetAttribute("OsmNode", id)
		end
		for _, j in man.junctions do
			disc("Junction", j.id, j.x, j.z, j.r)
		end
		local jointsModule = data:FindFirstChild("joints")
		if jointsModule then
			local rows = require(jointsModule) :: any
			for i = 1, #rows, 4 do
				disc("Joint", rows[i], rows[i + 1], rows[i + 2], rows[i + 3])
			end
		end
		if not existing then
			junctions:PivotTo(junctions:GetPivot() + Builder.ORIGIN)
			junctions.Parent = world
		else
			for _, p in junctions:GetChildren() do
				(p :: BasePart).Position += Builder.ORIGIN
				p.Parent = existing
			end
			junctions:Destroy()
		end
		local folder = world:FindFirstChild("WideChunks")
		if not folder then
			folder = Instance.new("Folder")
			folder.Name = "WideChunks"
			folder.Parent = world
		end
		local wanted: {[string]: boolean} = {}
		for _, id in options.only or {} do
			wanted[id] = true
		end
		for _, id in man.chunks do
			if (options.only == nil or wanted[id]) and not (folder :: Instance):FindFirstChild("Chunk_" .. id) then
				local chunkData = require(data:WaitForChild("chunk_" .. id)) :: any
				local chunk = Instance.new("Model")
				chunk.Name = "Chunk_" .. id
				chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
				for _, e in chunkData.edges do
					buildEdge(chunk, e :: Edge, junctionR, man.dashGap)
				end
				buildBuildings(chunk, chunkData.buildings or {}, man)
				buildProps(chunk, chunkData.palms or {}, chunkData.lights or {}, chunkData.signs or {})
				chunk:PivotTo(chunk:GetPivot() + Builder.ORIGIN)
				for _, d in chunk:GetDescendants() do
					if d:IsA("BasePart") then parts += 1 end
				end
				chunk.Parent = folder
				built += 1
				task.wait()
			end
		end
	end
	if options.roads ~= false and man.signs and #man.signs > 0 then
		local name = "RoadSigns_" .. man.name -- one model per data folder; rebuilt only when it is missing
		if not world:FindFirstChild(name) then
			local signs = Instance.new("Model")
			signs.Name = name
			buildRoadSigns(signs, man.signs)
			signs:PivotTo(signs:GetPivot() + Builder.ORIGIN)
			signs.Parent = world
		end
	end
	local removed = 0
	if options.removeBaseConflicts and man.baseBuildingConflicts then
		local ids = {}
		for _, id in man.baseBuildingConflicts do
			ids[id] = true
		end
		local base = world:FindFirstChild("Chunks")
		if base then
			for _, d in base:GetDescendants() do
				if d:IsA("BasePart") and ids[d:GetAttribute("OsmBuilding")] and d.Parent then
					-- the roof slab of a tall building is a sibling at the same x/z (no attribute)
					for _, s in (d.Parent :: Instance):GetChildren() do
						if s:IsA("BasePart") and s.Name == "Roof" and math.abs(s.Position.X - d.Position.X) < 0.05
							and math.abs(s.Position.Z - d.Position.Z) < 0.05 then
							s:Destroy()
						end
					end
					d:Destroy()
					removed += 1
				end
			end
		end
	end
	if options.terrain ~= false then
		extendTerrain(man)
	end
	return ("wide: %d chunks built now (%d parts), %d base buildings removed; %d chunks in manifest"):format(built, parts, removed, #man.chunks)
end

-- Undo Extend(): removes the wide chunks/discs and clears the wide terrain rectangles (the base slice is untouched;
-- base buildings removed with removeBaseConflicts come back only with a full Build()).
function Builder.RemoveExtension(folderName: string?)
	local world = workspace:FindFirstChild("PattayaWorld")
	if world then
		for _, n in {"WideChunks", "WideJunctions", "RoadSigns_bira_corridor"} do
			local f = world:FindFirstChild(n)
			if f then f:Destroy() end
		end
		world:SetAttribute("WideWorld", nil)
		world:SetAttribute("WideOsmBase", nil)
	end
	local data = game:GetService("ServerStorage"):FindFirstChild(folderName or "PattayaDataWide")
	if data then
		local man = require(data:WaitForChild("manifest")) :: any
		local o = Builder.ORIGIN
		for _, r in man.groundRects do
			for x0 = r[1], r[2] - 1, 2048 do
				for z0 = r[3], r[4] - 1, 2048 do
					local region = Region3.new(o + Vector3.new(x0, -16, z0), o + Vector3.new(math.min(x0 + 2048, r[2]), 8, math.min(z0 + 2048, r[4]))):ExpandToGrid(4)
					for _, m in {Enum.Material.Ground, Enum.Material.Sand, Enum.Material.Water} do
						workspace.Terrain:ReplaceMaterial(region, 4, m, Enum.Material.Air)
					end
					task.wait()
				end
			end
		end
	end
end

return Builder
