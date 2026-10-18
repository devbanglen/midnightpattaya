# Race HUD: speedometer + activity strip (ui-race, 2026-10-19)

Status: **written, not run in Studio.** All scripts compile with `luau-compile` 0.650. Nothing ran in Roblox.
Contract: docs/UI_CONTRACT.md. Look: docs/images/ui_mockup_owner.png. Sizes are given at 1920 × 1080 and HUD scale 1.
ui-core's root `MidnightHUD` UIScale does all scaling (HUD scale, touch).

Owner acceptance conditions (2026-10-19), all applied:
1. No gear or RPM is shown as engine data. The big arc is a **speed arc**: speed / the car's nitro top speed. It is
   labelled "KM/H" only. `HUD_Gear` and `HUD_RPM01` are not published.
2. The legacy-hide flag is **`Players.LocalPlayer:GetAttribute("MidnightHUD")`**. It is set locally by ui-core,
   per player, and is never replicated state. No workspace attribute is read anywhere.
3. Free roam and racing are **different layouts**. Free roam is compact: district, mode and one GPS pill. Racing is
   larger: a title plus the 4-cell POS/LAP/BEST/TIME strip. The switch fades and slides.
4. Proportions follow the mockup at 1080p:
   - gauge cluster 480 × 330 px, dial 340 px
   - strip 626 × 72 px, values 28 px, captions 16 px
   - district 22 px, mode line 15 px
   - wordmark "MIDNIGHT" 60 px over "PATTAYA" 50 px

## Files
| File | Studio location | What |
|---|---|---|
| `StarterPlayerScripts/CarController.client.luau` (edit) | LocalScript | telemetry attributes, CarHUD legacy hide |
| `StarterPlayerScripts/MidnightSpeedo.client.luau` (new) | LocalScript | bottom-right gauge in `MidnightHUD.BottomRight` |
| `StarterPlayerScripts/MidnightActivity.client.luau` (new) | LocalScript | wordmark + layouts in `MidnightHUD.TopCenter` |
| `PattayaRaceClient`, `PattayaSprintClient`, `PattayaChallengeClient`, `PattayaEventsClient`, `CircuitRaceClient` (edits) | LocalScripts | legacy hide only |

`tools/studio/install.ps1` already bundles every file in StarterPlayerScripts, so the two new scripts install as
LocalScripts.

**Root.** Both new scripts wait up to 10 s for `PlayerGui.MidnightHUD`. If it never appears, each script makes its
own ScreenGui (`MidnightSpeedoHUD` / `MidnightActivityHUD`) with its own UIScale: viewport height / 1080, × 0.8 on
touch, × `HUDScale`.

**When it shows.** The new HUD shows only while `LocalPlayer.MidnightHUD == true`, the exact mirror of the legacy
hide. One attribute switches between the old HUD and the new one.

## Telemetry (CarController → LocalPlayer attributes)
CarController publishes at most 20 Hz, and only a value that changed. Nothing here feeds back into driving, and
physics and input are unchanged.

