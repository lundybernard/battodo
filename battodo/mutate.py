"""Markdown mutations that also record events (ADR 0004, ADR 0005).

Every mutation edits the raw task line in place and appends an event, so
the markdown stays authoritative while the journal accumulates history.
Files with nothing to change are not rewritten at all, which keeps
mtimes stable for Syncthing.

The only mutation here is the one-time `[ADDED:]` backfill. It replaces
the daily bump, which ADR 0005 retired along with the `BUMPED` field and
the `TaskBumped` event: rank is now computed from the files rather than
accumulated in them, so btodo has nothing to write once a day.
"""

from datetime import date
from pathlib import Path
from typing import Any

from .journal import Journal, new_task_id
from .parser import Task, TodoFile, parse, parse_date, serialize
from .view import discover_lists

ADDED_EVENT = 'TaskAdded'
DATE_FIELDS = ('DUE',)


def task_snapshot(task: Task) -> dict[str, Any]:
    """The task's full state at event time.

    Snapshots are what make a later authority flip replayable despite
    hand-edits that never reached the journal.
    """
    return {
        'title': task.title,
        'done': task.done,
        'fields': dict(task.fields),
    }


def _append_fields(task: Task, updates: dict[str, str]) -> str:
    """Append fields to one raw line, leaving every existing one in place.

    Only ever called for fields the task does not have, so nothing is
    replaced and no other field shifts position.
    """
    fields = ' '.join(f'[{name}:{value}]' for name, value in updates.items())
    return f'{task.raw.rstrip()} {fields}'


def _needs_added(task: Task) -> bool:
    """Open top-level tasks with no `[ADDED:]`, whose dates all parse.

    A task whose date fields cannot be read is never touched. Template
    files carry placeholders like `[DUE:YYYY-MM-DD]`, and rewriting a
    line btodo cannot interpret is exactly the corruption the round-trip
    guarantee exists to prevent.
    """
    if task.done or task.indent or task.added:
        return False
    return all(
        parse_date(task.fields[name]) is not None
        for name in DATE_FIELDS
        if name in task.fields
    )


def backfill_file(path: Path, today: date, journal: Journal) -> list[str]:
    """Stamp `[ADDED:today]` where it is missing. Returns the titles.

    `today` is the migration date, not the real add date -- that is not
    recoverable from the files (ADR 0005). Age accrues from here.
    """
    doc: TodoFile = parse(path.read_text())
    stamped: list[str] = []

    for task in doc.tasks:
        if not _needs_added(task):
            continue

        snapshot = task_snapshot(task)
        task_id = task.task_id or new_task_id()
        updates = {'ADDED': today.isoformat()}
        if not task.task_id:
            updates['ID'] = task_id

        doc.lines[task.raw_index] = _append_fields(task, updates)
        stamped.append(task.title)

        journal.append(
            ADDED_EVENT,
            f'task/{task_id}',
            {
                'delta': {'ADDED': [None, today.isoformat()]},
                'snapshot': snapshot,
                # The date is the migration's, not the task's. A replay
                # must not read it as an observed fact.
                'backfilled': True,
            },
            actor='agent',
            source_file=path.name,
        )

    if stamped:
        path.write_text(serialize(doc))
    return stamped


def backfill_all(directory: Path, today: date) -> dict[str, list[str]]:
    """Backfill every discovered list in `directory`.

    Parked lists are included: they opt out of views, not of existing,
    and an unparked item should carry an add date.
    """
    journal = Journal(directory)
    result = {}
    for path in discover_lists(directory):
        stamped = backfill_file(path, today, journal)
        if stamped:
            result[path.name] = stamped
    return result
