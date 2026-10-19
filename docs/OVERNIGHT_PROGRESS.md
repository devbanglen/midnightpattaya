# OVERNIGHT PROGRESS — MIDNIGHT PATTAYA (autonomous run, started 2026-10-19 night)

Owner directive: "AUTONOMOUS OVERNIGHT DEVELOPMENT" + "AUTOMATIC LIMIT PROTECTION & RESUME" (2026-10-19). Project
Director: the leader session (Fable 5.1). Teams: Opus 5.5 agents, disjoint files, own branches, no pushes by teams.
Boundaries kept all night: no VIS-8, no Secondary UI implementation, no citywide rebuild, no publish, no .env to the
GPU box, no bulk uploads without need, rollback kept, Studio installs that need a fresh owner .rbxl are deferred.

Status words: DONE (committed), TESTED (ran offline or in Studio with evidence), UNVERIFIED (written, not run),
BLOCKED, PENDING_OWNER_TEST (needs Studio focus / emulator / clicks), WAITING_FOR_OWNER (needs a decision).

## Log (newest last)
| Time (local) | Item | Status | Evidence |
|---|---|---|---|
| 05:00–06:10 | VIS-7.1 lighting + mesh sample installed, probed, captured; weak-table bug fixed | DONE / TESTED | docs/VISUAL_ACCEPTANCE.md §5, commits f1bf51b…116682f |
| 06:20 | Focused render-FPS after the MeshPart swap (owner said "ready", viewport never reached ≥ 50 fps in 2 × 70 s polls) | PENDING_OWNER_TEST | render stayed 15–16 fps = unfocused; not counted |
| 06:25 | Thai sign close-up: Thai glyphs render in Gotham and BuilderSans identically (engine fallback) → no font change; sign board mesh front face missing (kit bug) | TESTED (Edit captures) | docs/images/vis71_thai_gotham.jpg, vis71_thai_buildersans.jpg, vis71_mesh_after_shophouse_side_day.jpg |
| 06:30 | team7/vis-kit2 started (Blender kit: sign board faces, awning shape, palm geometry; tools/blender only) | RUNNING | branch team7/vis-kit2 in D:\ROBLOXRACE-garage |

| 06:40 | Owner at Studio over remote desktop; viewport was on the **Server** DataModel (client not rendering). After the switch to Client, focus flickered: best 8-s window render rate 52.1, p50 16.7 ms, p99 67 ms (mixed focused/throttled frames), heartbeat 60, parts in view 6,033, InstanceCount 90,740, memory 6,542 MB. Not a clean focused measurement → still PENDING_OWNER_TEST (needs ~15 s uninterrupted focus on the Client view) | PENDING_OWNER_TEST | docs/VISUAL_PERFORMANCE.md §4 |
| 06:45 | team7/mesh-opt started (instance-count reduction for the kit MeshParts; owns VisMesh.py / VisMeshBuilder / new gen_merged.py) | RUNNING | branch team7/mesh-opt in D:\ROBLOXRACE-world |

