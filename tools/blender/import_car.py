"""Imported car GLB(s) -> Roblox body GLB + four spinning wheel GLBs + wheel layout + QA.

Run headless on the GPU box (docs/CAR_IMPORT_RED_SPORTS.md), always as
  blender -b --factory-startup --python-exit-code 1 -P import_car.py -- <mode> ...

Modes
  build <in.glb> <detect.json> <out_dir> [--id ID] [--body-tris 18000] [--wheel-tris 2000] [--tex 1024]
        [--wheel-tex 512]
      ONE fused mesh (Tripo-style: body + tyres + rims in one mesh). <detect.json> from
      tools/gpu/car_import_wheels.py (front, scale, wheel cylinders). Every wheel is cut out of the body along its
      cylinder (tyre + rim + hub, the real design), the arch gets a dark disc, everything is decimated.
  build_parts <body.glb> <wheel.glb> <parts.json> <out_dir> [same options]
      Separate inputs (e.g. Meshy: a body without wheels + ONE wheel). <parts.json> (frame N, metres):
        {"front_source_axis": "+z"|"-z", "length": 4.5, "radius": 0.38,
         "wheels": {"FL": [x, y, z], "FR": [...], "RL": [...], "RR": [...]},
         "wheel_outer": "+x"|"-x"   (which side of the wheel file is the outer face once its axle is along X),
         "arch_discs": false}
      The wheel's axle = its thinnest bounding-box axis. It is exported once as <ID>_wheel_L (outer face -X); the
      game turns it 180 deg for the right side (RaceCarServer), so one upload covers all four.
  qa <out_dir> <qa_dir> [--src <in.glb> <detect.json>] [--id ID]
      Renders (Workbench, textured, back faces culled like Roblox) and the numeric checks in <qa_dir>/<ID>_qa.json:
      wheel alignment / symmetry, arch clearance, suspension travel and steering sweeps against the body, spin axis
      and direction, triangle counts, textures, collision setup.

Frames: N = the pipeline frame (X right, Y up, front -Z, metres; = Roblox axes before the importer's 180 deg yaw).
Blender is Z-up: Blender (bx, by, bz) = N (x, -z, y), so the front is Blender +Y and every axle is Blender X.

Outputs in <out_dir>:
  <ID>.glb                    body, centred on its bounding box, <= --body-tris, texture <= --tex
  <ID>_wheel_<FL|FR|RL|RR>.glb (build) / <ID>_wheel_L.glb (build_parts): origin = axle centre = bounding-box
                              centre, axle along X (a rotation about X spins it), <= --wheel-tris, own baked texture
  <ID>_wheels.json            radius, width, rim, centres FL FR RL RR in metres in body space (front = -Z) + extras
  <ID>_build.json             triangle counts and the numbers behind them
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
WHEELS = ('FL', 'FR', 'RL', 'RR')
IMAGE_FORMAT = opt('--image-format', 'PNG')   # PNG (like the other cars) or JPEG (smaller GLBs, 3 PBR maps)
RF = 1.015         # a face belongs to a wheel when all its verts are within RF * r of the axle ...
XM = 0.03          # ... and within [x_in - XM, x_out + XM] (metres) across
DISC_IN = 0.06     # arch disc: this far (m) toward the car centre from the wheel's inner face
# game numbers (RaceCarServer / CarController) for the QA sweeps
BODY_LENGTH_STUDS = 16
SUSPENSION_REST, SAG, STEER_DEG = 1.6, 0.45, 28
REST_EXT = SUSPENSION_REST * (1 - SAG)
CHASSIS_STUDS = (7, 1.6, 15)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def import_mesh(path, name):
    """Import a GLB, join all its meshes into one object with identity transform; returns it."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in new:
        if o.type != 'MESH':
            bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except RuntimeError:
        pass
    ob.name = name
    return ob


def rot_b(rot):
    """Rotation given in glTF axes (3x3, source -> N) as a Blender-axes 4x4: C R C^T with Blender = C glTF."""
    C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    return (C @ Matrix(rot) @ C.transposed()).to_4x4()


def det_rot(det):
    return det['R'] if 'R' in det else ([[-1, 0, 0], [0, 1, 0], [0, 0, -1]] if det['yaw180'] else
                                        [[1, 0, 0], [0, 1, 0], [0, 0, 1]])


