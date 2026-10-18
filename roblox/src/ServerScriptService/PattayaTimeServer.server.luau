-- Day/night cycle for Midnight Pattaya: the server owns Lighting.ClockTime (it replicates to every client).
-- Lighting presets (Atmosphere, Bloom, ColorCorrection, ambient colours) are applied on each client by
-- PattayaNightLights from the replicated ClockTime, so the place's template Lighting is never changed by this
-- script except ClockTime (its start value is kept as the Lighting attribute TemplateClockTime).
-- Config (Lighting attributes, can be changed live from the Server command bar):
--   DayMinutes  real minutes per game day (default 24: one game hour per real minute)
--   TimeLock    a ClockTime number to hold the clock there (e.g. 21 for night tests); remove it (nil) to run
--   TimeCycle   false = this script leaves ClockTime alone
-- Example: game.Lighting:SetAttribute("TimeLock", 21)
local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")

local DEFAULT_DAY_MINUTES = 24
local START_CLOCK = 20.5 -- new servers open just after dusk: night is the signature
local UPDATE_EVERY = 0.5 -- seconds between ClockTime writes (0.5 game minutes at the default speed)

if Lighting:GetAttribute("TemplateClockTime") == nil then
	Lighting:SetAttribute("TemplateClockTime", Lighting.ClockTime)
end
if Lighting:GetAttribute("DayMinutes") == nil then
	Lighting:SetAttribute("DayMinutes", DEFAULT_DAY_MINUTES)
end

local clock = START_CLOCK
local acc = 0
RunService.Heartbeat:Connect(function(dt)
	if Lighting:GetAttribute("TimeCycle") == false then
		return
	end
	local lock = Lighting:GetAttribute("TimeLock")
	local minutes = Lighting:GetAttribute("DayMinutes")
	if type(minutes) ~= "number" or minutes <= 0 then
		minutes = DEFAULT_DAY_MINUTES
	end
	if type(lock) == "number" then
		clock = lock % 24
	else
		clock = (clock + dt * 24 / (minutes * 60)) % 24
	end
	acc += dt
	if acc >= UPDATE_EVERY then
		acc = 0
		if math.abs(Lighting.ClockTime - clock) > 1e-3 then
			Lighting.ClockTime = clock
		end
	end
end)
Lighting.ClockTime = clock
