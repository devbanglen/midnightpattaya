-- Minimap + world map (MIDNIGHT PATTAYA). Data: ReplicatedStorage.PattayaWorldMap (main roads, coast, districts,
-- POIs; world studs) and, when present, ReplicatedStorage.PattayaCorridorMap (the road to the Bira Circuit).
-- Minimap: north-up, centred on the car (or the character), 1 px = 4 studs at the middle zoom level (3 levels).
-- The whole map is drawn ONCE as Frames inside one container ("World"); only that container moves (when the player
-- moved at least one screen pixel or turned), so the per-frame cost is a couple of property writes and no instances.
-- M (or the MAP button, the card's expand button, or Bus "map.toggle") opens the full map: the same World container is
-- reparented into a full-screen panel with title bar, district names, legend and a destination list (GPSUpdate
-- "list"); clicking the Bira/circuit icon or a destination starts the GPS (GPSRequest, as before, plus Bus "gps.set"
-- tagged "map"). The GPS route (GPSUpdate "route") is drawn on both from a reused pool of segments.
-- Premium HUD (docs/UI_CONTRACT.md, docs/UI_MAP.md): colours/fonts from ReplicatedStorage.MidnightUI.Theme. The minimap
-- card sits in PlayerGui.MidnightHUD.BottomLeft while LocalPlayer attribute MidnightHUD == true (local, per player), else in the old
-- MinimapHUD ScreenGui (top-left, as before). Header = GPS destination + distance (LocalPlayer attributes GPS_Label /
-- GPS_Km from PattayaGPSClient) or "PATTAYA • <district>". Map icons use no external assets (text glyphs).
-- Marker sizes and line widths are kept constant on screen by dividing by the map scale whenever the scale changes.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")
local TweenService = game:GetService("TweenService")

local mapModule = ReplicatedStorage:WaitForChild("PattayaWorldMap", 60)
if not mapModule then
	return
end
local map = require(mapModule)
local corridorModule = ReplicatedStorage:FindFirstChild("PattayaCorridorMap")
local corridor = corridorModule and require(corridorModule) or nil
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
local GPSUpdate = remotes and remotes:WaitForChild("GPSUpdate", 30)
local GPSRequest = remotes and remotes:WaitForChild("GPSRequest", 30)
local player = Players.LocalPlayer

-- design tokens (required) + client bus / responsive helpers (optional) ------------------------------------------
local uiFolder = ReplicatedStorage:WaitForChild("MidnightUI", 30)
local themeModule = uiFolder and uiFolder:WaitForChild("Theme", 5)
if not themeModule then
	warn("PattayaMinimapClient: ReplicatedStorage.MidnightUI.Theme missing, minimap disabled")
	return
end
local Theme = require(themeModule) :: any
local busModule = uiFolder:FindFirstChild("Bus")
local Bus = if busModule then require(busModule) :: any else {fire = function(...) end, on = function(...) return nil end}
local responsiveModule = uiFolder:FindFirstChild("Responsive")
local Responsive: any = nil
if responsiveModule then
	local ok, mod = pcall(require, responsiveModule)
	if ok then Responsive = mod end
end
local reducedMotion = false
if Responsive and type(Responsive.reducedMotion) == "function" then
	local ok, v = pcall(Responsive.reducedMotion)
	reducedMotion = ok and v == true
end

local C = Theme.color
local MINI_SCALE = 0.25 -- world px per stud (UIScale 1 = middle minimap zoom)
local ZOOMS = {0.5, 1, 2} -- minimap zoom levels (UIScale on World)
local zoomIndex = 2
local TOUCH = 44 -- minimum touch target (px)
local CARD_W, CARD_H = 340, 300 -- owner mockup proportions at 1920x1080 (before the root HUD scale)
local HEADER_H = 38
local PAD = Theme.pad.s
local MAP_W, MAP_H = CARD_W - PAD * 2, CARD_H - HEADER_H - PAD
local ICON = 20 -- marker badge size on screen
local COL = {
	water = C.navy, land = C.surface, district = C.line, coast = C.cyan, express = C.textDim, main = C.textMuted,
	corridor = C.textDim, route = C.cyan, me = C.text, players = C.purple, label = C.textDim,
}
-- marker kinds: glyph (text only, no external assets), accent colour, legend text
local KIND = {
	taxi = {glyph = "🔧", color = C.yellow, legend = "Taxi job stand"},
	delivery = {glyph = "🔧", color = C.green, legend = "Delivery job stand"},
	boss = {glyph = "VS", color = C.red, legend = "Road Fight boss"},
	race = {glyph = "🏁", color = C.text, legend = "Central loop race"},
	bira = {glyph = "🏁", color = C.purple, legend = "Circuit entrance (tap = GPS)"},
	garage = {glyph = "🚗", color = C.cyan, legend = "Garage / car shop"},
	event = {glyph = "", color = C.yellow, legend = "Event gathering ring"},
}
local ORIGIN = map.origin or {x = 20000, z = 0}

-- a circuit entrance published by CircuitServer replaces the "pending corridor" placeholder for its POI
local function circuitPos(id: string): Vector3?
	local v = mapModule:GetAttribute("Circuit_" .. id)
	return if typeof(v) == "Vector3" then v else nil
end

local function px(x: number, z: number): (number, number)
	return (x - ORIGIN.x) * MINI_SCALE, (z - ORIGIN.z) * MINI_SCALE
end

local function corner(parent: Instance, r: number)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, r)
	c.Parent = parent
	return c
end
local function strokeOf(parent: Instance, color: Color3, thickness: number, transparency: number?): UIStroke
	local s = Instance.new("UIStroke")
	s.Color = color
	s.Thickness = thickness
	s.Transparency = transparency or 0
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Parent = parent
	return s
end
local function text(parent: Instance, props): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Font = props.font or Theme.font.bold
	t.TextSize = props.size or Theme.size.label
	t.TextColor3 = props.color or C.text
	t.TextXAlignment = props.align or Enum.TextXAlignment.Left
	t.Text = props.text or ""
	t.TextTruncate = Enum.TextTruncate.AtEnd
	t.ZIndex = props.z or 20
	t.Parent = parent
	return t
end
-- touch-safe feedback (ui-fix round 3): no AutoButtonColor; mouse hover (MouseMovement only, so a tap never leaves a
-- stuck hover), pressed colour while the touch / click that began on the button is held. `target` = what is recoloured.
local function pressFx(b: GuiButton, target: GuiObject?)
	local t = target or b
	local base: Color3? = nil
	local hovering, pressing = false, false
	local function render()
		if not hovering and not pressing then
			if base then
				t.BackgroundColor3 = base
				base = nil
			end
			return
		end
		base = base or t.BackgroundColor3
		t.BackgroundColor3 = if pressing then C.cyan else C.line
	end
	b.InputBegan:Connect(function(input: InputObject)
		local kind = input.UserInputType
		if kind == Enum.UserInputType.MouseMovement then
			hovering = true
			render()
		elseif kind == Enum.UserInputType.MouseButton1 or kind == Enum.UserInputType.Touch then
			pressing = true
			render()
			local c: RBXScriptConnection
			c = input:GetPropertyChangedSignal("UserInputState"):Connect(function()
				if input.UserInputState == Enum.UserInputState.End or input.UserInputState == Enum.UserInputState.Cancel then
					c:Disconnect()
					pressing = false
					render()
				end
			end)
		end
	end)
	b.InputEnded:Connect(function(input: InputObject)
		if input.UserInputType == Enum.UserInputType.MouseMovement then
			hovering = false
			render()
		end
	end)
end
local function button(parent: Instance, label: string, z: number?): TextButton
	local b = Instance.new("TextButton")
	b.AutoButtonColor = false
	pressFx(b)
	b.BackgroundColor3 = C.surface2
	b.BackgroundTransparency = Theme.alpha.panelDim
	b.BorderSizePixel = 0
	b.Font = Theme.font.bold
	b.TextSize = Theme.size.label
	b.TextColor3 = C.text
	b.Text = label
	b.ZIndex = z or 20
	b.Parent = parent
	corner(b, Theme.radius.button)
	strokeOf(b, C.line, Theme.stroke.thin, 0.2)
	return b
end

-- GUI roots -------------------------------------------------------------------------------------------------------
local legacyGui = Instance.new("ScreenGui") -- the old HUD's ScreenGui; holds the card when the new HUD is off
legacyGui.Name = "MinimapHUD"
legacyGui.ResetOnSpawn = false
legacyGui.DisplayOrder = 5
legacyGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

