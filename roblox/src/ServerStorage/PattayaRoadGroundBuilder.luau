--!strict
-- Ground at road level, pilot (MIDNIGHT PATTAYA): the terrain of the Road B box (Sukhumvit / Pattaya Klang junction,
-- world x 24220..24820, z 648..1252) raised from y -2 to y +0.43, so every road edge steps 0.57 down to the ground
-- instead of 3 studs to the terrain, and the strip between the road and the buildings is no longer a trench a car
-- cannot climb out of. docs/ROAD_GROUND_PILOT.md. Data: ServerStorage.PattayaDataRoadGround
-- (tools/roadvis/ground_export.py -> build/roadground/roblox: manifest + edges_<cx>_<cz>). Edit mode only. Written and
-- run OFFLINE (luau CLI with a voxel mock); NOT run in Studio yet: the terrain write needs the owner's explicit
-- permission and a fresh place backup.
--   local RG = require(game.ServerStorage.PattayaRoadGroundBuilder)
--   RG.Plan()        -- what Build would write; whether the terrain in the box is the expected state; Road B state
--   RG.Build()       -- backup (TerrainRegion + checksum) -> write the voxel layer -> measure + calibrate -> kerb bands
--   RG.Build({pavementColor = true})   -- OPT-IN: also Terrain:SetMaterialColor(Pavement) (global for Pavement)
--   RG.Build({edges = false})          -- the ground alone (no kerb bands; Road B not needed)
--   RG.Probe()       -- terrain height, road-to-ground steps, a 2-stud raycast grid for drops, the ramp, kerb bands
--   RG.Remove()      -- PasteRegion the backup, verify the voxels are EXACTLY the old ones (checksum), kerb bands gone
--   RG.Leftovers()   -- anything this module could have left behind ("road ground leftovers: none")
-- The ground: ONE voxel layer (y -4 .. 0, 4-stud voxels) gets a partial occupancy (Ground full stays under it, y -8 ..
-- -4). PattayaBuilder measured that a layer filled up to grid line Y renders at Y + 2 (filled to -4: surface -2). The
-- start value assumes linear in between (surface = -2 + 4 * occupancy, 0.6075 for +0.43); Build measures the surface
-- with raycasts on the terrain only and corrects the occupancy (secant from occupancy 0 = -2, at most 4 writes).
-- Outside the measured window the terrain is put back and Build aborts. Columns within 4 studs outside the box keep
-- the full height, then a 28-stud ramp brings it back to -2 (no new cliff at the box edge). Materials: Pavement near
-- buildings and along every paved edge, Ground in open lots and on the ramp. Zero new instances for the ground (one
-- TerrainRegion backup in ServerStorage). Kerb bands: thin non-colliding, non-queryable Parts along the road edges that
-- now face the ground (the edge reads as a kerb; no invisible wall, nothing the car or a raycast touches).
-- Nothing else in the place is touched: no part is moved, RoadVisPilot / ShoulderChunks / the road graph / GPS / car
-- physics stay as they are.
local ServerStorage = game:GetService("ServerStorage")

local RG = {}

RG.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN
RG.DATA = "PattayaDataRoadGround"
RG.BACKUP = "RoadGroundBackup" -- ServerStorage folder: TerrainRegion "Voxels" + the checksum and the write record
RG.FOLDER = "RoadGroundEdges" -- workspace.PattayaWorld folder of the kerb band cells
RG.SHOULDER_BACKUP = "PattayaShoulderTerrainBackup" -- PattayaShoulderBuilder.BuildTerrain backups (must not overlap)
local VOX = 4

local function rgb(c: {number}): Color3
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function data(): (Instance, any)
	local d = ServerStorage:WaitForChild(RG.DATA)
	local m = d:WaitForChild("manifest") :: ModuleScript
	return d, require(m:Clone()) :: any -- Clone(): a just-replaced module is never served from the require cache
