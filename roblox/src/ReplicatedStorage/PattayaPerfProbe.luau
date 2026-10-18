-- Client performance probe (MIDNIGHT PATTAYA). Measures what can be measured without a focused Studio window:
--  * Heartbeat rate and frame-time spread (simulation side; keeps running when Studio is unfocused),
--  * RenderStepped rate (the real render rate ONLY while the window is focused; Studio throttles it otherwise, so
--    a low number with the window in the background means nothing),
--  * Stats: memory by DeveloperMemoryTag (Instances, GraphicsTexture, GraphicsParts, PhysicsParts, ...), total
--    memory, instance/primitive counts, and render CPU/GPU frame times when the engine exposes them (pcall'd),
--  * what is loaded and drawn near the camera: Parts, visible Textures, enabled SpotLights/PointLights, Neon parts,
--    BillboardGuis, in the whole loaded world and within a radius / in front of the camera ("draw-call proxies":
--    Roblox has no script API for real draw calls; visible parts + visible textures + lights in view is the proxy).
--
-- Use (client side only: a LocalScript, or the Client command bar in a Studio Play test):
--   require(game.ReplicatedStorage.PattayaPerfProbe).run(10)          -- sample 10 s, print the report, return it
--   require(game.ReplicatedStorage.PattayaPerfProbe).counts(700)      -- just the counts, right now
-- From the server (e.g. the server command bar, or an MCP call that runs on the server):
--   workspace:SetAttribute("PerfProbe", 10)   -- every client runs run(10) and prints "[PerfProbe] ..." lines
--   (PattayaLOD.client calls watchAttribute(); the attribute is cleared by nobody, set it again to re-run: any new
--    number, e.g. 10.01, triggers a new run.)
local RunService = game:GetService("RunService")
local Stats = game:GetService("Stats")
local Lighting = game:GetService("Lighting")

local Probe = {}

local function try(fn, ...)
	local ok, v = pcall(fn, ...)
	return if ok then v else nil
end

local function percentile(sorted: {number}, p: number): number
	if #sorted == 0 then
		return 0
	end
	return sorted[math.clamp(math.ceil(#sorted * p), 1, #sorted)]
end

-- memory by tag, MB (every DeveloperMemoryTag the engine has; unknown ones are skipped)
function Probe.memory(): {[string]: number}
	local out = {}
	for _, tag in Enum.DeveloperMemoryTag:GetEnumItems() do
		local mb = try(Stats.GetMemoryUsageMbForTag, Stats, tag)
		if mb then
			out[tag.Name] = math.floor(mb * 10 + 0.5) / 10
		end
	end
	out.Total = math.floor((try(Stats.GetTotalMemoryUsageMb, Stats) or 0) * 10 + 0.5) / 10
	return out
end

-- engine counters (each read is pcall'd: some properties do not exist on every engine version)
function Probe.engine(): {[string]: any}
	local s: any = Stats
	local out = {}
	for _, prop in {"InstanceCount", "PrimitivesCount", "MovingPrimitivesCount", "ContactsCount", "HeartbeatTimeMs",
		"PhysicsStepTimeMs", "RenderCPUFrameTime", "RenderGPUFrameTime", "FrameTime", "DataReceiveKbps",
		"DataSendKbps"} do
		local v = try(function() return s[prop] end)
		if v ~= nil then
			out[prop] = if type(v) == "number" then math.floor(v * 100 + 0.5) / 100 else v
		end
	end
	out.RealPhysicsFPS = try(function() return workspace:GetRealPhysicsFPS() end)
	out.StreamingEnabled = workspace.StreamingEnabled
	out.Technology = try(function() return Lighting.Technology.Name end)
	out.QualityLevel = try(function() return UserSettings().GameSettings.SavedQualityLevel.Name end)
	return out
end

-- counts of loaded / near / in-view things under the Pattaya roots
function Probe.counts(radius: number?): {[string]: number}
	local r = radius or 700
	local cam = workspace.CurrentCamera
	local cf = if cam then cam.CFrame else CFrame.identity
	local origin, look = cf.Position, cf.LookVector
	-- in-view test: inside a cone a little wider than the horizontal field of view
	local vp = if cam then cam.ViewportSize else Vector2.new(16, 9)
	local halfH = math.rad((if cam then cam.FieldOfView else 70) / 2)
	local halfW = math.atan(math.tan(halfH) * vp.X / math.max(vp.Y, 1))
	local cosView = math.cos(math.max(halfW, halfH) + math.rad(5))
	local c = {parts = 0, partsNear = 0, partsInView = 0, hiddenParts = 0, textures = 0, texturesVisible = 0,
		texturesNear = 0, texturesInView = 0, spotLights = 0, spotLightsOn = 0, spotLightsOnNear = 0, pointLightsOn = 0,
		neonNear = 0, billboards = 0, drawProxyInView = 0, trafficModels = 0}
	local roots = {}
	for _, ch in workspace:GetChildren() do
		if ch.Name == "PattayaWorld" or string.sub(ch.Name, 1, 8) == "Circuit_" or ch:IsA("Model") then
			table.insert(roots, ch)
		elseif ch:IsA("Folder") then
			table.insert(roots, ch) -- traffic pool and other client folders
		end
	end
	local function partInfo(p: BasePart): (number, boolean)
		local off = p.Position - origin
		local d = off.Magnitude
		local inView = d < 1 or off.Unit:Dot(look) > cosView
		return d, inView
	end
	local n = 0
	for _, root in roots do
		for _, d in root:GetDescendants() do
			n += 1
			if n % 8000 == 0 then
				task.wait()
			end
			if d:IsA("BasePart") then
				c.parts += 1
				local hidden = d.Transparency >= 1 or d.LocalTransparencyModifier >= 1
				if hidden then
					c.hiddenParts += 1
					continue
				end
				local dist, inView = partInfo(d)
				if dist < r then
					c.partsNear += 1
					if d.Material == Enum.Material.Neon then c.neonNear += 1 end
					if inView then
						c.partsInView += 1
						c.drawProxyInView += 1
					end
				end
			elseif d:IsA("Texture") or d:IsA("Decal") then
				c.textures += 1
				local p = d.Parent
				if d.Transparency < 1 and p and p:IsA("BasePart") then
					c.texturesVisible += 1
					local dist, inView = partInfo(p)
					if dist < r then
						c.texturesNear += 1
						if inView then
							c.texturesInView += 1
							c.drawProxyInView += 1
						end
					end
				end
			elseif d:IsA("SpotLight") then
				c.spotLights += 1
				if d.Enabled then
					c.spotLightsOn += 1
					local p = d.Parent
					local pos = if p and p:IsA("BasePart") then p.Position
						elseif p and p:IsA("Attachment") then p.WorldPosition else nil
					if pos and (pos - origin).Magnitude < r then
						c.spotLightsOnNear += 1
					end
				end
			elseif d:IsA("PointLight") then
				if d.Enabled then c.pointLightsOn += 1 end
			elseif d:IsA("BillboardGui") then
				c.billboards += 1
			end
		end
	end
	local traffic = workspace:FindFirstChild("PattayaTraffic") -- the client traffic pool (models in use)
	if traffic then
		c.trafficModels = #traffic:GetChildren()
	end
	c.drawProxyInView += c.spotLightsOnNear + c.pointLightsOn
	c.radius = r
	return c
end

-- sample Heartbeat and RenderStepped for `seconds`, then print and return the full report
function Probe.run(seconds: number?, radius: number?)
	local secs = seconds or 10
	local hb, rs = {}, {}
	local c1 = RunService.Heartbeat:Connect(function(dt) table.insert(hb, dt) end)
	local c2 = RunService.RenderStepped:Connect(function(dt) table.insert(rs, dt) end)
	local t0 = os.clock()
	task.wait(secs)
	c1:Disconnect()
	c2:Disconnect()
	local elapsed = os.clock() - t0
	local function summary(samples: {number})
		local sorted = table.clone(samples)
		table.sort(sorted)
		return {
			rate = math.floor(#samples / elapsed * 10 + 0.5) / 10,
			p50ms = math.floor(percentile(sorted, 0.5) * 10000 + 0.5) / 10,
			p99ms = math.floor(percentile(sorted, 0.99) * 10000 + 0.5) / 10,
			worstMs = math.floor((sorted[#sorted] or 0) * 10000 + 0.5) / 10,
		}
	end
	local report = {
		seconds = math.floor(elapsed * 10 + 0.5) / 10,
		heartbeat = summary(hb),
		renderStepped = summary(rs),
		engine = Probe.engine(),
		memory = Probe.memory(),
		counts = Probe.counts(radius),
		lod = if _G.PattayaLOD then _G.PattayaLOD.stats() else nil,
		focused = nil :: boolean?,
	}
	-- a throttled (unfocused) Studio renders far below the Heartbeat rate
	report.focused = report.renderStepped.rate >= report.heartbeat.rate * 0.8
	Probe.print(report)
	return report
end

local function line(prefix: string, t: {[string]: any})
	local keys = {}
	for k in t do table.insert(keys, k) end
	table.sort(keys)
	local parts = {}
	for _, k in keys do
		local v = t[k]
		if type(v) ~= "table" then table.insert(parts, ("%s=%s"):format(k, tostring(v))) end
	end
	print(("[PerfProbe] %s: %s"):format(prefix, table.concat(parts, " ")))
end

function Probe.print(report)
	line("time", {seconds = report.seconds, renderLooksFocused = report.focused})
	line("heartbeat", report.heartbeat)
	line("renderStepped", report.renderStepped)
	line("engine", report.engine)
	line("memoryMB", report.memory)
	line("counts", report.counts)
	if report.lod then line("lod", report.lod) end
	local knobs = {}
	for _, k in {"PerfProfile", "LOD_Enabled", "LOD_FacadeRange", "LOD_PropRange", "LOD_Budget", "LOD_SpotCap",
		"LOD_LampLightRange", "LOD_FloodLightRange"} do
		local v = workspace:GetAttribute(k)
		if v ~= nil then knobs[k] = v end
	end
	line("knobs", knobs)
end

-- run when workspace attribute PerfProbe (seconds) is set or changed
local watching = false
function Probe.watchAttribute()
	if watching then
		return
	end
	watching = true
	local busy = false
	workspace:GetAttributeChangedSignal("PerfProbe"):Connect(function()
		local s = workspace:GetAttribute("PerfProbe")
		if type(s) == "number" and s > 0 and not busy then
			busy = true
			task.spawn(function()
				pcall(Probe.run, math.min(s, 120))
				busy = false
			end)
		end
	end)
end

return Probe
