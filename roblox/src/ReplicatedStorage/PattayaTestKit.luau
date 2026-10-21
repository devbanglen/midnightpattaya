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
-- Taxi / Delivery economy, automated (team18/arcade-econ; offline only so far, see the block before TK.stopAll):
-- TK.jobDriveTestStart(opts?) -> handle      the whole test in the background: warp to a stand, request the job as
--   the E key does, drive the server's route (autopilot <= 100 studs/s on the route, staged runs <= the frame-rate
--   cap), stage a head-on (crash), a light rear-end, a scrape and a near miss on the way (hitMatrix isolation), stop
--   in the destination ring, check every bump and the pay-out. opts: kinds, runs (2), fps (15 / 30 / 60 or a list),
--   stands, heavy (a heavy rear-end too), verbose. handle:poll(), handle.lines, handle:stop(); TK.jobDrivePoll()
--   from any copy of this module. CollisionModel is "arcade" only while it runs (a server kit lease).
-- TK.jobDriveTest(opts?, out?) -> summary, runs   the same, blocking; TK.jobStands(kind?) -> the stands this client sees
-- TK.jobMath                                 its pure maths (Hermite lead-ins, curve checks, caps, event specs, bumps)
-- TK.startAgent() / TK.stopAgent()           the client half of the server kit's 2-player check (S.mpCheck): started
--   by PattayaTraffic's TestKit hook when the server sets workspace TK_ClientAgent = true (Studio / DevTest only)
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
	local function add(kind: string, data, key: number?)
		table.insert(w.events, {t = now(), kind = kind, data = data, key = key})
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
		add("hit", player:GetAttribute("Recovery_LastHitTier"), player:GetAttribute("Recovery_LastHitKey"))
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
		-- near misses count for the tip only while the job runs: up to its finish (0.3 s of replication slack)
		local finishT = nil
		for _, e in self.events do
			if e.kind == "job finish" then finishT = e.t end
		end
		for _, e in self.events do
			if e.kind == "job bump" then table.insert(bumps, e) end
			if e.kind == "accepted" then table.insert(accepted, e) end
			if e.kind == "near" and (finishT == nil or e.t <= finishT + 0.3) then near += 1 end
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

