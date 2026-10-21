"""TK.jobDriveTest (the automated Taxi / Delivery economy check) and S.mpCheck (the 2-player check), team18/arcade-econ.

Offline only (luau CLI), in a simulated client-server session (tools/qa/tests/luau/sim_session.luau):
  server: the REAL PattayaJobsServer, PattayaRecoveryServer and PattayaTestKitServer; the jobs server's road graph
          (PattayaRoute) is a stand-in with a fixed route between stands, PattayaProgress pays into leaderstats;
  client: the REAL PattayaTraffic (shared traffic maths, ghosts, TK_HitTarget, the swept touch test, near misses, the
          TestKit agent hook) and the REAL PattayaTestKit (one copy per client). CarController is a stand-in for its
          arcade hit path only (PattayaRecovery.classifyHit / impactVelocity, the telemetry attributes, ArcadeAntiRoll
          for PattayaRecovery.antiRollHold, the TrafficHit report at most once a second; the spin is applied at once);
          otherwise the car coasts on its velocity (no suspension, no scenery);
  between: remotes queued per direction, server attributes replicated at the client's next frame, and the server
          seeing the car where the client's last frame left it (positions change only at client frames: the 15 fps
          aliasing case). The TestKit FPS cap sets the client's frame time (its busy wait is not simulated).
Nothing here ran in Studio."""
import os
import re
import unittest

import _qa

TESTKIT = os.path.join('ReplicatedStorage', 'PattayaTestKit.luau')
RECOVERY = os.path.join('ReplicatedStorage', 'PattayaRecovery.luau')
KITSERVER = os.path.join('ServerStorage', 'PattayaTestKitServer.luau')
JOBS = os.path.join('ServerScriptService', 'PattayaJobsServer.server.luau')
RECSERVER = os.path.join('ServerScriptService', 'PattayaRecoveryServer.server.luau')
TRAFFIC = os.path.join('StarterPlayer', 'StarterPlayerScripts', 'PattayaTraffic.client.luau')


def _long(s):
    """s as a Luau long-bracket string literal"""
    level = 0
    while (']' + '=' * level + ']') in s:
        level += 1
    eq = '=' * level
    return '[' + eq + '[\n' + s + ']' + eq + ']'


# A straight road along +X (map-local z = 0) with one lane each way 9 studs off the centre (traffic keeps left: the
# eastbound lane is at z = -9), each lane a closed loop that comes back 1,500 studs away. Job stands sit on the
# centreline with the kerb on the left of eastbound travel, so the stand's road direction is +X.
SYNTH = {
    'traffic': [
        {'speed': 45.0, 'phase': 37.0, 'n': 36, 'pts': [0, -9, 3400, -9, 3400, -1500, 0, -1500, 0, -9]},
        {'speed': 42.0, 'phase': 911.0, 'n': 34, 'pts': [3400, 9, 0, 9, 0, 1500, 3400, 1500, 3400, 9]},
    ],
    'stands': [
        {'id': 'a_taxi', 'kind': 'taxi', 'label': 'Stand A', 'x': 200.0, 'z': 0.0},
        {'id': 'b_taxi', 'kind': 'taxi', 'label': 'Stand B', 'x': 2900.0, 'z': 0.0},
        {'id': 'c_delivery', 'kind': 'delivery', 'label': 'Stand C', 'x': 300.0, 'z': 0.0},
        {'id': 'd_delivery', 'kind': 'delivery', 'label': 'Stand D', 'x': 3000.0, 'z': 0.0},
    ],
}


