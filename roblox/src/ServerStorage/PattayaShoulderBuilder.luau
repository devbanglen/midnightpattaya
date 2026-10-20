--!strict
-- Road shoulders, width tapers and carriageway hole fills along Sukhumvit Road (MIDNIGHT PATTAYA, pilot; the target
-- roads are a list in tools/mapgen/config/shoulders.json). Sukhumvit is built without sidewalks, so its slab edges
-- (road top 1.0) drop straight to the terrain (y -2), and the carriageway changes width abruptly at some nodes: a
-- wheel that leaves the slab falls about 3 studs. This layer ADDS flat road-height pieces beside the slabs; nothing
-- that exists is changed. Built in Studio (edit time) from the data modules in ServerStorage.PattayaDataShoulders
-- (tools/mapgen/road_shoulders.py -> build/shoulders/roblox: manifest + chunk_s<cx>_<cz>[_k]). Every chunk becomes an
-- Atomic Model workspace.PattayaWorld.ShoulderChunks.Chunk_<id> (<= 600 parts). Built chunks are skipped, so a call
-- can be repeated after an error. Written and run offline (luau CLI with stub Roblox types), NOT run in Studio yet.
--   local Sh = require(game.ServerStorage.PattayaShoulderBuilder)
--   Sh.Build({batch = "s1"})              -- one batch (<= 8 chunks), then "s2" ... (manifest.batchOrder)
--   Sh.Build({only = {"s9_1"}})            -- explicit chunk ids
--   Sh.Build()                             -- everything left
--   Sh.Probe()                             -- counts, flushness, overlap self-checks of what is built (prints + returns)
--   Sh.BuildTerrain({batch = "s1"})        -- OPTIONAL, separate: terrain fill boxes beside the shoulders (backed up first)
--   Sh.RemoveTerrain()                     -- writes the backed-up voxels back (terrain only)
--   Sh.Remove()                            -- full rollback: RemoveTerrain() + destroys ShoulderChunks
-- Piece: name manifest.shoulder.name ("Shoulder"), top manifest.shoulder.top (0.985: 1.5 cm under the road top, under
-- the junction / joint discs 0.99, above the aprons 0.98), 4 thick, Concrete 92,91,88 (RoadLook restyles only parts
-- named Road / Joint / Junction / markings / Sidewalk, so the shoulder keeps its own look), CanCollide / CanQuery true
-- (the car's suspension rays must hit it), attributes RoadFill = true (the leader's slab-overlap probe skips RoadFill
-- parts), Shoulder = true, ShoulderKind = "shoulder" | "taper" | "gap". Rows: boxes {cx, cz, ux, uz, length, width,
-- kind} = one Part (length along (ux, uz)); tris {x1, z1, x2, z2, x3, z3, kind} = two WedgeParts split at the foot of
-- the altitude on the longest side (exactly as PattayaBuilder.roadTriangle / PattayaApronBuilder.triangle).
-- Map-local (x, z) + ORIGIN. Geometry must match tools/mapgen/road_shoulders.py (piece_poly / wedge_count).
local ServerStorage = game:GetService("ServerStorage")

local Shoulders = {}

Shoulders.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN
Shoulders.FOLDER = "ShoulderChunks"
Shoulders.DATA = "PattayaDataShoulders"
Shoulders.BACKUP = "PattayaShoulderTerrainBackup" -- ServerStorage folder of TerrainRegion backups (BuildTerrain)
local ROAD_NAMES = {Road = true, Junction = true, Joint = true}
local MARK_NAMES = {Centre = true, Dash = true, ZebraStripe = true}
local KINDS = {"shoulder", "taper", "gap"}
local MODEL_NAMES = {shoulder = "Shoulders", taper = "Tapers", gap = "Fills"}

type Style = {top: number, thick: number, material: Enum.Material, color: Color3, name: string}

local function style(row: any): Style
	local mat = Enum.Material.Concrete
	local ok, m = pcall(function()
		return (Enum.Material :: any)[row.material]
	end)
	if ok and m then
		mat = m
	end
	return {top = row.top, thick = row.thick, material = mat, color = Color3.fromRGB(row.color[1], row.color[2], row.color[3]),
		name = row.name or "Shoulder"}
end

local function finish(p: BasePart, s: Style, kind: string, parent: Instance)
	p.Name = s.name
	p.Anchored = true
	p.Color = s.color
	p.Material = s.material
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.CanCollide = true
	p.CanQuery = true -- the car's suspension raycasts must hit it
	p.CanTouch = false
	p.CastShadow = false
	p:SetAttribute("RoadFill", true)
	p:SetAttribute("Shoulder", true)
	p:SetAttribute("ShoulderKind", kind)
	p.Parent = parent
