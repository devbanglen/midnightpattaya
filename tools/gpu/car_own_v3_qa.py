"""QA numbers and sheets for the own body v3 (docs/CAR_IMPORT_RED_SPORTS.md, "Own body v3"). numpy + Pillow, offline.

  python tools/gpu/car_own_v3_qa.py silhouette <cars_dir> <qa_dir> [--id red_sports_own_v3] [--ref-dir <dir>]
      side and top silhouettes of the body vs red_sports_fictional (and v2): IoU, roofline difference along the
      length, overlay image <qa_dir>/<id>_silhouette.png, numbers <cars_dir>/<id>_qa.json (key "silhouette")
  python tools/gpu/car_own_v3_qa.py clearance <cars_dir> [--id red_sports_own_v3]
      tyre envelope (cylinder r = layout radius, width = v2 tyre width) vs the body: clearance at rest, over the
      steering range (fronts, +-28 deg about the vertical axis through the wheel centre) and the free bump travel;
      numbers into <id>_qa.json (key "clearance")
  python tools/gpu/car_own_v3_qa.py shells <cars_dir> [--id red_sports_own_v3]
      closed-shell check of the body GLB (welded by position): components, open edges, duplicate directed edges,
      outward winding; numbers into <id>_qa.json (key "shells")
  python tools/gpu/car_own_v3_qa.py grid <out.png> <view1,view2,...> "<render_dir>|<id>|<tag>|<label>" ...
      QA sheet from renders (one row per view, one column per car); same as car_original_v2.py grid

Frame N: X right, Y up, front -Z, metres, body centred on its bounding box (the wheel layout's frame).
"""
import hashlib
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import car_debrand as cd  # noqa: E402

ID = 'red_sports_own_v3'
REF = 'red_sports_fictional'
V2 = 'red_sports_original_v2'
TYRE_W = 0.344
STEER = 28.0
RES = 0.005                  # silhouette pixel, metres


def load_body(cars_dir, cid):
    js, b = cd.glb_read(os.path.join(cars_dir, f'{cid}.glb'))
    P, N, UV, T = cd.mesh_arrays(js, b)
    return P, T


def silhouette(P, T, h_axis, v_axis, h_rng, v_rng, sign_h=1.0):
    """Orthographic silhouette (bool image, rows = v from top) of the triangles on the plane (h_axis, v_axis)."""
    W = int(round((h_rng[1] - h_rng[0]) / RES))
    H = int(round((v_rng[1] - v_rng[0]) / RES))
    im = Image.new('1', (W, H), 0)
    dr = ImageDraw.Draw(im)
    q = P[:, [h_axis, v_axis]] * (sign_h, 1.0)
    px = np.stack([(q[:, 0] - h_rng[0]) / RES, (v_rng[1] - q[:, 1]) / RES], 1)
    for t in T:
        dr.polygon([tuple(px[i]) for i in t], fill=1, outline=1)
    return np.asarray(im, bool)


def fill_holes(S):
    """Silhouette with its enclosed holes filled: background = what a flood fill from the border reaches."""
    im = Image.fromarray(np.pad(S, 1).astype(np.uint8) * 255).copy()     # (fromarray may share a read-only buffer)
    ImageDraw.floodfill(im, (0, 0), 128)
    return (np.asarray(im) != 128)[1:-1, 1:-1]


def top_line(S):
    """Per column: the top-most filled row (index, -1 where empty)."""
    any_ = S.any(0)
    return np.where(any_, S.argmax(0), -1)


