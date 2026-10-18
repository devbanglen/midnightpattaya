-- Time of day on the client, driven by Lighting.ClockTime (set by PattayaTimeServer):
--  1. Lighting presets dawn / day / dusk / night for a neon coastal city, blended by the clock (Lighting colours,
--     Atmosphere, Bloom, ColorCorrection). Client-side only, so the place's template Lighting is never saved
--     changed; the original values are kept and come back when the Lighting attribute PattayaLighting = false.
--  2. Night mode for the Pattaya world: lit window tiles on facades (4x4-window night tile, so it is shown at 4x the
--     day tile size), glowing street lamps with their SpotLights on.
--  3. Floodlights: any BasePart with attribute FloodLight=true anywhere in workspace gets its SpotLight children
--     enabled at night (circuit poles, beam emitters, lamp posts). Any BasePart with NightNeon=true turns Neon with
--     its NightColor attribute at night and back to SmoothPlastic + DayColor by day (circuit window bands, lamp heads).
--  4. Car lights at night: head and tail lights on the local driver's car and the nearest cars (local Attachments
--     with lights and glow sprites; the car models on the server are not changed).
-- Works with instance streaming: parts that stream in later get the current mode as they arrive.
local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local L: any = Lighting

local function isNight(): boolean
	local t = Lighting.ClockTime
	return t < 6.3 or t > 17.8
end

local night = isNight()
local nightListeners = {}
local function onNightChanged(fn)
	table.insert(nightListeners, fn)
end

-- 1. Lighting presets ------------------------------------------------------------------------------------------------
local C = Color3.fromRGB
local PRESETS = {
	night = {
		Ambient = C(22, 18, 42), OutdoorAmbient = C(44, 40, 82), Brightness = 1.2, ExposureCompensation = 0.1,
		EnvironmentDiffuseScale = 0.25, EnvironmentSpecularScale = 0.8, ColorShift_Top = C(70, 40, 140),
		atmo = {Density = 0.33, Offset = 0.1, Color = C(70, 45, 120), Decay = C(25, 12, 50), Glare = 0, Haze = 1.6},
		bloom = {Intensity = 1.1, Size = 28, Threshold = 0.9},
		grade = {Brightness = 0, Contrast = 0.12, Saturation = 0.18, TintColor = C(228, 218, 255)},
	},
	dusk = {
		Ambient = C(70, 50, 72), OutdoorAmbient = C(140, 92, 112), Brightness = 1.7, ExposureCompensation = 0,
		EnvironmentDiffuseScale = 0.6, EnvironmentSpecularScale = 0.9, ColorShift_Top = C(255, 140, 110),
		atmo = {Density = 0.36, Offset = 0.15, Color = C(255, 150, 140), Decay = C(120, 60, 130), Glare = 0.4, Haze = 2},
		bloom = {Intensity = 0.9, Size = 24, Threshold = 0.95},
		grade = {Brightness = 0, Contrast = 0.08, Saturation = 0.2, TintColor = C(255, 232, 232)},
	},
	day = {
		Ambient = C(105, 105, 115), OutdoorAmbient = C(140, 140, 150), Brightness = 2.6, ExposureCompensation = 0,
		EnvironmentDiffuseScale = 1, EnvironmentSpecularScale = 1, ColorShift_Top = C(255, 245, 225),
		atmo = {Density = 0.28, Offset = 0.2, Color = C(200, 215, 235), Decay = C(110, 140, 170), Glare = 0.2, Haze = 1},
		bloom = {Intensity = 0.5, Size = 24, Threshold = 1.4},
		grade = {Brightness = 0, Contrast = 0.03, Saturation = 0.08, TintColor = C(255, 255, 255)},
	},
	dawn = {
		Ambient = C(70, 60, 82), OutdoorAmbient = C(130, 112, 140), Brightness = 1.5, ExposureCompensation = 0,
		EnvironmentDiffuseScale = 0.6, EnvironmentSpecularScale = 0.9, ColorShift_Top = C(255, 185, 160),
		atmo = {Density = 0.38, Offset = 0.15, Color = C(255, 190, 170), Decay = C(140, 110, 150), Glare = 0.3, Haze = 2.2},
		bloom = {Intensity = 0.8, Size = 24, Threshold = 1.1},
		grade = {Brightness = 0, Contrast = 0.05, Saturation = 0.1, TintColor = C(255, 240, 235)},
	},
}
-- keyframes {ClockTime, preset}; blended linearly between neighbours
local KEYS = {{0, "night"}, {4.8, "night"}, {6.2, "dawn"}, {8, "day"}, {16.5, "day"}, {18.3, "dusk"}, {19.6, "night"},
	{24, "night"}}
