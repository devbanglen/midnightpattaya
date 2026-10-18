-- Minimap + world map (MIDNIGHT PATTAYA). Data: ReplicatedStorage.PattayaWorldMap (main roads, coast, districts,
-- POIs; world studs) and, when present, ReplicatedStorage.PattayaCorridorMap (the road to the Bira Circuit).
-- Minimap: north-up, centred on the car (or the character), 1 px = 4 studs, top-left of the screen. The whole map
-- is drawn once as Frames inside one container; each frame only the container moves, so the cost is one position.
-- M (or the MAP button) opens the full map: districts, POI icons; clicking the Bira icon (or any destination the GPS
-- server knows) starts the GPS to it. The GPS route (GPSUpdate "route") is drawn on both.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

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

local MINI_SCALE = 0.25 -- px per stud on the minimap
local MINI_SIZE = 230
local COL = {
	bg = Color3.fromRGB(12, 10, 26), land = Color3.fromRGB(28, 26, 48), sea = Color3.fromRGB(10, 30, 56),
	express = Color3.fromRGB(255, 200, 80), main = Color3.fromRGB(200, 205, 225), corridor = Color3.fromRGB(255, 200, 80),
	coast = Color3.fromRGB(60, 150, 200), route = Color3.fromRGB(0, 220, 255), car = Color3.fromRGB(255, 70, 140),
	taxi = Color3.fromRGB(255, 200, 30), delivery = Color3.fromRGB(40, 210, 130), boss = Color3.fromRGB(230, 40, 50),
	race = Color3.fromRGB(255, 255, 255), bira = Color3.fromRGB(0, 220, 255), district = Color3.fromRGB(170, 160, 210),
}
local ORIGIN = map.origin or {x = 20000, z = 0}

-- a circuit entrance published by CircuitServer replaces the "pending corridor" placeholder for its POI
local function circuitPos(id: string): Vector3?
	local v = mapModule:GetAttribute("Circuit_" .. id)
	return if typeof(v) == "Vector3" then v else nil
end

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil

local gui = Instance.new("ScreenGui")
gui.Name = "MinimapHUD"
gui.ResetOnSpawn = false
gui.DisplayOrder = 5

-- window: minimap by default, full map when open ------------------------------------------------------------------
local window = Instance.new("Frame")
window.Name = "Window"
window.AnchorPoint = Vector2.new(0, 0)
window.Position = UDim2.fromOffset(16, 60)
window.Size = UDim2.fromOffset(MINI_SIZE, MINI_SIZE)
window.BackgroundColor3 = COL.sea
window.BackgroundTransparency = 0.15
window.BorderSizePixel = 0
window.ClipsDescendants = true
window.Parent = gui
Instance.new("UICorner", window).CornerRadius = UDim.new(0, 12)
local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(0, 220, 255)
stroke.Thickness = 1.5
stroke.Transparency = 0.4
stroke.Parent = window

local world = Instance.new("Frame") -- everything in map pixels at MINI_SCALE; moved each frame, scaled by UIScale
world.Name = "World"
world.BackgroundTransparency = 1
world.Size = UDim2.fromOffset(0, 0)
world.Parent = window
local zoom = Instance.new("UIScale")
zoom.Scale = 1
zoom.Parent = world

local function px(x: number, z: number): (number, number)
	return (x - ORIGIN.x) * MINI_SCALE, (z - ORIGIN.z) * MINI_SCALE
end

local function line(parent: Instance, x1: number, z1: number, x2: number, z2: number, thickness: number, color: Color3, transparency: number?): Frame
	local ax, az = px(x1, z1)
	local bx, bz = px(x2, z2)
	local dx, dz = bx - ax, bz - az
	local len = math.sqrt(dx * dx + dz * dz)
	local f = Instance.new("Frame")
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.Position = UDim2.fromOffset((ax + bx) / 2, (az + bz) / 2)
	f.Size = UDim2.fromOffset(len + thickness, thickness)
	f.Rotation = math.deg(math.atan2(dz, dx))
	f.BackgroundColor3 = color
	f.BackgroundTransparency = transparency or 0
	f.BorderSizePixel = 0
	f.Parent = parent
	return f
end

local function polyline(parent: Instance, flat: {number}, thickness: number, color: Color3, transparency: number?, scaleOverride: number?)
	for i = 1, #flat - 3, 2 do
		line(parent, flat[i], flat[i + 1], flat[i + 2], flat[i + 3], thickness, color, transparency)
	end
end

