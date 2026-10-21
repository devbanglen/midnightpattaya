"""Original design v2 of the red sports car (offline, numpy + Pillow only; no Blender, no network).

Owner decision 2026-10-21: the fictional-brand car (red_sports_fictional) still reads as a Ferrari 812 Superfast.
This pass changes the SHAPE cues, not only paint, and writes a separate set (the inputs are never touched):

  python tools/gpu/car_original_v2.py build <cars_dir> <out_dir> [--source <tripo car.glb>] [--id red_sports_original_v2]

Input: <cars_dir>/red_sports_fictional.glb (+ red_sports.glb for the badge mask). Output in <out_dir>:
  <id>.glb (default paint, midnight blue), <id>_red.glb, <id>_white.glb  (body, one material, one 1024^2 texture)
  <id>_wheel_FL/FR/RL/RR.glb   new procedural wheels (one set for every paint)
  <id>_wheels.json             layout (same axle centres and radius 0.3848 as red_sports), upload BLOCKED marker
  <id>_build.json              what was changed, numbers per step
  <id>_emblem.png              the MP emblem decals cut out of the shipped textures (body 224 px, wheel cap 256 px)

  python tools/gpu/car_original_v2.py grid <out.png> <view1,view2,...> "<render_dir>|<id>|<tag>|<label>" ...
      QA sheet from tools/blender/car_debrand_render.py renders (one row per view, one column per car)

What changes (frame N: X right, Y up, front -Z, metres; numbers in REGIONS / SHELLS below):
  geometry  - the swept headlight recess area is repainted and new lamps are modelled on top: a straight twin-
              projector lamp bar and a separate vertical LED "fang" at each outer bumper corner;
            - the deep scallop / outlet behind each front wheel is filled (vertices put on a surface fitted to the
              wing around it) and three stepped horizontal gills are modelled instead;
            - the four twin-pod tail-lamp recesses are filled; a new full-width light blade with turned-down ends
              is modelled on the flat tail;
            - the four outboard round exhausts and the centre fog lamp are collapsed into the diffuser; two
              rectangular outlets are modelled between the inner diffuser fins;
            - a body-colour blade across the grille;
            - new wheels: tyre, 10-blade turbine rim, hub cap with the emblem, brake disc (no caliper: it would spin);
  texture   - the body atlas is re-packed (the Tripo atlas used 30 % of the 1024^2 image), sampled from the 2048^2
              Tripo source texture where given (else the 1024^2 build): 1.27x the texel density (1.6x the texels) on
              the visible surfaces, fewer on the underside;
            - 1024 x 128 px at the bottom of the atlas hold the new parts' graphics: the "MP" emblem is 224 px wide
              there (it was ~10 texels on the old atlas);
            - paint: midnight blue (default), red, white.
Tri budgets: body <= 20,000, each wheel <= 2,500. Wheels: origin = axle centre, axle along X, bounding box centred
on the origin (Roblox centres a MeshPart on its bounding box), radius 0.3848 exactly.
"""
import hashlib
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_debrand as cd  # noqa: E402

WHEELS = cd.WHEELS
SRC_ID = 'red_sports_fictional'
BADGE_ID = 'red_sports'
DEFAULT_ID = 'red_sports_original_v2'
ATLAS = 1024
DECAL_Y = 896                       # rows DECAL_Y..1023 = graphics of the new parts
PAINTS = {                          # suffix -> (name, rgb)
    '': ('midnight blue', (34, 52, 112)),
    '_red': ('red', None),          # None = keep the source red (cleaned)
    '_white': ('white', (226, 228, 230)),
}
WHEEL_R = 0.3848
UPLOAD = 'BLOCKED until the owner confirms the licence (Tripo terms for the body source; see docs)'

# ------------------------------------------------------------------------------------------------- decal atlas --
# name -> (x0, y0, x1, y1) px in the 1024^2 body atlas (bottom strip)
DECALS = {
    'emblem': (4, 900, 228, 1012),
    'hl_main': (240, 900, 752, 948),
    'tail': (240, 952, 1020, 976),
    'hl_drl': (760, 900, 1020, 916),
    'gill': (760, 920, 1020, 944),
    'blade': (240, 982, 600, 1006),
    'metal': (610, 982, 740, 1006),
    'black': (750, 982, 800, 1006),
    'wall': (810, 982, 860, 1006),
    'paint': (870, 982, 1020, 1006),
}


def decal_uv(name, u, v, inset=2.0):
    x0, y0, x1, y1 = DECALS[name]
    return np.stack([(x0 + inset + np.asarray(u) * (x1 - x0 - 2 * inset)) / ATLAS,
                     (y0 + inset + np.asarray(v) * (y1 - y0 - 2 * inset)) / ATLAS], -1)


# --------------------------------------------------------------------------------------------------- GLB write --
def glb_build(path, name, pos, nrm, uv, idx, img, mat_name, generator='MIDNIGHT PATTAYA car_original_v2.py'):
    """One node, one mesh, one primitive, one material with an embedded PNG base colour."""
    pos = np.ascontiguousarray(pos, np.float32)
    nrm = np.ascontiguousarray(nrm, np.float32)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    uv = np.ascontiguousarray(uv, np.float32)
    ib = np.ascontiguousarray(idx, np.uint32).ravel()
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    parts = [pos.tobytes(), nrm.tobytes(), uv.tobytes(), ib.tobytes(), buf.getvalue()]
    views, binc = [], bytearray()
    for i, p in enumerate(parts):
        binc += b'\0' * ((-len(binc)) % 4)
        v = {'buffer': 0, 'byteOffset': len(binc), 'byteLength': len(p)}
        if i < 3:
            v['target'] = 34962
        elif i == 3:
            v['target'] = 34963
        views.append(v)
        binc += p
    binc += b'\0' * ((-len(binc)) % 4)
    js = {'asset': {'version': '2.0', 'generator': generator}, 'scene': 0, 'scenes': [{'nodes': [0]}],
          'nodes': [{'name': name, 'mesh': 0}],
          'meshes': [{'name': name, 'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2},
                                                    'indices': 3, 'material': 0}]}],
          'accessors': [
              {'bufferView': 0, 'componentType': 5126, 'count': len(pos), 'type': 'VEC3',
               'min': pos.min(0).tolist(), 'max': pos.max(0).tolist()},
              {'bufferView': 1, 'componentType': 5126, 'count': len(nrm), 'type': 'VEC3'},
              {'bufferView': 2, 'componentType': 5126, 'count': len(uv), 'type': 'VEC2'},
              {'bufferView': 3, 'componentType': 5125, 'count': len(ib), 'type': 'SCALAR'}],
          'materials': [{'name': mat_name, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0},
                                                                     'metallicFactor': 0.0, 'roughnessFactor': 0.5}}],
          'textures': [{'sampler': 0, 'source': 0}], 'samplers': [{'magFilter': 9729, 'minFilter': 9987}],
          'images': [{'name': mat_name + '_basecolor', 'mimeType': 'image/png', 'bufferView': 4}],
          'bufferViews': views, 'buffers': [{'byteLength': len(binc)}]}
    cd.glb_write(path, js, bytes(binc))


# ------------------------------------------------------------------------------------------------ ray casting --
def raycast(orig, dirs, pos, nrm, idx, chunk=24):
    """Nearest hit of each ray on the triangles. Returns hit point, interpolated normal, ok mask."""
    tv = pos[idx]
    v0, e1, e2 = tv[:, 0], tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0]
    n = len(orig)
    H, NN, ok = np.zeros((n, 3)), np.zeros((n, 3)), np.zeros(n, bool)
    for i0 in range(0, n, chunk):
        o, d = orig[i0:i0 + chunk, None], dirs[i0:i0 + chunk, None]
        p = np.cross(d, e2[None])
        det = (e1[None] * p).sum(-1)
        good = np.abs(det) > 1e-12
        inv = np.where(good, 1 / np.where(good, det, 1), 0)
        s = o - v0[None]
        u = (s * p).sum(-1) * inv
        q = np.cross(s, e1[None])
        v = (d * q).sum(-1) * inv
        t = (e2[None] * q).sum(-1) * inv
        hit = good & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (t > 1e-6)
        t = np.where(hit, t, np.inf)
        k = np.argmin(t, 1)
        r = np.arange(len(k))
        tk = t[r, k]
        uk, vk = u[r, k], v[r, k]
        good_r = np.isfinite(tk)
        H[i0:i0 + chunk] = orig[i0:i0 + chunk] + dirs[i0:i0 + chunk] * np.where(good_r, tk, 0)[:, None]
        ii = idx[k]
        w = np.stack([1 - uk - vk, uk, vk], 1)
        nn = (w[:, :, None] * nrm[ii]).sum(1)
        NN[i0:i0 + chunk] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        ok[i0:i0 + chunk] = good_r
    return H, NN, ok


