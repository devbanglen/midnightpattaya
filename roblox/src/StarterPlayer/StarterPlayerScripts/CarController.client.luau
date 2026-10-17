-- Arcade car controller (RayCity feel): raycast suspension, scripted grip, handbrake drift, nitro.
-- Runs on the driver's client, which owns the car's physics (RaceCarServer sets the network owner).
-- Input: VehicleSeat throttle/steer (WASD, arrows, gamepad, mobile stick) + Nitro / Drift / Reset actions.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")

local player = Players.LocalPlayer

local CONFIG = {
	suspensionRest = 1.6,   -- studs from mount to wheel centre at full extension
	wheelRadius = 1.5,      -- fallback; each car carries its own WheelRadius attribute
	sag = 0.45,             -- spring compression at rest (fraction of rest length)
	dampingRatio = 0.35,
	maxSpeed = 160,         -- studs/s (~160 km/h on the HUD)
	nitroSpeed = 215,
	accel = 60,
	nitroAccel = 110,
	reverseSpeed = 45,
	brake = 130,
	coastDrag = 0.25,
	turnRate = 2.3,         -- rad/s at full lock
	grip = 9,               -- how fast sideways speed is killed
	driftGrip = 1.4,
	driftTurnBoost = 1.4,
	airUpright = 3,         -- pitch/roll damping while airborne
}

local state = {
	nitro = false,
	drift = false,
	spin = 0,
}

local params = RaycastParams.new()
params.FilterType = Enum.RaycastFilterType.Exclude

-- HUD --------------------------------------------------------------------------
local gui = Instance.new("ScreenGui")
gui.Name = "CarHUD"
gui.ResetOnSpawn = false
gui.Enabled = false
local speedLabel = Instance.new("TextLabel")
speedLabel.AnchorPoint = Vector2.new(1, 1)
speedLabel.Position = UDim2.new(1, -24, 1, -24)
speedLabel.Size = UDim2.fromOffset(220, 70)
speedLabel.BackgroundTransparency = 1
speedLabel.Font = Enum.Font.GothamBlack
speedLabel.TextScaled = true
speedLabel.TextColor3 = Color3.new(1, 1, 1)
speedLabel.TextStrokeTransparency = 0.4
speedLabel.TextXAlignment = Enum.TextXAlignment.Right
speedLabel.Parent = gui
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0, 1)
hint.Position = UDim2.new(0, 16, 1, -16)
hint.Size = UDim2.fromOffset(460, 22)
hint.BackgroundTransparency = 1
hint.Font = Enum.Font.GothamMedium
hint.TextSize = 16
hint.TextColor3 = Color3.new(1, 1, 1)
hint.TextStrokeTransparency = 0.5
hint.TextXAlignment = Enum.TextXAlignment.Left
hint.Text = "WASD drive  |  Shift nitro  |  Ctrl drift  |  R reset  |  Space exit"
hint.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

-- Actions (CAS also gives mobile buttons) ----------------------------------------
local current -- {seat, chassis, mounts, wheels}

local function onNitro(_, inputState)
	state.nitro = inputState == Enum.UserInputState.Begin
	return Enum.ContextActionResult.Sink
end

local function onDrift(_, inputState)
	state.drift = inputState == Enum.UserInputState.Begin
	return Enum.ContextActionResult.Sink
end

local function onReset(_, inputState)
	if inputState == Enum.UserInputState.Begin and current then
		local chassis = current.chassis
		local look = chassis.CFrame.LookVector
		local flat = Vector3.new(look.X, 0, look.Z)
		if flat.Magnitude < 0.1 then flat = Vector3.new(0, 0, -1) end
		local pos = chassis.Position + Vector3.new(0, 6, 0)
		chassis.AssemblyLinearVelocity = Vector3.zero
		chassis.AssemblyAngularVelocity = Vector3.zero
		chassis.CFrame = CFrame.lookAt(pos, pos + flat)
	end
	return Enum.ContextActionResult.Sink
end

local function bindActions()
	ContextActionService:BindAction("CarNitro", onNitro, true, Enum.KeyCode.LeftShift, Enum.KeyCode.ButtonR2)
	ContextActionService:BindAction("CarDrift", onDrift, true, Enum.KeyCode.LeftControl, Enum.KeyCode.ButtonL2)
	ContextActionService:BindAction("CarReset", onReset, true, Enum.KeyCode.R, Enum.KeyCode.ButtonY)
	ContextActionService:SetTitle("CarNitro", "NOS")
	ContextActionService:SetTitle("CarDrift", "DRIFT")
	ContextActionService:SetTitle("CarReset", "R")
	ContextActionService:SetPosition("CarNitro", UDim2.new(1, -110, 1, -200))
	ContextActionService:SetPosition("CarDrift", UDim2.new(1, -200, 1, -150))
	ContextActionService:SetPosition("CarReset", UDim2.new(1, -110, 1, -290))
end

local function unbindActions()
	for _, name in ipairs({"CarNitro", "CarDrift", "CarReset"}) do
		ContextActionService:UnbindAction(name)
	end
	state.nitro, state.drift = false, false
end

