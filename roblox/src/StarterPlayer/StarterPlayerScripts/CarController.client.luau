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

-- Recovery Kit (docs/RECOVERY_AND_COLLISION.md): auto-upright, R rules, stuck prompt + server rescue. Settings are
-- workspace attributes read through ReplicatedStorage.PattayaRecovery; Recovery_Enabled = false (or the module
-- missing) gives back today's R exactly.
local okRec, Recovery = pcall(function()
	return require(game:GetService("ReplicatedStorage"):WaitForChild("PattayaRecovery", 10))
end)
if not okRec then
	Recovery = nil
end

local state = {
	nitro = false,
	drift = false,
	spin = 0,
	fuel = 100,
	boosting = false,
	speed = 0,  -- forward speed of the last physics step (studs/s, signed), for the HUD telemetry below
	onRoad = false, -- a wheel ray hit a road part in the last step (stuck / off-road detection only)
}

-- recovery state (reset on every enter)
local rec = {
	lastResetAt = nil :: number?, -- os.clock() of the last manual R
	enteredAt = 0,
	upright = {upside = 0, tilt = 0},
	stuck = {t = 0} :: any,
	offRoad = {t = 0},
	anim = nil :: any,        -- {from, to, t, dur, keep}: the auto-upright turn-over in progress
	prompt = nil :: string?,  -- why the rescue prompt shows ("stuck" / "offroad")
	promptAt = 0,
	holdStart = nil :: number?, -- R held on the prompt since (os.clock)
	lastRequestAt = -math.huge,
	lastGoodLook = Vector3.new(0, 0, -1),
	uprights = 0,
}

-- arcade traffic hit in progress (CollisionModel = "arcade"; PattayaTraffic finds the touch, applyImpact below):
-- {start, untilT, steer, slide, spinT, w0} -- steering scale, drift grip and the scripted yaw kick while it lasts.
-- Pitch and roll are held at zero for the whole window, so a traffic hit can never roll the car.
local impact = nil :: any
local hitCount = 0
local lastHitReport = -math.huge

-- Anti-roll, part of the arcade hit response only (never the base car physics): from the touch until the hit window
-- (+ Arcade_AntiRollExtra) ends, the chassis keeps the up axis it had at the touch and only yaws. Two layers:
-- a client-side AlignOrientation (PrimaryAxisParallel, acts inside every physics substep) that is ENABLED ONLY in
-- that window, and a per-step projection in `step` (pitch/roll rate removed, the up axis put back if it drifted more
-- than Arcade_AntiRollSnapDeg). Round 6: side hits at 150 tilted the car to up 0.70-0.79.
local antiRoll = {chassis = nil :: BasePart?, att = nil :: Attachment?, align = nil :: AlignOrientation?,
	up0 = nil :: Vector3?, untilT = 0}

local function antiRollOff()
	antiRoll.up0, antiRoll.untilT = nil, 0
	if antiRoll.align then
		antiRoll.align.Enabled = false
	end
end

local function antiRollOn(chassis: BasePart, up0: Vector3, untilT: number, cfg)
	if antiRoll.chassis ~= chassis or not (antiRoll.align and antiRoll.align.Parent == chassis) then
		if antiRoll.align then antiRoll.align:Destroy() end
		if antiRoll.att then antiRoll.att:Destroy() end
		local att = Instance.new("Attachment")
		att.Name = "ArcadeAntiRollAtt"
		att.CFrame = CFrame.fromMatrix(Vector3.zero, Vector3.yAxis, Vector3.xAxis) -- primary (X) axis = chassis up
		att.Parent = chassis
		local align = Instance.new("AlignOrientation")
		align.Name = "ArcadeAntiRoll"
		align.Mode = Enum.OrientationAlignmentMode.OneAttachment
		align.AlignType = Enum.AlignType.PrimaryAxisParallel
		align.Attachment0 = att
		align.Enabled = false
		align.Parent = chassis
		antiRoll.chassis, antiRoll.att, antiRoll.align = chassis, att, align
	end
	local align = antiRoll.align :: AlignOrientation
	align.MaxTorque = cfg.Arcade_AntiRollTorque
	align.Responsiveness = cfg.Arcade_AntiRollResponse
	align.PrimaryAxis = up0
	align.Enabled = true
	antiRoll.up0, antiRoll.untilT = up0, untilT
