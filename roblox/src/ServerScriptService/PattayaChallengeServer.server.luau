-- Street Challenge (RayCity's 1-on-1 on the live streets, up to 4 cars). While driving, press C near another driver:
-- they get 10 s to accept. The server lays a point-to-point route on the real road graph where the cars are, puts
-- them side by side at its start, counts down 3-2-1 and races them through the checkpoints; first to the last one
-- wins. If no other player is near, a street racer (AI) pulls up and races you instead.
-- Rules: checkpoints in order (26 studs), 180 s limit, the rest are out 60 s after the winner, leaving the car
-- forfeits, the 260 studs/s teleport check applies. Trailing drivers get extra nitro per checkpoint (RayCity
-- catch-up). The race reuses the Street Sprint client (SprintUpdate) for gates, GPS arrow and HUD.
-- The race engine itself (grid, countdown, checkpoints, AI racers, standings, payout) lives in
-- ServerStorage.PattayaStreetRace and is shared with the Night Run / Survival events.
local Players = game:GetService("Players")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
if not (data and data:FindFirstChild("graph") and workspace:FindFirstChild("PattayaWorld")) then
	return
end
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()
local StreetRace = require(ServerStorage:WaitForChild("PattayaStreetRace")) -- the race engine (moved there)

local CHALLENGE_RANGE = 150
local INVITE_TIME = 10
local CP_SPACING = StreetRace.CP_SPACING
local CAR_Y = StreetRace.CAR_Y

local remote = StreetRace.remote
local ChallengeRequest = remote("ChallengeRequest") -- client -> server
local ChallengeReply = remote("ChallengeReply") -- client -> server (accept: boolean)
local ChallengeMsg = StreetRace.ChallengeMsg -- server -> client: ("invite", fromName, seconds) / ("msg", text) /
-- ("countdown", goAt) / ("standings", {names}, myPlace)
local SprintUpdate = StreetRace.SprintUpdate

local invites = {} -- [target] = {from, expires}
local lastRequest = {} -- [player] = time

local msg = StreetRace.msg
local botModel = StreetRace.botModel
local playerPart = StreetRace.playerPart
local botPart = StreetRace.botPart
local inRace = StreetRace.inRace

local function flat(v: Vector3): Vector3
	return Vector3.new(v.X, 0, v.Z)
end

ChallengeRequest.OnServerEvent:Connect(function(plr: Player)
	local now = os.clock()
	if now - (lastRequest[plr] or 0) < 3 then
		return
	end
	lastRequest[plr] = now
	local chassis = Route.carOf(plr)
	if not chassis or Route.busy(plr) or inRace(plr) then
		return
	end
	-- nearest other driver who is free
	local target, best = nil, CHALLENGE_RANGE
	for _, other in Players:GetPlayers() do
		local oc = other ~= plr and Route.carOf(other)
		if oc and not Route.busy(other) and not inRace(other) and not invites[other] then
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
	StreetRace.startRace({playerPart(plr), bot})
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
	if not (Route.carOf(from) and Route.carOf(plr)) or Route.busy(from) or Route.busy(plr) or inRace(from) or inRace(plr) then
		msg(plr, "Challenge no longer possible")
		msg(from, "Challenge no longer possible")
		return
	end
	StreetRace.startRace({playerPart(from), playerPart(plr)})
end)

-- Road Fight (RayCity single-player mode): a Road Master waits at a real spot in each district (ServerStorage.
-- PattayaData.roadfight, generated). Beat them in order, South -> Central -> North; then the Road King unlocks.
-- Stop in a boss's red ring and press E. Each boss races its own fixed course, faster than the last.
-- Wins are saved (Player attribute RoadFight, bit per boss) and give titles: "Road Fighter" after the three Road
-- Masters, "Road King" after the King. First wins pay full, repeat wins a third.
local RoadFightRequest = remote("RoadFightRequest")
local FIRST_MONEY = {300, 400, 500, 1000}
local FIRST_EXP = {150, 200, 250, 500}
local bossDefs = if data:FindFirstChild("roadfight") then require(data.roadfight) else {}
local bosses = {} -- [id] = {def, pos, dir, folder, display, busy}
local byOrder = {}
local rfFolder = workspace.PattayaWorld:FindFirstChild("RoadFight")
if rfFolder then
	rfFolder:Destroy()
end
rfFolder = Instance.new("Folder")
rfFolder.Name = "RoadFight"
rfFolder.Parent = workspace.PattayaWorld

local function beaten(plr: Player, order: number): boolean
	return bit32.btest(plr:GetAttribute("RoadFight") or 0, bit32.lshift(1, order - 1))
end

for _, d in bossDefs do
	local pos = Route.toWorld(Vector2.new(d.x, d.z), 1)
	local dir = Vector3.new(d.dx, 0, d.dz)
	local m = Instance.new("Model")
	m.Name = d.id
	m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	m:SetAttribute("Order", d.order)
	m:SetAttribute("Boss", d.boss)
	m:SetAttribute("Label", d.label)
	m:SetAttribute("Source", d.source)
	local ring = Instance.new("Part")
	ring.Name = "Ring"
	ring.Shape = Enum.PartType.Cylinder
	ring.Anchored, ring.CanCollide, ring.CanQuery, ring.CanTouch = true, false, false, false
	ring.Size = Vector3.new(0.3, 36, 36)
	ring.CFrame = CFrame.new(pos + Vector3.new(0, 0.2, 0)) * CFrame.Angles(0, 0, math.rad(90))
	ring.Material = Enum.Material.Neon
	ring.Color = if d.order == 4 then Color3.fromRGB(255, 200, 40) else Color3.fromRGB(230, 30, 40)
	ring.Transparency = 0.6
	ring.Parent = m
	local pole = Instance.new("Part")
	pole.Name = "Pole"
	pole.Anchored, pole.CanCollide, pole.CanQuery, pole.CanTouch = true, false, false, false
	pole.Size = Vector3.new(1, 22, 1)
	pole.Position = pos + Vector3.new(d.kx, 0, d.kz) * 12 + Vector3.new(0, 11, 0)
	pole.Material = Enum.Material.Neon
	pole.Color = ring.Color
	pole.Parent = m
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(260, 64)
	bb.StudsOffset = Vector3.new(0, 14, 0)
	bb.MaxDistance = 900
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = ring.Color
	t.TextStrokeTransparency = 0.1
	t.Text = d.label .. "\n" .. d.boss
	t.Parent = bb
	bb.Parent = pole
	m.PrimaryPart = ring
	m.Parent = rfFolder
	local b = {def = d, pos = pos, dir = dir, folder = m, busy = false}
	bosses[d.id] = b
	byOrder[d.order] = b
end

-- the boss's car waits parked in front of its ring (a copy of a grid car, so wait for RaceCarServer to make them)
task.spawn(function()
	for _ = 1, 60 do
		local any = false
		for _, m in workspace:GetChildren() do
			if m:GetAttribute("RaceCar") then any = true break end
		end
		if any then break end
		task.wait(0.5)
	end
	for _, b in bosses do
		local car = botModel(b.def.boss, b.def.car)
		if car then
			local at = b.pos + b.dir * 14 + Vector3.new(0, CAR_Y - 1, 0)
			local offset = car.PrimaryPart.CFrame:ToObjectSpace(car:GetPivot())
			car:PivotTo(CFrame.lookAt(at, at + b.dir) * offset)
			car.Parent = b.folder
			b.display = car
		end
	end
end)

local function onBossResult(p, race, reason: string?)
	local b, plr = race.data, p.plr
	local d = b.def
	if p.place == 1 then
		local first = not beaten(plr, d.order)
		plr:SetAttribute("RoadFight", bit32.bor(plr:GetAttribute("RoadFight") or 0, bit32.lshift(1, d.order - 1)))
		local money = math.floor(FIRST_MONEY[d.order] / (if first then 1 else 3))
		local exp = math.floor(FIRST_EXP[d.order] / (if first then 1 else 3))
		local ls = plr:FindFirstChild("leaderstats")
		local title = ls and ls:FindFirstChild("Title") and ls.Title.Value or ""
		if d.order == 4 then
			Progress.SetTitle(plr, "Road King")
		elseif title == "" and beaten(plr, 1) and beaten(plr, 2) and beaten(plr, 3) then
			Progress.SetTitle(plr, "Road Fighter")
		end
		Progress.Award(plr, money, exp, "Road Fight: beat " .. d.boss)
		local nextBoss = byOrder[d.order + 1]
		SprintUpdate:FireClient(plr, "finish", {time = p.time, length = race.length, money = money, exp = exp,
			text = ("YOU BEAT %s!  %.2f s"):format(string.upper(d.boss), p.time)})
		if first then
			msg(plr, if nextBoss then ("Unlocked: %s - %s"):format(nextBoss.def.label, nextBoss.def.boss)
				elseif d.order == 4 then "You are the ROAD KING of Pattaya!" else "")
		end
	elseif p.place then
		local exp = math.floor(race.length / 80)
		Progress.Award(plr, 0, exp, "Road Fight: lost to " .. d.boss)
		SprintUpdate:FireClient(plr, "finish", {time = p.time, length = race.length, money = 0, exp = exp,
			text = ("%s wins. Come back faster."):format(d.boss)})
	elseif not p.out then
		SprintUpdate:FireClient(plr, "stop", reason or "Did not finish")
	end
end

RoadFightRequest.OnServerEvent:Connect(function(plr: Player, id)
	local b = bosses[id]
	local chassis = Route.carOf(plr)
	if not (b and chassis) or Route.busy(plr) or inRace(plr) then
		return
	end
	local v = chassis.AssemblyLinearVelocity
	if flat(chassis.Position - b.pos).Magnitude > 22 or Vector3.new(v.X, 0, v.Z).Magnitude > 30 then
		return
	end
	for k = 1, b.def.order - 1 do
		if not beaten(plr, k) then
			msg(plr, ("Locked: beat %s (%s) first"):format(byOrder[k].def.boss, byOrder[k].def.district))
			return
		end
	end
	if b.busy then
		msg(plr, b.def.boss .. " is racing someone else. Wait a moment.")
		return
	end
	local part = botPart(b.def.vmax, b.def.boss, b.def.car, b.def.grip)
	if not part then
		return
	end
	b.busy = true
	if b.display then
		b.display.Parent = nil
	end
	msg(plr, ('%s: "%s"'):format(b.def.boss, b.def.line))
	-- a Road Fight boss always races its own course (same start and seed every time, so it can be learned)
	StreetRace.startRace({playerPart(plr), part}, {
		title = "ROAD FIGHT",
		data = b,
		route = function()
			return Route.pointToPoint(b.pos, b.dir, b.def.courseMin, b.def.courseMax, CP_SPACING,
				Random.new(b.def.order * 7919))
		end,
		onResult = onBossResult,
		onEnd = function()
			b.busy = false
			task.delay(4, function() -- the boss parks at its spot again
				if b.display then b.display.Parent = b.folder end
			end)
		end,
	})
	if not inRace(plr) then -- no course from here: put things back
		b.busy = false
		part.model:Destroy()
		if b.display then
			b.display.Parent = b.folder
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	invites[plr] = nil
	lastRequest[plr] = nil
end)
