-- Night mode for the Pattaya world, driven by Lighting.ClockTime: lit window tiles on facades (4x4-window night
-- tile, so it is shown at 4x the day tile size), glowing street lamps with their SpotLights on.
-- Works with instance streaming: parts that stream in later get the current mode as they arrive.
local Lighting = game:GetService("Lighting")

local world = workspace:WaitForChild("PattayaWorld", 60)
if not world then
	return
end
local NIGHT_TILES = 4

local function isNight(): boolean
	local t = Lighting.ClockTime
	return t < 6.3 or t > 17.8
end

local night = false

local function apply(inst: Instance)
	if inst:IsA("Texture") then
		local kind = inst:GetAttribute("Facade")
		if not kind then return end
		if inst:GetAttribute("DayU") == nil then
			inst:SetAttribute("DayU", inst.StudsPerTileU)
			inst:SetAttribute("DayV", inst.StudsPerTileV)
		end
		local u, v = inst:GetAttribute("DayU"), inst:GetAttribute("DayV")
		if night then
			inst.Texture = world:GetAttribute("FacadeNight_" .. kind)
			inst.StudsPerTileU, inst.StudsPerTileV = u * NIGHT_TILES, v * NIGHT_TILES
		else
			inst.Texture = world:GetAttribute("Facade_" .. kind)
			inst.StudsPerTileU, inst.StudsPerTileV = u, v
		end
	elseif inst:IsA("BasePart") and inst.Name == "Lamp" then
		inst.Material = if night then Enum.Material.Neon else Enum.Material.SmoothPlastic
		local light = inst:FindFirstChildOfClass("SpotLight")
		if light then light.Enabled = night end
	end
end

local function applyAll()
	for i, d in world:GetDescendants() do
		apply(d)
		if i % 4000 == 0 then task.wait() end
	end
end

world.DescendantAdded:Connect(function(d)
	if d:IsA("Texture") or d.Name == "Lamp" then
		-- attributes/children may arrive a frame later when streamed
		task.defer(apply, d)
	end
end)

night = isNight()
applyAll()
Lighting:GetPropertyChangedSignal("ClockTime"):Connect(function()
	local n = isNight()
	if n ~= night then
		night = n
		applyAll()
	end
end)
