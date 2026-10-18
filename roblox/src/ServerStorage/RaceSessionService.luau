-- Circuit sessions: who is on which circuit in which mode, the start procedure, penalties, results and rewards.
-- Data-driven: works on any circuit CircuitRegistry compiled. Wired to remotes by CircuitServer.
--
-- Each circuit has two session slots:
--   open   FreePractice / TimeAttack / TrackDay. Starts as soon as someone joins, anyone at the circuit can join
--          (same mode), ends when the last driver leaves. Cars start in the pit lane on an out lap; the first
--          start/finish crossing starts the timed lap. Rolling laps, no start lights.
--   formal CircuitRace / PrivateRoom. State machine:
--          Idle -> Forming (join window: 25 s public, until the owner presses Start in a private room)
--               -> Grid (cars placed and held on the grid slots, by join order or personal best, 3 s; the open
--                  session on that circuit is closed and its drivers moved to the paddock)
--               -> StartLights (5 red lights 1 s apart, then a random 0.5-2 s hold; moving more than 4 studs
--                  before the lights go out = jump start, +5 s)
--               -> Racing (laps judged by CheckpointValidator, timed by LapTimingService)
--               -> Finishing (after the winner: everyone else has 60 s, then DNF)
--               -> Results (12 s on screen, rewards paid) -> Idle
-- Rules per mode (valid laps only ever count as bests):
--   FreePractice  timing optional (opts.timing = false hides it), ghost cars, small EXP per valid lap
--   TimeAttack    ghost cars, sectors, personal best saved, global board (OrderedDataStore), pays per valid lap
--   TrackDay      collisions on, timing for everyone, personal best saved (no global writes)
--   CircuitRace   collisions on, 3/5/10/custom laps (1-20), grid by join order or PB, finishing order by total
--                 time incl. penalties, DNF 60 s after the winner, pays by place
--   PrivateRoom   a CircuitRace with an owner: invite list, laps, collisions on/off, allowed classes, spectators;
--                 pays EXP only
-- Penalties in races (time added to the result): jump start +5, cut +3 (once per lap), track limits: 2 warnings then +5 each,
-- pit lane speeding +5. In open sessions the same offences just invalidate the lap. Teleport = disqualified
-- (race) / lap invalid (open). Reset to the last gate is allowed (3 s cooldown) and invalidates the lap.
-- Allowed classes read the car model attribute "Class" (missing = "Street"). Upgrades are never required.
-- Ghost mode = CollisionGroup "CircuitGhost" (does not collide with itself) on the car and the seated driver.
-- Player attributes (read by CircuitRaceClient): CircuitActive, CircuitId, CircuitName, CircuitMode, CircuitState,
-- CircuitLap, CircuitLaps, CircuitLapStart, CircuitLastLap, CircuitBestLap, CircuitPB, CircuitLapValid,
-- CircuitPos, CircuitCount, CircuitGap, CircuitPit, CircuitPitLimit, CircuitOff, CircuitWrongWay, CircuitPenalty,
-- CircuitFormEnds, CircuitFinished, CircuitOwner.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local PhysicsService = game:GetService("PhysicsService")
local ServerStorage = game:GetService("ServerStorage")

local Registry = require(ServerStorage:WaitForChild("CircuitRegistry"))
local Validator = require(ServerStorage:WaitForChild("CheckpointValidator"))
local Timing = require(ServerStorage:WaitForChild("LapTimingService"))
local Leaderboard = require(ServerStorage:WaitForChild("LeaderboardService"))
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))

local Service = {}

Service.OPEN_MODES = {FreePractice = true, TimeAttack = true, TrackDay = true}
Service.FORMAL_MODES = {CircuitRace = true, PrivateRoom = true}
Service.CLASSES = {"Street", "Sport", "Super", "Hyper", "Track Spec"}

local FORM_TIME = 25
local GRID_TIME = 3
local LIGHT_INTERVAL = 1
local HOLD_MIN, HOLD_MAX = 0.5, 2.0
local JUMP_DIST = 4
local JUMP_SETTLE = 0.75 -- s after the lights start before jump starts are judged (client ownership handoff)
local JUMP_PENALTY = 5
local CUT_PENALTY = 3
local LIMIT_FREE_WARNINGS = 2
local LIMIT_PENALTY = 5
local PIT_PENALTY = 5
local DNF_AFTER_WINNER = 60
local RESULTS_TIME = 12
local RESET_COOLDOWN = 3
local CHASSIS_UP = 2.8 -- chassis centre above the surface (as driven)
local MAX_LAPS = 20
local PRIVATE_IDLE = 600
local AT_CIRCUIT = 600 -- studs from the centerline/paddock that count as "at the circuit"
local GHOST = "CircuitGhost"

-- Ranked play: interfaces only (not enabled). A rating per class bucket would be saved with
-- Progress.SetData(plr, "circuitRating", {[bucket] = rating}).
Service.Ranked = {
	enabled = false,
	ratingKey = "circuitRating",
	defaultRating = 1000,
	bucketOf = function(class: string): string
		return class -- one bucket per car class
	end,
	-- return false to throw a result away (e.g. too few drivers, a DNF storm, mismatched classes)
	validate = function(session, rows): boolean
		return #rows >= 2
	end,
	apply = function(session, rows) end, -- rating update goes here
}

-- Future systems subscribe here (flags, safety car, tyre wear, fuel, damage, replay, ghosts, AI, marshals).
-- Callbacks run in their own thread: onState(session), onGate(session, part, gate, t), onLap(session, part, lap),
-- onIncident(session, part, kind, data), onResults(session, rows).
Service.hooks = {onState = {}, onGate = {}, onLap = {}, onIncident = {}, onResults = {}}
local function fire(name: string, ...)
	for _, f in Service.hooks[name] do
		task.spawn(f, ...)
	end
