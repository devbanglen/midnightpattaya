"""Merged kit modules (mesh-opt): wide (W bays) x floor-band (H floors) assets built from the validated kit .glb files.
Pure Python 3 (stdlib only, no bpy): the kit geometry, UVs, normals and materials are copied cell by cell, nothing is
re-modelled, so a merged asset looks exactly like W x H kit modules placed edge to edge. Runs locally or on the box.

  python tools/blender/gen_merged.py [--kit build/vis_assets] [--request build/vis_assets/merged/request.json]
                                     [--out build/vis_assets/merged] [--twice]

Input:  request.json (written by tools/mapgen/VisMesh.py: name, base, w, h per merged asset the sample needs) and
        <kit>/buildings/<base>.glb + <kit>/manifest.json (the Blender export, validate.py).
Output: <out>/<Name>.glb, <out>/manifest.json (validate.py records + base / w / h / glass_alt_cells / checks),
        <out>/upload_patch.json (what the leader uploads: name, file, bytes, sha1, size, tris, MeshParts).
Asset rules (docs/BLENDER_PIPELINE.md): 1 unit = 1 stud, glTF Y-up = Roblox axes, front -Z; one root node <Name>
with one child mesh per MeshPart <Name>_<Short> (no node transforms); a kit module keeps the mount-anchor origin
(bottom centre of the mount plane, all geometry at z <= 0), a corner keeps the corner origin.
Cell (i, k), i = 0..W-1 bays along +X, k = 0..H-1 floors up: offset ((i - (W-1)/2) x 7.142857, k x 8.571429, 0).
Glass: with split_glass and W x H >= 2 the cells' MP_Glass is split into two MeshParts, <Name>_Glass and
<Name>_GlassAlt (floor(n/2) cells, picked by a fixed hash), so the builder can light the two halves independently
and lit panes keep varying inside a tile (MaterialLibrary / NightNeon act per MeshPart).
Checks (exit code 1 on any): validate.validate (naming, tris <= 10,000 per asset and <= 20,000 per MeshPart, materials,
origin rule, thickness), triangles == base x W x H, every part bbox == the analytic union of the base part bboxes over
its cells (+- 0.002 studs), asset bbox likewise; with --twice the whole set is generated a second time into a temp
folder and every byte compared (deterministic export).
"""
import hashlib
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate import read_glb, accessor, validate          # noqa: E402  (read-only reuse of the kit validator)
from common.units import MODULE_W, FLOOR_H, TRI_BUDGET       # noqa: E402

GENERATOR = 'MIDNIGHT PATTAYA tools/blender/gen_merged.py (cells copied from the Khronos glTF Blender I/O kit export)'
TOL = 0.002


def read_asset(path):
    """base kit glb -> (root name, [child dict(name, short, material(json), pos, nrm, uv, idx)])"""
    js, binc, _ = read_glb(path)
    scene = js['scenes'][js.get('scene', 0)]
    root = js['nodes'][scene['nodes'][0]]
    kids = []
    for ni in root.get('children', []):
        node = js['nodes'][ni]
        for k in ('translation', 'rotation', 'scale', 'matrix'):
            if k in node:
                raise ValueError(f'{path}: node {node["name"]} has a transform ({k})')
        mesh = js['meshes'][node['mesh']]
        if len(mesh['primitives']) != 1:
            raise ValueError(f'{path}: {node["name"]} has {len(mesh["primitives"])} primitives')
        pr = mesh['primitives'][0]
        at = pr['attributes']
        kids.append({'name': node['name'], 'short': node['name'][len(root['name']) + 1:],
                     'material': js['materials'][pr['material']],
                     'pos': accessor(js, binc, at['POSITION']), 'nrm': accessor(js, binc, at['NORMAL']),
                     'uv': accessor(js, binc, at['TEXCOORD_0']) if 'TEXCOORD_0' in at else None,
                     'idx': [t[0] for t in accessor(js, binc, pr['indices'])]})
    return root['name'], kids


def f32(v):
    return struct.unpack('<f', struct.pack('<f', v))[0]


