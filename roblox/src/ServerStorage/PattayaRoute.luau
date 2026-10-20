-- Route finding on the generated Pattaya road graph (ServerStorage.PattayaData.graph): shared by Street Sprint,
-- taxi/delivery jobs and the GPS. Coordinates are map-local (x, z) Vector2s; add PattayaBuilder.ORIGIN for world
-- positions.
--
-- Getting onto the graph (docs/ROUTING.md): a point off the graph (a job stand, a car, a paddock) joins it at the
-- nearest point ON a road edge (projection onto the edge polyline), never by a straight line to the nearest junction:
-- that line used to cross whole building blocks (Central Festival stand -> a junction 149 studs away through two
-- buildings). Route.snap prefers an edge whose road slab contains the point (projection distance <= half the road
-- width + SNAP_MARGIN) and whose straight connector does not cross a building footprint (the chunk data modules in
-- ServerStorage). Job stands get a fixed "anchor" node on their road edge (Route.anchor), which
-- Route.nearestNode(standPos, maxDist) returns when it is called without a look direction at a stand position, so
-- PattayaJobsServer's nearestNode -> dijkstra -> polylineOf keeps working unchanged and starts on the stand's road.
local ServerStorage = game:GetService("ServerStorage")

local Route = {}

Route.ORIGIN = Vector3.new(20000, 0, 0) -- PattayaBuilder.ORIGIN
local SOI_COST = 1.6
local SNAP_MARGIN = 8 -- studs beyond half the road width that still count as "on that road" (kerb, ring, sidewalk)
local ANCHOR_EPS = 1e-3 -- extra cost per anchor link: a path through an anchor never beats the original edge
local STAND_MATCH = 1 -- studs: nearestNode at a stand's own position returns the stand's anchor
local CHUNK = 512 -- chunk size of the exported map data (manifest.chunkSize)
local BUILDING_REACH = 300 -- studs: the largest building half-diagonal (287) rounded up, for the chunk search
local BUILDING_INSET = 1 -- studs: a connector grazing a footprint's edge does not count as crossing it
local DATA_FOLDERS = {"PattayaData", "PattayaDataWide", "PattayaDataCorridor"}
local SNAP_TRIES = 32 -- Route.snap: building checks on the nearest edges at most (bounds the cost of a boxed-in point)

local dataFolder = ServerStorage:WaitForChild("PattayaData")
local graph = require(dataFolder:WaitForChild("graph"))

-- nodes[i] = Vector2, adjacency[i] = {{to, edgeIndex, cost, reversed}}
local nodes = {}
for i = 1, #graph.nodes, 2 do
	table.insert(nodes, Vector2.new(graph.nodes[i], graph.nodes[i + 1]))
end
local adjacency = {}
for i = 1, #nodes do
	adjacency[i] = {}
end
local edgePts = {} -- [edgeIndex] = {Vector2} (simplified polyline a -> b); anchor pieces are appended after the graph's
local edgeCost = {} -- [edgeIndex] = Dijkstra cost of the whole graph edge
for ei, e in graph.edges do
	local flat = e[6]
	local seg = {}
	for i = 1, #flat, 2 do
		table.insert(seg, Vector2.new(flat[i], flat[i + 1]))
	end
	edgePts[ei] = seg
end
local graphEdges = #graph.edges -- edges 1..graphEdges are real roads; later indices are anchor pieces
for ei, e in graph.edges do
	local a, b, len, tier = e[1], e[2], e[3], e[4]
	local cost = len * (if tier == 3 then SOI_COST else 1)
	edgeCost[ei] = cost
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

