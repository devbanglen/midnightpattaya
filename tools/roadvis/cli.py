"""One command for the road-visual work (OFFLINE ONLY; nothing touches Studio or the existing build outputs).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py analyze [--city]     -> build/roadvis/analysis.json
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py pilot [--art]         -> build/roadvis/pilot_<name>.json,
        build/roadvis/scene_{before,after}.json (Blender input), build/roadvis/top_*.png; --art also copies the small
        top-down previews to art/roadvis/
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py compose         -> art/roadvis/cam_*.png, cmp_*.png from the
        local 3D renders in build/roadvis/renders_local (tools/roadvis/blender_preview.py with the PyPI bpy module)
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py ground [--city] [--art]   -> build/roadground/: the ground
        pilot QA (pilot.json), the Studio data for PattayaRoadGroundBuilder (roblox/), top-down and edge-step previews,
        Blender scenes (scene_ground_*.json); --city adds the city-wide audit (city_audit.json, about 1 min); --art
        copies the small previews to art/roadground/ (tools/roadvis/ground*.py, docs/ROAD_GROUND_PILOT.md)
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\cli.py ground-compose  -> art/roadground/ground_cmp_*.png from the
        local renders in build/roadground/renders_local
Blender preview renders (local PyPI bpy module, EEVEE; the GPU box is paused): docs/ROAD_VISUAL_SPEC.md section 10.
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np

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


def run_ground(build_root=None, art=False, city=False, log=print):
    """the ground pilot on Road B (docs/ROAD_GROUND_PILOT.md): QA today / B / B + ground, Studio data, previews"""
    from tools.roadvis import ground, ground_audit, ground_export, ground_view
    t = time.time()
    cfg = dict(junction.CFG)
    bl = world.world_bbox_local(cfg['bbox_world'])
    W = world.load(build_root, bbox=bl, margin=900.0)          # as run_pilot: the world the Road B export was made from
    out = os.path.join(W['broot'], 'roadground')
    os.makedirs(out, exist_ok=True)
    PB = junction.generate(W, dict(cfg, design='B', name=f"{cfg['name']}_B"), log=lambda *a: None)
    G, states, res = ground.pilot(W, PB, log=log)
    x = ground_export.export(W, PB, G, states, res, os.path.join(out, 'roblox'))
    log(f"luau data: {x['files']}; kerb parts {x['kerbParts']} in {x['cells']} cells; {x['edgeChecks']} edge checks; "
        f"{x['probes']} probes; probe expectation {x['expected']}; largest module {x['maxKB']} KB")
    res['export'] = {k: v for k, v in x.items() if k != 'files'}
    mask = ground_audit.TerrainMask(W['broot'])
    gx0, gz0, gx1, gz1 = G['cfg']['plateau_world']
    reach = G['cfg']['flat'] + G['cfg']['ramp']
    region_l = (gx0 - world.ORIGIN[0] - reach, gz0 - reach, gx1 - world.ORIGIN[0] + reach, gz1 + reach)
    objs, _ = ground_audit.city_objects(W['broot'], W, mask, field=states['B_ground'].ground, bbox=region_l, state=states['B_ground'])
    res['objects'] = {k: v for k, v in objs.items() if k in ('area', 'area_buried', 'area_rows')}
    objs_b, _ = ground_audit.city_objects(W['broot'], W, mask, field=states['B'].ground, bbox=region_l, state=states['B'])
    res['objects_B_without_ground'] = objs_b.get('area_buried')
    cxz = np.array([[a_, b_] for a_ in np.arange(region_l[0] + 2, region_l[2], 4.0) for b_ in np.arange(region_l[1] + 2, region_l[3], 4.0)])
    cells = mask.at(cxz)
    res['no_raise_in_region'] = dict(water_cells=int((cells == 1).sum()), sand_cells=int((cells == 2).sum()), cells=int(len(cells)))
    view = (bl[0] - 40, bl[1] - 40, bl[2] + 40, bl[3] + 40)
    titles = {'today': 'TODAY (before Road B), seen from above - offline preview',
              'B': 'ROAD B (built in Studio 2026-10-22), seen from above - offline preview',
              'B_ground': 'ROAD B + GROUND at y +0.43 (proposed), seen from above - offline preview'}
    looks, steps = [], []
    for name, P_, G_ in (('today', None, None), ('B', PB, None), ('B_ground', PB, G)):
        kerbs = G['kerbs'] if name == 'B_ground' else None
        looks.append(ground_view.top_look(W, P_, G_, states[name], view, os.path.join(out, f'top_{name}.png'), titles[name], kerbs=kerbs))
        im, cnt = ground_view.step_map(W, P_, G_, states[name], PB['area'], view, os.path.join(out, f'steps_{name}.png'),
                                       titles[name].replace('seen from above', 'edge steps'), kerbs=kerbs)
        steps.append(im)
        res.setdefault('step_map', {})[name] = cnt
    ground_view.strip(looks, os.path.join(out, 'top_today_B_ground.png'))
    ground_view.strip(steps, os.path.join(out, 'steps_today_B_ground.png'))
    res['scenes'] = ground_view.scenes(W, PB, G, out)
    if city:
        _, _, ca = ground_audit.run(W['broot'], log=log)
        with open(os.path.join(out, 'city_audit.json'), 'w', encoding='utf-8') as f:
            json.dump(ca, f, indent=1, default=str)
        res['city'] = 'city_audit.json'
    if art:
        from PIL import Image
        ad = os.path.join(REPO, 'art', 'roadground')
        os.makedirs(ad, exist_ok=True)
        for k in ('top_today_B_ground', 'steps_today_B_ground'):
            img = Image.open(os.path.join(out, k + '.png')).convert('RGB')
            if img.width > 1800:
                img = img.resize((1800, int(img.height * 1800 / img.width)))
            img.quantize(128).save(os.path.join(ad, k + '.png'), optimize=True)
    with open(os.path.join(out, 'pilot.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=1, default=str)
    log(f'{round(time.time() - t, 1)} s; wrote {out}')
    return W, PB, G, states, res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['analyze', 'pilot', 'compose', 'ground', 'ground-compose'])
    ap.add_argument('--city', action='store_true')
    ap.add_argument('--art', action='store_true')
    ap.add_argument('--build-root')
    a = ap.parse_args(argv)
    if a.cmd == 'analyze':
        analyze.main((['--city'] if a.city else []) + (['--build-root', a.build_root] if a.build_root else []))
    elif a.cmd == 'ground':
        run_ground(a.build_root, a.art, a.city)
    elif a.cmd == 'ground-compose':
        from tools.roadvis import ground_view
        rd = os.path.join(world.find_build_root(a.build_root), 'roadground', 'renders_local')
        ad = os.path.join(REPO, 'art', 'roadground')
        os.makedirs(ad, exist_ok=True)
        for p_ in ground_view.compose(rd, ad):
            print('wrote', p_)
    elif a.cmd == 'compose':
        rd = os.path.join(world.find_build_root(a.build_root), 'roadvis', 'renders_local')
        for p_ in raster.compose_cams(rd, os.path.join(REPO, 'art', 'roadvis')):
            print('wrote', p_)
    else:
        run_pilot(a.build_root, a.art)


if __name__ == '__main__':
    main()
