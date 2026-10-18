-- Circuit racing HUD and menus (MIDNIGHT PATTAYA). Draws only: all timing and judging is on the server
-- (CircuitServer / RaceSessionService), which publishes Player attributes (Circuit*) and CircuitMsg events.
-- * P (or the CIRCUIT button): session menu at a circuit (practice, time attack, track day, races, private rooms,
--   lap records), travel to a paddock elsewhere. The paddock ProximityPrompt (F) opens the same menu.
-- * T: reset the car to the last checkpoint (invalidates the lap).
-- * HUD: lap x/y, current/last/best lap, PB, position and gap, sector splits (purple = overall best, green =
--   personal best, yellow = slower, red = invalid lap), live timing tower, start lights, results.
-- * Warnings: WRONG WAY, TRACK LIMITS, PIT LANE limiter with your speed, penalties.
-- * Spectating: Z / X switch car, B stop.
-- * Ranked (when the server has it on): RANKED tag on the menu entry and the tower, your rating and the class board in
--   the menu, rating and change per driver on the results screen. The server computes every number.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ProximityPromptService = game:GetService("ProximityPromptService")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
local CircuitRequest = remotes and remotes:WaitForChild("CircuitRequest", 60)
local CircuitMsg = remotes and remotes:WaitForChild("CircuitMsg", 60)
if not (CircuitRequest and CircuitMsg) then
	return -- no circuits in this place
end

local WHITE = Color3.fromRGB(255, 255, 255)
local DIM = Color3.fromRGB(170, 180, 200)
local CYAN = Color3.fromRGB(0, 220, 255)
local PANEL = Color3.fromRGB(12, 12, 20)
local RANKED = Color3.fromRGB(255, 160, 40)
local SPLIT = {
	purple = Color3.fromRGB(175, 70, 255),
	green = Color3.fromRGB(40, 210, 90),
	yellow = Color3.fromRGB(255, 200, 40),
	invalid = Color3.fromRGB(210, 60, 60),
}

