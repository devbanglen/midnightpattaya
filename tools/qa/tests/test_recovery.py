"""Recovery Kit + arcade traffic hits (docs/RECOVERY_AND_COLLISION.md).

Runs the pure decision functions of ReplicatedStorage/PattayaRecovery.luau in the luau CLI (hit classification by
closing speed / angle, box overlap + sweep, upright timing, stuck / off-road detection, R and rescue cooldowns, the
rescue trail choice and the checkpoint clamp, the deterministic traffic positions, the TrafficHit report check), plus
static checks of the wiring in CarController, PattayaTraffic and PattayaRecoveryServer."""
import os
import re
import unittest

import _qa

MOD = os.path.join('ReplicatedStorage', 'PattayaRecovery.luau')
CAR = os.path.join('StarterPlayer', 'StarterPlayerScripts', 'CarController.client.luau')
TRAFFIC = os.path.join('StarterPlayer', 'StarterPlayerScripts', 'PattayaTraffic.client.luau')
SERVER = os.path.join('ServerScriptService', 'PattayaRecoveryServer.server.luau')
TESTKIT = os.path.join('ReplicatedStorage', 'PattayaTestKit.luau')

HARNESS = r'''
local R = require("./PattayaRecovery")
local attrs = {}
R._attr = function(name) return attrs[name] end
local fails, passes = 0, 0
local function check(name, cond, detail)
	if cond then
		passes += 1
		print("PASS " .. name)
	else
		fails += 1
		print("FAIL " .. name .. (if detail then " :: " .. tostring(detail) else ""))
	end
end
local function near(a, b, eps) return math.abs(a - b) <= (eps or 1e-6) end
local function frame(f, n) return f ~= nil and math.abs(f - n) <= 1 end -- float sums of dt land on n or n + 1
local cfg = R.config()

-- config ---------------------------------------------------------------------------------------------------------
check("default collision model is physical", R.get("CollisionModel") == "physical" and not R.arcade())
check("recovery on by default", R.enabled() and cfg.Recovery_UprightDelay == 1.5 and cfg.Recovery_StuckTime == 4)
attrs.CollisionModel = "arcade"
attrs.Recovery_UprightDelay = 2
attrs.Recovery_StuckTime = "x" -- wrong type: ignored
check("attributes override", R.arcade() and R.get("Recovery_UprightDelay") == 2 and R.get("Recovery_StuckTime") == 4)
attrs.Recovery_Enabled = false
check("master switch off", not R.enabled())
attrs = {}
cfg = R.config()

-- closing speed --------------------------------------------------------------------------------------------------
-- traffic heading +X at 45; I come from behind at 150: the normal points from the traffic car back to me (-X)
local vc, ang = R.closingSpeed(150, 0, 45, 0, -1, 0)
check("rear-end 150 into 45 -> vc 105", near(vc, 105) and near(ang, 90), vc)
vc = R.closingSpeed(-150, 0, 45, 0, 1, 0)
check("head-on 150 vs 45 -> vc 195", near(vc, 195), vc)
-- side-swipe: overtaking at 150 at 5 degrees into its side (normal -Z)
local a5 = math.rad(5)
local sv, sa = R.closingSpeed(150 * math.cos(a5), 150 * math.sin(a5), 45, 0, 0, -1)
check("5 degree swipe at 150 is shallow", sv < 15 and sa < 15, sv .. " " .. sa)
vc = R.closingSpeed(150, 0, 45, 0, 1, 0)
check("moving away -> vc 0", vc == 0)

-- classification ---------------------------------------------------------------------------------------------------
local h = R.classifyHit({vc = 10, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("vc 10 -> scrape 8%", h.tier == "scrape" and near(h.loss, 0.08) and h.control == 0, h.tier)
h = R.classifyHit({vc = 30, approachDeg = 10, facingDot = 1, side = 1, front = true}, cfg)
check("glancing 10 degrees -> scrape", h.tier == "scrape", h.tier)
h = R.classifyHit({vc = 30, approachDeg = 60, facingDot = 1, side = 1, front = true}, cfg)
check("vc 30 -> light 20%", h.tier == "light" and near(h.loss, 0.2) and near(h.control, 0.25) and near(h.steer, 0.7)
	and h.yaw >= 8 and h.yaw <= 15 and not h.slide, h.tier .. " " .. h.loss)
h = R.classifyHit({vc = 45, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("vc 45 -> heavy 45%, 45 deg, 0.6 s", h.tier == "heavy" and near(h.loss, 0.45) and near(h.yaw, 45)
	and near(h.control, 0.6) and near(h.steer, 0.3) and h.slide, h.tier .. " " .. h.loss .. " " .. h.yaw)
h = R.classifyHit({vc = 130, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("vc 130 -> heavy 70%, 120 deg, 1.2 s", near(h.loss, 0.7) and near(h.yaw, 120) and near(h.control, 1.2))
h = R.classifyHit({vc = 300, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("vc 300 capped at the heavy maximum", near(h.loss, 0.7) and near(h.yaw, 120) and near(h.control, 1.2))
h = R.classifyHit({vc = 87.5, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("vc 87.5 -> half way", near(h.loss, 0.575) and near(h.yaw, 82.5) and near(h.control, 0.9), h.loss)
h = R.classifyHit({vc = 105, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
check("rear-end at 150 (vc 105) is heavy", h.tier == "heavy" and h.loss > 0.6 and h.loss < 0.65, h.loss)
h = R.classifyHit({vc = 195, approachDeg = 90, facingDot = -1, side = 1, front = true}, cfg)
check("head-on 150 -> 85%, bounce 10, 1 s", h.tier == "headon" and near(h.loss, 0.85) and h.bounce == 10
	and near(h.control, 1) and math.abs(h.yaw) <= 20, h.tier)
h = R.classifyHit({vc = 195, approachDeg = 90, facingDot = -0.5, side = 1, front = true}, cfg)
check("60 degrees off head-on is heavy, not head-on", h.tier == "heavy", h.tier)
h = R.classifyHit({vc = 80, approachDeg = 90, facingDot = -1, side = 1, front = true}, cfg)
check("head-on below vc 90 is heavy", h.tier == "heavy", h.tier)
-- spin direction: + = nose left
local fr = R.classifyHit({vc = 60, approachDeg = 90, facingDot = 1, side = 1, front = true}, cfg)
local fl = R.classifyHit({vc = 60, approachDeg = 90, facingDot = 1, side = -1, front = true}, cfg)
local rr = R.classifyHit({vc = 60, approachDeg = 90, facingDot = 1, side = 1, front = false}, cfg)
check("front-right hit turns the nose left, front-left right", fr.yaw > 0 and fl.yaw < 0)
check("rear-quarter hit turns the nose towards and spins more", rr.yaw < 0 and math.abs(rr.yaw) > math.abs(fr.yaw))
local lr = R.classifyHit({vc = 30, approachDeg = 60, facingDot = 1, side = -1, front = false}, cfg)
check("light hit always turns away", lr.yaw < 0)
-- tuning attribute moves the table
attrs.Arcade_LightLoss = 0.3
check("Arcade_LightLoss attribute", near(R.classifyHit({vc = 30, approachDeg = 60}, R.config()).loss, 0.3))
attrs = {}

-- velocity after the hit -------------------------------------------------------------------------------------------
local vx, vz = R.impactVelocity(150, 0, -1, 0, {loss = 0.2, bounce = 0})
check("light hit at 150 -> 120", near(vx, 120) and near(vz, 0), vx)
local hh = R.classifyHit({vc = 195, approachDeg = 90, facingDot = -1, side = 1}, cfg)
vx, vz = R.impactVelocity(150, 0, -1, 0, hh)
check("head-on at 150 -> 10 studs/s backwards", near(vx, -10) and near(vz, 0), vx)
local T, w0 = R.spinProfile(90, 1.0)
check("spin profile integrates to the kick", near(w0 * T / 2, math.rad(90)) and T <= 0.6)

-- box overlap --------------------------------------------------------------------------------------------------------
-- traffic box at the origin facing -Z (half 3.3 x 7); my car (half 3.5 x 7.5)
local hit, depth, nx, nz = R.obbOverlap(0, 14, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("overlap behind: depth 0.5, normal +Z", hit and near(depth, 0.5) and near(nx, 0) and near(nz, 1), depth)
hit = R.obbOverlap(0, 14.4, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("just touching boxes", hit)
hit = R.obbOverlap(0, 14.7, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("0.2 studs apart: no overlap", not hit)
hit, depth, nx, nz = R.obbOverlap(6, 0, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("side overlap: normal +X", hit and near(nx, 1) and near(depth, 0.8), depth)
local s45 = math.sqrt(0.5)
hit = R.obbOverlap(9, 9, s45, -s45, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("rotated car corner-to-corner", hit == R.obbOverlap(9, 9, s45, -s45, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7))
hit = R.obbOverlap(10, 0, 1, 0, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("crossing car 10 studs to the side (nose in) overlaps", hit)
-- sweep: 24 studs sideways in one frame straight through the traffic car
local plain = R.obbOverlap(12, 0, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
local swept = R.sweptOverlap(-12, 0, 12, 0, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7)
check("sweep catches a skip-through", (not plain) and swept)
check("sweep ignores a teleport", not R.sweptOverlap(-100, 0, 12, 0, 0, -1, 3.5, 7.5, 0, 0, 0, -1, 3.3, 7))

-- auto-upright timing ------------------------------------------------------------------------------------------------
local st = {upside = 0, tilt = 0}
local dt = 1 / 60
local fired = nil
for i = 1, 200 do
	if R.uprightTick(st, -0.9, 30, dt, false, cfg) then fired = i break end
end
check("upside down (at speed) -> upright at 1.5 s", frame(fired, 90), fired)
st = {upside = 0, tilt = 0}
fired = nil
for i = 1, 200 do
	if R.uprightTick(st, 0.3, 5, dt, false, cfg) then fired = i break end
end
check("tilted 72 deg and slow -> upright at 1.5 s", frame(fired, 90), fired)
st = {upside = 0, tilt = 0}
fired = nil
for i = 1, 300 do
	if R.uprightTick(st, 0.3, 40, dt, false, cfg) then fired = i break end
end
check("tilted but fast: no upright", fired == nil)
st = {upside = 0, tilt = 0}
fired = nil
for i = 1, 300 do
	if R.uprightTick(st, 0.6, 0, dt, false, cfg) then fired = i break end
end
check("53 degrees: no upright", fired == nil)
st = {upside = 0, tilt = 0}
for i = 1, 80 do R.uprightTick(st, -1, 0, dt, false, cfg) end
R.uprightTick(st, -1, 0, dt, true, cfg) -- anchored / grace: resets
fired = nil
for i = 1, 200 do
	if R.uprightTick(st, -1, 0, dt, false, cfg) then fired = i break end
end
check("blocked frame resets the timer", frame(fired, 90), fired)
st = {upside = 0, tilt = 0}
fired = nil
for i = 1, 120 do
	-- rolling over and back within a second never fires
	if R.uprightTick(st, if i < 50 then -0.5 else 0.95, 30, dt, false, cfg) then fired = i end
end
check("a short roll that rights itself never fires", fired == nil)

-- stuck / off-road ---------------------------------------------------------------------------------------------------
local sk = {t = 0}
fired = nil
for i = 1, 400 do
	if R.stuckTick(sk, 100 + i * 0.001, 50, 1, dt, cfg) then fired = i break end
end
check("throttle held, not moving -> stuck at 4 s", frame(fired, 240), fired)
sk = {t = 0}
fired = nil
for i = 1, 900 do
	-- pushing a wall, creeping 1 stud/s: 4 studs in 4 s
	if R.stuckTick(sk, i * dt, 0, 1, dt, cfg) then fired = i break end
end
check("creeping 1 stud/s is stuck after 4 s (< 6 studs moved)", frame(fired, 240), fired)
sk = {t = 0}
fired = nil
for i = 1, 900 do
	-- 2 studs/s: 6 studs every 3 s, the timer restarts each time
	if R.stuckTick(sk, i * dt * 2, 0, 1, dt, cfg) then fired = i break end
end
check("2 studs/s is not stuck (the window restarts every 6 studs)", fired == nil, fired)
sk = {t = 0}
fired = nil
for i = 1, 900 do
	if R.stuckTick(sk, i * dt * 3, 0, 1, dt, cfg) then fired = i break end
end
check("moving 3 studs/s is not stuck", fired == nil, fired)
sk = {t = 0}
fired = nil
for i = 1, 600 do
	if R.stuckTick(sk, 0, 0, if i % 120 == 0 then 0 else 1, dt, cfg) then fired = i break end
end
check("releasing the throttle restarts the stuck timer", fired == nil, fired)
sk = {t = 0}
fired = nil
for i = 1, 600 do
	if R.stuckTick(sk, 0, 0, 0.3, dt, cfg) then fired = i break end
end
check("no throttle (waiting at a light) is never stuck", fired == nil)
local orr = {t = 0}
fired = nil
for i = 1, 600 do
	if R.offRoadTick(orr, false, 10, dt, cfg) then fired = i break end
end
check("off-road and slow -> 6 s", frame(fired, 360), fired)
orr = {t = 0}
fired = nil
for i = 1, 600 do
	if R.offRoadTick(orr, false, 60, dt, cfg) then fired = i break end
end
check("fast on the beach is fine", fired == nil)
orr = {t = 0}
fired = nil
for i = 1, 600 do
	if R.offRoadTick(orr, false, 0, dt, cfg, 0) then fired = i break end
end
check("parked off-road with no throttle is fine", fired == nil)
orr = {t = 0}
fired = nil
for i = 1, 600 do
	if R.offRoadTick(orr, false, 5, dt, cfg, 1) then fired = i break end
end
check("off-road, slow, throttle held -> 6 s", frame(fired, 360), fired)
check("fell off the map", R.fallen(-31, cfg) and not R.fallen(1, cfg))

-- manual R --------------------------------------------------------------------------------------------------------
local ok, why = R.resetAllowed(10, nil, 1, 0, cfg)
check("R when stopped", ok)
ok, why = R.resetAllowed(10, 9, 1, 0, cfg)
check("R cooldown 2 s", not ok and why == "cooldown")
ok = R.resetAllowed(11.01, 9, 1, 0, cfg)
check("R after the cooldown", ok)
ok, why = R.resetAllowed(10, nil, 1, 80, cfg)
check("R refused when level and fast", not ok and why == "level")
ok = R.resetAllowed(10, nil, 0.8, 80, cfg)
check("R when tilted 37 deg at speed", ok)
ok = R.resetAllowed(10, nil, 0.9, 80, cfg)
check("R refused when tilted 26 deg at speed", not ok)
attrs.Recovery_ResetCooldown = 0
ok = R.resetAllowed(10, 9.99, 1, 0, R.config())
check("cooldown 0 = unlimited", ok)
attrs = {}
check("rescue cooldown left", near(R.cooldownLeft(15, 10, 10), 5) and R.cooldownLeft(25, 10, 10) == 0
	and R.cooldownLeft(1, nil, 10) == 0)

-- rescue trail choice -------------------------------------------------------------------------------------------------
-- driving +X at 50 studs/s, 10 Hz, for 6 s, then stuck at x = 300 for 4 s
local crumbs = {}
for i = 0, 60 do
	table.insert(crumbs, {t = i * 0.1, x = i * 5, y = 3.8, z = 0, hx = 1, hz = 0, speed = 50, up = 1})
end
for i = 61, 100 do
	table.insert(crumbs, {t = i * 0.1, x = 300, y = 3.8, z = 0, hx = 1, hz = 0, speed = 0, up = 1})
end
local now = 10
local idx, path = R.pickCrumb(crumbs, now, 301, 1, {}, nil)
check("rescue picks the last driven spot behind the car", idx and crumbs[idx].x < 300 and crumbs[idx].x >= 290
	and crumbs[idx].speed >= 10, idx and crumbs[idx].x)
-- every candidate the rescue can return is a spot the car has already driven: never further along +X than now
local maxX = -math.huge
for i = 1, #crumbs do
	local j = R.pickCrumb(crumbs, now, 301, 1, {minDist = 0}, function(c) return c == crumbs[i] end)
	if j then maxX = math.max(maxX, crumbs[j].x) end
end
check("no rescue spot is ahead of the car", maxX <= 301, maxX)
-- next checkpoint at x = 310 (+X route): a spot inside 26 + 25 studs of it is refused
idx = R.pickCrumb(crumbs, now, 301, 1, {}, function(c) return R.cpAllows(c.x - 310, c.z, cfg) end)
check("checkpoint clamp keeps 51 studs before the next checkpoint", idx and crumbs[idx].x <= 259,
	idx and crumbs[idx].x)
-- loop gate at x = 310 facing +X: gate object space z = -(x - 310) (forward = -Z)
idx = R.pickCrumb(crumbs, now, 301, 1, {}, function(c) return R.gateAllows(c.z, -(c.x - 310), 20, cfg) end)
check("gate clamp keeps 25 studs before the next gate", idx and crumbs[idx].x <= 285, idx and crumbs[idx].x)
check("gate clamp: 10 studs before the gate refused", not R.gateAllows(0, 10, 20, cfg))
check("gate clamp: just past the gate refused", not R.gateAllows(0, -5, 20, cfg))
check("gate clamp: 30 before allowed, beside the corridor allowed", R.gateAllows(0, 30, 20, cfg)
	and R.gateAllows(40, 5, 20, cfg))
idx, path = R.pickCrumb(crumbs, now, 301, 1, {maxPath = 50}, function(c) return c.x < 200 end)
check("trail longer than maxPath -> nothing", idx == nil and path > 50)
local young = {{t = 9.5, x = 280, y = 3.8, z = 0, hx = 1, hz = 0, speed = 50, up = 1}}
check("a spot younger than 1 s is not used", R.pickCrumb(young, 10, 300, 0, {}, nil) == nil)
local rolled = {{t = 5, x = 280, y = 3.8, z = 0, hx = 1, hz = 0, speed = 50, up = 0.3}}
check("a spot where the car was tipped is not used", R.pickCrumb(rolled, 10, 300, 0, {}, nil) == nil)
local close = {{t = 5, x = 297, y = 3.8, z = 0, hx = 1, hz = 0, speed = 50, up = 1}}
check("a spot closer than 8 studs is not used", R.pickCrumb(close, 10, 300, 0, {}, nil) == nil)

-- heading -------------------------------------------------------------------------------------------------------------
local tx, tz = R.tangentAt({0, 0, 10, 0, 10, 10}, 15)
check("tangent on the second segment", near(tx, 0) and near(tz, 1))
tx, tz = R.alignHeading(0, 1, 0.1, -0.9)
check("road direction follows the car's heading", near(tx, 0) and near(tz, -1))

-- deterministic traffic -----------------------------------------------------------------------------------------------
local routes = R.buildTrafficRoutes({{pts = {0, 0, 100, 0, 100, 100, 0, 100, 0, 0}, speed = 50, phase = 0, kinds = {0, 1}}}, 1000, 0)
local near1 = R.trafficNear(routes, 1, 1050, 0, 5)
check("traffic car 1 at s = 50 after 1 s, heading +X", #near1 == 1 and near(near1[1].x, 1050) and near(near1[1].z, 0)
	and near(near1[1].lx, 1) and near1[1].kind == 0, #near1)
local near2 = R.trafficNear(routes, 0, 1100, 100, 5)
check("traffic car 2 half a loop on, heading -X", #near2 == 1 and near(near2[1].lx, -1) and near2[1].kind == 1, #near2)
check("no traffic far away", #R.trafficNear(routes, 0, 5000, 5000, 50) == 0)

-- TrafficHit report check ---------------------------------------------------------------------------------------------
local base = {now = 10, lastAt = nil, tier = "heavy", vc = 90, speedBefore = 140, serverPeak = 140, trafficDist = 12}
check("valid heavy report", (R.validateHitReport(base, cfg)))
local function with(k, v)
	local t = table.clone(base)
	t[k] = v
	return t
end
check("light hits are not reported", not R.validateHitReport(with("tier", "light"), cfg))
check("report rate limit 1 s", not R.validateHitReport(with("lastAt", 9.5), cfg))
check("report while slow refused", not R.validateHitReport(with("serverPeak", 20), cfg))
check("report with an absurd vc refused", not R.validateHitReport(with("vc", 300), cfg))
check("report with no traffic near refused", not R.validateHitReport(with("trafficDist", 200), cfg))
check("report without traffic data allowed", (R.validateHitReport(with("trafficDist", nil), cfg)))
check("NaN vc refused", not R.validateHitReport(with("vc", 0 / 0), cfg))

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''


def src(rel):
    return _qa.src(rel)


class RecoveryLogic(unittest.TestCase):
    def test_pure_functions_in_luau(self):
        code, out = _qa.run_luau(HARNESS, {'PattayaRecovery.luau': src(MOD)})
        self.assertEqual(code, 0, out[-3000:])
        fails = [line for line in out.splitlines() if line.startswith('FAIL ')]
        self.assertEqual(fails, [], out[-3000:])
        self.assertIn('FAILS\t0', out, out[-3000:])
        self.assertGreaterEqual(out.count('PASS '), 60, out[-2000:])


STAGED = r'''
-- Studio cases of 2026-10-21 (docs/test_results/recovery_kit_studio.txt) replayed offline: the traffic car moves on
-- its route by the same formula as PattayaTraffic, my car follows PattayaRecovery.stagePlan (what TK.hitTest
-- drives), and every frame runs PattayaRecovery.hitFromWorld (what PattayaTraffic runs). The first touch is
-- classified with the owner's table.
local R = require("./PattayaRecovery")
R._attr = function() return nil end
local cfg = R.config()
local fails, passes = 0, 0
local function check(name, cond, detail)
	if cond then passes += 1 print("PASS " .. name)
	else fails += 1 print("FAIL " .. name .. (if detail then " :: " .. tostring(detail) else "")) end
