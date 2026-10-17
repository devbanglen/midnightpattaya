"""Procedural facade textures (one floor x one bay per tile, transparent wall so the Part colour shows through).

  .venv\\Scripts\\python tools\\mapgen\\facades.py

Writes art/textures/facade_<kind>.png. They are uploaded once to Roblox and their asset ids go into
tools/mapgen/config/facade_assets.json (used by export_roblox.py).
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'art', 'textures')
S = 256


def tile(kind):
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == 'tower':            # tall hotels/condos: big glass window, slab line
        d.rectangle([0, 0, S, 14], fill=(235, 235, 235, 120))                       # floor slab
        d.rectangle([22, 40, S - 22, S - 24], fill=(55, 85, 120, 255))              # glass
        d.rectangle([22, 40, S - 22, 80], fill=(120, 160, 200, 255))                # sky reflection
        d.line([S // 2, 40, S // 2, S - 24], fill=(30, 40, 50, 255), width=6)       # mullion
        d.rectangle([12, S - 30, S - 12, S - 18], fill=(225, 225, 225, 200))        # balcony rail
    elif kind == 'office':         # commercial blocks / malls: ribbon glazing
        d.rectangle([0, 60, S, S - 40], fill=(70, 110, 140, 255))
        d.rectangle([0, 60, S, 95], fill=(140, 180, 210, 255))
        for x in range(0, S, 64):
            d.line([x, 60, x, S - 40], fill=(35, 45, 55, 255), width=6)
    elif kind == 'shophouse':      # low Thai shophouses: window above, roller shutter look below
        d.rectangle([40, 50, S - 40, 150], fill=(60, 75, 90, 255))
        d.rectangle([40, 50, S - 40, 70], fill=(150, 170, 185, 255))
        d.line([S // 2, 50, S // 2, 150], fill=(230, 230, 230, 255), width=6)
        d.rectangle([0, 190, S, S], fill=(0, 0, 0, 70))                            # awning shadow band
    im.save(os.path.join(OUT, f'facade_{kind}.png'))


def night_tile(kind, seed):
    """Night version: a 4 x 4 block of bays/floors (so lit windows don't repeat every window), random warm/cool lit
    windows, dark glass otherwise. Used at 4x the day tile size."""
    import random
    rng = random.Random(seed)
    N = 4
    im = Image.new('RGBA', (S * N, S * N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    warm, cool, dark = (255, 214, 140, 255), (190, 225, 255, 255), (25, 32, 45, 255)
    for fy in range(N):
        for bx in range(N):
            ox, oy = bx * S, fy * S
            r = rng.random()
            col = warm if r < 0.45 else cool if r < 0.6 else dark
            if kind == 'tower':
                d.rectangle([ox + 22, oy + 40, ox + S - 22, oy + S - 24], fill=col)
                d.line([ox + S // 2, oy + 40, ox + S // 2, oy + S - 24], fill=(20, 20, 25, 255), width=6)
            elif kind == 'office':
                d.rectangle([ox, oy + 60, ox + S, oy + S - 40], fill=col if r < 0.7 else dark)
                d.line([ox, oy + 60, ox, oy + S - 40], fill=(20, 20, 25, 255), width=6)
            else:
                d.rectangle([ox + 40, oy + 50, ox + S - 40, oy + 150], fill=col)
                if fy == N - 1:                                  # ground floor shops lit more often
                    d.rectangle([ox + 10, oy + 165, ox + S - 10, oy + S - 6], fill=warm if r < 0.8 else dark)
    im.save(os.path.join(OUT, f'facade_{kind}_night.png'))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for i, k in enumerate(('tower', 'office', 'shophouse')):
        tile(k)
        night_tile(k, i)
    print('wrote day + night facades for tower, office, shophouse')
