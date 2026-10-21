--!strict
-- Road visual pilot, design B (MIDNIGHT PATTAYA): the Sukhumvit / Pattaya Klang junction (world x 24220..24820,
-- z 650..1250) rebuilt from the road graph as one clean road surface: carriageway ribbons, kerb returns, islands,
-- kerbed sidewalks, continuous lane markings, stop lines and zebras on the junction legs. docs/ROAD_VISUAL_SPEC.md.
-- Data: ServerStorage.PattayaDataRoadVis (tools/roadvis/export_luau.py -> build/roadvis/roblox: manifest +
-- cell_<cx>_<cz>[_k], <= 600 parts each). Edit mode only. The pilot was built in Studio by the leader on 2026-10-22
-- (docs/test_results/road_b_pilot_studio.txt). CITY BATCHES (docs/ROAD_B_CITY_ROLLOUT.md): the same calls with a batch
-- id work on one batch of the whole-city rollout: RV.Plan("b001"), RV.Build("b001"), RV.MoveReplaced("b001"),
-- RV.Probe("b001"), RV.Remove("b001") (last in, first out), RV.Status(), RV.Leftovers(); data
-- ServerStorage.PattayaDataRoadVis_<id>, parts workspace.PattayaWorld.RoadVisCity.<id>, backup
-- ServerStorage.RoadVisCityBackup.<id>. The city mode has run OFFLINE only (luau CLI with stub Roblox types).
-- Without an id every call works on the pilot exactly as before.
--   local RV = require(game.ServerStorage.PattayaRoadVisBuilder)
--   RV.Plan()                 -- what Build would create and MoveReplaced would move (and whether the selection matches)
--   RV.Build()                -- workspace.PattayaWorld.RoadVisPilot (one Atomic Model per 256-stud cell)
--   RV.Build({mesh = true})   -- OPT-IN: invisible collision + EditableMesh visual MeshParts (see below)
--   RV.MoveReplaced()         -- moves the old road parts of the area to ServerStorage.RoadVisBackup (exact list check)
--   RV.Probe()                -- lane-centre support on every leg at offsets 0 / +-8 / +-14 / +-20 / +-24, buildings, counts
--   RV.Remove()               -- destroys RoadVisPilot and puts every backed-up part back (parent + CFrame), verified
--   RV.ShoulderLook({recolour = true, hideGapFills = true}) / RV.ShoulderLookRevert()   -- optional, owner-approved only
-- Default visual = the collision parts themselves, visible (asphalt "Road", "Sidewalk", "Island" WedgeParts) plus thin
-- non-colliding marking / kerb / grass Parts, plus invisible "RoadSupport" WedgeParts (Transparency 1, CanCollide and
-- CanQuery true, CanTouch false): road-height wheel support kept where an old part carried a wheel next to the new road. Why the default is Parts, not meshes: a MeshPart made from an
-- EditableMesh in Edit mode (AssetService:CreateEditableMesh + CreateMeshPartAsync(Content.fromObject(...))) lives in
-- memory only; its geometry is not saved with the place or published unless the mesh is uploaded as an asset, it
-- needs the EditableMesh API enabled for the experience and counts against the EditableMesh memory budget. Parts always
-- save, publish and stream. The mesh path is therefore an opt-in preview; it falls back to Parts when the API fails.
-- ShoulderChunks (the approved shoulder pilot) is never moved or destroyed by any function here; ShoulderLook only
-- changes Color / Material / Transparency (stored first as attributes) and keeps CanCollide.
local ServerStorage = game:GetService("ServerStorage")

local RV = {}

RV.ORIGIN = Vector3.new(20000, 0, 0) -- same as PattayaBuilder.ORIGIN
RV.FOLDER = "RoadVisPilot"
RV.DATA = "PattayaDataRoadVis"
RV.BACKUP = "RoadVisBackup"
local LABEL_OF_CODE = {"Road", "Sidewalk", "Dash", "Centre", "Junction", "Joint", "Apron", "CornerFill", "ZebraStripe"}
-- candidate containers (under workspace.PattayaWorld) and the part names / codes looked for in each
local CANDIDATES = {
	{folder = "WideChunks", names = {Road = 1, Sidewalk = 2, Dash = 3, Centre = 4}},
	{folder = "Chunks", names = {Road = 1, Sidewalk = 2, Dash = 3, Centre = 4}},
	{folder = "WideJunctions", names = {Junction = 5, Joint = 6}},
	{folder = "Junctions", names = {Junction = 5, Joint = 6}},
	{folder = "ApronChunks", names = {Road = 7, Sidewalk = 8}},
	{folder = "FurnitureChunks", names = {ZebraStripe = 9}},
}
local TRI_KIND = {"asphalt", "sidewalk", "island", "grass", "support"}
local TRI_NAME = {"Road", "Sidewalk", "Island", "Grass", "RoadSupport"}
local SEG_KIND = {"lane", "centre", "edge", "stop", "zebra", "kerb"}
local SEG_NAME = {"Dash", "Centre", "EdgeLine", "StopLine", "ZebraStripe", "Kerb"}

local function rgb(c: {number}): Color3
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function data(): (Instance, any)
	-- FindFirstChild, not WaitForChild: a missing data folder must fail at once, not yield forever in the command bar
	local d = ServerStorage:FindFirstChild(RV.DATA)
	local m = if d then d:FindFirstChild("manifest") :: ModuleScript? else nil
	if not (d and m) then
		error("PattayaRoadVisBuilder: ServerStorage." .. RV.DATA .. ".manifest not found (the pilot data is not installed; a city batch "
			.. "takes its id, e.g. RV.Plan(\"b001\"))")
	end
	return d :: Instance, require((m :: ModuleScript):Clone()) :: any -- Clone(): never served from the require cache
end

local function moduleData(d: Instance, name: string): any
	-- FindFirstChild, not WaitForChild: a module missing from a half-done install must fail at once, not yield forever
	local m = d:FindFirstChild(name) :: ModuleScript?
	if not m then
		error(("PattayaRoadVisBuilder: %s.%s not found (install every data module of the manifest)"):format(d:GetFullName(), name))
	end
	return require((m :: ModuleScript):Clone()) :: any
end

local function world(): Instance
	local w = workspace:FindFirstChild("PattayaWorld")
	if not w then
		error("PattayaRoadVisBuilder: workspace.PattayaWorld not found")
	end
	return w :: Instance
end

local function finish(p: BasePart, name: string, color: Color3, material: Enum.Material, collide: boolean, transparency: number,
	kind: string, parent: Instance, attrs: {[string]: any}?)
	p.Name = name
	p.Anchored = true
	p.Color = color
	p.Material = material
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.CanCollide = collide
	p.CanQuery = collide -- markings / kerb / grass stay out of the car's suspension rays
	p.CanTouch = false
	p.CastShadow = false
	p.Transparency = transparency
	p:SetAttribute("RoadVis", true)
	p:SetAttribute("RoadVisKind", kind)
	if attrs then -- city batches: RoadVisBatch (the batch that built it), RoadVisFor (a frontier piece: the batch that replaces it)
		for k, v in attrs do
			p:SetAttribute(k, v)
		end
	end
	p.Parent = parent
end

-- one flat triangle a-b-c (world x / z) from two WedgeParts split at the foot of the altitude on the longest side,
-- exactly as PattayaBuilder.roadTriangle; top / thick per layer
local function triangle(parent: Instance, a: Vector2, b: Vector2, c: Vector2, top: number, thick: number, name: string,
	color: Color3, material: Enum.Material, collide: boolean, transparency: number, kind: string, attrs: {[string]: any}?): number
	local ab, bc, ca = (b - a).Magnitude, (c - b).Magnitude, (a - c).Magnitude
	if bc > ab and bc >= ca then
		a, b, c = b, c, a
	elseif ca > ab and ca > bc then
		a, b, c = c, a, b
	end
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
	local y = top - thick / 2
	local yv = Vector3.new(c.X - foot.X, 0, c.Y - foot.Y) / h
	local n = 0
	for _, corner in {a, b} do
		local l = (foot - corner).Magnitude
		if l > 0.05 then
			local zv = Vector3.new(foot.X - corner.X, 0, foot.Y - corner.Y) / l
			local xv = yv:Cross(zv)
			local centre = foot + Vector2.new(yv.X, yv.Z) * (h / 2) - Vector2.new(zv.X, zv.Z) * (l / 2)
			local w = Instance.new("WedgePart")
			w.Size = Vector3.new(thick, h, l)
			w.CFrame = CFrame.fromMatrix(Vector3.new(centre.X, y, centre.Y), xv, yv, zv)
			finish(w, name, color, material, collide, transparency, kind, parent, attrs)
			n += 1
		end
	end
	return n
