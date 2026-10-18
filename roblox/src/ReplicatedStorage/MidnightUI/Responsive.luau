-- MIDNIGHT PATTAYA HUD responsiveness (ReplicatedStorage.MidnightUI.Responsive, ui-core). Client only.
--   Responsive.attach(screenGui)    UIScale in every anchor frame (TopLeft ... Toasts), safe-area insets on the gui
--   Responsive.addScale(guiObject)  one more UIScale kept in step (e.g. a modal card)
--   Responsive.scale()              effective scale = viewport scale x the player's HUD scale
--   Responsive.hudScale()           the player's setting: attribute LocalPlayer.HUDScale, 0.7-1.4, default 1
--   Responsive.isTouch() / isGamepad() / inputKind()  "keyboard" | "gamepad" | "touch"
--   Responsive.safeInsets(gui?)     extra {top, left, bottom, right} px a gui with IgnoreGuiInset must keep clear
--   Responsive.reducedMotion()      attribute LocalPlayer.ReducedMotion, else Roblox's own Reduce Motion setting
--   Responsive.isCompact()          small-screen / touch layout: touch input OR viewport width < COMPACT_WIDTH
--                                   (docs/UI_SYSTEM.md "Touch layout"); MidnightHUD mirrors it as gui attribute Compact
--   Responsive.onChange(fn)         fn(reason) with reason "scale" | "input" | "motion" | "viewport" (any size change)
-- Bus: fires "hud.scale" (effective scale, number) and "hud.reducedMotion" (bool) when they change.
-- Viewport scale: the HUD is laid out for a 1600x900 reference; scale = min(w/1600, h/900) clamped to 0.5-1.3
-- (touch devices never go below 0.62 so 76 px menu buttons stay >= 44 px). 1920x1080 -> 1.2, 1366x768 -> 0.85.
local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")

local Bus = require(script.Parent.Bus)

local Responsive = {}

Responsive.REFERENCE = Vector2.new(1600, 900)
Responsive.MIN_SCALE = 0.5
Responsive.MAX_SCALE = 1.3
Responsive.TOUCH_MIN_SCALE = 0.62
Responsive.HUD_SCALE_MIN = 0.7
Responsive.HUD_SCALE_MAX = 1.4
Responsive.COMPACT_WIDTH = 1100 -- viewport px: below this (or on touch) the compact layout is used
Responsive.TOUCH_RESERVE = 180 -- px (screen space) kept clear right of BottomRight for the jump button / touch zone
Responsive.ANCHORS = {"TopLeft", "TopCenter", "TopRight", "BottomLeft", "BottomCenter", "BottomRight", "Toasts"}

local player = Players.LocalPlayer
local scales: {UIScale} = {}
local callbacks: {(string) -> ()} = {}
local current = 1
local kind = "keyboard"
local motionReduced = false
local started = false
local start: () -> () -- defined below; every public getter calls it so the module works without attach()

local function notify(reason: string)
	for _, fn in callbacks do
		task.spawn(fn, reason)
	end
end

local GAMEPADS = {}
for i = 1, 8 do
	GAMEPADS[(Enum.UserInputType :: any)["Gamepad" .. i]] = true
end

local function preferredInput(): string?
	local ok, v = pcall(function()
		return (UserInputService :: any).PreferredInput
	end)
	if ok and typeof(v) == "EnumItem" then
		return v.Name
	end
	return nil
end

local function computeKind(): string
	local pref = preferredInput()
	if pref == "Touch" then
		return "touch"
	elseif pref == "Gamepad" then
		return "gamepad"
	elseif pref ~= nil then
		return "keyboard"
	end
	local last = UserInputService:GetLastInputType()
	if GAMEPADS[last] then
		return "gamepad"
	elseif last == Enum.UserInputType.Touch then
		return "touch"
	elseif UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled then
		return "touch"
	end
	return "keyboard"
end

function Responsive.inputKind(): string
	start()
	return kind
end
function Responsive.isTouch(): boolean
	start()
	return kind == "touch"
end
function Responsive.isGamepad(): boolean
	start()
	return kind == "gamepad"
end

function Responsive.isCompact(): boolean
	start()
	return kind == "touch" or Responsive.viewport().X < Responsive.COMPACT_WIDTH
end

function Responsive.hudScale(): number
	local v = tonumber(player:GetAttribute("HUDScale")) or 1
	return math.clamp(v, Responsive.HUD_SCALE_MIN, Responsive.HUD_SCALE_MAX)
end

