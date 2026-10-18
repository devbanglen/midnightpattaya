"""bmesh primitives in studs, Blender axes (Z up). Exported with +Y up, so Blender (x, y, z) -> Roblox (x, z, -y).

Facing rule: the "front" of an asset (street side of a facade module, the side a sign/lamp faces) is Blender +Y,
which is Roblox -Z (the Front face of a Roblox part).

Builder collects faces with a material name each; finish() (in common/export.py) optimises and splits them per
material into child meshes.
"""
import math
import bmesh
from mathutils import Vector, Matrix

from .units import MAX_MATERIALS

_BOX_FACES = {  # outward CCW windings for the 8-vertex box layout used in Builder.box
    'zn': (0, 3, 2, 1), 'zp': (4, 5, 6, 7), 'yn': (0, 1, 5, 4),
    'yp': (2, 3, 7, 6), 'xn': (3, 0, 4, 7), 'xp': (1, 2, 6, 5),
}


class Builder:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.keep = self.bm.faces.layers.int.new('uvkeep')   # 1 = UVs set by the primitive (cards, sign panels)
        self.mats = []

    # ---------------------------------------------------------------- internals
    def _mi(self, mat):
        from .materials import MATERIALS
        if mat not in MATERIALS:
            raise ValueError(f'{self.name}: material {mat} is not in the shared list')
        if mat not in self.mats:
            self.mats.append(mat)
            if len(self.mats) > MAX_MATERIALS:
                raise ValueError(f'{self.name}: more than {MAX_MATERIALS} materials: {self.mats}')
        return self.mats.index(mat)

    def _face(self, verts, mat, smooth=False, uvs=None):
        f = self.bm.faces.new(verts)
        f.material_index = self._mi(mat)
        f.smooth = smooth
        if uvs:
            for loop, uv in zip(f.loops, uvs):
                loop[self.uv].uv = uv
            f[self.keep] = 1
        return f

    def _v(self, co):
        return self.bm.verts.new(co)

    # ---------------------------------------------------------------- primitives
    def box(self, lo, hi, mat, skip=(), m=None):
        """axis-aligned box from corner lo to corner hi; skip = faces left out ('zn' bottom, 'yn' back, ...);
        m = optional Matrix applied to the 8 corners (rotation about the origin, then translation)."""
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        cs = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
              (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        if m is not None:
            cs = [m @ Vector(c) for c in cs]
        vs = [self._v(c) for c in cs]
        for k, idx in _BOX_FACES.items():
            if k not in skip:
                self._face([vs[i] for i in idx], mat)

    def boxc(self, c, size, mat, skip=(), rot=None):
        """box by centre + size, optionally rotated (Matrix 3x3/4x4 or Euler) about its centre"""
        hx, hy, hz = (s / 2 for s in size)
        m = Matrix.Translation(Vector(c))
        if rot is not None:
            m = m @ (rot.to_matrix().to_4x4() if hasattr(rot, 'to_matrix') else rot.to_4x4())
        self.box((-hx, -hy, -hz), (hx, hy, hz), mat, skip, m)

    def beam(self, p0, p1, w, h, mat, skip_ends=False):
        """square-section bar from p0 to p1 (w across, h vertical-ish)"""
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        L = d.length
        q = d.normalized().to_track_quat('Z', 'Y')
        m = Matrix.Translation(p0) @ q.to_matrix().to_4x4()
        self.box((-w / 2, -h / 2, 0), (w / 2, h / 2, L), mat, ('zn', 'zp') if skip_ends else (), m)

    def cyl(self, p0, p1, r, seg, mat, caps=(True, True), r1=None, smooth=True):
        """cylinder / cone frustum along p0 -> p1 (radius r at p0, r1 at p1)"""
        p0, p1 = Vector(p0), Vector(p1)
        r1 = r if r1 is None else r1
        d = p1 - p0
        q = d.normalized().to_track_quat('Z', 'Y')
        R = q.to_matrix()
        a, b = [], []
        for i in range(seg):
            t = 2 * math.pi * i / seg
            c, s = math.cos(t), math.sin(t)
            a.append(self._v(p0 + R @ Vector((c * r, s * r, 0))))
            b.append(self._v(p1 + R @ Vector((c * r1, s * r1, 0))))
        for i in range(seg):
            j = (i + 1) % seg
            self._face([a[i], a[j], b[j], b[i]], mat, smooth)
        if caps[0] and r > 1e-6:
            self._face(list(reversed(a)), mat)
        if caps[1] and r1 > 1e-6:
            self._face(b, mat)

    def tube(self, pts, radii, seg, mat, cap_end=True, cap_start=False, smooth=True):
        """swept ring along a polyline (palm trunks, curved lamp arms). Ring frames use the averaged tangent."""
        pts = [Vector(p) for p in pts]
        rings = []
        up = Vector((0, 0, 1))
        for k, p in enumerate(pts):
            t = (pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)]).normalized()
            side = t.cross(up)
            if side.length < 1e-4:
                side = Vector((1, 0, 0))
            side.normalize()
            nrm = side.cross(t).normalized()
            ring = []
            for i in range(seg):
                a = 2 * math.pi * i / seg
                ring.append(self._v(p + (side * math.cos(a) + nrm * math.sin(a)) * radii[k]))
            rings.append(ring)
        for k in range(len(rings) - 1):
            A, B = rings[k], rings[k + 1]
            for i in range(seg):
                j = (i + 1) % seg
                self._face([A[i], B[i], B[j], A[j]], mat, smooth)
        if cap_end:      # rings run clockwise seen from +tangent, so the end cap is reversed
            self._face(list(reversed(rings[-1])), mat)
        if cap_start:
            self._face(list(rings[0]), mat)

    def qn(self, verts, n, mat, uvs=None):
        """polygon whose winding is fixed so its normal points along n (any vertex order accepted)"""
        vs = [Vector(v) for v in verts]
        nn = Vector((0, 0, 0))
        for i in range(len(vs)):                      # Newell normal
            a, c = vs[i], vs[(i + 1) % len(vs)]
            nn += Vector(((a.y - c.y) * (a.z + c.z), (a.z - c.z) * (a.x + c.x), (a.x - c.x) * (a.y + c.y)))
        if nn.dot(Vector(n)) < 0:
            vs.reverse()
            uvs = list(reversed(uvs)) if uvs else None
        return self._face([self._v(v) for v in vs], mat, uvs=uvs)

    def quad(self, v0, v1, v2, v3, mat, uvs=None, double=False):
        """single quad, CCW = front; double adds a back face (separate verts so normals stay clean)"""
        vs = [self._v(Vector(v)) for v in (v0, v1, v2, v3)]
        self._face(vs, mat, uvs=uvs)
        if double:
            vb = [self._v(Vector(v)) for v in (v3, v2, v1, v0)]
            self._face(vb, mat, uvs=list(reversed(uvs)) if uvs else None)

    def card(self, pts, widths, normal_hint, mat, double=True):
        """alpha-ready strip (palm frond): quads along pts, width per point, UV u across 0..1, v along 0..1"""
        pts = [Vector(p) for p in pts]
        n = len(pts)
        L = [0.0]
        for k in range(1, n):
            L.append(L[-1] + (pts[k] - pts[k - 1]).length)
        for k in range(n - 1):
            t = (pts[k + 1] - pts[k]).normalized()
            side = t.cross(Vector(normal_hint)).normalized()
            a0, a1 = pts[k] - side * widths[k] / 2, pts[k] + side * widths[k] / 2
            b0, b1 = pts[k + 1] - side * widths[k + 1] / 2, pts[k + 1] + side * widths[k + 1] / 2
            v0, v1 = L[k] / L[-1], L[k + 1] / L[-1]
            self.quad(a0, a1, b1, b0, mat, uvs=[(0, v0), (1, v0), (1, v1), (0, v1)], double=double)

    def panel(self, x0, x1, z0, z1, y, mat, uv01=True):
        """front-facing (+Y) flat panel at depth y, UV 0..1 (sign boards; seen from +Y, x0 is on the right)"""
        self.quad((x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0), mat,
                  uvs=[(1, 0), (1, 1), (0, 1), (0, 0)] if uv01 else None)
