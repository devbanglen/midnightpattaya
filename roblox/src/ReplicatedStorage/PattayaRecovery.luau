-- PattayaRecovery: shared config and pure decision functions for the Recovery Kit (auto-upright, manual R rules,
-- stuck detection, server rescue) and the arcade traffic-hit model. docs/RECOVERY_AND_COLLISION.md
-- Used by CarController (client), PattayaTraffic (client), PattayaRecoveryServer (server) and PattayaTestKit (dev).
--
-- Every decision function here takes plain numbers / tables (no Roblox types), so tools/qa/tests/test_recovery.py
-- runs them in the luau CLI. Settings are workspace attributes read live through R.get(name); the defaults below
-- apply when an attribute is missing or has the wrong type.
local R = {}

R.DEFAULTS = {
	-- master switches -------------------------------------------------------------------------------------------
	Recovery_Enabled = true,       -- false = today's behaviour (unlimited R, lift 6, no auto-upright, no rescue)
	Recovery_AutoUpright = true,
	Recovery_AntiStuck = true,      -- stuck / off-road prompt and the server rescue
	Recovery_RescueAuto = false,    -- automatic rescue after Recovery_RescueAutoTime with no change (owner: prompt only)
	CollisionModel = "physical",    -- "physical" = today's solid traffic boxes; "arcade" = scripted hits (Phase 2)
	-- auto-upright -----------------------------------------------------------------------------------------------
	Recovery_UprightDelay = 1.5,    -- s upside down (up.Y < 0), any speed
	Recovery_TiltDelay = 1.5,       -- s tilted (up.Y < Recovery_TiltUpY) and slower than Recovery_TiltSlowSpeed
	Recovery_TiltUpY = 0.5,         -- 60 degrees of tilt
	Recovery_TiltSlowSpeed = 15,    -- studs/s
	Recovery_UprightTime = 0.35,    -- s of the turn-over animation
	Recovery_UprightLift = 2.5,     -- studs
	Recovery_UprightKeepVel = 0.2,  -- fraction of horizontal velocity kept
	Recovery_EnterGrace = 0.5,      -- s after getting in before anything triggers
	-- manual R --------------------------------------------------------------------------------------------------
	Recovery_ResetCooldown = 2,     -- s between two R resets (0 = unlimited)
	Recovery_ResetMinTiltDeg = 30,  -- R works when tilted more than this ...
	Recovery_ResetMaxSpeed = 10,    -- ... or slower than this (studs/s)
	Recovery_ResetLift = 3,         -- studs (legacy R lifts 6)
	-- stuck / off-road / fallen ----------------------------------------------------------------------------------
	Recovery_StuckTime = 4,         -- s of throttle held ...
	Recovery_StuckDist = 6,         -- ... while moving less than this (studs, from where it started)
	Recovery_StuckThrottle = 0.5,   -- |throttle| that counts as "trying to drive"
	Recovery_OffRoadTime = 6,       -- s with no road under any wheel ...
	Recovery_OffRoadSpeed = 20,     -- ... while slower than this
	Recovery_FallY = -30,           -- world Y below which the car has fallen off the map (roads sit at Y ~ 1)
	Recovery_RescueHold = 1,        -- s to hold R on the stuck prompt
	Recovery_RescueAutoTime = 8,    -- s (only with Recovery_RescueAuto)
	-- server rescue ----------------------------------------------------------------------------------------------
	Recovery_RescueCooldown = 10,   -- s between rescues (from the end of the last one)
	Recovery_RescueMaxSpeed = 25,   -- studs/s the server must see (horizontal, from position)
	Recovery_RescueMaxPath = 300,   -- studs of own trail the rescue may retrace
	Recovery_RescueGlide = 60,      -- studs/s of the tow back along the trail (jobs use Recovery_RescueGlideJob)
	Recovery_RescueGlideJob = 45,   -- below the jobs bump detector's 55 studs/s drop
	Recovery_RescueHoldRace = 1,    -- s anchored at the spot in races
	Recovery_RescueHoldFree = 0.5,  -- s anchored elsewhere
	Recovery_RescueGhost = 2,       -- s of client traffic ghost after a rescue
	Recovery_GateMargin = 25,       -- studs: a rescue spot stays this far before the next race gate / checkpoint
	-- arcade traffic hits (Phase 2) ------------------------------------------------------------------------------
	Arcade_ScrapeVc = 15,           -- vc below this = scrape
	Arcade_ScrapeAngle = 15,        -- or an approach shallower than this (degrees) = scrape
	Arcade_ScrapeLoss = 0.08,
	Arcade_ScrapeYaw = 5,
	Arcade_HeavyVc = 45,            -- vc from here = heavy (between scrape and this = light)
	Arcade_LightLoss = 0.20,
	Arcade_LightYawMin = 8,
	Arcade_LightYawMax = 15,
	Arcade_LightControl = 0.25,
	Arcade_LightSteer = 0.7,
	Arcade_HeavyLossMin = 0.45,
	Arcade_HeavyLossMax = 0.70,
	Arcade_HeavyYawMin = 45,
	Arcade_HeavyYawMax = 120,
	Arcade_HeavyControlMin = 0.6,
	Arcade_HeavyControlMax = 1.2,
	Arcade_HeavySteer = 0.3,
	Arcade_HeavyFullVc = 130,       -- vc at which the heavy values reach their maximum
	Arcade_HeadOnVc = 90,
	Arcade_HeadOnAngle = 30,        -- degrees: facing each other within this
	Arcade_HeadOnLoss = 0.85,
	Arcade_HeadOnYaw = 10,
	Arcade_HeadOnControl = 1.0,
	Arcade_HeadOnBounce = 10,       -- studs/s back
	Arcade_HitGhost = 1.5,          -- s a traffic car stays ghosted after hitting it (no double hit); it also stays
	                                -- ghosted while it still overlaps my car (no repeat hit while passing through it)
	Arcade_MaxPush = 2,             -- studs of push-out
	-- anti-roll, part of the arcade hit response only (never the base car physics): from the touch until the scripted
	-- window (+ Arcade_AntiRollExtra) ends, the chassis keeps the up axis it had at the touch; yaw stays free
	Arcade_AntiRoll = true,
	Arcade_AntiRollExtra = 0.25,    -- s after the hit window
	Arcade_AntiRollTorque = 1000000, -- AlignOrientation.MaxTorque
	Arcade_AntiRollResponse = 120,  -- AlignOrientation.Responsiveness
	Arcade_AntiRollSnapDeg = 3,     -- per step: put the up axis back when it drifted more than this
	-- server check of the TrafficHit report (jobs bump)
	Arcade_HitReportGap = 1,        -- s between two reports
	Arcade_HitMinSpeed = 40,        -- studs/s the server must have seen just before the hit
	Arcade_HitTrafficRadius = 45,   -- studs: a traffic car must be this close at that server time
}

local function workspaceAttr(name: string): any
	local ws = (workspace :: any)
	if ws == nil then
		return nil
	end
	return ws:GetAttribute(name)
end
R._attr = workspaceAttr -- tests replace this

function R.get(name: string): any
	local d = R.DEFAULTS[name]
	local v = R._attr(name)
	if v == nil or (d ~= nil and type(v) ~= type(d)) then
		return d
	end
	return v
end

