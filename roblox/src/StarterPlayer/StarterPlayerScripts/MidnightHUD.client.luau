-- MIDNIGHT PATTAYA premium HUD root (ui-core, 2026-10-19). Builds PlayerGui.MidnightHUD with the anchor frames of
-- docs/UI_CONTRACT.md (TopLeft, TopCenter, TopRight, BottomLeft, BottomCenter, BottomRight, Toasts, Modal) and, inside
-- them, the parts ui-core owns: the player card + money pill (TopLeft), the quick menu (TopRight), the toasts, the
-- context-action chips + job strip (BottomCenter), and the Settings / Help / Events modals plus the shared modal API.
-- ui-race fills TopCenter + BottomRight, ui-map fills BottomLeft. Layout follows docs/images/ui_mockup_owner.png
-- (1600x900 reference, scaled by MidnightUI.Responsive). Architecture and test checklist: docs/UI_SYSTEM.md.
-- Legacy-hide flag: LocalPlayer attribute "MidnightHUD" = true once built (client-local, never replicated state);
-- legacy HUD scripts hide the strips this HUD replaces while it is true.
-- Data is read-only and server-owned (leaderstats, player attributes); nothing here creates progression or race state.
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local GuiService = game:GetService("GuiService")
local UserInputService = game:GetService("UserInputService")
local ContextActionService = game:GetService("ContextActionService")
local TweenService = game:GetService("TweenService")

local player = Players.LocalPlayer
local uiFolder = ReplicatedStorage:WaitForChild("MidnightUI", 30)
if not uiFolder then
	warn("MidnightHUD: ReplicatedStorage.MidnightUI missing; the legacy HUD stays on")
	return
end
local Theme = require(uiFolder:WaitForChild("Theme"))
local Bus = require(uiFolder:WaitForChild("Bus"))
local Responsive = require(uiFolder:WaitForChild("Responsive"))
local InputPrompts = require(uiFolder:WaitForChild("InputPrompts"))
local C = require(uiFolder:WaitForChild("Components"))

local col = Theme.color
local MARGIN = 20 -- px from the safe-area edge (screen space, not scaled)

-- PattayaProgress.expToNext (ServerStorage.PattayaProgress, server-only module): EXP needed to go from `level` to
-- level + 1. Copied verbatim because the client cannot require ServerStorage; if the server rule changes, change it
-- here too (docs/UI_SYSTEM.md "Known gaps").
local function expToNext(level: number): number
	return 100 + (level - 1) * 60
end

local function commas(n: number): string
	local s = tostring(math.floor(math.abs(n) + 0.5))
	local out = s:reverse():gsub("(%d%d%d)", "%1,"):reverse()
	if out:sub(1, 1) == "," then
		out = out:sub(2)
	end
	return (if n < 0 then "-" else "") .. out
end

-- Root ScreenGui + anchors ------------------------------------------------------------------------------------------
local playerGui = player:WaitForChild("PlayerGui")
local old = playerGui:FindFirstChild("MidnightHUD")
if old then
	old:Destroy() -- a re-run of this script (Studio reinstall) never leaves two HUDs
end
local gui = Instance.new("ScreenGui")
gui.Name = "MidnightHUD"
gui.DisplayOrder = Theme.layer.hud
gui.IgnoreGuiInset = false
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

