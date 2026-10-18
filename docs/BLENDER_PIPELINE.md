# Blender asset pipeline (VIS-1 + VIS-2)

Branch `team6/vis-blender`. Status: **generated, validated and QA-rendered on the GPU box. Not uploaded, not
imported.** Uploading needs the owner (Studio 3D Importer or an Open Cloud API key), so nothing here has been seen in
Roblox yet.

What it makes: 43 low-poly, reusable `.glb` assets in three families.

- **A, buildings: a modular KIT, not whole buildings.** Ground-floor fronts, mid-floor fronts, tops, corners and roof
  items, all on the city's own grid, so the slice team can dress any `buildings_game.json` box.
- **B, roadside props.**
- **C, racing venue pieces.**

Every number in this document comes from `validate.py`, which reads the exported GLBs. The full output is in
`docs/images/vis_assets/manifest.json`.

## Run it

Blender is not installed locally. Everything runs headless on the GPU box: Blender 5.2.2 LTS at
`/root/w/blender/blender`, ssh alias `vast-rtx6000-1`.

```
bash tools/blender/run_remote.sh                 # Git Bash / Linux
powershell -ExecutionPolicy Bypass -File tools\blender\run_remote.ps1   # Windows PowerShell (tar via temp file + scp)
```

The scripts do these steps:

1. Push `tools/blender/` to the box (nothing else goes over: no `.env`, no keys).
2. On the box, run `remote_job.sh` under `/root/robloxrace/vis`.
3. Fetch the results into `build/vis_assets/`, which is gitignored.

`remote_job.sh` runs the steps below. Every Blender call goes through
`bash /root/kit/fleet/gslot.sh -- …` with `--python-exit-code 1`. It never uses `pkill`.

| step | command (on the box, cwd `/root/robloxrace/vis`) | last run |
|---|---|---|
| gen_buildings | `blender -b --factory-startup -P tools/blender/gen_buildings.py -- --out out/run` | 1.0 s, 24 assets |
| gen_roadside | `… gen_roadside.py -- --out out/run` | 0.9 s, 14 assets |
| gen_racing | `… gen_racing.py -- --out out/run` | 0.8 s, 5 assets |
| validate | `python3 tools/blender/validate.py out/run` (pure Python, also runs locally) | 0.1 s, 43/43 OK |
| qa_render | `blender -b … -P tools/blender/qa_render.py -- out/run out/run/qa` | 3.9 s, 5 PNGs |
| shrink_qa | `python3 tools/blender/shrink_qa.py out/run/qa out/run/qa_small` | 0.7 s |

Notes on running:

- Run a single asset with `-- --out DIR --only ShophouseShutter`.
- `validate.py build/vis_assets` re-checks the fetched files locally. On this run it gave the same summary.
- After a run, regenerate the Luau template with `python tools/blender/make_luau_manifest.py`.

Outputs, in `build/vis_assets/` (not committed):

- `{buildings,roadside,racing}/*.glb`
- `meta/*.json`: generator facts per asset
- `manifest.json`
- `qa/*.png`, plus `qa_small/*.jpg`, which are copied to `docs/images/vis_assets/`
- `logs/*.log` and `logs/timings.txt`

## Files

| file | role |
|---|---|
| `tools/blender/common/units.py` | scale + grid constants, triangle/material limits (pure Python) |
| `common/materials.py` | the shared material list (18 names, `MP_*`), created as Principled BSDF |
| `common/mesh.py` | bmesh `Builder`: box, oriented box, beam, cylinder/cone, swept tube, quad with forced normal, alpha card, UV 0..1 panel |
| `common/facade.py` | kit helpers: wall face with window holes + reveals, fills, front boxes, railings |
| `common/optimize.py` | merge by distance → dissolve degenerate → limited dissolve (planar, not across materials / cards) → triangulate → sharp edges from angle |
| `common/uv.py` | box-projected UVs in world studs (1 UV = 8 studs) except cards / sign panels (0..1) |
| `common/naming.py` | naming rule (also used by validate.py) |
| `export.py` | asset → origin rule → optimise → split per material → `.glb` + `meta/<name>.json` |
| `gen_buildings.py`, `gen_roadside.py`, `gen_racing.py` | the three families (parametric functions, one per asset) |
| `validate.py` | reads the GLB JSON + binary chunks, checks everything, writes `manifest.json` |
| `qa_render.py` | contact sheet per family (re-imported from the GLBs), kit assembly (Workbench) + night assembly (EEVEE) |
| `shrink_qa.py` | commit-sized JPEGs |
| `run_remote.sh`, `run_remote.ps1`, `remote_job.sh` | local → box → local |
| `make_luau_manifest.py` → `import_manifest.luau` | asset name → asset id template with the expected sizes / tris |
| `validate_import.luau`, `apply_import_settings.luau` | Studio-side settings + checks after the import |

