# Night lighting presets (VIS-3)

**Status:** VIS-3 presets captured by the leader (`docs/images/vis_preset_*.jpg`); the owner fixed their roles on
2026-10-19 (table below). **VIS-7.1 (window glow, bloom, wet road): written, not seen.** This page lists the presets,
their roles, the night styles of lit panes and neon, and how to switch and compare them.

## Preset roles (owner decision, 2026-10-19: final)
| Preset | Role | When it is used | Road look it pairs with |
|---|---|---|---|
| **MidnightClear** | **game default** | no `LightingPreset` attribute set (normal play) | dry |
| **MidnightWet** | after rain | set by a weather / event script or the command bar after a rain spell | wet |
| **Dawn** | early morning | early-morning sessions / events (blue-hour night, golden dawn) | dry |
| **Daylight** | day | day sessions; also the brightest night if a device reads too dark | dry |
| **Legacy** | **rollback only** | never in normal play; only to compare with or fall back to the pre-VIS-3 look | off |

Rules that follow from the roles:
- New look work tunes **MidnightClear** first; MidnightWet is tuned as "MidnightClear after rain", never on its own.
- Legacy is frozen: its values, lamps, neon and lit panes stay exactly as before VIS-3 (it ignores the VIS-7.1 night
  styles), so it is always a true rollback.
- Every knob still works on every preset: `NightExposure` (owner's +0.4 is baked into the 0.95 exposure),
  `NightSky`, `LightingPreset`, `RoadLook`, `PattayaLighting = false`.

## VIS-7.1: lit windows, shopfronts and neon (written, not seen)
Problem (captures `vis_preset_midnightclear.jpg`, `vis_cap4_neon_district.jpg`): every lit pane was Neon, so large
panes and shopfront glass rendered as flat, blown-out yellow / magenta blocks, i.e. as light sources. Even the
owner's live retint to 150,118,70 (`vis_slice_v1_night_warm.jpg`) is still Neon and still blooms at the big panes.

Fix: at night `PattayaNightLights` gives each NightNeon part a style from the data table
`MaterialLibrary.NightStyles[Mat]` (`roblox/src/ReplicatedStorage/MaterialLibrary.luau`). Edit the table, not the
script, to tune it.

| Key (`Mat`) | Which parts | Night material | Night colour | Why |
|---|---|---|---|---|
| `LitWindow` **large** (pane face > 20 studs²) | balcony / transom `WindowLit`, big `Window`s | **SmoothPlastic** (no Neon) | NightColor × **1.5** (150,118,70 → 225,177,105) | lit by the scene like a lit curtain: reads warm against the cool walls and dark glass, never blooms |
| `LitWindow` **small** (≤ 20 studs²) | small `Window`s (window pairs, rows) | Neon | NightColor × **0.68** (150,118,70 → 102,80,48) | small points of light, dimmed so they glow without blowing out |
| `Shopfront` (LitWindow named `ShopGlow`, `ShopGlass`, `LobbyGlass`, or attribute `Shopfront = true`) | ground-floor shop / lobby glass | **Glass** | NightColor × **1.4** (→ 210,165,98) | warm shop interior seen through glass; the light accent is the module's own thin `NeonSign` strip (shopfront_a / _b have one, lobby_a has none, none is added) |
| `NeonSurface` | `NeonSign` strips of the slice | Neon | palette hue rule, then HSV value capped at **0.85** (cyan 0,223,255 → 0,190,217; magenta 255,43,214 → 217,37,182) | stays saturated cyan / magenta instead of a white core |
| `NeonSign` (always-Neon sign props, PattayaBuilder) | old district signs | Neon (unchanged) | palette rule + value cap **0.85** | same reason |
| `_default` (no `Mat` / unknown) | circuit window bands, landmark and furniture lamps, coast | Neon | palette rule (as before) | unchanged |

- By day every NightNeon part is SmoothPlastic + DayColor, as before. Reflectance and Transparency are never touched.
- Pane area = the two largest axes of the part's Size multiplied (the face, whatever the part's orientation).
- The style is re-applied on a preset change (only registered parts, no world scan) and on the day/night switch.
- **Legacy** ignores the table (Neon + raw NightColor); so does any NightNeon part if MaterialLibrary cannot load
  (the script warns once and falls back).
