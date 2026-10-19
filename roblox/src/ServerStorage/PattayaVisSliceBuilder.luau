--!strict
-- VIS-4 visual slice builder (MIDNIGHT PATTAYA). Upgrades the procedural building boxes between Pattaya Nuea and
-- Pattaya Tai (Beach Road .. Second Road + frontage) IN PLACE with modular facades, at edit time in Studio.
-- Data: ServerStorage.PattayaDataVisSlice (manifest + chunk_v<cx>_<cz>[_k] modules written by tools/mapgen/vis_slice.py
-- into build/vis_slice/roblox). Map data (c) OpenStreetMap contributors, ODbL 1.0.
-- VIS-4 Part build: built in Studio 2026-10-19 (22,953 parts). VIS-7.1 changes (variety, mesh hooks): WRITTEN, NOT BUILT IN STUDIO.
--
-- Per building (all inside the original box, which never moves):
--   VisHull  invisible Part with exactly the original box size/CFrame: CanCollide + CanQuery like the original, so
--            collisions, car/camera raycasts and the road clearance are unchanged. Attribute OsmBuilding = OSM id.
--   VisCore  the visible wall: the original box inset only on its decorated faces; wall colour and the facade Textures
--            of the undecorated faces are copied from the original box (night tiles keep working on those faces).
--   modules  Parts made from the KIT in the manifest (manifest.modules / roofModules): shopfronts, window pairs + AC,
--            balcony rows, curtain wall, fins, parapet, roof plant. No per-building geometry is stored: a chunk only
--            lists placements (face, module, span, bays, floors). Facade parts never collide and are not queryable.
--            Roof modules are the only parts above the original box height (AC, water tank, plant room; <= 4.6 studs).
-- Every generated Part carries attribute Mat = a MaterialLibrary material name (DarkGlass, LitWindow, PaintedMetal,
-- NeonSurface, ConcreteSidewalk, PaintedPlaster, AwningFabric, SignPanel, RoofConcrete) and MeshSlot = the Blender
-- kit module that may replace it later (shopfront_a, balcony_row_a, ...), plus SlotInst = "<placement>:<floor>:<bay>"
-- so all Parts of one module instance can be swapped for one MeshPart by manifest. Base Material/Color come from the
-- manifest fallbacks, then (if present) a MaterialLibrary module is asked to style the part (see styleWithLibrary).
-- Night: lit windows / shop interiors / neon strips have NightNeon = true + DayColor/NightColor (PattayaNightLights
-- turns them Neon after dark). Neon strips are named "NeonSign" so PattayaLOD fades them beyond LOD_PropRange.
--
--   local V = require(game.ServerStorage.PattayaVisSliceBuilder)
--   V.Build({batch = "s1"})          -- one manifest batch (<= 8 chunks); then "s2" ... (manifest.batchOrder)
--   V.Build({only = {"v2_0"}})        -- explicit chunk ids; chunks that already exist are skipped (resumable)
--   V.Build({batch = "s1", replace = false}) -- build but keep the procedural boxes (they then overlap: debug only)
--   V.RemoveReplaced()               -- (Build does this for its chunks) move the boxes of built chunks to ServerStorage
--   V.RestoreReplaced()              -- put every moved box back
--   V.Probe()                        -- checks (expected: 0 touching roads, 0 outside the box, hull = original box)
--   V.Remove()                       -- undo: RemoveMesh(), destroys PattayaWorld.VisSliceChunks, restores the boxes
-- VIS-7.1 kit MeshParts (ServerStorage.VisMeshBuilder, data module PattayaDataVisSlice.vismesh):
--   V.BuildMesh()                    -- sample block: Part modules -> uploaded kit MeshParts (+ mesh palms); Build first
--   V.BuildMesh({only = {1209261453}, palms = false})   -- some sample buildings only (OSM ids or chunk ids)
--   V.ProbeMesh()                    -- MeshParts inside their box, 0 touching roads, sizes = manifest x scale
--   V.RemoveMesh()                   -- the Part buildings and the Part palms come back from ServerStorage.VisMeshRemoved
-- Variety (VIS-7.1): per building a palette variant (b.pal: plaster mixed into the city wall colour, trim, glass
-- tint), seeded AC / signboard density (b.acp / b.sgp: kit parts with dens = "ac" | "sign"), the mid module per
-- floor band and the top module are chosen by the exporter (they are plain placement rows here).
-- Variety v2 (VIS-7.2, team13; docs/VIS_VARIETY_2026-10-20.md; WRITTEN, NOT BUILT IN STUDIO): only when the export was
-- made with variety.v2_enabled (manifest.variety2 present). Building fields: wx / wxc (wall lerped wx % toward
-- variety2.stainColors[wxc]), shc (shutter colour variety2.shutterColors[shc]), gfa (shopfront pilasters in the darkened
-- accent), and the per-part gates of the patched kit: sp.gate = {field, value} (b[field] or 1 must equal value),
-- sp.dk / sp.dpi / sp.dinv (per-bay seeded density on b[dk]), sp.rh (balcony rhythm on b.rhp / b.rhs), colour key
-- accentBay (accent per bay). Without those fields every gate falls back to the VIS-7.1c result.
local ServerStorage = game:GetService("ServerStorage")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Builder = {}

