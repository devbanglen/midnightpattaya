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


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for k in ('tower', 'office', 'shophouse'):
        tile(k)
    print('wrote', ', '.join(f'facade_{k}.png' for k in ('tower', 'office', 'shophouse')))