def to_frame(ob, rot, scale=None, centre_n=None, length=None):
    """Move a source mesh into frame N (Blender axes): rotation (glTF axes 3x3), scale, centre."""
    ob.data.transform(rot_b(rot))
    lo, hi = bounds_np(ob)
    if scale is None:
        scale = length / (hi[1] - lo[1])
    ob.data.transform(Matrix.Scale(scale, 4))
    if centre_n is None:
        lo, hi = bounds_np(ob)
        cb = (lo + hi) / 2
    else:
        cb = np.array((centre_n[0], -centre_n[2], centre_n[1]))
    ob.data.transform(Matrix.Translation(Vector(-cb)))
    return scale, cb


def wheel_b(w):
    """Wheel from detect.json (frame N) -> Blender: centre, radius, inner/outer |x|, side sign."""
    return {'c': Vector((w['x'], -w['z'], w['y'])), 'r': w['r'], 'x_in': w['x_in'], 'x_out': w['x_out'],
            's': 1.0 if w['x'] > 0 else -1.0}


def verts_np(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3)


def bounds_np(ob):
    co = verts_np(ob)
    return co.min(0), co.max(0)


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


def base_color_node(mat):
    """The image node feeding the Principled BSDF's Base Color (not the normal / metallic-roughness maps)."""
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    stack = [l.from_node for l in bsdf.inputs['Base Color'].links]
    while stack:
        n = stack.pop()
        if n.type == 'TEX_IMAGE':
            return n
        for i in n.inputs:
            stack += [l.from_node for l in i.links]
    return next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')


def tex_image(ob):
    return base_color_node(ob.active_material).image


def image_role(mat, im):
    """Names of the BSDF inputs an image feeds (Base Color / Roughness / Metallic / Normal), following links."""
    roles, stack = set(), [n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image == im]
    seen = set()
    while stack:
        n = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        for o in n.outputs:
            for l in o.links:
                if l.to_node.type == 'BSDF_PRINCIPLED':
                    roles.add(l.to_socket.name)
                else:
                    stack.append(l.to_node)
    return sorted(roles)


def all_images(mat):
    return [n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image]


def image_np(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


def sample(tex, uv):
    H, W = tex.shape[:2]
    x = np.clip((uv[..., 0] % 1.0 * (W - 1)).astype(int), 0, W - 1)
    y = np.clip((uv[..., 1] % 1.0 * (H - 1)).astype(int), 0, H - 1)
    return tex[y, x, :3]


def wheel_masks(co, faces, uv, tex, wheels):
    """Faces inside each wheel cylinder, minus body-paint fragments of the arch lip at the tyre's outer edge."""
    masks = {}
    for k, w in wheels.items():
        rad = np.hypot(co[:, 1] - w['c'].y, co[:, 2] - w['c'].z)
        sx = co[:, 0] * w['s']
        inside = (rad <= w['r'] * RF) & (sx >= w['x_in'] - XM) & (sx <= w['x_out'] + XM)
        m = inside[faces].all(1)
        idx = np.nonzero(m)[0]
        cen = co[faces[idx]].mean(1)
        crad = np.hypot(cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z)
        col = sample(tex, uv[idx].mean(1))
        paint = (col[:, 0] > 0.18) & (col[:, 0] > 2.2 * col[:, 1]) & (col[:, 0] > 2.2 * col[:, 2])
        m[idx[(crad > 0.82 * w['r']) & paint]] = False      # body paint over the tyre (arch lip) stays body
        # arch lip / liner strips hugging the tyre face the axle (a tread faces away from it): they stay body
        t = co[faces[idx]]
        nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        radial = np.stack([np.zeros(len(idx)), cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z], 1) / (crad[:, None] + 1e-12)
        m[idx[(crad > 0.97 * w['r']) & ((nrm * radial).sum(1) < -0.3)]] = False
        masks[k] = drop_small_parts(m, faces, 0.02)
    return masks


def drop_small_parts(mask, faces, frac):
    """Clear mask faces that belong to connected pieces (shared vertices) smaller than frac of the masked faces."""
    idx = np.nonzero(mask)[0]
    f = faces[idx]
    verts, inv = np.unique(f, return_inverse=True)
    inv = inv.reshape(-1, 3)
    lab = np.arange(len(verts))
    for _ in range(500):                       # label propagation: each face pulls its verts to the min label
        fl = lab[inv].min(1)
        new = lab.copy()
        np.minimum.at(new, inv.ravel(), np.repeat(fl, 3))
        new = new[new]                         # pointer jumping
        if (new == lab).all():
            break
        lab = new
    flab = lab[inv[:, 0]]
    ids, counts = np.unique(flab, return_counts=True)
    small = ids[counts < frac * len(idx)]
    out = mask.copy()
    out[idx[np.isin(flab, small)]] = False
    return out


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
    count = 0
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
            count += 1
            for lp in f.loops:
                lp[uvl].uv = uv
    bm.to_mesh(me)
    bm.free()
    return count


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def decimate(ob, target):
    activate(ob)
    for _ in range(4):
        n = tri_count(ob)
        if n <= target:
            break
        m = ob.modifiers.new('dec', 'DECIMATE')
        m.decimate_type = 'COLLAPSE'
        m.ratio = target / n * 0.99
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
    mat = ob.active_material.copy()
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    nt = mat.node_tree
    tex = base_color_node(mat)
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
    ob.data.validate(clean_customdata=False)
    activate(ob)
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_yup=True,
                              export_apply=True, export_texcoords=True, export_normals=True,
                              export_materials='EXPORT', export_animations=False,
                              export_image_format='JPEG' if IMAGE_FORMAT == 'JPEG' else 'AUTO',
                              export_jpeg_quality=90)


