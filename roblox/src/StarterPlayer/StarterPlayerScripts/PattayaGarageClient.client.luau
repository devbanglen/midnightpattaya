-- Garage / car shop client: "E" (or the GARAGE button on mobile/gamepad X) inside the purple garage ring near the
-- Pattaya start opens the shop: cars with class, PI, stat bars, price/level; buy, select, upgrade, spawn my car.
-- Works on foot or in a car stopped in the ring. All money/level checks happen on the server (PattayaGarageServer).
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
local GarageRequest = remotes and remotes:WaitForChild("GarageRequest", 60)
local specsModule = ReplicatedStorage:WaitForChild("CarSpecs", 60)
local garage = workspace:WaitForChild("PattayaGarage", 120)
if not (GarageRequest and specsModule and garage) then
	return
end
local CarSpecs = require(specsModule)
local ring = garage:WaitForChild("Ring", 30)
if not ring then
	return
end
local RING_RADIUS = garage:GetAttribute("RingRadius") or 18
local STOP_SPEED = 30

local PURPLE, GOLD, WHITE = Color3.fromRGB(170, 70, 255), Color3.fromRGB(255, 200, 40), Color3.fromRGB(255, 255, 255)
local DARK = Color3.fromRGB(16, 12, 26)

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil

-- MIDNIGHT HUD (ui-core): Bus hook "garage.open" for the quick menu, and the legacy-hide flag (LocalPlayer attribute
-- "MidnightHUD", client-local). While it is true the new HUD shows the garage toasts; the shop and ring prompt stay.
local uiFolder = ReplicatedStorage:FindFirstChild("MidnightUI")
local busModule = uiFolder and uiFolder:FindFirstChild("Bus")
local Bus = if busModule then require(busModule) :: any else nil
local function midnight(): boolean
	return player:GetAttribute("MidnightHUD") == true
end

-- UI helpers ---------------------------------------------------------------------------------------------------------
local gui = Instance.new("ScreenGui")
gui.Name = "GarageUI"
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

local function label(parent: Instance, text: string, size: UDim2, pos: UDim2, font: Enum.Font?, color: Color3?): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Size = size
	t.Position = pos
	t.Font = font or Enum.Font.GothamMedium
	t.TextScaled = true
	t.TextColor3 = color or WHITE
	t.TextXAlignment = Enum.TextXAlignment.Left
	t.Text = text
	t.Parent = parent
	return t
end

local function button(parent: Instance, text: string, size: UDim2, pos: UDim2, color: Color3): TextButton
	local b = Instance.new("TextButton")
	b.Size = size
	b.Position = pos
	b.BackgroundColor3 = color
	b.AutoButtonColor = true
	b.Font = Enum.Font.GothamBlack
	b.TextScaled = true
	b.TextColor3 = WHITE
	b.Text = text
	b.Parent = parent
	Instance.new("UICorner", b).CornerRadius = UDim.new(0, 8)
	local pad = Instance.new("UIPadding", b)
	pad.PaddingTop, pad.PaddingBottom = UDim.new(0, 6), UDim.new(0, 6)
	return b
end

local prompt = Instance.new("TextLabel")
prompt.AnchorPoint = Vector2.new(0.5, 1)
prompt.Position = UDim2.new(0.5, 0, 1, -150)
prompt.Size = UDim2.fromOffset(520, 34)
prompt.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
prompt.BackgroundTransparency = 0.35
prompt.Font = Enum.Font.GothamBold
prompt.TextScaled = true
prompt.TextColor3 = Color3.fromRGB(220, 180, 255)
prompt.Text = "E   GARAGE: buy, pick and spawn your car"
prompt.Visible = false
prompt.Parent = gui
Instance.new("UICorner", prompt).CornerRadius = UDim.new(0, 8)

