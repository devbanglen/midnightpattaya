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

## Priority queue (owner order)
1. Blender mesh optimisation: instance count 2,074 → ≤ 1,018 for the 14-building block (merge per face / per floor band), LOD, UV + material kept, footprint/collision unchanged.
2. Texture / PBR pipeline (UV, facade textures, normal/roughness/metalness, glass, asphalt, concrete, palms) — offline validated before Roblox.
3. Visual refinement (palms, variety, window brightness, wet/dry, neon, Thai signs, ground-floor shops) — slice only.
4. Automated tests that need no owner (Luau syntax, Python tests, asset validation, bounds, road collision, determinism, manifest consistency, rollback).
5. Next-milestone prep (quality tiers, perf config, comparison tools, QA scripts; VIS-8 / Secondary UI as plans only).
