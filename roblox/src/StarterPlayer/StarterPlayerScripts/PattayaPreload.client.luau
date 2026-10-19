--!strict
-- PattayaPreload (MIDNIGHT PATTAYA, team10/streaming, 2026-10-20). Client only, read-only towards the car: it never
-- writes to the car, its physics or the camera. Written offline, not run in Studio; the leader measures it.
--
-- Leader measurement (2026-10-20): the stream-in hitch is dominated by the engine's own per-instance cost (22-27k
-- instances arrive in 6-8 frames after a teleport into a dense area), not by client scripts. What a client can do is
-- ask for the world EARLIER, so chunks are already in memory (and spread over more frames) when the car gets there,
-- and fetch the shared textures before they are first needed. Two parts:
--
-- 1. Stream ahead (only with workspace.StreamingEnabled): while the local player drives a RaceCar faster than
--    Preload_MinSpeed studs/s, LocalPlayer:RequestStreamAroundAsync(point ahead of the car along its horizontal
--    velocity), the point = speed * Preload_LeadSeconds studs ahead, clamped to [Preload_AheadMin, Preload_AheadMax].
--    At most one request in flight and at most one per Preload_Interval seconds; a new request only when the point
--    moved at least Preload_MinMove studs from the last one. Speed = LocalPlayer attribute HUD_SpeedKmh (CarController
--    telemetry, studs/s shown 1:1 as km/h); direction = the chassis' AssemblyLinearVelocity (read only). The car is
--    found the same way as PattayaTestKit.car(): Humanoid.SeatPart is a VehicleSeat whose parent has RaceCar.
-- 2. Content preload, once after join: ContentProvider:PreloadAsync in small batches for the shared look assets:
--    every id in ReplicatedStorage.MaterialLibraryMaps (PBR colour / normal / roughness / metalness maps), the
--    facade tiles on workspace.PattayaWorld (attributes Facade_* and FacadeNight_*, so the first dusk switch does not
--    fetch the night tiles), the MaterialVariants in MaterialService and the SurfaceAppearance templates in
--    ReplicatedStorage.MaterialLibraryAssets. (ServerStorage.VisAssetsManifest is not visible to the client and holds
--    Model package ids, not mesh ids; kit meshes arrive with their streamed MeshParts. See docs/STREAMING_PERFORMANCE.md.)
--
-- Switches (workspace attributes, live):
--   Preload_Enabled (default true; false = both parts off, nothing is requested)
--   Preload_StreamAhead (default OFF since 2026-10-20: leader A/B showed it worsens teleport hitches and gives no gain
--     while driving at 150 studs/s; set true to try it again)
--   Preload_MinSpeed (80) studs/s   Preload_LeadSeconds (4)   Preload_AheadMin (600) / Preload_AheadMax (900) studs
--   Preload_Interval (1.5) s        Preload_MinMove (250) studs   Preload_Timeout (2) s per request
-- Debug (client command bar): _G.PattayaPreload.stats()
local Players = game:GetService("Players")
local ContentProvider = game:GetService("ContentProvider")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local MaterialService = game:GetService("MaterialService")

local player = Players.LocalPlayer

local DEFAULTS: {[string]: number} = {Preload_MinSpeed = 80, Preload_LeadSeconds = 4, Preload_AheadMin = 600,
	Preload_AheadMax = 900, Preload_Interval = 1.5, Preload_MinMove = 250, Preload_Timeout = 2}
local TICK = 0.2 -- seconds between checks (a loop, not per frame)
local CONTENT_BATCH = 6 -- assets per PreloadAsync call
local CONTENT_GAP = 0.1 -- seconds between batches (spreads texture decode over frames)

local function knob(name: string): number
	local v = workspace:GetAttribute(name)
	return if type(v) == "number" then v else DEFAULTS[name]
end
local function on(): boolean
	return workspace:GetAttribute("Preload_Enabled") ~= false
end

local stats = {
	requests = 0, failed = 0, lastMs = 0, maxMs = 0, skippedSlow = 0,
	content = {queued = 0, ok = 0, failed = 0, seconds = 0, done = false},
}