end

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
-- recovery messages ("RECOVERED", "Stuck? Hold R to rescue", ...): its own label, shown with either HUD
local toast = Instance.new("TextLabel")
toast.Name = "RecoveryToast"
toast.AnchorPoint = Vector2.new(0.5, 0)
toast.Position = UDim2.new(0.5, 0, 0, 120)
toast.Size = UDim2.new(0.8, 0, 0, 30) -- fits a phone screen
toast.BackgroundTransparency = 1
toast.Font = Enum.Font.GothamBlack
toast.TextSize = 22
toast.TextColor3 = Color3.fromRGB(255, 230, 120)
toast.TextStrokeTransparency = 0.3
toast.Text = ""
toast.Visible = false
toast.Parent = gui
local toastUntil = 0
local function showToast(text: string, seconds: number?)
	toast.Text = text
	toast.Visible = true
	toastUntil = os.clock() + (seconds or 1.5)
end
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

-- flip in place: wheels down, heading kept (flattened), velocity zeroed. lift 6 = the legacy R.
local function flipInPlace(chassis: BasePart, lift: number)
	local look = chassis.CFrame.LookVector
	local flat = Vector3.new(look.X, 0, look.Z)
	if flat.Magnitude < 0.1 then flat = rec.lastGoodLook end
	local pos = chassis.Position + Vector3.new(0, lift, 0)
	chassis.AssemblyLinearVelocity = Vector3.zero
	chassis.AssemblyAngularVelocity = Vector3.zero
	chassis.CFrame = CFrame.lookAt(pos, pos + flat)
end

local function recoveryOn(): boolean
	return Recovery ~= nil and Recovery.enabled()
end

local function requestRescue(reason: string)
	if player:GetAttribute("CircuitActive") == true then
		showToast("On a circuit: press T to reset to the last gate", 2)
		return
	end
	local clock = os.clock()
	if clock - rec.lastRequestAt < 1 then
		return
	end
	rec.lastRequestAt = clock
	local remotes = game:GetService("ReplicatedStorage"):FindFirstChild("PattayaRemotes")
	local RequestRescue = remotes and remotes:FindFirstChild("RequestRescue")
	if RequestRescue then
		RequestRescue:FireServer(reason)
		showToast("Rescue requested...", 1.5)
	end
end

local overlapParams = OverlapParams.new()
overlapParams.FilterType = Enum.RaycastFilterType.Exclude
overlapParams.RespectCanCollide = true

-- manual R with the Recovery Kit rules: 2 s cooldown, only when tilted or slow, lift 3, and a blocked spot falls
-- through to the server rescue (R itself never moves the car along the road)
local function manualReset()
	local chassis = current.chassis
	if chassis.Anchored then
		return
	end
	local cfg = Recovery.config()
	local v = chassis.AssemblyLinearVelocity
	local speed = Vector3.new(v.X, 0, v.Z).Magnitude
	local ok, why = Recovery.resetAllowed(os.clock(), rec.lastResetAt, chassis.CFrame.UpVector.Y, speed, cfg)
	if not ok then
		if why == "cooldown" then
			showToast("R: wait a moment", 1)
		else
			showToast("R works when the car is tipped over or almost stopped", 1.5)
		end
		return
	end
	rec.lastResetAt = os.clock()
	local lift = cfg.Recovery_ResetLift
	local look = Vector3.new(chassis.CFrame.LookVector.X, 0, chassis.CFrame.LookVector.Z)
	if look.Magnitude < 0.1 then look = rec.lastGoodLook end
	local pos = chassis.Position + Vector3.new(0, lift, 0)
	local exclude = {current.seat.Parent, player.Character}
	local traffic = workspace:FindFirstChild("PattayaTraffic")
	if traffic then table.insert(exclude, traffic) end
	overlapParams.FilterDescendantsInstances = exclude
	local hits = workspace:GetPartBoundsInBox(CFrame.lookAt(pos, pos + look.Unit), chassis.Size, overlapParams)
	if #hits > 0 then
		requestRescue("blocked")
		return
	end
	flipInPlace(chassis, lift)
end

