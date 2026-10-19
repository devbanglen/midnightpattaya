"""Runs every offline QA test in tools/qa/tests (standard library unittest, no pytest needed).

    .venv\\Scripts\\python tools\\qa\\tests\\run_all.py [-v] [-k substring]

The same files also run under pytest (`python -m pytest tools/qa/tests -q`) when pytest is installed: they are plain
unittest.TestCase classes, and known problems are @unittest.expectedFailure (pytest reports them as xfail).
Exit code 1 when a test fails or errors (expected failures do not fail the run; an expected failure that starts
passing is reported as an "unexpected success" and does fail it, so the marker gets removed).
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class Result(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.rows = []
        self._t0 = 0.0

    def startTest(self, test):
        self._t0 = time.time()
        super().startTest(test)

    def _row(self, test, status, note=''):
        self.rows.append((status, test.id().split('.', 1)[-1], round(time.time() - self._t0, 2), note))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._row(test, 'PASS')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._row(test, 'FAIL', str(err[1]).splitlines()[0][:160] if str(err[1]) else '')

    def addError(self, test, err):
        super().addError(test, err)
        self._row(test, 'ERROR', f'{err[0].__name__}: {err[1]}'.splitlines()[0][:160])

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._row(test, 'SKIP', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._row(test, 'XFAIL', str(err[1]).splitlines()[0][:160] if str(err[1]) else '')

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._row(test, 'XPASS', 'known problem no longer reproduces: remove @expectedFailure')


def main():
    args = sys.argv[1:]
    verbose = '-v' in args
    pattern = None
    if '-k' in args:
        pattern = args[args.index('-k') + 1]
    suite = unittest.defaultTestLoader.discover(HERE, pattern='test_*.py', top_level_dir=HERE)
    if pattern:
        def flat(s):
            for t in s:
                if isinstance(t, unittest.TestSuite):
                    yield from flat(t)
                else:
                    yield t
        suite = unittest.TestSuite([t for t in flat(suite) if pattern in t.id()])
    stream = sys.stdout if verbose else open(os.devnull, 'w')
    runner = unittest.TextTestRunner(stream=stream, resultclass=Result, verbosity=2 if verbose else 0)
    t0 = time.time()
    res = runner.run(suite)
    counts = {}
    for status, name, secs, note in res.rows:
        counts[status] = counts.get(status, 0) + 1
        print(f'{status:5} {name}  ({secs}s){"  - " + note if note else ""}')
    print('\n' + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())) + f'  in {time.time() - t0:.1f}s')
    if res.failures or res.errors:
        print('\nDETAILS:')
        for test, tb in res.failures + res.errors:
            print('=' * 70 + f'\n{test.id()}\n{tb}')
    ok = not (res.failures or res.errors or res.unexpectedSuccesses)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
