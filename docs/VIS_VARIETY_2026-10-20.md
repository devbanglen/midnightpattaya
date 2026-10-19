# VIS-7.2 building variety v2: Beach Road slice (team13/vis-variety, 2026-10-20)

**Status: written and checked offline. Not built in Studio and not captured.** Nothing here has been seen in game.
Whether it looks better stays unknown until the leader builds it and captures it. VIS-8 (citywide) is still not
approved; this change covers the slice only.

## 1. What changed
Building variety in the slice is now controlled and seeded. All of it is switched by `variety.v2_enabled` in
`tools/mapgen/config/vis_slice.json`, or by `--v2` on the command line. The default is **false**.

The rules this change keeps:
- No box size, position, yaw, VisHull, collision or road changes.
- No new kit module, MeshPart asset, upload or texture.
- No change to the lighting preset.
- The owner plaster palette stays as the base colour.

Every choice is seeded by the OSM id, with salts 100 and up (VIS-7.1 uses salts 1–29, which are unchanged), so the
output is repeatable.

| Knob (`variety.v2.*`) | What it does | Who gets it | Instances |
|---|---|---|---|
| `weathering` | The wall colour (VisCore, fins, cornice/crown bands, MP_Wall MeshParts) is lerped 3–12 % toward one of three stain tints: warm grime, damp grey-green, dust. This happens after the palette mix. | 60 % of all buildings (287 here) | 0 |
| `shutter_colors` | Each building gets one shutter / roller-door colour: today's galvanised grey, pale blue, muted green, cream or light galvanised. The MP_Shutter MeshParts use it too. | shophouse, industrial | 0 |
| `shopfront_accent` | The shopfront_a pilasters take the awning accent colour, darkened 30 %. | 35 % of shophouses (85) | 0 |
| `shutters` | Each shopfront bay has its roller shutter either down, or up with a tall ShopGlow pane (lit like a shopfront). The share of bays with the shutter down is set per building, 30–85 %. | shophouse | neutral |
| `awnings` | Awning mode per building: 1 = one awning over the whole front, as today (96 buildings). 2 = one awning per bay, each in its own accent colour, with 0–35 % of bays left bare (84). 3 = no awning (29). | shophouse | +72 net |
| `balconies` | Two rhythms. balcony_grid_a: every 2nd, 3rd or 4th bay gets a solid plaster BalconyInfill instead of the rail, in vertical stacks or a diagonal (period 0 = all rails). balcony_row_a: 35 % of buildings get a solid plaster BalconyUpstand along the floor instead of the continuous rail. | hotel, condo | neutral (1,180 infills, 267 upstands) |
| `density_spread` | Shophouse AC units are set to 60 ± 30 % per building (was ± 20) and signboards to 75 ± 30 % (was 80 ± 20). Some rows end up dense, others sparse. | shophouse | −15 AC parts, −10 signboards |
| `roof_extra` | Extra copies of existing roof modules after the style's own list: shophouse AC bank 40 % and second water tank 20 %; hotel tank 45 % and AC 35 %; condo AC 50 %; commercial AC 45 % and tank 25 %; industrial tank 25 %. They pass the same fit test and the same taller-box/prop drop test (7 were dropped). | see left | +430 roof parts |
| `mesh_blocks_structural` (false) | Buildings in the vismesh blocks (sample block 1 and pilot block 2, 74 buildings) get only the colour knobs (`weathering`, `shutter_colors`). Their mesh rows, merged-asset requests and expected counts stay byte-identical, so nothing needs uploading. | — | — |
| `kit_patch` | Gates and new parts added to shopfront_a, balcony_grid_a and balcony_row_a, applied only while v2 is on. New parts are appended, so the part index of every existing part (the input to the lit and density hashes) does not change. | — | — |

How the kit patch works:
- New part fields:
  - `gate = [field, value]`: the part is made only on buildings whose field (default 1) equals value.
  - `dk`, `dpi`, `dinv`: a seeded density per bay. The part is made where `litHash(osm, face, module, floor, bay, dpi + 50) % 100 < b[dk]`, or where it is not when `dinv` is set.
  - `rh = 1 / 2`: rail bay or solid bay of the balcony rhythm (`rhp` = period, `rhs` = shift per floor).
- New colour keys:
  - `accentBay`: `accents[(litHash(..., pi + 70) // 7) % #accents + 1]`.
  - `gfPilaster`: the darkened accent when `gfa = 1`, otherwise wallDark.