- Bug fixed on the way: vis-slice neon strips are named `NeonSign` *and* NightNeon, so the sign recolour also ran on
  them and painted their dim day colour through the palette (bright cyan by day). A NightNeon part is now styled by
  the NightNeon path only.
- No new lights, no new parts, no SurfaceGuis: only Material and Color of existing parts change.

### Bloom (VIS-7.1)
| Keyframe | MidnightClear before → now | MidnightWet before → now |
|---|---|---|
| night | 0.45 / 1.3 → **0.35 / 1.45** | 0.55 / 1.2 → **0.40 / 1.40** |
| dusk (neon is on from 17:48) | 0.5 / 1.2 → **0.40 / 1.35** | inherits Clear → 0.40 / 1.35 |
| dawn (neon is on until 6:18) | 0.45 / 1.25 → **0.40 / 1.35** | inherits Clear → 0.40 / 1.35 |

(Intensity / Threshold; Size stays 24.) Dawn's night and dusk keyframes inherit Clear's (now 0.35 / 1.45 and
0.40 / 1.35); its own dawn keyframe (0.5 / 1.2) and Daylight's night (0.4 / 1.35) are unchanged.

**Readable-road rule still holds:** exposure is unchanged in every preset (MidnightClear 0.95 with the owner's
NightExposure +0.4 baked in, Wet 1.0), ambient is unchanged, and bloom only *adds* light around bright pixels, so
lowering it cannot darken the road. What changes: lane markings and headlight flares lose their soft halo. MidnightWet
also gets Atmosphere Haze 1.3 → **1.5** at night (humid air); density is unchanged, so the far road stays visible.

Scripts:
- `StarterPlayerScripts.PattayaNightLights`: the presets, street-lamp colours, neon palette and headlight colour.
- `StarterPlayerScripts.PattayaRoadLook`: the road surface. See `docs/MATERIAL_LIBRARY.md`.

Both scripts run on the client only and never save anything into the place.

## What was wrong (captures `night_sky_v1_corridor.jpg`, `hud_v3_full_freeroam.jpg`)
- **Uniform purple cast.** Five things all pushed the same violet onto every surface and onto the sky:
  - OutdoorAmbient 118,112,160 and ColorShift_Top 90,60,160
  - the Atmosphere haze colour 200,110,210, with Haze 2.6 and Offset 0.32
  - the lilac grade tint 232,224,255
  
  Sidewalks, building facades and the sky all came out the same lilac, so nothing stood out.
- **Bloom too strong.** Intensity 1.0 with Threshold 0.92 bloomed anything a bit brighter than white: lamp heads,
  white markings, the GPS ribbon, headlight flares.
- **Flat road.** The road is SmoothPlastic 46,47,52 with no texture and no reflection.

## The fix in one line
Keep the **brightness** the owner tuned (exposure 0.95, ambient luminance about the same), but change its **hue**
from violet to steel navy. The colour then comes from warm orange lamps and cyan/magenta neon. Bloom is limited to
what is really bright.

## Switching (live, command bar)
```lua
game.Lighting:SetAttribute("LightingPreset", "MidnightWet")   -- MidnightClear (default) | MidnightWet (after rain) | Dawn (early morning) | Daylight (day) | Legacy (rollback)
game.Lighting:SetAttribute("LightingPreset", nil)             -- back to the default (MidnightClear)
game.Lighting:SetAttribute("RoadLook", "wet")                 -- "dry" | "wet" | "off"; nil = follow the preset
game.Lighting:SetAttribute("TimeLock", 21)                    -- hold the clock (server command bar), nil = run again
```
- **Where to run it:**
  - Server command bar: the change replicates to every client.
  - Client command bar: only your own view changes, which is enough for a capture.
