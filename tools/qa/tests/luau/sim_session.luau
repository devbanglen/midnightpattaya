-- A simulated Roblox client-server session for the TestKit tests (tools/qa/tests/test_jobdrive.py), luau CLI only.
-- Loaded after prelude.luau (Vector3, CFrame). It provides:
--   * a sim clock (os.clock, workspace:GetServerTimeNow) and a thread scheduler: task.spawn / defer / delay / wait,
--     Signal:Wait and RemoteFunction:InvokeServer yield and the scheduler resumes them. A yield of that kind inside a
--     coroutine the scheduler does not own (TestKit's Heartbeat-resumed runners) is an error: in Roblox the runner's
--     own Heartbeat handler would resume it early;
--   * generic Instances (properties, children, attributes, IsA by class), RemoteEvent / RemoteFunction /
--     BindableEvent with the server side here and a replica per client (OnClientEvent, FireServer, InvokeServer);
--     remote traffic is queued per direction and delivered at the receiver's next frame (opts.latency);
--   * one server (60 Hz Heartbeat) and any number of clients, each with its own Player (attributes set by the server
--     replicate to it at its next frame), RunService (frames at its own rate, optional jitter), _G, workspace /
--     ReplicatedStorage views and a car (client-owned: the client moves it; the server sees the position and velocity
--     of the client's last frame, opts.latency later; the server kit's teleport anchors and moves it).
MAIN_ENV = getfenv(1) -- the main chunk's globals (the luau CLI keeps them apart from _G)
SIM = {t = 0, T0 = 1792540800.25, serverDt = 1 / 60, latency = 0, clients = {}, LIFO = true, errors = {}}
local realOs = os
os = {clock = function() return SIM.t end, time = realOs.time, date = realOs.date}

-- type tags ---------------------------------------------------------------------------------------------------------
local VEC_MT = getmetatable(Vector3.new(0, 0, 0))
local CF_MT = getmetatable(CFrame.lookAt(Vector3.new(0, 0, 0), Vector3.new(0, 0, -1)))
local IDENTITY = setmetatable({identity = true}, {__index = function() return nil end})
CF_MT.__mul = function(a, b)
	if b == IDENTITY or (type(b) == "table" and b.identity) then
		return a
	end
	if a == IDENTITY then
		return b
	end
	if type(b) == "table" and getmetatable(b) == CF_MT then
		return CFrame.lookAt(a.Position + b.Position, a.Position + b.Position + a.LookVector)
	end
	return a
end
CF_MT.__add = function(a, v)
	return CFrame.lookAt(a.Position + v, a.Position + v + a.LookVector)
end
function CF_MT.ToObjectSpace(_, _)
	return IDENTITY
end
function CF_MT.Lerp(a, b, t)
	return CFrame.lookAt(a.Position:Lerp(b.Position, t), a.Position:Lerp(b.Position, t) + a.LookVector)
end
CFrame.Angles = function() return IDENTITY end
CFrame.identity = IDENTITY
Vector2 = {new = function(x, y)
	return setmetatable({X = x or 0, Y = y or 0}, {__index = function(t, k)
		if k == "Magnitude" then return math.sqrt(t.X * t.X + t.Y * t.Y) end
		return nil
	end, __sub = function(a, b) return Vector2.new(a.X - b.X, a.Y - b.Y) end,
		__add = function(a, b) return Vector2.new(a.X + b.X, a.Y + b.Y) end})
end}
Color3 = {fromRGB = function(r, g, b) return {R = r, G = g, B = b} end, new = function(r, g, b) return {R = r, G = g, B = b} end}
UDim2 = {fromOffset = function(...) return {...} end, fromScale = function(...) return {...} end, new = function(...) return {...} end}
UDim = {new = function(...) return {...} end}
local enumMt = {}
enumMt.__index = function(t, k)
	local v = setmetatable({Name = k, path = (rawget(t, "path") or "Enum") .. "." .. k}, enumMt)
	rawset(t, k, v)
	return v
end
Enum = setmetatable({path = "Enum"}, enumMt)
RaycastParams = {new = function() return {} end}
OverlapParams = {new = function() return {} end}
PhysicalProperties = {new = function(...) return {...} end}

function SIM.typeof(x)
	local mt = getmetatable(x)
	if mt == VEC_MT then return "Vector3" end
	if mt == CF_MT then return "CFrame" end
	if type(x) == "table" and rawget(x, "_isInstance") then return "Instance" end
	if type(x) == "table" and rawget(x, "Connected") ~= nil then return "RBXScriptConnection" end
	return type(x)
end

-- scheduler ------------------------------------------------------------------------------------------------------
local owned = setmetatable({}, {__mode = "k"})
local waiting = {} -- {co, at?, sig?, box?}
local function report(co, err)
	local msg = debug.traceback(co, tostring(err))
	table.insert(SIM.errors, msg)
	print("SIM THREAD ERROR " .. msg)
end
local function resume(co, ...)
	local ok, req = coroutine.resume(co, ...)
	if not ok then
		report(co, req)
		return
	end
	if coroutine.status(co) == "suspended" then
		if type(req) ~= "table" then
			report(co, "a scheduler thread yielded without a wait request")
			return
		end
		req.co = co
		table.insert(waiting, req)
	end
end
SIM.resume = resume
local function mustYield(what: string)
	local co = coroutine.running()
	if not co or not owned[co] then
		local msg = ("%s outside a scheduler thread (a Heartbeat-resumed runner must never wait in the engine)"):format(what)
		table.insert(SIM.errors, debug.traceback(msg))
		error(msg, 3)
	end
end
local function spawnThread(f, ...)
	local co = if type(f) == "thread" then f else coroutine.create(f)
	owned[co] = true
	resume(co, ...)
	return co
end
task = {}
function task.spawn(f, ...)
	return spawnThread(f, ...)
end
function task.defer(f, ...)
	local co = coroutine.create(f)
	owned[co] = true
	table.insert(waiting, {co = co, at = SIM.t, args = table.pack(...)})
	return co
end
function task.delay(s, f, ...)
	local co = coroutine.create(f)
	owned[co] = true
	table.insert(waiting, {co = co, at = SIM.t + (s or 0), args = table.pack(...)})
	return co
end
function task.wait(s)
	mustYield("task.wait")
	local t0 = SIM.t
	coroutine.yield({at = SIM.t + (s or 0)})
	return SIM.t - t0
end
function task.cancel(co)
	for i = #waiting, 1, -1 do
		if waiting[i].co == co then table.remove(waiting, i) end
	end
end
-- resume every thread whose time has come
function SIM.wakeTimers()
	local due = {}
	for i = #waiting, 1, -1 do
		local w = waiting[i]
		if w.at and w.at <= SIM.t + 1e-9 then
			table.insert(due, 1, w)
			table.remove(waiting, i)
		end
	end
	for _, w in due do
		if w.args then
			resume(w.co, table.unpack(w.args, 1, w.args.n))
		else
			resume(w.co)
		end
	end
end

-- signals --------------------------------------------------------------------------------------------------------
function SIM.signal()
	local s = {list = {}}
	function s:Connect(f)
		local c = {Connected = true}
		function c:Disconnect() self.Connected = false end
		table.insert(self.list, {f = f, c = c})
		return c
	end
	function s:Once(f)
		local c
		c = self:Connect(function(...)
			c:Disconnect()
			f(...)
		end)
		return c
	end
	function s:Fire(...)
		local list = table.clone(self.list)
		local n = #list
		for k = 1, n do
			local i = if SIM.LIFO then n - k + 1 else k
			local e = list[i]
			if e.c.Connected then
				spawnThread(e.f, ...)
			end
		end
		for i = #self.list, 1, -1 do
			if not self.list[i].c.Connected then table.remove(self.list, i) end
		end
		-- threads waiting on this signal
		local due = {}
		for i = #waiting, 1, -1 do
			if waiting[i].sig == self then
				table.insert(due, 1, waiting[i])
				table.remove(waiting, i)
			end
		end
		local args = table.pack(...)
		for _, w in due do
			resume(w.co, table.unpack(args, 1, args.n))
		end
	end
	function s:Wait()
		mustYield("Signal:Wait")
		return coroutine.yield({sig = self})
	end
	return s
end

-- instances ------------------------------------------------------------------------------------------------------
local CLASS_IS = {Part = {"BasePart", "PVInstance"}, MeshPart = {"BasePart", "PVInstance"}, Model = {"PVInstance"},
	VehicleSeat = {"BasePart", "PVInstance"}, Seat = {"BasePart", "PVInstance"}}
local Inst = {}
local instMt = {}
instMt.__index = function(o, k)
	local ext = rawget(o, "_ext")[k] -- per-instance overrides (a car model's PivotTo / GetPivot)
	if ext ~= nil then return ext end
	local m = Inst[k]
	if m ~= nil then return m end
	local p = rawget(o, "_props")[k]
	if p ~= nil then return p end
	if k == "Parent" then return nil end
	local child = rawget(o, "_byName")[k]
	if child then return child end
	return nil
end
instMt.__newindex = function(o, k, v)
	if k == "Parent" then
		local old = rawget(o, "_props").Parent
		if old then old:_remove(o) end
		rawget(o, "_props").Parent = v
		if v then v:_add(o) end
		return
	end
	if k == "Name" then
		local par = rawget(o, "_props").Parent
		if par then par:_remove(o) end
		rawget(o, "_props").Name = v
		if par then par:_add(o) end
		return
	end
	if k == "CFrame" and v and getmetatable(v) == CF_MT then
		rawget(o, "_props").Position = v.Position
	elseif k == "Position" and v then
		local cf = rawget(o, "_props").CFrame
		rawget(o, "_props").CFrame = CFrame.lookAt(v, v + (if cf then cf.LookVector else Vector3.new(0, 0, -1)))
	end
	rawget(o, "_props")[k] = v
end
function SIM.instance(className: string, name: string?)
	local o = setmetatable({_isInstance = true, _props = {ClassName = className, Name = name or className},
		_children = {}, _byName = {}, _attr = {}, _sig = {}, _ext = {}}, instMt)
	if CLASS_IS[className] and table.find(CLASS_IS[className], "BasePart") then
		local p = rawget(o, "_props")
		p.CFrame, p.Position = CFrame.lookAt(Vector3.zero, Vector3.new(0, 0, -1)), Vector3.zero
		p.Size, p.Transparency, p.LocalTransparencyModifier = Vector3.new(4, 1, 2), 0, 0
		p.CanCollide, p.Anchored = true, false
		p.Touched = SIM.signal() -- never fires (nothing but the road exists)
	end
	if className == "RemoteEvent" then
		o._props.OnServerEvent = SIM.signal()
		o._props.replicas = {}
	elseif className == "RemoteFunction" then
		o._props.replicas = {}
	elseif className == "BindableEvent" then
		o._props.Event = SIM.signal()
	elseif className == "BindableFunction" then
		o._props.replicas = {}
	end
	return o
end
Instance = {new = function(className, parent)
	local o = SIM.instance(className)
	if parent then o.Parent = parent end
	return o
end}
function Inst:_add(c)
	table.insert(rawget(self, "_children"), c)
	rawget(self, "_byName")[c.Name] = rawget(self, "_byName")[c.Name] or c
end
function Inst:_remove(c)
	local ch = rawget(self, "_children")
	local i = table.find(ch, c)
	if i then table.remove(ch, i) end
	if rawget(self, "_byName")[c.Name] == c then
		rawget(self, "_byName")[c.Name] = nil
		for _, x in ch do
			if x.Name == c.Name then rawget(self, "_byName")[c.Name] = x break end
		end
	end
end
function Inst:FindFirstChild(name, recursive)
	local c = rawget(self, "_byName")[name]
	if c or not recursive then return c end
	for _, x in rawget(self, "_children") do
		local f = x:FindFirstChild(name, true)
		if f then return f end
	end
	return nil
end
function Inst:WaitForChild(name)
	return self:FindFirstChild(name)
end
function Inst:FindFirstChildOfClass(c)
	for _, x in rawget(self, "_children") do
		if x.ClassName == c then return x end
	end
	return nil
end
function Inst:GetChildren()
	return table.clone(rawget(self, "_children"))
end
function Inst:GetDescendants()
	local out = {}
	for _, x in rawget(self, "_children") do
		table.insert(out, x)
		for _, d in x:GetDescendants() do table.insert(out, d) end
	end
	return out
end
function Inst:IsA(c)
	if self.ClassName == c or c == "Instance" then return true end
	for _, x in CLASS_IS[self.ClassName] or {} do
		if x == c then return true end
	end
	return false
end
function Inst:IsDescendantOf(a)
	local p = self.Parent
	while p do
		if p == a then return true end
		p = p.Parent
	end
	return false
end
function Inst:FindFirstAncestorWhichIsA(c)
	local p = self.Parent
	while p do
		if p:IsA(c) then return p end
		p = p.Parent
	end
	return nil
end
function Inst:GetFullName()
	local parts = {}
	local o = self
	while o do
		table.insert(parts, 1, o.Name)
		o = o.Parent
	end
	return table.concat(parts, ".")
end
function Inst:Destroy()
	self.Parent = nil
end
function Inst:ClearAllChildren()
	for _, c in self:GetChildren() do c.Parent = nil end
end
function Inst:GetAttribute(k) return rawget(self, "_attr")[k] end
function Inst:GetAttributes() return table.clone(rawget(self, "_attr")) end
function Inst:SetAttribute(k, v)
	local a = rawget(self, "_attr")
	local old = a[k]
	a[k] = v
	if old ~= v then
		local s = rawget(self, "_sig")[k]
		if s then s:Fire() end
		local any = rawget(self, "_sig")["*"]
		if any then any:Fire(k) end
		local hook = rawget(self, "_props").onAttr
		if hook then hook(k, v) end
	end
end
function Inst:GetAttributeChangedSignal(k)
	local sig = rawget(self, "_sig")
	sig[k] = sig[k] or SIM.signal()
	return sig[k]
end
function Inst:GetPropertyChangedSignal() return SIM.signal() end
function Inst:GetPivot() return self.CFrame end
function Inst:PivotTo(cf) self.CFrame = cf end
-- remotes, server side
function Inst:FireClient(plrS, ...)
	local c = SIM.clientOf[plrS]
	if not c or not plrS.Parent then return end
	local rep = c.replica(self)
	local args = table.pack(...)
	if SIM.onFireClient then SIM.onFireClient(self, plrS, args) end -- the tests' record of what the server sent
	SIM.toClient(c, function() rep.OnClientEvent:Fire(table.unpack(args, 1, args.n)) end)
end
function Inst:FireAllClients(...)
	for _, c in SIM.clients do
		self:FireClient(c.playerS, ...)
	end
end
function Inst:Fire(...)
	self.Event:Fire(...)
end
function Inst:Invoke(...)
	return self.OnInvoke(...)
end

-- server and clients ------------------------------------------------------------------------------------------------
SIM.clientOf = {}
local toServer = {} -- {at, f}
function SIM.toServer(f)
	table.insert(toServer, {at = SIM.t + SIM.latency, f = f})
end
function SIM.toClient(c, f)
	table.insert(c.inbox, {at = SIM.t + SIM.latency, f = f})
end

SIM.workspace = SIM.instance("Workspace", "Workspace")
SIM.workspace.GetServerTimeNow = function() return SIM.T0 + SIM.t end
-- a flat road everywhere at SIM.roadY (a part named "Road"); nothing else is solid
SIM.roadY = 1
SIM.road = SIM.instance("Part", "Road")
SIM.workspace.Raycast = function(_, origin, dir)
	if dir.Y < 0 and origin.Y >= SIM.roadY and origin.Y + dir.Y <= SIM.roadY then
		return {Instance = SIM.road, Position = Vector3.new(origin.X, SIM.roadY, origin.Z), Normal = Vector3.new(0, 1, 0),
			Material = Enum.Material.Asphalt, Distance = origin.Y - SIM.roadY}
	end
	return nil
end
SIM.workspace.GetPartsInPart = function() return {} end
SIM.workspace.GetPartBoundsInBox = function() return {} end
SIM.workspace.BulkMoveTo = function(_, parts, cframes)
	for i, p in parts do
		p.CFrame = cframes[i]
	end
end
SIM.workspace.Gravity = 196.2
SIM.RS = SIM.instance("ReplicatedStorage", "ReplicatedStorage")
SIM.SS = SIM.instance("ServerStorage", "ServerStorage")
SIM.Lighting = SIM.instance("Lighting", "Lighting")
SIM.serverRun = {IsStudio = function() return true end, IsServer = function() return true end,
	IsClient = function() return false end, Heartbeat = SIM.signal(), Stepped = SIM.signal(),
	PreSimulation = SIM.signal(), PostSimulation = SIM.signal()}
SIM.PlayersS = SIM.instance("Players", "Players")
SIM.PlayersS.PlayerAdded = SIM.signal()
SIM.PlayersS.PlayerRemoving = SIM.signal()
SIM.PlayersS.GetPlayers = function()
	local out = {}
	for _, c in SIM.clients do
		if c.playerS.Parent then table.insert(out, c.playerS) end
	end
	return out
end
SIM.serverG = {}
local serverServices = {Players = SIM.PlayersS, RunService = SIM.serverRun, ReplicatedStorage = SIM.RS,
	ServerStorage = SIM.SS, Lighting = SIM.Lighting, Workspace = SIM.workspace,
	HttpService = {GenerateGUID = function() return "guid" end}}
SIM.serverGame = {GetService = function(_, n) return serverServices[n] or SIM.instance(n, n) end,
	CreatorId = 0, CreatorType = Enum.CreatorType.User, JobId = "", PlaceId = 0}

-- require: a ModuleScript instance carries its value (or a loader) in _props.value / _props.load
function SIM.require(m)
	if type(m) == "table" and rawget(m, "_isInstance") then
		local p = rawget(m, "_props")
		if p.value == nil and p.load then
			p.value = p.load()
		end
		return p.value
	end
	error("require of a non-module: " .. tostring(m))
end
function SIM.module(parent, name: string, value, load)
	local m = SIM.instance("ModuleScript", name)
	rawget(m, "_props").value = value
	rawget(m, "_props").load = load
	m.Parent = parent
	return m
end
-- a ModuleScript each client loads for itself (in Roblox every client runs its own copy): loader(c) -> value
function SIM.clientModule(parent, name: string, loader)
	local m = SIM.instance("ModuleScript", name)
	rawget(m, "_props").perClient = loader
	m.Parent = parent
	return m
end

-- a car: the client moves it (TestKit / CarController stand-in set CFrame and velocity); the server sees the state of
-- the client's last frame (SIM.latency later); anchoring / PivotTo from the server move it at once
local function newCar(c, at: Vector3, look: Vector3)
	local car = {cf = CFrame.lookAt(at, at + look), v = Vector3.zero, av = Vector3.zero, anchored = false,
		snaps = {{at = -math.huge, cf = CFrame.lookAt(at, at + look), v = Vector3.zero}}}
	c.car = car
	local function view(side: string)
		local model = SIM.instance("Model", "Car_" .. c.name)
		model:SetAttribute("RaceCar", true)
		local chassis = setmetatable({_isInstance = true, _side = side}, {
			__index = function(_, k)
				if side == "client" or car.anchored then
					if k == "CFrame" then return car.cf
					elseif k == "Position" then return car.cf.Position
					elseif k == "AssemblyLinearVelocity" then return car.v
					end
				else
					local s = car.snaps[1]
					for i = #car.snaps, 1, -1 do
						if car.snaps[i].at <= SIM.t + 1e-9 then s = car.snaps[i] break end
					end
					if k == "CFrame" then return s.cf
					elseif k == "Position" then return s.cf.Position
					elseif k == "AssemblyLinearVelocity" then return s.v
					end
				end
				if k == "AssemblyAngularVelocity" then return car.av
				elseif k == "Anchored" then return car.anchored
				elseif k == "Parent" then return model
				elseif k == "Name" then return "Chassis"
				elseif k == "ClassName" then return "Part"
				elseif k == "Size" then return Vector3.new(7, 1.6, 15)
				elseif k == "CanCollide" then return car.canCollide ~= false
				elseif k == "Material" then return Enum.Material.SmoothPlastic
				elseif k == "GetChildren" or k == "GetDescendants" then return function() return {} end
				elseif k == "GetAttribute" then return function() return nil end
				elseif k == "FindFirstAncestorWhichIsA" then
					return function(_, cl) return if cl == "Model" or cl == "PVInstance" then model else nil end
				elseif k == "AssemblyMass" then return 120
				elseif k == "Touched" then return SIM.signal()
				elseif k == "IsA" then return function(_, cl) return cl == "BasePart" or cl == "Part" end
				elseif k == "FindFirstChild" then return function(_, n) return car.children and car.children[n] end
				elseif k == "GetFullName" then return function() return "Workspace.Car_" .. c.name .. ".Chassis" end
				elseif k == "SetNetworkOwner" or k == "SetNetworkOwnershipAuto" then return function() end
				elseif k == "GetNetworkOwner" then return function() return c.playerS end
				elseif k == "ApplyImpulse" or k == "ApplyImpulseAtPosition" then return function() end
				elseif k == "IsDescendantOf" then return function(_, a) return a == model end
				end
				return nil
			end,
			__newindex = function(_, k, v)
				if k == "CFrame" then
					car.cf = v
					if side == "server" then
						table.insert(car.snaps, {at = SIM.t, cf = v, v = car.v})
					end
				elseif k == "AssemblyLinearVelocity" then
					car.v = v
				elseif k == "AssemblyAngularVelocity" then
					car.av = v
				elseif k == "Anchored" then
					car.anchored = v
				elseif k == "CanCollide" then
					car.canCollide = v
				end
			end})
		rawget(model, "_props").PrimaryPart = chassis
		table.insert(rawget(model, "_children"), chassis)
		rawget(model, "_byName").Chassis = chassis
		local ext = rawget(model, "_ext")
		ext.GetPivot = function() return car.cf end
		ext.PivotTo = function(_, cf)
			car.cf = cf
			table.insert(car.snaps, {at = SIM.t, cf = cf, v = car.v})
		end
		local seat = SIM.instance("VehicleSeat", "DriveSeat")
		seat.Parent = model
		local hum = SIM.instance("Humanoid", "Humanoid")
		rawget(hum, "_props").SeatPart = seat
		rawget(seat, "_props").Occupant = hum
		local char = SIM.instance("Model", c.name)
		hum.Parent = char
		rawget(char, "_props").GetDescendants = function() return {} end
		return model, chassis, char
	end
	c.modelS, c.chassisS, c.charS = view("server")
	c.modelC, c.chassisC, c.charC = view("client")
	c.playerS.Character = c.charS
	c.playerC.Character = c.charC
	c.workspaceC = c.workspaceC -- (set below)
end

-- the per-client replica of a server instance: modules shared, folders mapped, remotes per client
local function makeReplica(c, inst)
	if inst == nil then return nil end
	local cls = inst.ClassName
	if cls == "ModuleScript" then
		local per = rawget(inst, "_props").perClient
		if not per then
			return inst
		end
		if not c.modules[inst] then
			local mc = SIM.instance("ModuleScript", inst.Name)
			rawget(mc, "_props").load = function() return per(c) end
			c.modules[inst] = mc
		end
		return c.modules[inst]
	end
	if cls == "RemoteEvent" then
		local reps = inst.replicas
		if not reps[c] then
			reps[c] = setmetatable({_isInstance = true, Name = inst.Name, ClassName = "RemoteEvent",
				OnClientEvent = SIM.signal(),
				FireServer = function(_, ...)
					local args = table.pack(...)
					SIM.toServer(function() inst.OnServerEvent:Fire(c.playerS, table.unpack(args, 1, args.n)) end)
				end,
				IsA = function(_, x) return x == "RemoteEvent" or x == "Instance" end}, {})
		end
		return reps[c]
	end
	if cls == "RemoteFunction" then
		local reps = inst.replicas
		if not reps[c] then
			reps[c] = setmetatable({_isInstance = true, Name = inst.Name, ClassName = "RemoteFunction",
				InvokeServer = function(_, ...)
					mustYield("RemoteFunction:InvokeServer")
					local args = table.pack(...)
					local box = {}
					local caller = coroutine.running()
					SIM.toServer(function()
						spawnThread(function()
							local handler = inst.OnServerInvoke
							local res = if handler then table.pack(pcall(handler, c.playerS, table.unpack(args, 1, args.n)))
								else table.pack(false, "no OnServerInvoke")
							SIM.toClient(c, function()
								box.res = res
								for i = #waiting, 1, -1 do
									if waiting[i].box == box then table.remove(waiting, i) end
								end
								resume(caller)
							end)
						end)
					end)
					coroutine.yield({box = box})
					local res = box.res
					if not res[1] then error(res[2], 0) end
					return table.unpack(res, 2, res.n)
				end,
				IsA = function(_, x) return x == "RemoteFunction" or x == "Instance" end}, {})
		end
		return reps[c]
	end
	if cls == "Folder" or cls == "ReplicatedStorage" then
		c.folders[inst] = c.folders[inst] or setmetatable({_isInstance = true, Name = inst.Name, ClassName = cls,
			FindFirstChild = function(_, n) return makeReplica(c, inst:FindFirstChild(n)) end,
			WaitForChild = function(_, n) return makeReplica(c, inst:FindFirstChild(n)) end,
			GetChildren = function()
				local out = {}
				for _, x in inst:GetChildren() do table.insert(out, makeReplica(c, x)) end
				return out
			end,
			IsA = function(_, x) return x == cls or x == "Instance" end,
			ChildAdded = SIM.signal()}, {})
		return c.folders[inst]
	end
	return inst
end

-- the client's workspace: its own PattayaTraffic folder over the shared workspace
local function clientWorkspace(c)
	local ws = SIM.workspace
	local own = {}
	c.own = own
	local proxy = setmetatable({}, {__index = function(_, k)
		if k == "FindFirstChild" then
			return function(_, n, rec)
				if own[n] then return own[n] end
				return ws:FindFirstChild(n, rec)
			end
		elseif k == "WaitForChild" then
			return function(_, n)
				if own[n] then return own[n] end
				return ws:FindFirstChild(n)
			end
		elseif k == "CurrentCamera" then
			return nil
		elseif k == "_add" then
			-- an instance this client parents to workspace stays on this client (PattayaTraffic's folder)
			return function(_, ch) own[ch.Name] = ch end
		elseif k == "_remove" then
			return function(_, ch)
				if own[ch.Name] == ch then own[ch.Name] = nil end
			end
		end
		local v = ws[k]
		if type(v) == "function" then
			return function(_, ...) return v(ws, ...) end
		end
		return v
	end})
	return proxy
end

function SIM.addClient(name: string, opts)
	opts = opts or {}
	local c = {name = name, dt = opts.dt or 1 / 60, jitter = opts.jitter or 0, inbox = {}, folders = {}, G = {},
		modules = {}, nextFrame = SIM.t, frames = 0}
	c.baseDt = c.dt
	c.playerS = SIM.instance("Player", name)
	rawget(c.playerS, "_props").UserId = #SIM.clients + 1001
	c.playerC = SIM.instance("Player", name)
	rawget(c.playerC, "_props").UserId = c.playerS.UserId
	local ps = SIM.instance("Folder", "PlayerScripts")
	ps.Parent = c.playerC
	-- attributes the server sets replicate to the client's Player at its next frame
	rawget(c.playerS, "_props").onAttr = function(k, v)
		SIM.toClient(c, function() c.playerC:SetAttribute(k, v) end)
	end
	local ls = SIM.instance("Folder", "leaderstats")
	for _, k in {"Money", "EXP", "Level"} do
		local iv = SIM.instance("IntValue", k)
		rawget(iv, "_props").Value = if k == "Level" then 3 else 500
		iv.Parent = ls
	end
	local title = SIM.instance("StringValue", "Title")
	rawget(title, "_props").Value = ""
	title.Parent = ls
	ls.Parent = c.playerS
	rawget(c.playerC, "_byName").leaderstats = ls -- the same values on both sides
	c.playerS.Parent = SIM.PlayersS
	SIM.clientOf[c.playerS] = c
	c.run = {IsStudio = function() return true end, IsServer = function() return false end,
		IsClient = function() return true end, Heartbeat = SIM.signal(), RenderStepped = SIM.signal(),
		PreSimulation = SIM.signal(), Stepped = SIM.signal(), PostSimulation = SIM.signal()}
	c.Players = {LocalPlayer = c.playerC, GetPlayers = function() return {c.playerC} end}
	c.replica = function(inst) return makeReplica(c, inst) end
	c.RS = makeReplica(c, SIM.RS)
	c.workspace = clientWorkspace(c)
	local services = {Players = c.Players, RunService = c.run, ReplicatedStorage = c.RS, Workspace = c.workspace,
		ContextActionService = {BindAction = function() end, UnbindAction = function() end}}
	c.game = {GetService = function(_, n) return services[n] or {} end}
	newCar(c, opts.at or Vector3.new(20000, 3.8, 0), opts.look or Vector3.new(1, 0, 0))
	table.insert(SIM.clients, c)
	return c
end

-- one client frame: inbound remote events and attributes, RenderStepped, PreSimulation (TestKit places the car),
-- physics (the car coasts on its velocity), Heartbeat (traffic, CarController, TestKit runners), the replication
-- snapshot the server will see
function SIM.clientFrame(c)
	c.frames += 1
	local box = c.inbox
	c.inbox = {}
	local later = {}
	for _, m in box do
		if m.at <= SIM.t + 1e-9 then m.f() else table.insert(later, m) end
	end
	for _, m in later do table.insert(c.inbox, m) end
	local dt = c.lastDt or c.dt
	c.run.RenderStepped:Fire(dt)
	c.run.PreSimulation:Fire(dt)
	c.run.Stepped:Fire(SIM.t, dt)
	local car = c.car
	if not car.anchored then
		if c.physics then
			c.physics(dt)
		else
			local p = car.cf.Position + Vector3.new(car.v.X * dt, 0, car.v.Z * dt)
			car.cf = CFrame.lookAt(p, p + car.cf.LookVector)
		end
	end
	c.run.Heartbeat:Fire(dt)
	table.insert(car.snaps, {at = SIM.t + SIM.latency, cf = car.cf, v = car.v})
	if #car.snaps > 64 then table.remove(car.snaps, 1) end
end

function SIM.serverFrame()
	local box = toServer
	toServer = {}
	for _, m in box do
		if m.at <= SIM.t + 1e-9 then m.f() else table.insert(toServer, m) end
	end
	SIM.serverRun.Heartbeat:Fire(SIM.serverDt)
end

-- advance to the next client or server frame (whichever is first) and run it; timers in between
local nextServer = 0
function SIM.step()
	local tNext = nextServer
	for _, c in SIM.clients do
		tNext = math.min(tNext, c.nextFrame)
	end
	for _, w in waiting do
		if w.at and w.at < tNext then tNext = w.at end
	end
	SIM.t = math.max(SIM.t, tNext)
	SIM.wakeTimers()
	for _, c in SIM.clients do
		if c.nextFrame <= SIM.t + 1e-9 then
			local j = if c.jitter > 0 then (math.random() * 2 - 1) * c.jitter else 0
			c.lastDt = c.dt * (1 + j)
			c.nextFrame = SIM.t + c.lastDt
			SIM.clientFrame(c)
		end
	end
	if nextServer <= SIM.t + 1e-9 then
		nextServer = SIM.t + SIM.serverDt
		SIM.serverFrame()
	end
end
function SIM.run(seconds: number, untilF)
	local stop = SIM.t + seconds
	while SIM.t < stop do
		SIM.step()
		if untilF and untilF() then return true end
	end
	return false
end

-- load a script / module source with a side's globals as locals (game, workspace, require, task, _G, typeof, ...)
function SIM.load(source: string, env, chunkName: string)
	local f, err = loadstring(source, chunkName)
	if not f then error(err) end
	local G = setmetatable({}, {__index = function(_, k)
		local v = env[k]
		if v ~= nil then return v end
		return MAIN_ENV[k]
	end})
	setfenv(f, G)
	return f
end
function SIM.serverEnv(extra)
	local env = {game = SIM.serverGame, workspace = SIM.workspace, require = SIM.require, task = task, _G = SIM.serverG,
		typeof = SIM.typeof, os = os, Instance = Instance, script = SIM.instance("Script", "Script")}
	for k, v in extra or {} do env[k] = v end
	return env
end
function SIM.clientEnv(c, extra)
	local env = {game = c.game, workspace = c.workspace, require = SIM.require, task = task, _G = c.G, typeof = SIM.typeof,
		os = os, Instance = Instance, script = SIM.instance("LocalScript", "LocalScript"),
		print = function(...) SIM.print("[" .. c.name .. "]", ...) end}
	for k, v in extra or {} do env[k] = v end
	return env
end
SIM.print = print
-- run a server script in a scheduler thread (it may wait)
function SIM.runServerScript(source: string, name: string, extra)
	local f = SIM.load(source, SIM.serverEnv(extra), name)
	spawnThread(f)
end
-- run a LocalScript on client c in a scheduler thread
function SIM.runClientScript(c, source: string, name: string, extra)
	local f = SIM.load(source, SIM.clientEnv(c, extra), name)
	spawnThread(f)
end
