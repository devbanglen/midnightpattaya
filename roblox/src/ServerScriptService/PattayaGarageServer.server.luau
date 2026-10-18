-- Garage / car shop near the Pattaya start (directive section 7 "Racing classes", owner task 3).
-- * Every player owns the starter hatch for free; other cars are bought with Money and gated by Level
--   (ReplicatedStorage.CarSpecs holds prices, levels, stats, PI and classes).
-- * Owned cars, the selected car and upgrades are saved through PattayaProgress.GetData/SetData:
--     carsOwned   = {hatch = true, kei = true, ...}
--     carSelected = "kei"
--     carUpgrades = {kei = {engine = 1, grip = 0}, ...}
-- * "Spawn my car" builds the selected car beside the garage through RaceCarServer's buildCar
--   (ServerStorage.BuildCar BindableFunction), with attribute Owner = UserId so only its owner can drive it.
--   One personal car per player; the previous one is removed. The 6 shared grid cars are untouched.
-- Placement: a part named GarageSpot in workspace.PattayaWorld.Race (or workspace) overrides the automatic spot,
-- which is PattayaSpawn moved sideways to the left edge of its road (left-hand traffic), facing along the grid.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()
local CarSpecs = require(ReplicatedStorage:WaitForChild("CarSpecs"))
local BuildCar = ServerStorage:WaitForChild("BuildCar", 60) :: BindableFunction?

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local GarageRequest = remotes:FindFirstChild("GarageRequest") or Instance.new("RemoteFunction")
GarageRequest.Name = "GarageRequest"
GarageRequest.Parent = remotes

local RING_RADIUS = 18 -- the client prompt uses the same ring
local USE_RADIUS = 45 -- server-side check: requests only count near the garage
local BAY_SPACING = 22 -- personal cars park in bays along the road past the ring

-- Garage spot --------------------------------------------------------------------------------------------------------
local world = workspace:WaitForChild("PattayaWorld", 120)
local race = world and world:WaitForChild("Race", 60)
local spawnPart = race and race:WaitForChild("PattayaSpawn", 60)
if not spawnPart then
	warn("PattayaGarageServer: no PattayaWorld.Race.PattayaSpawn, garage disabled")
	return
end

local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude
rayParams.FilterDescendantsInstances = {}

-- starts just above road height so lamps, palm fronds and signs overhead don't count; a ray that starts inside a
-- building does not hit it, so buildings read as "not road" too
local function groundAt(pos: Vector3): RaycastResult?
	return workspace:Raycast(Vector3.new(pos.X, pos.Y + 4, pos.Z), Vector3.new(0, -30, 0), rayParams)
end

local function isRoad(hit: RaycastResult?): boolean
	if not hit then
		return false
	end
	local n = hit.Instance.Name
	return n == "Road" or n == "Junction" or n == "Dash" or n == "Centre"
end

local function findSpot(): (Vector3, Vector3)
	-- road direction: the Pattaya grid faces along the race route
	local grid = race:FindFirstChild("StartGrid")
	local slot = grid and grid:FindFirstChild("Slot1")
	local fwd = if slot then slot.CFrame.LookVector else Vector3.new(1, 0, 0)
	fwd = Vector3.new(fwd.X, 0, fwd.Z)
	fwd = if fwd.Magnitude > 0.1 then fwd.Unit else Vector3.new(1, 0, 0)

	local override = race:FindFirstChild("GarageSpot") or workspace:FindFirstChild("GarageSpot")
	if override and override:IsA("BasePart") then
		local look = override.CFrame.LookVector
		look = Vector3.new(look.X, 0, look.Z)
		return override.Position, if look.Magnitude > 0.1 then look.Unit else fwd
	end

	-- walk left from the spawn until the road ends; the ring goes just inside the edge (the shoulder lane)
	local left = Vector3.new(fwd.Z, 0, -fwd.X) -- fwd rotated +90 degrees about Y (right-hand: this is the left side)
	if left:Dot(CFrame.lookAt(Vector3.zero, fwd).RightVector) > 0 then
		left = -left
	end
	local base = spawnPart.Position
	local edge = nil
	for d = 0, 90, 2 do
		if not isRoad(groundAt(base + left * d)) then
			edge = d
			break
		end
	end
	local offset = if edge and edge >= 10 then edge - 8 else 24
	local pos = base + left * offset
	local hit = groundAt(pos)
	pos = Vector3.new(pos.X, if hit then hit.Position.Y else base.Y, pos.Z)
	return pos, fwd