end

local function segment(parent: Instance, a: Vector2, b: Vector2, width: number, top: number, thick: number, name: string,
	color: Color3, kind: string, attrs: {[string]: any}?): number
	local len = (b - a).Magnitude
	if len < 0.05 then
		return 0
	end
	local mid = (a + b) / 2
	local y = top - thick / 2
	local p = Instance.new("Part")
	p.Size = Vector3.new(width, thick, len)
	p.CFrame = CFrame.lookAt(Vector3.new(mid.X, y, mid.Y), Vector3.new(b.X, y, b.Y))
	finish(p, name, color, Enum.Material.SmoothPlastic, false, 0, kind, parent, attrs)
	return 1
end

-- ---- footprints and the replace rule (same rule as tools/roadvis/export_luau.replace_rule) ---------------------------
-- the part's footprint box: spanned by its two most horizontal axes (a slab / dash / zebra: its rectangle; a WedgePart:
-- the rectangle around its triangle; a disc Cylinder: its square). Returns centre (x, z) and 4 corners {x, z}.
local function footprint(p: BasePart): (Vector2, {Vector2})
	local cf, s = p.CFrame, p.Size
	local axes = {cf.XVector * s.X, cf.YVector * s.Y, cf.ZVector * s.Z}
	local units = {cf.XVector, cf.YVector, cf.ZVector}
	local up, best = 1, -1
	for i = 1, 3 do
		local v = math.abs(units[i].Y)
		if v > best then
			up, best = i, v
		end
	end
	local h = {}
	for i = 1, 3 do
		if i ~= up then
			table.insert(h, axes[i])
		end
	end
	local c = cf.Position
	local A, B = h[1] / 2, h[2] / 2
	local pts = {}
	for _, sg in {{1, 1}, {1, -1}, {-1, -1}, {-1, 1}} do
		local q = c + A * sg[1] + B * sg[2]
		table.insert(pts, Vector2.new(q.X, q.Z))
	end
	return Vector2.new(c.X, c.Z), pts
end

