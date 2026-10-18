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
local edgePts = {} -- [edgeIndex] = {Vector2} (simplified polyline a -> b)
for ei, e in graph.edges do
	local flat = e[6]
	local seg = {}
	for i = 1, #flat, 2 do
		table.insert(seg, Vector2.new(flat[i], flat[i + 1]))
	end
	edgePts[ei] = seg
end
for ei, e in graph.edges do
	local a, b, len, tier = e[1], e[2], e[3], e[4]
	local cost = len * (if tier == 3 then SOI_COST else 1)
	table.insert(adjacency[a], {b, ei, cost, false})
	table.insert(adjacency[b], {a, ei, cost, true})
end
Route.nodes = nodes
-- the city graph comes first in graph.luau; nodes after baseNodes belong to access corridors (e.g. the road to Bira)
-- and are never picked as sprint / challenge / boss destinations, so tested courses don't change when roads are added
Route.baseNodes = graph.baseNodes or #nodes
local osmIndex = {} -- OSM node id -> graph index (when graph.luau carries osmIds)
for i, id in (graph.osmIds or {}) do
	osmIndex[id] = i
end
Route.osmIndex = osmIndex

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

-- Nearest point on any road edge to p: edge index, the point, and the distance along the edge from node a.
function Route.nearestEdge(p: Vector2): (number?, Vector2?, number, number)
	local bestD, bestE, bestQ, bestS = math.huge, nil, nil, 0
	for ei, seg in edgePts do
		local acc = 0
		for i = 1, #seg - 1 do
			local a, b = seg[i], seg[i + 1]
			local ab = b - a
			local len2 = ab:Dot(ab)
			local t = if len2 > 1e-6 then math.clamp((p - a):Dot(ab) / len2, 0, 1) else 0
			local q = a + ab * t
			local d = (p - q).Magnitude
			if d < bestD then
				bestD, bestE, bestQ, bestS = d, ei, q, acc + math.sqrt(len2) * t
			end
			acc += math.sqrt(len2)
		end
	end
	return bestE, bestQ, bestD, bestS
end

-- Dijkstra from one node, or from several seeds {[node] = starting cost}. Binary heap: the wide world has ~3,000
-- nodes, and the old linear scan was O(n^2) per route.
function Route.dijkstra(src: number | {[number]: number})
	local dist, prev, done = {}, {}, {}
	local heap = {} -- {cost, node}
	local function push(c: number, n: number)
		table.insert(heap, {c, n})
		local i = #heap
		while i > 1 do
			local p = i // 2
			if heap[p][1] <= heap[i][1] then break end
			heap[p], heap[i] = heap[i], heap[p]
			i = p
		end
	end
	local function pop()
		local top = heap[1]
		local last = table.remove(heap)
		if #heap > 0 then
			heap[1] = last
			local i = 1
			while true do
				local l, r, s = 2 * i, 2 * i + 1, i
				if l <= #heap and heap[l][1] < heap[s][1] then s = l end
				if r <= #heap and heap[r][1] < heap[s][1] then s = r end
				if s == i then break end
				heap[s], heap[i] = heap[i], heap[s]
				i = s
			end
		end
		return top
	end
	if type(src) == "table" then
		for n, d in src do dist[n] = d; push(d, n) end
	else
		dist[src] = 0
		push(0, src)
	end
	while #heap > 0 do
		local top = pop()
		local bd, best = top[1], top[2]
		if done[best] or bd > (dist[best] or math.huge) then
			continue
		end
		done[best] = true
		for _, link in adjacency[best] do
			local m, cost = link[1], link[3]
			local nd = bd + cost
			if nd < (dist[m] or math.huge) then
				dist[m] = nd
				prev[m] = {best, link}
				push(nd, m)
			end
		end
	end
	return dist, prev
end

function Route.polylineOf(prev, src: number, dst: number): {Vector2}
	local chain = {}
	local n = dst
	while n ~= src and prev[n] do -- with several seeds the chain ends at whichever seed reached dst
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

