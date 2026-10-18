# Visual art direction — MIDNIGHT PATTAYA (VIS-4 / VIS-5)

Team vis-slice, 2026-10-19. Status: **written, not built in Studio** (the leader builds, drives and captures).
Target look: `docs/images/ui_mockup_owner.png`. Current look: `docs/images/hud_v3_full_freeroam.jpg` and
`hud_v2_full_looprace.jpg`, which show flat textured boxes with the same window tile on every face, a violet wash
over everything, and a camera low behind the car.

Sibling teams:
- **vis-lighting** owns the sky, Lighting presets, wet road and `MaterialLibrary`.
- **vis-blender** owns the MeshPart kits.

This file sets the shared rules. The facade kit below is ours.

## 1. Art rules

| Rule | What it means in the game | Who applies it |
|---|---|---|
| Navy night sky, not purple | Night sky and fog read deep navy / blue-black (about RGB 10–30, 15–35, 45–80). Violet is allowed only as a thin band of city glow on the horizon. Today's night preset (`PattayaNightLights` night `skyAtmo`: Decay 70,50,150, Color 200,110,210) is the "violet wash" the owner saw. | vis-lighting |
| No uniform purple | Never tint the whole frame. ColorCorrection TintColor stays near white. Purple/magenta only on light sources (neon). Walls keep their own colours: cream, white, sand, pale blue and green shophouse paint. | vis-lighting + us (wall colours are copied from the procedural box palette, never re-tinted) |
| Warm streetlights | Street and promenade lamps are warm white to sodium amber (around 255,200,140). They are the main road light, so asphalt reads warm under them and cool between them. | vis-lighting (lamp colours exist in `PattayaBuilder` / `PattayaCoastBuilder`) |
| Neon accents, budgeted | Cyan (0,235,255) and magenta (255,40,190) only, as thin strips on commercial fronts and some shophouses. Each strip turns Neon at night (NightNeon). Budget: 160 strips in the slice (93 used). One or two strips per building, never whole walls. The city's existing neon signs near Walking Street are respected: a face with one gets no extra signboard or neon from us. | us (kit `NeonSign` parts) |
| Selective lit windows | At night 25–40 % of windows are lit (per style, ± 10 % per building). Of those, 65 % are warm (255,214,140) and 35 % cool (190,225,255). Shop interiors are lit at 75–90 %. Unlit windows stay dark glass. Never light every window. | us (kit `lit` / `litOnly` parts) |
| Pattaya identity | Thai shophouse rows with roller shutters, awnings, AC units and rooftop water tanks. Beach Road hotels with white balcony bands. Bilingual Thai/English signboards with generic shop words only (no brands, no logos, no real business names, even where OSM has them). Palms and the beach promenade come from the coast and city layers, so we do not duplicate them. | us + coast/furniture layers |
| Readable silhouettes | Ground floor, mid floors and roofline are distinct: shopfront with awning, then a repeated floor rhythm, then parapet and roof plant. | us |
| Collisions never change | Facades are decoration. Every building keeps its exact collision box (`VisHull`) and its road clearance. | us |
| Camera serves the road | The chase camera keeps the road ahead in frame. No shake, no motion blur, no roll. FOV only widens with speed. | us (`MidnightCamera`) |

## 2. Facade kit (`tools/mapgen/config/vis_slice.json` → `manifest.modules`)

How it works:
- Every building keeps its original box as an invisible collider, `VisHull`.
- The visible wall, `VisCore`, is inset by the style's depth (`ins`, 0.6–1.8 studs), but only on decorated faces.
- Modules fill the gap between the core face and the original box face, so nothing sticks out of the box.
- The undecorated faces keep the original facade Textures, including the night tile.

Placement units:
- `span`: once per module instance across the face.
- `bay`: repeated per bay. The bay width comes from the style and is rounded to the face.
- `edge`: at every bay boundary.
- `n`: depth measured from the core face outwards.

Each part carries `Mat` (MaterialLibrary name) and `MeshSlot` (= the module name, the Blender kit slot).