local function onReset(_, inputState)
	if not current then
		return Enum.ContextActionResult.Sink
	end
	if not recoveryOn() then
		if inputState == Enum.UserInputState.Begin then
			flipInPlace(current.chassis, 6) -- today's R
		end
		return Enum.ContextActionResult.Sink
	end
	if inputState == Enum.UserInputState.Begin then
		if rec.prompt then
			rec.holdStart = os.clock() -- hold to rescue; a short tap is still the R flip (on release)
		else
			manualReset()
		end
	elseif inputState == Enum.UserInputState.End or inputState == Enum.UserInputState.Cancel then
		if rec.holdStart then
			local held = os.clock() - rec.holdStart
			rec.holdStart = nil
			if held < Recovery.get("Recovery_RescueHold") and inputState == Enum.UserInputState.End then
				manualReset()
			end
		end
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
	local hitNow = os.clock()
	local hitWin = impact
	if hitWin and hitNow >= hitWin.untilT then
		impact, hitWin = nil, nil
	end
	if hitWin then
		steer *= hitWin.steer
	end
	state.spin += fs * dt / radius

	local grounded = 0
	local onRoad = false
	for name, mount in pairs(current.mounts) do
		local origin = mount.WorldPosition
		local hit = workspace:Raycast(origin, -up * reach, params)
		local ext = CONFIG.suspensionRest
		if hit then
			grounded += 1
			if Recovery and (Recovery.ROAD_NAMES[hit.Instance.Name] or hit.Material == Enum.Material.Asphalt) then
				onRoad = true
			end
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

		-- grip: kill sideways sliding (much less while the handbrake is on = drift; a heavy traffic hit slides too)
		local grip = (state.drift or (hitWin and hitWin.slide)) and tune.driftGrip or tune.grip
		impulse -= right * ls * mass * math.min(1, grip * dt)
		chassis:ApplyImpulse(impulse)

		-- steering: drive the yaw rate toward the target (scales in with speed, flips in reverse)
		local speedFactor = math.clamp(math.abs(fs) / 35, 0, 1)
		local dir = fs >= 0 and 1 or -1
		local target = -steer * tune.turnRate * speedFactor * dir * (state.drift and tune.driftTurnBoost or 1)
		local av = chassis.AssemblyAngularVelocity
		local yaw = av:Dot(up)
		local newYaw = yaw + (target - yaw) * math.min(1, 8 * dt)
		if hitWin and hitNow - hitWin.start < hitWin.spinT then
			-- scripted spin of a traffic hit: yaw rate w0 * (1 - t / T) adds up to the kick angle
			newYaw = hitWin.w0 * (1 - (hitNow - hitWin.start) / hitWin.spinT)
		end
		chassis.AssemblyAngularVelocity = av + up * (newYaw - yaw)
	else
		-- airborne: damp pitch/roll so jumps land wheels-down
		local av = chassis.AssemblyAngularVelocity
		local yawPart = up * av:Dot(up)
		chassis.AssemblyAngularVelocity = yawPart + (av - yawPart) * (1 - math.min(1, CONFIG.airUpright * dt))
	end

	if antiRoll.up0 then
		if hitNow >= antiRoll.untilT then
			antiRollOff()
		else
			-- traffic hits never roll the car: only the yaw about the up axis it had at the touch is kept
			local u0 = antiRoll.up0 :: Vector3
			local av = chassis.AssemblyAngularVelocity
			local ax, ay, az = Recovery.yawOnlyRate(av.X, av.Y, av.Z, u0.X, u0.Y, u0.Z)
			chassis.AssemblyAngularVelocity = Vector3.new(ax, ay, az)
			local cfNow = chassis.CFrame
			local u = cfNow.UpVector
			if Recovery.tiltFrom(u.X, u.Y, u.Z, u0.X, u0.Y, u0.Z) > Recovery.get("Arcade_AntiRollSnapDeg") then
				local l = cfNow.LookVector
				local lx, ly, lz = Recovery.yawOnlyLook(l.X, l.Y, l.Z, u0.X, u0.Y, u0.Z)
				if lx then
					local pos = cfNow.Position
					chassis.CFrame = CFrame.lookAt(pos, pos + Vector3.new(lx, ly :: number, lz :: number), u0)
				end
			end
		end
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
	state.onRoad = onRoad
