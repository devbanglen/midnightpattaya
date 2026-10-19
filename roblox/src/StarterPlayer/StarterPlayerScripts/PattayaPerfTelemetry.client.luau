-- Mobile playtest telemetry (MIDNIGHT PATTAYA, owner decision "PRIVATE MOBILE PLAYTEST", 2026-10-20).
-- Runs ONLY for the experience owner (LocalPlayer.UserId == game.CreatorId) or when the LocalPlayer attribute
-- PerfTelemetry == true, so normal players pay nothing. Every 10 s it measures, on the real device:
--   render FPS (RenderStepped count), frame time p50 / p99 / worst, Heartbeat rate,
--   memory: Total, GraphicsTexture, GraphicsTextureCharacter, GraphicsMeshParts, GraphicsParts, Gui, Instances (MB),
--   speed (HUD_SpeedKmh), position, seconds since join and since the last teleport (jump > 300 studs),
--   phase: "cold" (first 60 s after join), "arrive" (first 30 s after a teleport), "drive150" (speed >= 140),
--   "drive" (speed >= 20), "idle".
-- It shows a small overlay (tap / click it to hide or show) and sends each sample to the server
-- (PattayaPerfTelemetry.server), which keeps the session in a DataStore the leader reads afterwards.
-- No per-frame allocation: one connection appends dt into a preallocated ring.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")
local UserInputService = game:GetService("UserInputService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
if not (player.UserId == game.CreatorId or player:GetAttribute("PerfTelemetry") == true) then
	return
end

local remote = ReplicatedStorage:WaitForChild("PerfTelemetry", 30)
local SAMPLE = 10
local joinedAt = os.clock()
local lastJumpAt = os.clock()
local lastPos: Vector3? = nil

local function mem(tag: Enum.DeveloperMemoryTag): number
	local ok, v = pcall(Stats.GetMemoryUsageMbForTag, Stats, tag)
	return if ok and type(v) == "number" then math.floor(v * 10 + 0.5) / 10 else -1
end

-- overlay
local gui = Instance.new("ScreenGui")
gui.Name = "PerfTelemetryOverlay"
gui.ResetOnSpawn = false
gui.DisplayOrder = 200
-- drawn inside the Roblox top bar strip (its centre is empty), so it never covers the HUD (team12 UI audit: the
-- old bottom-centre spot covered the job strip on every viewport)
gui.IgnoreGuiInset = true
local label = Instance.new("TextButton")
label.AutoButtonColor = false
label.Size = UDim2.fromOffset(250, 34)
label.Position = UDim2.new(0.5, -125, 0, 12)
label.BackgroundColor3 = Color3.fromRGB(11, 16, 32)
label.BackgroundTransparency = 0.35
label.TextColor3 = Color3.fromRGB(0, 223, 255)
label.Font = Enum.Font.RobotoMono
label.TextSize = 11
label.TextWrapped = true
label.Text = "perf: measuring…"
label.Parent = gui
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 6)
corner.Parent = label
local compact = false
label.Activated:Connect(function()
	compact = not compact
	label.Size = if compact then UDim2.fromOffset(60, 18) else UDim2.fromOffset(250, 34)
	label.Position = if compact then UDim2.new(0.5, -30, 0, 20) else UDim2.new(0.5, -125, 0, 12)
end)
gui.Parent = player:WaitForChild("PlayerGui")

-- frame-time ring
local RING = 2048
local ring = table.create(RING, 0)
local n = 0
local hb = 0
RunService.RenderStepped:Connect(function(dt)
	n += 1
	ring[((n - 1) % RING) + 1] = dt
end)
RunService.Heartbeat:Connect(function()
	hb += 1
end)

local function carSpeed(): number
	local v = player:GetAttribute("HUD_SpeedKmh")
	return if type(v) == "number" then v else 0
end

local seq = 0
while true do
	local n0, hb0 = n, hb
	local t0 = os.clock()
	local speedSum, speedN = 0, 0
	for _ = 1, SAMPLE * 2 do
		task.wait(0.5)
		speedSum += carSpeed()
		speedN += 1
		local char = player.Character
		local root = char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
		if root then
			if lastPos and (root.Position - lastPos).Magnitude > 300 then
				lastJumpAt = os.clock()
			end
			lastPos = root.Position
		end
	end
	local secs = os.clock() - t0
	local frames = n - n0
	local dts = {}
	for i = math.max(n0 + 1, n - RING + 1), n do
		table.insert(dts, ring[((i - 1) % RING) + 1])
	end
	table.sort(dts)
	local function pct(p: number): number
		if #dts == 0 then return 0 end
		return math.floor(dts[math.clamp(math.ceil(#dts * p), 1, #dts)] * 10000 + 0.5) / 10
	end
	local speed = if speedN > 0 then speedSum / speedN else 0
	local sinceJoin = os.clock() - joinedAt
	local sinceJump = os.clock() - lastJumpAt
	local phase = if sinceJoin < 60 then "cold" elseif sinceJump < 30 then "arrive"
		elseif speed >= 140 then "drive150" elseif speed >= 20 then "drive" else "idle"
	local cam = workspace.CurrentCamera
	seq += 1
	local s = {
		seq = seq, phase = phase, t = math.floor(sinceJoin),
		fps = math.floor(frames / secs * 10 + 0.5) / 10,
		p50 = pct(0.5), p99 = pct(0.99), worst = pct(1),
		hb = math.floor((hb - hb0) / secs * 10 + 0.5) / 10,
		total = math.floor(Stats:GetTotalMemoryUsageMb() * 10 + 0.5) / 10,
		tex = mem(Enum.DeveloperMemoryTag.GraphicsTexture),
		texChar = mem(Enum.DeveloperMemoryTag.GraphicsTextureCharacter),
		mesh = mem(Enum.DeveloperMemoryTag.GraphicsMeshParts),
		gparts = mem(Enum.DeveloperMemoryTag.GraphicsParts),
		gui = mem(Enum.DeveloperMemoryTag.Gui),
		inst = mem(Enum.DeveloperMemoryTag.Instances),
		speed = math.floor(speed),
		x = lastPos and math.floor(lastPos.X) or 0, z = lastPos and math.floor(lastPos.Z) or 0,
		vp = cam and (math.floor(cam.ViewportSize.X) .. "x" .. math.floor(cam.ViewportSize.Y)) or "?",
		touch = UserInputService.TouchEnabled,
		pbr = ReplicatedStorage:FindFirstChild("MaterialLibraryMaps") ~= nil,
	}
	label.Text = if compact then string.format("%d fps", s.fps)
		else string.format("%s %.0ffps p99 %.0fms\nmem %.0f tex %.0f MB", phase, s.fps, s.p99, s.total, s.tex)
	if remote then
		remote:FireServer(s)
	end
end
