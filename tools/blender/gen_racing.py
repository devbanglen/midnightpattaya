"""Family C: racing venue pieces (Bira circuit dressing, event areas). Run inside Blender:
  blender -b --factory-startup -P tools/blender/gen_racing.py -- --out <dir>

Prop scale: 1 m = 2.679 studs (common/units.py). Front = Roblox -Z (Blender +Y) = the track side.
No real circuit logos or sponsor marks: boards are plain placeholders (MP_Signboard, UV 0..1).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export                                     # noqa: E402
from common.mesh import Builder                   # noqa: E402
from common.facade import wall, fill, front_box   # noqa: E402
from common.units import pm                       # noqa: E402


def meta(group, anchor, collision, can_collide, note='', grid=None):
    m = {'group': group, 'kind': 'kit_module' if anchor == 'mount' else 'prop', 'anchor': anchor,
         'collision': collision, 'can_collide': can_collide, 'note': note}
    if grid:
        m['grid'] = grid
    return m


def garage_facade():
    """pit garage bay front, 6 m wide x 5 m high (16.1 x 13.4 studs): roll-up door, number board slot, fascia.
    Kit module (mount plane = building box face); tile along X for a pit building."""
    b = Builder('RAC_Garage_Facade')
    W, H, t = pm(6.0), pm(5.0), 0.8
    door = (-W / 2 + 1.2, W / 2 - 1.2, 0.0, pm(3.8))
    wall(b, W, H, [door], 'MP_Wall', t=t, recess=0.2)
    fill(b, door, 0.2, 'MP_Shutter')
    for k in range(10):                                                       # door panel ribs
        z = 0.6 + k * (door[3] - 0.8) / 10
        b.box((door[0], 0.2, z), (door[1], 0.32, z + 0.14), 'MP_Shutter', skip=('yn', 'xn', 'xp'))
    for x in (-W / 2, W / 2 - 0.9):                                           # pilasters
        b.box((x, t, 0.0), (x + 0.9, t + 0.4, H), 'MP_WallAccent', skip=('zn',))
    front_box(b, -W / 2, W / 2, door[3] + 0.2, door[3] + 0.8, t, t + 0.6, 'MP_WallAccent')   # door head beam
    b.panel(-W / 2 + 1.4, W / 2 - 1.4, door[3] + 1.1, H - 0.4, t + 0.05, 'MP_Signboard')       # team/number slot
    return b


def start_gantry():
    """start-line gantry over a 14 m track (37.5 studs clear), 7 m clearance: two box legs, truss beam, 5 start
    lights facing -Z (one lens MeshPart, lit by script), plain banner board"""
    b = Builder('RAC_Gantry_Start')
    span, clr = pm(14.0), pm(7.0)
    lw = 1.6
    for sx in (-1, 1):
        x = sx * (span / 2 + lw / 2)
        b.box((x - lw / 2, -lw / 2, 0.0), (x + lw / 2, lw / 2, clr + 3.6), 'MP_MetalDark')
        b.box((x - 1.4, -1.4, 0.0), (x + 1.4, 1.4, 0.6), 'MP_MetalDark', skip=('zn',))
    L = span + 2 * lw
    for z in (clr, clr + 3.6):                                                   # truss chords
        for y in (-0.7, 0.7):
            b.box((-L / 2, y - 0.2, z - 0.2), (L / 2, y + 0.2, z + 0.2), 'MP_MetalDark', skip=('xn', 'xp'))
    n = 10
    for k in range(n):                                                           # diagonals (front + back)
        x0 = -span / 2 + k * span / n
        x1 = x0 + span / n
        for y in (-0.7, 0.7):
            if k % 2 == 0:
                b.beam((x0, y, clr + 0.2), (x1, y, clr + 3.4), 0.15, 0.15, 'MP_MetalDark')
            else:
                b.beam((x0, y, clr + 3.4), (x1, y, clr + 0.2), 0.15, 0.15, 'MP_MetalDark')
    b.box((-span * 0.32, 0.9, clr + 0.3), (span * 0.32, 1.1, clr + 3.3), 'MP_MetalDark', skip=('yp',))
    b.panel(-span * 0.32, span * 0.32, clr + 0.3, clr + 3.3, 1.1, 'MP_Signboard')       # banner (placeholder)
    b.box((-5.6, 0.9, clr - 2.2), (5.6, 1.4, clr - 0.2), 'MP_MetalDark')                # light box
    for k in range(5):
        x = -4.4 + k * 2.2
        b.cyl((x, 1.4, clr - 1.2), (x, 1.5, clr - 1.2), 0.7, 10, 'MP_SignalLens', caps=(False, True))
    return b


def guardrail():
    """W-beam guardrail segment 4 m (10.7 studs), posts every 2 m; tile along X, track side = -Z"""
    b = Builder('RAC_Guardrail_Segment')
    L = pm(4.0)
    zc, hh = pm(0.6), pm(0.16)
    y = 0.6
    # W profile from 3 bent strips (front faces + top/bottom lips)
    prof = [(y + 0.0, zc - hh), (y + 0.35, zc - hh / 2), (y + 0.1, zc), (y + 0.35, zc + hh / 2), (y + 0.0, zc + hh)]
    for k in range(len(prof) - 1):
        (y0, z0), (y1, z1) = prof[k], prof[k + 1]
        b.qn([(-L / 2, y0, z0), (L / 2, y0, z0), (L / 2, y1, z1), (-L / 2, y1, z1)], (0, z1 - z0, -(y1 - y0)), 'MP_Metal')
        b.qn([(-L / 2, y0 - 0.06, z0), (L / 2, y0 - 0.06, z0), (L / 2, y1 - 0.06, z1), (-L / 2, y1 - 0.06, z1)], (0, -1, 0), 'MP_Metal')
    for x in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):
        b.box((x - 0.25, -0.25, 0.0), (x + 0.25, 0.25, zc + hh + 0.2), 'MP_MetalDark', skip=('zn',))
        b.box((x - 0.15, 0.25, zc - 0.3), (x + 0.15, y - 0.06, zc + 0.3), 'MP_MetalDark')      # spacer block
    return b


def pit_box_front():
    """pit box front (in front of a garage bay): low pit counter, canopy on 2 posts, board slot; mount anchor so
    it snaps to RAC_Garage_Facade (same 6 m width)"""
    b = Builder('RAC_Pit_BoxFront')
    W, d = pm(6.0), pm(3.0)
    zc = pm(3.6)
    b.box((-W / 2, 0.0, zc), (W / 2, d, zc + 0.35), 'MP_MetalDark', skip=('yn',))               # canopy frame
    b.qn([(-W / 2 + 0.2, 0.0, zc + 0.36), (W / 2 - 0.2, 0.0, zc + 0.36), (W / 2 - 0.2, d - 0.2, zc + 0.36),
          (-W / 2 + 0.2, d - 0.2, zc + 0.36)], (0, 0, 1), 'MP_Awning')
    for x in (-W / 2 + 0.3, W / 2 - 0.3):
        b.box((x - 0.2, d - 0.4, 0.0), (x + 0.2, d, zc), 'MP_MetalDark', skip=('zn', 'zp'))
    b.box((-W / 2 + 1.0, d - 1.0, 0.0), (-0.8, d - 0.2, pm(1.0)), 'MP_Concrete', skip=('zn',))   # counter
    b.box((0.8, d - 1.0, 0.0), (W / 2 - 1.0, d - 0.2, pm(1.0)), 'MP_Concrete', skip=('zn',))
    b.box((-W / 2 + 0.6, d - 0.05, zc - 1.6), (W / 2 - 0.6, d, zc - 0.05), 'MP_MetalDark', skip=('yp',))
    b.panel(-W / 2 + 0.6, W / 2 - 0.6, zc - 1.6, zc - 0.05, d + 0.01, 'MP_Signboard')
    return b


def banner_frame():
    """event banner frame 6 x 2 m board on two posts with weighted feet; both faces plain placeholders"""
    b = Builder('RAC_Banner_Frame')
    w, h, z0 = pm(6.0), pm(2.0), pm(1.0)
    for x in (-w / 2 - 0.3, w / 2 + 0.3):
        b.box((x - 0.2, -0.2, 0.0), (x + 0.2, 0.2, z0 + h + 0.3), 'MP_MetalDark', skip=('zn',))
        b.box((x - 0.6, -1.6, 0.0), (x + 0.6, 1.6, 0.5), 'MP_Concrete', skip=('zn',))
    b.box((-w / 2 - 0.1, -0.15, z0 - 0.1), (w / 2 + 0.1, 0.15, z0 + h + 0.1), 'MP_MetalDark', skip=('yn', 'yp'))
    b.panel(-w / 2, w / 2, z0, z0 + h, 0.15, 'MP_Signboard')
    b.qn([(-w / 2, -0.15, z0), (w / 2, -0.15, z0), (w / 2, -0.15, z0 + h), (-w / 2, -0.15, z0 + h)], (0, -1, 0),
         'MP_Signboard', uvs=[(1, 0), (0, 0), (0, 1), (1, 1)])
    return b


ASSETS = [
    (garage_facade, meta('Garage', 'mount', 'Box', True, 'pit garage bay, tile along X', {'modules_w_studs': round(pm(6.0), 4)})),
    (start_gantry, meta('Gantry', 'base', 'PreciseConvexDecomposition', True,
                        'legs collide, the span is 18.75 studs up; or CanCollide off + 2 leg Parts')),
    (guardrail, meta('Guardrail', 'base', 'Box', True, 'tile along X every 10.7 studs')),
    (pit_box_front, meta('Pit', 'mount', 'PreciseConvexDecomposition', True, 'snaps in front of RAC_Garage_Facade')),
    (banner_frame, meta('Banner', 'base', 'Box', True, 'placeholder board both faces')),
]

if __name__ == '__main__':
    export.main(ASSETS, 'racing')
