# MIDNIGHT PATTAYA UI system (ui-core, 2026-10-19)

Status: **written, not run in Studio.** Nothing in this document has been seen on screen yet; the team cannot run
Studio. Syntax of every new/changed Luau file was checked offline with `luau-compile` (luau-lang release CLI): that
proves the files parse, nothing more.

Binding rules: `docs/UI_CONTRACT.md`. Target look: `docs/images/ui_mockup_owner.png` (laid out from its pixel
positions on a 1600x900 reference). Owner acceptance conditions applied: the legacy-hide flag is the client-local
`LocalPlayer` attribute `MidnightHUD` (never `workspace`), the HUD visibility setting only changes this client's GUI.

## Files

| File | Kind | What |
|---|---|---|
| `roblox/src/ReplicatedStorage/MidnightUI/Theme.luau` | ModuleScript (leader, unchanged) | colour / font / size / radius / motion tokens |
| `roblox/src/ReplicatedStorage/MidnightUI/Bus.luau` | ModuleScript (rewritten, same API) | client event bus |
| `roblox/src/ReplicatedStorage/MidnightUI/Responsive.luau` | ModuleScript (new) | UIScale, HUD scale, input kind, safe insets, reduced motion |
| `roblox/src/ReplicatedStorage/MidnightUI/InputPrompts.luau` | ModuleScript (new) | key glyph per input + context actions per state |
| `roblox/src/ReplicatedStorage/MidnightUI/Components.luau` | ModuleScript (new) | panel, label, bar, buttons, icons, pill, toast card, toggle, slider |
| `roblox/src/StarterPlayer/StarterPlayerScripts/MidnightHUD.client.luau` | LocalScript (new) | the root HUD |
| `PattayaGarageClient.client.luau` | LocalScript (edited, additive) | Bus `garage.open`, legacy-hide of its toast |
| `PattayaJobsClient.client.luau` | LocalScript (edited, additive) | Bus `missions.open` panel, legacy-hide of its job strip / toasts |
| `tools/studio/install.ps1` | installer | also bundles `roblox/src/ReplicatedStorage/MidnightUI/*.luau` as `ReplicatedStorage/MidnightUI/<name>` |

Installer: `install.luau`'s `folder()` already creates a Folder for every extra path segment, so the keys
`ReplicatedStorage/MidnightUI/Theme` etc. become ModuleScripts in a Folder `ReplicatedStorage.MidnightUI`. The only
change needed was the extra `Entries` line in `install.ps1` (its `Get-ChildItem` is not recursive).

## Architecture

```
PlayerGui.MidnightHUD (ScreenGui, DisplayOrder Theme.layer.hud, IgnoreGuiInset false, ResetOnSpawn false,
                       ScreenInsets CoreUISafeInsets, ZIndexBehavior Sibling)
 ├ TopLeft       600x120  PlayerCard (CanvasGroup) + Money pill                     ui-core
 ├ TopCenter     560x260  (empty: wordmark/district/race strip)                       ui-race
 ├ TopRight      520x96   QuickMenu (CanvasGroup, 6 tiles)                           ui-core
 ├ BottomLeft    340x300  (empty: minimap)                                            ui-map
 ├ BottomCenter  620x100  ContextBar (6 pooled chips) + JobStrip pill                ui-core
 ├ BottomRight   440x300  (empty: speedometer)                                        ui-race
 ├ Toasts        290x260  3 pooled toast cards, bottom-up, right-aligned             ui-core
 ├ Modal         full screen dim + Card (UIScale) + Body                             ui-core (API for all)
 └ ShowHUD       52x52 settings tile, only while the HUD is hidden
```

- Every anchor is a transparent, non-Active Frame with an **offset size in design pixels** and a `UIScale`
  ("MidnightScale") inside it. Children are laid out in design pixels and scale together; the anchor's own position
  (margin 20 px) is not scaled.
- Scale = `clamp(min(w/1600, h/900), 0.5, 1.3) x HUDScale` (touch never below 0.62). 1920x1080 -> 1.2,
  1366x768 -> 0.85, 1600x900 -> 1.0.
