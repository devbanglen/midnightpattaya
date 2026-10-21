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
-- TK.trafficNear(radius?, at?) -> {{pos, look, speed, halfLen, halfWid, kind, dist}}  traffic cars around the car
--   (or `at`), nearest first, from the same deterministic formula the traffic uses (server clock)
-- TK.hitTest(mode, speed, opts?) -> result   staged traffic hit on the target's own lane: "rear" (rear-end, from
--   opts.lead = 120 studs behind along its route), "head" (head-on, from 120 ahead, against the route), "side"
--   (from its right at opts.angle, default 20 degrees, level with it at the touch). Target = the nearest traffic
--   car that has a model (opts.target = an entry of trafficNear). The car's position is planned with the traffic's
--   own route formula (PattayaRecovery.stagePlan), so it meets the car where it really is; opts.offset = studs to
--   its right (rear / head). Hands off on the arcade hit (or at contact in physical mode) and measures:
--   {touched, onTarget, tier, vc, before, after (arcade: the game's own speed right after the cut; physical: the
--   lowest speed in the 0.4 s after contact), lossPct, yawDeg (2 s), minUp, flipped, uprights}; result.text
-- TK.trafficModelAt(pos, within) -> Model?   the traffic model near a spot (nil = no model: cannot be hit)
--   Round 3 rules: the target is the nearest car whose whole approach (start spot included) stays opts.clearance (30)
--   studs from every other traffic car; if none, every other car ghosts for the run (TestKit-only hook
--   TK_HitTarget in PattayaTraffic, Studio / DevTest only). The car waits 0.3 s at its start; only a hit after the
--   approach began, near the planned meeting time, on the target counts (PattayaRecovery.acceptStagedHit). Arcade:
--   my car ignores scenery during the approach. Each row reports the Heartbeat rate (Hz).
-- TK.hitMatrix(opts?) -> summary, rows       every row of TK.HIT_MATRIX, PASS / FAIL against the owner's table;
--   opts.runs = 3 repeats it and prints "REPEATABLE" only when every row of every run passed. Rows are isolated
--   (other traffic ghosts, labelled "isolated"); opts.isolate = false = real traffic: another car within 30 studs
--   of mine before the touch aborts the row, retried with another target up to 3 times.
--   Round 4: my car and the seated character do not collide during an arcade approach; each row prints the lowest
--   speed seen on the approach ("approach-min").
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
function TK.trafficNear(radius: number?, at: Vector3?)
	assert(Rec, "trafficNear: ReplicatedStorage.PattayaRecovery missing")
	if not trafficRoutes then
		local data = ReplicatedStorage:FindFirstChild("PattayaTraffic")
		assert(data, "trafficNear: ReplicatedStorage.PattayaTraffic missing")
		trafficRoutes = Rec.buildTrafficRoutes(require(data :: ModuleScript), 20000, 0)
	end
	local chassis = TK.car()
	local c = at or (chassis and chassis.Position)
	assert(c, "trafficNear: get in a car or pass a position")
	local out = {}
	for _, e in Rec.trafficNear(trafficRoutes, workspace:GetServerTimeNow(), c.X, c.Z, radius or 300) do
		local sh = Rec.TRAFFIC_SHAPES[e.kind] or Rec.TRAFFIC_SHAPES[0]
		table.insert(out, {pos = Vector3.new(e.x, 1, e.z), look = Vector3.new(e.lx, 0, e.lz), speed = e.speed,
			halfLen = sh.len / 2, halfWid = sh.wid / 2, kind = e.kind, dist = e.dist, route = e.route, s = e.s, t = e.t})
	end
	return out
end

-- the traffic model PattayaTraffic shows near a spot (nil = that car has no model this frame: the pool of 70 is full,
-- and a car without a model is invisible and cannot be hit at all)
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

