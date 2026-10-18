--!strict
-- Street furniture layer for the Pattaya city (MIDNIGHT PATTAYA): traffic lights, zebra crossings, bilingual road
-- name signs, bus shelters, motorbike-taxi / taxi stands and utility poles. Built in Studio (edit time) from the data
-- modules in ServerStorage.PattayaDataFurniture (tools/mapgen/furniture.py -> build/furniture/roblox: manifest +
-- chunk_f<cx>_<cz>). Every chunk becomes an Atomic Model workspace.PattayaWorld.FurnitureChunks.Chunk_f<cx>_<cz>.
-- Nothing else in the place is touched. Built chunks are skipped, so a call can be repeated after an error.
--   local F = require(game.ServerStorage.PattayaFurnitureBuilder)
--   F.Build({batch = "f1"})                    -- one batch (<= 8 chunks), then "f2" ... (manifest.batchOrder)
--   F.Build({only = {"f0_1", "f1_1"}})          -- explicit chunk ids
--   F.Build()                                   -- everything left (the leader builds in batches instead)
--   F.Remove()                                  -- undo: destroys FurnitureChunks only
-- Geometry must match parts_of() in tools/mapgen/furniture.py (the exporter's overlap checks use the same shapes).
-- Map-local coordinates (x, z) + ORIGIN, like PattayaBuilder. Original, generic artwork: plain colours and text, no
-- logos or brands; road and stop names are the OSM `name` / `name:en` tags (Map data (c) OpenStreetMap contributors).
-- Parts that hang over the road (signal arms / heads) and every non-structural detail are CanCollide = false and
-- CanQuery = false; zebra stripes (attribute onRoad = true) lie flat on the slab (0.05 thick, top at y 1.07) with
-- CanCollide / CanQuery false, so they never form a bump or catch the car's suspension raycasts.
local ServerStorage = game:GetService("ServerStorage")

local Furniture = {}

Furniture.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN
local ROAD_TOP = 1.0
local GROUND_Y = -2.0 -- terrain surface beside the roads
local CURB_TOP = ROAD_TOP + 0.6 -- sidewalk top (PattayaBuilder CURB)
local CROSS_Y = ROAD_TOP + 0.045 -- zebra bar centre: bars span y 1.02 .. 1.07 (lane markings end at 1.05)
local CROSS_THICK = 0.05

local C = {
	signal = Color3.fromRGB(70, 74, 80),
	housing = Color3.fromRGB(28, 30, 34),
	red = Color3.fromRGB(255, 40, 40),
	amber = Color3.fromRGB(255, 170, 20),
	green = Color3.fromRGB(40, 255, 120),
	off = Color3.fromRGB(46, 40, 38),
	stripe = Color3.fromRGB(240, 240, 236),
	signBlue = Color3.fromRGB(0, 72, 150),
	post = Color3.fromRGB(150, 152, 156),
	pad = Color3.fromRGB(170, 168, 160),
	shelter = Color3.fromRGB(196, 200, 206),
	glass = Color3.fromRGB(150, 190, 210),
	roof = Color3.fromRGB(40, 92, 150),
	bench = Color3.fromRGB(120, 92, 64),
	orange = Color3.fromRGB(255, 122, 20),
	dark = Color3.fromRGB(26, 28, 34),
	concrete = Color3.fromRGB(150, 148, 142),
	wire = Color3.fromRGB(30, 30, 32),
}
local LAMP_ON = {C.red, C.amber, C.green}

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
	p.CanQuery = collide -- details stay out of raycasts (car suspension, probes)
	p.CanTouch = false
	p.CastShadow = false
	p.Parent = parent
	return p
end

-- text on one or both faces of a board; lines = {{text, heightFraction}} stacked from the top
local function boardText(board: BasePart, lines: {{any}}, color: Color3, faces: {Enum.NormalId})
	for _, face in faces do
		local gui = Instance.new("SurfaceGui")
		gui.Face = face
		gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
		gui.PixelsPerStud = 32
		gui.LightInfluence = 0.2 -- readable at night without its own light
		local y = 0
		for _, ln in lines do
			local label = Instance.new("TextLabel")
			label.BackgroundTransparency = 1
			label.Position = UDim2.fromScale(0, y)
			label.Size = UDim2.fromScale(1, ln[2])
			label.Text = ln[1]
			label.TextColor3 = color
			label.Font = Enum.Font.GothamBold -- Thai glyphs come from Roblox's font fallback
			label.TextScaled = true
			local pad = Instance.new("UIPadding")
			pad.PaddingLeft = UDim.new(0.05, 0)
			pad.PaddingRight = UDim.new(0.05, 0)
			pad.PaddingTop = UDim.new(0.08, 0)
			pad.PaddingBottom = UDim.new(0.08, 0)
			pad.Parent = label
			label.Parent = gui
			y += ln[2]
		end
		local stroke = Instance.new("UIStroke") -- thin white border, Thai street-sign style (generic)
		stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		stroke.Color = Color3.fromRGB(255, 255, 255)
		stroke.Thickness = 3
		local frame = Instance.new("Frame")
		frame.Size = UDim2.new(1, -8, 1, -8)
		frame.Position = UDim2.fromOffset(4, 4)
		frame.BackgroundTransparency = 1
		stroke.Parent = frame
		frame.Parent = gui
		gui.Parent = board
	end
end
local BOTH = {Enum.NormalId.Front, Enum.NormalId.Back}

-- signals {x, z, ax, az, arm, hx, hz, lit}: 6 Parts (pole, arm, head, 3 lamps); the lit lamp is NightNeon
local function buildSignals(folder: Instance, rows: {number})
	for i = 1, #rows, 8 do
		local x, z, ax, az, arm, hx, hz, lit = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 4], rows[i + 5], rows[i + 6], rows[i + 7]
		local a = Vector3.new(ax, 0, az).Unit
		local h = Vector3.new(hx, 0, hz).Unit
		local p = Vector3.new(x, 0, z)
		newPart(folder, "SignalPole", Vector3.new(0.8, 18, 0.8), CFrame.new(x, GROUND_Y + 9, z), C.signal, true)
		local head = p + a * arm
		local mid = p + a * (arm / 2)
		newPart(folder, "SignalArm", Vector3.new(0.4, 0.4, arm), CFrame.lookAt(Vector3.new(mid.X, 15.5, mid.Z), Vector3.new(head.X, 15.5, head.Z)), C.signal, false)
		local hc = Vector3.new(head.X, 13.2, head.Z)
		local hcf = CFrame.lookAt(hc, hc + h) -- front (-Z) faces the oncoming drivers
		newPart(folder, "SignalHead", Vector3.new(1.5, 4.2, 1.0), hcf, C.housing, false)
		for k, dy in {1.35, 0, -1.35} do
			local on = k == lit
			local lamp = newPart(folder, "SignalLamp", Vector3.new(1.0, 1.0, 0.2), hcf * CFrame.new(0, dy, -0.55), if on then LAMP_ON[k] else C.off, false)
			if on then
				lamp.Material = Enum.Material.Neon
				lamp:SetAttribute("NightNeon", true) -- PattayaNightLights: Neon + NightColor at night, SmoothPlastic + DayColor by day
				lamp:SetAttribute("DayColor", LAMP_ON[k])
				lamp:SetAttribute("NightColor", LAMP_ON[k])
			end
		end
	end
