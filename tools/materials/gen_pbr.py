"""Procedural, tileable PBR texture sets for MIDNIGHT PATTAYA's MaterialLibrary (VIS-3).

Writes 1024x1024 PNG maps into build/materials/ (gitignored, regenerable):
    <name>_albedo.png  <name>_normal.png  <name>_roughness.png  [<name>_metalness.png]
for name in asphalt, wet_asphalt, concrete, dark_glass, painted_metal, and small JPEG previews into
docs/images/materials/ (<name>_preview.jpg: albedo | normal | roughness | 2x2 tiling check).

Every map is seamless by construction: all noise is made in the frequency domain (FFT synthesis is periodic), blurs
are FFT convolutions, gradients use np.roll, and stamped features wrap around the edges. The script prints a seam
metric per map (mean jump across the wrap edge / mean jump between neighbouring interior pixels; ~1.0 = seamless).

Normal maps: tangent space, OpenGL convention (green = +Y up), which is what Roblox SurfaceAppearance and
MaterialVariant expect. Roughness: white = rough. Metalness: white = metal (painted_metal only; the others are
dielectric, so no metalness map is needed: Roblox treats a missing map as 0).

Usage (repo root):  python tools/materials/gen_pbr.py [--size 1024] [--seed 7] [--only asphalt,concrete]
Needs numpy + pillow (requirements.txt).
"""
import argparse
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'build', 'materials')
PREVIEW = os.path.join(ROOT, 'docs', 'images', 'materials')


# --- periodic building blocks --------------------------------------------------------------------------------------
def freqs(n):
    f = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(f, f)
    return fx, fy, np.sqrt(fx * fx + fy * fy)


def fractal(rng, n, beta, lo=0.0, hi=0.5, aniso=(1.0, 1.0)):
    """Periodic 1/f^beta noise in [0, 1]; lo/hi band-limit in cycles per pixel; aniso stretches the spectrum."""
    fx, fy, _ = freqs(n)
    r = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    amp = np.zeros_like(r)
    band = (r > max(lo, 1.0 / n)) & (r <= hi)
    amp[band] = r[band] ** (-beta / 2.0 - 0.5)
    phase = np.exp(2j * np.pi * rng.random((n, n)))
    img = np.real(np.fft.ifft2(amp * phase))
    img -= img.min()
    return img / max(img.max(), 1e-9)


def blur(img, sigma):
    """Periodic Gaussian blur (FFT)."""
    if sigma <= 0:
        return img
    n = img.shape[0]
    _, _, r = freqs(n)
    k = np.exp(-2.0 * (np.pi * sigma * r) ** 2)
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))


def stamps_fast(rng, n, count, rmin, rmax):
    """Wrapping round blobs (aggregate chips, pits) in [0, 1]; each blob only touches its own window (wrapped
    indices), so thousands of blobs stay fast."""
    h = np.zeros((n, n))
    for _ in range(count):
        cx, cy = rng.random(2) * n
        rad = rng.uniform(rmin, rmax)
        w = int(np.ceil(rad)) + 1
        xs = np.arange(int(cx) - w, int(cx) + w + 1)
        ys = np.arange(int(cy) - w, int(cy) + w + 1)
        gx, gy = np.meshgrid(xs, ys)
        d = np.sqrt((gx - cx) ** 2 + (gy - cy) ** 2) / rad
        val = np.clip(1.0 - d * d, 0, 1) * rng.uniform(0.5, 1.0)
        iy, ix = np.ix_(ys % n, xs % n)
        h[iy, ix] = np.maximum(h[iy, ix], val)
    return h


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    # OpenGL: +Y up in texture space = towards smaller row index, so the green channel uses +dy
    nx, ny, nz = -dx, dy, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln, ny / ln, nz / ln], axis=-1)


def to_rgb8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def normal_rgb8(nrm):
    return to_rgb8(nrm * 0.5 + 0.5)


def colorize(t, c0, c1):
    """Lerp between two RGB colours (0..255) by t in [0, 1]; returns float RGB in [0, 1]."""
    c0, c1 = np.array(c0) / 255.0, np.array(c1) / 255.0
    return c0 + (c1 - c0) * t[..., None]


