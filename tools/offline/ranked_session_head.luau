-- offline mock harness for RaceSessionService.Ranked (scratch, not in the repo)
local RealRating = require("./RankedRating")
local clock = 1000
local heartbeat = nil
local sent = {}

-- math types ---------------------------------------------------------------------------------------------------
local V = {}
V.__index = V
local function vec(x, y, z) return setmetatable({X = x or 0, Y = y or 0, Z = z or 0}, V) end
V.__add = function(a, b) return vec(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
V.__sub = function(a, b) return vec(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
V.__index = function(t, k)
	if k == "Magnitude" then return math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z) end
	if k == "Unit" then local m = math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z); return vec(t.X / m, t.Y / m, t.Z / m) end
	return V[k]
end
Vector3 = {new = vec, zero = vec(0, 0, 0)}
local CF = {}
local function cf(p) return setmetatable({Position = p or vec()}, CF) end
CF.__index = CF
CF.__add = function(a, v) return cf(a.Position + v) end
CF.__mul = function(a, b) return a end
function CF:ToObjectSpace(o) return cf(vec()) end
CFrame = {new = function(x, y, z) return cf(if type(x) == "table" then x else vec(x, y, z)) end,
	lookAt = function(p) return cf(p) end}

-- engine ------------------------------------------------------------------------------------------------------
task = {spawn = function(f, ...) f(...) end, delay = function(_, f, ...) f(...) end, wait = function() return 0 end}
local function signal() return {Connect = function(_, f) return f end} end
workspace = {GetServerTimeNow = function() return clock end}

local players = {}
local function attrObj(o)
	o._attrs = {}
	o.SetAttribute = function(self, k, v) self._attrs[k] = v end
	o.GetAttribute = function(self, k) return self._attrs[k] end
	return o
end
local PlayersSvc = {
	PlayerRemoving = signal(),
	GetPlayerByUserId = function(_, id) for _, p in players do if p.UserId == id and p.Parent then return p end end return nil end,
	GetPlayers = function() local t = {} for _, p in players do if p.Parent then table.insert(t, p) end end return t end,
}
local ServerStorageSvc = attrObj({})
local mods = {}
ServerStorageSvc.WaitForChild = function(_, name) return mods[name] end
local services = {
	Players = PlayersSvc,
	RunService = {Heartbeat = {Connect = function(_, f) heartbeat = f end}},
	PhysicsService = {RegisterCollisionGroup = function() end, CollisionGroupSetCollidable = function() end},
	ServerStorage = ServerStorageSvc,
}
game = {GetService = function(_, n) return services[n] end}

-- mocked modules ----------------------------------------------------------------------------------------------
local store = {} -- [plr] = extra table
local submitted = {}
mods.RankedRating = RealRating
mods.PattayaProgress = {
	GetData = function(plr, k) return store[plr] and store[plr][k] end,
	SetData = function(plr, k, v) store[plr] = store[plr] or {}; store[plr][k] = v end,
	Award = function() return 0 end,
}
mods.LeaderboardService = {
	init = function() end, getPB = function() return nil end, top = function() return {} end,
	overallLap = function() return nil end, overallSectors = function() return {} end,
	submit = function() return {pb = false, record = false} end,
	submitRating = function(plr, bucket, season, rating, prov) table.insert(submitted, {plr.Name, bucket, season, rating, prov}) end,
	rankedTop = function() return {} end,
}
mods.PattayaRoute = {carOf = function(plr) return plr._seat end, busy = function() return false end}
local grid = {}
for i = 1, 12 do grid[i] = CFrame.new(i * 10, 0, 0) end
local circuit = {id = "test_oval", name = "Test Oval", lengthStuds = 1565.6, len = 1565.6, grid = grid, def = {},
	entrance = CFrame.new(0, 0, 0), gates = {{}, {}}}
mods.CircuitRegistry = {
	at = function() return circuit end, get = function() return circuit end, all = function() return {circuit} end,
	nearest = function() return {s = circuit.len - 100} end,
}
mods.CheckpointValidator = {new = function()
	return {s = 0, lastGate = 1, pit = false, moved = function() end, sample = function() return {} end,
		armAt = function() end, resetFrame = function() return CFrame.new(0, 0, 0) end}
end}
mods.LapTimingService = {new = function()
	return {lap = 0, completed = 0, onGate = function() return {} end, invalidate = function() return true end}
end}

local function newPlayer(name, id, class)
	local car = attrObj({})
	car._attrs.Class = class
	car.PivotTo = function() end
	car.GetPivot = function() return CFrame.new(0, 0, 0) end
	car.GetDescendants = function() return {} end
	local chassis = {Parent = car, Position = vec(0, 0, 0), CFrame = CFrame.new(0, 0, 0), Anchored = false,
		AssemblyLinearVelocity = vec(), AssemblyAngularVelocity = vec(), SetNetworkOwner = function() end}
	local plr = attrObj({Name = name, DisplayName = name, UserId = id, Parent = PlayersSvc, Character = nil})
	plr._seat = chassis
	plr._attrs.ProgressLoaded = true
	table.insert(players, plr)
	return plr
end

local function step(dt)
	clock += dt
	heartbeat()
end

local function loadRSS()
	local require = function(x) return x end
