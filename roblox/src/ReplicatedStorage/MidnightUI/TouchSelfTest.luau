-- MIDNIGHT PATTAYA touch self-test (ReplicatedStorage.MidnightUI.TouchSelfTest, ui-fix round 3). DEV ONLY, client only.
-- Client command bar during Play (Device emulator on a phone preset):
--   print(require(game.ReplicatedStorage.MidnightUI.TouchSelfTest)())
-- Lists every visible button of the HUD (MidnightHUD, the minimap card, the full map when open) and of Roblox's touch
-- controls (ContextActionGui = ContextActionService buttons, TouchGui = jump button) with its rect in gui px
-- (AbsolutePosition space, i.e. under the top bar) and checks, at the button's centre, with
-- PlayerGui:GetGuiObjectsAtPosition, that the button is hit-testable there and that no other input-sinking GUI
-- (a GuiButton or an Active object, not its own child) is on top of it. Then lists every pair of overlapping controls.
-- It never clicks, fires or changes anything. Returns the report as one string (also printed).
local Players = game:GetService("Players")
local GuiService = game:GetService("GuiService")
local ContextActionService = game:GetService("ContextActionService")

local ROOTS = {"MidnightHUD", "MinimapHUD", "WorldMapUI", "ContextActionGui", "TouchGui"}

type Rect = {x: number, y: number, w: number, h: number}
type Entry = {button: GuiButton, path: string, rect: Rect, status: string, note: string, marker: boolean}

local function shown(o: Instance, stop: Instance): boolean
	local p: Instance? = o
	while p and p ~= stop do
		if p:IsA("GuiObject") and not p.Visible then
			return false
		end
		p = p.Parent
	end
	return true
end

local function pathOf(o: Instance, stop: Instance): string
	local parts = {}
	local p: Instance? = o
	while p and p ~= stop.Parent do
		table.insert(parts, 1, p.Name)
		p = p.Parent
	end
	return table.concat(parts, ".")
end

local function sinks(o: GuiObject): boolean
	if o:IsA("GuiButton") then
		return true
	end
	return o.Active == true
end

local function interactable(o: GuiObject): boolean
	local ok, v = pcall(function()
		return (o :: any).Interactable
	end)
	return not ok or v ~= false
end

local function overlaps(a: Rect, b: Rect): boolean
	return a.x < b.x + b.w and a.x + a.w > b.x and a.y < b.y + b.h and a.y + a.h > b.y
end

local function fmtRect(r: Rect): string
	return ("%d,%d %dx%d"):format(math.floor(r.x + 0.5), math.floor(r.y + 0.5), math.floor(r.w + 0.5),
		math.floor(r.h + 0.5))
end

