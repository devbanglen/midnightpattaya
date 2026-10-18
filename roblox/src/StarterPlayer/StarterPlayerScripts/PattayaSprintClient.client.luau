-- Street Sprint client: H key / SPRINT button asks the server for a route from here; shows local checkpoint gates,
-- a GPS arrow over the car pointing at the next checkpoint, distance/time HUD, and a reward toast for any race.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
if not remotes then
	return
end
local RequestSprint = remotes:WaitForChild("RequestSprint")
local SprintUpdate = remotes:WaitForChild("SprintUpdate")

local GOLD, CYAN, WHITE = Color3.fromRGB(255, 200, 40), Color3.fromRGB(0, 200, 255), Color3.fromRGB(255, 255, 255)

-- HUD -------------------------------------------------------------------------------------------------------------
local gui = Instance.new("ScreenGui")
gui.Name = "SprintHUD"
gui.ResetOnSpawn = false
local panel = Instance.new("TextLabel")
panel.AnchorPoint = Vector2.new(0.5, 0)
panel.Position = UDim2.new(0.5, 0, 0, 86)
panel.Size = UDim2.fromOffset(520, 40)
panel.BackgroundColor3 = Color3.fromRGB(40, 10, 50)
panel.BackgroundTransparency = 0.3
panel.Font = Enum.Font.GothamBlack
panel.TextScaled = true
panel.TextColor3 = WHITE
panel.Visible = false
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 10)
local toast = Instance.new("TextLabel")
toast.AnchorPoint = Vector2.new(0.5, 0.5)
toast.Position = UDim2.new(0.5, 0, 0.32, 0)
toast.Size = UDim2.fromOffset(620, 46)
toast.BackgroundTransparency = 1
toast.Font = Enum.Font.GothamBlack
toast.TextScaled = true
toast.TextColor3 = GOLD
toast.TextStrokeTransparency = 0.3
toast.Visible = false
toast.Parent = gui
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0, 1)
hint.Position = UDim2.new(0, 16, 1, -40)
hint.Size = UDim2.fromOffset(360, 20)
hint.BackgroundTransparency = 1
hint.Font = Enum.Font.GothamMedium
hint.TextSize = 15
hint.TextColor3 = Color3.fromRGB(255, 180, 240)
hint.TextStrokeTransparency = 0.5
hint.TextXAlignment = Enum.TextXAlignment.Left
hint.Text = "H  start a Street Sprint from here"
hint.Visible = false
hint.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

local function showToast(text: string, seconds: number)
	toast.Text = text
	toast.Visible = true
	local stamp = os.clock()
	toast:SetAttribute("Stamp", stamp)
	task.delay(seconds, function()
		if toast:GetAttribute("Stamp") == stamp then
			toast.Visible = false
		end
	end)
end

player:GetAttributeChangedSignal("LastRewardAt"):Connect(function()
	showToast(player:GetAttribute("LastReward") or "", 5)
end)
player:GetAttributeChangedSignal("RaceMessage"):Connect(function()
	local m = player:GetAttribute("RaceMessage")
	if m and m ~= "" then showToast(m, 4) end
end)

-- sprint state ------------------------------------------------------------------------------------------------
local sprint -- {gates = {Model}, cps = {Vector3}, next, start, timeLimit, length}
local folder: Folder? = nil
local arrow: Part? = nil

local function clear()
	if folder then folder:Destroy() end
	if arrow then arrow:Destroy() end
	folder, arrow, sprint = nil, nil, nil
	panel.Visible = false
end

local function paint(i: number, color: Color3)
	local g = sprint and sprint.gates[i]
	if g then
		for _, p in g:GetChildren() do p.Color = color end
	end
end

