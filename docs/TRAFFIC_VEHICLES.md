# Traffic vehicles (team9, branch `team9/traffic-vehicles`, 2026-10-19)

Owner review item 9: the ambient traffic cars were box-shaped. This branch adds real Pattaya street vehicles as
meshes. Pooling, movement, the single collision box, the ghost rule and near misses are unchanged, and the box car
is still there as the fallback.

**Status: generated, validated and QA-rendered on the GPU box. Not uploaded, and not seen in Studio.**

## Vehicles

All seven are made by `tools/blender/gen_traffic.py`. Sizes are in studs, X × Y × Z in Roblox axes (front −Z). The
box is the client's collision Body for that traffic kind.

| asset | traffic kind (box W × L) | weight | tris | MeshParts | mesh size | notes |
|---|---|---|---|---|---|---|
| `TRF_Car_Sedan` | 0 (6.6 × 14) | 0.38 | 644 | 4 | 6.60 × 5.42 × 14.24 | 30 % are taxis: taxi palette plus a yellow Neon roof-sign Part |
| `TRF_Car_Hatch` | 0 | 0.27 | 624 | 4 | 6.60 × 5.70 × 13.64 | hatchback / eco-car |
| `TRF_Scooter_Pair` | 0 | 0.22 | 1,008 | 4 | 5.23 × 6.85 × 12.77 | two scooters with seated riders, staggered across the lane |
| `TRF_TukTuk_Std` | 0 | 0.13 | 792 | 4 | 5.90 × 7.08 × 12.45 | one front wheel, rear bench, canopy on poles |
| `TRF_Songthaew_Std` | 1 (7 × 16) | 0.75 | 1,016 | 4 | 7.24 × 8.29 × 16.20 | baht bus: pickup with a covered rear cabin, two benches, open back with a step, roof rails |
| `TRF_Pickup_Std` | 1 | 0.25 | 700 | 4 | 7.24 × 6.60 × 16.20 | single cab, open bed |
| `TRF_Van_Std` | 2 (7.2 × 16) | 1.0 | 664 | 4 | 7.44 × 7.75 × 16.30 | one-box minivan. A city bus does not fit a 16-stud box, and changing the route data's kinds was out of scope. |

Notes on the table:

- The route data (`tools/mapgen/traffic.py`) only has kinds 0, 1 and 2. Each kind therefore has variants, picked by
  weight when a pooled model is first made.
- Each pool stays per kind. A pooled model keeps its variant and colour, the same way the box car kept its colour.
- Overhang past the box is limited to mirrors and bumpers: at most +0.12 per side in X and +0.15 per end in Z.
  `validate_traffic.py` fails any mesh that sticks out more than 0.45 in X or 0.3 in Z.

### MeshParts

Each vehicle has 4 MeshParts, named `<Asset>_<Short>`:

| part | contents | client setting |
|---|---|---|
| `Paint` | the body | coloured by the client from `TrafficVehicles.PALETTES`: car, taxi, pickup, songthaew (Pattaya blue ×2, light blue, white, red), tuktuk, scooter, van |
| `Dark` | glass, tyres, bumpers, grille, mirrors, seats, rails, riders | SmoothPlastic (28, 31, 38) |
| `Head` | head lamps | Neon (255, 250, 220) |
| `Tail` | tail lamps | Neon (230, 20, 20) |

This differs from the "Paint / Glass / Trim / Lights" split in the brief. A MeshPart has one colour, so head (white)
and tail (red) lamps cannot share one part. Tinted glass and black trim read the same at night, so they share `Dark`.

Head and Tail carry the attribute `TrafficLamp = "Head"` / `"Tail"`. They are Neon all the time, as the box car's
lamp Parts were. `PattayaNightLights` was not changed; it lights only `RaceCar` / `RivalBot` models. A later night
pass can find the lamps by that attribute or by the `_Head` / `_Tail` name suffix.

### Asset conventions

These follow docs/BLENDER_PIPELINE.md:

- 1 unit = 1 stud. glTF is Y-up, with the front toward −Z.
- The origin is the **footprint centre at road level**: wheel bottoms are at y = 0. This is the `pole` anchor, not
  the bbox centre, so asymmetric mirrors or steps do not shift the mesh against the collider.
- Every piece is a closed solid (box, cylinder, capped loft) because Studio may draw the winding reversed. The
  `34flip` QA panel shows every vehicle still reads with the winding reversed. The kit's shared files are not edited:
  - `traffic/trf_common.py` adds four car materials (`MP_CarPaint`, `MP_CarDark`, `MP_CarHead`, `MP_CarTail`) to
    the shared material dict at run time.
  - It also supplies a `TRF_<Group>_<Variant>` naming rule, patched into `export.py` / `validate.py` only while the
    traffic scripts run.

## Files

