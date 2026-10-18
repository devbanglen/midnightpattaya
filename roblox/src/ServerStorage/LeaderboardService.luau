-- Circuit lap records.
-- * Personal best per circuit: saved with the player's progress record (PattayaProgress.GetData/SetData key
--   "circuitPB" = {[circuitId] = {lap, s = {s1, s2, s3}, car, class, at}}), so it needs no extra DataStore budget.
-- * Global best: OrderedDataStore "CircuitBest_<id>", key "u<userId>", value = lap in milliseconds (lower is
--   better, read ascending). All calls are in pcall. In Studio without API access (or when the store fails) the
--   board falls back to this server's session memory; after a failure the store is not retried for 5 minutes.
-- * Friends board: global top 100 + this server's session times, filtered with plr:IsFriendsWith (pcall, cached).
--   Limits: friends outside the global top 100 who are not on this server are not shown; IsFriendsWith is a web
--   call, cached for 10 minutes per pair.
-- * Overall bests for purple splits: best known lap (global top 1 or session) and this server's best sectors.
-- Only valid laps are ever submitted (RaceSessionService checks), and only from server timing.
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")

local Leaderboard = {}

local PB_KEY = "circuitPB"
local TOP_N = 100
local REFRESH = 60
local RETRY_AFTER = 300

local Progress = nil
local stores = {} -- [circuitId] = OrderedDataStore
local cache = {} -- [circuitId] = {at, rows = {{userId, name, time}}}
local session = {} -- [circuitId] = {[userId] = {userId, name, time}}
local sessionSectors = {} -- [circuitId] = {s1, s2, s3}
local storeDownUntil = 0
local names = {} -- [userId] = name
local friendCache = {} -- [plr] = {[userId] = {value, at}}

function Leaderboard.init(progressModule)
	Progress = progressModule
end

local function storeFor(id: string)
	if os.clock() < storeDownUntil then
		return nil
	end
	if stores[id] == nil then
		local ok, s = pcall(function()
			return DataStoreService:GetOrderedDataStore("CircuitBest_" .. id)
		end)
		stores[id] = if ok then s else false
	end
	return stores[id] or nil
end

local function storeFailed(err)
	storeDownUntil = os.clock() + RETRY_AFTER
	warn("[Circuit] lap record store unavailable, using session memory: " .. tostring(err))
end

local function nameOf(userId: number): string
	if names[userId] then
		return names[userId]
	end
	local p = Players:GetPlayerByUserId(userId)
	if p then
		names[userId] = p.DisplayName
		return p.DisplayName
	end
	local ok, n = pcall(function()
		return Players:GetNameFromUserIdAsync(userId)
	end)
	names[userId] = if ok and n then n else ("#" .. userId)
	return names[userId]
end

-- personal best --------------------------------------------------------------------------------------------------
function Leaderboard.getPB(plr: Player, id: string)
	local all = Progress and Progress.GetData(plr, PB_KEY)
	return type(all) == "table" and all[id] or nil
end

-- A valid lap from server timing. `global` = also write it to the OrderedDataStore (Time Attack laps only).
-- Returns {pb = bool, record = bool (faster than every lap known: global board + this server)}.
function Leaderboard.submit(plr: Player, id: string, lap: number, sectors: {number}, carId: string?, class: string?,
	global: boolean?)
	local result = {pb = false, record = false}
	local all = Progress and Progress.GetData(plr, PB_KEY)
	all = if type(all) == "table" then all else {}
	local old = all[id]
	if not old or lap < old.lap then
		-- a lap that started mid-lap (race grid ahead of the line, armAt) has no sector 1 (or 2): an array with a hole
		-- may not serialise, and this table is saved inside the whole progress record. Keep sectors only when complete.
		local complete = type(sectors[1]) == "number" and type(sectors[2]) == "number" and type(sectors[3]) == "number"
		all[id] = {lap = lap, s = if complete then {sectors[1], sectors[2], sectors[3]} else nil, car = carId,
			class = class, at = os.time()}
		if Progress then
			Progress.SetData(plr, PB_KEY, all)
		end
		result.pb = true
	end
	-- overall best before this lap
	local best = Leaderboard.overallLap(id)
	if not best or lap < best then
		result.record = true
	end
	-- session memory
	session[id] = session[id] or {}
	local mine = session[id][plr.UserId]
	if not mine or lap < mine.time then
		session[id][plr.UserId] = {userId = plr.UserId, name = plr.DisplayName, time = lap}
	end
	names[plr.UserId] = plr.DisplayName
	-- best sectors on this server (purple)
	local ss = sessionSectors[id] or {}
	for k = 1, 3 do
		if sectors[k] and (not ss[k] or sectors[k] < ss[k]) then
			ss[k] = sectors[k]
		end
	end
	sessionSectors[id] = ss
	-- global store, only for a personal best (keeps the write budget small)
	if result.pb and global then
		local ms = math.floor(lap * 1000 + 0.5)
		task.spawn(function()
			local store = storeFor(id)
			if not store then
				return
			end
			local ok, err = pcall(function()
				store:UpdateAsync("u" .. plr.UserId, function(oldMs)
					if type(oldMs) == "number" and oldMs <= ms then
						return nil -- keep the faster one
					end
					return ms
				end)
			end)
			if not ok then
				storeFailed(err)
			end
			if cache[id] then
				cache[id].at = 0 -- refresh soon
			end
		end)
	end
	return result
