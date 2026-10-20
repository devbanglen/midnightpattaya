-- Recovery Kit, server half (docs/RECOVERY_AND_COLLISION.md): the stuck-car rescue.
-- CarController offers "Stuck? Hold R to rescue" and fires RequestRescue. The server decides everything:
--   * it keeps its own trail of every driven car (10 Hz samples of position, heading, speed, tilt; cleared on a
--     teleport), and the rescue spot is always a trail point: a place this car was driving normally on a road a
--     moment ago. A rescue can therefore only move a car back along where it came from, never forward: it cannot
--     skip a checkpoint or work as a shortcut.
--   * loop race: the spot also stays out of the next gate's corridor (Recovery_GateMargin before it). Sprints and
--     street races: when the race server publishes the player attribute RouteNextCp (Vector3, proposed diff in the
--     doc) the spot keeps 26 + margin away from it.
--   * the car is towed back along its own trail (anchored, server PivotTo) at Recovery_RescueGlide studs/s
--     (45 during a job, below the jobs bump detector), set down facing the road direction, held anchored
--     1 s in races / 0.5 s elsewhere and handed back to the driver.
--   * checks: Recovery_Enabled + Recovery_AntiStuck, seated in a race car that is not anchored, not in a circuit
--     session (circuits keep their T reset), server-seen speed below Recovery_RescueMaxSpeed, one rescue per
--     Recovery_RescueCooldown s.
-- Player attributes: RescueActive (bool), RescueAt (server time a rescue started), RescueEndAt.
-- Remotes (ReplicatedStorage.PattayaRemotes): RequestRescue (client -> server, reason string),
-- RescueUpdate (server -> client: "start" {eta, hold} / "done" {ghost} / "denied" text).
--
-- Arcade traffic hits (Phase 2, CollisionModel = "arcade"): CarController reports heavy / head-on hits with
-- TrafficHit (tier, vc, speedBefore). Checked here: arcade on, 1 report per Arcade_HitReportGap s, the server saw
-- the car at Arcade_HitMinSpeed or more in the last 0.6 s, vc plausible, and a traffic car (same deterministic
-- formula as the clients, ReplicatedStorage.PattayaTraffic) within Arcade_HitTrafficRadius at that server time.
-- A valid hit sets the player attributes TrafficHitAt / TrafficHitTier / TrafficHits and fires the server-only
-- BindableEvent ServerStorage.PattayaTrafficHit (plr, tier, vc): PattayaJobsServer counts it as a bump with the
-- proposed diff in docs/RECOVERY_AND_COLLISION.md.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local Recovery = require(ReplicatedStorage:WaitForChild("PattayaRecovery"))

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
local RequestRescue = remote("RequestRescue")
local RescueUpdate = remote("RescueUpdate")
local TrafficHit = remote("TrafficHit")
local hitSignal = ServerStorage:FindFirstChild("PattayaTrafficHit") or Instance.new("BindableEvent")
hitSignal.Name = "PattayaTrafficHit"
hitSignal.Parent = ServerStorage

-- road graph (optional: the old RaceMap test place has none). Only PattayaRoute's public nearestEdge / toLocal are
-- used; the edge polylines and widths come from the read-only graph data.
local Route, graph = nil, nil
do
	local data = ServerStorage:WaitForChild("PattayaData", 30)
	if data and data:FindFirstChild("graph") then
		local okR, r = pcall(require, ServerStorage:WaitForChild("PattayaRoute"))
		local okG, g = pcall(require, data.graph)
		if okR and okG then
			Route, graph = r, g
		else
			warn("PattayaRecoveryServer: road graph unavailable, rescue uses the trail only", r, g)
		end
	end
end

local SAMPLE_DT = 0.1
local TRAIL_SECONDS = 45
local TELEPORT_JUMP = 60 -- studs between two samples = a server move / teleport: the trail starts again
local CHASSIS_UP = 2.8   -- chassis centre above the road surface as driven (RaceSessionService CHASSIS_UP)

local trails = {} -- [player] = {chassis, crumbs = {{t, x, y, z, hx, hz, speed, up}}, at}
local busy = {}   -- [player] = true while a rescue runs
local lastRescueEnd = {} -- [player] = server time