end

-- crossings {x, z, tx, tz, n, barW, gap, depth}: n flat bars across the road, long side along the road
local function buildCrossings(folder: Instance, rows: {number})
	for i = 1, #rows, 8 do
		local x, z, tx, tz, n, bw, gap, depth = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 4], rows[i + 5], rows[i + 6], rows[i + 7]
		local t = Vector3.new(tx, 0, tz).Unit
		local across = Vector3.new(-t.Z, 0, t.X)
		for k = 1, n do
			local c = Vector3.new(x, CROSS_Y, z) + across * ((k - (n + 1) / 2) * (bw + gap))
			local s = newPart(folder, "ZebraStripe", Vector3.new(bw, CROSS_THICK, depth), CFrame.lookAt(c, c + t), C.stripe, false)
			s:SetAttribute("onRoad", true)
		end
	end
end

-- nameSigns {{x, z, tx, tz, nameTh, nameEn}}: post + blue board parallel to the named road, readable from both sides
local function buildNameSigns(folder: Instance, rows: {any})
	for _, r in rows do
		local x, z, tx, tz, th, en = r[1], r[2], r[3], r[4], r[5], r[6]
		newPart(folder, "NameSignPost", Vector3.new(0.6, 9.4, 0.6), CFrame.new(x, GROUND_Y + 4.7, z), C.post, true)
		local c = Vector3.new(x, 9.0, z)
		local board = newPart(folder, "NameSignBoard", Vector3.new(10, 3.2, 0.3), CFrame.lookAt(c, c + Vector3.new(-tz, 0, tx)), C.signBlue, false)
		if th ~= "" then board:SetAttribute("NameTh", th) end
		if en ~= "" then board:SetAttribute("NameEn", en) end
		local lines = if th ~= "" and en ~= "" then {{th, 0.56}, {en, 0.44}} else {{if th ~= "" then th else en, 1}}
		boardText(board, lines, Color3.fromRGB(255, 255, 255), BOTH)
	end
