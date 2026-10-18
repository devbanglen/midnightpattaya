# Visual performance — VIS-4 slice budget and measurement protocol

Team vis-slice, 2026-10-19. Status: **written, not built or measured in Studio**. The slice numbers below come from
the exporter (`build/vis_slice/vis_slice.json`). The leader takes FPS and memory with the protocol in section 3.

## 1. Baseline (copied from docs/PERFORMANCE_BUDGET.md)
**2026-10-18, central slice only.** Studio Play on the owner's Windows PC, desktop, fresh session. A server
autopilot drove the race path at 160 studs/s for a full lap of about 41 s. Studio caps at 60 FPS.

| Scenario | Avg FPS | 1% low | Worst frame |
|---|---|---|---|
| Idle at spawn | 60.0 | 54.4 | — |
| Camera over the sea, facing away from the city | 60.0 | 55.0 | — |
| Full lap at 160 studs/s, day | 60.0 | 44.0 | 31 ms |
| Full lap at 160 studs/s, night (lit windows, 291 spotlights) | 60.0 | 45.2 | 32 ms |

World then: 16,027 Parts, 11,116 facade Textures, 291 SpotLights (night only). With streaming, a client had
3,700–6,500 Pattaya parts loaded at a time.

**2026-10-18, LOD test.** Night, Studio unfocused:
- Heartbeat 60/s, p99 18.9 ms;
- InstanceCount 60,188;
- parts streamed 4,819 (866 in view);
- textures streamed 2,628, of which 2,200 hidden by the LOD;
- SpotLights on: 9 of 71;
- memory: BaseParts 213 MB, GraphicsTexture 115 MB.

**2026-10-19, after the road fix, corridor dressing and street furniture.** Studio unfocused, night:
- PerfProbe at the Central start: parts loaded 8,118, textures 4,068 (visible 460), SpotLights on 11 of 104, traffic models 57.
- GPS drive Central → Bira: Heartbeat 60 (p50 16.9 ms, p99 19.3 ms, worst 20.2 ms).
- Memory: Instances 156 MB, GraphicsTexture 180 MB, InstanceCount 54k.
- RenderStepped is throttled while Studio is unfocused, so render FPS is unmeasured in that run.

Target from PERFORMANCE_BUDGET.md: 60 FPS on the owner's PC, with a 1% low of at least 45.

## 2. Slice budget (exporter output, 2026-10-19)
| | Count |
|---|---|
| Buildings upgraded | 507 of 535 boxes in the slice area (7 too thin, 2 replaced by landmark proxies, 19 all party walls / blocked) |
| New Parts | **22,953** (budget ≤ 25,000): 507 VisHull + 507 VisCore + 21,939 module parts, of which 1,024 roof parts (lit pass 2026-10-19; first build 21,856) |
| Parts removed from the city chunks | 507 boxes + 261 Roof slabs (moved to ServerStorage, not deleted) |
| **Net Parts in workspace** | **+22,185** |
| Facade Textures | about −515: decorated faces lose their Texture (1,944 → 1,429 on the upgraded boxes) |
| NightNeon parts (Neon at night) | 7,289 (7,196 lit panes + 93 neon strips); panes lit about 45 %, shopfronts about 70 %, warm amber tones |
| SurfaceGuis (signboards) | 462, PixelsPerStud 20, LightInfluence 0 |
| SpotLights / PointLights | 0 added |
| Collision parts | unchanged: 507 VisHull = the 507 boxes; all module parts CanCollide/CanQuery/CanTouch false, CastShadow false (VisCore casts shadows above 20 studs, like the box did) |
| Streaming | 58 Atomic chunk models, ≤ 600 parts each (largest 599); 8 build batches of ≤ 8 chunks (234–4,091 parts) |
| Parts per style | hotel 10,709 · shophouse 8,512 · commercial 2,708 · condo 607 · industrial 313 · house 104 |
| Parts per module | balcony_row_a 7,373 · window_pair_ac_a 4,483 · shopfront_a 2,811 · lobby_a 2,028 · transom_a 973 · shopfront_b 867 · curtain_wall_a 601 · roof_plant_a 528 · parapet_a 513 · water_tank_a 456 · balcony_grid_a 456 · fins_a 431 · band_glass_a 146 · garage_door_a 108 · window_row_a 76 · house_front_a 49 · ac_pair_a 40 |

