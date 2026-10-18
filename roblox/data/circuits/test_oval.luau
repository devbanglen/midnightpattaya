-- TEST FIXTURE for the circuit race system (not a real track). Goes to ServerStorage.PattayaData.circuits.test_oval.
-- A ~1,600-stud closed loop far from the city around world (60000, 1, 60000): a 400-stud main straight going +X with
-- the start/finish line in its middle, a 180-degree right-hander, a back straight with an S-chicane, a second
-- right-hander back onto the main straight. The pit lane runs parallel to the main straight, 45 studs outside it.
-- Flat: every y is 1 (track surface height). Built at require time so the shape is easy to change; the real Bira
-- data from the geometry teammate is plain literal tables in the same format.
-- testSurface = true: CircuitServer builds a plain SmoothPlastic surface for it (ServerStorage.CircuitTestTrack)
-- when workspace.Circuits.test_oval does not exist yet.
local CX, CZ, Y = 60000, 60000, 1
local R = 111 -- radius of both ends
local HALF = 200 -- half length of the straights
local STEP = 5 -- centerline spacing
local CHICANE = 40 -- sideways offset of each chicane bump
local BUMP = 90 -- length of each chicane bump

local centerline = {}
local marks = {}
local function add(x: number, z: number)
	table.insert(centerline, x)
	table.insert(centerline, Y)
	table.insert(centerline, z)
end
local function count(): number
	return #centerline // 3
end

-- main straight, going +X at z = CZ - R
for x = CX - HALF, CX + HALF - STEP, STEP do
	add(x, CZ - R)
	if x == CX then marks.sf = count() end
	if x == CX - HALF + 10 then marks.pitEntry = count() end
	if x == CX + HALF - 10 then marks.pitExit = count() end
end
-- right-hand end: around (CX + HALF, CZ)
local arcSteps = math.floor(math.pi * R / STEP + 0.5)
for k = 0, arcSteps - 1 do
	local th = math.pi * k / arcSteps
	add(CX + HALF + R * math.sin(th), CZ - R * math.cos(th))
end
marks.s1 = count() + 1
-- back straight, going -X at z = CZ + R, with an S-chicane (bump out, bump in) between CX + BUMP and CX - BUMP
for x = CX + HALF, CX - HALF + STEP, -STEP do
	local z = CZ + R
	local u = (CX + BUMP - x) -- 0..2*BUMP across the chicane
	if u > 0 and u < BUMP then
		z += CHICANE * (1 - math.cos(2 * math.pi * u / BUMP)) / 2
	elseif u >= BUMP and u < 2 * BUMP then
		z -= CHICANE * (1 - math.cos(2 * math.pi * (u - BUMP) / BUMP)) / 2
	end
	add(x, z)
end
marks.s2 = count() + 1
-- left end (still a right-hand turn in driving direction): around (CX - HALF, CZ)
for k = 0, arcSteps - 1 do
	local th = math.pi * k / arcSteps
	add(CX - HALF - R * math.sin(th), CZ + R * math.cos(th))
end

local lengthStuds = 0
do
	local n = count()
	for i = 1, n do
		local j = i % n + 1
		local dx = centerline[j * 3 - 2] - centerline[i * 3 - 2]
		local dz = centerline[j * 3] - centerline[i * 3]
		lengthStuds += math.sqrt(dx * dx + dz * dz)
	end
end

-- pit lane: leaves the main straight near its start, runs 45 studs outside it (smaller z), rejoins near its end
local PZ = CZ - R
local pitLane = {
	CX - 190, Y, PZ - 16,
	CX - 175, Y, PZ - 26,
	CX - 160, Y, PZ - 36,
	CX - 140, Y, PZ - 44,
	CX - 120, Y, PZ - 45,
}
for x = CX - 100, CX + 100, 20 do
	table.insert(pitLane, x)
	table.insert(pitLane, Y)
	table.insert(pitLane, PZ - 45)
end
for _, v in {CX + 120, Y, PZ - 45, CX + 140, Y, PZ - 44, CX + 160, Y, PZ - 36, CX + 175, Y, PZ - 26, CX + 190, Y, PZ - 16} do
	table.insert(pitLane, v)
end

-- 12 grid slots behind the line, staggered two-by-two, facing +X
local grid = {}
for i = 1, 12 do
	local row = (i - 1) // 2
	local col = (i - 1) % 2
	table.insert(grid, {CX - 14 - row * 18 - col * 9, Y, PZ + (if col == 0 then -8 else 8), 1, 0})
end

return {
	id = "test_oval",
	name = "Test Oval",
	lengthStuds = math.floor(lengthStuds),
	centerline = centerline,
	trackWidth = 40,
	startFinish = {index = marks.sf},
	sectors = {marks.s1, marks.s2},
	grid = grid,
	pitLane = pitLane,
	pitWidth = 20, -- optional (default 20)
	pitEntryIndex = marks.pitEntry,
	pitExitIndex = marks.pitExit,
	pitSpeedLimit = 60, -- studs/s (the HUD speedo shows studs/s as km/h)
	curbs = {},
	brakeMarkers = {},
	buildings = {},
	parking = {},
	entrance = {x = CX, z = PZ - 95, dx = 1, dz = 0}, -- paddock, outside the pit lane
	testSurface = true,
}
