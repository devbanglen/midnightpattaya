--!strict
-- Junction aprons + sidewalk corner fills for the Pattaya city (MIDNIGHT PATTAYA). Closes the ground that lies open
-- 3 studs below the road (terrain y -2, road top 1.0, sidewalk top 1.6) at junction corners and soi mouths, where
-- the road slabs end at the junction disc and the sidewalks stop r + sidewalk studs before the node. Built in Studio
-- (edit time) from the data modules in ServerStorage.PattayaDataAprons (tools/mapgen/junction_aprons.py ->
-- build/aprons/roblox: manifest + chunk_a<cx>_<cz>). Every chunk becomes an Atomic Model
-- workspace.PattayaWorld.ApronChunks.Chunk_a<cx>_<cz>. Nothing else in the place is touched. Built chunks are
-- skipped, so a call can be repeated after an error.
--   local A = require(game.ServerStorage.PattayaApronBuilder)
--   A.Build({batch = "a1"})                  -- one batch (<= 8 chunks), then "a2" ... (manifest.batchOrder)
--   A.Build({only = {"a2_0", "a1_0"}})        -- explicit chunk ids
--   A.Build()                                 -- everything left
--   A.Probe()                                 -- overlap / height / part-count probe of what is built (prints + returns)
--   A.Remove()                                -- undo: destroys ApronChunks only
-- Apron: flat road-height piece (top 0.98 = 2 cm under the road top, 4 thick), name "Road", Material Asphalt,
-- attributes RoadFill = true (the leader's slab-overlap probe skips RoadFill parts), Apron = true, JunctionId.
-- Corner fill: sidewalk-height piece (top 1.58, 3.6 thick), name "Sidewalk", Material Concrete, CornerFill = true,
-- JunctionId. Triangles are two WedgeParts split at the foot of the altitude on the longest side (exactly as
-- PattayaBuilder.roadTriangle); rectangles are one Part. Geometry must match tools/mapgen/junction_aprons.py
-- (wedge_count / piece_poly: the exporter's checks use the same shapes). Map-local (x, z) + ORIGIN.
local ServerStorage = game:GetService("ServerStorage")

local Aprons = {}

Aprons.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN
local ROAD_TOP = 1.0
local CURB_TOP = 1.6
local ROAD_NAMES = {Road = true, Junction = true, Joint = true}

type Style = {top: number, thick: number, material: Enum.Material, color: Color3, name: string, attr: string}

local function style(row: any, name: string, attr: string, fallback: Enum.Material): Style
	local mat = fallback
	local ok, m = pcall(function()
		return (Enum.Material :: any)[row.material]
	end)
	if ok and m then
		mat = m
	end
	return {top = row.top, thick = row.thick, material = mat, color = Color3.fromRGB(row.color[1], row.color[2], row.color[3]),
		name = name, attr = attr}
end

local function finish(p: BasePart, s: Style, junction: number, parent: Instance)
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
	if s.attr == "Apron" then
		p:SetAttribute("RoadFill", true)
		p:SetAttribute("Apron", true)
	else
		p:SetAttribute("CornerFill", true)
	end
	p:SetAttribute("JunctionId", junction)
	p.Parent = parent
end

-- one flat triangle a-b-c from two WedgeParts (PattayaBuilder.roadTriangle with a top / thickness / style)
local function triangle(parent: Instance, a: Vector2, b: Vector2, c: Vector2, s: Style, junction: number): number
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
			local xv = yv:Cross(zv)
			local centre = foot + Vector2.new(yv.X, yv.Z) * (h / 2) - Vector2.new(zv.X, zv.Z) * (l / 2)
			local w = Instance.new("WedgePart")
			w.Size = Vector3.new(s.thick, h, l)
			w.CFrame = CFrame.fromMatrix(Vector3.new(centre.X, y, centre.Y), xv, yv, zv)
			finish(w, s, junction, parent)
			n += 1
		end
	end
	return n
end

local function buildTris(parent: Instance, rows: {number}?, s: Style): number
	local n = 0
	rows = rows or {}
	for i = 1, #(rows :: {number}), 7 do
		local r = rows :: {number}
		n += triangle(parent, Vector2.new(r[i], r[i + 1]), Vector2.new(r[i + 2], r[i + 3]), Vector2.new(r[i + 4], r[i + 5]), s, r[i + 6])
	end
	return n
end

-- boxes {cx, cz, ux, uz, length, width, junction}: one Part, length along (ux, uz)
local function buildBoxes(parent: Instance, rows: {number}?, s: Style): number
	local n = 0
	local r = rows or {}
	for i = 1, #r, 7 do
		local c = Vector3.new(r[i], s.top - s.thick / 2, r[i + 1])
		local p = Instance.new("Part")
		p.Size = Vector3.new(r[i + 5], s.thick, r[i + 4])
		p.CFrame = CFrame.lookAt(c, c + Vector3.new(r[i + 2], 0, r[i + 3]))
		finish(p, s, r[i + 6], parent)
		n += 1
	end
	return n
end

local function data(folderName: string?): (Instance, any)
	local d = ServerStorage:WaitForChild(folderName or "PattayaDataAprons")
	local manModule = d:WaitForChild("manifest") :: ModuleScript
	return d, require(manModule:Clone()) :: any -- Clone(): a just-replaced module is never served from the require cache
end

function Aprons.Build(opts: {folder: string?, only: {string}?, batch: string?}?): string
	local options = (opts or {}) :: any
	local folderData, man = data(options.folder)
	if options.batch then
		options.only = man.batches[options.batch] or error("unknown apron batch " .. tostring(options.batch))
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	if not world then
		error("PattayaApronBuilder: build the city first (PattayaBuilder.Build / Extend)")
	end
	local folder = world:FindFirstChild("ApronChunks")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "ApronChunks"
		folder.Parent = world
	end
	local root = folder :: Instance
	root:SetAttribute("Attribution", man.attribution)
	local apronStyle = style(man.apron, "Road", "Apron", Enum.Material.Asphalt)
	local cornerStyle = style(man.corner, "Sidewalk", "CornerFill", Enum.Material.Concrete)
	local wanted: {[string]: boolean} = {}
	for _, id in options.only or {} do
		wanted[id] = true
	end
	local built, parts = 0, 0
	for _, id in man.chunks do
		if (options.only == nil or wanted[id]) and not root:FindFirstChild("Chunk_" .. id) then
			local m = folderData:WaitForChild("chunk_" .. id) :: ModuleScript
			local d = require(m:Clone()) :: any
			local chunk = Instance.new("Model")
			chunk.Name = "Chunk_" .. id
			chunk.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
			local ap = Instance.new("Model")
			ap.Name = "Aprons"
			local co = Instance.new("Model")
			co.Name = "CornerFills"
			local n = buildTris(ap, d.aprons, apronStyle) + buildBoxes(ap, d.apronBoxes, apronStyle)
				+ buildTris(co, d.corners, cornerStyle) + buildBoxes(co, d.cornerBoxes, cornerStyle)
			ap.Parent = chunk
			co.Parent = chunk
			chunk:PivotTo(chunk:GetPivot() + Aprons.ORIGIN)
			if n ~= d.parts then
				warn(("apron chunk %s: %d parts built, data says %d"):format(id, n, d.parts))
			end
			parts += n
			chunk.Parent = root
			built += 1
			task.wait()
		end
	end
	return ("aprons: %d chunks built now (%d parts); %d chunks in manifest, %d built in total"):format(
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

-- Probe: for every built apron / corner part, the parts it overlaps (GetPartsInPart, exact geometry) other than road
-- surfaces (Road / Junction / Joint) and other aprons, its top height, and what a ray straight down at its centre hits
-- first. Wanted: obstacle hits 0 (buildings, props, furniture, landmarks...), aprons above the road top 0, corner fills
-- above the sidewalk top 0, corner fills inside a road surface 0, ray covered 0, parts = manifest counts.
function Aprons.Probe(opts: {folder: string?}?): string
	local options = (opts or {}) :: any
	local _, man = data(options.folder)
	local world = workspace:FindFirstChild("PattayaWorld")
	local root = world and world:FindFirstChild("ApronChunks")
	if not root then
		return "aprons probe: nothing built"
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = {root}
	params.RespectCanCollide = false
	local rp = RaycastParams.new()
	rp.FilterType = Enum.RaycastFilterType.Exclude
	rp.FilterDescendantsInstances = {}
	local stats = {aprons = 0, corners = 0, obstacleHits = 0, sidewalkHits = 0, cornerOnRoad = 0, apronAboveRoad = 0,
		cornerAboveCurb = 0, rayCovered = 0}
	local hitNames: {[string]: number} = {}
	local examples: {string} = {}
	for _, p in root:GetDescendants() do
		if p:IsA("BasePart") then
			local isApron = p:GetAttribute("Apron") == true
			if isApron then
				stats.aprons += 1
				if topY(p) > ROAD_TOP - 0.005 then
					stats.apronAboveRoad += 1
				end
			else
				stats.corners += 1
				if topY(p) > CURB_TOP - 0.005 then
					stats.cornerAboveCurb += 1
				end
			end
			local obstacle = false
			for _, q in workspace:GetPartsInPart(p, params) do
				if ROAD_NAMES[q.Name] then
					if not isApron then
						stats.cornerOnRoad += 1
					end
				elseif q.Name == "Sidewalk" then
					stats.sidewalkHits += 1
				elseif q.Name ~= "Centre" and q.Name ~= "Dash" and q.Name ~= "ZebraStripe" then
					obstacle = true
					hitNames[q.Name] = (hitNames[q.Name] or 0) + 1
				end
			end
			if obstacle then
				stats.obstacleHits += 1
				if #examples < 8 then
					table.insert(examples, ("%s J%s @ (%.0f, %.0f)"):format(p.Name, tostring(p:GetAttribute("JunctionId")), p.Position.X, p.Position.Z))
				end
			end
			-- the first collidable / queryable thing above the piece centre must be the piece itself or a road surface
			local c = p.Position
			local hit = workspace:Raycast(Vector3.new(c.X, 60, c.Z), Vector3.new(0, -70, 0), rp)
			if hit and hit.Instance ~= p and not ROAD_NAMES[hit.Instance.Name] and not hit.Instance:IsDescendantOf(root) then
				stats.rayCovered += 1
			end
		end
	end
	local names = {}
	for k, v in hitNames do
		table.insert(names, ("%s %d"):format(k, v))
	end
	table.sort(names)
	local c = man.counts
	local out = ("aprons probe: %d apron parts (data %d), %d corner parts (data %d); obstacle hits %d [%s]; sidewalk overlaps %d; "
		.. "corner parts on a road surface %d; aprons above road top %d; corner fills above sidewalk top %d; ray covered %d%s")
		:format(stats.aprons, c.apronParts, stats.corners, c.cornerParts, stats.obstacleHits, table.concat(names, ", "),
			stats.sidewalkHits, stats.cornerOnRoad, stats.apronAboveRoad, stats.cornerAboveCurb, stats.rayCovered,
			if #examples > 0 then "; e.g. " .. table.concat(examples, "; ") else "")
	print(out)
	return out
end

function Aprons.Remove(): string
	local world = workspace:FindFirstChild("PattayaWorld")
	local folder = world and world:FindFirstChild("ApronChunks")
	if not folder then
		return "aprons: nothing to remove"
	end
	local n = #folder:GetChildren()
	folder:Destroy()
	return ("aprons: removed %d chunks"):format(n)
end

return Aprons
