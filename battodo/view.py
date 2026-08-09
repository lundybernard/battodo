"""Render open todo items as sorted, aligned tables (R3).

Output is plain aligned text, not markdown. The pipe tables this started
as were written for a chat client to re-render; read in a terminal --
which is where `btodo view` actually lands -- they printed ragged,
because a markdown table needs no column widths and so nothing computed
any. Widths here come from the content, once for the whole view, so the
columns line up down the page and not merely within one category.

Terminal width is read here rather than at the CLI boundary: the width
is an input to the layout, and `build_view` is the only caller that
knows whether one was supplied. Passing `width` explicitly overrides the
probe, which is what keeps the layout tests independent of `$COLUMNS`.

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
from json import dumps
from pathlib import Path
from shutil import get_terminal_size
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

# Layout. TASK is the elastic column: every other one is as wide as its
# widest value, and the titles absorb whatever room is left over.
COLUMNS = ('RANK', 'P', 'LOE', 'TASK', 'DUE')
ALIGN = ('>', '>', '>', '<', '<')
TASK_COLUMN = COLUMNS.index('TASK')
INDENT = '  '
GAP = '  '
RULE = '─'
ELLIPSIS = '…'
# Below this, titles are too clipped to identify; a line that overruns a
# very narrow terminal and wraps beats one that says nothing.
MIN_TASK_WIDTH = 20


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


def open_children(task: Task) -> list[Task]:
    """The task's incomplete children: subtasks and checklist items."""
    return [child for child in task.children if not child.done]


def _row(task: Task, today: date) -> tuple[str, ...]:
    """One task as its five cell strings, in COLUMNS order."""
    children = open_children(task)
    # `(+2)`, not `(2 subtasks)`: it stays out of the title's way, and
    # the count needs no plural.
    badge = f' (+{len(children)})' if children else ''
    return (
        f'{rank(task, today):.1f}',
        f'{multiplier(task):.1f}',
        '' if task.loe is None else str(task.loe),
        f'{task.title}{badge}',
        due_label(task.due, today),
    )


def _table_width(widths: list[int]) -> int:
    return len(INDENT) + sum(widths) + len(GAP) * (len(COLUMNS) - 1)


def _column_widths(rows: list[tuple[str, ...]], width: int) -> list[int]:
    """Width of each column: its widest cell, TASK fitted to `width`.

    Parameters
    ----------
    rows : list[tuple[str, ...]]
        Every row in the whole view, so one set of widths serves all of
        its tables.
    width : int
        Terminal width to fit the rendered line into.
    """
    widths = [
        max([len(name), *(len(row[index]) for row in rows)])
        for index, name in enumerate(COLUMNS)
    ]
    room = width - (_table_width(widths) - widths[TASK_COLUMN])
    widths[TASK_COLUMN] = max(MIN_TASK_WIDTH, min(widths[TASK_COLUMN], room))
    return widths


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + ELLIPSIS


def _line(row: tuple[str, ...], widths: list[int]) -> str:
    """Pad and align one row's cells. Trailing space is stripped."""
    cells = list(row)
    cells[TASK_COLUMN] = _clip(cells[TASK_COLUMN], widths[TASK_COLUMN])
    padded = (
        f'{cell:{align}{size}}'
        for cell, align, size in zip(cells, ALIGN, widths)
    )
    return f'{INDENT}{GAP.join(padded)}'.rstrip()


def _heading(category: str, widths: list[int]) -> str:
    """A titled rule spanning the table, e.g. `-- Work ------`.

    Ruled to the table's own width rather than the terminal's: the two
    differ only where the MIN_TASK_WIDTH floor has already overrun a
    very narrow terminal, and a divider that wraps looks worse than a
    row that does.
    """
    title = category.replace('-', ' ').capitalize()
    prefix = f'{RULE * 2} {title} '
    return prefix + RULE * max(0, _table_width(widths) - len(prefix))


