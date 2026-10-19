"""Keeps the Studio runner (roblox/src/ServerStorage/PattayaQARunner.luau) in sync with the repo, and checks it is
read-only: its expected remotes / scripts / budgets are derived from the sources here, and it calls no API that
changes the world."""
import glob
import os
import re
import unittest

import _qa
import test_remotes_contract as RC

RUNNER = _qa.src('ServerStorage/PattayaQARunner.luau')
CODE = _qa.strip_comments(RUNNER)


def lua_map(name):
    body = re.search(rf'QA\.{name} = \{{(.*?)\n?\}}', RUNNER, re.S).group(1)
    return dict(re.findall(r'(\w+) = "(\w+)"', body))


def lua_list(name):
    body = re.search(rf'QA\.{name} = \{{(.*?)\}}', RUNNER, re.S).group(1)
    return re.findall(r'"(\w+)"', body)


def lua_num(name):
    return int(re.search(rf'QA\.{name} = (\d+)', RUNNER).group(1))


class RunnerSync(unittest.TestCase):
    def test_remotes_match_server_sources(self):
        srv = RC.server_remotes()
        want = {n: next(iter(d['class'])) for n, d in srv.items() if n != 'PerfTelemetry'}
        self.assertEqual(lua_map('REMOTES'), want)
        self.assertEqual(lua_map('ROOT_REMOTES'), {'PerfTelemetry': 'RemoteEvent'})

    def test_script_lists_match_repo(self):
        server = sorted(os.path.basename(p)[:-len('.server.luau')]
                        for p in glob.glob(os.path.join(_qa.SRC, 'ServerScriptService', '*.server.luau')))
        client = sorted(os.path.basename(p)[:-len('.client.luau')]
                        for p in glob.glob(os.path.join(_qa.SRC, 'StarterPlayer', 'StarterPlayerScripts', '*.client.luau')))
        self.assertEqual(sorted(lua_list('SERVER_SCRIPTS')), server)
        self.assertEqual(sorted(lua_list('CLIENT_SCRIPTS')), client)

    def test_chunk_caps_match_configs(self):
        caps = {k: int(v) for k, v in re.findall(r'(\w+) = (\d+)',
                                                  re.search(r'QA\.CHUNK_CAPS = \{(.*?)\}', RUNNER).group(1))}
        cfg = lambda n: _qa.load_json(os.path.join(_qa.CONFIG, n + '.json'))
        self.assertEqual(caps['VisSliceChunks'], cfg('vis_slice')['max_parts_per_chunk'])
        self.assertEqual(caps['FurnitureChunks'], cfg('furniture')['budget']['max_parts_per_chunk'])
        self.assertEqual(caps['CoastChunks'], cfg('coast')['max_parts_per_chunk'])
        self.assertEqual(caps['ApronChunks'], cfg('aprons')['budget']['max_parts_per_chunk'])
        self.assertEqual(caps['LandmarkChunks'], cfg('landmarks')['max_parts_per_landmark'])

    def test_expected_counts_match_data(self):
        race = _qa.load_json(_qa.need_build('central_pattaya', 'layout.json'))['race']
        self.assertEqual(lua_num('CENTRAL_CHECKPOINTS'), len(race['checkpoints']))
        import _circuit_harness as H
        self.assertEqual(lua_num('BIRA_GATES'), H.run()['C']['bira']['gates'])

    def test_folder_names_exist_in_builders(self):
        """The PattayaWorld folder names the runner counts are the ones the builders create."""
        builders = ''.join(_qa.read(p) for p in glob.glob(os.path.join(_qa.SRC, 'ServerStorage', '*Builder.luau')))
        for name in re.findall(r'(\w+Chunks) = \d+', re.search(r'QA\.CHUNK_CAPS = \{(.*?)\}', RUNNER).group(1)):
            self.assertIn(f'"{name}"', builders, name)

    def test_read_only(self):
        forbidden = [r':Destroy\(', r'Instance\.new\(', r':SetAttribute\(', r'\.Parent\s*=[^=]', r':PivotTo\(',
                     r':Fire(Client|AllClients|Server)?\(', r':Invoke(Server|Client)?\(', r'\.CFrame\s*=[^=]',
                     r':ClearAllChildren\(', r'\bS\.(start|seat|teleport|publish\w*|set\w+|startEvent)\(',
                     r'\bP\.(apply|applyLOD|revert)\(', r'\.Value\s*=[^=]', r':BulkMoveTo\(', r':SetNetworkOwner',
                     r'workspace\.\w+\s*=[^=]', r'\bLighting\b']
        hits = [p for p in forbidden if re.search(p, CODE)]
        self.assertEqual(hits, [], 'PattayaQARunner must not change the world')

    def test_runner_compiles(self):
        exe = _qa.find_luau('luau-compile')
        if not exe:
            self.skipTest('luau-compile not found')
        import subprocess
        r = subprocess.run([exe, '--null', os.path.join(_qa.SRC, 'ServerStorage', 'PattayaQARunner.luau')],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)


if __name__ == '__main__':
    unittest.main()