-- Physics step ------------------------------------------------------------------
local function step(dt)
	local seat, chassis = current.seat, current.chassis
	local cf = chassis.CFrame
	local up, fwd, right = cf.UpVector, cf.LookVector, cf.RightVector
	local mass = chassis.AssemblyMass
	local g = workspace.Gravity

	local k = mass * g / 4 / (CONFIG.suspensionRest * CONFIG.sag)
	local c = 2 * math.sqrt(k * mass / 4) * CONFIG.dampingRatio
	local radius = current.radius
	local reach = CONFIG.suspensionRest + radius

	local v = chassis.AssemblyLinearVelocity
	local fs = v:Dot(fwd)
	local ls = v:Dot(right)
	local steer = seat.SteerFloat
	local throttle = seat.ThrottleFloat
	state.spin += fs * dt / radius

	local grounded = 0
	for name, mount in pairs(current.mounts) do
		local origin = mount.WorldPosition
		local hit = workspace:Raycast(origin, -up * reach, params)
		local ext = CONFIG.suspensionRest
		if hit then
			grounded += 1
			ext = math.max(hit.Distance - radius, 0)
			local compression = CONFIG.suspensionRest - ext
			local springVel = chassis:GetVelocityAtPosition(origin):Dot(up)
			local force = k * compression - c * springVel
			if force > 0 then
				chassis:ApplyImpulseAtPosition(up * force * dt, origin)
			end
		end
		-- wheel visual: suspension travel, steering on the front, spin from speed
		local steerAngle = (name == "FL" or name == "FR") and -steer * math.rad(28) or 0
		current.welds[name].C0 = CFrame.new(mount.Position - Vector3.new(0, ext, 0))
			* CFrame.Angles(0, steerAngle, 0) * CFrame.Angles(-state.spin, 0, 0)
	end

	if grounded >= 2 then
		local impulse = Vector3.zero
		local top = state.nitro and CONFIG.nitroSpeed or CONFIG.maxSpeed
		local accel = 0
		if throttle > 0 then
			if fs < -2 then
				accel = CONFIG.brake
			elseif fs < top then
				accel = (state.nitro and CONFIG.nitroAccel or CONFIG.accel) * throttle
			end
		elseif throttle < 0 then
			if fs > 2 then
				accel = -CONFIG.brake
			elseif fs > -CONFIG.reverseSpeed then
				accel = CONFIG.accel * 0.6 * throttle
			end
		else
			accel = -fs * CONFIG.coastDrag
		end
		impulse += fwd * accel * mass * dt

		-- grip: kill sideways sliding (much less while the handbrake is on = drift)
		local grip = state.drift and CONFIG.driftGrip or CONFIG.grip
		impulse -= right * ls * mass * math.min(1, grip * dt)
		chassis:ApplyImpulse(impulse)

		-- steering: drive the yaw rate toward the target (scales in with speed, flips in reverse)
		local speedFactor = math.clamp(math.abs(fs) / 35, 0, 1)
		local dir = fs >= 0 and 1 or -1
		local target = -steer * CONFIG.turnRate * speedFactor * dir * (state.drift and CONFIG.driftTurnBoost or 1)
		local av = chassis.AssemblyAngularVelocity
		local yaw = av:Dot(up)
		local newYaw = yaw + (target - yaw) * math.min(1, 8 * dt)
		chassis.AssemblyAngularVelocity = av + up * (newYaw - yaw)
	else
		-- airborne: damp pitch/roll so jumps land wheels-down
		local av = chassis.AssemblyAngularVelocity
		local yawPart = up * av:Dot(up)
		chassis.AssemblyAngularVelocity = yawPart + (av - yawPart) * (1 - math.min(1, CONFIG.airUpright * dt))
	end

	speedLabel.Text = string.format("%d km/h%s", math.floor(math.abs(fs) * 1.0 + 0.5), state.nitro and " NOS" or "")
end

-- Enter / exit ------------------------------------------------------------------
local function enter(seat)
	local model = seat.Parent
	local chassis = model:FindFirstChild("Chassis")
	if not chassis then return end
	local mounts, welds = {}, {}
	for _, name in ipairs({"FL", "FR", "RL", "RR"}) do
		mounts[name] = chassis:FindFirstChild("Mount_" .. name)
		local wheel = model:FindFirstChild("Wheel_" .. name)
		welds[name] = wheel and wheel:FindFirstChild("WheelWeld")
		if not (mounts[name] and welds[name]) then return end
	end
	params.FilterDescendantsInstances = {model, player.Character}
	current = {seat = seat, chassis = chassis, mounts = mounts, welds = welds, radius = model:GetAttribute("WheelRadius") or CONFIG.wheelRadius}
	bindActions()
	gui.Enabled = true
end

local function exit()
	current = nil
	unbindActions()
	gui.Enabled = false
end

local function watchCharacter(character)
	local humanoid = character:WaitForChild("Humanoid")
	humanoid.Seated:Connect(function(active, seatPart)
		if active and seatPart and seatPart:IsA("VehicleSeat") and seatPart.Parent:GetAttribute("RaceCar") then
			enter(seatPart)
		else
			exit()
		end
	end)
	humanoid.Died:Connect(exit)
end

if player.Character then watchCharacter(player.Character) end
player.CharacterAdded:Connect(watchCharacter)

RunService.Heartbeat:Connect(function(dt)
	if current and current.chassis.Parent then
		step(math.min(dt, 1 / 30))
	end
end)
