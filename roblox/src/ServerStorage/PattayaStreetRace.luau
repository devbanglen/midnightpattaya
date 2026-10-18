-- Point-to-point street race engine on the live Pattaya streets, shared by Street Challenge, Road Fight
-- (PattayaChallengeServer) and the scheduled events Night Run / Survival (PattayaEventsServer).
-- Moved out of PattayaChallengeServer unchanged: AI street racer (model, speed profile, step), grid placement with
-- anchored cars through the countdown, ordered checkpoints within 26 studs (Route.segDist), standings, catch-up
-- nitro, forfeit / teleport check, time limit, DNF after the winner, the default Challenge payout.
--
-- StreetRace.startRace(parts, opts) -> race?   parts: from StreetRace.playerPart / StreetRace.botPart
-- opts (all optional; the defaults are exactly the Street Challenge):
--   title          HUD title ("CHALLENGE")
--   route          function(centre: Vector3, look: Vector3) -> r?, why   (default: Route.pointToPoint 1500-2600)
--   failPrefix     message prefix when no route is found ("Challenge: ")
--   timeLimit      seconds (180)
--   dnfAfterWinner seconds (60)
--   forfeitText    message for leaving the car ("Left the car - challenge forfeited")
--   gridAlongRoute place the grid on the route itself (front row ahead, back row at its start) instead of in a
--                  straight line behind it; bots keep their lane through corners. For big grids (events).
--   banner         toast shown at the start instead of "CHALLENGE vs ..." (big grids)
--   onResult       function(part, race, reason) for every human when the race ends (default: Challenge payout)
--   onEnd          function(race, reason) after all results
--   data           anything; kept as race.data for the callbacks
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))

local StreetRace = {}

local MIN_LEN, MAX_LEN, CP_SPACING = 1500, 2600, 250
local CP_RADIUS = 26
local COUNTDOWN = 3.5
local TIME_LIMIT = 180
local DNF_AFTER_WINNER = 60
local MAX_SPEED = 260
local CAR_Y = 3.8 -- chassis height on the road (as driven)
local BOT_NAMES = {"Ae Turbo", "Nong Benz", "Somchai R", "Pattaya Phantom", "Jomtien Kid", "Naklua Ghost"}
StreetRace.CP_SPACING = CP_SPACING
StreetRace.CAR_Y = CAR_Y
StreetRace.BOT_NAMES = BOT_NAMES

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
StreetRace.remote = remote
local ChallengeMsg = remote("ChallengeMsg") -- server -> client: ("invite", fromName, seconds) / ("msg", text) /
-- ("countdown", goAt) / ("standings", {names}, myPlace)
local SprintUpdate = remote("SprintUpdate")
local NitroBonus = remote("NitroBonus")
StreetRace.ChallengeMsg = ChallengeMsg
StreetRace.SprintUpdate = SprintUpdate

local byPlayer = {} -- [player] = race
local races = {}

-- FireClient to a player who already left would throw inside the shared Heartbeat (aborting that pass for every
-- race): every send to a player goes through this guard
local function fireClient(r: RemoteEvent, plr: Player?, ...)
	if plr and plr.Parent then
		r:FireClient(plr, ...)
	end
end
StreetRace.fireClient = fireClient

local function msg(plr: Player, text: string)
	fireClient(ChallengeMsg, plr, "msg", text)
end
StreetRace.msg = msg

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

local ORDINALS = {"1st", "2nd", "3rd", "4th"}
local function ordinal(n: number): string
	if ORDINALS[n] then
		return ORDINALS[n]
	end
	local tens = n % 100
	if tens >= 11 and tens <= 13 then
		return n .. "th"
	end
	local last = n % 10
	return n .. (if last == 1 then "st" elseif last == 2 then "nd" elseif last == 3 then "rd" else "th")
end
StreetRace.ordinal = ordinal

function StreetRace.inRace(plr: Player): boolean
	return byPlayer[plr] ~= nil
end

-- AI street racer --------------------------------------------------------------------------------------------------
local function botModel(name: string, carId: string?): Model?
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
	for _, m in pool do
		if carId and m.Name == "RaceCar_" .. carId then
			src = m
		end
	end
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
StreetRace.botModel = botModel

-- speed profile along the route: slow for corners (lateral grip), brake ahead of them
local function botProfile(route: {Vector3}, vmax: number, grip: number?)
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
		v[i] = if theta > 0.02 then math.min(vmax, math.sqrt((grip or 150) * 20 / theta)) else vmax
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
	if bot.lane and look.Magnitude > 0.1 then -- lane relative to the road direction (big-grid events)
		local u = look.Unit
		pos += Vector3.new(-u.Z, 0, u.X) * bot.lane
	end
	return if look.Magnitude > 0.1 then CFrame.lookAt(pos, pos + look) else CFrame.new(pos)
end

