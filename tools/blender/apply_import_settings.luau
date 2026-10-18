--[[ MIDNIGHT PATTAYA vis assets: apply the recommended per-family settings to imported models (Studio, Edit mode,
Command Bar). Changes only instances under ServerStorage.VisAssets: Anchored = true, CollisionFidelity and CanCollide
from import_manifest.luau (ServerStorage.VisAssetsManifest), CastShadow off for neon/lamp parts, CanQuery/CanTouch
off for non-colliding parts. Run validate_import.luau afterwards. ]]
local ServerStorage = game:GetService("ServerStorage")
local ROOT = assert(ServerStorage:FindFirstChild("VisAssets"), "ServerStorage.VisAssets missing")
local M = require(assert(ServerStorage:FindFirstChild("VisAssetsManifest"), "manifest missing"):Clone())
local n = 0
for name, exp in M do
	local model = ROOT:FindFirstChild(name, true)
	if not model then
		continue
	end
	for short in exp.parts do
		local mp = model:FindFirstChild(name .. "_" .. short, true)
		if mp and mp:IsA("MeshPart") then
			mp.Anchored = true
			mp.CollisionFidelity = Enum.CollisionFidelity[exp.collision]
			mp.CanCollide = exp.canCollide
			mp.CanQuery = exp.canCollide
			mp.CanTouch = exp.canCollide
			if short == "NeonC" or short == "NeonM" or short == "Lamp" then
				mp.CastShadow = false -- material stays SmoothPlastic; the night script can switch it to Neon
			end
			n += 1
		end
	end
end
print(("vis assets: settings applied to %d MeshParts"):format(n))
