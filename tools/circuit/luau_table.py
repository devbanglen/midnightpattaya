"""Minimal reader for the generated circuit data modules (roblox/data/circuits/<id>.luau): `return { ... }` with
nested table constructors, `key = value` fields, numbers, strings, true/false/nil. Comments (`--`) are skipped.
Arrays become lists, keyed tables dicts (a table with both keeps the positional items under '_list')."""
import re

_TOK = re.compile(r'\s+|--\[\[.*?\]\]|--[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}=,;\[\]]|'
                  r'-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[A-Za-z_][A-Za-z_0-9]*', re.S)


def _unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if n.isdigit():
                j = i + 1
                while j < len(s) and j < i + 4 and s[j].isdigit():
                    j += 1
                out.append(chr(int(s[i + 1:j])))
                i = j
                continue
            out.append({'n': '\n', 't': '\t', 'r': '\r'}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def tokens(src):
    pos, out = 0, []
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m:
            raise ValueError(f'bad token at {pos}: {src[pos:pos + 30]!r}')
        t = m.group(0)
        pos = m.end()
        if not (t.isspace() or t.startswith('--')):
            out.append(t)
    return out


def loads(src):
    toks = tokens(src)
    val, _ = _value(toks, toks.index('return') + 1)
    return val


def _value(t, i):
    x = t[i]
    if x == '{':
        return _table(t, i + 1)
    if x[0] in '"\'':
        return _unescape(x[1:-1]), i + 1
    if x in ('true', 'false', 'nil'):
        return {'true': True, 'false': False, 'nil': None}[x], i + 1
    v = float(x)
    return (int(v) if v.is_integer() and '.' not in x and 'e' not in x.lower() else v), i + 1


def _table(t, i):
    lst, dct = [], {}
    while t[i] != '}':
        if t[i] == '[':
            k, i = _value(t, i + 1)
            assert t[i] == ']' and t[i + 1] == '='
            v, i = _value(t, i + 2)
            dct[k] = v
        elif t[i + 1] == '=' and re.match(r'[A-Za-z_]', t[i]):
            key = t[i]
            v, i = _value(t, i + 2)
            dct[key] = v
        else:
            v, i = _value(t, i)
            lst.append(v)
        if t[i] in ',;':
            i += 1
    if dct and lst:
        dct['_list'] = lst
        return dct, i + 1
    return (dct if dct else lst), i + 1


def load(path):
    with open(path, encoding='utf-8') as f:
        return loads(f.read())
