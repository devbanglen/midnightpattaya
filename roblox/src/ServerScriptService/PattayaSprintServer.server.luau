-- Street Sprint (RayCity "challenge on the live streets"): while driving, the player requests a sprint (H key /
-- mobile button). The server picks a point-to-point route on the real road graph starting at the nearest junction
-- ahead, 1,500-2,600 studs long and preferring main roads, places checkpoints every ~250 studs and times the run.
-- Uses ServerStorage.PattayaData.graph (generated) and ServerStorage.PattayaProgress (money/EXP).
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
if not (data and data:FindFirstChild("graph") and workspace:FindFirstChild("PattayaWorld")) then
	return
end
local graph = require(data.graph)
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()

local ORIGIN = Vector3.new(20000, 0, 0) -- PattayaBuilder.ORIGIN
local MIN_LEN, MAX_LEN = 1500, 2600
local CP_SPACING = 250
local TIME_LIMIT = 150
local SOI_COST = 1.6

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

-- graph: nodes[i] = Vector2, adjacency[i] = {{to, edgeIndex, cost, reversed}}
local nodes = {}
for i = 1, #graph.nodes, 2 do
	table.insert(nodes, Vector2.new(graph.nodes[i], graph.nodes[i + 1]))
end
local adjacency = {}
for i = 1, #nodes do
	adjacency[i] = {}
end
for ei, e in graph.edges do
	local a, b, len, tier = e[1], e[2], e[3], e[4]
	local cost = len * (if tier == 3 then SOI_COST else 1)
	table.insert(adjacency[a], {b, ei, cost, false})
	table.insert(adjacency[b], {a, ei, cost, true})
end

local function dijkstra(src: number)
	local dist, prev, done = {[src] = 0}, {}, {}
	while true do
		local best, bd = nil, math.huge
		for n, d in dist do
			if not done[n] and d < bd then
				best, bd = n, d
			end
		end
		if not best then
			break
		end
		done[best] = true
		for _, link in adjacency[best] do
			local m, cost = link[1], link[3]
			local nd = bd + cost
			if nd < (dist[m] or math.huge) then
				dist[m] = nd
				prev[m] = {best, link}
			end
		end
	end
	return dist, prev
end

local function polylineOf(prev, src: number, dst: number): {Vector2}
	local chain = {}
	local n = dst
	while n ~= src do
		local p = prev[n]
		table.insert(chain, 1, p[2])
		n = p[1]
	end
	local pts = {}
	for _, link in chain do
		local flat = graph.edges[link[2]][6]
		local seg = {}
		for i = 1, #flat, 2 do
			table.insert(seg, Vector2.new(flat[i], flat[i + 1]))
		end
		if link[4] then -- traversed b -> a
			local r = {}
			for i = #seg, 1, -1 do table.insert(r, seg[i]) end
			seg = r
		end
		for i, p in seg do
			if i > 1 or #pts == 0 then table.insert(pts, p) end
		end
	end
	return pts
end

local function along(pts: {Vector2}, spacing: number): {Vector2}
	local out = {}
	local carry = spacing
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = (b - a).Magnitude
		local s = carry
		while s <= len do
			table.insert(out, a:Lerp(b, s / len))
			s += spacing
		end
		carry = s - len
	end
	if #out == 0 or (out[#out] - pts[#pts]).Magnitude > spacing * 0.4 then
		table.insert(out, pts[#pts])
	else
		out[#out] = pts[#pts] -- finish exactly at the end node
	end
	return out
end

local active = {} -- [player] = {cps = {Vector3}, dirs = {Vector3}, next, start, length}

local function carOf(plr: Player): BasePart?
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

local function stop(plr: Player, reason: string)
	if active[plr] then
		active[plr] = nil
		plr:SetAttribute("SprintActive", false)
		SprintUpdate:FireClient(plr, "stop", reason)
	end
end

-- distance from point c to the segment a-b on the ground plane (the car's path since the last sample)
local function segDist(a: Vector3, b: Vector3, c: Vector3): number
	local ab = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
	local ac = Vector3.new(c.X - a.X, 0, c.Z - a.Z)
	local len2 = ab:Dot(ab)
	local t = if len2 > 1e-6 then math.clamp(ac:Dot(ab) / len2, 0, 1) else 0
	return (ac - ab * t).Magnitude
end
local MAX_SPEED = 260

RequestSprint.OnServerEvent:Connect(function(plr: Player)
	local chassis = carOf(plr)
	if not chassis or active[plr] or plr:GetAttribute("RaceState") == "racing" then
		return
	end
	local p = Vector2.new(chassis.Position.X - ORIGIN.X, chassis.Position.Z - ORIGIN.Z)
	local look = Vector2.new(chassis.CFrame.LookVector.X, chassis.CFrame.LookVector.Z)
	-- nearest junction, preferring ones ahead of the car
	local src, sd = nil, math.huge
	for i, n in nodes do
		local d = (n - p).Magnitude
		local ahead = (n - p):Dot(look) > 0
		local score = d * (if ahead then 1 else 2.5)
		if score < sd and d < 400 then
			src, sd = i, score
		end
	end
	if not src then
		SprintUpdate:FireClient(plr, "stop", "No road nearby")
		return
	end
	local dist, prev = dijkstra(src)
	local candidates = {}
	for n, d in dist do
		if d >= MIN_LEN and d <= MAX_LEN then
			table.insert(candidates, n)
		end
	end
	if #candidates == 0 then
		SprintUpdate:FireClient(plr, "stop", "No route from here")
		return
	end
	local dst = candidates[math.random(1, #candidates)]
	local pts = polylineOf(prev, src, dst)
	local cps2 = along(pts, CP_SPACING)
	local cps, dirs = {}, {}
	local length = 0
	for i = 1, #pts - 1 do length += (pts[i + 1] - pts[i]).Magnitude end
	local prevPt = nodes[src]
	for _, c in cps2 do
		local dir = (c - prevPt)
		dir = if dir.Magnitude > 0.1 then dir.Unit else Vector2.new(1, 0)
		table.insert(cps, Vector3.new(c.X + ORIGIN.X, 1, c.Y + ORIGIN.Z))
		table.insert(dirs, Vector3.new(dir.X, 0, dir.Y))
		prevPt = c
	end
	local route = {}
	for _, q in pts do
		table.insert(route, Vector3.new(q.X + ORIGIN.X, 1, q.Y + ORIGIN.Z))
	end
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
		local hitCp = segDist(st.last, pos, c) < 26
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
end)
