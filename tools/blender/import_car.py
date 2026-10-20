"""Imported single-mesh car (e.g. an AI-generated GLB) -> Roblox body GLB + spinning wheel GLBs + wheel layout.

Run headless on the GPU box (docs/CAR_IMPORT_RED_SPORTS.md):

  blender -b --factory-startup --python-exit-code 1 -P import_car.py -- build <in.glb> <detect.json> <out_dir> \
          [--id red_sports] [--body-tris 18000] [--wheel-tris 2000] [--tex 1024] [--wheel-tex 512]
  blender -b --factory-startup --python-exit-code 1 -P import_car.py -- qa <in.glb> <detect.json> <out_dir> <qa_dir> \
          [--id red_sports]

<detect.json> comes from tools/gpu/car_import_wheels.py (front direction, scale, wheel cylinders in the pipeline
frame N: X right, Y up, front -Z, metres). Blender is Z-up: Blender (bx, by, bz) = N (x, -z, y), so the front is Blender +Y and every wheel axle is Blender X.

build writes into <out_dir>:
  <id>.glb               body: wheels cut out, a dark double-sided disc behind each wheel arch, decimated to
                         <= --body-tris, texture downscaled to --tex, centred on its own bounding box
  <id>_wheel_L.glb       the front-left tyre + rim, origin = axle centre (bbox centre), axle along X, so a rotation
  <id>_wheel_R.glb       about X spins it; decimated to <= --wheel-tris; own baked --wheel-tex texture
  <id>_wheels.json       same schema as the other cars (+ extra keys): radius, width, rim, centres FL FR RL RR in
                         metres in body space (front = -Z)
  <id>_build.json        triangle counts and the numbers behind them
qa writes PNGs (Workbench, textured) into <qa_dir>: before/after side, top, 3/4 and end views, wheel close-ups.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
MODE = argv[0]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CAR_ID = opt('--id', 'red_sports')
RF = 1.03          # a face belongs to a wheel when all its verts are within RF * r of the axle ...
XM = 0.03          # ... and within [x_in - XM, x_out + XM] (metres) across


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def import_source(path, det):
    """Import the source GLB and move it into the pipeline frame (Blender axes)."""
    bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
    activate(ob)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if ob.parent:
        ob.parent = None
    R = Matrix.Diagonal((-1.0, -1.0, 1.0, 1.0)) if det['yaw180'] else Matrix.Identity(4)   # 180 deg about up
    c = det['centre']
    T = Matrix.Translation((-c[0], c[2], -c[1])) @ Matrix.Scale(det['scale'], 4) @ R
    ob.data.transform(T)
    ob.name = CAR_ID + '_src'
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except RuntimeError:
        pass
    return ob


def wheel_b(w):
    """Wheel from detect.json (frame N) -> Blender: centre, radius, inner/outer |x|, side sign."""
    return {'c': Vector((w['x'], -w['z'], w['y'])), 'r': w['r'], 'x_in': w['x_in'], 'x_out': w['x_out'],
            's': 1.0 if w['x'] > 0 else -1.0}


def arrays(me):
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get('co', co)
    lt = np.empty(len(me.polygons), np.int32)
    me.polygons.foreach_get('loop_total', lt)
    assert (lt == 3).all(), 'expects a triangle mesh'
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get('vertex_index', vi)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get('uv', uv)
    return co.reshape(-1, 3), vi.reshape(-1, 3), uv.reshape(-1, 3, 2)


def wheel_masks(co, faces, wheels):
    masks = {}
    for k, w in wheels.items():
        rad = np.hypot(co[:, 1] - w['c'].y, co[:, 2] - w['c'].z)
        sx = co[:, 0] * w['s']
        inside = (rad <= w['r'] * RF) & (sx >= w['x_in'] - XM) & (sx <= w['x_out'] + XM)
        masks[k] = inside[faces].all(1)
    return masks


def image_np(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def sample(tex, uv):
    H, W = tex.shape[:2]
    x = np.clip((uv[..., 0] % 1.0 * (W - 1)).astype(int), 0, W - 1)
    y = np.clip((uv[..., 1] % 1.0 * (H - 1)).astype(int), 0, H - 1)
    return tex[y, x, :3]


def subset(src, keep, name):
    ob = src.copy()
    ob.data = src.data.copy()
    ob.name = ob.data.name = name
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    dele = [f for f, k in zip(bm.faces, keep) if not k]
    bmesh.ops.delete(bm, geom=dele, context='FACES')
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def add_disc(ob, centre, x, radius, uv, y_clip=None, n=28):
    """Double-sided flat disc in the plane x = const (normal +-X), optionally clipped below z = y_clip."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    for flip in (False, True):
        ring = []
        for i in range(n):
            a = 2 * math.pi * i / n
            y, z = centre.y + radius * math.cos(a), centre.z + radius * math.sin(a)
            if y_clip is not None:
                z = max(z, y_clip)
            ring.append(bm.verts.new((x, y, z)))
        mid = bm.verts.new((x, centre.y, max(centre.z, y_clip if y_clip is not None else centre.z)))
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            if (a.co - b.co).length < 1e-6:
                continue
            f = bm.faces.new((mid, b, a) if flip else (mid, a, b))
            for lp in f.loops:
                lp[uvl].uv = uv
    bm.to_mesh(me)
    bm.free()


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def decimate(ob, target):
    activate(ob)
    for _ in range(3):
        n = tri_count(ob)
        if n <= target:
            break
        m = ob.modifiers.new('dec', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = target / n * 0.995
        m.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.quads_convert_to_tris()
    bpy.ops.object.mode_set(mode='OBJECT')
    return tri_count(ob)


def smooth(ob, angle=40):
    activate(ob)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    except (AttributeError, RuntimeError, TypeError):
        bpy.ops.object.shade_smooth()


def bake_wheel(ob, size, out_dir):
    """Give the wheel its own compact texture: new UVs (smart project), bake the atlas colour into them."""
    me = ob.data
    me.uv_layers[0].name = 'src'
    me.uv_layers.new(name='bake')
    me.uv_layers.active = me.uv_layers['bake']
    activate(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
    bpy.ops.object.mode_set(mode='OBJECT')
    src_mat = ob.active_material
    mat = src_mat.copy()
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    nt = mat.node_tree
    tex = next(n for n in nt.nodes if n.type == 'TEX_IMAGE')
    uvn = nt.nodes.new('ShaderNodeUVMap')
    uvn.uv_map = 'src'
    nt.links.new(uvn.outputs['UV'], tex.inputs['Vector'])
    emit = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(tex.outputs['Color'], emit.inputs['Color'])
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    nt.links.new(emit.outputs['Emission'], out.inputs['Surface'])
    img = bpy.data.images.new(ob.name + '_tex', size, size)
    tn = nt.nodes.new('ShaderNodeTexImage')
    tn.image = img
    for n in nt.nodes:
        n.select = False
    tn.select = True
    nt.nodes.active = tn
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 4
    sc.cycles.device = 'CPU'
    activate(ob)
    bpy.ops.object.bake(type='EMIT', margin=6, use_clear=True, uv_layer='bake')
    path = os.path.join(out_dir, ob.name + '_tex.png')
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    # final material: the baked image on the new UVs only
    m2 = bpy.data.materials.new(ob.name + '_mat')
    m2.use_nodes = True
    bsdf = next(n for n in m2.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    t2 = m2.node_tree.nodes.new('ShaderNodeTexImage')
    t2.image = bpy.data.images.load(path)
    m2.node_tree.links.new(t2.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.5
    bsdf.inputs['Metallic'].default_value = 0.0
    me.uv_layers.remove(me.uv_layers['src'])
    me.uv_layers.active = me.uv_layers['bake']
    me.uv_layers['bake'].active_render = True
    ob.data.materials.clear()
    ob.data.materials.append(m2)


def export(ob, path):
    activate(ob)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                              export_apply=True, export_texcoords=True, export_normals=True,
                              export_materials='EXPORT', export_animations=False)


def to_n(v):
    """Blender -> frame N (glTF / Roblox axes)."""
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


def bounds_np(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    return co.min(0), co.max(0)


# ----------------------------------------------------------------------------------------------------------------
def build():
    src_glb, det_path, out_dir = argv[1], argv[2], argv[3]
    body_tris = opt('--body-tris', 18000, int)
    wheel_tris = opt('--wheel-tris', 2000, int)
    tex_size = opt('--tex', 1024, int)
    wheel_tex = opt('--wheel-tex', 512, int)
    os.makedirs(out_dir, exist_ok=True)
    det = json.load(open(det_path))
    reset()
    src = import_source(src_glb, det)
    wheels = {k: wheel_b(w) for k, w in det['wheels'].items()}
    co, faces, uv = arrays(src.data)
    masks = wheel_masks(co, faces, wheels)
    info = {'source_tris': int(len(faces)), 'wheel_faces_cut': {k: int(m.sum()) for k, m in masks.items()}}
    print('wheel faces', info['wheel_faces_cut'])

    img = next(n for n in src.active_material.node_tree.nodes if n.type == 'TEX_IMAGE').image
    tex = image_np(img)
    # dark texel for the arch discs: the darkest tread faces (outer ring, below the axle) whose corners are dark too
    best = None
    for k, w in wheels.items():
        m = masks[k]
        cen = co[faces[m]].mean(1)
        rad = np.hypot(cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z)
        tread = (rad > 0.9 * w['r']) & (cen[:, 2] < w['c'].z)
        tuv = uv[m][tread]
        lum = sample(tex, tuv).mean(-1).max(1)
        if len(lum):
            i = int(np.argmin(lum))
            if best is None or lum[i] < best[0]:
                best = (float(lum[i]), tuv[i].mean(0))
    dark_uv = Vector(best[1]) if best else Vector((0.0, 0.0))
    info['arch_disc_texel_lum'] = round(best[0], 3) if best else None
    # rim colour: outer face of the wheel, inside 55 % of the radius
    rims = []
    for k, w in wheels.items():
        m = masks[k]
        cen = co[faces[m]].mean(1)
        rad = np.hypot(cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z)
        outer = (rad < 0.55 * w['r']) & (cen[:, 0] * w['s'] > (w['x_in'] + w['x_out']) / 2)
        rims.append(sample(tex, uv[m][outer].mean(1)))
    rim = (np.median(np.concatenate(rims), 0) * 255).round().astype(int).tolist()

    # --- wheels: cut each, measure; keep FL as the left mesh and FR as the right mesh -----------------------------
    layout = {}
    wheel_obs = {}
    for k in ('FL', 'FR', 'RL', 'RR'):
        w = wheels[k]
        ob = subset(src, masks[k], f'{CAR_ID}_wheel_{k}')
        lo, hi = bounds_np(ob)
        ctr = Vector(((lo[0] + hi[0]) / 2, w['c'].y, w['c'].z))
        co_w = np.empty(len(ob.data.vertices) * 3)
        ob.data.vertices.foreach_get('co', co_w)
        co_w = co_w.reshape(-1, 3)
        r_cut = float(np.percentile(np.hypot(co_w[:, 1] - ctr.y, co_w[:, 2] - ctr.z), 99.5))
        layout[k] = {'centre_b': ctr, 'r': r_cut, 'w': float(hi[0] - lo[0]),
                     'bbox_yz_centre_err': float(max(abs((lo[1] + hi[1]) / 2 - ctr.y), abs((lo[2] + hi[2]) / 2 - ctr.z)))}
        if k in ('FL', 'FR'):
            wheel_obs[k] = ob
        else:
            bpy.data.objects.remove(ob)
    print('wheel cut', {k: (round(v['r'], 4), round(v['w'], 4), round(v['bbox_yz_centre_err'], 4)) for k, v in layout.items()})

    side_info = {}
    for k, ob in wheel_obs.items():
        side = 'L' if k == 'FL' else 'R'
        L = layout[k]
        ob.data.transform(Matrix.Translation(-L['centre_b']))
        before = tri_count(ob)
        # inner cap: closes the tyre's open back (the cut leaves whatever the arch hid); inside the tyre volume
        lo, hi = bounds_np(ob)
        s = wheels[k]['s']
        x_inner = (hi[0] if s < 0 else lo[0]) + s * 0.01    # 1 cm in from the inner bound, toward the outer face
        add_disc(ob, Vector((0, 0, 0)), x_inner, L['r'] * 0.96, dark_uv, n=24)
        after = decimate(ob, wheel_tris)
        smooth(ob, 50)
        # roundness of the decimated outline: tread radii spread
        co_w = np.empty(len(ob.data.vertices) * 3)
        ob.data.vertices.foreach_get('co', co_w)
        co_w = co_w.reshape(-1, 3)
        rr = np.hypot(co_w[:, 1], co_w[:, 2])
        outer = rr > 0.9 * L['r']
        ang = np.degrees(np.arctan2(co_w[outer, 2], co_w[outer, 1]))
        hist = np.histogram(ang, bins=36, range=(-180, 180))[0]
        side_info[side] = {'from': k, 'tris_cut': before, 'tris': after,
                           'tread_radius_min_max': [round(float(rr[outer].min()), 4), round(float(rr[outer].max()), 4)],
                           'empty_10deg_sectors': int((hist == 0).sum())}
        ob.name = ob.data.name = f'{CAR_ID}_wheel_{side}'
        try:
            bake_wheel(ob, wheel_tex, out_dir)
            side_info[side]['texture'] = f'baked {wheel_tex}x{wheel_tex}'
        except Exception as e:      # keep the shared atlas if the bake fails
            print('bake failed, wheel keeps the atlas:', repr(e))
            side_info[side]['texture'] = 'atlas (bake failed)'
        wheel_obs[k] = ob
    info['wheels'] = side_info

    # --- body ----------------------------------------------------------------------------------------------------
    allw = np.zeros(len(faces), bool)
    for m in masks.values():
        allw |= m
    body = subset(src, ~allw, CAR_ID)
    bpy.data.objects.remove(src)
    info['body_tris_cut'] = tri_count(body)
    disc_tris = 0
    for k, w in wheels.items():
        x = w['s'] * (w['x_in'] - 0.012)
        add_disc(body, w['c'], x, w['r'] * 1.3, dark_uv, y_clip=w['c'].z - 0.55 * w['r'])
        disc_tris += 2 * 28
    info['body_tris'] = decimate(body, body_tris)
    info['arch_disc_tris_approx'] = disc_tris
    smooth(body, 40)
    # texture -> tex_size (after the wheel bakes read the full-size atlas)
    if max(img.size) > tex_size:
        img.scale(tex_size, tex_size)
    img.pack()
    info['body_texture'] = list(img.size)
    lo, hi = bounds_np(body)
    shift = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))
    body.data.transform(Matrix.Translation(-shift))
    size_b = hi - lo

    out = {
        'size': [round(float(size_b[0]), 4), round(float(size_b[2]), 4), round(float(size_b[1]), 4)],
        'radius': round(float(np.mean([layout[k]['r'] for k in layout])), 4),
        'width': round(float(np.mean([layout[k]['w'] for k in layout])), 4),
        'rim': rim,
        'wheels': {k: to_n(layout[k]['centre_b'] - shift) for k in ('FL', 'FR', 'RL', 'RR')},
        'per_wheel': {k: {'r': round(layout[k]['r'], 4), 'w': round(layout[k]['w'], 4)} for k in layout},
        'wheel_meshes': {'L': f'{CAR_ID}_wheel_L.glb (cut from FL)', 'R': f'{CAR_ID}_wheel_R.glb (cut from FR)'},
        'front': '-Z', 'units': 'metres, body space (centre of the body mesh bounding box)',
    }
    json.dump(out, open(os.path.join(out_dir, f'{CAR_ID}_wheels.json'), 'w'), indent=1)
    export(body, os.path.join(out_dir, f'{CAR_ID}.glb'))
    for k, ob in wheel_obs.items():
        export(ob, os.path.join(out_dir, ob.name + '.glb'))
    info['size_m'] = out['size']
    json.dump(info, open(os.path.join(out_dir, f'{CAR_ID}_build.json'), 'w'), indent=1)
    print(json.dumps(info, indent=1))
    print(json.dumps(out, indent=1))


# ----------------------------------------------------------------------------------------------------------------
def setup_render(res):
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.show_backface_culling = True     # Roblox culls back faces
    sc.world = bpy.data.worlds.new('w')
    sc.world.color = (0.82, 0.84, 0.88)
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x, sc.render.resolution_y = res
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = 'ORTHO'
    return cam


def shoot(cam, objs, path, az, el, pad=1.1):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, (hi - lo).length
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = centre + d * size * 3
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    sc = bpy.context.scene
    r = sc.render.resolution_x / sc.render.resolution_y
    cam.data.ortho_scale = size * pad * max(1.0, 1 / r) * 0.9
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def grid(paths, cols, out):
    tiles = []
    for p in paths:
        im = bpy.data.images.load(p)
        tiles.append(np.array(im.pixels[:], np.float32).reshape(im.size[1], im.size[0], 4))
        bpy.data.images.remove(im)
    h, w = tiles[0].shape[:2]
    rows = []
    for i in range(0, len(tiles), cols):
        row = tiles[i:i + cols] + [np.ones((h, w, 4), np.float32)] * (cols - len(tiles[i:i + cols]))
        rows.append(np.concatenate(row, 1))
    sheet = np.concatenate(rows[::-1], 0)       # Blender images are bottom-up
    img = bpy.data.images.new('sheet', sheet.shape[1], sheet.shape[0], alpha=True)
    img.pixels.foreach_set(sheet.ravel())
    img.filepath_raw, img.file_format = out, 'PNG'
    img.save()
    for p in paths:
        os.remove(p)


# views: (name, azimuth, elevation). Front of the car = Blender +Y; azimuth 0 looks from -Y (the rear)
VIEWS = [('side_left', -90, 0), ('side_right', 90, 0), ('top', 0, 89.9), ('34_front_left', -140, 22),
         ('front', 180, 0), ('34_rear_right', 40, 22)]


def qa():
    src_glb, det_path, out_dir, qa_dir = argv[1], argv[2], argv[3], argv[4]
    os.makedirs(qa_dir, exist_ok=True)
    det = json.load(open(det_path))
    lay = json.load(open(os.path.join(out_dir, f'{CAR_ID}_wheels.json')))
    # before: the source mesh in the pipeline frame
    reset()
    src = import_source(src_glb, det)
    cam = setup_render((900, 560))
    paths = []
    for name, az, el in VIEWS:
        p = os.path.join(qa_dir, f'_b_{name}.png')
        shoot(cam, [src], p, az, el)
        paths.append(p)
    grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_before.png'))

    # after: body + the wheel GLBs placed at the layout centres (L on FL/RL, R on FR/RR)
    reset()
    bpy.ops.import_scene.gltf(filepath=os.path.join(out_dir, f'{CAR_ID}.glb'))
    body = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    objs = list(body)
    wheel_src = {}
    for side in ('L', 'R'):
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(out_dir, f'{CAR_ID}_wheel_{side}.glb'))
        wheel_src[side] = next(o for o in bpy.context.scene.objects if o not in before and o.type == 'MESH')
    for k, c in lay['wheels'].items():
        side = 'L' if k.endswith('L') else 'R'
        o = wheel_src[side] if k.startswith('F') else wheel_src[side].copy()
        if o.name not in bpy.context.scene.collection.objects and not o.users_collection:
            bpy.context.scene.collection.objects.link(o)
        o.location = Vector((c[0], -c[2], c[1]))
        objs.append(o)
    cam = setup_render((900, 560))
    paths = []
    for name, az, el in VIEWS:
        p = os.path.join(qa_dir, f'_a_{name}.png')
        shoot(cam, objs, p, az, el)
        paths.append(p)
    grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_after.png'))
    # body alone (arch discs, cut quality)
    paths = []
    for name, az, el in [('side_left', -90, 0), ('34_front_left', -140, 22), ('under_34', -130, -25), ('front', 180, 0)]:
        p = os.path.join(qa_dir, f'_c_{name}.png')
        shoot(cam, body, p, az, el)
        paths.append(p)
    grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_body_only.png'))
    # wheels alone: outer face, inner face, tread, and the L wheel turned 30 deg about X (spin axis check)
    cam = setup_render((520, 520))
    for o in objs:
        o.hide_render = True
    paths = []
    for side in ('L', 'R'):
        w = wheel_src[side]
        w.hide_render = False
        keep = w.location.copy()
        w.location = Vector((0, 0, 0))
        outer_az = -90 if side == 'L' else 90
        for az, el in ((outer_az, 0), (-outer_az, 0), (0, 0)):
            p = os.path.join(qa_dir, f'_w_{side}_{az}_{el}.png')
            shoot(cam, [w], p, az, el, pad=1.15)
            paths.append(p)
        w.rotation_euler = (math.radians(30), 0, 0)
        p = os.path.join(qa_dir, f'_w_{side}_spin30.png')
        shoot(cam, [w], p, outer_az, 0, pad=1.15)
        paths.append(p)
        w.rotation_euler = (0, 0, 0)
        w.location = keep
        w.hide_render = True
    grid(paths, 4, os.path.join(qa_dir, f'{CAR_ID}_wheels.png'))


if MODE == 'build':
    build()
elif MODE == 'qa':
    qa()
else:
    raise SystemExit('mode must be build or qa')