-- design sizes at scale 1 (1600x900 reference, measured from the owner's mockup)
local ANCHORS = {
	TopLeft = {anchor = Vector2.new(0, 0), size = Vector2.new(600, 120)},
	TopCenter = {anchor = Vector2.new(0.5, 0), size = Vector2.new(560, 260)},
	TopRight = {anchor = Vector2.new(1, 0), size = Vector2.new(520, 96)},
	BottomLeft = {anchor = Vector2.new(0, 1), size = Vector2.new(340, 300)},
	BottomCenter = {anchor = Vector2.new(0.5, 1), size = Vector2.new(620, 100)},
	BottomRight = {anchor = Vector2.new(1, 1), size = Vector2.new(440, 300)},
	Toasts = {anchor = Vector2.new(1, 1), size = Vector2.new(290, 260)},
}
local anchors: {[string]: Frame} = {}
for name, def in ANCHORS do
	local f = Instance.new("Frame")
	f.Name = name
	f.BackgroundTransparency = 1
	f.AnchorPoint = def.anchor
	f.Size = UDim2.fromOffset(def.size.X, def.size.Y)
	f.Active = false
	f.ZIndex = if name == "Toasts" then 60 else 1
	f.Parent = gui
	anchors[name] = f
end
local modal = Instance.new("Frame")
modal.Name = "Modal"
modal.Size = UDim2.fromScale(1, 1)
modal.BackgroundColor3 = col.navy
modal.BackgroundTransparency = Theme.alpha.overlay
modal.BorderSizePixel = 0
modal.Active = true -- swallows clicks behind an open modal
modal.Visible = false
modal.ZIndex = 50
modal.Parent = gui

-- positions depend on the scale (Toasts sit above the scaled BottomRight) and on touch (reserve for the jump button)
local function layout()
	local s = Responsive.scale()
	local touch = Responsive.isTouch()
	local reserve = if touch then Responsive.TOUCH_RESERVE else 0
	anchors.TopLeft.Position = UDim2.fromOffset(MARGIN, MARGIN)
	anchors.TopCenter.Position = UDim2.new(0.5, 0, 0, MARGIN)
	anchors.TopRight.Position = UDim2.new(1, -MARGIN, 0, MARGIN)
	anchors.BottomCenter.Position = UDim2.new(0.5, 0, 1, -MARGIN)
	anchors.BottomRight.Position = UDim2.new(1, -(MARGIN + reserve), 1, -MARGIN)
	anchors.Toasts.Position = UDim2.new(1, -(MARGIN + reserve), 1,
		-(MARGIN + math.floor(ANCHORS.BottomRight.size.Y * s) + 12))
	if touch then
		-- the dynamic thumbstick owns the lower-left of the screen: the minimap anchor moves under the player card
		anchors.BottomLeft.AnchorPoint = Vector2.new(0, 0)
		anchors.BottomLeft.Position = UDim2.fromOffset(MARGIN, MARGIN + math.floor(ANCHORS.TopLeft.size.Y * s) + 8)
	else
		anchors.BottomLeft.AnchorPoint = Vector2.new(0, 1)
		anchors.BottomLeft.Position = UDim2.new(0, MARGIN, 1, -MARGIN)
	end
end

-- Toasts --------------------------------------------------------------------------------------------------------------
local MAX_TOASTS = 3
local toastList = Instance.new("UIListLayout")
toastList.FillDirection = Enum.FillDirection.Vertical
toastList.VerticalAlignment = Enum.VerticalAlignment.Bottom
toastList.HorizontalAlignment = Enum.HorizontalAlignment.Right
toastList.SortOrder = Enum.SortOrder.LayoutOrder
toastList.Padding = UDim.new(0, 8)
toastList.Parent = anchors.Toasts

type ToastReq = {title: string, body: string?, kind: string?, icon: string?, duration: number?, key: string?}
type Slot = {card: CanvasGroup, busy: boolean, stamp: number, key: string?}
local slots: {Slot} = {}
for i = 1, MAX_TOASTS do
	local card = C.toastCard({parent = anchors.Toasts, name = "Toast" .. i, size = UDim2.fromOffset(280, 64)}) :: any
	card.Visible = false
	card.GroupTransparency = 1
	table.insert(slots, {card = card, busy = false, stamp = 0})
end
local queue: {ToastReq} = {}
local order = 0
local pump: () -> ()

local function release(slot: Slot, stamp: number)
	if slot.stamp ~= stamp or not slot.busy then
		return
	end
	local tw = C.tween(slot.card, {GroupTransparency = 1}, "normal")
	local function done()
		if slot.stamp == stamp then
			slot.card.Visible = false
			slot.busy = false
			slot.key = nil
			pump()
		end
	end
	if tw then
		tw.Completed:Once(done)
	else
		done()
	end
end

local function showIn(slot: Slot, req: ToastReq)
	order += 1
	slot.busy = true
	slot.key = req.key
	slot.stamp = order
	local stamp = order
	C.setToast(slot.card, req.title, req.body, req.kind, req.icon)
	slot.card.LayoutOrder = order
	if not slot.card.Visible then
		slot.card.GroupTransparency = 1
		slot.card.Visible = true
	end
	C.tween(slot.card, {GroupTransparency = 0}, "normal")
	task.delay(req.duration or 4, release, slot, stamp)
end

pump = function()
	while #queue > 0 do
		local free = nil
		for _, s in slots do
			if not s.busy then
				free = s
				break
			end
		end
		if not free then
			return
		end
		showIn(free, table.remove(queue, 1) :: ToastReq)
	end
end

-- req.key: a toast with the same key that is still on screen is updated in place (near-miss combos) instead of queued
local function toast(req: ToastReq)
	if type(req) ~= "table" or type(req.title) ~= "string" then
		return
	end
	if req.key then
		for _, s in slots do
			if s.busy and s.key == req.key then
				showIn(s, req)
				return
			end
		end
	end
	table.insert(queue, req)
	if #queue > 8 then
		table.remove(queue, 1) -- a burst never builds a minute-long backlog
	end
	pump()
end
Bus.on("toast", function(t)
	if type(t) == "table" then
		toast({title = tostring(t.title or ""), body = t.body and tostring(t.body), kind = t.kind, icon = t.icon,
			duration = tonumber(t.duration), key = t.key})
	end
end)

-- Modal API: Bus "modal.open" ({title, build = function(body) end, width?, height?}) / "modal.close" ------------------
local card = C.panel({parent = modal, name = "Card", anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.5),
	size = UDim2.fromOffset(640, 500), alpha = 0.08, glow = true, accent = true, zIndex = 51})
Responsive.addScale(card)
local cardTitle = C.label({parent = card, name = "Title", text = "", font = "display", textSize = Theme.size.title + 2,
	position = UDim2.fromOffset(24, 14), size = UDim2.new(1, -96, 0, 34), fit = true, minSize = 12})
local closeBtn = C.button({parent = card, name = "Close", text = "X", style = "ghost", textSize = Theme.size.title,
	anchor = Vector2.new(1, 0), position = UDim2.new(1, -12, 0, 10), size = UDim2.fromOffset(44, 44)})
C.divider({parent = card, position = UDim2.fromOffset(20, 60), size = UDim2.new(1, -40, 0, 1)})
local body: Frame? = nil
local modalOpen = false
local prevSelection: GuiObject? = nil

local function closeModal()
	if not modalOpen then
		return
	end
	modalOpen = false
	modal.Visible = false
	if body then
		body:Destroy() -- build() loops end when their body leaves the tree
		body = nil
	end
	ContextActionService:UnbindAction("MidnightModalClose")
	if GuiService.SelectedObject and GuiService.SelectedObject:IsDescendantOf(modal) then
		GuiService.SelectedObject = prevSelection
	end
end

local function openModal(spec: any)
	if type(spec) ~= "table" then
		return
	end
	if body then
		body:Destroy()
	end
	local w = math.clamp(tonumber(spec.width) or 640, 360, 900)
	local h = math.clamp(tonumber(spec.height) or 500, 240, 640)
	card.Size = UDim2.fromOffset(w, h)
	cardTitle.Text = tostring(spec.title or "")
	local b = Instance.new("Frame")
	b.Name = "Body"
	b.BackgroundTransparency = 1
	b.Position = UDim2.fromOffset(24, 72)
	b.Size = UDim2.new(1, -48, 1, -88)
	b.ZIndex = 52
	b.Parent = card
	body = b
	modalOpen = true
	modal.Visible = true
	if type(spec.build) == "function" then
		local ok, err = pcall(spec.build, b)
		if not ok then
			warn("MidnightHUD modal build failed: " .. tostring(err))
		end
	end
	ContextActionService:BindActionAtPriority("MidnightModalClose", function(_, state)
		if state == Enum.UserInputState.Begin then
			closeModal()
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.ContextActionPriority.High.Value, Enum.KeyCode.ButtonB)
	if Responsive.isGamepad() then
		prevSelection = GuiService.SelectedObject
		GuiService.SelectedObject = closeBtn
	end
