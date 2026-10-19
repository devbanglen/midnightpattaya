-- MIDNIGHT PATTAYA touch controls (ReplicatedStorage.MidnightUI.TouchControls, ui-fix round 3). Client only.
-- The game's legacy scripts bind their actions with ContextActionService createTouchButton = true. On a phone those
-- Roblox buttons (NOS / DRIFT / R / SPRINT / RACE / CIRCUIT / GPS / MAP ...) used to sit at hand-picked offsets and
-- overlapped each other. While the compact HUD is on (LocalPlayer attribute MidnightHUD == true, PlayerGui.MidnightHUD
-- attribute Compact == true, and the device has touch) this module:
--   * removes the GPS and MAP touch buttons (unbind + rebind the same handler/keys without a button): the HUD's
--     minimap expand button / quick menu open the map, the minimap header GPS chip cycles the GPS;
--   * puts the remaining buttons in a fixed grid above the jump button (2 columns x 3 rows, 8 px gaps, NOS 72 px,
--     the others 56 px) plus up to 3 "context" slots left of it (FIGHT / GARAGE / JOIN, only while bound);
--   * restyles each button with Theme tokens (rounded, navy glass, cyan stroke, own pressed state).
-- When any condition goes false everything is put back exactly: the original title/position (from register opts),
-- size, image and title styling (snapshotted before the first change), and hidden actions are rebound with a button.
--   TouchControls.register(actionName, opts)  call right after the legacy BindAction (+ SetTitle/SetPosition)
--     opts.slot     "nitro" | "drift" | "reset" | "sprint" | "race" | "circuit" | "context"
--     opts.hide     true: no touch button while compact (needs opts.handler + opts.keys to rebind)
--     opts.handler  the bound function;  opts.keys  {Enum.KeyCode...} as passed to BindAction
--     opts.title / opts.position  the legacy SetTitle / SetPosition values (restored when the layout turns off)
--   TouchControls.active()  -> boolean        TouchControls.rects() -> {[actionName]: {x, y, w, h}} (gui px, live)
--   TouchControls.refresh()                   re-apply now (also runs on every flag / viewport change and at 2 Hz)
-- Layout and the test steps: docs/UI_SYSTEM.md "Round 3: touch controls". Never errors into the caller (pcall).
local Players = game:GetService("Players")
local ContextActionService = game:GetService("ContextActionService")
local UserInputService = game:GetService("UserInputService")

local Theme = require(script.Parent.Theme)
local col = Theme.color

local TouchControls = {}

TouchControls.GAP = 8
-- slot -> offset of the button's top-left corner from (R, B) = (jump button right edge, 8 px above the jump button),
-- in px at grid scale 1: x = R - dx, y = B - dy; size in px. Right column is 72 wide (NOS), the 56 px buttons in it
-- are centred in that column.
TouchControls.SLOTS = {
	nitro = {dx = 72, dy = 72, size = 72},
	drift = {dx = 136, dy = 56, size = 56},
	reset = {dx = 64, dy = 136, size = 56},
	sprint = {dx = 136, dy = 136, size = 56},
	race = {dx = 64, dy = 200, size = 56},
	circuit = {dx = 136, dy = 200, size = 56},
	ctx1 = {dx = 200, dy = 56, size = 56},
	ctx2 = {dx = 200, dy = 136, size = 56},
	ctx3 = {dx = 264, dy = 56, size = 56},
}
TouchControls.GRID_H = 200 -- px from the top of the race row to B at grid scale 1
TouchControls.MIN_BUTTON = 44 -- the grid shrinks on short screens, never below 44 px buttons

-- buttons of scripts the UI team does not edit: managed by name, original positions copied from those scripts
local AUTO = {
	PattayaGarage = {slot = "context", title = "GARAGE", position = UDim2.new(1, -290, 1, -310)}, -- PattayaGarageClient
	EventJoin = {slot = "context", title = "JOIN", position = UDim2.new(1, -340, 1, -240)}, -- PattayaEventsClient
}
local CONTEXT_ORDER = {"RoadFight", "PattayaGarage", "EventJoin"}

type Reg = {slot: string?, hide: boolean?, handler: any, keys: {any}?, title: string?, position: UDim2?}
type Styled = {button: GuiButton, snap: {[string]: any}, title: TextLabel?, titleSnap: {[string]: any}?,
	conns: {RBXScriptConnection}, extras: {Instance}, key: string?, accent: boolean}

local player = Players.LocalPlayer
local registered: {[string]: Reg} = {}
local hidden: {[string]: boolean} = {}
local styled: {[string]: Styled} = {}
local liveRects: {[string]: {x: number, y: number, w: number, h: number}} = {}
local started = false
local hud: ScreenGui? = nil
local hudConn: RBXScriptConnection? = nil
local scheduled = false

