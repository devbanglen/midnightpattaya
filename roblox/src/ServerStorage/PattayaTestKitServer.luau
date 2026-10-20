-- PattayaTestKitServer (DEV ONLY, server side): the server half of ReplicatedStorage.PattayaTestKit.
-- No gameplay script requires this module. It works only in Studio (RunService:IsStudio()) or when the place sets
-- workspace attribute DevTest = true; on a live DevTest server only game.CreatorId and the user ids listed in the
-- workspace attribute DevTestUsers ("123,456") may call it from a client.
-- Start once per Play session from the server (Studio command bar on "Server", or the execute tool):
--   local S = require(game.ServerStorage.PattayaTestKitServer).start()     -- also stored as _G.TKS
-- Functions (also callable from a client through TK.server(action, ...), the player is then the caller):
--   S.player(nameOrNil) -> Player                     first player when no name
--   S.seat(plr, carName?, at?) -> ok, msg             seat in workspace[carName] ("personal" = the garage car,
--                                                     nil = nearest free race car), then optionally S.teleport
--   S.spawnCar(plr, carId, opts?) -> ok, msg         build a test car of any ServerStorage.CarBodies id (also ids
--                                                     not in CarSpecs / the garage, e.g. "red_sports") 14 studs in
--                                                     front of the player through ServerStorage.BuildCar, named
--                                                     TestCar_<id>_<userId> (replaces the previous one), and seat
--                                                     the player (opts.seat = false: just build; opts.color)
--   S.teleport(plr, target, opts?) -> ok, msg         move the player's car to a Vector3/CFrame in hops of
--                                                     opts.hop (300, never under 61) studs, anchored, so loop and
--                                                     circuit gates ignore every hop (they skip jumps > 60); ground
--                                                     found by raycast (opts.ground = false keeps target Y);
--                                                     refused while a race/sprint/job/session runs (opts.force)
--   S.publishPath(name, pts, closed?) -> count        workspace attribute "TK_<name>" = "x,y,z;..." (chunked as
--                                                     TK_<name>_1.. with a number in TK_<name> when long)
--   S.publishCircuit(id) -> msg                       TK_Circuit_<id> (closed centreline from CircuitRegistry),
--                                                     TK_Pit_<id> (pit lane), TK_Entrance_<id> (Vector3)
--   S.publishRouteTo(plr, target, isOsm?) -> msg      GPS route from the car: target "bira" | "central" | OSM id |
--                                                     graph index -> TK_Route
--   S.setProgress(plr, {Money, Level, EXP, Title, RoadFight}) -> msg
--   S.setAttribute(plr, name, value)                  any player attribute (EventJoined, RoadFight, ...)
--   S.probePath(pathOrAttr, opts?) -> summary, data   server raycasts every opts.every (25) studs along a path
--                                                     (the server has every part, streaming does not matter)
--   S.startEvent(kind, lead)  S.setTime(clock|nil)    Night Run / Survival start, Lighting TimeLock
--   S.report(plr?) -> string
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")
local Lighting = game:GetService("Lighting")

local function enabled(): boolean
	return RunService:IsStudio() or workspace:GetAttribute("DevTest") == true
end

if not enabled() then
	return setmetatable({enabled = false}, {
		__index = function()
			error("PattayaTestKitServer is disabled (needs Studio or workspace attribute DevTest = true)", 2)
		end,
	})
end

local S = {enabled = true}

local CHASSIS_UP = 2.8 -- chassis centre above the road surface (as RaceSessionService places cars)
local CHUNK = 50000 -- characters per path attribute
local ROAD_NAMES = {Road = true, Junction = true, Dash = true, Centre = true, Asphalt = true, PitLane = true,
	TransitionRoad = true, ServiceRoad = true, Parking = true, EdgeLine = true, PitLine = true}
local DESTINATIONS = {bira = 1457068485, central = 423748313} -- PattayaGPSServer's OSM junction ids

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

function S.player(who): Player?
	if typeof(who) == "Instance" and who:IsA("Player") then
		return who
	end
	if type(who) == "string" then
		return Players:FindFirstChild(who) :: Player?
	end
	return Players:GetPlayers()[1]
end

local function carOf(plr: Player): (BasePart?, Model?)
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent and seat.Parent:GetAttribute("RaceCar") then
		local m = seat.Parent :: Model
		return m.PrimaryPart, m
	end
	return nil, nil
