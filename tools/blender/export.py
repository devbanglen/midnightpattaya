"""Asset -> Roblox-ready .glb (run inside Blender). Used by gen_buildings.py / gen_roadside.py / gen_racing.py.

Per asset:
  * the Builder's bmesh is optimised (common/optimize.py), box-UV'd (common/uv.py) and split per material into
    child meshes <Asset>_<MaterialShort> under an empty <Asset> (=> a Model with <= 4 MeshParts in Roblox, one
    material each, so every part can be tinted on its own);
  * origin: props / roof items = base centre (bbox centred in X and depth, bottom at 0);
            kit modules = bottom centre of the MOUNT plane (the face that sits on the building box), front toward
            Blender +Y = Roblox -Z, so the whole module lies at Roblox z <= 0 and modules snap edge to edge;
  * geometry is in studs, exported glTF Y-up (export_yup) => Roblox X right, Y up, -Z front, 1 unit = 1 stud;
  * no transforms on the nodes (applied), flat/smooth normals from angle, no textures (baseColorFactor only).
Writes <out>/<family>/<Asset>.glb and <out>/meta/<Asset>.json (generator facts: family, anchor, grid, collision).
"""
import json
import os
import sys
import time

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import materials as M          # noqa: E402
from common.optimize import optimise       # noqa: E402
from common.uv import box_project          # noqa: E402
from common.naming import check as check_name  # noqa: E402
from common.units import TRI_BUDGET        # noqa: E402

MIN_THICK = 0.05                            # studs

GLTF_OPTS = dict(export_format='GLB', use_selection=True, export_yup=True, export_apply=True,
                 export_materials='EXPORT', export_texcoords=True, export_normals=True, export_tangents=False,
                 export_cameras=False, export_lights=False, export_animations=False, export_skins=False,
                 export_morph=False, export_extras=False, export_image_format='NONE')


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M.make_bpy_materials()


def _clear_objects():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)


def _place_origin(bm, anchor, name):
    pts = [v.co for v in bm.verts]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    if anchor == 'base':
        off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    elif anchor == 'mount':
        if lo.y < -0.01:
            raise ValueError(f'{name}: kit module reaches behind its mount plane (min y {lo.y:.3f})')
        off = Vector(((lo.x + hi.x) / 2, 0.0, lo.z))
    elif anchor == 'pole':
        off = Vector((0.0, 0.0, lo.z))            # pole / trunk foot modelled at the origin
    elif anchor == 'corner':
        off = Vector((0.0, 0.0, lo.z))            # building corner stays at the origin
    else:
        raise ValueError(anchor)
    for v in bm.verts:
        v.co -= off


def build_and_export(builder, meta, out_dir):
    name = builder.name
    err = check_name(name)
    if err:
        raise ValueError(err)
    _clear_objects()
    bm = builder.bm
    _place_origin(bm, meta['anchor'], name)
    tris = optimise(bm)
    box_project(bm)
    if tris > TRI_BUDGET:
        raise ValueError(f'{name}: {tris} triangles > budget {TRI_BUDGET}')

    solidified, tris_out = [], 0
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    children = []
    for mi, mat in enumerate(builder.mats):
        part = bm.copy()
        bmesh.ops.delete(part, geom=[f for f in part.faces if f.material_index != mi], context='FACES')
        bmesh.ops.delete(part, geom=[v for v in part.verts if not v.link_faces], context='VERTS')
        for f in part.faces:
            f.material_index = 0
        # Roblox: "Meshes cannot be 0 thickness and must have some volume". A part that is a single flat sheet
        # (glass fill, sign panel, flat roof) gets a 0.05-stud shell toward its back.
        ext = [max(v.co[i] for v in part.verts) - min(v.co[i] for v in part.verts) for i in range(3)]
        if min(ext) < MIN_THICK:
            bmesh.ops.solidify(part, geom=part.faces[:], thickness=MIN_THICK)
            bmesh.ops.triangulate(part, faces=part.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
            part.normal_update()
            for e in part.edges:
                e.smooth = False
            solidified.append(mat)
            box_project(part)
            tris_out += len(part.faces)
        else:
            tris_out += len(part.faces)
        cname = f'{name}_{M.short(mat)}'
        me = bpy.data.meshes.new(cname)
        part.to_mesh(me)
        part.free()
        me.materials.append(bpy.data.materials[mat])
        ob = bpy.data.objects.new(cname, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = root
        children.append(ob)
    bm.free()

    fam_dir = os.path.join(out_dir, meta['family'])
    os.makedirs(fam_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, 'meta'), exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [root] + children:
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    props = bpy.ops.export_scene.gltf.get_rna_type().properties.keys()
    opts = {k: v for k, v in GLTF_OPTS.items() if k in props}
    path = os.path.join(fam_dir, f'{name}.glb')
    bpy.ops.export_scene.gltf(filepath=path, **opts)
    if tris_out > TRI_BUDGET:
        raise ValueError(f'{name}: {tris_out} triangles > budget {TRI_BUDGET}')
    meta = dict(meta, name=name, materials=list(builder.mats), blender_tris=tris_out,
                children=[c.name for c in children], solidified=solidified)
    with open(os.path.join(out_dir, 'meta', f'{name}.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return tris_out


def main(assets, family):
    """assets: list of (fn, meta) where fn() returns a Builder. CLI: blender -b -P gen_x.py -- --out DIR [--only N]"""
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = argv[argv.index('--out') + 1] if '--out' in argv else os.path.join(os.getcwd(), 'build', 'vis_assets')
    only = argv[argv.index('--only') + 1] if '--only' in argv else None
    reset_scene()
    t0 = time.time()
    n = 0
    for fn, meta in assets:
        b = fn()
        if only and only not in b.name:
            b.bm.free()
            continue
        tris = build_and_export(b, dict(meta, family=family), out)
        print(f'EXPORT {family} {b.name} tris={tris} mats={len(b.mats)}', flush=True)
        n += 1
    print(f'DONE {family}: {n} assets in {time.time() - t0:.1f}s', flush=True)
