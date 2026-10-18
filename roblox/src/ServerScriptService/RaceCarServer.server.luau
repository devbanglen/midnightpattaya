-- Spawns the test cars on the start grid and hands physics ownership to the driver.
-- The driving itself (raycast suspension, grip, drift, nitro) runs on the driver's client: CarController.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

-- per-car performance (PI, class); optional so a place without the module still spawns cars
local okSpecs, CarSpecs = pcall(function()
	return require(ReplicatedStorage:WaitForChild("CarSpecs", 10))
end)
if not okSpecs then
	warn("RaceCarServer: ReplicatedStorage.CarSpecs missing, cars get no Class/PI", CarSpecs)
	CarSpecs = nil
end

local GRID = workspace:WaitForChild("RaceMap"):WaitForChild("StartGrid")
-- one car per grid slot; a body mesh in ServerStorage.CarBodies.<id> replaces the placeholder box
local CARS = {
	{id = "jdm_coupe", color = Color3.fromRGB(30, 110, 255)},
	{id = "hatch", color = Color3.fromRGB(255, 120, 20)},
	{id = "supercar", color = Color3.fromRGB(150, 230, 30)},
	{id = "muscle", color = Color3.fromRGB(210, 25, 30)},
	{id = "kei", color = Color3.fromRGB(150, 210, 180)},
	{id = "gt_sedan", color = Color3.fromRGB(30, 30, 35)},
}
local BODY_LENGTH = 16       -- studs, nose to tail
local SUSPENSION_REST, SAG = 1.6, 0.45            -- must match CarController
local REST_EXT = SUSPENSION_REST * (1 - SAG)      -- how far a wheel hangs below its mount at rest
local WHEEL_NAMES = {"FL", "FR", "RL", "RR"}

-- placeholder layout, studs in chassis space (front = -Z, like LookVector)
local DEFAULT_LAYOUT = {
	radius = 1.5,
	width = 1.4,
	rim = Color3.fromRGB(190, 190, 195),
	mounts = {
		FL = Vector3.new(-3.4, 0, -5.2),
		FR = Vector3.new(3.4, 0, -5.2),
		RL = Vector3.new(-3.4, 0, 5.2),
		RR = Vector3.new(3.4, 0, 5.2),
	},
}

local function weld(a, b)
	local w = Instance.new("WeldConstraint")
	w.Part0, w.Part1 = a, b
	w.Parent = b
end

local function visual(model, chassis, name, size, offset, color, material, transparency)
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.CFrame = chassis.CFrame * CFrame.new(offset)
	p.Color = color
	p.Material = material or Enum.Material.SmoothPlastic
	p.Transparency = transparency or 0
	p.CanCollide = false
	p.Massless = true
	p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
	p.Parent = model
	weld(chassis, p)
	return p
end

-- Wheel layout from the body's attributes (export_car.py's <id>_wheels.json: metres in body space, front = -Z).
-- Mounts sit at chassis height and the body is lowered so its wheel centres hang REST_EXT below them. The game
-- wheels are a touch larger than the (blacked-out) fused tyres so they cover them.
local function bodyLayout(src, s)
	local radius = src:GetAttribute("WheelRadius")
	if not radius then return nil end
	local ySum = 0
	for _, n in ipairs(WHEEL_NAMES) do
		ySum += src:GetAttribute("Wheel" .. n).Y * s
	end
	local bodyOffset = -REST_EXT - ySum / 4
	local mounts = {}
	for _, n in ipairs(WHEEL_NAMES) do
		local p = src:GetAttribute("Wheel" .. n) * s
		mounts[n] = Vector3.new(p.X, p.Y + bodyOffset + REST_EXT, p.Z)
	end
	return {
		radius = radius * s * 1.04,
		width = (src:GetAttribute("WheelWidth") or radius * 0.75) * s * 1.15,
		rim = src:GetAttribute("RimColor") or DEFAULT_LAYOUT.rim,
		mounts = mounts,
		bodyOffset = bodyOffset,
	}
end

