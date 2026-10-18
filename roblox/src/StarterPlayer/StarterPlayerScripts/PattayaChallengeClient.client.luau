-- Street Challenge client: C (or the RACE button) challenges the nearest driver, or a street racer if nobody is near.
-- Shows incoming challenges (Y accept / N decline), the 3-2-1-GO countdown and challenge messages. The race itself
-- (gates, GPS arrow, HUD with position) is drawn by PattayaSprintClient.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
if not remotes then
	return
end
local ChallengeRequest = remotes:WaitForChild("ChallengeRequest", 30)
local ChallengeReply = remotes:WaitForChild("ChallengeReply", 30)
local ChallengeMsg = remotes:WaitForChild("ChallengeMsg", 30)
if not (ChallengeRequest and ChallengeReply and ChallengeMsg) then
	return
end

local RED, WHITE = Color3.fromRGB(255, 80, 80), Color3.fromRGB(255, 255, 255)

local gui = Instance.new("ScreenGui")
gui.Name = "ChallengeHUD"
gui.ResetOnSpawn = false
local function label(pos: UDim2, size: UDim2, color: Color3): TextLabel
	local t = Instance.new("TextLabel")
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = pos
	t.Size = size
	t.BackgroundTransparency = 1
	t.Font = Enum.Font.GothamBlack
	t.TextScaled = true
	t.TextColor3 = color
	t.TextStrokeTransparency = 0.2
	t.Visible = false
	t.Parent = gui
	return t
end
local big = label(UDim2.new(0.5, 0, 0.42, 0), UDim2.fromOffset(300, 140), WHITE)
local note = label(UDim2.new(0.5, 0, 0.5, 0), UDim2.fromOffset(640, 36), RED)
local invite = label(UDim2.new(0.5, 0, 0.6, 0), UDim2.fromOffset(640, 70), WHITE)
invite.BackgroundColor3 = Color3.fromRGB(60, 0, 0)
invite.BackgroundTransparency = 0.25
Instance.new("UICorner", invite).CornerRadius = UDim.new(0, 10)
local hint = Instance.new("TextLabel")
hint.AnchorPoint = Vector2.new(0, 1)
hint.Position = UDim2.new(0, 16, 1, -62)
hint.Size = UDim2.fromOffset(360, 20)
hint.BackgroundTransparency = 1
hint.Font = Enum.Font.GothamMedium
hint.TextSize = 15
hint.TextColor3 = Color3.fromRGB(255, 150, 150)
hint.TextStrokeTransparency = 0.5
hint.TextXAlignment = Enum.TextXAlignment.Left
hint.Text = "C  challenge a driver to a street race"
hint.Visible = false
hint.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

local function toast(text: string)
	note.Text = text
	note.Visible = true
	local stamp = os.clock()
	note:SetAttribute("Stamp", stamp)
	task.delay(3.5, function()
		if note:GetAttribute("Stamp") == stamp then note.Visible = false end
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

local function busy(): boolean
	return player:GetAttribute("RaceState") == "racing" or player:GetAttribute("SprintActive") == true
		or player:GetAttribute("JobActive") == true
end

-- incoming challenge ------------------------------------------------------------------------------------------------
local inviteUntil = 0
local function closeInvite()
	invite.Visible = false
	inviteUntil = 0
	ContextActionService:UnbindAction("ChallengeAccept")
	ContextActionService:UnbindAction("ChallengeDecline")
end

local function reply(accept: boolean)
	if inviteUntil > 0 then
		ChallengeReply:FireServer(accept)
		closeInvite()
	end
end

ChallengeMsg.OnClientEvent:Connect(function(kind, a, b)
	if kind == "invite" then
		inviteUntil = os.clock() + b
		invite.Text = ("%s challenges you to a street race!\nY accept    N decline"):format(a)
		invite.Visible = true
		ContextActionService:BindAction("ChallengeAccept", function(_, state)
			if state == Enum.UserInputState.Begin then reply(true) end
			return Enum.ContextActionResult.Sink
		end, true, Enum.KeyCode.Y, Enum.KeyCode.ButtonA)
		ContextActionService:SetTitle("ChallengeAccept", "ACCEPT")
		ContextActionService:SetPosition("ChallengeAccept", UDim2.new(0.5, -110, 0.7, 0))
		ContextActionService:BindAction("ChallengeDecline", function(_, state)
			if state == Enum.UserInputState.Begin then reply(false) end
			return Enum.ContextActionResult.Sink
		end, true, Enum.KeyCode.N, Enum.KeyCode.ButtonB)
		ContextActionService:SetTitle("ChallengeDecline", "NO")
		ContextActionService:SetPosition("ChallengeDecline", UDim2.new(0.5, 40, 0.7, 0))
	elseif kind == "msg" then
		toast(a)
	elseif kind == "countdown" then
		local goAt = a
		task.spawn(function()
			big.Visible = true
			while true do
				local left = goAt - workspace:GetServerTimeNow()
				if left <= 0 then break end
				big.Text = tostring(math.ceil(left))
				big.TextColor3 = WHITE
				RunService.RenderStepped:Wait()
			end
			big.Text = "GO!"
			big.TextColor3 = Color3.fromRGB(80, 255, 120)
			task.wait(1)
			big.Visible = false
		end)
	end
end)

-- C: challenge -------------------------------------------------------------------------------------------------------
ContextActionService:BindAction("StreetChallenge", function(_, state)
	if state == Enum.UserInputState.Begin and inCar() and not busy() then
		ChallengeRequest:FireServer()
	end
	return Enum.ContextActionResult.Pass
end, true, Enum.KeyCode.C, Enum.KeyCode.ButtonL1)
ContextActionService:SetTitle("StreetChallenge", "RACE")
ContextActionService:SetPosition("StreetChallenge", UDim2.new(1, -270, 1, -240))

RunService.RenderStepped:Connect(function()
	hint.Visible = inCar() ~= nil and not busy()
	if inviteUntil > 0 and os.clock() > inviteUntil then
		closeInvite()
	end
end)
