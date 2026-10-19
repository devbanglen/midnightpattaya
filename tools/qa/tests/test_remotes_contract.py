"""Static client/server remote contract over roblox/src (grep based, comments stripped):
- every RemoteEvent / RemoteFunction a *.client.luau waits for is created by a server script or server module;
- a remote the client fires (FireServer / InvokeServer) has a server listener (OnServerEvent / OnServerInvoke);
- a remote the client listens to (OnClientEvent) is fired by the server (FireClient / FireAllClients / fireClient);
- every remote the server creates is used by some client (no dead remotes) and has one class everywhere.
Covers Missions (jobs), Events, Challenges / Road Fight, Sprint, GPS, Garage, Circuit, Race, telemetry."""
import os
import re
import unittest

import _qa


def files(pred):
    out = {}
    for f in _qa.luau_files():
        rel = os.path.relpath(f, _qa.SRC).replace('\\', '/')
        if not rel.startswith('..') and pred(rel):
            out[rel] = _qa.strip_comments(_qa.read(f))
    return out


SERVER = files(lambda r: r.startswith(('ServerScriptService/', 'ServerStorage/'))
               and 'TestKit' not in r and not r.endswith('Test.luau'))
CLIENT = files(lambda r: r.endswith('.client.luau'))

CALL = r'(?:remotes|ReplicatedStorage)\s*:\s*(?:WaitForChild|FindFirstChild)\(\s*"(\w+)"'


def server_remotes():
    """name -> {'class': set, 'files': set, 'vars': {(file, var)}}"""
    out = {}

    def add(name, cls, f, var):
        d = out.setdefault(name, {'class': set(), 'files': set(), 'vars': set()})
        d['class'].add(cls)
        d['files'].add(f)
        if var:
            d['vars'].add((f, var))

    for f, s in SERVER.items():
        # local function remote(name) ... Instance.new("RemoteEvent") ... end  +  local X = remote("Name")
        helper = re.search(r'local function (\w+)\(name: string\)[^\n]*\n(?:.*\n){0,6}?.*Instance\.new\("(Remote\w+)"\)', s)
        if helper:
            for var, name in re.findall(rf'local (\w+) = {helper.group(1)}\("(\w+)"\)', s):
                add(name, helper.group(2), f, var)
        # a module's helper re-used: local remote = StreetRace.remote  ->  local X = remote("Name")
        for alias in re.findall(r'local (\w+) = \w+\.remote\b', s):
            for var, name in re.findall(rf'local (\w+) = {alias}\("(\w+)"\)', s):
                add(name, 'RemoteEvent', f, var)
        # local X = parent:FindFirstChild("Name") or Instance.new("RemoteEvent")   (+ X.Name = "Name")
        for var, name, cls in re.findall(r'local (\w+) = [\w.]+:FindFirstChild\("(\w+)"\) or Instance\.new\("(Remote\w+)"\)', s):
            add(name, cls, f, var)
    # aliases of another module's remote: local ChallengeMsg = StreetRace.ChallengeMsg
    for f, s in SERVER.items():
        for var, attr in re.findall(r'local (\w+) = \w+\.(\w+)[ \t]*$', s, re.M):
            for name, d in out.items():
                if any(v == attr and g.startswith('ServerStorage/') and g != f for g, v in d['vars']):
                    d['vars'].add((f, var))
    return out


def client_remotes():
    """name -> {'files': set, 'fire': set, 'listen': set, 'invoke': set}"""
    out = {}
    for f, s in CLIENT.items():
        names = {}
        for var, name in re.findall(r'local (\w+)\s*=\s*[^\n]*?' + CALL + r'[^\n]*$', s, re.M):
            names[var] = name
        uses = []
        for var, name in names.items():
            v = re.escape(var)
            u = set()
            if re.search(rf'\b{v}:FireServer\b', s):
                u.add('fire')
            if re.search(rf'\b{v}\.OnClientEvent\b', s) or re.search(rf'\b{v}\.OnClientInvoke\b', s):
                u.add('listen')
            if re.search(rf'\b{v}:InvokeServer\b', s):
                u.add('invoke')
            if u:
                uses.append((name, u))
        # helper wire(remotes, "Name", fn) -> OnClientEvent
        for name in re.findall(r'\bwire\(\s*remotes\s*,\s*"(\w+)"', s):
            uses.append((name, {'listen'}))
        # inline: remotes:WaitForChild("Name", t).OnClientEvent / :FireServer(
        kmap = {'OnClientEvent': 'listen', 'FireServer': 'fire', 'InvokeServer': 'invoke'}
        for name, kind in re.findall(CALL + r'[^)]*\)\s*(?:\)\s*)?[.:](OnClientEvent|FireServer|InvokeServer)', s):
            uses.append((name, {kmap[kind]}))
        for name, u in uses:
            d = out.setdefault(name, {'files': set(), 'fire': set(), 'listen': set(), 'invoke': set()})
            d['files'].add(f)
            for k in u:
                d[k].add(f)
    return out


