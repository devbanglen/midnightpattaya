-- MIDNIGHT PATTAYA — Studio installer. Run in the command bar (edit mode) while tools/studio/install.ps1 serves the
-- bundles. (Re)creates every script and data module from the repo without deleting anything else in the place.
-- After it: build the world if the place is empty (see docs/ROBLOX_INTEGRATION.md "Rebuild from scratch").
-- Keys may name sub-folders (e.g. ReplicatedStorage/MidnightUI/Theme): folder() creates a Folder per extra segment, so
-- the HUD modules land in ReplicatedStorage.MidnightUI as ModuleScripts (scripts.json, from install.ps1).
local Http = game:GetService("HttpService")
local was = Http.HttpEnabled
Http.HttpEnabled = true
local function get(n) return Http:GetAsync("http://localhost:8765/" .. n, true) end
local SS = game:GetService("ServerStorage")
local containers = {
	ServerScriptService = game:GetService("ServerScriptService"),
	ServerStorage = SS,
	ReplicatedStorage = game:GetService("ReplicatedStorage"),
	ReplicatedFirst = game:GetService("ReplicatedFirst"),
	StarterPlayerScripts = game:GetService("StarterPlayer"):WaitForChild("StarterPlayerScripts"),
	PattayaData = nil, -- folders below are created on demand under ServerStorage
}
local function folder(path: string): Instance
	local parent = SS
	for seg in path:gmatch("[^/]+") do
		if containers[seg] and parent == SS and seg ~= "PattayaData" then
			parent = containers[seg]
		else
			local f = parent:FindFirstChild(seg)
			if not f then
				f = Instance.new("Folder")
				f.Name = seg
				f.Parent = parent
			end
			parent = f
		end
	end
	return parent
end
local function install(bundle, isScript: boolean)
	local n = 0
	for key, src in bundle do
		local dir, name = key:match("^(.*)/([^/]+)$")
		local class = "ModuleScript"
		if isScript then
			if name:match("%.server$") then class = "Script"; name = name:gsub("%.server$", "")
			elseif name:match("%.client$") then class = "LocalScript"; name = name:gsub("%.client$", "") end
		end
		local parent = folder(dir)
		local inst = parent:FindFirstChild(name)
		if not inst or inst.ClassName ~= class then
			if inst then inst:Destroy() end
			inst = Instance.new(class)
			inst.Name = name
			inst.Parent = parent
		end
		inst.Source = src
		n += 1
		if n % 50 == 0 then task.wait() end
	end
	return n
end
local ok, err = pcall(function()
	local scripts = Http:JSONDecode(get("scripts.json"))
	local data = Http:JSONDecode(get("data.json"))
	print(("installed %d scripts, %d data modules"):format(install(scripts, true), install(data, false)))
	pcall(function() get("quit") end)
end)
Http.HttpEnabled = was
if not ok then warn("install failed: " .. tostring(err)) end
print("HttpEnabled restored to " .. tostring(Http.HttpEnabled))
