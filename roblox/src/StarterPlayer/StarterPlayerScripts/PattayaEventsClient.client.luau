-- Night Run / Survival client (PattayaEventsServer): announcement banner with countdown, GPS arrow over the car to
-- the gathering ring, and J (R1 on a gamepad, a JOIN button on mobile) to join while driving within range.
-- Event state comes from attributes on ReplicatedStorage.PattayaEvent; the race itself is drawn by
-- PattayaSprintClient and the countdown by PattayaChallengeClient, like any street race.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
local state = ReplicatedStorage:WaitForChild("PattayaEvent", 60)
local EventJoin = remotes and remotes:WaitForChild("EventJoin", 60)
if not (state and EventJoin) then
	return
end

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil

local gui = Instance.new("ScreenGui")
gui.Name = "EventHUD"
gui.ResetOnSpawn = false
local banner = Instance.new("TextLabel")
banner.AnchorPoint = Vector2.new(0.5, 0)
banner.Position = UDim2.new(0.5, 0, 0, 132)
banner.Size = UDim2.fromOffset(640, 32)
banner.BackgroundColor3 = Color3.fromRGB(25, 5, 40)
banner.BackgroundTransparency = 0.25
banner.Font = Enum.Font.GothamBlack
banner.TextScaled = true
banner.TextColor3 = Color3.fromRGB(255, 255, 255)
banner.Visible = false
banner.Parent = gui
Instance.new("UICorner", banner).CornerRadius = UDim.new(0, 8)
local stroke = Instance.new("UIStroke")
stroke.Thickness = 2
stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
stroke.Parent = banner
if Style then
	Style.accent(banner, 8)
end
gui.Parent = player:WaitForChild("PlayerGui")

local function inCar(): BasePart?
	local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

-- GPS arrow to the ring (only while gathering and not yet joined)
local arrow: Part? = nil
local function setArrow(on: boolean, color: Color3?)
	if on and not arrow then
		local a = Instance.new("Part")
		a.Name = "EventArrow"
		a.Anchored, a.CanCollide, a.CanQuery, a.CanTouch = true, false, false, false
		a.Size = Vector3.new(1, 0.4, 6)
		a.Material = Enum.Material.Neon
		local tip = Instance.new("Part")
		tip.Name = "Tip"
		tip.Anchored, tip.CanCollide, tip.CanQuery, tip.CanTouch = true, false, false, false
		tip.Shape = Enum.PartType.Wedge
		tip.Size = Vector3.new(3.4, 0.4, 2.6)
		tip.Material = Enum.Material.Neon
		tip.Parent = a
		a.Parent = workspace
		arrow = a
	elseif not on and arrow then
		arrow:Destroy()
		arrow = nil
	end
	if arrow and color then
		arrow.Color = color
		local tip = arrow:FindFirstChild("Tip") :: Part
		tip.Color = color
	end
end

local bound = false
local function bindJoin(on: boolean)
	if on and not bound then
		ContextActionService:BindAction("EventJoin", function(_, s)
			if s == Enum.UserInputState.Begin then
				EventJoin:FireServer()
			end
			return Enum.ContextActionResult.Pass
		end, true, Enum.KeyCode.J, Enum.KeyCode.ButtonR1)
		ContextActionService:SetTitle("EventJoin", "JOIN")
		ContextActionService:SetPosition("EventJoin", UDim2.new(1, -340, 1, -240))
		bound = true
	elseif not on and bound then
		ContextActionService:UnbindAction("EventJoin")
		bound = false
	end
end

RunService.RenderStepped:Connect(function()
	local phase = state:GetAttribute("Phase")
	local chassis = inCar()
	local joined = player:GetAttribute("EventJoined") == true
	local title = state:GetAttribute("Title") or ""
	local color = state:GetAttribute("Color") or Color3.fromRGB(200, 60, 255)
	local ringPos = state:GetAttribute("RingPos") or Vector3.zero
	local wantArrow = false
	if phase == "gathering" then
		local left = math.max(0, math.ceil((state:GetAttribute("StartAt") or 0) - workspace:GetServerTimeNow()))
		local clock = ("%d:%02d"):format(left // 60, left % 60)
		local count = state:GetAttribute("Entrants") or 0
		if joined then
			banner.Text = ("%s in %s  -  you're in!  (%d drivers)"):format(title, clock, count)
		elseif chassis then
			local d = Vector3.new(ringPos.X - chassis.Position.X, 0, ringPos.Z - chassis.Position.Z).Magnitude
			local canKey = d <= (state:GetAttribute("JoinRadius") or 1500)
			banner.Text = ("%s in %s  -  ring %d m%s"):format(title, clock, math.floor(d * 0.28),
				if canKey then "  -  J to join" else "  -  follow the beacon")
			wantArrow = player:GetAttribute("SprintActive") ~= true and player:GetAttribute("JobActive") ~= true
		else
			banner.Text = ("%s in %s  -  get in a car and follow the beacon"):format(title, clock)
		end
		banner.Visible = true
		stroke.Color = color
		bindJoin(chassis ~= nil and not joined)
	elseif phase == "running" and (joined or player:GetAttribute("EventActive") == true)
		and (state:GetAttribute("Round") or 0) > 0 then
		banner.Text = ("%s  round %d/%d  -  %d drivers left"):format(title, state:GetAttribute("Round"),
			state:GetAttribute("Rounds") or 0, state:GetAttribute("Alive") or 0)
		banner.Visible = true
		stroke.Color = color
		bindJoin(false)
	else
		banner.Visible = false
		bindJoin(false)
	end
	setArrow(wantArrow and chassis ~= nil, color)
	if arrow and chassis then
		local from = chassis.Position + Vector3.new(0, 12, 0)
		local fl = Vector3.new(ringPos.X - from.X, 0, ringPos.Z - from.Z)
		if fl.Magnitude > 1 then
			arrow.CFrame = CFrame.lookAt(from, from + fl)
			local tip = arrow:FindFirstChild("Tip") :: Part
			tip.CFrame = arrow.CFrame * CFrame.new(0, 0, -4.3)
		end
	end
end)