end

local function moduleData(d: Instance, name: string): any
	local m = d:WaitForChild(name) :: ModuleScript
	return require(m:Clone()) :: any
end

local function world(): Instance
	local w = workspace:FindFirstChild("PattayaWorld")
	if not w then
		error("PattayaRoadGroundBuilder: workspace.PattayaWorld not found")
	end
	return w :: Instance
end

-- ---- voxel boxes ---------------------------------------------------------------------------------------------------
-- written columns: voxel x i0 .. i0 + ni - 1, z k0 .. k0 + nk - 1, the one layer y -4 .. 0
local function writeRegion(man: any): Region3
	local g = man.region
	return Region3.new(Vector3.new(VOX * g.i0, -4, VOX * g.k0), Vector3.new(VOX * (g.i0 + g.ni), 0, VOX * (g.k0 + g.nk)))
end

-- the backup box (inclusive voxel indices) as a Region3 in studs, for ReadVoxels
local function boxRegion(vmin: Vector3, vmax: Vector3): Region3
	return Region3.new(Vector3.new(VOX * vmin.X, VOX * vmin.Y, VOX * vmin.Z),
		Vector3.new(VOX * (vmax.X + 1), VOX * (vmax.Y + 1), VOX * (vmax.Z + 1)))
end

local function backupBox(man: any): (Vector3, Vector3)
	local b = man.backup
	return Vector3.new(b.i0, b.y0, b.k0), Vector3.new(b.i1, b.y1, b.k1)
end

-- exact fingerprint of every voxel in the box: two polynomial hashes over (material, occupancy in 1/65535 steps),
-- plus the voxel count; stored on the backup before the first write, compared after the restore
local function checksum(vmin: Vector3, vmax: Vector3): string
	local mats, occs = workspace.Terrain:ReadVoxels(boxRegion(vmin, vmax), VOX)
	local size = mats.Size
	local h1, h2, n = 0, 0, 0
	for x = 1, size.X do
		for y = 1, size.Y do
			for z = 1, size.Z do
				local v = (mats[x][y][z] :: Enum.Material).Value * 65536 + math.floor(occs[x][y][z] * 65535 + 0.5)
				h1 = (h1 * 131 + v) % 2147483647
				h2 = (h2 * 137 + v) % 1000000009
				n += 1
			end
		end
	end
	return ("%d:%d:%d"):format(h1, h2, n)
end