local fullGui = Instance.new("ScreenGui") -- full map overlay (built once, Enabled while open)
fullGui.Name = "WorldMapUI"
fullGui.ResetOnSpawn = false
fullGui.IgnoreGuiInset = true
fullGui.DisplayOrder = Theme.layer.overlay
fullGui.Enabled = false
fullGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling

-- minimap card: header + map view + controls ----------------------------------------------------------------------
local card = Instance.new("Frame")
card.Name = "MinimapCard"
card.Size = UDim2.fromOffset(CARD_W, CARD_H)
card.BackgroundColor3 = C.surface
card.BackgroundTransparency = Theme.alpha.panel
card.BorderSizePixel = 0
card.Parent = legacyGui
corner(card, Theme.radius.panel)
strokeOf(card, C.line, Theme.stroke.normal, 0.1)
local accent = Instance.new("Frame") -- cyan -> purple accent line on the panel top
accent.Name = "Accent"
accent.Position = UDim2.fromOffset(Theme.radius.panel, 0)
accent.Size = UDim2.new(1, -Theme.radius.panel * 2, 0, 2)
accent.BackgroundColor3 = C.text
accent.BorderSizePixel = 0
accent.ZIndex = 20
accent.Parent = card
local grad = Instance.new("UIGradient")
grad.Color = Theme.accentGradient()
grad.Parent = accent

local pin = Instance.new("Frame") -- location pin (dot in a ring)
pin.Name = "Pin"
pin.AnchorPoint = Vector2.new(0, 0.5)
pin.Position = UDim2.fromOffset(PAD + 2, HEADER_H / 2)
pin.Size = UDim2.fromOffset(12, 12)
pin.BackgroundColor3 = C.cyan
pin.BorderSizePixel = 0
pin.ZIndex = 20
pin.Parent = card
corner(pin, Theme.radius.pill)
local pinCore = Instance.new("Frame")
pinCore.AnchorPoint = Vector2.new(0.5, 0.5)
pinCore.Position = UDim2.fromScale(0.5, 0.5)
pinCore.Size = UDim2.fromOffset(4, 4)
pinCore.BackgroundColor3 = C.navy
pinCore.BorderSizePixel = 0
pinCore.ZIndex = 21
pinCore.Parent = pin
corner(pinCore, Theme.radius.pill)

local header = text(card, {font = Theme.font.bold, size = Theme.size.label, color = C.text, text = "PATTAYA"})
header.Name = "Header"
header.Position = UDim2.fromOffset(PAD + 20, 0)
header.Size = UDim2.new(1, -(PAD + 20) - 40, 0, HEADER_H)
header.TextScaled = true -- long GPS / circuit lines shrink (down to 10 px) instead of ending in "…"
header.TextTruncate = Enum.TextTruncate.None
do
	local lim = Instance.new("UITextSizeConstraint")
	lim.MaxTextSize = Theme.size.label
	lim.MinTextSize = 10
	lim.Parent = header
end
-- compact HUD only: GPS chip at the right end of the header; tap = the G key (next destination, then off) through
-- Bus "gps.cycle" -> PattayaGPSClient (same GPSRequest flow). Replaces the removed GPS touch button (TouchControls).
local gpsChip = Instance.new("TextButton")
gpsChip.Name = "GPSChip"
gpsChip.AnchorPoint = Vector2.new(1, 0)
gpsChip.Position = UDim2.new(1, -2, 0, -8) -- hit area 48 x 30: the 22 px header + the 8 px gap above the card
gpsChip.Size = UDim2.fromOffset(48, 30)
gpsChip.BackgroundTransparency = 1
gpsChip.AutoButtonColor = false
gpsChip.Selectable = false
gpsChip.Text = ""
gpsChip.ZIndex = 23
gpsChip.Visible = false
gpsChip.Parent = card
local gpsPill = text(gpsChip, {font = Theme.font.display, size = Theme.size.caption - 2, color = C.textDim, text = "GPS",
	align = Enum.TextXAlignment.Center, z = 24})
gpsPill.Name = "Pill"
gpsPill.AnchorPoint = Vector2.new(0.5, 1)
gpsPill.Position = UDim2.new(0.5, 0, 1, -3)
gpsPill.Size = UDim2.fromOffset(44, 16)
gpsPill.BackgroundColor3 = C.navy
gpsPill.BackgroundTransparency = Theme.alpha.panelDim
corner(gpsPill, Theme.radius.pill)
local gpsPillStroke = strokeOf(gpsPill, C.line, Theme.stroke.thin)
pressFx(gpsChip, gpsPill)
gpsChip.Activated:Connect(function()
	if Bus.count and Bus.count("gps.cycle") == 0 then
		Bus.fire("toast", {title = "GPS", body = "GPS is not ready yet", kind = "warn"})
		return
	end
	Bus.fire("gps.cycle")
end)

local compass = text(card, {font = Theme.font.display, size = Theme.size.label, color = C.text, text = "N",
	align = Enum.TextXAlignment.Center})
compass.Name = "Compass"
compass.AnchorPoint = Vector2.new(1, 0.5)
compass.Position = UDim2.new(1, -PAD, 0, HEADER_H / 2)
compass.Size = UDim2.fromOffset(24, 24)
compass.BackgroundColor3 = C.navy
compass.BackgroundTransparency = Theme.alpha.panelDim
corner(compass, Theme.radius.pill)
strokeOf(compass, C.line, Theme.stroke.thin)

local mapView = Instance.new("Frame") -- the clipped viewport the World container moves inside
mapView.Name = "MapView"
mapView.Position = UDim2.fromOffset(PAD, HEADER_H)
mapView.Size = UDim2.fromOffset(MAP_W, MAP_H)
mapView.BackgroundColor3 = COL.water
mapView.BackgroundTransparency = 0
mapView.BorderSizePixel = 0
mapView.ClipsDescendants = true
mapView.Parent = card
corner(mapView, Theme.radius.small)

local credit = text(card, {font = Theme.font.body, size = math.max(9, Theme.size.caption - 3), color = C.textMuted,
	text = "© OpenStreetMap contributors"})
credit.Name = "Credit"
credit.AnchorPoint = Vector2.new(0, 1)
credit.Position = UDim2.new(0, PAD + 46, 1, -PAD - 4)
credit.Size = UDim2.fromOffset(170, 12)
credit.TextStrokeColor3 = C.navy
credit.TextStrokeTransparency = 0.4

-- compass rose bottom-left inside the map (north-up map: N always points up), as in the owner mockup
local rose = text(card, {font = Theme.font.display, size = Theme.size.caption, color = C.text, text = "N",
	align = Enum.TextXAlignment.Center, z = 21})
rose.Name = "CompassRose"
rose.AnchorPoint = Vector2.new(0, 1)
rose.Position = UDim2.new(0, PAD + 6, 1, -PAD - 6)
rose.Size = UDim2.fromOffset(32, 32)
rose.TextYAlignment = Enum.TextYAlignment.Bottom
rose.BackgroundColor3 = C.navy
rose.BackgroundTransparency = Theme.alpha.panelDim
corner(rose, Theme.radius.pill)
strokeOf(rose, C.line, Theme.stroke.thin)
local roseTip = text(rose, {font = Theme.font.display, size = Theme.size.caption - 2, color = C.cyan, text = "▲",
	align = Enum.TextXAlignment.Center, z = 22})
roseTip.Position = UDim2.fromOffset(0, 2)
roseTip.Size = UDim2.new(1, 0, 0, 12)

-- district label inside the map (top-left), e.g. "CENTRAL PATTAYA"
local mapDistrict = text(card, {font = Theme.font.bold, size = Theme.size.label, color = C.text, text = "", z = 21})
mapDistrict.Name = "District"
mapDistrict.Position = UDim2.fromOffset(PAD + 10, HEADER_H + 8)
mapDistrict.Size = UDim2.fromOffset(MAP_W - TOUCH - 30, 18)
mapDistrict.TextStrokeColor3 = C.navy
mapDistrict.TextStrokeTransparency = 0.3

-- touch-sized controls (>= 44 px) on the right edge of the map view
local function ctrl(label: string, bottomIndex: number): TextButton
	local b = button(card, label, 22)
	b.Font = Theme.font.display
	b.TextSize = Theme.size.title
	b.AnchorPoint = Vector2.new(1, 1)
	b.Position = UDim2.new(1, -PAD - 4, 1, -PAD - 4 - (bottomIndex * (TOUCH + 6)))
	b.Size = UDim2.fromOffset(TOUCH, TOUCH)
	b.BackgroundColor3 = C.navy
	b.BackgroundTransparency = Theme.alpha.panel
	return b
