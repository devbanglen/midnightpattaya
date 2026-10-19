-- Studio COMMAND BAR, EDIT mode (leader): put the traffic vehicle templates where PattayaTraffic's clients clone them.
-- 1. Fill ASSET_IDS below (or the assetId fields of ReplicatedStorage.TrafficVehicles) with the uploaded Model ids.
--    Alternatively import the 7 .glb with the 3D Importer (Scale Unit Studs, Merge Meshes OFF, Set Pivot to Scene
--    Origin ON, Make Double Sided OFF, Invert Negative Faces OFF) and leave the Models in Workspace: step 2 picks up a
--    Model named TRF_* found in Workspace when an id is 0.
-- 2. Run this. It makes ReplicatedStorage.TrafficVehicleTemplates.<Name> (a Model holding the 4 MeshParts
--    <Name>_Paint/_Dark/_Head/_Tail), replacing an older one, and prints a check line per asset.
-- 3. Save the place. Nothing else to do: the client places each clone from the manifest centre and turns it back by
--    the importer's 180 deg yaw itself (TrafficVehicles.IMPORT_YAW), so the templates' own position and rotation do
--    not matter and are NOT changed here. Anchored / CanCollide / Massless / welds are set on the clones by the
--    client (unanchored, massless, non-colliding, CanQuery off, welded to the invisible collision box).
local InsertService = game:GetService("InsertService")
local RS = game:GetService("ReplicatedStorage")

local ASSET_IDS = { -- 0 = take the module's assetId, else a TRF_* Model already in Workspace
	TRF_Car_Sedan = 0, TRF_Car_Hatch = 0, TRF_Scooter_Pair = 0, TRF_TukTuk_Std = 0,
	TRF_Songthaew_Std = 0, TRF_Pickup_Std = 0, TRF_Van_Std = 0,
}

-- the command bar caches require(): read the module from a fresh clone so edits to it are seen
local modClone = RS:WaitForChild("TrafficVehicles"):Clone()
local TV = require(modClone)

local folder = RS:FindFirstChild(TV.TEMPLATE_FOLDER)
if not folder then
	folder = Instance.new("Folder")
	folder.Name = TV.TEMPLATE_FOLDER
	folder.Parent = RS
end

local function findModel(root: Instance, name: string): Model?
	if root:IsA("Model") and root.Name == name then
		return root
	end
	local m = root:FindFirstChild(name, true)
	if m and m:IsA("Model") then
		return m
	end
	-- importer may wrap the file in an extra Model: the Model that holds <name>_Paint
	local p = root:FindFirstChild(name .. "_Paint", true)
	return if p and p.Parent and p.Parent:IsA("Model") then p.Parent :: Model else nil
end

for name, a in TV.ASSETS do
	local id = ASSET_IDS[name]
	if not id or id == 0 then
		id = a.assetId
	end
	local model: Model? = nil
	local container: Instance? = nil
	if id and id > 0 then
		local ok, res = pcall(InsertService.LoadAsset, InsertService, id)
		if ok then
			container = res
			model = findModel(res, name)
		else
			warn(name, "LoadAsset", id, "failed:", res)
		end
	else
		model = findModel(workspace, name)
	end
	if not model then
		warn(name, ": no Model (id " .. tostring(id) .. ")")
		continue
	end
	local m = model :: Model
	local old = folder:FindFirstChild(name)
	if old and old ~= m then
		old:Destroy()
	end
	m.Name = name
	local report = {}
	for short, sp in a.parts do
		local mp = m:FindFirstChild(name .. "_" .. short, true)
		if mp and mp:IsA("MeshPart") then
			mp.Anchored = true -- template only; the client's clones are unanchored + welded
			mp.CanCollide = false
			mp.CanQuery = false
			mp.CanTouch = false
			local want = Vector3.new(sp.size[1], sp.size[2], sp.size[3])
			local d = mp.Size - want
			local bad = math.max(math.abs(d.X), math.abs(d.Y), math.abs(d.Z)) > TV.SIZE_TOL
			table.insert(report, ("%s %s%s"):format(short, if bad then "SIZE " .. tostring(mp.Size) .. " want " else "",
				if bad then tostring(want) else "ok"))
		else
			table.insert(report, short .. " MISSING")
		end
	end
	m.Parent = folder
	if container and container ~= m then
		container:Destroy()
	end
	print(name, table.concat(report, ", "))
end
modClone:Destroy()
print("TrafficVehicleTemplates:", #folder:GetChildren(), "templates (save the place)")
