"""The approved Sukhumvit shoulder pilot in the owner's view, and its anti-flip support (offline, read only).

  shoulder_report(W, area, P=None)  pieces / parts / visible area per kind (shoulder strip, taper, gap fill) inside the
                                   area and inside the owner's camera footprint; visible = not under a higher surface
  offset_drive(W, area, P=None)    the shoulder generator's drive gate on Sukhumvit: a car footprint (car_width 4 x
                                   car_length 9, 6 points, as road_shoulders.drive 'spec') every 2 studs along every
                                   Sukhumvit carriageway of the graph at lateral offsets 0, +-8, +-14, +-20, +-24; each
                                   sample is 'flat' (every point on a road-height surface: asphalt, disc, apron,
                                   shoulder), 'kerb' (a point on a sidewalk / island top, 0.45-0.6 up, no drop) or 'drop'
                                   (a point over terrain, 3 studs down). Gate: drops after <= drops before per offset.
P None = the current built state (before); P = a pilot (A or B): replaced parts out, pilot surfaces in, shoulders kept.
"""
import math

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from tools.roadvis import world

OFFSETS = (0, 8, -8, 14, -14, 20, -20, 24, -24)
CAR_W, CAR_L = 4.0, 9.0
OWNER_CAM = dict(pos=(24609.8, 115.9, 713.3), dir=(-0.386, -0.386, 0.837), fov=70.0, res=(1831, 1074))


def owner_footprint(far=1500.0):
    """ground polygon (local x / z, y = 1) the owner's screenshot camera sees"""
    px, py, pz = OWNER_CAM['pos']
    px -= world.ORIGIN[0]
    f = np.array(OWNER_CAM['dir'], float)
    f /= np.linalg.norm(f)
    right = np.cross(f, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    th = math.tan(math.radians(OWNER_CAM['fov'] / 2))
    tw = th * OWNER_CAM['res'][0] / OWNER_CAM['res'][1]
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        d = f + right * sx * tw + up * sy * th
        if d[1] < -1e-6:
            t = (1.0 - py) / d[1]
            g = np.array([px + d[0] * t, pz + d[2] * t])
        else:
            h = np.array([d[0], d[2]])
            g = np.array([px, pz]) + h / np.linalg.norm(h) * far
        if np.linalg.norm(g - [px, pz]) > far:
            g = np.array([px, pz]) + (g - [px, pz]) / np.linalg.norm(g - [px, pz]) * far
        pts.append(tuple(g))
    return Polygon(pts).buffer(0)


def _state(W, P):
    """(flat union, high union) of the state"""
    rep = {id(s) for s in P['replaced']} if P is not None else set()
    flat = [s['poly'] for s in W['surf'] if id(s) not in rep and (s['kind'] in world.ROAD_KINDS or s['kind'] in world.SHOULDER_KINDS)]
    high = [s['poly'] for s in W['surf'] if id(s) not in rep and s['kind'] in ('sidewalk', 'corner')]
    if P is not None:
        flat.append(P['coll_asphalt'])
        high += [P['walk'], P['islands']]
    return unary_union(flat), unary_union(high)


def shoulder_report(W, area, P=None):
    flat, high = _state(W, P)
    cover = [s['poly'] for s in W['surf'] if s['kind'] in ('road', 'fill', 'junction', 'joint') and (P is None or id(s) not in {id(r) for r in P['replaced']})]
    if P is not None:
        cover += [P['S']]
    over = unary_union(cover + [high])                           # surfaces above the shoulder top (0.985)
    view = owner_footprint()
    out = {}
    for k in world.SHOULDER_KINDS:
        ps = [s for s in W['surf'] if s['kind'] == k and s['poly'].intersects(area)]
        vis = unary_union([s['poly'] for s in ps]).difference(over) if ps else Polygon()
        out[k] = dict(pieces=len(ps), parts=sum(s.get('parts', 1) for s in ps),
                      area=round(unary_union([s['poly'] for s in ps]).area if ps else 0.0, 0),
                      visible_area=round(vis.intersection(area).area, 0),
                      visible_in_owner_view=round(vis.intersection(view).area, 0),
                      visible_pieces=sum(1 for s in ps if s['poly'].difference(over).area > 1.0),
                      visible_pieces_in_view=sum(1 for s in ps if s['poly'].difference(over).intersection(view).area > 1.0))
    return out


def offset_drive(W, area, P=None, chains=None, inset=50.0, step=2.0):
    flat, high = _state(W, P)
    shapely.prepare(flat)
    shapely.prepare(high)
    inner = area.buffer(-inset)
    G = W['graph']
    lines = [e for e in G['edges'] if e['class'] == 'trunk' and (e.get('name_en') == 'Sukhumvit Road' or e.get('name') == 'ถนนสุขุมวิท')
             and LineString(e['pts']).intersects(inner)]
    pts_rel = [(-CAR_L / 2, -CAR_W / 2), (-CAR_L / 2, CAR_W / 2), (CAR_L / 2, -CAR_W / 2), (CAR_L / 2, CAR_W / 2), (0, -CAR_W / 2), (0, CAR_W / 2)]
    res = {}
    for o in OFFSETS:
        n = drop = kerb = n_in = drop_in = kerb_in = 0
        for e in lines:
            Q = world.rc.probes_of(e['pts'], step)
            if len(Q) < 3:
                continue
            T = np.gradient(Q, axis=0)
            T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
            m = shapely.contains_xy(inner, Q[:, 0], Q[:, 1])
            Q, T = Q[m], T[m]
            if not len(Q):
                continue
            N = np.stack([-T[:, 1], T[:, 0]], axis=1)
            C = Q + N * o
            on_f = np.ones(len(C), bool)
            on_h = np.zeros(len(C), bool)
            for lo, la in pts_rel:
                p = C + T * lo + N * la
                f = shapely.contains_xy(flat, p[:, 0], p[:, 1])
                h = shapely.contains_xy(high, p[:, 0], p[:, 1])
                on_f &= f | h
                on_h |= h
            d = ~on_f
            k = on_f & on_h
            n += len(C)
            drop += int(d.sum())
            kerb += int(k.sum())
            if abs(o) <= e['width'] / 2:
                n_in += len(C)
                drop_in += int(d.sum())
                kerb_in += int(k.sum())
        res[str(o)] = dict(samples=n, drop=drop, kerb=kerb, in_lane_samples=n_in, in_lane_drop=drop_in, in_lane_kerb=kerb_in)
    return res