end
closeBtn.Activated:Connect(closeModal)
Bus.on("modal.open", openModal)
Bus.on("modal.close", closeModal)

-- shared helpers for modal bodies
local function scrollList(parent: Instance, padding: number?): ScrollingFrame
	local sf = Instance.new("ScrollingFrame")
	sf.BackgroundTransparency = 1
	sf.BorderSizePixel = 0
	sf.Size = UDim2.fromScale(1, 1)
	sf.CanvasSize = UDim2.new()
	sf.AutomaticCanvasSize = Enum.AutomaticSize.Y
	sf.ScrollingDirection = Enum.ScrollingDirection.Y
	sf.ScrollBarThickness = 4
	sf.ScrollBarImageColor3 = col.cyan
	sf.ZIndex = 52
	sf.Parent = parent
	local l = Instance.new("UIListLayout")
	l.SortOrder = Enum.SortOrder.LayoutOrder
	l.Padding = UDim.new(0, padding or 8)
	l.Parent = sf
	C.padding(sf, {0, 10, 0, 4})
	return sf
end

-- Player card (TopLeft) ------------------------------------------------------------------------------------------------
local fadeGroups: {CanvasGroup} = {}
local cardPanel = C.panel({parent = anchors.TopLeft, name = "PlayerCard", size = UDim2.fromOffset(380, 112),
	glow = true, accent = true, canvas = true}) :: any
table.insert(fadeGroups, cardPanel)
local avatarFrame = C.panel({parent = cardPanel, name = "Avatar", position = UDim2.fromOffset(12, 12),
	size = UDim2.fromOffset(88, 88), radius = Theme.radius.button, color = col.navy, alpha = 0, gradient = false,
	strokeColor = col.purple})
local avatarInitial = C.label({parent = avatarFrame, text = string.upper(string.sub(player.DisplayName, 1, 1)),
	font = "display", textSize = Theme.size.big, align = "center", color = col.textDim, size = UDim2.fromScale(1, 1)})
local avatar = Instance.new("ImageLabel")
avatar.Name = "Image"
avatar.BackgroundTransparency = 1
avatar.Size = UDim2.fromScale(1, 1)
avatar.Image = ""
avatar.Parent = avatarFrame
C.corner(avatar, Theme.radius.button)
task.spawn(function()
	local ok, img = pcall(function()
		return Players:GetUserThumbnailAsync(player.UserId, Enum.ThumbnailType.HeadShot, Enum.ThumbnailSize.Size150x150)
	end)
	if ok and type(img) == "string" then
		avatar.Image = img
		avatarInitial.Visible = false
	end
end)
local nameLabel = C.label({parent = cardPanel, name = "Name", text = player.DisplayName, font = "display",
	textSize = Theme.size.title + 2, position = UDim2.fromOffset(112, 12), size = UDim2.fromOffset(170, 28),
	fit = true, minSize = 12})
local levelLabel = C.label({parent = cardPanel, name = "Level", text = "", font = "display", rich = true,
	textSize = Theme.size.title + 2, align = "right", anchor = Vector2.new(1, 0), position = UDim2.new(1, -14, 0, 12),
	size = UDim2.fromOffset(86, 28)})
local titleLabel = C.label({parent = cardPanel, name = "Title", text = "", font = "body", textSize = Theme.size.label,
	color = col.textDim, position = UDim2.fromOffset(112, 40), size = UDim2.new(1, -126, 0, 18), fit = true, minSize = 10})
C.label({parent = cardPanel, name = "ExpCaption", text = "EXP", font = "bold", textSize = Theme.size.caption,
	color = col.cyan, position = UDim2.fromOffset(112, 64), size = UDim2.fromOffset(34, 16)})
local expBar = C.bar({parent = cardPanel, name = "ExpBar", position = UDim2.fromOffset(150, 68),
	size = UDim2.new(1, -164, 0, 8)})
local expText = C.label({parent = cardPanel, name = "ExpText", text = "", font = "mono", textSize = Theme.size.caption,
	color = col.textDim, align = "right", anchor = Vector2.new(1, 0), position = UDim2.new(1, -14, 0, 82),
	size = UDim2.new(1, -126, 0, 16)})

local moneyPill = C.pill({parent = anchors.TopLeft, name = "Money", lead = "฿", leadColor = col.green, text = "0",
	textColor = col.green, font = "display", textSize = Theme.size.title + 4, position = UDim2.fromOffset(392, 6),
	size = UDim2.fromOffset(0, 52), autoX = true, stroke = col.line})
local moneyMin = Instance.new("UISizeConstraint")
moneyMin.MinSize = Vector2.new(150, 52)
moneyMin.MaxSize = Vector2.new(208, 52) -- fits up to 9,999,999,999 at 28 px; leaves TopCenter free
moneyMin.Parent = moneyPill
local moneyStroke = moneyPill:FindFirstChildOfClass("UIStroke") :: UIStroke

local function setTitle(t: string)
	titleLabel.Text = t
	titleLabel.Visible = t ~= ""
	nameLabel.Position = if t ~= "" then UDim2.fromOffset(112, 12) else UDim2.fromOffset(112, 22)
end
setTitle("")

-- Quick menu (TopRight) -----------------------------------------------------------------------------------------------
local menuGroup = Instance.new("CanvasGroup") -- fades as one; 6 px padding keeps the gamepad selection ring visible
menuGroup.Name = "QuickMenu"
menuGroup.BackgroundTransparency = 1
menuGroup.AnchorPoint = Vector2.new(1, 0)
menuGroup.Position = UDim2.new(1, 6, 0, -6)
menuGroup.Size = UDim2.new(1, 12, 0, 96)
menuGroup.Parent = anchors.TopRight
table.insert(fadeGroups, menuGroup)
local menuList = Instance.new("UIListLayout")
menuList.FillDirection = Enum.FillDirection.Horizontal
menuList.HorizontalAlignment = Enum.HorizontalAlignment.Right
menuList.VerticalAlignment = Enum.VerticalAlignment.Center
menuList.Padding = UDim.new(0, 8)
menuList.SortOrder = Enum.SortOrder.LayoutOrder
menuList.Parent = menuGroup
C.padding(menuGroup, 6)

