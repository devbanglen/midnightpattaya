"""QA renders of the exported .glb files (run inside Blender, Workbench, like tools/gpu/bl_turntable.py).

  blender -b --factory-startup -P tools/blender/qa_render.py -- <vis_out_dir> <png_dir>

Writes per family a contact sheet <png_dir>/<family>_sheet.png (every asset re-imported FROM THE GLB, so the
picture shows what Roblox will receive: 3/4 view from the front, labels = name + triangle count from manifest.json)
and <png_dir>/kit_assembly.png: a shophouse row and a hotel tower assembled only from kit modules on the
module grid (proves modules, corners and tops snap), each on a plain grey building box.

Per-asset views (VIS-7.1b):  ... -- <vis_out_dir> <png_dir> --views NAME[,NAME...] [--only-views]
  writes <png_dir>/views/<NAME>_{front,34,back,34flip}.png with BACK-FACE CULLING ON (as Roblox draws a glTF with
  doubleSided = false): front = from Roblox -Z (Blender +Y), 34 = front-right 3/4 from above, back = from Roblox +Z,
  34flip = the 3/4 view with every triangle's winding reversed (what a viewer that reads the winding the other way
  would draw: closed solids and two-sided sheets must still read). qa_compose.py puts the four into one sheet.
"""
import glob
import json
import math
import os
import sys

import bpy
from mathutils import Vector, Euler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.units import MODULE_W, FLOOR_H, GROUND_H   # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
SRC, DST = argv[0], argv[1]
VIEWS = argv[argv.index('--views') + 1].split(',') if '--views' in argv else []
ONLY_VIEWS = '--only-views' in argv
os.makedirs(DST, exist_ok=True)
MAN = {}
if os.path.exists(os.path.join(SRC, 'manifest.json')):
    MAN = {a['name']: a for a in json.load(open(os.path.join(SRC, 'manifest.json')))['assets']}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'MATERIAL'
    sc.display.shading.show_cavity = True
    sc.display.shading.show_object_outline = False
    sc.display.shading.show_shadows = True
    sc.world = bpy.data.worlds.new('w')
    sc.world.color = (0.07, 0.08, 0.13)
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.exposure = 0.8


def import_glb(path):
    """import one glb into its own collection; returns (collection, root object)"""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    name = os.path.splitext(os.path.basename(path))[0]
    col = bpy.data.collections.new(name)
    for o in new:
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
        for slot in getattr(o, 'material_slots', []):
            m = slot.material
            if m and m.use_nodes:
                bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                if bsdf:
                    m.diffuse_color = bsdf.inputs['Base Color'].default_value
                    em = bsdf.inputs.get('Emission Strength')
                    if em is not None and em.default_value > 0:      # neon / lamps read brighter
                        c = bsdf.inputs['Emission Color'].default_value
                        m.diffuse_color = (min(1, c[0] * 1.2), min(1, c[1] * 1.2), min(1, c[2] * 1.2), 1)
    root = next((o for o in new if o.parent is None), None)
    return col, root, new


