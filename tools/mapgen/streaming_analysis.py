"""Streaming analysis for MIDNIGHT PATTAYA (team16/streaming-arch). Offline, read-only: nothing in build/ is changed.

Reads the exported chunk modules (the same data the Studio builders turn into instances) and re-creates, per data item,
the instances each builder makes (count, category, map-local position). From that it computes:

  1. per chunk (each Atomic Model in workspace.PattayaWorld): total instances, road/collision vs decorative split;
  2. spatial density per 256 / 512 stud cell;
  3. a streaming simulation (teleport into the densest area, driving at 100 / 150 / 200 studs/s) under the pc
     profile (StreamingMinRadius 512, StreamingTargetRadius 1280: ServerStorage/PattayaPerfProfile.luau) for the
     current layout and the alternative layouts (a) 256-stud chunks, (b) roads Atomic 256 + decorative Default,
     (b2) roads Persistent, (c) b + detail props as a client-built near layer, (d) b + building LevelOfDetail;
  4. the prototype layout plan for the test district (mirrors roblox/src/ServerStorage/StreamingPrototype.luau).

EVERY NUMBER HERE IS AN ESTIMATE from a model of the builders and of the engine; the leader measures in Studio.
Instance counts follow the builder code (PattayaBuilder, PattayaApronBuilder, PattayaFurnitureBuilder,
PattayaCoastBuilder, PattayaLandmarksBuilder, PattayaVisSliceBuilder); SurfaceGui sub-trees are approximated and
VisMeshPalms (VIS-7.1) are not modelled.

    .venv\\Scripts\\python tools\\mapgen\\streaming_analysis.py            # writes build/streaming/*
    .venv\\Scripts\\python tools\\mapgen\\streaming_analysis.py --quick    # fewer scenarios (tests)

Coordinates are map-local studs; the world position is map + (20000, 0, 0) (PattayaBuilder.ORIGIN).
"""
import glob
import heapq
import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'circuit'))
import luau_table  # noqa: E402

ORIGIN_X = 20000.0

# ---- engine model (estimates; see docs/STREAMING_ARCHITECTURE.md "Model") ------------------------------------------
PC = {'min_radius': 512, 'target_radius': 1280}
FRAME_S = 1 / 60
ENGINE_BUDGET = 3300        # instances the engine hands to the client per frame during a burst: the leader measured
                            # 19,000-27,000 instances in 6-8 frames after a teleport (docs/STREAMING_PERFORMANCE.md)
COST_MS = 0.058             # measured stream-in cost per instance (Studio Play, throttled render, scripts enabled)
CLIENT_BUDGET = 200         # instances per frame the client near-layer builder (layout c) creates
NEAR_RADIUS = 384           # layout c: detail props exist only within this distance of the camera / car
LOD_TARGET = 896            # layout d: TargetRadius when far buildings are drawn as StreamingMesh imposters

# ---- categories ----------------------------------------------------------------------------------------------------
# road     = drivable / collision ground the car must always have: road slabs, fill wedges, junction / joint discs,
#            aprons, corner fills, sidewalks (kerb collision)
# marking  = on-slab paint, no collision: centre lines, lane dashes, zebra stripes
# building = building bodies (collide) with their facade Textures, roofs, vis-slice and landmark buildings
# detail   = props: palms, street lights (+SpotLights), neon signs, dressing, furniture, coast props, road signs
# model    = container Models (chunk, per-edge road model, Buildings / Props folders)
ROAD_CATS = ('road',)
DECOR_CATS = ('marking', 'building', 'detail')

FACADE_OF = {'hotel', 'condo', 'apartment', 'mall', 'commercial', 'parking', 'shophouse'}


class Item:
    __slots__ = ('x', 'z', 'n', 'cat', 'src', 'chunk', 'name')

    def __init__(self, x, z, n, cat, src, chunk, name):
        self.x, self.z, self.n, self.cat, self.src, self.chunk, self.name = x, z, n, cat, src, chunk, name


# ---- data loading --------------------------------------------------------------------------------------------------
def find_build():
    env = os.environ.get('MP_BUILD_DIR')
    if env and os.path.isdir(env):
        return env
    own = os.path.join(ROOT, 'build')
    if os.path.isdir(os.path.join(own, 'pattaya_wide')):
        return own
    parts = os.path.normpath(ROOT).split(os.sep)
    if '.claude' in parts:
        cand = os.path.join(os.sep.join(parts[:parts.index('.claude')]), 'build')
        if os.path.isdir(cand):
            return cand
    return own


def load(path):
    return luau_table.load(path)


def lst(d, k):
    v = d.get(k) if isinstance(d, dict) else None
    if v is None:
        return []
    if isinstance(v, dict):  # empty table `{}` parses as {} (dict)
        return v.get('_list', [])
    return v