-- staged hit: plan, target and lane checks (all maths in PattayaRecovery: stagePlan, plannedPathClear,
-- acceptStagedHit, tested offline in tools/qa/tests/test_recovery.py)
local function stage(target, mode: string, speed: number, opts)
	return Rec.stagePlan({route = target.route, s0 = target.s, t0 = target.t, vT = target.speed,
		halfWid = target.halfWid, halfLen = target.halfLen, speed = speed, mode = mode, lead = opts.lead,
		offset = opts.offset, angle = opts.angle, runLat = opts.runLat})
end

-- the nearest traffic car with a model whose whole approach is clear of every other traffic car by `clearance`
-- studs (start spot included); returns target, clear (false = none was clear: the nearest with a model)
local function pickTarget(mode: string, speed: number, opts, startDelay: number)
	local clearance = opts.clearance or 30
	local fallback = nil
	for _, e in TK.trafficNear(opts.radius or 500) do
		if not trafficModelAt(e.pos, 4) or (opts.excludeKeys and opts.excludeKeys[e.key]) then continue end
		fallback = fallback or e
		-- plan from the moment the approach will start
		local t0 = e.t + startDelay
		local probe = table.clone(e)
		probe.s, probe.t = e.s + e.speed * startDelay, t0
		local plan, meet = stage(probe, mode, speed, opts)
		local others = {}
		local x0, z0 = plan(t0)
		for _, o in TK.trafficNear(700, Vector3.new(x0, 1, z0)) do
			if o.key ~= e.key then table.insert(others, o) end
		end
		local clear = Rec.plannedPathClear(plan, t0, meet, others, clearance)
		if clear then
			return e, true
		end
	end
	return fallback, false
end

local hz = {n = 0, at = os.clock(), rate = 0}
RunService.Heartbeat:Connect(function()
	hz.n += 1
	local c = os.clock()
	if c - hz.at >= 0.5 then
		hz.rate, hz.n, hz.at = hz.n / (c - hz.at), 0, c
	end
end)

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