## Conventions

**Units.** Assets are modelled directly in studs, so 1 glTF unit = 1 stud. The city scale is not uniform
(`tools/mapgen` config: 0.28 m per stud, ×0.5 horizontal compression, ×0.75 vertical scale), so:

| what | rule | studs |
|---|---|---|
| kit module width | 4 m × 0.5 / 0.28 | **7.143** |
| mid floor | 3.2 m × 0.75 / 0.28 (= `buildings_game.json` `level_studs`) | **8.571** |
| ground floor | floor + `ground_floor_extra_studs` 3 | **11.571** |
| parapet | 1.2 m vertical | 3.214 (+0.3 coping) |
| props (lights, palms, benches, racing items) | 1 m = 0.75 / 0.28 on **all** axes (not compressed) | 9 m pole ≈ 24 |

A box with `levels` L has height `L × 8.571 + 3`. That is exactly one ground row plus (L−1) mid rows, and the top
row stands on the roof.

To cover an edge of length E:

- Use n = round(E / 7.143) modules and scale the row in X by E / (n × 7.143). That stays within about ±7 % for n ≥ 7.
- Typical edges: a 4 m × 12 m shophouse is 1 module × 3 deep. A 20–40 m tower is 5–10 modules. A 15–30 m commercial
  front is 4–7 modules, or the one-mesh `GF_Commercial7Bay`.

**Axes.** Blender is Z-up, and the exporter writes glTF Y-up (`export_yup`). The resulting axes match Roblox:

- X is right, Y is up.
- The **front** (street side, lamp arm, sign face, lens) faces **−Z**, which is the Front face of a Roblox part.

**Origins (anchor in the manifest).**

- `base`: bbox base centre.
- `pole`: the pole or trunk foot is at the origin. Used for the single-arm light, the signal mast, the barrier and
  the palms, so a collider Part or a map point lines up with the pole.
- `mount`: kit modules (GF/MF/TP, garage facade, pit box). The origin is the bottom centre of the mount plane, which
  is the face that sits on the building box. The module lies entirely at local z ≤ 0, so modules placed edge to edge
  at `x = (i + ½) × 7.143` on the box face snap together. The back, sides and top/bottom are left open (the box
  behind covers them). Top modules close their back because it is seen from the roof.
- `corner`: the origin is on the building-box corner, and the building interior is at local x < 0, z > 0. Rotate
  the piece 90° per corner. It overlaps the module ends by 0.9 studs.

**Materials and parts.**

- Each asset uses at most 4 materials, all from the shared list:
  - `MP_Wall`, `MP_WallAccent`, `MP_Glass`, `MP_Metal`, `MP_MetalDark`, `MP_Shutter`
  - `MP_Awning`, `MP_Signboard`, `MP_NeonCyan`, `MP_NeonMagenta`, `MP_LampWarm`, `MP_SignalLens`
  - `MP_Foliage`, `MP_Bark`, `MP_Wood`, `MP_Concrete`, `MP_Stripe`, `MP_Rubber`
- Each material becomes **one child mesh** under the asset root, so it imports as one MeshPart with one material. The
  child is named `<Asset>_<Short>`, e.g. `BLD_GF_ShophouseShutter_Wall`. Each part can then be tinted on its own
  (MeshPart.Color / SurfaceAppearance) from the city palettes.
- No textures are embedded; only glTF `baseColorFactor` is used. UVs are present for later textures.
- Sign boards are plain `MP_Signboard` panels with UV 0..1. No brands and no logos.

**Naming.** Assets follow `^(BLD|RSD|RAC)_<Group>_<Variant>$`. The groups are:

- BLD: GF, MF, TP, CN, RF
- RSD: Light, Signal, Pole, Sign, Shelter, Barrier, Bench, Rail, Palm, Awning
- RAC: Garage, Gantry, Guardrail, Pit, Banner

Names never end in `_Att`, `_InnerCage` or `_OuterCage`, because the importer turns those into other instance types.

