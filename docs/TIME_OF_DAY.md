# Time of day and night identity

Midnight Pattaya is a night game first ("Drive the City. Own the Night."), but daytime is still supported. The
clock decides what the city looks like and whether the scheduled race is a Night Run or a Day Run.

**Status: built in code, not playtested.** Nothing here has been run in Studio yet.

## Scripts
| Script | Side | Job |
|---|---|---|
| `ServerScriptService.PattayaTimeServer` | server | runs the clock, writes `Lighting.ClockTime` (replicates to all clients) |
| `StarterPlayerScripts.PattayaNightLights` | client | lighting presets, night facades and lamps, floodlights, car lights |
| `ServerScriptService.PattayaEventsServer` | server | names the event NIGHT RUN or DAY RUN from `ClockTime` |

## The cycle (`PattayaTimeServer`)
- **Speed:** **24 real minutes per game day** by default, which is one game hour per real minute.
- **Start:** a new server opens at **20:30**, just after dusk, so the first thing players see is the night city.
- **Updates:** the clock advances every frame on the server, and `ClockTime` is written every 0.5 s (half a game
  minute at the default speed). That is one replicated property, so the network cost is negligible.
- **Settings:** these are attributes on `Lighting`, and they can be changed live from the Server command bar.

| Attribute | Default | Meaning |
|---|---|---|
| `DayMinutes` | 24 | real minutes per game day |
| `TimeLock` | (none) | a number such as `21` holds the clock at that time; remove it (`nil`) to run again |
| `TimeCycle` | (none) | `false` = the script stops touching `ClockTime` |
| `TemplateClockTime` | set once | the place's original `ClockTime`, kept so it can be restored |
| `PattayaLighting` | (none) | `false` = clients restore the template Lighting values (see below) |
| `NightExposure` | 0 | client knob: added to ExposureCompensation at night (e.g. `0.3` brighter, `-0.3` darker) |
| `NightSky` | 1 | client knob: how much of the night sky look is used, `0` (off) to `1` (full) |

Examples: `game.Lighting:SetAttribute("TimeLock", 21)` gives permanent night for tests.
`game.Lighting:SetAttribute("DayMinutes", 4)` gives a fast cycle for checking the presets.

**Night** means `ClockTime < 6.3 or > 17.8`, the same test in every script. It drives:
- lit windows
- lamps and floodlights
- car lights
- the Night Run name

## Lighting presets (client, `PattayaNightLights`)
There are four presets, blended linearly between keyframes by `ClockTime`:

| Time | 0:00–4:48 | 6:12 | 8:00–16:30 | 18:18 | 19:36–24:00 |
|---|---|---|---|---|---|
| Preset | night | dawn | day | dusk | night |

Between keyframes the values blend. For example, 5:30 is halfway between night and dawn.

| | Night (signature) | Dusk | Day | Dawn |
|---|---|---|---|---|
| Ambient / OutdoorAmbient | violet 74,70,104 / 118,112,160 | 70,50,72 / 140,92,112 | 105,105,115 / 140,140,150 | 70,60,82 / 130,112,140 |
| Brightness / ExposureCompensation | 1.7 / 0.95 | 1.7 / 0 | 2.6 / 0 | 1.5 / 0 |
| EnvironmentDiffuse / Specular | 0.45 / 0.8 (wet-road shine) | 0.6 / 0.9 | 1 / 1 | 0.6 / 0.9 |
| Atmosphere density, haze, colour | 0.26, 1.1, violet (night sky: see below) | 0.36, 2, coral | 0.28, 1, sea-blue | 0.38, 2.2, peach |
| Bloom intensity / size / threshold | 1.0 / 24 / 0.92 (neon glows) | 0.9 / 24 / 0.95 | 0.5 / 24 / 1.4 | 0.8 / 24 / 1.1 |
| ColorCorrection contrast / saturation / tint | 0.1 / 0.16 / lilac | 0.08 / 0.2 / rose | 0.03 / 0.08 / white | 0.05 / 0.1 / warm |

The first night preset pulled OutdoorAmbient down to deep violet so the neon and lit windows stood out, but the owner
could not see the road at all (2026-10-18). The preset was lifted (ambient, exposure, less fog) and the owner then tuned
the live knob `Lighting` attribute `NightExposure` to **+0.4** by eye (2026-10-19). That value is baked in:
ExposureCompensation 0.95 at night. `NightExposure` still works for further tuning (added to the exposure, scaled by
how "night" the blend is), default 0.

**Owner report (2026-10-19):** the exposure brightens the road and the headlight area, but the **sky stays almost
black** and does not change with the knob. The template `Sky` has `StarCount = 0`, and ClockTime 20.5-21 puts the sun
far below the horizon, so the skybox is unlit. Exposure scales what is on screen, so a black sky stays black.