end

-- one flat triangle a-b-c from two WedgeParts (PattayaBuilder.roadTriangle with a top / thickness / style)
local function triangle(parent: Instance, a: Vector2, b: Vector2, c: Vector2, s: Style, kind: string): number
	local ab, bc, ca = (b - a).Magnitude, (c - b).Magnitude, (a - c).Magnitude
	if bc > ab and bc >= ca then
		a, b, c = b, c, a
	elseif ca > ab and ca > bc then
		a, b, c = c, a, b
	end -- now a-b is the longest side
	local len = (b - a).Magnitude
	if len < 0.05 then
		return 0
	end
	local dir = (b - a) / len
	local t = (c - a):Dot(dir)
	local foot = a + dir * t
	local h = (c - foot).Magnitude
	if h < 0.05 then
		return 0
	end
	local y = s.top - s.thick / 2
	local yv = Vector3.new(c.X - foot.X, 0, c.Y - foot.Y) / h -- object Y: foot -> apex
	local n = 0
	for _, corner in {a, b} do
		local l = (foot - corner).Magnitude
		if l > 0.05 then
			local zv = Vector3.new(foot.X - corner.X, 0, foot.Y - corner.Y) / l -- object Z: acute corner -> foot
			local xv = yv:Cross(zv) -- object X: up (+Y world) for both wedges
			local centre = foot + Vector2.new(yv.X, yv.Z) * (h / 2) - Vector2.new(zv.X, zv.Z) * (l / 2)
			local w = Instance.new("WedgePart")
			w.Size = Vector3.new(s.thick, h, l)
			w.CFrame = CFrame.fromMatrix(Vector3.new(centre.X, y, centre.Y), xv, yv, zv)
			finish(w, s, kind, parent)
			n += 1
		end
	end
	return n
end

local function data(folderName: string?): (Instance, any)
	local d = ServerStorage:WaitForChild(folderName or Shoulders.DATA)
	local manModule = d:WaitForChild("manifest") :: ModuleScript
	return d, require(manModule:Clone()) :: any -- Clone(): a just-replaced module is never served from the require cache
end

local function chunkData(folderData: Instance, id: string): any
	local m = folderData:WaitForChild("chunk_" .. id) :: ModuleScript
	return require(m:Clone()) :: any
end

local function selection(man: any, options: any): {[string]: boolean}?
	if options.batch then
		options.only = man.batches[options.batch] or error("unknown shoulder batch " .. tostring(options.batch))
	end
	if options.only == nil then
		return nil
	end
	local wanted: {[string]: boolean} = {}
	for _, id in options.only do
		wanted[id] = true
	end
	return wanted
end

local function world(): Instance
	local w = workspace:FindFirstChild("PattayaWorld")
	if not w then
		error("PattayaShoulderBuilder: build the city first (PattayaBuilder.Build / Extend)")
	end
	return w :: Instance
end

-- builds one chunk's data into a new Atomic Model (not parented); returns the model and its part count
function Shoulders.buildChunk(id: string, d: any, s: Style): (Model, number)
	local chunk = Instance.new("Model")
	chunk.Name = "Chunk_" .. id
	chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	local models: {[string]: Model} = {}
	for _, k in KINDS do
		local m = Instance.new("Model")
		m.Name = MODEL_NAMES[k]
		models[k] = m
	end
	local n = 0
	local r = d.boxes or {}
	for i = 1, #r, 7 do
		local kind = KINDS[r[i + 6]] or "shoulder"
		local c = Vector3.new(r[i], s.top - s.thick / 2, r[i + 1])
		local p = Instance.new("Part")
		p.Size = Vector3.new(r[i + 5], s.thick, r[i + 4])
		p.CFrame = CFrame.lookAt(c, c + Vector3.new(r[i + 2], 0, r[i + 3]))
		finish(p, s, kind, models[kind])
		n += 1
	end
	local t = d.tris or {}
	for i = 1, #t, 7 do
		local kind = KINDS[t[i + 6]] or "shoulder"
		n += triangle(models[kind], Vector2.new(t[i], t[i + 1]), Vector2.new(t[i + 2], t[i + 3]), Vector2.new(t[i + 4], t[i + 5]), s, kind)
	end
	for _, k in KINDS do
		if #models[k]:GetChildren() > 0 then
			models[k].Parent = chunk
		else
			models[k]:Destroy()
		end
	end
	chunk:PivotTo(chunk:GetPivot() + Shoulders.ORIGIN)
	return chunk, n
