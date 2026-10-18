-- MIDNIGHT PATTAYA speedometer (ui-race, docs/UI_RACE_HUD.md). Bottom-right cluster inside PlayerGui.MidnightHUD.BottomRight
-- (ui-core's root ScreenGui; its UIScale applies the HUD scale / touch shrink). Fallback: own ScreenGui after 10 s.
-- Draws only, from measured values (owner rule: nothing presented as engine data that the game does not simulate):
--   * SPEED arc = HUD_SpeedKmh / the car's nitro top speed (CarSpecs, the same numbers CarController drives with;
--     full arc = nitro top speed). The part of the arc above the normal top speed is the nitro zone (purple).
--   * big km/h digits (eased between the 20 Hz samples), "KM/H" caption, NITRO arc + percent (HUD_Nitro, cyan, pulses
--     while HUD_Boosting, red under 15 %), DRIFT tag (HUD_Drifting), class badge (HUD_Class) and car name / PI,
--     LIMITED tag while the event attributes SpeedCap / Equalised are set.
-- Visible only while in a car (HUD_InCar) AND LocalPlayer attribute MidnightHUD == true (set locally by ui-core; the
-- legacy CarHUD shows otherwise). Proportions follow docs/images/ui_mockup_owner.png at 1920 x 1080: the cluster is
-- 480 x 330 px at HUD scale 1, dial 340 px. GUI instances are built once; updates only change properties.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")
local uiFolder = ReplicatedStorage:WaitForChild("MidnightUI", 30)
if not uiFolder then
	return
end
local Theme = require(uiFolder:WaitForChild("Theme")) :: any
local C = Theme.color
local okSpecs, CarSpecs = pcall(function()
	return require(ReplicatedStorage:WaitForChild("CarSpecs", 10)) :: any
end)
if not okSpecs then
	CarSpecs = nil
end

local SPEED_SEGMENTS = 24 -- the maximum the brief allows; built once, reused
local NITRO_SEGMENTS = 12
local ARC_START, ARC_SWEEP = 135, 270 -- degrees, screen space (0 = right, clockwise): bottom-left round to bottom-right
local NITRO_START, NITRO_SWEEP = 215, -95 -- outer arc on the dial's left, filling from the bottom up
local NITRO_WARN = 15

local CLASS_COLOR = { -- class badge colours from Theme tokens (class names = CarSpecs.CLASSES)
	Street = C.cyan, Sport = C.green, Super = C.purple, Hyper = C.red, ["Track Spec"] = C.yellow,
}

local function reducedMotion(): boolean
	return player:GetAttribute("ReducedMotion") == true
end

local function corner(parent: Instance, radius: number?)
	local c = Instance.new("UICorner")
	c.CornerRadius = if radius then UDim.new(0, radius) else UDim.new(1, 0)
	c.Parent = parent
end

local function label(parent: Instance, props): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.AnchorPoint = props.anchor or Vector2.new(0.5, 0.5)
	t.Position = props.pos
	t.Size = props.size
	t.Font = props.font or Theme.font.bold
	t.TextColor3 = props.color or C.text
	t.Text = props.text or ""
	t.TextScaled = true
	t.TextXAlignment = props.alignX or Enum.TextXAlignment.Center
	-- navy outline keeps text readable on a sunlit road as well as at night
	t.TextStrokeColor3 = C.navy
	t.TextStrokeTransparency = props.stroke or 0.55
	t.ZIndex = props.z or 3
	t.Parent = parent
	return t
end

-- root ---------------------------------------------------------------------------------------------------------------
local hudRoot = playerGui:WaitForChild("MidnightHUD", 10)
local anchor = hudRoot and hudRoot:FindFirstChild("BottomRight")
if not anchor then
	-- ui-core's root is missing: own ScreenGui with its own scale (viewport height / 1080, x0.8 on touch) and 180 px
	-- clear of the touch thumbstick / jump zone, like the contract's BottomRight frame
	local g = Instance.new("ScreenGui")
	g.Name = "MidnightSpeedoHUD"
	g.ResetOnSpawn = false
	g.DisplayOrder = Theme.layer.hud
	local scale = Instance.new("UIScale")
	scale.Parent = g
	local touch = UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled
	local frame = Instance.new("Frame")
	frame.Name = "BottomRight"
	frame.BackgroundTransparency = 1
	frame.AnchorPoint = Vector2.new(1, 1)
	frame.Position = UDim2.new(1, -Theme.pad.xl, 1, if touch then -180 else -Theme.pad.xl)
	frame.Size = UDim2.fromOffset(480, 330)
	frame.Parent = g
	local function rescale()
		local cam = workspace.CurrentCamera
		local h = if cam then cam.ViewportSize.Y else 1080
		scale.Scale = math.clamp(h / 1080, 0.55, 1.3) * (if touch then 0.8 else 1) * (player:GetAttribute("HUDScale") or 1)
	end
	rescale()
	if workspace.CurrentCamera then
		workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(rescale)
	end
	player:GetAttributeChangedSignal("HUDScale"):Connect(rescale)
	g.Parent = playerGui
	anchor = frame