- **Output:** each client prints `[PattayaLighting] preset <name>` and `[PattayaRoadLook] <mode>`.
- **Unknown name:** the client warns once and uses MidnightClear.
- **Owner knobs still work on every preset:**
  - `NightExposure` is added to the exposure at night.
  - `NightSky` (0..1) blends from the preset's plain night atmosphere to its night-sky atmosphere and stars.
  - `PattayaLighting = false` restores the template Lighting.
- **Clock blend is unchanged:** night 0:00–4:48, dawn 6:12, day 8:00–16:30, dusk 18:18, night from 19:36. Each
  preset supplies its own four keyframes.

## Presets
Each preset is a complete set of night, dusk, day and dawn keyframes. It also sets:
- the street-lamp light and lamp-head colours
- the neon palette
- the headlight colour
- the road look it pairs with (used when `RoadLook` is not set)

Roles: see "Preset roles" at the top.

| Preset | Idea | Road look |
|---|---|---|
| **MidnightClear** (default) | dry, clear neon night; navy, not purple; readable road | dry |
| **MidnightWet** | after rain: more sheen and humidity, lamp halo, stronger grade; overcast humid day | wet |
| **Dawn** | blue-hour night (lighter navy, horizon glow, the "TimeLock 19.6" look without touching the clock); golden dawn and dusk | dry |
| **Daylight** | brightest and most readable: night exposure *above* the owner baseline (fallback for "too dark", phones); crisp clear day | dry |
| **Legacy** | exactly the values before VIS-3 (violet night, bloom 1.0/0.92); lamps, neon and headlights as built | off |

### Night keyframe (the one the owner is choosing)
| | Legacy | MidnightClear | MidnightWet | Dawn | Daylight |
|---|---|---|---|---|---|
| Ambient | 74,70,104 violet | 60,68,96 navy | 54,62,90 | 70,80,112 | 78,86,112 |
| OutdoorAmbient (luminance) | 118,112,160 (117) | 100,114,150 (114) | 94,108,144 (108) | 112,128,170 (128) | 124,134,166 (135) |
| ColorShift_Top | 90,60,160 | 120,140,190 moonlight | same | 130,150,210 | same as Clear |
| Brightness / Exposure | 1.7 / 0.95 | 1.7 / **0.95** (owner baseline) | 1.7 / 1.0 | 1.7 / 0.95 | 1.7 / 1.1 |
| EnvDiffuse / EnvSpecular | 0.45 / 0.8 | 0.45 / 0.8 | 0.4 / **1.0** | 0.45 / 0.8 | 0.5 / 0.8 |
| Atmosphere density / haze / colour | 0.26 / 1.1 / 90,65,140 | **0.22** / 1.0 / 70,84,120 | 0.26 / **1.5** (VIS-7.1) / 72,86,122 | 0.22 / 1.0 / 90,110,160 | 0.22 / 1.0 / 70,84,120 |
| Night sky (NightSky=1): Decay / Color / Haze / Offset | 70,50,150 / 200,110,210 / 2.6 / 0.32 | **34,42,118 indigo** / 96,92,150 / 1.8 / 0.22 | same, haze 2.0 | 60,78,170 / 150,120,170 / 2.0 / 0.26 | 44,56,120 / 96,92,150 / 1.8 / 0.22 |
| Stars | 3000 | 3000 | 1500 (haze) | 1500 | 2000 |
| Bloom intensity / size / threshold (VIS-7.1) | 1.0 / 24 / 0.92 | **0.35 / 24 / 1.45** | 0.40 / 24 / 1.40 | 0.35 / 24 / 1.45 | 0.4 / 24 / 1.35 |
| Grade brightness / contrast / saturation / tint | 0.04 / 0.1 / 0.16 / 232,224,255 lilac | 0.02 / 0.12 / 0.12 / 240,244,255 cool neutral | 0.02 / 0.14 / 0.16 / 236,242,255 | as Clear | 0.02 / 0.08 / 0.12 / as Clear |

