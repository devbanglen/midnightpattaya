--!strict
-- Player money / EXP / level (RayCity-style: races and missions pay money and EXP; levels gate content later).
-- Shown as leaderstats; saved with DataStoreService when the place allows it (Studio needs "Enable Studio Access to
-- API Services"; without it the values simply live for the session).
-- Record format, session lock and save timing: docs/RACING_ROUTE_DESIGN.md "Progression".
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")
local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")

local Progress = {}

local STORE_NAME = "PattayaProgress_v1"
local LOCK_TTL = 300 -- s: a lock from another session younger than this is live; older = that server died
local AUTOSAVE_EVERY = 120 -- s (also refreshes this session's locks, so they never go stale while we hold them)
local LOAD_TRIES = 3
-- this server's session id (JobId is empty in Studio)
local SESSION_ID = if game.JobId ~= "" then game.JobId else HttpService:GenerateGUID(false)

local store: any = nil
local warnedNoStore = false
local function noStore(why: string)
	store = nil
	if not warnedNoStore then
		warnedNoStore = true
		warn(("PattayaProgress: no DataStore (%s); progress lives for this session only"):format(why))
	end
end
do
	local okStore, ds = pcall(function()
		return DataStoreService:GetDataStore(STORE_NAME)
	end)
	if okStore then
		store = ds
	else
		noStore(tostring(ds))
	end
end

-- Studio without "Enable Studio Access to API Services": every request fails the same way. Switch to session-only
-- once (one warning) instead of warning and refusing to save per player.
local function isNoApiError(err: any): boolean
	if not RunService:IsStudio() then
		return false
	end
	local e = string.lower(tostring(err))
	return string.find(e, "studioaccesstoapisnotallowed", 1, true) ~= nil
		or string.find(e, "api services", 1, true) ~= nil or string.find(e, "api access", 1, true) ~= nil
end

local function expToNext(level: number): number
	return 100 + (level - 1) * 60
end
Progress.expToNext = expToNext

-- Titles: every earned one is kept in extra.titles (a set); the Title leaderstat shows the best by this rank.
Progress.TITLE_RANK = {["Road King"] = 3, ["Road Fighter"] = 2, ["Survivor"] = 1}

-- Free-form per-player data for other systems (garage cars, ...): Progress.GetData / SetData. Saved in the same record
-- under "extra"; old records without it load as an empty table.
local extra: {[Player]: {[string]: any}} = {}
-- players whose saved record could not be read: never overwrite their record with session defaults
local loadFailed: {[Player]: boolean} = {}
-- players whose record has been read (or there is no store): until then the values are defaults, never save them
local loaded: {[Player]: boolean} = {}
-- a save in flight: saves of one player never overlap, so a late autosave can't re-lock after the release
local saving: {[Player]: boolean} = {}
-- the final save (lock released) has started: no more saves for this player
local released: {[Player]: boolean} = {}

local function stats(plr: Player)
	return plr:FindFirstChild("leaderstats")
end

-- true when another live session holds the record (its lock is younger than LOCK_TTL)
local function lockedElsewhere(rec: any): boolean
	if type(rec) ~= "table" or type(rec.lock) ~= "table" then
		return false
	end
	local id, at = rec.lock.id, rec.lock.at
	return id ~= SESSION_ID and type(at) == "number" and os.time() - at < LOCK_TTL
end

local function bestTitle(titles: {[string]: any}): string
	local best, rank = "", -1
	for name, on in titles do
		local r = Progress.TITLE_RANK[name] or 0
		if on and (r > rank or (r == rank and name < best)) then
			best, rank = name, r
		end
	end
	return best
end

local function refreshTitle(plr: Player)
	local ls = stats(plr)
	local ex = extra[plr]
	if ls and ex and type(ex.titles) == "table" then
		ls.Title.Value = bestTitle(ex.titles)
	end
end

local function setup(plr: Player)
	local ls = Instance.new("Folder")
	ls.Name = "leaderstats"
	local level = Instance.new("IntValue")
	level.Name = "Level"
	level.Value = 1
	level.Parent = ls
	local money = Instance.new("IntValue")
	money.Name = "Money"
	money.Parent = ls
	local exp = Instance.new("IntValue")
	exp.Name = "EXP"
	exp.Parent = ls
	local title = Instance.new("StringValue") -- best earned title ("Road King" > "Road Fighter" > "Survivor")
	title.Name = "Title"
	title.Parent = ls
	plr:SetAttribute("RoadFight", 0) -- bit k-1 set = Road Fight boss of order k beaten
	ls.Parent = plr
	extra[plr] = {}
	local data: any = nil
	if store then
		-- Read the record and claim it for this session in one UpdateAsync. A record locked by another live session
		-- (a fast rejoin while the old server is still saving) is left alone: retried, then treated as load-failed.
		local ok, err, busy = false, nil, false
		for attempt = 1, LOAD_TRIES do -- a single transient DataStore error used to disable saving for the session
			busy = false
			ok, err = pcall(function()
				(store :: any):UpdateAsync("p" .. plr.UserId, function(old: any): any
					data = old
					busy = lockedElsewhere(old)
					if busy then
						return nil -- cancel: no write
					end
					local rec: any = if type(old) == "table" then old else {}
					rec.lock = {id = SESSION_ID, at = os.time()}
					return rec
				end)
			end)
			if (ok and not busy) or not plr.Parent or (not ok and isNoApiError(err)) then
				break
			end
			task.wait(attempt * 2)
		end
		if not plr.Parent then
			-- left while the record was loading: PlayerRemoving has run already, don't leave state behind
			extra[plr] = nil
			loadFailed[plr] = nil
			if ok and not busy then
				-- we claimed the record: give the lock back so the player's next server can load it at once
				pcall(function()
					(store :: any):UpdateAsync("p" .. plr.UserId, function(old: any): any
						if type(old) ~= "table" or type(old.lock) ~= "table" or old.lock.id ~= SESSION_ID then
							return nil
						end
						(old :: any).lock = nil
						return old
					end)
				end)
			end
			return
		end
		if not ok and isNoApiError(err) then
			noStore("Studio without API access")
			data = nil
		elseif not ok or busy then
			loadFailed[plr] = true
			data = nil
			warn(("PattayaProgress: could not load %s's progress (%s); it will not be saved this session")
				:format(plr.Name, if busy then "record locked by another live server" else tostring(err)))
		end
	end
	if type(data) == "table" then
		level.Value = data.level or 1
		money.Value = data.money or 0
		exp.Value = data.exp or 0
		plr:SetAttribute("RoadFight", data.roadFight or 0)
		if type(data.extra) == "table" then
			extra[plr] = data.extra
		end
	end
	-- titles: the set in extra.titles; older records only have the single `title` string. Road Fight titles earned
	-- before titles were a set are re-granted from the saved RoadFight bits (a Survivor title used to block
	-- Road Fighter).
	local ex = extra[plr]
	local titles = if type(ex.titles) == "table" then ex.titles else {}
	if type(data) == "table" and type(data.title) == "string" and data.title ~= "" then
		titles[data.title] = true
	end
	local rf = tonumber(plr:GetAttribute("RoadFight")) or 0
	if bit32.band(rf, 7) == 7 then
		titles["Road Fighter"] = true
	end
	if bit32.band(rf, 8) ~= 0 then
		titles["Road King"] = true
	end
	ex.titles = titles
	title.Value = bestTitle(titles)
	loaded[plr] = true
	plr:SetAttribute("ProgressLoaded", true) -- GetData is meaningful from here on
end

-- release = true: the player is leaving (or the server closes). The lock is cleared so the next server can load the
-- record at once, and no later save runs for this player.
local function save(plr: Player, release: boolean?)
	if released[plr] then
		-- the final save is already running (PlayerRemoving and BindToClose both call this): wait for it, so the
		-- BindToClose budget covers it
		local w = 0
		while saving[plr] and w < 30 do
			w += task.wait(0.1)
		end
		return
	end
	-- one save at a time per player: a release waits for an autosave in flight (else that autosave could land last
	-- and leave a fresh lock behind, which would block the player's next server for LOCK_TTL)
	local waited = 0
	while saving[plr] and waited < 30 do
		waited += task.wait(0.1)
	end
	if released[plr] then
		return save(plr, release) -- another final save started while we waited: wait for that one
	end
	local ls = stats(plr)
	if not (store and ls and extra[plr] and loaded[plr]) or loadFailed[plr] then
		return
	end
	if release then
		released[plr] = true
	end
	-- the record is built before the first yield (PlayerRemoving clears the tables after this returns)
	local data = {level = ls.Level.Value, money = ls.Money.Value, exp = ls.EXP.Value, title = ls.Title.Value,
		roadFight = plr:GetAttribute("RoadFight") or 0, extra = extra[plr],
		lock = if release then nil else {id = SESSION_ID, at = os.time()}}
	local stolen = false
	saving[plr] = true
	local ok, err = pcall(function()
		(store :: any):UpdateAsync("p" .. plr.UserId, function(old: any): any
			stolen = lockedElsewhere(old)
			if stolen then
				return nil -- another live session took the record over (our lock went stale): never overwrite it
			end
			if data.lock then
				data.lock.at = os.time()
			end
			return data
		end)
	end)
	saving[plr] = nil
	if not ok then
		warn(("PattayaProgress: saving %s's progress failed: %s"):format(plr.Name, tostring(err)))
	elseif stolen then
		warn(("PattayaProgress: %s's record is locked by another server; this session's save was skipped")
			:format(plr.Name))
	end
end

-- Returns the number of levels gained.
function Progress.Award(plr: Player, money: number, exp: number, reason: string): number
	local ls = stats(plr)
	if not ls then
		return 0
	end
	ls.Money.Value += math.floor(money)
	ls.EXP.Value += math.floor(exp)
	local gained = 0
	while ls.EXP.Value >= expToNext(ls.Level.Value) do
		ls.EXP.Value -= expToNext(ls.Level.Value)
		ls.Level.Value += 1
		gained += 1
	end
	plr:SetAttribute("LastReward", ("+%d ฿  +%d EXP  (%s)%s"):format(money, exp, reason, if gained > 0 then "  LEVEL UP!" else ""))
	plr:SetAttribute("LastRewardAt", workspace:GetServerTimeNow())
	return gained
end

-- Adds an earned title to the player's set (kept for good, saved as extra.titles) and shows the best one by
-- Progress.TITLE_RANK in the Title leaderstat. Returns true when the title is new for this player.
function Progress.GrantTitle(plr: Player, name: string): boolean
	local ex = extra[plr]
	if not ex then
		return false
	end
	if type(ex.titles) ~= "table" then
		ex.titles = {}
	end
	local isNew = not ex.titles[name]
	ex.titles[name] = true
	refreshTitle(plr)
	return isNew
end

-- Overrides the whole title set (dev / test kit only): "" clears every title, a name leaves just that one.
function Progress.SetTitle(plr: Player, title: string)
	local ex = extra[plr]
	if ex then
		ex.titles = if title ~= "" then {[title] = true} else {}
	end
	local ls = stats(plr)
	if ls then
		ls.Title.Value = title
	end
end

-- Value stored under `key` for this player (nil before the record has loaded: check attribute ProgressLoaded).
-- Tables are returned by reference; call SetData after changing one.
-- GetData(plr, "titles") = every earned title as a set ({["Survivor"] = true, ...}); change it via GrantTitle.
function Progress.GetData(plr: Player, key: string): any
	local t = extra[plr]
	return t and t[key]
end

-- Stores a DataStore-safe value (string/number/boolean/nil or a table of those with string keys or array form).
-- Saved with the rest of the record by the autosave, when the player leaves and when the server closes.
function Progress.SetData(plr: Player, key: string, value: any)
	local t = extra[plr]
	if t then
		t[key] = value
	end
end

local started = false
function Progress.Start()
	if started then
		return
	end
	started = true
	for _, p in Players:GetPlayers() do
		task.spawn(setup, p)
	end
	Players.PlayerAdded:Connect(setup)
	Players.PlayerRemoving:Connect(function(p)
		save(p, true) -- builds the record before it yields; releases the session lock
		extra[p] = nil
		loadFailed[p] = nil
		loaded[p] = nil
		saving[p] = nil
		released[p] = nil
	end)
	-- autosave: a server crash loses at most AUTOSAVE_EVERY seconds, and this session's locks stay fresh
	task.spawn(function()
		while true do
			task.wait(AUTOSAVE_EVERY)
			for _, p in Players:GetPlayers() do
				if store and loaded[p] and not loadFailed[p] and not saving[p] and not released[p] then
					task.spawn(save, p)
				end
			end
		end
	end)
	game:BindToClose(function()
		-- every player in parallel (one by one could run past the 30 s close budget with many players)
		local pending = 0
		for _, p in Players:GetPlayers() do
			pending += 1
			task.spawn(function()
				save(p, true)
				pending -= 1
			end)
		end
		local t0 = os.clock()
		while pending > 0 and os.clock() - t0 < 25 do
			task.wait(0.1)
		end
	end)
end

return Progress
