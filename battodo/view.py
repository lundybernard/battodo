"""Render open todo items as sorted markdown tables (R3).

Selection matches `view_todos.py` in the live system: open items only,
future-dated *recurring* items suppressed. Note that SCHEMA.md's prose
is stricter than this (it would also hide future-dated non-recurring
items); R3 and the script agree with each other, so btodo follows them.

Ordering does *not* match the script any more. Items sort by the rank
computed in `rank.py` (ADR 0005) rather than by stored priority, so the
table shows that rank -- the ordering is otherwise unreadable, since
nothing in the file states it.

The host clock runs UTC while todos are anchored to the user's local
day, so the zone is named rather than a fixed offset.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .parser import Task, TodoFile, parse, parse_date
from .rank import multiplier, rank


@dataclass
class Config:
    """Where btodo looks for lists.

    One source for now; R6 turns this into a list of sources once the
    discovery/merge semantics in ADR 0004 are settled.
    """

    source_dir: str = '~/todo'


class SourceError(Exception):
    """The configured source directory yields no todo lists.

    Raised rather than rendering an empty view: pointed at a home
    directory with no `todo/` in it, btodo printed a bare header and
    exited 0, which reads as "nothing to do" instead of "I looked in the
    wrong place". The message always carries the resolved path.
    """


TZ = ZoneInfo('America/Los_Angeles')
ALWAYS_ACTIVE = frozenset({'study', 'career', 'events'})
CATEGORY_ORDER = ['work', 'chores', 'study', 'career', 'events']
OPEN_HEADING = '## Open'
NO_DUE_SORTS_LAST = 'zzzz'
# A list carrying this marker anywhere is parked: still discovered, so
# mutations reach it, but never surfaced in a view (ADR 0005).
PARKED_MARKER = 'battodo:parked'


def active_categories(now: datetime) -> set[str]:
    """Categories whose time window is open at `now`."""
    active = set(ALWAYS_ACTIVE)
    is_weekday = now.weekday() < 5
    hour = now.hour
    if is_weekday and 9 <= hour < 17:
        active.add('work')
    if is_weekday and 17 <= hour < 21:
        active.add('chores')
    if not is_weekday and 10 <= hour < 20:
        active.add('chores')
    return active


def discover_lists(directory: Path) -> list[Path]:
    """Every markdown file in `directory` that is a todo list.

    The predicate is the presence of a `## Open` heading. This is what
    fixes the hard-coded five-category bug: ad-hoc lists such as
    backlog.md are picked up, while SCHEMA.md, CLAUDE.md, and the
    differently-formatted completed.md are excluded.

    Parked lists are included -- opting out of *views* is not opting out
    of existing, and a mutation must still reach them.
    """
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob('*.md')
        if OPEN_HEADING in path.read_text()
    )


def visible_tasks(doc: TodoFile, today: date) -> list[Task]:
    """Open top-level tasks, minus suppressed future recurrences."""
    visible = []
    for task in doc.tasks:
        if task.done:
            continue
        due = parse_date(task.due)
        if due and task.repeat and due > today:
            continue
        visible.append(task)
    return visible


def sort_key(task: Task, today: date) -> tuple[float, str, str]:
    """Rank descending, then nearest due, undated last, then title."""
    return (
        -rank(task, today),
        task.due or NO_DUE_SORTS_LAST,
        task.title,
    )


def due_label(due: str | None, today: date) -> str:
    if due is None:
        return ''
    parsed = parse_date(due)
    if parsed is None:
        # a placeholder such as YYYY-MM-DD: show it verbatim
        return due
    if parsed < today:
        return 'OVERDUE'
    if parsed == today:
        return 'TODAY'
    return due


def _table(tasks: list[Task], today: date) -> list[str]:
    rows = [
        '| Rank | P | LOE | Task | Due |',
        '|------|---|-----|------|-----|',
    ]
    for task in tasks:
        loe = task.loe if task.loe is not None else ''
        open_children = [c for c in task.children if not c.done]
        badge = f' _({len(open_children)} subtasks)_' if open_children else ''
        rows.append(
            f'| {rank(task, today):.1f} | {multiplier(task):g} | {loe} '
            f'| {task.title}{badge} | {due_label(task.due, today)} |'
        )
    return rows


def build_view(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int = 5,
) -> str:
    """Render the tables for every active category in `directory`."""
    today = now.date()
    resolved = directory.expanduser().resolve()
    if not resolved.is_dir():
        raise SourceError(f'todo source directory not found: {resolved}')

    paths = discover_lists(resolved)
    if not paths:
        raise SourceError(
            f'no todo lists (no file with a "{OPEN_HEADING}" heading) '
            f'in: {resolved}'
        )

    active = active_categories(now)
    header = (
        f'**{now.strftime("%A")} {today} {now.strftime("%H:%M")}** '
        f'— active: {", ".join(sorted(active))}'
    )
    out = [header, '']

    ordered = sorted(
        paths,
        key=lambda p: (
            CATEGORY_ORDER.index(p.stem)
            if p.stem in CATEGORY_ORDER
            else len(CATEGORY_ORDER),
            p.stem,
        ),
    )

    for path in ordered:
        category = path.stem
        if category in CATEGORY_ORDER and category not in active:
            continue
        text = path.read_text()
        if PARKED_MARKER in text:
            continue
        tasks = sorted(
            visible_tasks(parse(text), today),
            key=lambda task: sort_key(task, today),
        )
        if not tasks:
            continue
        if not show_all:
            tasks = tasks[:top_n]
        out.append(f'### {category.capitalize()}')
        out.append('')
        out.extend(_table(tasks, today))
        out.append('')

    return '\n'.join(out)