local function playerGui(): Instance?
	return player:FindFirstChildOfClass("PlayerGui")
end

function TouchControls.active(): boolean
	return player:GetAttribute("MidnightHUD") == true and hud ~= nil and hud.Parent ~= nil
		and hud:GetAttribute("Compact") == true and UserInputService.TouchEnabled
end

local function isBound(name: string): boolean
	local ok, info = pcall(function()
		return ContextActionService:GetBoundActionInfo(name)
	end)
	return ok and type(info) == "table" and next(info) ~= nil
end

local function buttonOf(name: string): GuiButton?
	-- GetButton on an UNBOUND action prints "ContextActionService could not find the function passed in, doing
	-- nothing." on every call (measured in Studio: refreshNow runs every 0.5 s for CarNitro/CarDrift/CarReset while not
	-- in a car, ~7 lines/s); GetBoundActionInfo is silent, so ask that first
	if not isBound(name) then
		return nil
	end
	local ok, b = pcall(function()
		return ContextActionService:GetButton(name)
	end)
	if ok and typeof(b) == "Instance" and b:IsA("GuiButton") then
		return b
	end
	return nil
end

-- hide / show (GPS, MAP) ---------------------------------------------------------------------------------------------
local function hideAction(name: string, reg: Reg)
	if not (reg.handler and reg.keys) or not isBound(name) then
		return
	end
	ContextActionService:UnbindAction(name)
	ContextActionService:BindAction(name, reg.handler, false, table.unpack(reg.keys))
	hidden[name] = true
end

local function showAction(name: string, reg: Reg)
	hidden[name] = nil
	if not (reg.handler and reg.keys) or not isBound(name) then
		return -- the legacy script unbound it meanwhile: nothing to restore
	end
	ContextActionService:UnbindAction(name)
	ContextActionService:BindAction(name, reg.handler, true, table.unpack(reg.keys))
	if reg.title then
		ContextActionService:SetTitle(name, reg.title)
	end
	if reg.position then
		ContextActionService:SetPosition(name, reg.position)
	end
end

-- styling -------------------------------------------------------------------------------------------------------------
local BUTTON_PROPS = {"Size", "Image", "ImageTransparency", "BackgroundTransparency", "BackgroundColor3", "AutoButtonColor"}
local TITLE_PROPS = {"Font", "TextColor3", "TextScaled", "TextSize", "TextStrokeTransparency", "Size", "Position",
	"AnchorPoint"}

local function snapshot(obj: Instance, props: {string}): {[string]: any}
	local s = {}
	for _, p in props do
		local ok, v = pcall(function()
			return (obj :: any)[p]
		end)
		if ok then
			s[p] = v
		end
	end
	return s
end

local function restoreProps(obj: Instance, s: {[string]: any})
	for p, v in s do
		pcall(function()
			(obj :: any)[p] = v
		end)
	end
end

local function paint(st: Styled, pressed: boolean)
	local b = st.button
	b.BackgroundColor3 = if pressed then col.cyan else col.navy
	b.BackgroundTransparency = if pressed then 0.15 else Theme.alpha.panel
	if st.title then
		st.title.TextColor3 = if pressed then col.navy else col.text
	end
end

local function styleTitle(st: Styled): boolean -- true when the title was styled just now
	if st.title and st.title.Parent == st.button then
		return false
	end
	local t = st.button:FindFirstChild("ActionTitle")
	if not (t and t:IsA("TextLabel")) then
		return false -- the core script adds it after SetTitle; picked up on a later refresh
	end
	st.title = t
	st.titleSnap = snapshot(t, TITLE_PROPS)
	t.Font = Theme.font.display
	t.TextColor3 = col.text
	t.TextStrokeTransparency = 1
	t.TextScaled = true
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromScale(0.5, 0.5)
	t.Size = UDim2.new(1, -10, 0.5, 0)
	local lim = Instance.new("UITextSizeConstraint")
	lim.Name = "MidnightTextSize"
	lim.MaxTextSize = if st.accent then Theme.size.title else Theme.size.label
	lim.MinTextSize = 8
	lim.Parent = t
	table.insert(st.extras, lim)
	return true
end