### Night sky (2026-10-19, team4/night-ui): written, not seen
**Seen once (leader, 2026-10-19):** `docs/images/night_sky_v1_corridor.jpg`, Play at ClockTime 21 on the corridor
with `NightSky = 1` (default) and the baked exposure 0.95. The sky is a flat bright violet/magenta from horizon to
zenith: no longer black, the road and HUD read clearly, but stars are not visible against it in the capture and it may
be too bright/flat for a "midnight" look. The owner should try `NightSky = 0.5` and `0.3` and pick a default.

**Status before that look: written, not seen.** Nobody had looked at this in Studio when it was written. The values are a first guess, and the owner
tunes them by eye with the `NightSky` knob.

Goal: a "neon coastal city at night" sky. Deep indigo/violet overhead instead of black, a lighter pink-violet glow
along the horizon (city light haze), and visible stars.

What changed (client only, `PattayaNightLights` section 1, inside the night preset):
- **Stars:** `Sky.StarCount` goes from the template value (0) to **3000** at night. It blends in across dusk and out
  across dawn. The skybox textures, the sun and the moon are not touched. If the place has no `Sky`, none is created,
  because a new Sky would bring in Roblox's default skybox.
- **Atmosphere sky values** at full night replace the night preset's own Atmosphere values. Density stays 0.26, so
  the road fog does not change.

| Atmosphere | Night preset (`NightSky = 0`) | Night sky (`NightSky = 1`) | Why |
|---|---|---|---|
| Decay | 40,25,70 | **70,50,150** indigo | the sky hue away from the sun, which is the whole sky at night |
| Color | 90,65,140 | **200,110,210** pink-violet | the hue of the haze, so the horizon band reads as city light |
| Haze | 1.1 | **2.6** | the band of haze above the horizon |
| Offset | 0.12 | **0.32** | lets the haze cover the far skyline, so it glows instead of cutting black against the sky |
| Glare, Density | 0, 0.26 | unchanged | no sun glow at night; the road stays as visible as before |

- **Knob `NightSky`** (Lighting attribute, 0 to 1, default 1). It blends between the plain night preset (0) and the
  night sky above (1). 0.5 is halfway. Like `NightExposure`, it is scaled by how "night" the preset blend is, so it
  fades in and out with dusk and dawn. `NightExposure` works as before.
- **Template safety:** the same as the rest of the presets. The Sky's original `StarCount` is saved the first time
  the script sees the Sky, and `PattayaLighting = false` puts it back, along with the Atmosphere values.

Why this approach:
- The Atmosphere and the Sky are the only things the client can change that are drawn on the sky itself. Ambient,
  OutdoorAmbient and ColorShift_Bottom only light surfaces. A brighter ColorCorrection would wash out the whole
  screen, not just the sky.
- A new skybox would need an asset id we cannot check, so that was ruled out.
- **"Blue hour" clock: considered, not built.** The server would show a ClockTime of about 19.5 all night while
  keeping its own game time. It was not built for two reasons:
  - The sun has to get from the west at dusk to the east at dawn, so the shown clock would have to jump at some point
    in the night, and the moon and stars would jump with it.
  - Every script that reads `ClockTime` would read the shown time, not the game time.
  If the Atmosphere values are not enough, the owner can preview the blue-hour look with `TimeLock = 19.6` (test
  step 4). 19.6 is still night (`> 17.8`), and the night preset is fully on from 19.6.

Not known until it is seen in Studio:
- How much the Atmosphere colours show when the sun is this far below the horizon. If the sky is still close to
  black at `NightSky = 1`, the next things to try are a brighter Decay, a higher Haze, or the blue-hour clock.
- Whether the custom skybox (`SkyboxUp = rbxassetid://17181714834`) is itself a dark texture that hides the stars.

Owner test (Studio Play, Server command bar; the attributes replicate, so each client picks them up):
1. `game.Lighting:SetAttribute("TimeLock", 21)`. Look up at the sky. Expect indigo, not black, with stars and a
   pink-violet glow low on the horizon.
2. Compare the strength:
   - `game.Lighting:SetAttribute("NightSky", 0)` gives the old night sky.
   - `game.Lighting:SetAttribute("NightSky", 0.5)` gives halfway.
   - `game.Lighting:SetAttribute("NightSky", 1)` gives the full effect.
   Pick the value that looks right, and it gets baked in like `NightExposure` was.
3. `game.Lighting:SetAttribute("NightExposure", 0.2)` still makes the ground brighter, as before.
4. Blue-hour preview: `game.Lighting:SetAttribute("TimeLock", 19.6)`, then back to `21`. If 19.6 looks much better,
   say so, and the blue-hour clock can be built in the next pass.
