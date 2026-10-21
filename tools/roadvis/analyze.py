"""Road-visual defect metrics, for one area and citywide, from the BUILT data (world.load).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\analyze.py [--area x0 z0 x1 z1 (world)] [--city] [--out file]

Definitions (all in map-local studs; areas in studs^2; 1 stud = 0.28 m in Roblox units, but see proportions):
  asphalt          union of every road-height asphalt part: slabs, fill triangles, junction + joint discs, aprons
  overlap>=2       area covered by >= 2 distinct asphalt units (an edge's slabs + fills = one unit, each disc one unit,
                   the aprons of one junction one unit), rasterised at `res` studs
  disc overhang    disc area outside the union of all edge slabs + fills (a circle sticking out past the road edges)
  lane corridor    where real lanes are: every graph edge (graph_game.json, BOTH carriageways, hidden ones too) buffered
                   by width / 2 (flat ends, +1 stud tolerance), plus per junction node (degree >= 3) the convex hull of
                   its arms' cross-sections at the node and at the widest half-width out, plus a disc of half-width at
                   degree-2 nodes (bend wedge)
  meaningless asphalt   asphalt minus lane corridor (medians paved over, fill blobs, disc overhangs, apron spill)
  lane holes       lane corridor of a VISIBLE carriageway lane not covered by asphalt (the car would drop)
  crossings        per zebra: angle between its bars and the leg's direction, share of the asphalt cross-section it
                   spans, whether either end lands on a sidewalk / corner fill, whether it sits on a hidden carriageway,
                   distance to the nearest junction node
  lane lines       expected lane boundaries (per graph edge: lanes - 1 boundaries + the centre of a two-way road; tier
                   soi excluded, junction interiors excluded) sampled every 4 studs; a sample is covered when a drawn
                   marking (dash gaps bridged) lies within 1.5 studs; plus marking run ends away from junction mouths
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
if os.path.dirname(os.path.dirname(HERE)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from tools.roadvis import world  # noqa: E402

PILOT_BBOX_WORLD = (24220.0, 650.0, 24820.0, 1250.0)
LANE_M = {'trunk': 3.5, 'trunk_link': 3.5, 'primary': 3.5, 'primary_link': 3.5, 'secondary': 3.25, 'secondary_link': 3.25,
          'tertiary': 3.25, 'tertiary_link': 3.25}
LANE_M_DEFAULT = 3.0
COMPRESSION, M_PER_STUD = 0.5, 0.28


def r1(v, n=1):
    return round(float(v), n)


# ---- raster helpers ----------------------------------------------------------------------------------------------------
def _draw(mask, poly, x0, z0, res):
    d = ImageDraw.Draw(mask)
    for q in getattr(poly, 'geoms', [poly]):
        if q.geom_type == 'Polygon' and not q.is_empty:
            d.polygon([((x - x0) / res, (z - z0) / res) for x, z in q.exterior.coords], fill=1)
            for h in q.interiors:
                d.polygon([((x - x0) / res, (z - z0) / res) for x, z in h.coords], fill=0)


def count_raster(units, bbox, res):
    """int16 array: how many units (lists of polygons) cover each cell of bbox"""
    x0, z0, x1, z1 = bbox
    W, H = int(math.ceil((x1 - x0) / res)), int(math.ceil((z1 - z0) / res))
    cnt = np.zeros((H, W), np.int16)
    for polys in units:
        polys = [p for p in polys if p is not None and not p.is_empty]
        if not polys:
            continue
        bx0, bz0, bx1, bz1 = unary_union(polys).bounds if len(polys) > 1 else polys[0].bounds
        i0, j0 = max(int((bx0 - x0) / res) - 1, 0), max(int((bz0 - z0) / res) - 1, 0)
        i1, j1 = min(int((bx1 - x0) / res) + 2, W), min(int((bz1 - z0) / res) + 2, H)
        if i1 <= i0 or j1 <= j0:
            continue
        m = Image.new('1', (i1 - i0, j1 - j0), 0)
        for p in polys:
            _draw(m, p, x0 + i0 * res, z0 + j0 * res, res)
        cnt[j0:j1, i0:i1] += np.asarray(m, dtype=np.int16)
    return cnt


# ---- building blocks -------------------------------------------------------------------------------------------------
def asphalt_units(W, B=None):
    """[(label, [polys])] distinct asphalt units inside box B"""
    by_edge, by_apron, out = defaultdict(list), defaultdict(list), []
    for s in W['surf']:
        if B is not None and not s['poly'].intersects(B):
            continue
        k = s['kind']
        if k in ('road', 'fill'):
            by_edge[s['edge']].append(s['poly'])
        elif k in ('junction', 'joint'):
            out.append((f"{k}:{s['node']}", [s['poly']]))
        elif k == 'apron':
            by_apron[s['node']].append(s['poly'])
    out += [(f"edge:{W['edges'][i]['id']}", v) for i, v in sorted(by_edge.items())]
    out += [(f'apron:{n}', v) for n, v in sorted(by_apron.items())]
    return out


def corridor(W, B, tol=1.0):
    """(lane corridor polygon inside B (see module doc), per-edge corridors {edge id: poly}, junction hulls)"""
    G = W['graph']
    Bb = B.buffer(150)
    per, parts, hulls = {}, [], []
    ends = defaultdict(list)          # node -> [(dir away from node, width)]
    for e in G['edges']:
        L = LineString(e['pts'])
        if not L.intersects(Bb):
            continue
        p = L.buffer(e['width'] / 2 + tol, cap_style='flat', join_style='round')
        per[e['id']] = p
        parts.append(p)
        P = np.asarray(e['pts'], float)
        for node, a, b in ((e['a'], P[0], P[min(3, len(P) - 1)]), (e['b'], P[-1], P[max(-4, -len(P))])):
            d = b - a
            n = np.linalg.norm(d)
            if n > 0:
                ends[node].append((d / n, e['width'], tuple(a)))
    for node, lst in ends.items():
        c = np.asarray(G['nodes'].get(node, lst[0][2]), float)
        if G['deg'][node] >= 3:
            R = max(w for _, w, _ in lst) / 2
            pts = []
            for d, w, _ in lst:
                nrm = np.array([-d[1], d[0]])
                for s in (0.0, R):
                    pts += [tuple(c + d * s + nrm * (w / 2 + tol)), tuple(c + d * s - nrm * (w / 2 + tol))]
            parts.append(shapely.MultiPoint(pts).convex_hull)
            hulls.append(parts[-1])
        else:
            parts.append(Point(c).buffer(max(w for _, w, _ in lst) / 2 + tol, 24))
    return unary_union(parts).intersection(B), per, (unary_union(hulls) if hulls else Polygon())


def visible_lane_area(W, B, per):
    """corridor of the carriageways that the built data shows as roads (graph edges that are not hidden), inside B"""
    hid = {e['id'] for e in W['edges'] if e.get('hidden')}
    return unary_union([p for k, p in per.items() if k not in hid]).intersection(B)


def crossing_report(W, asphalt, walk_union, B=None):
    G = W['graph']
    gl = {e['id']: e for e in G['edges']}
    hidden = {e['id'] for e in W['edges'] if e.get('hidden')}
    merged = {e['id'] for e in W['edges'] if e.get('merged')}
    jn = [(n, np.asarray(G['nodes'][n], float)) for n in G['nodes'] if G['deg'][n] >= 3]
    jtree = STRtree([Point(*p) for _, p in jn]) if jn else None
    rows = []
    for c in W['crossings']:
        x, z, tx, tz, n, bw, gap, dep = c['row']
        if B is not None and not B.contains(Point(x, z)):
            continue
        p = np.array([x, z])
        t = np.array([tx, tz]) / math.hypot(tx, tz)
        across = np.array([-t[1], t[0]])
        span = n * (bw + gap) - gap
        e = gl.get(c['edge'])
        ang = None
        if e is not None:
            L = LineString(e['pts'])
            s = L.project(Point(x, z))
            a_, b_ = L.interpolate(max(s - 3, 0)), L.interpolate(min(s + 3, L.length))
            d = np.array([b_.x - a_.x, b_.y - a_.y])
            d /= max(np.linalg.norm(d), 1e-9)
            ang = math.degrees(math.acos(min(1.0, abs(float(d @ t)))))
        # asphalt cross-section through the crossing centre, across the road
        ray = LineString([tuple(p - across * 200), tuple(p + across * 200)])
        sec = ray.intersection(asphalt)
        seg_len = 0.0
        for g in getattr(sec, 'geoms', [sec]):
            if not g.is_empty and g.distance(Point(x, z)) < 0.5:
                seg_len = g.length
        e1, e2 = p - across * span / 2, p + across * span / 2
        land = [walk_union.distance(Point(*q)) <= 3.0 if walk_union is not None and not walk_union.is_empty else False for q in (e1, e2)]
        dj = None
        if jtree is not None:
            k = jtree.query_nearest(Point(x, z))
            dj = float(np.linalg.norm(jn[int(k[0])][1] - p))
        rows.append(dict(x=r1(x), z=r1(z), world=world.to_world(r1(x), r1(z)), edge=c['edge'], src=c['src'], bars=int(n), span=r1(span),
                         asphalt_section=r1(seg_len), coverage=r1(span / seg_len if seg_len else 0, 2),
                         angle_err_deg=r1(ang) if ang is not None else None, lands=land, on_hidden_edge=c['edge'] in hidden,
                         on_merged_edge=c['edge'] in merged, dist_junction=r1(dj) if dj is not None else None))
    return rows


def crossing_summary(rows):
    n = len(rows)
    if not n:
        return dict(n=0)
    return dict(n=n,
                span_lt_80pct_of_asphalt=sum(1 for r in rows if r['coverage'] < 0.8),
                no_landing_either_end=sum(1 for r in rows if not any(r['lands'])),
                landing_both_ends=sum(1 for r in rows if all(r['lands'])),
                on_hidden_carriageway=sum(1 for r in rows if r['on_hidden_edge']),
                on_merged_slab=sum(1 for r in rows if r['on_merged_edge']),
                angle_err_gt_10=sum(1 for r in rows if (r['angle_err_deg'] or 0) > 10),
                midblock_gt_60_from_junction=sum(1 for r in rows if (r['dist_junction'] or 0) > 60),
                median_coverage=r1(np.median([r['coverage'] for r in rows]), 2))


def lane_line_report(W, B, junction_r=None):
    """expected lane boundary coverage + abrupt marking run ends inside B"""
    G = W['graph']
    hidden = {e['id'] for e in W['edges'] if e.get('hidden')}
    jr = {}
    for s in W['surf']:
        if s['kind'] == 'junction':
            jr[s['node']] = s['r']
    # drawn markings, dash gaps bridged: each mark segment extended by 6 studs each way, buffered 1.5
    segs = [m for m in W['marks'] if B is None or m['poly'].intersects(B)]
    lines = []
    for m in segs:
        a, b = np.asarray(m['a']), np.asarray(m['b'])
        d = b - a
        n = np.linalg.norm(d)
        if n < 1e-6:
            continue
        d /= n
        ext = m.get('gap', 12) / 2 + 0.5 if m['kind'] == 'lane' else 0.5
        lines.append(LineString([tuple(a - d * ext), tuple(b + d * ext)]))
    mk = unary_union(lines).buffer(1.5, cap_style='flat') if lines else None
    exp_n = exp_cov = 0
    exp_hidden_n = exp_hidden_cov = 0
    per_class = Counter()
    for e in G['edges']:
        if e['tier'] == 'soi':
            continue
        L = LineString(e['pts'])
        if B is not None and not L.intersects(B):
            continue
        n, w = e['lanes'], e['width']
        offs = [(k - n / 2) * w / n for k in range(1, n)] if e['oneway'] else [0.0] + [k * w / n * sg for k in range(1, n // 2) for sg in (1, -1)]
        if not offs:
            continue
        P = np.asarray(e['pts'], float)
        tot = L.length
        ra = (jr.get(e['a'], 0) if G['deg'][e['a']] >= 3 else 0) + 2
        rb = (jr.get(e['b'], 0) if G['deg'][e['b']] >= 3 else 0) + 2
        if tot - ra - rb < 8:
            continue
        inner = world.rc.trim(P, ra, rb)
        if inner is None:
            continue
        for o in offs:
            q = world.rc.offset(inner, o) if abs(o) > 1e-6 else inner
            qs = world.rc.probes_of(q, 4.0)
            pts = shapely.points(qs[:, 0], qs[:, 1])
            if B is not None:
                pts = pts[shapely.contains(B, pts)]
            if not len(pts):
                continue
            cov = int(shapely.contains(mk, pts).sum()) if mk is not None else 0
            if e['id'] in hidden:
                exp_hidden_n += len(pts); exp_hidden_cov += cov
            else:
                exp_n += len(pts); exp_cov += cov
    # marking run ends: endpoints of the bridged runs farther than r + 6 from any junction node
    ends_total = ends_abrupt = 0
    run_lens = []
    if mk is not None:
        jpts = [Point(*G['nodes'][n]).buffer(jr.get(n, 13) + 6) for n in G['nodes'] if G['deg'][n] >= 3 and n in jr]
        jzone = unary_union(jpts) if jpts else None
        runs = shapely.line_merge(unary_union(lines))
        for g in getattr(runs, 'geoms', [runs]):
            run_lens.append(g.length)
            for q in (g.coords[0], g.coords[-1]):
                if B is not None and not B.contains(Point(q)):
                    continue
                ends_total += 1
                if jzone is None or not jzone.contains(Point(q)):
                    ends_abrupt += 1
    return dict(expected_boundary_samples_visible=exp_n, covered_visible=exp_cov,
                coverage_visible=r1(exp_cov / exp_n if exp_n else 0, 3),
                expected_boundary_samples_hidden=exp_hidden_n, covered_hidden=exp_hidden_cov,
                coverage_all=r1((exp_cov + exp_hidden_cov) / (exp_n + exp_hidden_n) if exp_n + exp_hidden_n else 0, 3),
                marking_parts=len(segs), runs=len(run_lens), run_median_len=r1(np.median(run_lens)) if run_lens else None,
                run_ends=ends_total, run_ends_away_from_junctions=ends_abrupt)


def joints_report(W, B=None):
    """lane-line breaks at degree-2 joints between two marked (non-soi, visible) edges: gap and lateral jump"""
    G = W['graph']
    at = defaultdict(list)
    for i, e in enumerate(W['edges']):
        if e.get('hidden') or e['tier'] == 'soi':
            continue
        at[e['a']].append((i, 'a'))
        at[e['b']].append((i, 'b'))
    marks_by_edge = defaultdict(list)
    for m in W['marks']:
        marks_by_edge[m['edge']].append(m)
    n = broken = lanes_change = 0
    gaps, jumps = [], []
    for node, lst in at.items():
        if G['deg'].get(node, 0) != 2 or len(lst) != 2:
            continue
        c = G['nodes'].get(node)
        if c is None or (B is not None and not B.contains(Point(c))):
            continue
        (i, ei), (j, ej) = lst
        A, Bq = W['edges'][i], W['edges'][j]
        n += 1
        if A['lanes'] != Bq['lanes'] or A['width'] != Bq['width'] or A['oneway'] != Bq['oneway']:
            lanes_change += 1
        mi = marks_by_edge.get(i, [])
        mj = marks_by_edge.get(j, [])
        if not mi or not mj:
            broken += 1
            continue
        cp = Point(c)
        di = min(m['poly'].distance(cp) for m in mi)
        dj = min(m['poly'].distance(cp) for m in mj)
        g = di + dj
        gaps.append(g)
        if g > 12 + 8:            # more than one dash gap + dash with nothing
            broken += 1
        # lateral jump: centre / dash line positions just before vs just after the joint
        def lat(ms):
            near = [m for m in ms if m['poly'].distance(cp) < 25]
            return sorted({r1(LineString([tuple(m['a']), tuple(m['b'])]).distance(cp), 0) for m in near})
        la, lb = lat(mi), lat(mj)
        if la and lb:
            jumps.append(max(min(abs(x - y) for y in lb) for x in la))
    return dict(joints=n, broken=broken, lanes_or_width_change=lanes_change,
                median_gap=r1(np.median(gaps)) if gaps else None, p90_gap=r1(np.percentile(gaps, 90)) if gaps else None,
                jump_gt_3=sum(1 for v in jumps if v > 3))


def proportions(W, B, asphalt):
    """road vs city scale for box B (local)"""
    G = W['graph']
    kk = COMPRESSION / M_PER_STUD                       # studs per real metre of city distance
    lane = 13.0
    out = dict(studs_per_m_city=r1(kk, 3), studs_per_m_lane=r1(lane / 3.5, 3),
               studs_per_m_car=r1(world.CAR['width'] / 1.85, 3), studs_per_m_height=r1(0.75 / M_PER_STUD, 3),
               road_widening_vs_city=r1(lane / 3.5 / kk, 2))
    # real road area share inside the same ground box (OSM lanes x lane width, at city scale)
    src = W['graph']['source_by_way']
    real = game_lane = 0.0
    for e in G['edges']:
        L = LineString(e['pts']).intersection(B)
        if L.is_empty:
            continue
        s = src.get(e['way'])
        lanes = e['lanes']
        if s is not None and s.get('lanes_tag'):
            try:
                lanes = max(int(str(s['lanes_tag']).split(';')[0]), 1)
            except ValueError:
                pass
        real += L.length * lanes * LANE_M.get(e['class'], LANE_M_DEFAULT) * kk          # in studs^2 at city scale
        game_lane += L.length * e['width']
    A = B.area
    bl = [b for b in W['blds'] if b['poly'].intersects(B)]
    sb = []
    for b in bl:
        sb.append(b['poly'].distance(asphalt) if not asphalt.is_empty else 0.0)
    out.update(box_area=r1(A, 0), asphalt_share=r1(asphalt.area / A, 3), real_road_share_city_scale=r1(real / A, 3),
               game_lane_share=r1(game_lane / A, 3),
               buildings=len(bl), building_median_w=r1(np.median([max(b['w'], b['d']) for b in bl])) if bl else None,
               building_median_d=r1(np.median([min(b['w'], b['d']) for b in bl])) if bl else None,
               building_median_h=r1(np.median([b['h'] for b in bl])) if bl else None,
               building_setback_median=r1(np.median(sb)) if sb else None,
               building_setback_p10=r1(np.percentile(sb, 10)) if sb else None,
               building_share=r1(unary_union([b['poly'] for b in bl]).intersection(B).area / A, 3) if bl else 0)
    return out


def edges_table(W, B):
    G = W['graph']
    src = G['source_by_way']
    gl = {e['id']: e for e in G['edges']}
    rows = []
    for e in W['edges']:
        L = LineString(e['pts'])
        if not L.intersects(B):
            continue
        g = gl.get(e['id'], {})
        s = src.get(e['way'], {})
        rows.append(dict(id=e['id'], name=e.get('label'), cls=g.get('class'), osm_lanes=s.get('lanes_tag'), osm_oneway=s.get('oneway'),
                         lanes=e['lanes'], oneway=e['oneway'], width=e['width'], sidewalk=e['sidewalk'] if not e.get('swSide') else f"{e['sidewalk']} (one side)",
                         hidden=bool(e.get('hidden')), merged=bool(e.get('merged')), cutA=e.get('cutA'), cutB=e.get('cutB'),
                         fill_tris=len(e.get('fill') or []) // 6, len_in_box=r1(L.intersection(B).length),
                         real_width_m=r1(int(s['lanes_tag']) * LANE_M.get(g.get('class'), LANE_M_DEFAULT), 1) if s.get('lanes_tag', '') and str(s.get('lanes_tag')).isdigit() else None))
    return rows


def measure(W, B, res=0.5, full=True):
    """every metric for box B (shapely box, local)"""
    surf = [s for s in W['surf'] if s['poly'].intersects(B)]
    by = defaultdict(list)
    for s in surf:
        by[s['kind']].append(s['poly'])
    asphalt = unary_union([p for k in world.ROAD_KINDS for p in by.get(k, [])]).intersection(B)
    slabs = unary_union(by.get('road', []) + by.get('fill', []))
    should = unary_union([p for k in world.SHOULDER_KINDS for p in by.get(k, [])]).intersection(B)
    walk = unary_union(by.get('sidewalk', []) + by.get('corner', []))
    units = asphalt_units(W, B)
    cnt = count_raster([u for _, u in units], B.bounds, res)
    cell = res * res
    # disc overhang
    over = []
    for s in surf:
        if s['kind'] in ('junction', 'joint'):
            o = s['poly'].difference(slabs).intersection(B).area
            over.append((s['kind'], s['node'], o, s['poly'].area))
    cor, per, hulls = corridor(W, B)
    vis = visible_lane_area(W, B, per)
    _, per_in, _ = corridor(W, B, tol=-2.0)               # the wheel paths: lanes shrunk 2 studs from the edge
    vis_in = visible_lane_area(W, B, per_in)
    unexplained = asphalt.difference(vis)
    meaningless = asphalt.difference(cor)
    cc = count_raster([[p] for p in per.values()], B.bounds, res)
    jz = Image.new('1', (cc.shape[1], cc.shape[0]), 0)
    _draw(jz, hulls.buffer(2), B.bounds[0], B.bounds[1], res)
    jz = np.asarray(jz, bool)
    holes = vis_in.difference(asphalt.union(should).buffer(0.05)) if not vis_in.is_empty else vis_in
    parts = Counter()
    for s in surf:
        parts[s['kind']] += s.get('parts', 1)
    res_d = dict(
        bbox_local=[r1(v) for v in B.bounds], bbox_world=[r1(v) for v in (B.bounds[0] + world.ORIGIN[0], B.bounds[1], B.bounds[2] + world.ORIGIN[0], B.bounds[3])],
        area=r1(B.area, 0), asphalt=r1(asphalt.area, 0), shoulder_concrete=r1(should.area, 0),
        overlap_ge2=r1((cnt >= 2).sum() * cell, 0), overlap_ge3=r1((cnt >= 3).sum() * cell, 0),
        overlap_share_of_asphalt=r1((cnt >= 2).sum() * cell / max(asphalt.area, 1), 3),
        stacked_excess=r1(max(int(cnt.sum()) - int((cnt >= 1).sum()), 0) * cell, 0),
        discs=len(over), discs_overhanging_gt_5=sum(1 for o in over if o[2] > 5),
        disc_overhang_area=r1(sum(o[2] for o in over), 0), disc_area=r1(sum(o[3] for o in over), 0),
        fill_area=r1(unary_union(by.get('fill', [])).intersection(B).area, 0) if by.get('fill') else 0,
        apron_area=r1(unary_union(by.get('apron', [])).intersection(B).area, 0) if by.get('apron') else 0,
        lane_corridor=r1(cor.area, 0), meaningless_asphalt=r1(meaningless.area, 0),
        meaningless_share=r1(meaningless.area / max(asphalt.area, 1), 3),
        unexplained_by_visible_lanes=r1(unexplained.area, 0),
        carriageway_overlap=r1(((cc >= 2) & ~jz).sum() * cell, 0),
        visible_lane_area=r1(vis.area, 0), lane_holes=r1(holes.area, 0),
        parts_by_kind=dict(parts), parts_total=int(sum(parts.values())),
    )
    if full:
        res_d['marking_parts'] = sum(1 for m in W['marks'] if m['poly'].intersects(B))
        res_d['crossing_parts'] = sum(len(c['bars']) for c in W['crossings'] if any(b.intersects(B) for b in c['bars']))
        rows = crossing_report(W, asphalt.buffer(0.01), walk, B)
        res_d['crossings'] = crossing_summary(rows)
        res_d['crossing_rows'] = rows
        res_d['lane_lines'] = lane_line_report(W, B)
        res_d['joints'] = joints_report(W, B)
        res_d['proportions'] = proportions(W, B, asphalt)
        res_d['edges'] = edges_table(W, B)
        res_d['worst_discs'] = [dict(kind=k, node=n, overhang=r1(o), area=r1(a)) for k, n, o, a in sorted(over, key=lambda v: -v[2])[:12]]
    res_d['_geo'] = dict(asphalt=asphalt, meaningless=meaningless, unexplained=unexplained, corridor=cor, holes=holes, overlap=cnt)
    return res_d


def city(W, res=1.0, chunk=512, log=print):
    """per-chunk metrics summed over the city (raster at `res`)"""
    xs = [s['poly'].bounds for s in W['surf']]
    x0 = math.floor(min(b[0] for b in xs) / chunk); x1 = math.floor(max(b[2] for b in xs) / chunk)
    z0 = math.floor(min(b[1] for b in xs) / chunk); z1 = math.floor(max(b[3] for b in xs) / chunk)
    tree = STRtree([s['poly'] for s in W['surf']])
    tot = Counter()
    worst = []
    nch = 0
    for cx in range(x0, x1 + 1):
        for cz in range(z0, z1 + 1):
            B = box(cx * chunk, cz * chunk, (cx + 1) * chunk, (cz + 1) * chunk)
            idx = tree.query(B)
            if not len(idx):
                continue
            sub = dict(W, surf=[W['surf'][i] for i in idx])
            if not any(s['kind'] in ('road', 'fill') for s in sub['surf']):
                continue
            m = measure(sub, B, res=res, full=False)
            nch += 1
            for k in ('asphalt', 'shoulder_concrete', 'overlap_ge2', 'overlap_ge3', 'stacked_excess', 'discs', 'discs_overhanging_gt_5',
                      'disc_overhang_area', 'disc_area', 'fill_area', 'apron_area', 'lane_corridor', 'meaningless_asphalt',
                      'visible_lane_area', 'lane_holes', 'parts_total', 'carriageway_overlap', 'unexplained_by_visible_lanes'):
                tot[k] += m[k]
            worst.append((m['meaningless_asphalt'], f'{cx}_{cz}', m['overlap_ge2'], m['disc_overhang_area']))
    out = {k: r1(v, 0) for k, v in tot.items()}
    out['chunks'] = nch
    out['overlap_share_of_asphalt'] = r1(tot['overlap_ge2'] / max(tot['asphalt'], 1), 3)
    out['meaningless_share'] = r1(tot['meaningless_asphalt'] / max(tot['asphalt'], 1), 3)
    out['disc_overhang_share_of_disc_area'] = r1(tot['disc_overhang_area'] / max(tot['disc_area'], 1), 3)
    out['worst_chunks_by_meaningless'] = [dict(chunk=c, meaningless=r1(a, 0), overlap=r1(o, 0), disc_overhang=r1(d, 0))
                                          for a, c, o, d in sorted(worst, reverse=True)[:10]]
    log(f'city: {nch} chunks')
    return out


def city_lines_and_crossings(W):
    """citywide lane-line, joint and crossing metrics (vector, whole map)"""
    surf = W['surf']
    asphalt_tree = STRtree([s['poly'] for s in surf if s['kind'] in world.ROAD_KINDS])
    walk = [s['poly'] for s in surf if s['kind'] in ('sidewalk', 'corner')]
    asph = [s['poly'] for s in surf if s['kind'] in world.ROAD_KINDS]
    rows = []
    wt = STRtree(walk) if walk else None
    for c in W['crossings']:
        x, z = c['row'][0], c['row'][1]
        B = box(x - 120, z - 120, x + 120, z + 120)
        a = unary_union([asph[i] for i in asphalt_tree.query(B)]).buffer(0.01)
        wl = unary_union([walk[i] for i in wt.query(B)]) if wt is not None else None
        sub = dict(W, crossings=[c])
        rows += crossing_report(sub, a, wl, None)
    return dict(crossings=crossing_summary(rows), lane_lines=lane_line_report(W, None), joints=joints_report(W, None))


def strip_geo(d):
    return {k: v for k, v in d.items() if k != '_geo'}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--area', nargs=4, type=float, default=list(PILOT_BBOX_WORLD), help='world x0 z0 x1 z1')
    ap.add_argument('--city', action='store_true')
    ap.add_argument('--build-root')
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    bl = world.world_bbox_local(a.area)
    if a.city:
        W = world.load(a.build_root)
    else:
        W = world.load(a.build_root, bbox=bl)
    out = dict(area=strip_geo(measure(W, box(*bl))))
    if a.city:
        out['city'] = city(W)
        out['city'].update(city_lines_and_crossings(W))
    broot = world.find_build_root(a.build_root)
    path = a.out or os.path.join(broot, 'roadvis', 'analysis.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    print(json.dumps({k: v for k, v in out['area'].items() if k not in ('crossing_rows', 'edges')}, ensure_ascii=False, indent=1, default=str))
    if 'city' in out:
        print(json.dumps(out['city'], ensure_ascii=False, indent=1, default=str))
    print('wrote', path)


if __name__ == '__main__':
    main()