local function style(name: string, b: GuiButton, reg: Reg): Styled
	local st: Styled = {button = b, snap = snapshot(b, BUTTON_PROPS), conns = {}, extras = {}, accent = reg.slot == "nitro"}
	b.AutoButtonColor = false
	if b:IsA("ImageButton") then
		b.ImageTransparency = 1 -- the Roblox circle image; the core may swap it on press, it stays invisible
	end
	local corner = Instance.new("UICorner")
	corner.Name = "MidnightCorner"
	corner.CornerRadius = UDim.new(0, Theme.radius.panel)
	corner.Parent = b
	local stroke = Instance.new("UIStroke")
	stroke.Name = "MidnightStroke"
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	stroke.Color = if st.accent then col.cyan else col.line
	stroke.Thickness = if st.accent then Theme.stroke.thick else Theme.stroke.normal
	stroke.Transparency = 0.1
	stroke.Parent = b
	table.insert(st.extras, corner)
	table.insert(st.extras, stroke)
	-- own pressed state: follows the touch that began on the button until that touch ends / is cancelled
	table.insert(st.conns, b.InputBegan:Connect(function(input: InputObject)
		if input.UserInputType ~= Enum.UserInputType.Touch and input.UserInputType ~= Enum.UserInputType.MouseButton1 then
			return
		end
		paint(st, true)
		local c: RBXScriptConnection
		c = input:GetPropertyChangedSignal("UserInputState"):Connect(function()
			if input.UserInputState == Enum.UserInputState.End or input.UserInputState == Enum.UserInputState.Cancel then
				c:Disconnect()
				if styled[name] == st then
					paint(st, false)
				end
			end
		end)
		table.insert(st.conns, c)
	end))
	styleTitle(st)
	paint(st, false)
	styled[name] = st
	return st
end

local function unstyle(name: string, reg: Reg?)
	local st = styled[name]
	if not st then
		return
	end
	styled[name] = nil
	liveRects[name] = nil
	for _, c in st.conns do
		c:Disconnect()
	end
	for _, e in st.extras do
		e:Destroy()
	end
	if st.button.Parent then
		restoreProps(st.button, st.snap)
		if st.title and st.titleSnap then
			restoreProps(st.title, st.titleSnap)
		end
		if reg and reg.position and isBound(name) then -- SetPosition on an unbound action prints too
			ContextActionService:SetPosition(name, reg.position)
		end
	end
end

-- grid geometry (absolute gui px, the AbsolutePosition space) --------------------------------------------------------
local function anchorPoint(): (number, number, number)
	local pg = playerGui()
	local touchGui = pg and pg:FindFirstChild("TouchGui")
	local jump = touchGui and touchGui:FindFirstChild("JumpButton", true)
	local R, B
	if jump and jump:IsA("GuiObject") and jump.AbsoluteSize.X > 0 then
		R = jump.AbsolutePosition.X + jump.AbsoluteSize.X
		B = jump.AbsolutePosition.Y - TouchControls.GAP
	else -- Roblox's jump button formula (TouchJump): 70 px at (W-95, H-90) on small screens, else 120 px
		local origin = if hud then hud.AbsolutePosition else Vector2.zero
		local size = if hud then hud.AbsoluteSize else Vector2.new(830, 381)
		local cam = workspace.CurrentCamera
		local vp = if cam then cam.ViewportSize else size
		local small = math.min(vp.X, vp.Y) <= 500
		R = origin.X + size.X - (if small then 25 else 50)
		B = origin.Y + size.Y - (if small then 90 else 210) - TouchControls.GAP
	end
	-- top limit: 8 px under the HUD's compact menu button (top-right)
	local top = (if hud then hud.AbsolutePosition.Y else 0) + 64
	local menu = hud and hud:FindFirstChild("TopRight")
	menu = menu and menu:FindFirstChild("MenuButton")
	if menu and menu:IsA("GuiObject") and menu.AbsoluteSize.Y > 0 then
		top = menu.AbsolutePosition.Y + menu.AbsoluteSize.Y + TouchControls.GAP
	end
	local k = math.clamp((B - top) / TouchControls.GRID_H, TouchControls.MIN_BUTTON / 56, 1)
	return R, B, k
end

local function rectFor(slot: string, R: number, B: number, k: number): {x: number, y: number, w: number, h: number}?
	local s = TouchControls.SLOTS[slot]
	if not s then
		return nil
	end
	local size = math.floor(s.size * k + 0.5)
	return {x = math.floor(R - s.dx * k + 0.5), y = math.floor(B - s.dy * k + 0.5), w = size, h = size}
end