-- one staged hit (TK.hitTest retries it)
local function hitOnce(mode: string, speed: number, opts)
	local chassis, model = TK.car()
	assert(chassis and model and Rec, "hitTest: get in a car first (and PattayaRecovery must be installed)")
	local arcade = workspace:GetAttribute("CollisionModel") == "arcade"
	local START_DELAY = 0.3 -- s between the target choice and the start of the approach (placement + one frame)
	local target, clear = opts.target, true
	if not target then
		target, clear = pickTarget(mode, speed, opts, START_DELAY)
	end
	assert(target, "hitTest: no traffic car with a model nearby")
	-- isolate: every other car ghosts for this run (TestKit-only hook TK_HitTarget in PattayaTraffic). Default for
	-- TK.hitMatrix; otherwise only when no clear lane was found
	local ghostOthers = opts.isolate == true or not clear
	if ghostOthers then
		player:SetAttribute("TK_HitTarget", target.key)
	end
	local approachT = workspace:GetServerTimeNow() + START_DELAY
	local probe = table.clone(target)
	probe.s, probe.t = target.s + target.speed * (approachT - target.t), approachT
	local plan, meetAt = stage(probe, mode, speed, opts)
	local Y = 1 + 2.8 -- road + chassis ride height (traffic roads are at Y = 1)
	local function targetAt(t: number): Vector3
		local x, z = Rec.routePoint(target.route, target.s + target.speed * (t - target.t))
		return Vector3.new(x, 1, z)
	end
	local uprightsBefore = player:GetAttribute("Recovery_Uprights") or 0
	-- arcade: nothing on my car collides during the hold and the approach (scenery cannot slow it before the touch;
	-- the wheel rays still hold it up). Re-applied every step (the Humanoid may switch body parts back).
	local colliders = if arcade then carColliders(model) else {}
	local saved = {}
	for _, p in colliders do saved[p] = p.CanCollide end
	local function noCollide()
		for _, p in colliders do
			if p.Parent and p.CanCollide then p.CanCollide = false end
		end
	end
	local hitsBefore = nil
	local state = {done = false, reason = "", releaseAt = 0, frames = 0, startClock = 0, abort = nil}
	-- speed as the hit test sees it (after physics, Heartbeat): the lowest during the approach, and the last one
	local seen = {min = math.huge, last = 0}
	local hb = RunService.Heartbeat:Connect(function()
		if state.done or workspace:GetServerTimeNow() < approachT then return end
		local v = flat(chassis.AssemblyLinearVelocity).Magnitude
		seen.last = v
		seen.min = math.min(seen.min, v)
	end)
	local conn = onPreSim(function()
		if state.done then return end
		if arcade then noCollide() end
		local t = workspace:GetServerTimeNow()
		local count = player:GetAttribute("Recovery_HitCount") or 0
		if t < approachT then
			-- holding at the start: anything counted here is not the staged hit
			hitsBefore = count
			local x, z, dx, dz = plan(approachT)
			local p = Vector3.new(x, Y, z)
			chassis.CFrame = CFrame.lookAt(p, p + Vector3.new(dx, 0, dz))
			chassis.AssemblyLinearVelocity = Vector3.zero
			chassis.AssemblyAngularVelocity = Vector3.zero
			return
		end
		if state.frames == 0 then state.startClock = os.clock() end
		state.frames += 1
		if hitsBefore and count ~= hitsBefore then
			-- a hit registered: is it the staged one?
			local hp = player:GetAttribute("Recovery_LastHitPos")
			local tp = targetAt(t)
			local ok, why = Rec.acceptStagedHit({hitT = t, approachT = approachT, meet = meetAt,
				frameDt = 1 / math.max(hz.rate, 1), hitX = if typeof(hp) == "Vector3" then hp.X else math.huge,
				hitZ = if typeof(hp) == "Vector3" then hp.Z else math.huge, targetX = tp.X, targetZ = tp.Z})
			state.done, state.releaseAt = true, t
			state.reason = if ok then "hit" else "rejected: " .. tostring(why)
			if not ok and not ghostOthers and why and why:find("another car", 1, true) then
				state.abort = "another car hit"
			end
			return
		end
		-- not isolated: another car coming within 30 studs of mine before the touch aborts the run (TK.hitTest retries)
		if not ghostOthers and t < meetAt - 0.05 then
			for _, o in TK.trafficNear(opts.clearance or 30, chassis.Position) do
				if o.key ~= target.key then
					state.done, state.reason, state.abort = true, "traffic in the way", "traffic in the way"
					return
				end
			end
		end
		local x, z, dx, dz, gap = plan(t)
		if not arcade and gap <= 0.3 then
			state.done, state.reason, state.releaseAt = true, "contact", t -- physics takes the touch from here
		elseif arcade and gap < -4 then
			state.done, state.reason = true, "no hit registered (overlapping)"
		elseif t > meetAt + 2 or t - approachT > (opts.timeout or 10) then
			state.done, state.reason = true, "timeout"
		end
		local p = Vector3.new(x, Y, z)
		local dir = Vector3.new(dx, 0, dz).Unit
		chassis.CFrame = CFrame.lookAt(p, p + dir)
		chassis.AssemblyLinearVelocity = dir * speed
		chassis.AssemblyAngularVelocity = Vector3.zero
	end)
	while not state.done do RunService.Heartbeat:Wait() end
	conn:Disconnect()
	hb:Disconnect()
	for p, c in saved do
		if p.Parent then p.CanCollide = c end
	end
	local frameHz = if state.frames > 1 then (state.frames - 1) / math.max(os.clock() - state.startClock, 1e-3) else hz.rate
	local immediate = flat(chassis.AssemblyLinearVelocity).Magnitude
	local look0 = flat(chassis.CFrame.LookVector).Unit
	local minSpeed, minUp, minDist = immediate, 1, math.huge
	local t1 = os.clock()
	while os.clock() - t1 < 2 do
		RunService.Heartbeat:Wait()
		local v = flat(chassis.AssemblyLinearVelocity).Magnitude
		if os.clock() - t1 < 0.4 then minSpeed = math.min(minSpeed, v) end
		minUp = math.min(minUp, chassis.CFrame.UpVector.Y)
		minDist = math.min(minDist, flat(chassis.Position - targetAt(workspace:GetServerTimeNow())).Magnitude)
	end
	if ghostOthers then
		player:SetAttribute("TK_HitTarget", nil)
	end
	local look1 = flat(chassis.CFrame.LookVector).Unit
	local yaw = math.deg(math.atan2(look0:Cross(look1).Y, look0:Dot(look1)))
	local res = {mode = mode, speed = speed, angle = opts.angle, model = if arcade then "arcade" else "physical",
		reason = state.reason, abort = state.abort, yawDeg = yaw, minUp = minUp, flipped = minUp < 0.5, hz = frameHz,
		ghostedOthers = ghostOthers, vT = target.speed, targetKey = target.key, approachMin = if seen.min < math.huge then seen.min else nil,
		uprights = (player:GetAttribute("Recovery_Uprights") or 0) - uprightsBefore}
	if arcade then
		local good = state.reason == "hit"
		res.touched, res.onTarget = good, good
		res.tier = if good then player:GetAttribute("Recovery_LastHitTier") else nil
		res.vc = if good then player:GetAttribute("Recovery_LastHitVc") else nil
		res.before = if good then player:GetAttribute("Recovery_LastHitBefore") or speed else speed
		res.after = if good then player:GetAttribute("Recovery_LastHitAfter") or immediate else immediate
		res.measured = immediate
	else
		res.before, res.after, res.measured = speed, minSpeed, immediate
		res.touched = state.reason == "contact" and (minSpeed < speed * 0.9 or minDist < target.halfLen + 9)
		res.onTarget = res.touched
	end
	res.lossPct = (1 - (res.after or 0) / math.max(res.before or speed, 1)) * 100
	res.lastHit = player:GetAttribute("Recovery_LastHit")
	res.text = ("hitTest %s @%d%s [%s, %.0f Hz%s]: %s tier=%s vc=%s %d->%d (-%d%%) approach-min %s yaw=%d minUp=%.2f%s")
		:format(mode, speed, if opts.angle then " a" .. opts.angle elseif opts.offset then " off" .. opts.offset else "",
		res.model, frameHz, if ghostOthers then ", isolated" else "",
		if res.touched then "hit" else "MISSED (" .. state.reason .. ")", tostring(res.tier),
		if res.vc then tostring(math.floor(res.vc)) else "-", math.floor(res.before or 0), math.floor(res.after or 0),
		math.floor(res.lossPct + 0.5), if res.approachMin then tostring(math.floor(res.approachMin)) else "-",
		math.floor(yaw), minUp, if res.flipped then " FLIPPED" else "")
	return res
