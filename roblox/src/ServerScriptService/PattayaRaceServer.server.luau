-- Checkpoint race on the generated Pattaya loop (workspace.PattayaWorld.Race, built by ServerStorage.PattayaBuilder).
-- Drive through the white start gate in a car to start; cross every gate in order for each lap.
-- State is published as Player attributes for PattayaRaceClient: RaceState (idle/racing/finished), RaceLap,
-- RaceNext, RaceStart (server clock), RaceLastTime, RaceBest, RaceMessage.
--
-- A gate counts when the car's path between two samples crosses the gate plane forwards (edge-triggered, so a car
-- sitting in the gate can't restart a finished race and a laggy sample can't jump a gate) within the road width.
-- Moves faster than MAX_SPEED between gates invalidate the run (teleport check: the driver's client owns the car).
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local world = workspace:WaitForChild("PattayaWorld", 30)
local race = world and world:FindFirstChild("Race")
if not race then
	return
end
local Progress = require(ServerStorage:WaitForChild("PattayaProgress"))
Progress.Start()

-- busy = PattayaRoute.busy (loop race / sprint / job / circuit session). PattayaRoute needs the generated road graph,
-- so it is required lazily, only once PattayaData.graph exists (else the same attribute check without it).
local routeBusy: ((Player) -> boolean)? = nil
local function busy(plr: Player): boolean
	if not routeBusy then
		local data = ServerStorage:FindFirstChild("PattayaData")
		if data and data:FindFirstChild("graph") then
			local ok, Route = pcall(require, ServerStorage:WaitForChild("PattayaRoute"))
			if ok then
				routeBusy = (Route :: any).busy
			end
		end
	end
	if routeBusy then
		return routeBusy(plr)
	end
	return plr:GetAttribute("RaceState") == "racing" or plr:GetAttribute("SprintActive") == true
		or plr:GetAttribute("JobActive") == true or plr:GetAttribute("CircuitActive") == true
end

local remotes = ReplicatedStorage:FindFirstChild("PattayaRemotes") or Instance.new("Folder")
remotes.Name = "PattayaRemotes"
remotes.Parent = ReplicatedStorage
local NitroBonus = remotes:FindFirstChild("NitroBonus") or Instance.new("RemoteEvent")
NitroBonus.Name = "NitroBonus"
NitroBonus.Parent = remotes

local LAPS = race:GetAttribute("Laps") or 1
local LENGTH = race:GetAttribute("LengthStuds") or 6000
local MAX_SPEED = 260 -- studs/s: nitro top speed is 215; above this between two gates = not driven
local SIDE_MARGIN = 12 -- beyond the road edge: sidewalks are up to 10 studs
local gates = {}
for _, g in race.Checkpoints:GetChildren() do
	gates[g:GetAttribute("Index")] = g
end
local COUNT = #gates

local states = {} -- [player] = {lap, next, start, lastGateAt, lastGatePos}
local lastPos = {} -- [player] = Vector3 (previous sample)

local function crossed(gate: BasePart, a: Vector3, b: Vector3): boolean
	-- a sample-to-sample jump this long is a respawn/teleport, not driving (215 studs/s at 20 Hz is ~11 studs)
	if (b - a).Magnitude > 60 then
		return false
	end
	local ra = gate.CFrame:PointToObjectSpace(a)
	local rb = gate.CFrame:PointToObjectSpace(b)
	-- the gate faces along the route: forward is -Z in object space, so a forward crossing goes from +Z to -Z
	if not (ra.Z > 0 and rb.Z <= 0) then
		return false
	end
	local t = ra.Z / (ra.Z - rb.Z)
	local hit = ra:Lerp(rb, t)
	return math.abs(hit.X) < gate.Size.X / 2 + SIDE_MARGIN and math.abs(hit.Y) < 16
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
			lastPos[plr] = nil
			continue
		end
		local pos = chassis.Position
		local prev = lastPos[plr]
		lastPos[plr] = pos
		if not prev then
			continue
		end
		local st = states[plr]
		if not st then
			-- not while in a sprint, job or circuit session (no loop race runs here yet: RaceState isn't "racing")
			if crossed(gates[1], prev, pos) and not busy(plr) then
				st = {lap = 1, next = 2, start = now, lastGateAt = now, lastGatePos = pos}
				states[plr] = st
				plr:SetAttribute("RaceState", "racing")
				plr:SetAttribute("RaceStart", now)
				plr:SetAttribute("RaceLap", 1)
				plr:SetAttribute("RaceNext", 2)
				plr:SetAttribute("RaceMessage", "")
			end
		elseif crossed(gates[st.next], prev, pos) then
			local dt = math.max(now - st.lastGateAt, 1 / 60)
			if (pos - st.lastGatePos).Magnitude / dt > MAX_SPEED then
				setIdle(plr)
				plr:SetAttribute("RaceMessage", "Run invalid (moved too fast between checkpoints)")
				continue
			end
			st.lastGateAt, st.lastGatePos = now, pos
			NitroBonus:FireClient(plr, 15)
			if st.next == 1 then
				if st.lap >= LAPS then
					local t = now - st.start
					states[plr] = nil
					plr:SetAttribute("RaceState", "finished")
					plr:SetAttribute("RaceLastTime", t)
					local best = plr:GetAttribute("RaceBest")
					local record = not best or t < best
					if record then
						plr:SetAttribute("RaceBest", t)
					end
					-- pay by distance; faster average speed and a personal best pay extra
					local avg = LENGTH * LAPS / t
					local money = math.floor(LENGTH * LAPS / 25 + math.max(0, avg - 90) * 3 + (if record then 150 else 0))
					local exp = math.floor(LENGTH * LAPS / 50)
					Progress.Award(plr, money, exp, if record then "Central Loop - new best" else "Central Loop")
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
	lastPos[plr] = nil
end)
