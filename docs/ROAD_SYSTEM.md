# Road system

Builder: `roblox/src/ServerStorage/PattayaBuilder.luau` (copy in Studio at `ServerStorage.PattayaBuilder`).

- One anchored Part per simplified centreline segment, lengthened at each joint by the outer-edge gap of the bend
  (`width/2 * tan(turn/2)`), so curves have no visible gaps. Straight stretches are single long Parts (≤120 studs).
- Junctions: one flat cylinder per graph node, radius = widest incident road half-width + sidewalk.
- Markings (non-colliding, `CanQuery = false` so the car's suspension rays ignore them): double yellow centre line on
  two-way main roads, dashed lane lines, none on sois. They stop at junction discs.
- Sidewalks: offset strips, 0.6-stud curb, trimmed back from junctions.
- Road top at Y = 1 (gameplay), on a terrain ground slab with top at Y = 0.
- Each edge Model carries attributes: EdgeId, OsmWay, Tier, Lanes, Oneway, Coastal, NameTh.
- Tiers in use: main (secondary/tertiary/primary), soi (residential/unclassified/living_street). Express (trunk:
  Sukhumvit) lies just east of the first slice.

First build: 2,125 simplified segments → 7,545 Parts including markings and sidewalks, 463 junctions, 72 chunks.

Not done yet: elevation/bridges, banking, traffic signals, overlap check between widened parallel roads, drive test.