def silhouette_qa(cars_dir, qa_dir, cid=ID, ref_dir=None):
    out = {}
    bodies = {k: load_body(ref_dir or cars_dir, k) for k in (REF, V2)}
    bodies[cid] = load_body(cars_dir, cid)
    zr, yr, xr = (-2.30, 2.30), (-0.75, 0.70), (-1.20, 1.20)
    side = {k: silhouette(P, T, 2, 1, zr, yr) for k, (P, T) in bodies.items()}
    top = {k: silhouette(P, T, 2, 0, zr, xr) for k, (P, T) in bodies.items()}

    def iou(a, b):
        return float((a & b).sum() / max((a | b).sum(), 1))
    out['side_iou_vs_fictional'] = round(iou(side[cid], side[REF]), 4)
    out['top_iou_vs_fictional'] = round(iou(top[cid], top[REF]), 4)
    out['side_iou_v2_vs_fictional'] = round(iou(side[V2], side[REF]), 4)
    out['top_iou_v2_vs_fictional'] = round(iou(top[V2], top[REF]), 4)
    # the fictional and v2 side silhouettes have see-through window holes: the same numbers with the holes filled
    sf = {k: fill_holes(v) for k, v in side.items()}
    out['side_iou_vs_fictional_holes_filled'] = round(iou(sf[cid], sf[REF]), 4)
    out['side_iou_v2_vs_fictional_holes_filled'] = round(iou(sf[V2], sf[REF]), 4)
    # roofline (top of the side silhouette) along the length
    ref, own = top_line(side[REF]), top_line(side[cid])
    ok = (ref >= 0) & (own >= 0)
    zc = zr[0] + (np.arange(side[cid].shape[1]) + 0.5) * RES
    y_ref = yr[1] - (ref + 0.5) * RES
    y_own = yr[1] - (own + 0.5) * RES
    d = np.where(ok, y_own - y_ref, np.nan)
    out['roofline'] = {
        'mean_abs_diff_m': round(float(np.nanmean(np.abs(d))), 4),
        'max_lower_m': round(float(-np.nanmin(d)), 4), 'max_lower_at_z': round(float(zc[np.nanargmin(d)]), 3),
        'max_higher_m': round(float(np.nanmax(d)), 4), 'max_higher_at_z': round(float(zc[np.nanargmax(d)]), 3),
        'share_of_length_diff_over_5cm': round(float(np.nanmean(np.abs(d) > 0.05)), 3),
        'roof_peak_z': {'fictional': round(float(zc[np.argmax(np.where(ref >= 0, -ref, -10 ** 6))]), 3),
                        cid: round(float(zc[np.argmax(np.where(own >= 0, -own, -10 ** 6))]), 3)},
        'samples_every_0_25m': [{'z': round(float(z), 2), 'fictional_y': round(float(y_ref[i]), 3),
                                 'own_y': round(float(y_own[i]), 3), 'diff': round(float(d[i]), 3)}
                                for z in np.arange(-2.25, 2.26, 0.25)
                                for i in [int(np.argmin(np.abs(zc - z)))] if ok[i]],
    }
    # greenhouse position: where the side silhouette is taller than the belt (y > 0.3), as a share of the length
    for k in (REF, cid):
        tl = yr[1] - (top_line(side[k]) + 0.5) * RES
        cab = zc[(top_line(side[k]) >= 0) & (tl > 0.45)]
        out[f'cabin_above_0_45m_z_{"fictional" if k == REF else "own"}'] = [round(float(cab.min()), 3),
                                                                          round(float(cab.max()), 3)]
    # overlay image: grey = both, red = fictional only, blue = own only; roofline curves
    os.makedirs(qa_dir, exist_ok=True)
    panels = []
    for name, S in (('side', side), ('top', top)):
        a, b = S[REF], S[cid]
        img = np.full(a.shape + (3,), 255, np.uint8)
        img[a & b] = (150, 150, 155)
        img[a & ~b] = (226, 74, 70)
        img[b & ~a] = (52, 104, 214)
        im = Image.fromarray(img)
        dr = ImageDraw.Draw(im)
        if name == 'side':
            for line, col in ((ref, (150, 20, 20)), (own, (10, 40, 140))):
                pts = [(i, int(r)) for i, r in enumerate(line) if r >= 0]
                dr.line(pts, fill=col, width=2)
        panels.append((name, im))
    W = max(p.width for _, p in panels)
    H = sum(p.height + 76 for _, p in panels) + 40
    sheet = Image.new('RGB', (W + 20, H), 'white')
    dr = ImageDraw.Draw(sheet)
    y = 10
    dr.text((10, y), f'{cid} (blue) over {REF} (red); grey = both. 5 mm pixels, body meshes only (no wheels).',
            fill='black')
    y += 20
    rl = out['roofline']
    for name, p in panels:
        lines = [f'{name} view (nose left): IoU {out[name + "_iou_vs_fictional"]:.3f} '
                 f'(v2 vs fictional {out[name + "_iou_v2_vs_fictional"]:.3f})']
        if name == 'side':
            lines[0] += (f'; with the window holes filled {out["side_iou_vs_fictional_holes_filled"]:.3f} '
                         f'(v2 {out["side_iou_v2_vs_fictional_holes_filled"]:.3f})')
            lines.append(f"roofline: mean |diff| {rl['mean_abs_diff_m'] * 100:.1f} cm, own lower by up to "
                         f"{rl['max_lower_m'] * 100:.1f} cm (z {rl['max_lower_at_z']}), higher by up to "
                         f"{rl['max_higher_m'] * 100:.1f} cm (z {rl['max_higher_at_z']}); roof peak z "
                         f"{rl['roof_peak_z'][cid]} (fictional {rl['roof_peak_z']['fictional']})")
        for k, line in enumerate(lines):
            dr.text((10, y + 14 * k), line, fill='black')
        sheet.paste(p, (10, y + 34))
        y += p.height + 76
    sheet.save(os.path.join(qa_dir, f'{cid}_silhouette.png'), optimize=True)
    return out