end

local ringPos, roadFwd = findSpot()
local leftDir = Vector3.new(roadFwd.Z, 0, -roadFwd.X)
if leftDir:Dot(CFrame.lookAt(Vector3.zero, roadFwd).RightVector) > 0 then
	leftDir = -leftDir
end

-- Visuals (no collisions, no raycast hits, so cars and traffic drive through them) ------------------------------------
local garage = Instance.new("Model")
garage.Name = "PattayaGarage"
garage.ModelStreamingMode = Enum.ModelStreamingMode.Persistent

local function deco(name: string, size: Vector3, cf: CFrame, color: Color3, material: Enum.Material?, transparency: number?): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Material = material or Enum.Material.SmoothPlastic
	p.Transparency = transparency or 0
	p.Parent = garage
	return p
end

local PURPLE = Color3.fromRGB(170, 70, 255)
local ring = deco("Ring", Vector3.new(0.3, RING_RADIUS * 2, RING_RADIUS * 2),
	CFrame.new(ringPos + Vector3.new(0, 0.4, 0)) * CFrame.Angles(0, 0, math.rad(90)), PURPLE, Enum.Material.Neon, 0.55)
ring.Shape = Enum.PartType.Cylinder
garage.PrimaryPart = ring
-- sign on two posts at the road edge, facing the road
local signBase = ringPos + leftDir * (RING_RADIUS + 3)
local signCf = CFrame.lookAt(signBase + Vector3.new(0, 14, 0), signBase + Vector3.new(0, 14, 0) - leftDir)
for _, s in {-1, 1} do
	deco("Post", Vector3.new(0.8, 14, 0.8), signCf * CFrame.new(s * 9, -7, 0), Color3.fromRGB(30, 30, 36), Enum.Material.Metal)
end
local board = deco("Sign", Vector3.new(20, 6, 0.6), signCf, Color3.fromRGB(20, 12, 34))
local sg = Instance.new("SurfaceGui")
sg.Face = Enum.NormalId.Front
sg.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
sg.PixelsPerStud = 30
sg.LightInfluence = 0
sg.Parent = board
local label = Instance.new("TextLabel")
label.Size = UDim2.fromScale(1, 1)
label.BackgroundTransparency = 1
label.Font = Enum.Font.GothamBlack
label.TextScaled = true
label.TextColor3 = Color3.fromRGB(230, 200, 255)
label.Text = "GARAGE  ·  CAR SHOP"
label.Parent = sg
deco("SignGlow", Vector3.new(20.6, 0.4, 0.7), signCf * CFrame.new(0, -3.3, 0), PURPLE, Enum.Material.Neon)
garage:SetAttribute("RingRadius", RING_RADIUS)
garage.Parent = workspace

-- Player data ---------------------------------------------------------------------------------------------------------
local function readData(plr: Player)
	local owned = Progress.GetData(plr, "carsOwned")
	if type(owned) ~= "table" then
		owned = {}
	end
	owned[CarSpecs.STARTER] = true
	local selected = Progress.GetData(plr, "carSelected")
	if type(selected) ~= "string" or not owned[selected] or not CarSpecs.Cars[selected] then
		selected = CarSpecs.STARTER
	end
	local upgrades = Progress.GetData(plr, "carUpgrades")
	if type(upgrades) ~= "table" then
		upgrades = {}
	end
	return owned, selected, upgrades
end

local function writeData(plr: Player, owned, selected: string, upgrades)
	Progress.SetData(plr, "carsOwned", owned)
	Progress.SetData(plr, "carSelected", selected)
	Progress.SetData(plr, "carUpgrades", upgrades)
end

