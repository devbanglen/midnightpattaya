-- Per-car performance specs, Performance Index (PI) and racing classes. Shared by RaceCarServer (model attributes),
-- PattayaGarageServer (prices, level gates, upgrades), PattayaGarageClient (shop UI) and CarController (driving).
-- Classes come from PI bands, never from the car's name, so a future car or an upgrade lands in the right class by
-- its numbers alone. See docs/GARAGE_AND_CLASSES.md for the table, formula and test plan.
--
-- Units: speeds in studs/s (the HUD shows them 1:1 as km/h), accelerations in studs/s^2, turnRate in rad/s.
local CarSpecs = {}

-- Keys a car may override. Anything missing falls back to the hatch (= the single CONFIG every car used before).
CarSpecs.BASE = {
	maxSpeed = 160,
	nitroSpeed = 215,
	accel = 60,
	nitroAccel = 110,
	reverseSpeed = 45,
	brake = 130,
	coastDrag = 0.25,
	turnRate = 2.3,
	grip = 9,
	driftGrip = 1.4,
	driftTurnBoost = 1.4,
	nitroMax = 100,
	nitroDrain = 28,
	nitroRegen = 4,
	nitroDriftRegen = 14,
}

-- Hard ceiling for any nitro top speed (stock or upgraded): the race/job/challenge servers treat moves faster than
-- 260 studs/s as a teleport, so stay well below that.
CarSpecs.NITRO_LIMIT = 245

-- Class bands by PI (inclusive lower bound). Names are what the circuit race system filters on (model attribute
-- "Class").
CarSpecs.CLASSES = {
	{name = "Street", min = 100, color = Color3.fromRGB(120, 200, 255)},
	{name = "Sport", min = 550, color = Color3.fromRGB(90, 230, 120)},
	{name = "Super", min = 650, color = Color3.fromRGB(255, 200, 40)},
	{name = "Hyper", min = 750, color = Color3.fromRGB(255, 110, 40)},
	{name = "Track Spec", min = 850, color = Color3.fromRGB(230, 60, 220)},
}

-- Shop order. price in Baht (leaderstats Money), level = required leaderstats Level.
CarSpecs.ORDER = {"hatch", "kei", "jdm_coupe", "muscle", "gt_sedan", "supercar"}
CarSpecs.STARTER = "hatch"
CarSpecs.Cars = {
	hatch = {
		color = Color3.fromRGB(255, 120, 20),
		name = "Hot Hatch", blurb = "Free starter. Same numbers every race was tuned with.",
		price = 0, level = 1,
		stats = {}, -- exactly BASE
	},
	kei = {
		color = Color3.fromRGB(150, 210, 180),
		name = "Kei Racer", blurb = "Cheap and nimble: brakes late, turns in sharp, runs out of top end.",
		price = 3000, level = 1,
		stats = {maxSpeed = 146, nitroSpeed = 200, accel = 64, nitroAccel = 108, brake = 142, grip = 10.5,
			driftGrip = 1.6, driftTurnBoost = 1.5, turnRate = 2.65, nitroDrain = 26, nitroDriftRegen = 16},
	},
	jdm_coupe = {
		color = Color3.fromRGB(30, 110, 255),
		name = "JDM Coupe", blurb = "Drift king: slides easy and refills nitro fast while sideways.",
		price = 12000, level = 4,
		stats = {maxSpeed = 168, nitroSpeed = 222, accel = 66, nitroAccel = 115, brake = 138, grip = 9.5,
			driftGrip = 1.2, driftTurnBoost = 1.75, turnRate = 2.5, nitroDriftRegen = 22},
	},
	muscle = {
		color = Color3.fromRGB(210, 25, 30),
		name = "Muscle Car", blurb = "Straight-line monster with a big nitro tank. Heavy in the corners.",
		price = 15000, level = 5,
		stats = {maxSpeed = 182, nitroSpeed = 236, accel = 74, nitroAccel = 125, brake = 112, grip = 7.5,
			driftGrip = 1.5, driftTurnBoost = 1.3, turnRate = 2.0, nitroMax = 120},
	},
	gt_sedan = {
		color = Color3.fromRGB(30, 30, 35),
		name = "GT Sedan", blurb = "All-rounder: quick, stable, strong brakes.",
		price = 22000, level = 7,
		stats = {maxSpeed = 171, nitroSpeed = 226, accel = 67, nitroAccel = 118, brake = 146, grip = 10.2,
			turnRate = 2.4, nitroMax = 110},
	},
	supercar = {
		color = Color3.fromRGB(150, 230, 30),
		name = "Supercar", blurb = "Fastest car in Pattaya. Priced like it.",
		price = 55000, level = 10,
		stats = {maxSpeed = 188, nitroSpeed = 240, accel = 74, nitroAccel = 130, brake = 150, grip = 10.5,
			driftTurnBoost = 1.45, turnRate = 2.45, nitroDrain = 27},
	},
}