def tris_near(pos, idx, lo, hi):
    c = pos[idx]
    m = np.all((c.max(1) >= lo) & (c.min(1) <= hi), axis=1)
    return idx[m]


# ---------------------------------------------------------------------------------------------- region refit --
def poly_terms(a, b, deg):
    t = [np.ones_like(a), a, b]
    if deg >= 2:
        t += [a * a, a * b, b * b]
    if deg >= 3:
        t += [a ** 3, a * a * b, a * b * b, b ** 3]
    return np.stack(t, 1)


def poly_grad(coef, a, b, deg):
    ga = coef[1] + (2 * coef[3] * a + coef[4] * b if deg >= 2 else 0) + \
        (3 * coef[6] * a * a + 2 * coef[7] * a * b + coef[8] * b * b if deg >= 3 else 0)
    gb = coef[2] + (coef[4] * a + 2 * coef[5] * b if deg >= 2 else 0) + \
        (coef[7] * a * a + 2 * coef[8] * a * b + 3 * coef[9] * b * b if deg >= 3 else 0)
    return np.broadcast_to(ga, np.shape(a)).astype(float), np.broadcast_to(gb, np.shape(a)).astype(float)


def refit(pos, nrm, sel, ring, out_dir, deg, depth, report, name, up=0.03, weight=None):
    """Put the selected vertices on a surface fitted to the ring vertices. out_dir = the outward direction of the
    surface (unit vector); the height h = p . out_dir is fitted as a polynomial of the two in-plane coordinates.
    Robust: the fit is repeated keeping only the outer layer of the ring (h >= fit - 1 cm), so inner parts seen
    through gaps do not drag it in. Only vertices from `depth` m inside to `up` m outside the fit move. Normals
    become the fit's normals. Topology / UVs unchanged."""
    n0 = np.asarray(out_dir, float)
    n0 /= np.linalg.norm(n0)
    e1 = np.cross(n0, (0, 1, 0) if abs(n0[1]) < 0.9 else (1, 0, 0))
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n0, e1)
    a, b, val = pos @ e1, pos @ e2, pos @ n0
    keep = ring.copy()
    for _ in range(4):
        A = poly_terms(a[keep], b[keep], deg)
        coef = np.linalg.lstsq(A, val[keep], rcond=None)[0]
        f_r = poly_terms(a[ring], b[ring], deg) @ coef
        k2 = ring & np.zeros(len(pos), bool)
        k2[np.nonzero(ring)[0][val[ring] >= f_r - 0.01]] = True
        if k2.sum() < 3 * A.shape[1] or (k2 == keep).all():
            break
        keep = k2
    A = poly_terms(a[keep], b[keep], deg)
    res = np.abs(A @ coef - val[keep])
    f = poly_terms(a, b, deg) @ coef
    mv = sel & (val > f - depth) & (val < f + up)
    moved = np.abs(val[mv] - f[mv])
    w = np.ones(int(mv.sum())) if weight is None else weight[mv]
    pos[mv] += np.outer((f[mv] - val[mv]) * w, n0)
    ga, gb = poly_grad(coef, a[mv], b[mv], deg)
    n = n0[None] - ga[:, None] * e1[None] - gb[:, None] * e2[None]
    n = n / np.linalg.norm(n, axis=1, keepdims=True)
    n = n * w[:, None] + nrm[mv] * (1 - w[:, None])
    nrm[mv] = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    report['geometry'].append({'name': name, 'verts_moved': int(mv.sum()), 'ring_verts': int(ring.sum()),
                               'ring_used': int(keep.sum()), 'fit_degree': deg,
                               'fit_rms_m': round(float(np.sqrt((res ** 2).mean())), 4),
                               'max_move_m': round(float(moved.max()) if len(moved) else 0.0, 4)})
    return mv


