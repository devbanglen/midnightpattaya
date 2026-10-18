-- Taxi / delivery jobs client: "E" prompt when the car is stopped in a stand ring, then a GPS route line on the road,
-- a gold arrow over the car, a beacon at the destination, and a HUD with time left and fare.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ContextActionService = game:GetService("ContextActionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local player = Players.LocalPlayer
local remotes = ReplicatedStorage:WaitForChild("PattayaRemotes", 60)
local world = workspace:WaitForChild("PattayaWorld", 60)
if not (remotes and world) then
	return
end
local RequestJob = remotes:WaitForChild("RequestJob", 30)
local CancelJob = remotes:WaitForChild("CancelJob", 30)
local JobUpdate = remotes:WaitForChild("JobUpdate", 30)
if not (RequestJob and CancelJob and JobUpdate) then
	return
end
local standsFolder = world:WaitForChild("JobStands", 30)

local GOLD, WHITE = Color3.fromRGB(255, 200, 40), Color3.fromRGB(255, 255, 255)
local STAND_RADIUS = 18
local STOP_SPEED = 30

-- shared MIDNIGHT PATTAYA panel style (ReplicatedStorage.MidnightStyle); styling only, the HUD works without it
local styleModule = ReplicatedStorage:WaitForChild("MidnightStyle", 10)
local Style = if styleModule then require(styleModule) :: any else nil

-- MIDNIGHT HUD (ui-core): Bus hook "missions.open" for the quick menu, and the legacy-hide flag (LocalPlayer attribute
-- "MidnightHUD", client-local). While it is true the job strip is hidden and its text is published as the client-local
-- attributes HUD_JobText / HUD_JobUrgent (<= 4 Hz) for MidnightHUD's BottomCenter, and job messages become Bus toasts.
local uiFolder = ReplicatedStorage:FindFirstChild("MidnightUI")
local function uiModule(name: string): any
	local m = uiFolder and uiFolder:FindFirstChild(name)
	return if m then require(m) :: any else nil
end
local Bus = uiModule("Bus")
local function midnight(): boolean
	return player:GetAttribute("MidnightHUD") == true
end
local lastPub: string? = nil
local lastPubAt = 0
local function publishJob(text: string?, urgent: boolean?)
	local now = os.clock()
	if text == lastPub or (text ~= nil and lastPub ~= nil and now - lastPubAt < 0.25) then
		return
	end
	lastPub, lastPubAt = text, now
	player:SetAttribute("HUD_JobText", text)
	player:SetAttribute("HUD_JobUrgent", if text then urgent == true else nil)
end

-- HUD -------------------------------------------------------------------------------------------------------------
local gui = Instance.new("ScreenGui")
gui.Name = "JobHUD"
gui.ResetOnSpawn = false
local panel = Instance.new("TextLabel")
panel.AnchorPoint = Vector2.new(0.5, 0)
panel.Position = UDim2.new(0.5, 0, 0, 86)
panel.Size = UDim2.fromOffset(560, 40)
panel.BackgroundColor3 = Color3.fromRGB(45, 35, 5)
panel.BackgroundTransparency = 0.3
panel.Font = Enum.Font.GothamBlack
panel.TextScaled = true
panel.TextColor3 = WHITE
panel.Visible = false
panel.Parent = gui
Instance.new("UICorner", panel).CornerRadius = UDim.new(0, 10)
if Style then
	Style.accent(panel, 10)
end
local prompt = Instance.new("TextLabel")
prompt.AnchorPoint = Vector2.new(0.5, 1)
prompt.Position = UDim2.new(0.5, 0, 1, -150)
prompt.Size = UDim2.fromOffset(520, 34)
prompt.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
prompt.BackgroundTransparency = 0.35
prompt.Font = Enum.Font.GothamBold
prompt.TextScaled = true
prompt.TextColor3 = GOLD
prompt.Visible = false
prompt.Parent = gui
Instance.new("UICorner", prompt).CornerRadius = UDim.new(0, 8)
local note = Instance.new("TextLabel") -- job messages; reward toasts come from the sprint client (LastReward)
note.AnchorPoint = Vector2.new(0.5, 0.5)
note.Position = UDim2.new(0.5, 0, 0.4, 0)
note.Size = UDim2.fromOffset(640, 38)
note.BackgroundTransparency = 1
note.Font = Enum.Font.GothamBlack
note.TextScaled = true
note.TextColor3 = GOLD
note.TextStrokeTransparency = 0.3
note.Visible = false
note.Parent = gui
gui.Parent = player:WaitForChild("PlayerGui")

local function toast(text: string)
	if midnight() and Bus then
		Bus.fire("toast", {title = "JOB", body = text, kind = "info", icon = "missions"})
		return
	end
	note.Text = text
	note.Visible = true
	local stamp = os.clock()
	note:SetAttribute("Stamp", stamp)
	task.delay(4, function()
		if note:GetAttribute("Stamp") == stamp then note.Visible = false end
	end)
end

player:GetAttributeChangedSignal("NearMissAt"):Connect(function()
	if midnight() then
		return -- MidnightHUD shows the near-miss card itself
	end
	local combo = player:GetAttribute("NearMissCombo") or 1
	toast(if combo > 1 then ("NEAR MISS  x%d"):format(combo) else "NEAR MISS")
end)

-- job state ------------------------------------------------------------------------------------------------------
local job -- {dest, start, timeLimit, fare, bumps, title, to}
local visuals: Folder? = nil
local arrow: Part? = nil

local function clear()
	if visuals then visuals:Destroy() end
	visuals, arrow, job = nil, nil, nil
	panel.Visible = false
	publishJob(nil)
end

local function neon(size: Vector3, cf: CFrame, color: Color3, transparency: number?): Part
	local p = Instance.new("Part")
	p.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false
	p.Material = Enum.Material.Neon
	p.Size = size
	p.CFrame = cf
	p.Color = color
	p.Transparency = transparency or 0
	p.Parent = visuals
	return p
end

local function buildVisuals(route: {Vector3}, dest: Vector3, color: Color3)
	visuals = Instance.new("Folder")
	visuals.Name = "JobRoute"
	-- GPS line on the road (RayCity auto-navigation)
	for i = 1, #route - 1 do
		local a, b = route[i] + Vector3.new(0, 0.35, 0), route[i + 1] + Vector3.new(0, 0.35, 0)
		local len = (b - a).Magnitude
		if len > 0.5 then
			neon(Vector3.new(2, 0.2, len), CFrame.lookAt((a + b) / 2, b), color, 0.45)
		end
	end
	-- destination beacon and ring
	neon(Vector3.new(4, 120, 4), CFrame.new(dest + Vector3.new(0, 60, 0)), color, 0.35)
	neon(Vector3.new(0.3, STAND_RADIUS * 2, STAND_RADIUS * 2), CFrame.new(dest + Vector3.new(0, 0.4, 0))
		* CFrame.Angles(0, 0, math.rad(90)), WHITE, 0.5)
	arrow = neon(Vector3.new(1.2, 0.4, 7), CFrame.new(), GOLD)
	local tip = neon(Vector3.new(4, 0.4, 3), CFrame.new(), GOLD)
	tip.Shape = Enum.PartType.Wedge
	tip.Name = "Tip"
	tip.Parent = arrow
	visuals.Parent = workspace
end

JobUpdate.OnClientEvent:Connect(function(kind, payload)
	if kind == "start" then
		clear()
		job = {dest = payload.dest, start = payload.start, timeLimit = payload.timeLimit, fare = payload.fare,
			bumps = 0, title = payload.title, to = payload.to}
		local color = if payload.kind == "delivery" then Color3.fromRGB(40, 210, 130) else GOLD
		buildVisuals(payload.route, payload.dest, color)
		panel.Visible = not midnight()
		toast(("%s: %s  →  %s  (%.1f km)"):format(payload.title, payload.from, payload.to, payload.length * 0.28 / 1000))
	elseif kind == "bump" and job then
		job.bumps = payload
		toast(if job.title == "TAXI" then "Ouch! The passenger didn't like that (fare cut)" else "Careful! Fragile parcel (fare cut)")
	elseif kind == "finish" then
		clear()
		-- the reward toast comes from the LastReward attribute (sprint client)
	elseif kind == "stop" then
		clear()
		toast(tostring(payload))
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

-- "E" prompt: bound only while the car is stopped in a stand ring (or a job is running, to cancel)
local promptStand: Model? = nil
local bound = false
local function setBound(on: boolean, title: string?)
	if on and not bound then
		ContextActionService:BindAction("PattayaJob", function(_, state)
			if state ~= Enum.UserInputState.Begin then
				return Enum.ContextActionResult.Pass
			end
			if job then
				CancelJob:FireServer()
			elseif promptStand then
				RequestJob:FireServer(promptStand.Name)
			end
			return Enum.ContextActionResult.Sink
		end, true, Enum.KeyCode.E, Enum.KeyCode.ButtonY)
		ContextActionService:SetPosition("PattayaJob", UDim2.new(1, -200, 1, -310))
		bound = true
	elseif not on and bound then
		ContextActionService:UnbindAction("PattayaJob")
		bound = false
	end
	if on and title then
		ContextActionService:SetTitle("PattayaJob", title)
	end
end

local function busy(): boolean
	return player:GetAttribute("RaceState") == "racing" or player:GetAttribute("SprintActive") == true
end

RunService.RenderStepped:Connect(function()
	local chassis = inCar()
	promptStand = nil
	if chassis and not job and not busy() and standsFolder then
		local v = chassis.AssemblyLinearVelocity
		if Vector3.new(v.X, 0, v.Z).Magnitude < STOP_SPEED then
			for _, m in standsFolder:GetChildren() do
				local ring = m:FindFirstChild("Ring")
				if ring and Vector3.new(ring.Position.X - chassis.Position.X, 0, ring.Position.Z - chassis.Position.Z).Magnitude < STAND_RADIUS then
					promptStand = m
					break
				end
			end
		end
	end
	if promptStand then
		local kind = promptStand:GetAttribute("Kind")
		prompt.Text = ("E   %s at %s"):format(if kind == "delivery" then "Pick up a delivery" else "Pick up a passenger",
			promptStand:GetAttribute("Label") or "")
		prompt.Visible = true
		setBound(true, if kind == "delivery" then "JOB" else "TAXI")
	elseif job and chassis then
		prompt.Visible = false
		setBound(true, "CANCEL")
	else
		prompt.Visible = false
		setBound(false)
	end
	if not (job and chassis) then
		return
	end
	local left = job.timeLimit - (workspace:GetServerTimeNow() - job.start)
	local from = chassis.Position + Vector3.new(0, 9, 0)
	local flat = Vector3.new(job.dest.X - from.X, 0, job.dest.Z - from.Z)
	if arrow and flat.Magnitude > 1 then
		arrow.CFrame = CFrame.lookAt(from, from + flat)
		local tip = arrow:FindFirstChild("Tip") :: Part
		tip.CFrame = arrow.CFrame * CFrame.new(0, 0, -5)
	end
	panel.Text = ("%s → %s   %d m   %d s left   fare ฿%d%s"):format(job.title, job.to, math.floor(flat.Magnitude * 0.28),
		math.max(0, math.ceil(left)), job.fare, if job.bumps > 0 then ("  (%d knocks)"):format(job.bumps) else "")
	panel.TextColor3 = if left < 15 then Color3.fromRGB(255, 90, 80) else WHITE
	if midnight() then
		panel.Visible = false
		publishJob(panel.Text, left < 15)
	end
end)

player:GetAttributeChangedSignal("MidnightHUD"):Connect(function()
	panel.Visible = job ~= nil and not midnight()
	if not midnight() then
		publishJob(nil)
	end
end)

-- quick menu (MidnightHUD TopRight "Missions"): the current job and the job stands this client knows about
local Theme, C = uiModule("Theme"), uiModule("Components")
if Bus and Theme and C then
	local col = Theme.color
	Bus.on("missions.open", function()
		Bus.fire("modal.open", {title = "MISSIONS", width = 600, height = 540, build = function(body: Frame)
			local status = C.label({parent = body, text = "", font = "bold", textSize = Theme.size.body, wrap = true,
				vAlign = "top", size = UDim2.new(1, -150, 0, 64)})
			local cancel = C.button({parent = body, text = "CANCEL JOB", style = "danger", anchor = Vector2.new(1, 0),
				position = UDim2.fromScale(1, 0), size = UDim2.fromOffset(140, 44), onClick = function()
					CancelJob:FireServer()
					Bus.fire("modal.close")
				end})
			C.label({parent = body, position = UDim2.fromOffset(0, 70), size = UDim2.new(1, 0, 0, 20), font = "body",
				textSize = Theme.size.label, color = col.textDim, fit = true, minSize = 10,
				text = "รับงาน: จอดในวง Taxi (เหลือง) / Delivery (เขียว) แล้วกด E"})
			C.divider({parent = body, position = UDim2.fromOffset(0, 100)})
			local list = Instance.new("ScrollingFrame")
			list.BackgroundTransparency = 1
			list.BorderSizePixel = 0
			list.Position = UDim2.fromOffset(0, 110)
			list.Size = UDim2.new(1, 0, 1, -110)
			list.CanvasSize = UDim2.new()
			list.AutomaticCanvasSize = Enum.AutomaticSize.Y
			list.ScrollBarThickness = 4
			list.ScrollBarImageColor3 = col.cyan
			list.Parent = body
			local layout = Instance.new("UIListLayout")
			layout.SortOrder = Enum.SortOrder.LayoutOrder
			layout.Padding = UDim.new(0, 4)
			layout.Parent = list
			-- stands: the JobStands models streamed in on this client, nearest first
			local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
			local rows = {}
			for _, m in (if standsFolder then standsFolder:GetChildren() else {}) do
				local ring = m:FindFirstChild("Ring") :: BasePart?
				local d = if ring and root then Vector3.new(ring.Position.X - root.Position.X, 0,
					ring.Position.Z - root.Position.Z).Magnitude else math.huge
				table.insert(rows, {label = m:GetAttribute("Label") or m.Name, kind = m:GetAttribute("Kind"), d = d})
			end
			table.sort(rows, function(a, b)
				return a.d < b.d
			end)
			C.label({parent = list, layoutOrder = 0, text = ("JOB STANDS (%d)"):format(#rows), font = "bold",
				textSize = Theme.size.caption, color = col.textDim})
			for i, r in rows do
				local row = Instance.new("Frame")
				row.BackgroundTransparency = 1
				row.Size = UDim2.new(1, -8, 0, 30)
				row.LayoutOrder = i
				row.Parent = list
				local delivery = r.kind == "delivery"
				C.pill({parent = row, text = if delivery then "DELIVERY" else "TAXI", textSize = Theme.size.caption,
					textColor = if delivery then col.green else col.yellow, stroke = if delivery then col.green else col.yellow,
					size = UDim2.fromOffset(96, 24), anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5)})
				C.label({parent = row, text = tostring(r.label), textSize = Theme.size.label, fit = true, minSize = 10,
					position = UDim2.fromOffset(106, 0), size = UDim2.new(1, -196, 1, 0)})
				C.label({parent = row, text = if r.d < math.huge then ("%.1f km"):format(r.d * 0.28 / 1000) else "",
					font = "mono", textSize = Theme.size.label, color = col.textDim, align = "right",
					anchor = Vector2.new(1, 0), position = UDim2.fromScale(1, 0), size = UDim2.new(0, 80, 1, 0)})
			end
			task.spawn(function()
				while body.Parent do -- 1 Hz while the window is open
					if job then
						local left = job.timeLimit - (workspace:GetServerTimeNow() - job.start)
						status.Text = ("%s  →  %s\nfare ฿%d  ·  %d s left%s"):format(job.title, job.to, job.fare,
							math.max(0, math.ceil(left)), if job.bumps > 0 then ("  ·  %d knocks"):format(job.bumps) else "")
					else
						status.Text = "No job running."
					end
					cancel.Visible = job ~= nil
					task.wait(1)
				end
			end)
		end})
	end)
end
