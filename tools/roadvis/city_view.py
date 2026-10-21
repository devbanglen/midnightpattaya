"""Offline previews of a city batch (not Studio captures): top-down looks and edge-step maps of today | Road B |
Road B + ground, and Blender scenes (tools/roadvis/blender_preview.py, local bpy: tools/blender/bpy_local.py).
Map-local studs; the pictures are world-aligned (x right, z down = south)."""
import json
import math
import os

import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from tools.roadvis import city, city_qa, ground, junction, scene, world
from tools.roadvis.junction import polys

PIT = (88, 94, 72)
GROUND_RGB = {1: (126, 118, 104), 2: (150, 148, 142)}
COL = dict(asphalt=(46, 47, 52), old_asphalt=(70, 70, 76), sidewalk=(170, 168, 160), island=(160, 158, 150), grass=(86, 120, 62),
           kerb=(205, 203, 196), white=(235, 235, 235), yellow=(245, 200, 40), shoulder=(92, 91, 88), building=(214, 205, 186),
           frontier=(70, 70, 76), corner=(150, 148, 142))
STEP_COLORS = [(0.6 + 1e-9, (40, 170, 70)), (1.2 + 1e-9, (240, 200, 0)), (1.5, (255, 130, 0)), (99.0, (230, 20, 20))]


class Canvas:
    def __init__(self, bbox, px, title=None):
        self.b, self.k = bbox, px
        self.top = 26 if title else 0
        w = int(math.ceil((bbox[2] - bbox[0]) * px))
        h = int(math.ceil((bbox[3] - bbox[1]) * px)) + self.top
        self.img = Image.new('RGB', (w, h), (255, 255, 255))
        self.d = ImageDraw.Draw(self.img)
        if title:
            self.d.text((6, 6), title, fill=(0, 0, 0), font=ImageFont.load_default())

    def xy(self, p):
        return ((p[0] - self.b[0]) * self.k, (p[1] - self.b[1]) * self.k + self.top)

    def poly(self, g, col):
        for p in polys(g):
            if p.is_empty:
                continue
            self.d.polygon([self.xy(q) for q in p.exterior.coords], fill=col)
            for r in p.interiors:
                self.d.polygon([self.xy(q) for q in r.coords], fill=None)

    def seg(self, a, b, w, col):
        self.d.line([self.xy(a), self.xy(b)], fill=col, width=max(1, int(round(w * self.k))))


def terrain_layer(c, field, pavement=False):
    """terrain pixels: today's pit (-2) dark, the raised ground shaded by height: Ground (the builder's default, as the
    pilot box), or with pavement=True the opt-in Pavement near buildings / paved edges"""
    w, h = c.img.size
    xs = c.b[0] + (np.arange(w) + 0.5) / c.k
    zs = c.b[1] + (np.arange(h - c.top) + 0.5) / c.k
    X, Z = np.meshgrid(xs, zs)
    xy = np.stack([X.ravel(), Z.ravel()], axis=1)
    hgt = field.at(xy)
    f = np.clip((hgt + 2.0) / 2.9, 0, 1)[:, None]
    mat = np.ones(len(xy), int)
    if field.o is not None and pavement:
        i = np.floor((xy[:, 0] + city.ORIGIN[0]) / 4).astype(int) - field.i0
        k = np.floor(xy[:, 1] / 4).astype(int) - field.k0
        ok = (i >= 0) & (k >= 0) & (i < field.o.shape[0]) & (k < field.o.shape[1])
        mm = np.zeros(len(xy), int)
        mm[ok] = field.mat[i[ok], k[ok]]
        mat = np.where(mm == 2, 2, 1)
    rgb = np.where(mat[:, None] == 2, np.array(GROUND_RGB[2], float), np.array(GROUND_RGB[1], float))
    col = np.array(PIT, float) * (1 - f) + rgb * f
    a = np.asarray(c.img).copy()
    a[c.top:, :, :] = col.reshape(h - c.top, w, 3).astype(np.uint8)
    c.img = Image.fromarray(a)
    c.d = ImageDraw.Draw(c.img)