### Dusk, day and dawn (MidnightClear; the others differ as noted)
| | Dusk | Day | Dawn |
|---|---|---|---|
| Ambient / Outdoor | 70,58,78 / 140,104,118 | 110,112,120 / 140,142,150 | 72,70,88 / 132,122,140 |
| Brightness / Exposure | 1.7 / 0.3 | 2.6 / 0 | 1.5 / 0.2 |
| ColorShift_Top | 255,150,100 | 255,245,225 | 255,190,150 |
| Atmosphere density / haze / colour / glare | 0.3 / 1.8 / 250,150,120 / 0.4 | 0.26 / 1 / 200,218,235 / 0.2 | 0.34 / 2 / 255,196,170 / 0.3 |
| Bloom intensity / threshold (VIS-7.1) | 0.40 / 1.35 | 0.35 / 1.6 | 0.40 / 1.35 |
| Grade contrast / saturation | 0.1 / 0.14 | 0.06 / 0.08 | 0.06 / 0.1 |

How the other presets differ from these keyframes:
- **MidnightWet:**
  - all keyframes: EnvSpecular 1.0
  - dusk: fog density 0.34, haze 2.0
  - day: overcast humid. Brightness 2.2, Outdoor 132,136,146, fog 0.32, haze 1.6, colour 190,200,210, saturation 0.06
  - dawn: fog density 0.38, haze 2.2
- **Dawn:**
  - dusk and dawn: golden. ColorShift_Top 255,170,100 (dusk) and 255,180,120 (dawn), haze colour 255,170–180,120–140,
    glare 0.5, haze 2.4, saturation 0.14–0.16
  - dawn: exposure 0.3
  - day: warmer, ColorShift_Top 255,232,200, tint 255,248,236
- **Daylight:**
  - day: Brightness 3.0, Outdoor 150,152,158, fog 0.22, haze 0.8, contrast 0.08, saturation 0.12
- **Legacy:** the old values, unchanged.

### Lights and neon per preset (no lights added; only colour and brightness of the existing ones)
| | Legacy | MidnightClear / Dawn | MidnightWet | Daylight |
|---|---|---|---|---|
| Lamp SpotLight colour | 255,220,170 (as built) | **255,176,96 sodium orange** | 255,176,96 | 255,190,120 |
| Lamp SpotLight brightness | as built (2.2 city, 1.8 promenade) | ×1.0 | ×1.15 | ×1.1 |
| Lamp head (Neon at night) | 255,236,190 | 255,170,80 | 255,170,80 | 255,184,104 |
| Neon palette | as built | cyan **#00DFFF**, magenta **#FF2BD6** | same | same |
| Headlights | 255,244,220 | 255,241,222 natural warm white | same | same |

- **Neon palette rule:** applies to NightNeon parts (their `NightColor`) and to the always-Neon `NeonSign` props.
  - A cyan-ish hue (HSV h 0.45–0.58) becomes #00DFFF.
  - A magenta or pink hue (h 0.80–0.97) becomes #FF2BD6.
  - These are kept: grey or dark colours, warm windows, yellow, green, violet, and red/amber/green signal lamps.
  - The original colours are kept in memory, so Legacy brings them back.
- **Floodlights:** the Bira circuit floodlights keep their own colour in every preset.
- **Tail lights:** unchanged.

## Rationale
- **Navy, not purple, at the same brightness.** The "too dark" history (2026-10-18) came from lowering the light
  level. MidnightClear keeps the level: OutdoorAmbient luminance is 114 against 117, and the exposure stays 0.95. Only
  the hue moves, to a desaturated blue (h about 223°). The road, sidewalks and facades then read as neutral
  night-blue greys, and orange lamps and cyan/magenta signs become the only strong colours, as in the mock-up.
