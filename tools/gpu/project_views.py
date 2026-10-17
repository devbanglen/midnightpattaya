"""Paint the exact colours of the orthographic concept views onto a textured car mesh.

  python project_views.py <in _tex.obj> <views dir> <id> <out dir> [--size 2048] [--power 4]

Views: <views dir>/<id>_{front,back,left,right,top}_cut.png (RGBA cut-outs), else <id>_<view>.png on white
(cut here); left = car facing picture-left, top = front pointing up. The car's axes are found by matching the mesh silhouette to the view silhouettes, so the
mesh may come in any orientation. Each texel takes the views that see it (z-buffer) weighted by how squarely they
face it; texels no view sees keep the base texture. Writes <out>/<id>_proj.obj/.mtl/.jpg (same geometry and UVs).
"""
import argparse, itertools, os, shutil
import numpy as np
import trimesh
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('obj'); ap.add_argument('views'); ap.add_argument('id'); ap.add_argument('out')
ap.add_argument('--size', type=int, default=2048, help='output texture size')
ap.add_argument('--power', type=float, default=4, help='view weight = cos(angle)^power')
ap.add_argument('--zbuf', type=int, default=768, help='z-buffer resolution along the long side')
ap.add_argument('--erode', type=int, default=4, help='px trimmed off each view silhouette (its edge never lines up)')
ap.add_argument('--disagree', type=float, default=38, help='colour spread between views above which the best view wins')
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)

mesh = trimesh.load(a.obj, process=False, force='mesh')
V, F = np.asarray(mesh.vertices, float), np.asarray(mesh.faces)
UV = np.asarray(mesh.visual.uv, float)
base = np.asarray(mesh.visual.material.image.convert('RGB').resize((a.size, a.size), Image.BICUBIC), float)
FN = np.asarray(mesh.face_normals, float)

# --- view images: crop to the cut-out, keep RGB + mask
VIEWS = ('front', 'back', 'left', 'right', 'top')
img = {}
def cutout(path):
    """White-background view -> RGBA: background = near-white pixels connected to the border (white paint inside
    the car stays, because it is enclosed by the outline)."""
    from scipy import ndimage
    rgb = np.asarray(Image.open(path).convert('RGB'))
    white = (rgb.min(axis=2) > 238)
    lab, _ = ndimage.label(white)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    bg = np.isin(lab, border[border > 0])
    return Image.fromarray(np.dstack([rgb, (~bg * 255).astype(np.uint8)]), 'RGBA')


for v in VIEWS:
    p = os.path.join(a.views, f'{a.id}_{v}_cut.png')
    raw = os.path.join(a.views, f'{a.id}_{v}.png')
    if os.path.exists(p) or os.path.exists(raw):
        im = Image.open(p).convert('RGBA') if os.path.exists(p) else cutout(raw)
        im = im.crop(im.getbbox())
        arr = np.asarray(im, float)
        img[v] = (arr[..., :3], arr[..., 3] > 127)
from scipy import ndimage
# silhouettes stay full size for the orientation search; sampling uses an eroded copy
sample_mask = {v: ndimage.binary_erosion(img[v][1], iterations=a.erode) for v in img}
print('views:', ', '.join(img))

# --- per view: (direction toward the camera, image x axis, image y axis) in the car frame F(orward) U(p) L(eft)
E = {'F': np.array([1, 0, 0]), 'U': np.array([0, 1, 0]), 'L': np.array([0, 0, 1])}
CAM = {'front': (E['F'], E['L'], -E['U']), 'back': (-E['F'], -E['L'], -E['U']),
       'left': (E['L'], -E['F'], -E['U']), 'right': (-E['L'], E['F'], -E['U']),
       'top': (E['U'], -E['L'], -E['F'])}

pts, _ = trimesh.sample.sample_surface(mesh, 300000, seed=1)


def silhouette(P, ax, ay, n=96):
    x, y = P @ ax, P @ ay
    x = (x - x.min()) / (np.ptp(x) + 1e-9); y = (y - y.min()) / (np.ptp(y) + 1e-9)
    g = np.zeros((n, n), bool)
    g[np.clip((y * (n - 1)).astype(int), 0, n - 1), np.clip((x * (n - 1)).astype(int), 0, n - 1)] = True
    return g