end
S.carOf = carOf

local function busyReason(plr: Player): string?
	if plr:GetAttribute("RaceState") == "racing" then return "loop race running" end
	for _, a in {"SprintActive", "JobActive", "CircuitActive"} do
		if plr:GetAttribute(a) == true then return a end
	end
	return nil
end

local function groundAt(pos: Vector3, exclude: {Instance}): RaycastResult?
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = exclude
	return workspace:Raycast(Vector3.new(pos.X, pos.Y + 60, pos.Z), Vector3.new(0, -200, 0), params)
end

local function characters(): {Instance}
	local list = {}
	for _, p in Players:GetPlayers() do
		if p.Character then table.insert(list, p.Character) end
	end
	return list
end

-- seat -------------------------------------------------------------------------------------------------------------
function S.seat(plr: Player, carName: string?, at)
	plr = S.player(plr) :: Player
	local hum = plr and plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	if not hum then
		return false, "no character"
	end
	local car: Model? = nil
	if carName == "personal" then
		car = workspace:FindFirstChild("PersonalCar_" .. plr.UserId) :: Model?
	elseif type(carName) == "string" then
		car = workspace:FindFirstChild(carName) :: Model?
	else
		local root = plr.Character:GetPivot().Position
		local best = math.huge
		for _, m in workspace:GetChildren() do
			local seat = m:FindFirstChild("DriveSeat")
			local owner = m:GetAttribute("Owner")
			if m:IsA("Model") and m:GetAttribute("RaceCar") and m.PrimaryPart and seat and not (seat :: VehicleSeat).Occupant
				and (owner == nil or owner == plr.UserId) then
				local d = (m.PrimaryPart.Position - root).Magnitude
				if d < best then car, best = m, d end
			end
		end
	end
	if not (car and car:GetAttribute("RaceCar")) then
		return false, "no such race car: " .. tostring(carName)
	end
	local seat = car:FindFirstChild("DriveSeat") :: VehicleSeat?
	if not seat then
		return false, "car has no DriveSeat"
	end
	if seat.Occupant and seat.Occupant ~= hum then
		return false, "seat taken"
	end
	if hum.SeatPart ~= seat then
		if hum.SeatPart then
			local sw = hum.SeatPart:FindFirstChild("SeatWeld")
			if sw then sw:Destroy() end
			hum.Sit = false
			task.wait(0.3)
		end
		seat:Sit(hum)
		local untilT = os.clock() + 3
		while hum.SeatPart ~= seat and os.clock() < untilT do
			task.wait(0.1)
		end
		if hum.SeatPart ~= seat then
			return false, "could not sit (seat:Sit did not take)"
		end
	end
	if at ~= nil then
		task.wait(0.3) -- let the network ownership handoff happen first
		local ok, msg = S.teleport(plr, at)
		return ok, ("seated in %s; %s"):format(car.Name, msg)
	end
	return true, "seated in " .. car.Name
end

-- spawnCar (dev test of a car body that is not in the garage) ---------------------------------------------------------
function S.spawnCar(plr: Player, carId: string, opts)
	plr = S.player(plr) :: Player
	opts = type(opts) == "table" and opts or {}
	if type(carId) ~= "string" then
		return false, "carId must be a string"
	end
	local root = plr and plr.Character and plr.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return false, "no character"
	end
	local factory = ServerStorage:FindFirstChild("BuildCar") :: BindableFunction?
	if not factory then
		return false, "ServerStorage.BuildCar missing (RaceCarServer not running)"
	end
	local name = ("TestCar_%s_%d"):format(carId, plr.UserId)
	local old = workspace:FindFirstChild(name)
	if old then
		local hum = plr.Character:FindFirstChildOfClass("Humanoid")
		if hum and hum.SeatPart and hum.SeatPart:IsDescendantOf(old) then
			hum.Sit = false
			task.wait(0.2)
		end
		old:Destroy()
	end
	local look = flat(root.CFrame.LookVector)
	look = if look.Magnitude > 0.1 then look.Unit else Vector3.new(0, 0, -1)
	local p = root.Position + look * 14
	local hit = groundAt(p, characters())
	if hit then
		p = Vector3.new(p.X, hit.Position.Y + CHASSIS_UP, p.Z)
	end
	local color = if typeof(opts.color) == "Color3" then opts.color else Color3.fromRGB(200, 20, 25)
	local ok, car = pcall(function()
		return factory:Invoke(CFrame.lookAt(p, p + look), color, carId, {name = name})
	end)
	if not (ok and car) then
		return false, "BuildCar failed: " .. tostring(car)
	end
	local hasBody = car:FindFirstChild("Body") ~= nil and car.PrimaryPart and car.PrimaryPart.Transparency == 1
	local wheelMeshes = 0
	for _, d in car:GetDescendants() do
		if d.Name == "WheelMesh" then wheelMeshes += 1 end
	end
	local info = ("%s built (body mesh %s, wheel meshes %d)"):format(name, hasBody and "yes" or "NO", wheelMeshes)
	if opts.seat == false then
		return true, info
	end
	local sok, msg = S.seat(plr, name)
	return sok, info .. "; " .. tostring(msg)