-- keyboard shortcuts owned by this HUD (keys no other script binds; I/O are Roblox camera zoom, so not used)
local SHORTCUTS = {missions = Enum.KeyCode.K, events = Enum.KeyCode.L, settings = Enum.KeyCode.U, help = Enum.KeyCode.F1}
local SHORTCUT_TEXT = {map = "M", missions = "K", events = "L", settings = "U", help = "F1"}

local openSettings: () -> ()
local openHelp: () -> ()
local openEventsFallback: () -> ()

local function goToGarageToast()
	toast({title = "GARAGE", body = "ไปที่วงม่วงข้างจุดเกิด แล้วกด E  ·  Go to the purple ring by the spawn, press E",
		kind = "info", icon = "garage"})
end

local MENU = {
	{id = "garage", label = "Garage", icon = "garage", fire = function()
		if Bus.count("garage.open") > 0 then
			Bus.fire("garage.open")
		else
			goToGarageToast()
		end
	end},
	{id = "map", label = "Map", icon = "map", fire = function()
		if Bus.count("map.toggle") > 0 then
			Bus.fire("map.toggle")
		else
			toast({title = "MAP", body = ("Press %s for the city map"):format(InputPrompts.glyph("map") or "M"), kind = "info"})
		end
	end},
	{id = "events", label = "Events", icon = "events", fire = function()
		if Bus.count("events.open") > 0 then
			Bus.fire("events.open")
		else
			openEventsFallback()
		end
	end},
	{id = "missions", label = "Missions", icon = "missions", fire = function()
		if Bus.count("missions.open") > 0 then
			Bus.fire("missions.open")
		else
			toast({title = "MISSIONS", body = "Taxi / Delivery: E ที่วงสีเหลือง / เขียว", kind = "info"})
		end
	end},
	{id = "settings", label = "Settings", icon = "settings", fire = function() Bus.fire("settings.open") end},
	{id = "help", label = "Help", icon = "help", fire = function() Bus.fire("help.open") end},
}
local tiles: {[string]: TextButton} = {}
for i, m in MENU do
	tiles[m.id] = C.iconButton({parent = menuGroup, name = m.id, icon = m.icon, label = m.label,
		hint = SHORTCUT_TEXT[m.id], size = UDim2.fromOffset(88, 84), layoutOrder = i, onClick = m.fire}) -- 88 wide: "Missions" truncated at 76 (leader, first capture)
