"""Compose the render_sheet.py panels into one contact sheet (local, PIL).
Usage: python tools/blender/textures/compose_sheet.py build/materials/qa/out [dst.jpg]"""
import glob
import os
import sys

from PIL import Image, ImageDraw


def main():
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.normpath(src)), 'material_sheet.jpg')
    mats = sorted(glob.glob(os.path.join(src, 'mat_*.png')))
    kits = sorted(glob.glob(os.path.join(src, 'kit_*.png')))
    street = glob.glob(os.path.join(src, 'street_night.png'))
    cw, ch, cols = 480, 240, 3
    rows_m = (len(mats) + cols - 1) // cols
    kw = cw * cols // max(len(kits), 1)
    H = rows_m * ch + (kw if kits else 0) + (int(cw * cols * 400 / 960) if street else 0)
    sheet = Image.new('RGB', (cw * cols, H), (20, 20, 24))
    dr = ImageDraw.Draw(sheet)
    for i, p in enumerate(mats):
        x, y = (i % cols) * cw, (i // cols) * ch
        sheet.paste(Image.open(p).convert('RGB').resize((cw, ch), Image.LANCZOS), (x, y))
        dr.text((x + 6, y + 4), os.path.basename(p)[4:-4], fill=(255, 255, 255))
    y = rows_m * ch
    for i, p in enumerate(kits):
        sheet.paste(Image.open(p).convert('RGB').resize((kw, kw), Image.LANCZOS), (i * kw, y))
        dr.text((i * kw + 6, y + 4), os.path.basename(p)[4:-4], fill=(255, 255, 255))
    if street:
        y += kw if kits else 0
        sh = int(cw * cols * 400 / 960)
        sheet.paste(Image.open(street[0]).convert('RGB').resize((cw * cols, sh), Image.LANCZOS), (0, y))
        dr.text((6, y + 4), 'street_night: DryAsphalt | WetAsphalt (12 studs/tile), Concrete kerb', fill=(255, 255, 255))
    sheet.save(dst, quality=88)
    print(dst, sheet.size)


if __name__ == '__main__':
    main()
