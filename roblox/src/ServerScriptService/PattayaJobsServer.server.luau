-- Taxi and delivery jobs (RayCity missions, the main EXP source there). Stands sit at real Pattaya POIs
-- (ServerStorage.PattayaData.jobs, generated from OSM). Stop a car in a stand's ring and press E: the server picks a
-- destination stand 900-3,200 studs away by road, gives a time limit from the route length and shows the route.
-- Drive any way you like; stop in the destination ring to get paid. Hard knocks (sudden speed loss = collision) cut
-- the fare: passengers and fragile parcels don't like them. Time left adds a tip.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
local world = workspace:FindFirstChild("PattayaWorld")
if not (data and data:FindFirstChild("jobs") and data:FindFirstChild("graph") and world) then
	return
end
local stands = require(data.jobs)
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()

local STAND_RADIUS = 18 -- studs: the ring on the road
local STOP_SPEED = 30 -- studs/s: "stopped" enough to pick up or drop off
local MIN_LEN, MAX_LEN = 900, 3200
local MAX_SPEED = 260 -- teleport check, as in the races
local BUMP_DROP = 55 -- studs/s of speed lost within BUMP_WINDOW = a collision (full braking, 130/s2, loses 45)
local BUMP_WINDOW = 0.35
local SAMPLE_DT = 0.1

local KINDS = {
	taxi = {color = Color3.fromRGB(255, 200, 30), title = "TAXI", base = 60, perStud = 1 / 10, expPerStud = 1 / 18,
		slack = 20, speed = 70, bumpCut = 0.12, tipPerSec = 1.5},
	delivery = {color = Color3.fromRGB(40, 210, 130), title = "DELIVERY", base = 80, perStud = 1 / 8, expPerStud = 1 / 22,
		slack = 15, speed = 85, bumpCut = 0.15, tipPerSec = 2},
}

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
local RequestJob = remote("RequestJob")
local CancelJob = remote("CancelJob")
local JobUpdate = remote("JobUpdate")
local NearMiss = remote("NearMiss") -- from PattayaTraffic (client-side traffic)
local NitroBonus = remote("NitroBonus")
local NEAR_TIP = 5 -- ฿ per near miss during a job (RayCity "thrill" tips)

-- stands: built at runtime from the generated data (persistent, so every client sees all of them) ----------------
local folder = world:FindFirstChild("JobStands")
if folder then
	folder:Destroy()
end
folder = Instance.new("Folder")
folder.Name = "JobStands"
local byId = {}
for _, s in stands do
	local kind = KINDS[s.kind]
	if not kind then
		continue
	end
	local pos = Route.toWorld(Vector2.new(s.x, s.z), 1)
	local m = Instance.new("Model")
	m.Name = s.id
	m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	m:SetAttribute("Kind", s.kind)
	m:SetAttribute("Label", s.label)
	m:SetAttribute("Source", s.source)
	local ring = Instance.new("Part")
	ring.Name = "Ring"
	ring.Shape = Enum.PartType.Cylinder
	ring.Anchored, ring.CanCollide, ring.CanQuery, ring.CanTouch = true, false, false, false
	ring.Size = Vector3.new(0.3, STAND_RADIUS * 2, STAND_RADIUS * 2)
	ring.CFrame = CFrame.new(pos + Vector3.new(0, 0.2, 0)) * CFrame.Angles(0, 0, math.rad(90))
	ring.Material = Enum.Material.Neon
	ring.Color = kind.color
	ring.Transparency = 0.65
	ring.Parent = m
	local kerb = Vector3.new(s.kx, 0, s.kz) -- the stand sits in the kerb lane; the sign stands on the pavement
	local pole = Instance.new("Part")
	pole.Name = "Pole"
	pole.Anchored, pole.CanCollide, pole.CanQuery, pole.CanTouch = true, false, false, false
	pole.Size = Vector3.new(1, 18, 1)
	pole.Position = pos + kerb * 12 + Vector3.new(0, 9, 0)
	pole.Material = Enum.Material.Neon
	pole.Color = kind.color
	pole.Parent = m
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(220, 56)
	bb.StudsOffset = Vector3.new(0, 12, 0)
	bb.MaxDistance = 700
	bb.AlwaysOnTop = false
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = kind.color
	t.TextStrokeTransparency = 0.2
	t.Text = kind.title .. "\n" .. s.label
	t.Parent = bb
	bb.Parent = pole
	m.PrimaryPart = ring
	m.Parent = folder
	byId[s.id] = {id = s.id, kind = s.kind, label = s.label, pos = pos}
end
folder.Parent = world

-- jobs -------------------------------------------------------------------------------------------------------------
local active = {} -- [player] = {kind, from, to, dest, start, timeLimit, length, fare, bumps, ...}

local function stop(plr: Player, reason: string)
	if active[plr] then
		active[plr] = nil
		plr:SetAttribute("JobActive", false)
		JobUpdate:FireClient(plr, "stop", reason)
	end
end

local function speedOf(chassis: BasePart): number
	local v = chassis.AssemblyLinearVelocity
	return Vector3.new(v.X, 0, v.Z).Magnitude
end

local function flatDist(a: Vector3, b: Vector3): number
	return Vector3.new(a.X - b.X, 0, a.Z - b.Z).Magnitude
end

