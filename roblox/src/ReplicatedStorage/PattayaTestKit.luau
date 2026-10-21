-- PattayaTestKit (DEV ONLY, client side). Reusable pieces of the leader's ad-hoc Studio tests: an autopilot for the
-- local player's client-owned car, road probes, a recorder for every PattayaRemotes event, and a compact report.
-- No gameplay script requires this module. It only works in Studio (RunService:IsStudio()) or when the place sets
-- the attribute DevTest = true on workspace; otherwise every call errors with "PattayaTestKit is disabled".
-- Server half: ServerStorage.PattayaTestKitServer (seat, teleport in hops, publish paths, set Money/Level, ...);
-- start it once per Play session from the server: require(game.ServerStorage.PattayaTestKitServer).start()
-- Copy-paste snippets: docs/TEST_KIT.md.
--
-- local TK = require(game.ReplicatedStorage.PattayaTestKit)        -- also stored as _G.TK
-- TK.drivePath(points, opts) -> handle      points: {Vector3} | packed string | attribute name (see readPath)
--   opts.speed     studs/s (number or function(h) -> number), default 140
--   opts.physics   false (default): set CFrame + velocity along the path every frame (ride height kept on the road)
--                  true: only the horizontal AssemblyLinearVelocity and the yaw AssemblyAngularVelocity are set, so
--                  gravity and the car's own suspension are real (hills, kerbs, landing)
--   opts.corner    lateral grip for a corner speed profile (like the AI racers; 150 = bot grip). Default: none in
--                  CFrame mode, 150 in physics mode. opts.brake (110) / opts.accel (CFrame: instant, physics: 60)
--   opts.caps      per-point speed caps (same length as points), e.g. a pit lane at 45
--   opts.lateral   studs to the right of the path (number or function(h) -> number), e.g. to leave the track
--   opts.onRoad    function(hit: RaycastResult?, h) -> boolean: your own "is this road" for the probes
--   opts.probeEvery seconds between road probes (0.5); opts.stopAt: distance along the path or function(h) -> bool
--   opts.startAt   server time to start (a countdown); opts.startWhen: function(h) -> bool; the drive also waits
--                  while the chassis is anchored (race grids hold cars until GO)
--   opts.stalls    {{at = studs, time = s}}: dead stop for `time` seconds at distance `at` (staged crash)
--   opts.holdEnd   seconds of zero velocity after the end (1); opts.fromCar (true): start from the car's position
--   opts.name      handle name in TK.handles / _G.TK.handles (default "drive"); opts.stopIfStuck (false)
--   handle:poll() -> one-line status   handle:log(text)   handle:stop(reason)   handle:wait(timeout) -> poll()
--   handle.logs (strings), handle.done, handle.reason, handle.stats {probes, road, off, byName, maxDev, minUp, ...}
-- TK.followRoute(source, opts) -> handle?, err   source: "SprintUpdate" | "JobUpdate" | "GPSUpdate" | {route}
--   opts.trigger = function() ... end fires the request after the recorder is hooked; opts.useLast = true takes the
--   last recorded route; opts.timeout (10 s) for the route to arrive. Sprint/race payloads start at payload.start.
-- TK.autoFollow(remoteName, opts) -> stopper: drives every new "start" route (Survival rounds) until :stop()
-- TK.lapCircuit(pathAttr, laps, opts) -> handle  closed path (attribute from the server kit, or "RacePath"):
--   drives to the start line, `laps` full laps, then 30 studs past the line. opts.pit = pit path attribute,
--   opts.pitOnLap = k, opts.pitSpeed = 45 take the pit lane on lap k. Physics mode by default (opts.physics=false off).
-- TK.hookRemotes(names?) -> recorder  records every OnClientEvent of PattayaRemotes (+ player attribute changes):
--   rec:dump(n?, filter?) -> string, rec:last(remote, kind?) -> args, rec:wait(remote, kind?, timeout?) -> args?,
--   rec:count(remote?, kind?), rec:clear(), rec:stop()
-- TK.probeRoadUnderCar() -> info {hit, name, path, y, road}, string
-- TK.seatIn(carName?, at?) -> ok, msg       (server kit) seat in a car ("RaceCar_hatch", "personal", nil = nearest)
-- TK.teleport(target, opts?) -> ok, msg     (server kit) move the car in hops > 60 studs (gates ignore them)
-- TK.server(action, ...) -> results          any server kit action (see PattayaTestKitServer)
-- TK.fire(remote, ...) / TK.invoke(remote, ...)  FireServer / InvokeServer on PattayaRemotes (logged)
-- TK.readPath(source, inst?) -> {Vector3}, TK.reverse(pts), TK.concat(...), TK.slice(pts, i, j), TK.jumpTo(pos)
-- TK.ghostTraffic(on), TK.car() -> chassis?, model?, TK.report() -> compact string, TK.stopAll()
-- Recovery Kit (docs/RECOVERY_AND_COLLISION.md):
-- TK.flipCar(rollDeg?, lift?)               tip the car over in place (180 = on its roof; 90 = on its side)
-- TK.flipTest(rollDeg?, timeout?) -> result  flip, then wait until it is wheels-down again:
--   {ok, seconds (flip -> up.Y > 0.9), minUp, uprights (CarController count)}; result.text is one line
-- TK.holdThrottle(value, seconds) -> stopper  keeps the seat's ThrottleFloat at value (stuck test; holding W works too)
-- TK.recovery() -> string                    the Recovery / CollisionModel switches and the car's recovery attributes
-- TK.trafficNear(radius?, at?, atT?) -> {{key, pos, look, speed, halfLen, halfWid, kind, dist, route, s, t}}  traffic
--   cars around the car (or `at`) at server time atT (default now), nearest first, from the shared formula the
--   traffic is drawn with (PattayaRecovery)
-- TK.drawT() -> number?                       the server time PattayaTraffic last drew its cars with (folder DrawT)
-- TK.hitTest(mode, speed, opts?) -> result   staged traffic hit on the target's own lane: "rear" (rear-end, from
--   opts.lead = 120 studs behind along its route), "head" (head-on, from 120 ahead, against the route), "side"
--   (a straight run from its right at opts.angle, default 20 degrees, to its heading at the touch). The car's
--   position is planned with the traffic's own route formula (PattayaRecovery.stagePlan), so it meets the car where
--   it really is; opts.offset = studs to its right (rear / head). Hands off on the arcade hit (or at contact in
--   physical mode) and measures {touched, targetKey, hitKey, keyMatch, tier, before (the player's impact speed),
--   trafficSpeed, vc (closing speed), after, lossPct, yawDeg, scriptYaw, minUp (+ minUpAt, minUpWhere), hz,
--   render, lag, extraHits, log (per-frame lines around the hit)}; result.text is the row line.
--   Target (round 6): the nearest car with a real model under its key (where the model is DRAWN is never used),
--   a straight approach (R.STAGE_BEND_DEG) and for side hits a steady heading at the touch (R.SIDE_STEADY_DEG),
--   and an approach clear of other traffic by opts.clearance (30) studs; if none is clear every other car ghosts
--   for the run (TestKit-only hook TK_HitTarget in PattayaTraffic, Studio / DevTest only). The car waits 0.3 s at
--   its start; only a hit after the approach began, near the planned time, whose key (Recovery_LastHitKey, from
--   the hit event) is the target's counts (PattayaRecovery.acceptStagedHit). Its numbers are read the frame the hit
--   is counted (a later hit cannot overwrite them). Arcade: my car ignores scenery during the approach, takes
--   collisions back once it is clear of everything, and is braked gently once the hit response (its window + 0.3 s)
--   is over. A miss says whether PattayaTraffic found a touch and CarController ignored it (Recovery_HitIgnored).
-- TK.trafficModelAt(pos, within) -> Model?   the traffic model near a spot (diagnostics only)
-- TK.selfCheck(n?, at?) -> ok, lines, info   for the n (5) nearest cars with a model: the model carrying the car's key
--   stands where the shared maths puts that key at DrawT (0.5 studs); the drawn-vs-now lag (studs, ms), DrawT age
--   and draw rate are reported, never a failure. Every line must say "match" before hitMatrix.
-- TK.trafficModels() -> {[key]: Model}        the traffic models shown now, by key
-- TK.hitMatrixStart(opts?) -> handle          hitMatrix in the background (handle:poll(), .lines, .done, :stop())
-- TK.hitMatrix(opts?) -> summary, rows       every row of TK.HIT_MATRIX, PASS / FAIL against the owner's table;
--   opts.runs = 3 repeats it and prints "REPEATABLE" only when every row of every run passed; opts.fps = 30 or
--   {15, 30, 60} runs it under the TestKit FPS cap at each level with a summary per level. Rows are isolated
--   (other traffic ghosts, labelled "isolated"); opts.isolate = false = real traffic: another car within 30 studs
--   of mine before the touch aborts the row, retried with another target up to 3 times. Failing rows print their
--   per-frame log (opts.verbose: every row).
-- TK.fpsLimit(fps?) -> fps?, TK.fpsLimitOn()  TestKit-only frame-rate cap (busy wait in Heartbeat; nil removes it)
-- TK.cleanup() -> string                     clears what the hit tests can leave: runs in progress, the FPS cap,
--   TK_HitTarget, TrafficGhostAll (TK.stopAll runs it too)
-- TK.nearMissTest(opts?) -> result           a staged overtake 5 studs beside a traffic car: one near miss paid, no hit
-- TK.jobWatch() -> watcher, TK.jobPayout(start, finish, nearMisses) -> ok, text   Taxi / Delivery bump and pay-out
--   check with arcade on (watcher:report())
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local function enabled(): boolean
	return RunService:IsStudio() or workspace:GetAttribute("DevTest") == true
end

if not enabled() then
	return setmetatable({enabled = false}, {
		__index = function()
			error("PattayaTestKit is disabled (needs Studio or workspace attribute DevTest = true)", 2)
		end,
	})
end

local TK = {enabled = true, handles = {}, recorder = nil :: any, trafficConn = nil :: RBXScriptConnection?}
_G.TK = TK

local player = Players.LocalPlayer
local STEP = 4 -- resample spacing (studs)
local ROAD_NAMES = {Road = true, Junction = true, Dash = true, Centre = true, Asphalt = true, PitLane = true,
	TransitionRoad = true, ServiceRoad = true, Parking = true, EdgeLine = true, PitLine = true}
TK.ROAD_NAMES = ROAD_NAMES

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

local function fmtNum(x: number): string
	if x == math.floor(x) and math.abs(x) < 1e9 then
		return tostring(math.floor(x))
	end
	return string.format("%.2f", x)
end

-- car --------------------------------------------------------------------------------------------------------------
function TK.car(): (BasePart?, Model?)
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent and seat.Parent:GetAttribute("RaceCar") then
		local model = seat.Parent :: Model
		return model.PrimaryPart, model
	end
	return nil, nil
end

local function excludeList(model: Instance?): {Instance}
	local list = {}
	if model then table.insert(list, model) end
	if player.Character then table.insert(list, player.Character) end
	local traffic = workspace:FindFirstChild("PattayaTraffic")
	if traffic then table.insert(list, traffic) end
	return list
end

local function carModelOf(inst: Instance): Model?
	local m = inst:FindFirstAncestorWhichIsA("Model")
	while m do
		if m:GetAttribute("RaceCar") or m:GetAttribute("RivalBot") then
			return m
		end
		m = m:FindFirstAncestorWhichIsA("Model")
	end
	return nil
end

local function isRoadHit(hit: RaycastResult?): boolean
	if not hit then
		return false
	end
	local n = hit.Instance.Name
	return ROAD_NAMES[n] == true or string.sub(n, 1, 4) == "Curb"
end

-- one probe straight down from just above the chassis (the car and character are excluded)
local function probeAt(pos: Vector3, model: Instance?): RaycastResult?
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = excludeList(model)
	return workspace:Raycast(pos + Vector3.new(0, 2, 0), Vector3.new(0, -40, 0), params)
end

function TK.probeRoadUnderCar()
	local chassis, model = TK.car()
	local char = player.Character
	local pos = if chassis then chassis.Position elseif char then char:GetPivot().Position else nil
	if not pos then
		return {hit = false}, "no character"
	end
	local hit = probeAt(pos, model)
	local info = {hit = hit ~= nil, road = isRoadHit(hit)}
	if hit then
		info.name, info.path, info.y = hit.Instance.Name, hit.Instance:GetFullName(), hit.Position.Y
		info.dist = pos.Y - hit.Position.Y
		info.car = carModelOf(hit.Instance) ~= nil
	end
	local text = if hit then ("%s %s y=%.2f below=%.2f at (%.0f, %.0f)"):format(if info.road then "ROAD" else "OFF",
		info.path, info.y, info.dist, pos.X, pos.Z) else ("NO HIT at (%.0f, %.0f)"):format(pos.X, pos.Z)
	return info, text
end

-- paths ------------------------------------------------------------------------------------------------------------
local function parsePacked(s: string)
	local pts = {}
	local is2D = false
	for item in string.gmatch(s, "[^;]+") do
		local nums = {}
		for x in string.gmatch(item, "[^,]+") do
			table.insert(nums, tonumber(x))
		end
		if #nums == 2 and nums[1] and nums[2] then
			table.insert(pts, Vector3.new(nums[1], 0, nums[2]))
			is2D = true
		elseif #nums >= 3 and nums[1] and nums[2] and nums[3] then
			table.insert(pts, Vector3.new(nums[1], nums[2], nums[3]))
		end
	end
	return pts, is2D
end

-- source: {Vector3} | {route = {Vector3}} | packed "x,z;..." / "x,y,z;..." | "RacePath" (PattayaWorld.Race.Path)
-- | an attribute name on `inst` (default workspace; "TK_" is tried as a prefix; numeric value = chunk count)
function TK.readPath(source, inst: Instance?)
	if type(source) == "table" then
		local src = if source.route then source.route else source
		local out = table.clone(src)
		out.flat = src.flat
		return out
	end
	assert(type(source) == "string", "readPath: points, a packed string or an attribute name")
	if source == "RacePath" then
		local world = workspace:FindFirstChild("PattayaWorld")
		local race = world and world:FindFirstChild("Race")
		local s = race and race:GetAttribute("Path")
		assert(type(s) == "string", "readPath: PattayaWorld.Race has no Path attribute")
		local pts, is2D = parsePacked(s)
		pts.flat, pts.closed = is2D, true
		return pts
	end
	if string.find(source, ";", 1, true) then
		local pts, is2D = parsePacked(source)
		pts.flat = is2D
		return pts
	end
	inst = inst or workspace
	local name = source
	local v = (inst :: Instance):GetAttribute(name)
	if v == nil and string.sub(name, 1, 3) ~= "TK_" then
		name = "TK_" .. name
		v = (inst :: Instance):GetAttribute(name)
	end
	if type(v) == "number" then -- chunked
		local parts = {}
		for i = 1, v do
			table.insert(parts, (inst :: Instance):GetAttribute(name .. "_" .. i) or "")
		end
		v = table.concat(parts, ";")
	end
	assert(type(v) == "string", "readPath: no path attribute " .. source)
	local pts, is2D = parsePacked(v)
	pts.flat = is2D
	pts.closed = (inst :: Instance):GetAttribute(name .. "_closed") == true
	return pts
end

function TK.reverse(pts)
	local out = {}
	for i = #pts, 1, -1 do table.insert(out, pts[i]) end
	out.flat = pts.flat
	return out
end

function TK.concat(...)
	local out = {}
	for _, p in {...} do
		for i = 1, #p do table.insert(out, p[i]) end
		if p.flat then out.flat = true end
	end
	return out
end

function TK.slice(pts, i: number, j: number?)
	local out = {}
	for k = i, j or #pts do table.insert(out, pts[k]) end
	out.flat = pts.flat
	return out
end

-- index of the path point nearest to pos (flat distance)
function TK.nearestIndex(pts, pos: Vector3): (number, number)
	local best, bd = 1, math.huge
	for i = 1, #pts do -- numeric: path tables also carry the keys flat/closed (generalised iteration would hit them)
		local p = pts[i]
		local d = flat(p - pos).Magnitude
		if d < bd then best, bd = i, d end
	end
	return best, bd
end

-- resample to STEP studs; caps follow the points (min of the two ends of each segment)
local function resample(pts, caps)
	local out, outCaps, cum = {pts[1]}, {caps and caps[1] or math.huge}, {0}
	local carry = 0
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = flat(b - a).Magnitude
		local cap = math.min(caps and caps[i] or math.huge, caps and caps[i + 1] or math.huge)
		if len > 1e-3 then
			local s = STEP - carry
			while s <= len do
				table.insert(out, a:Lerp(b, s / len))
				table.insert(outCaps, cap)
				table.insert(cum, cum[#cum] + (flat(out[#out] - out[#out - 1]).Magnitude))
				s += STEP
			end
			carry = len - (s - STEP)
		end
	end
	local last = pts[#pts]
	if flat(last - out[#out]).Magnitude > 0.05 then
		table.insert(out, last)
		table.insert(outCaps, caps and caps[#pts] or math.huge)
		table.insert(cum, cum[#cum] + flat(last - out[#out - 1]).Magnitude)
	end
	return out, outCaps, cum
end

-- corner speed profile (as PattayaStreetRace's AI) plus a braking pass
local function profile(pts, caps, grip: number?, brake: number)
	local v = {}
	local K = 5 -- ~20 studs each side
	for i = 1, #pts do
		local limit = caps[i] or math.huge
		if grip then
			local a, b, c = pts[math.max(1, i - K)], pts[i], pts[math.min(#pts, i + K)]
			local d1, d2 = flat(b - a), flat(c - b)
			if d1.Magnitude > 0.1 and d2.Magnitude > 0.1 then
				local theta = math.acos(math.clamp(d1.Unit:Dot(d2.Unit), -1, 1))
				if theta > 0.02 then
					limit = math.min(limit, math.sqrt(grip * 20 / theta))
				end
			end
		end
		v[i] = limit
	end
	for i = #pts - 1, 1, -1 do
		local ds = flat(pts[i + 1] - pts[i]).Magnitude
		v[i] = math.min(v[i], math.sqrt(math.min(v[i + 1], 1e6) ^ 2 + 2 * brake * ds))
	end
	return v
end

-- drive ------------------------------------------------------------------------------------------------------------
local Handle = {}
Handle.__index = Handle

function Handle:log(text: string)
	local t = if self.t0 then os.clock() - self.t0 else 0
	table.insert(self.logs, ("[%.1f] %s"):format(t, text))
	if #self.logs > 200 then table.remove(self.logs, 1) end
end

function Handle:poll(): string
	local st = self.stats
	local pct = if self.total > 0 then math.floor(100 * math.min(self.s, self.total) / self.total) else 0
	local names = {}
	for n, c in st.byName do table.insert(names, ("%s %d"):format(n, c)) end
	table.sort(names)
	local t = if self.t0 then (self.tEnd or os.clock()) - self.t0 else 0
	return ("%s: %s %d%% s=%.0f/%.0f t=%.1fs v=%.0f vmax=%.0f | probes %d road %d off %d [%s] | dev max %.1f up min %.2f%s")
		:format(self.name, if self.done then "done(" .. tostring(self.reason) .. ")" else self.state, pct, self.s,
			self.total, t, st.speed, st.maxSpeed, st.probes, st.road, st.off, table.concat(names, ", "), st.maxDev,
			st.minUp, if #self.logs > 0 then " | last: " .. self.logs[#self.logs] else "")
end

function Handle:stop(reason: string?)
	if self.done then
		return
	end
	self.done = true
	self.reason = reason or "stopped"
	self.tEnd = os.clock()
	self:log("stop: " .. self.reason)
	if self.conn then self.conn:Disconnect() end
	local chassis = self.chassis
	local hold = self.opts.holdEnd or 1
	if chassis and chassis.Parent and hold > 0 and not chassis.Anchored then
		local untilT = os.clock() + hold
		local c
		c = RunService.Heartbeat:Connect(function()
			if os.clock() > untilT or not chassis.Parent or chassis.Anchored then
				c:Disconnect()
				return
			end
			local v = chassis.AssemblyLinearVelocity
			chassis.AssemblyLinearVelocity = Vector3.new(0, math.min(v.Y, 0), 0)
			chassis.AssemblyAngularVelocity = Vector3.zero
		end)
	end
end

function Handle:wait(timeout: number?): string
	local untilT = os.clock() + (timeout or 600)
	while not self.done and os.clock() < untilT do
		task.wait(0.25)
	end
	return self:poll()
end

-- point, direction and index at distance s along the resampled path
local function at(h, s: number): (Vector3, Vector3, number)
	local cum, pts = h.cum, h.pts
	s = math.clamp(s, 0, h.total)
	local i = h.hintIdx or 1
	while i < #pts - 1 and cum[i + 1] < s do i += 1 end
	while i > 1 and cum[i] > s do i -= 1 end
	h.hintIdx = i
	local j = math.min(i + 1, #pts)
	local segLen = cum[j] - cum[i]
	local f = if segLen > 1e-6 then (s - cum[i]) / segLen else 0
	local p = pts[i]:Lerp(pts[j], f)
	local d = flat(pts[j] - pts[i])
	if d.Magnitude < 1e-3 and i > 1 then d = flat(pts[i] - pts[i - 1]) end
	return p, if d.Magnitude > 1e-3 then d.Unit else Vector3.new(0, 0, -1), i
end

local function valueOf(x, h, default)
	if type(x) == "function" then return x(h) end
	if x == nil then return default end
	return x
end

-- before each physics step (PreSimulation; older engines: Stepped, whose first argument is the time)
local function onPreSim(f: (number) -> ()): RBXScriptConnection
	local ok, sig = pcall(function() return (RunService :: any).PreSimulation end)
	if ok and sig then
		return sig:Connect(f)
	end
	return RunService.Stepped:Connect(function(_, dt) f(dt) end)
end

-- join a path where the car is: project the car onto the first segments (a grid along the route, a GPS line from
-- a point behind) instead of driving back to point 1
local function joinAtCar(src, caps, pos: Vector3)
	local bestK, bestD, bestQ = 1, math.huge, src[1]
	for k = 1, math.min(#src - 1, 40) do
		local a, b = src[k], src[k + 1]
		local ab, ap = flat(b - a), flat(pos - a)
		local len2 = ab:Dot(ab)
		local t = if len2 > 1e-6 then math.clamp(ap:Dot(ab) / len2, 0, 1) else 0
		local q = a:Lerp(b, t)
		local d = flat(pos - q).Magnitude
		if d < bestD then bestK, bestD, bestQ = k, d, q end
	end
	local out, outCaps = {}, if caps then {} else nil
	local function add(p: Vector3, cap: number?)
		table.insert(out, p)
		if outCaps then table.insert(outCaps, cap or math.huge) end
	end
	if bestD > 4 then add(pos, caps and caps[bestK]) end
	if flat(bestQ - src[bestK + 1]).Magnitude > 0.5 then add(bestQ, caps and caps[bestK]) end
	for k = bestK + 1, #src do add(src[k], caps and caps[k]) end
	out.flat = src.flat
	return out, outCaps
end

function TK.drivePath(points, opts)
	opts = opts or {}
	local chassis, model = TK.car()
	assert(chassis, "drivePath: get in a car first (TK.seatIn)")
	local src = TK.readPath(points)
	local caps = opts.caps
	if opts.fromCar ~= false and #src >= 2 then
		src, caps = joinAtCar(src, caps, chassis.Position)
	end
	assert(#src >= 2, "drivePath: need at least 2 points")
	local physics = opts.physics == true
	local name = opts.name or "drive"
	local old = TK.handles[name]
	if old and not old.done then old:stop("replaced") end
	for _, other in TK.handles do
		if not other.done and other.chassis == chassis then other:stop("another drive started") end
	end
	local pts, ptsCaps, cum = resample(src, caps)
	local brake = opts.brake or 110
	local grip = opts.corner
	if grip == nil and physics then grip = 150 end
	if grip == false then grip = nil end
	local h = setmetatable({
		name = name, opts = opts, physics = physics, chassis = chassis, model = model, pts = pts, cum = cum,
		total = cum[#cum], prof = profile(pts, ptsCaps, grip, brake), flatPath = src.flat == true,
		s = 0, v = 0, state = "waiting", done = false, logs = {}, hintIdx = 1, idx = 1,
		stats = {probes = 0, road = 0, off = 0, byName = {}, maxDev = 0, minUp = 1, speed = 0, maxSpeed = 0,
			offStreak = 0, samples = 0},
	}, Handle)
	TK.handles[name] = h
	_G.TK.handles = TK.handles
	local ride = nil
	local lastY = chassis.Position.Y
	local nextProbe = 0
	local slowSince = nil
	local stall = nil -- {untilT}
	local stalls = table.clone(opts.stalls or {})
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude

	local function groundY(p: Vector3, fromY: number): number?
		params.FilterDescendantsInstances = excludeList(model)
		local hit = workspace:Raycast(Vector3.new(p.X, fromY + 12, p.Z), Vector3.new(0, -60, 0), params)
		if hit and not carModelOf(hit.Instance) then
			return hit.Position.Y
		end
		return nil
	end

	local function probe()
		local st = h.stats
		local hit = probeAt(chassis.Position, model)
		local road
		if opts.onRoad then
			road = opts.onRoad(hit, h) == true
		else
			road = isRoadHit(hit)
		end
		st.probes += 1
		local n = if not hit then "(none)" elseif carModelOf(hit.Instance) then "(car)" else hit.Instance.Name
		st.byName[n] = (st.byName[n] or 0) + 1
		if road then
			st.road += 1
			if st.offStreak >= 3 then h:log(("back on road after %d off probes"):format(st.offStreak)) end
			st.offStreak = 0
		else
			st.off += 1
			st.offStreak += 1
			if st.offStreak == 1 or st.offStreak == 3 then
				local p = chassis.Position
				h:log(("off road (%s) at (%.0f, %.0f) s=%.0f"):format(n, p.X, p.Z, h.s))
			end
		end
	end

	h.conn = onPreSim(function(dt)
		dt = math.min(dt, 1 / 20)
		if h.done then return end
		local c2 = TK.car()
		if c2 ~= chassis or not chassis.Parent then
			h:stop("left the car")
			return
		end
		local now = os.clock()
		if h.state == "waiting" then
			if chassis.Anchored then return end
			if opts.startAt and workspace:GetServerTimeNow() < opts.startAt then return end
			if opts.startWhen and not opts.startWhen(h) then return end
			h.state = "running"
			h.t0 = now
			h.v = if physics then flat(chassis.AssemblyLinearVelocity).Magnitude else 0
			local g = groundY(chassis.Position, chassis.Position.Y)
			ride = if g then math.clamp(chassis.Position.Y - g, 1.5, 6) else 2.8
			h:log(("start %s mode, %.0f studs, ride %.2f"):format(if physics then "physics" else "cframe", h.total, ride))
		end
		if chassis.Anchored then return end -- held by the server (reset, grid): wait it out
		local st = h.stats
		-- staged dead stop
		if stall then
			if now < stall then
				chassis.AssemblyLinearVelocity = Vector3.new(0, chassis.AssemblyLinearVelocity.Y, 0)
				chassis.AssemblyAngularVelocity = Vector3.zero
				h.v = 0
				return
			end
			stall = nil
		end
		for i, sd in stalls do
			if h.s >= sd.at then
				table.remove(stalls, i)
				stall = now + (sd.time or 0.4)
				h:log(("stall %.1fs at s=%.0f"):format(sd.time or 0.4, h.s))
				return
			end
		end
		-- speed command
		local vWant = math.min(valueOf(opts.speed, h, 140), h.prof[h.idx] or math.huge)
		local accel = opts.accel or (if physics then 60 else math.huge)
		if vWant > h.v then
			h.v = math.min(vWant, h.v + accel * dt)
		else
			h.v = math.max(vWant, h.v - brake * dt)
		end
		local lat = valueOf(opts.lateral, h, 0)
		if physics then
			-- progress: nearest resampled point in a window ahead of the last one
			local pos = chassis.Position
			local bi, bd = h.idx, math.huge
			local hi = math.min(#pts, h.idx + math.ceil((h.v * dt + 12) / STEP) + 6)
			for i = math.max(1, h.idx - 3), hi do
				local d = flat(pts[i] - pos).Magnitude
				if d < bd then bi, bd = i, d end
			end
			h.idx = bi
			h.s = cum[bi]
			local look = math.clamp(h.v * 0.3, 10, 40)
			local tp, tdir = at(h, h.s + look)
			if lat ~= 0 then tp += Vector3.new(-tdir.Z, 0, tdir.X) * lat end
			local want = flat(tp - pos)
			want = if want.Magnitude > 0.1 then want.Unit else tdir
			local v = chassis.AssemblyLinearVelocity
			chassis.AssemblyLinearVelocity = want * h.v + Vector3.new(0, v.Y, 0)
			local fwd = flat(chassis.CFrame.LookVector)
			if fwd.Magnitude > 0.1 then
				fwd = fwd.Unit
				local angle = math.atan2(fwd:Cross(want).Y, fwd:Dot(want))
				local av = chassis.AssemblyAngularVelocity
				chassis.AssemblyAngularVelocity = Vector3.new(av.X, math.clamp(angle * 5, -3, 3), av.Z)
			end
			st.maxDev = math.max(st.maxDev, bd)
			if h.s >= h.total - 3 then h:stop("end") return end
		else
			h.s = math.min(h.total, h.s + h.v * dt)
			local p, dir, i = at(h, h.s)
			h.idx = i
			local p2 = at(h, math.min(h.total, h.s + 6))
			local d = flat(p2 - p)
			dir = if d.Magnitude > 0.1 then d.Unit else dir
			if lat ~= 0 then p += Vector3.new(-dir.Z, 0, dir.X) * lat end
			local g = groundY(p, lastY)
			local y
			if g then
				y = g + ride
			elseif not h.flatPath then
				y = p.Y + ride
			else
				y = lastY
			end
			lastY = y
			local pos = Vector3.new(p.X, y, p.Z)
			chassis.CFrame = CFrame.lookAt(pos, pos + dir)
			chassis.AssemblyLinearVelocity = dir * h.v
			chassis.AssemblyAngularVelocity = Vector3.zero
			if h.s >= h.total - 0.01 then h:stop("end") return end
		end
		-- stats
		local speed = flat(chassis.AssemblyLinearVelocity).Magnitude
		st.speed = speed
		st.maxSpeed = math.max(st.maxSpeed, speed)
		st.minUp = math.min(st.minUp, chassis.CFrame.UpVector.Y)
		st.samples += 1
		if physics then
			if speed < 3 and h.v > 10 then
				slowSince = slowSince or now
				if now - slowSince > 3 and not h.stuckLogged then
					h.stuckLogged = true
					h:log(("stuck at (%.0f, %.0f) s=%.0f"):format(chassis.Position.X, chassis.Position.Z, h.s))
					if opts.stopIfStuck then h:stop("stuck") return end
				end
			else
				slowSince = nil
				h.stuckLogged = false
			end
		end
		if now >= nextProbe then
			nextProbe = now + (opts.probeEvery or 0.5)
			probe()
		end
		local stopAt = opts.stopAt
		if type(stopAt) == "number" and h.s >= stopAt then
			h:stop("stopAt")
		elseif type(stopAt) == "function" and stopAt(h) then
			h:stop("stopAt")
		end
	end)
	return h
end

-- instant client-side move of the car (e.g. the teleport-cheat test; the server judges it as a jump)
function TK.jumpTo(pos: Vector3, look: Vector3?)
	local chassis = TK.car()
	assert(chassis, "jumpTo: get in a car first")
	local dir = flat(look or chassis.CFrame.LookVector)
	dir = if dir.Magnitude > 0.1 then dir.Unit else Vector3.new(0, 0, -1)
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.CFrame = CFrame.lookAt(pos, pos + dir)
end

-- remotes ----------------------------------------------------------------------------------------------------------
local QUIET = {standings = true, tower = true, CircuitPos = true, CircuitGap = true, CircuitCount = true,
	NearMissAt = true, LastRewardAt = true, GarageMsgAt = true}

local function brief(v, depth: number): string
	local t = typeof(v)
	if t == "string" then
		return if #v > 80 then string.sub(v, 1, 77) .. "..." else v
	elseif t == "number" then
		return fmtNum(v)
	elseif t == "Vector3" then
		return ("(%.0f,%.0f,%.0f)"):format(v.X, v.Y, v.Z)
	elseif t == "Instance" then
		return v.Name
	elseif t == "table" then
		if depth <= 0 then return "{..}" end
		local n = #v
		if n > 0 then
			if n <= 4 then
				local items = {}
				for _, x in v do table.insert(items, brief(x, depth - 1)) end
				return "[" .. table.concat(items, ",") .. "]"
			end
			return ("[#%d]"):format(n)
		end
		local keys = {}
		for k in v do table.insert(keys, tostring(k)) end
		table.sort(keys)
		local items = {}
		for i, k in keys do
			if i > 8 then table.insert(items, "...") break end
			local x = v[k]
			if x == nil then x = v[tonumber(k)] end
			table.insert(items, k .. "=" .. brief(x, depth - 1))
		end
		return "{" .. table.concat(items, " ") .. "}"
	end
	return tostring(v)
end
TK.brief = brief

local Recorder = {}
Recorder.__index = Recorder
local recorder = nil

local function record(rec, remote: string, args)
	rec.n += 1
	table.insert(rec.events, {i = rec.n, t = os.clock() - rec.t0, st = workspace:GetServerTimeNow(), remote = remote,
		kind = if type(args[1]) == "string" then args[1] else nil, args = args})
	if #rec.events > 2000 then table.remove(rec.events, 1) end
	rec.counts[remote] = (rec.counts[remote] or 0) + 1
end

function TK.hookRemotes(names: {string}?)
	if recorder and not recorder.stopped then
		return recorder
	end
	local rec = setmetatable({events = {}, counts = {}, conns = {}, n = 0, t0 = os.clock(), stopped = false}, Recorder)
	local want = nil
	if names then
		want = {}
		for _, n in names do want[n] = true end
	end
	local folder = ReplicatedStorage:WaitForChild("PattayaRemotes", 10)
	local function hook(r: Instance)
		if r:IsA("RemoteEvent") and (not want or want[r.Name]) then
			table.insert(rec.conns, (r :: RemoteEvent).OnClientEvent:Connect(function(...)
				record(rec, r.Name, table.pack(...))
			end))
		end
	end
	if folder then
		for _, r in folder:GetChildren() do hook(r) end
		table.insert(rec.conns, folder.ChildAdded:Connect(hook))
	end
	table.insert(rec.conns, player.AttributeChanged:Connect(function(attr)
		record(rec, "attr", table.pack(attr, player:GetAttribute(attr)))
	end))
	recorder = rec
	TK.recorder = rec
	return rec
end

function Recorder:clear()
	table.clear(self.events)
	table.clear(self.counts)
end

function Recorder:stop()
	self.stopped = true
	for _, c in self.conns do c:Disconnect() end
	if recorder == self then recorder = nil end
end

local function matches(e, remote: string?, kind: string?): boolean
	return (remote == nil or e.remote == remote) and (kind == nil or e.kind == kind)
end

function Recorder:count(remote: string?, kind: string?): number
	local n = 0
	for _, e in self.events do
		if matches(e, remote, kind) then n += 1 end
	end
	return n
end

function Recorder:last(remote: string?, kind: string?)
	for i = #self.events, 1, -1 do
		local e = self.events[i]
		if matches(e, remote, kind) then return e.args, e end
	end
	return nil
end

-- waits for an event recorded after this call
function Recorder:wait(remote: string?, kind: string?, timeout: number?)
	local from = self.n
	local untilT = os.clock() + (timeout or 10)
	while os.clock() < untilT do
		for i = #self.events, 1, -1 do
			local e = self.events[i]
			if e.i <= from then break end
			if matches(e, remote, kind) then return e.args, e end
		end
		task.wait(0.05)
	end
	return nil
end

-- the last n events (default 30) as text; filter = remote name or function(e) -> bool; quiet kinds are skipped
function Recorder:dump(n: number?, filter): string
	local lines = {}
	for i = #self.events, 1, -1 do
		local e = self.events[i]
		local ok
		if type(filter) == "function" then
			ok = filter(e)
		elseif type(filter) == "string" then
			ok = e.remote == filter
		else
			ok = not (QUIET[e.kind or ""] or (e.remote == "attr" and QUIET[tostring(e.args[1])]))
		end
		if ok then
			local parts = {}
			for k = 1, e.args.n do table.insert(parts, brief(e.args[k], 2)) end
			table.insert(lines, 1, ("%.1f %s %s"):format(e.t, e.remote, table.concat(parts, " ")))
			if #lines >= (n or 30) then break end
		end
	end
	return table.concat(lines, "\n")
end

local function remoteNamed(name: string): Instance
	local folder = ReplicatedStorage:WaitForChild("PattayaRemotes", 10)
	local r = folder and folder:WaitForChild(name, 5)
	assert(r, "no remote " .. name)
	return r :: Instance
end

function TK.fire(name: string, ...)
	local r = remoteNamed(name) :: RemoteEvent
	if recorder then record(recorder, "out", table.pack(name, ...)) end
	r:FireServer(...)
end

function TK.invoke(name: string, ...)
	local r = remoteNamed(name) :: RemoteFunction
	if recorder then record(recorder, "out", table.pack(name, ...)) end
	return r:InvokeServer(...)
end

-- server kit -------------------------------------------------------------------------------------------------------
function TK.server(action: string, ...)
	local rf = ReplicatedStorage:FindFirstChild("PattayaTestKitRemote")
	assert(rf, "server kit not started: run require(game.ServerStorage.PattayaTestKitServer).start() on the server")
	return (rf :: RemoteFunction):InvokeServer(action, ...)
end

function TK.seatIn(carName: string?, atPos)
	return TK.server("seat", carName, atPos)
end

function TK.teleport(target, opts)
	return TK.server("teleport", target, opts)
end

-- routes from remotes ----------------------------------------------------------------------------------------------
local ROUTE_KIND = {SprintUpdate = "start", JobUpdate = "start", GPSUpdate = "route"}

local function routeFromArgs(args)
	local payload = args and args[2]
	if type(payload) ~= "table" then return nil end
	return payload.route, payload
end

function TK.followRoute(source, opts)
	opts = table.clone(opts or {})
	local route, payload
	if type(source) == "string" and ROUTE_KIND[source] then
		local rec = TK.hookRemotes()
		local args
		if opts.useLast then
			args = rec:last(source, ROUTE_KIND[source])
		else
			local from = rec.n
			if opts.trigger then opts.trigger() end
			args = rec:wait(source, ROUTE_KIND[source], opts.timeout or 10)
			if not args then
				-- a "stop" answer (refused) is more useful than a timeout
				local last, e = rec:last(source)
				if last and e and e.i > from then
					return nil, "no route: " .. brief(last[2], 2)
				end
			end
		end
		if not args then
			return nil, "no " .. source .. " route arrived"
		end
		route, payload = routeFromArgs(args)
	else
		route = if type(source) == "table" and source.route then source.route else source
		payload = if type(source) == "table" then source else nil
	end
	if type(route) ~= "table" or #route < 2 then
		return nil, "route has no points"
	end
	if payload and type(payload.start) == "number" and opts.startAt == nil then
		opts.startAt = payload.start -- sprint: now; challenge / events: GO after the countdown
	end
	opts.name = opts.name or "route"
	local h = TK.drivePath(route, opts)
	h.payload = payload
	return h
end

-- follows every new route start on `remote` (default SprintUpdate) until stopper:stop()
function TK.autoFollow(remote: string?, opts)
	remote = remote or "SprintUpdate"
	local rec = TK.hookRemotes()
	local stopper = {running = true, count = 0}
	function stopper:stop() self.running = false end
	task.spawn(function()
		while stopper.running do
			local args = rec:wait(remote, ROUTE_KIND[remote], 5)
			if args and stopper.running then
				local route, payload = routeFromArgs(args)
				if route and #route >= 2 and TK.car() then
					local o = table.clone(opts or {})
					o.startAt = payload and payload.start
					o.name = o.name or "auto"
					stopper.count += 1
					stopper.handle = TK.drivePath(route, o)
					stopper.handle:log(("autoFollow route %d"):format(stopper.count))
				end
			end
		end
	end)
	TK.handles.autoFollow = stopper :: any
	return stopper
end

-- circuits / closed paths ------------------------------------------------------------------------------------------
-- Unrolled closed path: from the car to the start line (index 1), `laps` full laps, then 30 studs past the line.
-- opts.pit (pit lane path) + opts.pitOnLap = k: on lap k the car leaves the track where the pit lane starts and
-- rejoins where it ends (speed cap opts.pitSpeed, default 45). A car sitting in the pit lane (open sessions start
-- there) first drives out along it. Returns points, caps.
function TK.lapPath(pathSource, laps: number, opts)
	opts = opts or {}
	local track = TK.readPath(pathSource)
	local chassis = TK.car()
	assert(chassis, "lapPath: get in a car first")
	local n = #track
	if flat(track[n] - track[1]).Magnitude < 0.5 then table.remove(track) n -= 1 end
	local out, caps = {}, {}
	local function add(p: Vector3, cap: number?)
		table.insert(out, p)
		table.insert(caps, cap or math.huge)
	end
	local pit = opts.pit and TK.readPath(opts.pit)
	local pitSpeed = opts.pitSpeed or 45
	add(chassis.Position)
	local pitIn = pit and TK.nearestIndex(track, pit[1])
	local pitOut = pit and TK.nearestIndex(track, pit[#pit])
	local i
	local pj, pd = 0, math.huge
	if pit then pj, pd = TK.nearestIndex(pit, chassis.Position) end
	local ti, td = TK.nearestIndex(track, chassis.Position)
	if pit and pd < 20 and pd < td then
		for k = pj, #pit do add(pit[k], pitSpeed) end -- out of the pits first
		i = pitOut % n + 1
	else
		i = ti % n + 1
	end
	local crossings, lap, pitted = 0, 0, false
	local guard = 0
	while guard < n * (laps + 3) do
		guard += 1
		if i == 1 then
			crossings += 1
			lap = crossings
			if crossings > laps then break end
		end
		if pit and not pitted and lap == opts.pitOnLap and i == pitIn then
			pitted = true
			for k = 1, #pit do add(pit[k], pitSpeed) end
			local nextI = pitOut % n + 1
			if pitOut < pitIn then -- the pit lane passes the line
				crossings += 1
				lap = crossings
				if crossings > laps then i = nextI break end
			end
			i = nextI
			continue
		end
		add(track[i])
		i = i % n + 1
	end
	-- 30 studs past the line
	local walked = 0
	local prev = out[#out]
	for _ = 1, n do
		local p = track[i]
		walked += if prev then flat(p - prev).Magnitude else 0
		add(p)
		prev = p
		i = i % n + 1
		if walked > 30 then break end
	end
	out.flat = track.flat
	return out, caps
end

function TK.lapCircuit(pathSource, laps: number?, opts)
	opts = table.clone(opts or {})
	if opts.physics == nil then opts.physics = true end
	-- a published circuit centreline "TK_Circuit_<id>" comes with its pit lane "TK_Pit_<id>"
	if opts.pit == nil and type(pathSource) == "string" then
		local pitName = string.gsub(pathSource, "Circuit_", "Pit_")
		if pitName ~= pathSource and (workspace:GetAttribute(pitName) ~= nil or workspace:GetAttribute("TK_" .. pitName) ~= nil) then
			opts.pit = pitName
		end
	end
	opts.fromCar = false -- lapPath already starts at the car
	local pts, caps = TK.lapPath(pathSource, laps or 1, opts)
	opts.caps = caps
	opts.name = opts.name or "lap"
	return TK.drivePath(pts, opts)
end

-- misc -------------------------------------------------------------------------------------------------------------
-- traffic cars non-solid for this client (the drive tests ran with traffic made non-solid). Only each car's root
-- ("Body") collides, and PattayaTraffic turns it solid again when a car stops ghosting, so this re-applies it on
-- every Heartbeat until ghostTraffic(false).
function TK.ghostTraffic(on: boolean): number
	local folder = workspace:FindFirstChild("PattayaTraffic")
	if TK.trafficConn then
		TK.trafficConn:Disconnect()
		TK.trafficConn = nil
	end
	if not folder then
		return 0
	end
	local function apply(solid: boolean): number
		local n = 0
		for _, m in folder:GetChildren() do
			local root = m:IsA("Model") and m.PrimaryPart
			if root then
				root.CanCollide = solid
				n += 1
			end
		end
		return n
	end
	-- arcade collision model: PattayaTraffic skips scripted hits while this is set
	player:SetAttribute("TrafficGhostAll", if on then true else nil)
	if on then
		TK.trafficConn = RunService.Heartbeat:Connect(function() apply(false) end)
		return apply(false)
	end
	-- arcade boxes never collide: leave them as PattayaTraffic set them
	if workspace:GetAttribute("CollisionModel") == "arcade" then
		return 0
	end
	return apply(true)
end

-- recovery -----------------------------------------------------------------------------------------------------------
function TK.flipCar(rollDeg: number?, lift: number?): number
	local chassis = TK.car()
	assert(chassis, "flipCar: get in a car first")
	local look = flat(chassis.CFrame.LookVector)
	look = if look.Magnitude > 0.1 then look.Unit else Vector3.new(0, 0, -1)
	local pos = chassis.Position + Vector3.new(0, lift or 4, 0)
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	chassis.CFrame = CFrame.lookAt(pos, pos + look) * CFrame.Angles(0, 0, math.rad(rollDeg or 180))
	return os.clock()
end

function TK.flipTest(rollDeg: number?, timeout: number?)
	local chassis = TK.car()
	assert(chassis, "flipTest: get in a car first")
	local before = player:GetAttribute("Recovery_Uprights") or 0
	local t0 = TK.flipCar(rollDeg)
	local minUp, upAt = 1, nil
	local deadline = t0 + (timeout or 8)
	while os.clock() < deadline do
		RunService.Heartbeat:Wait()
		if not chassis.Parent then break end
		local up = chassis.CFrame.UpVector.Y
		minUp = math.min(minUp, up)
		if minUp < 0.5 and up > 0.9 then
			upAt = upAt or os.clock()
			if os.clock() - upAt > 0.25 then break end
		else
			upAt = nil
		end
	end
	local res = {ok = upAt ~= nil, seconds = if upAt then upAt - t0 else nil, minUp = minUp,
		uprights = (player:GetAttribute("Recovery_Uprights") or 0) - before}
	res.text = ("flipTest roll %s: %s in %s s (minUp %.2f, auto-uprights %d)"):format(tostring(rollDeg or 180),
		if res.ok then "upright" else "NOT upright", if res.seconds then string.format("%.2f", res.seconds) else "-",
		minUp, res.uprights)
	return res
end

function TK.holdThrottle(value: number, seconds: number)
	local _, model = TK.car()
	assert(model, "holdThrottle: get in a car first")
	local seat = model:FindFirstChild("DriveSeat") :: VehicleSeat
	local t0 = os.clock()
	local conn
	conn = RunService.Heartbeat:Connect(function()
		if os.clock() - t0 > seconds or not seat.Parent then
			conn:Disconnect()
			return
		end
		seat.ThrottleFloat = value
	end)
	return {stop = function() conn:Disconnect() end}
end

function TK.recovery(): string
	local parts = {}
	for _, k in {"Recovery_Enabled", "Recovery_AutoUpright", "Recovery_AntiStuck", "Recovery_RescueAuto", "CollisionModel"} do
		table.insert(parts, k .. "=" .. tostring(workspace:GetAttribute(k)))
	end
	for _, k in {"Recovery_Uprights", "RescueActive", "RescueAt", "RescueEndAt", "Recovery_HitCount", "Recovery_LastHit",
		"TrafficHits", "TrafficGhostUntil"} do
		local v = player:GetAttribute(k)
		if v ~= nil then table.insert(parts, k .. "=" .. brief(v, 1)) end
	end
	return table.concat(parts, " ")
end

local recModule = ReplicatedStorage:FindFirstChild("PattayaRecovery")
local Rec = recModule and require(recModule) :: any
local trafficRoutes = nil

-- cooperative waits: inside TK.hitMatrixStart's runner (a coroutine resumed by a Heartbeat connection, so it outlives
-- the Studio execute snippet that started it) they yield to the runner; anywhere else they wait a Heartbeat
local runnerCo: thread? = nil
local function waitFrame()
	if runnerCo ~= nil and coroutine.running() == runnerCo then
		coroutine.yield()
	else
		RunService.Heartbeat:Wait()
	end
end
local function waitSeconds(sec: number)
	local t0 = os.clock()
	repeat waitFrame() until os.clock() - t0 >= sec
end

-- frame rates the hit tests report, each over the last 0.5 s: Heartbeat (once a frame: physics and scripts) and
-- RenderStepped (frames drawn; Studio draws only ~15 a second while its window is not focused)
local rates = {hb = 0, render = 0, hbN = 0, renderN = 0, at = os.clock()}
RunService.Heartbeat:Connect(function()
	rates.hbN += 1
	local c = os.clock()
	if c - rates.at >= 0.5 then
		rates.hb, rates.render = rates.hbN / (c - rates.at), rates.renderN / (c - rates.at)
		rates.hbN, rates.renderN, rates.at = 0, 0, c
	end
end)
pcall(function()
	RunService.RenderStepped:Connect(function() rates.renderN += 1 end)
end)
TK.rates = rates

-- TK.fpsLimit(fps?, maxSeconds?) -> fps?   TestKit-only frame-rate cap (this module loads only in Studio and DevTest
-- places): a busy wait at the end of each Heartbeat keeps this client to at most `fps` frames a second, so physics
-- steps, scripts and drawing all run at that rate. TK.fpsLimit(nil) removes it, and it removes itself after
-- maxSeconds (1800), so a crashed test never leaves a slow client behind. TK.hitMatrix({fps = ...}) sets it and
-- removes it on every path (errors included), as do TK.cleanup and TK.stopAll. Player attribute TK_FpsLimit shows it.
-- The cap and the staged runs in progress live in _G.TK_LIVE, so a second copy of this module (the Studio execute
-- context can get its own copy) still finds and removes them.
local live = if type(_G.TK_LIVE) == "table" then _G.TK_LIVE else {}
_G.TK_LIVE = live
live.limiter = live.limiter or {fps = nil :: number?, conn = nil :: RBXScriptConnection?, nextAt = 0, expires = 0}
live.activeRuns = live.activeRuns or {}
local limiter = live.limiter
function TK.fpsLimit(fps: number?, maxSeconds: number?): number?
	if limiter.conn then
		limiter.conn:Disconnect()
		limiter.conn = nil
	end
	limiter.fps = nil
	player:SetAttribute("TK_FpsLimit", nil)
	if type(fps) ~= "number" or fps ~= fps or fps <= 0 then
		return nil
	end
	local frame = 1 / fps
	limiter.fps, limiter.nextAt, limiter.expires = fps, os.clock() + frame, os.clock() + (maxSeconds or 1800)
	limiter.conn = RunService.Heartbeat:Connect(function()
		if os.clock() > limiter.expires then
			TK.fpsLimit(nil)
			return
		end
		while os.clock() < limiter.nextAt do
			-- busy wait: this frame does not end before its slot
		end
		local now = os.clock()
		limiter.nextAt = if now - limiter.nextAt > frame then now + frame else limiter.nextAt + frame
	end)
	player:SetAttribute("TK_FpsLimit", fps)
	return fps
end
-- the cap in force (nil = none)
function TK.fpsLimitOn(): number?
	return if limiter.conn then limiter.fps else nil
end

-- PattayaTraffic stamps its folder with DrawT, the server time it drew and hit-tested its cars with, every Heartbeat
-- (and DrawHz, its draws per second). TestKit computes positions AT DrawT whenever it compares them with the drawn
-- models. Round 6: TK.hitMatrixStart's runner is resumed by its own Heartbeat connection, which can run before
-- PattayaTraffic's in the same frame (Roblox does not order handlers; later connections usually fire first): it then
-- still saw the models of the frame before while GetServerTimeNow() had moved on by a frame (67 ms at 15 fps, ~0.1 s
-- with a slow frame), i.e. 5-6 studs at traffic speed: selfCheck 0/5 and pickTarget's 4-stud match failed. The
-- positions are a pure function of the time, so computing them at DrawT is exact whatever the handler order or rate.
-- nil when PattayaTraffic is older (no DrawT) or not drawing (stale by more than 0.5 s).
local function drawT(): number?
	local f = workspace:FindFirstChild("PattayaTraffic")
	local t = f and f:GetAttribute("DrawT")
	if type(t) == "number" and math.abs(workspace:GetServerTimeNow() - t) < 0.5 then
		return t
	end
	return nil
end
TK.drawT = drawT

-- traffic cars around the car (or `at`) at server time atT (default: now), nearest first, computed with
-- PattayaRecovery's shared functions: the same numbers PattayaTraffic draws its cars with (by construction since
-- team18/arcade-fix-4). Each entry: key (the car's key in PattayaTraffic and its model's TrafficKey attribute), ri, k,
-- pos, look, speed, halfLen, halfWid, kind, dist, route, s, t (= atT).
function TK.trafficNear(radius: number?, at: Vector3?, atT: number?)
	assert(Rec, "trafficNear: ReplicatedStorage.PattayaRecovery missing")
	if not trafficRoutes then
		local data = ReplicatedStorage:FindFirstChild("PattayaTraffic")
		assert(data, "trafficNear: ReplicatedStorage.PattayaTraffic missing")
		trafficRoutes = Rec.buildTrafficRoutes(require(data :: ModuleScript), Rec.TRAFFIC_ORIGIN_X, Rec.TRAFFIC_ORIGIN_Z)
	end
	local c = at
	if not c then
		local chassis = TK.car()
		c = chassis and chassis.Position
	end
	assert(c, "trafficNear: get in a car or pass a position")
	local out = {}
	for _, e in Rec.trafficNear(trafficRoutes, atT or workspace:GetServerTimeNow(), c.X, c.Z, radius or 300) do
		local te = Rec.tkTrafficEntry(e)
		te.pos = Vector3.new(te.x, Rec.TRAFFIC_ROAD_Y, te.z)
		te.look = Vector3.new(te.lx, 0, te.lz)
		table.insert(out, te)
	end
	return out
end

-- where traffic car e (a trafficNear entry) is at server time t, shared maths: x, z, heading lx, lz
local function carAt(e, t: number): (number, number, number, number)
	local x, z, s = Rec.trafficCarAt(e.route, e.k, t)
	local lx, lz = Rec.trafficHeading(e.route, s)
	return x, z, lx, lz
end

-- the traffic models PattayaTraffic shows right now, by key (its TrafficKey attribute)
local function trafficModels(): {[number]: Model}
	local out = {}
	local folder = workspace:FindFirstChild("PattayaTraffic")
	if folder then
		for _, m in folder:GetChildren() do
			local key = m:IsA("Model") and m.PrimaryPart and m:GetAttribute("TrafficKey")
			if type(key) == "number" then out[key] = m :: Model end
		end
	end
	return out
end
TK.trafficModels = trafficModels

-- the traffic model PattayaTraffic shows near a spot (diagnostics only: targets and hits are identified by key)
local function trafficModelAt(pos: Vector3, within: number): Model?
	local folder = workspace:FindFirstChild("PattayaTraffic")
	if not folder then return nil end
	local best, bd = nil, within
	for _, m in folder:GetChildren() do
		local root = m:IsA("Model") and m.PrimaryPart
		if root then
			local d = flat(root.Position - pos).Magnitude
			if d < bd then best, bd = m, d end
		end
	end
	return best :: Model?
end
TK.trafficModelAt = trafficModelAt

-- ghosted by PattayaTraffic (faded, no arcade hits)?
local function ghosted(m: Model): boolean
	local root = m.PrimaryPart
	return root ~= nil and (root.LocalTransparencyModifier or 0) > 0.3
end

-- drawn vs computed, a diagnostic (never a gate): how far car e's model stands behind where the shared maths puts
-- it at `now` (studs, and ms of its travel), and how far from its spot at the time it was drawn (dT)
local function modelLag(m: Model, e, now: number, dT: number?): (number, number, number?)
	local p = (m.PrimaryPart :: BasePart).Position
	local xn, zn = carAt(e, now)
	local behind = math.sqrt((p.X - xn) ^ 2 + (p.Z - zn) ^ 2)
	local atDraw = nil
	if dT then
		local xd, zd = carAt(e, dT)
		atDraw = math.sqrt((p.X - xd) ^ 2 + (p.Z - zd) ^ 2)
	end
	return behind, behind / math.max(e.speed, 1e-3) * 1000, atDraw
end

-- TK.selfCheck(n?, at?) -> ok, lines, info   run it before hitMatrix (hitMatrix does).
-- Checked (ok): PattayaTraffic draws with the shared maths (folder Positions = "shared") and stamps DrawT; for the n
-- (5) nearest cars that have a model, the model carrying that car's TrafficKey stands where the shared maths puts
-- that key AT DrawT, within 0.5 studs (32-bit positions); no TK_HitTarget / TrafficGhostAll left over.
-- Reported only (never a failure): how far the models are behind the computed spot NOW, in studs and ms (round 6's
-- 5-6 studs), DrawT's age, PattayaTraffic's draw rate and this client's frame rates (info has the numbers).
function TK.selfCheck(n: number?, at: Vector3?)
	assert(Rec, "selfCheck: PattayaRecovery missing")
	if not at and not TK.car() then
		local cam = workspace.CurrentCamera
		at = cam and cam.Focus.Position
	end
	local folder = workspace:FindFirstChild("PattayaTraffic")
	local positions = folder and folder:GetAttribute("Positions")
	local drawHz = folder and folder:GetAttribute("DrawHz")
	local dT = drawT()
	local now = workspace:GetServerTimeNow()
	local models = trafficModels()
	local anyTagged = next(models) ~= nil
	local lines = {}
	local compared, matched, lagMax, lagMsMax = 0, 0, 0, 0
	for _, e in TK.trafficNear(650, at, dT or now) do
		if compared >= (n or 5) then break end
		local m = models[e.key]
		if not m then continue end -- no model (pool full or out of range): nothing to compare
		compared += 1
		local behind, ms, atDraw = modelLag(m, e, now, dT)
		lagMax, lagMsMax = math.max(lagMax, behind), math.max(lagMsMax, ms)
		local good = atDraw ~= nil and atDraw <= 0.5
		if good then matched += 1 end
		table.insert(lines, ("%s key %d (route %d car %d) at (%.0f, %.0f), %.0f studs away: model %s from its spot at DrawT; %.1f studs / %.0f ms behind now%s"):format(
			if good then "match" else "MISMATCH", e.key, e.ri, e.k, e.x, e.z, e.dist,
			if atDraw then ("%.2f studs"):format(atDraw) else "(no DrawT)", behind, ms,
			if ghosted(m) then " (ghosted)" else ""))
	end
	local hook = player:GetAttribute("TK_HitTarget")
	local ghostAll = player:GetAttribute("TrafficGhostAll") == true
	local ok = compared > 0 and matched == compared and positions == "shared" and dT ~= nil and hook == nil
		and not ghostAll
	local info = {compared = compared, matched = matched, lagStuds = lagMax, lagMs = lagMsMax,
		drawAgeMs = if dT then (now - dT) * 1000 else nil, drawHz = drawHz, hb = rates.hb, render = rates.render,
		fpsLimit = TK.fpsLimitOn()}
	table.insert(lines, ("selfCheck diagnostic (not a gate): drawn models up to %.1f studs / %.0f ms behind the computed spot now; DrawT %s old; PattayaTraffic draws %s/s; Heartbeat %.0f Hz, render %.0f fps%s"):format(
		lagMax, lagMsMax, if dT then ("%.0f ms"):format((now - dT) * 1000) else "-", tostring(drawHz), rates.hb,
		rates.render, if info.fpsLimit then (", TestKit FPS cap %s"):format(tostring(info.fpsLimit)) else ""))
	table.insert(lines, ("selfCheck: %d/%d keys match their models at DrawT; PattayaTraffic positions: %s%s%s%s%s%s"):format(
		matched, compared, tostring(positions),
		if dT then "" else "; no fresh DrawT on workspace.PattayaTraffic (PattayaTraffic older than team18/arcade-fix-5, or not drawing)",
		if anyTagged then "" else "; models carry no TrafficKey (old PattayaTraffic?)",
		if hook ~= nil then ("; TK_HitTarget is still set (%s)"):format(tostring(hook)) else "",
		if ghostAll then "; TrafficGhostAll is still set (TK.ghostTraffic(false))" else "",
		if ok then " - OK" else " - FAIL"))
	for _, l in lines do print(l) end
	return ok, lines, info
end

-- staged hit: plan, target and lane checks (all maths in PattayaRecovery: stagePlan, routeStraight,
-- plannedPathClear, acceptStagedHit; tested offline in tools/qa/tests/test_recovery.py)
local function stage(target, mode: string, speed: number, opts)
	return Rec.stagePlan({route = target.route, s0 = target.s, t0 = target.t, vT = target.speed,
		halfWid = target.halfWid, halfLen = target.halfLen, speed = speed, mode = mode, lead = opts.lead,
		offset = opts.offset, angle = opts.angle, runLat = opts.runLat, gap = opts.gap})
end

-- The target: the nearest traffic car that
--   1. has a model under its key that is not ghosted (a car without a model cannot be hit). Where that model is drawn
--      is never used (round 6: it lags by a frame in the runner);
--   2. drives a straight stretch: the whole staged approach within opts.maxBend (R.STAGE_BEND_DEG, 15) degrees of
--      one direction (round 6, route 26: a kink between the cars made a rear-end a head-on and moved the touch
--      0.38 s), and for side hits its heading steady within opts.steady (R.SIDE_STEADY_DEG, 1) degree around the
--      touch (the side rows sit 1-3 degrees from a tier threshold);
--   3. whose approach stays opts.clearance (30) studs from every other traffic car.
-- Returns target, clear (false = 1 and 2 hold but no approach was clear: the nearest such car), skipped (counts).
local function pickTarget(mode: string, speed: number, opts, startDelay: number)
	local clearance = opts.clearance or 30
	local fallback = nil
	local skipped = {excluded = 0, model = 0, ghosted = 0, bend = 0, busy = 0}
	local models = trafficModels()
	local tRef = drawT() or workspace:GetServerTimeNow()
	local t0 = workspace:GetServerTimeNow() + startDelay
	for _, e in TK.trafficNear(opts.radius or 500, opts.around, tRef) do
		if opts.excludeKeys and opts.excludeKeys[e.key] then
			skipped.excluded += 1
			continue
		end
		local m = models[e.key]
		if not m then
			skipped.model += 1
			continue
		end
		if ghosted(m) then
			skipped.ghosted += 1
			continue
		end
		-- plan from the moment the approach will start
		local probe = table.clone(e)
		probe.s, probe.t = e.s + e.speed * (t0 - e.t), t0
		local plan, meet, span, touch = stage(probe, mode, speed, opts)
		if span and not Rec.routeStraight(e.route, span[1], span[2], opts.maxBend or Rec.STAGE_BEND_DEG or 15) then
			skipped.bend += 1
			continue
		end
		if mode == "side" and touch
			and not Rec.routeStraight(e.route, touch[1], touch[2], opts.steady or Rec.SIDE_STEADY_DEG or 1, 2) then
			skipped.bend += 1
			continue
		end
		fallback = fallback or e
		local others = {}
		local x0, z0 = plan(t0)
		for _, o in TK.trafficNear(700, Vector3.new(x0, 1, z0), t0) do
			if o.key ~= e.key then table.insert(others, o) end
		end
		if Rec.plannedPathClear(plan, t0, meet, others, clearance) then
			return e, true, skipped
		end
		skipped.busy += 1
	end
	return fallback, false, skipped
end

local function skippedText(s): string
	if not s then return "" end
	return (" (%d without a model, %d ghosted, %d on a bend, %d excluded)"):format(s.model, s.ghosted, s.bend, s.excluded)
end

-- every collidable part that moves with my car: the chassis AND the seated character (its torso and head collide;
-- the round 4 side rows lost 25-90 studs/s before the touch, the likeliest cause being the driver's body hitting
-- palms / signs beside the lane between two frames)
local function carColliders(model: Model): {BasePart}
	local out = {}
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then table.insert(out, d) end
	end
	if player.Character then
		for _, d in player.Character:GetDescendants() do
			if d:IsA("BasePart") then table.insert(out, d) end
		end
	end
	return out
end

-- the first solid part that is not road which any of `parts` is inside (nil = clear). After a hit my car's
-- collisions go back on only once it is clear, so switching them on never pops it out of a kerb, a palm or a sign.
local function insideScenery(parts: {BasePart}, ignore: {Instance}): BasePart?
	if #parts == 0 then
		return nil
	end
	local params = OverlapParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore
	params.RespectCanCollide = true
	for _, p in parts do
		if p.Parent then
			for _, h in workspace:GetPartsInPart(p, params) do
				if not (ROAD_NAMES[h.Name] or h.Material == Enum.Material.Asphalt) then
					return h
				end
			end
		end
	end
	return nil
end

-- CarController's auto-upright turns the car over for Recovery_UprightTime s from Recovery_LastUprightAt; it moves
-- the car itself and CarController ignores traffic hits while it runs, so a staged run waits for it to end
local function waitUpright(cfg)
	local t0 = os.clock()
	while os.clock() - t0 < 3 do
		local at = player:GetAttribute("Recovery_LastUprightAt")
		if type(at) ~= "number" or workspace:GetServerTimeNow() - at > (cfg.Recovery_UprightTime or 0.6) + 0.3 then
			return
		end
		waitFrame()
	end
end

-- every number of the hit CarController applied (it sets them all before Recovery_HitCount), read in one go the
-- frame the count changes: a later hit can no longer overwrite what a run reports (round 6, side 70: a second hit
-- 1.5 s later, at 33-40 studs/s, replaced the first one's numbers before they were read)
local HIT_FIELDS = {key = "Recovery_LastHitKey", t = "Recovery_LastHitT", tier = "Recovery_LastHitTier",
	before = "Recovery_LastHitBefore", after = "Recovery_LastHitAfter", trafficSpeed = "Recovery_LastHitTrafficSpeed",
	vc = "Recovery_LastHitVc", rel = "Recovery_LastHitRel", angle = "Recovery_LastHitAngle",
	facing = "Recovery_LastHitFacing", n = "Recovery_LastHitN", yaw = "Recovery_LastHitYaw",
	control = "Recovery_LastHitControl", pos = "Recovery_LastHitPos"}
local function snapshotHit()
	local s = {}
	for k, a in HIT_FIELDS do
		s[k] = player:GetAttribute(a)
	end
	return s
end

local BRAKE = 120 -- studs/s2: the test's gentle stop after the hit response (the jobs bump detector needs 157)

local function int(x): string
	return if type(x) == "number" and x == x then tostring(math.floor(x + 0.5)) else "-"
end
local function since(t, ref: number): string
	return if type(t) == "number" then ("meet%+.3f s"):format(t - ref) else "-"
end

-- one line per staged hit with every field the owner's review asks for (round 6): target and actual hit IDs and
-- whether they match, the player's impact speed, the traffic speed and the closing speed as separate numbers, tier,
-- speed loss, yaw, minUp and the frame rate
local function rowText(res): string
	local label = ("%s @%d%s"):format(res.mode, res.speed, if res.angle then " a" .. res.angle
		elseif res.offset then " off" .. res.offset else "")
	local idText = if res.hitKey == nil then "no hit" elseif res.keyMatch then "match" else "NOT the target"
	return ("hitTest %s [%s%s, Heartbeat %.0f Hz, render %.0f fps]: %s | target %s, hit %s, %s | impact %s, traffic %s, closing %s (planned %s) | tier %s | loss %s%% (%s -> %s) | yaw %s (spin %s, scripted %s) | minUp %.2f%s | approach-min %s | touch %s, hand-off %s | lag %s%s"):format(
		label, res.model, if res.ghostedOthers then ", isolated" else "", res.hz or 0, res.render or 0,
		if res.touched then "hit" else "MISSED (" .. tostring(res.reason) .. ")",
		tostring(res.targetKey), tostring(res.hitKey or "-"), idText,
		int(res.before), int(res.trafficSpeed), int(res.vc), int(res.planned and res.planned.vc),
		tostring(res.tier or "-"), int(res.lossPct), int(res.before), int(res.after), int(res.yawDeg), int(res.spinYaw),
		int(res.scriptYaw),
		res.minUp, if res.minUp < 0.995 then (" at +%.2f s"):format(res.minUpAt or 0) else "", int(res.approachMin),
		since(res.hitT, res.meet), since(res.handOff, res.meet),
		if res.lag then ("%.1f studs / %.0f ms"):format(res.lag, res.lagMs or 0) else "-",
		if (res.extraHits or 0) > 0 then (" | %d more hit(s)"):format(res.extraHits) else "")
end

-- one staged hit. Everything it changes (TK_HitTarget, collisions, connections) is undone by `cleanup`, which
-- hitOnce runs whatever happens (MISSED, rejected, error), and TK.cleanup runs for runs still in progress.
local function hitBody(mode: string, speed: number, opts, cleanup: {() -> ()})
	local chassis, model = TK.car()
	assert(chassis and model and Rec, "hitTest: get in a car first (and PattayaRecovery must be installed)")
	assert(player:GetAttribute("TrafficGhostAll") ~= true, "hitTest: TrafficGhostAll is on (TK.ghostTraffic(false) first)")
	local arcade = workspace:GetAttribute("CollisionModel") == "arcade"
	local cfg = Rec.config()
	local START_DELAY = 0.3 -- s between the target choice and the start of the approach (placement + one frame)
	waitUpright(cfg)
	local target, clear, skipped = opts.target, true, nil
	if not target then
		target, clear, skipped = pickTarget(mode, speed, opts, START_DELAY)
	end
	assert(target, "hitTest: no traffic car to stage the hit on nearby" .. skippedText(skipped))
	assert(target.key ~= nil, "hitTest: target without a key")
	-- isolate: every other car ghosts for this run (TestKit-only hook TK_HitTarget in PattayaTraffic). Default for
	-- TK.hitMatrix; otherwise only when no clear lane was found
	local ghostOthers = opts.isolate == true or not clear
	if ghostOthers then
		player:SetAttribute("TK_HitTarget", target.key)
		table.insert(cleanup, function() player:SetAttribute("TK_HitTarget", nil) end)
	end
	local approachT = workspace:GetServerTimeNow() + START_DELAY
	local probe = table.clone(target)
	probe.s, probe.t = target.s + target.speed * (approachT - target.t), approachT
	local plan, meetAt = stage(probe, mode, speed, opts)
	local _, planned = Rec.expectedStaged(mode, speed, opts.angle, target.speed, cfg)
	local Y = 1 + 2.8 -- road + chassis ride height (traffic roads are at Y = 1)
	local uprightsBefore = player:GetAttribute("Recovery_Uprights") or 0
	-- arcade: nothing on my car collides during the hold and the approach (scenery cannot slow it before the touch;
	-- the wheel rays still hold it up). Re-applied every step (the Humanoid may switch body parts back).
	local colliders = if arcade then carColliders(model) else {}
	local saved = {}
	for _, p in colliders do saved[p] = p.CanCollide end
	local restored = false
	local function restoreCollisions()
		if restored then return end
		restored = true
		for p, c in saved do
			if p.Parent then p.CanCollide = c end
		end
	end
	table.insert(cleanup, restoreCollisions)
	local function noCollide()
		for _, p in colliders do
			if p.Parent and p.CanCollide then p.CanCollide = false end
		end
	end
	local solid = {}
	for p, c in saved do
		if c then table.insert(solid, p) end
	end
	local ignore = excludeList(model)
	local st = {done = false, reason = "", frames = 0, startClock = 0, abort = nil :: string?,
		targetCheck = "not checked" :: string?, handOff = nil :: number?, snap = nil :: any,
		dir = Vector3.new(0, 0, -1), lag = nil :: number?, lagMs = nil :: number?, touch = nil :: any,
		prevGap = nil :: number?}
	local hitsBefore, touchesBefore = nil, nil
	-- per-frame log around the hit, taken at Heartbeat (the phase PattayaTraffic tests in): the last 10 frames of the
	-- approach and the first 6 after the hit was counted
	local pre, post = {}, {}
	local seen = {min = math.huge}
	local function logLine(tag: string, t: number): string
		local v = chassis.AssemblyLinearVelocity
		local p = chassis.Position
		local l = flat(chassis.CFrame.LookVector)
		l = if l.Magnitude > 0.1 then l.Unit else Vector3.new(0, 0, -1)
		local tx, tz, tlx, tlz = carAt(target, t)
		local tvx, tvz = tlx * target.speed, tlz * target.speed
		local info = Rec.hitFromWorld({x = p.X, z = p.Z, lx = l.X, lz = l.Z, vx = v.X, vz = v.Z},
			{x = tx, z = tz, lx = tlx, lz = tlz, speed = target.speed, halfWid = target.halfWid, halfLen = target.halfLen})
		local dT = drawT()
		return ("  %-9s t=%s%s | me %.0f (%.0f, %.0f) | target %.0f (%.0f, %.0f), centres %.1f studs | relative %.0f | %s"):format(
			tag, since(t, meetAt), if dT then " drawT=" .. since(dT, meetAt) else "", flat(v).Magnitude, v.X, v.Z,
			target.speed, tvx, tvz, math.sqrt((p.X - tx) ^ 2 + (p.Z - tz) ^ 2),
			math.sqrt((v.X - tvx) ^ 2 + (v.Z - tvz) ^ 2),
			if info then ("boxes overlap: vc %.0f n (%.2f, %.2f) depth %.1f"):format(info.vc, info.nx, info.nz, info.depth)
				else "apart")
	end
	local hb = RunService.Heartbeat:Connect(function()
		local t = workspace:GetServerTimeNow()
		if t < approachT or not hitsBefore then return end
		local count = player:GetAttribute("Recovery_HitCount") or 0
		if count ~= hitsBefore then
			if #post < 6 then table.insert(post, logLine(if #post == 0 then "HIT seen" else "after", t)) end
			return
		end
		if st.handOff then return end
		seen.min = math.min(seen.min, flat(chassis.AssemblyLinearVelocity).Magnitude)
		table.insert(pre, logLine("approach", t))
		if #pre > 10 then table.remove(pre, 1) end
	end)
	table.insert(cleanup, function() hb:Disconnect() end)
	local conn = onPreSim(function(stepDt: number)
		if st.done then return end
		if arcade then noCollide() end
		local t = workspace:GetServerTimeNow()
		local count = player:GetAttribute("Recovery_HitCount") or 0
		if t < approachT then
			-- holding at the start: anything counted here is not the staged hit. The target must have a model under
			-- its key that is real (a car without a model cannot be hit; the isolation hook ghosts every OTHER car).
			-- Where that model is drawn is only measured (lag), never compared.
			hitsBefore = count
			touchesBefore = player:GetAttribute("Traffic_Touches") or 0
			local m = trafficModels()[target.key]
			st.targetCheck = if not m then "no model under its key (pool full or out of range)"
				elseif ghosted(m) then "its model is ghosted" else nil
			if m then
				st.lag, st.lagMs = modelLag(m, target, t)
			end
			local x, z, dx, dz = plan(approachT)
			local p = Vector3.new(x, Y, z)
			chassis.CFrame = CFrame.lookAt(p, p + Vector3.new(dx, 0, dz))
			chassis.AssemblyLinearVelocity = Vector3.zero
			chassis.AssemblyAngularVelocity = Vector3.zero
			return
		end
		if st.frames == 0 then
			st.startClock = os.clock()
			if st.targetCheck then
				st.done, st.reason, st.abort = true, "target check: " .. tostring(st.targetCheck), "target"
				return
			end
		end
		st.frames += 1
		if hitsBefore and count ~= hitsBefore then
			-- a hit was applied: snapshot it before anything can overwrite it, then decide whether it is the staged
			-- one by the key the hit event names (never by where a model is drawn) and by its own time
			local snap = snapshotHit()
			st.snap, st.handOff = snap, t
			local ok, why = Rec.acceptStagedHit({hitT = if type(snap.t) == "number" then snap.t else t,
				approachT = approachT, meet = meetAt, frameDt = 1 / math.max(rates.hb, 1), hitKey = snap.key,
				targetKey = target.key})
			st.done = true
			st.reason = if ok then "hit" else "rejected: " .. tostring(why)
			if not ok and not ghostOthers and why and why:find("another car", 1, true) then
				st.abort = "another car hit"
			end
			return
		end
		local touches = player:GetAttribute("Traffic_Touches") or 0
		if touchesBefore and touches ~= touchesBefore and not st.touch then
			st.touch = {t = t, key = player:GetAttribute("Traffic_TouchKey"), frame = st.frames}
		end
		-- not isolated: another car coming within 30 studs of mine before the touch aborts the run (TK.hitTest retries)
		if not ghostOthers and t < meetAt - 0.05 then
			for _, o in TK.trafficNear(opts.clearance or 30, chassis.Position) do
				if o.key ~= target.key then
					st.done, st.reason, st.abort = true, "traffic in the way", "traffic in the way"
					return
				end
			end
		end
		local x, z, dx, dz, gap = plan(t)
		if not arcade and gap <= 0.3 then
			st.done, st.reason, st.handOff = true, "contact", t -- physics takes the touch from here
		elseif arcade and st.prevGap and st.prevGap < -4 then
			-- the car stood more than 4 studs into it at the last Heartbeat (where PattayaTraffic tests) and no hit
			-- was counted (this frame's planned gap alone would call it before that Heartbeat at low frame rates)
			st.done, st.reason, st.handOff = true, "no hit registered (overlapping)", t
		elseif t > meetAt + 2 or t - approachT > (opts.timeout or 10) then
			st.done, st.reason, st.handOff = true, "timeout", t
		end
		-- placed one physics step short of the plan: this step moves it speed * stepDt on, so at Heartbeat, where
		-- PattayaTraffic tests the touch, it is exactly on the plan (unplaced, the touch came speed * dt / vc early:
		-- 0.3 s for rear 70 at 15 fps)
		local dir = Vector3.new(dx, 0, dz).Unit
		local p = Vector3.new(x, Y, z) - dir * (speed * math.clamp(stepDt or 0, 0, 0.1))
		st.dir, st.prevGap = dir, gap
		chassis.CFrame = CFrame.lookAt(p, p + dir)
		chassis.AssemblyLinearVelocity = dir * speed
		chassis.AssemblyAngularVelocity = Vector3.zero
	end)
	table.insert(cleanup, function() conn:Disconnect() end)
	while not st.done do waitFrame() end
	conn:Disconnect()
	local frameHz = if st.frames > 1 then (st.frames - 1) / math.max(os.clock() - st.startClock, 1e-3) else rates.hb
	local renderFps = rates.render
	local immediate = flat(chassis.AssemblyLinearVelocity).Magnitude
	local snap = st.snap
	local good = st.reason == "hit"
	-- the hit response: CarController's hit window (control / spin, Recovery_LastHitControl) + the anti-roll's
	-- extra; the test watches it plus 0.3 s, then brakes the car gently to a stop (round 6's side 150 rows went on at
	-- ~145 studs/s for the whole 2 s, off the end of the straight into kerbs and scenery: ordinary driving, not the hit)
	local window = if snap and type(snap.control) == "number" then snap.control else 0
	-- (the braking time stays tied to Arcade_AntiRollExtra as in round 7: CarController's longer anti-roll after heavy
	-- / head-on hits, Arcade_AntiRollHeavyExtra, does not change when this test's driver brakes)
	local respond = window + (cfg.Arcade_AntiRollExtra or 0) + 0.3
	local w = {minUp = 1, minUpAt = 0, minUpWhere = nil :: string?, minSpeed = immediate, minDist = math.huge,
		collisionsAt = nil :: number?, blocker = nil :: string?, brakeAt = nil :: number?}
	local function brake()
		local vv = chassis.AssemblyLinearVelocity
		local sp = flat(vv).Magnitude
		if sp > 0.5 then
			local k = math.max(sp - BRAKE / math.max(rates.hb, 15), 0) / sp
			chassis.AssemblyLinearVelocity = Vector3.new(vv.X * k, vv.Y, vv.Z * k)
		end
	end
	local t1 = os.clock()
	local yawLook = nil
	-- diagnostics, never a gate (round 8, 60 fps rear @100: yaw 34 of a scripted 53, then minUp 0.82 over the
	-- sidewalk): the yaw the scripted spin reached at its end (spinProfile's T + 0.05 s), every part that is not road
	-- the car's colliders touched while watched, and how far the car went off the target's lane (+ = right of it;
	-- the near kerb is on the left, traffic keeps left)
	local diag = {spinT = math.clamp(math.max(window, 0.25) * 0.6, 0.15, 0.6), spinYaw = nil :: number?,
		contacts = {} :: {string}, seen = {}, laneMax = 0, laneAtMinUp = nil :: number?, speedAtMinUp = nil :: number?}
	local laneX, laneZ, laneTx, laneTz = nil, nil, nil, nil
	if snap and type(snap.t) == "number" and target.route and target.k then
		local hx, hz, hs = Rec.trafficCarAt(target.route, target.k, snap.t)
		laneX, laneZ = hx, hz
		laneTx, laneTz = Rec.routeTangent(target.route, hs)
	end
	local touchConns = {}
	if arcade and snap and st.abort == nil then
		local skip = {workspace:FindFirstChild("PattayaTraffic"), model, player.Character}
		for _, part in solid do
			table.insert(touchConns, part.Touched:Connect(function(other: BasePart)
				if #diag.contacts >= 12 or ROAD_NAMES[other.Name] or string.sub(other.Name, 1, 4) == "Curb" then
					return
				end
				for _, s in skip do
					if s and other:IsDescendantOf(s) then
						return
					end
				end
				local name = other:GetFullName()
				if not diag.seen[name] then
					diag.seen[name] = true
					table.insert(diag.contacts, ("%s (%s, top y %.1f) at +%.2f s"):format(name, part.Name,
						other.Position.Y + other.Size.Y / 2, os.clock() - t1))
				end
			end))
		end
	end
	table.insert(cleanup, function()
		for _, c in touchConns do
			c:Disconnect()
		end
	end)
	if st.abort == nil then
		while os.clock() - t1 < (opts.watch or 2) do
			waitFrame()
			local el = os.clock() - t1
			local up = chassis.CFrame.UpVector.Y
			local lat = nil
			if laneX then
				lat = (chassis.Position.X - laneX) * -(laneTz :: number) + (chassis.Position.Z - laneZ) * (laneTx :: number)
				if math.abs(lat) > math.abs(diag.laneMax) then
					diag.laneMax = lat
				end
			end
			if diag.spinYaw == nil and el >= diag.spinT + 0.05 then
				local l = flat(chassis.CFrame.LookVector)
				if l.Magnitude > 0.1 then
					l = l.Unit
					diag.spinYaw = math.deg(math.atan2(st.dir:Cross(l).Y, st.dir:Dot(l)))
				end
			end
			if up < w.minUp then
				w.minUp, w.minUpAt = up, el
				local okProbe, info = pcall(TK.probeRoadUnderCar)
				w.minUpWhere = if okProbe and info then (if info.road then "on road " else "off road ") .. tostring(info.name)
					else nil
				diag.laneAtMinUp, diag.speedAtMinUp = lat, flat(chassis.AssemblyLinearVelocity).Magnitude
			end
			local v = flat(chassis.AssemblyLinearVelocity).Magnitude
			if el < 0.4 then w.minSpeed = math.min(w.minSpeed, v) end
			local tx, tz = carAt(target, workspace:GetServerTimeNow())
			w.minDist = math.min(w.minDist, math.sqrt((chassis.Position.X - tx) ^ 2 + (chassis.Position.Z - tz) ^ 2))
			if arcade then
				if not restored then
					local b = insideScenery(solid, ignore)
					if b then
						w.blocker = b:GetFullName()
					else
						restoreCollisions()
						w.collisionsAt = el
					end
				end
				if good and el > respond then
					w.brakeAt = w.brakeAt or el
					brake()
				end
			end
		end
		yawLook = flat(chassis.CFrame.LookVector)
		-- gentle stop (below the jobs bump detector), then stop the car where it is
		local t2 = os.clock()
		while arcade and os.clock() - t2 < 2 and flat(chassis.AssemblyLinearVelocity).Magnitude > 20 do
			waitFrame()
			brake()
		end
	end
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	hb:Disconnect()
	local look0 = st.dir
	local look1 = yawLook or flat(chassis.CFrame.LookVector)
	look1 = if look1.Magnitude > 0.1 then look1.Unit else look0
	local yaw = math.deg(math.atan2(look0:Cross(look1).Y, look0:Dot(look1)))
	local countNow = player:GetAttribute("Recovery_HitCount") or 0
	local res = {mode = mode, speed = speed, angle = opts.angle, offset = opts.offset,
		model = if arcade then "arcade" else "physical", reason = st.reason, abort = st.abort, yawDeg = yaw,
		minUp = w.minUp, minUpAt = w.minUpAt, minUpWhere = w.minUpWhere, flipped = w.minUp < 0.5, hz = frameHz,
		render = renderFps, fpsLimit = TK.fpsLimitOn(), ghostedOthers = ghostOthers, vT = target.speed,
		targetKey = target.key, approachMin = if seen.min < math.huge then seen.min else nil,
		uprights = (player:GetAttribute("Recovery_Uprights") or 0) - uprightsBefore, lag = st.lag, lagMs = st.lagMs,
		window = window, respond = respond, brakeAt = w.brakeAt, collisionsAt = w.collisionsAt, blocker = w.blocker,
		planned = planned, meet = meetAt, approachT = approachT, handOff = st.handOff,
		extraHits = if hitsBefore and snap then math.max(countNow - hitsBefore - 1, 0) else 0}
	if snap then
		res.hitKey, res.keyMatch, res.hitT = snap.key, snap.key == target.key, snap.t
		res.trafficSpeed, res.rel, res.scriptYaw = snap.trafficSpeed, snap.rel, snap.yaw
	end
	if arcade then
		-- every number is the staged hit's own (the snapshot): player speed, traffic speed and closing speed apart
		res.touched, res.onTarget = good, good
		res.tier = if snap then snap.tier else nil
		res.vc = if snap then snap.vc else nil
		res.before = if snap and type(snap.before) == "number" then snap.before else speed
		res.after = if snap and type(snap.after) == "number" then snap.after else immediate
		res.measured = immediate
	else
		res.before, res.after, res.measured = speed, w.minSpeed, immediate
		res.touched = st.reason == "contact" and (w.minSpeed < speed * 0.9 or w.minDist < target.halfLen + 9)
		res.onTarget = res.touched
	end
	res.lossPct = (1 - (res.after or 0) / math.max(res.before or speed, 1)) * 100
	res.lastHit = player:GetAttribute("Recovery_LastHit")
	-- why nothing was counted: did PattayaTraffic find a touch (Traffic_Touches) and CarController not apply it
	-- (Recovery_HitIgnored), or was there no touch at all?
	if not snap and st.abort == nil and arcade then
		local parts = {}
		local touches = player:GetAttribute("Traffic_Touches") or 0
		if st.touch or (touchesBefore and touches ~= touchesBefore) then
			table.insert(parts, ("PattayaTraffic found a touch (key %s)"):format(tostring(player:GetAttribute("Traffic_TouchKey"))))
			local ignAt = player:GetAttribute("Recovery_HitIgnoredAt")
			if type(ignAt) == "number" and ignAt >= approachT - 0.1 then
				table.insert(parts, "CarController ignored it: " .. tostring(player:GetAttribute("Recovery_HitIgnored")))
			else
				table.insert(parts, "CarController did not count it")
			end
		elseif drawT() ~= nil then
			table.insert(parts, "PattayaTraffic found no touch")
		end
		local m = trafficModels()[target.key]
		table.insert(parts, if not m then "the target has no model now" elseif ghosted(m) then "the target is ghosted now"
			else "the target is real")
		res.miss = table.concat(parts, "; ")
	end
	local log = {("  plan: approach from %s, touch planned at server time %.3f; %s"):format(since(approachT, meetAt),
		meetAt, if snap then ("PattayaTraffic touch at %s on key %s (vc %s, n %s), TestKit hand-off at %s (approach frame %d)")
			:format(since(snap.t, meetAt), tostring(snap.key), int(snap.vc), tostring(snap.n), since(st.handOff, meetAt),
			st.frames) else "no hit counted" .. (if res.miss then " - " .. res.miss else ""))}
	for _, l in pre do table.insert(log, l) end
	for _, l in post do table.insert(log, l) end
	table.insert(log, ("  after: collisions %s; %s; lowest up %.2f at +%.2f s%s; hit window %.2f s (+%.2f anti-roll, +0.3 watched)"):format(
		if w.collisionsAt then ("back on at +%.2f s"):format(w.collisionsAt)
			elseif w.blocker then "stayed off (inside " .. w.blocker .. ")" else "unchanged",
		if w.brakeAt then ("braking from +%.2f s"):format(w.brakeAt) else "no braking", w.minUp, w.minUpAt,
		if w.minUpWhere then " " .. w.minUpWhere else "", window,
		if snap and Rec.antiRollHold then Rec.antiRollHold(tostring(snap.tier), window, cfg) - window
			else cfg.Arcade_AntiRollExtra or 0))
	if snap and arcade then
		table.insert(log, ("  diag: the spin reached %s at +%.2f s (scripted %s); off the target's lane up to %+.1f studs (+ = right; the near kerb is on the left)%s; touched: %s"):format(
			if diag.spinYaw then ("%+d deg"):format(math.floor(diag.spinYaw + 0.5)) else "-", diag.spinT + 0.05,
			int(snap.yaw), diag.laneMax,
			if diag.laneAtMinUp then (", at the lowest up %+.1f studs at %d studs/s"):format(diag.laneAtMinUp,
				math.floor((diag.speedAtMinUp or 0) + 0.5)) else "",
			if #diag.contacts > 0 then table.concat(diag.contacts, "; ") else "nothing but road"))
	end
	res.spinYaw, res.contacts, res.laneMax = diag.spinYaw, diag.contacts, diag.laneMax
	res.log = log
	res.text = rowText(res)
	return res
end

-- the cleanup lists of the staged runs in progress: TK.cleanup runs them (a stopped TK.hitMatrixStart never returns
-- to hitOnce, so its car collisions and connections would otherwise stay as the run left them)
local activeRuns: {[{() -> ()}]: boolean} = live.activeRuns
local function runCleanup(list: {() -> ()})
	for i = #list, 1, -1 do
		pcall(list[i])
	end
	table.clear(list)
end

-- finally-style wrapper: the cleanup runs on every path, errors included (round 5: TK_HitTarget must never stay set)
local function hitOnce(mode: string, speed: number, opts)
	local cleanup = {}
	activeRuns[cleanup] = true
	local ok, res = pcall(hitBody, mode, speed, opts, cleanup)
	runCleanup(cleanup)
	activeRuns[cleanup] = nil
	if not ok then
		error(res, 0)
	end
	return res
end

-- staged hit with retries: a run aborted by other traffic (not isolated) or by a failed target check is tried again
-- with another target, up to opts.tries (3) times; res.tries says how many it took
function TK.hitTest(mode: string, speed: number, opts)
	opts = table.clone(opts or {})
	local tried = {}
	local res
	for i = 1, opts.tries or 3 do
		opts.excludeKeys = tried
		res = hitOnce(mode, speed, opts)
		res.tries = i
		if res.targetKey ~= nil then
			tried[res.targetKey] = true
		end
		if not res.abort or opts.target then
			return res
		end
		waitSeconds(1)
	end
	return res
end

-- the owner's table as staged hits (CollisionModel must be "arcade"; set it on the server first)
TK.HIT_MATRIX = {
	{"rear", 70}, {"rear", 100}, {"rear", 150}, {"rear", 200}, {"rear", 150, {offset = 2}},
	{"head", 100}, {"head", 150}, {"head", 200},
	{"side", 150, {angle = 5}}, {"side", 150, {angle = 20}}, {"side", 70, {angle = 25}}, {"side", 100, {angle = 10}},
}

-- one matrix run: PASS / FAIL per row (out = optional list the lines are appended to as they come). A failing row
-- (or every row with opts.verbose) is followed by its per-frame log. Returns pass, rows, and the rows' rates.
local function matrixRun(opts, cfg, label: string, out: {string}?)
	local rows, pass = {}, 0
	local hzs, renders = {}, {}
	for i, row in opts.rows or TK.HIT_MATRIX do
		local mode, speed, o = row[1], row[2], table.clone(row[3] or {})
		if o.isolate == nil then o.isolate = opts.isolate ~= false end
		o.around = opts.around -- targets are searched around the matrix's home spot, not where the last row ended
		local chassis = TK.car()
		if chassis then
			chassis.AssemblyLinearVelocity = Vector3.zero
			chassis.AssemblyAngularVelocity = Vector3.zero
		end
		local ok, res = pcall(TK.hitTest, mode, speed, o)
		local line
		local extra = nil
		if not ok then
			line = ("FAIL %s%2d %s @%d: error %s"):format(label, i, mode, speed, tostring(res))
		else
			table.insert(hzs, res.hz or 0)
			table.insert(renders, res.render or 0)
			local want = Rec.expectedStaged(mode, speed, o.angle, res.vT or 45, cfg)
			local problems = {}
			if not res.touched then table.insert(problems, "no staged hit (" .. res.reason .. ")") end
			if res.hitKey ~= nil and not res.keyMatch then
				table.insert(problems, ("the hit was car %s, not the target %s"):format(tostring(res.hitKey),
					tostring(res.targetKey)))
			end
			if res.touched and res.tier ~= want.tier then
				table.insert(problems, ("tier %s, table %s"):format(tostring(res.tier), want.tier))
			end
			local loss = 1 - (res.after or 0) / math.max(res.before or speed, 1)
			if res.touched and want.bounce == 0 and math.abs(loss - want.loss) > (opts.tol or 0.05) then
				table.insert(problems, ("loss %d%%, table %d%%"):format(math.floor(loss * 100 + 0.5),
					math.floor(want.loss * 100 + 0.5)))
			end
			if res.touched and want.bounce > 0 and (res.after or 0) > (res.before or speed) * 0.3 then
				table.insert(problems, ("head-on left %d of %d"):format(math.floor(res.after or 0), math.floor(res.before or 0)))
			end
			-- the PLAYER's speed at the touch (Recovery_LastHitBefore), never the closing speed
			if res.touched and (res.before or 0) < speed * 0.9 then
				table.insert(problems, ("impact speed %d of %d (lowest on the approach %s)"):format(
					math.floor(res.before or 0), speed, if res.approachMin then tostring(math.floor(res.approachMin)) else "-"))
			end
			if res.minUp < 0.85 then
				table.insert(problems, ("minUp %.2f at +%.2f s%s"):format(res.minUp, res.minUpAt or 0,
					if res.minUpWhere then " " .. res.minUpWhere else ""))
			end
			if (res.extraHits or 0) > 0 then
				table.insert(problems, ("%d more hit(s) after the staged one"):format(res.extraHits))
			end
			local good = #problems == 0
			if good then pass += 1 end
			line = ("%s %s%2d %s | table %s %d%%%s%s"):format(if good then "PASS" else "FAIL", label, i, res.text,
				want.tier, math.floor(want.loss * 100 + 0.5),
				if (res.tries or 1) > 1 then (" | tries %d"):format(res.tries) else "",
				if good then "" else " | " .. table.concat(problems, "; "))
			if not good or opts.verbose then extra = res.log end
		end
		print(line)
		table.insert(rows, line)
		if out then table.insert(out, line) end
		if extra then
			for _, l in extra do
				print(l)
				if out then table.insert(out, l) end
			end
		end
		if opts.onRow then opts.onRow(i, line, if ok then res else nil) end
		waitSeconds(opts.gap or 1.5)
	end
	return pass, rows, hzs, renders
end

local function spread(list: {number}): string
	if #list == 0 then return "-" end
	local lo, hi = math.huge, -math.huge
	for _, x in list do
		lo, hi = math.min(lo, x), math.max(hi, x)
	end
	if math.floor(lo + 0.5) == math.floor(hi + 0.5) then
		return tostring(math.floor(lo + 0.5))
	end
	return ("%d-%d"):format(math.floor(lo + 0.5), math.floor(hi + 0.5))
end

-- TK.hitMatrix(opts?, out?) -> summary, rows, perRun   runs TK.HIT_MATRIX (opts.rows to choose) opts.runs (1) times
-- and prints a PASS / FAIL line per row against the owner's table, a summary per run, per frame-rate level and
-- overall. opts.fps = 30 (or a list, {15, 30, 60}) runs it under TestKit's FPS cap at each level in turn (TK.fpsLimit;
-- removed at the end on every path, errors included; a 60 fps level needs the Studio window focused, and every
-- level prints the Heartbeat / render rates it really ran at). Rows are isolated (every other traffic car ghosts;
-- opts.isolate = false runs them in real traffic with retries). Targets are searched around where the car is when
-- the matrix starts (opts.around), so rows do not wander off. Each level starts with TK.selfCheck() and is skipped
-- if TestKit and PattayaTraffic disagree on the keys (opts.skipSelfCheck = true to run anyway).
-- A row passes when: the hit is the staged one (the key the hit event names = the target's, at the planned time);
-- the tier is the table's for the geometry and the target's real speed (PattayaRecovery.expectedStaged); the loss
-- is within opts.tol (0.05) (head-on: near stop); the player's speed at the hit is >= 90 % of the planned speed; no
-- tilt (minUp >= 0.85 over the 2 s watched); no second hit. opts.verbose prints every row's per-frame log (failing
-- rows always do). opts.onRow(i, line, res) is called after each row.
-- A full run takes about 5 s a row: from the Studio execute tool use TK.hitMatrixStart (below) and poll it.
function TK.hitMatrix(opts, out: {string}?)
	opts = table.clone(opts or {})
	assert(Rec, "hitMatrix: PattayaRecovery missing")
	assert(workspace:GetAttribute("CollisionModel") == "arcade", "hitMatrix: set CollisionModel = \"arcade\" on the server")
	local chassis = TK.car()
	assert(chassis, "hitMatrix: get in a car first")
	opts.around = opts.around or chassis.Position
	player:SetAttribute("TK_HitTarget", nil)
	local levels = {}
	if type(opts.fps) == "table" then
		for _, f in opts.fps do table.insert(levels, f) end
	elseif type(opts.fps) == "number" then
		levels = {opts.fps}
	else
		levels = {0} -- no cap: whatever this client runs at
	end
	local function emit(s: string, list: {string}?)
		print(s)
		if out then table.insert(out, s) end
		if list then table.insert(list, s) end
	end
	local cfg = Rec.config()
	local runs = opts.runs or 1
	local total = #(opts.rows or TK.HIT_MATRIX)
	local all, perRun, levelLines = {}, {}, {}
	local grand, grandTotal = 0, 0
	local okRun, err = pcall(function()
		for _, fps in levels do
			local flabel = if fps > 0 then ("%dfps "):format(fps) else ""
			TK.fpsLimit(if fps > 0 then fps else nil)
			waitSeconds(1.2) -- the rate settles and the counters measure it
			if not opts.skipSelfCheck then
				local ok, lines = TK.selfCheck(5)
				if out then for _, l in lines do table.insert(out, l) end end
				if not ok then
					emit(("hitMatrix @%s: not run - TK.selfCheck failed (TestKit and PattayaTraffic disagree; see the lines above)")
						:format(if fps > 0 then fps .. " fps" else "client rate"), levelLines)
					grandTotal += total * runs
					continue
				end
			end
			local lvlPass, hzs, renders = 0, {}, {}
			for r = 1, runs do
				local pass, rows, h, rd = matrixRun(opts, cfg, flabel .. (if runs > 1 then ("r%d "):format(r) else ""), out)
				for _, l in rows do table.insert(all, l) end
				for _, x in h do table.insert(hzs, x) end
				for _, x in rd do table.insert(renders, x) end
				lvlPass += pass
				emit(("hitMatrix %srun %d: %d/%d PASS (Heartbeat %s Hz, render %s fps%s)"):format(flabel, r, pass, total,
					spread(h), spread(rd), if opts.isolate == false then ", real traffic" else ", isolated"), perRun)
			end
			grand += lvlPass
			grandTotal += total * runs
			local rateNote = ""
			if fps > 0 then
				local lo = math.huge
				for _, x in hzs do lo = math.min(lo, x) end
				local rlo = math.huge
				for _, x in renders do rlo = math.min(rlo, x) end
				if lo < fps * 0.85 or rlo < fps * 0.85 then
					rateNote = (" - NOTE: ran at Heartbeat %s Hz / render %s fps, below the %d asked%s"):format(spread(hzs),
						spread(renders), fps, if fps >= 50 then " (focus the Studio window for the 60 fps level)" else "")
				end
			end
			emit(("hitMatrix @%s: %d/%d PASS over %d run%s (Heartbeat %s Hz, render %s fps)%s%s"):format(
				if fps > 0 then fps .. " fps" else "client rate", lvlPass, total * runs, runs, if runs > 1 then "s" else "",
				spread(hzs), spread(renders), if lvlPass == total * runs then " - REPEATABLE" else "", rateNote), levelLines)
		end
	end)
	TK.fpsLimit(nil)
	player:SetAttribute("TK_HitTarget", nil)
	if not okRun then
		error(err, 0)
	end
	local summary
	if #levels == 1 then
		summary = ("hitMatrix: %d/%d PASS over %d run%s%s%s"):format(grand, grandTotal, runs, if runs > 1 then "s" else "",
			if levels[1] > 0 then (" at %d fps"):format(levels[1]) else "",
			if grand == grandTotal and grandTotal > 0 then " - REPEATABLE" else "")
	else
		summary = ("hitMatrix: %d/%d PASS over %d frame-rate levels x %d run%s%s | %s"):format(grand, grandTotal, #levels,
			runs, if runs > 1 then "s" else "", if grand == grandTotal and grandTotal > 0 then " - REPEATABLE at every level" else "",
			table.concat(levelLines, " | "))
	end
	emit(summary)
	return summary, all, perRun
end

-- TK.cleanup(quiet?) -> string   undoes everything the hit and near-miss tests can leave behind: staged runs still in
-- progress (a stopped TK.hitMatrixStart: their connections are dropped and the car's collisions restored), the FPS
-- cap, the TK_HitTarget isolation hook and TrafficGhostAll (TK.ghostTraffic(false)). Says what it found and reminds
-- that CollisionModel = "arcade" is a test-only server setting (the saved place stays "physical").
function TK.cleanup(quiet: boolean?): string
	local found = {}
	local n = 0
	for list in activeRuns do
		n += 1
		runCleanup(list)
	end
	table.clear(activeRuns)
	if n > 0 then table.insert(found, ("%d staged run(s) stopped"):format(n)) end
	if TK.fpsLimitOn() then table.insert(found, ("FPS cap %s removed"):format(tostring(TK.fpsLimitOn()))) end
	TK.fpsLimit(nil)
	if player:GetAttribute("TK_HitTarget") ~= nil then table.insert(found, "TK_HitTarget cleared") end
	player:SetAttribute("TK_HitTarget", nil)
	if player:GetAttribute("TrafficGhostAll") == true or TK.trafficConn then
		TK.ghostTraffic(false)
		table.insert(found, "TrafficGhostAll cleared")
	end
	local cm = workspace:GetAttribute("CollisionModel")
	local s = ("cleanup: %s; CollisionModel = %s%s"):format(
		if #found > 0 then table.concat(found, ", ") else "nothing left over", tostring(cm),
		if cm == "arcade" then " (test only: set it back to \"physical\" on the server; the saved place stays physical)" else "")
	if not quiet then print(s) end
	return s
end

-- TK.hitMatrixStart(opts?) -> handle   the same matrix in the background, driven by a Heartbeat connection (it keeps
-- running after the Studio execute snippet returns), e.g. TK.hitMatrixStart({runs = 3, fps = {15, 30, 60}}).
-- handle:poll() -> "running 7 lines" / the summary; handle.lines (every line so far), handle.done, handle.summary,
-- handle:stop() (runs TK.cleanup). Also TK.handles.matrix.
function TK.hitMatrixStart(opts)
	local h = {lines = {}, done = false, summary = nil :: string?, error = nil :: string?}
	local co = coroutine.create(function()
		local ok, summary = pcall(TK.hitMatrix, opts, h.lines)
		h.summary = if ok then summary else nil
		h.error = if ok then nil else tostring(summary)
		h.done = true
	end)
	local conn
	conn = RunService.Heartbeat:Connect(function()
		if coroutine.status(co) ~= "suspended" then
			conn:Disconnect()
			h.done = true
			return
		end
		runnerCo = co
		local ok, err = coroutine.resume(co)
		runnerCo = nil
		if not ok then
			h.error, h.done = tostring(err), true
			conn:Disconnect()
			TK.cleanup(true)
		end
	end)
	function h:poll(): string
		if self.error then return "error: " .. self.error end
		if self.done then return self.summary or "done" end
		return ("running, %d lines: %s"):format(#self.lines, self.lines[#self.lines] or "-")
	end
	function h:stop(reason: string?)
		conn:Disconnect()
		self.done = true
		self.error = self.error or ("stopped" .. (if reason then " (" .. reason .. ")" else ""))
		TK.cleanup(true)
	end
	TK.handles.matrix = h
	return h
end

-- TK.nearMissTest(opts?) -> result   arcade on or off: my car overtakes a traffic car on its right at opts.speed (110)
-- with opts.gap (5) studs between the two sides (inside PattayaTraffic's 7-stud near-miss band), from opts.lead (60)
-- studs behind to 30 ahead (PattayaRecovery.stagePlan "pass", isolated like hitTest), then brakes. Expected: exactly
-- one near miss paid by the server (NearMissAt / NitroBonus) and no traffic hit during the pass; opts.gap = 9
-- (outside the band) or opts.speed = 65 with opts.lead = 20 (below 70) must pay none.
-- result = {ok, awards, nitro, hits (during the pass), hitsAfter (while braking), expected, text}.
function TK.nearMissTest(opts)
	opts = table.clone(opts or {})
	local speed, gap = opts.speed or 110, opts.gap or 5
	local chassis, model = TK.car()
	assert(chassis and model and Rec, "nearMissTest: get in a car first (and PattayaRecovery must be installed)")
	local expected = if gap > 0 and gap < Rec.NEAR_GAP and speed > Rec.NEAR_SPEED then 1 else 0
	local cleanup = {}
	activeRuns[cleanup] = true
	local ok, res = pcall(function()
		local cfg = Rec.config()
		waitUpright(cfg)
		opts.gap = gap
		local target = opts.target
		if not target then
			target = pickTarget("pass", speed, opts, 0.3)
		end
		assert(target, "nearMissTest: no traffic car on a straight nearby")
		player:SetAttribute("TK_HitTarget", target.key)
		table.insert(cleanup, function() player:SetAttribute("TK_HitTarget", nil) end)
		local approachT = workspace:GetServerTimeNow() + 0.3
		local probe = table.clone(target)
		probe.s, probe.t = target.s + target.speed * (approachT - target.t), approachT
		local plan = stage(probe, "pass", speed, opts)
		local awards, nitro = 0, 0
		local c1 = player:GetAttributeChangedSignal("NearMissAt"):Connect(function() awards += 1 end)
		table.insert(cleanup, function() c1:Disconnect() end)
		local nb = ReplicatedStorage:FindFirstChild("PattayaRemotes")
		nb = nb and nb:FindFirstChild("NitroBonus")
		if nb then
			local c2 = (nb :: RemoteEvent).OnClientEvent:Connect(function(amount)
				if type(amount) == "number" then nitro += amount end
			end)
			table.insert(cleanup, function() c2:Disconnect() end)
		end
		local hits0 = player:GetAttribute("Recovery_HitCount") or 0
		local hitsPass = 0
		local Y = 1 + 2.8
		local done = false
		local conn = onPreSim(function(stepDt: number)
			if done then return end
			local t = workspace:GetServerTimeNow()
			local tt = math.max(t, approachT)
			local x, z, dx, dz, left = plan(tt)
			local dir = Vector3.new(dx, 0, dz).Unit
			local p = Vector3.new(x, Y, z) - (if t < approachT then Vector3.zero
				else dir * (speed * math.clamp(stepDt or 0, 0, 0.1))) -- one physics step short (see hitBody)
			chassis.CFrame = CFrame.lookAt(p, p + dir)
			chassis.AssemblyLinearVelocity = if t < approachT then Vector3.zero else dir * speed
			chassis.AssemblyAngularVelocity = Vector3.zero
			if t >= approachT and (left <= 0 or t - approachT > (opts.timeout or 15)) then
				done = true
			end
		end)
		table.insert(cleanup, function() conn:Disconnect() end)
		while not done do waitFrame() end
		conn:Disconnect()
		hitsPass = (player:GetAttribute("Recovery_HitCount") or 0) - hits0
		-- brake gently and give the server's answer time to come back
		local t1 = os.clock()
		while os.clock() - t1 < 1.5 do
			waitFrame()
			local vv = chassis.AssemblyLinearVelocity
			local sp = flat(vv).Magnitude
			if sp > 0.5 then
				local k = math.max(sp - BRAKE / math.max(rates.hb, 15), 0) / sp
				chassis.AssemblyLinearVelocity = Vector3.new(vv.X * k, vv.Y, vv.Z * k)
			end
		end
		chassis.AssemblyLinearVelocity = Vector3.zero
		chassis.AssemblyAngularVelocity = Vector3.zero
		local hitsAfter = (player:GetAttribute("Recovery_HitCount") or 0) - hits0 - hitsPass
		local r = {awards = awards, nitro = nitro, hits = hitsPass, hitsAfter = hitsAfter, expected = expected,
			targetKey = target.key, speed = speed, gap = gap}
		r.ok = awards == expected and hitsPass == 0
		r.text = ("nearMissTest @%d gap %.1f on key %d [Heartbeat %.0f Hz, render %.0f fps]: %d near miss(es) paid (nitro %s), %d hit(s) during the pass%s; expected %d near miss, 0 hits - %s")
			:format(speed, gap, target.key, rates.hb, rates.render, awards, int(nitro), hitsPass,
			if hitsAfter > 0 then (" (%d while braking afterwards)"):format(hitsAfter) else "", expected,
			if r.ok then "PASS" else "FAIL")
		return r
	end)
	runCleanup(cleanup)
	activeRuns[cleanup] = nil
	if not ok then
		error(res, 0)
	end
	print(res.text)
	return res
end

-- Taxi / Delivery pay-out (PattayaJobsServer, read-only there; the same numbers): money = floor(fare * (1 - cut)) +
-- tip with cut = min(bumps * bumpCut, 0.6), tip = floor(max(0, timeLimit - time) * tipPerSec) + 5 per near miss.
TK.JOB_KINDS = {taxi = {bumpCut = 0.12, tipPerSec = 1.5}, delivery = {bumpCut = 0.15, tipPerSec = 2}}
TK.NEAR_TIP = 5
-- TK.jobPayout(start, finish, nearMisses) -> ok, text   start / finish = the JobUpdate "start" / "finish" payloads
function TK.jobPayout(start, finish, nearMisses: number?): (boolean, string)
	local k = TK.JOB_KINDS[start and start.kind]
	if not (k and finish) then
		return false, "jobPayout: need the JobUpdate start and finish payloads (taxi or delivery)"
	end
	local cut = math.min((finish.bumps or 0) * k.bumpCut, 0.6)
	local tip = math.floor(math.max(0, start.timeLimit - finish.time) * k.tipPerSec) + TK.NEAR_TIP * (nearMisses or 0)
	local money = math.floor(start.fare * (1 - cut)) + tip
	local ok = finish.money == money and finish.tip == tip
	return ok, ("jobPayout %s: fare %d, %d bump(s) (cut %d%%), %.1f s of %d, %d near miss(es): expected money %d (tip %d), paid %s (tip %s) - %s")
		:format(tostring(start.kind), start.fare, finish.bumps or 0, math.floor(cut * 100 + 0.5), finish.time,
		start.timeLimit, nearMisses or 0, money, tip, tostring(finish.money), tostring(finish.tip), if ok then "PASS" else "FAIL")
end

-- TK.jobWatch() -> watcher   the economy check with arcade on (in Play, test only): start a job, then drive (by hand,
-- or TK.hitTest; mind the job's 260 studs/s teleport check). It records the job's JobUpdate events, every arcade
-- hit CarController applies (with its tier), every hit report the server accepted (TrafficHits / TrafficHitTier),
-- and every near miss it paid (NearMissAt). watcher:report() -> text, ok: every accepted heavy / head-on hit gave
-- exactly one bump (within 1.5 s), no light / scrape hit gave one, no two bumps came within 1 s, and at "finish" the
-- pay-out matches TK.jobPayout. Bumps without an accepted hit (the speed-drop detector: kerbs, walls) are listed
-- apart. watcher:stop().
function TK.jobWatch()
	local w = {events = {}, start = nil :: any, finish = nil :: any, conns = {} :: {RBXScriptConnection}}
	local function now(): number return workspace:GetServerTimeNow() end
	local function add(kind: string, data)
		table.insert(w.events, {t = now(), kind = kind, data = data})
	end
	local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes")
	local ju = remotes and remotes:FindFirstChild("JobUpdate")
	if ju then
		table.insert(w.conns, (ju :: RemoteEvent).OnClientEvent:Connect(function(kind, data)
			if kind == "start" then
				w.start, w.finish = data, nil
				table.clear(w.events)
			elseif kind == "finish" then
				w.finish = data
			end
			add("job " .. tostring(kind), data)
		end))
	end
	table.insert(w.conns, player:GetAttributeChangedSignal("Recovery_HitCount"):Connect(function()
		add("hit", player:GetAttribute("Recovery_LastHitTier"))
	end))
	table.insert(w.conns, player:GetAttributeChangedSignal("TrafficHits"):Connect(function()
		add("accepted", player:GetAttribute("TrafficHitTier"))
	end))
	table.insert(w.conns, player:GetAttributeChangedSignal("NearMissAt"):Connect(function()
		add("near", nil)
	end))
	function w:stop()
		for _, c in self.conns do c:Disconnect() end
		table.clear(self.conns)
	end
	function w:report(): (string, boolean)
		local lines, ok = {}, true
		local bumps, accepted, near = {}, {}, 0
		for _, e in self.events do
			if e.kind == "job bump" then table.insert(bumps, e) end
			if e.kind == "accepted" then table.insert(accepted, e) end
			if e.kind == "near" then near += 1 end
		end
		local used = {}
		for _, a in accepted do
			local n = 0
			for i, b in bumps do
				if b.t >= a.t - 0.5 and b.t <= a.t + 1.5 then
					n += 1
					used[i] = true
				end
			end
			local want = if a.data == "heavy" or a.data == "headon" then 1 else 0
			if n ~= want then ok = false end
			table.insert(lines, ("accepted %s hit at %.2f: %d bump(s)%s"):format(tostring(a.data), a.t - (self.events[1] and self.events[1].t or a.t), n,
				if n == want then "" else (" - FAIL (expected %d)"):format(want)))
		end
		for _, e in self.events do
			if e.kind == "hit" and (e.data == "light" or e.data == "scrape") then
				for _, b in bumps do
					if b.t >= e.t - 0.2 and b.t <= e.t + 1.5 then
						local near2 = false
						for _, a in accepted do
							if math.abs(a.t - e.t) < 1.5 then near2 = true end
						end
						if not near2 then
							ok = false
							table.insert(lines, ("a %s hit was followed by a bump - FAIL"):format(e.data))
						end
					end
				end
			end
		end
		for i = 2, #bumps do
			if bumps[i].t - bumps[i - 1].t <= 1 then
				ok = false
				table.insert(lines, ("two bumps %.2f s apart - FAIL (one crash counted twice)"):format(bumps[i].t - bumps[i - 1].t))
			end
		end
		local other = 0
		for i in bumps do
			if not used[i] then other += 1 end
		end
		if other > 0 then
			table.insert(lines, ("%d bump(s) without an accepted traffic hit (the speed-drop detector: kerbs, walls, scenery)"):format(other))
		end
		if self.start and self.finish then
			local pok, ptext = TK.jobPayout(self.start, self.finish, near)
			if not pok then ok = false end
			table.insert(lines, ptext)
			if (self.finish.bumps or 0) ~= #bumps then
				ok = false
				table.insert(lines, ("finish says %d bump(s), %d bump events seen - FAIL"):format(self.finish.bumps or 0, #bumps))
			end
		else
			table.insert(lines, if self.start then "job running (no finish yet)" else "no job seen (start one after TK.jobWatch())")
		end
		local text = ("jobWatch: %d event(s), %d accepted hit(s), %d bump(s), %d near miss(es) - %s\n%s"):format(#self.events,
			#accepted, #bumps, near, if ok then "OK" else "FAIL", table.concat(lines, "\n"))
		print(text)
		return text, ok
	end
	TK.handles.jobWatch = w
	return w
end

function TK.stopAll()
	for _, h in TK.handles do
		if type(h) == "table" and h.stop then h:stop("stopAll") end
	end
	TK.cleanup() -- the isolation hook, the FPS cap, ghosting and staged runs never outlive a stop
end

-- frame counters for the report (render is throttled to ~15/s when Studio is not the focused window)
local frames = {hb = 0, render = 0, hbRate = 0, renderRate = 0, at = os.clock()}
RunService.Heartbeat:Connect(function()
	frames.hb += 1
	local now = os.clock()
	if now - frames.at >= 1 then
		frames.hbRate, frames.renderRate = frames.hb / (now - frames.at), frames.render / (now - frames.at)
		frames.hb, frames.render, frames.at = 0, 0, now
	end
end)
pcall(function()
	RunService.RenderStepped:Connect(function() frames.render += 1 end)
end)

local REPORT_ATTRS = {"RaceState", "RaceLap", "RaceNext", "RaceLastTime", "SprintActive", "JobActive", "CircuitActive",
	"CircuitMode", "CircuitState", "CircuitLap", "CircuitLastLap", "CircuitLapValid", "CircuitPenalty", "EventJoined",
	"EventActive", "Equalised", "SpeedCap", "RoadFight", "NearMissCombo", "Recovery_Uprights", "RescueActive",
	"Recovery_HitCount", "TrafficHits"}

function TK.report(): string
	local lines = {}
	local chassis, model = TK.car()
	if chassis and model then
		local p, v = chassis.Position, flat(chassis.AssemblyLinearVelocity).Magnitude
		table.insert(lines, ("car %s %s PI %s at (%.0f, %.1f, %.0f) v=%.0f up=%.2f%s"):format(model.Name,
			tostring(model:GetAttribute("Class") or "?"), tostring(model:GetAttribute("PI") or "?"), p.X, p.Y, p.Z, v,
			chassis.CFrame.UpVector.Y, if chassis.Anchored then " ANCHORED" else ""))
	else
		table.insert(lines, "car: not seated")
	end
	local ls = player:FindFirstChild("leaderstats")
	local attrs = {}
	if ls then
		for _, k in {"Level", "Money", "EXP", "Title"} do
			local x = ls:FindFirstChild(k)
			if x then table.insert(attrs, k .. "=" .. tostring((x :: any).Value)) end
		end
	end
	for _, k in REPORT_ATTRS do
		local x = player:GetAttribute(k)
		if x ~= nil and x ~= false then table.insert(attrs, k .. "=" .. brief(x, 1)) end
	end
	table.insert(lines, table.concat(attrs, " "))
	local lr = player:GetAttribute("LastReward")
	if lr then table.insert(lines, "LastReward: " .. tostring(lr)) end
	for _, h in TK.handles do
		if type(h) == "table" and h.poll then table.insert(lines, h:poll()) end
	end
	if recorder then
		local counts = {}
		for r, c in recorder.counts do table.insert(counts, r .. " " .. c) end
		table.sort(counts)
		table.insert(lines, "events: " .. table.concat(counts, ", "))
		table.insert(lines, recorder:dump(8, function(e)
			local k = e.kind
			return e.remote ~= "attr" and (k == "msg" or k == "toast" or k == "finish" or k == "stop" or k == "lap"
				or k == "warn" or k == "results" or k == "arrived" or k == "bump" or k == "invite")
		end))
	end
	table.insert(lines, ("fps heartbeat %.0f render %.0f"):format(frames.hbRate, frames.renderRate))
	return table.concat(lines, "\n")
end

return TK
