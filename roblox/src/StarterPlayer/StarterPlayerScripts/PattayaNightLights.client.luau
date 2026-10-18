-- Time of day on the client, driven by Lighting.ClockTime (set by PattayaTimeServer):
--  1. Lighting presets dawn / day / dusk / night for a neon coastal city, blended by the clock (Lighting colours,
--     Atmosphere, Bloom, ColorCorrection, the Sky's star count). Client-side only, so the place's template Lighting is never saved
--     changed; the original values are kept and come back when the Lighting attribute PattayaLighting = false.
--  2. Night mode for the Pattaya world: lit window tiles on facades (4x4-window night tile, so it is shown at 4x the
--     day tile size), glowing street lamps with their SpotLights on.
--  3. Floodlights: any BasePart with attribute FloodLight=true anywhere in workspace gets its SpotLight children
--     enabled at night (circuit poles). Lamp and floodlight SpotLights share a budget: only the nearest
--     LOD_SpotCap (60) within range of the camera are on (see section 3; LOD_Enabled = false lifts it). Any BasePart
--     with NightNeon=true turns Neon with its NightColor attribute at night and back to SmoothPlastic + DayColor by
--     day (circuit window bands, lamp heads).
--     Street lamps, neon palette and headlight colour follow the active LightingPreset (section 1).
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
-- VIS-3 (2026-10-19): the look is chosen by the Lighting attribute LightingPreset (live, command bar):
--   MidnightClear (default) | MidnightWet | Dawn | Daylight | Legacy
-- Each preset is a full set of night / dusk / day / dawn keyframes, still blended by ClockTime (KEYS below), plus the
-- street-lamp colours, the neon palette (NightNeon parts and NeonSign props) and the headlight colour. The owner knobs
-- NightExposure and NightSky work on top of every preset. docs/NIGHT_LIGHTING.md has the table and the rationale.
-- Written, not run in Studio: every value except Legacy is a first guess for the owner to compare by eye.

-- Legacy = the values in use before VIS-3, verbatim (uniform violet cast at night, strong bloom).
local LEGACY = {
	night = {
		-- the first night preset was too dark to see the road (owner, 2026-10-18): lifted ambient/exposure, less fog;
		-- the owner then tuned NightExposure to +0.4 by eye (2026-10-19), baked in here (0.55 -> 0.95).
		Ambient = C(74, 70, 104), OutdoorAmbient = C(118, 112, 160), Brightness = 1.7, ExposureCompensation = 0.95,
		EnvironmentDiffuseScale = 0.45, EnvironmentSpecularScale = 0.8, ColorShift_Top = C(90, 60, 160),
		atmo = {Density = 0.26, Offset = 0.12, Color = C(90, 65, 140), Decay = C(40, 25, 70), Glare = 0, Haze = 1.1},
		bloom = {Intensity = 1.0, Size = 24, Threshold = 0.92},
		grade = {Brightness = 0.04, Contrast = 0.1, Saturation = 0.16, TintColor = C(232, 224, 255)},
		-- night sky (owner, 2026-10-19: the sky stayed black). The skybox is unlit at 20:30-21:00 and exposure does
		-- not lift a black sky, so the sky is coloured through the two things that do draw over it: the Atmosphere
		-- (Decay = the sky hue away from the sun, which is the whole sky at night; Haze + Color = the band above the
		-- horizon; a higher Offset lets that haze cover the far skyline like city light) and Sky.StarCount. These
		-- values replace the atmo values above by the Lighting attribute NightSky (0..1, default 1; 0 = the plain
		-- night preset above, with the template's star count).
		skyAtmo = {Offset = 0.32, Color = C(200, 110, 210), Decay = C(70, 50, 150), Haze = 2.6},
		sky = {StarCount = 3000},
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

-- MidnightClear: dry, clear night. The violet of Legacy becomes a steel navy of about the SAME brightness
-- (OutdoorAmbient luminance ~114 vs ~117 in Legacy), so the road stays as readable as at the owner's baseline
-- (exposure 0.95 kept); colour then comes from the warm lamps and the cyan / magenta neon instead of a purple wash.
-- Bloom only on what is really bright (Threshold 1.3), low navy fog, indigo sky with stars.
local CLEAR = {
	night = {
		Ambient = C(60, 68, 96), OutdoorAmbient = C(100, 114, 150), Brightness = 1.7, ExposureCompensation = 0.95,
		EnvironmentDiffuseScale = 0.45, EnvironmentSpecularScale = 0.8, ColorShift_Top = C(120, 140, 190),
		atmo = {Density = 0.22, Offset = 0.1, Color = C(70, 84, 120), Decay = C(28, 34, 80), Glare = 0, Haze = 1.0},
		bloom = {Intensity = 0.45, Size = 24, Threshold = 1.3},
		grade = {Brightness = 0.02, Contrast = 0.12, Saturation = 0.12, TintColor = C(240, 244, 255)},
		skyAtmo = {Offset = 0.22, Color = C(96, 92, 150), Decay = C(34, 42, 118), Haze = 1.8},
		sky = {StarCount = 3000},
	},
	dusk = {
		Ambient = C(70, 58, 78), OutdoorAmbient = C(140, 104, 118), Brightness = 1.7, ExposureCompensation = 0.3,
		EnvironmentDiffuseScale = 0.6, EnvironmentSpecularScale = 0.9, ColorShift_Top = C(255, 150, 100),
		atmo = {Density = 0.3, Offset = 0.15, Color = C(250, 150, 120), Decay = C(90, 60, 120), Glare = 0.4, Haze = 1.8},
		bloom = {Intensity = 0.5, Size = 24, Threshold = 1.2},
		grade = {Brightness = 0.01, Contrast = 0.1, Saturation = 0.14, TintColor = C(255, 238, 228)},
	},
	day = {
		Ambient = C(110, 112, 120), OutdoorAmbient = C(140, 142, 150), Brightness = 2.6, ExposureCompensation = 0,
		EnvironmentDiffuseScale = 1, EnvironmentSpecularScale = 1, ColorShift_Top = C(255, 245, 225),
		atmo = {Density = 0.26, Offset = 0.2, Color = C(200, 218, 235), Decay = C(110, 140, 170), Glare = 0.2, Haze = 1},
		bloom = {Intensity = 0.35, Size = 24, Threshold = 1.6},
		grade = {Brightness = 0, Contrast = 0.06, Saturation = 0.08, TintColor = C(255, 255, 252)},
	},
	dawn = {
		Ambient = C(72, 70, 88), OutdoorAmbient = C(132, 122, 140), Brightness = 1.5, ExposureCompensation = 0.2,
		EnvironmentDiffuseScale = 0.6, EnvironmentSpecularScale = 0.9, ColorShift_Top = C(255, 190, 150),
		atmo = {Density = 0.34, Offset = 0.15, Color = C(255, 196, 170), Decay = C(130, 120, 160), Glare = 0.3, Haze = 2},
		bloom = {Intensity = 0.45, Size = 24, Threshold = 1.25},
		grade = {Brightness = 0, Contrast = 0.06, Saturation = 0.1, TintColor = C(255, 242, 232)},
	},
}

-- a copy of a keyframe set with some fields replaced (nested tables merged one level deep)
local function variant(base, changes)
	local out = {}
	for name, frame in base do
		local f = table.clone(frame)
		for k, v in frame do
			if type(v) == "table" then
				f[k] = table.clone(v)
			end
		end
		for k, v in changes[name] or {} do
			if type(v) == "table" and type(f[k]) == "table" then
				for k2, v2 in v do
					f[k][k2] = v2
				end
			else
				f[k] = v
			end
		end
		out[name] = f
	end
	return out
end

-- MidnightWet: after-rain city. Same navy base, a touch more humid (fog, lamp halo), full environment specular so
-- smooth / wet surfaces pick up the sky, slightly stronger grade so wet colours pop. Pairs with RoadLook "wet"
-- (PattayaRoadLook follows the preset when the RoadLook attribute is not set). Day keyframe: humid overcast.
local WET = variant(CLEAR, {
	night = {Ambient = C(54, 62, 90), OutdoorAmbient = C(94, 108, 144), ExposureCompensation = 1.0,
		EnvironmentDiffuseScale = 0.4, EnvironmentSpecularScale = 1.0,
		atmo = {Density = 0.26, Color = C(72, 86, 122), Haze = 1.3},
		bloom = {Intensity = 0.55, Threshold = 1.2},
		grade = {Contrast = 0.14, Saturation = 0.16, TintColor = C(236, 242, 255)},
		skyAtmo = {Haze = 2.0}, sky = {StarCount = 1500}},
	dusk = {EnvironmentSpecularScale = 1.0, atmo = {Density = 0.34, Haze = 2.0}},
	day = {Brightness = 2.2, OutdoorAmbient = C(132, 136, 146), EnvironmentSpecularScale = 1.0,
		atmo = {Density = 0.32, Color = C(190, 200, 210), Haze = 1.6, Glare = 0.1},
		grade = {Contrast = 0.08, Saturation = 0.06}},
	dawn = {EnvironmentSpecularScale = 1.0, atmo = {Density = 0.38, Haze = 2.2}},
})

-- Dawn: the blue-hour / golden-hour candidate. Night is a lighter blue-hour navy with a soft horizon glow (the
-- "TimeLock 19.6" look from docs/TIME_OF_DAY.md without touching the clock); dawn and dusk are warmer, more golden.
local DAWN = variant(CLEAR, {
	night = {Ambient = C(70, 80, 112), OutdoorAmbient = C(112, 128, 170), ColorShift_Top = C(130, 150, 210),
		atmo = {Color = C(90, 110, 160), Decay = C(46, 60, 140)},
		skyAtmo = {Offset = 0.26, Color = C(150, 120, 170), Decay = C(60, 78, 170), Haze = 2.0}, sky = {StarCount = 1500}},
	dusk = {ColorShift_Top = C(255, 170, 100), atmo = {Color = C(255, 170, 120), Glare = 0.5, Haze = 2.4},
		grade = {Saturation = 0.16, TintColor = C(255, 236, 220)}},
	day = {ColorShift_Top = C(255, 232, 200), grade = {Saturation = 0.12, TintColor = C(255, 248, 236)}},
	dawn = {ExposureCompensation = 0.3, ColorShift_Top = C(255, 180, 120),
		atmo = {Color = C(255, 180, 140), Glare = 0.5, Haze = 2.4}, bloom = {Intensity = 0.5, Threshold = 1.2},
		grade = {Saturation = 0.14, TintColor = C(255, 238, 222)}},
})

-- Daylight: the brightest, most readable set. Night ambient and exposure ABOVE the owner baseline (fallback if night
-- is still too dark, e.g. on phones), crisp clear tropical day.
local DAYLIGHT = variant(CLEAR, {
	night = {Ambient = C(78, 86, 112), OutdoorAmbient = C(124, 134, 166), ExposureCompensation = 1.1,
		EnvironmentDiffuseScale = 0.5, bloom = {Intensity = 0.4, Threshold = 1.35}, grade = {Contrast = 0.08},
		skyAtmo = {Decay = C(44, 56, 120)}, sky = {StarCount = 2000}},
	day = {Brightness = 3.0, OutdoorAmbient = C(150, 152, 158), atmo = {Density = 0.22, Haze = 0.8},
		grade = {Contrast = 0.08, Saturation = 0.12}},
})

-- Street lamps (parts named Lamp and their SpotLights): warm sodium orange. brightness scales the builder's value
-- (2.2 city, 1.8 promenade); no light is added. neon: NightNeon colours and NeonSign props whose hue is cyan-ish or
-- magenta-ish are snapped to the owner palette; other hues (warm windows, signal lamps, yellow, green) are kept.
local MIDNIGHT_LAMP = {light = C(255, 176, 96), part = C(255, 170, 80), brightness = 1.0}
local MIDNIGHT_NEON = {cyan = C(0, 223, 255), magenta = C(255, 43, 214)}
local HEAD_WARM = C(255, 241, 222) -- natural warm white (about 4,500 K), not blue-white
local SETS = {
	MidnightClear = {keys = CLEAR, lamp = MIDNIGHT_LAMP, neon = MIDNIGHT_NEON, head = HEAD_WARM, road = "dry"},
	MidnightWet = {keys = WET, lamp = {light = C(255, 176, 96), part = C(255, 170, 80), brightness = 1.15},
		neon = MIDNIGHT_NEON, head = HEAD_WARM, road = "wet"},
	Dawn = {keys = DAWN, lamp = MIDNIGHT_LAMP, neon = MIDNIGHT_NEON, head = HEAD_WARM, road = "dry"},
	Daylight = {keys = DAYLIGHT, lamp = {light = C(255, 190, 120), part = C(255, 184, 104), brightness = 1.1},
		neon = MIDNIGHT_NEON, head = HEAD_WARM, road = "dry"},
	-- Legacy: lamps, neon and headlights exactly as the builders made them, road look off
	Legacy = {keys = LEGACY, lamp = nil, neon = nil, head = C(255, 244, 220), road = "off"},
}
local DEFAULT_SET = "MidnightClear"
local warnedPreset: any = nil
local function currentSetName(): string
	local v = Lighting:GetAttribute("LightingPreset")
	if type(v) == "string" and SETS[v] then
		return v
	end
	if v ~= nil and warnedPreset ~= v then
		warnedPreset = v
		warn(`[PattayaLighting] unknown LightingPreset {tostring(v)}; using {DEFAULT_SET} (MidnightClear, MidnightWet, Dawn, Daylight, Legacy)`)
	end
	return DEFAULT_SET
end
local activeName = currentSetName()
local function activeSet()
	return SETS[activeName]
end
local presetListeners = {}
Lighting:GetAttributeChangedSignal("LightingPreset"):Connect(function()
	local name = currentSetName()
	if name == activeName then
		return
	end
	activeName = name
	print("[PattayaLighting] preset " .. name)
	for _, fn in presetListeners do
		task.spawn(fn)
	end
end)
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
-- the template Sky is only adjusted, never created (a new Sky would swap in Roblox's default skybox textures);
-- its original values are saved the first time it is seen and restored by PattayaLighting = false
local SKY_PROPS = {"StarCount"}
local sky: any = nil
local skySaved = {}
local function findSky(): any
	if sky and sky.Parent == Lighting then
		return sky
	end
	local s = Lighting:FindFirstChildOfClass("Sky")
	if s and s ~= sky then
		sky = s
		skySaved = {}
		for _, prop in SKY_PROPS do
			skySaved[prop] = (s :: any)[prop]
		end
	end
	return s
end

local function presetAt(t: number)
	local keys = activeSet().keys
	for i = 1, #KEYS - 1 do
		local a, b = KEYS[i], KEYS[i + 1]
		if t >= a[1] and t <= b[1] then
			local f = if b[1] > a[1] then (t - a[1]) / (b[1] - a[1]) else 0
			return keys[a[2]], keys[b[2]], f, a[2], b[2]
		end
	end
	return keys.night, keys.night, 0, "night", "night"
end

local presetsOn = false
local function applyPreset()
	local pa, pb, f, na, nb = presetAt(Lighting.ClockTime % 24)
	local nightFrame = activeSet().keys.night
	for _, prop in LIGHTING_PROPS do
		L[prop] = lerp(pa[prop], pb[prop], f)
	end
	-- how "night" the blend is: 1 in the night preset, ramping in and out across dusk and dawn
	local w = (if na == "night" then 1 - f else 0) + (if nb == "night" then f else 0)
	-- live tuning knob: Lighting attribute NightExposure (e.g. 0.3 brighter, -0.3 darker) scaled by how "night" it is
	local boost = Lighting:GetAttribute("NightExposure")
	if type(boost) == "number" and boost ~= 0 then
		L.ExposureCompensation += boost * w
	end
	-- second knob: Lighting attribute NightSky (0..1, default 1) = how much of the night sky look is used
	local skyKnob = Lighting:GetAttribute("NightSky")
	local k = math.clamp(if type(skyKnob) == "number" then skyKnob else 1, 0, 1) * w
	local skyAtmo = nightFrame.skyAtmo
	for key, e in effects do
		local inst = e.inst
		if e.created and inst.Parent ~= Lighting then
			inst.Parent = Lighting
		end
		for _, prop in EFFECT_PROPS[key] do
			local v = lerp(pa[key][prop], pb[key][prop], f)
			if key == "atmo" and k > 0 and skyAtmo[prop] ~= nil then
				v = lerp(v, skyAtmo[prop], k)
			end
			inst[prop] = v
		end
	end
	local s = findSky()
	if s then
		for _, prop in SKY_PROPS do
			-- from the template value by day to the night value at night (whole numbers for StarCount)
			local v = math.floor(lerp(skySaved[prop], nightFrame.sky[prop], k) + 0.5)
			if s[prop] ~= v then
				s[prop] = v
			end
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
	if sky and sky.Parent then
		for prop, v in skySaved do
			sky[prop] = v
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
-- SpotLight budget (lamps and floodlights): at night only the nearest LOD_SpotCap SpotLights within range of the
-- camera are enabled (lamps LOD_LampLightRange, floodlights LOD_FloodLightRange; a light behind the camera counts
-- 1.5x as far). By day all are off, as before. Re-evaluated 4 times a second; Enabled is only written when a light's
-- state changes. workspace attribute LOD_Enabled = false lifts the cap and the ranges (every light on at night, the
-- old behaviour). The knobs are workspace attributes so ServerStorage.PattayaPerfProfile can set them.
local SPOT_DEFAULTS = {LOD_SpotCap = 60, LOD_LampLightRange = 350, LOD_FloodLightRange = 550}
local function spotKnob(name: string): number
	local v = workspace:GetAttribute(name)
	return if type(v) == "number" then v else SPOT_DEFAULTS[name]
end
type Spot = {flood: boolean, pos: Vector3, on: boolean, c0: Color3, b0: number}
local spots: {[SpotLight]: Spot} = {}
-- lamp SpotLights take the preset's lamp colour and a brightness scale of the builder's value (c0 / b0 kept, so
-- Legacy and any later preset start from the original); floodlights (circuit) keep their own colour
local function styleSpot(light: SpotLight, s: Spot)
	if s.flood then
		return
	end
	local lamp = activeSet().lamp
	local col = if lamp then lamp.light else s.c0
	local br = if lamp then s.b0 * lamp.brightness else s.b0
	if light.Color ~= col then light.Color = col end
	if light.Brightness ~= br then light.Brightness = br end
end
local function registerSpot(light: SpotLight, flood: boolean)
	if spots[light] then
		return
	end
	local p = light.Parent :: BasePart
	local s: Spot = {flood = flood, pos = p.Position, on = light.Enabled, c0 = light.Color, b0 = light.Brightness}
	spots[light] = s
	if light.Enabled and not night then
		light.Enabled = false
		s.on = false
	end
	styleSpot(light, s)
end
local spotAcc = 1
local function updateSpots()
	spotAcc = 0
	local cap, lampR, floodR = math.huge, math.huge, math.huge
	if workspace:GetAttribute("LOD_Enabled") ~= false then
		cap, lampR, floodR = spotKnob("LOD_SpotCap"), spotKnob("LOD_LampLightRange"), spotKnob("LOD_FloodLightRange")
	end
	local want = {}
	if night then
		local cam = workspace.CurrentCamera
		local cf = if cam then cam.CFrame else CFrame.identity
		local origin, look = cf.Position, cf.LookVector
		local near = {}
		for light, s in spots do
			local off = s.pos - origin
			local d = off.Magnitude
			if off:Dot(look) < 0 then
				d *= 1.5
			end
			if d < (if s.flood then floodR else lampR) then
				table.insert(near, {light, d})
			end
		end
		if #near > cap then
			table.sort(near, function(a, b) return a[2] < b[2] end)
		end
		for i = 1, math.min(#near, cap) do
			want[near[i][1]] = true
		end
	end
	for light, s in spots do
		if not light:IsDescendantOf(workspace) then
			spots[light] = nil -- streamed out (a light that streams in again is a new instance)
			continue
		end
		local on = want[light] == true
		if s.on ~= on then
			s.on = on
			light.Enabled = on
		end
	end
end
RunService.Heartbeat:Connect(function(dt)
	spotAcc += dt
	if spotAcc >= 0.25 then
		updateSpots()
	end
end)

local function applyFlood(part: BasePart)
	for _, c in part:GetChildren() do
		if c:IsA("SpotLight") then
			registerSpot(c, true)
		end
	end
end
-- NightNeon=true parts (circuit window bands, lamp heads): Neon + NightColor at night, SmoothPlastic + DayColor by day
-- neon palette of the active preset: cyan-ish hues -> palette cyan, magenta/pink hues -> palette magenta; others kept
local function neonColor(c: Color3): Color3
	local pal = activeSet().neon
	if not pal then
		return c
	end
	local h, s, v = c:ToHSV()
	if s < 0.45 or v < 0.35 then
		return c
	end
	if h >= 0.45 and h <= 0.58 then
		return pal.cyan
	elseif h >= 0.80 and h <= 0.97 then
		return pal.magenta
	end
	return c
end
local neons = setmetatable({}, {__mode = "k"})
local function applyNeon(part: BasePart)
	local col = part:GetAttribute(if night then "NightColor" else "DayColor")
	part.Material = if night then Enum.Material.Neon else Enum.Material.SmoothPlastic
	if typeof(col) == "Color3" then
		part.Color = if night then neonColor(col) else col
	end
end
-- always-Neon sign props (PattayaBuilder "NeonSign"): recoloured through the palette, original colour kept
local signOrig: {[BasePart]: Color3} = setmetatable({}, {__mode = "k"}) :: any
local function applySign(part: BasePart)
	local orig = signOrig[part]
	if not orig then
		orig = part.Color
		signOrig[part] = orig
	end
	part.Color = neonColor(orig)
end
-- street-lamp heads (parts named Lamp): Neon in the preset's warm lamp colour at night, the builder colour by day
local lampOrig: {[BasePart]: Color3} = setmetatable({}, {__mode = "k"}) :: any
local function applyLamp(part: BasePart)
	local orig = lampOrig[part]
	if not orig then
		orig = part.Color
		lampOrig[part] = orig
	end
	local lamp = activeSet().lamp
	part.Material = if night then Enum.Material.Neon else Enum.Material.SmoothPlastic
	part.Color = if night and lamp then lamp.part else orig
end
workspace.DescendantAdded:Connect(function(d)
	if d:IsA("SpotLight") then
		local p = d.Parent
		if p and p:IsA("BasePart") then
			if p:GetAttribute("FloodLight") == true then
				registerSpot(d, true)
			elseif p.Name == "Lamp" then
				registerSpot(d, false) -- a lamp's SpotLight that streamed in after its part
			end
		end
	elseif d:IsA("BasePart") then
		if d:GetAttribute("FloodLight") == true then
			task.defer(applyFlood, d)
		end
		if d:GetAttribute("NightNeon") == true then
			neons[d] = true
			task.defer(applyNeon, d)
		end
	end
end)
task.spawn(function()
	for i, d in workspace:GetDescendants() do
		if d:IsA("BasePart") then
			if d:GetAttribute("FloodLight") == true then
				applyFlood(d)
			end
			if d:GetAttribute("NightNeon") == true then
				neons[d] = true
				applyNeon(d)
			end
		end
		if i % 5000 == 0 then task.wait() end
	end
end)
onNightChanged(function()
	updateSpots()
	for p in neons do
		if p.Parent then applyNeon(p) end
	end
end)

-- 4. Car lights ----------------------------------------------------------------------------------------------------
local CAR_LIGHT_RANGE = 350 -- studs from the camera
local MAX_LIT_CARS = 8 -- including your own
local TAIL_COLOR = Color3.fromRGB(255, 30, 30) -- head colour: the active preset's `head` (natural warm white)
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
	local HEAD_COLOR = activeSet().head
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
		applyLamp(inst)
		local light = inst:FindFirstChildOfClass("SpotLight")
		if light then registerSpot(light, false) end -- switched by the SpotLight budget (section 3)
	elseif inst:IsA("BasePart") and inst.Name == "NeonSign" then
		applySign(inst)
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

-- LightingPreset changed: restyle what the preset colours (only registered parts and lights, no world scan); car
-- lights are dropped and come back on the next car-light tick (0.3 s) with the new headlight colour
table.insert(presetListeners, function()
	for light, s in spots do
		if light.Parent then styleSpot(light, s) end
	end
	for p in lampOrig do
		if p.Parent then applyLamp(p) end
	end
	for p in signOrig do
		if p.Parent then applySign(p) end
	end
	for p in neons do
		if p.Parent then applyNeon(p) end
	end
	for c in lit do
		removeLights(c)
	end
end)

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
	if d:IsA("Texture") or d.Name == "Lamp" or d.Name == "NeonSign" then
		-- attributes/children may arrive a frame later when streamed
		task.defer(apply, d)
	end
end)
applyAll()
