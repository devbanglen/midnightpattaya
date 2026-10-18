"""Bira Circuit venue - OSM raceway + DEM -> data-driven circuit definition (Luau) for CircuitBuilder.

  .venv\\Scripts\\python tools\\circuit\\access_corridor.py tools\\circuit\\config\\bira.json   (first)
  .venv\\Scripts\\python tools\\circuit\\bira_circuit.py    tools\\circuit\\config\\bira.json

Scale: the circuit is NOT compressed (0.28 m/stud, 1 m = 3.571 studs). Only its anchor - the facility junction on
CBI.2081, the last node of the corridor graph - sits at its city-compressed position; from
there a straight transition road (the slack left by un-compressing the venue) leads to the gate, and the facility
hangs off the gate at 1:1 in its real orientation.
Elevation: Terrarium DEM tiles (AWS open data), smoothed along the track; the track by the gate is at the city road
top (y = 1).

Writes build/bira/bira.luau (copy committed as roblox/data/circuits/bira.luau), build/bira/circuit.json (same data)
and build/bira/bira_check.png (corridor overview, facility plan, elevation profile).
Everything marked verified=false is a gameplay addition, not survey data.
"""
import json, math, os, shutil, sys
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# --- small geometry helpers (closed loops are arrays without the repeated first point) -----------------------------
def chaikin_closed(p, iterations):
    p = np.asarray(p, float)
    for _ in range(iterations):
        q = np.roll(p, -1, axis=0)
        p = np.stack([0.75 * p + 0.25 * q, 0.25 * p + 0.75 * q], axis=1).reshape(-1, 2)
    return p


def resample_closed(p, step):
    q = np.vstack([p, p[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])
    n = max(int(round(s[-1] / step)), 8)
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(t, s, q[:, 0]), np.interp(t, s, q[:, 1])], axis=1), s[-1]


def chaikin_open(p, iterations):
    p = np.asarray(p, float)
    for _ in range(iterations):
        q = np.empty((2 * (len(p) - 1), 2))
        q[0::2] = 0.75 * p[:-1] + 0.25 * p[1:]
        q[1::2] = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.vstack([p[:1], q[1:-1], p[-1:]])
    return p


def resample_open(p, step):
    p = np.asarray(p, float)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    n = max(int(round(s[-1] / step)), 1)
    t = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(t, s, p[:, k]) for k in range(p.shape[1])], axis=1)


def circ_smooth(v, win):
    """moving average over a closed loop (win samples)."""
    win = max(int(win) | 1, 1)
    k = np.ones(win) / win
    h = win // 2
    return np.convolve(np.concatenate([v[-h:], v, v[:h]]), k, mode='valid') if h else v.copy()


def tangents(p):
    t = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    return t / np.linalg.norm(t, axis=1)[:, None]


def obb(poly):
    """oriented box of a footprint: centre, w (long side), d, angle of the long side (radians, x east / y north)."""
    r = Polygon(poly).minimum_rotated_rectangle
    c = np.array(r.exterior.coords)[:4]
    e1, e2 = c[1] - c[0], c[2] - c[1]
    if np.linalg.norm(e2) > np.linalg.norm(e1):
        e1, e2 = e2, e1
    return c.mean(0), float(np.linalg.norm(e1)), float(np.linalg.norm(e2)), math.atan2(e1[1], e1[0])


class Dem:
    """Terrarium PNG tiles: height = R*256 + G + B/256 - 32768 (metres), bilinear sampling."""
    def __init__(self, folder, z):
        self.folder, self.z, self.cache = folder, z, {}

    def px(self, lat, lon):
        n = 2 ** self.z
        return (lon + 180) / 360 * n * 256, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256

    def raw(self, X, Y):
        tx, ty = X // 256, Y // 256
        if (tx, ty) not in self.cache:
            f = os.path.join(self.folder, f'{self.z}_{tx}_{ty}.png')
            if not os.path.exists(f):
                raise FileNotFoundError(f)
            a = np.asarray(Image.open(f).convert('RGB'), float)
            self.cache[(tx, ty)] = a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256 - 32768
        return self.cache[(tx, ty)][Y % 256, X % 256]

    def __call__(self, lat, lon):
        x, y = self.px(lat, lon)
        x0, y0 = int(math.floor(x - 0.5)), int(math.floor(y - 0.5))
        fx, fy = x - 0.5 - x0, y - 0.5 - y0
        return ((1 - fx) * (1 - fy) * self.raw(x0, y0) + fx * (1 - fy) * self.raw(x0 + 1, y0)
                + (1 - fx) * fy * self.raw(x0, y0 + 1) + fx * fy * self.raw(x0 + 1, y0 + 1))


def lua_num_list(vals, per_line=16, fmt='{:.1f}'):
    s = [fmt.format(v).rstrip('0').rstrip('.') if '.' in fmt.format(v) else fmt.format(v) for v in vals]
    s = [x if x not in ('-0', '') else '0' for x in s]
    return '\n'.join('    ' + ', '.join(s[i:i + per_line]) + ',' for i in range(0, len(s), per_line))


def lua_str(s):
    out = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return '"' + ''.join(c if ord(c) >= 32 else f'\\{ord(c)}' for c in out) + '"'


def lua_val(v, ind='  '):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        r = f'{float(v):.2f}'.rstrip('0').rstrip('.')
        return '0' if r in ('-0', '') else r
    if isinstance(v, str):
        return lua_str(v)
    if isinstance(v, dict):
        return '{ ' + ', '.join(f'{k} = {lua_val(x, ind)}' for k, x in v.items()) + ' }'
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool) for x in v):
            return '{\n' + lua_num_list(v) + '\n' + ind + '}' if len(v) > 12 else '{ ' + ', '.join(lua_val(x) for x in v) + ' }'
        return '{\n' + '\n'.join(f'{ind}  {lua_val(x, ind + "  ")},' for x in v) + f'\n{ind}}}'
    raise TypeError(type(v))


