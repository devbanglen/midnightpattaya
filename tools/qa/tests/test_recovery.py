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
                self.assertGreaterEqual(out.count('PASS '), 8, out[-1500:])

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
        # a traffic hit never rolls the car: pitch / roll are zeroed during the hit window
        self.assertIn('chassis.AssemblyAngularVelocity = up * av:Dot(up)', self.car)

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
