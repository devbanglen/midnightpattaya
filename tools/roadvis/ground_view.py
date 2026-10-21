"""Previews of the ground pilot (OFFLINE previews, not Studio): top-down looks with the raised ground, edge-step maps,
and the 3D scenes (today | B | B + ground) for tools/roadvis/blender_preview.py with the owner's 2026-10-22 camera.

  top_look()    raster.render_look (what the eye sees from straight above) with the terrain coloured by state: today's
                terrain 3 studs down (dark), the raised ground by material (Pavement / Ground), the kerb bands
  step_map()    the same look with every surface edge coloured by its step down to what lies beyond it
  scenes()      scene JSONs (scene.py format) with a heightfield mesh of the raised ground and the cameras below
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import box

from tools.roadvis import ground, raster, scene, world

TERRAIN_PIX = raster.COLORS['terrain']
PIT = (88, 94, 72)                 # today's terrain at y -2, seen from above: 3 studs below the road
MAT_RGB = {1: (126, 118, 104), 2: (150, 148, 142)}   # Ground (scene.PAL terrain) / Pavement (the pilot colour)
KERB = (205, 203, 196)
STEP_COLORS = [(0.6 + 1e-9, (40, 170, 70)), (1.2 + 1e-9, (240, 200, 0)), (1.5, (255, 130, 0)), (99.0, (230, 20, 20))]
# cameras (Roblox world): the owner's screenshot camera of 2026-10-22, an overview, a low driver view at the frontage
CAMS = {
    'owner': dict(pos=(24564.0, 57.0, 807.0), dir=(-0.39, -0.39, 0.84), fov=70, res=(1600, 900)),
    'overview': dict(pos=(24790.0, 330.0, 1330.0), look=(24520.0, 0.0, 950.0), fov=50, res=(1600, 1000)),
    # a chase camera 6 studs up, 12 behind a car that runs down the east edge of Sukhumvit (spot 2, path B, lateral -14)
    # towards the trench in front of the two buildings at world x 24544..24561, z 990..1045
    'driver_low': dict(pos=(24556.0, 6.5, 925.0), look=(24543.0, 1.2, 1010.0), fov=65, res=(1600, 900)),
}


def _xy_of_pixels(c, ys, xs):
    x = c.b[0] + (xs + 0.5) / c.k
    z = c.b[1] + (ys - c.top + 0.5) / c.k
    return np.stack([x, z], axis=1)


def top_look(W, P, G, st, bbox, path, title, kerbs=None, px=1.5):
    """what the eye sees from straight above; terrain pixels coloured by the state's ground (see module doc)"""
    img = raster.render_look(W, bbox, None, P=P, px=px, title=title)
    c = raster.Canvas(bbox, px, None, None)
    c.top = 26 if title else 0
    a = np.asarray(img).copy()
    m = np.all(a == np.array(TERRAIN_PIX, np.uint8), axis=2)
    m[:c.top] = False
    ys, xs = np.nonzero(m)
    xy = _xy_of_pixels(c, ys, xs)
    h = st.ground.at(xy)
    col = np.tile(np.array(PIT, float), (len(xy), 1))
    if G is not None:
        i = np.floor((xy[:, 0] + world.ORIGIN[0]) / ground.VOX).astype(int) - G['i0']
        k = np.floor(xy[:, 1] / ground.VOX).astype(int) - G['k0']
        ok = (i >= 0) & (k >= 0) & (i < G['ni']) & (k < G['nk'])
        mat = np.zeros(len(xy), int)
        mat[ok] = G['mat'][i[ok], k[ok]]
        raised = h > ground.TERRAIN_TOP + 0.05
        for code, rgb in MAT_RGB.items():
            sel = raised & (mat == code)
            # shade by height: 0.43 -> full colour, -2 -> the pit colour
            f = np.clip((h[sel] - ground.TERRAIN_TOP) / (G['cfg']['top'] - ground.TERRAIN_TOP), 0, 1)[:, None]
            col[sel] = np.array(PIT, float) * (1 - f) + np.array(rgb, float) * f
    a[ys, xs] = col.astype(np.uint8)
    img = Image.fromarray(a)
    if kerbs:
        d = ImageDraw.Draw(img)
        for s in kerbs:
            d.line([c.xy(s['a']), c.xy(s['b'])], fill=KERB, width=max(1, int(round(s['w'] * px))))
    img.save(path)
    return img