- **Sky.** The Atmosphere Decay paints the night sky. In Legacy, Decay 70,50,150 with Color 200,110,210 at Haze
  2.6 gave the flat bright violet seen in `night_sky_v1_corridor.jpg`. MidnightClear uses about half the values,
  blue-shifted: Decay 34,42,118 and Color 96,92,150 at Haze 1.8. That should give a deep indigo sky where 3000 stars
  can show. The haze colour also tints distant buildings, so a navy haze reads as night air, not a purple wash.
- **Bloom.** VIS-3 used Threshold 1.3 / Intensity 0.45; the captures still showed big Neon panes smeared, so VIS-7.1
  moved to 1.45 / 0.35 (≤ 0.4, ≥ 1.4) together with the non-Neon lit panes. Only HDR-bright pixels bloom: neon strips,
  lamp heads and headlight flares; white markings, pale facades and lit panes should not.
- **Grade.** The lilac tint is replaced by a faint cool neutral (240,244,255). Saturation drops from 0.16 to 0.12,
  because the neon is already saturated. Contrast rises from 0.1 to 0.12 to separate road from sidewalk.
- **Fog.** Density goes from 0.26 to 0.22. That gives low fog, with the far skyline still visible as silhouettes.
- **Wet look.** MidnightWet raises EnvironmentSpecularScale to 1.0. Smooth surfaces then pick up more of the sky
  and environment. The RoadLook "wet" surface (SmoothPlastic 26,28,34, Reflectance 0.25; junctions 0.3; markings
  0.4; VIS-7.1) shows sharp highlights from lamp
  SpotLights and headlights. Roblox has no screen-space reflections, so neon is **not** mirrored in the road. The
  mock-up's streaks of reflected sign light cannot be reproduced with built-in features (see `MATERIAL_LIBRARY.md`).
- **Lamps.** 255,176,96 is a sodium/LED-warm orange, which matches the mock-up's warm streetlights. It contrasts
  with the cool navy ambient and the cyan/magenta neon.

## Comparison protocol (leader)
Use the same camera, the same times, one preset at a time. Graphics quality: the **same** fixed level for all
captures (Settings → Graphics manual, max if possible). Write it in the capture name.

1. **Technology:** check `Lighting.Technology` in Studio Properties. It is Studio-only and scripts cannot set it.
   Write it down; `Future` is recommended for the lamp/headlight highlights on the wet road. Do not change it
   between captures. If you do try another value, capture that as a separate set.
2. **Start Play,** with the car on the road. Server command bar: `game.Lighting:SetAttribute("TimeLock", 21)`.
3. **Freeze the camera** (client command bar):
   ```lua
   local cam = workspace.CurrentCamera; _G.shotCF = cam.CFrame; cam.CameraType = Enum.CameraType.Scriptable
   ```
   To put it back later: `workspace.CurrentCamera.CFrame = _G.shotCF`. To unfreeze:
   `workspace.CurrentCamera.CameraType = Enum.CameraType.Custom`.
4. **Capture each preset.** For each of `Legacy`, `MidnightClear`, `MidnightWet`, `Dawn`, `Daylight`:
   - Run `game.Lighting:SetAttribute("LightingPreset", "<name>")`.
   - Wait 1 s. Presets apply 4 times a second, and the road restyles over a few frames.
   - Capture. Name it `vis3_<spot>_<preset>_t21.jpg`.
5. **Repeat at 12 and at 6:** `TimeLock = 12`, then `TimeLock = 6` (6 is the dawn ramp).
6. **Road look alone,** at MidnightClear, t21: `RoadLook = "off"`, `"dry"`, `"wet"`. Then remove it (nil).
7. **Knobs,** at MidnightClear, t21:
   - `NightSky = 0.5`, then remove it.
   - `NightExposure = -0.2`, then `0.2`, then remove it.

   This shows whether the owner's baseline still holds with the new hue.