- Positions are recomputed on every scale / input change (`layout()`): `Toasts` sits 12 px above the *scaled*
  `BottomRight`; on touch `BottomRight` and `Toasts` move 180 px left (jump button / touch zone, per the contract) and
  `BottomLeft` moves under the player card (the dynamic thumbstick owns the lower-left), anchor point (0,0).
- Event-driven: leaderstats `.Changed`, player attribute signals, `Humanoid.Seated`, the `NitroBonus` remote, Bus.
  Two slow loops only: the circuit-proximity check (2 Hz, a distance test against 1-3 points) and 1 Hz text refresh
  inside open Events / Missions windows. No RenderStepped/Heartbeat in the HUD; no GUI instance is created per
  frame (toasts and chips are pooled; a toast icon is rebuilt only when its icon kind changes).
- Motion: all tweens go through `Components.tween`, which sets the goal instantly when reduced motion is on. Nothing
  shakes or flashes; level-up is a toast, money is a 0.6 s count-up and a short green stroke on the pill.

## Bus

`Bus.on(name, fn)` returns `{Connected, Disconnect()}`; `Bus.fire(name, ...)`; `Bus.count(name)` = listeners connected.
The bus is now plain Luau lists (the module table is shared by every LocalScript on the client): arguments are passed
by reference, so tables keep identity and **functions survive** (a BindableEvent cannot carry the `build` callback of
`modal.open`). Each listener runs in its own `task.spawn` thread.

| Name | Payload | Fired by | Listened by |
|---|---|---|---|
| `garage.open` | – | quick menu Garage | PattayaGarageClient (opens the shop inside the ring, else a toast) |
| `map.toggle` | – | quick menu Map, gamepad short Select | **ui-map (must listen)** |
| `events.open` | – | quick menu Events | ui-race if they want; else MidnightHUD's built-in Events window |
| `missions.open` | – | quick menu Missions, K | PattayaJobsClient (missions window) |
| `settings.open` / `help.open` | – | quick menu, U / F1 | MidnightHUD |
| `toast` | `{title, body?, kind?, icon?, duration?, key?}` | anyone | MidnightHUD |
| `modal.open` / `modal.close` | `{title, build = function(body: Frame), width?, height?}` | anyone | MidnightHUD |
| `minimap.visible` | bool | Settings "Minimap" | **ui-map** |
| `hud.scale` | number (effective scale) | Responsive | anyone (e.g. a fallback ScreenGui) |
| `hud.reducedMotion` | bool | Responsive | anyone |

Fallbacks (quick menu): a tile whose event has no listener (`Bus.count == 0`) does not die silently: Garage/Map/
Missions show a short toast with the key to use, Events opens the built-in window (live `ReplicatedStorage.PattayaEvent`
state, 1 Hz).

Toast `kind`: `info` (cyan), `reward` (green), `warn` (red), `pb` (yellow), `levelup` (purple). `key`: a card with
the same key still on screen is updated in place (near-miss combos). Max 3 visible, queue of 8, 4 s default.
Title accepts RichText (`<font color="#3DDC84">+25</font>`).

## How other teams use it

```lua
local gui = player.PlayerGui:WaitForChild("MidnightHUD", 10)
local UI = game.ReplicatedStorage:WaitForChild("MidnightUI")
local C, Theme, Bus = require(UI.Components), require(UI.Theme), require(UI.Bus)
if gui then
	local speedo = C.panel({parent = gui.BottomRight, size = UDim2.fromScale(1, 1), glow = true})
	-- lay out in design pixels inside the anchor (440x300 here); the anchor's UIScale does the rest
end
Bus.fire("toast", {title = "PERSONAL BEST", body = "01:32.58", kind = "pb"})
Bus.fire("modal.open", {title = "CIRCUIT", build = function(body) C.label({parent = body, text = "..."}) end})
```

- Fill your anchor, or anchor your panel to the anchor's corner nearest the screen edge: ui-core moves anchor frames
  (touch layout), never resizes them.
- Free space at 1366x768 (s 0.85): between the money pill (ends x ~505) and the quick menu (starts x ~925) at the top;
  the race strip must stay below y ~60 there or within that gap. The chips row is 42 px at the bottom of BottomCenter.
