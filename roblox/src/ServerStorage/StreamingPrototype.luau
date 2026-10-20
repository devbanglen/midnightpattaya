-- Streaming architecture PROTOTYPE (team16/streaming-arch, docs/STREAMING_ARCHITECTURE.md). Dev tool: no gameplay
-- script requires it. It copies ONE dense district of workspace.PattayaWorld into a separate, removable test area
-- (workspace.StreamingProto, +60,000 studs in X, own flat ground, no terrain) re-chunked per a layout variant, and
-- measures stream-in there in Play. The main world is only READ (parts are Clone()d, never moved or changed).
--
-- !! Build() is a PLACE CHANGE (adds ~25-35k instances to the place). The leader runs it only after the owner has
-- !! confirmed a fresh .rbxl backup. Remove() takes everything out again.
--
-- EDIT mode (command bar / execute_luau; Clone(): Studio caches the first require):
--   local P = require(game.ServerStorage.StreamingPrototype:Clone())
--   print(P.Plan("B"))            -- dry run: containers, instances per mode, largest Atomic unit; changes nothing
--   print(P.Build("B"))           -- builds variant B (an existing prototype is removed first); then save the place
--   print(P.Probe())              -- instances per folder / streaming mode / category
--   print(P.Remove())             -- undo: workspace.StreamingProto + the ReplicatedStorage helpers
-- Variants (each Build replaces the previous one; build, save, Play, measure, next):
--   A  control: the district as it is now (one Atomic Model per source chunk, junction discs loose)
--   B  roads + markings Atomic per 256-stud cell (cap 1500 instances, split into quadrants above it);
--      buildings and props Default (non-atomic: the engine streams each part on its own)
--   C  B, and the detail props (palms, lights, signs, furniture, coast props) are NOT streamed: templates in
--      ReplicatedStorage.StreamingProtoDetail, the client builds them within NearRadius (384) at a budget per frame
--   D  B, with buildings as Atomic Models per 256 cell with LevelOfDetail = StreamingMesh (imposters when streamed out)
--
-- PLAY mode. Server (command bar on Server):
--   require(game.ServerStorage.StreamingPrototype).Server.start()      -- remote for the client harness (Studio / DevTest)
-- Client (command bar on Client; Build() put a copy of this module in ReplicatedStorage):
--   local P = require(game.ReplicatedStorage.StreamingPrototype)
--   P.Client.run({mode = "teleport"})                       -- teleport into the proto centre, record 20 s
--   P.Client.run({mode = "drive", speed = 150})             -- teleport, settle 8 s, drive the proto path, record
--   P.Client.run({mode = "teleport_drive", speed = 200})    -- teleport and drive off at once (road-availability stress)
--   print(P.Client.last())                                  -- the summary again; _G.StreamProto.result = the table
-- Seat in a race car first (PattayaTestKit: TK.seatIn()). Drives use PattayaTestKit.drivePath (CFrame mode default).
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")

local P = {}