-- A point-to-point race route from the junction nearest `pos` (preferring ones ahead along `look`): random
-- destination minLen..maxLen away by road, checkpoints every `spacing` ending at the destination.
-- With `rng` (a Random) the pick is repeatable: the same start and seed give the same course (Road Fight bosses).
-- Returns {cps = {Vector3}, dirs = {Vector3}, route = {Vector3}, length} or nil, reason.
function Route.pointToPoint(pos: Vector3, look: Vector3, minLen: number, maxLen: number, spacing: number, rng: Random?)
	local src = Route.nearestNode(Route.toLocal(pos), 400, Vector2.new(look.X, look.Z))
	if not src then
		return nil, "No road nearby"
	end
	local dist, prev = Route.dijkstra(src)
	local candidates = {}
	for n, d in dist do
		if d >= minLen and d <= maxLen and n <= Route.baseNodes then
			table.insert(candidates, n)
		end
	end
	if #candidates == 0 then
		return nil, "No route from here"
	end
	table.sort(candidates) -- table order is not stable between servers
	local dst = candidates[if rng then rng:NextInteger(1, #candidates) else math.random(1, #candidates)]
	local pts = Route.polylineOf(prev, src, dst)
	local cps, dirs = {}, {}
	local prevPt = nodes[src]
	for _, c in Route.along(pts, spacing) do
		local dir = (c - prevPt)
		dir = if dir.Magnitude > 0.1 then dir.Unit else Vector2.new(1, 0)
		table.insert(cps, Route.toWorld(c))
		table.insert(dirs, Vector3.new(dir.X, 0, dir.Y))
		prevPt = c
	end
	local route = {}
	for _, q in pts do
		table.insert(route, Route.toWorld(q))
	end
	return {cps = cps, dirs = dirs, route = route, length = Route.length(pts)}
end

-- Route from a world position to a graph node (by OSM id or graph index): the polyline in world coordinates and its
-- length, or nil, reason. Used by the GPS (e.g. the way to the Bira Circuit).
function Route.routeTo(pos: Vector3, look: Vector3?, target: number, isOsmId: boolean?)
	local dst = if isOsmId then osmIndex[target] else target
	if not dst then
		return nil, "Unknown destination"
	end
	local p = Route.toLocal(pos)
	local ei, q, d, s = Route.nearestEdge(p)
	if not ei or d > 150 then
		return nil, "No road nearby"
	end
	local e = graph.edges[ei]
	local a, b, len = e[1], e[2], e[3]
	-- seeds: the edge's far end(s); the start of the polyline is the projection point q
	local seeds = {}
	local tail = {} -- polyline from q to each seed, chosen after the search
	local seg = edgePts[ei]
	local function along(fromS: number, toS: number): {Vector2} -- edge vertices between two arc positions, in travel order
		local pos = {0}
		for i = 1, #seg - 1 do
			pos[i + 1] = pos[i] + (seg[i + 1] - seg[i]).Magnitude
		end
		local out = {}
		if toS >= fromS then
			for i = 1, #seg do
				if pos[i] > fromS + 0.01 and pos[i] <= toS + 0.01 then table.insert(out, seg[i]) end
			end
		else
			for i = #seg, 1, -1 do
				if pos[i] < fromS - 0.01 and pos[i] >= toS - 0.01 then table.insert(out, seg[i]) end
			end
		end
		return out
	end
	local polyLen = 0
	for i = 1, #seg - 1 do polyLen += (seg[i + 1] - seg[i]).Magnitude end
	seeds[b] = math.max(polyLen - s, 0)
	tail[b] = along(s, polyLen)
	local oneway = true
	for _, link in adjacency[b] do
		if link[1] == a and link[2] == ei then oneway = false end
	end
	if not oneway then
		seeds[a] = s
		tail[a] = along(s, 0)
	end
	if dst == a or dst == b then
		local pts = {q}
		for _, x in tail[dst] do table.insert(pts, x) end
		local route = {}
		for _, x in pts do table.insert(route, Route.toWorld(x)) end
		return {route = route, length = Route.length(pts), nodeIndex = dst}
	end
	local dist, prev = Route.dijkstra(seeds)
	if not dist[dst] then
		return nil, "No road to the destination"
	end
	-- which seed did the best path start from? follow prev back to a node without prev
	local n = dst
	while prev[n] do n = prev[n][1] end
	local pts = {q}
	for _, x in tail[n] or {} do table.insert(pts, x) end
	for i, x in Route.polylineOf(prev, n, dst) do
		if i > 1 then table.insert(pts, x) end
	end
	local route = {}
	for _, x in pts do table.insert(route, Route.toWorld(x)) end
	return {route = route, length = Route.length(pts), nodeIndex = dst}
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

-- true when the player is already in a race, sprint, job or circuit session
function Route.busy(plr: Player): boolean
	return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
		or plr:GetAttribute("JobActive") == true or plr:GetAttribute("CircuitActive") == true
end

return Route