end

-- a long straight loop (heading +X on the south side) and a round one (radius 300, 48 points)
local straight = R.buildTrafficRoutes({{pts = {0, 0, 3000, 0, 3000, 600, 0, 600, 0, 0}, speed = 45, phase = 0,
	kinds = {0}}}, 0, 0)[1]
local circ = {}
for i = 0, 48 do
	local a = i / 48 * 2 * math.pi
	table.insert(circ, 300 * math.cos(a))
	table.insert(circ, 300 * math.sin(a))
end
local round = R.buildTrafficRoutes({{pts = circ, speed = 45, phase = 0, kinds = {0}}}, 0, 0)[1]

local SH = R.TRAFFIC_SHAPES[0]
local function trafficAt(route, s0, t0, t, vT)
	local s = s0 + vT * (t - t0)
	local x, z = R.routePoint(route, s)
	local x2, z2 = R.routePoint(route, s + 6) -- heading as PattayaTraffic: towards the point 6 studs on
	local lx, lz = x2 - x, z2 - z
	local m = math.sqrt(lx * lx + lz * lz)
	return x, z, lx / m, lz / m
end

-- returns the first hit's info + classification, the time of it, and the planned meeting time
local function run(route, s0, mode, speed, opts, fps, reverseTraffic, vT, kind)
	opts = opts or {}
	vT = vT or 45
	local SH = R.TRAFFIC_SHAPES[kind or 0]
	local plan, meet = R.stagePlan({route = route, s0 = s0, t0 = 0, vT = vT, halfWid = SH.wid / 2, halfLen = SH.len / 2,
		speed = speed, mode = mode, lead = opts.lead, offset = opts.offset, angle = opts.angle,
		alignCorner = opts.alignCorner})
	local dt = 1 / fps
	local px, pz = nil, nil
	local t = 0
	while t < meet + 2 do
		t += dt
		local x, z, dx, dz = plan(t)
		local m = math.sqrt(dx * dx + dz * dz)
		dx, dz = dx / m, dz / m
		local tx, tz, tlx, tlz = trafficAt(route, s0, 0, t, vT)
		if reverseTraffic then tlx, tlz = -tlx, -tlz end
		local info, rx, rz = R.hitFromWorld({x = x, z = z, lx = dx, lz = dz, vx = dx * speed, vz = dz * speed},
			{x = tx, z = tz, lx = tlx, lz = tlz, speed = vT, halfWid = SH.wid / 2, halfLen = SH.len / 2}, px, pz)
		px, pz = rx, rz
		if info then
			local res = R.classifyHit(info, cfg)
			local wx, wz = R.impactVelocity(dx * speed, dz * speed, info.nx, info.nz, res)
			res.after = math.sqrt(wx * wx + wz * wz)
			-- the contact normal against the traffic car's own axes, and my centre in its frame
			info.lateralN = math.abs(info.nx * -tlz + info.nz * tlx)
			info.relAlong = (x - tx) * tlx + (z - tz) * tlz
			return info, res, t, meet
		end
	end
	return nil, nil, t, meet
end

local function near(a, b, eps) return math.abs(a - b) <= eps end

-- a third route: straight, a 4-stud lane change over 30 studs, straight, then a 90 degree bend of radius 400
local sc = {0, 0, 800, 0, 830, 4, 1200, 4}
for i = 1, 24 do
	local a = i / 24 * math.pi / 2
	table.insert(sc, 1200 + 400 * math.sin(a))
	table.insert(sc, 404 - 400 * math.cos(a))
end
for _, q in {1600, 2400, 0, 2400} do table.insert(sc, q) end
table.insert(sc, 0)
table.insert(sc, 0)

-- the owner's table rows (TK.HIT_MATRIX); expected values come from the geometry (R.expectedStaged)
local CASES = {
	{"rear", 70}, {"rear", 100}, {"rear", 150}, {"rear", 200}, {"rear", 150, {offset = 2}},
	{"head", 100}, {"head", 150}, {"head", 200},
	{"side", 150, {angle = 5}}, {"side", 150, {angle = 20}}, {"side", 70, {angle = 25}}, {"side", 100, {angle = 10}},
}
local THRESHOLDS = {15, 45, 90}
for _, vT in {38, 45, 55} do
	local mk = function(pts) return R.buildTrafficRoutes({{pts = pts, speed = vT, phase = 0, kinds = {0}}}, 0, 0)[1] end
	local ROUTES = {
		{"straight", mk({0, 0, 3000, 0, 3000, 600, 0, 600, 0, 0}), 500, false},
		{"round", mk(circ), 400, true},
		{"lanechange", mk(sc), 760, true},   -- meets at / through the lane change
		{"bend", mk(sc), 1400, true},        -- meets on the radius-400 bend
	}
	for _, route in ROUTES do
		for _, fps in {60, 30, 20, 15} do
			for ci, c in CASES do
				local mode, speed, opts = c[1], c[2], c[3]
				local kind = (ci + fps) % 3 -- every row meets sedans, songthaews and vans across the frame rates
				local want, wantHit = R.expectedStaged(mode, speed, opts and opts.angle, vT, cfg)
				local name = ("%s vT%d k%d %s %d @%dfps%s"):format(route[1], vT, kind, mode, speed, fps,
					if opts and opts.angle then " a" .. opts.angle elseif opts and opts.offset then " off" .. opts.offset else "")
				local info, res, t, meet = run(route[2], route[3], mode, speed, opts, fps, false, vT, kind)
				if not info then
					check(name .. " touches", false, "no touch")
					continue
				end
				check(name .. " touches when planned", math.abs(t - meet) < 0.25 + 1 / fps, ("t %.2f meet %.2f"):format(t, meet))
				local nearEdge = false
				for _, th in THRESHOLDS do
					if math.abs(wantHit.vc - th) < 3 then nearEdge = true end
				end
				if not nearEdge then
					check(name .. " -> " .. want.tier, res.tier == want.tier, ("%s vc %.1f (want %.1f) angle %.0f facing %.2f")
						:format(res.tier, info.vc, wantHit.vc, info.approachDeg, info.facingDot))
					if want.bounce == 0 then
						check(name .. " loss", near(res.loss, want.loss, if route[4] then 0.04 else 0.01),
							("%.3f vs %.3f"):format(res.loss, want.loss))
					else
						check(name .. " head-on near stop + bounce", res.after <= 10.5 + (if route[4] then 0.05 * speed else 0), res.after)
					end
				end
				if mode == "side" then
					-- my leading corner meets the middle of its side: the normal is its side axis
					check(name .. " side normal", info.lateralN > (if route[4] then 0.95 else 0.99), info.lateralN)
				end
				if res.tier == "heavy" then
					check(name .. " spin in the 45-120 band", math.abs(res.yaw) >= 45 and math.abs(res.yaw) <= 120, res.yaw)
				end
			end
		end
	end
end

-- Studio round 3 rows (docs/test_results/recovery_kit_studio.txt, ~15 Hz) as regressions --------------------------
local straight45 = straight
-- rows "rear 100 / head 100 / head 200: scrape vc=0 0->0": a hit at the start spot, before the approach
local ok, why = R.acceptStagedHit({hitT = 9.9, approachT = 10, meet = 11.5, frameDt = 1 / 15, hitX = 0, hitZ = 0,
	targetX = 0, targetZ = 0})
check("studio r3 rear100/head100/head200: a hit before the approach is not the staged hit", not ok, why)
-- and a car parked on the start spot makes the lane "not clear" (the helper then picks another target or ghosts)
do
	local plan, meet = R.stagePlan({route = straight45, s0 = 500, t0 = 0, vT = 45, halfWid = 3.3, halfLen = 7,
		speed = 100, mode = "head"})
	local x0, z0 = plan(0)
	local parked = {route = R.buildTrafficRoutes({{pts = {x0 - 1, z0, x0 + 1, z0, x0 + 1, z0 + 1, x0 - 1, z0}, speed = 0,
		phase = 0, kinds = {0}}}, 0, 0)[1], s = 0, t = 0, speed = 0}
	check("studio r3 head100: a car on the start spot -> lane not clear", not R.plannedPathClear(plan, 0, meet, {parked}, 30))
	-- the same lane with nobody else is clear; an oncoming car in the next lane is not
	check("an empty lane is clear", R.plannedPathClear(plan, 0, meet, {}, 30))
	local oncoming = R.buildTrafficRoutes({{pts = {3000, 12, 0, 12, 0, 600, 3000, 600, 3000, 12}, speed = 45, phase = 0,
		kinds = {0}}}, 0, 0)[1]
	local rel = {route = oncoming, s = 3000 - 560, t = 0, speed = 45}
	local okClear, worst = R.plannedPathClear(plan, 0, meet, {rel}, 30)
	check("studio r3: an oncoming car 12 studs over, passing during the approach -> not clear", not okClear, worst)
end
-- rows "hit (NOT the target car)": a hit on another car is rejected, the target is accepted
ok = R.acceptStagedHit({hitT = 11.5, approachT = 10, meet = 11.5, frameDt = 1 / 15, hitX = 40, hitZ = 0,
	targetX = 0, targetZ = 0})
check("studio r3: a hit 40 studs from the target is another car", not ok)
ok = R.acceptStagedHit({hitT = 11.55, approachT = 10, meet = 11.5, frameDt = 1 / 15, hitX = 3, hitZ = 0,
	targetX = 0, targetZ = 0})
check("studio r3: the target hit one 15 Hz frame late is accepted", ok)
ok = R.acceptStagedHit({hitT = 12.6, approachT = 10, meet = 11.5, frameDt = 1 / 15, hitX = 0, hitZ = 0,
	targetX = 0, targetZ = 0})
check("a hit 1.1 s after the planned meeting is not the staged hit", not ok)
-- "side 150 a5 -> heavy vc 147" and "side 150 a20 -> scrape vc 0" were other cars; on the target at 15 Hz:
for _, fps in {15, 30, 60} do
	local _, r5 = run(straight45, 500, "side", 150, {angle = 5}, fps)
	check(("studio r3 side 150 a5 on the target @%d Hz -> scrape"):format(fps), r5 and r5.tier == "scrape", r5 and r5.tier)
	local i20, r20 = run(straight45, 500, "side", 150, {angle = 20}, fps)
	check(("studio r3 side 150 a20 on the target @%d Hz -> heavy"):format(fps), r20 and r20.tier == "heavy",
		r20 and (r20.tier .. " vc " .. i20.vc))
	local _, rh = run(straight45, 500, "head", 150, nil, fps)
	check(("studio r3 head 150 @%d Hz -> headon"):format(fps), rh and rh.tier == "headon", rh and rh.tier)
	local i70, r70 = run(straight45, 500, "side", 70, {angle = 25}, fps)
	check(("studio r3 side 70 a25 @%d Hz -> light 20%%"):format(fps), r70 and r70.tier == "light" and near(r70.loss, 0.2, 1e-6),
		r70 and (r70.tier .. " vc " .. i70.vc))
end
-- round 4 "side 100 a10 -> heavy": with the centres level the leading corner reaches the front corner of a 14-stud
-- car; the new alignment puts it on the middle of the side for every kind
for kind = 0, 2 do
	for _, c in {{100, 10}, {150, 5}, {150, 20}, {70, 25}} do
		local info, res = run(straight45, 500, "side", c[1], {angle = c[2]}, 60, false, 45, kind)
		local want = R.expectedStaged("side", c[1], c[2], 45, cfg)
		check(("studio r4 side %d a%d k%d -> %s on the side face"):format(c[1], c[2], kind, want.tier),
			info and res.tier == want.tier and info.lateralN > 0.99, info and ("%s n %.2f"):format(res.tier, info.lateralN))
	end
