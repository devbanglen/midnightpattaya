-- GPS destinations (RayCity's click-to-navigate): the client asks for a route to a named destination, the server
-- finds it on the road graph (ServerStorage.PattayaRoute, which includes the Bira access corridor once the
-- corridor graph is installed) and sends the polyline back. Refreshed every few seconds while set, cleared on
-- arrival. Pure guidance: nothing is judged here.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
if not (data and data:FindFirstChild("graph") and workspace:FindFirstChild("PattayaWorld")) then
	return
end
local Route = require(ServerStorage:WaitForChild("PattayaRoute"))

-- id -> {label, osm = OSM node id of the road junction to route to, arrive = world point that counts as arrival}
local DESTINATIONS = {
	{id = "bira", label = "Bira Circuit", osm = 1457068485, arriveRadius = 120},
	{id = "central", label = "Central Pattaya (start)", osm = 423748313, arriveRadius = 80},
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
local GPSRequest = remote("GPSRequest") -- client -> server: destination id or nil (clear)
local GPSUpdate = remote("GPSUpdate") -- server -> client: "route" {id, label, route, length} | "arrived" label | "clear" | "list" {...}

local active = {} -- [player] = {dest, at}
local REFRESH = 4

local function available()
	local list = {}
	for _, d in DESTINATIONS do
		if Route.osmIndex[d.osm] then
			table.insert(list, {id = d.id, label = d.label})
		end
	end
	return list
end

local function send(plr: Player, dest)
	local chassis = Route.carOf(plr)
	local pos = if chassis then chassis.Position else (plr.Character and plr.Character:GetPivot().Position)
	if not pos then
		return
	end
	local r, why = Route.routeTo(pos, chassis and chassis.CFrame.LookVector or nil, dest.osm, true)
	if not r then
		GPSUpdate:FireClient(plr, "clear", why)
		active[plr] = nil
		return
	end
	local goal = r.route[#r.route]
	if (Vector3.new(goal.X - pos.X, 0, goal.Z - pos.Z)).Magnitude < dest.arriveRadius then
		GPSUpdate:FireClient(plr, "arrived", dest.label)
		active[plr] = nil
		return
	end
	GPSUpdate:FireClient(plr, "route", {id = dest.id, label = dest.label, route = r.route, length = r.length})
end

GPSRequest.OnServerEvent:Connect(function(plr: Player, id)
	if id == "list" then
		GPSUpdate:FireClient(plr, "list", available())
		return
	end
	if id == nil then
		active[plr] = nil
		GPSUpdate:FireClient(plr, "clear")
		return
	end
	for _, d in DESTINATIONS do
		if d.id == id and Route.osmIndex[d.osm] then
			active[plr] = {dest = d, at = 0}
			return
		end
	end
	GPSUpdate:FireClient(plr, "clear", "Destination not on the map yet")
end)

RunService.Heartbeat:Connect(function()
	local now = os.clock()
	for plr, st in active do
		if not plr.Parent then
			active[plr] = nil
		elseif now - st.at >= REFRESH then
			st.at = now
			send(plr, st.dest)
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	active[plr] = nil
end)