### Spots (each one tests something different)
| Spot | Why |
|---|---|
| **A. Beach Road / Central Loop start, behind the car, looking along the road** (spawn area) | road readability at speed, lamps, wet highlights, sky with stars, sea side |
| **B. Walking Street / a neon-sign block** (or the densest NeonSign cluster on the Central Loop) | neon palette (cyan/magenta), bloom, overexposure |
| **C. The Bira corridor spot of `night_sky_v1_corridor.jpg`** | direct before/after against the existing capture (sky, purple cast) |
| **D. Bira grid at night** (`Circuit_bira`) | floodlights unchanged, window bands (NightNeon warm), bloom on the floodlight heads |

Minimum set if time is short: A and C at t21 for all five presets, plus A at t12 and t6 for MidnightClear and Legacy.

### What to look for
- **Purple:** is the sidewalk, facade or sky still lilac? It should be a neutral or blue grey, with an indigo sky.
- **Road readability:** can you see the road edges, the lane dashes and the centre line 150+ studs ahead at t21,
  without headlights? It must be at least as readable as Legacy.
- **Sky:** deep navy/indigo with visible stars, not black and not bright violet. Is there a soft glow at the horizon?
- **Neon:** do the signs read as cyan and magenta with a modest halo? Are they blown out to white? Is there a
  bloom smear across the screen?
- **Lamps:** a warm orange pool under each lit lamp. Every second lamp has a real light; the others are only a
  glowing head.
- **Wet road:** sharp lamp and headlight highlights and a darker surface. The neon will not mirror in the road
  (engine limit), and that is not a bug.
- **Day (t12):** no fog wall, the sea is blue, the facade colours are natural, and nothing blooms.
- **Dawn (t6):** peach/golden and not muddy. Lamps are still on until 6:18.
- **FPS:** presets change only Lighting properties, the effects and colours, so the cost should be unchanged. Check
  it anyway with `workspace:SetAttribute("PerfProbe", 10)` (server) at spot A, t21, for Legacy and MidnightWet. Wet
  turns on RoadLook "wet".

## Thai text on signboards (recommendation; the slice builder belongs to vis-mesh)
The slice signboards (`PattayaVisSliceBuilder.addSign`) and PattayaBuilder / FurnitureBuilder signs use a
SurfaceGui TextLabel with `Enum.Font.GothamBold` and Thai strings, relying on "Roblox's font fallback".

What the Creator Docs say (read 2026-10-19):
- The `Enum.Font` list (Legacy, Arial, SourceSans*, Gotham*, BuilderSans*, Arimo*, Roboto*, Ubuntu, …) and the
  `Font` datatype's built-in family list (`rbxasset://fonts/families/*.json`: Arimo, Builder Sans, Source Sans Pro,
  Roboto, Ubuntu, Montserrat, Nunito, …) have **no column for supported scripts and do not mention Thai.**
  https://create.roblox.com/docs/reference/engine/enums/Font,
  https://create.roblox.com/docs/reference/engine/datatypes/Font
- None of these families is a Thai design; Thai glyphs on Roblox come from the engine's fallback font when the chosen
  family has no glyph. The docs do not document that fallback (which font, which weights), so it cannot be checked
  from here: **unverified, needs a capture.**

Recommendation:
- **Thai labels: `Font.fromName("BuilderSans", Enum.FontWeight.Bold)`** (FontFace), Latin labels keep the Theme's
  Gotham. Builder Sans is Roblox's current app-UI family (the default for new UI), so it is the family most likely
  to have its Thai fallback tuned to it; Gotham is a legacy licensed face with a wide geometric Latin, and a fallback
  Thai next to it tends to look mismatched in weight. Both claims are inferences, not documented: the capture below
  decides. Builder Sans is a plain sans, so it sits with the Midnight Theme (GothamBlack / GothamBold) without
  clashing.
- Second choice: `Enum.Font.Arimo` / `ArimoBold` (metric-compatible Arial) or `SourceSansBold`.
- Avoid decorative families (Arcade, SciFi, Bangers, Cartoon, Highway, …) for Thai: the Latin face changes but the
  Thai fallback does not, so the two scripts look unrelated.