-- Upgrades: 3 tiers each of engine and grip. Never required. A tier can only be fitted when the upgraded PI stays in
-- the car's stock class (class rules), so upgrades never move a car into a higher league.
CarSpecs.MAX_TIER = 3
CarSpecs.UPGRADE_KINDS = {"engine", "grip"}
local UPGRADE_FEE = {0.12, 0.25, 0.45} -- of max(car price, 8000), per tier
local function applyUpgrades(s, engine: number, grip: number)
	s.maxSpeed *= 1 + 0.02 * engine
	s.nitroSpeed *= 1 + 0.02 * engine
	s.accel *= 1 + 0.04 * engine
	s.nitroAccel *= 1 + 0.03 * engine
	s.grip *= 1 + 0.04 * grip
	s.turnRate *= 1 + 0.02 * grip
	s.brake *= 1 + 0.03 * grip
end

local function clamp01(x: number): number
	return math.clamp(x, 0, 1)
end
local function range(lo: number, hi: number, v: number): number
	return clamp01((v - lo) / (hi - lo))
end

-- Full stats table for a car (copy; safe to modify). Unknown id -> BASE.
function CarSpecs.Stats(id: string?, engine: number?, grip: number?)
	local car = id and CarSpecs.Cars[id]
	local s = table.clone(CarSpecs.BASE)
	if car then
		for k, v in car.stats do
			s[k] = v
		end
	end
	local e = math.clamp(math.floor(engine or 0), 0, CarSpecs.MAX_TIER)
	local g = math.clamp(math.floor(grip or 0), 0, CarSpecs.MAX_TIER)
	applyUpgrades(s, e, g)
	s.nitroSpeed = math.min(s.nitroSpeed, CarSpecs.NITRO_LIMIT)
	return s
end

-- 0..1 ratings, used for the PI and for the shop's stat bars.
function CarSpecs.Ratings(s)
	return {
		speed = range(120, 200, s.maxSpeed),
		accel = range(40, 100, s.accel),
		brake = range(90, 190, s.brake),
		grip = (range(6, 14, s.grip) + range(1.8, 3.0, s.turnRate)) / 2,
		drift = (range(1.1, 1.8, s.driftTurnBoost) + range(8, 26, s.nitroDriftRegen)) / 2,
		nitro = (range(160, 250, s.nitroSpeed) + range(2.5, 6, s.nitroMax / s.nitroDrain)) / 2,
	}
end

CarSpecs.PI_WEIGHTS = {speed = 0.34, accel = 0.20, brake = 0.10, grip = 0.18, drift = 0.06, nitro = 0.12}

-- PI = 100 + 900 * weighted sum of the ratings, rounded: 100..999.
function CarSpecs.PI(s): number
	local r = CarSpecs.Ratings(s)
	local sum = 0
	for k, w in CarSpecs.PI_WEIGHTS do
		sum += w * r[k]
	end
	return math.clamp(math.floor(100 + 900 * sum + 0.5), 100, 999)
end

function CarSpecs.ClassOf(pi: number): string
	local name = CarSpecs.CLASSES[1].name
	for _, c in CarSpecs.CLASSES do
		if pi >= c.min then
			name = c.name
		end
	end
	return name
end

function CarSpecs.ClassColor(name: string): Color3
	for _, c in CarSpecs.CLASSES do
		if c.name == name then
			return c.color
		end
	end
	return Color3.new(1, 1, 1)
end

-- {stats, pi, class} for a car with upgrades
function CarSpecs.Describe(id: string, engine: number?, grip: number?)
	local s = CarSpecs.Stats(id, engine, grip)
	local pi = CarSpecs.PI(s)
	return {stats = s, pi = pi, class = CarSpecs.ClassOf(pi)}
end

-- Stats for a spawned car model (attributes CarId, UpgEngine, UpgGrip set by RaceCarServer).
function CarSpecs.ForModel(model: Instance)
	return CarSpecs.Stats(model:GetAttribute("CarId"), model:GetAttribute("UpgEngine"), model:GetAttribute("UpgGrip"))
end

-- Equalised events (Night Run / Survival): every car drives with the stock starter's numbers.
function CarSpecs.Equalised()
	return CarSpecs.Stats(CarSpecs.STARTER, 0, 0)
end

function CarSpecs.UpgradePrice(id: string, tier: number): number
	local car = CarSpecs.Cars[id]
	local basis = math.max(car and car.price or 0, 8000)
	return math.floor(basis * (UPGRADE_FEE[tier] or 1) / 100 + 0.5) * 100
end

-- Can `kind` ("engine"/"grip") go from its current tier to the next? Returns ok, reason, price, newPi.
function CarSpecs.CanUpgrade(id: string, engine: number, grip: number, kind: string)
	if not CarSpecs.Cars[id] then
		return false, "Unknown car"
	end
	local cur = if kind == "engine" then engine else grip
	if kind ~= "engine" and kind ~= "grip" then
		return false, "Unknown upgrade"
	end
	if cur >= CarSpecs.MAX_TIER then
		return false, "Max tier"
	end
	local e = if kind == "engine" then engine + 1 else engine
	local g = if kind == "grip" then grip + 1 else grip
	local stockClass = CarSpecs.Describe(id, 0, 0).class
	local after = CarSpecs.Describe(id, e, g)
	if after.class ~= stockClass then
		return false, ("Class rules: would leave %s (PI %d)"):format(stockClass, after.pi), nil, after.pi
	end
	return true, nil, CarSpecs.UpgradePrice(id, cur + 1), after.pi
end

return CarSpecs
