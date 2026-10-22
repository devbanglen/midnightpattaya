"""Road B for the whole city, batch by batch: one command (OFFLINE; nothing touches Studio).

  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py plan [--limit N]
      -> build/roadcity/plan.json, plan_batches.csv: every batch in build order with its numbers (parts added and
         moved, net instances, Atomic cells, frontier pieces, ground columns), the city totals
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py map [--art]
      -> build/roadcity/plan_map.png, plan_map_city.png (and art/roadcity/plan_map_city.png with --art)
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py batch b001 [--art]
      -> build/roadcity/b001/: roblox_rv/ (ServerStorage.PattayaDataRoadVis_b001), roblox_ground/manifest.luau
         (ServerStorage.PattayaDataRoadGround_b001), qa.json (offline QA), drives.json (TestKit paths), previews;
         build/roadcity/noraise/PattayaDataRoadGroundNoRaise.luau
  D:\\ROBLOXRACE\\.venv\\Scripts\\python tools\\roadvis\\city_cli.py bundle b001 [b003 ...] [--no-builders] [--rv-only]
      -> build/roadcity/b001/install/: roadcity_b001.json + install_b001.luau (served by tools/studio/serve.ps1);
         several ids -> build/roadcity/install_<first>_<last>/
docs/ROAD_B_CITY_ROLLOUT.md explains the batches, the numbers and the Studio procedure.
"""
import argparse
import csv
import json
import os
import pickle
import sys
import time
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from shapely.geometry import box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

from tools.roadvis import city, city_export, city_ground, city_qa, ground, world  # noqa: E402


def out_root(build_root=None):
    return os.path.join(world.find_build_root(build_root), 'roadcity')


def load(build_root=None, log=print):
    CW = city.CityWorld(build_root, log=log)
    plan = city.plan_city(CW, log=log)
    nr = city_ground.NoRaise(CW.broot, log=log)
    return CW, plan, nr


def ground_plan_for(nr, res, G0=None):
    """the batch's ground plan with its materials; G0 = its level plan made before the batch (option B), reused"""
    I = res['ideal']
    paved = unary_union([I['S'], I['walk'], I['islands']])
    if G0 is not None:
        return city_ground.add_materials(G0, paved=paved, blds=I['blds'])
    return city_ground.plan(res['box'], nr, paved=paved, blds=I['blds'])