end

function Shoulders.Build(opts: {folder: string?, only: {string}?, batch: string?}?): string
	local options = (opts or {}) :: any
	local folderData, man = data(options.folder)
	local wanted = selection(man, options)
	local w = world()
	local folder = w:FindFirstChild(Shoulders.FOLDER)
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = Shoulders.FOLDER
		folder.Parent = w
	end
	local root = folder :: Instance
	root:SetAttribute("Attribution", man.attribution)
	local s = style(man.shoulder)
	local built, parts = 0, 0
	for _, id in man.chunks do
		if (wanted == nil or wanted[id]) and not root:FindFirstChild("Chunk_" .. id) then
			local d = chunkData(folderData, id)
			local chunk, n = Shoulders.buildChunk(id, d, s)
			if n ~= d.parts then
				warn(("shoulder chunk %s: %d parts built, data says %d"):format(id, n, d.parts))
			end
			if n > (man.maxPartsPerChunk or 600) then
				warn(("shoulder chunk %s: %d parts, over the %d cap"):format(id, n, man.maxPartsPerChunk or 600))
			end
			parts += n
			chunk.Parent = root
			built += 1
			task.wait()
		end
	end
	return ("shoulders: %d chunks built now (%d parts); %d chunks in manifest, %d built in total"):format(
		built, parts, #man.chunks, #root:GetChildren())
end

-- highest world y of a part's box corners (a WedgePart's top is its +X face here: X = up)
local function topY(p: BasePart): number
	local cf, s = p.CFrame, p.Size / 2
	local best = -math.huge
	for _, dx in {-1, 1} do
		for _, dy in {-1, 1} do
			for _, dz in {-1, 1} do
				best = math.max(best, (cf * Vector3.new(dx * s.X, dy * s.Y, dz * s.Z)).Y)
			end
		end
	end
	return best
end

