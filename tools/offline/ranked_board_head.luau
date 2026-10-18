task = {spawn = function(f, ...) f(...) end}
local mode = "fail"
local data = {}
local function sorted(desc)
	local t = {}
	for k, v in data do table.insert(t, {key = k, value = v}) end
	table.sort(t, function(a, b) if desc then return a.value > b.value end return a.value < b.value end)
	return {GetCurrentPage = function() return t end}
end
local DS = {GetOrderedDataStore = function(_, name)
	if mode == "fail" then error("StudioAccessToApisNotAllowed") end
	return {
		SetAsync = function(_, k, v) data[k] = v end,
		GetSortedAsync = function(_, asc, n) return sorted(not asc) end,
		UpdateAsync = function() end,
	}
end}
local players = {}
local Players = {
	PlayerRemoving = {Connect = function() end},
	GetPlayerByUserId = function(_, id) return players[id] end,
	GetNameFromUserIdAsync = function(_, id) return "user" .. id end,
}
game = {GetService = function(_, n) if n == "Players" then return Players end return DS end}
local warned = 0
warn = function() warned += 1 end
local function load()
