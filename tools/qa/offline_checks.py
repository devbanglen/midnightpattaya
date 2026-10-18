"""Offline checks for MIDNIGHT PATTAYA that need no Roblox Studio (owner's overnight priority 4).

    .venv\\Scripts\\python tools\\qa\\offline_checks.py [--no-export]

1. luau-compile every roblox/src/**/*.luau and build/vis_slice/roblox/*.luau (syntax). Needs luau-compile.exe from
   https://github.com/luau-lang/luau/releases on PATH, in tools/luau/, or in a Claude scratchpad/luau folder.
2. Asset manifest consistency: build/vis_assets/manifest.json names == upload_ids.json names ==
   roblox/src/ServerStorage/VisAssetsManifest.luau names, every id numeric and unique.
3. vis_slice export determinism: run tools/mapgen/vis_slice.py twice and compare the output file hashes
   (skipped with --no-export); the exporter's own footprint checks must all be 0 in its log.
4. Rollback inventory: the Remove/Restore entry points and the Legacy / off switches still exist.
Exit code 1 if any check fails. Prints a short table; no mock data, every line is measured.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
fails = []


def find_luau_compile():
    cands = [shutil.which('luau-compile'), os.path.join(ROOT, 'tools', 'luau', 'luau-compile.exe')]
    tmp = os.environ.get('TEMP', '')
    cands += glob.glob(os.path.join(tmp, 'claude', '*', '*', 'scratchpad', 'luau', 'luau-compile.exe'))
    cands += ['/tmp/luaudl/bin/luau-compile.exe', os.path.join(tmp, 'luaudl', 'bin', 'luau-compile.exe')]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def check_luau():
    exe = find_luau_compile()
    files = glob.glob(os.path.join(ROOT, 'roblox', 'src', '**', '*.luau'), recursive=True)
    files += glob.glob(os.path.join(ROOT, 'build', 'vis_slice', 'roblox', '*.luau'))
    if not exe:
        print(f'luau-compile: NOT FOUND (skipped {len(files)} files)')
        return
    bad = 0
    for f in files:
        r = subprocess.run([exe, f], capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            bad += 1
            msg = (r.stderr or r.stdout).strip().splitlines()[:2]
            fails.append(f'luau-compile {os.path.relpath(f, ROOT)}: ' + ' | '.join(msg))
    print(f'luau-compile: {len(files) - bad}/{len(files)} files compile')


def manifest_names(man):
    a = man.get('assets')
    if isinstance(a, dict):
        return set(a.keys())
    if isinstance(a, list):
        return {x['name'] for x in a}
    return {k for k in man.keys() if k.startswith(('BLD_', 'RSD_', 'RC_'))}


def check_manifest():
    mj = os.path.join(ROOT, 'build', 'vis_assets', 'manifest.json')
    up = os.path.join(ROOT, 'build', 'vis_assets', 'upload_ids.json')
    lu = os.path.join(ROOT, 'roblox', 'src', 'ServerStorage', 'VisAssetsManifest.luau')
    if not (os.path.exists(mj) and os.path.exists(up)):
        print('asset manifest: build/vis_assets missing (skipped)')
        return
    names = manifest_names(json.load(open(mj, encoding='utf-8')))
    ids = json.load(open(up, encoding='utf-8'))
    luau_ids = dict(re.findall(r'\["([A-Za-z0-9_]+)"\]\s*=\s*(\d+)', open(lu, encoding='utf-8').read()))
    problems = []
    if names != set(ids):
        problems.append(f'manifest vs upload_ids names differ: {sorted(names ^ set(ids))[:6]}')
    if set(ids) != set(luau_ids):
        problems.append(f'upload_ids vs VisAssetsManifest.luau names differ: {sorted(set(ids) ^ set(luau_ids))[:6]}')
    for k, v in ids.items():
        if not str(v).isdigit():
            problems.append(f'{k}: id not numeric ({v})')
        if k in luau_ids and str(v) != luau_ids[k]:
            problems.append(f'{k}: id differs json {v} vs luau {luau_ids[k]}')
    if len(set(ids.values())) != len(ids):
        problems.append('duplicate asset ids')
    for pr in problems:
        fails.append('asset manifest: ' + pr)
    print(f'asset manifest: {len(names)} assets, {len(ids)} ids, {len(luau_ids)} in Luau, {len(problems)} problems')


def hash_dir(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, '*.luau'))):
        out[os.path.basename(f)] = hashlib.sha256(open(f, 'rb').read()).hexdigest()
    return out


def check_export():
    py = sys.executable
    script = os.path.join(ROOT, 'tools', 'mapgen', 'vis_slice.py')
    cfg = os.path.join(ROOT, 'tools', 'mapgen', 'config', 'vis_slice.json')
    out_dir = os.path.join(ROOT, 'build', 'vis_slice', 'roblox')
    if not os.path.exists(script):
        print('vis_slice export: script missing (skipped)')
        return
    hashes = []
    log = ''
    for _ in range(2):
        r = subprocess.run([py, script, cfg], capture_output=True, text=True, cwd=ROOT, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            fails.append('vis_slice export failed: ' + (r.stderr.strip().splitlines() or ['?'])[-1])
            print('vis_slice export: FAILED')
            return
        log = r.stdout
        hashes.append(hash_dir(out_dir))
    same = hashes[0] == hashes[1]
    if not same:
        fails.append('vis_slice export is not deterministic (file hashes differ between two runs)')
    m = re.search(r'checks: (.*)', log)
    nonzero = []
    if m:
        for part in m.group(1).split(','):
            k, _, v = part.strip().rpartition(' ')
            if v.isdigit() and int(v) != 0:
                nonzero.append(part.strip())
    else:
        fails.append('vis_slice export log has no "checks:" line')
    if nonzero:
        fails.append('vis_slice footprint checks not 0: ' + ', '.join(nonzero))
    print(f'vis_slice export: deterministic={same}, {len(hashes[0])} modules, footprint checks '
          f'{"all 0" if not nonzero else nonzero}')


def check_rollback():
    want = {
        'roblox/src/ServerStorage/PattayaVisSliceBuilder.luau': ['function Builder.Remove', 'RestoreReplaced'],
        'roblox/src/ServerStorage/VisMeshBuilder.luau': ['function M.RemoveMesh'],
        'roblox/src/StarterPlayer/StarterPlayerScripts/PattayaNightLights.client.luau': ['Legacy ='],
        'roblox/src/StarterPlayer/StarterPlayerScripts/PattayaRoadLook.client.luau': ['"off"'],
    }
    ok = 0
    for rel, needles in want.items():
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            fails.append(f'rollback: {rel} missing')
            continue
        src = open(p, encoding='utf-8').read()
        for n in needles:
            if n in src:
                ok += 1
            else:
                fails.append(f'rollback: {rel} lacks "{n}"')
    print(f'rollback entry points: {ok} present')


if __name__ == '__main__':
    check_luau()
    check_manifest()
    if '--no-export' not in sys.argv:
        check_export()
    check_rollback()
    if fails:
        print('\nFAILED:')
        for f in fails:
            print(' - ' + f)
        sys.exit(1)
    print('\nALL CHECKS PASSED')