- Thai has stacked vowels and tone marks above and below the line: keep the existing 8 % top/bottom UIPadding with
  `TextScaled`, or the marks clip.
- How the vis-mesh team would apply it (one line in `addSign`, their file; `"\224[\184\185]"` matches the
  UTF-8 lead bytes of the Thai block U+0E00–U+0E7F, since Lua patterns work on bytes):
  `if text:find("\224[\184\185]") then label.FontFace = Font.fromName("BuilderSans", Enum.FontWeight.Bold) end`
- Leader check (client command bar, at a Thai signboard, night): compare one label under each font
  ```lua
  for _, g in workspace.PattayaWorld:GetDescendants() do if g:IsA("TextLabel") and g.Text:find("\224[\184\185]") then g.FontFace = Font.fromName("BuilderSans", Enum.FontWeight.Bold) end end
  ```
  Capture before / after as `vis71_thai_gotham.jpg` / `vis71_thai_buildersans.jpg`. Thai shown as boxes or
  missing marks = that font gets no fallback on this device.

## Before / after capture protocol (VIS-7.1, for the owner)
Same spot, same clock, same camera, same graphics level for every picture; only the thing being compared changes.

1. **Studio settings:** note `Lighting.Technology` and the graphics level (Settings → Graphics manual; max if
   possible) and keep both fixed. Put them in the capture note.
2. **Play**, car on Beach Road / Walking Street at the spot of `vis_cap4_neon_district.jpg` (South Pattaya /
   Walking Street, looking south along the street with shopfronts on both sides).
3. **Clock:** server command bar `game.Lighting:SetAttribute("TimeLock", 21)`. Wait 2 s.
4. **Freeze the camera** (client command bar):
   `local cam = workspace.CurrentCamera; _G.shotCF = cam.CFrame; cam.CameraType = Enum.CameraType.Scriptable`.
   Restore later with `workspace.CurrentCamera.CFrame = _G.shotCF`.
5. **"Before":** not Legacy (Legacy is the pre-VIS-3 look). The before pictures for this pass already exist
   (`vis_cap4_neon_district.jpg`, `vis_preset_midnightclear.jpg`, `vis_preset_midnightwet.jpg`) if the spot and clock
   match; if not, check out `main` at 8f08c03, capture there with the same steps, then check out this branch.
6. **"After"** captures, 1 s apart after each change:
   | # | Command (client bar is enough) | Name |
   |---|---|---|
   | 1 | `LightingPreset = nil` (MidnightClear) | `vis71_neon_district_midnightclear_t21.jpg` |
   | 2 | `LightingPreset = "MidnightWet"` | `vis71_neon_district_midnightwet_t21.jpg` |
   | 3 | `LightingPreset = "Legacy"` (rollback check: must look like before VIS-3) | `vis71_neon_district_legacy_t21.jpg` |
   | 4 | `LightingPreset = nil; RoadLook = "wet"` (road only: wet vs dry under the same light) | `vis71_road_wet_t21.jpg` |
   | 5 | `RoadLook = "dry"` | `vis71_road_dry_t21.jpg` |
   | 6 | `RoadLook = "off"`, then `nil` (must equal the builder look, then back to dry) | `vis71_road_off_t21.jpg` |
7. **Same at the spot of `vis_preset_midnightclear.jpg`** (Beach Road promenade, hotel towers on the right): #1 and
   #2 only, names `vis71_beachroad_<preset>_t21.jpg`.
8. **Dusk check:** `TimeLock = 18.5`, MidnightClear, spot of step 2: `vis71_neon_district_midnightclear_t18_5.jpg`
   (neon on with the dusk bloom).
9. Optional: the Thai font check above.

What to look for:
- **Big panes and shop glass:** warm amber / tan, clearly "lit inside", with readable edges and mullions; no flat
  yellow blocks and no glow spilling over the walls. If they read too dull, raise `colorMul` of `LitWindow.large` /
  `Shopfront` (1.5 / 1.4 → 1.7 / 1.6); if they read like cardboard, try `material = Glass` for `large`.