local toastLabel = label(gui, "", UDim2.fromOffset(640, 34), UDim2.new(0.5, -320, 0.32, 0), Enum.Font.GothamBlack, GOLD)
toastLabel.TextXAlignment = Enum.TextXAlignment.Center
toastLabel.TextStrokeTransparency = 0.3
toastLabel.Visible = false
local function toast(text: string)
	if midnight() and Bus then
		Bus.fire("toast", {title = "GARAGE", body = text, kind = "info", icon = "garage"})
		return
	end
	toastLabel.Text = text
	toastLabel.Visible = true
	local stamp = os.clock()
	toastLabel:SetAttribute("Stamp", stamp)
	task.delay(4, function()
		if toastLabel:GetAttribute("Stamp") == stamp then toastLabel.Visible = false end
	end)
end
player:GetAttributeChangedSignal("GarageMsgAt"):Connect(function()
	if midnight() then
		return -- MidnightHUD shows GarageMsg itself
	end
	toast(player:GetAttribute("GarageMsg") or "")
end)
player:GetAttributeChangedSignal("MidnightHUD"):Connect(function()
	if midnight() then
		toastLabel.Visible = false
	end
end)

-- shop window
local panel = Instance.new("Frame")
panel.AnchorPoint = Vector2.new(0.5, 0.5)
panel.Position = UDim2.fromScale(0.5, 0.5)
panel.Size = UDim2.fromScale(0.92, 0.84)
panel.BackgroundColor3 = DARK
panel.BackgroundTransparency = 0.08
panel.Visible = false
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 14)
local stroke = Instance.new("UIStroke", panel)
stroke.Color = PURPLE
stroke.Thickness = 2
local limit = Instance.new("UISizeConstraint", panel)
limit.MaxSize = Vector2.new(860, 520)

local title = label(panel, "MIDNIGHT PATTAYA GARAGE", UDim2.new(0.6, 0, 0, 30), UDim2.new(0, 16, 0, 10), Enum.Font.GothamBlack, Color3.fromRGB(220, 180, 255))
title.TextXAlignment = Enum.TextXAlignment.Left
if Style then
	Style.title(title)
	Style.accent(panel, 14)
end
local wallet = label(panel, "", UDim2.new(0.36, 0, 0, 24), UDim2.new(0.62, 0, 0, 14), Enum.Font.GothamBold, GOLD)
wallet.TextXAlignment = Enum.TextXAlignment.Right

-- car list (left)
local list = Instance.new("Frame")
list.BackgroundTransparency = 1
list.Position = UDim2.new(0, 12, 0, 50)
list.Size = UDim2.new(0.36, -12, 1, -110)
list.Parent = panel
local layout = Instance.new("UIListLayout", list)
layout.Padding = UDim.new(0, 6)
layout.SortOrder = Enum.SortOrder.LayoutOrder

-- details (right)
local detail = Instance.new("Frame")
detail.BackgroundTransparency = 1
detail.Position = UDim2.new(0.36, 12, 0, 50)
detail.Size = UDim2.new(0.64, -24, 1, -110)
detail.Parent = panel
local dName = label(detail, "", UDim2.new(0.7, 0, 0, 30), UDim2.new(0, 0, 0, 0), Enum.Font.GothamBlack)
local dClass = label(detail, "", UDim2.new(0.3, 0, 0, 30), UDim2.new(0.7, 0, 0, 0), Enum.Font.GothamBlack)
dClass.TextXAlignment = Enum.TextXAlignment.Right
local dBlurb = label(detail, "", UDim2.new(1, 0, 0, 18), UDim2.new(0, 0, 0, 34), Enum.Font.GothamMedium, Color3.fromRGB(200, 200, 215))