local function fmt(t: number?): string
	if not t then
		return "-:--.---"
	end
	return string.format("%d:%06.3f", t // 60, t % 60)
end

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil
-- premium HUD tokens + bus (ReplicatedStorage.MidnightUI), optional: only used while MidnightHUD == true
local uiFolder = ReplicatedStorage:FindFirstChild("MidnightUI")
local themeModule = uiFolder and uiFolder:FindFirstChild("Theme")
local busModule = uiFolder and uiFolder:FindFirstChild("Bus")
local Theme = if themeModule then require(themeModule) :: any else nil
local Bus = if busModule then require(busModule) :: any else nil

local gui = Instance.new("ScreenGui")
gui.Name = "CircuitHUD"
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

local function box(parent: Instance, pos: UDim2, size: UDim2, color: Color3?, transparency: number?): Frame
	local f = Instance.new("Frame")
	f.Position = pos
	f.Size = size
	f.BackgroundColor3 = color or PANEL
	f.BackgroundTransparency = transparency or 0.3
	f.BorderSizePixel = 0
	f.Parent = parent
	Instance.new("UICorner", f).CornerRadius = UDim.new(0, 8)
	return f
end

local function text(parent: Instance, pos: UDim2, size: UDim2, str: string, color: Color3?, font: Enum.Font?, align: Enum.TextXAlignment?): TextLabel
	local t = Instance.new("TextLabel")
	t.Position = pos
	t.Size = size
	t.BackgroundTransparency = 1
	t.Font = font or Enum.Font.GothamBold
	t.TextScaled = true
	t.TextColor3 = color or WHITE
	t.TextXAlignment = align or Enum.TextXAlignment.Left
	t.Text = str
	t.Parent = parent
	return t
end

-- HUD panel (top left, under the Roblox menu buttons) ------------------------------------------------------------------
local hud = box(gui, UDim2.fromOffset(16, 64), UDim2.fromOffset(300, 196))
hud.Visible = false
local hudTitle = text(hud, UDim2.fromOffset(10, 6), UDim2.new(1, -20, 0, 16), "MIDNIGHT PATTAYA", CYAN, Enum.Font.GothamBlack)
local lapLine = text(hud, UDim2.fromOffset(10, 26), UDim2.new(1, -20, 0, 30), "LAP 0/0", WHITE, Enum.Font.GothamBlack)
local curLine = text(hud, UDim2.fromOffset(10, 60), UDim2.new(1, -20, 0, 26), "", WHITE, Enum.Font.Code)
local lastLine = text(hud, UDim2.fromOffset(10, 88), UDim2.new(1, -20, 0, 18), "", DIM, Enum.Font.Code)
local bestLine = text(hud, UDim2.fromOffset(10, 108), UDim2.new(1, -20, 0, 18), "", DIM, Enum.Font.Code)
local posLine = text(hud, UDim2.fromOffset(10, 130), UDim2.new(1, -20, 0, 22), "", WHITE, Enum.Font.GothamBold)
local sectorBoxes = {}
for k = 1, 3 do
	local b = box(hud, UDim2.fromOffset(10 + (k - 1) * 95, 158), UDim2.fromOffset(90, 30), Color3.fromRGB(40, 40, 50), 0.2)
	local t = text(b, UDim2.fromOffset(4, 3), UDim2.new(1, -8, 1, -6), "S" .. k, DIM, Enum.Font.Code, Enum.TextXAlignment.Center)
	sectorBoxes[k] = {frame = b, label = t}
end
local function clearSectors(from: number)
	for k = from, 3 do
		sectorBoxes[k].frame.BackgroundColor3 = Color3.fromRGB(40, 40, 50)
		sectorBoxes[k].label.Text = "S" .. k
		sectorBoxes[k].label.TextColor3 = DIM
	end
end

-- timing tower (under the HUD)
local tower = box(gui, UDim2.fromOffset(16, 268), UDim2.fromOffset(300, 20))
tower.Visible = false
local towerLines = {}
for i = 1, 12 do
	towerLines[i] = text(tower, UDim2.fromOffset(8, 4 + (i - 1) * 18), UDim2.new(1, -16, 0, 16), "", WHITE, Enum.Font.Code)
	towerLines[i].TextScaled = false
	towerLines[i].TextSize = 14
end

-- centre messages
local warnLabel = text(gui, UDim2.new(0.5, -300, 0.24, 0), UDim2.fromOffset(600, 46), "", SPLIT.invalid, Enum.Font.GothamBlack, Enum.TextXAlignment.Center)
warnLabel.TextStrokeTransparency = 0.2
local stateLabel = text(gui, UDim2.new(0.5, -300, 0.31, 0), UDim2.fromOffset(600, 30), "", WHITE, Enum.Font.GothamBlack, Enum.TextXAlignment.Center)
stateLabel.TextStrokeTransparency = 0.3
local toastLabel = text(gui, UDim2.new(0.5, -320, 0.37, 0), UDim2.fromOffset(640, 30), "", WHITE, Enum.Font.GothamBold, Enum.TextXAlignment.Center)
toastLabel.TextStrokeTransparency = 0.3
local flashLabel = text(gui, UDim2.new(0.5, -260, 0.17, 0), UDim2.fromOffset(520, 44), "", WHITE, Enum.Font.GothamBlack, Enum.TextXAlignment.Center)
flashLabel.TextStrokeTransparency = 0.2

local function timed(label: TextLabel, str: string, color: Color3?, seconds: number)
	label.Text = str
	if color then label.TextColor3 = color end
	local stamp = os.clock()
	label:SetAttribute("Stamp", stamp)
	task.delay(seconds, function()
		if label:GetAttribute("Stamp") == stamp then label.Text = "" end
	end)
end

-- start lights
local lights = box(gui, UDim2.new(0.5, -170, 0, 70), UDim2.fromOffset(340, 80), Color3.fromRGB(5, 5, 8), 0.1)
lights.Visible = false
local bulbs = {}
for k = 1, 5 do
	local b = Instance.new("Frame")
	b.Position = UDim2.fromOffset(14 + (k - 1) * 64, 12)
	b.Size = UDim2.fromOffset(56, 56)
	b.BackgroundColor3 = Color3.fromRGB(45, 10, 10)
	b.BorderSizePixel = 0
	b.Parent = lights
	Instance.new("UICorner", b).CornerRadius = UDim.new(1, 0)
	bulbs[k] = b
end
local lightsInfo = nil -- {at, interval, count, outAt}

-- results
local results = box(gui, UDim2.new(0.5, -330, 0.5, -205), UDim2.fromOffset(660, 410), PANEL, 0.08)
results.Visible = false
local resultsTitle = text(results, UDim2.fromOffset(16, 10), UDim2.new(1, -32, 0, 30), "RESULTS", CYAN, Enum.Font.GothamBlack, Enum.TextXAlignment.Center)
local resultLines = {}
for i = 1, 13 do
	resultLines[i] = text(results, UDim2.fromOffset(16, 48 + (i - 1) * 24), UDim2.new(1, -32, 0, 20), "", WHITE, Enum.Font.Code)
	resultLines[i].TextScaled = false
	resultLines[i].TextSize = 15
end
-- ranked: your rating, or why the race did not count
local rankLine = text(results, UDim2.fromOffset(16, 376), UDim2.new(1, -32, 0, 22), "", RANKED, Enum.Font.GothamBlack, Enum.TextXAlignment.Center)

-- spectator bar
local specBar = box(gui, UDim2.new(0.5, -250, 1, -120), UDim2.fromOffset(500, 34))
specBar.Visible = false
local specLabel = text(specBar, UDim2.fromOffset(10, 6), UDim2.new(1, -20, 1, -12), "", WHITE, Enum.Font.GothamBold, Enum.TextXAlignment.Center)

-- menu -------------------------------------------------------------------------------------------------------------------
local menu = box(gui, UDim2.new(0.5, -230, 0.5, -230), UDim2.fromOffset(460, 460), PANEL, 0.05)
menu.Visible = false
text(menu, UDim2.fromOffset(16, 10), UDim2.new(1, -60, 0, 24), "MIDNIGHT PATTAYA  CIRCUITS", CYAN, Enum.Font.GothamBlack)
local closeBtn = Instance.new("TextButton")
closeBtn.Position = UDim2.new(1, -40, 0, 8)
closeBtn.Size = UDim2.fromOffset(30, 30)
closeBtn.BackgroundColor3 = Color3.fromRGB(60, 20, 30)
closeBtn.TextColor3 = WHITE
closeBtn.Font = Enum.Font.GothamBlack
closeBtn.TextSize = 18
closeBtn.Text = "X"
closeBtn.Parent = menu
Instance.new("UICorner", closeBtn).CornerRadius = UDim.new(0, 6)
local scroll = Instance.new("ScrollingFrame")
scroll.Position = UDim2.fromOffset(12, 44)
scroll.Size = UDim2.new(1, -24, 1, -56)
scroll.BackgroundTransparency = 1
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 6
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.CanvasSize = UDim2.new()
scroll.Parent = menu
local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 6)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = scroll