end
for i, m in MENU do -- gamepad: left/right walks the row, wraps at the ends
	local t = tiles[m.id]
	t.NextSelectionLeft = tiles[MENU[if i == 1 then #MENU else i - 1].id]
	t.NextSelectionRight = tiles[MENU[if i == #MENU then 1 else i + 1].id]
end
menuGroup.SelectionGroup = true

local function refreshHints()
	local kb = Responsive.inputKind() == "keyboard"
	for id, t in tiles do
		local h = t:FindFirstChild("Hint") :: TextLabel?
		if h then
			h.Visible = kb and SHORTCUT_TEXT[id] ~= nil
		end
	end
end

for id, key in SHORTCUTS do
	ContextActionService:BindActionAtPriority("MidnightMenu_" .. id, function(_, state)
		if state == Enum.UserInputState.Begin then
			for _, m in MENU do
				if m.id == id then
					m.fire()
				end
			end
		end
		return Enum.ContextActionResult.Pass
	end, false, Enum.ContextActionPriority.Low.Value, key)
end

-- gamepad Select: hold 0.35 s = focus the quick menu; a short press = the map (forwarded as Bus "map.toggle", which
-- PattayaMinimapClient must listen to per the contract). Bound at High priority over the minimap's own Select bind.
-- When nobody listens to "map.toggle" yet, the press is passed through so the old map key keeps working.
local selectDownAt = 0
local selectOpened = false
local selectSunk = false
ContextActionService:BindActionAtPriority("MidnightQuickMenu", function(_, state)
	if state == Enum.UserInputState.Begin then
		selectDownAt = os.clock()
		selectOpened = false
		local stamp = selectDownAt
		task.delay(0.35, function()
			if selectDownAt == stamp and UserInputService:IsGamepadButtonDown(Enum.UserInputType.Gamepad1,
				Enum.KeyCode.ButtonSelect) then
				selectOpened = true
				if gui.Enabled and anchors.TopRight.Visible then
					GuiService.SelectedObject = tiles.garage
				end
			end
		end)
		selectSunk = Bus.count("map.toggle") > 0
		return if selectSunk then Enum.ContextActionResult.Sink else Enum.ContextActionResult.Pass
	elseif state == Enum.UserInputState.End then
		selectDownAt = 0
		if selectSunk and not selectOpened then
			Bus.fire("map.toggle")
		end
		return if selectSunk then Enum.ContextActionResult.Sink else Enum.ContextActionResult.Pass
	end
	return Enum.ContextActionResult.Pass
end, false, Enum.ContextActionPriority.High.Value, Enum.KeyCode.ButtonSelect)

-- Context chips + job strip (BottomCenter) -----------------------------------------------------------------------------
local chipsRow = Instance.new("Frame")
chipsRow.Name = "ContextBar"
chipsRow.BackgroundTransparency = 1
chipsRow.AnchorPoint = Vector2.new(0.5, 1)
chipsRow.Position = UDim2.fromScale(0.5, 1)
chipsRow.Size = UDim2.new(1, 0, 0, 42)
chipsRow.Parent = anchors.BottomCenter
local chipsList = Instance.new("UIListLayout")
chipsList.FillDirection = Enum.FillDirection.Horizontal
chipsList.HorizontalAlignment = Enum.HorizontalAlignment.Center
chipsList.VerticalAlignment = Enum.VerticalAlignment.Center
chipsList.Padding = UDim.new(0, 10)
chipsList.SortOrder = Enum.SortOrder.LayoutOrder
chipsList.Parent = chipsRow

type Chip = {frame: Frame, key: TextLabel, label: TextLabel}
local chips: {Chip} = {}
for i = 1, 6 do -- pooled: chips are re-texted, never rebuilt
	local f = C.panel({parent = chipsRow, name = "Chip" .. i, size = UDim2.fromOffset(0, 42), radius = Theme.radius.button,
		layoutOrder = i}) :: Frame
	f.AutomaticSize = Enum.AutomaticSize.X
	f.Visible = false
	local l = Instance.new("UIListLayout")
	l.FillDirection = Enum.FillDirection.Horizontal
	l.VerticalAlignment = Enum.VerticalAlignment.Center
	l.Padding = UDim.new(0, 10)
	l.SortOrder = Enum.SortOrder.LayoutOrder
	l.Parent = f
	C.padding(f, {7, 14, 0, 0})
	local keyCap = C.label({parent = f, name = "Key", text = "", font = "display", textSize = Theme.size.label + 1,
		color = col.navy, align = "center", autoX = true, size = UDim2.new(0, 0, 0, 28), layoutOrder = 1})
	keyCap.BackgroundTransparency = 0
	keyCap.BackgroundColor3 = col.text
	keyCap.TextTruncate = Enum.TextTruncate.None
	C.corner(keyCap, Theme.radius.small)
	C.padding(keyCap, {8, 8, 0, 0})
	local keyMin = Instance.new("UISizeConstraint")
	keyMin.MinSize = Vector2.new(28, 28)
	keyMin.Parent = keyCap
	local lab = C.label({parent = f, name = "Label", text = "", font = "bold", textSize = Theme.size.label + 1,
		autoX = true, size = UDim2.new(0, 0, 0, 28), layoutOrder = 2})
	lab.TextTruncate = Enum.TextTruncate.None
	table.insert(chips, {frame = f, key = keyCap, label = lab})
end

local jobStrip = C.pill({parent = anchors.BottomCenter, name = "JobStrip", text = "", textColor = col.yellow,
	anchor = Vector2.new(0.5, 1), position = UDim2.new(0.5, 0, 1, -52), size = UDim2.fromOffset(0, 34), autoX = true,
	stroke = col.yellow, textSize = Theme.size.label})
jobStrip.Visible = false
local jobMax = Instance.new("UISizeConstraint")
jobMax.MaxSize = Vector2.new(620, 34)
jobMax.Parent = jobStrip

-- gameplay state for the chips (all read-only attributes)
local eventState: Instance? = ReplicatedStorage:FindFirstChild("PattayaEvent")
local worldMapModule: Instance? = ReplicatedStorage:FindFirstChild("PattayaWorldMap")
local nearCircuit = false
local seatedInCar = false
local lastChipKey = ""

local function inCar(): boolean
	return player:GetAttribute("HUD_InCar") == true or seatedInCar
end

local function eventGathering(): boolean
	return eventState ~= nil and eventState:GetAttribute("Phase") == "gathering"
		and player:GetAttribute("EventJoined") ~= true
end

local function refreshChips()
	local list = InputPrompts.list({
		inCar = inCar(),
		raceState = player:GetAttribute("RaceState"),
		sprintActive = player:GetAttribute("SprintActive") == true,
		circuitActive = player:GetAttribute("CircuitActive") == true,
		eventActive = player:GetAttribute("EventActive") == true,
		eventGathering = eventGathering(),
		jobActive = player:GetAttribute("JobActive") == true,
		nearCircuit = nearCircuit,
	})
	local parts = {}
	for _, a in list do
		table.insert(parts, a.glyph .. ":" .. a.label)
	end
	local key = table.concat(parts, "|") .. (if Responsive.isTouch() then "#t" else "")
	if key == lastChipKey then
		return
	end
	lastChipKey = key
	for i, chip in chips do
		local a = list[i]
		chip.frame.Visible = a ~= nil
		if a then
			chip.key.Text = a.glyph
			chip.label.Text = a.label
		end
	end
	-- touch: Roblox draws its own action buttons (ContextActionService), so the chips would only cover controls
	chipsRow.Visible = not Responsive.isTouch()
	jobStrip.Position = if chipsRow.Visible and #list > 0 then UDim2.new(0.5, 0, 1, -52) else UDim2.new(0.5, 0, 1, 0)
end

local function refreshJobStrip()
	local t = player:GetAttribute("HUD_JobText")
	jobStrip.Visible = type(t) == "string" and t ~= ""
	if jobStrip.Visible then
		C.setPill(jobStrip, t :: string)
		local urgent = player:GetAttribute("HUD_JobUrgent") == true
		local txt = jobStrip:FindFirstChild("Text") :: TextLabel
		txt.TextColor3 = if urgent then col.red else col.yellow
		local s = jobStrip:FindFirstChildOfClass("UIStroke") :: UIStroke
		s.Color = if urgent then col.red else col.yellow
	end
end

for _, a in {"HUD_InCar", "RaceState", "SprintActive", "CircuitActive", "EventActive", "EventJoined", "JobActive"} do
	player:GetAttributeChangedSignal(a):Connect(refreshChips)
end
player:GetAttributeChangedSignal("HUD_JobText"):Connect(refreshJobStrip)
player:GetAttributeChangedSignal("HUD_JobUrgent"):Connect(refreshJobStrip)

local function hookCharacter(char: Model)
	local hum = char:WaitForChild("Humanoid", 10) :: Humanoid?
	if not hum then
		return
	end
	local function seated(active: boolean, seat: Instance?)
		seatedInCar = active and seat ~= nil and seat:IsA("VehicleSeat") and seat.Parent ~= nil
			and seat.Parent:GetAttribute("RaceCar") ~= nil
		refreshChips()
	end
	hum.Seated:Connect(seated)
	seated(hum.SeatPart ~= nil, hum.SeatPart)
end

-- near a circuit entrance (P CIRCUIT): positions published by CircuitServer as Circuit_<id> attributes; checked at
-- 2 Hz while driving (a distance test, no allocation)
local circuitSpots: {Vector3} = {}
local function readCircuits()
	table.clear(circuitSpots)
	if worldMapModule then
		for name, v in worldMapModule:GetAttributes() do
			if string.sub(name, 1, 8) == "Circuit_" and typeof(v) == "Vector3" then
				table.insert(circuitSpots, v)
			end
		end
	end
end
task.spawn(function()
	worldMapModule = worldMapModule or ReplicatedStorage:WaitForChild("PattayaWorldMap", 60)
	if worldMapModule then
		readCircuits()
		worldMapModule.AttributeChanged:Connect(readCircuits)
	end
end)
task.spawn(function()
	local range = InputPrompts.CIRCUIT_RANGE
	while gui.Parent do
		local near = false
		local char = player.Character
		local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		if root and inCar() then
			local p = root.Position
			for _, v in circuitSpots do
				local dx, dz = v.X - p.X, v.Z - p.Z
				if dx * dx + dz * dz < range * range then
					near = true
					break
				end
			end
		end
		if near ~= nearCircuit then
			nearCircuit = near
			refreshChips()
		end
		task.wait(0.5)
	end
end)

-- Progression (leaderstats) ---------------------------------------------------------------------------------------------
local moneyValue = Instance.new("NumberValue") -- tweened for the count-up; the label follows it
moneyValue.Changed:Connect(function(v)
	C.setPill(moneyPill, commas(v))
end)
local progressReady = false
local lastLevel = 0

local function refreshLevel(ls: Instance)
	local level = (ls:FindFirstChild("Level") :: IntValue?)
	local exp = (ls:FindFirstChild("EXP") :: IntValue?)
	if not (level and exp) then
		return
	end
	local need = expToNext(level.Value)
	levelLabel.Text = ("<font size=\"%d\" color=\"%s\">LV.</font> %d"):format(Theme.size.label, C.hex(col.textDim),
		level.Value)
	expText.Text = ("%s / %s"):format(commas(exp.Value), commas(need))
	C.setBar(expBar, exp.Value / math.max(1, need), progressReady)
end

local function hookStats(ls: Instance)
	local money = ls:WaitForChild("Money", 30) :: IntValue?
	local level = ls:WaitForChild("Level", 30) :: IntValue?
	local exp = ls:WaitForChild("EXP", 30) :: IntValue?
	local title = ls:WaitForChild("Title", 30) :: StringValue?
	if not (money and level and exp) then
		return
	end
	moneyValue.Value = money.Value
	C.setPill(moneyPill, commas(money.Value))
	lastLevel = level.Value
	refreshLevel(ls)
	if title then
		setTitle(title.Value)
		title.Changed:Connect(function()
			setTitle(title.Value)
		end)
	end
	money.Changed:Connect(function()
		local target = money.Value
		if Responsive.reducedMotion() or not progressReady then
			moneyValue.Value = target
		else
			TweenService:Create(moneyValue, TweenInfo.new(0.6, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
				{Value = target}):Play()
			C.tween(moneyStroke, {Color = col.green}, "fast")
			task.delay(0.8, function()
				C.tween(moneyStroke, {Color = col.line}, "slow")
			end)
		end
	end)
	exp.Changed:Connect(function()
		refreshLevel(ls)
	end)
	level.Changed:Connect(function()
		refreshLevel(ls)
		if progressReady and level.Value > lastLevel then
			toast({title = "LEVEL UP!", body = ("Level %d"):format(level.Value), kind = "levelup", duration = 5})
		end
		lastLevel = level.Value
	end)
	-- values set while the saved record loads are not "earned": no count-up / level-up toast until ProgressLoaded
	local function markReady()
		task.delay(1, function()
			progressReady = true
			moneyValue.Value = money.Value
			lastLevel = level.Value
		end)
	end
	if player:GetAttribute("ProgressLoaded") then
		markReady()
	else
		player:GetAttributeChangedSignal("ProgressLoaded"):Once(markReady)
	end
end
task.spawn(function()
	local ls = player:FindFirstChild("leaderstats") or player:WaitForChild("leaderstats", 120)
	if ls then
		hookStats(ls)
	end
end)

-- reward toasts from PattayaProgress.Award: LastReward = "+n ฿  +n EXP  (reason)[  LEVEL UP!]" (the level-up toast
-- comes from the Level leaderstat, so it is not repeated here)
player:GetAttributeChangedSignal("LastRewardAt"):Connect(function()
	local at = tonumber(player:GetAttribute("LastRewardAt")) or 0
	if math.abs(workspace:GetServerTimeNow() - at) > 15 then
		return -- a stale value (e.g. replicated on join) is not news
	end
	local s = tostring(player:GetAttribute("LastReward") or "")
	local money, exp, reason = string.match(s, "^%+(%-?%d+) ฿%s+%+(%-?%d+) EXP%s+%((.-)%)")
	if money then
		toast({title = ("<font color=\"%s\">+%s ฿</font>   <font color=\"%s\">+%s EXP</font>"):format(C.hex(col.green),
			commas(tonumber(money) or 0), C.hex(col.cyan), commas(tonumber(exp) or 0)), body = reason, kind = "reward",
			duration = 5})
	elseif s ~= "" then
		toast({title = s, kind = "reward", duration = 5})
	end
end)

-- garage messages (PattayaGarageServer)
player:GetAttributeChangedSignal("GarageMsgAt"):Connect(function()
	local m = player:GetAttribute("GarageMsg")
	if type(m) == "string" and m ~= "" then
		toast({title = "GARAGE", body = m, kind = "info", icon = "garage"})
	end
end)

-- near misses (PattayaJobsServer): NearMissCombo / NearMissAt; the nitro paid comes on the NitroBonus remote just
-- before the attributes, so a bonus that arrived within 0.5 s belongs to this near miss
local lastBonus, lastBonusAt = 0, -1
local nearAt = -1
local function nearMissToast(bonus: number?)
	local combo = tonumber(player:GetAttribute("NearMissCombo")) or 1
	local title = if combo > 1 then ("NEAR MISS x%d"):format(combo) else "NEAR MISS"
	if bonus and bonus > 0 then
		title ..= ("  <font color=\"%s\">+%d</font>"):format(C.hex(col.green), bonus)
	end
	toast({title = title, body = if bonus and bonus > 0 then "Nitro bonus" else nil, kind = "info", icon = "garage",
		duration = 2.5, key = "nearmiss"})
end
player:GetAttributeChangedSignal("NearMissAt"):Connect(function()
	nearAt = os.clock()
	nearMissToast(if os.clock() - lastBonusAt < 0.5 then lastBonus else nil)
end)
task.spawn(function()
	local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
	local nb = remotes and remotes:WaitForChild("NitroBonus", 60)
	if nb and nb:IsA("RemoteEvent") then
		nb.OnClientEvent:Connect(function(amount)
			lastBonus, lastBonusAt = tonumber(amount) or 0, os.clock()
			if os.clock() - nearAt < 0.5 then
				nearMissToast(lastBonus) -- the attribute won the race: update the card in place
			end
		end)
	end
end)

-- Settings (only options that work; values live as LocalPlayer attributes, this client only) --------------------------
local setHidden: (boolean) -> ()
local restoreBtn = C.iconButton({parent = gui, name = "ShowHUD", icon = "settings", size = UDim2.fromOffset(52, 52),
	anchor = Vector2.new(1, 0), position = UDim2.new(1, -MARGIN, 0, MARGIN), onClick = function()
		Bus.fire("settings.open")
	end})
restoreBtn.Visible = false
restoreBtn.ZIndex = 40

setHidden = function(hidden: boolean)
	for name, f in anchors do
		if name ~= "Toasts" then
			f.Visible = not hidden
		end
	end
	restoreBtn.Visible = hidden
end
player:GetAttributeChangedSignal("HUDHidden"):Connect(function()
	setHidden(player:GetAttribute("HUDHidden") == true)
end)

openSettings = function()
	openModal({title = "SETTINGS", width = 560, height = 520, build = function(b: Frame)
		local list = scrollList(b, 6)
		C.slider({parent = list, layoutOrder = 1, label = "HUD scale", min = Responsive.HUD_SCALE_MIN,
			max = Responsive.HUD_SCALE_MAX, step = 0.05, value = Responsive.hudScale(), format = "%.2fx",
			onChange = function(v)
				player:SetAttribute("HUDScale", v)
			end})
		C.toggle({parent = list, layoutOrder = 2, label = "Reduced motion (no slides, fades or count-ups)",
			value = Responsive.reducedMotion(), onChange = function(v)
				player:SetAttribute("ReducedMotion", v)
			end})
		C.toggle({parent = list, layoutOrder = 3, label = "Show HUD (toasts always show)",
			value = player:GetAttribute("HUDHidden") ~= true, onChange = function(v)
				player:SetAttribute("HUDHidden", not v)
			end})
		if Bus.count("minimap.visible") > 0 then -- only when the minimap listens (ui-map)
			C.toggle({parent = list, layoutOrder = 4, label = "Minimap", value = player:GetAttribute("HUDMinimap") ~= false,
				onChange = function(v)
					player:SetAttribute("HUDMinimap", v)
				end})
		end
		C.label({parent = list, layoutOrder = 5, text = "Settings last for this session (they are kept on your player, "
			.. "not saved to the cloud yet).", font = "body", textSize = Theme.size.caption, color = col.textMuted,
			wrap = true, size = UDim2.new(1, 0, 0, 34)})
		C.button({parent = list, layoutOrder = 6, text = "RESET TO DEFAULTS", style = "ghost",
			size = UDim2.fromOffset(220, 44), onClick = function()
				player:SetAttribute("HUDScale", nil)
				player:SetAttribute("ReducedMotion", nil)
				player:SetAttribute("HUDHidden", nil)
				player:SetAttribute("HUDMinimap", nil)
				closeModal()
				openSettings()
			end})
	end})
end
player:GetAttributeChangedSignal("HUDMinimap"):Connect(function()
	Bus.fire("minimap.visible", player:GetAttribute("HUDMinimap") ~= false)
end)
Bus.on("settings.open", function()
	openSettings()
end)

-- Help / controls (HOW_TO_PLAY_TH.md, Thai + English) ------------------------------------------------------------------
local HELP = {
	{"W A S D", nil, "ขับ", "Drive"},
	{"Shift", "nitro", "ไนตรัส", "Nitro"},
	{"Ctrl", "drift", "ดริฟต์ (เบรกมือ)", "Drift (handbrake)"},
	{"R", "reset", "พลิกรถกลับ", "Flip the car back"},
	{"Space", "exit", "ลงจากรถ", "Get out of the car"},
	{"G", "gps", "GPS: เลือกปลายทาง เส้นสีฟ้าบนถนน + ลูกศรเหนือรถ", "GPS: pick a destination, blue line on the road"},
	{"M", "map", "เปิด/ปิดแผนที่ทั้งเมือง", "Open / close the city map"},
	{"H", "sprint", "Street Sprint: วิ่งจับเวลาผ่านด่านบนถนนจริง", "Street Sprint: timed checkpoints on real roads"},
	{"C", "challenge", "ท้าแข่ง 1v1 กับผู้เล่นใกล้ ๆ (Y รับ / N ปฏิเสธ)", "1v1 challenge a nearby driver (Y accept / N decline)"},
	{"E", "ring", "ที่วงสี: รับงาน Taxi / Delivery, Road Fight, เปิดอู่", "At a ring: taxi / delivery job, Road Fight, garage"},
	{"J", "join", "เข้าร่วม Night Run / Survival เมื่อมีประกาศ", "Join Night Run / Survival when announced"},
	{"P", "circuit", "เมนูสนามแข่ง", "Circuit menu"},
	{"T", "circuitReset", "รีเซ็ตรถกลับด่านล่าสุดบนสนามแข่ง", "Back to the last checkpoint on a circuit"},
	{"Z / X / B", nil, "สลับ/หยุดกล้องผู้ชมในสนาม", "Spectator camera: previous / next / stop"},
	{"K / L / U / F1", "quickMenu", "เมนู: ภารกิจ / อีเวนต์ / ตั้งค่า / วิธีเล่น", "Menu: missions / events / settings / help"},
}
openHelp = function()
	openModal({title = "HOW TO PLAY  ·  วิธีเล่น", width = 760, height = 560, build = function(b: Frame)
		local list = scrollList(b, 4)
		local pad = Responsive.isGamepad()
		for i, row in HELP do
			local r = Instance.new("Frame")
			r.BackgroundTransparency = 1
			r.Size = UDim2.new(1, 0, 0, 40)
			r.LayoutOrder = i
			r.Parent = list
			local keyText = row[1]
			if pad and row[2] then
				local g = InputPrompts.KEYS[row[2]] and InputPrompts.KEYS[row[2]].pad
				if g then
					keyText = g
				end
			end
			C.pill({parent = r, text = keyText, font = "display", textSize = Theme.size.label, color = col.surface2,
				size = UDim2.fromOffset(140, 32), anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5)})
			C.label({parent = r, text = row[3], font = "body", textSize = Theme.size.label, position = UDim2.fromOffset(152, 0),
				size = UDim2.new(1, -152, 0, 20), fit = true, minSize = 10})
			C.label({parent = r, text = row[4], font = "body", textSize = Theme.size.caption, color = col.textDim,
				position = UDim2.fromOffset(152, 20), size = UDim2.new(1, -152, 0, 18), fit = true, minSize = 9})
		end
		C.label({parent = list, layoutOrder = 100, wrap = true, size = UDim2.new(1, 0, 0, 36), font = "body",
			textSize = Theme.size.caption, color = col.textMuted,
			text = "Gamepad: hold SELECT for this menu, tap SELECT for the map, B closes a window."})
	end})
end
Bus.on("help.open", function()
	openHelp()
end)

-- Events fallback (only when no other script handles "events.open"): live state of ReplicatedStorage.PattayaEvent
openEventsFallback = function()
	openModal({title = "EVENTS", width = 560, height = 360, build = function(b: Frame)
		local info = C.label({parent = b, text = "", font = "bold", textSize = Theme.size.body, wrap = true, vAlign = "top",
			size = UDim2.new(1, 0, 0, 120)})
		C.label({parent = b, text = "Night Run / Survival: ประกาศทุก 15 นาที, กด J หรือวิ่งเข้าวงรวมพลเพื่อเข้าร่วม",
			font = "body", textSize = Theme.size.label, color = col.textDim, wrap = true, vAlign = "top",
			position = UDim2.fromOffset(0, 140), size = UDim2.new(1, 0, 0, 60)})
		task.spawn(function()
			while b.Parent do -- 1 Hz text refresh while the window is open
				local st = eventState
				local phase = st and st:GetAttribute("Phase")
				if phase == "gathering" then
					local left = math.max(0, math.ceil((st:GetAttribute("StartAt") or 0) - workspace:GetServerTimeNow()))
					info.Text = ("%s starts in %d:%02d\n%d drivers%s"):format(tostring(st:GetAttribute("Title") or "Event"),
						left // 60, left % 60, st:GetAttribute("Entrants") or 0,
						if player:GetAttribute("EventJoined") then "  ·  you're in!" else "")
				elseif phase == "running" then
					info.Text = ("%s is running  ·  round %d"):format(tostring(st:GetAttribute("Title") or "Event"),
						st:GetAttribute("Round") or 0)
				else
					info.Text = "No event announced right now."
				end
				task.wait(1)
			end
		end)
	end})
end

-- quick-menu badges: Events while an event gathers (and I have not joined), Missions while a job runs
local function refreshBadges()
	C.setBadge(tiles.events, eventGathering())
	C.setBadge(tiles.missions, player:GetAttribute("JobActive") == true)
end
player:GetAttributeChangedSignal("EventJoined"):Connect(refreshBadges)
player:GetAttributeChangedSignal("JobActive"):Connect(refreshBadges)
task.spawn(function()
	eventState = eventState or ReplicatedStorage:WaitForChild("PattayaEvent", 60)
	if eventState then
		eventState:GetAttributeChangedSignal("Phase"):Connect(function()
			refreshBadges()
			refreshChips()
		end)
		refreshBadges()
		refreshChips()
	end
end)

-- HUD fade in on spawn, out on death (CanvasGroups of this HUD only; instant with reduced motion) --------------------
local function fadeTo(alpha: number)
	for _, g in fadeGroups do
		C.tween(g, {GroupTransparency = alpha}, "slow")
	end
end
local function onCharacter(char: Model)
	for _, g in fadeGroups do
		g.GroupTransparency = 1
	end
	fadeTo(0)
	task.spawn(hookCharacter, char)
	local hum = char:WaitForChild("Humanoid", 10) :: Humanoid?
	if hum then
		hum.Died:Connect(function()
			fadeTo(1)
		end)
	end
end
player.CharacterAdded:Connect(onCharacter)

-- Responsive + start --------------------------------------------------------------------------------------------------
gui.Parent = playerGui
Responsive.attach(gui)
layout()
Responsive.onChange(function(reason)
	layout()
	if reason == "input" then
		refreshHints()
		lastChipKey = ""
		refreshChips()
	end
end)
refreshHints()
refreshChips()
refreshJobStrip()
refreshBadges()
setHidden(player:GetAttribute("HUDHidden") == true)
if player:GetAttribute("HUDMinimap") == false then
	Bus.fire("minimap.visible", false)
end
if player.Character then
	task.spawn(onCharacter, player.Character)
end
-- the legacy-hide flag: client-local (LocalPlayer attribute), never replicated world state
player:SetAttribute("MidnightHUD", true)
