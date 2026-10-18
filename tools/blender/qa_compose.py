"""Compose the per-asset QA views of qa_render.py --views into one sheet per asset (needs Pillow; run on the box).
  python3 qa_compose.py <png_dir>        # reads <png_dir>/views/<NAME>_{front,34,back,34flip}.png
writes <png_dir>/<NAME>_views.jpg (2 x 2: front | 3/4  /  back | 3/4 winding flipped, labelled)."""
import glob
import os
import sys

from PIL import Image, ImageDraw

TAGS = (('front', 'front (Roblox -Z), culling on'), ('34', '3/4 front-right, culling on'),
        ('back', 'back (Roblox +Z), culling on'), ('34flip', '3/4, winding reversed'))
src = sys.argv[1]
names = sorted({os.path.basename(p).rsplit('_', 1)[0] for p in glob.glob(os.path.join(src, 'views', '*_front.png'))})
for n in names:
    ims = [Image.open(os.path.join(src, 'views', f'{n}_{t}.png')).convert('RGB') for t, _l in TAGS]
    cw = max(i.width for i in ims)
    ch = max(i.height for i in ims) + 28
    sheet = Image.new('RGB', (2 * cw, 2 * ch + 30), (20, 22, 30))
    d = ImageDraw.Draw(sheet)
    d.text((8, 8), n, fill=(235, 240, 255))
    for k, (im, (_t, lab)) in enumerate(zip(ims, TAGS)):
        x, y = (k % 2) * cw, 30 + (k // 2) * ch
        sheet.paste(im, (x + (cw - im.width) // 2, y + 24))
        d.text((x + 8, y + 6), lab, fill=(200, 210, 230))
    out = os.path.join(src, f'{n}_views.jpg')
    sheet.save(out, quality=88)
    print(out, sheet.size)
