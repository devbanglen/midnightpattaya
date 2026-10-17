"""Projected car -> Roblox-ready GLB (one file, texture embedded) with the wheels cut out, plus the wheel layout.

  python export_car.py <dir> <id> [--length 4.5] [--keep-wheels]

Reads <dir>/<id>_proj.obj and <dir>/<id>_frame.json (written by project_views.py: R maps mesh coords to the car frame
F(orward) U(p) L(eft)). Writes, in Roblox axes (X right, Y up, front toward -Z, metres, centred on the bounding box
of what is exported):
  <dir>/<id>.glb          body with the fused tyres painted black (the game's spinning wheels cover them)
  <dir>/<id>_wheels.json  radius, width, centre of each wheel (FL FR RL RR), rim colour
  <dir>/<id>_wheels.png   side-view check: detected wheel circles over the mesh
"""
import argparse, json, os
import numpy as np
import trimesh
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument('dir'); ap.add_argument('id')
ap.add_argument('--length', type=float, default=4.5)
ap.add_argument('--keep-wheels', action='store_true')
a = ap.parse_args()

mesh = trimesh.load(os.path.join(a.dir, f'{a.id}_proj.obj'), process=False, force='mesh')
R = np.array(json.load(open(os.path.join(a.dir, f'{a.id}_frame.json')))['R'])
car = np.asarray(mesh.vertices) @ R.T                       # columns: F, U, L
# car frame -> Roblox: X = right = -L, Y = up = U, Z = back = -F (both maps are reflections, together a rotation)
rbx = np.stack([-car[:, 2], car[:, 1], -car[:, 0]], axis=1)
lo, hi = rbx.min(0), rbx.max(0)
rbx -= (lo + hi) / 2
rbx *= a.length / (hi[2] - lo[2])
mesh.vertices = rbx
mesh.fix_normals()

# --- find the wheels ------------------------------------------------------------------------------------------
pts, fidx = trimesh.sample.sample_surface(mesh, 250000, seed=2)
ymin, H, L = pts[:, 1].min(), np.ptp(pts[:, 1]), np.ptp(pts[:, 2])
NB = 240
edges = np.linspace(pts[:, 2].min(), pts[:, 2].max(), NB + 1)
zc_bins = (edges[:-1] + edges[1:]) / 2
b = np.clip(np.digitize(pts[:, 2], edges) - 1, 0, NB - 1)
profile = np.full(NB, np.inf)
np.minimum.at(profile, b, pts[:, 1])                         # lowest point of the car at each z (side silhouette bottom)
d = profile - ymin


def axle(half):
    """Tyre contact = the longest run of bins touching the ground in this half; radius from the tyre's arc."""
    sel = (zc_bins < 0) if half == 'front' else (zc_bins > 0)
    touch = sel & (d < 0.03 * H)
    runs, start = [], None
    for i in range(NB + 1):
        if i < NB and touch[i]:
            start = i if start is None else start
        elif start is not None:
            runs.append((start, i - 1)); start = None
    s, e = max(runs, key=lambda r: r[1] - r[0])
    ic = (s + e) // 2
    z0 = zc_bins[ic]
    est = []
    for step in (1, -1):                                     # walk out along the arc while it keeps rising
        last = d[ic]
        i = (e if step == 1 else s) + step
        while 0 <= i < NB and np.isfinite(d[i]) and d[i] >= last - 1e-4 and d[i] < 0.6 * H:
            dz = abs(zc_bins[i] - z0)
            if d[i] > 0.01 * H:
                est.append((dz * dz + d[i] * d[i]) / (2 * d[i]))
            last = d[i]; i += step
    r = float(np.median(est)) if est else 0.16 * L / 2
    r = float(np.clip(r, 0.06 * L, 0.11 * L))
    return z0, r


wheels = {}
for half, tag in (('front', 'F'), ('rear', 'R')):
    z0, r = axle(half)
    yc = ymin + r
    near = np.hypot(pts[:, 2] - z0, pts[:, 1] - yc) < r * 0.98
    for side, s in (('L', -1), ('R', 1)):
        on = near & (pts[:, 0] * s > 0)
        x_out = float(np.abs(pts[on, 0]).max())
        width = 0.75 * r
        wheels[tag + side] = {'x': s * (x_out - width / 2), 'y': yc, 'z': z0, 'r': r, 'w': width, 'x_out': x_out}
