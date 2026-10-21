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
