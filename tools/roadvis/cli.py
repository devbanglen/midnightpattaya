"""One command for the road-visual work (OFFLINE ONLY; nothing touches Studio or the existing build outputs).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py analyze [--city]     -> build/roadvis/analysis.json
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py pilot [--art]         -> build/roadvis/pilot_<name>.json,
        build/roadvis/scene_{before,after}.json (Blender input), build/roadvis/top_*.png; --art also copies the small
        top-down previews to art/roadvis/
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py compose         -> art/roadvis/cam_*.png, cmp_*.png from the
        local 3D renders in build/roadvis/renders_local (tools/roadvis/blender_preview.py with the PyPI bpy module)
Blender preview renders (local PyPI bpy module, EEVEE; the GPU box is paused): docs/ROAD_VISUAL_SPEC.md section 10.
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from shapely.geometry import box  # noqa: E402

from tools.roadvis import analyze, junction, raster, scene, shoulders_view, world  # noqa: E402


def run_pilot(build_root=None, art=False, log=print, cfg=None, designs=('A', 'B')):
    """both designs on the same junction: pilot JSON per design, top-down images, Blender scenes, compare.json"""
    cfg = dict(junction.CFG, **(cfg or {}))
    bl = world.world_bbox_local(cfg['bbox_world'])
    t = time.time()
    W = world.load(build_root, bbox=bl, margin=900.0)        # the wide margin is scenery for the 3D previews
    out = os.path.join(W['broot'], 'roadvis')
    os.makedirs(out, exist_ok=True)
    area = box(*bl)
    pilots, data = {}, {}
    for d in designs:
        c = dict(cfg, design=d, name=f"{cfg['name']}_{d}")
        P = junction.generate(W, c)
        pilots[d] = P
        data[d] = junction.export(W, P, os.path.join(out, f"pilot_{c['name']}.json"))
    A = world.crop(W, bl)
    view = (bl[0] - 40, bl[1] - 40, bl[2] + 40, bl[3] + 40)
    imgs = {}
    imgs['top_before_layers'] = raster.render_before(A, view, os.path.join(out, 'top_before_layers.png'), px=1.5,
                                                     title='BEFORE (current built data): layer classification - offline preview')
    imgs['top_before'] = raster.render_look(W, view, os.path.join(out, 'top_before.png'), None, px=1.5,
                                            title='BEFORE: current built data, seen from above - offline preview')
    for d, P in pilots.items():
        imgs[f'top_{d}'] = raster.render_look(W, view, os.path.join(out, f'top_{d}.png'), P, px=1.5,
                                              title=f'DESIGN {d}: offline pilot (not built) - offline preview')
    if 'A' in pilots and 'B' in pilots:
        im = raster.side_by_side(imgs['top_before'], imgs['top_A'], os.path.join(out, '_tmp.png'))
        raster.side_by_side(im, imgs['top_B'], os.path.join(out, 'top_before_A_B.png'))
        os.remove(os.path.join(out, '_tmp.png'))
    cmp_ = dict(before=dict(shoulders=shoulders_view.shoulder_report(W, area), drive=shoulders_view.offset_drive(W, area)))
    for d, P in pilots.items():
        cmp_[d] = dict(parts=data[d]['parts'], checks={k: v for k, v in data[d]['checks'].items() if not k.endswith('_bad')},
                       shoulders=shoulders_view.shoulder_report(W, area, P), drive=shoulders_view.offset_drive(W, area, P))
    with open(os.path.join(out, 'compare.json'), 'w', encoding='utf-8') as f:
        json.dump(cmp_, f, ensure_ascii=False, indent=1, default=str)
    paths = scene.export(W, pilots, out)
    if 'B' in pilots:                       # Studio data modules for PattayaRoadVisBuilder (design B)
        from tools.roadvis import export_luau
        lx = export_luau.export(W, pilots['B'], os.path.join(out, 'roblox'))
        log(f"luau data: {lx['modules']} modules, {lx['parts']} parts, replace list {lx['replace']}")
    if art:
        from PIL import Image
        ad = os.path.join(REPO, 'art', 'roadvis')
        os.makedirs(ad, exist_ok=True)
        for k in ['top_before_layers', 'top_before'] + [f'top_{d}' for d in pilots] + (['top_before_A_B'] if len(pilots) == 2 else []):
            img = Image.open(os.path.join(out, k + '.png')).convert('RGB')
            if img.width > 1500:
                img = img.resize((1500, int(img.height * 1500 / img.width)))
            img.save(os.path.join(ad, k + '.png'), optimize=True)
    for d in pilots:
        log(f"design {d}: parts replaced {data[d]['parts']['before_replaced_total']} -> {data[d]['parts']['after_total']}; "
            f"wheel unsupported before {data[d]['checks']['wheel_before']['unsupported']} -> {data[d]['checks']['wheel_after']['unsupported']} "
            f"of {data[d]['checks']['wheel_after']['samples']}")
    log(f'{round(time.time() - t, 1)} s; scenes {paths}')
    return W, pilots, data, cmp_


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['analyze', 'pilot', 'compose'])
    ap.add_argument('--city', action='store_true')
    ap.add_argument('--art', action='store_true')
    ap.add_argument('--build-root')
    a = ap.parse_args(argv)
    if a.cmd == 'analyze':
        analyze.main((['--city'] if a.city else []) + (['--build-root', a.build_root] if a.build_root else []))
    elif a.cmd == 'compose':
        rd = os.path.join(world.find_build_root(a.build_root), 'roadvis', 'renders_local')
        for p_ in raster.compose_cams(rd, os.path.join(REPO, 'art', 'roadvis')):
            print('wrote', p_)
    else:
        run_pilot(a.build_root, a.art)


if __name__ == '__main__':
    main()