- A loop started in a modal `build` should end when `body.Parent == nil` (the body is destroyed on close).
- If the HUD is missing (script order), wait with `WaitForChild("MidnightHUD", 10)`, else make your own ScreenGui.

## Components (all return the Instance; props tables; Theme only)

| Function | Notes |
|---|---|
| `panel{parent,size,position,anchor,color,alpha,radius,stroke=false,strokeColor,glow,accent,gradient=false,canvas,clip,zIndex,layoutOrder,name}` | glass Frame: UICorner, hairline UIStroke (cyan when `glow`), surface2->navy gradient, optional cyan->purple top line. `canvas=true` -> CanvasGroup with an inner `Surface` frame (a gradient/stroke on a CanvasGroup would tint/outline the whole group) |
| `panelStroke(panel)` | the panel's UIStroke (handles the canvas case) |
| `accentLine{parent,inset,thickness}` | cyan -> purple line, faded ends |
| `label{parent,text,size,position,anchor,textSize,font,color,align,vAlign,wrap,fit,minSize,autoX,rich}` | `fit` = TextScaled capped at textSize with `UITextSizeConstraint` (no overflow); otherwise truncates with "..." |
| `valueLabel{parent,value,caption,valueSize,color,captionColor,align}` | children `Value`, `Caption` |
| `bar{parent,size,value,from,to,segments,trackColor}` / `setBar(bar, v, animate)` | gradient fill, optional ticks |
| `button{parent,text,style,onClick,size,textSize}` | styles primary/secondary/danger/ghost; 44 px tall default; hover, press scale, gamepad selection ring |
| `iconButton{parent,icon,label,hint,size,onClick}` / `setBadge(b, on)` | quick-menu tile; children `Icon`,`Label`,`Hint`,`Badge` |
| `icon(name, parent, px, color)` | vector icons from Frames: garage, map, events, missions, settings, help, nitro, star, coin, warn, info, trophy |
| `pill{parent,text,lead,leadColor,textColor,color,alpha,stroke,autoX,textSize,font}` / `setPill(p, text)` | |
| `divider{parent,vertical,size,position}` | 1 px hairline |
| `toastCard{parent,title,body,kind,icon,size}` / `setToast(card,title,body,kind,icon)` | CanvasGroup card (fades as one) |
| `toggle{parent,label,value,onChange}` -> frame, set | 72x44 switch |
| `slider{parent,label,min,max,step,value,format,onChange}` -> frame, set | -/+ buttons for gamepad, click/drag track |
| `tween(obj, goal, speed, style)` | honours reduced motion |
| `corner`, `stroke`, `padding`, `gradient`, `kindColor`, `hex`, `selectionImage` | helpers |

`Responsive`: `attach(gui)`, `addScale(obj)`, `scale()`, `hudScale()`, `baseScale()`, `isTouch()`, `isGamepad()`,
`inputKind()`, `safeInsets(gui?)`, `reducedMotion()`, `onChange(fn)`. Input kind comes from
`UserInputService.PreferredInput` when the engine has it, else `GetLastInputType()`.
`InputPrompts`: `glyph(action)`, `label(action)`, `list(state)`, `KEYS` (copied from the binding scripts),
`CIRCUIT_RANGE` (900 studs).

## What the root builds (data sources)

- **Player card**: avatar (`Players:GetUserThumbnailAsync` headshot; initial letter until it loads), DisplayName,
  `LV. n` (leaderstats Level), Title (leaderstats Title; hidden when empty), EXP bar + `EXP / next` where next =
  `100 + (Level - 1) * 60`, **copied from `PattayaProgress.expToNext`** (ServerStorage cannot be required on the client).
- **Money pill** `฿ 125,800`: leaderstats Money with thousands separators, 0.6 s count-up after `ProgressLoaded`.
- **Quick menu**: Garage, Map, Events, Missions, Settings, Help. Keyboard hints M / L / K / U / F1 (Map's M is the
  minimap script's own key; K/L/U/F1 are bound by the HUD at low priority; I/O are not used because they zoom the
  Roblox camera). Badges: Events while an event gathers and you have not joined; Missions while a job runs.
  Gamepad: **hold Select 0.35 s** focuses the menu (left/right wrap, B leaves); a short Select is forwarded as
  `map.toggle` (the HUD binds Select at High priority). If nothing listens to `map.toggle`, Select is passed through
  so the old map key keeps working.
