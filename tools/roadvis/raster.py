"""Top-down classification images (same renderer for 'before' = current built data and 'after' = pilot).

The visible top surface wins, by height, like a ray straight down in Studio:
  building > sidewalk (1.6) > corner fill (1.58) > road slab / fill (1.0) > junction / joint disc (0.99)
  > shoulder / taper / gap fill (0.985) > apron (0.98) > terrain
Markings and zebra bars are drawn on top (they are non-colliding decals).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLORS = {
    'terrain': (122, 140, 86), 'building': (200, 190, 168), 'sidewalk': (172, 170, 164), 'corner': (240, 200, 40),
    'road': (52, 52, 58), 'fill': (110, 60, 160), 'junction': (40, 70, 150), 'joint': (90, 120, 200),
    'shoulder': (230, 60, 60), 'taper': (240, 40, 200), 'gap': (150, 0, 150), 'apron': (230, 120, 30),
    # pilot layers
    'asphalt': (52, 52, 58), 'kerb': (215, 215, 210), 'median': (120, 150, 90), 'island': (180, 176, 168),
    'lane': (240, 240, 240), 'centre': (250, 200, 30), 'edge': (240, 240, 240), 'stop': (255, 255, 255),
    'zebra': (255, 255, 255), 'gore': (240, 240, 240),
}
# draw order = painter's algorithm (lowest first)
ORDER_BEFORE = ['apron', 'shoulder', 'taper', 'gap', 'junction', 'joint', 'road', 'fill', 'corner', 'sidewalk', 'building']
LEGEND_BEFORE = ['road', 'fill', 'junction', 'joint', 'apron', 'corner', 'shoulder', 'taper', 'gap', 'sidewalk', 'building', 'terrain']
LEGEND_SCREEN = {'road': 'road slab', 'fill': 'fill tri', 'junction': 'junction disc', 'joint': 'joint disc', 'apron': 'apron',
                 'corner': 'corner fill', 'shoulder': 'shoulder', 'taper': 'taper', 'gap': 'gap fill', 'sidewalk': 'sidewalk',
                 'building': 'building', 'terrain': 'terrain', 'asphalt': 'asphalt', 'kerb': 'kerb', 'median': 'median',
                 'island': 'island', 'lane': 'markings'}


class Canvas:
    def __init__(self, bbox, px_per_stud=2.0, legend=None, title=None):
        self.b, self.k = bbox, px_per_stud
        self.w = int(round((bbox[2] - bbox[0]) * px_per_stud))
        self.h = int(round((bbox[3] - bbox[1]) * px_per_stud))
        self.top = 26 if title else 0
        self.bottom = 30 if legend else 0
        self.img = Image.new('RGB', (self.w, self.h + self.top + self.bottom), COLORS['terrain'])
        self.d = ImageDraw.Draw(self.img)
        self.legend, self.title = legend, title

    def xy(self, p):
        return ((p[0] - self.b[0]) * self.k, (p[1] - self.b[1]) * self.k + self.top)   # +z downwards (south)

    def poly(self, g, color, outline=None):
        if g is None or g.is_empty:
            return
        geoms = getattr(g, 'geoms', [g])
        for q in geoms:
            if q.geom_type != 'Polygon':
                continue
            if not q.interiors:
                self.d.polygon([self.xy(p) for p in q.exterior.coords], fill=color, outline=outline)
                continue
            m = Image.new('L', self.img.size, 0)          # holes stay transparent (what is under them shows)
            md = ImageDraw.Draw(m)
            md.polygon([self.xy(p) for p in q.exterior.coords], fill=255)
            for h in q.interiors:
                md.polygon([self.xy(p) for p in h.coords], fill=0)
            self.img.paste(Image.new('RGB', self.img.size, color), (0, 0), m)

    def line(self, pts, color, width=1):
        self.d.line([self.xy(p) for p in pts], fill=color, width=width)

    def finish(self, path=None):
        f = ImageFont.load_default()
        if self.title:
            self.d.rectangle([0, 0, self.w, self.top], fill=(255, 255, 255))
            self.d.text((6, 6), self.title, fill=(0, 0, 0), font=f)
        if self.legend:
            y = self.top + self.h
            self.d.rectangle([0, y, self.w, y + self.bottom], fill=(255, 255, 255))
            x = 6
            for k in self.legend:
                self.d.rectangle([x, y + 9, x + 12, y + 21], fill=COLORS[k], outline=(0, 0, 0))
                lab = LEGEND_SCREEN.get(k, k)
                self.d.text((x + 16, y + 9), lab, fill=(0, 0, 0), font=f)
                x += 22 + int(self.d.textlength(lab, font=f)) + 10
        if path:
            self.img.save(path)
        return self.img


def render_before(W, bbox, path, px=2.0, title=None, marks=True):
    c = Canvas(bbox, px, LEGEND_BEFORE, title)
    by = {}
    for s in W['surf']:
        by.setdefault(s['kind'], []).append(s['poly'])
    for b in W['blds']:
        by.setdefault('building', []).append(b['poly'])
    for k in ORDER_BEFORE:
        for p in by.get(k, []):
            c.poly(p, COLORS[k])
    if marks:
        for m in W['marks']:
            c.poly(m['poly'], COLORS['centre'] if m['kind'] == 'centre' else COLORS['lane'])
        for x in W['crossings']:
            for bar in x['bars']:
                c.poly(bar, COLORS['zebra'])
    return c.finish(path)


def render_after(P, W, bbox, path, px=2.0, title=None):
    """P: pilot dict from junction.generate (polygons), W: world (buildings + terrain context)"""
    c = Canvas(bbox, px, ['asphalt', 'kerb', 'sidewalk', 'median', 'island', 'lane', 'building', 'terrain'], title)
    for k in ('island', 'median', 'sidewalk', 'kerb', 'asphalt'):
        for p in P['layers'].get(k, []):
            c.poly(p, COLORS[k])
    for m in P['marks']:
        c.poly(m['poly'], COLORS.get(m['kind'], COLORS['lane']))
    for b in W['blds']:
        c.poly(b['poly'], COLORS['building'])
    return c.finish(path)


def side_by_side(a, b, path, gap=12):
    w = a.width + b.width + gap
    h = max(a.height, b.height)
    im = Image.new('RGB', (w, h), (255, 255, 255))
    im.paste(a, (0, 0))
    im.paste(b, (a.width + gap, 0))
    im.save(path)
    return im


LOOK = {'asphalt': (52, 53, 58), 'shoulder': (110, 109, 105), 'sidewalk': (172, 170, 164), 'corner': (150, 148, 142),
        'kerb': (215, 214, 208), 'island': (165, 163, 156), 'grass': (96, 128, 70)}


def render_look(W, bbox, path, P=None, px=1.5, title=None):
    """what the eye sees from straight above, same palette for before (P None) and after (pilot P inside its area):
    every asphalt part (slab, fill, disc, apron) is one colour, shoulders concrete, sidewalks / kerbs light"""
    from shapely.geometry import Point
    c = Canvas(bbox, px, None, title)
    rep = {id(s) for s in P['replaced']} if P is not None else set()
    area = P['area'] if P is not None else None
    order = [('apron', 'asphalt'), ('shoulder', 'shoulder'), ('taper', 'shoulder'), ('gap', 'shoulder'), ('junction', 'asphalt'),
             ('joint', 'asphalt'), ('road', 'asphalt'), ('fill', 'asphalt'), ('corner', 'corner'), ('sidewalk', 'sidewalk')]
    by = {}
    for s in W['surf']:
        if id(s) not in rep:
            by.setdefault(s['kind'], []).append(s['poly'])
    for k, col in order:
        for p in by.get(k, []):
            c.poly(p, LOOK[col])
        if P is not None and k == 'gap':
            c.poly(P['S'], LOOK['asphalt'])
    if P is not None:
        c.poly(P['islands'], LOOK['island'])
        c.poly(P['green'], LOOK['grass'])
        c.poly(P['walk'], LOOK['sidewalk'])
        c.poly(P['kerb'], LOOK['kerb'])
    for m in W['marks']:
        if area is None or not area.contains(m['poly'].centroid):
            c.poly(m['poly'], COLORS['centre'] if m['kind'] == 'centre' else COLORS['lane'])
    for x in W['crossings']:
        if area is None or not area.contains(Point(x['row'][0], x['row'][1])):
            for b in x['bars']:
                c.poly(b, COLORS['zebra'])
    if P is not None:
        for m in P['marks']:
            c.poly(m['poly'], COLORS['centre'] if m['kind'] == 'centre' else COLORS['lane'])
    for b in W['blds']:
        c.poly(b['poly'], COLORS['building'])
    return c.finish(path)


CAM_LABELS = {'before': 'BEFORE (today, as built)', 'A': 'DESIGN A', 'B': 'DESIGN B (Build default)',
              'B_look': 'DESIGN B + ShoulderLook (opt-in)'}


def compose_cams(render_dir, out_dir, cams=('owner_view', 'street', 'driver', 'aerial'), states=('before', 'A', 'B'),
                 width=720, note='offline EEVEE preview, not Studio'):
    """the local 3D renders (blender_preview.py, one engine for every state) as small labelled previews:
    cam_<state>_<cam>.png per state and cmp_<cam>.png = the states side by side; plus cmp_owner_view_look.png
    (B default | B + ShoulderLook) when B_look renders exist. 128-colour palette PNGs, small enough for the repo."""
    import os
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
            d = ImageDraw.Draw(lab)
            d.text((6, 5), f'{CAM_LABELS.get(st, st)} - {cam} - {note}', fill=(0, 0, 0), font=f)
            out = os.path.join(out_dir, f'cam_{st}_{cam}.png')
            lab.quantize(128).save(out, optimize=True)
            made.append(out)
            panels.append(lab)
        if len(panels) > 1:
            gap = 8
            strip = Image.new('RGB', (sum(p.width for p in panels) + gap * (len(panels) - 1), panels[0].height), (255, 255, 255))
            x = 0
            for p_ in panels:
                strip.paste(p_, (x, 0))
                x += p_.width + gap
            out = os.path.join(out_dir, f'cmp_{cam}.png')
            strip.quantize(128).save(out, optimize=True)
            made.append(out)
    look = [os.path.join(render_dir, f'{st}_owner_view.png') for st in ('B', 'B_look')]
    if all(os.path.exists(q) for q in look):
        panels = []
        for st, src in zip(('B', 'B_look'), look):
            im = Image.open(src).convert('RGB')
            im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
            lab = Image.new('RGB', (im.width, im.height + 22), (255, 255, 255))
            lab.paste(im, (0, 22))
            ImageDraw.Draw(lab).text((6, 5), f'{CAM_LABELS[st]} - owner_view - {note}', fill=(0, 0, 0), font=f)
            panels.append(lab)
        strip = Image.new('RGB', (panels[0].width * 2 + 8, panels[0].height), (255, 255, 255))
        strip.paste(panels[0], (0, 0))
        strip.paste(panels[1], (panels[0].width + 8, 0))
        out = os.path.join(out_dir, 'cmp_owner_view_look.png')
        strip.quantize(128).save(out, optimize=True)
        made.append(out)
    return made