-- the expected state of the box before a build and after a restore: Ground full in the layer y -8 .. -4, Air above
-- (PattayaBuilder extendTerrain: filled to y -4). Returns ok, report.
local function expectedState(vmin: Vector3, vmax: Vector3): (boolean, string)
	local mats, occs = workspace.Terrain:ReadVoxels(boxRegion(vmin, vmax), VOX)
	local size = mats.Size
	local good, bad = 0, 0
	local seen: {[string]: number} = {}
	for x = 1, size.X do
		for y = 1, size.Y do
			local vy = vmin.Y + y - 1
			for z = 1, size.Z do
				local m, o = mats[x][y][z] :: Enum.Material, occs[x][y][z] :: number
				local ok = if vy <= -2 then m == Enum.Material.Ground and o >= 0.99 else m == Enum.Material.Air and o <= 0.01
				if ok then
					good += 1
				else
					bad += 1
					local k = ("%s %.2f at y %d"):format(m.Name, o, VOX * vy)
					seen[k] = (seen[k] or 0) + 1
				end
			end
		end
	end
	local kinds = {}
	for k, c in seen do
		table.insert(kinds, ("%s x%d"):format(k, c))
	end
	table.sort(kinds)
	return bad == 0, ("%d voxels as expected, %d not%s"):format(good, bad,
		if bad > 0 then " [" .. table.concat(kinds, "; ", 1, math.min(6, #kinds)) .. "]" else "")
end

-- a PattayaShoulderBuilder terrain backup whose box overlaps ours: its RemoveTerrain would later paste over the ground
local function shoulderBackups(vmin: Vector3, vmax: Vector3): number
	local f = ServerStorage:FindFirstChild(RG.SHOULDER_BACKUP)
	if not f then
		return 0
	end
	local n = 0
	for _, r in f:GetChildren() do
		if r:IsA("TerrainRegion") then
			local c = r:GetAttribute("Corner")
			local s = (r :: any).SizeInCells
			if typeof(c) == "Vector3" and s then
				if c.X <= vmax.X and c.X + s.X - 1 >= vmin.X and c.Z <= vmax.Z and c.Z + s.Z - 1 >= vmin.Z then
					n += 1
				end
			else
				n += 1 -- unknown extent: assume it overlaps
			end
		end
	end
	return n
end

-- ---- the column rule (= tools/roadvis/ground.ramp_factor) -------------------------------------------------------------
local function factor(man: any, cx: number, cz: number): number
	local p = man.plateau
	local dx = math.max(p[1] - cx, cx - p[3], 0)
	local dz = math.max(p[2] - cz, cz - p[4], 0)
	local d = math.sqrt(dx * dx + dz * dz)
	if d <= man.flat then
		return 1
	end
	return math.clamp(1 - (d - man.flat) / man.ramp, 0, 1)
end

-- WriteVoxels arrays [x][y][z] for the written columns at occupancy occTop * scale * factor
local function arrays(man: any, scale: number): (any, any, number, number)
	local g = man.region
	local mats, occs = table.create(g.ni), table.create(g.ni)
	local raised, plateau = 0, 0
	for a = 1, g.ni do
		local row = man.columns[a]
		local mz, oz = table.create(g.nk), table.create(g.nk)
		local cx = VOX * (g.i0 + a - 1) + VOX / 2
		for b = 1, g.nk do
			local ch = string.sub(row, b, b)
			local m, o = Enum.Material.Air, 0
			if ch ~= "." then
				local cz = VOX * (g.k0 + b - 1) + VOX / 2
				local f = factor(man, cx, cz)
				o = math.min(1, man.occTop * scale * f)
				if o > 0 then
					m = if ch == "p" then Enum.Material.Pavement else Enum.Material.Ground
					raised += 1
					local p = man.plateau
					if cx > p[1] and cx < p[3] and cz > p[2] and cz < p[4] then
						plateau += 1
					end
				else
					o = 0
				end
			end
			mz[b], oz[b] = m, o
		end
		mats[a], occs[a] = {mz}, {oz}
	end
	return mats, occs, raised, plateau
end

-- the terrain surface at the calibration columns (raycasts that see the terrain only): median, min, max, hits
local function measure(man: any): (number, number, number, number)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = {workspace.Terrain}
	local ys = {}
	local P = man.calibrate.probes
	for i = 1, #P, 2 do
		local hit = workspace:Raycast(Vector3.new(P[i], 20, P[i + 1]), Vector3.new(0, -40, 0), params)
		if hit then
			table.insert(ys, hit.Position.Y)
		end
	end
	if #ys == 0 then
		return -math.huge, -math.huge, -math.huge, 0
	end
	table.sort(ys)
	return ys[(#ys + 1) // 2], ys[1], ys[#ys], #ys
end

-- ---- Plan ---------------------------------------------------------------------------------------------------------
local function roadBState(man: any): (boolean, string)
	local w = workspace:FindFirstChild("PattayaWorld")
	local rv = w and w:FindFirstChild(man.roadB.folder)
	local backup = ServerStorage:FindFirstChild(man.roadB.backup)
	local cells, parts = 0, 0
	if rv then
		for _, c in rv:GetChildren() do
			cells += 1
			for _, p in c:GetDescendants() do
				if p:IsA("BasePart") then
					parts += 1
				end
			end
		end
	end
	local moved = if backup then backup:GetAttribute("Count") else nil
	return rv ~= nil, ("Road B: %s (%d cells, %d parts; data %d cells, %d parts); %s %s"):format(
		if rv then "RoadVisPilot built" else "RoadVisPilot NOT built", cells, parts, man.roadB.cells, man.roadB.parts,
		man.roadB.backup, if backup then ("present (Count %s, built in Studio 2026-10-22: %d)"):format(tostring(moved), man.roadB.moved) else "absent")
end

function RG.Plan(): string
	local _, man = data()
	local c = man.counts
	local vmin, vmax = backupBox(man)
	local lines = {("road ground plan: raise %d voxel columns (%d in the box, %d collar + ramp) of the layer y -4..0 to y %.2f "
		.. "(start occupancy %.4f, linear model; Build measures and calibrates); Pavement %d / Ground %d columns; "
		.. "%d kerb band parts in %d cells; 0 new instances for the ground"):format(c.written, c.plateau, c.ramp, man.top,
		man.occTop, c.pavement, c.ground, c.kerbParts, #man.cells)}
	local built = ServerStorage:FindFirstChild(RG.BACKUP) ~= nil
	if built then
		table.insert(lines, "terrain box: the ground is BUILT (RoadGroundBackup present): the box is not in its original state by design")
	else
		local ok, rep = expectedState(vmin, vmax)
		table.insert(lines, ("terrain box: voxels x %d..%d, z %d..%d, y %d..%d (world x %d..%d, z %d..%d): %s; %s"):format(
			vmin.X, vmax.X, vmin.Z, vmax.Z, vmin.Y, vmax.Y, VOX * vmin.X, VOX * (vmax.X + 1), VOX * vmin.Z, VOX * (vmax.Z + 1),
			if ok then "MATCHES the expected state (Ground full at y -8..-4, Air above)" else "DOES NOT MATCH (Build would abort)", rep))
	end
	local _, rb = roadBState(man)
	table.insert(lines, rb)
	table.insert(lines, ("shoulder terrain backups overlapping the box: %d (must be 0)"):format(shoulderBackups(vmin, vmax)))
	local pc = workspace.Terrain:GetMaterialColor(Enum.Material.Pavement)
	table.insert(lines, ("Pavement colour now %d, %d, %d (Build changes it only with {pavementColor = true}: %d, %d, %d)"):format(
		math.floor(pc.R * 255 + 0.5), math.floor(pc.G * 255 + 0.5), math.floor(pc.B * 255 + 0.5),
		man.pavementColor[1], man.pavementColor[2], man.pavementColor[3]))
	local w = workspace:FindFirstChild("PattayaWorld")
	table.insert(lines, ("ground built: %s; kerb bands present: %s"):format(tostring(built), tostring(w ~= nil and w:FindFirstChild(RG.FOLDER) ~= nil)))
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

-- ---- Build --------------------------------------------------------------------------------------------------------
local function buildEdges(d: Instance, man: any, w: Instance): (number, number)
	local root = Instance.new("Folder")
	root.Name = RG.FOLDER
	root:SetAttribute("Attribution", man.attribution)
	local k = man.kerb
	local color = rgb(k.color)
	local O = RG.ORIGIN
	local n, cells = 0, 0
	for _, name in man.modules do
		local m = moduleData(d, name)
		local cell = Instance.new("Model")
		cell.Name = "Cell_" .. m.cell
		cell.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
		local s = m.segs
		local made = 0
		for i = 1, #s, 5 do
			local a = Vector2.new(s[i] + O.X, s[i + 1] + O.Z)
			local b = Vector2.new(s[i + 2] + O.X, s[i + 3] + O.Z)
			local len = (b - a).Magnitude
			if len >= 0.05 then
				local mid = (a + b) / 2
				local y = (k.top + k.bottom) / 2
				local p = Instance.new("Part")
				p.Name = "GroundKerb"
				p.Size = Vector3.new(s[i + 4], k.top - k.bottom, len)
				p.CFrame = CFrame.lookAt(Vector3.new(mid.X, y, mid.Y), Vector3.new(b.X, y, b.Y))
				p.Anchored = true
				p.Color = color
				p.Material = Enum.Material.Concrete
				p.TopSurface = Enum.SurfaceType.Smooth
				p.BottomSurface = Enum.SurfaceType.Smooth
				p.CanCollide = false -- visual only: the asphalt under it carries the wheels, no invisible wall
				p.CanQuery = false -- out of the suspension rays and the probes
				p.CanTouch = false
				p.CastShadow = false
				p:SetAttribute("RoadGround", "kerb")
				p.Parent = cell
				made += 1
			end
		end
		if made ~= m.parts then
			warn(("road ground: kerb module %s built %d parts, data says %d"):format(name, made, m.parts))
		end
		n += made
		cells += 1
		cell.Parent = root
	end
	root.Parent = w
	return n, cells
end

function RG.Build(opts: {calibrate: boolean?, edges: boolean?, pavementColor: boolean?}?): string
	local options = (opts or {}) :: any
	local d, man = data()
	local w = world()
	if ServerStorage:FindFirstChild(RG.BACKUP) then
		return "road ground: RoadGroundBackup exists: the ground is already built (RG.Remove() first)"
	end
	if w:FindFirstChild(RG.FOLDER) then
		return "road ground: PattayaWorld.RoadGroundEdges exists without a terrain backup: run RG.Remove() first"
	end
	local rbBuilt, rb = roadBState(man)
	if options.edges ~= false and not rbBuilt then
		return "road ground: ABORTED, nothing written: the kerb bands follow Road B's asphalt and RoadVisPilot is not built ("
			.. rb .. "); RG.Build({edges = false}) raises the ground alone"
	end
	local vmin, vmax = backupBox(man)
	local sb = shoulderBackups(vmin, vmax)
	if sb > 0 then
		return ("road ground: ABORTED, nothing written: %d PattayaShoulderBuilder terrain backups overlap the box (their RemoveTerrain would paste over the ground)"):format(sb)
	end
	local ok, rep = expectedState(vmin, vmax)
	if not ok then
		local msg = "road ground: ABORTED, nothing written: the terrain in the box is not the expected state (" .. rep .. ")"
		warn(msg)
		return msg
	end
	local terrain = workspace.Terrain
	-- 1. backup first: every voxel of the box (one voxel wider than the written columns, y -8 .. 4) + its checksum
	local folder = Instance.new("Folder")
	folder.Name = RG.BACKUP
	local region = terrain:CopyRegion(Region3int16.new(Vector3int16.new(vmin.X, vmin.Y, vmin.Z), Vector3int16.new(vmax.X, vmax.Y, vmax.Z)))
	region.Name = "Voxels"
	region:SetAttribute("Corner", vmin)
	region.Parent = folder
	folder:SetAttribute("BoxMin", vmin)
	folder:SetAttribute("BoxMax", vmax)
	folder:SetAttribute("Checksum", checksum(vmin, vmax))
	folder:SetAttribute("Data", man.name)
	folder.Parent = ServerStorage
	-- 2. write, measure, calibrate
	local scale, writes = 1, 0
	local raised, plateau = 0, 0
	local function write()
		local mats, occs, r, p = arrays(man, scale)
		terrain:WriteVoxels(writeRegion(man), VOX, mats, occs)
		raised, plateau = r, p
		writes += 1
	end
	write()
	local med, lo, hi, n = measure(man)
	local cal = man.calibrate
	if options.calibrate ~= false then
		-- secant on (occupancy, measured surface): the first pair is (0, -2) = today's terrain and the model write
		local o0, s0 = 0, man.terrainTop
		while writes < cal.maxWrites and n > 0 and med > man.terrainTop + 0.05 and math.abs(med - man.top) > cal.tol do
			local o1 = man.occTop * scale
			local o2 = o1 + (man.top - med) * (o1 - o0) / (med - s0)
			o0, s0 = o1, med
			scale = math.clamp(o2, 0.05, 1) / man.occTop
			write()
			med, lo, hi, n = measure(man)
		end
	end
	local inWindow = n > 0 and med >= man.window[1] and med <= man.window[2] and hi - lo <= 2 * cal.flat
	if not inWindow then
		terrain:PasteRegion(region, Vector3int16.new(vmin.X, vmin.Y, vmin.Z), true)
		local exact = checksum(vmin, vmax) == folder:GetAttribute("Checksum")
		if exact then
			folder:Destroy()
		end
		local msg = ("road ground: ABORTED after %d writes: measured surface %s (window %.2f .. %.2f, %d probes); terrain %s")
			:format(writes, if n > 0 then ("median %.3f, %.3f .. %.3f"):format(med, lo, hi) else "not found", man.window[1],
				man.window[2], n, if exact then "restored exactly (checksum), backup removed" else "restore NOT exact: RoadGroundBackup KEPT")
		warn(msg)
		return msg
	end
	folder:SetAttribute("Scale", scale)
	folder:SetAttribute("Writes", writes)
	folder:SetAttribute("Measured", med)
	-- 3. optional Pavement colour (global for every Pavement voxel of the place; old colour kept on the backup)
	if options.pavementColor then
		folder:SetAttribute("PavementColorBefore", terrain:GetMaterialColor(Enum.Material.Pavement))
		terrain:SetMaterialColor(Enum.Material.Pavement, rgb(man.pavementColor))
	end
	-- 4. kerb bands
	local kp, kc = 0, 0
	if options.edges ~= false then
		kp, kc = buildEdges(d, man, w)
	end
	return ("road ground: raised %d columns (%d in the box, %d collar + ramp) to y %.3f (median of %d probes, %.3f .. %.3f; "
		.. "%d writes, occupancy %.4f); %d kerb band parts in %d cells%s; backup ServerStorage.%s (%s)"):format(raised, plateau,
		raised - plateau, med, n, lo, hi, writes, man.occTop * scale, kp, kc, if options.pavementColor then "; Pavement recoloured" else "",
		RG.BACKUP, tostring(folder:GetAttribute("Checksum")))
end

-- ---- Remove / Leftovers ---------------------------------------------------------------------------------------------
function RG.Remove(): string
	local w = workspace:FindFirstChild("PattayaWorld")
	local edges = w and w:FindFirstChild(RG.FOLDER)
	local nEdges = 0
	if edges then
		for _, p in edges:GetDescendants() do
			if p:IsA("BasePart") then
				nEdges += 1
			end
		end
		edges:Destroy()
	end
	local folder = ServerStorage:FindFirstChild(RG.BACKUP)
	if not folder then
		return ("road ground: no terrain backup, nothing to restore; %d kerb band parts removed"):format(nEdges)
	end
	local region = folder:FindFirstChild("Voxels")
	local vmin, vmax = folder:GetAttribute("BoxMin"), folder:GetAttribute("BoxMax")
	if not (region and region:IsA("TerrainRegion") and typeof(vmin) == "Vector3" and typeof(vmax) == "Vector3") then
		local msg = "road ground: RoadGroundBackup is incomplete (no Voxels / box): nothing restored, backup KEPT"
		warn(msg)
		return msg
	end
	local terrain = workspace.Terrain
	terrain:PasteRegion(region :: TerrainRegion, Vector3int16.new(vmin.X, vmin.Y, vmin.Z), true)
	local pc = folder:GetAttribute("PavementColorBefore")
	if typeof(pc) == "Color3" then
		terrain:SetMaterialColor(Enum.Material.Pavement, pc)
	end
	local now = checksum(vmin, vmax)
	local want = folder:GetAttribute("Checksum")
	if now == want then
		folder:Destroy()
		return ("road ground: terrain restored EXACTLY (checksum %s = before the build), backup removed; %d kerb band parts removed%s")
			:format(now, nEdges, if typeof(pc) == "Color3" then "; Pavement colour restored" else "")
	end
	local msg = ("road ground: terrain restore NOT exact (checksum %s, before %s): RoadGroundBackup KEPT; %d kerb band parts removed")
		:format(now, tostring(want), nEdges)
	warn(msg)
	return msg
end

function RG.Leftovers(): string
	local found = {}
	if ServerStorage:FindFirstChild(RG.BACKUP) then
		table.insert(found, "ServerStorage." .. RG.BACKUP)
	end
	local w = workspace:FindFirstChild("PattayaWorld")
	if w and w:FindFirstChild(RG.FOLDER) then
		table.insert(found, "PattayaWorld." .. RG.FOLDER)
	end
	local tagged = 0
	for _, root in {w, ServerStorage} do
		if root then
			for _, d in (root :: Instance):GetDescendants() do
				if d:GetAttribute("RoadGround") ~= nil then
					tagged += 1
				end
			end
		end
	end
	if tagged > 0 then
		table.insert(found, ("%d instances with the RoadGround attribute"):format(tagged))
	end
	local ok, man = pcall(function()
		local _, m = data()
		return m
	end)
	if ok and man and not ServerStorage:FindFirstChild(RG.BACKUP) then
		local vmin, vmax = backupBox(man)
		local same, rep = expectedState(vmin, vmax)
		if not same then
			table.insert(found, "terrain box not in its original state: " .. rep)
		end
	elseif not ok then
		table.insert(found, "(no data module: the terrain box was not checked)")
	end
	return if #found == 0 then "road ground leftovers: none" else "road ground leftovers: " .. table.concat(found, "; ")
end

-- ---- Probe --------------------------------------------------------------------------------------------------------
-- 1. the terrain surface at the calibration columns; 2. every road-to-ground edge pair: the top on the road (0.6 stud
-- in) minus the top on the ground (1.5 studs out), must be <= 0.6 (+0.03); 3. a 2-stud raycast grid over the box:
-- neighbour steps of 1.5 or more between floor hits (tops <= 1.8: walls, props and buildings are not floors) = drops;
-- 4. the ramp: terrain-only rays every stud outward from the box edge on its four sides (largest step between
-- neighbours); 5. kerb bands present / data. The manifest holds the offline expectation.
function RG.Probe(): string
	local _, man = data()
	local med, lo, hi, n = measure(man)
	local all = RaycastParams.new()
	all.FilterType = Enum.RaycastFilterType.Exclude
	all.FilterDescendantsInstances = {}
	local function top(x: number, z: number, params: RaycastParams): number
		-- from 300 studs up: a ray must not start inside a tall building (it would not hit that building)
		local hit = workspace:Raycast(Vector3.new(x, 300, z), Vector3.new(0, -320, 0), params)
		return if hit then hit.Position.Y else -math.huge
	end
	local E = man.edgeChecks
	local nE, over, smin, smax, propHit = 0, 0, math.huge, -math.huge, 0
	local worstAt = ""
	for i = 1, #E, 5 do
		local yi, yo = top(E[i], E[i + 1], all), top(E[i + 2], E[i + 3], all)
		if yi > 1.8 or yo > 1.8 then
			propHit += 1 -- a pole, sign or building over one of the two points: not a floor step
			continue
		end
		local s = yi - yo
		nE += 1
		smin, smax = math.min(smin, s), math.max(smax, s)
		if s > 0.63 then
			over += 1
			if worstAt == "" then
				worstAt = ("; first over 0.6 at (%.1f, %.1f) step %.2f"):format(E[i + 2], E[i + 3], s)
			end
		end
	end
	local p = man.plateau
	local g = man.probe.grid
	local nx, nz = math.floor((p[3] - p[1]) / g), math.floor((p[4] - p[2]) / g)
	local prev: {number} = {}
	local drops, rays, maxStep, voids = 0, 0, 0, 0
	local dropAt = {}
	for a = 0, nx - 1 do
		local row = {}
		for b = 0, nz - 1 do
			local x, z = p[1] + (a + 0.5) * g, p[2] + (b + 0.5) * g
			local y = top(x, z, all)
			rays += 1
			row[b + 1] = y
			if y <= -1e9 then
				voids += 1 -- a ray that found nothing at all: a hole down to nowhere
			end
			local function cmp(y2: number?)
				if y2 and y <= 1.8 and y2 <= 1.8 and y > -1e9 and y2 > -1e9 then
					local s = math.abs(y - y2)
					maxStep = math.max(maxStep, s)
					if s >= 1.5 then
						drops += 1
						if #dropAt < 5 then
							table.insert(dropAt, ("(%.1f, %.1f) %.2f"):format(x, z, s))
						end
					end
				end
			end
			cmp(if b > 0 then row[b] else nil)
			cmp(prev[b + 1])
		end
		prev = row
		if a % 30 == 29 then
			task.wait()
		end
	end
	-- the ramp, terrain only: one line out of the middle of each side of the box
	local tp = RaycastParams.new()
	tp.FilterType = Enum.RaycastFilterType.Include
	tp.FilterDescendantsInstances = {workspace.Terrain}
	local cx, cz = (p[1] + p[3]) / 2, (p[2] + p[4]) / 2
	local rampStep, rampLow = 0, math.huge
	for _, s in {{p[1], cz, -1, 0}, {p[3], cz, 1, 0}, {cx, p[2], 0, -1}, {cx, p[4], 0, 1}} do
		local last = nil
		for t = -8, man.flat + man.ramp + 8 do
			local y = top(s[1] + s[3] * t, s[2] + s[4] * t, tp)
			if last then
				rampStep = math.max(rampStep, math.abs(y - last))
			end
			rampLow = math.min(rampLow, y)
			last = y
		end
	end
	local w = workspace:FindFirstChild("PattayaWorld")
	local edges = w and w:FindFirstChild(RG.FOLDER)
	local kp = 0
	if edges then
		for _, d in edges:GetDescendants() do
			if d:IsA("BasePart") then
				kp += 1
			end
		end
	end
	local e = man.probe.expected
	local lines = {
		("road ground probe: terrain at %d calibration columns: median %.3f (%.3f .. %.3f), target %.2f, window %.2f .. %.2f"):format(
			n, med, lo, hi, man.top, man.window[1], man.window[2]),
		("road-to-ground edges: %d pairs, step %.3f .. %.3f, over 0.6: %d (offline %.3f .. %.3f); %d pairs under a prop skipped%s"):format(
			nE, smin, smax, over, man.probe.edgeStepMin or -1, man.probe.edgeStepMax or -1, propHit, worstAt),
		("grid %g studs over the box: %d rays, floor steps >= 1.5: %d (offline %d; without the ground %d), largest floor step %.2f (offline %.2f), rays that hit nothing %d%s"):format(
			g, rays, drops, e.floorPairsOver1_5, man.probe.expectedWithoutGround.floorPairsOver1_5, maxStep, e.maxFloorStep, voids,
			if #dropAt > 0 then "; e.g. " .. table.concat(dropAt, "; ") else ""),
		("ramp (terrain only, 4 lines): largest 1-stud step %.3f, lowest %.2f"):format(rampStep, rampLow),
		("kerb bands: %d parts (data %d); backup %s"):format(kp, man.counts.kerbParts,
			if ServerStorage:FindFirstChild(RG.BACKUP) then "present" else "absent"),
	}
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

return RG
