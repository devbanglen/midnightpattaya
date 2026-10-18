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
	-- idle hold: no throttle and slower than this -> the brakes hold the car (no creep on the grid or at lights)
	idleHoldSpeed = 3,      -- studs/s
	idleHoldRate = 20,      -- 1/s: how fast the hold bleeds off the remaining speed (capped by the car's brake)
	turnRate = 2.3,         -- rad/s at full lock
	grip = 9,               -- how fast sideways speed is killed
	driftGrip = 1.4,
	driftTurnBoost = 1.4,
	airUpright = 3,         -- pitch/roll damping while airborne
	-- nitro gauge (RayCity SP style): drains while boosting, refills slowly, faster while drifting; race and sprint
	-- checkpoints add a chunk (NitroBonus remote)
	nitroMax = 100,
	nitroDrain = 28,        -- per second while boosting
	nitroRegen = 4,         -- per second, always
	nitroDriftRegen = 14,   -- extra per second while drifting above 40 studs/s
}

-- Per-car performance comes from ReplicatedStorage.CarSpecs (the car's CarId / UpgEngine / UpgGrip attributes);
-- CONFIG above stays the fallback when the module or the car id is missing. Suspension values always come from
-- CONFIG (RaceCarServer's parked spring uses the same numbers).
-- Player attributes set by event servers (Night Run / Survival):
--   Equalised = true  -> every car drives with CarSpecs.Equalised() (the stock starter hatch)
--   SpeedCap = number -> caps both the top speed and the nitro top speed
-- Both are client-trusted, like the rest of this controller; the race servers keep their own teleport checks.
local okSpecs, CarSpecs = pcall(function()
	return require(game:GetService("ReplicatedStorage"):WaitForChild("CarSpecs", 10))
end)
if not okSpecs then
	CarSpecs = nil
end

local tune = CONFIG -- performance table of the car being driven (see pickTune)

local state = {
	nitro = false,
	drift = false,
	spin = 0,
	fuel = 100,
	boosting = false,
	speed = 0,  -- forward speed of the last physics step (studs/s, signed), for the HUD telemetry below
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
local nitroBack = Instance.new("Frame")
nitroBack.AnchorPoint = Vector2.new(1, 1)
nitroBack.Position = UDim2.new(1, -24, 1, -96)
nitroBack.Size = UDim2.fromOffset(220, 12)
nitroBack.BackgroundColor3 = Color3.fromRGB(20, 20, 30)
nitroBack.BackgroundTransparency = 0.3
nitroBack.Parent = gui
Instance.new("UICorner", nitroBack).CornerRadius = UDim.new(0, 6)
local nitroFill = Instance.new("Frame")
nitroFill.Size = UDim2.fromScale(1, 1)
nitroFill.BackgroundColor3 = Color3.fromRGB(0, 200, 255)
nitroFill.Parent = nitroBack
Instance.new("UICorner", nitroFill).CornerRadius = UDim.new(0, 6)
local nitroLabel = Instance.new("TextLabel")
nitroLabel.AnchorPoint = Vector2.new(1, 1)
nitroLabel.Position = UDim2.new(1, -250, 1, -92)
nitroLabel.Size = UDim2.fromOffset(50, 20)
nitroLabel.BackgroundTransparency = 1
nitroLabel.Font = Enum.Font.GothamBlack
nitroLabel.TextSize = 16
nitroLabel.TextColor3 = Color3.fromRGB(0, 200, 255)
nitroLabel.Text = "NOS"
nitroLabel.Parent = gui
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
local carLabel = Instance.new("TextLabel")
carLabel.AnchorPoint = Vector2.new(1, 1)
carLabel.Position = UDim2.new(1, -24, 1, -112)
carLabel.Size = UDim2.fromOffset(300, 20)
carLabel.BackgroundTransparency = 1
carLabel.Font = Enum.Font.GothamBold
carLabel.TextSize = 16
carLabel.TextColor3 = Color3.new(1, 1, 1)
carLabel.TextStrokeTransparency = 0.5
carLabel.TextXAlignment = Enum.TextXAlignment.Right
carLabel.Text = ""
carLabel.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

-- Legacy hide (docs/UI_CONTRACT.md): while LocalPlayer attribute MidnightHUD == true (set locally by ui-core, per player,
-- never replicated state) the new HUD (MidnightSpeedo / MidnightActivity + ui-core's key prompts) draws speed, nitro, car name and the key hint, so these step aside. The
-- labels keep updating underneath; setting the attribute false brings them straight back.
local function applyLegacyHide()
	local show = player:GetAttribute("MidnightHUD") ~= true
	speedLabel.Visible = show
	nitroBack.Visible = show
	nitroLabel.Visible = show
	carLabel.Visible = show
	hint.Visible = show
end
player:GetAttributeChangedSignal("MidnightHUD"):Connect(applyLegacyHide)
applyLegacyHide()

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

-- compact touch layout (docs/UI_SYSTEM.md "Round 3: touch controls"): MidnightUI.TouchControls owns the button grid
local function touchRegister(name: string, opts: {[string]: any})
	local m = game:GetService("ReplicatedStorage"):FindFirstChild("MidnightUI")
	m = m and m:FindFirstChild("TouchControls")
	if m then (require(m) :: any).register(name, opts) end
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
	touchRegister("CarNitro", {slot = "nitro", title = "NOS", position = UDim2.new(1, -110, 1, -200)})
	touchRegister("CarDrift", {slot = "drift", title = "DRIFT", position = UDim2.new(1, -200, 1, -150)})
	touchRegister("CarReset", {slot = "reset", title = "R", position = UDim2.new(1, -110, 1, -290)})
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
				-- push along the ground normal, not the chassis up: a slightly pitched chassis (driver or body mass
				-- off the mounts' centre) would otherwise get a constant forward/back push of g * sin(pitch)
				local push = if hit.Normal:Dot(up) > 0.5 then hit.Normal else up
				chassis:ApplyImpulseAtPosition(push * force * dt, origin)
			end
		end
		-- wheel visual: suspension travel, steering on the front, spin from speed
		local steerAngle = (name == "FL" or name == "FR") and -steer * math.rad(28) or 0
		current.welds[name].C0 = CFrame.new(mount.Position - Vector3.new(0, ext, 0))
			* CFrame.Angles(0, steerAngle, 0) * CFrame.Angles(-state.spin, 0, 0)
	end

	if grounded >= 2 then
		local impulse = Vector3.zero
		state.boosting = state.nitro and state.fuel > 0 and throttle > 0
		local top = state.boosting and tune.nitroSpeed or tune.maxSpeed
		local cap = player:GetAttribute("SpeedCap")
		local capped = type(cap) == "number" and cap > 0
		if capped then
			top = math.min(top, cap)
		end
		local accel = 0
		if capped and fs > top + 2 then
			-- over the event's cap (e.g. it was just set): ease down to it
			accel = -math.min(tune.brake, (fs - top) * 3)
		elseif throttle > 0 then
			if fs < -2 then
				accel = tune.brake
			elseif fs < top then
				accel = (state.boosting and tune.nitroAccel or tune.accel) * throttle
			end
		elseif throttle < 0 then
			if fs > 2 then
				accel = -tune.brake
			elseif fs > -tune.reverseSpeed then
				accel = tune.accel * 0.6 * throttle
			end
		elseif math.abs(fs) < CONFIG.idleHoldSpeed then
			-- idle and almost stopped: hold the car (coastDrag alone has no static hold, so any small push creeps)
			accel = -math.clamp(fs * CONFIG.idleHoldRate, -tune.brake, tune.brake)
		else
			accel = -fs * tune.coastDrag
		end
		impulse += fwd * accel * mass * dt

		-- grip: kill sideways sliding (much less while the handbrake is on = drift)
		local grip = state.drift and tune.driftGrip or tune.grip
		impulse -= right * ls * mass * math.min(1, grip * dt)
		chassis:ApplyImpulse(impulse)

		-- steering: drive the yaw rate toward the target (scales in with speed, flips in reverse)
		local speedFactor = math.clamp(math.abs(fs) / 35, 0, 1)
		local dir = fs >= 0 and 1 or -1
		local target = -steer * tune.turnRate * speedFactor * dir * (state.drift and tune.driftTurnBoost or 1)
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

	-- nitro gauge
	if state.boosting then
		state.fuel -= tune.nitroDrain * dt
	else
		local regen = tune.nitroRegen
		if state.drift and math.abs(fs) > 40 and grounded >= 2 then
			regen += tune.nitroDriftRegen
		end
		state.fuel += regen * dt
	end
	state.fuel = math.clamp(state.fuel, 0, tune.nitroMax)
	nitroFill.Size = UDim2.fromScale(state.fuel / tune.nitroMax, 1)
	nitroFill.BackgroundColor3 = if state.boosting then Color3.fromRGB(255, 120, 40) else Color3.fromRGB(0, 200, 255)
	speedLabel.Text = string.format("%d km/h%s", math.floor(math.abs(fs) * 1.0 + 0.5), state.boosting and " NOS" or "")
	state.speed = fs
end

-- Enter / exit ------------------------------------------------------------------
local function pickTune()
	if not current then
		return
	end
	local model = current.seat.Parent
	local equalised = player:GetAttribute("Equalised") == true
	local base = model:GetAttribute("CarId")
	if CarSpecs and equalised then
		tune = CarSpecs.Equalised()
	elseif CarSpecs and base and CarSpecs.Cars[base] then
		tune = CarSpecs.ForModel(model)
	else
		tune = CONFIG
	end
	state.fuel = math.min(state.fuel, tune.nitroMax)
	local text = ""
	local spec = CarSpecs and base and CarSpecs.Cars[base]
	if spec then
		text = ("%s  ·  %s %d"):format(spec.name, model:GetAttribute("Class") or "", model:GetAttribute("PI") or 0)
		carLabel.TextColor3 = CarSpecs.ClassColor(model:GetAttribute("Class") or "")
	end
	if equalised then
		text ..= "  ·  EQUALISED"
	end
	local cap = player:GetAttribute("SpeedCap")
	if type(cap) == "number" and cap > 0 then
		text ..= ("  ·  CAP %d"):format(cap)
	end
	carLabel.Text = text
	-- HUD telemetry: what the car is (the model's own attributes, set by RaceCarServer from CarSpecs)
	player:SetAttribute("HUD_CarName", if spec then spec.name else model.Name)
	player:SetAttribute("HUD_Class", model:GetAttribute("Class") or "")
	player:SetAttribute("HUD_PI", model:GetAttribute("PI") or 0)
end
player:GetAttributeChangedSignal("Equalised"):Connect(pickTune)
player:GetAttributeChangedSignal("SpeedCap"):Connect(pickTune)

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
	pickTune()
	bindActions()
	gui.Enabled = true
end

local hudTelemetryReset -- forward (telemetry block below)

local function exit()
	current = nil
	unbindActions()
	gui.Enabled = false
	hudTelemetryReset()
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

-- checkpoint bonuses from PattayaRaceServer / PattayaSprintServer
task.spawn(function()
	local remotes = game:GetService("ReplicatedStorage"):WaitForChild("PattayaRemotes", 60)
	local bonus = remotes and remotes:WaitForChild("NitroBonus", 60)
	if bonus then
		bonus.OnClientEvent:Connect(function(amount)
			state.fuel = math.min(tune.nitroMax, state.fuel + amount)
		end)
	end
end)

-- HUD telemetry (docs/UI_RACE_HUD.md) -------------------------------------------------------------------------------
-- Published as LocalPlayer attributes at <= 20 Hz, only when a value changes. Read-only for the HUD scripts; nothing
-- here feeds back into driving. HUD_SpeedKmh keeps the game's convention (studs/s shown 1:1 as km/h). Only measured
-- values are published: there is no gearbox or engine model, so no gear / RPM attribute exists (owner rule).
local TELEMETRY_DT = 1 / 20
local tele = {acc = 0, last = {}}

local function publish(name: string, value: any)
	if tele.last[name] ~= value then
		tele.last[name] = value
		player:SetAttribute(name, value)
	end
end

hudTelemetryReset = function()
	publish("HUD_InCar", false)
	publish("HUD_SpeedKmh", 0)
	publish("HUD_Boosting", false)
	publish("HUD_Drifting", false)
end
hudTelemetryReset()

local function publishTelemetry()
	local fs = state.speed
	publish("HUD_InCar", true)
	publish("HUD_SpeedKmh", math.floor(math.abs(fs) + 0.5))
	-- percent of this car's tank (the muscle car's tank is 120): the same fraction the old CarHUD bar shows
	publish("HUD_Nitro", math.floor(state.fuel / math.max(tune.nitroMax, 1) * 100 + 0.5))
	publish("HUD_Boosting", state.boosting == true)
	-- drifting = handbrake held while actually moving (the same > 40 studs/s rule that gives the drift nitro refill)
	publish("HUD_Drifting", state.drift == true and math.abs(fs) > 40)
end

RunService.Heartbeat:Connect(function(dt)
	if current and current.chassis.Parent then
		step(math.min(dt, 1 / 30))
		tele.acc += dt
		if tele.acc >= TELEMETRY_DT then
			tele.acc = 0
			publishTelemetry()
		end
	end
end)
