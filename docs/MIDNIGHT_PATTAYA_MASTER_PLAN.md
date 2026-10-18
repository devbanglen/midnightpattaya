# MIDNIGHT PATTAYA — master plan

**MIDNIGHT PATTAYA** · *Open World Street Racing* · "Drive the City. Own the Night."

An original open-world street racing game for Roblox, set in a gameplay-scaled Pattaya built from real
OpenStreetMap data. RayCity is gameplay inspiration only: no RayCity assets, code, music, logos or UI are used.
The project was called "Pattaya Racing World" until 2026-10-18. The old plan, `PATTAYA_RACING_MASTER_PLAN.md`, is
kept as history; this file supersedes it. Live status is in `PROJECT_STATUS.md`. The owner communicates in Thai.

## Naming rule
- The player-facing name is "MIDNIGHT PATTAYA", used in UI, the loading screen and docs.
- Internal identifiers keep their names so nothing breaks: `Pattaya*` scripts, `PattayaWorld`, `PattayaData`, the
  DataStore `PattayaProgress_v1`, and repository paths.

## Architecture
The directive's modules, mapped to what exists (✓ built and tested, ◐ in progress, ○ planned):

| Directive module | Our implementation | State |
|---|---|---|
| WorldMap | world-map data export (`worldmap.luau`) + client map UI | ◐ data being built (world team); UI ○ |
| RoadGraph | `tools/mapgen/road_graph.py` → `graph.luau`; runtime `ServerStorage.PattayaRoute` | ✓ central slice |
| WorldStreaming | chunked `PattayaWorld` (512-stud Atomic models, StreamingEnabled); traffic is client-side and clock-driven | ✓ central slice |
| CircuitGeometry | `tools/circuit/*` → `circuits/<id>.luau`; `ServerStorage.CircuitBuilder` | ◐ Bira team |
| CircuitAccess | corridor graph from city to Bira, merged into the road graph; GPS target | ◐ Bira team |
| RaceSessionService | circuit session state machine (practice / time attack / race / track day / private) | ◐ circuit team |
| LapTimingService | server-authoritative lap + sector timing | ◐ circuit team |
| CheckpointValidator | edge-triggered plane-crossing gates + teleport check (already in the loop race); generalised for circuits | ✓ loop race, ◐ circuits |
| LeaderboardService | personal best (saved) + global (OrderedDataStore) + friends | ◐ circuit team |
| RaceUI | HUD clients (`PattayaRaceClient`, `PattayaSprintClient`, `PattayaChallengeClient`, `PattayaJobsClient`; circuit client in progress) | ✓ / ◐ |
| SpectatorService | follow-camera for circuit races | ○ (hooks first) |

Already built and tested:
- Loop race, Street Sprint, taxi/delivery jobs, ambient traffic + near misses.
- Street Challenge, against AI and against 2 players.
- Road Fight: 4 bosses with titles.
- Money/EXP/levels, RayCity-style nitro.
- Night facades, lamps and neon signs.

See `RACING_ROUTE_DESIGN.md`.

Pipeline (unchanged, data-driven, reproducible):
```
OSM raw (ODbL) -> osm_normalize -> road_graph -> buildings/facades -> gameplay_layout -> traffic -> export_roblox
  -> localhost HTTP -> Studio ServerStorage.PattayaData -> PattayaBuilder -> workspace.PattayaWorld
Bira: OSM raceway + DEM -> tools/circuit -> circuits/bira.luau -> CircuitBuilder -> venue (near 1:1 scale)
```

## Geography plan
```
NAKLUA ─ NORTH PATTAYA ─ CENTRAL (built) ─ SOUTH / WALKING STREET ─ PRATUMNAK ─ JOMTIEN      (city, compressed 0.5)
                         │
                         └─ Sukhumvit / intercity corridor (compressed) ──> transition road ──> BIRA CIRCUIT
                                                                                              entrance → parking/paddock → track
```
- **City:** compression 0.5, 0.28 m/stud, origin (20000, 0, 0). The central slice coordinates are frozen; every
  tested feature is keyed to them.
- **Bira International Circuit** (Pong, Bang Lamung): placed at the compressed position of its real location, but
  the venue itself is near 1:1 so the track keeps its proportions. A controlled transition road joins the scales.
  No teleport-only map: the drive from the city is part of the experience.

## Phases (directive, mapped to status)
| Phase | Content | Status |
|---|---|---|
| A | Audit + name update | ◐ this update: plan, loading screen, docs |
| B | Central Pattaya playable prototype | ✓ (see status; human playtest feedback pending) |
| C | Bira source data + track geometry audit | ◐ Bira team |
| D | Playable Bira geometry | ◐ Bira team (code); Studio build by the leader |
| E | Circuit connection to the city road network | ◐ Bira team (corridor data); merge + drive test by the leader |
| F | Free Practice + server-validated lap timing | ◐ circuit team |
| G | Multiplayer circuit racing | ◐ circuit team; 2-player Studio test needed |
| H | Circuit visual detailing (floodlights, garages, signage) | ◐ partly Bira team; night lighting by the events team |
| I | Leaderboards, private races, ranked preparation | ◐ circuit team |
| J | Broader Pattaya world (Naklua → Jomtien) | ◐ world team |
| — | Night Run / Survival (scheduled events), day/night cycle | ◐ events team |
| — | Garage, car shop, car classes (Street/Sport/Super/Hyper/Track Spec by performance index) | ◐ garage team |

## Bira acceptance (the milestone is not complete until all of these are tested)
- The track resembles the real layout.
- The route is driveable continuously.
- Curbs and collision geometry don't break the car.
- Consecutive valid laps work.
- Pit entry and exit are usable.
- Server lap timing works, including start/finish.
- The circuit integrates with the existing cars.
- The world map routes players to the circuit, and the drive from the city has been tested.
- Performance has been profiled.

Unverified items stay marked unverified.

## Team process
- The work is split across five parallel worktrees (`team/bira`, `team/circuit`, `team/events`, `team/garage`,
  `team/world`). Each team owns its files.
- The leader merges the branches, imports into Studio (the only Studio user, so no parallel Studio edits), playtests
  with the client-side autopilot, and records results in `PROJECT_STATUS.md`.
- Nothing is called "done" without a test in Studio. Code written by a team stays "written, not playtested" until
  then.

## Branding and IP
- MIDNIGHT PATTAYA artwork and UI are original.
- HUD style: the HUD panels use the loading screen's colours (neon cyan to pink) through
  `ReplicatedStorage.MidnightStyle`.
  - Each panel gets a thin cyan-to-pink accent line along its top edge.
  - Titled panels use a GothamBlack title and show the name, either in the title (Garage, Circuits menu, circuit
    HUD, open map) or as a small "MIDNIGHT PATTAYA" wordmark (loop race HUD, circuit results).
  - The module only decorates panels and never moves them. If it is missing, the HUDs still work, just undecorated.
- Bira International Circuit is named descriptively as a real place. Its official logos, artwork and marks are not
  used. Sponsor boards are placeholders ("MIDNIGHT PATTAYA", invented brands) until rights are clarified.
- OSM: "© OpenStreetMap contributors" (ODbL).
