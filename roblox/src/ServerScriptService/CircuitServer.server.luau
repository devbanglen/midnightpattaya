-- Circuit racing (MIDNIGHT PATTAYA): wires the data-driven circuit system together. Does nothing unless
-- ServerStorage.PattayaData.circuits exists (one ModuleScript per circuit, see docs/CIRCUIT_RACE_SYSTEM.md).
-- * Loads and compiles every circuit (CircuitRegistry). A definition with testSurface = true gets a plain driveable
--   surface (CircuitTestTrack) when workspace.Circuits.<id> is missing (test fixture only).
-- * Puts a paddock marker at each circuit's `entrance`: a cyan ring, a sign and a ProximityPrompt (F) that opens the
--   session menu. P anywhere also opens it (client); away from a circuit the menu offers travel to a paddock.
-- * Remotes in ReplicatedStorage.PattayaRemotes: CircuitRequest (client -> server: action, arg) and CircuitMsg
--   (server -> client: kind, payload). All judging and timing is server-side (RaceSessionService and friends).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local data = ServerStorage:WaitForChild("PattayaData", 30)
local folder = data and data:WaitForChild("circuits", 5)
if not folder then
	return
end
if not data:FindFirstChild("graph") then
	warn("[Circuit] PattayaData.graph is missing (PattayaRoute needs it) - circuit racing disabled")
	return
end
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()
local Registry = require(ServerStorage:WaitForChild("CircuitRegistry"))
local Sessions = require(ServerStorage:WaitForChild("RaceSessionService"))
local Leaderboard = require(ServerStorage:WaitForChild("LeaderboardService"))

local list = Registry.load(folder)
if #list == 0 then
	warn("[Circuit] no circuit definitions could be loaded")
	return
end
-- tell the client map where each venue's entrance really is (the world-map export only has a placeholder)
local worldMap = ReplicatedStorage:FindFirstChild("PattayaWorldMap")
if worldMap then
	for _, c in list do
		local e = c.def.entrance
		if e then
			worldMap:SetAttribute("Circuit_" .. c.id, Vector3.new(e.x, 0, e.z))
		end
	end
end

-- test surfaces ------------------------------------------------------------------------------------------------------
local root = workspace:FindFirstChild("Circuits")
if not root then
	root = Instance.new("Folder")
	root.Name = "Circuits"
	root.Parent = workspace
end
for _, c in list do
	if c.def.testSurface and not root:FindFirstChild(c.id) then
		local builder = ServerStorage:FindFirstChild("CircuitTestTrack")
		if builder then
			local ok, err = pcall(function()
				require(builder).Build(c.def)
			end)
			if not ok then
				warn("[Circuit] test surface for " .. c.id .. " failed: " .. tostring(err))
			end
		end
	end
end

-- remotes ------------------------------------------------------------------------------------------------------------
local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local function remote(name: string): RemoteEvent
	local r = remotes:FindFirstChild(name) or Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r :: RemoteEvent
end
local CircuitRequest = remote("CircuitRequest")
local CircuitMsg = remote("CircuitMsg") -- ("menu", info) ("toast", text) ("warn", {kind, text}) ("sector", r)
-- ("lap", r) ("lights", {at, interval, count}) ("lightsOut", {at}) ("tower", {rows}) ("results", {...})
-- ("spectate", info|nil) ("invite", {...}) ("friends", {circuit, rows})

local function send(plr: Player, kind: string, payload)
	if plr.Parent then
		CircuitMsg:FireClient(plr, kind, payload)
	end
end
Sessions.init(send)

-- paddock markers -----------------------------------------------------------------------------------------------------
local CYAN = Color3.fromRGB(0, 220, 255)
for _, c in list do
	local m = Instance.new("Model")
	m.Name = "Paddock_" .. c.id
	m.ModelStreamingMode = Enum.ModelStreamingMode.Persistent
	local pos = c.entrance.Position
	local ring = Instance.new("Part")
	ring.Name = "Ring"
	ring.Shape = Enum.PartType.Cylinder
	ring.Anchored, ring.CanCollide, ring.CanQuery, ring.CanTouch = true, false, false, false
	ring.Size = Vector3.new(0.3, 40, 40)
	ring.CFrame = CFrame.new(pos + Vector3.new(0, 0.2, 0)) * CFrame.Angles(0, 0, math.rad(90))
	ring.Material = Enum.Material.Neon
	ring.Color = CYAN
	ring.Transparency = 0.6
	ring.Parent = m
	local pole = Instance.new("Part")
	pole.Name = "Pole"
	pole.Anchored, pole.CanCollide, pole.CanTouch = true, false, false
	pole.Size = Vector3.new(1, 22, 1)
	pole.Position = pos + c.entrance.RightVector * 22 + Vector3.new(0, 11, 0)
	pole.Material = Enum.Material.Neon
	pole.Color = CYAN
	pole.Parent = m
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(280, 64)
	bb.StudsOffset = Vector3.new(0, 14, 0)
	bb.MaxDistance = 1200
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = CYAN
	t.TextStrokeTransparency = 0.1
	t.Text = c.name .. "\nPADDOCK  (P)"
	t.Parent = bb
	bb.Parent = pole
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Circuit menu"
	prompt.ObjectText = c.name
	prompt.KeyboardKeyCode = Enum.KeyCode.F -- not P: the client binds P to the same menu everywhere
	prompt.GamepadKeyCode = Enum.KeyCode.DPadRight
	prompt.RequiresLineOfSight = false
	prompt.MaxActivationDistance = 30
	prompt.Parent = pole
	prompt.Triggered:Connect(function(plr)
		send(plr, "menu", Sessions.menuInfo(plr))
	end)
	m.PrimaryPart = ring
	m.Parent = root
end

-- requests -------------------------------------------------------------------------------------------------------------
local lastAt = {}
CircuitRequest.OnServerEvent:Connect(function(plr: Player, action, arg, arg2)
	local t = os.clock()
	if t - (lastAt[plr] or 0) < 0.2 then
		return
	end
	lastAt[plr] = t
	if type(action) ~= "string" then
		return
	end
	if action == "menu" then
		send(plr, "menu", Sessions.menuInfo(plr))
	elseif action == "join" then
		local ok, why = Sessions.join(plr, arg)
		if not ok and why then
			send(plr, "toast", why)
		end
		send(plr, "menu", Sessions.menuInfo(plr))
	elseif action == "leave" then
		Sessions.leave(plr)
		send(plr, "menu", Sessions.menuInfo(plr))
	elseif action == "reset" then
		Sessions.reset(plr)
	elseif action == "start" then
		Sessions.start(plr)
	elseif action == "invite" then
		Sessions.invite(plr, arg)
		send(plr, "menu", Sessions.menuInfo(plr))
	elseif action == "spectate" then
		Sessions.spectate(plr, arg, arg2)
	elseif action == "unspectate" then
		Sessions.unspectate(plr)
	elseif action == "travel" then
		local ok, why = Sessions.travel(plr, arg)
		send(plr, "toast", if ok then "Welcome to the paddock - press P for the circuit menu" else why)
	elseif action == "friends" and type(arg) == "string" and Registry.get(arg) then
		task.spawn(function()
			send(plr, "friends", {circuit = arg, rows = Leaderboard.friends(plr, arg, 10)})
		end)
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	lastAt[plr] = nil
end)
