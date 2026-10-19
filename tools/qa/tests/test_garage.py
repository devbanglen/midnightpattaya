"""Garage: ReplicatedStorage/CarSpecs.luau (cars, PI, classes, upgrades, prices) against docs/GARAGE_AND_CLASSES.md,
and the GarageRequest contract between PattayaGarageServer and PattayaGarageClient.
The numbers are parsed from the Luau source; the PI/upgrade maths is a line-by-line Python port whose formula lines
are asserted to still be in the source (so the port cannot silently drift)."""
import math
import os
import re
import unittest

import _qa

SPEC = _qa.src('ReplicatedStorage/CarSpecs.luau')
DOC = _qa.read(os.path.join(_qa.DOCS, 'GARAGE_AND_CLASSES.md'))
REQUIRED_STATS = ['maxSpeed', 'nitroSpeed', 'accel', 'nitroAccel', 'reverseSpeed', 'brake', 'coastDrag', 'turnRate',
                  'grip', 'driftGrip', 'driftTurnBoost', 'nitroMax', 'nitroDrain', 'nitroRegen', 'nitroDriftRegen']
# sane ranges (studs/s, studs/s^2, rad/s); the race servers call > 260 studs/s a teleport
RANGES = {'maxSpeed': (100, 220), 'nitroSpeed': (150, 245), 'accel': (30, 120), 'nitroAccel': (60, 180),
          'reverseSpeed': (20, 80), 'brake': (80, 200), 'coastDrag': (0.05, 1), 'turnRate': (1.5, 3.5),
          'grip': (5, 15), 'driftGrip': (0.8, 2.5), 'driftTurnBoost': (1.0, 2.0), 'nitroMax': (50, 200),
          'nitroDrain': (10, 50), 'nitroRegen': (1, 10), 'nitroDriftRegen': (5, 30)}


def nums(body):
    return {k: float(v) for k, v in re.findall(r'(\w+)\s*=\s*(-?[\d.]+)', body)}


def parse_specs():
    base = nums(re.search(r'CarSpecs\.BASE = \{(.*?)\n\}', SPEC, re.S).group(1))
    classes = [(n, int(m)) for n, m in re.findall(r'\{name = "([^"]+)", min = (\d+)', SPEC)]
    order = re.findall(r'"(\w+)"', re.search(r'CarSpecs\.ORDER = \{(.*?)\}', SPEC).group(1))
    cars = {}
    body = re.search(r'CarSpecs\.Cars = \{(.*?)\n\}', SPEC, re.S).group(1)
    for m in re.finditer(r'\n\t(\w+) = \{(.*?)\n\t\},', body, re.S):
        blk = m.group(2)
        price, level = re.search(r'price = (\d+), level = (\d+)', blk).groups()
        stats = nums(re.search(r'stats = \{(.*?)\}', blk, re.S).group(1))
        name = re.search(r'name = "([^"]+)"', blk).group(1)
        cars[m.group(1)] = dict(price=int(price), level=int(level), stats=stats, name=name)
    weights = nums(re.search(r'PI_WEIGHTS = \{(.*?)\}', SPEC).group(1))
    fee = [float(x) for x in re.search(r'UPGRADE_FEE = \{(.*?)\}', SPEC).group(1).split(',')]
    upg = [(k, float(c), w) for k, c, w in re.findall(r's\.(\w+) \*= 1 \+ ([\d.]+) \* (engine|grip)', SPEC)]
    nitro_limit = int(re.search(r'NITRO_LIMIT = (\d+)', SPEC).group(1))
    max_tier = int(re.search(r'MAX_TIER = (\d+)', SPEC).group(1))
    return dict(base=base, classes=classes, order=order, cars=cars, weights=weights, fee=fee, upg=upg,
                nitro_limit=nitro_limit, max_tier=max_tier)


S = parse_specs()

# the Ratings() lines this port mirrors (asserted present in the source)
RATING_LINES = [
    'speed = range(120, 200, s.maxSpeed)',
    'accel = range(40, 100, s.accel)',
    'brake = range(90, 190, s.brake)',
    'grip = (range(6, 14, s.grip) + range(1.8, 3.0, s.turnRate)) / 2',
    'drift = (range(1.1, 1.8, s.driftTurnBoost) + range(8, 26, s.nitroDriftRegen)) / 2',
    'nitro = (range(160, 250, s.nitroSpeed) + range(2.5, 6, s.nitroMax / s.nitroDrain)) / 2',
    'math.clamp(math.floor(100 + 900 * sum + 0.5), 100, 999)',
    'math.floor(basis * (UPGRADE_FEE[tier] or 1) / 100 + 0.5) * 100',
    'local basis = math.max(car and car.price or 0, 8000)',
]