end
local expandBtn = ctrl("⤢", 0)
expandBtn.Name = "Expand"
local zoomOutBtn = ctrl("−", 1)
zoomOutBtn.Name = "ZoomOut"
local zoomInBtn = ctrl("+", 2)
zoomInBtn.Name = "ZoomIn"

-- World container: every map layer, in world px at MINI_SCALE, scaled by one UIScale -----------------------------
local world = Instance.new("Frame")
world.Name = "World"
world.BackgroundTransparency = 1
world.Size = UDim2.fromOffset(0, 0)
world.Parent = mapView
local zoom = Instance.new("UIScale")
zoom.Scale = 1
zoom.Parent = world

local layers = {}
for i, name in {"Land", "Coast", "Roads", "Corridor", "Track", "Route", "Labels", "Pois", "Players", "Me"} do
	local f = Instance.new("Frame")
	f.Name = name
	f.BackgroundTransparency = 1
	f.Size = UDim2.fromOffset(0, 0)
	f.ZIndex = i
	f.Parent = world
	layers[name] = f
end

-- screen-constant sizes: registries resized by applyScale (only when the scale changes, never per frame)
local lineList = {} -- {f, len, t}
local routeSegs = {} -- pooled route segments, same shape as lineList entries
local routeUsed = 0
local trackSegs = {} -- pooled circuit track / pit lane / start-finish segments (rebuilt on attribute change only)
local trackUsed = 0
local scaledList = {} -- {f, w, h, stroke?, sw?}
local curScale = 1

local function sizeLine(e)
	e.f.Size = UDim2.fromOffset(e.len + e.t / curScale, e.t / curScale)
end
local function placeLine(e, x1: number, z1: number, x2: number, z2: number)
	local ax, az = px(x1, z1)
	local bx, bz = px(x2, z2)
	local dx, dz = bx - ax, bz - az
	e.len = math.sqrt(dx * dx + dz * dz)
	e.f.Position = UDim2.fromOffset((ax + bx) / 2, (az + bz) / 2)
	e.f.Rotation = math.deg(math.atan2(dz, dx))
	sizeLine(e)
end
local function newLine(parent: Instance, thickness: number, color: Color3, transparency: number?)
	local f = Instance.new("Frame")
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.BackgroundColor3 = color
	f.BackgroundTransparency = transparency or 0
	f.BorderSizePixel = 0
	f.ZIndex = (parent :: GuiObject).ZIndex
	f.Parent = parent
	return {f = f, len = 0, t = thickness}
end
local function line(parent: Instance, x1: number, z1: number, x2: number, z2: number, thickness: number, color: Color3, transparency: number?)
	local e = newLine(parent, thickness, color, transparency)
	placeLine(e, x1, z1, x2, z2)
	table.insert(lineList, e)
	return e.f
end
local function polyline(parent: Instance, flat: {number}, thickness: number, color: Color3, transparency: number?)
	for i = 1, #flat - 3, 2 do
		line(parent, flat[i], flat[i + 1], flat[i + 2], flat[i + 3], thickness, color, transparency)
	end
end
local function scaled(f: GuiObject, w: number, h: number, stroke: UIStroke?)
	local e = {f = f, w = w, h = h, stroke = stroke, sw = stroke and stroke.Thickness}
	table.insert(scaledList, e)
	f.Size = UDim2.fromOffset(w / curScale, h / curScale)
	return e
end

local function applyScale(s: number)
	curScale = s
	zoom.Scale = s
	for _, e in lineList do
		sizeLine(e)
	end
	for i = 1, routeUsed do
		sizeLine(routeSegs[i])
	end
	for i = 1, trackUsed do
		sizeLine(trackSegs[i])
	end
	for _, e in scaledList do
		e.f.Size = UDim2.fromOffset(e.w / s, e.h / s)
		if e.stroke then
			e.stroke.Thickness = e.sw / s
		end
	end
end

-- land: district polygons filled by horizontal spans (built once) -------------------------------------------------
local ROW = 50 -- studs per fill row
local function crossings(poly: {number}, z: number): {number}
	local xs = {}
	local n = #poly // 2
	for i = 1, n do
		local j = i % n + 1
		local x1, z1, x2, z2 = poly[2 * i - 1], poly[2 * i], poly[2 * j - 1], poly[2 * j]
		if (z1 <= z) ~= (z2 <= z) then
			table.insert(xs, x1 + (z - z1) * (x2 - x1) / (z2 - z1))
		end
	end
	table.sort(xs)
	return xs
end
for _, d in map.districts or {} do
	local poly = d.poly
	if poly and #poly >= 6 then
		local minZ, maxZ = math.huge, -math.huge
		for i = 2, #poly, 2 do
			minZ, maxZ = math.min(minZ, poly[i]), math.max(maxZ, poly[i])
		end
		local z = math.floor(minZ / ROW) * ROW + ROW / 2
		while z < maxZ do
			local xs = crossings(poly, z)
			for k = 1, #xs - 1, 2 do
				local ax, az = px(xs[k], z - ROW / 2)
				local bx = px(xs[k + 1], z)
				local f = Instance.new("Frame")
				f.Position = UDim2.fromOffset(ax, az)
				f.Size = UDim2.fromOffset(bx - ax, ROW * MINI_SCALE * 1.1)
				f.BackgroundColor3 = COL.land
				f.BorderSizePixel = 0
				f.ZIndex = 1
				f.Parent = layers.Land
			end
			z += ROW
		end
	end
end
for _, d in map.districts or {} do
	polyline(layers.Land, d.poly, 1.2, COL.district, 0.3)
end
for _, c in map.coast or {} do
	polyline(layers.Coast, c, 2, COL.coast, 0.55)
end
for _, r in map.roads or {} do
	polyline(layers.Roads, r.pts, if r.tier == 1 then 3 else 2, if r.tier == 1 then COL.express else COL.main, if r.tier == 1 then 0.1 else 0.25)
end
if corridor then
	for _, r in corridor.roads or {} do
		polyline(layers.Corridor, r.pts, 3, COL.corridor, 0.1)
	end
end

-- district labels (both views) ------------------------------------------------------------------------------------
for _, d in map.districts or {} do
	local mx, mz = px(d.x, d.z)
	local t = text(layers.Labels, {font = Theme.font.display, color = COL.label, text = string.upper(d.name),
		align = Enum.TextXAlignment.Center, z = layers.Labels.ZIndex})
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromOffset(mx, mz)
	t.TextScaled = true
	t.TextTransparency = 0.25
	t.TextStrokeColor3 = C.navy
	t.TextStrokeTransparency = 0.5
	scaled(t, 200, 14)
end

-- POI markers (reused data: job stands, bosses, race start, Bira; plus garage, circuits, event, players) -----------
local open = false
local view = "ALL" -- full map view: ALL / CITY / NEAR
local viewChosen = false -- true once the player pressed VIEW (then the compact default no longer applies)
local destinations = {} -- {{id, label}} from GPSUpdate "list"
local currentDest: string? = nil
local poiEntries = {} -- {badge, label, kind, poi, gpsId}
local onMarkerClick: (entry: any) -> () = function() end

