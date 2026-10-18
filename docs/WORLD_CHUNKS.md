# World chunks

- Chunk size: 512 studs (`chunk_size_studs`). Chunk id = `floor(x/512)_floor(z/512)` in gameplay coordinates;
  an edge belongs to the chunk of its middle point (stable while the source data and config are unchanged).
- Each chunk is a Model `workspace.PattayaWorld.Chunks.Chunk_<id>` with `ModelStreamingMode = Atomic`, ready for
  instance streaming. `Workspace.StreamingEnabled` is NOT switched on yet (it affects the whole place; decide in
  Phase 8 with measurements).
- Data modules: `ServerStorage.PattayaData.chunk_<id>` (generated), `manifest` (chunk list, junctions, sea mask,
  coastline, bounds, attribution).
- First slice: 72 chunks, largest data module 44 KB.

## Wide world (Naklua – Jomtien, `tools/mapgen/config/pattaya_wide.json`) — built as data, NOT imported yet
The wide world is an **extension** of the tested central slice, not a rebuild:
- Same CRS (EPSG:32647), same `origin_utm` as `build/central_pattaya/graph_game.json` (fixed in the config),
  compression 0.5, 0.28 m/stud, chunk size 512, world ORIGIN (20000, 0, 0). Every shared OSM node lands on exactly
  the same stud; seam nodes are checked.
- `base` block: road segments with both ends inside the central slice bbox, and buildings wholly inside it, belong to
  the base build and are not regenerated. New edges meet the base graph only at base nodes.
- Area: lat 12.858–12.985, from the sea to Sukhumvit Road (+~130 m; `clip_polygon_lat_lon`). The Bira corridor
  continues east of Sukhumvit (tools/circuit).
- Output `build/pattaya_wide/roblox/`: 444 new `chunk_<cx>_<cz>` modules (largest 13 KB, 1.5 MB total — all far below
  the 200 KB per-module limit), `manifest.luau` (183 KB: new chunks, import batches, new junction discs, seam discs,
  terrain rectangles outside the base frame, sea rows, coastline), combined runtime modules `graph.luau` (+
  `graph_part_1/2`), `jobs.luau`, `roadfight.luau` (identical to central), `traffic.luau`, and `worldmap.luau`.
- Chunk ids use the same formula as the base; a new chunk may share an id with a base chunk, so new chunks are built
  into a separate folder `workspace.PattayaWorld.WideChunks.Chunk_<id>` (Atomic streaming, like the base).

### Import plan for the leader (incremental; the tested slice stays untouched)
Prerequisite: save the place (or rely on version history). Studio memory/time below are ESTIMATES, not measured.
1. **Data in** (same localhost HttpListener method as the central slice, `docs/ROBLOX_INTEGRATION.md`): create
   `ServerStorage.PattayaDataWide` and load `build/pattaya_wide/roblox/manifest.luau` + all `chunk_*.luau` (445
   modules, 1.7 MB). Do **not** touch `ServerStorage.PattayaData` yet.
2. **Builder**: replace `ServerStorage.PattayaBuilder` with `roblox/src/ServerStorage/PattayaBuilder.luau`
   (`Build()` behaves as before; adds `Extend()` and `RemoveExtension()`). Untested in Studio — run it on a copy of
   the place first if possible.
3. **Terrain**: `B.Extend({roads = false})` — clears and fills ground in 4 rectangles around the base frame (2048-stud
   tiles), then carves sea/sand rows. Nothing inside the base frame (snapped outward to the voxel grid) is written.
   Frame 13,680 x 26,336 studs minus the base frame; expect tens of seconds to a few minutes (estimate).
4. **Seam batch**: `B.Extend({terrain = false, batch = "seam"})` (69 chunks next to the slice). Check: roads meet the
   slice's roads end-to-end where they cross the slice border (e.g. Pattaya Nuea/Klang/Tai east ends,
   Thappraya south), no building over a road. Then decide on `B.Extend({roads = false, terrain = false,
   removeBaseConflicts = true})`: it deletes the 8 base buildings (OSM ids in `manifest.baseBuildingConflicts`)
   that a new road surface cuts into at the seam — the only change to base content, and only if called.
5. **District batches**, one call each, playtest between: `pratumnak` (106), `jomtien` (127), `south` (14),
   `central` (14), `north` (29), `naklua` (85). Each call prints chunks/parts built; built chunks are skipped, so a
   call can be repeated after an error. Expect roughly 1–3 minutes per 100 chunks (one `task.wait()` per chunk plus
   Part creation) and Studio memory growing by very roughly 100–200 MB for the whole extension (~40k Parts, ~24.5k
   Textures).
6. **Runtime switch** (only after the Luau owners have done the two changes in `docs/WORLD_MAP_INTEGRATION.md`:
   heap Dijkstra, boss courses pinned to the base graph): in `ServerStorage.PattayaData` replace `graph` and add
   `graph_part_1`, `graph_part_2`; replace `jobs` (25 stands); `ReplicatedStorage.PattayaTraffic` ← wide
   `traffic.luau` (84 loops); `roadfight` is identical. Add `ReplicatedStorage.PattayaWorldMap` ← `worldmap.luau`.
   The central `manifest` and chunk modules stay as they are (race, spawn, landmarks unchanged).
7. **Undo**: `B.RemoveExtension()` removes WideChunks, WideJunctions and the wide terrain rectangles; restore the
   old `graph`/`jobs`/`traffic` modules from `build/central_pattaya/roblox/`.

## Imported by the leader (2026-10-18, Studio)
- Data in: `PattayaDataWide` (manifest + 444 chunk modules, loaded from one JSON bundle in a single HTTP call to stay
  under HttpService's request limit), `PattayaDataCorridor` (deduplicated corridor, 11 chunks), merged runtime graph
  `PattayaData.graph` + `graph_part_1/2` (central 463 nodes / 614 edges first, then 2,462 wide nodes, then 16
  corridor nodes; 3,818 edges), wide `jobs` (25 stands), wide `PattayaTraffic` (84 loops), `PattayaWorldMap`.
- `Extend({roads = false})`: wide terrain in 13 s (Ground under Jomtien and Naklua probes, Water west of Jomtien).
- Chunks: the first 69-chunk seam call crashed Studio part-way (37 built; Auto-Recovery brought the place back).
  Rebuilt in groups of 8 chunks per `Extend({only = ...})` call: seam 69, pratumnak 106 (8,988 parts), jomtien 127
  (11,657), south 14 (1,529), central 14 (1,652), north 29 (3,255), naklua 85 (5,334), corridor 11; **455 wide chunks,
  ~35k parts, no errors, about 30 s of build time in total.** Studio memory went from 3.4 to 3.9 GB.
- Probes (raycast every 25 studs along every new edge, 24,994 points): 95.9% hit road at y = 1; 966 hit a
  sidewalk at y 1.6 (close parallel roads / dual carriageways overlap at ×0.5, the known central-slice issue, a
  0.6-stud bump) and 62 hit nothing (gaps to investigate; 228 edges have at least one miss, most just one point at
  a junction). The corridor: 1,240 probes, 0 misses.
- `removeBaseConflicts` was NOT run: the 8 seam buildings listed in the manifest are still there.
- Build in small `only` groups from now on: one 69-chunk call crashed Studio once (64 GB machine, Studio at 3.4 GB,
  so not memory); 8-chunk calls never did.
