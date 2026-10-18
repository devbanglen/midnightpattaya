"""Top-down self-check render of a circuit venue, drawn from the generated data module the way CircuitBuilder.luau
builds it (no Studio needed). It mirrors the builder's placement rules (normals, barrier offsets, grandstand front,
garage door side, grid slot heading, board facing, floodlight aim) so orientation mistakes show up on paper, and it
runs a few automatic checks that are printed and listed on the image.

  .venv\\Scripts\\python tools\\circuit\\render_venue.py roblox/data/circuits/bira.luau docs/images/bira_venue_render.png

World axes: x east (right), z south (down), so north is up like a map. Colours: asphalt dark, run-off green, pit lane
blue-grey, service/paddock roads brown-grey, verge/shoulders tan, parking bays white lines; arrows: driving direction
(white), grandstand front / garage doors / board faces / floodlight aim (see legend). Red marks = a failed check.
"""
import math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import luau_table  # noqa: E402

SHOULDER = 16.0  # studs: CircuitBuilder SHOULDER_W (sloped plank from the road edge down to the verge)


def v3(flat):
    return np.array(flat, float).reshape(-1, 3)


def normals(p2, closed):
    """right-hand horizontal normals in world x/z (as CircuitBuilder.normals)."""
    n = len(p2)
    out = np.zeros((n, 2))
    for i in range(n):
        a = p2[i - 1] if i > 0 else (p2[-1] if closed else p2[i])
        b = p2[i + 1] if i < n - 1 else (p2[0] if closed else p2[i])
        t = b - a
        L = np.linalg.norm(t)
        t = t / L if L > 1e-6 else np.array([1.0, 0])
        out[i] = (-t[1], t[0])
    return out


def rect(cx, cz, w, d, yaw):
    """corners of a part of size (w, ., d) rotated CFrame.Angles(0, -rad(yaw), 0): local X -> (cos, sin) in x/z."""
    a = math.radians(yaw)
    u, v = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
    c = np.array([cx, cz])
    return [c + u * sx * w / 2 + v * sz * d / 2 for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))], u, v


def point_in_poly(p, poly):
    x, y = p
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


class Canvas:
    def __init__(self, size, lo, scale):
        self.img = Image.new('RGB', size, (235, 235, 230))
        self.dr = ImageDraw.Draw(self.img)
        self.lo, self.s = np.asarray(lo, float), scale

    def T(self, p):
        return ((p[0] - self.lo[0]) * self.s, (p[1] - self.lo[1]) * self.s)

    def poly(self, pts, fill=None, outline=None, width=1):
        self.dr.polygon([self.T(p) for p in pts], fill=fill, outline=outline, width=width)

    def line(self, pts, fill, width=1):
        self.dr.line([self.T(p) for p in pts], fill=fill, width=max(1, int(round(width))))

    def wline(self, pts, fill, studs):
        self.line(pts, fill, studs * self.s)

    def dot(self, p, r_px, fill, outline=None):
        x, y = self.T(p)
        self.dr.ellipse([x - r_px, y - r_px, x + r_px, y + r_px], fill=fill, outline=outline)

    def arrow(self, p, d, length_studs, fill, width=2, min_px=10):
        d = np.asarray(d, float)
        d = d / (np.linalg.norm(d) + 1e-9)
        L = max(length_studs, min_px / self.s)
        q = np.asarray(p) + d * L
        n = np.array([-d[1], d[0]])
        h = L * 0.35
        self.line([p, q], fill, width)
        self.line([q, q - d * h + n * h * 0.6], fill, width)
        self.line([q, q - d * h - n * h * 0.6], fill, width)

    def text(self, p, s, fill, font):
        self.dr.text(self.T(p), s, fill=fill, font=font)


def strip_quads(pts2, widths, offsets=None):
    """one quad per segment, like CircuitBuilder.strip without merging (good enough for a plan view)."""
    nrm = normals(pts2, False)
    quads = []
    for k in range(len(pts2) - 1):
        a, b = pts2[k], pts2[k + 1]
        w = max(widths[k], widths[k + 1]) / 2
        quads.append([a + nrm[k] * w, b + nrm[k + 1] * w, b - nrm[k + 1] * w, a - nrm[k] * w])
    return quads