def smooth_normals_band(pos, nrm, moved, idx):
    """Recompute the normals (area-weighted, vertices welded by position) of every vertex that shares a triangle
    with a moved vertex, so the old crease shading does not survive around the filled areas. In place on nrm."""
    key = np.round(pos / 1e-5).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    tp = pos[idx]
    fn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
    acc = np.zeros((weld.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, weld[idx[:, k]], fn)
    band = np.zeros(len(pos), bool)
    touch = moved[idx].any(1)
    band[idx[touch].ravel()] = True
    band &= ~moved                       # moved vertices keep the fitted surface's normals
    n = acc[weld[band]]
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ok = ln[:, 0] > 1e-12
    bi = np.nonzero(band)[0]
    nrm[bi[ok]] = n[ok] / ln[ok]
    return pos


WHEEL_CIRCLE = 0.47     # keep the arch (wheel centre distance in y/z) out of the side refit


def _inside(p, lo, hi):
    return np.all((p >= lo) & (p <= hi), axis=1)


def mean_normal(nrm, m):
    v = nrm[m].mean(0)
    return v / np.linalg.norm(v)


def fill_geometry(pos, nrm, lay, report, idx):
    """Fill the recesses of the old signature cues (vertex moves only)."""
    pos_in = pos
    pos, nrm = pos.copy(), nrm.copy()
    x, y, z = pos[:, 0], pos[:, 1], pos[:, 2]
    moved = np.zeros(len(pos), bool)
    for side, key in ((-1, 'FL'), (1, 'FR')):
        tag = key[1]
        sx = np.array([side, 1, 1.0])
        # 1. side scallop / outlet behind the front wheel -> smooth wing surface (x = f(y, z))
        wc = lay['wheels'][key]
        far = np.hypot(y - wc[1], z - wc[2]) > WHEEL_CIRCLE
        box = (z > -0.97) & (z < -0.22) & (y > -0.44) & (y < 0.17)
        big = (z > -1.10) & (z < -0.05) & (y > -0.50) & (y < 0.28)
        outer = x * side > 0.78
        ring = big & ~box & outer & far & (nrm[:, 0] * side > 0.7)
        inset = np.min(np.stack([z + 0.97, -0.22 - z, y + 0.44, 0.17 - y,
                                 np.hypot(y - wc[1], z - wc[2]) - WHEEL_CIRCLE], 1), 1)
        soft = np.clip(inset / 0.04, 0, 1) ** 0.7
        moved |= refit(pos, nrm, box & outer & far, ring, (side, 0, 0), 3, 0.18, report, f'side_scallop_{tag}',
                       up=0.12, weight=soft)
        # 2. swept headlight recess -> smooth nose / wing surface, fitted along the area's mean normal
        lo, hi = np.array([0.48, -0.175, -2.14]), np.array([0.985, 0.16, -1.48])
        clear = np.hypot(y - wc[1], z - wc[2]) > 0.50          # not the arch liner under the wing
        reg = _inside(pos * sx, lo, hi) & clear
        big = _inside(pos * sx, lo - (0.0, 0.07, 0.07), hi + (0.03, 0.07, 0.10)) & clear
        nd = mean_normal(nrm, big)
        ring = big & ~reg & ((nrm @ nd) > 0.75)
        q = pos * sx
        inset = np.min(np.stack([q[:, 0] - lo[0], hi[0] - q[:, 0], q[:, 1] - lo[1], hi[1] - q[:, 1],
                                 q[:, 2] - lo[2], hi[2] - q[:, 2]], 1), 1)
        soft = np.clip(inset / 0.03, 0, 1) ** 0.7
        moved |= refit(pos, nrm, reg, ring, nd, 3, 0.30, report, f'headlight_recess_{tag}', weight=soft)
        # 3. twin tail-lamp pod recesses -> flat tail (z = f(x, y))
        reg = (x * side > 0.45) & (x * side < 0.975) & (y > 0.03) & (y < 0.228) & (z > 1.78)
        big = (x * side > 0.40) & (x * side < 1.0) & (y > -0.04) & (y < 0.29) & (z > 1.78)
        ring = big & ~reg & (nrm[:, 2] > 0.55)
        moved |= refit(pos, nrm, reg, ring, (0, 0, 1), 2, 0.26, report, f'tail_pods_{tag}')
        # 4. outboard exhaust housing with the twin round tips -> one flat panel
        reg = (x * side > 0.52) & (x * side < 0.95) & (y > -0.50) & (y < -0.30) & (z > 1.80)
        big = (x * side > 0.42) & (x * side < 1.0) & (y > -0.30) & (y < -0.20) & (z > 1.80)
        ring = big & (nrm[:, 2] > 0.6)
        moved |= refit(pos, nrm, reg, ring, (0, 0, 1), 1, 0.30, report, f'exhaust_housing_{tag}', up=0.02)
        # 5. bonnet slash vents -> smooth bonnet (y = f(x, z))
        reg = (x * side > 0.26) & (x * side < 0.52) & (z > -1.80) & (z < -1.38) & (y > 0.0)
        big = (x * side > 0.18) & (x * side < 0.62) & (z > -1.92) & (z < -1.26) & (y > 0.0)
        ring = big & ~reg & (nrm[:, 1] > 0.7)
        moved |= refit(pos, nrm, reg, ring, (0, 1, 0), 2, 0.08, report, f'bonnet_vent_{tag}')
    # 6. centre bonnet vent
    reg = (np.abs(x) < 0.28) & (z > -1.36) & (z < -1.10) & (y > 0.0)
    big = (np.abs(x) < 0.40) & (z > -1.48) & (z < -0.98) & (y > 0.0)
    moved |= refit(pos, nrm, reg, big & ~reg & (nrm[:, 1] > 0.7), (0, 1, 0), 2, 0.08, report, 'bonnet_vent_centre')
    # 7. centre fog lamp in the diffuser
    reg = (np.abs(x) < 0.085) & (y > -0.425) & (y < -0.29) & (z > 1.85)
    big = (np.abs(x) < 0.13) & (y > -0.46) & (y < -0.25) & (z > 1.85)
    moved |= refit(pos, nrm, reg, big & ~reg & (nrm[:, 2] > 0.6), (0, 0, 1), 1, 0.15, report, 'fog_lamp')
    pos = smooth_normals_band(pos, nrm, moved, idx)
    # never grow the bounding box: Roblox centres the MeshPart on it, so the wheel layout depends on it
    lo, hi = pos_in.min(0), pos_in.max(0)
    pos = np.clip(pos, lo, hi)
    return pos, nrm, moved


# -------------------------------------------------------------------------------------------- new parts (shells) --
class Parts:
    """Accumulates new geometry (vertices, normals, UVs, triangles) in body space."""

    def __init__(self):
        self.P, self.N, self.UV, self.T = [], [], [], []
        self.n = 0
        self.log = []

    def add(self, P, N, UV, T, name):
        P, N, UV, T = map(np.asarray, (P, N, UV, T))
        # winding: every triangle faces along its vertices' normals
        tp = P[T]
        fn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
        flip = (fn * N[T].sum(1)).sum(1) < 0
        T = T.copy()
        T[flip] = T[flip][:, ::-1]
        self.P.append(P)
        self.N.append(N)
        self.UV.append(UV)
        self.T.append(T + self.n)
        self.n += len(P)
        self.log.append({'name': name, 'verts': int(len(P)), 'tris': int(len(T))})

    def arrays(self):
        return (np.concatenate(self.P), np.concatenate(self.N), np.concatenate(self.UV), np.concatenate(self.T))


def _project(pts2, frame, body):
    """2D screen points -> body surface: 3D = o + a*e1 + b*e2 - d*0.6, ray along d."""
    o, e1, e2, d = (np.asarray(frame[k], float) for k in ('o', 'e1', 'e2', 'd'))
    d = d / np.linalg.norm(d)
    p3 = o + pts2[:, :1] * e1 + pts2[:, 1:2] * e2 - d * 0.6
    far = p3 + d * 5.0
    lo = np.minimum(p3.min(0), far.min(0)) - 0.02
    hi = np.maximum(p3.max(0), far.max(0)) + 0.02
    sub = tris_near(body[0], body[3], lo, hi)
    H, NN, ok = raycast(p3, np.repeat(d[None], len(p3), 0), body[0], body[1], sub)
    if not ok.all():
        raise RuntimeError(f'{int((~ok).sum())} shell points missed the body ({frame.get("name")})')
    return H, NN


def _walls(parts, top, topn, loop, offset, sink, uvname, name, centre):
    """Side walls from the raised boundary down below the surface (closed loop of top-vertex indices)."""
    P, N, UV, T = [], [], [], []
    m = len(loop)
    for k in range(m):
        i, j = loop[k], loop[(k + 1) % m]
        a, b = top[i], top[j]
        a2, b2 = a - topn[i] * (offset + sink), b - topn[j] * (offset + sink)
        e = b - a
        out = np.cross(e, topn[i] + topn[j])
        mid = (a + b) / 2 - centre
        mid -= (topn[i] + topn[j]) / 2 * (mid @ ((topn[i] + topn[j]) / 2))
        if out @ mid < 0:
            out = -out
        out /= max(np.linalg.norm(out), 1e-9)
        base = len(P)
        P += [a, b, b2, a2]
        N += [out] * 4
        UV += list(decal_uv(uvname, np.array([0, 1, 1, 0]), np.array([0, 0, 1, 1])))
        T += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    parts.add(P, N, UV, T, name + '_walls')


def strip_shell(parts, body, pts, hw, frame, uvname, name, step=0.03, across=1, offset=0.003, sink=0.008,
                taper=None, walls=False):
    """A raised band of half-width hw (m) along a 2D polyline, conformed to the body surface."""
    pts = np.asarray(pts, float)
    dense = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        k = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        dense += [a + (b - a) * (i / k) for i in range(1, k + 1)]
    dense = np.array(dense)
    L = len(dense)
    seg = np.diff(dense, axis=0)
    seg /= np.linalg.norm(seg, axis=1, keepdims=True)
    tang = np.zeros_like(dense)
    tang[0], tang[-1] = seg[0], seg[-1]
    tang[1:-1] = seg[:-1] + seg[1:]
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    perp = np.stack([-tang[:, 1], tang[:, 0]], 1)
    miter = np.ones(L)
    miter[1:-1] = 1 / np.maximum(0.5, (perp[1:-1] * np.stack([-seg[:-1, 1], seg[:-1, 0]], 1)).sum(1))
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    s = arc / arc[-1]
    w = hw * (np.interp(s, *taper) if taper else 1.0)
    grid = np.zeros((L, across + 1, 2))
    for j in range(across + 1):
        t = -1 + 2 * j / across
        grid[:, j] = dense + perp * (t * w * miter)[:, None]
    H, NN = _project(grid.reshape(-1, 2), frame, body)
    top = H + NN * offset
    U = np.repeat(s, across + 1)
    V = np.tile(np.linspace(0, 1, across + 1), L)
    UV = decal_uv(uvname, U, V)
    T = []
    for i in range(L - 1):
        for j in range(across):
            a = i * (across + 1) + j
            T += [[a, a + across + 1, a + across + 2], [a, a + across + 2, a + 1]]
    parts.add(top, NN, UV, T, name)
    loop = [j for j in range(across + 1)] + [i * (across + 1) + across for i in range(1, L)] + \
        [(L - 1) * (across + 1) + j for j in range(across - 1, -1, -1)] + [i * (across + 1) for i in range(L - 2, 0, -1)]
    if walls:
        _walls(parts, top, NN, loop, offset, sink, 'wall', name, top.mean(0))
    return {'points': L * (across + 1), 'length_m': round(float(arc[-1]), 3)}


def capsule_shell(parts, body, size, frame, name, rings=2, nb=32, offset=0.003, sink=0.006, walls=False):
    """The MP emblem: a capsule (half-length 0.29, radius 0.21, x size) conformed to the surface, UV = planar map
    into the 224 x 112 px emblem decal (badge coords x in [-0.5, 0.5], y in [-0.25, 0.25])."""
    t = np.linspace(0, 2 * np.pi, nb, endpoint=False)
    hl, r = 0.29, 0.21
    # outline: right half-circle, top line, left half-circle, bottom line (param by angle around the capsule)
    ox, oy = [], []
    for a in t:
        c, s_ = math.cos(a), math.sin(a)
        cx = hl if c >= 0 else -hl
        ox.append(cx + r * c)
        oy.append(r * s_)
    outline = np.stack([ox, oy], 1)
    pts = [np.zeros(2)]
    for k in range(1, rings + 1):
        pts += list(outline * (k / rings))
    pts = np.array(pts)
    H, NN = _project(pts * size, frame, body)
    top = H + NN * offset
    UV = decal_uv('emblem', pts[:, 0] + 0.5, 0.5 - pts[:, 1] * 2, inset=0.0)
    T = [[0, 1 + i, 1 + (i + 1) % nb] for i in range(nb)]
    for k in range(1, rings):
        b0, b1 = 1 + (k - 1) * nb, 1 + k * nb
        for i in range(nb):
            i2 = (i + 1) % nb
            T += [[b0 + i, b1 + i, b1 + i2], [b0 + i, b1 + i2, b0 + i2]]
    parts.add(top, NN, UV, T, name)
    loop = [1 + (rings - 1) * nb + i for i in range(nb)]
    if walls:
        _walls(parts, top, NN, loop, offset, sink, 'wall', name, top.mean(0))


def outlet_shell(parts, body, cx, cy, hx, hy, rad, name, z_lip=0.025, depth=0.07, nper=5):
    """A rectangular exhaust outlet with rounded corners on the rear (d = -Z): outer wall, front ring, inner wall,
    dark back cap."""
    pts = []
    for qx, qy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccy = cx + qx * (hx - rad), cy + qy * (hy - rad)
        for i in range(nper + 1):
            a = math.radians(a0 + 90 * i / nper)
            pts.append((ccx + rad * math.cos(a), ccy + rad * math.sin(a)))
    pts = np.array(pts)
    n = len(pts)
    frame = {'o': (0, 0, 3.0), 'e1': (1, 0, 0), 'e2': (0, 1, 0), 'd': (0, 0, -1), 'name': name}
    H, NN = _project(pts, frame, body)
    zf = H[:, 2].max() + z_lip
    cen = np.array([cx, cy])
    inner2 = cen + (pts - cen) * np.array([(hx - 0.012) / hx, (hy - 0.012) / hy])
    outer_front = np.c_[pts, np.full(n, zf)]
    inner_front = np.c_[inner2, np.full(n, zf)]
    inner_back = np.c_[inner2, np.full(n, zf - depth)]
    base_pts = H - np.array([0, 0, 0.01])
    radial = np.c_[(pts - cen) / np.linalg.norm(pts - cen, axis=1, keepdims=True), np.zeros(n)]
    P, N, UV, T = [], [], [], []

    def ring_quads(A, B, nA, nB, uvname):
        b = len(P)
        for k in range(n):
            P.append(A[k]); N.append(nA[k]); UV.append(decal_uv(uvname, k / n, 0.0))
            P.append(B[k]); N.append(nB[k]); UV.append(decal_uv(uvname, k / n, 1.0))
        for k in range(n):
            k2 = (k + 1) % n
            T.extend([[b + 2 * k, b + 2 * k2, b + 2 * k2 + 1], [b + 2 * k, b + 2 * k2 + 1, b + 2 * k + 1]])
    ring_quads(base_pts, outer_front, radial, radial, 'metal')                                   # outer wall
    zf_n = np.tile([0, 0, 1.0], (n, 1))
    ring_quads(outer_front, inner_front, zf_n, zf_n, 'metal')                                   # front lip
    ring_quads(inner_front, inner_back, -radial, -radial, 'black')                              # inner wall
    b = len(P)
    P.append(np.array([cx, cy, zf - depth])); N.append(np.array([0, 0, 1.0])); UV.append(decal_uv('black', 0.5, 0.5))
    for k in range(n):
        P.append(inner_back[k]); N.append(np.array([0, 0, 1.0])); UV.append(decal_uv('black', 0.5, 0.5))
    for k in range(n):
        T.append([b, b + 1 + k, b + 1 + (k + 1) % n])
    parts.add(P, N, UV, T, name)


def front_frame(name, z0=-2.0, tilt=0.2):
    """Screen coords (x, y) are exact on the plane z = z0; rays come slightly from above (tilt)."""
    return {'o': (0, 0, z0), 'e1': (1, 0, 0), 'e2': (0, 1, 0), 'd': (0, -tilt, 1.0), 'name': name}


def rear_frame(name):
    return {'o': (0, 0, 3.0), 'e1': (1, 0, 0), 'e2': (0, 1, 0), 'd': (0, 0, -1.0), 'name': name}


def side_frame(side, name):
    return {'o': (2.0 * side, 0, 0), 'e1': (0, 0, 1), 'e2': (0, 1, 0), 'd': (-side, 0, 0), 'name': name}


SHELLS = {
    'hl_main': {'pts': [(0.855, 0.046), (0.74, 0.034), (0.605, 0.017)], 'hw': 0.022},
    'hl_drl': {'pts': [(0.905, -0.045), (0.895, -0.225)], 'hw': 0.010},
    'grille_blade': {'pts': [(-0.44, -0.355), (0.44, -0.355)], 'hw': 0.014},
    'gills': [{'pts': [(-0.86, 0.045), (-0.50, 0.065)], 'hw': 0.011},
              {'pts': [(-0.84, -0.025), (-0.53, -0.008)], 'hw': 0.011},
              {'pts': [(-0.80, -0.095), (-0.56, -0.080)], 'hw': 0.011}],
    'tail': {'pts': [(-0.905, 0.035), (-0.93, 0.150), (0.93, 0.150), (0.905, 0.035)], 'hw': 0.011},
    'outlets': [(-0.27, -0.395, 0.072, 0.030, 0.016), (0.27, -0.395, 0.072, 0.030, 0.016)],
    'emblem_nose': {'centre': (0.0, -0.128), 'size': 0.11},
    'emblem_tail': {'centre': (0.0, 0.080), 'size': 0.12},
}


def build_parts(body):
    parts = Parts()
    rep = {}
    S = SHELLS
    for side in (-1, 1):
        sx = np.array([side, 1.0])
        tag = 'L' if side < 0 else 'R'
        pts = np.array(S['hl_main']['pts']) * sx
        rep['headlight_' + tag] = strip_shell(parts, body, pts, S['hl_main']['hw'], front_frame('hl', -2.0, 0.1), 'hl_main',
                                              'headlight_' + tag, across=2, step=0.02, offset=0.004, walls=True)
        pts = np.array(S['hl_drl']['pts']) * sx
        rep['drl_' + tag] = strip_shell(parts, body, pts, S['hl_drl']['hw'], front_frame('drl', -2.05), 'hl_drl',
                                        'drl_' + tag, offset=0.004, walls=True)
        for gi, g in enumerate(S['gills']):
            rep[f'gill{gi}_{tag}'] = strip_shell(parts, body, g['pts'], g['hw'], side_frame(side, 'gill'), 'gill',
                                                 f'gill{gi}_{tag}', taper=([0, 0.15, 1], [0.55, 1, 1]), offset=0.005)
    rep['grille_blade'] = strip_shell(parts, body, S['grille_blade']['pts'], S['grille_blade']['hw'],
                                      front_frame('blade', -2.2, 0.0), 'blade', 'grille_blade', offset=0.006)
    rep['tail_blade'] = strip_shell(parts, body, S['tail']['pts'], S['tail']['hw'], rear_frame('tail'), 'tail',
                                    'tail_blade')
    for i, (cx, cy, hx, hy, r) in enumerate(S['outlets']):
        outlet_shell(parts, body, cx, cy, hx, hy, r, f'outlet_{i}')
    e = S['emblem_nose']
    fr = front_frame('emblem_nose', -2.17, 0.12)
    fr['o'] = (e['centre'][0], e['centre'][1], -2.17)
    capsule_shell(parts, body, e['size'], fr, 'emblem_nose')
    e = S['emblem_tail']
    fr = rear_frame('emblem_tail')
    fr['o'] = (e['centre'][0], e['centre'][1], 3.0)
    capsule_shell(parts, body, e['size'], fr, 'emblem_tail')
    return parts, rep


# --------------------------------------------------------------------------------------------- atlas re-pack --
def islands(idx, nverts):
    par = np.arange(nverts)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for t in idx:
        r0 = find(t[0])
        for v in t[1:]:
            r = find(v)
            if r != r0:
                par[r] = r0
    roots = np.array([find(v) for v in range(nverts)])
    tri_root = roots[idx[:, 0]]
    _, lab = np.unique(tri_root, return_inverse=True)
    return lab


def _island_masks(uvp, idx, lab, n, lo, scale, pad):
    """Per island: occupancy mask (rows = v, cols = u) of its triangles at the given scale, grown by pad px."""
    from PIL import ImageDraw
    order = np.argsort(lab, kind='stable')
    starts = np.searchsorted(lab[order], np.arange(n + 1))
    masks = []
    for i in range(n):
        tri = idx[order[starts[i]:starts[i + 1]]]
        t = (uvp[tri] - lo[i]) * scale[i] + pad
        w = int(math.ceil(t[..., 0].max() + pad)) + 1
        h = int(math.ceil(t[..., 1].max() + pad)) + 1
        im = Image.new('L', (w, h), 0)
        dr = ImageDraw.Draw(im)
        for tt in t:
            dr.polygon([tuple(p) for p in tt], fill=255, outline=255)
        m = np.asarray(im) > 0
        if pad >= 1:
            g = m.copy()
            for _ in range(int(pad)):
                g = g | np.roll(g, 1, 0) | np.roll(g, -1, 0) | np.roll(g, 1, 1) | np.roll(g, -1, 1)
            m = g
        masks.append(m)
    return masks


def _skyline_pack(masks, W, H):
    """Top-down skyline packing of bitmap masks (each may be turned 90 degrees). Uses the jagged top/bottom
    profile of each mask, not its bounding box. Returns [(x, y, rot)] or None if it overflows H."""
    from numpy.lib.stride_tricks import sliding_window_view
    sky = np.zeros(W, np.int64)
    out = [None] * len(masks)
    order = sorted(range(len(masks)), key=lambda i: -max(masks[i].shape))
    for i in order:
        best = None
        for rot in (0, 1):
            m = masks[i] if rot == 0 else masks[i].T[::-1]
            h, w = m.shape
            if w > W:
                continue
            occ = m.any(0)
            top = np.where(occ, m.argmax(0), 0)
            bot = np.where(occ, h - m[::-1].argmax(0), 0)
            win = sliding_window_view(sky, w)
            ys = np.max(np.where(occ[None], win - top[None], -10 ** 9), 1)
            ys = np.maximum(ys, 0)
            x = int(np.argmin(ys + 0.0 * np.arange(len(ys))))
            y = int(ys[x])
            cand = (y + h, y, x, rot, bot, occ)
            if best is None or cand[:2] < best[:2]:
                best = cand
        yh, y, x, rot, bot, occ = best
        if yh > H:
            return None
        w = len(occ)
        sky[x:x + w] = np.where(occ, y + bot, sky[x:x + w])
        out[i] = (x, y, rot)
    return out


def repack_uv(pos, uv, idx, report, pad=2.0):
    lab = islands(idx, len(pos))
    n = lab.max() + 1
    uvp = uv * ATLAS
    lo = np.full((n, 2), np.inf)
    hi = np.full((n, 2), -np.inf)
    for k in range(3):
        np.minimum.at(lo, lab, uvp[idx[:, k]])
        np.maximum.at(hi, lab, uvp[idx[:, k]])
    # weight: islands that are never seen (underside, deep inside) get fewer texels
    tc = pos[idx].mean(1)
    cy = np.bincount(lab, tc[:, 1], n) / np.bincount(lab, None, n)
    cx = np.bincount(lab, np.abs(tc[:, 0]), n) / np.bincount(lab, None, n)
    weight = np.where(cy < -0.50, 0.45, np.where((cx < 0.62) & (cy < 0.25) & (cy > -0.35), 0.75, 1.0))
    a, b = 0.8, 2.5
    best = None
    for _ in range(9):
        s = (a + b) / 2
        masks = _island_masks(uvp, idx, lab, n, lo, s * weight, pad)
        p = _skyline_pack(masks, ATLAS, DECAL_Y)
        if p is None:
            b = s
        else:
            a, best = s, (p, masks)
    if best is None:
        raise RuntimeError('atlas re-pack failed even at scale 0.8')
    s = a
    place, masks = best
    vlab = np.zeros(len(pos), int)
    for k in range(3):
        vlab[idx[:, k]] = lab
    sc = (s * weight)[vlab]
    loc = (uvp - lo[vlab]) * sc[:, None] + pad                     # in the island's mask frame (u, v)
    new = np.zeros_like(uv)
    for i in range(n):
        x, y, rot = place[i]
        vm = vlab == i
        if rot == 0:
            q = loc[vm]
        else:                                                      # mask.T[::-1]: (row, col) -> (w-1-col, row)
            w = masks[i].shape[1]
            q = np.stack([loc[vm, 1], w - loc[vm, 0]], 1)
        new[vm] = (q + (x, y)) / ATLAS
    report['atlas'] = {'islands': int(n), 'packer': 'skyline over island bitmaps, 90-degree turns, 2 px gutter',
                       'scale_exterior': round(float(s), 3), 'scale_underside': round(float(s * 0.45), 3),
                       'scale_interior_cabin': round(float(s * 0.75), 3),
                       'packed_rows': DECAL_Y, 'decal_rows': ATLAS - DECAL_Y}
    return new


def raster_bary(uv, idx, W, H):
    """Per texel: triangle id (-1 = none) and barycentric weights, texel centre inside the UV triangle."""
    T = -np.ones((H, W), np.int64)
    B = np.zeros((H, W, 3))
    t = uv[idx] * (W, H)
    for k in range(len(idx)):
        (x0, y0), (x1, y1), (x2, y2) = t[k]
        lx, hx = int(max(0, math.floor(min(x0, x1, x2) - 0.5))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        ly, hy = int(max(0, math.floor(min(y0, y1, y2) - 0.5))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if hx < lx or hy < ly:
            continue
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(lx, hx + 1) + 0.5, np.arange(ly, hy + 1) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
        c = 1 - a - b
        e = -0.02
        ins = (a >= e) & (b >= e) & (c >= e)
        if not ins.any():
            continue
        ii, jj = np.nonzero(ins)
        T[ii + ly, jj + lx] = k
        B[ii + ly, jj + lx] = np.stack([a[ins], b[ins], c[ins]], 1)
    return T, B


def bilinear(img, uv):
    """img (H, W, 3) float, uv (..., 2) glTF (top-left origin) -> colours."""
    Hh, Ww = img.shape[:2]
    x = np.clip(uv[..., 0] * Ww - 0.5, 0, Ww - 1.001)
    y = np.clip(uv[..., 1] * Hh - 0.5, 0, Hh - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) +
            img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def resample_body(pos, nrm, uv_old, uv_new, idx, base_hi, fict, badge_mask):
    """New atlas texels <- old texture at the corresponding old UV. base_hi: the Tripo source (2048^2) or the
    fictional build (1024^2); texels the fictional pass repainted (badge_mask, at 1024) come from `fict`."""
    T, B = raster_bary(uv_new, idx, ATLAS, ATLAS)
    M = T >= 0
    tri = idx[T[M]]
    w = B[M]
    w = np.clip(w, 0, None)
    w /= w.sum(1, keepdims=True)
    ouv = (w[:, :, None] * uv_old[tri]).sum(1)
    col = bilinear(base_hi, ouv)
    bm = bilinear(badge_mask[..., None].astype(float), ouv)[:, 0]
    col = col * (1 - bm[:, None]) + bilinear(fict, ouv) * bm[:, None]
    img = np.zeros((ATLAS, ATLAS, 3))
    img[M] = col
    P = np.zeros((ATLAS, ATLAS, 3))
    N = np.zeros((ATLAS, ATLAS, 3))
    P[M] = (w[:, :, None] * pos[tri]).sum(1)
    nn = (w[:, :, None] * nrm[tri]).sum(1)
    N[M] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
    return img, P, N, M


def pad_gutters(img, M, steps=6):
    cover = M.copy()
    out = img.copy()
    for _ in range(steps):
        acc = np.zeros_like(out)
        cnt = np.zeros(M.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            s = np.roll(np.roll(cover, dy, 0), dx, 1)
            acc += np.roll(np.roll(out, dy, 0), dx, 1) * s[..., None]
            cnt += s
        g = (cnt > 0) & ~cover
        out[g] = acc[g] / cnt[g][:, None]
        cover |= g
    return out


# -------------------------------------------------------------------------------------------------- painting --
def masked_blur(a, m, r=2):
    acc = np.zeros_like(a)
    cnt = np.zeros(m.shape)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = np.roll(np.roll(m, dy, 0), dx, 1)
            acc += np.roll(np.roll(a, dy, 0), dx, 1) * (s[..., None] if a.ndim == 3 else s)
            cnt += s
    cnt = np.maximum(cnt, 1)
    return acc / (cnt[..., None] if a.ndim == 3 else cnt)


def body_fills(img, P, N, M, lay, report):
    """Paint over the old cues that the new geometry replaces (texture side)."""
    rgb = np.clip(img / 255, 0, 1)
    h, s, v = cd.hsv(rgb)
    paint = M & (((h < 22) | (h > 335)) & (s > 0.5) & (v > 0.25))
    dark = M & (v < 0.2)
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ax = np.abs(x)
    fills = []
    hl = M & (ax > 0.50) & (ax < 0.97) & (y > -0.16) & (y < 0.15) & (z > -2.12) & (z < -1.50) & (N[..., 1] > -0.5)
    fills.append(('old_swept_headlights', hl, 'paint', 0.07))
    tail = M & (z > 1.78) & (N[..., 2] > 0.15) & (y > -0.02) & (y < 0.24) & (ax < 0.985)
    fills.append(('old_tail_pods_and_bar', tail, 'paint', 0.07))
    nose = M & (np.linalg.norm(P - np.array([0.0, -0.128, -2.167]), axis=2) < 0.075)
    fills.append(('old_nose_badge', nose & ~paint, 'paint', 0.06))
    for side, key in ((-1, 'FL'), (1, 'FR')):
        wc = lay['wheels'][key]
        far = np.hypot(y - wc[1], z - wc[2]) > WHEEL_CIRCLE + 0.01
        sc = M & (x * side > 0.76) & (z > -0.99) & (z < -0.15) & (y > -0.45) & (y < 0.18) & far & (N[..., 0] * side > 0.3)
        fills.append((f'old_side_scallop_{key[1]}', sc, 'paint', 0.07))
    ex = M & (ax > 0.51) & (ax < 0.995) & (y > -0.56) & (y < -0.295) & (z > 1.80)
    ex |= M & (ax < 0.095) & (y > -0.435) & (y < -0.28) & (z > 1.85)
    fills.append(('old_exhausts_fog_lamp', ex, 'dark', 0.06))
    bv = M & (y > 0.0) & (N[..., 1] > 0.3) & (((ax > 0.25) & (ax < 0.53) & (z > -1.81) & (z < -1.37)) |
                                              ((ax < 0.29) & (z > -1.37) & (z < -1.09)))
    fills.append(('old_bonnet_vents', bv, 'paint', 0.06))
    out = img.copy()
    done = np.zeros(M.shape, bool)
    for name, sel, src, ringd in fills:
        lo = P[sel].min(0) - ringd if sel.any() else None
        if lo is None:
            report['fills'].append({'name': name, 'texels': 0})
            continue
        hi = P[sel].max(0) + ringd
        near = M & np.all((P >= lo) & (P <= hi), axis=2) & ~sel & ~done
        source = near & (paint if src == 'paint' else dark)
        n = cd.idw_fill(out, P, sel, source, k=24)
        done |= sel
        report['fills'].append({'name': name, 'texels': n, 'fill_from': src, 'source_texels': int(source.sum())})
    return out, done


def recolour(img, M, target, report, key):
    rgb = np.clip(img / 255, 0, 1)
    h, s, v = cd.hsv(rgb)
    red = M & ((h < 25) | (h > 330)) & (s > 0.28) & (v > 0.06)
    core = red & (s > 0.6) & (v > 0.3)
    ref_v = float(np.median(v[core]))
    ref_rgb = np.median(img[core], 0)
    ratio = v / ref_v
    ratio_s = masked_blur(ratio, red, 2)
    ratio = np.where(red, 0.45 * ratio + 0.55 * ratio_s, ratio)
    T = np.asarray(ref_rgb if target is None else target, float)
    base = T[None, None] * np.minimum(ratio, 1.0)[..., None]
    hi_ = (255 - T)[None, None] * np.clip(ratio - 1.0, 0, 1)[..., None] * 0.55
    new = base + hi_
    alpha = np.clip((s - 0.28) / 0.3, 0, 1)[..., None]
    grey = (v * 255)[..., None] * np.ones(3)
    mix = alpha * new + (1 - alpha) * (0.5 * grey + 0.5 * new)
    out = img.copy()
    out[red] = mix[red]
    report['paint'][key] = {'texels': int(red.sum()), 'reference_rgb': [int(c) for c in ref_rgb],
                            'target_rgb': [int(c) for c in T]}
    return out, T


def draw_decals(img, paint_rgb):
    """The graphics of the new parts in the bottom strip of the atlas."""
    def region(name):
        x0, y0, x1, y1 = DECALS[name]
        ys, xs = np.mgrid[y0:y1, x0:x1]
        u = (xs + 0.5 - x0) / (x1 - x0)
        v = (ys + 0.5 - y0) / (y1 - y0)
        return (slice(y0, y1), slice(x0, x1)), u, v

    def smooth(e0, e1, t):
        t = np.clip((t - e0) / (e1 - e0), 0, 1)
        return t * t * (3 - 2 * t)
    pr = np.asarray(paint_rgb, float)
    # headlight bar: smoked housing, LED line on top, two square projectors, a teal accent line at the bottom
    sl, u, v = region('hl_main')
    W = DECALS['hl_main'][2] - DECALS['hl_main'][0]
    H_ = DECALS['hl_main'][3] - DECALS['hl_main'][1]
    c = np.zeros(u.shape + (3,))
    c[:] = (22, 25, 32)
    c += (np.array((38, 40, 48)) * (1 - v)[..., None]) * 0.6
    led = np.exp(-((v - 0.14) / 0.055) ** 2)
    c = c * (1 - led[..., None]) + np.array((246, 250, 255)) * led[..., None]
    for uc in (0.30, 0.52):
        du = np.abs(u - uc) * W / H_
        dv = np.abs(v - 0.58)
        sq = np.maximum(du, dv)
        ring = (sq < 0.24) & (sq > 0.17)
        lens = sq <= 0.17
        c[ring] = (150, 156, 166)
        c[lens] = (60, 66, 80)
        core = np.hypot(du, dv) < 0.07
        c[core] = (228, 236, 250)
    c[v > 0.88] = (0, 168, 170)
    img[sl] = c
    # DRL fang: white LED with a grey frame
    sl, u, v = region('hl_drl')
    c = np.zeros(u.shape + (3,))
    c[:] = (70, 74, 82)
    core = smooth(0.2, 0.32, v) * (1 - smooth(0.68, 0.8, v))
    img[sl] = c * (1 - core[..., None]) + np.array((250, 252, 255)) * core[..., None]
    # tail blade: dark red lens, bright red core line
    sl, u, v = region('tail')
    c = np.zeros(u.shape + (3,))
    c[:] = (60, 6, 10)
    core = np.exp(-((v - 0.5) / 0.16) ** 2)
    c = c * (1 - core[..., None]) + np.array((255, 40, 44)) * core[..., None]
    edge = (v < 0.17) | (v > 0.83)
    c[edge] = (24, 22, 24)
    img[sl] = c
    # gills: black slot with a teal top edge
    sl, u, v = region('gill')
    c = np.zeros(u.shape + (3,))
    c[:] = (12, 12, 14)
    c[v < 0.22] = (0, 150, 152)
    c[(v >= 0.22) & (v < 0.4)] = (36, 38, 42)
    img[sl] = c
    # grille blade: body paint with a soft highlight on top
    sl, u, v = region('blade')
    shade = 0.75 + 0.45 * np.exp(-((v - 0.3) / 0.25) ** 2)
    img[sl] = np.clip(pr[None, None] * shade[..., None], 0, 255)
    for name, col in (('metal', (150, 152, 158)), ('black', (8, 8, 10)), ('wall', (28, 29, 32)), ('paint', pr)):
        sl, u, v = region(name)
        img[sl] = col
        if name == 'metal':
            img[sl] = np.array((95, 98, 104)) + np.array((90, 90, 92)) * np.exp(-((v - 0.5) / 0.3) ** 2)[..., None]
    # emblem: MP capsule (car_debrand.emblem_rgba), on the paint colour so the anti-aliased rim blends in
    sl, u, v = region('emblem')
    bx, by = u - 0.5, (0.5 - v) * 0.5
    cw = DECALS['emblem'][2] - DECALS['emblem'][0]
    col, a = cd.emblem_rgba(bx.ravel() / 1.0, by.ravel(), 'capsule', aa=1.2 / cw)
    col = col.reshape(u.shape + (3,))
    a = a.reshape(u.shape)[..., None]
    img[sl] = col * a + pr[None, None] * (1 - a)
    return img


# ----------------------------------------------------------------------------------------------- the wheels --
TYRE = [(0.150, 0.272), (0.164, 0.300), (0.172, 0.335), (0.168, 0.362), (0.155, 0.378), (0.122, WHEEL_R),
        (-0.122, WHEEL_R), (-0.155, 0.378), (-0.168, 0.362), (-0.172, 0.335), (-0.164, 0.300), (-0.150, 0.272)]
LIP = [(0.150, 0.274), (0.157, 0.266), (0.152, 0.257), (0.136, 0.252), (-0.140, 0.252)]
WT = {'tyre': (0, 0, 512, 160), 'rim': (0, 160, 256, 192), 'blade': (256, 160, 512, 224),
      'dark': (0, 192, 256, 224), 'black': (0, 224, 64, 256), 'disc': (0, 256, 256, 512),
      'cap': (256, 256, 512, 512)}
FACE_X = 0.118


def wuv(name, u, v, inset=1.5):
    x0, y0, x1, y1 = WT[name]
    return np.stack([(x0 + inset + np.asarray(u, float) * (x1 - x0 - 2 * inset)) / 512,
                     (y0 + inset + np.asarray(v, float) * (y1 - y0 - 2 * inset)) / 512], -1)


def revolve(prof, nseg, uvname, outward, vrange=(0, 1)):
    """Surface of revolution about X. prof: (x, r) points; outward(+1/-1) picks the normal side."""
    prof = np.asarray(prof, float)
    m = len(prof)
    th = np.linspace(0, 2 * np.pi, nseg + 1)
    d = np.gradient(prof, axis=0)
    n2 = np.stack([-d[:, 1], d[:, 0]], 1) * outward            # (nx, nr)
    n2 /= np.linalg.norm(n2, axis=1, keepdims=True)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(prof, axis=0), axis=1))])
    vv = vrange[0] + (vrange[1] - vrange[0]) * arc / arc[-1]
    P, N, UV = [], [], []
    for t in th:
        c, s = math.cos(t), math.sin(t)
        for i in range(m):
            x, r = prof[i]
            P.append((x, r * c, r * s))
            N.append((n2[i, 0], n2[i, 1] * c, n2[i, 1] * s))
            UV.append(wuv(uvname, t / (2 * np.pi), vv[i]))
    T = []
    for k in range(nseg):
        for i in range(m - 1):
            a, b = k * m + i, (k + 1) * m + i
            T += [[a, b, b + 1], [a, b + 1, a + 1]]
    return np.array(P), np.array(N), np.array(UV), np.array(T)


