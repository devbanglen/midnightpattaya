-- Road surface look (MIDNIGHT PATTAYA, VIS-3), client only, reversible. Written, not run in Studio.
--
-- Lighting attribute RoadLook = "dry" | "wet" | "off" (live, from the server or client command bar):
--   dry  road slabs (Road, Junction, Joint) -> MaterialLibrary.DryAsphalt (Asphalt grain, 62,63,68, no reflection);
--        markings (Centre, Dash, ZebraStripe) -> RoadPaint, their own colour (white / yellow) a little brighter
--   wet  road slabs -> WetAsphalt (SmoothPlastic, darker 34,36,42, Reflectance 0.14: sharp lamp/headlight highlights
--        and a sky reflection); markings -> RoadPaintWet (Reflectance 0.06), colour brighter
--   off  every touched part gets back exactly what the builder gave it (Material, Color, Reflectance, variant)
-- When RoadLook is not set, the look follows Lighting.LightingPreset: MidnightWet -> wet, Legacy -> off, else dry.
-- Sidewalks are never touched. Nothing outside workspace.PattayaWorld is touched (circuit track: not yet).
--
-- Cost: parts are registered when they stream in (DescendantAdded) or by a one-off chunked scan at start, and styled
-- from a queue, ROAD_BUDGET parts per Heartbeat; the Heartbeat connection exists only while the queue is not empty,
-- so in steady driving this script does no per-frame work. No new parts, no transparent planes, no lights.
-- Honest limit: Roblox has no screen-space reflections. Reflectance mirrors the sky / environment only, so a "wet"
-- road shows lamp and headlight highlights (specular from real SpotLights) and a faint sky sheen, not mirrored neon.
-- Debug (client command bar): _G.PattayaRoadLook.stats()
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local ML = require(ReplicatedStorage:WaitForChild("MaterialLibrary"))

local ROAD_NAMES = {Road = true, Junction = true, Joint = true}
local MARK_NAMES = {Centre = true, Dash = true, ZebraStripe = true}
local PRESET_ROAD = {MidnightWet = "wet", Legacy = "off"} -- any other preset (or none): dry
local ROAD_BUDGET = 400 -- parts styled per Heartbeat while a chunk streams in or the look changes
local SCAN_BATCH = 5000 -- instances per frame in the start-up scan

local function currentMode(): string
	local v = Lighting:GetAttribute("RoadLook")
	if v == "dry" or v == "wet" or v == "off" then
		return v
	end
	local preset = Lighting:GetAttribute("LightingPreset")
	return (type(preset) == "string" and PRESET_ROAD[preset]) or "dry"
end
local mode = currentMode()

type Rec = {saved: any, mark: boolean, styled: string?}
local recs: {[BasePart]: Rec} = setmetatable({}, {__mode = "k"}) :: any
local queue: {BasePart} = {}
local conn: RBXScriptConnection? = nil

local function brighter(c: Color3): Color3
	local h, s, v = c:ToHSV()
	return Color3.fromHSV(h, s, math.min(1, v * 1.05 + 0.03))
end

local function style(part: BasePart)
	local rec = recs[part]
	if not rec or rec.styled == mode or not part.Parent then
		return
	end
	if mode == "off" then
		if rec.styled then
			ML.restore(part, rec.saved)
		end
	elseif rec.mark then
		ML.apply(part, if mode == "wet" then "RoadPaintWet" else "RoadPaint", {color = brighter(rec.saved.Color)})
	else
		ML.apply(part, if mode == "wet" then "WetAsphalt" else "DryAsphalt")
	end
	rec.styled = if mode == "off" then nil else mode
end

local function drain()
	local n = math.min(#queue, ROAD_BUDGET)
	for i = 1, n do
		style(queue[i])
	end
	if n == #queue then
		table.clear(queue)
	else
		table.move(queue, n + 1, #queue, 1)
		for i = #queue - n + 1, #queue do
			queue[i] = nil
		end
	end
	if #queue == 0 and conn then
		conn:Disconnect()
		conn = nil
	end
end

local function enqueue(part: BasePart)
	table.insert(queue, part)
	if not conn then
		conn = RunService.Heartbeat:Connect(drain)
	end
end

local function register(d: Instance)
	if not d:IsA("BasePart") then
		return
	end
	local road, mark = ROAD_NAMES[d.Name] == true, MARK_NAMES[d.Name] == true
	if not (road or mark) or recs[d] then
		return
	end
	recs[d] = {saved = ML.save(d), mark = mark, styled = nil}
	if mode ~= "off" then
		enqueue(d)
	end
end

local function onModeChanged()
	local m = currentMode()
	if m == mode then
		return
	end
	mode = m
	print("[PattayaRoadLook] " .. m)
	for part in recs do
		enqueue(part)
	end
end
Lighting:GetAttributeChangedSignal("RoadLook"):Connect(onModeChanged)
Lighting:GetAttributeChangedSignal("LightingPreset"):Connect(onModeChanged)

_G.PattayaRoadLook = {
	stats = function()
		local n, styled = 0, 0
		for _, r in recs do
			n += 1
			if r.styled then styled += 1 end
		end
		return {mode = mode, registered = n, styled = styled, queued = #queue}
	end,
}

local world = workspace:WaitForChild("PattayaWorld", 60)
if not world then
	return
end
world.DescendantAdded:Connect(register)
for i, d in world:GetDescendants() do
	register(d)
	if i % SCAN_BATCH == 0 then
		task.wait()
	end
end