end
do
	local info = run(straight45, 500, "side", 100, {angle = 10, alignCorner = false}, 60, false, 45, 0)
	local info2 = run(straight45, 500, "side", 100, {angle = 10}, 60, false, 45, 0)
	print(("INFO old alignment side 100 a10: normal lateral %.2f, my centre %.1f studs along; new: %.2f, %.1f"):format(
		info and info.lateralN or -1, info and info.relAlong or 0, info2.lateralN, info2.relAlong))
	check("new side alignment: my centre is behind its centre (corner on the side middle)", info2.relAlong < -3,
		info2.relAlong)
end
-- round 4 "head 100 rejected -0.50 s": the planned meeting holds for every kind at 60 / 15 Hz
for kind = 0, 2 do
	for _, fps in {60, 15} do
		local info, _, t, meet = run(straight45, 500, "head", 100, nil, fps, false, 45, kind)
		check(("studio r4 head 100 k%d @%d Hz meets when planned"):format(kind, fps), info and math.abs(t - meet) < 0.1,
			("%.2f vs %.2f"):format(t, meet))
	end
end
local okR, whyR = R.acceptStagedHit({hitT = 10.5, approachT = 10, meet = 11, frameDt = 1 / 60, hitX = 30, hitZ = 0,
	targetX = 0, targetZ = 0})
check("a rejection names every reason (time and another car)", not okR and whyR:find("planned", 1, true)
	and whyR:find("another car", 1, true), whyR)

-- "side 70 a25: speed at the hit 37": the run-up started 33 studs off the lane (kerb); now at most 6 studs further
-- out than the touching distance
do
	for _, c in {{70, 25}, {150, 5}, {150, 20}, {100, 10}} do
		local a = math.rad(c[2])
		local plan = R.stagePlan({route = straight45, s0 = 500, t0 = 0, vT = 45, halfWid = 3.3, halfLen = 7, speed = c[1],
			mode = "side", angle = c[2]})
		local _, z0 = plan(0)
		local latC = 3.3 + 3.5 * math.cos(a) + 7.5 * math.sin(a)
		-- straight route heading +X: its right is (-lz, lx) = (0, 1) -> lateral = z
		check(("side %d a%d starts within 6 studs of the touching line (lateral %.1f, touch %.1f)"):format(c[1], c[2],
			z0, latC), z0 <= latC + 6 + 1e-6 and z0 > latC, z0)
	end
end

-- what the Studio "side 150 a20 -> headon -92 %" looks like: the same side approach into a car coming the other way
local info, res = run(straight, 500, "side", 150, {angle = 20}, 60, true)
check("a 20 degree side approach into an ONCOMING car is a heavy side hit, never a head-on", info and res.tier == "heavy"
	and info.vc > 45 and info.vc < 60, res and (res.tier .. " vc " .. info.vc))
for _, fps in {60, 30, 20} do
	info, res = run(straight, 500, "side", 150, {angle = 20}, fps, true)
	check("oncoming side hit at " .. fps .. " fps keeps the side normal", info and math.abs(info.nz) > 0.99, info and info.nz)
end
-- and "head 150 -> heavy": a head-on aimed 9 studs off the lane only clips the corner at an angle
info, res = run(straight, 500, "head", 150, {offset = 9}, 60)
check("an offset head-on that only clips the corner is not a full head-on", info == nil or res.tier ~= "headon"
	or info.facingDot <= -0.866, res and res.tier)

-- conventions, one by one (world numbers as PattayaTraffic passes them)
local me = {x = 0, z = 14, lx = 0, lz = -1, vx = 0, vz = -150}           -- behind a car heading -Z, nose to its tail
local tr = {x = 0, z = 0, lx = 0, lz = -1, speed = 45, halfWid = 3.3, halfLen = 7}
info = R.hitFromWorld(me, tr)
check("rear-end: vc 105, facing +1, it is in front of me", info and near(info.vc, 105, 1e-6)
	and near(info.facingDot, 1, 1e-6) and info.front == true and near(info.nz, 1, 1e-6), info and info.vc)
me = {x = 0, z = -14, lx = 0, lz = 1, vx = 0, vz = 150}                 -- in front of it, driving at it
info = R.hitFromWorld(me, tr)
check("head-on: vc 195, facing -1", info and near(info.vc, 195, 1e-6) and near(info.facingDot, -1, 1e-6)
	and info.front == true, info and info.vc)
me = {x = 6.5, z = 0, lx = 0, lz = -1, vx = -10, vz = -150}             -- level with it on its right, drifting left
info = R.hitFromWorld(me, tr)
check("side: traffic on my left, vc = my sideways speed", info and info.side == -1 and near(info.vc, 10, 1e-6)
	and near(info.nx, 1, 1e-6), info and info.side)
me = {x = 0, z = 30, lx = 0, lz = -1, vx = 0, vz = -150}
check("apart: no hit", R.hitFromWorld(me, tr) == nil)

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''


class StagedHits(unittest.TestCase):
    """The Studio arcade cases replayed offline through stagePlan + hitFromWorld + classifyHit."""

    def test_studio_cases(self):
        code, out = _qa.run_luau(STAGED, {'PattayaRecovery.luau': src(MOD)})
        self.assertEqual(code, 0, out[-3000:])
        fails = [line for line in out.splitlines() if line.startswith('FAIL ')]
        self.assertEqual(fails, [], out[-4000:])
        self.assertIn('FAILS\t0', out, out[-3000:])
        self.assertGreaterEqual(out.count('PASS '), 1500, out[-2000:])


# --- Studio round 5 (2026-10-21): TestKit keys / positions vs PattayaTraffic ---------------------------------------

# synthetic traffic data in the generated module's format (used when build/ is missing; the real data is tested too)
SYNTH_DATA = r'''
local out = {}
for ri = 1, 12 do
	local pts = {}
	local cx, cz, rad = 300 * ri - 1800, 150 * ri + 700, 400 + 37 * ri
	for i = 0, 96 do
		local a = i / 96 * 2 * math.pi
		-- one decimal like the generator, irregular so float32 rounding differs point to point
		table.insert(pts, math.floor((cx + rad * math.cos(a) + 0.37 * math.sin(7 * a)) * 10 + 0.5) / 10)
		table.insert(pts, math.floor((cz + rad * math.sin(a) * 0.8) * 10 + 0.5) / 10)
	end
	local kinds = {}
	for k = 1, 6 + ri % 5 do table.insert(kinds, (k + ri) % 3) end
	table.insert(out, {length = 0, speed = 38 + ri % 4 * 5.5, phase = 13.7 * ri, kinds = kinds, pts = pts})
end
return out
'''

KEYS = r'''
local R = require("./PattayaRecovery")
local data = require("./traffic")
local fails, passes = 0, 0
local function check(name, cond, detail)
	if cond then passes += 1 print("PASS " .. name)
	else fails += 1 print("FAIL " .. name .. (if detail then " :: " .. tostring(detail) else "")) end
end
local T = 1792540800.25 -- workspace:GetServerTimeNow() on 2026-10-21 (epoch seconds)

-- 1. the OLD client maths, op for op, with the native float32 vector type (= Roblox Vector3): round 3-5 root cause
local OX, OZ, RY = R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z, R.TRAFFIC_ROAD_Y
local legacy = {}
for _, r in data do
	local pts, cum = {}, {0}
	for i = 1, #r.pts, 2 do
		table.insert(pts, vector.create(r.pts[i] + OX, RY, r.pts[i + 1] + OZ))
	end
	for i = 2, #pts do
		cum[i] = cum[i - 1] + vector.magnitude(pts[i] - pts[i - 1])
	end
	table.insert(legacy, {pts = pts, cum = cum, length = cum[#cum], speed = r.speed, phase = r.phase, kinds = r.kinds})
end
local function legacyAt(r, s)
	s %= r.length
	local cum = r.cum
	local lo, hi = 1, #cum
	while hi - lo > 1 do
		local mid = (lo + hi) // 2
		if cum[mid] <= s then lo = mid else hi = mid end
	end
	local seg = cum[hi] - cum[lo]
	local a, b = r.pts[lo], r.pts[hi]
	return a + (b - a) * (if seg > 0 then (s - cum[lo]) / seg else 0)
end
local routes = R.buildTrafficRoutes(data, OX, OZ)
local diffs = {}
for ri, r in legacy do
	for k = 1, #r.kinds do
		local p = legacyAt(r, r.phase + (k - 1) * r.length / #r.kinds + T * r.speed)
		local x, z = R.trafficCarAt(routes[ri], k, T)
		table.insert(diffs, math.sqrt((p.x - x) ^ 2 + (p.z - z) ^ 2))
	end
end
table.sort(diffs)
local median = diffs[#diffs // 2 + 1]
print(("INFO old client maths vs shared maths at t = %d: %d cars, median %.0f studs, max %.0f"):format(T, #diffs,
	median, diffs[#diffs]))
check("round 3-5 root cause reproduced: the old Vector3 (float32) loops put the same key far from the shared spot",
	median > 50, median)

-- 2. keys: route order = data order, key = route * 1000 + car, unique
local seenKeys, unique, count = {}, true, 0
for ri, r in routes do
	for k = 1, #r.kinds do
		local key = R.trafficKey(ri, k)
		if seenKeys[key] then unique = false end
		seenKeys[key] = true
		count += 1
	end
end
check("keys are unique (" .. count .. " cars)", unique)
check("route i of the build is route i of the data", #routes == #data and routes[1].speed == data[1].speed
	and routes[#routes].phase == data[#data].phase)

-- 3. PattayaTraffic's draw loop (R.forEachTrafficCar with its RADIUS) and TestKit's list (R.trafficNear ->
-- R.tkTrafficEntry) at many spots and times: every car TestKit lists is drawn with the same key, place and heading
local mismatch, compared = 0, 0
local spots = {}
for _, r in routes do
	local i = 1 + (#r.xs // 3)
	table.insert(spots, {r.xs[i], r.zs[i]})
end
for si, spot in spots do
	local t = T + si * 7.31
	local drawn = {}
	R.forEachTrafficCar(routes, t, spot[1], spot[2], 650, function(key, x, z, d2, r, k, ri, s)
		local lx, lz = R.trafficHeading(r, s)
		drawn[key] = {x = x, z = z, lx = lx, lz = lz}
	end)
	for _, e in R.trafficNear(routes, t, spot[1], spot[2], 300) do
		local te = R.tkTrafficEntry(e)
		compared += 1
		local d = drawn[te.key]
		if not (d and d.x == te.x and d.z == te.z and d.lx == te.lx and d.lz == te.lz and te.route ~= nil
			and te.s ~= nil and te.t == t and te.key == R.trafficKey(te.ri, te.k)) then
			mismatch += 1
		end
	end
end
check(("PattayaTraffic draw loop == TestKit list: %d cars compared, identical key / x / z / heading"):format(compared),
	compared > 20 and mismatch == 0, mismatch)

-- 4. a second copy of the data module (the Studio execute context gets its own module copies) gives the same numbers
local function deepCopy(v)
	if type(v) ~= "table" then return v end
	local o = {}
	for k, x in v do o[k] = deepCopy(x) end
	return o
end
local routes2 = R.buildTrafficRoutes(deepCopy(data), OX, OZ)
local same = true
for ri, r in routes do
	for k = 1, #r.kinds do
		local x1, z1 = R.trafficCarAt(r, k, T)
		local x2, z2 = R.trafficCarAt(routes2[ri], k, T)
		if x1 ~= x2 or z1 ~= z2 then same = false end
	end
end
check("a separate copy of the traffic module gives identical keys and positions", same)

-- 5. precision of the shared maths itself at the epoch clock: one 60 Hz frame advances a car's arc by speed / 60
local r = routes[1]
local _, _, s0 = R.trafficCarAt(r, 1, T)
local _, _, s1 = R.trafficCarAt(r, 1, T + 1 / 60)
check(("one 60 Hz frame advances the arc by speed / 60 (%.6f vs %.6f)"):format(s1 - s0, r.speed / 60),
	math.abs((s1 - s0) - r.speed / 60) < 1e-4, s1 - s0)

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# TestKit loaded in a mocked Roblox client: TK.trafficNear keeps the key (round 5 crash), TK.selfCheck compares the
# keys with the models PattayaTraffic shows, hitTest clears TK_HitTarget on every path.
TK_MOCK = r'''
local RealR = require("./PattayaRecovery")
local DATA = require("./traffic")
local T = 1792540800.25

local waits = 0
local function signal()
	return {Connect = function() return {Disconnect = function() end} end, Wait = function()
		waits += 1
		if waits > 20000 then error("mock: endless wait") end -- a test must fail, never hang
		return 0
	end}
end
local function attrs(obj)
	obj._attr = obj._attr or {}
	obj.GetAttribute = function(self, k) return self._attr[k] end
	obj.SetAttribute = function(self, k, v) self._attr[k] = v end
	return obj
end
local player = attrs({Name = "Tester", Character = nil})
local RECOVERY_MODULE, TRAFFIC_MODULE = {Name = "PattayaRecovery"}, {Name = "PattayaTraffic"}
local services = {
	Players = {LocalPlayer = player},
	RunService = {IsStudio = function() return true end, Heartbeat = signal(), RenderStepped = signal(),
		PreSimulation = signal(), Stepped = signal()},
	ReplicatedStorage = {FindFirstChild = function(_, n)
		if n == "PattayaRecovery" then return RECOVERY_MODULE elseif n == "PattayaTraffic" then return TRAFFIC_MODULE end
		return nil
	end, WaitForChild = function() return nil end},
}
game = {GetService = function(_, n) return services[n] or {} end}

-- the traffic folder PattayaTraffic would show: models placed by a draw function, tagged (or not) with TrafficKey
local folder = attrs({Name = "PattayaTraffic", _children = {}})
folder.GetChildren = function(self) return self._children end
local function model(key, x, z)
	local m = attrs({Name = "Traffic", PrimaryPart = {Position = Vector3.new(x, 2.6, z), LocalTransparencyModifier = 0}})
	m.IsA = function(_, c) return c == "Model" end
	if key ~= nil then m._attr.TrafficKey = key end
	return m
end
workspace = attrs({CurrentCamera = nil})
workspace.GetServerTimeNow = function() return T end
workspace.FindFirstChild = function(_, n) if n == "PattayaTraffic" then return folder end return nil end

local realRequire = require
local require = function(m)
	if m == RECOVERY_MODULE then return RealR elseif m == TRAFFIC_MODULE then return DATA end
	return realRequire(m)
end
local _G = {} -- the CLI's _G is read-only; TestKit stores itself as _G.TK
local TK = (function()
__TESTKIT__
end)()

local fails, passes = 0, 0
local function check(name, cond, detail)
	if cond then passes += 1 print("PASS " .. name)
	else fails += 1 print("FAIL " .. name .. (if detail then " :: " .. tostring(detail) else "")) end
end