end

-- staged hit with retries: a run aborted by other traffic (not isolated) is tried again with another target,
-- up to opts.tries (3) times; res.tries says how many it took
function TK.hitTest(mode: string, speed: number, opts)
	opts = table.clone(opts or {})
	local tried = {}
	local res
	for i = 1, opts.tries or 3 do
		opts.excludeKeys = tried
		res = hitOnce(mode, speed, opts)
		res.tries = i
		tried[res.targetKey] = true
		if not res.abort or opts.target then
			return res
		end
		task.wait(1)
	end
	return res
end

-- the owner's table as staged hits (CollisionModel must be "arcade"; set it on the server first)
TK.HIT_MATRIX = {
	{"rear", 70}, {"rear", 100}, {"rear", 150}, {"rear", 200}, {"rear", 150, {offset = 2}},
	{"head", 100}, {"head", 150}, {"head", 200},
	{"side", 150, {angle = 5}}, {"side", 150, {angle = 20}}, {"side", 70, {angle = 25}}, {"side", 100, {angle = 10}},
}

-- one matrix run: PASS / FAIL per row
local function matrixRun(opts, cfg, label: string)
	local rows, pass = {}, 0
	for i, row in opts.rows or TK.HIT_MATRIX do
		local mode, speed, o = row[1], row[2], table.clone(row[3] or {})
		if o.isolate == nil then o.isolate = opts.isolate ~= false end
		local ok, res = pcall(TK.hitTest, mode, speed, o)
		local line
		if not ok then
			line = ("FAIL %s%2d %s @%d: error %s"):format(label, i, mode, speed, tostring(res))
		else
			local want = Rec.expectedStaged(mode, speed, o.angle, res.vT or 45, cfg)
			local problems = {}
			if not res.touched then table.insert(problems, "no staged hit (" .. res.reason .. ")") end
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
			if res.touched and (res.before or 0) < speed * 0.9 then
				table.insert(problems, ("speed at the hit %d of %d (lowest on the approach %s)"):format(
					math.floor(res.before or 0), speed, if res.approachMin then tostring(math.floor(res.approachMin)) else "-"))
			end
			if res.minUp < 0.85 then table.insert(problems, ("minUp %.2f"):format(res.minUp)) end
			local good = #problems == 0
			if good then pass += 1 end
			line = ("%s %s%2d %s | table %s %d%%%s%s"):format(if good then "PASS" else "FAIL", label, i, res.text,
				want.tier, math.floor(want.loss * 100 + 0.5), if (res.tries or 1) > 1 then (" | tries %d"):format(res.tries) else "",
				if good then "" else " | " .. table.concat(problems, "; "))
		end
		print(line)
		table.insert(rows, line)
		task.wait(opts.gap or 1.5)
	end
	return pass, rows