local LIGHTING_PROPS = {"Ambient", "OutdoorAmbient", "Brightness", "ExposureCompensation", "EnvironmentDiffuseScale",
	"EnvironmentSpecularScale", "ColorShift_Top"}
local EFFECT_PROPS = {
	atmo = {"Density", "Offset", "Color", "Decay", "Glare", "Haze"},
	bloom = {"Intensity", "Size", "Threshold"},
	grade = {"Brightness", "Contrast", "Saturation", "TintColor"},
}

local function lerp(a, b, f)
	if typeof(a) == "Color3" then
		return a:Lerp(b, f)
	end
	return a + (b - a) * f
end

-- the template's original values, restored by PattayaLighting = false
local originalLighting = {}
for _, prop in LIGHTING_PROPS do
	originalLighting[prop] = L[prop]
end
-- reuse the template's own effect if it has one (two blooms or atmospheres stack badly), else make ours
local effects = {}
local function effect(key: string, class: string, name: string)
	local e = Lighting:FindFirstChildOfClass(class)
	local created = false
	if not e then
		e = Instance.new(class)
		e.Name = name
		created = true
	end
	local inst: any = e
	local saved = {}
	for _, prop in EFFECT_PROPS[key] do
		saved[prop] = inst[prop]
	end
	effects[key] = {inst = inst, created = created, saved = saved}
end
effect("atmo", "Atmosphere", "PattayaAtmosphere")
effect("bloom", "BloomEffect", "PattayaBloom")
effect("grade", "ColorCorrectionEffect", "PattayaGrade")

local function presetAt(t: number)
	for i = 1, #KEYS - 1 do
		local a, b = KEYS[i], KEYS[i + 1]
		if t >= a[1] and t <= b[1] then
			local f = if b[1] > a[1] then (t - a[1]) / (b[1] - a[1]) else 0
			return PRESETS[a[2]], PRESETS[b[2]], f
		end
	end
	return PRESETS.night, PRESETS.night, 0
end

local presetsOn = false
local function applyPreset()
	local pa, pb, f = presetAt(Lighting.ClockTime % 24)
	for _, prop in LIGHTING_PROPS do
		L[prop] = lerp(pa[prop], pb[prop], f)
	end
	for key, e in effects do
		local inst = e.inst
		if e.created and inst.Parent ~= Lighting then
			inst.Parent = Lighting
		end
		for _, prop in EFFECT_PROPS[key] do
			inst[prop] = lerp(pa[key][prop], pb[key][prop], f)
		end
	end
	presetsOn = true
end

local function revertPreset()
	if not presetsOn then
		return
	end
	for prop, v in originalLighting do
		L[prop] = v
	end
	for _, e in effects do
		local inst = e.inst
		if e.created then
			inst.Parent = nil
		else
			for prop, v in e.saved do
				inst[prop] = v
			end
		end
	end
	presetsOn = false
end

local presetAcc = 1
RunService.Heartbeat:Connect(function(dt)
	presetAcc += dt
	if presetAcc < 0.25 then -- 4 updates a second is plenty for a 24-minute day
		return
	end
	presetAcc = 0
	if Lighting:GetAttribute("PattayaLighting") == false then
		revertPreset()
	else
		applyPreset()
	end
end)

