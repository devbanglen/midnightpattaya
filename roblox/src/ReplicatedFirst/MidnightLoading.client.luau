-- MIDNIGHT PATTAYA loading screen (ReplicatedFirst): replaces Roblox's default one while the game and the first
-- streamed part of the city load, then fades out. Original artwork only: text, gradient and neon lines.
local ReplicatedFirst = game:GetService("ReplicatedFirst")
local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")

ReplicatedFirst:RemoveDefaultLoadingScreen()
local player = Players.LocalPlayer
local gui = Instance.new("ScreenGui")
gui.Name = "MidnightLoading"
gui.IgnoreGuiInset = true
gui.DisplayOrder = 100
gui.ResetOnSpawn = false

local bg = Instance.new("Frame")
bg.Size = UDim2.fromScale(1, 1)
bg.BackgroundColor3 = Color3.fromRGB(8, 6, 20)
bg.BorderSizePixel = 0
bg.Parent = gui
local grad = Instance.new("UIGradient")
grad.Rotation = 90
grad.Color = ColorSequence.new({
	ColorSequenceKeypoint.new(0, Color3.fromRGB(10, 8, 30)),
	ColorSequenceKeypoint.new(0.65, Color3.fromRGB(40, 10, 60)),
	ColorSequenceKeypoint.new(1, Color3.fromRGB(255, 70, 140)),
})
grad.Parent = bg

local function text(str: string, y: number, h: number, color: Color3, font: Enum.Font): TextLabel
	local t = Instance.new("TextLabel")
	t.AnchorPoint = Vector2.new(0.5, 0.5)
	t.Position = UDim2.fromScale(0.5, y)
	t.Size = UDim2.new(0.9, 0, h, 0)
	t.BackgroundTransparency = 1
	t.Font = font
	t.TextScaled = true
	t.TextColor3 = color
	t.Text = str
	t.Parent = bg
	return t
end
local title = text("MIDNIGHT PATTAYA", 0.4, 0.13, Color3.fromRGB(255, 255, 255), Enum.Font.GothamBlack)
local glow = Instance.new("UIStroke")
glow.Color = Color3.fromRGB(0, 220, 255)
glow.Thickness = 3
glow.Transparency = 0.2
glow.Parent = title
text("OPEN WORLD STREET RACING", 0.5, 0.045, Color3.fromRGB(0, 220, 255), Enum.Font.GothamBold)
text("Drive the City. Own the Night.", 0.57, 0.035, Color3.fromRGB(255, 150, 210), Enum.Font.GothamMedium)
local status = text("Loading the city...", 0.86, 0.028, Color3.fromRGB(220, 220, 235), Enum.Font.Gotham)
text("Map data © OpenStreetMap contributors", 0.95, 0.022, Color3.fromRGB(170, 160, 190), Enum.Font.Gotham)

-- a neon "road line" that runs while loading
local bar = Instance.new("Frame")
bar.AnchorPoint = Vector2.new(0.5, 0.5)
bar.Position = UDim2.fromScale(0.5, 0.8)
bar.Size = UDim2.new(0.5, 0, 0, 4)
bar.BackgroundColor3 = Color3.fromRGB(60, 50, 90)
bar.BorderSizePixel = 0
bar.Parent = bg
local fill = Instance.new("Frame")
fill.Size = UDim2.fromScale(0.15, 1)
fill.BackgroundColor3 = Color3.fromRGB(0, 220, 255)
fill.BorderSizePixel = 0
fill.Parent = bar
gui.Parent = player:WaitForChild("PlayerGui")

local running = true
task.spawn(function()
	while running do
		fill.Position = UDim2.fromScale(-0.15, 0)
		local tw = TweenService:Create(fill, TweenInfo.new(1.1, Enum.EasingStyle.Sine), {Position = UDim2.fromScale(1, 0)})
		tw:Play()
		tw.Completed:Wait()
	end
end)

-- wait for the game, then for the city near the spawn (streaming), at most ~12 s in total
if not game:IsLoaded() then
	game.Loaded:Wait()
end
status.Text = "Streaming Pattaya..."
local t0 = os.clock()
local world = workspace:WaitForChild("PattayaWorld", 8)
while world and os.clock() - t0 < 4 and not world:FindFirstChild("Race") do
	task.wait(0.2)
end
task.wait(0.5)
running = false
status.Text = ""
for _, d in bg:GetDescendants() do
	if d:IsA("TextLabel") then
		TweenService:Create(d, TweenInfo.new(0.6), {TextTransparency = 1}):Play()
	elseif d:IsA("UIStroke") then
		TweenService:Create(d, TweenInfo.new(0.6), {Transparency = 1}):Play()
	elseif d:IsA("Frame") then
		TweenService:Create(d, TweenInfo.new(0.6), {BackgroundTransparency = 1}):Play()
	end
end
TweenService:Create(bg, TweenInfo.new(0.8), {BackgroundTransparency = 1}):Play()
task.wait(0.9)
gui:Destroy()
