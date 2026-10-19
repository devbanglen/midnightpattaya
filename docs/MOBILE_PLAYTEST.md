# Private mobile playtest — MIDNIGHT PATTAYA (owner decision 2026-10-20)

Scope: measure the real phone (Android / iOS) before the Second Road pilot. The emulator is not a phone (it renders
on the PC GPU) and is never used as the mobile result.

## Pre-publish checks (leader, 2026-10-20)
| Check | Result |
|---|---|
| Studio place | PlaceId 117826785726076, universe 10771583260 |
| Owner | users/11827127344 = DevSrc3rRoR (Open Cloud universe read + MarketplaceService), not a group |
| Visibility | **PRIVATE** (Open Cloud `visibility`), mobile + tablet enabled, console off |
| Git | main pushed (telemetry commit 5dc0363 and later) |
| Cloud save | last cloud update 2026-10-19T11:27Z (owner Ctrl+S); the telemetry scripts were added after it → save again |
| Local backup | Documents\zzzzzz.rbxl (16:15) |
| New place / other place | none created, none touched |

The leader does not publish through Open Cloud: that API publishes a local .rbxl file, and the only files on disk are
older than the current Studio state, so it would push a stale version. Publishing is done from the open Studio
session (same place, already linked).

## Owner steps
1. Studio: **Ctrl+S**, then **File → Publish to Roblox** (Alt+P). It publishes to the same place; the experience stays
   Private (only you can join).
2. Phone: Roblox app, logged in as DevSrc3rRoR → open https://www.roblox.com/games/117826785726076 → Play.
3. The game shows a small cyan bar at the bottom centre (owner only): phase, FPS, p99 frame time, total memory and
   GraphicsTexture in MB. Tap it to shrink / expand.
4. Test order (about 6 minutes):
   - **Cold start:** stay still for 60 s right after spawning (phase `cold`).
   - **Streaming:** open the map, set GPS to Bira, drive normally out of the centre (new areas load).
   - **150 studs/s:** on Beach Road and Second Road hold full speed + nitro for 30 s (phase `drive150`).
   - **New area:** use a teleport (garage / event / GPS destination) and stay 30 s after arriving (phase `arrive`).
   - **Sample block:** drive slowly past Beach Road Soi 7/8 (the mesh buildings and palms) and stop there 30 s.
5. Developer Console on the phone: in chat type `/console` (or Roblox menu → Settings → Developer Console) →
   **Memory** tab: note Total and GraphicsTexture; **Log → Server**: the `[PerfTelemetry]` lines are the 10 s samples.
   Screenshots of the Memory tab and the overlay are enough.

## Telemetry (works without the Developer Console)
- `StarterPlayerScripts.PattayaPerfTelemetry` (client, owner only) samples every 10 s: render FPS, p50 / p99 / worst frame
  ms, Heartbeat, memory Total / GraphicsTexture / GraphicsTextureCharacter / GraphicsMeshParts / GraphicsParts / Gui /
  Instances, speed, position, viewport, touch, whether the PBR module is present, phase.
- `ServerScriptService.PattayaPerfTelemetry` prints each sample to the server log and stores the session in DataStore
  `PerfTelemetry_v1` (key `<userId>_<time>`, index `<userId>_sessions`).
- Reading the DataStore from outside needs the Open Cloud key to have the **universe-datastores read** scope (it does not
  today: 403 "Scope not authorized"). Without it: screenshots, or Studio with API access enabled.

## Separating the new texture cost (PBR) from GraphicsTexture
GraphicsTexture is the whole client texture pool (Roblox UI, terrain, built-in materials, 3 facade images, PBR maps).
Textures stay cached inside a session, so the split needs two **fresh joins**:
1. Join A (as published): note GraphicsTexture after 60 s standing at Beach Road Soi 7/8.
2. Leader removes `ReplicatedStorage.MaterialLibraryMaps` and the Pattaya MaterialVariants / SurfaceAppearance
   templates (reversible, kept in ServerStorage), owner publishes, Join B at the same spot and time.
3. PBR cost = A − B. The offline estimate for comparison is 15–18 MiB resident (docs/MATERIAL_LIBRARY.md).

## Not approved (unchanged)
Second Road pilot install, VIS-8, Secondary UI. No physics or road change to chase FPS without evidence.
