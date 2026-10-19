-- Tail of the offline circuit harness (assembled by tools/qa/tests/test_circuits.py after prelude.luau and the real
-- CircuitRegistry / CheckpointValidator / LapTimingService / circuit data sources). Prints one fact per line:
--   C <id> n len lengthStuds gates s1 s2          G <id> i s line halfWidth inBypass pitLat
--   GRID <id> i x y z lookX lookZ                 PIT <id> width len entryS exitS trackEntryS trackExitS limit
--   ENT <id> x y z                                RUN <id> <name> key=value ...
local function fmt(x)
	if x == nil then
		return "nil"
	end
	return string.format("%.3f", x)
end

-- drives a list of positions through a fresh tracker + timer at `dt` seconds per sample
local function drive(c, positions, dt)
	local tr = Validator.new(c)
	local timer = Timing.new()
	local counts, missed, laps, t = {}, 0, {}, 0
	for _, pos in positions do
		t += dt
		for _, e in tr:sample(pos, t) do
			counts[e.kind] = (counts[e.kind] or 0) + 1
			if e.kind == "gate" then
				if e.missed then
					missed += 1
				end
				for _, r in timer:onGate(c.gates[e.gate], e.t, {}, nil) do
					if r.kind == "lap" then
						table.insert(laps, string.format("%.2f%s", r.time, if r.valid then "" else "!" .. tostring(r.reason)))
					end
				end
			end
		end
	end
	local kinds = {}
	for k, v in counts do
		table.insert(kinds, k .. ":" .. v)
	end
	table.sort(kinds)
	return string.format("events=%s missed=%d laps=%s", table.concat(kinds, ","), missed, table.concat(laps, ";"))
end

local function along(c, s0, s1, speed, dt, out)
	local s = s0
	while s <= s1 do
		table.insert(out, (Registry.pointAt(c, s)))
		s += speed * dt
	end
	return out
end

local function alongPolyline(pts, speed, dt, out)
	local carry = 0
	for i = 1, #pts - 1 do
		local a, b = pts[i], pts[i + 1]
		local len = (b - a).Magnitude
		local s = carry
		while s < len do
			table.insert(out, a:Lerp(b, s / len))
			s += speed * dt
		end
		carry = s - len
	end
	table.insert(out, pts[#pts])
	return out
end

for _, id in IDS do
	local ok, c = pcall(Registry.compile, DEFS[id])
	if not ok then
		print("ERR", id, tostring(c))
		continue
	end
	print("C", id, c.n, fmt(c.len), c.lengthStuds, #c.gates, fmt(c.sectorS[1]), fmt(c.sectorS[2]))
	for i, g in c.gates do
		print("G", id, i, fmt(g.s), g.line or 0, fmt(g.halfWidth), if g.inBypass then 1 else 0, fmt(g.pitLat))
	end
	for i, cf in c.grid do
		local p, l = cf.Position, cf.LookVector
		print("GRID", id, i, fmt(p.X), fmt(p.Y), fmt(p.Z), fmt(l.X), fmt(l.Z))
	end
	if c.pit then
		local p = c.pit
		print("PIT", id, fmt(p.width), fmt(p.len), fmt(p.entryS), fmt(p.exitS), fmt(p.trackEntryS), fmt(p.trackExitS),
			fmt(p.limit))
	end
	local e = c.entrance.Position
	print("ENT", id, fmt(e.X), fmt(e.Y), fmt(e.Z))

	local dt = 0.05 -- 20 Hz samples, like the server Heartbeat at a replication rate the judge copes with
	-- two clean laps on the centreline at 100 studs/s, starting 60 studs before the line, ending 60 past it
	local laps = along(c, c.len - 60, 3 * c.len + 60, 100, dt, {})
	print("RUN", id, "clean2", drive(c, laps, dt))
	-- the same at 230 studs/s (nitro top speed of the fastest car is 240, the judge's teleport limit is 260)
	print("RUN", id, "fast1", drive(c, along(c, c.len - 60, 2 * c.len + 60, 230, dt, {}), dt))
	-- a lap through the pit lane: centreline to the pit entry, the pit lane at 50 studs/s, centreline to the line
	if c.pit then
		local p = c.pit
		-- leave / rejoin the centreline where the pit lane's first / last point projects onto it
		local absEntry = c.len + Registry.nearest(c, p.pts[1]).s
		local absExit = c.len + Registry.nearest(c, p.pts[#p.pts]).s
		while absExit <= absEntry do
			absExit += c.len
		end
		local pos = along(c, c.len - 60, absEntry, 100, dt, {})
		alongPolyline(p.pts, 50, dt, pos)
		along(c, absExit, (math.floor(absExit / c.len) + 1) * c.len + 60, 100, dt, pos)
		print("RUN", id, "pitlap", drive(c, pos, dt))
	end
end
for _, w in WARNINGS do
	print("WARN", w)
end
print("DONE")