def disc(x, r0, r1, nseg, nx, uvname, planar=True, ring_uv=None):
    th = np.linspace(0, 2 * np.pi, nseg, endpoint=False)
    P, N, UV, T = [], [], [], []
    if r0 == 0:
        P.append((x, 0, 0)); N.append((nx, 0, 0)); UV.append(wuv(uvname, 0.5, 0.5))
        for t in th:
            P.append((x, r1 * math.cos(t), r1 * math.sin(t))); N.append((nx, 0, 0))
            UV.append(wuv(uvname, 0.5 + 0.5 * math.cos(t), 0.5 + 0.5 * math.sin(t)))
        T = [[0, 1 + i, 1 + (i + 1) % nseg] for i in range(nseg)]
    else:
        for t in th:
            for r in (r0, r1):
                P.append((x, r * math.cos(t), r * math.sin(t))); N.append((nx, 0, 0))
                rr = r / r1 * 0.5
                UV.append(wuv(uvname, 0.5 + rr * math.cos(t), 0.5 + rr * math.sin(t)))
        for i in range(nseg):
            a, b = 2 * i, 2 * ((i + 1) % nseg)
            T += [[a, b, b + 1], [a, b + 1, a + 1]]
    return np.array(P, float), np.array(N, float), np.array(UV, float), np.array(T)


