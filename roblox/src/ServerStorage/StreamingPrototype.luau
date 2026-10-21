-- Streaming architecture PROTOTYPE (team16/streaming-arch, docs/STREAMING_ARCHITECTURE.md). Dev tool: no gameplay
-- script requires it. It copies ONE dense district of workspace.PattayaWorld into a separate, removable test area
-- (workspace.StreamingProto, +60,000 studs in X, own flat ground, no terrain) re-chunked per a layout variant, and
-- measures stream-in there in Play. The main world is only READ (parts are Clone()d, never moved or changed).
--
-- !! Build() is a PLACE CHANGE (adds ~23k instances + two small boot scripts). The leader runs it only after the owner
-- !! has confirmed a fresh .rbxl backup. Remove() takes everything out again; Leftovers() lists anything that is left.
--
-- EDIT mode (command bar / execute_luau; Clone(): Studio caches the first require):
--   local P = require(game.ServerStorage.StreamingPrototype:Clone())
--   print(P.Plan("B"))            -- dry run: containers, instances per mode, largest Atomic unit; changes nothing
--   print(P.ParityText())         -- A and B copy the same source parts (per source folder); P.Parity() = the table
--   print(P.Build("B"))           -- builds variant B (an existing prototype is removed first); then save the place
--   print(P.SetBoot("cold"))      -- what the boot scripts do in the next Play: "cold" | "teleport" | "off"
--   print(P.Probe())              -- instances per folder / streaming mode / category
--   print(P.Remove())             -- undo: workspace.StreamingProto, ReplicatedStorage helpers, boot scripts
--   print(P.Leftovers())          -- "" when nothing of the prototype is left in the place
-- Variants (each Build replaces the previous one; build, save, Play, measure, next). Approved now: A and B.
--   A  control: the district as it is now (one Atomic Model per source chunk, junction discs / palms loose)
--   B  road layer (roads, sidewalks, discs, aprons, corner fills, SHOULDERS, markings) Atomic per 256-stud cell
--      (cap 1500 instances, split into quadrants above it); buildings and props Default (non-atomic)
--   C  (later) B, and detail props built by the client within NearRadius from ReplicatedStorage templates
--   D  (later) B, buildings Atomic per 256 cell with LevelOfDetail = StreamingMesh
-- Every variant copies the same source parts (P.Parity()); only grouping and streaming mode differ.
--
-- PLAY mode: Build() also installs ServerScriptService.StreamingProtoBoot and StarterPlayerScripts.
-- StreamingProtoBootClient. They do nothing outside Studio or when workspace.StreamingProto.Boot is "off". With
-- Boot = "cold" or "teleport" each fresh Play runs one automatic sequence for the first player:
--   cold      the server seats the player in the nearest race car and moves it to the proto start right after join,
--             without RequestStreamAroundAsync; the client records the first ColdSeconds (30) s after join, then
--             drives the proto path at 100, 150 and 200 studs/s (each drive recorded)
--   teleport  the server seats the player in the nearest race car where it spawned (city); after 15 s the car is
--             teleported into the proto (PattayaTestKitServer.teleport, pre-stream like the game), 20 s recorded,
--             then the same three drives
-- Each recorded window prints one "[StreamProto]" line; _G.StreamProto.runs holds them, P.Client.report() joins them.
-- By hand (Boot = "off"): server require(game.ServerStorage.StreamingPrototype).Server.start(); client
--   require(game.ReplicatedStorage.StreamingPrototype).Client.run({mode = "teleport" | "drive", speed = 150})
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
local BOOT_SERVER = "StreamingProtoBoot"
local BOOT_CLIENT = "StreamingProtoBootClient"
local SOURCES = {"Chunks", "WideChunks", "ApronChunks", "FurnitureChunks", "VisSliceChunks", "CoastChunks",
	"LandmarkChunks", "ShoulderChunks", "Junctions", "WideJunctions", "VisMeshPalms", "Landmarks"}
local LOOSE = {Junctions = true, WideJunctions = true, VisMeshPalms = true, Landmarks = true} -- Default today
-- categories (the same rules as tools/mapgen/streaming_analysis.py): road = what the car drives / collides on
local ROAD_NAMES = {Road = true, Sidewalk = true, Junction = true, Joint = true}
local MARK_NAMES = {Centre = true, Dash = true, ZebraStripe = true}
local BUILDING_ROOTS = {VisSliceChunks = true, LandmarkChunks = true}
local ROAD_ROOTS = {ShoulderChunks = true, ApronChunks = true} -- every part of these is road collision

