-- Offline stand-ins for PattayaRoute (tools/qa/routing_harness, luau CLI only), loaded after tools/qa/tests/luau/prelude.luau
-- (Vector3 / CFrame / warn): Vector2, Random, a fake ServerStorage tree with ModuleScript loaders and a require that
-- resolves them (cached like Roblox: every module is loaded once and shared).
local V2 = {}
local function v2(x, y)
	return setmetatable({X = x or 0, Y = y or 0}, V2)
end
V2.__index = function(t, k)
	if k == "Magnitude" then
		return math.sqrt(t.X * t.X + t.Y * t.Y)
	elseif k == "Unit" then
		local m = math.sqrt(t.X * t.X + t.Y * t.Y)
		if m == 0 then
			return v2(0 / 0, 0 / 0)
		end
		return v2(t.X / m, t.Y / m)
	end
	return V2[k]
end
V2.__add = function(a, b) return v2(a.X + b.X, a.Y + b.Y) end
V2.__sub = function(a, b) return v2(a.X - b.X, a.Y - b.Y) end
V2.__unm = function(a) return v2(-a.X, -a.Y) end
V2.__mul = function(a, b)
	if type(a) == "number" then
		return v2(a * b.X, a * b.Y)
	elseif type(b) == "number" then
		return v2(a.X * b, a.Y * b)
	end
	return v2(a.X * b.X, a.Y * b.Y)
end
V2.__div = function(a, b) return v2(a.X / b, a.Y / b) end
V2.__eq = function(a, b) return a.X == b.X and a.Y == b.Y end
V2.__tostring = function(a) return string.format("%.2f, %.2f", a.X, a.Y) end
function V2.Dot(a, b) return a.X * b.X + a.Y * b.Y end
function V2.Lerp(a, b, t) return v2(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t) end
Vector2 = {new = v2, zero = v2(0, 0)}

-- Random.new(seed):NextInteger(a, b): repeatable (not Roblox's sequence; the harness only needs old == new)
local R = {}
R.__index = R
function R:NextInteger(a, b)
	self.s = (self.s * 1103515245 + 12345) % 2147483648
	return a + self.s % (b - a + 1)
end
Random = {new = function(seed) return setmetatable({s = (seed or 1) % 2147483648}, R) end}

-- fake instances ----------------------------------------------------------------------------------------------------
local Inst = {}
Inst.__index = Inst
function Inst:FindFirstChild(name)
	return self._children[name]
end
function Inst:WaitForChild(name)
	local c = self._children[name]
	if not c then
		error("WaitForChild: " .. self.Name .. " has no " .. tostring(name))
	end
	return c
end
function Inst:IsA(class)
	return self.ClassName == class
end
function Inst:add(child)
	child.Parent = self
	self._children[child.Name] = child
	return child
end
function NewInst(name, class, loader)
	return setmetatable({Name = name, ClassName = class, _children = {}, _loader = loader}, Inst)
end

local moduleCache = {}
REQUIRE_COUNT = {} -- [module name] = times its loader ran (chunk data loads, for the tests)
function REQ(m)
	if type(m) ~= "table" or m.ClassName ~= "ModuleScript" then
		error("require: not a ModuleScript: " .. tostring(m))
	end
	local v = moduleCache[m]
	if v == nil then
		REQUIRE_COUNT[m.Name] = (REQUIRE_COUNT[m.Name] or 0) + 1
		v = m._loader(m)
		moduleCache[m] = v
	end
	return v
end

SERVER_STORAGE = NewInst("ServerStorage", "Folder")
GAME = {GetService = function(_, name)
	assert(name == "ServerStorage", "harness: only ServerStorage")
	return SERVER_STORAGE
end}
