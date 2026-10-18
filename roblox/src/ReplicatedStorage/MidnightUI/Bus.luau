-- Client-side UI event bus (ReplicatedStorage.MidnightUI.Bus). Lets HUD scripts talk without requiring each other:
--   Bus.on("map.toggle", fn) / Bus.fire("map.toggle")
-- Names used by the MIDNIGHT PATTAYA HUD (docs/UI_CONTRACT.md lists them): "map.toggle", "garage.open",
-- "events.open", "missions.open", "settings.open", "help.open", "hud.scale" (number), "hud.reducedMotion" (bool),
-- "toast" (table {title, body, kind}), "gps.set" (destination id | nil).
-- One BindableEvent per client, created on first use. Server code never uses this module.
local Bus = {}
local event: BindableEvent? = nil
local function get(): BindableEvent
	if not event then
		local e = Instance.new("BindableEvent")
		e.Name = "MidnightUIBus"
		event = e
	end
	return event :: BindableEvent
end

function Bus.fire(name: string, ...: any)
	get():Fire(name, ...)
end

function Bus.on(name: string, fn: (...any) -> ()): RBXScriptConnection
	return get().Event:Connect(function(n: string, ...)
		if n == name then
			fn(...)
		end
	end)
end

return Bus