-- Scales the body mesh to BODY_LENGTH. Returns (hasMesh, layout): without a wheel layout the mesh's own fused tyres
-- are the wheels, so it is dropped until its lowest point sits on the ground at rest.
local function attachBody(model, chassis, id)
	local folder = ServerStorage:FindFirstChild("CarBodies")
	local src = folder and folder:FindFirstChild(id)
	if not src then return false end
	local mesh = src:IsA("MeshPart") and src or src:FindFirstChildWhichIsA("MeshPart", true)
	if not mesh then return false end
	local s = BODY_LENGTH / mesh.Size.Z
	local layout = bodyLayout(src, s)
	local body = mesh:Clone()
	body.Name = "Body"
	body.Size = body.Size * s
	local offsetY = layout and layout.bodyOffset or body.Size.Y / 2 - (DEFAULT_LAYOUT.radius + REST_EXT)
	body.CFrame = chassis.CFrame * CFrame.new(0, offsetY, 0) * CFrame.Angles(0, math.rad(src:GetAttribute("YawFix") or 0), 0)
	body.Anchored = false
	body.CanCollide = false
	body.Massless = true
	body.Parent = model
	weld(chassis, body)
	return true, layout
end

-- opts (optional, personal garage cars): {owner = userId, engine = tier, grip = tier, name = model name}
local function buildCar(cf, color, id, opts)
	opts = opts or {}
	local model = Instance.new("Model")
	model.Name = opts.name or ("RaceCar_" .. id)
	model:SetAttribute("RaceCar", true)
	model:SetAttribute("CarId", id)
	local engine, gripTier = opts.engine or 0, opts.grip or 0
	model:SetAttribute("UpgEngine", engine)
	model:SetAttribute("UpgGrip", gripTier)
	if CarSpecs then
		local d = CarSpecs.Describe(id, engine, gripTier)
		model:SetAttribute("PI", d.pi)
		model:SetAttribute("Class", d.class)
	end
	local owner = opts.owner
	if owner then
		model:SetAttribute("Owner", owner) -- only this UserId may drive it
	end

	local chassis = Instance.new("Part")
	chassis.Name = "Chassis"
	chassis.Size = Vector3.new(7, 1.6, 15)
	chassis.CFrame = cf
	chassis.Color = Color3.fromRGB(25, 25, 28)
	chassis.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0, 0, 100, 1) -- no ground friction: grip is scripted
	chassis.TopSurface, chassis.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
	chassis.Parent = model
	model.PrimaryPart = chassis

	local hasMesh, meshLayout = attachBody(model, chassis, id)
	local layout = meshLayout or DEFAULT_LAYOUT
	local showWheels = meshLayout ~= nil or not hasMesh
	model:SetAttribute("WheelRadius", layout.radius)
	if hasMesh then
		chassis.Transparency = 1
	else
		-- placeholder body until the mesh is imported
		visual(model, chassis, "Body", Vector3.new(7.4, 1.8, 15.6), Vector3.new(0, 0.9, 0), color)
		visual(model, chassis, "Cabin", Vector3.new(6.2, 2.2, 7), Vector3.new(0, 2.9, 1), Color3.fromRGB(20, 25, 35), Enum.Material.Glass, 0.35)
		visual(model, chassis, "Spoiler", Vector3.new(7, 0.3, 1.6), Vector3.new(0, 3.2, 7.2), color)
		visual(model, chassis, "HeadlightL", Vector3.new(1.6, 0.5, 0.2), Vector3.new(-2.4, 1.1, -7.85), Color3.fromRGB(255, 250, 230), Enum.Material.Neon)
		visual(model, chassis, "HeadlightR", Vector3.new(1.6, 0.5, 0.2), Vector3.new(2.4, 1.1, -7.85), Color3.fromRGB(255, 250, 230), Enum.Material.Neon)
		visual(model, chassis, "TailLights", Vector3.new(6, 0.4, 0.2), Vector3.new(0, 1.2, 7.85), Color3.fromRGB(255, 30, 30), Enum.Material.Neon)
	end

	local seat = Instance.new("VehicleSeat")
	seat.Name = "DriveSeat"
	seat.Size = Vector3.new(2, 1, 2)
	seat.CFrame = chassis.CFrame * CFrame.new(-1.4, 1.3, 1)
	seat.Transparency = 1
	seat.Massless = true
	seat.CanCollide = false
	seat.MaxSpeed, seat.Torque, seat.TurnSpeed = 0, 0, 0 -- the client controller drives
	seat.HeadsUpDisplay = false
	seat.Parent = model
	weld(chassis, seat)

	local r, width = layout.radius, layout.width
	local function wheelPart(parent, name, size, cf, color, material)
		local p = Instance.new("Part")
		p.Name = name
		p.Size = size
		p.CFrame = cf
		p.Color = color
		p.Material = material or Enum.Material.SmoothPlastic
		p.CanCollide = false
		p.Massless = true
		p.Transparency = showWheels and 0 or 1
		p.TopSurface, p.BottomSurface = Enum.SurfaceType.Smooth, Enum.SurfaceType.Smooth
		p.Parent = parent
		return p
	end
	for _, name in ipairs(WHEEL_NAMES) do
		local pos = layout.mounts[name]
		local att = Instance.new("Attachment")
		att.Name = "Mount_" .. name
		att.Position = pos
		att.Parent = chassis

		local cf = chassis.CFrame * CFrame.new(pos - Vector3.new(0, REST_EXT, 0))
		local wheel = wheelPart(model, "Wheel_" .. name, Vector3.new(width, r * 2, r * 2), cf, Color3.fromRGB(22, 22, 24))
		wheel.Shape = Enum.PartType.Cylinder
		local rim = wheelPart(wheel, "Rim", Vector3.new(width + 0.08, r * 1.3, r * 1.3), cf, layout.rim, Enum.Material.Metal)
		rim.Shape = Enum.PartType.Cylinder
		weld(wheel, rim)
		-- spokes, so the spin reads on screen
		local spokeColor = layout.rim:Lerp(Color3.new(0, 0, 0), 0.35)
		for k = 0, 2 do
			local spoke = wheelPart(wheel, "Spoke", Vector3.new(width + 0.14, r * 0.22, r * 1.25), cf * CFrame.Angles(math.rad(k * 60), 0, 0), spokeColor, Enum.Material.Metal)
			weld(wheel, spoke)
		end

		-- a Weld (not WeldConstraint) so the controller can move the wheel through C0
		local w = Instance.new("Weld")
		w.Name = "WheelWeld"
		w.Part0, w.Part1 = chassis, wheel
		w.C0 = CFrame.new(pos - Vector3.new(0, REST_EXT, 0))
		w.Parent = wheel
	end

	-- the driver is hidden while seated (the generated bodies have no cabin room for a character)
	local hidden = {}
	local function hideDriver(character)
		for _, d in ipairs(character:GetDescendants()) do
			if (d:IsA("BasePart") or d:IsA("Decal")) and d.Transparency < 1 then
				hidden[d] = d.Transparency
				d.Transparency = 1
			end
		end
	end
	local function showDriver()
		for d, t in pairs(hidden) do
			if d.Parent then d.Transparency = t end
		end
		table.clear(hidden)
	end

	seat:GetPropertyChangedSignal("Occupant"):Connect(function()
		local hum = seat.Occupant
		local plr = hum and Players:GetPlayerFromCharacter(hum.Parent)
		showDriver()
		if owner and plr and plr.UserId ~= owner then
			-- someone else's personal car: throw them out again
			task.defer(function()
				local sw = seat:FindFirstChild("SeatWeld")
				if sw then sw:Destroy() end
				if hum.Parent then
					hum.Sit = false
					hum.Jump = true
				end
			end)
			plr:SetAttribute("GarageMsg", "That car belongs to someone else")
			plr:SetAttribute("GarageMsgAt", workspace:GetServerTimeNow())
			return
		end
		if plr then hideDriver(hum.Parent) end
		if plr then
			chassis:SetNetworkOwner(plr)
		elseif chassis:IsDescendantOf(workspace) then
			chassis:SetNetworkOwner(nil) -- parked: the server holds it up (see the Heartbeat below)
		end
	end)

	model.Parent = workspace
	chassis:SetNetworkOwner(nil)
	return model