-- districts (land shading) -> coast -> roads -> corridor -> POIs -> route -> car
local layers = {}
for _, name in {"Land", "Coast", "Roads", "Corridor", "Pois", "Route", "Labels"} do
	local f = Instance.new("Frame")
	f.Name = name
	f.BackgroundTransparency = 1
	f.Size = UDim2.fromOffset(0, 0)
	f.Parent = world
	layers[name] = f
end
for _, d in map.districts or {} do
	polyline(layers.Land, d.poly, 1.2, COL.district, 0.75)
end
for _, c in map.coast or {} do
	polyline(layers.Coast, c, 2, COL.coast, 0.2)
end
for _, r in map.roads or {} do
	polyline(layers.Roads, r.pts, if r.tier == 1 then 3 else 2, if r.tier == 1 then COL.express else COL.main, if r.tier == 1 then 0.1 else 0.25)
end
if corridor then
	for _, r in corridor.roads or {} do
		polyline(layers.Corridor, r.pts, 3, COL.corridor, 0.1)
	end
end

local poiButtons = {} -- shown only on the full map
local function poiDot(p, color: Color3, size: number, x: number, z: number)
	local mx, mz = px(x, z)
	local dot = Instance.new("TextButton")
	dot.AnchorPoint = Vector2.new(0.5, 0.5)
	dot.Position = UDim2.fromOffset(mx, mz)
	dot.Size = UDim2.fromOffset(size, size)
	dot.BackgroundColor3 = color
	dot.BorderSizePixel = 0
	dot.Text = ""
	dot.AutoButtonColor = false
	dot.Parent = layers.Pois
	Instance.new("UICorner", dot).CornerRadius = UDim.new(1, 0)
	local label = Instance.new("TextLabel")
	label.AnchorPoint = Vector2.new(0.5, 1)
	label.Position = UDim2.new(0.5, 0, 0, -2)
	label.Size = UDim2.fromOffset(160, 14)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.GothamBold
	label.TextSize = 11
	label.TextColor3 = color
	label.TextStrokeTransparency = 0.3
	label.Text = p.label or p.id
	label.Visible = false
	label.Parent = dot
	poiButtons[dot] = {poi = p, label = label}
	return dot
end
for _, p in map.pois or {} do
	local x, z = p.x, p.z
	if p.kind == "bira" then
		local real = circuitPos("bira")
		if real then x, z = real.X, real.Z end
	end
	local color = COL[p.kind] or COL.main
	local dot = poiDot(p, color, if p.kind == "bira" or p.kind == "race" then 7 else 4, x, z)
	if p.kind == "bira" and GPSRequest then
		dot.MouseButton1Click:Connect(function()
			GPSRequest:FireServer("bira")
		end)
	end
end
for _, d in map.districts or {} do
	local mx, mz = px(d.x, d.z)
	local t = Instance.new("TextLabel")
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromOffset(mx, mz)
	t.Size = UDim2.fromOffset(200, 16)
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextSize = 12
	t.TextColor3 = COL.district
	t.TextTransparency = 0.2
	t.Text = string.upper(d.name)
	t.Visible = false
	t.Parent = layers.Labels
end

-- car marker (screen space, centre of the minimap) and route ---------------------------------------------------------
local marker = Instance.new("ImageLabel")
marker.AnchorPoint = Vector2.new(0.5, 0.5)
marker.Size = UDim2.fromOffset(16, 16)
marker.BackgroundTransparency = 1
marker.Image = "rbxasset://textures/ui/TopBar/arrowUp.png" -- Roblox-shipped UI asset (no external content)
marker.ImageColor3 = COL.car
marker.ZIndex = 5
marker.Parent = window
local markerDot = Instance.new("Frame") -- fallback if the image fails to load
markerDot.AnchorPoint = Vector2.new(0.5, 0.5)
markerDot.Size = UDim2.fromOffset(7, 7)
markerDot.BackgroundColor3 = COL.car
markerDot.BorderSizePixel = 0
markerDot.ZIndex = 4
markerDot.Parent = window
Instance.new("UICorner", markerDot).CornerRadius = UDim.new(1, 0)

