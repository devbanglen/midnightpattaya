"""Family T: ambient traffic vehicles (Pattaya street mix). Run inside Blender:
  blender -b --factory-startup --python-exit-code 1 -P tools/blender/gen_traffic.py -- --out <dir> [--only N,...]
writes <dir>/traffic/<Asset>.glb and <dir>/traffic/meta/<Asset>.json (then traffic/validate_traffic.py writes
<dir>/traffic/manifest.json, kept apart from the main kit manifest).

Every vehicle replaces one box car of PattayaTraffic.client.luau and keeps that car's collision: the client still
makes ONE invisible box Part (the old Body size of the traffic kind) and welds these meshes to it, non-colliding.
So the visual fills that footprint (KIND_BOX in traffic/trf_common.py):
  kind 0  6.6 x 14 studs: TRF_Car_Sedan (taxi = sedan + a roof-sign Part from the client), TRF_Car_Hatch,
          TRF_Scooter_Pair (two scooters with riders, staggered, as they ride in Pattaya), TRF_TukTuk_Std
  kind 1  7 x 16:        TRF_Songthaew_Std (baht bus: pickup + covered rear bench cabin + roof rails), TRF_Pickup_Std
  kind 2  7.2 x 16:      TRF_Van_Std (one-box minivan; a full city bus does not fit the 16-stud box)

Axes as the kit (docs/BLENDER_PIPELINE.md): 1 unit = 1 stud, Blender +Y = front = Roblox -Z, Z up, exported Y-up.
Origin ('pole' anchor): the CENTRE OF THE FOOTPRINT AT ROAD LEVEL (wheel bottoms at 0), not the bbox centre, so the
client places the meshes at Body.CFrame * (0, -Lift, 0) whatever the mirrors / steps do to the bbox.
Max 4 MeshParts: Paint / Dark / Head / Tail (see traffic/trf_common.py). Every piece is a CLOSED solid (box, cyl,
prism, loft with caps), so it reads with either triangle winding (Studio drew some kit meshes from behind).
Generic shapes, no brands, no logos, no text.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from traffic import trf_common as T          # noqa: E402
T.install_materials()                         # before export (reset_scene makes the bpy materials from the dict)
import export                                 # noqa: E402
export.check_name = T.check                   # TRF_ naming rule instead of BLD|RSD|RAC (runtime patch, no file edit)
from mathutils import Vector                  # noqa: E402
from common.mesh import Builder, _newell      # noqa: E402

PAINT, DARK, HEAD, TAIL = 'MP_CarPaint', 'MP_CarDark', 'MP_CarHead', 'MP_CarTail'


# ------------------------------------------------------------------------------------------------ primitives
def face(b, verts, hint, mat, smooth=False):
    """polygon with its winding fixed so the normal points along hint"""
    vs = [Vector(v) for v in verts]
    if _newell(vs).dot(Vector(hint)) < 0:
        vs.reverse()
    b._face([b._v(v) for v in vs], mat, smooth)


def loft(b, rings, axis, mat, smooth=True, caps=True):
    """closed solid through convex rings (lists of 3D points, same count, ordered around) stacked along axis
    (0 x, 1 y, 2 z). Side quads face away from the ring centres, caps face out along the axis."""
    rings = [[Vector(p) for p in r] for r in rings]
    n = len(rings[0])
    cents = [sum(r, Vector((0, 0, 0))) / n for r in rings]
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        c = (cents[i] + cents[i + 1]) / 2
        for j in range(n):
            k = (j + 1) % n
            q = [A[j], A[k], B[k], B[j]]
            hint = sum(q, Vector((0, 0, 0))) / 4 - c
            hint[axis] = 0
            face(b, q, hint, mat, smooth)
    if caps:
        d = cents[-1] - cents[0]
        face(b, rings[0], -d, mat)
        face(b, rings[-1], d, mat)


def section(w, z0, z1, x=0.0):
    """car body cross-section at half width w from sill z0 to top z1: flat floor, near-vertical sides, a rounded
    shoulder (10 points, convex)"""
    h = z1 - z0
    r = min(0.3, h * 0.25, w * 0.3)
    tu = min(0.18, w * 0.1)
    pts = [(-w + r, z0), (w - r, z0), (w, z0 + r), (w, z0 + h * 0.62), (w - tu, z1 - r), (w - r - 0.15, z1),
           (-(w - r - 0.15), z1), (-(w - tu), z1 - r), (-w, z0 + h * 0.62), (-w, z0 + r)]
    return [(px + x, pz) for px, pz in pts]


def body(b, stations, mat=PAINT, x=0.0):
    """lofted body along the length: stations = [(y, half width, sill z, top z)], rear to front"""
    loft(b, [[(px, y, pz) for px, pz in section(w, z0, z1, x)] for y, w, z0, z1 in stations], 1, mat)


def rrect(x0, x1, y0, y1, z, c):
    """chamfered rectangle (8 points) in the XY plane at height z"""
    return [(x0 + c, y0, z), (x1 - c, y0, z), (x1, y0 + c, z), (x1, y1 - c, z), (x1 - c, y1, z), (x0 + c, y1, z),
            (x0, y1 - c, z), (x0, y0 + c, z)]


def vloft(b, rects, mat, smooth=False):
    """closed solid through chamfered rectangles stacked in z: rects = [(x0, x1, y0, y1, z, chamfer)]"""
    loft(b, [rrect(*r) for r in rects], 2, mat, smooth)


def box(b, x0, x1, y0, y1, z0, z1, mat):
    b.box((x0, y0, z0), (x1, y1, z1), mat)


def mbox(b, xa, xb, y0, y1, z0, z1, mat):
    """mirrored pair of boxes at x in [xa, xb] and [-xb, -xa]"""
    box(b, xa, xb, y0, y1, z0, z1, mat)
    box(b, -xb, -xa, y0, y1, z0, z1, mat)


def wheel(b, x0, x1, y, r, seg=16):
    b.cyl((x0, y, r), (x1, y, r), r, seg, DARK)


def wheels(b, xin, xout, ys, r, seg=16):
    for y in ys:
        wheel(b, xin, xout, y, r, seg)
        wheel(b, -xout, -xin, y, r, seg)


def mbeam(b, p0, p1, w, mat=PAINT):
    """mirrored pair of square bars (pillars, rails); p0/p1 on the +X side"""
    b.beam(p0, p1, w, w, mat)
    b.beam((-p0[0], p0[1], p0[2]), (-p1[0], p1[1], p1[2]), w, w, mat)


def blob(b, c, rx, ry, rz, mat, seg=8, rings=6):
    """closed ellipsoid-ish solid (helmets, heads)"""
    rs = []
    for k in range(1, rings):
        t = -math.pi / 2 + math.pi * k / rings
        s, z = math.cos(t), c[2] + rz * math.sin(t)
        rs.append([(c[0] + rx * s * math.cos(2 * math.pi * i / seg), c[1] + ry * s * math.sin(2 * math.pi * i / seg), z)
                   for i in range(seg)])
    loft(b, rs, 2, mat, smooth=True)


def greenhouse(b, lo, hi, roof_lo, roof_hi, pillars, pw=0.28):
    """dark glass cabin (vloft lo -> hi), a body-colour roof slab and body-colour pillars (pairs (p0, p1) on +X)"""
    vloft(b, [lo, hi], DARK)
    vloft(b, [roof_lo, roof_hi], PAINT)
    for p0, p1 in pillars:
        mbeam(b, p0, p1, pw)


# ------------------------------------------------------------------------------------------------ cars (kind 0)
def sedan():
    """compact 4-door sedan (Thai city car / taxi body), 14 x 6.6 footprint, roof 5.42"""
    b = Builder('TRF_Car_Sedan')
    body(b, [(-7.0, 2.85, 1.35, 3.05), (-6.75, 3.1, 0.95, 3.4), (-5.6, 3.15, 0.85, 3.5), (-3.3, 3.2, 0.85, 3.55),
             (2.0, 3.2, 0.85, 3.5), (5.4, 3.15, 0.9, 3.1), (6.7, 3.0, 0.95, 2.8), (7.0, 2.75, 1.3, 2.4)])
    greenhouse(b, (-2.85, 2.85, -3.6, 2.3, 3.4, 0.5), (-2.45, 2.45, -1.9, 0.3, 5.2, 0.5),
               (-2.5, 2.5, -1.95, 0.35, 5.12, 0.5), (-2.3, 2.3, -1.75, 0.15, 5.42, 0.45),
               [((2.78, 2.2, 3.45), (2.42, 0.25, 5.15)), ((2.86, -0.75, 3.45), (2.47, -0.75, 5.15)),
                ((2.8, -3.5, 3.45), (2.42, -1.85, 5.15))])
    _car_ends(b, 7.0, 6.6, rear_tail=(2.45, 2.95))
    mbox(b, 2.9, 3.3, 1.75, 2.2, 3.45, 3.85, DARK)                  # mirrors
    wheels(b, 2.6, 3.25, (4.4, -4.4), 1.35)
    return b


def hatch():
    """5-door hatchback / eco-car, 13.4 long in the 14 x 6.6 footprint, roof 5.7"""
    b = Builder('TRF_Car_Hatch')
    body(b, [(-6.7, 2.9, 1.3, 3.3), (-6.5, 3.15, 0.9, 3.6), (-4.5, 3.2, 0.85, 3.65), (1.6, 3.2, 0.85, 3.6),
             (5.0, 3.15, 0.9, 3.2), (6.4, 3.0, 0.95, 2.9), (6.7, 2.75, 1.3, 2.5)])
    greenhouse(b, (-2.85, 2.85, -6.25, 1.9, 3.5, 0.5), (-2.45, 2.45, -5.7, -0.2, 5.5, 0.5),
               (-2.5, 2.5, -5.8, -0.1, 5.42, 0.5), (-2.3, 2.3, -5.6, -0.3, 5.7, 0.45),
               [((2.78, 1.75, 3.55), (2.42, -0.15, 5.45)), ((2.88, -2.0, 3.55), (2.48, -2.0, 5.45)),
                ((2.8, -6.1, 3.55), (2.42, -5.65, 5.45))])
    _car_ends(b, 6.7, 6.3, rear_tail=(2.7, 3.25))
    mbox(b, 2.9, 3.3, 1.35, 1.8, 3.55, 3.95, DARK)
    wheels(b, 2.6, 3.25, (4.2, -4.2), 1.3)
    return b


def _car_ends(b, yf, yh, rear_tail):
    """bumpers, grille, head and tail lamps of a car whose nose is at +yf and tail at -yf"""
    box(b, -2.95, 2.95, yf - 0.45, yf + 0.12, 0.95, 1.5, DARK)       # front bumper
    box(b, -2.95, 2.95, -yf - 0.12, -yf + 0.45, 0.95, 1.5, DARK)     # rear bumper
    box(b, -1.35, 1.35, yf - 0.4, yf + 0.04, 1.55, 2.25, DARK)       # grille
    mbox(b, 1.55, 2.65, yh - 0.2, yf + 0.02, 2.05, 2.5, HEAD)
    mbox(b, 1.6, 2.8, -yf - 0.03, -yf + 0.55, rear_tail[0], rear_tail[1], TAIL)
    box(b, -0.9, 0.9, -yf - 0.06, -yf + 0.3, 1.65, 2.2, DARK)        # rear plate recess


def tuktuk():
    """three-wheel tuk-tuk (samlor), 12.4 long in the 14 x 6.6 footprint: wide rear passenger tub with a bench,
    narrow driver section, single front wheel under a fairing, flat canopy on poles, roof 7.1"""
    b = Builder('TRF_TukTuk_Std')
    body(b, [(-6.0, 2.6, 1.3, 3.0), (-5.8, 2.8, 1.0, 3.3), (-1.3, 2.8, 1.0, 3.3), (-1.0, 2.5, 1.1, 3.0)])   # tub
    body(b, [(-1.2, 1.5, 0.95, 2.6), (2.8, 1.3, 0.95, 2.4), (3.4, 1.0, 1.05, 2.6)])                         # cab floor
    body(b, [(3.1, 1.0, 1.4, 3.6), (5.4, 0.85, 2.0, 3.8), (6.1, 0.6, 2.4, 3.5)])                            # fairing
    box(b, -0.35, 0.35, 4.1, 5.7, 1.95, 2.15, DARK)                                                         # mudguard
    b.beam((0, 4.9, 0.95), (0, 4.4, 3.6), 0.3, 0.3, DARK)                                                   # fork
    wheel(b, -0.4, 0.4, 4.9, 0.95, 14)
    wheels(b, 2.35, 2.95, (-3.9,), 1.05, 14)
    box(b, -2.5, 2.5, -5.0, -2.6, 3.2, 3.6, DARK)                                                           # bench
    box(b, -2.5, 2.5, -5.6, -5.1, 3.3, 5.0, DARK)                                                           # backrest
    box(b, -0.8, 0.8, -0.7, 0.9, 2.5, 3.0, DARK)                                                            # driver seat
    _rider(b, 0.0, 0.6, 3.0, (2.9, 4.0), helmet=False)
    b.beam((-1.0, 2.9, 4.0), (1.0, 2.9, 4.0), 0.18, 0.18, DARK)                                             # handlebar
    vloft(b, [(-2.95, 2.95, -6.2, 3.4, 6.6, 0.5), (-2.85, 2.85, -6.05, 3.2, 7.1, 0.4)], PAINT)              # canopy
    for x, y in ((2.6, -5.8), (2.5, -1.0)):
        mbeam(b, (x, y, 3.2), (x, y, 6.65), 0.22, DARK)
    mbeam(b, (1.1, 3.0, 3.5), (1.2, 3.25, 6.65), 0.2, DARK)                                                 # screen posts
    box(b, -1.05, 1.05, 3.0, 3.12, 3.8, 6.4, DARK)                                                          # windscreen
    b.cyl((0, 6.0, 3.05), (0, 6.25, 3.05), 0.45, 10, HEAD)
    mbox(b, 2.0, 2.6, -6.08, -5.85, 2.3, 2.75, TAIL)
    box(b, -2.7, 2.7, -6.2, -5.9, 1.0, 1.4, DARK)                                                           # rear bumper
    return b


def _rider(b, ox, oy, seat_z, grip, helmet=True):
    """seated rider silhouette (Dark), hips over (ox, oy) at seat_z, hands on grips at (y, z); helmet in Paint"""
    gy, gz = grip
    hy = oy - 0.4
    vloft(b, [(ox - 0.6, ox + 0.6, hy - 0.5, hy + 0.5, seat_z - 0.1, 0.25),
              (ox - 0.75, ox + 0.75, hy + 0.05, hy + 0.85, seat_z + 2.2, 0.25),
              (ox - 0.5, ox + 0.5, hy + 0.2, hy + 0.75, seat_z + 2.55, 0.2)], DARK)                         # torso
    head_y = hy + 0.55
    blob(b, (ox, head_y, seat_z + 3.1), 0.5, 0.55, 0.52, PAINT if helmet else DARK)
    if helmet:
        box(b, ox - 0.35, ox + 0.35, head_y + 0.38, head_y + 0.56, seat_z + 2.95, seat_z + 3.3, DARK)       # visor
    for s in (-1, 1):
        b.beam((ox + s * 0.72, hy + 0.5, seat_z + 2.05), (ox + s * 0.9, gy - 0.05, gz + 0.05), 0.32, 0.32, DARK)
        knee = (ox + s * 0.48, hy + 1.65, seat_z + 0.2)
        b.beam((ox + s * 0.38, hy + 0.1, seat_z + 0.15), knee, 0.42, 0.42, DARK)                           # thigh
        b.beam(knee, (ox + s * 0.42, hy + 1.55, seat_z - 1.75), 0.36, 0.36, DARK)                          # shin


def _scooter(b, ox, oy):
    """one step-through scooter (6.2 long) with a seated rider; origin of the scooter = (ox, oy)"""
    wheel(b, ox - 0.25, ox + 0.25, oy + 2.05, 0.85, 12)
    wheel(b, ox - 0.25, ox + 0.25, oy - 2.05, 0.85, 12)
    body(b, [(oy - 0.6, 0.62, 1.0, 1.45), (oy + 1.3, 0.62, 1.0, 1.45)], x=ox)                           # floorboard
    body(b, [(oy - 2.9, 0.4, 2.2, 2.75), (oy - 2.6, 0.62, 1.7, 2.95), (oy - 1.0, 0.7, 1.15, 2.95),
             (oy - 0.4, 0.62, 1.05, 2.4)], x=ox)                                                          # rear body
    vloft(b, [(ox - 0.75, ox + 0.75, oy + 1.15, oy + 1.9, 1.05, 0.25),
              (ox - 0.45, ox + 0.45, oy + 1.7, oy + 2.3, 3.9, 0.2)], PAINT)                              # leg shield
    box(b, ox - 0.35, ox + 0.35, oy + 1.5, oy + 2.6, 1.85, 2.05, PAINT)                                   # fender
    b.beam((ox, oy + 2.05, 0.85), (ox, oy + 1.95, 3.2), 0.22, 0.22, DARK)                                 # fork
    box(b, ox - 0.55, ox + 0.55, oy - 2.5, oy - 0.3, 2.9, 3.3, DARK)                                      # seat
    b.beam((ox - 1.0, oy + 2.0, 4.0), (ox + 1.0, oy + 2.0, 4.0), 0.18, 0.18, DARK)                        # handlebar
    box(b, ox - 0.3, ox + 0.3, oy + 2.22, oy + 2.42, 3.3, 3.65, HEAD)
    box(b, ox - 0.28, ox + 0.28, oy - 2.97, oy - 2.8, 2.35, 2.65, TAIL)
    _rider(b, ox, oy - 0.7, 3.3, (oy + 2.0, 4.0))


def scooter_pair():
    """two scooters with riders, staggered across the lane (left one ahead), filling the 14 x 6.6 footprint"""
    b = Builder('TRF_Scooter_Pair')
    _scooter(b, -1.55, 3.5)
    _scooter(b, 1.55, -3.4)
    return b


# ------------------------------------------------------------------------------------------------ pickups (kind 1)
def _pickup_front(b):
    """chassis, hood, single cab with glass and roof, bumpers, grille, head lamps, mirrors, wheels (16 x 7)"""
    body(b, [(-8.0, 3.3, 1.25, 2.6), (-7.8, 3.4, 1.0, 2.75), (7.5, 3.4, 1.0, 2.75), (7.95, 3.2, 1.25, 2.6)])
    body(b, [(3.5, 3.38, 2.5, 4.05), (6.4, 3.35, 2.5, 3.9), (7.6, 3.2, 2.5, 3.55), (7.95, 3.0, 2.5, 3.25)])
    body(b, [(-1.3, 3.38, 2.5, 4.15), (3.6, 3.38, 2.5, 4.1)])
    greenhouse(b, (-3.15, 3.15, -1.15, 3.7, 4.0, 0.45), (-2.75, 2.75, -1.0, 1.6, 6.35, 0.45),
               (-2.8, 2.8, -1.05, 1.65, 6.28, 0.45), (-2.6, 2.6, -0.9, 1.45, 6.6, 0.4),
               [((3.05, 3.55, 4.1), (2.68, 1.55, 6.3)), ((3.1, -1.1, 4.1), (2.7, -0.95, 6.3))], 0.3)
    wheels(b, 2.8, 3.5, (5.4, -5.4), 1.4)
    box(b, -3.35, 3.35, 7.6, 8.1, 1.0, 1.75, DARK)                     # front bumper
    box(b, -3.35, 3.35, -8.1, -7.7, 1.0, 1.6, DARK)                    # rear bumper
    box(b, -1.9, 1.9, 7.75, 8.0, 2.65, 3.35, DARK)                     # grille
    mbox(b, 2.0, 3.05, 7.6, 7.98, 2.75, 3.3, HEAD)
    mbox(b, 3.3, 3.62, 3.2, 3.65, 4.0, 4.45, DARK)                     # mirrors
    mbox(b, 2.95, 3.42, -8.0, -7.75, 2.85, 3.9, TAIL)


def pickup():
    """one-ton pickup (single cab, open bed with tailgate), 16 x 7, roof 6.6"""
    b = Builder('TRF_Pickup_Std')
    _pickup_front(b)
    mbox(b, 3.05, 3.4, -7.95, -1.4, 2.7, 4.25, PAINT)                  # bed sides
    box(b, -3.4, 3.4, -1.55, -1.35, 2.7, 4.25, PAINT)                  # bed front wall
    box(b, -3.4, 3.4, -7.95, -7.7, 2.7, 4.15, PAINT)                   # tailgate
    box(b, -3.05, 3.05, -7.7, -1.55, 2.6, 2.8, DARK)                   # bed floor
    return b


def songthaew():
    """Pattaya songthaew (baht bus): pickup with a covered rear cabin, two long benches, open sides above the
    panels, open back with a step and grab poles, roof rails, 16 x 7, top 8.2"""
    b = Builder('TRF_Songthaew_Std')
    _pickup_front(b)
    mbox(b, 3.1, 3.45, -7.95, -1.4, 2.7, 4.4, PAINT)                   # lower side panels
    box(b, -3.45, 3.45, -1.55, -1.35, 2.7, 7.45, PAINT)                # front wall behind the cab
    for y in (-7.8, -5.65, -3.5, -1.65):
        mbox(b, 3.12, 3.44, y - 0.16, y + 0.16, 4.4, 7.45, PAINT)      # pillars
    vloft(b, [(-3.5, 3.5, -8.1, 0.6, 7.4, 0.3), (-3.4, 3.4, -8.0, 0.5, 7.8, 0.25)], PAINT)   # roof
    for y in (-7.6, -3.8, 0.0):
        mbeam(b, (3.15, y, 7.75), (3.15, y, 8.2), 0.16, DARK)          # rail posts
    mbeam(b, (3.15, -7.8, 8.2), (3.15, 0.2, 8.2), 0.18, DARK)          # rails
    for y in (-7.8, 0.2):
        b.beam((-3.15, y, 8.2), (3.15, y, 8.2), 0.16, 0.16, DARK)
    mbox(b, 1.6, 3.1, -7.5, -1.7, 3.65, 3.95, DARK)                    # benches
    mbox(b, 2.85, 3.1, -7.5, -1.7, 3.95, 5.0, DARK)                    # bench backs
    box(b, -3.1, 3.1, -7.7, -1.5, 2.6, 2.85, DARK)                     # floor
    box(b, -2.0, 2.0, -8.0, -7.5, 1.7, 1.95, DARK)                     # rear step
    mbeam(b, (2.85, -7.9, 2.9), (2.85, -7.9, 7.3), 0.16, DARK)         # grab poles
    return b


# ------------------------------------------------------------------------------------------------ van (kind 2)
def van():
    """one-box 15-seat minivan (hotel / airport shuttle), 16 x 7.2, roof 7.75"""
    b = Builder('TRF_Van_Std')
    body(b, [(-8.0, 3.4, 1.25, 4.3), (-7.8, 3.6, 0.95, 4.45), (4.9, 3.6, 0.95, 4.45), (6.9, 3.55, 0.95, 3.95),
             (7.75, 3.45, 1.0, 3.5), (8.0, 3.2, 1.3, 3.05)])
    greenhouse(b, (-3.4, 3.4, -7.85, 5.2, 4.3, 0.5), (-3.2, 3.2, -7.7, 3.9, 7.3, 0.5),
               (-3.28, 3.28, -7.78, 3.95, 7.22, 0.5), (-3.1, 3.1, -7.6, 3.75, 7.75, 0.45),
               [((3.33, 5.05, 4.35), (3.17, 3.9, 7.25)), ((3.37, 2.0, 4.35), (3.2, 2.0, 7.25)),
                ((3.37, -1.8, 4.35), (3.2, -1.8, 7.25)), ((3.37, -5.0, 4.35), (3.2, -5.0, 7.25)),
                ((3.3, -7.8, 4.35), (3.15, -7.65, 7.25))], 0.3)
    wheels(b, 2.95, 3.62, (5.0, -4.9), 1.4)
    box(b, -3.5, 3.5, 7.7, 8.15, 1.0, 1.8, DARK)
    box(b, -3.5, 3.5, -8.15, -7.75, 1.0, 1.7, DARK)
    box(b, -1.8, 1.8, 7.85, 8.03, 2.2, 2.55, DARK)                     # grille
    mbox(b, 2.0, 3.1, 7.7, 8.02, 2.6, 3.2, HEAD)
    mbox(b, 2.95, 3.45, -8.03, -7.8, 3.0, 4.6, TAIL)
    mbox(b, 3.4, 3.72, 5.0, 5.4, 4.4, 5.0, DARK)                       # mirrors
    mbox(b, 3.58, 3.63, -7.0, 4.5, 2.2, 2.45, DARK)                    # side moulding
    return b


def meta(kind, note, roof_top, roof_y, taxi=False):
    """roof_top = highest roof point (studs above the road), roof_y = roof centre along Blender +Y (front) -> the
    client puts the taxi sign at Roblox z = -roof_y"""
    return {'group': 'Traffic', 'kind': f'traffic{kind}', 'traffic_kind': kind, 'anchor': 'pole',
            'collision': 'none (client box Part)', 'can_collide': False, 'footprint': list(T.KIND_BOX[kind]),
            'roof_top': roof_top, 'roof_z': -roof_y, 'taxi_sign': taxi, 'note': note}


ASSETS = [
    (sedan, meta(0, 'compact sedan; taxi variant = taxi palette + roof sign Part', 5.42, -0.8, True)),
    (hatch, meta(0, 'hatchback / eco-car', 5.7, -2.95)),
    (scooter_pair, meta(0, 'two scooters with riders, staggered', 6.6, 0.0)),
    (tuktuk, meta(0, 'tuk-tuk, single front wheel, canopy', 7.1, -1.4)),
    (songthaew, meta(1, 'Pattaya baht bus: covered rear bench cabin, roof rails', 8.2, -3.8)),
    (pickup, meta(1, 'single-cab pickup, open bed', 6.6, 0.3)),
    (van, meta(2, 'one-box minivan (a 16-stud box cannot hold a city bus)', 7.75, -1.9)),
]


def main():
    import json
    import time
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(os.getcwd(), 'build', 'vis_assets')
    only = argv[argv.index('--only') + 1].split(',') if '--only' in argv else None
    tdir = os.path.join(out, 'traffic')
    export.reset_scene()
    t0, n = time.time(), 0
    for fn, m in ASSETS:
        b = fn()
        if only and not any(o in b.name for o in only):
            b.bm.free()
            continue
        tris = export.build_and_export(b, dict(m, family='.'), tdir)
        mp = os.path.join(tdir, 'meta', b.name + '.json')
        with open(mp) as f:
            md = json.load(f)
        md['family'] = 'traffic'
        with open(mp, 'w') as f:
            json.dump(md, f, indent=1)
        print(f'EXPORT traffic {b.name} tris={tris} mats={len(md["materials"])}', flush=True)
        n += 1
    print(f'DONE traffic: {n} assets in {time.time() - t0:.1f}s', flush=True)


if __name__ == '__main__':
    main()