end

-- Parked cars: same spring as CarController, plus a parking brake, so they rest on their wheels instead of the
-- chassis. Wheel radius comes from the car (WheelRadius attribute).
local REST, DAMPING = SUSPENSION_REST, 0.6
local parkParams = RaycastParams.new()
parkParams.FilterType = Enum.RaycastFilterType.Exclude

RunService.Heartbeat:Connect(function(dt)
	dt = math.min(dt, 1 / 30)
	for _, model in ipairs(workspace:GetChildren()) do
		if not model:GetAttribute("RaceCar") then continue end
		local seat, chassis = model:FindFirstChild("DriveSeat"), model.PrimaryPart
		if not (seat and chassis) or seat.Occupant then continue end
		local up = chassis.CFrame.UpVector
		local mass = chassis.AssemblyMass
		local RADIUS = model:GetAttribute("WheelRadius") or DEFAULT_LAYOUT.radius
		local k = mass * workspace.Gravity / 4 / (REST * SAG)
		local c = 2 * math.sqrt(k * mass / 4) * DAMPING
		parkParams.FilterDescendantsInstances = {model}
		local grounded = 0
		for _, mount in ipairs(chassis:GetChildren()) do
			if mount:IsA("Attachment") then
				local origin = mount.WorldPosition
				local hit = workspace:Raycast(origin, -up * (REST + RADIUS), parkParams)
				if hit then
					grounded += 1
					local compression = REST - math.max(hit.Distance - RADIUS, 0)
					local force = k * compression - c * chassis:GetVelocityAtPosition(origin):Dot(up)
					if force > 0 then
						chassis:ApplyImpulseAtPosition(up * force * dt, origin)
					end
				end
			end
		end
		if grounded >= 2 then
			-- parking brake: bleed off horizontal motion and spin
			local v = chassis.AssemblyLinearVelocity
			local flat = v - up * v:Dot(up)
			chassis:ApplyImpulse(-flat * mass * math.min(1, 4 * dt))
			local av = chassis.AssemblyAngularVelocity
			chassis.AssemblyAngularVelocity = av - up * av:Dot(up) * math.min(1, 4 * dt)
		end
	end
end)

