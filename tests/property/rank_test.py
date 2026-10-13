"""Property tests for `battodo.rank`, driven by Hypothesis.

Each case ranks one task with a drawn due date. The expected factor
derives from the drawn date and the curve, never from the code under
test.
"""

from datetime import date, timedelta
from unittest import TestCase

from hypothesis import example, given
from hypothesis import strategies as st

from battodo.parser import TaskNode
from battodo.rank import DEFAULT_DUE_CURVE, Curve, due_factor, parse_curve

from .strategies import NEARBY, TODAY, grammar

# The curve a task ranks on when the configuration names none.
CURVE = parse_curve(DEFAULT_DUE_CURVE)
# The days a drawn curve puts its points on.
CURVE_DAYS = st.integers(min_value=-400, max_value=400)
# The factors a drawn curve takes.
CURVE_FACTORS = st.floats(min_value=0, max_value=10)


class DueFactorTests(TestCase):
    """Property tests for battodo.rank.due_factor."""

    @given(st.dates(min_value=TODAY - NEARBY, max_value=TODAY + NEARBY))
    @example(due=TODAY + timedelta(days=30))
    @example(due=TODAY + timedelta(days=7))
    @example(due=TODAY)
    @example(due=TODAY - timedelta(days=14))
    def test_default_curve(t, due: date) -> None:
        task = dated_task(due.isoformat())

        ret = due_factor(task, TODAY, CURVE)

        t.assertAlmostEqual(ret, default_factor((TODAY - due).days))

    @given(grammar.field_values)
    @example(value='')
    @example(value='2000-01-01')
    @example(value='2999-01-01')
    def test_bounds(t, value: str) -> None:
        task = dated_task(value)

        ret = due_factor(task, TODAY, CURVE)

        t.assertGreaterEqual(ret, 0.5)
        t.assertLessEqual(ret, 4.0)

    @given(st.data())
    def test_order(t, data: st.DataObject) -> None:
        curve = data.draw(rising_curves())
        pair = data.draw(st.lists(CURVE_DAYS, min_size=2, max_size=2))
        earlier, later = sorted(pair)
        before, after = task_past_due(earlier), task_past_due(later)

        ret = due_factor(before, TODAY, curve), due_factor(after, TODAY, curve)

        # The later a task runs against its due date, the higher it
        # stands on a curve whose factors do not fall.
        t.assertLessEqual(*ret)


def dated_task(due: str) -> TaskNode:
    """One open top-level task whose only field is `due`."""
    return TaskNode(
        raw_index=0,
        indent=0,
        done=False,
        title='A dated task',
        fields={'DUE': due},
    )


def task_past_due(days: int) -> TaskNode:
    """A task whose due date falls `days` before TODAY."""
    due = TODAY - timedelta(days=days)
    return dated_task(due.isoformat())


def default_factor(days: int) -> float:
    """The default curve as ADR 0026 tabulates it, at `days` past due."""
    if days <= -30:
        return 0.5
    if days <= -7:
        return 0.5 + 0.5 * (days + 30) / 23
    if days <= 0:
        return 1.0 + (days + 7) / 7
    if days <= 14:
        return 2.0 + 2.0 * days / 14
    return 4.0


@st.composite
def rising_curves(draw: st.DrawFn) -> Curve:
    """A curve whose factors do not fall as its days rise."""
    days = sorted(draw(st.lists(CURVE_DAYS, min_size=1, unique=True)))
    count = len(days)
    drawn = draw(st.lists(CURVE_FACTORS, min_size=count, max_size=count))
    return list(zip(days, sorted(drawn), strict=True))