def _select(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int,
) -> tuple[set[str], list[tuple[str, list[Task], int]]]:
    """What a view shows: the active set, and each category with its tasks.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    now : datetime
        The clock, which decides both the active set and every rank.
    show_all : bool
        Keep every task rather than the top `top_n` per category.
    top_n : int
        How many tasks survive per category when `show_all` is false.

    Returns
    -------
    set of str
        The categories whose window is open at `now`.
    list of (str, list of Task, int)
        Categories in display order, each with its tasks ranked and the
        number of them held back by `top_n`.

    Raises
    ------
    SourceError
        The directory is missing, or holds no todo lists.
    """
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
    ordered = sorted(
        paths,
        key=lambda p: (
            CATEGORY_ORDER.index(p.stem)
            if p.stem in CATEGORY_ORDER
            else len(CATEGORY_ORDER),
            p.stem,
        ),
    )

    selected = []
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
        shown = tasks if show_all else tasks[:top_n]
        selected.append((category, shown, len(tasks) - len(shown)))

    return active, selected


def build_view(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int = 5,
    width: int = 0,
) -> str:
    """Render the tables for every active category in `directory`.

    `width` is the terminal width to lay the columns out in; 0 probes
    the terminal (80 columns when there is none, e.g. a pipe).
    """
    today = now.date()
    active, selected = _select(directory, now, show_all=show_all, top_n=top_n)

    header = (
        f'{now.strftime("%A")} {today} {now.strftime("%H:%M")} '
        f'— active: {", ".join(sorted(active))}'
    )

    # Rendering waits until every section is built: the columns are
    # sized against the whole view, not one category at a time.
    sections = [
        (category, [_row(task, today) for task in tasks], hidden)
        for category, tasks, hidden in selected
    ]

    width = width or get_terminal_size().columns
    widths = _column_widths(
        [row for _, rows, _ in sections for row in rows], width
    )

    out = [header]
    for category, rows, hidden in sections:
        out.append('')
        out.append(_heading(category, widths))
        out.append(_line(COLUMNS, widths))
        out.extend(_line(row, widths) for row in rows)
        if hidden:
            out.append(f'{INDENT}{ELLIPSIS} and {hidden} more')

    return '\n'.join(out)


def _task_json(task: Task, today: date) -> dict[str, object]:
    return {
        'id': task.task_id,
        'title': task.title,
        'rank': round(rank(task, today), 2),
        'priority': multiplier(task),
        'loe': task.loe,
        'due': task.due,
        'added': task.added,
        'repeat': task.repeat,
        'tags': task.tags,
        'subtasks': len(open_children(task)),
    }


def build_json(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int = 5,
) -> str:
    """Serialize the same selection `build_view` renders.

    The schema is a contract for agents (R2), so it carries stored
    fields verbatim -- no OVERDUE/TODAY labels, no column widths. Task
    arrays are in rank order; `rank` itself is rounded for display and
    must not be used to re-sort.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    now : datetime
        The clock, which decides both the active set and every rank.
    show_all : bool
        Emit every task rather than the top `top_n` per category.
    top_n : int, optional
        How many tasks survive per category when `show_all` is false.

    Returns
    -------
    str
        A JSON document::

            {"date": "2026-08-05",
             "active": ["career", "events", "study", "work"],
             "categories": [{"name": "work", "tasks": [
                 {"id": null, "title": "...", "rank": 6.0,
                  "priority": 2.0, "loe": null, "due": null,
                  "added": "2026-05-10", "repeat": null,
                  "tags": [], "subtasks": 0}]}]}

    Raises
    ------
    SourceError
        The directory is missing, or holds no todo lists.
    """
    today = now.date()
    active, selected = _select(directory, now, show_all=show_all, top_n=top_n)
    return dumps(
        {
            'date': today.isoformat(),
            'active': sorted(active),
            'categories': [
                {
                    'name': category,
                    'tasks': [_task_json(task, today) for task in tasks],
                }
                for category, tasks, _ in selected
            ],
        },
        indent=2,
    )
