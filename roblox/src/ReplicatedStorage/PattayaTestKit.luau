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
		for _, v in p do table.insert(out, v) end
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
	for i, p in pts do
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
			for _, p in pit do add(p, pitSpeed) end
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
-- traffic cars non-solid for this client (the drive tests run "traffic made non-solid")
function TK.ghostTraffic(on: boolean)
	local folder = workspace:FindFirstChild("PattayaTraffic")
	if not folder then return 0 end
	local n = 0
	local function set(d: Instance)
		if d:IsA("BasePart") then
			d.CanCollide = not on
			n += 1
		end
	end
	for _, d in folder:GetDescendants() do set(d) end
	if TK.trafficConn then TK.trafficConn:Disconnect() TK.trafficConn = nil end
	if on then TK.trafficConn = folder.DescendantAdded:Connect(set) end
	return n
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
	"EventActive", "Equalised", "SpeedCap", "RoadFight", "NearMissCombo"}

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
