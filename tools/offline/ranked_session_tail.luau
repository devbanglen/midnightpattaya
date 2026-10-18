end

local Service = loadRSS()
Service.init(function(plr, kind, payload) table.insert(sent, {to = plr.Name, kind = kind, payload = payload}) end)

local fails = 0
lastTower = nil
local function check(name, cond, detail)
	print((if cond then "PASS " else "FAIL ") .. name .. (if detail then "  " .. tostring(detail) else ""))
	if not cond then fails += 1 end
end

local function lastOf(kind, to)
	for i = #sent, 1, -1 do
		if sent[i].kind == kind and (to == nil or sent[i].to == to) then return sent[i].payload end
	end
	return nil
end

-- runs one formal race; finishOrder = players who finish, in order; the rest are DNF. Returns the results payload.
local function race(opts, list, finishOrder, tweak)
	sent = {}
	local ok, why = Service.join(list[1], opts)
	assert(ok, why)
	for i = 2, #list do
		if opts.mode == "PrivateRoom" then Service.invite(list[1], list[i].UserId) end
		local ok2, why2 = Service.join(list[i], {mode = opts.mode, join = true})
		assert(ok2, why2)
	end
	if opts.mode == "PrivateRoom" then Service.start(list[1]) end
	step(26) -- forming over -> grid
	step(3.1) -- lights
	step(8) -- lights out -> racing
	for _, plr in list do
		local p = Service.partOf(plr)
		local at = table.find(finishOrder, plr)
		if at then
			p.finished, p.raceTime, p.crossOrder = true, 30 + at, at
		else
			p.dnf = "DNF"
		end
	end
	if tweak then tweak(list) end
	step(0.1) -- results
	local res = lastOf("results")
	lastTower = lastOf("tower")
	step(13) -- results over -> idle
	return res
end

local A = newPlayer("Player1", -1, "Sport")
local B = newPlayer("Player2", -2, "Sport")

-- 1. ranked off (default): nothing changes
local r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A, B})
check("off: results sent", r ~= nil)
check("off: not ranked", r and r.ranked == false and r.unranked == nil)
check("off: no rating fields", r and r.rows[1].rating == nil)
check("off: nothing saved", store[A] == nil or store[A].circuitRating == nil)

-- 2. on via the ServerStorage attribute: 1024 / 976
game:GetService("ServerStorage"):SetAttribute("RankedEnabled", true)
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A, B})
check("on: ranked", r and r.ranked == true, r and r.unranked)
check("on: bucket Sport", r and r.bucket == "Sport")
check("on: P1 1024 +24", r and r.rows[1].rating == 1024 and r.rows[1].ratingDelta == 24)
check("on: P2 976 -24", r and r.rows[2].rating == 976 and r.rows[2].ratingDelta == -24)
check("on: provisional", r and r.rows[1].provisional == true and r.rows[1].ratedRaces == 1)
check("on: saved", store[A].circuitRating.Sport.rating == 1024 and store[B].circuitRating.Sport.rating == 976
	and store[A].circuitRating.Sport.season == 1, store[A].circuitRating.Sport.rating)
check("on: ratingSaved", r and r.rows[1].ratingSaved == true)
check("on: board submit", #submitted == 2 and submitted[1][2] == "Sport" and submitted[1][4] == 1024)
check("on: tower ranked flag", lastTower ~= nil and lastTower.ranked == true)

-- 3. second race, same winner: 1043 / 957
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A, B})
check("race 2: 1043 / 957", r and r.rows[1].rating == 1043 and r.rows[2].rating == 957,
	r and (r.rows[1].rating .. "/" .. r.rows[2].rating))

-- 4. too short (1 lap on the 1565-stud oval)
r = race({mode = "CircuitRace", laps = 1}, {A, B}, {A, B})
check("short: unranked", r and r.ranked == false and r.unranked == "too short (2+ laps here)", r and r.unranked)
check("short: unchanged", store[A].circuitRating.Sport.rating == 1043)

-- 5. private room is never ranked
r = race({mode = "PrivateRoom", laps = 3}, {A, B}, {A, B})
check("private: not ranked", r and r.ranked == false and r.unranked == nil)
check("private: unchanged", store[A].circuitRating.Sport.rating == 1043)

-- 6. open modes never ranked (session flag)
Service.join(A, {mode = "TimeAttack"})
check("time attack: no ranked flag", Service.partOf(A).session.ranked == false)
Service.leave(A)

-- 7. mixed classes
B._seat.Parent._attrs.Class = "Street"
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A, B})
check("mixed: unranked", r and r.ranked == false and r.unranked == "mixed classes", r and r.unranked)
B._seat.Parent._attrs.Class = "Sport"

-- 8. disqualified driver voids the race
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A}, function(list) Service.partOf(B).dq = true end)
check("dq: unranked", r and r.ranked == false and r.unranked == "a driver was disqualified", r and r.unranked)

-- 9. solo race
r = race({mode = "CircuitRace", laps = 3}, {A}, {A})
check("solo: unranked", r and r.unranked == "needs 2 or more drivers", r and r.unranked)

-- 10. DNF: B does not finish -> loses (957 vs 1043, K(2)=42.67)
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {A})
check("dnf: ranked", r and r.ranked == true, r and r.unranked)
check("dnf: B row DNF rated", r and r.rows[2].status == "DNF" and r.rows[2].ratingDelta < 0,
	r and r.rows[2].ratingDelta)

-- 11. nobody finished
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {})
check("all dnf: unranked", r and r.unranked == "nobody finished", r and r.unranked)

-- 12. Equalised: own bucket
A._attrs.Equalised, B._attrs.Equalised = true, true
r = race({mode = "CircuitRace", laps = 3}, {A, B}, {B, A})
check("equalised bucket", r and r.ranked and r.bucket == "Equalised" and r.rows[1].rating == 1024, r and r.bucket)
check("equalised kept apart", store[A].circuitRating.Sport ~= nil and store[A].circuitRating.Equalised.rating == 976)
A._attrs.Equalised, B._attrs.Equalised = nil, nil

-- 13. driver who left the game mid-race: rated against, not saved, does not error
local C = newPlayer("Player3", -3, "Sport")
r = race({mode = "CircuitRace", laps = 3}, {A, B, C}, {A, B}, function() C.Parent = nil end)
check("leaver: ranked", r and r.ranked == true, r and r.unranked)
check("leaver: row rated not saved", r and r.rows[3].rating ~= nil and r.rows[3].ratingSaved == nil)
check("leaver: nothing stored", store[C] == nil or store[C].circuitRating == nil)

-- 14. menu info
local info = Service.menuInfo(A)
check("menu ranked info", info.ranked and info.ranked.bucket == "Sport" and info.ranked.minLaps == 2
	and info.ranked.rating == store[A].circuitRating.Sport.rating, info.ranked and info.ranked.rating)

print(("%d failures"):format(fails))
