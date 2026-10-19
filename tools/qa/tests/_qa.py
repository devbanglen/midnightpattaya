"""Shared helpers for the offline QA tests (tools/qa/tests). Standard library only.

Paths:
  ROOT   repo checkout that holds these tests (roblox/src, docs, tools)
  BUILD  generated map outputs (gitignored): $MP_BUILD_DIR, else ROOT/build, else the main checkout's build/ when the
         tests run from a worktree under <main>/.claude/worktrees/<name>
Luau CLI: $LUAU_DIR, the known Claude scratchpad folder, any Claude scratchpad/luau folder under %TEMP%, tools/luau/,
or PATH. Tests that need it are skipped with a clear message when it is missing.
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC = os.path.join(ROOT, 'roblox', 'src')
DOCS = os.path.join(ROOT, 'docs')
CONFIG = os.path.join(ROOT, 'tools', 'mapgen', 'config')


def _find_build():
    env = os.environ.get('MP_BUILD_DIR')
    if env and os.path.isdir(env):
        return env
    own = os.path.join(ROOT, 'build')
    if os.path.isdir(own):
        return own
    parts = os.path.normpath(ROOT).split(os.sep)
    if '.claude' in parts:
        main = os.sep.join(parts[:parts.index('.claude')])
        cand = os.path.join(main, 'build')
        if os.path.isdir(cand):
            return cand
    return None


BUILD = _find_build()

KNOWN_LUAU_DIR = (r'C:/Users/src3r/AppData/Local/Temp/claude/D--ROBLOXRACE/'
                  r'13fa2bc9-cdf0-4f9f-857d-7126dc2df433/scratchpad/luau')


def find_luau(tool='luau'):
    """Path to luau.exe / luau-compile.exe, or None."""
    exe = tool + ('.exe' if os.name == 'nt' else '')
    dirs = [os.environ.get('LUAU_DIR'), KNOWN_LUAU_DIR, os.path.join(ROOT, 'tools', 'luau')]
    tmp = os.environ.get('TEMP', '')
    dirs += glob.glob(os.path.join(tmp, 'claude', '*', '*', 'scratchpad', 'luau'))
    for d in dirs:
        if d and os.path.exists(os.path.join(d, exe)):
            return os.path.join(d, exe)
    return shutil.which(tool)


def need_build(*rel):
    """Path under BUILD; skips the test when build/ (or that file) is not there."""
    if not BUILD:
        raise unittest.SkipTest('build/ not found (set MP_BUILD_DIR to the generated map outputs)')
    p = os.path.join(BUILD, *rel)
    if not os.path.exists(p):
        raise unittest.SkipTest(f'{os.path.join("build", *rel)} missing')
    return p


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def src(rel):
    return read(os.path.join(SRC, rel))


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def luau_table(path):
    """Parses a data-only Luau module (`return { ... }`) with tools/circuit/luau_table.py."""
    sys.path.insert(0, os.path.join(ROOT, 'tools', 'circuit'))
    try:
        import luau_table
    finally:
        sys.path.pop(0)
    return luau_table.load(path)


def luau_files():
    return sorted(glob.glob(os.path.join(SRC, '**', '*.luau'), recursive=True)
                  + glob.glob(os.path.join(ROOT, 'roblox', 'data', '**', '*.luau'), recursive=True))


def run_luau(main_source, files=None, timeout=180):
    """Runs a Luau script with the luau CLI in a temp folder (files = {name: source} written next to it).
    Returns (returncode, stdout+stderr). Skips the test when the CLI is missing."""
    exe = find_luau('luau')
    if not exe:
        raise unittest.SkipTest('luau CLI not found (set LUAU_DIR; https://github.com/luau-lang/luau/releases)')
    work = tempfile.mkdtemp(prefix='mpqa_')
    try:
        for name, text in (files or {}).items():
            with open(os.path.join(work, name), 'w', encoding='utf-8', newline='\n') as f:
                f.write(text.replace('\r', ''))
        with open(os.path.join(work, 'main.luau'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(main_source.replace('\r', ''))
        r = subprocess.run([exe, 'main.luau'], cwd=work, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    finally:
        shutil.rmtree(work, ignore_errors=True)


def dist2(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def polyline_length(pts, closed=False):
    n = sum(dist2(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    return n + (dist2(pts[-1], pts[0]) if closed else 0)


def point_seg_dist(p, a, b):
    ax, az = a[0], a[1]
    dx, dz = b[0] - ax, b[1] - az
    l2 = dx * dx + dz * dz
    t = 0 if l2 <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / l2))
    return math.hypot(p[0] - (ax + dx * t), p[1] - (az + dz * t))


def dist_to_polyline(p, pts, closed=False):
    n = len(pts)
    m = n if closed else n - 1
    return min(point_seg_dist(p, pts[i], pts[(i + 1) % n]) for i in range(m))


def strip_comments(luau):
    """Luau source without -- comments (block and line). Strings are kept (a '--' inside a string is rare here)."""
    luau = re.sub(r'--\[(=*)\[.*?\]\1\]', '', luau, flags=re.S)
    return re.sub(r'--[^\n]*', '', luau)