def main(cfg_path):
    sys.stdout.reconfigure(encoding='utf-8')
    cfg = json.load(open(cfg_path, encoding='utf-8'))
    out_dir = os.path.join(ROOT, 'build', cfg['name'])
    corr = json.load(open(os.path.join(out_dir, 'corridor_graph_game.json'), encoding='utf-8'))
    ox, oy = corr['origin_utm']
    kc = corr['compression'] / corr['meters_per_stud']            # city: studs per real metre (1.786)
    ks = cfg['circuit_compression'] / corr['meters_per_stud']      # circuit: studs per real metre (3.571)
    WX, _, WZ = cfg['world_origin']
    TOP = cfg['city_road_top']
    tf = Transformer.from_crs('EPSG:4326', cfg['crs'], always_xy=True)
    inv = Transformer.from_crs(cfg['crs'], 'EPSG:4326', always_xy=True)
    raw = json.load(open(os.path.join(ROOT, cfg['circuit_raw']), encoding='utf-8'))
    W = {e['id']: e for e in raw['elements'] if e['type'] == 'way' and 'geometry' in e}
    N = {e['id']: e for e in raw['elements'] if e['type'] == 'node'}
    npos = {}
    for w in W.values():
        for n, g in zip(w['nodes'], w['geometry']):
            npos[n] = np.array(tf.transform(g['lon'], g['lat']))
    for n in N.values():
        npos[n['id']] = np.array(tf.transform(n['lon'], n['lat']))
    utm = lambda w: np.array([tf.transform(g['lon'], g['lat']) for g in W[w]['geometry']])
    dem = Dem(os.path.join(ROOT, cfg['dem_tiles']), cfg['dem_zoom'])
    def h_at(p):                                                   # DEM metres at a UTM point
        lon, lat = inv.transform(p[0], p[1])
        return dem(lat, lon)

    # --- 1. raceway loop from OSM ----------------------------------------------------------------------------------
    ids = cfg['raceway_ways']
    chain = list(W[ids[0]]['nodes'])
    rest = [list(W[i]['nodes']) for i in ids[1:]]
    while rest:
        for r in rest:
            if r[0] == chain[-1]:
                chain += r[1:]; rest.remove(r); break
            if r[-1] == chain[-1]:
                chain += r[::-1][1:]; rest.remove(r); break
        else:
            sys.exit('raceway ways do not chain into a loop')
    if chain[0] != chain[-1]:
        sys.exit('raceway is not closed')
    raw_loop = np.array([npos[n] for n in chain[:-1]])
    area = 0.5 * np.sum(raw_loop[:, 0] * np.roll(raw_loop[:, 1], -1) - np.roll(raw_loop[:, 0], -1) * raw_loop[:, 1])
    if (area < 0) != (cfg['direction'] == 'clockwise'):
        raw_loop = raw_loop[::-1]; chain = chain[::-1]
    raw_len = float(np.linalg.norm(np.diff(np.vstack([raw_loop, raw_loop[:1]]), axis=0), axis=1).sum())

    step_m = cfg['resample_studs'] / ks
    loop, smooth_len = resample_closed(chaikin_closed(raw_loop, cfg['chaikin_iterations']), step_m)
    n = len(loop)
    tan = tangents(loop)
    right = np.stack([tan[:, 1], -tan[:, 0]], axis=1)              # right-hand side in x east / y north

    # --- 2. start/finish: track point beside the middle of the longest pit building (exact line position unverified)
    pits = [(w, obb(utm(w))) for w in cfg['pit_building_ways'] if w in W]
    main_pit = max(pits, key=lambda x: x[1][1])
    sf = int(np.argmin(np.linalg.norm(loop - main_pit[1][0], axis=1)))
    loop = np.roll(loop, -sf, axis=0); tan = np.roll(tan, -sf, axis=0); right = np.roll(right, -sf, axis=0)
    s = np.arange(n) * (smooth_len / n)                             # metres from the line, driving direction
    track_ls = LineString(np.vstack([loop, loop[:1]]))

    # --- 3. corners (curvature) -------------------------------------------------------------------------------------
    head = np.unwrap(np.arctan2(tan[:, 1], tan[:, 0]))
    dpsi = np.diff(np.concatenate([head, [head[0] + (head[-1] - head[0]) + (head[1] - head[0])]]))
    dpsi = (dpsi + np.pi) % (2 * np.pi) - np.pi
    curv = circ_smooth(dpsi / step_m, int(12 / step_m))            # 1/m, + = left
    on = np.abs(curv) > 1 / cfg['corner_max_radius_m']
    regions = []
    start = int(np.argmin(on)) if on.any() and not on.all() else 0   # begin scanning on a straight
    idx = [(start + j) % n for j in range(n)]
    cur = None
    for j in idx:
        sg = 0 if not on[j] else int(np.sign(curv[j]))
        if sg and cur and cur['sign'] == sg:
            cur['to'] = j
        elif sg:
            cur = {'from': j, 'to': j, 'sign': sg}; regions.append(cur)
        else:
            cur = None
    merged = []
    for r in regions:                                             # merge same-direction pieces split by a short gap
        if merged and merged[-1]['sign'] == r['sign'] and ((r['from'] - merged[-1]['to']) % n) * step_m < cfg['corner_merge_gap_m']:
            merged[-1]['to'] = r['to']
        else:
            merged.append(dict(r))
    corners = []
    for r in merged:
        span = [(r['from'] + j) % n for j in range(((r['to'] - r['from']) % n) + 1)]
        turn = math.degrees(float(np.sum(dpsi[span])))
        if abs(turn) >= cfg['corner_min_turn_deg']:
            rmin = 1 / max(float(np.max(np.abs(curv[span]))), 1e-6)
            corners.append({'from': span[0], 'to': span[-1], 'turn': round(turn, 1), 'dir': 'L' if turn > 0 else 'R',
                            'radius_m': round(rmin, 1), 's_m': round(float(s[span[0]]), 1)})
    corners.sort(key=lambda c: c['from'])
    total_turn = math.degrees(float(np.sum(dpsi)))

    # --- 4. elevation along the track -------------------------------------------------------------------------------
    h_raw = np.array([h_at(p) for p in loop])
    h_trk = circ_smooth(h_raw, int(cfg['elevation_smooth_m'] / step_m))
    grade = np.diff(np.concatenate([h_trk, h_trk[:1]])) / step_m

    # --- 5. pit lane (OSM service ways), width profile ---------------------------------------------------------------
    pchain = []
    for w in cfg['pit_lane_ways']:
        p = [npos[x] for x in W[w]['nodes']]
        pchain += p if not pchain else p[1:]
    pit_raw = np.array(pchain)
    if np.linalg.norm(pit_raw[0] - loop[0]) > 0:                  # orient: entry first (before the line in driving order)
        e0 = int(np.argmin(np.linalg.norm(loop - pit_raw[0], axis=1)))
        e1 = int(np.argmin(np.linalg.norm(loop - pit_raw[-1], axis=1)))
        if s[e0] < s[e1] and s[e0] < smooth_len / 2:               # pit start lies just after the line -> it is the exit
            pit_raw = pit_raw[::-1]
    pit_entry = int(np.argmin(np.linalg.norm(loop - pit_raw[0], axis=1)))
    pit_exit = int(np.argmin(np.linalg.norm(loop - pit_raw[-1], axis=1)))
    hw_m = np.full(n, cfg['track_width_m'] / 2)
    pit_span = [(pit_entry + j) % n for j in range(((pit_exit - pit_entry) % n) + 1)]
    for j in pit_span:
        hw_m[j] = cfg['pit_straight_width_m'] / 2
    hw_m = circ_smooth(hw_m, int(30 / step_m))
    pit_pts = resample_open(chaikin_open(pit_raw, 3), 6 / ks)
    # trim the ends lying on the track surface (they would double the asphalt); keep a little overlap
    d_tr = np.array([track_ls.distance(Point(p)) for p in pit_pts])
    keep = np.where(d_tr > cfg['track_width_m'] / 2 * 0.6)[0]
    pit_pts = pit_pts[keep[0]:keep[-1] + 1]
    pit_side = int(np.sign(np.dot(pit_pts[len(pit_pts) // 2] - loop[int(np.argmin(np.linalg.norm(loop - pit_pts[len(pit_pts) // 2], axis=1)))],
                                  right[int(np.argmin(np.linalg.norm(loop - pit_pts[len(pit_pts) // 2], axis=1)))])))

    # --- 6. clearances -> barrier offsets (never closer than half way to the neighbouring track or the pit lane) -------
    def side_clear(obst, obst_hw):
        """per track point and side: free distance to obstacle points (minus their half width) along the normal."""
        clear = np.full((n, 2), 1e9)
        for i in range(n):
            d = obst['p'] - loop[i]
            a = d @ right[i]; b = d @ tan[i]
            m = (np.abs(b) < obst_hw + 2.0) & obst['far'](i)
            if m.any():
                for k, sg in enumerate((1, -1)):
                    mm = m & (a * sg > 0)
                    if mm.any():
                        clear[i, k] = float(np.min(a[mm] * sg - obst_hw[mm]))
        return clear
    arc_far = lambda i: np.minimum(np.abs(s - s[i]), smooth_len - np.abs(s - s[i])) > 120
    clear_trk = side_clear({'p': loop, 'far': arc_far}, hw_m)
    pit_hw = np.full(len(pit_pts), cfg['pit_lane_width_m'] / 2)
    clear_pit = side_clear({'p': pit_pts, 'far': lambda i: np.ones(len(pit_pts), bool)}, pit_hw)
    outside = np.zeros((n, 2), bool)                              # outside of a corner gets the wider run-off
    for c in corners:
        k = 0 if c['dir'] == 'L' else 1                           # right side (k=0) is the outside of a left turn
        for j in range((c['to'] - c['from']) % n + 1 + int(25 / step_m)):
            outside[(c['from'] + j) % n, k] = True
    barrier = np.zeros((n, 2))
    for k in range(2):
        want = hw_m + np.where(outside[:, k], cfg['runoff_outside_corner_m'], cfg['runoff_m'])
        want = circ_smooth(want, int(40 / step_m))
        avail = clear_trk[:, k] / 2 - 0.5                         # half way to the neighbouring part of the track
        avail = np.minimum(avail, hw_m + (clear_pit[:, k] - hw_m) / 2)   # pit wall half way to the pit lane
        b = np.minimum(want, avail)
        b = np.minimum(circ_smooth(b, int(20 / step_m)), b)       # smooth, but never past the available room
        gap = clear_pit[:, k] < hw_m + cfg['barrier_min_clear_m'] + cfg['pit_lane_width_m'] / 2  # pit entry/exit opening
        b = np.where(gap, 0.0, np.maximum(b, hw_m + 1.0))
        barrier[:, k] = b

    # --- 7. placement -------------------------------------------------------------------------------------------
    # The corridor graph ends at the facility junction J (city-compressed position). The real road from J to the gate
    # is only a few metres, but the facility is 1:1 while everything around it is x0.5, so the facility footprint
    # would cover the compressed corridor west of J. A straight transition road from J, in the real access direction,
    # absorbs that: it is the slack created by un-compressing the venue. Its length is the shortest (>= the config
    # minimum) that keeps the facility, plaza and transition clear of every corridor road.
    J = cfg['facility_junction_node']
    jw = np.array([WX + (npos[J][0] - ox) * kc, WZ - (npos[J][1] - oy) * kc])
    cj = np.array(corr['nodes'][str(J)]) + [WX, WZ]
    assert np.linalg.norm(jw - cj) < 0.05, 'facility junction does not match the corridor graph node'
    acc_way = next(w for w in W.values() if J in w['nodes'] and w['tags'].get('highway') == 'service')
    acc = np.array([npos[x] for x in acc_way['nodes']])
    if acc_way['nodes'][0] != J:
        acc = acc[::-1]
    acc_ls = LineString(acc)
    gate_pt = np.array(acc_ls.interpolate(acc_ls.project(Point(npos[cfg['gate_node']]))).coords[0])
    acc_len = float(acc_ls.project(Point(gate_pt)))               # real J -> gate distance along the road
    adir = acc[-1] - acc[0]; adir = adir / np.linalg.norm(adir)  # real access direction (J -> track corner)
    dw = np.array([adir[0], -adir[1]])                            # same direction in world x/z
    stadium = Polygon(utm(cfg['stadium_way']))
    PL_W, PL_D = cfg['plaza_m'][0] * ks, cfg['plaza_m'][1] * ks
    corr_zone = [LineString(np.array(e['pts']) + [WX, WZ]).buffer(e['width'] / 2 + cfg['corridor_clear_studs']) for e in corr['edges']]
    st = np.array(stadium.exterior.coords)
    nrm = np.array([-dw[1], dw[0]])
    for tlen in np.arange(max(cfg['transition_min_studs'], PL_D + 40), 4000, 10.0):
        gw = jw + dw * tlen
        fac = Polygon(np.stack([gw[0] + (st[:, 0] - gate_pt[0]) * ks, gw[1] - (st[:, 1] - gate_pt[1]) * ks], axis=1))
        plaza_c = gw - dw * (PL_D / 2 + 10)
        plaza = Polygon([plaza_c + dw * a * PL_D / 2 + nrm * b * PL_W / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        tr = LineString([jw + dw * (cfg['corridor_clear_studs'] + 30), gw - dw * 5]).buffer(13)
        if not any(z.intersects(fac) or z.intersects(plaza) or z.intersects(tr) for z in corr_zone) \
                and not fac.intersects(LineString([jw, gw - dw * 5])):
            break
    else:
        sys.exit('no clear placement for the facility')
    acc_w = np.array([jw + dw * t for t in np.linspace(0, tlen, max(int(tlen / 6), 1) + 1)])
    vs = cfg['vertical_scale']
    i_g = int(np.argmin(np.linalg.norm(loop - gate_pt, axis=1)))
    h_ref = float(h_trk[i_g])                                     # track height nearest the gate = city road top
    h_gate_dem = float(h_at(gate_pt))

    def W2(p):                                                     # facility UTM point -> world x, z (1:1 about the gate)
        p = np.asarray(p)
        return np.stack([gw[0] + (p[..., 0] - gate_pt[0]) * ks, gw[1] - (p[..., 1] - gate_pt[1]) * ks], axis=-1)
    def Y(hm):                                                     # DEM metres -> world surface y
        return TOP + (np.asarray(hm) - h_ref) * ks * vs
    y_trk = Y(h_trk)
    y_acc = np.full(len(acc_w), TOP)                              # transition stays at the city road height

    cl_w = W2(loop)
    near_y = lambda p: float(y_trk[int(np.argmin(np.linalg.norm(loop - p, axis=1)))])
    pit_y_src = np.array([near_y(p) for p in pit_pts])
    def site_y(p):                                                 # pit-side buildings sit at pit-lane level
        dp = np.linalg.norm(pit_pts - p, axis=1)
        return float(pit_y_src[int(np.argmin(dp))]) if dp.min() < 80 else near_y(p)

    # --- 8. venue elements ----------------------------------------------------------------------------------------
    hw_s = hw_m * ks
    def at(i, side, off):                                          # world point beside track index i (0-based)
        p = loop[i] + right[i] * side * off
        return W2(p)
    # sectors (gameplay split at thirds of the lap)
    sectors = [int(round(n / 3)), int(round(2 * n / 3))]
    # grid: 2-wide staggered, first slot on the inside of the first corner
    first = next((c for c in corners if c['from'] > 0), corners[0])
    pole = 1 if first['dir'] == 'R' else -1
    grid = []
    for k in range(cfg['grid_slots']):
        back = cfg['grid_first_m'] + k * cfg['grid_row_m']
        i = int(round(-back / step_m)) % n
        side = pole if k % 2 == 0 else -pole
        p = W2(loop[i] + right[i] * side * hw_m[i] * 0.45)
        grid.append({'x': round(float(p[0]), 2), 'y': round(float(y_trk[i]), 2), 'z': round(float(p[1]), 2),
                     'dx': round(float(tan[i][0]), 4), 'dz': round(float(-tan[i][1]), 4)})
    # curbs: inside through the corner, outside on the exit
    curbs = []
    for c in corners:
        ins = 1 if c['dir'] == 'R' else -1
        L = (c['to'] - c['from']) % n
        curbs.append({'from': c['from'] + 1, 'to': (c['from'] + L) % n + 1, 'side': ins})
        ex0 = (c['from'] + int(L * 0.6)) % n
        curbs.append({'from': ex0 + 1, 'to': (c['to'] + int(15 / step_m)) % n + 1, 'side': -ins})
    # brake boards (100 m and 50 m) before corners that follow a straight
    brake = []
    for ci, c in enumerate(corners):
        prev = corners[ci - 1]
        straight = ((c['from'] - prev['to']) % n) * step_m
        if straight < cfg['brake_board_min_straight_m']:
            continue
        outside_side = -1 if c['dir'] == 'R' else 1               # outside of the coming corner
        for dist in (100, 50):
            side = outside_side
            i = (c['from'] - int(round(dist / step_m))) % n
            k = 0 if side == 1 else 1
            off = (barrier[i, k] if barrier[i, k] > 0 else hw_m[i] + cfg['runoff_m']) - 1.5
            on_pit = lambda sd, o: np.min(np.linalg.norm(pit_pts - (loop[i] + right[i] * sd * o), axis=1)) < cfg['pit_lane_width_m'] / 2 + 1.5
            if on_pit(side, off):                                  # pit exit/entry beside the outside: stand by the asphalt
                off = hw_m[i] + 2.5
                if on_pit(side, off):
                    side, off = -side, (barrier[i, 1 - k] if barrier[i, 1 - k] > 0 else hw_m[i] + cfg['runoff_m']) - 1.5
            p = at(i, side, off)
            brake.append({'index': i + 1, 'dist': dist, 'side': side, 'x': round(float(p[0]), 2),
                          'y': round(float(y_trk[i]), 2), 'z': round(float(p[1]), 2)})
    # buildings
    buildings = []
    def add_bld(kind, poly_or_box, verified, src, y=None):
        if isinstance(poly_or_box, tuple):
            c, w, d, ang = poly_or_box
        else:
            c, w, d, ang = obb(poly_or_box)
        p = W2(c)
        buildings.append({'kind': kind, 'x': round(float(p[0]), 2), 'z': round(float(p[1]), 2), 'w': round(w * ks, 2),
                          'd': round(d * ks, 2), 'h': round(cfg['building_heights_m'][kind] * ks, 2),
                          'yaw': round(math.degrees(-ang), 2), 'y': round(site_y(c) if y is None else y, 2),
                          'verified': verified, 'source': src})
    for w, box in pits:
        add_bld('pit_garage', box, True, f'OSM way {w} "{W[w]["tags"].get("name", "")}" footprint; height assumed')
    for w in cfg['grandstand_ways']:
        if w in W:
            add_bld('grandstand', utm(w), True, f'OSM way {w} "{W[w]["tags"].get("name", "")}" footprint; height assumed')
    c, w, d, ang = main_pit[1]
    u = np.array([math.cos(ang), math.sin(ang)])
    ctr = c + u * (np.dot(loop[0] - c, u))                         # on the main pit building, level with the line
    rc_y = site_y(ctr) + cfg['building_heights_m']['pit_garage'] * ks
    add_bld('race_control', (ctr, 24.0, min(d, 14.0), ang), False, 'gameplay: tower on the pit building at the line', y=rc_y)
    # paddock slab behind the pit garages, shrunk until it is clear of the track and run-off
    away = np.array([-math.sin(ang), math.cos(ang)])
    if np.dot(away, c - loop[0]) < 0:
        away = -away
    # behind the pit building row that lies furthest from the track on the pit side; clear of track, pits, buildings
    box = lambda c2, w2, d2, a2: Polygon([c2 + np.array([math.cos(a2), math.sin(a2)]) * a * w2 / 2
                                          + np.array([-math.sin(a2), math.cos(a2)]) * b * d2 / 2
                                          for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    blocked = track_ls.buffer(cfg['track_width_m'] / 2 + cfg['runoff_m'] + 5).union(
        LineString(pit_pts).buffer(cfg['pit_lane_width_m'] / 2 + 3))
    for _, (c2, w2, d2, a2) in pits:
        blocked = blocked.union(box(c2, w2, d2, a2).buffer(2))
    row = [b for b in pits if np.dot(away, b[1][0] - loop[0]) > 0 and track_ls.distance(Point(b[1][0])) < 120]
    c, w, d, ang = max(row, key=lambda b: track_ls.distance(Point(b[1][0])))[1] if row else main_pit[1]
    for depth in (45, 35, 25, 15):
        pc = c + away * (d / 2 + 4 + depth / 2)
        if not box(pc, w, depth, ang).intersects(blocked):
            add_bld('paddock', (pc, w, depth, ang), False, 'gameplay: paddock apron behind the pit garages')
            break
    else:
        print('paddock: no clear spot behind the pit garages, skipped')
    # parking: OSM parking areas/nodes inside (or within 100 m of) the venue outline; others in the bbox belong to
    # the neighbouring golf club and are ignored. A node only gives the position: size assumed, shrunk to stay clear.
    parking = []
    near_venue = stadium.buffer(100)
    for w in cfg['parking_ways']:
        if w in W and Polygon(utm(w)).intersects(near_venue):
            c2, pw, pd, pa = obb(utm(w)); p = W2(c2)
            parking.append({'x': round(float(p[0]), 2), 'z': round(float(p[1]), 2), 'w': round(pw * ks, 2), 'd': round(pd * ks, 2),
                            'yaw': round(math.degrees(-pa), 2), 'y': round(site_y(c2), 2), 'verified': True,
                            'source': f'OSM way {w} amenity=parking'})
        elif w in W:
            print(f'parking way {w} is {Polygon(utm(w)).distance(stadium):.0f} m outside the venue, skipped')
    for nid in cfg['parking_nodes']:
        if nid not in npos or not near_venue.contains(Point(npos[nid])):
            continue
        q = npos[nid]
        i = int(np.argmin(np.linalg.norm(loop - q, axis=1)))
        pa = math.atan2(tan[i][1], tan[i][0])
        for sz in (1.0, 0.7, 0.5):
            if not box(q, 30 * sz, 18 * sz, pa).intersects(blocked):
                p = W2(q)
                parking.append({'x': round(float(p[0]), 2), 'z': round(float(p[1]), 2), 'w': round(30 * sz * ks, 2),
                                'd': round(18 * sz * ks, 2), 'yaw': round(math.degrees(-pa), 2), 'y': round(site_y(q), 2),
                                'verified': False, 'source': f'OSM node {nid} amenity=parking (position real, size assumed)'})
                break
        else:
            print(f'parking node {nid}: no clear spot, skipped')
    # entrance plaza / visitor parking outside the gate (gameplay; the real visitor parking layout is not mapped)
    parking.append({'x': round(float(plaza_c[0]), 2), 'z': round(float(plaza_c[1]), 2), 'w': round(PL_D, 2), 'd': round(PL_W, 2),
                    'yaw': round(math.degrees(math.atan2(dw[1], dw[0])), 2), 'y': round(TOP, 2), 'verified': False,
                    'source': 'gameplay: entrance plaza / visitor parking on the transition road before the gate'})
    entrance = {'x': round(float(gw[0]), 2), 'z': round(float(gw[1]), 2), 'y': TOP, 'dx': round(float(adir[0]), 4),
                'dz': round(float(-adir[1]), 4), 'osmNode': cfg['gate_node']}
    # service roads inside the stadium outline (OSM), clipped off the track surface and run-off
    skip = set(cfg['pit_lane_ways']) | {acc_way['id']}
    serv = []
    clip_zone = track_ls.buffer(cfg['track_width_m'] / 2 + cfg['runoff_m'])
    for w in W.values():
        t = w['tags']
        if t.get('highway') != 'service' or w['id'] in skip or t.get('tunnel') == 'yes':
            continue
        ls = LineString(utm(w['id']))
        if not ls.intersects(stadium):
            continue
        g = ls.intersection(stadium).difference(clip_zone)
        for part in getattr(g, 'geoms', [g]):
            if part.geom_type == 'LineString' and part.length > 15:
                q = resample_open(np.array(part.coords), 6 / ks)
                # heights: the DEM ground (terrain is filled to it away from the track), blended to the run-off top
                # where the road was clipped at the track zone, and to the plaza level near the gate; then smoothed
                yd = np.array([float(Y(h_at(qq))) for qq in q]) + 0.2
                yt = np.array([near_y(qq) - 0.64 for qq in q])
                dtr = np.array([track_ls.distance(Point(qq)) for qq in q])
                wt = np.clip((dtr - (cfg['track_width_m'] / 2 + cfg['runoff_m'])) / 25, 0, 1)
                ys = yt * (1 - wt) + yd * wt
                wg = np.clip((np.linalg.norm(q - gate_pt, axis=1) - 10) / 25, 0, 1)
                ys = TOP * (1 - wg) + ys * wg
                if len(ys) >= 5:
                    ys = np.concatenate([ys[:2], np.convolve(ys, np.ones(5) / 5, mode='valid'), ys[-2:]])
                xz = W2(q)
                # x, y, z order like every other flat point list (it was x, z, y before: roads were built in the sky)
                serv.append({'way': w['id'], 'width': round(6.0 * ks, 2),
                             'pts': [round(float(v), 2) for k in range(len(q)) for v in (xz[k][0], ys[k], xz[k][1])]})
    # floodlights behind the barrier, on the side with more room
    flood = []
    every = int(round(cfg['floodlight_spacing_m'] / step_m))
    for i in range(0, n - every // 2, every):                     # no second pole right before the first one
        best = None
        for k, side in enumerate((1, -1)):
            if barrier[i, k] <= 0 or (pit_side == side and clear_pit[i, k] < 1e8):
                continue
            off = barrier[i, k] + 2.0
            room = clear_trk[i, k] - off - 8
            if room > 0 and (best is None or room > best[0]):
                best = (room, side, off)
        if best:
            p = at(i, best[1], best[2])
            flood.append({'x': round(float(p[0]), 2), 'y': round(float(y_trk[i]), 2), 'z': round(float(p[1]), 2),
                          'dx': round(float(-right[i][0] * best[1]), 4), 'dz': round(float(right[i][1] * best[1]), 4),
                          'reach': round(best[2] * ks, 1), 'hw': round(float(hw_m[i] * ks), 1)})
    # --- 8b. arrival area (gameplay): visitor paddock, car park, signs, flags, lamps, verge ground ------------------
    # The pit garages and their apron sit in the infield: every road to them crosses the live track (OSM: an at-grade
    # crossing at the west hairpin, or tunnel 132455224). So the paddock the players use (circuit menu ring) is put
    # OUTSIDE the track, beside the plaza, on a short service road; the infield apron stays as scenery.
    reach_w = np.maximum(barrier.max(axis=1), hw_m + cfg['runoff_m']) * ks   # studs from the centreline to the barrier
    def track_clear(pts):                                          # min clearance (studs) of world points to the barrier zone
        return min(float(np.min(np.linalg.norm(cl_w - np.asarray(p), axis=1) - reach_w)) for p in pts)
    def wrect(cx, cz, w, d, yaw_rad):                              # world rectangle polygon, local X along yaw
        u2 = np.array([math.cos(yaw_rad), math.sin(yaw_rad)]); v2 = np.array([-math.sin(yaw_rad), math.cos(yaw_rad)])
        c2 = np.array([cx, cz])
        return Polygon([c2 + u2 * a * w / 2 + v2 * b * d / 2 for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    def samples(poly):
        b = poly.bounds
        pts = list(poly.exterior.coords)
        for xx in np.linspace(b[0], b[2], 8):
            for zz in np.linspace(b[1], b[3], 8):
                if poly.contains(Point(xx, zz)):
                    pts.append((xx, zz))
        return pts
    def free(poly, others, clear=15):
        return (track_clear(samples(poly)) > clear and not any(z.intersects(poly) for z in corr_zone)
                and not any(o.buffer(4).intersects(poly) for o in others))
    yaw_p = math.atan2(dw[1], dw[0])
    yaw_deg = round(math.degrees(yaw_p), 2)
    plaza_poly = wrect(plaza_c[0], plaza_c[1], PL_D, PL_W, yaw_p)
    road_poly = LineString([jw, gw]).buffer(13 + 4)
    PD_W, PD_D, PD_GAP, PD_ROAD = 130.0, 80.0, 40.0, 20.0         # paddock along / across, road gap, road width (studs)
    paddock = None
    for side in (-1, 1):                                          # -nrm = left of the arrival direction
        for shift in (40, 20, 0, -20, -40, 60):
            pc = plaza_c + dw * shift + nrm * side * (PL_W / 2 + PD_GAP + PD_D / 2)
            poly = wrect(pc[0], pc[1], PD_W, PD_D, yaw_p)
            if free(poly, [plaza_poly, road_poly]):
                paddock = (pc, side, shift, poly)
                break
        if paddock:
            break
    if not paddock:
        sys.exit('no clear spot for the visitor paddock beside the plaza')
    pc, pside, pshift, pd_poly = paddock
    ra = plaza_c + dw * pshift + nrm * pside * (PL_W / 2 - 6)      # paddock road: plaza edge -> paddock edge, straight
    rb = pc - nrm * pside * (PD_D / 2 - 6)
    pd_road = resample_open(np.array([ra, rb]), 6.0)
    pd_road_poly = LineString([ra, rb]).buffer(PD_ROAD / 2)
    BAY_W, BAY_D, AISLE = 10.0, 22.0, 20.0
    CP_W, CP_D = 12 * BAY_W, 2 * BAY_D + AISLE
    carpark = None
    for side in (-pside, pside):
        for shift in (0, -20, 20, -40, 40):
            cc = plaza_c + dw * shift + nrm * side * (PL_W / 2 + CP_D / 2)
            poly = wrect(cc[0], cc[1], CP_W, CP_D, yaw_p)
            if free(poly, [road_poly, pd_poly, pd_road_poly], clear=10):
                carpark = (cc, side, poly)
                break
        if carpark:
            break
    if not carpark:                                               # fall back: beside the paddock, away from the plaza
        for shift in (0, 40, -40, 80, -80):
            cc = pc + dw * shift + nrm * pside * (PD_D / 2 + 4 + CP_D / 2)
            poly = wrect(cc[0], cc[1], CP_W, CP_D, yaw_p)
            if free(poly, [road_poly, pd_road_poly, plaza_poly], clear=10):
                carpark = (cc, pside, poly)
                break
    if not carpark:
        sys.exit('no clear spot for the car park')
    cc, cside, cp_poly = carpark
    paddock_def = {'x': round(float(pc[0]), 2), 'y': TOP, 'z': round(float(pc[1]), 2),
                   'dx': round(float(-nrm[0] * pside), 4), 'dz': round(float(-nrm[1] * pside), 4),
                   'w': PD_W, 'd': PD_D, 'yaw': yaw_deg, 'verified': False,
                   'source': 'gameplay: visitor/team paddock outside the track beside the plaza (circuit menu ring)'}
    paddock_road = {'pts': [round(float(v), 2) for q in pd_road for v in (q[0], TOP, q[1])], 'width': PD_ROAD}
    car_park = [{'x': round(float(cc[0]), 2), 'y': TOP, 'z': round(float(cc[1]), 2), 'w': CP_W, 'd': CP_D, 'yaw': yaw_deg,
                 'bayW': BAY_W, 'bayD': BAY_D, 'bays': 24, 'verified': False,
                 'source': 'gameplay: visitor car park with marked bays beside the plaza'}]
    # signs: dx/dz = the way the sign face looks (toward its readers). Thailand drives on the left, so road signs
    # stand on the left verge of the arrival road.
    left = -nrm
    arrow = lambda side: '<-' if side == -1 else '->'
    signs = [
        ('road', 'BIRA CIRCUIT ->', jw + dw * 40 + left * 22, -dw, 18, 6, 9),
        ('pylon', 'BIRA CIRCUIT', plaza_c - dw * (PL_D / 2 + 14) + left * 24, -dw, 10, 26, 0),
        ('road', arrow(pside) + ' PADDOCK', plaza_c - dw * (PL_D / 2 - 6) + nrm * pside * 20, -dw, 16, 5, 8),
        ('road', 'P CAR PARK ' + arrow(cside), plaza_c - dw * (PL_D / 2 - 6) + nrm * cside * 20, -dw, 16, 5, 8),
        ('board', 'PADDOCK', pc + nrm * pside * (PD_D / 2 - 3), -nrm * pside, 30, 7, 10),
    ]
    signs_def = [{'kind': k_, 'text': t_, 'x': round(float(p_[0]), 2), 'y': TOP, 'z': round(float(p_[1]), 2),
                  'dx': round(float(f_[0]), 4), 'dz': round(float(f_[1]), 4), 'w': w_, 'h': h_, 'post': po_}
                 for k_, t_, p_, f_, w_, h_, po_ in signs]
    flag_poles = []
    for k in range(4):                                            # two rows of flags lining the road into the gate
        for sd in (-1, 1):
            q = plaza_c + dw * (PL_D / 2 - 6 - k * 26) + nrm * sd * 19
            flag_poles.append({'x': round(float(q[0]), 2), 'y': TOP, 'z': round(float(q[1]), 2), 'color': k % 4})
    lamp_posts = []
    for poly_, inset in ((pd_poly, 4), (cp_poly, 3), (plaza_poly, 4)):
        cs = np.array(poly_.exterior.coords)[:4]
        ctr2 = cs.mean(0)
        for q in cs:
            dq = ctr2 - q
            dq = dq / np.linalg.norm(dq)
            p2 = q + dq * inset
            lamp_posts.append({'x': round(float(p2[0]), 2), 'y': TOP, 'z': round(float(p2[1]), 2),
                               'dx': round(float(dq[0]), 4), 'dz': round(float(dq[1]), 4)})
    # verge ground: low slabs (top 1 stud under the road) under the arrival area, and sloped shoulders on every edge,
    # so a car that leaves the road rolls down 1 stud onto flat ground instead of dropping 4 studs onto terrain
    VERGE_PAD = 30.0
    verge = [{'x': round(float((jw + gw)[0] / 2), 2), 'z': round(float((jw + gw)[1] / 2), 2), 'w': round(float(tlen), 1),
              'd': 26 + 2 * VERGE_PAD, 'yaw': yaw_deg, 'y': TOP - 1.0}]
    for cx_, cz_, w_, d_ in ((plaza_c[0], plaza_c[1], PL_D, PL_W), (pc[0], pc[1], PD_W, PD_D), (cc[0], cc[1], CP_W, CP_D)):
        verge.append({'x': round(float(cx_), 2), 'z': round(float(cz_), 2), 'w': round(float(w_ + 2 * VERGE_PAD), 1),
                      'd': round(float(d_ + 2 * VERGE_PAD), 1), 'yaw': yaw_deg, 'y': TOP - 1.0})
    rmid = (ra + rb) / 2
    verge.append({'x': round(float(rmid[0]), 2), 'z': round(float(rmid[1]), 2), 'w': PD_ROAD + 2 * VERGE_PAD,
                  'd': round(float(np.linalg.norm(rb - ra)), 1), 'yaw': yaw_deg, 'y': TOP - 1.0})
    shoulders = []                                                # edge a -> b (x, z), o = outward, y = top at the edge
    def edge(a, b, o, y=TOP):
        shoulders.append({'ax': round(float(a[0]), 2), 'az': round(float(a[1]), 2), 'bx': round(float(b[0]), 2),
                          'bz': round(float(b[1]), 2), 'ox': round(float(o[0]), 4), 'oz': round(float(o[1]), 4), 'y': y})
    for sd in (-1, 1):
        edge(jw + nrm * sd * 13, gw + nrm * sd * 13, nrm * sd)
        edge(ra + dw * sd * PD_ROAD / 2, rb + dw * sd * PD_ROAD / 2, dw * sd)
    for poly_ in (plaza_poly, pd_poly, cp_poly):
        cs = np.array(poly_.exterior.coords)[:4]
        ctr2 = cs.mean(0)
        for k in range(4):
            a, b = cs[k], cs[(k + 1) % 4]
            ab = (b - a) / np.linalg.norm(b - a)
            o = (a + b) / 2 - ctr2
            o = o - ab * (o @ ab)
            edge(a, b, o / np.linalg.norm(o))
    flat_zone = road_poly.union(plaza_poly).union(pd_poly).union(cp_poly).union(pd_road_poly).buffer(VERGE_PAD)
    # ground heightfield for terrain under the facility (DEM, pulled under the track so it never pokes through)
    cell = 32.0
    fac = stadium.buffer(40)
    bx0, by0, bx1, by1 = fac.bounds
    wx = W2(np.array([[bx0, by1], [bx1, by0]]))
    x0, z0 = float(wx[0][0]), float(wx[0][1])
    nx, nz = int((wx[1][0] - x0) / cell) + 1, int((wx[1][1] - z0) / cell) + 1
    gh = []
    for jz in range(nz):
        for jx in range(nx):
            px = gate_pt[0] + ((x0 + (jx + 0.5) * cell) - gw[0]) / ks
            py = gate_pt[1] - ((z0 + (jz + 0.5) * cell) - gw[1]) / ks
            q = np.array([px, py])
            yd = float(Y(h_at(q)))
            dd = np.linalg.norm(loop - q, axis=1)
            j = int(np.argmin(dd))
            reach = barrier[j].max()
            zone = max(hw_m[j] + cfg['runoff_outside_corner_m'], reach) + cell / ks
            near = dd < zone + 30
            if near.any():
                yt = float(np.min(y_trk[near])) - 1.5                 # lowest track surface around the cell
                w8 = min(max((dd[j] - zone) / 30, 0), 1)
                yd = yt if dd[j] < zone else min(yd, yt + (yd - yt) * w8) if yd > yt else yd * w8 + yt * (1 - w8)
            # arrival area: terrain flat 1 stud under the road top, blended back to the ground over 64 studs
            dz_ = flat_zone.distance(Point(x0 + (jx + 0.5) * cell, z0 + (jz + 0.5) * cell))
            if dz_ < 64:
                wf = dz_ / 64
                yf = (TOP - 1.0) * (1 - wf) + yd * wf
                yd = min(yd, yf) if near.any() else yf
            gh.append(int(math.floor(yd)))
    ground = {'x0': round(x0, 2), 'z0': round(z0, 2), 'cell': cell, 'nx': nx, 'nz': nz,
              'base': round(min(gh) - 12, 1), 'h': gh}

    # --- 9. overlap checks ------------------------------------------------------------------------------------------
    fac_w = Polygon(W2(np.array(stadium.exterior.coords)))
    city = corr['slice_bbox_s_w_n_e']
    corr_hits = []
    for e in corr['edges']:
        if J in (e['a'], e['b']):
            continue
        ls = LineString(np.array(e['pts']) + [WX, WZ]).buffer(e['width'] / 2)
        if ls.intersects(fac_w):
            corr_hits.append(e['id'])
    cx = [WX + p[0] for e in corr['edges'] for p in e['pts']]

    # --- 10. write --------------------------------------------------------------------------------------------------
    length3d = float(np.sum(np.sqrt(np.sum(np.diff(np.vstack([cl_w, cl_w[:1]]), axis=0) ** 2, axis=1)
                                     + np.diff(np.concatenate([y_trk, y_trk[:1]])) ** 2)))
    centre = [round(float(v), 2) for i in range(n) for v in (cl_w[i][0], y_trk[i], cl_w[i][1])]
    pit_y = list(pit_y_src)
    pit_w = W2(pit_pts)
    defn = {
        'id': 'bira', 'name': cfg['venue_name'], 'lengthStuds': round(length3d, 1),
        'studsPerMetre': round(ks, 4), 'direction': cfg['direction'],
        'centerline': centre,
        'width': [round(float(2 * v), 2) for v in hw_s],
        'trackWidth': round(cfg['track_width_m'] * ks, 2),
        'startFinish': {'index': 1},
        'sectors': [sectors[0] + 1, sectors[1] + 1],
        'grid': grid,
        'pitLane': [round(float(v), 2) for i in range(len(pit_pts)) for v in (pit_w[i][0], pit_y[i], pit_w[i][1])],
        'pitLaneWidth': round(cfg['pit_lane_width_m'] * ks, 2), 'pitSide': pit_side,
        'pitEntryIndex': pit_entry + 1, 'pitExitIndex': pit_exit + 1,
        'pitSpeedLimit': cfg['pit_speed_limit_studs_s'],
        'curbs': curbs, 'curbWidth': round(1.2 * ks, 2),
        'barrierRight': [round(float(v * ks), 1) for v in barrier[:, 0]],
        'barrierLeft': [round(float(v * ks), 1) for v in barrier[:, 1]],
        'runoffDefault': round(cfg['runoff_m'] * ks, 2),
        'brakeMarkers': brake,
        'corners': [{'from': c['from'] + 1, 'to': c['to'] + 1, 'turn': c['turn'], 'dir': c['dir'], 'radiusStuds': round(c['radius_m'] * ks, 1)} for c in corners],
        'buildings': buildings, 'parking': parking, 'entrance': entrance,
        'access': {'pts': [round(float(v), 2) for i in range(len(acc_w)) for v in (acc_w[i][0], y_acc[i], acc_w[i][1])],
                   'width': 26, 'joinNode': J, 'corridorGraph': 'build/bira/corridor_graph_game.json',
                   'scaleFrom': round(kc, 4), 'scaleTo': round(ks, 4), 'realLengthM': round(acc_len, 1),
                   'lengthStuds': round(float(tlen), 1), 'note': 'straight transition: slack from un-compressing the venue, not a real distance'},
        'serviceRoads': serv,
        'paddock': paddock_def, 'paddockRoad': paddock_road, 'carPark': car_park, 'signs': signs_def,
        'flagPoles': flag_poles, 'lampPosts': lamp_posts, 'verge': verge, 'shoulders': shoulders,
        'floodlights': flood,
        'ground': ground,
        'sources': [
            'Track centreline: OSM ways ' + ', '.join(map(str, ids)) + ' (highway=raceway "Bira Circuit"), (c) OpenStreetMap contributors, ODbL 1.0, base ' + raw['osm3s']['timestamp_osm_base'],
            'Pit lane: OSM service ways ' + ', '.join(map(str, cfg['pit_lane_ways'])),
            'Buildings: OSM "Pit Stop" x3, "Seating" footprints; parking OSM way ' + ', '.join(map(str, cfg['parking_ways'])),
            'Elevation: Terrain Tiles (Terrarium, AWS Open Data, z' + str(cfg['dem_zoom']) + '), SRTM-derived in this area; smoothed ' + str(cfg['elevation_smooth_m']) + ' m along the track',
            'Facts: length 2.41 km (Wikipedia / bira.co.th), direction ' + cfg['direction'] + ' (' + cfg['direction_source'] + ')',
        ],
        'verified': {
            'centerline_plan': 'OSM (traced, not surveyed); smoothed with 3 Chaikin passes',
            'elevation': 'DEM (~30 m SRTM-class), smoothed: shape plausible, absolute values unverified',
            'direction': 'secondary source only',
            'startFinish': 'gameplay: beside the middle of the main pit building (real line position unverified)',
            'sectors': 'gameplay (thirds of the lap)',
            'width': 'gameplay assumption (' + str(cfg['track_width_m']) + ' m, pit straight ' + str(cfg['pit_straight_width_m']) + ' m)',
            'pitLane': 'OSM service ways (route real, width assumed)',
            'grid': 'gameplay', 'curbs': 'gameplay (from curvature)', 'barriers': 'gameplay (run-off ' + str(cfg['runoff_m']) + '/' + str(cfg['runoff_outside_corner_m']) + ' m, limited by clearance)',
            'brakeMarkers': 'gameplay', 'floodlights': 'gameplay (no evidence of circuit floodlighting)',
            'buildings': 'pit_garage/grandstand footprints from OSM (heights assumed); race_control/paddock gameplay',
            'parking': 'one OSM parking area + gameplay entrance plaza', 'access': 'corridor = real roads (OSM, x0.5); transition road length = gameplay slack',
        },
        'attribution': cfg['attribution'],
    }
    json.dump(defn, open(os.path.join(out_dir, 'circuit.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    body = '\n'.join(f'  {k} = {lua_val(v)},' for k, v in defn.items())
    luau = ('--!strict\n-- GENERATED by tools/circuit/bira_circuit.py from tools/circuit/config/bira.json - do not edit by hand.\n'
            '-- Bira Circuit game venue: WORLD coordinates (studs), centreline closed loop in driving direction, y = surface.\n'
            '-- Indices are 1-based into centerline points; side = 1 right / -1 left of the driving direction.\n'
            f'-- {cfg["attribution"]}\n'
            'return {\n' + body + '\n}\n')
    open(os.path.join(out_dir, 'bira.luau'), 'w', encoding='utf-8').write(luau)
    dst = os.path.join(ROOT, 'roblox', 'data', 'circuits')
    os.makedirs(dst, exist_ok=True)
    shutil.copy(os.path.join(out_dir, 'bira.luau'), os.path.join(dst, 'bira.luau'))

    # --- report -----------------------------------------------------------------------------------------------------
    print(f"raceway OSM loop {raw_len:,.0f} m ({len(chain) - 1} nodes), smoothed {smooth_len:,.0f} m, target 2,410 m "
          f"({(raw_len / 2410 - 1) * 100:+.1f}%); total turning {total_turn:+.0f} deg")
    print(f"corners (>= {cfg['corner_min_turn_deg']} deg, radius < {cfg['corner_max_radius_m']} m): {len(corners)} = "
          + ', '.join(f"{c['dir']}{abs(c['turn']):.0f}@{c['s_m']:.0f}m(r{c['radius_m']:.0f})" for c in corners))
    print(f"elevation raw {h_raw.min():.1f}..{h_raw.max():.1f} m, smoothed {h_trk.min():.1f}..{h_trk.max():.1f} m, "
          f"max grade {np.max(np.abs(grade)) * 100:.1f}%, reference (track by the gate) {h_ref:.1f} m, DEM at gate {h_gate_dem:.1f} m")
    print(f"centreline {n} pts every {cfg['resample_studs']} studs, lap {length3d:,.0f} studs; pit lane {len(pit_pts)} pts, side {pit_side}, "
          f"entry idx {pit_entry + 1} exit idx {pit_exit + 1}")
    print(f"access road real {acc_len:.1f} m; transition {tlen:.0f} studs: junction {jw.round(1)} -> gate {gw.round(1)} (world)")
    print(f"facility world bbox x {fac_w.bounds[0]:.0f}..{fac_w.bounds[2]:.0f}, z {fac_w.bounds[1]:.0f}..{fac_w.bounds[3]:.0f}; "
          f"y {y_trk.min():.0f}..{y_trk.max():.0f}; corridor x {min(cx):.0f}..{max(cx):.0f}")
    print(f"corridor edges overlapping the facility: {corr_hits or 'none'}; buildings {len(buildings)}, parking {len(parking)}, "
          f"service roads {len(serv)}, floodlights {len(flood)}, brake boards {len(brake)}, curbs {len(curbs)}, ground {nx}x{nz}")
    print(f"luau {os.path.getsize(os.path.join(out_dir, 'bira.luau')) / 1024:.0f} KB")

    # --- check image ------------------------------------------------------------------------------------------------
    im = Image.new('RGB', (1900, 1300), 'white')
    dr = ImageDraw.Draw(im)
    # left: overview (world x/z), city slice box, corridor, facility
    allp = np.array([[WX + p[0], WZ + p[1]] for e in corr['edges'] for p in e['pts']] + list(fac_w.exterior.coords)
                    + [[WX - 1465, -3172], [WX + 3006, 3169]])
    lo, hi = allp.min(0) - 300, allp.max(0) + 300
    f = 880 / (hi - lo).max()
    T = lambda p: (10 + (p[0] - lo[0]) * f, 60 + (p[1] - lo[1]) * f)
    dr.rectangle([T((WX - 1465, -3172)), T((WX + 3006, 3169))], outline=(120, 120, 220), width=2)
    dr.text(T((WX - 1400, -3150)), 'central slice (graph_game.json)', fill=(80, 80, 200))
    for e in corr['edges']:
        dr.line([T((WX + x, WZ + z)) for x, z in e['pts']], fill=(230, 70, 40) if e['tier'] == 'express' else (240, 150, 20), width=2)
    dr.polygon([T(p) for p in fac_w.exterior.coords], outline=(200, 0, 200))
    dr.line([T(p) for p in cl_w] + [T(cl_w[0])], fill=(200, 0, 0), width=2)
    dr.text((14, 10), 'OVERVIEW (world studs, x east, z south): corridor x0.5 compressed, circuit 1:1', fill=(0, 0, 0))
    dr.text((14, 26), f'corridor {sum(LineString(e["pts"]).length for e in corr["edges"]) / 2:,.0f} studs one way', fill=(0, 0, 0))
    # right: facility plan
    fpts = np.vstack([np.array(fac_w.exterior.coords), acc_w, [[p["x"], p["z"]] for p in parking]])
    lo2, hi2 = fpts.min(0) - 40, fpts.max(0) + 40
    f2 = 940 / (hi2 - lo2).max()
    T2 = lambda p: (930 + (p[0] - lo2[0]) * f2, 40 + (p[1] - lo2[1]) * f2)
    gx = lambda jx: x0 + jx * cell
    gmin, gmax = min(gh), max(gh)
    for jz in range(nz):
        for jx in range(nx):
            v = int(200 + 50 * (gh[jz * nx + jx] - gmin) / max(gmax - gmin, 1))
            dr.rectangle([T2((gx(jx), z0 + jz * cell)), T2((gx(jx + 1), z0 + (jz + 1) * cell))], fill=(v - 30, v, v - 40))
    dr.polygon([T2(p) for p in fac_w.exterior.coords], outline=(200, 0, 200))
    for k, side in enumerate((1, -1)):
        bp = [(i, at(i, side, barrier[i, k])) for i in range(n)]
        run = []
        for i, p in bp + [bp[0]]:
            if barrier[i, k] > 0:
                run.append(T2(p))
            else:
                if len(run) > 1: dr.line(run, fill=(90, 90, 90), width=1)
                run = []
        if len(run) > 1: dr.line(run, fill=(90, 90, 90), width=1)
    for i in range(n):
        a, b = at(i, 1, hw_m[i]), at(i, -1, hw_m[i])
        dr.line([T2(a), T2(b)], fill=(60, 60, 66), width=2)
    dr.line([T2(p) for p in pit_w], fill=(80, 140, 255), width=max(2, int(cfg['pit_lane_width_m'] * ks * f2)))
    for c in curbs:
        i0, i1 = c['from'] - 1, c['to'] - 1
        js = [(i0 + j) % n for j in range((i1 - i0) % n + 1)]
        k = 0 if c['side'] == 1 else 1
        dr.line([T2(at(j, c['side'], hw_m[j] + 0.4)) for j in js], fill=(230, 30, 30), width=3)
    for r in serv:
        q = np.array(r['pts']).reshape(-1, 3)[:, [0, 1]]
        dr.line([T2(p) for p in q], fill=(150, 130, 100), width=2)
    for b in buildings + [dict(p, kind='parking') for p in parking]:
        ang = math.radians(b['yaw'])
        u2, v2 = np.array([math.cos(ang), math.sin(ang)]), np.array([-math.sin(ang), math.cos(ang)])
        c2 = np.array([b['x'], b['z']])
        poly = [c2 + u2 * a * b['w'] / 2 + v2 * bb * b['d'] / 2 for a, bb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        col = {'pit_garage': (0, 150, 0), 'grandstand': (0, 90, 200), 'race_control': (255, 120, 0),
               'paddock': (170, 170, 170), 'parking': (255, 190, 0)}[b['kind']]
        dr.polygon([T2(p) for p in poly], outline=col, width=2)
        dr.text(T2(c2), b['kind'] + ('' if b['verified'] else '*'), fill=col)
    for g in grid:
        dr.ellipse([T2((g['x'] - 6, g['z'] - 6)), T2((g['x'] + 6, g['z'] + 6))], fill=(0, 0, 0))
    for b in brake:
        dr.rectangle([T2((b['x'] - 5, b['z'] - 5)), T2((b['x'] + 5, b['z'] + 5))], fill=(255, 255, 255), outline=(0, 0, 0))
    for fl in flood:
        dr.ellipse([T2((fl['x'] - 7, fl['z'] - 7)), T2((fl['x'] + 7, fl['z'] + 7))], fill=(255, 220, 0))
    dr.line([T2(p) for p in acc_w], fill=(240, 150, 20), width=4)
    for i, lbl in ((0, 'S/F'), (sectors[0], 'S1|S2'), (sectors[1], 'S2|S3'), (pit_entry, 'pit in'), (pit_exit, 'pit out')):
        dr.line([T2(at(i, 1, hw_m[i] + 6)), T2(at(i, -1, hw_m[i] + 6))], fill=(255, 0, 255), width=3)
        dr.text(T2(at(i, -1, hw_m[i] + 25)), lbl, fill=(160, 0, 160))
    for ci, c in enumerate(corners):
        m = (c['from'] + ((c['to'] - c['from']) % n) // 2) % n
        side = 1 if c['dir'] == 'L' else -1
        dr.text(T2(at(m, side, hw_m[m] + 40)), f"T{ci + 1}", fill=(200, 0, 0))
    dr.text((934, 10), f'FACILITY 1:1 ({ks:.3f} studs/m): track, pit lane (blue), curbs, barriers, buildings (* = gameplay), '
            'grid, brake boards, floodlights, access (orange), terrain shade', fill=(0, 0, 0))
    # bottom: elevation profile
    y0p, hp = 1000, 260
    dr.rectangle([10, y0p, 1890, y0p + hp], outline=(0, 0, 0))
    ys = (y_trk - y_trk.min()) / max(np.ptp(y_trk), 1)
    yr = (Y(h_raw) - y_trk.min()) / max(np.ptp(y_trk), 1)
    X = lambda i: 20 + i / n * 1860
    dr.line([(X(i), y0p + hp - 10 - yr[i] * (hp - 30)) for i in range(n)], fill=(190, 190, 190), width=1)
    dr.line([(X(i), y0p + hp - 10 - ys[i] * (hp - 30)) for i in range(n)], fill=(200, 0, 0), width=2)
    for ci, c in enumerate(corners):
        dr.text((X(c['from']), y0p + 4), f"T{ci + 1}", fill=(0, 0, 0))
    dr.text((20, y0p + hp + 6), f'elevation along the lap from S/F (DEM grey raw, red smoothed): {h_trk.min():.0f}..{h_trk.max():.0f} m '
            f'= y {y_trk.min():.0f}..{y_trk.max():.0f} studs, max grade {np.max(np.abs(grade)) * 100:.1f}%  |  '
            f'OSM length {raw_len:,.0f} m vs 2,410 m official  |  {len(corners)} corners by curvature', fill=(0, 0, 0))
    im.save(os.path.join(out_dir, 'bira_check.png'))


if __name__ == '__main__':
    main(sys.argv[1])