**Geometry rules** (all checked by `validate.py`):

- At most 10,000 triangles per asset, which is the project budget. The largest asset is `BLD_GF_Commercial7Bay` at 512.
- At most 20,000 triangles per MeshPart (Roblox hard limit).
- Triangles only, with normals and UVs.
- Identity node transforms.
- No 0-thickness part: a flat sheet (glass fill, sign panel, flat roof) gets a 0.05-stud shell, because Roblox rejects
  0-thickness meshes.
- Palm fronds are two-sided cards (real back faces, `doubleSided` false) with UV 0..1, ready for an alpha frond
  texture.

## Roblox limits used (researched 2026-10-19)

| fact | source |
|---|---|
| "Individual meshes can not exceed 20,000 triangles"; meshes "cannot be 0 thickness"; quads where possible; watertight (we build front shells on boxes; see risks) | Creator Docs, Mesh specifications: https://create.roblox.com/docs/art/modeling/specifications |
| Importer formats .fbx / .obj / .gltf. Settings: Import Only As Model, Upload to Roblox, Add to Workspace, Set Pivot to Scene Origin (default on), Anchored (default off), World Forward = Front / World Up = Top, **Scale Unit (default Studs)**, **Merge Meshes (default off)**, Invert Negative Faces, per-object Make Double Sided, Use Imported Pivot | Creator Docs, 3D Importer: https://create.roblox.com/docs/art/modeling/3d-importer |
| Blender → Studio: set Scale Unit to Stud; glTF "do not require these additional scaling configurations" (FBX needs Apply Scalings = FBX Unit Scale); Studio is Y-up; export Z forward / Y up | Creator Docs, Blender guide: https://create.roblox.com/docs/en-us/art/blender.md |
| up to 4096×4096 textures (the UV page says 1024×1024 for maps), PBR maps albedo/normal (OpenGL)/roughness/metalness/emissive mask | Creator Docs, Texture specifications: https://create.roblox.com/docs/art/modeling/texture-specifications |
| CollisionFidelity: Default, Hull, Box, PreciseConvexDecomposition, Tunable | https://create.roblox.com/docs/reference/engine/enums/CollisionFidelity |
| `TriangleMeshPart.MeshSize` (Vector3, read only), `CollisionFidelity` (scriptable) | https://create.roblox.com/docs/reference/engine/classes/TriangleMeshPart |
| `AssetService:CreateEditableMeshAsync(content)` (yields, AssetRead) and `EditableMesh:GetFaces()` give a triangle count from a script | https://create.roblox.com/docs/reference/engine/classes/AssetService, …/classes/EditableMesh |
| Open Cloud Assets API: `POST https://apis.roblox.com/assets/v1/assets`, asset type Model accepts `model/gltf-binary` (.glb), ≤ 20 MB per call, poll `operations/{id}` for the `assetId`; Mesh-type uploads only accept Roblox-sourced content; key needs asset write permission | https://create.roblox.com/docs/cloud/guides/usage-assets |

Not confirmed in the docs:

- How the importer treats a glTF node hierarchy (root empty plus children). We expect a Model named after the root,
  with one MeshPart per child.
- Whether `baseColorFactor` becomes MeshPart.Color or a SurfaceAppearance.

The first import has to confirm both. `validate_import.luau` searches at any depth, so it works either way.

## Asset list (from `manifest.json`, 2026-10-19 run)

43 assets / 129 MeshParts / **5,789 triangles in total**; the largest asset is 512 (`BLD_GF_Commercial7Bay`, 7 modules). Sizes are in studs (X × Y × Z, Roblox
axes). "(collide)" means CanCollide is recommended on the mesh. All other props keep CanCollide off on the mesh and
use a simple Part collider for the pole or trunk, as the builder already does.

### A. Building kit (24)

