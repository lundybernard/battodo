"""Next due date for a recurring task (SCHEMA.md `[REPEAT:]`).

Two kinds, and the distinction is the whole point of the field. An
*interval* (`Nd`/`Nw`) is anchored to the completion date, so it drifts
with when the task actually got done -- "pay the bill 15 days after the
last payment". A *schedule* (`weekly:DAY`/`monthly:N`) is anchored to
the calendar and must not drift; the previous `DUE` is ignored entirely.

Both kinds land strictly after the completion date: finishing a
`weekly:fri` task on a Friday schedules the next one a week out, not
the same day.
"""

import re
from calendar import monthrange
from datetime import date, timedelta

WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
DAYS_PER_UNIT = {'d': 1, 'w': 7}

INTERVAL_RE = re.compile(r'^([1-9]\d*)([dw])$')
WEEKLY_RE = re.compile(rf'^weekly:({"|".join(WEEKDAYS)})$')
MONTHLY_RE = re.compile(r'^monthly:([1-9]|[12][0-9]|3[01])$')


class RepeatError(ValueError):
    """A `[REPEAT:]` value btodo cannot interpret.

    Raised rather than dropping the recurrence: completing a recurring
    task removes its block, so a silently unscheduled item is data loss.
    """


def next_due(spec: str, completed: date) -> date:
    """The next due date for `spec`, given when the task was completed.

    Parameters
    ----------
    spec : str
        A `[REPEAT:]` value: `Nd`, `Nw`, `weekly:DAY`, or `monthly:N`.
    completed : date
        The completion date, in the user's local day.

    Returns
    -------
    date
        Always strictly after `completed`.

    Raises
    ------
    RepeatError
        If `spec` is not one of the four recognised forms.
    """
    value = spec.strip().lower()

    if interval := INTERVAL_RE.match(value):
        count, unit = interval.groups()
        return completed + timedelta(days=int(count) * DAYS_PER_UNIT[unit])
    if weekly := WEEKLY_RE.match(value):
        return _next_weekday(weekly.group(1), completed)
    if monthly := MONTHLY_RE.match(value):
        return _next_month_day(int(monthly.group(1)), completed)

    raise RepeatError(f'unrecognised REPEAT value: {spec!r}')


def _next_weekday(name: str, completed: date) -> date:
    ahead = (WEEKDAYS.index(name) - completed.weekday()) % 7
    return completed + timedelta(days=ahead or 7)


def _next_month_day(day: int, completed: date) -> date:
    year, month = completed.year, completed.month
    if completed.day >= day:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    # Short months clamp: `monthly:31` is the last day of February.
    return date(year, month, min(day, monthrange(year, month)[1]))