# ---- polyline helpers (PattayaBuilder.stripe / trim / dashes) ----------------------------------------------------------
def pairs(flat):
    return [(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]


def seglen(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def total_len(pts):
    return sum(seglen(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def trim(pts, d0, d1):
    total = total_len(pts)
    if total <= d0 + d1 + 2:
        return None
    out, s, lo, hi = [], 0.0, d0, total - d1
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ln = seglen(a, b)
        s0, s1 = s, s + ln
        if s1 >= lo and s0 <= hi and ln > 0:
            ta = min(max((lo - s0) / ln, 0), 1)
            tb = min(max((hi - s0) / ln, 0), 1)
            if not out:
                out.append((a[0] + (b[0] - a[0]) * ta, a[1] + (b[1] - a[1]) * ta))
            out.append((a[0] + (b[0] - a[0]) * tb, a[1] + (b[1] - a[1]) * tb))
        s = s1
    return out if len(out) >= 2 else None


def stripe_mids(pts):
    """one Part per polyline segment longer than 0.05 studs: their midpoints"""
    return [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:]) if seglen(a, b) > 0.05]


def offset(pts, d):
    out = []
    n = len(pts)
    for i in range(n):
        if i == 0:
            tx, tz = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            tx, tz = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
        else:
            l1 = seglen(pts[i - 1], pts[i]) or 1
            l2 = seglen(pts[i], pts[i + 1]) or 1
            tx = (pts[i + 1][0] - pts[i][0]) / l2 + (pts[i][0] - pts[i - 1][0]) / l1
            tz = (pts[i + 1][1] - pts[i][1]) / l2 + (pts[i][1] - pts[i - 1][1]) / l1
        L = math.hypot(tx, tz) or 1
        tx, tz = tx / L, tz / L
        out.append((pts[i][0] - tz * d, pts[i][1] + tx * d))
    return out


def dash_points(pts, dash, gap):
    out, carry = [], 0.0
    for a, b in zip(pts, pts[1:]):
        ln = seglen(a, b)
        if ln <= 0:
            continue
        dx, dz = (b[0] - a[0]) / ln, (b[1] - a[1]) / ln
        s = carry
        while s + dash <= ln:
            m = s + dash / 2
            out.append((a[0] + dx * m, a[1] + dz * m))
            s += dash + gap
        carry = max(s - ln, 0)
    return out


def wedge_count(a, b, c):
    """WedgeParts PattayaBuilder.roadTriangle / PattayaApronBuilder.triangle make (0, 1 or 2)"""
    ab, bc, ca = seglen(a, b), seglen(b, c), seglen(c, a)
    if bc > ab and bc >= ca:
        a, b, c = b, c, a
    elif ca > ab and ca > bc:
        a, b, c = c, a, b
    L = seglen(a, b)
    if L < 0.05:
        return 0
    dx, dz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t = (c[0] - a[0]) * dx + (c[1] - a[1]) * dz
    foot = (a[0] + dx * t, a[1] + dz * t)
    if seglen(c, foot) < 0.05:
        return 0
    return int(seglen(foot, a) > 0.05) + int(seglen(foot, b) > 0.05)


def detail(out, x, z, n, c, src, chunk, name):
    """a detail item as two Items: its colliding / touching parts (name) and the rest (name + '~', no collision)"""
    if c > 0:
        out.append(Item(x, z, c, 'detail', src, chunk, name))
    if n - c > 0:
        out.append(Item(x, z, n - c, 'detail', src, chunk, name if c == 0 else name + '~'))


# ---- builders ------------------------------------------------------------------------------------------------------
def edge_items(e, jr, dash_gap, src, chunk, out):
    """PattayaBuilder.buildEdge: slab stripes (road), fill wedges (road), markings, sidewalks (road)"""
    pts = pairs(e['pts'])
    name = e.get('nameEn') or e.get('name') or e.get('class')
    out.append(Item(pts[0][0], pts[0][1], 1, 'model', src, chunk, 'RoadModel'))
    if len(pts) < 2:
        return
    hidden = e.get('hidden')
    if not hidden:
        if not (e.get('cutA') or e.get('cutB') or e.get('hide')):
            pieces = [pts]
        else:
            total = total_len(pts)
            hi = total - (e.get('cutB') or 0)
            s = e.get('cutA') or 0
            spans, hide = [], lst(e, 'hide')
            for k in range(0, len(hide) - 1, 2):
                if hide[k] > s:
                    spans.append((s, min(hide[k], hi)))
                s = max(s, hide[k + 1])
            spans.append((s, hi))
            pieces = [trim(pts, a, total - b) for a, b in spans if b > a]
        for p in pieces:
            if p:
                for (x, z) in stripe_mids(p):
                    out.append(Item(x, z, 1, 'road', src, chunk, 'Road:' + str(name)))
    fill = lst(e, 'fill')
    for k in range(0, len(fill) - 5, 6):
        a, b, c = (fill[k], fill[k + 1]), (fill[k + 2], fill[k + 3]), (fill[k + 4], fill[k + 5])
        n = wedge_count(a, b, c)
        if n:
            out.append(Item((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, n, 'road', src, chunk, 'RoadFill'))
    if hidden:
        return
    ra = jr.get(e.get('a'), 0) or e.get('jA') or 0
    rb = jr.get(e.get('b'), 0) or e.get('jB') or 0
    ra, rb = max(ra, e.get('cutA') or 0), max(rb, e.get('cutB') or 0)
    pieces = [(ra, rb)]
    nm = lst(e, 'noMarks')
    if nm:
        total = total_len(pts)
        pieces, s, hi = [], ra, total - rb
        for k in range(0, len(nm) - 1, 2):
            if nm[k] > s:
                pieces.append((s, total - min(nm[k], hi)))
            s = max(s, nm[k + 1])
        pieces.append((s, rb))
    lanes, width = e.get('lanes') or 2, e.get('width') or 20
    for d0, d1 in pieces:
        inner = trim(pts, d0, d1)
        if inner and e.get('tier') != 'soi':
            lines = []
            if e.get('oneway'):
                for k in range(1, lanes):
                    lines.append(('dash', (k - lanes / 2) * width / lanes))
            else:
                lines += [('solid', -0.5), ('solid', 0.5)]
                for k in range(1, lanes // 2):
                    d = k * width / lanes
                    lines += [('dash', d), ('dash', -d)]
            for kind, d in lines:
                line = offset(inner, d)
                ps = stripe_mids(line) if kind == 'solid' else dash_points(line, 8, dash_gap)
                for (x, z) in ps:
                    out.append(Item(x, z, 1, 'marking', src, chunk, 'Centre' if kind == 'solid' else 'Dash'))
    sw = e.get('sidewalk') or 0
    if sw > 0:
        sa = ra + sw if ra > 0 else 0
        sb = rb + sw if rb > 0 else 0
        t = trim(pts, sa, sb)
        if t:
            for side in (-1, 1):
                if e.get('swSide') is None or e.get('swSide') == side:
                    for (x, z) in stripe_mids(offset(t, side * (width + sw) / 2)):
                        out.append(Item(x, z, 1, 'road', src, chunk, 'Sidewalk'))


def building_items(rows, man, src, chunk, out, skip_osm):
    if not rows:
        return
    out.append(Item(rows[0], rows[1], 1, 'model', src, chunk, 'Buildings'))
    pal = man['palettes']
    fmin = man.get('facadeMinHeight') or 0
    for i in range(0, len(rows) - 7, 8):
        x, z, w, d, h = rows[i:i + 5]
        palette = pal[int(rows[i + 6]) - 1]
        if rows[i + 7] in skip_osm:
            continue  # replaced by a vis-slice / landmark building (stashed in ServerStorage)
        n = 1 + (4 if (palette in FACADE_OF and h >= fmin) else 0)
        out.append(Item(x, z, n, 'building', src, chunk, 'Building'))
        if h > 30:
            out.append(Item(x, z, 1, 'building', src, chunk, 'Roof'))


def prop_items(cd, src, chunk, out):
    palms, lights, signs = lst(cd, 'palms'), lst(cd, 'lights'), lst(cd, 'signs')
    if palms or lights or signs:
        out.append(Item(*(palms or lights or signs)[:2], 1, 'model', src, chunk, 'Props'))
    for i in range(0, len(palms) - 1, 2):
        detail(out, palms[i], palms[i + 1], 6, 1, src, chunk, 'Palm')
    for k, i in enumerate(range(0, len(lights) - 3, 4)):
        detail(out, lights[i], lights[i + 1], 3 + (1 if k % 2 == 0 else 0), 1, src, chunk, 'StreetLight')
    for i in range(0, len(signs) - 7, 8):
        detail(out, signs[i], signs[i + 1], 2, 0, src, chunk, 'NeonSign')


def dress_items(cd, src, chunk, out):
    trees, poles, rs, gs = lst(cd, 'trees'), lst(cd, 'poles'), lst(cd, 'roadSigns'), lst(cd, 'gantries')
    if not (trees or poles or rs or gs):
        return
    out.append(Item(0, 0, 0, 'model', src, chunk, 'Dressing'))
    out[-1].x, out[-1].z = (trees or poles or [0, 0])[:2] if (trees or poles) else (rs or gs)[0][:2]
    for i in range(0, len(trees) - 2, 3):
        detail(out, trees[i], trees[i + 1], 2, 1, src, chunk, 'Tree')
    for i in range(0, len(poles) - 4, 5):
        detail(out, poles[i], poles[i + 1], 2 + (1 if poles[i + 4] > 0 else 0), 1, src, chunk, 'UtilityPole')
    for s in rs:
        detail(out, s[0], s[1], 8, 2, src, chunk, 'RoadSign')
    for g in gs:
        detail(out, g[0], g[1], 12, 3, src, chunk, 'Gantry')


def city_chunks(build, data_dir, src, folder, man, jr, skip_osm, out):
    dash_gap = man.get('dashGap') or 12
    for cid in man['chunks']:
        f = os.path.join(build, data_dir, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'{folder}/Chunk_{cid}'
        first = len(out)
        for e in lst(cd, 'edges'):
            edge_items(e, jr, dash_gap, src, chunk, out)
        building_items(lst(cd, 'buildings'), man, src, chunk, out, skip_osm)
        prop_items(cd, src, chunk, out)
        dress_items(cd, src, chunk, out)
        if len(out) > first:
            it = out[first]
            out.append(Item(it.x, it.z, 1, 'model', src, chunk, 'ChunkModel'))


def junction_items(man, joints, src, folder, out):
    for j in lst(man, 'junctions'):
        out.append(Item(j['x'], j['z'], 1, 'road', src, folder, 'Junction'))
    for i in range(0, len(joints) - 3, 4):
        out.append(Item(joints[i + 1], joints[i + 2], 1, 'road', src, folder, 'Joint'))


def apron_items(build, out):
    d = os.path.join(build, 'aprons', 'roblox')
    man = load(os.path.join(d, 'manifest.luau'))
    for cid in man['chunks']:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'ApronChunks/Chunk_{cid}'
        first = len(out)
        for key, name in (('aprons', 'Apron'), ('corners', 'CornerFill')):
            r = lst(cd, key)
            for k in range(0, len(r) - 6, 7):
                a, b, c = (r[k], r[k + 1]), (r[k + 2], r[k + 3]), (r[k + 4], r[k + 5])
                n = wedge_count(a, b, c)
                if n:
                    out.append(Item((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, n, 'road', 'aprons', chunk, name))
        r = lst(cd, 'apronBoxes')
        for k in range(0, len(r) - 6, 7):
            out.append(Item(r[k], r[k + 1], 1, 'road', 'aprons', chunk, 'ApronBox'))
        if len(out) > first:
            out.append(Item(out[first].x, out[first].z, 1, 'model', 'aprons', chunk, 'ChunkModel'))


GUI_SIGN = 5  # SurfaceGui + TextLabel + UIPadding + UIStroke + Frame (one face, one line)


def furniture_items(build, out):
    d = os.path.join(build, 'furniture', 'roblox')
    man = load(os.path.join(d, 'manifest.luau'))
    for cid in man['chunks']:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'FurnitureChunks/Chunk_{cid}'
        first = len(out)
        r = lst(cd, 'signals')
        for i in range(0, len(r) - 7, 8):
            detail(out, r[i], r[i + 1], 6, 1, 'furniture', chunk, 'Signal')
        r = lst(cd, 'crossings')
        for i in range(0, len(r) - 7, 8):
            out.append(Item(r[i], r[i + 1], int(r[i + 4]), 'marking', 'furniture', chunk, 'ZebraStripe'))
        for s in lst(cd, 'nameSigns'):
            lines = max(1, sum(1 for t in s[4:6] if t))
            detail(out, s[0], s[1], 2 + 2 * (3 + 2 * lines), 1, 'furniture', chunk, 'NameSign')
        for s in lst(cd, 'shelters'):
            detail(out, s[0], s[1], 8 + 2 * GUI_SIGN, 6, 'furniture', chunk, 'Shelter')
        r = lst(cd, 'taxis')
        for i in range(0, len(r) - 4, 5):
            detail(out, r[i], r[i + 1], (6 if r[i + 4] == 1 else 4) + 1 + 2 * GUI_SIGN, 2, 'furniture', chunk, 'TaxiStand')
        r = lst(cd, 'poles')
        for i in range(0, len(r) - 4, 5):
            detail(out, r[i], r[i + 1], 2 + (1 if r[i + 4] > 0 else 0), 1, 'furniture', chunk, 'UtilityPole')
        if len(out) > first:
            out.append(Item(out[first].x, out[first].z, 2, 'model', 'furniture', chunk, 'ChunkModel'))


COAST_COLLIDE = {'umbrellas': 0, 'lamps': 2, 'towers': 3, 'boats': 0, 'huts': 4, 'kites': 0}  # Model + colliding parts
COAST_PARTS = {'umbrellas': (5, 4), 'lamps': (4, 3), 'towers': (4, 7), 'boats': (5, 3), 'huts': (5, 6), 'kites': (6, 5)}


def coast_items(build, out):
    d = os.path.join(build, 'coast', 'roblox')
    man = load(os.path.join(d, 'manifest.luau'))
    for cid in man['chunks']:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'CoastChunks/Chunk_{cid}'
        first = len(out)
        for kind, (stride, n) in COAST_PARTS.items():
            r = lst(cd, kind)
            for k, i in enumerate(range(0, len(r) - stride + 1, stride)):
                extra = 1 + (1 if kind == 'lamps' and k % 2 == 0 else 0) + (2 if kind in ('towers', 'huts') else 0)
                detail(out, r[i], r[i + 1], n + extra, COAST_COLLIDE[kind], 'coast', chunk, kind)  # +1: the item's Model
        if len(out) > first:
            out.append(Item(out[first].x, out[first].z, 1, 'model', 'coast', chunk, 'ChunkModel'))


def landmark_items(build, out):
    d = os.path.join(build, 'landmarks', 'roblox')
    man = load(os.path.join(d, 'manifest.luau'))
    replaced = {r['osm'] for r in lst(man, 'replaces')}
    for cid in man['chunks']:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'LandmarkChunks/Chunk_{cid}'
        for lm in lst(cd, 'landmarks'):
            parts = len(lst(lm, 'parts')) // 15
            out.append(Item(lm['x'], lm['z'], 1 + parts + 3 * len(lst(lm, 'texts')), 'building', 'landmarks', chunk, 'Landmark'))
        out.append(Item(out[-1].x, out[-1].z, 1, 'model', 'landmarks', chunk, 'ChunkModel'))
    return replaced


def vis_items(build, out):
    d = os.path.join(build, 'vis_slice', 'roblox')
    man = load(os.path.join(d, 'manifest.luau'))
    replaced = set()
    for cid in man['chunks']:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'VisSliceChunks/Chunk_{cid}'
        for b in lst(cd, 'buildings'):
            replaced.add(b['osm'])
            out.append(Item(b['x'], b['z'], 1 + b['parts'] + (3 if b.get('txt', 0) > 0 else 0), 'building', 'vis_slice', chunk, 'VisBuilding'))
        if lst(cd, 'buildings'):
            out.append(Item(out[-1].x, out[-1].z, 1, 'model', 'vis_slice', chunk, 'ChunkModel'))
    return replaced


# Sukhumvit shoulder pilot (PattayaShoulderBuilder): the chunks installed in the place (leader, 2026-10-21); the
# other exported chunks are not built yet. Override with $MP_SHOULDER_CHUNKS="all" or a comma list.
SHOULDER_INSTALLED = ('s10_26', 's9_1', 's10_25', 's8_2', 's8_1', 's9_25', 's8_2_2', 's8_1_2')


def shoulder_items(build, out, ids=None):
    """ShoulderChunks: road-height boxes (one Part) and triangles (two WedgeParts), all road collision"""
    d = os.path.join(build, 'shoulders', 'roblox')
    if not os.path.isdir(d):
        return
    env = os.environ.get('MP_SHOULDER_CHUNKS')
    if ids is None:
        if env == 'all':
            ids = [os.path.basename(f)[6:-5] for f in sorted(glob.glob(os.path.join(d, 'chunk_*.luau')))]
        elif env:
            ids = env.split(',')
        else:
            ids = SHOULDER_INSTALLED
    for cid in ids:
        f = os.path.join(d, f'chunk_{cid}.luau')
        if not os.path.exists(f):
            continue
        cd = load(f)
        chunk = f'ShoulderChunks/Chunk_{cid}'
        first = len(out)
        kinds = set()
        r = lst(cd, 'boxes')
        for k in range(0, len(r) - 6, 7):
            out.append(Item(r[k], r[k + 1], 1, 'road', 'shoulders', chunk, 'Shoulder'))
            kinds.add(r[k + 6])
        t = lst(cd, 'tris')
        for k in range(0, len(t) - 6, 7):
            a, b, c = (t[k], t[k + 1]), (t[k + 2], t[k + 3]), (t[k + 4], t[k + 5])
            n = wedge_count(a, b, c)
            if n:
                out.append(Item((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, n, 'road', 'shoulders', chunk, 'Shoulder'))
                kinds.add(t[k + 6])
        if len(out) > first:
            out.append(Item(out[first].x, out[first].z, 1 + len(kinds), 'model', 'shoulders', chunk, 'ChunkModel'))


def collect(build=None):
    """Every modelled instance group of workspace.PattayaWorld as Items (map-local positions)."""
    build = build or find_build()
    out = []
    lm_replaced = landmark_items(build, out)
    vis_replaced = vis_items(build, out)
    skip = lm_replaced | vis_replaced
    cman = load(os.path.join(build, 'central_pattaya', 'roblox', 'manifest.luau'))
    wman = load(os.path.join(build, 'pattaya_wide', 'roblox', 'manifest.luau'))
    kman = load(os.path.join(build, 'bira', 'roblox_corridor', 'manifest.luau'))
    skip_central = skip | set(lst(wman, 'baseBuildingConflicts'))
    jr = {}
    for m in (cman, wman, kman):
        for j in lst(m, 'junctions'):
            jr[j['id']] = j['r']
    city_chunks(build, os.path.join('central_pattaya', 'roblox'), 'central', 'Chunks', cman, jr, skip_central, out)
    city_chunks(build, os.path.join('pattaya_wide', 'roblox'), 'wide', 'WideChunks', wman, jr, skip, out)
    city_chunks(build, os.path.join('bira', 'roblox_corridor'), 'corridor', 'WideChunks', kman, jr, skip, out)

    def joints(rel):
        p = os.path.join(build, rel)
        return load(p) if os.path.exists(p) else []
    junction_items(cman, joints('central_pattaya/roblox/joints.luau'), 'central', 'Junctions', out)
    junction_items(wman, joints('pattaya_wide/roblox/joints.luau'), 'wide', 'WideJunctions', out)
    junction_items(kman, joints('bira/roblox_corridor/joints.luau'), 'corridor', 'WideJunctions', out)
    apron_items(build, out)
    shoulder_items(build, out)
    furniture_items(build, out)
    coast_items(build, out)
    return out


LOOSE = ('Junctions', 'WideJunctions')  # Models with default streaming: each disc is its own unit


# ---- per chunk / density -------------------------------------------------------------------------------------------
def chunk_table(items):
    t = defaultdict(lambda: defaultdict(int))
    for it in items:
        t[it.chunk][it.cat] += it.n
    rows = []
    for ch, c in t.items():
        total = sum(c.values())
        rows.append({'chunk': ch, 'total': total, 'road': c['road'], 'marking': c['marking'], 'building': c['building'],
                     'detail': c['detail'], 'model': c['model']})
    rows.sort(key=lambda r: (-r['total'], r['chunk']))
    return rows


def folder_table(rows):
    f = defaultdict(lambda: {'chunks': 0, 'total': 0, 'max': 0, 'road': 0, 'decor': 0})
    for r in rows:
        k = r['chunk'].split('/')[0]
        f[k]['chunks'] += 1
        f[k]['total'] += r['total']
        f[k]['max'] = max(f[k]['max'], r['total'])
        f[k]['road'] += r['road']
        f[k]['decor'] += r['marking'] + r['building'] + r['detail']
    return dict(sorted(f.items()))


def density(items, cell):
    g = defaultdict(lambda: defaultdict(int))
    for it in items:
        g[(math.floor(it.x / cell), math.floor(it.z / cell))][it.cat] += it.n
    rows = [{'cell': list(k), 'cx': (k[0] + 0.5) * cell, 'cz': (k[1] + 0.5) * cell, 'total': sum(v.values()),
             'road': v['road'], 'decor': v['marking'] + v['building'] + v['detail']} for k, v in g.items()]
    rows.sort(key=lambda r: (-r['total'], r['cell']))
    tot = [r['total'] for r in rows]
    return {'cell': cell, 'cells': len(rows), 'max': max(tot), 'p50': pct(tot, 50), 'p90': pct(tot, 90), 'top': rows[:12]}


def pct(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(math.ceil(p / 100 * len(s))) - 1))
    return s[k]


# ---- layouts -------------------------------------------------------------------------------------------------------
class Unit:
    __slots__ = ('uid', 'n', 'minx', 'maxx', 'minz', 'maxz', 'mode', 'layer', 'road', 'roadn', 'items')

    def __init__(self, uid, mode, layer):
        self.uid, self.mode, self.layer = uid, mode, layer
        self.n, self.roadn, self.road = 0, 0, False
        self.minx = self.minz = math.inf
        self.maxx = self.maxz = -math.inf
        self.items = []

    def add(self, it):
        self.n += it.n
        self.items.append(it)
        if it.cat == 'road':
            self.road = True
            self.roadn += it.n
        self.minx, self.maxx = min(self.minx, it.x), max(self.maxx, it.x)
        self.minz, self.maxz = min(self.minz, it.z), max(self.maxz, it.z)

    def dist(self, x, z):
        dx = max(self.minx - x, 0, x - self.maxx)
        dz = max(self.minz - z, 0, z - self.maxz)
        return math.hypot(dx, dz)


def cell_key(it, size, x0=0.0, z0=0.0):
    return (math.floor((it.x - x0) / size), math.floor((it.z - z0) / size))


def split_capped(items, size, cap, x0, z0, prefix):
    """Groups items into size-stud cells; a cell over `cap` instances is split into quadrants (down to 64 studs).
    Returns {name: [items]} (deterministic names)."""
    out = {}
    cells = defaultdict(list)
    for it in items:
        cells[cell_key(it, size, x0, z0)].append(it)
    for k in sorted(cells):
        group = cells[k]
        n = sum(i.n for i in group)
        name = f'{prefix}_{k[0]}_{k[1]}'
        if n > cap and size > 64:
            sub = split_capped(group, size / 2, cap, x0 + k[0] * size, z0 + k[1] * size, name)
            out.update(sub)
        else:
            out[name] = group
    return out


DETAIL_NEAR = {'detail'}  # layout c: the client-built near layer (markings stay engine-streamed, with the roads)


def layout(items, variant, cap=1500):
    """Units for a layout variant. Modes: 'atomic' (one unit), 'default' (each item its own unit), 'persistent'
    (present from join), 'client' (layout c near layer, built by the client within NEAR_RADIUS).
      A   current: every chunk model Atomic; Junctions / WideJunctions loose (default)
      a   everything re-chunked into 256-stud Atomic models (roads and decoration still mixed)
      b   roads + markings Atomic per 256 cell (capped); buildings and detail Default (per part)
      b2  as b, but the road layer Persistent
      c   as b, and detail props built by the client within NEAR_RADIUS
      d   as b, buildings grouped Atomic per 256 cell with LevelOfDetail = StreamingMesh, TargetRadius LOD_TARGET
    """
    units = []
    if variant == 'A':
        by = defaultdict(list)
        for it in items:
            by[it.chunk].append(it)
        for ch in sorted(by):
            if ch in LOOSE:
                for k, it in enumerate(by[ch]):
                    u = Unit(f'{ch}#{k}', 'default', 'road' if it.cat == 'road' else 'decor')
                    u.add(it)
                    units.append(u)
            else:
                u = Unit(ch, 'atomic', 'mixed')
                for it in by[ch]:
                    u.add(it)
                units.append(u)
        return units
    roads = [it for it in items if it.cat in ('road', 'marking')]
    decor = [it for it in items if it.cat not in ('road', 'marking')]
    if variant == 'a':
        for name, group in sorted(split_capped(items, 256, 10 ** 9, 0, 0, 'Cell').items()):
            u = Unit(name, 'atomic', 'mixed')
            for it in group:
                u.add(it)
            units.append(u)
        return units
    road_mode = 'persistent' if variant == 'b2' else 'atomic'
    for name, group in sorted(split_capped([i for i in roads if i.cat != 'model'], 256, cap, 0, 0, 'Road').items()):
        u = Unit(name, road_mode, 'road')
        u.n += 1  # the cell Model
        for it in group:
            u.add(it)
        units.append(u)
    if variant == 'd':
        bld = [i for i in decor if i.cat == 'building']
        rest = [i for i in decor if i.cat != 'building']
        for name, group in sorted(split_capped(bld, 256, cap, 0, 0, 'Bld').items()):
            u = Unit(name, 'atomic_lod', 'decor')
            u.n += 1
            for it in group:
                u.add(it)
            units.append(u)
        decor = rest
    for k, it in enumerate(decor):
        if it.cat == 'model':
            continue  # chunk / folder models of the old layout do not exist in the new one
        mode = 'client' if (variant == 'c' and it.cat in DETAIL_NEAR and not collides(it)) else 'default'
        u = Unit(f'D{k}', mode, 'decor')
        u.add(it)
        units.append(u)
    return units


def target_radius(variant):
    return LOD_TARGET if variant == 'd' else PC['target_radius']


# ---- engine simulation ---------------------------------------------------------------------------------------------
class Grid:
    """spatial hash of units (by AABB) for fast radius queries"""

    def __init__(self, units, cell=256):
        self.cell, self.g = cell, defaultdict(list)
        for u in units:
            for i in range(math.floor(u.minx / cell), math.floor(u.maxx / cell) + 1):
                for j in range(math.floor(u.minz / cell), math.floor(u.maxz / cell) + 1):
                    self.g[(i, j)].append(u)

    def near(self, x, z, r):
        c = self.cell
        seen, out = set(), []
        for i in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for j in range(math.floor((z - r) / c), math.floor((z + r) / c) + 1):
                for u in self.g.get((i, j), ()):
                    if u.uid not in seen:
                        seen.add(u.uid)
                        if u.dist(x, z) <= r:
                            out.append(u)
        return out


class Road:
    """nearest road item lookup -> the unit that holds it"""

    def __init__(self, units, cell=64):
        self.cell, self.g = cell, defaultdict(list)
        for u in units:
            for it in u.items:
                if it.cat == 'road' and it.name not in ('Sidewalk', 'CornerFill'):
                    self.g[(math.floor(it.x / cell), math.floor(it.z / cell))].append((it, u))

    def unit_at(self, x, z, r=48):
        best, bd = None, r
        c = self.cell
        for i in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for j in range(math.floor((z - r) / c), math.floor((z + r) / c) + 1):
                for it, u in self.g.get((i, j), ()):
                    d = math.hypot(it.x - x, it.z - z)
                    if d < bd:
                        best, bd = u, d
        return best


def simulate(units, path, speed, variant, budget=ENGINE_BUDGET, warm=False, duration=None, look=1.0):
    """Frame-by-frame model. Every frame the units within TargetRadius that are not loaded join the engine queue
    (nearest first); the engine transfers `budget` instances per frame and creates a unit in the frame its last
    instance has arrived (an Atomic unit therefore lands whole, and a big one waits several frames). Persistent units are loaded before t = 0. Client-layer units
    (layout c) are built by the client within NEAR_RADIUS at CLIENT_BUDGET instances per frame.
    warm=True: everything within TargetRadius of the start is already loaded (steady driving).
    Road check: the road unit under the car and under the point `look` s ahead must be loaded each frame."""
    R = target_radius(variant)
    grid = Grid(units)
    roads = Road(units)
    loaded = set()
    persistent = [u for u in units if u.mode == 'persistent']
    for u in persistent:
        loaded.add(u.uid)
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + seglen(a, b))
    length = cum[-1]

    def at(s):
        s = min(max(s, 0), length)
        lo, hi = 0, len(cum) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        seg = cum[hi] - cum[lo] or 1
        t = (s - cum[lo]) / seg
        a, b = path[lo], path[hi]
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t

    if warm:
        x, z = at(0)
        for u in grid.near(x, z, R):
            loaded.add(u.uid)
    queued, heap, cheap, cqueued, progress = set(), [], [], set(), {}
    frames, missing_under, missing_ahead, first_road, lead_min = [], 0, 0, None, math.inf
    load_t = {}
    t, s = 0.0, 0.0
    total_t = duration if duration is not None else (length / speed if speed > 0 else 10.0)
    nframes = int(round(total_t / FRAME_S))
    over_t = {}
    for f in range(nframes + 1):
        x, z = at(s)
        for u in grid.near(x, z, R):
            if u.uid in loaded or u.uid in queued:
                continue
            if u.mode == 'client':
                continue
            queued.add(u.uid)
            heapq.heappush(heap, (u.dist(x, z), u.uid, u))
        if f % 6 == 5 and heap:  # the engine re-ranks its queue by the current distance (every 0.1 s here)
            heap = [(u.dist(x, z), uid, u) for _, uid, u in heap]
            heapq.heapify(heap)
        # engine delivery: `budget` instances of transfer per frame, nearest unit first; a unit is applied (its
        # instances created) in the frame its last instance arrives, an Atomic unit all at once
        got, remaining = 0, budget
        while heap and remaining > 0:
            d, uid, u = heap[0]
            need = u.n - progress.get(uid, 0)
            if need <= remaining:
                heapq.heappop(heap)
                remaining -= need
                got += u.n
                loaded.add(uid)
                load_t[uid] = t
            else:
                progress[uid] = progress.get(uid, 0) + remaining
                remaining = 0
        # client near layer (layout c)
        cgot = 0
        if variant == 'c':
            for u in grid.near(x, z, NEAR_RADIUS):
                if u.mode == 'client' and u.uid not in loaded and u.uid not in cqueued:
                    cqueued.add(u.uid)
                    heapq.heappush(cheap, (u.dist(x, z), u.uid, u))
            while cheap and cgot < CLIENT_BUDGET:
                _, uid, u = heapq.heappop(cheap)
                cgot += u.n
                loaded.add(uid)
        frames.append(got + cgot)
        # road availability
        under = roads.unit_at(x, z)
        if under is not None:
            if under.uid not in over_t:
                over_t[under.uid] = t
            if under.uid not in loaded:
                missing_under += 1
            elif first_road is None:
                first_road = f
        ax, az = at(s + speed * look)
        ahead = roads.unit_at(ax, az)
        if ahead is not None and ahead.uid not in loaded:
            missing_ahead += 1
        t += FRAME_S
        s += speed * FRAME_S
    # lead: time between a road unit's delivery and the car first being over it (persistent / warm-loaded units
    # count as loaded at t = -inf and are left out)
    leads = [over_t[uid] - load_t[uid] for uid in over_t if uid in load_t]
    nz = [v for v in frames if v > 0]
    return {
        'variant': variant, 'speed': speed, 'budget': budget, 'warm': warm, 'frames': len(frames),
        'peak_per_frame': max(frames) if frames else 0,
        'p99_per_frame': pct(frames, 99), 'frames_with_arrivals': len(nz),
        'frames_over_1000': sum(1 for v in frames if v > 1000),
        'total_arrived': sum(frames),
        'est_worst_frame_ms': round(max(frames) * COST_MS, 1) if frames else 0,
        'est_p99_ms': round(pct(frames, 99) * COST_MS, 1),
        'road_missing_under_car_frames': missing_under,
        'road_missing_ahead_frames': missing_ahead,
        'first_frame_road_under_car': first_road,
        'min_road_lead_s': round(min(leads), 2) if leads else None,
        'persistent_instances': sum(u.n for u in persistent),
    }


def teleport(units, x, z, variant, budget=ENGINE_BUDGET, seconds=3.0, speed=0.0, path=None):
    """teleport into (x, z) with an empty client stream; speed > 0: the car drives off at once along `path`
    (a road path starting at the target)"""
    if speed == 0 or not path:
        path = [(x, z), (x + 1, z)]
    return simulate(units, path, speed, variant, budget, warm=False, duration=seconds)


def snap_road(items, x, z):
    """the nearest road slab piece to (x, z): teleports land on a road like PattayaTestKitServer.teleport"""
    best = min((i for i in items if i.cat == 'road' and i.name.startswith('Road')),
               key=lambda i: (i.x - x) ** 2 + (i.z - z) ** 2)
    return best.x, best.z, best.name[5:] if best.name.startswith('Road:') else best.name


def road_path_from(build, items, x, z, length):
    """a path along the named road nearest to (x, z), starting at its point nearest to (x, z)"""
    sx, sz, name = snap_road(items, x, z)
    chain = road_chain(build, name, 10 ** 9)
    if len(chain) < 2:
        return [(sx, sz), (sx + length, sz)], name
    k = min(range(len(chain)), key=lambda i: (chain[i][0] - sx) ** 2 + (chain[i][1] - sz) ** 2)
    fwd = chain[k:]
    back = chain[:k + 1][::-1]
    pts = fwd if total_len(fwd) >= total_len(back) else back
    out, s = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        out.append(b)
        s += seglen(a, b)
        if s >= length:
            break
    return out, name


def burst_windows(units, x, z, variant):
    """instances inside MinRadius / TargetRadius of (x, z) and the largest indivisible unit there"""
    R = target_radius(variant)
    g = Grid(units)
    near = g.near(x, z, PC['min_radius'])
    far = g.near(x, z, R)
    return {'variant': variant, 'in_min_radius': sum(u.n for u in near if u.mode != 'client'),
            'in_target_radius': sum(u.n for u in far if u.mode != 'client'),
            'road_in_min_radius': sum(u.roadn for u in near),
            'largest_unit': max([u.n for u in far if u.mode in ('atomic', 'atomic_lod')] or [0]),
            'client_layer_in_near': sum(u.n for u in g.near(x, z, NEAR_RADIUS) if u.mode == 'client'),
            'units_in_target_radius': len(far)}


# ---- drive path (a named road chain, like the leader's Sukhumvit drive) --------------------------------------------
def road_chain(build, name, max_len=9000.0):
    """the longest chain of edges named `name` (central + wide), from its south end, cut at max_len studs"""
    edges = []
    for d in ('central_pattaya/roblox', 'pattaya_wide/roblox'):
        for f in sorted(glob.glob(os.path.join(build, d, 'chunk_*.luau'))):
            for e in lst(load(f), 'edges'):
                if (e.get('nameEn') or e.get('name')) == name and len(e['pts']) >= 4:
                    edges.append(e)
    if not edges:
        return []
    adj = defaultdict(list)
    for k, e in enumerate(edges):
        adj[e['a']].append(k)
        adj[e['b']].append(k)

    def end(e, node):
        p = pairs(e['pts'])
        return p if e['a'] == node else p[::-1]
    # start: the southern-most edge end (smallest z)
    start_e = min(range(len(edges)), key=lambda k: min(edges[k]['pts'][1::2]))
    e0 = edges[start_e]
    p0 = pairs(e0['pts'])
    node = e0['a'] if p0[0][1] <= p0[-1][1] else e0['b']
    used, pts = set(), []
    k = start_e
    while k is not None and k not in used:
        used.add(k)
        seg = end(edges[k], node)
        pts += seg if not pts else seg[1:]
        node = edges[k]['b'] if node == edges[k]['a'] else edges[k]['a']
        nxt = [j for j in adj[node] if j not in used]
        if not nxt:
            break
        # straightest continuation
        hx, hz = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]

        def turn(j):
            q = end(edges[j], node)
            ux, uz = q[1][0] - q[0][0], q[1][1] - q[0][1]
            return -(hx * ux + hz * uz) / ((math.hypot(hx, hz) * math.hypot(ux, uz)) or 1)
        k = min(nxt, key=turn)
    out, s = [pts[0]], 0.0
    for a, b in zip(pts, pts[1:]):
        if s + seglen(a, b) > max_len:
            break
        s += seglen(a, b)
        out.append(b)
    return out


def path_through(units_or_items, x, z, half=1400.0):
    """a straight east-west line through (x, z) (the prototype drive, when no named road is wanted)"""
    return [(x - half, z), (x + half, z)]


# ---- prototype plan (mirror of StreamingPrototype.luau) ------------------------------------------------------------
PROTO_CENTRE_WORLD = (23140.0, 1761.0)
PROTO_HALF = 1536.0
PROTO_OFFSET_X = 60000.0
PROTO_CELL = 256
PROTO_CAP = 1500


def district(items, cx, cz, half=PROTO_HALF):
    return [it for it in items if abs(it.x - cx) <= half and abs(it.z - cz) <= half and it.cat != 'model']


# detail items with no colliding / touching part (builders: NeonSign + frame, beach umbrellas + loungers, boats,
# parasails). In Studio, StreamingPrototype decides per PART (CanCollide or CanTouch), so a palm's fronds go to the
# client layer while its trunk stays engine-streamed; the model splits each item the same way ('~' = the part
# without collision).
NONCOLLIDE_DETAIL = {'NeonSign', 'umbrellas', 'boats', 'kites'}


def collides(it):
    """True when the item holds a part with CanCollide / CanTouch (layout C keeps it engine-streamed)"""
    return not (it.cat == 'detail' and (it.name.endswith('~') or it.name in NONCOLLIDE_DETAIL))


def proto_plan(items, variant, cx, cz, half=PROTO_HALF, cell=PROTO_CELL, cap=PROTO_CAP):
    """Container assignment for the prototype (same rules as StreamingPrototype.luau Plan()). Returns
    {'containers': {name: {'mode', 'layer', 'n', 'roads'}}, 'assign': [(item index, container)]}.
    Cells are anchored at the district's min corner so the plan does not depend on the world grid."""
    src = district(items, cx, cz, half)
    x0, z0 = cx - half, cz - half
    conts, assign = {}, []

    def put(name, mode, layer, k, it):
        c = conts.setdefault(name, {'mode': mode, 'layer': layer, 'n': 0, 'roads': 0, 'items': 0})
        c['n'] += it.n
        c['items'] += 1
        c['roads'] += it.n if it.cat == 'road' else 0
        assign.append((k, name))
    if variant == 'A':
        for k, it in enumerate(src):
            if it.chunk in LOOSE:
                put('Loose/' + it.chunk, 'default', 'road' if it.cat == 'road' else 'decor', k, it)
            else:
                put('Control/' + it.chunk.replace('/', '_'), 'atomic', 'mixed', k, it)
        return {'variant': variant, 'containers': conts, 'assign': assign, 'source': src}
    idx = {id(it): k for k, it in enumerate(src)}
    roads = [it for it in src if it.cat in ('road', 'marking')]
    for name, group in split_capped(roads, cell, cap, x0, z0, 'Roads/Road').items():
        for it in group:
            put(name, 'atomic', 'road', idx[id(it)], it)
    for it in src:
        if it.cat in ('road', 'marking'):
            continue
        k = idx[id(it)]
        ck = cell_key(it, cell, x0, z0)
        if it.cat == 'building':
            mode = 'atomic_lod' if variant == 'D' else 'default'
            put(f'Buildings/Bld_{ck[0]}_{ck[1]}', mode, 'decor', k, it)
        elif variant == 'C' and not collides(it):
            put(f'Detail/Det_{ck[0]}_{ck[1]}', 'client', 'detail', k, it)
        else:
            put(f'Props/Prop_{ck[0]}_{ck[1]}', 'default', 'decor', k, it)
    return {'variant': variant, 'containers': conts, 'assign': assign, 'source': src}


# ---- report --------------------------------------------------------------------------------------------------------
VARIANTS = ('A', 'a', 'b', 'b2', 'c', 'd')


def analyse(build=None, quick=False):
    build = build or find_build()
    items = collect(build)
    rows = chunk_table(items)
    res = {'note': 'ESTIMATES from a model of the builders and the engine (tools/mapgen/streaming_analysis.py); not measured',
           'params': {'pc': PC, 'engine_budget_per_frame': ENGINE_BUDGET, 'cost_ms_per_instance': COST_MS,
                      'client_budget': CLIENT_BUDGET, 'near_radius': NEAR_RADIUS, 'lod_target_radius': LOD_TARGET},
           'totals': {}, 'folders': folder_table(rows), 'top_chunks': rows[:15],
           'density': {'256': density(items, 256), '512': density(items, 512)}}
    for cat in ('road', 'marking', 'building', 'detail', 'model'):
        res['totals'][cat] = sum(i.n for i in items if i.cat == cat)
    res['totals']['all'] = sum(i.n for i in items)
    d512 = res['density']['512']['top'][0]
    pcx, pcz = PROTO_CENTRE_WORLD[0] - ORIGIN_X, PROTO_CENTRE_WORLD[1]
    targets = {'dense_512_cell': (d512['cx'], d512['cz']), 'proto_centre': (pcx, pcz),
               'Chunk_5_3': (5.5 * 512, 3.5 * 512)}
    res['targets'] = {k: {'map': v, 'world': (v[0] + ORIGIN_X, v[1]), 'road': snap_road(items, *v)}
                      for k, v in targets.items()}
    variants = ('A', 'b', 'c') if quick else VARIANTS
    lay = {v: layout(items, v) for v in variants}
    res['layouts'] = {}
    for v, units in lay.items():
        atom = [u.n for u in units if u.mode in ('atomic', 'atomic_lod')]
        res['layouts'][v] = {'units': len(units), 'atomic_units': len(atom), 'max_atomic': max(atom or [0]),
                             'p90_atomic': pct(atom, 90),
                             'persistent': sum(u.n for u in units if u.mode == 'persistent'),
                             'client_layer': sum(u.n for u in units if u.mode == 'client'),
                             'road_in_decor_units': sum(u.roadn for u in units if u.layer == 'decor')}
    res['bursts'] = {k: [burst_windows(lay[v], x, z, v) for v in variants] for k, (x, z) in targets.items()}
    res['teleport'] = {}
    tx, tz, _ = snap_road(items, *targets['proto_centre'])
    off_path, off_name = road_path_from(build, items, tx, tz, 900.0)
    res['teleport_road'] = {'map': (round(tx, 1), round(tz, 1)), 'drive_off_road': off_name,
                            'drive_off_points': len(off_path)}
    for v in variants:
        res['teleport'][v] = {'standing': teleport(lay[v], tx, tz, v),
                              'drive_off_150': teleport(lay[v], tx, tz, v, speed=150.0, path=off_path),
                              'drive_off_200_slow_client': teleport(lay[v], tx, tz, v, budget=800, speed=200.0,
                                                                    path=off_path)}
    if not quick and path_ok(build):
        sp = road_chain(build, 'Sukhumvit Road', 9000.0)
        res['drive_stress'] = {str(b): {v: _brief(simulate(lay[v], sp, 200.0, v, budget=b, warm=False)) for v in variants}
                               for b in (150, 300, 600)}
    if not quick:
        res['teleport_budget_sensitivity'] = {str(b): {v: teleport(lay[v], tx, tz, v, budget=b)['peak_per_frame']
                                                       for v in variants} for b in (1500, 3300, 6000)}
    path = road_chain(build, 'Sukhumvit Road', 9000.0)
    res['drive_path'] = {'name': 'Sukhumvit Road', 'points': len(path),
                         'length': round(sum(seglen(a, b) for a, b in zip(path, path[1:])), 1)}
    res['drive'] = {}
    if path:
        speeds = (150.0,) if quick else (100.0, 150.0, 200.0)
        for v in variants:
            res['drive'][v] = {str(int(sp)): simulate(lay[v], path, sp, v, warm=True) for sp in speeds}
    res['proto_parity'] = proto_parity(items, pcx, pcz)
    res['proto'] = {}
    for v in ('A', 'B', 'C', 'D'):
        p = proto_plan(items, v, pcx, pcz)
        cs = p['containers']
        res['proto'][v] = {'containers': len(cs), 'instances': sum(c['n'] for c in cs.values()),
                           'road_instances': sum(c['roads'] for c in cs.values()),
                           'max_atomic': max([c['n'] for c in cs.values() if c['mode'].startswith('atomic')] or [0]),
                           'by_mode': dict(sorted(_count_modes(cs).items()))}
    return res, items


def path_ok(build):
    return os.path.exists(os.path.join(build, 'pattaya_wide', 'roblox', 'manifest.luau'))


def _brief(r):
    return {k: r[k] for k in ('peak_per_frame', 'p99_per_frame', 'road_missing_under_car_frames',
                              'road_missing_ahead_frames', 'min_road_lead_s', 'frames_over_1000')}


def proto_parity(items, cx, cz, half=PROTO_HALF):
    """per source folder (the PattayaWorld child) {variant: (parts, instances)} for the prototype variants A and B:
    they must be identical (the same source parts are copied; only grouping and streaming mode differ)"""
    out = {}
    for v in ('A', 'B', 'C', 'D'):
        p = proto_plan(items, v, cx, cz, half)
        t = defaultdict(lambda: [0, 0])
        for k, _name in p['assign']:
            it = p['source'][k]
            r = t[it.chunk.split('/')[0]]
            r[0] += 1
            r[1] += it.n
        out[v] = {k: tuple(v2) for k, v2 in sorted(t.items())}
    return out


def _count_modes(cs):
    out = defaultdict(int)
    for c in cs.values():
        out[c['mode']] += c['n']
    return out


def write(res, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'analysis.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=1, sort_keys=True)
    lines = ['STREAMING ANALYSIS (estimates, not measured)', '']
    t = res['totals']
    lines.append('instances: ' + ', '.join(f'{k} {v:,}' for k, v in t.items()))
    lines.append('')
    lines.append('folder              chunks   total     max/chunk  road     decor')
    for k, f in res['folders'].items():
        lines.append(f'{k:<18}{f["chunks"]:>7}{f["total"]:>9,}{f["max"]:>11,}{f["road"]:>9,}{f["decor"]:>9,}')
    lines.append('')
    for v, L in res['layouts'].items():
        lines.append(f'layout {v:<3} units {L["units"]:>7,}  atomic {L["atomic_units"]:>5}  max atomic {L["max_atomic"]:>6,}'
                     f'  persistent {L["persistent"]:>7,}  client {L["client_layer"]:>6,}  road-in-decor {L["road_in_decor_units"]}')
    lines.append('')
    for v, T in res['teleport'].items():
        s, d = T['standing'], T['drive_off_150']
        lines.append(f'teleport {v:<3} peak/frame {s["peak_per_frame"]:>6,} (~{s["est_worst_frame_ms"]} ms) frames>1000 '
                     f'{s["frames_over_1000"]:>3} frames {s["frames_with_arrivals"]:>3}  road under car at frame '
                     f'{s["first_frame_road_under_car"]}  drive-off150 missing under/ahead {d["road_missing_under_car_frames"]}/'
                     f'{d["road_missing_ahead_frames"]} lead {d["min_road_lead_s"]}  slow-client200 missing '
                     f'{T["drive_off_200_slow_client"]["road_missing_under_car_frames"]}/'
                     f'{T["drive_off_200_slow_client"]["road_missing_ahead_frames"]}')
    lines.append('')
    for v, D in res['drive'].items():
        for sp, r in D.items():
            lines.append(f'drive {v:<3} {sp:>3} st/s  peak/frame {r["peak_per_frame"]:>6,} p99 {r["p99_per_frame"]:>6,} '
                         f'frames>1000 {r["frames_over_1000"]:>3}  missing under/ahead {r["road_missing_under_car_frames"]}/'
                         f'{r["road_missing_ahead_frames"]}  lead {r["min_road_lead_s"]} s')
    with open(os.path.join(out_dir, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return '\n'.join(lines)


def main():
    quick = '--quick' in sys.argv
    build = find_build()
    res, _ = analyse(build, quick)
    print(write(res, os.path.join(build, 'streaming')))


if __name__ == '__main__':
    main()
