"""Validate the traffic GLBs with the kit's validate.py checks (pure Python) plus the traffic rules, and write
<out>/traffic/manifest.json (separate from the main kit manifest).
  python validate_traffic.py <vis_out_dir>          # reads <dir>/traffic/*.glb and <dir>/traffic/meta/*.json
Traffic rules on top of validate.validate(): TRF_ naming, <= 2,500 tris, <= 4 MeshParts, only the four car
materials, and the footprint: the mesh must fill the client's collision box (KIND_BOX) without sticking far out of
it (x within half the box width + 0.45 for mirrors, z within half the box length + 0.3 for bumpers / steps)."""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from traffic import trf_common as T   # noqa: E402
T.install_materials()
import validate as V                  # noqa: E402
V.check_name = T.check
V.CHILD_RE = T.CHILD_RE


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', '..', 'build', 'vis_assets')
    tdir = os.path.join(out, 'traffic')
    recs = []
    for p in sorted(glob.glob(os.path.join(tdir, '*.glb'))):
        n = os.path.splitext(os.path.basename(p))[0]
        mp = os.path.join(tdir, 'meta', n + '.json')
        meta = json.load(open(mp)) if os.path.exists(mp) else None
        r = V.validate(p, meta)
        r['file'] = 'traffic/' + os.path.basename(p)
        if meta and meta.get('blender_tris') != r['tris']:
            r['warnings'].append(f'blender reported {meta.get("blender_tris")} tris, glb has {r["tris"]}')
        if r['tris'] > T.TRI_MAX:
            r['fails'].append(f'{r["tris"]} tris > traffic budget {T.TRI_MAX}')
        if len(r['parts']) > T.PARTS_MAX:
            r['fails'].append(f'{len(r["parts"])} MeshParts > {T.PARTS_MAX}')
        bad = [m for m in r['materials'] if m not in T.TRF_MATERIALS]
        if bad:
            r['fails'].append(f'non-car materials {bad}')
        if meta:
            for k in ('traffic_kind', 'footprint', 'roof_top', 'roof_z', 'taxi_sign'):
                r[k] = meta.get(k)
            W, H, L = meta['footprint']
            lo, hi = r['bbox_min'], r['bbox_max']
            if max(-lo[0], hi[0]) > W / 2 + 0.45 or max(-lo[2], hi[2]) > L / 2 + 0.3:
                r['fails'].append(f'sticks out of the {W} x {L} collision box: x {lo[0]}..{hi[0]}, z {lo[2]}..{hi[2]}')
            r['fill'] = [round((hi[0] - lo[0]) / W, 2), round((hi[2] - lo[2]) / L, 2)]
        r['ok'] = not r['fails']
        recs.append(r)
        print(f'{"OK  " if r["ok"] else "FAIL"} {n:20s} tris {r["tris"]:5d}  parts {len(r["parts"])} '
              f'({",".join(q["name"].rsplit("_", 1)[1] for q in r["parts"])})  size {r["size_studs"][0]:5.2f} x '
              f'{r["size_studs"][1]:5.2f} x {r["size_studs"][2]:5.2f}  box {r.get("footprint")}  fill {r.get("fill")}  '
              f'{"; ".join(r["fails"])}')
    summary = {'assets': len(recs), 'ok': sum(r['ok'] for r in recs), 'tris_total': sum(r['tris'] for r in recs),
               'tris_max': max((r['tris'] for r in recs), default=0),
               'units': 'studs (1 glTF unit = 1 stud), Y up, front -Z; origin = footprint centre at road level',
               'limits': {'asset_tris': T.TRI_MAX, 'meshparts': T.PARTS_MAX},
               'kind_box': {str(k): v for k, v in T.KIND_BOX.items()}}
    json.dump({'summary': summary, 'assets': recs}, open(os.path.join(tdir, 'manifest.json'), 'w'), indent=1)
    print(json.dumps(summary))
    sys.exit(0 if summary['ok'] == summary['assets'] else 1)


if __name__ == '__main__':
    main()
