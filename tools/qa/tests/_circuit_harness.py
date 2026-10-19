"""Runs the REAL CircuitRegistry.compile, CheckpointValidator and LapTimingService on the real circuit data
(roblox/data/circuits/*.luau) with the luau CLI and parses the printed facts. Cached per process."""
import os

import _qa

_CACHE = {}
MODULES = ['CircuitRegistry', 'CheckpointValidator', 'LapTimingService']


def _wrap(name, source, require_map=None):
    head = ''
    if require_map:
        pairs = ', '.join(f'{k} = {v}' for k, v in require_map.items())
        head = f'local __mods = {{{pairs}}}\nlocal require = function(x) return __mods[x] or error("no mock module " .. tostring(x)) end\n'
    return f'local {name} = (function(...)\n{head}{source}\nend)()\n'


def circuit_ids():
    d = os.path.join(_qa.ROOT, 'roblox', 'data', 'circuits')
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.luau'))


def run():
    if 'out' in _CACHE:
        return _CACHE['out']
    sources = {m: _qa.src(os.path.join('ServerStorage', m + '.luau')) for m in MODULES}
    parts = [_qa.read(os.path.join(_qa.HERE, 'luau', 'prelude.luau'))]
    parts.append(_wrap('Registry', sources['CircuitRegistry']))
    parts.append(_wrap('Validator', sources['CheckpointValidator'], {'CircuitRegistry': 'Registry'}))
    parts.append(_wrap('Timing', sources['LapTimingService']))
    ids = circuit_ids()
    parts.append('local DEFS = {}\n')
    for cid in ids:
        data = _qa.read(os.path.join(_qa.ROOT, 'roblox', 'data', 'circuits', cid + '.luau'))
        parts.append(f'DEFS["{cid}"] = (function()\n{data}\nend)()\n')
    parts.append('local IDS = {' + ', '.join(f'"{i}"' for i in ids) + '}\n')
    parts.append(_qa.read(os.path.join(_qa.HERE, 'luau', 'circuit_tail.luau')))
    code, out = _qa.run_luau(''.join(parts))
    res = {'code': code, 'raw': out, 'C': {}, 'G': {}, 'GRID': {}, 'PIT': {}, 'ENT': {}, 'RUN': {}, 'ERR': {},
           'WARN': []}
    for line in out.splitlines():
        f = line.split('\t') if '\t' in line else line.split()
        if not f:
            continue
        k = f[0]
        if k == 'C':
            cid = f[1]
            res['C'][cid] = dict(n=int(f[2]), len=float(f[3]), lengthStuds=float(f[4]), gates=int(f[5]),
                                 s1=float(f[6]), s2=float(f[7]))
        elif k == 'G':
            res['G'].setdefault(f[1], []).append(dict(i=int(f[2]), s=float(f[3]), line=int(f[4]),
                                                      half=float(f[5]), bypass=f[6] == '1',
                                                      pitLat=None if f[7] == 'nil' else float(f[7])))
        elif k == 'GRID':
            res['GRID'].setdefault(f[1], []).append(tuple(float(x) for x in f[3:8]))
        elif k == 'PIT':
            res['PIT'][f[1]] = dict(zip(['width', 'len', 'entryS', 'exitS', 'trackEntryS', 'trackExitS', 'limit'],
                                        map(float, f[2:9])))
        elif k == 'ENT':
            res['ENT'][f[1]] = tuple(float(x) for x in f[2:5])
        elif k == 'RUN':
            kv = {}
            for item in ' '.join(f[3:]).split():
                a, _, b = item.partition('=')
                kv[a] = b
            res['RUN'].setdefault(f[1], {})[f[2]] = kv
        elif k == 'ERR':
            res['ERR'][f[1]] = ' '.join(f[2:])
        elif k == 'WARN':
            res['WARN'].append(' '.join(f[1:]))
    _CACHE['out'] = res
    return res