function Responsive.viewport(): Vector2
	local cam = workspace.CurrentCamera
	return if cam then cam.ViewportSize else Responsive.REFERENCE
end

function Responsive.baseScale(): number
	local vp = Responsive.viewport()
	local ref = Responsive.REFERENCE
	local s = math.min(vp.X / ref.X, vp.Y / ref.Y)
	local lo = if kind == "touch" then Responsive.TOUCH_MIN_SCALE else Responsive.MIN_SCALE
	return math.clamp(s, lo, Responsive.MAX_SCALE)
end

function Responsive.scale(): number
	start()
	return current
end

local function computeMotion(): boolean
	local a = player:GetAttribute("ReducedMotion")
	if type(a) == "boolean" then
		return a
	end
	local ok, v = pcall(function()
		return (GuiService :: any).ReducedMotionEnabled
	end)
	return ok and v == true
end

function Responsive.reducedMotion(): boolean
	start()
	return motionReduced
end

function Responsive.safeInsets(gui: ScreenGui?): {top: number, left: number, bottom: number, right: number}
	if gui and gui.IgnoreGuiInset then
		local tl, br = GuiService:GetGuiInset()
		return {top = tl.Y, left = tl.X, bottom = br.Y, right = br.X}
	end
	-- IgnoreGuiInset = false: Roblox already keeps the content below the top bar (and ScreenInsets handles notches)
	return {top = 0, left = 0, bottom = 0, right = 0}
end

local function applyScale(force: boolean?)
	local s = Responsive.baseScale() * Responsive.hudScale()
	if not force and math.abs(s - current) < 1e-3 then
		return
	end
	current = s
	for i = #scales, 1, -1 do
		local u = scales[i]
		if u.Parent then
			u.Scale = s
		else
			table.remove(scales, i)
		end
	end
	Bus.fire("hud.scale", s)
	notify("scale")
end

start = function()
	if started then
		return
	end
	started = true
	kind = computeKind()
	motionReduced = computeMotion()
	current = Responsive.baseScale() * Responsive.hudScale()
	local camConn: RBXScriptConnection? = nil
	local function hookCamera()
		if camConn then
			camConn:Disconnect()
		end
		local cam = workspace.CurrentCamera
		if cam then
			camConn = cam:GetPropertyChangedSignal("ViewportSize"):Connect(function()
				applyScale()
				notify("viewport") -- compact positions depend on the size even when the scale is clamped
			end)
		end
		applyScale()
	end
	workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(hookCamera)
	hookCamera()
	player:GetAttributeChangedSignal("HUDScale"):Connect(function()
		applyScale()
	end)
	local function inputChanged()
		local k = computeKind()
		if k ~= kind then
			kind = k
			notify("input")
			applyScale() -- the touch minimum may change the scale
		end
	end
	UserInputService.LastInputTypeChanged:Connect(inputChanged)
	pcall(function()
		UserInputService:GetPropertyChangedSignal("PreferredInput" :: any):Connect(inputChanged)
	end)
	local function motionChanged()
		local m = computeMotion()
		if m ~= motionReduced then
			motionReduced = m
			Bus.fire("hud.reducedMotion", m)
			notify("motion")
		end
	end
	player:GetAttributeChangedSignal("ReducedMotion"):Connect(motionChanged)
	pcall(function()
		GuiService:GetPropertyChangedSignal("ReducedMotionEnabled" :: any):Connect(motionChanged)
	end)
end

function Responsive.addScale(obj: GuiObject): UIScale
	start()
	local u = obj:FindFirstChild("MidnightScale")
	if not (u and u:IsA("UIScale")) then
		u = Instance.new("UIScale")
		u.Name = "MidnightScale"
		u.Parent = obj
	end
	local scale = u :: UIScale
	scale.Scale = current
	if not table.find(scales, scale) then
		table.insert(scales, scale)
	end
	return scale
end

function Responsive.attach(gui: ScreenGui)
	start()
	pcall(function()
		(gui :: any).ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets -- notches + Roblox top bar
	end)
	for _, name in Responsive.ANCHORS do
		local f = gui:FindFirstChild(name)
		if f and f:IsA("GuiObject") then
			Responsive.addScale(f)
		end
	end
	applyScale(true)
end

function Responsive.onChange(fn: (string) -> ()): () -> ()
	start()
	table.insert(callbacks, fn)
	return function()
		local i = table.find(callbacks, fn)
		if i then
			table.remove(callbacks, i)
		end
	end
end

return Responsive