# ------------------------------------------------------------------------------------------------- clearance --
def surface_samples(P, T, n=4):
    """Points on every triangle (barycentric grid with n steps per edge) -> (k, 3)."""
    pts = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            a, b = i / n, j / n
            c = 1 - a - b
            pts.append(P[T[:, 0]] * a + P[T[:, 1]] * b + P[T[:, 2]] * c)
    return np.concatenate(pts)


def cyl_sd(q, r, hw):
    """Signed distance of points q (wheel frame: x = axle) to a closed cylinder (radius r, half width hw)."""
    rad = np.hypot(q[:, 1], q[:, 2]) - r
    ax = np.abs(q[:, 0]) - hw
    out = np.hypot(np.maximum(rad, 0), np.maximum(ax, 0))
    return np.where((rad > 0) | (ax > 0), out, np.maximum(rad, ax))


def clearance_qa(cars_dir, cid=ID):
    P, T = load_body(cars_dir, cid)
    with open(os.path.join(cars_dir, f'{cid}_wheels.json'), encoding='utf-8') as f:
        lay = json.load(f)
    r, hw = lay['radius'], TYRE_W / 2
    S = surface_samples(P, T)
    out = {'tyre_envelope': {'radius_m': r, 'width_m': TYRE_W, 'note': 'closed cylinder round the v2 tyre'},
           'steer_deg': STEER}
    for k, c in lay['wheels'].items():
        c = np.array(c)
        q0 = S - c
        near = (np.abs(q0[:, 0]) < 0.75) & (np.abs(q0[:, 1]) < 0.75) & (np.abs(q0[:, 2]) < 0.75)
        q0 = q0[near]
        rest = cyl_sd(q0, r, hw)
        rec = {'rest_min_clearance_m': round(float(rest.min()), 4),
               'rest_points_inside': int((rest < 0).sum())}
        # free bump travel: raise the wheel until the envelope touches the body
        lo_h, hi_h = 0.0, 0.40
        for _ in range(30):
            h = (lo_h + hi_h) / 2
            if cyl_sd(q0 - (0, h, 0), r, hw).min() > 0:
                lo_h = h
            else:
                hi_h = h
        rec['free_bump_travel_m'] = round(lo_h, 4)
        if k[0] == 'F':
            worst, worst_a = 1e9, 0.0
            per = {}
            for a in np.arange(-STEER, STEER + 0.01, 1.0):
                th = math.radians(a)
                ca, sa = math.cos(th), math.sin(th)
                # rotate the body points by -a about the vertical axis = the wheel turned by +a
                q = np.stack([ca * q0[:, 0] - sa * q0[:, 2], q0[:, 1], sa * q0[:, 0] + ca * q0[:, 2]], 1)
                m = float(cyl_sd(q, r, hw).min())
                per[round(float(a))] = round(m, 4)
                if m < worst:
                    worst, worst_a = m, a
            rec['steer_min_clearance_m'] = round(worst, 4)
            rec['steer_min_at_deg'] = round(float(worst_a))
            rec['steer_clearance_at_full_lock_m'] = {'-28': per[-28], '+28': per[28]}
        out[k] = rec
    return out