end

-- Recovery Kit tick (after the physics step) ------------------------------------------------------------------
local function clearPrompt()
	if rec.prompt then
		rec.prompt = nil
		rec.holdStart = nil
		if toast.Text:find("R", 1, true) then
			toastUntil = 0
		end
	end
end

local function resetRecovery()
	rec.upright.upside, rec.upright.tilt = 0, 0
	rec.stuck.ax, rec.stuck.az, rec.stuck.t = nil, nil, 0
	rec.offRoad.t = 0
	rec.anim = nil
	clearPrompt()
end

local function startUpright(chassis: BasePart, cfg)
	local cf = chassis.CFrame
	local look = Vector3.new(cf.LookVector.X, 0, cf.LookVector.Z)
	local v = chassis.AssemblyLinearVelocity
	local flatVel = Vector3.new(v.X, 0, v.Z)
	if look.Magnitude < 0.3 then
		look = if flatVel.Magnitude > 5 then flatVel else rec.lastGoodLook
	end
	local target = cf.Position + Vector3.new(0, cfg.Recovery_UprightLift, 0)
	rec.anim = {from = cf, to = CFrame.lookAt(target, target + look.Unit), t = 0, dur = cfg.Recovery_UprightTime,
		keep = flatVel * cfg.Recovery_UprightKeepVel}
	rec.uprights += 1
	player:SetAttribute("Recovery_Uprights", rec.uprights)
	player:SetAttribute("Recovery_LastUprightAt", workspace:GetServerTimeNow())
end

-- the turn-over: true while it runs (the physics step is skipped for those frames)
local function animTick(chassis: BasePart, dt: number): boolean
	local a = rec.anim
	if not a then
		return false
	end
	if chassis.Anchored then
		rec.anim = nil
		return false
	end
	a.t += dt
	local k = math.min(a.t / math.max(a.dur, 0.05), 1)
	chassis.CFrame = a.from:Lerp(a.to, k)
	chassis.AssemblyAngularVelocity = Vector3.zero
	if k >= 1 then
		chassis.AssemblyLinearVelocity = a.keep
		rec.anim = nil
		showToast("RECOVERED", 1.2)
		return true
	end
	chassis.AssemblyLinearVelocity = Vector3.zero
	return true
end

local function recoveryTick(dt: number)
	local chassis = current.chassis
	if not recoveryOn() then
		resetRecovery()
		return
	end
	local cfg = Recovery.config()
	local cf = chassis.CFrame
	local upY = cf.UpVector.Y
	local v = chassis.AssemblyLinearVelocity
	local speed = Vector3.new(v.X, 0, v.Z).Magnitude
	if upY > 0.8 then
		local look = Vector3.new(cf.LookVector.X, 0, cf.LookVector.Z)
		if look.Magnitude > 0.1 then rec.lastGoodLook = look.Unit end
	end
	local held = chassis.Anchored or player:GetAttribute("RescueActive") == true
	local blocked = held or os.clock() - rec.enteredAt < cfg.Recovery_EnterGrace or rec.anim ~= nil
	if cfg.Recovery_AutoUpright and Recovery.uprightTick(rec.upright, upY, speed, dt, blocked, cfg) then
		startUpright(chassis, cfg)
		clearPrompt()
		return
	end
	if not cfg.Recovery_AntiStuck or held then
		rec.stuck.ax, rec.stuck.t = nil, 0
		rec.offRoad.t = 0
		clearPrompt()
		return
	end
	local pos = chassis.Position
	if Recovery.fallen(pos.Y, cfg) then
		requestRescue("fell")
		return
	end
	local throttleAbs = math.abs(current.seat.ThrottleFloat)
	local stuck = Recovery.stuckTick(rec.stuck, pos.X, pos.Z, throttleAbs, dt, cfg)
	local off = Recovery.offRoadTick(rec.offRoad, state.onRoad, speed, dt, cfg, throttleAbs)
	local why = if stuck then "stuck" elseif off then "offroad" else nil
	if why and not rec.prompt then
		rec.prompt = why
		rec.promptAt = os.clock()
	end
	if not rec.prompt then
		return
	end
	-- the prompt stays until the car drives off (or a rescue / upright clears it)
	if not why and speed > 8 then
		clearPrompt()
		return
	end
	local circuit = player:GetAttribute("CircuitActive") == true
	local text = if circuit then "Stuck? Press T to reset"
		elseif rec.holdStart then "Rescuing... keep holding R"
		else "Stuck? Hold R to rescue"
	showToast(text, 0.3)
	if rec.holdStart and os.clock() - rec.holdStart >= cfg.Recovery_RescueHold then
		rec.holdStart = nil
		requestRescue(rec.prompt)
	elseif cfg.Recovery_RescueAuto and not circuit
		and os.clock() - rec.promptAt >= cfg.Recovery_RescueAutoTime - cfg.Recovery_StuckTime then
		rec.promptAt = os.clock() + 30 -- one automatic try, then the prompt stays
		requestRescue("auto")
	end
