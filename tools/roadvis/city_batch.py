"""One city batch, ready to install (OFFLINE): Studio data, the offline QA, the Studio drive paths, previews.

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py batch b001 [--art]

Writes build/roadcity/<id>/:
  roblox_rv/            ServerStorage.PattayaDataRoadVis_<id> (manifest with the probe expectation + cell modules)
  roblox_ground/        ServerStorage.PattayaDataRoadGround_<id> (manifest)
  ../noraise/PattayaDataRoadGroundNoRaise.luau   (ServerStorage.PattayaDataRoadGroundNoRaise, all batches)
  qa.json               the offline QA: today | Road B | Road B + ground (lane holes, drops, steps, spot and off-road
                        runs, the seam with the pilot, poles on islands)
  drives.json           the spot and off-road runs as TestKit packed paths (TK.drivePath(packed, {physics = true}))
  fixture.json          the replaced old parts' footprints and nearby decoys (the Luau builder test)
  top_*.png, steps_*.png    offline previews; scene_*.json for tools/roadvis/blender_preview.py
"""
import json
import os
import time

import numpy as np
import shapely
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from tools.roadvis import city, city_cli, city_export, city_ground, city_qa, ground, ground_audit, junction, shoulder_proof, world

LATERALS = (0, 14, -14, 20, -20, 24, -24)


def spot_paths(res, area, min_len=150.0, built_area=None):
    """the batch's carriageway chains that cross the box (centre path at least `min_len` studs inside it): one spot
    path per chain and direction, inside the box + 8 studs, and on into built Road B boxes next to it (the pilot): the
    seam is driven; the old roads beyond a frontier edge are not this batch's (they are today's)"""
    I = res['ideal']
    big = area.buffer(8, join_style='mitre')
    if built_area is not None and not built_area.is_empty:
        big = big.union(built_area)
    out = []
    for c in I['chains']:
        poly, Q, T, hw, s = I['rib'][c['id']]
        inside = shapely.contains_xy(area, Q[:, 0], Q[:, 1])
        if inside.sum() * 2.0 < min_len:
            continue
        m = shapely.contains_xy(big, Q[:, 0], Q[:, 1])
        # the longest run of consecutive samples inside `big`
        runs, start = [], None
        for k, v in enumerate(m):
            if v and start is None:
                start = k
            if not v and start is not None:
                runs.append((start, k - 1))
                start = None
        if start is not None:
            runs.append((start, len(m) - 1))
        a, b = max(runs, key=lambda r: r[1] - r[0])
        if b - a < 20:
            continue
        seg = Q[a:b + 1]
        for d in ('fwd',) if c['oneway'] else ('fwd', 'rev'):
            pts = seg if d == 'fwd' else seg[::-1]
            out.append(dict(chain=c['id'], name=c['name'], dir=d, pts=pts, hw=float(np.median(hw[a:b + 1]))))
    return out


def run_rows(st, paths, laterals=LATERALS, packed=False):
    rows = []
    for p in paths:
        Q, T = ground.path_frame(p['pts'])
        R = np.stack([-T[:, 1], T[:, 0]], axis=1)
        for lat in laterals:
            if abs(lat) > p['hw'] + 26:
                continue
            C = Q + R * lat
            m = ground.run_metrics(st, C, T)
            row = dict(chain=p['chain'], name=p['name'], dir=p['dir'], lateral=lat, **{k: v for k, v in m.items() if not k.startswith('_')})
            if packed:
                row['packed'] = ';'.join(f'{x + city.ORIGIN[0]:.1f},{z:.1f}' for x, z in C[::2])
            rows.append(row)
    return rows


_OBJ = {}


def furniture_rows(CW):
    if 'rows' not in _OBJ:
        _OBJ['rows'] = ground_audit.city_objects(CW.broot, CW.W, ground_audit.TerrainMask(CW.broot))[1]
    return _OBJ['rows']


