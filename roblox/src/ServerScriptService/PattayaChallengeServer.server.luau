-- Street Challenge (RayCity's 1-on-1 on the live streets, up to 4 cars). While driving, press C near another driver:
-- they get 10 s to accept. The server lays a point-to-point route on the real road graph where the cars are, puts
-- them side by side at its start, counts down 3-2-1 and races them through the checkpoints; first to the last one
-- wins. If no other player is near, a street racer (AI) pulls up and races you instead.
-- Rules: checkpoints in order (26 studs), 180 s limit, the rest are out 60 s after the winner, leaving the car
-- forfeits, the 260 studs/s teleport check applies. Trailing drivers get extra nitro per checkpoint (RayCity
-- catch-up). The race reuses the Street Sprint client (SprintUpdate) for gates, GPS arrow and HUD.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
if not (data and data:FindFirstChild("graph") and workspace:FindFirstChild("PattayaWorld")) then
	return
end
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()

local CHALLENGE_RANGE = 150
local INVITE_TIME = 10
local MIN_LEN, MAX_LEN, CP_SPACING = 1500, 2600, 250
local CP_RADIUS = 26
local COUNTDOWN = 3.5
local TIME_LIMIT = 180
local DNF_AFTER_WINNER = 60
local MAX_SPEED = 260
local MAX_CARS = 4
local CAR_Y = 3.8 -- chassis height on the road (as driven)
local BOT_NAMES = {"Ae Turbo", "Nong Benz", "Somchai R", "Pattaya Phantom", "Jomtien Kid", "Naklua Ghost"}

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
local ChallengeRequest = remote("ChallengeRequest") -- client -> server
local ChallengeReply = remote("ChallengeReply") -- client -> server (accept: boolean)
local ChallengeMsg = remote("ChallengeMsg") -- server -> client: ("invite", fromName, seconds) / ("msg", text) /
-- ("countdown", goAt) / ("standings", {names}, myPlace)
local SprintUpdate = remote("SprintUpdate")
local NitroBonus = remote("NitroBonus")

local invites = {} -- [target] = {from, expires}
local lastRequest = {} -- [player] = time
local byPlayer = {} -- [player] = race
local races = {}

local function msg(plr: Player, text: string)
	ChallengeMsg:FireClient(plr, "msg", text)
end

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

-- AI street racer --------------------------------------------------------------------------------------------------
local function botModel(name: string): Model?
	local pool = {}
	for _, m in workspace:GetChildren() do
		local seat = m:FindFirstChild("DriveSeat")
		if m:GetAttribute("RaceCar") and m.PrimaryPart and seat and not seat.Occupant then
			table.insert(pool, m)
		end
	end
	if #pool == 0 then
		return nil
	end
	local src = pool[math.random(1, #pool)]
	local m = src:Clone()
	m:SetAttribute("RaceCar", nil)
	m:SetAttribute("RivalBot", true)
	m.Name = "Rival_" .. name
	for _, d in m:GetDescendants() do
		if d:IsA("Script") or d:IsA("LocalScript") or d:IsA("Seat") or d:IsA("VehicleSeat") or d:IsA("Constraint") then
			d:Destroy()
		elseif d:IsA("BasePart") then
			d.Anchored = true
			d.CanCollide, d.CanTouch, d.CanQuery = false, false, false
		end
	end
	m.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(200, 36)
	bb.StudsOffset = Vector3.new(0, 7, 0)
	bb.MaxDistance = 500
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = Color3.fromRGB(255, 90, 90)
	t.TextStrokeTransparency = 0.2
	t.Text = name
	t.Parent = bb
	bb.Parent = m.PrimaryPart
	return m
end

-- speed profile along the route: slow for corners (lateral grip), brake ahead of them
local function botProfile(route: {Vector3}, vmax: number)
	local pts = {}
	for i = 1, #route - 1 do
		local a, b = route[i], route[i + 1]
		local n = math.max(1, math.floor((b - a).Magnitude / 4))
		for j = 0, n - 1 do table.insert(pts, a:Lerp(b, j / n)) end
	end
	table.insert(pts, route[#route])
	local cum = {0}
	for i = 2, #pts do cum[i] = cum[i - 1] + (pts[i] - pts[i - 1]).Magnitude end
	local v = {}
	local K = 5 -- ~20 studs each side
	for i = 1, #pts do
		local a, b, c = pts[math.max(1, i - K)], pts[i], pts[math.min(#pts, i + K)]
		local d1, d2 = flat(b - a), flat(c - b)
		local theta = if d1.Magnitude > 0.1 and d2.Magnitude > 0.1 then math.acos(math.clamp(d1.Unit:Dot(d2.Unit), -1, 1)) else 0
		v[i] = if theta > 0.02 then math.min(vmax, math.sqrt(150 * 20 / theta)) else vmax
	end
	for i = #pts - 1, 1, -1 do -- braking pass, 110 studs/s2
		v[i] = math.min(v[i], math.sqrt(v[i + 1] ^ 2 + 2 * 110 * (cum[i + 1] - cum[i])))
	end
	return pts, cum, v
end

local function botStep(bot, dt: number): CFrame
	local pts, cum, prof = bot.pts, bot.cum, bot.prof
	while bot.idx < #pts - 1 and cum[bot.idx + 1] <= bot.s do
		bot.idx += 1
	end
	bot.v = math.min(prof[bot.idx], bot.v + 45 * dt)
	bot.s = math.min(bot.s + bot.v * dt, cum[#cum])
	while bot.idx < #pts - 1 and cum[bot.idx + 1] <= bot.s do
		bot.idx += 1
	end
	local i, j = bot.idx, bot.idx + 1
	local f = if cum[j] > cum[i] then (bot.s - cum[i]) / (cum[j] - cum[i]) else 0
	local p = pts[i]:Lerp(pts[j], f)
	local ahead = pts[math.min(#pts, j + 2)]
	local look = flat(ahead - p)
	local pos = Vector3.new(p.X, CAR_Y, p.Z) + bot.laneOffset
	return if look.Magnitude > 0.1 then CFrame.lookAt(pos, pos + look) else CFrame.new(pos)
end

-- races --------------------------------------------------------------------------------------------------------------
local function positionOf(part): Vector3?
	if part.plr then
		local chassis = Route.carOf(part.plr)
		return chassis and chassis.Position
	end
	return part.cf and part.cf.Position
end

local function standings(race)
	local order = {}
	for _, p in race.parts do
		table.insert(order, p)
	end
	table.sort(order, function(a, b)
		if a.place or b.place then
			return (a.place or 99) < (b.place or 99)
		end
		if a.out ~= b.out then
			return not a.out
		end
		return a.progress > b.progress
	end)
	return order
end

local function endRace(race, reason: string?)
	if race.ended then
		return
	end
	race.ended = true
	local n = #race.parts
	for _, p in race.parts do
		if p.plr then
			byPlayer[p.plr] = nil
			p.plr:SetAttribute("SprintActive", false)
			local chassis = Route.carOf(p.plr)
			if chassis and chassis.Anchored then
				chassis.Anchored = false
				pcall(function() chassis:SetNetworkOwner(p.plr) end)
			end
			if p.place then
				local winner = p.place == 1
				local money = math.floor(race.length / (if winner then 15 else 40) + (if winner then 100 * (n - 1) else 0))
				local exp = math.floor(race.length / (if winner then 30 else 60))
				local rivals = {}
				for _, q in race.parts do
					if q ~= p then table.insert(rivals, q.name) end
				end
				Progress.Award(p.plr, money, exp, if winner then "Challenge won" else ("Challenge %d/%d"):format(p.place, n))
				SprintUpdate:FireClient(p.plr, "finish", {time = p.time, length = race.length, money = money, exp = exp,
					text = if winner then ("YOU WIN!  %.2f s  vs %s"):format(p.time, table.concat(rivals, ", "))
						else ("%s place  %.2f s"):format(({"1st", "2nd", "3rd", "4th"})[p.place], p.time)})
			elseif not p.out then -- drivers already out were told when it happened
				SprintUpdate:FireClient(p.plr, "stop", reason or "Did not finish")
			end
		elseif p.model then
			local m = p.model
			task.delay(4, function() m:Destroy() end)
		end
	end
	table.remove(races, table.find(races, race))
end

local function startRace(parts)
	-- route from the junction nearest the cars, heading the way the first car faces
	local centre, look = Vector3.zero, nil
	local count = 0
	for _, p in parts do
		if p.plr then
			local chassis = Route.carOf(p.plr)
			if not chassis then
				return
			end
			centre += chassis.Position
			count += 1
			look = look or chassis.CFrame.LookVector
		end
	end
	centre /= count
	local r, why = Route.pointToPoint(centre, look, MIN_LEN, MAX_LEN, CP_SPACING)
	if not r then
		for _, p in parts do
			if p.plr then msg(p.plr, "Challenge: " .. why) end
		end
		return
	end
	local p0 = r.route[1]
	local p1 = r.route[2]
	for k = 2, #r.route do
		p1 = r.route[k]
		if flat(p1 - p0).Magnitude > 10 then break end
	end
	local d0 = flat(p1 - p0).Unit
	local right = Vector3.new(-d0.Z, 0, d0.X)
	local now = workspace:GetServerTimeNow()
	local race = {parts = parts, cps = r.cps, length = r.length, goAt = now + COUNTDOWN, standingsAt = 0}
	local names = {}
	for i, p in parts do
		local row, col = (i - 1) // 2, (i - 1) % 2
		local slot = p0 + d0 * (8 - row * 20) + right * (if col == 0 then -7 else 7)
		local cf = CFrame.lookAt(Vector3.new(slot.X, CAR_Y, slot.Z), Vector3.new(slot.X, CAR_Y, slot.Z) + d0)
		p.next, p.progress, p.last = 1, 0, cf.Position
		p.lastCpAt, p.lastCpPos = race.goAt, cf.Position
		if p.plr then
			local chassis = Route.carOf(p.plr) :: BasePart
			local car = chassis.Parent :: Model
			car:PivotTo(cf * chassis.CFrame:ToObjectSpace(car:GetPivot())) -- chassis lands exactly on cf
			chassis.AssemblyLinearVelocity = Vector3.zero
			chassis.Anchored = true -- held on the line until GO
			p.plr:SetAttribute("SprintActive", true)
			byPlayer[p.plr] = race
		else
			p.cf = cf
			p.offset = p.model.PrimaryPart.CFrame:ToObjectSpace(p.model:GetPivot())
			p.pts, p.cum, p.prof = botProfile(r.route, p.vmax)
			p.s, p.v, p.idx = 0, 0, 1
			p.laneOffset = right * (if (i - 1) % 2 == 0 then -7 else 7)
			p.model:PivotTo(cf * p.offset)
			p.model.Parent = workspace
		end
		table.insert(names, p.name)
	end
	table.insert(races, race)
	for _, p in parts do
		if p.plr then
			local rivals = {}
			for _, n in names do
				if n ~= p.name then table.insert(rivals, n) end
			end
			SprintUpdate:FireClient(p.plr, "start", {checkpoints = r.cps, dirs = r.dirs, route = r.route, length = r.length,
				start = race.goAt, timeLimit = TIME_LIMIT, title = "CHALLENGE", rivals = rivals})
			ChallengeMsg:FireClient(p.plr, "countdown", race.goAt)
		end
	end
	task.delay(race.goAt - workspace:GetServerTimeNow(), function()
		if race.ended then
			return
		end
		for _, p in parts do
			local chassis = p.plr and Route.carOf(p.plr)
			if chassis then
				chassis.Anchored = false
				pcall(function() chassis:SetNetworkOwner(p.plr) end)
			end
		end
	end)
end

local function playerPart(plr: Player)
	return {plr = plr, name = plr.DisplayName}
end

local function botPart(vmax: number?)
	local name = BOT_NAMES[math.random(1, #BOT_NAMES)]
	local m = botModel(name)
	if not m then
		return nil
	end
	return {name = name, model = m, vmax = vmax or 135}
end

ChallengeRequest.OnServerEvent:Connect(function(plr: Player)
	local now = os.clock()
	if now - (lastRequest[plr] or 0) < 3 then
		return
	end
	lastRequest[plr] = now
	local chassis = Route.carOf(plr)
	if not chassis or Route.busy(plr) or byPlayer[plr] then
		return
	end
	-- nearest other driver who is free
	local target, best = nil, CHALLENGE_RANGE
	for _, other in Players:GetPlayers() do
		local oc = other ~= plr and Route.carOf(other)
		if oc and not Route.busy(other) and not byPlayer[other] and not invites[other] then
			local d = (oc.Position - chassis.Position).Magnitude
			if d < best then
				target, best = other, d
			end
		end
	end
	if target then
		invites[target] = {from = plr, expires = now + INVITE_TIME}
		ChallengeMsg:FireClient(target, "invite", plr.DisplayName, INVITE_TIME)
		msg(plr, ("Challenge sent to %s..."):format(target.DisplayName))
		task.delay(INVITE_TIME + 0.5, function()
			local inv = invites[target]
			if inv and inv.from == plr then
				invites[target] = nil
				msg(plr, ("%s didn't answer"):format(target.DisplayName))
			end
		end)
		return
	end
	-- nobody around: a street racer takes you on
	local bot = botPart()
	if not bot then
		msg(plr, "No rivals around")
		return
	end
	msg(plr, ("%s wants to race you!"):format(bot.name))
	startRace({playerPart(plr), bot})
end)

ChallengeReply.OnServerEvent:Connect(function(plr: Player, accept)
	local inv = invites[plr]
	invites[plr] = nil
	if not inv or os.clock() > inv.expires then
		return
	end
	local from = inv.from
	if not accept then
		msg(from, ("%s declined"):format(plr.DisplayName))
		return
	end
	if not (Route.carOf(from) and Route.carOf(plr)) or Route.busy(from) or Route.busy(plr) or byPlayer[from] or byPlayer[plr] then
		msg(plr, "Challenge no longer possible")
		msg(from, "Challenge no longer possible")
		return
	end
	startRace({playerPart(from), playerPart(plr)})
end)

RunService.Heartbeat:Connect(function(dt)
	local now = workspace:GetServerTimeNow()
	for i = #races, 1, -1 do
		local race = races[i]
		if now < race.goAt then
			continue
		end
		local leaderNext = 0
		for _, p in race.parts do
			if not (p.place or p.out) then leaderNext = math.max(leaderNext, p.next) end
		end
		local active = 0
		for _, p in race.parts do
			if p.place or p.out then
				continue
			end
			if p.plr then
				if not p.plr.Parent or not Route.carOf(p.plr) then
					p.out, p.outReason = true, "Left the car - challenge forfeited"
					SprintUpdate:FireClient(p.plr, "stop", p.outReason)
					byPlayer[p.plr] = nil
					p.plr:SetAttribute("SprintActive", false)
					continue
				end
			else
				p.cf = botStep(p, dt)
				p.model:PivotTo(p.cf * p.offset)
			end
			active += 1
			local pos = positionOf(p) :: Vector3
			local c = race.cps[p.next]
			local hit = Route.segDist(p.last, pos, c) < CP_RADIUS
			p.last = pos
			if hit then
				if p.plr then
					local dtc = math.max(now - p.lastCpAt, 1 / 60)
					if (pos - p.lastCpPos).Magnitude / dtc > MAX_SPEED then
						p.out, p.outReason = true, "Run invalid (moved too fast)"
						SprintUpdate:FireClient(p.plr, "stop", p.outReason)
						byPlayer[p.plr] = nil
						p.plr:SetAttribute("SprintActive", false)
						continue
					end
					-- catch-up: trailing drivers get more nitro per checkpoint
					NitroBonus:FireClient(p.plr, if p.next < leaderNext then 30 else 20)
				end
				p.lastCpAt, p.lastCpPos = now, pos
				if p.next == #race.cps then
					race.finished = (race.finished or 0) + 1
					p.place = race.finished
					p.time = now - race.goAt
					race.firstFinishAt = race.firstFinishAt or now
					if p.plr then
						msg(p.plr, ("Finished %s - waiting for the others"):format(({"1st", "2nd", "3rd", "4th"})[p.place]))
					end
				else
					p.next += 1
					if p.plr then
						SprintUpdate:FireClient(p.plr, "next", p.next)
					end
				end
			end
			p.progress = p.next * 100000 - flat(race.cps[p.next] - pos).Magnitude
		end
		if now - race.standingsAt > 0.5 then
			race.standingsAt = now
			local order = standings(race)
			local names = {}
			for _, p in order do
				table.insert(names, p.name)
			end
			for place, p in order do
				if p.plr and not p.out then
					ChallengeMsg:FireClient(p.plr, "standings", names, place)
				end
			end
		end
		local everyonePlayerDone = true
		for _, p in race.parts do
			if p.plr and not (p.place or p.out) then everyonePlayerDone = false end
		end
		if active == 0 or everyonePlayerDone then
			endRace(race)
		elseif race.firstFinishAt and now - race.firstFinishAt > DNF_AFTER_WINNER then
			endRace(race, "Did not finish (60 s after the winner)")
		elseif now - race.goAt > TIME_LIMIT then
			endRace(race, "Time up")
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	invites[plr] = nil
	lastRequest[plr] = nil
end)