### Ground floor (height 11.57 studs = one 8.57 level + 3)
```
shopfront_a (shophouse)           shopfront_b (commercial)          lobby_a (hotel / condo)
+------------------------+        +------------------------+        +------------------------+
| [ SIGNBOARD  TH / EN ] |        |[====  SIGN BAND  =====]|        |     [ HOTEL SIGN ]     |
|~~~~~~~~ NEON ~~~~~~~~~ |opt     |~~~~~~~~ NEON ~~~~~~~~~ |opt     |========================| canopy
|\\\\\\\ AWNING \\\\\\\\\|wedge   |  |      |      |      | |        ||  ____  ||  ____  ||  |
||==shutter==||==shutter=|        |  | lit  | glass| lit  | |        || |lobby| || |lobby| ||  |
||  lit shop || lit shop |        |  |      |      |      | |mullions|| | lit | || | lit | ||  |
|P           P           P pilaster|  |      |      |      | |        |P |     | P |     | P  pilasters
+------------------------+        +------------------------+        +------------------------+
garage_door_a (industrial): lintel + roller door per 14-stud bay
house_front_a (house): eave wedge + one window per bay
```

### Mid floors (one per level, 8.57 studs; "whole" = once over all mid floors)
```
window_pair_ac_a (shophouse)      balcony_row_a + band_glass_a +    balcony_grid_a + fins_a (condo)
                                  fins_a every ~30 studs (hotel)
+------------------------+        +------------------------+        +------------------------+
|  [##] [##]  [##] [##]  |        |  lit     dark    lit   |        |lit |dark| lit|dark|lit |
|  [##] [##]o [##] [##]o | AC     |▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓| glass   |▓▓▓▓|▓▓▓▓|▓▓▓▓|▓▓▓▓|▓▓▓▓|
|_______sill_____________|        |#### rail (full span) ##|        |#rl#|#rl#|#rl#|#rl#|#rl#| rail per bay
                                  |======= slab ===========|        |=========slab===========|
curtain_wall_a + transom_a (commercial): blue glass over all mid floors, mullion every 7 studs, a transom per floor,
                                  some panes lit (litOnly)
window_row_a (industrial / house): one window per 10-stud bay
```

### Roofline and roof
| Module | Parts | Notes |
|---|---|---|
| `parapet_a` | 1 cornice band per decorated face, 1.2 studs, top = box top | in the inset band, never above the box |
| `roof_plant_a` | 2 AC condensers + plant/stair room (4 × 3.2 × 4) | hotels, condos, commercial; needs a 10 × 12 roof |
| `water_tank_a` | stand + vertical cylinder tank (blue) | shophouses and condos; needs 5 × 5 |
| `ac_pair_a` | 2 AC condensers | industrial |

Roof modules are the only parts above the original box height (at most 4.6 studs, non-colliding, not queryable).
A roof module is dropped where a taller box or a prop overlaps the roof (6 cases).

### Styles (category → modules)
| Style | Categories | Inset | Faces | Ground | Mid | Whole | Roof | Lit win / shop | Neon |
|---|---|---|---|---|---|---|---|---|---|
| shophouse | shophouse | 1.2 | 1 (2 on a main-road corner) | shopfront_a (12-stud bay) | window_pair_ac_a | — | water_tank_a | 35 / 75 % | 12 % of buildings |
| hotel | hotel | 1.8 | 1 (2 if the 2nd face sees Beach/Second Road) | lobby_a | balcony_row_a | band_glass_a, fins_a/30 | roof_plant_a | 30 / 90 % | — |
| condo | condo, apartments | 1.6 | 2 | lobby_a | balcony_grid_a | band_glass_a, fins_a/9 | roof_plant_a, water_tank_a | 25 / 90 % | — |
| commercial | commercial, mall, public | 0.8 | 2 | shopfront_b | transom_a | curtain_wall_a/7 | roof_plant_a | 40 / 80 % | 50 % of commercial/mall |
| industrial | industrial, parking | 0.6 | 1 | garage_door_a | window_row_a | — | ac_pair_a | 15 % | — |
| house | house | 0.8 | 1 | house_front_a | window_row_a | — | — | 30 % | — |

Temples are not touched.

### Which faces get modules
- **Front face:** the face that sees the nearest road within 60 studs. Beach Road and Second Road count 25 studs closer. A beachfront face that sees the coastline also counts.
- **Party walls:** a face whose first 6 studs outward are ≥ 30 % covered by another box is a party wall and gets nothing.
- **Facade band:** the band between the box face and the core face must be free of other boxes (the OSM data has 508 overlapping box pairs), city props, furniture, landmarks and the Walking Street gate. Where it is not free, the face's span is trimmed to its largest free stretch, or the face is dropped when that stretch is shorter than half the face.

