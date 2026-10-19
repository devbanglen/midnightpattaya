# Secondary UI — PLAN ONLY (not approved, not started; leader, 2026-10-20)

Owner rule: no Secondary UI implementation before the Driving HUD gets visual acceptance. This is the analysis asked
for in overnight priority 5. Nothing here exists in code.

## Scope (from the PREMIUM GAME UI / UX MASTER DIRECTIVE)
Garage screen, race results, missions / jobs board, settings, help — full-screen or sheet layouts opened from the
quick menu (`Bus` events `garage.open`, `missions.open`, `settings.open`, `help.open`, and the circuit `results` /
`menu` messages that today still use the legacy CircuitHUD).

## Building blocks that already exist
- `ReplicatedStorage.MidnightUI`: Theme tokens, Bus (plain listener lists), Components (panel, label, button, bar,
  pill, divider, accentLine), Responsive (UIScale, compact flag, safe insets), InputPrompts, TouchControls.
- `MidnightHUD.Modal` anchor (full-screen, hidden) for sheets; Toasts anchor for confirmations.
- Data: `GarageRequest` RemoteFunction (cars, classes, PI from `ReplicatedStorage.CarSpecs`), `JobUpdate` /
  `RequestJob`, circuit `CircuitMsg` results payload, `Player.leaderstats`, settings attributes (HUDScale,
  reduced motion).
- Legacy screens to replace, one attribute away from rollback: `GarageUI`, `JobHUD`, `CircuitHUD` results/menu.

## Proposed screens (each one sheet in `Modal`, compact-aware)
1. **Garage**: car list (class pill, PI, top speed bar, owned/price), preview camera on the garage car, actions buy /
   select / paint. Server contract unchanged (`GarageRequest`).
2. **Results**: circuit and sprint results table (position, driver, time, best lap, sectors, penalties, rewards),
   PB highlight, "race again" / "leave" buttons; replaces the legacy `results` popup.
3. **Missions**: jobs board (taxi / delivery stands with distance and fare), event schedule (Night Run / Survival),
   Road Fight bosses with status; GPS set from the row (`gps.set`).
4. **Settings**: HUD scale, reduced motion, camera (MidnightCamera on/off, look-back key), lighting preset choice is
   owner-only (not exposed), controls glyphs; stored as LocalPlayer attributes / DataStore later.
5. **Help**: HOW_TO_PLAY_TH content as cards; input glyphs from InputPrompts.

## Acceptance conditions to carry over
Same as the HUD: mockup fidelity, per-player legacy hide, 1920×1080 / 1366×768 / mobile landscape, no overlap or
overflow, no FPS cost (sheets built once, hidden, no per-frame work), real Studio captures, Thai where the old UI had
Thai.

## Team plan (when approved)
Three disjoint teams: ui-garage (Garage + Settings; files `MidnightGarage.client.luau`, `MidnightSettings.client.luau`,
edits `PattayaGarageClient`), ui-results (Results; edits `CircuitRaceClient`, `PattayaSprintClient` hooks),
ui-missions (Missions + Help; edits `PattayaJobsClient`, `PattayaEventsClient`). Shared modules frozen; new
Components only through ui-garage with a listed API. Leader installs and tests with the test kit + emulator.