function R.enabled(): boolean
	return R.get("Recovery_Enabled") ~= false
end

function R.arcade(): boolean
	return R.get("CollisionModel") == "arcade"
end

-- a snapshot of every setting (one table per call: the decision functions below read from it)
function R.config(): {[string]: any}
	local c = {}
	for k in R.DEFAULTS do
		c[k] = R.get(k)
	end
	return c
end

-- near miss (PattayaTraffic): side clearance and minimum speed, and the shortest gap between two awards
R.NEAR_GAP, R.NEAR_SPEED, R.NEAR_INTERVAL = 7, 70, 0.6

-- road part names (same list as PattayaTestKit.ROAD_NAMES)
R.ROAD_NAMES = {Road = true, Junction = true, Dash = true, Centre = true, Asphalt = true, PitLane = true,
	TransitionRoad = true, ServiceRoad = true, Parking = true, EdgeLine = true, PitLine = true}

-- player car collider (RaceCarServer Chassis 7 x 1.6 x 15) and the traffic colliders (PattayaTraffic SHAPES, by kind)
R.CAR_HALF_WID, R.CAR_HALF_LEN = 3.5, 7.5
R.TRAFFIC_SHAPES = {[0] = {len = 14, wid = 6.6, h = 2.4}, [1] = {len = 16, wid = 7, h = 2.6}, [2] = {len = 16, wid = 7.2, h = 6}}

local function clamp(x: number, a: number, b: number): number
	return if x < a then a elseif x > b then b else x
end
local function lerp(a: number, b: number, t: number): number
	return a + (b - a) * t
end

-- auto-upright ------------------------------------------------------------------------------------------------------
-- st = {upside = s, tilt = s}. Call every frame. blocked (anchored, just got in, mid-animation, rescue) resets the
-- timers. Returns true on the frame the car should be turned back over.
function R.uprightTick(st, upY: number, speed: number, dt: number, blocked: boolean, cfg): boolean
	if blocked then
		st.upside, st.tilt = 0, 0
		return false
	end
	st.upside = if upY < 0 then (st.upside or 0) + dt else 0
	st.tilt = if upY < cfg.Recovery_TiltUpY and speed < cfg.Recovery_TiltSlowSpeed then (st.tilt or 0) + dt else 0
	if st.upside >= cfg.Recovery_UprightDelay or st.tilt >= cfg.Recovery_TiltDelay then
		st.upside, st.tilt = 0, 0
		return true
	end
	return false
end

-- manual R: ok, reason ("cooldown" | "level" | nil)
function R.resetAllowed(now: number, lastAt: number?, upY: number, speed: number, cfg): (boolean, string?)
	local cd = cfg.Recovery_ResetCooldown
	if lastAt and cd > 0 and now - lastAt < cd then
		return false, "cooldown"
	end
	local tilted = upY < math.cos(math.rad(cfg.Recovery_ResetMinTiltDeg))
	if not tilted and speed >= cfg.Recovery_ResetMaxSpeed then
		return false, "level"
	end
	return true, nil
end

function R.cooldownLeft(now: number, lastAt: number?, cd: number): number
	if not lastAt then
		return 0
	end
	return math.max(0, cd - (now - lastAt))
end

-- stuck: throttle (or reverse) held while the car stays within Recovery_StuckDist of where that started.
-- st = {ax, az, t}. Returns true once it has lasted Recovery_StuckTime.
function R.stuckTick(st, x: number, z: number, throttleAbs: number, dt: number, cfg): boolean
	if throttleAbs <= cfg.Recovery_StuckThrottle then
		st.ax, st.az, st.t = nil, nil, 0
		return false
	end
	if st.ax == nil then
		st.ax, st.az, st.t = x, z, 0
	end
	local dx, dz = x - st.ax, z - st.az
	if dx * dx + dz * dz > cfg.Recovery_StuckDist * cfg.Recovery_StuckDist then
		st.ax, st.az, st.t = x, z, 0
		return false
	end
	st.t += dt
	return st.t >= cfg.Recovery_StuckTime
end

-- off-road: no wheel on a road part for Recovery_OffRoadTime while slow (driving fast on the beach is allowed) and,
-- when throttleAbs is given, while trying to drive (a car parked on the sand with no input is not stuck)
function R.offRoadTick(st, onRoad: boolean, speed: number, dt: number, cfg, throttleAbs: number?): boolean
	if onRoad or speed >= cfg.Recovery_OffRoadSpeed
		or (throttleAbs ~= nil and throttleAbs <= cfg.Recovery_StuckThrottle) then
		st.t = 0
		return false
	end
	st.t = (st.t or 0) + dt
	return st.t >= cfg.Recovery_OffRoadTime
end

function R.fallen(y: number, cfg): boolean
	return y < cfg.Recovery_FallY
end

-- rescue spot choice (server) ----------------------------------------------------------------------------------------
-- crumbs: the server's own samples of this car, oldest first: {t, x, y, z, hx, hz, speed, up}. The rescue only ever
-- goes back to a place the car has already been, so it can never move a player forward along a route.
-- Walks back from the newest crumb, adding up the trail length from (curX, curZ); the first crumb that is old
-- enough, was driven normally (speed, upright), is far enough from the stuck spot and passes allow(crumb) wins.
-- Returns index, trail length (or nil when nothing within maxPath qualifies).
function R.pickCrumb(crumbs, now: number, curX: number, curZ: number, opts, allow: ((any) -> boolean)?): (number?, number)
	local minAge = opts.minAge or 1
	local minSpeed = opts.minSpeed or 10
	local minUp = opts.minUp or 0.8
	local minDist = opts.minDist or 8
	local maxPath = opts.maxPath or 300
	local px, pz = curX, curZ
	local path = 0
	for i = #crumbs, 1, -1 do
		local c = crumbs[i]
		path += math.sqrt((c.x - px) ^ 2 + (c.z - pz) ^ 2)
		px, pz = c.x, c.z
		if path > maxPath then
			return nil, path
		end
		local dx, dz = c.x - curX, c.z - curZ
		if now - c.t >= minAge and c.speed >= minSpeed and c.up >= minUp and dx * dx + dz * dz >= minDist * minDist
			and (allow == nil or allow(c)) then
			return i, path
		end
	end
	return nil, path
end

-- loop-race gate clamp: (relX, relZ) = the spot in the next gate's object space (forward = -Z, so "before the gate"
-- is +Z). The spot must not be at or past the gate inside its corridor, nor within margin before it.
function R.gateAllows(relX: number, relZ: number, halfWidth: number, cfg): boolean
	if math.abs(relX) > halfWidth + 12 then
		return true
	end
	return relZ >= cfg.Recovery_GateMargin or relZ < -80
end

-- point checkpoints (sprint / street races: hit within 26 studs): keep 26 + margin away from the next one
function R.cpAllows(dx: number, dz: number, cfg): boolean
	local r = 26 + cfg.Recovery_GateMargin
	return dx * dx + dz * dz >= r * r
end

-- unit tangent of a flat polyline {x1, z1, x2, z2, ...} at arc length s, as (tx, tz)
function R.tangentAt(flat: {number}, s: number): (number, number)
	local acc = 0
	local n = #flat // 2
	local tx, tz = 0, -1
	for i = 1, n - 1 do
		local ax, az = flat[2 * i - 1], flat[2 * i]
		local bx, bz = flat[2 * i + 1], flat[2 * i + 2]
		local len = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
		if len > 1e-6 then
			tx, tz = (bx - ax) / len, (bz - az) / len
			if acc + len >= s then
				return tx, tz
			end
		end
		acc += len
	end
	return tx, tz
