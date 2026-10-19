-- Client LOD for the Pattaya world (MIDNIGHT PATTAYA). Local only: nothing is replicated or saved.
--  * Facade Textures (Texture with attribute Facade) on building bodies farther than LOD_FacadeRange from the camera
--    get Transparency 1 (one property write per Texture, no reparenting, so PattayaNightLights' day/night swap of the
--    Texture id and tile size keeps working on hidden Textures too).
--  * Small props (palms, neon signs and their frames) farther than LOD_PropRange get LocalTransparencyModifier 1
--    (client-only multiplier; the part's own Transparency and its collision are untouched).
--  * Street-lamp and floodlight SpotLights are capped by PattayaNightLights (nearest LOD_SpotCap within range).
-- Works with instance streaming: parts are registered as they stream in (workspace.PattayaWorld and every
-- workspace.Circuit_* model) and forgotten as they stream out. Distance checks run round-robin, LOD_Budget parts per
-- Heartbeat, with a hysteresis band so a part on the edge does not flicker. A frame never touches more than the
-- budget, so a chunk streaming in (hundreds of parts at once) costs nothing extra in that frame.
--
-- Live knobs (attributes on workspace; the server, the command bar or ServerStorage.PattayaPerfProfile can set them):
--   LOD_Enabled = false      everything shown again, the script idles
--   LOD_FacadeRange (700)    studs
--   LOD_PropRange (900)      studs
--   LOD_Budget (300)         parts checked per Heartbeat
-- ReplicatedStorage.PattayaPerfProbe (if installed) can be run by setting workspace attribute PerfProbe = <seconds>.
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local DEFAULTS = {LOD_FacadeRange = 700, LOD_PropRange = 900, LOD_Budget = 300}
local HYSTERESIS = 40 -- studs: hide beyond range + this, show again inside range
local PROP_NAMES = {PalmTrunk = true, PalmFrond = true, NeonSign = true, SignFrame = true,
	-- street furniture layer (PattayaFurnitureBuilder, 2026-10-19): small parts hidden beyond LOD_PropRange too
	SignalArm = true, SignalHead = true, SignalLamp = true, NameSignBoard = true, BusSign = true, TaxiSign = true,
	TaxiVest = true, TaxiCanopy = true, ShelterRoof = true, PoleArm = true, PoleWire = true, ZebraStripe = true,
	-- coast layer (PattayaCoastBuilder): beach props
	UmbrellaCanopy = true, UmbrellaPole = true, Lounger = true, BoatHull = true, BoatBow = true, BoatEngine = true,
	BoatConsole = true, TowerFlag = true, TowerFlagPole = true, ParasailLine = true}

local function knob(name: string): number
	local v = workspace:GetAttribute(name)
	return if type(v) == "number" then v else DEFAULTS[name]
end
local function enabled(): boolean
	return workspace:GetAttribute("LOD_Enabled") ~= false
end

-- registry: one record per part, kept in a dense array for round-robin sweeps --------------------------------------
type Rec = {part: BasePart, pos: Vector3, kind: string, hidden: boolean, textures: {[Texture]: number}?, index: number}
local list: {Rec} = {}
local byPart: {[BasePart]: Rec} = {}
local cursor = 1

local function setHidden(rec: Rec, hide: boolean)
	rec.hidden = hide
	if rec.kind == "facade" then
		for t, original in rec.textures :: {[Texture]: number} do
			t.Transparency = if hide then 1 else original
		end
	else
		rec.part.LocalTransparencyModifier = if hide then 1 else 0
	end
end

local function add(part: BasePart, kind: string): Rec
	local rec = byPart[part]
	if rec then
		return rec
	end
	local r: Rec = {part = part, pos = part.Position, kind = kind, hidden = false,
		textures = if kind == "facade" then {} else nil, index = #list + 1}
	list[r.index] = r
	byPart[part] = r
	return r
end

local function remove(part: Instance)
	local rec = byPart[part :: BasePart]
	if not rec then
		return
	end
	byPart[part :: BasePart] = nil
	local last = list[#list]
	list[rec.index] = last
	last.index = rec.index
	list[#list] = nil
end

local function addTexture(t: Texture)
	local part = t.Parent
	if not (part and part:IsA("BasePart")) or t:GetAttribute("Facade") == nil then
		return
	end
	local rec = add(part, "facade")
	local textures = rec.textures :: {[Texture]: number}
	if textures[t] == nil then
		textures[t] = if t.Transparency < 1 then t.Transparency else 0
		if rec.hidden then
			t.Transparency = 1
		end
	end
end

-- streamed instances wait in a queue and are registered at the start of the next Heartbeat (attributes and
-- children of a streamed part can arrive a frame later)
local queue: {Instance} = {}
local function consider(d: Instance)
	-- kit mesh palms (workspace.PattayaWorld.VisMeshPalms.<model>.<part>) have their own LOD (VisMeshPalmLOD): leaving
	-- them to this sweep hid the impostor with up to ~1 s latency while driving (owner review ecbbf89 item 7)
	local gp = d.Parent and d.Parent.Parent
	if gp and gp.Name == "VisMeshPalms" then
		return
	end
	if d:IsA("Texture") or (d:IsA("BasePart") and PROP_NAMES[d.Name]) then
		table.insert(queue, d)
	end
end
local function forget(d: Instance)
	if d:IsA("BasePart") then
		remove(d)
	elseif d:IsA("Texture") then
		local rec = byPart[d.Parent :: BasePart]
		if rec and rec.textures then
			rec.textures[d :: Texture] = nil
		end
	end
end
local function drainQueue()
	if #queue == 0 then
		return
	end
	local q = queue
	queue = {}
	for _, d in q do
		if d.Parent and d:IsDescendantOf(workspace) then
			if d:IsA("Texture") then
				addTexture(d)
			else
				add(d :: BasePart, "prop")
			end
		end
	end
end

local watched: {[Instance]: boolean} = {}
local function watch(root: Instance)
	if watched[root] then
		return
	end
	watched[root] = true
	root.DescendantAdded:Connect(consider)
	root.DescendantRemoving:Connect(forget)
	task.spawn(function()
		for i, d in root:GetDescendants() do
			consider(d)
			if i % 5000 == 0 then
				task.wait()
			end
		end
	end)
end

local function maybeWatch(c: Instance)
	if c.Name == "PattayaWorld" or string.sub(c.Name, 1, 8) == "Circuit_" then
		watch(c)
	end
end
workspace.ChildAdded:Connect(maybeWatch)
for _, c in workspace:GetChildren() do
	maybeWatch(c)
end

-- the sweep ------------------------------------------------------------------------------------------------------
local wasEnabled = true
RunService.Heartbeat:Connect(function()
	drainQueue()
	if not enabled() then
		if wasEnabled then
			wasEnabled = false
			for _, rec in list do
				if rec.hidden then setHidden(rec, false) end
			end
		end
		return
	end
	wasEnabled = true
	local n = #list
	if n == 0 then
		return
	end
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	local focus = cam.CFrame.Position
	local facadeR, propR = knob("LOD_FacadeRange"), knob("LOD_PropRange")
	local budget = math.min(knob("LOD_Budget"), n)
	for _ = 1, budget do
		if cursor > #list then
			cursor = 1
		end
		if #list == 0 then
			break
		end
		local rec = list[cursor]
		cursor += 1
		if rec.part.Parent == nil then
			remove(rec.part) -- missed removal (e.g. the whole world was rebuilt)
			continue
		end
		local range = if rec.kind == "facade" then facadeR else propR
		local d = (rec.pos - focus).Magnitude
		if rec.hidden then
			if d < range then setHidden(rec, false) end
		elseif d > range + HYSTERESIS then
			setHidden(rec, true)
		end
	end
end)

-- optional probe trigger: workspace:SetAttribute("PerfProbe", 10) from the server runs a 10 s probe on every client
task.spawn(function()
	local probeModule = ReplicatedStorage:WaitForChild("PattayaPerfProbe", 20)
	if probeModule and probeModule:IsA("ModuleScript") then
		local ok, Probe = pcall(require, probeModule)
		if ok and type(Probe) == "table" and Probe.watchAttribute then
			Probe.watchAttribute()
		end
	end
end)

-- for the probe and for debugging from the client command bar
_G.PattayaLOD = {
	stats = function()
		local hidden, facades, props, textures = 0, 0, 0, 0
		for _, rec in list do
			if rec.hidden then hidden += 1 end
			if rec.kind == "facade" then
				facades += 1
				for _ in rec.textures :: {[Texture]: number} do textures += 1 end
			else
				props += 1
			end
		end
		return {tracked = #list, facadeParts = facades, facadeTextures = textures, props = props, hidden = hidden}
	end,
}
