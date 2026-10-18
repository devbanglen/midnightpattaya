--!strict
-- Builds the Pattaya landmark proxies in Studio (edit time) from ServerStorage.PattayaDataLandmarks (manifest +
-- chunk_l<cx>_<cz> modules written by tools/mapgen/landmarks.py into build/landmarks/roblox). Every landmark stands on
-- its real OSM footprint (Map data (c) OpenStreetMap contributors, ODbL 1.0); the shapes are generic stylised Parts
-- with names as plain text (no logos, no official artwork).
-- Each data chunk becomes an Atomic-streaming Model workspace.PattayaWorld.LandmarkChunks.Chunk_l<cx>_<cz> holding one
-- Model per landmark. Nothing else in the place is touched, except by RemoveReplaced (see below).
-- WRITTEN, NOT RUN IN STUDIO YET.
--   local L = require(game.ServerStorage.PattayaLandmarksBuilder)
--   L.Build({batch = "l1"})            -- the chunks of one manifest batch (<= 8 chunks); then "l2"
--   L.Build({only = {"l2_0"}})         -- explicit chunk ids; chunks that already exist are skipped (resumable)
--   L.RemoveReplaced()                 -- deletes the procedural building boxes the proxies replace (manifest.replaces)
--   L.RemoveReplaced({only = {"terminal21"}}) -- ... only for these landmark ids
--   L.RestoreReplaced()                -- puts every removed box back where it was
--   L.Probe()                          -- landmark parts touching a Road / Sidewalk / Junction / Joint part (expected 0)
--   L.Remove()                         -- undo: destroys workspace.PattayaWorld.LandmarkChunks
-- Night look: parts with the NightNeon attribute (NightColor / DayColor) are switched by PattayaNightLights; the
-- small market-stall neon strips are named "NeonSign", so PattayaLOD fades them beyond LOD_PropRange like the city's
-- neon signs. Landmark bodies are never faded: they are meant to be seen from far away.
local ServerStorage = game:GetService("ServerStorage")

local Builder = {}

Builder.ORIGIN = Vector3.new(20000, 0, 0) -- same world offset as PattayaBuilder (map-local x + 20000)
local DATA = "PattayaDataLandmarks"
local STRIDE = 15 -- name, shape, sx, sy, sz, x, y, z, rx, ry, rz, color, material, flags, transparency

local MATERIALS = {
	Enum.Material.SmoothPlastic, Enum.Material.Wood, Enum.Material.WoodPlanks, Enum.Material.Concrete,
	Enum.Material.Glass, Enum.Material.Metal, Enum.Material.Marble, Enum.Material.Slate, Enum.Material.Foil,
	Enum.Material.Brick, Enum.Material.Granite, Enum.Material.Plastic,
}
local SHAPES = {Enum.PartType.Block, Enum.PartType.Cylinder, Enum.PartType.Ball}
local FACES: {[string]: Enum.NormalId} = {
	Front = Enum.NormalId.Front, Back = Enum.NormalId.Back, Left = Enum.NormalId.Left,
	Right = Enum.NormalId.Right, Top = Enum.NormalId.Top, Bottom = Enum.NormalId.Bottom,
}
local FONTS: {[string]: Enum.Font} = {GothamBlack = Enum.Font.GothamBlack, GothamBold = Enum.Font.GothamBold}

local function dataFolder(name: string?): Instance
	local folder = ServerStorage:FindFirstChild(name or DATA)
	assert(folder, "PattayaLandmarksBuilder: no ServerStorage." .. (name or DATA))
	return folder
end

local function load(module: Instance): any
	-- required from a clone so Edit mode's require cache never hands back an older version of a re-installed module
	return require(module:Clone() :: ModuleScript) :: any
end

local function color(list: {number}, i: number): Color3
	return Color3.fromRGB(list[i * 3 - 2], list[i * 3 - 1], list[i * 3])
end

local function addText(part: BasePart, face: string, text: string, fg: Color3, font: string, stroke: Color3?)
	local gui = Instance.new("SurfaceGui")
	gui.Face = FACES[face] or Enum.NormalId.Front
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 24
	gui.LightInfluence = 0 -- readable day and night (the board itself is dark)
	gui.Brightness = 1.4
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Text = text
	label.TextColor3 = fg
	label.Font = FONTS[font] or Enum.Font.GothamBlack
	label.TextScaled = true
	if stroke then
		label.TextStrokeColor3 = stroke
		label.TextStrokeTransparency = 0.35
	end
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0.04, 0)
	pad.PaddingRight = UDim.new(0.04, 0)
	pad.PaddingTop = UDim.new(0.1, 0)
	pad.PaddingBottom = UDim.new(0.1, 0)
	pad.Parent = label
	label.Parent = gui
	gui.Parent = part
end

