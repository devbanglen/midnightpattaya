"""Family B: roadside props. Run inside Blender:
  blender -b --factory-startup -P tools/blender/gen_roadside.py -- --out <dir>

Anchors: 'base' = bbox base centre; 'pole' = the pole/trunk foot stays at the origin (bottom at 0) so a collider Part
or a placement point from the map data lines up with the pole even when an arm or a leaning crown is off-centre.

Prop scale (common/units.py): 1 m real = 2.679 studs on all axes (the city's vertical scale; props are not
compressed). Origin = base centre. Front = Roblox -Z (Blender +Y): the side a lamp arm, sign face or bench seat faces;
place props with -Z toward the road. Generic shapes, no brands; sign faces are plain placeholders (UV 0..1).
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export                                # noqa: E402
from common.mesh import Builder              # noqa: E402
from common.units import pm                  # noqa: E402


def prop(group, collision, can_collide, note='', anchor='base'):
    return {'group': group, 'kind': 'prop', 'anchor': anchor, 'collision': collision, 'can_collide': can_collide,
            'note': note}


def _footing(b, r=0.5, h=0.35):
    b.box((-pm(r), -pm(r), 0.0), (pm(r), pm(r), h), 'MP_Concrete', skip=('zn',))


def _lamp_arm(b, z_top, reach, sign=1):
    """curved arm from the pole top out along +/-Y, lamp head with a warm emissive underside"""
    pts = []
    for k in range(6):
        t = k / 5
        pts.append((0.0, sign * reach * t, z_top - 1.4 + 1.4 * math.sin(t * math.pi / 2) + 0.3 * t))
    b.tube(pts, [0.22, 0.2, 0.18, 0.17, 0.16, 0.15], 6, 'MP_MetalDark', cap_end=True)
    y = sign * reach
    zt = pts[-1][2]
    b.box((-0.55, y - (1.6 if sign > 0 else 0.4), zt - 0.45), (0.55, y + (0.4 if sign > 0 else 1.6), zt + 0.1), 'MP_MetalDark', skip=('zn',))
    b.box((-0.45, y - (1.5 if sign > 0 else 0.3), zt - 0.5), (0.45, y + (0.3 if sign > 0 else 1.5), zt - 0.45), 'MP_LampWarm', skip=('zp',))


def light_double():
    """highway double-arm street light, 10 m pole (26.8 studs), arms 2.2 m each way (median of a dual carriageway)"""
    b = Builder('RSD_Light_DoubleArm')
    h = pm(10.0)
    _footing(b)
    b.box((-0.5, -0.5, 0.35), (0.5, 0.5, 0.55), 'MP_MetalDark', skip=('zn',))
    b.cyl((0, 0, 0.55), (0, 0, h - 1.2), 0.42, 8, 'MP_MetalDark', r1=0.26, caps=(False, False))
    b.cyl((0, 0, h - 1.2), (0, 0, h - 0.9), 0.26, 8, 'MP_MetalDark', caps=(False, True))
    _lamp_arm(b, h - 1.0, pm(2.2), 1)
    _lamp_arm(b, h - 1.0, pm(2.2), -1)
    return b


def light_single():
    """street single-arm light, 8 m pole (21.4 studs), arm 1.8 m toward the road (front, Roblox -Z)"""
    b = Builder('RSD_Light_SingleArm')
    h = pm(8.0)
    _footing(b, 0.4)
    b.cyl((0, 0, 0.35), (0, 0, h - 1.0), 0.32, 8, 'MP_MetalDark', r1=0.2, caps=(False, False))
    b.cyl((0, 0, h - 1.0), (0, 0, h - 0.8), 0.2, 8, 'MP_MetalDark', caps=(False, True))
    _lamp_arm(b, h - 0.9, pm(1.8), 1)
    return b


def _signal_head(b, cx, cy, z0, facing=1):
    """3-lens signal housing (1.4 x 4.0 studs, game-readable), backplate, visors; lenses one MeshPart"""
    w, h = 1.4, 4.0
    b.box((cx - w / 2, cy - 0.5, z0), (cx + w / 2, cy + 0.5, z0 + h), 'MP_MetalDark')
    b.box((cx - w / 2 - 0.35, cy - 0.55, z0 - 0.3), (cx + w / 2 + 0.35, cy - 0.5, z0 + h + 0.3), 'MP_Stripe')   # backplate
    b.box((cx - w / 2 - 0.35, cy - 0.6, z0 - 0.3), (cx + w / 2 + 0.35, cy - 0.55, z0 + h + 0.3), 'MP_MetalDark')
    for k in range(3):
        z = z0 + h - 0.7 - k * 1.3
        b.cyl((cx, cy + 0.5, z), (cx, cy + 0.56, z), 0.48, 10, 'MP_SignalLens', caps=(False, True))
        b.qn([(cx - 0.6, cy + 0.5, z + 0.55), (cx + 0.6, cy + 0.5, z + 0.55),
              (cx + 0.6, cy + 1.2, z + 0.45), (cx - 0.6, cy + 1.2, z + 0.45)], (0, 0, 1), 'MP_MetalDark')   # visor
        b.qn([(cx - 0.6, cy + 0.5, z + 0.5), (cx + 0.6, cy + 0.5, z + 0.5),
              (cx + 0.6, cy + 1.2, z + 0.4), (cx - 0.6, cy + 1.2, z + 0.4)], (0, 0, -1), 'MP_MetalDark')


def signal_housing():
    """traffic-signal housing alone (to hang on existing masts / gantries); lenses face Roblox -Z"""
    b = Builder('RSD_Signal_Housing')
    _signal_head(b, 0.0, 0.0, 0.3)
    b.box((-0.15, -0.15, 0.0), (0.15, 0.15, 0.3), 'MP_MetalDark', skip=('zn',))
    return b


def signal_mast():
    """signal mast 6.5 m with a 5 m cantilever arm over the lane (+X) and a housing facing the traffic (-Z)"""
    b = Builder('RSD_Signal_Mast')
    h, arm = pm(6.5), pm(5.0)
    _footing(b, 0.45)
    b.cyl((0, 0, 0.35), (0, 0, h), 0.4, 8, 'MP_MetalDark', r1=0.3, caps=(False, True))
    b.beam((0, 0, h - 1.0), (arm, 0, h - 0.4), 0.35, 0.35, 'MP_MetalDark')
    b.beam((0, 0, h - 3.0), (arm * 0.45, 0, h - 0.9), 0.15, 0.15, 'MP_MetalDark')
    _signal_head(b, arm - 0.9, 0.0, h - 5.0)
    _signal_head(b, 0.0, 0.45, pm(2.6))                     # pedestrian-height repeater on the pole
    return b


def utility_pole():
    """Thai concrete utility pole 9 m (24 studs), two crossarms with insulators, a cable drum box"""
    b = Builder('RSD_Pole_Utility')
    h = pm(9.0)
    b.box((-0.45, -0.45, 0.0), (0.45, 0.45, 0.4), 'MP_Concrete', skip=('zn',))
    b.cyl((0, 0, 0.4), (0, 0, h), 0.42, 6, 'MP_Concrete', r1=0.28, caps=(False, True))
    for z, half in ((h - 1.0, pm(1.2)), (h - 2.6, pm(0.9))):
        b.box((-half, -0.18, z - 0.18), (half, 0.18, z + 0.18), 'MP_MetalDark')
        for x in (-half + 0.3, -half / 3, half / 3, half - 0.3):
            b.cyl((x, 0, z + 0.18), (x, 0, z + 0.75), 0.14, 6, 'MP_Rubber')
    b.beam((0, 0, h - 3.6), (pm(0.9) * 0.8, 0, h - 2.78), 0.12, 0.12, 'MP_MetalDark')
    b.box((-0.7, 0.42, pm(4.5)), (0.7, 1.3, pm(4.5) + 1.6), 'MP_MetalDark')                # junction box
    for k in range(3):                                                                    # cable coils (tangle)
        z = pm(5.6) + k * 0.25
        b.cyl((-0.9, 0.0, z), (0.9, 0.0, z), 0.5 - k * 0.08, 6, 'MP_Rubber', caps=(True, True))
    return b


def sign_post():
    """road sign post 2.8 m with a blank 1.2 x 0.9 m board (placeholder face toward -Z)"""
    b = Builder('RSD_Sign_Post')
    h = pm(2.8)
    b.cyl((0, -0.32, 0.0), (0, -0.32, h), 0.17, 8, 'MP_Metal', caps=(False, True))
    w, hh = pm(1.2), pm(0.9)
    z0 = h - hh - 0.1
    b.box((-w / 2, -0.15, z0), (w / 2, 0.0, z0 + hh), 'MP_Metal', skip=('yp',))
    b.panel(-w / 2, w / 2, z0, z0 + hh, 0.0, 'MP_Signboard')
    return b


def bus_shelter():
    """bus shelter 4 x 1.6 m, 2.6 m high: posts, roof, glass back, bench, blank ad panel (placeholder)"""
    b = Builder('RSD_Shelter_Bus')
    w, d, h = pm(4.0), pm(1.6), pm(2.6)
    for x in (-w / 2 + 0.3, w / 2 - 0.3):
        for y in (-d / 2 + 0.3, d / 2 - 0.5):
            b.box((x - 0.15, y - 0.15, 0.0), (x + 0.15, y + 0.15, h), 'MP_MetalDark', skip=('zn', 'zp'))
    b.box((-w / 2, -d / 2, h), (w / 2, d / 2 + 0.4, h + 0.35), 'MP_MetalDark')
    b.box((-w / 2 + 0.45, -d / 2 + 0.22, 0.5), (w / 2 - 0.45, -d / 2 + 0.38, h - 0.2), 'MP_Glass')     # glass back
    b.box((w / 2 - 0.4, -d / 2 + 0.3, 0.3), (w / 2 - 0.2, d / 2 - 0.6, h - 0.3), 'MP_Signboard')   # ad panel
    b.box((-w / 2 + 0.6, -d / 2 + 0.45, pm(0.45) - 0.12), (w / 2 - 1.2, -d / 2 + 0.45 + pm(0.4), pm(0.45)), 'MP_Metal')
    for x in (-w / 2 + 1.0, w / 2 - 1.6):
        b.box((x - 0.1, -d / 2 + 0.6, 0.0), (x + 0.1, -d / 2 + 0.8, pm(0.45) - 0.12), 'MP_Metal', skip=('zn', 'zp'))
    return b


def parking_barrier():
    """boom-gate parking barrier: cabinet, 4 m striped arm toward +X, rest post"""
    b = Builder('RSD_Barrier_Parking')
    cw, ch = pm(0.35), pm(1.0)
    b.box((-cw / 2, -cw / 2, 0.0), (cw / 2, cw / 2, ch), 'MP_Stripe', skip=('zn',))
    b.box((-cw / 2 - 0.1, -cw / 2 - 0.1, ch), (cw / 2 + 0.1, cw / 2 + 0.1, ch + 0.15), 'MP_MetalDark')
    L = pm(4.0)
    seg = 8
    for k in range(seg):
        x0 = cw / 2 + k * (L / seg)
        mat = 'MP_Stripe' if k % 2 else 'MP_Wall'
        b.box((x0, -0.15, ch - 0.45), (x0 + L / seg, 0.15, ch - 0.05), mat, skip=() if k in (0, seg - 1) else ('xn', 'xp'))
    b.box((cw / 2 + L - 0.15, -0.15, 0.0), (cw / 2 + L + 0.15, 0.15, ch - 0.45), 'MP_MetalDark', skip=('zn',))
    return b


def bench():
    """park/beach bench 1.8 m: wooden slats, steel legs, backrest on the -Y side (sitters face -Z in Roblox)"""
    b = Builder('RSD_Bench_Park')
    w, sh, d = pm(1.8), pm(0.45), pm(0.45)
    for k in range(3):
        y = -d / 2 + k * d / 3
        b.box((-w / 2, y + 0.04, sh - 0.12), (w / 2, y + d / 3 - 0.04, sh), 'MP_Wood')
    for k in range(2):
        z = sh + 0.35 + k * 0.45
        b.box((-w / 2, -d / 2 - 0.12, z), (w / 2, -d / 2, z + 0.32), 'MP_Wood')
    for x in (-w / 2 + 0.4, w / 2 - 0.4):
        b.box((x - 0.1, d / 2 - 0.3, 0.0), (x + 0.1, d / 2 - 0.1, sh - 0.12), 'MP_MetalDark', skip=('zn', 'zp'))
        b.box((x - 0.1, -d / 2 - 0.12, 0.0), (x + 0.1, -d / 2 + 0.08, sh + 1.25), 'MP_MetalDark', skip=('zn',))
    return b


def beach_railing():
    """beach promenade railing segment 2.5 m (6.7 studs) with concrete post footings; tile along X"""
    b = Builder('RSD_Rail_Beach')
    L, h = pm(2.5), pm(1.0)
    b.box((-L / 2, -0.35, 0.0), (L / 2, 0.35, 0.5), 'MP_Concrete', skip=('zn', 'xn', 'xp'))     # kerb
    for x in (-L / 2 + 0.2, L / 2 - 0.2):
        b.box((x - 0.18, -0.18, 0.5), (x + 0.18, 0.18, h), 'MP_Metal', skip=('zn',))
    for z in (h - 0.15, h * 0.62):
        b.cyl((-L / 2, 0, z), (L / 2, 0, z), 0.12, 6, 'MP_Metal', caps=(False, False))
    for k in range(1, 6):                                                                # balusters
        x = -L / 2 + L * k / 6
        b.box((x - 0.05, -0.05, 0.5), (x + 0.05, 0.05, h * 0.62), 'MP_Metal', skip=('zn', 'zp'))
    return b


# ---------------------------------------------------------------------------------------------------------- palms
# VIS-7.1b: geometry-only coconut palms (no textures in Roblox yet). Two MeshParts: Bark (trunk with ring bands, crown
# shaft, coconuts, hanging dead fronds) and Leaf (green fronds: curved rachis + tapered two-sided leaflets).
# Budget <= 3,000 triangles per palm. Pivot = trunk foot at the origin ('pole' anchor), lean toward +X.

def _v(x):
    from mathutils import Vector
    return Vector(x)


def _frond(b, rnd, origin, yaw, pitch, L, n_leaf, mat, droop=0.45, twist=0.6, leaf_len=3.0, rachis_r=0.16,
           seg=5, keel=0.42, leaf_w=0.2):
    """one frond: rachis = 3-sided tube along an arching curve (rises with `pitch`, sags with `droop`), n_leaf
    leaflets per side (narrow strap: base point -> widest fold -> tip, 2 triangles, two-sided), angled toward the tip, keeled down
    into a V, drooping at the tip; the leaflet plane rolls along the frond by `twist` (rad at the tip)."""
    from mathutils import Matrix, Quaternion
    O = _v(origin)
    hdir = _v((math.cos(yaw), math.sin(yaw), 0.0))
    up = _v((0, 0, 1))

    def P(s):
        u = s / L
        return O + hdir * (math.cos(pitch) * s) + up * (math.sin(pitch) * s - droop * L * u * u)

    pts = [P(L * k / seg) for k in range(seg + 1)]
    b.tube(pts, [rachis_r * (1 - 0.75 * k / seg) for k in range(seg + 1)], 3, mat, cap_end=False)
    side0 = hdir.cross(up).normalized()                   # horizontal, perpendicular to the frond
    for i in range(n_leaf):
        u = 0.1 + 0.88 * i / max(1, n_leaf - 1)
        s = L * u
        c = P(s)
        tng = (P(min(L, s + 0.05)) - P(max(0.0, s - 0.05))).normalized()
        roll = twist * u
        side = Quaternion(tng, roll) @ side0
        side = (side - tng * side.dot(tng)).normalized()
        nrm = side.cross(tng).normalized()                # 'up' of the leaflet plane
        if nrm.z < 0:
            nrm = -nrm
        ln = leaf_len * (0.45 + 0.75 * math.sin(math.pi * min(1.0, 0.15 + u * 0.95))) * rnd.uniform(0.9, 1.08)
        for sgn in (-1, 1):
            d = (side * sgn * math.cos(0.62) + tng * math.sin(0.62)).normalized()   # ~36 deg toward the tip
            d = (d * math.cos(keel) - nrm * math.sin(keel)).normalized()           # keel: V-shaped cross-section
            wdir = (tng - d * tng.dot(d)).normalized()
            base = c + side * sgn * rachis_r * 0.6
            sag = (0.25 + 0.6 * u) * ln * 0.22
            mid = base + d * (ln * 0.42) - up * (sag * 0.3)
            tip = base + d * ln - up * sag
            wm = leaf_w * rnd.uniform(0.85, 1.1)
            # narrow strap leaflet folded at its widest point: 2 triangles, two-sided
            b.poly2([base, mid - wdir * wm, mid + wdir * wm], mat)
            b.poly2([mid - wdir * wm, tip, mid + wdir * wm], mat)


def _coconut(b, c, r, mat):
    """low octahedron-ish nut (8 triangles)"""
    x, y, z = c
    v = [b._v((x + r, y, z)), b._v((x, y + r, z)), b._v((x - r, y, z)), b._v((x, y - r, z)),
         b._v((x, y, z + r * 0.9)), b._v((x, y, z - r * 1.05))]
    for i in range(4):
        j = (i + 1) % 4
        b._face([v[i], v[j], v[4]], mat)
        b._face([v[j], v[i], v[5]], mat)


def _palm(name, h_trunk, lean_deg, n_fronds, seed, frond_len, n_leaf, bands=14):
    rnd = random.Random(seed)
    b = Builder(name)
    dx = h_trunk * math.tan(math.radians(lean_deg))
    wig = rnd.uniform(-0.25, 0.25)

    def axis(t):                                          # slightly curved trunk axis, lean toward +X
        return (dx * (0.55 * t + 0.45 * t * t), wig * math.sin(math.pi * t), h_trunk * t)

    pts, radii = [], []
    r0, r1 = 0.78, 0.5
    pts.append(axis(0.0)); radii.append(r0 + 0.32)                        # root flare
    pts.append(axis(0.03)); radii.append(r0 + 0.08)
    for k in range(bands):                                                # ring bands: ridge + groove per band
        t0 = 0.05 + 0.87 * k / bands
        t1 = t0 + 0.87 / bands * 0.35
        r = r0 + (r1 - r0) * t0
        pts.append(axis(t0)); radii.append(r * 1.09)
        pts.append(axis(t1)); radii.append(r * 0.93)
    for t, r in ((0.95, r1 * 1.12), (0.985, r1 * 1.18), (1.0, r1 * 0.9)):  # crown shaft bulge
        pts.append(axis(t)); radii.append(r)
    b.tube(pts, radii, 7, 'MP_Bark', cap_end=True)
    top = _v(axis(1.0))
    # green fronds: youngest pointing up near the top, oldest drooping below; golden-angle yaw with jitter
    ga = math.radians(137.5)
    for k in range(n_fronds):
        f = k / max(1, n_fronds - 1)
        yaw = k * ga + rnd.uniform(-0.25, 0.25)
        pitch = math.radians(48 - 78 * f + rnd.uniform(-7, 7))
        L = frond_len * (0.78 + 0.3 * math.sin(math.pi * min(1.0, 0.2 + f))) * rnd.uniform(0.92, 1.06)
        o = top + _v((math.cos(yaw) * 0.25, math.sin(yaw) * 0.25, -0.15 - 0.55 * f))
        _frond(b, rnd, o, yaw, pitch, L, n_leaf, 'MP_Foliage', droop=0.32 + 0.3 * f, twist=rnd.uniform(-0.9, 0.9),
               leaf_len=frond_len * 0.27)
    # two hanging dead fronds (brown = MP_Bark part) and a coconut cluster under the crown
    for k in range(2):
        yaw = rnd.uniform(0, 2 * math.pi) if k == 0 else yaw + math.pi * rnd.uniform(0.7, 1.3)
        o = top + _v((math.cos(yaw) * 0.35, math.sin(yaw) * 0.35, -0.9))
        _frond(b, rnd, o, yaw, math.radians(-62 + rnd.uniform(-8, 8)), frond_len * 0.62, 6, 'MP_Bark',
               droop=0.12, twist=rnd.uniform(-0.4, 0.4), leaf_len=frond_len * 0.13, rachis_r=0.13, seg=3, keel=1.0,
               leaf_w=0.16)
    for k in range(6):
        a = k * 2 * math.pi / 6 + rnd.uniform(-0.3, 0.3)
        rr = 0.62 + 0.12 * (k % 2)
        _coconut(b, (top.x + math.cos(a) * rr, top.y + math.sin(a) * rr, top.z - 0.75 - 0.35 * (k % 2)), 0.42, 'MP_Bark')
    return b


def palm_a():
    """tall coconut palm (~33 studs), lean 4 deg"""
    return _palm('RSD_Palm_A', 28.0, 4.0, 13, 11, 12.5, 16)


def palm_b():
    """mid coconut palm (~29 studs), lean 7 deg"""
    return _palm('RSD_Palm_B', 25.0, 7.0, 12, 22, 12.0, 15)


def palm_c():
    """short coconut palm (~25 studs), lean 5 deg"""
    return _palm('RSD_Palm_C', 20.5, 5.0, 11, 33, 11.0, 15)


def shop_awning():
    """free-standing retractable shop awning 3 m wide (8 studs): wall bracket rail, sloped fabric, valance, arms.
    Back (the wall side) at the -Y edge of the bbox."""
    b = Builder('RSD_Awning_Shop')
    w, proj, drop = pm(3.0), pm(2.0), pm(0.6)
    z0 = pm(2.6)
    b.box((-w / 2, 0.0, z0 - 0.2), (w / 2, 0.35, z0 + 0.4), 'MP_MetalDark')
    # closed fabric slab (VIS-7.1b: the two opposite one-sided sheets read as a thin wedge in Roblox)
    b.prism([(-w / 2, 0.35, z0 + 0.3), (-w / 2, proj, z0 - drop), (-w / 2, proj, z0 - drop - 0.08),
             (-w / 2, 0.35, z0 + 0.22)], (w, 0, 0), 'MP_Awning')
    b.box((-w / 2, proj - 0.1, z0 - drop - 0.7), (w / 2, proj + 0.05, z0 - drop), 'MP_Awning')
    for x in (-w / 2 + 0.2, w / 2 - 0.2):
        b.beam((x, 0.3, z0 - 1.0), (x, proj - 0.1, z0 - drop - 0.1), 0.12, 0.12, 'MP_MetalDark')
    return b


ASSETS = [
    (light_double, prop('Light', 'Box', False, 'mesh CanCollide off; add an invisible 1x24x1 Part collider for the pole')),
    (light_single, prop('Light', 'Box', False, 'mesh CanCollide off; pole collider Part', anchor='pole')),
    (signal_housing, prop('Signal', 'Box', False, 'hang on a mast/gantry; lenses are one MeshPart (light by script)')),
    (signal_mast, prop('Signal', 'Box', False, 'mesh CanCollide off; pole collider Part', anchor='pole')),
    (utility_pole, prop('Pole', 'Box', False, 'mesh CanCollide off; pole collider Part')),
    (sign_post, prop('Sign', 'Box', False, 'blank board, UV 0..1 for a decal/texture')),
    (bus_shelter, prop('Shelter', 'PreciseConvexDecomposition', True, 'open front; decomposition keeps it walk-in')),
    (parking_barrier, prop('Barrier', 'Box', True, 'arm along +X', anchor='pole')),
    (bench, prop('Bench', 'Box', True)),
    (beach_railing, prop('Rail', 'Box', True, 'tile along X every 6.7 studs, -Z toward the walkway')),
    (palm_a, prop('Palm', 'Box', False, 'geometry fronds (rachis + two-sided leaflets), <= 3000 tris; trunk collider Part', anchor='pole')),
    (palm_b, prop('Palm', 'Box', False, 'geometry fronds (rachis + two-sided leaflets), <= 3000 tris; trunk collider Part', anchor='pole')),
    (palm_c, prop('Palm', 'Box', False, 'geometry fronds (rachis + two-sided leaflets), <= 3000 tris; trunk collider Part', anchor='pole')),
    (shop_awning, prop('Awning', 'Box', False, 'wall side at the bbox -Y/+Z(Roblox) edge')),
]

if __name__ == '__main__':
    export.main(ASSETS, 'roadside')
