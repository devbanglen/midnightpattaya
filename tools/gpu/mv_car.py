"""Cars: multi-view shape (Hunyuan3D-2mv) + base texture (Hunyuan3D-2.1 paint), on the shared GPU box.

  python mv_car.py <views dir> <out dir> <id> [--faces N] [--no-texture]

<views dir>/<id>_front.png, _back.png, _left.png, _right.png (left = car facing picture-left), optional _top.png
(front pointing up) and _34.png (3/4 front-left; used as the first paint reference when present).
Writes <out>/<id>.glb (shape), <id>_white.obj, <id>_tex.obj/.mtl/.jpg.
"""
import argparse, os, sys, time, types
R = '/root/robloxrace'
ap = argparse.ArgumentParser()
ap.add_argument('views'); ap.add_argument('out'); ap.add_argument('id')
ap.add_argument('--faces', type=int, default=18000)
ap.add_argument('--steps', type=int, default=50); ap.add_argument('--octree', type=int, default=384)
ap.add_argument('--seed', type=int, default=1234)
ap.add_argument('--no-texture', action='store_true')
ap.add_argument('--tex-size', type=int, default=2048); ap.add_argument('--render-size', type=int, default=1024)
a = ap.parse_args()
views, out = os.path.abspath(a.views), os.path.abspath(a.out)
os.makedirs(out, exist_ok=True)

import torch
from PIL import Image
sys.path.insert(0, '/root/Hunyuan3D-2')
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline
from hy3dgen.shapegen.postprocessors import FloaterRemover, DegenerateFaceRemover, FaceReducer

rembg = BackgroundRemover()
def load(name):
    p = os.path.join(views, f'{a.id}_{name}.png')
    if not os.path.exists(p):
        return None
    img = rembg(Image.open(p).convert('RGB'))
    img.save(os.path.join(out, f'{a.id}_{name}_cut.png'))
    return img

cut = {v: load(v) for v in ('front', 'back', 'left', 'right', 'top', '34')}
t0 = time.time()
pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('/root/Hunyuan3D-2mv', subfolder='hunyuan3d-dit-v2-mv',
                                                        variant='fp16')
mv = {v: cut[v] for v in ('front', 'back', 'left', 'right') if cut[v] is not None}
mesh = pipe(image=mv, num_inference_steps=a.steps, octree_resolution=a.octree, num_chunks=20000,
            generator=torch.manual_seed(a.seed), output_type='trimesh')[0]
mesh = FaceReducer()(DegenerateFaceRemover()(FloaterRemover()(mesh)), max_facenum=a.faces)
mesh.export(os.path.join(out, a.id + '.glb'))
white = os.path.join(out, a.id + '_white.obj')
mesh.export(white)
t1 = time.time()
print(f'{a.id}: shape {t1 - t0:.1f}s {len(mesh.faces)} faces', flush=True)
del pipe; torch.cuda.empty_cache()
if a.no_texture:
    sys.exit(0)

# texture: Hunyuan3D-2.1 paint (read-only from the installed copy), every view as a reference image
REPO = '/root/ayothaya/hy/Hunyuan3D-2.1'
sys.path[:0] = [REPO, os.path.join(REPO, 'hy3dpaint')]
os.chdir(REPO)                                  # hy3dpaint loads configs by relative path
sys.modules.setdefault('bpy', types.ModuleType('bpy'))
from textureGenPipeline import Hunyuan3DPaintPipeline, Hunyuan3DPaintConfig
cfg = Hunyuan3DPaintConfig(max_num_view=6, resolution=512)
cfg.texture_size, cfg.render_size = a.tex_size, a.render_size
cfg.realesrgan_ckpt_path = os.path.join(REPO, 'hy3dpaint/ckpt/RealESRGAN_x4plus.pth')
cfg.multiview_cfg_path = os.path.join(REPO, 'hy3dpaint/cfgs/hunyuan-paint-pbr.yaml')
paint = Hunyuan3DPaintPipeline(cfg)
# one reference only: a list of images hits an unbound variable in 2.1's __call__, and every reference is squashed to
# 512x512, so pad it square first. The exact colours from every view come afterwards from project_views.py.
ref = cut['34'] if cut['34'] is not None else cut['front']
side = int(max(ref.size) * 1.1)
sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
sq.paste(ref, ((side - ref.width) // 2, (side - ref.height) // 2))
paint(mesh_path=white, image_path=sq, output_mesh_path=os.path.join(out, a.id + '_tex.obj'),
      use_remesh=False, save_glb=False)
print(f'{a.id}: texture {time.time() - t1:.1f}s', flush=True)