end

-- the road direction (tx, tz) flipped to agree with the heading the car had (hx, hz)
function R.alignHeading(tx: number, tz: number, hx: number, hz: number): (number, number)
	if tx * hx + tz * hz < 0 then
		return -tx, -tz
	end
	return tx, tz
end

-- arcade traffic hits ---------------------------------------------------------------------------------------------
-- 2D oriented-box overlap (separating axis test). Box = centre (cx, cz), unit forward (fx, fz), half width hw
-- (along right = (-fz, fx)) and half length hl (along forward). Returns hit, depth, and the contact normal (nx, nz)
-- pointing from box B towards box A.
function R.obbOverlap(ax: number, az: number, afx: number, afz: number, ahw: number, ahl: number,
	bx: number, bz: number, bfx: number, bfz: number, bhw: number, bhl: number): (boolean, number, number, number)
	local axes = {{-afz, afx}, {afx, afz}, {-bfz, bfx}, {bfx, bfz}}
	local dx, dz = ax - bx, az - bz
	local best, bnx, bnz = math.huge, 0, 0
	for _, u in axes do
		local ux, uz = u[1], u[2]
		local ra = ahw * math.abs(-afz * ux + afx * uz) + ahl * math.abs(afx * ux + afz * uz)
		local rb = bhw * math.abs(-bfz * ux + bfx * uz) + bhl * math.abs(bfx * ux + bfz * uz)
		local d = dx * ux + dz * uz
		local o = ra + rb - math.abs(d)
		if o <= 0 then
			return false, 0, 0, 0
		end
		if o < best then
			best = o
			local sgn = if d >= 0 then 1 else -1
			bnx, bnz = ux * sgn, uz * sgn
		end
	end
	return true, best, bnx, bnz
end

-- overlap of the two boxes along each of the 4 axes: {{o, ux, uz, d}} (o <= 0 on an axis = separated there)
local function axisOverlaps(ax: number, az: number, afx: number, afz: number, ahw: number, ahl: number,
	bx: number, bz: number, bfx: number, bfz: number, bhw: number, bhl: number)
	local out = {}
	local dx, dz = ax - bx, az - bz
	for _, u in {{-afz, afx}, {afx, afz}, {-bfz, bfx}, {bfx, bfz}} do
		local ux, uz = u[1], u[2]
		local ra = ahw * math.abs(-afz * ux + afx * uz) + ahl * math.abs(afx * ux + afz * uz)
		local rb = bhw * math.abs(-bfz * ux + bfx * uz) + bhl * math.abs(bfx * ux + bfz * uz)
		local d = dx * ux + dz * uz
		table.insert(out, {ra + rb - math.abs(d), ux, uz, d})
	end
	return out
end

-- swept version: box A moved from (pax, paz) to (ax, az) since the last frame; tests in steps of <= 1 stud so a low
-- frame rate cannot skip through a car. Returns hit, depth, nx, nz, and the A centre where the hit was found.
-- The contact normal is the face the boxes actually met on: of the axes that still separated them one step
-- earlier, the one that closed last (time of impact). The smallest-overlap axis alone is wrong once a 30 FPS step
-- pushes a corner deep into a long side: it picked the length axis on a 20 degree side hit and called it a scrape
-- (Studio 2026-10-21, docs/RECOVERY_AND_COLLISION.md section 10).
function R.sweptOverlap(pax: number?, paz: number?, ax: number, az: number, afx: number, afz: number, ahw: number,
	ahl: number, bx: number, bz: number, bfx: number, bfz: number, bhw: number, bhl: number)
	local steps = 1
	if pax and paz then
		local move = math.sqrt((ax - pax) ^ 2 + (az - paz) ^ 2)
		if move > 60 then
			pax, paz = nil, nil -- a teleport, not a sweep
		else
			steps = math.clamp(math.ceil(move), 1, 60)
		end
	end
	local before = if pax then axisOverlaps(pax, paz :: number, afx, afz, ahw, ahl, bx, bz, bfx, bfz, bhw, bhl) else nil
	for i = 1, steps do
		local t = i / steps
		local cx = if pax then lerp(pax, ax, t) else ax
		local cz = if paz then lerp(paz :: number, az, t) else az
		local now = axisOverlaps(cx, cz, afx, afz, ahw, ahl, bx, bz, bfx, bfz, bhw, bhl)
		local hit = true
		for _, a in now do
			if a[1] <= 0 then hit = false break end
		end
		if hit then
			local pick = nil
			if before then
				local lastClose = -math.huge
				for k, a in now do
					local o0 = before[k][1]
					if o0 <= 0 then
						local tk = -o0 / math.max(a[1] - o0, 1e-9)
						if tk > lastClose then lastClose, pick = tk, k end
					end
				end
			end
			if not pick then -- no earlier sample (or already overlapping): the smallest overlap
				local best = math.huge
				for k, a in now do
					if a[1] < best then best, pick = a[1], k end
				end
			end
			local a = now[pick :: number]
			local sgn = if a[4] >= 0 then 1 else -1
			return true, a[1], a[2] * sgn, a[3] * sgn, cx, cz
		end
		before = now
	end
	return false, 0, 0, 0, ax, az
end

-- closing speed: how fast my car moves into the traffic car along the contact normal (n points from the traffic car
-- to me), counting the traffic car's own velocity. Also returns the approach angle in degrees (0 = sliding along
-- the contact face, 90 = straight into it) and the relative speed.
function R.closingSpeed(vx: number, vz: number, tvx: number, tvz: number, nx: number, nz: number): (number, number, number)
	local rx, rz = vx - tvx, vz - tvz
	local rel = math.sqrt(rx * rx + rz * rz)
	local vc = math.max(0, -(rx * nx + rz * nz))
	local angle = if rel > 1e-6 then math.deg(math.asin(clamp(vc / rel, 0, 1))) else 0
	return vc, angle, rel
end