| asset | anchor | tris | parts | size | collision |
|---|---|---|---|---|---|
| `BLD_GF_ShophouseShutter` (roller shutter half down, metal awning, sign slot) | mount | 108 | 4 | 7.14 x 11.57 x 3.95 | Box |
| `BLD_GF_ShophouseAwning` (open shopfront, fabric awning, sign slot) | mount | 88 | 4 | 7.14 x 11.57 x 4.30 | Box |
| `BLD_GF_Restaurant` (glazing, canopy, planters, sign slot) | mount | 150 | 4 | 7.14 x 11.57 x 3.35 | Box |
| `BLD_GF_CommercialBay` (1 bay) | mount | 82 | 4 | 7.14 x 11.57 x 0.95 | Box |
| `BLD_GF_Commercial7Bay` (7-bay front, one mesh) | mount | 512 | 4 | 50.00 x 11.57 x 3.75 | Box |
| `BLD_GF_HotelLobby` (2 modules, drop-off canopy, cyan LED) | mount | 110 | 4 | 14.29 x 11.57 x 7.65 | Box |
| `BLD_MF_PunchedTwin` | mount | 98 | 3 | 7.14 x 8.57 x 0.85 | Box |
| `BLD_MF_PunchedAC` (window + AC condenser) | mount | 110 | 4 | 7.14 x 8.57 x 1.75 | Box |
| `BLD_MF_ShophouseUpper` (grilles, cornice) | mount | 132 | 4 | 7.14 x 8.57 x 1.00 | Box |
| `BLD_MF_BalconyRow` (solid parapet) | mount | 61 | 3 | 7.14 x 8.57 x 3.80 | Box |
| `BLD_MF_CondoBalcony` (railing) | mount | 150 | 4 | 7.14 x 8.57 x 4.15 | Box |
| `BLD_MF_CurtainWall` | mount | 48 | 3 | 7.14 x 8.57 x 0.40 | Box |
| `BLD_MF_CurtainWallNeon` (magenta LED fin) | mount | 44 | 4 | 7.14 x 8.57 x 1.00 | Box |
| `BLD_TP_Parapet` | mount | 22 | 2 | 7.14 x 3.51 x 1.05 | Box |
| `BLD_TP_CorniceNeon` (cyan LED line) | mount | 38 | 3 | 7.14 x 4.51 x 1.80 | Box |
| `BLD_TP_CrownFin` (2-floor tower crown) | mount | 74 | 4 | 7.14 x 17.14 x 2.35 | Box |
| `BLD_CN_Ground` | corner | 4 | 1 | 1.88 x 11.57 x 1.88 | Box |
| `BLD_CN_Mid` | corner | 4 | 1 | 1.88 x 8.57 x 1.88 | Box |
| `BLD_CN_Top` | corner | 12 | 1 | 2.13 x 3.51 x 2.13 | Box |
| `BLD_CN_GlassMid` | corner | 36 | 2 | 1.88 x 8.57 x 1.93 | Box |
| `BLD_RF_PlantRoom` | base | 118 | 4 | 12.80 x 9.07 x 9.80 | Box |
| `BLD_RF_ACUnits` | base | 162 | 3 | 8.40 x 2.30 x 3.20 | Box |
| `BLD_RF_WaterTank` | base | 200 | 3 | 4.70 x 8.30 x 4.70 | Hull |
| `BLD_RF_SignFrame` (rooftop board, magenta neon border) | base | 144 | 3 | 21.40 x 12.06 x 2.73 | Box |

### B. Roadside (14)

| asset | anchor | tris | parts | size | collision |
|---|---|---|---|---|---|
| `RSD_Light_DoubleArm` (10 m, median) | base | 246 | 3 | 2.68 x 26.21 x 12.59 | Box, pole collider |
| `RSD_Light_SingleArm` (8 m, arm toward −Z) | pole | 134 | 3 | 2.14 x 20.96 x 6.29 | Box, pole collider |
| `RSD_Signal_Housing` (3 lenses, visors, backplate) | base | 140 | 3 | 2.10 x 4.60 x 1.80 | Box |
| `RSD_Signal_Mast` (6.5 m, 5 m arm, 2 heads) | pole | 316 | 4 | 14.75 x 17.41 x 2.85 | Box, pole collider |
| `RSD_Pole_Utility` (concrete, 2 crossarms, cable coils) | base | 294 | 3 | 6.43 x 24.11 x 1.80 | Box, pole collider |
| `RSD_Sign_Post` (blank board) | base | 44 | 2 | 3.21 x 7.50 x 0.49 | Box |
| `RSD_Shelter_Bus` (blank ad panel) | base | 96 | 4 | 10.71 x 7.31 x 4.69 | PreciseConvexDecomposition (collide) |
| `RSD_Barrier_Parking` (boom along +X) | pole | 104 | 3 | 11.90 x 2.83 x 1.14 | Box (collide) |
| `RSD_Bench_Park` | base | 96 | 2 | 4.82 x 2.46 x 1.28 | Box (collide) |
| `RSD_Rail_Beach` (tile every 6.70) | base | 90 | 2 | 6.70 x 2.68 x 0.70 | Box (collide) |
| `RSD_Palm_A` (8 m, 9 fronds) | pole | 286 | 2 | 19.71 x 22.75 x 16.75 | Box, trunk collider |
| `RSD_Palm_B` (10 m, 11 fronds, leaning) | pole | 306 | 2 | 17.38 x 28.09 x 21.41 | Box, trunk collider |
| `RSD_Palm_C` (6 m, 7 fronds) | pole | 258 | 2 | 16.68 x 16.79 x 15.07 | Box, trunk collider |
| `RSD_Awning_Shop` (3 m) | base | 52 | 2 | 8.04 x 2.71 x 5.41 | Box |