5. `game.Lighting:SetAttribute("PattayaLighting", false)`. The stars go back to the template's 0 and the Atmosphere
   gets its template values. `game.Lighting:SetAttribute("PattayaLighting", nil)` brings the presets back.
6. `game.Lighting:SetAttribute("TimeLock", nil)`. The clock runs again, and the stars fade out across dawn.

**Template safety:**
- All of this runs on the client, so the place's saved Lighting is never changed.
- **Existing effects are reused.** If the template already has an `Atmosphere`, `BloomEffect` or
  `ColorCorrectionEffect`, that effect is adjusted. Two blooms or two atmospheres would stack badly.
- **Missing effects are created** under clear names: `PattayaAtmosphere`, `PattayaBloom` and `PattayaGrade`.
- **The original values are saved** when the script starts. Setting `Lighting.PattayaLighting = false` puts them
  back: our own effects are removed and the template's effects get their old values.
- The server only writes `ClockTime`. Its start value is saved in `TemplateClockTime`.

## Night world (client, `PattayaNightLights`)
- **Facades and street lamps:** unchanged from Phase 7.
  - Facades switch to the 4×4 night tile.
  - `Lamp` parts turn Neon and their SpotLight turns on.
  - This is applied when the night state changes and to parts that stream in later.
- **Floodlight hook (Bira circuit):** any **BasePart with attribute `FloodLight = true`**, anywhere in `workspace`,
  gets all of its **SpotLight children** enabled at night and disabled by day.
  - The script handles streaming. `workspace.DescendantAdded` catches parts and SpotLights that arrive later,
    including a SpotLight that arrives after its pole.
  - There is a one-off scan at start, done in chunks of 5,000 instances.
  - **Limit:** the attribute must already be set when the part arrives. Setting it later at runtime isn't picked up.
    Ship it on the pole.
- **Car lights hook:** every 0.3 s at night, the script lights up to **8 cars**: your own car and the nearest other
  cars within 350 studs of the camera.
  - It covers `RaceCar` models (players' cars) and `RivalBot` models (AI racers, bosses).
  - **Headlights:** a SpotLight beam on an Attachment at the front of the `PrimaryPart` (chassis), tilted 8° down.
    Range 70 for your car and 45 for others, angle 65, no shadows.
  - **Tail light:** a red PointLight at the back (range 10).
  - **Lamp flares:** four small always-facing glow sprites (BillboardGui) at the lamp corners.
  - **Local only:** the lights are Attachments created by the client. The car models on the server are not changed,
    and `CarController` ignores them because it only looks up `Chassis`, `Mount_*` and `Wheel_*`.
  - **Clean-up:** lights are removed when a car leaves the range, when the car is destroyed, or at dawn.
  - **Traffic cars** (`PattayaTraffic`) already have their own neon head and tail parts and get no extra lights.

## Performance notes
- **Light counts:** at night the worst case adds 16 dynamic lights for cars (8 SpotLights + 8 PointLights). The lamp and
  floodlight SpotLights are on top of that, capped by the SpotLight budget (nearest 60 within 350 / 550 studs,
  `docs/PERFORMANCE_BUDGET.md`). None of them cast shadows.
- **Updates:** presets are written 4 times a second, not every frame, and only a handful of properties change.
  Floodlights are only touched when the night state changes.
- **Post-processing:** Bloom size 28 and the Atmosphere are cheap on desktop. On low-end mobile, Roblox scales
  graphics quality down automatically.
- **Still to measure:** FPS during a full Night Run with 16 cars and their lights. Compare it with the Phase 8
  numbers in `docs/PERFORMANCE_BUDGET.md`.
- **Mobile:** `MAX_LIT_CARS` and `CAR_LIGHT_RANGE` at the top of the car-lights section are the knobs if mobile is
  too slow.

## Test plan (Studio Play)
1. Install, then Play. `ClockTime` starts at 20.5. Expect an indigo sky with stars and a glow on the horizon, lit windows, glowing lamps, and your car
   with headlights on the road ahead and a red glow behind.
2. Run `game.Lighting:SetAttribute("DayMinutes", 2)` (Server). Watch a full day in 2 minutes:
   - dawn turns peach
   - the day is clear and blue
   - dusk turns coral
   - night returns
   - lamps and car lights switch at about 06:18 and 17:48
3. Run `TimeLock = 12`. The clock stops at noon and the car lights are gone.
4. Run `PattayaLighting = false`. The template look comes back. Set it to `true`, or remove it, to bring the presets
   back.
5. Place a Part with attribute `FloodLight = true` and a disabled SpotLight child. It lights at night and goes dark by
   day, including when it streams in later.
6. Start a Night Run (`docs/RACING_ROUTE_DESIGN.md` §9). The AI racers' cars show headlights and tail glows near you.
7. Watch FPS (Shift+F5) at night in a 16-car grid.