local BARS = {
	{key = "speed", name = "Top speed", value = function(s) return ("%d"):format(s.maxSpeed) end},
	{key = "accel", name = "Acceleration", value = function(s) return ("%d"):format(s.accel) end},
	{key = "brake", name = "Braking", value = function(s) return ("%d"):format(s.brake) end},
	{key = "grip", name = "Handling", value = function(s) return ("%.1f"):format(s.grip) end},
	{key = "drift", name = "Drift", value = function(s) return ("%.2f"):format(s.driftTurnBoost) end},
	{key = "nitro", name = "Nitro", value = function(s) return ("%d / %d"):format(s.nitroSpeed, s.nitroMax) end},
}
local bars = {}
for i, b in BARS do
	local y = 58 + (i - 1) * 26
	label(detail, b.name, UDim2.new(0.26, 0, 0, 18), UDim2.new(0, 0, 0, y + 2), Enum.Font.GothamBold)
	local back = Instance.new("Frame")
	back.Position = UDim2.new(0.27, 0, 0, y + 5)
	back.Size = UDim2.new(0.53, 0, 0, 12)
	back.BackgroundColor3 = Color3.fromRGB(45, 40, 60)
	back.Parent = detail
	Instance.new("UICorner", back).CornerRadius = UDim.new(0, 6)
	local fill = Instance.new("Frame")
	fill.Size = UDim2.fromScale(0.5, 1)
	fill.BackgroundColor3 = PURPLE
	fill.Parent = back
	Instance.new("UICorner", fill).CornerRadius = UDim.new(0, 6)
	local v = label(detail, "", UDim2.new(0.18, 0, 0, 18), UDim2.new(0.82, 0, 0, y + 2), Enum.Font.GothamBold)
	v.TextXAlignment = Enum.TextXAlignment.Right
	bars[b.key] = {fill = fill, value = v, fmt = b.value}
end
local dPrice = label(detail, "", UDim2.new(1, 0, 0, 22), UDim2.new(0, 0, 0, 220), Enum.Font.GothamBold, GOLD)
local actionBtn = button(detail, "", UDim2.new(0.48, 0, 0, 40), UDim2.new(0, 0, 0, 250), PURPLE)
local upEngine = button(detail, "", UDim2.new(0.48, 0, 0, 30), UDim2.new(0.52, 0, 0, 250), Color3.fromRGB(70, 60, 95))
local upGrip = button(detail, "", UDim2.new(0.48, 0, 0, 30), UDim2.new(0.52, 0, 0, 286), Color3.fromRGB(70, 60, 95))
local upNote = label(detail, "Upgrades are optional and stay inside the car's class.", UDim2.new(1, 0, 0, 16),
	UDim2.new(0, 0, 0, 324), Enum.Font.GothamMedium, Color3.fromRGB(170, 170, 190))

-- bottom row
local spawnBtn = button(panel, "SPAWN MY CAR", UDim2.new(0.4, 0, 0, 44), UDim2.new(0, 12, 1, -54), Color3.fromRGB(40, 150, 90))
local closeBtn = button(panel, "CLOSE", UDim2.new(0.18, 0, 0, 44), UDim2.new(1, -12, 1, -54), Color3.fromRGB(90, 40, 50))
closeBtn.AnchorPoint = Vector2.new(1, 0)
local msg = label(panel, "", UDim2.new(0.38, -24, 0, 36), UDim2.new(0.42, 0, 1, -50), Enum.Font.GothamBold, WHITE)
msg.TextWrapped = true
gui.Parent = player:WaitForChild("PlayerGui")

-- Shop logic ---------------------------------------------------------------------------------------------------------
local st = nil -- last state from the server
local focus = CarSpecs.STARTER
local rows = {}
local open = false
local pending = false

local function upgradesOf(id: string): (number, number)
	local u = st and st.upgrades and st.upgrades[id]
	if type(u) ~= "table" then
		return 0, 0
	end
	return u.engine or 0, u.grip or 0
end