def run_batches(CW, plan, nr, upto=None, limit=None, write_dir=None, log=print, keep_ideal=None, cfg=None, only=None):
    """make every batch in plan order (up to `upto` included, or `limit` batches): returns (state, rows, results).
    write_dir: also write each batch's Studio data (roblox_rv) there (sizes are measured on the written text)."""
    st = city.new_state(CW)
    rows, results = [], {}
    gplans = {'pilot': city_ground.pilot_plan(nr)}
    for n, b in enumerate(plan['batches']):
        if limit is not None and n >= limit:
            break
        t = time.time()
        before = dict(replaced_old=set(st['replaced_old']))
        # the batch's ground levels first (they do not depend on Road B): option B drops the invisible supports where
        # this plan, the pilot's raise or a batch raised before puts the ground at the plateau
        G0 = city_ground.plan(b['box'], nr)
        res = city.make_batch(CW, plan, st, b, cfg=cfg, ground_full=city_ground.FullTest([G0] + list(gplans.values())))
        x = city_export.export(CW, plan, res, os.path.join(write_dir, b['id'], 'roblox_rv') if write_dir else None, write=bool(write_dir))
        poles = []
        if write_dir:
            from tools.roadvis import city_batch
            BXb = box(*city.wloc(b['box']))
            with open(os.path.join(write_dir, b['id'], 'fixture.json'), 'w', encoding='utf-8') as f:
                json.dump(dict(batch=b['id'], box=b['box'], old=city_batch.fixture(CW, before, res, BXb)), f)
            poles = city_batch.poles_on_islands(CW, res, BXb)
        G = ground_plan_for(nr, res, G0)
        gplans[b['id']] = G
        moved = len(res['rep_old']) + len(res['rep_pilot']) + sum(f['n'] for f in res['rep_front'])
        rows.append(dict(id=b['id'], group=b['group'], cells=len(b['cells']), box=b['box'], added=x['parts'], moved=moved,
                         net=x['parts'] - moved, own=x['own'], completion=x['completion'], frontier=x['frontier'], segs=x['segs'],
                         optional=x['optional'], atomic_cells=x['cells'], max_cell_parts=x['maxCellParts'], modules=x['modules'],
                         max_module_kb=x['maxModuleKB'], data_kb=None, probe_samples=x['probeSamples'],
                         replaced_old=len(res['rep_old']), replaced_pilot=len(res['rep_pilot']), replaced_frontier=sum(f['n'] for f in res['rep_front']),
                         ground_written=G['counts']['written'], ground_plateau=G['counts']['plateau'],
                         ground_never_raise=G['counts']['never_raise'], ground_plateau_lowered=G['counts']['plateau_lowered'],
                         byKind=x['byKind'], replaceByName=x['replaceByName'], frontierFor=x['frontierFor'],
                         neighbours=res['neighbours'], poles_on_islands=sum(1 for p in poles if p['on'] == 'island'),
                         poles_in_asphalt=sum(1 for p in poles if p['on'] == 'asphalt'), poles=poles,
                         supports_dropped=res.get('dropped', {}).get('support', 0),
                         secs=round(time.time() - t, 1)))
        if keep_ideal is None or b['id'] not in keep_ideal:
            res['ideal'] = dict(chains=res['ideal']['chains'], rib=res['ideal']['rib'], cfg=res['ideal']['cfg'],
                                blds=res['ideal']['blds'], S=res['ideal']['S'], walk=res['ideal']['walk'],
                                islands=res['ideal']['islands'], crossings=res['ideal']['crossings'])
        results[b['id']] = res
        log(f"{b['id']} {b['group'][:12]:12s} cells {len(b['cells'])}: +{x['parts']} parts (own {x['own']}, completion "
            f"{x['completion']}, frontier {x['frontier']}, segs {x['segs']}), moved {moved}, net {x['parts'] - moved:+d}; "
            f"Atomic cells {x['cells']} (max {x['maxCellParts']}); ground {G['counts']['written']} columns; {rows[-1]['secs']} s")
        if upto is not None and b['id'] == upto:
            break
    return st, rows, results, gplans


