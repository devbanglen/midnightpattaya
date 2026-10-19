"""Rewards and progress: the money / EXP formulas of every activity (read from the Luau source and evaluated over
realistic inputs), PattayaProgress levels and titles, and the job / event / Road Fight tables."""
import math
import re
import unittest

import _qa

GARAGE = _qa.src('ReplicatedStorage/CarSpecs.luau')
PRICES = [int(p) for p in re.findall(r'price = (\d+), level', GARAGE)]
TOP_PRICE = max(PRICES)
CHEAPEST_PAID = min(p for p in PRICES if p > 0)


def _if_to_py(e):
    """Luau `(if A then B else C)` -> Python `((B) if (A) else (C))`, nested parentheses allowed."""
    while True:
        i = e.find('(if ')
        if i < 0:
            return e
        depth, j = 0, i
        while True:
            if e[j] == '(':
                depth += 1
            elif e[j] == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        inner = e[i + 4:j]
        # split at the top-level ' then ' / ' else '
        parts, cur, d, k = [], '', 0, 0
        while k < len(inner):
            ch = inner[k]
            d += ch == '('
            d -= ch == ')'
            for kw in (' then ', ' else '):
                if d == 0 and inner.startswith(kw, k) and len(parts) < 2:
                    parts.append(cur)
                    cur = ''
                    k += len(kw)
                    break
            else:
                cur += ch
                k += 1
        parts.append(cur)
        a, b, c = (_if_to_py(x) for x in parts)
        e = e[:i] + f'(({b}) if ({a}) else ({c}))' + e[j + 1:]


def formula(rel, var):
    """The right-hand side of `local <var> = ...` in a Luau file, as a Python expression."""
    s = _qa.src(rel)
    m = re.search(rf'local {var} = (.+)$', s, re.M)
    assert m, f'{rel}: no "local {var} =" line'
    e = _if_to_py(m.group(1).strip())
    return e.replace('math.floor', 'floor').replace('math.max', 'max').replace('math.min', 'min')


def ev(expr, **env):
    env.update(floor=math.floor, max=max, min=min)
    return eval(expr, {'__builtins__': {}}, env)  # source is the repo's own Luau, not external input


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class RewardFormulas(unittest.TestCase):
    def check_band(self, name, money, exp, minutes):
        """No documented economy budget exists; QA rule: never negative, always some EXP, and one run never pays
        more than 10% of the most expensive car. `minutes` is kept for the rate printed in docs/AUTOMATED_QA.md."""
        self.assertGreaterEqual(money, 0, name)
        self.assertGreater(exp, 0, name)
        self.assertLessEqual(money, 0.1 * TOP_PRICE, f'{name}: {money} per run is >10% of the top car')

    def test_central_loop(self):
        f = 'ServerScriptService/PattayaRaceServer.server.luau'
        money_e, exp_e, avg_e = formula(f, 'money'), formula(f, 'exp'), formula(f, 'avg')
        race = _qa.load_json(_qa.need_build('central_pattaya', 'layout.json'))['race']
        L, laps = race['length_studs'], race['laps']
        prev = None
        for t in (L * laps / 240, L * laps / 160, L * laps / 100, 600):
            for record in (False, True):
                avg = ev(avg_e, LENGTH=L, LAPS=laps, t=t)
                money = ev(money_e, LENGTH=L, LAPS=laps, t=t, avg=avg, record=record)
                exp = ev(exp_e, LENGTH=L, LAPS=laps)
                self.check_band(f'loop t={t:.0f} record={record}', money, exp, t / 60)
            if prev is not None:
                self.assertLessEqual(money, prev, 'a slower run must not pay more')
            prev = money
        # the starter can buy the cheapest paid car within ~20 average runs
        avg = ev(avg_e, LENGTH=L, LAPS=laps, t=L * laps / 130)
        per_run = ev(money_e, LENGTH=L, LAPS=laps, t=L * laps / 130, avg=avg, record=False)
        self.assertLessEqual(CHEAPEST_PAID / per_run, 20, f'{per_run} per loop vs {CHEAPEST_PAID}')

    def test_street_sprint(self):
        f = 'ServerScriptService/PattayaSprintServer.server.luau'
        s = _qa.src(f)
        lo, hi = map(int, re.search(r'MIN_LEN, MAX_LEN = (\d+), (\d+)', s).groups())
        tl = int(re.search(r'TIME_LIMIT = (\d+)', s).group(1))
        for length in (lo, hi):
            for t in (length / 240, length / 120, tl):
                st = Obj(length=length)
                avg = length / t
                money = ev(formula(f, 'money'), st=st, avg=avg)
                exp = ev(formula(f, 'exp'), st=st)
                self.check_band(f'sprint {length}/{t:.0f}s', money, exp, t / 60)

    def test_street_challenge(self):
        f = 'ServerStorage/PattayaStreetRace.luau'
        for length in (1500, 2600, 4500):
            for n in (2, 4, 7):
                for winner in (True, False):
                    race = Obj(length=length)
                    money = ev(formula(f, 'money'), race=race, winner=winner, n=n)
                    exp = ev(formula(f, 'exp'), race=race, winner=winner)
                    self.check_band(f'challenge {length} n={n} win={winner}', money, exp, length / 150 / 60)

    def test_night_run_event(self):
        f = 'ServerScriptService/PattayaEventsServer.server.luau'
        src = _qa.src(f)
        podium = [int(x) for x in re.search(r'podium = \{([\d, ]+)\}', src).group(1).split(',')]
        self.assertEqual(podium, sorted(podium, reverse=True), 'podium pays 1st most')
        lo, hi = map(int, re.search(r'nightRun = \{minLen = (\d+), maxLen = (\d+)', src).groups())
        C = Obj(podium={i + 1: v for i, v in enumerate(podium)})

        class P(dict):
            def __getitem__(self, k):
                return dict.get(self, k)

        C.podium = P(C.podium)
        expr_m = formula(f, 'money')
        for length in (lo, hi):
            for n, nh in ((2, 1), (8, 4), (16, 16)):
                last = None
                for place in range(1, n + 1):
                    money = ev(expr_m, race=Obj(length=length), n=n, nh=nh, place=place, C=C)
                    exp = ev(formula(f, 'exp'), race=Obj(length=length), n=n, place=place)
                    self.check_band(f'night run {length} {place}/{n}', money, exp, length / 140 / 60)
                    if last is not None:
                        self.assertLessEqual(money, last, 'a lower place must not pay more')
                    last = money

    def test_jobs_table(self):
        src = _qa.src('ServerScriptService/PattayaJobsServer.server.luau')
        body = re.search(r'local KINDS = \{(.*?)\n\}', src, re.S).group(1)
        kinds = dict(re.findall(r'\n\t(\w+) = \{(.*?)\},?(?=\n\t\w+ = \{|\s*$)', body + '\n', re.S))
        self.assertEqual(sorted(kinds), ['delivery', 'taxi'])
        for name, blk in kinds.items():
            vals = {}
            for k, v in re.findall(r'(\w+) = ([\d.]+(?: / [\d.]+)?)', blk):
                vals[k] = eval(v, {'__builtins__': {}})
            for k in ('base', 'perStud', 'expPerStud', 'slack', 'speed', 'bumpCut', 'tipPerSec'):
                self.assertGreater(vals.get(k, 0), 0, f'{name}.{k}')
            self.assertLess(vals['bumpCut'], 0.5, name)
            for length in (800, 3000):
                fare = math.floor(vals['base'] + length * vals['perStud'])
                exp = math.floor(length * vals['expPerStud'])
                self.check_band(f'{name} {length}', fare, exp, length / vals['speed'] / 60)
        self.assertIn('local fare = math.floor(k.base + length * k.perStud)', src)
        self.assertIn('math.min(st.bumps * k.bumpCut, 0.6)', src, 'bump cut must be capped')

    def test_road_fight_table(self):
        src = _qa.src('ServerScriptService/PattayaChallengeServer.server.luau')
        money = [int(x) for x in re.search(r'FIRST_MONEY = \{([\d, ]+)\}', src).group(1).split(',')]
        exp = [int(x) for x in re.search(r'FIRST_EXP = \{([\d, ]+)\}', src).group(1).split(',')]
        self.assertEqual(len(money), len(exp))
        self.assertEqual(money, sorted(money), 'later bosses pay more')
        self.assertEqual(exp, sorted(exp))
        self.assertTrue(all(m <= 0.1 * TOP_PRICE for m in money))

    def test_survival_table(self):
        src = _qa.src('ServerScriptService/PattayaEventsServer.server.luau')
        m = re.search(r'roundMoney = (\d+), roundExp = (\d+), winMoney = (\d+), winExp = (\d+)', src)
        rm, rx, wm, wx = map(int, m.groups())
        rounds = int(re.search(r'survival = \{rounds = (\d+)', src).group(1))
        self.assertTrue(rm > 0 and rx > 0 and wm > rm * rounds and wx > rx * rounds)
        self.assertLessEqual(wm + rounds * rm, 0.1 * TOP_PRICE)