| 06:55 | Regression drive after the slice rebuild: Beach Road north end → Bira, twice (201.6 s and 216.8 s at 150 studs/s): 396/396 and 425/426 probes on road; the one miss and the only tilt (up 0.88) are at a pre-existing Joint disc at world (24639, 428), outside the slice; second tilt 0.94 at (42576, 3476) corridor. No new obstacle from the mesh block or the palm colliders | TESTED | TK drive handles, tilt monitor |
| 07:00 | tools/qa/offline_checks.py: luau-compile 125/125, asset manifest consistent (43/43/43), vis_slice export deterministic, footprint checks all 0, rollback entry points present | DONE / TESTED | commit b4d12cf |
| 07:05 | team7/vis-kit2 merged (closed sign boards + awnings robust to reversed winding, coconut palms 2.3–2.7k tris, QA view sheets); 8 fixed .glb re-uploaded via Open Cloud → new ids in VisAssetsManifest (reason: Studio showed sign fronts missing; palms low-poly) | DONE (upload TESTED by operation ids) | commits 2f126b5, 96b9a29; build/vis_assets/qa/*_views.jpg |

| 07:30 | Root cause of the see-through sign boards found in Studio: Roblox's glTF import bakes a 180-deg yaw into every mesh (RSD_Palm_A_Bark centre +0.969 x in the file loads at -0.97 x; MeshPart rotation reads 0). VisMeshBuilder now places kit parts with IMPORT_YAW (CFrame.Angles(0, pi, 0)) and puts sign labels on the Back face; it also requires a fresh VisAssetsManifest clone in Edit mode (stale ids made the new palms "unusable") | DONE / TESTED (ProbeMesh) | commits 8c4667c, 1e445cf |
| 07:35 | Sample block rebuilt with the 8 fixed assets: 14 buildings 40 Parts + 1,612 MeshParts, 157 geometry palms (0 unusable), ProbeMesh all 0 | TESTED (probes) / captures PENDING_OWNER_TEST (Studio not in front) | docs/VISUAL_ACCEPTANCE.md §5 |

| 07:50 | World map: compact HUD opens on CITY (verified in the emulator: "VIEW: CITY" after M); the VIEW button tap via the MCP mouse tool did not register (button sits in the top-inset band at y -16 inset-space) — real-finger tap untested | DONE (default) / PENDING_OWNER_TEST (tap) | commit 6182364 |
| 08:00 | **SAFE PAUSE: usage limit reached.** Teams mesh-opt and textures still running on their branches; everything validated is committed and pushed on main | WAITING_FOR_MANUAL_RESUME | docs/state/OVERNIGHT_PAUSE.md |

| 09:10 | Resumed after the usage-limit pause. team7/mesh-opt merged (wide / floor-band merged tiles 1–4 bays × 1–4 floors, 3 tiers in VisMeshBuilder, palm impostor trunk = collider); 36 merged tiles uploaded (79 ids in VisAssetsManifest); Studio: 14 buildings **40 Parts + 508 MeshParts** (was 40 + 1,612), block r160 total **1,002** (was 2,074; original Parts 1,018), ProbeMesh all 0, 157 palms, 0 unusable; A/B still available with BuildMesh({merged = false}) | DONE / TESTED (probes) — look PENDING_OWNER_TEST | commits 26ae99f, 0ef38b5 |
| 09:20 | team7/textures merged (13 procedural PBR sets, 42 maps, validate_pbr.py all pass, Blender sheet docs/images/materials/vis71c_material_sheet.jpg; MaterialLibrary reads an optional MaterialLibraryMaps module, no look change until ids exist) | DONE / TESTED (offline) | commit 399abeb |

| 09:40 | 42 PBR maps uploaded as Image assets (Open Cloud, 0 failures); `ReplicatedStorage.MaterialLibraryMaps` installed; `studioCreateVariants()` made 5 Pattaya MaterialVariants (DryAsphalt, WetAsphalt, PaintedMetal, DarkGlass, Concrete) + 14 SurfaceAppearance templates. Look in game not yet seen (textures on roads apply through RoadLook at play time; kit MeshParts get templates on rebuild) | DONE (install) / PENDING_OWNER_TEST (look) | commit 0b6ab8c; build/materials/image_ids.json |

| 10:00 | Play check after mesh-opt + textures: 0 client errors; roads near the block carry the textured PattayaDryAsphalt variant (24/24); merged tiles: 97/97 NightNeon MeshParts lit at 21:00; 407/508 MeshParts carry SurfaceAppearance; palm impostor trunk is a working collider (raycast hits, CanCollide true); Heartbeat 60.2, p99 19.1 ms (render unfocused → not counted) | TESTED | Play session 10:00 |
| 10:10 | Priority 5: docs/VIS8_ROLLOUT_PLAN.md and docs/SECONDARY_UI_PLAN.md (plans only, nothing implemented); palm trunks now get the Bark SurfaceAppearance, MP_Shutter mapped to the Shutter surface; slice rebuilt (23,786 parts) + mesh block rebuilt | DONE / TESTED (probes) | commit acbf71b |

| 10:40 | Studio came to the front: captures of the merged block (day street / aerial / shophouse close-up / night street / hero drive with HUD) taken; palms visible in play (one-off LTM artefact at session start, 0 hidden in 48 samples while driving); clean-start drive up min 1.00; tail PointLight 1.5/10 painted crossings pink on PBR roads → 0.5/6 | DONE / TESTED | docs/VISUAL_ACCEPTANCE.md §5.3, commit f0c4a73 |

| 10:55 | **Focused render FPS measured** (desktop 2684 × 1148, Studio in front): merged tiles + PBR 59.9 fps, p50 16.7 / p99 18.1 / worst 39.6 ms, parts in view 5,203, memory 6,164 MB; A/B original Part build 60.0 fps, p99 18.0, parts in view 5,248 → no measurable cost; world map inset fix verified on desktop (no regression) | TESTED | docs/VISUAL_PERFORMANCE.md §6, commits 3ea1eaa, 2ccdaf6 |

| 11:40 | Owner review ecbbf89 received: VIS-7.1c = technical baseline; VIS-8 not approved; Second Road pilot may be PREPARED (mesh-opt agent resumed with the brief, no install); palettes changed to the owner tones (exported, Studio rebuild deferred until a fresh .rbxl); docs' "pending" notes replaced | DONE | commits 17f6ae6, cecfec0, a54041a |
| 11:50 | Palm impostor pop-in test at 150 studs/s: 119 switches at 381–450 studs, 0 inside 300; 93 frames with a palm showing neither mesh nor impostor (PattayaLOD unhide latency on the impostor) → fix planned: exclude VisMeshPalms from PattayaLOD and raise the mesh range | TESTED (finding) | Play run 11:50 |
| 11:55 | **Road hole found** while chasing a flip (up −0.92 → 0.77 at (21032–21041, 43–63)): terrain 3 studs below road level at the mouth of Soi Pattaya 8 on Beach Road (x 21042–21070, z 50–110) — no junction fill between Soi 8's slab and the Beach Road slab; a car drifting right at the junction drops a wheel. Fix: hole audit + fill patches (reversible folder), re-drive | IN PROGRESS | tilt log, raycast grid |

| 12:30 | Palm LOD: cross-fade 0.35 s, range 550, PattayaLOD no longer touches mesh palms, late-streamed parts join the record. Pop-in test at 150 studs/s: **0 gap frames** (was 93–197), 161 switches at 500–629 studs, 0 inside 400 | DONE / TESTED | commits 69a58b5, dcc46f3 |
| 12:45 | team8/junction-aprons merged (data-driven junction aprons + sidewalk corner fills, 23,791 parts in 375 chunks, offline checks 0). **Pilot batch a1 only** (8 chunks, 1,676 parts) built in Studio around Beach Road: Probe obstacle hits 0, aprons above road 0, corner fills over a road surface 0 (160,801-ray grid); road-edge drops to terrain 771 → 131 in the 600-stud area; drive Beach Road → Soi 8 junction at 150: up min **0.94** (was 0.77 / −0.92 flip), 0 tilts < 0.9. Rest of the batches NOT built (needs the owner's fresh .rbxl) | DONE / TESTED (pilot) | commit 7d21d4c; rollback `PattayaApronBuilder.Remove()` |
| 12:50 | Second Road pilot export prepared by mesh-opt (60 buildings: 2,577 Parts → 137 + 2,177 = 2,314; 48 new tiles NOT uploaded) — waits for the mobile baseline + .rbxl per owner rule | WAITING_FOR_OWNER | commit 97c5d32, docs/VISUAL_ACCEPTANCE §4.9 |

| 16:20 | Owner saved a fresh backup (Documents\zzzzzz.rbxl, 16:15) + git at d567071. Slice rebuilt with the owner palette (23,786 parts, Probe all 0) + mesh block + palms (FullRange 550, ProbeMesh 0) | DONE / TESTED | — |
| 16:30 | Junction aprons built citywide: 47 batches, 9,154 apron + 14,633 corner parts; Probe aprons above road 0, corner fills above sidewalk 0; corner fill over a road surface 0 of 42,734 top samples (the builder's own 1,602 count is bounding-box based); 4 poles stand inside fills (harmless) | DONE / TESTED | `PattayaApronBuilder.Remove()` rolls back |
| 16:40 | Regression: Beach Road → Bira 217 s at 150, 425/426 on road, 0 tilts < 0.9 (up min 0.93); Central Loop lap 52 s, 102/103, up min 0.99 | TESTED | TK handles full / loop2 |

| 16:50 | team9/traffic-vehicles started (owner item 9: box traffic → Blender sedan / pickup / songthaew / tuk-tuk / scooter / minivan, same collision boxes, box fallback kept; owns PattayaTraffic.client + new TrafficVehicles module) | RUNNING | branch team9/traffic-vehicles in D:\ROBLOXRACE-qa |

| 17:30 | Traffic vehicles (owner item 9): team9 merged; 7 Blender vehicles (sedan/taxi, hatch, scooter pair, tuk-tuk, pickup, songthaew, minivan; 624–1,016 tris, 4 MeshParts) uploaded (ids in TrafficVehicles), templates installed in ReplicatedStorage.TrafficVehicleTemplates (7/7 parts ok). Play: 54/54 traffic cars built from meshes, 0 box fallbacks, head lamps at the front on 54/55 moving cars, collision = the old Body box only (meshes non-colliding / non-query / massless), near misses still pay (14 in 35 s). Captures pending Studio focus | DONE / TESTED | commits f281f48, 1283930 |
| 17:35 | Palette day capture docs/images/vis71d_palette_street_day.jpg | DONE | — |

| 18:00 | Owner saved (Ctrl+S). Focused desktop perf after aprons + palette + mesh traffic: 60.0 fps, p99 18.3 ms, parts in view 5,366, memory 6,756 MB, textures 230 MB. Captures: palette night street, tuk-tuk and songthaew traffic at night | TESTED | docs/images/vis71d_palette_street_night.jpg, traffic_*_night.jpg |

| 18:20 | Mobile baseline (Device Emulator 830×439, compact HUD): steady 59.9 fps / p99 18.8 ms parked, 59.7 fps / p99 28.2 ms driving after streaming settles; first 10–20 s after arriving have 100–200 ms streaming hitches (1 % low 14–19); GraphicsTexture 230–242 MB (≫ 18 MiB budget — mostly not the PBR maps; A/B + real phone needed) | TESTED (emulator = PC GPU) | docs/VISUAL_PERFORMANCE.md §7 |

| 18:30 | Texture A/B inconclusive in Studio (cache keeps 244.7 MB after removing all PBR); only 3 distinct facade images in the world; Studio's own textures/CoreGui inflate the figures → real-phone measurement needed for the 18 MiB budget | PENDING_OWNER_TEST | docs/VISUAL_PERFORMANCE.md §7 |

## Priority queue (owner order)
1. Blender mesh optimisation: instance count 2,074 → ≤ 1,018 for the 14-building block (merge per face / per floor band), LOD, UV + material kept, footprint/collision unchanged.
2. Texture / PBR pipeline (UV, facade textures, normal/roughness/metalness, glass, asphalt, concrete, palms) — offline validated before Roblox.
3. Visual refinement (palms, variety, window brightness, wet/dry, neon, Thai signs, ground-floor shops) — slice only.
4. Automated tests that need no owner (Luau syntax, Python tests, asset validation, bounds, road collision, determinism, manifest consistency, rollback).
5. Next-milestone prep (quality tiers, perf config, comparison tools, QA scripts; VIS-8 / Secondary UI as plans only).