local title = Instance.new("TextLabel")
title.AnchorPoint = Vector2.new(0, 0)
title.Position = UDim2.fromOffset(8, 4)
title.Size = UDim2.fromOffset(200, 14)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 11
title.TextXAlignment = Enum.TextXAlignment.Left
title.TextColor3 = Color3.fromRGB(190, 200, 230)
title.Text = "M  map"
title.ZIndex = 6
title.Parent = window
local credit = Instance.new("TextLabel")
credit.AnchorPoint = Vector2.new(1, 1)
credit.Position = UDim2.new(1, -6, 1, -3)
credit.Size = UDim2.fromOffset(260, 12)
credit.BackgroundTransparency = 1
credit.Font = Enum.Font.Gotham
credit.TextSize = 9
credit.TextXAlignment = Enum.TextXAlignment.Right
credit.TextColor3 = Color3.fromRGB(150, 160, 190)
credit.Text = "© OpenStreetMap contributors"
credit.ZIndex = 6
credit.Parent = window
if Style then
	title.Font = Style.TITLE_FONT
	Style.accent(window, 12).ZIndex = 7
end
gui.Parent = player:WaitForChild("PlayerGui")

if GPSUpdate then
	GPSUpdate.OnClientEvent:Connect(function(kind, payload)
		layers.Route:ClearAllChildren()
		if kind == "route" and payload.route then
			local flat = {}
			for _, v in payload.route do
				table.insert(flat, v.X)
				table.insert(flat, v.Z)
			end
			polyline(layers.Route, flat, 3, COL.route, 0)
		end
	end)
end

-- full map toggle -------------------------------------------------------------------------------------------------
local open = false
local function setOpen(on: boolean)
	open = on
	local cam = workspace.CurrentCamera
	local vp = cam and cam.ViewportSize or Vector2.new(1280, 720)
	if on then
		local w = math.min(vp.X - 40, 1100)
		local h = math.min(vp.Y - 90, 820)
		window.Size = UDim2.fromOffset(w, h)
		window.Position = UDim2.fromOffset((vp.X - w) / 2, (vp.Y - h) / 2 + 10)
		local b = map.bounds
		local extra = corridor and corridor.bounds
		local maxX = math.max(b.maxX, extra and extra.maxX or b.maxX)
		local minX = math.min(b.minX, extra and extra.minX or b.minX)
		local spanX = (maxX - minX) * MINI_SCALE
		local spanZ = (b.maxZ - b.minZ) * MINI_SCALE
		zoom.Scale = math.min(w / spanX, h / spanZ) * 0.92
		title.Text = "MIDNIGHT PATTAYA   (M close, click a marker for GPS)"
	else
		window.Size = UDim2.fromOffset(MINI_SIZE, MINI_SIZE)
		window.Position = UDim2.fromOffset(16, 60)
		zoom.Scale = 1
		title.Text = "M  map"
	end
	for _, entry in poiButtons do
		entry.label.Visible = on
	end
	for _, l in layers.Labels:GetChildren() do
		l.Visible = on
	end
	marker.Visible = true
end
ContextActionService:BindAction("WorldMap", function(_, state)
	if state == Enum.UserInputState.Begin then
		setOpen(not open)
	end
	return Enum.ContextActionResult.Pass
end, true, Enum.KeyCode.M, Enum.KeyCode.ButtonSelect)
ContextActionService:SetTitle("WorldMap", "MAP")
ContextActionService:SetPosition("WorldMap", UDim2.new(1, -410, 1, -240))

local function focus(): (Vector3, number)
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	local part = if seat and seat:IsA("VehicleSeat") then seat.Parent.PrimaryPart else (char and char:FindFirstChild("HumanoidRootPart"))
	if part then
		local lv = part.CFrame.LookVector
		return part.Position, math.deg(math.atan2(lv.X, -lv.Z))
	end
	return Vector3.new(ORIGIN.x, 0, ORIGIN.z), 0
end

RunService.RenderStepped:Connect(function()
	local pos, heading = focus()
	local size = window.AbsoluteSize
	if open then
		-- whole map centred
		local b = map.bounds
		local extra = corridor and corridor.bounds
		local maxX = math.max(b.maxX, extra and extra.maxX or b.maxX)
		local minX = math.min(b.minX, extra and extra.minX or b.minX)
		local cx, cz = px((minX + maxX) / 2, (b.minZ + b.maxZ) / 2)
		world.Position = UDim2.fromOffset(size.X / 2 - cx * zoom.Scale, size.Y / 2 - cz * zoom.Scale)
		local mx, mz = px(pos.X, pos.Z)
		marker.Position = UDim2.fromOffset(size.X / 2 + (mx - cx) * zoom.Scale, size.Y / 2 + (mz - cz) * zoom.Scale)
	else
		local mx, mz = px(pos.X, pos.Z)
		world.Position = UDim2.fromOffset(size.X / 2 - mx, size.Y / 2 - mz)
		marker.Position = UDim2.fromOffset(size.X / 2, size.Y / 2)
	end
	marker.Rotation = heading
	markerDot.Position = marker.Position
end)
