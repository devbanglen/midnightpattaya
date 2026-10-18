-- GPS client: G cycles the destination (Bira Circuit, back to Central Pattaya, off). Draws the route as a cyan line
-- on the road (rebuilt from the server's refresh every few seconds, only the next ~2,500 studs to keep parts low),
-- a cyan arrow over the car, a HUD line with the distance, and a toast on arrival.
-- Premium HUD (docs/UI_CONTRACT.md, docs/UI_MAP.md): colours come from ReplicatedStorage.MidnightUI.Theme. While the
-- LocalPlayer attribute MidnightHUD == true (set locally by ui-core) the on-screen GPS panel, hint and centre toast hide: the minimap header in
-- MidnightHUD.BottomLeft shows destination + distance (published here as the client-local LocalPlayer attributes
-- GPS_Label / GPS_Km) and route set / arrived / cleared go to the Bus "toast". With the attribute false the old GPSHUD
-- shows again. Bus "gps.set" (id | nil) from other HUD scripts (quick menu) is forwarded to GPSRequest; the map script
-- calls GPSRequest itself and tags its own Bus fire with source "map", which is not forwarded a second time.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
if not remotes then
	return
end
local GPSRequest = remotes:WaitForChild("GPSRequest", 30)
local GPSUpdate = remotes:WaitForChild("GPSUpdate", 30)
if not (GPSRequest and GPSUpdate) then
	return
end

-- design tokens + client bus (ReplicatedStorage.MidnightUI); the GPS keeps working without them
local uiFolder = ReplicatedStorage:WaitForChild("MidnightUI", 10)
local themeModule = uiFolder and uiFolder:FindFirstChild("Theme")
local busModule = uiFolder and uiFolder:FindFirstChild("Bus")
local Theme = if themeModule then require(themeModule) :: any else nil
local Bus = if busModule then require(busModule) :: any else nil

local CYAN = if Theme then Theme.color.cyan else Color3.fromRGB(0, 220, 255)
local DRAW_STUDS = 2500

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil

local gui = Instance.new("ScreenGui")
gui.Name = "GPSHUD"
gui.ResetOnSpawn = false
local panel = Instance.new("TextLabel")
panel.AnchorPoint = Vector2.new(1, 0)
panel.Position = UDim2.new(1, -16, 0, 150)
panel.Size = UDim2.fromOffset(330, 30)
panel.BackgroundColor3 = if Theme then Theme.color.navy else Color3.fromRGB(0, 30, 40)
panel.BackgroundTransparency = if Theme then Theme.alpha.panel else 0.3
panel.Font = if Theme then Theme.font.bold else Enum.Font.GothamBold
panel.TextScaled = true
panel.TextColor3 = CYAN
panel.Visible = false
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, if Theme then Theme.radius.button else 8)
if Style then
	Style.accent(panel, 8)
end
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0, 1)
hint.Position = UDim2.new(0, 16, 1, -84)
hint.Size = UDim2.fromOffset(360, 20)
hint.BackgroundTransparency = 1
hint.Font = if Theme then Theme.font.body else Enum.Font.GothamMedium
hint.TextSize = 15
hint.TextColor3 = if Theme then Theme.color.textDim else Color3.fromRGB(150, 230, 255)
hint.TextStrokeTransparency = 0.5
hint.TextXAlignment = Enum.TextXAlignment.Left
hint.Text = "G  GPS: Bira Circuit"
hint.Visible = false
hint.Parent = gui
local toast = Instance.new("TextLabel")
toast.AnchorPoint = Vector2.new(0.5, 0.5)
toast.Position = UDim2.new(0.5, 0, 0.36, 0)
toast.Size = UDim2.fromOffset(620, 40)
toast.BackgroundTransparency = 1
toast.Font = if Theme then Theme.font.display else Enum.Font.GothamBlack
toast.TextScaled = true
toast.TextColor3 = CYAN
toast.TextStrokeTransparency = 0.3
toast.Visible = false
toast.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

-- legacy-hide: the new HUD (ui-core sets the local LocalPlayer attribute MidnightHUD = true) replaces the panel, hint and centre toast
local function newHud(): boolean
	return player:GetAttribute("MidnightHUD") == true
end

local function showToast(text: string)
	if newHud() then
		return -- notify() sends the Bus toast instead while the new HUD is on
	end
	toast.Text = text
	toast.Visible = true
	local stamp = os.clock()
	toast:SetAttribute("Stamp", stamp)
	task.delay(4, function()
		if toast:GetAttribute("Stamp") == stamp then toast.Visible = false end
	end)
end

