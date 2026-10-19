--!strict
-- VIS-7.1 VisMeshPalmLOD (MIDNIGHT PATTAYA): client-only switch between the full RSD_Palm mesh and its 2-part impostor
-- for workspace.PattayaWorld.VisMeshPalms (built by ServerStorage.VisMeshBuilder). WRITTEN, NOT RUN IN STUDIO.
--
-- NOT ACTIVE BY ITSELF: it lives in ServerStorage because the vis-mesh team owns no client folder. To use it, the
-- owner of the client scripts copies it to ReplicatedStorage and starts it from a LocalScript:
--     require(game.ReplicatedStorage.VisMeshPalmLOD).Start()
-- Without it the palms still work: the full mesh shows at every distance and PattayaLOD hides PalmTrunk / PalmFrond
-- beyond LOD_PropRange (900) exactly like the old Part palms; the impostor parts stay Transparency 1.
--
-- Within FullRange studs of the camera (attribute FullRange on the VisMeshPalms folder, default 400): mesh shown,
-- impostor hidden. Beyond FullRange + HYSTERESIS: mesh Transparency 1, impostor Transparency 0. Local writes only
-- (Transparency on the client never replicates). PattayaLOD's LocalTransparencyModifier beyond LOD_PropRange still
-- applies on top, so far palms disappear as before. Budget: BUDGET palms per Heartbeat, round robin.
local RunService = game:GetService("RunService")

local M = {}
local HYSTERESIS = 30
local BUDGET = 60

type Rec = {model: Model, pos: Vector3, mesh: {BasePart}, imp: {BasePart}, far: boolean}

function M.Start()
	assert(RunService:IsClient(), "VisMeshPalmLOD runs on the client")
	local world = workspace:WaitForChild("PattayaWorld")
	local list: {Rec} = {}
	local byModel: {[Instance]: Rec} = {}
	local folder: Instance? = nil

	-- cross-fade over FADE seconds instead of a hard swap (owner review ecbbf89 item 7: no visible pop-in at speed); the
	-- impostor fades in while the mesh fades out, so a palm never shows nothing
	local TweenService = game:GetService("TweenService")
	local FADE = TweenInfo.new(0.35, Enum.EasingStyle.Linear)
	local function setFar(r: Rec, far: boolean)
		r.far = far
		for _, p in r.mesh do
			TweenService:Create(p, FADE, {Transparency = if far then 1 else 0}):Play()
		end
		for _, p in r.imp do
			TweenService:Create(p, FADE, {Transparency = if far then 0 else 1}):Play()
		end
	end
	local function add(m: Instance)
		if not m:IsA("Model") or byModel[m] then
			return
		end
		local r: Rec = {model = m, pos = m:GetPivot().Position, mesh = {}, imp = {}, far = false}
		for _, p in m:GetChildren() do
			if p:IsA("MeshPart") then
				table.insert(r.mesh, p)
			elseif p:IsA("BasePart") and p:GetAttribute("VisMeshImpostor") then
				table.insert(r.imp, p)
			end
		end
		byModel[m] = r
		table.insert(list, r)
		-- StreamingEnabled: a model's parts can arrive after the model; late parts join the record and take its state
		-- (before, a late impostor stayed Transparency 1 while the mesh faded out: a palm showed nothing at range)
		m.ChildAdded:Connect(function(p)
			if not p:IsA("BasePart") or byModel[m] ~= r then
				return
			end
			if p:IsA("MeshPart") then
				table.insert(r.mesh, p)
				p.Transparency = if r.far then 1 else 0
			elseif p:GetAttribute("VisMeshImpostor") then
				table.insert(r.imp, p)
				p.Transparency = if r.far then 0 else 1
			end
		end)
	end
	local function remove(m: Instance)
		local r = byModel[m]
		if not r then
			return
		end
		byModel[m] = nil
		local i = table.find(list, r)
		if i then
			list[i] = list[#list]
			list[#list] = nil
		end
	end
	local function attach(f: Instance)
		folder = f
		for _, m in f:GetChildren() do
			add(m)
		end
		f.ChildAdded:Connect(function(m)
			task.defer(add, m) -- streamed models arrive with their parts a frame later
		end)
		f.ChildRemoved:Connect(remove)
	end
	local f = world:FindFirstChild("VisMeshPalms")
	if f then
		attach(f)
	else
		world.ChildAdded:Connect(function(c)
			if c.Name == "VisMeshPalms" and not folder then
				attach(c)
			end
		end)
	end

	local cursor = 1
	RunService.Heartbeat:Connect(function()
		local n = #list
		if n == 0 then
			return
		end
		local cam = workspace.CurrentCamera
		if not cam then
			return
		end
		local range = (folder and folder:GetAttribute("FullRange") :: number?) or 400
		local at = cam.CFrame.Position
		for _ = 1, math.min(BUDGET, n) do
			if cursor > n then
				cursor = 1
			end
			local r = list[cursor]
			cursor += 1
			local d = (r.pos - at).Magnitude
			if not r.far and d > range + HYSTERESIS then
				setFar(r, true)
			elseif r.far and d < range then
				setFar(r, false)
			end
		end
	end)
end

return M