-- 3. Floodlights (anywhere in workspace) ---------------------------------------------------------------------------
local floods = setmetatable({}, {__mode = "k"})
local function applyFlood(part: BasePart)
	for _, c in part:GetChildren() do
		if c:IsA("SpotLight") then
			c.Enabled = night
		end
	end
end
-- NightNeon=true parts (circuit window bands, lamp heads): Neon + NightColor at night, SmoothPlastic + DayColor by day
local neons = setmetatable({}, {__mode = "k"})
local function applyNeon(part: BasePart)
	local col = part:GetAttribute(if night then "NightColor" else "DayColor")
	part.Material = if night then Enum.Material.Neon else Enum.Material.SmoothPlastic
	if typeof(col) == "Color3" then part.Color = col end
end
local function track(d: Instance)
	if d:IsA("BasePart") then
		if d:GetAttribute("FloodLight") == true then
			floods[d] = true
			task.defer(applyFlood, d)
		end
		if d:GetAttribute("NightNeon") == true then
			neons[d] = true
			task.defer(applyNeon, d)
		end
	end
end
workspace.DescendantAdded:Connect(function(d)
	if d:IsA("SpotLight") then
		local p = d.Parent
		if p and p:IsA("BasePart") and p:GetAttribute("FloodLight") == true then
			floods[p] = true
			d.Enabled = night
		end
	else
		track(d)
	end
end)
task.spawn(function()
	for i, d in workspace:GetDescendants() do
		track(d)
		if i % 5000 == 0 then task.wait() end
	end
end)
onNightChanged(function()
	for p in floods do
		if p.Parent then applyFlood(p) end
	end
	for p in neons do
		if p.Parent then applyNeon(p) end
	end
end)

-- 4. Car lights ----------------------------------------------------------------------------------------------------
local CAR_LIGHT_RANGE = 350 -- studs from the camera
local MAX_LIT_CARS = 8 -- including your own
local HEAD_COLOR, TAIL_COLOR = Color3.fromRGB(255, 244, 220), Color3.fromRGB(255, 30, 30)
local lit = {} -- [chassis] = {Attachment}