local function buildGates(cps: {Vector3}, dirs: {Vector3}): {Model}
	folder = Instance.new("Folder")
	folder.Name = "SprintGates"
	local gates = {}
	for i, c in cps do
		local m = Instance.new("Model")
		local right = Vector3.new(-dirs[i].Z, 0, dirs[i].X)
		local final = i == #cps
		for _, s in {-1, 1} do
			local post = Instance.new("Part")
			post.Anchored, post.CanCollide, post.CanQuery, post.CanTouch = true, false, false, false
			post.Material = Enum.Material.Neon
			post.Size = Vector3.new(1.2, if final then 26 else 16, 1.2)
			post.Position = c + right * s * 24 + Vector3.new(0, post.Size.Y / 2, 0)
			post.Color = if final then WHITE else CYAN
			post.Parent = m
		end
		m.Parent = folder
		gates[i] = m
	end
	folder.Parent = workspace
	arrow = Instance.new("Part")
	arrow.Name = "GPSArrow"
	arrow.Anchored, arrow.CanCollide, arrow.CanQuery, arrow.CanTouch = true, false, false, false
	arrow.Size = Vector3.new(1.2, 0.4, 7)
	arrow.Material = Enum.Material.Neon
	arrow.Color = GOLD
	local tip = Instance.new("Part")
	tip.Anchored, tip.CanCollide, tip.CanQuery, tip.CanTouch = true, false, false, false
	tip.Shape = Enum.PartType.Wedge
	tip.Size = Vector3.new(4, 0.4, 3)
	tip.Material = Enum.Material.Neon
	tip.Color = GOLD
	tip.Name = "Tip"
	tip.Parent = arrow
	arrow.Parent = workspace
	return gates
end

SprintUpdate.OnClientEvent:Connect(function(kind, payload)
	if kind == "start" then
		clear()
		sprint = {cps = payload.checkpoints, next = 1, start = payload.start, timeLimit = payload.timeLimit, length = payload.length}
		sprint.gates = buildGates(payload.checkpoints, payload.dirs)
		paint(1, GOLD)
		panel.Visible = true
		showToast(("STREET SPRINT  %.1f km"):format(payload.length * 0.28 / 1000), 2.5)
	elseif kind == "next" and sprint then
		paint(sprint.next, Color3.fromRGB(60, 60, 70))
		sprint.next = payload
		paint(payload, GOLD)
	elseif kind == "finish" then
		clear()
		showToast(("SPRINT FINISHED  %.2f s"):format(payload.time), 4)
	elseif kind == "stop" then
		clear()
		showToast(tostring(payload), 3)
	end
end)

local function inCar(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

ContextActionService:BindAction("StreetSprint", function(_, state)
	if state == Enum.UserInputState.Begin and inCar() and not sprint then
		RequestSprint:FireServer()
	end
	return Enum.ContextActionResult.Pass
end, true, Enum.KeyCode.H, Enum.KeyCode.ButtonX)
ContextActionService:SetTitle("StreetSprint", "SPRINT")
ContextActionService:SetPosition("StreetSprint", UDim2.new(1, -200, 1, -240))

RunService.RenderStepped:Connect(function()
	local chassis = inCar()
	hint.Visible = chassis ~= nil and sprint == nil and player:GetAttribute("RaceState") ~= "racing"
		and player:GetAttribute("JobActive") ~= true
	if not sprint then
		return
	end
	local target = sprint.cps[sprint.next]
	local elapsed = workspace:GetServerTimeNow() - sprint.start
	if chassis and target and arrow then
		local from = chassis.Position + Vector3.new(0, 9, 0)
		local flat = Vector3.new(target.X - from.X, 0, target.Z - from.Z)
		if flat.Magnitude > 1 then
			arrow.CFrame = CFrame.lookAt(from, from + flat)
			local tip = arrow:FindFirstChild("Tip") :: Part
			tip.CFrame = arrow.CFrame * CFrame.new(0, 0, -5)
		end
		panel.Text = ("SPRINT  CP %d/%d   %d m   %.1f s / %d s"):format(sprint.next, #sprint.cps,
			math.floor(flat.Magnitude * 0.28), elapsed, sprint.timeLimit)
	end
end)