def blades(nb=10, r0=0.072, r1=0.254, sweep=38.0, segs=8, thick=0.034):
    P, N, UV, T = [], [], [], []
    for bi in range(nb):
        th0 = 2 * np.pi * bi / nb
        front, back = [], []
        for i in range(segs + 1):
            f = i / segs
            r = r0 + (r1 - r0) * f
            th = th0 + math.radians(sweep) * f ** 1.25
            w = 0.017 + 0.017 * f                              # half-width (tangential), m
            x = FACE_X - 0.028 * f
            tan = np.array([0, -math.sin(th), math.cos(th)])
            rad = np.array([0, math.cos(th), math.sin(th)])
            c = np.array([x, 0, 0]) + rad * r
            for sgn in (-1, 1):
                front.append(c + tan * w * sgn)
                back.append(c + tan * w * sgn - np.array([thick, 0, 0]))
        front, back = np.array(front), np.array(back)
        # front face
        b = len(P)
        for i in range(segs + 1):
            for j, sgn in enumerate((-1, 1)):
                P.append(front[2 * i + j]); N.append((1, 0, 0)); UV.append(wuv('blade', i / segs, j))
        for i in range(segs):
            a = b + 2 * i
            T += [[a, a + 2, a + 3], [a, a + 3, a + 1]]
        # side walls (two edges)
        for j in (0, 1):
            b = len(P)
            for i in range(segs + 1):
                p, q = front[2 * i + j], back[2 * i + j]
                other = front[2 * i + 1 - j]
                nrm = p - other
                nrm[0] = 0
                nrm /= np.linalg.norm(nrm)
                P += [p, q]; N += [nrm, nrm]
                UV += [wuv('dark', i / segs, 0), wuv('dark', i / segs, 1)]
            for i in range(segs):
                a = b + 2 * i
                T += [[a, a + 2, a + 3], [a, a + 3, a + 1]]
    return np.array(P, float), np.array(N, float), np.array(UV, float), np.array(T)