def shell_check(P, T, tol=1e-6):
    """Closed-shell check of a triangle mesh: vertices welded by position (tol), triangles grouped into connected
    components; each component must use every edge once in each direction (closed, consistently wound) and have a
    positive signed volume (wound outward, glTF counter-clockwise front faces). Returns a summary dict."""
    key = np.round(P / tol).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    W = weld[T]
    m = len(W)
    par = np.arange(weld.max() + 1)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for t in W:
        r0 = find(t[0])
        for v in t[1:]:
            r = find(v)
            if r != r0:
                par[r] = r0
    comp = np.array([find(t[0]) for t in W])
    labels, comp = np.unique(comp, return_inverse=True)
    e_from = np.concatenate([W[:, 0], W[:, 1], W[:, 2]])
    e_to = np.concatenate([W[:, 1], W[:, 2], W[:, 0]])
    nv = int(weld.max()) + 1
    directed = e_from.astype(np.int64) * nv + e_to
    rev = e_to.astype(np.int64) * nv + e_from
    uniq, cnt = np.unique(directed, return_counts=True)
    dup = int((cnt > 1).sum())
    present = np.isin(rev, uniq)
    open_edges = int((~present).sum())
    tp = P[T]
    vol = np.einsum('ij,ij->i', tp[:, 0], np.cross(tp[:, 1], tp[:, 2])) / 6
    comp_vol = np.bincount(comp, vol, len(labels))
    return {'components': int(len(labels)), 'open_edge_uses': open_edges, 'duplicate_directed_edges': dup,
            'components_with_negative_volume': int((comp_vol <= 0).sum()),
            'min_component_volume_m3': round(float(comp_vol.min()), 7), 'triangles': int(m)}


def update_qa_json(cars_dir, cid, key, val):
    """Store one QA section in <cars_dir>/<cid>_qa.json, stamped with the sha256 of the body GLB it measured (the
    tests use the stamp to know the numbers belong to the committed build)."""
    path = os.path.join(cars_dir, f'{cid}_qa.json')
    data = {}
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    with open(os.path.join(cars_dir, f'{cid}.glb'), 'rb') as f:
        val = dict(val, measured_glb_sha256=hashlib.sha256(f.read()).hexdigest())
    data[key] = val
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write('\n')
    print(json.dumps({key: val}, indent=1))


def grid(out_path, names, columns, tile=480):
    """One row per view, one column per (render_dir, id, tag, label); every row as tall as its tallest thumbnail."""
    rows = [n for n in names if all(os.path.isfile(os.path.join(d, f'{i}_{t}_{n}.png')) for d, i, t, _ in columns)]
    thumbs = []
    for n in rows:
        row = []
        for d, i, t, label in columns:
            im = Image.open(os.path.join(d, f'{i}_{t}_{n}.png')).convert('RGB')
            im.thumbnail((tile, tile))
            row.append((im, f'{n}: {label}'))
        thumbs.append(row)
    heights = [max(im.height for im, _ in row) + 22 for row in thumbs]
    sh = Image.new('RGB', (len(columns) * tile, sum(heights)), 'white')
    dr = ImageDraw.Draw(sh)
    y = 0
    for row, h in zip(thumbs, heights):
        for c, (im, text) in enumerate(row):
            sh.paste(im, (c * tile, y + 22))
            dr.text((c * tile + 6, y + 5), text, fill='black')
        y += h
    sh.save(out_path, optimize=True)
    return rows


def main(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    cid = opt('--id', ID)
    if argv[0] == 'silhouette':
        update_qa_json(argv[1], cid, 'silhouette', silhouette_qa(argv[1], argv[2], cid, opt('--ref-dir')))
    elif argv[0] == 'clearance':
        update_qa_json(argv[1], cid, 'clearance', clearance_qa(argv[1], cid))
    elif argv[0] == 'shells':
        update_qa_json(argv[1], cid, 'shells', shell_check(*load_body(argv[1], cid)))
    elif argv[0] == 'grid':
        print(grid(argv[1], argv[2].split(','), [tuple(c.split('|')) for c in argv[3:]]))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
