-- Unit test for ServerStorage.RankedRating (dev only: nothing in the game requires it).
-- Studio, command bar (Server or Edit mode):
--   print(require(game.ServerStorage.RankedRatingTest)())
-- Offline with the luau CLI: pass the module in, e.g. require("./RankedRatingTest")(require("./RankedRating")).
-- Returns (summary: string, allPassed: boolean). It never errors on a failed check; it lists them in the summary.
-- The expected numbers are the worked examples in docs/RANKED_SYSTEM.md.
return function(module: any?): (string, boolean)
	local R = module
	if R == nil then
		R = require((game :: any):GetService("ServerStorage"):WaitForChild("RankedRating"))
	end
	local passed, failed = 0, {}
	local function check(name: string, cond: boolean, detail: string?)
		if cond then
			passed += 1
		else
			table.insert(failed, name .. (if detail then " (" .. detail .. ")" else ""))
		end
	end
	local function eq(name: string, got: any, want: any)
		check(name, got == want, ("got %s, want %s"):format(tostring(got), tostring(want)))
	end
	local function near(name: string, got: number, want: number, tol: number)
		check(name, math.abs(got - want) <= tol, ("got %.4f, want %.4f"):format(got, want))
	end

	-- K factor and expected score
	eq("K new driver", R.kFactor(0), 48)
	eq("K after 10 races", R.kFactor(10), 32)
	near("K long run", R.kFactor(1e9), 16, 1e-6)
	near("K after 20 races", R.kFactor(20), 26.6667, 1e-3)
	near("E equal", R.expected(1000, 1000), 0.5, 1e-9)
	near("E 1000 vs 1200", R.expected(1000, 1200), 0.2403, 1e-4)
	near("E symmetric", R.expected(1300, 1100) + R.expected(1100, 1300), 1, 1e-9)

	-- two new drivers (the Studio 2-player test): race 1, race 2 same winner, race 3 reversed
	local r1 = R.update({{key = "P1", rating = 1000, races = 0}, {key = "P2", rating = 1000, races = 0}})
	eq("2p race 1 winner", r1[1].new, 1024)
	eq("2p race 1 loser", r1[2].new, 976)
	eq("2p race 1 delta", r1[1].delta, 24)
	eq("2p race 1 races", r1[1].races, 1)
	eq("2p race 1 provisional", r1[1].provisional, true)
	local r2 = R.update({{key = "P1", rating = 1024, races = 1}, {key = "P2", rating = 976, races = 1}})
	eq("2p race 2 winner", r2[1].new, 1043)
	eq("2p race 2 loser", r2[2].new, 957)
	local r3 = R.update({{key = "P2", rating = 957, races = 2}, {key = "P1", rating = 1043, races = 2}})
	eq("2p race 3 upset winner", r3[1].new, 984)
	eq("2p race 3 upset loser", r3[2].new, 1016)

	-- worked example: A new (1000, 0 races) wins, B (1200, 20 races) second, C (1100, 8 races) DNF
	local w = R.update({
		{key = "A", rating = 1000, races = 0},
		{key = "B", rating = 1200, races = 20},
		{key = "C", rating = 1100, races = 8, dnf = true},
	})
	eq("example A", w[1].new, 1034)
	eq("example B", w[2].new, 1200)
	eq("example C", w[3].new, 1089)
	near("example A raw", w[1].raw, 33.5955, 1e-3)
	near("example B raw", w[2].raw, -0.2658, 1e-3)
	near("example C raw", w[3].raw, -11.4839, 1e-3)
	eq("example keys keep order", w[3].key, "C")

	-- provisional ends after the 5th race
	local p = R.update({{key = "a", rating = 1000, races = 4}, {key = "b", rating = 1000, races = 30}})
	eq("5th race ends provisional", p[1].provisional, false)
	eq("5th race count", p[1].races, 5)

	-- a DNF never gains: a low-rated DNF draws a high-rated DNF (would be a big gain) and loses to a finisher
	local d = R.update({
		{key = "fin", rating = 2000, races = 50},
		{key = "lowDnf", rating = 600, races = 50, dnf = true},
		{key = "highDnf", rating = 2000, races = 50, dnf = true},
	})
	eq("DNF gain capped at 0", d[2].delta, 0)
	check("DNF raw capped", d[2].raw == 0)
	check("high DNF loses", d[3].delta < 0)
	-- all DNF and equal: nobody moves
	local dd = R.update({{key = 1, rating = 1000, races = 9, dnf = true}, {key = 2, rating = 1000, races = 9, dnf = true}})
	eq("double DNF equal", dd[1].delta + dd[2].delta, 0)

	-- bounds
	local top = R.update({{key = 1, rating = 2995, races = 0}, {key = 2, rating = 3000, races = 0}})
	check("max bound", top[1].new <= R.MAX_RATING, tostring(top[1].new))
	local bottom = R.update({{key = 1, rating = 3000, races = 0}, {key = 2, rating = 105, races = 0}})
	check("min bound", bottom[2].new >= R.MIN_RATING, tostring(bottom[2].new))

	-- one driver: no change
	local solo = R.update({{key = 1, rating = 1234, races = 3}})
	eq("solo unchanged", solo[1].new, 1234)
	eq("solo races unchanged", solo[1].races, 3)

	-- seasons and stored entries
	local seasons = {{id = 1, starts = 100}, {id = 2, starts = 200}}
	eq("season before first", R.seasonAt(50, seasons).id, 1)
	eq("season 1", R.seasonAt(150, seasons).id, 1)
	eq("season 2", R.seasonAt(200, seasons).id, 2)
	local soft = R.normalise({rating = 1400, races = 30, season = 1}, 2)
	eq("soft reset rating", soft.rating, 1200)
	eq("soft reset races", soft.races, 5)
	eq("soft reset season", soft.season, 2)
	local same = R.normalise({rating = 1400, races = 30, season = 2}, 2)
	eq("same season kept", same.rating, 1400)
	eq("same season races", same.races, 30)
	eq("missing entry", R.normalise(nil, 2).rating, 1000)
	eq("broken entry", R.normalise({rating = "x"}, 2).rating, 1000)
	eq("clamped entry", R.normalise({rating = 99999, races = 1, season = 2}, 2).rating, R.MAX_RATING)
	check("real season table", R.seasonAt(os.time()).id >= 1)

	local total = passed + #failed
	if #failed == 0 then
		return ("RankedRating: %d/%d checks passed"):format(passed, total), true
	end
	return ("RankedRating: %d/%d checks passed. FAILED: %s"):format(passed, total, table.concat(failed, "; ")), false
end
