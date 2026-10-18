--!strict
-- MidnightCamera (VIS-5): chase camera for the player's own car. Client-only, nothing replicated or saved.
-- WRITTEN, NOT RUN IN STUDIO YET.
--
-- Active only while ALL of these hold:
--   * the local Humanoid sits in a VehicleSeat whose car model has attribute RaceCar (the CarController rule);
--   * the camera's CameraSubject is that Humanoid or the seat (the default while seated). Anything else - e.g. the
--     circuit spectator (CircuitRaceClient sets CameraSubject to another car's chassis) - makes this script step aside
--     and hand the camera back to Roblox until the subject is the player again;
--   * neither Lighting nor LocalPlayer has attribute MidnightCamera == false (live switch; false = Roblox's default
--     vehicle camera, exactly as before this script existed).
-- While active the camera is Scriptable and moved in a RenderStep bound after Roblox's camera
-- (RenderPriority.Camera + 1). When it steps aside it restores CameraType Custom and the FieldOfView it found;
-- CameraSubject is never changed by this script.
--
-- Behaviour: the camera sits behind and above the car on a smoothed heading (a blend of the car's nose and its
-- velocity direction, so drifts show the car's side), the camera orbits the car on that smoothed angle (car-relative,
-- not a lagging world position, so it never falls behind at speed and the road ahead stays in view; look-back swings
-- around the car), distance/height follow the speed smoothly, the car's height is smoothed separately
-- (kerbs and bumps do not jolt the view), the camera never rolls, and there is no shake and no motion blur. Distance,
-- look-ahead and FOV grow with speed (FOV 70 -> 85 at the car's nitro top speed). A raycast pulls the camera in front
-- of walls/buildings between the car and the camera.
-- Look around: hold Q (gamepad: press the right stick, R3) = look back; right mouse drag or the gamepad right stick =
-- look left/right up to OrbitMax degrees, springing back when released. (No existing script binds Q, R3, the right
-- stick or right-mouse drag; E is used by prompts, so it is not used here.)
--
-- Tuning knobs: every value in KNOBS can be overridden live by a number attribute "MC_<Name>" on LocalPlayer or on
-- Lighting (LocalPlayer wins), e.g. game.Lighting:SetAttribute("MC_FovMax", 80). See docs/VISUAL_ART_DIRECTION.md.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local ContextActionService = game:GetService("ContextActionService")
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer

local KNOBS: {[string]: number} = {
	Distance = 17, -- studs from the car's centre to the camera (horizontal) at rest
	DistanceAtTop = 21, -- ... at top speed
	Height = 6.0, -- camera height above the car's (smoothed) centre
	HeightAtTop = 5.2, -- slightly lower at speed (more road, more sense of speed)
	LookHeight = 2.6, -- aim point above the car's centre
	LookAhead = 10, -- aim point ahead of the car at rest (studs)
	LookAheadAtTop = 28, -- ... at top speed: keeps the road ahead in the frame
	FovBase = 70, -- degrees at and below FovStartSpeed
	FovMax = 85, -- degrees at the car's nitro top speed
	FovStartSpeed = 40, -- studs/s
	TopSpeed = 0, -- studs/s used for the speed scaling; 0 = the car's own nitro top speed (CarSpecs), else 215
	DistanceDamping = 3, -- 1/s: distance / height follow the speed smoothly
	YawDamping = 5, -- 1/s: how fast the heading follows the car at rest ...
	YawDampingAtTop = 9, -- ... and at top speed
	HeightDamping = 10, -- 1/s: smoothing of the car's height (kerbs, bumps)
	FovDamping = 3, -- 1/s
	VelocityBlend = 0.35, -- 0 = heading follows the car's nose only, 1 = the velocity direction only
	OrbitMax = 50, -- degrees of look left/right
	OrbitReturn = 4, -- 1/s spring back after the mouse / stick is released
	LookBackDamping = 12, -- 1/s turn into / out of look-back
	CollisionPad = 1.0, -- studs kept between the camera and a wall it was pulled in front of
	MinDistance = 6, -- studs: closest the wall pull-in may bring the camera
	CollisionRelease = 4, -- 1/s: how fast the camera moves back out after a wall
	ThinObstacle = 4, -- studs: parts thinner than this (poles, palms, signs) never pull the camera in
	IntroTime = 0.4, -- s: glide from Roblox's camera into the chase camera
}

local function knob(name: string): number
	local v = player:GetAttribute("MC_" .. name)
	if type(v) ~= "number" then
		v = Lighting:GetAttribute("MC_" .. name)
	end
	return if type(v) == "number" then v else KNOBS[name]
end

local function enabled(): boolean
	return Lighting:GetAttribute("MidnightCamera") ~= false and player:GetAttribute("MidnightCamera") ~= false
end

local okSpecs, CarSpecs = pcall(function()
	return require(ReplicatedStorage:WaitForChild("CarSpecs", 10) :: ModuleScript) :: any
end)
if not okSpecs then
	CarSpecs = nil
end

local okUI, Responsive = pcall(function()
	local ui = ReplicatedStorage:WaitForChild("MidnightUI", 5)
	return require((ui :: Instance):WaitForChild("Responsive", 5) :: ModuleScript) :: any
end)
if not okUI then
	Responsive = nil
end
local function reducedMotion(): boolean
	if Responsive and type(Responsive.reducedMotion) == "function" then
		local ok, v = pcall(Responsive.reducedMotion)
		return ok and v == true
	end
	return player:GetAttribute("ReducedMotion") == true
end

-- state --------------------------------------------------------------------------------------------------------------
type Car = {seat: VehicleSeat, model: Model, chassis: BasePart, top: number}
local active = false
local car: Car? = nil
local saved = {fov = 70, mouse = Enum.MouseBehavior.Default, mouseChanged = false}
local yaw = 0 -- smoothed heading (radians, world)
local dist, height = 17, 6 -- smoothed distance / height
local coll = math.huge -- smoothed wall pull-in distance
local intro, introFrom = 1, CFrame.new()
local carY = 0 -- smoothed car height
local fov = 70
local orbit, orbitTarget = 0, 0 -- radians (mouse / stick)
local back = 0 -- 0..1 look-back blend
local lookBackHeld = false
local rightMouse = false
local stickX = 0
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude

local function seatedCar(): Car?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if not (seat and seat:IsA("VehicleSeat")) then
		return nil
	end
	local model = seat.Parent
	if not (model and model:IsA("Model") and model:GetAttribute("RaceCar")) then
		return nil
	end
	local chassis = model:FindFirstChild("Chassis") or model.PrimaryPart
	if not (chassis and chassis:IsA("BasePart")) then
		return nil
	end
	return {seat = seat :: VehicleSeat, model = model, chassis = chassis, top = 215}
end

local function subjectIsMine(cam: Camera, c: Car): boolean
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local s = cam.CameraSubject
	return s == nil or s == hum or s == c.seat or s == c.chassis
end

local function flatYaw(v: Vector3): number
	return math.atan2(-v.X, -v.Z) -- yaw of a direction (0 = looking down -Z, like CFrame.Angles(0, yaw, 0))
end

local function yawDir(a: number): Vector3
	return Vector3.new(-math.sin(a), 0, -math.cos(a))
end

local function angleLerp(a: number, b: number, t: number): number
	local d = (b - a + math.pi) % (2 * math.pi) - math.pi
	return a + d * t
end

-- input: look back / orbit ------------------------------------------------------------------------------------------
local function onLookBack(_: string, state: Enum.UserInputState): Enum.ContextActionResult
	lookBackHeld = state == Enum.UserInputState.Begin
	return Enum.ContextActionResult.Pass -- never swallow the key from other scripts
end

local connections: {RBXScriptConnection} = {}
local function bindInput()
	ContextActionService:BindAction("MidnightCameraLookBack", onLookBack, false, Enum.KeyCode.Q, Enum.KeyCode.ButtonR3)
	table.insert(connections, UserInputService.InputBegan:Connect(function(input, processed)
		if input.UserInputType == Enum.UserInputType.MouseButton2 and not processed then
			rightMouse = true
			if not saved.mouseChanged then
				saved.mouse = UserInputService.MouseBehavior
				saved.mouseChanged = true
			end
			UserInputService.MouseBehavior = Enum.MouseBehavior.LockCurrentPosition
		end
	end))
	table.insert(connections, UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton2 then
			rightMouse = false
			if saved.mouseChanged then
				UserInputService.MouseBehavior = saved.mouse
				saved.mouseChanged = false
			end
		end
	end))
	table.insert(connections, UserInputService.InputChanged:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseMovement and rightMouse then
			local m = math.rad(knob("OrbitMax"))
			orbitTarget = math.clamp(orbitTarget - input.Delta.X * 0.006, -m, m)
		elseif input.KeyCode == Enum.KeyCode.Thumbstick2 then
			stickX = if math.abs(input.Position.X) > 0.2 then input.Position.X else 0
		end
	end))