local function myChassis(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

local function flare(att: Attachment, color: Color3, size: number)
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromScale(size, size)
	bb.LightInfluence = 0
	bb.MaxDistance = CAR_LIGHT_RANGE
	local f = Instance.new("Frame")
	f.Size = UDim2.fromScale(1, 1)
	f.BackgroundColor3 = color
	f.BorderSizePixel = 0
	f.BackgroundTransparency = 0.15
	Instance.new("UICorner", f).CornerRadius = UDim.new(0.5, 0)
	f.Parent = bb
	bb.Parent = att
end

local function addLights(chassis: BasePart, mine: boolean)
	local half = chassis.Size.Z / 2
	local w = math.min(chassis.Size.X / 2 - 0.8, 2.8)
	local made = {}
	local function att(name: string, cf: CFrame): Attachment
		local a = Instance.new("Attachment")
		a.Name = name
		a.CFrame = cf
		a.Parent = chassis
		table.insert(made, a)
		return a
	end
	-- front is -Z (LookVector); the beam is tilted 8 degrees down
	local head = att("PattayaHeadBeam", CFrame.new(0, 0.6, -half - 0.3) * CFrame.Angles(math.rad(-8), 0, 0))
	local beam = Instance.new("SpotLight")
	beam.Face = Enum.NormalId.Front
	beam.Color = HEAD_COLOR
	beam.Brightness = if mine then 3.5 else 2.5
	beam.Range = if mine then 70 else 45
	beam.Angle = 65
	beam.Shadows = false
	beam.Parent = head
	local tail = att("PattayaTailGlow", CFrame.new(0, 0.8, half + 0.4))
	local glow = Instance.new("PointLight")
	glow.Color = TAIL_COLOR
	glow.Brightness = 1.5
	glow.Range = 10
	glow.Shadows = false
	glow.Parent = tail
	for _, s in {-1, 1} do
		flare(att("PattayaHeadFlare", CFrame.new(s * w, 0.9, -half - 0.1)), HEAD_COLOR, 1.3)
		flare(att("PattayaTailFlare", CFrame.new(s * w, 1.1, half + 0.1)), TAIL_COLOR, 1.0)
	end
	lit[chassis] = made
end

local function removeLights(chassis: BasePart)
	for _, a in lit[chassis] or {} do
		a:Destroy()
	end
	lit[chassis] = nil
end

local carAcc = 1
RunService.Heartbeat:Connect(function(dt)
	carAcc += dt
	if carAcc < 0.3 then
		return
	end
	carAcc = 0
	local want = {}
	if night then
		local cam = workspace.CurrentCamera
		local origin = if cam then cam.CFrame.Position else Vector3.zero
		local mine = myChassis()
		local list = {}
		for _, m in workspace:GetChildren() do
			if m:IsA("Model") and (m:GetAttribute("RaceCar") or m:GetAttribute("RivalBot")) then
				local c = m.PrimaryPart
				if c and c ~= mine then
					local d = (c.Position - origin).Magnitude
					if d < CAR_LIGHT_RANGE then table.insert(list, {c, d}) end
				end
			end
		end
		table.sort(list, function(a, b) return a[2] < b[2] end)
		if mine then
			want[mine] = true
		end
		for i = 1, math.min(#list, MAX_LIT_CARS - (if mine then 1 else 0)) do
			want[list[i][1]] = true
		end
		for c in want do
			if not lit[c] then addLights(c, c == mine) end
		end
	end
	for c in lit do
		if not want[c] or not c.Parent then removeLights(c) end
	end
end)

-- 2. Pattaya world: facades and street lamps -------------------------------------------------------------------------
local world: Instance? = nil
local NIGHT_TILES = 4

local function apply(inst: Instance)
	local w = world
	if not w then return end
	if inst:IsA("Texture") then
		local kind = inst:GetAttribute("Facade")
		if not kind then return end
		if inst:GetAttribute("DayU") == nil then
			inst:SetAttribute("DayU", inst.StudsPerTileU)
			inst:SetAttribute("DayV", inst.StudsPerTileV)
		end
		local u, v = inst:GetAttribute("DayU"), inst:GetAttribute("DayV")
		if night then
			inst.Texture = w:GetAttribute("FacadeNight_" .. kind)
			inst.StudsPerTileU, inst.StudsPerTileV = u * NIGHT_TILES, v * NIGHT_TILES
		else
			inst.Texture = w:GetAttribute("Facade_" .. kind)
			inst.StudsPerTileU, inst.StudsPerTileV = u, v
		end
	elseif inst:IsA("BasePart") and inst.Name == "Lamp" then
		inst.Material = if night then Enum.Material.Neon else Enum.Material.SmoothPlastic
		local light = inst:FindFirstChildOfClass("SpotLight")
		if light then light.Enabled = night end
	end
end

local function applyAll()
	local w = world
	if not w then return end
	for i, d in w:GetDescendants() do
		apply(d)
		if i % 4000 == 0 then task.wait() end
	end
end
onNightChanged(applyAll)

Lighting:GetPropertyChangedSignal("ClockTime"):Connect(function()
	local n = isNight()
	if n ~= night then
		night = n
		for _, fn in nightListeners do
			task.spawn(fn)
		end
	end
end)

world = workspace:WaitForChild("PattayaWorld", 60)
if not world then
	return
end
world.DescendantAdded:Connect(function(d)
	if d:IsA("Texture") or d.Name == "Lamp" then
		-- attributes/children may arrive a frame later when streamed
		task.defer(apply, d)
	end
end)
applyAll()