-- hit = {vc, approachDeg, facingDot (my heading . traffic heading, -1 = head-on), side (+1 = the traffic car is on my
-- right, -1 = left), front (true = it hit my front half)}. Returns the scripted result:
-- {tier = "scrape" | "light" | "heavy" | "headon", loss (fraction of speed), yaw (degrees, + = nose turns left),
--  control (s of reduced steering), steer (steering scale during it), slide (drift grip during it), bounce (studs/s)}
function R.classifyHit(hit, cfg)
	local vc, angle = hit.vc, hit.approachDeg or 90
	local side = if (hit.side or 1) >= 0 then 1 else -1
	local headOnDot = -math.cos(math.rad(cfg.Arcade_HeadOnAngle))
	if vc >= cfg.Arcade_HeadOnVc and (hit.facingDot or 1) <= headOnDot then
		return {tier = "headon", loss = cfg.Arcade_HeadOnLoss, yaw = side * cfg.Arcade_HeadOnYaw,
			control = cfg.Arcade_HeadOnControl, steer = cfg.Arcade_HeavySteer, slide = true,
			bounce = cfg.Arcade_HeadOnBounce}
	end
	if vc < cfg.Arcade_ScrapeVc or angle < cfg.Arcade_ScrapeAngle then
		-- nose turns away from the traffic car
		return {tier = "scrape", loss = cfg.Arcade_ScrapeLoss, yaw = side * cfg.Arcade_ScrapeYaw * clamp(vc / 15, 0, 1),
			control = 0, steer = 1, slide = false, bounce = 0}
	end
	if vc < cfg.Arcade_HeavyVc then
		local t = clamp((vc - cfg.Arcade_ScrapeVc) / math.max(cfg.Arcade_HeavyVc - cfg.Arcade_ScrapeVc, 1), 0, 1)
		return {tier = "light", loss = cfg.Arcade_LightLoss,
			yaw = side * lerp(cfg.Arcade_LightYawMin, cfg.Arcade_LightYawMax, t),
			control = cfg.Arcade_LightControl, steer = cfg.Arcade_LightSteer, slide = false, bounce = 0}
	end
	local t = clamp((vc - cfg.Arcade_HeavyVc) / math.max(cfg.Arcade_HeavyFullVc - cfg.Arcade_HeavyVc, 1), 0, 1)
	-- front half hit: the nose is pushed away; rear half: the tail is pushed away (nose turns towards), and spins more
	local sign = if hit.front == false then -side else side
	local yaw = lerp(cfg.Arcade_HeavyYawMin, cfg.Arcade_HeavyYawMax, t)
	if hit.front == false then
		yaw = math.min(yaw * 1.25, cfg.Arcade_HeavyYawMax)
	end
	return {tier = "heavy", loss = lerp(cfg.Arcade_HeavyLossMin, cfg.Arcade_HeavyLossMax, t), yaw = sign * yaw,
		control = lerp(cfg.Arcade_HeavyControlMin, cfg.Arcade_HeavyControlMax, t), steer = cfg.Arcade_HeavySteer,
		slide = true, bounce = 0}
end

-- new horizontal velocity after a hit: speed cut by loss; for a bounce (head-on) the part still closing on the
-- traffic car is removed and `bounce` studs/s added away from it. (vx, vz) my velocity, (nx, nz) from traffic to me.
function R.impactVelocity(vx: number, vz: number, nx: number, nz: number, res): (number, number)
	local k = 1 - res.loss
	local wx, wz = vx * k, vz * k
	if res.bounce > 0 then
		local closing = -(wx * nx + wz * nz)
		if closing > 0 then
			wx, wz = wx + nx * closing, wz + nz * closing
		end
		wx, wz = wx + nx * res.bounce, wz + nz * res.bounce
	end
	return wx, wz
end

-- The whole arcade touch test in world numbers (the same maths PattayaTraffic runs every frame, so the luau CLI
-- tests reproduce Studio cases from recorded positions and velocities).
-- me = {x, z, lx, lz (unit heading), vx, vz}; tr = {x, z, lx, lz (unit heading), speed, halfWid, halfLen}
-- prevX / prevZ: my centre in the traffic car's frame last frame (nil = no sweep).
-- Traffic frame = CFrame.lookAt(traffic, traffic + heading): +X = right = heading x up = (-lz, lx), forward = -Z.
-- Returns info (nil when they do not touch) and my centre in the traffic frame (store it for the next sweep).
-- info = {vc, approachDeg, rel, facingDot, side (+1 = the traffic car is on my right), front (it touched my front
-- half), nx, nz (world normal from the traffic car to me), depth}
function R.hitFromWorld(me, tr, prevX: number?, prevZ: number?)
	local rx, rz = -tr.lz, tr.lx -- traffic right
	local dx, dz = me.x - tr.x, me.z - tr.z
	local relX = dx * rx + dz * rz
	local relZ = -(dx * tr.lx + dz * tr.lz)
	local fx = me.lx * rx + me.lz * rz
	local fz = -(me.lx * tr.lx + me.lz * tr.lz)
	local fm = math.sqrt(fx * fx + fz * fz)
	if fm < 1e-6 then
		fx, fz = 0, -1
	else
		fx, fz = fx / fm, fz / fm
	end
	local hit, depth, onx, onz = R.sweptOverlap(prevX, prevZ, relX, relZ, fx, fz, R.CAR_HALF_WID, R.CAR_HALF_LEN,
		0, 0, 0, -1, tr.halfWid, tr.halfLen)
	if not hit then
		return nil, relX, relZ
	end
	-- object (x, z) -> world: x along right, z along -heading
	local nx, nz = onx * rx - onz * tr.lx, onx * rz - onz * tr.lz
	local nm = math.sqrt(nx * nx + nz * nz)
	if nm < 1e-6 then
		nx, nz = -me.lx, -me.lz
	else
		nx, nz = nx / nm, nz / nm
	end
	local vc, approach, rel = R.closingSpeed(me.vx, me.vz, tr.lx * tr.speed, tr.lz * tr.speed, nx, nz)
	-- the traffic car in my frame: right = (-lz, lx), front = heading
	local ox, oz = tr.x - me.x, tr.z - me.z
	local otherX = ox * -me.lz + oz * me.lx
	local otherFwd = ox * me.lx + oz * me.lz
	return {vc = vc, approachDeg = approach, rel = rel, facingDot = me.lx * tr.lx + me.lz * tr.lz,
		side = if otherX >= 0 then 1 else -1, front = otherFwd > 0, nx = nx, nz = nz, depth = depth}, relX, relZ
end

-- do my car and a traffic car overlap, with `margin` studs added to both boxes? (same frame maths as hitFromWorld;
-- PattayaTraffic keeps a hit traffic car ghosted while this holds, so a car driving through it is not hit again)
function R.carsOverlap(me, tr, margin: number): boolean
	local rx, rz = -tr.lz, tr.lx
	local dx, dz = me.x - tr.x, me.z - tr.z
	local relX = dx * rx + dz * rz
	local relZ = -(dx * tr.lx + dz * tr.lz)
	local fx = me.lx * rx + me.lz * rz
	local fz = -(me.lx * tr.lx + me.lz * tr.lz)
	local fm = math.sqrt(fx * fx + fz * fz)
	if fm < 1e-6 then
		fx, fz = 0, -1
	else
		fx, fz = fx / fm, fz / fm
	end
	local hit = R.obbOverlap(relX, relZ, fx, fz, R.CAR_HALF_WID + margin, R.CAR_HALF_LEN + margin, 0, 0, 0, -1,
		tr.halfWid + margin, tr.halfLen + margin)
	return hit
end

-- yaw only (arcade hit anti-roll): the chassis look (lx, ly, lz) turned into the plane normal to the held up axis
-- (ux, uy, uz), as a unit vector; nil when the look is (nearly) parallel to that axis
function R.yawOnlyLook(lx: number, ly: number, lz: number, ux: number, uy: number, uz: number): (number?, number?, number?)
	local d = lx * ux + ly * uy + lz * uz
	local px, py, pz = lx - ux * d, ly - uy * d, lz - uz * d
	local m = math.sqrt(px * px + py * py + pz * pz)
	if m < 1e-4 then
		return nil, nil, nil
	end
	return px / m, py / m, pz / m
end

-- the angular velocity (ax, ay, az) with only its part about the held up axis kept (yaw)
function R.yawOnlyRate(ax: number, ay: number, az: number, ux: number, uy: number, uz: number): (number, number, number)
	local d = ax * ux + ay * uy + az * uz
	return ux * d, uy * d, uz * d
