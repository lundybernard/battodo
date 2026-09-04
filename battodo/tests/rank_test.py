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


def item(**fields: str) -> TaskNode:
    """An open top-level task carrying `fields`."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title='X',
        fields=fields,
    )


def one(name: str, value: str | None) -> TaskNode:
    """A task carrying only `name`, or none at all when value is None."""
    return item() if value is None else item(**{name: value})


class MultiplierTests(TestCase):
    """Unit tests for battodo.rank.multiplier."""

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
                t.assertAlmostEqual(multiplier(one('P', value)), expected)

    def test_order(t) -> None:
        legacy = [1, 8, 33, 47, 76, 83, 95, 98]
        folded = [multiplier(item(P=str(p))) for p in legacy]

        with t.subTest('no ordering the live files hold is lost'):
            t.assertEqual(folded, sorted(folded))

        with t.subTest('and no two legacy values fold on to one'):
            t.assertEqual(len(set(folded)), len(folded))


class AgeScoreTests(TestCase):
    """Unit tests for battodo.rank.age_score."""

    def test_age_score(t) -> None:
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
                t.assertAlmostEqual(
                    age_score(one('ADDED', value), TODAY), expected
                )


class DueScoreTests(TestCase):
    """Unit tests for battodo.rank.due_score."""

    def test_due_score(t) -> None:
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
                t.assertAlmostEqual(
                    due_score(one('DUE', value), TODAY), expected
                )


class RankTests(TestCase):
    """Unit tests for battodo.rank.rank."""

    def test_rank(t) -> None:
        with t.subTest('a fresh undated item ranks at its multiplier'):
            t.assertAlmostEqual(rank(item(P='3'), TODAY), 3.0)

        with t.subTest('waiting multiplies: the same task at three ages'):
            fresh = item(P='3', ADDED='2026-08-08')
            month = item(P='3', ADDED='2026-07-09')
            quarter = item(P='3', ADDED='2026-05-10')
            t.assertAlmostEqual(rank(fresh, TODAY), 3.0)
            t.assertAlmostEqual(rank(month, TODAY), 6.0)
            t.assertAlmostEqual(rank(quarter, TODAY), 9.0)

        with t.subTest('age and lateness compound'):
            task = item(P='2', ADDED='2026-07-09', DUE='2026-08-01')
            t.assertAlmostEqual(rank(task, TODAY), 8.0)

        with t.subTest('a parked item ranks zero whatever its dates'):
            task = item(P='0', ADDED='2020-01-01', DUE='2020-01-01')
            t.assertAlmostEqual(rank(task, TODAY), 0.0)

        with t.subTest('urgency is bounded, so the multiplier still rules'):
            worst = item(P='1', ADDED='2020-01-01', DUE='2020-01-01')
            t.assertAlmostEqual(rank(worst, TODAY), 6.0)
            t.assertLess(
                rank(worst, TODAY),
                rank(item(P='5', ADDED='2026-05-10'), TODAY),
            )