end

-- shelters {{x, z, nx, nz, label}}: pad, back wall, 2 posts, roof, bench, bus-stop pole + sign (8 Parts)
local SW, SD = 12, 5
local function buildShelters(folder: Instance, rows: {any})
	for _, r in rows do
		local x, z, nx, nz, label = r[1], r[2], r[3], r[4], r[5]
		local base = CFrame.lookAt(Vector3.new(x, 0, z), Vector3.new(x + nx, 0, z + nz)) -- -Z = towards the road
		newPart(folder, "ShelterPad", Vector3.new(SW, CURB_TOP - GROUND_Y, SD), base * CFrame.new(0, (CURB_TOP + GROUND_Y) / 2, 0), C.pad, true)
		local wall = newPart(folder, "ShelterWall", Vector3.new(SW, 6.4, 0.3), base * CFrame.new(0, CURB_TOP + 3.4, SD / 2 - 0.3), C.glass, true)
		wall.Transparency = 0.35
		for _, sx in {-1, 1} do
			newPart(folder, "ShelterPost", Vector3.new(0.4, 7.6, 0.4), base * CFrame.new(sx * (SW / 2 - 0.5), CURB_TOP + 3.8, -(SD / 2 - 0.5)), C.shelter, true)
		end
		newPart(folder, "ShelterRoof", Vector3.new(SW + 1, 0.4, SD + 1.2), base * CFrame.new(0, CURB_TOP + 7.8, 0), C.roof, false)
		newPart(folder, "ShelterBench", Vector3.new(SW - 3, 0.5, 1.4), base * CFrame.new(0, CURB_TOP + 1.6, SD / 2 - 1.3), C.bench, true)
		newPart(folder, "BusSignPole", Vector3.new(0.4, 10, 0.4), base * CFrame.new(SW / 2 + 1, GROUND_Y + 5, -(SD / 2 - 0.4)), C.post, true)
		local sign = newPart(folder, "BusSign", Vector3.new(2.4, 2.4, 0.2),
			base * CFrame.new(SW / 2 + 1, 7.4, -(SD / 2 - 0.4)) * CFrame.Angles(0, -math.pi / 2, 0), C.signBlue, false)
		local lines = if label ~= "" then {{"BUS", 0.55}, {label, 0.45}} else {{"BUS", 1}}
		boardText(sign, lines, Color3.fromRGB(255, 255, 255), BOTH)
	end
end

-- taxis {x, z, nx, nz, kind}: canopy stand; kind 1 = motorbike taxi ("WIN", orange vest rack), 2 = taxi
local TW, TD = 6, 3
local function buildTaxis(folder: Instance, rows: {number})
	for i = 1, #rows, 5 do
		local x, z, nx, nz, kind = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 4]
		local base = CFrame.lookAt(Vector3.new(x, 0, z), Vector3.new(x + nx, 0, z + nz))
		for _, sx in {-1, 1} do
			newPart(folder, "TaxiPost", Vector3.new(0.4, 8, 0.4), base * CFrame.new(sx * (TW / 2 - 0.3), GROUND_Y + 4, 0), C.post, true)
		end
		newPart(folder, "TaxiCanopy", Vector3.new(TW + 0.6, 0.3, TD + 0.6), base * CFrame.new(0, GROUND_Y + 8.15, 0), C.orange, false)
		newPart(folder, "TaxiRack", Vector3.new(TW - 1, 0.3, 0.3), base * CFrame.new(0, GROUND_Y + 6.4, 0), C.post, false)
		if kind == 1 then
			for _, sx in {-1, 1} do -- the drivers' orange vests on the rack (proxy)
				newPart(folder, "TaxiVest", Vector3.new(1.3, 1.7, 0.3), base * CFrame.new(sx * 1.2, GROUND_Y + 5.4, 0), C.orange, false)
			end
		end
		local sign = newPart(folder, "TaxiSign", Vector3.new(3.2, 1.4, 0.2), base * CFrame.new(0, GROUND_Y + 9.2, -TD / 2), C.dark, false)
		boardText(sign, {{if kind == 1 then "WIN" else "TAXI", 1}}, C.orange, BOTH)
	end