local function place(name: string, st: Styled, r: {x: number, y: number, w: number, h: number})
	local b = st.button
	local parent = b.Parent
	local origin = if parent and parent:IsA("GuiBase2d") then (parent :: any).AbsolutePosition else Vector2.zero
	local ap = b.AnchorPoint -- the core script's buttons use (0, 0); honour anything else
	local px, py = r.x - origin.X + ap.X * r.w, r.y - origin.Y + ap.Y * r.h
	local key = ("%d,%d,%d"):format(px, py, r.w)
	liveRects[name] = r
	local size = UDim2.fromOffset(r.w, r.h)
	if b.Size ~= size then
		b.Size = size
	end
	if st.key == key then
		return
	end
	st.key = key
	ContextActionService:SetPosition(name, UDim2.fromOffset(px, py))
end

-- refresh -------------------------------------------------------------------------------------------------------------
local function refreshNow()
	local on = TouchControls.active()
	for name, reg in registered do
		if reg.hide then
			if on and not hidden[name] then
				hideAction(name, reg)
			elseif not on and hidden[name] then
				showAction(name, reg)
			end
		end
	end
	local R, B, k = 0, 0, 1
	if on then
		R, B, k = anchorPoint()
	end
	-- context slots go to the bound context buttons in a fixed order
	local ctxSlot: {[string]: string} = {}
	local n = 0
	for _, name in CONTEXT_ORDER do
		if registered[name] and buttonOf(name) then
			n += 1
			if n <= 3 then
				ctxSlot[name] = "ctx" .. n
			end
		end
	end
	for name, reg in registered do
		if not reg.hide then
			local b = buttonOf(name)
			local st = styled[name]
			if st and st.button ~= b then -- rebound (new button) or unbound: the old one is gone, forget it
				for _, c in st.conns do
					c:Disconnect()
				end
				styled[name] = nil
				liveRects[name] = nil
				st = nil
			end
			local slot = if reg.slot == "context" then ctxSlot[name] else reg.slot
			local r = if on and slot then rectFor(slot, R, B, k) else nil
			if r and b then
				local s = st or style(name, b, reg)
				if styleTitle(s) then
					paint(s, false) -- never repainted otherwise: a held button keeps its pressed look
				end
				place(name, s, r)
			elseif st then
				unstyle(name, reg)
			end
		end
	end
end

function TouchControls.refresh()
	local ok, err = pcall(refreshNow)
	if not ok then
		warn("TouchControls: " .. tostring(err))
	end
end

local function schedule()
	if scheduled then
		return
	end
	scheduled = true
	task.defer(function()
		scheduled = false
		TouchControls.refresh()
	end)
end

local function hookHud(g: Instance?)
	if not (g and g:IsA("ScreenGui") and g.Name == "MidnightHUD") then
		return
	end
	hud = g
	if hudConn then
		hudConn:Disconnect()
	end
	hudConn = g:GetAttributeChangedSignal("Compact"):Connect(schedule)
	schedule()
end

local function start()
	if started then
		return
	end
	started = true
	for name, reg in AUTO do
		if not registered[name] then
			registered[name] = reg
		end
	end
	task.spawn(function()
		local pg = player:WaitForChild("PlayerGui")
		hookHud(pg:FindFirstChild("MidnightHUD"))
		pg.ChildAdded:Connect(function(c)
			if c.Name == "MidnightHUD" then
				task.defer(hookHud, c)
			end
		end)
	end)
	player:GetAttributeChangedSignal("MidnightHUD"):Connect(schedule)
	local camConn: RBXScriptConnection? = nil
	local function hookCamera()
		if camConn then
			camConn:Disconnect()
		end
		local cam = workspace.CurrentCamera
		if cam then
			camConn = cam:GetPropertyChangedSignal("ViewportSize"):Connect(schedule)
		end
	end
	workspace:GetPropertyChangedSignal("CurrentCamera"):Connect(hookCamera)
	hookCamera()
	task.spawn(function() -- buttons are created by the Roblox core script a moment after BindAction, and come and go
		while true do
			task.wait(0.5)
			if TouchControls.active() or next(styled) ~= nil or next(hidden) ~= nil then
				TouchControls.refresh()
			end
		end
	end)
end

function TouchControls.register(actionName: string, opts: Reg?)
	local ok, err = pcall(function()
		start()
		registered[actionName] = opts or {}
		hidden[actionName] = nil -- a fresh BindAction made a fresh (visible) button
		schedule()
	end)
	if not ok then
		warn("TouchControls.register: " .. tostring(err))
	end
end

function TouchControls.rects(): {[string]: {x: number, y: number, w: number, h: number}}
	return table.clone(liveRects)
end

function TouchControls.registered(): {string}
	local out = {}
	for name in registered do
		table.insert(out, name)
	end
	table.sort(out)
	return out
end

function TouchControls.isHidden(name: string): boolean
	return hidden[name] == true
end

return TouchControls