local function badge(kind: string, x: number, z: number, labelText: string, size: number?)
	local k = KIND[kind] or KIND.race
	local mx, mz = px(x, z)
	local b = Instance.new("TextButton")
	b.Name = kind
	b.AnchorPoint = Vector2.new(0.5, 0.5)
	b.Position = UDim2.fromOffset(mx, mz)
	b.BackgroundColor3 = C.navy
	b.BackgroundTransparency = 0.1
	b.BorderSizePixel = 0
	b.AutoButtonColor = false
	b.Selectable = false
	b.Text = ""
	b.ZIndex = layers.Pois.ZIndex
	b.Parent = layers.Pois
	corner(b, Theme.radius.pill)
	local st = strokeOf(b, k.color, Theme.stroke.thick)
	scaled(b, size or ICON, size or ICON, st)
	local g = Instance.new("TextLabel")
	g.BackgroundTransparency = 1
	g.AnchorPoint = Vector2.new(0.5, 0.5)
	g.Position = UDim2.fromScale(0.5, 0.5)
	g.Size = UDim2.fromScale(0.7, 0.7)
	g.Font = Theme.font.display
	g.TextScaled = true
	g.TextColor3 = k.color
	g.Text = k.glyph
	g.ZIndex = b.ZIndex + 1
	g.Parent = b
	local label = Instance.new("TextLabel")
	label.AnchorPoint = Vector2.new(0.5, 1)
	label.Position = UDim2.new(0.5, 0, 0, 0)
	label.BackgroundTransparency = 1
	label.Font = Theme.font.bold
	label.TextScaled = true
	label.TextColor3 = k.color
	label.TextStrokeColor3 = C.navy
	label.TextStrokeTransparency = 0.3
	label.Text = labelText
	label.Visible = false
	label.ZIndex = b.ZIndex + 1
	label.Parent = b
	scaled(label, 170, 14)
	local entry = {badge = b, label = label, kind = kind, gpsId = nil :: string?, text = labelText}
	b.Activated:Connect(function() -- Activated: mouse click and touch tap
		if open then -- the minimap's markers are display-only
			onMarkerClick(entry)
		end
	end)
	table.insert(poiEntries, entry)
	return entry
end
local function moveBadge(entry, x: number, z: number)
	local mx, mz = px(x, z)
	entry.badge.Position = UDim2.fromOffset(mx, mz)
end

local circuitEntries = {} -- [circuit id] = entry (the Bira POI is reused for "bira")
for _, p in map.pois or {} do
	local x, z = p.x, p.z
	if p.kind == "bira" then
		local real = circuitPos("bira")
		if real then x, z = real.X, real.Z end
	end
	local e = badge(p.kind, x, z, p.label or p.id, if p.kind == "bira" or p.kind == "race" then ICON + 4 else ICON)
	e.poi = p
	if p.kind == "bira" then
		e.gpsId = "bira"
		circuitEntries.bira = e
	end
end
-- circuit entrances published later by CircuitServer (Circuit_<id> attributes): move Bira, add flags for others
local function onCircuitAttr(name: string)
	if string.sub(name, 1, 8) ~= "Circuit_" then
		return
	end
	local id = string.sub(name, 9)
	local v = mapModule:GetAttribute(name)
	if typeof(v) ~= "Vector3" then
		return
	end
	local e = circuitEntries[id]
	if e then
		moveBadge(e, v.X, v.Z)
	else
		e = badge("bira", v.X, v.Z, string.upper(id) .. " CIRCUIT", ICON + 4)
		e.gpsId = id
		circuitEntries[id] = e
		applyScale(curScale)
	end
end
for name in mapModule:GetAttributes() do
	onCircuitAttr(name)
end
mapModule.AttributeChanged:Connect(onCircuitAttr)

-- garage ring (workspace.PattayaGarage, Persistent model built by PattayaGarageServer)
task.spawn(function()
	local garage = workspace:WaitForChild("PattayaGarage", 120)
	local ring = garage and (garage :: Model).PrimaryPart
	if ring then
		badge("garage", ring.Position.X, ring.Position.Z, "GARAGE", ICON + 2)
		applyScale(curScale)
	end
end)

-- current event gathering ring (ReplicatedStorage.PattayaEvent: Phase, RingPos), pulsing while gathering
local eventEntry = badge("event", ORIGIN.x, ORIGIN.z, "EVENT", ICON)
eventEntry.badge.Visible = false
local pulse = Instance.new("Frame")
pulse.Name = "Pulse"
pulse.AnchorPoint = Vector2.new(0.5, 0.5)
pulse.Position = UDim2.fromScale(0.5, 0.5)
pulse.Size = UDim2.fromScale(1, 1)
pulse.BackgroundColor3 = KIND.event.color
pulse.BackgroundTransparency = 0.3
pulse.BorderSizePixel = 0
pulse.ZIndex = eventEntry.badge.ZIndex - 1
pulse.Parent = eventEntry.badge
corner(pulse, Theme.radius.pill)
local pulseTween = TweenService:Create(pulse, TweenInfo.new(1, Theme.motion.ease, Theme.motion.easeOut, -1),
	{Size = UDim2.fromScale(2.4, 2.4), BackgroundTransparency = 1})
local function setPulse(on: boolean)
	if on and not reducedMotion then
		pulseTween:Play()
	else
		pulseTween:Cancel()
		pulse.Size = UDim2.fromScale(1, 1)
		pulse.BackgroundTransparency = 0.3
	end
end
Bus.on("hud.reducedMotion", function(v)
	reducedMotion = v == true
	setPulse(eventEntry.badge.Visible)
end)
task.spawn(function()
	local state = ReplicatedStorage:WaitForChild("PattayaEvent", 60)
	if not state then
		return
	end
	local function refresh()
		local phase = state:GetAttribute("Phase")
		local at = state:GetAttribute("RingPos")
		local show = phase == "gathering" and typeof(at) == "Vector3" and at ~= Vector3.zero
		if show then
			moveBadge(eventEntry, at.X, at.Z)
			local title = state:GetAttribute("Title")
			eventEntry.label.Text = if type(title) == "string" and title ~= "" then title .. "  (J join)" else "EVENT"
		end
		eventEntry.badge.Visible = show
		setPulse(show)
	end
	state:GetAttributeChangedSignal("Phase"):Connect(refresh)
	state:GetAttributeChangedSignal("RingPos"):Connect(refresh)
	refresh()
end)

-- other players (nearest few), a fixed pool updated twice a second
local PLAYER_POOL = 10
local playerDots = {}
for i = 1, PLAYER_POOL do
	local d = Instance.new("Frame")
	d.Name = "Player" .. i
	d.AnchorPoint = Vector2.new(0.5, 0.5)
	d.BackgroundColor3 = COL.players
	d.BorderSizePixel = 0
	d.Visible = false
	d.ZIndex = layers.Players.ZIndex
	d.Parent = layers.Players
	corner(d, Theme.radius.pill)
	scaled(d, 9, 9, strokeOf(d, C.navy, Theme.stroke.thin))
	playerDots[i] = d
end

-- you: arrow (Roblox-shipped UI texture) + dot fallback, in the World so it moves with the map
local meDot = Instance.new("Frame")
meDot.Name = "MeDot"
meDot.AnchorPoint = Vector2.new(0.5, 0.5)
meDot.BackgroundColor3 = C.cyan
meDot.BorderSizePixel = 0
meDot.ZIndex = layers.Me.ZIndex
meDot.Parent = layers.Me
corner(meDot, Theme.radius.pill)
scaled(meDot, 8, 8)
local marker = Instance.new("ImageLabel")
marker.Name = "Me"
marker.AnchorPoint = Vector2.new(0.5, 0.5)
marker.BackgroundTransparency = 1
marker.Image = "rbxasset://textures/ui/TopBar/arrowUp.png" -- Roblox-shipped UI asset (no external content)
marker.ImageColor3 = COL.me
marker.ZIndex = layers.Me.ZIndex + 1
marker.Parent = layers.Me
scaled(marker, 20, 20)

-- GPS route on the map (pooled segments) --------------------------------------------------------------------------
local function setRoute(points: {Vector3}?)
	local n = 0
	if points then
		for i = 1, #points - 1 do
			n += 1
			local e = routeSegs[n]
			if not e then -- grows only when a route is longer than any before (on a route event, never per frame)
				e = newLine(layers.Route, 3.5, COL.route, 0)
				routeSegs[n] = e
			end
			e.f.Visible = true
			placeLine(e, points[i].X, points[i].Z, points[i + 1].X, points[i + 1].Z)
		end
	end
	for i = n + 1, #routeSegs do
		routeSegs[i].f.Visible = false
	end
	routeUsed = n
end

-- circuit track layer: CircuitPath_<id> (closed centreline, first point = start/finish) and CircuitPit_<id> (pit
-- lane), packed "x,z;x,z;..." in world studs on PattayaWorldMap by CircuitServer. Missing/garbled = no layer.
local trackBounds: {minX: number, maxX: number, minZ: number, maxZ: number}? = nil
local function unpackPath(v: any): {number}?
	if type(v) ~= "string" or v == "" then
		return nil
	end
	local flat = {}
	for xs, zs in string.gmatch(v, "(%-?[%d%.]+),(%-?[%d%.]+)") do
		local x, z = tonumber(xs), tonumber(zs)
		if x and z then
			table.insert(flat, x)
			table.insert(flat, z)
		end
	end
	return if #flat >= 4 then flat else nil