| file | role |
|---|---|
| `tools/blender/gen_traffic.py` | generator. Its helpers: lofted body sections, chamfered-rect greenhouse lofts, ellipsoids, rider |
| `tools/blender/traffic/trf_common.py` | car materials, naming rule, `KIND_BOX` footprints, budgets (2,500 tris, 4 MeshParts) |
| `tools/blender/traffic/validate_traffic.py` | the `validate.py` checks plus the traffic rules. Writes `build/vis_assets/traffic/manifest.json`, separate from the main manifest |
| `tools/blender/traffic/qa_traffic.py` | reuses `qa_render.py`: front / 3/4 / back / 3/4 winding-reversed views, a line-up inside the green collider wire boxes, and an EEVEE night line-up |
| `tools/blender/traffic/run_traffic.sh`, `remote_traffic.sh` | local → GPU box → local. The box work dir is `/root/robloxrace/vis/team9traffic`, so other teams' `tools/blender` and `out/` are untouched. Blender runs through `gslot.sh`. Only `tools/blender` is sent. |
| `tools/blender/traffic/make_traffic_luau.py` | manifest → the generated `ASSETS` block of `TrafficVehicles.luau`, keeping any `assetId` already filled in |
| `tools/blender/traffic/install_templates.luau` | Studio command-bar install (below) |
| `roblox/src/ReplicatedStorage/TrafficVehicles.luau` | asset table, variants, palettes, template lookup, `build(kind, root, lift, model)` |
| `roblox/src/StarterPlayer/StarterPlayerScripts/PattayaTraffic.client.luau` | `makeCar` tries the meshes first and falls back to the box car |

To run the pipeline:

```
bash tools/blender/traffic/run_traffic.sh
python tools/blender/traffic/make_traffic_luau.py
```

Outputs go to `build/vis_assets/traffic/` (gitignored):

- `*.glb`
- `meta/*.json`
- `manifest.json`
- `qa/TRF_*_views.jpg`, `qa/traffic_lineup.png`, `qa/traffic_night.png`
- `logs/`

## Client behaviour

`makeCar(kind)` creates the Body Part exactly as before: same size, anchored, CanCollide, CanQuery and CanTouch off,
and the same Lift / HalfLen / HalfWid attributes. Then `TrafficVehicles.build` runs:

1. It picks a variant of the kind by weight, but only among variants whose template exists in
   `ReplicatedStorage.TrafficVehicleTemplates` and whose MeshPart sizes match the manifest within 0.1.
2. It clones those MeshParts into the car Model:
   - CFrame = `Body.CFrame * (0, −Lift, 0) * manifest centre * IMPORT_YAW`
   - unanchored, massless, CanCollide / CanQuery / CanTouch off, CastShadow off
   - welded to the Body with a WeldConstraint, as the box car's parts were
3. It sets the Body's Transparency to 1.

`BulkMoveTo` of the Body moves everything, as before. `setGhost` fades all BaseParts of the model, so it covers the
meshes too.

**Fallback:** the box car is built by the old, unchanged code when any of these holds:

- the module is missing or errors (loaded with `pcall`);
- there is no template folder;
- no usable variant exists for the kind;
- `build` errors (any half-built parts are removed).

A broken template (missing part or wrong size) prints one warning and is skipped.

Costs:

- Pool size (70), radius (650) and the Heartbeat loop are unchanged.
- No per-frame work or allocations were added. Templates are looked up only when a pooled model is first made.
- A mesh car is 4–5 instances plus welds; a box car was 11–13 Parts.

**IMPORT_YAW:** Roblox's glTF importer bakes a 180° yaw into every mesh (measured by the leader). The client turns
each clone back, as `VisMeshBuilder` does. The templates' own position and rotation are ignored, so nothing has to
be baked or moved after import.

## Upload and install (leader)

Upload the seven files in `build/vis_assets/traffic/`:

- `TRF_Car_Sedan.glb`
- `TRF_Car_Hatch.glb`
- `TRF_Scooter_Pair.glb`
- `TRF_TukTuk_Std.glb`
- `TRF_Songthaew_Std.glb`
- `TRF_Pickup_Std.glb`
- `TRF_Van_Std.glb`

Use the same importer settings as the kit: Scale Unit Studs, Merge Meshes off, Set Pivot to Scene Origin on, Make
Double Sided off, Invert Negative Faces off.

Then:

1. Put the Model ids in `TrafficVehicles.ASSETS.<name>.assetId`, or in `ASSET_IDS` at the top of
   `install_templates.luau`. If you imported straight into Workspace, leave the ids at 0.
2. In Edit mode, paste `tools/blender/traffic/install_templates.luau` into the Command Bar and run it. For each
   asset it:
   - calls `LoadAsset` on the id, or takes the `TRF_*` Model already in Workspace;
   - finds the Model that holds the `<name>_Paint`… parts, even if the importer added a wrapper level;
   - moves it to `ReplicatedStorage.TrafficVehicleTemplates.<name>`;
   - sets the template parts Anchored, CanCollide / CanQuery / CanTouch off;
   - prints `Paint ok, Dark ok, Head ok, Tail ok`, or the size mismatch.

   It reads the module from a clone, to avoid the command bar's `require` cache.
3. Save the place, then Play. Traffic should show the vehicles. Remove or rename the folder to get the box cars back.

## Not verified

Nothing here has been seen in Studio or in a live game. These checks are still open:

- The importer's 180° yaw on these files. If cars drive backwards, set `IMPORT_YAW` to `CFrame.identity`.
- Part names and hierarchy after import.
- MeshPart sizes matching the manifest.
- How Neon lamps and the smooth-shaded lofts look under the game's lighting.
- Whether the weld / `BulkMoveTo` behaviour with MeshParts matches the old Parts. It should, since it is the same
  pattern.

Other limits:

- The EEVEE night render does not show the lamp emission. The glTF emissive was not picked up on re-import; in
  Roblox the client sets the lamps to Neon.
- The Luau compiles with `luau-compile` and passes `luau-analyze` (Roblox globals aside). `build` was exercised with
  mocked Instances, including no folder, partial templates and a wrong size, but not in Roblox.
- Taxis are one colour plus a roof sign. Two-tone taxis would need a fifth MeshPart.