class ProgressModule(unittest.TestCase):
    def test_exp_curve(self):
        prog = _qa.src('ServerStorage/PattayaProgress.luau')
        a, b = map(int, re.search(r'return (\d+) \+ \(level - 1\) \* (\d+)', prog).groups())
        self.assertGreater(a, 0)
        self.assertGreaterEqual(b, 0)
        # Award() loops `while EXP >= expToNext(level)`: it must terminate for any award
        self.assertIn('while ls.EXP.Value >= expToNext(ls.Level.Value) do', prog)

    def test_granted_titles_are_ranked(self):
        prog = _qa.src('ServerStorage/PattayaProgress.luau')
        ranked = set(re.findall(r'\["([^"]+)"\] = \d', re.search(r'TITLE_RANK = \{(.*?)\}', prog).group(1)))
        granted = set()
        for rel in ('ServerScriptService/PattayaChallengeServer.server.luau',
                    'ServerScriptService/PattayaEventsServer.server.luau'):
            s = _qa.src(rel)
            granted |= set(re.findall(r'GrantTitle\(\w+, "([^"]+)"\)', s))
            granted |= set(re.findall(r'title = "([^"]+)"\}', s))
        self.assertTrue(granted, 'no granted titles found')
        self.assertEqual(granted - ranked, set(), 'titles granted but missing from Progress.TITLE_RANK')

    def test_every_award_reason_is_a_string(self):
        """Progress.Award(plr, money, exp, reason): 4 arguments at every call site."""
        bad = []
        for f in _qa.luau_files():
            s = _qa.strip_comments(_qa.read(f))
            for m in re.finditer(r'Progress\.Award\(', s):
                depth, i = 1, m.end()
                args, cur = [], ''
                while depth and i < len(s):
                    ch = s[i]
                    if ch in '([{':
                        depth += 1
                    elif ch in ')]}':
                        depth -= 1
                    if depth == 1 and ch == ',':
                        args.append(cur)
                        cur = ''
                    elif depth:
                        cur += ch
                    i += 1
                args.append(cur)
                if len(args) != 4:
                    bad.append(f'{f}: {s[m.start():i][:80]}')
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