def to_n(v):
    """Blender -> frame N (glTF / Roblox axes)."""
    return [round(float(v[0]), 4), round(float(v[2]), 4), round(float(-v[1]), 4)]


def roundness(ob, r):
    co = verts_np(ob)
    rr = np.hypot(co[:, 1], co[:, 2])
    outer = rr > 0.9 * r
    ang = np.degrees(np.arctan2(co[outer, 2], co[outer, 1]))
    hist = np.histogram(ang, bins=36, range=(-180, 180))[0]
    return {'tread_radius_min_max': [round(float(rr[outer].min()), 4), round(float(rr[outer].max()), 4)],
            'empty_10deg_sectors': int((hist == 0).sum())}


def finish_wheel(ob, key, r, dark_uv, opts, out_dir, cap_x=None):
    """ob: wheel with its origin on the axle centre. Optional inner cap, decimate, bake, name."""
    info = {'tris_cut': tri_count(ob)}
    if cap_x is not None and dark_uv is not None:
        add_disc(ob, Vector((0, 0, 0)), cap_x, r * 0.96, dark_uv, n=24)
    info['tris'] = decimate(ob, opts['wheel_tris'])
    smooth(ob, 50)
    info.update(roundness(ob, r))
    ob.name = ob.data.name = f'{CAR_ID}_wheel_{key}'
    if opts['wheel_tex'] > 0:
        try:
            bake_wheel(ob, opts['wheel_tex'], out_dir)
            info['texture'] = [opts['wheel_tex'], opts['wheel_tex']]
        except Exception as e:      # keep the shared atlas if the bake fails
            print('bake failed, wheel keeps the source atlas:', repr(e))
            info['texture'] = 'source atlas (bake failed)'
    return info


def finish_body(body, img, opts, info):
    info['body_tris'] = decimate(body, opts['body_tris'])
    smooth(body, 40)
    if img is not None:
        # every map of the body material (base colour, and for PBR sources normal + metallic-roughness) -> <= tex
        info['body_textures'] = {}
        for im in all_images(body.active_material):
            if max(im.size) > opts['tex']:
                im.scale(opts['tex'], opts['tex'])
            im.file_format = opts['image_format']
            im.pack()
            kind = image_role(body.active_material, im)
            info['body_textures'][im.name] = {'size': list(im.size), 'kind': kind}
        info['body_texture'] = list(img.size)
    lo, hi = bounds_np(body)
    shift = (lo + hi) / 2
    body.data.transform(Matrix.Translation(Vector(-shift)))
    return shift, hi - lo


