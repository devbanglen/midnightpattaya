-- Offline stand-ins for the few Roblox types the circuit modules use (tools/qa/tests, luau CLI only).
-- Vector3 and CFrame follow the Roblox conventions: Vector3.new(nil...) = 0 (the arguments are optional),
-- CFrame.lookAt(at, target): -Z = look direction, +X = right = look:Cross(yAxis), PointToObjectSpace = (right, up, -look).
local V = {}
local function vec(x, y, z)
	return setmetatable({X = x or 0, Y = y or 0, Z = z or 0}, V)
end
V.__index = function(t, k)
	if k == "Magnitude" then
		return math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z)
	elseif k == "Unit" then
		local m = math.sqrt(t.X * t.X + t.Y * t.Y + t.Z * t.Z)
		if m == 0 then
			return vec(0 / 0, 0 / 0, 0 / 0)
		end
		return vec(t.X / m, t.Y / m, t.Z / m)
	end
	return V[k]
end
V.__add = function(a, b) return vec(a.X + b.X, a.Y + b.Y, a.Z + b.Z) end
V.__sub = function(a, b) return vec(a.X - b.X, a.Y - b.Y, a.Z - b.Z) end
V.__unm = function(a) return vec(-a.X, -a.Y, -a.Z) end
V.__mul = function(a, b)
	if type(a) == "number" then
		return vec(a * b.X, a * b.Y, a * b.Z)
	elseif type(b) == "number" then
		return vec(a.X * b, a.Y * b, a.Z * b)
	end
	return vec(a.X * b.X, a.Y * b.Y, a.Z * b.Z)
end
V.__div = function(a, b) return vec(a.X / b, a.Y / b, a.Z / b) end
V.__eq = function(a, b) return a.X == b.X and a.Y == b.Y and a.Z == b.Z end
V.__tostring = function(a) return string.format("%.2f, %.2f, %.2f", a.X, a.Y, a.Z) end
function V.Dot(a, b) return a.X * b.X + a.Y * b.Y + a.Z * b.Z end
function V.Cross(a, b)
	return vec(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X)
end
function V.Lerp(a, b, t) return vec(a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t, a.Z + (b.Z - a.Z) * t) end
Vector3 = {new = vec, zero = vec(0, 0, 0), one = vec(1, 1, 1), xAxis = vec(1, 0, 0), yAxis = vec(0, 1, 0),
	zAxis = vec(0, 0, 1)}

local CF = {}
CF.__index = CF
local function cframe(pos, look)
	local L = look
	local R = L:Cross(Vector3.yAxis)
	if R.Magnitude < 1e-9 then
		R = vec(1, 0, 0)
	end
	R = R.Unit
	local U = R:Cross(L).Unit
	return setmetatable({Position = pos, LookVector = L, RightVector = R, UpVector = U}, CF)
end
function CF:PointToObjectSpace(p)
	local rel = p - self.Position
	return vec(rel:Dot(self.RightVector), rel:Dot(self.UpVector), -rel:Dot(self.LookVector))
end
CFrame = {
	lookAt = function(at, target)
		local d = target - at
		return cframe(at, if d.Magnitude > 1e-9 then d.Unit else vec(0, 0, -1))
	end,
	new = function(x, y, z)
		return cframe(if type(x) == "table" then x else vec(x, y, z), vec(0, 0, -1))
	end,
}

WARNINGS = {}
function warn(...)
	local t = {}
	for i = 1, select("#", ...) do
		t[i] = tostring((select(i, ...)))
	end
	table.insert(WARNINGS, table.concat(t, " "))
end

-- game:GetService("ServerStorage"):WaitForChild(name) returns the name; the harness's `require` maps it to a module
local service = {WaitForChild = function(_, name) return name end, FindFirstChild = function(_, name) return name end}
game = {GetService = function() return service end}