-- a toast for the new HUD (Bus "toast") or the old centre toast, never both
local function notify(text: string, kind: string?)
	if newHud() and Bus then
		Bus.fire("toast", {title = "GPS", body = text, kind = kind or "info"})
	else
		showToast(text)
	end
end

local destinations = {} -- {{id, label}, ...} from the server
local current: string? = nil
local route: {Vector3}? = nil
local label = ""
local folder: Folder? = nil
local arrow: Part? = nil

local function clearDrawing()
	if folder then folder:Destroy() end
	if arrow then arrow:Destroy() end
	folder, arrow = nil, nil
end

local function neon(size: Vector3, cf: CFrame, transparency: number): Part
	local p = Instance.new("Part")
	p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false
	p.Material = Enum.Material.Neon
	p.Color = CYAN
	p.Size = size
	p.CFrame = cf
	p.Transparency = transparency
	p.Parent = folder
	return p
end

local function draw(pts: {Vector3})
	clearDrawing()
	folder = Instance.new("Folder")
	folder.Name = "GPSRoute"
	local drawn = 0
	for i = 1, #pts - 1 do
		local a, b = pts[i] + Vector3.new(0, 0.35, 0), pts[i + 1] + Vector3.new(0, 0.35, 0)
		local len = (b - a).Magnitude
		if len > 0.5 then
			neon(Vector3.new(2.5, 0.2, len), CFrame.lookAt((a + b) / 2, b), 0.4)
			drawn += len
			if drawn > DRAW_STUDS then break end
		end
	end
	folder.Parent = workspace
	arrow = neon(Vector3.new(1.2, 0.4, 7), CFrame.new(), 0)
	arrow.Name = "GPSArrow"
	local tip = neon(Vector3.new(4, 0.4, 3), CFrame.new(), 0)
	tip.Shape = Enum.PartType.Wedge
	tip.Name = "Tip"
	tip.Parent = arrow
end

-- minimap header data (client-local attributes, read by PattayaMinimapClient): GPS_Label (string | nil), GPS_Km
local function publish(text: string?, km: number?)
	player:SetAttribute("GPS_Label", text)
	player:SetAttribute("GPS_Km", km)
end
local function refreshPanel()
	panel.Visible = route ~= nil and not newHud()
end
player:GetAttributeChangedSignal("MidnightHUD"):Connect(function()
	refreshPanel()
	if newHud() then
		hint.Visible = false
		toast.Visible = false
	end
end)

GPSUpdate.OnClientEvent:Connect(function(kind, payload, extra)
	if kind == "list" then
		destinations = payload
	elseif kind == "route" then
		local changed = payload.id ~= current or route == nil -- the server re-sends the route every few seconds
		current, route, label = payload.id, payload.route, payload.label
		draw(payload.route)
		refreshPanel()
		if changed then
			publish(label, if type(payload.length) == "number" then payload.length * 0.28 / 1000 else nil)
			if newHud() and Bus then
				Bus.fire("toast", {title = "GPS", body = tostring(label), kind = "info"})
			end
		end
	elseif kind == "arrived" then
		current, route = nil, nil
		clearDrawing()
		refreshPanel()
		publish(nil, nil)
		notify(("You have arrived: %s"):format(tostring(payload)), "reward")
	elseif kind == "clear" then
		local had = route ~= nil
		current, route = nil, nil
		clearDrawing()
		refreshPanel()
		publish(nil, nil)
		if payload then
			notify(tostring(payload), "warn")
		elseif had and newHud() and Bus then
			Bus.fire("toast", {title = "GPS", body = "GPS off", kind = "info"})
		end
	end
end)
GPSRequest:FireServer("list")

-- other HUD scripts (quick menu, missions) pick a destination through the Bus; the map tags its own fires "map"
if Bus then
	Bus.on("gps.set", function(id, source)
		if source ~= "map" then
			GPSRequest:FireServer(id)
		end
	end)
end