def poles_on_islands(CW, res, region):
    """street furniture whose foot stands on a Road B island or in its asphalt in this batch (the leader's 2026-10-22
    flip: a NameSignPost / SignalPole on a 40-stud median island); listed, never moved"""
    rows = furniture_rows(CW)
    I = res['ideal']
    isl, S, walk = I['islands'], I['S'], I['walk']
    out = []
    for r in rows:
        if r['kind'] == 'Building' or not region.contains(Point(r['x'], r['z'])):
            continue
        p = Point(r['x'], r['z'])
        where = 'island' if isl.contains(p) else 'asphalt' if S.contains(p) else 'sidewalk' if walk.contains(p) else 'ground'
        if where in ('island', 'asphalt'):
            d_edge = round(float(S.boundary.distance(p)), 1) if where == 'asphalt' else round(float(isl.boundary.distance(p)), 1)
            out.append(dict(kind=r['kind'], world=[round(r['x'] + city.ORIGIN[0], 1), round(r['z'], 1)], on=where,
                            to_edge=d_edge, island_width=round(float(_local_width(isl, p)), 1) if where == 'island' else None))
    return sorted(out, key=lambda o: (o['on'], o['kind'], o['world']))


def _local_width(g, p):
    for q in junction.polys(g):
        if q.contains(p):
            mrr = q.minimum_rotated_rectangle
            c = np.asarray(mrr.exterior.coords)
            e = [np.hypot(*(c[i + 1] - c[i])) for i in range(2)]
            return min(e)
    return 0.0


def fixture(CW, st_before, res, area):
    """the replaced old parts with their footprint boxes (corners, world) and the old parts within 40 studs that stay
    (decoys), for the Luau test of RV.MoveReplaced(<id>)"""
    rep = {o['i'] for o in res['rep_old']}
    out = []
    for j in CW.old_tree.query(area.buffer(40)):
        o = CW.old[int(j)]
        if o['i'] in st_before['replaced_old'] and o['i'] not in rep:
            continue
        c = np.asarray(o['key'].exterior.coords)[:-1]
        out.append(dict(code=o['code'], corners=[[round(float(x) + city.ORIGIN[0], 4), round(float(z), 4)] for x, z in c],
                        replaced=o['i'] in rep))
    return out


