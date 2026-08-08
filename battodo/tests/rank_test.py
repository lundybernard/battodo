from datetime import date
from unittest import TestCase

from ..parser import Task, parse
from ..rank import (
    age_score,
    due_score,
    multiplier,
    rank,
)

TODAY = date(2026, 8, 8)


def item(line: str) -> Task:
    """The one top-level task in a minimal open section."""
    return parse(f'## Open\n\n{line}\n').tasks[0]


class MultiplierTests(TestCase):
    def test_multiplier(t) -> None:
        cases = {
            # New 0-5 scale, taken as written.
            '- [ ] X': 1.0,
            '- [ ] X [P:0]': 0.0,
            '- [ ] X [P:3]': 3.0,
            '- [ ] X [P:5]': 5.0,
            # Legacy bump-inflated values, folded on to the scale.
            '- [ ] X [P:6]': 1.24,
            '- [ ] X [P:33]': 2.32,
            '- [ ] X [P:98]': 4.92,
            '- [ ] X [P:125]': 5.0,
            # Hand-edited files: a value that is not a number at all.
            '- [ ] X [P:N]': 1.0,
            '- [ ] X [P:]': 1.0,
        }
        for line, expected in cases.items():
            with t.subTest(line):
                t.assertAlmostEqual(multiplier(item(line)), expected)

    def test_multiplier_is_order_preserving(t) -> None:
        """No ordering present in the live files may be lost."""
        legacy = [1, 8, 33, 47, 76, 83, 95, 98]
        folded = [multiplier(item(f'- [ ] X [P:{p}]')) for p in legacy]
        t.assertEqual(folded, sorted(folded))
        t.assertEqual(len(set(folded)), len(folded))


class AgeScoreTests(TestCase):
    def test_age_score(t) -> None:
        cases = {
            # No ADDED: the whole legacy corpus, and every hand-added item.
            '- [ ] X': 0.0,
            '- [ ] X [ADDED:2026-08-08]': 0.0,
            '- [ ] X [ADDED:2026-07-24]': 0.5,
            '- [ ] X [ADDED:2026-07-09]': 1.0,
            # Capped at two months of waiting.
            '- [ ] X [ADDED:2026-06-09]': 2.0,
            '- [ ] X [ADDED:2020-01-01]': 2.0,
            # Placeholders and clock skew never produce a negative score.
            '- [ ] X [ADDED:YYYY-MM-DD]': 0.0,
            '- [ ] X [ADDED:2026-09-01]': 0.0,
        }
        for line, expected in cases.items():
            with t.subTest(line):
                t.assertAlmostEqual(age_score(item(line), TODAY), expected)


class DueScoreTests(TestCase):
    def test_due_score(t) -> None:
        cases = {
            '- [ ] X': 0.0,
            # Beyond the fortnight horizon: no contribution yet.
            '- [ ] X [DUE:2026-09-01]': 0.0,
            '- [ ] X [DUE:2026-08-22]': 0.0,
            # Ramping up over the fortnight before it comes due.
            '- [ ] X [DUE:2026-08-15]': 0.5,
            '- [ ] X [DUE:2026-08-08]': 1.0,
            # Late: another multiplier's worth per week, capped.
            '- [ ] X [DUE:2026-08-01]': 2.0,
            '- [ ] X [DUE:2026-07-25]': 3.0,
            '- [ ] X [DUE:2026-01-01]': 3.0,
            '- [ ] X [DUE:YYYY-MM-DD]': 0.0,
        }
        for line, expected in cases.items():
            with t.subTest(line):
                t.assertAlmostEqual(due_score(item(line), TODAY), expected)


class RankTests(TestCase):
    def test_rank(t) -> None:
        with t.subTest('a fresh undated item ranks at its multiplier'):
            t.assertAlmostEqual(rank(item('- [ ] X [P:3]'), TODAY), 3.0)

        with t.subTest('waiting multiplies: the same task at three ages'):
            fresh = '- [ ] X [P:3] [ADDED:2026-08-08]'
            month = '- [ ] X [P:3] [ADDED:2026-07-09]'
            quarter = '- [ ] X [P:3] [ADDED:2026-05-10]'
            t.assertAlmostEqual(rank(item(fresh), TODAY), 3.0)
            t.assertAlmostEqual(rank(item(month), TODAY), 6.0)
            t.assertAlmostEqual(rank(item(quarter), TODAY), 9.0)

        with t.subTest('age and lateness compound'):
            line = '- [ ] X [P:2] [ADDED:2026-07-09] [DUE:2026-08-01]'
            t.assertAlmostEqual(rank(item(line), TODAY), 8.0)

        with t.subTest('a parked item ranks zero whatever its dates'):
            line = '- [ ] X [P:0] [ADDED:2020-01-01] [DUE:2020-01-01]'
            t.assertAlmostEqual(rank(item(line), TODAY), 0.0)

        with t.subTest('urgency is bounded, so the multiplier still rules'):
            worst = '- [ ] X [P:1] [ADDED:2020-01-01] [DUE:2020-01-01]'
            t.assertAlmostEqual(rank(item(worst), TODAY), 6.0)
            t.assertLess(
                rank(item(worst), TODAY),
                rank(item('- [ ] X [P:5] [ADDED:2026-05-10]'), TODAY),
            )