def mask_grid(m, n=96):
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((n, n), Image.BILINEAR)) > 127


def dilate(g):
    d = g.copy()
    d[1:] |= g[:-1]; d[:-1] |= g[1:]; d[:, 1:] |= g[:, :-1]; d[:, :-1] |= g[:, 1:]
    return d


# --- find the rotation R (mesh coords -> car frame) whose silhouettes best match the views
grids = {v: mask_grid(img[v][1]) for v in img}
best, bestR = -1, None
for perm in itertools.permutations(range(3)):
    for signs in itertools.product((1, -1), repeat=3):
        R = np.zeros((3, 3))
        for r, (c, s) in enumerate(zip(perm, signs)):
            R[r, c] = s
        # (F, U, L) with L = the car's LEFT is a left-handed frame (forward x up = right), so a right-handed mesh
        # maps into it by a reflection. A rotation here would silently mirror the front/back/top views left-right.
        if np.linalg.det(R) > 0:
            continue
        P = pts @ R.T
        score = 0
        for v in img:
            _, ax, ay = CAM[v]
            s = dilate(silhouette(P, ax, ay))
            score += (s & grids[v]).sum() / ((s | grids[v]).sum() + 1e-9)
        if score > best:
            best, bestR = score, R
print(f'orientation IoU sum {best:.2f} over {len(img)} views')
import json
json.dump({'R': bestR.tolist(), 'iou': best}, open(os.path.join(a.out, f'{a.id}_frame.json'), 'w'))
Vc, FNc, Pc = V @ bestR.T, FN @ bestR.T, pts @ bestR.T

# --- z-buffers per view (from the dense surface samples)
zb = {}
for v in img:
    d, ax, ay = CAM[v]
    x, y, z = Pc @ ax, Pc @ ay, Pc @ d
    x0, y0, w, h = x.min(), y.min(), np.ptp(x), np.ptp(y)
    s = (a.zbuf - 1) / max(w, h)
    W, H = int(w * s) + 1, int(h * s) + 1
    buf = np.full((H, W), -np.inf)
    np.maximum.at(buf, (((y - y0) * s).astype(int), ((x - x0) * s).astype(int)), z)
    # fill pin-holes between samples: a pixel takes the max of its 3x3 neighbourhood
    pad = np.pad(buf, 1, constant_values=-np.inf)
    buf = np.max([pad[i:i + H, j:j + W] for i in range(3) for j in range(3)], axis=0)
    zb[v] = (buf, x0, y0, w, h, s)
eps = 0.012 * np.ptp(Vc, axis=0).max()

# --- rasterise every face into UV space: texel -> 3D position (car frame) + face normal
T = a.size
pos = np.zeros((T, T, 3)); nrm = np.zeros((T, T, 3)); cov = np.zeros((T, T), bool)
uvp = np.stack([UV[:, 0] * (T - 1), (1 - UV[:, 1]) * (T - 1)], 1)
for f in range(len(F)):
    i0, i1, i2 = F[f]
    p0, p1, p2 = uvp[i0], uvp[i1], uvp[i2]
    xmin, ymin = np.floor(np.minimum(np.minimum(p0, p1), p2)).astype(int)
    xmax, ymax = np.ceil(np.maximum(np.maximum(p0, p1), p2)).astype(int)
    xmin, ymin, xmax, ymax = max(xmin, 0), max(ymin, 0), min(xmax, T - 1), min(ymax, T - 1)
    if xmax < xmin or ymax < ymin:
        continue
    gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
    d = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(d) < 1e-12:
        continue
    b0 = ((p1[1] - p2[1]) * (gx - p2[0]) + (p2[0] - p1[0]) * (gy - p2[1])) / d
    b1 = ((p2[1] - p0[1]) * (gx - p2[0]) + (p0[0] - p2[0]) * (gy - p2[1])) / d
    b2 = 1 - b0 - b1
    m = (b0 >= -0.02) & (b1 >= -0.02) & (b2 >= -0.02)          # small overlap closes seams
    if not m.any():
        continue
    yy, xx = (gy[m] - 0.5).astype(int), (gx[m] - 0.5).astype(int)
    pos[yy, xx] = b0[m, None] * Vc[i0] + b1[m, None] * Vc[i1] + b2[m, None] * Vc[i2]
    nrm[yy, xx] = FNc[f]
    cov[yy, xx] = True

