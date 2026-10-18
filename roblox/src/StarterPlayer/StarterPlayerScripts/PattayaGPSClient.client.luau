-- GPS client: G cycles the destination (Bira Circuit, back to Central Pattaya, off). Draws the route as a cyan line
-- on the road (rebuilt from the server's refresh every few seconds, only the next ~2,500 studs to keep parts low),
-- a cyan arrow over the car, a HUD line with the distance, and a toast on arrival.
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

local CYAN = Color3.fromRGB(0, 220, 255)
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
panel.BackgroundColor3 = Color3.fromRGB(0, 30, 40)
panel.BackgroundTransparency = 0.3
panel.Font = Enum.Font.GothamBold
panel.TextScaled = true
panel.TextColor3 = CYAN
panel.Visible = false
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 8)
if Style then
	Style.accent(panel, 8)
end
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0, 1)
hint.Position = UDim2.new(0, 16, 1, -84)
hint.Size = UDim2.fromOffset(360, 20)
hint.BackgroundTransparency = 1
hint.Font = Enum.Font.GothamMedium
hint.TextSize = 15
hint.TextColor3 = Color3.fromRGB(150, 230, 255)
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
toast.Font = Enum.Font.GothamBlack
toast.TextScaled = true
toast.TextColor3 = CYAN
toast.TextStrokeTransparency = 0.3
toast.Visible = false
toast.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

local function showToast(text: string)
	toast.Text = text
	toast.Visible = true
	local stamp = os.clock()
	toast:SetAttribute("Stamp", stamp)
	task.delay(4, function()
		if toast:GetAttribute("Stamp") == stamp then toast.Visible = false end
	end)
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

GPSUpdate.OnClientEvent:Connect(function(kind, payload, extra)
	if kind == "list" then
		destinations = payload
	elseif kind == "route" then
		current, route, label = payload.id, payload.route, payload.label
		draw(payload.route)
		panel.Visible = true
	elseif kind == "arrived" then
		current, route = nil, nil
		clearDrawing()
		panel.Visible = false
		showToast(("You have arrived: %s"):format(tostring(payload)))
	elseif kind == "clear" then
		current, route = nil, nil
		clearDrawing()
		panel.Visible = false
		if payload then showToast(tostring(payload)) end
	end
end)
GPSRequest:FireServer("list")

local function inCar(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

-- G: next destination in the list, then off
ContextActionService:BindAction("GPSCycle", function(_, state)
	if state ~= Enum.UserInputState.Begin then
		return Enum.ContextActionResult.Pass
	end
	if #destinations == 0 then
		GPSRequest:FireServer("list")
		showToast("GPS: no destinations on the map yet")
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
		showToast("GPS off")
	else
		local d = destinations[nextIndex]
		current = d.id
		GPSRequest:FireServer(d.id)
		showToast(("GPS: %s"):format(d.label))
	end
	return Enum.ContextActionResult.Pass
end, true, Enum.KeyCode.G, Enum.KeyCode.DPadUp)
ContextActionService:SetTitle("GPSCycle", "GPS")
ContextActionService:SetPosition("GPSCycle", UDim2.new(1, -340, 1, -240))

RunService.RenderStepped:Connect(function()
	local chassis = inCar()
	hint.Visible = chassis ~= nil and current == nil and #destinations > 0
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
	-- distance left along the route (from the first point ahead), not as the crow flies
	local remaining = 0
	local started = false
	for i = 1, #route - 1 do
		if not started and Vector3.new(route[i].X - pos.X, 0, route[i].Z - pos.Z).Magnitude > 25 then
			started = true
			remaining += Vector3.new(route[i].X - pos.X, 0, route[i].Z - pos.Z).Magnitude
		end
		if started then
			remaining += (route[i + 1] - route[i]).Magnitude
		end
	end
	panel.Text = ("GPS  %s   %.1f km"):format(label, remaining * 0.28 / 1000)
end)
