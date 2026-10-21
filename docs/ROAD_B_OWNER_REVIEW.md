# Road B: owner review (Sukhumvit / Pattaya Klang junction, world x 24220..24820, z 650..1250)

**Status: OWNER REVIEW. Nothing has been built in Studio, and building is NOT approved.** Every number below comes
from the offline tools (`tools/roadvis`, read only on `build/`). Every image is an offline Blender or PIL preview, not
a Studio capture, and none of it is a Visual PASS. The final proof that cars do not flip needs physics drives in Studio
after an approved build (section 7).

Regenerate everything with `D:\ROBLOXRACE\.venv\Scripts\python tools\roadvis\cli.py pilot --art` and
`tools\roadvis\shoulder_proof.py`. Tests: `tools\qa\tests\run_all.py` (all green, 194; 29 in `test_roadvis`).

## 1. Root cause (summary)

Full report: [ROAD_VISUAL_ROOT_CAUSE.md](ROAD_VISUAL_ROOT_CAUSE.md).

| # | Cause | Number at this junction | Section |
|---|---|---|---|
| 1 | City at x0.5, lanes and car at x1: roads take 2.08x their real share | carriageway-on-carriageway overlap 12,188 studs² (0.85 M citywide) | [§2](ROAD_VISUAL_ROOT_CAUSE.md#2-proportions-the-main-cause) |
| 2 | Dual carriageways merged by moving one slab onto the median | 250 of 3,253 lane samples over terrain; 360 fill triangles | [§3](ROAD_VISUAL_ROOT_CAUSE.md#3-defects-at-this-junction-measured) |
| 3 | Junction discs | 38 % of disc area sticks out past the slabs (13 % citywide) | [§3](ROAD_VISUAL_ROOT_CAUSE.md#3-defects-at-this-junction-measured) |
| 4 | What you see is what you drive on: every collision patch is visible | 25.7 % of the asphalt is stacked 2+ surfaces deep | [§5](ROAD_VISUAL_ROOT_CAUSE.md#5-ranked-root-causes) |
| 5 | Markings and zebras made per edge | lane-line coverage 46 %; 0 of 18 zebras reach a sidewalk at both ends | [§3](ROAD_VISUAL_ROOT_CAUSE.md#3-defects-at-this-junction-measured), [§4](ROAD_VISUAL_ROOT_CAUSE.md#4-citywide-same-definitions-551-chunks-of-512-studs-raster-1-stud) |
| 6 | Sukhumvit (express) has no sidewalk; the shoulder pilot outlines the ragged edge | 227 shoulder strips visible in the owner's view | [§6](ROAD_VISUAL_ROOT_CAUSE.md#6-the-approved-shoulder-pilot-in-the-owners-view-honest-assessment) |

Design B fixes these at the junction. It builds both carriageways from the road graph (the graph is unchanged), uses
topology-aware junction polygons with no discs, adds kerbed sidewalks and islands, draws markings per carriageway, and
puts zebras only on legs. Spec and the A vs B comparison: [ROAD_VISUAL_SPEC.md](ROAD_VISUAL_SPEC.md).

## 2. Before / A / B images (offline previews, NOT Studio)

The three panels show the same view: before, design A, design B. The 3D views are Blender Cycles renders of the
exported footprints, using the owner's screenshot camera: pos (24609.8, 115.9, 713.3), look (-0.386, -0.386, 0.837),
vertical FOV 70, 1831 x 1074. The top-down view is a PIL raster.

The 3D renders come from the junction-interior version (`4b5918d`). Since then, only the edge of the sidewalks and
islands next to shoulder pieces changed (section 6). The GPU box had no free Blender slot when this was written, so
re-render the 3D views before the approval meeting with
`tools/roadvis/blender_preview.py` (spec §10). The top-down image is current.

Top-down (current):

![top-down before / A / B](../art/roadvis/top_before_A_B.png)

Owner's camera:

![owner camera before / A / B](../art/roadvis/cmp_owner_view.png)

Street level, east kerb of Sukhumvit:

![street before / A / B](../art/roadvis/cmp_street.png)

Driver chase camera, northbound:

![driver before / A / B](../art/roadvis/cmp_driver.png)

Aerial:

![aerial before / A / B](../art/roadvis/cmp_aerial.png)

## 3. Geometry QA (offline, design B)

**Probe expectations.** These are what `RV.Probe()` should report in Studio. 680 lane-centre samples on 31 legs,
outside the 50-stud seam band. A 4 x 9 car footprint (6 points) sits at each offset, counted only where the offset lies
on the carriageway.

| Offset | Samples | Drop (wheel over terrain) | Kerb contact (0.45–0.6 step up) |
|---|---|---|---|
| 0 | 680 | **0** | 0 |
| +8 | 625 | **0** | 0 |
| −8 | 625 | **0** | 0 |
| +14 | 216 | **0** | 0 |
| −14 | 216 | **0** | 0 |
| +20 | 123 | **0** | 0 |
| −20 | 123 | **0** | 3 |
| +24 | 118 | **0** | 15 |
| −24 | 118 | **0** | 20 |

**Other checks, before vs B:**

| Check | Before | B |
|---|---|---|
| Wheel check: 4 RaceCar wheels on every lane of every carriageway, outside the seam band | 250 of 3,253 unsupported | **0 of 3,253** |
| Same, including the 40-stud seam band at the area edge | 295 of 3,871 | 18 of 3,871. These are at the seam, where the old merged slab continues outside the area. |
| Pilot parts or sidewalks overlapping a building | | **0.0 studs²** |
| Visible asphalt without collision under it | | 0.0 studs² |
| Collision outside the visible surface | | 27.5 studs² (plus a 118.7 studs² invisible support strip, section 6) |
| Asphalt outside every lane corridor and junction (inside the area) | 470 | **0.0** |
| Zebras that reach a sidewalk or island at both ends | 0 of 18 | **4 of 4**: Pattaya Klang 41 studs, Sukhumvit 109 and 104, Soi 53 26. All perpendicular to their leg. |
| Lane / centre / edge markings inside the junction polygon | | **0.0 studs²**. The polygon is 19,857 studs²; only stop lines and zebras sit at its boundary. |
| Lane-boundary coverage outside the junction polygon | 45.8 % | 99.3 % |

Note on zebras: the trunk_link zebra (Thanon Pinang) of the earlier version is no longer placed. Its sidewalk landing
moved behind a shoulder piece when sidewalks stopped covering the shoulders. 4 remain, all landing on a sidewalk.

## 4. Instance budget

**Parts in the area:**

| | Parts |
|---|---|
| Before: old parts that `MoveReplaced` moves to `ServerStorage.RoadVisBackup` | **804**: Road 397, Sidewalk 7, Dash 41, Centre 22, Junction 17, Joint 10, Apron 142, CornerFill 13, ZebraStripe 155 |
| After, default Parts build (approvable without asset uploads) | **1,935**: asphalt 550, sidewalk 710, island 144, lane 179, centre 36, edge 108, stop 6, zebra 68, kerb 64, grass 70 |
| After, mesh build (`Build({mesh = true})`) | 1,457 (1,415 invisible collision wedges + 42 MeshParts). It **needs the tile meshes uploaded as assets, which is not approved**, so it stays a preview option. |
| Shoulder pilot parts in the area (unchanged) | 1,601 |

**Atomic cells.** `RoadVisPilot` has 10 Models, each `ModelStreamingMode = Atomic`. A 256-stud cell over 600 parts is
split into its 128-stud quadrants. Each module is at most 600 parts and at most 60 KB.

| Cell | Parts | Cell | Parts |
|---|---|---|---|
| 16_3 | 257 | 17_3q11 | 160 |
| 16_4 | 74 | 17_4 | 541 |
| 17_2 | 93 | 18_2 | 175 |
| 17_3q00 | 31 | 18_3 | 91 |
| 17_3q01 | 354 | **max** | **541 ≤ 600** |
| 17_3q10 | 159 | | |

**QA runner (`PattayaQARunner.luau`, not changed):**

| Item | Reference / cap | Change with B |
|---|---|---|
| `PART_REFS` WideChunks | 37,800 (warn above 47,250) | −467 |
| `PART_REFS` ApronChunks | 23,791 (warn above 29,738) | −155 |
| `PART_REFS` FurnitureChunks | 9,246 (warn above 11,557) | −155 |
| WideJunctions (no reference) | | −27 |
| RoadVisPilot (no reference) | | **+1,935** (INFO line only) |
| ShoulderChunks | 2,536 | 0 |
| `TOTAL_PARTS_WARN` | 160,000 | **+1,131** net in workspace. The 804 backed-up parts sit in ServerStorage, which the runner does not count. |
| `CHUNK_CAPS` | no entry for RoadVisPilot | Not checked. Every cell is ≤ 600, so a future `RoadVisPilot = 600` cap would pass. |

**Conclusion:** no QARunner cap or reference has to change for the pilot. If the pilot is accepted, adding
`["PattayaWorld.RoadVisPilot"] = 1935` to `PART_REFS` and `RoadVisPilot = 600` to `CHUNK_CAPS` would make it
visible. **Not done here.**

## 5. Rollback

| Step | Command | Expected |
|---|---|---|
| 1 | `RV.ShoulderLookRevert()` (only if the optional shoulder look was applied) | every changed shoulder part gets its original Color / Material / Transparency back from its `RVOrig*` attributes |
| 2 | `RV.Remove()` | `RoadVisPilot` destroyed; **`restored 804 of 804`**, each part to its exact original parent and CFrame; backup folder removed. If any original parent is missing, the backup is KEPT and the message says so. |
| 3 | `RV.Plan()` | `pilot built: false; backup present: false`; move plan `MATCHES the data` again |
| 4 | File > version history | last resort: the place version saved just before the build |

**What is saved where during a pilot:**

| Item | Where |
|---|---|
| Builder | `ServerStorage.PattayaRoadVisBuilder` |
| Data | `ServerStorage.PattayaDataRoadVis` (manifest + 10 cell modules) |
| New road | `workspace.PattayaWorld.RoadVisPilot.Cell_*` (10 Atomic Models) |
| Moved old parts | `ServerStorage.RoadVisBackup`. One Folder per original parent, with an ObjectValue `OriginalParentRef`. Each part has the attributes `OriginalParent` (path), `OriginalCFrame` and `RoadVisMoved`. The folder attribute `Count` = 804. |
| Optional shoulder look | attributes `RVOrigColor`, `RVOrigMaterial`, `RVOrigTransparency` on the shoulder parts it touched; nothing else |

## 6. Proof that the shoulder pilot still carries the wheels with B (offline)

### 6.1 No shoulder part is moved, hidden or changed by default
- The replace list (804 parts) contains **0** shoulder pieces (`shoulder_proof.untouched`).
- `MoveReplaced` only looks in WideChunks, Chunks, WideJunctions, Junctions, ApronChunks and FurnitureChunks, under road
  part names. It skips anything in `ShoulderChunks` or with the `Shoulder` attribute, and checks twice.
- In the luau test on a mock tree, a part named `Road` inside `ShoulderChunks` is never selected.
- `Build` creates parts only under `RoadVisPilot`. `Remove` destroys only `RoadVisPilot` and the backup folder; a source
  test allows no other `:Destroy()`.
- `ShoulderLook` is opt-in only. It keeps CanCollide, and its revert is tested.

### 6.2 Where B meets the shoulders: heights, gaps, overlaps
Every edge of the 871 shoulder / taper / gap pieces in the area was sampled every 1 stud. The collision top was read
0.1 stud outside the edge.

| Edge class (studs of shoulder edge) | Before (today) | With B |
|---|---|---|
| Flush (road-height neighbour, step ≤ 0.02) | 3,165 | **3,250** (largest step 0.015) |
| Kerb (step **up** 0.6 to a sidewalk / island face, no drop) | 21 | 1,118 (largest 0.615) |
| Drop (terrain, 3 studs down) | 1,980 | **788** |
| Slot (nothing at 0.1 but a surface within 1 stud) | 151 | 162 (+11) |
| Between two shoulder pieces | 1,666 | 1,666 |

**Overlaps:**

| Overlap | Area |
|---|---|
| B sidewalk / island collision on a shoulder piece | **0.0 studs²** |
| B visual sidewalk on a shoulder piece | **0.0 studs²** |
| B asphalt on a shoulder piece | 2,977 studs², 1.5 cm above it (1.000 vs 0.985). Both collide, the step is 0.015 and the asphalt hides the shoulder. This is the only overlap, and it is flush. |

To reach this, design B was changed on this branch:
- Sidewalks and islands stop exactly at shoulder pieces.
- Sidewalk / island collision is pulled back from the asphalt only, never from a shoulder.
- The new asphalt also rebuilds the outside part of every replaced part that reaches past the area edge.
- An invisible road-height strip (118.7 studs², never under a kerb, at most 2 studs from the visible asphalt) keeps
  the support where an old apron used to hold a wheel.

Result: 1,192 fewer studs of shoulder edge drop to terrain. Where a shoulder meets B's sidewalk, there is a 0.6 kerb
instead of a 3-stud drop. The 11 extra slot studs come from the simplified kerb collision (simplify tolerance
0.25 studs). Their width was not measured separately.

### 6.3 Shoulder drive gate on the combined geometry
The run set is the same as the Studio pilot: the narrowing spot (24560, 900), path B (docs/ROAD_SHOULDERS.md), forward
and reverse, TestKit lateral ±24 / ±20 / ±14 (+ = right of travel), 100 / 150 / 200 studs/s. That is 36 runs.

Every 1 stud, the 4 RaceCar wheel contacts read the collision top. "Drops" counts samples where a wheel is over
terrain. "Up" is the static up-vector Y of the plane through the 4 contacts. **Speed does not change static geometry**,
so the three speeds give identical numbers.

| Dir | Lateral | Before: drops / min up | With B: drops / min up | B kerb samples |
|---|---|---|---|---|
| fwd | +24 | 0 / 1.000 | 0 / 0.998 | 81 |
| fwd | −24 | 66 / 0.916 | **44** / 0.916 | 45 |
| fwd | +20 | 0 / 1.000 | 0 / 0.999 | 16 |
| fwd | −20 | 40 / 0.967 | **31** / 0.953 | 43 |
| fwd | +14 | 0 / 1.000 | 0 / 1.000 | 0 |
| fwd | −14 | 0 / 1.000 | 0 / 0.999 | 6 |
| rev | +24 | 66 / 0.916 | **46** / 0.916 | 44 |
| rev | −24 | 1 / 0.967 | **0** / 0.998 | 81 |
| rev | +20 | 40 / 0.967 | **31** / 0.953 | 43 |
| rev | −20 | 0 / 1.000 | 0 / 0.999 | 15 |
| rev | +14 | 0 / 1.000 | 0 / 0.999 | 6 |
| rev | −14 | 0 / 1.000 | 0 / 1.000 | 0 |

**Result:**
- **Minimum up 0.916 with B, the same as before.**
- Runs with any wheel over terrain: 12 with B against 15 before.
- **Every run has the same or fewer drop samples.**
- Lower "up" values come only from kerb contacts, plus one case at ±20: 0.953 against 0.967, where one wheel is over
  terrain while another is on a kerb.
- 25 samples at fwd −24 / rev +24 touch a building corner in both states. That is an artefact of offsetting the harness
  path by 24 studs in the offline model.

**How to read this.** The offline model is a stricter, static proxy. On today's geometry it still finds wheel drops
in runs where the Studio pilot had **72 runs, 0 flips, min up 0.71**
(docs/test_results/shoulders_pilot_after.txt). So it can show "B is not worse than today", but it cannot show "no
flips". Spot 1 (25250, 13430) is outside the pilot area, so B does not change it and its Studio result stands.

**The final proof needs the same 72 physics drives in Studio after an approved build.**

## 7. Studio acceptance (later, after approval) and the approval request

**Procedure:** spec §9 has every command and its expected output. In short:
1. Save the place and confirm the version-history entry.
2. Put in the builder and the 10 data modules.
3. `RV.Plan()`: it must say `MATCHES the data` (804). If it does not, stop.
4. `RV.Build()`: 10 cells, 1,935 parts.
5. `RV.MoveReplaced()`: 804 moved.
6. `RV.Probe()`: 0 drops at every offset, kerb contacts about 3 / 15 / 20.
7. Captures from the owner's camera with Studio focused.
8. Play mode, physics:
   - The shoulder harness: 2 spots × 2 directions × ±24 / ±20 / ±14 × 100 / 150 / 200. Pass: 0 flips, min up ≥ 0.71
     (the current Studio result).
   - Every open direction of the junction on every lane.
9. GPS route through the junction, traffic loops for 2 minutes, a Street Challenge with checkpoints in the junction.
10. Frame times with Studio focused.
11. Rollback rehearsal: `Remove()` gives 804 of 804, then `Build()` again if the owner keeps it.

**Approval request (exact wording for the owner):**

> I approve a Studio PILOT BUILD of Road B at the Sukhumvit / Pattaya Klang junction (world x 24220..24820,
> z 650..1250) on a freshly saved place version, with the default Parts build (1,935 parts in 10 Atomic cells). 804 old
> road parts in that area are moved, not deleted, to ServerStorage.RoadVisBackup. The road graph, GPS, traffic data,
> physics and the shoulder pilot (ShoulderChunks) stay unchanged, and the optional shoulder recolour is NOT applied.
> Acceptance needs: 0 flips in the 72 shoulder-harness physics drives (min up ≥ 0.71), Probe 0 drops, and captures from
> my screenshot camera with Studio focused. Any failure means RV.Remove() (804/804 restored). Mesh assets are not
> approved.