end
local function trackSeg(x1: number, z1: number, x2: number, z2: number, thickness: number, color: Color3, transparency: number)
	trackUsed += 1
	local e = trackSegs[trackUsed]
	if not e then
		e = newLine(layers.Track, thickness, color, transparency)
		trackSegs[trackUsed] = e
	end
	e.t = thickness
	e.f.BackgroundColor3 = color
	e.f.BackgroundTransparency = transparency
	e.f.Visible = true
	placeLine(e, x1, z1, x2, z2)
end
local function rebuildTrack()
	trackUsed = 0
	local b = {minX = math.huge, maxX = -math.huge, minZ = math.huge, maxZ = -math.huge}
	local function grow(flat: {number})
		for i = 1, #flat, 2 do
			b.minX, b.maxX = math.min(b.minX, flat[i]), math.max(b.maxX, flat[i])
			b.minZ, b.maxZ = math.min(b.minZ, flat[i + 1]), math.max(b.maxZ, flat[i + 1])
		end
	end
	for name, v in mapModule:GetAttributes() do
		if string.sub(name, 1, 12) == "CircuitPath_" then
			local flat = unpackPath(v)
			if flat then
				grow(flat)
				local n = #flat
				for i = 1, n - 1, 2 do
					local j = if i + 2 <= n then i + 2 else 1 -- closed loop
					trackSeg(flat[i], flat[i + 1], flat[j], flat[j + 1], 4, C.textDim, 0.05)
				end
				-- start/finish tick: perpendicular to the first leg through the first point
				local dx, dz = flat[3] - flat[1], flat[4] - flat[2]
				local l = math.sqrt(dx * dx + dz * dz)
				if l > 0 then
					local hx, hz = -dz / l * 40, dx / l * 40 -- 40 studs each side (about a track width)
					trackSeg(flat[1] - hx, flat[2] - hz, flat[1] + hx, flat[2] + hz, 4, C.yellow, 0)
				end
			end
		elseif string.sub(name, 1, 11) == "CircuitPit_" then
			local flat = unpackPath(v)
			if flat then
				grow(flat)
				for i = 1, #flat - 3, 2 do
					trackSeg(flat[i], flat[i + 1], flat[i + 2], flat[i + 3], 2, C.textMuted, 0.1)
				end
			end
		end
	end
	-- start/finish ticks above the track segments (siblings in the Track layer; pooled frames get reused, so set it)
	for i = 1, #trackSegs do
		local e = trackSegs[i]
		if i > trackUsed then
			e.f.Visible = false
		else
			e.f.ZIndex = layers.Track.ZIndex + (if e.f.BackgroundColor3 == C.yellow then 1 else 0)
		end
	end
	trackBounds = if b.minX < math.huge then b else nil
end
rebuildTrack()
mapModule.AttributeChanged:Connect(function(name: string)
	if string.sub(name, 1, 12) == "CircuitPath_" or string.sub(name, 1, 11) == "CircuitPit_" then
		rebuildTrack()
	end
end)

applyScale(ZOOMS[zoomIndex])

-- full map overlay (built once) -----------------------------------------------------------------------------------
local dim = Instance.new("TextButton") -- sinks clicks behind the panel; clicking outside the panel closes
dim.Name = "Dim"
dim.Size = UDim2.fromScale(1, 1)
dim.BackgroundColor3 = C.navy
dim.BackgroundTransparency = Theme.alpha.overlay
dim.AutoButtonColor = false
dim.Selectable = false
dim.Text = ""
dim.Parent = fullGui
local panel = Instance.new("Frame")
panel.Name = "Panel"
panel.AnchorPoint = Vector2.new(0.5, 0.5)
panel.Position = UDim2.fromScale(0.5, 0.5)
panel.BackgroundColor3 = C.surface
panel.BackgroundTransparency = Theme.alpha.panel * 0.5
panel.BorderSizePixel = 0
panel.Active = true
panel.Parent = fullGui
corner(panel, Theme.radius.panel)
strokeOf(panel, C.line, Theme.stroke.normal)
local pAccent = accent:Clone()
pAccent.Parent = panel

local TITLE_H = 60
local fTitle = text(panel, {font = Theme.font.display, size = Theme.size.title, color = C.text, text = "MIDNIGHT PATTAYA"})
fTitle.Position = UDim2.fromOffset(Theme.pad.l, 8)
fTitle.Size = UDim2.new(0.5, 0, 0, 26)
local fSub = text(panel, {font = Theme.font.body, size = Theme.size.caption, color = C.textDim,
	text = "WORLD MAP  ·  M close  ·  tap a flag or a destination for GPS"})
fSub.Position = UDim2.fromOffset(Theme.pad.l, 34)
fSub.Size = UDim2.new(0.6, 0, 0, 16)
local fGps = text(panel, {font = Theme.font.bold, size = Theme.size.label, color = C.cyan, text = "",
	align = Enum.TextXAlignment.Right})
fGps.AnchorPoint = Vector2.new(1, 0)
local closeBtn = button(panel, "X")
closeBtn.Name = "Close"
closeBtn.Font = Theme.font.display
closeBtn.AnchorPoint = Vector2.new(1, 0)
closeBtn.Position = UDim2.new(1, -Theme.pad.m, 0, 8)
closeBtn.Size = UDim2.fromOffset(TOUCH, TOUCH)
local viewBtn = button(panel, "VIEW: ALL")
viewBtn.Name = "View"
viewBtn.AnchorPoint = Vector2.new(1, 0)
viewBtn.Position = UDim2.new(1, -Theme.pad.m - TOUCH - Theme.pad.s, 0, 8)
viewBtn.Size = UDim2.fromOffset(120, TOUCH)
fGps.Position = UDim2.new(1, -Theme.pad.m - TOUCH - 120 - Theme.pad.s * 3, 0, 8)
fGps.Size = UDim2.fromOffset(320, TOUCH)

local fullView = Instance.new("Frame")
fullView.Name = "MapView"
fullView.BackgroundColor3 = COL.water
fullView.BorderSizePixel = 0
fullView.ClipsDescendants = true
fullView.Parent = panel
corner(fullView, Theme.radius.small)
local fCredit = text(panel, {font = Theme.font.body, size = Theme.size.caption, color = C.textDim,
	text = "© OpenStreetMap contributors (ODbL)", align = Enum.TextXAlignment.Right, z = 22})
fCredit.Name = "Credit"
fCredit.AnchorPoint = Vector2.new(1, 1)
fCredit.TextStrokeColor3 = C.navy
fCredit.TextStrokeTransparency = 0.4

local side = Instance.new("ScrollingFrame")
side.Name = "Sidebar"
side.BackgroundTransparency = 1
side.BorderSizePixel = 0
side.ScrollBarThickness = 4
side.ScrollBarImageColor3 = C.line
side.AutomaticCanvasSize = Enum.AutomaticSize.Y
side.CanvasSize = UDim2.new()
side.ZIndex = 20
side.Parent = panel
local sideList = Instance.new("UIListLayout")
sideList.Padding = UDim.new(0, Theme.pad.s)
sideList.SortOrder = Enum.SortOrder.LayoutOrder
sideList.Parent = side
local function sideHeading(label: string, order: number): TextLabel
	local t = text(side, {font = Theme.font.bold, size = Theme.size.caption, color = C.purple, text = label})
	t.Size = UDim2.new(1, -8, 0, 18)
	t.LayoutOrder = order
	return t
end
local info = text(side, {font = Theme.font.body, size = Theme.size.caption, color = C.textDim,
	text = "Tap a marker to see what it is."})
