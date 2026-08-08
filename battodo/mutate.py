"""Markdown mutations that also record events (R4, ADR 0004).

Every mutation edits the raw task line in place and appends an event, so
the markdown stays authoritative while the journal accumulates history.
Files with nothing to change are not rewritten at all, which keeps
mtimes stable for Syncthing.
"""

import re
from datetime import date
from pathlib import Path
from typing import Any

from .journal import Journal, new_task_id
from .parser import Task, TodoFile, parse, parse_date, serialize
from .view import discover_lists

BUMP_EVENT = 'TaskBumped'


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


def _set_fields(task: Task, updates: dict[str, str]) -> str:
    """Apply several field updates to one raw line, in place."""
    line = task.raw
    present = dict(task.fields)
    for name, value in updates.items():
        if name in present:
            line = re.sub(
                rf'\[{name}:[^\]]*\]', f'[{name}:{value}]', line, count=1
            )
        else:
            line = f'{line.rstrip()} [{name}:{value}]'
            present[name] = value
    return line


def _is_bumpable(task: Task, today: date) -> bool:
    """The SCHEMA.md daily-bump predicate, top-level tasks only.

    A task whose date fields cannot be parsed is never touched. Template
    files carry placeholders like `[DUE:YYYY-MM-DD]`, and rewriting a
    line btodo cannot interpret is exactly the corruption the round-trip
    guarantee exists to prevent.
    """
    if task.done or task.indent:
        return False
    if task.due:
        due = parse_date(task.due)
        if due is None or due > today:
            return False
    if task.bumped:
        bumped = parse_date(task.bumped)
        if bumped is None or bumped >= today:
            return False
    return True


def bump_file(path: Path, today: date, journal: Journal) -> list[str]:
    """Apply the daily bump to one list. Returns the titles bumped."""
    doc: TodoFile = parse(path.read_text())
    bumped: list[str] = []

    for task in doc.tasks:
        if not _is_bumpable(task, today):
            continue

        snapshot = task_snapshot(task)
        task_id = task.task_id or new_task_id()
        updates = {
            'P': str(task.priority + 1),
            'BUMPED': today.isoformat(),
        }
        if not task.task_id:
            updates['ID'] = task_id

        doc.lines[task.raw_index] = _set_fields(task, updates)
        bumped.append(task.title)

        journal.append(
            BUMP_EVENT,
            f'task/{task_id}',
            {
                'delta': {
                    'P': [task.priority, task.priority + 1],
                    'BUMPED': [task.bumped, today.isoformat()],
                },
                'snapshot': snapshot,
            },
            actor='agent',
            source_file=path.name,
        )

    if bumped:
        path.write_text(serialize(doc))
    return bumped


def bump_all(directory: Path, today: date) -> dict[str, list[str]]:
    """Bump every discovered list in `directory`.

    Operating on all discovered lists is the R4 fix: the current scripts
    hard-code five category filenames and silently skip backlog.md and
    other ad-hoc lists.
    """
    journal = Journal(directory)
    result = {}
    for path in discover_lists(directory):
        bumped = bump_file(path, today, journal)
        if bumped:
            result[path.name] = bumped
    return result
