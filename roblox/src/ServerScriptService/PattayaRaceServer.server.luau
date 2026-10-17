-- Checkpoint race on the generated Pattaya loop (workspace.PattayaWorld.Race, built by ServerStorage.PattayaBuilder).
-- Drive through the white start gate in a car to start; pass every checkpoint in order for each lap.
-- State is published as Player attributes for PattayaRaceClient: RaceState (idle/racing/finished), RaceLap,
-- RaceNext, RaceStart (server clock), RaceLastTime, RaceBest.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local world = workspace:WaitForChild("PattayaWorld", 30)
local race = world and world:FindFirstChild("Race")
if not race then
	return
end
local LAPS = race:GetAttribute("Laps") or 1
local gates = {}
for _, g in race.Checkpoints:GetChildren() do
	gates[g:GetAttribute("Index")] = g
end
local COUNT = #gates

local states = {} -- [player] = {lap, next, start}

local function passed(gate: BasePart, pos: Vector3): boolean
	local rel = gate.CFrame:PointToObjectSpace(pos)
	return math.abs(rel.Z) < 9 and math.abs(rel.X) < gate.Size.X / 2 + 2 and math.abs(rel.Y) < 16
end

local function setIdle(plr: Player)
	states[plr] = nil
	if plr:GetAttribute("RaceState") == "racing" then
		plr:SetAttribute("RaceState", "idle")
	end
end

local function carOf(plr: Player): BasePart?
	local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat.Parent:GetAttribute("RaceCar") then
		return seat.Parent.PrimaryPart
	end
	return nil
end

RunService.Heartbeat:Connect(function()
	local now = workspace:GetServerTimeNow()
	for _, plr in Players:GetPlayers() do
		local chassis = carOf(plr)
		if not chassis then
			setIdle(plr)
			continue
		end
		local pos = chassis.Position
		local st = states[plr]
		if not st then
			-- start: through gate 1 in the driving direction
			if passed(gates[1], pos) and chassis.AssemblyLinearVelocity:Dot(gates[1].CFrame.LookVector) > 5 then
				st = {lap = 1, next = 2, start = now}
				states[plr] = st
				plr:SetAttribute("RaceState", "racing")
				plr:SetAttribute("RaceStart", now)
				plr:SetAttribute("RaceLap", 1)
				plr:SetAttribute("RaceNext", 2)
			end
		elseif passed(gates[st.next], pos) then
			if st.next == 1 then
				if st.lap >= LAPS then
					local t = now - st.start
					states[plr] = nil
					plr:SetAttribute("RaceState", "finished")
					plr:SetAttribute("RaceLastTime", t)
					local best = plr:GetAttribute("RaceBest")
					if not best or t < best then
						plr:SetAttribute("RaceBest", t)
					end
					continue
				end
				st.lap += 1
				plr:SetAttribute("RaceLap", st.lap)
			end
			st.next = st.next % COUNT + 1
			plr:SetAttribute("RaceNext", st.next)
		end
	end
end)

Players.PlayerRemoving:Connect(function(plr)
	states[plr] = nil
end)