def rng(lo, hi, v):
    return min(1.0, max(0.0, (v - lo) / (hi - lo)))


def stats(cid, e=0, g=0):
    s = dict(S['base'])
    s.update(S['cars'][cid]['stats'])
    for k, c, w in S['upg']:
        s[k] *= 1 + c * (e if w == 'engine' else g)
    s['nitroSpeed'] = min(s['nitroSpeed'], S['nitro_limit'])
    return s


def pi(s):
    r = dict(speed=rng(120, 200, s['maxSpeed']), accel=rng(40, 100, s['accel']), brake=rng(90, 190, s['brake']),
             grip=(rng(6, 14, s['grip']) + rng(1.8, 3.0, s['turnRate'])) / 2,
             drift=(rng(1.1, 1.8, s['driftTurnBoost']) + rng(8, 26, s['nitroDriftRegen'])) / 2,
             nitro=(rng(160, 250, s['nitroSpeed']) + rng(2.5, 6, s['nitroMax'] / s['nitroDrain'])) / 2)
    total = sum(w * r[k] for k, w in S['weights'].items())
    return max(100, min(999, math.floor(100 + 900 * total + 0.5)))


def class_of(p):
    name = S['classes'][0][0]
    for n, m in S['classes']:
        if p >= m:
            name = n
    return name


def upgrade_price(cid, tier):
    basis = max(S['cars'][cid]['price'], 8000)
    return math.floor(basis * S['fee'][tier - 1] / 100 + 0.5) * 100


def best_upgrades(cid):
    """'bought engine then grip, alternating' while the class rule allows (CarSpecs.CanUpgrade)."""
    stock = class_of(pi(stats(cid)))
    e = g = 0
    turn = 'engine'
    while True:
        moved = False
        for kind in ([turn, 'grip' if turn == 'engine' else 'engine']):
            ne, ng = (e + 1, g) if kind == 'engine' else (e, g + 1)
            if max(ne, ng) <= S['max_tier'] and class_of(pi(stats(cid, ne, ng))) == stock:
                e, g, moved = ne, ng, True
                turn = 'grip' if kind == 'engine' else 'engine'
                break
        if not moved:
            return e, g, pi(stats(cid, e, g))


def doc_car_rows():
    rows = {}
    for line in DOC.splitlines():
        m = re.match(r'\| (\w+) \(([^)]*)\) \|(.*)\|\s*$', line)
        if m and m.group(1) in S['cars']:
            cells = [c.strip() for c in m.group(3).split('|')]
            rows[m.group(1)] = cells
    return rows