Builder.ORIGIN = Vector3.new(20000, 0, 0) -- same world offset as PattayaBuilder (map-local x + 20000)
local BASE_Y = 0 -- PattayaBuilder: footings at ROAD_TOP - 1
local DATA = "PattayaDataVisSlice"
local ROOT_NAME = "VisSliceChunks"
local BACKUP = "PattayaVisSliceRemoved"

type Face = {n: Vector3, u: Vector3, half: string, span: string, id: Enum.NormalId}
-- face index -> outward normal, U axis (both in the box's local frame), half-extent key, span key, NormalId.
-- Must match FACES in tools/mapgen/vis_slice.py.
local FACE: {Face} = {
	{n = Vector3.new(1, 0, 0), u = Vector3.new(0, 0, 1), half = "w", span = "d", id = Enum.NormalId.Right},
	{n = Vector3.new(-1, 0, 0), u = Vector3.new(0, 0, -1), half = "w", span = "d", id = Enum.NormalId.Left},
	{n = Vector3.new(0, 0, 1), u = Vector3.new(-1, 0, 0), half = "d", span = "w", id = Enum.NormalId.Back},
	{n = Vector3.new(0, 0, -1), u = Vector3.new(1, 0, 0), half = "d", span = "w", id = Enum.NormalId.Front},
}

local function dataFolder(name: string?): Instance
	local folder = ServerStorage:FindFirstChild(name or DATA)
	assert(folder, "PattayaVisSliceBuilder: no ServerStorage." .. (name or DATA))
	return folder
end

local function load(module: Instance): any
	-- required from a clone so Edit mode's require cache never hands back an older version of a re-installed module
	return require(module:Clone() :: ModuleScript) :: any
end

local function rgb(t: {number}): Color3
	return Color3.fromRGB(t[1], t[2], t[3])
end

-- Deterministic per-window number: the same integer formula as lit_hash() in tools/mapgen/vis_slice.py.
function Builder.litHash(osm: number, face: number, mod: number, k: number, j: number, pi: number, modN: number): number
	return (osm % modN) * 7919 + face * 104729 + mod * 1009 + k * 131 + j * 31 + pi * 7
end

-- Optional MaterialLibrary (sibling team vis-lighting). Looked up once per Build in ServerStorage then ReplicatedStorage.
-- Accepted shapes: lib.apply(part, name) / lib.Apply(part, name), or lib.get(name) / lib.Get(name) / lib[name]
-- returning {Material = Enum.Material?, MaterialVariant = string?, Color = Color3?}. Every call is pcall'd; without a
-- library (or with opts.materialLibrary = false) the manifest fallbacks stay.
local function findLibrary(opts: any): any
	if opts.materialLibrary == false then
		return nil
	end
	local m = ServerStorage:FindFirstChild("MaterialLibrary") or ReplicatedStorage:FindFirstChild("MaterialLibrary")
	if not (m and m:IsA("ModuleScript")) then
		return nil
	end
	local ok, lib = pcall(load, m)
	return if ok and type(lib) == "table" then lib else nil
end

local function styleWithLibrary(lib: any, part: BasePart, name: string, keepColor: boolean)
	if not lib then
		return
	end
	local fn = lib.apply or lib.Apply
	if type(fn) == "function" then
		local c = part.Color
		pcall(fn, part, name)
		if keepColor then
			part.Color = c -- wall / accent / sign colours are per building; the library only sets the surface
		end
		return
	end
	local getter = lib.get or lib.Get
	local ok: boolean, spec: any = false, nil
	if type(getter) == "function" then
		ok, spec = pcall(getter, name)
	else
		ok, spec = true, lib[name]
	end
	if ok and type(spec) == "table" then
		pcall(function()
			if typeof(spec.Material) == "EnumItem" then part.Material = spec.Material end
			if type(spec.MaterialVariant) == "string" then part.MaterialVariant = spec.MaterialVariant end
			if not keepColor and typeof(spec.Color) == "Color3" then part.Color = spec.Color end
		end)
	end
end

-- original procedural boxes ---------------------------------------------------------------------------------------
local function originalsIn(container: Instance?): {[number]: BasePart}
	local map: {[number]: BasePart} = {}
	if container then
		for _, d in container:GetDescendants() do
			if d:IsA("BasePart") then
				local id = d:GetAttribute("OsmBuilding")
				if type(id) == "number" then
					map[id] = d
				end
			end
		end
	end
	return map
end

local function cityChunk(world: Instance, src: string): Instance?
	local chunks = world:FindFirstChild("Chunks")
	return chunks and chunks:FindFirstChild("Chunk_" .. src)
end

local function backupChunk(src: string, create: boolean): Instance?
	local backup = ServerStorage:FindFirstChild(BACKUP)
	if not backup and create then
		backup = Instance.new("Folder")
		backup.Name = BACKUP
		backup.Parent = ServerStorage
	end
	if not backup then
		return nil
	end
	local r = backup:FindFirstChild("Chunks")
	if not r and create then
		r = Instance.new("Folder")
		r.Name = "Chunks"
		r.Parent = backup
	end
	if not r then
		return nil
	end
	local c = r:FindFirstChild("Chunk_" .. src)
	if not c and create then
		c = Instance.new("Folder")
		c.Name = "Chunk_" .. src
		c.Parent = r
	end
	return c
end

-- the tall-box roof slab: a sibling Part named "Roof" at the same x/z (no attribute), as in PattayaLandmarksBuilder
local function roofOf(box: BasePart): BasePart?
	local parent = box.Parent
	if not parent then
		return nil
	end
	for _, s in parent:GetChildren() do
		if s:IsA("BasePart") and s.Name == "Roof" and math.abs(s.Position.X - box.Position.X) < 0.05
			and math.abs(s.Position.Z - box.Position.Z) < 0.05 then
			return s
		end
	end
	return nil
end

local function stash(part: Instance, src: string)
	part:SetAttribute("FromParent", (part.Parent :: Instance).Name)
	part.Parent = backupChunk(src, true)
end

-- one building -------------------------------------------------------------------------------------------------------
type Ctx = {man: any, lib: any, colors: {[string]: Color3}, mats: {[string]: Enum.Material}, signs: boolean}

local function newPart(parent: Instance, name: string, size: Vector3, cf: CFrame, shape: string?): BasePart
	local p: BasePart
	if shape == "wedge" then
		p = Instance.new("WedgePart")
	else
		local part = Instance.new("Part")
		if shape == "cyl" then
			part.Shape = Enum.PartType.Cylinder
		end
		p = part
	end
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.CFrame = cf
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

local function addSign(part: BasePart, text: string, fg: Color3)
	local gui = Instance.new("SurfaceGui")
	gui.Face = Enum.NormalId.Front -- the part's front looks out of the facade
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 20
	gui.LightInfluence = 0 -- readable day and night on the dark/colour board
	gui.Brightness = 1.2
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Text = text
	label.TextColor3 = fg
	label.Font = Enum.Font.GothamBold -- Thai glyphs come from Roblox's font fallback
	label.TextScaled = true
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0.04, 0)
	pad.PaddingRight = UDim.new(0.04, 0)
	pad.PaddingTop = UDim.new(0.08, 0)
	pad.PaddingBottom = UDim.new(0.08, 0)
	pad.Parent = label
	label.Parent = gui
	gui.Parent = part
