-- Server-side judge of one car on one circuit (one tracker per participant). Feed it the chassis position every
-- Heartbeat with tracker:sample(pos, now); it returns a list of events. It never trusts the client: everything is
-- worked out from the replicated chassis position.
--
-- Rules
-- * Gates (CircuitRegistry): a gate counts when the path between two samples crosses its plane going forwards
--   (edge-triggered, like the loop race) within the track half width + SIDE_MARGIN. Gates the pit lane bypasses also
--   count when crossed inside the pit lane (gate.pitLat), so a lap through the pits is still a lap.
-- * Order: gates must be passed in order. Crossing a later gate (up to LOOKAHEAD ahead) re-syncs the tracker and
--   reports the skipped gates as missed (= the lap was cut). Pit-bypassed gates the pit lane never crosses are
--   skipped silently while in pit mode.
-- * Before the first start/finish crossing a tracker is unarmed (out lap): only gate 1 is watched.
-- * Teleport: more than MAX_SPEED studs/s over a 0.25 s window -> "teleport" event (the run is invalid).
--   A single sample-to-sample jump over 60 studs is never judged as a crossing (respawn / server reset).
-- * Track limits: chassis more than width/2 + LIMIT_ALLOW from the centerline (and not inside the pit lane) for
--   more than LIMIT_TIME -> "trackLimit". Cut: an off-track excursion that gains more centerline progress than the
--   distance driven while off (x1.05 + 8 studs) -> "cut".
-- * Wrong way: centerline progress going backwards for more than WRONG_WAY_DIST -> "wrongWay" on/off.
-- * Pit lane: crossing the pit entry gate starts pit mode, the exit gate ends it. In pit mode, speed above the
--   limit + PIT_TOL -> "pitSpeed" (warning, once per visit); above it for PIT_PENALTY_TIME in total -> "pitPenalty".
-- Event kinds: gate {gate, t, missed}, teleport {speed}, offTrack {on}, trackLimit, cut {gain}, wrongWay {on},
-- pit {on}, pitSpeed {speed}, pitPenalty {speed}.
local ServerStorage = game:GetService("ServerStorage")
local Registry = require(ServerStorage:WaitForChild("CircuitRegistry"))

local Validator = {}
Validator.MAX_SPEED = 260 -- studs/s: nitro top speed is 215
Validator.SIDE_MARGIN = 10 -- a gate still counts this far past the track edge
Validator.LIMIT_ALLOW = 6 -- chassis centre this far past the edge = all four wheels off (car is 7 wide)
Validator.LIMIT_TIME = 1.0
Validator.WRONG_WAY_DIST = 30
Validator.LOOKAHEAD = 4
Validator.PIT_TOL = 3
Validator.PIT_PENALTY_TIME = 1.5
local JUMP = 60

local Tracker = {}
Tracker.__index = Tracker

function Validator.new(circuit)
	return setmetatable({
		c = circuit,
		armed = false, -- false = out lap, waiting for the start/finish line
		next = 1, -- expected gate
		lastGate = nil, -- last gate passed (reset point)
		pit = false,
		speed = 0,
		s = 0,
		lateral = 0,
		hint = nil,
		back = 0,
		wrongWay = false,
		off = false,
		offSince = nil,
		offFlagged = false,
		offStartS = 0,
		offDriven = 0,
		pitOver = 0,
		pitWarned = false,
		pitPenalised = false,
	}, Tracker)
end

-- Arms the tracker at arc length s (a race start on a grid ahead of the line): the next gate is the first one
-- past s, as if the lap had already started.
function Tracker:armAt(s: number)
	local gates = self.c.gates
	self.armed = true
	self.next = 1
	for i, g in gates do
		if g.s > s + 1 then
			self.next = i
			break
		end
	end
	self.lastGate = (self.next - 2) % #gates + 1
end

-- After a server-side move (reset to a gate, grid placement): forget the previous sample so it is not judged.
function Tracker:moved(pos: Vector3, now: number)
	self.lastPos, self.lastT = pos, now
	self.winPos, self.winT = pos, now
	self.hint = nil
	self.back = 0
	self.sValid = false -- the next sample sets s without judging direction
	self.offSince, self.offFlagged, self.off = nil, false, false
end

-- CFrame on the track to put a car back at: the last gate passed (or the nearest centerline point when unarmed)
function Tracker:resetFrame(pos: Vector3): CFrame
	local c = self.c
	local at, dir
	if self.lastGate and not self.pit then
		local g = c.gates[self.lastGate]
		at, dir = g.pos, g.dir
	else
		local near = Registry.nearest(c, pos, self.hint)
		at, dir = Registry.pointAt(c, near.s)
	end
	return CFrame.lookAt(at, at + dir)
end

-- does the move a -> b cross gate g forwards within its width? returns (hit, fraction of the move)
local function crossGate(g, a: Vector3, b: Vector3, pit): (boolean, number)
	local ra = g.cf:PointToObjectSpace(a)
	local rb = g.cf:PointToObjectSpace(b)
	if not (ra.Z > 0 and rb.Z <= 0) then
		return false, 0
	end
	local f = ra.Z / (ra.Z - rb.Z)
	local hit = ra:Lerp(rb, f)
	if math.abs(hit.Y) > 20 then
		return false, 0
	end
	if math.abs(hit.X) < g.halfWidth + Validator.SIDE_MARGIN then
		return true, f
	end
	if pit and g.pitLat and math.abs(hit.X - g.pitLat) < pit.width / 2 + Validator.SIDE_MARGIN then
		return true, f
	end
	return false, 0