### C. Racing (5)

| asset | anchor | tris | parts | size | collision |
|---|---|---|---|---|---|
| `RAC_Garage_Facade` (roll-up door, number slot; tile along X) | mount | 116 | 4 | 16.07 x 13.39 x 1.20 | Box (collide) |
| `RAC_Gantry_Start` (14 m span, 7 m clearance, 5 lights, blank banner) | base | 490 | 3 | 41.90 x 22.55 x 2.90 | PreciseConvexDecomposition (collide) |
| `RAC_Guardrail_Segment` (W-beam, tile every 10.71) | base | 82 | 2 | 10.71 x 2.24 x 1.20 | Box (collide) |
| `RAC_Pit_BoxFront` (snaps in front of the garage facade) | mount | 80 | 4 | 16.07 x 10.00 x 8.05 | PreciseConvexDecomposition (collide) |
| `RAC_Banner_Frame` (blank both faces) | base | 52 | 3 | 17.87 x 8.34 x 3.20 | Box (collide) |

QA images, re-imported from the GLBs on the box, are in `docs/images/vis_assets/`:

- `buildings_sheet.jpg`, `roadside_sheet.jpg`, `racing_sheet.jpg`
- `kit_assembly.jpg`: a shophouse row (4 modules × G+3 + parapet), a 4 × 3-module hotel tower (lobby, 12 floors of
  condo balcony / curtain wall with LED fin, crown) and a 7-bay commercial block, built only from kit modules on the
  grid, on grey boxes.
- `kit_assembly_night.jpg`: the same assembly in EEVEE at night.

The assemblies show modules, corners and tops snapping with no gaps.

## Roblox import procedure (owner / leader; not done)

Mesh assets have to be uploaded under the owner's account. There are two routes.

### Route 1: Studio 3D Importer (recommended for the first batch)

1. Copy `build/vis_assets/{buildings,roadside,racing}/*.glb` to the Studio machine, or re-run `run_remote.*`.
2. In Studio, choose **File → Import 3D** (Avatar tab → Import 3D, or the Home tab, depending on the Studio version).
   Select one family's `.glb` files; multi-select is allowed.
3. Settings for every file:
   - **File Geometry → Scale Unit: Studs.** The files already hold studs, so do not choose Meters.
   - **Merge Meshes: off.** Keep one MeshPart per material, so the named parts survive.
   - **File Transform → World Forward: Front, World Up: Top.** These are the defaults; the files are already Y-up with
     the front toward −Z.
   - **Set Pivot to Scene Origin: on** (default). This keeps the exported origin rule.
   - **Anchored: on.**
   - **Import Only As Model: on**, **Upload to Roblox: on**, **Add to Workspace: on**.
   - **Make Double Sided: off.** Fronds and sheets are already two-sided geometry.
   - **Invert Negative Faces: off.**
   - Creator: the owner's account or group that owns the experience.
4. Check the importer preview. It should show no errors. A warning about no textures is fine.
5. Move the imported Models to **`ServerStorage.VisAssets`**, keeping one folder per family if wanted.
6. Run **`tools/blender/apply_import_settings.luau`** in the Command Bar. It sets the following from the manifest:
   - **CollisionFidelity** per family: kit modules and roof items Box, water tank Hull, bus shelter / gantry / pit box
     PreciseConvexDecomposition, everything else Box.
   - CanCollide, CanQuery and CanTouch.
   - Anchored on.
   - CastShadow off on neon/lamp parts.
   CollisionFidelity is not an importer setting, so it has to be set here.
7. Copy `tools/blender/import_manifest.luau` into a ModuleScript **`ServerStorage.VisAssetsManifest`**. Fill each
   `modelId` from Asset Manager → Models → Copy Asset ID. The `size`/`tris` fields are already filled from the
   validated GLBs.