local function category(p: BasePart, rootName: string): string
	local n = p.Name
	if ROAD_ROOTS[rootName] or ROAD_NAMES[n] or p:GetAttribute("Shoulder") or p:GetAttribute("RoadFill") or p:GetAttribute("Apron") or p:GetAttribute("CornerFill") then
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
type Src = {part: BasePart, cat: string, root: string, chunk: string, n: number, x: number, z: number, collide: boolean?}

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
						n = 1 + #d:GetDescendants(), x = pos.X, z = pos.Z, collide = d.CanCollide or d.CanTouch})
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
		elseif variant == "C" and not it.collide then
			-- C: only NON-colliding detail (fronds, lamp heads, arms, boards, canopies, neon signs, ...) is built by
			-- the client. Every part with CanCollide / CanTouch (poles, trunks, posts, shelters, hut walls, ...)
			-- stays engine-streamed in Props, so the server, other players' cars and traffic see the same collision
			-- as in A and B (no client-only collision anywhere; P.CollisionAudit checks it)
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

-- the drive path comes from the road graph (ServerStorage.PattayaRoute: nearestNode, dijkstra, polylineOf, toWorld),
-- not from slab centres (those crossed ground and buildings: leader A/B run 2026-10-21, 58% of samples off road).
-- PickRoute chooses the LONGEST graph route that lies fully inside the district and whose samples every `spacing`
-- (4) studs are 100% on copied road parts; if no checked route reaches 100%, the best one is returned only when it
-- reaches `need` (0.99), otherwise nil + the reason (Build then fails). Pure logic: `Route` and `onRoad` are passed in
-- (unit-tested with a mock graph in the luau CLI).
--   box = {minx, maxx, minz, maxz} map-local; onRoad(p: Vector3) -> boolean, p in PROTO world coordinates
--   opts: shift (Vector3 added to Route.toWorld, default +offsetX), spacing 4, margin 40, need 0.99, seeds 12,
--         maxRoutes 300 (polylines measured), maxCheck 60 (routes sampled), minLen 800, from / to (map-local Vector2:
--         a fixed route between the nodes nearest to them, e.g. the leader's (1800, 1700) -> (4500, 1800))
local function polyLen(pts: {any}): number
	local L = 0
	for i = 2, #pts do
		L += math.sqrt((pts[i].X - pts[i - 1].X) ^ 2 + (pts[i].Y - pts[i - 1].Y) ^ 2)
	end
	return L
end

local function samplePoly(pts: {any}, spacing: number): {{number}}
	local out = {{pts[1].X, pts[1].Y}}
	local carry = 0
	for i = 2, #pts do
		local ax, az, bx, bz = pts[i - 1].X, pts[i - 1].Y, pts[i].X, pts[i].Y
		local L = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
		local s = spacing - carry
		while s <= L do
			local t = s / L
			table.insert(out, {ax + (bx - ax) * t, az + (bz - az) * t})
			s += spacing
		end
		carry = L - (s - spacing)
	end
	local last = pts[#pts]
	table.insert(out, {last.X, last.Y})
	return out
end

function P.RouteCoverage(Route: any, onRoad: (Vector3) -> boolean, pts: {any}, shift: Vector3, spacing: number?): (number, number)
	local samples = samplePoly(pts, spacing or 4)
	local ok = 0
	for _, s in samples do
		local w = Route.toWorld({X = s[1], Y = s[2]}, 1)
		if onRoad(Vector3.new(w.X + shift.X, w.Y + shift.Y, w.Z + shift.Z)) then ok += 1 end
	end
	return ok / #samples, #samples
end

function P.PickRoute(Route: any, onRoad: (Vector3) -> boolean, box: {number}, opts: any?): (any?, string)
	local o = opts or {}
	local shift: Vector3 = o.shift or Vector3.new(P.CONFIG.offsetX, 0, 0)
	local spacing, margin, need = o.spacing or 4, o.margin or 40, o.need or 0.99
	local function inside(p: any): boolean
		return p.X >= box[1] + margin and p.X <= box[2] - margin and p.Y >= box[3] + margin and p.Y <= box[4] - margin
	end
	local function allInside(pts: {any}): boolean
		for _, p in pts do
			if not inside(p) then return false end
		end
		return true
	end
	local routes = {} -- {pts, len}
	if o.from and o.to then
		local s = Route.nearestNode(o.from, 400)
		local t = Route.nearestNode(o.to, 400)
		if not (s and t) then return nil, "no graph node near from / to" end
		local _, prev = Route.dijkstra(s)
		local pts = Route.polylineOf(prev, s, t)
		table.insert(routes, {pts = pts, len = polyLen(pts)})
	else
		local cand = {}
		for i = 1, (Route.baseNodes or #Route.nodes) do
			local n = Route.nodes[i]
			if n and inside(n) then table.insert(cand, i) end
		end
		if #cand < 2 then return nil, "fewer than 2 graph nodes inside the district" end
		-- seeds spread over the district (farthest-point sampling, deterministic)
		local seeds = {cand[1]}
		local dmin = {}
		for _, c in cand do dmin[c] = math.huge end
		while #seeds < math.min(o.seeds or 12, #cand) do
			local last = Route.nodes[seeds[#seeds]]
			local best, bd = nil, -1
			for _, c in cand do
				local n = Route.nodes[c]
				dmin[c] = math.min(dmin[c], (n.X - last.X) ^ 2 + (n.Y - last.Y) ^ 2)
				if dmin[c] > bd then best, bd = c, dmin[c] end
			end
			if not best or bd <= 0 then break end
			table.insert(seeds, best)
		end
		-- every (seed, node) pair ranked by graph cost; the maxRoutes best become polylines
		local pairsList = {}
		local prevOf = {}
		for _, s in seeds do
			local dist, prev = Route.dijkstra(s)
			prevOf[s] = prev
			for _, t in cand do
				if t ~= s and dist[t] then table.insert(pairsList, {s, t, dist[t]}) end
			end
		end
		table.sort(pairsList, function(a, b)
			if a[3] ~= b[3] then return a[3] > b[3] end
			if a[1] ~= b[1] then return a[1] < b[1] end
			return a[2] < b[2]
		end)
		for k = 1, math.min(#pairsList, o.maxRoutes or 300) do
			local pr = pairsList[k]
			local pts = Route.polylineOf(prevOf[pr[1]], pr[1], pr[2])
			if #pts >= 2 and allInside(pts) then
				local len = polyLen(pts)
				if len >= (o.minLen or 800) then table.insert(routes, {pts = pts, len = len}) end
			end
		end
	end
	if #routes == 0 then return nil, "no graph route fully inside the district" end
	table.sort(routes, function(a, b) return a.len > b.len end)
	local best, bestFrac = nil, -1
	for k = 1, math.min(#routes, o.maxCheck or 60) do
		local r = routes[k]
		local frac, n = P.RouteCoverage(Route, onRoad, r.pts, shift, spacing)
		r.frac, r.samples = frac, n
		if frac >= 1 then
			return r, ("route %.0f studs, %d samples, 100%% on road"):format(r.len, n)
		end
		if frac > bestFrac then best, bestFrac = r, frac end
	end
	if best and bestFrac >= need then
		return best, ("route %.0f studs, %d samples, %.1f%% on road (no 100%% route among the checked)"):format(best.len,
			best.samples, bestFrac * 100)
	end
	return nil, ("best route only %.1f%% on road (< %.0f%%)"):format(math.max(bestFrac, 0) * 100, need * 100)
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

-- everything the prototype ever puts into the place (Build, Server.start, the client near layer)
local function ownInstances(): {Instance}
	local out = {}
	local function add(parent: Instance?, name: string)
		local x = parent and parent:FindFirstChild(name)
		if x then table.insert(out, x) end
	end
	local SSS = game:GetService("ServerScriptService")
	local SP = game:GetService("StarterPlayer")
	local SPS = SP and SP:FindFirstChild("StarterPlayerScripts")
	add(workspace, ROOT)
	add(workspace, CLIENT_FOLDER)
	add(ReplicatedStorage, DETAIL)
	add(ReplicatedStorage, "StreamingPrototype")
	add(ReplicatedStorage, REMOTE)
	add(SSS, BOOT_SERVER)
	add(SPS, BOOT_CLIENT)
	return out
end

local OWN_ATTR_PREFIX = "StreamProto" -- the prototype sets no attributes outside its own instances; checked anyway

-- one line per prototype instance or attribute still in the place; "" = clean
function P.Leftovers(): string
	local rows = {}
	for _, inst in ownInstances() do
		table.insert(rows, inst:GetFullName())
	end
	for _, svc in {workspace, ReplicatedStorage} do
		for k in svc:GetAttributes() do
			if string.sub(k, 1, #OWN_ATTR_PREFIX) == OWN_ATTR_PREFIX then
				table.insert(rows, svc.Name .. "@" .. k)
			end
		end
	end
	table.sort(rows)
	return table.concat(rows, "\n")
end

function P.Remove(): string
	assert(isEdit(), "StreamingPrototype.Remove: Edit mode only")
	local n = 0
	for _, inst in ownInstances() do
		n += 1 + #inst:GetDescendants()
		inst:Destroy()
	end
	for _, svc in {workspace, ReplicatedStorage} do
		for k in svc:GetAttributes() do
			if string.sub(k, 1, #OWN_ATTR_PREFIX) == OWN_ATTR_PREFIX then svc:SetAttribute(k, nil) end
		end
	end
	local left = P.Leftovers()
	return ("StreamingPrototype removed (%d instances); the main world was not touched; leftovers: %s"):format(n,
		if left == "" then "none" else left)
end

-- A and B must copy exactly the same source parts: per source folder {parts, instances} of each plan
function P.Parity(items: {Src}?): {[string]: {[string]: {number}}}
	local src = items or collect()
	local out = {}
	for _, v in {"A", "B", "C", "D"} do
		local conts = P.MakePlan(v, src)
		local t: {[string]: {number}} = {}
		for _, c in conts do
			for _, it in c.items do
				local r = t[it.root] or {0, 0}
				r[1] += 1
				r[2] += it.n
				t[it.root] = r
			end
		end
		out[v] = t
	end
	return out
end

function P.ParityText(items: {Src}?): string
	local par = P.Parity(items)
	local V = {"A", "B", "C", "D"}
	local seen, roots = {}, {}
	for _, v in V do
		for r in par[v] do
			if not seen[r] then seen[r] = true; table.insert(roots, r) end
		end
	end
	table.sort(roots)
	local head = ("%-16s"):format("source")
	for _, v in V do head ..= ("  %s parts %8s"):format(v, v .. " inst") end
	local lines = {head .. "  same"}
	local ok = true
	local tot = {A = {0, 0}, B = {0, 0}, C = {0, 0}, D = {0, 0}}
	for _, r in roots do
		local line = ("%-16s"):format(r)
		local a = par.A[r] or {0, 0}
		local same = true
		for _, v in V do
			local x = par[v][r] or {0, 0}
			same = same and x[1] == a[1] and x[2] == a[2]
			tot[v][1] += x[1]
			tot[v][2] += x[2]
			line ..= ("  %7d %8d"):format(x[1], x[2])
		end
		ok = ok and same
		table.insert(lines, line .. "  " .. (if same then "yes" else "NO"))
	end
	local line = ("%-16s"):format("total")
	for _, v in V do
		line ..= ("  %7d %8d"):format(tot[v][1], tot[v][2])
		ok = ok and tot[v][2] == tot.A[2] and tot[v][1] == tot.A[1]
	end
	table.insert(lines, line .. "  " .. (if ok then "PARITY OK" else "PARITY FAILED"))
	return table.concat(lines, "\n")
end

-- what the boot scripts do in the next Play (Edit mode): "cold", "teleport" or "off"
function P.SetBoot(kind: string, coldSeconds: number?, driveModes: string?): string
	assert(isEdit(), "SetBoot: Edit mode")
	assert(kind == "cold" or kind == "teleport" or kind == "off", "SetBoot: cold | teleport | off")
	local root = workspace:FindFirstChild(ROOT)
	assert(root, "SetBoot: Build() first")
	root:SetAttribute("Boot", kind)
	root:SetAttribute("ColdSeconds", coldSeconds or 30)
	if driveModes then
		assert(driveModes == "both" or driveModes == "cframe" or driveModes == "physics", "driveModes: both | cframe | physics")
		root:SetAttribute("DriveModes", driveModes)
	end
	return "StreamingProto.Boot = " .. kind .. " (save, then a fresh Play)"
end

local BOOT_SERVER_SRC = [[
-- StreamingPrototype boot (dev only; removed by StreamingPrototype.Remove). Does nothing outside Studio or when
-- workspace.StreamingProto.Boot is "off".
local root = workspace:FindFirstChild("StreamingProto")
if not (game:GetService("RunService"):IsStudio() and root and root:GetAttribute("Boot") ~= "off") then return end
local P = require(game:GetService("ServerStorage"):WaitForChild("StreamingPrototype"))
P.Server.start()
P.Server.check()
P.Server.boot(root:GetAttribute("Boot"))
]]

local BOOT_CLIENT_SRC = [[
-- StreamingPrototype boot, client (dev only; removed by StreamingPrototype.Remove)
local root = workspace:WaitForChild("StreamingProto", 30)
if not (game:GetService("RunService"):IsStudio() and root and root:GetAttribute("Boot") ~= "off") then return end
local P = require(game:GetService("ReplicatedStorage"):WaitForChild("StreamingPrototype", 30))
P.Client.sequence(root:GetAttribute("Boot"))
]]

local function installBoot()
	local SSS = game:GetService("ServerScriptService")
	local SPS = game:GetService("StarterPlayer"):FindFirstChild("StarterPlayerScripts")
	for _, spec in {{SSS, BOOT_SERVER, "Script", BOOT_SERVER_SRC}, {SPS, BOOT_CLIENT, "LocalScript", BOOT_CLIENT_SRC}} do
		local parent = spec[1]
		if parent then
			local old = parent:FindFirstChild(spec[2])
			if old then old:Destroy() end
			local sc: any = Instance.new(spec[3])
			sc.Name = spec[2]
			sc.Source = spec[4]
			sc.Parent = parent
		end
	end
end

-- client-only collision audit: every template of the client-built layer (variant C) must have CanCollide = false
-- and CanTouch = false. Returns the offending parts ("" = none). Build("C") fails when it is not empty.
function P.CollisionAudit(): string
	local det = ReplicatedStorage:FindFirstChild(DETAIL)
	if not det then return "" end
	local bad = {}
	for _, d in det:GetDescendants() do
		if d:IsA("BasePart") and (d.CanCollide or d.CanTouch) then
			table.insert(bad, d:GetFullName())
		end
	end
	table.sort(bad)
	return table.concat(bad, "\n")
end

function P.Build(variant: string?, opts: any?): string
	assert(isEdit(), "StreamingPrototype.Build: Edit mode only")
	local bo = opts or {}
	local okRoute, Route = pcall(function()
		return require(game:GetService("ServerStorage"):WaitForChild("PattayaRoute", 5) :: any)
	end)
	assert(okRoute and Route, "StreamingPrototype.Build: needs ServerStorage.PattayaRoute (the road graph) for the drive path")
	local v = string.upper(variant or "B")
	local t0 = os.clock()
	local conts, src = P.MakePlan(v)
	assert(#src > 0, "StreamingPrototype.Build: the district is empty (is PattayaWorld built?)")
	if #ownInstances() > 0 then
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
	-- the drive path: the longest road-graph route fully inside the district whose 4-stud samples are on copied
	-- road parts (PickRoute); fewer than 99% on road fails the build (the prototype is removed again)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {root}
	local function onRoad(p: Vector3): boolean
		local hit = workspace:Raycast(p + Vector3.new(0, 40, 0), Vector3.new(0, -80, 0), params)
		return hit ~= nil and hit.Instance:GetAttribute("ProtoCat") == "road"
	end
	local origin: Vector3 = Route.ORIGIN or Vector3.new(20000, 0, 0)
	local mc = cfg.centre - origin
	local box = {mc.X - cfg.half, mc.X + cfg.half, mc.Z - cfg.half, mc.Z + cfg.half}
	local picked, why = P.PickRoute(Route, onRoad, box, {shift = shift, from = bo.pathFrom, to = bo.pathTo})
	if not picked then
		P.Remove()
		error("StreamingPrototype.Build: no usable drive path (" .. why .. "); the prototype was removed again")
	end
	local path = {}
	for _, q in picked.pts do
		table.insert(path, Route.toWorld(q, 1) + shift)
	end
	root:SetAttribute("ProtoPath", packPath(path))
	root:SetAttribute("ProtoPathInfo", why)
	root:SetAttribute("ProtoPathCoverage", picked.frac)
	root:SetAttribute("Boot", "off")
	root:SetAttribute("ColdSeconds", 30)
	root:SetAttribute("DriveModes", "both")
	local audit = P.CollisionAudit()
	if audit ~= "" then
		P.Remove()
		error("StreamingPrototype.Build: client-layer parts with collision (must be none):\n" .. audit)
	end
	installClientCopy()
	installBoot()
	return planText(v, conts, src) .. ("\nbuilt %d parts (%d not clonable) in %.1f s; drive path %d points (%s);"
		.. " workspace.%s%s; boot scripts installed (Boot = off, see P.SetBoot); SAVE the place, then Play"):format(cloned, failed, os.clock() - t0, #path, why, ROOT,
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

local function unpackPath(s: string?): {Vector3}
	local out = {}
	for item in string.gmatch(s or "", "[^;]+") do
		local x, y, z = string.match(item, "([-%d%.]+),([-%d%.]+),([-%d%.]+)")
		if x then table.insert(out, Vector3.new(tonumber(x) :: number, tonumber(y) :: number, tonumber(z) :: number)) end
	end
	return out
end

local function serverKit(): any
	local ok, kit = pcall(function()
		return require(game:GetService("ServerStorage"):WaitForChild("PattayaTestKitServer", 5) :: any)
	end)
	return if ok then kit else nil
end

-- moves the player's car to `goal` without RequestStreamAroundAsync (anchored 0.3 s, like the kit)
local function moveDirect(plr: Player, goal: Vector3, look: Vector3?): (boolean, string)
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	local car = seat and seat.Parent
	if not (car and car:IsA("Model") and car.PrimaryPart) then return false, "not in a car" end
	local chassis = car.PrimaryPart :: BasePart
	local offset = chassis.CFrame:ToObjectSpace(car:GetPivot())
	local at = goal + Vector3.new(0, 2.8, 0)
	local dir = if look and look.Magnitude > 0.1 then Vector3.new(look.X, 0, look.Z).Unit else Vector3.xAxis
	chassis.Anchored = true
	chassis.AssemblyLinearVelocity = Vector3.zero
	car:PivotTo(CFrame.lookAt(at, at + dir) * offset)
	task.wait(0.3)
	chassis.Anchored = false
	pcall(function() chassis:SetNetworkOwner(plr) end)
	return true, "moved (no pre-stream)"
end

local function protoStart(): (Vector3?, Vector3?)
	local root = workspace:FindFirstChild(ROOT)
	local path = unpackPath(root and root:GetAttribute("ProtoPath"))
	if #path < 2 then return nil, nil end
	return path[1], path[2] - path[1]
end

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
			local kit = serverKit()
			if b ~= false and kit and kit.teleport then
				return kit.teleport(plr, a, {hop = 1e6, force = true})
			end
			return moveDirect(plr, a)
		elseif action == "seat" then
			local kit = serverKit()
			if not kit then return false, "no PattayaTestKitServer" end
			return kit.seat(plr)
		end
		return false, "unknown action"
	end
	return "StreamingPrototype server remote ready"
end

-- server-side check (Play, server; the boot Script runs it): the server sees every part, so this is the collision a
-- server, other players' cars and traffic get. (1) client-layer templates with collision (must be 0); (2) the drive
-- path sampled every 4 studs against the copied road layer on the server (must be 100%); (3) colliding parts in
-- workspace.StreamingProto per category (A, B, C, D must give the same numbers: C moves no colliding part)
function P.Server.check(): string
	local root = workspace:FindFirstChild(ROOT)
	if not root then return "[StreamProto] server check: no workspace." .. ROOT end
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {root}
	local path = unpackPath(root:GetAttribute("ProtoPath"))
	local ok, n = 0, 0
	for i = 2, #path do
		local a, b = path[i - 1], path[i]
		local L = (Vector3.new(b.X, 0, b.Z) - Vector3.new(a.X, 0, a.Z)).Magnitude
		local steps = math.max(1, math.floor(L / 4))
		for k = 0, steps - 1 do
			local q = a:Lerp(b, k / steps)
			local hit = workspace:Raycast(q + Vector3.new(0, 40, 0), Vector3.new(0, -80, 0), params)
			n += 1
			if hit and hit.Instance:GetAttribute("ProtoCat") == "road" then ok += 1 end
		end
	end
	local collide: {[string]: number} = {}
	for _, d in root:GetDescendants() do
		if d:IsA("BasePart") and d.CanCollide then
			local c = d:GetAttribute("ProtoCat") or "?"
			collide[c] = (collide[c] or 0) + 1
		end
	end
	local keys = {}
	for k in collide do table.insert(keys, k) end
	table.sort(keys)
	local parts = {}
	for _, k in keys do table.insert(parts, k .. " " .. collide[k]) end
	local audit = P.CollisionAudit()
	local nAudit = 0
	for _ in string.gmatch(audit, "[^\n]+") do nAudit += 1 end
	local line = ("[StreamProto] server check variant %s: client-only collision parts %d; path on road (server) %d/%d = %.1f%%;"
		.. " colliding parts: %s"):format(tostring(root:GetAttribute("Variant")), nAudit, ok, n,
		if n > 0 then ok / n * 100 else 0, table.concat(parts, ", "))
	print(line)
	return line
end

-- boot sequence (the boot Script): seat the first player in the nearest race car; "cold": move it into the proto at
-- once, without pre-stream. The client half (Client.sequence) records.
function P.Server.boot(kind: string)
	local function go(plr: Player)
		local char = plr.Character or plr.CharacterAdded:Wait()
		char:WaitForChild("Humanoid", 10)
		task.wait(1)
		local kit = serverKit()
		if not kit then
			warn("[StreamProto] boot: no PattayaTestKitServer")
			return
		end
		local ok, msg = kit.seat(plr)
		plr:SetAttribute("StreamProtoSeated", os.clock()) -- player attribute: gone with the Play session
		if ok and kind == "cold" then
			local start, look = protoStart()
			if start then
				ok, msg = moveDirect(plr, start, look)
				plr:SetAttribute("StreamProtoArrived", ok)
			end
		end
		print("[StreamProto] boot", kind, plr.Name, ok, msg)
	end
	local first = Players:GetPlayers()[1]
	if first then
		task.spawn(go, first)
	else
		local conn
		conn = Players.PlayerAdded:Connect(function(plr)
			conn:Disconnect()
			go(plr)
		end)
	end
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
	local frameMade = 0
	local conn = RunService.Heartbeat:Connect(function()
		frameMade = 0
		local f = focus()
		if not f then return end
		local spent = 0
		for _, t in all do
			if spent >= budget then break end
			local d = math.sqrt((t.pos.X - f.X) ^ 2 + (t.pos.Z - f.Z) ^ 2)
			if not t.live and d <= R then
				local c = t.tpl:Clone()
				c.CanCollide = false
				c.CanTouch = false
				c.CanQuery = false
				c.Parent = folder
				t.live = c
				spent += t.n
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

local function getTK(): any
	local ok, TK = pcall(function() return require(ReplicatedStorage:WaitForChild("PattayaTestKit", 10) :: any) end)
	assert(ok and TK, "needs ReplicatedStorage.PattayaTestKit")
	return TK
end

-- per-window statistics: avg FPS, p99 / worst frame, 1% low FPS, instances added per frame (max, p99)
function P.stats(frameMs: {number}, added: {number}): {[string]: number}
	local sorted = table.clone(frameMs)
	table.sort(sorted)
	local sum = 0
	for _, ms in frameMs do sum += ms end
	local k = math.max(1, math.ceil(#sorted * 0.01))
	local worstSum = 0
	for i = #sorted - k + 1, #sorted do worstSum += sorted[i] end
	local a = table.clone(added)
	table.sort(a)
	local over50, over100 = 0, 0
	for _, ms in frameMs do
		if ms > 50 then over50 += 1 end
		if ms > 100 then over100 += 1 end
	end
	local total = 0
	for _, n in added do total += n end
	return {
		frames = #frameMs, avgFps = if sum > 0 then #frameMs / (sum / 1000) else 0,
		p99Ms = percentile(sorted, 99), worstMs = sorted[#sorted] or 0, medianMs = percentile(sorted, 50),
		low1Fps = if worstSum > 0 then 1000 / (worstSum / k) else 0, over50 = over50, over100 = over100,
		addedMax = a[#a] or 0, addedP99 = percentile(a, 99), addedTotal = total,
	}
end

-- one recorded window. o.mode: "cold" | "teleport" | "drive" | "teleport_drive"; o.speed; o.seconds;
-- o.reverse (drive the path backwards); o.prestream (teleport: false = no RequestStreamAroundAsync); o.t0 (cold:
-- the client start time, so the window begins at join)
function P.Client.measure(o: any): any
	assert(RunService:IsClient(), "Client.measure: Play mode, client side")
	local mode = o.mode or "teleport"
	local speed = o.speed or 150
	local root = workspace:WaitForChild(ROOT, 30)
	assert(root, "no workspace." .. ROOT .. " (Build() it in Edit mode first)")
	local TK = getTK()
	local remote = ReplicatedStorage:WaitForChild(REMOTE, 30) :: RemoteFunction?
	local path = unpackPath(root:GetAttribute("ProtoPath"))
	assert(#path >= 2, "the prototype has no drive path")
	if o.reverse then
		local r = {}
		for i = #path, 1, -1 do table.insert(r, path[i]) end
		path = r
	end
	local cum = cumulative(path)
	local variant = root:GetAttribute("Variant")
	local cfg = P.CONFIG
	local centre: Vector3 = root:GetAttribute("Centre") or (cfg.centre + Vector3.new(cfg.offsetX, 0, 0))
	local half: number = root:GetAttribute("Half") or cfg.half
	-- road-missing is checked against the copied road layer (roads, discs, aprons, corner fills, shoulders: ProtoCat
	-- "road"); a ray that hits the proto ground or nothing counts as missing
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {root}
	local function roadAt(p: Vector3): boolean
		local hit = workspace:Raycast(Vector3.new(p.X, p.Y + 30, p.Z), Vector3.new(0, -60, 0), params)
		return hit ~= nil and hit.Instance:GetAttribute("ProtoCat") == "road"
	end
	local function inProto(p: Vector3): boolean
		return math.abs(p.X - centre.X) <= half and math.abs(p.Z - centre.Z) <= half
	end
	local function carPos(): Vector3?
		local c = TK.car()
		return c and c.Position
	end
	local nearCount, stopNear = function() return 0 end, function() end
	if variant == "C" then
		nearCount, stopNear = startNearLayer(carPos)
	end
	local frames, added, clientAdded = {}, {}, {}
	local missUnder, missAhead5, missAhead10, checks = 0, 0, 0, 0
	local firstRoad: number? = nil
	local arrived: number? = nil
	local addCount = 0
	local addConn = root.DescendantAdded:Connect(function() addCount += 1 end)
	local mem0 = memory()
	local recording = false
	local t0 = o.t0 or os.clock()
	local drive: any = nil
	local moving = mode == "drive" or mode == "teleport_drive"
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
		if pos and inProto(pos) then
			arrived = arrived or (os.clock() - t0)
			checks += 1
			if roadAt(pos) then
				firstRoad = firstRoad or (os.clock() - t0)
			else
				missUnder += 1
			end
			if moving and drive then
				local s = arcOf(path, cum, pos)
				if s < cum[#cum] - speed * 0.5 and not roadAt(pointAt(path, cum, s + speed * 0.5)) then missAhead5 += 1 end
				if s < cum[#cum] - speed * 1.0 and not roadAt(pointAt(path, cum, s + speed * 1.0)) then missAhead10 += 1 end
			end
		end
	end)
	local msg = ""
	recording = true
	if mode == "teleport" or mode == "teleport_drive" then
		t0 = os.clock()
		assert(remote, "server remote missing: Server.start()")
		local ok, m = (remote :: RemoteFunction):InvokeServer("teleport", path[1], o.prestream ~= false)
		msg = tostring(ok) .. " " .. tostring(m)
	end
	if moving then
		if mode == "drive" then
			t0 = os.clock()
			missUnder, checks = 0, 0
		end
		drive = TK.drivePath(path, {speed = speed, physics = o.physics == true, name = "streamproto", holdEnd = 0.5})
	end
	local seconds = o.seconds or (if moving then cum[#cum] / speed + (if o.physics then 25 else 10) else 20)
	local stopAt = t0 + seconds
	while os.clock() < stopAt do
		if drive and drive.done and os.clock() - t0 > 3 then break end
		task.wait(0.1)
	end
	recording = false
	frameConn:Disconnect()
	addConn:Disconnect()
	if drive and not drive.done then drive:stop("measure end") end
	stopNear()
	-- completeness inside MinRadius / TargetRadius of the car (containers by their box, expected vs present)
	local pos = carPos() or path[1]
	local okIdx, index = pcall(function() return HttpService:JSONDecode(root:GetAttribute("Index")) end)
	local present: {[string]: number} = {}
	for _, f in root:GetChildren() do
		for _, m in f:GetChildren() do present[f.Name .. "/" .. m.Name] = 1 + #m:GetDescendants() end
	end
	local function complete(r: number): number?
		if not okIdx then return nil end
		local exp, got = 0, 0
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
		return if exp > 0 then got / exp else nil
	end
	local mem1 = memory()
	local st = P.stats(frames, added)
	local clientMax = 0
	for _, n in clientAdded do clientMax = math.max(clientMax, n) end
	local res = {
		variant = variant, mode = mode, speed = if moving then speed else nil, prestream = o.prestream ~= false,
		physics = moving and o.physics == true,
		stats = st, roadMissingUnderCar = missUnder, roadChecks = checks, roadMissingAhead05s = missAhead5,
		roadMissingAhead1s = missAhead10, firstRoadUnderCarS = firstRoad, arrivedInProtoS = arrived,
		completeMin = complete(cfg.minRadius), completeTarget = complete(cfg.targetRadius), clientLayerMax = clientMax,
		memBefore = mem0, memAfter = mem1, drive = drive and drive.reason, msg = msg,
	}
	local tags = {}
	for _, t in MEM_TAGS do
		if mem1[t] then table.insert(tags, ("%s %.0f (%+.0f)"):format(t, mem1[t], mem1[t] - (mem0[t] or 0))) end
	end
	res.summary = ("[StreamProto] %s %s%s | avg %.1f fps, p99 %.0f ms, 1%% low %.1f fps, worst %.0f ms, >50ms %d, >100ms %d,"
		.. " %d frames | added/frame max %d p99 %d total %d%s | road missing under car %d/%d, ahead 0.5s %d, 1s %d;"
		.. " in proto at %.1fs, first road %.1fs | complete min %s target %s | mem total %.0f MB (%+.0f): %s")
		:format(tostring(variant), mode, if moving then (" v=%d %s"):format(speed, if o.physics then "physics" else "cframe") else "", st.avgFps, st.p99Ms,
			st.low1Fps, st.worstMs, st.over50, st.over100, st.frames, st.addedMax, st.addedP99, st.addedTotal,
			if variant == "C" then (" (client layer max %d)"):format(clientMax) else "", missUnder, checks, missAhead5,
			missAhead10, arrived or -1, firstRoad or -1,
			if res.completeMin then ("%.0f%%"):format(res.completeMin * 100) else "-",
			if res.completeTarget then ("%.0f%%"):format(res.completeTarget * 100) else "-",
			mem1.total, mem1.total - mem0.total, table.concat(tags, ", "))
	last = res
	_G.StreamProto = _G.StreamProto or {}
	_G.StreamProto.result = res
	_G.StreamProto.runs = _G.StreamProto.runs or {}
	table.insert(_G.StreamProto.runs, res.summary)
	print(res.summary)
	return res
end

function P.Client.run(opts: any?): string
	return P.Client.measure(opts or {}).summary
end

-- the automatic sequence of one fresh Play (boot LocalScript): "cold" or "teleport", then drives at 100 / 150 / 200
function P.Client.sequence(kind: string): string
	local tStart = os.clock() -- the client script starts right after join
	local TK = getTK()
	local untilT = os.clock() + 60
	while not TK.car() and os.clock() < untilT do task.wait(0.2) end
	assert(TK.car(), "[StreamProto] sequence: not seated in a car within 60 s (boot server)")
	local root = workspace:WaitForChild(ROOT, 30)
	if kind == "cold" then
		local secs = (root and root:GetAttribute("ColdSeconds")) or 30
		P.Client.measure({mode = "cold", t0 = tStart, seconds = secs - (os.clock() - tStart)})
	else
		task.wait(math.max(0, 15 - (os.clock() - tStart))) -- the city around the spawn settles first
		P.Client.measure({mode = "teleport", seconds = 20})
	end
	-- DriveModes (root attribute): "both" (default: CFrame then physics at each speed), "cframe" or "physics"
	local dm = (root and root:GetAttribute("DriveModes")) or "both"
	local modes = if dm == "cframe" then {false} elseif dm == "physics" then {true} else {false, true}
	local k = 0
	for _, v in {100, 150, 200} do
		for _, phys in modes do
			task.wait(2)
			k += 1
			P.Client.measure({mode = "drive", speed = v, physics = phys, reverse = k % 2 == 0})
		end
	end
	local rep = P.Client.report()
	print(rep)
	return rep
end

function P.Client.report(): string
	local runs = _G.StreamProto and _G.StreamProto.runs
	return if runs then table.concat(runs, "\n") else "no run yet"
end

function P.Client.last(): string
	return if last then last.summary else "no run yet"
end

return P
