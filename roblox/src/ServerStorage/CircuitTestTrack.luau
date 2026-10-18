-- Plain driveable surface for a circuit definition (test fixture only; the real Bira geometry comes from the
-- geometry teammate's CircuitBuilder). Builds workspace.Circuits.<id>: a grass base big enough to drive anywhere
-- around the track, SmoothPlastic asphalt along the centerline, the pit lane, a white start/finish stripe, yellow
-- sector stripes and white grid boxes. No race logic.
-- Edit time (command bar):
--   local c = require(game.ServerStorage.PattayaData.circuits.test_oval)
--   require(game.ServerStorage.CircuitTestTrack).Build(c)
-- CircuitServer also calls Build at run time for a definition with testSurface = true when workspace.Circuits.<id>
-- does not exist.
local TestTrack = {}

local ASPHALT = Color3.fromRGB(48, 48, 52)
local PIT = Color3.fromRGB(72, 72, 78)
local GRASS = Color3.fromRGB(58, 110, 52)

local function points(flat): {Vector3}
	local out = {}
	for i = 1, #flat - 2, 3 do
		table.insert(out, Vector3.new(flat[i], flat[i + 1], flat[i + 2]))
	end
	return out
end

local function slab(parent: Instance, name: string, a: Vector3, b: Vector3, width: number, color: Color3, top: number)
	local d = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
	local len = d.Magnitude
	if len < 0.05 then
		return
	end
	local mid = (a + b) / 2
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Material = Enum.Material.SmoothPlastic
	p.Color = color
	p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
	p.Size = Vector3.new(width, 1, len + 2) -- 1 stud of overlap at each end hides the gaps on the outside of corners
	local c = Vector3.new(mid.X, top - 0.5, mid.Z)
	p.CFrame = CFrame.lookAt(c, c + d)
	p.Parent = parent
end

local function stripe(parent: Instance, name: string, at: Vector3, dir: Vector3, across: number, along: number, color: Color3, top: number)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.Material = Enum.Material.SmoothPlastic
	p.Color = color
	p.Size = Vector3.new(across, 0.1, along)
	local c = Vector3.new(at.X, top + 0.05, at.Z)
	p.CFrame = CFrame.lookAt(c, c + dir)
	p.Parent = parent
end

function TestTrack.Build(def)
	local root = workspace:FindFirstChild("Circuits")
	if not root then
		root = Instance.new("Folder")
		root.Name = "Circuits"
		root.Parent = workspace
	end
	local old = root:FindFirstChild(def.id)
	if old then
		old:Destroy()
	end
	local model = Instance.new("Model")
	model.Name = def.id
	model:SetAttribute("TestSurface", true)

	local pts = points(def.centerline)
	local n = #pts
	local widthOf = function(i: number): number
		return (def.width and def.width[i]) or def.trackWidth or 40
	end
	local minX, maxX, minZ, maxZ, y = math.huge, -math.huge, math.huge, -math.huge, pts[1].Y
	local function grow(p: Vector3, r: number)
		minX, maxX = math.min(minX, p.X - r), math.max(maxX, p.X + r)
		minZ, maxZ = math.min(minZ, p.Z - r), math.max(maxZ, p.Z + r)
	end
	for i, p in pts do
		grow(p, widthOf(i))
		y = math.min(y, p.Y)
	end
	local pit = if def.pitLane then points(def.pitLane) else {}
	for _, p in pit do
		grow(p, 30)
	end
	if def.entrance then
		grow(Vector3.new(def.entrance.x, y, def.entrance.z), 60)
	end

	-- grass base, 0.2 below the asphalt, in tiles (a part can be at most 2048 studs on a side)
	local base = Instance.new("Folder")
	base.Name = "Base"
	base.Parent = model
	local TILE = 2000
	local x0 = minX - 80
	while x0 < maxX + 80 do
		local z0 = minZ - 80
		local w = math.min(TILE, maxX + 80 - x0)
		while z0 < maxZ + 80 do
			local d = math.min(TILE, maxZ + 80 - z0)
			local g = Instance.new("Part")
			g.Name = "Grass"
			g.Anchored = true
			g.Material = Enum.Material.SmoothPlastic
			g.Color = GRASS
			g.Size = Vector3.new(w, 2, d)
			g.Position = Vector3.new(x0 + w / 2, y - 0.2 - 1, z0 + d / 2)
			g.Parent = base
			z0 += d
		end
		x0 += w
	end

	local track = Instance.new("Folder")
	track.Name = "Track"
	track.Parent = model
	for i = 1, n do
		local j = i % n + 1
		slab(track, "Asphalt", pts[i], pts[j], (widthOf(i) + widthOf(j)) / 2, ASPHALT, (pts[i].Y + pts[j].Y) / 2)
	end
	local pitWidth = def.pitWidth or 20
	for i = 1, #pit - 1 do
		slab(track, "PitLane", pit[i], pit[i + 1], pitWidth, PIT, (pit[i].Y + pit[i + 1].Y) / 2 - 0.05)
	end

	local function dirAt(i: number): Vector3
		local a, b = pts[(i - 2) % n + 1], pts[i % n + 1]
		local d = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
		return if d.Magnitude > 0.01 then d.Unit else Vector3.new(0, 0, -1)
	end
	local sf = def.startFinish and def.startFinish.index or 1
	stripe(model, "StartFinish", pts[sf], dirAt(sf), widthOf(sf), 3, Color3.new(1, 1, 1), pts[sf].Y)
	for k, i in def.sectors or {} do
		stripe(model, "Sector" .. k, pts[i], dirAt(i), widthOf(i), 1.5, Color3.fromRGB(255, 210, 40), pts[i].Y)
	end
	for k, s in def.grid or {} do
		local at = Vector3.new(s[1], s[2], s[3])
		local dir = Vector3.new(s[4], 0, s[5]).Unit
		stripe(model, "Grid" .. k, at + dir * 8, dir, 7, 0.6, Color3.new(1, 1, 1), s[2])
	end
	model.Parent = root
	return model
end

return TestTrack
