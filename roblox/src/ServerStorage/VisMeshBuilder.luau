--!strict
-- VIS-7.1 VisMesh (MIDNIGHT PATTAYA): the uploaded Blender kit as MeshParts on the Beach Road sample block, and mesh
-- palms for the whole slice. Edit mode in Studio. Called through PattayaVisSliceBuilder (V.BuildMesh / V.RemoveMesh /
-- V.ProbeMesh); data from tools/mapgen/vis_slice.py + VisMesh.py (PattayaDataVisSlice.vismesh + field `mesh` of the
-- sample buildings in the chunk modules). Asset ids: ServerStorage.VisAssetsManifest (name -> Model asset id).
-- Map data (c) OpenStreetMap contributors, ODbL 1.0. WRITTEN, NOT BUILT IN STUDIO.
--
-- Assets: each needed asset is loaded ONCE with InsertService:LoadAsset (pcall) and kept under
-- ServerStorage.VisAssets.<name> (Model -> Model -> <Asset>_<Material>_Node -> MeshPart); an asset already there is
-- reused (so a second BuildMesh does not load again, and the owner may drop a hand-imported copy there). An asset is
-- usable when every MeshPart the Blender manifest lists exists with its size (+- 0.05 studs). A missing / failed
-- asset never stops the build: every Part row whose group needs it is built from the Part kit instead (reported).
-- Buildings: the Part building Vis_<osm> (from V.Build) moves to ServerStorage.VisMeshRemoved.Buildings and a new
-- Vis_<osm> takes its place: same VisHull (the original box: collisions, raycasts and road clearance unchanged), a
-- VisCore inset deeper on the decorated faces, Part rows only where no mesh replaces them, then the kit MeshParts:
-- anchored, CanCollide / CanQuery / CanTouch false, CastShadow only on the wall-sized MP_Wall parts, RenderFidelity
-- Automatic, attribute Mat (MaterialLibrary name) + MeshSlot + VisAsset / VisPart / VisScale; kit glass panes picked
-- lit at night are NightNeon (PattayaNightLights), neon strips NightNeon cyan / magenta. Scale is uniform and 1 for
-- every row (the kit was built on the city grid); tops / corner tops / roof items stand on the roof (AboveRoof).
-- Palms: each city palm in the slice bbox (PattayaBuilder Props: PalmTrunk + 5 PalmFrond) moves to
-- ServerStorage.VisMeshRemoved.Palms; workspace.PattayaWorld.VisMeshPalms.VisPalm_<i> gets the RSD_Palm_<A|B|C> mesh at
-- the trunk foot with the Part palm's yaw: MeshParts named PalmTrunk / PalmFrond (PattayaLOD hides them beyond
-- LOD_PropRange like the Part palms), a 2-part impostor (PalmTrunk cylinder + flat PalmFrond card, attribute
-- VisMeshImpostor, Transparency 1 until the client VisMeshPalmLOD shows it beyond palmFullRange) and an invisible
-- VisMeshPalmCollider (the old trunk collided).
-- mesh-opt (team7, WRITTEN, NOT BUILT IN STUDIO): the export carries two mesh tiers per building: `m` = merged rows
-- (wide W-bay x H-floor kit assets from tools/blender/gen_merged.py, BLD_<G>_<Variant>W<w>H<h>, one row repeated every
-- H floors) and `mb` = the VIS-7.1 1-bay kit rows. Per Part row group: merged when every merged asset of the group is
-- usable, else the 1-bay kit, else the Part kit (V.BuildMesh({merged = false}) forces the 1-bay kit). Merged tiles
-- split their glass into Glass + GlassAlt; each lit-hashes on its own (pi = 7 x glass ordinal). Palms: with
-- vm.palmImpostorCollides the impostor trunk (cylinder at the trunk foot) is the collider (4 instances per palm).
local InsertService = game:GetService("InsertService")
local ServerStorage = game:GetService("ServerStorage")

local M = {}

local CACHE = "VisAssets"
local REMOVED = "VisMeshRemoved"
local PALMS = "VisMeshPalms"
local SIZE_TOL = 0.05

local function child(parent: Instance, name: string, create: boolean, class: string?): Instance?
	local c = parent:FindFirstChild(name)
	if not c and create then
		c = Instance.new(class or "Folder")
		c.Name = name
		c.Parent = parent
	end
	return c
end

local function v3(t: {number}): Vector3
	return Vector3.new(t[1], t[2], t[3])
end

type Tpl = {part: MeshPart, rot: CFrame}
type Assets = {tpl: {[string]: {[string]: Tpl}}, failed: {[string]: string}, loadedNow: number, cached: number,
	offsetMax: number, rotMax: number}