-- Probe: for every built shoulder part, its top height (flush: |top - manifest top| <= 0.02, never above the road
-- top), the parts it overlaps (GetPartsInPart, exact geometry) other than road surfaces / markings / other shoulder
-- pieces (obstacle hits: buildings, props, furniture, landmarks, sidewalks, aprons...), how many touch a road surface
-- (expected: pieces tuck 0.1 under the slab edges), and what a ray straight down at its centre hits first (must be the
-- piece itself or a road surface). Wanted: parts = manifest counts, not flush 0, above road 0, obstacle hits 0,
-- sidewalk / apron overlaps 0, ray covered 0. Terrain boxes: the surface height a ray finds at each built box centre.
function Shoulders.Probe(opts: {folder: string?}?): string
	local options = (opts or {}) :: any
	local folderData, man = data(options.folder)
	local w = workspace:FindFirstChild("PattayaWorld")
	local root = w and w:FindFirstChild(Shoulders.FOLDER)
	if not root then
		return "shoulders probe: nothing built"
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = {root}
	params.RespectCanCollide = false
	local rp = RaycastParams.new()
	rp.FilterType = Enum.RaycastFilterType.Exclude
	rp.FilterDescendantsInstances = {}
	local roadTop = man.roadTop or 1.0
	local top = man.shoulder.top
	local stats = {parts = 0, notFlush = 0, aboveRoad = 0, obstacleHits = 0, sidewalkHits = 0, apronHits = 0,
		roadTouch = 0, rayCovered = 0}
	local byKind: {[string]: number} = {shoulder = 0, taper = 0, gap = 0}
	local hitNames: {[string]: number} = {}
	local examples: {string} = {}
	local dataParts = 0
	for _, chunk in root:GetChildren() do
		local id = string.sub(chunk.Name, 7)
		local ok, d = pcall(chunkData, folderData, id)
		if ok and d then
			dataParts += d.parts
		end
	end
	for _, p in root:GetDescendants() do
		if p:IsA("BasePart") then
			stats.parts += 1
			local kind = p:GetAttribute("ShoulderKind")
			if type(kind) == "string" and byKind[kind] ~= nil then
				byKind[kind] += 1
			end
			local y = topY(p)
			if math.abs(y - top) > 0.02 then
				stats.notFlush += 1
			end
			if y > roadTop + 0.005 then
				stats.aboveRoad += 1
			end
			local obstacle, road = false, false
			for _, q in workspace:GetPartsInPart(p, params) do
				if ROAD_NAMES[q.Name] then
					if q:GetAttribute("Apron") == true then
						stats.apronHits += 1
					else
						road = true
					end
				elseif q.Name == "Sidewalk" then
					stats.sidewalkHits += 1
				elseif not MARK_NAMES[q.Name] and q:GetAttribute("Shoulder") ~= true then
					obstacle = true
					hitNames[q.Name] = (hitNames[q.Name] or 0) + 1
				end
			end
			if road then
				stats.roadTouch += 1
			end
			if obstacle then
				stats.obstacleHits += 1
				if #examples < 8 then
					table.insert(examples, ("%s %s @ (%.0f, %.0f)"):format(p.Name, tostring(kind), p.Position.X, p.Position.Z))
				end
			end
			local c = p.Position
			local hit = workspace:Raycast(Vector3.new(c.X, 60, c.Z), Vector3.new(0, -70, 0), rp)
			if hit and hit.Instance ~= p and not ROAD_NAMES[hit.Instance.Name] and not hit.Instance:IsDescendantOf(root)
				and not MARK_NAMES[hit.Instance.Name] then
				stats.rayCovered += 1
			end
		end
	end
	local names = {}
	for k, v in hitNames do
		table.insert(names, ("%s %d"):format(k, v))
	end
	table.sort(names)
	-- terrain boxes: the first terrain hit at each built box centre (BuildTerrain), lowest / highest
	local terrainNote = ""
	local backup = ServerStorage:FindFirstChild(Shoulders.BACKUP)
	if backup and backup:GetAttribute("Chunks") then
		local tp = RaycastParams.new()
		tp.FilterType = Enum.RaycastFilterType.Include
		tp.FilterDescendantsInstances = {workspace.Terrain}
		local lo, hi, n, over = math.huge, -math.huge, 0, 0
		for id in string.gmatch(backup:GetAttribute("Chunks") :: string, "[^,]+") do
			local ok, d = pcall(chunkData, folderData, id)
			local r = if ok and d then d.terrain or {} else {}
			for i = 1, #r, 6 do
				local hit = workspace:Raycast(Vector3.new(r[i], 20, r[i + 1]) + Shoulders.ORIGIN, Vector3.new(0, -40, 0), tp)
				if hit then
					n += 1
					lo, hi = math.min(lo, hit.Position.Y), math.max(hi, hit.Position.Y)
					if hit.Position.Y > roadTop - 0.05 then
						over += 1
					end
				end
			end
		end
		terrainNote = ("; terrain boxes probed %d: surface y %.2f .. %.2f, at / above the road top %d (wanted 0)"):format(
			n, if n > 0 then lo else 0, if n > 0 then hi else 0, over)
	end
	local c = man.counts
	local out = ("shoulders probe: %d parts (built chunks' data %d; manifest total %d) [shoulder %d, taper %d, gap %d]; "
		.. "not flush %d; above road top %d; obstacle hits %d [%s]; sidewalk overlaps %d; apron overlaps %d; "
		.. "touching a road surface %d (expected, 0.1 tuck); ray covered %d%s%s")
		:format(stats.parts, dataParts, c.parts, byKind.shoulder, byKind.taper, byKind.gap, stats.notFlush, stats.aboveRoad,
			stats.obstacleHits, table.concat(names, ", "), stats.sidewalkHits, stats.apronHits, stats.roadTouch,
			stats.rayCovered, terrainNote, if #examples > 0 then "; e.g. " .. table.concat(examples, "; ") else "")
	print(out)
	return out
end

-- terrain ------------------------------------------------------------------------------------------------------------
-- Rows {cx, cz, ux, uz, length, width}: a box from y manifest.terrain.bottom to .top, length along (ux, uz). Before a
-- box is filled, the voxels of its axis-aligned bounds (y -8 .. 4, 4-stud voxels) are copied into a TerrainRegion in
-- ServerStorage[BACKUP] (attributes Seq, Corner); RemoveTerrain pastes them back in reverse order, which restores the
-- exact earlier voxels even where boxes overlap. Built chunk ids are kept in the backup folder's attribute Chunks.
local function boxBounds(cf: CFrame, size: Vector3): (Vector3, Vector3)
	local lo, hi = Vector3.new(math.huge, math.huge, math.huge), Vector3.new(-math.huge, -math.huge, -math.huge)
	for _, dx in {-1, 1} do
		for _, dy in {-1, 1} do
			for _, dz in {-1, 1} do
				local p = cf * Vector3.new(dx * size.X / 2, dy * size.Y / 2, dz * size.Z / 2)
				lo = Vector3.new(math.min(lo.X, p.X), math.min(lo.Y, p.Y), math.min(lo.Z, p.Z))
				hi = Vector3.new(math.max(hi.X, p.X), math.max(hi.Y, p.Y), math.max(hi.Z, p.Z))
			end
		end
	end
	return lo, hi
end

function Shoulders.terrainBox(r: {number}, i: number, man: any): (CFrame, Vector3)
	local t = man.terrain
	local y = (t.top + t.bottom) / 2
	local c = Vector3.new(r[i], y, r[i + 1]) + Shoulders.ORIGIN
	local cf = CFrame.lookAt(c, c + Vector3.new(r[i + 2], 0, r[i + 3]))
	return cf, Vector3.new(r[i + 5], t.top - t.bottom, r[i + 4])
end

function Shoulders.BuildTerrain(opts: {folder: string?, only: {string}?, batch: string?}?): string
	local options = (opts or {}) :: any
	local folderData, man = data(options.folder)
	local wanted = selection(man, options)
	local terrain = workspace.Terrain
	local mat = (Enum.Material :: any)[man.terrain.material] or Enum.Material.Ground
	local backup = ServerStorage:FindFirstChild(Shoulders.BACKUP)
	if not backup then
		backup = Instance.new("Folder")
		backup.Name = Shoulders.BACKUP
		backup.Parent = ServerStorage
	end
	local bf = backup :: Instance
	local done: {[string]: boolean} = {}
	local list = (bf:GetAttribute("Chunks") or "") :: string
	for id in string.gmatch(list, "[^,]+") do
		done[id] = true
	end
	local seq = (bf:GetAttribute("Seq") or 0) :: number
	local chunks, boxes = 0, 0
	for _, id in man.chunks do
		if (wanted == nil or wanted[id]) and not done[id] then
			local d = chunkData(folderData, id)
			local r = d.terrain or {}
			for i = 1, #r, 6 do
				local cf, size = Shoulders.terrainBox(r, i, man)
				local lo, hi = boxBounds(cf, size)
				local vmin = Vector3int16.new(math.floor(lo.X / 4) - 1, -2, math.floor(lo.Z / 4) - 1)
				local vmax = Vector3int16.new(math.floor(hi.X / 4) + 1, 0, math.floor(hi.Z / 4) + 1)
				local region = terrain:CopyRegion(Region3int16.new(vmin, vmax))
				seq += 1
				region.Name = ("B%06d"):format(seq)
				region:SetAttribute("Seq", seq)
				region:SetAttribute("Corner", Vector3.new(vmin.X, vmin.Y, vmin.Z))
				region:SetAttribute("Chunk", id)
				region.Parent = bf
				terrain:FillBlock(cf, size, mat)
				boxes += 1
			end
			list = if list == "" then id else list .. "," .. id
			bf:SetAttribute("Chunks", list)
			bf:SetAttribute("Seq", seq)
			chunks += 1
			task.wait()
		end
	end
	return ("shoulder terrain: %d chunks, %d boxes filled now (voxels backed up in ServerStorage.%s)"):format(
		chunks, boxes, Shoulders.BACKUP)
end

function Shoulders.RemoveTerrain(): string
	local bf = ServerStorage:FindFirstChild(Shoulders.BACKUP)
	if not bf then
		return "shoulder terrain: nothing to restore"
	end
	local regions = {}
	for _, r in bf:GetChildren() do
		if r:IsA("TerrainRegion") then
			table.insert(regions, r)
		end
	end
	table.sort(regions, function(a, b)
		return (a:GetAttribute("Seq") :: number) > (b:GetAttribute("Seq") :: number)
	end) -- newest first: every box's voxels go back to what they were before it was filled
	local terrain = workspace.Terrain
	for i, r in regions do
		local c = r:GetAttribute("Corner") :: Vector3
		terrain:PasteRegion(r :: TerrainRegion, Vector3int16.new(c.X, c.Y, c.Z), true)
		if i % 200 == 0 then
			task.wait()
		end
	end
	bf:Destroy()
	return ("shoulder terrain: %d boxes restored"):format(#regions)
end

function Shoulders.Remove(): string
	local t = Shoulders.RemoveTerrain()
	local w = workspace:FindFirstChild("PattayaWorld")
	local folder = w and w:FindFirstChild(Shoulders.FOLDER)
	if not folder then
		return "shoulders: nothing to remove; " .. t
	end
	local n = #folder:GetChildren()
	folder:Destroy()
	return ("shoulders: removed %d chunks; %s"):format(n, t)
end

return Shoulders
