--!strict
-- Ranked circuit rating (MIDNIGHT PATTAYA). Pure maths: no Roblox services, no instances, no clock reads, so it runs
-- in the offline `luau` CLI as well as in Studio (ServerStorage.RankedRatingTest checks it).
-- Used by RaceSessionService.Ranked; the maths, the worked example and the test plan are in docs/RANKED_SYSTEM.md.
--
-- The rating is Elo extended to a multi-driver race:
-- * Every pair of rated drivers is one "duel". Finishing ahead = 1, behind = 0. Two DNFs draw (0.5). A DNF always
--   loses to every finisher.
-- * Expected score of A against B: E = 1 / (1 + 10^((Rb - Ra) / 400)).
-- * Change for A = K(A) / (N - 1) * sum over opponents of w * (S - E), rounded to a whole point.
-- * K shrinks with races played: K = K_MIN + (K_MAX - K_MIN) * K_HALF / (K_HALF + races) (48 for a new driver, 32 after
--   10 races, 16 in the long run).
-- * Glicko-lite: a provisional opponent (fewer than PROVISIONAL_RACES rated races) is less certain, so an established
--   driver's duel against them counts with weight PROVISIONAL_WEIGHT (0.5). New drivers move fast, settled ratings are
--   not dragged around by unknowns.
-- * A DNF never gains rating (its change is capped at 0).
-- * Ratings are kept between MIN_RATING and MAX_RATING.
-- * Seasons: each stored entry remembers its season id. When a new season has started, the entry is soft reset before
--   it is used: rating -> round((rating + DEFAULT) / 2), races -> min(races, SEASON_KEEP_RACES).
-- One rating per class bucket (Street / Sport / Super / Hyper / Track Spec / Equalised): RaceSessionService picks it.
local Rating = {}

Rating.DEFAULT = 1000
Rating.MIN_RATING = 100
Rating.MAX_RATING = 3000
Rating.PROVISIONAL_RACES = 5
Rating.PROVISIONAL_WEIGHT = 0.5
Rating.K_MAX = 48
Rating.K_MIN = 16
Rating.K_HALF = 10
Rating.SEASON_KEEP_RACES = 5

-- Season table. `starts` is a UTC unix time (os.time()). Add a row to start a new season; never edit a started one.
-- Before the first season starts, the first one is used.
Rating.SEASONS = {
	{id = 1, name = "Season 1", starts = 1790812800}, -- 2026-10-01 00:00 UTC
}

export type Entry = {rating: number, races: number, season: number}
export type Driver = {key: any, rating: number, races: number, dnf: boolean?}
export type Result = {key: any, old: number, new: number, delta: number, races: number, provisional: boolean,
	k: number, raw: number}

local function round(x: number): number
	return math.floor(x + 0.5)
end

local function clampRating(r: number): number
	return math.clamp(r, Rating.MIN_RATING, Rating.MAX_RATING)
end

function Rating.kFactor(races: number): number
	races = math.max(0, races)
	return Rating.K_MIN + (Rating.K_MAX - Rating.K_MIN) * Rating.K_HALF / (Rating.K_HALF + races)
end

function Rating.expected(ra: number, rb: number): number
	return 1 / (1 + 10 ^ ((rb - ra) / 400))
end

function Rating.isProvisional(races: number): boolean
	return races < Rating.PROVISIONAL_RACES
end

-- the season running at unix time t (the latest one that has started; the first one before any has)
function Rating.seasonAt(t: number, seasons: {any}?): any
	local list = seasons or Rating.SEASONS
	local best = list[1]
	for _, s in list do
		if s.starts <= t and s.starts >= best.starts then
			best = s
		end
	end
	return best
end

-- A stored entry made safe to use in season `seasonId`: missing or broken -> a fresh DEFAULT entry; from an earlier
-- season -> soft reset. Returns a new table (the stored one is not changed).
function Rating.normalise(stored: any, seasonId: number, default: number?): Entry
	local base = default or Rating.DEFAULT
	if type(stored) ~= "table" or type(stored.rating) ~= "number" or stored.rating ~= stored.rating then
		return {rating = base, races = 0, season = seasonId}
	end
	local rating = clampRating(stored.rating)
	local races = if type(stored.races) == "number" and stored.races >= 0 then math.floor(stored.races) else 0
	local season = if type(stored.season) == "number" then stored.season else seasonId
	if season < seasonId then
		rating = clampRating(round((rating + base) / 2))
		races = math.min(races, Rating.SEASON_KEEP_RACES)
	end
	return {rating = rating, races = races, season = seasonId}
end

-- drivers: the rated drivers in finishing order (index 1 = winner); DNFs last, flagged dnf = true.
-- Returns one Result per driver, same order. Fewer than 2 drivers -> no change for anyone.
function Rating.update(drivers: {Driver}): {Result}
	local n = #drivers
	local out: {Result} = {}
	for i, d in drivers do
		local k = Rating.kFactor(d.races)
		local sum = 0
		if n >= 2 then
			local mineProv = Rating.isProvisional(d.races)
			for j, o in drivers do
				if j ~= i then
					local s
					if d.dnf and o.dnf then
						s = 0.5
					elseif d.dnf then
						s = 0
					elseif o.dnf then
						s = 1
					else
						s = if i < j then 1 else 0
					end
					local w = if Rating.isProvisional(o.races) and not mineProv then Rating.PROVISIONAL_WEIGHT else 1
					sum += w * (s - Rating.expected(d.rating, o.rating))
				end
			end
		end
		local raw = if n >= 2 then k * sum / (n - 1) else 0
		if d.dnf and raw > 0 then
			raw = 0
		end
		local new = if n >= 2 then clampRating(round(d.rating + raw)) else d.rating
		local races = if n >= 2 then d.races + 1 else d.races
		out[i] = {key = d.key, old = d.rating, new = new, delta = new - d.rating, races = races,
			provisional = Rating.isProvisional(races), k = k, raw = raw}
	end
	return out
end

return Rating