def make_wheel(side):
    """side +1 = right wheel (outer face +X), -1 = left (mirrored; the cap emblem reads correctly on both)."""
    pieces = [revolve(TYRE, 48, 'tyre', -1),
              revolve(LIP, 48, 'rim', 1),            # lip faces +X, barrel faces the axle
              blades(),
              revolve([(FACE_X + 0.008, 0.074), (FACE_X - 0.040, 0.074)], 24, 'dark', -1),
              disc(FACE_X + 0.008, 0.0, 0.074, 24, 1.0, 'cap'),
              disc(-0.020, 0.100, 0.195, 32, 1.0, 'disc'),
              disc(-0.060, 0.0, 0.256, 32, 1.0, 'black'),   # closes the wheel (overlaps the barrel)
              disc(-0.061, 0.0, 0.275, 32, -1.0, 'black')]  # inner side: closed up to the tyre bead
    P, N, UV, T = [], [], [], []
    n = 0
    for p, nn, uv, t in pieces:
        p, nn, t = p.copy(), nn.copy(), t.copy()
        tp = p[t]
        fn = np.cross(tp[:, 1] - tp[:, 0], tp[:, 2] - tp[:, 0])
        flip = (fn * nn[t].sum(1)).sum(1) < 0
        t[flip] = t[flip][:, ::-1]
        P.append(p); N.append(nn); UV.append(uv); T.append(t + n)
        n += len(p)
    P, N, UV, T = (np.concatenate(a) for a in (P, N, UV, T))
    cap = slice(sum(len(pc[0]) for pc in pieces[:4]), sum(len(pc[0]) for pc in pieces[:5]))
    # cap UV so the emblem reads from outside: viewer's right = -Z (right wheel) / +Z (left wheel), up = +Y
    cp = P[cap]
    UV[cap] = wuv('cap', 0.5 + (-cp[:, 2] * side) / 0.148, 0.5 - cp[:, 1] / 0.148)
    if side < 0:
        P[:, 0] *= -1
        N[:, 0] *= -1
        T = T[:, ::-1]
    return P, N, UV, T