local function buildLandmark(lm: any, attribution: string): (Model, number)
	local model = Instance.new("Model")
	model.Name = lm.id
	model:SetAttribute("LandmarkName", lm.name)
	model:SetAttribute("Label", lm.label)
	model:SetAttribute("Source", lm.source)
	model:SetAttribute("Attribution", attribution)
	local o = Builder.ORIGIN
	local cols, names, rows = lm.colors, lm.names, lm.parts
	local parts: {BasePart} = {}
	for i = 1, #rows, STRIDE do
		local shape = rows[i + 1]
		local p: BasePart
		if shape == 4 then
			p = Instance.new("WedgePart")
		else
			local part = Instance.new("Part")
			part.Shape = SHAPES[shape] -- before Size: a Ball keeps its (uniform) size
			p = part
		end
		p.Name = names[rows[i]]
		p.Anchored = true
		p.Size = Vector3.new(rows[i + 2], rows[i + 3], rows[i + 4])
		p.CFrame = CFrame.new(rows[i + 5] + o.X, rows[i + 6] + o.Y, rows[i + 7] + o.Z)
			* CFrame.fromEulerAnglesYXZ(rows[i + 8], rows[i + 9], rows[i + 10])
		p.Color = color(cols, rows[i + 11])
		p.Material = MATERIALS[rows[i + 12]]
		local flags = rows[i + 13]
		p.CanCollide = bit32.band(flags, 1) ~= 0
		p.CanQuery = bit32.band(flags, 2) ~= 0
		p.CastShadow = bit32.band(flags, 4) ~= 0
		p.CanTouch = false
		p.Transparency = rows[i + 14]
		p.TopSurface = Enum.SurfaceType.Smooth
		p.BottomSurface = Enum.SurfaceType.Smooth
		p.Parent = model
		table.insert(parts, p)
	end
	local neon = lm.neon
	for i = 1, #neon, 3 do -- PattayaNightLights: Neon + NightColor after dark, SmoothPlastic + DayColor by day
		local p = parts[neon[i]]
		p:SetAttribute("NightNeon", true)
		p:SetAttribute("DayColor", color(cols, neon[i + 1]))
		p:SetAttribute("NightColor", color(cols, neon[i + 2]))
	end
	for _, t in lm.texts do
		addText(parts[t[1]], t[2], t[3], color(cols, t[4]), t[5], if t[6] > 0 then color(cols, t[6]) else nil)
	end
	return model, #parts
end