end

-- Arcade traffic hits (Phase 2) ---------------------------------------------------------------------------------
-- PattayaTraffic fires PlayerScripts.CarImpact with {vc, approachDeg, facingDot, side, front, nx, nz, depth}. The
-- result comes from PattayaRecovery.classifyHit (owner numbers: light -20 %; heavy -45..-70 % with a 45-120 degree
-- spin and 0.6-1.2 s of weak steering; head-on -85 % and a small bounce). Heavy and head-on hits are reported to
-- the server (TrafficHit) for the jobs bump penalty.
local function reportHit(tier: string, vc: number, speedBefore: number)
	local clock = os.clock()
	if clock - lastHitReport < 1 then
		return
	end
	lastHitReport = clock
	local remotes = game:GetService("ReplicatedStorage"):FindFirstChild("PattayaRemotes")
	local TrafficHit = remotes and remotes:FindFirstChild("TrafficHit")
	if TrafficHit then
		TrafficHit:FireServer(tier, vc, speedBefore)
	end
end

-- a touch PattayaTraffic found but this script did not apply (diagnostic for TestKit: "touch not applied")
local function ignored(why: string)
	player:SetAttribute("Recovery_HitIgnored", why)
	player:SetAttribute("Recovery_HitIgnoredAt", workspace:GetServerTimeNow())
end