P.CONFIG = {
	centre = Vector3.new(23140, 0, 1761), -- world position of the district centre (map (3140, 1761), near Chunk_5_3)
	half = 1536, -- the district is centre +- half in X and Z (covers StreamingTargetRadius 1280 around the centre)
	offsetX = 60000, -- the prototype lies this far east of its source
	cell = 256, -- new chunk size
	cap = 1500, -- max instances per Atomic container (a cell above it is split into quadrants, down to 64 studs)
	minCell = 64,
	groundY = -2, -- ground top (the world's terrain surface is at y = -2)
	nearRadius = 384, -- variant C: client-built detail radius
	clientBudget = 200, -- variant C: instances the client builds / destroys per frame
	minRadius = 512, -- pc profile (ServerStorage/PattayaPerfProfile.luau), for the completeness check
	targetRadius = 1280,
}
local ROOT = "StreamingProto"
local DETAIL = "StreamingProtoDetail"
local CLIENT_FOLDER = "StreamingProtoClient"
local REMOTE = "StreamingProtoRemote"
local DEV_REMOTE_CLASS = "RemoteFunction"
local SOURCES = {"Chunks", "WideChunks", "ApronChunks", "FurnitureChunks", "VisSliceChunks", "CoastChunks",
	"LandmarkChunks", "Junctions", "WideJunctions", "VisMeshPalms", "Landmarks"}
local LOOSE = {Junctions = true, WideJunctions = true, VisMeshPalms = true, Landmarks = true} -- Default today
-- categories (the same rules as tools/mapgen/streaming_analysis.py): road = what the car drives / collides on
local ROAD_NAMES = {Road = true, Sidewalk = true, Junction = true, Joint = true}
local MARK_NAMES = {Centre = true, Dash = true, ZebraStripe = true}
local BUILDING_ROOTS = {VisSliceChunks = true, LandmarkChunks = true}

local function category(p: BasePart, rootName: string): string
	local n = p.Name
	if ROAD_NAMES[n] or p:GetAttribute("RoadFill") or p:GetAttribute("Apron") or p:GetAttribute("CornerFill") then
		return "road"
	end
	if MARK_NAMES[n] then
		return "marking"
	end
	if BUILDING_ROOTS[rootName] or p:GetAttribute("OsmBuilding") ~= nil or n == "Roof" then
		return "building"
	end
	local parent = p.Parent
	if parent and parent.Name == "Buildings" then
		return "building"
	end
	return "detail"
end

local function isEdit(): boolean
	return not RunService:IsRunning()
end

local function devAllowed(): boolean
	return RunService:IsStudio() or workspace:GetAttribute("DevTest") == true
end

-- ---- source collection ------------------------------------------------------------------------------------------
type Src = {part: BasePart, cat: string, root: string, chunk: string, n: number, x: number, z: number}

-- every top-level BasePart (its parent is not a BasePart) of the source folders inside the district, with its
-- category and the instances it brings (itself + its Textures / lights / GUIs)
local function collect(): {Src}
	local world = workspace:FindFirstChild("PattayaWorld")
	assert(world, "StreamingPrototype: no workspace.PattayaWorld")
	local c, h = P.CONFIG.centre, P.CONFIG.half
	local out = {}
	for _, rootName in SOURCES do
		local root = world:FindFirstChild(rootName)
		if not root then continue end
		for _, d in root:GetDescendants() do
			if d:IsA("BasePart") and not (d.Parent and d.Parent:IsA("BasePart")) then
				local pos = d.Position
				if math.abs(pos.X - c.X) <= h and math.abs(pos.Z - c.Z) <= h then
					-- the source container: the child of the root that holds it (Chunk_<id>) or the root (loose)
					local chunk = d
					while chunk.Parent and chunk.Parent ~= root do
						chunk = chunk.Parent
					end
					local chunkName = if LOOSE[rootName] or chunk == d then rootName else rootName .. "_" .. chunk.Name
					table.insert(out, {part = d, cat = category(d, rootName), root = rootName, chunk = chunkName,
						n = 1 + #d:GetDescendants(), x = pos.X, z = pos.Z})
				end
			end
		end
	end
	-- deterministic order (GetDescendants order is stable, but sort anyway so plans compare between runs)
	table.sort(out, function(a, b)
		if a.x ~= b.x then return a.x < b.x end
		if a.z ~= b.z then return a.z < b.z end
		return a.part.Name < b.part.Name
	end)
	return out
end

-- ---- plan --------------------------------------------------------------------------------------------------------
type Container = {name: string, folder: string, mode: string, layer: string, n: number, roads: number,
	items: {Src}, minx: number, maxx: number, minz: number, maxz: number}

-- cells of `size` studs anchored at (x0, z0); a cell over the cap is split into quadrants (names get _i_j appended)
local function splitCapped(items: {Src}, size: number, x0: number, z0: number, prefix: string, out: {[string]: {Src}})
	local cells: {[string]: {Src}} = {}
	local keys: {{number}} = {}
	for _, it in items do
		local i, j = math.floor((it.x - x0) / size), math.floor((it.z - z0) / size)
		local k = i .. "_" .. j
		if not cells[k] then
			cells[k] = {}
			table.insert(keys, {i, j})
		end
		table.insert(cells[k], it)
	end
	for _, ij in keys do
		local group = cells[ij[1] .. "_" .. ij[2]]
		local n = 0
		for _, it in group do n += it.n end
		local name = prefix .. "_" .. ij[1] .. "_" .. ij[2]
		if n > P.CONFIG.cap and size > P.CONFIG.minCell then
			splitCapped(group, size / 2, x0 + ij[1] * size, z0 + ij[2] * size, name, out)
		else
			out[name] = group
		end
	end
end

function P.MakePlan(variant: string, items: {Src}?): ({[string]: Container}, {Src})
	variant = string.upper(variant or "B")
	assert(variant == "A" or variant == "B" or variant == "C" or variant == "D", "variant A, B, C or D")
	local src = items or collect()
	local conts: {[string]: Container} = {}
	local function put(folder: string, name: string, mode: string, layer: string, it: Src)
		local key = folder .. "/" .. name
		local c = conts[key]
		if not c then
			c = {name = name, folder = folder, mode = mode, layer = layer, n = 0, roads = 0, items = {},
				minx = math.huge, maxx = -math.huge, minz = math.huge, maxz = -math.huge}
			conts[key] = c
		end
		c.n += it.n
		if it.cat == "road" then c.roads += it.n end
		table.insert(c.items, it)
		c.minx, c.maxx = math.min(c.minx, it.x), math.max(c.maxx, it.x)
		c.minz, c.maxz = math.min(c.minz, it.z), math.max(c.maxz, it.z)
	end
	local cfg = P.CONFIG
	local x0, z0 = cfg.centre.X - cfg.half, cfg.centre.Z - cfg.half
	if variant == "A" then
		for _, it in src do
			if LOOSE[it.root] then
				put("Loose", it.root, "Default", if it.cat == "road" then "road" else "decor", it)
			else
				put("Control", it.chunk, "Atomic", "mixed", it)
			end
		end
		return conts, src
	end
	local roads = {}
	for _, it in src do
		if it.cat == "road" or it.cat == "marking" then table.insert(roads, it) end
	end
	local cells: {[string]: {Src}} = {}
	splitCapped(roads, cfg.cell, x0, z0, "Road", cells)
	for name, group in cells do
		for _, it in group do put("Roads", name, "Atomic", "road", it) end
	end
	for _, it in src do
		if it.cat == "road" or it.cat == "marking" then continue end
		local i, j = math.floor((it.x - x0) / cfg.cell), math.floor((it.z - z0) / cfg.cell)
		if it.cat == "building" then
			put("Buildings", "Bld_" .. i .. "_" .. j, if variant == "D" then "AtomicLOD" else "Default", "decor", it)
		elseif variant == "C" then
			put("Detail", "Det_" .. i .. "_" .. j, "Client", "detail", it)
		else
			put("Props", "Prop_" .. i .. "_" .. j, "Default", "decor", it)
		end
	end
	return conts, src
end

local function planText(variant: string, conts: {[string]: Container}, src: {Src}): string
	local byMode: {[string]: number} = {}
	local byCat: {[string]: number} = {}
	local total, maxAtomic, nCont, roadIn = 0, 0, 0, 0
	for _, it in src do
		byCat[it.cat] = (byCat[it.cat] or 0) + it.n
		total += it.n
	end
	for _, c in conts do
		nCont += 1
		byMode[c.mode] = (byMode[c.mode] or 0) + c.n
		if c.mode == "Atomic" or c.mode == "AtomicLOD" then maxAtomic = math.max(maxAtomic, c.n) end
		if c.layer ~= "road" and c.layer ~= "mixed" then roadIn += c.roads end
	end
	local function fmt(t: {[string]: number}): string
		local keys = {}
		for k in t do table.insert(keys, k) end
		table.sort(keys)
		local s = {}
		for _, k in keys do table.insert(s, k .. " " .. t[k]) end
		return table.concat(s, ", ")
	end
	return ("variant %s: %d source parts, %d instances (%s) -> %d containers (%s); largest Atomic %d; road in decor %d")
		:format(variant, #src, total, fmt(byCat), nCont, fmt(byMode), maxAtomic, roadIn)
end

function P.Plan(variant: string?): string
	local v = string.upper(variant or "B")
	local conts, src = P.MakePlan(v)
	return planText(v, conts, src)
end

-- ---- build -------------------------------------------------------------------------------------------------------
local function setMode(m: Model, mode: string)
	if mode == "Atomic" or mode == "AtomicLOD" then
		m.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	elseif mode == "Persistent" then
		m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	else
		m.ModelStreamingMode = Enum.ModelStreamingMode.Default
	end
	if mode == "AtomicLOD" then
		local ok = pcall(function()
			(m :: any).LevelOfDetail = Enum.ModelLevelOfDetail.StreamingMesh
		end)
		m:SetAttribute("LODSet", ok)
	end
end

local function ground(root: Instance)
	local cfg = P.CONFIG
	local g = Instance.new("Model")
	g.Name = "Ground"
	g.ModelStreamingMode = Enum.ModelStreamingMode.Persistent -- 4-9 parts: always there, so a missing road is seen
	local span = (cfg.half + 512) * 2
	local tiles = math.ceil(span / 2048)
	local size = span / tiles
	local x0 = cfg.centre.X + cfg.offsetX - span / 2
	local z0 = cfg.centre.Z - span / 2
	for i = 0, tiles - 1 do
		for j = 0, tiles - 1 do
			local p = Instance.new("Part")
			p.Name = "ProtoGround"
			p.Anchored = true
			p.Size = Vector3.new(size, 4, size)
			p.CFrame = CFrame.new(x0 + (i + 0.5) * size, cfg.groundY - 2, z0 + (j + 0.5) * size)
			p.Color = Color3.fromRGB(86, 96, 70)
			p.Material = Enum.Material.Ground
			p.TopSurface = Enum.SurfaceType.Smooth
			p.CanTouch = false
			p.CastShadow = false
			p:SetAttribute("ProtoCat", "ground")
			p.Parent = g
		end
	end
	g.Parent = root
end

-- the drive path: the named road with the most slab length in the district, slab centres ordered along its main
-- direction, one point per 40 studs (nearest to the previous point, so a dual carriageway is not zig-zagged)
local function drivePath(src: {Src}): {Vector3}
	local byName: {[string]: {Src}} = {}
	local len: {[string]: number} = {}
	for _, it in src do
		local p = it.part
		local parent = p.Parent
		if p.Name == "Road" and not p:GetAttribute("RoadFill") and parent and parent:GetAttribute("EdgeId") then
			local nm = parent.Name
			byName[nm] = byName[nm] or {}
			table.insert(byName[nm], it)
			len[nm] = (len[nm] or 0) + p.Size.Z
		end
	end
	local best, bestLen = nil, 0
	for nm, l in len do
		if l > bestLen or (l == bestLen and best and nm < best) then best, bestLen = nm, l end
	end
	if not best then return {} end
	local items = byName[best]
	-- main direction: the two farthest-apart centres (from the first, then from that one)
	local function farthest(from: Src): Src
		local f, fd = from, -1
		for _, it in items do
			local d = (it.x - from.x) ^ 2 + (it.z - from.z) ^ 2
			if d > fd then f, fd = it, d end
		end
		return f
	end
	local a = farthest(items[1])
	local b = farthest(a)
	local dir = Vector2.new(b.x - a.x, b.z - a.z)
	if dir.Magnitude < 1 then return {} end
	dir = dir.Unit
	local buckets: {[number]: {Src}} = {}
	local maxk = 0
	for _, it in items do
		local s = (it.x - a.x) * dir.X + (it.z - a.z) * dir.Y
		local k = math.floor(s / 40)
		buckets[k] = buckets[k] or {}
		table.insert(buckets[k], it)
		maxk = math.max(maxk, k)
	end
	local out = {}
	local prev: Vector3? = nil
	for k = 0, maxk do
		local bk = buckets[k]
		if bk then
			local pick, pd = bk[1], math.huge
			for _, it in bk do
				local d = if prev then (it.x - prev.X) ^ 2 + (it.z - prev.Z) ^ 2 else 0
				if d < pd then pick, pd = it, d end
			end
			local top = pick.part.Position.Y + pick.part.Size.Y / 2
			local pt = Vector3.new(pick.x + P.CONFIG.offsetX, top, pick.z)
			table.insert(out, pt)
			prev = pt
		end
	end
	return out
end

local function packPath(pts: {Vector3}): string
	local s = table.create(#pts)
	for _, p in pts do table.insert(s, ("%.1f,%.1f,%.1f"):format(p.X, p.Y, p.Z)) end
	return table.concat(s, ";")
end

local function installClientCopy()
	local old = ReplicatedStorage:FindFirstChild("StreamingPrototype")
	if old then old:Destroy() end
	local copy = (script :: Instance):Clone()
	copy.Name = "StreamingPrototype"
	copy.Parent = ReplicatedStorage
end

function P.Remove(): string
	assert(isEdit(), "StreamingPrototype.Remove: Edit mode only")
	local n = 0
	for _, inst in {workspace:FindFirstChild(ROOT), ReplicatedStorage:FindFirstChild(DETAIL),
		ReplicatedStorage:FindFirstChild("StreamingPrototype"), ReplicatedStorage:FindFirstChild(REMOTE)} do
		if inst then
			n += 1 + #inst:GetDescendants()
			inst:Destroy()
		end
	end
	return ("StreamingPrototype removed (%d instances); the main world was not touched"):format(n)
end

function P.Build(variant: string?): string
	assert(isEdit(), "StreamingPrototype.Build: Edit mode only")
	local v = string.upper(variant or "B")
	local t0 = os.clock()
	local conts, src = P.MakePlan(v)
	assert(#src > 0, "StreamingPrototype.Build: the district is empty (is PattayaWorld built?)")
	if workspace:FindFirstChild(ROOT) or ReplicatedStorage:FindFirstChild(DETAIL) then
		P.Remove()
	end
	local cfg = P.CONFIG
	local shift = Vector3.new(cfg.offsetX, 0, 0)
	local root = Instance.new("Folder")
	root.Name = ROOT
	root:SetAttribute("Variant", v)
	root:SetAttribute("Centre", cfg.centre + shift)
	root:SetAttribute("Half", cfg.half)
	root:SetAttribute("NearRadius", cfg.nearRadius)
	root:SetAttribute("ClientBudget", cfg.clientBudget)
	root:SetAttribute("Source", "copy of PattayaWorld around " .. tostring(cfg.centre) .. " (team16/streaming-arch)")
	ground(root)
	local detailRoot: Instance? = nil
	if v == "C" then
		detailRoot = Instance.new("Folder");
		(detailRoot :: Instance).Name = DETAIL
	end
	-- deterministic container order
	local keys = {}
	for k in conts do table.insert(keys, k) end
	table.sort(keys)
	local folders: {[string]: Instance} = {}
	local index = {}
	local cloned, failed = 0, 0
	for _, key in keys do
		local c = conts[key]
		local holder: Instance
		if c.mode == "Client" then
			holder = Instance.new("Folder")
			holder.Parent = detailRoot
		else
			local f = folders[c.folder]
			if not f then
				f = Instance.new("Folder")
				f.Name = c.folder
				f.Parent = root
				folders[c.folder] = f
			end
			local m = Instance.new("Model")
			setMode(m, c.mode)
			m.Parent = f
			holder = m
		end
		holder.Name = c.name
		holder:SetAttribute("Mode", c.mode)
		holder:SetAttribute("Layer", c.layer)
		holder:SetAttribute("Expect", c.n + 1)
		for _, it in c.items do
			local ok, copy = pcall(function() return it.part:Clone() end)
			if ok and copy then
				copy:PivotTo(copy:GetPivot() + shift)
				copy:SetAttribute("ProtoCat", it.cat)
				copy:SetAttribute("ProtoSrc", it.chunk)
				copy.Parent = holder
				cloned += 1
				if cloned % 3000 == 0 then task.wait() end
			else
				failed += 1 -- Archivable = false
			end
		end
		table.insert(index, {c.folder .. "/" .. c.name, c.mode, c.n + 1, math.floor(c.minx + cfg.offsetX),
			math.floor(c.maxx + cfg.offsetX), math.floor(c.minz), math.floor(c.maxz)})
	end
	root:SetAttribute("Index", HttpService:JSONEncode(index))
	root.Parent = workspace
	if detailRoot then (detailRoot :: Instance).Parent = ReplicatedStorage end
	-- the drive path, kept only where a downward ray hits a proto road part (built now, so this is the baseline)
	local raw = drivePath(src)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {root}
	local path = {}
	for _, p in raw do
		local hit = workspace:Raycast(p + Vector3.new(0, 40, 0), Vector3.new(0, -80, 0), params)
		if hit and hit.Instance:GetAttribute("ProtoCat") == "road" then table.insert(path, p) end
	end
	root:SetAttribute("ProtoPath", packPath(path))
	root:SetAttribute("ProtoPathDropped", #raw - #path)
	installClientCopy()
	return planText(v, conts, src) .. ("\nbuilt %d parts (%d not clonable) in %.1f s; drive path %d points (%d dropped: no road under them);"
		.. " workspace.%s%s; SAVE the place, then Play"):format(cloned, failed, os.clock() - t0, #path, #raw - #path, ROOT,
		if v == "C" then " + ReplicatedStorage." .. DETAIL else "")
end

-- ---- probe -------------------------------------------------------------------------------------------------------
function P.Probe(): string
	local root = workspace:FindFirstChild(ROOT)
	if not root then return "no workspace." .. ROOT end
	local lines = {("variant %s (%s)"):format(tostring(root:GetAttribute("Variant")), if isEdit() then "edit" else "play")}
	local byMode: {[string]: {number}} = {}
	local byCat: {[string]: number} = {}
	for _, f in root:GetChildren() do
		local n, models, maxM = 1 + #f:GetDescendants(), 0, 0
		for _, m in f:GetChildren() do
			if m:IsA("Model") then
				models += 1
				local k = 1 + #m:GetDescendants()
				maxM = math.max(maxM, k)
				local mode = m:GetAttribute("Mode") or m.ModelStreamingMode.Name
				byMode[mode] = byMode[mode] or {0, 0}
				byMode[mode][1] += 1
				byMode[mode][2] += k
			end
		end
		table.insert(lines, ("  %-10s %7d instances, %4d models, largest %d"):format(f.Name, n, models, maxM))
	end
	for _, d in root:GetDescendants() do
		local c = d:GetAttribute("ProtoCat")
		if c then byCat[c] = (byCat[c] or 0) + 1 end
	end
	for mode, v in byMode do
		table.insert(lines, ("  mode %-10s %4d models %7d instances"):format(mode, v[1], v[2]))
	end
	for c, n in byCat do
		table.insert(lines, ("  cat  %-10s %7d parts"):format(c, n))
	end
	local det = ReplicatedStorage:FindFirstChild(DETAIL)
	if det then
		table.insert(lines, ("  ReplicatedStorage.%s: %d cells, %d instances (client near layer templates)"):format(DETAIL,
			#det:GetChildren(), #det:GetDescendants()))
	end
	return table.concat(lines, "\n")
end

-- ---- server (Play) -----------------------------------------------------------------------------------------------
P.Server = {}

function P.Server.start(): string
	assert(RunService:IsServer() and RunService:IsRunning(), "Server.start: Play mode, server side")
	assert(devAllowed(), "StreamingPrototype is dev only (Studio or workspace DevTest = true)")
	-- dev-only remote, directly in ReplicatedStorage (like PattayaTestKitRemote) and deliberately NOT in
	-- PattayaRemotes, so the game's remote contract (tools/qa/tests/test_remotes_contract.py) is not touched
	local rf = ReplicatedStorage:FindFirstChild(REMOTE) or Instance.new(DEV_REMOTE_CLASS)
	rf.Name = REMOTE
	rf.Parent = ReplicatedStorage
	;(rf :: RemoteFunction).OnServerInvoke = function(plr: Player, action, a, b)
		if not RunService:IsStudio() and plr.UserId ~= game.CreatorId then
			return false, "not allowed"
		end
		if action == "teleport" then
			-- a = Vector3 goal, b = prestream (true: PattayaTestKitServer.teleport, which streams around the goal)
			local ok, kit = pcall(function()
				return require(game:GetService("ServerStorage"):WaitForChild("PattayaTestKitServer", 2) :: any)
			end)
			if b ~= false and ok and kit and kit.teleport then
				return kit.teleport(plr, a, {hop = 1e6, force = true})
			end
			-- no pre-stream: move the car directly (anchored for 0.3 s like the kit)
			local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
			local seat = hum and hum.SeatPart
			local car = seat and seat.Parent
			if not (car and car:IsA("Model") and car.PrimaryPart) then return false, "not in a car" end
			local chassis = car.PrimaryPart :: BasePart
			local offset = chassis.CFrame:ToObjectSpace(car:GetPivot())
			chassis.Anchored = true
			car:PivotTo(CFrame.lookAt(a + Vector3.new(0, 2.8, 0), a + Vector3.new(0, 2.8, 0) + Vector3.xAxis) * offset)
			task.wait(0.3)
			chassis.Anchored = false
			pcall(function() chassis:SetNetworkOwner(plr) end)
			return true, "moved (no pre-stream)"
		end
		return false, "unknown action"
	end
	return "StreamingPrototype server remote ready"
end

-- ---- client (Play) -----------------------------------------------------------------------------------------------
P.Client = {}
local last: any = nil

local MEM_TAGS = {"Instances", "PhysicsParts", "PhysicsCollision", "GraphicsParts", "GraphicsMeshParts",
	"GraphicsTexture", "GraphicsSolidModels", "Gui", "LuaHeap", "Script"}

local function memory(): {[string]: number}
	local Stats = game:GetService("Stats")
	local out = {total = Stats:GetTotalMemoryUsageMb()}
	for _, t in MEM_TAGS do
		pcall(function()
			out[t] = (Stats :: any):GetMemoryUsageMbForTag((Enum.DeveloperMemoryTag :: any)[t])
		end)
	end
	return out
end

local function percentile(sorted: {number}, p: number): number
	if #sorted == 0 then return 0 end
	return sorted[math.clamp(math.ceil(p / 100 * #sorted), 1, #sorted)]
end

local function unpackPath(s: string?): {Vector3}
	local out = {}
	for item in string.gmatch(s or "", "[^;]+") do
		local x, y, z = string.match(item, "([-%d%.]+),([-%d%.]+),([-%d%.]+)")
		if x then table.insert(out, Vector3.new(tonumber(x) :: number, tonumber(y) :: number, tonumber(z) :: number)) end
	end
	return out
end

-- arc-length helpers for the path-ahead road checks
local function cumulative(pts: {Vector3}): {number}
	local cum = {0}
	for i = 2, #pts do
		cum[i] = cum[i - 1] + (Vector3.new(pts[i].X, 0, pts[i].Z) - Vector3.new(pts[i - 1].X, 0, pts[i - 1].Z)).Magnitude
	end
	return cum
end

local function pointAt(pts: {Vector3}, cum: {number}, s: number): Vector3
	if s <= 0 then return pts[1] end
	for i = 2, #pts do
		if cum[i] >= s then
			local t = (s - cum[i - 1]) / math.max(cum[i] - cum[i - 1], 1e-3)
			return pts[i - 1]:Lerp(pts[i], t)
		end
	end
	return pts[#pts]
end

local function arcOf(pts: {Vector3}, cum: {number}, pos: Vector3): number
	local best, bs = math.huge, 0
	for i = 2, #pts do
		local a, b = pts[i - 1], pts[i]
		local ab = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
		local L = ab.Magnitude
		if L > 0 then
			local t = math.clamp(Vector3.new(pos.X - a.X, 0, pos.Z - a.Z):Dot(ab) / (L * L), 0, 1)
			local q = Vector3.new(a.X + ab.X * t, 0, a.Z + ab.Z * t)
			local d = (Vector3.new(pos.X, 0, pos.Z) - q).Magnitude
			if d < best then best, bs = d, cum[i - 1] + L * t end
		end
	end
	return bs
end

type Tpl = {tpl: BasePart, pos: Vector3, n: number, live: Instance?}

-- variant C: the client builds the detail templates within NearRadius of `focus()`, CLIENT_BUDGET instances per frame
local function startNearLayer(focus: () -> Vector3?): (() -> number, () -> ())
	local det = ReplicatedStorage:WaitForChild(DETAIL, 10)
	if not det then return function() return 0 end, function() end end
	local root = workspace:FindFirstChild(ROOT)
	local R = (root and root:GetAttribute("NearRadius")) or P.CONFIG.nearRadius
	local budget = (root and root:GetAttribute("ClientBudget")) or P.CONFIG.clientBudget
	local folder = Instance.new("Folder")
	folder.Name = CLIENT_FOLDER
	folder.Parent = workspace
	local all: {Tpl} = {}
	for _, cell in det:GetChildren() do
		for _, p in cell:GetChildren() do
			if p:IsA("BasePart") then
				table.insert(all, {tpl = p, pos = p.Position, n = 1 + #p:GetDescendants(), live = nil})
			end
		end
	end
	local made = 0
	local frameMade = 0
	local conn = RunService.Heartbeat:Connect(function()
		frameMade = 0
		local f = focus()
		if not f then return end
		local fx, fz = f.X, f.Z
		local spent = 0
		-- nearest first would need a sort per frame; the list is scanned with a cursor instead (budget-bound)
		for _, t in all do
			if spent >= budget then break end
			local d = math.sqrt((t.pos.X - fx) ^ 2 + (t.pos.Z - fz) ^ 2)
			if not t.live and d <= R then
				local c = t.tpl:Clone()
				c.Parent = folder
				t.live = c
				spent += t.n
				made += t.n
			elseif t.live and d > R + 64 then
				(t.live :: Instance):Destroy()
				t.live = nil
				spent += t.n
			end
		end
		frameMade = spent
	end)
	return function() return frameMade end, function()
		conn:Disconnect()
		folder:Destroy()
	end
end

function P.Client.run(opts: any?): string
	assert(RunService:IsClient(), "Client.run: Play mode, client side")
	local o = opts or {}
	local mode = o.mode or "teleport"
	local speed = o.speed or 150
	local seconds = o.seconds or 20
	local root = workspace:WaitForChild(ROOT, 10)
	assert(root, "no workspace." .. ROOT .. " (Build() it in Edit mode first)")
	local okTK, TK = pcall(function() return require(ReplicatedStorage:WaitForChild("PattayaTestKit", 5) :: any) end)
	assert(okTK and TK, "needs ReplicatedStorage.PattayaTestKit")
	local chassis = TK.car()
	assert(chassis, "seat in a race car first (TK.seatIn())")
	local remote = ReplicatedStorage:WaitForChild(REMOTE, 5) :: RemoteFunction?
	assert(remote, "run require(game.ServerStorage.StreamingPrototype).Server.start() on the server first")
	local path = unpackPath(root:GetAttribute("ProtoPath"))
	assert(#path >= 2, "the prototype has no drive path")
	local cum = cumulative(path)
	local variant = root:GetAttribute("Variant")
	local cfg = P.CONFIG
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {root}
	local function roadAt(p: Vector3): boolean
		local hit = workspace:Raycast(Vector3.new(p.X, p.Y + 30, p.Z), Vector3.new(0, -60, 0), params)
		return hit ~= nil and hit.Instance:GetAttribute("ProtoCat") == "road"
	end
	local function carPos(): Vector3?
		local c = TK.car()
		return c and c.Position
	end
	local start = path[1]
	local nearCount, stopNear = function() return 0 end, function() end
	if variant == "C" then
		nearCount, stopNear = startNearLayer(carPos)
	end
	local frames: {number} = {}
	local added: {number} = {}
	local clientAdded: {number} = {}
	local missUnder, missAhead5, missAhead10 = 0, 0, 0
	local firstRoad: number? = nil
	local addCount = 0
	local addConn = root.DescendantAdded:Connect(function() addCount += 1 end)
	local mem0 = memory()
	local recording = false
	local t0 = 0
	local drive: any = nil
	local frameConn = RunService.RenderStepped:Connect(function(dt)
		if not recording then
			addCount = 0
			return
		end
		table.insert(frames, dt * 1000)
		table.insert(added, addCount)
		table.insert(clientAdded, nearCount())
		addCount = 0
		local pos = carPos()
		if pos then
			if roadAt(pos) then
				firstRoad = firstRoad or (os.clock() - t0)
			else
				missUnder += 1
			end
			if mode ~= "teleport" then
				local s = arcOf(path, cum, pos)
				if not roadAt(pointAt(path, cum, s + speed * 0.5)) then missAhead5 += 1 end
				if not roadAt(pointAt(path, cum, s + speed * 1.0)) then missAhead10 += 1 end
			end
		end
	end)
	local function teleportIn()
		t0 = os.clock()
		recording = true
		local ok, msg = remote:InvokeServer("teleport", start, o.prestream ~= false)
		return ok, msg
	end
	local tpOk, tpMsg
	if mode == "drive" then
		tpOk, tpMsg = remote:InvokeServer("teleport", start, o.prestream ~= false)
		task.wait(o.settle or 8)
		t0 = os.clock()
		missUnder = 0
		recording = true
		drive = TK.drivePath(path, {speed = speed, physics = o.physics == true, name = "streamproto", holdEnd = 0.5})
	elseif mode == "teleport_drive" then
		tpOk, tpMsg = teleportIn()
		drive = TK.drivePath(path, {speed = speed, physics = o.physics == true, name = "streamproto", holdEnd = 0.5})
	else
		tpOk, tpMsg = teleportIn()
	end
	local stopAt = os.clock() + seconds
	while os.clock() < stopAt do
		if drive and drive.done and os.clock() - t0 > 3 then break end
		task.wait(0.1)
	end
	recording = false
	frameConn:Disconnect()
	addConn:Disconnect()
	if drive and not drive.done then drive:stop("measure end") end
	-- completeness inside MinRadius / TargetRadius of the car (containers by their box, expected vs present)
	local pos = carPos() or start
	local okIdx, index = pcall(function() return HttpService:JSONDecode(root:GetAttribute("Index")) end)
	local present: {[string]: number} = {}
	for _, f in root:GetChildren() do
		for _, m in f:GetChildren() do present[f.Name .. "/" .. m.Name] = 1 + #m:GetDescendants() end
	end
	local function complete(r: number): (number, number)
		local exp, got = 0, 0
		if not okIdx then return 0, 0 end
		for _, row in index do
			if row[2] ~= "Client" then
				local dx = math.max(row[4] - pos.X, 0, pos.X - row[5])
				local dz = math.max(row[6] - pos.Z, 0, pos.Z - row[7])
				if math.sqrt(dx * dx + dz * dz) <= r then
					exp += row[3]
					got += math.min(present[row[1]] or 0, row[3])
				end
			end
		end
		return got, exp
	end
	local gMin, eMin = complete(cfg.minRadius)
	local gT, eT = complete(cfg.targetRadius)
	local mem1 = memory()
	stopNear()
	local sorted = table.clone(frames)
	table.sort(sorted)
	local over50, over100, maxAdd, sumAdd, maxClient = 0, 0, 0, 0, 0
	for i, ms in frames do
		if ms > 50 then over50 += 1 end
		if ms > 100 then over100 += 1 end
		maxAdd = math.max(maxAdd, added[i])
		sumAdd += added[i]
		maxClient = math.max(maxClient, clientAdded[i])
	end
	local res = {
		variant = variant, mode = mode, speed = speed, prestream = o.prestream ~= false, teleport = tpMsg, ok = tpOk,
		frames = #frames, worstMs = sorted[#sorted] or 0, p99Ms = percentile(sorted, 99), p95Ms = percentile(sorted, 95),
		medianMs = percentile(sorted, 50), over50 = over50, over100 = over100, maxAddedPerFrame = maxAdd,
		totalAdded = sumAdd, maxClientPerFrame = maxClient, roadMissingUnderCar = missUnder,
		roadMissingAhead05s = missAhead5, roadMissingAhead1s = missAhead10, firstRoadUnderCarS = firstRoad,
		completeMin = if eMin > 0 then gMin / eMin else nil, completeTarget = if eT > 0 then gT / eT else nil,
		memBefore = mem0, memAfter = mem1, drive = drive and drive.reason,
	}
	local memDelta = {}
	for k, v in mem1 do
		if mem0[k] then table.insert(memDelta, ("%s %+.1f"):format(k, v - mem0[k])) end
	end
	table.sort(memDelta)
	res.summary = ("[StreamProto] variant %s %s v=%.0f prestream=%s | frames %d worst %.0f ms p99 %.0f p95 %.0f median %.0f"
		.. " | >50ms %d >100ms %d | added max/frame %d total %d (client layer max/frame %d) | road missing under car %d,"
		.. " ahead 0.5s %d, 1s %d, first road %.2fs | complete min %.0f%% target %.0f%% | mem %.0f MB (%s) | %s")
		:format(tostring(variant), mode, speed, tostring(res.prestream), #frames, res.worstMs,
			res.p99Ms, res.p95Ms, res.medianMs, over50, over100, maxAdd, sumAdd, maxClient, missUnder, missAhead5,
			missAhead10, firstRoad or -1, (res.completeMin or 0) * 100, (res.completeTarget or 0) * 100, mem1.total,
			table.concat(memDelta, ", "), tostring(tpMsg))
	last = res
	_G.StreamProto = _G.StreamProto or {}
	_G.StreamProto.result = res
	_G.StreamProto.runs = _G.StreamProto.runs or {}
	table.insert(_G.StreamProto.runs, res.summary)
	print(res.summary)
	return res.summary
end

function P.Client.last(): string
	return if last then last.summary else "no run yet"
end

return P
