"""Fictional-brand pass for an imported car (offline, numpy + Pillow only; no Blender, no network).

Works on the OPTIMISED outputs of tools/blender/import_car.py (body GLB + 4 wheel GLBs). Topology, UVs and the
four wheel meshes' geometry are copied byte for byte; the embedded base-colour PNGs are replaced and the body's
embossed grille-horse relief is flattened in place (RELIEFS). So the separated-wheel rig (origin = axle, axle
along X) and the triangle counts stay exactly as built.

  python -I tools/gpu/car_debrand.py scan  <in_dir> <id> <out.json>
      lists texel clusters that look like badge colours (yellow / gold / chrome-white) in 3D body space
  python -I tools/gpu/car_debrand.py apply <in_dir> <id> <out_dir> <new_id> [--report out.json] [--debug dir]
      paints the brand marks out, adds the fictional "MP" emblem, softens the signature cues (see MARKS / CUES),
      writes <out_dir>/<new_id>.glb, <new_id>_wheel_XX.glb, <new_id>_wheels.json, <new_id>_debrand.json
  python -I tools/gpu/car_debrand.py pairs <before_dir> <after_dir> <out.png> name1,name2,...
      before | after sheet of renders from tools/blender/car_debrand_render.py
  python -I tools/gpu/car_debrand.py sheet <out.png> <img> [<img> ...]

How it finds texels in 3D: every triangle is rasterised in UV space, so each texel knows its body-space position
and normal (frame N: X right, Y up, front -Z, metres). Marks are selected by a 3D region AND a colour test, then
filled with the median paint colour of the same region's ring (so the fill follows the fragmented Tripo atlas).
The emblem is a signed-distance shape evaluated on a plane tangent to the surface (own design, made here).
"""
import io
import json
import math
import os
import struct
import sys

import numpy as np
from PIL import Image

WHEELS = ('FL', 'FR', 'RL', 'RR')


# ---------------------------------------------------------------------------------------------------- GLB I/O --
def glb_read(path):
    b = open(path, 'rb').read()
    magic, _ver, _len = struct.unpack_from('<III', b, 0)
    assert magic == 0x46546C67, path
    jl = struct.unpack_from('<I', b, 12)[0]
    js = json.loads(b[20:20 + jl])
    bl = struct.unpack_from('<I', b, 20 + jl)[0]
    binc = b[28 + jl:28 + jl + bl]
    return js, binc


def _view(js, binc, bv):
    v = js['bufferViews'][bv]
    o = v.get('byteOffset', 0)
    return binc[o:o + v['byteLength']]


def accessor(js, binc, i):
    a = js['accessors'][i]
    dt = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[a['componentType']]
    n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
    raw = _view(js, binc, a['bufferView'])
    off = a.get('byteOffset', 0)
    return np.frombuffer(raw, dt, a['count'] * n, off).reshape(a['count'], n) if n > 1 else \
        np.frombuffer(raw, dt, a['count'], off)


def mesh_arrays(js, binc):
    p = js['meshes'][0]['primitives'][0]
    pos = accessor(js, binc, p['attributes']['POSITION']).astype(np.float64)
    nrm = accessor(js, binc, p['attributes']['NORMAL']).astype(np.float64)
    uv = accessor(js, binc, p['attributes']['TEXCOORD_0']).astype(np.float64)
    idx = accessor(js, binc, p['indices']).astype(np.int64).reshape(-1, 3)
    return pos, nrm, uv, idx


def image_of(js, binc, k=0):
    return Image.open(io.BytesIO(_view(js, binc, js['images'][k]['bufferView']))).convert('RGB')


def glb_replace_image(js, binc, img, name=None, k=0, pos=None, nrm=None):
    """Same JSON + buffers, image k replaced by a PNG of img (and, if given, the POSITION / NORMAL data replaced by
    float32 arrays of the same vertex count: same topology, same UVs). bufferViews are re-packed (4-byte aligned)."""
    js = json.loads(json.dumps(js))
    buf = io.BytesIO()
    img.save(buf, 'PNG', optimize=True)
    repl = {js['images'][k]['bufferView']: buf.getvalue()}
    prim = js['meshes'][0]['primitives'][0]['attributes']
    for key, arr in (('POSITION', pos), ('NORMAL', nrm)):
        if arr is None:
            continue
        acc = js['accessors'][prim[key]]
        bv = js['bufferViews'][acc['bufferView']]
        assert acc.get('byteOffset', 0) == 0 and 'byteStride' not in bv and len(arr) == acc['count'], key
        assert sum(1 for a in js['accessors'] if a.get('bufferView') == acc['bufferView']) == 1, key
        a32 = np.ascontiguousarray(arr, np.float32)
        repl[acc['bufferView']] = a32.tobytes()
        if key == 'POSITION':
            acc['min'], acc['max'] = a32.min(0).tolist(), a32.max(0).tolist()
    out, off = bytearray(), 0
    for i, v in enumerate(js['bufferViews']):
        data = repl.get(i, None) or _view(js, binc, i)
        pad = (-off) % 4
        out += b'\0' * pad
        off += pad
        v['byteOffset'] = off
        v['byteLength'] = len(data)
        out += data
        off += len(data)
    out += b'\0' * ((-len(out)) % 4)
    js['buffers'][0]['byteLength'] = len(out)
    if name:
        js['images'][k]['name'] = name
    return js, bytes(out)