end

-- teleport in hops -----------------------------------------------------------------------------------------------
function S.teleport(plr: Player, target, opts)
	plr = S.player(plr) :: Player
	opts = type(opts) == "table" and opts or {}
	local chassis, car = carOf(plr)
	if not (chassis and car) then
		return false, "not in a car"
	end
	local busy = busyReason(plr)
	if busy and not opts.force then
		return false, "refused while " .. busy .. " (opts.force = true to do it anyway)"
	end
	local start = chassis.Position
	local goal: Vector3
	local look: Vector3
	if typeof(target) == "CFrame" then
		goal, look = target.Position, target.LookVector
	elseif typeof(target) == "Vector3" then
		goal = target
		look = if typeof(opts.look) == "Vector3" then opts.look else flat(goal - start)
	else
		return false, "target must be a Vector3 or CFrame"
	end
	look = flat(look)
	look = if look.Magnitude > 0.1 then look.Unit else flat(chassis.CFrame.LookVector).Unit
	if opts.ground ~= false then
		local exclude = characters()
		table.insert(exclude, car)
		local hit = groundAt(goal, exclude)
		if hit then
			goal = Vector3.new(goal.X, hit.Position.Y + CHASSIS_UP, goal.Z)
		end
	end
	local hop = math.max(61, tonumber(opts.hop) or 300)
	local dist = flat(goal - start).Magnitude
	local hops = math.max(1, math.ceil(dist / hop))
	local short = dist < 61
	local offset = chassis.CFrame:ToObjectSpace(car:GetPivot())
	chassis.Anchored = true
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	for k = 1, hops do
		local p = start:Lerp(goal, k / hops)
		if k < hops then
			p = Vector3.new(p.X, math.max(start.Y, goal.Y) + 20, p.Z) -- in transit, clear of kerbs and props
		end
		car:PivotTo(CFrame.lookAt(p, p + look) * offset)
		task.wait(tonumber(opts.hopWait) or 0.1) -- every server Heartbeat sample sees one hop (> 60 studs)
	end
	pcall(function()
		plr:RequestStreamAroundAsync(goal, 5)
	end)
	task.wait(0.3)
	if chassis.Parent then
		chassis.AssemblyLinearVelocity = Vector3.zero
		chassis.Anchored = false
		pcall(function() chassis:SetNetworkOwner(plr) end)
	end
	return true, ("moved %.0f studs in %d hop(s)%s"):format(dist, hops,
		if short and dist > 1 then " (WARNING: a move under 61 studs can still count as a gate crossing)" else "")
end

