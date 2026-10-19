"""Rewrite the generated ASSETS block of roblox/src/ReplicatedStorage/TrafficVehicles.luau from the traffic manifest
(pure Python). assetId values already in the module are kept, so the leader's ids survive a regeneration.
  python tools/blender/traffic/make_traffic_luau.py [build/vis_assets/traffic/manifest.json]"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
MOD = os.path.join(REPO, 'roblox', 'src', 'ReplicatedStorage', 'TrafficVehicles.luau')
BEGIN = '-- BEGIN GENERATED'
END = '-- END GENERATED'


def num(v):
    return ('%.3f' % v).rstrip('0').rstrip('.') if v != int(v) else str(int(v))


def vec(v):
    return '{' + ', '.join(num(x) for x in v) + '}'


def main():
    man_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'build', 'vis_assets', 'traffic', 'manifest.json')
    man = json.load(open(man_path))
    src = open(MOD, encoding='utf8').read()
    ids = dict(re.findall(r'\b(TRF_\w+) = \{assetId = (\d+)', src))
    lines = [BEGIN + ' (tools/blender/traffic/make_traffic_luau.py from build/vis_assets/traffic/manifest.json;',
             '-- assetId values are kept when the block is regenerated)', 'TrafficVehicles.ASSETS = {']
    for a in sorted(man['assets'], key=lambda a: (a['traffic_kind'], a['name'])):
        if not a['ok']:
            raise SystemExit(f'{a["name"]} failed validation: {a["fails"]}')
        n = a['name']
        lines.append(f'\t{n} = {{assetId = {ids.get(n, "0")}, kind = {a["traffic_kind"]}, tris = {a["tris"]}, '
                     f'roofTop = {num(a["roof_top"])}, roofZ = {num(a["roof_z"])}, '
                     f'taxiSign = {"true" if a["taxi_sign"] else "false"},')
        lines.append(f'\t\tsize = {vec(a["size_studs"])}, parts = {{')
        for p in a['parts']:
            short = p['name'].rsplit('_', 1)[1]
            lines.append(f'\t\t\t{short} = {{size = {vec(p["size"])}, centre = {vec(p["centre"])}}},')
        lines.append('\t\t}},')
    lines.append('}')
    i, j = src.index(BEGIN), src.index(END)
    src = src[:i] + '\n'.join(lines) + '\n' + src[j:]
    open(MOD, 'w', encoding='utf8', newline='\n').write(src)
    print(f'wrote {len(man["assets"])} assets into {MOD}')


if __name__ == '__main__':
    main()
