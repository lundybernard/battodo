from datetime import date
from unittest import TestCase

from ..rank import (
    TaskNode,
    age_score,
    due_score,
    multiplier,
    rank,
)

TODAY = date(2026, 8, 8)


def ranked_task() -> TaskNode:
    """One open top-level task, its fields set per test."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title='A ranked task',
        fields={},
    )


class MultiplierTests(TestCase):
    """Unit tests for battodo.rank.multiplier."""

    def setUp(t) -> None:
        t.tk = ranked_task()

    def test_scale(t) -> None:
        cases = {
            # New 0-5 scale, taken as written.
            None: 1.0,
            '0': 0.0,
            '3': 3.0,
            '5': 5.0,
            # Legacy bump-inflated values, folded on to the scale.
            '6': 1.24,
            '33': 2.32,
            '98': 4.92,
            '125': 5.0,
            # Hand-edited files: a value that is not a number at all.
            'N': 1.0,
            '': 1.0,
        }

        for value, expected in cases.items():
            with t.subTest(f'P:{value}'):
                t.tk.fields = {} if value is None else {'P': value}
                ret = multiplier(t.tk)
                t.assertAlmostEqual(ret, expected)

    def test_order(t) -> None:
        folded = []
        for priority in (1, 8, 33, 47, 76, 83, 95, 98):
            t.tk.fields = {'P': str(priority)}
            folded.append(multiplier(t.tk))

        with t.subTest('no ordering the live files hold is lost'):
            t.assertEqual(folded, sorted(folded))

        with t.subTest('and no two legacy values fold on to one'):
            t.assertEqual(len(set(folded)), len(folded))


class AgeScoreTests(TestCase):
    """Unit tests for battodo.rank.age_score."""

    def setUp(t) -> None:
        t.tk = ranked_task()

    def test_scale(t) -> None:
        cases = {
            # No ADDED: the whole legacy corpus, and every hand-added item.
            None: 0.0,
            '2026-08-08': 0.0,
            # A single day already counts: waiting starts accruing at
            # once, rather than after some grace period.
            '2026-08-07': 1 / 30,
            '2026-07-24': 0.5,
            '2026-07-09': 1.0,
            # Capped at two months of waiting.
            '2026-06-09': 2.0,
            '2020-01-01': 2.0,
            # Placeholders and clock skew never produce a negative score.
            'YYYY-MM-DD': 0.0,
            '2026-09-01': 0.0,
        }

        for value, expected in cases.items():
            with t.subTest(f'ADDED:{value}'):
                t.tk.fields = {} if value is None else {'ADDED': value}
                ret = age_score(t.tk, TODAY)
                t.assertAlmostEqual(ret, expected)


class DueScoreTests(TestCase):
    """Unit tests for battodo.rank.due_score."""

    def setUp(t) -> None:
        t.tk = ranked_task()

    def test_scale(t) -> None:
        cases = {
            None: 0.0,
            # Beyond the fortnight horizon: no contribution yet.
            '2026-09-01': 0.0,
            '2026-08-22': 0.0,
            # Ramping up over the fortnight before it comes due.
            '2026-08-15': 0.5,
            '2026-08-08': 1.0,
            # Late: another multiplier's worth per week, capped.
            '2026-08-01': 2.0,
            '2026-07-25': 3.0,
            '2026-01-01': 3.0,
            'YYYY-MM-DD': 0.0,
        }

        for value, expected in cases.items():
            with t.subTest(f'DUE:{value}'):
                t.tk.fields = {} if value is None else {'DUE': value}
                ret = due_score(t.tk, TODAY)
                t.assertAlmostEqual(ret, expected)


class RankTests(TestCase):
    """Unit tests for battodo.rank.rank."""

    def setUp(t) -> None:
        t.tk = ranked_task()

    def test_multiplier(t) -> None:
        # A fresh undated item ranks at its multiplier.
        t.tk.fields = {'P': '3'}
        ret = rank(t.tk, TODAY)
        t.assertAlmostEqual(ret, 3.0)

    def test_age(t) -> None:
        ages = {'2026-08-08': 3.0, '2026-07-09': 6.0, '2026-05-10': 9.0}

        for added, expected in ages.items():
            with t.subTest(f'ADDED:{added}'):
                t.tk.fields = {'P': '3', 'ADDED': added}
                ret = rank(t.tk, TODAY)
                t.assertAlmostEqual(ret, expected)

    def test_compound(t) -> None:
        # Age and lateness compound.
        t.tk.fields = {'P': '2', 'ADDED': '2026-07-09', 'DUE': '2026-08-01'}
        ret = rank(t.tk, TODAY)
        t.assertAlmostEqual(ret, 8.0)

    def test_parked(t) -> None:
        t.tk.fields = {'P': '0', 'ADDED': '2020-01-01', 'DUE': '2020-01-01'}
        ret = rank(t.tk, TODAY)
        t.assertAlmostEqual(ret, 0.0)

    def test_bounded(t) -> None:
        t.tk.fields = {'P': '1', 'ADDED': '2020-01-01', 'DUE': '2020-01-01'}
        worst = rank(t.tk, TODAY)

        with t.subTest('urgency alone cannot reach past its cap'):
            t.assertAlmostEqual(worst, 6.0)

        with t.subTest('so the multiplier still rules'):
            t.tk.fields = {'P': '5', 'ADDED': '2026-05-10'}
            ret = rank(t.tk, TODAY)
            t.assertLess(worst, ret)
