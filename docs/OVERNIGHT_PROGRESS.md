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

## Priority queue (owner order)
1. Blender mesh optimisation: instance count 2,074 → ≤ 1,018 for the 14-building block (merge per face / per floor band), LOD, UV + material kept, footprint/collision unchanged.
2. Texture / PBR pipeline (UV, facade textures, normal/roughness/metalness, glass, asphalt, concrete, palms) — offline validated before Roblox.
3. Visual refinement (palms, variety, window brightness, wet/dry, neon, Thai signs, ground-floor shops) — slice only.
4. Automated tests that need no owner (Luau syntax, Python tests, asset validation, bounds, road collision, determinism, manifest consistency, rollback).
5. Next-milestone prep (quality tiers, perf config, comparison tools, QA scripts; VIS-8 / Secondary UI as plans only).