-- a spot on the first route, and the cars PattayaTraffic draws there (shared maths, 70-model pool)
local routes = RealR.buildTrafficRoutes(DATA, RealR.TRAFFIC_ORIGIN_X, RealR.TRAFFIC_ORIGIN_Z)
local r1 = routes[1]
local spot = Vector3.new(r1.xs[1 + #r1.xs // 3], 1, r1.zs[1 + #r1.xs // 3])
local function drawShared(tag)
	folder._children = {}
	RealR.forEachTrafficCar(routes, T, spot.X, spot.Z, 650, function(key, x, z)
		if #folder._children < 70 then table.insert(folder._children, model(if tag then key else nil, x, z)) end
	end)
	folder._attr.Positions = "shared"
	folder._attr.DrawT = T -- the server time PattayaTraffic drew them with
end

-- TK.trafficNear: every entry keeps key / route / s / t (round 5: the key was dropped -> "table index is nil")
local list = TK.trafficNear(300, spot)
local okFields = #list > 0
for _, e in list do
	if e.key == nil or e.route == nil or e.s == nil or e.t == nil or e.ri == nil or e.k == nil or e.pos == nil then
		okFields = false
	end
end
check(("TK.trafficNear entries carry key, route, s, t (%d cars)"):format(#list), okFields)
local ref = RealR.trafficNear(routes, T, spot.X, spot.Z, 300)
local sameKeys = #ref == #list
for i, e in ref do
	if not list[i] or list[i].key ~= e.key or list[i].pos.X ~= e.x or list[i].pos.Z ~= e.z then sameKeys = false end
end
check("TK.trafficNear keys and spots == the shared PattayaRecovery list", sameKeys)

-- TK.selfCheck against models drawn with the shared maths and tagged: every key matches
drawShared(true)
local ok, lines = TK.selfCheck(5, spot)
check("TK.selfCheck passes when PattayaTraffic draws with the shared maths", ok, lines[#lines])
-- ... and fails when the models are where the OLD float32 client maths put them
folder._children = {}
for ri, r in DATA do
	local pts, cum = {}, {0}
	for i = 1, #r.pts, 2 do table.insert(pts, vector.create(r.pts[i] + 20000, 1, r.pts[i + 1])) end
	for i = 2, #pts do cum[i] = cum[i - 1] + vector.magnitude(pts[i] - pts[i - 1]) end
	local L = cum[#cum]
	for k = 1, #r.kinds do
		local s = (r.phase + (k - 1) * L / #r.kinds + T * r.speed) % L
		local lo = 1
		while lo < #cum - 1 and cum[lo + 1] <= s do lo += 1 end
		local a, b = pts[lo], pts[lo + 1]
		local seg = cum[lo + 1] - cum[lo]
		local p = a + (b - a) * (if seg > 0 then (s - cum[lo]) / seg else 0)
		if (p.x - spot.X) ^ 2 + (p.z - spot.Z) ^ 2 < 650 * 650 and #folder._children < 70 then
			table.insert(folder._children, model(RealR.trafficKey(ri, k), p.x, p.z))
		end
	end
end
folder._attr.Positions = "shared" -- even if it claimed "shared", the keys give it away
ok, lines = TK.selfCheck(5, spot)
check("TK.selfCheck FAILS against the old client positions (what rounds 3-5 ran into)", not ok, lines[#lines])
-- untagged models (an old PattayaTraffic): reported
drawShared(false)
ok, lines = TK.selfCheck(5, spot)
check("TK.selfCheck reports models without TrafficKey", not ok and lines[#lines]:find("no TrafficKey", 1, true) ~= nil,
	lines[#lines])
-- a leftover TK_HitTarget is reported
drawShared(true)
player:SetAttribute("TK_HitTarget", 1001)
ok, lines = TK.selfCheck(5, spot)
check("TK.selfCheck fails and reports a TK_HitTarget left set", not ok and lines[#lines]:find("still set", 1, true) ~= nil,
	lines[#lines])
player:SetAttribute("TK_HitTarget", nil)

-- TK.hitTest: the isolation hook is cleared even when the run errors half way
local chassis = {Position = spot, CFrame = CFrame.lookAt(spot, spot + Vector3.new(1, 0, 0)), AssemblyLinearVelocity = Vector3.zero,
	AssemblyAngularVelocity = Vector3.zero}
local carModel = attrs({PrimaryPart = chassis, GetDescendants = function() return {} end})
carModel._attr.RaceCar = true
local seat = {Parent = carModel, IsA = function(_, c) return c == "VehicleSeat" end}
local hum = {SeatPart = seat}
player.Character = {FindFirstChildOfClass = function(_, c) if c == "Humanoid" then return hum end end,
	GetDescendants = function() return {} end}
workspace._attr.CollisionModel = "arcade"
local badTarget = table.clone(list[1])
badTarget.s = nil -- the plan maths errors right after the hook was set
local okRun, err = pcall(TK.hitTest, "rear", 100, {target = badTarget, isolate = true})
check("hitTest error path clears TK_HitTarget", not okRun and player:GetAttribute("TK_HitTarget") == nil, err)
-- a target the hook was set for, and the hook set during the run: TK.stopAll clears it too
player:SetAttribute("TK_HitTarget", 5)
TK.stopAll()
check("TK.stopAll clears TK_HitTarget", player:GetAttribute("TK_HitTarget") == nil)

-- round 6: models drawn a slow frame ago (0.1 s), DrawT says when; TestKit compares them at DrawT
local LAG = 0.1
local function drawAt(t, stamp)
	folder._children = {}
	RealR.forEachTrafficCar(routes, t, spot.X, spot.Z, 650, function(key, x, z)
		if #folder._children < 70 then table.insert(folder._children, model(key, x, z)) end
	end)
	folder._attr.Positions = "shared"
	folder._attr.DrawT = stamp
end
drawAt(T - LAG, T - LAG)
local okLag, linesLag, infoLag = TK.selfCheck(5, spot)
check(("selfCheck passes with the models drawn %.0f ms ago: compared at DrawT"):format(LAG * 1000), okLag,
	linesLag[#linesLag])
check(("the drawn-vs-now lag is reported, never failed (%.1f studs / %.0f ms, DrawT %.0f ms old)"):format(
	infoLag.lagStuds, infoLag.lagMs, infoLag.drawAgeMs or -1), infoLag.lagStuds > 3 and math.abs((infoLag.drawAgeMs or 0)
	- LAG * 1000) < 1, infoLag.lagStuds)
-- round 6's TestKit compared the models with the spot NOW, within 4 studs: that is what failed
local oldFail = 0
local shown = TK.trafficModels()
for _, e in TK.trafficNear(650, spot) do
	local m = shown[e.key]
	if m and (m.PrimaryPart.Position - e.pos).Magnitude > 4 then oldFail += 1 end
end
check(("round 6 reproduced: compared at now, %d models are over 4 studs off"):format(oldFail), oldFail > 0, oldFail)
-- no DrawT (an older PattayaTraffic): the check fails and says why
drawAt(T - LAG, nil)
local okNo, linesNo = TK.selfCheck(5, spot)
check("selfCheck fails without DrawT and says so", not okNo and linesNo[#linesNo]:find("DrawT", 1, true) ~= nil,
	linesNo[#linesNo])
drawShared(true)

-- the TestKit FPS cap: on and visible, removed by TK.cleanup and by TK.stopAll
check("TK.fpsLimit(30) is on and visible", TK.fpsLimit(30) == 30 and TK.fpsLimitOn() == 30
	and player:GetAttribute("TK_FpsLimit") == 30)
TK.cleanup(true)
check("TK.cleanup removes the FPS cap", TK.fpsLimitOn() == nil and player:GetAttribute("TK_FpsLimit") == nil)
TK.fpsLimit(15)
player:SetAttribute("TK_HitTarget", 7)
TK.stopAll()
check("TK.stopAll removes the FPS cap and the hook", TK.fpsLimitOn() == nil and player:GetAttribute("TK_FpsLimit") == nil
	and player:GetAttribute("TK_HitTarget") == nil)

-- Taxi / Delivery pay-out (PattayaJobsServer's formula)
local start = {kind = "taxi", fare = 300, timeLimit = 60}
check("pay-out: fare 300, 1 bump (-12 %), 20 s early, 2 near misses = 264 + 30 + 10",
	(TK.jobPayout(start, {money = 304, tip = 40, bumps = 1, time = 40}, 2)))
check("pay-out: a fare paid without the bump cut is caught",
	not TK.jobPayout(start, {money = 340, tip = 40, bumps = 1, time = 40}, 2))
check("pay-out: 6 bumps cut 60 % at most, late = no tip",
	(TK.jobPayout({kind = "delivery", fare = 500, timeLimit = 50}, {money = 200, tip = 0, bumps = 6, time = 55}, 0)))

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''


class TrafficKeys(unittest.TestCase):
    """Round 5: TestKit, PattayaTraffic and the server must agree on every traffic car's key and position."""

    def _data(self):
        path = None
        if _qa.BUILD:
            cand = os.path.join(_qa.BUILD, 'pattaya_wide', 'roblox', 'traffic.luau')
            if os.path.exists(cand):
                path = cand
        return [('synthetic', SYNTH_DATA)] + ([('pattaya_wide', _qa.read(path))] if path else [])

    def _run(self, main, data):
        prelude = _qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau'))
        code, out = _qa.run_luau(prelude + '\n' + main, {'PattayaRecovery.luau': src(MOD), 'traffic.luau': data})
        self.assertEqual(code, 0, out[-3000:])
        fails = [line for line in out.splitlines() if line.startswith('FAIL ')]
        self.assertEqual(fails, [], out[-3000:])
        self.assertIn('FAILS\t0', out, out[-3000:])
        return out

    def test_shared_keys_and_positions(self):
        for name, data in self._data():
            with self.subTest(data=name):
                out = self._run(KEYS, data)
                self.assertGreaterEqual(out.count('PASS '), 6, out[-1500:])

    def test_testkit_traffic_near_and_self_check(self):
        tk = src(os.path.join('ReplicatedStorage', 'PattayaTestKit.luau'))
        main = TK_MOCK.replace('__TESTKIT__', tk)
        for name, data in self._data():
            with self.subTest(data=name):
                out = self._run(main, data)
                self.assertGreaterEqual(out.count('PASS '), 18, out[-1500:])

    def test_one_implementation(self):
        """PattayaTraffic draws through the shared functions (no own Vector3 loop maths when the module is there),
        tags its models with TrafficKey; TestKit and the server build the loops with the shared origin."""
        traffic = _qa.strip_comments(src(TRAFFIC))
        self.assertIn('Recovery.buildTrafficRoutes(routesData, Recovery.TRAFFIC_ORIGIN_X, Recovery.TRAFFIC_ORIGIN_Z)',
                      traffic)
        self.assertIn('Recovery.forEachTrafficCar(routes, t, focus.X, focus.Z, RADIUS, placeCar)', traffic)
        self.assertIn('Recovery.trafficHeading(r, s)', traffic)
        self.assertIn('m:SetAttribute("TrafficKey", key)', traffic)
        self.assertIn('if SHARED then', traffic)
        tk = _qa.strip_comments(src(os.path.join('ReplicatedStorage', 'PattayaTestKit.luau')))
        self.assertIn('Rec.buildTrafficRoutes(require(data :: ModuleScript), Rec.TRAFFIC_ORIGIN_X, Rec.TRAFFIC_ORIGIN_Z)',
                      tk)
        self.assertIn('Rec.tkTrafficEntry(e)', tk)
        server = _qa.strip_comments(src(SERVER))
        self.assertIn('Recovery.TRAFFIC_ORIGIN_X, Recovery.TRAFFIC_ORIGIN_Z', server)
        self.assertIn('Recovery.buildTrafficRoutes(data, TRAFFIC_ORIGIN_X, TRAFFIC_ORIGIN_Z)', server)



# --- Studio round 6 + owner review (team18/arcade-fix-5) ----------------------------------------------------------

CHECK = r'''
local fails, passes = 0, 0
local function check(name, cond, detail)
	if cond then passes += 1 print("PASS " .. name)
	else fails += 1 print("FAIL " .. name .. (if detail then " :: " .. tostring(detail) else "")) end
end
local function near(a, b, eps) return type(a) == "number" and math.abs(a - b) <= (eps or 1e-6) end
'''

# the generated lanes double back at corners ("swallowtails"); PattayaRecovery cleans them, the loop seam included
LANES = r'''
local R = require("./PattayaRecovery")
local data = require("./traffic")
local REAL = __REAL__
__CHECK__
local function reversals(xs, zs)
	local n = 0
	for i = 2, #xs - 1 do
		if R.turnDeg(xs[i - 1], zs[i - 1], xs[i], zs[i], xs[i + 1], zs[i + 1]) > R.LANE_CLEAN.turnDeg then n += 1 end
	end
	return n
end

-- 1. forward 100, 4 studs back, forward again: cut
local cx, cz, n = R.cleanLanePolyline({0, 100, 96, 196}, {0, 0, 0.5, 1})
check("a 4-stud swallowtail is cut", n == 1 and #cx == 3 and reversals(cx, cz) == 0, n)
-- 2. a real U-turn (the lane after it heads back) and 3. an ordinary corner are kept
local _, _, nU = R.cleanLanePolyline({0, 100, 98, 0}, {0, 0, 6, 6})
check("a U-turn is kept", nU == 0, nU)
local _, _, nC = R.cleanLanePolyline({0, 100, 100}, {0, 0, 100})
check("a 90 degree corner is kept", nC == 0, nC)
-- 4. a closed loop whose swallowtail straddles the seam (generated loops start on a corner)
local LX = {0, 100, 100, 0, 0, 0}
local LZ = {0, 0, 100, 100, -4, 0}
local _, _, nOpen = R.cleanLanePolyline(LX, LZ)
local qx, qz, nLoop = R.cleanLaneLoop(LX, LZ)
check("the open-polyline cleanup cannot reach a swallowtail on the seam", nOpen == 0, nOpen)
check("the loop cleanup cuts it", nLoop == 1, nLoop)
check("the cleaned loop starts where it started and closes exactly",
	qx[1] == 0 and qz[1] == 0 and qx[#qx] == qx[1] and qz[#qz] == qz[1], ("%s, %s"):format(qx[#qx], qz[#qz]))
local rev = 0
for i = 1, #qx - 1 do
	local a = if i == 1 then #qx - 1 else i - 1
	if R.turnDeg(qx[a], qz[a], qx[i], qz[i], qx[i + 1], qz[i + 1]) > 100 then rev += 1 end
end
check("no reversal anywhere on the cleaned loop, seam included", rev == 0, rev)

-- 5. buildTrafficRoutes: cleaned loops, arc 0 kept, a car crossing the seam never turns round
local loopData = {{pts = {0, 0, 100, 0, 100, 100, 0, 100, 0, -4, 0, 0}, speed = 40, phase = 0, kinds = {0}}}
local rawL = R.buildTrafficRoutes(loopData, 0, 0, true)[1]
local cleanL = R.buildTrafficRoutes(loopData, 0, 0)[1]
check(("raw loop 408 long, cleaned 400 (%.1f, %.1f)"):format(rawL.length, cleanL.length),
	near(rawL.length, 408) and near(cleanL.length, 400))
local x50, z50 = R.routePoint(cleanL, 50)
check("arc 50 is still (50, 0)", near(x50, 50) and near(z50, 0))
local function seamFlip(r)
	local s = r.length - 30
	local px, pz = R.trafficHeading(r, s)
	local flip = false
	while s < r.length + 30 do
		s += 1
		local hx, hz = R.trafficHeading(r, s)
		if hx * px + hz * pz < -0.5 then flip = true end
		px, pz = hx, hz
	end
	return flip
end
check("a car crossing the cleaned seam never faces backwards", not seamFlip(cleanL))
check("on the raw loop it did (the swallowtail)", seamFlip(rawL))

-- 6. R.routeStraight
check("a straight stretch is straight", (R.routeStraight(cleanL, 10, 90, 1)))
local okc, worstc = R.routeStraight(cleanL, 80, 125, 15)
check(("a corner inside the span is not (worst %.0f degrees)"):format(worstc), not okc and worstc > 30)

if REAL then
	local raw = R.buildTrafficRoutes(data, R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z, true)
	local clean = R.buildTrafficRoutes(data, R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z)
	local function flips(routes)
		local back = 0
		for _, r in routes do
			local s = 0
			while s < r.length do
				local ax, az = R.routePoint(r, s - 6)
				local bx, bz = R.routePoint(r, s)
				local ex, ez = R.routePoint(r, s + 6)
				local ux, uz, vx, vz = bx - ax, bz - az, ex - bx, ez - bz
				local lu, lv = math.sqrt(ux * ux + uz * uz), math.sqrt(vx * vx + vz * vz)
				if lu > 1e-6 and lv > 1e-6 and (ux * vx + uz * vz) / (lu * lv) < -0.5 then back += 1 end
				s += 2
			end
		end
		return back
	end
	local removed = 0
	for _, r in data do
		local xs, zs = {}, {}
		for i = 1, #r.pts, 2 do
			table.insert(xs, r.pts[i] + R.TRAFFIC_ORIGIN_X)
			table.insert(zs, r.pts[i + 1] + R.TRAFFIC_ORIGIN_Z)
		end
		local _, _, n2 = R.cleanLaneLoop(xs, zs)
		removed += n2
	end
	local fr, fc = flips(raw), flips(clean)
	print(("INFO pattaya_wide lanes: %d swallowtails cut; heading reversals (2-stud samples) raw %d, cleaned %d"):format(
		removed, fr, fc))
	check("round 6 cause: the generated lanes double back hundreds of times", fr > 400 and removed > 250, fr)
	check("cleaned lanes: under 20 reversal samples left (junction shapes; TestKit never stages there)", fc < 20, fc)
	local closed, lr, lc, sameStart, seamOk = true, 0, 0, true, true
	for i, r in clean do
		local m = #r.xs
		if r.xs[1] ~= r.xs[m] or r.zs[1] ~= r.zs[m] then closed = false end
		-- (6 loops start inside a seam swallowtail: they start at the crossing point that replaced it, 6-9 studs on)
		if math.abs(r.xs[1] - raw[i].xs[1]) > 12 or math.abs(r.zs[1] - raw[i].zs[1]) > 12 then sameStart = false end
		if seamFlip(r) then seamOk = false end
		lr += raw[i].length
		lc += r.length
	end
	check("every cleaned loop closes exactly", closed)
	check("every loop still starts at its first point (or the crossing point that replaced it)", sameStart)
	check("no car turns round crossing any loop seam", seamOk)
	check(("total lane length changes by under 3 %% (%.0f -> %.0f)"):format(lr, lc), math.abs(lc - lr) / lr < 0.03)
end

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# every row of the owner's table staged on the real routes the way TK.hitTest stages it (target filter included) and
# tested every frame the way PattayaTraffic tests it, at 15 / 30 / 60 fps; plus round 6's route 26 rear 70 rows
SCAN = r'''
local R = require("./PattayaRecovery")
R._attr = function() return nil end
local cfg = R.config()
local data = require("./traffic")
__CHECK__
local raw = R.buildTrafficRoutes(data, R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z, true)
local clean = R.buildTrafficRoutes(data, R.TRAFFIC_ORIGIN_X, R.TRAFFIC_ORIGIN_Z)
local T = 1792540800.25
local CASES = {
	{"rear", 70}, {"rear", 100}, {"rear", 150}, {"rear", 200}, {"rear", 150, {offset = 2}},
	{"head", 100}, {"head", 150}, {"head", 200},
	{"side", 150, {angle = 5}}, {"side", 150, {angle = 20}}, {"side", 70, {angle = 25}}, {"side", 100, {angle = 10}},
}
local function staged(route, k, t0, mode, speed, o)
	local _, _, s0 = R.trafficCarAt(route, k, t0)
	local SH = R.TRAFFIC_SHAPES[route.kinds[k]] or R.TRAFFIC_SHAPES[0]
	return R.stagePlan({route = route, s0 = s0, t0 = t0, vT = route.speed, halfWid = SH.wid / 2, halfLen = SH.len / 2,
		speed = speed, mode = mode, lead = o.lead, offset = o.offset, angle = o.angle})
end
-- TestKit's target filter (pickTarget): a straight approach, and for a side hit a steady heading at the touch
local function stageable(route, mode, span, touch)
	return R.routeStraight(route, span[1], span[2], R.STAGE_BEND_DEG)
		and (mode ~= "side" or R.routeStraight(route, touch[1], touch[2], R.SIDE_STEADY_DEG, 2))
end
local function simulate(route, k, t0, mode, speed, o, fps)
	local plan, meet = staged(route, k, t0, mode, speed, o)
	local SH = R.TRAFFIC_SHAPES[route.kinds[k]] or R.TRAFFIC_SHAPES[0]
	local dt = 1 / fps
	local px, pz = nil, nil
	local t = t0
	while t < meet + 2 do
		t += dt
		local x, z, dx, dz, gap = plan(t)
		local m = math.sqrt(dx * dx + dz * dz)
		dx, dz = dx / m, dz / m
		local tx, tz, s = R.trafficCarAt(route, k, t)
		local lx, lz = R.trafficHeading(route, s)
		local info, rx, rz = R.hitFromWorld({x = x, z = z, lx = dx, lz = dz, vx = dx * speed, vz = dz * speed},
			{x = tx, z = tz, lx = lx, lz = lz, speed = route.speed, halfWid = SH.wid / 2, halfLen = SH.len / 2}, px, pz)
		px, pz = rx, rz
		if info then
			return R.classifyHit(info, cfg), t - meet, info
		end
		if gap < -4 then return nil, "overlap" end
	end
	return nil, "timeout"
end
local function scan(routes, filter, fps)
	local bad, total, per = 0, 0, {}
	for _, c in CASES do
		local mode, speed, o = c[1], c[2], c[3] or {}
		local nb = 0
		for ri, r in routes do
			for k = 1, #r.kinds, 3 do
				local t0 = T + ri * 3.7 + k * 1.3
				local _, _, span, touch = staged(r, k, t0, mode, speed, o)
				if filter and not stageable(r, mode, span, touch) then continue end
				total += 1
				local res, dtm = simulate(r, k, t0, mode, speed, o, fps)
				local want = R.expectedStaged(mode, speed, o.angle, r.speed, cfg)
				if not (res and type(dtm) == "number" and math.abs(dtm) < 0.35 + 1.5 / fps and res.tier == want.tier) then
					nb += 1
					bad += 1
				end
			end
		end
		table.insert(per, ("%s %d%s: %d"):format(mode, speed,
			if o.angle then " a" .. o.angle elseif o.offset then " off" .. o.offset else "", nb))
	end
	return bad, total, table.concat(per, ", ")
end
for _, fps in {15, 30, 60} do
	local bad, total, per = scan(clean, true, fps)
	print(("INFO cleaned lanes + TestKit's target filter @%d fps: %d of %d staged hits wrong (%s)"):format(fps, bad,
		total, per))
	check(("every staged row on the real routes meets, on time, with the table's tier @%d fps (%d hits)"):format(fps,
		total), bad == 0 and total > 2000, per)
end
local badRaw, totalRaw, perRaw = scan(raw, false, 15)
print(("INFO raw lanes, no filter @15 fps: %d of %d wrong (%s)"):format(badRaw, totalRaw, perRaw))
check("round 6 reproduced: raw lanes without the filter get staged hits wrong", badRaw > totalRaw * 0.01, badRaw)

-- route 26 rear 70 (Studio round 6: r1 head-on vc 110 on key 26001, r2 a hit 0.38 s early on key 26012)
local function r26(routes, filter)
	local r = routes[26]
	local headon, early, other, total = 0, 0, 0, 0
	for k = 1, #r.kinds do
		for i = 0, 59 do
			local t0 = T + i * 2.9 + k * 0.7
			local _, _, span, touch = staged(r, k, t0, "rear", 70, {})
			if filter and not stageable(r, "rear", span, touch) then continue end
			total += 1
			local res, dtm = simulate(r, k, t0, "rear", 70, {}, 15)
			local want = R.expectedStaged("rear", 70, nil, r.speed, cfg)
			if res and res.tier == "headon" then
				headon += 1
			elseif type(dtm) == "number" and dtm < -(0.35 + 1.5 / 15) then
				early += 1
			elseif not (res and res.tier == want.tier and type(dtm) == "number" and math.abs(dtm) < 0.35 + 1.5 / 15) then
				other += 1
			end
		end
	end
	return headon, early, other, total
end
if #raw >= 26 then
	local h1, e1, o1, n1 = r26(raw, false)
	local h2, e2, o2, n2 = r26(clean, false)
	local h3, e3, o3, n3 = r26(clean, true)
	print(("INFO route 26 rear 70 @15 fps: raw %d runs (%d head-on, %d early, %d other); cleaned %d (%d, %d, %d); cleaned + filter %d (%d, %d, %d)")
		:format(n1, h1, e1, o1, n2, h2, e2, o2, n3, h3, e3, o3))
	check("round 6 route 26 reproduced on the raw lanes: rear-ends seen as head-on and hits far too early",
		h1 > 0 and e1 > 0, ("%d head-on, %d early"):format(h1, e1))
	check("cleaned lanes: no head-on and no early hit on route 26", h2 == 0 and e2 == 0, ("%d, %d"):format(h2, e2))
	check("cleaned lanes + TestKit's filter: every route 26 rear 70 run right", n3 > 50 and h3 + e3 + o3 == 0,
		("%d runs, %d wrong"):format(n3, h3 + e3 + o3))
end

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# rear 70 review: low closing speeds (2-25 studs/s), a long overlap build-up, the loop seam; and side 70's repeat hit
LOWVC = r'''
local R = require("./PattayaRecovery")
R._attr = function() return nil end
local cfg = R.config()
__CHECK__
local SH = R.TRAFFIC_SHAPES[0]
local hw, hl = SH.wid / 2, SH.len / 2
local function loop(pts) return R.buildTrafficRoutes({{pts = pts, speed = 45, phase = 0, kinds = {0}}}, 0, 0)[1] end
local straight = loop({0, 0, 4000, 0, 4000, 800, 0, 800, 0, 0})
-- starts in the middle of its bottom straight, so the touch can be planned right on the seam
local seamed = loop({2000, 0, 4000, 0, 4000, 800, 0, 800, 0, 0, 2000, 0})

-- a rear-end planned like TK.hitTest and tested every frame like PattayaTraffic, then what CarController does (speed
-- cut, push-out) and my car coasting (0.25 / s) while the traffic car drives on; hold = PattayaTraffic's ghost since
-- arcade-fix-5 (R.hitGhostStart / R.hitGhostStep), else round 6's plain 1.5 s ghost
local function rear(route, s0, vT, speed, fps, hold, watch)
	local plan, meet = R.stagePlan({route = route, s0 = s0, t0 = 0, vT = vT, halfWid = hw, halfLen = hl, speed = speed,
		mode = "rear"})
	local dt = 1 / fps
	local st = {ghostUntil = -math.huge}
	local hits = {}
	local px, pz = nil, nil
	local x, z, dx, dz = plan(0)
	local vx, vz = dx * speed, dz * speed
	local driven = true
	local t = 0
	while t < meet + watch do
		t += dt
		if driven then
			x, z, dx, dz = plan(t)
			vx, vz = dx * speed, dz * speed
		else
			x, z = x + vx * dt, z + vz * dt
			local k = math.exp(-0.25 * dt)
			vx, vz = vx * k, vz * k
		end
		local sT = s0 + vT * t
		local tx, tz = R.routePoint(route, sT)
		local lx, lz = R.trafficHeading(route, sT)
		local sp = math.sqrt(vx * vx + vz * vz)
		local me = {x = x, z = z, lx = vx / sp, lz = vz / sp, vx = vx, vz = vz}
		local tr = {x = tx, z = tz, lx = lx, lz = lz, speed = vT, halfWid = hw, halfLen = hl}
		if hold then
			R.hitGhostStep(st, t, R.carsOverlap(me, tr, 1))
		end
		local info, rx, rz = R.hitFromWorld(me, tr, px, pz)
		px, pz = rx, rz
		if info and t >= st.ghostUntil then
			local res = R.classifyHit(info, cfg)
			table.insert(hits, {t = t, info = info, res = res, speed = sp, lx = lx, lz = lz})
			if hold then R.hitGhostStart(st, t, cfg) else st.ghostUntil = t + cfg.Arcade_HitGhost end
			vx, vz = R.impactVelocity(vx, vz, info.nx, info.nz, res)
			local push = math.min((info.depth or 0) + 0.5, cfg.Arcade_MaxPush)
			x, z = x + info.nx * push, z + info.nz * push
			driven = false
		end
	end
	return hits, meet
end
for _, fps in {15, 30, 60} do
	for _, vc in {2, 5, 10, 20, 25} do
		for _, case in {{"straight", straight, 600}, {"seam", seamed, nil}} do
			local route, s0 = case[2], case[3]
			if not s0 then
				s0 = route.length - 45 * (120 - (hl + R.CAR_HALF_LEN)) / vc -- the target is on the seam at the touch
			end
			local hits, meet = rear(route, s0, 45, 45 + vc, fps, true, 4)
			local name = ("rear vc %d @%d fps (%s)"):format(vc, fps, case[1])
			local h = hits[1]
			check(name .. ": exactly one hit, none while my car pushes on through it", #hits == 1, #hits)
			if h then
				check(name .. ": in the first frame after the planned touch", h.t >= meet - 1e-6 and h.t - meet <= 1 / fps + 1e-6,
					h.t - meet)
				check(name .. ": on its rear face", math.abs(h.info.nx * h.lx + h.info.nz * h.lz) > 0.99,
					("n (%.2f, %.2f)"):format(h.info.nx, h.info.nz))
				check(name .. ": closing speed = the speed difference", near(h.info.vc, vc, 0.01), h.info.vc)
				local want = R.expectedStaged("rear", 45 + vc, nil, 45, cfg)
				check(name .. ": tier " .. want.tier, h.res.tier == want.tier, h.res.tier)
			end
		end
	end
end

-- side 70 a25 (Studio round 6: "speed at the hit 33/37/40", r2 scrape): after the light hit my car ran alongside
-- the traffic car, still overlapping it; once its 1.5 s ghost was over it was hit again at 33-40 studs/s, and that
-- second hit's numbers were the ones read. Here: parallel, 1 stud into its side, coasting from 56 (70 - 20 %).
local function alongside(hold, fps)
	local dt = 1 / fps
	local st = {ghostUntil = -math.huge}
	local hits = {{t = 0, speed = 70}}
	if hold then R.hitGhostStart(st, 0, cfg) else st.ghostUntil = cfg.Arcade_HitGhost end
	local px, pz = nil, nil
	local t = 0
	local zMe = hw + R.CAR_HALF_WID - 1
	local function at(tt)
		local v = 56 * math.exp(-0.25 * tt)
		local x = 56 * (1 - math.exp(-0.25 * tt)) / 0.25
		return {x = x, z = zMe, lx = 1, lz = 0, vx = v, vz = 0}, {x = 45 * tt, z = 0, lx = 1, lz = 0, speed = 45,
			halfWid = hw, halfLen = hl}, v
	end
	while t < 3.5 do
		t += dt
		local me, tr, v = at(t)
		if hold then R.hitGhostStep(st, t, R.carsOverlap(me, tr, 1)) end
		local info, rx, rz = R.hitFromWorld(me, tr, px, pz)
		px, pz = rx, rz
		if info and t >= st.ghostUntil then
			table.insert(hits, {t = t, speed = v})
			if hold then R.hitGhostStart(st, t, cfg) else st.ghostUntil = t + cfg.Arcade_HitGhost end
		end
	end
	return hits, st
end
for _, fps in {15, 30, 60} do
	local old = alongside(false, fps)
	check(("round 6 side 70 reproduced @%d fps: with the plain 1.5 s ghost a second hit comes at %.2f s, my car at %.0f studs/s (Studio 33-40)")
		:format(fps, old[2] and old[2].t or -1, old[2] and old[2].speed or -1),
		#old == 2 and math.abs(old[2].t - 1.5) <= 1 / fps + 1e-6 and old[2].speed > 33 and old[2].speed < 40, #old)
	local new, st = alongside(true, fps)
	check(("@%d fps: with the hold, no second hit while the cars still overlap"):format(fps), #new == 1, #new)
	-- apart for a frame, then a new touch: a real new hit counts again
	R.hitGhostStep(st, 10, false)
	check(("@%d fps: the hold ends once the cars are apart"):format(fps), st.hitHold == nil and 10 >= st.ghostUntil)
end

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# the arcade hit response's anti-roll maths, and near misses with arcade on
ANTIROLL_NEAR = r'''
local R = require("./PattayaRecovery")
R._attr = function() return nil end
local cfg = R.config()
__CHECK__
-- anti-roll: only the yaw about the held up axis is kept; the look is turned into the plane normal to it
local ax, ay, az = R.yawOnlyRate(1, 2, 3, 0, 1, 0)
check("yawOnlyRate keeps only the yaw (up = Y)", ax == 0 and ay == 2 and az == 0)
local u = {math.sin(math.rad(10)), math.cos(math.rad(10)), 0}
ax, ay, az = R.yawOnlyRate(0.5, 2, -1, u[1], u[2], u[3])
local d = 0.5 * u[1] + 2 * u[2]
check("yawOnlyRate on a tilted up axis: parallel to it, the yaw part kept",
	near(ax, u[1] * d) and near(ay, u[2] * d) and near(az, 0))
local lx, ly, lz = R.yawOnlyLook(1, 0.3, 0, 0, 1, 0)
check("yawOnlyLook flattens the look", near(lx, 1) and near(ly, 0) and near(lz, 0))
check("yawOnlyLook along the up axis: none", R.yawOnlyLook(0, 1, 0, 0, 1, 0) == nil)
check("tiltFrom: 0 and 10 degrees", near(R.tiltFrom(0, 1, 0, 0, 1, 0), 0, 1e-4) and near(R.tiltFrom(u[1], u[2], u[3], 0, 1, 0), 10, 1e-4))
check("the anti-roll is part of the arcade defaults (the hit window + 0.25 s; heavy / head-on: + their slide)",
	cfg.Arcade_AntiRoll == true and cfg.Arcade_AntiRollExtra > 0 and cfg.Arcade_AntiRollExtra <= 0.5
	and cfg.Arcade_AntiRollSnapDeg > 0 and cfg.Arcade_AntiRollHeavyExtra > cfg.Arcade_AntiRollExtra
	and cfg.Arcade_AntiRollHeavyExtra <= 2)
-- round 8 (60 fps rear @100): how long the hold lasts after the touch, per tier
check("antiRollHold: light / scrape keep the window + Arcade_AntiRollExtra",
	near(R.antiRollHold("light", 0.25, cfg), 0.5) and near(R.antiRollHold("scrape", 0.15, cfg), 0.4))
check("antiRollHold: heavy / head-on add Arcade_AntiRollHeavyExtra (rear @100: 0.66 + 1.5)",
	near(R.antiRollHold("heavy", 0.66, cfg), 2.16) and near(R.antiRollHold("headon", 1.0, cfg), 2.5))
local cfgOld = table.clone(cfg)
cfgOld.Arcade_AntiRollHeavyExtra = 0
check("antiRollHold: Arcade_AntiRollHeavyExtra = 0 is the round 7 hold (window + 0.25 s) for every tier",
	near(R.antiRollHold("heavy", 0.66, cfgOld), 0.91) and near(R.antiRollHold("headon", 1.0, cfgOld), 1.25)
	and near(R.antiRollHold("light", 0.25, cfgOld), 0.5))
-- the scripted spin (a yaw RATE set once per Heartbeat, integrated over the next frame) reaches the table's kick at
-- every frame rate within one frame of rate: rear @100 (vc 55: 53.8 degrees) reaches 51.6-56.1 at 60 Hz, so a
-- 34-36 degree heading after 2 s (Studio round 8) is not the script
for _, case in {{53.8, 0.67}, {97.9, 1.02}, {120, 1.2}, {10, 1.0}} do
	local T, w0 = R.spinProfile(case[1], case[2])
	for _, hz in {15, 30, 60} do
		local lo, hi = 0, 0
		for k = 0, math.ceil(T * hz) do
			local t = k / hz
			if t < T then
				hi += w0 * (1 - t / T) / hz
				if k > 0 then lo += w0 * (1 - t / T) / hz end
			end
		end
		local slack = math.deg(w0 / hz) + 1e-6
		check(("scripted spin %.1f deg at %d Hz: %.1f..%.1f (within one frame of rate, %.1f deg)"):format(case[1], hz,
			math.deg(lo), math.deg(hi), slack), math.abs(math.deg(lo) - case[1]) <= slack
			and math.abs(math.deg(hi) - case[1]) <= slack)
	end
end

-- near misses: my car from 30 studs behind a traffic car to 30 ahead, `g` studs beside it, `u` studs/s faster
local hw, hl = 3.3, 7
local function pass(g, u2, v, fps, touch, t0, st, lastAt)
	st = st or {}
	local fires, last = 0, lastAt or -math.huge
	local relX = hw + R.CAR_HALF_WID + g
	local relZ = hl + 30
	local t = t0 or 0
	while relZ > -(hl + 30) do
		t += 1 / fps
		relZ -= u2 / fps
		local x = relX
		if touch and math.abs(relZ) < 3 then x = hw + R.CAR_HALF_WID - 0.5 end
		if R.nearMissStep(st, x, relZ, hw, hl, false, v, t, last) then
			fires += 1
			last = t
		end
	end
	return fires, t, last
end
for _, fps in {15, 30, 60} do
	check(("near miss @%d fps: a pass 5 studs beside it at 110 pays once"):format(fps), pass(5, 65, 110, fps) == 1)
	check(("near miss @%d fps: 9 studs beside it (outside the 7-stud band) pays nothing"):format(fps), pass(9, 65, 110, fps) == 0)
	check(("near miss @%d fps: at 60 studs/s (below 70) nothing"):format(fps), pass(5, 65, 60, fps) == 0)
	check(("near miss @%d fps: a pass that touches it is a hit, not a near miss"):format(fps), pass(5, 65, 110, fps, true) == 0)
end
-- two passes 0.3 s apart: the second is not paid (0.6 s between awards)
local f1, tEnd, last = pass(5, 400, 110, 60)
local f2 = pass(5, 400, 110, 60, false, tEnd - 0.1, {}, last)
check("a second near miss within 0.6 s is not paid", f1 == 1 and f2 == 0, f2)
check("PattayaTraffic's inline fallback uses the same numbers", R.NEAR_GAP == 7 and R.NEAR_SPEED == 70
	and R.CAR_HALF_WID == 3.5 and R.NEAR_INTERVAL == 0.6)

-- TK.nearMissTest's staged pass (stagePlan "pass") with PattayaTraffic's per-frame rule: once at 5 studs, never a hit
local route = R.buildTrafficRoutes({{pts = {0, 0, 4000, 0, 4000, 800, 0, 800, 0, 0}, speed = 45, phase = 0,
	kinds = {0}}}, 0, 0)[1]
local SH = R.TRAFFIC_SHAPES[0]
local function stagedPass(gap, speed, fps)
	local plan = R.stagePlan({route = route, s0 = 1000, t0 = 0, vT = 45, halfWid = SH.wid / 2, halfLen = SH.len / 2,
		speed = speed, mode = "pass", gap = gap})
	local st, fires, hits, last = {}, 0, 0, -math.huge
	local px, pz = nil, nil
	local t = 0
	while t < 8 do
		t += 1 / fps
		local x, z, dx, dz, left = plan(t)
		local sT = 1000 + 45 * t
		local tx, tz = R.routePoint(route, sT)
		local tlx, tlz = R.trafficHeading(route, sT)
		local info, rx, rz = R.hitFromWorld({x = x, z = z, lx = dx, lz = dz, vx = dx * speed, vz = dz * speed},
			{x = tx, z = tz, lx = tlx, lz = tlz, speed = 45, halfWid = SH.wid / 2, halfLen = SH.len / 2}, px, pz)
		px, pz = rx, rz
		if info then hits += 1 end
		if R.nearMissStep(st, rx, rz, SH.wid / 2, SH.len / 2, false, speed, t, last) then
			fires += 1
			last = t
		end
		if left <= 0 then break end
	end
	return fires, hits
end
for _, fps in {15, 30, 60} do
	local f, h = stagedPass(5, 110, fps)
	check(("staged pass @%d fps, 5 studs, 110: one near miss, no hit"):format(fps), f == 1 and h == 0, ("%d, %d"):format(f, h))
	f, h = stagedPass(9, 110, fps)
	check(("staged pass @%d fps, 9 studs: none"):format(fps), f == 0 and h == 0, f)
	f, h = stagedPass(5, 60, fps)
	check(("staged pass @%d fps, at 60: none"):format(fps), f == 0 and h == 0, f)
end

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# PattayaRecoveryServer's TrafficHit check with two players in one mocked server: real hits accepted, fakes and floods
# refused, and one player's reports never touch the other player
SERVER2P = r'''
local RealR = require("./PattayaRecovery")
RealR._attr = function(name) return workspace and workspace._attr[name] end -- the module sees the mocked workspace
local DATA = require("./traffic")
__CHECK__
local T = 1792540800.25
local now = T
local function signal()
	local s = {list = {}}
	function s:Connect(f)
		table.insert(self.list, f)
		return {Disconnect = function() end}
	end
	function s:Fire(...)
		for _, f in self.list do f(...) end
	end
	return s
end
local function attrs(o)
	o._attr = o._attr or {}
	o.GetAttribute = function(self, k) return self._attr[k] end
	o.SetAttribute = function(self, k, v) self._attr[k] = v end
	return o
end
local bindable = {}
local clientFired = {}
local function instance(className)
	local o = attrs({ClassName = className, Name = className, _children = {}})
	o.FindFirstChild = function(self, n) return self._children[n] end
	o.IsA = function(self, c) return self.ClassName == c end
	if className == "RemoteEvent" then
		o.OnServerEvent = signal()
		o.FireClient = function(self, plr, ...) table.insert(clientFired, {self.Name, plr, ...}) end
	elseif className == "BindableEvent" then
		o.Event = signal()
		o.Fire = function(self, ...) table.insert(bindable, table.pack(...)) end
	end
	return setmetatable(o, {__newindex = function(t, k, v)
		if k == "Parent" and v then v._children[t.Name] = t end
		rawset(t, k, v)
	end})
end
Instance = {new = function(c) return instance(c) end}
RaycastParams = {new = function() return {} end}
OverlapParams = {new = function() return {} end}
Enum = {RaycastFilterType = {Exclude = 1}}
local RECOVERY_MODULE = {Name = "PattayaRecovery"}
local TRAFFIC_MODULE = {Name = "PattayaTraffic", IsA = function(_, c) return c == "ModuleScript" end}
local players = {}
local Players = {GetPlayers = function() return players end, PlayerRemoving = signal()}
local RunService = {Heartbeat = signal(), IsStudio = function() return true end}
local RS = instance("ReplicatedStorage")
RS._children.PattayaTraffic = TRAFFIC_MODULE
RS.WaitForChild = function(self, n) if n == "PattayaRecovery" then return RECOVERY_MODULE end return self._children[n] end
local SS = instance("ServerStorage")
SS.WaitForChild = function() return nil end -- no road graph: the rescue uses the trail only
local services = {Players = Players, RunService = RunService, ReplicatedStorage = RS, ServerStorage = SS}
game = {GetService = function(_, n) return services[n] end}
workspace = attrs({})
workspace.GetServerTimeNow = function() return now end
workspace._attr.CollisionModel = "arcade"
local realRequire = require
local require = function(m)
	if m == RECOVERY_MODULE then return RealR elseif m == TRAFFIC_MODULE then return DATA end
	return realRequire(m)
end

;(function()
__SERVER__
end)()

-- two drivers: A next to a traffic car, B on an empty spot far from any route; C next to traffic but crawling
local routes = RealR.buildTrafficRoutes(DATA, RealR.TRAFFIC_ORIGIN_X, RealR.TRAFFIC_ORIGIN_Z)
local function driver(name)
	local chassis = {Position = Vector3.zero, AssemblyLinearVelocity = Vector3.zero,
		CFrame = CFrame.lookAt(Vector3.zero, Vector3.new(1, 0, 0))}
	local model = attrs({PrimaryPart = chassis})
	model._attr.RaceCar = true
	local seat = {Parent = model, IsA = function(_, c) return c == "VehicleSeat" end}
	local hum = {SeatPart = seat}
	local plr = attrs({Name = name, Character = {FindFirstChildOfClass = function(_, c)
		if c == "Humanoid" then return hum end
	end}})
	plr.chassis = chassis
	table.insert(players, plr)
	return plr
end
local A, B, C = driver("A"), driver("B"), driver("C")
local function place(plr, pos, vel)
	plr.chassis.Position = pos
	plr.chassis.AssemblyLinearVelocity = vel
	plr.chassis.CFrame = CFrame.lookAt(pos, pos + (if vel.Magnitude > 0 then vel.Unit else Vector3.new(1, 0, 0)))
end
-- A follows traffic car 1 of route 1 four studs beside it at 120 studs/s; C waits (stopped) where that car will be at
-- the first report; B drives a straight line far from every route
local PC
do
	local x, z, s = RealR.trafficCarAt(routes[1], 1, T + 1.5)
	local lx, lz = RealR.trafficHeading(routes[1], s)
	PC = Vector3.new(x, 3.8, z) - Vector3.new(-lz, 0, lx) * 4
end
local function frame(dt)
	now += dt
	local x, z, s = RealR.trafficCarAt(routes[1], 1, now)
	local lx, lz = RealR.trafficHeading(routes[1], s)
	local side = Vector3.new(-lz, 0, lx) * 4
	place(A, Vector3.new(x, 3.8, z) + side, Vector3.new(lx, 0, lz) * 120)
	place(C, PC, Vector3.zero)
	place(B, Vector3.new(90000 + (now - T) * 120, 3.8, 90000), Vector3.new(120, 0, 0))
	RunService.Heartbeat:Fire()
end
for _ = 1, 30 do frame(0.05) end
local remotes = RS._children.PattayaRemotes
local TrafficHit = remotes._children.TrafficHit
local function report(plr, tier, vc, speed)
	TrafficHit.OnServerEvent:Fire(plr, tier, vc, speed)
end
local function hits(plr) return plr:GetAttribute("TrafficHits") or 0 end

report(A, "heavy", 80, 120)
check("A's real heavy hit beside a traffic car is accepted", hits(A) == 1 and #bindable == 1 and bindable[1][1] == A
	and bindable[1][2] == "heavy", hits(A))
report(B, "heavy", 80, 120)
check("B's fake report (no traffic car within 45 studs) is refused", hits(B) == 0 and #bindable == 1, hits(B))
check("A's hit did not touch B", B:GetAttribute("TrafficHitAt") == nil and B:GetAttribute("TrafficHitTier") == nil)
report(C, "heavy", 80, 10)
check("C's report from a crawling car (server saw < 40 studs/s) is refused", hits(C) == 0, hits(C))
report(A, "heavy", 80, 120)
check("A's second report within 1 s is refused (one per Arcade_HitReportGap)", hits(A) == 1, hits(A))
for _ = 1, 24 do frame(0.05) end
report(A, "light", 30, 120)
check("a light hit is never reported as a bump", hits(A) == 1, hits(A))
for _ = 1, 6 do frame(0.05) end
report(A, "headon", 1000, 120)
check("an impossible closing speed (1000) is refused", hits(A) == 1, hits(A))
for _ = 1, 6 do frame(0.05) end
report(A, "headon", 0 / 0, 120)
check("a NaN closing speed is refused", hits(A) == 1, hits(A))
for _ = 1, 6 do frame(0.05) end
report(A, "headon", 150, 120)
check("A's real head-on 1.5 s later is accepted", hits(A) == 2 and #bindable == 2 and bindable[2][1] == A, hits(A))
-- a flood: five reports in one moment after the gap -> at most one counts
for _ = 1, 24 do frame(0.05) end
for _ = 1, 5 do report(A, "heavy", 90, 120) end
check("a flood of five reports counts once", hits(A) == 3, hits(A))
-- B never got anything, and every signal to the jobs server named A
local onlyA = true
for _, b in bindable do
	if b[1] ~= A then onlyA = false end
end
check("the jobs bump signal only ever named the player who was hit", onlyA and hits(B) == 0 and hits(C) == 0)
-- arcade off: reports are ignored
workspace._attr.CollisionModel = "physical"
for _ = 1, 30 do frame(0.05) end
report(A, "heavy", 90, 120)
check("with CollisionModel = physical every report is ignored", hits(A) == 3, hits(A))

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# TestKit end to end in a simulated client: PreSimulation -> physics -> Heartbeat frames at 15 / 30 / 60 fps, with a
# stand-in PattayaTraffic (the shared draw loop, DrawT, ghosts, the hold, the swept touch test, near misses) and a
# stand-in CarController (classifyHit, impactVelocity, push-out, the Recovery_LastHit* telemetry). Heartbeat handlers
# fire newest first, so TestKit's runner sees the models of the frame before (round 6's situation).
TKSIM = r'''
local RealR = require("./PattayaRecovery")
RealR._attr = function(name) return workspace and workspace._attr[name] end -- the module sees the mocked workspace
local DATA = require("./traffic")
__CHECK__
local T0 = 1792540800.25
local DT = 1 / 60
local EPS = 0 -- fake seconds per os.clock() call (the FPS cap's busy wait needs time to pass)
local clock = 0
local realOs = os
local os = {clock = function() clock += EPS return clock end, time = realOs.time, date = realOs.date}
local function now() return T0 + clock end
local LIFO = true
local STEP
local function newSignal()
	local s = {list = {}}
	function s:Connect(f)
		local c = {Connected = true}
		function c:Disconnect() self.Connected = false end
		table.insert(self.list, {f = f, c = c})
		return c
	end
	function s:Fire(...)
		local list = table.clone(self.list)
		if LIFO then
			for i = #list, 1, -1 do if list[i].c.Connected then list[i].f(...) end end
		else
			for i = 1, #list do if list[i].c.Connected then list[i].f(...) end end
		end
	end
	function s:Wait()
		STEP()
		return DT
	end
	return s
end
local function attrs(o)
	o._attr = o._attr or {}
	o._sig = {}
	o.GetAttribute = function(self, k) return self._attr[k] end
	o.SetAttribute = function(self, k, v)
		local old = self._attr[k]
		self._attr[k] = v
		if old ~= v and self._sig[k] then self._sig[k]:Fire() end
	end
	o.GetAttributeChangedSignal = function(self, k)
		self._sig[k] = self._sig[k] or newSignal()
		return self._sig[k]
	end
	return o
end
RaycastParams = {new = function() return {} end}
OverlapParams = {new = function() return {} end}
Enum = {RaycastFilterType = {Exclude = 1}, Material = {Asphalt = 1}}
local player = attrs({Name = "Tester"})
local RunService = {IsStudio = function() return true end, Heartbeat = newSignal(), RenderStepped = newSignal(),
	PreSimulation = newSignal(), Stepped = newSignal()}
local NitroBonus = {Name = "NitroBonus", OnClientEvent = newSignal()}
local JobUpdate = {Name = "JobUpdate", OnClientEvent = newSignal()}
local remotes = {Name = "PattayaRemotes", _c = {NitroBonus = NitroBonus, JobUpdate = JobUpdate}}
remotes.FindFirstChild = function(self, n) return self._c[n] end
local RECOVERY_MODULE, TRAFFIC_MODULE = {Name = "PattayaRecovery"}, {Name = "PattayaTraffic"}
local services = {
	Players = {LocalPlayer = player},
	RunService = RunService,
	ReplicatedStorage = {FindFirstChild = function(_, n)
		if n == "PattayaRecovery" then return RECOVERY_MODULE elseif n == "PattayaTraffic" then return TRAFFIC_MODULE
		elseif n == "PattayaRemotes" then return remotes end
		return nil
	end, WaitForChild = function() return nil end},
}
game = {GetService = function(_, n) return services[n] or {} end}
local folder = attrs({Name = "PattayaTraffic", _children = {}})
folder.GetChildren = function(self) return self._children end
folder.GetFullName = function() return "Workspace.PattayaTraffic" end
workspace = attrs({CurrentCamera = nil})
workspace.GetServerTimeNow = function() return now() end
workspace.FindFirstChild = function(_, n) if n == "PattayaTraffic" then return folder end return nil end
workspace.Raycast = function() return nil end
workspace._attr.CollisionModel = "arcade"

-- my car: a chassis whose CFrame / velocities TestKit sets and the fake physics integrates
local carModel = attrs({Name = "Car"})
carModel._attr.RaceCar = true
carModel.GetDescendants = function() return {} end
local car = {cf = CFrame.lookAt(Vector3.zero, Vector3.new(1, 0, 0)), v = Vector3.zero, av = Vector3.zero}
local chassis = setmetatable({}, {
	__index = function(_, k)
		if k == "CFrame" then return car.cf
		elseif k == "Position" then return car.cf.Position
		elseif k == "AssemblyLinearVelocity" then return car.v
		elseif k == "AssemblyAngularVelocity" then return car.av
		elseif k == "Parent" then return carModel
		elseif k == "Anchored" then return false
		end
		return nil
	end,
	__newindex = function(_, k, val)
		if k == "CFrame" then car.cf = val
		elseif k == "AssemblyLinearVelocity" then car.v = val
		elseif k == "AssemblyAngularVelocity" then car.av = val end
	end})
carModel.PrimaryPart = chassis
local seat = {Parent = carModel, IsA = function(_, c) return c == "VehicleSeat" end}
local hum = {SeatPart = seat}
player.Character = {FindFirstChildOfClass = function(_, c) if c == "Humanoid" then return hum end end,
	GetDescendants = function() return {} end}

-- the stand-in CarController.applyImpact (same maths and telemetry; the spin is applied at once)
local hitCount, touches = 0, 0
local INJECT = nil -- {after = s, vc = n}: a fake second hit on the same car `after` s later (re-hit test)
local KEY_OFFSET = 0 -- report the touch with another key (wrong-car test)
local firstHitT = nil
local function applyImpact(info, c)
	local res = RealR.classifyHit(info, c)
	local v = car.v
	local before = math.sqrt(v.X ^ 2 + v.Z ^ 2)
	local wx, wz = RealR.impactVelocity(v.X, v.Z, info.nx, info.nz, res)
	car.v = Vector3.new(wx, 0, wz)
	local push = math.min((info.depth or 0) + 0.5, c.Arcade_MaxPush)
	local p = car.cf.Position + Vector3.new(info.nx * push, 0, info.nz * push)
	local look = car.cf.LookVector
	local a = math.rad(res.yaw)
	local nl = Vector3.new(look.X * math.cos(a) + look.Z * math.sin(a), 0, -look.X * math.sin(a) + look.Z * math.cos(a))
	car.cf = CFrame.lookAt(p, p + nl)
	local window = 0
	if res.control > 0 or math.abs(res.yaw) > 0 then
		window = math.max(res.control, (RealR.spinProfile(res.yaw, math.max(res.control, 0.25))))
	end
	hitCount += 1
	player:SetAttribute("Recovery_LastHitKey", info.key)
	player:SetAttribute("Recovery_LastHitT", info.at)
	player:SetAttribute("Recovery_LastHitTier", res.tier)
	player:SetAttribute("Recovery_LastHitBefore", before)
	player:SetAttribute("Recovery_LastHitAfter", math.sqrt(wx * wx + wz * wz))
	player:SetAttribute("Recovery_LastHitTrafficSpeed", info.trafficSpeed)
	player:SetAttribute("Recovery_LastHitVc", info.vc)
	player:SetAttribute("Recovery_LastHitRel", info.rel)
	player:SetAttribute("Recovery_LastHitN", Vector3.new(info.nx, 0, info.nz))
	player:SetAttribute("Recovery_LastHitYaw", res.yaw)
	player:SetAttribute("Recovery_LastHitControl", window)
	player:SetAttribute("Recovery_HitCount", hitCount)
end

-- the stand-in PattayaTraffic: draw (shared maths), ghosts, the hold, the touch test, near misses, DrawT
local routes = RealR.buildTrafficRoutes(DATA, RealR.TRAFFIC_ORIGIN_X, RealR.TRAFFIC_ORIGIN_Z)
local entries = {}
local lastNearAt, serverNearAt = -math.huge, -math.huge
local function trafficFrame()
	local t = now()
	local c = RealR.config()
	local myPos = car.cf.Position
	local v = car.v
	local l = car.cf.LookVector
	local tk = player:GetAttribute("TK_HitTarget")
	local noHits = player:GetAttribute("TrafficGhostAll") == true
	local seen, children = {}, {}
	RealR.forEachTrafficCar(routes, t, myPos.X, myPos.Z, 650, function(key, x, z, _, r, k, _, s)
		seen[key] = true
		local e = entries[key]
		if not e then
			local sh = RealR.TRAFFIC_SHAPES[r.kinds[k]] or RealR.TRAFFIC_SHAPES[0]
			local m = attrs({Name = "Traffic", PrimaryPart = {Position = Vector3.zero, LocalTransparencyModifier = 0}})
			m.IsA = function(_, cl) return cl == "Model" end
			m._attr.TrafficKey = key
			e = {model = m, ghostUntil = -math.huge, halfWid = sh.wid / 2, halfLen = sh.len / 2}
			entries[key] = e
		end
		table.insert(children, e.model)
		local lx, lz = RealR.trafficHeading(r, s)
		e.model.PrimaryPart.Position = Vector3.new(x, 2.3, z)
		local dx, dz = myPos.X - x, myPos.Z - z
		local relX, relZ = dx * -lz + dz * lx, -(dx * lx + dz * lz)
		local along = v.X * lx + v.Z * lz
		if relZ < 0 and relZ > -(e.halfLen + 16) and math.abs(relX) < e.halfWid + 4 and along > -10
			and along < r.speed - 5 then
			e.ghostUntil = t + 1.5
		end
		if tk ~= nil and key ~= tk then e.ghostUntil = math.max(e.ghostUntil, t + 0.25) end
		local me = {x = myPos.X, z = myPos.Z, lx = l.X, lz = l.Z, vx = v.X, vz = v.Z}
		local tr = {x = x, z = z, lx = lx, lz = lz, speed = r.speed, halfWid = e.halfWid, halfLen = e.halfLen}
		if e.hitHold and t >= e.ghostUntil then
			RealR.hitGhostStep(e, t, RealR.carsOverlap(me, tr, 1))
		end
		local close = math.abs(relX) < e.halfWid + 12 and math.abs(relZ) < e.halfLen + 14
		local wasClose = e.lastRel and math.abs(e.lastRel[1]) < e.halfWid + 12 and math.abs(e.lastRel[2]) < e.halfLen + 14
		if t >= e.ghostUntil and not noHits and (close or wasClose) then
			local info = RealR.hitFromWorld(me, tr, e.lastRel and e.lastRel[1], e.lastRel and e.lastRel[2])
			if info then
				info.key, info.trafficSpeed, info.at, info.tx, info.tz = key + KEY_OFFSET, r.speed, t, x, z
				touches += 1
				player:SetAttribute("Traffic_Touches", touches)
				player:SetAttribute("Traffic_TouchKey", key)
				applyImpact(info, c)
				firstHitT = firstHitT or t
				RealR.hitGhostStart(e, t, c)
				e.near = false
			end
		end
		e.lastRel = {relX, relZ}
		local ghost = t < e.ghostUntil
		e.model.PrimaryPart.LocalTransparencyModifier = if ghost then 0.6 else 0
		local mySpeed = math.sqrt(v.X ^ 2 + v.Z ^ 2)
		if RealR.nearMissStep(e, relX, relZ, e.halfWid, e.halfLen, ghost, mySpeed, t, lastNearAt) then
			lastNearAt = t
			-- the jobs server's check (in a car, >= 60 studs/s, 0.6 s apart)
			if mySpeed >= 60 and t - serverNearAt >= 0.6 then
				serverNearAt = t
				player:SetAttribute("NearMissAt", t)
				NitroBonus.OnClientEvent:Fire(8)
			end
		end
	end)
	for key in entries do
		if not seen[key] then entries[key] = nil end
	end
	folder._children = children
	folder._attr.Positions = "shared"
	folder._attr.DrawT = t
	if INJECT and firstHitT and t >= firstHitT + INJECT.after then
		local info = {vc = INJECT.vc, approachDeg = 30, facingDot = 1, side = 1, front = true, nx = 0, nz = 1, depth = 0.2,
			key = player:GetAttribute("Recovery_LastHitKey"), trafficSpeed = 45, at = t, rel = INJECT.vc}
		INJECT = nil
		applyImpact(info, RealR.config())
	end
end
RunService.Heartbeat:Connect(trafficFrame) -- connected first: with newest-first firing it runs last in a frame

local frames, MAX_FRAMES = 0, 600000
STEP = function()
	frames += 1
	if frames > MAX_FRAMES then error("sim: too many frames") end
	clock += DT
	RunService.RenderStepped:Fire(DT)
	RunService.PreSimulation:Fire(DT)
	local p = car.cf.Position + Vector3.new(car.v.X * DT, 0, car.v.Z * DT)
	car.cf = CFrame.lookAt(p, p + car.cf.LookVector)
	local k = math.exp(-0.25 * DT) -- CarController's coast drag
	car.v = Vector3.new(car.v.X * k, 0, car.v.Z * k)
	RunService.Heartbeat:Fire(DT)
end

local realRequire = require
local require = function(m)
	if m == RECOVERY_MODULE then return RealR elseif m == TRAFFIC_MODULE then return DATA end
	return realRequire(m)
end
local _G = {}
local TK = (function()
__TESTKIT__
end)()

-- home spot: the traffic car with the most stageable cars around it (rear 70, the longest approach, on a straight)
local cfg = RealR.config()
local cars = {}
for ri, r in routes do
	for k2 = 1, #r.kinds do
		local x, z, s = RealR.trafficCarAt(r, k2, T0)
		local sh = RealR.TRAFFIC_SHAPES[r.kinds[k2]] or RealR.TRAFFIC_SHAPES[0]
		local _, _, span = RealR.stagePlan({route = r, s0 = s, t0 = T0, vT = r.speed, halfWid = sh.wid / 2,
			halfLen = sh.len / 2, speed = 70, mode = "rear"})
		table.insert(cars, {x = x, z = z, ok = RealR.routeStraight(r, span[1], span[2], RealR.STAGE_BEND_DEG)})
	end
end
local best, bestN = cars[1], -1
for i = 1, #cars, 3 do
	local a = cars[i]
	local n = 0
	for _, b in cars do
		if b.ok and (a.x - b.x) ^ 2 + (a.z - b.z) ^ 2 < 450 * 450 then n += 1 end
	end
	if n > bestN then best, bestN = a, n end
end
local spot = Vector3.new(best.x + 40, 3.8, best.z + 40)
local function home()
	car.cf = CFrame.lookAt(spot, spot + Vector3.new(1, 0, 0))
	car.v = Vector3.zero
	for _ = 1, 3 do STEP() end
end
home()

local function runMatrix(opts)
	local h = TK.hitMatrixStart(opts)
	local n = 0
	while not h.done do
		STEP()
		n += 1
		if n > 200000 then break end
	end
	return h
end
local function rowsOk(lines, want)
	local good, bad = 0, {}
	for _, l in lines do
		if l:sub(1, 5) == "PASS " then
			good += 1
			-- every owner field is on the line
			if not (l:find("target %d+, hit %d+, match") and l:find("impact %d+, traffic %d+, closing %d+")
				and l:find("| tier %a+ |") and l:find("loss %-?%d+%%") and l:find("yaw %-?%d+") and l:find("minUp %d")
				and l:find("Heartbeat %d+ Hz, render %d+ fps")) then
				table.insert(bad, "fields missing: " .. l)
			end
		elseif l:sub(1, 5) == "FAIL " then
			table.insert(bad, l)
		end
	end
	return good == want and #bad == 0, good, table.concat(bad, "\n")
end

-- 1. the whole matrix through the background runner at 15, 30 and 60 fps
for _, fps in {15, 30, 60} do
	DT = 1 / fps
	home()
	local h = runMatrix({runs = 1, around = spot, gap = 0.3})
	local ok, good, bad = rowsOk(h.lines, 12)
	check(("hitMatrixStart @%d fps: 12/12 PASS with every field on every row (%d)"):format(fps, good),
		ok and h.summary ~= nil and h.summary:find("12/12 PASS", 1, true) ~= nil, (h.error or "") .. "\n" .. bad)
	check(("@%d fps: nothing left behind (TK_HitTarget, FPS cap)"):format(fps),
		player:GetAttribute("TK_HitTarget") == nil and TK.fpsLimitOn() == nil)
	-- the runner ran before PattayaTraffic in each frame (newest first): its selfCheck saw the models of the
	-- frame before, and passed because positions are compared at DrawT
	local lag = nil
	for _, l in h.lines do
		local s = l:match("drawn models up to ([%d%.]+) studs")
		if s then lag = tonumber(s) end
	end
	check(("@%d fps: selfCheck in the runner passes with the models one frame behind (%.2f studs reported, not failed)")
		:format(fps, lag or -1), lag ~= nil and lag > 0.3, lag)
end

-- 2. the other handler order, 15 fps
LIFO = false
DT = 1 / 15
home()
local hF = runMatrix({runs = 1, around = spot, gap = 0.3})
check("handlers in connection order @15 fps: 12/12 PASS", (rowsOk(hF.lines, 12)), hF.summary or hF.error)
LIFO = true

-- 3. the FPS cap through hitMatrix: on during the rows, gone afterwards, also when the matrix errors
DT = 1 / 60
EPS = 1e-4
home()
local capSeen, rowHz = nil, nil
local summary = TK.hitMatrix({fps = 30, rows = {{"rear", 150}}, runs = 1, around = spot, gap = 0.3,
	onRow = function(_, _, res)
		capSeen = player:GetAttribute("TK_FpsLimit")
		rowHz = res and res.hz
	end})
check(("hitMatrix({fps = 30}): capped during the row (%s, %.0f Hz) and 1/1 PASS"):format(tostring(capSeen), rowHz or -1),
	capSeen == 30 and rowHz ~= nil and rowHz > 26 and rowHz < 34 and summary:find("1/1 PASS", 1, true) ~= nil, summary)
check("the cap is removed when the matrix ends", TK.fpsLimitOn() == nil and player:GetAttribute("TK_FpsLimit") == nil)
home()
local okErr, err = pcall(TK.hitMatrix, {fps = 30, rows = {{"rear", 150}}, runs = 1, around = spot, gap = 0.3,
	onRow = function() error("boom") end})
check("an error inside the matrix still removes the cap and the hook", not okErr and tostring(err):find("boom", 1, true)
	~= nil and TK.fpsLimitOn() == nil and player:GetAttribute("TK_FpsLimit") == nil
	and player:GetAttribute("TK_HitTarget") == nil, err)
EPS = 0

-- 4. a second hit on the same car half a second later: the run keeps the FIRST hit's numbers and reports the extra
DT = 1 / 30
home()
firstHitT = nil
INJECT = {after = 0.5, vc = 5}
local r4 = TK.hitTest("side", 70, {angle = 25, isolate = true, around = spot})
check(("re-hit: the staged hit's own numbers survive a later hit (tier %s, impact %s, %s more)"):format(tostring(r4.tier),
	tostring(r4.before and math.floor(r4.before)), tostring(r4.extraHits)),
	r4.touched and r4.tier == "light" and r4.before > 63 and r4.extraHits == 1 and r4.text:find("1 more hit", 1, true) ~= nil,
	r4.text)
INJECT = nil

-- 5. a hit event naming another key is not the staged hit
home()
KEY_OFFSET = 1
local r5 = TK.hitTest("rear", 150, {isolate = true, around = spot, tries = 1})
check("a hit reported on another car's key is rejected by key", not r5.touched and r5.keyMatch == false
	and r5.reason:find("another car (hit", 1, true) ~= nil, r5.reason)
KEY_OFFSET = 0

-- 6. stopping a running matrix: TK.cleanup drops the run's connections, the car is no longer driven
home()
local h6 = TK.hitMatrixStart({runs = 1, around = spot, gap = 0.3})
for _ = 1, 140 do STEP() end
h6:stop("test")
local v0 = car.v.Magnitude
for _ = 1, 20 do STEP() end
check("a stopped matrix leaves no hook and no driven car", player:GetAttribute("TK_HitTarget") == nil
	and car.v.Magnitude <= v0 + 1e-6, ("%.1f -> %.1f"):format(v0, car.v.Magnitude))

-- 7. near misses with arcade on: TK.nearMissTest
DT = 1 / 30
for _, c in {{gap = 5, speed = 110, want = 1}, {gap = 9, speed = 110, want = 0}, {gap = 5, speed = 65, want = 0, lead = 20}} do
	home()
	local r = TK.nearMissTest({gap = c.gap, speed = c.speed, around = spot, lead = c.lead})
	check(("nearMissTest gap %d @%d: %d near miss(es), %d hits (want %d, 0)"):format(c.gap, c.speed, r.awards, r.hits, c.want),
		r.ok and r.awards == c.want and r.hits == 0 and r.expected == c.want, r.text)
end

-- 8. jobWatch: an accepted heavy hit gives one bump; pay-out checked at the finish; a double bump is caught
local w = TK.jobWatch()
JobUpdate.OnClientEvent:Fire("start", {kind = "taxi", fare = 300, timeLimit = 60, start = now()})
for _ = 1, 3 do STEP() end
player:SetAttribute("Recovery_LastHitTier", "heavy")
player:SetAttribute("Recovery_HitCount", (player:GetAttribute("Recovery_HitCount") or 0) + 1)
player:SetAttribute("TrafficHitTier", "heavy")
player:SetAttribute("TrafficHits", 1)
for _ = 1, 6 do STEP() end
JobUpdate.OnClientEvent:Fire("bump", 1)
for _ = 1, 60 do STEP() end
JobUpdate.OnClientEvent:Fire("finish", {time = 40, money = 294, exp = 10, tip = 30, bumps = 1})
local text1, ok1 = w:report()
check("jobWatch: one accepted heavy hit, one bump, pay-out right", ok1, text1)
JobUpdate.OnClientEvent:Fire("start", {kind = "taxi", fare = 300, timeLimit = 60, start = now()})
player:SetAttribute("TrafficHitTier", "heavy")
player:SetAttribute("TrafficHits", 2)
STEP()
JobUpdate.OnClientEvent:Fire("bump", 1)
for _ = 1, 10 do STEP() end
JobUpdate.OnClientEvent:Fire("bump", 2)
local text2, ok2 = w:report()
check("jobWatch: two bumps for one crash are caught", not ok2 and text2:find("counted twice", 1, true) ~= nil, text2)
w:stop()

print(("%d passed, %d failed"):format(passes, fails))
print("FAILS", fails)
'''

# a synthetic map for the TestKit simulation when build/ is missing: long straight loops both ways round
SIM_DATA = r'''
local out = {}
for i = 0, 3 do
	local z0 = i * 60
	local pts = {0, z0, 3000, z0, 3000, z0 + 600, 0, z0 + 600, 0, z0}
	if i % 2 == 1 then pts = {0, z0, 0, z0 + 600, 3000, z0 + 600, 3000, z0, 0, z0} end
	local kinds = {}
	for k = 1, 16 do table.insert(kinds, (k + i) % 3) end
	table.insert(out, {length = 0, speed = 40 + 5 * i, phase = 37 * i, kinds = kinds, pts = pts})
end
return out
'''


def _real_traffic():
    """The generated map's traffic module (build/pattaya_wide), or None."""
    if _qa.BUILD:
        cand = os.path.join(_qa.BUILD, 'pattaya_wide', 'roblox', 'traffic.luau')
        if os.path.exists(cand):
            return _qa.read(cand)
    return None


class _Harness(unittest.TestCase):
    def harness(self, main, files, min_pass):
        prelude = _qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau'))
        code, out = _qa.run_luau(prelude + '\n' + main.replace('__CHECK__', CHECK), files, timeout=900)
        self.assertEqual(code, 0, out[-3000:])
        fails = [line for line in out.splitlines() if line.startswith('FAIL ')]
        self.assertEqual(fails, [], out[-5000:])
        self.assertIn('FAILS\t0', out, out[-3000:])
        self.assertGreaterEqual(out.count('PASS '), min_pass, out[-2000:])
        return out


class LaneCleanup(_Harness):
    """Round 6, route 26: the generated lanes double back at corners; PattayaRecovery cleans them (seam included)."""

    def test_lane_cleanup(self):
        runs = [('synthetic', SYNTH_DATA, 'false')]
        real = _real_traffic()
        if real:
            runs.append(('pattaya_wide', real, 'true'))
        for name, data, flag in runs:
            with self.subTest(data=name):
                self.harness(LANES.replace('__REAL__', flag), {'PattayaRecovery.luau': src(MOD), 'traffic.luau': data},
                             17 if flag == 'true' else 12)


class StagedRealRoutes(_Harness):
    """Every row of the owner's table staged on the real routes the way TK.hitTest stages it, at 15 / 30 / 60 fps,
    and round 6's route 26 rear 70 failures reproduced on the raw lanes and gone on the cleaned ones."""

    def test_every_row_on_the_real_routes(self):
        real = _real_traffic()
        if not real:
            raise unittest.SkipTest('build/pattaya_wide/roblox/traffic.luau missing')
        self.harness(SCAN, {'PattayaRecovery.luau': src(MOD), 'traffic.luau': real}, 7)


class LowClosingSpeed(_Harness):
    """Rear 70 review: slow closing (2-25 studs/s), long overlap build-up, the loop seam; side 70's repeat hit."""

    def test_low_closing_speed_and_repeat_hits(self):
        self.harness(LOWVC, {'PattayaRecovery.luau': src(MOD)}, 150)


class AntiRollAndNearMiss(_Harness):
    def test_anti_roll_maths_and_near_misses(self):
        self.harness(ANTIROLL_NEAR, {'PattayaRecovery.luau': src(MOD)}, 26)


class ServerTwoPlayers(_Harness):
    """PattayaRecoveryServer's TrafficHit check with two players: real hits accepted, fakes refused, no cross-talk."""

    def test_traffic_hit_two_players(self):
        main = SERVER2P.replace('__SERVER__', src(SERVER))
        runs = [('synthetic', SYNTH_DATA)]
        real = _real_traffic()
        if real:
            runs.append(('pattaya_wide', real))
        for name, data in runs:
            with self.subTest(data=name):
                self.harness(main, {'PattayaRecovery.luau': src(MOD), 'traffic.luau': data}, 12)


class TestKitSimulation(_Harness):
    """TK.hitMatrix / hitMatrixStart / hitTest / nearMissTest / jobWatch end to end in a simulated client (stand-in
    PattayaTraffic and CarController on the shared maths) at 15 / 30 / 60 fps, the FPS cap and every cleanup path."""

    def test_testkit_end_to_end(self):
        main = TKSIM.replace('__TESTKIT__', src(TESTKIT))
        runs = [('synthetic', SIM_DATA)]
        real = _real_traffic()
        if real:
            runs.append(('pattaya_wide', real))
        for name, data in runs:
            with self.subTest(data=name):
                self.harness(main, {'PattayaRecovery.luau': src(MOD), 'traffic.luau': data}, 17)


class ArcadeHitScope(unittest.TestCase):
    """Owner review round 6: the fixes change only the arcade hit response and TestKit; the car physics, the
    physical default and the multiplayer scope stay as they were."""

    @classmethod
    def setUpClass(cls):
        cls.car = _qa.strip_comments(src(CAR))
        cls.traffic = _qa.strip_comments(src(TRAFFIC))
        cls.tk = _qa.strip_comments(src(TESTKIT))

    @staticmethod
    def _body(code, head):
        i = code.index(head)
        return code[i:code.index('\nend\n', i)]

    def test_anti_roll_only_in_the_hit_window(self):
        car = self.car
        self.assertEqual(car.count('Instance.new("AlignOrientation")'), 1)
        on = self._body(car, 'local function antiRollOn(')
        self.assertIn('Instance.new("AlignOrientation")', on)
        self.assertIn('align.Enabled = true', on)
        self.assertEqual(car.count('align.Enabled = true'), 1, 'the AlignOrientation is switched on in antiRollOn only')
        self.assertEqual(car.count('antiRollOn('), 2, 'defined once, called once (applyImpact)')
        impact = self._body(car, 'local function applyImpact(')
        self.assertIn('if cfg.Arcade_AntiRoll then', impact)
        # round 8: the hold comes from PattayaRecovery.antiRollHold (window + 0.25 s; heavy / head-on + their slide)
        self.assertIn('antiRollOn(chassis, up0, now + Recovery.antiRollHold(res.tier, window, cfg), cfg)', impact)
        self.assertIn('if hitNow >= antiRoll.untilT then', car)
        self.assertGreaterEqual(car.count('antiRollOff()'), 4, 'window end, enter, exit')
        mod = _qa.strip_comments(src(MOD))
        hold = self._body(mod, 'function R.antiRollHold(')
        self.assertIn('if tier == "heavy" or tier == "headon" then', hold)
        self.assertIn('cfg.Arcade_AntiRollHeavyExtra', hold)

    def test_car_physics_unchanged(self):
        raw = src(CAR)
        for const in ('suspensionRest = 1.6', 'sag = 0.45', 'dampingRatio = 0.35', 'coastDrag = 0.25',
                      'turnRate = 2.3', 'grip = 9,', 'driftGrip = 1.4', 'airUpright = 3'):
            self.assertIn(const, raw)
        self.assertIn('local grip = (state.drift or (hitWin and hitWin.slide)) and tune.driftGrip or tune.grip', raw)
        for word in ('CustomPhysicalProperties', 'Massless', 'AssemblyMass ='):
            self.assertNotIn(word, raw)

    def test_arcade_never_the_default(self):
        self.assertRegex(src(MOD), r'CollisionModel = "physical"')
        for path in _qa.luau_files():
            text = _qa.strip_comments(_qa.read(path))
            if path.endswith('PattayaTestKitServer.luau'):
                # team18/arcade-econ: the server kit's test-only lease (Studio / DevTest) is the one place that sets
                # it: "arcade" for a test, then the value from before (tools/qa/tests/test_jobdrive.py)
                sets = re.findall(r'SetAttribute\(\s*"CollisionModel"\s*,\s*([^)]*)\)', text)
                self.assertEqual(sorted(sets), ['"arcade"', 'back'], path)
                self.assertLess(text.index('if not enabled() then'), text.index('function S.arcadeLease('))
                continue
            self.assertNotRegex(text, r'SetAttribute\(\s*"CollisionModel"', path)

    def test_hit_identity_and_telemetry(self):
        traffic, car = self.traffic, self.car
        self.assertIn('info.key, info.trafficSpeed, info.at, info.tx, info.tz = key, speed, t, q.X, q.Z', traffic)
        self.assertIn('folder:SetAttribute("DrawT", t)', traffic)
        self.assertIn('Recovery.hitGhostStep(entry, t, Recovery.carsOverlap(', traffic)
        self.assertIn('Recovery.hitGhostStart(entry, t, Recovery.config())', traffic)
        self.assertIn('Recovery.nearMissStep(entry, rel.X, rel.Z, entry.halfWid, entry.halfLen, entry.ghost', traffic)
        impact = self._body(car, 'local function applyImpact(')
        count_at = impact.index('player:SetAttribute("Recovery_HitCount", hitCount)')
        for field in ('Key', 'T', 'Tier', 'Before', 'After', 'TrafficSpeed', 'Vc', 'Rel', 'N', 'Yaw', 'Control'):
            at = impact.index(f'player:SetAttribute("Recovery_LastHit{field}"')
            self.assertLess(at, count_at, f'Recovery_LastHit{field} is set before the count')
        for why in ('bad payload', 'not driving', 'arcade off', 'car anchored', 'auto-upright running'):
            self.assertIn(why, impact)

    def test_testkit_identifies_hits_by_key(self):
        tk = self.tk
        self.assertIn('hitKey = snap.key,', tk)
        self.assertIn('targetKey = target.key', tk)
        accept = tk[tk.index('Rec.acceptStagedHit({'):]
        accept = accept[:accept.index('})')]
        self.assertNotIn('hitX', accept, 'no position form: the hit names its car')
        self.assertIn('local function drawT()', tk)
        # TestKit (and its FPS cap) only loads in Studio / DevTest places
        self.assertLess(tk.index('if not enabled() then'), tk.index('function TK.fpsLimit('))

    def test_multiplayer_scope(self):
        traffic, car = self.traffic, self.car
        # PattayaTraffic tests only the local player's own car; CarController applies a hit to its own car
        self.assertIn('local car = myCar()', traffic)
        self.assertIn('local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")', traffic)
        self.assertIn('local chassis = current.chassis', self._body(car, 'local function applyImpact('))
        jobs = _qa.strip_comments(src(os.path.join('ServerScriptService', 'PattayaJobsServer.server.luau')))
        hook = jobs[jobs.index('hitSignal.Event:Connect(function(plr, tier)'):]
        hook = hook[:hook.index('end)')]
        self.assertIn('local st = active[plr]', hook)
        self.assertIn('(tier == "heavy" or tier == "headon") and now - st.lastBumpAt > 1', hook)


class RecoveryWiring(unittest.TestCase):
    """Static checks: the switches, remotes and rollback paths the doc promises are in the code."""

    @classmethod
    def setUpClass(cls):
        cls.mod = src(MOD)
        cls.car = _qa.strip_comments(src(CAR))
        cls.traffic = _qa.strip_comments(src(TRAFFIC))
        cls.server = _qa.strip_comments(src(SERVER))

    def test_defaults(self):
        self.assertRegex(self.mod, r'CollisionModel = "physical"')
        self.assertRegex(self.mod, r'Recovery_Enabled = true')
        self.assertRegex(self.mod, r'Recovery_UprightDelay = 1\.5')
        self.assertRegex(self.mod, r'Recovery_StuckTime = 4\b')
        self.assertRegex(self.mod, r'Recovery_ResetCooldown = 2\b')
        self.assertRegex(self.mod, r'Recovery_RescueAuto = false')

    def test_legacy_reset_kept_when_switched_off(self):
        """Recovery_Enabled = false gives today's R: flip in place with the 6-stud lift, no cooldown."""
        self.assertIn('flipInPlace(current.chassis, 6)', self.car)
        self.assertIn('recoveryOn()', self.car)

    def test_server_remotes(self):
        for name in ('RequestRescue', 'RescueUpdate', 'TrafficHit'):
            self.assertRegex(self.server, rf'local {name} = remote\("{name}"\)')
        self.assertIn('RequestRescue.OnServerEvent', self.server)
        self.assertIn('TrafficHit.OnServerEvent', self.server)
        self.assertIn('RescueUpdate:FireClient', self.server)
        self.assertIn('CircuitActive', self.server, 'circuits keep their T reset')

    def test_rescue_only_uses_the_trail_in_races(self):
        """In a race the rescue spot is a trail point (never a free nearest-road snap) and passes the gate clamp."""
        self.assertIn('gateAllows', self.server)
        self.assertIn('cpAllows', self.server)
        self.assertRegex(self.server, r'elseif not racing and Route and graph then')

    def test_traffic_switch(self):
        self.assertIn('CollisionModel', self.traffic)
        self.assertIn('CarImpact', self.traffic)
        self.assertIn('CarImpact', self.car)
        self.assertIn('NearMiss:FireServer', self.traffic, 'near misses still reported')
        # physical stays the default: the boxes only stop colliding when the attribute says "arcade"
        self.assertIn('workspace:GetAttribute("CollisionModel") == "arcade"', self.traffic)
        self.assertIn('entry.root.CanCollide = not on and not arcade', self.traffic)
        self.assertRegex(self.traffic, r'local arcade = false')
        # the TestKit "only the target is real" hook works only in Studio / DevTest places
        self.assertIn('TK_HitTarget', self.traffic)
        self.assertIn('IS_STUDIO or workspace:GetAttribute("DevTest") == true', self.traffic)
        # the impact is ignored unless arcade is on (a stale event after switching back does nothing)
        self.assertIn('Recovery.arcade()', self.car)
        # a traffic hit never rolls the car: during the hit window only the yaw about the up axis it had at the
        # touch is kept (AlignOrientation + per-step projection, arcade hit response only: ArcadeHitScope)
        self.assertIn('Recovery.yawOnlyRate(av.X, av.Y, av.Z, u0.X, u0.Y, u0.Z)', self.car)
        self.assertIn('antiRollOn(chassis, up0, now + Recovery.antiRollHold(res.tier, window, cfg), cfg)', self.car)

    def test_no_new_client_scripts(self):
        """Client logic lives in CarController / PattayaTraffic: the QA runner's CLIENT_SCRIPTS list stays valid."""
        folder = os.path.join(_qa.SRC, 'StarterPlayer', 'StarterPlayerScripts')
        names = [f for f in os.listdir(folder) if 'Recovery' in f or 'Collision' in f]
        self.assertEqual(names, [])

    def test_doc_exists(self):
        doc = _qa.read(os.path.join(_qa.DOCS, 'RECOVERY_AND_COLLISION.md'))
        for word in ('Recovery_Enabled', 'CollisionModel', 'Rollback', 'flipTest', 'TrafficHit'):
            self.assertIn(word, doc)


if __name__ == '__main__':
    unittest.main()
