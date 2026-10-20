# Owner mobile-test decision — offline response

> **Leader note, 2026-10-21 (file hygiene review).** This file was written by another session on 2026-10-19 at
> 97531db and committed later after a diff review. Still valid: section 1 (texture budget; `texture_budget.py` re-run
> 2026-10-21: scene 15.08 MiB, PASS) and section 3 (fresh-client phone A/B). Superseded:
> - Section 2: the leader measured these options on 2026-10-20 (docs/STREAMING_PERFORMANCE.md). Content preload is
>   on. Pre-streaming ahead with `RequestStreamAroundAsync` made teleports worse and is opt-in only.
> - Section 4: the asset-manifest FAIL was a checker gap, not a data error. Traffic-vehicle ids live in
>   `ReplicatedStorage/TrafficVehicles.luau`; `offline_checks.py` now checks them there, and all checks pass.

Response to the owner decision on the Mobile Baseline (commit `97531db`). This file is **offline analysis and
test preparation only**. Nothing here was rebuilt, published, or uploaded. No `.rbxl` was opened or written. Git
HEAD is unchanged at `97531db` on `main`.

Scope honoured:
- NOT done (awaiting owner): Pilot Second Road 60-building install, VIS-8 citywide rollout, Secondary UI, any
  Rebuild / Publish / asset upload, any new or overwritten Place.
- Done here: offline texture-budget separation (point 8), streaming-stutter analysis + mitigation options prepared
  but not applied (point 7), the fresh-client real-phone A/B procedure (point 9), an automated-QA gate (prep).

---

## 1. PBR texture budget, separated from GraphicsTexture (point 8)

**Finding: the PBR MaterialLibraryMaps are within the 18 MiB mobile budget. The 230–242 MB GraphicsTexture measured
on the client is NOT the PBR maps.**

New offline tool `tools/materials/texture_budget.py` reads `build/materials/manifest.json` and reports the
GPU-resident footprint of the 13 PBR sets, using the documented method (block-compressed, mips included; 1.0 B/px for
normal and RGBA color, 0.5 B/px for RGB color and single-channel roughness/metalness). It reproduces the
`MATERIAL_LIBRARY.md` estimate exactly and writes `build/materials/texture_budget.json`.

| Measure | Value |
|---|---|
| All 13 sets resident (compressed + mips) | **17.75 MiB** |
| Scene resident (dry XOR wet asphalt; RoadLook shows one) | **15.08 MiB** |
| Uncompressed RGBA8 + mips (hard upper bound) | 105.3 MiB |
| Upload size (42 PNGs on disk) | 14.76 MiB |
| Budget check vs 18 MiB | **PASS**, headroom 2.92 MiB (all sets) / 2.92+ (scene) |

Cross-checks against `docs/MATERIAL_LIBRARY.md` "Budget (mobile)": upload 14.76 vs 14.8 MiB, upper bound 105.3 vs
105 MiB, ground sets 2.67 vs 2.7 MiB each, DarkGlassGrid 2.67 vs 2.7, PalmFrond 1.67 vs 1.7 — all match.

**Why the on-device figure is 230–242 MB.** That total is the whole client GraphicsTexture pool: Roblox's own
UI / CoreGui / terrain / built-in material textures, plus the 3 distinct facade decal images used across 3,236
Texture objects, plus the PBR maps. The PBR share is ~15–18 MiB of it. An in-session A/B cannot show this: §7 showed
that destroying all 492 SurfaceAppearances and 8,591 MaterialVariant uses still left GraphicsTexture at 244.7 MB after
15 s, because textures stay cached for the session. So the offline estimate above is the authoritative PBR number
until the real-phone A/B (section 3) confirms it on device.

**If a cut is needed** (the audit prints these deltas): Concrete 1024²→512² saves 2.0 MiB; DarkGlassGrid 1024²→512²
saves 2.0 MiB. Either keeps the scene well under budget. These are export-time changes (`gen_pbr.py --only <set>
--size 512`) and require a re-upload, so they are held until the owner authorises.

Run it:
```
python tools/materials/texture_budget.py            # table
python tools/materials/texture_budget.py --json     # machine-readable
```
Exit code is 2 if the resident estimate exceeds the budget, so it also works as a QA gate.

---

## 2. Streaming stutter, first 10–20 s (point 7)

**Finding: the hitches are streaming-instantiation spikes on fresh entry, not a steady-state frame cost. They clear on
their own once the Atomic chunks around the player have streamed in.**

From `VISUAL_PERFORMANCE.md` §7 (Device Emulator, PC GPU, MidnightClear 21:00, everything installed):

| Scene | 1st window | after streaming settles |
|---|---|---|
| Static street cam, HUD on | p99 53.8 ms, worst 101 ms, 1% low ~19 fps (first 10 s) | p99 18.8 ms, 59.9 fps (2nd 10 s) |
| Driving 150 studs/s through the slice | p99 71.9 ms, worst 203 ms, 1% low ~14 fps (first 20 s) | p99 28.2 ms, 59.7 fps (next 20 s) |

