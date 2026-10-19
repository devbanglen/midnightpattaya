"""Procedural PBR texture sets for MIDNIGHT PATTAYA (VIS-3, extended in VIS-7.1c).

Writes, per set, build/materials/<Set>/ (gitignored, regenerable):
    color.png      sRGB albedo (RGB; RGBA for the alpha card PalmFrond)
    normal.png     tangent-space normal, OpenGL convention (+Y = green points UP the image, i.e. toward row 0)
    roughness.png  8-bit grey, white = rough
    metalness.png  8-bit grey, white = metal -- only for sets that have metal (PaintedMetal, Shutter, SignPanel);
                   every other set is a dielectric and Roblox treats an empty MetalnessMap as 0 (saves uploads/memory)
    height.png     8-bit grey height the normal map was derived from. NOT uploaded; validate_pbr.py re-integrates
                   the normal map and correlates it with this height to prove the handedness (OpenGL vs DirectX).
plus build/materials/manifest.json and upload_list.json / .csv (write_manifest), and small previews in
docs/images/materials/<Set>_preview.jpg (color | normal | roughness | 2x2 tiling check).

Tiled sets are seamless by construction: noise is synthesised in the frequency domain (periodic), blurs are FFT
convolutions, gradients use np.roll, stamped features and strokes wrap around the edges, and regular features
(slats, rings, joints) have a period that divides the tile. validate_pbr.py measures it (edge-wrap ratio).

Parameters per set: the SETS table at the end (edge size, tiled, Roblox target, base material + studs per tile for
the MaterialVariant, seed offset, content note). Common flags: --size overrides every set's edge (power of two),
--seed (default 7), --only DryAsphalt,Concrete, --no-preview.

Usage (repo root):  python tools/materials/gen_pbr.py [--seed 7] [--only Bark,PalmFrond] [--no-preview]
Needs numpy + pillow (requirements.txt).
"""
import argparse
import csv
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'build', 'materials')
PREVIEW = os.path.join(ROOT, 'docs', 'images', 'materials')
KIT_STUDS_PER_TILE = 8.0     # tools/blender/common/units.py UV_STUDS_PER_TILE (box-projected kit UVs)


# --- periodic building blocks --------------------------------------------------------------------------------------
def freqs(h, w=None):
    w = w or h
    fy = np.fft.fftfreq(h)[:, None] * np.ones((1, w))
    fx = np.fft.fftfreq(w)[None, :] * np.ones((h, 1))
    return fx, fy, np.sqrt(fx * fx + fy * fy)


def fractal(rng, n, beta, lo=0.0, hi=0.5, aniso=(1.0, 1.0), w=None):
    """Periodic 1/f^beta noise in [0, 1] (n rows x w columns); lo/hi band-limit in cycles per pixel; aniso stretches
    the spectrum: aniso=(0.05, 1) keeps high X frequencies only = long streaks running along Y (vertical),
    (1, 0.05) = streaks running along X (horizontal)."""
    w = w or n
    fx, fy, _ = freqs(n, w)
    r = np.sqrt((fx * aniso[0]) ** 2 + (fy * aniso[1]) ** 2)
    amp = np.zeros_like(r)
    band = (r > max(lo, 1.0 / max(n, w))) & (r <= hi)
    amp[band] = r[band] ** (-beta / 2.0 - 0.5)
    phase = np.exp(2j * np.pi * rng.random((n, w)))
    img = np.real(np.fft.ifft2(amp * phase))
    img -= img.min()
    return img / max(img.max(), 1e-9)


def blur(img, sigma):
    """Periodic Gaussian blur (FFT)."""
    if sigma <= 0:
        return img
    h, w = img.shape
    _, _, r = freqs(h, w)
    k = np.exp(-2.0 * (np.pi * sigma * r) ** 2)
    return np.real(np.fft.ifft2(np.fft.fft2(img) * k))


def stamps_fast(rng, n, count, rmin, rmax):
    """Wrapping round blobs (aggregate chips, pits) in [0, 1]."""
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


def strokes(rng, n, count, lmin, lmax, ang=(-0.4, 0.4), wander=0.0):
    """Wrapping 1-px polylines (scratches, cracks); wander = random walk of the direction per pixel (rad)."""
    s = np.zeros((n, n))
    for _ in range(count):
        x, y = rng.random(2) * n
        a = rng.uniform(*ang)
        for _k in range(int(rng.uniform(lmin, lmax))):
            s[int(y) % n, int(x) % n] = 1.0
            a += rng.normal(0, wander) if wander else 0.0
            x += np.cos(a)
            y += np.sin(a)
    return s