local function tiers(upgrades, id: string): (number, number)
	local u = upgrades[id]
	if type(u) ~= "table" then
		return 0, 0
	end
	return math.clamp(tonumber(u.engine) or 0, 0, CarSpecs.MAX_TIER), math.clamp(tonumber(u.grip) or 0, 0, CarSpecs.MAX_TIER)
end

local personal: {[Player]: Model} = {}

local function stateFor(plr: Player)
	local ls = plr:FindFirstChild("leaderstats")
	local owned, selected, upgrades = readData(plr)
	return {
		owned = owned,
		selected = selected,
		upgrades = upgrades,
		money = ls and ls:FindFirstChild("Money") and ls.Money.Value or 0,
		level = ls and ls:FindFirstChild("Level") and ls.Level.Value or 1,
		hasCar = personal[plr] ~= nil and personal[plr].Parent ~= nil,
	}
end

local function busy(plr: Player): boolean
	return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
		or plr:GetAttribute("JobActive") == true
end

local function nearGarage(plr: Player): boolean
	local root = plr.Character and plr.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return false
	end
	local d = root.Position - ringPos
	return Vector3.new(d.X, 0, d.Z).Magnitude < USE_RADIUS and math.abs(d.Y) < 40
end

-- Personal cars --------------------------------------------------------------------------------------------------------
local function removePersonal(plr: Player)
	local car = personal[plr]
	personal[plr] = nil
	if car then
		local seat = car:FindFirstChild("DriveSeat") :: VehicleSeat?
		local hum = seat and seat.Occupant
		if hum then
			local sw = seat:FindFirstChild("SeatWeld")
			if sw then sw:Destroy() end
			hum.Sit = false
		end
		car:Destroy()
	end
end

local function bayFree(pos: Vector3): boolean
	for _, m in workspace:GetChildren() do
		if m:IsA("Model") and m:GetAttribute("RaceCar") and m.PrimaryPart then
			local d = m.PrimaryPart.Position - pos
			if Vector3.new(d.X, 0, d.Z).Magnitude < 11 then
				return false
			end
		end
	end
	return true
end

local function spawnPersonal(plr: Player, id: string, engine: number, grip: number): (boolean, string)
	if not BuildCar then
		return false, "Car factory missing (RaceCarServer)"
	end
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local wasInOwn = hum and personal[plr] and hum.SeatPart and hum.SeatPart:IsDescendantOf(personal[plr])
	local onFoot = hum and hum.SeatPart == nil
	removePersonal(plr)
	-- first free bay past the ring along the road (the old car is gone already, so its bay is free again)
	local pos = nil
	for i = 1, 4 do
		local p = ringPos + roadFwd * (RING_RADIUS + 8 + (i - 1) * BAY_SPACING)
		if bayFree(p) then
			pos = p
			break
		end
	end
	if not pos then
		return false, "All garage bays are full, try again in a moment"
	end
	local hit = groundAt(pos)
	local y = (if hit then hit.Position.Y else pos.Y) + 2.6
	local at = Vector3.new(pos.X, y, pos.Z)
	local spec = CarSpecs.Cars[id]
	local ok, car = pcall(function()
		return (BuildCar :: BindableFunction):Invoke(CFrame.lookAt(at, at + roadFwd), spec.color, id,
			{owner = plr.UserId, engine = engine, grip = grip, name = "PersonalCar_" .. plr.UserId})
	end)
	if not (ok and car) then
		warn("PattayaGarageServer: BuildCar failed", car)
		return false, "Could not build the car"
	end
	personal[plr] = car
	car.PrimaryPart.AncestryChanged:Connect(function()
		-- fell out of the world (the engine deletes the chassis) or was removed
		if personal[plr] == car and (car.PrimaryPart == nil or not car:IsDescendantOf(workspace)) then
			personal[plr] = nil
			car:Destroy()
		end
	end)
	if (onFoot or wasInOwn) and hum and hum.Health > 0 then
		task.delay(0.3, function()
			local seat = car.Parent and car:FindFirstChild("DriveSeat") :: VehicleSeat?
			if seat and not seat.Occupant and hum.Parent and hum.SeatPart == nil then
				seat:Sit(hum)
			end
		end)
	end
	return true, ("Your %s is waiting beside the garage"):format(spec.name)
