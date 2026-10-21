--!strict
-- Road visual pilot, design B (MIDNIGHT PATTAYA): the Sukhumvit / Pattaya Klang junction (world x 24220..24820,
-- z 650..1250) rebuilt from the road graph as one clean road surface: carriageway ribbons, kerb returns, islands,
-- kerbed sidewalks, continuous lane markings, stop lines and zebras on the junction legs. docs/ROAD_VISUAL_SPEC.md.
-- Data: ServerStorage.PattayaDataRoadVis (tools/roadvis/export_luau.py -> build/roadvis/roblox: manifest +
-- cell_<cx>_<cz>[_k], <= 600 parts each). Edit mode only. Written and run OFFLINE (luau CLI with stub Roblox types);
-- NOT run in Studio yet, and installing it needs the owner's approval.
--   local RV = require(game.ServerStorage.PattayaRoadVisBuilder)
--   RV.Plan()                 -- what Build would create and MoveReplaced would move (and whether the selection matches)
--   RV.Build()                -- workspace.PattayaWorld.RoadVisPilot (one Atomic Model per 256-stud cell)
--   RV.Build({mesh = true})   -- OPT-IN: invisible collision + EditableMesh visual MeshParts (see below)
--   RV.MoveReplaced()         -- moves the old road parts of the area to ServerStorage.RoadVisBackup (exact list check)
--   RV.Probe()                -- lane-centre support on every leg at offsets 0 / +-8 / +-14 / +-20 / +-24, buildings, counts
--   RV.Remove()               -- destroys RoadVisPilot and puts every backed-up part back (parent + CFrame), verified
--   RV.ShoulderLook({recolour = true, hideGapFills = true}) / RV.ShoulderLookRevert()   -- optional, owner-approved only
-- Default visual = the collision parts themselves, visible (asphalt "Road", "Sidewalk", "Island" WedgeParts) plus thin
-- non-colliding marking / kerb / grass Parts. Why the default is Parts, not meshes: a MeshPart made from an
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
local TRI_KIND = {"asphalt", "sidewalk", "island", "grass"}
local TRI_NAME = {"Road", "Sidewalk", "Island", "Grass"}
local SEG_KIND = {"lane", "centre", "edge", "stop", "zebra", "kerb"}
local SEG_NAME = {"Dash", "Centre", "EdgeLine", "StopLine", "ZebraStripe", "Kerb"}

local function rgb(c: {number}): Color3
	return Color3.fromRGB(c[1], c[2], c[3])
end

local function data(): (Instance, any)
	local d = ServerStorage:WaitForChild(RV.DATA)
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
		error("PattayaRoadVisBuilder: workspace.PattayaWorld not found")
	end
	return w :: Instance
end

local function finish(p: BasePart, name: string, color: Color3, material: Enum.Material, collide: boolean, transparency: number,
	kind: string, parent: Instance)
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
	p.Parent = parent
end

-- one flat triangle a-b-c (world x / z) from two WedgeParts split at the foot of the altitude on the longest side,
-- exactly as PattayaBuilder.roadTriangle; top / thick per layer
local function triangle(parent: Instance, a: Vector2, b: Vector2, c: Vector2, top: number, thick: number, name: string,
	color: Color3, material: Enum.Material, collide: boolean, transparency: number, kind: string): number
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
			finish(w, name, color, material, collide, transparency, kind, parent)
			n += 1
		end
	end
	return n
end

local function segment(parent: Instance, a: Vector2, b: Vector2, width: number, top: number, thick: number, name: string,
	color: Color3, kind: string): number
	local len = (b - a).Magnitude
	if len < 0.05 then
		return 0
	end
	local mid = (a + b) / 2
	local y = top - thick / 2
	local p = Instance.new("Part")
	p.Size = Vector3.new(width, thick, len)
	p.CFrame = CFrame.lookAt(Vector3.new(mid.X, y, mid.Y), Vector3.new(b.X, y, b.Y))
	finish(p, name, color, Enum.Material.SmoothPlastic, false, 0, kind, parent)
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

function RV.Plan(): string
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

function RV.Build(opts: {mesh: boolean?}?): string
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
	local mats = {Enum.Material.Asphalt, Enum.Material.Concrete, Enum.Material.Concrete, Enum.Material.Grass}
	local tops = {T.asphalt, T.sidewalk, T.island, T.grass}
	local thick = {K.asphalt, K.sidewalk, K.island, K.grass}
	local colors = {rgb(C.asphalt), rgb(C.sidewalk), rgb(C.island), rgb(C.grass)}
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
			local collide = k ~= 4
			if useMesh and k == 4 then
				continue -- grass is in the mesh
			end
			local nm = if useMesh and collide then TRI_NAME[k] .. "Collision" else TRI_NAME[k]
			n += triangle(cell, Vector2.new(t[i] + O.X, t[i + 1] + O.Z), Vector2.new(t[i + 2] + O.X, t[i + 3] + O.Z),
				Vector2.new(t[i + 4] + O.X, t[i + 5] + O.Z), tops[k], thick[k], nm, colors[k], mats[k], collide,
				if useMesh and collide then 1 else 0, TRI_KIND[k])
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
function RV.MoveReplaced(): string
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

function RV.Remove(): string
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
-- drop), drop = a point hits nothing or lower, blocked = higher (a building or prop on the road). Plus: pilot parts
-- overlapping a building, counts. The manifest holds the offline expectation for the same samples.
function RV.Probe(): string
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
	local totalDrop = 0
	for _, o in man.probe.offsets do
		local n, flat, kerb, drop, blocked = 0, 0, 0, 0, 0
		for i = 1, #S, 6 do
			local hw = S[i + 4]
			if math.abs(o) <= hw then
				local cx, cz, tx, tz = S[i] + O.X, S[i + 1] + O.Z, S[i + 2], S[i + 3]
				local nx, nz = -tz, tx
				local worst = "flat"
				for _, q in pts do
					local x = cx + nx * (o + q[2]) + tx * q[1]
					local z = cz + nz * (o + q[2]) + tz * q[1]
					local hit = workspace:Raycast(Vector3.new(x, 40, z), Vector3.new(0, -60, 0), params)
					local y = if hit then hit.Position.Y else -math.huge
					local cls = if y > 1.8 then "blocked" elseif y > 1.1 then "kerb" elseif y >= 0.9 then "flat" else "drop"
					if cls == "drop" or (cls == "blocked" and worst ~= "drop") or (cls == "kerb" and worst == "flat") then
						worst = cls
					end
				end
				n += 1
				if worst == "flat" then flat += 1 elseif worst == "kerb" then kerb += 1 elseif worst == "drop" then drop += 1 else blocked += 1 end
			end
		end
		totalDrop += drop
		local e = man.probe.expected[tostring(o)]
		table.insert(lines, ("offset %d: %d samples, flat %d, kerb %d, drop %d, blocked %d (offline expected: drop %d, kerb %d)"):format(
			o, n, flat, kerb, drop, blocked, e and e.drop or -1, e and e.kerb or -1))
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
	local head = ("road vis probe: %d legs, %d samples; pilot parts %d (data %d); building overlaps %d; moved parts %s; total drops %d"):format(
		#man.probe.legs, #S // 6, built, man.counts.parts, bHits, if backup then tostring(backup:GetAttribute("Count")) else "none", totalDrop)
	local out = head .. "\n" .. table.concat(lines, "\n")
	print(out)
	return out
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