RequestJob.OnServerEvent:Connect(function(plr: Player, standId)
	local from = byId[standId]
	local chassis = Route.carOf(plr)
	if not (from and chassis) or active[plr] or Route.busy(plr) then
		return
	end
	if flatDist(chassis.Position, from.pos) > STAND_RADIUS + 4 or speedOf(chassis) > STOP_SPEED then
		return
	end
	local src = Route.nearestNode(Route.toLocal(from.pos), 600)
	if not src then
		return
	end
	local dist, prev = Route.dijkstra(src)
	-- destinations: any other stand whose nearest junction is in range by road
	local options = {}
	for _, s in byId do
		if s ~= from then
			local n = Route.nearestNode(Route.toLocal(s.pos), 600)
			local d = n and dist[n]
			if d and d >= MIN_LEN and d <= MAX_LEN then
				table.insert(options, {stand = s, node = n})
			end
		end
	end
	if #options == 0 then
		JobUpdate:FireClient(plr, "stop", "No customers here right now")
		return
	end
	local pick = options[math.random(1, #options)]
	local to = pick.stand
	local pts = Route.polylineOf(prev, src, pick.node)
	table.insert(pts, 1, Route.toLocal(from.pos))
	table.insert(pts, Route.toLocal(to.pos))
	local length = Route.length(pts)
	local k = KINDS[from.kind]
	local timeLimit = math.floor(k.slack + length / k.speed)
	local fare = math.floor(k.base + length * k.perStud)
	local route = {}
	for _, q in pts do
		table.insert(route, Route.toWorld(q))
	end
	local now = workspace:GetServerTimeNow()
	active[plr] = {kind = from.kind, from = from, to = to, start = now, timeLimit = timeLimit, length = length,
		fare = fare, bumps = 0, nearTip = 0, history = {}, low = 0, lastBumpAt = 0, sampleAt = now, samplePos = chassis.Position,
		checkAt = now, checkPos = chassis.Position}
	plr:SetAttribute("JobActive", true)
	JobUpdate:FireClient(plr, "start", {kind = from.kind, title = k.title, from = from.label, to = to.label,
		dest = to.pos, route = route, length = length, start = now, timeLimit = timeLimit, fare = fare})
end)

CancelJob.OnServerEvent:Connect(function(plr: Player)
	stop(plr, "Job cancelled")
end)

-- near misses past traffic: the traffic is client-side, so the server can only sanity-check (in a car, fast, rate
-- limited). Pays nitro (more for a combo within 4 s) and a tip during a job.
local nearState = {} -- [player] = {at, combo}
NearMiss.OnServerEvent:Connect(function(plr: Player)
	local chassis = Route.carOf(plr)
	local now = workspace:GetServerTimeNow()
	local ns = nearState[plr] or {at = 0, combo = 0}
	nearState[plr] = ns
	if not chassis or speedOf(chassis) < 60 or now - ns.at < 0.6 then
		return
	end
	ns.combo = if now - ns.at < 4 then math.min(ns.combo + 1, 10) else 1
	ns.at = now
	NitroBonus:FireClient(plr, (6 + 2 * ns.combo) * (if plr:GetAttribute("EventActive") then 2 else 1)) -- x2 in events
	local st = active[plr]
	if st then
		st.nearTip += NEAR_TIP
	end
	plr:SetAttribute("NearMissCombo", ns.combo)
	plr:SetAttribute("NearMissAt", now)
end)

RunService.Heartbeat:Connect(function()
	local now = workspace:GetServerTimeNow()
	for plr, st in active do
		local chassis = Route.carOf(plr)
		if not chassis or not plr.Parent then
			stop(plr, "Left the car - job cancelled")
			continue
		end
		if now - st.start > st.timeLimit then
			stop(plr, "Too late! The customer left")
			continue
		end
		if plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true then
			stop(plr, "Job cancelled")
			continue
		end
		local pos = chassis.Position
		-- teleport check once a second
		if now - st.checkAt >= 1 then
			if flatDist(pos, st.checkPos) / (now - st.checkAt) > MAX_SPEED then
				stop(plr, "Job invalid (moved too fast)")
				continue
			end
			st.checkAt, st.checkPos = now, pos
		end
		-- collision: ground speed (from position, 10 Hz: replicated velocity glitches on corners) falls by more than
		-- BUMP_DROP within BUMP_WINDOW and stays down for two samples
		local speed = speedOf(chassis)
		if now - st.sampleAt >= SAMPLE_DT then
			local v = flatDist(pos, st.samplePos) / (now - st.sampleAt)
			st.sampleAt, st.samplePos = now, pos
			local h = st.history
			local peak = 0
			for _, e in h do
				if now - e[1] <= BUMP_WINDOW then
					peak = math.max(peak, e[2])
				end
			end
			st.low = if peak - v > BUMP_DROP then st.low + 1 else 0
			table.insert(h, {now, v})
			if #h > 8 then
				table.remove(h, 1)
			end
			if st.low >= 2 and now - st.lastBumpAt > 1 then
				st.lastBumpAt = now
				st.bumps += 1
				st.low = 0
				table.clear(h)
				JobUpdate:FireClient(plr, "bump", st.bumps)
			end
		end
		-- drop-off
		if flatDist(pos, st.to.pos) < STAND_RADIUS + 2 and speed < STOP_SPEED then
			local k = KINDS[st.kind]
			local t = now - st.start
			local cut = math.min(st.bumps * k.bumpCut, 0.6)
			local tip = math.floor(math.max(0, st.timeLimit - t) * k.tipPerSec) + st.nearTip
			local money = math.floor(st.fare * (1 - cut)) + tip
			local exp = math.floor(st.length * k.expPerStud)
			active[plr] = nil
			plr:SetAttribute("JobActive", false)
			Progress.Award(plr, money, exp, ("%s to %s"):format(k.title, st.to.label))
			JobUpdate:FireClient(plr, "finish", {time = t, money = money, exp = exp, tip = tip, bumps = st.bumps,
				to = st.to.label})
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	active[plr] = nil
	nearState[plr] = nil
end)