end

function Tracker:sample(pos: Vector3, now: number)
	local ev = {}
	local c = self.c
	if not self.lastPos then
		self:moved(pos, now)
		return ev
	end
	local a, ta = self.lastPos, self.lastT
	self.lastPos, self.lastT = pos, now
	-- teleport check over 0.25 s windows (replication jitter averages out)
	if now - self.winT >= 0.25 then
		local v = (pos - self.winPos).Magnitude / (now - self.winT)
		self.winPos, self.winT = pos, now
		self.speed = v
		if v > Validator.MAX_SPEED then
			table.insert(ev, {kind = "teleport", speed = v})
			self.hint = nil
			self.sValid = false
			return ev
		end
	end
	if (pos - a).Magnitude > JUMP then
		self.hint = nil
		self.sValid = false
		return ev
	end

	local near = Registry.nearest(c, pos, self.hint)
	local prevS = if self.sValid then self.s else near.s
	self.hint, self.s, self.lateral = near.index, near.s, near.lateral
	self.sValid = true
	local pitDist = Registry.nearestPit(c, pos)
	local pit = c.pit
	local inPitLane = pit ~= nil and pitDist < pit.width / 2 + 4
	local onCircuit = near.dist < near.width * 2 + 40 or inPitLane

	-- pit lane mode
	if pit then
		if not self.pit and crossGate(pit.entryGate, a, pos, nil) then
			self.pit = true
			self.pitOver, self.pitWarned, self.pitPenalised = 0, false, false
			table.insert(ev, {kind = "pit", on = true})
		elseif self.pit and (crossGate(pit.exitGate, a, pos, nil) or (not inPitLane and near.dist < near.width / 2)) then
			self.pit = false
			table.insert(ev, {kind = "pit", on = false})
		end
		if self.pit and inPitLane and near.dist > near.width / 2 + 4 then
			if self.speed > pit.limit + Validator.PIT_TOL then
				self.pitOver += now - ta
				if not self.pitWarned then
					self.pitWarned = true
					table.insert(ev, {kind = "pitSpeed", speed = self.speed})
				end
				if self.pitOver > Validator.PIT_PENALTY_TIME and not self.pitPenalised then
					self.pitPenalised = true
					table.insert(ev, {kind = "pitPenalty", speed = self.speed})
				end
			end
		end
	end

	-- wrong way: progress going backwards
	if onCircuit then
		local ds = Registry.wrapDelta(c, prevS, self.s)
		if ds < -0.2 then
			self.back += -ds
		elseif ds > 0.2 then
			self.back = math.max(0, self.back - ds * 2)
		end
		local wrong = self.back > Validator.WRONG_WAY_DIST
		if wrong ~= self.wrongWay then
			self.wrongWay = wrong
			table.insert(ev, {kind = "wrongWay", on = wrong})
		end
	end

	-- gates
	local gates = c.gates
	local count = #gates
	local pitArg = if pit then pit else nil
	if not self.armed then
		local hit, f = crossGate(gates[1], a, pos, pitArg)
		if hit then
			self.armed = true
			self.next = 1 % count + 1
			self.lastGate = 1
			table.insert(ev, {kind = "gate", gate = 1, t = ta + (now - ta) * f, missed = false})
		end
	else
		for look = 0, Validator.LOOKAHEAD do
			local k = (self.next - 1 + look) % count + 1
			local g = gates[k]
			local skippable = self.pit and g.inBypass and not g.pitLat
			if not skippable then
				local hit, f = crossGate(g, a, pos, pitArg)
				if hit then
					local tc = ta + (now - ta) * f
					for m = 0, look do
						local j = (self.next - 1 + m) % count + 1
						local gj = gates[j]
						local silent = self.pit and gj.inBypass and not gj.pitLat
						table.insert(ev, {kind = "gate", gate = j, t = tc, missed = m < look and not silent})
					end
					self.next = k % count + 1
					self.lastGate = k
					break
				end
			end
		end
	end

	-- track limits and cutting (only once on a timed lap)
	if self.armed then
		local edge = near.width / 2 + Validator.LIMIT_ALLOW
		local off = near.dist > edge and not inPitLane
		if off then
			if not self.off then
				self.off = true
				self.offSince = now
				self.offFlagged = false
				self.offStartS = prevS
				self.offDriven = 0
				table.insert(ev, {kind = "offTrack", on = true})
			end
			self.offDriven += Vector3.new(pos.X - a.X, 0, pos.Z - a.Z).Magnitude
			if not self.offFlagged and now - (self.offSince :: number) > Validator.LIMIT_TIME then
				self.offFlagged = true
				table.insert(ev, {kind = "trackLimit"})
			end
		elseif self.off then
			self.off = false
			table.insert(ev, {kind = "offTrack", on = false})
			local gain = Registry.wrapDelta(c, self.offStartS, self.s)
			if gain > 20 and gain > self.offDriven * 1.05 + 8 then
				table.insert(ev, {kind = "cut", gain = gain})
			end
		end
	end
	return ev
end

return Validator