def step_map(W, P, G, st, area, bbox, path, title, px=1.5, kerbs=None):
    """top_look + every edge of the colliding surfaces in `area` (1-stud samples) coloured by its step down to what
    lies 0.25 stud beyond it: green <= 0.6 (drivable both ways), yellow <= 1.2 (a sidewalk / island face down to the
    ground), orange < 1.5, red >= 1.5 (a drop / a wall the car cannot climb)"""
    img = top_look(W, P, G, st, bbox, path, title, kerbs=kerbs, px=px)
    c = raster.Canvas(bbox, px, None, None)
    c.top = 26 if title else 0
    d = ImageDraw.Draw(img)
    E = ground.edge_samples(st, area)
    face = ~E['bld'] & ~E['slot'] & ~E['kerb'] & (E['h_in'] >= 0.9)      # h_in < 0.9: a sliver, not a surface edge
    counts = {}
    for j in np.nonzero(face)[0]:
        s = E['step'][j]
        for lim, rgb in STEP_COLORS:
            if s < lim or lim == 99.0:
                break
        u, v = c.xy(E['p'][j])
        d.ellipse([u - 1.3, v - 1.3, u + 1.3, v + 1.3], fill=rgb)
        counts[rgb] = counts.get(rgb, 0) + 1
    f = ImageFont.load_default()
    labels = [('<= 0.6 stud (drivable back up)', STEP_COLORS[0][1]), ('0.6 - 1.2 (sidewalk / island face)', STEP_COLORS[1][1]),
              ('1.2 - 1.5', STEP_COLORS[2][1]), ('>= 1.5 (drop; a car cannot climb out)', STEP_COLORS[3][1])]
    y = c.top + 8
    d.rectangle([4, y - 4, 292, y + 16 * len(labels) + 2], fill=(255, 255, 255), outline=(0, 0, 0))
    for i, (lab, rgb) in enumerate(labels):
        d.ellipse([10, y + 16 * i + 2, 20, y + 16 * i + 12], fill=rgb, outline=(0, 0, 0))
        d.text((26, y + 16 * i + 1), f'{lab}: {counts.get(rgb, 0)} studs', fill=(0, 0, 0), font=f)
    img.save(path)
    return img, {lab: counts.get(rgb, 0) for lab, rgb in labels}


def strip(images, path, gap=10):
    w = sum(i.width for i in images) + gap * (len(images) - 1)
    h = max(i.height for i in images)
    out = Image.new('RGB', (w, h), (255, 255, 255))
    x = 0
    for i in images:
        out.paste(i, (x, 0))
        x += i.width + gap
    out.save(path)
    return out


