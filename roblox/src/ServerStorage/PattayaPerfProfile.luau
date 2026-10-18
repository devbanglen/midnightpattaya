-- Named performance profiles (MIDNIGHT PATTAYA): instance-streaming settings + client LOD knobs, applied in one call
-- and reversible. See docs/PERFORMANCE_BUDGET.md ("Profiles").
--
--   local P = require(game.ServerStorage.PattayaPerfProfile:Clone())   -- Clone(): Studio caches the first require
--   P.apply("pc")        -- EDIT mode (command bar), then save: streaming properties + LOD attributes on workspace
--   P.applyLOD("pc_night") -- PLAY mode (server command bar): LOD attributes only, live on every client
--   P.revert()           -- puts back the values saved by the first apply() (also removes the LOD attributes)
--   P.show()             -- prints the current values
--
-- Streaming properties are read at server start, so they only take effect in the next Play session / server; in a
-- running game apply() still sets the LOD attributes. Every property write is pcall'd: if Studio refuses one, the
-- report names it and it can be set by hand in the Properties panel (Workspace -> Streaming).
-- The backup of the original values lives in the workspace attribute PerfProfileBackup (JSON) and is written once,
-- by the first apply(), so apply("pc") followed by apply("mobile") and revert() still goes back to the original.
local HttpService = game:GetService("HttpService")

local P = {}

-- why these numbers: docs/PERFORMANCE_BUDGET.md. Cars drive 160 studs/s (215 with nitro) and need ~1,000 studs of
-- road ahead; chunks are 512-stud Atomic models.
P.PROFILES = {
	pc = {
		streaming = {StreamingMinRadius = 512, StreamingTargetRadius = 1280, StreamOutBehavior = "Opportunistic",
			ModelStreamingBehavior = "Improved"},
		lod = {LOD_Enabled = true, LOD_FacadeRange = 700, LOD_PropRange = 900, LOD_Budget = 300, LOD_SpotCap = 60,
			LOD_LampLightRange = 350, LOD_FloodLightRange = 550},
	},
	-- night events (Night Run grid: up to 16 car lights on top of the lamps): fewer lamp lights, lit windows kept
	-- farther because the skyline of lit windows is the night look
	pc_night = {
		streaming = {StreamingMinRadius = 512, StreamingTargetRadius = 1280, StreamOutBehavior = "Opportunistic",
			ModelStreamingBehavior = "Improved"},
		lod = {LOD_Enabled = true, LOD_FacadeRange = 900, LOD_PropRange = 900, LOD_Budget = 300, LOD_SpotCap = 40,
			LOD_LampLightRange = 300, LOD_FloodLightRange = 550},
	},
	mobile = {
		streaming = {StreamingMinRadius = 384, StreamingTargetRadius = 768, StreamOutBehavior = "Opportunistic",
			ModelStreamingBehavior = "Improved"},
		lod = {LOD_Enabled = true, LOD_FacadeRange = 400, LOD_PropRange = 500, LOD_Budget = 200, LOD_SpotCap = 16,
			LOD_LampLightRange = 220, LOD_FloodLightRange = 400},
	},
}

local STREAM_PROPS = {"StreamingMinRadius", "StreamingTargetRadius", "StreamOutBehavior", "ModelStreamingBehavior"}
local LOD_ATTRS = {"LOD_Enabled", "LOD_FacadeRange", "LOD_PropRange", "LOD_Budget", "LOD_SpotCap",
	"LOD_LampLightRange", "LOD_FloodLightRange"}

local function readProp(prop: string): any
	local ok, v = pcall(function() return (workspace :: any)[prop] end)
	if not ok then
		return nil
	end
	if typeof(v) == "EnumItem" then
		return v.Name
	end
	return v
end

local function writeProp(prop: string, value: any): (boolean, string?)
	return pcall(function()
		local w: any = workspace
		if type(value) == "string" then
			w[prop] = (Enum :: any)[prop][value]
		else
			w[prop] = value
		end
	end)
end

local function backup()
	if workspace:GetAttribute("PerfProfileBackup") then
		return
	end
	local b = {streaming = {}, lod = {}}
	for _, prop in STREAM_PROPS do
		b.streaming[prop] = readProp(prop)
	end
	for _, a in LOD_ATTRS do
		b.lod[a] = workspace:GetAttribute(a) -- nil (absent) is the usual original
	end
	workspace:SetAttribute("PerfProfileBackup", HttpService:JSONEncode(b))
end

function P.applyLOD(name: string)
	local prof = P.PROFILES[name]
	assert(prof, "unknown profile " .. tostring(name) .. " (pc, pc_night, mobile)")
	backup()
	for k, v in prof.lod do
		workspace:SetAttribute(k, v)
	end
	workspace:SetAttribute("PerfProfile", name)
	return ("PerfProfile %s: LOD attributes set (live on every client)"):format(name)
end

function P.apply(name: string)
	local prof = P.PROFILES[name]
	assert(prof, "unknown profile " .. tostring(name) .. " (pc, pc_night, mobile)")
	if not workspace.StreamingEnabled then
		warn("PerfProfile: Workspace.StreamingEnabled is false; the streaming values are set but do nothing until it is on")
	end
	backup()
	local failed = {}
	for prop, v in prof.streaming do
		local ok, err = writeProp(prop, v)
		if not ok then
			table.insert(failed, ("%s=%s (%s)"):format(prop, tostring(v), tostring(err)))
		end
	end
	P.applyLOD(name)
	local msg = ("PerfProfile %s applied. %s"):format(name, P.show(true))
	if #failed > 0 then
		msg ..= "\nNOT set (set by hand in Properties -> Workspace -> Streaming): " .. table.concat(failed, "; ")
	end
	print(msg)
	return msg
end

function P.revert()
	local raw = workspace:GetAttribute("PerfProfileBackup")
	if type(raw) ~= "string" then
		return "PerfProfile: nothing to revert (no backup)"
	end
	local b = HttpService:JSONDecode(raw)
	local failed = {}
	for _, prop in STREAM_PROPS do
		local v = b.streaming[prop]
		if v ~= nil then
			local ok, err = writeProp(prop, v)
			if not ok then table.insert(failed, prop .. " (" .. tostring(err) .. ")") end
		end
	end
	for _, a in LOD_ATTRS do
		workspace:SetAttribute(a, b.lod[a]) -- JSON drops nils, so absent attributes are removed again
	end
	workspace:SetAttribute("PerfProfile", nil)
	workspace:SetAttribute("PerfProfileBackup", nil)
	local msg = "PerfProfile reverted. " .. P.show(true)
	if #failed > 0 then
		msg ..= "\nNOT restored: " .. table.concat(failed, "; ")
	end
	print(msg)
	return msg
end

function P.show(quiet: boolean?): string
	local parts = {"profile=" .. tostring(workspace:GetAttribute("PerfProfile")),
		"StreamingEnabled=" .. tostring(workspace.StreamingEnabled)}
	for _, prop in STREAM_PROPS do
		table.insert(parts, prop .. "=" .. tostring(readProp(prop)))
	end
	for _, a in LOD_ATTRS do
		table.insert(parts, a .. "=" .. tostring(workspace:GetAttribute(a)))
	end
	local s = table.concat(parts, " ")
	if not quiet then
		print(s)
	end
	return s
end

return P