if Style then
	Style.accent(hud, 8)
	Style.accent(results, 8)
	Style.wordmark(results)
	Style.accent(menu, 8)
	Style.accent(specBar, 8)
end

-- Legacy hide (docs/UI_CONTRACT.md, docs/UI_RACE_HUD.md): while LocalPlayer attribute MidnightHUD == true (set locally
-- by ui-core) the new MidnightActivity strip draws lap / time / last / best / position / sectors, the start lights, GO,
-- lap flashes, warnings and the state line, so the top-left HUD panel and those centre labels move into a
-- container that hides. The timing tower, toasts, results screen, spectator bar and menu stay as they are. Everything keeps updating underneath and the
-- attribute going false shows it again; remotes, bindings and world effects are unchanged.
local legacy = Instance.new("Frame")
legacy.Name = "LegacyHidden"
legacy.BackgroundTransparency = 1
legacy.Size = UDim2.fromScale(1, 1)
legacy.ZIndex = 0 -- under the results screen and the menu, as these elements were before
legacy.Parent = gui
for _, g in {hud, lights, warnLabel, stateLabel, flashLabel} do
	g.Parent = legacy
end
local function applyLegacyHide()
	legacy.Visible = player:GetAttribute("MidnightHUD") ~= true
end
player:GetAttributeChangedSignal("MidnightHUD"):Connect(applyLegacyHide)
applyLegacyHide()
gui.Parent = player:WaitForChild("PlayerGui")

-- timing tower under the premium HUD (owner fix): while MidnightHUD == true it sits 8 px under the player card
-- (TopLeft anchor), scaled with the HUD, in Theme colours and fonts. Compact / touch layout (MidnightHUD gui attribute
-- Compact, docs/UI_SYSTEM.md "Touch layout"): under the minimap card instead, with only as many rows as fit above
-- the thumbstick zone (bottom 100 px), at least 3. MidnightHUD false = the old look and place at (16, 268).
local towerRows = 12
local towerScale = Instance.new("UIScale")
towerScale.Parent = tower
local towerStroke = Instance.new("UIStroke")
towerStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
towerStroke.Enabled = false
towerStroke.Parent = tower
local function hudAnchor(name: string): GuiObject?
	local hudGui = player:FindFirstChildOfClass("PlayerGui") and player.PlayerGui:FindFirstChild("MidnightHUD")
	local a = hudGui and hudGui:FindFirstChild(name)
	return if a and a:IsA("GuiObject") then a else nil
end
local function placeTower()
	local styled = player:GetAttribute("MidnightHUD") == true and Theme ~= nil
	local topLeft = if styled then hudAnchor("TopLeft") else nil
	local hudGui = topLeft and topLeft:FindFirstAncestorWhichIsA("ScreenGui")
	local small = hudGui ~= nil and hudGui:GetAttribute("Compact") == true
	local a: GuiObject? = topLeft
	if small then
		local bl = hudAnchor("BottomLeft")
		local mc = bl and bl:FindFirstChild("MinimapCard")
		if mc and mc:IsA("GuiObject") and mc.Visible then
			a = mc
		end
	end
	towerRows = 12
	if styled and a and topLeft then
		local sc = topLeft:FindFirstChildOfClass("UIScale")
		local s = if sc then sc.Scale else 1
		towerScale.Scale = s
		local pos = a.AbsolutePosition - gui.AbsolutePosition -- the HUD's space -> this ScreenGui's space
		local top = pos.Y + a.AbsoluteSize.Y + 8
		tower.AnchorPoint = Vector2.new(0, 0)
		tower.Position = UDim2.fromOffset(pos.X, top)
		if small and hudGui then
			local avail = (hudGui.AbsoluteSize.Y - 100) - top
			towerRows = math.clamp(math.floor((avail / s - 8) / 18), 3, 12)
		end
		tower.BackgroundColor3 = Theme.color.surface
		tower.BackgroundTransparency = Theme.alpha.panel
		towerStroke.Enabled = true
		towerStroke.Color = Theme.color.line
		towerStroke.Thickness = Theme.stroke.thin
		towerStroke.Transparency = 0.2
		for _, l in towerLines do
			l.Font = Theme.font.mono
			l.TextSize = Theme.size.caption + 1
		end
	else
		towerScale.Scale = 1
		tower.AnchorPoint = Vector2.new(0, 0)
		tower.Position = UDim2.fromOffset(16, 268)
		tower.BackgroundColor3 = PANEL
		tower.BackgroundTransparency = 0.3
		towerStroke.Enabled = false
		for _, l in towerLines do
			l.Font = Enum.Font.Code
			l.TextSize = 14
		end
	end