def cmd_batch(bid, build_root=None, art=False, log=print, variant=city.DEFAULT_VARIANT):
    t0 = time.time()
    CW, plan, nr = city_cli.load(build_root, log=log)
    out = os.path.join(city_cli.out_root(build_root), bid)
    os.makedirs(out, exist_ok=True)
    # every batch before bid, then bid itself with the full ideal kept
    st, rows, results, gplans = city_cli.run_batches(CW, plan, nr, upto=bid, log=log, keep_ideal={bid}, cfg=city.VARIANTS[variant])
    if bid not in results:
        raise SystemExit(f'{bid} is not in the plan')
    res = results[bid]
    b = next(x for x in plan['batches'] if x['id'] == bid)
    BX = box(*city.wloc(b['box']))
    region = BX.buffer(200, join_style='mitre')       # the seam paths run up to 160 studs into built neighbours
    # state before this batch (for "today")
    st_before = dict(st, built=[x for x in st['built'] if x != bid],
                     replaced_old=st['replaced_old'] - {o['i'] for o in res['rep_old']},
                     replaced_pilot=st['replaced_pilot'] - {p['i'] for p in res['rep_pilot']},
                     pieces={k: v for k, v in st['pieces'].items() if k != bid})
    raised_before = [k for k in gplans if k != bid and (k == 'pilot' or k in st_before['built'])]
    g_before = city_qa.CityGround([gplans[k] for k in raised_before])
    g_after = city_qa.CityGround([gplans[k] for k in raised_before + [bid]])
    S_today = city_qa.CityState(CW, st_before, region, field=g_before)
    S_B = city_qa.CityState(CW, st, region, field=g_before)
    S_BG = city_qa.CityState(CW, st, region, field=g_after)
    # ---- Studio data
    exp = city_qa.probe_expected(S_B, res['probe_rows'])
    x = city_export.export(CW, plan, res, os.path.join(out, 'roblox_rv'), expected=exp)
    G = gplans[bid]
    gx = city_ground.export(bid, res['seq'], G, S_BG, BX, os.path.join(out, 'roblox_ground'), raised_before=raised_before,
                            neighbours=res['neighbours'])
    nx = city_ground.export_noraise(nr, os.path.join(city_cli.out_root(build_root), 'noraise', 'PattayaDataRoadGroundNoRaise.luau'))
    log(f"{bid}: Road B data {x['modules']} modules, {x['parts']} parts, replace {x['replace']} (+{x['optional']} optional); "
        f"ground {gx['counts']['written']} columns, {gx['edgeChecks']} edge checks; never-raise {nx['runs']} runs")
    # ---- offline QA
    qa = dict(note='OFFLINE static model (tools/roadvis/city_qa.py): collision tops, terrain height field, buildings as walls; '
                   'not physics', batch=bid, box=b['box'], studio_data=dict(rv=x, ground=gx, noraise=nx))
    pl = box(*city.wloc(city.PILOT_BOX_WORLD))
    shared = BX.buffer(0.5).intersection(pl.buffer(0.5))
    seam_band = shared.buffer(40.0, join_style='mitre') if not shared.is_empty else Polygon()
    # built Road B next to the batch (the pilot, earlier city batches): the box edges toward them are seams; the
    # other edges are frontier edges (old roads go on beyond them until that neighbour is built)
    built_boxes = [pl] + [box(*city.wloc(st['pieces'][k]['box'])) for k in st_before['pieces']]
    built_area = unary_union(built_boxes)
    frontier_edges = BX.exterior.difference(built_area.buffer(0.5))
    frontier_in = BX.intersection(frontier_edges.buffer(20, join_style='mitre')) if not frontier_edges.is_empty else Polygon()
    core = BX.difference(frontier_in)
    for name, S_ in (('today', S_today), ('B', S_B), ('B_ground', S_BG)):
        r = dict(lanes_core=city_qa.lane_check(S_, res['ideal'], core),
                 lanes_frontier_in=city_qa.lane_check(S_, res['ideal'], frontier_in) if not frontier_in.is_empty else None,
                 lanes_box=city_qa.lane_check(S_, res['ideal'], BX),
                 lanes_pilot_seam=city_qa.lane_check(S_, res['ideal'], seam_band) if not seam_band.is_empty else None,
                 grid_box=ground.grid_steps(S_, BX, res=1.0),
                 grid_pilot_seam=ground.grid_steps(S_, seam_band, res=1.0) if not seam_band.is_empty else None,
                 edges=ground.edge_report(ground.edge_samples(S_, BX)),
                 road_edges=ground.edge_report(ground.edge_samples(S_, BX, road_only=True), S_, rays=False))
        sp = spot_paths(res, BX, built_area=built_area.intersection(BX.buffer(160, join_style="mitre")))
        rr = run_rows(S_, sp)
        r['spot'] = ground.summarize_runs(rr)
        # the runs a car can drive: no wheel inside a building (a lateral beyond a soi with no sidewalk can run into one)
        r['spot_clear'] = ground.summarize_runs([x for x in rr if not x['blocked']])
        r['spot2_pilot_path_B'] = ground.summarize_runs(ground.spot2_runs(S_))
        orr = ground.offroad_runs(S_, city_qa.pseudo_pilot(res, BX))
        r['offroad'] = {k: ground.summarize_runs([o for o in orr if o['set'] == k]) for k, _ in ground.OFFROAD_SETS}
        r['offroad_rows'] = orr
        qa[name] = r
        log(f"{name}: lane holes core {r['lanes_core']['holes']} of {r['lanes_core']['samples']}, frontier band "
            f"{r['lanes_frontier_in']['holes'] if r['lanes_frontier_in'] else '-'}, box {r['lanes_box']['holes']} of {r['lanes_box']['samples']} (pilot seam "
            f"{r['lanes_pilot_seam']['holes'] if r['lanes_pilot_seam'] else '-'}), drops {r['lanes_box']['drops']}; grid >=1.5 "
            f"{r['grid_box']['drop_cells']} (max {r['grid_box']['max_step']}); road->ground max {r['road_edges'].get('road_to_ground_max_step')}; "
            f"spot runs {r['spot']['runs']} drop {r['spot'].get('with_drop')} climb {r['spot'].get('with_climb')} (clear of "
            f"buildings {r['spot_clear'].get('runs')}: drop {r['spot_clear'].get('with_drop')} climb {r['spot_clear'].get('with_climb')}); spot2 "
            f"{r['spot2_pilot_path_B'].get('with_drop')}/{r['spot2_pilot_path_B'].get('with_climb')}; offroad "
            + '; '.join(f"{k} {v['runs']} runs drop {v.get('with_drop')} climb {v.get('with_climb')}" for k, v in r['offroad'].items()))
    qa['probe_expected'] = exp
    qa['poles'] = poles_on_islands(CW, res, BX.buffer(40))
    qa['pilot_band_completion'] = dict(region_area=round(res['region'].area, 1),
                                       asphalt=round(res['comp_geom'][1].area, 1), sidewalk=round(res['comp_geom'][2].area, 1),
                                       support=round(res['comp_geom'][5].area, 1))
    qa['replaced'] = dict(old=len(res['rep_old']), pilot=len(res['rep_pilot']), frontier=sum(f['n'] for f in res['rep_front']),
                          uncertain_old=len(res.get('unc_old', ())), uncertain_pilot=len(res.get('unc_pilot', ())))
    qa['secs'] = round(time.time() - t0, 1)
    rows_drives = []
    sp = spot_paths(res, BX, built_area=built_area.intersection(BX.buffer(160, join_style="mitre")))
    for r_ in run_rows(S_BG, sp, packed=True):
        # Studio drives: every spot run the static model sees clear of buildings, at 70 studs/s; the lane-0 runs at 100 too
        rows_drives.append(dict(set='spot', studio=r_['blocked'] == 0, speeds=[70, 100] if r_['lateral'] == 0 else [70],
                                **{k: v for k, v in r_.items()}))
    ex = ground.offroad_runs(S_BG, city_qa.pseudo_pilot(res, BX), paths=True)
    for e in ex:
        # off the road onto the raised ground and back: 35 (the leader's off-road loop) and 70 (ground -> road)
        rows_drives.append(dict(set='offroad_' + e['set'], studio=True, speeds=[35, 70] if e['set'] == 'harness' else [35],
                                name=e['name'], dir=e['dir'], lateral=e['lateral'], deepest=e['world'],
                                drops=e['drops'], climbs=e['climbs'], min_up=e['min_up'], packed=e['packed']))
    with open(os.path.join(out, 'drives.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(note='OFFLINE static model. Car centre paths (world x, z) for TK.drivePath(packed, {physics = true, '
                            'speed = s}) for every s in speeds of the runs with studio = true; docs/ROAD_B_CITY_ROLLOUT.md',
                       batch=bid, runs=[dict(id=i + 1, **r_) for i, r_ in enumerate(rows_drives)]), f, indent=1)
    with open(os.path.join(out, 'fixture.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(batch=bid, box=b['box'], old=fixture(CW, st_before, res, BX)), f)
    with open(os.path.join(out, 'qa.json'), 'w', encoding='utf-8') as f:
        json.dump(qa, f, indent=1, default=str)
    if art:
        from tools.roadvis import city_view
        city_view.previews(CW, plan, st_before, st, res, gplans, raised_before, out, log=log)
    log(f'{bid}: wrote {out} ({round(time.time() - t0, 1)} s)')
    return qa
