-- Road surface look (MIDNIGHT PATTAYA, VIS-3, wet pass VIS-7.1), client only, reversible. Written, not run in Studio.
--
-- Lighting attribute RoadLook = "dry" | "wet" | "off" (live, from the server or client command bar):
--   dry  road slabs (Road, Junction, Joint) -> MaterialLibrary.DryAsphalt (Asphalt grain, 62,63,68, no reflection);
--        markings (Centre, Dash, ZebraStripe) -> RoadPaint, their own colour (white / yellow) a little brighter;
--        sidewalks: the builder's own look
--   wet  Road + Joint -> WetAsphalt (SmoothPlastic, no grain, much darker 26,28,34, Reflectance 0.25);
--        Junction discs -> WetAsphaltJunction (same, Reflectance 0.3: a junction reads as a shallow puddle);
--        markings -> RoadPaintWet (Reflectance 0.4 so lamp / headlight highlights read as wet), colour brighter and
--        tinted: white -> a touch of cyan, yellow -> a touch of amber (the light of the neon and the lamps);
--        sidewalks (Sidewalk) -> their own colour 15 % darker (material untouched)
--   off  every touched part gets back exactly what the builder gave it (Material, Color, Reflectance, Transparency,
--        MaterialVariant)
-- When RoadLook is not set, the look follows Lighting.LightingPreset: MidnightWet -> wet, Legacy -> off, else dry.
-- Nothing outside workspace.PattayaWorld is touched (circuit track: not yet). No new parts, decals or lights.
--
-- Cost: parts are registered when they stream in (DescendantAdded) or by a one-off chunked scan at start, and styled
-- from a queue, ROAD_BUDGET parts per Heartbeat; the Heartbeat connection exists only while the queue is not empty,
-- so once the queue has drained (steady driving, no look change) this script does NO per-frame work. Render cost:
-- Reflectance is a material parameter (sky / environment probe only), not an extra pass.
-- Honest limit: Roblox has no screen-space reflections. Reflectance mirrors the sky / environment only, so a "wet"
-- road shows lamp and headlight highlights (specular from real SpotLights) and a sky sheen, not mirrored neon.
-- Debug (client command bar): _G.PattayaRoadLook.stats()
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local ML = require(ReplicatedStorage:WaitForChild("MaterialLibrary"))

-- part name -> kind
local KIND = {Road = "road", Joint = "road", Junction = "junction", Centre = "mark", Dash = "mark",
	ZebraStripe = "mark", Sidewalk = "walk"}
local WET_MAT = {road = "WetAsphalt", junction = "WetAsphaltJunction"}
local PRESET_ROAD = {MidnightWet = "wet", Legacy = "off"} -- any other preset (or none): dry
local ROAD_BUDGET = 400 -- parts styled per Heartbeat while a chunk streams in or the look changes
local SCAN_BATCH = 5000 -- instances per frame in the start-up scan
local WET_WALK_DARKEN = 0.15 -- sidewalk colour lerped this far to black when wet
local WET_TINT_WHITE = Color3.fromRGB(205, 240, 255) -- white paint picks up a little cyan neon
local WET_TINT_YELLOW = Color3.fromRGB(255, 186, 90) -- yellow paint picks up a little sodium amber
local WET_TINT = 0.15

local function currentMode(): string
	local v = Lighting:GetAttribute("RoadLook")
	if v == "dry" or v == "wet" or v == "off" then
		return v
	end
	local preset = Lighting:GetAttribute("LightingPreset")
	return (type(preset) == "string" and PRESET_ROAD[preset]) or "dry"
end
local mode = currentMode()

type Rec = {saved: any, kind: string, styled: string?}
local recs: {[BasePart]: Rec} = setmetatable({}, {__mode = "k"}) :: any
local queue: {BasePart} = {}
local conn: RBXScriptConnection? = nil

local function brighter(c: Color3, mul: number, add: number): Color3
	local h, s, v = c:ToHSV()
	return Color3.fromHSV(h, s, math.min(1, v * mul + add))
end

local function wetPaint(c: Color3): Color3
	local _, s = c:ToHSV()
	local b = brighter(c, 1.1, 0.06)
	return b:Lerp(if s < 0.25 then WET_TINT_WHITE else WET_TINT_YELLOW, WET_TINT)
end

local function style(part: BasePart)
	local rec = recs[part]
	if not rec or rec.styled == mode or not part.Parent then
		return
	end
	local kind = rec.kind
	-- sidewalks only change when wet; dry and off both mean "the builder's look"
	if mode == "off" or (kind == "walk" and mode == "dry") then
		if rec.styled then
			ML.restore(part, rec.saved)
		end
		rec.styled = nil
		return
	end
	if kind == "walk" then
		part.Color = (rec.saved.Color :: Color3):Lerp(Color3.new(0, 0, 0), WET_WALK_DARKEN)
	elseif kind == "mark" then
		if mode == "wet" then
			ML.apply(part, "RoadPaintWet", {color = wetPaint(rec.saved.Color)})
		else
			ML.apply(part, "RoadPaint", {color = brighter(rec.saved.Color, 1.05, 0.03)})
		end
	else
		ML.apply(part, if mode == "wet" then WET_MAT[kind] else "DryAsphalt")
	end
	rec.styled = mode
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
	local kind = KIND[d.Name]
	if not kind or recs[d] then
		return
	end
	recs[d] = {saved = ML.save(d), kind = kind, styled = nil}
	if mode == "wet" or (mode == "dry" and kind ~= "walk") then
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
	for part, rec in recs do
		if rec.styled ~= m then
			enqueue(part)
		end
	end
end
Lighting:GetAttributeChangedSignal("RoadLook"):Connect(onModeChanged)
Lighting:GetAttributeChangedSignal("LightingPreset"):Connect(onModeChanged)

_G.PattayaRoadLook = {
	stats = function()
		local n, styled = 0, 0
		local byKind = {}
		for _, r in recs do
			n += 1
			byKind[r.kind] = (byKind[r.kind] or 0) + 1
			if r.styled then styled += 1 end
		end
		return {mode = mode, registered = n, styled = styled, queued = #queue, heartbeat = conn ~= nil,
			byKind = byKind}
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
