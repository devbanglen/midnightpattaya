"""Static Luau checks: every roblox/src/**/*.luau and roblox/data/**/*.luau compiles with luau-compile (syntax and
compile errors only; no type check). Skipped with a message when luau-compile is not installed."""
import os
import re
import subprocess
import unittest

import _qa


class LuauCompile(unittest.TestCase):
    def test_every_luau_file_compiles(self):
        exe = _qa.find_luau('luau-compile')
        if not exe:
            self.skipTest('luau-compile not found: put it in $LUAU_DIR or ' + _qa.KNOWN_LUAU_DIR)
        files = _qa.luau_files()
        self.assertGreater(len(files), 50, 'expected the whole roblox/src tree')
        bad = []
        for f in files:
            r = subprocess.run([exe, '--null', f], capture_output=True, text=True, encoding='utf-8',
                               errors='replace')
            if r.returncode != 0:
                msg = (r.stderr or r.stdout).strip().splitlines()[:2]
                bad.append(os.path.relpath(f, _qa.ROOT) + ': ' + ' | '.join(msg))
        self.assertEqual(bad, [], f'{len(bad)} of {len(files)} files do not compile')

    def test_script_kinds_match_folders(self):
        """*.server.luau only under ServerScriptService, *.client.luau only under StarterPlayer / ReplicatedFirst,
        plain modules never in ServerScriptService (Rojo/install.ps1 map the suffix to the Script class)."""
        wrong = []
        for f in _qa.luau_files():
            rel = os.path.relpath(f, _qa.SRC).replace('\\', '/')
            if rel.startswith('..'):
                continue
            top = rel.split('/')[0]
            if f.endswith('.server.luau') and top != 'ServerScriptService':
                wrong.append(rel)
            elif f.endswith('.client.luau') and top not in ('StarterPlayer', 'ReplicatedFirst'):
                wrong.append(rel)
            elif not re.search(r'\.(server|client)\.luau$', f) and top == 'ServerScriptService':
                wrong.append(rel)
        self.assertEqual(wrong, [])

    def test_no_duplicate_script_names(self):
        """Two scripts with the same name in one Studio folder would shadow each other on install."""
        seen = {}
        for f in _qa.luau_files():
            rel = os.path.relpath(f, _qa.ROOT).replace('\\', '/')
            folder = os.path.dirname(rel)
            name = re.sub(r'(\.server|\.client)?\.luau$', '', os.path.basename(rel))
            seen.setdefault((folder, name), []).append(rel)
        dups = [v for v in seen.values() if len(v) > 1]
        self.assertEqual(dups, [])


if __name__ == '__main__':
    unittest.main()