end

local send = function(_plr: Player, _kind: string, _payload: any) end
local slots = {} -- [circuitId] = {open = session?, formal = session?}
local byPlayer = {} -- [player] = part
local spectating = {} -- [player] = session
local lastReset = {}
local nextId = 0

local function now(): number
	return workspace:GetServerTimeNow()
end

local function fmt(t: number?): string
	if not t then
		return "-"
	end
	return string.format("%d:%06.3f", t // 60, t % 60)
end

local function slotOf(id: string)
	slots[id] = slots[id] or {}
	return slots[id]
end

local function classOf(car: Model?): string
	local c = car and car:GetAttribute("Class")
	return if type(c) == "string" and c ~= "" then c else "Street"
end

local function attrs(plr: Player, t)
	for k, v in t do
		plr:SetAttribute(k, v)
	end
end

local ATTRS = {"CircuitId", "CircuitName", "CircuitMode", "CircuitState", "CircuitLap", "CircuitLaps",
	"CircuitLapStart", "CircuitLastLap", "CircuitBestLap", "CircuitPB", "CircuitLapValid", "CircuitPos",
	"CircuitCount", "CircuitGap", "CircuitPit", "CircuitPitLimit", "CircuitOff", "CircuitWrongWay", "CircuitPenalty",
	"CircuitFormEnds", "CircuitFinished", "CircuitOwner"}

local function clearAttrs(plr: Player)
	for _, k in ATTRS do
		plr:SetAttribute(k, nil)
	end
	plr:SetAttribute("CircuitActive", false)
end

-- collision ------------------------------------------------------------------------------------------------------
pcall(function()
	PhysicsService:RegisterCollisionGroup(GHOST)
end)
pcall(function()
	PhysicsService:CollisionGroupSetCollidable(GHOST, GHOST, false)
end)

local function setGhost(part, on: boolean)
	if on == (part.ghost == true) then
		return
	end
	if on then
		part.groups = {}
		local list = part.car:GetDescendants()
		local ch = part.plr.Character
		if ch then
			for _, d in ch:GetDescendants() do table.insert(list, d) end
		end
		for _, d in list do
			if d:IsA("BasePart") then
				part.groups[d] = d.CollisionGroup
				d.CollisionGroup = GHOST
			end
		end
	else
		for d, g in part.groups or {} do
			if d.Parent then
				d.CollisionGroup = g
			end
		end
		part.groups = nil
	end
	part.ghost = on
end

-- moving cars (server-side: anchor, PivotTo, then hand the car back to the driver) --------------------------------
local function placeChassis(plr: Player, chassis: BasePart, surface: CFrame, hold: boolean)
	local car = chassis.Parent :: Model
	local cf = surface + Vector3.new(0, CHASSIS_UP, 0)
	chassis.Anchored = true
	car:PivotTo(cf * chassis.CFrame:ToObjectSpace(car:GetPivot())) -- chassis lands exactly on cf
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	if not hold then
		task.delay(0.5, function()
			if chassis.Parent and chassis.Anchored then
				chassis.Anchored = false
				pcall(function() chassis:SetNetworkOwner(plr) end)
			end
		end)
	end
end

local function release(part)
	local chassis = part.chassis
	if chassis and chassis.Parent and chassis.Anchored then
		chassis.Anchored = false
		pcall(function() chassis:SetNetworkOwner(part.plr) end)
	end
end

local function moveCar(part, surface: CFrame, hold: boolean)
	placeChassis(part.plr, part.chassis, surface, hold)
	part.ignoreUntil = now() + 0.8
	part.tracker:moved(part.chassis.Position, now())
end

local function pitPoint(pit, s: number): CFrame
	s = math.clamp(s, 0, pit.len)
	for i = 1, #pit.pts - 1 do
		if pit.cum[i + 1] >= s then
			local segLen = pit.cum[i + 1] - pit.cum[i]
			local f = if segLen > 0 then (s - pit.cum[i]) / segLen else 0
			local a, b = pit.pts[i], pit.pts[i + 1]
			local p = a:Lerp(b, f)
			local d = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
			return CFrame.lookAt(p, p + (if d.Magnitude > 0.01 then d.Unit else Vector3.new(0, 0, -1)))
		end
	end
	return CFrame.new(pit.pts[#pit.pts])
end

-- sessions ----------------------------------------------------------------------------------------------------------
local function everyone(s)
	local list = {}
	for _, p in s.parts do
		if p.plr.Parent then table.insert(list, p.plr) end
	end
	for plr, sess in spectating do
		if sess == s and plr.Parent then table.insert(list, plr) end
	end
	return list
end

local function broadcast(s, kind: string, payload)
	for _, plr in everyone(s) do
		send(plr, kind, payload)
	end
end

local function setState(s, state: string)
	s.state = state
	s.stateAt = now()
	for _, p in s.parts do
		if not p.gone then p.plr:SetAttribute("CircuitState", state) end
	end
	fire("onState", s)
end

local function newSession(c, kind: string, mode: string, opts, owner: Player?)
	nextId += 1
	opts = opts or {}
	local allowed = nil
	if type(opts.classes) == "table" and #opts.classes > 0 then
		allowed = {}
		for _, cl in opts.classes do
			if table.find(Service.CLASSES, cl) then allowed[cl] = true end
		end
		if next(allowed) == nil then allowed = nil end
	end
	local laps = math.clamp(math.floor(tonumber(opts.laps) or 3), 1, MAX_LAPS)
	local collisions
	if mode == "PrivateRoom" then
		collisions = opts.collisions ~= false
	else
		collisions = mode == "CircuitRace" or mode == "TrackDay"
	end
	local s = {
		id = nextId, circuit = c, kind = kind, mode = mode, parts = {}, joinSeq = 0,
		laps = if kind == "formal" then laps else 0,
		gridBy = if opts.gridBy == "pb" then "pb" else "join",
		private = mode == "PrivateRoom", owner = owner, invited = {},
		allowed = allowed, collisions = collisions,
		timing = not (mode == "FreePractice" and opts.timing == false),
		formEnds = if mode == "CircuitRace" then now() + FORM_TIME else nil,
		lastActivity = now(), finishedCount = 0, towerAt = 0, standingsAt = 0,
		bestLap = nil, bestSectors = {},
	}
	s.state = if kind == "open" then "Racing" else "Forming"
	s.stateAt = now()
	slotOf(c.id)[kind] = s
	return s
end

local function refsFor(s)
	-- overall bests for purple: the best of the global board and this session
	local lap = Leaderboard.overallLap(s.circuit.id)
	if s.bestLap and (not lap or s.bestLap < lap) then
		lap = s.bestLap
	end
	local sectors = table.clone(Leaderboard.overallSectors(s.circuit.id))
	for k = 1, 3 do
		if s.bestSectors[k] and (not sectors[k] or s.bestSectors[k] < sectors[k]) then
			sectors[k] = s.bestSectors[k]
		end
	end
	return {lap = lap, sectors = sectors}
end

local function partAttrs(s, p)
	local c = s.circuit
	attrs(p.plr, {
		CircuitActive = true, CircuitId = c.id, CircuitName = c.name, CircuitMode = s.mode, CircuitState = s.state,
		CircuitLaps = s.laps, CircuitLap = 0, CircuitLapStart = nil, CircuitLastLap = nil, CircuitBestLap = nil,
		CircuitPB = p.pbLap, CircuitLapValid = true, CircuitPos = nil, CircuitCount = #s.parts, CircuitGap = "",
		CircuitPit = false, CircuitPitLimit = c.pit and c.pit.limit or nil, CircuitOff = false,
		CircuitWrongWay = false, CircuitPenalty = 0, CircuitFormEnds = s.formEnds, CircuitFinished = nil,
		CircuitOwner = if s.owner then s.owner.DisplayName else nil,
	})
end

local function addPart(s, plr: Player, chassis: BasePart)
	s.joinSeq += 1
	local pb = Leaderboard.getPB(plr, s.circuit.id)
	local p = {
		plr = plr, name = plr.DisplayName, chassis = chassis, car = chassis.Parent, joinSeq = s.joinSeq,
		class = classOf(chassis.Parent), pbLap = pb and pb.lap or nil,
		tracker = Validator.new(s.circuit),
		timer = Timing.new({pbLap = if pb then pb.lap else nil, pbSectors = if pb then pb.s else nil}),
		penalty = 0, limitStrikes = 0, keyTimes = {}, lastKey = 0, ignoreUntil = 0, session = s,
	}
	table.insert(s.parts, p)
	byPlayer[plr] = p
	s.lastActivity = now()
	partAttrs(s, p)
	for _, q in s.parts do
		q.plr:SetAttribute("CircuitCount", #s.parts)
	end
	return p
end

-- removes a driver from the session; in a running race they stay in the results as DNF
local function dropPart(p, reason: string?)
	local s = p.session
	if p.gone then
		return
	end
	p.gone = true
	byPlayer[p.plr] = nil
	if p.plr.Parent then
		if p.chassis and p.chassis.Parent then
			setGhost(p, false)
			release(p)
		end
		clearAttrs(p.plr)
		if reason then
			send(p.plr, "toast", reason)
		end
	end
	local racing = s.kind == "formal" and (s.state == "Racing" or s.state == "Finishing" or s.state == "StartLights")
	if racing and not p.finished then
		p.dnf = reason or "DNF"
	elseif not (s.kind == "formal" and s.state == "Results") then
		local i = table.find(s.parts, p)
		if i then table.remove(s.parts, i) end
	end
end

local function closeSession(s, reason: string?)
	for _, p in table.clone(s.parts) do
		dropPart(p, reason)
	end
	for plr, sess in spectating do
		if sess == s then
			spectating[plr] = nil
			plr.ReplicationFocus = nil
			if plr.Parent then send(plr, "spectate", nil) end
		end
	end
	local sl = slotOf(s.circuit.id)
	if sl[s.kind] == s then
		sl[s.kind] = nil
	end
	s.closed = true
	fire("onState", s)
end

-- open sessions start in the pit lane (pit mode on, limiter applies) or on the grid when there is no pit lane
local function placeOpen(s, p)
	local c = s.circuit
	local k = #s.parts - 1
	if c.pit then
		local pit = c.pit
		local sAt = math.max(pit.entryS + 5, pit.exitS - 40 - (k % 5) * 20)
		moveCar(p, pitPoint(pit, sAt), false)
		p.tracker.pit = true
		p.plr:SetAttribute("CircuitPit", true)
	else
		moveCar(p, c.grid[k % #c.grid + 1], false)
	end
end

-- requests ----------------------------------------------------------------------------------------------------------
local function carHere(plr: Player)
	local chassis = Route.carOf(plr)
	if not chassis then
		return nil, nil, "Get in a car first"
	end
	local c = Registry.at(chassis.Position, AT_CIRCUIT)
	return chassis, c, nil
end

local function allowedFor(s, p): boolean
	return s.allowed == nil or s.allowed[p.class or "Street"] == true
end

-- create a session (opts.mode) or join the one running; returns ok, message
function Service.join(plr: Player, opts)
	opts = type(opts) == "table" and opts or {}
	local mode = opts.mode
	if not (Service.OPEN_MODES[mode] or Service.FORMAL_MODES[mode]) then
		return false, "Unknown mode"
	end
	local chassis, c, why = carHere(plr)
	if not chassis then
		return false, why
	end
	if not c or (opts.circuit and opts.circuit ~= c.id) then
		return false, "Drive to the circuit paddock first"
	end
	local current = byPlayer[plr]
	if current then
		if current.session.kind == "open" and Service.FORMAL_MODES[mode] then
			dropPart(current, nil) -- leaving practice to join a race
		else
			return false, "You are already in a session (leave it first)"
		end
	end
	if Route.busy(plr) then
		return false, "Finish your race, sprint or job first"
	end
	if spectating[plr] then
		Service.unspectate(plr)
	end
	local class = classOf(chassis.Parent :: Model)
	local sl = slotOf(c.id)
	if Service.OPEN_MODES[mode] then
		local f = sl.formal
		if f and f.state ~= "Forming" then
			return false, "A race is running on this circuit - spectate or wait"
		end
		local s = sl.open
		if s and s.mode ~= mode then
			return false, ("The track is open for %s - join that or wait"):format(s.mode)
		end
		s = s or newSession(c, "open", mode, opts, nil)
		local p = addPart(s, plr, chassis)
		setGhost(p, not s.collisions)
		placeOpen(s, p)
		send(plr, "toast", ("%s - %s. Out lap: cross the line to start timing."):format(c.name, mode))
		return true
	end
	-- formal
	local s = sl.formal
	if s then
		if s.state ~= "Forming" then
			return false, "A race is already running here"
		end
		if s.private and not (s.owner == plr or s.invited[plr.UserId]) then
			return false, "That room is private (invite only)"
		end
		if #s.parts >= #c.grid then
			return false, "The grid is full"
		end
	else
		if opts.join then
			return false, "No race is forming"
		end
		s = newSession(c, "formal", mode, opts, if mode == "PrivateRoom" then plr else nil)
	end
	if s.allowed and not s.allowed[class] then
		local list = {}
		for cl in s.allowed do table.insert(list, cl) end
		if #s.parts == 0 then closeSession(s) end
		return false, ("Class %s not allowed here (%s)"):format(class, table.concat(list, ", "))
	end
	addPart(s, plr, chassis)
	if s.private then
		send(plr, "toast", if s.owner == plr then "Private room created: invite drivers, then press START"
			else "Joined the private room - waiting for the owner to start")
	else
		send(plr, "toast", ("Race forming: %d laps, starts in %d s"):format(s.laps, math.ceil(s.formEnds - now())))
	end
	return true
end

function Service.leave(plr: Player)
	local p = byPlayer[plr]
	if p then
		local s = p.session
		dropPart(p, "Left the session")
		if s.kind == "formal" and s.private and s.owner == plr and s.state == "Forming" then
			closeSession(s, "The room owner left - room closed")
		end
	end
	if spectating[plr] then
		Service.unspectate(plr)
	end
end

function Service.reset(plr: Player)
	local p = byPlayer[plr]
	if not p or p.finished then
		return
	end
	local s = p.session
	local t = now()
	if not (s.kind == "open" or s.state == "Racing" or s.state == "Finishing") then
		return
	end
	if t - (lastReset[plr] or 0) < RESET_COOLDOWN then
		return
	end
	local chassis = Route.carOf(plr)
	if chassis ~= p.chassis then
		return
	end
	lastReset[plr] = t
	moveCar(p, p.tracker:resetFrame(chassis.Position), false)
	if p.timer:invalidate("Reset") then
		p.plr:SetAttribute("CircuitLapValid", false)
	end
	send(plr, "warn", {kind = "reset", text = "Car reset to the last checkpoint - lap invalid"})
	fire("onIncident", s, p, "reset", nil)
end

function Service.start(plr: Player)
	local p = byPlayer[plr]
	local s = p and p.session
	if s and s.kind == "formal" and s.private and s.owner == plr and s.state == "Forming" then
		s.formEnds = now() -- the next Heartbeat moves everyone to the grid
	end
end

function Service.invite(plr: Player, userId)
	local p = byPlayer[plr]
	local s = p and p.session
	local target = typeof(userId) == "number" and Players:GetPlayerByUserId(userId)
	if not (s and s.private and s.owner == plr and target and target ~= plr) then
		return
	end
	s.invited[target.UserId] = true
	send(target, "invite", {from = plr.DisplayName, circuit = s.circuit.id, name = s.circuit.name, laps = s.laps})
	send(plr, "toast", "Invited " .. target.DisplayName)
end

function Service.spectate(plr: Player, circuitId, targetUserId)
	local sl = type(circuitId) == "string" and slots[circuitId]
	local s = sl and (if sl.formal and sl.formal.state ~= "Forming" then sl.formal else sl.open or sl.formal)
	if not s or byPlayer[plr] then
		return
	end
	if s.private and not (s.invited[plr.UserId] or s.owner == plr) then
		send(plr, "toast", "That room is private")
		return
	end
	spectating[plr] = s
	local targets = {}
	for _, p in s.parts do
		if not p.gone then table.insert(targets, p.plr.UserId) end
	end
	local focus = nil
	for _, p in s.parts do
		if not p.gone and (targetUserId == nil or p.plr.UserId == targetUserId) then
			focus = p
			break
		end
	end
	plr.ReplicationFocus = if focus and focus.chassis and focus.chassis.Parent then focus.chassis else nil
	send(plr, "spectate", {circuit = s.circuit.id, name = s.circuit.name, mode = s.mode, targets = targets,
		target = focus and focus.plr.UserId})
end

function Service.unspectate(plr: Player)
	spectating[plr] = nil
	plr.ReplicationFocus = nil
	send(plr, "spectate", nil)
end

function Service.travel(plr: Player, circuitId)
	local c = type(circuitId) == "string" and Registry.get(circuitId)
	local chassis = Route.carOf(plr)
	if not c then
		return false, "Unknown circuit"
	end
	if not chassis then
		return false, "Get in a car first"
	end
	if byPlayer[plr] or Route.busy(plr) then
		return false, "Finish what you are doing first"
	end
	-- the driver's client owns the car's physics: make sure the paddock ground is streamed in before the car lands
	pcall(function()
		plr:RequestStreamAroundAsync(c.entrance.Position, 5)
	end)
	if Route.carOf(plr) ~= chassis then
		return false, "Get in a car first"
	end
	placeChassis(plr, chassis, c.entrance, false)
	return true
end

-- what the session menu shows
function Service.menuInfo(plr: Player)
	local chassis = Route.carOf(plr)
	local root = plr.Character and plr.Character:FindFirstChild("HumanoidRootPart")
	local pos = (chassis and chassis.Position) or (root and root.Position)
	local c = pos and Registry.at(pos, AT_CIRCUIT)
	local info = {circuits = {}, inCar = chassis ~= nil, classes = Service.CLASSES}
	for _, x in Registry.all() do
		table.insert(info.circuits, {id = x.id, name = x.name, length = x.lengthStuds})
	end
	local p = byPlayer[plr]
	if p then
		local s = p.session
		info.session = {circuit = s.circuit.id, name = s.circuit.name, mode = s.mode, state = s.state, kind = s.kind,
			owner = s.owner == plr, private = s.private, laps = s.laps}
		c = s.circuit
		if s.private and s.owner == plr then
			info.invitable = {}
			for _, other in Players:GetPlayers() do
				if other ~= plr and not s.invited[other.UserId] then
					table.insert(info.invitable, {userId = other.UserId, name = other.DisplayName})
				end
			end
		end
	end
	info.spectating = spectating[plr] ~= nil
	if c then
		local sl = slotOf(c.id)
		info.at = {id = c.id, name = c.name, length = c.lengthStuds, laps = c.def.defaultLaps or 3}
		if sl.open then
			info.open = {mode = sl.open.mode, count = #sl.open.parts}
		end
		local f = sl.formal
		if f then
			local classes = nil
			if f.allowed then
				classes = {}
				for cl in f.allowed do table.insert(classes, cl) end
			end
			info.formal = {mode = f.mode, state = f.state, count = #f.parts, laps = f.laps, private = f.private,
				owner = f.owner and f.owner.DisplayName, collisions = f.collisions, classes = classes,
				formLeft = f.formEnds and math.max(0, math.ceil(f.formEnds - now())) or nil,
				canJoin = f.state == "Forming" and (not f.private or f.owner == plr or f.invited[plr.UserId] == true)}
		end
		local pb = Leaderboard.getPB(plr, c.id)
		info.pb = pb and pb.lap
		info.top = Leaderboard.top(c.id, 5)
	end
	return info
end

-- judging -----------------------------------------------------------------------------------------------------------
local function penalise(s, p, seconds: number, text: string)
	p.penalty += seconds
	p.plr:SetAttribute("CircuitPenalty", p.penalty)
	send(p.plr, "warn", {kind = "penalty", text = ("%s  +%d s"):format(text, seconds)})
	fire("onIncident", s, p, "penalty", {seconds = seconds, text = text})
end

local function invalidate(s, p, reason: string)
	if not s.timing then
		return
	end
	if p.timer:invalidate(reason) then
		p.plr:SetAttribute("CircuitLapValid", false)
		send(p.plr, "warn", {kind = "invalid", text = "Lap invalid: " .. reason})
	end
end

local function isRace(s): boolean
	return s.kind == "formal"
end

-- cutting costs CUT_PENALTY at most once per lap (one chicane cut gives a cut event per bump and missed gates)
local function cutPenalty(s, p, text: string)
	if isRace(s) and p.timer.lap > 0 and p.cutLap ~= p.timer.lap then
		p.cutLap = p.timer.lap
		penalise(s, p, CUT_PENALTY, text)
	end
end

local function payLap(s, p, r, sub)
	local L = s.circuit.lengthStuds
	local money, exp = 0, 0
	if s.mode == "TimeAttack" or s.mode == "TrackDay" then
		money, exp = L / 60, L / 80
	elseif s.mode == "FreePractice" then
		exp = L / 160
	end
	if sub.pb then money += 100 end
	if sub.record then money += 250 end
	if money + exp >= 1 then
		Progress.Award(p.plr, money, exp, ("%s lap %s%s"):format(s.circuit.name, fmt(r.time),
			if sub.record then " - track record!" elseif sub.pb then " - personal best" else ""))
	end
end

local function finishRace(s, p, t: number)
	s.finishedCount += 1
	p.finished = true
	p.crossOrder = s.finishedCount
	p.raceTime = t - s.outAt
	p.plr:SetAttribute("CircuitFinished", p.raceTime + p.penalty)
	send(p.plr, "toast", ("Finished  %s%s"):format(fmt(p.raceTime),
		if p.penalty > 0 then ("  (+%d s penalties)"):format(p.penalty) else ""))
	if not s.firstFinishAt then
		s.firstFinishAt = now()
		setState(s, "Finishing")
	end
end

local function onLap(s, p, r, t: number)
	send(p.plr, "lap", r)
	attrs(p.plr, {CircuitLastLap = r.time, CircuitBestLap = p.timer.sessionBest, CircuitLap = p.timer.lap,
		CircuitLapStart = p.timer.lapStart, CircuitLapValid = true})
	fire("onLap", s, p, r)
	if r.valid then
		if not s.bestLap or r.time < s.bestLap then
			s.bestLap = r.time
		end
		local sub = Leaderboard.submit(p.plr, s.circuit.id, r.time, r.sectors, p.car:GetAttribute("CarId"), p.class,
			s.mode == "TimeAttack")
		if sub.pb then
			p.pbLap = r.time
			p.plr:SetAttribute("CircuitPB", r.time)
		end
		if not isRace(s) then
			payLap(s, p, r, sub)
		end
	end
	if isRace(s) and p.timer.completed >= s.laps then
		finishRace(s, p, t)
	end
end

local function handle(s, p, ev, t: number)
	local kind = ev.kind
	if kind == "gate" then
		local gate = s.circuit.gates[ev.gate]
		if ev.missed then
			invalidate(s, p, "missed checkpoint")
			cutPenalty(s, p, "Track cut")
		end
		fire("onGate", s, p, ev.gate, ev.t)
		if not s.timing then
			return
		end
		local results = p.timer:onGate(gate, ev.t, refsFor(s), if isRace(s) then s.outAt else nil)
		if isRace(s) then
			local key = p.timer.lap * 1000 + ev.gate
			p.keyTimes[key] = ev.t
			p.lastKey = key
		end
		for _, r in results do
			if r.kind == "sector" then
				if r.colour ~= "invalid" and (not s.bestSectors[r.n] or r.time < s.bestSectors[r.n]) then
					s.bestSectors[r.n] = r.time -- overall best sector (purple) as soon as it is set
				end
				send(p.plr, "sector", r)
			elseif r.kind == "start" then
				attrs(p.plr, {CircuitLap = p.timer.lap, CircuitLapStart = p.timer.lapStart, CircuitLapValid = true})
			elseif r.kind == "lap" then
				onLap(s, p, r, ev.t)
				if p.finished then
					return
				end
			end
		end
	elseif kind == "teleport" then
		if isRace(s) and p.timer.lap > 0 then
			dropPart(p, "Disqualified: moved too fast (teleport)")
		else
			invalidate(s, p, "teleport")
		end
	elseif kind == "offTrack" then
		p.plr:SetAttribute("CircuitOff", ev.on)
	elseif kind == "trackLimit" then
		invalidate(s, p, "track limits")
		if isRace(s) and p.timer.lap > 0 then
			p.limitStrikes += 1
			if p.limitStrikes > LIMIT_FREE_WARNINGS then
				penalise(s, p, LIMIT_PENALTY, "Track limits")
			else
				send(p.plr, "warn", {kind = "limits", text = ("Track limits warning %d/%d"):format(p.limitStrikes,
					LIMIT_FREE_WARNINGS)})
			end
		end
		fire("onIncident", s, p, "trackLimit", nil)
	elseif kind == "cut" then
		invalidate(s, p, "corner cut")
		cutPenalty(s, p, "Corner cut")
		fire("onIncident", s, p, "cut", ev)
	elseif kind == "wrongWay" then
		p.plr:SetAttribute("CircuitWrongWay", ev.on)
		if ev.on then
			invalidate(s, p, "wrong way")
		end
	elseif kind == "pit" then
		p.plr:SetAttribute("CircuitPit", ev.on)
	elseif kind == "pitSpeed" then
		send(p.plr, "warn", {kind = "pit", text = ("PIT LIMITER  %d / %d"):format(math.floor(ev.speed),
			s.circuit.pit and s.circuit.pit.limit or 0)})
	elseif kind == "pitPenalty" then
		invalidate(s, p, "pit lane speeding")
		if isRace(s) and p.timer.lap > 0 then
			penalise(s, p, PIT_PENALTY, "Pit lane speeding")
		end
		fire("onIncident", s, p, "pitSpeeding", ev)
	end
end

local function samplePart(s, p, t: number)
	if t < p.ignoreUntil then
		p.tracker:moved(p.chassis.Position, t)
		return
	end
	for _, ev in p.tracker:sample(p.chassis.Position, t) do
		if p.gone or p.finished then
			break
		end
		handle(s, p, ev, t)
	end
end

-- the car this part joined with is still being driven by them
local function carOk(p): boolean
	return p.plr.Parent ~= nil and Route.carOf(p.plr) == p.chassis and p.chassis.Parent ~= nil
end

-- race order and gaps -------------------------------------------------------------------------------------------------
local function progressOf(s, p): number
	local c = s.circuit
	if p.finished then
		return 1e9 - p.crossOrder
	end
	local along = p.tracker.s
	if p.tracker.lastGate == 1 and along > c.len / 2 then
		along = 0
	elseif p.tracker.lastGate == #c.gates and along < c.len / 2 then
		along = c.len
	end
	if p.timer.lap == 0 then
		return if along > c.len / 2 then along - c.len else along
	end
	return p.timer.completed * c.len + along
end

local function standings(s)
	local order = {}
	for _, p in s.parts do
		table.insert(order, p)
	end
	local prog = {}
	for _, p in order do
		prog[p] = if p.dnf then -1e9 else progressOf(s, p)
	end
	table.sort(order, function(a, b)
		if prog[a] ~= prog[b] then
			return prog[a] > prog[b]
		end
		return a.joinSeq < b.joinSeq
	end)
	return order
end

local function updateStandings(s)
	local order = standings(s)
	local rows = {}
	for i, p in order do
		local gap = ""
		if i == 1 then
			gap = "LEADER"
		else
			local ahead = order[i - 1]
			local mine = p.keyTimes[p.lastKey]
			local theirs = ahead.keyTimes[p.lastKey]
			if p.dnf then
				gap = "DNF"
			elseif ahead.timer.lap > p.timer.lap + 1 then
				gap = "+1 LAP"
			elseif mine and theirs then
				gap = string.format("+%.3f", mine - theirs)
			end
		end
		if not p.gone then
			attrs(p.plr, {CircuitPos = i, CircuitCount = #order, CircuitGap = gap})
		end
		table.insert(rows, {pos = i, name = p.name, lap = math.min(p.timer.lap, s.laps), gap = gap,
			best = p.timer.sessionBest, status = if p.dnf then "DNF" elseif p.finished then "FIN"
				elseif p.tracker.pit then "PIT" else ""})
	end
	return rows
end

local function openTower(s)
	local order = table.clone(s.parts)
	table.sort(order, function(a, b)
		local x, y = a.timer.sessionBest or math.huge, b.timer.sessionBest or math.huge
		if x ~= y then return x < y end
		return a.joinSeq < b.joinSeq
	end)
	local rows = {}
	for i, p in order do
		table.insert(rows, {pos = i, name = p.name, lap = p.timer.completed, best = p.timer.sessionBest,
			last = p.timer.lastLap, status = if p.tracker.pit then "PIT" else ""})
		p.plr:SetAttribute("CircuitPos", i)
		p.plr:SetAttribute("CircuitCount", #order)
	end
	return rows
end

-- formal flow ---------------------------------------------------------------------------------------------------------
local function toGrid(s)
	local c = s.circuit
	for _, p in table.clone(s.parts) do
		if not carOk(p) then
			local chassis = Route.carOf(p.plr)
			if chassis and p.plr.Parent then -- switched cars while forming: take the new one
				p.chassis, p.car, p.class = chassis, chassis.Parent, classOf(chassis.Parent)
			else
				dropPart(p, "No car at the start - removed from the race")
			end
		end
		if not p.gone and not allowedFor(s, p) then
			dropPart(p, "Your car's class is not allowed in this race")
		end
	end
	if #s.parts == 0 then
		closeSession(s)
		return
	end
	-- the open session on this circuit makes way for the race
	local open = slotOf(c.id).open
	if open then
		for _, q in table.clone(open.parts) do
			local chassis = q.chassis
			dropPart(q, "Session closed: a race is starting. Moved to the paddock.")
			if chassis and chassis.Parent then
				placeChassis(q.plr, chassis, c.entrance, false)
			end
		end
		closeSession(open)
	end
	table.sort(s.parts, function(a, b)
		if s.gridBy == "pb" then
			local x, y = a.pbLap or math.huge, b.pbLap or math.huge
			if x ~= y then return x < y end
		end
		return a.joinSeq < b.joinSeq
	end)
	for i, p in s.parts do
		p.slot = c.grid[i]
		setGhost(p, not s.collisions)
		moveCar(p, p.slot, true)
		p.plr:SetAttribute("CircuitLaps", s.laps)
		send(p.plr, "toast", ("Grid slot %d of %d"):format(i, #s.parts))
	end
	setState(s, "Grid")
end

local function startLights(s)
	local t = now()
	for _, p in s.parts do
		if not p.gone then
			release(p)
			p.jumped = false
			p.jumpRef = nil
		end
	end
	s.lightsAt = t
	s.outAt = t + 4 * LIGHT_INTERVAL + HOLD_MIN + math.random() * (HOLD_MAX - HOLD_MIN)
	setState(s, "StartLights")
	broadcast(s, "lights", {at = t, interval = LIGHT_INTERVAL, count = 5})
end

local function goRacing(s)
	local c = s.circuit
	local t = now()
	for _, p in s.parts do
		if p.gone then
			continue
		end
		local pos = p.chassis.Position
		p.tracker:moved(pos, t)
		local near = Registry.nearest(c, pos)
		if near.s > c.len - 300 then
			-- grid behind the line: the first crossing starts lap 1, timed from lights out
		else
			p.tracker:armAt(near.s)
			p.timer:startLap(s.outAt)
			p.timer.sector = if near.s < c.sectorS[1] then 1 elseif near.s < c.sectorS[2] then 2 else 3
			attrs(p.plr, {CircuitLap = 1, CircuitLapStart = s.outAt})
		end
		p.plr:SetAttribute("CircuitLapStart", s.outAt)
	end
	setState(s, "Racing")
	broadcast(s, "lightsOut", {at = s.outAt})
end

local function showResults(s)
	local L = s.circuit.lengthStuds
	local finishers, others = {}, {}
	for _, p in s.parts do
		if p.finished then
			table.insert(finishers, p)
		else
			table.insert(others, p)
		end
	end
	table.sort(finishers, function(a, b)
		local x, y = a.raceTime + a.penalty, b.raceTime + b.penalty
		if x ~= y then return x < y end
		return a.crossOrder < b.crossOrder
	end)
	local prog = {}
	for _, p in others do
		prog[p] = if p.dnf and p.timer.lap == 0 then -1e9 else progressOf(s, p)
	end
	table.sort(others, function(a, b) return prog[a] > prog[b] end)
	local rows = {}
	local n = #s.parts
	for i, p in finishers do
		table.insert(rows, {pos = i, name = p.name, userId = p.plr.UserId, time = p.raceTime + p.penalty,
			penalty = p.penalty, best = p.timer.sessionBest, laps = p.timer.completed, status = "FIN", class = p.class})
	end
	for _, p in others do
		table.insert(rows, {pos = #rows + 1, name = p.name, userId = p.plr.UserId, time = nil, penalty = p.penalty,
			best = p.timer.sessionBest, laps = p.timer.completed, status = "DNF", reason = p.dnf, class = p.class})
	end
	-- rewards
	for i, p in finishers do
		if p.plr.Parent then
			local laps = s.laps
			local money, exp
			if i == 1 then
				money, exp = L * laps / 20 + 80 * (n - 1), L * laps / 40
			else
				money, exp = L * laps / 40, L * laps / 60
			end
			if s.private then
				money = 0
			end
			Progress.Award(p.plr, money, exp, ("%s race P%d/%d"):format(s.circuit.name, i, n))
			rows[i].money, rows[i].exp = math.floor(money), math.floor(exp)
		end
	end
	if Service.Ranked.enabled and Service.Ranked.validate(s, rows) then
		Service.Ranked.apply(s, rows)
	end
	fire("onResults", s, rows)
	setState(s, "Results")
	broadcast(s, "results", {name = s.circuit.name, mode = s.mode, laps = s.laps, rows = rows,
		bestLap = s.bestLap})
end

local function stepFormal(s, t: number)
	-- drop drivers who left the game
	for _, p in table.clone(s.parts) do
		if not p.plr.Parent and not p.gone then
			dropPart(p, nil)
		end
	end
	local state = s.state
	if state == "Forming" then
		if #s.parts == 0 then
			closeSession(s)
		elseif s.private and t - s.lastActivity > PRIVATE_IDLE then
			closeSession(s, "Private room closed (idle)")
		elseif s.formEnds and t >= s.formEnds then
			toGrid(s)
		end
		return
	end
	if state == "Grid" then
		for _, p in table.clone(s.parts) do
			if not p.gone and not carOk(p) then dropPart(p, "Left the car") end
		end
		if t - s.stateAt >= GRID_TIME then
			startLights(s)
		end
		return
	end
	if state == "StartLights" then
		for _, p in s.parts do
			if p.gone then
				continue
			end
			if not carOk(p) then
				dropPart(p, "Left the car")
			elseif t - s.lightsAt < JUMP_SETTLE then
				-- the car was just released to its driver's client: let the ownership handoff and suspension settle
			elseif not p.jumpRef then
				p.jumpRef = p.chassis.Position
			elseif not p.jumped then
				local d = p.chassis.Position - p.jumpRef
				if Vector3.new(d.X, 0, d.Z).Magnitude > JUMP_DIST then
					p.jumped = true
					penalise(s, p, JUMP_PENALTY, "JUMP START")
				end
			end
		end
		if t >= s.outAt then
			goRacing(s)
		end
		return
	end
	if state == "Racing" or state == "Finishing" then
		local running = 0
		for _, p in s.parts do
			if p.gone or p.finished or p.dnf then
				continue
			end
			if not carOk(p) then
				dropPart(p, "Left the car - DNF")
				continue
			end
			samplePart(s, p, t)
			if not (p.gone or p.finished) then
				running += 1
			end
		end
		if t - s.standingsAt > 0.5 then
			s.standingsAt = t
			local rows = updateStandings(s)
			if t - s.towerAt > 1 then
				s.towerAt = t
				broadcast(s, "tower", {mode = s.mode, laps = s.laps, rows = rows})
			end
		end
		local limit = s.outAt + s.laps * s.circuit.len / 30 + 120
		if running == 0 then
			showResults(s)
		elseif s.firstFinishAt and t - s.firstFinishAt > DNF_AFTER_WINNER then
			for _, p in s.parts do
				if not (p.finished or p.dnf) then p.dnf = "DNF (60 s after the winner)" end
			end
			showResults(s)
		elseif t > limit then
			for _, p in s.parts do
				if not (p.finished or p.dnf) then p.dnf = "DNF (time limit)" end
			end
			showResults(s)
		end
		return
	end
	if state == "Results" and t - s.stateAt >= RESULTS_TIME then
		closeSession(s, nil)
	end
end

local function stepOpen(s, t: number)
	for _, p in table.clone(s.parts) do
		if p.gone then
			continue
		end
		if not carOk(p) then
			dropPart(p, if p.plr.Parent then "Left the car - session ended" else nil)
			continue
		end
		samplePart(s, p, t)
	end
	if #s.parts == 0 then
		closeSession(s)
		return
	end
	if t - s.towerAt > 1 then
		s.towerAt = t
		broadcast(s, "tower", {mode = s.mode, rows = openTower(s)})
	end
end

-- startup -------------------------------------------------------------------------------------------------------------
local started = false
function Service.init(sendFn)
	if started then
		return
	end
	started = true
	send = sendFn
	Leaderboard.init(Progress)
	RunService.Heartbeat:Connect(function()
		local t = now()
		for _, sl in slots do
			for _, kind in {"formal", "open"} do
				local s = sl[kind]
				if s and not s.closed then
					local ok, err = pcall(if kind == "formal" then stepFormal else stepOpen, s, t)
					if not ok then
						warn("[Circuit] session error: " .. tostring(err))
					end
				end
			end
		end
	end)
	Players.PlayerRemoving:Connect(function(plr)
		local p = byPlayer[plr]
		if p then
			dropPart(p, nil)
		end
		spectating[plr] = nil
		lastReset[plr] = nil
	end)
end

function Service.partOf(plr: Player)
	return byPlayer[plr]
end

function Service.sessions(circuitId: string)
	return slotOf(circuitId)
end

return Service