def draw_state(c, CW, st, region, field, boxes=()):
    """everything the place holds in `region` after the batches in st"""
    terrain_layer(c, field)
    for j in CW.old_tree.query(region):
        o = CW.old[int(j)]
        if o['i'] in st['replaced_old'] or o['cls'] == 'mark':
            continue
        c.poly(o['shape'], COL['old_asphalt'] if o['cls'] == 'road' else COL['corner'] if o['code'] == 8 else COL['sidewalk'])
    if CW.sh_tree is not None:
        for j in CW.sh_tree.query(region):
            c.poly(CW.shoulders[int(j)]['poly'], COL['shoulder'])
    pc = {11: COL['asphalt'], 12: COL['sidewalk'], 13: COL['island'], 14: COL['grass']}
    for j in CW.pilot_tree.query(region):
        p = CW.pilot['parts'][int(j)]
        if p['i'] in st['replaced_pilot'] or p['seg'] or p['code'] not in pc:
            continue
        c.poly(p['shape'], pc[p['code']])
    kc = {1: COL['asphalt'], 2: COL['sidewalk'], 3: COL['island'], 4: COL['grass']}
    built = set(st['built'])
    for res in st['pieces'].values():
        for t in res['tris'] + res['comp']:
            if t['kind'] in kc and t['tri'].intersects(region):
                c.poly(t['tri'], kc[t['kind']])
        for t in res['front']:
            if t['target'] not in built and t['tri'].intersects(region):
                c.poly(t['tri'], COL['frontier'] if t['kind'] == 1 else COL['sidewalk'])
    for j in CW.old_tree.query(region):
        o = CW.old[int(j)]
        if o['i'] in st['replaced_old'] or o['cls'] != 'mark':
            continue
        c.poly(o['shape'], COL['yellow'] if o['code'] == 4 else COL['white'])
    segcol = {1: COL['white'], 2: COL['yellow'], 3: COL['white'], 4: COL['white'], 5: COL['white'], 6: COL['kerb']}
    for j in CW.pilot_tree.query(region):
        p = CW.pilot['parts'][int(j)]
        if p['i'] in st['replaced_pilot'] or not p['seg']:
            continue
        r = p['row']
        c.seg((r[0], r[1]), (r[2], r[3]), r[4], segcol[p['kind']])
    names = {'lane': 1, 'centre': 2, 'edge': 3, 'stop': 4, 'zebra': 5, 'kerb': 6}
    for res in st['pieces'].values():
        for a, b, w, kind in res['segs']:
            c.seg(a, b, w, segcol[names[kind]])
    for bb in CW.buildings(region):
        c.poly(bb['poly'], COL['building'])
    for bx, col in boxes:
        x0, z0, x1, z1 = city.wloc(bx)
        c.d.rectangle([c.xy((x0, z0)), c.xy((x1, z1))], outline=col, width=2)


def step_dots(c, st, area):
    E = ground.edge_samples(st, area)
    if not E.get('n'):
        return {}
    face = ~E['bld'] & ~E['slot'] & ~E['kerb'] & (E['h_in'] >= 0.9)
    counts = {}
    for j in np.nonzero(face)[0]:
        s = E['step'][j]
        for lim, rgb in STEP_COLORS:
            if s < lim or lim == 99.0:
                break
        u, v = c.xy(E['p'][j])
        c.d.ellipse([u - 1.3, v - 1.3, u + 1.3, v + 1.3], fill=rgb)
        counts[rgb] = counts.get(rgb, 0) + 1
    labels = [('<= 0.6 (drivable back up)', STEP_COLORS[0][1]), ('0.6 - 1.2 (kerb face down to the ground)', STEP_COLORS[1][1]),
              ('1.2 - 1.5', STEP_COLORS[2][1]), ('>= 1.5 (a drop / a wall)', STEP_COLORS[3][1])]
    y = c.top + 8
    c.d.rectangle([4, y - 4, 300, y + 16 * len(labels) + 2], fill=(255, 255, 255), outline=(0, 0, 0))
    for i, (lab, rgb) in enumerate(labels):
        c.d.ellipse([10, y + 16 * i + 2, 20, y + 16 * i + 12], fill=rgb, outline=(0, 0, 0))
        c.d.text((26, y + 16 * i + 1), f'{lab}: {counts.get(rgb, 0)} studs', fill=(0, 0, 0), font=ImageFont.load_default())
    return {lab: counts.get(rgb, 0) for lab, rgb in labels}


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


