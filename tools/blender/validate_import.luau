--[[ MIDNIGHT PATTAYA vis assets: post-import check (leader runs it in Studio, Edit mode, Command Bar or the MCP
execute_luau tool). Read-only: it changes nothing.

Setup: put the generated tools/blender/import_manifest.luau as a ModuleScript `ServerStorage.VisAssetsManifest`, and
the imported models (any depth) under `ServerStorage.VisAssets` (or change ROOT below).

What it checks per manifest entry (expected values come from validate.py on the exported GLBs):
  * a Model (or the first instance) named exactly like the asset exists under ROOT
  * each expected MeshPart child <Asset>_<Short> exists, is a MeshPart, and MeshPart.MeshSize matches the GLB part
    bbox (+-0.05 studs) -> proves Scale Unit = Studs (if every size is 3.571x too big the file was read as metres;
    0.28x = it was read with another unit) and Y-up (swapped X/Y/Z sizes = wrong World Up/Forward)
  * MeshPart.Size == MeshSize (nobody rescaled the part after import)
  * overall extents of the parts == manifest size (+-0.1)
  * pivot rule: lowest point of the parts sits at the model pivot's Y (+-0.05) -> "Set Pivot to Scene Origin" kept
    the exported origin
  * CollisionFidelity vs the recommendation, Anchored, CanCollide recommendation
  * optional triangle count: AssetService:CreateEditableMeshAsync(Content.fromUri(MeshId)):GetFaces() -- needs the
    EditableMesh API to be allowed for the asset (the experience must own it); reported as "n/a" when it fails.
What it CANNOT check: material/texture appearance, normals, UV layout, how the asset looks at night (eye check).
]]
local ServerStorage = game:GetService("ServerStorage")
local AssetService = game:GetService("AssetService")

local ROOT = ServerStorage:FindFirstChild("VisAssets")
local MANIFEST = ServerStorage:FindFirstChild("VisAssetsManifest")
assert(ROOT, "put the imported models under ServerStorage.VisAssets")
assert(MANIFEST, "put import_manifest.luau as ServerStorage.VisAssetsManifest")
local M = require(MANIFEST:Clone()) -- Clone(): Studio caches the first require of an edited ModuleScript

local TRY_TRIS = true
local tol, tolBox = 0.05, 0.1
local okCount, failCount, missing = 0, 0, 0

local function near(a: Vector3, b: Vector3, t: number): boolean
	return math.abs(a.X - b.X) <= t and math.abs(a.Y - b.Y) <= t and math.abs(a.Z - b.Z) <= t
end

local function fmt(v: Vector3): string
	return string.format("%.2f x %.2f x %.2f", v.X, v.Y, v.Z)
end

local function triCount(mp: MeshPart): number?
	if not TRY_TRIS then
		return nil
	end
	local ok, res = pcall(function()
		local em = AssetService:CreateEditableMeshAsync(Content.fromUri(mp.MeshId))
		local n = #em:GetFaces()
		em:Destroy()
		return n
	end)
	return if ok then res else nil
end

local names = {}
for name in M do
	table.insert(names, name)
end
table.sort(names)

for _, name in names do
	local exp = M[name]
	local model = ROOT:FindFirstChild(name, true)
	if not model then
		missing += 1
		print(("MISSING %s"):format(name))
		continue
	end
	local problems = {}
	local lo, hi = Vector3.new(math.huge, math.huge, math.huge), Vector3.new(-math.huge, -math.huge, -math.huge)
	local pivot = if model:IsA("Model") then model:GetPivot() else (model :: BasePart).CFrame
	local tris, trisKnown = 0, true
	for short, p in exp.parts do
		local mp = model:FindFirstChild(name .. "_" .. short, true)
		if not mp or not mp:IsA("MeshPart") then
			table.insert(problems, ("part %s_%s missing"):format(name, short))
			continue
		end
		if not near(mp.MeshSize, p.size, tol) then
			table.insert(problems, ("%s MeshSize %s, expected %s"):format(short, fmt(mp.MeshSize), fmt(p.size)))
		end
		if not near(mp.Size, mp.MeshSize, tol) then
			table.insert(problems, ("%s Size %s was rescaled (MeshSize %s)"):format(short, fmt(mp.Size), fmt(mp.MeshSize)))
		end
		if mp.CollisionFidelity.Name ~= exp.collision then
			table.insert(problems, ("%s CollisionFidelity %s (recommended %s)"):format(short, mp.CollisionFidelity.Name, exp.collision))
		end
		if not mp.Anchored then
			table.insert(problems, short .. " not Anchored")
		end
		-- extents in the pivot frame
		local cf = pivot:ToObjectSpace(mp.CFrame)
		local h = mp.Size / 2
		for _, sx in { -1, 1 } do
			for _, sy in { -1, 1 } do
				for _, sz in { -1, 1 } do
					local c = cf * Vector3.new(sx * h.X, sy * h.Y, sz * h.Z)
					lo = Vector3.new(math.min(lo.X, c.X), math.min(lo.Y, c.Y), math.min(lo.Z, c.Z))
					hi = Vector3.new(math.max(hi.X, c.X), math.max(hi.Y, c.Y), math.max(hi.Z, c.Z))
				end
			end
		end
		local n = triCount(mp)
		if n then
			tris += n
			if n ~= p.tris then
				table.insert(problems, ("%s %d tris, expected %d"):format(short, n, p.tris))
			end
		else
			trisKnown = false
		end
	end
	if lo.X < math.huge then
		if not near(hi - lo, exp.size, tolBox) then
			table.insert(problems, ("extents %s, expected %s"):format(fmt(hi - lo), fmt(exp.size)))
		end
		if math.abs(lo.Y) > tol then
			table.insert(problems, ("lowest point %.2f studs from the pivot (expected 0: pivot moved?)"):format(lo.Y))
		end
	end
	local triText = if trisKnown then tostring(tris) else "n/a"
	if #problems == 0 then
		okCount += 1
		print(("OK      %-30s %s  tris %s/%d"):format(name, fmt(exp.size), triText, exp.tris))
	else
		failCount += 1
		print(("CHECK   %-30s %s"):format(name, table.concat(problems, "; ")))
	end
end
print(("vis assets: %d ok, %d to check, %d missing (of %d)"):format(okCount, failCount, missing, #names))