- Exported building fields: `wx wxc shc gfa shp awm awp rhp rhs brs`, plus `acp` / `sgp` with the wider spread. The manifest gets `variety2` (stain colours, shutter colours, accentDarkMix).
- Cap rule: the cap check uses the VIS-7.1 facade layout, which v2 never changes. If a building's v2 parts would go over its style cap, it first loses its extra roof modules, then its structural knobs. This happened to 7 buildings. As a result the placement rows (`p`) are identical for all 507 buildings.

Files: `tools/mapgen/vis_slice.py` (roof placement factored into `place_roofs`, plus `apply_kit_patch`, `v2_fields`
and the `--v2` flag), `tools/mapgen/config/vis_slice.json` (`variety.v2_enabled`, `variety.v2`) and
`roblox/src/ServerStorage/PattayaVisSliceBuilder.luau` (the gates, colour keys and stain tint). `VisMeshBuilder.luau`
did not need a change: it reuses `buildBuilding` and its `colour()`, so mesh buildings get the weathering and shutter
colours automatically.

## 2. Checks done offline
- **Off = today, byte for byte.** `vis_slice.py` with v2 off was diffed against the main checkout's current
  `build/vis_slice/` (`manifest.luau`, `vismesh.luau`, 59 chunks, `vis_slice.json`, `mesh_sample.json`, check png) and
  against `build/vis_assets/merged/request.json`. Every file is identical. This was run before and after the change.
