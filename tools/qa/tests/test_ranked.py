"""Ranked circuit racing: runs the repo's own Luau checks with the luau CLI (same as tools/offline/run_ranked.sh):
ServerStorage/RankedRatingTest.luau on the real RankedRating module, and the mocked RaceSessionService.Ranked /
LeaderboardService ranked-board harnesses in tools/offline. docs/RANKED_SYSTEM.md has the worked examples."""
import os
import re
import unittest

import _qa

OFF = os.path.join(_qa.ROOT, 'tools', 'offline')


def ss(name):
    return _qa.src(os.path.join('ServerStorage', name + '.luau'))


class Ranked(unittest.TestCase):
    def test_rating_unit_test(self):
        code, out = _qa.run_luau('local s, ok = require("./RankedRatingTest")(require("./RankedRating"))\n'
                                 'print(s)\nprint("ALLPASSED", ok)\n',
                                 {'RankedRating.luau': ss('RankedRating'), 'RankedRatingTest.luau': ss('RankedRatingTest')})
        self.assertEqual(code, 0, out[-1500:])
        self.assertIn('ALLPASSED\ttrue', out, out[-1500:])
        m = re.search(r'(\d+)/(\d+) checks passed', out)
        self.assertTrue(m and m.group(1) == m.group(2) and int(m.group(2)) >= 10, out[-500:])

    def _harness(self, head, module, tail):
        main = _qa.read(os.path.join(OFF, head)) + ss(module) + '\n' + _qa.read(os.path.join(OFF, tail))
        code, out = _qa.run_luau(main, {'RankedRating.luau': ss('RankedRating')})
        self.assertEqual(code, 0, out[-1500:])
        self.assertRegex(out, r'\n0 failures', out[-1500:])
        self.assertNotIn('FAIL', out.replace('0 failures', ''), out[-1500:])
        self.assertGreaterEqual(out.count('PASS'), 5)

    def test_session_ranked_mocked(self):
        self._harness('ranked_session_head.luau', 'RaceSessionService', 'ranked_session_tail.luau')

    def test_leaderboard_ranked_mocked(self):
        self._harness('ranked_board_head.luau', 'LeaderboardService', 'ranked_board_tail.luau')

    def test_ranked_wired_in_session(self):
        """RaceSessionService requires RankedRating and the Studio runner can run the unit test."""
        self.assertIn('RankedRating', ss('RaceSessionService'))
        runner = os.path.join(_qa.SRC, 'ServerStorage', 'PattayaQARunner.luau')
        self.assertTrue(os.path.exists(runner))
        self.assertIn('RankedRatingTest', _qa.read(runner))


if __name__ == '__main__':
    unittest.main()