local function refresh()
	if not st then
		return
	end
	wallet.Text = ("Level %d   ฿%d"):format(st.level, st.money)
	for _, id in CarSpecs.ORDER do
		local car = CarSpecs.Cars[id]
		local e, g = upgradesOf(id)
		local d = CarSpecs.Describe(id, e, g)
		local row = rows[id]
		local status
		if st.selected == id then
			status = "SELECTED"
		elseif st.owned[id] then
			status = "OWNED"
		elseif st.level < car.level then
			status = ("LOCKED Lv %d"):format(car.level)
		else
			status = ("฿%d"):format(car.price)
		end
		row.name.Text = car.name
		row.info.Text = ("%s %d   %s"):format(d.class, d.pi, status)
		row.info.TextColor3 = CarSpecs.ClassColor(d.class)
		row.button.BackgroundColor3 = if id == focus then Color3.fromRGB(80, 50, 130) else Color3.fromRGB(35, 30, 50)
	end
	local car = CarSpecs.Cars[focus]
	local e, g = upgradesOf(focus)
	local d = CarSpecs.Describe(focus, e, g)
	dName.Text = car.name
	dClass.Text = ("%s  PI %d"):format(d.class, d.pi)
	dClass.TextColor3 = CarSpecs.ClassColor(d.class)
	dBlurb.Text = car.blurb
	local r = CarSpecs.Ratings(d.stats)
	for key, b in bars do
		b.fill.Size = UDim2.fromScale(math.max(0.03, r[key]), 1)
		b.value.Text = b.fmt(d.stats)
	end
	local owned = st.owned[focus] == true
	if owned then
		dPrice.Text = if st.selected == focus then "Owned · selected" else "Owned"
		actionBtn.Text = if st.selected == focus then "SELECTED" else "SELECT"
		actionBtn.BackgroundColor3 = if st.selected == focus then Color3.fromRGB(60, 60, 70) else PURPLE
	else
		dPrice.Text = ("Price ฿%d   ·   Level %d needed"):format(car.price, car.level)
		local can = st.level >= car.level and st.money >= car.price
		actionBtn.Text = if st.level < car.level then ("LOCKED (Lv %d)"):format(car.level) else ("BUY ฿%d"):format(car.price)
		actionBtn.BackgroundColor3 = if can then Color3.fromRGB(200, 140, 20) else Color3.fromRGB(60, 60, 70)
	end
	for _, pair in {{"engine", upEngine, e}, {"grip", upGrip, g}} do
		local kind, btn, tier = pair[1], pair[2], pair[3]
		local ok, reason, price = CarSpecs.CanUpgrade(focus, e, g, kind)
		local nameText = if kind == "engine" then "ENGINE" else "GRIP"
		btn.Visible = owned
		if tier >= CarSpecs.MAX_TIER then
			btn.Text = ("%s %d/%d  MAX"):format(nameText, tier, CarSpecs.MAX_TIER)
		elseif ok then
			btn.Text = ("%s %d/%d  +1 ฿%d"):format(nameText, tier, CarSpecs.MAX_TIER, price)
		else
			btn.Text = ("%s %d/%d  class max"):format(nameText, tier, CarSpecs.MAX_TIER)
			btn:SetAttribute("Reason", reason)
		end
	end
	upNote.Visible = owned
	spawnBtn.Text = ("SPAWN MY %s"):format(string.upper(CarSpecs.Cars[st.selected] and CarSpecs.Cars[st.selected].name or "CAR"))
end

local function request(action: string, id: string?, kind: string?)
	if pending then
		return
	end
	pending = true
	local ok, res = pcall(function()
		return GarageRequest:InvokeServer(action, id, kind)
	end)
	pending = false
	if not ok or type(res) ~= "table" then
		msg.Text = "Garage not answering, try again"
		return
	end
	if res.state then
		st = res.state
	end
	if res.msg then
		msg.Text = res.msg
		msg.TextColor3 = if res.ok then Color3.fromRGB(140, 255, 160) else Color3.fromRGB(255, 120, 110)
	end
	refresh()
	return res
end