What this means for a client:
- The slice is about 3,000 × 5,150 studs.
- At StreamingTargetRadius 1,280 (the `pc` profile), a car on Beach Road loads roughly a third to a half of the slice at once. Expect about 7,000–11,000 extra Parts loaded on top of today's 8,118 at the Central start. This is an estimate, not measured.

Risks:
- **7,289 NightNeon parts.** Neon parts with bloom are cheap to draw but add bloom area at night.
- **SurfaceGuis.** 462 signboards; each SurfaceGui costs a GUI layout and a texture.
- **PattayaLOD does not know the new part names.** Only the neon strips (`NeonSign`) and signboards (`SignFrame`) are faded beyond LOD_PropRange (900).

Cut list, if the measurements miss the target (cheapest first):
1. `V.Build({signs = false})`: no SurfaceGuis.
2. Lower `lit_win` in the config: fewer lit panes.
3. Larger `mid_bay` for hotels.
4. Ask team2/perf to add the small kit parts to `PROP_NAMES` in PattayaLOD: `ACUnit`, `Window`, `WindowLit`, `ShopGlow`, `Shutter`, `Sill`, `BalconyRail`, `ACCondenser`, `TankStand`, `WaterTank`, `Pilaster`, `Mullion`, `Transom`.

## 3. Measurement protocol (leader; the same steps before and after)
Run everything in a fresh Studio session with the Studio window in front. Use profile `pc`
(`require(game.ServerStorage.PattayaPerfProfile:Clone()).apply("pc")` in edit mode, then save).

1. **Before.**
   - Make sure no vis chunks exist (`V.Remove()` if they do).
   - Play, then `game.Lighting:SetAttribute("TimeLock", 21)` (server).
2. **Probes at three fixed spots** (server: teleport the car or use the test-kit autopilot):
   - A = Beach Road (21373, 1, -1000)
   - B = Second Road (21915, 1, -600)
   - C = Soi Pattaya 2 (21800, 1, -1802)

   At each spot, idle 5 s, then `workspace:SetAttribute("PerfProbe", 10)` (use 10.01, 10.02 … for reruns). Record:
   - `heartbeat` rate, p50 / p99 / worst;
   - `renderStepped` rate (valid only with `renderLooksFocused=true`);
   - memoryMB Instances / GraphicsParts / GraphicsTexture / total;
   - `counts.parts`, `texturesVisible`, `neonNear`, `drawProxyInView`, InstanceCount.
3. **Drive.** Autopilot the Central Loop (Beach Road → Pattaya Tai → Second Road → Pattaya Klang), 1 full lap at 160 studs/s, then one Beach Road run at 215 studs/s (nitro). Record:
   - FPS avg / 1% low / worst frame (Shift+F5 or the MicroProfiler, Ctrl+Alt+F6 in Studio);
   - whether streaming kept up (no "road missing" moments).
4. Repeat steps 2–3 by day (`TimeLock` 13).
5. **After.**
   - Stop Play.
   - Build all 8 batches (`V.Build({batch = "s1"})` … `"s8"`), run `V.Probe()`, save.
   - Repeat steps 1–4 with the same seeds and spots.
6. **Camera only.** Repeat step 3 with `MidnightCamera` true vs false (the slice built both times). The camera costs at most 4 raycasts per frame; its FPS effect is expected to be within noise.
7. **Report** a table like section 1 with these rows: idle A/B/C night, lap night, lap day, nitro Beach Road. Columns: FPS avg, 1% low, worst, Heartbeat p99, memory Instances/GraphicsParts, parts loaded. Report before/after deltas.

**Pass:** after-avg 60 FPS and 1% low ≥ 45 on the owner's PC (the PERFORMANCE_BUDGET target), and memory growth
in line with the part count. If it fails, apply the cut list in section 2 one step at a time and re-measure.
Mobile (≥ 30 FPS with profile `mobile`) is not measured in this phase.