def grooves(n, period, width):
    """Wrapping grid of grooves (panel seams / joints): 1 on a groove, 0 elsewhere; period divides n."""
    i = np.arange(n) + 0.5 + period / 2  # grooves mid-tile, so the wrap edge itself is flat surface
    d = np.minimum(i % period, period - (i % period))
    line = np.clip(1.0 - d / max(width, 1e-6), 0, 1)
    return np.maximum(line[None, :], line[:, None])


# --- materials -----------------------------------------------------------------------------------------------------
def asphalt_base(rng, n):
    grain = fractal(rng, n, 0.6, lo=0.05)                 # fine binder grain
    mottle = fractal(rng, n, 2.2, hi=0.02)                # large soft patches (wear)
    stones = stamps_fast(rng, n, n * n // 260, 1.2, 3.4)  # aggregate chips
    height = 0.45 * grain + 0.55 * stones
    return grain, mottle, stones, height


def mat_asphalt(rng, n):
    grain, mottle, stones, height = asphalt_base(rng, n)
    t = np.clip(0.25 * grain + 0.45 * stones + 0.3 * mottle, 0, 1)
    albedo = colorize(t, (38, 39, 42), (92, 92, 96))
    rough = np.clip(0.86 + 0.1 * grain - 0.08 * stones, 0, 1)
    return {'albedo': albedo, 'normal': normal_from_height(height, 6.0), 'roughness': rough}


def mat_wet_asphalt(rng, n):
    grain, mottle, stones, height = asphalt_base(rng, n)
    puddle = blur(fractal(rng, n, 2.4, hi=0.03), 3)
    puddle = np.clip((puddle - 0.58) / 0.12, 0, 1)        # ~25% of the area under standing water
    t = np.clip(0.25 * grain + 0.45 * stones + 0.3 * mottle, 0, 1)
    albedo = colorize(t, (22, 23, 26), (58, 58, 62)) * (1.0 - 0.25 * puddle[..., None])
    rough = np.clip(0.32 + 0.12 * grain - 0.06 * stones, 0, 1) * (1.0 - puddle) + 0.04 * puddle
    flat = height * (1.0 - 0.9 * puddle)                  # water fills the texture in puddles
    return {'albedo': albedo, 'normal': normal_from_height(flat, 5.0), 'roughness': rough}


def mat_concrete(rng, n):
    pores = fractal(rng, n, 0.4, lo=0.12)
    cloud = fractal(rng, n, 2.0, hi=0.04)
    pits = stamps_fast(rng, n, n * n // 2500, 0.8, 1.8)
    joint = grooves(n, n, 2.5)                            # one expansion joint per tile (mid-tile, both axes)
    t = np.clip(0.55 * cloud + 0.25 * pores - 0.35 * pits, 0, 1)
    albedo = colorize(t, (118, 116, 110), (170, 168, 160)) * (1.0 - 0.45 * joint[..., None])
    height = 0.3 * pores - 0.5 * pits - 1.0 * joint
    rough = np.clip(0.78 + 0.12 * pores + 0.1 * joint, 0, 1)
    return {'albedo': albedo, 'normal': normal_from_height(height, 4.0), 'roughness': rough}


def mat_dark_glass(rng, n):
    smudge = blur(fractal(rng, n, 1.6, hi=0.06), 2)
    frame = grooves(n, n // 2, 6.0)                       # 2x2 panes with mullions per tile
    t = np.clip(0.15 * smudge, 0, 1)
    albedo = colorize(t, (16, 22, 32), (34, 44, 60))
    albedo = albedo * (1 - frame[..., None]) + np.array([46, 48, 54]) / 255.0 * frame[..., None]
    rough = np.clip(0.04 + 0.1 * smudge, 0, 1) * (1 - frame) + 0.55 * frame
    height = -0.8 * blur(frame, 1.0) + 0.01 * smudge
    return {'albedo': albedo, 'normal': normal_from_height(height, 3.0), 'roughness': rough}


def mat_painted_metal(rng, n):
    brushed = fractal(rng, n, 1.0, lo=0.01, aniso=(0.05, 1.0))  # streaks along X
    orange = fractal(rng, n, 1.4, lo=0.02, hi=0.15)              # paint orange-peel
    scratch = np.zeros((n, n))
    for _ in range(24):                                          # wrapping hairline scratches
        x0, y0 = rng.random(2) * n
        ang = rng.uniform(-0.4, 0.4)
        length = rng.uniform(n * 0.05, n * 0.25)
        s = np.linspace(0, length, int(length * 2))
        xs = (x0 + np.cos(ang) * s).astype(int) % n
        ys = (y0 + np.sin(ang) * s).astype(int) % n
        scratch[ys, xs] = 1.0
    scratch = np.clip(blur(scratch, 0.6) * 2, 0, 1) * 0.7
    t = np.clip(0.5 + 0.25 * (orange - 0.5) + 0.1 * (brushed - 0.5), 0, 1)
    paint = colorize(t, (60, 62, 68), (82, 84, 90))
    bare = np.array([150, 152, 156]) / 255.0
    albedo = paint * (1 - scratch[..., None]) + bare * scratch[..., None]
    rough = np.clip(0.45 + 0.15 * (orange - 0.5) + 0.05 * brushed, 0, 1) * (1 - scratch) + 0.3 * scratch
    metal = scratch
    height = 0.2 * orange - 0.6 * scratch
    return {'albedo': albedo, 'normal': normal_from_height(height, 3.0), 'roughness': rough, 'metalness': metal}


MATERIALS = {
    'asphalt': mat_asphalt,
    'wet_asphalt': mat_wet_asphalt,
    'concrete': mat_concrete,
    'dark_glass': mat_dark_glass,
    'painted_metal': mat_painted_metal,
}

SEED_OFFSET = {'asphalt': 0, 'wet_asphalt': 0, 'concrete': 101, 'dark_glass': 202, 'painted_metal': 303}


# --- output --------------------------------------------------------------------------------------------------------
def seam_metric(a):
    a = a.astype(np.float64)
    if a.ndim == 3:
        a = a.mean(axis=2)
    interior = np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean()
    edge = np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0, :] - a[-1, :]).mean()
    return edge / max(interior, 1e-9)


def write_set(name, maps, n):
    os.makedirs(OUT, exist_ok=True)
    imgs = {}
    for kind, data in maps.items():
        if kind == 'normal':
            arr = normal_rgb8(data)
        elif data.ndim == 3:
            arr = to_rgb8(data)
        else:
            arr = to_rgb8(data)
        mode = 'RGB' if arr.ndim == 3 else 'L'
        img = Image.fromarray(arr, mode)
        img.save(os.path.join(OUT, f'{name}_{kind}.png'), optimize=True)
        imgs[kind] = img
        print(f'  {name}_{kind}.png  {n}x{n}  seam {seam_metric(arr):.2f}')
    return imgs


def write_preview(name, imgs, cell=192):
    os.makedirs(PREVIEW, exist_ok=True)
    parts = [imgs['albedo'], imgs['normal'], imgs['roughness'].convert('RGB')]
    sheet = Image.new('RGB', (cell * 4, cell), (0, 0, 0))
    for i, im in enumerate(parts):
        sheet.paste(im.convert('RGB').resize((cell, cell), Image.LANCZOS), (i * cell, 0))
    half = imgs['albedo'].convert('RGB').resize((cell // 2, cell // 2), Image.LANCZOS)
    for dx in (0, 1):
        for dy in (0, 1):
            sheet.paste(half, (3 * cell + dx * cell // 2, dy * cell // 2))
    sheet.save(os.path.join(PREVIEW, f'{name}_preview.jpg'), quality=85)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--size', type=int, default=1024)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--only', default='', help='comma list of material names')
    ap.add_argument('--no-preview', action='store_true')
    a = ap.parse_args()
    names = [s for s in a.only.split(',') if s] or list(MATERIALS)
    for name in names:
        # wet asphalt shares the asphalt seed, so the two share the same stones (a road can switch between them)
        rng = np.random.default_rng(a.seed + SEED_OFFSET[name])
        print(name)
        imgs = write_set(name, MATERIALS[name](rng, a.size), a.size)
        if not a.no_preview:
            write_preview(name, imgs)
    print(f'maps in {OUT}')


if __name__ == '__main__':
    main()
