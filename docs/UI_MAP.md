# UI map — minimap card, full map, GPS guidance (team ui-map, 2026-10-19)

Status: **written, not run in Studio.** Nothing below has been played; the leader tests with the checklist at the end.
Binding rules: `docs/UI_CONTRACT.md`. Owner reference: `docs/images/ui_mockup_owner.png` (bottom-left card).

Files (only these two scripts were edited; no server script, no other team's file):
- `roblox/src/StarterPlayer/StarterPlayerScripts/PattayaMinimapClient.client.luau` — minimap card + full map (M).
- `roblox/src/StarterPlayer/StarterPlayerScripts/PattayaGPSClient.client.luau` — world route line/arrow, distance,
  legacy GPS panel, toasts.

There is still one GPS (server `PattayaGPSServer`, remotes `GPSRequest` / `GPSUpdate`) and one map data source
(`ReplicatedStorage.PattayaWorldMap` + `PattayaCorridorMap`). Nothing new was added on the server.

## What changed

### Minimap card (bottom-left)
- Parent: `PlayerGui.MidnightHUD.BottomLeft` (waits 10 s for `MidnightHUD`, also picks it up if it appears later)
  while `Players.LocalPlayer:GetAttribute("MidnightHUD") == true`. Otherwise the card lives in the old
  `MinimapHUD` ScreenGui at the old top-left spot (16, 60).
- Size 340 × 300 px (owner mockup proportions at 1920×1080) before the root HUD `UIScale`; Theme glass panel
  (`surface`, `alpha.panel`, `radius.panel`, `line` stroke, cyan→purple accent line on top).
- Header: pin icon + **destination • distance** (`BIRA CIRCUIT  •  8.4 KM`) while a GPS route is set, otherwise
  `PATTAYA  •  <DISTRICT>` (dimmed pin). N badge top-right.
- Map: north-up as before, centred on the car (or the character). Water `navy`, land = district polygons filled with
  `surface` (horizontal spans built once), district outlines `line`, coast `cyan` (faint), Sukhumvit `textDim`,
  main roads `textMuted`, Bira corridor `textDim`, GPS route `cyan`, district names on the map, current district
  label top-left inside the map, compass "N" bottom-left, small "© OpenStreetMap contributors" credit bottom.
- Player arrow (Roblox-shipped `rbxasset://textures/ui/TopBar/arrowUp.png`, `text` colour, plus a cyan dot fallback),
  rotated to the car/character heading.
- Controls, 44 × 44 px each, right edge: `+` / `−` zoom (3 levels: 0.5×, 1×, 2× of 4 studs per px) and expand
  (opens the full map, same as M).
- Rotate-with-player was **not** added: a rotated container stops clipping in Roblox, so it is not cheap.

### Full map (M, gamepad Select, the touch MAP button, the card's expand button, Bus `map.toggle`)
- Own ScreenGui `WorldMapUI` (DisplayOrder `Theme.layer.overlay`, built once, `Enabled` while open) with a dimmed
  backdrop (click outside = close), panel with title bar (`MIDNIGHT PATTAYA`, hint line, GPS status, `VIEW` button,
  `X` close), the map, and a sidebar: info line for the tapped marker, **DESTINATIONS** (from `GPSUpdate "list"`,
  44 px buttons, the current one highlighted cyan), **CLEAR GPS**, **LEGEND**.
- Views (`VIEW` button): ALL (city + Bira corridor), CITY (city bounds), NEAR (4 studs/px, follows you).
- Tap/click: a destination button or a flag (Bira / any circuit entrance) sets the GPS; other markers show their name
  and type in the info line. Job-stand names are shown in NEAR; the rest have labels in every view.
- Credit `© OpenStreetMap contributors (ODbL)` bottom-right of the map.
- Gamepad: on open the first destination is selected (`GuiService.SelectedObject`) when the last input was a gamepad;
  `NextSelection*` links VIEW → destinations → CLEAR GPS, VIEW ↔ X. B closes (bound at high priority only while the
  map is open; it sinks B so the challenge "decline" key does not fire at the same time). Select toggles.
- All previous functions kept: M / Select / touch MAP toggle, Bira icon → `GPSRequest:FireServer("bira")`, route
  drawn on the map, districts and POIs.

### GPS world guidance (`PattayaGPSClient`)
- Route line + arrow kept, colour `Theme.color.cyan`. G cycling unchanged.
- Destination + distance now go to the minimap header through client-local LocalPlayer attributes `GPS_Label`
  (string or nil) and `GPS_Km` (number, ≤ 4 Hz, along the route, on foot too). Same formula as before
  (studs × 0.28 / 1000).
- Toasts: while the new HUD is on, route set (new destination only, not the 4-second refresh), arrived and cleared
  fire Bus `toast` `{title = "GPS", body = <label or message>, kind = "info" | "reward" | "warn"}`.

## Marker sources (no new data)

| marker | source | glyph / colour |
|---|---|---|
| taxi job stand | `PattayaWorldMap.pois` kind `taxi` (same ids as `jobs.luau` / `PattayaJobsServer`) | 🔧 yellow |
| delivery job stand | `pois` kind `delivery` | 🔧 green |
| Road Fight boss | `pois` kind `boss` | VS red |
| central loop race | `pois` kind `race` | 🏁 white |
| Bira entrance | `pois` kind `bira`, moved to `PattayaWorldMap` attribute `Circuit_bira` when CircuitServer sets it | 🏁 purple, tap = GPS `bira` |
| other circuit entrances | `ReplicatedStorage.PattayaWorldMap` attributes `Circuit_<id>` (CircuitServer), live | 🏁 purple, tap = GPS `<id>` (server answers "not on the map yet" if it has no such destination) |
| garage | `workspace.PattayaGarage.PrimaryPart` (ring, Persistent model from PattayaGarageServer) | 🚗 cyan |
| event gathering ring | `ReplicatedStorage.PattayaEvent` attributes `Phase == "gathering"` + `RingPos` (PattayaEventsServer) | pulsing yellow dot |
| other drivers | `Players` characters / their car chassis, nearest 10, refreshed every 0.5 s | purple dot |
| you | your car chassis or HumanoidRootPart | arrow |
| GPS route | `GPSUpdate "route"` polyline | cyan line |

Note: `UI_CONTRACT.md` says `workspace.PattayaWorldMap` for the `Circuit_<id>` attributes; CircuitServer actually
writes them on `ReplicatedStorage.PattayaWorldMap` (the ModuleScript), which is what the map reads.

## Bus usage (`ReplicatedStorage.MidnightUI.Bus`)
- listens `map.toggle` (no argument = toggle, `true` / `false` = open / close).
- listens `minimap.visible` (bool; `false` hides the card).
- listens `hud.scale` (re-places the card for the mobile margin), `hud.reducedMotion` (stops the event pulse).
- fires `gps.set` (id or nil, `"map"`) when a destination is picked on the map; the map still calls
  `GPSRequest:FireServer(id)` itself, exactly as before.
- `PattayaGPSClient` listens `gps.set` and forwards it to `GPSRequest` unless the second argument is `"map"`
  (so the quick menu can set the GPS through the Bus without a second request).
- `PattayaGPSClient` fires `toast` (see above).

## Legacy-hide behaviour (per player, never replicated)
Flag: `Players.LocalPlayer:GetAttribute("MidnightHUD")`, set locally by ui-core. Both scripts listen to its change.
- `true`: card in `MidnightHUD.BottomLeft`; `GPSHUD` panel, "G GPS" hint and centre toast hidden; GPS messages go
  to the Bus toast.
- `false` / nil: card back in `MinimapHUD` (top-left, as before); `GPSHUD` panel/hint/toast work as before.
- The full map (`WorldMapUI`) is the same in both modes.

## Mobile
- Touch (Responsive `isTouch()` if ui-core provides it, else TouchEnabled and no keyboard): the card is lifted
  170 screen px above the bottom edge (clear of Roblox's thumbstick zone) and shrunk by its own `UIScale` so it fits
  between that margin and 110 px reserved at the top, on top of the root HUD scale (scale 0.45–1).
- All buttons are 44 × 44 px at scale 1. On very small phones the shrink makes them smaller than 44 px on screen
  (see risks).

## Performance
- The map (land, roads, coast, corridor, labels, POIs) is built once in one `World` frame; the full map reuses the
  same frame (reparented), so there is one copy, not two.
- Per frame: one `focus()` and, only when you moved ≥ 1 screen px or turned ≥ 2°, three position writes. No
  instances are created per frame.
- Route segments are pooled (the pool grows only when a route is longer than any before). Player dots: fixed pool of
  10. Markers and line widths are resized only when the scale changes (zoom, view, open/close).
- District lookup: once per second.

## Studio test checklist (leader)
Everything is written, not run in Studio. Check the Output window for errors from both scripts first.
1. Join with the new HUD off (no `MidnightHUD`): the card appears top-left in `MinimapHUD`, styled; GPS panel shows
   on the right as before when a route is set.
2. With ui-core's HUD on (`LocalPlayer.MidnightHUD = true`): the card sits in the bottom-left anchor; set the
   attribute to false in the command bar (client) and back: the card moves to top-left and back, the `GPSHUD` panel
   appears and hides.
3. Press M: the full map opens; press M again, X, B (gamepad), or click outside: it closes. Quick-menu Map button
   (ui-core, Bus `map.toggle`) opens/closes it. The card's expand button opens it.
4. Full map: VIEW cycles ALL / CITY / NEAR; district names, legend, credit visible; markers are readable (about 20 px)
   in every view.
5. Set a destination from the list and by tapping the Bira flag: the route appears on the full map and minimap, a
   GPS toast appears (new HUD) and the world route line is cyan. CLEAR GPS clears it ("GPS off" toast).
6. Drive with GPS on: the minimap header reads e.g. `BIRA CIRCUIT  •  8.4 KM` and counts down; on arrival a toast,
   header back to `PATTAYA  •  <DISTRICT>`.
7. Zoom + / − : three levels, buttons dim at the ends; line widths and icons stay the same size on screen.
8. Markers: garage near spawn, job stands, bosses, race start; start an event (`PattayaEvents`) and see the pulsing
   dot at the gathering ring; second player shows as a purple dot.
9. Mobile emulator (landscape phone, e.g. iPhone 14): card above the thumbstick, nothing under the jump button,
   buttons tappable; full map buttons ≥ 44 px.
10. Gamepad: Select opens, the first destination is highlighted, D-pad moves through the list, A sets GPS, B closes.
11. Day/night (`TimeLock` 12 / 21): header and labels readable.
12. Performance: MicroProfiler while driving at 200 studs/s with the card open: no new GUI instances per frame,
    RenderStepped cost for the minimap well under 0.1 ms.

## Open risks
- Not run in Studio. Luau type/syntax checked by reading only (no luau-analyze on this machine).
- Emoji glyphs (🔧 🏁 🚗) and the expand glyph (⤢) depend on Roblox's font fallback; if one shows as a box, swap the
  glyph in the `KIND` table / `ctrl("⤢", 0)` for plain text.
- UIStroke thickness on markers is divided by the map scale on the assumption that UIScale scales strokes; if not,
  the full-map badge rings look thick.
- At the full-map ALL view, roads are ~0.3 px lines made 1–3 px wide by compensation; about 2,000–2,800 Frames total
  (land fill adds ~600) — check the frame count in the MicroProfiler on mobile.
- Mobile shrink can take the card down to 0.45 × (buttons ~20 px on screen) on short phones; if too small, raise the
  minimum scale or hide the zoom buttons on touch.
- `MidnightHUD.BottomLeft` size/padding is ui-core's: the card anchors to its bottom-left corner with no extra gap.
- The other-driver dots show every player within streaming range (no "challenger" filter); remove the pool if the
  owner does not want other players on the map.
- Theme module is required (`ReplicatedStorage.MidnightUI.Theme`); without it the minimap does not start (warns).

## Owner fixes (team5/ui-fix, written, not run in Studio)

- **Circuit track layer.** CircuitServer publishes, next to `Circuit_<id>`, on `ReplicatedStorage.PattayaWorldMap`:
  `CircuitPath_<id>` = closed centreline `"x,z;x,z;..."` (world studs, integers, first point = start/finish line,
  loop closed by the client) and `CircuitPit_<id>` = pit lane (open polyline, only when the circuit has one). Both are
  Douglas-Peucker decimated in XZ to <= 250 points (10 studs max deviation; the tolerance grows only if 250 is not
  reached), a few KB each. The minimap and the full map draw them in a "Track" layer (between Corridor and Route) from
  a pooled segment set: track `textDim` 4 px, pit lane `textMuted` 2 px, start/finish tick `yellow`. A missing or
  garbled attribute = no layer. The full map's ALL view now also frames the circuit venues; legend row added.
- **Header in a session.** `CircuitActive == true` -> header `"<CircuitName>  •  <mode>"` (e.g. "BIRA CIRCUIT  •
  TIME ATTACK"), yellow pin; otherwise GPS / district as before. The header shrinks (TextScaled, 10-14 px) instead of
  ending in "…".
- **Arrow in the venue.** `focus()` falls back to the seat itself when the car model has no PrimaryPart (before, that
  case put the arrow at the map origin).
- **GPS distance.** PattayaGPSClient now projects the car onto the nearest route segment and sums from there (the old
  walk counted from the route start once the car had left it, so the header distance did not count down).