end

local panel = Instance.new("Frame")
panel.Name = "MidnightSpeedo"
panel.BackgroundTransparency = 1
panel.AnchorPoint = Vector2.new(1, 1)
panel.Position = UDim2.fromScale(1, 1)
panel.Size = UDim2.fromOffset(480, 330)
panel.Visible = false
panel.Parent = anchor

-- dial: 340 px circle at the cluster's bottom-right (mockup: ~345 px on a 1080p frame)
local dial = Instance.new("Frame")
dial.Name = "Dial"
dial.AnchorPoint = Vector2.new(1, 1)
dial.Position = UDim2.fromScale(1, 1)
dial.Size = UDim2.fromScale(340 / 480, 340 / 330)
dial.BackgroundColor3 = C.navy
dial.BackgroundTransparency = Theme.alpha.panel
dial.ZIndex = 1
dial.Parent = panel
corner(dial)
local ratio = Instance.new("UIAspectRatioConstraint")
ratio.AspectRatio = 1
ratio.Parent = dial
local dialStroke = Instance.new("UIStroke")
dialStroke.Color = C.line
dialStroke.Thickness = Theme.stroke.thick
dialStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
dialStroke.Parent = dial
-- inner accent ring (cyan -> purple, like the mockup's bezel)
local bezel = Instance.new("Frame")
bezel.AnchorPoint = Vector2.new(0.5, 0.5)
bezel.Position = UDim2.fromScale(0.5, 0.5)
bezel.Size = UDim2.fromScale(0.74, 0.74)
bezel.BackgroundTransparency = 1
bezel.ZIndex = 1
bezel.Parent = dial
corner(bezel)
local bezelStroke = Instance.new("UIStroke")
bezelStroke.Thickness = Theme.stroke.thin
bezelStroke.Color = C.text
bezelStroke.Transparency = 0.5
bezelStroke.Parent = bezel
local bezelGrad = Instance.new("UIGradient")
bezelGrad.Color = Theme.accentGradient()
bezelGrad.Rotation = 90
bezelGrad.Parent = bezelStroke

local function arcSegment(parent: Instance, angleDeg: number, radius: number, w: number, h: number): Frame
	local a = math.rad(angleDeg)
	local f = Instance.new("Frame")
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.Position = UDim2.fromScale(0.5 + radius * math.cos(a), 0.5 + radius * math.sin(a))
	f.Size = UDim2.fromScale(w, h)
	f.Rotation = angleDeg + 90 -- long side along the radius
	f.BorderSizePixel = 0
	f.BackgroundColor3 = C.line
	f.BackgroundTransparency = 0.35
	f.ZIndex = 2
	f.Parent = parent
	corner(f, 2)
	return f
end

local speedSegs = {}
for i = 1, SPEED_SEGMENTS do
	local ang = ARC_START + (i - 0.5) / SPEED_SEGMENTS * ARC_SWEEP
	speedSegs[i] = arcSegment(dial, ang, 0.43, 0.026, 0.085)
end

local speedText = label(dial, {pos = UDim2.fromScale(0.5, 0.47), size = UDim2.fromScale(0.6, 0.25),
	text = "0", font = Theme.font.display, stroke = 0.35})
label(dial, {pos = UDim2.fromScale(0.5, 0.63), size = UDim2.fromScale(0.26, 0.075),
	text = "KM/H", font = Theme.font.bold, color = C.text})
local carName = label(dial, {pos = UDim2.fromScale(0.5, 0.75), size = UDim2.fromScale(0.42, 0.05),
	text = "", font = Theme.font.bold, color = C.textDim, stroke = 0.8})
local piText = label(dial, {pos = UDim2.fromScale(0.5, 0.81), size = UDim2.fromScale(0.2, 0.04),
	text = "", font = Theme.font.mono, color = C.textMuted, stroke = 1})

-- class badge straddling the bottom of the dial (mockup: purple "SUPER" pill)
local badge = Instance.new("Frame")
badge.Name = "ClassBadge"
badge.AnchorPoint = Vector2.new(0.5, 0.5)
badge.Position = UDim2.fromScale(0.5, 0.92)
badge.Size = UDim2.fromScale(0.46, 0.085)
badge.BackgroundColor3 = C.surface
badge.BackgroundTransparency = 0.1
badge.ZIndex = 4
badge.Parent = dial
corner(badge, Theme.radius.small)
local badgeStroke = Instance.new("UIStroke")
badgeStroke.Thickness = Theme.stroke.thick
badgeStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
badgeStroke.Parent = badge
local badgeText = label(badge, {pos = UDim2.fromScale(0.5, 0.5), size = UDim2.fromScale(0.86, 0.78),
	text = "", font = Theme.font.display, stroke = 0.6, z = 5})

-- nitro: outer arc hugging the dial's left side, percent + caption inside that crescent (mockup "72% NITRO")
local nitroSegs = {}
for i = 1, NITRO_SEGMENTS do
	local ang = NITRO_START + (i - 0.5) / NITRO_SEGMENTS * NITRO_SWEEP
	nitroSegs[i] = arcSegment(dial, ang, 0.6, 0.034, 0.075)
end
local nitroPct = label(panel, {anchor = Vector2.new(0.5, 0.5), pos = UDim2.fromScale(0.1, 0.62),
	size = UDim2.fromScale(0.15, 0.1), text = "0%", font = Theme.font.display, color = C.text, stroke = 0.4})
local nitroCaption = label(panel, {anchor = Vector2.new(0.5, 0.5), pos = UDim2.fromScale(0.1, 0.72),
	size = UDim2.fromScale(0.11, 0.055), text = "NITRO", font = Theme.font.bold, color = C.text})
local driftTag = label(panel, {anchor = Vector2.new(0.5, 0.5), pos = UDim2.fromScale(0.1, 0.8),
	size = UDim2.fromScale(0.1, 0.05), text = "DRIFT", font = Theme.font.bold, color = C.purple})
driftTag.Visible = false
local limited = Instance.new("Frame")
limited.Name = "Limited"
limited.AnchorPoint = Vector2.new(0.5, 0.5)
limited.Position = UDim2.fromScale(0.12, 0.42)
limited.Size = UDim2.fromScale(0.2, 0.07)
limited.BackgroundColor3 = C.red
limited.BackgroundTransparency = 0.15
limited.Visible = false
limited.ZIndex = 3
limited.Parent = panel
corner(limited, Theme.radius.small)
local limitedText = label(limited, {pos = UDim2.fromScale(0.5, 0.5), size = UDim2.fromScale(0.9, 0.72), text = "LIMITED",
	font = Theme.font.bold, stroke = 1, z = 4})

-- compact / touch variant (docs/UI_SYSTEM.md "Touch layout"): MidnightHUD sets attribute Compact on its ScreenGui
-- and sizes BottomRight to 242 x 113 (design px, about 150 x 70 on an 830 x 439 phone). No dial: big digits, KM/H,
-- nitro percent and a nitro bar; "LIMITED" replaces KM/H while a speed cap / equalised event is on.
local function isCompact(): boolean
	return hudRoot ~= nil and hudRoot:GetAttribute("Compact") == true
end
local mini = Instance.new("Frame")
mini.Name = "MidnightSpeedoCompact"
mini.Size = UDim2.fromOffset(242, 113)
mini.BackgroundColor3 = C.navy
mini.BackgroundTransparency = Theme.alpha.panel
mini.BorderSizePixel = 0
mini.Visible = false
mini.Parent = anchor
corner(mini, Theme.radius.panel)
local miniStroke = Instance.new("UIStroke")
miniStroke.Color = C.line
miniStroke.Thickness = Theme.stroke.thin
miniStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
miniStroke.Parent = mini
local miniSpeed = label(mini, {anchor = Vector2.new(0, 0), pos = UDim2.fromOffset(8, 6), size = UDim2.fromOffset(142, 74),
	text = "0", font = Theme.font.display, alignX = Enum.TextXAlignment.Right, stroke = 0.6})
local miniUnit = label(mini, {anchor = Vector2.new(0, 0), pos = UDim2.fromOffset(158, 52), size = UDim2.fromOffset(76, 22),
	text = "KM/H", font = Theme.font.bold, color = C.textDim, alignX = Enum.TextXAlignment.Left, stroke = 1})
local miniNitro = label(mini, {anchor = Vector2.new(0, 0), pos = UDim2.fromOffset(158, 12), size = UDim2.fromOffset(76, 32),
	text = "0%", font = Theme.font.display, color = C.cyan, alignX = Enum.TextXAlignment.Left, stroke = 1})
local miniTrack = Instance.new("Frame")
miniTrack.Name = "NitroBar"
miniTrack.Position = UDim2.fromOffset(10, 88)
miniTrack.Size = UDim2.fromOffset(222, 14)
miniTrack.BackgroundColor3 = C.surface2
miniTrack.BackgroundTransparency = 0.2
miniTrack.BorderSizePixel = 0
miniTrack.ZIndex = 3
miniTrack.Parent = mini
corner(miniTrack, Theme.radius.small)
local miniFill = Instance.new("Frame")
miniFill.Size = UDim2.fromScale(0, 1)
miniFill.BackgroundColor3 = C.cyan
miniFill.BorderSizePixel = 0
miniFill.ZIndex = 4
miniFill.Parent = miniTrack
corner(miniFill, Theme.radius.small)

-- nitro pulse, built once: the dial ring glows cyan while boosting
local pulse = TweenService:Create(dialStroke, TweenInfo.new(0.35, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true),
	{Thickness = Theme.stroke.thick * 3})

-- state ------------------------------------------------------------------------------------------------------------
local topSpeed, normalTop = 215, 160 -- the driven car's nitro / normal top speed (studs/s); refreshed on entry
local speedTarget, speedShown, speedShownInt, speedLit = 0, 0, -1, -1
local nitroLit, nitroWarn = -1, nil

local function visibleNow(): boolean
	return player:GetAttribute("MidnightHUD") == true and player:GetAttribute("HUD_InCar") == true
end

-- same choice as CarController.pickTune: Equalised events drive the starter's numbers, else the model's CarId +
-- upgrades; unknown -> CarSpecs.BASE / CarController's CONFIG (160 / 215)
local function readTopSpeed()
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	local model = seat and seat.Parent
	local s = nil
	if CarSpecs and model then
		if player:GetAttribute("Equalised") == true then
			s = CarSpecs.Equalised()
		elseif model:GetAttribute("CarId") and CarSpecs.Cars[model:GetAttribute("CarId")] then
			s = CarSpecs.ForModel(model)
		end
	end
	topSpeed = if s then s.nitroSpeed else 215
	normalTop = if s then s.maxSpeed else 160
	speedLit, speedShownInt = -1, -1 -- repaint the arc on the next frame
end

local function paintSpeedArc(lit: number)
	local nitroFrom = normalTop / math.max(topSpeed, 1)
	for i, seg in speedSegs do
		local frac = i / SPEED_SEGMENTS
		local inNitro = frac > nitroFrom + 0.001
		if i <= lit then
			seg.BackgroundColor3 = if inNitro then C.purple else C.cyan
			seg.BackgroundTransparency = 0
		else
			seg.BackgroundColor3 = if inNitro then C.purple else C.line
			seg.BackgroundTransparency = if inNitro then 0.7 else 0.35
		end
	end
end

local function paintNitro()
	local pct = player:GetAttribute("HUD_Nitro") or 0
	local lit = math.clamp(math.ceil(pct / 100 * NITRO_SEGMENTS - 0.001), 0, NITRO_SEGMENTS)
	local warn = pct < NITRO_WARN
	nitroPct.Text = ("%d%%"):format(pct)
	if lit ~= nitroLit or warn ~= nitroWarn then
		nitroLit, nitroWarn = lit, warn
		local on = if warn then C.red else C.cyan
		for i, seg in nitroSegs do
			seg.BackgroundColor3 = if i <= lit then on else C.line
			seg.BackgroundTransparency = if i <= lit then 0 else 0.45
		end
		nitroPct.TextColor3 = if warn then C.red else C.text
		miniFill.BackgroundColor3 = if warn then C.red else C.cyan
		miniNitro.TextColor3 = if warn then C.red else C.cyan
	end
	miniNitro.Text = nitroPct.Text
	miniFill.Size = UDim2.fromScale(math.clamp(pct / 100, 0, 1), 1)
end

local function paintBoost()
	local boosting = player:GetAttribute("HUD_Boosting") == true
	if boosting then
		dialStroke.Color = C.cyan
		if reducedMotion() then
			dialStroke.Thickness = Theme.stroke.thick * 2
		else
			pulse:Play()
		end
	else
		pulse:Cancel()
		dialStroke.Color = C.line
		dialStroke.Thickness = Theme.stroke.thick
	end
	nitroCaption.TextColor3 = if boosting then C.cyan else C.text
end

local function paintCar()
	local class = player:GetAttribute("HUD_Class") or ""
	local col = CLASS_COLOR[class] or C.textDim
	badgeText.Text = string.upper(class)
	badgeText.TextColor3 = C.text
	badgeStroke.Color = col
	badge.BackgroundColor3 = col
	badge.BackgroundTransparency = 0.55
	badge.Visible = class ~= ""
	carName.Text = string.upper(player:GetAttribute("HUD_CarName") or "")
	local pi = player:GetAttribute("HUD_PI") or 0
	piText.Text = if pi > 0 then ("PI %d"):format(pi) else ""
end

local function paintLimited()
	local cap = player:GetAttribute("SpeedCap")
	local capped = type(cap) == "number" and cap > 0
	local eq = player:GetAttribute("Equalised") == true
	limited.Visible = capped or eq
	limitedText.Text = if capped then ("LIMITED %d"):format(cap) elseif eq then "EQUALISED" else "LIMITED"
	miniUnit.Text = if capped or eq then "LIMITED" else "KM/H"
	miniUnit.TextColor3 = if capped or eq then C.red else C.textDim
end

local function refreshVisible()
	local on = visibleNow()
	if on and not (panel.Visible or mini.Visible) then
		readTopSpeed()
		-- snap on entry: no sweep from the last car's numbers
		speedTarget = player:GetAttribute("HUD_SpeedKmh") or 0
		speedShown = speedTarget
		speedShownInt = -1
	end
	local small = isCompact()
	panel.Visible = on and not small
	mini.Visible = on and small
end

-- wiring -----------------------------------------------------------------------------------------------------------
local function onAttr(name: string, fn: () -> ())
	player:GetAttributeChangedSignal(name):Connect(fn)
end
onAttr("HUD_InCar", refreshVisible)
onAttr("MidnightHUD", refreshVisible)
if hudRoot then
	hudRoot:GetAttributeChangedSignal("Compact"):Connect(refreshVisible)
end
onAttr("HUD_SpeedKmh", function()
	speedTarget = player:GetAttribute("HUD_SpeedKmh") or 0
end)
onAttr("HUD_Nitro", paintNitro)
onAttr("HUD_Boosting", paintBoost)
onAttr("HUD_Drifting", function()
	driftTag.Visible = player:GetAttribute("HUD_Drifting") == true
end)
for _, n in {"HUD_Class", "HUD_CarName", "HUD_PI"} do
	onAttr(n, function()
		paintCar()
		if panel.Visible or mini.Visible then readTopSpeed() end -- car swapped while seated (garage spawn)
	end)
end
onAttr("SpeedCap", paintLimited)
onAttr("Equalised", function()
	paintLimited()
	if panel.Visible or mini.Visible then readTopSpeed() end
end)

refreshVisible()
paintSpeedArc(0)
paintNitro()
paintBoost()
paintCar()
paintLimited()

-- easing between the 20 Hz samples: only while the shown value is off its target; the digits and the arc change only
-- when their rounded values do (no allocation per frame)
RunService.RenderStepped:Connect(function(dt)
	if not (panel.Visible or mini.Visible) then
		return
	end
	if math.abs(speedTarget - speedShown) > 0.05 or speedShownInt < 0 then
		local k = if reducedMotion() then 1 else math.min(1, dt * 14)
		speedShown += (speedTarget - speedShown) * k
		local n = math.floor(speedShown + 0.5)
		if n ~= speedShownInt then
			speedShownInt = n
			speedText.Text = tostring(n)
			miniSpeed.Text = speedText.Text
		end
		local lit = math.clamp(math.floor(speedShown / math.max(topSpeed, 1) * SPEED_SEGMENTS + 0.5), 0, SPEED_SEGMENTS)
		if lit ~= speedLit then
			speedLit = lit
			paintSpeedArc(lit)
		end
	end
end)