end
player:GetAttributeChangedSignal("MidnightHUD"):Connect(placeTower)
placeTower()

-- menu options remembered between openings
local opt = {laps = 3, gridBy = "join", collisions = true, classIndex = 0, timing = true}
local lastInfo = nil
local order = 0

local function clearMenu()
	for _, c in scroll:GetChildren() do
		if c:IsA("GuiObject") then c:Destroy() end
	end
	order = 0
end

local function row(str: string, color: Color3?, height: number?): TextLabel
	order += 1
	local t = text(scroll, UDim2.new(), UDim2.new(1, -10, 0, height or 20), str, color or DIM, Enum.Font.GothamBold)
	t.TextScaled = false
	t.TextSize = 15
	t.TextWrapped = true
	t.LayoutOrder = order
	return t
end

local function button(str: string, color: Color3?, onClick: () -> ())
	order += 1
	local b = Instance.new("TextButton")
	b.Size = UDim2.new(1, -10, 0, 34)
	b.BackgroundColor3 = color or Color3.fromRGB(0, 90, 120)
	b.TextColor3 = WHITE
	b.Font = Enum.Font.GothamBold
	b.TextSize = 16
	b.Text = str
	b.AutoButtonColor = true
	b.LayoutOrder = order
	b.Parent = scroll
	Instance.new("UICorner", b).CornerRadius = UDim.new(0, 6)
	b.Activated:Connect(onClick)
	return b
end

local render -- forward

local function classesOpt()
	if opt.classIndex == 0 then
		return nil
	end
	local classes = lastInfo and lastInfo.classes or {}
	return {classes[opt.classIndex]}
end

local function request(action: string, a, b)
	CircuitRequest:FireServer(action, a, b)
end