for i, id in CarSpecs.ORDER do
	local b = Instance.new("TextButton")
	b.Size = UDim2.new(1, 0, 0, 54)
	b.LayoutOrder = i
	b.BackgroundColor3 = Color3.fromRGB(35, 30, 50)
	b.AutoButtonColor = true
	b.Text = ""
	b.Parent = list
	Instance.new("UICorner", b).CornerRadius = UDim.new(0, 8)
	local n = label(b, "", UDim2.new(1, -16, 0.5, -2), UDim2.new(0, 8, 0, 4), Enum.Font.GothamBlack)
	local info = label(b, "", UDim2.new(1, -16, 0.4, 0), UDim2.new(0, 8, 0.55, 0), Enum.Font.GothamBold)
	rows[id] = {button = b, name = n, info = info}
	b.Activated:Connect(function()
		focus = id
		refresh()
	end)
end

actionBtn.Activated:Connect(function()
	if not st then return end
	if st.owned[focus] then
		if st.selected ~= focus then request("select", focus) end
	else
		request("buy", focus)
	end
end)
upEngine.Activated:Connect(function() request("upgrade", focus, "engine") end)
upGrip.Activated:Connect(function() request("upgrade", focus, "grip") end)

local function setOpen(on: boolean)
	open = on
	panel.Visible = on
	if on then
		msg.Text = ""
		local res = request("state")
		if res and res.state then
			focus = res.state.selected or focus
			refresh()
		end
	end
end
closeBtn.Activated:Connect(function() setOpen(false) end)
spawnBtn.Activated:Connect(function()
	local res = request("spawn")
	if res and res.ok then
		setOpen(false)
		toast(res.msg)
	end
end)

-- Ring prompt (nearRing: updated every frame below, read by the quick-menu hook) --------------------------------------------------------------------------------------------------------
local bound = false
local nearRing = false
local function setBound(on: boolean)
	if on and not bound then
		ContextActionService:BindAction("PattayaGarage", function(_, state)
			if state ~= Enum.UserInputState.Begin then
				return Enum.ContextActionResult.Pass
			end
			task.spawn(setOpen, not open) -- opening asks the server, don't yield inside the action handler
			return Enum.ContextActionResult.Sink
		end, true, Enum.KeyCode.E, Enum.KeyCode.ButtonX)
		ContextActionService:SetTitle("PattayaGarage", "GARAGE")
		ContextActionService:SetPosition("PattayaGarage", UDim2.new(1, -290, 1, -310))
		bound = true
	elseif not on and bound then
		ContextActionService:UnbindAction("PattayaGarage")
		bound = false
	end
end

local function busy(): boolean
	return player:GetAttribute("RaceState") == "racing" or player:GetAttribute("SprintActive") == true
		or player:GetAttribute("JobActive") == true
end

RunService.RenderStepped:Connect(function()
	local char = player.Character
	local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local here = false
	if root and hum and hum.Health > 0 and not busy() then
		local seat = hum.SeatPart
		local body = if seat and seat.Parent and seat.Parent.PrimaryPart then seat.Parent.PrimaryPart else root
		local d = body.Position - ring.Position
		if Vector3.new(d.X, 0, d.Z).Magnitude < RING_RADIUS and math.abs(d.Y) < 20 then
			local v = body.AssemblyLinearVelocity
			here = seat == nil or Vector3.new(v.X, 0, v.Z).Magnitude < STOP_SPEED
		end
	end
	nearRing = here
	prompt.Visible = here and not open
	setBound(here or open)
	if open and not here then
		-- walked/drove away (or a race started): close the shop
		local d = root and (root.Position - ring.Position)
		if not d or Vector3.new(d.X, 0, d.Z).Magnitude > RING_RADIUS + 12 or busy() then
			setOpen(false)
		end
	end
end)

-- quick menu (MidnightHUD TopRight "Garage"): opens the same shop window as E, only inside the garage ring
if Bus then
	Bus.on("garage.open", function()
		if nearRing then
			if not open then
				task.spawn(setOpen, true)
			end
		else
			Bus.fire("toast", {title = "GARAGE", kind = "info", icon = "garage",
				body = "ไปที่วงม่วงข้างจุดเกิด แล้วกด E  ·  Go to the purple ring by the spawn, press E"})
		end
	end)
end