def glb_write(path, js, binc, node_name=None):
    if node_name:
        js['nodes'][0]['name'] = node_name
        js['meshes'][0]['name'] = node_name
    jb = json.dumps(js, separators=(',', ':')).encode()
    jb += b' ' * ((-len(jb)) % 4)
    total = 12 + 8 + len(jb) + 8 + len(binc)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(jb), 0x4E4F534A) + jb)
        f.write(struct.pack('<II', len(binc), 0x004E4942) + binc)


# ------------------------------------------------------------------------------------------ UV rasterisation --
def raster(pos, nrm, uv, idx, size):
    """Per texel: body-space position, normal and a coverage mask (texel centre inside a UV triangle).
    glTF UV origin is top-left, so texel (row, col) = (v * H, u * W)."""
    W, H = size
    P = np.zeros((H, W, 3))
    N = np.zeros((H, W, 3))
    M = np.zeros((H, W), bool)
    t = uv[idx] * (W, H)                                  # (T, 3, 2) in pixel units (x = u, y = v)
    for k in range(len(idx)):
        (x0, y0), (x1, y1), (x2, y2) = t[k]
        lo_x, hi_x = int(max(0, math.floor(min(x0, x1, x2) - 0.5))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        lo_y, hi_y = int(max(0, math.floor(min(y0, y1, y2) - 0.5))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if hi_x < lo_x or hi_y < lo_y:
            continue
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(d) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(lo_x, hi_x + 1) + 0.5, np.arange(lo_y, hi_y + 1) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / d
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / d
        c = 1 - a - b
        e = -1e-3
        inside = (a >= e) & (b >= e) & (c >= e)
        if not inside.any():
            continue
        ii, jj = np.nonzero(inside)
        rr, cc = ii + lo_y, jj + lo_x
        w = np.stack([a[inside], b[inside], c[inside]], 1)
        i3 = idx[k]
        P[rr, cc] = w @ pos[i3]
        N[rr, cc] = w @ nrm[i3]
        M[rr, cc] = True
    n = np.linalg.norm(N, axis=2, keepdims=True)
    N = np.where(n > 1e-9, N / np.maximum(n, 1e-9), 0)
    return P, N, M


def dilate_into(img, changed, cover, steps=3):
    """Copy edited texels into neighbouring texels that no triangle covers (atlas padding), so mipmaps and
    bilinear filtering do not bring the old badge colour back at island edges."""
    a = img.copy()
    done = changed.copy()
    for _ in range(steps):
        grow = np.zeros_like(done)
        acc = np.zeros(a.shape, np.float64)
        cnt = np.zeros(done.shape, np.float64)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            s = np.roll(np.roll(done, dy, 0), dx, 1)
            v = np.roll(np.roll(a, dy, 0), dx, 1)
            acc += v * s[..., None]
            cnt += s
        grow = (cnt > 0) & ~done & ~cover
        a[grow] = acc[grow] / cnt[grow][:, None]
        done |= grow
    return a


# ------------------------------------------------------------------------------------------------ colour tests --
def hsv(rgb):
    """rgb float 0..1 (..., 3) -> h (deg), s, v."""
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm = m & (mx == r)
    gm = m & (mx == g) & ~rm
    bm = m & ~rm & ~gm
    h[rm] = (60 * ((g - b)[rm] / d[rm])) % 360
    h[gm] = 60 * ((b - r)[gm] / d[gm]) + 120
    h[bm] = 60 * ((r - g)[bm] / d[bm]) + 240
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def is_yellow(rgb):
    h, s, v = hsv(rgb)
    return (h > 35) & (h < 70) & (s > 0.35) & (v > 0.35)


def is_red_paint(rgb):
    h, s, v = hsv(rgb)
    return ((h < 15) | (h > 340)) & (s > 0.55) & (v > 0.35)


def clusters(P, mask, link=0.03):
    """Greedy 3D clustering of masked texels (positions in metres)."""
    pts = P[mask]
    rc = np.argwhere(mask)
    lab = -np.ones(len(pts), int)
    out = []
    for i in range(len(pts)):
        if lab[i] >= 0:
            continue
        lab[i] = len(out)
        stack, members = [i], [i]
        while stack:
            j = stack.pop()
            d = np.linalg.norm(pts - pts[j], axis=1)
            nb = np.nonzero((d < link) & (lab < 0))[0]
            lab[nb] = len(out)
            stack += nb.tolist()
            members += nb.tolist()
        m = np.array(members)
        out.append({'n_texels': int(len(m)), 'centre': [round(float(x), 3) for x in pts[m].mean(0)],
                    'lo': [round(float(x), 3) for x in pts[m].min(0)],
                    'hi': [round(float(x), 3) for x in pts[m].max(0)],
                    'uv_px_sample': rc[m[0]].tolist()})
    out.sort(key=lambda c: -c['n_texels'])
    return out


def frame_axes(n, up=(0.0, 1.0, 0.0)):
    """Viewer's right / up for a surface facing n (viewer looks along -n). Text drawn in (right, up) reads
    correctly (not mirrored) from outside."""
    n = np.asarray(n, float) / np.linalg.norm(n)
    u = np.asarray(up, float)
    u = u - n * (u @ n)
    if np.linalg.norm(u) < 1e-6:
        u = np.array((0.0, 0.0, -1.0)) - n * (-n[2])
    u /= np.linalg.norm(u)
    r = np.cross(-n, u)
    return r / np.linalg.norm(r), u


def splat(P, N, M, img, centre, n, half, res=256, up=(0.0, 1.0, 0.0), depth=0.25):
    """Orthographic look at the TEXTURE as it sits on the surface: covered texels within `half` metres of centre
    (in the view plane) and `depth` metres along n, facing the viewer, splatted with a z-buffer."""
    r, u = frame_axes(n, up)
    n = np.asarray(n, float) / np.linalg.norm(n)
    d = P - np.asarray(centre)
    x, y, z = d @ r, d @ u, d @ n
    m = M & (np.abs(x) < half) & (np.abs(y) < half) & (np.abs(z) < depth) & ((N @ n) > 0.05)
    out = np.full((res, res, 3), 235, np.uint8)
    zb = np.full((res, res), -1e9)
    px = ((x[m] / half + 1) / 2 * (res - 1)).astype(int)
    py = ((1 - (y[m] / half + 1) / 2) * (res - 1)).astype(int)
    col = img[m]
    zz = z[m]
    order = np.argsort(zz)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            a, b = np.clip(py[order] + dy, 0, res - 1), np.clip(px[order] + dx, 0, res - 1)
            w = zz[order] >= zb[a, b] - 1e-4
            zb[a[w], b[w]] = zz[order][w]
            out[a[w], b[w]] = col[order][w]
    return Image.fromarray(out)


def load_car(in_dir, cid):
    lay = json.load(open(os.path.join(in_dir, f'{cid}_wheels.json')))
    js, binc = glb_read(os.path.join(in_dir, f'{cid}.glb'))
    body = {'js': js, 'bin': binc, 'mesh': mesh_arrays(js, binc), 'img': image_of(js, binc)}
    wheels = {}
    for k in WHEELS:
        wjs, wb = glb_read(os.path.join(in_dir, lay['wheel_meshes'][k]))
        wheels[k] = {'js': wjs, 'bin': wb, 'mesh': mesh_arrays(wjs, wb), 'img': image_of(wjs, wb)}
    return lay, body, wheels


def scan(in_dir, cid, out_json):
    lay, body, wheels = load_car(in_dir, cid)
    rep = {}
    img = np.asarray(body['img'], np.float64) / 255
    P, N, M = raster(*body['mesh'], body['img'].size)
    rep['body_yellow'] = clusters(P, M & is_yellow(img))[:40]
    for k, w in wheels.items():
        wi = np.asarray(w['img'], np.float64) / 255
        P2, N2, M2 = raster(*w['mesh'], w['img'].size)
        rep['wheel_' + k + '_yellow'] = clusters(P2, M2 & is_yellow(wi), 0.02)[:10]
    json.dump(rep, open(out_json, 'w'), indent=1)
    print(json.dumps({k: [(c['n_texels'], c['centre']) for c in v[:12]] for k, v in rep.items()}, indent=0))


# -------------------------------------------------------------------------------------------- the MP emblem --
# Own design for the fictional make "Midnight Pattaya" (MP): a horizontal capsule (body badge) or a disc (wheel
# caps) with a navy field, a silver rim and a silver twin-peak zigzag that reads as an "M" (and as two waves /
# two peaks). Pure geometry, defined here; not traced from or modelled on any real brand. A lozenge (Renault-like)
# and an oval with a winged M (Mazda-like) were avoided on purpose.
NAVY = np.array((22, 30, 62), float)
SILVER = np.array((206, 210, 220), float)
TEAL = np.array((0, 168, 170), float)
GLYPH = np.array(((-0.27, -0.13), (-0.135, 0.15), (0.0, -0.05), (0.135, 0.15), (0.27, -0.13)))


def _seg_dist(x, y, a, b):
    px, py = x - a[0], y - a[1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - t * dx, py - t * dy)


def emblem_rgba(x, y, shape='capsule', aa=0.04):
    """Badge colour and coverage at badge coords (x, y) in [-0.5, 0.5] (size 1 = badge width). Returns (rgb,
    alpha). Signed distances: < 0 inside."""
    if shape == 'capsule':
        d_out = _seg_dist(x, y, (-0.29, 0.0), (0.29, 0.0)) - 0.21
        gl, stroke, rim = GLYPH * (0.9, 0.62), 0.032, 0.045
    else:
        d_out = np.hypot(x, y) - 0.5
        gl, stroke, rim = GLYPH, 0.045, 0.07
    glyph = np.min([_seg_dist(x, y, gl[i], gl[i + 1]) for i in range(len(gl) - 1)], 0) - stroke

    def cov(d):
        return np.clip(0.5 - d / max(aa, 1e-4), 0, 1)
    a_all = cov(d_out)
    field = cov(d_out + rim)                                      # 1 inside the inner field
    col = SILVER[None] * (1 - field[:, None]) + NAVY[None] * field[:, None]
    g = (cov(glyph) * field)[:, None]
    col = col * (1 - g) + SILVER[None] * g
    return col, a_all


def emblem_png(path, size=512):
    """The emblem as a flat image (capsule body badge | disc wheel cap), for the docs."""
    ys, xs = np.mgrid[0:size, 0:size]
    out = []
    for shape in ('capsule', 'disc'):
        x = (xs.ravel() + 0.5) / size - 0.5
        y = 0.5 - (ys.ravel() + 0.5) / size
        c, a = emblem_rgba(x * 1.05, y * 1.05, shape, aa=1.5 / size)
        bg = np.array((255, 255, 255), float)
        out.append((c * a[:, None] + bg * (1 - a[:, None])).reshape(size, size, 3))
    Image.fromarray(np.concatenate(out, 1).astype(np.uint8)).save(path)


# ------------------------------------------------------------------------------------------------- painting --
def texel_pitch(P, sel):
    """Typical texel spacing (m) among selected texels (median 4-neighbour distance)."""
    d = []
    for ax in (0, 1):
        q = np.roll(P, 1, ax)
        s2 = np.roll(sel, 1, ax) & sel
        if s2.any():
            d.append(np.linalg.norm((P - q)[s2], axis=1))
    d = np.concatenate(d) if d else np.array([0.01])
    d = d[d < 0.05]
    return float(np.median(d)) if len(d) else 0.01


def idw_fill(img, P, target, source, k=8):
    """Each target texel <- inverse-distance-squared mean of its k nearest source texels in 3D."""
    tp, sp, sc = P[target], P[source], img[source]
    if not len(tp) or not len(sp):
        return 0
    out = np.empty((len(tp), 3))
    for i0 in range(0, len(tp), 512):
        d = np.linalg.norm(tp[i0:i0 + 512, None] - sp[None], axis=2)
        kk = min(k, d.shape[1])
        nn = np.argpartition(d, kk - 1, axis=1)[:, :kk]
        dd = np.take_along_axis(d, nn, 1)
        w = 1 / np.maximum(dd, 1e-4) ** 2
        out[i0:i0 + 512] = (sc[nn] * w[..., None]).sum(1) / w.sum(1, keepdims=True)
    img[target] = out
    return int(len(tp))


def grow(P, seed, cand, dist):
    """seed + the texels in cand within dist (m) of any seed texel."""
    out = seed.copy()
    rest = cand & ~seed
    if not seed.any() or not rest.any():
        return out
    sp = P[seed]
    ci = np.argwhere(rest)
    cp = P[rest]
    near = np.zeros(len(cp), bool)
    for i0 in range(0, len(cp), 1024):
        near[i0:i0 + 1024] = (np.linalg.norm(cp[i0:i0 + 1024, None] - sp[None], axis=2) < dist).any(1)
    out[tuple(ci[near].T)] = True
    return out


def place_emblem(img, P, N, M, centre, n, size, shape, up=(0.0, 1.0, 0.0), depth=0.03):
    n = np.asarray(n, float) / np.linalg.norm(n)
    r, u = frame_axes(n, up)
    d = P - np.asarray(centre, float)
    x, y, z = d @ r / size, d @ u / size, d @ n
    m = M & (np.abs(x) < 0.6) & (np.abs(y) < 0.6) & (np.abs(z) < depth) & ((N @ n) > 0.2)
    aa = texel_pitch(P, m) / size
    c, a = emblem_rgba(x[m], y[m], shape, aa=aa)
    img[m] = img[m] * (1 - a[:, None]) + c * a[:, None]
    return int((a > 0.5).sum()), aa


def surface_normal(P, N, M, centre, radius):
    m = M & (np.linalg.norm(P - np.asarray(centre), axis=2) < radius)
    v = N[m].mean(0)
    return v / np.linalg.norm(v)


# Brand marks in the Tripo red_sports texture (frame N, metres), found by `scan` + close-up renders:
# region = sphere (centre, radius); seed = colour test that starts the selection; grow = non-paint texels within
# `grow` m of a seed; fill = which neighbours repaint it (red paint or dark trim).
MARKS = [
    {'name': 'nose_shield', 'what': 'yellow shield with a black horse on the nose, just above the grille',
     'centre': (0.0, -0.128, -2.167), 'radius': 0.06, 'seed': 'yellow', 'grow': 0.02, 'fill': 'paint'},
    {'name': 'grille_horse', 'what': 'chrome prancing horse in the centre of the grille',
     'centre': (0.0, -0.345, -2.166), 'radius': 0.075, 'seed': 'chrome', 'grow': 0.012, 'fill': 'dark'},
    {'name': 'fender_shield_L', 'what': 'yellow shield on the left front wing, behind the wheel arch',
     'centre': (-0.95, 0.087, -0.674), 'radius': 0.08, 'seed': 'yellow', 'grow': 0.03, 'fill': 'paint'},
    {'name': 'fender_shield_R', 'what': 'right front wing (mirror position; checked, nothing there)',
     'centre': (0.95, 0.087, -0.674), 'radius': 0.07, 'seed': 'yellow', 'grow': 0.02, 'fill': 'paint'},
    {'name': 'tail_horse', 'what': 'chrome prancing horse in the centre of the tail',
     'centre': (0.0, 0.08, 2.18), 'radius': 0.065, 'seed': 'chrome', 'grow': 0.015, 'fill': 'paint'},
    {'name': 'steering_badge', 'what': 'yellow/orange badge on the steering-wheel boss (interior)',
     'centre': (-0.388, 0.124, -0.153), 'radius': 0.09, 'seed': 'yellow_orange', 'grow': 0.008, 'fill': 'dark'},
]
EMBLEMS = [   # where the MP emblem goes (body); size = badge width in metres
    {'name': 'nose', 'centre': (0.0, -0.128, -2.167), 'size': 0.095, 'shape': 'capsule'},
    {'name': 'tail', 'centre': (0.0, 0.08, 2.18), 'size': 0.11, 'shape': 'capsule'},
]
TAIL = {'lamp_y': 0.11, 'pods_x': (0.48, 0.94), 'pods_y': (0.045, 0.172), 'rear_z': 1.88, 'bar_x': 0.92,
        'bar_gap': 0.065, 'bar_half': 0.015, 'core_half': 0.007,
        'lens': (34, 12, 15), 'edge': (110, 10, 16), 'core': (255, 46, 46)}
GRILLE = {'lo': (-0.42, -0.46, -2.40), 'hi': (0.42, -0.25, -2.05), 'pitch': 0.028}
WHEEL = {'cap_r': 0.072, 'cap_x': 0.07, 'emblem': 0.13, 'rim_r': (0.072, 0.285), 'spoke_x': 0.04,
         'caliper_r': 0.30}


def seed_mask(rgb, kind):
    h, s, v = hsv(rgb)
    if kind == 'yellow':
        return is_yellow(rgb)
    if kind == 'yellow_orange':
        return (h > 18) & (h < 70) & (s > 0.4) & (v > 0.3)
    if kind == 'chrome':
        return (s < 0.35) & (v > 0.42)
    raise ValueError(kind)


# Embossed geometry: the grille and tail horses are raised reliefs (front faces ~3 cm proud, side walls with sideways
# normals). Flatten = every vertex within `radius` (in the X-Y plane of the front) is put on a plane fitted to the
# grille surface around it, normals set to that plane's normal. The relief triangles stay (zero-area walls), so
# the triangle count and UVs do not change.
RELIEFS = [
    {'name': 'grille_horse_relief', 'centre': (0.0, -0.345, -2.166), 'radius': 0.085, 'ring': 0.125, 'facing': -1},
    {'name': 'tail_horse_relief', 'centre': (0.0, 0.08, 2.18), 'radius': 0.06, 'ring': 0.11, 'facing': 1},
]


def flatten_reliefs(pos, nrm, report):
    """facing -1 = a front surface (normal -Z), +1 = a rear surface (+Z). The surface z = f(x, y) is fitted to the
    ring of vertices around the relief that face that way (quadratic when there are enough, else a plane)."""
    pos, nrm = pos.copy(), nrm.copy()
    for rf in RELIEFS:
        c = np.asarray(rf['centre'])
        sgn = rf['facing']
        d = np.hypot(pos[:, 0] - c[0], pos[:, 1] - c[1])
        near = np.abs(pos[:, 2] - c[2]) < 0.06
        inner = near & (d < rf['radius'])
        ring = near & (d >= rf['radius']) & (d < rf['ring']) & (nrm[:, 2] * sgn > 0.6)
        x, y = pos[:, 0] - c[0], pos[:, 1] - c[1]
        quad = ring.sum() >= 15
        cols = (lambda x, y: [np.ones_like(x), x, y, x * x, x * y, y * y]) if quad else \
            (lambda x, y: [np.ones_like(x), x, y])
        A = np.stack(cols(x[ring], y[ring]), 1)
        coef = np.linalg.lstsq(A, pos[ring, 2], rcond=None)[0]
        xi, yi = x[inner], y[inner]
        z_new = np.stack(cols(xi, yi), 1) @ coef
        if quad:
            gx = coef[1] + 2 * coef[3] * xi + coef[4] * yi
            gy = coef[2] + coef[4] * xi + 2 * coef[5] * yi
        else:
            gx, gy = np.full_like(xi, coef[1]), np.full_like(xi, coef[2])
        n = np.stack([-gx, -gy, np.ones_like(xi)], 1) * sgn
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        moved = np.abs(pos[inner, 2] - z_new)
        pos[inner, 2] = z_new
        nrm[inner] = n
        report['geometry'].append({'name': rf['name'], 'verts_flattened': int(inner.sum()),
                                   'ring_verts': int(ring.sum()), 'fit': 'quadratic' if quad else 'plane',
                                   'max_move_m': round(float(moved.max()), 4),
                                   'median_move_m': round(float(np.median(moved)), 4)})
    return pos, nrm


def debrand_body(img8, P, N, M, report):
    img = img8.astype(np.float64)
    rgb = img / 255
    changed = np.zeros(M.shape, bool)
    paint = M & is_red_paint(rgb)
    h, s, v = hsv(rgb)
    dark = M & (v < 0.22)
    for mk in MARKS:
        dist = np.linalg.norm(P - np.asarray(mk['centre']), axis=2)
        reg = M & (dist < mk['radius'])
        keep = paint if mk['fill'] == 'paint' else dark
        seed = reg & seed_mask(rgb, mk['seed']) & ~keep
        sel = grow(P, seed, reg & ~keep, mk['grow']) if seed.sum() >= 3 else np.zeros_like(seed)
        shell = M & (dist < mk['radius'] + 0.06) & ~sel & ~changed
        n = idw_fill(img, P, sel, shell & keep)
        changed |= sel
        report['marks'].append({'name': mk['name'], 'what': mk['what'], 'seed_texels': int(seed.sum()),
                                'repainted_texels': n, 'fill': mk['fill']})
    # grille: horizontal slats instead of the honeycomb mesh (signature-cue change, texture only)
    g = M & np.all((P >= GRILLE['lo']) & (P <= GRILLE['hi']), axis=2) & (N[..., 2] < -0.3) & ~paint
    gv = np.median(img[g], 0) if g.any() else np.array((20, 20, 22.0))
    phase = (P[..., 1] / GRILLE['pitch']) % 1.0
    img[g] = np.minimum(gv, (26, 26, 28))
    img[g & (phase < 0.38)] = (70, 72, 76)
    changed |= g
    report['cues'].append({'name': 'grille_slats', 'texels': int(g.sum()),
                           'what': 'honeycomb grille mesh repainted as dark horizontal slats'})
    # tail: smoke the four lamp pods, add one full-width light bar
    t = TAIL
    rear = M & (P[..., 2] > t['rear_z']) & (N[..., 2] > 0.3)
    ax = np.abs(P[..., 0])
    # each side's two pods (and the paint between them) become ONE dark smoked lens, keeping 25 % of the detail
    pods = rear & (ax > t['pods_x'][0]) & (ax < t['pods_x'][1]) & (P[..., 1] > t['pods_y'][0]) & \
        (P[..., 1] < t['pods_y'][1])
    lum = img[pods].mean(1, keepdims=True) / 255
    img[pods] = np.array(t['lens'])[None] * (0.75 + 0.5 * lum) + img[pods] * 0.08
    # the bar, anti-aliased against the texel pitch (the atlas islands are rotated: hard edges staircase)
    pitch = texel_pitch(P, rear & (ax < t['bar_x']))
    dy = np.abs(P[..., 1] - t['lamp_y'])
    end = np.minimum(t['bar_x'] - ax, ax - t['bar_gap'])
    cov = np.clip((t['bar_half'] - dy) / pitch + 0.5, 0, 1) * np.clip(end / pitch + 0.5, 0, 1) * rear
    core = np.clip((t['core_half'] - dy) / pitch + 0.5, 0, 1) * (cov > 0)
    img[:] = img * (1 - cov[..., None]) + np.array(t['edge'])[None, None] * cov[..., None]
    img[:] = img * (1 - core[..., None]) + np.array(t['core'])[None, None] * core[..., None]
    bar = cov > 0
    changed |= pods | bar
    report['cues'].append({'name': 'tail_light_bar', 'texels': int((pods | bar).sum()),
                           'what': 'each side\'s twin lamp pods painted as one dark smoked lens; one thin '
                                   'full-width red light bar painted across the tail at lamp height (texture only: '
                                   'the recessed pod shapes in the geometry remain)'})
    for em in EMBLEMS:
        nrm = surface_normal(P, N, M, em['centre'], 0.05)
        k, aa = place_emblem(img, P, N, M, em['centre'], nrm, em['size'], em['shape'])
        changed |= M & (np.linalg.norm(P - np.asarray(em['centre']), axis=2) < em['size'] * 0.6)
        report['emblems'].append({'name': em['name'], 'texels': k, 'size_m': em['size'],
                                  'texels_across': round(1 / max(aa, 1e-6), 1), 'normal': nrm.round(3).tolist()})
    img = dilate_into(img, changed, M)
    return np.clip(img, 0, 255).astype(np.uint8)


def debrand_wheel(img8, P, N, M, side, report, key):
    """side = -1 (left wheel, outer face -X) or +1 (right). Wheel mesh space: axle along X, origin at the axle."""
    img = img8.astype(np.float64)
    rgb = img / 255
    h, s, v = hsv(rgb)
    rho = np.hypot(P[..., 1], P[..., 2])
    xo = P[..., 0] * side
    w = WHEEL
    yellow = M & is_yellow(rgb) & (rho < 0.12)
    cap = M & (rho < w['cap_r']) & (xo > w['cap_x'])
    rim = M & (rho > w['rim_r'][0]) & (rho < w['rim_r'][1]) & (xo > w['spoke_x']) & (s < 0.35) & ~cap
    cal = M & (rho < w['caliper_r']) & is_red_paint(rgb) & ~cap
    # rims: black forged look -> silver (a different finish; the spoke geometry is unchanged)
    lum = rgb[rim].mean(1)
    img[rim] = SILVER[None] * np.clip(0.55 + 1.6 * lum, 0.55, 1.1)[:, None] * 0.82
    # calipers: red -> teal (the fictional make's accent colour)
    img[cal] = TEAL[None] * np.clip(v[cal] * 1.1, 0.3, 1.0)[:, None]
    # centre cap: the yellow horse cap becomes the MP disc emblem
    img[cap] = NAVY
    k, aa = place_emblem(img, P, N, M, (side * 0.115, 0.0, 0.0), (side, 0.0, 0.0), w['emblem'], 'disc',
                         depth=0.06)
    img = dilate_into(img, cap | rim | cal, M)
    rem = M & is_yellow(np.clip(img, 0, 255) / 255) & (rho < 0.12)
    report['wheels'][key] = {'yellow_cap_texels_before': int(yellow.sum()), 'yellow_left_after': int(rem.sum()),
                             'cap_texels': int(cap.sum()), 'rim_texels': int(rim.sum()),
                             'caliper_texels': int(cal.sum()), 'emblem_texels_across': round(1 / max(aa, 1e-6), 1)}
    return np.clip(img, 0, 255).astype(np.uint8)


def apply(in_dir, cid, out_dir, new_id, report_path=None):
    os.makedirs(out_dir, exist_ok=True)
    lay, body, wheels = load_car(in_dir, cid)
    report = {'source_id': cid, 'id': new_id, 'marks': [], 'geometry': [], 'cues': [], 'emblems': [],
              'wheels': {},
              'note': 'edit of the optimised build: textures repainted, the grille- and tail-horse reliefs flattened in place; '
                      'topology, UVs, wheel meshes, pivots and triangle counts are unchanged'}
    img8 = np.asarray(body['img']).copy()
    P, N, M = raster(*body['mesh'], body['img'].size)
    new = debrand_body(img8, P, N, M, report)
    pos2, nrm2 = flatten_reliefs(body['mesh'][0], body['mesh'][1], report)
    report['yellow_texels_body_before'] = int((M & is_yellow(img8 / 255.0)).sum())
    report['yellow_texels_body_after'] = int((M & is_yellow(new / 255.0)).sum())
    js, b = glb_replace_image(body['js'], body['bin'], Image.fromarray(new), f'{new_id}_basecolor',
                              pos=pos2, nrm=nrm2)
    glb_write(os.path.join(out_dir, f'{new_id}.glb'), js, b, new_id)
    files = {}
    for k in WHEELS:
        w = wheels[k]
        P2, N2, M2 = raster(*w['mesh'], w['img'].size)
        nw = debrand_wheel(np.asarray(w['img']).copy(), P2, N2, M2, -1 if k[1] == 'L' else 1, report, k)
        js, b = glb_replace_image(w['js'], w['bin'], Image.fromarray(nw), f'{new_id}_wheel_{k}_tex')
        files[k] = f'{new_id}_wheel_{k}.glb'
        glb_write(os.path.join(out_dir, files[k]), js, b, f'{new_id}_wheel_{k}')
    lay2 = json.loads(json.dumps(lay))
    lay2['wheel_meshes'] = files
    lay2['rim'] = [int(x) for x in SILVER * 0.8]
    lay2['fictional_brand'] = {'from': cid, 'emblem': 'MP (Midnight Pattaya), own design',
                               'upload': 'BLOCKED until the owner confirms the licence'}
    json.dump(lay2, open(os.path.join(out_dir, f'{new_id}_wheels.json'), 'w'), indent=1)
    json.dump(report, open(report_path or os.path.join(out_dir, f'{new_id}_debrand.json'), 'w'), indent=1)
    emblem_png(os.path.join(out_dir, f'{new_id}_emblem.png'))
    print(json.dumps(report, indent=1))
    return report


def pairs(before_dir, after_dir, out_path, names, tile=520):
    """Before | after sheet: one row per view name (renders from tools/blender/car_debrand_render.py)."""
    from PIL import ImageDraw
    rows = []
    for n in names:
        b = [f for f in os.listdir(before_dir) if f.endswith(f'_before_{n}.png')]
        a = [f for f in os.listdir(after_dir) if f.endswith(f'_after_{n}.png')]
        if b and a:
            rows.append((n, os.path.join(before_dir, b[0]), os.path.join(after_dir, a[0])))
    sheet = Image.new('RGB', (2 * tile, len(rows) * (tile + 20)), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (n, b, a) in enumerate(rows):
        for j, p in enumerate((b, a)):
            im = Image.open(p).convert('RGB')
            im.thumbnail((tile, tile))
            sheet.paste(im, (j * tile, i * (tile + 20) + 20))
            d.text((j * tile + 6, i * (tile + 20) + 4), f'{n}: {"before (source badges)" if j == 0 else "after (fictional MP)"}',
                   fill='black')
    sheet.save(out_path)


def sheet(out_path, paths, cols=3, tile=420):
    """Plain contact sheet with file-name captions."""
    from PIL import ImageDraw
    rows = (len(paths) + cols - 1) // cols
    s = Image.new('RGB', (cols * tile, rows * (tile + 20)), 'white')
    d = ImageDraw.Draw(s)
    for i, p in enumerate(paths):
        im = Image.open(p).convert('RGB')
        im.thumbnail((tile, tile))
        x, y = (i % cols) * tile, (i // cols) * (tile + 20)
        s.paste(im, (x, y + 20))
        d.text((x + 6, y + 4), os.path.basename(p)[:-4], fill='black')
    s.save(out_path, optimize=True)


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('scan', 'apply', 'pairs', 'sheet'):
        sys.exit(__doc__)
    if sys.argv[1] == 'scan':
        scan(*sys.argv[2:5])
    elif sys.argv[1] == 'pairs':
        pairs(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5].split(','))
    elif sys.argv[1] == 'sheet':
        sheet(sys.argv[2], sys.argv[3:])
    else:
        a = sys.argv[2:]
        apply(a[0], a[1], a[2], a[3], a[a.index('--report') + 1] if '--report' in a else None)