def wheel_texture():
    img = np.zeros((512, 512, 3))
    # tyre: sidewalls dark rubber with one fine ring, tread with 3 grooves and sipes
    x0, y0, x1, y1 = WT['tyre']
    ys, xs = np.mgrid[y0:y1, x0:x1]
    u = (xs + 0.5) / 512
    v = (ys + 0.5 - y0) / (y1 - y0)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(np.array(TYRE), axis=0), axis=1))])
    a = arc / arc[-1]
    tread = (v > a[5]) & (v < a[6])
    c = np.zeros(u.shape + (3,))
    c[:] = (30, 30, 32)
    side_t = np.where(v < 0.5, v / a[5], (1 - v) / (1 - a[6]))
    c += (np.array((10, 10, 11)) * np.clip(side_t, 0, 1)[..., None])
    ringl = (np.abs(side_t - 0.45) < 0.035) & ~tread
    c[ringl] = (52, 53, 56)
    tv = (v - a[5]) / (a[6] - a[5])
    groove = tread & ((np.abs(tv - 0.25) < 0.03) | (np.abs(tv - 0.5) < 0.03) | (np.abs(tv - 0.75) < 0.03))
    sipe = tread & ((u * 96) % 1 < 0.12) & ((tv < 0.22) | (tv > 0.78))
    c[tread] = (36, 36, 38)
    c[groove | sipe] = (14, 14, 15)
    img[y0:y1, x0:x1] = c
    # rim lip / barrel: gunmetal with a bright machined lip
    x0, y0, x1, y1 = WT['rim']
    v = (np.mgrid[y0:y1, x0:x1][0] + 0.5 - y0) / (y1 - y0)
    img[y0:y1, x0:x1] = np.where((v < 0.45)[..., None], np.array((196, 200, 208.0)), np.array((58, 62, 70.0)))
    # blade face: gunmetal centre, diamond-cut bright edges
    x0, y0, x1, y1 = WT['blade']
    ys, xs = np.mgrid[y0:y1, x0:x1]
    u = (xs + 0.5 - x0) / (x1 - x0)
    v = (ys + 0.5 - y0) / (y1 - y0)
    c = np.zeros(u.shape + (3,))
    c[:] = (62, 66, 74)
    c += np.array((18, 18, 20)) * (1 - u)[..., None]
    edge = (v < 0.16) | (v > 0.84)
    c[edge] = (206, 210, 218)
    img[y0:y1, x0:x1] = c
    x0, y0, x1, y1 = WT['dark']
    img[y0:y1, x0:x1] = (40, 42, 47)
    x0, y0, x1, y1 = WT['black']
    img[y0:y1, x0:x1] = (9, 9, 10)
    # brake disc: grey ring with slots, dark hat
    x0, y0, x1, y1 = WT['disc']
    ys, xs = np.mgrid[y0:y1, x0:x1]
    dx = (xs + 0.5 - x0) / (x1 - x0) - 0.5
    dy = (ys + 0.5 - y0) / (y1 - y0) - 0.5
    rr = np.hypot(dx, dy) * 2
    ang = np.arctan2(dy, dx)
    c = np.zeros(dx.shape + (3,))
    c[:] = (118, 120, 124)
    slot = (np.abs(((ang * 12 / np.pi) + rr * 3) % 2 - 1) < 0.08) & (rr > 0.6) & (rr < 0.95)
    c[slot] = (60, 61, 64)
    c[rr < 0.55] = (48, 50, 54)
    img[y0:y1, x0:x1] = c
    # centre cap: the MP disc emblem at 256 px
    x0, y0, x1, y1 = WT['cap']
    ys, xs = np.mgrid[y0:y1, x0:x1]
    bx = (xs + 0.5 - x0) / (x1 - x0) - 0.5
    by = 0.5 - (ys + 0.5 - y0) / (y1 - y0)
    col, al = cd.emblem_rgba(bx.ravel() * 1.04, by.ravel() * 1.04, 'disc', aa=1.2 / 256)
    col = col.reshape(bx.shape + (3,))
    al = al.reshape(bx.shape)[..., None]
    img[y0:y1, x0:x1] = col * al + cd.SILVER * (1 - al)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------------------------------------------- build --
