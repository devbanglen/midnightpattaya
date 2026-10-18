"""Validate exported .glb files from the glTF JSON chunk + binary accessors (pure Python 3, no Blender needed) and
write manifest.json. Every number in docs/BLENDER_PIPELINE.md comes from this file's output.

  python validate.py <vis_out_dir>            # reads <dir>/{buildings,roadside,racing}/*.glb and <dir>/meta/*.json

Checks per asset (FAIL stops nothing but is listed and makes the exit code 1):
  * naming rule (common/naming.py), child names <Asset>_<Short> with a shared material
  * triangles per child mesh (= Roblox MeshPart) <= 20,000 (Roblox hard limit) and per asset <= 10,000 (budget)
  * <= 4 materials, every material name in the shared list (common/materials.py)
  * bbox in studs (glTF Y-up = Roblox axes) and origin rule: base anchor -> centred in X/Z, bottom at y 0;
    mount anchor (kit modules) -> centred in X, bottom at y 0, all geometry at z <= 0 (front toward -Z)
  * no node transforms other than identity (so Studio pivots = exported origin)
  * normals present on every primitive, indices present, mode = triangles
  * every MeshPart has some thickness on all axes (>= 0.01 studs; Roblox rejects 0-thickness meshes)
"""
import glob
import hashlib
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common.naming import check as check_name, CHILD_RE  # noqa: E402
from common.materials import MATERIALS                   # noqa: E402
from common.units import TRI_BUDGET, TRI_HARD_LIMIT, MAX_MATERIALS  # noqa: E402

COMP = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
TOL = 0.02


def read_glb(path):
    data = open(path, 'rb').read()
    magic, ver, length = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67, f'{path}: not a GLB'
    off, js, binc = 12, None, b''
    while off < length:
        clen, ctype = struct.unpack_from('<II', data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode('utf8'))
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc, data


def accessor(js, binc, idx):
    a = js['accessors'][idx]
    bv = js['bufferViews'][a['bufferView']]
    fmt, size = COMP[a['componentType']]
    n = NCOMP[a['type']]
    stride = bv.get('byteStride') or size * n
    base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    return [struct.unpack_from('<' + fmt * n, binc, base + i * stride) for i in range(a['count'])]


def qmat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def node_xf(node):
    """returns (fn(point)->point, is_identity)"""
    if 'matrix' in node:
        m = node['matrix']
        ident = all(abs(m[i] - (1 if i in (0, 5, 10, 15) else 0)) < 1e-6 for i in range(16))
        return (lambda p: tuple(m[r] * p[0] + m[4 + r] * p[1] + m[8 + r] * p[2] + m[12 + r] for r in range(3))), ident
    t = node.get('translation', [0, 0, 0])
    r = node.get('rotation', [0, 0, 0, 1])
    s = node.get('scale', [1, 1, 1])
    R = qmat(r)
    ident = (max(map(abs, t)) < 1e-6 and abs(r[3]) > 1 - 1e-6 and max(abs(v - 1) for v in s) < 1e-6)

    def f(p):
        q = (p[0] * s[0], p[1] * s[1], p[2] * s[2])
        return tuple(R[i][0] * q[0] + R[i][1] * q[1] + R[i][2] * q[2] + t[i] for i in range(3))
    return f, ident