return function(): string
	local player = Players.LocalPlayer
	local pg = player:FindFirstChildOfClass("PlayerGui")
	if not pg then
		return "TouchSelfTest: no PlayerGui (run it on the client during Play)"
	end
	local out = {}
	local cam = workspace.CurrentCamera
	local vp = if cam then cam.ViewportSize else Vector2.zero
	local inset = GuiService:GetGuiInset()
	local hud = pg:FindFirstChild("MidnightHUD")
	local tc: any = nil
	pcall(function()
		tc = require(script.Parent:WaitForChild("TouchControls", 1) :: ModuleScript)
	end)
	table.insert(out, ("TouchSelfTest  viewport %dx%d  inset %d  MidnightHUD=%s  Compact=%s  TouchControls.active=%s")
		:format(vp.X, vp.Y, inset.Y, tostring(player:GetAttribute("MidnightHUD")),
			tostring(hud and hud:GetAttribute("Compact")), tostring(tc and tc.active())))

	-- CAS action name per button (the buttons themselves are named "Button" by the core script)
	local actionOf: {[Instance]: string} = {}
	local ok, bound = pcall(function()
		return ContextActionService:GetAllBoundActionInfo()
	end)
	if ok and type(bound) == "table" then
		for name in bound do
			local okB, b = pcall(function()
				return ContextActionService:GetButton(name)
			end)
			if okB and typeof(b) == "Instance" then
				actionOf[b] = name
			end
		end
	end

	-- collect
	local entries: {Entry} = {}
	for _, rootName in ROOTS do
		local g = pg:FindFirstChild(rootName)
		if g and g:IsA("ScreenGui") and g.Enabled then
			for _, d in g:GetDescendants() do
				if d:IsA("GuiButton") and d.AbsoluteSize.X > 0 and d.AbsoluteSize.Y > 0 and shown(d, g) then
					local path = pathOf(d, g)
					if actionOf[d] then
						path ..= "  [CAS " .. actionOf[d] .. "]"
					end
					local inWorld = d:FindFirstAncestor("World") ~= nil -- map markers (POI badges)
					table.insert(entries, {button = d, path = path, marker = inWorld, status = "", note = "",
						rect = {x = d.AbsolutePosition.X, y = d.AbsolutePosition.Y, w = d.AbsoluteSize.X, h = d.AbsoluteSize.Y}})
				end
			end
		end
	end

	-- coordinate probe: GetGuiObjectsAtPosition is documented in the AbsolutePosition space; if the first HUD button
	-- is only found with the top-bar inset added, use that offset for every probe (and say so)
	local offsetY = 0
	for _, e in entries do
		local c = Vector2.new(e.rect.x + e.rect.w / 2, e.rect.y + e.rect.h / 2)
		local direct = table.find(pg:GetGuiObjectsAtPosition(c.X, c.Y), e.button) ~= nil
		if not direct and table.find(pg:GetGuiObjectsAtPosition(c.X, c.Y + inset.Y), e.button) ~= nil then
			offsetY = inset.Y
		end
		if direct or offsetY ~= 0 then
			break
		end
	end
	if offsetY ~= 0 then
		table.insert(out, ("note: probes use +%d px (GetGuiObjectsAtPosition expects screen px incl. the top bar here)")
			:format(offsetY))
	end

	-- probe each centre
	local okCount, bad = 0, 0
	local markersOk, markers = 0, 0
	for _, e in entries do
		local r = e.rect
		local cx, cy = r.x + r.w / 2, r.y + r.h / 2
		local list = pg:GetGuiObjectsAtPosition(cx, cy + offsetY)
		local idx = table.find(list, e.button)
		if not interactable(e.button) then
			e.status, e.note = "OFF", "Interactable = false"
		elseif cx < 0 or cy < -inset.Y or cx > vp.X or cy > vp.Y then
			e.status, e.note = "OFF", "centre off screen"
		elseif not idx then
			e.status, e.note = "MISS", "not hit-testable at its centre (clipped by a parent, or behind the screen edge)"
		else
			local blocker: GuiObject? = nil
			for i = 1, idx - 1 do -- objects above the button at that point (topmost first)
				local o = list[i]
				if not o:IsDescendantOf(e.button) and sinks(o) then
					blocker = o
					break
				end
			end
			if blocker then
				local root = blocker:FindFirstAncestorWhichIsA("ScreenGui") or blocker
				e.status, e.note = "COVERED", "by " .. pathOf(blocker, root)
			else
				e.status = "OK"
			end
		end
		if e.marker then
			markers += 1
			if e.status == "OK" then
				markersOk += 1
			end
		else
			if e.status == "OK" then
				okCount += 1
			else
				bad += 1
			end
			table.insert(out, ("[%s] %s  rect %s%s"):format(e.status, e.path, fmtRect(r),
				if e.note ~= "" then "  (" .. e.note .. ")" else ""))
		end
	end
	if markers > 0 then
		table.insert(out, ("map markers (POI badges): %d / %d hit-testable at their centre (the minimap card's markers"
			.. " are display-only and clipped, the full map's markers set the GPS when tapped)"):format(markersOk, markers))
	end

	-- overlapping controls (not parent/child), map markers excluded
	local pairsOut = {}
	for i = 1, #entries do
		local a = entries[i]
		if not a.marker then
			for j = i + 1, #entries do
				local b = entries[j]
				if not b.marker and not a.button:IsAncestorOf(b.button) and not b.button:IsAncestorOf(a.button)
					and overlaps(a.rect, b.rect) then
					table.insert(pairsOut, ("  %s  x  %s"):format(a.path, b.path))
				end
			end
		end
	end
	table.insert(out, ("overlapping controls: %d"):format(#pairsOut))
	for _, l in pairsOut do
		table.insert(out, l)
	end
	if tc then
		local hiddenList = {}
		for _, name in tc.registered() do
			if tc.isHidden(name) then
				table.insert(hiddenList, name)
			end
		end
		table.insert(out, "touch buttons removed by TouchControls: " .. (if #hiddenList > 0
			then table.concat(hiddenList, ", ") else "none"))
	end
	table.insert(out, ("summary: %d controls OK, %d not OK, %d overlaps"):format(okCount, bad, #pairsOut))
	local report = table.concat(out, "\n")
	print(report)
	return report
end