def instance(col, loc, rot_z=0.0, parent_col=None):
    e = bpy.data.objects.new(col.name + '_inst', None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = col
    e.location = loc
    e.rotation_euler = Euler((0, 0, rot_z))
    (parent_col or bpy.context.scene.collection).objects.link(e)
    return e


def bounds(objs):
    pts = []
    for o in objs:
        if o.type == 'MESH':
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def mat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def label(text, loc, size):
    cu = bpy.data.curves.new('lbl', 'FONT')
    cu.body = text
    cu.size = size
    cu.align_x = 'CENTER'
    ob = bpy.data.objects.new('lbl', cu)
    ob.location = loc
    ob.rotation_euler = Euler((math.radians(90), 0, 0))     # stands in XZ, reads left->right from -Y
    ob.data.materials.append(mat('lbl', (0.92, 0.95, 1.0, 1)))
    bpy.context.scene.collection.objects.link(ob)
    return ob


def inst_bounds(insts, extra=()):
    pts = []
    for e in insts:
        for o in e.instance_collection.all_objects:
            if o.type == 'MESH':
                pts += [e.matrix_world @ o.matrix_world @ Vector(c) for c in o.bound_box]
    for o in extra:
        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def render(path, lo, hi, az=-35.0, el=24.0, res=2000, pad=1.08):
    sc = bpy.context.scene
    centre = (lo + hi) / 2
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = 'ORTHO'
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    size = (hi - lo).length
    cam.location = centre + d * size * 2
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_end = size * 6
    # fit: project the bbox corners on the camera plane
    R = cam.rotation_euler.to_matrix()
    right, up = R @ Vector((1, 0, 0)), R @ Vector((0, 1, 0))
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    us = [(c - centre).dot(right) for c in corners]
    vs = [(c - centre).dot(up) for c in corners]
    w, h = max(us) - min(us), max(vs) - min(vs)
    cam.location += right * (max(us) + min(us)) / 2 + up * (max(vs) + min(vs)) / 2
    aspect = w / h
    sc.render.resolution_x = res if aspect >= 1 else int(res * aspect)
    sc.render.resolution_y = int(res / aspect) if aspect >= 1 else res
    cam.data.ortho_scale = max(w, h) * pad
    sc.render.filepath = path
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    bpy.ops.render.render(write_still=True)
    print('RENDER', path, sc.render.resolution_x, sc.render.resolution_y, flush=True)


def sheet(family):
    reset()
    files = sorted(glob.glob(os.path.join(SRC, family, '*.glb')))
    if not files:
        return
    items = []
    for p in files:
        col, root, objs = import_glb(p)
        lo, hi = bounds(objs)
        items.append((col, lo, hi))
    area = sum((hi.x - lo.x + 4) * (hi.z - lo.z + 6) for _c, lo, hi in items)
    row_w = max(math.sqrt(area) * 1.7, max(hi.x - lo.x for _c, lo, hi in items) + 4)
    x = z = 0.0
    row_h = 0.0
    placed = []
    for col, lo, hi in items:
        w, h = hi.x - lo.x, hi.z - lo.z
        cell = max(w, 15.0)                     # labels are ~15 studs wide
        if x > 0 and x + cell > row_w:
            x, z = 0.0, z - row_h - 12.0
            row_h = 0.0
        # rotate 180 deg: fronts (+Y) face the camera at -Y; the bbox flips in X and Y
        x += (cell - w) / 2
        e = instance(col, (x + hi.x, 0, z), math.pi)
        a = MAN.get(col.name, {})
        txt = col.name.split('_', 1)[1]
        if a:
            s = a['size_studs']
            txt += chr(10) + f"{a['tris']} tris  {s[0]:.1f} x {s[1]:.1f} x {s[2]:.1f}"
        label(txt, (x + w / 2, -hi.y - 1, z - 2.4), 1.1)
        placed.append(e)
        x += w + (cell - w) / 2 + 5.0
        row_h = max(row_h, h)
    bpy.context.view_layer.update()
    lo, hi = inst_bounds(placed, [o for o in bpy.context.scene.objects if o.type == 'FONT'])
    render(os.path.join(DST, f'{family}_sheet.png'), lo, hi, az=-30, el=22)


def night_setup(lo, hi):
    """EEVEE night look (emissive neon/lamps from the glTF materials, dark blue sky, weak moonlight, ground)"""
    sc = bpy.context.scene
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [i.identifier for i in
                                                        sc.view_settings.bl_rna.properties['view_transform'].enum_items] else 'Filmic'
    sc.view_settings.exposure = 0.0
    try:
        sc.eevee.taa_render_samples = 32
        sc.eevee.use_bloom = True
    except AttributeError:
        pass
    w = sc.world
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (0.010, 0.012, 0.035, 1)
    bg.inputs['Strength'].default_value = 1.0
    sun = bpy.data.objects.new('moon', bpy.data.lights.new('moon', 'SUN'))
    sun.data.energy = 0.25
    sun.data.color = (0.6, 0.7, 1.0)
    sun.rotation_euler = Euler((math.radians(55), 0, math.radians(150)))
    sc.collection.objects.link(sun)
    for k, (x, col) in enumerate(((lo.x + 10, (1.0, 0.75, 0.45)), ((lo.x + hi.x) / 2, (1.0, 0.75, 0.45)),
                                  (hi.x - 10, (1.0, 0.75, 0.45)))):          # warm street lights in front
        L = bpy.data.objects.new(f'street{k}', bpy.data.lights.new(f'street{k}', 'POINT'))
        L.data.energy = 60000
        L.data.color = col
        L.location = (x, 22, 20)
        sc.collection.objects.link(L)
    bpy.ops.mesh.primitive_plane_add(size=1, location=((lo.x + hi.x) / 2, (lo.y + hi.y) / 2 + 20, -0.05))
    g = bpy.context.active_object
    g.scale = ((hi.x - lo.x) * 1.6, (hi.y - lo.y) + 80, 1)
    gm = bpy.data.materials.new('ground')
    gm.use_nodes = True
    b = next(n for n in gm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (0.03, 0.03, 0.035, 1)
    b.inputs['Roughness'].default_value = 0.35
    g.data.materials.append(gm)


def assembly(night=False):
    reset()
    lib = {}
    for p in glob.glob(os.path.join(SRC, 'buildings', '*.glb')):
        col, _root, _objs = import_glb(p)
        lib[col.name] = col
    grey = mat('box', (0.30, 0.31, 0.34, 1))
    body = []

    def box(x0, y0, z0, x1, y1, z1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        ob = bpy.context.active_object
        ob.scale = (x1 - x0, y1 - y0, z1 - z0)
        ob.data.materials.append(grey)
        body.append(ob)

    def building(ox, nw, nd, rows):
        """building box nw x nd modules at ox (front edge on y=0, building behind at y<0); rows = list of
        (height, [module names cycled along the edge]); top row stands on the roof."""
        Wb, Db = nw * MODULE_W, nd * MODULE_W
        hbox = sum(h for h, _m, top in rows if not top)
        box(ox, -Db, 0, ox + Wb, 0, hbox)
        z = 0.0
        for h, mods, top in rows:
            k = 0
            i = 0
            while i < nw:                                   # front edge (+Y)
                name = mods[k % len(mods)]
                span = 7 if '7Bay' in name else (2 if 'Lobby' in name else 1)
                if i + span > nw:
                    name, span = mods[-1], 1
                instance(lib[name], (ox + (i + span / 2) * MODULE_W, 0, z))
                i += span
                k += 1
            for j in range(nd):                              # right edge (+X), module front rotated to +X
                name = mods[j % len(mods)]
                if '7Bay' in name or 'Lobby' in name:
                    name = 'BLD_GF_CommercialBay'
                instance(lib[name], (ox + Wb, -(j + 0.5) * MODULE_W, z), -math.pi / 2)
            cn = ('BLD_CN_Top' if top else ('BLD_CN_Ground' if z == 0 else
                  ('BLD_CN_GlassMid' if 'CurtainWall' in mods[0] else 'BLD_CN_Mid')))
            instance(lib[cn], (ox + Wb, 0, z))
            instance(lib[cn], (ox, 0, z), math.pi / 2)        # front-left corner: interior at +x, -y
            z += h
        return hbox

    # shophouse row: 4 shophouses (1 module each), ground + 3 floors + parapet
    gf = ['BLD_GF_ShophouseShutter', 'BLD_GF_ShophouseAwning', 'BLD_GF_Restaurant', 'BLD_GF_ShophouseShutter']
    building(0.0, 4, 2, [(GROUND_H, gf, False), (FLOOR_H, ['BLD_MF_ShophouseUpper'], False),
                         (FLOOR_H, ['BLD_MF_PunchedAC', 'BLD_MF_ShophouseUpper'], False),
                         (FLOOR_H, ['BLD_MF_PunchedTwin'], False), (3.5, ['BLD_TP_Parapet'], True)])
    # hotel tower: 4 modules, lobby + bays, 12 floors condo/curtain wall, crown
    rows = [(GROUND_H, ['BLD_GF_HotelLobby', 'BLD_GF_CommercialBay'], False)]
    for f in range(12):
        rows.append((FLOOR_H, ['BLD_MF_CondoBalcony'] if f % 3 else ['BLD_MF_CurtainWallNeon', 'BLD_MF_CurtainWall'], False))
    rows.append((2 * FLOOR_H, ['BLD_TP_CrownFin'], True))
    hb = building(4 * MODULE_W + 14.0, 4, 3, rows)
    instance(lib['BLD_RF_WaterTank'], (4 * MODULE_W + 14.0 + 8, -12, hb))
    # commercial block: 7-bay front, 2 floors balcony rows, cornice
    building(-7 * MODULE_W - 14.0, 7, 2, [(GROUND_H, ['BLD_GF_Commercial7Bay', 'BLD_GF_CommercialBay'], False),
                                          (FLOOR_H, ['BLD_MF_BalconyRow'], False),
                                          (FLOOR_H, ['BLD_MF_BalconyRow'], False),
                                          (4.6, ['BLD_TP_CorniceNeon'], True)])
    instance(lib['BLD_RF_ACUnits'], (-7 * MODULE_W - 14.0 + 10, -6, GROUND_H + 2 * FLOOR_H))
    instance(lib['BLD_RF_PlantRoom'], (-7 * MODULE_W - 14.0 + 30, -7, GROUND_H + 2 * FLOOR_H))
    instance(lib['BLD_RF_SignFrame'], (4 * MODULE_W / 2, -8, GROUND_H + 3 * FLOOR_H))
    bpy.context.view_layer.update()
    insts = [o for o in bpy.context.scene.objects if o.instance_type == 'COLLECTION']
    lo, hi = inst_bounds(insts, body)
    if night:
        night_setup(lo, hi)
        render(os.path.join(DST, 'kit_assembly_night.png'), lo, hi, az=145, el=12, pad=1.12, res=1600)
    else:
        render(os.path.join(DST, 'kit_assembly.png'), lo, hi, az=145, el=18, pad=1.12)   # from +Y: fronts + right side


def find_glb(name):
    for fam in ('buildings', 'roadside', 'racing'):
        p = os.path.join(SRC, fam, name + '.glb')
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)


def asset_views(name):
    """front / 3/4 / back / 3/4-flipped renders of one glb with back-face culling on (Workbench)"""
    import bmesh
    out = os.path.join(DST, 'views')
    os.makedirs(out, exist_ok=True)
    for flip in (False, True):
        reset()
        sc = bpy.context.scene
        sc.display.shading.show_backface_culling = True
        sc.world.color = (0.30, 0.34, 0.42)                 # mid grey-blue: dark glass and white signs both read
        col, root, objs = import_glb(find_glb(name))
        sc.collection.children.link(col)
        for o in objs:
            for slot in getattr(o, 'material_slots', []):
                if slot.material:
                    slot.material.use_backface_culling = True
            if flip and o.type == 'MESH':
                bm = bmesh.new()
                bm.from_mesh(o.data)
                bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
                bm.to_mesh(o.data)
                bm.free()
        bpy.context.view_layer.update()
        lo, hi = bounds(objs)
        # imported glTF: Roblox -Z (front) = Blender +Y; render() azimuth 180 looks from +Y
        shots = [('34flip', 145.0, 22.0)] if flip else [('front', 180.0, 4.0), ('34', 145.0, 22.0), ('back', 0.0, 8.0)]
        for tag, az, el in shots:
            render(os.path.join(out, f'{name}_{tag}.png'), lo, hi, az=az, el=el, res=900, pad=1.12)


if __name__ == '__main__':
    if not ONLY_VIEWS:
        for fam in ('buildings', 'roadside', 'racing'):
            sheet(fam)
        assembly()
        assembly(night=True)
    for n in VIEWS:
        asset_views(n)
    print('QA DONE', flush=True)