Mechanism: on arrival/fast entry the client streams in parts + mesh assets + first-frame texture decode for new
chunks. The main-thread instantiation and first upload of each chunk land in a few frames, producing 100–200 ms
spikes. Once the target radius is populated, frame pacing returns to vsync-bound 60. One spike was large enough to
tip the test car once (up −0.33) on a first run; the repeat over the same route, already streamed, had no tilt.

### Mitigation options — PREPARED, NOT APPLIED (none changes a core game system)

All of these are loading/streaming configuration or pre-warming, outside gameplay, ranked cheapest first:

1. **Pre-stream the spawn/start area before releasing the car.** Call
   `Player:RequestStreamAroundAsync(startPosition)` during the loading screen / countdown, then unfreeze. Moves the
   first-10 s hitch into the load screen where it is invisible. No gameplay change.
2. **Preload the start-area content.** `ContentProvider:PreloadAsync` the facade decal image ids and the start-chunk
   mesh asset ids (from `build/materials/image_ids.json` and `build/vis_assets/upload_ids.json`) during the load
   screen, so first-frame texture decode does not hitch mid-drive.
3. **Lower the mobile StreamingTargetRadius burst.** The `mobile` profile already uses target radius 768
   (`PERFORMANCE_BUDGET.md`). Reducing it, or lowering per-frame stream-in, spreads instantiation over more frames and
   flattens the spike, at the cost of slightly nearer pop-in. Tunable, reversible.
4. **Pace instantiation via the existing LOD budget.** `LOD_Budget = 300 parts/Heartbeat` already paces the distance
   sweep; a similar cap on new-chunk dressing during the first seconds after entry caps the spike height.
5. **Already helping:** the mesh-opt merged tiles cut instance count (block 634→548; ~56k citywide vs the 1-bay kit),
   which lowers per-chunk instantiation cost. No further action.

Recommended first step once authorised: option 1 + 2 together (pre-stream + preload on spawn/teleport). They target the
exact window that hurts and touch only the load/spawn path.

---

## 3. Real-phone texture A/B — fresh-client procedure (point 9)

The owner required the A/B to start from a **new client**, not an in-session texture removal (which reads from cache).
Procedure, on a real phone (Roblox app, same private place):

1. **Run A — with PBR maps.** Fully close the Roblox app (clear its texture cache). Join the place fresh. Wait for the
   loading screen to finish and stand still at spawn. Open Developer Console → Memory → read **GraphicsTexture** (MB).
   Record. Drive the standard slice route once; read GraphicsTexture again at the same spot.
2. **Run B — without PBR maps.** In Studio, with the place in a throwaway test copy (do not overwrite the live place),
   remove `ReplicatedStorage.MaterialLibraryMaps` (or skip `studioCreateVariants()`) so no SurfaceAppearance /
   MaterialVariant maps exist, and save that test copy only. Fully close the app again, join fresh, repeat step 1's
   readings at the same spots.
3. **PBR share on device = GraphicsTexture(A) − GraphicsTexture(B)** at the matched spots. Compare against the 18 MiB
   budget and against the ~15–18 MiB offline estimate in section 1.

Rules: close the app fully between runs (cache clears only on a cold start); never remove textures mid-session and read
the cached number; do not publish or overwrite the live place to make the B build — use a local test copy. This stays
`PENDING_OWNER_TEST` until the owner runs it or authorises a private playtest build.

---

## 4. Automated QA (prep)

`tools/qa/offline_checks.py` gained a fifth check, `check_texture_budget()`, which runs the section-1 audit as a gate
(additive; the existing four checks are untouched). Current run (`--no-export`):

- luau-compile: 128/128 files compile.
- rollback entry points: 5 present.
- **texture budget: PASS (headroom 2.92 MiB).**
- asset manifest: **FAIL — pre-existing, not caused by this work.** `upload_ids.json` lists 6 traffic-vehicle names
  (`TRF_Car_Hatch`, `TRF_Car_Sedan`, `TRF_Pickup_Std`, `TRF_Scooter_Pair`, `TRF_Songthaew_Std`, `TRF_TukTuk_Std`) that
  are missing from `build/vis_assets/manifest.json` and `VisAssetsManifest.luau`. This is an asset-bookkeeping mismatch
  from the traffic-vehicles work; flagged for the owner, not fixed here (fixing it touches asset manifests).

---

## Files added/changed by this response (all offline, additive)
- `tools/materials/texture_budget.py` — new, offline PBR budget audit + QA gate.
- `build/materials/texture_budget.json` — new, audit output.
- `tools/qa/offline_checks.py` — added `check_texture_budget()` (existing checks unchanged).
- `docs/OWNER_MOBILE_DECISION_RESPONSE.md` — this file.

No `.rbxl`, no live place, no upload, no rebuild. Rollback: delete the four files above.