# ---- 3D scenes ---------------------------------------------------------------------------------------------------------
def ground_meshes(G, o):
    """the raised ground as a heightfield through the column centres (surface = -2 + 4 * occupancy, the offline model),
    one mesh per material; quads whose four corners are all unraised are left out (the -2 terrain plane shows)"""
    occ = G['occ']
    mat = G['mat']
    ni, nk = occ.shape
    cx = (G['i0'] + np.arange(ni)) * ground.VOX + ground.VOX / 2 - world.ORIGIN[0]
    cz = (G['k0'] + np.arange(nk)) * ground.VOX + ground.VOX / 2
    hgt = ground.TERRAIN_TOP + ground.VOX * occ
    meshes = {code: scene.Mesh(f'ground_{ground.MAT_CODES[code]}', rgb) for code, rgb in MAT_RGB.items()}
    ox, oz = o
    for i in range(ni - 1):
        for k in range(nk - 1):
            q = occ[i:i + 2, k:k + 2]
            if not (q > 0).any():
                continue
            mm = mat[i:i + 2, k:k + 2]
            code = 2 if (mm == 2).any() else 1
            p = [(float(cx[i + a] - ox), float(hgt[i + a, k + b]), float(cz[k + b] - oz)) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
            # Roblox x / z seen from above with y up: (x, -z) counter-clockwise faces up (scene.Mesh.extrude convention)
            meshes[code].quad(p[0], p[3], p[2], p[1])
    return list(meshes.values())


def kerb_meshes(kerbs, cfg, o):
    m = scene.Mesh('kerb_band', KERB)
    ox, oz = o
    from shapely.geometry import LineString
    for s in kerbs:
        poly = LineString([s['a'], s['b']]).buffer(s['w'] / 2, cap_style='flat')
        m.extrude(poly, cfg['kerb_top'], cfg['kerb_bottom'], o)
    return [m]


def cameras(o):
    cx, cz = o
    out = {}
    for name, c in CAMS.items():
        d = dict(fov=c['fov'], res=list(c['res']))
        p = c['pos']
        d['pos'] = [p[0] - world.ORIGIN[0] - cx, p[1], p[2] - cz]
        if 'dir' in c:
            d['dir'] = list(c['dir'])
        else:
            l_ = c['look']
            d['look'] = [l_[0] - world.ORIGIN[0] - cx, l_[1], l_[2] - cz]
        out[name] = d
    return out


def scenes(W, PB, G, out_dir):
    """scene_ground_<today|B|B_ground>.json: the Road B scene builders (scene.before_scene / after_scene) plus the
    raised ground mesh and the kerb bands for B + ground; cameras = CAMS"""
    area = PB['area']
    c = area.centroid
    o = (round(c.x, 1), round(c.y, 1))
    os.makedirs(out_dir, exist_ok=True)
    states = [('today', scene.before_scene(W, area, o)), ('B', scene.after_scene(W, PB, area, o))]
    gm = scene.after_scene(W, PB, area, o) + ground_meshes(G, o) + kerb_meshes(G['kerbs'], G['cfg'], o)
    states.append(('B_ground', gm))
    paths = {}
    for name, ms in states:
        data = dict(note='PREVIEW ONLY (offline render input, tools/roadvis/ground_view.py)', origin=list(o),
                    objects=[x.out() for x in ms if x.f], cameras=cameras(o))
        p = os.path.join(out_dir, f'scene_ground_{name}.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
        paths[name] = p
    return paths


LABELS = {'today': 'TODAY (as built before Road B)', 'B': 'ROAD B (built 2026-10-22)', 'B_ground': 'ROAD B + GROUND (proposed)'}


def compose(render_dir, out_dir, cams=('owner', 'overview', 'driver_low'), states=('today', 'B', 'B_ground'), width=640,
            note='offline EEVEE preview, not Studio'):
    """small labelled panels per camera: <state>_<cam>.png from blender_preview.py -> ground_cmp_<cam>.png"""
    f = ImageFont.load_default()
    made = []
    for cam in cams:
        panels = []
        for st in states:
            src = os.path.join(render_dir, f'{st}_{cam}.png')
            if not os.path.exists(src):
                continue
            im = Image.open(src).convert('RGB')
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            lab = Image.new('RGB', (im.width, im.height + 22), (255, 255, 255))
            lab.paste(im, (0, 22))
            ImageDraw.Draw(lab).text((6, 5), f'{LABELS.get(st, st)} - {cam} - {note}', fill=(0, 0, 0), font=f)
            panels.append(lab)
        if panels:
            out = os.path.join(out_dir, f'ground_cmp_{cam}.png')
            strip(panels, out, gap=8).quantize(128).save(out, optimize=True)
            made.append(out)
    return made