end

-- the angle (degrees) between the current up axis and the held one
function R.tiltFrom(ux: number, uy: number, uz: number, hx: number, hy: number, hz: number): number
	return math.deg(math.acos(clamp(ux * hx + uy * hy + uz * hz, -1, 1)))
end

-- Near miss, one traffic car per frame (PattayaTraffic): my car's centre (relX, relZ) in that car's frame
-- (forward = -Z). st = {side, near} kept per traffic car; ghost = the car is a ghost this frame. Returns true when
-- this frame completes a near miss: my car went from one end of it to the other within R.NEAR_GAP studs of its
-- side, never touching it, faster than R.NEAR_SPEED, at least R.NEAR_INTERVAL s after the last one.
function R.nearMissStep(st, relX: number, relZ: number, halfWid: number, halfLen: number, ghost: boolean,
	carSpeed: number, t: number, lastNearAt: number): boolean
	local lateral = math.abs(relX) - halfWid - R.CAR_HALF_WID
	local side = if relZ < -halfLen then -1 elseif relZ > halfLen then 1 else 0
	local fire = false
	if side ~= 0 then
		if st.side and st.side ~= 0 and side ~= st.side and st.near and carSpeed > R.NEAR_SPEED
			and t - lastNearAt > R.NEAR_INTERVAL then
			fire = true
		end
		st.side = side
		st.near = nil
	elseif lateral > 0 and lateral < R.NEAR_GAP and not ghost then
		st.near = if st.near == nil then true else st.near
	elseif lateral <= 0 then
		st.near = false -- touched / overlapping: not a near miss
	end
	return fire
end

-- yaw-rate profile of the scripted spin: omega(t) = w0 * (1 - t / T) for t < T integrates to the kick angle.
-- Returns T (s) and w0 (rad/s, + = left).
function R.spinProfile(yawDeg: number, control: number): (number, number)
	local T = clamp(control * 0.6, 0.15, 0.6)
	return T, 2 * math.rad(yawDeg) / T
end

-- deterministic traffic: ONE implementation for PattayaTraffic.client (what is drawn and hit), TestKit and the
-- server's TrafficHit check ---------------------------------------------------------------------------------------
-- Studio rounds 3-5 (2026-10-21): the client computed the loops with Vector3 maths. Roblox Vector3 components are
-- 32-bit floats, so its loop lengths differed from these double-precision ones by up to ~0.01 studs, and a car's
-- arc s = phase + t * speed (t = epoch seconds, ~1.8e9) wraps ~9 million times: the same car key was drawn
-- ~700 studs (median) from where TestKit / the server computed it. Now PattayaTraffic uses these functions too, so
-- key, position and heading agree by construction (tools/qa/tests/test_recovery.py TrafficKeys).
R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z = 20000, 0 -- PattayaBuilder.ORIGIN
R.TRAFFIC_ROAD_Y = 1