end

local function unbindInput()
	ContextActionService:UnbindAction("MidnightCameraLookBack")
	for _, c in connections do
		c:Disconnect()
	end
	table.clear(connections)
	lookBackHeld, rightMouse, stickX = false, false, 0
	if saved.mouseChanged then
		UserInputService.MouseBehavior = saved.mouse
		saved.mouseChanged = false
	end
end

-- per frame -----------------------------------------------------------------------------------------------------------
local function update(dt: number)
	local cam = workspace.CurrentCamera
	local c = car
	if not (cam and c and c.chassis.Parent) then
		return
	end
	dt = math.min(dt, 0.1)
	local cf = c.chassis.CFrame
	local pos = cf.Position
	local vel = c.chassis.AssemblyLinearVelocity
	local flatVel = Vector3.new(vel.X, 0, vel.Z)
	local look = Vector3.new(cf.LookVector.X, 0, cf.LookVector.Z)
	if look.Magnitude < 0.05 then
		look = yawDir(yaw)
	end
	look = look.Unit
	local fwdSpeed = flatVel:Dot(look)
	local speed = flatVel.Magnitude
	local topKnob = knob("TopSpeed")
	local top = if topKnob > 0 then topKnob else c.top
	local startS = knob("FovStartSpeed")
	local s = math.clamp((speed - startS) / math.max(top - startS, 1), 0, 1)

	-- heading: the car's nose, blended toward the velocity direction when moving forward
	local dir = look
	if fwdSpeed > 8 then
		local vb = knob("VelocityBlend")
		local blended = look * (1 - vb) + flatVel.Unit * vb
		if blended.Magnitude > 0.05 then
			dir = blended.Unit
		end
	end
	local yawRate = knob("YawDamping") + (knob("YawDampingAtTop") - knob("YawDamping")) * s
	yaw = angleLerp(yaw, flatYaw(dir), 1 - math.exp(-yawRate * dt))

	-- look around
	local m = math.rad(knob("OrbitMax"))
	if stickX ~= 0 then
		orbitTarget = -stickX * m
	elseif not rightMouse then
		orbitTarget *= math.exp(-knob("OrbitReturn") * dt)
	end
	orbit += (orbitTarget - orbit) * (1 - math.exp(-12 * dt))
	back += ((if lookBackHeld then 1 else 0) - back) * (1 - math.exp(-knob("LookBackDamping") * dt))
	local viewYaw = yaw + orbit + math.pi * back

	-- the camera orbits the car on the smoothed angle (car-relative, so speed never drags it back and look-back
	-- swings around the car instead of through it); distance / height / car height are smoothed scalars
	local dRate = 1 - math.exp(-knob("DistanceDamping") * dt)
	dist += (knob("Distance") + (knob("DistanceAtTop") - knob("Distance")) * s - dist) * dRate
	height += (knob("Height") + (knob("HeightAtTop") - knob("Height")) * s - height) * dRate
	carY += (pos.Y - carY) * (1 - math.exp(-knob("HeightDamping") * dt))
	local base = Vector3.new(pos.X, carY, pos.Z)
	local ahead = knob("LookAhead") + (knob("LookAheadAtTop") - knob("LookAhead")) * s
	local aimDir = yawDir(viewYaw)
	local aim = base + aimDir * ahead * (1 - back) + Vector3.new(0, knob("LookHeight"), 0)
	local camPos = base - aimDir * dist + Vector3.new(0, height, 0)

	-- keep the camera in front of walls between the car and the camera; thin parts (poles, palms, sign posts) are
	-- skipped so they never make the view jump. In instantly, out slowly.
	local exclude: {Instance} = {c.model}
	if player.Character then
		table.insert(exclude, player.Character :: Model)
	end
	local from = base + Vector3.new(0, knob("LookHeight"), 0)
	local want = (camPos - from).Magnitude
	local free = want
	for _ = 1, 4 do
		rayParams.FilterDescendantsInstances = exclude
		local hit = workspace:Raycast(from, camPos - from, rayParams)
		if not hit then
			break
		end
		local part = hit.Instance
		local sz = part.Size
		if part:IsA("BasePart") and (math.min(sz.X, sz.Z) < knob("ThinObstacle") or (part.Transparency >= 0.95
			and part.Name ~= "VisHull")) then
			table.insert(exclude, part) -- thin or invisible (VisHull stands for a building, so it counts)
		else
			free = math.max((hit.Position - from).Magnitude - knob("CollisionPad"), knob("MinDistance"))
			break
		end
	end
	if free < coll then
		coll = free
	else
		coll += (free - coll) * (1 - math.exp(-knob("CollisionRelease") * dt))
	end
	if coll < want then
		camPos = from + (camPos - from).Unit * coll
	end

	-- FOV by speed (none with Reduce Motion)
	local fovTarget = knob("FovBase")
	if not reducedMotion() then
		fovTarget += (knob("FovMax") - knob("FovBase")) * s
	end
	fov += (fovTarget - fov) * (1 - math.exp(-knob("FovDamping") * dt))
	cam.FieldOfView = fov
	local goal = CFrame.lookAt(camPos, aim)
	if intro < 1 then
		intro = math.min(1, intro + dt / math.max(knob("IntroTime"), 0.01))
		local t = intro * intro * (3 - 2 * intro)
		goal = introFrom:Lerp(goal, t)
	end
	cam.CFrame = goal
	cam.Focus = CFrame.new(aim)