def cmd_plan(build_root=None, limit=None, log=print, variant=city.DEFAULT_VARIANT):
    t0 = time.time()
    CW, plan, nr = load(build_root, log=log)
    out = out_root(build_root)
    os.makedirs(out, exist_ok=True)
    main = variant == city.DEFAULT_VARIANT
    data_dir = os.path.join(out, "data") if main else None
    tag = "" if main else "_" + variant
    st, rows, results, gplans = run_batches(CW, plan, nr, limit=limit, write_dir=data_dir, log=log, cfg=city.VARIANTS[variant])
    # data size per batch (the written roblox_rv text)
    for r in rows:
        d = os.path.join(data_dir, r['id'], 'roblox_rv') if data_dir else ''
        r['data_kb'] = round(sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) / 1024, 1) if d and os.path.isdir(d) else None
    tot = Counter()
    for r in rows:
        for k in ('added', 'moved', 'net', 'own', 'completion', 'frontier', 'segs', 'atomic_cells', 'replaced_old', 'replaced_pilot',
                  'replaced_frontier', 'ground_written', 'ground_plateau', 'ground_never_raise', 'poles_on_islands', 'poles_in_asphalt',
                  'supports_dropped'):
            tot[k] += r[k]
        for k, v in r['byKind'].items():
            tot['kind_' + k] += v
    # frontier pieces still standing at the end (targets never built)
    standing = sum(t['n'] for res in results.values() for t in res['front'] if t['target'] not in set(st['built']))
    left_old = [o for o in CW.old if o['i'] not in st['replaced_old']]
    summary = dict(variant=variant, cfg={k: list(v) if isinstance(v, tuple) else v for k, v in city.VARIANTS[variant].items()},
                   batches=len(rows), groups=dict(Counter(r['group'] for r in rows)), totals=dict(tot),
                   frontier_standing_at_end=standing, old_parts_total=len(CW.old), old_parts_left=len(left_old),
                   old_parts_left_by_kind=dict(Counter(city.CODE_LABEL[o['code']] for o in left_old)),
                   pilot=dict(parts=len(CW.pilot['parts']), replaced_by_city=len(st['replaced_pilot'])),
                   max_cell_parts=max(r['max_cell_parts'] for r in rows), max_batch_added=max(r['added'] for r in rows),
                   split_fix=dict(city.ROBUST), secs=round(time.time() - t0, 1))
    plan_out = dict(plan, summary=summary, rows=rows)
    with open(os.path.join(out, f'plan{tag}.json'), 'w', encoding='utf-8') as f:
        json.dump(plan_out, f, indent=1, default=str)
    with open(os.path.join(out, f'plan_batches{tag}.csv'), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        cols = ['id', 'group', 'cells', 'box', 'added', 'moved', 'net', 'own', 'completion', 'frontier', 'segs', 'atomic_cells',
                'max_cell_parts', 'modules', 'data_kb', 'replaced_old', 'replaced_pilot', 'replaced_frontier', 'optional',
                'ground_written', 'ground_plateau', 'ground_never_raise', 'probe_samples', 'poles_on_islands', 'poles_in_asphalt']
        w.writerow(cols)
        for r in rows:
            w.writerow([('%g..%g x %g..%g' % (r['box'][0], r['box'][2], r['box'][1], r['box'][3])) if c == 'box' else r[c] for c in cols])
    with open(os.path.join(out, f'state_end{tag}.pkl'), 'wb') as f:
        pickle.dump(dict(built=st['built'], replaced_old=st['replaced_old'], replaced_pilot=st['replaced_pilot'],
                         uncertain_old=st['uncertain_old'], uncertain_pilot=st['uncertain_pilot']), f)
    log(f"plan: {summary['batches']} batches, +{tot['added']} parts, moved {tot['moved']}, net {tot['net']:+d}; "
        f"old parts left {summary['old_parts_left']} of {summary['old_parts_total']}; {summary['secs']} s")
    return plan_out


INSTALLER = r'''-- MIDNIGHT PATTAYA: install Road B city batch {bid} (generated by tools/roadvis/city_cli.py bundle {bid}).
-- Run in the Studio command bar (Edit mode) while this folder is served:
--   powershell -File tools\studio\serve.ps1 -Dir build\roadcity\{bid}\install -Port 8765 -Seconds 300
-- It creates or updates these ModuleScripts only (it deletes nothing): ServerStorage.PattayaRoadVisBuilder,
-- ServerStorage.PattayaRoadGroundBuilder, ServerStorage.PattayaDataRoadVis_{bid} ({rv} modules),
-- ServerStorage.PattayaDataRoadGround_{bid} (manifest), ServerStorage.PattayaDataRoadGroundNoRaise.
-- Afterwards require the builders through a Clone() (Edit mode caches required modules):
--   local RV = require(game.ServerStorage.PattayaRoadVisBuilder:Clone())
--   local RG = require(game.ServerStorage.PattayaRoadGroundBuilder:Clone())
local Http = game:GetService("HttpService")
local was = Http.HttpEnabled
Http.HttpEnabled = true
local SS = game:GetService("ServerStorage")
local ok, err = pcall(function()
	local bundle = Http:JSONDecode(Http:GetAsync("http://localhost:8765/roadcity_{bid}.json", true))
	local n, sum = 0, 0
	for key, src in bundle do
		local segs = string.split(key, "/")
		assert(segs[1] == "ServerStorage" and #segs >= 2, "bad key " .. key)
		local parent: Instance = SS
		for i = 2, #segs - 1 do
			local f = parent:FindFirstChild(segs[i])
			if not f then
				f = Instance.new("Folder")
				f.Name = segs[i]
				f.Parent = parent
			end
			parent = f
		end
		local name = segs[#segs]
		local m = parent:FindFirstChild(name)
		if m and not m:IsA("ModuleScript") then
			error(m:GetFullName() .. " exists and is not a ModuleScript: nothing more installed")
		end
		if not m then
			m = Instance.new("ModuleScript")
			m.Name = name
			m.Parent = parent
		end
		(m :: ModuleScript).Source = src
		n += 1
		sum += #src
		if n % 25 == 0 then task.wait() end
	end
	print(("road city {bid}: installed %d modules (%d characters); expected {n} modules"):format(n, sum))
	pcall(function() Http:GetAsync("http://localhost:8765/quit", true) end)
end)
Http.HttpEnabled = was
if not ok then warn("road city {bid} install failed: " .. tostring(err)) end
print("HttpEnabled restored to " .. tostring(Http.HttpEnabled))
'''


def _rv_dir(build_root, bid):
    d = os.path.join(out_root(build_root), bid, 'roblox_rv')
    return d if os.path.isdir(d) else os.path.join(out_root(build_root), 'data', bid, 'roblox_rv')


def cmd_bundle(bids, build_root=None, log=print, builders=True, ground=True):
    """an install bundle for one batch or several (in plan order) and its command-bar installer:
      one batch, default: build/roadcity/<id>/install/roadcity_<id>.json + install_<id>.luau with the two road
          builders, the batch's Road B data, its ground data and the never-raise data (run `batch <id>` first)
      builders=False (--no-builders): the data only (the builders are installed already, e.g. with b001)
      ground=False (--rv-only): Road B data only (e.g. a place copy for the frame-time measurement), from
          build/roadcity/<id>/roblox_rv or the plan's build/roadcity/data/<id>/roblox_rv
      several ids: build/roadcity/install_<first>_<last>/roadcity_<first>_<last>.json
    Keys are "ServerStorage/<Folder>/<module>" like tools/studio/install.ps1; the installer pulls the bundle from
    localhost:8765 (tools/studio/serve.ps1) and creates or updates those ModuleScripts only."""
    if isinstance(bids, str):
        bids = [bids]
    tag = bids[0] if len(bids) == 1 else f'{bids[0]}_{bids[-1]}'
    src = os.path.join(REPO, 'roblox', 'src', 'ServerStorage')
    nr = os.path.join(out_root(build_root), 'noraise', 'PattayaDataRoadGroundNoRaise.luau')
    files = {}
    if builders:
        files['ServerStorage/PattayaRoadVisBuilder'] = os.path.join(src, 'PattayaRoadVisBuilder.luau')
        files['ServerStorage/PattayaRoadGroundBuilder'] = os.path.join(src, 'PattayaRoadGroundBuilder.luau')
    nmods = {}
    for bid in bids:
        rv = _rv_dir(build_root, bid)
        need = [os.path.join(rv, 'manifest.luau')]
        rg = os.path.join(out_root(build_root), bid, 'roblox_ground', 'manifest.luau')
        if ground:
            need += [rg, nr]
        for f in need:
            if not os.path.exists(f):
                raise SystemExit(f'{f} missing: run tools/roadvis/city_cli.py batch {bid} (or plan) first')
        if ground:
            files[f'ServerStorage/PattayaDataRoadGround_{bid}/manifest'] = rg
        mods = sorted(f[:-5] for f in os.listdir(rv) if f.endswith('.luau'))
        nmods[bid] = len(mods)
        for m in mods:
            files[f'ServerStorage/PattayaDataRoadVis_{bid}/{m}'] = os.path.join(rv, m + '.luau')
    if ground:
        files['ServerStorage/PattayaDataRoadGroundNoRaise'] = nr
    if len(bids) == 1 and builders and ground:
        # the original single-batch layout (b001's bundle is made this way)
        def rank(k):
            return 0 if k.endswith('Builder') else 1 if '/PattayaDataRoadGround_' in k else 2 if k.endswith('NoRaise') else 3
        files = {k: files[k] for k in sorted(files, key=lambda k: (rank(k), list(files).index(k)))}
    bundle = {k: open(v, encoding='utf-8').read() for k, v in files.items()}
    big = {k: len(v) for k, v in bundle.items() if len(v) > 190000}
    if big:
        raise SystemExit(f'modules over the 200 KB source limit: {big}')
    d = os.path.join(out_root(build_root), bids[0], 'install') if len(bids) == 1 else os.path.join(out_root(build_root), f'install_{tag}')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f'roadcity_{tag}.json'), 'w', encoding='utf-8') as f:
        json.dump(bundle, f, ensure_ascii=False)
    if len(bids) == 1 and builders and ground:
        text = INSTALLER.replace('{bid}', tag).replace('{rv}', str(nmods[tag])).replace('{n}', str(len(bundle)))
    else:
        what = []
        if builders:
            what += ['ServerStorage.PattayaRoadVisBuilder', 'ServerStorage.PattayaRoadGroundBuilder']
        what += [f'ServerStorage.PattayaDataRoadVis_{b} ({nmods[b]} modules)' for b in bids]
        if ground:
            what += [f'ServerStorage.PattayaDataRoadGround_{b} (manifest)' for b in bids] + ['ServerStorage.PattayaDataRoadGroundNoRaise']
        rel = os.path.relpath(d, os.path.dirname(os.path.dirname(out_root(build_root)))).replace('/', '\\')
        head = (f"-- MIDNIGHT PATTAYA: install Road B city data {tag} (generated by tools/roadvis/city_cli.py bundle "
                f"{' '.join(bids)}{'' if builders else ' --no-builders'}{'' if ground else ' --rv-only'}).\n"
                f"-- Run in the Studio command bar (Edit mode) while this folder is served:\n"
                f"--   powershell -File tools\\studio\\serve.ps1 -Dir {rel} -Port 8765 -Seconds 300\n"
                f"-- It creates or updates these ModuleScripts only (it deletes nothing):\n"
                + ''.join(f'--   {w}\n' for w in what)
                + ('' if builders else '-- The road builders are NOT in this bundle: they are installed already (drift check: same source as the repo).\n'))
        body = INSTALLER[INSTALLER.index('-- Afterwards require the builders'):]
        text = head + body.replace('{bid}', tag).replace('{n}', str(len(bundle)))
    with open(os.path.join(d, f'install_{tag}.luau'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    log(f'{tag}: install bundle {d} ({len(bundle)} modules, {round(sum(len(v) for v in bundle.values()) / 1024)} KB); '
        f'largest module {max(len(v) for v in bundle.values()) // 1024} KB')
    return dict(dir=d, modules=len(bundle))


GROUP_COLOURS = {'Sukhumvit Road': (200, 30, 30), 'Beach Road': (0, 120, 220), 'Second Road': (0, 170, 170),
                 'Pattaya Klang / Central Road': (160, 0, 160), 'North Pattaya Road': (220, 140, 0),
                 'South Pattaya Road': (120, 80, 0), 'Thepprasit Road': (0, 150, 0), 'Jomtien Beach Road': (60, 60, 200),
                 'rest': (165, 165, 165), 'corridor': (120, 120, 60)}


def cmd_map(build_root=None, art_dir=None, log=print):
    """plan_map.png (the whole plan) and plan_map_city.png (the city part): every batch box coloured by its road group
    with its number (main roads), the pilot box in black, batch 1 filled; the road graph in grey. North is up (z+ =
    south, so world z grows downwards in the image)."""
    from PIL import Image, ImageDraw
    CW = city.CityWorld(build_root, log=log)
    plan = city.plan_city(CW, log=log)
    S = 1 / 12.0
    X0, Z0, X1, Z1 = 15400, -9800, 45000, 15800
    w, h = int((X1 - X0) * S), int((Z1 - Z0) * S)
    img = Image.new('RGB', (w, h), (235, 232, 222))
    d = ImageDraw.Draw(img)

    def px(x, z):
        return (x - X0) * S, (z - Z0) * S
    for e in CW.W['graph']['edges']:
        d.line([px(x + city.ORIGIN[0], z) for x, z in e['pts']], fill=(95, 95, 95), width=1)
    b1 = plan['batches'][0]['box']
    d.rectangle([px(b1[0], b1[1]), px(b1[2], b1[3])], fill=(255, 210, 120))
    for b in plan['batches']:
        x0, z0, x1, z1 = b['box']
        q0, q1 = px(x0, z0), px(x1, z1)
        d.rectangle([q0, (q1[0] - 1, q1[1] - 1)], outline=GROUP_COLOURS[b['group']], width=2)
        if b['group'] not in ('rest',):
            d.text((q0[0] + 2, q0[1] + 2), b['id'][1:], fill=GROUP_COLOURS[b['group']])
    x0, z0, x1, z1 = city.PILOT_BOX_WORLD
    d.rectangle([px(x0, z0), px(x1, z1)], outline=(0, 0, 0), width=3)
    y = 8
    for g, c in GROUP_COLOURS.items():
        d.rectangle([(8, y), (22, y + 10)], outline=c, width=2)
        d.text((28, y), g, fill=(0, 0, 0))
        y += 14
    d.text((28, y), 'pilot (black), batch 1 (filled); north is up; 600-stud cells', fill=(0, 0, 0))
    out = out_root(build_root)
    os.makedirs(out, exist_ok=True)
    img.save(os.path.join(out, 'plan_map.png'), optimize=True)
    city_img = img.crop((0, 0, int((29200 - X0) * S), h))
    city_img.save(os.path.join(out, 'plan_map_city.png'), optimize=True)
    made = [os.path.join(out, 'plan_map.png'), os.path.join(out, 'plan_map_city.png')]
    if art_dir:
        os.makedirs(art_dir, exist_ok=True)
        city_img.quantize(64).save(os.path.join(art_dir, 'plan_map_city.png'), optimize=True)
        made.append(os.path.join(art_dir, 'plan_map_city.png'))
    log('plan map: ' + ', '.join(made))
    return made


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['plan', 'batch', 'bundle', 'map'])
    ap.add_argument('ids', nargs='*')
    ap.add_argument('--no-builders', action='store_true')
    ap.add_argument('--rv-only', action='store_true')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--art', action='store_true')
    ap.add_argument('--build-root')
    ap.add_argument('--variant', default=city.DEFAULT_VARIANT, choices=sorted(city.VARIANTS))
    a = ap.parse_args()
    if a.cmd == 'plan':
        cmd_plan(a.build_root, a.limit, variant=a.variant)
    elif a.cmd == 'bundle':
        cmd_bundle(a.ids or ['b001'], a.build_root, builders=not a.no_builders, ground=not a.rv_only)
    elif a.cmd == 'map':
        cmd_map(a.build_root, os.path.join(REPO, 'art', 'roadcity') if a.art else None)
    else:
        from tools.roadvis import city_batch
        city_batch.cmd_batch((a.ids or ['b001'])[0], a.build_root, art=a.art, variant=a.variant)
