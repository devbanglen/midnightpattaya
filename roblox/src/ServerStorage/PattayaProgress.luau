--!strict
-- Player money / EXP / level (RayCity-style: races and missions pay money and EXP; levels gate content later).
-- Shown as leaderstats; saved with DataStoreService when the place allows it (Studio needs "Enable Studio Access to
-- API Services"; without it the values simply live for the session).
local Players = game:GetService("Players")
local DataStoreService = game:GetService("DataStoreService")

local Progress = {}

local STORE_NAME = "PattayaProgress_v1"
local okStore, store = pcall(function()
	return DataStoreService:GetDataStore(STORE_NAME)
end)
if not okStore then
	store = nil
end

local function expToNext(level: number): number
	return 100 + (level - 1) * 60
end
Progress.expToNext = expToNext

local function stats(plr: Player)
	return plr:FindFirstChild("leaderstats")
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
	local title = Instance.new("StringValue") -- Road Fight title ("Road Fighter", "Road King")
	title.Name = "Title"
	title.Parent = ls
	plr:SetAttribute("RoadFight", 0) -- bit k-1 set = Road Fight boss of order k beaten
	ls.Parent = plr
	if store then
		local ok, data = pcall(function()
			return (store :: any):GetAsync("p" .. plr.UserId)
		end)
		if ok and type(data) == "table" then
			level.Value = data.level or 1
			money.Value = data.money or 0
			exp.Value = data.exp or 0
			title.Value = data.title or ""
			plr:SetAttribute("RoadFight", data.roadFight or 0)
		end
	end
end

local function save(plr: Player)
	local ls = stats(plr)
	if not (store and ls) then
		return
	end
	local data = {level = ls.Level.Value, money = ls.Money.Value, exp = ls.EXP.Value, title = ls.Title.Value,
		roadFight = plr:GetAttribute("RoadFight") or 0}
	pcall(function()
		(store :: any):SetAsync("p" .. plr.UserId, data)
	end)
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

function Progress.SetTitle(plr: Player, title: string)
	local ls = stats(plr)
	if ls then
		ls.Title.Value = title
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
	Players.PlayerRemoving:Connect(save)
	game:BindToClose(function()
		for _, p in Players:GetPlayers() do
			save(p)
		end
	end)
end

return Progress
