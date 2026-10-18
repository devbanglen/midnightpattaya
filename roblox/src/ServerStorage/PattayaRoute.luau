-- Route finding on the generated Pattaya road graph (ServerStorage.PattayaData.graph): shared by Street Sprint and
-- taxi/delivery jobs. Coordinates are map-local (x, z) Vector2s; add PattayaBuilder.ORIGIN for world positions.
local ServerStorage = game:GetService("ServerStorage")

local Route = {}

Route.ORIGIN = Vector3.new(20000, 0, 0) -- PattayaBuilder.ORIGIN
local SOI_COST = 1.6

local graph = require(ServerStorage:WaitForChild("PattayaData"):WaitForChild("graph"))

-- nodes[i] = Vector2, adjacency[i] = {{to, edgeIndex, cost, reversed}}
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
Route.nodes = nodes

function Route.toLocal(p: Vector3): Vector2
	return Vector2.new(p.X - Route.ORIGIN.X, p.Z - Route.ORIGIN.Z)
end

function Route.toWorld(p: Vector2, y: number?): Vector3
	return Vector3.new(p.X + Route.ORIGIN.X, y or 1, p.Y + Route.ORIGIN.Z)
end

-- nearest node within maxDist; with a look direction, nodes behind count 2.5x as far
function Route.nearestNode(p: Vector2, maxDist: number, look: Vector2?): number?
	local best, bs = nil, math.huge
	for i, n in nodes do
		local d = (n - p).Magnitude
		local score = d
		if look and (n - p):Dot(look) <= 0 then
			score = d * 2.5
		end
		if score < bs and d < maxDist then
			best, bs = i, score
		end
	end
	return best
end

function Route.dijkstra(src: number)
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

function Route.polylineOf(prev, src: number, dst: number): {Vector2}
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
	if #pts == 0 then
		pts = {nodes[src]}
	end
	return pts
end

function Route.length(pts: {Vector2}): number
	local length = 0
	for i = 1, #pts - 1 do length += (pts[i + 1] - pts[i]).Magnitude end
	return length
end

-- points every `spacing` along the polyline, the last one exactly at its end
function Route.along(pts: {Vector2}, spacing: number): {Vector2}
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

-- distance from point c to the segment a-b on the ground plane (a car's path since the last sample)
function Route.segDist(a: Vector3, b: Vector3, c: Vector3): number
	local ab = Vector3.new(b.X - a.X, 0, b.Z - a.Z)
	local ac = Vector3.new(c.X - a.X, 0, c.Z - a.Z)
	local len2 = ab:Dot(ab)
	local t = if len2 > 1e-6 then math.clamp(ac:Dot(ab) / len2, 0, 1) else 0
	return (ac - ab * t).Magnitude
end

-- the chassis of the race car this player is driving, if any
function Route.carOf(plr: Player): BasePart?
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

-- true when the player is already in a race, sprint or job
function Route.busy(plr: Player): boolean
	return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
		or plr:GetAttribute("JobActive") == true
end

return Route