- **Toasts**: Bus `toast`; `LastReward`/`LastRewardAt` (`+1,234 ฿  +80 EXP` + reason; ignored if older than 15 s);
  Level increase -> `LEVEL UP!`; `GarageMsg`/`GarageMsgAt`; `NearMissAt` -> `NEAR MISS x3 +14` (the +n is the
  nitro actually paid on the `NitroBonus` remote within 0.5 s; no number is shown if none arrived).
- **Context chips** from `InputPrompts.list`: in a car, free roam: `G GPS | M MAP | C CHALLENGE | H STREET SPRINT`
  (+ `J JOIN` while `PattayaEvent.Phase == "gathering"` and not joined, + `P CIRCUIT` within 900 studs of a
  `Circuit_<id>` entrance); circuit: `T RESET | P CIRCUIT`; loop/street/event race: none; job: `E CANCEL JOB | M MAP`;
  on foot: `M MAP`. In-car = `HUD_InCar` (ui-race) or seated in a `RaceCar` VehicleSeat. Hidden on touch (Roblox
  draws its own action buttons there).
- **Job strip**: `HUD_JobText` / `HUD_JobUrgent` published by PattayaJobsClient while the flag is on (red when < 15 s).
- **Settings** (only options that work): HUD scale 0.70-1.40 (step 0.05), Reduced motion, Show HUD (hides every anchor
  except Toasts; a small settings tile stays top-right to undo), Minimap (shown only when something listens to
  `minimap.visible`), Reset to defaults.
- **Help**: the control table of `HOW_TO_PLAY_TH.md`, Thai + English; gamepad glyphs when a gamepad is in use.
- **Fade**: player card + quick menu fade in on spawn and out on death (instant with reduced motion).

### Settings persistence

Stored as **LocalPlayer attributes set on the client** (client-local, not replicated, survive respawn because the
HUD has `ResetOnSpawn = false` and the attributes live on the Player): `HUDScale` (number), `ReducedMotion` (bool;
nil = follow Roblox's own Reduce Motion setting), `HUDHidden` (bool), `HUDMinimap` (bool, nil = on). They are **not
saved across sessions**: that needs a server remote + PattayaProgress `SetData`, and UI teams do not touch server
scripts (see Known gaps).

### Legacy hide

`MidnightHUD.client` sets `Players.LocalPlayer:SetAttribute("MidnightHUD", true)` as its last step.
- PattayaGarageClient: while true, its centre toast label stays hidden and its messages go to Bus `toast`; GarageMsg
  is shown by the HUD. The ring prompt ("E GARAGE") and the shop window are unchanged.
- PattayaJobsClient: while true, the top job strip is hidden and published as `HUD_JobText`/`HUD_JobUrgent`; job
  messages become Bus toasts; its near-miss text is left to the HUD. Ring prompt, route line, arrow, beacon unchanged.
- Set the attribute to false (client command bar: `game.Players.LocalPlayer:SetAttribute("MidnightHUD", false)`) and
  both strips come back (attribute-changed signal both ways). The new HUD itself stays; disable it with
  `PlayerGui.MidnightHUD.Enabled = false`.

## Studio test checklist (leader)

Install: `powershell -File tools\studio\install.ps1`, then run `tools/studio/install.luau` in the command bar. Check
`ReplicatedStorage.MidnightUI` holds Theme, Bus, Responsive, InputPrompts, Components (ModuleScripts) and
`StarterPlayerScripts.MidnightHUD` exists. Play, Output open.

First look (most likely to need a fix):
1. No errors from `MidnightHUD` / `Components` in Output. `PlayerGui.MidnightHUD` has the 8 anchor frames.
2. Player card top-left: avatar, name, `LV. 1`, EXP bar `0 / 100` (Level 1 -> 100, Level 2 -> 160 ...). Set money
   from the server bar `game.Players.<you>.leaderstats.Money.Value += 12345`: the pill counts up to the new value
   with separators.
3. The CanvasGroup panels (player card, quick menu, toasts) render crisp and are not tinted dark (the canvas fix);
   text is readable at `game.Lighting:SetAttribute("TimeLock", 12)` and `21`.
4. Quick menu: each tile hovers/presses; Garage outside the ring -> Thai/English toast; inside the purple ring ->
   the shop opens; Missions -> the missions window with the stand list; Settings/Help open; Map/Events behave per
   the fallback rules above until ui-map / ui-race listen.
5. Drive: chips `G GPS | M MAP | C CHALLENGE | H STREET SPRINT` appear only in a car; on foot `M MAP`. Start a
   Street Sprint: chips disappear. Near a traffic car at speed: `NEAR MISS` card updates in place for combos.
6. Finish a sprint / job: reward toast `+n ฿  +n EXP` with the reason; enough EXP -> `LEVEL UP!`.

### Test matrix

Studio: **Test > Device** (Device emulator) for each row; the HUD re-lays out when the emulator changes the viewport.
For each, check: (a) no overlap between ui-core panels and the other teams' panels (card / pill vs TopCenter strip,
quick menu vs strip, chips vs minimap / speedometer, toasts vs speedometer), (b) every button clickable (hover
highlight shows; nothing invisible on top of it: anchors are non-Active), (c) no text overflow (long DisplayName,
`Road Fighter` title, money 9,999,999, the job strip text, the Help rows; `fit` labels shrink, never spill), (d) the
four screen corners / Roblox top-bar buttons and the camera are not covered, (e) FPS before/after.