# ---- 3D scene -----------------------------------------------------------------------------------------------------------
def scene_objects(CW, st, region, field, o, pavement=False):
    """scene.Mesh objects: terrain heightfield, buildings, every surface (extruded from its top to -3), markings"""
    out = []
    T = {1: scene.Mesh('ground_Ground', GROUND_RGB[1]), 2: scene.Mesh('ground_Pavement', GROUND_RGB[2])}
    x0, z0, x1, z1 = region.bounds
    step = 4.0
    xs = np.arange(math.floor(x0 / step) * step, x1 + step, step)
    zs = np.arange(math.floor(z0 / step) * step, z1 + step, step)
    H = field.at(np.stack(np.meshgrid(xs, zs, indexing='ij'), axis=-1).reshape(-1, 2)).reshape(len(xs), len(zs))
    ox, oz = o
    for a in range(len(xs) - 1):
        for b in range(len(zs) - 1):
            p = [(float(xs[a + i] - ox), float(H[a + i, b + j]), float(zs[b + j] - oz)) for i, j in ((0, 0), (1, 0), (1, 1), (0, 1))]
            mat = 1
            if field.o is not None:
                ii = int(math.floor((xs[a] + 2 + city.ORIGIN[0]) / 4)) - field.i0
                kk = int(math.floor((zs[b] + 2) / 4)) - field.k0
                if pavement and 0 <= ii < field.o.shape[0] and 0 <= kk < field.o.shape[1] and field.mat[ii, kk] == 2:
                    mat = 2
            T[mat].quad(p[0], p[3], p[2], p[1])
    out += list(T.values())
    bm = [scene.Mesh(f'buildings_{i}', c) for i, c in enumerate(scene.BLD)]
    for b in CW.buildings(region):
        bm[b['id'] % len(scene.BLD)].extrude(b['poly'], b['h'], -2.0, o)
    out += bm
    m = {k: scene.Mesh(k, scene.PAL[k]) for k in ('asphalt', 'sidewalk', 'corner', 'shoulder', 'island', 'grass')}
    for j in CW.old_tree.query(region):
        q = CW.old[int(j)]
        if q['i'] in st['replaced_old'] or q['cls'] == 'mark':
            continue
        m['asphalt' if q['cls'] == 'road' else 'corner' if q['code'] == 8 else 'sidewalk'].extrude(q['shape'], q['top'], -3.0, o)
    if CW.sh_tree is not None:
        for j in CW.sh_tree.query(region):
            m['shoulder'].extrude(CW.shoulders[int(j)]['poly'], 0.985, -3.0, o)
    name = {11: 'asphalt', 12: 'sidewalk', 13: 'island', 14: 'grass'}
    for j in CW.pilot_tree.query(region):
        p = CW.pilot['parts'][int(j)]
        if p['i'] in st['replaced_pilot'] or p['seg'] or p['code'] not in name:
            continue
        m[name[p['code']]].extrude(p['shape'], p['top'] + (0.01 if p['code'] == 11 else 0), -3.0, o)
    kname = {1: 'asphalt', 2: 'sidewalk', 3: 'island', 4: 'grass'}
    built = set(st['built'])
    for res in st['pieces'].values():
        for t in res['tris'] + res['comp']:
            if t['kind'] in kname and t['tri'].intersects(region):
                top = city.TRI_TOP[t['kind']] + (0.01 if t['kind'] == 1 else 0)
                m[kname[t['kind']]].extrude(t['tri'], top, top - 0.02 if t['kind'] == 4 else -3.0, o)
        for t in res['front']:
            if t['target'] not in built and t['tri'].intersects(region):
                m['asphalt' if t['kind'] == 1 else 'sidewalk'].extrude(t['tri'], city.TRI_TOP[t['kind']], -3.0, o)
    out += list(m.values())
    mk = {k: scene.Mesh('mark_' + k, scene.PAL[k]) for k in ('lane', 'centre', 'zebra', 'kerb')}
    for j in CW.old_tree.query(region):
        q = CW.old[int(j)]
        if q['i'] in st['replaced_old'] or q['cls'] != 'mark':
            continue
        mk['centre' if q['code'] == 4 else 'zebra' if q['code'] == 9 else 'lane'].extrude(q['shape'], 1.05, 1.05, o, walls=False)
    kind_of = {1: 'lane', 2: 'centre', 3: 'lane', 4: 'zebra', 5: 'zebra', 6: 'kerb'}
    for j in CW.pilot_tree.query(region):
        p = CW.pilot['parts'][int(j)]
        if p['i'] in st['replaced_pilot'] or not p['seg']:
            continue
        mk[kind_of[p['kind']]].extrude(p['shape'], 1.61 if p['kind'] == 6 else 1.04, 1.04, o, walls=False)
    seg_kind = {'lane': 'lane', 'edge': 'lane', 'centre': 'centre', 'stop': 'zebra', 'zebra': 'zebra', 'kerb': 'kerb'}
    for res in st['pieces'].values():
        for a, b, w, kind in res['segs']:
            g = world.seg_poly(a, b, w)
            if g is not None and g.intersects(region):
                mk[seg_kind[kind]].extrude(g, 1.611 if kind == 'kerb' else 1.04, 1.04, o, walls=False)
    out += list(mk.values())
    return out