end

-- Requests -----------------------------------------------------------------------------------------------------------
local lastRequest: {[Player]: number} = {}

local function handle(plr: Player, action: any, id: any, kind: any)
	if type(action) ~= "string" then
		return {ok = false, msg = "Bad request"}
	end
	if not plr:GetAttribute("ProgressLoaded") then
		return {ok = false, msg = "Loading your garage..."}
	end
	if action == "state" then
		return {ok = true, state = stateFor(plr)}
	end
	local now = os.clock()
	if lastRequest[plr] and now - lastRequest[plr] < 0.3 then
		return {ok = false, msg = "Slow down", state = stateFor(plr)}
	end
	lastRequest[plr] = now
	if not nearGarage(plr) then
		return {ok = false, msg = "Drive into the garage ring first", state = stateFor(plr)}
	end
	if busy(plr) then
		return {ok = false, msg = "Finish your race or job first", state = stateFor(plr)}
	end
	local ls = plr:FindFirstChild("leaderstats")
	local money = ls and ls:FindFirstChild("Money") :: IntValue?
	local level = ls and ls:FindFirstChild("Level") :: IntValue?
	if not (money and level) then
		return {ok = false, msg = "No progress data"}
	end
	local owned, selected, upgrades = readData(plr)
	local car = type(id) == "string" and CarSpecs.Cars[id]
	if action == "spawn" then
		local e, g = tiers(upgrades, selected)
		local ok, msg = spawnPersonal(plr, selected, e, g)
		return {ok = ok, msg = msg, state = stateFor(plr)}
	end
	if not car then
		return {ok = false, msg = "Unknown car", state = stateFor(plr)}
	end
	local msg
	if action == "buy" then
		if owned[id] then
			return {ok = false, msg = "You already own it", state = stateFor(plr)}
		elseif level.Value < car.level then
			return {ok = false, msg = ("Needs level %d"):format(car.level), state = stateFor(plr)}
		elseif money.Value < car.price then
			return {ok = false, msg = ("Needs ฿%d (you have ฿%d)"):format(car.price, money.Value), state = stateFor(plr)}
		end
		money.Value -= car.price
		owned[id] = true
		selected = id
		msg = ("Bought the %s for ฿%d"):format(car.name, car.price)
	elseif action == "select" then
		if not owned[id] then
			return {ok = false, msg = "Buy it first", state = stateFor(plr)}
		end
		selected = id
		msg = ("%s selected. Spawn it with SPAWN MY CAR"):format(car.name)
	elseif action == "upgrade" then
		if not owned[id] then
			return {ok = false, msg = "Buy it first", state = stateFor(plr)}
		end
		local e, g = tiers(upgrades, id)
		local ok, reason, price = CarSpecs.CanUpgrade(id, e, g, kind)
		if not ok then
			return {ok = false, msg = reason, state = stateFor(plr)}
		elseif money.Value < price then
			return {ok = false, msg = ("Needs ฿%d"):format(price), state = stateFor(plr)}
		end
		money.Value -= price
		if kind == "engine" then e += 1 else g += 1 end
		upgrades[id] = {engine = e, grip = g}
		local d = CarSpecs.Describe(id, e, g)
		msg = ("%s %s tier %d fitted: PI %d. Respawn the car to use it"):format(car.name,
			if kind == "engine" then "engine" else "grip", if kind == "engine" then e else g, d.pi)
	else
		return {ok = false, msg = "Unknown action", state = stateFor(plr)}
	end
	writeData(plr, owned, selected, upgrades)
	return {ok = true, msg = msg, state = stateFor(plr)}
end

GarageRequest.OnServerInvoke = function(plr, action, id, kind)
	local ok, res = pcall(handle, plr, action, id, kind)
	if not ok then
		warn("PattayaGarageServer:", res)
		return {ok = false, msg = "Garage error"}
	end
	return res
end

Players.PlayerRemoving:Connect(function(plr)
	removePersonal(plr)
	lastRequest[plr] = nil
end)