def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def build(cars_dir, out_dir, cid=DEFAULT_ID, source=None):
    if cid in (SRC_ID, BADGE_ID) or not cid.startswith('red_sports_original'):
        raise SystemExit(f'refusing id {cid!r}: the inputs must never be overwritten')
    os.makedirs(out_dir, exist_ok=True)
    lay, body, _ = cd.load_car(cars_dir, SRC_ID)
    _, bbody, _ = cd.load_car(cars_dir, BADGE_ID)
    pos, nrm, uv, idx = body['mesh']
    report = {'id': cid, 'from': SRC_ID, 'geometry': [], 'parts': {}, 'fills': [], 'paint': {},
              'upload': UPLOAD,
              'inputs': {f: sha256(os.path.join(cars_dir, f)) for f in (f'{SRC_ID}.glb', f'{BADGE_ID}.glb')}}
    # 1. geometry: fill the old cue recesses
    pos2, nrm2, moved = fill_geometry(pos, nrm, lay, report, idx)
    # 2. new parts conformed to the filled body
    parts, prep = build_parts((pos2, nrm2, uv, idx))
    report['parts'] = {'shells': prep, 'pieces': parts.log}
    # 3. atlas re-pack and resample
    fict = np.asarray(body['img'], float)
    badge = np.asarray(bbody['img'], float)
    badge_mask = (np.abs(fict - badge).max(2) > 18)
    if source:
        sjs, sb = cd.glb_read(source)
        base_hi = np.asarray(cd.image_of(sjs, sb), float)
        report['texture_source'] = {'file': os.path.basename(source), 'sha256': sha256(source),
                                    'size': list(base_hi.shape[:2])}
    else:
        base_hi = fict
        report['texture_source'] = {'file': f'{SRC_ID}.glb (1024^2 build texture; no source given)'}
    uv_new = repack_uv(pos2, uv, idx, report)
    img, P, N, M = resample_body(pos2, nrm2, uv, uv_new, idx, base_hi, fict, badge_mask)
    img, filled = body_fills(img, P, N, M, lay, report)
    pP, pN, pUV, pT = parts.arrays()
    allP = np.concatenate([pos2, pP])
    allN = np.concatenate([nrm2, pN])
    allUV = np.concatenate([uv_new, pUV])
    allT = np.concatenate([idx, pT + len(pos2)])
    # centre on the bounding box (Roblox centres a MeshPart on it): the layout stays valid only if the box is unchanged
    lo, hi = allP.min(0), allP.max(0)
    report['bbox_shift_m'] = [round(float(c), 5) for c in (lo + hi) / 2]
    report['tris'] = {'body_old': int(len(idx)), 'new_parts': int(len(pT)), 'body_total': int(len(allT))}
    outputs = {}
    for suffix, (pname, target) in PAINTS.items():
        im2, T = recolour(img, M, target, report, pname)
        im2 = pad_gutters(im2, M, 6)
        im2 = draw_decals(im2, T)
        tex = Image.fromarray(np.clip(im2, 0, 255).astype(np.uint8))
        name = cid + suffix
        glb_build(os.path.join(out_dir, name + '.glb'), name, allP, allN, allUV, allT, tex, name + '_paint')
        outputs[suffix or 'default'] = {'paint': pname, 'rgb': [int(c) for c in T], 'body': name + '.glb'}
        if not suffix:
            tex_default = tex
    # 4. wheels
    wt = wheel_texture()
    files, wrep = {}, {}
    for k in WHEELS:
        side = -1 if k[1] == 'L' else 1
        P_, N_, UV_, T_ = make_wheel(side)
        files[k] = f'{cid}_wheel_{k}.glb'
        glb_build(os.path.join(out_dir, files[k]), f'{cid}_wheel_{k}', P_, N_, UV_, T_, wt, f'{cid}_wheel')
        lo, hi = P_.min(0), P_.max(0)
        wrep[k] = {'tris': int(len(T_)), 'bbox_centre': [round(float(c), 5) for c in (lo + hi) / 2],
                   'radius': round(float(np.hypot(P_[:, 1], P_[:, 2]).max()), 5),
                   'width': round(float(hi[0] - lo[0]), 4)}
    report['wheels'] = wrep
    lay2 = json.loads(json.dumps(lay))
    lay2.pop('fictional_brand', None)
    lay2['wheel_meshes'] = files
    lay2['rim'] = [62, 66, 74]
    lay2['per_wheel'] = {k: {'r': wrep[k]['radius'], 'w': wrep[k]['width'],
                             'bbox_yz_vs_axle_m': round(float(np.hypot(*wrep[k]['bbox_centre'][1:])), 5)}
                         for k in WHEELS}
    lay2['original_v2'] = {'from': SRC_ID, 'paints': outputs, 'emblem': 'MP (Midnight Pattaya), own design',
                           'upload': UPLOAD}
    json.dump(lay2, open(os.path.join(out_dir, f'{cid}_wheels.json'), 'w'), indent=1)
    emblem_sheet(os.path.join(out_dir, f'{cid}_emblem.png'), tex_default, wt)
    json.dump(report, open(os.path.join(out_dir, f'{cid}_build.json'), 'w'), indent=1)
    print(json.dumps({k: report[k] for k in ('geometry', 'tris', 'atlas', 'wheels', 'bbox_shift_m')}, indent=1))
    return report


def emblem_sheet(path, body_tex, wheel_tex):
    """The emblem exactly as it ships: the body decal (224 x 112 px) and the wheel-cap decal (256 x 256 px), cut out
    of the textures and enlarged 2x without filtering, so the texel sharpness can be judged."""
    x0, y0, x1, y1 = DECALS['emblem']
    a = body_tex.crop((x0, y0, x1, y1))
    cx0, cy0, cx1, cy1 = WT['cap']
    b = wheel_tex.crop((cx0, cy0, cx1, cy1))
    a = a.resize((a.width * 2, a.height * 2), Image.NEAREST)
    b = b.resize((b.width * 2, b.height * 2), Image.NEAREST)
    sh = Image.new('RGB', (a.width + b.width + 30, max(a.height, b.height) + 20), 'white')
    sh.paste(a, (10, 10 + (b.height - a.height) // 2))
    sh.paste(b, (a.width + 20, 10))
    sh.save(path, optimize=True)


def grid(out_path, names, columns, tile=480):
    """QA sheet: one row per view name, one column per (render_dir, id, tag, label); renders come from
    tools/blender/car_debrand_render.py (<dir>/<id>_<tag>_<name>.png)."""
    from PIL import ImageDraw
    rows = [n for n in names if all(os.path.isfile(os.path.join(d, f'{i}_{t}_{n}.png')) for d, i, t, _ in columns)]
    sh = Image.new('RGB', (len(columns) * tile, len(rows) * (tile + 22)), 'white')
    dr = ImageDraw.Draw(sh)
    for r, n in enumerate(rows):
        for c, (d, i, t, label) in enumerate(columns):
            im = Image.open(os.path.join(d, f'{i}_{t}_{n}.png')).convert('RGB')
            im.thumbnail((tile, tile))
            sh.paste(im, (c * tile, r * (tile + 22) + 22))
            dr.text((c * tile + 6, r * (tile + 22) + 5), f'{n}: {label}', fill='black')
    sh.save(out_path, optimize=True)
    return rows


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == 'grid':
        # grid <out.png> <name1,name2,...> <dir>|<id>|<tag>|<label> ...
        print(grid(sys.argv[2], sys.argv[3].split(','), [tuple(c.split('|')) for c in sys.argv[4:]]))
        sys.exit(0)
    if len(sys.argv) < 4 or sys.argv[1] != 'build':
        sys.exit(__doc__)
    a = sys.argv[2:]
    build(a[0], a[1], a[a.index('--id') + 1] if '--id' in a else DEFAULT_ID,
          a[a.index('--source') + 1] if '--source' in a else None)