-- 1. stream ahead -----------------------------------------------------------------------------------------------
local function myChassis(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent and seat.Parent:GetAttribute("RaceCar") then
		return (seat.Parent :: Model).PrimaryPart
	end
	return nil
end

local inFlight = false
local lastAt = -math.huge
local lastTarget: Vector3? = nil

local function request(target: Vector3)
	inFlight = true
	lastAt = os.clock()
	lastTarget = target
	stats.requests += 1
	task.spawn(function()
		local t0 = os.clock()
		local ok, err = pcall(function()
			player:RequestStreamAroundAsync(target, knob("Preload_Timeout"))
		end)
		local ms = (os.clock() - t0) * 1000
		stats.lastMs = math.floor(ms)
		if ms > stats.maxMs then
			stats.maxMs = math.floor(ms)
		end
		if not ok then
			stats.failed += 1
			if stats.failed <= 3 then
				warn("[PattayaPreload] RequestStreamAroundAsync: " .. tostring(err))
			end
		end
		inFlight = false
	end)
end

local function tickStreamAhead()
	if not workspace.StreamingEnabled or workspace:GetAttribute("Preload_StreamAhead") ~= true then
		return
	end
	if inFlight or os.clock() - lastAt < knob("Preload_Interval") then
		return
	end
	local kmh = player:GetAttribute("HUD_SpeedKmh")
	local speed = if type(kmh) == "number" then kmh else 0
	if speed < knob("Preload_MinSpeed") then
		stats.skippedSlow += 1
		return
	end
	local chassis = myChassis()
	if not chassis then
		return
	end
	local v = chassis.AssemblyLinearVelocity
	local flat = Vector3.new(v.X, 0, v.Z)
	local mag = flat.Magnitude
	if mag < 1 then
		return
	end
	local ahead = math.clamp(speed * knob("Preload_LeadSeconds"), knob("Preload_AheadMin"), knob("Preload_AheadMax"))
	local target = chassis.Position + flat * (ahead / mag)
	local last = lastTarget
	if last and (target - last).Magnitude < knob("Preload_MinMove") then
		return
	end
	request(target)
end

task.spawn(function()
	while true do
		task.wait(TICK)
		if on() then
			local ok, err = pcall(tickStreamAhead)
			if not ok then
				warn("[PattayaPreload] " .. tostring(err))
				task.wait(5)
			end
		end
	end
end)

-- 2. content preload --------------------------------------------------------------------------------------------
local function assetString(v: any): string?
	if type(v) == "number" then
		return "rbxassetid://" .. tostring(v)
	elseif type(v) == "string" and v ~= "" then
		return if string.match(v, "^%d+$") then "rbxassetid://" .. v else v
	end
	return nil
end

local function collect(): {any}
	local list: {any} = {}
	local seen: {[any]: boolean} = {}
	local function addOne(x: any)
		if x ~= nil and not seen[x] then
			seen[x] = true
			table.insert(list, x)
		end
	end
	-- PBR maps (ReplicatedStorage.MaterialLibraryMaps: set -> {color, normal, roughness, metalness})
	local mapsMod = ReplicatedStorage:FindFirstChild("MaterialLibraryMaps")
	if mapsMod and mapsMod:IsA("ModuleScript") then
		local ok, maps = pcall(require, mapsMod)
		if ok and type(maps) == "table" then
			for _, set in maps do
				if type(set) == "table" then
					for _, id in set do
						addOne(assetString(id))
					end
				end
			end
		end
	end
	-- facade tiles (day and night) published on the world model by PattayaBuilder
	local world = workspace:FindFirstChild("PattayaWorld") or workspace:WaitForChild("PattayaWorld", 30)
	if world then
		for name, value in world:GetAttributes() do
			if string.sub(name, 1, 7) == "Facade_" or string.sub(name, 1, 12) == "FacadeNight_" then
				addOne(assetString(value))
			end
		end
	end
	-- MaterialVariants (their maps) and the SurfaceAppearance templates cloned onto kit MeshParts
	for _, d in MaterialService:GetDescendants() do
		if d:IsA("MaterialVariant") then
			addOne(d)
		end
	end
	local assets = ReplicatedStorage:FindFirstChild("MaterialLibraryAssets")
	if assets then
		for _, d in assets:GetChildren() do
			if d:IsA("SurfaceAppearance") then
				addOne(d)
			end
		end
	end
	return list
end

task.spawn(function()
	if not game:IsLoaded() then
		game.Loaded:Wait()
	end
	if not on() then
		return
	end
	local t0 = os.clock()
	local list = collect()
	stats.content.queued = #list
	local batch: {any} = {}
	local function callback(_, status: Enum.AssetFetchStatus)
		if status == Enum.AssetFetchStatus.Success then
			stats.content.ok += 1
		elseif status == Enum.AssetFetchStatus.Failure or status == Enum.AssetFetchStatus.TimedOut then
			stats.content.failed += 1
		end
	end
	for i, item in list do
		if not on() then
			break
		end
		table.insert(batch, item)
		if #batch >= CONTENT_BATCH or i == #list then
			local ok, err = pcall(function()
				ContentProvider:PreloadAsync(batch, callback)
			end)
			if not ok then
				warn("[PattayaPreload] PreloadAsync: " .. tostring(err))
			end
			table.clear(batch)
			task.wait(CONTENT_GAP)
		end
	end
	stats.content.seconds = math.floor((os.clock() - t0) * 10) / 10
	stats.content.done = true
	print(`[PattayaPreload] content: {stats.content.queued} queued, {stats.content.ok} ok, {stats.content.failed} failed, {stats.content.seconds} s`)
end)

_G.PattayaPreload = {
	stats = function()
		return {enabled = on(), streaming = workspace.StreamingEnabled, inFlight = inFlight, requests = stats.requests,
			failed = stats.failed, lastMs = stats.lastMs, maxMs = stats.maxMs, lastTarget = lastTarget,
			content = table.clone(stats.content)}
	end,
}
