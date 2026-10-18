-- MaterialLibrary (MIDNIGHT PATTAYA, VIS-3): named surface looks shared by the client look scripts.
-- Written, not run in Studio.
--
-- Each entry: Material, Color, Reflectance, optional Transparency, optional `variant` (the name of a MaterialVariant
-- in MaterialService, used only if one with that name exists) and `surfaceAppearance` asset ids (nil until the owner
-- uploads the maps made by tools/materials/gen_pbr.py; see docs/MATERIAL_LIBRARY.md).
--
-- Use (client or server):
--   local ML = require(game.ReplicatedStorage.MaterialLibrary)
--   local saved = ML.save(part)          -- {Material, Color, Reflectance, Transparency, MaterialVariant}
--   ML.apply(part, "WetAsphalt")         -- or ML.apply(part, "NeonSurface", {color = Color3.fromRGB(0, 223, 255)})
--   ML.restore(part, saved)
--
-- Roblox limits that shape this module (Creator Docs, checked 2026-10-19):
--   * MaterialVariant.ColorMap / NormalMap / RoughnessMap / MetalnessMap are Plugin Security: a running game cannot
--     create a textured variant. The variants are made once in Studio (ML.studioCreateVariants() from the EDIT-mode
--     command bar after upload) and saved with the place; at runtime only BasePart.MaterialVariant (a string) is set.
--   * A MaterialVariant only applies when its BaseMaterial equals the part's Material, so an entry that has a variant
--     names the `variantMaterial` to use when the variant exists (WetAsphalt: SmoothPlastic without, Asphalt with).
--   * SurfaceAppearance works on MeshParts only and its maps are Plugin Security too. apply() clones a pre-made
--     SurfaceAppearance from ReplicatedStorage.MaterialLibraryAssets.<Name> into a MeshPart if one exists; plain Parts
--     (all roads, sidewalks and buildings) get the MaterialVariant route instead.
--   * Reflectance reflects the sky / environment only: there are no screen-space reflections of lamps or neon.
local MaterialService = game:GetService("MaterialService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

export type SurfaceMaps = {colorMap: string?, normalMap: string?, roughnessMap: string?, metalnessMap: string?}
export type Def = {
	Material: Enum.Material,
	Color: Color3,
	Reflectance: number,
	Transparency: number?,
	variant: string?, -- MaterialVariant name (made in Studio from the maps below)
	variantMaterial: Enum.Material?, -- the Material to use when that variant exists (its BaseMaterial)
	studsPerTile: number?, -- for the variant
	surfaceAppearance: SurfaceMaps, -- rbxassetid://... once uploaded; nil until then
	maps: string?, -- tools/materials/gen_pbr.py map set (build/materials/<maps>_*.png)
}

local C = Color3.fromRGB
local NONE: SurfaceMaps = {colorMap = nil, normalMap = nil, roughnessMap = nil, metalnessMap = nil}
local function maps(): SurfaceMaps
	return table.clone(NONE)
end

local ML = {}

ML.materials = {
	-- roads: the dry look uses the built-in Asphalt grain; slightly lighter than the builder's 46,47,52 because the
	-- Asphalt texture reads darker than SmoothPlastic and the road must stay readable at night
	DryAsphalt = {Material = Enum.Material.Asphalt, Color = C(62, 63, 68), Reflectance = 0,
		variant = "PattayaDryAsphalt", variantMaterial = Enum.Material.Asphalt, studsPerTile = 12,
		surfaceAppearance = maps(), maps = "asphalt"} :: Def,
	-- wet (VIS-7.1): much darker than dry, smooth (no Asphalt grain, so it reads different at a glance; sharp
	-- specular highlights from lamps and headlights), sky-only mirror 0.25 (Reflectance costs nothing extra)
	WetAsphalt = {Material = Enum.Material.SmoothPlastic, Color = C(26, 28, 34), Reflectance = 0.25,
		variant = "PattayaWetAsphalt", variantMaterial = Enum.Material.Asphalt, studsPerTile = 12,
		surfaceAppearance = maps(), maps = "wet_asphalt"} :: Def,
	-- junction discs when wet: a little more mirror than the slabs, so a junction reads as a shallow puddle
	-- (no extra parts). Joint discs (the small fill discs at bends) stay WetAsphalt so no spots appear mid-road.
	WetAsphaltJunction = {Material = Enum.Material.SmoothPlastic, Color = C(26, 28, 34), Reflectance = 0.3,
		variant = "PattayaWetAsphalt", variantMaterial = Enum.Material.Asphalt, studsPerTile = 12,
		surfaceAppearance = maps(), maps = "wet_asphalt"} :: Def,
	ConcreteSidewalk = {Material = Enum.Material.Concrete, Color = C(150, 148, 142), Reflectance = 0,
		variant = "PattayaConcrete", variantMaterial = Enum.Material.Concrete, studsPerTile = 8,
		surfaceAppearance = maps(), maps = "concrete"} :: Def,
	RoadPaint = {Material = Enum.Material.SmoothPlastic, Color = C(242, 242, 236), Reflectance = 0,
		surfaceAppearance = maps()} :: Def,
	-- wet paint (VIS-7.1): Reflectance 0.4 so lamp / headlight highlights read as wet; the colour is taken from the
	-- marking (white / yellow) by RoadLook, brighter and tinted cyan (white) or amber (yellow). Knob: if the markings
	-- read too dark at night (a sky mirror is dark at night), lower this to 0.2.
	RoadPaintWet = {Material = Enum.Material.SmoothPlastic, Color = C(250, 250, 246), Reflectance = 0.4,
		surfaceAppearance = maps()} :: Def,
	DarkGlass = {Material = Enum.Material.Glass, Color = C(22, 30, 42), Reflectance = 0.3, Transparency = 0.1,
		variant = "PattayaDarkGlass", variantMaterial = Enum.Material.Glass, studsPerTile = 16,
		surfaceAppearance = maps(), maps = "dark_glass"} :: Def,
	-- the generic "lit window" surface for one-off use; the vis-slice panes are styled at night by ML.NightStyles
	-- below (not by this entry)
	LitWindow = {Material = Enum.Material.Neon, Color = C(255, 196, 120), Reflectance = 0,
		surfaceAppearance = maps()} :: Def,
	PaintedMetal = {Material = Enum.Material.Metal, Color = C(70, 72, 78), Reflectance = 0.05,
		variant = "PattayaPaintedMetal", variantMaterial = Enum.Material.Metal, studsPerTile = 6,
		surfaceAppearance = maps(), maps = "painted_metal"} :: Def,
	Vegetation = {Material = Enum.Material.Grass, Color = C(58, 120, 56), Reflectance = 0,
		surfaceAppearance = maps()} :: Def,
	-- neon: owner palette cyan #00DFFF (default) / magenta #FF2BD6; pass {color = ...} for the other
	NeonSurface = {Material = Enum.Material.Neon, Color = C(0, 223, 255), Reflectance = 0,
		surfaceAppearance = maps()} :: Def,
	-- car paints: SmoothPlastic + Reflectance gives the clear-coat sky reflection Roblox can do on Parts; MeshPart
	-- bodies with a SurfaceAppearance keep their own maps (apply() only clones one in if an asset template exists)
	CarPaintMidnight = {Material = Enum.Material.SmoothPlastic, Color = C(18, 22, 40), Reflectance = 0.25,
		surfaceAppearance = maps()} :: Def,
	CarPaintPearl = {Material = Enum.Material.SmoothPlastic, Color = C(236, 236, 232), Reflectance = 0.2,
		surfaceAppearance = maps()} :: Def,
	CarPaintRed = {Material = Enum.Material.SmoothPlastic, Color = C(196, 24, 32), Reflectance = 0.22,
		surfaceAppearance = maps()} :: Def,
}

-- Night styles (VIS-7.1), read by PattayaNightLights for every NightNeon part at night, keyed by the part's `Mat`
-- attribute. Goal: lit panes read as warm interior light, not as light sources; neon stays neon without blooming to
-- white. Fields (all optional):
--   material  Enum.Material used at night (default Neon)
--   palette   true = snap cyan-ish / magenta-ish hues to the preset's neon palette first (the old hue rule)
--   colorMul  multiply NightColor's RGB (clamped to 1): < 1 dims a Neon pane, > 1 lifts a non-emissive pane so it
--             still reads as lit under the navy ambient
--   maxValue  cap the HSV value of the result (Neon colour V <= 0.85 keeps bloom from whiting it out)
-- LitWindow is split by pane area (the two largest Size axes multiplied): <= smallArea studs^2 = `small`, else `large`.
-- A LitWindow pane is a shopfront if it has attribute Shopfront = true or its name is in SHOPFRONT_NAMES (the kit's
-- ground-floor glass: shopfront_a ShopGlow, shopfront_b ShopGlass, lobby_a LobbyGlass); shopfronts use `Shopfront`.
-- `_default`: NightNeon parts with no Mat or an unknown Mat (circuit window bands, landmark / furniture lamps):
-- unchanged behaviour. `NeonSign`: the always-Neon sign props (PattayaBuilder), colour cap only.
-- The Legacy preset ignores this table (rollback = Neon + raw NightColor, exactly as before).
ML.NightStyles = {
	LitWindow = {
		smallArea = 20,
		small = {material = Enum.Material.Neon, colorMul = 0.68},
		-- leader, Studio check 2026-10-19: SmoothPlastic x1.5 read as flat beige wall under the navy ambient; dim Neon
		-- x0.68 reads as warm interior light without the old blown-out yellow (captures vis71_after_neon_*)
		large = {material = Enum.Material.Neon, colorMul = 0.68},
	},
	Shopfront = {material = Enum.Material.Glass, colorMul = 1.4},
	NeonSurface = {material = Enum.Material.Neon, palette = true, maxValue = 0.85},
	-- the base-layer sign slabs (PattayaBuilder Props, 20 x 6 studs) are dimmed a little as well
	NeonSign = {palette = true, colorMul = 0.75, maxValue = 0.85},
	_default = {material = Enum.Material.Neon, palette = true},
}
ML.SHOPFRONT_NAMES = {ShopGlow = true, ShopGlass = true, LobbyGlass = true}

ML.PALETTE = {cyan = C(0, 223, 255), magenta = C(255, 43, 214), lamp = C(255, 176, 96), head = C(255, 241, 222)}

-- variant lookup, cached per name (a variant can sit anywhere under MaterialService)
local variantCache: {[string]: boolean} = {}
function ML.hasVariant(name: string?): boolean
	if not name then
		return false
	end
	local hit = variantCache[name]
	if hit == nil then
		local v = MaterialService:FindFirstChild(name, true)
		hit = v ~= nil and v:IsA("MaterialVariant")
		variantCache[name] = hit
	end
	return hit
end
-- call after variants were added or removed while running (the cache is per session)
function ML.clearCache()
	table.clear(variantCache)
end

function ML.get(name: string): Def
	local def = ML.materials[name]
	assert(def, "MaterialLibrary: unknown material " .. tostring(name))
	return def
end

export type Saved = {Material: Enum.Material, Color: Color3, Reflectance: number, Transparency: number,
	MaterialVariant: string}
function ML.save(part: BasePart): Saved
	return {Material = part.Material, Color = part.Color, Reflectance = part.Reflectance,
		Transparency = part.Transparency, MaterialVariant = part.MaterialVariant}
end

function ML.restore(part: BasePart, saved: Saved)
	part.Material = saved.Material
	part.MaterialVariant = saved.MaterialVariant
	part.Color = saved.Color
	part.Reflectance = saved.Reflectance
	part.Transparency = saved.Transparency
	local sa = part:FindFirstChild("MaterialLibrarySA")
	if sa then
		sa:Destroy()
	end
end

-- opts.color: use this colour instead of the entry's; opts.keepColor: leave the part's colour alone
-- opts.keepTransparency: leave Transparency alone even if the entry has one
function ML.apply(part: BasePart, name: string, opts: {color: Color3?, keepColor: boolean?, keepTransparency: boolean?}?)
	local def = ML.get(name)
	local o = opts or {}
	local useVariant = ML.hasVariant(def.variant)
	local mat = if useVariant and def.variantMaterial then def.variantMaterial else def.Material
	if part.Material ~= mat then
		part.Material = mat
	end
	local mv = if useVariant then def.variant :: string else ""
	if part.MaterialVariant ~= mv then
		part.MaterialVariant = mv
	end
	if not o.keepColor then
		local col = o.color or def.Color
		if part.Color ~= col then
			part.Color = col
		end
	end
	if part.Reflectance ~= def.Reflectance then
		part.Reflectance = def.Reflectance
	end
	if def.Transparency ~= nil and not o.keepTransparency then
		part.Transparency = def.Transparency
	end
	-- MeshParts only: a pre-made SurfaceAppearance template (authored in Studio from the uploaded maps)
	if part:IsA("MeshPart") then
		local assets = ReplicatedStorage:FindFirstChild("MaterialLibraryAssets")
		local template = assets and assets:FindFirstChild(name)
		local old = part:FindFirstChild("MaterialLibrarySA")
		if template and template:IsA("SurfaceAppearance") and not part:FindFirstChildOfClass("SurfaceAppearance") then
			local sa = template:Clone()
			sa.Name = "MaterialLibrarySA"
			sa.Parent = part
		elseif old and not template then
			old:Destroy()
		end
	end
end

-- STUDIO, EDIT mode, command bar only (MaterialVariant maps are Plugin Security, the command bar may set them):
-- creates or updates a MaterialVariant per entry that has a `variant` and at least a colour map id, and a
-- SurfaceAppearance template per entry under ReplicatedStorage.MaterialLibraryAssets. Then save the place.
--   require(game.ReplicatedStorage.MaterialLibrary).studioCreateVariants()
-- Fill the asset ids in ML.materials first (docs/MATERIAL_LIBRARY.md, "Upload").
function ML.studioCreateVariants(): string
	local made, skipped = {}, {}
	local assets = ReplicatedStorage:FindFirstChild("MaterialLibraryAssets")
	for name, def in ML.materials do
		local sa = def.surfaceAppearance
		if not sa.colorMap then
			table.insert(skipped, name)
			continue
		end
		if def.variant then
			local mv: any = MaterialService:FindFirstChild(def.variant)
			if not mv then
				mv = Instance.new("MaterialVariant")
				mv.Name = def.variant
				mv.Parent = MaterialService
			end
			mv.BaseMaterial = def.variantMaterial or def.Material
			mv.StudsPerTile = def.studsPerTile or 8
			mv.ColorMap = sa.colorMap
			if sa.normalMap then mv.NormalMap = sa.normalMap end
			if sa.roughnessMap then mv.RoughnessMap = sa.roughnessMap end
			if sa.metalnessMap then mv.MetalnessMap = sa.metalnessMap end
		end
		if not assets then
			local folder = Instance.new("Folder")
			folder.Name = "MaterialLibraryAssets"
			folder.Parent = ReplicatedStorage
			assets = folder
		end
		local t: any = (assets :: Instance):FindFirstChild(name) or Instance.new("SurfaceAppearance")
		t.Name = name
		t.ColorMap = sa.colorMap
		if sa.normalMap then t.NormalMap = sa.normalMap end
		if sa.roughnessMap then t.RoughnessMap = sa.roughnessMap end
		if sa.metalnessMap then t.MetalnessMap = sa.metalnessMap end
		t.Parent = assets
		table.insert(made, name)
	end
	ML.clearCache()
	table.sort(made)
	table.sort(skipped)
	local msg = `[MaterialLibrary] made/updated: {table.concat(made, ", ")}; no colour map yet: {table.concat(skipped, ", ")}`
	print(msg)
	return msg
end

return ML