P, N = pos[cov], nrm[cov]
acc = np.zeros((len(P), 3)); acc2 = np.zeros(len(P)); wsum = np.zeros(len(P)); wmax = np.zeros(len(P))
best = np.zeros((len(P), 3))
for v in img:
    d, ax, ay = CAM[v]
    rgb, msk = img[v][0], sample_mask[v]
    buf, x0, y0, w, h, s = zb[v]
    x, y, z = P @ ax, P @ ay, P @ d
    bx = np.clip(((x - x0) * s).astype(int), 0, buf.shape[1] - 1)
    by = np.clip(((y - y0) * s).astype(int), 0, buf.shape[0] - 1)
    vis = z >= buf[by, bx] - eps
    ih, iw = msk.shape
    ix = np.clip(((x - x0) / w * (iw - 1)).astype(int), 0, iw - 1)
    iy = np.clip(((y - y0) / h * (ih - 1)).astype(int), 0, ih - 1)
    wt = np.clip(N @ d, 0, 1) ** a.power * vis * msk[iy, ix]
    if v == 'top':
        wt *= 0.8                     # GPT's top view is the least exact one
    c_ = rgb[iy, ix]
    acc += wt[:, None] * c_; acc2 += wt * (c_ ** 2).sum(1); wsum += wt
    better = wt > wmax
    best[better] = c_[better]; wmax = np.maximum(wmax, wt)
    print(f'  {v}: {int((wt > 0.05).sum())} texels', flush=True)

out = base.copy()
ws = np.maximum(wsum, 1e-9)
col = acc / ws[:, None]
# spread between the views that see a texel: where they disagree (a drawn edge landing on the wrong panel, e.g.
# body paint smeared onto the windscreen) take the one view that faces the texel most squarely instead of the mix.
# (Falling back to Hunyuan's paint there was tried: its own dark smears showed through on the supercar.)
spread = np.sqrt(np.maximum(acc2 / ws - (col ** 2).sum(1), 0) / 3)
several = (wsum - wmax) > 0.15 * wsum
mix = np.where(several, np.clip((a.disagree * 1.5 - spread) / (a.disagree * 0.5), 0, 1), 1.0)[:, None]
col = mix * col + (1 - mix) * best
blend = np.clip(wsum / 0.25, 0, 1)[:, None]
out[cov] = blend * col + (1 - blend) * base[cov]
print(f'projected {int((wsum > 0.05).sum())}/{len(P)} texels, {int((several & (mix[:, 0] < 0.5)).sum())} disputed -> best view', flush=True)

# --- grow the painted islands into ALL the empty texture (Roblox halves the texture and mip-maps it: narrow gutters
# showed up in game as dark cracks along every UV seam)
_, (ny, nx) = ndimage.distance_transform_edt(~cov, return_indices=True)
o = out[ny, nx]
Image.fromarray(np.clip(o, 0, 255).astype(np.uint8)).save(os.path.join(a.out, f'{a.id}_proj.jpg'), quality=92)

# same geometry/UVs: copy the OBJ, point its material at the new texture
src_dir, src_name = os.path.dirname(a.obj), os.path.splitext(os.path.basename(a.obj))[0]
with open(a.obj) as fi, open(os.path.join(a.out, f'{a.id}_proj.obj'), 'w') as fo:
    for line in fi:
        fo.write(f'mtllib {a.id}_proj.mtl\n' if line.startswith('mtllib') else line)
with open(os.path.join(a.out, f'{a.id}_proj.mtl'), 'w') as fo:
    fo.write(f'newmtl Material\nKd 1 1 1\nNi 1.5\nd 1.0\nillum 2\nmap_Kd {a.id}_proj.jpg\n')
print('wrote', os.path.join(a.out, f'{a.id}_proj.obj'))
