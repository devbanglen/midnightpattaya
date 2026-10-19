-- Mobile playtest telemetry, server side (MIDNIGHT PATTAYA, 2026-10-20). Receives the samples sent by
-- PattayaPerfTelemetry.client (owner only), prints one line per sample to the server log (Developer Console →
-- Server) and keeps the session in DataStore "PerfTelemetry_v1", key "<userId>_<sessionStart>" (list of samples,
-- capped at 720 = 2 h). Index key "<userId>_sessions" lists the session keys (last 20). The leader reads them with
-- Open Cloud (Data Stores) or from Studio. Saves at most every 30 s per session and on leave. Only the experience
-- owner (or a player with attribute PerfTelemetry) is recorded; anything else is ignored.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local DataStoreService = game:GetService("DataStoreService")
local RunService = game:GetService("RunService")

local remote = ReplicatedStorage:FindFirstChild("PerfTelemetry") or Instance.new("RemoteEvent")
remote.Name = "PerfTelemetry"
remote.Parent = ReplicatedStorage

local store: DataStore? = nil
if not RunService:IsStudio() then
	local ok, s = pcall(function()
		return DataStoreService:GetDataStore("PerfTelemetry_v1")
	end)
	if ok then store = s end
end

local sessions = {} -- [player] = {key, samples, dirty, lastSave}

local function allowed(plr: Player): boolean
	return plr.UserId == game.CreatorId or plr:GetAttribute("PerfTelemetry") == true
end

local function save(plr: Player)
	local s = sessions[plr]
	if not (s and s.dirty and store) then return end
	s.dirty = false
	s.lastSave = os.clock()
	local samples = s.samples
	pcall(function()
		store:SetAsync(s.key, {v = 1, place = game.PlaceId, version = game.PlaceVersion, samples = samples})
	end)
end

local NUM = {"seq", "t", "fps", "p50", "p99", "worst", "hb", "total", "tex", "texChar", "mesh", "gparts", "gui", "inst", "speed", "x", "z"}
remote.OnServerEvent:Connect(function(plr, sample)
	if not allowed(plr) or type(sample) ~= "table" then return end
	local clean = {}
	for _, k in NUM do
		local v = sample[k]
		clean[k] = if type(v) == "number" and v == v then v else -1
	end
	clean.phase = if type(sample.phase) == "string" then sample.phase:sub(1, 12) else "?"
	clean.vp = if type(sample.vp) == "string" then sample.vp:sub(1, 12) else "?"
	clean.touch = sample.touch == true
	clean.pbr = sample.pbr == true
	local s = sessions[plr]
	if not s then
		s = {key = ("%d_%d"):format(plr.UserId, os.time()), samples = {}, dirty = false, lastSave = 0}
		sessions[plr] = s
		if store then
			pcall(function()
				store:UpdateAsync(("%d_sessions"):format(plr.UserId), function(old)
					local list = type(old) == "table" and old or {}
					table.insert(list, s.key)
					while #list > 20 do table.remove(list, 1) end
					return list
				end)
			end)
		end
	end
	table.insert(s.samples, clean)
	while #s.samples > 720 do table.remove(s.samples, 1) end
	s.dirty = true
	print(("[PerfTelemetry] %s %s %.1ffps p99 %.1fms worst %.1fms mem %.0f tex %.0f gui %.0f spd %d @%d,%d vp %s touch %s pbr %s v%d")
		:format(s.key, clean.phase, clean.fps, clean.p99, clean.worst, clean.total, clean.tex, clean.gui, clean.speed,
			clean.x, clean.z, clean.vp, tostring(clean.touch), tostring(clean.pbr), game.PlaceVersion))
	if os.clock() - s.lastSave > 30 then
		task.spawn(save, plr)
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	save(plr)
	sessions[plr] = nil
end)
game:BindToClose(function()
	for plr in sessions do
		save(plr)
	end
end)