def write_outputs(out_dir, body, wheel_obs, centres_b, per_wheel, rim, size_b, shift, info, extra):
    lay = {
        'size': [round(float(size_b[0]), 4), round(float(size_b[2]), 4), round(float(size_b[1]), 4)],
        'radius': round(float(np.mean([per_wheel[k]['r'] for k in per_wheel])), 4),
        'width': round(float(np.mean([per_wheel[k]['w'] for k in per_wheel])), 4),
        'rim': rim,
        'wheels': {k: to_n(Vector(centres_b[k]) - Vector(shift)) for k in WHEELS},
        'per_wheel': per_wheel,
        'wheel_meshes': {k: ob.name + '.glb' for k, ob in wheel_obs.items()},
        'front': '-Z', 'units': 'metres, body space (centre of the body mesh bounding box)',
    }
    lay.update(extra)
    json.dump(lay, open(os.path.join(out_dir, f'{CAR_ID}_wheels.json'), 'w'), indent=1)
    export(body, os.path.join(out_dir, f'{CAR_ID}.glb'))
    for ob in wheel_obs.values():
        export(ob, os.path.join(out_dir, ob.name + '.glb'))
    info['size_m'] = lay['size']
    json.dump(info, open(os.path.join(out_dir, f'{CAR_ID}_build.json'), 'w'), indent=1)
    print(json.dumps(info, indent=1))
    print(json.dumps(lay, indent=1))


def options():
    return {'body_tris': opt('--body-tris', 18000, int), 'wheel_tris': opt('--wheel-tris', 2000, int),
            'tex': opt('--tex', 1024, int), 'wheel_tex': opt('--wheel-tex', 512, int), 'image_format': IMAGE_FORMAT}


# ----------------------------------------------------------------------------------------------------------------
def build():
    """One fused mesh: cut the four wheels out along their cylinders."""
    src_glb, det_path, out_dir = argv[1], argv[2], argv[3]
    o = options()
    os.makedirs(out_dir, exist_ok=True)
    det = json.load(open(det_path))
    reset()
    src = import_mesh(src_glb, CAR_ID + '_src')
    to_frame(src, det_rot(det), scale=det['scale'], centre_n=det['centre'])
    wheels = {k: wheel_b(w) for k, w in det['wheels'].items()}
    img = tex_image(src)
    tex = image_np(img)
    co, faces, uv = arrays(src.data)
    masks = wheel_masks(co, faces, uv, tex, wheels)
    info = {'source_tris': int(len(faces)), 'wheel_faces_cut': {k: int(m.sum()) for k, m in masks.items()},
            'front_source_axis': det.get('front_source_axis')}
    print('wheel faces', info['wheel_faces_cut'])

    # dark texel for the arch discs and wheel caps: the darkest tread face (outer ring, below the axle)
    best = None
    for k, w in wheels.items():
        m = masks[k]
        cen = co[faces[m]].mean(1)
        rad = np.hypot(cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z)
        tuv = uv[m][(rad > 0.9 * w['r']) & (cen[:, 2] < w['c'].z)]
        lum = sample(tex, tuv).mean(-1).max(1)
        if len(lum):
            i = int(np.argmin(lum))
            if best is None or lum[i] < best[0]:
                best = (float(lum[i]), tuv[i].mean(0))
    dark_uv = Vector(best[1]) if best else None
    info['dark_texel_lum'] = round(best[0], 3) if best else None
    # rim colour: outer face of the wheel, inside 55 % of the radius
    rims = []
    for k, w in wheels.items():
        m = masks[k]
        cen = co[faces[m]].mean(1)
        rad = np.hypot(cen[:, 1] - w['c'].y, cen[:, 2] - w['c'].z)
        outer = (rad < 0.55 * w['r']) & (cen[:, 0] * w['s'] > (w['x_in'] + w['x_out']) / 2)
        rims.append(sample(tex, uv[m][outer].mean(1)))
    rim = (np.median(np.concatenate(rims), 0) * 255).round().astype(int).tolist()

    # wheels: cut, origin on the axle (x = bbox middle), cap, decimate, bake
    centres, per_wheel, wheel_obs, inner_x = {}, {}, {}, {}
    info['wheels'] = {}
    for k in WHEELS:
        w = wheels[k]
        ob = subset(src, masks[k], f'{CAR_ID}_cut_{k}')
        lo, hi = bounds_np(ob)
        ctr = Vector(((lo[0] + hi[0]) / 2, w['c'].y, w['c'].z))
        cw = verts_np(ob)
        r_cut = float(np.percentile(np.hypot(cw[:, 1] - ctr.y, cw[:, 2] - ctr.z), 99.5))
        yz_err = float(max(abs((lo[1] + hi[1]) / 2 - ctr.y), abs((lo[2] + hi[2]) / 2 - ctr.z)))
        inner_x[k] = hi[0] if w['s'] < 0 else lo[0]
        centres[k] = ctr
        per_wheel[k] = {'r': round(r_cut, 4), 'w': round(float(hi[0] - lo[0]), 4), 'bbox_yz_vs_axle_m': round(yz_err, 4)}
        ob.data.transform(Matrix.Translation(-ctr))
        cap = inner_x[k] - ctr.x + w['s'] * 0.01         # 1 cm in from the inner bound, toward the outer face
        info['wheels'][k] = finish_wheel(ob, k, r_cut, dark_uv, o, out_dir, cap_x=cap)
        wheel_obs[k] = ob
    print('wheels', json.dumps(per_wheel))

    # body: everything else + a dark double-sided disc behind each arch (no see-through)
    allw = np.zeros(len(faces), bool)
    for m in masks.values():
        allw |= m
    body = subset(src, ~allw, CAR_ID)
    bpy.data.objects.remove(src)
    info['body_tris_cut'] = tri_count(body)
    disc_x = {}
    info['arch_disc_tris'] = 0
    if dark_uv is not None:
        for k, w in wheels.items():
            disc_x[k] = inner_x[k] - w['s'] * DISC_IN
            info['arch_disc_tris'] += add_disc(body, w['c'], disc_x[k], w['r'] * 1.15, dark_uv,
                                               y_clip=w['c'].z - 0.55 * w['r'])
    shift, size_b = finish_body(body, img, o, info)
    write_outputs(out_dir, body, wheel_obs, centres, per_wheel, rim, size_b, shift, info,
                  {'arch_disc_x': {k: round(float(x - shift[0]), 4) for k, x in disc_x.items()}})


