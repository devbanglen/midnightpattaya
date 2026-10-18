"""Family A: modular building KIT (not whole buildings). Run inside Blender:
  blender -b --factory-startup -P tools/blender/gen_buildings.py -- --out <dir>

Grid (common/units.py, the city's own scale): module width MODULE_W = 7.143 studs (4 m x 0.5 compression),
ground floor GROUND_H = 11.571 studs, mid floor FLOOR_H = 8.571 studs (3.2 m, == buildings_game.json level_studs),
parapet PARAPET_H = 3.214 studs. A building box edge of length L takes round(L / MODULE_W) modules (scale the row in
X by L / (n * MODULE_W) -- within +-7 %), a box of `levels` takes 1 ground + (levels - 1) mid rows + 1 top row:
box h = levels * FLOOR_H + 3 = GROUND_H + (levels - 1) * FLOOR_H exactly.

Groups: GF ground-floor fronts, MF mid-floor fronts, TP top (parapet) fronts, CN corner pieces, RF roof items.
Kit modules (GF/MF/TP) use the 'mount' anchor, CN the 'corner' anchor, RF the 'base' anchor (export.py).
Generic shapes only; sign boards are plain placeholders (MP_Signboard, UV 0..1 for a texture later).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export                                                     # noqa: E402
from common.mesh import Builder                                   # noqa: E402
from common.facade import wall, fill, front_box, railing          # noqa: E402
from common.units import MODULE_W as W, FLOOR_H as FH, GROUND_H as GH, PARAPET_H as PH, WALL_T as T  # noqa: E402

HW = W / 2


def kit(group, modules_w=1, floors=None, collision='Box', note=''):
    return {'group': group, 'kind': 'kit_module', 'anchor': 'mount',
            'grid': {'modules_w': modules_w, 'height_studs': floors, 'module_w_studs': round(W, 4)},
            'collision': collision, 'can_collide': False, 'note': note}


# ------------------------------------------------------------------------------------------------- ground floor
def gf_shophouse_shutter():
    """Thai shophouse bay: roller shutter half down over a dark shop, shutter box, sheet-metal awning, sign slot"""
    b = Builder('BLD_GF_ShophouseShutter')
    hole = (-HW + 0.55, HW - 0.55, 0.0, 7.6)
    wall(b, W, GH, [hole], 'MP_Wall', recess=0.1)
    fill(b, (hole[0], hole[1], 0.0, 4.2), 0.1, 'MP_Glass')                 # dark shop interior
    b.box((hole[0], 0.1, 4.2), (hole[1], 0.4, 7.6), 'MP_Shutter', skip=('yn', 'zp'))   # shutter curtain
    for k in range(5):                                                      # shutter ribs
        z = 4.6 + k * 0.62
        b.box((hole[0], 0.4, z), (hole[1], 0.5, z + 0.12), 'MP_Shutter', skip=('yn',))
    b.box((hole[0] - 0.1, 0.1, 7.6), (hole[1] + 0.1, 1.1, 8.4), 'MP_Shutter', skip=('yn',))  # shutter box
    # sheet-metal awning sloping down to the street
    b.qn([(-HW, T, 8.4), (HW, T, 8.4), (HW, T + 3.2, 7.3), (-HW, T + 3.2, 7.3)], (0, 0.3, 1), 'MP_Shutter')
    b.qn([(-HW, T, 8.3), (HW, T, 8.3), (HW, T + 3.2, 7.2), (-HW, T + 3.2, 7.2)], (0, -0.3, -1), 'MP_Shutter')
    # sign slot: plain board on the fascia
    front_box(b, -HW + 0.3, HW - 0.3, 8.8, 11.0, T, T + 0.25, 'MP_Signboard')
    b.panel(-HW + 0.45, HW - 0.45, 8.95, 10.85, T + 0.26, 'MP_Signboard')
    return b


def gf_shophouse_awning():
    """open shopfront: glazed display + door, fabric awning with valance, sign slot"""
    b = Builder('BLD_GF_ShophouseAwning')
    hole = (-HW + 0.5, HW - 0.5, 0.0, 7.8)
    wall(b, W, GH, [hole], 'MP_Wall', recess=0.25)
    fill(b, hole, 0.25, 'MP_Glass')
    for x in (-0.9, 0.9):                                                   # mullions / door frame
        b.box((x - 0.12, 0.25, 0.0), (x + 0.12, 0.45, 7.8), 'MP_Wall', skip=('yn', 'zn', 'zp'))
    b.box((hole[0], 0.25, 2.6), (-0.9, 0.45, 2.85), 'MP_Wall', skip=('yn',))   # display sill rails
    b.box((0.9, 0.25, 2.6), (hole[1], 0.45, 2.85), 'MP_Wall', skip=('yn',))
    # fabric awning (two-sided sheet) + valance
    b.qn([(-HW + 0.2, T, 8.6), (HW - 0.2, T, 8.6), (HW - 0.2, T + 3.6, 6.9), (-HW + 0.2, T + 3.6, 6.9)], (0, 0.4, 1), 'MP_Awning')
    b.qn([(-HW + 0.2, T, 8.5), (HW - 0.2, T, 8.5), (HW - 0.2, T + 3.6, 6.8), (-HW + 0.2, T + 3.6, 6.8)], (0, -0.4, -1), 'MP_Awning')
    b.box((-HW + 0.2, T + 3.55, 6.1), (HW - 0.2, T + 3.7, 6.9), 'MP_Awning')
    for x in (-HW + 0.3, HW - 0.3):                                         # side cheeks
        b.qn([(x, T, 8.6), (x, T + 3.6, 6.9), (x, T + 3.6, 6.1), (x, T, 7.6)], (1 if x > 0 else -1, 0, 0), 'MP_Awning')
    front_box(b, -HW + 0.3, HW - 0.3, 8.9, 11.0, T, T + 0.25, 'MP_Signboard')
    b.panel(-HW + 0.45, HW - 0.45, 9.05, 10.85, T + 0.26, 'MP_Signboard')
    return b


def gf_restaurant():
    """restaurant front: full glazing with a centred door, flat canopy, planters, sign slot"""
    b = Builder('BLD_GF_Restaurant')
    hole = (-HW + 0.45, HW - 0.45, 0.6, 7.9)
    wall(b, W, GH, [hole], 'MP_Wall', recess=0.3, reveal_mat='MP_WallAccent')
    fill(b, hole, 0.3, 'MP_Glass')
    front_box(b, -HW, HW, 0.0, 0.6, T, T + 0.15, 'MP_WallAccent')          # plinth
    for x in (-1.0, 1.0, hole[0] + 0.1, hole[1] - 0.1):                     # frames
        b.box((x - 0.1, 0.3, 0.6), (x + 0.1, 0.5, 7.9), 'MP_WallAccent', skip=('yn', 'zn', 'zp'))
    b.box((hole[0], 0.3, 6.6), (hole[1], 0.5, 6.8), 'MP_WallAccent', skip=('yn',))   # transom
    front_box(b, -HW, HW, 8.1, 8.6, T, T + 2.8, 'MP_WallAccent')            # flat canopy
    for x0 in (-HW + 0.2, 1.4):                                              # planters
        front_box(b, x0, x0 + HW - 1.6, 0.0, 1.4, T, T + 1.0, 'MP_WallAccent', bottom=False)
    front_box(b, -HW + 0.4, HW - 0.4, 8.9, 11.0, T, T + 0.3, 'MP_Signboard')
    b.panel(-HW + 0.55, HW - 0.55, 9.05, 10.85, T + 0.31, 'MP_Signboard')
    return b


def _commercial_bay(b, x0, entrance=False):
    """one 4 m bay of a commercial front: pilaster on the left edge, storefront glass, fascia sign strip"""
    x1 = x0 + W
    hole = (x0 + 0.7, x1, 0.0, 8.2)
    wall(b, W, GH, [hole], 'MP_Wall', recess=0.3, x0=x0)
    fill(b, hole, 0.3, 'MP_Glass')
    b.box((x0, T, 0.0), (x0 + 0.7, T + 0.35, 8.6), 'MP_WallAccent', skip=('zn',))      # pilaster
    b.box((hole[0], 0.3, 7.3), (x1, 0.45, 7.5), 'MP_WallAccent', skip=('yn',))          # transom
    b.box(((x0 + x1) / 2 - 0.08, 0.3, 0.0), ((x0 + x1) / 2 + 0.08, 0.45, 7.3), 'MP_WallAccent', skip=('yn', 'zn'))
    front_box(b, x0, x1, 8.6, 9.4, T, T + 0.4, 'MP_WallAccent')                         # fascia band
    b.panel(x0 + 0.5, x1 - 0.5, 9.6, 11.2, T + 0.12, 'MP_Signboard')                    # sign strip
    if entrance:
        front_box(b, x0 + 0.3, x1 - 0.3, 7.6, 8.2, T, T + 3.2, 'MP_WallAccent')         # entrance canopy


def gf_commercial_bay():
    b = Builder('BLD_GF_CommercialBay')
    _commercial_bay(b, -HW)
    b.box((HW - 0.7, T, 0.0), (HW, T + 0.35, 8.6), 'MP_WallAccent', skip=('zn',))      # closing pilaster (overlaps next bay)
    return b


def gf_commercial_7bay():
    """7-bay commercial front (28 m real, 50 studs) as one mesh, centre bay with an entrance canopy"""
    b = Builder('BLD_GF_Commercial7Bay')
    for k in range(7):
        _commercial_bay(b, -3.5 * W + k * W, entrance=(k == 3))
    b.box((3.5 * W - 0.7, T, 0.0), (3.5 * W, T + 0.35, 8.6), 'MP_WallAccent', skip=('zn',))
    return b


def gf_hotel_lobby():
    """hotel/condo lobby, 2 modules: tall glazing, drop-off canopy on two columns, cyan LED strip on the canopy edge"""
    b = Builder('BLD_GF_HotelLobby')
    w = 2 * W
    hole = (-w / 2 + 0.8, w / 2 - 0.8, 0.0, 10.2)
    wall(b, w, GH, [hole], 'MP_Wall', recess=0.3)
    fill(b, hole, 0.3, 'MP_Glass')
    for x in (-3.6, -1.2, 1.2, 3.6):
        b.box((x - 0.1, 0.3, 0.0), (x + 0.1, 0.5, 10.2), 'MP_WallAccent', skip=('yn', 'zn', 'zp'))
    b.box((hole[0], 0.3, 7.0), (hole[1], 0.5, 7.25), 'MP_WallAccent', skip=('yn',))
    front_box(b, -w / 2 + 0.5, w / 2 - 0.5, 7.6, 8.4, T, T + 7.0, 'MP_WallAccent')    # canopy slab
    for x in (-w / 2 + 1.4, w / 2 - 1.4):
        b.cyl((x, T + 6.0, 0.0), (x, T + 6.0, 7.6), 0.35, 8, 'MP_WallAccent', caps=(False, False))
    b.box((-w / 2 + 0.5, T + 6.95, 7.75), (w / 2 - 0.5, T + 7.1, 8.25), 'MP_NeonCyan', skip=('yn',))
    return b


# --------------------------------------------------------------------------------------------------- mid floors
def mf_punched_twin():
    b = Builder('BLD_MF_PunchedTwin')
    holes = [(-HW + 0.9, -0.5, 2.3, 6.9), (0.5, HW - 0.9, 2.3, 6.9)]
    wall(b, W, FH, holes, 'MP_Wall', recess=0.3)
    for h in holes:
        fill(b, h, 0.3, 'MP_Glass')
        front_box(b, h[0] - 0.2, h[1] + 0.2, 2.05, 2.3, T, T + 0.3, 'MP_WallAccent')     # sills
        b.box(((h[0] + h[1]) / 2 - 0.06, 0.3, h[2]), ((h[0] + h[1]) / 2 + 0.06, 0.4, h[3]), 'MP_WallAccent', skip=('yn', 'zn', 'zp'))
    front_box(b, -HW, HW, 0.0, 0.5, T, T + 0.12, 'MP_WallAccent')                       # slab line
    return b


def mf_punched_ac():
    """one wide window, AC condenser on a bracket (every Pattaya facade has them)"""
    b = Builder('BLD_MF_PunchedAC')
    hole = (-HW + 1.2, HW - 1.2, 2.8, 6.8)
    wall(b, W, FH, [hole], 'MP_Wall', recess=0.3)
    fill(b, hole, 0.3, 'MP_Glass')
    for x in (-0.8, 0.8):
        b.box((x - 0.07, 0.3, hole[2]), (x + 0.07, 0.4, hole[3]), 'MP_WallAccent', skip=('yn', 'zn', 'zp'))
    front_box(b, hole[0] - 0.2, hole[1] + 0.2, 2.55, 2.8, T, T + 0.3, 'MP_WallAccent')
    front_box(b, -HW + 0.8, -HW + 3.4, 0.9, 2.3, T + 0.1, T + 1.1, 'MP_Metal')          # condenser
    b.cyl((-HW + 2.1, T + 1.1, 1.6), (-HW + 2.1, T + 1.15, 1.6), 0.55, 10, 'MP_Metal', caps=(False, True))
    front_box(b, -HW + 0.9, -HW + 3.3, 0.75, 0.9, T, T + 1.2, 'MP_WallAccent')          # bracket
    front_box(b, -HW, HW, 0.0, 0.5, T, T + 0.12, 'MP_WallAccent')
    return b


def mf_shophouse_upper():
    """shophouse upper floor: two tall windows with security grilles, cornice band"""
    b = Builder('BLD_MF_ShophouseUpper')
    holes = [(-HW + 0.8, -0.45, 1.8, 6.9), (0.45, HW - 0.8, 1.8, 6.9)]
    wall(b, W, FH, holes, 'MP_Wall', recess=0.3)
    for h in holes:
        fill(b, h, 0.3, 'MP_Glass')
        for k in range(1, 4):                                                          # grille bars
            x = h[0] + (h[1] - h[0]) * k / 4
            b.box((x - 0.05, T - 0.05, h[2]), (x + 0.05, T + 0.05, h[3]), 'MP_Metal', skip=('zn', 'zp'))
        b.box((h[0], T - 0.05, 4.3), (h[1], T + 0.05, 4.42), 'MP_Metal', skip=('xn', 'xp'))
    front_box(b, -HW, HW, 7.6, 8.2, T, T + 0.45, 'MP_WallAccent')                       # cornice band
    return b


def mf_balcony_row():
    """balcony row: sliding glass door, slab + solid parapet wall (older hotels / apartments)"""
    b = Builder('BLD_MF_BalconyRow')
    hole = (-HW + 0.6, HW - 0.6, 0.5, 7.0)
    wall(b, W, FH, [hole], 'MP_Wall', recess=0.3)
    fill(b, hole, 0.3, 'MP_Glass')
    b.box((-0.06, 0.3, hole[2]), (0.06, 0.4, hole[3]), 'MP_WallAccent', skip=('yn', 'zn', 'zp'))
    front_box(b, -HW, HW, 0.0, 0.5, T, T + 3.2, 'MP_WallAccent')                        # slab
    b.box((-HW, T + 2.95, 0.5), (HW, T + 3.2, 3.4), 'MP_Wall', skip=('xn', 'xp', 'zn'))    # parapet front
    b.box((-HW, T + 2.95, 3.4), (HW, T + 3.25, 3.6), 'MP_WallAccent', skip=('xn', 'xp'))
    return b


def mf_condo_balcony():
    """condo balcony: full-height glazing, thin slab, metal railing"""
    b = Builder('BLD_MF_CondoBalcony')
    hole = (-HW + 0.35, HW - 0.35, 0.4, 7.9)
    wall(b, W, FH, [hole], 'MP_Wall', recess=0.3)
    fill(b, hole, 0.3, 'MP_Glass')
    for x in (-1.2, 1.2):
        b.box((x - 0.06, 0.3, hole[2]), (x + 0.06, 0.4, hole[3]), 'MP_Metal', skip=('yn', 'zn', 'zp'))
    front_box(b, -HW, HW, 0.0, 0.4, T, T + 3.6, 'MP_WallAccent')
    railing(b, -HW + 0.1, HW - 0.1, 0.4, T + 3.45, 2.9, 'MP_Metal', posts=5)
    for x in (-HW + 0.1, HW - 0.1):                                                    # side rails
        b.box((x - 0.06, T + 0.1, 3.18), (x + 0.06, T + 3.45, 3.3), 'MP_Metal')
    return b


def mf_curtain_wall():
    """curtain wall: flush glass, mullions on a 2-panel grid, spandrel band at the slab"""
    b = Builder('BLD_MF_CurtainWall')
    hole = (-HW, HW, 1.2, FH)
    wall(b, W, FH, [hole], 'MP_WallAccent', recess=T)          # only the spandrel strip as wall face
    fill(b, hole, T - 0.1, 'MP_Glass')
    for x in (-HW + 0.08, 0.0, HW - 0.08):
        b.box((x - 0.08, T - 0.1, 1.2), (x + 0.08, T + 0.25, FH), 'MP_Metal', skip=('zn', 'zp', 'yn'))
    b.box((-HW, T - 0.1, 1.15), (HW, T + 0.25, 1.35), 'MP_Metal', skip=('xn', 'xp', 'yn'))
    return b


def mf_curtain_wall_neon():
    """curtain wall with a vertical magenta LED fin on the left edge (hotel accent at night)"""
    b = Builder('BLD_MF_CurtainWallNeon')
    hole = (-HW, HW, 1.2, FH)
    wall(b, W, FH, [hole], 'MP_WallAccent', recess=T)
    fill(b, hole, T - 0.1, 'MP_Glass')
    for x in (0.0, HW - 0.08):
        b.box((x - 0.08, T - 0.1, 1.2), (x + 0.08, T + 0.25, FH), 'MP_Metal', skip=('zn', 'zp', 'yn'))
    b.box((-HW, T - 0.1, 1.15), (HW, T + 0.25, 1.35), 'MP_Metal', skip=('xn', 'xp', 'yn'))
    b.box((-HW, T - 0.1, 0.0), (-HW + 0.45, T + 0.7, FH), 'MP_WallAccent', skip=('zn', 'zp', 'yn'))   # fin
    b.box((-HW + 0.1, T + 0.7, 0.0), (-HW + 0.35, T + 0.85, FH), 'MP_NeonMagenta', skip=('zn', 'zp', 'yn'))
    return b


# ---------------------------------------------------------------------------------------------------- top / parapet
def _parapet(b, x0, x1, h, cap=True):
    """parapet wall standing above the roof: front, back (seen from the roof) and coping"""
    b.box((x0, 0.0, 0.0), (x1, T, h), 'MP_Wall', skip=('xn', 'xp', 'zn', 'zp'))
    if cap:
        b.box((x0, 0.0, h), (x1, T + 0.25, h + 0.3), 'MP_WallAccent', skip=('xn', 'xp'))


def tp_parapet():
    b = Builder('BLD_TP_Parapet')
    _parapet(b, -HW, HW, PH)
    front_box(b, -HW, HW, 0.0, 0.45, T, T + 0.12, 'MP_WallAccent')
    return b


def tp_cornice_neon():
    """stepped hotel cornice with a cyan LED line under the top step"""
    b = Builder('BLD_TP_CorniceNeon')
    _parapet(b, -HW, HW, PH + 1.0, cap=False)
    front_box(b, -HW, HW, 0.0, 0.6, T, T + 0.5, 'MP_WallAccent')
    front_box(b, -HW, HW, PH - 0.2, PH + 0.6, T, T + 0.9, 'MP_WallAccent')
    b.box((-HW, T + 0.9, PH - 0.15), (HW, T + 1.0, PH + 0.05), 'MP_NeonCyan', skip=('xn', 'xp', 'yn'))
    b.box((-HW, 0.0, PH + 1.0), (HW, T + 0.35, PH + 1.3), 'MP_WallAccent', skip=('xn', 'xp'))
    return b


def tp_crown_fin():
    """tower crown module, 2 floors high: open fin frame with an LED edge (stack on top of the last floor)"""
    b = Builder('BLD_TP_CrownFin')
    h = 2 * FH
    _parapet(b, -HW, HW, 1.4, cap=False)
    for x in (-HW + 0.3, HW - 0.3):
        b.box((x - 0.3, 0.0, 0.0), (x + 0.3, T + 1.4, h), 'MP_WallAccent', skip=('zn',))
    b.box((-HW, 0.0, h - 1.0), (HW, T + 1.4, h), 'MP_WallAccent', skip=('xn', 'xp'))
    b.box((-HW, T + 1.4, h - 0.9), (HW, T + 1.55, h - 0.6), 'MP_NeonCyan', skip=('xn', 'xp', 'yn'))
    for x in (-HW + 0.3, HW - 0.3):
        b.box((x - 0.1, T + 1.4, 1.4), (x + 0.1, T + 1.55, h - 1.0), 'MP_NeonCyan', skip=('zn', 'zp', 'yn'))
    for k in range(1, 4):                                                               # louvre slats
        z = 1.4 + k * (h - 2.4) / 4
        b.box((-HW + 0.6, 0.3, z - 0.12), (HW - 0.6, T + 0.9, z + 0.12), 'MP_Metal', skip=('xn', 'xp'))
    return b


# ------------------------------------------------------------------------------------------------------- corners
def _corner(name, h, cap=False, glass=False):
    b = Builder(name)
    c, o = 0.9, T + 0.18                                    # reaches c into the building, o out of both faces
    b.box((-c, -c, 0.0), (o, o, h), 'MP_Metal' if glass else 'MP_WallAccent', skip=('xn', 'yn', 'zn', 'zp'))
    if cap:
        b.box((-c, -c, h), (o + 0.25, o + 0.25, h + 0.3), 'MP_WallAccent', skip=('xn', 'yn'))
    if glass:                                                # thin glazed reveal strips either side of the post
        b.box((-c, o, 1.2), (-c + 0.05, o + 0.02, h), 'MP_Glass', skip=('zn', 'zp'))
    return b


def cn_ground():
    return _corner('BLD_CN_Ground', GH)


def cn_mid():
    return _corner('BLD_CN_Mid', FH)


def cn_top():
    return _corner('BLD_CN_Top', PH, cap=True)


def cn_glass_mid():
    return _corner('BLD_CN_GlassMid', FH, glass=True)


# ---------------------------------------------------------------------------------------------------- roof items
def rf_plant_room():
    """rooftop plant room: block with louvred front, door, slab overhang (12 x 9 x 8.6 studs)"""
    b = Builder('BLD_RF_PlantRoom')
    w, d, h = 12.0, 9.0, FH
    b.box((-w / 2, -d / 2, 0), (w / 2, d / 2, h), 'MP_Wall', skip=('zn', 'yp'))
    hole = (-w / 2 + 1.0, 1.0, 1.2, 6.8)
    wall(b, w, h, [hole, (2.5, 4.6, 0.0, 6.0)], 'MP_Wall', t=d / 2, recess=d / 2 - 0.3)
    fill(b, (2.5, 4.6, 0.0, 6.0), d / 2 - 0.3, 'MP_Metal')                              # door
    fill(b, hole, d / 2 - 0.3, 'MP_Shutter')
    for k in range(7):                                                                  # louvre blades
        z = 1.5 + k * 0.75
        b.box((hole[0], d / 2 - 0.25, z), (hole[1], d / 2 + 0.15, z + 0.18), 'MP_Shutter', skip=('xn', 'xp'))
    b.box((-w / 2 - 0.4, -d / 2 - 0.4, h), (w / 2 + 0.4, d / 2 + 0.4, h + 0.5), 'MP_WallAccent')
    return b


def rf_ac_units():
    """cluster of 4 AC condensers on a concrete plinth (8.4 x 3.2 studs)"""
    b = Builder('BLD_RF_ACUnits')
    b.box((-4.2, -1.6, 0.0), (4.2, 1.6, 0.4), 'MP_Concrete', skip=('zn',))
    for k in range(4):
        x = -3.15 + k * 2.1
        b.box((x - 0.95, -1.1, 0.4), (x + 0.95, 0.9, 2.3), 'MP_Metal', skip=('zn',))
        b.cyl((x, 0.9, 1.35), (x, 1.0, 1.35), 0.7, 10, 'MP_MetalDark', caps=(False, True))
    return b


def rf_water_tank():
    """stainless water tank on a steel stand (Thai roof staple)"""
    b = Builder('BLD_RF_WaterTank')
    r, z0 = 2.0, 2.4
    b.cyl((0, 0, z0 + 0.2), (0, 0, z0 + 5.2), r, 14, 'MP_Metal')
    b.cyl((0, 0, z0 + 5.2), (0, 0, z0 + 5.9), r, 14, 'MP_Metal', r1=0.5)
    b.box((-2.3, -2.3, z0), (2.3, 2.3, z0 + 0.2), 'MP_MetalDark')
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box((sx * 2.0 - 0.15, sy * 2.0 - 0.15, 0.3), (sx * 2.0 + 0.15, sy * 2.0 + 0.15, z0), 'MP_MetalDark', skip=('zn', 'zp'))
            b.box((sx * 2.0 - 0.35, sy * 2.0 - 0.35, 0.0), (sx * 2.0 + 0.35, sy * 2.0 + 0.35, 0.3), 'MP_Concrete', skip=('zn',))
    b.beam((-2.0, -2.0, 0.6), (2.0, 2.0, z0 - 0.2), 0.12, 0.12, 'MP_MetalDark')
    b.beam((2.0, -2.0, 0.6), (-2.0, 2.0, z0 - 0.2), 0.12, 0.12, 'MP_MetalDark')
    return b


def rf_sign_frame():
    """rooftop sign frame: steel lattice legs, plain board (placeholder), magenta neon border"""
    b = Builder('BLD_RF_SignFrame')
    w, h, z0 = 21.4, 8.0, 4.0
    for x in (-w / 2 + 1.5, -w / 6, w / 6, w / 2 - 1.5):
        b.box((x - 0.2, -1.6, 0.0), (x + 0.2, -1.2, z0 + h), 'MP_MetalDark', skip=('zn',))
        b.beam((x, 1.0, 0.0), (x, -1.4, z0 + 1.0), 0.3, 0.3, 'MP_MetalDark')
    b.box((-w / 2, -1.2, z0), (w / 2, -0.8, z0 + h), 'MP_MetalDark')
    b.panel(-w / 2 + 0.4, w / 2 - 0.4, z0 + 0.4, z0 + h - 0.4, -0.79, 'MP_Signboard')
    for z in (z0, z0 + h - 0.25):
        b.box((-w / 2, -0.8, z), (w / 2, -0.6, z + 0.25), 'MP_NeonMagenta', skip=('yn',))
    for x in (-w / 2, w / 2 - 0.25):
        b.box((x, -0.8, z0 + 0.25), (x + 0.25, -0.6, z0 + h - 0.25), 'MP_NeonMagenta', skip=('yn', 'zn', 'zp'))
    return b


def rf_meta(collision='Box', note=''):
    return {'group': 'RF', 'kind': 'roof_item', 'anchor': 'base', 'collision': collision, 'can_collide': False,
            'note': note}


def cn_meta(h):
    return {'group': 'CN', 'kind': 'corner', 'anchor': 'corner', 'grid': {'height_studs': round(h, 4)},
            'collision': 'Box', 'can_collide': False,
            'note': 'origin = building box corner; building interior at Roblox x<0, z>0; rotate 90 deg per corner'}


ASSETS = [
    (gf_shophouse_shutter, kit('GF', 1, round(GH, 4), note='Thai shophouse, roller shutter half down, sign slot')),
    (gf_shophouse_awning, kit('GF', 1, round(GH, 4), note='open shopfront, fabric awning, sign slot')),
    (gf_restaurant, kit('GF', 1, round(GH, 4), note='restaurant glazing, canopy, planters, sign slot')),
    (gf_commercial_bay, kit('GF', 1, round(GH, 4), note='one commercial bay; repeat along the edge')),
    (gf_commercial_7bay, kit('GF', 7, round(GH, 4), note='7-bay commercial front (28 m real) as one mesh')),
    (gf_hotel_lobby, kit('GF', 2, round(GH, 4), note='hotel/condo lobby with drop-off canopy and LED edge')),
    (mf_punched_twin, kit('MF', 1, round(FH, 4), note='two punched windows')),
    (mf_punched_ac, kit('MF', 1, round(FH, 4), note='wide window + AC condenser')),
    (mf_shophouse_upper, kit('MF', 1, round(FH, 4), note='shophouse upper floor, grilles, cornice')),
    (mf_balcony_row, kit('MF', 1, round(FH, 4), note='balcony with solid parapet')),
    (mf_condo_balcony, kit('MF', 1, round(FH, 4), note='condo balcony with railing')),
    (mf_curtain_wall, kit('MF', 1, round(FH, 4), note='curtain wall glass')),
    (mf_curtain_wall_neon, kit('MF', 1, round(FH, 4), note='curtain wall + magenta LED fin')),
    (tp_parapet, kit('TP', 1, round(PH + 0.3, 4), note='parapet above the roof (closed back)')),
    (tp_cornice_neon, kit('TP', 1, round(PH + 1.3, 4), note='hotel cornice with cyan LED line')),
    (tp_crown_fin, kit('TP', 1, round(2 * FH, 4), note='tower crown, 2 floors, LED edges')),
    (cn_ground, cn_meta(GH)), (cn_mid, cn_meta(FH)), (cn_top, cn_meta(PH + 0.3)), (cn_glass_mid, cn_meta(FH)),
    (rf_plant_room, rf_meta(note='place on the roof, inset >= 2 studs from the parapet')),
    (rf_ac_units, rf_meta()),
    (rf_water_tank, rf_meta(collision='Hull')),
    (rf_sign_frame, rf_meta(note='rooftop sign, plain placeholder board (no brands)')),
]

if __name__ == '__main__':
    export.main(ASSETS, 'buildings')