class CarSpecsData(unittest.TestCase):
    def test_port_matches_source_formulas(self):
        for line in RATING_LINES:
            self.assertIn(line, SPEC, 'CarSpecs formula changed: update the Python port in test_garage.py')
        self.assertEqual(len(S['upg']), 7, 'applyUpgrades lines')

    def test_every_car_complete_and_in_range(self):
        self.assertEqual(sorted(S['order']), sorted(S['cars']), 'ORDER lists exactly the cars')
        self.assertIn(re.search(r'STARTER = "(\w+)"', SPEC).group(1), S['cars'])
        self.assertEqual(sorted(S['base']), sorted(REQUIRED_STATS))
        for cid in S['cars']:
            s = stats(cid)
            for k in REQUIRED_STATS:
                lo, hi = RANGES[k]
                self.assertTrue(lo <= s[k] <= hi, f'{cid}.{k} = {s[k]} outside {lo}..{hi}')
            self.assertGreater(s['nitroSpeed'], s['maxSpeed'], cid)
            unknown = set(S['cars'][cid]['stats']) - set(REQUIRED_STATS)
            self.assertEqual(unknown, set(), f'{cid} overrides unknown keys')

    def test_upgraded_cars_stay_under_limits(self):
        for cid in S['cars']:
            for e in range(S['max_tier'] + 1):
                for g in range(S['max_tier'] + 1):
                    s = stats(cid, e, g)
                    self.assertLessEqual(s['nitroSpeed'], S['nitro_limit'])
                    self.assertLess(s['maxSpeed'], 260 - 15, f'{cid} E{e}G{g} top speed {s["maxSpeed"]:.0f}')

    def test_shop_order_prices_and_levels_non_decreasing(self):
        prices = [S['cars'][c]['price'] for c in S['order']]
        levels = [S['cars'][c]['level'] for c in S['order']]
        self.assertEqual(prices, sorted(prices))
        self.assertEqual(levels, sorted(levels))
        self.assertEqual(S['cars'][S['order'][0]]['price'], 0, 'starter is free')

    def test_classes_bands(self):
        mins = [m for _, m in S['classes']]
        self.assertEqual(mins, sorted(mins))
        self.assertEqual([n for n, _ in S['classes']], ['Street', 'Sport', 'Super', 'Hyper', 'Track Spec'])

    def test_doc_table_matches_specs(self):
        rows = doc_car_rows()
        self.assertEqual(sorted(rows), sorted(S['cars']), 'docs car table lists every car')
        cols = ['maxSpeed', 'nitroSpeed', 'accel', 'nitroAccel', 'brake', 'grip', 'turnRate', 'driftGrip',
                'driftTurnBoost', 'nitroMax', 'nitroDrain', 'nitroDriftRegen']
        for cid, cells in rows.items():
            s = stats(cid)
            for k, cell in zip(cols, cells):
                self.assertAlmostEqual(float(cell), s[k], places=2, msg=f'{cid}.{k}: doc {cell} vs code {s[k]}')
            p = pi(s)
            self.assertEqual(int(cells[12]), p, f'{cid}: doc PI {cells[12]} vs computed {p}')
            self.assertEqual(cells[13], class_of(p), f'{cid}: doc class')
            price = 0 if cells[14] == 'free' else int(cells[14].replace(',', ''))
            self.assertEqual(price, S['cars'][cid]['price'], f'{cid}: doc price')
            self.assertEqual(int(cells[15]), S['cars'][cid]['level'], f'{cid}: doc level')

    def test_doc_class_band_table(self):
        for name, lo in S['classes']:
            self.assertRegex(DOC, rf'\| {re.escape(name)} \| {lo}[–-]\d+ \|', f'doc band row for {name}')

    def test_doc_upgrade_table(self):
        for cid in S['cars']:
            m = re.search(rf'^\| {cid} \| E(\d) G(\d) \| (\d+) \|', DOC, re.M)
            self.assertIsNotNone(m, f'no upgrade row for {cid}')
            e, g, p = best_upgrades(cid)
            self.assertEqual((int(m.group(1)), int(m.group(2)), int(m.group(3))), (e, g, p), cid)

    def test_doc_upgrade_price_examples(self):
        self.assertEqual([upgrade_price('hatch', t) for t in (1, 2, 3)], [1000, 2000, 3600])
        self.assertEqual([upgrade_price('supercar', t) for t in (1, 2, 3)], [6600, 13800, 24800])

    def test_levels_reachable(self):
        """Car level gates against PattayaProgress.expToNext: EXP to reach the top car's level stays reasonable."""
        prog = _qa.src('ServerStorage/PattayaProgress.luau')
        a, b = map(int, re.search(r'return (\d+) \+ \(level - 1\) \* (\d+)', prog).groups())
        top = max(c['level'] for c in S['cars'].values())
        need = sum(a + (lv - 1) * b for lv in range(1, top))
        self.assertLess(need, 10000, f'{need} EXP to reach level {top}')


class GarageContract(unittest.TestCase):
    def test_garage_actions_match(self):
        server = _qa.src('ServerScriptService/PattayaGarageServer.server.luau')
        client = _qa.src('StarterPlayer/StarterPlayerScripts/PattayaGarageClient.client.luau')
        self.assertIn('Instance.new("RemoteFunction")', server)
        self.assertIn('GarageRequest.OnServerInvoke', server)
        self.assertIn('GarageRequest:InvokeServer', client)
        handled = set(re.findall(r'action == "(\w+)"', server))
        sent = set(re.findall(r'request\("(\w+)"', client))
        self.assertTrue(sent, 'no request("...") calls found in the client')
        self.assertEqual(sent - handled, set(), 'client sends actions the server does not handle')
        kinds = set(re.findall(r'request\("upgrade", \w+, "(\w+)"\)', client))
        upgrade_kinds = set(re.findall(r'"(\w+)"', re.search(r'UPGRADE_KINDS = \{(.*?)\}', SPEC).group(1)))
        self.assertEqual(kinds, upgrade_kinds)


if __name__ == '__main__':
    unittest.main()
