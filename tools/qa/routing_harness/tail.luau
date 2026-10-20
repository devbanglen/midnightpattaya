-- Scenarios run against OLD_ROUTE (PattayaRoute_old.luau, the module before the snap fix) and NEW_ROUTE
-- (roblox/src/ServerStorage/PattayaRoute.luau). SCEN comes from route_harness.py. Output: one tab-separated line per
-- fact, points as "x z" pairs in map-local studs (world - PattayaBuilder.ORIGIN).
local ORIGIN_X = 20000
local function out(...)
	local t = {}
	for i = 1, select("#", ...) do
		t[i] = tostring((select(i, ...)))
	end
	print(table.concat(t, "\t"))
end
local function fmt2(pts)
	local t = {}
	for _, p in pts do
		table.insert(t, string.format("%.3f %.3f", p.X, p.Y))
	end
	return table.concat(t, " ")
end
local function fmt3(pts)
	local t = {}
	for _, p in pts do
		table.insert(t, string.format("%.3f %.3f", p.X - ORIGIN_X, p.Z))
	end
	return table.concat(t, " ")
end

local stands = REQ(SERVER_STORAGE:WaitForChild("PattayaData"):WaitForChild("jobs"))
local MIN_LEN, MAX_LEN = 900, 3200 -- PattayaJobsServer

for _, variant in {"old", "new"} do
	local R = if variant == "old" then OLD_ROUTE else NEW_ROUTE
	local t0 = os.clock()
	-- jobs: exactly the PattayaJobsServer flow (standNode = nearestNode(toLocal(stand.pos), 600), cached; one Dijkstra
	-- from the start stand; every other stand in range by road is a possible destination; stand positions added at
	-- both ends of the polyline)
	local nodeOf = {}
	local function standNode(s)
		if nodeOf[s] == nil then
			nodeOf[s] = R.nearestNode(R.toLocal(R.toWorld(Vector2.new(s.x, s.z), 1)), 600) or false
		end
		return if nodeOf[s] then nodeOf[s] else nil
	end
	for _, from in stands do
		local src = standNode(from)
		if not src then
			out("JOBERR", variant, from.id, "no node")
			continue
		end
		local dist, prev = R.dijkstra(src)
		local nOpt = 0
		for _, to in stands do
			if to ~= from then
				local n = standNode(to)
				local d = n and dist[n]
				if d and d >= MIN_LEN and d <= MAX_LEN then
					nOpt += 1
					local pts = R.polylineOf(prev, src, n)
					table.insert(pts, 1, R.toLocal(R.toWorld(Vector2.new(from.x, from.z), 1)))
					table.insert(pts, R.toLocal(R.toWorld(Vector2.new(to.x, to.z), 1)))
					out("JOB", variant, from.id, to.id, string.format("%.2f", R.length(pts)), fmt2(pts))
				end
			end
		end
		out("JOBN", variant, from.id, nOpt)
	end
	out("TIME", variant, "jobs", string.format("%.3f", os.clock() - t0))
	t0 = os.clock()
	-- GPS: Route.routeTo(car position, look, OSM id, true, GPS_SNAP)
	for _, g in SCEN.gps do
		local ok, r, why = pcall(R.routeTo, Vector3.new(g.x + ORIGIN_X, 1, g.z), nil, g.target, true, g.snap)
		if ok and r then
			out("GPS", variant, g.name, string.format("%.3f %.3f", g.x, g.z), string.format("%.2f", r.length),
				fmt3(r.route))
		else
			out("GPSERR", variant, g.name, tostring(if ok then why else r))
		end
	end
	out("TIME", variant, "gps", string.format("%.3f", os.clock() - t0))
	-- sprints / street races / events: Route.pointToPoint with a seeded pick (after the new module made its anchors)
	for i, sp in SCEN.sprint do
		local r, why = R.pointToPoint(Vector3.new(sp.x + ORIGIN_X, 1, sp.z), Vector3.new(sp.lx, 0, sp.lz), sp.minLen,
			sp.maxLen, sp.spacing, Random.new(sp.seed))
		if r then
			local dirs = {}
			for _, d in r.dirs do
				table.insert(dirs, string.format("%.4f %.4f", d.X, d.Z))
			end
			out("SPR", variant, i, string.format("%.2f", r.length), fmt3(r.cps) .. " | " .. table.concat(dirs, " ")
				.. " | " .. fmt3(r.route))
		else
			out("SPRERR", variant, i, tostring(why))
		end
	end
end

-- the Luau-side building check, on the old stand connectors (stand -> nearest junction)
for _, s in stands do
	local p = Vector2.new(s.x, s.z)
	local n = OLD_ROUTE.nearestNode(p, 600)
	if n then
		local q = OLD_ROUTE.nodes[n]
		out("XB", s.id, if NEW_ROUTE.crossesBuilding(p, q) then 1 else 0, string.format("%.2f", (q - p).Magnitude))
	end
	local a, q, d = NEW_ROUTE.anchor(p, 600)
	out("ANCHOR", s.id, a, string.format("%.3f %.3f", q.X, q.Y), string.format("%.2f", d))
end
-- off-road points whose nearest edge is behind a building: old nearestEdge vs new snap (GPS maxSnap)
local tSnap, worst = 0, 0
for _, sp in SCEN.snap do
	local p = Vector2.new(sp.x, sp.z)
	local _, qo, dOld = OLD_ROUTE.nearestEdge(p)
	local t0 = os.clock()
	local _, qn, dNew = NEW_ROUTE.snap(p, 700)
	local dt = os.clock() - t0
	tSnap += dt
	worst = math.max(worst, dt)
	out("SNAP", sp.name, string.format("%.3f %.3f", sp.x, sp.z), string.format("%.3f %.3f", qo.X, qo.Y),
		string.format("%.3f %.3f", qn.X, qn.Y), string.format("%.2f", dOld), string.format("%.2f", dNew))
end
out("TIME", "new", "snap_total", string.format("%.4f", tSnap))
out("TIME", "new", "snap_worst", string.format("%.4f", worst))
for name, c in REQUIRE_COUNT do
	if string.sub(name, 1, 6) == "chunk_" then
		out("CHUNKREQ", name, c)
	end
end
out("WARN_COUNT", #WARNINGS)
out("DONE")