-- Taxi / Delivery economy, automated (team18/arcade-econ) -----------------------------------------------------------
-- Written and run offline only (tools/qa/tests/test_jobdrive.py drives it against the real PattayaJobsServer,
-- PattayaRecoveryServer and PattayaTestKitServer in a simulated client-server session); not yet run in Studio.
--
-- TK.jobDriveTestStart(opts) -> handle   the whole test in the background (one job takes 30-70 s): handle:poll(),
--   handle.lines (every line so far), handle.done, handle.summary, handle:stop() (cancels the job, runs TK.cleanup).
--   Also TK.handles.jobDrive, and TK.jobDrivePoll() (works from another copy of this module).
-- TK.jobDriveTest(opts, out?) -> summary, runs   the same, blocking (inside a runner, or a thread that may wait).
-- One run, no human input:
--   1. the server kit warps the car to a job stand of the kind BEFORE the job (the 260 studs/s check is not running
--      yet); the car stops in the ring and requests the job as the E key does (RequestJob);
--   2. an autopilot drives the route the server sent (JobUpdate "start"): CFrame mode, at most opts.cruise (100)
--      studs/s and the frame-rate cap (JM.capFor: 76 at 15 fps), braking at 70 studs/s2 (the speed-drop detector
--      needs 55 in 0.35 s). Every phase is a continuous curve (Hermite lead-ins and rejoins): never a position jump;
--   3. on the way it stages traffic hits with the hitMatrix isolation (TK_HitTarget, shared keys; between events
--      TK_HitTarget = 0 ghosts every car, so nothing else can hit the car or pay a near miss): a head-on (a heavy
--      rear-end when no oncoming car comes), a light rear-end, a scrape and a near miss, each on a traffic car whose
--      lane runs along the route (PattayaRecovery.stagePlan, the hitMatrix geometry; JM.passOncomingPlan for a near
--      miss past an oncoming car). At the touch the car is handed to CarController: the impact is its real arcade
--      response. Then a gentle stop (heavy / head-on) and a curve back onto the route;
--   4. it stops in the destination ring and the server finishes the job;
--   5. TK.jobWatch records the whole job. Checks: every applied heavy / head-on hit was accepted by the server and
--      gave exactly one bump; light / scrape hits gave none; no two bumps within 1 s; no bump without a hit (the
--      autopilot never trips the detector); each staged hit had the planned tier and the target's key; the near
--      miss was paid once; the pay-out = TK.jobPayout (fare cut + time tip + 5 per near miss); Money went up by it.
--      A run is PASS, FAIL, or INCOMPLETE (every check passed but an event found no traffic car along that route).
-- opts: kinds ({"taxi", "delivery"}), runs (2 per kind), fps (nil = the client rate; 15 / 30 / 60 or a list: the
--   TestKit FPS cap), stands (ids: a list, or {taxi = {...}, delivery = {...}}; default JM.STANDS: the stands with the
--   most traffic along their routes, offline analysis), cruise (100), heavy (false; true = a heavy rear-end is needed
--   as well), detour (30: studs from the route a staged run may use), keepProgress (true: Money / EXP / Level are set
--   back at the end), verbose (the per-run jobWatch report and the server speed probe).
-- Never changes saved state: CollisionModel is "arcade" only while the test runs (a server kit lease: given back at
-- the end, on any error or stop, and it expires by itself), the job of a failed run is cancelled, progress is set
-- back, and TK.cleanup leaves nothing over.
do
	local JM = {}
	TK.jobMath = JM -- the pure maths (tools/qa/tests/test_jobdrive.py)

	JM.Y = 1 + 2.8 -- staged runs: road + chassis ride height (as hitBody)
	JM.ACCEL, JM.BRAKE = 60, 70 -- autopilot, studs/s2 (braking well under the jobs detector's 55 in 0.35 s)
	JM.HIT_BRAKE = 60 -- the gentle stop after a heavy / head-on hit
	JM.MAX_DROP = 25 -- studs/s a planned curve may lose within 0.35 s
	JM.GROUPS = {crash = {"headon", "heavy"}, heavy = {"heavy"}, light = {"light"}, scrape = {"scrape"},
		near = {"nearOncoming", "near"}}
	JM.EVENTS = {"crash", "light", "scrape", "near"}
	JM.STANDS = {taxi = {"police_station", "central_festival", "terminal21", "walking_street"},
		delivery = {"night_plaza", "bua_khao", "naklua_fresh", "windy_plaza"}}

	-- the autopilot's top speed at a client frame rate. The server measures speed from positions every 0.1 s; at 15 fps
	-- a sample holds one client frame or two, so a steady v reads 0.57 v .. 1.33 v (a 0.76 v "drop" from aliasing
	-- alone; the detector wants 55): 76 keeps it near the limit only in a sequence that cannot come twice in a row.
	function JM.capFor(hz: number?): number
		local f = hz or 60
		if f <= 17 then
			return 76
		elseif f <= 24 then
			return 100
		elseif f <= 34 then
			return 110
		end
		return 120
	end

	-- cubic Hermite in time: from (x0, z0) moving at (vx0, vz0) to (x1, z1) moving at (vx1, vz1) T seconds later.
	-- f(u) -> x, z, vx, vz for u = seconds since the start (clamped to [0, T]). Position and velocity are continuous at
	-- both ends, so a lead-in or a rejoin never jumps.
	function JM.hermite(x0: number, z0: number, vx0: number, vz0: number, x1: number, z1: number, vx1: number,
		vz1: number, T: number)
		return function(u: number): (number, number, number, number)
			local s = math.clamp(u / T, 0, 1)
			local s2, s3 = s * s, s * s * s
			local h00, h10, h01, h11 = 2 * s3 - 3 * s2 + 1, s3 - 2 * s2 + s, -2 * s3 + 3 * s2, s3 - s2
			local d00, d10, d01, d11 = 6 * s2 - 6 * s, 3 * s2 - 4 * s + 1, -6 * s2 + 6 * s, 3 * s2 - 2 * s
			local x = h00 * x0 + h10 * T * vx0 + h01 * x1 + h11 * T * vx1
			local z = h00 * z0 + h10 * T * vz0 + h01 * z1 + h11 * T * vz1
			local vx = (d00 * x0 + d10 * T * vx0 + d01 * x1 + d11 * T * vx1) / T
			local vz = (d00 * z0 + d10 * T * vz0 + d01 * z1 + d11 * T * vz1) / T
			return x, z, vx, vz
		end
	end

	-- a curve f over T seconds: top speed, the lowest velocity along (cx, cz) (< 0 = it would turn back), the largest
	-- acceleration, and the largest speed loss within the jobs detector's 0.35 s window
	function JM.curveStats(f, T: number, cx: number, cz: number)
		local n = math.max(8, math.ceil(T / 0.05))
		local dt = T / n
		local maxV, minAlong, maxA, maxDrop = 0, math.huge, 0, 0
		local speeds = table.create(n + 1)
		local pvx, pvz = nil, nil
		for i = 0, n do
			local _, _, vx, vz = f(i * dt)
			local sp = math.sqrt(vx * vx + vz * vz)
			speeds[i + 1] = sp
			maxV = math.max(maxV, sp)
			minAlong = math.min(minAlong, vx * cx + vz * cz)
			if pvx then
				maxA = math.max(maxA, math.sqrt((vx - pvx) ^ 2 + (vz - (pvz :: number)) ^ 2) / dt)
			end
			pvx, pvz = vx, vz
		end
		local w = math.max(1, math.floor(0.35 / dt + 0.5))
		for i = 1, #speeds do
			local peak = 0
			for j = math.max(1, i - w), i do
				peak = math.max(peak, speeds[j])
			end
			maxDrop = math.max(maxDrop, peak - speeds[i])
		end
		return {maxV = maxV, minAlong = minAlong, maxA = maxA, maxDrop = maxDrop}
	end

	-- the staged event a traffic car of speed vT allows with the autopilot capped at `cap`: {name, mode, speed,
	-- angle, gap, approach (s from the run's start to the touch / level), want (tier, or "near")}, or nil. Hits are
	-- checked against the owner's table (PattayaRecovery.expectedStaged) with margin: head-on vc >= 110, heavy
	-- rear-end vc 60, light vc 20-30, scrape at 7 degrees (vc ~9), near misses at NEAR_SPEED + 5 or more.
	function JM.eventSpec(name: string, vT: number, cap: number, cfg): {[string]: any}?
		local spec
		if name == "headon" then
			spec = {mode = "head", speed = math.min(cap, math.max(70, 115 - vT)), approach = 1.0, want = "headon"}
		elseif name == "heavy" then
			spec = {mode = "rear", speed = vT + 60, approach = 1.2, want = "heavy"}
		elseif name == "light" then
			spec = {mode = "rear", speed = vT + math.clamp(cap - vT, 0, 30), approach = 1.4, want = "light"}
		elseif name == "scrape" then
			spec = {mode = "side", speed = math.min(cap, 80), angle = 7, want = "scrape"}
		elseif name == "near" then
			spec = {mode = "pass", speed = math.min(cap, math.max(Rec.NEAR_SPEED + 8, vT + 30)), gap = 5, approach = 1.2,
				want = "near"}
		elseif name == "nearOncoming" then
			spec = {mode = "passOncoming", speed = math.min(cap, 85), gap = 5, approach = 0.9, want = "near"}
		else
			return nil
		end
		if spec.speed > cap + 1e-6 then
			return nil
		end
		if spec.mode == "rear" and spec.speed - vT < (if name == "light" then 20 else 55) then
			return nil
		end
		if spec.mode == "side" and spec.speed * math.cos(math.rad(spec.angle)) < vT + 15 then
			return nil
		end
		if spec.want == "near" then
			if spec.speed < Rec.NEAR_SPEED + 5 or (spec.mode == "pass" and spec.speed < vT + 20) then
				return nil
			end
		else
			local res = Rec.expectedStaged(spec.mode, spec.speed, spec.angle, vT, cfg)
			if res.tier ~= spec.want then
				return nil
			end
			spec.loss = res.loss
		end
		spec.name = name
		return spec
	end

	-- near miss past an ONCOMING traffic car (its lane runs against mine): my car drives the other way along its
	-- route, gap studs off its right side (the road-centre side), from `lead` studs ahead of it to 30 studs behind it.
	-- p = {route, s0, t0, vT, halfWid, halfLen, speed, lead, gap}. Same interface as PattayaRecovery.stagePlan's
	-- "pass": plan(t) -> x, z, dirX, dirZ, studs left to drive; the level time; the arc span both cars use; and the
	-- span around the target while level (positions and directions from PattayaRecovery's shared route maths).
	function JM.passOncomingPlan(p)
		local r, s0, t0, vT, speed = p.route, p.s0, p.t0, p.vT, p.speed
		local lead = p.lead or 100
		local lat = p.halfWid + Rec.CAR_HALF_WID + (p.gap or 5)
		local past = p.halfLen + Rec.CAR_HALF_LEN + 30
		local closing = math.max(speed + vT, 1e-3)
		local level = t0 + lead / closing
		local tEnd = t0 + (lead + past) / closing
		local plan = function(t: number)
			local sc = s0 + lead - speed * (t - t0)
			local x, z = Rec.routePoint(r, sc)
			local tx, tz = Rec.routeTangent(r, sc)
			return x - tz * lat, z + tx * lat, -tx, -tz, sc - (s0 + vT * (t - t0) - past)
		end
		local sEnd = s0 + lead - speed * (tEnd - t0)
		local sT = s0 + vT * (level - t0)
		return plan, level, {sEnd - Rec.CAR_HALF_LEN - 10, s0 + lead + Rec.CAR_HALF_LEN + 10},
			{sT - p.halfLen - 6, sT + p.halfLen + 6}
	end

	-- The bookkeeping of one job from TK.jobWatch's events ({t, kind, data, key}) as plain data, the owner's rules:
	-- every applied heavy / head-on hit was accepted by the server (opts.requireAccepted, default on) and every accepted
	-- hit gave exactly one bump (from 0.5 s before to 1.5 s after it); a light / scrape hit gave no bump; no two bumps
	-- within 1 s; a bump without an accepted hit ("stray": the speed-drop detector: kerbs, walls, or a bad autopilot)
	-- fails with opts.noStray. Near misses count from the job's start to its finish (+0.3 s). Returns
	-- {ok, lines, accepted, bumps, hits, heavy, unaccepted, light, lightBumped, doubles, stray, near, perAccepted}.
	function JM.matchBumps(events, opts)
		opts = opts or {}
		local lines, ok = {}, true
		local hits, accepted, bumps = {}, {}, {}
		local t0, tf = nil, nil
		for _, e in events do
			if e.kind == "job start" then
				t0 = t0 or e.t
			elseif e.kind == "job finish" then
				tf = e.t
			elseif e.kind == "hit" then
				table.insert(hits, e)
			elseif e.kind == "accepted" then
				table.insert(accepted, e)
			elseif e.kind == "job bump" then
				table.insert(bumps, e)
			end
		end
		local ref = t0 or (events[1] and events[1].t) or 0
		local near = 0
		for _, e in events do
			if e.kind == "near" and (t0 == nil or e.t >= t0 - 0.05) and (tf == nil or e.t <= tf + 0.3) then
				near += 1
			end
		end
		local res = {accepted = #accepted, bumps = #bumps, hits = #hits, near = near, heavy = 0, unaccepted = 0,
			light = 0, lightBumped = 0, doubles = 0, stray = 0, perAccepted = {}}
		local used = {}
		for _, a in accepted do
			local n = 0
			for i, b in bumps do
				if b.t >= a.t - 0.5 and b.t <= a.t + 1.5 then
					n += 1
					used[i] = true
				end
			end
			table.insert(res.perAccepted, n)
			if n ~= 1 then
				ok = false
				table.insert(lines, ("accepted %s hit at %+.2f s: %d bump(s), expected 1 - FAIL"):format(tostring(a.data),
					a.t - ref, n))
			end
		end
		for _, h in hits do
			if h.data == "heavy" or h.data == "headon" then
				res.heavy += 1
				local found = false
				for _, a in accepted do
					if a.t >= h.t - 0.3 and a.t <= h.t + 1.0 then
						found = true
					end
				end
				if not found then
					res.unaccepted += 1
					if opts.requireAccepted ~= false then
						ok = false
						table.insert(lines, ("%s hit at %+.2f s (key %s) was not accepted by the server (TrafficHits) - FAIL")
							:format(tostring(h.data), h.t - ref, tostring(h.key)))
					end
				end
			elseif h.data == "light" or h.data == "scrape" then
				res.light += 1
				for i, b in bumps do
					if b.t >= h.t - 0.2 and b.t <= h.t + 1.5 and not used[i] then
						ok = false
						res.lightBumped += 1
						table.insert(lines, ("%s hit at %+.2f s (key %s) was followed by a bump - FAIL"):format(h.data,
							h.t - ref, tostring(h.key)))
					end
				end
			end
		end
		for i = 2, #bumps do
			if bumps[i].t - bumps[i - 1].t <= 1 then
				ok = false
				res.doubles += 1
				table.insert(lines, ("two bumps %.2f s apart - FAIL (one crash counted twice)"):format(bumps[i].t - bumps[i - 1].t))
			end
		end
		for i in bumps do
			if not used[i] then
				res.stray += 1
			end
		end
		if res.stray > 0 then
			if opts.noStray then
				ok = false
			end
			table.insert(lines, ("%d bump(s) without an accepted traffic hit (the speed-drop detector)%s"):format(res.stray,
				if opts.noStray then " - FAIL (the autopilot must never trip it)" else ""))
		end
		res.ok, res.lines = ok, lines
		return res
	end

	-- the job stands this client knows (JobStands models are Persistent): {id, kind, label, pos (ring centre), road}
	local function standList(kind: string?)
		local world = workspace:FindFirstChild("PattayaWorld")
		local folder = world and world:FindFirstChild("JobStands")
		local out = {}
		if folder then
			for _, m in folder:GetChildren() do
				local ring = m:FindFirstChild("Ring")
				if ring and ring:IsA("BasePart") and (kind == nil or m:GetAttribute("Kind") == kind) then
					local pole = m:FindFirstChild("Pole")
					local road = nil
					if pole and pole:IsA("BasePart") then
						local k = flat(pole.Position - ring.Position)
						road = if k.Magnitude > 0.1 then Vector3.new(-k.Z, 0, k.X).Unit else nil
					end
					table.insert(out, {id = m.Name, kind = m:GetAttribute("Kind"), label = m:GetAttribute("Label"),
						pos = ring.Position, road = road})
				end
			end
		end
		return out
	end
	TK.jobStands = standList

	-- A server kit call that is safe inside a background runner: the runner is a coroutine resumed from Heartbeat, so it
	-- must never yield to the engine itself (InvokeServer would be resumed early); the call runs in its own thread and
	-- the runner waits frames for it. Elsewhere it is a plain TK.server call.
	local function serverCall(timeout: number, action: string, ...)
		local args = table.pack(...)
		if not (runnerCo ~= nil and coroutine.running() == runnerCo) then
			return TK.server(action, table.unpack(args, 1, args.n))
		end
		local box = {done = false, res = nil :: any}
		task.spawn(function()
			box.res = table.pack(pcall(TK.server, action, table.unpack(args, 1, args.n)))
			box.done = true
		end)
		local t0 = os.clock()
		while not box.done do
			if os.clock() - t0 > timeout then
				error(("server kit call %s did not return within %d s"):format(action, timeout), 0)
			end
			waitFrame()
		end
		if not box.res[1] then
			error(box.res[2], 0)
		end
		return table.unpack(box.res, 2, box.res.n)
	end
	-- fire and forget (cleanup paths: they must not wait)
	local function serverSend(action: string, ...)
		local args = table.pack(...)
		task.spawn(function()
			pcall(TK.server, action, table.unpack(args, 1, args.n))
		end)
	end

	-- the job route as an autopilot path: resampled every 4 studs, corner speeds (bot grip 150), the cruise cap, a stop
	-- at the destination at JM.BRAKE, and the nominal time to go from every point
	local function buildPath(route, cruise: number, from: Vector3?)
		local src = {}
		if from and flat(from - route[1]).Magnitude > 1 then
			table.insert(src, Vector3.new(from.X, route[1].Y, from.Z)) -- join where the car stands
		end
		for i = 1, #route do
			local p = route[i]
			if #src == 0 or flat(p - src[#src]).Magnitude > 0.05 then
				table.insert(src, p)
			end
		end
		assert(#src >= 2, "jobDriveTest: the job route has fewer than 2 points")
		local pts, _, cum = resample(src, nil)
		local prof = profile(pts, {}, 150, JM.BRAKE)
		for i = 1, #prof do
			prof[i] = math.min(prof[i], cruise)
		end
		prof[#prof] = 0
		for i = #pts - 1, 1, -1 do
			prof[i] = math.min(prof[i], math.sqrt(prof[i + 1] ^ 2 + 2 * JM.BRAKE * (cum[i + 1] - cum[i])))
		end
		local tGo = table.create(#pts, 0)
		for i = #pts - 1, 1, -1 do
			tGo[i] = tGo[i + 1] + (cum[i + 1] - cum[i]) / math.max((prof[i] + prof[i + 1]) / 2, 6)
		end
		return {pts = pts, cum = cum, prof = prof, tGo = tGo, total = cum[#cum], hintIdx = 1}
	end

	local function pathIndex(path, s: number): number
		local cum = path.cum
		local lo, hi = 1, #cum
		if s <= 0 then
			return 1
		elseif s >= cum[hi] then
			return math.max(1, hi - 1)
		end
		while hi - lo > 1 do
			local mid = (lo + hi) // 2
			if cum[mid] <= s then lo = mid else hi = mid end
		end
		return lo
	end
	-- x, z and the unit direction of the path at arc s
	local function pathPoint(path, s: number): (number, number, number, number)
		local i = pathIndex(path, s)
		local pts, cum = path.pts, path.cum
		local j = math.min(i + 1, #pts)
		local seg = cum[j] - cum[i]
		local f = if seg > 1e-6 then math.clamp((s - cum[i]) / seg, 0, 1) else 0
		local a, b = pts[i], pts[j]
		local dx, dz = b.X - a.X, b.Z - a.Z
		local m = math.sqrt(dx * dx + dz * dz)
		if m < 1e-6 then
			dx, dz, m = 0, -1, 1
		end
		return a.X + (b.X - a.X) * f, a.Z + (b.Z - a.Z) * f, dx / m, dz / m
	end
	-- speed limit and nominal time to go at arc s (interpolated; 0 at the end)
	local function profAt(path, s: number): number
		if s >= path.total - 1e-3 then
			return 0
		end
		local i = pathIndex(path, s)
		local seg = path.cum[i + 1] - path.cum[i]
		local f = if seg > 1e-6 then math.clamp((s - path.cum[i]) / seg, 0, 1) else 0
		return path.prof[i] + (path.prof[i + 1] - path.prof[i]) * f
	end
	local function timeToGo(path, s: number): number
		local i = pathIndex(path, s)
		local seg = path.cum[i + 1] - path.cum[i]
		local f = if seg > 1e-6 then math.clamp((s - path.cum[i]) / seg, 0, 1) else 0
		return path.tGo[i] + (path.tGo[i + 1] - path.tGo[i]) * f
	end
	-- the point of the path nearest (x, z) among arcs [s0, s0 + span]: arc, distance
	local function pathProject(path, x: number, z: number, s0: number, span: number): (number?, number)
		local pts, cum = path.pts, path.cum
		local i = pathIndex(path, math.max(s0, 0))
		local best, bestS = math.huge, nil
		while i < #pts and cum[i] <= s0 + span do
			local a, b = pts[i], pts[i + 1]
			local abx, abz = b.X - a.X, b.Z - a.Z
			local l2 = abx * abx + abz * abz
			local t = if l2 > 1e-9 then math.clamp(((x - a.X) * abx + (z - a.Z) * abz) / l2, 0, 1) else 0
			local d = math.sqrt((x - a.X - abx * t) ^ 2 + (z - a.Z - abz * t) ^ 2)
			if d < best then
				best, bestS = d, cum[i] + t * (cum[i + 1] - cum[i])
			end
			i += 1
		end
		return bestS, best
	end
	JM.buildPath, JM.pathPoint, JM.pathProject, JM.profAt, JM.timeToGo = buildPath, pathPoint, pathProject, profAt, timeToGo

	-- where the autopilot will be over the next `horizon` s if it just keeps driving the route: {t, x, z}
	local function nominalAhead(path, s: number, v: number, cruise: number, horizon: number)
		local out = {}
		local t = 0
		while t <= horizon + 1e-6 do
			local x, z = pathPoint(path, s)
			table.insert(out, {t = t, x = x, z = z})
			for _ = 1, 5 do
				local vw = math.min(cruise, profAt(path, s))
				v = if vw > v then math.min(vw, v + JM.ACCEL * 0.05) else math.max(vw, v - JM.BRAKE * 0.05)
				s = math.min(path.total, s + v * 0.05)
			end
			t += 0.25
		end
		return out
	end

	-- the driver: ONE PreSimulation connection places the car every physics step for the whole job.
	-- Modes: "hold" (still), "route" (the job route), "curve" (a Hermite lead-in to a staged run, or a rejoin onto the
	-- route), "stage" (the staged run itself, hitBody's placement: exactly on the plan at Heartbeat), "free" (no
	-- placement: CarController's arcade hit response). Every placed frame puts the car one physics step short of where
	-- it must be at Heartbeat (as hitBody), with that velocity, so at Heartbeat it is exactly on the curve.
	local Driver = {}
	Driver.__index = Driver

	local function newDriver(chassis: BasePart, model: Model, cap: number)
		local p = chassis.Position
		local l = flat(chassis.CFrame.LookVector)
		local D = setmetatable({chassis = chassis, model = model, mode = "hold", path = nil :: any, s = 0, v = 0,
			cruise = cap, cap = cap, lastPos = p, lastVel = Vector3.zero, lastT = workspace:GetServerTimeNow(),
			look = if l.Magnitude > 0.1 then l.Unit else Vector3.new(0, 0, -1), ride = 2.8, y = p.Y,
			colliders = carColliders(model), saved = {}, collOff = false, st = nil :: any, curve = nil :: any,
			arrived = false, lost = false, dead = false, maxSpeed = 0, params = RaycastParams.new()}, Driver)
		for _, part in D.colliders do
			D.saved[part] = part.CanCollide
		end
		D.params.FilterType = Enum.RaycastFilterType.Exclude
		D.conn = onPreSim(function(stepDt: number)
			D:step(stepDt)
		end)
		return D
	end

	-- the car's Y over the ground at (x, z) (ride height kept), nil when nothing is below
	function Driver:groundY(x: number, z: number, fromY: number): number?
		self.params.FilterDescendantsInstances = excludeList(self.model)
		local hit = workspace:Raycast(Vector3.new(x, fromY + 12, z), Vector3.new(0, -60, 0), self.params)
		if hit and not carModelOf(hit.Instance) then
			return hit.Position.Y + self.ride
		end
		return nil
	end

	function Driver:noCollide()
		for _, part in self.colliders do
			if part.Parent and part.CanCollide then
				part.CanCollide = false
			end
		end
		self.collOff = true
	end

	-- collisions back as they were (the end of a run: D:stop)
	function Driver:restoreCollisions()
		if not self.collOff then
			return
		end
		for part, c in self.saved do
			if part.Parent then
				part.CanCollide = c
			end
		end
		self.collOff = false
	end

	function Driver:place(x: number, y: number, z: number, vx: number, vz: number, lx: number, lz: number, dt: number,
		t: number)
		local p = Vector3.new(x - vx * dt, y, z - vz * dt)
		local look = Vector3.new(lx, 0, lz)
		look = if look.Magnitude > 1e-3 then look.Unit else self.look
		self.chassis.CFrame = CFrame.lookAt(p, p + look)
		self.chassis.AssemblyLinearVelocity = Vector3.new(vx, 0, vz)
		self.chassis.AssemblyAngularVelocity = Vector3.zero
		self.lastPos, self.lastVel, self.lastT, self.look = Vector3.new(x, y, z), Vector3.new(vx, 0, vz), t, look
		self.maxSpeed = math.max(self.maxSpeed, math.sqrt(vx * vx + vz * vz))
	end

	-- the look turns towards the velocity at most 4 rad/s
	function Driver:turnTowards(vx: number, vz: number, dt: number): (number, number)
		local cur = self.look
		local sp = math.sqrt(vx * vx + vz * vz)
		if sp < 2 then
			return cur.X, cur.Z
		end
		local wx, wz = vx / sp, vz / sp
		local ang = math.atan2(cur.X * wz - cur.Z * wx, cur.X * wx + cur.Z * wz)
		local maxStep = 4 * dt
		if math.abs(ang) <= maxStep then
			return wx, wz
		end
		local a = if ang > 0 then maxStep else -maxStep
		local c, s = math.cos(a), math.sin(a)
		return cur.X * c - cur.Z * s, cur.X * s + cur.Z * c
	end

	-- straight on at the last velocity (a staged run that ended, until the runner hands over to a rejoin)
	function Driver:coast(t: number, dt: number)
		local v = self.lastVel
		local u = t - self.lastT
		local p = self.lastPos + v * u
		self:place(p.X, self.lastPos.Y, p.Z, v.X, v.Z, self.look.X, self.look.Z, dt, t)
	end

	function Driver:routeStep(t: number, dt: number)
		local path = self.path
		local vWant = math.min(self.cruise, profAt(path, self.s))
		if vWant > self.v then
			self.v = math.min(vWant, self.v + JM.ACCEL * dt)
		else
			self.v = math.max(vWant, self.v - JM.BRAKE * dt)
		end
		self.s = math.min(path.total, self.s + self.v * dt)
		local p, dir = at(path, self.s)
		local p2 = at(path, math.min(path.total, self.s + 6))
		local d = flat(p2 - p)
		if d.Magnitude > 0.1 then
			dir = d.Unit
		end
		local y = self:groundY(p.X, p.Z, self.y) or self.y
		self.y = y
		self:place(p.X, y, p.Z, dir.X * self.v, dir.Z * self.v, dir.X, dir.Z, dt, t)
		if self.s >= path.total - 0.05 and self.v < 0.5 then
			self.arrived = true
		end
	end

	function Driver:curveStep(t: number, dt: number)
		local c = self.curve
		local u = t - c.tA
		if c.kind == "leadin" then
			local st = self.st
			local count = player:GetAttribute("Recovery_HitCount") or 0
			if st.hitsBefore ~= nil and count ~= st.hitsBefore then
				-- a hit before the staged run began: not the staged one (the target is the only real car)
				st.snap, st.handOff, st.done, st.reason = snapshotHit(), t, true, "hit during the lead-in"
				self.mode = "free"
				return
			end
			st.hitsBefore = count
			st.touchesBefore = player:GetAttribute("Traffic_Touches") or 0
			if t >= c.tEnd then
				self.mode = "stage"
				self:stageStep(t, dt)
				return
			end
		elseif u >= c.T then
			-- back on the route: continue from where the curve ends, at its end speed
			self.mode = "route"
			self.s, self.v = math.max(c.sJ + c.vJ * (u - c.T) - c.vJ * dt, 0), c.vJ
			self.path.hintIdx = pathIndex(self.path, self.s)
			self.y = c.y1
			self:routeStep(t, dt)
			return
		end
		local x, z, vx, vz = c.f(u)
		local k = math.clamp(u / c.T, 0, 1)
		local y = c.y0 + (c.y1 - c.y0) * (k * k * (3 - 2 * k))
		local lx, lz = self:turnTowards(vx, vz, dt)
		self:place(x, y, z, vx, vz, lx, lz, dt, t)
	end

	-- the staged run: hitBody's per-step logic, from a flying start (the lead-in ends exactly on the plan, moving at its
	-- speed). The hit is counted by CarController (Recovery_HitCount); from that frame on the car is not placed again.
	function Driver:stageStep(t: number, dt: number)
		local st = self.st
		if st.done then
			self:coast(t, dt)
			return
		end
		local count = player:GetAttribute("Recovery_HitCount") or 0
		if not st.started then
			st.started = true
			st.startClock = os.clock()
			-- the target must have a real model under its key (the isolation hook ghosts every OTHER car)
			local m = trafficModels()[st.key]
			local why = if not m then "no model under its key" elseif ghosted(m) then "its model is ghosted" else nil
			if why then
				st.done, st.reason, st.abort = true, "target check: " .. why, "target"
				self:coast(t, dt)
				return
			end
		end
		st.frames += 1
		if st.hitsBefore and count ~= st.hitsBefore then
			local snap = snapshotHit()
			st.snap, st.handOff, st.done = snap, t, true
			if st.pass then
				st.reason = "hit during the pass"
			else
				local ok, why = Rec.acceptStagedHit({hitT = if type(snap.t) == "number" then snap.t else t,
					approachT = st.approachT, meet = st.meet, frameDt = 1 / math.max(rates.hb, 1), hitKey = snap.key,
					targetKey = st.key})
				st.reason = if ok then "hit" else "rejected: " .. tostring(why)
			end
			self.mode = "free"
			return
		end
		local touches = player:GetAttribute("Traffic_Touches") or 0
		if st.touchesBefore and touches ~= st.touchesBefore and not st.touch then
			st.touch = {t = t, key = player:GetAttribute("Traffic_TouchKey")}
		end
		local x, z, dx, dz, gap = st.plan(t)
		if st.pass then
			if gap <= 0 or t - st.approachT > 15 then
				st.done, st.reason = true, "passed"
			end
		elseif st.prevGap and st.prevGap < -4 then
			st.done, st.reason = true, "no hit registered (overlapping)"
		elseif t > st.meet + 2 or t - st.approachT > 10 then
			st.done, st.reason = true, "timeout"
		end
		local dir = Vector3.new(dx, 0, dz).Unit
		st.dir, st.prevGap = dir, gap
		self:place(x, JM.Y, z, dir.X * st.speed, dir.Z * st.speed, dir.X, dir.Z, dt, t)
	end

	function Driver:step(stepDt: number)
		if self.dead then
			return
		end
		local chassis = self.chassis
		if not chassis.Parent or TK.car() ~= chassis then
			self.lost = true
			return
		end
		if chassis.Anchored then
			return
		end
		-- the car ignores scenery for the whole job (re-applied every step: the Humanoid may switch body parts back),
		-- also while CarController moves it after a hit ("free"); D:stop() gives the collisions back
		self:noCollide()
		if self.mode == "free" then
			return
		end
		local t = workspace:GetServerTimeNow()
		local dt = math.clamp(stepDt or 1 / 60, 1 / 240, 0.1)
		if self.mode == "hold" then
			local p = self.lastPos
			self:place(p.X, p.Y, p.Z, 0, 0, self.look.X, self.look.Z, dt, t)
		elseif self.mode == "route" then
			self:routeStep(t, dt)
		elseif self.mode == "curve" then
			self:curveStep(t, dt)
		elseif self.mode == "stage" then
			self:stageStep(t, dt)
		end
	end

	-- back onto the route: a Hermite from where the car is (and its velocity) to a point L studs further along the
	-- route than both its projection and sFloor, arriving at the route's speed there
	function Driver:startRejoin(sFloor: number, fromRest: boolean?)
		local path = self.path
		local chassis = self.chassis
		local pos, vel, t
		if self.mode == "free" then
			pos = chassis.Position
			local v = chassis.AssemblyLinearVelocity
			vel = Vector3.new(v.X, 0, v.Z)
			t = workspace:GetServerTimeNow()
			local l = flat(chassis.CFrame.LookVector)
			if l.Magnitude > 0.1 then
				self.look = l.Unit
			end
		else
			pos, vel, t = self.lastPos, self.lastVel, self.lastT
		end
		if fromRest and vel.Magnitude < 16 then
			vel = Vector3.zero
		end
		local sp = vel.Magnitude
		local sP = pathProject(path, pos.X, pos.Z, math.max(sFloor - 60, 0), 800) or sFloor
		local sJ = math.min(path.total, math.max(sP, sFloor) + math.clamp(25 + 1.2 * sp, 30, 120))
		local jx, jz, tx, tz = pathPoint(path, sJ)
		local vJ = if sJ >= path.total - 0.5 then 0 else math.min(self.cruise, profAt(path, sJ), math.max(sp + 40, 35))
		local dist = math.sqrt((jx - pos.X) ^ 2 + (jz - pos.Z) ^ 2)
		local cx, cz = if dist > 1e-3 then (jx - pos.X) / dist else tx, if dist > 1e-3 then (jz - pos.Z) / dist else tz
		local T = math.clamp(2 * dist / math.max(sp + vJ, 10), 0.8, 6)
		local f = JM.hermite(pos.X, pos.Z, vel.X, vel.Z, jx, jz, tx * vJ, tz * vJ, T)
		for _ = 1, 6 do
			local s = JM.curveStats(f, T, cx, cz)
			if s.maxV <= self.cap + 5 and s.maxDrop <= JM.MAX_DROP then
				break
			end
			T *= 1.3
			f = JM.hermite(pos.X, pos.Z, vel.X, vel.Z, jx, jz, tx * vJ, tz * vJ, T)
		end
		local y1 = self:groundY(jx, jz, pos.Y) or (1 + self.ride)
		self.curve = {kind = "rejoin", f = f, tA = t, T = T, sJ = sJ, vJ = vJ, y0 = pos.Y, y1 = y1}
		self.arrived = false
		self.mode = "curve"
	end

	function Driver:stop()
		if self.dead then
			return
		end
		self.dead = true
		if self.conn then
			self.conn:Disconnect()
		end
		local c = self.chassis
		if c.Parent and not c.Anchored then
			c.AssemblyLinearVelocity = Vector3.new(0, math.min(c.AssemblyLinearVelocity.Y, 0), 0)
			c.AssemblyAngularVelocity = Vector3.zero
		end
		self:restoreCollisions()
	end

	-- the staged run for event spec on target e (a trafficNear entry) starting at approachT: plan, meet, span, touch
	local function planFor(e, spec, approachT: number)
		local probe = table.clone(e)
		probe.s, probe.t = e.s + e.speed * (approachT - e.t), approachT
		local contact = e.halfLen + Rec.CAR_HALF_LEN
		local lead = nil
		if spec.mode == "rear" then
			lead = contact + (spec.speed - e.speed) * spec.approach
		elseif spec.mode == "head" then
			lead = contact + (spec.speed + e.speed) * spec.approach
		elseif spec.mode == "pass" then
			lead = (spec.speed - e.speed) * spec.approach
		elseif spec.mode == "passOncoming" then
			return JM.passOncomingPlan({route = e.route, s0 = probe.s, t0 = approachT, vT = e.speed, halfWid = e.halfWid,
				halfLen = e.halfLen, speed = spec.speed, lead = (spec.speed + e.speed) * spec.approach, gap = spec.gap})
		end
		return stage(probe, spec.mode, spec.speed, {lead = lead, angle = spec.angle, gap = spec.gap})
	end

	-- can event spec be staged on car e with a lead-in of Tl s from where the autopilot is now? Returns the candidate
	-- or nil: the target's lane straight over the run (and steady around a side touch, as pickTarget); the run's
	-- start and end within ctx.maxLat studs of the route ahead and heading along it; a lead-in that stays near the
	-- route, never touches the target, never goes over the cap, never turns back and never loses more than
	-- JM.MAX_DROP within 0.35 s; and the job still finishes in time (ctx.deadline).
	local function tryCandidate(job, D, e, spec, Tl: number, ctx)
		local path = job.path
		local approachT = D.lastT + Tl
		local plan, meet, span, touch = planFor(e, spec, approachT)
		if not plan then
			return nil
		end
		if span and not Rec.routeStraight(e.route, span[1], span[2], Rec.STAGE_BEND_DEG or 15) then
			return nil
		end
		if spec.mode == "side" and touch and not Rec.routeStraight(e.route, touch[1], touch[2], Rec.SIDE_STEADY_DEG or 1, 2) then
			return nil
		end
		local x1, z1, dx1, dz1 = plan(approachT)
		local s1, lat1 = pathProject(path, x1, z1, D.s - 5, 500)
		if not s1 or lat1 > ctx.maxLat or s1 < D.s + 5 then
			return nil
		end
		local _, _, tx, tz = pathPoint(path, s1)
		if dx1 * tx + dz1 * tz < 0.9 then
			return nil
		end
		local tEnd = meet
		if spec.mode == "pass" then
			tEnd = meet + (e.halfLen + Rec.CAR_HALF_LEN + 30) / math.max(spec.speed - e.speed, 1)
		elseif spec.mode == "passOncoming" then
			tEnd = meet + (e.halfLen + Rec.CAR_HALF_LEN + 30) / (spec.speed + e.speed)
		end
		local x2, z2 = plan(tEnd)
		local s2, lat2 = pathProject(path, x2, z2, s1 - 5, 600)
		if not s2 or lat2 > ctx.maxLat + 10 or s2 < s1 then
			return nil
		end
		local x0, z0 = D.lastPos.X, D.lastPos.Z
		local dist = math.sqrt((x1 - x0) ^ 2 + (z1 - z0) ^ 2)
		if dist < 8 then
			return nil
		end
		local f = JM.hermite(x0, z0, D.lastVel.X, D.lastVel.Z, x1, z1, dx1 * spec.speed, dz1 * spec.speed, Tl)
		local cs = JM.curveStats(f, Tl, (x1 - x0) / dist, (z1 - z0) / dist)
		if cs.maxV > ctx.cap + 4 or cs.minAlong < 3 or cs.maxDrop > JM.MAX_DROP or cs.maxA > 160 then
			return nil
		end
		local sRun = D.s
		for k = 1, 8 do
			local u = Tl * k / 9
			local x, z, vx, vz = f(u)
			local sk, latk = pathProject(path, x, z, sRun - 5, 300)
			if not sk or latk > ctx.maxLat + 8 then
				return nil
			end
			sRun = sk
			local tx2, tz2, tlx, tlz = carAt(e, D.lastT + u)
			local m = math.sqrt(vx * vx + vz * vz)
			local lx, lz = if m > 1 then vx / m else dx1, if m > 1 then vz / m else dz1
			if Rec.carsOverlap({x = x, z = z, lx = lx, lz = lz}, {x = tx2, z = tz2, lx = tlx, lz = tlz,
				halfWid = e.halfWid, halfLen = e.halfLen}, 3) then
				return nil
			end
		end
		-- the time the event costs after its run (offline session: head-on ~2.9 s = the watched hit window near
		-- standstill + the rejoin from rest; light / scrape ~0.7 s; near miss ~0.3 s), with margin
		local post = if spec.want == "headon" or spec.want == "heavy" then 3.5 elseif spec.want == "near" then 0.5 else 1.0
		local eta = tEnd + post + timeToGo(path, s2)
		if eta > ctx.deadline then
			return nil
		end
		return {e = e, spec = spec, plan = plan, meet = meet, approachT = approachT, f = f, T = Tl, tA = D.lastT,
			eta = eta, s1 = s1, s2 = s2, tEnd = tEnd}
	end

	-- the best staged event to start now (the earliest finish of the job), or nil
	local function planNext(job, D, ctx)
		local now = D.lastT
		local nominal = nominalAhead(job.path, D.s, D.v, D.cruise, 4.5)
		local models = trafficModels()
		local best = nil
		for _, e in TK.trafficNear(450, Vector3.new(D.lastPos.X, 0, D.lastPos.Z), now) do
			if job.used[e.key] or not models[e.key] then
				continue
			end
			local close = false
			for _, n in nominal do
				local ex, ez = carAt(e, now + n.t)
				if (ex - n.x) ^ 2 + (ez - n.z) ^ 2 < 140 * 140 then
					close = true
					break
				end
			end
			if not close then
				continue
			end
			for _, group in job.pending do
				for _, name in JM.GROUPS[group] do
					local spec = JM.eventSpec(name, e.speed, ctx.cap, ctx.cfg)
					if not spec then
						continue
					end
					local Tl = 1.0
					while Tl <= 3.0 + 1e-6 do
						local c = tryCandidate(job, D, e, spec, Tl, ctx)
						if c then
							c.group = group
							-- the crash first (the bump check's core, and the event that costs the most time); same-
							-- direction cars are scarce (one-way loops): a near miss prefers an oncoming car, the crash a
							-- head-on
							c.score = c.eta + (if group == "crash" then -4 else 0)
								+ (if name == "near" then 4 elseif name == "heavy" and group == "crash" then 2 else 0)
							if not best or c.score < best.score then
								best = c
							end
							break
						end
						Tl += 0.25
					end
				end
			end
		end
		return best
	end

	-- the watch after a staged hit: CarController's hit window + the anti-roll extra + 0.3 s untouched (its arcade
	-- response), then (heavy / head-on) a gentle stop. Unlike hitBody the car keeps ignoring scenery (Driver:step): a
	-- kerb or wall it slid into would trip the jobs speed-drop detector, a bump that is not the traffic hit's.
	local function afterHit(D, ev, cfg, job)
		local chassis = D.chassis
		local snap = D.st.snap
		local window = if snap and type(snap.control) == "number" then snap.control else 0
		local respond = window + (cfg.Arcade_AntiRollExtra or 0) + 0.3
		local minUp = 1
		local t1 = os.clock()
		while os.clock() - t1 < respond and not job.ended and not D.lost do
			waitFrame()
			minUp = math.min(minUp, chassis.CFrame.UpVector.Y)
		end
		if ev.tier == "heavy" or ev.tier == "headon" then
			local t2 = os.clock()
			while os.clock() - t2 < 3 and flat(chassis.AssemblyLinearVelocity).Magnitude > 15 and not job.ended do
				waitFrame()
				minUp = math.min(minUp, chassis.CFrame.UpVector.Y)
				local vv = chassis.AssemblyLinearVelocity
				local sp = flat(vv).Magnitude
				if sp > 0.5 then
					local k = math.max(sp - JM.HIT_BRAKE / math.max(rates.hb, 15), 0) / sp
					chassis.AssemblyLinearVelocity = Vector3.new(vv.X * k, vv.Y, vv.Z * k)
				end
			end
		end
		ev.minUp, ev.respond = minUp, respond
	end

	-- one staged event: lead-in, run, CarController's response, rejoin. Returns the event record.
	local function runEvent(job, D, cand, cfg)
		local e, spec = cand.e, cand.spec
		local ev = {group = cand.group, name = spec.name, mode = spec.mode, speed = spec.speed, angle = spec.angle,
			key = e.key, vT = e.speed, want = spec.want, approachT = cand.approachT, meet = cand.meet, tEnd = cand.tEnd,
			leadIn = cand.T, s1 = cand.s1, at = cand.tA - job.start, eta = cand.eta - job.start}
		job.used[e.key] = true
		player:SetAttribute("TK_HitTarget", e.key) -- only the target is real now (it un-ghosts within 0.25 s)
		D.st = {key = e.key, plan = cand.plan, meet = cand.meet, approachT = cand.approachT, speed = spec.speed,
			pass = spec.want == "near", frames = 0, done = false, hitsBefore = nil :: number?}
		D.curve = {kind = "leadin", f = cand.f, tA = cand.tA, T = cand.T, tEnd = cand.approachT, y0 = D.lastPos.Y,
			y1 = JM.Y}
		D.mode = "curve"
		while not D.st.done and not job.ended and not D.lost do
			waitFrame()
		end
		local st = D.st
		ev.reason, ev.touch = st.reason, st.touch
		if st.snap then
			local snap = st.snap
			ev.hit, ev.tier, ev.hitKey, ev.keyMatch = true, snap.tier, snap.key, snap.key == e.key
			ev.before, ev.after, ev.vc, ev.hitT = snap.before, snap.after, snap.vc, snap.t
			afterHit(D, ev, cfg, job)
		end
		player:SetAttribute("TK_HitTarget", 0) -- every car a ghost again
		if not job.ended and not D.lost then
			D:startRejoin(math.max(cand.s1, D.s), ev.tier == "heavy" or ev.tier == "headon")
			while D.mode == "curve" and not job.ended and not D.lost do
				waitFrame()
			end
		end
		return ev
	end

	-- one event as a line; asRun = during the drive (before the checks: no verdict, no bump / pay-out counts yet)
	local function eventLine(ev, asRun: boolean?): string
		local what = ("%s %s @%d%s on key %d (%.0f studs/s) from +%.1f s (job finish planned at +%.1f s)"):format(ev.name,
			ev.mode, ev.speed, if ev.angle then " a" .. ev.angle else "", ev.key, ev.vT, ev.at or 0, ev.eta or 0)
		if ev.want == "near" then
			if asRun then
				return ("%s: %s"):format(what, tostring(ev.reason))
			end
			return ("%s: %s, %d near miss(es) paid, %d hit(s)%s"):format(what, tostring(ev.reason), ev.paid or 0,
				ev.hitsDuring or 0, if ev.ok then "" else " - FAIL")
		end
		local hit = ("%s: %s, tier %s (planned %s), hit key %s%s, impact %s -> %s, vc %s"):format(what, tostring(ev.reason),
			tostring(ev.tier or "-"), ev.want, tostring(ev.hitKey or "-"), if ev.keyMatch then " = target" else "",
			int(ev.before), int(ev.after), int(ev.vc))
		if asRun then
			return hit
		end
		return hit .. (if ev.want == "heavy" or ev.want == "headon" then (", accepted %s, bumps %d"):format(
			if ev.accepted then "yes" else "NO", ev.bumps or 0) else (", bumps %d"):format(ev.bumps or 0))
			.. (if ev.ok then "" else " - FAIL")
	end

	local function leaderstat(name: string): number?
		local ls = player:FindFirstChild("leaderstats")
		local v = ls and ls:FindFirstChild(name)
		return if v then (v :: any).Value else nil
	end

	-- ONE job: stand -> request -> drive with staged events -> finish -> checks. Never leaves a job running.
	local function jobRun(kind: string, stand, opts, ctxBase, emit)
		local res = {kind = kind, stand = stand.id, status = "FAIL", ok = false, events = {}, lines = {}, reason = nil}
		local cleanup = {}
		activeRuns[cleanup] = true
		local okBody, err = pcall(function()
			local chassis, model = TK.car()
			assert(chassis and model, "jobDriveTest: get in a car first (TK.seatIn)")
			if player:GetAttribute("JobActive") == true then
				TK.fire("CancelJob")
				local t0 = os.clock()
				while player:GetAttribute("JobActive") == true and os.clock() - t0 < 3 do
					waitFrame()
				end
			end
			-- 1. to the stand BEFORE the job (the server kit moves the car in anchored hops), then still in the ring
			local okTp, msg = serverCall(45, "teleport", stand.pos, {look = stand.road})
			assert(okTp, "teleport to the stand failed: " .. tostring(msg))
			local t0 = os.clock()
			repeat
				waitFrame()
			until not chassis.Anchored or os.clock() - t0 > 5
			waitSeconds(0.4)
			chassis, model = TK.car()
			assert(chassis and model, "jobDriveTest: not in a car after the teleport")
			local D = newDriver(chassis, model, ctxBase.cap)
			table.insert(cleanup, function()
				D:stop()
			end)
			local g = D:groundY(chassis.Position.X, chassis.Position.Z, chassis.Position.Y)
			if g then
				D.ride = math.clamp(chassis.Position.Y - (g - D.ride), 1.5, 6)
			end
			waitSeconds(0.5)
			local inRing = flat(chassis.Position - stand.pos).Magnitude
			assert(inRing < 14, ("the car is %.0f studs from the ring centre after the teleport"):format(inRing))
			if ctxBase.needSelfCheck then
				-- once per frame-rate level, before any hook is set: TestKit and PattayaTraffic agree on the keys
				local okC, lines, info = TK.selfCheck(5)
				for _, l in lines do
					emit("    " .. l)
				end
				if not okC and info.compared > 0 then
					error("TK.selfCheck failed: TestKit and PattayaTraffic disagree on the traffic keys (see the lines above)", 0)
				end
				ctxBase.needSelfCheck = info.compared == 0 -- no traffic model here to compare: try at the next stand
			end
			-- 2. the request, as the E key sends it, with TK.jobWatch on for the whole job
			local w = TK.jobWatch()
			table.insert(cleanup, function()
				w:stop()
			end)
			table.insert(cleanup, function()
				if player:GetAttribute("JobActive") == true then
					TK.fire("CancelJob") -- a failed or stopped run never leaves a job running
				end
			end)
			pcall(serverCall, 10, "speedProbe", "start")
			local money0 = leaderstat("Money")
			local function stopEvent()
				for _, e in w.events do
					if e.kind == "job stop" then
						return e
					end
				end
				return nil
			end
			TK.fire("RequestJob", stand.id)
			local tReq = os.clock()
			local refired = false
			while not w.start and not stopEvent() and os.clock() - tReq < 5 do
				waitFrame()
				if not refired and os.clock() - tReq > 1.5 then
					refired = true
					TK.fire("RequestJob", stand.id) -- the server drops a request within 0.5 s of the last one
				end
			end
			if not w.start then
				local s = stopEvent()
				res.status, res.reason = "NO JOB", if s then tostring(s.data) else "no answer to RequestJob in 5 s"
				return
			end
			local start = w.start
			res.to, res.fare, res.timeLimit, res.length = start.to, start.fare, start.timeLimit, start.length
			-- 3. the drive
			local path = buildPath(start.route, ctxBase.cruise, chassis.Position)
			local job = {path = path, start = start.start, timeLimit = start.timeLimit, used = {}, pending = {},
				ended = false, tries = {}}
			for _, gname in ctxBase.events do
				table.insert(job.pending, gname)
			end
			-- an event is staged only when the job still finishes 4 s before its time limit (the estimate errs on the
			-- slow side: 0.5-1 s in the offline session)
			local ctx = {cap = ctxBase.cap, cfg = ctxBase.cfg, maxLat = ctxBase.detour,
				deadline = start.start + start.timeLimit - 4}
			player:SetAttribute("TK_HitTarget", 0) -- every traffic car a ghost: only staged targets are ever real
			table.insert(cleanup, function()
				player:SetAttribute("TK_HitTarget", nil)
			end)
			D.path, D.s, D.v, D.cruise = path, 0, 0, ctxBase.cruise
			D.mode = "route"
			local nextPlan = 0
			while true do
				waitFrame()
				if D.lost then
					job.ended, job.why = true, "left the car"
					break
				end
				if w.finish then
					break
				end
				local s = stopEvent()
				if s then
					job.ended, job.why = true, tostring(s.data)
					break
				end
				if D.mode == "route" and D.arrived then
					break
				end
				if D.mode == "route" and #job.pending > 0 and os.clock() >= nextPlan and D.s < path.total - 60 then
					nextPlan = os.clock() + 0.2
					ctx.maxLat = if path.total - D.s < 400 then math.max(ctxBase.detour, 60) else ctxBase.detour
					local cand = planNext(job, D, ctx)
					if cand then
						local ev = runEvent(job, D, cand, ctx.cfg)
						table.insert(res.events, ev)
						local achieved = if ev.want == "near" then ev.reason == "passed"
							else (ev.reason == "hit" and ev.tier == ev.want and ev.keyMatch == true)
						job.tries[cand.group] = (job.tries[cand.group] or 0) + 1
						if achieved or job.tries[cand.group] >= 3 then
							table.remove(job.pending, table.find(job.pending, cand.group) :: number)
						end
						if opts.verbose then
							emit("    event (as run): " .. eventLine(ev, true))
						end
					end
				end
			end
			-- 4. stopped in the destination ring: the server finishes the job
			if not job.ended then
				D.mode = "hold"
				local t1 = os.clock()
				while not w.finish and not stopEvent() and os.clock() - t1 < 6 do
					waitFrame()
				end
				if not w.finish then
					local s = stopEvent()
					job.ended, job.why = true, if s then tostring(s.data) else "no finish 6 s after stopping in the ring"
				end
			end
			D:stop()
			waitSeconds(1.0) -- the last JobUpdate / attribute changes arrive
			res.finish = w.finish
			res.uncovered = job.pending
			res.why = job.why
			-- 5. checks
			local evs = w.events
			local mb = JM.matchBumps(evs, {noStray = true, requireAccepted = true})
			res.match = mb
			local problems = {}
			if job.ended then
				table.insert(problems, "job ended: " .. tostring(job.why))
			end
			for _, l in mb.lines do
				if l:find("FAIL", 1, true) then
					table.insert(problems, l)
				end
			end
			if mb.stray > 0 and (ctxBase.hz or 60) <= 24 then
				-- 15 fps with uneven frames (offline: frame times +-20 %): the jobs server reads speed from positions every 0.1 s and
				-- a 15 fps car moves in steps, so two low readings in a row can come from the frame rate alone
				table.insert(problems, ("at %.0f Hz a stray bump can be the frame rate (the server's 10 Hz speed reading of a car that moves in %.0f steps a second: see the server speed probe line); rerun at 30 or 60 fps"):format(
					ctxBase.hz, ctxBase.hz))
			end
			for _, ev in res.events do
				ev.ok = true
				if ev.want == "near" then
					local paid, hitsDuring = 0, 0
					for _, x in evs do
						if x.t >= ev.approachT - 0.2 and x.t <= ev.tEnd + 1.0 then
							if x.kind == "near" then paid += 1 elseif x.kind == "hit" then hitsDuring += 1 end
						end
					end
					ev.paid, ev.hitsDuring = paid, hitsDuring
					ev.ok = ev.reason == "passed" and paid == 1 and hitsDuring == 0
				else
					ev.bumps = 0
					local tH = ev.hitT or ev.meet
					for _, x in evs do
						if x.kind == "job bump" and x.t >= tH - 0.5 and x.t <= tH + 1.6 then
							ev.bumps += 1
						end
						if x.kind == "accepted" and x.t >= tH - 0.3 and x.t <= tH + 1.0 then
							ev.accepted = true
						end
					end
					local crash = ev.want == "heavy" or ev.want == "headon"
					ev.ok = ev.reason == "hit" and ev.tier == ev.want and ev.keyMatch == true
						and (if crash then ev.accepted == true and ev.bumps == 1 else ev.bumps == 0)
				end
				if not ev.ok then
					table.insert(problems, eventLine(ev))
				end
			end
			if res.finish then
				local pok, ptext = TK.jobPayout(start, res.finish, mb.near)
				res.payout = ptext
				if not pok then
					table.insert(problems, ptext)
				end
				if (res.finish.bumps or 0) ~= mb.bumps then
					table.insert(problems, ("finish says %d bump(s), %d bump events seen"):format(res.finish.bumps or 0, mb.bumps))
				end
				local money1 = leaderstat("Money")
				if money0 and money1 and money1 - money0 ~= res.finish.money then
					table.insert(problems, ("Money went up by %d, the finish paid %d"):format(money1 - money0, res.finish.money))
				end
				res.moneyDelta = if money0 and money1 then money1 - money0 else nil
			end
			local wtext, wok = w:report()
			res.watch = wtext
			if not wok then
				table.insert(problems, "jobWatch: FAIL")
			end
			local okProbe, probe = pcall(serverCall, 10, "speedProbe", "get", start.start, workspace:GetServerTimeNow())
			res.probe = if okProbe then probe else nil
			res.problems = problems
			if #problems > 0 then
				res.status = "FAIL"
			elseif #job.pending > 0 then
				res.status = "INCOMPLETE"
			else
				res.status, res.ok = "PASS", true
			end
		end)
		runCleanup(cleanup)
		activeRuns[cleanup] = nil
		if not okBody then
			res.status, res.reason = "FAIL", "error: " .. tostring(err)
		end
		return res
	end

	local function runLine(res, label: string): string
		if res.status == "NO JOB" or (res.status == "FAIL" and res.reason) then
			return ("%s jobDrive %s%s at %s: %s"):format(res.status, label, res.kind, res.stand, tostring(res.reason))
		end
		local f = res.finish
		local evs = {}
		for _, ev in res.events do
			table.insert(evs, ("%s %s"):format(ev.name, if ev.ok then "ok" else "FAIL"))
		end
		local mb = res.match or {}
		return ("%s jobDrive %s%s %s -> %s: %d studs, limit %s s, fare %s%s [Heartbeat %.0f Hz, render %.0f fps%s] | events: %s%s | bumps %s (accepted hits %s, stray %s, doubles %s) | near misses %s | %s%s"):format(
			res.status, label, res.kind, res.stand, tostring(res.to), math.floor(res.length or 0), tostring(res.timeLimit),
			tostring(res.fare), if f then (", done in %.1f s"):format(f.time) else "", rates.hb, rates.render,
			if TK.fpsLimitOn() then (", cap %d fps"):format(TK.fpsLimitOn() :: number) else "",
			if #evs > 0 then table.concat(evs, ", ") else "none",
			if res.uncovered and #res.uncovered > 0 then " | not covered: " .. table.concat(res.uncovered, ", ") .. " (no traffic car along the route in time)" else "",
			tostring(mb.bumps or "-"), tostring(mb.accepted or "-"), tostring(mb.stray or "-"), tostring(mb.doubles or "-"),
			tostring(mb.near or "-"), tostring(res.payout or "no pay-out"),
			if res.problems and #res.problems > 0 then " | " .. table.concat(res.problems, "; ") else "")
	end

	-- the stands to use for a kind, in order (opts.stands, else JM.STANDS, else every stand of the kind, nearest first)
	local function standsFor(kind: string, opts)
		local all = standList(kind)
		local byId = {}
		for _, s in all do
			byId[s.id] = s
		end
		local want = opts.stands
		if type(want) == "table" and want[kind] then
			want = want[kind]
		end
		if type(want) == "string" then
			want = {want}
		end
		local out = {}
		for _, id in (if type(want) == "table" and #want > 0 then want else JM.STANDS[kind] or {}) do
			if byId[id] then
				table.insert(out, byId[id])
			end
		end
		if #out == 0 then
			local here = TK.car()
			local p = if here then here.Position else Vector3.zero
			table.sort(all, function(a, b)
				return flat(a.pos - p).Magnitude < flat(b.pos - p).Magnitude
			end)
			out = all
		end
		return out
	end

	function TK.jobDriveTest(opts, out: {string}?)
		opts = table.clone(opts or {})
		assert(Rec, "jobDriveTest: ReplicatedStorage.PattayaRecovery missing")
		assert(TK.car(), "jobDriveTest: get in a car first (TK.seatIn)")
		assert(ReplicatedStorage:FindFirstChild("PattayaTestKitRemote"),
			"jobDriveTest: start the server kit first: require(game.ServerStorage.PattayaTestKitServer).start()")
		local kinds = opts.kinds or {"taxi", "delivery"}
		local runs = opts.runs or 2
		local levels = if type(opts.fps) == "table" then table.clone(opts.fps)
			elseif type(opts.fps) == "number" then {opts.fps} else {0}
		local events = table.clone(opts.events or JM.EVENTS)
		if opts.heavy and not table.find(events, "heavy") then
			table.insert(events, "heavy")
		end
		local all, summaries = {}, {}
		local function emit(s: string)
			print(s)
			table.insert(all, s)
			if out then table.insert(out, s) end
		end
		local cleanup = {}
		activeRuns[cleanup] = true
		local progress0 = {Money = leaderstat("Money"), EXP = leaderstat("EXP"), Level = leaderstat("Level")}
		local restoreProgress = opts.keepProgress ~= false and progress0.Money ~= nil
		local leased = false
		local leaseSeconds = math.min(1800, 120 + #levels * #kinds * runs * 100)
		local results = {}
		-- a stopped test (handle:stop / TK.cleanup) never returns here: these give the lease and the progress back then
		table.insert(cleanup, function()
			if leased then
				leased = false
				serverSend("arcadeRelease")
			end
			if restoreProgress then
				restoreProgress = false
				serverSend("setProgress", progress0)
			end
			serverSend("speedProbe", "stop")
		end)
		local okAll, err = pcall(function()
			-- CollisionModel = "arcade" on the server for this test only (a lease: given back below, by TK.cleanup, and
			-- it runs out by itself after leaseSeconds)
			local okL, leaseMsg = serverCall(15, "arcadeLease", leaseSeconds)
			assert(okL, "arcade lease refused: " .. tostring(leaseMsg))
			leased = true
			local t0 = os.clock()
			while workspace:GetAttribute("CollisionModel") ~= "arcade" and os.clock() - t0 < 3 do
				waitFrame()
			end
			assert(workspace:GetAttribute("CollisionModel") == "arcade", "CollisionModel did not reach this client as arcade")
			emit("jobDriveTest: " .. tostring(leaseMsg))
			for _, fps in levels do
				local flabel = if fps > 0 then ("%dfps "):format(fps) else ""
				TK.fpsLimit(if fps > 0 then fps else nil)
				waitSeconds(1.2)
				local hz = math.min(if fps > 0 then fps else 1000, if rates.hb > 0 then rates.hb else 60)
				-- the route at the cruise speed; the staged runs (and their lead-ins) up to the frame-rate cap, so a heavy
				-- rear-end at traffic speed + 60 fits at 30 and 60 fps
				local cap = math.min(JM.capFor(hz), 120)
				local cruise = math.min(opts.cruise or 100, cap)
				local ctxBase = {cap = cap, cruise = cruise, cfg = Rec.config(), detour = opts.detour or 30, events = events,
					needSelfCheck = opts.skipSelfCheck ~= true, hz = hz}
				local lvlPass, lvlRuns = 0, 0
				for _, kind in kinds do
					local list = standsFor(kind, opts)
					if #list == 0 then
						emit(("FAIL jobDrive %s%s: no job stand of this kind in workspace.PattayaWorld.JobStands"):format(flabel, kind))
						continue
					end
					local pick = 0
					for r = 1, runs do
						local res
						for _ = 1, math.min(3, #list) do
							pick = pick % #list + 1
							res = jobRun(kind, list[pick], opts, ctxBase, emit)
							if res.status ~= "NO JOB" then
								break
							end
							emit(runLine(res, flabel))
						end
						res.level, res.cap = fps, cap
						table.insert(results, res)
						lvlRuns += 1
						if res.ok then
							lvlPass += 1
						end
						emit(runLine(res, flabel .. ("r%d "):format(r)))
						if opts.verbose or not res.ok then
							for _, ev in res.events do
								emit("    " .. eventLine(ev))
							end
							if res.watch then
								for l in string.gmatch(res.watch, "[^\n]+") do
									emit("    " .. l)
								end
							end
							if res.probe then
								emit("    server speed probe: " .. tostring(res.probe))
							end
						end
					end
				end
				table.insert(summaries, ("@%s: %d/%d runs PASS (autopilot: route <= %d, staged runs <= %d studs/s)"):format(
					if fps > 0 then fps .. " fps" else "client rate", lvlPass, lvlRuns, cruise, cap))
			end
		end)
		TK.fpsLimit(nil)
		player:SetAttribute("TK_HitTarget", nil)
		-- the lease back (CollisionModel as it was before the test, "physical" if it was already "arcade") and the
		-- progress as it was, on every path that gets here
		local relMsg = "no lease taken"
		if leased then
			leased = false
			local okR, _, msg = pcall(serverCall, 15, "arcadeRelease")
			relMsg = if okR then tostring(msg) else "lease release failed: " .. tostring(msg)
			local t1 = os.clock()
			while workspace:GetAttribute("CollisionModel") == "arcade" and os.clock() - t1 < 3 do
				waitFrame()
			end
		end
		if restoreProgress then
			restoreProgress = false
			pcall(serverCall, 15, "setProgress", progress0)
		end
		activeRuns[cleanup] = nil
		pcall(serverCall, 10, "speedProbe", "stop")
		if not okAll then
			emit("jobDriveTest: error: " .. tostring(err))
		end
		-- coverage and totals
		local count = {crash = 0, heavy = 0, light = 0, scrape = 0, near = 0}
		local pass, total, incomplete = 0, 0, 0
		for _, r in results do
			total += 1
			if r.ok then pass += 1 end
			if r.status == "INCOMPLETE" then incomplete += 1 end
			for _, ev in r.events do
				if ev.ok then
					count[ev.group] = (count[ev.group] or 0) + 1
				end
			end
		end
		local cov = {}
		for _, g in events do
			table.insert(cov, ("%s %d"):format(g, count[g] or 0))
		end
		local cleanText = TK.cleanup(true)
		local summary = ("jobDriveTest: %d/%d runs PASS%s | %s | events ok: %s | %s | %s%s"):format(pass, total,
			if incomplete > 0 then (" (%d INCOMPLETE)"):format(incomplete) else "", table.concat(summaries, " | "),
			table.concat(cov, ", "), relMsg, cleanText, if pass == total and total > 0 and okAll then " - ALL PASS" else "")
		emit(summary)
		return summary, results
	end

	-- the background runner shared by the job test (a coroutine resumed from Heartbeat: it outlives the Studio execute
	-- snippet that starts it, as TK.hitMatrixStart). The handle lives in _G.TK_LIVE too, so TK.jobDrivePoll() finds it
	-- from another copy of this module.
	local function background(name: string, body)
		local h = {name = name, lines = {}, done = false, summary = nil :: string?, error = nil :: string?}
		local co = coroutine.create(function()
			local ok, summary = pcall(body, h)
			if ok then
				h.summary = summary
			else
				h.error = tostring(summary)
			end
			h.done = true
		end)
		local conn
		conn = RunService.Heartbeat:Connect(function()
			if coroutine.status(co) ~= "suspended" then
				conn:Disconnect()
				h.done = true
				return
			end
			local prev = runnerCo
			runnerCo = co
			local ok, err = coroutine.resume(co)
			runnerCo = prev
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
			TK.cleanup(true) -- the runs' cleanup lists: job cancelled, lease and progress given back, car free
		end
		TK.handles[name] = h
		live.handles = live.handles or {}
		live.handles[name] = h
		return h
	end

	function TK.jobDriveTestStart(opts)
		local running = live.handles and live.handles.jobDrive
		assert(not (running and not running.done),
			"a job test is already running: TK.jobDrivePoll(), or stop it with _G.TK_LIVE.handles.jobDrive:stop()")
		return background("jobDrive", function(h)
			return (TK.jobDriveTest(opts, h.lines))
		end)
	end

	-- the poll line of the running (or last) job test, from any copy of this module
	function TK.jobDrivePoll(): string
		local h = live.handles and live.handles.jobDrive
		return if h then h:poll() else "no job test started"
	end
end

-- 2-player check, client half (team18/arcade-econ; offline only) -------------------------------------------------
-- TK.startAgent() -> text   answers the server kit's S.mpCheck through ReplicatedStorage.PattayaTestKitAgent: each
--   command runs on THIS player's own client (its car, its attributes, its traffic view) and reports back. In Studio /
--   DevTest, PattayaTraffic starts it by itself when the server sets workspace attribute TK_ClientAgent = true, so
--   nothing has to be typed into each client; it stops when that attribute is cleared. TK.stopAgent() stops it.
-- Commands: ping, watchStart, watchStop(key, t1, t2), hitTest(mode, speed, opts), nearMiss(opts), park,
--   jobStart(standId), jobState, jobCancel, cleanup.
do
	local AGENT_ATTRS = {"Recovery_HitCount", "Recovery_LastHitKey", "Recovery_LastHitT", "Recovery_LastHitTier",
		"Recovery_LastHit", "Recovery_HitIgnored", "Recovery_Uprights", "TrafficHits", "TrafficHitAt", "TrafficHitTier",
		"NearMissAt", "NearMissCombo", "TK_HitTarget", "TrafficGhostAll", "TK_FpsLimit", "JobActive"}

	local function agentState()
		local s = {name = player.Name, userId = player.UserId,
			collisionModel = tostring(workspace:GetAttribute("CollisionModel")), attrs = {}, car = false}
		for _, a in AGENT_ATTRS do
			local v = player:GetAttribute(a)
			if v ~= nil then
				s.attrs[a] = if type(v) == "number" or type(v) == "boolean" or type(v) == "string" then v else tostring(v)
			end
		end
		local chassis = TK.car()
		if chassis then
			s.car, s.pos = true, chassis.Position
			s.speed = flat(chassis.AssemblyLinearVelocity).Magnitude
			s.upY = chassis.CFrame.UpVector.Y
			local ar = chassis:FindFirstChild("ArcadeAntiRoll")
			s.antiRoll = ar ~= nil and (ar :: any).Enabled == true
		end
		local models, gh = 0, 0
		for _, m in trafficModels() do
			models += 1
			if ghosted(m) then
				gh += 1
			end
		end
		s.models, s.ghosted = models, gh
		return s
	end

	local CMDS = {}

	function CMDS.ping()
		return agentState()
	end

	-- watch this client while the other player tests: own car (moved? anti-roll?), own attributes, the traffic view
	-- (how many models ghosted, and when each key was ghosted)
	function CMDS.watchStart()
		local A = live.agent
		if A.watch then
			A.watch.conn:Disconnect()
		end
		local chassis = TK.car()
		local W = {t0 = workspace:GetServerTimeNow(), maxMove = 0, maxSpeed = 0, antiRoll = false, frames = 0,
			ghostMax = 0, models = 0, keys = {}, before = agentState().attrs, tkSet = false,
			p0 = chassis and chassis.Position}
		W.conn = RunService.Heartbeat:Connect(function()
			W.frames += 1
			local c = TK.car()
			if c and W.p0 then
				W.maxMove = math.max(W.maxMove, flat(c.Position - W.p0).Magnitude)
				W.maxSpeed = math.max(W.maxSpeed, flat(c.AssemblyLinearVelocity).Magnitude)
				local ar = c:FindFirstChild("ArcadeAntiRoll")
				if ar and (ar :: any).Enabled == true then
					W.antiRoll = true
				end
			end
			if player:GetAttribute("TK_HitTarget") ~= nil or player:GetAttribute("TrafficGhostAll") == true then
				W.tkSet = true
			end
			local t = workspace:GetServerTimeNow()
			local n, g = 0, 0
			for key, m in trafficModels() do
				n += 1
				local gh = ghosted(m)
				if gh then
					g += 1
				end
				local k = W.keys[key]
				if not k then
					k = {first = t, last = t, ghost = {}, on = false}
					W.keys[key] = k
				end
				k.last = t
				if gh and not k.on then
					table.insert(k.ghost, {t, math.huge})
				elseif not gh and k.on then
					k.ghost[#k.ghost][2] = t
				end
				k.on = gh
			end
			if n > 0 then
				W.ghostMax = math.max(W.ghostMax, g / n)
			end
			W.models = math.max(W.models, n)
		end)
		A.watch = W
		return {t0 = W.t0, car = chassis ~= nil}
	end

	-- what changed since watchStart; key / t1 / t2: was that traffic car drawn on this client then, and ghosted?
	function CMDS.watchStop(key: number?, t1: number?, t2: number?)
		local A = live.agent
		local W = A.watch
		assert(W, "watchStop without watchStart")
		W.conn:Disconnect()
		A.watch = nil
		local after = agentState()
		local changed = {}
		for _, a in AGENT_ATTRS do
			if W.before[a] ~= after.attrs[a] then
				table.insert(changed, ("%s: %s -> %s"):format(a, tostring(W.before[a]), tostring(after.attrs[a])))
			end
		end
		local keyInfo = nil
		if type(key) == "number" then
			local k = W.keys[key]
			local a, b = t1 or W.t0, t2 or math.huge
			keyInfo = {seen = k ~= nil and k.first <= b and k.last >= a, ghosted = false}
			if k then
				for _, iv in k.ghost do
					if iv[1] <= b and iv[2] >= a then
						keyInfo.ghosted = true
					end
				end
			end
		end
		return {maxMove = W.maxMove, maxSpeed = W.maxSpeed, antiRoll = W.antiRoll, tkSet = W.tkSet,
			ghostMax = W.ghostMax, models = W.models, frames = W.frames, changed = changed, key = keyInfo,
			collisionModel = after.collisionModel}
	end

	-- a staged hit on THIS player's car (TK.hitTest, isolated), with the anti-roll watched on this car
	function CMDS.hitTest(mode: string, speed: number, opts)
		local o = if type(opts) == "table" then opts else {}
		if o.isolate == nil then
			o.isolate = true
		end
		local seen = false
		local conn = RunService.Heartbeat:Connect(function()
			local c = TK.car()
			local ar = c and c:FindFirstChild("ArcadeAntiRoll")
			if ar and (ar :: any).Enabled == true then
				seen = true
			end
		end)
		local ok, res = pcall(TK.hitTest, mode, speed, o)
		conn:Disconnect()
		if not ok then
			error(res, 0)
		end
		return {touched = res.touched == true, tier = res.tier, hitKey = res.hitKey, targetKey = res.targetKey,
			keyMatch = res.keyMatch == true, hitT = res.hitT, meet = res.meet, before = res.before, after = res.after,
			minUp = res.minUp, reason = res.reason, text = res.text, antiRoll = seen}
	end

	function CMDS.nearMiss(opts)
		local r = TK.nearMissTest(if type(opts) == "table" then opts else {})
		return {ok = r.ok, awards = r.awards, hits = r.hits, targetKey = r.targetKey, text = r.text}
	end

	-- stop the car where it is (CarController's idle hold keeps it there)
	function CMDS.park()
		local c = TK.car()
		if c then
			c.AssemblyLinearVelocity = Vector3.zero
			c.AssemblyAngularVelocity = Vector3.zero
		end
		return {car = c ~= nil}
	end

	-- a job requested the way the E key does (the server kit already put this car in the stand's ring)
	function CMDS.jobStart(standId: string)
		local A = live.agent
		if A.job then
			A.job:stop()
		end
		local w = TK.jobWatch()
		A.job = w
		TK.fire("RequestJob", standId)
		local t0 = os.clock()
		local refired = false
		local stopped = nil
		while not w.start and os.clock() - t0 < 5 do
			RunService.Heartbeat:Wait()
			for _, e in w.events do
				if e.kind == "job stop" then
					stopped = e.data
				end
			end
			if stopped then
				break
			end
			if not refired and os.clock() - t0 > 1.5 then
				refired = true
				TK.fire("RequestJob", standId)
			end
		end
		return {started = w.start ~= nil, to = w.start and w.start.to, timeLimit = w.start and w.start.timeLimit,
			reason = if stopped ~= nil then tostring(stopped) else nil}
	end

	function CMDS.jobState()
		local w = live.agent.job
		local out = {active = player:GetAttribute("JobActive") == true, bumps = 0, hits = 0, accepted = 0, events = {}}
		if w then
			for _, e in w.events do
				if e.kind == "job bump" then
					out.bumps += 1
				elseif e.kind == "hit" then
					out.hits += 1
				elseif e.kind == "accepted" then
					out.accepted += 1
				end
				if #out.events < 20 then
					table.insert(out.events, ("%.2f %s %s"):format(e.t, e.kind, brief(e.data, 1)))
				end
			end
		end
		return out
	end

	function CMDS.jobCancel()
		TK.fire("CancelJob")
		local t0 = os.clock()
		while player:GetAttribute("JobActive") == true and os.clock() - t0 < 3 do
			RunService.Heartbeat:Wait()
		end
		local w = live.agent.job
		if w then
			w:stop()
			live.agent.job = nil
		end
		return {active = player:GetAttribute("JobActive") == true}
	end

	function CMDS.cleanup()
		return TK.cleanup(true)
	end

	function TK.startAgent(): string
		if live.agent and live.agent.on then
			return "agent already running"
		end
		local ev = ReplicatedStorage:FindFirstChild("PattayaTestKitAgent")
		if not (ev and ev:IsA("RemoteEvent")) then
			return "no ReplicatedStorage.PattayaTestKitAgent (start the server kit first)"
		end
		local remote = ev :: RemoteEvent
		local A = {on = true, conns = {}, watch = nil :: any, job = nil :: any}
		live.agent = A
		table.insert(A.conns, remote.OnClientEvent:Connect(function(kind, id, cmd, ...)
			if kind ~= "cmd" or not A.on then
				return
			end
			local args = table.pack(...)
			task.spawn(function()
				local f = CMDS[cmd]
				local ok, res = false, "unknown agent command " .. tostring(cmd)
				if f then
					ok, res = pcall(f, table.unpack(args, 1, args.n))
				end
				remote:FireServer("result", id, ok, if ok then res else tostring(res))
			end)
		end))
		table.insert(A.conns, workspace:GetAttributeChangedSignal("TK_ClientAgent"):Connect(function()
			if workspace:GetAttribute("TK_ClientAgent") ~= true then
				TK.stopAgent()
			end
		end))
		remote:FireServer("hello", agentState())
		return "agent started"
	end

	function TK.stopAgent(): string
		local A = live.agent
		if not (A and A.on) then
			return "no agent running"
		end
		A.on = false
		for _, c in A.conns do
			c:Disconnect()
		end
		if A.watch then
			A.watch.conn:Disconnect()
		end
		if A.job then
			A.job:stop()
		end
		live.agent = nil
		return "agent stopped"
	end
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