-- Lane polyline cleanup (round 6, route 26): the generated loops are lane offsets of the road centrelines, and at
-- most corners the inner offset overshoots and comes back ("swallowtail": forward, a few studs BACK, forward again;
-- 333 of them in pattaya_wide). A car on such a stretch drives backwards for a moment and is drawn facing backwards,
-- so a rear-end there was classified head-on (rear 70: vc 110) and the arc distance overstated the real gap (hit
-- 0.38 s early). A short reversed segment B-C between A-B and C-D that leave in roughly the same direction is
-- replaced by the crossing point of A-B and C-D, or by C projected onto A-B when that is within R.LANE_CLEAN.proj
-- studs. Genuine U-turns (C-D heads back) and ordinary corners are kept.
R.LANE_CLEAN = {maxSeg = 30, turnDeg = 100, fwdDot = -0.5, proj = 10}
-- TestKit's staged hits: the whole approach within R.STAGE_BEND_DEG of one direction, and for side hits the target's
-- heading around the touch within R.SIDE_STEADY_DEG (stagePlan's third and fourth results)
R.STAGE_BEND_DEG, R.SIDE_STEADY_DEG = 15, 1

local function segCross(ax: number, az: number, bx: number, bz: number, cx: number, cz: number, dx: number,
	dz: number): (number?, number?)
	local rx, rz = bx - ax, bz - az
	local sx, sz = dx - cx, dz - cz
	local den = rx * sz - rz * sx
	if math.abs(den) < 1e-9 then
		return nil, nil
	end
	local qx, qz = cx - ax, cz - az
	local t = (qx * sz - qz * sx) / den
	local u = (qx * rz - qz * rx) / den
	if t >= 0 and t <= 1 and u >= 0 and u <= 1 then
		return ax + t * rx, az + t * rz
	end
	return nil, nil
end

-- the turn angle at b (degrees, 0 = straight on, 180 = straight back)
local function turnDeg(ax: number, az: number, bx: number, bz: number, cx: number, cz: number): number
	local ux, uz = bx - ax, bz - az
	local vx, vz = cx - bx, cz - bz
	local lu, lv = math.sqrt(ux * ux + uz * uz), math.sqrt(vx * vx + vz * vz)
	if lu < 1e-9 or lv < 1e-9 then
		return 0
	end
	return math.deg(math.acos(clamp((ux * vx + uz * vz) / (lu * lv), -1, 1)))
end
R.turnDeg = turnDeg

-- xs, zs: one lane polyline (a closed loop keeps its first and last point). Returns cleaned copies and the number
-- of swallowtails removed.
function R.cleanLanePolyline(xs: {number}, zs: {number}): ({number}, {number}, number)
	local c = R.LANE_CLEAN
	local removed = 0
	for _ = 1, 8 do
		local ox, oz = {xs[1]}, {zs[1]}
		local n = #xs
		local i = 2
		while i <= n - 1 do
			local cut = false
			if i + 2 <= n then
				local ax, az = ox[#ox], oz[#oz]
				local bx, bz, cx, cz, dx, dz = xs[i], zs[i], xs[i + 1], zs[i + 1], xs[i + 2], zs[i + 2]
				local bc = math.sqrt((cx - bx) ^ 2 + (cz - bz) ^ 2)
				if bc <= c.maxSeg and turnDeg(ax, az, bx, bz, cx, cz) > c.turnDeg then
					local l1 = math.sqrt((bx - ax) ^ 2 + (bz - az) ^ 2)
					local l2 = math.sqrt((dx - cx) ^ 2 + (dz - cz) ^ 2)
					if l1 > 1e-9 and l2 > 1e-9
						and ((bx - ax) * (dx - cx) + (bz - az) * (dz - cz)) / (l1 * l2) > c.fwdDot then
						local x, z = segCross(ax, az, bx, bz, cx, cz, dx, dz)
						if not x then
							-- no crossing: C projected on A-B when it lies close to it
							local abx, abz = bx - ax, bz - az
							local t = ((cx - ax) * abx + (cz - az) * abz) / (l1 * l1)
							if t >= 0 and t <= 1 then
								local px, pz = ax + t * abx, az + t * abz
								if math.sqrt((px - cx) ^ 2 + (pz - cz) ^ 2) <= c.proj then
									x, z = px, pz
								end
							end
						end
						if x then
							table.insert(ox, x)
							table.insert(oz, z :: number)
							i += 2
							cut = true
							removed += 1
						end
					end
				end
			end
			if not cut then
				table.insert(ox, xs[i])
				table.insert(oz, zs[i])
				i += 1
			end
		end
		table.insert(ox, xs[n])
		table.insert(oz, zs[n])
		local done = #ox == #xs
		xs, zs = ox, oz
		if done then
			break
		end
	end
	return xs, zs, removed
end

-- A closed loop (first point = last point within 1 stud: every generated loop) is cleaned across its seam as well:
-- 59 of the 84 loops start on a corner, and a swallowtail there (routes 7 and 8) was out of reach of the open
-- polyline cleanup, whose first and last points stay fixed. The loop is opened at the middle of its longest segment
-- (a straight stretch) for the cleanup, then turned back to start where it started (the old first point, or the
-- cleaned point nearest it when that point was cut) and closed exactly on it: arc 0 is where it was, the seam has no
-- gap (the data closes its loops within 0.45 studs), and a car crossing it, R.trafficHeading's point 6 studs on and
-- R.routeStraight all see one continuous lane. Open polylines are cleaned as before.
function R.cleanLaneLoop(xs: {number}, zs: {number}): ({number}, {number}, number)
	local n = #xs
	if n < 4 or math.sqrt((xs[1] - xs[n]) ^ 2 + (zs[1] - zs[n]) ^ 2) > 1 then
		return R.cleanLanePolyline(xs, zs)
	end
	-- unique points 1 .. n - 1 (point n repeats point 1); segment i runs from point i to point i + 1 (n - 1 -> 1)
	local m = n - 1
	local best, bi = -1, 1
	for i = 1, m do
		local j = i % m + 1
		local l = (xs[j] - xs[i]) ^ 2 + (zs[j] - zs[i]) ^ 2
		if l > best then
			best, bi = l, i
		end
	end
	local bj = bi % m + 1
	local mx, mz = (xs[bi] + xs[bj]) / 2, (zs[bi] + zs[bj]) / 2
	local rx, rz = {mx}, {mz}
	for j = 1, m do
		local i = (bi + j - 1) % m + 1
		table.insert(rx, xs[i])
		table.insert(rz, zs[i])
	end
	table.insert(rx, mx)
	table.insert(rz, mz)
	local cx, cz, removed = R.cleanLanePolyline(rx, rz)
	local k = #cx - 1 -- unique points (the last repeats the first)
	local bestD, q = math.huge, 1
	for i = 1, k do
		local d = (cx[i] - xs[1]) ^ 2 + (cz[i] - zs[1]) ^ 2
		if d < bestD then
			bestD, q = d, i
		end
	end
	local ox, oz = {}, {}
	for j = 0, k - 1 do
		local i = (q - 1 + j) % k + 1
		table.insert(ox, cx[i])
		table.insert(oz, cz[i])
	end
	table.insert(ox, cx[q])
	table.insert(oz, cz[q])
	return ox, oz, removed
end

-- routesData = require(ReplicatedStorage.PattayaTraffic); ox, oz = PattayaBuilder.ORIGIN X / Z (R.TRAFFIC_ORIGIN_*).
-- Route i of the result is route i of the data (the key of its car k is R.trafficKey(i, k)). The lanes are cleaned
-- (R.cleanLaneLoop) unless raw = true (tests).
function R.buildTrafficRoutes(routesData, ox: number, oz: number, raw: boolean?)
	local out = {}
	for _, r in routesData do
		local xs, zs, cum = {}, {}, {0}
		local minX, maxX, minZ, maxZ = math.huge, -math.huge, math.huge, -math.huge
		for i = 1, #r.pts, 2 do
			table.insert(xs, r.pts[i] + ox)
			table.insert(zs, r.pts[i + 1] + oz)
		end
		if not raw then
			xs, zs = R.cleanLaneLoop(xs, zs)
		end
		for i = 1, #xs do
			local x, z = xs[i], zs[i]
			minX, maxX, minZ, maxZ = math.min(minX, x), math.max(maxX, x), math.min(minZ, z), math.max(maxZ, z)
		end
		for i = 2, #xs do
			cum[i] = cum[i - 1] + math.sqrt((xs[i] - xs[i - 1]) ^ 2 + (zs[i] - zs[i - 1]) ^ 2)
		end
		table.insert(out, {xs = xs, zs = zs, cum = cum, length = cum[#cum], speed = r.speed, phase = r.phase,
			kinds = r.kinds, minX = minX, maxX = maxX, minZ = minZ, maxZ = maxZ})
	end
	return out
end

local function routePoint(r, s: number): (number, number)
	s %= r.length
	local cum = r.cum
	local lo, hi = 1, #cum
	while hi - lo > 1 do
		local mid = (lo + hi) // 2
		if cum[mid] <= s then lo = mid else hi = mid end
	end
	local seg = cum[hi] - cum[lo]
	local t = if seg > 0 then (s - cum[lo]) / seg else 0
	return lerp(r.xs[lo], r.xs[hi], t), lerp(r.zs[lo], r.zs[hi], t)
end
R.routePoint = routePoint

-- unit direction of a route at arc s, as (tx, tz)
function R.routeTangent(r, s: number): (number, number)
	local ax, az = routePoint(r, s - 3)
	local bx, bz = routePoint(r, s + 3)
	local dx, dz = bx - ax, bz - az
	local m = math.sqrt(dx * dx + dz * dz)
	if m < 1e-6 then
		return 0, -1
	end
	return dx / m, dz / m
end

-- is the route between arcs s1 and s2 (s1 < s2, not wrapped) within maxDeg of one direction? Returns ok and the
-- largest heading change seen (sampled every `step` studs; TestKit stages hits only on straight stretches)
function R.routeStraight(r, s1: number, s2: number, maxDeg: number, step: number?): (boolean, number)
	local mx, mz = R.routeTangent(r, (s1 + s2) / 2)
	local worst = 0
	local s = s1
	while s <= s2 do
		local tx, tz = R.routeTangent(r, s)
		local a = math.deg(math.acos(clamp(tx * mx + tz * mz, -1, 1)))
		if a > worst then worst = a end
		s += step or 4
	end
	return worst <= maxDeg, worst
end

-- the key of car k on route ri (PattayaTraffic's `active` table, its models' TrafficKey attribute, TK_HitTarget)
function R.trafficKey(ri: number, k: number): number
	return ri * 1000 + k
end

-- car k of route r at server time t: x, z and its arc s (not wrapped)
function R.trafficCarAt(r, k: number, t: number): (number, number, number)
	local s = r.phase + (k - 1) * r.length / #r.kinds + t * r.speed
	local x, z = routePoint(r, s)
	return x, z, s
end

-- the heading a traffic car is drawn with at arc s: towards the point 6 studs on (unit; (0, -1) if degenerate)
function R.trafficHeading(r, s: number): (number, number)
	local x, z = routePoint(r, s)
	local x2, z2 = routePoint(r, s + 6)
	local lx, lz = x2 - x, z2 - z
	local m = math.sqrt(lx * lx + lz * lz)
	if m > 0.01 then
		return lx / m, lz / m
	end
	return 0, -1
end

-- every traffic car within radius of (cx, cz) at server time t, in route then car order:
-- fn(key, x, z, d2, r, k, ri, s). PattayaTraffic draws its cars through this, R.trafficNear lists them.
function R.forEachTrafficCar(routes, t: number, cx: number, cz: number, radius: number, fn)
	local r2 = radius * radius
	for ri, r in routes do
		if r.length <= 0 or cx < r.minX - radius or cx > r.maxX + radius or cz < r.minZ - radius or cz > r.maxZ + radius then
			continue
		end
		for k = 1, #r.kinds do
			local x, z, s = R.trafficCarAt(r, k, t)
			local dx, dz = x - cx, z - cz
			local d2 = dx * dx + dz * dz
			if d2 <= r2 then
				fn(R.trafficKey(ri, k), x, z, d2, r, k, ri, s)
			end
		end
	end
end

-- traffic cars within radius of (cx, cz) at server time t, nearest first: {key, ri, k, x, z, lx, lz (unit heading),
-- speed, kind, dist, route, s (arc length on the route at time t, not wrapped), t}. The car is at
-- R.routePoint(route, s + speed * dt) dt seconds later.
function R.trafficNear(routes, t: number, cx: number, cz: number, radius: number)
	local out = {}
	R.forEachTrafficCar(routes, t, cx, cz, radius, function(key, x, z, d2, r, k, ri, s)
		local lx, lz = R.trafficHeading(r, s)
		table.insert(out, {x = x, z = z, lx = lx, lz = lz, speed = r.speed, kind = r.kinds[k], dist = math.sqrt(d2),
			route = r, s = s, t = t, ri = ri, k = k, key = key})
	end)
	table.sort(out, function(a, b) return a.dist < b.dist end)
	return out
end

-- TestKit entry (TK.trafficNear) from a trafficNear entry: every field TestKit needs, the key included (round 5
-- crashed on a nil key: the old copy dropped it). shapes = R.TRAFFIC_SHAPES.
function R.tkTrafficEntry(e)
	local sh = R.TRAFFIC_SHAPES[e.kind] or R.TRAFFIC_SHAPES[0]
	return {x = e.x, z = e.z, lx = e.lx, lz = e.lz, speed = e.speed, halfLen = sh.len / 2, halfWid = sh.wid / 2,
		kind = e.kind, dist = e.dist, route = e.route, s = e.s, t = e.t, key = e.key, ri = e.ri, k = e.k}
end

-- Staged hit for TK.hitTest (and its offline tests): where my car must be at server time t to meet a traffic car
-- on its own lane. p = {route, s0, t0 (the traffic car is at arc s0 at server time t0), vT (its speed), halfWid,
-- halfLen, speed (mine), mode = "rear" | "head" | "side" | "pass", lead (studs, rear / head / pass), offset (studs to
-- its right, rear / head), angle (degrees, side), gap (studs between the sides, pass)}. Returns plan(t) -> x, z, dirX,
-- dirZ, gap (studs before the boxes meet along the approach; <= 0 = touching; pass: studs left to drive), the server
-- time the boxes are due to meet (pass: level with it), the arc span {s1, s2} of the route both cars use from the
-- start to just after the touch (TestKit stages only where R.routeStraight(route, s1, s2, R.STAGE_BEND_DEG) holds),
-- and the arc span around the target at the touch (side hits: its heading steady within R.SIDE_STEADY_DEG there).
--   rear: on the lane behind it, along the route.   head: on its lane ahead of it, against the route.
--   side: from its right (the overtaking side), a straight run at `angle` to its heading at the touch, my front
--   corner on the middle of its side.   pass: overtaking it on its right, `gap` studs beside it (near-miss test).
function R.stagePlan(p)
	local r, s0, t0, vT = p.route, p.s0, p.t0, p.vT
	local speed = p.speed
	local contact = p.halfLen + R.CAR_HALF_LEN
	local function lane(sArc: number, lat: number)
		local x, z = routePoint(r, sArc)
		local tx, tz = R.routeTangent(r, sArc)
		local rx, rz = -tz, tx
		return x + rx * lat, z + rz * lat, tx, tz, rx, rz
	end
	if p.mode == "pass" then
		-- near-miss test: my car overtakes it on its right with p.gap (5) studs between the sides, from p.lead (60)
		-- studs behind to 30 studs ahead, never touching
		local lead = p.lead or 60
		local lat = p.halfWid + R.CAR_HALF_WID + (p.gap or 5)
		local level = t0 + lead / math.max(speed - vT, 1e-3)
		return function(t)
			local sc = s0 - lead + speed * (t - t0)
			local x, z, tx, tz = lane(sc, lat)
			return x, z, tx, tz, (s0 + vT * (t - t0)) + p.halfLen + R.CAR_HALF_LEN + 30 - sc
		end, level, {s0 - lead - R.CAR_HALF_LEN, s0 + vT * (level + 2 - t0) + p.halfLen + 40},
			{s0 + vT * (level - t0) - p.halfLen - 6, s0 + vT * (level - t0) + p.halfLen + 6}
	end
	if p.mode == "head" then
		local lead = p.lead or 120
		local meet = t0 + math.max(lead - contact, 0) / (speed + vT)
		local sT = s0 + vT * (meet - t0)
		return function(t)
			local sc = s0 + lead - speed * (t - t0)
			local x, z, tx, tz = lane(sc, p.offset or 0)
			return x, z, -tx, -tz, sc - (s0 + vT * (t - t0)) - contact
		end, meet, {s0 - p.halfLen - 10, s0 + lead + R.CAR_HALF_LEN}, {sT - p.halfLen - 6, sT + contact + 6}
	elseif p.mode == "side" then
		local a = math.rad(p.angle or 20)
		local vs, u = speed * math.sin(a), speed * math.cos(a)
		-- lateral distance between the centres when the corner of my (angled) box reaches its side
		local latC = p.halfWid + R.CAR_HALF_WID * math.cos(a) + R.CAR_HALF_LEN * math.sin(a)
		-- run-up: at most p.runLat (6) studs of sideways travel, so the start stays next to its lane (a long run-up
		-- started a 25 degree run 33 studs off the lane, on the kerb: Studio round 3, side 70 hit at 37)
		local run = math.clamp((p.runLat or 6) / math.max(vs, 1e-3), 0.05, 0.8)
		local tc = t0 + run
		-- my leading (front-left) corner meets the MIDDLE of its side: with the centres level (round 3) the corner
		-- reached its front corner (7.4 studs ahead at 10 degrees vs a 7-stud half length), a corner-to-corner
		-- touch whose normal can be its front face (Studio round 4: side 100 a10 -> heavy). p.alignCorner = false
		-- keeps the old alignment (tests only).
		local cornerAhead = if p.alignCorner == false then 0
			else R.CAR_HALF_LEN * math.cos(a) - R.CAR_HALF_WID * math.sin(a)
		-- A straight run at `angle` to the target's heading AT THE TOUCH (its shared position and heading at tc), no
		-- longer along the lane (round 6 review, offline scan of the real routes): on a lane that bends a few degrees
		-- at a polyline point, the lane direction where my car was differed from the target's heading at the touch by
		-- up to 5 degrees, and side 150 a5 / a20 and side 100 a10 sit within 1-3 degrees of a tier threshold.
		-- p.laneRun = true keeps the old lane-following run (tests only).
		local sT = s0 + vT * (tc - t0)
		local touch = {sT - p.halfLen - 6, sT + vT * 0.3 + p.halfLen + 6}
		local span = {sT - cornerAhead - u * run - R.CAR_HALF_LEN, sT + vT * 0.3 + p.halfLen + 10}
		if p.laneRun then
			return function(t)
				local lat = latC + vs * (tc - t)
				local sc = s0 + vT * (tc - t0) - cornerAhead - u * (tc - t)
				local x, z, tx, tz, rx, rz = lane(sc, lat)
				local dx, dz = tx * math.cos(a) - rx * math.sin(a), tz * math.cos(a) - rz * math.sin(a)
				return x, z, dx, dz, lat - latC
			end, tc, span, touch
		end
		local xT, zT = routePoint(r, sT)
		local hx, hz = R.trafficHeading(r, sT)
		local gx, gz = -hz, hx -- its right
		local ca, sa = math.cos(a), math.sin(a)
		local dx, dz = hx * ca - gx * sa, hz * ca - gz * sa
		-- my centre at the touch: latC out on its right, cornerAhead behind the middle of its side
		local cx, cz = xT + gx * latC - hx * cornerAhead, zT + gz * latC - hz * cornerAhead
		return function(t)
			local back = speed * (tc - t)
			return cx - dx * back, cz - dz * back, dx, dz, vs * (tc - t)
		end, tc, span, touch
	end
	local lead = p.lead or 120
	local meet = t0 + math.max(lead - contact, 0) / math.max(speed - vT, 1e-3)
	local sT = s0 + vT * (meet - t0)
	return function(t)
		local sc = s0 - lead + speed * (t - t0)
		local x, z, tx, tz = lane(sc, p.offset or 0)
		return x, z, tx, tz, (s0 + vT * (t - t0)) - sc - contact
	end, meet, {s0 - lead - R.CAR_HALF_LEN, sT + vT * 0.3 + p.halfLen + 10}, {sT - contact - 6, sT + p.halfLen + 6}
end

-- Staged hit helpers (TK.hitTest / TK.hitMatrix, tested offline) ----------------------------------------------------
-- Is the planned approach clear of every other traffic car? others = {{route, s, t, speed}} (trafficNear entries
-- without the target). Samples my planned centre from t0 to meet + 0.5 s every 0.05 s against each car's position
-- at that time; returns clear, the smallest distance seen.
function R.plannedPathClear(plan, t0: number, meet: number, others, clearance: number): (boolean, number)
	local worst = math.huge
	local t = t0
	while t <= meet + 0.5 do
		local x, z = plan(t)
		for _, o in others do
			local ox, oz = routePoint(o.route, o.s + o.speed * (t - o.t))
			local d = math.sqrt((x - ox) ^ 2 + (z - oz) ^ 2)
			if d < worst then worst = d end
		end
		t += 0.05
	end
	return worst >= clearance, worst
end

-- Does a registered hit belong to the staged run? h = {hitT, approachT (server time the approach began), meet,
-- frameDt (the Heartbeat step), hitX, hitZ (position of the traffic car that was hit), targetX, targetZ (the target's
-- position at hitT)}. A hit before the approach began (e.g. the car placed on top of another car), far from the
-- planned meeting time or on another car does not count. Returns ok, reason.
function R.acceptStagedHit(h): (boolean, string?)
	local slack = 0.35 + 1.5 * (h.frameDt or 1 / 60)
	local why = {}
	if h.hitT < h.approachT then
		table.insert(why, "before the approach")
	elseif math.abs(h.hitT - h.meet) > slack then
		table.insert(why, ("%.2f s from the planned meeting"):format(h.hitT - h.meet))
	end
	-- every reason is reported: round 4's "head 100 -0.50 s" did not say whether it was also another car.
	-- Identity: the key of the car the hit event names (round 6 review: never where a model happens to be drawn);
	-- the position form remains for callers without keys.
	if h.targetKey ~= nil then
		if h.hitKey ~= h.targetKey then
			table.insert(why, ("another car (hit %s, target %s)"):format(tostring(h.hitKey), tostring(h.targetKey)))
		end
	else
		local d = math.sqrt((h.hitX - h.targetX) ^ 2 + (h.hitZ - h.targetZ) ^ 2)
		if d > 6 + 60 * (h.frameDt or 1 / 60) then
			table.insert(why, ("another car (%.0f studs from the target)"):format(d))
		end
	end
	if #why > 0 then
		return false, table.concat(why, ", ")
	end
	return true, nil
end

-- the ghost a traffic car gets after an arcade hit (PattayaTraffic): Arcade_HitGhost seconds, then for as long as it
-- still overlaps my car. st = {ghostUntil, hitHold}; overlapping = R.carsOverlap(me, it, 1) this frame.
function R.hitGhostStart(st, t: number, cfg)
	st.ghostUntil = t + cfg.Arcade_HitGhost
	st.hitHold = true
end
function R.hitGhostStep(st, t: number, overlapping: boolean)
	if st.hitHold and t >= st.ghostUntil then
		if overlapping then
			st.ghostUntil = t + 0.2
		else
			st.hitHold = nil
		end
	end
end

-- What the owner's table says a staged hit must give: the hit as the geometry makes it (rear: vc = speed - vT,
-- head: speed + vT, side: speed * sin(angle) into its side), classified. Returns the classifyHit result and the hit.
function R.expectedStaged(mode: string, speed: number, angleDeg: number?, vT: number, cfg)
	local hit
	if mode == "head" then
		hit = {vc = speed + vT, approachDeg = 90, facingDot = -1, side = 1, front = true}
	elseif mode == "side" then
		local a = math.rad(angleDeg or 20)
		local vc = speed * math.sin(a)
		local rel = math.sqrt((speed * math.cos(a) - vT) ^ 2 + vc * vc)
		hit = {vc = vc, approachDeg = math.deg(math.asin(clamp(vc / math.max(rel, 1e-6), 0, 1))),
			facingDot = math.cos(a), side = -1, front = true}
	else
		hit = {vc = math.max(speed - vT, 0), approachDeg = 90, facingDot = 1, side = 1, front = true}
	end
	return R.classifyHit(hit, cfg), hit
end

-- server check of a client TrafficHit report: ok, reason
-- info = {now, lastAt, tier, vc, speedBefore, serverPeak (max horizontal speed the server saw in the last 0.6 s),
--         trafficDist (nearest traffic car at that time, or nil when the traffic data is missing)}
function R.validateHitReport(info, cfg): (boolean, string?)
	if info.tier ~= "heavy" and info.tier ~= "headon" then
		return false, "tier"
	end
	if type(info.vc) ~= "number" or info.vc ~= info.vc or info.vc < 0 or info.vc > 400 then
		return false, "vc"
	end
	if info.lastAt and info.now - info.lastAt < cfg.Arcade_HitReportGap then
		return false, "rate"
	end
	if (info.serverPeak or 0) < cfg.Arcade_HitMinSpeed then
		return false, "slow"
	end
	-- closing speed can exceed my speed by at most the traffic speed (55) plus replication slack
	if info.vc > info.serverPeak + 80 then
		return false, "vc"
	end
	if info.trafficDist ~= nil and info.trafficDist > cfg.Arcade_HitTrafficRadius then
		return false, "no traffic"
	end
	return true, nil
end

return R
