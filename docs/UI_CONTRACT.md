# UI contract — MIDNIGHT PATTAYA premium HUD (leader, 2026-10-19)

Shared rules for the three UI teams (ui-core, ui-race, ui-map) so their work fits together without touching each
other's files. Source: the owner's "PREMIUM GAME UI / UX MASTER DIRECTIVE" and the mockup `docs/images/ui_mockup_owner.png`
(top-left player card, top-centre wordmark + district + race strip POS/LAP/BEST/TIME, top-right quick menu,
bottom-left minimap with destination header, bottom-centre key prompts, bottom-right speedometer with nitro/gear/class,
right-side toasts).

## Shared modules (ReplicatedStorage.MidnightUI; Theme and Bus exist, the rest is ui-core's)
- `Theme` — design tokens (colours, fonts, sizes, radii, motion). Nothing hard-codes a colour.
- `Bus` — client event bus: `Bus.on(name, fn)`, `Bus.fire(name, ...)`. Names: `map.toggle`, `garage.open`,
  `events.open`, `missions.open`, `settings.open`, `help.open`, `hud.scale` (number), `hud.reducedMotion` (bool),
  `toast` ({title, body, kind = "info"|"reward"|"warn"|"pb"}), `gps.set` (destination id or nil).
- `Components` (ui-core) — panel(props), label(props), valueLabel, bar(props), button(props), iconButton, pill,
  divider, accentLine; every component takes a `parent` and returns the Instance; uses Theme only.
- `Responsive` (ui-core) — `Responsive.attach(screenGui)` adds a UIScale driven by viewport size × the player's HUD
  scale (attribute `LocalPlayer.HUDScale`, default 1, range 0.7–1.4), exposes `Responsive.isTouch()`,
  `Responsive.isGamepad()`, `Responsive.safeInsets()`, `Responsive.reducedMotion()`; fires `hud.scale` on change.
- `InputPrompts` (ui-core) — `InputPrompts.glyph(actionKey)` returns the text for the current input type
  (keyboard "G", gamepad "Y", touch "TAP"); keys come from the existing scripts (G GPS, M map, C challenge, H sprint,
  J join event, P circuit menu, F prompt, Shift nitro, Ctrl drift, R reset, Space exit).

## Root ScreenGui (ui-core): `PlayerGui.MidnightHUD`
- `DisplayOrder = Theme.layer.hud`, `IgnoreGuiInset = false`, `ResetOnSpawn = false`.
- Anchor frames (all transparent, named exactly): `TopLeft`, `TopCenter`, `TopRight`, `BottomLeft`, `BottomCenter`,
  `BottomRight`, `Toasts` (right side, above the speedometer), `Modal` (full-screen, hidden by default).
- Other teams parent their panels into these frames: ui-race → `TopCenter` (activity strip) and `BottomRight`
  (speedometer); ui-map → `BottomLeft` (minimap). If `MidnightHUD` is not there yet (script order), wait for it with
  `PlayerGui:WaitForChild("MidnightHUD", 10)`; if it never comes, make your own ScreenGui as a fallback.
- Mobile: `BottomRight` keeps 180 px clear on the right/bottom for Roblox's touch thumbstick/jump zone; the
  speedometer shrinks (Responsive) instead of overlapping.

## Legacy HUD migration (no deletion)
- When `MidnightHUD` exists, ui-core sets `Players.LocalPlayer:SetAttribute("MidnightHUD", true)` (client-local, per player; never a workspace or replicated value, so multiplayer is unaffected). Every legacy ScreenGui
  (`CarHUD`, `RaceHUD`, `SprintHUD`, `ChallengeHUD`, `EventHUD`, `CircuitHUD`, `GPSHUD`, `MinimapHUD`, `JobHUD`,
  `GarageUI`) keeps working but hides the parts the new HUD replaces (`Visible = false`) while the attribute is true,
  and shows them again when it is false (the old HUD is one attribute away: that is the migration plan).
- Who edits which legacy script: ui-race → `CarController` (telemetry + hide the CarHUD nitro bar/speed),
  `PattayaRaceClient`, `PattayaSprintClient`, `PattayaChallengeClient`, `PattayaEventsClient`, `CircuitRaceClient`;
  ui-map → `PattayaMinimapClient`, `PattayaGPSClient`; ui-core → `PattayaGarageClient`, `PattayaJobsClient` (Bus hooks
  for the quick menu: `garage.open`, `missions.open`). Nobody else touches a legacy client script; server scripts
  are not touched by any UI team (server-authoritative data stays as is).