function Builder.Build(opts: {only: {string}?, batch: string?, folder: string?}?): string
	local options = (opts or {}) :: any
	local data = dataFolder(options.folder)
	local man = load(data:WaitForChild("manifest"))
	local only = options.only
	if options.batch then
		only = man.batches[options.batch] or error("unknown batch " .. tostring(options.batch))
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "PattayaLandmarksBuilder: build the city first (PattayaBuilder.Build())")
	local root = world:FindFirstChild("LandmarkChunks")
	if not root then
		root = Instance.new("Folder")
		root.Name = "LandmarkChunks"
		root:SetAttribute("Attribution", man.attribution)
		root.Parent = world
	end
	local wanted: {[string]: boolean} = {}
	for _, id in only or {} do
		wanted[id] = true
	end
	local built, parts, skipped = 0, 0, 0
	for _, id in man.chunks do
		if only == nil or wanted[id] then
			if (root :: Instance):FindFirstChild("Chunk_" .. id) then
				skipped += 1
			else
				local chunkData = load(data:WaitForChild("chunk_" .. id))
				local chunk = Instance.new("Model")
				chunk.Name = "Chunk_" .. id
				chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
				for _, lm in chunkData.landmarks do
					local model, n = buildLandmark(lm, man.attribution)
					model.Parent = chunk
					parts += n
				end
				chunk.Parent = root
				built += 1
				task.wait()
			end
		end
	end
	return ("landmarks: %d chunks built now (%d parts), %d already there; %d chunks in manifest"):format(
		built, parts, skipped, #man.chunks)
end

-- Takes out the procedural building boxes (attribute OsmBuilding) that a proxy replaces, listed in manifest.replaces
-- with their dataset ("central" = PattayaWorld.Chunks, "wide" = PattayaWorld.WideChunks) and chunk. The roof slab of a
-- tall box (a sibling "Roof" part at the same x/z, no attribute) goes with it. Nothing is destroyed: the parts move to
-- ServerStorage.PattayaLandmarksRemoved/<Chunks|WideChunks>/<Chunk_id> (attribute FromParent = their old parent's name),
-- and RestoreReplaced() moves them back.
local BACKUP = "PattayaLandmarksRemoved"
function Builder.RemoveReplaced(opts: {only: {string}?, folder: string?}?): string
	local options = (opts or {}) :: any
	local man = load(dataFolder(options.folder):WaitForChild("manifest"))
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "no workspace.PattayaWorld")
	local wantLm: {[string]: boolean}? = nil
	if options.only then
		local w: {[string]: boolean} = {}
		for _, id in options.only do
			w[id] = true
		end
		wantLm = w
	end
	local backup = ServerStorage:FindFirstChild(BACKUP)
	if not backup then
		backup = Instance.new("Folder")
		backup.Name = BACKUP
		backup.Parent = ServerStorage
	end
	local function stash(part: Instance, rootName: string, chunkName: string)
		local r = (backup :: Instance):FindFirstChild(rootName)
		if not r then
			r = Instance.new("Folder")
			r.Name = rootName
			r.Parent = backup
		end
		local c = (r :: Instance):FindFirstChild(chunkName)
		if not c then
			c = Instance.new("Folder")
			c.Name = chunkName
			c.Parent = r
		end
		part:SetAttribute("FromParent", (part.Parent :: Instance).Name)
		part.Parent = c
	end
	local removed, missing = 0, {}
	for _, r in man.replaces do
		if wantLm == nil or (wantLm :: {[string]: boolean})[r.landmark] then
			local rootName = if r.dataset == "central" then "Chunks" else "WideChunks"
			local root = world:FindFirstChild(rootName)
			local chunk = root and root:FindFirstChild("Chunk_" .. r.chunk)
			local found = false
			if chunk then
				for _, d in chunk:GetDescendants() do
					if d:IsA("BasePart") and d:GetAttribute("OsmBuilding") == r.osm and d.Parent then
						for _, s in (d.Parent :: Instance):GetChildren() do
							if s:IsA("BasePart") and s.Name == "Roof" and math.abs(s.Position.X - d.Position.X) < 0.05
								and math.abs(s.Position.Z - d.Position.Z) < 0.05 then
								stash(s, rootName, (chunk :: Instance).Name)
							end
						end
						stash(d, rootName, (chunk :: Instance).Name)
						removed += 1
						found = true
					end
				end
			end
			if not found then
				table.insert(missing, ("%s/%s:%d"):format(rootName, r.chunk, r.osm))
			end
		end
	end
	if #missing > 0 then
		warn("PattayaLandmarksBuilder.RemoveReplaced: not found (already removed, or chunk not built):", table.concat(missing, ", "))
	end
	return ("removed %d procedural boxes; %d not found"):format(removed, #missing)
end

function Builder.RestoreReplaced(): string
	local backup = ServerStorage:FindFirstChild(BACKUP)
	local world = workspace:FindFirstChild("PattayaWorld")
	if not (backup and world) then
		return "nothing to restore"
	end
	local restored, lost = 0, 0
	for _, r in backup:GetChildren() do
		for _, c in r:GetChildren() do
			local chunk = world:FindFirstChild(r.Name) and (world :: any)[r.Name]:FindFirstChild(c.Name)
			for _, p in c:GetChildren() do
				local parent = chunk and (chunk:FindFirstChild(p:GetAttribute("FromParent") or "") or chunk)
				if parent then
					p:SetAttribute("FromParent", nil)
					p.Parent = parent
					restored += 1
				else
					lost += 1 -- the city chunk is gone (rebuilt?): the part stays in the backup folder
				end
			end
		end
	end
	return ("restored %d parts; %d left in ServerStorage.%s"):format(restored, lost, BACKUP)
end

-- Landmark parts that touch a Road / Sidewalk / Junction / Joint part (expected 0), plus part counts per landmark.
function Builder.Probe(): string
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "no workspace.PattayaWorld")
	local root = world:FindFirstChild("LandmarkChunks")
	if not root then
		return "no LandmarkChunks"
	end
	local roads = {}
	for _, d in world:GetDescendants() do
		if d:IsA("BasePart") and (d.Name == "Road" or d.Name == "Sidewalk" or d.Name == "Junction" or d.Name == "Joint") then
			table.insert(roads, d)
		end
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = roads
	local n, hits = 0, 0
	for _, chunk in root:GetChildren() do
		for _, lm in chunk:GetChildren() do
			local c = 0
			for _, p in lm:GetDescendants() do
				if p:IsA("BasePart") then
					n += 1
					c += 1
					if #workspace:GetPartsInPart(p, params) > 0 then
						hits += 1
						warn("touches road:", p:GetFullName())
					end
				end
			end
			print(lm.Name, c)
		end
	end
	return ("landmark parts %d, touching road/sidewalk/disc %d"):format(n, hits)
end

function Builder.Remove(): string
	local world = workspace:FindFirstChild("PattayaWorld")
	local root = world and world:FindFirstChild("LandmarkChunks")
	if root then
		root:Destroy()
		return "LandmarkChunks removed (boxes taken out by RemoveReplaced come back with RestoreReplaced)"
	end
	return "nothing to remove"
end

return Builder