info.Size = UDim2.new(1, -8, 0, 34)
info.TextWrapped = true
info.TextTruncate = Enum.TextTruncate.None
info.LayoutOrder = 1
sideHeading("DESTINATIONS", 2)
local clearBtn = button(side, "CLEAR GPS")
clearBtn.Name = "ClearGPS"
clearBtn.Size = UDim2.new(1, -8, 0, TOUCH)
clearBtn.LayoutOrder = 500
clearBtn.TextColor3 = C.textDim
sideHeading("LEGEND", 600)
local legendOrder = 600
local function legendRow(color: Color3, glyph: string, label: string, round: boolean)
	legendOrder += 1
	local row = Instance.new("Frame")
	row.BackgroundTransparency = 1
	row.Size = UDim2.new(1, -8, 0, 22)
	row.LayoutOrder = legendOrder
	row.Parent = side
	local sw = Instance.new("TextLabel")
	sw.Size = UDim2.fromOffset(if round then 20 else 20, if round then 20 else 4)
	sw.AnchorPoint = Vector2.new(0, 0.5)
	sw.Position = UDim2.new(0, 0, 0.5, 0)
	sw.BackgroundColor3 = if round then C.navy else color
	sw.BorderSizePixel = 0
	sw.Font = Theme.font.display
	sw.TextScaled = true
	sw.TextColor3 = color
	sw.Text = glyph
	sw.ZIndex = 21
	sw.Parent = row
	if round then
		corner(sw, Theme.radius.pill)
		strokeOf(sw, color, Theme.stroke.thick)
	end
	local t = text(row, {font = Theme.font.body, size = Theme.size.caption, color = C.textDim, text = label, z = 21})
	t.Position = UDim2.fromOffset(30, 0)
	t.Size = UDim2.new(1, -30, 1, 0)
end
for _, kind in {"taxi", "delivery", "boss", "race", "bira", "garage", "event"} do
	local k = KIND[kind]
	legendRow(k.color, k.glyph, k.legend, true)
end
legendRow(COL.players, "", "Other drivers", true)
legendRow(COL.me, "▲", "You", true)
legendRow(COL.route, "", "GPS route", false)
legendRow(COL.express, "", "Sukhumvit (express)", false)
legendRow(C.textDim, "", "Circuit track (yellow = start/finish)", false)

local destButtons = {} -- rebuilt only when the server sends a new list
local function linkSelection()
	local chain = {viewBtn}
	for _, b in destButtons do
		table.insert(chain, b)
	end
	table.insert(chain, clearBtn)
	for i, b in chain do
		b.NextSelectionUp = chain[i - 1]
		b.NextSelectionDown = chain[i + 1]
	end
	viewBtn.NextSelectionRight = closeBtn
	closeBtn.NextSelectionLeft = viewBtn
	closeBtn.NextSelectionDown = chain[2] or clearBtn
end

-- GPS: same remote as before, plus the Bus notice (tagged "map" so PattayaGPSClient does not send it twice)
local function pick(id: string?)
	if GPSRequest then
		GPSRequest:FireServer(id)
	end
	Bus.fire("gps.set", id, "map")
end

local function styleDestButtons()
	for _, b in destButtons do
		local isCurrent = b:GetAttribute("DestId") == currentDest
		b.TextColor3 = if isCurrent then C.cyan else C.text
		local st = b:FindFirstChildOfClass("UIStroke")
		if st then st.Color = if isCurrent then C.cyan else C.line end
	end
end
local function rebuildDestinations()
	for _, b in destButtons do
		b:Destroy()
	end
	table.clear(destButtons)
	for i, d in destinations do
		local b = button(side, string.upper(tostring(d.label)))
		b.Name = "Dest_" .. tostring(d.id)
		b.Size = UDim2.new(1, -8, 0, TOUCH)
		b.LayoutOrder = 10 + i
		b:SetAttribute("DestId", d.id)
		b.Activated:Connect(function()
			pick(d.id)
		end)
		table.insert(destButtons, b)
	end
	styleDestButtons()
	linkSelection()
end
linkSelection()
clearBtn.Activated:Connect(function()
	pick(nil)
end)

onMarkerClick = function(entry)
	local kindText = (KIND[entry.kind] or KIND.race).legend
	local district = entry.poi and entry.poi.district
	info.Text = ("%s\n%s%s"):format(entry.text, kindText, if district then "  ·  " .. district else "")
	if entry.gpsId then
		pick(entry.gpsId)
	end
end

-- header (card + full map title bar) ------------------------------------------------------------------------------
local districtName: string? = nil
local CIRCUIT_MODE = {TimeAttack = "TIME ATTACK", FreePractice = "FREE PRACTICE", TrackDay = "TRACK DAY",
	CircuitRace = "RACE", PrivateRoom = "PRIVATE ROOM"}
local function updateHeader()
	mapDistrict.Text = districtName or ""
	local lbl = player:GetAttribute("GPS_Label")
	local km = player:GetAttribute("GPS_Km")
	if player:GetAttribute("CircuitActive") == true then -- inside a circuit session: venue + session mode
		local name = player:GetAttribute("CircuitName")
		local mode = player:GetAttribute("CircuitMode")
		local s = string.upper(if type(name) == "string" and name ~= "" then name else "CIRCUIT")
		if type(mode) == "string" and mode ~= "" then
			s ..= "  •  " .. (CIRCUIT_MODE[mode] or string.upper(mode))
		end
		header.Text = s
		header.TextColor3 = C.text
		pin.BackgroundColor3 = C.yellow
		fGps.Text = s
	elseif type(lbl) == "string" and lbl ~= "" then
		local s = string.upper(lbl)
		if type(km) == "number" then
			s = ("%s  •  %.1f KM"):format(s, km)
		end
		header.Text = s
		header.TextColor3 = C.text
		pin.BackgroundColor3 = C.cyan
		fGps.Text = "GPS  " .. s
	else
		header.Text = if districtName then "PATTAYA  •  " .. string.upper(districtName) else "PATTAYA"
		header.TextColor3 = C.textDim
		pin.BackgroundColor3 = C.textMuted
		fGps.Text = if districtName then string.upper(districtName) else ""
	end
	local routed = type(lbl) == "string" and lbl ~= ""
	gpsPill.TextColor3 = if routed then C.cyan else C.textDim
	gpsPillStroke.Color = if routed then C.cyan else C.line
end
player:GetAttributeChangedSignal("GPS_Label"):Connect(updateHeader)
player:GetAttributeChangedSignal("GPS_Km"):Connect(updateHeader)
for _, a in {"CircuitActive", "CircuitName", "CircuitMode"} do
	player:GetAttributeChangedSignal(a):Connect(updateHeader)
end

local function districtAt(x: number, z: number): string?
	for _, d in map.districts or {} do
		if d.poly and #d.poly >= 6 then
			local xs = crossings(d.poly, z)
			for k = 1, #xs - 1, 2 do
				if x >= xs[k] and x <= xs[k + 1] then
					return d.name
				end
			end
		end
	end
	return nil
end

-- placement: MidnightHUD.BottomLeft when the new HUD is on, else the old MinimapHUD ScreenGui -----------------------
local hudAnchor: GuiObject? = nil
local wantCard = true -- Bus "minimap.visible"
local function refreshCard()
	card.Visible = wantCard and not open
end
-- mobile landscape: Roblox's thumbstick lives in the bottom-left; keep the card above a safe margin and shrink it
-- (on top of the root HUD UIScale) so header + map still fit between the top-left player card and the thumbstick
local cardScale = Instance.new("UIScale")
cardScale.Parent = card
local TOUCH_MARGIN = 170 -- screen px kept clear above the bottom edge for the thumbstick/jump zone
local TOP_RESERVE = 110 -- screen px for the top bar + player card
local function isTouch(): boolean
	if Responsive and type(Responsive.isTouch) == "function" then
		local ok, v = pcall(Responsive.isTouch)
		if ok then return v == true end
	end
	return UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled
end
local function rootScale(): number -- the root HUD's UIScale (Responsive.attach), 1 if none
	-- Responsive.attach puts the UIScale on each anchor frame (MidnightScale), not on the ScreenGui
	local s = hudAnchor and hudAnchor:FindFirstChildOfClass("UIScale")
	if not s then
		local hud = hudAnchor and hudAnchor:FindFirstAncestorWhichIsA("ScreenGui")
		s = hud and hud:FindFirstChildOfClass("UIScale")
	end
	return if s then s.Scale else 1