def cameras(o, cams):
    cx, cz = o
    out = {}
    for name, c in cams.items():
        d = dict(fov=c['fov'], res=list(c['res']))
        p = c['pos']
        d['pos'] = [p[0] - city.ORIGIN[0] - cx, p[1], p[2] - cz]
        l_ = c['look']
        d['look'] = [l_[0] - city.ORIGIN[0] - cx, l_[1], l_[2] - cz]
        out[name] = d
    return out


def batch_cams(res):
    """an overview of the batch, the seam with the pilot from both sides, a driver on the main carriageway"""
    x0, z0, x1, z1 = res['box']
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    I = res['ideal']
    cams = {'overview': dict(pos=(x1 + 120, 420.0, z1 + 260), look=(cx, 0.0, cz), fov=50, res=(1600, 1000))}
    # the longest chain through the box: drivers looking along it
    best = None
    BX = box(*city.wloc(res['box']))
    for c in I['chains']:
        poly, Q, T, hw, s = I['rib'][c['id']]
        n = int(shapely.contains_xy(BX, Q[:, 0], Q[:, 1]).sum())
        if best is None or n > best[0]:
            best = (n, Q)
    if best is not None:
        Q = best[1]
        ins = Q[shapely.contains_xy(BX, Q[:, 0], Q[:, 1])]
        if len(ins) > 40:
            a, b = ins[len(ins) // 4], ins[len(ins) // 4 + 30]
            cams['driver'] = dict(pos=(a[0] + city.ORIGIN[0], 7.0, a[1]), look=(b[0] + city.ORIGIN[0], 2.0, b[1]), fov=65, res=(1600, 900))
    pl = city.PILOT_BOX_WORLD
    if z1 == pl[1] and x0 < pl[2] and x1 > pl[0]:                 # the batch's z1 edge is the pilot's z0 edge
        sx = 24560.0 if x0 <= 24560 < x1 else (x0 + x1) / 2
        cams['seam_from_batch'] = dict(pos=(sx - 40, 60.0, z1 - 140), look=(sx, 0.0, z1 + 30), fov=60, res=(1600, 900))
        cams['seam_from_pilot'] = dict(pos=(sx + 40, 60.0, z1 + 160), look=(sx, 0.0, z1 - 20), fov=60, res=(1600, 900))
        cams['seam_driver'] = dict(pos=(sx - 6, 7.0, z1 - 90), look=(sx - 12, 2.0, z1 + 60), fov=65, res=(1600, 900))
    return cams


def previews(CW, plan, st_before, st, res, gplans, raised_before, out_dir, log=print):
    bid = res['id']
    BX = box(*city.wloc(res['box']))
    view = BX.buffer(60, join_style='mitre')
    pl = box(*city.wloc(city.PILOT_BOX_WORLD))
    if BX.buffer(1).intersects(pl):
        view = unary_union([view, pl.intersection(BX.buffer(200, join_style='mitre'))]).envelope
    vb = view.bounds
    g_before = city_qa.CityGround([gplans[k] for k in raised_before])
    g_after = city_qa.CityGround([gplans[k] for k in raised_before + [bid]])
    boxes = [(res['box'], (255, 0, 0)), (city.PILOT_BOX_WORLD, (255, 200, 0))]
    titles = {'today': f'TODAY (pilot built, {bid} not) - offline preview',
              'B': f'ROAD B {bid} built (ground not raised in {bid}) - offline preview',
              'B_ground': f'ROAD B {bid} + GROUND +0.9 - offline preview'}
    looks, steps, counts = [], [], {}
    region = view.buffer(10)
    for name, s_, fld in (('today', st_before, g_before), ('B', st, g_before), ('B_ground', st, g_after)):
        c = Canvas(vb, 1.2, titles[name])
        draw_state(c, CW, s_, region, fld, boxes)
        c.img.save(os.path.join(out_dir, f'top_{name}.png'))
        looks.append(c.img)
        state = city_qa.CityState(CW, s_, region, field=fld)
        c2 = Canvas(vb, 1.2, titles[name].replace('offline preview', 'edge steps'))
        draw_state(c2, CW, s_, region, fld, boxes)
        counts[name] = step_dots(c2, state, BX)
        c2.img.save(os.path.join(out_dir, f'steps_{name}.png'))
        steps.append(c2.img)
    strip(looks, os.path.join(out_dir, 'top_today_B_ground.png'))
    strip(steps, os.path.join(out_dir, 'steps_today_B_ground.png'))
    with open(os.path.join(out_dir, 'step_counts.json'), 'w', encoding='utf-8') as f:
        json.dump(counts, f, indent=1)
    # Blender scenes
    cams = batch_cams(res)
    c = view.centroid
    o = (round(c.x, 1), round(c.y, 1))
    sregion = view.buffer(250, join_style='mitre')
    for name, s_, fld in (('today', st_before, g_before), ('B_ground', st, g_after)):
        objs = scene_objects(CW, s_, sregion, fld, o)
        data = dict(note='PREVIEW ONLY (offline render input, tools/roadvis/city_view.py)', origin=list(o),
                    objects=[x.out() for x in objs if x.f], cameras=cameras(o, cams))
        with open(os.path.join(out_dir, f'scene_{name}.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
    log(f'{bid}: previews in {out_dir} (step counts {counts})')
    return counts


def compose(render_dir, out_dir, bid, cams, states=('today', 'B_ground'), width=640):
    """labelled side-by-side panels per camera from the local renders <state>_<cam>.png"""
    f = ImageFont.load_default()
    made = []
    labels = {'today': 'TODAY (pilot only)', 'B_ground': f'ROAD B {bid} + GROUND +0.9'}
    for cam in cams:
        panels = []
        for stt in states:
            src = os.path.join(render_dir, f'{stt}_{cam}.png')
            if not os.path.exists(src):
                continue
            im = Image.open(src).convert('RGB')
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            lab = Image.new('RGB', (im.width, im.height + 22), (255, 255, 255))
            lab.paste(im, (0, 22))
            ImageDraw.Draw(lab).text((6, 5), f'{labels.get(stt, stt)} - {cam} - offline EEVEE preview, not Studio', fill=(0, 0, 0), font=f)
            panels.append(lab)
        if panels:
            out = os.path.join(out_dir, f'{bid}_cmp_{cam}.png')
            strip(panels, out, gap=8).quantize(128).save(out, optimize=True)
            made.append(out)
    return made