end

local function buildBuilding(ctx: Ctx, b: any, parent: Instance, original: BasePart?): (Model, number)
	local man = ctx.man
	local o = Builder.ORIGIN
	local model = Instance.new("Model")
	model.Name = "Vis_" .. tostring(b.osm)
	model:SetAttribute("OsmBuilding", b.osm)
	model:SetAttribute("Category", b.cat)
	local style = man.styles[b.style]
	model:SetAttribute("Style", style.name)
	local base = CFrame.new(b.x + o.X, BASE_Y + o.Y, b.z + o.Z) * CFrame.Angles(0, -math.rad(b.yaw), 0)
	local count = 0

	-- hull: the original box, invisible, colliding and queryable exactly like before
	local hull = newPart(model, "VisHull", Vector3.new(b.w, b.h, b.d), base * CFrame.new(0, b.h / 2, 0), nil)
	hull.Transparency = 1
	hull.CanCollide = true
	hull.CanQuery = true
	hull:SetAttribute("OsmBuilding", b.osm)
	hull:SetAttribute("VisSlice", true)
	count += 1

	-- colours of this building: city box colour, mixed toward the building's palette variant (plaster / trim / glass)
	local wall = if original then original.Color else Color3.fromRGB(205, 200, 190)
	local cols = ctx.colors
	local pals = man.palettes and man.palettes[b.style]
	local pal = if pals and b.pal then pals[b.pal] else nil
	local trim: Color3? = nil
	local glass: Color3? = nil
	if pal then
		wall = wall:Lerp(rgb(pal.plaster), man.paletteWallMix or 0.75)
		trim = rgb(pal.trim)
		glass = rgb(pal.glass)
	end
	-- variety v2 (VIS-7.2): weathering / stain tint on the plaster, per-building shutter colour, accent pilasters
	local v2 = man.variety2
	local shutterCol: Color3? = nil
	if v2 then
		if b.wx and b.wx > 0 then
			wall = wall:Lerp(rgb(v2.stainColors[b.wxc or 1]), b.wx / 100)
		end
		if b.shc then
			shutterCol = rgb(v2.shutterColors[b.shc])
		end
	end
	local function colour(key: string): Color3
		if key == "wall" then return wall end
		if key == "wallDark" then return wall:Lerp(Color3.new(0, 0, 0), 0.25) end
		if key == "shutter" and shutterCol then return shutterCol end
		if key == "gfPilaster" then
			if b.gfa == 1 then
				return rgb(man.accents[b.acc]):Lerp(Color3.new(0, 0, 0), if v2 then v2.accentDarkMix else 0.3)
			end
			return wall:Lerp(Color3.new(0, 0, 0), 0.25)
		end
		if key == "accentBay" then return rgb(man.accents[b.acc]) end -- per bay: set by the placement loop
		if key == "wallTrim" then return trim or wall:Lerp(Color3.new(1, 1, 1), 0.45) end
		if key == "trim" and trim then return trim end
		if key == "glass" and glass then return glass end
		if key == "accent" then return rgb(man.accents[b.acc]) end
		if key == "signBoard" then return rgb(man.signCombos[b.sc].board) end
		return cols[key] or wall
	end

	-- core: inset only on decorated faces; the undecorated faces keep the original facade Textures
	local ins = b.ins
	local cw, cd = b.w - ins[1] - ins[2], b.d - ins[3] - ins[4]
	local core = newPart(model, "VisCore", Vector3.new(cw, b.h, cd),
		base * CFrame.new((ins[2] - ins[1]) / 2, b.h / 2, (ins[4] - ins[3]) / 2), nil)
	core.Color = wall
	core.Material = Enum.Material.SmoothPlastic
	core.CastShadow = b.h > 20
	core:SetAttribute("Mat", "PaintedPlaster")
	core:SetAttribute("MeshSlot", "core_" .. style.name)
	styleWithLibrary(ctx.lib, core, "PaintedPlaster", true)
	if original then
		for _, t in original:GetChildren() do
			if t:IsA("Texture") then
				for f = 1, 4 do
					if FACE[f].id == t.Face and ins[f] == 0 then
						local c = t:Clone()
						c.Parent = core -- keeps attribute Facade: PattayaNightLights / PattayaLOD treat it like before
					end
				end
			end
		end
	end
	count += 1

	local litCfg = man.lit
	local spread = litCfg.spread
	local tones: {Color3} = {}
	for _, t in litCfg.tones do
		table.insert(tones, rgb(t))
	end
	local upperTone = rgb(litCfg.upper_tone)
	local upperStyle = table.find(litCfg.upper_styles, style.name) ~= nil
	local neonNight = if b.neon == 2 then cols.neonMagenta else cols.neonCyan
	local neonDay = if b.neon == 2 then cols.neonMagentaDay else cols.neonCyanDay
	local text = if b.txt > 0 then man.texts[b.txt] else nil
	local textColour = rgb(man.signCombos[b.sc].text)

	local function finish(p: BasePart, sp: any, slot: string, inst: string, lit: boolean, hsh: number, upper: boolean,
		over: Color3?)
		local matName = sp.mat
		if sp.neon then
			p.Color = neonDay
			p.Material = Enum.Material.SmoothPlastic
			p:SetAttribute("NightNeon", true)
			p:SetAttribute("DayColor", neonDay)
			p:SetAttribute("NightColor", neonNight)
		elseif lit then
			matName = "LitWindow"
			local day = over or colour(sp.col)
			p.Color = day
			p.Material = Enum.Material.SmoothPlastic
			p:SetAttribute("NightNeon", true)
			p:SetAttribute("DayColor", day)
			-- warm amber, one of the manifest tones per pane; hotel/condo upper floors a slightly cooler tone
			p:SetAttribute("NightColor", if upper then upperTone else tones[math.floor(hsh / 100) % #tones + 1])
		else
			p.Color = over or colour(sp.col)
			p.Material = ctx.mats[matName] or Enum.Material.SmoothPlastic
			styleWithLibrary(ctx.lib, p, matName, true)
		end
		p:SetAttribute("Mat", matName)
		p:SetAttribute("MeshSlot", slot)
		p:SetAttribute("SlotInst", inst)
		if sp.text and text and ctx.signs then
			addSign(p, text, textColour)
		end
	end

	-- facade placements: the Lua twin of Kit.face_parts in tools/mapgen/vis_slice.py
	local P = b.p
	local nPl = #P // 10
	for pIndex = 1, nPl do
		local r = (pIndex - 1) * 10
		local f, mi, u0, u1, nb, v0, vh, nv, dv, flags =
			P[r + 1], P[r + 2], P[r + 3], P[r + 4], P[r + 5], P[r + 6], P[r + 7], P[r + 8], P[r + 9], P[r + 10]
		local face = FACE[f]
		local mod = man.modules[mi]
		local inset = ins[f]
		local dist = (if face.half == "w" then b.w else b.d) / 2
		local span = u1 - u0
		local bw = span / nb
		local neonOk = bit32.band(flags, 1) ~= 0
		local noText = bit32.band(flags, 2) ~= 0
		for k = 0, nv - 1 do
			local vb = v0 + k * dv
			for pi0, sp in mod.parts do
				local pi = pi0 - 1
				if sp.neon and not neonOk then continue end
				if sp.gate and (b[sp.gate[1]] or 1) ~= sp.gate[2] then continue end -- v2 per-building variant gate
				if (sp.text or sp.neon) and noText then continue end
				-- seeded signboard density (twin of Kit.face_parts in vis_slice.py)
				if sp.dens == "sign" and Builder.litHash(b.osm, f, mi, k, 0, pi + 50, litCfg.hash_mod) % 100 >= (b.sgp or 100) then
					continue
				end
				local rep = sp.rep
				local cells = if rep == 0 then 1 elseif rep == 1 then nb else nb + 1
				for j = 0, cells - 1 do
					local cs = if rep == 0 then u0 else u0 + j * bw
					local cwid = if rep == 0 then span else bw
					local su = sp.u
					local ua, ub
					if rep == 2 then
						ua, ub = cs + su[2], cs + su[4]
					else
						ua, ub = cs + su[1] * cwid + su[2], cs + su[3] * cwid + su[4]
					end
					ua, ub = math.max(ua, u0), math.min(ub, u1)
					local sv = sp.v
					local va, vtop = vb + sv[1] * vh + sv[2], vb + sv[3] * vh + sv[4]
					local n0, n1
					if sp.n then
						n1 = math.min(-inset + sp.n[2], 0)
						n0 = -inset + sp.n[1]
					else
						n1 = math.min(sp.nh[2], 0)
						n0 = math.max(sp.nh[1], -inset)
					end
					if ub - ua < 0.1 or vtop - va < 0.05 or n1 - n0 < 0.05 then continue end
					if sp.dens == "ac" and Builder.litHash(b.osm, f, mi, k, j, pi + 50, litCfg.hash_mod) % 100 >= (b.acp or 100) then
						continue -- seeded AC density (per bay)
					end
					-- v2 (twin of Kit.face_parts): seeded per-bay density on b[dk] (dinv = the complement), balcony rhythm
					if sp.dk and ((Builder.litHash(b.osm, f, mi, k, j, (sp.dpi or pi) + 50, litCfg.hash_mod) % 100
						< (b[sp.dk] or 100)) == (sp.dinv == true)) then
						continue
					end
					if sp.rh then
						local rp = b.rhp or 0
						local solid = rp > 0 and (j + k * (b.rhs or 0)) % rp == 0
						if solid ~= (sp.rh == 2) then continue end
					end
					local over: Color3? = nil
					if sp.col == "accentBay" then -- one accent per bay (awning mode 2)
						local acc = man.accents
						over = rgb(acc[(Builder.litHash(b.osm, f, mi, k, j, pi + 70, litCfg.hash_mod) // 7) % #acc + 1])
					end
					local lit, hsh = false, 0
					if sp.lit then
						local pct = if sp.lit == "win" then style.litWin else style.litShop
						pct = math.clamp(pct + b.osm % (2 * spread + 1) - spread, 0, 100)
						hsh = Builder.litHash(b.osm, f, mi, k, j, pi, litCfg.hash_mod)
						lit = hsh % 100 < pct
						if sp.litOnly and not lit then continue end
					end
					local um, vm, nm = (ua + ub) / 2, (va + vtop) / 2, dist + (n0 + n1) / 2
					local pos = face.n * nm + face.u * um + Vector3.new(0, vm, 0)
					local cf = base * CFrame.fromMatrix(pos, face.u, Vector3.yAxis, -face.n)
					local p = newPart(model, sp.k, Vector3.new(ub - ua, vtop - va, n1 - n0), cf, sp.shape)
					local upper = upperStyle and v0 > 0 and vb + vh / 2 > b.h / 2 -- upper half of the building
					finish(p, sp, mod.slot, ("%d:%d:%d"):format(pIndex, k, j), lit, hsh, upper, over)
					count += 1
				end
			end
		end
	end

	-- roof modules (local frame of the box, on top of the core)
	local R = b.r
	for rIndex = 1, #R // 3 do
		local r = (rIndex - 1) * 3
		local mod = man.roofModules[R[r + 1]]
		local fx, fz = R[r + 2], R[r + 3]
		for _, sp in mod.parts do
			local c, s = sp.c, sp.s
			local cf = base * CFrame.new(fx + c[1], b.h + c[2], fz + c[3])
			local size = Vector3.new(s[1], s[2], s[3])
			if sp.shape == "cyl" then -- vertical cylinder: Roblox cylinders run along X
				cf *= CFrame.Angles(0, 0, math.pi / 2)
				size = Vector3.new(s[2], s[1], s[3])
			end
			local p = newPart(model, sp.k, size, cf, sp.shape)
			finish(p, sp, mod.slot, ("r%d"):format(rIndex), false, 0, false)
			count += 1
		end
	end
	model.Parent = parent
	return model, count, colour
end

-- public API ---------------------------------------------------------------------------------------------------------
local function context(man: any, opts: any): Ctx
	local colors: {[string]: Color3} = {}
	for k, v in man.colors do
		colors[k] = rgb(v)
	end
	local mats: {[string]: Enum.Material} = {}
	for k, v in man.materials do
		local ok, e = pcall(function() return (Enum.Material :: any)[v] end)
		mats[k] = if ok and e then e else Enum.Material.SmoothPlastic
	end
	return {man = man, lib = findLibrary(opts), colors = colors, mats = mats, signs = opts.signs ~= false}
end

local function wantedIds(man: any, opts: any): ({string}, {[string]: boolean}?)
	local only = opts.only
	if opts.batch then
		only = man.batches[opts.batch] or error("unknown batch " .. tostring(opts.batch))
	end
	if only == nil then
		return man.chunks, nil
	end
	local w: {[string]: boolean} = {}
	for _, id in only do
		w[id] = true
	end
	return man.chunks, w
end

-- internals shared with ServerStorage.VisMeshBuilder (VIS-7.1 kit MeshParts); not a public API
Builder._internal = {
	FACE = FACE, BASE_Y = BASE_Y, DATA = DATA, ROOT_NAME = ROOT_NAME, BACKUP = BACKUP, rgb = rgb, load = load,
	dataFolder = dataFolder, context = context, buildBuilding = buildBuilding, styleWithLibrary = styleWithLibrary,
	addSign = addSign, originalsIn = originalsIn, cityChunk = cityChunk, backupChunk = backupChunk,
}

local function meshBuilder(): any
	local m = script.Parent:FindFirstChild("VisMeshBuilder")
	assert(m and m:IsA("ModuleScript"), "PattayaVisSliceBuilder: no ServerStorage.VisMeshBuilder")
	return load(m)
end

function Builder.BuildMesh(opts: any?): string
	return meshBuilder().BuildMesh(Builder, opts or {})
end

function Builder.RemoveMesh(opts: any?): string
	return meshBuilder().RemoveMesh(Builder, opts or {})
end

function Builder.ProbeMesh(opts: any?): string
	return meshBuilder().ProbeMesh(Builder, opts or {})
end

function Builder.Build(opts: {only: {string}?, batch: string?, folder: string?, replace: boolean?, signs: boolean?,
	materialLibrary: boolean?}?): string
	local options = (opts or {}) :: any
	local data = dataFolder(options.folder)
	local man = load(data:WaitForChild("manifest"))
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "PattayaVisSliceBuilder: build the city first (PattayaBuilder.Build())")
	local root = world:FindFirstChild(ROOT_NAME)
	if not root then
		root = Instance.new("Folder")
		root.Name = ROOT_NAME
		root:SetAttribute("Attribution", man.attribution)
		root.Parent = world
	end
	local ctx = context(man, options)
	local ids, wanted = wantedIds(man, options)
	local built, parts, skipped, missing, replaced = 0, 0, 0, 0, 0
	local originalCache: {[string]: {[number]: BasePart}} = {}
	for _, id in ids do
		if wanted ~= nil and not wanted[id] then continue end
		if (root :: Instance):FindFirstChild("Chunk_" .. id) then
			skipped += 1
			continue
		end
		local cd = load(data:WaitForChild("chunk_" .. id))
		local src = cd.src
		if not originalCache[src] then
			local map = originalsIn(cityChunk(world, src))
			for osm, p in originalsIn(backupChunk(src, false)) do
				if not map[osm] then map[osm] = p end
			end
			originalCache[src] = map
		end
		local originals = originalCache[src]
		local chunk = Instance.new("Model")
		chunk.Name = "Chunk_" .. id
		chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
		chunk:SetAttribute("Src", src)
		local n = 0
		for _, b in cd.buildings do
			local original = originals[b.osm]
			if not original then
				missing += 1
			end
			local _, c = buildBuilding(ctx, b, chunk, original)
			n += c
			if options.replace ~= false and original and original:IsDescendantOf(workspace) then
				local roof = roofOf(original)
				if roof then stash(roof, src) end
				stash(original, src)
				replaced += 1
			end
		end
		chunk.Parent = root
		parts += n
		built += 1
		if n ~= man.chunkParts[id] then
			warn(("PattayaVisSliceBuilder: chunk %s built %d parts, manifest says %d"):format(id, n, man.chunkParts[id]))
		end
		task.wait()
	end
	if missing > 0 then
		warn(("PattayaVisSliceBuilder: %d original boxes not found (city chunk not built or rebuilt?) - those buildings use a default wall colour and no facade Textures"):format(missing))
	end
	return ("vis slice: %d chunks built now (%d parts), %d already there; %d procedural boxes moved to ServerStorage.%s; %d chunks in manifest (%d parts)"):format(
		built, parts, skipped, replaced, BACKUP, #man.chunks, man.totalParts)
end

-- Moves the procedural boxes (and their Roof slabs) of every BUILT vis chunk to ServerStorage.PattayaVisSliceRemoved.
-- Needed again after PattayaBuilder.RebuildChunks() brings a city chunk back.
function Builder.RemoveReplaced(opts: {folder: string?}?): string
	local options = (opts or {}) :: any
	local data = dataFolder(options.folder)
	local man = load(data:WaitForChild("manifest"))
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "no workspace.PattayaWorld")
	local root = world:FindFirstChild(ROOT_NAME)
	if not root then
		return "no VisSliceChunks built"
	end
	local moved = 0
	for _, id in man.chunks do
		local chunk = root:FindFirstChild("Chunk_" .. id)
		if not chunk then continue end
		local src = chunk:GetAttribute("Src") :: string
		local originals = originalsIn(cityChunk(world, src))
		for _, m in chunk:GetChildren() do
			local osm = m:GetAttribute("OsmBuilding")
			local original = if type(osm) == "number" then originals[osm] else nil
			if original then
				local roof = roofOf(original)
				if roof then stash(roof, src) end
				stash(original, src)
				moved += 1
			end
		end
	end
	return ("moved %d procedural boxes to ServerStorage.%s"):format(moved, BACKUP)
end

function Builder.RestoreReplaced(): string
	local backup = ServerStorage:FindFirstChild(BACKUP)
	local world = workspace:FindFirstChild("PattayaWorld")
	if not (backup and world) then
		return "nothing to restore"
	end
	local restored, lost = 0, 0
	local r = backup:FindFirstChild("Chunks")
	for _, c in (if r then r:GetChildren() else {}) do
		local chunk = cityChunk(world, string.sub(c.Name, 7))
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
	return ("restored %d parts; %d left in ServerStorage.%s"):format(restored, lost, BACKUP)
end

function Builder.Remove(): string
	local meshMsg = "no VisMeshBuilder"
	if script.Parent:FindFirstChild("VisMeshBuilder") then
		local ok, r = pcall(Builder.RemoveMesh)
		meshMsg = if ok then tostring(r) else "RemoveMesh failed: " .. tostring(r)
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	local root = world and world:FindFirstChild(ROOT_NAME)
	local msg = meshMsg .. "; no VisSliceChunks"
	if root then
		root:Destroy()
		msg = meshMsg .. "; VisSliceChunks removed"
	end
	return msg .. "; " .. Builder.RestoreReplaced()
end

-- Checks after a build (Studio edit mode or Play server):
--  * facade/roof parts touching a Road / Sidewalk / Junction / Joint part (expected 0)
--  * facade parts outside their VisHull (expected 0; roof parts are allowed above the top only)
--  * VisHull vs the original box in the backup folder: size and CFrame equal (expected 0 mismatches)
--  * procedural boxes still in the city chunks for an upgraded building (expected 0 after Build/RemoveReplaced)
--  * counts: parts, NightNeon parts, signboards, per-chunk part count vs manifest
function Builder.Probe(opts: {folder: string?, roads: boolean?}?): string
	local options = (opts or {}) :: any
	local man = load(dataFolder(options.folder):WaitForChild("manifest"))
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "no workspace.PattayaWorld")
	local root = world:FindFirstChild(ROOT_NAME)
	if not root then
		return "no VisSliceChunks"
	end
	local roads = {}
	if options.roads ~= false then
		for _, d in world:GetDescendants() do
			if d:IsA("BasePart") and (d.Name == "Road" or d.Name == "Sidewalk" or d.Name == "Junction" or d.Name == "Joint") then
				table.insert(roads, d)
			end
		end
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = roads
	local nParts, onRoad, outside, neon, signsN, hullBad, dup, chunkBad = 0, 0, 0, 0, 0, 0, 0, 0
	local backupMaps: {[string]: {[number]: BasePart}} = {}
	local cityMaps: {[string]: {[number]: BasePart}} = {}
	local checked = 0
	for _, chunk in root:GetChildren() do
		local src = chunk:GetAttribute("Src") :: string
		if not backupMaps[src] then
			backupMaps[src] = originalsIn(backupChunk(src, false))
			cityMaps[src] = originalsIn(cityChunk(world, src))
		end
		local inChunk = 0
		for _, m in chunk:GetChildren() do
			local osm = m:GetAttribute("OsmBuilding") :: number
			local hull = m:FindFirstChild("VisHull") :: BasePart?
			local isMesh = m:GetAttribute("VisMesh") == true
			if isMesh then -- a VIS-7.1 kit building: counts as its Part build here; V.ProbeMesh() checks its MeshParts
				inChunk += (m:GetAttribute("PartBuildParts") :: number?) or 0
			end
			if cityMaps[src][osm] then
				dup += 1
			end
			local orig = backupMaps[src][osm]
			if hull and orig then
				if (hull.Size - orig.Size).Magnitude > 0.01 or (hull.Position - orig.Position).Magnitude > 0.01
					or hull.CFrame.LookVector:Dot(orig.CFrame.LookVector) < 0.99999 then
					hullBad += 1
					warn("hull differs from the original box:", m:GetFullName())
				end
			elseif hull and not orig then
				hullBad += 1
				warn("no original box in the backup to compare with:", m:GetFullName())
			end
			for _, p in m:GetChildren() do
				if not p:IsA("BasePart") then continue end
				nParts += 1
				if not isMesh then inChunk += 1 end
				if p:GetAttribute("NightNeon") == true then neon += 1 end
				if p:FindFirstChildOfClass("SurfaceGui") then signsN += 1 end
				if p == hull or not hull then continue end
				-- inside the hull: all 8 corners in the hull's local frame (roof parts may stand above the top)
				local h = hull :: BasePart
				local tol = if p:IsA("MeshPart") then 0.06 else 0.02 -- kit rows on a 20.1 box end at 20.142
				local half = h.Size / 2 + Vector3.new(tol, tol, tol)
				local roofPart = string.sub(p:GetAttribute("SlotInst") or "", 1, 1) == "r" or p:GetAttribute("AboveRoof") == true
				local out = false
				for corner = 0, 7 do
					local sgn = Vector3.new(if corner % 2 == 0 then -1 else 1, if (corner // 2) % 2 == 0 then -1 else 1,
						if corner // 4 == 0 then -1 else 1)
					local c = h.CFrame:PointToObjectSpace(p.CFrame:PointToWorldSpace(p.Size / 2 * sgn))
					if math.abs(c.X) > half.X or math.abs(c.Z) > half.Z or c.Y < -half.Y or (c.Y > half.Y and not roofPart) then
						out = true
					end
				end
				if out then
					outside += 1
					warn("outside its box:", p:GetFullName())
				end
				if #roads > 0 and #workspace:GetPartsInPart(p, params) > 0 then
					onRoad += 1
					warn("touches road:", p:GetFullName())
				end
				checked += 1
				if checked % 400 == 0 then task.wait() end
			end
		end
		local id = string.sub(chunk.Name, 7)
		if man.chunkParts[id] ~= inChunk then
			chunkBad += 1
			warn(("chunk %s: %d parts, manifest %s"):format(id, inChunk, tostring(man.chunkParts[id])))
		end
	end
	return ("vis parts %d (manifest total %d); touching road/sidewalk/disc %d; outside their box %d; hull != original %d; boxes still in the city %d; chunks with a different part count %d; NightNeon %d; signboards %d")
		:format(nParts, man.totalParts, onRoad, outside, hullBad, dup, chunkBad, neon, signsN)
end

return Builder
