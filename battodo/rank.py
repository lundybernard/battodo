"""Compute an item's rank from its dates and priority (ADR 0005).

Rank replaces the stored, daily-bumped `P`: it is a pure function of the
file and the clock, so nothing is written to keep it current.

    rank = multiplier x (1 + age_score + due_score)

An item starts at its multiplier, gains a full multiplier's worth for
every month it waits, ramps up over the fortnight before it comes due,
and gains another for every week it is late. Every term is *bounded* --
that is what the stored `P` lacked, and why an ignored overdue item used
to grow without limit until priority stopped meaning anything.

Every field is read tolerantly. These files are typed into by hand and
carry placeholders such as `[DUE:YYYY-MM-DD]`; an unreadable field
contributes nothing and never raises.
"""

from datetime import date

from .parser import Task, parse_date

# `P` on the new scale. Absent reads as NEUTRAL, not zero: an
# unprioritized item still ranks by its dates. An explicit `P:0` parks it.
NEUTRAL_MULTIPLIER = 1.0
MAX_MULTIPLIER = 5.0
# Bump-inflated legacy values (1..125 in the live data) fold on to the
# scale order-preservingly, so no existing ordering is lost.
LEGACY_P_DIVISOR = 25

BASE_URGENCY = 1.0
AGE_SCALE_DAYS = 30
AGE_CAP = 2.0
DUE_HORIZON_DAYS = 14
OVERDUE_SCALE_DAYS = 7
DUE_CAP = 3.0


def multiplier(task: Task) -> float:
    """The task's priority as a 0-5 multiplier.

    Parameters
    ----------
    task : Task
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


def age_score(task: Task, today: date) -> float:
    """How long the task has been waiting: +1 per month, capped at +2."""
    added = parse_date(task.added)
    if added is None:
        return 0.0
    days = (today - added).days
    if days <= 0:
        return 0.0
    return min(AGE_CAP, days / AGE_SCALE_DAYS)


def due_score(task: Task, today: date) -> float:
    """How pressing the due date is: ramps to +1, then +1 per week late."""
    due = parse_date(task.due)
    if due is None:
        return 0.0
    days = (due - today).days
    if days < 0:
        return min(DUE_CAP, 1 - days / OVERDUE_SCALE_DAYS)
    if days >= DUE_HORIZON_DAYS:
        return 0.0
    return (DUE_HORIZON_DAYS - days) / DUE_HORIZON_DAYS


def rank(task: Task, today: date) -> float:
    """The task's computed rank. Higher sorts first."""
    urgency = BASE_URGENCY + age_score(task, today) + due_score(task, today)
    return multiplier(task) * urgency
