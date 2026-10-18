-- Scheduled street events (RayCity Jilju/Pokju and Survival) on the live Pattaya streets.
--   NIGHT RUN (DAY RUN by day): every CONFIG.intervalMinutes the server announces a mass race 60 s ahead. A big
--     purple ring with a beacon appears at a start junction on a main road. Drive into the ring, or press J (R1 /
--     JOIN button) while driving within CONFIG.joinRadius, to enter. At the start everyone is put on a multi-row
--     grid (up to 16 cars) on one long point-to-point route (2,500-4,500 studs), 3-2-1-GO, race, standings,
--     pay by place and number of entrants. Entrants carry the Player attribute EventActive=true while racing
--     (PattayaJobsServer pays extra near-miss nitro for it).
--   SURVIVAL: every CONFIG.survivalEvery-th event. 3-5 rounds on consecutive short routes (each round starts where
--     the last one ended). After each round the slowest 20% are eliminated (at least 1, never everyone); drivers who
--     leave the car are out. Cars are equalised: Player attributes Equalised=true and SpeedCap (CarController
--     honours them). Last driver standing wins a title and the prize.
--   AI street racers fill the grid up to CONFIG.botFill cars when fewer than 2 humans joined a Night Run (and always
--   for Survival, so it has rounds to play), so both run with 1 player in Studio.
-- Testing: switch the Studio command bar to the Server and run
--   game.ServerStorage.StartEvent:Fire("nightrun", 15)   -- or "survival"; the number is the lead time in seconds
-- Optional overrides as attributes on this script: IntervalMinutes, SurvivalEvery, LeadSeconds (0 interval = off).
-- The race itself runs on ServerStorage.PattayaStreetRace (shared with Street Challenge and Road Fight).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")
local Lighting = game:GetService("Lighting")

local data = ServerStorage:WaitForChild("PattayaData", 30)
if not (data and data:FindFirstChild("graph") and workspace:FindFirstChild("PattayaWorld")) then
	return
end
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()
local StreetRace = require(ServerStorage:WaitForChild("PattayaStreetRace"))
local graph = require(data.graph)

local CONFIG = {
	intervalMinutes = 15, -- real minutes between events (0 = only forced starts)
	leadSeconds = 60, -- announcement ahead of the start
	survivalEvery = 3, -- every 3rd scheduled event is Survival (0 = never)
	ringRadius = 45, -- drive into this ring to join
	joinRadius = 1500, -- or press J while driving this close to the ring
	maxEntrants = 16,
	botFill = 6, -- grid size filled with AI (Night Run: only when fewer than 2 humans joined)
	nightRun = {minLen = 2500, maxLen = 4500, spacing = 300, timeLimit = 240, dnfAfter = 45,
		botSpeed = {125, 150}, podium = {200, 100, 50}},
	survival = {rounds = 4, minLen = 1000, maxLen = 1600, spacing = 250, timeLimit = 120, dnfAfter = 25,
		eliminate = 0.2, speedCap = 150, botSpeed = {128, 142}, pause = 7,
		roundMoney = 40, roundExp = 20, winMoney = 600, winExp = 300, title = "Survivor"},
}
local function cfg(attr: string, default: number): number
	local v = script:GetAttribute(attr)
	return if type(v) == "number" then v else default
end

local remote = StreetRace.remote
local EventJoin = remote("EventJoin") -- client -> server: join the announced event
local ChallengeMsg = StreetRace.ChallengeMsg
local SprintUpdate = StreetRace.SprintUpdate
local msg = StreetRace.msg
local ordinal = StreetRace.ordinal

-- public state for clients (attributes replicate, so late joiners see the event too)
local state = ReplicatedStorage:FindFirstChild("PattayaEvent") or Instance.new("Folder")
state.Name = "PattayaEvent"
state.Parent = ReplicatedStorage
local function setState(t)
	for k, v in t do
		state:SetAttribute(k, v)
	end