end

-- boards -----------------------------------------------------------------------------------------------------------
local refreshing = {}
local function refresh(id: string)
	if refreshing[id] then
		return
	end
	refreshing[id] = true
	task.spawn(function()
		local rows = {}
		local store = storeFor(id)
		if store then
			local ok, res = pcall(function()
				return store:GetSortedAsync(true, TOP_N):GetCurrentPage()
			end)
			if ok then
				for _, e in res do
					local userId = tonumber(string.sub(e.key, 2))
					if userId and type(e.value) == "number" then
						table.insert(rows, {userId = userId, time = e.value / 1000})
					end
				end
				for _, r in rows do
					r.name = nameOf(r.userId)
				end
			else
				storeFailed(res)
			end
		end
		cache[id] = {at = os.clock(), rows = rows}
		refreshing[id] = nil
	end)
end

-- merged global (cached) + session rows, best first, one row per player
local function merged(id: string)
	local c = cache[id]
	if not c or os.clock() - c.at > REFRESH then
		refresh(id)
	end
	local byUser = {}
	for _, r in (c and c.rows or {}) do
		byUser[r.userId] = {userId = r.userId, name = r.name, time = r.time}
	end
	for userId, r in session[id] or {} do
		if not byUser[userId] or r.time < byUser[userId].time then
			byUser[userId] = {userId = userId, name = r.name, time = r.time}
		end
	end
	local rows = {}
	for _, r in byUser do
		table.insert(rows, r)
	end
	table.sort(rows, function(a, b) return a.time < b.time end)
	return rows
end

function Leaderboard.top(id: string, n: number?)
	local rows = merged(id)
	local out = {}
	for i = 1, math.min(n or 10, #rows) do
		out[i] = rows[i]
	end
	return out
end

-- at most this many IsFriendsWith web calls per friends() request; cached answers (10 min per player) are free
local FRIEND_CALLS_PER_REQUEST = 25

-- returns (isFriend, usedWebCall); nil when the answer is not cached and the budget is spent
local function isFriend(plr: Player, userId: number, canCall: boolean): (boolean?, boolean)
	if userId == plr.UserId then
		return true, false
	end
	local cache = friendCache[plr]
	if not cache then
		if not plr.Parent then
			return false, false -- left: don't recreate the cache PlayerRemoving cleared
		end
		cache = {}
		friendCache[plr] = cache
	end
	local e = cache[userId]
	if e and os.clock() - e.at < 600 then
		return e.value, false
	end
	if not canCall then
		return nil, false
	end
	local ok, v = pcall(function()
		return plr:IsFriendsWith(userId)
	end)
	if friendCache[plr] then -- may have left while the call yielded
		friendCache[plr][userId] = {value = ok and v == true, at = os.clock()}
	end
	return ok and v == true, true
end

-- yields (IsFriendsWith): call from a task, not from Heartbeat.
-- A cold cache costs at most FRIEND_CALLS_PER_REQUEST web calls per request (it used to be up to 100); rows past the
-- budget are skipped this time and get checked by later requests as the cache warms.
function Leaderboard.friends(plr: Player, id: string, n: number?)
	local out = {}
	local calls = 0
	for _, r in merged(id) do
		local friend, called = isFriend(plr, r.userId, calls < FRIEND_CALLS_PER_REQUEST)
		if called then
			calls += 1
		end
		if friend then
			table.insert(out, r)
			if #out >= (n or 10) then
				break
			end
		end
	end
	return out
end

function Leaderboard.overallLap(id: string): number?
	local rows = merged(id)
	return rows[1] and rows[1].time or nil
end

function Leaderboard.overallSectors(id: string)
	return sessionSectors[id] or {}
end

Players.PlayerRemoving:Connect(function(plr)
	friendCache[plr] = nil
end)

return Leaderboard
