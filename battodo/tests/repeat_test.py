from datetime import date
from unittest import TestCase

from ..repeat import RepeatError, next_due

# A Saturday, so the weekly cases exercise both directions of the wrap.
SATURDAY = date(2026, 8, 8)


class NextDueTests(TestCase):
    """Unit tests for battodo.repeat.next_due."""

    def test_interval(t) -> None:
        cases = {
            '1d': date(2026, 8, 9),
            '15d': date(2026, 8, 23),
            '1w': date(2026, 8, 15),
            '2w': date(2026, 8, 22),
        }
        for spec, expected in cases.items():
            with t.subTest(spec):
                t.assertEqual(next_due(spec, SATURDAY), expected)

    def test_weekday(t) -> None:
        cases = {
            'weekly:sun': date(2026, 8, 9),
            'weekly:fri': date(2026, 8, 14),
            # Completed on its own weekday: a full week out, never today.
            'weekly:sat': date(2026, 8, 15),
            'WEEKLY:SUN': date(2026, 8, 9),
        }
        for spec, expected in cases.items():
            with t.subTest(spec):
                t.assertEqual(next_due(spec, SATURDAY), expected)

    def test_day_of_month(t) -> None:
        cases = {
            # Day-of-month still ahead: this month.
            ('monthly:15', SATURDAY): date(2026, 8, 15),
            # Already reached: next month.
            ('monthly:8', SATURDAY): date(2026, 9, 8),
            ('monthly:1', SATURDAY): date(2026, 9, 1),
            # Year boundary.
            ('monthly:1', date(2026, 12, 20)): date(2027, 1, 1),
            # Short month clamps to its last day.
            ('monthly:31', date(2026, 1, 31)): date(2026, 2, 28),
        }
        for (spec, completed), expected in cases.items():
            with t.subTest(f'{spec} on {completed}'):
                t.assertEqual(next_due(spec, completed), expected)

    def test_unreadable(t) -> None:
        for spec in ('sometimes', '0d', '3m', 'weekly:caturday', 'monthly:0'):
            with t.subTest(spec):
                with t.assertRaises(RepeatError) as caught:
                    next_due(spec, SATURDAY)
                t.assertIn(repr(spec), str(caught.exception))
