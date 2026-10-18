-- VIS-7.1 palm LOD starter (leader, 2026-10-19): runs ReplicatedStorage.VisMeshPalmLOD on the client so the kit mesh
-- palms (workspace.PattayaWorld.VisMeshPalms) switch to their 2-part impostor beyond FullRange (400 studs, attribute
-- on the folder). The module is installed in ReplicatedStorage by tools/studio/install.ps1 (source: ServerStorage copy
-- roblox/src/ServerStorage/VisMeshPalmLOD.luau). Without the module nothing happens: the full mesh shows up to
-- PattayaLOD's prop range, as before.
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local mod = ReplicatedStorage:WaitForChild("VisMeshPalmLOD", 10)
if not mod then
	return
end
local ok, err = pcall(function()
	require(mod).Start()
end)
if not ok then
	warn("[VisMeshPalmLOD] " .. tostring(err))
end
