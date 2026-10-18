-- MIDNIGHT PATTAYA input glyphs + context actions (ReplicatedStorage.MidnightUI.InputPrompts, ui-core). Client only.
--   InputPrompts.glyph(action)   key text for the current input: keyboard "G", gamepad "D-PAD UP", touch "TAP";
--                                nil when the action has no binding on that input (e.g. P on a gamepad)
--   InputPrompts.label(action)   short English action name ("GPS", "MAP", ...)
--   InputPrompts.list(state)     the context actions to show for a gameplay state, as {{action, glyph, label}}
-- The key map below is copied from the scripts that bind the actions (ContextActionService), so the HUD never shows a
-- key that does nothing: GPS PattayaGPSClient (G / DPadUp), map PattayaMinimapClient (M / ButtonSelect, which the
-- HUD forwards on a short press, see MidnightHUD), challenge PattayaChallengeClient (C / L1), sprint
-- PattayaSprintClient (H / X), join PattayaEventsClient (J / R1), circuit menu CircuitRaceClient (P, keyboard only),
-- circuit reset CircuitRaceClient (T / DPadDown), nitro/drift/reset CarController (Shift / RT, Ctrl / LT, R / Y),
-- garage + job + Road Fight rings (E; X or Y on a gamepad depending on the ring), exit car (Space / A, Roblox jump),
-- ProximityPrompts (F / X, Roblox defaults).
local Responsive = require(script.Parent.Responsive)

local InputPrompts = {}

export type Action = {action: string, glyph: string, label: string}
export type State = {
	inCar: boolean?, -- LocalPlayer HUD_InCar (ui-race) or seated in a RaceCar VehicleSeat
	raceState: string?, -- LocalPlayer RaceState (idle / racing / finished)
	sprintActive: boolean?, -- SprintActive (Street Sprint, Challenge, Road Fight and event races)
	circuitActive: boolean?, -- CircuitActive
	eventActive: boolean?, -- EventActive (in an event race)
	eventGathering: boolean?, -- ReplicatedStorage.PattayaEvent Phase == "gathering" and not EventJoined
	jobActive: boolean?, -- JobActive
	nearCircuit: boolean?, -- within InputPrompts.CIRCUIT_RANGE of a Circuit_<id> entrance
}

InputPrompts.CIRCUIT_RANGE = 900 -- studs from a circuit entrance (ReplicatedStorage.PattayaWorldMap Circuit_<id>)

InputPrompts.KEYS = {
	gps = {key = "G", pad = "D-PAD UP", label = "GPS"},
	map = {key = "M", pad = "SELECT", label = "MAP"},
	challenge = {key = "C", pad = "LB", label = "CHALLENGE"},
	sprint = {key = "H", pad = "X", label = "STREET SPRINT"},
	join = {key = "J", pad = "RB", label = "JOIN"},
	circuit = {key = "P", pad = nil, label = "CIRCUIT"},
	circuitReset = {key = "T", pad = "D-PAD DOWN", label = "RESET"},
	nitro = {key = "SHIFT", pad = "RT", label = "NITRO"},
	drift = {key = "CTRL", pad = "LT", label = "DRIFT"},
	reset = {key = "R", pad = "Y", label = "FLIP"},
	exit = {key = "SPACE", pad = "A", label = "EXIT CAR"},
	ring = {key = "E", pad = "X / Y", label = "RING"},
	prompt = {key = "F", pad = "X", label = "INTERACT"},
	jobCancel = {key = "E", pad = "Y", label = "CANCEL JOB"},
	quickMenu = {key = nil, pad = "HOLD SELECT", label = "MENU"},
}

function InputPrompts.glyph(action: string): string?
	local k = InputPrompts.KEYS[action]
	if not k then
		return nil
	end
	local input = Responsive.inputKind()
	if input == "gamepad" then
		return k.pad
	elseif input == "touch" then
		return if k.key then "TAP" else nil
	end
	return k.key
end

function InputPrompts.label(action: string): string
	local k = InputPrompts.KEYS[action]
	return if k then k.label else string.upper(action)
end

local function add(out: {Action}, action: string, label: string?)
	local g = InputPrompts.glyph(action)
	if g then
		table.insert(out, {action = action, glyph = g, label = label or InputPrompts.label(action)})
	end
end

-- Context actions for a state. Racing (loop race, street race, circuit, event) shows only that mode's own keys;
-- in a car in free roam: GPS, MAP, CHALLENGE, STREET SPRINT (+ JOIN while an event gathers, + CIRCUIT near a circuit);
-- on foot: MAP. ProximityPrompt (F) and ring (E) prompts are drawn by their own scripts and are not repeated here.
function InputPrompts.list(state: State): {Action}
	local out: {Action} = {}
	if state.circuitActive then
		add(out, "circuitReset")
		add(out, "circuit")
		return out
	end
	if state.raceState == "racing" or state.sprintActive or state.eventActive then
		return out -- loop / street / event race: the race HUD speaks, no extra keys
	end
	if state.jobActive then
		if state.inCar then
			add(out, "jobCancel")
			add(out, "map")
		end
		return out
	end
	if state.inCar then
		add(out, "gps")
		add(out, "map")
		add(out, "challenge")
		add(out, "sprint")
		if state.eventGathering then
			add(out, "join")
		end
		if state.nearCircuit then
			add(out, "circuit")
		end
	else
		add(out, "map")
	end
	return out
end

return InputPrompts