- **Small panes:** small warm points, no white cores. Too bright → `small.colorMul` 0.68 → 0.6.
- **Neon strips / signs:** saturated cyan and magenta with a modest halo, not white. Too dull → `maxValue` 0.85 →
  0.92, or bloom Threshold 1.45 → 1.35.
- **Road (readable-road rule):** edges, dashes and the centre line visible 150+ studs ahead at t21 without headlights,
  at least as readable as `vis_preset_midnightclear.jpg`.
- **Wet vs dry (#4 / #5):** wet clearly darker and smoother (no grain), lamp and headlight highlights sharp, junction
  discs slightly shinier; markings still bright. If wet markings read darker than dry, lower
  `MaterialLibrary.RoadPaintWet.Reflectance` 0.4 → 0.2 (a sky mirror is dark at night).
- **FPS:** `workspace:SetAttribute("PerfProbe", 10)` (server) at step 2 for MidnightClear and MidnightWet; the change
  should be within noise (no new instances; fewer Neon pixels, if anything, is cheaper).

## Roblox APIs used (Creator Docs, read 2026-10-19)
- **Lighting:** https://create.roblox.com/docs/reference/engine/classes/Lighting
  - Ambient, OutdoorAmbient (clamped never to be below Ambient), ColorShift_Top, Brightness, ExposureCompensation
    (pre-tonemap bias, ±1 = ×2), EnvironmentDiffuseScale and EnvironmentSpecularScale (environment-derived diffuse
    and specular; specular "makes smooth objects reflect their surroundings").
  - `Technology` is listed there as read-only to scripts (Studio only).
  - The newer `LightingStyle` and `PrioritizeLightingQuality` are also place settings. They are not touched here.
- **Atmosphere** (Density, Offset, Color, Decay, Glare, Haze), **Sky** (StarCount), **BloomEffect** (Intensity, Size,
  Threshold), **ColorCorrectionEffect** (Brightness, Contrast, Saturation, TintColor):
  https://create.roblox.com/docs/reference/engine/classes/Atmosphere, …/Sky, …/BloomEffect,
  …/ColorCorrectionEffect.
- **BasePart.Reflectance** reflects the sky only, and some materials ignore it:
  https://create.roblox.com/docs/reference/engine/classes/BasePart
- DepthOfField and SunRays: not used. Depth of field blurs the road ahead, which is wrong for a racer. Sun rays do
  nothing at night.
- SpotLight and PointLight: colour and brightness changes only, no new instances, `Shadows` stays false. The
  SpotLight budget (nearest 60 within 350/550 studs, `docs/PERFORMANCE_BUDGET.md`) is unchanged.

## Risks and unknowns
- **Not seen.** Every value is a first guess, and the sky especially. If MidnightClear's sky is near black, raise
  `NightSky` or try Dawn (brighter Decay). If it is still violet, lower the skyAtmo Color.
- **Bloom threshold 1.45 might be too high for Neon** on some quality levels, and the signs would then look flat.
  Bloom is a quick knob in the preset table (Daylight keeps 1.35 for comparison).
- **Non-Neon lit panes depend on the ambient.** A SmoothPlastic / Glass pane is lit by the scene, so in a darker
  preset or with a negative NightExposure it dims with everything else (that is the point: it is not a light
  source). `colorMul` in NightStyles is the knob.
- **Asphalt texture.** RoadLook "dry" uses the built-in Asphalt material. On low graphics quality Roblox may draw
  a plainer material. Asphalt at 62,63,68 may read lighter or darker than expected; `off` restores the old look.
- **Neon hue rule.** A sign whose builder colour sits near a hue boundary might be snapped to cyan or magenta
  unexpectedly. Legacy shows the original colours.
- **Car lights.** A preset change removes the car lights; they come back within 0.3 s with the new headlight
  colour. A short flicker is expected and harmless.
