# VIS-8 citywide rollout — PLAN ONLY (not approved, not started; leader, 2026-10-20)

Owner rule: VIS-8 (applying the visual slice treatment to the whole city) needs explicit owner approval. This page
is the analysis the owner asked for in priority 5; nothing here is implemented.

## What VIS-8 would cover
1. Facade kit (Part modules + merged MeshPart tiles) on every building outside the Beach Road slice: central slice
   3,018 buildings + the wide world (Naklua–Jomtien, 455 chunks). The slice today covers 507 buildings.
2. Mesh palms + impostor LOD on every palm row (Beach Road sea side today: 157).
3. Lighting presets, RoadLook and NightStyles already apply citywide (they are per-part, data driven) — no change.
4. PBR maps apply citywide through MaterialVariants (roads, sidewalks) today; SurfaceAppearance only on kit MeshParts.

## Numbers measured so far (sample block, Studio)
| Build | 14 buildings | block r160 (buildings + palms) |
|---|---|---|
| Original procedural Parts | 634 | 1,018 |
| VIS-7.1 1-bay kit MeshParts | 40 + 1,612 | 2,074 |
| mesh-opt merged tiles (1–4 bays × 1–4 floors) | 40 + 508 | 1,002 |

Exporter estimate for the 507 slice buildings with merged tiles: 21,896 instances (vs 23,786 procedural Parts), 111
distinct assets (6.2 MB glb), 40 MeshParts per building on average, 90th percentile 83, max 359. Triangles do not
change with merging (tiles are copies of kit cells): the hotel tower is 14.5k tris.

## Extrapolation to the city (rough, to be measured per district before any build)
- Central slice 3,018 buildings × ~40 MeshParts ≈ 120k MeshParts if every building got the kit — too many. VIS-8 must
  be **tiered**: kit on buildings within N studs of the main racing routes (Beach Road, Second Road, Sukhumvit,
  Walking Street approach, circuit corridor), procedural boxes with the facade variety pass elsewhere.
- Streaming keeps only nearby chunks loaded (today 22–29k parts loaded while driving), so the budget that matters is
  parts *in view*: the sample block raised parts in view 4,657 → 6,030 with the 1-bay kit; merged tiles should bring
  it back near the Part figure (to be measured: PENDING_OWNER_TEST, needs a focused Studio).
- Uploads: 111 merged assets for the slice set; a citywide set with more module/band combinations was estimated at
  250 assets / 35.8 MB (1–8 × 1–8). Keep 1–4 × 1–4.
- Memory: unique mesh data ~2 MB; textures 15–18 MiB compressed (already uploaded). Per-instance cost unmeasured.

## Preconditions (all must be true before asking for approval)
1. Owner Visual Acceptance of VIS-7.1 + 7.1b/c on the sample block (captures day/night, hero shot).
2. Focused performance run with the merged build: render FPS, 1 % low, memory, parts in view — before/after on the
   same camera, desktop and mobile emulator.
3. A district pilot (e.g. Second Road between Soi 7 and Soi 13, ~60 buildings) built with `V.Build` + `BuildMesh`,
   probed, driven, captured — then the owner decides the tier map.
4. Git checkpoint + fresh .rbxl backup before each district build; builds in batches of ≤ 8 chunks; every layer keeps
   its Remove / Restore path (`V.Remove`, `V.RemoveMesh`, `RestoreReplaced`).

## Proposed order (if approved)
1. Second Road slice (already in the slice bbox) → 2. Sukhumvit corridor frontage → 3. Walking Street / South Pattaya
   → 4. Naklua → 5. Jomtien. Each step: export (`vis_slice.py` with a district config), offline checks
   (`tools/qa/offline_checks.py`), upload only new tiles, build, probe, drive, capture, perf, owner check.

## Open decisions for the owner
- Tier map: which districts get the kit, which keep procedural boxes + variety only.
- Mobile budget: cap MeshParts in view (e.g. 4,000) and texture memory (currently ~18 MiB).
- Whether merged tiles are "good enough" visually (seams, repeated lit patterns) — see the sample block.