end

-- poles {x, z, ax, az, wire}: the corridor's utility pole (pole, crossarm, wire to the next pole)
local function buildPoles(folder: Instance, rows: {number})
	for i = 1, #rows, 5 do
		local x, z, ax, az, wire = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 4]
		local base = CFrame.lookAt(Vector3.new(x, GROUND_Y, z), Vector3.new(x + ax, GROUND_Y, z + az))
		newPart(folder, "UtilityPole", Vector3.new(0.9, 26, 0.9), base * CFrame.new(0, 13, 0), C.concrete, true)
		newPart(folder, "PoleArm", Vector3.new(6, 0.5, 0.5), base * CFrame.new(0, 24.5, 0), C.concrete, false)
		if wire > 0 then
			local a = Vector3.new(x, GROUND_Y + 24.8, z)
			local b = a + Vector3.new(ax, 0, az).Unit * wire
			newPart(folder, "PoleWire", Vector3.new(0.15, 0.15, wire), CFrame.lookAt((a + b) / 2, b), C.wire, false)
		end
	end
end

local function group(chunk: Instance, name: string, rows: {any}?, fn: (Instance, any) -> ())
	if rows and #rows > 0 then
		local m = Instance.new("Model")
		m.Name = name
		fn(m, rows)
		m.Parent = chunk
	end
end

function Furniture.Build(opts: {folder: string?, only: {string}?, batch: string?}?): string
	local options = (opts or {}) :: any
	local data = ServerStorage:WaitForChild(options.folder or "PattayaDataFurniture")
	local man = require(data:WaitForChild("manifest")) :: any
	if options.batch then
		options.only = man.batches[options.batch] or error("unknown furniture batch " .. tostring(options.batch))
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	if not world then
		error("PattayaFurnitureBuilder: build the city first (PattayaBuilder.Build / Extend)")
	end
	local folder = world:FindFirstChild("FurnitureChunks")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "FurnitureChunks"
		folder.Parent = world
	end
	local root = folder :: Instance
	root:SetAttribute("Attribution", man.attribution)
	root:SetAttribute("OsmBase", man.osmBase)
	local wanted: {[string]: boolean} = {}
	for _, id in options.only or {} do
		wanted[id] = true
	end
	local built, parts = 0, 0
	for _, id in man.chunks do
		if (options.only == nil or wanted[id]) and not root:FindFirstChild("Chunk_" .. id) then
			local d = require(data:WaitForChild("chunk_" .. id)) :: any
			local chunk = Instance.new("Model")
			chunk.Name = "Chunk_" .. id
			chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
			group(chunk, "Signals", d.signals, buildSignals)
			group(chunk, "Crossings", d.crossings, buildCrossings)
			group(chunk, "NameSigns", d.nameSigns, buildNameSigns)
			group(chunk, "Shelters", d.shelters, buildShelters)
			group(chunk, "Taxis", d.taxis, buildTaxis)
			group(chunk, "Poles", d.poles, buildPoles)
			chunk:PivotTo(chunk:GetPivot() + Furniture.ORIGIN)
			local n = 0
			for _, p in chunk:GetDescendants() do
				if p:IsA("BasePart") then n += 1 end
			end
			if n ~= d.parts then
				warn(("furniture chunk %s: %d parts built, data says %d"):format(id, n, d.parts))
			end
			parts += n
			chunk.Parent = root
			built += 1
			task.wait()
		end
	end
	return ("furniture: %d chunks built now (%d parts); %d chunks in manifest, %d built in total"):format(
		built, parts, #man.chunks, #root:GetChildren())
end

function Furniture.Remove(): string
	local world = workspace:FindFirstChild("PattayaWorld")
	local folder = world and world:FindFirstChild("FurnitureChunks")
	if not folder then
		return "furniture: nothing to remove"
	end
	local n = #folder:GetChildren()
	folder:Destroy()
	return ("furniture: removed %d chunks"):format(n)
end

return Furniture