| Resolution | Expected scale | Specific checks |
|---|---|---|
| 1920x1080 (desktop) | 1.20 | card ~456x134 px top-left, menu ~600 px wide top-right, chips centred bottom, toasts above the speedometer |
| 1366x768 (laptop) | 0.85 | top row: money pill ends ~505 px, quick menu starts ~925 px; chips row (~500 px) does not touch BottomLeft/BottomRight |
| Mobile landscape (e.g. iPhone 14 / Galaxy S-series in the emulator) | 0.62 | jump button + thumbstick uncovered; minimap anchor under the card; chips hidden; tiles >= 44 px; modal fits the height |
| Tablet (iPad landscape) | ~0.64-0.85 | as mobile; check the menu does not reach the TopCenter strip |
| Gamepad (any, plug one in or use the emulator's controller) | – | hold Select -> menu focus ring, left/right wraps, A activates, B leaves / closes a modal; tap Select -> map |

Attributes to flip on the client (command bar, client side, during Play):
`game.Players.LocalPlayer:SetAttribute("HUDScale", 0.7)` / `1.4` (all anchors scale, Toasts stay above the speedo),
`...("ReducedMotion", true)` (no fades, instant count-up), `...("HUDHidden", true)` (only toasts + the small tile),
`...("MidnightHUD", false)` (legacy job strip / garage toast return), `...("HUD_InCar", true)` (chips for car state
without a car).

FPS before/after (PerfProbe, client command bar, window focused, same spot and time of day, 10 s each):
```lua
local P = require(game.ReplicatedStorage.PattayaPerfProbe)
game.Players.LocalPlayer.PlayerGui.MidnightHUD.Enabled = false; P.run(10)   -- before
game.Players.LocalPlayer.PlayerGui.MidnightHUD.Enabled = true;  P.run(10)   -- after
```
Compare RenderStepped/Heartbeat rates and `Instances` memory; repeat once with 3 toasts on screen
(`require(game.ReplicatedStorage.MidnightUI.Bus).fire("toast", {title = "TEST", body = "x"})` x5).

## Known gaps / risks

- **Not run in Studio.** Likely first fixes: icon proportions (vector icons drawn blind), CanvasGroup text sharpness,
  exact spacing vs the mockup.
- `expToNext` is duplicated from `PattayaProgress` (server-only module). If the rule changes there, change
  `MidnightHUD.client.luau` too; moving it to ReplicatedStorage would need a server-script edit (not a UI-team task).
- Settings are session-only (client attributes). Cloud persistence needs a small server remote.
- `map.toggle` and `minimap.visible` need ui-map listeners; gamepad Select is claimed by the HUD at High priority
  when `map.toggle` has a listener. Roblox's own Select-to-navigate-GUI behaviour is not relied on.
- The legacy LastReward toast in PattayaSprintClient (ui-race) will show alongside the new reward toast until ui-race
  hides it under the flag.
- F1 as the Help shortcut: if Studio/the client swallows it, change `SHORTCUTS.help` in `MidnightHUD.client.luau`.
- The missions window lists the JobStands models streamed in on this client (far stands may be missing under
  streaming); distances are straight-line.
- No mockup crown icon, no "+" on the money pill (no shop to open), no slanted chip edges: left out rather than faked.
- `docs/UI_CONTRACT.md` still says `workspace:SetAttribute("MidnightHUD")`; the owner's acceptance condition
  (LocalPlayer attribute) supersedes it and is what the code does.

## Owner fixes (team5/ui-fix, written, not run in Studio)

- `Components.label` with `fit = true` no longer shows an ellipsis: TextScaled down to `minSize`, `TextTruncate.None`
  (pass `truncate = true` to keep "…" for free text; the toast title/body do). The quick-menu tile label uses the full
  tile width minus 6 px and `minSize = 8`, so "Missions"/"Settings" fit at 88 px across HUD scale 0.62-1.3.
- Player card: name/title were already `fit`; the level label ("LV. n", rich text) is `TextTruncate.None`.
- `Components.label` adds no text stroke (unchanged).

## Touch layout (compact; team5/ui-fix, written, not run in Studio)

**When:** `Responsive.isCompact()` = touch input **or** viewport width < 1100 px (`Responsive.COMPACT_WIDTH`).
MidnightHUD mirrors it as attribute `Compact` on its ScreenGui. MidnightActivity, MidnightSpeedo and
PattayaMinimapClient read that attribute, and so does CircuitRaceClient for the tower. Desktop (not compact) keeps
the exact v1 layout: every compact change is behind that flag. Desktop sizes are restored when the window grows back.

**Rules**
1. Nothing overlaps another HUD element or Roblox's touch controls. Roblox's own buttons (`PlayerGui.ContextActionGui`
   and `TouchGui` GuiButtons up to 200 px, i.e. the CAS buttons and the jump button) are read at runtime: once a
   second, on viewport changes and on gui AbsoluteSize changes (`placeAvoiding`). The speedometer slides left in
   8 px steps until it is 8 px clear of them. The job strip / chips get the widest centred width that stays 8 px
   clear in their rows. The thumbstick visual (bottom-left, bottom ~100 px) is kept clear by the layout itself
   (nothing is placed there).
2. Margin 12 screen px. Anchor sizes are design px x the HUD scale (`Responsive.scale()`, 0.62 on a phone).
3. Player card 300 x 100: avatar, name (shrinks down to 8 px, never "..."), `LV. n` + the money (green, inside the
   card, shrink-to-fit, the separate money pill is hidden), EXP bar. Title line and EXP numbers are hidden.
4. Quick menu: one 72 x 72 menu button (>= 44 px on screen, red dot = any tile badge). It opens the 6 tiles
   (88 x 84 each, >= 44 px) as a sheet left of the button. While the sheet is open TopCenter hides. A tile tap, the
   button again, or 8 s untouched closes it. Gamepad hold-Select opens it too.
5. TopCenter 660 x 190: no wordmark. Free roam is one line (`<district>  •  FREE ROAM` / `<job> JOB`) plus the
   GPS / event pill. The racing title, strip, status, sectors and lights move up to y 0.
6. Toasts: a top-centre column under TopCenter, 260 x 136, newest below, at most 2 on screen.
7. Speedometer: the compact variant 242 x 113 (about 150 x 70) has big digits, KM/H (or LIMITED), nitro % and a
   nitro bar, with no dial. Centred, bottom edge 90 px above the screen bottom, but never closer than 8 px under the
   toast column.
8. Minimap card: 150 x 120 screen px under the player card, header 22 px. There is no compass, rose or district
   label. The OSM credit is kept (8 px). Zoom in / zoom out / expand are 36 px buttons in a column just right of the
   card.
9. Circuit timing tower: under the minimap card, scaled with the HUD, only the rows that fit above the bottom 100 px
   (at least 3).
10. Known exception: the big centre text (3-2-1-GO / VICTORY, a few seconds) sits under the strip and can cover the
    toast column while it shows.

**Expected rectangles at 830 x 439 (GuiInset 58, so the HUD gui is 830 x 381; scale 0.62), in gui px:**

| element | x, y | w x h |
|---|---|---|
| TopLeft / player card | 12, 12 | 186 x 62 |
| TopRight / menu button | 773.4, 12 | 44.6 x 44.6 |
| quick-menu sheet (open only; TopCenter hidden) | 408.8, 8.3 | 359.6 x 59.5 (tiles 54.6 x 52.1) |
| TopCenter (activity) | 210.4, 12 | 409.2 x 117.8 |
| Toasts column (2 max) | 334.4, 135.8 | 161.2 x 84.3 |
| BottomLeft anchor / minimap card | 12, 82 | 150 x 120 |
| minimap buttons (+, -, expand) | 168, 82 / 124 / 166 | 36 x 36 each |
| BottomRight / compact speedo | 339, 228 | 150 x 70 |
| BottomCenter anchor | 222.8, 326.8 | 384.4 x 42.2 (job strip at its bottom, 21 px tall, <= 384 wide) |
| circuit timing tower (session) | 12, 210 | 186 x 60.8 (5 rows) |

## Owner review round 2 — results (leader, 2026-10-19, Studio)
Build: main after team5/ui-fix (df46ff5 + 433b7ce) + leader fixes (TopRight anchor 584 px; MidnightActivity re-asserts
group positions after a Compact change and on viewport changes: a startup slide tween had left the free-roam group at
the compact y on desktop, see `docs/images/hud_v3_full_regression_before_fix.jpg`).

| check | result |
|---|---|
| Full screen 2684×1219 (owner's monitor, F11) | all elements placed as the mockup; 6 quick-menu tiles complete ("Missions" not truncated); wordmark → district → mode → GPS pill order correct after the fix; `hud_v3_full_freeroam.jpg`, `hud_v2_full_looprace.jpg` |
| Bira Time Attack, full screen | minimap shows the track loop + pit lane + car dot, header "BIRA CIRCUIT (GAME VENUE) • TIME ATTACK", no legacy menu popup, timing tower under the player card; `hud_v2_full_bira.jpg` |
| Laptop preset (Studio gave 1676×987, not 1366×768) | all elements fit, nothing clipped; `hud_v2_laptop_1676x987.jpg` |
| Mobile landscape 830×439 (Device Emulator, TouchEnabled) | compact layout on: card 186×62 with money inside, minimap 150×120 + 36 px buttons, one-line activity + GPS pill, toasts under the strip, compact speedo 150×70, menu button 44.6 px; numeric overlap test between every HUD rect and the 7 ContextActionService buttons + jump button + thumbstick visual: 0 overlaps; `hud_v3_mobile_830x439.jpg` (the 3D scene did not render in that emulator capture, HUD only) |
| FPS | HUD on vs off (Studio focused, full screen): heartbeat 59.9 vs 60 Hz, render 59.9 vs 60 fps, p50 16.6 vs 16.7 ms, p99 21.7 vs 19.9 ms; later probes ran unfocused (render throttled to 15 fps both ways, heartbeat 59.8 vs 60) |
| Client errors | 0 in every session |
| Legacy rollback | `LocalPlayer.MidnightHUD = false` brings the old HUD back (not re-run this round) |

Remaining (honest list): the game's legacy ContextActionService touch buttons (GPS/NOS/MAP/DRIFT/SPRINT/RACE/CIRCUIT) crowd
and overlap each other on a small phone — they are the old mobile controls, not the new HUD; a touch-controls pass should
drop MAP/GPS/CIRCUIT from CAS when the compact HUD provides them. The 1366×768 case was measured on Studio's laptop preset
(1676×987). The compact speedo drops the class badge and car name. The 3-2-1-GO big text can cover the toast column for a
few seconds on touch. The district label falls back to "PATTAYA" outside the mapped district polygons (Sukhumvit).