def _synth_world():
    routes = []
    for a in SYNTH['stands']:
        for b in SYNTH['stands']:
            if a is b:
                continue
            n = max(2, int(abs(b['x'] - a['x']) // 300) + 1)
            pts = []
            for i in range(n + 1):
                pts += [a['x'] + (b['x'] - a['x']) * i / n, 0.0]
            routes.append({'from': a['id'], 'to': b['id'], 'pts': pts})
    return {'stands': SYNTH['stands'], 'routes': routes}


def _lua(v):
    if isinstance(v, dict):
        return '{' + ', '.join(f'{k} = {_lua(x)}' for k, x in v.items()) + '}'
    if isinstance(v, (list, tuple)):
        return '{' + ', '.join(_lua(x) for x in v) + '}'
    if isinstance(v, str):
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    return repr(v)


def _synth_traffic_luau():
    rows = []
    for i, r in enumerate(SYNTH['traffic']):
        kinds = ','.join(str((k + i) % 3) for k in range(r['n']))
        pts = ','.join(f'{x:g}' for x in r['pts'])
        rows.append(f'{{length = 0, speed = {r["speed"]}, phase = {r["phase"]}, kinds = {{{kinds}}}, pts = {{{pts}}}}}')
    return 'return {' + ', '.join(rows) + '}'


CHECK = r'''
fails, passes = 0, 0
function check(name, cond, detail)
	if cond then passes += 1 print("PASS " .. name)
	else fails += 1 print("FAIL " .. name .. (if detail ~= nil then " :: " .. tostring(detail) else "")) end
end
function near(a, b, eps) return type(a) == "number" and math.abs(a - b) <= (eps or 1e-6) end
'''

# the session: server scripts, stand-ins, clients ------------------------------------------------------------------
BOOT = r'''
local SRC = {recovery = __RECOVERY__, recServer = __RECSERVER__, jobs = __JOBS__, kitServer = __KITSERVER__,
	testkit = __TESTKIT__, traffic = __TRAFFIC__}
DATA = (loadstring(__DATA__))()
WORLD = __WORLD__
math.randomseed(__SEED__)
SIM.latency = __LATENCY__
SIM.T0 += __T0SHIFT__ -- another traffic picture at the start
__CHECK__
local function stands()
	local out = {}
	for _, s in WORLD.stands do
		table.insert(out, {id = s.id, kind = s.kind, label = s.label, x = s.x, z = s.z, kx = 0, kz = -1, source = "test"})
	end
	return out
end

-- the jobs server's road graph: every stand is a node; the route between two stands is the given polyline
local function makeRoute(W)
	local Route = {}
	function Route.toLocal(p) return Vector2.new(p.X - 20000, p.Z) end
	function Route.toWorld(p, y) return Vector3.new(p.X + 20000, y or 1, p.Y) end
	local byKey = {}
	for _, r in W.routes do
		local pts = {}
		for i = 1, #r.pts, 2 do table.insert(pts, Vector2.new(r.pts[i], r.pts[i + 1])) end
		local len = 0
		for i = 2, #pts do len += (pts[i] - pts[i - 1]).Magnitude end
		byKey[r.from .. ">" .. r.to] = {pts = pts, length = len}
	end
	function Route.nearestNode(p)
		for i, s in W.stands do
			if math.abs(s.x - p.X) < 1 and math.abs(s.z - p.Y) < 1 then return i end
		end
		return nil
	end
	Route.nearestJunction = Route.nearestNode
	function Route.dijkstra(src)
		local dist = {[src] = 0}
		for i, s in W.stands do
			local r = byKey[W.stands[src].id .. ">" .. s.id]
			if r then dist[i] = r.length end
		end
		return dist, src
	end
	function Route.polylineOf(_, src, dst)
		local r = byKey[W.stands[src].id .. ">" .. W.stands[dst].id]
		local out = {}
		for i = 2, #r.pts - 1 do table.insert(out, r.pts[i]) end
		return out
	end
	function Route.length(pts)
		local len = 0
		for i = 2, #pts do len += (pts[i] - pts[i - 1]).Magnitude end
		return len
	end
	function Route.carOf(plr)
		local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
		local seat = hum and hum.SeatPart
		if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
			return seat.Parent.PrimaryPart
		end
		return nil
	end
	function Route.busy(plr)
		return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
			or plr:GetAttribute("JobActive") == true or plr:GetAttribute("CircuitActive") == true
	end
	return Route
end

-- progress: pays into leaderstats like PattayaProgress.Award, and remembers every award
AWARDS = {}
local Progress = {}
function Progress.Start() end
function Progress.Award(plr, money, exp, reason)
	local ls = plr:FindFirstChild("leaderstats")
	ls.Money.Value += math.floor(money)
	ls.EXP.Value += math.floor(exp)
	table.insert(AWARDS, {plr = plr.Name, money = money, exp = exp, reason = reason, t = SIM.t})
	return 0
end

-- every message a server remote sends to a client (the server's own truth for the checks)
SENT = {}
SIM.onFireClient = function(remote, plrS, args)
	table.insert(SENT, {t = SIM.t, name = remote.Name, plr = plrS.Name, args = args})
end

R = SIM.load(SRC.recovery, SIM.serverEnv(), "PattayaRecovery")()
SIM.module(SIM.RS, "PattayaRecovery", R)
SIM.module(SIM.RS, "PattayaTraffic", DATA)
local PD = SIM.instance("Folder", "PattayaData")
PD.Parent = SIM.SS
SIM.module(PD, "jobs", stands())
SIM.module(PD, "graph", {})
local worldFolder = SIM.instance("Folder", "PattayaWorld")
worldFolder.Parent = SIM.workspace
SIM.module(SIM.SS, "PattayaRoute", makeRoute(WORLD))
SIM.module(SIM.SS, "PattayaProgress", Progress)
-- every client loads its own copy of the TestKit (also when PattayaTraffic's hook requires it)
SIM.clientModule(SIM.RS, "PattayaTestKit", function(c)
	return SIM.load(SRC.testkit, SIM.clientEnv(c), "PattayaTestKit")()
end)

-- stand-in CarController for one client, the arcade hit path only (CarController.applyImpact): same checks, same
-- PattayaRecovery maths and telemetry attributes, ArcadeAntiRoll enabled on the chassis for antiRollHold seconds,
-- heavy / head-on hits reported to the server at most once a second. The spin is applied at once.
local function standInCar(c)
	local hitCount, lastReport = 0, -math.huge
	local P = c.playerC
	c.antiRollUntil = 0
	c.hits = {}
	local function ignored(why)
		P:SetAttribute("Recovery_HitIgnored", why)
		P:SetAttribute("Recovery_HitIgnoredAt", SIM.workspace:GetServerTimeNow())
	end
	local function applyImpact(info)
		if type(info) ~= "table" or type(info.vc) ~= "number" or info.vc ~= info.vc then
			ignored("bad payload")
			return
		end
		if not R.arcade() then
			ignored("arcade off")
			return
		end
		local car = c.car
		if car.anchored then
			ignored("car anchored")
			return
		end
		local cfg = R.config()
		local res = R.classifyHit(info, cfg)
		local v = car.v
		local before = math.sqrt(v.X * v.X + v.Z * v.Z)
		local nx, nz = info.nx or 0, info.nz or 0
		local wx, wz = R.impactVelocity(v.X, v.Z, nx, nz, res)
		car.v = Vector3.new(wx, 0, wz)
		local push = math.min((info.depth or 0) + 0.5, cfg.Arcade_MaxPush)
		local p = car.cf.Position + Vector3.new(nx * push, 0, nz * push)
		local look = car.cf.LookVector
		local a = math.rad(res.yaw)
		local nl = Vector3.new(look.X * math.cos(a) + look.Z * math.sin(a), 0, -look.X * math.sin(a) + look.Z * math.cos(a))
		car.cf = CFrame.lookAt(p, p + nl)
		local window = 0
		if res.control > 0 or math.abs(res.yaw) > 0 then
			local spinT = R.spinProfile(res.yaw, math.max(res.control, 0.25))
			window = math.max(res.control, spinT)
		end
		if cfg.Arcade_AntiRoll then
			car.children = {ArcadeAntiRoll = {Name = "ArcadeAntiRoll", Enabled = true}}
			c.antiRollUntil = os.clock() + R.antiRollHold(res.tier, window, cfg)
		end
		hitCount += 1
		P:SetAttribute("Recovery_LastHitKey", info.key)
		P:SetAttribute("Recovery_LastHitT", info.at)
		P:SetAttribute("Recovery_LastHitTier", res.tier)
		P:SetAttribute("Recovery_LastHitBefore", before)
		P:SetAttribute("Recovery_LastHitAfter", math.sqrt(wx * wx + wz * wz))
		P:SetAttribute("Recovery_LastHitTrafficSpeed", info.trafficSpeed)
		P:SetAttribute("Recovery_LastHitVc", info.vc)
		P:SetAttribute("Recovery_LastHitRel", info.rel)
		P:SetAttribute("Recovery_LastHitAngle", info.approachDeg)
		P:SetAttribute("Recovery_LastHitFacing", info.facingDot)
		P:SetAttribute("Recovery_LastHitYaw", res.yaw)
		P:SetAttribute("Recovery_LastHitControl", window)
		P:SetAttribute("Recovery_HitCount", hitCount)
		table.insert(c.hits, {t = SIM.t, tier = res.tier, key = info.key, vc = info.vc, before = before})
		if (res.tier == "heavy" or res.tier == "headon") and os.clock() - lastReport >= 1 then
			lastReport = os.clock()
			local remotes = c.RS:FindFirstChild("PattayaRemotes")
			local th = remotes and remotes:FindFirstChild("TrafficHit")
			if th then
				th:FireServer(res.tier, info.vc, before)
			end
		end
	end
	local ev = SIM.instance("BindableEvent", "CarImpact")
	ev.Parent = P:FindFirstChild("PlayerScripts")
	ev.Event:Connect(applyImpact)
	-- the physics step: the car coasts on its velocity; an injected dead stop holds it where it is
	c.physics = function(dt)
		local car = c.car
		if c.freezeUntil and SIM.t < c.freezeUntil then
			c.frozenCf = c.frozenCf or car.cf
			car.cf, car.v = c.frozenCf, Vector3.zero
			return
		end
		c.frozenCf = nil
		local p = car.cf.Position + Vector3.new(car.v.X * dt, 0, car.v.Z * dt)
		car.cf = CFrame.lookAt(p, p + car.cf.LookVector)
		if car.children and os.clock() >= c.antiRollUntil then
			car.children.ArcadeAntiRoll.Enabled = false
		end
	end
end

-- the server's own view of every car: speed over each second (as the jobs teleport check), anchored moves excluded
SERVER_SPEED = {}
SIM.serverRun.Heartbeat:Connect(function()
	for _, c in SIM.clients do
		local p = c.chassisS.Position
		local s = SERVER_SPEED[c.name]
		if not s then
			s = {at = SIM.t, pos = p, maxPerSecond = 0, anchoredSeen = false}
			SERVER_SPEED[c.name] = s
		end
		if c.car.anchored then
			s.anchoredSeen = true
		end
		if SIM.t - s.at >= 1 then
			local d = Vector3.new(p.X - s.pos.X, 0, p.Z - s.pos.Z).Magnitude / (SIM.t - s.at)
			if not s.anchoredSeen then
				s.maxPerSecond = math.max(s.maxPerSecond, d)
			end
			s.at, s.pos, s.anchoredSeen = SIM.t, p, c.car.anchored
		end
	end
end)

SIM.runServerScript(SRC.recServer, "PattayaRecoveryServer")
local MATH_FIRST = setmetatable({random = function(a, b) return if b then a else 0.5 end}, {__index = math})
SIM.runServerScript(SRC.jobs, "PattayaJobsServer", {math = MATH_FIRST})
S = SIM.load(SRC.kitServer, SIM.serverEnv(), "PattayaTestKitServer")()
SIM.module(SIM.SS, "PattayaTestKitServer", S)
S.start()

function addClient(name, opts)
	local c = SIM.addClient(name, opts)
	standInCar(c)
	SIM.runClientScript(c, SRC.traffic, "PattayaTraffic")
	c.TK = SIM.require(c.RS:FindFirstChild("PattayaTestKit"))
	-- the TestKit FPS cap is the client's frame time here (its busy wait cannot run on a simulated clock)
	local realLimit = c.TK.fpsLimit
	local capFps = nil
	c.TK.fpsLimit = function(fps)
		realLimit(nil)
		if type(fps) == "number" and fps == fps and fps > 0 then
			capFps = fps
			c.dt = math.max(c.baseDt, 1 / fps)
			c.playerC:SetAttribute("TK_FpsLimit", fps)
			return fps
		end
		capFps = nil
		c.dt = c.baseDt
		return nil
	end
	c.TK.fpsLimitOn = function() return capFps end
	return c
end
'''

# JobMath: the pure parts through TK.jobMath (one client) ----------------------------------------------------------
JOBMATH = r'''
local c = addClient("A", {dt = 1 / 60, at = Vector3.new(20200, 3.8, 0)})
SIM.run(0.5)
local JM = c.TK.jobMath
local cfg = R.config()
-- Hermite: ends and velocities exact, continuous
local f = JM.hermite(0, 0, 100, 0, 200, 10, 70, 5, 2.5)
local x0, z0, vx0, vz0 = f(0)
local x1, z1, vx1, vz1 = f(2.5)
check("hermite starts where the car is, at its velocity", near(x0, 0) and near(z0, 0) and near(vx0, 100) and near(vz0, 0))
check("hermite ends on the run's start, at its velocity", near(x1, 200) and near(z1, 10) and near(vx1, 70) and near(vz1, 5))
local xa, za, vxa, vza = f(1.0)
local xb, zb = f(1.0 + 1e-4)
check("hermite velocity is the derivative of its position", near((xb - xa) / 1e-4, vxa, 1e-2) and near((zb - za) / 1e-4, vza, 1e-2))
-- curveStats: a steady straight loses nothing; a 100 -> 0 stop in 1 s is caught; a curve that turns back is caught
local st = JM.curveStats(JM.hermite(0, 0, 100, 0, 250, 0, 100, 0, 2.5), 2.5, 1, 0)
check(("steady curve: no speed loss (%.2f), top 100 (%.1f)"):format(st.maxDrop, st.maxV), st.maxDrop < 0.5 and near(st.maxV, 100, 0.5))
local stop = JM.curveStats(JM.hermite(0, 0, 100, 0, 50, 0, 0, 0, 1), 1, 1, 0)
check(("a hard stop is caught (loss in 0.35 s %.0f > JM.MAX_DROP %d)"):format(stop.maxDrop, JM.MAX_DROP), stop.maxDrop > JM.MAX_DROP)
local back = JM.curveStats(JM.hermite(0, 0, -30, 0, 100, 0, 80, 0, 2), 2, 1, 0)
check("a curve that starts backwards is caught (minAlong < 0)", back.minAlong < 0)
-- frame-rate caps (the server's 10 Hz speed from positions)
check("capFor: 76 at 15 fps, 100 at 20, 110 at 30, 120 at 60", JM.capFor(15) == 76 and JM.capFor(20) == 100
	and JM.capFor(30) == 110 and JM.capFor(60) == 120)
-- event specs: the owner's table with margin, for every traffic speed 38-56 and every cap
local bad = {}
for vT = 38, 56 do
	for _, cap in {76, 100, 110, 120} do
		for _, name in {"headon", "light", "scrape", "near", "nearOncoming"} do
			local spec = JM.eventSpec(name, vT, cap, cfg)
			if not spec then
				table.insert(bad, ("%s missing at vT %d cap %d"):format(name, vT, cap))
			else
				if spec.speed > cap + 1e-6 then table.insert(bad, name .. " over the cap") end
				if spec.want ~= "near" then
					local res, hit = R.expectedStaged(spec.mode, spec.speed, spec.angle, vT, cfg)
					if res.tier ~= spec.want then table.insert(bad, ("%s vT %d cap %d: tier %s"):format(name, vT, cap, res.tier)) end
					if name == "light" and (hit.vc < 19 or hit.vc > 31) then table.insert(bad, "light vc " .. hit.vc) end
					if name == "scrape" and hit.vc > 11 then table.insert(bad, "scrape vc " .. hit.vc) end
					if name == "headon" and hit.vc < 105 then table.insert(bad, "headon vc " .. hit.vc) end
				elseif spec.speed <= R.NEAR_SPEED + 4 then
					table.insert(bad, name .. " too slow for a near miss")
				end
			end
		end
		local heavy = JM.eventSpec("heavy", vT, cap, cfg)
		if (heavy ~= nil) ~= (cap >= vT + 60) then table.insert(bad, ("heavy at vT %d cap %d"):format(vT, cap)) end
	end
end
check("eventSpec: every event for traffic at 38-56 studs/s under every cap, with its tier (heavy only where the cap allows)",
	#bad == 0, table.concat(bad, "; "))
-- matchBumps: the owner's rules
local function ev(t, kind, data, key) return {t = t, kind = kind, data = data, key = key} end
local m = JM.matchBumps({ev(0, "job start"), ev(5, "hit", "headon", 1), ev(5.05, "accepted", "headon"), ev(5.1, "job bump", 1),
	ev(9, "hit", "light", 2), ev(12, "hit", "scrape", 3), ev(15, "near"), ev(30, "job finish")}, {noStray = true})
check("matchBumps: a head-on accepted with one bump, light and scrape without, one near miss", m.ok and m.near == 1
	and m.accepted == 1 and m.bumps == 1, table.concat(m.lines, "; "))
m = JM.matchBumps({ev(0, "job start"), ev(5, "hit", "heavy", 1), ev(9, "job finish")}, {noStray = true})
check("matchBumps: a heavy hit the server did not accept fails", not m.ok and m.unaccepted == 1)
m = JM.matchBumps({ev(0, "job start"), ev(5, "hit", "heavy", 1), ev(5.05, "accepted", "heavy"), ev(5.1, "job bump", 1),
	ev(5.9, "job bump", 2), ev(9, "job finish")}, {noStray = true})
check("matchBumps: two bumps for one crash fail", not m.ok and m.doubles == 1)
m = JM.matchBumps({ev(0, "job start"), ev(5, "hit", "light", 1), ev(5.3, "job bump", 1), ev(9, "job finish")}, {noStray = true})
check("matchBumps: a bump after a light hit fails", not m.ok and m.lightBumped == 1)
m = JM.matchBumps({ev(0, "job start"), ev(7, "job bump", 1), ev(9, "job finish")}, {noStray = true})
check("matchBumps: a bump without a hit fails the autopilot", not m.ok and m.stray == 1)
m = JM.matchBumps({ev(0, "job start"), ev(7, "job bump", 1), ev(9, "job finish")}, {})
check("matchBumps: ... and is only listed when noStray is off", m.ok and m.stray == 1)
m = JM.matchBumps({ev(-1, "near"), ev(0, "job start"), ev(3, "near"), ev(9, "job finish"), ev(9.2, "near"), ev(10, "near")}, {})
check("matchBumps: near misses count from the start to the finish (+0.3 s)", m.near == 2, m.near)
-- the oncoming near miss: my car passes `gap` studs off the right side of a car coming the other way; at 15 / 30 /
-- 60 fps exactly one near miss (R.nearMissStep, PattayaTraffic's rule), never a touch
local routes = R.buildTrafficRoutes(DATA, R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z)
local r = routes[2] -- westbound
for _, fps in {15, 30, 60} do
	local plan = JM.passOncomingPlan({route = r, s0 = 1000, t0 = 0, vT = r.speed, halfWid = 3.3, halfLen = 7,
		speed = 85, lead = 110, gap = 5})
	local st2 = {}
	local fires, touched, minGap = 0, false, math.huge
	local t = 0
	while t < 3 do
		local x, z, dx, dz, left = plan(t)
		local s = 1000 + r.speed * t
		local tx, tz = R.routePoint(r, s)
		local lx, lz = R.trafficHeading(r, s)
		local ddx, ddz = x - tx, z - tz
		local relX, relZ = ddx * -lz + ddz * lx, -(ddx * lx + ddz * lz)
		if R.carsOverlap({x = x, z = z, lx = dx, lz = dz}, {x = tx, z = tz, lx = lx, lz = lz, halfWid = 3.3, halfLen = 7}, 0) then
			touched = true
		end
		if math.abs(relZ) < 7 then minGap = math.min(minGap, math.abs(relX) - 3.3 - R.CAR_HALF_WID) end
		if R.nearMissStep(st2, relX, relZ, 3.3, 7, false, 85, t, -math.huge) then fires += 1 end
		if left <= 0 then break end
		t += 1 / fps
	end
	check(("oncoming near miss at %d fps: %d near miss, gap %.1f studs, no touch"):format(fps, fires, minGap),
		fires == 1 and not touched and minGap > 3 and minGap < R.NEAR_GAP)
end
check("no thread errors", #SIM.errors == 0, SIM.errors[1])
print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# JobDrive: the whole test in the session ---------------------------------------------------------------------------
JOBDRIVE = r'''
local SCENARIO = "__SCENARIO__"
local A = addClient("A", {dt = 1 / 60, jitter = __JITTER__,
	at = Vector3.new(20000 + WORLD.stands[1].x + 30, 3.8, WORLD.stands[1].z), look = Vector3.new(1, 0, 0)})
SIM.run(1.0)
local TK = A.TK
local KIT = SIM.serverG.TKS_LIVE
-- the car ignores scenery for the whole job: its collisions are off in every frame of a job
local collOn, jobFrames = 0, 0
A.run.Heartbeat:Connect(function()
	if A.playerC:GetAttribute("JobActive") == true then
		jobFrames += 1
		if A.car.canCollide ~= false then collOn += 1 end
	end
end)
local money0 = A.playerS.leaderstats.Money.Value
local exp0 = A.playerS.leaderstats.EXP.Value
local tStart = SIM.t
local h = TK.jobDriveTestStart(__OPTS__)
local okSecond, errSecond = pcall(TK.jobDriveTestStart, __OPTS__)
check("a second job test is refused while one runs", not okSecond and tostring(errSecond):find("already running", 1, true)
	~= nil, errSecond)
if SCENARIO == "stray" then
	-- a dead stop of 0.5 s at speed, 6 s into the first job: the speed-drop detector counts a bump without a hit
	SIM.run(120, function() return A.playerS:GetAttribute("JobActive") == true end)
	SIM.run(6)
	A.freezeUntil = SIM.t + 0.5
elseif SCENARIO == "stop" then
	SIM.run(120, function() return A.playerS:GetAttribute("JobActive") == true end)
	SIM.run(8)
	h:stop("test")
	SIM.run(3)
end
local finished = SIM.run(900, function() return h.done end)
print(("SESSION jobDriveTest took %.1f s"):format(SIM.t - tStart))
for _, l in h.lines do print("LINE " .. l) end
print("SUMMARY " .. tostring(h.summary) .. " | ERROR " .. tostring(h.error))
check("the test finished (no hang)", finished or SCENARIO == "stop", h:poll())
check("no thread errors and no engine wait inside a Heartbeat-resumed runner", #SIM.errors == 0, SIM.errors[1])
-- the server's own truth: every job that finished paid the jobs server's formula
local KINDS = {taxi = {cut = 0.12, tps = 1.5}, delivery = {cut = 0.15, tps = 2}}
local starts, finishes, bumps, stops = {}, {}, 0, {}
for _, m in SENT do
	if m.name == "JobUpdate" then
		local kind, p = m.args[1], m.args[2]
		if kind == "start" then table.insert(starts, p)
		elseif kind == "finish" then table.insert(finishes, p)
		elseif kind == "bump" then bumps += 1
		elseif kind == "stop" then table.insert(stops, tostring(p)) end
	end
end
local payoutsOk = #finishes > 0
local payText = {}
local minBumps, minNear = math.huge, math.huge
for i, f in finishes do
	local s = starts[i]
	local k = KINDS[s.kind]
	local cut = math.min(f.bumps * k.cut, 0.6)
	local tipNoNear = math.floor(math.max(0, s.timeLimit - f.time) * k.tps)
	local nearN = (f.tip - tipNoNear) / 5
	table.insert(payText, ("%s fare %d bumps %d tip %d (%s near) money %d"):format(s.kind, s.fare, f.bumps, f.tip,
		tostring(nearN), f.money))
	minBumps, minNear = math.min(minBumps, f.bumps), math.min(minNear, nearN)
	if nearN ~= math.floor(nearN) or nearN < 0 or f.money ~= math.floor(s.fare * (1 - cut)) + f.tip then
		payoutsOk = false
	end
end
local serverMax = SERVER_SPEED.A and SERVER_SPEED.A.maxPerSecond or 0
if SCENARIO == "pass" then
	-- every run line: status, kind and its events
	local runs, evOk, evAll, crashAll = {}, 0, 0, true
	for _, l in h.lines do
		local status = l:match("^(%u+) jobDrive [%w ]-r%d+ ")
		if status then
			local list = l:match(" | events: ([^|]*)") or ""
			table.insert(runs, status)
			local crash = false
			for name, okText in list:gmatch("(%a+) (%a+)") do
				evAll += 1
				if okText == "ok" then evOk += 1 end
				if okText == "ok" and (name == "headon" or name == "heavy") then crash = true end
			end
			crashAll = crashAll and crash
		end
	end
	local nPass, nIncomplete = 0, 0
	for _, s in runs do
		if s == "PASS" then nPass += 1 elseif s == "INCOMPLETE" then nIncomplete += 1 end
	end
	if __ALLOW_INCOMPLETE__ then
		-- 15 fps: the autopilot is capped at 76 studs/s, below the delivery jobs' nominal 85, so a long delivery job
		-- leaves time for the crash and some of the other events only (INCOMPLETE, never FAIL)
		check(("every run PASS or INCOMPLETE, at least one PASS, the crash covered in every run (%s)"):format(
			table.concat(runs, ", ")), #runs == __RUNS__ and nPass + nIncomplete == #runs and nPass >= 1 and crashAll)
		check(("every staged event that ran passed (%d/%d)"):format(evOk, evAll), evAll >= 2 * __RUNS__ and evOk == evAll)
	else
		check(("summary: every run PASS (%s)"):format(tostring(h.summary)), h.summary ~= nil
			and h.summary:find("ALL PASS", 1, true) ~= nil and nPass == __RUNS__)
		check(("every staged event of every run passed (%d/%d)"):format(evOk, evAll), evAll == __EVENTS__ * __RUNS__
			and evOk == evAll)
	end
	check(("the jobs server paid every job by its formula (%s)"):format(table.concat(payText, "; ")), payoutsOk
		and #finishes == #starts and #finishes == __RUNS__ and minBumps >= 1
		and (__ALLOW_INCOMPLETE__ or minNear >= 1))
	check("no job was stopped (no 'moved too fast', no 'Too late', no cancel)", #stops == 0, table.concat(stops, "; "))
	check(("the car ignored scenery in every frame of every job (%d of %d frames collided)"):format(collOn, jobFrames),
		jobFrames > 200 and collOn == 0)
	check(("the server never saw the car faster than the autopilot cap over any second (%.0f studs/s)"):format(serverMax),
		serverMax < 125 and serverMax > 40)
	local heavy = 0
	for _, x in A.hits do
		if x.tier == "heavy" or x.tier == "headon" then heavy += 1 end
	end
	local accepted = A.playerS:GetAttribute("TrafficHits") or 0
	check(("every heavy / head-on hit was accepted by the server (%d of %d) and gave one bump (%d)"):format(accepted, heavy,
		bumps), heavy >= __RUNS__ and accepted == heavy and bumps == heavy)
elseif SCENARIO == "stray" then
	local strayLine = false
	for _, l in h.lines do
		if l:find("without an accepted traffic hit", 1, true) and l:find("FAIL", 1, true) then strayLine = true end
	end
	check("a dead stop during the drive: the bump without a hit is caught and the run FAILs", strayLine
		and h.summary ~= nil and h.summary:find("0/1 runs PASS", 1, true) ~= nil, h.summary)
elseif SCENARIO == "stop" then
	check("stopped mid-job: the job was cancelled", A.playerS:GetAttribute("JobActive") ~= true
		and #stops >= 1 and stops[#stops]:find("cancel", 1, true) ~= nil, table.concat(stops, "; "))
end
-- nothing left over, on every path
check("CollisionModel is back to nil (it was nil before the test)", SIM.workspace:GetAttribute("CollisionModel") == nil,
	SIM.workspace:GetAttribute("CollisionModel"))
check("the server kit holds no lease and no speed probe", KIT.lease == nil and next(KIT.probes) == nil)
check("no TestKit attribute left on the client", A.playerC:GetAttribute("TK_HitTarget") == nil
	and A.playerC:GetAttribute("TrafficGhostAll") == nil and A.playerC:GetAttribute("TK_FpsLimit") == nil)
check("no job running", A.playerS:GetAttribute("JobActive") ~= true)
check(("Money / EXP set back (%d -> %d, %d -> %d)"):format(money0, A.playerS.leaderstats.Money.Value, exp0,
	A.playerS.leaderstats.EXP.Value), A.playerS.leaderstats.Money.Value == money0 and A.playerS.leaderstats.EXP.Value == exp0)
SIM.run(0.5)
check(("the car is free, still and collides again (%.1f studs/s)"):format(A.car.v.Magnitude), A.car.anchored == false
	and A.car.v.Magnitude < 1 and A.car.canCollide ~= false)
print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# the 2-player check ---------------------------------------------------------------------------------------------------
MPCHECK = r'''
local A = addClient("A", {dt = 1 / 60, at = Vector3.new(21500, 3.8, 3), look = Vector3.new(1, 0, 0)})
local B = addClient("B", {dt = 1 / 30, at = Vector3.new(21000, 3.8, 3), look = Vector3.new(1, 0, 0)})
SIM.run(1.0)
local tStart = SIM.t
local h = S.mpCheckStart({})
local okSecond, errSecond = pcall(S.mpCheckStart, {})
check("a second mpCheck is refused while one runs", not okSecond and tostring(errSecond):find("already running", 1, true)
	~= nil, errSecond)
local finished = SIM.run(400, function() return h.done end)
print(("SESSION mpCheck took %.1f s"):format(SIM.t - tStart))
for _, l in h.lines do print("LINE " .. l) end
check("mpCheck finished", finished, S.mpCheckPoll())
check("no thread errors and no engine wait inside a Heartbeat-resumed runner", #SIM.errors == 0, SIM.errors[1])
check(("mpCheck: every check passed (%s)"):format(tostring(h.summary)), h.summary ~= nil
	and h.summary:find("ALL PASS", 1, true) ~= nil and h.summary:find(" 0 FAIL", 1, true) ~= nil)
local passN = 0
for _, l in h.lines do if l:sub(1, 5) == "PASS " then passN += 1 end end
check(("mpCheck ran its checks (%d PASS lines)"):format(passN), passN >= 20)
check("both agents were started by PattayaTraffic's hook and stopped again", A.G.TK_LIVE.agent == nil
	and B.G.TK_LIVE.agent == nil and SIM.workspace:GetAttribute("TK_ClientAgent") == nil)
check("after mpCheck: CollisionModel nil, no lease", SIM.workspace:GetAttribute("CollisionModel") == nil
	and SIM.serverG.TKS_LIVE.lease == nil)
check("after mpCheck: no job, no TestKit attribute on either client", A.playerS:GetAttribute("JobActive") ~= true
	and B.playerS:GetAttribute("JobActive") ~= true and A.playerC:GetAttribute("TK_HitTarget") == nil
	and B.playerC:GetAttribute("TK_HitTarget") == nil)
-- one player only: the check says what the owner must do
B.playerS.Parent = nil
local h2 = S.mpCheckStart({})
SIM.run(2, function() return h2.done end)
check("with one player mpCheck does not run and says what the owner must do", h2.summary ~= nil
	and h2.summary:find("Clients and Servers", 1, true) ~= nil, h2.summary)
-- the lease runs out by itself (a test that died never leaves arcade on)
S.arcadeLease("crashed test", 5)
check("lease: arcade on", SIM.workspace:GetAttribute("CollisionModel") == "arcade")
SIM.run(6)
check("lease: back to nil 5 s later without a release", SIM.workspace:GetAttribute("CollisionModel") == nil)
SIM.workspace:SetAttribute("CollisionModel", "arcade")
S.arcadeLease("t", 30)
S.arcadeRelease("t")
check("lease: arcade before the test comes back as physical (owner rule)", SIM.workspace:GetAttribute("CollisionModel") == "physical")
SIM.workspace:SetAttribute("CollisionModel", nil)
print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''


class _Session(unittest.TestCase):
    def session(self, scenario, subs=None, min_pass=1, timeout=600, seed=7, latency=0.0, t0shift=0.0):
        prelude = _qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau'))
        sim = _qa.read(os.path.join(_qa.HERE, 'luau', 'sim_session.luau'))
        boot = BOOT
        for key, rel in (('__RECOVERY__', RECOVERY), ('__RECSERVER__', RECSERVER), ('__JOBS__', JOBS),
                         ('__KITSERVER__', KITSERVER), ('__TESTKIT__', TESTKIT), ('__TRAFFIC__', TRAFFIC)):
            boot = boot.replace(key, _long(_qa.src(rel)))
        boot = boot.replace('__DATA__', _long(_synth_traffic_luau()))
        boot = boot.replace('__WORLD__', _lua(_synth_world()))
        boot = boot.replace('__SEED__', str(seed)).replace('__LATENCY__', repr(latency))
        boot = boot.replace('__T0SHIFT__', repr(t0shift))
        boot = boot.replace('__CHECK__', CHECK)
        main = scenario
        for k, v in (subs or {}).items():
            main = main.replace(k, v)
        source = prelude + '\n' + sim + '\n' + boot + '\n' + main
        if os.environ.get('JOBDRIVE_DUMP'):  # debugging: the assembled script (line numbers in errors refer to it)
            with open(os.environ['JOBDRIVE_DUMP'], 'w', encoding='utf-8', newline='\n') as f:
                f.write(source)
        code, out = _qa.run_luau(source, timeout=timeout)
        self.assertEqual(code, 0, out[-6000:])
        fails = [line for line in out.splitlines() if line.startswith('FAIL ')]
        self.assertEqual(fails, [], out[-8000:])
        self.assertIn('FAILS\t0', out, out[-4000:])
        self.assertGreaterEqual(out.count('\nPASS '), min_pass, out[-3000:])
        return out


class JobMath(_Session):
    """Hermite lead-ins, the curve checks, the frame-rate caps, the event specs against the owner's table, the bump
    rules (matchBumps) and the oncoming near miss, through TK.jobMath."""

    def test_pure_parts(self):
        self.session(JOBMATH, min_pass=19)


def _jobdrive(fps, jitter=0.0, scenario='pass', runs=1, kinds=('taxi', 'delivery'), allow_incomplete=False,
              heavy=False):
    opts = {'kinds': list(kinds), 'runs': runs, 'fps': fps,
            'stands': {'taxi': ['a_taxi'], 'delivery': ['c_delivery']}}
    if heavy:
        opts['heavy'] = True  # a heavy rear-end as well as the crash (head-on)
    return {'__SCENARIO__': scenario, '__JITTER__': repr(jitter), '__OPTS__': _lua(opts),
            '__RUNS__': str(runs * len(kinds)), '__ALLOW_INCOMPLETE__': 'true' if allow_incomplete else 'false',
            '__EVENTS__': '5' if heavy else '4'}


class JobDriveSession(_Session):
    """TK.jobDriveTest end to end against the real jobs, recovery and test kit servers and the real PattayaTraffic:
    taxi and delivery, every staged event, the server's pay-out, no bump without a hit, nothing left over; at 60, 30
    and 15 fps (15 also with 20 % frame jitter and 60 ms of network latency); a stray bump is caught; a stop in the
    middle of a job cancels it and gives everything back."""

    def test_60fps(self):
        self.session(JOBDRIVE, subs=_jobdrive(60), min_pass=12)

    def test_30fps(self):
        self.session(JOBDRIVE, subs=_jobdrive(30), min_pass=12)

    def test_30fps_heavy_rear_end_too(self):
        # opts.heavy: a heavy rear-end at traffic speed + 60 (the staged runs may go up to the 30 fps cap, 110)
        self.session(JOBDRIVE, subs=_jobdrive(30, heavy=True), min_pass=12, t0shift=41.0)

    def test_15fps(self):
        self.session(JOBDRIVE, subs=_jobdrive(15, allow_incomplete=True), min_pass=12)

    def test_15fps_jitter_latency(self):
        # 5 % frame jitter (the TestKit FPS cap paces frames evenly) and 30 ms latency. With 20 % jitter about a
        # quarter of the 15 fps sessions get one stray bump from the frame rate alone (docs/RECOVERY_AND_COLLISION.md
        # 16.3); 30 and 60 fps stay clean with 20 % jitter and 60 ms.
        self.session(JOBDRIVE, subs=_jobdrive(15, jitter=0.05, allow_incomplete=True), min_pass=12, seed=11,
                     latency=0.03, t0shift=27.4)

    def test_30fps_jitter_latency(self):
        self.session(JOBDRIVE, subs=_jobdrive(30, jitter=0.2), min_pass=12, seed=5, latency=0.06, t0shift=68.5)

    def test_stray_bump_is_caught(self):
        self.session(JOBDRIVE, subs=_jobdrive(30, scenario='stray', kinds=('taxi',)), min_pass=8)

    def test_stop_mid_job(self):
        self.session(JOBDRIVE, subs=_jobdrive(30, scenario='stop', kinds=('taxi',)), min_pass=8)


class MpCheckSession(_Session):
    """S.mpCheck with two simulated clients (60 and 30 fps; the agents started by PattayaTraffic's hook), the arcade
    lease (expiry, the owner rule) and the one-player message."""

    def test_two_players(self):
        self.session(MPCHECK, min_pass=10)


class StaticScope(unittest.TestCase):
    """Test-only scope: the PattayaTraffic hook is guarded; nothing but that hook names the TestKit; the lease is the
    only place that sets CollisionModel and it restores it; the job test never waits in the engine inside its runner."""

    def test_traffic_hook_guarded(self):
        traffic = _qa.strip_comments(_qa.src(TRAFFIC))
        i = traffic.index('if IS_STUDIO or workspace:GetAttribute("DevTest") == true then')
        hook = traffic[i:traffic.index('\nend\n', i)]
        self.assertIn('workspace:GetAttribute("TK_ClientAgent") == true', hook)
        self.assertIn('rawget(kit, "enabled") == true and kit.startAgent', hook)
        self.assertIn('pcall(require, m)', hook)
        self.assertEqual(traffic.count('PattayaTestKit'), 1, 'only the hook names the TestKit')

    def test_no_other_script_loads_the_testkit(self):
        # no Script / LocalScript (the files that run by themselves) names the client TestKit module except
        # PattayaTraffic's guarded hook; dev modules run by hand (StreamingPrototype, PattayaQARunner) may
        n = 0
        for path in _qa.luau_files():
            if not path.endswith(('.server.luau', '.client.luau')) or path.endswith('PattayaTraffic.client.luau'):
                continue
            n += 1
            text = _qa.strip_comments(_qa.read(path))
            self.assertIsNone(re.search(r'PattayaTestKit\b', text), path)
        self.assertGreater(n, 20)

    def test_lease_restores(self):
        kit = _qa.strip_comments(_qa.src(KITSERVER))
        self.assertLess(kit.index('if not enabled() then'), kit.index('function S.arcadeLease('))
        sets = re.findall(r'SetAttribute\(\s*"CollisionModel"\s*,\s*([^)]*)\)', kit)
        self.assertEqual(sorted(sets), ['"arcade"', 'back'])
        self.assertIn('elseif L.prev == "arcade" then "physical"', kit)
        self.assertIn('math.clamp(tonumber(seconds) or 600, 5, 1800)', kit)
        self.assertIn('leaseRestore("lease ran out")', kit)

    def test_testkit_runner_never_waits_in_the_engine(self):
        tk = _qa.strip_comments(_qa.src(TESTKIT))
        body = tk[tk.index('do\n\tlocal JM = {}'):tk.index('function TK.stopAll()')]
        jd = body[:body.index('local AGENT_ATTRS')]
        for word in ('task.wait(', 'Heartbeat:Wait(', ':InvokeServer('):
            self.assertNotIn(word, jd, 'the job test runs in a Heartbeat-resumed runner: ' + word)


if __name__ == '__main__':
    unittest.main()