def validate(path, meta):
    js, binc, raw = read_glb(path)
    name = os.path.splitext(os.path.basename(path))[0]
    fails, warns = [], []
    e = check_name(name)
    if e:
        fails.append(e)
    scene = js['scenes'][js.get('scene', 0)]
    roots = [js['nodes'][i] for i in scene['nodes']]
    if len(roots) != 1 or roots[0].get('name') != name:
        fails.append(f'expected one root node named {name}, got {[r.get("name") for r in roots]}')
    parts, lo, hi, total, mats = [], [math.inf] * 3, [-math.inf] * 3, 0, set()

    def walk(ni, xfs):
        nonlocal total
        node = js['nodes'][ni]
        f, ident = node_xf(node)
        if not ident:
            warns.append(f'node {node.get("name")} has a transform')
        xfs = xfs + [f]
        if 'mesh' in node:
            mesh = js['meshes'][node['mesh']]
            ptris, pmats = 0, []
            plo, phi = [math.inf] * 3, [-math.inf] * 3
            for prim in mesh['primitives']:
                if prim.get('mode', 4) != 4:
                    fails.append(f'{node.get("name")}: primitive mode {prim.get("mode")} is not triangles')
                if 'indices' not in prim:
                    fails.append(f'{node.get("name")}: no indices')
                    continue
                if 'NORMAL' not in prim['attributes']:
                    fails.append(f'{node.get("name")}: no normals')
                if 'TEXCOORD_0' not in prim['attributes']:
                    warns.append(f'{node.get("name")}: no UVs')
                ptris += js['accessors'][prim['indices']]['count'] // 3
                mname = js['materials'][prim['material']]['name'] if 'material' in prim else None
                pmats.append(mname)
                for p in accessor(js, binc, prim['attributes']['POSITION']):
                    for fx in reversed(xfs):
                        p = fx(p)
                    for i in range(3):
                        plo[i], phi[i] = min(plo[i], p[i]), max(phi[i], p[i])
            nm = node.get('name', '')
            if not CHILD_RE.match(nm) or not nm.startswith(name + '_'):
                fails.append(f'child mesh name {nm} breaks the rule <Asset>_<Short>')
            if len(set(pmats)) != 1:
                fails.append(f'{nm}: {len(set(pmats))} materials in one MeshPart')
            if min(phi[i] - plo[i] for i in range(3)) < 0.01:
                fails.append(f'{nm}: zero thickness (Roblox: meshes cannot be 0 thickness)')
            if ptris > TRI_HARD_LIMIT:
                fails.append(f'{nm}: {ptris} tris > Roblox limit {TRI_HARD_LIMIT}')
            for i in range(3):
                lo[i], hi[i] = min(lo[i], plo[i]), max(hi[i], phi[i])
            total += ptris
            mats.update(pmats)
            parts.append({'name': nm, 'material': pmats[0] if pmats else None, 'tris': ptris,
                          'size': [round(phi[i] - plo[i], 3) for i in range(3)],
                          'centre': [round((phi[i] + plo[i]) / 2, 3) for i in range(3)]})
        for c in node.get('children', []):
            walk(c, xfs)

    for ni in scene['nodes']:
        walk(ni, [])
    if total > TRI_BUDGET:
        fails.append(f'{total} tris > asset budget {TRI_BUDGET}')
    if len(mats) > MAX_MATERIALS:
        fails.append(f'{len(mats)} materials > {MAX_MATERIALS}')
    bad = [m for m in mats if m not in MATERIALS]
    if bad:
        fails.append(f'materials not in the shared list: {bad}')
    anchor = (meta or {}).get('anchor')
    if anchor is None:
        warns.append('no meta json (anchor unknown)')
    if abs(lo[1]) > TOL:
        fails.append(f'bottom at y {lo[1]:.3f}, expected 0')
    if anchor in ('base', 'mount') and abs(lo[0] + hi[0]) > TOL:
        fails.append(f'not centred in X ({lo[0]:.3f}..{hi[0]:.3f})')
    if anchor == 'base' and abs(lo[2] + hi[2]) > TOL:
        fails.append(f'base anchor not centred in Z ({lo[2]:.3f}..{hi[2]:.3f})')
    if anchor == 'mount' and hi[2] > TOL:
        fails.append(f'kit module crosses its mount plane: max z {hi[2]:.3f} > 0')
    if anchor == 'pole' and not (lo[0] <= 0 <= hi[0] and lo[2] <= 0 <= hi[2]):
        fails.append('pole anchor: origin outside the footprint')
    if anchor == 'corner' and not (lo[0] < 0 < hi[0] and lo[2] < 0 < hi[2]):
        fails.append('corner piece does not straddle the building corner at the origin')
    size = [round(hi[i] - lo[i], 3) for i in range(3)]
    rec = {
        'name': name, 'file': os.path.relpath(path, os.path.dirname(os.path.dirname(path))).replace('\\', '/'),
        'bytes': len(raw), 'sha1': hashlib.sha1(raw).hexdigest(),
        'tris': total, 'materials': sorted(mats), 'parts': parts,
        'bbox_min': [round(v, 3) for v in lo], 'bbox_max': [round(v, 3) for v in hi], 'size_studs': size,
        'ok': not fails, 'fails': fails, 'warnings': sorted(set(warns)),
    }
    for k in ('family', 'group', 'kind', 'anchor', 'grid', 'collision', 'can_collide', 'note'):
        if meta and k in meta:
            rec[k] = meta[k]
    return rec


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'build', 'vis_assets')
    recs = []
    for fam in ('buildings', 'roadside', 'racing'):
        for p in sorted(glob.glob(os.path.join(out, fam, '*.glb'))):
            n = os.path.splitext(os.path.basename(p))[0]
            mp = os.path.join(out, 'meta', n + '.json')
            meta = json.load(open(mp)) if os.path.exists(mp) else None
            r = validate(p, meta)
            if meta and meta.get('blender_tris') != r['tris']:
                r['warnings'].append(f'blender reported {meta.get("blender_tris")} tris, glb has {r["tris"]}')
            recs.append(r)
            print(f'{"OK  " if r["ok"] else "FAIL"} {n:34s} tris {r["tris"]:5d}  parts {len(r["parts"])}  '
                  f'size {r["size_studs"][0]:7.2f} x {r["size_studs"][1]:7.2f} x {r["size_studs"][2]:7.2f}  '
                  f'{"; ".join(r["fails"])}')
    summary = {
        'assets': len(recs), 'ok': sum(r['ok'] for r in recs),
        'tris_total': sum(r['tris'] for r in recs), 'tris_max': max((r['tris'] for r in recs), default=0),
        'by_family': {f: sum(1 for r in recs if r.get('family') == f) for f in ('buildings', 'roadside', 'racing')},
        'units': 'studs (1 glTF unit = 1 stud), Y up, front -Z',
        'limits': {'asset_tris_budget': TRI_BUDGET, 'meshpart_tris_hard': TRI_HARD_LIMIT, 'materials': MAX_MATERIALS},
    }
    json.dump({'summary': summary, 'assets': recs}, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
    print(json.dumps(summary))
    sys.exit(0 if summary['ok'] == summary['assets'] else 1)


if __name__ == '__main__':
    main()
