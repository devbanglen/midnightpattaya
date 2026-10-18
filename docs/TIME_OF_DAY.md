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
| Ambient / OutdoorAmbient | deep violet 22,18,42 / 44,40,82 | 70,50,72 / 140,92,112 | 105,105,115 / 140,140,150 | 70,60,82 / 130,112,140 |
| Brightness | 1.2 | 1.7 | 2.6 | 1.5 |
| EnvironmentDiffuse / Specular | 0.25 / 0.8 (wet-road shine) | 0.6 / 0.9 | 1 / 1 | 0.6 / 0.9 |
| Atmosphere density, haze, colour | 0.33, 1.6, violet | 0.36, 2, coral | 0.28, 1, sea-blue | 0.38, 2.2, peach |
| Bloom intensity / size / threshold | 1.1 / 28 / 0.9 (neon glows) | 0.9 / 24 / 0.95 | 0.5 / 24 / 1.4 | 0.8 / 24 / 1.1 |
| ColorCorrection contrast / saturation / tint | 0.12 / 0.18 / lilac | 0.08 / 0.2 / rose | 0.03 / 0.08 / white | 0.05 / 0.1 / warm |

The first night preset pulled OutdoorAmbient down to deep violet so the neon and lit windows stood out, but the owner
could not see the road at all (2026-10-18). The preset was lifted (ambient, exposure, less fog) and the owner then tuned
the live knob `Lighting` attribute `NightExposure` to **+0.4** by eye (2026-10-19). That value is baked in:
ExposureCompensation 0.95 at night. `NightExposure` still works for further tuning (added to the exposure, scaled by
how "night" the blend is), default 0.

**Open (owner, 2026-10-19):** the exposure brightens the road and the headlight area, but the **sky stays almost
black** and does not change with the knob. The template `Sky` has `StarCount = 0`, and ClockTime 20.5-21 puts the sun
far below the horizon, so the skybox is unlit. Candidates for the next pass: a night preset that overrides the Sky
(stars on, a lighter indigo horizon through the Atmosphere Color/Decay), or holding the night clock nearer 19.5
("blue hour") instead of 21. The owner asked to leave it for now.

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
1. Install, then Play. `ClockTime` starts at 20.5. Expect a dark violet sky, lit windows, glowing lamps, and your car
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
