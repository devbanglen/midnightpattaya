"""Facade helpers for kit modules (mount plane y = 0, street side +Y, x centred, bottom z = 0).

A module is a FRONT SHELL: the face at y = t plus window reveals, fills and protrusions. Its back (y = 0), sides and
top/bottom are left open because it sits on a building box and next to / above other modules (top modules that
stand above the roof close their back).
"""
from .units import WALL_T


def wall(b, W, H, holes, mat, t=WALL_T, recess=0.25, reveal_mat=None, x0=None, z0=0.0):
    """front wall face of width W (centred) and height H with rectangular holes [(hx0, hx1, hz0, hz1), ...].
    The holes get 4 reveal faces from the front face back to y = recess (where the fill goes)."""
    x0 = -W / 2 if x0 is None else x0
    x1 = x0 + W
    z1 = z0 + H
    xs = sorted({x0, x1, *[h[0] for h in holes], *[h[1] for h in holes]})
    zs = sorted({z0, z1, *[h[2] for h in holes], *[h[3] for h in holes]})
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            cx, cz = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            if any(h[0] < cx < h[1] and h[2] < cz < h[3] for h in holes):
                continue
            b.qn([(xs[i], t, zs[j]), (xs[i + 1], t, zs[j]), (xs[i + 1], t, zs[j + 1]), (xs[i], t, zs[j + 1])],
                 (0, 1, 0), mat)
    rm = reveal_mat or mat
    for hx0, hx1, hz0, hz1 in holes:
        if recess >= t:
            continue
        b.qn([(hx0, recess, hz1), (hx1, recess, hz1), (hx1, t, hz1), (hx0, t, hz1)], (0, 0, -1), rm)   # head
        if hz0 > z0 + 1e-6:
            b.qn([(hx0, recess, hz0), (hx1, recess, hz0), (hx1, t, hz0), (hx0, t, hz0)], (0, 0, 1), rm)  # sill
        b.qn([(hx0, recess, hz0), (hx0, t, hz0), (hx0, t, hz1), (hx0, recess, hz1)], (1, 0, 0), rm)     # jambs
        b.qn([(hx1, recess, hz0), (hx1, t, hz0), (hx1, t, hz1), (hx1, recess, hz1)], (-1, 0, 0), rm)


def fill(b, hole, y, mat):
    """flat fill (glass, shutter, dark interior) of a hole at depth y, facing the street"""
    hx0, hx1, hz0, hz1 = hole
    b.qn([(hx0, y, hz0), (hx1, y, hz0), (hx1, y, hz1), (hx0, y, hz1)], (0, 1, 0), mat)


def front_box(b, x0, x1, z0, z1, y0, y1, mat, back=False, bottom=True, top=True):
    """box in front of the wall (sills, bands, slabs, sign boxes); back face only if asked (seen from behind)"""
    skip = [] if back else ['yn']
    if not bottom:
        skip.append('zn')
    if not top:
        skip.append('zp')
    b.box((x0, y0, z0), (x1, y1, z1), mat, skip=tuple(skip))


def railing(b, x0, x1, z, y, h, mat, posts=4, bar=0.12):
    """balcony railing along x at depth y: top rail, mid rail, posts"""
    b.box((x0, y - bar, z + h - bar), (x1, y + bar, z + h), mat)
    b.box((x0, y - bar / 2, z + h * 0.45), (x1, y + bar / 2, z + h * 0.45 + bar), mat)
    for k in range(posts + 1):
        x = x0 + (x1 - x0) * k / posts
        x = min(max(x, x0 + bar / 2), x1 - bar / 2)
        b.box((x - bar / 2, y - bar / 2, z), (x + bar / 2, y + bar / 2, z + h - bar), mat, skip=('zn', 'zp'))
