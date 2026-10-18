-- Race HUD for PattayaRaceServer: lap, checkpoint, timer, results; the next checkpoint's posts glow gold.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local world = workspace:WaitForChild("PattayaWorld", 30)
local race = world and world:WaitForChild("Race", 30)
if not race then
	return
end
local gates = {}
for _, g in race:WaitForChild("Checkpoints"):GetChildren() do
	gates[g:GetAttribute("Index")] = g
end
local COUNT = #gates
local LAPS = race:GetAttribute("Laps") or 1
local CYAN, WHITE, GOLD = Color3.fromRGB(0, 200, 255), Color3.fromRGB(255, 255, 255), Color3.fromRGB(255, 200, 40)

local gui = Instance.new("ScreenGui")
gui.Name = "RaceHUD"
gui.ResetOnSpawn = false
local panel = Instance.new("Frame")
panel.AnchorPoint = Vector2.new(0.5, 0)
panel.Position = UDim2.new(0.5, 0, 0, 14)
panel.Size = UDim2.fromOffset(560, 64)
panel.BackgroundColor3 = Color3.fromRGB(15, 15, 22)
panel.BackgroundTransparency = 0.35
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 12)
local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, 0, 0, 22)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 15
title.TextColor3 = Color3.fromRGB(150, 220, 255)
title.Text = race:GetAttribute("RaceName") or "Race"
title.Parent = panel
local line = Instance.new("TextLabel")
line.Position = UDim2.fromOffset(0, 22)
line.Size = UDim2.new(1, -20, 0, 36)
line.Position = UDim2.fromOffset(10, 24)
line.BackgroundTransparency = 1
line.Font = Enum.Font.GothamBlack
line.TextScaled = true
line.TextColor3 = Color3.new(1, 1, 1)
line.Parent = panel
gui.Parent = player:WaitForChild("PlayerGui")

local function fmt(t: number): string
	return string.format("%d:%05.2f", t // 60, t % 60)
end

local lit
local function highlight(index: number?)
	if lit then
		for _, p in lit:GetChildren() do
			p.Color = if lit:GetAttribute("Index") == 1 then WHITE else CYAN
		end
	end
	lit = index and gates[index]
	if lit then
		for _, p in lit:GetChildren() do
			p.Color = GOLD
		end
	end
end

RunService.RenderStepped:Connect(function()
	local state = player:GetAttribute("RaceState") or "idle"
	-- the loop panel steps aside during a sprint, challenge or job (they have their own HUD line below it)
	panel.Visible = state == "racing" or not (player:GetAttribute("SprintActive") or player:GetAttribute("JobActive")
		or player:GetAttribute("CircuitActive"))
	if state == "racing" then
		local nextCp = player:GetAttribute("RaceNext") or 2
		local elapsed = workspace:GetServerTimeNow() - (player:GetAttribute("RaceStart") or 0)
		local done = (nextCp - 2) % COUNT
		line.Text = string.format("LAP %d/%d   CP %d/%d   %s", player:GetAttribute("RaceLap") or 1, LAPS, done, COUNT, fmt(elapsed))
		if not lit or lit:GetAttribute("Index") ~= nextCp then
			highlight(nextCp)
		end
	elseif state == "finished" then
		local best = player:GetAttribute("RaceBest")
		line.Text = string.format("FINISH %s   BEST %s", fmt(player:GetAttribute("RaceLastTime") or 0), best and fmt(best) or "-")
		if lit and lit:GetAttribute("Index") ~= 1 then highlight(1) end
	else
		line.Text = "Drive through the white gate to start"
		if lit and lit:GetAttribute("Index") ~= 1 then highlight(1) end
		if not lit then highlight(1) end
	end
end)