- **Each knob switches off on its own.** With v2 on and every sub-knob's `enabled` set to false, the export gives 23,786
  parts, 390 signboards and 59 chunks (today's counts). The manifest then differs only by the kit patch and `variety2`.
- **v2 on:** all checks are 0 (outside own box, above the box, road + sidewalk, discs, gate, city props, furniture,
  coast, landmarks, other boxes). The run is deterministic: two runs gave identical output.
- **vismesh unchanged:** `vismesh.luau` and `request.json` are identical with v2 on. In `mesh_sample.json` only
  `citywide_estimate` (report only) changed. The 74 mesh-block buildings differ only by `wx` / `wxc` / `shc`.
- **Luau twin:** both builders compile with `luau-compile.exe`. The real `PattayaVisSliceBuilder.luau` was then run in
  `luau.exe` with mocked Roblox APIs on every exported building. v2 data gave 24,273 parts with 0 of 60 chunks differing
  from `manifest.chunkParts`. The current (v2-off) data gave 23,786 parts with 0 of 59 chunks differing, so the new
  builder is backward compatible.

## 3. Instance deltas (export, slice; not measured in Studio)
| | Today (VIS-7.1c) | v2 on | Delta |
|---|---|---|---|
| Slice Parts (`totalParts`) | 23,786 | 24,273 | **+487 (+2.05 %)** |
| Roof parts | 1,024 | 1,454 | +430 (water_tank_a 456 → 662, ac_pair_a 40 → 264) |
| shopfront_a parts | 2,892 | 2,964 | +72 (per-bay awnings minus no-awning fronts) |
| window_pair_ac_a parts | 2,141 | 2,126 | −15 (AC density) |
| balcony_grid_a / balcony_row_a | 6,347 / 3,423 | 6,347 / 3,423 | 0 (infill / upstand replace rails) |
| Signboards (Part + SurfaceGui + TextLabel + UIPadding) | 390 | 380 | −10 (−30 GUI instances) |
| NightNeon parts (lit panes + neon) | 6,430 | 6,599 | +169 (open shop panes) |
| **Instances, Parts + GUI** | 24,956 | 25,413 | **+457 (+1.8 %)**, under the +5 % limit |
| Chunks / batches | 59 / 8 | 60 / 8 | new chunk `v3_-2_3`; batches s1–s8 = 3,007 / 3,720 / 2,325 / 3,401 / 3,712 / 3,907 / 3,721 / 480 |
| Sample block 1 (mesh) | 40 Parts + 508 MeshParts | same | 0 |
| Textures / uploads / lights | — | — | 0 new textures, 0 uploads, 0 lights |

Per style: hotel +166, shophouse +279, commercial +34, industrial +8, condo 0, house 0. Every part stays under the
25,000 slice budget and under 600 parts per chunk (the largest has 599).

## 4. Leader install (Studio, edit mode; only after the owner's fresh .rbxl backup + a git checkpoint)
1. On main after the merge, export with v2 (16 s). This rewrites `build/vis_slice/` (and `request.json`, unchanged):
   ```
   .venv\Scripts\python tools\mapgen\vis_slice.py tools\mapgen\config\vis_slice.json --v2
   ```
   Expect `parts 24,273`, `signboards 380`, `60 chunks (max 599 parts)`, all checks 0, and
   `vismesh sample block: ... 40 Parts + 508 MeshParts`.
2. Install, with the same JSON bundle / HttpListener method as before (docs/VISUAL_ACCEPTANCE.md §4 step 2):
   - `ServerStorage.PattayaDataVisSlice` ← every file in `build/vis_slice/roblox/`: `manifest.luau`, `vismesh.luau` and
     **60** `chunk_v*.luau`, including the new `chunk_v3_-2_3`. Replace the old modules. A stale chunk module left over
     does no harm, because the builder only reads the chunks listed in `manifest.chunks`.
   - `ServerStorage.PattayaVisSliceBuilder` ← `roblox/src/ServerStorage/PattayaVisSliceBuilder.luau`.
   - `VisMeshBuilder`, `VisAssetsManifest`, `MaterialLibrary`: no change. No asset upload.
3. Rebuild. Edit mode caches `require`, so require a parented clone of the new builder. Its `script.Parent` must be
   ServerStorage so that it finds `VisMeshBuilder`. The builder already clones the data modules itself.
   ```lua
   local SS = game:GetService("ServerStorage")
   local m = SS.PattayaVisSliceBuilder:Clone(); m.Name = "PattayaVisSliceBuilder_v2run"; m.Parent = SS
   local V = require(m)
   print(V.Remove())                 -- RemoveMesh + VisSliceChunks removed + procedural boxes restored
   for _, s in {"s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"} do print(V.Build({batch = s})) end
   print(V.Probe())
   ```
   Expect `vis parts 24273 (manifest total 24273); touching road/sidewalk/disc 0; outside their box 0; hull != original 0;
   boxes still in the city 0; chunks with a different part count 0; NightNeon 6599; signboards 380`.
   Each `V.Build` prints its batch parts (s1 3,007 … s8 480). No `built %d parts, manifest says %d` warning should appear.
4. Put the mesh sample block and palms back, unchanged: `print(V.BuildMesh())` and then `print(V.ProbeMesh())`. Expect
   the same as VIS-7.1c: 14 buildings, 40 Parts + 508 MeshParts, 0 unusable, palms 157, outside / road / size 0. Only
   build pilot block 2 (`V.BuildMesh({block = 2})`) if it was built before.
5. When done, `m:Destroy()`.
6. Capture the same cameras as VIS-7.1c (`vismesh.camera` street / aerial, Beach Road Soi 7/8), day and 21:00, plus a
   shophouse row outside the sample block. The hotel and shophouse rows north of the sample block show most of the
   structural knobs. Then run a focused perf before/after and compare against docs/VISUAL_PERFORMANCE.md §6.

## 5. Rollback
- **Data:** run the export without `--v2` (v2_enabled is false in the committed config). That reproduces the VIS-7.1c
  output byte for byte. Copy it into `PattayaDataVisSlice` (59 chunks; `chunk_v3_-2_3` can stay or be deleted), then
  repeat step 3 (`V.Remove()`, s1–s8, `V.Probe()` → 23,786 parts, NightNeon 6,430, signboards 390) and step 4.
- **Builder:** the new `PattayaVisSliceBuilder` builds the old data exactly (offline twin test: 23,786 parts, 0 chunk
  mismatches), so it can stay. To revert anyway, use the source of `roblox/src/ServerStorage/PattayaVisSliceBuilder.luau`
  from main before this branch.
- **Whole slice off:** `V.Remove()` brings the procedural boxes back (unchanged rollback path). `V.RemoveMesh()` /
  `RestoreReplaced()` work as before.
- **Single knob:** set that knob's `enabled` to false in `variety.v2` (or tune its %), re-export with `--v2`, and
  reinstall the data.

## 6. Open points for the leader / owner
- **Look:** unverified. The weathering mix (3–12 %) and the per-bay awning colours are guesses until someone sees them
  at night under MidnightClear. If they read as dirty or noisy, lower `weathering.mix_pct` or move `awnings.mode_weights`
  toward mode 1.
- **Night:** +169 lit open-shop panes (NightNeon). The lit share of shopfronts is the same, only on more glass.
- **Mesh blocks:** structural variety is kept out of the mesh blocks on purpose. `mesh_blocks_structural: true` would
  change their Part / roof rows and has to be checked for new merged-asset requests (uploads) first.