end

-- TK.hitMatrix(opts?) -> summary, rows   runs TK.HIT_MATRIX (opts.rows to choose) opts.runs (1) times and prints a
-- PASS / FAIL line per row against the owner's table, a summary per run and an overall line. Rows are isolated
-- (every other traffic car ghosts; opts.isolate = false runs them in real traffic with retries).
-- A row passes when: the hit is the staged one; the tier is the table's for the geometry and the target's real
-- speed (PattayaRecovery.expectedStaged); the loss is within opts.tol (0.05) (head-on: near stop); the speed at the
-- hit is >= 90 % of the planned speed; no flip (minUp >= 0.85).
function TK.hitMatrix(opts)
	opts = opts or {}
	assert(Rec, "hitMatrix: PattayaRecovery missing")
	assert(workspace:GetAttribute("CollisionModel") == "arcade", "hitMatrix: set CollisionModel = \"arcade\" on the server")
	local cfg = Rec.config()
	local runs = opts.runs or 1
	local total = #(opts.rows or TK.HIT_MATRIX)
	local all, perRun, allPass = {}, {}, 0
	for r = 1, runs do
		local pass, rows = matrixRun(opts, cfg, if runs > 1 then ("r%d "):format(r) else "")
		for _, l in rows do table.insert(all, l) end
		allPass += pass
		local line = ("hitMatrix run %d: %d/%d PASS (Heartbeat %.0f Hz%s)"):format(r, pass, total, hz.rate,
			if opts.isolate == false then ", real traffic" else ", isolated")
		print(line)
		table.insert(perRun, line)
	end
	local summary = ("hitMatrix: %d/%d PASS over %d run%s%s"):format(allPass, total * runs, runs,
		if runs > 1 then "s" else "", if allPass == total * runs then " - REPEATABLE" else "")
	print(summary)
	return summary, all, perRun
end

function TK.stopAll()
	for _, h in TK.handles do
		if type(h) == "table" and h.stop then h:stop("stopAll") end
	end
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