local function now(): number
	return workspace:GetServerTimeNow()
end

local function carOf(plr: Player): BasePart?
	if Route then
		return Route.carOf(plr)
	end
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

local function inRace(plr: Player): boolean
	return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
		or plr:GetAttribute("EventActive") == true
end

-- trail -------------------------------------------------------------------------------------------------------------
RunService.Heartbeat:Connect(function()
	local t = now()
	for _, plr in Players:GetPlayers() do
		local chassis = carOf(plr)
		local tr = trails[plr]
		if not chassis then
			trails[plr] = nil
			continue
		end
		if not tr or tr.chassis ~= chassis then
			tr = {chassis = chassis, crumbs = {}, at = 0}
			trails[plr] = tr
		end
		if busy[plr] or t - tr.at < SAMPLE_DT then
			continue
		end
		local pos = chassis.Position
		local crumbs = tr.crumbs
		local last = crumbs[#crumbs]
		local speed = 0
		if last then
			local d = math.sqrt((pos.X - last.x) ^ 2 + (pos.Z - last.z) ^ 2)
			if d > TELEPORT_JUMP then
				table.clear(crumbs)
			else
				speed = d / math.max(t - last.t, 1 / 60)
			end
		end
		tr.at = t
		local look = chassis.CFrame.LookVector
		local flat = Vector3.new(look.X, 0, look.Z)
		flat = if flat.Magnitude > 0.1 then flat.Unit else Vector3.new(0, 0, -1)
		table.insert(crumbs, {t = t, x = pos.X, y = pos.Y, z = pos.Z, hx = flat.X, hz = flat.Z, speed = speed,
			up = chassis.CFrame.UpVector.Y})
		while #crumbs > 0 and t - crumbs[1].t > TRAIL_SECONDS do
			table.remove(crumbs, 1)
		end
	end
end)

-- horizontal speed from the last second of the trail (velocity replication jitters on a car pushing a wall)
local function serverSpeed(tr, chassis: BasePart): number
	local v = chassis.AssemblyLinearVelocity
	local vel = Vector3.new(v.X, 0, v.Z).Magnitude
	local crumbs = tr.crumbs
	local n = #crumbs
	if n >= 2 then
		local a, b = nil, crumbs[n]
		for i = n - 1, 1, -1 do
			a = crumbs[i]
			if b.t - a.t >= 1 then break end
		end
		if a and b.t > a.t then
			local fromPos = math.sqrt((b.x - a.x) ^ 2 + (b.z - a.z) ^ 2) / (b.t - a.t)
			return math.min(vel, fromPos)
		end
	end
	return vel
end

-- road under a spot: (on road, road direction tx, tz) from the graph; without a graph, anything solid below counts
local castParams = RaycastParams.new()
castParams.FilterType = Enum.RaycastFilterType.Exclude
local function roadAt(x: number, z: number): (boolean, number?, number?)
	if Route and graph then
		local ei, _, d, s = Route.nearestEdge(Route.toLocal(Vector3.new(x, 0, z)))
		local e = ei and graph.edges[ei]
		if not e then
			return false
		end
		local width = e[5] or 26
		if d > width / 2 + 2 then
			return false
		end
		local tx, tz = Recovery.tangentAt(e[6], s)
		return true, tx, tz
	end
	return true, nil, nil
end

local function groundY(x: number, y: number, z: number, exclude: {Instance}): number?
	castParams.FilterDescendantsInstances = exclude
	local hit = workspace:Raycast(Vector3.new(x, y + 6, z), Vector3.new(0, -24, 0), castParams)
	return hit and hit.Position.Y
end

-- another car (or anything solid) already where the rescue would put this one
local overlapParams = OverlapParams.new()
overlapParams.FilterType = Enum.RaycastFilterType.Exclude
overlapParams.RespectCanCollide = true
local function blocked(cf: CFrame, size: Vector3, exclude: {Instance}): boolean
	overlapParams.FilterDescendantsInstances = exclude
	local parts = workspace:GetPartBoundsInBox(cf + Vector3.new(0, 1, 0), size + Vector3.new(1, 0, 1), overlapParams)
	return #parts > 0
end

-- loop race: the next gate of this player (PattayaRaceServer publishes RaceNext)
local function nextGate(plr: Player): BasePart?
	if plr:GetAttribute("RaceState") ~= "racing" then
		return nil
	end
	local world = workspace:FindFirstChild("PattayaWorld")
	local cps = world and world:FindFirstChild("Race") and world.Race:FindFirstChild("Checkpoints")
	local idx = plr:GetAttribute("RaceNext")
	if not (cps and idx) then
		return nil
	end
	for _, g in cps:GetChildren() do
		if g:IsA("BasePart") and g:GetAttribute("Index") == idx then
			return g
		end
	end
	return nil
end

local function pointAlong(path: {Vector3}, s: number): Vector3
	for i = 1, #path - 1 do
		local seg = (path[i + 1] - path[i]).Magnitude
		if s <= seg then
			return path[i]:Lerp(path[i + 1], if seg > 0 then s / seg else 1)
		end
		s -= seg
	end
	return path[#path]
end

-- the rescue ----------------------------------------------------------------------------------------------------------
local function deny(plr: Player, text: string)
	RescueUpdate:FireClient(plr, "denied", text)
end

local function release(plr: Player, chassis: BasePart)
	if chassis.Parent and chassis.Anchored then
		chassis.Anchored = false
		local owner = if carOf(plr) == chassis then plr else nil
		pcall(function() chassis:SetNetworkOwner(owner) end)
	end
end

local function tow(plr: Player, chassis: BasePart, path: {Vector3}, final: CFrame, speed: number, hold: number)
	local car = chassis.Parent :: Model
	local offset = chassis.CFrame:ToObjectSpace(car:GetPivot())
	local look0 = Vector3.new(chassis.CFrame.LookVector.X, 0, chassis.CFrame.LookVector.Z)
	look0 = if look0.Magnitude > 0.1 then look0.Unit else final.LookVector
	local rot0 = CFrame.lookAt(Vector3.zero, look0)
	local rot1 = final.Rotation
	chassis.Anchored = true
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	local total = 0
	for i = 1, #path - 1 do
		total += (path[i + 1] - path[i]).Magnitude
	end
	local dur = math.max(total / speed, 0.3)
	local t0 = os.clock()
	while true do
		local a = math.min((os.clock() - t0) / dur, 1)
		if not (chassis.Parent and car.Parent) then
			return
		end
		local p = pointAlong(path, total * a)
		local lift = 3 * math.sin(math.pi * a) -- up and over the kerb, down on the spot
		local r = rot0:Lerp(rot1, math.min(a * 3, 1))
		car:PivotTo((CFrame.new(p + Vector3.new(0, lift, 0)) * r) * offset)
		if a >= 1 then break end
		RunService.Heartbeat:Wait()
	end
	car:PivotTo(final * offset)
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	task.wait(hold)
	release(plr, chassis)
end

local function rescue(plr: Player, reason: string)
	local cfg = Recovery.config()
	if not (cfg.Recovery_Enabled and cfg.Recovery_AntiStuck) then
		return
	end
	if busy[plr] then
		return
	end
	local chassis = carOf(plr)
	local tr = trails[plr]
	if not (chassis and tr) then
		return
	end
	if plr:GetAttribute("CircuitActive") == true then
		deny(plr, "On a circuit: press T to reset to the last gate")
		return
	end
	if chassis.Anchored then
		return -- race grid, another server move
	end
	local t = now()
	local cdLeft = Recovery.cooldownLeft(t, lastRescueEnd[plr], cfg.Recovery_RescueCooldown)
	if cdLeft > 0 then
		deny(plr, ("Rescue ready in %d s"):format(math.ceil(cdLeft)))
		return
	end
	if serverSpeed(tr, chassis) >= cfg.Recovery_RescueMaxSpeed then
		deny(plr, "Rescue: slow down first")
		return
	end
	local racing = inRace(plr)
	local car = chassis.Parent :: Model
	local exclude = {car}
	for _, p in Players:GetPlayers() do
		if p.Character then table.insert(exclude, p.Character) end
	end
	local gate = nextGate(plr)
	local cp = plr:GetAttribute("RouteNextCp")
	local checks = 0
	local function allow(c): boolean
		-- each check scans the road graph: at most 40 candidates per rescue
		checks += 1
		if checks > 40 then
			return false
		end
		if gate then
			local rel = gate.CFrame:PointToObjectSpace(Vector3.new(c.x, gate.Position.Y, c.z))
			if not Recovery.gateAllows(rel.X, rel.Z, gate.Size.X / 2, cfg) then
				return false
			end
		end
		if typeof(cp) == "Vector3" and not Recovery.cpAllows(c.x - cp.X, c.z - cp.Z, cfg) then
			return false
		end
		if c.y < cfg.Recovery_FallY or not roadAt(c.x, c.z) then
			return false
		end
		-- solid ground under it (a sample taken while falling past a road's x/z does not count)
		return groundY(c.x, c.y, c.z, exclude) ~= nil
	end
	local pos = chassis.Position
	local crumbs = tr.crumbs
	local idx, _ = Recovery.pickCrumb(crumbs, t, pos.X, pos.Z, {maxPath = cfg.Recovery_RescueMaxPath}, allow)
	local path, spot, heading
	if idx then
		local c = crumbs[idx]
		path = {pos}
		for i = #crumbs, idx, -1 do
			table.insert(path, Vector3.new(crumbs[i].x, crumbs[i].y, crumbs[i].z))
		end
		local _, tx, tz = roadAt(c.x, c.z)
		local hx, hz = c.hx, c.hz
		if tx then
			hx, hz = Recovery.alignHeading(tx :: number, tz :: number, c.hx, c.hz)
		end
		spot = Vector3.new(c.x, c.y, c.z)
		heading = Vector3.new(hx, 0, hz)
		-- everything after the chosen point is behind us again: a second rescue can only go further back
		for _ = idx + 1, #crumbs do
			table.remove(crumbs)
		end
	elseif not racing and Route and graph then
		-- free roam / job without a usable trail (just got in, fell off the map): the nearest road within 300 studs
		local ei, q, d, s = Route.nearestEdge(Route.toLocal(pos))
		if not ei or d > 300 then
			deny(plr, "No road nearby to rescue to")
			return
		end
		local tx, tz = Recovery.tangentAt(graph.edges[ei][6], s)
		local look = chassis.CFrame.LookVector
		tx, tz = Recovery.alignHeading(tx, tz, look.X, look.Z)
		spot = Route.toWorld(q :: Vector2, pos.Y)
		heading = Vector3.new(tx, 0, tz)
		path = {pos, spot}
	else
		deny(plr, "No safe spot behind you yet: press R to flip in place")
		return
	end
	local gy = groundY(spot.X, spot.Y, spot.Z, exclude)
	local y = if gy then gy + CHASSIS_UP + 0.3 else spot.Y + 0.5
	local final = CFrame.lookAt(Vector3.new(spot.X, y, spot.Z), Vector3.new(spot.X, y, spot.Z) + heading)
	if blocked(final, chassis.Size, exclude) then
		-- someone parked there: a little further back along the road
		final = final + heading * -12
	end
	path[#path] = final.Position
	busy[plr] = true
	plr:SetAttribute("RescueActive", true)
	plr:SetAttribute("RescueAt", t)
	local jobs = plr:GetAttribute("JobActive") == true
	local speed = if jobs then cfg.Recovery_RescueGlideJob else cfg.Recovery_RescueGlide
	local hold = if racing then cfg.Recovery_RescueHoldRace else cfg.Recovery_RescueHoldFree
	local total = 0
	for i = 1, #path - 1 do
		total += (path[i + 1] - path[i]).Magnitude
	end
	RescueUpdate:FireClient(plr, "start", {eta = total / speed + hold, hold = hold, reason = reason})
	local ok, err = pcall(tow, plr, chassis, path, final, speed, hold)
	if not ok then
		warn("PattayaRecoveryServer: rescue failed:", err)
		release(plr, chassis)
	end
	busy[plr] = nil
	lastRescueEnd[plr] = now()
	plr:SetAttribute("RescueActive", false)
	plr:SetAttribute("RescueEndAt", lastRescueEnd[plr])
	if plr.Parent then
		RescueUpdate:FireClient(plr, "done", {ghost = cfg.Recovery_RescueGhost})
	end
end

local lastRequest = {} -- [player] = os.clock(): drop floods before any work
RequestRescue.OnServerEvent:Connect(function(plr: Player, reason)
	local c = os.clock()
	if c - (lastRequest[plr] or -math.huge) < 0.5 then
		return
	end
	lastRequest[plr] = c
	rescue(plr, if type(reason) == "string" then reason:sub(1, 16) else "stuck")
end)

-- arcade TrafficHit reports --------------------------------------------------------------------------------------
local TRAFFIC_ORIGIN_X, TRAFFIC_ORIGIN_Z = 20000, 0 -- PattayaBuilder.ORIGIN (as in PattayaTraffic.client.luau)
local trafficRoutes = nil :: any
local function routesOnce()
	if trafficRoutes == nil then
		trafficRoutes = false
		local m = ReplicatedStorage:FindFirstChild("PattayaTraffic")
		if m and m:IsA("ModuleScript") then
			local ok, data = pcall(require, m)
			if ok and type(data) == "table" then
				trafficRoutes = Recovery.buildTrafficRoutes(data, TRAFFIC_ORIGIN_X, TRAFFIC_ORIGIN_Z)
			end
		end
	end
	return trafficRoutes or nil
end

-- nearest traffic car to the car now or up to 0.3 s ago (the report arrives a little after the touch); nil = no data
local function trafficDistance(pos: Vector3, t: number): number?
	local routes = routesOnce()
	if not routes then
		return nil
	end
	local best = math.huge
	for _, back in {0, 0.15, 0.3} do
		local list = Recovery.trafficNear(routes, t - back, pos.X, pos.Z, 120)
		if list[1] then
			best = math.min(best, list[1].dist)
		end
	end
	return best
end

local lastHitAt = {} -- [player] = server time of the last accepted report
local lastHitTry = {} -- [player] = server time of the last report of any kind
TrafficHit.OnServerEvent:Connect(function(plr: Player, tier, vc, speedBefore)
	if not Recovery.arcade() then
		return
	end
	local chassis = carOf(plr)
	local tr = trails[plr]
	if not (chassis and tr) or type(tier) ~= "string" or type(vc) ~= "number" then
		return
	end
	local t = now()
	local cfg = Recovery.config()
	if t - (lastHitAt[plr] or -math.huge) < cfg.Arcade_HitReportGap or t - (lastHitTry[plr] or -math.huge) < 0.25 then
		return -- flood: dropped before the traffic lookup
	end
	lastHitTry[plr] = t
	local v = chassis.AssemblyLinearVelocity
	local peak = Vector3.new(v.X, 0, v.Z).Magnitude
	for i = #tr.crumbs, 1, -1 do
		local c = tr.crumbs[i]
		if t - c.t > 0.6 then break end
		peak = math.max(peak, c.speed)
	end
	local ok = Recovery.validateHitReport({now = t, lastAt = lastHitAt[plr], tier = tier, vc = vc,
		speedBefore = if type(speedBefore) == "number" then speedBefore else nil, serverPeak = peak,
		trafficDist = trafficDistance(chassis.Position, t)}, cfg)
	if not ok then
		return
	end
	lastHitAt[plr] = t
	plr:SetAttribute("TrafficHitAt", t)
	plr:SetAttribute("TrafficHitTier", tier)
	plr:SetAttribute("TrafficHits", (plr:GetAttribute("TrafficHits") or 0) + 1)
	hitSignal:Fire(plr, tier, vc)
end)

Players.PlayerRemoving:Connect(function(plr)
	lastHitAt[plr] = nil
	lastHitTry[plr] = nil
	trails[plr] = nil
	busy[plr] = nil
	lastRescueEnd[plr] = nil
	lastRequest[plr] = nil
end)
