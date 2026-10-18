-- Street Sprint (RayCity "challenge on the live streets"): while driving, the player requests a sprint (H key /
-- mobile button). The server picks a point-to-point route on the real road graph starting at the nearest junction
-- ahead, 1,500-2,600 studs long and preferring main roads, places checkpoints every ~250 studs and times the run.
-- Uses ServerStorage.PattayaRoute (road graph), ServerStorage.PattayaProgress (money/EXP).
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

local MIN_LEN, MAX_LEN = 1500, 2600
local CP_SPACING = 250
local TIME_LIMIT = 150
local MAX_SPEED = 260

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
local RequestSprint = remote("RequestSprint")
local SprintUpdate = remote("SprintUpdate")
local NitroBonus = remote("NitroBonus")

local active = {} -- [player] = {cps = {Vector3}, dirs = {Vector3}, next, start, length}
local carOf = Route.carOf
-- request rate limit: at most one RequestSprint per REQUEST_GAP s per player (extras are dropped), and never a second
-- route search while one is running for that player (pointToPoint runs a Dijkstra over the whole road graph)
local REQUEST_GAP = 0.5
local lastRequest: {[Player]: number} = {}
local routing: {[Player]: boolean} = {}

local function stop(plr: Player, reason: string)
	if active[plr] then
		active[plr] = nil
		plr:SetAttribute("SprintActive", false)
		if plr.Parent then -- the Heartbeat also stops runs of players who already left
			SprintUpdate:FireClient(plr, "stop", reason)
		end
	end
end

RequestSprint.OnServerEvent:Connect(function(plr: Player)
	local clock = os.clock()
	if routing[plr] or clock - (lastRequest[plr] or -math.huge) < REQUEST_GAP then
		return
	end
	lastRequest[plr] = clock
	local chassis = carOf(plr)
	if not chassis or active[plr] or Route.busy(plr) then
		return
	end
	routing[plr] = true
	local okR, r, why = pcall(Route.pointToPoint, chassis.Position, chassis.CFrame.LookVector, MIN_LEN, MAX_LEN,
		CP_SPACING)
	routing[plr] = nil
	if not okR then
		warn("PattayaSprintServer: route search failed:", r)
		return
	end
	if not r then
		SprintUpdate:FireClient(plr, "stop", why)
		return
	end
	local cps, dirs, route, length = r.cps, r.dirs, r.route, r.length
	local now0 = workspace:GetServerTimeNow()
	active[plr] = {cps = cps, dirs = dirs, next = 1, start = now0, length = length, last = chassis.Position,
		lastCpAt = now0, lastCpPos = chassis.Position}
	plr:SetAttribute("SprintActive", true)
	SprintUpdate:FireClient(plr, "start", {checkpoints = cps, dirs = dirs, route = route, length = length,
		start = active[plr].start, timeLimit = TIME_LIMIT})
end)

RunService.Heartbeat:Connect(function()
	local now = workspace:GetServerTimeNow()
	for plr, st in active do
		local chassis = carOf(plr)
		if not chassis or not plr.Parent then
			stop(plr, "Left the car")
			continue
		end
		if now - st.start > TIME_LIMIT then
			stop(plr, "Time up")
			continue
		end
		if plr:GetAttribute("RaceState") == "racing" then
			stop(plr, "Joined the loop race")
			continue
		end
		-- a checkpoint counts when the car's path since the last sample passes within 26 studs of its centre (roads
		-- are 26-78 studs wide), so a slow network update can't jump it
		local c = st.cps[st.next]
		local pos = chassis.Position
		local hitCp = Route.segDist(st.last, pos, c) < 26
		st.last = pos
		if hitCp then
			local dt = math.max(now - st.lastCpAt, 1 / 60)
			if (pos - st.lastCpPos).Magnitude / dt > MAX_SPEED then
				stop(plr, "Run invalid (moved too fast)")
				continue
			end
			st.lastCpAt, st.lastCpPos = now, pos
			NitroBonus:FireClient(plr, 20)
			if st.next == #st.cps then
				local t = now - st.start
				active[plr] = nil
				plr:SetAttribute("SprintActive", false)
				-- pay by distance, bonus for average speed above 90 studs/s
				local avg = st.length / t
				local money = math.floor(st.length / 20 + math.max(0, avg - 90) * 2)
				local exp = math.floor(st.length / 40)
				Progress.Award(plr, money, exp, "Street Sprint")
				SprintUpdate:FireClient(plr, "finish", {time = t, length = st.length, money = money, exp = exp})
			else
				st.next += 1
				SprintUpdate:FireClient(plr, "next", st.next)
			end
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	active[plr] = nil
	lastRequest[plr] = nil
	routing[plr] = nil
end)