render = function(info)
	lastInfo = info
	clearMenu()
	if info.session then
		local s = info.session
		row(("In session: %s - %s (%s)"):format(s.name, s.mode, s.state), WHITE)
		if s.owner and s.private and s.state == "Forming" then
			button("START RACE", Color3.fromRGB(0, 140, 60), function()
				request("start")
				menu.Visible = false
			end)
			row("Invite drivers on this server:")
			for _, p in info.invitable or {} do
				button("Invite " .. p.name, Color3.fromRGB(60, 60, 100), function() request("invite", p.userId) end)
			end
		end
		button("Leave session", Color3.fromRGB(130, 30, 40), function() request("leave") end)
		return
	end
	if info.spectating then
		button("Stop spectating", Color3.fromRGB(130, 30, 40), function()
			request("unspectate")
			menu.Visible = false
		end)
	end
	if not info.at then
		row("You are not at a circuit. Travel to a paddock:", WHITE)
		if not info.inCar then
			row("Get in a car first.", SPLIT.invalid)
		end
		for _, c in info.circuits do
			button(("Travel: %s  (%d studs)"):format(c.name, c.length), nil, function()
				request("travel", c.id)
				menu.Visible = false
			end)
		end
		return
	end
	local at = info.at
	row(("%s  -  %d studs  -  your best %s"):format(at.name, at.length, fmt(info.pb)), WHITE)
	if not info.inCar then
		row("Get in a car to drive.", SPLIT.invalid)
	end
	-- open track
	row("OPEN TRACK", CYAN)
	if info.open then
		button(("Join %s  (%d on track)"):format(info.open.mode, info.open.count), nil, function()
			request("join", {mode = info.open.mode, circuit = at.id})
			menu.Visible = false
		end)
		button("Spectate the open session", Color3.fromRGB(50, 50, 70), function()
			request("spectate", at.id)
			menu.Visible = false
		end)
	else
		local locked = info.formal and info.formal.state ~= "Forming"
		if locked then
			row("A race is running - the open track is closed.")
		else
			button("Time Attack  (ghost cars, records)", nil, function()
				request("join", {mode = "TimeAttack", circuit = at.id})
				menu.Visible = false
			end)
			button(("Free Practice  (timing %s)"):format(if opt.timing then "on" else "off"), nil, function()
				request("join", {mode = "FreePractice", circuit = at.id, timing = opt.timing})
				menu.Visible = false
			end)
			button("Practice timing: toggle", Color3.fromRGB(50, 50, 70), function()
				opt.timing = not opt.timing
				render(lastInfo)
			end)
			button("Track Day  (collisions on, everyone timed)", nil, function()
				request("join", {mode = "TrackDay", circuit = at.id})
				menu.Visible = false
			end)
		end
	end
	-- races
	row("RACES", CYAN)
	local rk = info.ranked
	if rk then
		row(("RANKED ON  -  %s  -  your %s rating %s%s"):format(rk.season, string.upper(rk.bucket),
			if rk.rating then tostring(rk.rating) else "-",
			if rk.provisional then ("  (PROVISIONAL %d/%d)"):format(rk.races or 0, rk.provisionalRaces) else ""), RANKED, 40)
	end
	local f = info.formal
	if f then
		local classes = if f.classes then table.concat(f.classes, ", ") else "all classes"
		local tag = if f.ranked and f.rankedOk then "[RANKED] " elseif f.ranked then "[UNRANKED: too few laps] " else ""
		row(("%s%s%s: %s, %d laps, %d drivers, %s, collisions %s"):format(tag, f.mode,
			if f.owner then " of " .. f.owner else "", f.state, f.laps, f.count, classes,
			if f.collisions then "on" else "off"), if f.ranked then RANKED else WHITE, 40)
		if f.canJoin then
			button(("Join race%s"):format(if f.formLeft and not f.private then (" (starts in %d s)"):format(f.formLeft) else ""),
				Color3.fromRGB(0, 140, 60), function()
				request("join", {mode = f.mode, circuit = at.id, join = true})
				menu.Visible = false
			end)
		elseif f.state ~= "Forming" then
			button("Spectate the race", Color3.fromRGB(50, 50, 70), function()
				request("spectate", at.id)
				menu.Visible = false
			end)
		end
	else
		row(("Laps: %d     Grid: %s     Class: %s     Collisions: %s"):format(opt.laps,
			if opt.gridBy == "pb" then "by PB" else "join order",
			if opt.classIndex == 0 then "all" else info.classes[opt.classIndex],
			if opt.collisions then "on" else "off"), WHITE)
		for _, n in {3, 5, 10} do
			button(("Laps: %d"):format(n), Color3.fromRGB(50, 50, 70), function()
				opt.laps = n
				render(lastInfo)
			end)
		end
		button("Laps -1 / custom", Color3.fromRGB(50, 50, 70), function()
			opt.laps = math.max(1, opt.laps - 1)
			render(lastInfo)
		end)
		button("Laps +1 / custom", Color3.fromRGB(50, 50, 70), function()
			opt.laps = math.min(20, opt.laps + 1)
			render(lastInfo)
		end)
		button("Grid order: toggle join order / personal best", Color3.fromRGB(50, 50, 70), function()
			opt.gridBy = if opt.gridBy == "pb" then "join" else "pb"
			render(lastInfo)
		end)
		local rankedTag = ""
		if rk then
			rankedTag = if opt.laps >= rk.minLaps then "  RANKED" else ("  unranked: %d+ laps"):format(rk.minLaps)
		end
		button(("Start a public race (%d laps, forms 25 s)%s"):format(opt.laps, rankedTag), Color3.fromRGB(0, 140, 60), function()
			request("join", {mode = "CircuitRace", circuit = at.id, laps = opt.laps, gridBy = opt.gridBy})
			menu.Visible = false
		end)
		row("Private room options:", DIM)
		button("Private: collisions on/off", Color3.fromRGB(50, 50, 70), function()
			opt.collisions = not opt.collisions
			render(lastInfo)
		end)
		button("Private: allowed class (cycle)", Color3.fromRGB(50, 50, 70), function()
			opt.classIndex = (opt.classIndex + 1) % (#info.classes + 1)
			render(lastInfo)
		end)
		button("Create private room", Color3.fromRGB(90, 40, 140), function()
			request("join", {mode = "PrivateRoom", circuit = at.id, laps = opt.laps, gridBy = opt.gridBy,
				collisions = opt.collisions, classes = classesOpt()})
		end)
	end
	-- records
	row("LAP RECORDS", CYAN)
	if info.top and #info.top > 0 then
		for i, r in info.top do
			row(("%d. %s  %s"):format(i, fmt(r.time), r.name), WHITE)
		end
	else
		row("No laps yet - set the first one in Time Attack.")
	end
	button("Friends board", Color3.fromRGB(50, 50, 70), function()
		request("friends", at.id)
	end)
	if rk then
		row(("RANKED BOARD  -  %s  -  %s"):format(string.upper(rk.bucket), rk.season), RANKED)
		if rk.top and #rk.top > 0 then
			for i, r in rk.top do
				row(("%d. %d  %s%s"):format(i, r.rating, r.name, if r.provisional then "  (P)" else ""), WHITE)
			end
			row(("(P) = provisional: fewer than %d ranked races"):format(rk.provisionalRaces))
		else
			row("No ranked results yet in this class.")
		end
	end
end

closeBtn.Activated:Connect(function()
	menu.Visible = false
end)

-- the menu opens only when the player asked for it (owner fix: a join through the CircuitRequest remote, e.g. the
-- test kit, or the server's menu refresh after join/leave made it pop up over the HUD): P / the CIRCUIT button,
-- the paddock ProximityPrompt (F) or Bus "circuit.open". Any other "menu" message only refreshes the content.
local menuAskedAt = -math.huge
local function askMenu()
	menuAskedAt = os.clock()
	request("menu")
end
local function toggleMenu()
	if menu.Visible then
		menu.Visible = false
	else
		askMenu()
	end
end
ProximityPromptService.PromptTriggered:Connect(function(prompt, plr)
	if plr ~= player then
		return
	end
	local m = prompt:FindFirstAncestorWhichIsA("Model")
	if m and string.sub(m.Name, 1, 8) == "Paddock_" then
		menuAskedAt = os.clock() -- the server answers this prompt with "menu" itself
	end
end)
if Bus then
	Bus.on("circuit.open", function()
		if not menu.Visible then
			askMenu()
		end
	end)
end

ContextActionService:BindAction("CircuitMenu", function(_, state)
	if state == Enum.UserInputState.Begin then toggleMenu() end
	return Enum.ContextActionResult.Pass
end, true, Enum.KeyCode.P)
ContextActionService:SetTitle("CircuitMenu", "CIRCUIT")
ContextActionService:SetPosition("CircuitMenu", UDim2.new(1, -200, 1, -290))

ContextActionService:BindAction("CircuitReset", function(_, state)
	if state == Enum.UserInputState.Begin and player:GetAttribute("CircuitActive") then
		request("reset")
	end
	return Enum.ContextActionResult.Pass
end, false, Enum.KeyCode.T, Enum.KeyCode.DPadDown)

-- spectating -------------------------------------------------------------------------------------------------------
local spec = nil -- {targets, index, circuit, name}
local function chassisOf(userId: number): BasePart?
	local p = Players:GetPlayerByUserId(userId)
	local hum = p and p.Character and p.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	return seat and seat.Parent and (seat.Parent :: Model).PrimaryPart or nil
end

local function stopSpectating()
	spec = nil
	specBar.Visible = false
	ContextActionService:UnbindAction("CircuitSpecPrev")
	ContextActionService:UnbindAction("CircuitSpecNext")
	ContextActionService:UnbindAction("CircuitSpecStop")
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	if hum then
		workspace.CurrentCamera.CameraSubject = hum
	end
end

local function cycle(d: number)
	if not spec or #spec.targets == 0 then
		return
	end
	spec.index = (spec.index - 1 + d) % #spec.targets + 1
	request("spectate", spec.circuit, spec.targets[spec.index])
end

local function startSpectating(info)
	local keep = spec
	spec = {targets = info.targets, circuit = info.circuit, name = info.name, index = 1}
	for i, id in info.targets do
		if id == info.target then spec.index = i end
	end
	specBar.Visible = true
	if not keep then
		ContextActionService:BindAction("CircuitSpecPrev", function(_, s)
			if s == Enum.UserInputState.Begin then cycle(-1) end
			return Enum.ContextActionResult.Sink
		end, false, Enum.KeyCode.Z, Enum.KeyCode.DPadLeft)
		ContextActionService:BindAction("CircuitSpecNext", function(_, s)
			if s == Enum.UserInputState.Begin then cycle(1) end
			return Enum.ContextActionResult.Sink
		end, false, Enum.KeyCode.X, Enum.KeyCode.DPadRight)
		ContextActionService:BindAction("CircuitSpecStop", function(_, s)
			if s == Enum.UserInputState.Begin then request("unspectate") end
			return Enum.ContextActionResult.Sink
		end, false, Enum.KeyCode.B)
	end
end

-- server messages --------------------------------------------------------------------------------------------------
CircuitMsg.OnClientEvent:Connect(function(kind, payload)
	if kind == "menu" then
		render(payload)
		if os.clock() - menuAskedAt < 5 then -- asked for (P / prompt / Bus); else a silent refresh
			menuAskedAt = -math.huge
			menu.Visible = true
		end
	elseif kind == "toast" then
		timed(toastLabel, tostring(payload), WHITE, 4)
	elseif kind == "warn" then
		local color = if payload.kind == "pit" then CYAN elseif payload.kind == "limits" then SPLIT.yellow else SPLIT.invalid
		timed(toastLabel, payload.text, color, 3.5)
	elseif kind == "sector" then
		if payload.n == 1 then clearSectors(2) end
		local b = sectorBoxes[payload.n]
		if b then
			b.frame.BackgroundColor3 = SPLIT[payload.colour] or SPLIT.yellow
			b.label.Text = string.format("%.3f", payload.time)
			b.label.TextColor3 = WHITE
		end
	elseif kind == "lap" then
		local color = SPLIT[payload.colour] or WHITE
		local note = if not payload.valid then "  INVALID" elseif payload.pb then "  PERSONAL BEST" else ""
		timed(flashLabel, ("LAP %d  %s%s"):format(payload.lap, fmt(payload.time), note), color, 4)
	elseif kind == "lights" then
		lightsInfo = {at = payload.at, interval = payload.interval, count = payload.count}
		lights.Visible = true
	elseif kind == "lightsOut" then
		if lightsInfo then lightsInfo.outAt = payload.at end
		timed(flashLabel, "GO!", SPLIT.green, 1.5)
		task.delay(1.2, function()
			lightsInfo = nil
			lights.Visible = false
		end)
	elseif kind == "tower" then
		local rows = payload.rows or {}
		local head = if payload.ranked then 1 else 0 -- a RANKED header line takes the first row
		placeTower() -- position + rows that fit (compact)
		tower.Size = UDim2.fromOffset(300, 8 + (math.min(#rows, towerRows - head) + head) * 18)
		for i = 1, 12 do
			local r = if i <= towerRows then rows[i - head] else nil
			towerLines[i].TextColor3 = if Theme and player:GetAttribute("MidnightHUD") == true then Theme.color.text else WHITE
			if head == 1 and i == 1 then
				towerLines[i].Text = "RANKED RACE"
				towerLines[i].TextColor3 = RANKED
			elseif r then
				if payload.mode == "CircuitRace" or payload.mode == "PrivateRoom" then
					towerLines[i].Text = ("%2d %-14s L%d %s %s"):format(r.pos, string.sub(r.name, 1, 14), r.lap, r.gap, r.status)
				else
					towerLines[i].Text = ("%2d %-14s %s %s"):format(r.pos, string.sub(r.name, 1, 14), fmt(r.best), r.status)
				end
			else
				towerLines[i].Text = ""
			end
		end
		tower:SetAttribute("Until", os.clock() + 3)
	elseif kind == "results" then
		local ranked = payload.ranked == true
		resultsTitle.Text = ("%s  -  %s  -  %d laps%s"):format(payload.name, payload.mode, payload.laps,
			if ranked then "  -  RANKED " .. string.upper(payload.bucket or "") else "")
		-- ranked rows carry the rating column, so the name is shorter and the text a little smaller
		local nameW = if ranked then 13 else 15
		resultLines[1].Text = if ranked then "POS DRIVER        TIME       PEN  BEST LAP   REWARD          RATING"
			else "POS DRIVER          TIME       PEN  BEST LAP   REWARD"
		resultLines[1].TextColor3 = DIM
		local mine = nil
		for i = 1, 13 do
			resultLines[i].TextSize = if ranked then 14 else 15
		end
		for i = 2, 13 do
			local r = payload.rows[i - 1]
			if r then
				local reward = if r.money or r.exp then ("+%d B +%d EXP"):format(r.money or 0, r.exp or 0) else ""
				local line = ("%-3s %-" .. nameW .. "s %-10s %-4s %-10s %s"):format(if r.status == "FIN" then tostring(r.pos) else "DNF",
					string.sub(r.name, 1, nameW), if r.time then fmt(r.time) else "-", if r.penalty > 0 then "+" .. r.penalty else "",
					fmt(r.best), reward)
				if ranked and r.rating then
					line = ("%-60s %d (%+d)%s"):format(line, r.rating, r.ratingDelta or 0, if r.provisional then " P" else "")
				end
				resultLines[i].Text = line
				resultLines[i].TextColor3 = if r.userId == player.UserId then SPLIT.yellow else WHITE
				if r.userId == player.UserId then mine = r end
			else
				resultLines[i].Text = ""
			end
		end
		if ranked and mine and mine.rating then
			rankLine.Text = ("YOUR %s RATING  %d  (%+d)%s%s"):format(string.upper(mine.bucket or payload.bucket or ""),
				mine.rating, mine.ratingDelta or 0,
				if mine.provisional then ("   PROVISIONAL %d/%d"):format(mine.ratedRaces or 0, payload.provisionalRaces or 5) else "",
				if mine.ratingSaved then "" else "   (not saved)")
		elseif ranked then
			rankLine.Text = "RANKED RACE  -  " .. string.upper(payload.bucket or "")
		elseif payload.unranked then
			rankLine.Text = "UNRANKED  -  " .. tostring(payload.unranked)
		else
			rankLine.Text = ""
		end
		results.Visible = true
		task.delay(12, function() results.Visible = false end)
	elseif kind == "spectate" then
		if payload then
			startSpectating(payload)
		else
			stopSpectating()
		end
	elseif kind == "invite" then
		timed(toastLabel, ("%s invited you to a private room at %s (%d laps). Go to its paddock and press P."):format(
			payload.from, payload.name, payload.laps), SPLIT.purple, 8)
	elseif kind == "friends" then
		if menu.Visible then
			row("FRIENDS", CYAN)
			if #payload.rows == 0 then
				row("No friends' laps found (global top 100 + this server).")
			end
			for i, r in payload.rows do
				row(("%d. %s  %s"):format(i, fmt(r.time), r.name), WHITE)
			end
		end
	end
end)

results.InputBegan:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		results.Visible = false
	end
end)

-- per frame ----------------------------------------------------------------------------------------------------------
local function mySpeed(): number
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat then
		local v = seat.AssemblyLinearVelocity
		return Vector3.new(v.X, 0, v.Z).Magnitude
	end
	return 0
end

RunService.RenderStepped:Connect(function()
	local now = workspace:GetServerTimeNow()
	local active = player:GetAttribute("CircuitActive") == true
	hud.Visible = active
	tower.Visible = (active or spec ~= nil) and (tower:GetAttribute("Until") or 0) > os.clock()
	-- start lights
	if lightsInfo then
		local lit = math.clamp(math.floor((now - lightsInfo.at) / lightsInfo.interval) + 1, 0, lightsInfo.count)
		if lightsInfo.outAt and now >= lightsInfo.outAt then
			lit = 0
		end
		for k, b in bulbs do
			b.BackgroundColor3 = if k <= lit then Color3.fromRGB(255, 25, 25) else Color3.fromRGB(45, 10, 10)
		end
	end
	-- spectator label
	if spec then
		local id = spec.targets[spec.index]
		local target = id and Players:GetPlayerByUserId(id)
		local chassis = id and chassisOf(id)
		if chassis and workspace.CurrentCamera.CameraSubject ~= chassis then
			workspace.CurrentCamera.CameraSubject = chassis
		end
		specLabel.Text = ("SPECTATING %s  -  %s     Z / X switch   B stop"):format(
			target and target.DisplayName or "...", spec.name or "")
	end
	if not active then
		warnLabel.Text = ""
		stateLabel.Text = ""
		return
	end
	local state = player:GetAttribute("CircuitState") or ""
	local mode = player:GetAttribute("CircuitMode") or ""
	local laps = player:GetAttribute("CircuitLaps") or 0
	local lap = player:GetAttribute("CircuitLap") or 0
	local race = mode == "CircuitRace" or mode == "PrivateRoom"
	hudTitle.Text = ("%s  %s"):format(string.upper(player:GetAttribute("CircuitName") or ""), string.upper(mode))
	if race then
		lapLine.Text = ("LAP %d/%d"):format(math.clamp(lap, 0, laps), laps)
	else
		lapLine.Text = if lap == 0 then "OUT LAP" else ("LAP %d"):format(lap)
	end
	local lapStart = player:GetAttribute("CircuitLapStart")
	local valid = player:GetAttribute("CircuitLapValid") ~= false
	local finished = player:GetAttribute("CircuitFinished")
	if finished then
		curLine.Text = "FINISHED " .. fmt(finished)
		curLine.TextColor3 = SPLIT.green
	elseif lapStart and (lap > 0 or race) and now >= lapStart then
		curLine.Text = "NOW  " .. fmt(now - lapStart) .. (if valid then "" else "  X")
		curLine.TextColor3 = if valid then WHITE else SPLIT.invalid
	else
		curLine.Text = "NOW  " .. fmt(nil)
		curLine.TextColor3 = DIM
	end
	lastLine.Text = "LAST " .. fmt(player:GetAttribute("CircuitLastLap"))
	bestLine.Text = ("BEST %s   PB %s"):format(fmt(player:GetAttribute("CircuitBestLap")), fmt(player:GetAttribute("CircuitPB")))
	local pos, count = player:GetAttribute("CircuitPos"), player:GetAttribute("CircuitCount") or 1
	local penalty = player:GetAttribute("CircuitPenalty") or 0
	posLine.Text = ("P%s/%d  %s%s"):format(pos and tostring(pos) or "-", count, player:GetAttribute("CircuitGap") or "",
		if penalty > 0 then ("   PEN +%d s"):format(penalty) else "")
	-- state line
	if state == "Forming" then
		local ends = player:GetAttribute("CircuitFormEnds")
		stateLabel.Text = if ends then ("RACE FORMING - start in %d s"):format(math.max(0, math.ceil(ends - now)))
			else "PRIVATE ROOM - waiting for the owner to start"
	elseif state == "Grid" then
		stateLabel.Text = "ON THE GRID - hold still"
	elseif state == "StartLights" then
		stateLabel.Text = "WAIT FOR LIGHTS OUT"
	elseif state == "Finishing" and not finished then
		stateLabel.Text = "THE LEADER HAS FINISHED - last lap"
	else
		stateLabel.Text = ""
	end
	-- warnings (most important first)
	if player:GetAttribute("CircuitWrongWay") then
		warnLabel.Text = if math.floor(os.clock() * 3) % 2 == 0 then "WRONG WAY" else ""
		warnLabel.TextColor3 = SPLIT.invalid
	elseif player:GetAttribute("CircuitPit") then
		local limit = player:GetAttribute("CircuitPitLimit") or 0
		local v = mySpeed()
		warnLabel.Text = ("PIT LANE  %d / %d"):format(math.floor(v), limit)
		warnLabel.TextColor3 = if v > limit then SPLIT.invalid else CYAN
	elseif player:GetAttribute("CircuitOff") then
		warnLabel.Text = "TRACK LIMITS"
		warnLabel.TextColor3 = SPLIT.yellow
	else
		warnLabel.Text = ""
	end
end)
