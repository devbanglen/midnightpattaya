-- Client-side UI event bus (ReplicatedStorage.MidnightUI.Bus). Lets HUD scripts talk without requiring each other:
--   Bus.on("map.toggle", fn) / Bus.fire("map.toggle")
-- Names used by the MIDNIGHT PATTAYA HUD (docs/UI_CONTRACT.md and docs/UI_SYSTEM.md list them): "map.toggle",
-- "garage.open", "events.open", "missions.open", "settings.open", "help.open", "hud.scale" (number),
-- "hud.reducedMotion" (bool), "toast" (table {title, body, kind}), "gps.set" (destination id | nil),
-- "minimap.visible" (bool), "modal.open" ({title, build = function(body) end}), "modal.close".
--
-- Plain Luau listener lists (ui-core, 2026-10-19): every LocalScript on one client gets the same cached module table,
-- so the listeners live here directly. Unlike the first version (one BindableEvent), arguments are passed by
-- reference: tables keep their identity and functions survive (Bindables copy tables and cannot carry functions,
-- which the `modal.open` build callback needs). Each listener runs in its own thread (task.spawn), so one failing
-- listener never stops the others. Same API as before: Bus.on returns an object with :Disconnect(). Server code
-- never uses this module.
local Bus = {}

export type Connection = {Connected: boolean, Disconnect: (self: any) -> ()}

local listeners: {[string]: {(...any) -> ()}} = {}

function Bus.fire(name: string, ...: any)
	local list = listeners[name]
	if not list or #list == 0 then
		return
	end
	-- copy: a listener may disconnect (or connect) while we iterate
	for _, fn in table.clone(list) do
		task.spawn(fn, ...)
	end
end

function Bus.on(name: string, fn: (...any) -> ()): Connection
	local list = listeners[name]
	if not list then
		list = {}
		listeners[name] = list
	end
	table.insert(list, fn)
	local conn = {Connected = true}
	function conn.Disconnect(self: any)
		if not self.Connected then
			return
		end
		self.Connected = false
		local l = listeners[name]
		local i = l and table.find(l, fn)
		if l and i then
			table.remove(l, i)
		end
	end
	return conn :: any
end

-- number of listeners connected for `name` (lets a sender offer a fallback when nobody handles an event yet)
function Bus.count(name: string): number
	local list = listeners[name]
	return if list then #list else 0
end

return Bus