local function spawnAtSlot(grid, i, spec)
	local slot = grid:FindFirstChild("Slot" .. i)
	if not slot then return end
	-- RaceMap slots are axis-aligned boxes and its cars face +X along the south road; Pattaya slots are rotated to
	-- face along the race route
	local look = if grid == GRID then Vector3.new(1, 0, 0) else slot.CFrame.LookVector
	local cf = CFrame.lookAt(slot.Position + Vector3.new(0, 2.6, 0), slot.Position + Vector3.new(0, 2.6, 0) + look)
	local car = buildCar(cf, spec.color, spec.id)
	-- a car that falls out of the world loses its chassis to the engine: clear the rest, put a new one on its slot
	local gone = false
	car.PrimaryPart.AncestryChanged:Connect(function()
		if gone then return end
		if car.PrimaryPart == nil or not car:IsDescendantOf(workspace) then
			gone = true
			car:Destroy()
			task.delay(3, spawnAtSlot, grid, i, spec)
		end
	end)
end

-- PattayaGarageServer builds personal cars through the same path: BuildCar:Invoke(cframe, color, carId, opts)
local factory = ServerStorage:FindFirstChild("BuildCar") or Instance.new("BindableFunction")
factory.Name = "BuildCar"
factory.OnInvoke = function(cf, color, id, opts)
	return buildCar(cf, color, id, opts)
end
factory.Parent = ServerStorage

for i, spec in ipairs(CARS) do
	spawnAtSlot(GRID, i, spec)
end

-- the Pattaya world (generated by ServerStorage.PattayaBuilder) has its own start grid on the Central Loop
local pattaya = workspace:FindFirstChild("PattayaWorld")
local pattayaGrid = pattaya and pattaya:FindFirstChild("Race") and pattaya.Race:FindFirstChild("StartGrid")
if pattayaGrid then
	for i, spec in ipairs(CARS) do
		spawnAtSlot(pattayaGrid, i, spec)
	end
end