def build_parts():
    """Separate body (no wheels) + one wheel file, placed by <parts.json>."""
    body_glb, wheel_glb, parts_path, out_dir = argv[1], argv[2], argv[3], argv[4]
    o = options()
    os.makedirs(out_dir, exist_ok=True)
    P = json.load(open(parts_path))
    reset()
    body = import_mesh(body_glb, CAR_ID)
    rot = P.get('R') or ([[-1, 0, 0], [0, 1, 0], [0, 0, -1]] if P['front_source_axis'] == '+z' else
                         [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    to_frame(body, rot, length=P.get('length', 4.5))
    info = {'source_tris': tri_count(body), 'mode': 'parts'}
    img = tex_image(body) if body.active_material and body.active_material.use_nodes else None

    wheel = import_mesh(wheel_glb, CAR_ID + '_wheel_src')
    lo, hi = bounds_np(wheel)
    ext = hi - lo
    axle = int(np.argmin(ext))                  # thinnest axis = axle
    wheel.data.transform(Matrix.Translation(Vector(-(lo + hi) / 2)))
    if axle == 1:
        wheel.data.transform(Matrix.Rotation(math.pi / 2, 4, 'Z'))
    elif axle == 2:
        wheel.data.transform(Matrix.Rotation(math.pi / 2, 4, 'Y'))
    # wheel_outer is given in the wheel file's own glTF axes after the axle is turned onto X
    if P.get('wheel_outer', '-x') == '+x':
        wheel.data.transform(Matrix.Rotation(math.pi, 4, 'Z'))
    lo, hi = bounds_np(wheel)
    r_file = max(hi[1] - lo[1], hi[2] - lo[2]) / 2
    r = P.get('radius', r_file)
    wheel.data.transform(Matrix.Scale(r / r_file, 4))
    lo, hi = bounds_np(wheel)
    per = {'r': round(float(r), 4), 'w': round(float(hi[0] - lo[0]), 4), 'bbox_yz_vs_axle_m': 0.0}
    info['wheels'] = {'L': finish_wheel(wheel, 'L', r, None, o, out_dir)}
    info['wheels']['L']['axle_axis_in_file'] = 'xyz'[axle]

    centres = {k: Vector((v[0], -v[2], v[1])) for k, v in P['wheels'].items()}
    rim = P.get('rim', [180, 180, 185])
    shift, size_b = finish_body(body, img, o, info)
    write_outputs(out_dir, body, {'L': wheel}, centres, {k: per for k in WHEELS}, rim, size_b, shift, info,
                  {'wheel_meshes_note': 'one left wheel (outer face -X); the right side uses it turned 180 deg'})


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
    bpy.context.view_layer.update()          # bound_box / matrix_world are stale after data or location changes
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


def surface_points(ob):
    """Vertices + triangle centres + edge midpoints of a mesh (world = mesh space here)."""
    co = verts_np(ob)
    vi = np.empty(len(ob.data.loops), np.int32)
    ob.data.loops.foreach_get('vertex_index', vi)
    lt = np.empty(len(ob.data.polygons), np.int32)
    ob.data.polygons.foreach_get('loop_total', lt)
    pts = [co]
    if (lt == 3).all():
        t = co[vi.reshape(-1, 3)]
        pts += [t.mean(1), (t[:, 0] + t[:, 1]) / 2, (t[:, 1] + t[:, 2]) / 2, (t[:, 2] + t[:, 0]) / 2]
    return np.concatenate(pts)


def wheel_sweep(body_pts, c, r, w, steer_deg, dy):
    """Body points inside the tyre cylinder (radius r, width w, axle X) after steering about the vertical axis
    through the wheel centre and moving the wheel up by dy (m). Returns (count, min gap over the tyre's x band)."""
    p = body_pts - (np.array(c) + np.array((0, 0, dy)))
    a = math.radians(steer_deg)
    ca, sa = math.cos(a), math.sin(a)
    x = p[:, 0] * ca + p[:, 1] * sa                 # rotate by -steer about Z (into the wheel frame)
    y = -p[:, 0] * sa + p[:, 1] * ca
    rad = np.hypot(y, p[:, 2])
    band = np.abs(x) <= 0.45 * w                 # the tyre, not the 3 cm cut margins
    ring = band & (rad > 0.75 * r)               # tyre ring; inner hub-area body bits are hidden behind the rim
    inside = ring & (rad <= r * 0.985)
    gap = float((rad[ring] - r).min()) if ring.any() else float('inf')
    return int(inside.sum()), gap, int((band & (rad <= 0.75 * r)).sum())


def qa():
    out_dir, qa_dir = argv[1], argv[2]
    os.makedirs(qa_dir, exist_ok=True)
    lay = json.load(open(os.path.join(out_dir, f'{CAR_ID}_wheels.json')))
    build = json.load(open(os.path.join(out_dir, f'{CAR_ID}_build.json')))
    report = {'car': CAR_ID}
    if '--src' in argv:
        src_glb, det_path = argv[argv.index('--src') + 1], argv[argv.index('--src') + 2]
        det = json.load(open(det_path))
        reset()
        src = import_mesh(src_glb, 'src')
        to_frame(src, det_rot(det), scale=det['scale'], centre_n=det['centre'])
        cam = setup_render((900, 560))
        paths = []
        for name, az, el in VIEWS:
            p = os.path.join(qa_dir, f'_b_{name}.png')
            shoot(cam, [src], p, az, el)
            paths.append(p)
        grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_before.png'))

    # after: body + wheel GLBs at the layout centres, the way RaceCarServer places them
    reset()
    body = import_mesh(os.path.join(out_dir, f'{CAR_ID}.glb'), 'body')
    files = lay['wheel_meshes']
    wsrc = {k: import_mesh(os.path.join(out_dir, f), 'w_' + k) for k, f in files.items()}
    placed = {}
    for k in WHEELS:
        if k in wsrc:
            ob, turn = wsrc[k], 0.0
        elif k[1] in wsrc:
            ob, turn = wsrc[k[1]], 0.0
        else:
            ob, turn = wsrc['R' if k[1] == 'L' else 'L'], math.pi
        if ob.name in [o.name for o in placed.values()]:
            ob = ob.copy()
            bpy.context.scene.collection.objects.link(ob)
        c = lay['wheels'][k]
        ob.location = Vector((c[0], -c[2], c[1]))
        ob.rotation_euler = (0, 0, turn)
        placed[k] = ob
    objs = [body] + list(placed.values())
    cam = setup_render((900, 560))
    paths = []
    for name, az, el in VIEWS:
        p = os.path.join(qa_dir, f'_a_{name}.png')
        shoot(cam, objs, p, az, el)
        paths.append(p)
    grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_after.png'))

    # --- numbers --------------------------------------------------------------------------------------------------
    s = BODY_LENGTH_STUDS / lay['size'][2]               # studs per metre in game
    bump, droop = REST_EXT / s, (SUSPENSION_REST - REST_EXT) / s
    W = lay['wheels']
    report['scale_studs_per_m'] = round(s, 4)
    report['alignment'] = {
        'front_axle_z_diff_m': round(abs(W['FL'][2] - W['FR'][2]), 4),
        'rear_axle_z_diff_m': round(abs(W['RL'][2] - W['RR'][2]), 4),
        'front_y_diff_m': round(abs(W['FL'][1] - W['FR'][1]), 4),
        'rear_y_diff_m': round(abs(W['RL'][1] - W['RR'][1]), 4),
        'front_track_asymmetry_m': round(W['FL'][0] + W['FR'][0], 4),
        'rear_track_asymmetry_m': round(W['RL'][0] + W['RR'][0], 4),
        'wheelbase_m': round(((W['RL'][2] + W['RR'][2]) - (W['FL'][2] + W['FR'][2])) / 2, 4),
        'track_front_m': round(W['FR'][0] - W['FL'][0], 4), 'track_rear_m': round(W['RR'][0] - W['RL'][0], 4),
        'wheel_mesh_bbox_centre_vs_axle_m': {k: v.get('bbox_yz_vs_axle_m') for k, v in lay['per_wheel'].items()},
    }
    bpts = surface_points(body)
    discs = lay.get('arch_disc_x', {})
    if discs:
        keep = np.ones(len(bpts), bool)
        for x in discs.values():
            keep &= np.abs(bpts[:, 0] - x) > 1e-3
        bpts = bpts[keep]
    sweeps = {}
    dys = np.round(np.linspace(-droop, bump, 25), 4)
    for k in WHEELS:
        c = (W[k][0], -W[k][2], W[k][1])
        r, w = lay['per_wheel'][k]['r'], lay['per_wheel'][k]['w']
        rest = wheel_sweep(bpts, c, r, w, 0, 0)
        first = None
        for dy in dys[dys >= 0]:
            n = wheel_sweep(bpts, c, r, w, 0, float(dy))[0]
            if n > 0:
                first = float(dy)
                break
        entry = {'rest_points_inside': rest[0], 'rest_min_gap_m': round(rest[1], 4), 'rest_hub_area_points': rest[2],
                 'first_contact_bump_m': first, 'first_contact_bump_studs': None if first is None else round(first * s, 3),
                 'max_bump_m': round(bump, 4), 'max_droop_m': round(droop, 4),
                 'droop_points_inside': wheel_sweep(bpts, c, r, w, 0, -droop)[0]}
        if k[0] == 'F':
            entry['steer'] = {}
            for st in (-STEER_DEG, STEER_DEG):
                n0, g0, _ = wheel_sweep(bpts, c, r, w, st, 0)
                nb = wheel_sweep(bpts, c, r, w, st, bump * 0.5)[0]
                entry['steer'][f'{st:+d}deg'] = {'rest_points_inside': n0, 'rest_min_gap_m': round(g0, 4),
                                                 'half_bump_points_inside': nb}
        sweeps[k] = entry
    report['clearance'] = sweeps
    report['rotation'] = {
        'spin_axis': 'mesh X = wheel part X (CarController: C0 * Angles(-spin, 0, 0))',
        'direction': 'spin += forward_speed * dt / radius; for forward (-Z) motion the contact point moves to +Z '
                     '(backward) = rolling without slip',
        'visual_vs_rolling_radius': 'game radius = WheelRadius * 1.04 (RaceCarServer), so the mesh turns 4 % slower '
                                    'than true rolling and floats 0.04 r above the ground',
        'steer_pivot': 'Angles(0, steer, 0) about the wheel part centre = mesh bbox centre = axle centre '
                       '(see alignment.wheel_mesh_bbox_centre_vs_axle_m)',
    }
    report['triangles'] = {'body': build.get('body_tris'), 'wheels': {k: v.get('tris') for k, v in build['wheels'].items()},
                           'limit_per_meshpart': 20000}
    report['textures'] = {'body': build.get('body_textures', build.get('body_texture')), 'wheels': {k: v.get('texture') for k, v in build['wheels'].items()}}
    report['collision'] = {
        'chassis_box_studs': CHASSIS_STUDS,
        'body_size_studs': [round(v * s, 2) for v in lay['size']],
        'body_meshpart': 'CanCollide false, Massless (RaceCarServer.attachBody)',
        'wheel_meshes': 'CanCollide/CanQuery/CanTouch false, Massless, welded to the hidden wheel cylinder '
                        '(itself CanCollide false, Massless); suspension = raycasts from the chassis mounts',
    }
    json.dump(report, open(os.path.join(qa_dir, f'{CAR_ID}_qa.json'), 'w'), indent=1)
    print(json.dumps(report, indent=1))

    # sweep pictures: side at full bump, top at full steer (fronts)
    rest_loc = {k: o.location.copy() for k, o in placed.items()}
    for o in placed.values():
        o.location.z += bump
    p1 = os.path.join(qa_dir, '_s_bump_left.png')
    shoot(cam, objs, p1, -90, 0)
    p1b = os.path.join(qa_dir, '_s_bump_34.png')
    shoot(cam, objs, p1b, -140, 22)
    for k, o in placed.items():
        o.location = rest_loc[k]
    for k in ('FL', 'FR'):
        placed[k].rotation_euler.z += math.radians(STEER_DEG)
    p2 = os.path.join(qa_dir, '_s_steer_top.png')
    shoot(cam, objs, p2, 0, 89.9)
    p3 = os.path.join(qa_dir, '_s_steer_34.png')
    shoot(cam, objs, p3, -140, 22)
    for k in ('FL', 'FR'):
        placed[k].rotation_euler.z -= math.radians(STEER_DEG)
    grid([p1, p1b, p2, p3], 2, os.path.join(qa_dir, f'{CAR_ID}_sweeps.png'))

    # body alone (arch discs, cut quality)
    for o in placed.values():
        o.hide_render = True
    paths = []
    for name, az, el in [('side_left', -90, 0), ('34_front_left', -140, 22), ('under_34', -130, -25), ('front', 180, 0)]:
        p = os.path.join(qa_dir, f'_c_{name}.png')
        shoot(cam, [body], p, az, el)
        paths.append(p)
    grid(paths, 2, os.path.join(qa_dir, f'{CAR_ID}_body_only.png'))
    body.hide_render = True
    # wheels alone: outer face, inner face, tread, turned 30 deg about X (spin axis check)
    cam = setup_render((420, 420))
    paths = []
    for k, ob in wsrc.items():
        ob.hide_render = False
        keep_loc, keep_rot = ob.location.copy(), ob.rotation_euler.copy()
        ob.location, ob.rotation_euler = Vector((0, 0, 0)), (0, 0, 0)
        outer_az = -90 if k.endswith('L') else 90      # left wheels' outer face is -X
        for az, el in ((outer_az, 0), (-outer_az, 0), (0, 0)):
            p = os.path.join(qa_dir, f'_w_{k}_{az}_{el}.png')
            shoot(cam, [ob], p, az, el, pad=1.15)
            paths.append(p)
        ob.rotation_euler = (math.radians(30), 0, 0)
        p = os.path.join(qa_dir, f'_w_{k}_spin30.png')
        shoot(cam, [ob], p, outer_az, 0, pad=1.15)
        paths.append(p)
        ob.location, ob.rotation_euler = keep_loc, keep_rot
        ob.hide_render = True
    grid(paths, 4, os.path.join(qa_dir, f'{CAR_ID}_wheels.png'))


if MODE == 'build':
    build()
elif MODE == 'build_parts':
    build_parts()
elif MODE == 'qa':
    qa()
else:
    raise SystemExit('mode must be build, build_parts or qa')
