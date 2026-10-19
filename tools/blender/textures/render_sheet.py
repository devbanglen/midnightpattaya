"""VIS-7.1c material QA renders (Blender, headless, Cycles). Own script in the qa_render.py spirit, nothing shared
with the frozen pipeline except common/uv.py, which it calls to UV the test shapes exactly like export.py UVs the kit.

  blender -b --factory-startup --python-exit-code 1 -P tools/blender/textures/render_sheet.py -- \
      <maps dir = build/materials> <glb dir with BLD_*/RSD_* .glb> <out dir>

Writes <out>/mat_<Set>.png (sphere + cube, box-projected at 8 studs per UV tile like the kit; non-tiled sets get
their own shape: SignPanel = closed sign board with the front face UV 0..1, PalmFrond = alpha cards like card()),
<out>/kit_<Asset>.png (kit GLBs with the maps assigned per MP_* material, daylight) and <out>/street_night.png
(dry | wet asphalt at 12 studs per tile under a street lamp and a headlight, the MaterialVariant scale).
Compose locally: python tools/blender/textures/compose_sheet.py <out dir>.
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # tools/blender -> `common`
from common.uv import box_project                    # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
MAPS, GLB, OUT = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)

TILED = ['DryAsphalt', 'WetAsphalt', 'Concrete', 'PlasterFacadeA', 'PlasterFacadeB', 'PlasterFacadeC', 'DarkGlass',
         'DarkGlassGrid', 'PaintedMetal', 'Shutter', 'Bark']
# kit material -> (set, tint) ; tint multiplies the colour map (stands in for SurfaceAppearance.Color / palette)
KIT_MAP = {
    'MP_Wall': ('PlasterFacadeB', None), 'MP_WallAccent': ('PlasterFacadeA', (0.55, 0.57, 0.6)),
    'MP_Glass': ('DarkGlass', None), 'MP_Metal': ('PaintedMetal', None), 'MP_MetalDark': ('PaintedMetal', None),
    'MP_Shutter': ('Shutter', None), 'MP_Signboard': ('SignPanel', None), 'MP_Concrete': ('Concrete', None),
    'MP_Bark': ('Bark', None),
}
KIT = [('BLD_GF_ShophouseShutter', {}), ('BLD_MF_BalconyRow', {'MP_Wall': ('PlasterFacadeC', None)}),
       ('BLD_GF_Restaurant', {'MP_Wall': ('PlasterFacadeA', (0.95, 0.75, 0.62))}), ('RSD_Palm_A', {})]


# --- scene ---------------------------------------------------------------------------------------------------------
def reset(res=(640, 320)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dev in ('OPTIX', 'CUDA'):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.type == dev for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == dev
                    sc.cycles.device = 'GPU'
                    break
            except TypeError:
                continue
    except Exception as e:                                  # CPU fallback
        print('GPU setup failed, CPU:', e)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    w = bpy.data.worlds.new('W')
    w.use_nodes = True
    sc.world = w
    return sc


def world(color, strength):
    bg = bpy.context.scene.world.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (*color, 1)
    bg.inputs['Strength'].default_value = strength


def light(kind, loc, energy, color=(1, 1, 1), rot=None, size=None, spot=None):
    ld = bpy.data.lights.new(kind, kind)
    ld.energy = energy
    ld.color = color
    if size is not None:
        if kind == 'SUN':
            ld.angle = size
        else:
            ld.shadow_soft_size = size
    if spot:
        ld.spot_size = spot
    ob = bpy.data.objects.new(kind, ld)
    ob.location = loc
    if rot:
        ob.rotation_euler = rot
    bpy.context.scene.collection.objects.link(ob)
    return ob


def camera(loc, target, lens=50):
    cd = bpy.data.cameras.new('Cam')
    cd.lens = lens
    ob = bpy.data.objects.new('Cam', cd)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.scene.camera = ob


def render(name):
    bpy.context.scene.render.filepath = os.path.join(OUT, name + '.png')
    bpy.ops.render.render(write_still=True)
    print('RENDER', name)


# --- materials -----------------------------------------------------------------------------------------------------
def img(path, data):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return im


def pbr(set_name, tint=None):
    key = set_name + ('' if tint is None else '_t%.2f%.2f%.2f' % tint)
    m = bpy.data.materials.get(key)
    if m:
        return m
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    d = os.path.join(MAPS, set_name)

    def tex(kind, data):
        p = os.path.join(d, kind + '.png')
        if not os.path.exists(p):
            return None
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(p, data)
        t.interpolation = 'Linear'
        return t
    c = tex('color', False)
    col_out = c.outputs['Color']
    if tint is not None:
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(col_out, mix.inputs[6])
        mix.inputs[7].default_value = (*tint, 1)
        col_out = mix.outputs[2]
    nt.links.new(col_out, bsdf.inputs['Base Color'])
    if c.image.channels == 4 and set_name == 'PalmFrond':
        nt.links.new(c.outputs['Alpha'], bsdf.inputs['Alpha'])
    r = tex('roughness', True)
    nt.links.new(r.outputs['Color'], bsdf.inputs['Roughness'])
    mt = tex('metalness', True)
    if mt:
        nt.links.new(mt.outputs['Color'], bsdf.inputs['Metallic'])
    else:
        bsdf.inputs['Metallic'].default_value = 0.0
    n = tex('normal', True)
    nm = nt.nodes.new('ShaderNodeNormalMap')                 # Blender tangent space = OpenGL (+Y), like Roblox
    nt.links.new(n.outputs['Color'], nm.inputs['Color'])
    nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    return m


def obj_from_bm(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def new_bm():
    bm = bmesh.new()
    bm.loops.layers.uv.new('UVMap')
    return bm


def ground(mat_color=(0.08, 0.08, 0.09), size=60):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size)
    m = bpy.data.materials.new('Ground')
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (*mat_color, 1)
    b.inputs['Roughness'].default_value = 0.9
    me = bpy.data.meshes.new('G')
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    ob = bpy.data.objects.new('G', me)
    bpy.context.scene.collection.objects.link(ob)


def day_lights():
    world((0.55, 0.62, 0.75), 0.6)
    light('SUN', (0, 0, 10), 3.5, (1.0, 0.95, 0.88), rot=(math.radians(50), 0, math.radians(35)), size=0.05)
    light('AREA', (-6, 12, 9), 600, (1, 1, 1), size=6)


# --- panels --------------------------------------------------------------------------------------------------------
def panel_tiled(name):
    reset()
    day_lights()
    ground()
    m = pbr(name)
    bm = new_bm()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=3.2)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(-4.2, 0, 3.2))
    bm.normal_update()
    box_project(bm)
    obj_from_bm('Sphere', bm, m)
    bm = new_bm()
    bmesh.ops.create_cube(bm, size=8.0)                      # one full UV tile per face (8 studs)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0),
                     matrix=__import__('mathutils').Matrix.Rotation(math.radians(30), 3, 'Z'))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(5.5, -1, 4.0))
    bm.normal_update()
    box_project(bm)
    ob = obj_from_bm('Cube', bm, m)
    for p in ob.data.polygons:
        p.use_smooth = False
    camera((0.6, 24, 9.0), (0.6, 0, 3.8), lens=32)
    render('mat_' + name)


def panel_sign():
    reset()
    day_lights()
    ground()
    m = pbr('SignPanel')
    x0, x1, z0, z1, y0, y1 = -3.25, 3.25, 2.0, 4.2, 0.0, 0.26     # gf_shophouse sign_box proportions
    bm = new_bm()
    keep = bm.faces.layers.int.new('uvkeep')
    uv = bm.loops.layers.uv.active
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    bm.normal_update()
    for f in bm.faces:
        if f.normal.y > 0.9:                                         # the board front: UV 0..1 as panel()
            for lp in f.loops:
                x, _, z = lp.vert.co
                lp[uv].uv = (1.0 if x < 0 else 0.0, 1.0 if z > (z0 + z1) / 2 else 0.0)
            f[keep] = 1
    box_project(bm)
    ob = obj_from_bm('Sign', bm, m)
    for p in ob.data.polygons:
        p.use_smooth = False
    ob.rotation_euler = (0, 0, math.radians(-18))
    camera((1.5, 11, 4.0), (0, 0, 3.0), lens=50)
    render('mat_SignPanel')


def panel_frond():
    reset()
    world((0.55, 0.62, 0.75), 0.8)
    light('SUN', (0, 0, 10), 3.5, (1.0, 0.95, 0.88), rot=(math.radians(40), 0, math.radians(20)), size=0.05)
    ground((0.3, 0.28, 0.24))
    m = pbr('PalmFrond')
    for k in range(7):                                      # a small crown of cards, uv like common/mesh.py card()
        yaw = k * 2 * math.pi / 7
        pitch = math.radians(25 - (k % 3) * 22)
        L, W, seg = 7.0, 2.6, 6
        h = Vector((math.cos(yaw), math.sin(yaw), 0))
        side = Vector((-math.sin(yaw), math.cos(yaw), 0))
        bm = new_bm()
        uv = bm.loops.layers.uv.active
        rows = []
        for i in range(seg + 1):
            s = i / seg
            p = Vector((0, 0, 6)) + h * (math.cos(pitch) * L * s) + Vector((0, 0, math.sin(pitch) * L * s
                                                                               - 2.2 * s * s))
            rows.append((bm.verts.new(p - side * W / 2), bm.verts.new(p + side * W / 2), s))
        for i in range(seg):
            (a0, a1, v0), (b0, b1, v1) = rows[i], rows[i + 1]
            f = bm.faces.new((a0, a1, b1, b0))
            for lp, t in zip(f.loops, ((0, v0), (1, v0), (1, v1), (0, v1))):
                lp[uv].uv = t
        obj_from_bm('Card%d' % k, bm, m)
    bm = new_bm()
    bmesh.ops.create_cone(bm, cap_ends=False, segments=10, radius1=0.45, radius2=0.35, depth=6.2)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, 3.0))
    bm.normal_update()
    box_project(bm)
    obj_from_bm('Trunk', bm, pbr('Bark'))
    camera((0, 22, 7), (0, 0, 5), lens=40)
    render('mat_PalmFrond')


def panel_kit(asset, override):
    reset((640, 640))
    day_lights()
    ground((0.35, 0.34, 0.32))
    sub = 'buildings' if asset.startswith('BLD') else 'roadside'
    p = os.path.join(GLB, sub, asset + '.glb')
    if not os.path.exists(p):
        p = os.path.join(GLB, asset + '.glb')
    bpy.ops.import_scene.gltf(filepath=p)
    mapping = dict(KIT_MAP)
    mapping.update(override)
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for ob in bpy.context.scene.objects:
        if ob.type != 'MESH' or ob.name == 'G':
            continue
        for slot in ob.material_slots:
            base = slot.material.name.split('.')[0] if slot.material else ''
            if base in mapping:
                slot.material = pbr(*mapping[base])
        for c in ob.bound_box:
            w = ob.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    ctr = (lo + hi) / 2
    ext = max(hi - lo)
    camera((ctr.x + ext * 0.45, ctr.y + ext * 1.55, ctr.z + ext * 0.25), ctr, lens=45)
    render('kit_' + asset)


def panel_street():
    reset((960, 400))
    world((0.02, 0.025, 0.05), 1.0)                            # night
    for x0, name in ((-24, 'DryAsphalt'), (0, 'WetAsphalt')):
        bm = new_bm()
        uv = bm.loops.layers.uv.active
        vs = [bm.verts.new(c) for c in ((x0, -12, 0), (x0 + 24, -12, 0), (x0 + 24, 12, 0), (x0, 12, 0))]
        f = bm.faces.new(vs)
        for lp in f.loops:                                     # MaterialVariant scale: 12 studs per tile
            lp[uv].uv = (lp.vert.co.x / 12.0, lp.vert.co.y / 12.0)
        ob = obj_from_bm(name, bm, pbr(name))
        ob.data.polygons[0].use_smooth = False
    bm = new_bm()                                              # concrete kerb strip at the back
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(48, 4, 0.6))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 14, 0.3))
    bm.normal_update()
    box_project(bm)
    obj_from_bm('Kerb', bm, pbr('Concrete'))
    light('SPOT', (-12, 4, 14), 7000, (1.0, 0.72, 0.42), size=0.4, spot=math.radians(110))   # street lamps
    light('SPOT', (12, 4, 14), 7000, (1.0, 0.72, 0.42), size=0.4, spot=math.radians(110))
    light('AREA', (0, 30, 6), 3000, (0.0, 0.85, 1.0), size=8)       # cyan neon sign behind the camera's view
    camera((0, -22, 6.5), (0, 4, 0), lens=30)
    render('street_night')


if __name__ == '__main__':
    only = os.environ.get('SHEET_ONLY', '')
    todo = [('mat_' + s, (lambda s=s: panel_tiled(s))) for s in TILED]
    todo += [('mat_SignPanel', panel_sign), ('mat_PalmFrond', panel_frond), ('street_night', panel_street)]
    todo += [('kit_' + a, (lambda a=a, o=o: panel_kit(a, o))) for a, o in KIT]
    for name, fn in todo:
        if only and not any(k in name for k in only.split(',')):
            continue
        fn()
    print('DONE')