-- the loaded MeshPart for one manifest part: by its own name, by its node ("<part>_Node"), else the only MeshPart of
-- the asset with exactly that size (the importer's naming is not pinned down by a test yet)
local IMPORT_YAW = CFrame.Angles(0, math.pi, 0) -- see prepareAssets: the importer bakes a 180 deg yaw

local function findPart(root: Instance, sp: any, taken: {[Instance]: boolean}): MeshPart?
	local bySize: {MeshPart} = {}
	local want = Vector3.new(sp.size[1], sp.size[2], sp.size[3])
	for _, d in root:GetDescendants() do
		if d:IsA("MeshPart") and not taken[d] then
			local parent = d.Parent
			if d.Name == sp.name or (parent and (parent.Name == sp.name .. "_Node" or parent.Name == sp.name)) then
				return d
			end
			local e = d.Size - want
			if math.max(math.abs(e.X), math.abs(e.Y), math.abs(e.Z)) <= 0.05 then
				table.insert(bySize, d)
			end
		end
	end
	return if #bySize == 1 then bySize[1] else nil
end

-- asset cache ---------------------------------------------------------------------------------------------------------
local function prepareAssets(vm: any, names: {[string]: boolean}): Assets
	-- Edit mode caches require(): after a re-upload changes the ids, a Clone() is the only way to read the new source
	-- (leader, VIS-7.1b: BuildMesh loaded the old palm ids and reported them unusable)
	local manifestMod = ServerStorage:WaitForChild("VisAssetsManifest") :: ModuleScript
	local RunService = game:GetService("RunService")
	local ids = require(if RunService:IsEdit() then manifestMod:Clone() else manifestMod) :: any
	local byName: {[string]: any} = {}
	for _, a in vm.assets do
		byName[a.name] = a
	end
	local cache = child(ServerStorage, CACHE, true) :: Instance
	local out: Assets = {tpl = {}, failed = {}, loadedNow = 0, cached = 0, offsetMax = 0, rotMax = 0}
	local list = {}
	for name in names do
		table.insert(list, name)
	end
	table.sort(list)
	for _, name in list do
		local a = byName[name]
		local root = cache:FindFirstChild(name)
		if root then
			out.cached += 1
		else
			local id = ids[name]
			if type(id) ~= "number" then
				out.failed[name] = "no id in VisAssetsManifest"
				continue
			end
			local ok, res = pcall(function()
				return InsertService:LoadAsset(id)
			end)
			if not ok or typeof(res) ~= "Instance" then
				out.failed[name] = "LoadAsset failed: " .. tostring(res)
				continue
			end
			root = res :: Instance
			root.Name = name
			for _, d in root:GetDescendants() do
				if d:IsA("BasePart") then
					d.Anchored = true -- loaded unanchored; the cache must not fall in ServerStorage either way
				end
			end
			root.Parent = cache
			out.loadedNow += 1
		end
		local r = root :: Instance
		local inner = r:FindFirstChildWhichIsA("Model")
		local pivotModel = if inner then inner elseif r:IsA("Model") then r else nil
		local pivot = if pivotModel then (pivotModel :: Model):GetPivot() else CFrame.identity
		local tpl: {[string]: Tpl} = {}
		local bad: string? = nil
		local taken: {[Instance]: boolean} = {}
		for _, sp in a.parts do
			local mp = findPart(r, sp, taken)
			if not mp then
				bad = "no MeshPart " .. sp.name
				break
			end
			taken[mp] = true
			local want = v3(sp.size)
			local d = mp.Size - want
			if math.max(math.abs(d.X), math.abs(d.Y), math.abs(d.Z)) > SIZE_TOL then
				bad = ("%s size %s, manifest %s"):format(sp.name, tostring(mp.Size), tostring(want))
				break
			end
			-- placement uses the manifest centre and no rotation (the manifest is in Roblox axes); the loaded offset and
			-- rotation are only measured, so a surprise shows up in the BuildMesh report
			local rel = pivot:ToObjectSpace(mp.CFrame)
			out.offsetMax = math.max(out.offsetMax, (rel.Position - v3(sp.centre)).Magnitude)
			local _, ang = mp.CFrame.Rotation:ToAxisAngle()
			out.rotMax = math.max(out.rotMax, math.deg(math.abs(ang)))
			-- IMPORT_YAW (leader, measured 2026-10-19): Roblox's glTF importer bakes every mesh rotated 180 deg about Y
			-- (RSD_Palm_A_Bark centre +0.969 x in the file loads at -0.97; the MeshPart's own rotation reads 0). The
			-- manifest centre is kept and the part is turned back, so a module's street-side detail faces the street
			-- (before this, sign boards showed their open back and asymmetric modules faced into the wall).
			tpl[sp.short] = {part = mp, rot = IMPORT_YAW}
		end
		if bad then
			out.failed[name] = bad
		else
			out.tpl[name] = tpl
		end
	end
	return out
end

local function newMeshPart(tpl: Tpl, cf: CFrame, sp: any, scale: number, parent: Instance): MeshPart
	local mp = tpl.part:Clone()
	for _, c in mp:GetChildren() do
		if not c:IsA("SurfaceAppearance") then
			c:Destroy()
		end
	end
	mp.Anchored = true
	mp.CanCollide = false
	mp.CanQuery = false
	mp.CanTouch = false
	if scale ~= 1 then
		mp.Size = v3(sp.size) * scale
	end
	mp.CFrame = cf * CFrame.new(v3(sp.centre) * scale) * tpl.rot
	pcall(function()
		(mp :: any).RenderFidelity = Enum.RenderFidelity.Automatic
	end)
	mp:SetAttribute("VisPart", sp.short)
	mp:SetAttribute("VisScale", scale)
	mp.Parent = parent
	return mp
end

-- data ------------------------------------------------------------------------------------------------------------------
local function loadData(V: any, opts: any): (any, any, Instance)
	local I = V._internal
	local data = I.dataFolder(opts.folder)
	local man = I.load(data:WaitForChild("manifest"))
	local vmMod = data:FindFirstChild("vismesh")
	assert(vmMod, "PattayaVisSliceBuilder: no PattayaDataVisSlice.vismesh (re-copy build/vis_slice/roblox)")
	return man, I.load(vmMod), data
end

local function wantedSet(vm: any, only: {any}?): ({[number]: boolean}, {[string]: boolean}?)
	local osm: {[number]: boolean} = {}
	local chunks: {[string]: boolean}? = nil
	if only == nil then
		for _, id in vm.sample do
			osm[id] = true
		end
		return osm, nil
	end
	local c: {[string]: boolean} = {}
	for _, v in only do
		if type(v) == "number" then
			osm[v] = true
		else
			c[tostring(v)] = true
		end
	end
	if next(c) then
		chunks = c
	end
	return osm, chunks
end

-- one building --------------------------------------------------------------------------------------------------------
local function buildMeshBuilding(V: any, ctx: any, vm: any, A: Assets, b: any, original: BasePart?): (Model, any)
	local I = V._internal
	local man = ctx.man
	local mesh = b.mesh
	local FACE = I.FACE
	-- tiers per Part row group: "m" merged rows usable, else "b" 1-bay kit rows usable, else the Part kit (nil)
	local Q = mesh.q
	local Mm: {any} = mesh.m
	local Mb: {any} = mesh.mb or mesh.m
	if ctx.useMerged == false then
		Mm = Mb
	end
	local oneTier = Mm == Mb
	local hasRows: {[number]: boolean} = {}
	local function scan(M: {any}): ({[number]: boolean}, {[number]: boolean}, boolean)
		local has, blk, cornerOk = {}, {}, true
		for r = 0, #M // 10 - 1 do
			local g = M[r * 10 + 8]
			local ok = A.tpl[vm.assets[M[r * 10 + 2]].name] ~= nil
			if g ~= 0 then
				has[g] = true
				hasRows[g] = true
				if not ok then blk[g] = true end
			elseif not ok then
				cornerOk = false
			end
		end
		return has, blk, cornerOk
	end
	local hasM, blkM, cornerM = scan(Mm)
	local hasB, blkB, cornerB = scan(Mb)
	local tier: {[number]: string} = {}
	for g in hasM do
		if not blkM[g] then
			tier[g] = "m"
		elseif not oneTier and hasB[g] and not blkB[g] then
			tier[g] = "b"
		end
	end
	for r = 0, #Q // 6 - 1 do
		local g = Q[r * 6 + 6]
		hasRows[g] = true
		tier[g] = if A.tpl[vm.assets[Q[r * 6 + 1]].name] then "q" else nil
	end
	-- corner stacks (group 0): the merged set when all of it loads, else the 1-bay set (unusable rows skipped)
	local cornerTier = if cornerM or oneTier then "m" else (if cornerB then "b" else "m")
	local function meshed(g: number): boolean
		return g ~= 0 and tier[g] ~= nil
	end
	local nMergedRows, nBaseRows = 0, 0
	for g, t in tier do
		if t == "m" and not oneTier then nMergedRows += 1 elseif t == "b" or (t == "m" and oneTier) then nBaseRows += 1 end
	end
	-- Part rows that stay (no mesh, or their mesh group fell back)
	local keepP, fallbackRows = {}, 0
	for i = 1, #mesh.pg do
		local g = mesh.pg[i]
		if not meshed(g) then
			if hasRows[g] then fallbackRows += 1 end
			for t = 1, 10 do
				table.insert(keepP, mesh.p[(i - 1) * 10 + t])
			end
		end
	end
	local keepR = {}
	for i = 1, #mesh.rg do
		local g = mesh.rg[i]
		if not meshed(g) then
			if hasRows[g] then fallbackRows += 1 end
			for t = 1, 3 do
				table.insert(keepR, b.r[(i - 1) * 3 + t])
			end
		end
	end
	local b2 = table.clone(b)
	b2.ins, b2.p, b2.r = mesh.ins, keepP, keepR
	local model, nParts, colour = I.buildBuilding(ctx, b2, nil, original)

	local o = V.ORIGIN
	local base = CFrame.new(b.x + o.X, I.BASE_Y + o.Y, b.z + o.Z) * CFrame.Angles(0, -math.rad(b.yaw), 0)
	local style = man.styles[b.style]
	local litCfg = man.lit
	local tones: {Color3} = {}
	for _, t in litCfg.tones do
		table.insert(tones, I.rgb(t))
	end
	local upperTone = I.rgb(litCfg.upper_tone)
	local upperStyle = table.find(litCfg.upper_styles, style.name) ~= nil
	local cols = ctx.colors
	local text = if b.txt > 0 then man.texts[b.txt] else nil
	local textColour = I.rgb(man.signCombos[b.sc].text)
	local minShadow = vm.castShadowMinHeight or 8
	local nMesh, nSigns, nLit = 0, 0, 0

	local function dress(mp: MeshPart, sp: any, a: any, slot: string, inst: string, lit: boolean?, hsh: number,
		upper: boolean, ground: boolean)
		local matName = sp.mat
		mp:SetAttribute("VisAsset", a.name)
		if sp.mp == "MP_NeonCyan" or sp.mp == "MP_NeonMagenta" then
			local mag = sp.mp == "MP_NeonMagenta"
			local day = if mag then cols.neonMagentaDay else cols.neonCyanDay
			mp.Color = day
			mp.Material = Enum.Material.SmoothPlastic
			mp:SetAttribute("NightNeon", true)
			mp:SetAttribute("DayColor", day)
			mp:SetAttribute("NightColor", if mag then cols.neonMagenta else cols.neonCyan)
			if ground then
				mp.Name = "NeonSign" -- street-level neon fades beyond LOD_PropRange like the Part neon strips
			end
		elseif lit then
			matName = "LitWindow"
			local day = colour(sp.col)
			mp.Color = day
			mp.Material = Enum.Material.SmoothPlastic
			mp:SetAttribute("NightNeon", true)
			mp:SetAttribute("DayColor", day)
			mp:SetAttribute("NightColor", if upper then upperTone else tones[math.floor(hsh / 100) % #tones + 1])
			nLit += 1
		else
			mp.Color = colour(sp.col)
			mp.Material = ctx.mats[matName] or Enum.Material.SmoothPlastic
			I.styleWithLibrary(ctx.lib, mp, matName, true)
		end
		mp.CastShadow = sp.mp == "MP_Wall" and mp.Size.Y >= minShadow
		mp:SetAttribute("Mat", matName)
		mp:SetAttribute("MeshSlot", slot)
		mp:SetAttribute("SlotInst", inst)
	end

	-- facade rows: face, asset, uc, v0, nv, dv, scale, group, flags, column (tier "m" from Mm, tier "b" from Mb)
	local function emit(Mrows: {any}, which: string)
	for r = 0, #Mrows // 10 - 1 do
		local q = r * 10
		local f, ai, uc, v0, nv, dv, sc, g, fl, j =
			Mrows[q + 1], Mrows[q + 2], Mrows[q + 3], Mrows[q + 4], Mrows[q + 5], Mrows[q + 6], Mrows[q + 7], Mrows[q + 8],
			Mrows[q + 9], Mrows[q + 10]
		local a = vm.assets[ai]
		local tpl = A.tpl[a.name]
		if not tpl then continue end
		if g == 0 then
			if cornerTier ~= which then continue end
		elseif tier[g] ~= which then
			continue
		end
		local face = FACE[f]
		local dist = (if face.half == "w" then b.w else b.d) / 2
		local ins = mesh.ins[f]
		local above = bit32.band(fl, 16) ~= 0
		local litKind = if bit32.band(fl, 1) ~= 0 then "win" elseif bit32.band(fl, 2) ~= 0 then "shop" else nil
		local slot = if g == 0 then "corner" else man.modules[mesh.p[(g - 1) * 10 + 2]].slot
		local pct = 0
		if litKind then
			pct = if litKind == "win" then style.litWin else style.litShop
			pct = math.clamp(pct + b.osm % (2 * litCfg.spread + 1) - litCfg.spread, 0, 100)
		end
		for k = 0, nv - 1 do
			local y = v0 + k * dv
			local origin = base * CFrame.fromMatrix(face.n * (dist - ins) + face.u * uc + Vector3.new(0, y, 0), face.u,
				Vector3.yAxis, -face.n)
			for _, sp in a.parts do
				-- twin: VisMesh.mesh_lit_hash (GlassAlt = glass ordinal 1 -> pi 7, 49 off mod 100)
				local hsh = V.litHash(b.osm, f, 900 + ai, k, j, 7 * (sp.gi or 0), litCfg.hash_mod)
				local mp = newMeshPart(tpl[sp.short], origin, sp, sc, model)
				local lit = litKind ~= nil and sp.mp == "MP_Glass" and hsh % 100 < pct
				dress(mp, sp, a, slot, ("m%d:%d:%d"):format(r + 1, k, j), lit, hsh,
					upperStyle and y + 4 > b.h / 2, v0 == 0 and not above)
				if above then mp:SetAttribute("AboveRoof", true) end
				if bit32.band(fl, 4) ~= 0 and sp.mp == "MP_Signboard" and text and ctx.signs then
					I.addSign(mp, text, textColour)
					nSigns += 1
				end
				nMesh += 1
			end
		end
	end
	end
	emit(Mm, "m")
	if not oneTier then
		emit(Mb, "b")
	end
	-- roof rows: asset, x, z, yaw (deg), scale, group
	for r = 0, #Q // 6 - 1 do
		local q = r * 6
		local ai, x, z, yaw, sc, g = Q[q + 1], Q[q + 2], Q[q + 3], Q[q + 4], Q[q + 5], Q[q + 6]
		local a = vm.assets[ai]
		local tpl = A.tpl[a.name]
		if not tpl or tier[g] ~= "q" then continue end
		local origin = base * CFrame.new(x, b.h, z) * CFrame.Angles(0, math.rad(yaw), 0)
		local rr = b.r[(g - 1001) * 3 + 1]
		local slot = man.roofModules[rr].slot
		for _, sp in a.parts do
			local mp = newMeshPart(tpl[sp.short], origin, sp, sc, model)
			dress(mp, sp, a, slot, ("q%d"):format(r + 1), false, 0, false, false)
			mp:SetAttribute("AboveRoof", true)
			nMesh += 1
		end
	end
	model:SetAttribute("VisMesh", true)
	model:SetAttribute("PartBuildParts", b.parts)
	model:SetAttribute("ExpectParts", nParts)
	model:SetAttribute("ExpectMeshParts", nMesh)
	model:SetAttribute("FallbackRows", fallbackRows)
	model:SetAttribute("MeshTier", if oneTier then "base" elseif nBaseRows == 0 then "merged" else "mixed")
	return model, {parts = nParts, meshParts = nMesh, fallback = fallbackRows, signs = nSigns, lit = nLit,
		mergedRows = if oneTier then 0 else nMergedRows, baseRows = nBaseRows}
end

-- palms -----------------------------------------------------------------------------------------------------------------
type PalmParts = {trunk: BasePart, fronds: {BasePart}}

-- the Part palms of one city chunk, keyed by the trunk foot (PattayaBuilder: foot = trunk CFrame * (-h/2, 0, 0))
local function cityPalms(props: Instance?): {PalmParts}
	local out: {PalmParts} = {}
	if not props then
		return out
	end
	local fronds: {BasePart} = {}
	for _, p in props:GetChildren() do
		if p:IsA("BasePart") and p.Name == "PalmFrond" then
			table.insert(fronds, p)
		end
	end
	for _, p in props:GetChildren() do
		if p:IsA("BasePart") and p.Name == "PalmTrunk" then
			local top = p.CFrame:PointToWorldSpace(Vector3.new(p.Size.X / 2, 0, 0))
			local mine = {}
			for _, fr in fronds do
				if (fr.Position - top).Magnitude < 8 then
					table.insert(mine, fr)
				end
			end
			table.insert(out, {trunk = p, fronds = mine})
		end
	end
	return out
end

local function buildPalms(V: any, ctx: any, vm: any, A: Assets): any
	local I = V._internal
	local world = workspace:FindFirstChild("PattayaWorld") :: Instance
	local root = child(world, PALMS, true, "Folder") :: Instance
	local removed = child(child(ServerStorage, REMOVED, true) :: Instance, "Palms", true) :: Instance
	local o = V.ORIGIN
	local byChunk: {[string]: {PalmParts}} = {}
	local res = {built = 0, already = 0, moved = 0, notFound = 0, failed = 0, meshParts = 0}
	for i, row in vm.palms do
		local name = "VisPalm_" .. i
		if root:FindFirstChild(name) then
			res.already += 1
			continue
		end
		local x, z, var, yaw, hOld = row[1], row[2], row[3], row[4], row[5]
		local src = vm.palmSrc[i]
		local aName = vm.palmAssets[var]
		local tpl = A.tpl[aName]
		if not tpl then
			res.failed += 1 -- the Part palm stays
			continue
		end
		local a: any = nil
		for _, e in vm.assets do
			if e.name == aName then a = e end
		end
		local foot = Vector3.new(x + o.X, I.BASE_Y + o.Y, z + o.Z)
		-- find and stash the Part palm
		if not byChunk[src] then
			local ch = I.cityChunk(world, src)
			byChunk[src] = cityPalms(ch and ch:FindFirstChild("Props"))
		end
		local found: PalmParts? = nil
		for _, pp in byChunk[src] do
			local t = pp.trunk
			local f = t.CFrame:PointToWorldSpace(Vector3.new(-t.Size.X / 2, 0, 0))
			if t.Parent and (f - foot).Magnitude < 0.3 and math.abs(t.Size.X - hOld) < 0.3 then
				found = pp
				break
			end
		end
		if found then
			local dest = child(removed, "Chunk_" .. src, true) :: Instance
			for _, p in {found.trunk, table.unpack(found.fronds)} do
				p:SetAttribute("FromParent", (p.Parent :: Instance).Name)
				p.Parent = dest
				res.moved += 1
			end
		else
			res.notFound += 1
		end
		local model = Instance.new("Model")
		model.Name = name
		model:SetAttribute("VisPalm", true)
		model:SetAttribute("VisAsset", aName)
		model:SetAttribute("Src", src)
		model:SetAttribute("PartPalmFound", found ~= nil)
		local cf = CFrame.new(foot) * CFrame.Angles(0, yaw, 0)
		local bark, leaf = nil, nil
		for _, sp in a.parts do
			local mp = newMeshPart(tpl[sp.short], cf, sp, 1, model)
			mp:SetAttribute("VisAsset", aName)
			mp:SetAttribute("Mat", sp.mat)
			if sp.mp == "MP_Bark" then
				mp.Name = "PalmTrunk"
				mp.Material = Enum.Material.Wood
				bark = sp
			else
				mp.Name = "PalmFrond"
				I.styleWithLibrary(ctx.lib, mp, "Vegetation", true)
				leaf = sp
			end
			mp.CastShadow = true -- like the Part palms
			res.meshParts += 1
		end
		-- impostor: trunk cylinder + flat crown card, hidden until the client VisMeshPalmLOD shows it far away
		local function imp(nm: string, size: Vector3, at: CFrame, col: Color3)
			local p = Instance.new("Part")
			p.Name = nm
			p.Shape = Enum.PartType.Cylinder
			p.Size = size
			p.CFrame = at
			p.Color = col
			p.Material = Enum.Material.SmoothPlastic
			p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch, p.CastShadow = true, false, false, false, false
			p.Transparency = 1
			p:SetAttribute("VisMeshImpostor", true)
			p.Parent = model
		end
		local barkMp = model:FindFirstChild("PalmTrunk") :: BasePart?
		local leafMp = model:FindFirstChild("PalmFrond") :: BasePart?
		local impCollides = vm.palmImpostorCollides == true
		if bark and barkMp then
			local h = bark.size[2]
			-- mesh-opt: with palmImpostorCollides the trunk impostor stands at the trunk foot and is the collider (the
			-- old Part trunk collided too); far away it is the visible trunk, near it is invisible but still solid
			local at = if impCollides then cf * CFrame.new(0, h / 2, 0) else cf * CFrame.new(bark.centre[1], h / 2, bark.centre[3])
			imp("PalmTrunk", Vector3.new(h, 1.6, 1.6), at * CFrame.Angles(0, 0, math.pi / 2), barkMp.Color)
			if impCollides then
				for _, c in model:GetChildren() do
					if c:IsA("Part") and c:GetAttribute("VisMeshImpostor") and c.Name == "PalmTrunk" then
						c.CanCollide, c.CanQuery = true, true
						c:SetAttribute("VisMeshPalmCollider", true)
					end
				end
			end
		end
		if leaf and leafMp then
			local d = 0.8 * math.max(leaf.size[1], leaf.size[3])
			imp("PalmFrond", Vector3.new(0.4, d, d), cf * CFrame.new(v3(leaf.centre)) * CFrame.Angles(0, 0, math.pi / 2),
				leafMp.Color)
		end
		if not (impCollides and bark and barkMp) then
			local cs = vm.palmCollider
			local col = Instance.new("Part")
			col.Name = "VisMeshPalmCollider"
			col.Size = Vector3.new(cs[1], cs[2], cs[3])
			col.CFrame = cf * CFrame.new(0, cs[2] / 2, 0)
			col.Transparency = 1
			col.Anchored, col.CanCollide, col.CanQuery, col.CanTouch, col.CastShadow = true, true, true, false, false
			col.Parent = model
		end
		model.Parent = root
		res.built += 1
		if i % 40 == 0 then task.wait() end
	end
	root:SetAttribute("FullRange", vm.palmFullRange)
	return res
end

-- public ------------------------------------------------------------------------------------------------------------
function M.BuildMesh(V: any, opts: any): string
	local I = V._internal
	local man, vm, data = loadData(V, opts)
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "PattayaVisSliceBuilder: build the city first (PattayaBuilder.Build())")
	local root = world:FindFirstChild(I.ROOT_NAME)
	local ctx = I.context(man, opts)
	ctx.useMerged = opts.merged ~= false
	local wantOsm, wantChunk = wantedSet(vm, opts.only)
	local doBuildings = opts.buildings ~= false
	local doPalms = opts.palms ~= false and opts.only == nil or opts.palms == true

	-- which chunks / buildings, and which assets they need
	local todo = {}
	local names: {[string]: boolean} = {}
	if doBuildings then
		for _, id in vm.sampleChunks do
			if wantChunk and not wantChunk[id] then continue end
			local cd = I.load(data:WaitForChild("chunk_" .. id))
			for _, b in cd.buildings do
				if b.mesh and (wantChunk ~= nil or wantOsm[b.osm]) then
					table.insert(todo, {id = id, src = cd.src, b = b})
					local rowsM = if ctx.useMerged then b.mesh.m else (b.mesh.mb or b.mesh.m)
					for r = 0, #rowsM // 10 - 1 do
						names[vm.assets[rowsM[r * 10 + 2]].name] = true
					end
					for r = 0, #b.mesh.q // 6 - 1 do
						names[vm.assets[b.mesh.q[r * 6 + 1]].name] = true
					end
				end
			end
		end
	end
	if doPalms then
		for _, n in vm.palmAssets do
			names[n] = true
		end
	end
	local A = prepareAssets(vm, names)
	-- merged asset unusable -> its buildings need the 1-bay kit assets as well: load those too (second pass)
	if ctx.useMerged and next(A.failed) then
		local more: {[string]: boolean} = {}
		for _, t in todo do
			local mb = t.b.mesh.mb
			if mb then
				for r = 0, #mb // 10 - 1 do
					local n = vm.assets[mb[r * 10 + 2]].name
					if not names[n] then more[n] = true end
				end
			end
		end
		if next(more) then
			local B2 = prepareAssets(vm, more)
			for n, tp in B2.tpl do A.tpl[n] = tp end
			for n, why in B2.failed do A.failed[n] = why end
			A.loadedNow += B2.loadedNow
			A.cached += B2.cached
			A.offsetMax = math.max(A.offsetMax, B2.offsetMax)
			A.rotMax = math.max(A.rotMax, B2.rotMax)
		end
	end
	for n, why in A.failed do
		warn(("VisMesh: asset %s unusable (%s): its rows fall back to Parts"):format(n, why))
	end

	local nB, nSkip, nMissing, parts, meshParts, fallback, signs, lit = 0, 0, 0, 0, 0, 0, 0, 0
	local mergedRows, baseRows = 0, 0
	local removedB = child(child(ServerStorage, REMOVED, true) :: Instance, "Buildings", true) :: Instance
	local originals: {[string]: {[number]: BasePart}} = {}
	for _, t in todo do
		local chunk = root and root:FindFirstChild("Chunk_" .. t.id)
		if not chunk then
			warn(("VisMesh: Chunk_%s is not built: run V.Build({only = {\"%s\"}}) first"):format(t.id, t.id))
			nMissing += 1
			continue
		end
		local existing = chunk:FindFirstChild("Vis_" .. t.b.osm)
		if existing and existing:GetAttribute("VisMesh") then
			nSkip += 1
			continue
		end
		if not originals[t.src] then
			local map = I.originalsIn(I.backupChunk(t.src, false))
			for osm, p in I.originalsIn(I.cityChunk(world, t.src)) do
				if not map[osm] then map[osm] = p end
			end
			originals[t.src] = map
		end
		local model, r = buildMeshBuilding(V, ctx, vm, A, t.b, originals[t.src][t.b.osm])
		if existing then
			existing:SetAttribute("FromChunk", chunk.Name)
			existing.Parent = child(removedB, chunk.Name, true)
		end
		model.Parent = chunk
		nB += 1
		parts += r.parts
		meshParts += r.meshParts
		fallback += r.fallback
		signs += r.signs
		lit += r.lit
		mergedRows += r.mergedRows
		baseRows += r.baseRows
		task.wait()
	end
	local palmMsg = "palms not requested"
	if doPalms then
		local p = buildPalms(V, ctx, vm, A)
		palmMsg = ("palms: %d mesh palms built (%d MeshParts), %d already there, %d Part palm parts moved to ServerStorage.%s.Palms, %d Part palms not found in the city chunk, %d kept (asset unusable)")
			:format(p.built, p.meshParts, p.already, p.moved, REMOVED, p.notFound, p.failed)
	end
	local failedList = {}
	for n in A.failed do
		table.insert(failedList, n)
	end
	table.sort(failedList)
	return ("vismesh: assets %d loaded now, %d from ServerStorage.%s, %d unusable [%s] (loaded vs manifest: max centre offset %.3f studs, max rotation %.1f deg); buildings %d built (%d Parts + %d MeshParts, %d Part rows fell back, %d signboards, %d lit panes; Part rows on merged tiles %d, on the 1-bay kit %d), %d already mesh, %d chunks missing; expected when every asset loads: %d Parts + %d MeshParts (1-bay kit: %d, BuildMesh({merged = false})) for the %d sample buildings; %s")
		:format(A.loadedNow, A.cached, CACHE, #failedList, table.concat(failedList, ", "), A.offsetMax, A.rotMax, nB, parts, meshParts,
			fallback, signs, lit, mergedRows, baseRows, nSkip, nMissing, vm.expected.parts, vm.expected.meshParts,
			vm.expected.meshPartsBase or vm.expected.meshParts, #vm.sample, palmMsg)
end

function M.RemoveMesh(V: any, opts: any): string
	local I = V._internal
	local world = workspace:FindFirstChild("PattayaWorld")
	local removed = ServerStorage:FindFirstChild(REMOVED)
	local nB, nRestored, nP, nPalmModels = 0, 0, 0, 0
	local root = world and world:FindFirstChild(I.ROOT_NAME)
	local rb = removed and removed:FindFirstChild("Buildings")
	if root then
		for _, chunk in root:GetChildren() do
			for _, m in chunk:GetChildren() do
				if m:GetAttribute("VisMesh") == true then
					local name = m.Name
					m:Destroy()
					nB += 1
					local back = rb and rb:FindFirstChild(chunk.Name)
					local part = back and back:FindFirstChild(name)
					if part then
						part:SetAttribute("FromChunk", nil)
						part.Parent = chunk
						nRestored += 1
					end
				end
			end
		end
	end
	if rb then
		rb:Destroy() -- what is left belongs to chunks that no longer exist
	end
	local palms = world and world:FindFirstChild(PALMS)
	if palms then
		nPalmModels = #palms:GetChildren()
		palms:Destroy()
	end
	local rp = removed and removed:FindFirstChild("Palms")
	local lost = 0
	if rp and world then
		for _, c in rp:GetChildren() do
			local chunk = I.cityChunk(world, string.sub(c.Name, 7))
			for _, p in c:GetChildren() do
				local parent = chunk and chunk:FindFirstChild(p:GetAttribute("FromParent") or "Props")
				if parent then
					p:SetAttribute("FromParent", nil)
					p.Parent = parent
					nP += 1
				else
					lost += 1
				end
			end
		end
	end
	return ("vismesh removed: %d mesh buildings (%d Part buildings back), %d mesh palms, %d Part palm parts back, %d left in ServerStorage.%s (city chunk gone)")
		:format(nB, nRestored, nPalmModels, nP, lost, REMOVED)
end

-- Checks after BuildMesh (edit mode or Play server):
--  * MeshParts outside their VisHull (all 8 bbox corners; AboveRoof parts may stand above the top) - expected 0
--  * MeshParts touching a Road / Sidewalk / Junction / Joint part - expected 0
--  * MeshPart Size vs Blender manifest size x VisScale (+- 0.05) - expected 0 mismatches
--  * per building: Parts / MeshParts vs the counts the builder recorded and vs the exporter (all assets loaded)
--  * palms: mesh palms, impostors, colliders, Part palms still in the city at a mesh palm (expected 0)
function M.ProbeMesh(V: any, opts: any): string
	local I = V._internal
	local _, vm, data = loadData(V, opts)
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "no workspace.PattayaWorld")
	local spec: {[string]: {[string]: any}} = {}
	for _, a in vm.assets do
		local t = {}
		for _, sp in a.parts do
			t[sp.short] = sp
		end
		spec[a.name] = t
	end
	local exp: {[number]: any} = {}
	for _, id in vm.sampleChunks do
		for _, b in I.load(data:WaitForChild("chunk_" .. id)).buildings do
			if b.mesh then exp[b.osm] = b.mesh end
		end
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
	local root = world:FindFirstChild(I.ROOT_NAME)
	local nB, nParts, nMesh, outside, onRoad, sizeBad, countBad, vsExport, fallback = 0, 0, 0, 0, 0, 0, 0, 0, 0
	local mixed = 0
	local checked = 0
	for _, chunk in (if root then root:GetChildren() else {}) do
		for _, m in chunk:GetChildren() do
			if m:GetAttribute("VisMesh") ~= true then continue end
			nB += 1
			local hull = m:FindFirstChild("VisHull") :: BasePart?
			local np, nm = 0, 0
			for _, p in m:GetChildren() do
				if not p:IsA("BasePart") then continue end
				if not p:IsA("MeshPart") then
					np += 1
					continue
				end
				nm += 1
				local sp = spec[p:GetAttribute("VisAsset") or ""]
				sp = sp and sp[p:GetAttribute("VisPart") or ""]
				local sc = (p:GetAttribute("VisScale") :: number?) or 1
				if not sp then
					sizeBad += 1
					warn("VisMesh: MeshPart without a manifest entry:", p:GetFullName())
				else
					local d = p.Size - v3(sp.size) * sc
					if math.max(math.abs(d.X), math.abs(d.Y), math.abs(d.Z)) > SIZE_TOL then
						sizeBad += 1
						warn("VisMesh: size differs from the manifest:", p:GetFullName(), p.Size)
					end
				end
				if hull then
					local half = hull.Size / 2 + Vector3.new(0.06, 0.06, 0.06)
					local above = p:GetAttribute("AboveRoof") == true
					for corner = 0, 7 do
						local sgn = Vector3.new(if corner % 2 == 0 then -1 else 1, if (corner // 2) % 2 == 0 then -1 else 1,
							if corner // 4 == 0 then -1 else 1)
						local c = hull.CFrame:PointToObjectSpace(p.CFrame:PointToWorldSpace(p.Size / 2 * sgn))
						if math.abs(c.X) > half.X or math.abs(c.Z) > half.Z or c.Y < -half.Y or (c.Y > half.Y and not above) then
							outside += 1
							warn("VisMesh: outside its box:", p:GetFullName())
							break
						end
					end
				end
				if #roads > 0 and #workspace:GetPartsInPart(p, params) > 0 then
					onRoad += 1
					warn("VisMesh: touches road:", p:GetFullName())
				end
				checked += 1
				if checked % 300 == 0 then task.wait() end
			end
			nParts += np
			nMesh += nm
			fallback += (m:GetAttribute("FallbackRows") :: number?) or 0
			if np ~= m:GetAttribute("ExpectParts") or nm ~= m:GetAttribute("ExpectMeshParts") then
				countBad += 1
				warn(("VisMesh: %s has %d Parts + %d MeshParts, builder recorded %s + %s"):format(m:GetFullName(), np, nm,
					tostring(m:GetAttribute("ExpectParts")), tostring(m:GetAttribute("ExpectMeshParts"))))
			end
			local e = exp[m:GetAttribute("OsmBuilding") :: number]
			local tierName = m:GetAttribute("MeshTier")
			local wantM = if e and tierName == "base" then (e.meshPartsBase or e.meshParts) else (e and e.meshParts)
			if e and tierName ~= "mixed" and (np ~= e.parts or nm ~= wantM) then
				vsExport += 1
			end
			if tierName == "mixed" then mixed += 1 end
		end
	end
	-- palms
	local palms = world:FindFirstChild(PALMS)
	local nPalm, nPalmMesh, nImp, nCol, partLeft = 0, 0, 0, 0, 0
	local o = V.ORIGIN
	local feet: {[string]: {Vector3}} = {}
	for _, pm in (if palms then palms:GetChildren() else {}) do
		nPalm += 1
		for _, p in pm:GetChildren() do
			if p:IsA("MeshPart") then nPalmMesh += 1 end
			if p:GetAttribute("VisMeshImpostor") then nImp += 1 end
			if p.Name == "VisMeshPalmCollider" or p:GetAttribute("VisMeshPalmCollider") then nCol += 1 end
		end
		local i = tonumber(string.sub(pm.Name, 9))
		local row = i and vm.palms[i]
		if row then
			local src = vm.palmSrc[i]
			feet[src] = feet[src] or {}
			table.insert(feet[src], Vector3.new(row[1] + o.X, I.BASE_Y + o.Y, row[2] + o.Z))
		end
	end
	for src, list in feet do
		local ch = I.cityChunk(world, src)
		for _, pp in cityPalms(ch and ch:FindFirstChild("Props")) do
			local t = pp.trunk
			local f = t.CFrame:PointToWorldSpace(Vector3.new(-t.Size.X / 2, 0, 0))
			for _, foot in list do
				if (f - foot).Magnitude < 0.3 then
					partLeft += 1
					break
				end
			end
		end
	end
	return ("vismesh probe: %d mesh buildings (sample %d): %d Parts + %d MeshParts (export expects %d + %d with every asset); MeshParts outside their box %d; touching road/sidewalk/disc %d; size != manifest x scale %d; buildings whose counts differ from the builder %d, from the export %d (%d on mixed merged / 1-bay tiers, not compared); Part rows on fallback %d | palms %d (of %d), %d MeshParts, %d impostor parts, %d colliders (separate or impostor trunk), Part palms still at a mesh palm %d")
		:format(nB, #vm.sample, nParts, nMesh, vm.expected.parts, vm.expected.meshParts, outside, onRoad, sizeBad, countBad,
			vsExport, mixed, fallback, nPalm, #vm.palms, nPalmMesh, nImp, nCol, partLeft)
end

return M