local function applyImpact(info)
	if type(info) ~= "table" or type(info.vc) ~= "number" or info.vc ~= info.vc then
		ignored("bad payload")
		return
	end
	if not (current and Recovery and Recovery.arcade()) then
		ignored(if not current then "not driving" else "arcade off")
		return
	end
	local chassis = current.chassis
	if chassis.Anchored or rec.anim then
		ignored(if chassis.Anchored then "car anchored" else "auto-upright running")
		return
	end
	local cfg = Recovery.config()
	local res = Recovery.classifyHit(info, cfg)
	local v = chassis.AssemblyLinearVelocity
	local before = Vector3.new(v.X, 0, v.Z).Magnitude
	local up0 = chassis.CFrame.UpVector -- the up axis at the touch (held by the anti-roll)
	local nx, nz = info.nx or 0, info.nz or 0
	local wx, wz = Recovery.impactVelocity(v.X, v.Z, nx, nz, res)
	chassis.AssemblyLinearVelocity = Vector3.new(wx, v.Y, wz)
	-- out of the traffic box along the contact normal (it ghosts now, so this is only so the cars don't overlap)
	local push = math.min((info.depth or 0) + 0.5, cfg.Arcade_MaxPush)
	if push > 0 then
		chassis.CFrame += Vector3.new(nx, 0, nz) * push
	end
	local now = os.clock()
	local window = 0
	if res.control > 0 or math.abs(res.yaw) > 0 then
		local spinT, w0 = Recovery.spinProfile(res.yaw, math.max(res.control, 0.25))
		window = math.max(res.control, spinT)
		impact = {start = now, untilT = now + window, steer = res.steer, slide = res.slide,
			spinT = spinT, w0 = w0}
	end
	if cfg.Arcade_AntiRoll then
		antiRollOn(chassis, up0, now + window + cfg.Arcade_AntiRollExtra, cfg)
	end
	hitCount += 1
	-- test telemetry (TK.hitTest): the numbers of THIS hit, all set before the count so a reader sees them together.
	-- Player speed, traffic speed and closing speed are separate fields (round 6 review).
	local after = math.sqrt(wx * wx + wz * wz)
	player:SetAttribute("Recovery_LastHitKey", info.key) -- the traffic car PattayaTraffic hit (its key)
	player:SetAttribute("Recovery_LastHitT", info.at)     -- the server time PattayaTraffic found the touch
	player:SetAttribute("Recovery_LastHitTier", res.tier)
	player:SetAttribute("Recovery_LastHitBefore", before) -- player (impact) speed, horizontal
	player:SetAttribute("Recovery_LastHitAfter", after)
	player:SetAttribute("Recovery_LastHitTrafficSpeed", info.trafficSpeed)
	player:SetAttribute("Recovery_LastHitVc", info.vc)     -- closing speed along the contact normal
	player:SetAttribute("Recovery_LastHitRel", info.rel)   -- relative speed |v_me - v_traffic|
	player:SetAttribute("Recovery_LastHitAngle", info.approachDeg)
	player:SetAttribute("Recovery_LastHitFacing", info.facingDot)
	player:SetAttribute("Recovery_LastHitN", Vector3.new(nx, 0, nz))
	player:SetAttribute("Recovery_LastHitYaw", res.yaw)
	player:SetAttribute("Recovery_LastHitControl", window)
	if type(info.tx) == "number" and type(info.tz) == "number" then
		player:SetAttribute("Recovery_LastHitPos", Vector3.new(info.tx, 0, info.tz))
	end
	player:SetAttribute("Recovery_HitCount", hitCount)
	player:SetAttribute("Recovery_LastHit", ("%s vc=%d %d->%d yaw=%d ctl=%.2f"):format(res.tier, math.floor(info.vc),
		math.floor(before), math.floor(math.sqrt(wx * wx + wz * wz)), math.floor(res.yaw), res.control))
	if res.tier == "heavy" or res.tier == "headon" then
		reportHit(res.tier, info.vc, before)
		showToast(if res.tier == "headon" then "HEAD-ON!" else "CRASH!", 0.8)
	end
end

do
	local ps = player:WaitForChild("PlayerScripts", 10)
	if ps then
		local ev = ps:FindFirstChild("CarImpact") or Instance.new("BindableEvent")
		ev.Name = "CarImpact"
		ev.Parent = ps
		;(ev :: BindableEvent).Event:Connect(applyImpact)
	end
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
	rec.enteredAt = os.clock()
	resetRecovery()
	impact = nil
	antiRollOff()
	pickTune()
	bindActions()
	gui.Enabled = true
end

local hudTelemetryReset -- forward (telemetry block below)

local function exit()
	current = nil
	impact = nil
	antiRollOff()
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

-- server rescue (PattayaRecoveryServer)
task.spawn(function()
	local remotes = game:GetService("ReplicatedStorage"):WaitForChild("PattayaRemotes", 60)
	if not remotes then
		return
	end
	local RescueUpdate = remotes:WaitForChild("RescueUpdate", 60)
	if not RescueUpdate then
		return
	end
	RescueUpdate.OnClientEvent:Connect(function(kind, info)
		if kind == "start" then
			resetRecovery()
			showToast("RESCUE", (type(info) == "table" and tonumber(info.eta) or 1) + 0.5)
		elseif kind == "done" then
			resetRecovery()
			local ghost = type(info) == "table" and tonumber(info.ghost) or 2
			-- PattayaTraffic ghosts the traffic around the car for these seconds (no drop into a traffic car)
			player:SetAttribute("TrafficGhostUntil", workspace:GetServerTimeNow() + ghost)
			showToast("BACK ON THE ROAD", 1.5)
		elseif kind == "denied" and type(info) == "string" then
			showToast(info, 2)
		end
	end)
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
	if toast.Visible and os.clock() > toastUntil then
		toast.Visible = false
	end
	if current and current.chassis.Parent then
		local sdt = math.min(dt, 1 / 30)
		if not animTick(current.chassis, sdt) then
			step(sdt)
			if Recovery then
				recoveryTick(sdt)
			end
		end
		tele.acc += dt
		if tele.acc >= TELEMETRY_DT then
			tele.acc = 0
			publishTelemetry()
		end
	end
end)