def main(src, out):
    d = luau_table.load(src)
    c3 = v3(d['centerline'])
    c = c3[:, [0, 2]]
    n = len(c)
    nrm = normals(c, True)
    tan = np.stack([nrm[:, 1], -nrm[:, 0]], 1)
    width = np.array(d['width'], float)
    bR, bL = np.array(d['barrierRight'], float), np.array(d['barrierLeft'], float)
    pit3 = v3(d['pitLane'])
    pit = pit3[:, [0, 2]]
    issues, notes = [], []

    def nearest(p, pts=c):
        dd = np.linalg.norm(pts - np.asarray(p)[:2], axis=1)
        i = int(np.argmin(dd))
        return i, float(dd[i])

    def lateral(p, i):
        """signed lateral offset of p from centreline point i (+ = right of the driving direction)."""
        return float(np.dot(np.asarray(p) - c[i], nrm[i]))

    # ---- automatic checks (same placement rules as the builder) ------------------------------------------------------
    # grid: heading along the driving direction, behind the line
    sf = d['startFinish']['index'] - 1
    for k, s in enumerate(d['grid']):
        i, dist = nearest((s['x'], s['z']))
        dot = s['dx'] * tan[i][0] + s['dz'] * tan[i][1]
        back = (sf - i) % n
        if dot < 0.95:
            issues.append(f'grid slot {k + 1} heading off the track direction (dot {dot:.2f})')
        if back > n // 2:
            issues.append(f'grid slot {k + 1} is past the start line')
        if abs(lateral((s['x'], s['z']), i)) > width[i] / 2 - 4.5:
            issues.append(f'grid slot {k + 1} overhangs the track edge')
    # brake boards: before the corner they mark, outside of it, inside the barrier, facing the oncoming cars
    corners = d['corners']
    for b in d['brakeMarkers']:
        i = b['index'] - 1
        nxt = min(corners, key=lambda cn: (cn['from'] - 1 - i) % n)
        ahead = ((nxt['from'] - 1 - i) % n) * 5.0
        want = b['dist'] * d['studsPerMetre']
        if abs(ahead - want) > 10:
            issues.append(f"brake board {b['dist']} at index {b['index']}: {ahead:.0f} studs before the corner, wants {want:.0f}")
        outside = -1 if nxt['dir'] == 'R' else 1
        if b['side'] != outside:
            q = c[i] + nrm[i] * outside * (width[i] / 2 + 9)
            if nearest(q, pit)[1] < d['pitLaneWidth'] / 2 + 6:
                notes.append(f"brake board {b['dist']} at index {b['index']}: inside of the corner (pit lane on the outside)")
            else:
                issues.append(f"brake board {b['dist']} at index {b['index']} is on the inside of the corner")
        lat = lateral((b['x'], b['z']), i)
        bar = bR[i] if lat > 0 else bL[i]
        if bar > 0 and abs(lat) > bar:
            issues.append(f"brake board {b['dist']} at index {b['index']} stands outside the barrier")
        if abs(lat) < width[i] / 2 + 2:
            issues.append(f"brake board {b['dist']} at index {b['index']} stands on the track")
        if nearest((b['x'], b['z']), pit)[1] < d['pitLaneWidth'] / 2 + 1:
            issues.append(f"brake board {b['dist']} at index {b['index']} stands on the pit lane")
    # buildings: footprints, grandstand front, garage door side
    blds = d['buildings']
    foot = []
    for b in blds:
        poly, u, v = rect(b['x'], b['z'], b['w'], b['d'], b['yaw'])
        foot.append((b, poly, u, v))
    for b, poly, u, v in foot:
        ctr = np.array([b['x'], b['z']])
        if b['kind'] == 'grandstand':
            i, _ = nearest(ctr)
            to = c[i] - ctr
            to /= np.linalg.norm(to)
            front = u * np.sign(to @ u) if abs(to @ u) > abs(to @ v) else v * np.sign(to @ v)
            b['_front'] = front
            # what the seats look at: the first track point straight ahead of the front face
            ahead = [j for j in range(n) if (c[j] - ctr) @ front > 0 and abs((c[j] - ctr) @ (np.array([-front[1], front[0]]))) < b['w'] / 2]
            if (to @ front) < 0.5:
                issues.append(f"grandstand front points {math.degrees(math.acos(max(-1, min(1, to @ front)))):.0f} deg away from the nearest track point")
            depth_to = min((np.linalg.norm(c[j] - ctr) for j in ahead), default=1e9)
            b['_view'] = depth_to
            if depth_to > 400:
                issues.append(f'grandstand: no track within 400 studs in front of the seats ({depth_to:.0f})')
        if b['kind'] == 'pit_garage':
            j, dpit = nearest(ctr, pit)
            target = pit[j] if dpit < 150 else c[nearest(ctr)[0]]
            b['_doors'] = 1 if (target - ctr) @ v > 0 else -1
        if b['kind'] in ('pit_garage', 'grandstand', 'race_control'):
            for i in range(0, n, 2):
                if point_in_poly(c[i], poly):
                    issues.append(f"{b['kind']} footprint covers the track at index {i + 1}")
                    break
            for j in range(0, len(pit), 2):
                if point_in_poly(pit[j], poly) and b['kind'] != 'race_control':
                    issues.append(f"{b['kind']} footprint covers the pit lane")
                    break
    # floodlights: outside the barrier, not in a building, aimed at the track
    fl_bad = set()
    for k, f in enumerate(d['floodlights']):
        p = np.array([f['x'], f['z']])
        i, dist = nearest(p)
        lat = lateral(p, i)
        bar = bR[i] if lat > 0 else bL[i]
        aim = np.array([f['dx'], f['dz']])
        if bar > 0 and abs(lat) < bar:
            issues.append(f'floodlight {k + 1} is inside the barrier'); fl_bad.add(k)
        if abs(lat) < width[i] / 2 + 3:
            issues.append(f'floodlight {k + 1} stands on the track'); fl_bad.add(k)
        if (c[i] - p) @ aim < 0:
            issues.append(f'floodlight {k + 1} aims away from the track'); fl_bad.add(k)
        for b, poly, u, v in foot:
            if b['kind'] != 'paddock' and point_in_poly(p, poly):
                issues.append(f"floodlight {k + 1} stands inside a {b['kind']}"); fl_bad.add(k)
        jp, dp = nearest(p, pit)
        if dp < d['pitLaneWidth'] / 2 + 2:
            issues.append(f'floodlight {k + 1} stands on the pit lane'); fl_bad.add(k)
        for r in d['serviceRoads']:
            sp = v3(r['pts'])[:, [0, 2]]
            if np.min(np.linalg.norm(sp - p, axis=1)) < r['width'] / 2 + 1:
                issues.append(f"floodlight {k + 1} stands on service road {r['way']}"); fl_bad.add(k)
                break
        # beam emitters (CircuitBuilder BEAM_SPREAD): the middle one must hang over the track and aim at its centre
        if 'reach' in f:
            em = p + aim / np.linalg.norm(aim) * (f['reach'] - f['hw'])
            ie, de = nearest(em)
            if de > width[ie] / 2 + 6:
                issues.append(f'floodlight {k + 1}: beam emitter {de:.0f} studs from the centreline (off the track)')
            f['_beams'] = [em + np.array([-aim[1], aim[0]]) / np.linalg.norm(aim) * kk * 70 for kk in (-1, 0, 1)]
        if 'reach' in f and abs(abs(lat) - f['reach']) > 25:
            issues.append(f'floodlight {k + 1}: reach {f["reach"]} vs lateral {abs(lat):.0f}')
    ylo, yhi = c3[:, 1].min() - 40, c3[:, 1].max() + 40
    for r in d['serviceRoads']:
        ys = v3(r['pts'])[:, 1]
        if ys.min() < ylo or ys.max() > yhi:
            issues.append(f"service road {r['way']} heights {ys.min():.0f}..{ys.max():.0f} outside the venue range")
    # entrance / paddock
    e = d['entrance']
    ent = np.array([e['x'], e['z']])
    pad = d.get('paddock')
    if pad:
        pp = np.array([pad['x'], pad['z']])
        notes.append(f"paddock point {pp.round(0).tolist()} y {pad.get('y')}: {np.linalg.norm(pp - ent):.0f} studs from the gate")
        i, dist = nearest(pp)
        if dist < width[i] / 2 + 20:
            issues.append('paddock point is on/next to the track')
        jp, dp = nearest(pp, pit)
        if dp < d['pitLaneWidth'] / 2 + 5:
            issues.append('paddock point is on the pit lane')
        for b, poly, u, v in foot:
            if b['kind'] in ('pit_garage', 'grandstand') and point_in_poly(pp, poly):
                issues.append(f"paddock point is inside a {b['kind']}")
    if d.get('paddockRoad'):
        pr = v3(d['paddockRoad']['pts'])
        p2 = pr[:, [0, 2]]
        w = d['paddockRoad']['width']
        cross = 0
        for q in p2:
            i, dist = nearest(q)
            if dist < width[i] / 2:
                cross += 1
        notes.append(f'paddock road {np.sum(np.linalg.norm(np.diff(pr, axis=0), axis=1)):.0f} studs, {w} wide, '
                     f'{cross} of {len(p2)} points on the track (at-grade crossing)')
        steps = np.abs(np.diff(pr[:, 1]))
        lens = np.linalg.norm(np.diff(p2, axis=0), axis=1)
        grade = np.max(steps / np.maximum(lens, 1e-6))
        notes.append(f'paddock road max grade {grade * 100:.1f}%')
        if grade > 0.2:
            issues.append(f'paddock road too steep ({grade * 100:.0f}%)')

    # corridor roads near the venue (optional context: build/<id>/corridor_graph_game.json)
    corridor = []
    cg = os.path.join(os.path.dirname(os.path.abspath(src)), '..', '..', '..', 'build', d['id'], 'corridor_graph_game.json')
    if os.path.exists(cg):
        import json
        gj = json.load(open(cg, encoding='utf-8'))
        wx = 20000.0  # world origin x of the map-local graph
        for e2 in gj['edges']:
            pts = np.array(e2['pts'], float) + [wx, 0]
            if pts[:, 0].max() > 44300:
                corridor.append((pts, e2['width']))

    # ---- drawing -------------------------------------------------------------------------------------------------------
    g = d['ground']
    gx0, gz0, cell, nx, nz = g['x0'], g['z0'], g['cell'], g['nx'], g['nz']
    hh = np.array(g['h'], float).reshape(nz, nx)
    lo_all = np.array([min(gx0, c[:, 0].min(), v3(d['access']['pts'])[:, 0].min()) - 60, gz0 - 20])
    hi_all = np.array([gx0 + nx * cell + 20, gz0 + nz * cell + 20])
    W = 2400
    s1 = (W - 20) / (hi_all - lo_all)[0]
    H1 = int((hi_all - lo_all)[1] * s1) + 10
    # zoom: entrance, plaza, parking, pits, paddock, grid, grandstand
    zlo = np.array([44700.0, 2730.0])
    zhi = np.array([46420.0, 3400.0])
    s2 = (W - 20) / (zhi - zlo)[0]
    H2 = int((zhi - zlo)[1] * s2) + 10
    LEG = 420
    img = Image.new('RGB', (W, 40 + H1 + 40 + H2 + LEG), (250, 250, 250))
    try:
        font = ImageFont.truetype('arial.ttf', 15)
        big = ImageFont.truetype('arialbd.ttf', 22)
        small = ImageFont.truetype('arial.ttf', 12)
    except OSError:
        font = big = small = ImageFont.load_default()
    top = ImageDraw.Draw(img)
    top.text((10, 8), f"{d['name']}: top-down render of what CircuitBuilder builds (from {os.path.basename(src)}); "
                      f"north up, x east, z south; overview {1 / s1:.2f} studs/px", fill=(0, 0, 0), font=big)
    top.text((10, 40 + H1 + 8), f'Zoom: entrance, plaza, parking, paddock road, pits, grid, grandstand ({1 / s2:.2f} studs/px)',
             fill=(0, 0, 0), font=big)
    panels = [Canvas((W - 20, H1), lo_all, s1), Canvas((W - 20, H2), zlo, s2)]
    hmin, hmax = hh.min(), hh.max()

    def draw(P, zoom):
        # terrain
        for jz in range(nz):
            for jx in range(nx):
                t = (hh[jz, jx] - hmin) / max(hmax - hmin, 1)
                col = (int(150 + 60 * t), int(175 + 55 * t), int(130 + 50 * t))
                x0, z0 = gx0 + jx * cell, gz0 + jz * cell
                P.poly([(x0, z0), (x0 + cell, z0), (x0 + cell, z0 + cell), (x0, z0 + cell)], fill=col)
        # verge / shoulders, plaza ground (new)
        for vg in d.get('verge', []):
            poly, _, _ = rect(vg['x'], vg['z'], vg['w'], vg['d'], vg['yaw'])
            P.poly(poly, fill=(222, 205, 160))
            if vg.get('slope', 0) > 0:
                inner, _, _ = rect(vg['x'], vg['z'], vg['w'] - 2 * vg['slope'], vg['d'] - 2 * vg['slope'], vg['yaw'])
                P.poly(inner, fill=(232, 220, 185))
        for sh in d.get('shoulders', []):
            a, b2, o = np.array([sh['ax'], sh['az']]), np.array([sh['bx'], sh['bz']]), np.array([sh['ox'], sh['oz']])
            P.poly([a, b2, b2 + o * SHOULDER, a + o * SHOULDER], fill=(200, 180, 130))
        for e2 in corridor:
            P.wline(e2[0], (55, 56, 62), e2[1])
        # run-off: barrier to barrier
        for i in range(n):
            j = (i + 1) % n
            r1 = bR[i] if bR[i] > 0 else width[i] / 2 + d['runoffDefault']
            l1 = bL[i] if bL[i] > 0 else width[i] / 2 + d['runoffDefault']
            r2 = bR[j] if bR[j] > 0 else width[j] / 2 + d['runoffDefault']
            l2 = bL[j] if bL[j] > 0 else width[j] / 2 + d['runoffDefault']
            P.poly([c[i] + nrm[i] * r1, c[j] + nrm[j] * r2, c[j] - nrm[j] * l2, c[i] - nrm[i] * l1], fill=(110, 160, 85))
        # roads
        for r in d['serviceRoads']:
            sp = v3(r['pts'])[:, [0, 2]]
            for q in strip_quads(sp, [r['width']] * len(sp)):
                P.poly(q, fill=(120, 112, 100))
        acc = v3(d['access']['pts'])[:, [0, 2]]
        for q in strip_quads(acc, [d['access']['width']] * len(acc)):
            P.poly(q, fill=(55, 56, 62))
        if d.get('paddockRoad'):
            pr = v3(d['paddockRoad']['pts'])[:, [0, 2]]
            for q in strip_quads(pr, [d['paddockRoad']['width']] * len(pr)):
                P.poly(q, fill=(95, 88, 78))
        for p in d['parking']:
            poly, u, v = rect(p['x'], p['z'], p['w'], p['d'], p['yaw'])
            P.poly(poly, fill=(80, 81, 86))
        for pk in d.get('carPark', []):
            poly, u, v = rect(pk['x'], pk['z'], pk['w'], pk['d'], pk['yaw'])
            P.poly(poly, fill=(80, 81, 86), outline=(255, 255, 255))
            ctr = np.array([pk['x'], pk['z']])
            # bays: rows along local X, bay width bayW, depth bayD, an aisle in the middle
            for row in (-1, 1):
                zc = row * (pk['d'] / 2 - pk['bayD'] / 2)
                nb = int(pk['w'] // pk['bayW'])
                for k in range(nb + 1):
                    xk = -pk['w'] / 2 + k * pk['bayW']
                    a = ctr + u * xk + v * (zc - pk['bayD'] / 2)
                    b2 = ctr + u * xk + v * (zc + pk['bayD'] / 2)
                    P.line([a, b2], (255, 255, 255), 1)
        # pit lane
        for q in strip_quads(pit, [d['pitLaneWidth']] * len(pit)):
            P.poly(q, fill=(70, 80, 100))
        # asphalt
        for i in range(n):
            j = (i + 1) % n
            P.poly([c[i] + nrm[i] * width[i] / 2, c[j] + nrm[j] * width[j] / 2, c[j] - nrm[j] * width[j] / 2,
                    c[i] - nrm[i] * width[i] / 2], fill=(52, 53, 58))
        # curbs
        cw = d['curbWidth']
        for ck in d['curbs']:
            idx = []
            i = ck['from'] - 1
            while True:
                idx.append(i)
                if i == ck['to'] - 1 or len(idx) > n:
                    break
                i = (i + 1) % n
            for t in range(len(idx) - 1):
                a, b2 = idx[t], idx[t + 1]
                off = lambda q: c[q] + nrm[q] * ck['side'] * (width[q] / 2 + cw / 2 - 0.5)
                P.wline([off(a), off(b2)], (240, 240, 240) if t % 2 == 0 else (205, 30, 35), max(cw, 2.5 / P.s))
        # barriers
        for side, off in ((1, bR), (-1, bL)):
            run = []
            for t in range(n + 1):
                i = t % n
                if off[i] > 0:
                    run.append(c[i] + nrm[i] * side * off[i])
                else:
                    if len(run) > 1:
                        P.line(run, (150, 150, 145), 2 if not zoom else 3)
                    run = []
            if len(run) > 1:
                P.line(run, (150, 150, 145), 2 if not zoom else 3)
        # start / finish, sectors
        for i, col in [(sf, (255, 255, 255))] + [(s - 1, (255, 210, 0)) for s in d['sectors']]:
            P.line([c[i] + nrm[i] * width[i] / 2, c[i] - nrm[i] * width[i] / 2], col, 4)
        # driving direction
        for i in range(0, n, 60):
            P.arrow(c[i] - tan[i] * 12, tan[i], 24, (255, 255, 255), 2)
        # buildings
        for b, poly, u, v in foot:
            col = {'pit_garage': (225, 228, 232), 'race_control': (40, 60, 90), 'grandstand': (170, 175, 185),
                   'paddock': (160, 160, 160)}.get(b['kind'], (200, 200, 200))
            P.poly(poly, fill=col, outline=(30, 30, 30))
            ctr = np.array([b['x'], b['z']])
            if '_front' in b:
                P.arrow(ctr, b['_front'], b['d'] * 0.9, (0, 90, 220), 4)
            if '_doors' in b:
                s = b['_doors']
                a = ctr + v * s * (b['d'] / 2 + 1.5) - u * (b['w'] / 2 - 2)
                b2 = ctr + v * s * (b['d'] / 2 + 1.5) + u * (b['w'] / 2 - 2)
                P.line([a, b2], (230, 120, 0), 5 if zoom else 3)
                for k in range(1, 6):
                    m = ctr + u * (b['w'] * (k / 6 - 0.5))
                    P.arrow(m, v * s, 20, (230, 120, 0), 2)
            for wn in b.get('windows', []):
                pass
            if zoom or b['kind'] != 'paddock':
                P.text(ctr - u * b['w'] * 0.35, b['kind'], (0, 0, 0), small)
        # grid
        for k, s in enumerate(d['grid']):
            poly, _, _ = rect(s['x'], s['z'], 9, 17, math.degrees(math.atan2(s['dz'], s['dx'])) - 90 + 90)
            # slot: 9 wide across, 17 long along (dx, dz)
            f = np.array([s['dx'], s['dz']])
            r = np.array([-f[1], f[0]])
            p0 = np.array([s['x'], s['z']])
            P.poly([p0 + f * 8.5 + r * 4.5, p0 + f * 8.5 - r * 4.5, p0 - f * 8.5 - r * 4.5, p0 - f * 8.5 + r * 4.5],
                   outline=(255, 255, 255))
            if zoom:
                P.arrow(p0 - f * 6, f, 12, (0, 230, 255), 2)
        # brake boards: square + face direction (toward the oncoming cars) + link to the corner start
        for b in d['brakeMarkers']:
            i = b['index'] - 1
            p0 = np.array([b['x'], b['z']])
            P.dot(p0, 5 if not zoom else 7, (255, 255, 255), (0, 0, 0))
            P.arrow(p0, -tan[i], 25, (200, 0, 200), 2)
            nxt = min(corners, key=lambda cn: (cn['from'] - 1 - i) % n)
            if not zoom:
                P.text(p0 + nrm[i] * b['side'] * 20, str(b['dist']), (120, 0, 120), small)
        for ci, cn in enumerate(corners):
            m = (cn['from'] - 1 + ((cn['to'] - cn['from']) % n) // 2) % n
            side = 1 if cn['dir'] == 'L' else -1
            P.text(c[m] + nrm[m] * side * (width[m] / 2 + 60), f'T{ci + 1}', (200, 0, 0), font)
            P.dot(c[cn['from'] - 1], 3, (200, 0, 0))
        # floodlights (pole + aim), beam emitters if present
        for k, f in enumerate(d['floodlights']):
            p0 = np.array([f['x'], f['z']])
            bad = k in fl_bad
            P.dot(p0, 6 if not zoom else 8, (255, 40, 40) if bad else (255, 210, 0), (0, 0, 0))
            P.arrow(p0, (f['dx'], f['dz']), f.get('reach', 40) * 0.8, (255, 160, 0), 2)
            for bm in f.get('_beams', []):
                P.dot(bm, 2 if not zoom else 3, (255, 250, 200), (160, 120, 0))
        # entrance arch, signs, flags, paddock point, ring
        fwd = np.array([e['dx'], e['dz']])
        fwd /= np.linalg.norm(fwd)
        side = np.array([-fwd[1], fwd[0]])
        span = d['access']['width'] + 8
        P.line([ent + side * span / 2, ent - side * span / 2], (255, 255, 255), 6)
        P.text(ent + side * (span / 2 + 6), 'GATE', (0, 0, 0), font)
        for sg in d.get('signs', []):
            p0 = np.array([sg['x'], sg['z']])
            P.dot(p0, 6, (0, 160, 255), (0, 0, 0))
            P.arrow(p0, (sg['dx'], sg['dz']), 20, (0, 160, 255), 2)
            if zoom:
                P.text(p0 + np.array([6, 6]), sg['text'].replace('\n', ' '), (0, 70, 160), small)
        for lp in d.get('lampPosts', []):
            P.dot((lp['x'], lp['z']), 4, (255, 240, 160), (0, 0, 0))
        for fp in d.get('flagPoles', []):
            P.dot((fp['x'], fp['z']), 4, (255, 0, 120), (0, 0, 0))
        if pad:
            P.dot((pad['x'], pad['z']), 10, (0, 220, 255), (0, 0, 0))
            P.text((pad['x'] + 12, pad['z'] - 12), 'PADDOCK (ring)', (0, 120, 160), font)
        P.dot(ent, 7, None, (0, 220, 255))

    for k, P in enumerate(panels):
        draw(P, k == 1)
    zl = panels[0].T(zlo), panels[0].T(zhi)
    panels[0].dr.rectangle([zl[0][0], zl[0][1], zl[1][0], zl[1][1]], outline=(0, 0, 0), width=2)
    img.paste(panels[0].img, (10, 40))
    img.paste(panels[1].img, (10, 40 + H1 + 40))
    dr = ImageDraw.Draw(img)
    y0 = 40 + H1 + 40 + H2
    legend = [
        'Legend: white arrows = driving direction; white/yellow bars = start-finish / sector lines; red/white = curbs; '
        'grey lines = barriers; T1.. = corners (red dot = corner start)',
        'blue arrow = grandstand front (seats face this way); orange line + arrows = pit garage doors; white rectangles = '
        'grid slots (cyan arrow = car heading)',
        'white dot + magenta arrow = brake board (arrow = the way the board face looks, toward oncoming cars); yellow dot + '
        'orange arrow = floodlight pole and aim, small pale dots = its 3 invisible beam emitters over the track edge (red = failed check)',
        'tan = verge slab (top 1 stud under the road) and sloped shoulders on every road/plaza edge; dark grey west of the '
        'transition road = corridor roads; blue dots + arrows = signs (arrow = face direction); pink = flag poles; '
        'pale yellow = lamp posts; cyan = paddock point (circuit menu ring)',
    ]
    for k, s in enumerate(legend):
        dr.text((10, y0 + 8 + k * 20), s, fill=(0, 0, 0), font=font)
    dr.text((10, y0 + 100), f'Checks: {len(issues)} problem(s)', fill=(200, 0, 0) if issues else (0, 130, 0), font=big)
    for k, s in enumerate((issues or ['none']) [:10] + notes[:5]):
        dr.text((10, y0 + 130 + k * 18), ('- ' if k < len(issues) else '  ') + s, fill=(200, 0, 0) if k < len(issues) else (0, 0, 0), font=font)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print(f'wrote {out} ({img.size[0]}x{img.size[1]})')
    for s in notes:
        print('note:', s)
    print(f'{len(issues)} problem(s)')
    for s in issues:
        print('  -', s)
    return issues


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join('build', 'bira', 'venue_render.png'))