def normal_from_height(h, strength):
    """OpenGL tangent space: +X right, +Y UP the image (toward row 0), +Z out of the surface. Row index grows
    downward, so dh/d(up) = -(h[r+1] - h[r-1]) / 2 and n_y = -dh/d(up) = +dy."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    nx, ny, nz = -dx, dy, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln, ny / ln, nz / ln], axis=-1)


def to8(a):
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def colorize(t, c0, c1):
    c0, c1 = np.array(c0) / 255.0, np.array(c1) / 255.0
    return c0 + (c1 - c0) * t[..., None]


def grooves(n, period, width):
    """Wrapping grid of grooves (both axes): 1 on a groove, 0 elsewhere; period divides n; grooves sit mid-period,
    so the wrap edge itself is flat surface."""
    i = np.arange(n) + 0.5 + period / 2
    d = np.minimum(i % period, period - (i % period))
    line = np.clip(1.0 - d / max(width, 1e-6), 0, 1)
    return np.maximum(line[None, :], line[:, None])


def norm01(a):
    a = a - a.min()
    return a / max(a.max(), 1e-9)


# --- VIS-3 sets (looks unchanged) ---------------------------------------------------------------------------------
def asphalt_base(rng, n):
    grain = fractal(rng, n, 0.6, lo=0.05)                 # fine binder grain
    mottle = fractal(rng, n, 2.2, hi=0.02)                # large soft patches (wear)
    stones = stamps_fast(rng, n, n * n // 260, 1.2, 3.4)  # aggregate chips
    height = 0.45 * grain + 0.55 * stones
    return grain, mottle, stones, height


def mat_dry_asphalt(rng, n):
    grain, mottle, stones, height = asphalt_base(rng, n)
    t = np.clip(0.25 * grain + 0.45 * stones + 0.3 * mottle, 0, 1)
    color = colorize(t, (38, 39, 42), (92, 92, 96))
    rough = np.clip(0.86 + 0.1 * grain - 0.08 * stones, 0, 1)
    return {'color': color, 'height': height, 'nstrength': 6.0, 'roughness': rough}


def mat_wet_asphalt(rng, n):
    grain, mottle, stones, height = asphalt_base(rng, n)   # same seed as DryAsphalt: the same stones
    puddle = blur(fractal(rng, n, 2.4, hi=0.03), 3)
    puddle = np.clip((puddle - 0.58) / 0.12, 0, 1)         # ~25% of the area under standing water
    damp = blur(fractal(rng, n, 2.0, hi=0.05), 2)          # the film between puddles is uneven too
    t = np.clip(0.25 * grain + 0.45 * stones + 0.3 * mottle, 0, 1)
    color = colorize(t, (22, 23, 26), (58, 58, 62)) * (1.0 - 0.25 * puddle[..., None])
    rough = np.clip(0.26 + 0.14 * damp + 0.12 * grain - 0.06 * stones, 0, 1) * (1.0 - puddle) + 0.04 * puddle
    flat = height * (1.0 - 0.9 * puddle)                   # water fills the texture in puddles
    return {'color': color, 'height': flat, 'nstrength': 5.0, 'roughness': rough}


def mat_concrete(rng, n):
    pores = fractal(rng, n, 0.4, lo=0.12)
    cloud = fractal(rng, n, 2.0, hi=0.04)
    pits = stamps_fast(rng, n, n * n // 2500, 0.8, 1.8)
    joint = grooves(n, n, 2.5 * n / 1024)                 # one expansion joint per tile (mid-tile, both axes)
    t = np.clip(0.55 * cloud + 0.25 * pores - 0.35 * pits, 0, 1)
    color = colorize(t, (118, 116, 110), (170, 168, 160)) * (1.0 - 0.45 * joint[..., None])
    height = 0.3 * pores - 0.5 * pits - 1.0 * joint
    rough = np.clip(0.78 + 0.12 * pores + 0.1 * joint, 0, 1)
    return {'color': color, 'height': height, 'nstrength': 4.0, 'roughness': rough}


def mat_dark_glass_grid(rng, n):
    smudge = blur(fractal(rng, n, 1.6, hi=0.06), 2)
    frame = grooves(n, n // 2, 6.0 * n / 1024)             # 2x2 panes with mullions per tile
    t = np.clip(0.15 * smudge, 0, 1)
    color = colorize(t, (16, 22, 32), (34, 44, 60))
    color = color * (1 - frame[..., None]) + np.array([46, 48, 54]) / 255.0 * frame[..., None]
    rough = np.clip(0.04 + 0.1 * smudge, 0, 1) * (1 - frame) + 0.55 * frame
    height = -0.8 * blur(frame, 1.0) + 0.01 * smudge
    return {'color': color, 'height': height, 'nstrength': 3.0, 'roughness': rough}


def mat_painted_metal(rng, n):
    brushed = fractal(rng, n, 1.0, lo=0.01, aniso=(0.05, 1.0))  # brushed streaks (vertical)
    orange = fractal(rng, n, 1.4, lo=0.02, hi=0.15)              # paint orange-peel
    scratch = np.clip(blur(strokes(rng, n, 24, n * 0.05, n * 0.25), 0.6) * 2, 0, 1) * 0.7
    t = np.clip(0.5 + 0.25 * (orange - 0.5) + 0.1 * (brushed - 0.5), 0, 1)
    paint = colorize(t, (60, 62, 68), (82, 84, 90))
    bare = np.array([150, 152, 156]) / 255.0
    color = paint * (1 - scratch[..., None]) + bare * scratch[..., None]
    rough = np.clip(0.45 + 0.15 * (orange - 0.5) + 0.05 * brushed, 0, 1) * (1 - scratch) + 0.3 * scratch
    return {'color': color, 'height': 0.2 * orange - 0.6 * scratch, 'nstrength': 3.0, 'roughness': rough,
            'metalness': scratch}


# --- VIS-7.1c sets ------------------------------------------------------------------------------------------------
def mat_dark_glass(rng, n):
    """Plain pane (no mullions: the kit models its mullions as geometry): smudges, vertical rain streaks, a very
    faint pane waviness in the normal map."""
    smudge = blur(fractal(rng, n, 1.6, hi=0.06), 2)
    streak = fractal(rng, n, 1.2, lo=0.01, aniso=(0.04, 1.0))   # long vertical streaks (rain runs down the pane)
    streak = np.clip((streak - 0.55) / 0.3, 0, 1)
    wave = fractal(rng, n, 2.6, hi=0.01)
    t = np.clip(0.12 * smudge + 0.25 * streak, 0, 1)
    color = colorize(t, (16, 22, 32), (40, 48, 62))
    rough = np.clip(0.03 + 0.08 * smudge + 0.18 * streak, 0, 1)
    return {'color': color, 'height': wave * 0.6 + 0.02 * streak, 'nstrength': 2.0, 'roughness': rough}


PLASTER_TONES = {   # (dark, light) sRGB; A is near-neutral so SurfaceAppearance.Color / a palette tint can drive it
    'A': ((206, 202, 192), (246, 243, 236)),   # warm white
    'B': ((196, 170, 132), (232, 210, 172)),   # sand / cream shophouse render
    'C': ((128, 168, 160), (174, 206, 196)),   # faded pastel mint
}


def plaster(tone):
    def make(rng, n):
        stucco = fractal(rng, n, 0.5, lo=0.08)                       # fine trowel / sand grain
        cloud = fractal(rng, n, 2.2, hi=0.03)                        # large repaint patches
        streak = fractal(rng, n, 1.3, lo=0.004, aniso=(0.06, 1.0))   # water stains running down (vertical)
        streak = np.clip((streak - 0.5) / 0.35, 0, 1) * blur(fractal(rng, n, 2.0, hi=0.02), 4)
        crack = np.clip(blur(strokes(rng, n, 4, n * 0.15, n * 0.4, ang=(1.2, 1.9), wander=0.05), 0.5) * 2, 0, 1)  # hairline cracks
        patch = np.clip((blur(fractal(rng, n, 2.6, hi=0.02), 2) - 0.72) / 0.05, 0, 1)   # smoother repaired spots
        dark, light = PLASTER_TONES[tone]
        t = np.clip(0.55 + 0.25 * (cloud - 0.5) + 0.12 * (stucco - 0.5) + 0.08 * patch, 0, 1)
        color = colorize(t, dark, light)
        color *= (1.0 - 0.22 * streak[..., None]) * (1.0 - 0.2 * crack[..., None])
        height = 0.5 * stucco * (1 - 0.6 * patch) - 0.5 * crack
        rough = np.clip(0.82 + 0.1 * stucco - 0.1 * patch - 0.08 * streak, 0, 1)
        return {'color': color, 'height': height, 'nstrength': 3.0, 'roughness': rough}
    return make


def mat_shutter(rng, n):
    """Corrugated galvanised roller shutter: horizontal slats (32 per tile = 0.25 stud each on the kit's 8-stud
    tiling), rounded crest + narrow hinge groove, zinc spangle, dirt settled in the grooves, a few rust spots."""
    p = n / 32
    y = (np.arange(n) + 0.5 + p / 2) % p / p                         # 0..1 within a slat; wrap edge = mid-crest
    prof = np.sin(np.pi * np.clip((y - 0.08) / 0.84, 0, 1)) ** 0.6   # crest
    groove = np.clip(1.0 - np.minimum(y, 1 - y) / 0.08, 0, 1)        # hinge line between slats
    prof = prof[:, None] * np.ones((1, n))
    groove = groove[:, None] * np.ones((1, n))
    spangle = fractal(rng, n, 1.0, lo=0.02, hi=0.2)
    dirt = np.clip(groove * 0.9 + 0.5 * (fractal(rng, n, 2.0, hi=0.03) - 0.5), 0, 1)
    rust = np.clip((blur(fractal(rng, n, 1.8, hi=0.05), 1.5) - 0.78) / 0.08, 0, 1)
    zinc = colorize(np.clip(0.5 + 0.35 * (spangle - 0.5), 0, 1), (120, 124, 126), (168, 172, 174))
    color = zinc * (1 - 0.55 * dirt[..., None])
    rustc = np.array([118, 70, 40]) / 255.0
    color = color * (1 - rust[..., None]) + rustc * rust[..., None]
    metal = np.clip(0.9 * (1 - dirt) * (1 - rust), 0, 1)
    rough = np.clip(0.42 + 0.12 * spangle + 0.4 * dirt + 0.45 * rust, 0, 1)
    height = prof - 0.6 * groove + 0.05 * rust
    return {'color': color, 'height': height, 'nstrength': 5.0, 'roughness': rough, 'metalness': metal}


def mat_bark(rng, n):
    """Coconut palm trunk: grey-brown, irregular horizontal leaf-scar rings (16 per tile = 0.5 stud) and fine
    vertical fibres. Rings run along X because the box-projected UVs put V on world Z (the trunk axis)."""
    per = n / 16
    wob = fractal(rng, n, 2.0, hi=0.02)                       # each ring wobbles (periodic, so still seamless)
    y = (np.arange(n)[:, None] + per / 2 + (wob - 0.5) * per * 0.6) % per / per   # wrap edge = mid-scar
    ring = np.exp(-((y - 0.5) / 0.09) ** 2)                   # raised scar ridge mid-ring
    gap = np.exp(-((np.minimum(y, 1 - y)) / 0.06) ** 2)       # dark crease between scars
    fiss = fractal(rng, n, 1.0, lo=0.02, aniso=(0.08, 1.0))   # vertical fibres
    fiss = np.clip((fiss - 0.5) / 0.3, 0, 1)
    lichen = np.clip((blur(fractal(rng, n, 1.8, hi=0.04), 1) - 0.7) / 0.1, 0, 1)
    t = np.clip(0.5 + 0.3 * ring - 0.45 * gap - 0.25 * fiss, 0, 1)
    color = colorize(t, (62, 52, 44), (150, 136, 118))
    color = color * (1 - 0.4 * lichen[..., None]) + np.array([98, 104, 80]) / 255.0 * 0.4 * lichen[..., None]
    height = 0.8 * ring - 0.7 * gap - 0.35 * fiss
    rough = np.clip(0.88 + 0.08 * fiss - 0.05 * ring, 0, 1)
    return {'color': color, 'height': height, 'nstrength': 6.0, 'roughness': rough}


def bleed(c, a, steps=64):
    """Push the colour of opaque pixels outward into transparent ones (repeated 3x3 average of covered pixels), so
    mip-maps and bilinear filtering never pull a black / default fringe into the leaf edges."""
    m = (a > 0.5).astype(np.float64)
    acc_c, acc_m = c * m[..., None], m.copy()
    for _ in range(steps):
        if acc_m.min() > 0:
            break
        sc = sum(np.roll(np.roll(acc_c * acc_m[..., None], dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        sm = sum(np.roll(np.roll(acc_m, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        grow = (acc_m == 0) & (sm > 0)
        acc_c[grow] = sc[grow] / sm[grow][..., None]
        acc_m[grow] = 1.0
    mean = (c * m[..., None]).sum(axis=(0, 1)) / max(m.sum(), 1)
    out = np.where(acc_m[..., None] > 0, acc_c, mean)
    return np.where(m[..., None] > 0, c, out)


def mat_palm_frond(rng, n):
    """Alpha card, (n/2) x n (u across, v along the frond: base at the image BOTTOM, which is the v = 0 end of
    common/mesh.py card() in Blender and, after the glTF V flip and back, in Roblox). Central rachis, 34 leaflets
    per side angled ~28-40 deg toward the tip and drooping, longest mid-frond, a few brown tips. Colour is bled
    into the transparent area."""
    W, H = n // 2, n
    ss = 2
    img_a = Image.new('L', (W * ss, H * ss), 0)
    img_c = Image.new('RGB', (W * ss, H * ss), (60, 100, 40))
    img_h = Image.new('L', (W * ss, H * ss), 0)
    da, dc, dh = ImageDraw.Draw(img_a), ImageDraw.Draw(img_c), ImageDraw.Draw(img_h)
    cx = W * ss / 2
    base_y, tip_y = H * ss * 0.995, H * ss * 0.02
    nleaf = 34
    for side in (-1, 1):
        for i in range(nleaf):
            u = (i + 0.5 + rng.uniform(-0.2, 0.2)) / nleaf     # 0 base .. 1 tip
            y0 = base_y + (tip_y - base_y) * (0.04 + 0.94 * u)
            env = np.sin(np.pi * min(1.0, 0.12 + 0.95 * u)) ** 0.7
            ang = np.radians(rng.uniform(28, 40))               # from horizontal, toward the tip
            ln = (0.08 + 0.92 * env) * (W * ss / 2 - 6) / np.cos(ang) * rng.uniform(0.9, 1.0)
            wid = W * ss * 0.022 * (0.6 + 0.6 * env)
            pts = []
            for k in range(9):
                s = k / 8
                a = ang - 0.18 * s * s                          # leaflets droop (curve back down)
                pts.append((cx + side * ln * s * np.cos(a), y0 - ln * s * np.sin(a), wid * (1 - s) ** 0.8 + 1.0))
            g = rng.uniform(0.85, 1.15)
            tip_brown = rng.random() < 0.08
            for k in range(8):
                (x0, ya, w0), (x1, yb, w1) = pts[k], pts[k + 1]
                L = max(np.hypot(x1 - x0, yb - ya), 1e-6)
                nx, ny = -(yb - ya) / L, (x1 - x0) / L
                poly = [(x0 + nx * w0, ya + ny * w0), (x1 + nx * w1, yb + ny * w1),
                        (x1 - nx * w1, yb - ny * w1), (x0 - nx * w0, ya - ny * w0)]
                s = k / 8
                col = (120, 98, 54) if (tip_brown and s > 0.6) else \
                    (int((44 + 50 * s) * g), int((92 + 52 * s) * g), int((34 + 14 * s) * g))
                da.polygon(poly, fill=255)
                dc.polygon(poly, fill=col)
                dh.polygon(poly, fill=int(150 + 60 * (1 - s)))
                dh.line([(x0, ya), (x1, yb)], fill=230, width=max(1, int(w0 * 0.35)))   # leaflet midrib
    for k in range(40):                                         # rachis on top, tapering to the tip
        s0, s1 = k / 40, (k + 1) / 40
        ya, yb = base_y + (tip_y - base_y) * s0, base_y + (tip_y - base_y) * s1
        w0 = W * ss * (0.035 * (1 - s0) + 0.006)
        poly = [(cx - w0, ya), (cx + w0, ya), (cx + w0 * 0.97, yb), (cx - w0 * 0.97, yb)]
        da.polygon(poly, fill=255)
        dc.polygon(poly, fill=(int(150 - 50 * s0), int(150 - 30 * s0), 70))
        dh.polygon(poly, fill=255)
    a = np.asarray(img_a.resize((W, H), Image.LANCZOS)).astype(np.float64) / 255.0
    c = np.asarray(img_c.resize((W, H), Image.LANCZOS)).astype(np.float64) / 255.0
    h = np.asarray(img_h.filter(ImageFilter.GaussianBlur(1.5)).resize((W, H), Image.LANCZOS)).astype(np.float64) / 255
    c = c * (0.9 + 0.2 * fractal(rng, H, 1.5, hi=0.08, w=W))[..., None]
    c = bleed(c, a)
    rough = np.clip(0.55 + 0.15 * (1 - h), 0, 1)
    return {'color': c, 'alpha': a, 'height': h, 'nstrength': 4.0, 'roughness': rough}


def mat_sign_panel(rng, n):
    """Sign board face, n x n/2, UV 0..1 on the board front (common/mesh.py panel()). Matte light acrylic face (the
    SurfaceGui text goes on top of it), a slightly uneven back-light glow, a brushed aluminium frame and 4 corner
    screws. The frame runs round every edge, so the box-projected board sides wrap cleanly too."""
    W, H = n, n // 2
    yy, xx = np.mgrid[0:H, 0:W]
    fw = max(4, n // 64)
    edge = np.minimum(np.minimum(xx, W - 1 - xx), np.minimum(yy, H - 1 - yy)).astype(np.float64)
    frame = (edge < fw).astype(np.float64)
    bevel = np.clip(1 - np.abs(edge - fw * 0.5) / (fw * 0.5), 0, 1) * frame
    glow = 1 - 0.12 * (((xx / W - 0.5) * 2) ** 2 + ((yy / H - 0.5) * 2) ** 2)
    blot = fractal(rng, H, 2.2, hi=0.03, w=W)
    face = np.clip(0.88 * glow + 0.06 * (blot - 0.5), 0, 1)
    color = np.stack([face * 0.97, face * 0.97, face], axis=-1)
    brushed = fractal(rng, H, 1.0, lo=0.02, aniso=(0.05, 1.0), w=W)
    alu = colorize(np.clip(0.5 + 0.3 * (brushed - 0.5), 0, 1), (150, 152, 156), (196, 198, 202))
    color = color * (1 - frame[..., None]) + alu * frame[..., None]
    height = 0.6 * bevel + 0.2 * frame
    metal = frame.copy()
    for sx, sy in ((fw * 3, fw * 3), (W - fw * 3, fw * 3), (fw * 3, H - fw * 3), (W - fw * 3, H - fw * 3)):
        sc = np.clip(1 - np.hypot(xx - sx, yy - sy) / (fw * 0.9), 0, 1)
        on = (sc > 0)[..., None]
        height = height + 0.6 * np.sqrt(sc)
        metal = np.maximum(metal, on[..., 0].astype(np.float64))
        color = np.where(on, np.array([0.62, 0.63, 0.65]), color)
    rough = np.where(metal > 0.5, 0.35 + 0.1 * brushed, 0.5 + 0.05 * blot)
    return {'color': color, 'height': height, 'nstrength': 4.0, 'roughness': rough, 'metalness': metal}


# Set table. targets: 'MaterialVariant' = plain Parts (BaseMaterial `base`, StudsPerTile `studs`; values match the
# MaterialLibrary.luau entries) and/or 'SurfaceAppearance' = kit MeshParts (the mesh UVs set the tiling: box
# projection 8 studs per UV tile, or 0..1 per face for sign boards and frond cards). Edge sizes are powers of two
# and <= 1024 (mobile); `size` is the long edge (PalmFrond 512x1024, SignPanel 512x256).
SETS = {
    'DryAsphalt':     dict(fn=mat_dry_asphalt, size=1024, tiled=True, seed=0, targets=['MaterialVariant'],
                           base='Asphalt', studs=12, note='road slabs; binder grain + aggregate chips + wear'),
    'WetAsphalt':     dict(fn=mat_wet_asphalt, size=1024, tiled=True, seed=0, targets=['MaterialVariant'],
                           base='Asphalt', studs=12, note='same stones as DryAsphalt; darker; roughness 0.04 in '
                           'puddles (~25% of the area), ~0.26-0.5 elsewhere'),
    'Concrete':       dict(fn=mat_concrete, size=1024, tiled=True, seed=101,
                           targets=['MaterialVariant', 'SurfaceAppearance'], base='Concrete', studs=8,
                           note='sidewalks (variant) and kit MP_Concrete; one expansion joint per tile'),
    'PlasterFacadeA': dict(fn=plaster('A'), size=512, tiled=True, seed=404,
                           targets=['SurfaceAppearance', 'MaterialVariant'], base='Plaster', studs=8,
                           note='warm white (near neutral: the tint target for per-building colours)'),
    'PlasterFacadeB': dict(fn=plaster('B'), size=512, tiled=True, seed=404,
                           targets=['SurfaceAppearance', 'MaterialVariant'], base='Plaster', studs=8,
                           note='sand / cream render'),
    'PlasterFacadeC': dict(fn=plaster('C'), size=512, tiled=True, seed=404,
                           targets=['SurfaceAppearance', 'MaterialVariant'], base='Plaster', studs=8,
                           note='faded pastel mint'),
    'DarkGlass':      dict(fn=mat_dark_glass, size=512, tiled=True, seed=202, targets=['SurfaceAppearance'],
                           base=None, studs=None, note='plain pane for kit MP_Glass (mullions are geometry)'),
    'DarkGlassGrid':  dict(fn=mat_dark_glass_grid, size=1024, tiled=True, seed=202, targets=['MaterialVariant'],
                           base='Glass', studs=16, note='Part window bands: 2x2 panes + mullions per tile'),
    'PaintedMetal':   dict(fn=mat_painted_metal, size=512, tiled=True, seed=303,
                           targets=['MaterialVariant', 'SurfaceAppearance'], base='Metal', studs=6,
                           note='orange peel, brushed streaks, scratches to bare metal (metalness)'),
    'Shutter':        dict(fn=mat_shutter, size=512, tiled=True, seed=505, targets=['SurfaceAppearance'],
                           base=None, studs=None, note='corrugated, 32 slats per tile = 0.25 stud; galvanised'),
    'Bark':           dict(fn=mat_bark, size=512, tiled=True, seed=606, targets=['SurfaceAppearance'],
                           base=None, studs=None, note='palm trunk leaf-scar rings (16 per tile) + fibres'),
    'PalmFrond':      dict(fn=mat_palm_frond, size=1024, tiled=False, seed=707, targets=['SurfaceAppearance'],
                           base=None, studs=None, alpha=True,
                           note='alpha card 512x1024, UV 0..1 (card()); AlphaMode Transparency'),
    'SignPanel':      dict(fn=mat_sign_panel, size=512, tiled=False, seed=808, targets=['SurfaceAppearance'],
                           base=None, studs=None, note='512x256, UV 0..1 on the board front; frame wraps'),
}
MAP_KINDS = ('color', 'normal', 'roughness', 'metalness')


# --- output --------------------------------------------------------------------------------------------------------
def write_set(name, maps):
    d = os.path.join(OUT, name)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if f.endswith('.png'):
            os.remove(os.path.join(d, f))
    rgb = to8(maps['color'])
    files = {'color': Image.fromarray(np.dstack([rgb, to8(maps['alpha'])]), 'RGBA') if 'alpha' in maps
             else Image.fromarray(rgb, 'RGB')}
    nrm = normal_from_height(maps['height'], maps['nstrength'])
    files['normal'] = Image.fromarray(to8(nrm * 0.5 + 0.5), 'RGB')
    files['roughness'] = Image.fromarray(to8(maps['roughness']), 'L')
    if 'metalness' in maps:
        files['metalness'] = Image.fromarray(to8(maps['metalness']), 'L')
    files['height'] = Image.fromarray(to8(norm01(maps['height'])), 'L')
    for kind, im in files.items():
        im.save(os.path.join(d, f'{kind}.png'), optimize=True)
    return files


def write_preview(name, imgs, cell=192):
    os.makedirs(PREVIEW, exist_ok=True)
    w0, h0 = imgs['color'].size
    cw, ch = (cell, int(cell * h0 / w0)) if w0 >= h0 else (int(cell * w0 / h0), cell)
    sheet = Image.new('RGB', (cell * 4, cell), (40, 40, 44))

    def flat(im):
        if im.mode == 'RGBA':
            bg = Image.new('RGB', im.size, (40, 40, 44))
            bg.paste(im, mask=im.split()[3])
            return bg
        return im.convert('RGB')
    for i, k in enumerate(('color', 'normal', 'roughness')):
        sheet.paste(flat(imgs[k]).resize((cw, ch), Image.LANCZOS), (i * cell, 0))
    half = flat(imgs['color']).resize((cw // 2, ch // 2), Image.LANCZOS)
    for dx in (0, 1):
        for dy in (0, 1):
            sheet.paste(half, (3 * cell + dx * (cw // 2), dy * (ch // 2)))
    sheet.save(os.path.join(PREVIEW, f'{name}_preview.jpg'), quality=85)


def write_manifest(seed):
    """manifest.json: set -> files (size, bytes), tiling, Roblox target(s). upload_list.json / .csv: one row per PNG
    to upload as an Image asset; `name` (MP_<Set>_<map>) is the display name and the key of the id file the leader
    writes after the upload (tools/materials/make_maps_module.py)."""
    sets, uploads = {}, []
    for name, cfg in SETS.items():
        d = os.path.join(OUT, name)
        if not os.path.isdir(d):
            continue
        files = {}
        for kind in MAP_KINDS:
            p = os.path.join(d, f'{kind}.png')
            if not os.path.exists(p):
                continue
            with Image.open(p) as im:
                w, h, mode = im.size[0], im.size[1], im.mode
            rel = f'{name}/{kind}.png'
            files[kind] = {'path': rel, 'width': w, 'height': h, 'mode': mode, 'bytes': os.path.getsize(p)}
            uploads.append({'name': f'MP_{name}_{kind}', 'set': name, 'map': kind, 'path': f'build/materials/{rel}',
                            'width': w, 'height': h})
        sets[name] = {
            'files': files,
            'tileable': cfg['tiled'],
            'targets': cfg['targets'],
            'materialVariant': ({'baseMaterial': cfg['base'], 'studsPerTile': cfg['studs']}
                                if 'MaterialVariant' in cfg['targets'] else None),
            'surfaceAppearance': ({'uv': f'box projection, {KIT_STUDS_PER_TILE:g} studs per UV tile' if cfg['tiled']
                                   else 'per-face 0..1',
                                   'alphaMode': 'Transparency' if cfg.get('alpha') else 'Overlay'}
                                  if 'SurfaceAppearance' in cfg['targets'] else None),
            'metalness': 'map' if 'metalness' in files else 'none (dielectric: MetalnessMap left empty = 0)',
            'note': cfg['note'],
        }
    man = {'generator': 'tools/materials/gen_pbr.py', 'seed': seed,
           'normalConvention': 'OpenGL (+Y green up the image), tangent space',
           'colorSpace': 'color = sRGB; normal / roughness / metalness = linear data',
           'roughness': 'white = rough', 'metalness': 'white = metal', 'sets': sets}
    with open(os.path.join(OUT, 'manifest.json'), 'w') as f:
        json.dump(man, f, indent=1)
    with open(os.path.join(OUT, 'upload_list.json'), 'w') as f:
        json.dump(uploads, f, indent=1)
    with open(os.path.join(OUT, 'upload_list.csv'), 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=['name', 'set', 'map', 'path', 'width', 'height'])
        wr.writeheader()
        wr.writerows(uploads)
    return man, uploads


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--size', type=int, default=0, help='override the long edge of every set (power of two)')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--only', default='', help='comma list of set names')
    ap.add_argument('--no-preview', action='store_true')
    a = ap.parse_args()
    names = [s for s in a.only.split(',') if s] or list(SETS)
    for name in names:
        cfg = SETS[name]
        n = a.size or cfg['size']
        rng = np.random.default_rng(a.seed + cfg['seed'])   # Dry/WetAsphalt share a seed: the same stones
        imgs = write_set(name, cfg['fn'](rng, n))
        w, h = imgs['color'].size
        print(f'{name:15s} {w}x{h}  {", ".join(k for k in imgs if k != "height")}')
        if not a.no_preview:
            write_preview(name, imgs)
    man, up = write_manifest(a.seed)
    print(f'{len(man["sets"])} sets, {len(up)} images to upload; manifest + upload list in {OUT}')


if __name__ == '__main__':
    main()