## Data contract (read-only for the UI; all set by the server)
- Progression: `Player.leaderstats` Money / EXP / Level / Title (PattayaProgress); attributes `LastReward` (string
  "+n ฿  +n EXP  (reason)[  LEVEL UP!]") + `LastRewardAt`, `ProgressLoaded`, `GarageMsg`/`GarageMsgAt`.
- Loop race: attributes `RaceState` (idle/racing/finished), `RaceLap`, `RaceNext`, `RaceStart` (server clock),
  `RaceLastTime`, `RaceBest`, `RaceMessage`; `workspace.PattayaWorld.Race` attributes Laps/LengthStuds.
- Street Sprint / Challenge / Road Fight / events: remote `PattayaRemotes.SprintUpdate` ("start" {checkpoints, dirs,
  route, length, start, timeLimit}, "next" i, "finish" {time, length, money, exp}, "stop" reason), `ChallengeMsg`,
  `EventJoin` / attributes `EventActive`, `EventJoined`, `Equalised`, `SpeedCap`; `SprintActive`, `JobActive`,
  `RoadFight`; `NearMissCombo` / `NearMissAt`; `NitroBonus` (amount).
- Circuit: `CircuitRequest` (client→server), `CircuitMsg` ("toast", "menu" {...}, "tower" {mode, rows}, "lap"
  {lap, time, sectors, valid, pb, colour}, "results" {...}, "spectate", "invite"); attributes `CircuitActive`,
  `CircuitState` (Forming/Grid/StartLights/Racing/Results …), `CircuitName`, `CircuitLaps`, `CircuitCount`,
  `CircuitPos`, `CircuitLapStart`, `CircuitLapValid`, `CircuitPB`, `CircuitPenalty`, `CircuitWrongWay`, `CircuitPit`,
  `CircuitOff`, `CircuitFinished`, `CircuitFormEnds`.
- GPS: `GPSRequest` (id | nil), `GPSUpdate` ("route" {id, label, route, length}, "arrived" label, "clear" why, "list").
- Jobs: `RequestJob`, `CancelJob`, `JobUpdate`. Garage: `GarageRequest` RemoteFunction.
- Car (client-local, published by ui-race's CarController edit at ≤ 20 Hz as LocalPlayer attributes):
  `HUD_SpeedKmh` (studs/s shown as km/h, the existing convention: 160 studs/s = "160 km/h"), `HUD_Nitro` (0–100),
  `HUD_Boosting`, `HUD_Drifting`, `HUD_CarName`, `HUD_Class`, `HUD_PI`, `HUD_InCar`. No gear or RPM: the arcade
  car has no gearbox, and the owner forbids derived gear/RPM presented as engine data (the gauge arc is speed / top speed).
- World: `ReplicatedStorage.PattayaWorldMap` (districts/POIs/roads for the map), `PattayaCorridorMap`,
  `workspace.PattayaWorldMap` attributes `Circuit_<id>` (entrance positions).

## Rules for all three teams
- Luau + native Roblox UI only (ScreenGui/Frame/TextLabel/ImageLabel/UIGradient/UICorner/UIStroke/UIScale/
  UIAspectRatioConstraint/TweenService). No external assets or fonts; no RayCity artwork.
- Event-driven; telemetry at ≤ 20 Hz with tweened interpolation; never allocate GUI instances per frame.
- Text must stay readable by day and at night (panel alpha from Theme; test both via `TimeLock` 12 / 21).
- Thai strings where the old UI had Thai (HOW_TO_PLAY_TH.md); English elsewhere, same as now.
- Nothing is "tested" unless it ran in Studio; the teams cannot run Studio, so every report says "written, not run".
- Commit on your own branch only; no pushes; messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Owner acceptance conditions (2026-10-19)
1. `docs/images/ui_mockup_owner.png` is the visual target: proportions, colours, spacing and elements as close as possible.
2. Legacy-HUD hiding is per player (LocalPlayer attribute, client-local) and must not affect multiplayer.
3. Free Roam HUD and Racing HUD are clearly separate layouts.
4. No virtual gear/RPM presented as real engine data.
5. Tested at 1920×1080, 1366×768 and mobile landscape.
6. Checked for overlapping HUD, unclickable buttons, text overflow, UI covering the camera corners.
7. No significant FPS drop from the new UI (PerfProbe before/after).
8. When the driving HUD is done: real Studio captures by day, by night and at Bira Circuit for the owner.
No secondary UI (garage/results/missions screens) before the owner approves the driving HUD captures.
