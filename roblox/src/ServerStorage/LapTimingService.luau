-- Lap and sector timing for one participant, driven only by validated gate events from CheckpointValidator (server
-- clock, crossing time interpolated between samples). Client times are never used.
-- Sectors end at the gates CircuitRegistry marks with `line` (2 = end of sector 1, 3 = end of sector 2,
-- 1 = start/finish = end of sector 3 and of the lap).
-- A lap is valid unless something invalidated it (missed gate/cut, track limits, teleport, reset, pit speeding, wrong
-- way, jump start): invalid laps are shown but never become a best or a record.
-- Split colours (computed here, drawn by the client): "purple" = best of everyone (session/global), "green" = the
-- driver's personal best, "yellow" = slower, "invalid" = lap already invalid.
local Timing = {}

local Timer = {}
Timer.__index = Timer

-- opts.pbLap / opts.pbSectors: saved personal best (LeaderboardService) so the first lap can already show green
function Timing.new(opts)
	opts = opts or {}
	return setmetatable({
		lap = 0, -- lap in progress (0 = not started: out lap / before the first line crossing)
		completed = 0, -- laps completed (valid or not)
		lapStart = nil,
		sector = 1, -- sector in progress
		sectorStart = nil,
		cur = {}, -- sector times of the lap in progress
		valid = true,
		reason = nil,
		lastLap = nil,
		lastValid = nil,
		bestLap = opts.pbLap, -- personal best lap (saved PB or this session)
		bestSectors = table.clone(opts.pbSectors or {}),
		sessionBest = nil, -- best valid lap this session
		laps = {}, -- {time, valid, sectors}
	}, Timer)
end

function Timer:startLap(t: number)
	self.lap += 1
	self.lapStart = t
	self.sector = 1
	self.sectorStart = t
	self.cur = {}
	self.valid = true
	self.reason = nil
end

-- returns true when this call made the lap invalid (so the caller can tell the driver once)
function Timer:invalidate(reason: string): boolean
	if self.lap > 0 and self.valid then
		self.valid = false
		self.reason = reason
		return true
	end
	return false
end

local function colour(time: number, valid: boolean, personal: number?, overall: number?): string
	if not valid then
		return "invalid"
	end
	if not overall or time <= overall then
		return "purple"
	end
	if not personal or time <= personal then
		return "green"
	end
	return "yellow"
end

-- A validated gate event. `refs` = {lap = overall best lap, sectors = {s1, s2, s3}} (session/global, may be empty).
-- `raceStart`: for a race, lap 1 is timed from the lights going out instead of the first line crossing.
-- Returns a list of results: {kind = "sector", n, time, colour} / {kind = "lap", lap, time, valid, colour, pb,
-- sectors, reason} / {kind = "start", lap}
function Timer:onGate(gate, t: number, refs, raceStart: number?)
	local out = {}
	refs = refs or {}
	local line = gate.line
	if not line then
		return out
	end
	if self.lap == 0 then
		if line == 1 then
			self:startLap(raceStart or t)
			table.insert(out, {kind = "start", lap = self.lap})
		end
		return out
	end
	-- which sector this line ends: line 2 -> 1, line 3 -> 2, line 1 -> 3
	local ends = if line == 1 then 3 else line - 1
	if ends ~= self.sector then
		-- a sector line out of order (only after a resync): the split is meaningless, the lap is not
		self:invalidate("missed sector")
		self.sector = ends
	end
	local st = t - (self.sectorStart or t)
	self.cur[ends] = st
	local refS = refs.sectors and refs.sectors[ends]
	local col = colour(st, self.valid, self.bestSectors[ends], refS)
	if self.valid and (not self.bestSectors[ends] or st < self.bestSectors[ends]) then
		self.bestSectors[ends] = st
	end
	table.insert(out, {kind = "sector", n = ends, time = st, colour = col})
	self.sectorStart = t
	self.sector = ends % 3 + 1
	if ends == 3 then
		local lt = t - (self.lapStart :: number)
		local valid = self.valid
		local pb = valid and (not self.bestLap or lt < self.bestLap)
		local lcol = colour(lt, valid, self.bestLap, refs.lap)
		if pb then
			self.bestLap = lt
		end
		if valid and (not self.sessionBest or lt < self.sessionBest) then
			self.sessionBest = lt
		end
		self.lastLap, self.lastValid = lt, valid
		self.completed += 1
		local sectors = {self.cur[1], self.cur[2], self.cur[3]}
		table.insert(self.laps, {time = lt, valid = valid, sectors = sectors})
		table.insert(out, {kind = "lap", lap = self.lap, time = lt, valid = valid, colour = lcol, pb = pb,
			sectors = sectors, reason = self.reason})
		self:startLap(t)
	end
	return out
end

return Timing
