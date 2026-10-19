-- Traffic vehicle meshes for PattayaTraffic.client.luau (team9 traffic-vehicles, 2026-10-19).
-- Assets: tools/blender/gen_traffic.py -> build/vis_assets/traffic/*.glb (docs/TRAFFIC_VEHICLES.md).
--
-- Clients cannot InsertService:LoadAsset, so the leader puts the loaded Models under
-- ReplicatedStorage.TrafficVehicleTemplates.<AssetName> in Studio edit mode (tools/blender/traffic/install_templates.luau).
-- The client clones the MeshParts <AssetName>_<Short> (Paint, Dark, Head, Tail) from there. A template is used only
-- when every part exists and its Size matches the manifest; otherwise that variant is skipped, and when a traffic
-- kind has no usable variant the client builds today's box car (unchanged code path).
--
-- Placement: the manifest centre of each part (Roblox axes, origin = footprint centre at road level, front -Z) and
-- IMPORT_YAW: Roblox's glTF importer bakes every mesh rotated 180 deg about Y (leader, measured 2026-10-19; the
-- MeshPart's own rotation reads 0), so each clone is turned back. The template's own position/rotation is ignored,
-- so the templates need no adjustment after import.
--
-- Lamps: <Asset>_Head / <Asset>_Tail are Neon (as the box car's lamp parts were) and carry the attribute
-- TrafficLamp = "Head" / "Tail" so a later night pass can find them; PattayaNightLights does not touch traffic.
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local TrafficVehicles = {}

TrafficVehicles.IMPORT_YAW = CFrame.Angles(0, math.pi, 0)
TrafficVehicles.TEMPLATE_FOLDER = "TrafficVehicleTemplates"
TrafficVehicles.SIZE_TOL = 0.1 -- studs, MeshPart.Size vs manifest part size

-- BEGIN GENERATED (tools/blender/traffic/make_traffic_luau.py from build/vis_assets/traffic/manifest.json;
-- assetId values are kept when the block is regenerated)
TrafficVehicles.ASSETS = {
	TRF_Car_Hatch = {assetId = 0, kind = 0, tris = 624, roofTop = 5.7, roofZ = 2.95, taxiSign = false,
		size = {6.6, 5.7, 13.64}, parts = {
			Dark = {size = {6.6, 5.5, 13.64}, centre = {0, 2.75, 0}},
			Head = {size = {5.3, 0.45, 0.62}, centre = {0, 2.275, -6.41}},
			Paint = {size = {6.4, 4.85, 13.4}, centre = {0, 3.275, 0}},
			Tail = {size = {5.6, 0.55, 0.58}, centre = {0, 2.975, 6.44}},
		}},
	TRF_Car_Sedan = {assetId = 0, kind = 0, tris = 644, roofTop = 5.42, roofZ = 0.8, taxiSign = true,
		size = {6.6, 5.42, 14.24}, parts = {
			Dark = {size = {6.6, 5.2, 14.24}, centre = {0, 2.6, 0}},
			Head = {size = {5.3, 0.45, 0.62}, centre = {0, 2.275, -6.71}},
			Paint = {size = {6.4, 4.57, 14}, centre = {0, 3.135, 0}},
			Tail = {size = {5.6, 0.5, 0.58}, centre = {0, 2.7, 6.74}},
		}},
	TRF_Scooter_Pair = {assetId = 0, kind = 0, tris = 1008, roofTop = 6.6, roofZ = 0, taxiSign = false,
		size = {5.229, 6.85, 12.77}, parts = {
			Dark = {size = {5.229, 6.6, 12.7}, centre = {0, 3.3, -0.05}},
			Head = {size = {3.7, 0.35, 7.1}, centre = {0, 3.475, -2.37}},
			Paint = {size = {4.6, 5.85, 12.4}, centre = {0, 3.925, 0.1}},
			Tail = {size = {3.66, 0.3, 7.07}, centre = {0, 2.5, 2.835}},
		}},
	TRF_TukTuk_Std = {assetId = 0, kind = 0, tris = 792, roofTop = 7.1, roofZ = 1.4, taxiSign = false,
		size = {5.9, 7.076, 12.45}, parts = {
			Dark = {size = {5.9, 6.635, 12.05}, centre = {0, 3.317, 0.175}},
			Head = {size = {0.9, 0.856, 0.25}, centre = {0, 3.026, -6.125}},
			Paint = {size = {5.9, 6.15, 12.3}, centre = {0, 4.001, 0.05}},
			Tail = {size = {5.2, 0.45, 0.23}, centre = {0, 2.501, 5.965}},
		}},
	TRF_Pickup_Std = {assetId = 0, kind = 1, tris = 700, roofTop = 6.6, roofZ = -0.3, taxiSign = false,
		size = {7.24, 6.6, 16.2}, parts = {
			Dark = {size = {7.24, 6.35, 16.2}, centre = {0, 3.175, 0}},
			Head = {size = {6.1, 0.55, 0.38}, centre = {0, 3.025, -7.79}},
			Paint = {size = {6.8, 5.6, 15.95}, centre = {0, 3.8, 0.025}},
			Tail = {size = {6.84, 1.05, 0.25}, centre = {0, 3.375, 7.875}},
		}},
	TRF_Songthaew_Std = {assetId = 0, kind = 1, tris = 1016, roofTop = 8.2, roofZ = 3.8, taxiSign = false,
		size = {7.24, 8.29, 16.2}, parts = {
			Dark = {size = {7.24, 8.29, 16.2}, centre = {0, 4.145, 0}},
			Head = {size = {6.1, 0.55, 0.38}, centre = {0, 3.025, -7.79}},
			Paint = {size = {7, 6.8, 16.05}, centre = {0, 4.4, 0.075}},
			Tail = {size = {6.84, 1.05, 0.25}, centre = {0, 3.375, 7.875}},
		}},
	TRF_Van_Std = {assetId = 0, kind = 2, tris = 664, roofTop = 7.75, roofZ = 1.9, taxiSign = false,
		size = {7.44, 7.75, 16.3}, parts = {
			Dark = {size = {7.44, 7.3, 16.3}, centre = {0, 3.65, 0}},
			Head = {size = {6.2, 0.6, 0.32}, centre = {0, 2.9, -7.86}},
			Paint = {size = {7.2, 6.8, 16.012}, centre = {0, 4.35, 0.006}},
			Tail = {size = {6.9, 1.6, 0.23}, centre = {0, 3.8, 7.915}},
		}},
}
-- END GENERATED

-- variants per traffic kind (PattayaTraffic SHAPES: 0 = 14 x 6.6 car box, 1 = 16 x 7 songthaew box, 2 = 16 x 7.2 van
-- box) with weights; palette = key of PALETTES
TrafficVehicles.VARIANTS = {
	[0] = {
		{name = "TRF_Car_Sedan", weight = 0.38, palette = "car"},
		{name = "TRF_Car_Hatch", weight = 0.27, palette = "car"},
		{name = "TRF_Scooter_Pair", weight = 0.22, palette = "scooter"},
		{name = "TRF_TukTuk_Std", weight = 0.13, palette = "tuktuk"},
	},
	[1] = {
		{name = "TRF_Songthaew_Std", weight = 0.75, palette = "songthaew"},
		{name = "TRF_Pickup_Std", weight = 0.25, palette = "pickup"},
	},
	[2] = {
		{name = "TRF_Van_Std", weight = 1, palette = "van"},
	},
}
TrafficVehicles.TAXI_CHANCE = 0.3 -- of the vehicles with taxiSign (sedans): taxi palette + yellow roof sign Part

local function rgb(r: number, g: number, b: number): Color3
	return Color3.fromRGB(r, g, b)
end
local WHITE, SILVER, BLACK, GREY = rgb(235, 235, 235), rgb(165, 170, 175), rgb(25, 25, 30), rgb(95, 100, 105)
-- Thai street mix: mostly white / silver / black, some red and dark blue; taxis pink, green, orange, blue, yellow
TrafficVehicles.PALETTES = {
	car = {WHITE, WHITE, WHITE, SILVER, SILVER, BLACK, BLACK, GREY, rgb(170, 25, 30), rgb(30, 45, 90)},
	taxi = {rgb(240, 110, 170), rgb(40, 160, 70), rgb(240, 130, 30), rgb(40, 90, 200), rgb(235, 200, 40)},
	pickup = {WHITE, WHITE, SILVER, BLACK, GREY, rgb(170, 25, 30)},
	songthaew = {rgb(30, 70, 170), rgb(30, 70, 170), rgb(20, 110, 200), WHITE, rgb(180, 30, 35)},
	tuktuk = {rgb(25, 90, 200), rgb(40, 150, 70), rgb(190, 30, 35), rgb(240, 190, 30)},
	scooter = {rgb(190, 30, 35), BLACK, WHITE, rgb(30, 80, 180), rgb(240, 120, 170), SILVER},
	van = {WHITE, WHITE, WHITE, SILVER},
}
TrafficVehicles.DARK = rgb(28, 31, 38) -- glass, tyres, trim, rider
TrafficVehicles.HEAD = rgb(255, 250, 220) -- same lamp colours as the box car
TrafficVehicles.TAIL = rgb(230, 20, 20)
TrafficVehicles.TAXI_SIGN = rgb(255, 230, 80)

-- templates ---------------------------------------------------------------------------------------------------------
local cache: {[string]: any} = {} -- [name] = {[short] = MeshPart} | false (unusable)
local warned: {[string]: boolean} = {}

local function warnOnce(name: string, msg: string)
	if not warned[name] then
		warned[name] = true
		warn("[TrafficVehicles] " .. name .. ": " .. msg .. " (box car used)")
	end
end

-- {short = template MeshPart} for a usable template, else nil. A missing folder / model is not cached (the templates
-- may still be replicating); a broken template is cached as unusable.
function TrafficVehicles.template(name: string): {[string]: MeshPart}?
	local c = cache[name]
	if c ~= nil then
		return c or nil
	end
	local a = TrafficVehicles.ASSETS[name]
	local folder = ReplicatedStorage:FindFirstChild(TrafficVehicles.TEMPLATE_FOLDER)
	local model = folder and folder:FindFirstChild(name)
	if not (a and model) then
		return nil
	end
	local parts = {}
	for short, sp in a.parts do
		local mp = model:FindFirstChild(name .. "_" .. short, true)
		if not (mp and mp:IsA("MeshPart")) then
			warnOnce(name, "no MeshPart " .. name .. "_" .. short)
			cache[name] = false
			return nil
		end
		local d = mp.Size - Vector3.new(sp.size[1], sp.size[2], sp.size[3])
		if math.max(math.abs(d.X), math.abs(d.Y), math.abs(d.Z)) > TrafficVehicles.SIZE_TOL then
			warnOnce(name, ("%s size %s, manifest %s"):format(mp.Name, tostring(mp.Size), table.concat(sp.size, ", ")))
			cache[name] = false
			return nil
		end
		parts[short] = mp
	end
	cache[name] = parts
	return parts
end

-- a usable variant of the kind, picked by weight among the variants whose template is there; nil = none
function TrafficVehicles.pick(kind: number): (string?, any)
	local list = TrafficVehicles.VARIANTS[kind]
	if not list then
		return nil, nil
	end
	local total = 0
	for _, v in list do
		if TrafficVehicles.template(v.name) then
			total += v.weight
		end
	end
	if total <= 0 then
		return nil, nil
	end
	local r = math.random() * total
	for _, v in list do
		if TrafficVehicles.template(v.name) then
			r -= v.weight
			if r <= 0 then
				return v.name, v
			end
		end
	end
	return nil, nil
end

local function attach(root: BasePart, p: BasePart, cf: CFrame, model: Model)
	p.Anchored = false
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Massless = true
	p.CastShadow = false
	p.CFrame = cf
	local w = Instance.new("WeldConstraint")
	w.Part0, w.Part1 = root, p
	w.Parent = p
	p.Parent = model
end

-- Mesh vehicle of a traffic kind on the collision root (the invisible Body box, centre `lift` above the road):
-- clones the template MeshParts into `model`, welded to root, non-colliding, CanQuery false, massless.
-- Returns the asset name, or nil when no template of this kind is usable (the caller builds the box car).
function TrafficVehicles.build(kind: number, root: BasePart, lift: number, model: Model): string?
	local name, v = TrafficVehicles.pick(kind)
	local parts = name and TrafficVehicles.template(name)
	if not (name and parts) then
		return nil
	end
	local a = TrafficVehicles.ASSETS[name]
	local taxi = a.taxiSign and math.random() < TrafficVehicles.TAXI_CHANCE
	local pal = TrafficVehicles.PALETTES[if taxi then "taxi" else v.palette] or TrafficVehicles.PALETTES.car
	local paint = pal[math.random(1, #pal)]
	local base = root.CFrame * CFrame.new(0, -lift, 0)
	for short, tpl in parts do
		local sp = a.parts[short]
		local mp = tpl:Clone()
		for _, c in mp:GetChildren() do
			c:Destroy()
		end
		mp.Material = if short == "Head" or short == "Tail" then Enum.Material.Neon else Enum.Material.SmoothPlastic
		mp.Color = if short == "Paint" then paint
			elseif short == "Head" then TrafficVehicles.HEAD
			elseif short == "Tail" then TrafficVehicles.TAIL
			else TrafficVehicles.DARK
		if short == "Head" or short == "Tail" then
			mp:SetAttribute("TrafficLamp", short)
		end
		attach(root, mp, base * CFrame.new(sp.centre[1], sp.centre[2], sp.centre[3]) * TrafficVehicles.IMPORT_YAW, model)
	end
	if taxi then
		local s = Instance.new("Part")
		s.Name = "TaxiSign"
		s.Size = Vector3.new(2.4, 0.8, 1)
		s.Color = TrafficVehicles.TAXI_SIGN
		s.Material = Enum.Material.Neon
		attach(root, s, base * CFrame.new(0, a.roofTop + 0.38, a.roofZ), model)
	end
	model:SetAttribute("Vehicle", name)
	return name
end

return TrafficVehicles