local function inCar(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

-- G: next destination in the list, then off (also the minimap header GPS chip of the compact HUD: Bus "gps.cycle")
local function gpsCycle(_, state)
	if state ~= Enum.UserInputState.Begin then
		return Enum.ContextActionResult.Pass
	end
	if #destinations == 0 then
		GPSRequest:FireServer("list")
		notify("GPS: no destinations on the map yet", "warn")
		return Enum.ContextActionResult.Pass
	end
	local nextIndex = 1
	if current then
		for i, d in destinations do
			if d.id == current then nextIndex = i + 1 end
		end
	end
	if nextIndex > #destinations then
		GPSRequest:FireServer(nil)
		showToast("GPS off") -- new HUD: the server's "clear" reply sends the Bus toast
	else
		local d = destinations[nextIndex]
		current = d.id
		GPSRequest:FireServer(d.id)
		showToast(("GPS: %s"):format(d.label)) -- new HUD: the server's "route" reply sends the Bus toast
	end
	return Enum.ContextActionResult.Pass
end
ContextActionService:BindAction("GPSCycle", gpsCycle, true, Enum.KeyCode.G, Enum.KeyCode.DPadUp)
ContextActionService:SetTitle("GPSCycle", "GPS")
ContextActionService:SetPosition("GPSCycle", UDim2.new(1, -340, 1, -240))
-- compact touch layout (docs/UI_SYSTEM.md "Round 3: touch controls"): MidnightUI.TouchControls owns the button grid
local function touchRegister(name: string, opts: {[string]: any})
	local m = game:GetService("ReplicatedStorage"):FindFirstChild("MidnightUI")
	m = m and m:FindFirstChild("TouchControls")
	if m then (require(m) :: any).register(name, opts) end
end
touchRegister("GPSCycle", {hide = true, handler = gpsCycle, keys = {Enum.KeyCode.G, Enum.KeyCode.DPadUp}, title = "GPS",
	position = UDim2.new(1, -340, 1, -240)})
if Bus then
	Bus.on("gps.cycle", function()
		gpsCycle(nil, Enum.UserInputState.Begin)
	end)
end

local function focusPart(chassis: BasePart?): BasePart?
	if chassis then
		return chassis
	end
	local char = player.Character
	return char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
end

-- distance left along the route, not as the crow flies: project the car onto the nearest route segment (XZ) and
-- add the gap to it, the rest of that segment and every segment after it (the old version counted from the first
-- point more than 25 studs away, which is the route start once the car has left it, so the number never fell)
local function remainingStuds(pos: Vector3, pts: {Vector3}): number
	local n = #pts
	if n == 0 then
		return 0
	elseif n == 1 then
		return Vector3.new(pts[1].X - pos.X, 0, pts[1].Z - pos.Z).Magnitude
	end
	local bestD, bestI, bestT = math.huge, 1, 0
	for i = 1, n - 1 do
		local a, b = pts[i], pts[i + 1]
		local dx, dz = b.X - a.X, b.Z - a.Z
		local l2 = dx * dx + dz * dz
		local t = if l2 > 0 then math.clamp(((pos.X - a.X) * dx + (pos.Z - a.Z) * dz) / l2, 0, 1) else 0
		local ex, ez = pos.X - (a.X + dx * t), pos.Z - (a.Z + dz * t)
		local d = ex * ex + ez * ez
		if d < bestD then
			bestD, bestI, bestT = d, i, t
		end
	end
	local remaining = math.sqrt(bestD) + (pts[bestI + 1] - pts[bestI]).Magnitude * (1 - bestT)
	for i = bestI + 1, n - 1 do
		remaining += (pts[i + 1] - pts[i]).Magnitude
	end
	return remaining
end

local lastPublish = 0
RunService.RenderStepped:Connect(function()
	local chassis = inCar()
	-- minimap header distance at <= 4 Hz, in the car or on foot
	local now = os.clock()
	if route and now - lastPublish >= 0.25 then
		lastPublish = now
		local part = focusPart(chassis)
		if part then
			publish(label, remainingStuds(part.Position, route) * 0.28 / 1000)
		end
	end
	hint.Visible = chassis ~= nil and current == nil and #destinations > 0 and not newHud()
	if hint.Visible and destinations[1] then
		hint.Text = ("G  GPS: %s"):format(destinations[1].label)
	end
	if not (route and chassis and arrow) then
		return
	end
	-- aim the arrow at the first route point still ahead of the car
	local pos = chassis.Position
	local target
	for i = 1, #route do
		local q = route[i]
		if Vector3.new(q.X - pos.X, 0, q.Z - pos.Z).Magnitude > 25 then
			target = q
			break
		end
	end
	target = target or route[#route]
	local from = pos + Vector3.new(0, 9, 0)
	local flat = Vector3.new(target.X - from.X, 0, target.Z - from.Z)
	if flat.Magnitude > 1 then
		arrow.CFrame = CFrame.lookAt(from, from + flat)
		local tip = arrow:FindFirstChild("Tip") :: Part
		tip.CFrame = arrow.CFrame * CFrame.new(0, 0, -5)
	end
	if panel.Visible then
		panel.Text = ("GPS  %s   %.1f km"):format(label, remainingStuds(pos, route) * 0.28 / 1000)
	end
end)