def server_uses(name, srv):
    """'listen' if some server var of this remote has OnServerEvent/OnServerInvoke, 'fire' if FireClient/AllClients
    (directly or through a local fireClient(remote, ...) helper)."""
    u = set()
    for f, var in srv[name]['vars']:
        s = SERVER[f]
        v = re.escape(var)
        if re.search(rf'\b{v}\.OnServerEvent\b', s) or re.search(rf'\b{v}\.OnServerInvoke\b', s):
            u.add('listen')
        if re.search(rf'\b{v}:Fire(All)?Clients?\b', s) or re.search(rf'\bfireClient\(\s*{v}\b', s):
            u.add('fire')
    return u


class RemoteContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server_remotes()
        cls.cli = client_remotes()

    def test_scanner_found_the_known_remotes(self):
        """Guards the grep itself: these remotes are known from the docs (UI_CONTRACT, CIRCUIT_RACE_SYSTEM, ...)."""
        for name in ('NitroBonus', 'RequestSprint', 'SprintUpdate', 'RequestJob', 'CancelJob', 'JobUpdate',
                     'NearMiss', 'EventJoin', 'ChallengeRequest', 'ChallengeReply', 'ChallengeMsg',
                     'RoadFightRequest', 'GPSRequest', 'GPSUpdate', 'GarageRequest', 'CircuitRequest', 'CircuitMsg',
                     'PerfTelemetry'):
            self.assertIn(name, self.srv, f'server side of {name} not found')
            self.assertIn(name, self.cli, f'client side of {name} not found')

    def test_client_remotes_exist_on_server(self):
        missing = sorted(n for n in self.cli if n not in self.srv)
        self.assertEqual(missing, [], 'clients wait for remotes no server creates')

    def test_server_remotes_used_by_a_client(self):
        unused = sorted(n for n in self.srv if n not in self.cli)
        self.assertEqual(unused, [], 'server remotes no client uses')

    def test_one_class_per_remote(self):
        mixed = {n: sorted(d['class']) for n, d in self.srv.items() if len(d['class']) > 1}
        self.assertEqual(mixed, {})

    def test_directions_match(self):
        problems = []
        for name, c in self.cli.items():
            if name not in self.srv:
                continue
            cls = next(iter(self.srv[name]['class']))
            su = server_uses(name, self.srv)
            if c['fire'] and 'listen' not in su:
                problems.append(f'{name}: client FireServer ({sorted(c["fire"])}) but no server OnServerEvent')
            if c['invoke'] and (cls != 'RemoteFunction' or 'listen' not in su):
                problems.append(f'{name}: client InvokeServer but server has no RemoteFunction.OnServerInvoke')
            if c['listen'] and 'fire' not in su:
                problems.append(f'{name}: client OnClientEvent ({sorted(c["listen"])}) but no server FireClient')
            if (c['fire'] or c['listen']) and cls != 'RemoteEvent':
                problems.append(f'{name}: used as RemoteEvent by the client, created as {cls}')
        self.assertEqual(problems, [])

    def test_client_scripts_use_shared_remotes_folder(self):
        """Every server creates its remotes under ReplicatedStorage.PattayaRemotes (or ReplicatedStorage itself for
        PerfTelemetry); clients wait for that folder."""
        for f, s in SERVER.items():
            if re.search(r'Instance\.new\("Remote(Event|Function)"\)', s) and 'PerfTelemetry' not in f:
                self.assertIn('PattayaRemotes', s, f)


if __name__ == '__main__':
    unittest.main()
