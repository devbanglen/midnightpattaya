"""Offline checks for the PBR sets written by gen_pbr.py (reads build/materials/manifest.json).

Per map: file exists, power-of-two edges <= 1024, expected mode (color RGB / RGBA for alpha cards, normal RGB,
roughness / metalness L). Tiled sets: edge-wrap ratio (mean jump across the wrap edge / mean jump between interior
neighbours; ~1 = seamless, a seam shows up as >> 1). Normal maps: decoded length ~1, z > 0, mean slope ~0, and the
HANDEDNESS: the normal map is integrated back to a height field (Fourier Poisson solve) assuming OpenGL (+Y green
up) and assuming DirectX (green flipped); each is correlated with the height.png the map was made from, and OpenGL
must win clearly. A synthetic dome is checked the same way. Alpha cards: coverage, AA edge share, and colour bled into
the transparent area (no black fringe). Wet vs dry asphalt: darker, smoother, puddle share. Memory: total PNG bytes
(upload size) and two texture-memory estimates (uncompressed RGBA8 + mips = upper bound; block-compressed ~1 byte/px
for RGBA / normal and 0.5 byte/px for opaque colour / grey maps + mips, the usual BC/ASTC range; Roblox's own GPU
format is not documented, so this is an estimate).

Usage (repo root):  python tools/materials/validate_pbr.py      exit code 1 on any FAIL; writes validation.json
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gen_pbr import OUT, normal_from_height  # noqa: E402

SEAM_MAX = 1.5
MAX_EDGE = 1024


def pot(v):
    return v > 0 and (v & (v - 1)) == 0


def seam_ratio(a):
    a = a.astype(np.float64)
    if a.ndim == 3:
        a = a[..., :3].mean(axis=2)
    interior = np.abs(np.diff(a, axis=1)).mean() + np.abs(np.diff(a, axis=0)).mean()
    edge = np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0, :] - a[-1, :]).mean()
    return edge / max(interior, 1e-9)


def integrate(gx, gr):
    """Least-squares height from a periodic gradient field (central differences): gx = dh/dx (column), gr = dh/drow."""
    h, w = gx.shape
    fx = np.fft.fftfreq(w)[None, :]
    fr = np.fft.fftfreq(h)[:, None]
    dx = 1j * np.sin(2 * np.pi * fx)
    dr = 1j * np.sin(2 * np.pi * fr)
    den = np.abs(dx) ** 2 + np.abs(dr) ** 2
    den[den < 1e-12] = np.inf
    H = (np.conj(dx) * np.fft.fft2(gx) + np.conj(dr) * np.fft.fft2(gr)) / den
    return np.real(np.fft.ifft2(H))


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / max(np.sqrt((a * a).sum() * (b * b).sum()), 1e-12))


def handedness(nrm, height):
    """Correlation of the re-integrated height with the source height, OpenGL vs DirectX reading of green."""
    nx, ny, nz = nrm[..., 0], nrm[..., 1], np.maximum(nrm[..., 2], 1e-3)
    gx = -nx / nz                      # dh/dx
    gr_gl = ny / nz                    # OpenGL: n_y = -dh/d(up) = +dh/d(row)
    gr_dx = -ny / nz                   # DirectX: green points down the image
    return corr(integrate(gx, gr_gl), height), corr(integrate(gx, gr_dx), height)


def decode_normal(img):
    a = np.asarray(img.convert('RGB')).astype(np.float64) / 255.0 * 2 - 1
    return a


def mem(w, h, kind, mode):
    px = w * h * 4 / 3                                  # + mip chain
    raw = px * 4
    bpp = 1.0 if (kind == 'normal' or mode == 'RGBA') else 0.5
    return raw, px * bpp


def main():
    man = json.load(open(os.path.join(OUT, 'manifest.json')))
    fails, rows, out = [], [], {'sets': {}}
    tot_png = tot_raw = tot_bc = 0.0

    # synthetic dome: the generator's own convention must read as OpenGL
    yy, xx = np.mgrid[0:128, 0:128]
    dome = np.clip(1 - ((xx - 64) ** 2 + (yy - 64) ** 2) / 40.0 ** 2, 0, 1) ** 0.5
    nd = normal_from_height(dome, 8.0)
    top_green = nd[30:40, 60:68, 1].mean()             # upper flank (rows above centre) must face +Y = up
    gl, dxr = handedness(nd, dome)
    ok = top_green > 0.2 and gl > 0.9 and gl > dxr
    out['dome'] = {'upperFlankGreen': round(float(top_green), 3), 'corrOpenGL': round(gl, 3),
                   'corrDirectX': round(dxr, 3), 'ok': ok}
    print(f'dome self-test: upper flank n_y={top_green:+.2f}, corr OpenGL {gl:.3f} vs DirectX {dxr:.3f} '
          f'-> {"OK" if ok else "FAIL"}')
    if not ok:
        fails.append('dome self-test')

    for name, s in man['sets'].items():
        res = {}
        d = os.path.join(OUT, name)
        for kind, f in s['files'].items():
            p = os.path.join(OUT, f['path'])
            if not os.path.exists(p):
                fails.append(f'{name}/{kind}: missing')
                continue
            im = Image.open(p)
            w, h = im.size
            r = {'size': f'{w}x{h}', 'mode': im.mode, 'bytes': os.path.getsize(p)}
            tot_png += r['bytes']
            raw, bc = mem(w, h, kind, im.mode)
            tot_raw += raw
            tot_bc += bc
            if not (pot(w) and pot(h)) or max(w, h) > MAX_EDGE:
                fails.append(f'{name}/{kind}: size {w}x{h} not power of two <= {MAX_EDGE}')
            want = {'color': ('RGBA',) if s['surfaceAppearance'] and s['surfaceAppearance']['alphaMode'] ==
                    'Transparency' else ('RGB',), 'normal': ('RGB',), 'roughness': ('L',), 'metalness': ('L',)}[kind]
            if im.mode not in want:
                fails.append(f'{name}/{kind}: mode {im.mode}, want {want}')
            arr = np.asarray(im)
            if s['tileable']:
                sr = seam_ratio(arr)
                r['seam'] = round(float(sr), 2)
                if sr > SEAM_MAX:
                    fails.append(f'{name}/{kind}: seam ratio {sr:.2f} > {SEAM_MAX}')
            if kind == 'normal':
                n = decode_normal(im)
                ln = np.sqrt((n ** 2).sum(axis=2))
                r['lenMeanDev'] = round(float(np.abs(ln - 1).mean()), 3)
                r['minZ'] = round(float(n[..., 2].min()), 3)
                r['meanXY'] = [round(float(n[..., 0].mean()), 3), round(float(n[..., 1].mean()), 3)]
                hp = os.path.join(d, 'height.png')
                hgt = np.asarray(Image.open(hp)).astype(np.float64) / 255.0
                gl, dxr = handedness(n, hgt)
                r['corrOpenGL'], r['corrDirectX'] = round(gl, 3), round(dxr, 3)
                if r['lenMeanDev'] > 0.03 or r['minZ'] <= 0 or max(map(abs, r['meanXY'])) > 0.05:
                    fails.append(f'{name}/normal: not a clean unit tangent-space map {r}')
                if not (gl > 0.5 and gl > dxr + 0.2):
                    fails.append(f'{name}/normal: handedness unclear (OpenGL {gl:.2f}, DirectX {dxr:.2f})')
            if kind in ('roughness', 'metalness'):
                v = arr.astype(np.float64) / 255.0
                r['mean'] = round(float(v.mean()), 3)
                r['p5_p95'] = [round(float(np.percentile(v, 5)), 3), round(float(np.percentile(v, 95)), 3)]
            if kind == 'color' and im.mode == 'RGBA':
                a = arr[..., 3].astype(np.float64) / 255.0
                rgb = arr[..., :3].astype(np.float64)
                cov = float((a > 0.5).mean())
                aa = float(((a > 0.02) & (a < 0.98)).mean())
                lum_in = rgb[a > 0.5].mean()
                lum_out = rgb[a < 0.02].mean() if (a < 0.02).any() else lum_in
                r.update(alphaCoverage=round(cov, 3), alphaEdgeShare=round(aa, 3),
                         bleedLumRatio=round(float(lum_out / max(lum_in, 1e-6)), 2))
                if not (0.25 <= cov <= 0.75):
                    fails.append(f'{name}: alpha coverage {cov:.2f} outside 0.25..0.75')
                if lum_out < 0.5 * lum_in:
                    fails.append(f'{name}: transparent area not colour-bled (dark fringe risk)')
            res[kind] = r
        out['sets'][name] = res
        rows.append(name)
        line = '  '.join(f'{k}:{v["size"]}' + (f' seam {v["seam"]}' if 'seam' in v else '') for k, v in res.items())
        print(f'{name:15s} {line}')
        if 'normal' in res:
            n = res['normal']
            print(f'{"":15s} normal: OpenGL corr {n["corrOpenGL"]:.2f} vs DirectX {n["corrDirectX"]:.2f}, '
                  f'|n|-1 {n["lenMeanDev"]}, minZ {n["minZ"]}')
        if 'alphaCoverage' in res.get('color', {}):
            c = res['color']
            print(f'{"":15s} alpha coverage {c["alphaCoverage"]:.0%}, AA edge {c["alphaEdgeShare"]:.1%}, '
                  f'bleed lum ratio {c["bleedLumRatio"]}')

    # wet vs dry asphalt
    try:
        def ld(s, k):
            return np.asarray(Image.open(os.path.join(OUT, s, f'{k}.png'))).astype(np.float64) / 255.0
        dr, wr = ld('DryAsphalt', 'roughness'), ld('WetAsphalt', 'roughness')
        dc, wc = ld('DryAsphalt', 'color').mean(), ld('WetAsphalt', 'color').mean()
        puddle = float((wr < 0.1).mean())
        ok = wr.mean() < dr.mean() - 0.3 and wc < dc * 0.75 and 0.1 <= puddle <= 0.4
        out['wetVsDry'] = {'roughDry': round(float(dr.mean()), 3), 'roughWet': round(float(wr.mean()), 3),
                           'colorDry': round(float(dc), 3), 'colorWet': round(float(wc), 3),
                           'puddleShare': round(puddle, 3), 'ok': ok}
        print(f'wet vs dry: roughness {dr.mean():.2f} -> {wr.mean():.2f}, colour {dc:.3f} -> {wc:.3f}, '
              f'puddles (rough < 0.1) {puddle:.0%} -> {"OK" if ok else "FAIL"}')
        if not ok:
            fails.append('wet vs dry asphalt contrast')
    except FileNotFoundError:
        pass

    out['memory'] = {'pngBytes': int(tot_png), 'uncompressedRGBA8WithMips': int(tot_raw),
                     'compressedEstimateWithMips': int(tot_bc)}
    print(f'total: {sum(len(s) for s in out["sets"].values())} maps, PNG {tot_png / 2**20:.1f} MiB (upload), '
          f'texture memory upper bound {tot_raw / 2**20:.1f} MiB (RGBA8 + mips), '
          f'compressed estimate {tot_bc / 2**20:.1f} MiB')
    out['fails'] = fails
    with open(os.path.join(OUT, 'validation.json'), 'w') as f:
        json.dump(out, f, indent=1)
    print('FAIL:\n  ' + '\n  '.join(fails) if fails else 'ALL CHECKS PASSED')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
