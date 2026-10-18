"""Make commit-sized JPEG copies of the QA renders (needs Pillow; run on the box after qa_render.py).
  python3 shrink_qa.py <qa_dir> <out_dir> [max_px=1400]"""
import glob
import os
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
mx = int(sys.argv[3]) if len(sys.argv) > 3 else 1400
os.makedirs(dst, exist_ok=True)
for p in sorted(glob.glob(os.path.join(src, '*.png'))):
    im = Image.open(p).convert('RGB')
    im.thumbnail((mx, mx), Image.LANCZOS)
    out = os.path.join(dst, os.path.splitext(os.path.basename(p))[0] + '.jpg')
    im.save(out, quality=85, optimize=True)
    print(out, im.size, os.path.getsize(out))
