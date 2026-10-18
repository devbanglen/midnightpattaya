-- MIDNIGHT PATTAYA activity strip (ui-race, docs/UI_RACE_HUD.md). Top-centre, inside PlayerGui.MidnightHUD.TopCenter
-- (ui-core's root ScreenGui; fallback: own ScreenGui after 10 s). Draws only: every value is read from what the servers
-- already publish (player attributes, PattayaRemotes events, ReplicatedStorage.PattayaEvent). It keeps no race state
-- of its own beyond what is needed to draw (the sprint payload the server sent, like PattayaSprintClient does).
--
-- Layouts (owner rule: free roam and racing are visibly different, switched with a fade/slide):
--   wordmark  "MIDNIGHT / PATTAYA" (always, top)
--   FREE      compact: district (point-in-polygon on PattayaWorldMap, 2 Hz) + "OPEN WORLD • FREE ROAM" (or the job)
--             + one small pill: the GPS destination and distance left (GPSUpdate), else a gathering event's call.
--   RACE      larger: mode title + detail line, the 4-cell strip (POS/LAP/BEST/TIME, contents by mode), a status /
--             warning line, circuit sector bars and start lights.
--   BIG       centre text under the strip: 3-2-1-GO, VICTORY / FINISHED / DNF, results handoff (any layout).
-- Visible only while LocalPlayer attribute MidnightHUD == true (set locally by ui-core). Sizes follow
-- docs/images/ui_mockup_owner.png at 1920 x 1080 (strip 626 x 72 px, value text 30 px) at HUD scale 1.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")
local uiFolder = ReplicatedStorage:WaitForChild("MidnightUI", 30)
if not uiFolder then
	return
end
local Theme = require(uiFolder:WaitForChild("Theme")) :: any
local C = Theme.color
local SPLIT = {purple = C.purple, green = C.green, yellow = C.yellow, invalid = C.red} -- circuit sector colours
local STUD_M = 0.28 -- metres per stud, the game's convention (sprint / GPS / event distances)

local function reducedMotion(): boolean
	return player:GetAttribute("ReducedMotion") == true
end
local function dur(t: number): number
	return if reducedMotion() then 0 else t
end
local function fmt(t: number?): string
	if not t then
		return "--:--.--"
	end
	t = math.max(0, t)
	return string.format("%02d:%05.2f", t // 60, t % 60)
end
local function clock(t: number): string
	t = math.max(0, math.ceil(t))
	return string.format("%d:%02d", t // 60, t % 60)
end

-- root ---------------------------------------------------------------------------------------------------------------
local hudRoot = playerGui:WaitForChild("MidnightHUD", 10)
local anchor = hudRoot and hudRoot:FindFirstChild("TopCenter")
if not anchor then
	local g = Instance.new("ScreenGui")
	g.Name = "MidnightActivityHUD"
	g.ResetOnSpawn = false
	g.DisplayOrder = Theme.layer.hud
	local scale = Instance.new("UIScale")
	scale.Parent = g
	local frame = Instance.new("Frame")
	frame.Name = "TopCenter"
	frame.BackgroundTransparency = 1
	frame.AnchorPoint = Vector2.new(0.5, 0)
	frame.Position = UDim2.fromScale(0.5, 0)
	frame.Size = UDim2.fromOffset(660, 400)
	frame.Parent = g
	local function rescale()
		local cam = workspace.CurrentCamera
		local h = if cam then cam.ViewportSize.Y else 1080
		scale.Scale = math.clamp(h / 1080, 0.55, 1.3) * (player:GetAttribute("HUDScale") or 1)
	end
	rescale()
	if workspace.CurrentCamera then
		workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(rescale)
	end
	player:GetAttributeChangedSignal("HUDScale"):Connect(rescale)
	g.Parent = playerGui
	anchor = frame
end

local root = Instance.new("Frame")
root.Name = "MidnightActivity"
root.BackgroundTransparency = 1
root.AnchorPoint = Vector2.new(0.5, 0)
root.Position = UDim2.fromScale(0.5, 0)
root.Size = UDim2.fromOffset(660, 400)
root.Visible = false
root.Parent = anchor

-- builders: every element of a layout is registered with its resting transparencies so the layout can fade as a group
type Group = {items: {{inst: Instance, props: {[string]: number}}}, frame: Frame}
local function newGroup(name: string, y: number, h: number): Group
	local f = Instance.new("Frame")
	f.Name = name
	f.BackgroundTransparency = 1
	f.Position = UDim2.fromOffset(0, y)
	f.Size = UDim2.new(1, 0, 0, h)
	f.Visible = false
	f.Parent = root
	return {items = {}, frame = f}
end
local function reg(group: Group?, inst: Instance, props: {string})
	if group then
		local t = {}
		for _, p in props do
			t[p] = (inst :: any)[p]
		end
		table.insert(group.items, {inst = inst, props = t})
	end
end

local function text(parent: Instance, group: Group?, props): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.AnchorPoint = props.anchor or Vector2.new(0.5, 0)
	t.Position = props.pos
	t.Size = props.size
	t.Font = props.font or Theme.font.bold
	t.TextSize = props.textSize or Theme.size.body
	t.TextColor3 = props.color or C.text
	t.TextXAlignment = props.alignX or Enum.TextXAlignment.Center
	t.TextStrokeColor3 = C.navy
	t.TextStrokeTransparency = props.stroke or 0.5 -- readable over a sunlit sky and at night
	t.Text = props.text or ""
	t.ZIndex = props.z or 3
	t.Parent = parent
	reg(group, t, {"TextTransparency", "TextStrokeTransparency"})
	return t
end

local function box(parent: Instance, group: Group?, props): Frame
	local f = Instance.new("Frame")
	f.AnchorPoint = props.anchor or Vector2.new(0.5, 0)
	f.Position = props.pos
	f.Size = props.size
	f.BackgroundColor3 = props.color or C.surface
	f.BackgroundTransparency = props.alpha or Theme.alpha.panel
	f.BorderSizePixel = 0
	f.ZIndex = props.z or 2
	f.Rotation = props.rotation or 0
	f.Parent = parent
	if props.radius then
		local c = Instance.new("UICorner")
		c.CornerRadius = UDim.new(0, props.radius)
		c.Parent = f
	end
	reg(group, f, {"BackgroundTransparency"})
	if props.stroke then
		local s = Instance.new("UIStroke")
		s.Thickness = Theme.stroke.normal
		s.Color = C.text
		s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		s.Parent = f
		local gr = Instance.new("UIGradient")
		gr.Color = Theme.accentGradient()
		gr.Parent = s
		reg(group, s, {"Transparency"})
	end
	return f
end

-- wordmark (shared by both layouts) ---------------------------------------------------------------------------------
local function wordLine(str: string, y: number, h: number, size: number, c0: Color3, c1: Color3)
	local t = text(root, nil, {pos = UDim2.fromOffset(330, y), size = UDim2.fromOffset(440, h), text = str,
		font = Theme.font.display, textSize = size, stroke = 1})
	local gr = Instance.new("UIGradient")
	gr.Color = ColorSequence.new(c0, c1)
	gr.Rotation = 90
	gr.Parent = t
	local s = Instance.new("UIStroke") -- glyph outline (Contextual) so the wordmark reads on a bright sky
	s.Color = C.navy
	s.Thickness = Theme.stroke.thick
	s.Transparency = 0.2
	s.Parent = t
	return t
end
wordLine("MIDNIGHT", 14, 62, 60, C.text, C.cyan)
wordLine("PATTAYA", 72, 52, 50, C.purple, C.purple:Lerp(C.text, 0.25))

-- FREE layout (compact) ----------------------------------------------------------------------------------------------
local free = newGroup("FreeRoam", 132, 110)
local fDistrict = text(free.frame, free, {pos = UDim2.fromOffset(330, 0), size = UDim2.fromOffset(520, 26),
	text = "PATTAYA", font = Theme.font.bold, textSize = 22, stroke = 0.4})
local fMode = text(free.frame, free, {pos = UDim2.fromOffset(330, 27), size = UDim2.fromOffset(520, 18),
	text = "OPEN WORLD • FREE ROAM", font = Theme.font.body, textSize = 15, color = C.textDim})
local fPill = box(free.frame, free, {pos = UDim2.fromOffset(330, 54), size = UDim2.fromOffset(380, 34),
	radius = 17, stroke = true, alpha = Theme.alpha.panel})
local fPillDot = box(fPill, free, {anchor = Vector2.new(0, 0.5), pos = UDim2.new(0, 14, 0.5, 0), size = UDim2.fromOffset(9, 9),
	color = C.cyan, alpha = 0, radius = 5, z = 3})
local fPillText = text(fPill, free, {anchor = Vector2.new(0, 0.5), pos = UDim2.new(0, 32, 0.5, 0), size = UDim2.new(1, -44, 1, 0),
	font = Theme.font.bold, textSize = 16, alignX = Enum.TextXAlignment.Left, stroke = 0.7})
fPill.Visible = false

-- RACE layout (larger) -----------------------------------------------------------------------------------------------
local race = newGroup("Racing", 128, 170)
local rTitle = text(race.frame, race, {pos = UDim2.fromOffset(330, 0), size = UDim2.fromOffset(600, 28),
	font = Theme.font.display, textSize = 24, stroke = 0.4})
local rSub = text(race.frame, race, {pos = UDim2.fromOffset(330, 29), size = UDim2.fromOffset(600, 18),
	font = Theme.font.body, textSize = 15, color = C.textDim})
local strip = box(race.frame, race, {pos = UDim2.fromOffset(330, 54), size = UDim2.fromOffset(626, 72),
	radius = Theme.radius.panel, stroke = true, color = C.navy})
local cells = {}
for i = 1, 4 do
	local x = (i - 0.5) / 4
	local cap = text(strip, race, {pos = UDim2.new(x, 0, 0, 7), size = UDim2.new(0.25, -16, 0, 18), font = Theme.font.bold,
		textSize = 16, color = C.cyan, stroke = 0.8})
	local val = text(strip, race, {pos = UDim2.new(x, 0, 0, 27), size = UDim2.new(0.25, -6, 0, 38),
		font = Theme.font.display, textSize = 28, stroke = 0.6})
	cells[i] = {cap = cap, val = val}
	if i > 1 then -- slanted divider, like the mockup's parallelogram cells
		box(strip, race, {anchor = Vector2.new(0.5, 0.5), pos = UDim2.new((i - 1) / 4, 0, 0.5, 0), size = UDim2.fromOffset(2, 50),
			color = C.line, alpha = 0, rotation = 15, z = 3})
	end
end
local rStatus = text(race.frame, race, {pos = UDim2.fromOffset(330, 132), size = UDim2.fromOffset(600, 22),
	font = Theme.font.display, textSize = 20, color = C.red, stroke = 0.3})
-- circuit sector bars (under the strip, left of centre) and start lights (replace the status line while lit)
local sectors = {}
for k = 1, 3 do
	local b = box(race.frame, race, {pos = UDim2.fromOffset(330 + (k - 2) * 112, 160), size = UDim2.fromOffset(104, 24),
		color = C.surface2, alpha = 0.15, radius = Theme.radius.small})
	local t = text(b, race, {anchor = Vector2.new(0.5, 0.5), pos = UDim2.fromScale(0.5, 0.5), size = UDim2.new(1, -8, 1, -4),
		text = "S" .. k, font = Theme.font.mono, textSize = 15, color = C.textDim, stroke = 1})
	sectors[k] = {frame = b, label = t}
end
local sectorRow = {sectors[1].frame, sectors[2].frame, sectors[3].frame}
local lightsRow = Instance.new("Frame")
lightsRow.Name = "StartLights"
lightsRow.BackgroundTransparency = 1
lightsRow.AnchorPoint = Vector2.new(0.5, 0)
lightsRow.Position = UDim2.fromOffset(330, 132)
lightsRow.Size = UDim2.fromOffset(5 * 44, 38)
lightsRow.Visible = false
lightsRow.Parent = race.frame
local bulbs = {}
for k = 1, 5 do
	bulbs[k] = box(lightsRow, nil, {anchor = Vector2.new(0.5, 0), pos = UDim2.fromOffset(22 + (k - 1) * 44, 0),
		size = UDim2.fromOffset(34, 34), color = C.surface2, alpha = 0, radius = 17, z = 3})
end

-- BIG centre text (countdown / result), outside both layouts
local big = text(root, nil, {pos = UDim2.fromOffset(330, 318), size = UDim2.fromOffset(600, 64), font = Theme.font.display,
	textSize = Theme.size.huge, stroke = 0.2})
local bigSub = text(root, nil, {pos = UDim2.fromOffset(330, 380), size = UDim2.fromOffset(600, 22), font = Theme.font.bold,
	textSize = Theme.size.title, stroke = 0.4})

-- layout switching (fade + slide, Theme.motion; instant with ReducedMotion) -----------------------------------------
local current: Group? = nil
local function fadeGroup(g: Group, shown: boolean, t: number)
	local info = TweenInfo.new(t, Theme.motion.ease, Theme.motion.easeOut)
	for _, it in g.items do
		local goal = {}
		for p, base in it.props do
			goal[p] = if shown then base else 1
		end
		if t <= 0 then
			for p, v in goal do
				(it.inst :: any)[p] = v
			end
		else
			TweenService:Create(it.inst, info, goal):Play()
		end
	end
end
local function setLayout(g: Group)
	if current == g then
		return
	end
	local old = current
	current = g
	local t = dur(Theme.motion.normal)
	if old then
		local oldFrame = old.frame
		fadeGroup(old, false, t)
		if t > 0 then
			TweenService:Create(oldFrame, TweenInfo.new(t, Theme.motion.ease, Theme.motion.easeOut),
				{Position = UDim2.fromOffset(0, oldFrame.Position.Y.Offset - 10)}):Play()
		end
		task.delay(t, function()
			if current ~= old then
				oldFrame.Visible = false
			end
		end)
	end
	local y = if g == free then 132 else 128
	g.frame.Position = UDim2.fromOffset(0, y + (if t > 0 then 12 else 0))
	fadeGroup(g, false, 0)
	g.frame.Visible = true
	fadeGroup(g, true, t)
	if t > 0 then
		TweenService:Create(g.frame, TweenInfo.new(t, Theme.motion.ease, Theme.motion.easeOut),
			{Position = UDim2.fromOffset(0, y)}):Play()
	end
end

local bigStamp = 0
local function showBig(str: string, color: Color3, sub: string?, seconds: number)
	bigStamp += 1
	local stamp = bigStamp
	big.Text, big.TextColor3 = str, color
	bigSub.Text, bigSub.TextColor3 = sub or "", C.text
	if not reducedMotion() then -- small pop-in, no shake
		big.TextSize = Theme.size.huge * 0.8
		TweenService:Create(big, TweenInfo.new(Theme.motion.fast, Enum.EasingStyle.Back, Theme.motion.easeOut),
			{TextSize = Theme.size.huge}):Play()
	end
	task.delay(seconds, function()
		if bigStamp == stamp then
			big.Text, bigSub.Text = "", ""
		end
	end)
end

local flashing: {[TextLabel]: number} = {}
local function flash(lbl: TextLabel, color: Color3, rest: Color3)
	flashing[lbl] = os.clock() + 1.6
	lbl.TextColor3 = color
	if reducedMotion() then
		task.delay(1.6, function()
			lbl.TextColor3 = rest
		end)
	else
		TweenService:Create(lbl, TweenInfo.new(1.6, Enum.EasingStyle.Quad, Enum.EasingDirection.In), {TextColor3 = rest}):Play()
	end
end
local function setCell(i: number, cap: string?, val: string?, color: Color3?)
	local c = cells[i]
	c.cap.Text = cap or ""
	c.val.Text = val or ""
	if (flashing[c.val] or 0) < os.clock() then
		c.val.TextColor3 = color or C.text
	end
end

-- data sources ---------------------------------------------------------------------------------------------------------
local mapData = nil
task.spawn(function()
	local m = ReplicatedStorage:WaitForChild("PattayaWorldMap", 60)
	if m then
		local ok, data = pcall(require, m)
		if ok and type(data) == "table" then
			mapData = data
		end
	end
end)
local loop = nil -- {count, laps, name}
task.spawn(function()
	local world = workspace:WaitForChild("PattayaWorld", 60)
	local r = world and world:WaitForChild("Race", 60)
	local cps = r and r:WaitForChild("Checkpoints", 30)
	if r and cps then
		loop = {count = #cps:GetChildren(), laps = r:GetAttribute("Laps") or 1, name = r:GetAttribute("RaceName") or "Loop Race"}
	end
end)
local eventState = ReplicatedStorage:FindFirstChild("PattayaEvent")
task.spawn(function()
	eventState = eventState or ReplicatedStorage:WaitForChild("PattayaEvent", 60)
end)

local street = nil -- the street race the server sent: {cps, next, start, timeLimit, length, title, rivals, place, count}
local gps = nil -- {label, route, suffix, idx}
local job = nil -- {title, to}
local lights = nil -- {at, interval, count, outAt}

local function carPart(): BasePart?
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat.Parent and (seat.Parent :: Model).PrimaryPart then
		return (seat.Parent :: Model).PrimaryPart
	end
	return char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
end

local function clearSectors(from: number)
	for k = from, 3 do
		sectors[k].frame.BackgroundColor3 = C.surface2
		sectors[k].label.Text = "S" .. k
		sectors[k].label.TextColor3 = C.textDim
	end
end

local function titleOf(t: string?): (string, string?)
	if not t or t == "SPRINT" then
		return "STREET SPRINT", nil
	elseif t == "CHALLENGE" then
		return "STREET CHALLENGE", nil
	elseif string.sub(t, 1, 8) == "SURVIVAL" then
		return "SURVIVAL", "survival"
	end
	return string.upper(t), nil
end

local function wire(remotes: Instance, name: string, fn: (...any) -> ())
	task.spawn(function()
		local r = remotes:WaitForChild(name, 60)
		if r and r:IsA("RemoteEvent") then
			r.OnClientEvent:Connect(fn)
		end
	end)
end

task.spawn(function()
	local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
	if not remotes then
		return
	end
	wire(remotes, "SprintUpdate", function(kind, payload)
		if kind == "start" then
			street = {cps = payload.checkpoints, next = 1, start = payload.start, timeLimit = payload.timeLimit,
				length = payload.length, title = payload.title, rivals = payload.rivals}
		elseif kind == "next" and street then
			street.next = payload
		elseif kind == "finish" then
			local txt = payload.text
			if txt and (string.find(string.upper(txt), "WIN") ~= nil) then
				showBig("VICTORY", C.green, txt, 5)
			else
				showBig("FINISHED", C.yellow, txt or fmt(payload.time), 5)
			end
			street = nil
		elseif kind == "stop" then
			if street then
				showBig("DNF", C.red, tostring(payload), 4)
			end
			street = nil
		end
	end)
	wire(remotes, "ChallengeMsg", function(kind, a, b)
		if kind == "standings" and street then
			street.place, street.count = b, #a
		elseif kind == "countdown" then
			local goAt = a
			task.spawn(function()
				local shown = -1
				while true do
					local left = goAt - workspace:GetServerTimeNow()
					if left <= 0 then
						break
					end
					local n = math.ceil(left)
					if n ~= shown then
						shown = n
						showBig(tostring(n), C.text, nil, 1.2)
					end
					task.wait(0.05)
				end
				showBig("GO!", C.green, nil, 1)
			end)
		end
	end)
	wire(remotes, "GPSUpdate", function(kind, payload)
		if kind == "route" and type(payload) == "table" and payload.route and #payload.route >= 2 then
			-- distance left along the route: suffix sums once per route, a moving nearest-point index at 2 Hz
			local r = payload.route
			local suffix = table.create(#r, 0)
			for i = #r - 1, 1, -1 do
				suffix[i] = suffix[i + 1] + (r[i + 1] - r[i]).Magnitude
			end
			gps = {label = payload.label or "", route = r, suffix = suffix, idx = 1, left = suffix[1]}
		elseif kind == "arrived" or kind == "clear" then
			gps = nil
		end
	end)
	wire(remotes, "JobUpdate", function(kind, payload)
		if kind == "start" and type(payload) == "table" then
			job = {title = payload.title or "JOB", to = payload.to}
		elseif kind == "finish" or kind == "stop" then
			job = nil
		end
	end)
	wire(remotes, "CircuitMsg", function(kind, payload)
		if kind == "sector" then
			if payload.n == 1 then
				clearSectors(2)
			end
			local s = sectors[payload.n]
			if s then
				s.frame.BackgroundColor3 = SPLIT[payload.colour] or C.yellow
				s.label.Text = string.format("%.3f", payload.time)
				s.label.TextColor3 = C.text
			end
		elseif kind == "lap" then
			if payload.pb and payload.valid then
				flash(cells[3].val, C.yellow, C.text)
				flash(cells[3].cap, C.yellow, C.cyan)
				showBig("PERSONAL BEST", C.yellow, ("LAP %d  %s"):format(payload.lap, fmt(payload.time)), 3)
			elseif not payload.valid then
				showBig("LAP INVALID", C.red, ("LAP %d  %s"):format(payload.lap, fmt(payload.time)), 2.5)
			end
		elseif kind == "lights" then
			lights = {at = payload.at, interval = payload.interval, count = payload.count}
		elseif kind == "lightsOut" then
			if lights then
				lights.outAt = payload.at
			end
			showBig("GO!", C.green, nil, 1.5)
			task.delay(1.2, function()
				lights = nil
			end)
		elseif kind == "results" and type(payload) == "table" then
			local mine = nil
			for _, r in payload.rows or {} do
				if r.userId == player.UserId then
					mine = r
				end
			end
			if mine then
				local fin = mine.status == "FIN"
				local isRace = payload.mode == "CircuitRace" or payload.mode == "PrivateRoom"
				local head = if not fin then "DNF" elseif isRace and mine.pos == 1 then "VICTORY"
					elseif isRace then ("P%d"):format(mine.pos) else "SESSION OVER"
				local col = if not fin then C.red elseif head == "VICTORY" then C.green else C.yellow
				showBig(head, col, ("RESULTS  •  P%s/%d  •  %s"):format(tostring(mine.pos or "-"), #(payload.rows or {}),
					if mine.time then fmt(mine.time) else "BEST " .. fmt(mine.best)), 8)
			end
		end
	end)
end)

-- loop race: personal best and finish come from the attributes PattayaRaceServer sets
player:GetAttributeChangedSignal("RaceState"):Connect(function()
	if player:GetAttribute("RaceState") == "finished" then
		local t = player:GetAttribute("RaceLastTime")
		local best = player:GetAttribute("RaceBest")
		local pb = t and best and math.abs(t - best) < 1e-3
		showBig("FINISHED", if pb then C.yellow else C.green,
			("%s%s"):format(fmt(t), if pb then "  •  NEW BEST" else ("  •  BEST " .. fmt(best))), 6)
	end
end)
local raceFinishedAt = 0
player:GetAttributeChangedSignal("RaceBest"):Connect(function()
	flash(cells[3].val, C.yellow, C.text)
	flash(cells[3].cap, C.yellow, C.cyan)
end)
player:GetAttributeChangedSignal("CircuitActive"):Connect(function()
	clearSectors(1)
	lights = nil
end)

-- district (2 Hz) --------------------------------------------------------------------------------------------------
local function inPoly(poly: {number}, x: number, z: number): boolean
	local inside = false
	local n = #poly // 2
	local j = n
	for i = 1, n do
		local xi, zi = poly[2 * i - 1], poly[2 * i]
		local xj, zj = poly[2 * j - 1], poly[2 * j]
		if (zi > z) ~= (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi then
			inside = not inside
		end
		j = i
	end
	return inside
end

local function districtAt(pos: Vector3): string
	if mapData and mapData.districts then
		for _, d in mapData.districts do
			if d.poly and #d.poly >= 6 and inPoly(d.poly, pos.X, pos.Z) then
				return string.upper(d.name or d.id or "PATTAYA")
			end
		end
	end
	return "PATTAYA"
end

local function gpsTick(pos: Vector3)
	if not gps then
		return
	end
	local r = gps.route
	local best, bestD = gps.idx, math.huge
	for i = gps.idx, math.min(#r, gps.idx + 60) do
		local q = r[i]
		local d = (Vector3.new(q.X, 0, q.Z) - Vector3.new(pos.X, 0, pos.Z)).Magnitude
		if d < bestD then
			best, bestD = i, d
		end
	end
	gps.idx = best
	local nxt = math.min(best + 1, #r)
	local q = r[nxt]
	gps.left = (Vector3.new(q.X, 0, q.Z) - Vector3.new(pos.X, 0, pos.Z)).Magnitude + gps.suffix[nxt]
end

local slowAcc = 0
local function slowTick()
	local part = carPart()
	if part then
		fDistrict.Text = districtAt(part.Position)
		gpsTick(part.Position)
	end
end

-- main update (20 Hz) ------------------------------------------------------------------------------------------------
local PRETTY = {TimeAttack = "TIME ATTACK", FreePractice = "FREE PRACTICE", TrackDay = "TRACK DAY",
	CircuitRace = "RACE", PrivateRoom = "PRIVATE ROOM"}

local function circuitTick(now: number)
	local mode = player:GetAttribute("CircuitMode") or ""
	local isRace = mode == "CircuitRace" or mode == "PrivateRoom"
	local name = string.upper(player:GetAttribute("CircuitName") or "CIRCUIT")
	local pb = player:GetAttribute("CircuitPB")
	rTitle.Text = name
	rSub.Text = ("%s%s"):format(PRETTY[mode] or string.upper(mode), if pb then "  •  PB " .. fmt(pb) else "")
	local lap = player:GetAttribute("CircuitLap") or 0
	local laps = player:GetAttribute("CircuitLaps") or 0
	local lapStart = player:GetAttribute("CircuitLapStart")
	local valid = player:GetAttribute("CircuitLapValid") ~= false
	local finished = player:GetAttribute("CircuitFinished")
	local timeText, timeCol = fmt(nil), C.textDim
	if finished then
		timeText, timeCol = fmt(finished), C.green
	elseif lapStart and (lap > 0 or isRace) and now >= lapStart then
		timeText, timeCol = fmt(now - lapStart), if valid then C.text else C.red
	end
	local best = player:GetAttribute("CircuitBestLap")
	if isRace then
		local pos, count = player:GetAttribute("CircuitPos"), player:GetAttribute("CircuitCount") or 1
		setCell(1, "POS", ("%s/%d"):format(pos and tostring(pos) or "-", count), C.yellow)
		setCell(2, "LAP", ("%d/%d"):format(math.clamp(lap, 0, laps), laps))
	else
		setCell(1, "LAP", if lap == 0 then "OUT" else tostring(lap))
		setCell(2, "LAST", fmt(player:GetAttribute("CircuitLastLap")))
	end
	setCell(3, "BEST", fmt(best or pb))
	setCell(4, if finished then "FINISHED" else "TIME", timeText, timeCol)
	-- status / warnings (most important first; warnings red as in the old HUD, track limits yellow, pit cyan)
	local state = player:GetAttribute("CircuitState") or ""
	local penalty = player:GetAttribute("CircuitPenalty") or 0
	local penText = if penalty > 0 then ("   PEN +%d s"):format(penalty) else ""
	local status, col = "", C.text
	if player:GetAttribute("CircuitWrongWay") then
		status, col = if math.floor(os.clock() * 3) % 2 == 0 then "WRONG WAY" else "", C.red
	elseif player:GetAttribute("CircuitPit") then
		local limit = player:GetAttribute("CircuitPitLimit") or 0
		local v = player:GetAttribute("HUD_SpeedKmh") or 0
		status, col = ("PIT LANE  %d / %d"):format(v, limit), if v > limit then C.red else C.cyan
	elseif player:GetAttribute("CircuitOff") then
		status, col = "TRACK LIMITS", C.yellow
	elseif penalty > 0 then
		status, col, penText = ("PENALTY +%d s"):format(penalty), C.red, ""
	elseif state == "Forming" then
		local ends = player:GetAttribute("CircuitFormEnds")
		status, col = if ends then ("RACE FORMING  •  START IN %d s"):format(math.max(0, math.ceil(ends - now)))
			else "PRIVATE ROOM  •  WAITING FOR THE OWNER", C.textDim
	elseif state == "Grid" then
		status, col = "ON THE GRID  •  HOLD STILL", C.text
	elseif state == "StartLights" then
		status, col = "WAIT FOR LIGHTS OUT", C.text
	elseif state == "Finishing" and not finished then
		status, col = "THE LEADER HAS FINISHED  •  LAST LAP", C.yellow
	elseif finished then
		status, col = "FINISHED", C.green
	end
	rStatus.Text = status .. penText
	rStatus.TextColor3 = col
	-- sectors only when the session is timed (no lap start = untimed practice / not started)
	local timed = player:GetAttribute("CircuitLapStart") ~= nil or (player:GetAttribute("CircuitLastLap") ~= nil)
	for _, f in sectorRow do
		f.Visible = timed and not lights
	end
	-- start lights
	if lights then
		lightsRow.Visible = true
		rStatus.Text = ""
		local lit = math.clamp(math.floor((now - lights.at) / lights.interval) + 1, 0, lights.count)
		if lights.outAt and now >= lights.outAt then
			lit = 0
		end
		for k, b in bulbs do
			b.BackgroundColor3 = if k <= lit then C.red else C.surface2
		end
	else
		lightsRow.Visible = false
	end
end

local function streetTick(now: number)
	local s = street :: any
	local title, kind = titleOf(s.title)
	rTitle.Text = title
	if kind == "survival" and eventState then
		rSub.Text = ("ROUND %d/%d  •  %d DRIVERS LEFT"):format(eventState:GetAttribute("Round") or 0,
			eventState:GetAttribute("Rounds") or 0, eventState:GetAttribute("Alive") or 0)
	elseif s.rivals and #s.rivals > 0 then
		rSub.Text = ("VS %s  •  %.1f KM"):format(string.upper(table.concat(s.rivals, ", ")), (s.length or 0) * STUD_M / 1000)
	else
		rSub.Text = ("%.1f KM"):format((s.length or 0) * STUD_M / 1000)
	end
	local elapsed = math.max(0, now - (s.start or now))
	local left = (s.timeLimit or 0) - elapsed
	local n = #(s.cps or {})
	if s.place then
		setCell(1, "POS", ("%d/%d"):format(s.place, s.count or 1), C.yellow)
		setCell(2, "CP", ("%d/%d"):format(s.next, n))
	else
		setCell(1, "CP", ("%d/%d"):format(s.next, n))
		local part = carPart()
		local target = s.cps and s.cps[s.next]
		local dist = if part and target
			then Vector3.new(target.X - part.Position.X, 0, target.Z - part.Position.Z).Magnitude * STUD_M else nil
		setCell(2, "NEXT", if dist then ("%d m"):format(math.floor(dist)) else "-")
	end
	setCell(3, "TIME", fmt(elapsed))
	if s.timeLimit then
		setCell(4, "LEFT", clock(left), if left < 10 then C.red else C.text)
	else
		setCell(4, "", "")
	end
	rStatus.Text = ""
	lightsRow.Visible = false
	for _, f in sectorRow do
		f.Visible = false
	end
end

local function loopTick(now: number)
	local l = loop or {count = 1, laps = 1, name = "Loop Race"}
	rTitle.Text = string.upper(l.name)
	rSub.Text = ("LOOP RACE  •  %d LAP%s"):format(l.laps, if l.laps == 1 then "" else "S")
	local state = player:GetAttribute("RaceState")
	local best = player:GetAttribute("RaceBest")
	if state == "racing" then
		local nextCp = player:GetAttribute("RaceNext") or 2
		local done = (nextCp - 2) % math.max(l.count, 1)
		setCell(1, "LAP", ("%d/%d"):format(player:GetAttribute("RaceLap") or 1, l.laps))
		setCell(2, "CP", ("%d/%d"):format(done, l.count))
		setCell(3, "BEST", fmt(best))
		setCell(4, "TIME", fmt(now - (player:GetAttribute("RaceStart") or now)))
		rStatus.Text = ""
	else -- just finished (shown for a few seconds)
		setCell(1, "LAP", ("%d/%d"):format(l.laps, l.laps))
		setCell(2, "CP", ("%d/%d"):format(l.count, l.count))
		setCell(3, "BEST", fmt(best))
		setCell(4, "FINISH", fmt(player:GetAttribute("RaceLastTime")), C.green)
		rStatus.Text = "FINISHED"
		rStatus.TextColor3 = C.green
	end
	lightsRow.Visible = false
	for _, f in sectorRow do
		f.Visible = false
	end
end

local function freeTick(now: number)
	if job and player:GetAttribute("JobActive") == true then
		fMode.Text = ("OPEN WORLD  •  %s JOB"):format(string.upper(job.title))
	else
		fMode.Text = "OPEN WORLD  •  FREE ROAM"
	end
	local pill: string? = nil
	local dotCol = C.cyan
	if gps then
		pill = ("%s  •  %.1f KM"):format(string.upper(gps.label), (gps.left or 0) * STUD_M / 1000)
	elseif eventState and eventState:GetAttribute("Phase") == "gathering" then
		-- a gathering event is the only other guidance line (it replaces the old EventHUD banner)
		local title = string.upper(eventState:GetAttribute("Title") or "EVENT")
		local leftT = (eventState:GetAttribute("StartAt") or 0) - now
		if player:GetAttribute("EventJoined") == true then
			pill = ("%s IN %s  •  YOU'RE IN  •  %d DRIVERS"):format(title, clock(leftT), eventState:GetAttribute("Entrants") or 0)
		else
			local ring = eventState:GetAttribute("RingPos") or Vector3.zero
			local part = carPart()
			local d = if part then Vector3.new(ring.X - part.Position.X, 0, ring.Z - part.Position.Z).Magnitude else nil
			local canJoin = d and d <= (eventState:GetAttribute("JoinRadius") or 1500)
			pill = ("%s IN %s%s%s"):format(title, clock(leftT),
				if d then ("  •  RING %d M"):format(math.floor(d * STUD_M)) else "",
				if canJoin and player:GetAttribute("HUD_InCar") then "  •  J TO JOIN" else "")
		end
		dotCol = C.purple
	end
	fPill.Visible = pill ~= nil
	if pill then
		fPillText.Text = pill
		fPillDot.BackgroundColor3 = dotCol
		fPill.Size = UDim2.fromOffset(math.clamp(52 + #pill * 9, 200, 600), 34)
	end
end

local acc = 0
RunService.Heartbeat:Connect(function(dt)
	root.Visible = player:GetAttribute("MidnightHUD") == true
	if not root.Visible then
		return
	end
	acc += dt
	slowAcc += dt
	if slowAcc >= 0.5 then
		slowAcc = 0
		slowTick()
	end
	if acc < 0.05 then
		return
	end
	acc = 0
	local now = workspace:GetServerTimeNow()
	if player:GetAttribute("CircuitActive") == true then
		setLayout(race)
		circuitTick(now)
	elseif street then
		setLayout(race)
		streetTick(now)
	elseif player:GetAttribute("RaceState") == "racing"
		or (player:GetAttribute("RaceState") == "finished" and os.clock() - raceFinishedAt < 6) then
		setLayout(race)
		loopTick(now)
	else
		setLayout(free)
		freeTick(now)
	end
end)
player:GetAttributeChangedSignal("RaceState"):Connect(function()
	if player:GetAttribute("RaceState") == "finished" then
		raceFinishedAt = os.clock()
	end
end)
