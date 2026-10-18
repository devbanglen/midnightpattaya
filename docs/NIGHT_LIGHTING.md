# Night lighting presets (VIS-3)

**Status: written, not run in Studio.** Nobody has seen these presets yet. Every value except `Legacy` is a first
guess, chosen against the owner's mock-up (`docs/images/ui_mockup_owner.png`). The leader compares the presets in
Studio and the owner picks one by eye. This page lists the presets and explains how to switch and compare them.

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
game.Lighting:SetAttribute("LightingPreset", "MidnightWet")   -- MidnightClear (default) | MidnightWet | Dawn | Daylight | Legacy
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
| Atmosphere density / haze / colour | 0.26 / 1.1 / 90,65,140 | **0.22** / 1.0 / 70,84,120 | 0.26 / 1.3 / 72,86,122 | 0.22 / 1.0 / 90,110,160 | 0.22 / 1.0 / 70,84,120 |
| Night sky (NightSky=1): Decay / Color / Haze / Offset | 70,50,150 / 200,110,210 / 2.6 / 0.32 | **34,42,118 indigo** / 96,92,150 / 1.8 / 0.22 | same, haze 2.0 | 60,78,170 / 150,120,170 / 2.0 / 0.26 | 44,56,120 / 96,92,150 / 1.8 / 0.22 |
| Stars | 3000 | 3000 | 1500 (haze) | 1500 | 2000 |
| Bloom intensity / size / threshold | 1.0 / 24 / 0.92 | **0.45 / 24 / 1.3** | 0.55 / 24 / 1.2 | 0.45 / 24 / 1.3 | 0.4 / 24 / 1.35 |
| Grade brightness / contrast / saturation / tint | 0.04 / 0.1 / 0.16 / 232,224,255 lilac | 0.02 / 0.12 / 0.12 / 240,244,255 cool neutral | 0.02 / 0.14 / 0.16 / 236,242,255 | as Clear | 0.02 / 0.08 / 0.12 / as Clear |

### Dusk, day and dawn (MidnightClear; the others differ as noted)
| | Dusk | Day | Dawn |
|---|---|---|---|
| Ambient / Outdoor | 70,58,78 / 140,104,118 | 110,112,120 / 140,142,150 | 72,70,88 / 132,122,140 |
| Brightness / Exposure | 1.7 / 0.3 | 2.6 / 0 | 1.5 / 0.2 |
| ColorShift_Top | 255,150,100 | 255,245,225 | 255,190,150 |
| Atmosphere density / haze / colour / glare | 0.3 / 1.8 / 250,150,120 / 0.4 | 0.26 / 1 / 200,218,235 / 0.2 | 0.34 / 2 / 255,196,170 / 0.3 |
| Bloom intensity / threshold | 0.5 / 1.2 | 0.35 / 1.6 | 0.45 / 1.25 |
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
- **Bloom.** Threshold 1.3 (the brief allows ≥ 1.2) means only HDR-bright pixels bloom: Neon parts, lamp heads and
  headlight flares. White markings and pale facades should not. Intensity 0.45 (≤ 0.6) leaves a halo instead of a
  smear.
- **Grade.** The lilac tint is replaced by a faint cool neutral (240,244,255). Saturation drops from 0.16 to 0.12,
  because the neon is already saturated. Contrast rises from 0.1 to 0.12 to separate road from sidewalk.
- **Fog.** Density goes from 0.26 to 0.22. That gives low fog, with the far skyline still visible as silhouettes.
- **Wet look.** MidnightWet raises EnvironmentSpecularScale to 1.0. Smooth surfaces then pick up more of the sky
  and environment. The RoadLook "wet" surface (SmoothPlastic, Reflectance 0.14) shows sharp highlights from lamp
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
- **Bloom threshold 1.3 might be too high for Neon** on some quality levels, and the signs would then look flat.
  Dawn and MidnightWet use 1.2–1.3. Bloom is a quick knob in the preset table.
- **Asphalt texture.** RoadLook "dry" uses the built-in Asphalt material. On low graphics quality Roblox may draw
  a plainer material. Asphalt at 62,63,68 may read lighter or darker than expected; `off` restores the old look.
- **Neon hue rule.** A sign whose builder colour sits near a hue boundary might be snapped to cyan or magenta
  unexpectedly. Legacy shows the original colours.
- **Car lights.** A preset change removes the car lights; they come back within 0.3 s with the new headlight
  colour. A short flicker is expected and harmless.