-- point and direction `s` studs along a route polyline
local function pointAlong(route: {Vector3}, s: number): (Vector3, Vector3)
	local walked = 0
	for i = 1, #route - 1 do
		local a, b = route[i], route[i + 1]
		local len = flat(b - a).Magnitude
		if len > 0.01 and walked + len >= s then
			return a:Lerp(b, (s - walked) / len), flat(b - a).Unit
		end
		walked += len
	end
	local a, b = route[math.max(1, #route - 1)], route[#route]
	local d = flat(b - a)
	return b, if d.Magnitude > 0.01 then d.Unit else Vector3.new(0, 0, -1)
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
StreetRace.standings = standings

-- Street Challenge payout (the default onResult)
local function challengeResult(p, race, reason: string?)
	local n = #race.parts
	if p.place then
		local winner = p.place == 1
		local money = math.floor(race.length / (if winner then 15 else 40) + (if winner then 100 * (n - 1) else 0))
		local exp = math.floor(race.length / (if winner then 30 else 60))
		local rivals = {}
		for _, q in race.parts do
			if q ~= p then table.insert(rivals, q.name) end
		end
		Progress.Award(p.plr, money, exp, if winner then "Challenge won" else ("Challenge %d/%d"):format(p.place, n))
		fireClient(SprintUpdate, p.plr, "finish", {time = p.time, length = race.length, money = money, exp = exp,
			text = if winner then ("YOU WIN!  %.2f s  vs %s"):format(p.time, table.concat(rivals, ", "))
				else ("%s place  %.2f s"):format(ordinal(p.place), p.time)})
	elseif not p.out then -- drivers already out were told when it happened
		fireClient(SprintUpdate, p.plr, "stop", reason or "Did not finish")
	end
end

-- un-anchors the car a driver was put on the grid with, even if they have left it since (it would stay frozen in
-- the street for good: nothing else ever un-anchors a race car); the driver gets it back only if still seated in it
local function releaseCar(p)
	local chassis = p.chassis
	if chassis and chassis.Parent and chassis.Anchored then
		chassis.Anchored = false
		local owner = if Route.carOf(p.plr) == chassis then p.plr else nil
		pcall(function() chassis:SetNetworkOwner(owner) end)
	end
end

local function endRace(race, reason: string?)
	if race.ended then
		return
	end
	race.ended = true
	race.endReason = reason
	local opts = race.opts
	for _, p in race.parts do
		if p.plr then
			byPlayer[p.plr] = nil
			p.plr:SetAttribute("SprintActive", false)
			releaseCar(p)
			local ok, err = pcall(opts.onResult or challengeResult, p, race, reason)
			if not ok then warn("StreetRace onResult: " .. tostring(err)) end
		elseif p.model then
			local m = p.model
			task.delay(4, function() m:Destroy() end)
		end
	end
	if opts.onEnd then
		local ok, err = pcall(opts.onEnd, race, reason)
		if not ok then warn("StreetRace onEnd: " .. tostring(err)) end
	end
	local k = table.find(races, race)
	if k then table.remove(races, k) end
end

function StreetRace.startRace(parts, opts)
	opts = opts or {}
	-- route from the junction nearest the cars, heading the way the first car faces (or opts.route)
	local centre, look = Vector3.zero, nil
	local count = 0
	for _, p in parts do
		if p.plr then
			local chassis = Route.carOf(p.plr)
			if not chassis then
				return nil
			end
			centre += chassis.Position
			count += 1
			look = look or chassis.CFrame.LookVector
		end
	end
	if count == 0 then
		return nil
	end
	centre /= count
	local r, why
	if opts.route then
		r, why = opts.route(centre, look)
	else
		r, why = Route.pointToPoint(centre, look, MIN_LEN, MAX_LEN, CP_SPACING)
	end
	if not r then
		for _, p in parts do
			if p.plr then msg(p.plr, (opts.failPrefix or "Challenge: ") .. tostring(why)) end
		end
		return nil
	end
	local timeLimit = opts.timeLimit or TIME_LIMIT
	local p0 = r.route[1]
	local p1 = r.route[2]
	for k = 2, #r.route do
		p1 = r.route[k]
		if flat(p1 - p0).Magnitude > 10 then break end
	end
	local d0 = flat(p1 - p0).Unit
	local right = Vector3.new(-d0.Z, 0, d0.X)
	local now = workspace:GetServerTimeNow()
	local race = {parts = parts, cps = r.cps, length = r.length, route = r.route, goAt = now + COUNTDOWN, standingsAt = 0,
		opts = opts, data = opts.data, timeLimit = timeLimit, ended = false}
	local rows = (#parts + 1) // 2
	local names = {}
	for i, p in parts do
		local row, col = (i - 1) // 2, (i - 1) % 2
		local side = if col == 0 then -7 else 7
		local cf, sAlong
		if opts.gridAlongRoute then
			sAlong = 8 + (rows - 1 - row) * 20
			local at, dir = pointAlong(r.route, sAlong)
			local slot = at + Vector3.new(-dir.Z, 0, dir.X) * side
			cf = CFrame.lookAt(Vector3.new(slot.X, CAR_Y, slot.Z), Vector3.new(slot.X, CAR_Y, slot.Z) + dir)
		else
			local slot = p0 + d0 * (8 - row * 20) + right * side
			cf = CFrame.lookAt(Vector3.new(slot.X, CAR_Y, slot.Z), Vector3.new(slot.X, CAR_Y, slot.Z) + d0)
		end
		p.next, p.progress, p.last = 1, 0, cf.Position
		p.place, p.out, p.time = nil, nil, nil
		p.lastCpAt, p.lastCpPos = race.goAt, cf.Position
		if p.plr then
			local chassis = Route.carOf(p.plr) :: BasePart
			p.chassis = chassis -- the car that is held on the grid (released at GO / at the end)
			local car = chassis.Parent :: Model
			car:PivotTo(cf * chassis.CFrame:ToObjectSpace(car:GetPivot())) -- chassis lands exactly on cf
			chassis.AssemblyLinearVelocity = Vector3.zero
			chassis.Anchored = true -- held on the line until GO
			p.plr:SetAttribute("SprintActive", true)
			byPlayer[p.plr] = race
		else
			p.cf = cf
			p.offset = p.model.PrimaryPart.CFrame:ToObjectSpace(p.model:GetPivot())
			p.pts, p.cum, p.prof = botProfile(r.route, p.vmax, p.grip)
			p.v, p.idx = 0, 1
			if opts.gridAlongRoute then
				p.s, p.lane, p.laneOffset = sAlong, side, Vector3.zero
			else
				p.s = 0
				p.laneOffset = right * (if (i - 1) % 2 == 0 then -7 else 7)
			end
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
			fireClient(SprintUpdate, p.plr, "start", {checkpoints = r.cps, dirs = r.dirs, route = r.route, length = r.length,
				start = race.goAt, timeLimit = timeLimit, title = opts.title or "CHALLENGE", rivals = rivals,
				banner = opts.banner})
			fireClient(ChallengeMsg, p.plr, "countdown", race.goAt)
		end
	end
	task.delay(race.goAt - workspace:GetServerTimeNow(), function()
		if race.ended then
			return
		end
		for _, p in parts do
			if p.plr then
				releaseCar(p)
			end
		end
	end)
	return race
end

function StreetRace.playerPart(plr: Player)
	return {plr = plr, name = plr.DisplayName}
end

function StreetRace.botPart(vmax: number?, name: string?, carId: string?, grip: number?)
	name = name or BOT_NAMES[math.random(1, #BOT_NAMES)]
	local m = botModel(name :: string, carId)
	if not m then
		return nil
	end
	return {name = name, model = m, vmax = vmax or 135, grip = grip}
end

local function knockOut(p, reason: string)
	p.out, p.outReason = true, reason
	fireClient(SprintUpdate, p.plr, "stop", reason)
	byPlayer[p.plr] = nil
	p.plr:SetAttribute("SprintActive", false)
end

RunService.Heartbeat:Connect(function(dt)
	local now = workspace:GetServerTimeNow()
	for i = #races, 1, -1 do
		local race = races[i]
		if now < race.goAt then
			continue
		end
		local opts = race.opts
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
					knockOut(p, opts.forfeitText or "Left the car - challenge forfeited")
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
						knockOut(p, "Run invalid (moved too fast)")
						continue
					end
					-- catch-up: trailing drivers get more nitro per checkpoint
					fireClient(NitroBonus, p.plr, if p.next < leaderNext then 30 else 20)
				end
				p.lastCpAt, p.lastCpPos = now, pos
				if p.next == #race.cps then
					race.finished = (race.finished or 0) + 1
					p.place = race.finished
					p.time = now - race.goAt
					race.firstFinishAt = race.firstFinishAt or now
					if p.plr then
						msg(p.plr, ("Finished %s - waiting for the others"):format(ordinal(p.place)))
					end
				else
					p.next += 1
					if p.plr then
						fireClient(SprintUpdate, p.plr, "next", p.next)
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
					fireClient(ChallengeMsg, p.plr, "standings", names, place)
				end
			end
		end
		local everyonePlayerDone = true
		for _, p in race.parts do
			if p.plr and not (p.place or p.out) then everyonePlayerDone = false end
		end
		local dnfAfter = opts.dnfAfterWinner or DNF_AFTER_WINNER
		if active == 0 or everyonePlayerDone then
			endRace(race)
		elseif race.firstFinishAt and now - race.firstFinishAt > dnfAfter then
			endRace(race, ("Did not finish (%d s after the winner)"):format(dnfAfter))
		elseif now - race.goAt > race.timeLimit then
			endRace(race, "Time up")
		end
	end
end)

return StreetRace