def alt_cells(name, w, h):
    """the floor(n/2) cells whose glass goes to GlassAlt: fixed hash order, so it is irregular but deterministic"""
    cells = [(i, k) for k in range(h) for i in range(w)]
    seed = zlib.crc32(name.encode('ascii'))
    key = lambda c: (zlib.crc32(struct.pack('<III', seed, c[0], c[1])), c)
    return sorted(sorted(cells, key=key)[:len(cells) // 2])


def write_glb(path, name, children):
    """children: [(child name, material json, pos, nrm, uv, idx)] -> glb with the kit's node layout"""
    js = {'asset': {'generator': GENERATOR, 'version': '2.0'}, 'scene': 0,
          'scenes': [{'name': 'Scene', 'nodes': [len(children)]}],
          'nodes': [], 'materials': [], 'meshes': [], 'accessors': [], 'bufferViews': [], 'buffers': []}
    blob = bytearray()
    mat_index = {}

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        js['bufferViews'].append({'buffer': 0, 'byteLength': len(data), 'byteOffset': len(blob), 'target': target})
        blob.extend(data)
        return len(js['bufferViews']) - 1

    for ci, (cname, mat, pos, nrm, uv, idx) in enumerate(children):
        mk = json.dumps(mat, sort_keys=True)
        if mk not in mat_index:
            mat_index[mk] = len(js['materials'])
            js['materials'].append(mat)
        attrs = {}
        data = b''.join(struct.pack('<3f', *p) for p in pos)
        lo = [min(p[a] for p in pos) for a in range(3)]
        hi = [max(p[a] for p in pos) for a in range(3)]
        js['accessors'].append({'bufferView': view(data, 34962), 'componentType': 5126, 'count': len(pos),
                                'max': hi, 'min': lo, 'type': 'VEC3'})
        attrs['POSITION'] = len(js['accessors']) - 1
        js['accessors'].append({'bufferView': view(b''.join(struct.pack('<3f', *n) for n in nrm), 34962),
                                'componentType': 5126, 'count': len(nrm), 'type': 'VEC3'})
        attrs['NORMAL'] = len(js['accessors']) - 1
        if uv is not None:
            js['accessors'].append({'bufferView': view(b''.join(struct.pack('<2f', *t) for t in uv), 34962),
                                    'componentType': 5126, 'count': len(uv), 'type': 'VEC2'})
            attrs['TEXCOORD_0'] = len(js['accessors']) - 1
        big = len(pos) > 65535
        js['accessors'].append({'bufferView': view(struct.pack(('<%dI' if big else '<%dH') % len(idx), *idx), 34963),
                                'componentType': 5125 if big else 5123, 'count': len(idx), 'type': 'SCALAR'})
        js['meshes'].append({'name': cname, 'primitives': [{'attributes': attrs, 'indices': len(js['accessors']) - 1,
                                                            'material': mat_index[mk]}]})
        js['nodes'].append({'mesh': ci, 'name': cname})
    js['nodes'].append({'children': list(range(len(children))), 'name': name})
    while len(blob) % 4:
        blob.append(0)
    js['buffers'].append({'byteLength': len(blob)})
    jb = json.dumps(js, separators=(',', ':'), sort_keys=False).encode('utf8')
    while len(jb) % 4:
        jb += b' '
    total = 12 + 8 + len(jb) + 8 + len(blob)
    out = struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(jb), 0x4E4F534A) + jb + \
        struct.pack('<II', len(blob), 0x004E4942) + bytes(blob)
    with open(path, 'wb') as f:
        f.write(out)


def build(req, kit_dir, kit_man, out_dir, split_glass):
    name, base, w, h = req['name'], req['base'], req['w'], req['h']
    ka = kit_man[base]
    bname, kids = read_asset(os.path.join(kit_dir, ka['file']))
    assert bname == base, (bname, base)
    corner = ka.get('anchor') == 'corner'
    if corner and w != 1:
        raise ValueError(f'{name}: a corner merges vertically only')
    pitch_y = FLOOR_H                                          # floor bands: mid modules / corner mids only
    if abs(ka['size_studs'][1] - FLOOR_H) > 0.01 and h > 1:
        raise ValueError(f'{name}: base {base} is {ka["size_studs"][1]} tall, floor bands need {FLOOR_H:.3f}')
    alt = set(alt_cells(name, w, h)) if split_glass and w * h >= 2 else set()
    cells = [(i, k) for k in range(h) for i in range(w)]
    children, expect = [], {}
    for kid in kids:
        groups = [(kid['short'], [c for c in cells if not (kid['material']['name'] == 'MP_Glass' and c in alt)])]
        if kid['material']['name'] == 'MP_Glass' and alt:
            groups.append((kid['short'] + 'Alt', sorted(alt, key=lambda c: (c[1], c[0]))))
        for short, cl in groups:
            pos, nrm, uv, idx = [], [], [], []
            lo, hi = [math.inf] * 3, [-math.inf] * 3
            plo = [min(p[a] for p in kid['pos']) for a in range(3)]
            phi = [max(p[a] for p in kid['pos']) for a in range(3)]
            for (i, k) in cl:
                dx = (i - (w - 1) / 2) * MODULE_W
                dy = k * pitch_y
                base_i = len(pos)
                pos += [(f32(p[0] + dx), f32(p[1] + dy), p[2]) for p in kid['pos']]
                nrm += kid['nrm']
                if kid['uv'] is not None:
                    uv += kid['uv']
                idx += [base_i + t for t in kid['idx']]
                for a, d in ((0, dx), (1, dy), (2, 0.0)):
                    lo[a] = min(lo[a], plo[a] + d)
                    hi[a] = max(hi[a], phi[a] + d)
            cname = f'{name}_{short}'
            children.append((cname, kid['material'], pos, nrm, uv if kid['uv'] is not None else None, idx))
            expect[cname] = {'size': [hi[a] - lo[a] for a in range(3)], 'centre': [(hi[a] + lo[a]) / 2 for a in range(3)],
                             'tris': len(idx) // 3}
    path = os.path.join(out_dir, f'{name}.glb')
    write_glb(path, name, children)
    meta = {k: ka[k] for k in ('family', 'group', 'kind', 'anchor', 'collision', 'can_collide') if k in ka}
    meta['grid'] = {'width_bays': w, 'floors': h, 'module_w': round(MODULE_W, 4), 'height_studs': round(FLOOR_H, 4)}
    meta['note'] = f'{w} x {h} cells of {base} (gen_merged.py); ' + (ka.get('note') or '')
    rec = validate(path, meta)
    rec['file'] = 'merged/' + os.path.basename(path)
    # own checks: triangles and bboxes against the analytic union of the base cells
    fails = rec['fails']
    if rec['tris'] != ka['tris'] * w * h:
        fails.append(f'tris {rec["tris"]} != base {ka["tris"]} x {w * h}')
    if rec['tris'] > TRI_BUDGET:
        fails.append(f'tris {rec["tris"]} > {TRI_BUDGET}')
    got = {p['name']: p for p in rec['parts']}
    if set(got) != set(expect):
        fails.append(f'parts {sorted(got)} != expected {sorted(expect)}')
    for cn, e in expect.items():
        g = got.get(cn)
        if g and max(abs(g['size'][a] - e['size'][a]) for a in range(3)) > TOL:
            fails.append(f'{cn}: size {g["size"]} != analytic {[round(v, 3) for v in e["size"]]}')
        if g and max(abs(g['centre'][a] - e['centre'][a]) for a in range(3)) > TOL:
            fails.append(f'{cn}: centre {g["centre"]} != analytic {[round(v, 3) for v in e["centre"]]}')
    blo, bhi = ka['bbox_min'], ka['bbox_max']
    xlo = blo[0] - (w - 1) / 2 * MODULE_W
    xhi = bhi[0] + (w - 1) / 2 * MODULE_W
    yhi = bhi[1] + (h - 1) * pitch_y
    want_lo, want_hi = [xlo, blo[1], blo[2]], [xhi, yhi, bhi[2]]
    if max(abs(rec['bbox_min'][a] - want_lo[a]) for a in range(3)) > 0.005 or \
            max(abs(rec['bbox_max'][a] - want_hi[a]) for a in range(3)) > 0.005:
        fails.append(f'bbox {rec["bbox_min"]}..{rec["bbox_max"]} != analytic {want_lo}..{want_hi}')
    rec['ok'] = not fails
    rec.update(base=base, w=w, h=h, glass_alt_cells=[list(c) for c in sorted(alt, key=lambda c: (c[1], c[0]))],
               meshparts=len(rec['parts']), base_meshparts=len(ka['parts']))
    return rec


def run(kit_dir, req_path, out_dir):
    req = json.load(open(req_path, encoding='utf-8'))
    kit_man = {a['name']: a for a in json.load(open(os.path.join(kit_dir, 'manifest.json'), encoding='utf-8'))['assets']}
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):
        if f.endswith('.glb'):
            os.remove(os.path.join(out_dir, f))
    recs = []
    for r in sorted(req['assets'], key=lambda r: r['name']):
        rec = build(r, kit_dir, kit_man, out_dir, req.get('split_glass', True))
        recs.append(rec)
        print(f'{"OK  " if rec["ok"] else "FAIL"} {rec["name"]:34s} {r["w"]}x{r["h"]} of {r["base"]:24s} tris {rec["tris"]:5d}  '
              f'MeshParts {rec["meshparts"]} (base {rec["base_meshparts"]} x {r["w"] * r["h"]} = '
              f'{rec["base_meshparts"] * r["w"] * r["h"]})  size {rec["size_studs"]}  {"; ".join(rec["fails"])}')
    summary = {'assets': len(recs), 'ok': sum(r['ok'] for r in recs), 'tris_total': sum(r['tris'] for r in recs),
               'tris_max': max((r['tris'] for r in recs), default=0), 'bytes_total': sum(r['bytes'] for r in recs),
               'meshparts_total': sum(r['meshparts'] for r in recs),
               'kit_manifest_sha1': hashlib.sha1(open(os.path.join(kit_dir, 'manifest.json'), 'rb').read()).hexdigest(),
               'units': 'studs (1 glTF unit = 1 stud), Y up, front -Z'}
    json.dump({'summary': summary, 'assets': recs}, open(os.path.join(out_dir, 'manifest.json'), 'w', encoding='utf-8',
                                                          newline='\n'), indent=1)
    patch = {'comment': 'mesh-opt merged kit assets to upload (Open Cloud, assetType Model, model/gltf-binary, one per '
                        'file); then add name = Model asset id to ServerStorage.VisAssetsManifest. Sizes in studs.',
             'assets': [{'name': r['name'], 'file': 'build/vis_assets/' + r['file'], 'bytes': r['bytes'], 'sha1': r['sha1'],
                         'size_studs': r['size_studs'], 'tris': r['tris'],
                         'meshparts': {p['name']: p['size'] for p in r['parts']}} for r in recs]}
    json.dump(patch, open(os.path.join(out_dir, 'upload_patch.json'), 'w', encoding='utf-8', newline='\n'), indent=1)
    return recs, summary


def main():
    argv = sys.argv[1:]

    def arg(k, d):
        return argv[argv.index(k) + 1] if k in argv else d
    root = os.path.abspath(os.path.join(HERE, '..', '..'))
    kit = arg('--kit', os.path.join(root, 'build', 'vis_assets'))
    req = arg('--request', os.path.join(kit, 'merged', 'request.json'))
    out = arg('--out', os.path.join(kit, 'merged'))
    recs, summary = run(kit, req, out)
    rc = 0 if summary['ok'] == summary['assets'] else 1
    if '--twice' in argv:
        tmp = tempfile.mkdtemp(prefix='gen_merged_')
        try:
            recs2, _ = run(kit, req, tmp)
            diff = [a['name'] for a, b in zip(recs, recs2) if a['sha1'] != b['sha1']]
            diff += [f for f in ('manifest.json', 'upload_patch.json')
                     if open(os.path.join(out, f), 'rb').read() != open(os.path.join(tmp, f), 'rb').read()]
            print(f'determinism: second run {"identical" if not diff else "DIFFERS: " + ", ".join(diff)} '
                  f'({len(recs2)} glb + manifest + upload_patch)')
            rc = rc or (1 if diff else 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(summary))
    sys.exit(rc)


if __name__ == '__main__':
    main()