local function area(poly: {Vector2}): number
	local s = 0
	for i = 1, #poly do
		local a, b = poly[i], poly[i % #poly + 1]
		s += a.X * b.Y - b.X * a.Y
	end
	return math.abs(s) / 2
end

-- Sutherland-Hodgman clip of a convex polygon to the box x0..x1, z0..z1
local function clip(poly: {Vector2}, x0: number, z0: number, x1: number, z1: number): {Vector2}
	local function cut(pts: {Vector2}, inside: (Vector2) -> boolean, cross: (Vector2, Vector2) -> Vector2): {Vector2}
		local out = {}
		for i = 1, #pts do
			local a, b = pts[i], pts[i % #pts + 1]
			local ia, ib = inside(a), inside(b)
			if ia then
				table.insert(out, a)
			end
			if ia ~= ib then
				table.insert(out, cross(a, b))
			end
		end
		return out
	end
	local function atX(x: number): (Vector2, Vector2) -> Vector2
		return function(a: Vector2, b: Vector2): Vector2
			local t = (x - a.X) / (b.X - a.X)
			return Vector2.new(x, a.Y + (b.Y - a.Y) * t)
		end
	end
	local function atZ(z: number): (Vector2, Vector2) -> Vector2
		return function(a: Vector2, b: Vector2): Vector2
			local t = (z - a.Y) / (b.Y - a.Y)
			return Vector2.new(a.X + (b.X - a.X) * t, z)
		end
	end
	local p = poly
	p = cut(p, function(q) return q.X >= x0 end, atX(x0))
	if #p == 0 then return p end
	p = cut(p, function(q) return q.X <= x1 end, atX(x1))
	if #p == 0 then return p end
	p = cut(p, function(q) return q.Y >= z0 end, atZ(z0))
	if #p == 0 then return p end
	p = cut(p, function(q) return q.Y <= z1 end, atZ(z1))
	return p
end

local function inShoulders(p: Instance, w: Instance): boolean
	local sc = w:FindFirstChild("ShoulderChunks")
	return (sc ~= nil and p:IsDescendantOf(sc)) or p:GetAttribute("Shoulder") == true
end

-- every candidate part the rule selects: {{part, code}}
local function selectReplaced(man: any): {{part: BasePart, code: number}}
	local w = world()
	local x0, z0, x1, z1 = man.bbox[1], man.bbox[2], man.bbox[3], man.bbox[4]
	local out = {}
	for _, cand in CANDIDATES do
		local f = w:FindFirstChild(cand.folder)
		if f then
			for _, d in f:GetDescendants() do
				if d:IsA("BasePart") and cand.names[d.Name] and not inShoulders(d, w) and d:GetAttribute("RoadVis") == nil then
					local p = d :: BasePart
					local c, pts = footprint(p)
					if c.X > x0 and c.X < x1 and c.Y > z0 and c.Y < z1 then
						local full = area(pts)
						if full > 0 and area(clip(pts, x0, z0, x1, z1)) >= 0.5 * full - 1e-6 then
							local code = cand.names[d.Name]
							if code == 1 and p:GetAttribute("Apron") == true then
								code = 7
							end
							table.insert(out, {part = p, code = code})
						end
					end
				end
			end
		end
	end
	return out
end

-- compares the selection with the manifest's expected list: every selected part must match an expected key (code,
-- world x, z within tolerance) one to one. Returns ok, report.
local function matchExpected(man: any, sel: {{part: BasePart, code: number}}): (boolean, string)
	local keys = man.replace.keys
	local tol = man.replace.tolerance or 0.3
	local grid: {[string]: {number}} = {}
	local used: {[number]: boolean} = {}
	local function key(code: number, x: number, z: number): string
		return code .. ":" .. math.floor(x / 4) .. ":" .. math.floor(z / 4)
	end
	for i = 1, #keys, 3 do
		local k = key(keys[i], keys[i + 1], keys[i + 2])
		grid[k] = grid[k] or {}
		table.insert(grid[k], i)
	end
	local unmatched = {}
	for _, s in sel do
		local c = footprint(s.part)
		local found = nil
		for dx = -1, 1 do
			for dz = -1, 1 do
				local list = grid[s.code .. ":" .. (math.floor(c.X / 4) + dx) .. ":" .. (math.floor(c.Y / 4) + dz)]
				if list and not found then
					for _, i in list do
						if not used[i] and math.abs(keys[i + 1] - c.X) <= tol and math.abs(keys[i + 2] - c.Y) <= tol then
							found = i
							break
						end
					end
				end
			end
		end
		if found then
			used[found] = true
		else
			table.insert(unmatched, ("%s %s at (%.1f, %.1f)"):format(LABEL_OF_CODE[s.code], s.part:GetFullName(), c.X, c.Y))
		end
	end
	local missing = 0
	for i = 1, #keys, 3 do
		if not used[i] then
			missing += 1
		end
	end
	local ok = #sel == man.replace.total and #unmatched == 0 and missing == 0
	local report = ("selected %d, expected %d; unmatched selected %d, expected but not found %d%s"):format(#sel,
		man.replace.total, #unmatched, missing, if #unmatched > 0 then " [" .. table.concat(unmatched, "; ", 1, math.min(5, #unmatched)) .. "]" else "")
	return ok, report
end

local function countByLabel(sel: {{part: BasePart, code: number}}): string
	local c = {}
	for _, s in sel do
		local l = LABEL_OF_CODE[s.code]
		c[l] = (c[l] or 0) + 1
	end
	local out = {}
	for _, l in LABEL_OF_CODE do
		if c[l] then
			table.insert(out, l .. " " .. c[l])
			c[l] = nil
		end
	end
	return table.concat(out, ", ")
end

local function pilotPlan(): string
	local _, man = data()
	local w = workspace:FindFirstChild("PattayaWorld")
	local lines = {("road vis plan: %d modules, %d cells, %d parts to build (fallback Parts); %d mesh triangles (opt-in)"):format(
		#man.modules, #man.cells, man.counts.parts, man.counts.meshTriangles)}
	if w then
		local sel = selectReplaced(man)
		local ok, rep = matchExpected(man, sel)
		table.insert(lines, ("move plan: %s -> %s; %s"):format(countByLabel(sel), if ok then "MATCHES the data" else "DOES NOT MATCH (MoveReplaced would abort)", rep))
		table.insert(lines, ("pilot built: %s; backup present: %s"):format(tostring(w:FindFirstChild(RV.FOLDER) ~= nil),
			tostring(ServerStorage:FindFirstChild(RV.BACKUP) ~= nil)))
	else
		table.insert(lines, "PattayaWorld not found: nothing to move")
	end
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

-- ---- Build ----------------------------------------------------------------------------------------------------------
local function tryMesh(): any
	local ok, svc = pcall(function()
		return game:GetService("AssetService")
	end)
	if not ok or svc == nil then
		return nil
	end
	local s = svc :: any
	if typeof(s.CreateEditableMesh) ~= "function" or typeof(s.CreateMeshPartAsync) ~= "function" then
		return nil
	end
	return s
end

local function meshLayer(svc: any, rows: {number}, layer: number, top: number, origin: Vector3): any
	local em = svc:CreateEditableMesh()
	local n = 0
	for i = 1, #rows, 7 do
		if rows[i + 6] == layer then
			local a = em:AddVertex(Vector3.new(rows[i], top, rows[i + 1]) + origin)
			local b = em:AddVertex(Vector3.new(rows[i + 2], top, rows[i + 3]) + origin)
			local c = em:AddVertex(Vector3.new(rows[i + 4], top, rows[i + 5]) + origin)
			em:AddTriangle(a, c, b)
			n += 1
		end
	end
	if n == 0 then
		return nil
	end
	return svc:CreateMeshPartAsync(Content.fromObject(em))
end

local function pilotBuild(opts: {mesh: boolean?}?): string
	local options = (opts or {}) :: any
	local d, man = data()
	local w = world()
	if w:FindFirstChild(RV.FOLDER) then
		return "road vis: RoadVisPilot already exists (RV.Remove() first)"
	end
	local svc = if options.mesh then tryMesh() else nil
	if options.mesh and svc == nil then
		warn("road vis: EditableMesh / CreateMeshPartAsync not available in this session: building the Parts fallback")
	end
	local useMesh = svc ~= nil
	local root = Instance.new("Folder")
	root.Name = RV.FOLDER
	root:SetAttribute("Attribution", man.attribution)
	root:SetAttribute("Mode", if useMesh then "mesh" else "parts")
	local T, C, K = man.tops, man.colors, man.thick
	local O = RV.ORIGIN
	local cells: {[string]: Model} = {}
	local parts, wrong = 0, 0
	local mats = {Enum.Material.Asphalt, Enum.Material.Concrete, Enum.Material.Concrete, Enum.Material.Grass, Enum.Material.Asphalt}
	local tops = {T.asphalt, T.sidewalk, T.island, T.grass, T.support or T.asphalt}
	local thick = {K.asphalt, K.sidewalk, K.island, K.grass, K.support or K.asphalt}
	local colors = {rgb(C.asphalt), rgb(C.sidewalk), rgb(C.island), rgb(C.grass), rgb(C.asphalt)}
	local segColor = {rgb(C.white), rgb(C.yellow), rgb(C.white), rgb(C.white), rgb(C.white), rgb(C.kerb)}
	for _, name in man.modules do
		local m = moduleData(d, name)
		local cell = cells[m.cell]
		if not cell then
			cell = Instance.new("Model")
			cell.Name = "Cell_" .. m.cell
			cell.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
			cells[m.cell] = cell
		end
		local n = 0
		local t = m.tris
		for i = 1, #t, 7 do
			local k = t[i + 6]
			local collide = k ~= 4 -- grass is the only visual-only triangle
			if useMesh and k == 4 then
				continue -- grass is in the mesh
			end
			-- kind 5: invisible wheel support (always Transparency 1; CanCollide / CanQuery true so the suspension rays
			-- see it; CanTouch false): keeps the support an old part gave a wheel next to the new road, never visible
			local invisible = k == 5 or (useMesh and collide)
			local nm = if k == 5 then TRI_NAME[k] elseif useMesh and collide then TRI_NAME[k] .. "Collision" else TRI_NAME[k]
			n += triangle(cell, Vector2.new(t[i] + O.X, t[i + 1] + O.Z), Vector2.new(t[i + 2] + O.X, t[i + 3] + O.Z),
				Vector2.new(t[i + 4] + O.X, t[i + 5] + O.Z), tops[k], thick[k], nm, colors[k], mats[k], collide,
				if invisible then 1 else 0, TRI_KIND[k])
		end
		if not useMesh then
			local s = m.segs
			for i = 1, #s, 6 do
				local k = s[i + 5]
				local top = if k == 6 then T.kerb else T.mark
				local th = if k == 6 then K.kerb else K.mark
				n += segment(cell, Vector2.new(s[i] + O.X, s[i + 1] + O.Z), Vector2.new(s[i + 2] + O.X, s[i + 3] + O.Z), s[i + 4], top, th,
					SEG_NAME[k], segColor[k], SEG_KIND[k])
			end
		end
		if not useMesh and n ~= m.parts then
			wrong += 1
			warn(("road vis module %s: %d parts built, data says %d"):format(name, n, m.parts))
		end
		if useMesh and #m.mesh > 0 then
			local layerTop = {T.asphalt + T.meshLift, T.sidewalk + 0.004, T.kerb, T.island + 0.004, T.grass, T.mark, T.mark}
			local layerColor = {rgb(C.asphalt), rgb(C.sidewalk), rgb(C.kerb), rgb(C.island), rgb(C.grass), rgb(C.white), rgb(C.yellow)}
			for layer = 1, 7 do
				local ok, mp = pcall(meshLayer, svc, m.mesh, layer, layerTop[layer], Vector3.new(O.X, 0, O.Z))
				if ok and mp then
					local mpart = mp :: BasePart
					finish(mpart, "RoadVisMesh", layerColor[layer], Enum.Material.SmoothPlastic, false, 0, "mesh" .. layer, cell)
					n += 1
				elseif not ok then
					warn("road vis: mesh layer failed: " .. tostring(mp))
				end
			end
		end
		parts += n
		task.wait()
	end
	for _, id in man.cells do
		if cells[id] then
			cells[id].Parent = root
		end
	end
	root.Parent = w
	return ("road vis: built %d cells, %d parts (%s)%s"):format(#root:GetChildren(), parts, if useMesh then "mesh visual" else "Parts",
		if wrong > 0 then (", %d modules with a part-count mismatch"):format(wrong) else "")
end

-- ---- MoveReplaced / Remove --------------------------------------------------------------------------------------
local function pilotMoveReplaced(): string
	local _, man = data()
	local w = world()
	if ServerStorage:FindFirstChild(RV.BACKUP) then
		return "road vis: RoadVisBackup already exists: nothing moved (run RV.Remove() to restore first)"
	end
	local sel = selectReplaced(man)
	local ok, report = matchExpected(man, sel)
	if not ok then
		local msg = "road vis: ABORTED, nothing moved: the selection does not match the data (" .. report .. ")"
		warn(msg)
		return msg
	end
	for _, s in sel do -- second safety net: never a shoulder part
		if inShoulders(s.part, w) then
			return "road vis: ABORTED, a ShoulderChunks part was selected (" .. s.part:GetFullName() .. ")"
		end
	end
	local backup = Instance.new("Folder")
	backup.Name = RV.BACKUP
	local groups: {[Instance]: Folder} = {}
	local n = 0
	for _, s in sel do
		local p = s.part
		local parent = p.Parent :: Instance
		local g = groups[parent]
		if not g then
			local f = Instance.new("Folder")
			f.Name = "From_" .. tostring(n)
			local ref = Instance.new("ObjectValue")
			ref.Name = "OriginalParentRef"
			ref.Value = parent
			ref.Parent = f
			f:SetAttribute("OriginalParent", parent:GetFullName())
			f.Parent = backup
			groups[parent] = f
			g = f
		end
		p:SetAttribute("OriginalParent", parent:GetFullName())
		p:SetAttribute("OriginalCFrame", p.CFrame)
		p:SetAttribute("RoadVisMoved", LABEL_OF_CODE[s.code])
		p.Parent = g
		n += 1
	end
	backup:SetAttribute("Count", n)
	backup.Parent = ServerStorage
	return ("road vis: moved %d parts (%s) to ServerStorage.%s; %s"):format(n, countByLabel(sel), RV.BACKUP, report)
end

local function pilotRemove(): string
	local w = world()
	local removed = false
	local pilot = w:FindFirstChild(RV.FOLDER)
	if pilot then
		pilot:Destroy()
		removed = true
	end
	local backup = ServerStorage:FindFirstChild(RV.BACKUP)
	if not backup then
		return ("road vis: pilot %s; no backup to restore"):format(if removed then "removed" else "not built")
	end
	local expected = backup:GetAttribute("Count") or -1
	local restored, failed = 0, 0
	for _, g in backup:GetChildren() do
		local ref = g:FindFirstChild("OriginalParentRef") :: ObjectValue?
		local target = ref and ref.Value
		for _, p in g:GetChildren() do
			if p:IsA("BasePart") then
				if target and target.Parent then
					local cf = p:GetAttribute("OriginalCFrame")
					if typeof(cf) == "CFrame" then
						(p :: BasePart).CFrame = cf
					end
					p:SetAttribute("OriginalParent", nil)
					p:SetAttribute("OriginalCFrame", nil)
					p:SetAttribute("RoadVisMoved", nil)
					p.Parent = target
					restored += 1
				else
					failed += 1
				end
			end
		end
	end
	if restored == expected and failed == 0 then
		backup:Destroy()
		return ("road vis: pilot %s; restored %d of %d parts to their original parents; backup removed"):format(
			if removed then "removed" else "not built", restored, expected)
	end
	local msg = ("road vis: pilot %s; restored %d of %d parts, %d could not be restored (original parent gone): backup KEPT"):format(
		if removed then "removed" else "not built", restored, expected, failed)
	warn(msg)
	return msg
end

-- ---- Probe ------------------------------------------------------------------------------------------------------
-- lane-centre support: per probe sample (every 4 studs on every leg outside the seam band) and offset (only where the
-- offset lies on the carriageway, |o| <= half width), a 4 x 9 car footprint (6 points) is raycast straight down: flat =
-- every point hits a top in 0.9..1.1 (road, shoulder, apron), kerb = a point hits 1.1..1.8 (sidewalk / island, no
-- drop), drop = a point hits nothing or lower, blocked = higher (a building or prop on the road). A drop point whose
-- 4 neighbour rays 0.05 stud away all hit road is a hairline seam (a float32 crack between two coplanar wedges; Studio
-- 2026-10-22, sample 220 at (24504.9, 1045.4)), counted apart, not as a drop. Plus: pilot parts overlapping a building,
-- counts. The manifest holds the offline expectation for the same samples.
local function pilotProbe(): string
	local _, man = data()
	local w = world()
	local pilot = w:FindFirstChild(RV.FOLDER)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = {}
	local O = RV.ORIGIN
	local S = man.probe.samples
	local fw, fl = man.probe.foot[1] / 2, man.probe.foot[2] / 2
	local pts = {{-fl, -fw}, {-fl, fw}, {fl, -fw}, {fl, fw}, {0, -fw}, {0, fw}}
	local lines = {}
	local totalDrop, totalSeam = 0, 0
	local dropAt = {}
	local function topAt(x: number, z: number): number
		local hit = workspace:Raycast(Vector3.new(x, 40, z), Vector3.new(0, -60, 0), params)
		return if hit then hit.Position.Y else -math.huge
	end
	-- a hairline seam, not a hole: the ray went through a float32 crack between two coplanar WedgeParts (world x about
	-- 24,500: positions step by 0.002 studs), and 4 rays 0.05 stud around it all hit a road-height top
	local function seam(x: number, z: number): boolean
		for _, d in {{0.05, 0}, {-0.05, 0}, {0, 0.05}, {0, -0.05}} do
			local y = topAt(x + d[1], z + d[2])
			if y < 0.9 or y > 1.1 then
				return false
			end
		end
		return true
	end
	for _, o in man.probe.offsets do
		local n, flat, kerb, drop, blocked, seams = 0, 0, 0, 0, 0, 0
		for i = 1, #S, 6 do
			local hw = S[i + 4]
			if math.abs(o) <= hw then
				local cx, cz, tx, tz = S[i] + O.X, S[i + 1] + O.Z, S[i + 2], S[i + 3]
				local nx, nz = -tz, tx
				local worst = "flat"
				for _, q in pts do
					local x = cx + nx * (o + q[2]) + tx * q[1]
					local z = cz + nz * (o + q[2]) + tz * q[1]
					local y = topAt(x, z)
					local cls = if y > 1.8 then "blocked" elseif y > 1.1 then "kerb" elseif y >= 0.9 then "flat" else "drop"
					if cls == "drop" and seam(x, z) then
						cls = "flat"
						seams += 1
					elseif cls == "drop" and #dropAt < 5 then
						table.insert(dropAt, ("(%.1f, %.1f) offset %d"):format(x, z, o))
					end
					if cls == "drop" or (cls == "blocked" and worst ~= "drop") or (cls == "kerb" and worst == "flat") then
						worst = cls
					end
				end
				n += 1
				if worst == "flat" then flat += 1 elseif worst == "kerb" then kerb += 1 elseif worst == "drop" then drop += 1 else blocked += 1 end
			end
		end
		totalDrop += drop
		totalSeam += seams
		local e = man.probe.expected[tostring(o)]
		table.insert(lines, ("offset %d: %d samples, flat %d, kerb %d, drop %d, blocked %d, hairline seams %d (offline expected: drop %d, kerb %d)"):format(
			o, n, flat, kerb, drop, blocked, seams, e and e.drop or -1, e and e.kerb or -1))
	end
	if #dropAt > 0 then
		table.insert(lines, "first drops at " .. table.concat(dropAt, "; "))
	end
	local bHits, built = 0, 0
	if pilot then
		local op = OverlapParams.new()
		for _, p in pilot:GetDescendants() do
			if p:IsA("BasePart") then
				built += 1
				if (p :: BasePart).CanCollide then
					for _, hit in workspace:GetPartsInPart(p :: BasePart, op) do
						if hit:GetAttribute("OsmBuilding") ~= nil then
							bHits += 1
							break
						end
					end
				end
			end
		end
	end
	local backup = ServerStorage:FindFirstChild(RV.BACKUP)
	local head = ("road vis probe: %d legs, %d samples; pilot parts %d (data %d); building overlaps %d; moved parts %s; total drops %d; hairline seams %d"):format(
		#man.probe.legs, #S // 6, built, man.counts.parts, bHits, if backup then tostring(backup:GetAttribute("Count")) else "none", totalDrop, totalSeam)
	local out = head .. "\n" .. table.concat(lines, "\n")
	print(out)
	return out
end

-- ==== CITY BATCHES (docs/ROAD_B_CITY_ROLLOUT.md) =====================================================================
-- Every function above with a batch id ("b001", ...) works on that batch: data ServerStorage.PattayaDataRoadVis_<id>
-- (tools/roadvis/city_cli.py -> build/roadcity/<id>/roblox_rv), parts in workspace.PattayaWorld.RoadVisCity.<id> (one
-- Atomic Model per 256-stud cell), backup ServerStorage.RoadVisCityBackup.<id>. Without an id (or "pilot") they work on
-- the pilot exactly as before (RoadVisPilot / PattayaDataRoadVis / RoadVisBackup).
-- Who owns an old part: the first batch built over it. MoveReplaced(<id>) takes every old road-layer part (the same
-- containers and names as the pilot), every RoadVisPilot part, whose footprint centre lies in the batch box (x0 <= x <
-- x1, z0 <= z < z1) or which overlaps the box by manifest.batch.overlapMin studs^2 or more, plus every frontier piece an
-- earlier batch built for this box (attribute RoadVisFor = <id>). The part of a replaced footprint outside the box is
-- rebuilt by Build as frontier pieces (RoadVisFor = the batch of that box). The data is made for one build order:
-- Plan / Build / MoveReplaced check that every batch in manifest.batch.builtBefore is built and no later one is.
-- Remove(<id>) is last-in first-out: it refuses while a later neighbour is built or holds this batch's pieces.
RV.CITY_FOLDER = "RoadVisCity"
RV.CITY_BACKUP = "RoadVisCityBackup"
RV.CITY_DATA_PREFIX = "PattayaDataRoadVis_"
local RV_CODE_TRI = {asphalt = 11, sidewalk = 12, island = 13, grass = 14, support = 15}
local RV_CODE_SEG = {lane = 21, centre = 22, edge = 23, stop = 24, zebra = 25, kerb = 26}
local CITY_LABEL = {[11] = "RV Road", [12] = "RV Sidewalk", [13] = "RV Island", [14] = "RV Grass", [15] = "RV RoadSupport",
	[21] = "RV Dash", [22] = "RV Centre", [23] = "RV EdgeLine", [24] = "RV StopLine", [25] = "RV ZebraStripe", [26] = "RV Kerb"}

local function isCity(id: any): boolean
	return type(id) == "string" and id ~= "" and id ~= "pilot"
end

local function cityData(id: string): (Instance, any)
	local d = ServerStorage:FindFirstChild(RV.CITY_DATA_PREFIX .. id)
	if not d then
		error("PattayaRoadVisBuilder: ServerStorage." .. RV.CITY_DATA_PREFIX .. id .. " not found (install the batch data first)")
	end
	local m = d:FindFirstChild("manifest") :: ModuleScript?
	if not m then
		error("PattayaRoadVisBuilder: ServerStorage." .. RV.CITY_DATA_PREFIX .. id .. ".manifest not found (install the batch data first)")
	end
	return d :: Instance, require((m :: ModuleScript):Clone()) :: any -- Clone(): never served from the require cache
end

local function cityRoot(create: boolean): Instance?
	local w = world()
	local r = w:FindFirstChild(RV.CITY_FOLDER)
	if not r and create then
		local f = Instance.new("Folder")
		f.Name = RV.CITY_FOLDER
		f:SetAttribute("Attribution", "Map data (c) OpenStreetMap contributors, ODbL 1.0")
		f.Parent = w
		r = f
	end
	return r
end

local function builtFolder(id: string): Instance?
	local w = workspace:FindFirstChild("PattayaWorld")
	if not w then
		return nil
	end
	if id == "pilot" then
		return w:FindFirstChild(RV.FOLDER)
	end
	local r = w:FindFirstChild(RV.CITY_FOLDER)
	return if r then r:FindFirstChild(id) else nil
end

-- the build order the data was made for: every batch in builtBefore built, no later batch built
local function orderCheck(man: any): (boolean, string)
	local missing, extra = {}, {}
	local before: {[string]: boolean} = {}
	for _, id in man.batch.builtBefore do
		before[id] = true
		if not builtFolder(id) then
			table.insert(missing, id)
		end
	end
	local r = cityRoot(false)
	if r then
		for _, f in r:GetChildren() do
			if f.Name ~= man.batch.id and not before[f.Name] then
				table.insert(extra, f.Name)
			end
		end
	end
	local ok = #missing == 0 and #extra == 0
	local msg = ("build order: %d batches must be built before %s: %s"):format(#man.batch.builtBefore, man.batch.id,
		if #missing == 0 then "all built" else ("NOT built: %s"):format(table.concat(missing, ", ", 1, math.min(8, #missing))))
	if #extra > 0 then
		msg ..= ("; built but made LATER in the plan (the data assumes they are not): %s"):format(table.concat(extra, ", ", 1, math.min(8, #extra)))
	end
	return ok, msg
end

-- Road B parts: replace code from the RoadVisKind attribute
local function rvCode(p: Instance): number?
	local k = p:GetAttribute("RoadVisKind")
	if type(k) ~= "string" then
		return nil
	end
	return RV_CODE_TRI[k] or RV_CODE_SEG[k]
end

-- a Road B part's exact footprint: the triangle of a WedgePart (corner, foot, apex: the builder's `triangle`), the
-- rectangle of a marking Part
local function rvFootprint(p: BasePart): (Vector2, {Vector2})
	if p:IsA("WedgePart") then
		local cf, s = p.CFrame, p.Size
		local c = cf.Position
		local Y, Z = cf.YVector * (s.Y / 2), cf.ZVector * (s.Z / 2)
		local a, b, d = c - Y - Z, c - Y + Z, c + Y + Z
		return Vector2.new(c.X, c.Z), {Vector2.new(a.X, a.Z), Vector2.new(b.X, b.Z), Vector2.new(d.X, d.Z)}
	end
	return footprint(p)
end

local function takes(man: any, c: Vector2, pts: {Vector2}): boolean
	local b = man.batch.box
	local x0, z0, x1, z1 = b[1], b[2], b[3], b[4]
	if c.X >= x0 and c.X < x1 and c.Y >= z0 and c.Y < z1 then
		return true
	end
	local minx, maxx, minz, maxz = math.huge, -math.huge, math.huge, -math.huge
	for _, q in pts do
		minx, maxx = math.min(minx, q.X), math.max(maxx, q.X)
		minz, maxz = math.min(minz, q.Y), math.max(maxz, q.Y)
	end
	if maxx <= x0 or minx >= x1 or maxz <= z0 or minz >= z1 then
		return false
	end
	return area(clip(pts, x0, z0, x1, z1)) >= man.batch.overlapMin - 1e-6
end

-- every part MoveReplaced(<id>) would move: {{part, code}}
local function selectCity(man: any): {{part: BasePart, code: number}}
	local w = world()
	local out = {}
	for _, cand in CANDIDATES do
		local f = w:FindFirstChild(cand.folder)
		if f then
			for _, d in f:GetDescendants() do
				if d:IsA("BasePart") and cand.names[d.Name] and not inShoulders(d, w) and d:GetAttribute("RoadVis") == nil then
					local p = d :: BasePart
					local c, pts = footprint(p)
					if takes(man, c, pts) then
						local code = cand.names[d.Name]
						if code == 1 and p:GetAttribute("Apron") == true then
							code = 7
						end
						table.insert(out, {part = p, code = code})
					end
				end
			end
		end
	end
	local pilot = w:FindFirstChild(RV.FOLDER)
	if pilot then
		for _, d in pilot:GetDescendants() do
			if d:IsA("BasePart") and d:GetAttribute("RoadVis") == true then
				local code = rvCode(d)
				if code then
					local c, pts = rvFootprint(d :: BasePart)
					if takes(man, c, pts) then
						table.insert(out, {part = d :: BasePart, code = code})
					end
				end
			end
		end
	end
	local root = w:FindFirstChild(RV.CITY_FOLDER)
	if root then
		for _, d in root:GetDescendants() do
			if d:IsA("BasePart") and d:GetAttribute("RoadVisFor") == man.batch.id then
				local code = rvCode(d)
				if code then
					table.insert(out, {part = d :: BasePart, code = code})
				end
			end
		end
	end
	return out
end

-- every selected part must match a required or an optional key (code, world x / z within tolerance), one to one, and
-- every required key must be matched. Optional keys: parts whose overlap with a box is within the data's tolerance of
-- the threshold (or whose centre lies on a box edge), so Studio's float32 positions may decide either way.
local function matchCity(man: any, sel: {{part: BasePart, code: number}}): (boolean, string)
	local tol = man.replace.tolerance or 0.3
	local function index(keys: {number}): {[string]: {number}}
		local g: {[string]: {number}} = {}
		for i = 1, #keys, 3 do
			local k = keys[i] .. ":" .. math.floor(keys[i + 1] / 4) .. ":" .. math.floor(keys[i + 2] / 4)
			g[k] = g[k] or {}
			table.insert(g[k], i)
		end
		return g
	end
	local req, opt = man.replace.keys, man.replace.optionalKeys or {}
	local greq, gopt = index(req), index(opt)
	local usedR, usedO = {}, {}
	local unmatched = {}
	local function find(keys: {number}, g: {[string]: {number}}, used: {[number]: boolean}, code: number, c: Vector2): number?
		for dx = -1, 1 do
			for dz = -1, 1 do
				local list = g[code .. ":" .. (math.floor(c.X / 4) + dx) .. ":" .. (math.floor(c.Y / 4) + dz)]
				if list then
					for _, i in list do
						if not used[i] and math.abs(keys[i + 1] - c.X) <= tol and math.abs(keys[i + 2] - c.Y) <= tol then
							return i
						end
					end
				end
			end
		end
		return nil
	end
	local nOpt = 0
	for _, s in sel do
		local c = s.part.Position
		local cc = Vector2.new(c.X, c.Z)
		local i = find(req, greq, usedR, s.code, cc)
		if i then
			usedR[i] = true
		else
			local j = find(opt, gopt, usedO, s.code, cc)
			if j then
				usedO[j] = true
				nOpt += 1
			else
				table.insert(unmatched, ("%s %s at (%.1f, %.1f)"):format(LABEL_OF_CODE[s.code] or CITY_LABEL[s.code] or tostring(s.code),
					s.part:GetFullName(), cc.X, cc.Y))
			end
		end
	end
	local missing = 0
	for i = 1, #req, 3 do
		if not usedR[i] then
			missing += 1
		end
	end
	local ok = #unmatched == 0 and missing == 0
	return ok, ("selected %d (required keys %d, optional keys %d of %d matched); unmatched selected %d, required but not found %d%s"):format(
		#sel, #req // 3, nOpt, #opt // 3, #unmatched, missing,
		if #unmatched > 0 then " [" .. table.concat(unmatched, "; ", 1, math.min(5, #unmatched)) .. "]" else "")
end

local function cityCount(sel: {{part: BasePart, code: number}}): string
	local c: {[string]: number} = {}
	local order = {}
	for _, s in sel do
		local l = LABEL_OF_CODE[s.code] or CITY_LABEL[s.code] or tostring(s.code)
		if s.part:GetAttribute("RoadVisFor") ~= nil then
			l = "frontier " .. l
		end
		if not c[l] then
			table.insert(order, l)
		end
		c[l] = (c[l] or 0) + 1
	end
	table.sort(order)
	local out = {}
	for _, l in order do
		table.insert(out, l .. " " .. c[l])
	end
	return table.concat(out, ", ")
end

local function cityPlan(id: string): string
	local _, man = cityData(id)
	local lines = {("road vis plan %s (plan seq %d, %s): %d modules, %d cells, %d parts to build (own %d, pilot-band completion %d, "
		.. "frontier %d, markings / kerbs %d)"):format(id, man.batch.seq, man.batch.group, #man.modules, #man.cells, man.counts.parts,
		man.counts.own, man.counts.completion, man.counts.frontier, man.counts.segs)}
	local okO, order = orderCheck(man)
	table.insert(lines, (if okO then "ORDER OK: " else "ORDER WRONG (Build / MoveReplaced would abort): ") .. order)
	local w = workspace:FindFirstChild("PattayaWorld")
	if w then
		local built = builtFolder(id) ~= nil
		local backup = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
		local hasBackup = backup ~= nil and backup:FindFirstChild(id) ~= nil
		if hasBackup then
			table.insert(lines, ("move plan: the batch's old parts are already in ServerStorage.%s.%s (moved)"):format(RV.CITY_BACKUP, id))
		else
			local sel = selectCity(man)
			local ok, rep = matchCity(man, sel)
			table.insert(lines, ("move plan: %s -> %s; %s"):format(cityCount(sel), if ok then "MATCHES the data" else "DOES NOT MATCH (MoveReplaced would abort)", rep))
		end
		table.insert(lines, ("batch built: %s; backup present: %s"):format(tostring(built), tostring(hasBackup)))
	else
		table.insert(lines, "PattayaWorld not found: nothing to move")
	end
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

local function cityBuild(id: string): string
	local d, man = cityData(id)
	local w = world()
	if builtFolder(id) then
		return ("road vis %s: already built (RV.Remove(%q) first)"):format(id, id)
	end
	local okO, order = orderCheck(man)
	if not okO then
		local msg = ("road vis %s: ABORTED, nothing built: %s"):format(id, order)
		warn(msg)
		return msg
	end
	local folder = Instance.new("Folder")
	folder.Name = id
	folder:SetAttribute("Attribution", man.attribution)
	folder:SetAttribute("Seq", man.batch.seq)
	folder:SetAttribute("Neighbours", table.concat(man.batch.neighbours, ","))
	folder:SetAttribute("Data", man.name)
	local T, C, K = man.tops, man.colors, man.thick
	local O = RV.ORIGIN
	local cells: {[string]: Model} = {}
	local parts, wrong = 0, 0
	local mats = {Enum.Material.Asphalt, Enum.Material.Concrete, Enum.Material.Concrete, Enum.Material.Grass, Enum.Material.Asphalt}
	local tops = {T.asphalt, T.sidewalk, T.island, T.grass, T.support or T.asphalt}
	local thick = {K.asphalt, K.sidewalk, K.island, K.grass, K.support or K.asphalt}
	local colors = {rgb(C.asphalt), rgb(C.sidewalk), rgb(C.island), rgb(C.grass), rgb(C.asphalt)}
	local segColor = {rgb(C.white), rgb(C.yellow), rgb(C.white), rgb(C.white), rgb(C.white), rgb(C.kerb)}
	local targets = man.batch.frontierFor
	for _, name in man.modules do
		local m = moduleData(d, name)
		local cell = cells[m.cell]
		if not cell then
			cell = Instance.new("Model")
			cell.Name = "Cell_" .. m.cell
			cell.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
			cells[m.cell] = cell
		end
		local n = 0
		local own = {RoadVisBatch = id}
		local t = m.tris
		for i = 1, #t, 7 do
			local k = t[i + 6]
			n += triangle(cell, Vector2.new(t[i] + O.X, t[i + 1] + O.Z), Vector2.new(t[i + 2] + O.X, t[i + 3] + O.Z),
				Vector2.new(t[i + 4] + O.X, t[i + 5] + O.Z), tops[k], thick[k], TRI_NAME[k], colors[k], mats[k], k ~= 4,
				if k == 5 then 1 else 0, TRI_KIND[k], own)
		end
		local f = m.ftris or {}
		for i = 1, #f, 8 do
			-- frontier piece: the old road outside the box, rebuilt; the batch of the box it lies in replaces it
			local k = f[i + 6]
			local tgt = if f[i + 7] > 0 then targets[f[i + 7]] else ""
			n += triangle(cell, Vector2.new(f[i] + O.X, f[i + 1] + O.Z), Vector2.new(f[i + 2] + O.X, f[i + 3] + O.Z),
				Vector2.new(f[i + 4] + O.X, f[i + 5] + O.Z), tops[k], thick[k], TRI_NAME[k], colors[k], mats[k], true, 0, TRI_KIND[k],
				{RoadVisBatch = id, RoadVisFor = tgt})
		end
		local s = m.segs
		for i = 1, #s, 6 do
			local k = s[i + 5]
			local top = if k == 6 then T.kerb else T.mark
			local th = if k == 6 then K.kerb else K.mark
			n += segment(cell, Vector2.new(s[i] + O.X, s[i + 1] + O.Z), Vector2.new(s[i + 2] + O.X, s[i + 3] + O.Z), s[i + 4], top, th,
				SEG_NAME[k], segColor[k], SEG_KIND[k], own)
		end
		if n ~= m.parts then
			wrong += 1
			warn(("road vis %s module %s: %d parts built, data says %d"):format(id, name, n, m.parts))
		end
		parts += n
		task.wait()
	end
	for _, cid in man.cells do
		if cells[cid] then
			cells[cid].Parent = folder
		end
	end
	folder:SetAttribute("Parts", parts)
	folder.Parent = cityRoot(true)
	return ("road vis %s: built %d cells, %d parts (data %d)%s"):format(id, #folder:GetChildren(), parts, man.counts.parts,
		if wrong > 0 then (", %d modules with a part-count mismatch"):format(wrong) else "")
end

local function cityMoveReplaced(id: string): string
	local _, man = cityData(id)
	local w = world()
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	if bk and bk:FindFirstChild(id) then
		return ("road vis %s: ServerStorage.%s.%s already exists: nothing moved (RV.Remove(%q) restores first)"):format(id, RV.CITY_BACKUP, id, id)
	end
	if not builtFolder(id) then
		return ("road vis %s: not built: nothing moved (RV.Build(%q) first, so the road is never missing)"):format(id, id)
	end
	local okO, order = orderCheck(man)
	if not okO then
		local msg = ("road vis %s: ABORTED, nothing moved: %s"):format(id, order)
		warn(msg)
		return msg
	end
	local sel = selectCity(man)
	local ok, report = matchCity(man, sel)
	if not ok then
		local msg = ("road vis %s: ABORTED, nothing moved: the selection does not match the data (%s)"):format(id, report)
		warn(msg)
		return msg
	end
	for _, s in sel do -- second safety net: never a shoulder part, never a part of this batch
		if inShoulders(s.part, w) then
			return ("road vis %s: ABORTED, a ShoulderChunks part was selected (%s)"):format(id, s.part:GetFullName())
		end
		if s.part:GetAttribute("RoadVisBatch") == id then
			return ("road vis %s: ABORTED, a part of this batch was selected (%s)"):format(id, s.part:GetFullName())
		end
	end
	if not bk then
		local f = Instance.new("Folder")
		f.Name = RV.CITY_BACKUP
		f.Parent = ServerStorage
		bk = f
	end
	local backup = Instance.new("Folder")
	backup.Name = id
	local groups: {[Instance]: Folder} = {}
	local n = 0
	for _, s in sel do
		local p = s.part
		local parent = p.Parent :: Instance
		local g = groups[parent]
		if not g then
			local f = Instance.new("Folder")
			f.Name = "From_" .. tostring(n)
			local ref = Instance.new("ObjectValue")
			ref.Name = "OriginalParentRef"
			ref.Value = parent
			ref.Parent = f
			f:SetAttribute("OriginalParent", parent:GetFullName())
			f.Parent = backup
			groups[parent] = f
			g = f
		end
		p:SetAttribute("OriginalParent", parent:GetFullName())
		p:SetAttribute("OriginalCFrame", p.CFrame)
		p:SetAttribute("RoadVisMoved", LABEL_OF_CODE[s.code] or CITY_LABEL[s.code])
		p.Parent = g
		n += 1
	end
	backup:SetAttribute("Count", n)
	backup:SetAttribute("Seq", man.batch.seq)
	backup.Parent = bk
	return ("road vis %s: moved %d parts (%s) to ServerStorage.%s.%s; %s"):format(id, n, cityCount(sel), RV.CITY_BACKUP, id, report)
end

-- last-in first-out: a later-built neighbour, or a backup that holds this batch's frontier pieces, blocks the removal
local function cityBlockers(id: string, built: Instance?): {string}
	local out = {}
	local seq = if built then built:GetAttribute("Seq") or 0 else 0
	local r = cityRoot(false)
	if r and built then
		for _, f in r:GetChildren() do
			if f ~= built then
				local nb = tostring(f:GetAttribute("Neighbours") or "")
				local mine = string.find("," .. nb .. ",", "," .. id .. ",", 1, true) ~= nil
				if mine and (f:GetAttribute("Seq") or 0) > seq then
					table.insert(out, f.Name .. " (a later neighbour)")
				end
			end
		end
	end
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	if bk then
		for _, b in bk:GetChildren() do
			if b.Name ~= id then
				for _, p in b:GetDescendants() do
					if p:GetAttribute("RoadVisBatch") == id then
						table.insert(out, b.Name .. " (holds this batch's frontier pieces)")
						break
					end
				end
			end
		end
	end
	return out
end

local function cityRemove(id: string): string
	local built = builtFolder(id)
	local blockers = cityBlockers(id, built)
	if #blockers > 0 then
		local msg = ("road vis %s: NOT removed, remove these first (last in, first out): %s"):format(id, table.concat(blockers, ", "))
		warn(msg)
		return msg
	end
	local removed = false
	if built then
		built:Destroy()
		removed = true
	end
	local root = cityRoot(false)
	if root and #root:GetChildren() == 0 then
		root:Destroy()
	end
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	local backup = if bk then bk:FindFirstChild(id) else nil
	if not backup then
		return ("road vis %s: %s; no backup to restore"):format(id, if removed then "removed" else "not built")
	end
	local expected = backup:GetAttribute("Count") or -1
	local restored, failed = 0, 0
	for _, g in backup:GetChildren() do
		local ref = g:FindFirstChild("OriginalParentRef") :: ObjectValue?
		local target = ref and ref.Value
		for _, p in g:GetChildren() do
			if p:IsA("BasePart") then
				if target and target.Parent then
					local cf = p:GetAttribute("OriginalCFrame")
					if typeof(cf) == "CFrame" then
						(p :: BasePart).CFrame = cf
					end
					p:SetAttribute("OriginalParent", nil)
					p:SetAttribute("OriginalCFrame", nil)
					p:SetAttribute("RoadVisMoved", nil)
					p.Parent = target
					restored += 1
				else
					failed += 1
				end
			end
		end
	end
	if restored == expected and failed == 0 then
		backup:Destroy()
		if #bk:GetChildren() == 0 then
			bk:Destroy()
		end
		return ("road vis %s: %s; restored %d of %d parts to their original parents; backup removed"):format(id,
			if removed then "removed" else "not built", restored, expected)
	end
	local msg = ("road vis %s: %s; restored %d of %d parts, %d could not be restored (original parent gone): backup KEPT"):format(id,
		if removed then "removed" else "not built", restored, expected, failed)
	warn(msg)
	return msg
end

-- lane-centre support per offset, inside the box and in the 30-stud seam band around it: flat (a Road part 0.9..1.1),
-- kerb (1.1..1.8), blocked (above 1.8), ground (the ray reaches the terrain: no road part under the wheel point; a
-- point whose 4 neighbour rays 0.05 away all hit road parts is a hairline seam, counted apart)
local function cityProbe(id: string): string
	local _, man = cityData(id)
	local built = builtFolder(id)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = {}
	local O = RV.ORIGIN
	local S = man.probe.samples
	local stride = man.probe.stride or 7
	local fw, fl = man.probe.foot[1] / 2, man.probe.foot[2] / 2
	local pts = {{-fl, -fw}, {-fl, fw}, {fl, -fw}, {fl, fw}, {0, -fw}, {0, fw}}
	local terrain = workspace.Terrain
	local function hitAt(x: number, z: number): (number, boolean)
		local hit = workspace:Raycast(Vector3.new(x, 40, z), Vector3.new(0, -60, 0), params)
		if not hit then
			return -math.huge, true
		end
		return hit.Position.Y, hit.Instance == terrain or hit.Instance == nil
	end
	local function seam(x: number, z: number): boolean
		for _, dd in {{0.05, 0}, {-0.05, 0}, {0, 0.05}, {0, -0.05}} do
			local y, ground = hitAt(x + dd[1], z + dd[2])
			if ground or y < 0.9 or y > 1.1 then
				return false
			end
		end
		return true
	end
	local lines = {}
	local groundIn, seams = 0, 0
	local at = {}
	for _, o in man.probe.offsets do
		local c = {inBox = {n = 0, flat = 0, kerb = 0, blocked = 0, ground = 0}, seam = {n = 0, flat = 0, kerb = 0, blocked = 0, ground = 0}}
		for i = 1, #S, stride do
			local hw = S[i + 4]
			if math.abs(o) <= hw then
				local cx, cz, tx, tz = S[i] + O.X, S[i + 1] + O.Z, S[i + 2], S[i + 3]
				local nx, nz = -tz, tx
				local worst = 0 -- 0 flat, 1 kerb, 2 blocked, 3 ground
				for _, q in pts do
					local x = cx + nx * (o + q[2]) + tx * q[1]
					local z = cz + nz * (o + q[2]) + tz * q[1]
					local y, ground = hitAt(x, z)
					local cls = if ground then 3 elseif y > 1.8 then 2 elseif y > 1.1 then 1 elseif y >= 0.9 then 0 else 3
					if cls == 3 and seam(x, z) then
						cls = 0
						seams += 1
					elseif cls == 3 and S[i + 6] == 1 and #at < 5 then
						table.insert(at, ("(%.1f, %.1f) offset %d"):format(x, z, o))
					end
					worst = math.max(worst, cls)
				end
				local t = if S[i + 6] == 1 then c.inBox else c.seam
				t.n += 1
				if worst == 0 then t.flat += 1 elseif worst == 1 then t.kerb += 1 elseif worst == 2 then t.blocked += 1 else t.ground += 1 end
			end
		end
		groundIn += c.inBox.ground
		local e = man.probe.expected[tostring(o)] or {}
		local ei, es = e.inBox or {}, e.seam or {}
		table.insert(lines, ("offset %d: in box %d samples, flat %d, kerb %d, blocked %d, ground %d (offline %s / %s / %s / %s); "
			.. "seam band %d, flat %d, kerb %d, blocked %d, ground %d (offline %s / %s / %s / %s)"):format(o, c.inBox.n, c.inBox.flat,
			c.inBox.kerb, c.inBox.blocked, c.inBox.ground, tostring(ei.flat), tostring(ei.kerb), tostring(ei.blocked), tostring(ei.ground),
			c.seam.n, c.seam.flat, c.seam.kerb, c.seam.blocked, c.seam.ground, tostring(es.flat), tostring(es.kerb), tostring(es.blocked),
			tostring(es.ground)))
	end
	if #at > 0 then
		table.insert(lines, "first in-box ground points at " .. table.concat(at, "; "))
	end
	local bHits, n = 0, 0
	if built then
		local op = OverlapParams.new()
		for _, p in built:GetDescendants() do
			if p:IsA("BasePart") then
				n += 1
				if (p :: BasePart).CanCollide then
					for _, hit in workspace:GetPartsInPart(p :: BasePart, op) do
						if hit:GetAttribute("OsmBuilding") ~= nil then
							bHits += 1
							break
						end
					end
				end
			end
		end
	end
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	local backup = if bk then bk:FindFirstChild(id) else nil
	local head = ("road vis probe %s: %d legs, %d samples; parts %d (data %d); building overlaps %d; moved parts %s; in-box ground points at offset 0..24: %d; hairline seams %d"):format(
		id, #man.probe.legs, #S // stride, n, man.counts.parts, bHits, if backup then tostring(backup:GetAttribute("Count")) else "none", groundIn, seams)
	local out = head .. "\n" .. table.concat(lines, "\n")
	print(out)
	return out
end

-- every city batch: built / moved / data present, in plan order
function RV.Status(): string
	local lines = {}
	local w = workspace:FindFirstChild("PattayaWorld")
	table.insert(lines, ("pilot: %s, backup %s"):format(if w and w:FindFirstChild(RV.FOLDER) then "built" else "not built",
		if ServerStorage:FindFirstChild(RV.BACKUP) then "present" else "absent"))
	local rows = {}
	local r = cityRoot(false)
	if r then
		for _, f in r:GetChildren() do
			table.insert(rows, {f.Name, f:GetAttribute("Seq") or 0, f:GetAttribute("Parts") or 0})
		end
	end
	table.sort(rows, function(a, b) return a[2] < b[2] end)
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	for _, row in rows do
		local b = if bk then bk:FindFirstChild(row[1]) else nil
		table.insert(lines, ("%s seq %d: %d parts; moved %s; data %s"):format(row[1], row[2], row[3],
			if b then tostring(b:GetAttribute("Count")) else "none",
			if ServerStorage:FindFirstChild(RV.CITY_DATA_PREFIX .. row[1]) then "present" else "absent"))
	end
	table.insert(lines, ("%d city batches built"):format(#rows))
	local out = table.concat(lines, "\n")
	print(out)
	return out
end

-- anything a city batch could leave behind after every batch is removed ("road vis city leftovers: none")
function RV.Leftovers(): string
	local found = {}
	local w = workspace:FindFirstChild("PattayaWorld")
	if w and w:FindFirstChild(RV.CITY_FOLDER) then
		table.insert(found, "PattayaWorld." .. RV.CITY_FOLDER)
	end
	if ServerStorage:FindFirstChild(RV.CITY_BACKUP) then
		table.insert(found, "ServerStorage." .. RV.CITY_BACKUP)
	end
	local tagged = 0
	for _, root in {w, ServerStorage} do
		if root then
			for _, d in (root :: Instance):GetDescendants() do
				if d:GetAttribute("RoadVisBatch") ~= nil or d:GetAttribute("RoadVisMoved") ~= nil then
					tagged += 1
				end
			end
		end
	end
	if tagged > 0 then
		table.insert(found, ("%d instances with RoadVisBatch / RoadVisMoved attributes"):format(tagged))
	end
	return if #found == 0 then "road vis city leftovers: none" else "road vis city leftovers: " .. table.concat(found, "; ")
end

-- ---- public entry points: a batch id selects a city batch, nothing (or "pilot") the pilot -------------------------------
function RV.Plan(id: string?): string
	if isCity(id) then
		return cityPlan(id :: string)
	end
	return pilotPlan()
end

function RV.Build(a: any?, b: any?): string
	if isCity(a) then
		return cityBuild(a :: string)
	end
	return pilotBuild(if type(a) == "table" then a else b)
end

function RV.MoveReplaced(id: string?): string
	if isCity(id) then
		return cityMoveReplaced(id :: string)
	end
	return pilotMoveReplaced()
end

function RV.Remove(id: string?): string
	if isCity(id) then
		return cityRemove(id :: string)
	end
	-- the pilot: never while a city batch next to it is built (its pilot-band pieces stand in the pilot box) or still
	-- holds pilot parts in its backup (they would not come back)
	local r = cityRoot(false)
	if r then
		for _, f in r:GetChildren() do
			local nb = "," .. tostring(f:GetAttribute("Neighbours") or "") .. ","
			if string.find(nb, ",pilot,", 1, true) then
				local msg = ("road vis: pilot NOT removed: city batch %s next to it is built; remove it first (last in, first out)"):format(f.Name)
				warn(msg)
				return msg
			end
		end
	end
	local bk = ServerStorage:FindFirstChild(RV.CITY_BACKUP)
	if bk then
		for _, b in bk:GetChildren() do
			for _, p in b:GetDescendants() do
				if p:IsA("BasePart") and p:GetAttribute("RoadVis") == true and p:GetAttribute("RoadVisBatch") == nil then
					local msg = ("road vis: pilot NOT removed: city batch %s holds pilot parts; remove it first (last in, first out)"):format(b.Name)
					warn(msg)
					return msg
				end
			end
		end
	end
	return pilotRemove()
end

function RV.Probe(id: string?): string
	if isCity(id) then
		return cityProbe(id :: string)
	end
	return pilotProbe()
end

-- ---- optional shoulder look (owner approval only) -------------------------------------------------------------------
-- strips and tapers: gutter concrete colour; gap fills: invisible (CanCollide / CanQuery untouched). Every original value
-- is stored as an attribute first, so ShoulderLookRevert puts it back exactly.
function RV.ShoulderLook(opts: {recolour: boolean?, hideGapFills: boolean?}?): string
	local options = (opts or {recolour = true, hideGapFills = true}) :: any
	local _, man = data()
	local sc = world():FindFirstChild("ShoulderChunks")
	if not sc then
		return "road vis: no ShoulderChunks"
	end
	local gutter = rgb(man.colors.gutter)
	local re, hid = 0, 0
	for _, p in sc:GetDescendants() do
		if p:IsA("BasePart") and p:GetAttribute("Shoulder") == true then
			local bp = p :: BasePart
			local kind = bp:GetAttribute("ShoulderKind")
			if bp:GetAttribute("RVOrigColor") == nil then
				bp:SetAttribute("RVOrigColor", bp.Color)
				bp:SetAttribute("RVOrigMaterial", bp.Material.Name)
				bp:SetAttribute("RVOrigTransparency", bp.Transparency)
			end
			if kind == "gap" and options.hideGapFills then
				bp.Transparency = 1
				hid += 1
			elseif kind ~= "gap" and options.recolour then
				bp.Color = gutter
				bp.Material = Enum.Material.Concrete
				re += 1
			end
		end
	end
	return ("road vis: shoulder look: %d strips / tapers recoloured, %d gap fills hidden (collision kept)"):format(re, hid)
end

function RV.ShoulderLookRevert(): string
	local sc = world():FindFirstChild("ShoulderChunks")
	if not sc then
		return "road vis: no ShoulderChunks"
	end
	local n = 0
	for _, p in sc:GetDescendants() do
		if p:IsA("BasePart") and p:GetAttribute("RVOrigColor") ~= nil then
			local bp = p :: BasePart
			bp.Color = bp:GetAttribute("RVOrigColor") :: Color3
			local ok, m = pcall(function()
				return (Enum.Material :: any)[bp:GetAttribute("RVOrigMaterial")]
			end)
			if ok and m then
				bp.Material = m
			end
			bp.Transparency = bp:GetAttribute("RVOrigTransparency") :: number
			bp:SetAttribute("RVOrigColor", nil)
			bp:SetAttribute("RVOrigMaterial", nil)
			bp:SetAttribute("RVOrigTransparency", nil)
			n += 1
		end
	end
	return ("road vis: shoulder look reverted on %d parts"):format(n)
end

return RV