-- paths --------------------------------------------------------------------------------------------------------------
local function pack(pts): string
	local items = table.create(#pts)
	for _, p in pts do
		table.insert(items, ("%.1f,%.1f,%.1f"):format(p.X, p.Y, p.Z))
	end
	return table.concat(items, ";")
end

function S.publishPath(name: string, pts, closed: boolean?): number
	assert(type(name) == "string" and type(pts) == "table", "publishPath(name, {Vector3})")
	local attr = if string.sub(name, 1, 3) == "TK_" then name else "TK_" .. name
	-- clear old chunks
	local old = workspace:GetAttribute(attr)
	if type(old) == "number" then
		for i = 1, old do workspace:SetAttribute(attr .. "_" .. i, nil) end
	end
	local packed = pack(pts)
	if #packed <= CHUNK then
		workspace:SetAttribute(attr, packed)
	else
		local chunks = {}
		local cur = {}
		local len = 0
		for item in string.gmatch(packed, "[^;]+") do
			if len + #item + 1 > CHUNK and #cur > 0 then
				table.insert(chunks, table.concat(cur, ";"))
				cur, len = {}, 0
			end
			table.insert(cur, item)
			len += #item + 1
		end
		if #cur > 0 then table.insert(chunks, table.concat(cur, ";")) end
		for i, c in chunks do workspace:SetAttribute(attr .. "_" .. i, c) end
		workspace:SetAttribute(attr, #chunks)
	end
	workspace:SetAttribute(attr .. "_closed", closed == true)
	return #pts
end

function S.publishCircuit(id: string): string
	local mod = ServerStorage:FindFirstChild("CircuitRegistry")
	assert(mod, "no ServerStorage.CircuitRegistry")
	local Registry = require(mod) :: any
	local c = Registry.get(id)
	if not c then
		-- 2026-10-19: the Studio command/execute context got its own copy of the module (empty registry) even though
		-- CircuitServer had loaded the circuits, so load them into this copy too (compile only; no world changes)
		local defs = ServerStorage:FindFirstChild("PattayaData")
		defs = defs and defs:FindFirstChild("circuits")
		if defs then
			Registry.load(defs)
			c = Registry.get(id)
		end
	end
	assert(c, "circuit not loaded: " .. tostring(id) .. " (is CircuitServer running?)")
	local n = S.publishPath("Circuit_" .. id, c.pts, true)
	local msg = ("TK_Circuit_%s: %d points, %.0f studs"):format(id, n, c.len)
	if c.pit then
		local m = S.publishPath("Pit_" .. id, c.pit.pts, false)
		msg ..= ("; TK_Pit_%s: %d points, limit %d"):format(id, m, c.pit.limit)
	end
	workspace:SetAttribute("TK_Entrance_" .. id, c.entrance.Position)
	return msg
end

function S.publishRouteTo(plr: Player, target, isOsm: boolean?): string
	plr = S.player(plr) :: Player
	local mod = ServerStorage:FindFirstChild("PattayaRoute")
	assert(mod, "no ServerStorage.PattayaRoute")
	local Route = require(mod) :: any
	local chassis = carOf(plr)
	local pos = if chassis then chassis.Position else (plr.Character and plr.Character:GetPivot().Position)
	assert(pos, "no car or character")
	if type(target) == "string" then
		target, isOsm = DESTINATIONS[target], true
		assert(target, "unknown destination (bira / central / OSM id / graph index)")
	end
	local r, why = Route.routeTo(pos, chassis and chassis.CFrame.LookVector, target, isOsm, 700) -- same snap as PattayaGPSServer
	assert(r, "no route: " .. tostring(why))
	local n = S.publishPath("Route", r.route, false)
	return ("TK_Route: %d points, %.0f studs"):format(n, r.length)
end

-- progress -----------------------------------------------------------------------------------------------------------
function S.setProgress(plr: Player, t): string
	plr = S.player(plr) :: Player
	assert(type(t) == "table", "setProgress(plr, {Money = n, Level = n, EXP = n, Title = s, RoadFight = bits})")
	local ls = plr:FindFirstChild("leaderstats")
	assert(ls, "no leaderstats (PattayaProgress not started)")
	local out = {}
	if t.Title ~= nil then
		-- the leaderstat only shows the best title of the saved set: reset the set through PattayaProgress
		local mod = ServerStorage:FindFirstChild("PattayaProgress")
		local okP, P = pcall(function() return if mod then require(mod) :: any else nil end)
		if okP and P and P.SetTitle then
			P.SetTitle(plr, tostring(t.Title))
		end
	end
	for _, k in {"Money", "Level", "EXP", "Title"} do
		local v = t[k]
		local inst = ls:FindFirstChild(k)
		if v ~= nil and inst then
			(inst :: any).Value = v
			table.insert(out, k .. "=" .. tostring(v))
		end
	end
	if t.RoadFight ~= nil then
		plr:SetAttribute("RoadFight", tonumber(t.RoadFight) or 0)
		table.insert(out, "RoadFight=" .. tostring(t.RoadFight))
	end
	return table.concat(out, " ")
end

function S.setAttribute(plr: Player, name: string, value)
	plr = S.player(plr) :: Player
	assert(type(name) == "string", "setAttribute(plr, name, value)")
	plr:SetAttribute(name, value)
	return name .. "=" .. tostring(value)
end

-- probes -----------------------------------------------------------------------------------------------------------
local function readPacked(s: string)
	local pts = {}
	for item in string.gmatch(s, "[^;]+") do
		local nums = {}
		for x in string.gmatch(item, "[^,]+") do table.insert(nums, tonumber(x)) end
		if #nums == 2 then
			table.insert(pts, Vector3.new(nums[1], 1, nums[2]))
		elseif #nums >= 3 then
			table.insert(pts, Vector3.new(nums[1], nums[2], nums[3]))
		end
	end
	return pts
end

local function pathOf(src)
	if type(src) == "table" then
		return src
	end
	if src == "RacePath" then
		local race = workspace:FindFirstChild("PattayaWorld") and workspace.PattayaWorld:FindFirstChild("Race")
		return readPacked(race and race:GetAttribute("Path") or "")
	end
	local attr = if string.sub(src, 1, 3) == "TK_" then src else "TK_" .. src
	local v = workspace:GetAttribute(attr)
	if type(v) == "number" then
		local parts = {}
		for i = 1, v do table.insert(parts, workspace:GetAttribute(attr .. "_" .. i) or "") end
		v = table.concat(parts, ";")
	end
	return readPacked(v or "")
end

-- opts.every (25 studs), opts.onRoad(hit) -> bool, opts.lateral (studs to the right, e.g. probe the edges)
function S.probePath(src, opts)
	opts = type(opts) == "table" and opts or {}
	local pts = pathOf(src)
	assert(#pts >= 2, "probePath: no path")
	local every = tonumber(opts.every) or 25
	local exclude = characters()
	local traffic = workspace:FindFirstChild("PattayaTraffic")
	if traffic then table.insert(exclude, traffic) end
	local byName, gaps = {}, {}
	local n, road, carry = 0, 0, 0
	local maxErr = 0
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = flat(b - a).Magnitude
		local s = carry
		while s <= len do
			local p = if len > 1e-3 then a:Lerp(b, s / len) else a
			local dir = flat(b - a)
			if opts.lateral and dir.Magnitude > 0.01 then
				dir = dir.Unit
				p += Vector3.new(-dir.Z, 0, dir.X) * opts.lateral
			end
			local hit = groundAt(p, exclude)
			n += 1
			local ok = if opts.onRoad then opts.onRoad(hit) == true
				else (hit ~= nil and (ROAD_NAMES[hit.Instance.Name] == true or string.sub(hit.Instance.Name, 1, 4) == "Curb"))
			local name = if hit then hit.Instance.Name else "(none)"
			byName[name] = (byName[name] or 0) + 1
			if ok then
				road += 1
				if hit and p.Y ~= 1 then maxErr = math.max(maxErr, math.abs(hit.Position.Y - p.Y)) end
			elseif #gaps < 10 then
				table.insert(gaps, ("(%.0f,%.0f) %s"):format(p.X, p.Z, name))
			end
			s += every
		end
		carry = s - len
	end
	local names = {}
	for k, c in byName do table.insert(names, k .. " " .. c) end
	table.sort(names)
	local summary = ("%d probes, %d road (%.1f%%), max |dy| %.2f [%s]%s"):format(n, road, 100 * road / math.max(n, 1),
		maxErr, table.concat(names, ", "), if #gaps > 0 then " first misses: " .. table.concat(gaps, "; ") else "")
	return summary, {n = n, road = road, byName = byName, gaps = gaps}
end

-- events / time ------------------------------------------------------------------------------------------------------
function S.startEvent(kind: string?, lead: number?): string
	local ev = ServerStorage:FindFirstChild("StartEvent") :: BindableEvent?
	assert(ev, "no ServerStorage.StartEvent (PattayaEventsServer not running)")
	ev:Fire(kind or "nightrun", lead or 15)
	return ("StartEvent %s in %d s"):format(kind or "nightrun", lead or 15)
end

function S.setTime(clock: number?): string
	Lighting:SetAttribute("TimeLock", clock)
	return "TimeLock=" .. tostring(clock)
end

-- report -------------------------------------------------------------------------------------------------------------
local ATTRS = {"RaceState", "SprintActive", "JobActive", "CircuitActive", "CircuitMode", "CircuitState",
	"EventJoined", "EventActive", "Equalised", "SpeedCap", "RoadFight", "ProgressLoaded"}

function S.report(who): string
	local lines = {}
	local list = if who then {S.player(who)} else Players:GetPlayers()
	for _, plr in list do
		if plr then
			local chassis, car = carOf(plr)
			local parts = {plr.Name}
			if chassis and car then
				local p = chassis.Position
				local ok, owner = pcall(function() return chassis:GetNetworkOwner() end)
				table.insert(parts, ("car %s (%.0f,%.1f,%.0f) owner=%s%s"):format(car.Name, p.X, p.Y, p.Z,
					if ok and owner then owner.Name else "server", if chassis.Anchored then " ANCHORED" else ""))
			else
				table.insert(parts, "on foot")
			end
			local ls = plr:FindFirstChild("leaderstats")
			if ls then
				for _, k in {"Level", "Money", "EXP", "Title"} do
					local x = ls:FindFirstChild(k)
					if x then table.insert(parts, k .. "=" .. tostring((x :: any).Value)) end
				end
			end
			for _, k in ATTRS do
				local x = plr:GetAttribute(k)
				if x ~= nil and x ~= false then table.insert(parts, k .. "=" .. tostring(x)) end
			end
			table.insert(lines, table.concat(parts, " "))
		end
	end
	local ev = ReplicatedStorage:FindFirstChild("PattayaEvent")
	if ev then
		table.insert(lines, ("event phase=%s kind=%s entrants=%s round=%s/%s"):format(tostring(ev:GetAttribute("Phase")),
			tostring(ev:GetAttribute("Kind")), tostring(ev:GetAttribute("Entrants")), tostring(ev:GetAttribute("Round")),
			tostring(ev:GetAttribute("Rounds"))))
	end
	return table.concat(lines, "\n")
end

-- client access ----------------------------------------------------------------------------------------------------
local function allowed(plr: Player): boolean
	if RunService:IsStudio() then
		return true
	end
	if game.CreatorType == Enum.CreatorType.User and plr.UserId == game.CreatorId then
		return true
	end
	local list = workspace:GetAttribute("DevTestUsers")
	if type(list) == "string" then
		for id in string.gmatch(list, "%d+") do
			if tonumber(id) == plr.UserId then return true end
		end
	end
	return false
end

local ACTIONS = {
	seat = function(plr, carName, at) return S.seat(plr, carName, at) end,
	spawnCar = function(plr, carId, opts) return S.spawnCar(plr, carId, opts) end,
	teleport = function(plr, target, opts) return S.teleport(plr, target, opts) end,
	publishPath = function(_, name, pts, closed) return S.publishPath(name, pts, closed) end,
	publishCircuit = function(_, id) return S.publishCircuit(id) end,
	publishRouteTo = function(plr, target, isOsm) return S.publishRouteTo(plr, target, isOsm) end,
	setProgress = function(plr, t) return S.setProgress(plr, t) end,
	setAttribute = function(plr, name, value) return S.setAttribute(plr, name, value) end,
	probePath = function(_, src, opts) return S.probePath(src, opts) end,
	startEvent = function(_, kind, lead) return S.startEvent(kind, lead) end,
	setTime = function(_, clock) return S.setTime(clock) end,
	report = function(_, who) return S.report(who) end,
}

local started = false
function S.start()
	if started then
		return S
	end
	started = true
	_G.TKS = S
	local rf = ReplicatedStorage:FindFirstChild("PattayaTestKitRemote") or Instance.new("RemoteFunction")
	rf.Name = "PattayaTestKitRemote"
	rf.Parent = ReplicatedStorage
	;(rf :: RemoteFunction).OnServerInvoke = function(plr: Player, action, ...)
		if not allowed(plr) then
			return false, "not allowed"
		end
		local f = type(action) == "string" and ACTIONS[action]
		if not f then
			return false, "unknown action " .. tostring(action)
		end
		local res = table.pack(pcall(f, plr, ...))
		if not res[1] then
			return false, tostring(res[2])
		end
		return table.unpack(res, 2, res.n)
	end
	print("[TestKit] server kit started")
	return S
end

return S