end
setState({Phase = "idle", Kind = "", Title = "", StartAt = 0, RingPos = Vector3.zero, RingRadius = CONFIG.ringRadius,
	JoinRadius = CONFIG.joinRadius, Entrants = 0, Round = 0, Rounds = 0, Alive = 0, NextAt = 0})

local function msgAll(text: string)
	ChallengeMsg:FireAllClients("msg", text)
end

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

local function isNight(): boolean
	local t = Lighting.ClockTime
	return t < 6.3 or t > 17.8 -- same as PattayaNightLights
end

-- start junctions: nodes on main roads (tier 2) with at least two roads
local mainNodes = {}
do
	local deg, main = {}, {}
	for _, e in graph.edges do
		for _, n in {e[1], e[2]} do
			deg[n] = (deg[n] or 0) + 1
			if e[4] == 2 then main[n] = true end
		end
	end
	for n in main do
		if deg[n] >= 2 then table.insert(mainNodes, n) end
	end
	table.sort(mainNodes)
end

-- pick a start on a main road, near a random driver when someone is driving, and a route from it
local function pickRoute(minLen: number, maxLen: number, spacing: number)
	local drivers = {}
	for _, plr in Players:GetPlayers() do
		local c = Route.carOf(plr)
		if c then table.insert(drivers, Route.toLocal(c.Position)) end
	end
	for _ = 1, 6 do
		local pool = mainNodes
		if #drivers > 0 then
			local centre = drivers[math.random(1, #drivers)]
			local near = {}
			for _, n in mainNodes do
				local d = (Route.nodes[n] - centre).Magnitude
				if d > 150 and d < 1500 then table.insert(near, n) end
			end
			if #near > 0 then pool = near end
		end
		if #pool == 0 then
			return nil
		end
		local n = pool[math.random(1, #pool)]
		local r = Route.pointToPoint(Route.toWorld(Route.nodes[n]), Vector3.new(1, 0, 0), minLen, maxLen, spacing)
		if r then
			return r
		end
	end
	return nil
end

-- gathering ring + beacon -------------------------------------------------------------------------------------------
local eventsFolder = workspace.PattayaWorld:FindFirstChild("Events")
if eventsFolder then
	eventsFolder:Destroy()
end
eventsFolder = Instance.new("Folder")
eventsFolder.Name = "Events"
eventsFolder.Parent = workspace.PattayaWorld

local function buildRing(pos: Vector3, title: string, color: Color3): Model
	local m = Instance.new("Model")
	m.Name = "EventRing"
	m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	local function part(name: string, size: Vector3, cf: CFrame, transparency: number, shape: Enum.PartType?)
		local p = Instance.new("Part")
		p.Name = name
		p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false
		p.Material = Enum.Material.Neon
		p.Color = color
		p.Transparency = transparency
		p.CastShadow = false
		if shape then p.Shape = shape end
		p.Size = size
		p.CFrame = cf
		p.Parent = m
		return p
	end
	local d = CONFIG.ringRadius * 2
	local ring = part("Ring", Vector3.new(0.3, d, d), CFrame.new(pos + Vector3.new(0, 0.25, 0)) * CFrame.Angles(0, 0, math.rad(90)),
		0.65, Enum.PartType.Cylinder)
	part("Beacon", Vector3.new(6, 260, 6), CFrame.new(pos + Vector3.new(0, 130, 0)), 0.55)
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(320, 70)
	bb.StudsOffset = Vector3.new(0, 150, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 6000
	bb.LightInfluence = 0
	local t = Instance.new("TextLabel")
	t.Name = "Label"
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = color
	t.TextStrokeTransparency = 0.1
	t.Text = title .. "\nJOIN HERE"
	t.Parent = bb
	bb.Parent = ring
	m.PrimaryPart = ring
	m.Parent = eventsFolder
	return m
end

-- event state -------------------------------------------------------------------------------------------------------
local phase = "idle" -- idle / gathering / running
local entrants = {} -- ordered list of players who joined
local joined = {} -- [player] = true
local ringPos = Vector3.zero
local eventCount = 0

local function clearPlayer(plr: Player)
	joined[plr] = nil
	if plr.Parent then
		plr:SetAttribute("EventJoined", nil)
		plr:SetAttribute("EventActive", nil)
		plr:SetAttribute("Equalised", nil)
		plr:SetAttribute("SpeedCap", nil)
		if not StreetRace.inRace(plr) then
			plr:SetAttribute("SprintActive", false)
		end
	end
end

local function join(plr: Player, how: string)
	if phase ~= "gathering" or joined[plr] or #entrants >= CONFIG.maxEntrants then
		if phase == "gathering" and not joined[plr] and #entrants >= CONFIG.maxEntrants then
			msg(plr, "The event is full")
		end
		return
	end
	if not Route.carOf(plr) or Route.busy(plr) or StreetRace.inRace(plr) then
		return
	end
	joined[plr] = true
	table.insert(entrants, plr)
	plr:SetAttribute("EventJoined", true)
	plr:SetAttribute("SprintActive", true) -- blocks sprints, jobs and challenges while waiting for the start
	state:SetAttribute("Entrants", #entrants)
	local left = math.max(0, math.ceil(state:GetAttribute("StartAt") - workspace:GetServerTimeNow()))
	msg(plr, ("You're in! %s starts in %d s%s"):format(state:GetAttribute("Title"), left,
		if how == "key" then " - you'll be moved to the grid" else ""))
end

EventJoin.OnServerEvent:Connect(function(plr: Player)
	local c = Route.carOf(plr)
	if c and phase == "gathering" and flat(c.Position - ringPos).Magnitude <= CONFIG.joinRadius then
		join(plr, "key")
	elseif c and phase == "gathering" then
		msg(plr, "Too far away - drive towards the beacon")
	end
end)

-- humans who can still race: joined, in a car, not taken by another mode
local function readyHumans(list: {Player}): {Player}
	local out = {}
	for _, plr in list do
		if plr.Parent and Route.carOf(plr) and not StreetRace.inRace(plr) and plr:GetAttribute("JobActive") ~= true
			and plr:GetAttribute("RaceState") ~= "racing" then
			table.insert(out, plr)
		else
			if plr.Parent then msg(plr, "You missed the start (not in your car)") end
			clearPlayer(plr)
		end
	end
	return out
end

local function newBots(count: number, speed: {number})
	local bots = {}
	local names = table.clone(StreetRace.BOT_NAMES)
	for i = 1, count do
		local base = names[(i - 1) % #names + 1]
		local name = if i > #names then base .. " " .. (i // #names + 1) else base
		table.insert(bots, {name = name, vmax = math.random(speed[1], speed[2])})
	end
	return bots
end

-- build race parts for this round: humans first (front rows), then bots
local function partsFor(humans: {Player}, bots)
	local parts = {}
	for _, plr in humans do
		local p = StreetRace.playerPart(plr)
		p.entrant = plr
		table.insert(parts, p)
	end
	for _, b in bots do
		local p = StreetRace.botPart(b.vmax, b.name, nil, 150)
		if p then
			p.entrant = b
			table.insert(parts, p)
		end
	end
	return parts
end

local function waitForEnd(race)
	while not race.ended do
		task.wait(0.5)
	end
end

-- NIGHT RUN ---------------------------------------------------------------------------------------------------------
local function runNightRun(title: string, r, humans: {Player}, bots)
	local C = CONFIG.nightRun
	local parts = partsFor(humans, bots)
	local n, nh = #parts, #humans
	local results = {}
	local race = StreetRace.startRace(parts, {
		title = title,
		banner = ("%s  %d cars  %.1f km"):format(title, n, r.length * 0.28 / 1000),
		route = function() return r end,
		failPrefix = title .. ": ",
		timeLimit = C.timeLimit,
		dnfAfterWinner = C.dnfAfter,
		forfeitText = "Left the car - out of the " .. title,
		gridAlongRoute = true,
		onResult = function(p, race, reason)
			local plr = p.plr
			clearPlayer(plr)
			if p.place then
				local place = p.place
				local money = math.floor(race.length / 25 + 20 * (n - place) + (C.podium[place] or 0) * (1 + 0.25 * (nh - 1)))
				local exp = math.floor(race.length / 40 + 10 * (n - place))
				Progress.Award(plr, money, exp, ("%s %s/%d"):format(title, ordinal(place), n))
				SprintUpdate:FireClient(plr, "finish", {time = p.time, length = race.length, money = money, exp = exp,
					text = if place == 1 then ("%s WINNER!  %.2f s"):format(title, p.time)
						else ("%s place of %d  %.2f s"):format(ordinal(place), n, p.time)})
			elseif not p.out then
				SprintUpdate:FireClient(plr, "stop", reason or "Did not finish")
			end
		end,
		onEnd = function(race)
			for place, p in StreetRace.standings(race) do
				results[place] = p
			end
		end,
	})
	if not race then
		for _, plr in humans do clearPlayer(plr) end
		return
	end
	state:SetAttribute("Entrants", n)
	for _, plr in humans do
		plr:SetAttribute("EventActive", true)
	end
	waitForEnd(race)
	local w = results[1]
	if w and w.place then
		msgAll(("%s won by %s  %.2f s"):format(title, w.name, w.time))
	else
		msgAll(title .. " is over")
	end
end

-- SURVIVAL ----------------------------------------------------------------------------------------------------------
local function runSurvival(title: string, r1, humans: {Player}, bots)
	local C = CONFIG.survival
	local rounds = math.clamp(C.rounds, 3, 5)
	-- alive: entrant records {plr=Player} or bot records {name, vmax}
	local alive = {}
	for _, plr in humans do
		table.insert(alive, plr)
		plr:SetAttribute("Equalised", true)
		plr:SetAttribute("SpeedCap", C.speedCap)
		plr:SetAttribute("EventActive", true)
	end
	for _, b in bots do
		table.insert(alive, b)
	end
	local function nameOf(e)
		return if typeof(e) == "Instance" then e.DisplayName else e.name
	end
	local function humansIn(list)
		local hs = {}
		for _, e in list do
			if typeof(e) == "Instance" then table.insert(hs, e) end
		end
		return hs
	end
	-- out after `round`; pays for the rounds survived before it (all of them for the final's runners-up)
	local function eliminateHuman(plr: Player, round: number, survived: number?, text: string?)
		local s = survived or (round - 1)
		clearPlayer(plr)
		if plr.Parent then
			if s > 0 then
				Progress.Award(plr, s * C.roundMoney, s * C.roundExp, ("%s: out in round %d"):format(title, round))
			end
			msg(plr, text or ("ELIMINATED in round %d of %d"):format(round, rounds))
		end
	end
	local r = r1
	local winner = nil
	for round = 1, rounds do
		local hs = readyHumans(humansIn(alive))
		-- drop humans who are no longer able to race from alive
		local ok = {}
		for _, plr in hs do ok[plr] = true end
		for i = #alive, 1, -1 do
			local e = alive[i]
			if typeof(e) == "Instance" and not ok[e] then
				table.remove(alive, i)
				eliminateHuman(e, round)
			end
		end
		if #hs == 0 then
			break
		end
		local final = round == rounds or #alive <= 2
		if round > 1 then
			local last, prev = r.route[#r.route], r.route[math.max(1, #r.route - 1)]
			local nr = Route.pointToPoint(last, last - prev, C.minLen, C.maxLen, C.spacing)
			if nr then r = nr end -- otherwise run the last route again
		end
		local botsAlive = {}
		for _, e in alive do
			if typeof(e) ~= "Instance" then table.insert(botsAlive, e) end
		end
		setState({Round = round, Rounds = rounds, Alive = #alive})
		local roundTitle = ("SURVIVAL R%d/%d"):format(round, rounds)
		local parts = partsFor(hs, botsAlive)
		local n = #parts
		local order
		local race = StreetRace.startRace(parts, {
			title = roundTitle,
			banner = ("%s  ROUND %d/%d%s  %d drivers"):format(title, round, rounds, if final then " FINAL" else "", n),
			route = function() return r end,
			failPrefix = title .. ": ",
			timeLimit = C.timeLimit,
			dnfAfterWinner = C.dnfAfter,
			forfeitText = "Left the car - eliminated",
			gridAlongRoute = true,
			onResult = function(p, race, reason)
				if p.place then
					SprintUpdate:FireClient(p.plr, "finish", {time = p.time, length = race.length, money = 0, exp = 0,
						text = ("Round %d: %s of %d  %.2f s"):format(round, ordinal(p.place), n, p.time)})
				elseif not p.out then
					SprintUpdate:FireClient(p.plr, "stop", reason or "Did not finish")
				end
			end,
			onEnd = function(race)
				order = StreetRace.standings(race)
			end,
		})
		if not race then
			break
		end
		waitForEnd(race)
		-- ranking: finishers by place, then the rest by progress, drivers who left the car last
		local ranked = {}
		for _, p in order do
			table.insert(ranked, p.entrant)
		end
		local outSet = {}
		for _, p in order do
			if p.out then outSet[p.entrant] = true end
		end
		if final then
			winner = ranked[1]
			for i = 2, #ranked do
				local e = ranked[i]
				if typeof(e) == "Instance" then
					eliminateHuman(e, round, round, ("%s in the final - %s wins"):format(ordinal(i), nameOf(winner)))
				end
			end
			alive = {winner}
			break
		end
		local k = math.max(1, math.floor(#ranked * C.eliminate))
		local cut = {}
		for i, e in ranked do
			if i > #ranked - k or outSet[e] then table.insert(cut, e) end
		end
		while #cut >= #ranked do -- never everyone: the best of them stays
			table.remove(cut, 1)
		end
		local cutSet = {}
		for _, e in cut do cutSet[e] = true end
		local nextAlive, cutNames = {}, {}
		for _, e in ranked do
			if cutSet[e] then
				table.insert(cutNames, nameOf(e))
				if typeof(e) == "Instance" then eliminateHuman(e, round) end
			else
				table.insert(nextAlive, e)
			end
		end
		alive = nextAlive
		for _, plr in humansIn(alive) do
			msg(plr, ("Round %d survived! Eliminated: %s. %d left"):format(round, table.concat(cutNames, ", "), #alive))
			plr:SetAttribute("SprintActive", true) -- hold other modes off during the break
		end
		if #alive <= 1 then
			winner = alive[1]
			break
		end
		if #humansIn(alive) == 0 then
			winner = alive[1] -- every human is out: the best remaining AI takes it
			break
		end
		setState({Alive = #alive})
		task.wait(C.pause)
	end
	-- result
	if winner and typeof(winner) == "Instance" and winner.Parent then
		local ls = winner:FindFirstChild("leaderstats")
		local current = ls and ls:FindFirstChild("Title") and ls.Title.Value or ""
		if current == "" then
			Progress.SetTitle(winner, C.title)
		end
		Progress.Award(winner, C.winMoney + rounds * C.roundMoney, C.winExp + rounds * C.roundExp, title .. " winner")
		msg(winner, "LAST DRIVER STANDING - you won SURVIVAL!")
	end
	for _, e in alive do
		if typeof(e) == "Instance" then clearPlayer(e) end
	end
	if winner then
		msgAll(("%s won by %s - last driver standing"):format(title, nameOf(winner)))
	else
		msgAll(title .. " is over")
	end
end

-- event lifecycle ---------------------------------------------------------------------------------------------------
local function runEvent(kind: string, lead: number?)
	if phase ~= "idle" then
		return false
	end
	kind = if kind == "survival" then "survival" else "nightrun"
	lead = math.max(5, lead or cfg("LeadSeconds", CONFIG.leadSeconds))
	local night = isNight()
	local title = if kind == "survival" then "SURVIVAL" else (if night then "NIGHT RUN" else "DAY RUN")
	local C = if kind == "survival" then CONFIG.survival else CONFIG.nightRun
	local r = pickRoute(C.minLen, C.maxLen, C.spacing)
	if not r then
		warn("PattayaEvents: no route for " .. title)
		return false
	end
	phase = "gathering"
	entrants, joined = {}, {}
	ringPos = r.route[1]
	local color = if kind == "survival" then Color3.fromRGB(255, 70, 40)
		elseif night then Color3.fromRGB(200, 60, 255) else Color3.fromRGB(255, 190, 40)
	local ring = buildRing(ringPos, title, color)
	local startAt = workspace:GetServerTimeNow() + lead
	setState({Phase = "gathering", Kind = kind, Title = title, StartAt = startAt, RingPos = ringPos, Entrants = 0,
		Round = 0, Rounds = 0, Alive = 0, Color = color})
	msgAll(("%s in %d s! Follow the beacon or press J to join"):format(title, lead))
	local label = ring.PrimaryPart:FindFirstChildWhichIsA("BillboardGui"):FindFirstChild("Label") :: TextLabel
	while workspace:GetServerTimeNow() < startAt do
		for _, plr in Players:GetPlayers() do
			local c = not joined[plr] and Route.carOf(plr)
			if c and flat(c.Position - ringPos).Magnitude <= CONFIG.ringRadius then
				join(plr, "ring")
			end
		end
		local left = math.ceil(startAt - workspace:GetServerTimeNow())
		label.Text = ("%s\nJOIN HERE  %d:%02d  (%d)"):format(title, left // 60, left % 60, #entrants)
		task.wait(0.25)
	end
	ring:Destroy()
	phase = "running"
	setState({Phase = "running"})
	local humans = readyHumans(entrants)
	if #humans == 0 then
		msgAll(title .. " cancelled - nobody joined")
	else
		-- Night Run: AI only when fewer than 2 humans joined; Survival always fills up to botFill so it has rounds
		local nb = if #humans < 2 or kind == "survival" then math.max(0, CONFIG.botFill - #humans) else 0
		local bots = newBots(nb, C.botSpeed)
		local ok, err = pcall(if kind == "survival" then runSurvival else runNightRun, title, r, humans, bots)
		if not ok then
			warn("PattayaEvents: " .. tostring(err))
		end
	end
	for _, plr in entrants do
		clearPlayer(plr)
	end
	entrants, joined = {}, {}
	phase = "idle"
	setState({Phase = "idle", Kind = "", Title = "", Entrants = 0, Round = 0, Rounds = 0, Alive = 0})
	return true
end

-- force start for testing: game.ServerStorage.StartEvent:Fire("nightrun" | "survival", leadSeconds)
local startEvent = ServerStorage:FindFirstChild("StartEvent") or Instance.new("BindableEvent")
startEvent.Name = "StartEvent"
startEvent.Parent = ServerStorage
startEvent.Event:Connect(function(kind, lead)
	task.spawn(runEvent, tostring(kind or "nightrun"), tonumber(lead))
end)

-- schedule
task.spawn(function()
	local nextAt = 0
	while true do
		local interval = cfg("IntervalMinutes", CONFIG.intervalMinutes)
		local lead = cfg("LeadSeconds", CONFIG.leadSeconds)
		local now = workspace:GetServerTimeNow()
		if interval <= 0 then
			nextAt = 0
			state:SetAttribute("NextAt", 0)
		elseif nextAt == 0 then
			nextAt = now + interval * 60
			state:SetAttribute("NextAt", nextAt)
		elseif now >= nextAt - lead then
			nextAt = now + lead + interval * 60
			state:SetAttribute("NextAt", nextAt)
			if phase == "idle" then
				eventCount += 1
				local every = cfg("SurvivalEvery", CONFIG.survivalEvery)
				local kind = if every > 0 and eventCount % every == 0 then "survival" else "nightrun"
				task.spawn(runEvent, kind, lead)
			end
		end
		task.wait(1)
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	joined[plr] = nil
	local i = table.find(entrants, plr)
	if i then
		table.remove(entrants, i)
		state:SetAttribute("Entrants", #entrants)
	end
end)