end
-- compact / touch card (docs/UI_SYSTEM.md "Touch layout", MidnightHUD gui attribute Compact): 150 x 120 SCREEN px
-- (the card's UIScale cancels the root HUD scale), header 22 px, no compass / rose / district label, the three
-- controls as a 36 px column just right of the card (zoom in, zoom out, expand). Desktop values restored otherwise.
local viewW, viewH = MAP_W, MAP_H -- the visible map area (card or full map), world px
local forceRedraw = true
local cardCompact: boolean? = nil
local function layoutCard(on: boolean)
	if cardCompact == on then
		return
	end
	cardCompact = on
	local w, h, hh, pad = CARD_W, CARD_H, HEADER_H, PAD
	if on then
		w, h, hh, pad = 150, 120, 22, 4
	end
	MAP_W, MAP_H = w - pad * 2, h - hh - pad
	card.Size = UDim2.fromOffset(w, h)
	pin.Position = UDim2.fromOffset(pad + 2, hh / 2)
	pin.Size = UDim2.fromOffset(if on then 8 else 12, if on then 8 else 12)
	header.Position = UDim2.fromOffset(pad + (if on then 14 else 20), 0)
	header.Size = UDim2.new(1, -(pad + (if on then 14 else 20)) - (if on then 52 else 40), 0, hh) -- compact: GPS chip
	gpsChip.Visible = on
	local lim = header:FindFirstChildOfClass("UITextSizeConstraint")
	if lim then
		lim.MaxTextSize = if on then Theme.size.caption else Theme.size.label
		lim.MinTextSize = if on then 8 else 10
	end
	compass.Visible = not on
	rose.Visible = not on
	mapDistrict.Visible = not on
	mapView.Position = UDim2.fromOffset(pad, hh)
	mapView.Size = UDim2.fromOffset(MAP_W, MAP_H)
	credit.Position = if on then UDim2.new(0, pad + 2, 1, -pad - 1) else UDim2.new(0, PAD + 46, 1, -PAD - 4)
	credit.Size = if on then UDim2.fromOffset(MAP_W - 4, 9) else UDim2.fromOffset(170, 12)
	credit.TextSize = if on then 8 else math.max(9, Theme.size.caption - 3)
	for i, b in {zoomInBtn, zoomOutBtn, expandBtn} do
		if on then
			b.AnchorPoint = Vector2.new(0, 0)
			b.Position = UDim2.new(1, 6, 0, (i - 1) * 42)
			b.Size = UDim2.fromOffset(36, 36)
			b.TextSize = Theme.size.body + 2
		else
			local bottomIndex = 3 - i -- expand 0, zoom out 1, zoom in 2 (as built)
			b.AnchorPoint = Vector2.new(1, 1)
			b.Position = UDim2.new(1, -PAD - 4, 1, -PAD - 4 - (bottomIndex * (TOUCH + 6)))
			b.Size = UDim2.fromOffset(TOUCH, TOUCH)
			b.TextSize = Theme.size.title
		end
	end
	if not open then
		viewW, viewH = MAP_W, MAP_H
	end
	forceRedraw = true
end

local function place()
	local useNew = hudAnchor ~= nil and hudAnchor.Parent ~= nil and player:GetAttribute("MidnightHUD") == true
	local touch = isTouch()
	local cam = workspace.CurrentCamera
	local vpY = if cam then cam.ViewportSize.Y else 720
	local hudGui = hudAnchor and hudAnchor:FindFirstAncestorWhichIsA("ScreenGui")
	local small = useNew and hudGui ~= nil and hudGui:GetAttribute("Compact") == true
	layoutCard(small)
	if small then
		card.AnchorPoint = Vector2.new(0, 0)
		card.Position = UDim2.fromOffset(0, 0)
		cardScale.Scale = 1 / math.max(rootScale(), 0.01) -- screen px (MidnightHUD places BottomLeft under the card)
		card.Parent = hudAnchor
	elseif useNew then
		local rs = rootScale()
		local margin = if touch then TOUCH_MARGIN / rs else 0
		card.AnchorPoint = Vector2.new(0, 1)
		card.Position = UDim2.new(0, 0, 1, -margin)
		cardScale.Scale = if touch then math.clamp((vpY - TOUCH_MARGIN - TOP_RESERVE) / (CARD_H * rs), 0.45, 1) else 1
		card.Parent = hudAnchor
	else
		card.AnchorPoint = Vector2.new(0, 0)
		card.Position = UDim2.fromOffset(16, 60)
		cardScale.Scale = if touch then math.clamp(vpY * 0.5 / CARD_H, 0.45, 1) else 1
		card.Parent = legacyGui
	end
	refreshCard()
end
local playerGui = player:WaitForChild("PlayerGui")
legacyGui.Parent = playerGui
fullGui.Parent = playerGui
local function findAnchor(hud: Instance?)
	if hud and hud:IsA("ScreenGui") and hud.Name == "MidnightHUD" then
		local a = hud:WaitForChild("BottomLeft", 5)
		if a and a:IsA("GuiObject") then
			hudAnchor = a
			hud:GetAttributeChangedSignal("Compact"):Connect(place)
			place()
		end
	end
end
task.spawn(function()
	findAnchor(playerGui:WaitForChild("MidnightHUD", 10))
end)
playerGui.ChildAdded:Connect(function(child)
	if child.Name == "MidnightHUD" and not hudAnchor then
		task.spawn(findAnchor, child)
	end
end)
player:GetAttributeChangedSignal("MidnightHUD"):Connect(place)
place()
Bus.on("hud.scale", function()
	task.defer(place) -- the root UIScale changed (viewport or player HUD scale)
end)
UserInputService.LastInputTypeChanged:Connect(function()
	local touch = isTouch()
	if touch ~= (card:GetAttribute("Touch") == true) then
		card:SetAttribute("Touch", touch)
		place()
	end
end)
Bus.on("minimap.visible", function(v)
	wantCard = v ~= false
	refreshCard()
end)

-- GPS events: route on the map, destination list ------------------------------------------------------------------
if GPSUpdate then
	GPSUpdate.OnClientEvent:Connect(function(kind, payload)
		if kind == "route" and payload and payload.route then
			currentDest = payload.id
			setRoute(payload.route)
		elseif kind == "list" and type(payload) == "table" then
			destinations = payload
			rebuildDestinations()
		elseif kind == "arrived" or kind == "clear" then
			currentDest = nil
			setRoute(nil)
		end
		styleDestButtons()
	end)
end

-- views / redraw --------------------------------------------------------------------------------------------------
local function boundsOf(name: string)
	local b = map.bounds
	local minX, maxX, minZ, maxZ = b.minX, b.maxX, b.minZ, b.maxZ
	if name == "ALL" then -- whole world: city + corridor + circuit venues
		local extra = {}
		if corridor and corridor.bounds then table.insert(extra, corridor.bounds) end
		if trackBounds then table.insert(extra, trackBounds) end
		for _, e in extra do
			minX, maxX = math.min(minX, e.minX), math.max(maxX, e.maxX)
			minZ, maxZ = math.min(minZ, e.minZ), math.max(maxZ, e.maxZ)
		end
	end
	return minX, maxX, minZ, maxZ
end
local function applyView()
	if view == "NEAR" then
		applyScale(1)
	else
		local minX, maxX, minZ, maxZ = boundsOf(view)
		local spanX, spanZ = (maxX - minX) * MINI_SCALE, (maxZ - minZ) * MINI_SCALE
		local s = math.min(viewW / spanX, viewH / spanZ) * 0.92
		applyScale(s)
		local cx, cz = px((minX + maxX) / 2, (minZ + maxZ) / 2)
		world.Position = UDim2.fromOffset(viewW / 2 - cx * s, viewH / 2 - cz * s)
	end
	viewBtn.Text = "VIEW: " .. view
	local labelsAll = view == "NEAR"
	for _, e in poiEntries do
		e.label.Visible = open and (labelsAll or (e.kind ~= "taxi" and e.kind ~= "delivery"))
	end
	forceRedraw = true
end

local function layoutFull()
	local cam = workspace.CurrentCamera
	local vp = cam and cam.ViewportSize or Vector2.new(1280, 720)
	local w = math.min(vp.X - 24, 1240)
	-- this ScreenGui ignores the GUI inset, so on a phone (viewport height under 600) the title row with VIEW / close
	-- would sit in Roblox's top-bar band; keep the whole panel below the inset there (leader, 2026-10-20)
	local topInset = if vp.Y < 600 then GuiService:GetGuiInset().Y else 0
	local h = math.min(vp.Y - 24 - topInset, 860)
	panel.Size = UDim2.fromOffset(w, h)
	panel.Position = UDim2.new(0.5, 0, 0.5, topInset / 2)
	local sideW = math.clamp(math.floor(w * 0.3), 180, 300)
	local mw, mh = w - sideW - Theme.pad.m * 3, h - TITLE_H - Theme.pad.m
	fullView.Position = UDim2.fromOffset(Theme.pad.m, TITLE_H)
	fullView.Size = UDim2.fromOffset(mw, mh)
	fCredit.Position = UDim2.fromOffset(Theme.pad.m + mw - 8, TITLE_H + mh - 4)
	fCredit.Size = UDim2.fromOffset(math.min(300, mw), 16)
	side.Position = UDim2.fromOffset(w - sideW - Theme.pad.m, TITLE_H)
	side.Size = UDim2.fromOffset(sideW, mh)
	fGps.Visible = w >= 900 -- narrow screens: the title bar keeps the buttons, the minimap header has the GPS line
	viewW, viewH = mw, mh
end

local function lastInputIsGamepad(): boolean
	local t = UserInputService:GetLastInputType()
	return t == Enum.UserInputType.Gamepad1 or t == Enum.UserInputType.Gamepad2
		or t == Enum.UserInputType.Gamepad3 or t == Enum.UserInputType.Gamepad4
end

local setOpen: (boolean) -> ()
setOpen = function(on: boolean)
	if on == open then
		return
	end
	open = on
	if on then
		fullGui.Enabled = true
		layoutFull()
		world.Parent = fullView
		-- compact / touch HUD (owner mobile test 2026-10-19): the whole-world ALL view is unreadable on a phone, so the
		-- map opens on CITY until the player picks a view themselves
		if not viewChosen then
			local hudGui = player:FindFirstChildOfClass("PlayerGui") and player.PlayerGui:FindFirstChild("MidnightHUD")
			view = if hudGui and hudGui:GetAttribute("Compact") == true then "CITY" else "ALL"
		end
		applyView()
		if #destinations == 0 and GPSRequest then
			GPSRequest:FireServer("list")
		end
		ContextActionService:BindActionAtPriority("WorldMapClose", function(_, state)
			if state == Enum.UserInputState.Begin then
				setOpen(false)
			end
			return Enum.ContextActionResult.Sink
		end, false, Enum.ContextActionPriority.High.Value, Enum.KeyCode.ButtonB)
		if lastInputIsGamepad() then
			GuiService.SelectedObject = destButtons[1] or viewBtn
		end
	else
		ContextActionService:UnbindAction("WorldMapClose")
		local sel = GuiService.SelectedObject
		if sel and sel:IsDescendantOf(fullGui) then
			GuiService.SelectedObject = nil
		end
		world.Parent = mapView
		viewW, viewH = MAP_W, MAP_H
		for _, e in poiEntries do
			e.label.Visible = false
		end
		applyScale(ZOOMS[zoomIndex])
		fullGui.Enabled = false
		forceRedraw = true
	end
	refreshCard()
end

local function worldMapAction(_, state)
	if state == Enum.UserInputState.Begin then
		setOpen(not open)
	end
	return Enum.ContextActionResult.Pass
end
ContextActionService:BindAction("WorldMap", worldMapAction, true, Enum.KeyCode.M, Enum.KeyCode.ButtonSelect)
ContextActionService:SetTitle("WorldMap", "MAP")
ContextActionService:SetPosition("WorldMap", UDim2.new(1, -410, 1, -240))
-- compact touch layout (docs/UI_SYSTEM.md "Round 3: touch controls"): MidnightUI.TouchControls owns the button grid
local function touchRegister(name: string, opts: {[string]: any})
	local m = game:GetService("ReplicatedStorage"):FindFirstChild("MidnightUI")
	m = m and m:FindFirstChild("TouchControls")
	if m then (require(m) :: any).register(name, opts) end
end
touchRegister("WorldMap", {hide = true, handler = worldMapAction, keys = {Enum.KeyCode.M, Enum.KeyCode.ButtonSelect},
	title = "MAP", position = UDim2.new(1, -410, 1, -240)})
Bus.on("map.toggle", function(v)
	if type(v) == "boolean" then
		setOpen(v)
	else
		setOpen(not open)
	end
end)
expandBtn.Activated:Connect(function()
	setOpen(true)
end)
closeBtn.Activated:Connect(function()
	setOpen(false)
end)
dim.Activated:Connect(function()
	setOpen(false)
end)
local VIEWS = {"ALL", "CITY", "NEAR"}
viewBtn.Activated:Connect(function()
	local i = table.find(VIEWS, view) or 1
	view = VIEWS[i % #VIEWS + 1]
	viewChosen = true
	applyView()
end)
local function setZoom(i: number)
	zoomIndex = math.clamp(i, 1, #ZOOMS)
	if not open then
		applyScale(ZOOMS[zoomIndex])
		forceRedraw = true
	end
	zoomInBtn.TextTransparency = if zoomIndex == #ZOOMS then 0.6 else 0
	zoomOutBtn.TextTransparency = if zoomIndex == 1 then 0.6 else 0
end
zoomInBtn.Activated:Connect(function()
	setZoom(zoomIndex + 1)
end)
zoomOutBtn.Activated:Connect(function()
	setZoom(zoomIndex - 1)
end)
setZoom(zoomIndex)
local cam = workspace.CurrentCamera
if cam then
	cam:GetPropertyChangedSignal("ViewportSize"):Connect(function()
		place()
		if open then
			layoutFull()
			applyView()
		end
	end)
end

local function focus(): (Vector3, number)
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	-- in a car: the car model's PrimaryPart, else the seat itself (a nested seat/model without PrimaryPart must not
	-- drop the arrow back to the map origin, e.g. inside the circuit venue)
	local part = if seat and seat:IsA("VehicleSeat")
		then ((seat.Parent and seat.Parent:IsA("Model") and (seat.Parent :: Model).PrimaryPart) or seat)
		else (char and char:FindFirstChild("HumanoidRootPart"))
	if part then
		local lv = part.CFrame.LookVector
		return part.Position, math.deg(math.atan2(lv.X, -lv.Z))
	end
	return Vector3.new(ORIGIN.x, 0, ORIGIN.z), 0
end

local function otherPos(plr: Player): Vector3?
	local char = plr.Character
	if not char then
		return nil
	end
	local hum = char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	-- as focus(): a seat whose parent is not a Model (or has no PrimaryPart) uses the seat itself; reading
	-- PrimaryPart of a non-Model threw inside RenderStepped every 0.5 s and froze every other player's dot
	local part = if seat and seat:IsA("VehicleSeat")
		then ((seat.Parent and seat.Parent:IsA("Model") and (seat.Parent :: Model).PrimaryPart) or seat)
		else char:FindFirstChild("HumanoidRootPart")
	return part and (part :: BasePart).Position or nil
end
local nearBuf = {} -- reused {dist, pos} rows
local function updatePlayers(me: Vector3)
	local n = 0
	for _, plr in Players:GetPlayers() do
		if plr ~= player then
			local p = otherPos(plr)
			if p then
				n += 1
				local row = nearBuf[n] or {}
				nearBuf[n] = row
				row.d, row.p = (Vector3.new(p.X - me.X, 0, p.Z - me.Z)).Magnitude, p
			end
		end
	end
	for i = n + 1, #nearBuf do
		nearBuf[i].d = math.huge
	end
	table.sort(nearBuf, function(a, b) return a.d < b.d end)
	for i = 1, PLAYER_POOL do
		local row = nearBuf[i]
		local dot = playerDots[i]
		if row and row.d < math.huge then
			local mx, mz = px(row.p.X, row.p.Z)
			dot.Position = UDim2.fromOffset(mx, mz)
			dot.Visible = true
		else
			dot.Visible = false
		end
	end
end

local lastMx, lastMz, lastHead = math.huge, math.huge, math.huge
local lastPlayers, lastDistrict = 0, 0
RunService.RenderStepped:Connect(function()
	local now = os.clock()
	local pos, heading = focus()
	local mx, mz = px(pos.X, pos.Z)
	local s = curScale
	-- redraw only when the player moved >= 1 screen px or turned >= 2 degrees (or after a zoom/view change)
	if forceRedraw or math.abs(mx - lastMx) * s >= 1 or math.abs(mz - lastMz) * s >= 1 or math.abs(heading - lastHead) >= 2 then
		forceRedraw = false
		lastMx, lastMz, lastHead = mx, mz, heading
		local at = UDim2.fromOffset(mx, mz)
		marker.Position = at
		marker.Rotation = heading
		meDot.Position = at
		if not open or view == "NEAR" then
			world.Position = UDim2.fromOffset(viewW / 2 - mx * s, viewH / 2 - mz * s)
		end
	end
	if now - lastPlayers >= 0.5 then
		lastPlayers = now
		updatePlayers(pos)
	end
	if now - lastDistrict >= 1 then
		lastDistrict = now
		local name = districtAt(pos.X, pos.Z)
		if name ~= districtName then
			districtName = name
			updateHeader()
		end
	end
end)
updateHeader()
