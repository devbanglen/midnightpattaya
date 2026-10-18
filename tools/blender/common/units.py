"""Scale and grid constants shared by every generator (pure Python, no bpy).

All geometry is modelled directly in STUDS (1 Blender unit = 1 stud). The glTF files therefore hold studs and are
imported into Roblox Studio with Scale Unit = Studs (1 unit = 1 stud, nothing rescaled).

The city (tools/mapgen, config central_pattaya.json) does not use one uniform scale:
  horizontal: 1 m real -> compression / meters_per_stud = 0.5 / 0.28 = 1.786 studs (footprints are compressed x0.5)
  vertical:   1 m real -> vertical_scale / meters_per_stud = 0.75 / 0.28 = 2.679 studs (level 3.2 m = 8.571 studs)
  ground floor of every building box gets +3 studs (ground_floor_extra_studs)
Building kit modules follow the city exactly so a module row fills a buildings_game.json box edge:
  module width 4 m -> 7.143 studs, mid floor 3.2 m -> 8.571 studs, ground floor 8.571 + 3 = 11.571 studs.
Props (street furniture, palms, racing items) are not compressed horizontally (a compressed bench or lamp looks
wrong next to a car); they use the vertical scale on all three axes: 1 m -> 2.679 studs. A 9 m street light is
24.1 studs (the builder's current part-based lights are 20 studs, palms 26-34 studs).
"""

METERS_PER_STUD = 0.28
COMPRESSION = 0.5
VERTICAL_SCALE = 0.75

H_STUDS_PER_M = COMPRESSION / METERS_PER_STUD          # 1.7857
V_STUDS_PER_M = VERTICAL_SCALE / METERS_PER_STUD       # 2.6786
PROP_STUDS_PER_M = V_STUDS_PER_M

MODULE_M = 4.0
FLOOR_M = 3.2
GROUND_EXTRA_STUDS = 3.0

MODULE_W = MODULE_M * H_STUDS_PER_M                    # 7.142857
FLOOR_H = FLOOR_M * V_STUDS_PER_M                      # 8.571429 (== buildings_game.json level_studs)
GROUND_H = FLOOR_H + GROUND_EXTRA_STUDS                # 11.571429
PARAPET_H = 1.2 * V_STUDS_PER_M                        # 3.214
WALL_T = 0.8                                           # facade shell thickness in studs (mount plane -> front face)

UV_STUDS_PER_TILE = 8.0                                # box-projected UVs: 1 UV unit = 8 studs (tileable textures later)

TRI_BUDGET = 10000                                     # per asset (project rule)
TRI_HARD_LIMIT = 20000                                 # Roblox: an individual mesh may not exceed 20,000 triangles
MAX_MATERIALS = 4


def pm(m):
    """prop metres -> studs"""
    return m * PROP_STUDS_PER_M


def hm(m):
    """building horizontal metres -> studs"""
    return m * H_STUDS_PER_M


def vm(m):
    """building vertical metres -> studs"""
    return m * V_STUDS_PER_M
