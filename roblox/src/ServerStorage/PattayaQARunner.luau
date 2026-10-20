-- PattayaQARunner (DEV ONLY, server side, READ-ONLY): live-state checks for a Play session. Nothing in the game
-- requires it. It never creates, changes, moves or destroys anything in the place: it only reads instances,
-- attributes and Stats, and requires pure modules (CircuitRegistry / RankedRating / PerfProfile are CLONED, so even
-- their module state stays out of the game's copies). docs/AUTOMATED_QA.md has the list of checks.
--
-- Run in Play, command bar (or execute tool) on the SERVER:
--   local lines = require(game.ServerStorage.PattayaQARunner:Clone()).run()   -- returns {string}
--   print(table.concat(lines, "\n"))
-- or print it directly:  require(game.ServerStorage.PattayaQARunner:Clone()).report()
-- Options: run({probe = true}) also raycasts along the Central Loop with PattayaTestKitServer.probePath (read-only
-- server raycasts, ~1 s); run({verbose = true}) adds the per-chunk lines.
-- Line format: "PASS <check> <detail>", "FAIL ...", "WARN ..." (budget heuristic or known issue), "INFO ...".
-- Line 1 is the summary: "QA <n> PASS, <n> FAIL, <n> WARN (<ms> ms)".
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")
local StarterPlayer = game:GetService("StarterPlayer")
local Stats = game:GetService("Stats")

local QA = {}

-- Contract (kept in sync with the repo by tools/qa/tests/test_qa_runner.py) ------------------------------------------
-- ReplicatedStorage.PattayaRemotes children: name -> class
QA.REMOTES = {
	CancelJob = "RemoteEvent", ChallengeMsg = "RemoteEvent", ChallengeReply = "RemoteEvent",
	ChallengeRequest = "RemoteEvent", CircuitMsg = "RemoteEvent", CircuitRequest = "RemoteEvent",
	EventJoin = "RemoteEvent", GPSRequest = "RemoteEvent", GPSUpdate = "RemoteEvent", GarageRequest = "RemoteFunction",
	JobUpdate = "RemoteEvent", NearMiss = "RemoteEvent", NitroBonus = "RemoteEvent", RequestJob = "RemoteEvent",
	RequestSprint = "RemoteEvent", RoadFightRequest = "RemoteEvent", SprintUpdate = "RemoteEvent",
}
-- directly under ReplicatedStorage
QA.ROOT_REMOTES = {PerfTelemetry = "RemoteEvent"}
-- roblox/src/ServerScriptService/*.server.luau
QA.SERVER_SCRIPTS = {"CircuitServer", "PattayaChallengeServer", "PattayaEventsServer", "PattayaGarageServer",
	"PattayaGPSServer", "PattayaJobsServer", "PattayaPerfTelemetry", "PattayaRaceServer", "PattayaSprintServer",
	"PattayaTimeServer", "RaceCarServer"}
-- roblox/src/StarterPlayer/StarterPlayerScripts/*.client.luau
QA.CLIENT_SCRIPTS = {"CarController", "CircuitRaceClient", "MidnightActivity", "MidnightCamera", "MidnightHUD",
	"MidnightSpeedo", "PattayaChallengeClient", "PattayaEventsClient", "PattayaGarageClient", "PattayaGPSClient",
	"PattayaJobsClient", "PattayaLOD", "PattayaMinimapClient", "PattayaNightLights", "PattayaPerfTelemetry",
	"PattayaPreload", "PattayaRaceClient", "PattayaRoadLook", "PattayaSprintClient", "PattayaTraffic", "VisMeshPalmLOD"}

-- Budgets (sources in brackets) -------------------------------------------------------------------------------------
-- Parts per Atomic chunk model, by PattayaWorld folder [tools/mapgen/config/*.json, VISUAL_PERFORMANCE.md,
-- STREET_FURNITURE.md]
QA.CHUNK_CAPS = {VisSliceChunks = 600, FurnitureChunks = 600, CoastChunks = 600, ApronChunks = 1500, LandmarkChunks = 900, ShoulderChunks = 600}
-- Reference BasePart counts per folder [PERFORMANCE_BUDGET.md measured/estimated, build/*.json totals]; WARN above
-- REF_SLACK x reference (a heuristic: the place has no single documented cap)
QA.PART_REFS = {
	["PattayaWorld.Chunks"] = 16027, ["PattayaWorld.WideChunks"] = 37800, ["PattayaWorld.VisSliceChunks"] = 23786,
	["PattayaWorld.FurnitureChunks"] = 9246, ["PattayaWorld.ApronChunks"] = 23791, ["PattayaWorld.CoastChunks"] = 6042,
	["PattayaWorld.LandmarkChunks"] = 1658, ["Circuit_bira"] = 6000,
	["PattayaWorld.ShoulderChunks"] = 2536, -- Sukhumvit shoulder pilot (8 chunks); full patch 12,193
}
QA.REF_SLACK = 1.25
QA.TOTAL_PARTS_WARN = 160000 -- sum of the references above x 1.25 (rounded)
QA.MEMORY_WARN_MB = 6000 -- PERFORMANCE_BUDGET.md: 4.4 GB total measured in Studio (server + client in one process)
QA.CENTRAL_CHECKPOINTS = 22 -- build/central_pattaya race (tools/qa/tests/test_race_central.py)
QA.BIRA_GATES = 96 -- CircuitRegistry on roblox/data/circuits/bira.luau (tools/qa/tests/test_circuits.py)

-------------------------------------------------------------------------------------------------------------------
local lines: {string} = {}
local counts = {PASS = 0, FAIL = 0, WARN = 0, INFO = 0}

local function out(kind: string, name: string, detail: string?)
	counts[kind] += 1
	table.insert(lines, kind .. " " .. name .. (if detail and detail ~= "" then "  " .. detail else ""))
end
local function check(name: string, ok: boolean, detail: string?)
	out(if ok then "PASS" else "FAIL", name, detail)
end
local function safe(name: string, f: () -> ())
	local ok, err = pcall(f)
	if not ok then
		out("FAIL", name, "check errored: " .. tostring(err))
	end
end

local function countParts(root: Instance): number
	local n = 0
	for _, d in root:GetDescendants() do
		if d:IsA("BasePart") then
			n += 1
		end
	end
	return n
end

local function requireClone(m: Instance?): any
	assert(m and m:IsA("ModuleScript"), "module missing")
	return require((m :: ModuleScript):Clone())
end

-- checks -------------------------------------------------------------------------------------------------------------
local function checkContext()
	check("context.server", RunService:IsServer(), "run from the server command bar / server execute")
	check("context.running", RunService:IsRunning(), "Play mode (scripts must have run)")
	out("INFO", "context.players", tostring(#Players:GetPlayers()))
end

local function checkRemotes()
	local folder = ReplicatedStorage:FindFirstChild("PattayaRemotes")
	check("remotes.folder", folder ~= nil and folder:IsA("Folder"), "ReplicatedStorage.PattayaRemotes")
	if not folder then
		return
	end
	local missing, wrong = {}, {}
	for name, cls in QA.REMOTES do
		local r = folder:FindFirstChild(name)
		if not r then
			table.insert(missing, name)
		elseif not r:IsA(cls) then
			table.insert(wrong, name .. " is " .. r.ClassName)
		end
	end
	table.sort(missing)
	local n = 0
	for _ in QA.REMOTES do
		n += 1
	end
	check("remotes.required", #missing == 0 and #wrong == 0, ("%d/%d present%s%s"):format(n - #missing, n,
		if #missing > 0 then "; missing " .. table.concat(missing, ", ") else "",
		if #wrong > 0 then "; wrong class " .. table.concat(wrong, ", ") else ""))
	local seen, dups, extra = {}, {}, {}
	for _, c in folder:GetChildren() do
		if seen[c.Name] then
			table.insert(dups, c.Name)
		end
		seen[c.Name] = true
		if not QA.REMOTES[c.Name] then
			table.insert(extra, c.Name)
		end
	end
	check("remotes.no_duplicates", #dups == 0, if #dups > 0 then table.concat(dups, ", ") else nil)
	if #extra > 0 then
		table.sort(extra)
		out("INFO", "remotes.extra", table.concat(extra, ", "))
	end
	for name, cls in QA.ROOT_REMOTES do
		local r = ReplicatedStorage:FindFirstChild(name)
		check("remotes." .. name, r ~= nil and r:IsA(cls), "ReplicatedStorage." .. name)
	end
end

local CONTAINERS = function(): {Instance}
	local list = {ServerScriptService, ServerStorage, ReplicatedStorage, game:GetService("ReplicatedFirst"),
		StarterPlayer, game:GetService("StarterGui"), workspace}
	for _, p in Players:GetPlayers() do
		local ps = p:FindFirstChild("PlayerScripts")
		if ps then
			table.insert(list, ps)
		end
	end
	return list
end

local function checkScripts()
	local missing, disabled = {}, {}
	for _, name in QA.SERVER_SCRIPTS do
		local s = ServerScriptService:FindFirstChild(name)
		if not (s and s:IsA("Script")) then
			table.insert(missing, name)
		elseif not (s :: Script).Enabled then
			table.insert(disabled, name)
		end
	end
	check("scripts.server", #missing == 0 and #disabled == 0, ("%d expected%s%s"):format(#QA.SERVER_SCRIPTS,
		if #missing > 0 then "; missing " .. table.concat(missing, ", ") else "",
		if #disabled > 0 then "; disabled " .. table.concat(disabled, ", ") else ""))
	local sps = StarterPlayer:FindFirstChild("StarterPlayerScripts")
	local cmissing = {}
	for _, name in QA.CLIENT_SCRIPTS do
		local s = sps and sps:FindFirstChild(name)
		if not (s and s:IsA("LocalScript")) then
			table.insert(cmissing, name)
		end
	end
	check("scripts.client", #cmissing == 0, ("%d expected%s"):format(#QA.CLIENT_SCRIPTS,
		if #cmissing > 0 then "; missing " .. table.concat(cmissing, ", ") else ""))

	-- duplicates: two scripts with one name under one parent, or a server Script that also exists outside
	-- ServerScriptService with the same name (it would run twice)
	local byKey: {[string]: number} = {}
	local serverNames = {}
	for _, n in QA.SERVER_SCRIPTS do
		serverNames[n] = true
	end
	local strays = {}
	local total = 0
	for _, root in CONTAINERS() do
		for _, d in root:GetDescendants() do
			if d:IsA("LuaSourceContainer") then
				total += 1
				local key = d.Parent:GetFullName() .. "/" .. d.Name .. "/" .. d.ClassName
				byKey[key] = (byKey[key] or 0) + 1
				if d:IsA("Script") and not d:IsA("LocalScript") and serverNames[d.Name]
					and d.Parent ~= ServerScriptService and (d :: Script).Enabled then
					table.insert(strays, d:GetFullName())
				end
			end
		end
	end
	local dups = {}
	for k, n in byKey do
		if n > 1 then
			table.insert(dups, k .. " x" .. n)
		end
	end
	table.sort(dups)
	check("scripts.no_duplicates", #dups == 0, ("%d scripts scanned%s"):format(total,
		if #dups > 0 then "; " .. table.concat(dups, "; ", 1, math.min(#dups, 8)) else ""))
	check("scripts.no_stray_server_copies", #strays == 0, if #strays > 0 then table.concat(strays, ", ") else nil)
end

local function checkGarage()
	local f = ServerStorage:FindFirstChild("BuildCar")
	check("garage.buildcar", f ~= nil and f:IsA("BindableFunction"), "ServerStorage.BuildCar (RaceCarServer ran)")
	local g = workspace:FindFirstChild("PattayaGarage")
	check("garage.marker", g ~= nil, "workspace.PattayaGarage (PattayaGarageServer ran)")
	local specsM = ReplicatedStorage:FindFirstChild("CarSpecs")
	check("garage.carspecs", specsM ~= nil and specsM:IsA("ModuleScript"), "ReplicatedStorage.CarSpecs")
	if not specsM then
		return
	end
	local Specs = require(specsM :: ModuleScript)
	local cars, bad = 0, {}
	for _, m in workspace:GetChildren() do
		if m:IsA("Model") and m:GetAttribute("RaceCar") then
			cars += 1
			local id = m:GetAttribute("CarId")
			if not (type(id) == "string" and Specs.Cars[id]) then
				table.insert(bad, m.Name .. " CarId=" .. tostring(id))
			else
				local d = Specs.Describe(id, m:GetAttribute("UpgEngine") or 0, m:GetAttribute("UpgGrip") or 0)
				if m:GetAttribute("PI") ~= d.pi or m:GetAttribute("Class") ~= d.class then
					table.insert(bad, ("%s PI %s/%s class %s/%s"):format(m.Name, tostring(m:GetAttribute("PI")),
						tostring(d.pi), tostring(m:GetAttribute("Class")), d.class))
				end
			end
		end
	end
	check("garage.car_attributes", cars > 0 and #bad == 0, ("%d RaceCar models%s"):format(cars,
		if #bad > 0 then "; " .. table.concat(bad, "; ", 1, math.min(#bad, 6)) else ""))
	for _, p in Players:GetPlayers() do
		local ls = p:FindFirstChild("leaderstats")
		local okLs = ls ~= nil and ls:FindFirstChild("Level") ~= nil and ls:FindFirstChild("Money") ~= nil
			and ls:FindFirstChild("EXP") ~= nil and ls:FindFirstChild("Title") ~= nil
		check("progress.leaderstats " .. p.Name, okLs, "Level/Money/EXP/Title")
		out("INFO", "progress.loaded " .. p.Name, tostring(p:GetAttribute("ProgressLoaded")))
	end
end

local function checkActivities()
	local world = workspace:FindFirstChild("PattayaWorld")
	check("world.PattayaWorld", world ~= nil)
	if not world then
		return
	end
	-- loop race
	local race = world:FindFirstChild("Race")
	local cps = race and race:FindFirstChild("Checkpoints")
	if cps then
		local idx, dup = {}, false
		for _, g in cps:GetChildren() do
			local i = g:GetAttribute("Index")
			if idx[i] then
				dup = true
			end
			idx[i] = true
		end
		local n = #cps:GetChildren()
		local contiguous = true
		for i = 1, n do
			if not idx[i] then
				contiguous = false
			end
		end
		check("race.checkpoints", n == QA.CENTRAL_CHECKPOINTS and contiguous and not dup,
			("%d gates (expect %d), Index 1..n %s"):format(n, QA.CENTRAL_CHECKPOINTS, if contiguous and not dup then "ok" else "BROKEN"))
		check("race.attributes", type(race:GetAttribute("Laps")) == "number" and type(race:GetAttribute("LengthStuds")) == "number"
			and type(race:GetAttribute("Path")) == "string", ("Laps=%s LengthStuds=%s"):format(tostring(race:GetAttribute("Laps")),
			tostring(race:GetAttribute("LengthStuds"))))
	else
		check("race.checkpoints", false, "workspace.PattayaWorld.Race.Checkpoints missing")
	end
	-- jobs (missions)
	local stands = world:FindFirstChild("JobStands") or workspace:FindFirstChild("JobStands", true)
	check("jobs.stands", stands ~= nil and #stands:GetChildren() >= 16,
		("%d job stands (central 16, wide 29)"):format(if stands then #stands:GetChildren() else 0))
	-- events
	local ev = ReplicatedStorage:FindFirstChild("PattayaEvent")
	check("events.state", ev ~= nil, ev and ("Phase=%s Kind=%s"):format(tostring(ev:GetAttribute("Phase")),
		tostring(ev:GetAttribute("Kind"))) or "ReplicatedStorage.PattayaEvent missing")
	local se = ServerStorage:FindFirstChild("StartEvent")
	check("events.startevent", se ~= nil and se:IsA("BindableEvent"), "ServerStorage.StartEvent")
	local evf = world:FindFirstChild("Events")
	-- the ring exists only while an event gathers (PattayaEventsServer.buildRing); idle needs just the folder
	local gathering = ev ~= nil and ev:GetAttribute("Phase") == "gathering"
	local hasRing = evf ~= nil and evf:FindFirstChild("EventRing") ~= nil
	check("events.ring", evf ~= nil and (hasRing or not gathering),
		("PattayaWorld.Events folder %s, EventRing %s (phase %s)"):format(tostring(evf ~= nil), tostring(hasRing),
			tostring(ev and ev:GetAttribute("Phase"))))
	-- GPS / sprint / challenge need the road graph
	local data = ServerStorage:FindFirstChild("PattayaData")
	check("data.graph", data ~= nil and data:FindFirstChild("graph") ~= nil, "ServerStorage.PattayaData.graph")
	check("data.circuits", data ~= nil and data:FindFirstChild("circuits") ~= nil, "ServerStorage.PattayaData.circuits")
end

local function checkCircuits()
	local data = ServerStorage:FindFirstChild("PattayaData")
	local folder = data and data:FindFirstChild("circuits")
	if not folder then
		check("circuit.registry", false, "no PattayaData.circuits")
		return
	end
	-- the game's own registry copy (empty when this context has its own module copies, see docs/TEST_KIT.md)
	local shared = ServerStorage:FindFirstChild("CircuitRegistry")
	local okS, sharedReg = pcall(require, shared)
	local sharedN = if okS and sharedReg then #sharedReg.all() else -1
	out("INFO", "circuit.registry_shared_copy", ("%d circuits loaded in this context's copy"):format(sharedN))
	-- a private clone loaded from the data (compile only, nothing is built)
	local Registry = requireClone(shared)
	local list = Registry.load(folder)
	local ids = {}
	for _, c in list do
		table.insert(ids, c.id)
	end
	local bira = Registry.get("bira")
	check("circuit.registry_has_bira", bira ~= nil, "compiled: " .. table.concat(ids, ", "))
	if bira then
		check("circuit.bira_gates", #bira.gates == QA.BIRA_GATES, ("%d gates, lap %.0f studs, %d grid slots"):format(
			#bira.gates, bira.len, #bira.grid))
		-- known issue (tools/qa/tests): keyed grid slots compile to the origin
		local bad = 0
		for _, cf in bira.grid do
			local near = Registry.nearest(bira, cf.Position)
			if near.dist > near.width / 2 + 5 then
				bad += 1
			end
		end
		out(if bad == 0 then "PASS" else "WARN", "circuit.bira_grid_on_track",
			("%d/%d slots off the track%s"):format(bad, #bira.grid, if bad > 0 then " (KNOWN: CircuitRegistry reads grid slots positionally, bira.luau has keyed slots)" else ""))
		local pw = bira.pit and bira.pit.width
		local want = bira.def.pitLaneWidth or bira.def.pitWidth
		out(if pw == want then "PASS" else "WARN", "circuit.bira_pit_width",
			("judge %s vs data %s%s"):format(tostring(pw), tostring(want), if pw ~= want then " (KNOWN: registry reads pitWidth, data has pitLaneWidth)" else ""))
		local venue = workspace:FindFirstChild("Circuit_bira")
		check("circuit.bira_venue", venue ~= nil, venue and ("workspace.Circuit_bira %d parts"):format(countParts(venue)) or "workspace.Circuit_bira missing")
	end
	local wm = ReplicatedStorage:FindFirstChild("PattayaWorldMap")
	check("circuit.server_ran", wm ~= nil and wm:GetAttribute("Circuit_bira") ~= nil,
		"PattayaWorldMap attribute Circuit_bira (set by CircuitServer)")
	check("circuit.paddock", workspace:FindFirstChild("Paddock_bira", true) ~= nil, "Paddock_bira marker")
	-- ranked maths unit test (pure)
	local okT, summary, allOk = pcall(function()
		return requireClone(ServerStorage:FindFirstChild("RankedRatingTest"))(requireClone(ServerStorage:FindFirstChild("RankedRating")))
	end)
	check("ranked.rating_test", okT and allOk == true, if okT then tostring(summary) else tostring(summary))
end

local function checkBudgets(opts)
	local perTop: {[string]: number} = {}
	local total = 0
	local world = workspace:FindFirstChild("PattayaWorld")
	for _, d in workspace:GetDescendants() do
		if d:IsA("BasePart") then
			total += 1
			-- top folder below workspace; for PattayaWorld one level deeper
			local a = d
			local chain = {}
			while a.Parent and a.Parent ~= workspace do
				table.insert(chain, 1, a.Parent)
				a = a.Parent
			end
			local key
			if #chain == 0 then
				key = "(workspace)"
			elseif chain[1] == world and chain[2] then
				key = "PattayaWorld." .. chain[2].Name
			else
				key = chain[1].Name
			end
			perTop[key] = (perTop[key] or 0) + 1
		end
	end
	local keys = {}
	for k in perTop do
		table.insert(keys, k)
	end
	table.sort(keys, function(a, b) return perTop[a] > perTop[b] end)
	for i, k in keys do
		local ref = QA.PART_REFS[k]
		if ref then
			out(if perTop[k] <= ref * QA.REF_SLACK then "PASS" else "WARN", "budget.parts " .. k,
				("%d parts (reference %d, warn above %d)"):format(perTop[k], ref, math.floor(ref * QA.REF_SLACK)))
		elseif i <= 12 then
			out("INFO", "budget.parts " .. k, ("%d parts"):format(perTop[k]))
		end
	end
	out(if total <= QA.TOTAL_PARTS_WARN then "PASS" else "WARN", "budget.parts_total",
		("%d BaseParts in workspace (warn above %d)"):format(total, QA.TOTAL_PARTS_WARN))
	-- per Atomic chunk caps
	if world then
		for folderName, cap in QA.CHUNK_CAPS do
			local f = world:FindFirstChild(folderName)
			if f then
				local worst, worstName, over, n = 0, "", 0, 0
				for _, chunk in f:GetChildren() do
					n += 1
					local c = countParts(chunk)
					if c > worst then
						worst, worstName = c, chunk.Name
					end
					if c > cap then
						over += 1
						if opts.verbose then
							out("INFO", "budget.chunk " .. folderName .. "." .. chunk.Name, tostring(c))
						end
					end
				end
				check("budget.chunk_cap " .. folderName, over == 0, ("%d chunks, largest %s %d parts, cap %d, over %d")
					:format(n, worstName, worst, cap, over))
			else
				out("INFO", "budget.chunk_cap " .. folderName, "folder not built")
			end
		end
	end
	-- Stats
	out("INFO", "stats.instances", ("InstanceCount %s, PrimitivesCount %s"):format(tostring(Stats.InstanceCount),
		tostring(Stats.PrimitivesCount)))
	local mem = Stats:GetTotalMemoryUsageMb()
	out(if mem <= QA.MEMORY_WARN_MB then "PASS" else "WARN", "stats.memory_total",
		("%.0f MB (warn above %d; Studio runs server and client in one process)"):format(mem, QA.MEMORY_WARN_MB))
	local tags = {}
	for _, tag in Enum.DeveloperMemoryTag:GetEnumItems() do
		local ok, v = pcall(function() return Stats:GetMemoryUsageMbForTag(tag) end)
		if ok and v >= 1 then
			table.insert(tags, {tag.Name, v})
		end
	end
	table.sort(tags, function(a, b) return a[2] > b[2] end)
	local parts = {}
	for i = 1, math.min(#tags, 10) do
		table.insert(parts, ("%s %.0f"):format(tags[i][1], tags[i][2]))
	end
	out("INFO", "stats.memory_by_tag", table.concat(parts, ", "))
	-- streaming / LOD profile (read-only; PerfProfile.show only reads)
	local okP, P = pcall(requireClone, ServerStorage:FindFirstChild("PattayaPerfProfile"))
	if okP then
		local pc = P.PROFILES.pc.streaming
		local okR, minR, tgtR = pcall(function() return workspace.StreamingMinRadius, workspace.StreamingTargetRadius end)
		out(if workspace.StreamingEnabled and okR and minR == pc.StreamingMinRadius and tgtR == pc.StreamingTargetRadius
			then "PASS" else "WARN", "budget.streaming_pc_profile", P.show(true))
	end
end

local function checkTestKit(opts)
	local m = ServerStorage:FindFirstChild("PattayaTestKitServer")
	if not m then
		out("INFO", "testkit", "PattayaTestKitServer not installed")
		return
	end
	local ok, S = pcall(require, m)
	if not ok or not S.enabled then
		out("INFO", "testkit", "disabled (needs Studio or DevTest)")
		return
	end
	for _, l in string.split(S.report(), "\n") do
		if l ~= "" then
			out("INFO", "testkit.report", l)
		end
	end
	if opts.probe then
		local okP, summary, d = pcall(S.probePath, "RacePath", {every = 50})
		if okP then
			check("testkit.probe_central_loop", d.road >= 0.95 * d.n, summary)
		else
			check("testkit.probe_central_loop", false, tostring(summary))
		end
	end
end

function QA.run(opts): {string}
	opts = type(opts) == "table" and opts or {}
	table.clear(lines)
	for k in counts do
		counts[k] = 0
	end
	local t0 = os.clock()
	safe("context", checkContext)
	safe("remotes", checkRemotes)
	safe("scripts", checkScripts)
	safe("garage", checkGarage)
	safe("activities", checkActivities)
	safe("circuits", checkCircuits)
	safe("budgets", function() checkBudgets(opts) end)
	safe("testkit", function() checkTestKit(opts) end)
	local result = table.clone(lines)
	table.insert(result, 1, ("QA %d PASS, %d FAIL, %d WARN (%.0f ms)"):format(counts.PASS, counts.FAIL, counts.WARN,
		(os.clock() - t0) * 1000))
	return result
end

function QA.report(opts): string
	local s = table.concat(QA.run(opts), "\n")
	print(s)
	return s
end

return QA
