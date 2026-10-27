"""Compute an item's rank from its dates and priority (ADRs 0005, 0026).

Rank is a pure function of the file, the clock and the due-date curve,
so nothing is written to keep it current.

    rank = multiplier x due_factor x (1 + age_score)

An item starts at its multiplier and gains a full multiplier's worth for
every month it waits. The due-date curve then scales it. The default
curve is below 1 far ahead of the due date, rises through the due date,
and caps when the item is long overdue. Every term is *bounded*, so no
item outgrows its priority.

Every field is read tolerantly. These files are typed into by hand and
carry placeholders such as `[DUE:YYYY-MM-DD]`; an unreadable field
contributes nothing and never raises.
"""

from datetime import date
from itertools import pairwise
from math import isfinite

from .parser import TaskNode, parse_date

# `P` on the new scale. Absent reads as NEUTRAL, not zero: an
# unprioritized item still ranks by its dates. An explicit `P:0` parks it.
NEUTRAL_MULTIPLIER = 1.0
MAX_MULTIPLIER = 5.0
# Bump-inflated legacy values (1..125 in the live data) fold on to the
# scale order-preservingly, so no existing ordering is lost.
LEGACY_P_DIVISOR = 25

AGE_SCALE_DAYS = 30
AGE_CAP = 2.0
# A task with no readable due date keeps its rank unscaled.
UNDATED_FACTOR = 1.0
# The due-date factor curve: `days:factor` points, where `days` is
# today minus the due date. A negative day is before the due date.
DEFAULT_DUE_CURVE = '-30:0.5, -7:1.0, 0:2.0, 14:4.0'
CURVE_ERROR = 'a rank due curve point must read days:factor'
CURVE_DAY_ERROR = 'a rank due curve names a day twice'

# A decoded curve: its points, earliest day first.
Curve = list[tuple[int, float]]


def rank(task: TaskNode, today: date, curve: Curve) -> float:
    """The task's computed rank on `curve`. Higher sorts first."""
    scale = multiplier(task) * due_factor(task, today, curve)
    return scale * (1 + age_score(task, today))


def multiplier(task: TaskNode) -> float:
    """The task's priority as a 0-5 multiplier.

    Parameters
    ----------
    task : TaskNode
        Any task; `P` may be absent, legacy-scaled, or unparseable.

    Returns
    -------
    float
        0.0 for an explicitly parked item, otherwise 1.0 to 5.0.
    """
    raw = task.fields.get('P')
    if raw is None:
        return NEUTRAL_MULTIPLIER
    try:
        priority = int(raw)
    except ValueError:
        return NEUTRAL_MULTIPLIER
    if priority <= MAX_MULTIPLIER:
        return float(priority)
    return min(MAX_MULTIPLIER, 1 + priority / LEGACY_P_DIVISOR)


def due_factor(task: TaskNode, today: date, curve: Curve) -> float:
    """How the due date scales the rank, read off `curve`.

    Parameters
    ----------
    task : TaskNode
        Any task; `DUE` may be absent or unreadable.
    today : date
        The day the rank is for.
    curve : Curve
        The decoded due-date curve, earliest day first.

    Returns
    -------
    float
        1.0 for a task with no readable due date. Otherwise the curve's
        factor at today minus the due date.
    """
    due = parse_date(task.due)
    if due is None:
        return UNDATED_FACTOR
    days = max((today - due).days, curve[0][0])
    for (low_days, low_factor), (high_days, high_factor) in pairwise(curve):
        if days < high_days:
            share = (days - low_days) / (high_days - low_days)
            return low_factor + share * (high_factor - low_factor)
    return curve[-1][1]


def age_score(task: TaskNode, today: date) -> float:
    """How long the task has been waiting: +1 per month, capped at +2."""
    added = parse_date(task.added)
    if added is None:
        return 0.0
    days = max((today - added).days, 0)
    return min(AGE_CAP, days / AGE_SCALE_DAYS)


def parse_curve(value: str) -> Curve:
    """Decode a due-date curve from whichever source configured it.

    Parameters
    ----------
    value : str
        Comma-separated `days:factor` points, in any order.

    Returns
    -------
    Curve
        The points, earliest day first.

    Raises
    ------
    ValueError
        A segment is not a whole number of days and a finite factor of
        0 or more, or two segments name the same day.
    """
    points: dict[int, float] = {}
    for segment in value.split(','):
        days, factor = parse_point(segment)
        if days in points:
            raise ValueError(f'{CURVE_DAY_ERROR}: {segment.strip()!r}')
        points[days] = factor
    return sorted(points.items())


def parse_point(segment: str) -> tuple[int, float]:
    """Decode one `days:factor` point of a due-date curve.

    Raises
    ------
    ValueError
        The segment is not a whole number of days and a finite factor
        of 0 or more.
    """
    text = segment.strip()
    try:
        days_text, factor_text = text.split(':')
        days, factor = int(days_text), float(factor_text)
    except ValueError:
        raise ValueError(f'{CURVE_ERROR}: {text!r}') from None
    if not isfinite(factor) or factor < 0:
        raise ValueError(f'{CURVE_ERROR}: {text!r}')
    # A factor of -0 passes the bound; abs reads it as 0.0.
    return days, abs(factor)