| Attribute | Value | Source |
|---|---|---|
| `HUD_InCar` | bool | true while CarController drives a car; false on exit / death |
| `HUD_SpeedKmh` | int | `abs(forward speed)` in studs/s, shown 1:1 as km/h (the same number as the old CarHUD text) |
| `HUD_Nitro` | int 0–100 | `fuel / tune.nitroMax × 100` (the same fraction as the old bar; the muscle car's tank is 120) |
| `HUD_Boosting` | bool | `state.boosting` (nitro held + fuel + throttle + grounded) |
| `HUD_Drifting` | bool | handbrake held and `|speed| > 40` (the rule that gives the drift nitro refill) |
| `HUD_CarName` | string | `CarSpecs.Cars[CarId].name`, else the model name |
| `HUD_Class` / `HUD_PI` | string / int | the car model's `Class` / `PI` attributes (RaceCarServer) |

On exit: `HUD_InCar`, `HUD_Boosting` and `HUD_Drifting` become false, and `HUD_SpeedKmh` becomes 0.

**No derived gear/RPM.** There is no gearbox or engine model, so per the owner rule nothing gear- or RPM-like is
published or drawn.

## Speedometer (bottom right)
**Dial.** A 340 px navy circle (`alpha.panel`) with a cyan→purple inner bezel.
- **Speed arc:** 24 rotated-Frame segments, 135° → 405° (270° sweep). Lit segments = `HUD_SpeedKmh / nitroSpeed`.
  - `nitroSpeed` comes from CarSpecs with the same choice as `CarController.pickTune`: Equalised → the starter car,
    else `ForModel` with upgrades, else 215.
  - The part of the arc above `maxSpeed / nitroSpeed` is the **nitro zone**: dim purple, lit purple.
- **Digits:** the big km/h number (display font) eases between the 20 Hz samples. The text changes only when the
  rounded value does.
- **Caption and badge:** "KM/H", then the car name, "PI n", and the class badge pill at the bottom edge. Badge
  colours by class: Street cyan, Sport green, Super purple, Hyper red, Track Spec yellow (Theme tokens).

**Nitro.** A 12-segment cyan arc outside the dial's left edge, plus "72%" and "NITRO".
- While boosting, the dial ring pulses cyan: a looping tween built once. With ReducedMotion it is a static thick
  ring instead.
- Below 15 % the arc and the percent turn red.
- A "DRIFT" tag shows while drifting.

**LIMITED tag.** A red pill reading "LIMITED 150" (`SpeedCap`) or "EQUALISED" (`Equalised`).

**Performance.** All instances are built once. Repaints happen only on attribute changes or when a rounded value
changes. Nothing is allocated per frame.

## Activity strip (top centre)
The wordmark is always shown. The layout comes from server state, first match wins:

| Priority | Condition | Layout | Line 2 (title / detail) | Strip cells | Status line |
|---|---|---|---|---|---|
| 1 | `CircuitActive` | RACE | `CircuitName` / `TIME ATTACK` · `PB mm:ss.cc` | race modes: **POS** p/n (yellow) · **LAP** l/L · **BEST** · **TIME**; open modes: **LAP** OUT/n · **LAST** · **BEST** · **TIME** (red while the lap is invalid; FINISHED + time green) | WRONG WAY (red, blinking) > PIT LANE v / limit (cyan, red over the limit) > TRACK LIMITS (yellow) > PENALTY +n s (red) > state text (forming countdown, ON THE GRID, WAIT FOR LIGHTS OUT, LEADER HAS FINISHED); PEN +n s is appended to the warnings. Sector bars S1–S3 coloured by the `sector` payload (purple / green / yellow / red). Start lights: 5 dots from `lights`, cleared at `lightsOut`. |
| 2 | a `SprintUpdate "start"` is live | RACE | title from the payload: STREET SPRINT / STREET CHALLENGE / ROAD FIGHT / NIGHT RUN / DAY RUN / SURVIVAL; detail = `VS rivals • n KM`, or for Survival `ROUND r/R • n DRIVERS LEFT` (PattayaEvent) | with standings (challenge, Road Fight, events): **POS** p/n · **CP** n/N · **TIME** · **LEFT**; solo sprint: **CP** n/N · **NEXT** distance in m · **TIME** · **LEFT** (red under 10 s) | – |
| 3 | `RaceState == "racing"` (or finished < 6 s ago) | RACE | `RaceName` (CENTRAL LOOP) / `LOOP RACE • n LAPS` | **LAP** n/N · **CP** done/N · **BEST** (`RaceBest`) · **TIME** (`now − RaceStart`); after the finish: FINISH `RaceLastTime` | FINISHED |
| 4 | otherwise | FREE | district (point-in-polygon, 2 Hz; else "PATTAYA") / `OPEN WORLD • FREE ROAM` or `OPEN WORLD • TAXI JOB` | none; one pill: GPS `LABEL • n.n KM` along the route (GPSUpdate), else a gathering event `NIGHT RUN IN 1:23 • RING 450 M • J TO JOIN` / `YOU'RE IN • n DRIVERS` | – |

**BIG centre text** (under the strip, in any layout):
- 3-2-1 / **GO!** (green): from `ChallengeMsg "countdown"` (street races and events) and circuit `lightsOut`.
- Street race end: **VICTORY** (green) when the finish text contains "WIN"; **FINISHED** (yellow) + the server's
  text or time otherwise; **DNF** (red) + reason on `stop` while racing.
- Loop race: **FINISHED** + time, "NEW BEST" in yellow when `RaceLastTime == RaceBest`.
- Circuit lap: **PERSONAL BEST** (yellow) / **LAP INVALID** (red).
- Circuit results handoff: **VICTORY** / **P n** / **DNF** / **SESSION OVER** + `RESULTS • P n/N • time`, for 8 s.
  CircuitRaceClient's own full results screen still opens.

**Personal best.** The BEST cell's caption and value flash yellow and fade back over 1.6 s. This fires on a circuit
`lap` with `pb`, and on any `RaceBest` change.

**Transitions.** A layout switch fades its whole group (registered transparencies) and slides it 10–12 px, over
`Theme.motion.normal`. The BIG text pops in from 80 % size (Back easing). With `LocalPlayer.ReducedMotion` every
duration is 0. There is no screen shake.

**Update rates.** Strip values update at 20 Hz (Heartbeat accumulator); district and GPS distance at 2 Hz.
Instances are only created at load. Tweens are created only on layout switches, flashes and the BIG text.

**Data used (read-only).**
- Player attributes: `Race*`, `Circuit*`, `JobActive`, `EventJoined`, `HUD_*`, `ReducedMotion`, `MidnightHUD`.
- `ReplicatedStorage.PattayaEvent` attributes: Phase / Title / StartAt / RingPos / JoinRadius / Entrants / Round /
  Rounds / Alive.
- `workspace.PattayaWorld.Race` (checkpoint count, Laps, RaceName) and `ReplicatedStorage.PattayaWorldMap`.
- Remotes `SprintUpdate`, `ChallengeMsg`, `CircuitMsg`, `GPSUpdate`, `JobUpdate`, listened to on the client only.
  It never fires a remote.

## Legacy-hide map (`LocalPlayer.MidnightHUD == true` hides; false shows again; attribute-changed both ways)
| Script | Hidden | Kept |
|---|---|---|
| CarController (CarHUD) | speed text, nitro bar + "NOS", car name line, key hint (bottom-left, under the minimap) | gui logic, bindings, mobile buttons |
| PattayaRaceClient | the whole RaceHUD (`gui.Enabled`) | gold next-gate posts |
| PattayaSprintClient | the CP/distance/time/position line, the "H start a Street Sprint" hint | centre toast (rewards, RaceMessage, start/finish text), gates, GPS arrow, H binding |
| PattayaChallengeClient | 3-2-1-GO countdown, "C challenge" hint | invite box + Y/N, message toast, Road Fight prompt + E |
| PattayaEventsClient | the EventHUD banner (`gui.Enabled`) | beacon arrow, J binding |
| CircuitRaceClient | top-left HUD panel (lap/times/pos/sectors), start lights, warning line, state line, lap/GO flash | timing tower, toasts, results screen, spectator bar, menu, all bindings |

The hidden pieces are moved into a full-screen transparent `LegacyHidden` frame, which is toggled, or the whole
`gui.Enabled` is toggled. The scripts' own `Visible` logic is untouched.

## Studio test checklist (leader)
Setup:
1. Install with `tools/studio/install.ps1`, then Play.
2. Client: `local TK = require(game.ReplicatedStorage.PattayaTestKit) TK.hookRemotes()`.
3. Server: `S = require(game.ServerStorage.PattayaTestKitServer).start()`.
4. If ui-core is not installed, set the flag on the client by hand:
   `game.Players.LocalPlayer:SetAttribute("MidnightHUD", true)`.

1. **Flag both ways.**
   - Set `MidnightHUD` true: the new HUD shows, and CarHUD speed/nitro, RaceHUD, SprintHUD line, EventHUD banner and
     the circuit panel are gone.
   - Set false: the old HUD is back and the new one is hidden.
   - Check `workspace:GetAttribute("MidnightHUD")` is never read: search the scripts.
2. **Telemetry.**
   - `print(S.seat(S.player()))`, then drive. Compare `LocalPlayer:GetAttribute("HUD_SpeedKmh")` with the `v=` in
     `print(TK.report())`. They must match within ±1, and the dial digits must show the same number.
   - Hold Shift: `HUD_Boosting` turns true, the ring pulses cyan, and the nitro % falls at about 28 %/s.
   - Compare the % with the old bar: toggle the flag off and on, and the fraction must match.
   - Below 15 % the arc turns red.
   - Check that `HUD_Gear` / `HUD_RPM01` are nil.
3. **Speed arc.** In the hatch (160 / 215) at a steady 160 the arc is ~74 % lit (18 of 24, all cyan). With nitro at
   215 it is full, and the last 6 segments are purple.
   - `S.setAttribute(plr, "SpeedCap", 150)`: the LIMITED 150 tag appears.
   - `S.setAttribute(plr, "Equalised", true)`: EQUALISED.
4. **Day / night.** `S.setTime(12)` and `S.setTime(21)`: the digits, captions and strip must be readable on both.
5. **Free roam.**
   - The district changes when you cross from Central to South: `TK.teleport` to a South Pattaya point, then wait
     0.5 s.
   - Press G (GPS): the pill shows `LABEL • n.n KM`. The km must fall as you drive (GPS drive:
     `TK.followRoute("GPSUpdate", {speed = 140, trigger = function() TK.fire("GPSRequest", "<id>") end})`).
   - On "arrived" the pill goes away.
6. **Loop.** Run `TK.lapCircuit("RacePath", 2, {physics = false, speed = 140})`.
   - The layout slides to RACE: CENTRAL LOOP, `LAP 1/2`, CP counts up, `TIME` ≈ `now − RaceStart`.
   - At the end: FINISHED + ~94.6 s. A first run sets BEST, so the BEST cell flashes yellow.
   - Six seconds later it is back to FREE.
7. **Street Sprint.** Run `TK.followRoute("SprintUpdate", {speed = 140, trigger = function() TK.fire("RequestSprint") end})`.
   - STREET SPRINT, CP n/N matches `rec:last("SprintUpdate","next")`, NEXT metres fall, LEFT counts down from the
     time limit.
   - Finish: FINISHED + time.
8. **Challenge / Road Fight.** Run `TK.followRoute("SprintUpdate", {speed = 150, trigger = function() TK.fire("ChallengeRequest") end})`.
   - Big 3-2-1-GO!, then POS p/n matching the last `ChallengeMsg standings` place, and VICTORY on a win.
   - At speed 70: FINISHED "2nd place".
   - Road Fight shows the title ROAD FIGHT and VS <boss>.
9. **Events.**
   - `S.startEvent("nightrun", 20)`: the free pill shows `NIGHT RUN IN 0:20 • RING n M`, plus `• J TO JOIN`
     within 1,500 studs.
   - After `TK.fire("EventJoin")`: `YOU'RE IN • n DRIVERS`.
   - Survival: the detail line shows `ROUND r/R • n DRIVERS LEFT`, and the LIMITED tag is on.
10. **Circuit.** Run `S.publishCircuit("test_oval")`, travel, join TimeAttack, then
    `TK.lapCircuit("TK_Circuit_test_oval", 3, {speed = 95})`.
    - TEST OVAL / TIME ATTACK, LAP OUT → 1..3, LAST and BEST match `CircuitLastLap` / `CircuitBestLap`.
    - Sector bars colour per the `sector` events in `TK.recorder:dump(10, ...)`.
    - A PB lap flashes BEST yellow and shows PERSONAL BEST.
    - The circuit rules test (wrong way, track limits, pit): WRONG WAY blinks red, TRACK LIMITS shows yellow,
      PIT LANE shows v / limit.
    - A circuit race (2 clients): the forming countdown, ON THE GRID, 5 lights, GO!, POS p/n = `CircuitPos`, and
      the results handoff, while the full results screen still opens.
11. **Mobile emulator (Studio device):** the gauge shrinks through the root UIScale and does not cover the jump
    button.
12. **ReducedMotion.** `LocalPlayer:SetAttribute("ReducedMotion", true)`: layout switches are instant and there is
    no pulse.

## Open risks
- Nothing has run in Studio. Text sizes and arc geometry may need nudging after the first screenshot.
- The CarHUD key hint (WASD / Shift / Ctrl / R / Space) is hidden. ui-core's InputPrompts should show Shift / Ctrl /
  R / Space, or the hint comes back.
- The RaceHUD idle line "Drive through the white gate to start" no longer shows. The gold/white gate posts still
  mark the start.
- Sprint toasts (rewards, finish text) stay centre-screen. ui-core's toasts may show the same reward a second time.
- The circuit timing tower: see "Owner fixes" below (moved under the player card while MidnightHUD is on).
- GPS distance uses its own nearest-point walk along the route (window of 60 points from the last match). A long
  teleport mid-route could leave it behind until the next route update.

## Owner fixes (team5/ui-fix, written, not run in Studio)

- **Text stroke.** MidnightActivity `text()`: text under 16 px gets no outline (mode subtitle "OPEN WORLD • FREE ROAM",
  "LOOP RACE • 2 LAPS", "TIME ATTACK", sector labels); the wordmark's UIStroke is 1 px at 0.4 transparency.
- **Circuit menu.** CircuitRaceClient shows the "MIDNIGHT PATTAYA CIRCUITS" menu only when asked: P / the CIRCUIT
  button, the paddock ProximityPrompt (seen client-side through ProximityPromptService.PromptTriggered on a
  `Paddock_*` model) or Bus `circuit.open`; the answer must arrive within 5 s. Any other `menu` payload (join through
  the remote / test kit, the refresh after join/leave/invite) only re-renders it. Side effect: after pressing a join
  button the menu stays closed (before, the server's refresh re-opened it).
- **Timing tower.** While `MidnightHUD == true` it sits 8 px under the `TopLeft` anchor (player card), or under
  `TopRight` (quick menu) on touch, scaled by that anchor's UIScale, in Theme surface/line/text and the mono font.
  Logic and the results screen unchanged; `MidnightHUD == false` restores the old place (16, 268) and look.
- PattayaGPSClient's own remaining distance (minimap header) now projects onto the nearest route segment; the
  activity strip's walk above is unchanged.