8. Run **`tools/blender/validate_import.luau`** in the Command Bar and paste its output back to the team.

Expected instances: a Model `BLD_GF_ShophouseShutter` containing MeshParts `BLD_GF_ShophouseShutter_Wall`, `_Glass`,
`_Shutter` and `_Sign`. The general pattern is `<Asset>_<Short>`, where Short is one of Wall, Accent, Glass, Metal,
Steel, Shutter, Awning, Sign, NeonC, NeonM, Lamp, Lens, Leaf, Bark, Wood, Concrete, Stripe or Rubber. If the importer
adds an extra Model level for the file, the check still finds the parts.

### Route 2: Open Cloud (bulk)

1. The owner creates an API key with asset write permission.
2. `POST https://apis.roblox.com/assets/v1/assets` with assetType `Model` and content type `model/gltf-binary`, one
   request per `.glb`.
3. Poll `GET /assets/v1/operations/{id}` until `done`, then read `response.assetId` and put it in
   `import_manifest.luau`.

This is not scripted here: the key must stay with the owner and must not go to the GPU box.

**What `validate_import.luau` checks:**

- Every part exists and is a MeshPart.
- `MeshPart.MeshSize` equals the GLB part bbox within ±0.05 studs. All sizes 3.57× too large means the file was read
  as metres. Swapped axes mean wrong World Up/Forward.
- `Size == MeshSize` (the part was not rescaled).
- Model extents match the manifest size within ±0.1.
- The lowest point is at the pivot's Y (the origin rule survived).
- CollisionFidelity matches the recommendation, and the part is Anchored.
- Triangle count per MeshPart, via `AssetService:CreateEditableMeshAsync(Content.fromUri(MeshId))` and `#GetFaces()`.
  This only works if EditableMesh may load the asset (the experience owns it); otherwise it prints `n/a`. Roblox may
  also re-split vertices, but the face count should equal the triangle count.

**What it cannot check:** colours/materials as rendered, normals and shading, UV layout, and the look at night. Those
need an eye check by the owner.

## What is NOT done

- **Upload and import.** The owner has to do this (Studio account or API key). No asset ids exist yet, so every
  `modelId = 0`.
- No textures, no SurfaceAppearance, no alpha frond texture. UVs are ready: fronds and sign panels are 0..1, the rest
  are box-projected at 8 studs per tile.
- No placement. Nothing places these assets in the world: there is no PattayaBuilder change and no change to road data
  or the Studio place. The slice team assembles modules on `buildings_game.json` boxes using the grid above.
- No LOD variants and no collision proxy meshes. Colliders are the existing Part pattern or the fidelity settings.
- The night look is only an EEVEE approximation in `kit_assembly_night.jpg`, not Roblox lighting.

## Risks

- **glTF unit interpretation.** If the importer reads glTF as metres despite Scale Unit = Studs, assets come in 3.57×
  too large. `validate_import.luau` catches this at once; re-import with the right Scale Unit rather than resizing.
- **Hierarchy and colour mapping** (root empty plus children, `baseColorFactor`) are not documented. If colours are
  lost, tint by MeshPart.Color from the material name in the manifest (Short suffix).
- **Front shells, not watertight.** Kit modules are open shells meant to sit on a building box. Roblox's spec asks
  for watertight meshes. Whether the importer only warns or refuses them is not documented. If it refuses, add back,
  side and top faces in `common/facade.py` `wall()`, at a few triangles per module.
- **Draw calls and instance count.** Each asset is 1–4 MeshParts. A 4 × 13-floor tower built from modules is about
  4 × 4 × 14 modules × about 3.5 parts, roughly 800 MeshParts (the same mesh ids, so instancing helps, but it is still
  many instances). For mobile (30 FPS), dress only near-road faces, use plain boxes plus facade textures far away
  (the existing PattayaLOD), or bake a building row into one mesh later.
- **Visual richness.** The assets are deliberately low-poly (4–512 triangles). Richness has to come from textures,
  neon and lighting (Phase 7) more than from geometry.
- **Box-only geometry checks.** Asset sizes match the city grid by construction, but no asset has been seen next to a
  real car or character in Roblox. The prop scale (2.68 studs/m) is close to the builder's existing parts (lights
  20 studs, palms 26–34 studs); check it by eye after import.