### Materials (`Mat` attribute → fallback `Enum.Material`, used until MaterialLibrary styles the part)
| Mat | Used by | Fallback |
|---|---|---|
| DarkGlass | windows, shop glass, glass bands, curtain wall | Glass |
| LitWindow | any window/shop pane that is lit at night (NightNeon) | SmoothPlastic (Neon at night via PattayaNightLights) |
| PaintedMetal | shutters, roller doors, rails, mullions, AC units, tanks | Metal |
| NeonSurface | neon strips (`NeonSign`) | SmoothPlastic (Neon at night) |
| ConcreteSidewalk | sills, balcony slabs, canopies, lintels | Concrete |
| PaintedPlaster | core walls, pilasters, fins, parapets | SmoothPlastic |
| AwningFabric | awnings | Fabric |
| SignPanel | signboards (SurfaceGui text) | SmoothPlastic |
| RoofConcrete | eaves, plant rooms | Concrete |

MaterialLibrary hook (`PattayaVisSliceBuilder.styleWithLibrary`):
- The builder looks for a ModuleScript `MaterialLibrary` in ServerStorage, then in ReplicatedStorage.
- It accepts any of these: `lib.apply(part, name)`, `lib.Apply(part, name)`, `lib.get(name)`, `lib.Get(name)`, or `lib[name]` returning `{Material, MaterialVariant, Color}`.
- Per-building colours (wall, accent, sign board) are kept.
- NightNeon parts are left alone, because PattayaNightLights switches them between SmoothPlastic by day and Neon at night.
- `V.Build({materialLibrary = false})` skips the library.

Names vis-lighting needs to provide (or map): the nine above. `DarkGlass`, `LitWindow`, `ConcreteSidewalk`,
`PaintedMetal` and `NeonSurface` come from the brief; the other four are ours.

### MeshPart swap later (vis-blender)
- Every part has `MeshSlot` = module name and `SlotInst` = `"<placement>:<floor>:<bay>"`. Roof parts use `"r<n>"`.
- To swap a module for a MeshPart, group the parts of one building model by (`MeshSlot`, `SlotInst`) and use their combined bounding box as the target frame.
- A later builder option can then create one MeshPart per group from an asset-id manifest keyed by slot name. The slots are the 17 module names above plus `core_<style>`.

## 3. Vehicle camera (VIS-5) — `StarterPlayerScripts.MidnightCamera`
**On/off:**
- It runs only while the player sits in their own RaceCar seat and the camera subject is the player. It steps aside for the circuit spectator.
- `Lighting` or `LocalPlayer` attribute `MidnightCamera = false` gives back Roblox's default vehicle camera live: CameraType Custom and the saved FOV.

**Tuning:** each knob can be overridden live with a number attribute `MC_<name>` on LocalPlayer (wins) or Lighting.

| Knob | Default | Meaning |
|---|---|---|
| Distance / DistanceAtTop | 17 / 21 | studs behind the car, at rest / at top speed |
| Height / HeightAtTop | 6.0 / 5.2 | camera height above the car centre |
| LookHeight | 2.6 | aim point above the car |
| LookAhead / LookAheadAtTop | 10 / 28 | aim point ahead of the car (keeps the road in frame) |
| FovBase / FovMax | 70 / 85 | FOV at ≤ FovStartSpeed / at the car's nitro top speed |
| FovStartSpeed | 40 | studs/s |
| TopSpeed | 0 | 0 = the car's own `CarSpecs` nitroSpeed (200–245), else this value |
| YawDamping / YawDampingAtTop | 5 / 9 | 1/s, heading smoothing (higher = stiffer) |
| DistanceDamping | 3 | 1/s, distance/height follow the speed |
| HeightDamping | 10 | 1/s, car height smoothing (kerbs) |
| FovDamping | 3 | 1/s |
| VelocityBlend | 0.35 | 0 = follow the nose, 1 = follow the velocity (drift view) |
| OrbitMax / OrbitReturn | 50 / 4 | look-left/right limit (deg) and spring-back (1/s) |
| LookBackDamping | 12 | 1/s, turn into look-back |
| CollisionPad / MinDistance / CollisionRelease | 1.0 / 6 / 4 | wall pull-in |
| ThinObstacle | 4 | parts thinner than this never pull the camera in |
| IntroTime | 0.4 | s, glide from Roblox's camera when you sit down |

**Keys:**
- Hold **Q** (gamepad R3) to look back.
- **Right-mouse drag** or the **right stick** to look left/right.
- No existing binding uses these. E is avoided because the prompts use it.
- With Reduce Motion on (`LocalPlayer.ReducedMotion` or Roblox's setting), the FOV stays at FovBase.

**Debug:** `_G.MidnightCamera.state()` from the client command bar.