r_all = float(np.mean([w['r'] for w in wheels.values()]))
w_all = float(np.mean([w['w'] for w in wheels.values()]))

# rim colour: texture under the wheel faces (centre half of the disc)
tex = np.asarray(mesh.visual.material.image.convert('RGB'))
uv = np.asarray(mesh.visual.uv)
cent = mesh.triangles_center
rim_cols = []
for w in wheels.values():
    m = (np.hypot(cent[:, 2] - w['z'], cent[:, 1] - w['y']) < w['r'] * 0.55) & (np.abs(cent[:, 0]) > w['x_out'] - w['w'] * 0.4) & (np.sign(cent[:, 0]) == np.sign(w['x']))
    tuv = uv[mesh.faces[m]].mean(1)
    px = np.clip((tuv[:, 0] * (tex.shape[1] - 1)).astype(int), 0, tex.shape[1] - 1)
    py = np.clip(((1 - tuv[:, 1]) * (tex.shape[0] - 1)).astype(int), 0, tex.shape[0] - 1)
    rim_cols.append(tex[py, px])
rim = np.median(np.concatenate(rim_cols), axis=0) if rim_cols and sum(len(c) for c in rim_cols) else np.array([180, 180, 185])

# --- black out the fused wheels ----------------------------------------------------------------------------------
# The mesh is one closed shell: deleting the tyre faces left see-through holes with pale edges around every arch.
# Instead the fused tyre is painted wheel-well black and the game's spinning wheel (slightly larger) covers it.
if not a.keep_wheels:
    dark = np.zeros(len(mesh.faces), bool)
    for w in wheels.values():
        # tyre only: inside the game wheel's radius (r * 1.04) so the fender lip around the arch keeps its paint
        dark |= ((np.hypot(cent[:, 2] - w['z'], cent[:, 1] - w['y']) < w['r'] * 0.97)
                 & (np.abs(cent[:, 0]) > w['x_out'] - w['w'] * 1.3) & (np.sign(cent[:, 0]) == np.sign(w['x'])))
    teximg = mesh.visual.material.image.convert('RGB')
    dr = ImageDraw.Draw(teximg)
    TW, TH = teximg.size
    for f in mesh.faces[dark]:
        poly = [(uv[i, 0] * (TW - 1), (1 - uv[i, 1]) * (TH - 1)) for i in f]
        dr.polygon(poly, fill=(22, 22, 24), outline=(22, 22, 24))
    mesh.visual.material.image = teximg
    print(f'{a.id}: blacked out {int(dark.sum())} fused wheel faces')

# re-centre on what is exported (Roblox centres a MeshPart on its own bounds) and move the wheels with it
lo, hi = mesh.vertices.min(0), mesh.vertices.max(0)
shift = (lo + hi) / 2
mesh.vertices = mesh.vertices - shift
size = hi - lo
layout = {
    'size': size.round(4).tolist(), 'radius': round(r_all, 4), 'width': round(w_all, 4),
    'rim': [int(c) for c in rim],
    'wheels': {k: [round(w['x'] - shift[0], 4), round(w['y'] - shift[1], 4), round(w['z'] - shift[2], 4)] for k, w in wheels.items()},
}
json.dump(layout, open(os.path.join(a.dir, f'{a.id}_wheels.json'), 'w'), indent=1)
mesh.export(os.path.join(a.dir, f'{a.id}.glb'))
print(f'{a.id}: body {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m, wheel r {r_all:.3f} w {w_all:.3f}, rim {layout["rim"]}')

# --- side-view check image -------------------------------------------------------------------------------------
S = 300 / L
W_, H_ = int(L * S) + 40, int(H * S) + 40
im = Image.new('RGB', (W_, H_), 'white')
dr = ImageDraw.Draw(im)
z0_, y0_ = pts[:, 2].min(), pts[:, 1].max()
for p in pts[::8]:
    dr.point((20 + (p[2] - z0_) * S, 20 + (y0_ - p[1]) * S), fill=(120, 120, 120))
for k, w in wheels.items():
    if k.endswith('L'):
        cx, cy = 20 + (w['z'] - z0_) * S, 20 + (y0_ - w['y']) * S
        dr.ellipse((cx - w['r'] * S, cy - w['r'] * S, cx + w['r'] * S, cy + w['r'] * S), outline=(255, 0, 0), width=2)
im.save(os.path.join(a.dir, f'{a.id}_wheels.png'))