local anchorPos: {[number]: Vector2} = {} -- anchor node index (> #nodes) -> position on its edge
local function nodePos(n: number): Vector2
	return nodes[n] or anchorPos[n]
end
Route.nodePos = nodePos

function Route.toLocal(p: Vector3): Vector2
	return Vector2.new(p.X - Route.ORIGIN.X, p.Z - Route.ORIGIN.Z)
end

function Route.toWorld(p: Vector2, y: number?): Vector3
	return Vector3.new(p.X + Route.ORIGIN.X, y or 1, p.Y + Route.ORIGIN.Z)
end

-- polyline helpers ---------------------------------------------------------------------------------------------------
local function arcPositions(seg: {Vector2}): {number}
	local pos = {0}
	for i = 1, #seg - 1 do
		pos[i + 1] = pos[i] + (seg[i + 1] - seg[i]).Magnitude
	end
	return pos
end

local function pointAtArc(seg: {Vector2}, pos: {number}, s: number): Vector2
	for i = 1, #seg - 1 do
		if s <= pos[i + 1] or i == #seg - 1 then
			local l = pos[i + 1] - pos[i]
			local t = if l > 1e-9 then math.clamp((s - pos[i]) / l, 0, 1) else 0
			return seg[i]:Lerp(seg[i + 1], t)
		end
	end
	return seg[1]
end

-- the piece of a polyline between arc positions s0 < s1, both ends included
local function subPolyline(seg: {Vector2}, pos: {number}, s0: number, s1: number): {Vector2}
	local out = {pointAtArc(seg, pos, s0)}
	for i = 1, #seg do
		if pos[i] > s0 + 0.01 and pos[i] < s1 - 0.01 then
			table.insert(out, seg[i])
		end
	end
	table.insert(out, pointAtArc(seg, pos, s1))
	return out
end

-- buildings (for the connector check) ----------------------------------------------------------------------------------
-- rows of 8 per building: x, z, w, d, h, yaw, palette, osmId (PattayaBuilder.buildBuildings: CFrame.Angles(0, -yaw, 0))
local chunkRows: {[string]: {{number}}} = {}
local function buildingRows(id: string): {{number}}
	local cached = chunkRows[id]
	if cached then
		return cached
	end
	local list = {}
	for _, folderName in DATA_FOLDERS do
		local folder = ServerStorage:FindFirstChild(folderName)
		if folder then
			for _, name in {"chunk_" .. id, "chunk_d" .. id} do
				local m = folder:FindFirstChild(name)
				if m and m:IsA("ModuleScript") then
					local ok, d = pcall(require, m)
					if ok and type(d) == "table" and type(d.buildings) == "table" and #d.buildings > 0 then
						table.insert(list, d.buildings)
					end
				end
			end
		end
	end
	chunkRows[id] = list
	return list
end

local function segmentHitsBox(p: Vector2, q: Vector2, rows: {number}, i: number): boolean
	local x, z, w, d, yaw = rows[i], rows[i + 1], rows[i + 2], rows[i + 3], rows[i + 5]
	local hx, hz = w / 2 - BUILDING_INSET, d / 2 - BUILDING_INSET
	if hx <= 0 or hz <= 0 then
		return false
	end
	local r = math.rad(yaw)
	local c, s = math.cos(r), math.sin(r)
	local function toBox(v: Vector2): (number, number)
		local dx, dz = v.X - x, v.Y - z
		return dx * c + dz * s, -dx * s + dz * c
	end
	local px, pz = toBox(p)
	local qx, qz = toBox(q)
	local t0, t1 = 0, 1
	for _, axis in {{px, qx - px, hx}, {pz, qz - pz, hz}} do
		local p0, dp, lim = axis[1], axis[2], axis[3]
		if math.abs(dp) < 1e-12 then
			if math.abs(p0) > lim then
				return false
			end
		else
			local ta, tb = (-lim - p0) / dp, (lim - p0) / dp
			if ta > tb then
				ta, tb = tb, ta
			end
			t0, t1 = math.max(t0, ta), math.min(t1, tb)
			if t0 > t1 then
				return false
			end
		end
	end
	return true
end

-- true when the straight line p -> q crosses a building footprint of the exported map (false when no data is there)
function Route.crossesBuilding(p: Vector2, q: Vector2): boolean
	local minX, maxX = math.min(p.X, q.X) - BUILDING_REACH, math.max(p.X, q.X) + BUILDING_REACH
	local minZ, maxZ = math.min(p.Y, q.Y) - BUILDING_REACH, math.max(p.Y, q.Y) + BUILDING_REACH
	for cx = math.floor(minX / CHUNK), math.floor(maxX / CHUNK) do
		for cz = math.floor(minZ / CHUNK), math.floor(maxZ / CHUNK) do
			for _, rows in buildingRows(cx .. "_" .. cz) do
				for i = 1, #rows - 7, 8 do
					local bx, bz = rows[i], rows[i + 1]
					if bx >= minX and bx <= maxX and bz >= minZ and bz <= maxZ and segmentHitsBox(p, q, rows, i) then
						return true
					end
				end
			end
		end
	end
	return false
end

-- snapping -----------------------------------------------------------------------------------------------------------
-- nearest node within maxDist; with a look direction, nodes behind count 2.5x as far.
-- Without a look direction, at a job stand's own position (within STAND_MATCH studs) it returns that stand's anchor
-- node on its road edge instead of a junction (PattayaJobsServer.standNode); see Route.anchor.
local standAnchorFor: (Vector2, number) -> number?
function Route.nearestNode(p: Vector2, maxDist: number, look: Vector2?): number?
	if not look then
		local anchor = standAnchorFor(p, maxDist)
		if anchor then
			return anchor
		end
	end
	return Route.nearestJunction(p, maxDist, look)
end

-- the nearest junction (graph node, never an anchor) within maxDist: nearestNode as it was before anchors.
-- PattayaJobsServer measures job-offer distances junction to junction with it, as before the snap fix, so the set
-- of jobs each stand offers is unchanged (docs/ROUTING.md "Job offers")
function Route.nearestJunction(p: Vector2, maxDist: number, look: Vector2?): number?
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

-- the nearest point of one edge to p: the point, its distance and its arc position from node a
local function projectOnEdge(seg: {Vector2}, p: Vector2): (Vector2, number, number)
	local bestD, bestQ, bestS = math.huge, seg[1], 0
	local acc = 0
	for i = 1, #seg - 1 do
		local a, b = seg[i], seg[i + 1]
		local ab = b - a
		local len2 = ab:Dot(ab)
		local t = if len2 > 1e-6 then math.clamp((p - a):Dot(ab) / len2, 0, 1) else 0
		local q = a + ab * t
		local d = (p - q).Magnitude
		if d < bestD then
			bestD, bestQ, bestS = d, q, acc + math.sqrt(len2) * t
		end
		acc += math.sqrt(len2)
	end
	return bestQ, bestD, bestS
end

-- Nearest point on any road edge to p: edge index, the point, its distance and the distance along the edge from node a.
-- Pure geometry (no width / building preference): see Route.snap for the one routes use.
function Route.nearestEdge(p: Vector2): (number?, Vector2?, number, number)
	local bestD, bestE, bestQ, bestS = math.huge, nil, nil, 0
	for ei = 1, graphEdges do
		local q, d, s = projectOnEdge(edgePts[ei], p)
		if d < bestD then
			bestD, bestE, bestQ, bestS = d, ei, q, s
		end
	end
	return bestE, bestQ, bestD, bestS
end

-- Where a route from p joins the road graph: edge index, the point on the edge, the connector length and the arc
-- position from node a (same results as nearestEdge), or nil when no edge is within maxSnap.
-- Order of preference, nearest first within each: (1) p is on that road (connector <= half the road width +
-- SNAP_MARGIN) and the connector crosses no building; (2) one of the SNAP_TRIES nearest edges whose connector
-- crosses no building (a paddock or car park off the graph); (3) the nearest edge (no building data, or a point boxed
-- in by buildings, which a car on the map cannot reach).
function Route.snap(p: Vector2, maxSnap: number?): (number?, Vector2?, number, number)
	local limit = maxSnap or math.huge
	local cands = {}
	for ei = 1, graphEdges do
		local q, d, s = projectOnEdge(edgePts[ei], p)
		if d <= limit then
			table.insert(cands, {ei, q, d, s})
		end
	end
	if #cands == 0 then
		return nil, nil, math.huge, 0
	end
	table.sort(cands, function(x, y)
		if x[3] ~= y[3] then
			return x[3] < y[3]
		end
		return x[1] < y[1]
	end)
	local blocked = {}
	local function clear(c): boolean
		local b = blocked[c]
		if b == nil then
			b = c[3] > 0.5 and Route.crossesBuilding(p, c[2])
			blocked[c] = b
		end
		return not b
	end
	for _, c in cands do
		local half = (graph.edges[c[1]][5] or 26) / 2
		-- inside the road surface the connector is on the road (no building check, no chunk data loaded); in the
		-- margin (kerb / sidewalk) it is checked
		if c[3] <= half + SNAP_MARGIN and (c[3] <= half or clear(c)) then
			return c[1], c[2], c[3], c[4]
		end
	end
	for i, c in cands do
		if i > SNAP_TRIES then
			break -- a point boxed in by buildings (a courtyard): stop checking, take the nearest
		end
		if clear(c) then
			return c[1], c[2], c[3], c[4]
		end
	end
	local c = cands[1]
	return c[1], c[2], c[3], c[4]
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
		local seg = edgePts[link[2]]
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
		pts = {nodePos(src)}
	end
	return pts
end

-- anchors: fixed nodes on a road edge (job stands) -------------------------------------------------------------------
-- An anchor splits its edge into pieces a -> anchor(s) -> b that are added NEXT to the original edge (which stays), each
-- piece costing its share of the edge cost + ANCHOR_EPS: a path through an anchor never beats the original edge, so
-- routes between junctions (sprints, street races, GPS) are unchanged. A one-way edge (no b -> a link) gives one-way
-- pieces. Anchor indices are above #nodes and above baseNodes, so they are never sprint / event destinations.
local anchorsOnEdge: {[number]: {{any}}} = {} -- [edge] = {{s, node}} sorted by arc position
local pieceLinks: {[number]: {{any}}} = {} -- [edge] = {{fromNode, link}} added for the current anchors
local anchorCount = 0

local function twoWay(ei: number): boolean
	local e = graph.edges[ei]
	for _, link in adjacency[e[2]] do
		if link[1] == e[1] and link[2] == ei then
			return true
		end
	end
	return false
end

local function rebuildPieces(ei: number)
	for _, pl in pieceLinks[ei] or {} do
		local list = adjacency[pl[1]]
		for i = #list, 1, -1 do
			if list[i] == pl[2] then table.remove(list, i) end
		end
	end
	local added = {}
	pieceLinks[ei] = added
	local e = graph.edges[ei]
	local seg = edgePts[ei]
	local pos = arcPositions(seg)
	local total = pos[#pos]
	local stops = {{0, e[1]}}
	for _, an in anchorsOnEdge[ei] do table.insert(stops, an) end
	table.insert(stops, {total, e[2]})
	local both = twoWay(ei)
	for i = 1, #stops - 1 do
		local s0, s1 = stops[i][1], stops[i + 1][1]
		local u, v = stops[i][2], stops[i + 1][2]
		local piece = subPolyline(seg, pos, s0, s1)
		table.insert(edgePts, piece)
		local idx = #edgePts
		local cost = (if total > 1e-9 then edgeCost[ei] * (s1 - s0) / total else 0) + ANCHOR_EPS
		local fwd = {v, idx, cost, false}
		table.insert(adjacency[u], fwd)
		table.insert(added, {u, fwd})
		if both then
			local back = {u, idx, cost, true}
			table.insert(adjacency[v], back)
			table.insert(added, {v, back})
		end
	end
end

-- A fixed node where p joins the road graph (Route.snap), for routes that start or end at p every time (job stands).
-- Returns the node index (use it with dijkstra / polylineOf like a junction), the point and the connector length,
-- or nil when no edge is within maxSnap.
function Route.anchor(p: Vector2, maxSnap: number?): (number?, Vector2?, number)
	local ei, q, d, s = Route.snap(p, maxSnap)
	if not ei or not q then
		return nil, nil, math.huge
	end
	anchorCount += 1
	local n = #nodes + anchorCount
	anchorPos[n] = q
	adjacency[n] = {}
	local list = anchorsOnEdge[ei] or {}
	anchorsOnEdge[ei] = list
	table.insert(list, {s, n})
	table.sort(list, function(x, y)
		if x[1] ~= y[1] then return x[1] < y[1] end
		return x[2] < y[2]
	end)
	rebuildPieces(ei)
	return n, q, d
end

-- job stands (ServerStorage.PattayaData.jobs): all anchors are made together the first time one is asked for, so
-- a Dijkstra from one stand already reaches every other stand's anchor
local stands: {{any}}? = nil
standAnchorFor = function(p: Vector2, maxDist: number): number?
	if stands == nil then
		local list = {}
		local m = dataFolder:FindFirstChild("jobs")
		local ok, data = false, nil
		if m then
			ok, data = pcall(require, m)
		end
		if ok and type(data) == "table" then
			for _, s in data do
				if type(s) == "table" and type(s.x) == "number" and type(s.z) == "number" then
					table.insert(list, {pos = Vector2.new(s.x, s.z), node = false})
				end
			end
		end
		stands = list
		for _, st in list do
			st.node = Route.anchor(st.pos, maxDist) or false
		end
	end
	for _, st in stands :: {{any}} do
		if st.node and (st.pos - p).Magnitude <= STAND_MATCH then
			return st.node
		end
	end
	return nil
end

-- routes -------------------------------------------------------------------------------------------------------------
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
-- length, or nil, reason. Used by the GPS (e.g. the way to the Bira Circuit, and back from its paddock).
-- The polyline starts at Route.snap's point (on the road the car is on, never across a building when the map data is
-- there; the car position itself is not in it, as before) and follows that edge to whichever end leads on.
function Route.routeTo(pos: Vector3, look: Vector3?, target: number, isOsmId: boolean?, maxSnap: number?)
	local dst = if isOsmId then osmIndex[target] else target
	if not dst then
		return nil, "Unknown destination"
	end
	local p = Route.toLocal(pos)
	-- maxSnap (default 150): how far off the graph the start may be. The GPS passes more, because a venue's paddock is
	-- off the graph (Bira paddock: 233 studs from the facility junction) and the route then begins with a straight
	-- leg from the car to the nearest road.
	local ei, q, d, s = Route.snap(p, maxSnap or 150)
	if not ei or not q then
		return nil, "No road nearby"
	end
	local e = graph.edges[ei]
	local a, b = e[1], e[2]
	-- seeds: the edge's end(s) reachable from q; the start of the polyline is the projection point q
	local seeds = {}
	local tail = {} -- polyline from q to each seed, chosen after the search
	local seg = edgePts[ei]
	local arc = arcPositions(seg)
	local function along(fromS: number, toS: number): {Vector2} -- edge vertices between two arc positions, in travel order
		local out = {}
		if toS >= fromS then
			for i = 1, #seg do
				if arc[i] > fromS + 0.01 and arc[i] <= toS + 0.01 then table.insert(out, seg[i]) end
			end
		else
			for i = #seg, 1, -1 do
				if arc[i] < fromS - 0.01 and arc[i] >= toS - 0.01 then table.insert(out, seg[i]) end
			end
		end
		return out
	end
	local polyLen = arc[#arc]
	seeds[b] = math.max(polyLen - s, 0)
	tail[b] = along(s, polyLen)
	if twoWay(ei) then
		seeds[a] = s
		tail[a] = along(s, 0)
	end
	local function finish(pts: {Vector2}, nodeIndex: number)
		local route = {}
		for _, x in pts do table.insert(route, Route.toWorld(x)) end
		return {route = route, length = Route.length(pts), nodeIndex = nodeIndex}
	end
	if (dst == a or dst == b) and tail[dst] then
		local pts = {q}
		for _, x in tail[dst] do table.insert(pts, x) end
		return finish(pts, dst)
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
	return finish(pts, dst)
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