end

-- activation -----------------------------------------------------------------------------------------------------------
local RENDER_NAME = "MidnightCamera"

local function activate(c: Car)
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	if CarSpecs and type(CarSpecs.ForModel) == "function" then -- the car's nitro top speed, once per entry
		local ok, spec = pcall(CarSpecs.ForModel, c.model)
		if ok and type(spec) == "table" and type(spec.nitroSpeed) == "number" then
			c.top = spec.nitroSpeed
		end
	end
	car = c
	active = true
	saved.fov = cam.FieldOfView
	fov = cam.FieldOfView
	local cf = c.chassis.CFrame
	carY = cf.Position.Y
	yaw = flatYaw(Vector3.new(cf.LookVector.X, 0, cf.LookVector.Z))
	-- start from where Roblox's camera is now, so the switch is a smooth glide instead of a cut
	introFrom, intro = cam.CFrame, 0
	dist, height, coll = knob("Distance"), knob("Height"), math.huge
	orbit, orbitTarget, back = 0, 0, 0
	cam.CameraType = Enum.CameraType.Scriptable
	bindInput()
	RunService:BindToRenderStep(RENDER_NAME, Enum.RenderPriority.Camera.Value + 1, update)
end

local function deactivate()
	if not active then
		return
	end
	active = false
	car = nil
	RunService:UnbindFromRenderStep(RENDER_NAME)
	unbindInput()
	local cam = workspace.CurrentCamera
	if cam then
		if cam.CameraType == Enum.CameraType.Scriptable then
			cam.CameraType = Enum.CameraType.Custom -- Roblox's own camera takes over again (vehicle camera while seated)
		end
		cam.FieldOfView = saved.fov
	end
end

-- cheap watcher: decides every frame whether the chase camera should run
RunService.Heartbeat:Connect(function()
	local cam = workspace.CurrentCamera
	local c = if enabled() and cam then seatedCar() else nil
	if c and cam and not subjectIsMine(cam, c) then
		c = nil -- spectating someone else (or another script owns the subject): step aside
	end
	if c then
		if not active then
			activate(c)
		elseif car and (car :: Car).seat ~= c.seat then
			deactivate()
			activate(c)
		end
	elseif active then
		deactivate()
	end
end)

player.CharacterRemoving:Connect(deactivate)

-- debug from the client command bar: _G.MidnightCamera.state()
_G.MidnightCamera = {
	state = function()
		return {active = active, fov = fov, yaw = math.deg(yaw), orbit = math.deg(orbit), back = back,
			car = if car then (car :: Car).model.Name else nil}
	end,
	knobs = KNOBS,
}
