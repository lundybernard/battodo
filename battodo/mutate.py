"""Markdown mutations that also record events (ADR 0004, ADR 0005).

Every mutation edits the raw task line in place and appends an event, so
the markdown stays authoritative while the journal accumulates history.
Files with nothing to change are not rewritten at all, which keeps
mtimes stable for Syncthing.

Two mutations live here. `complete` implements SCHEMA.md's completion
rules: log the ancestry to `completed.md`, mark `[x]`, remove the block
once the whole thing is done, and reschedule a recurring task instead of
deleting it. `backfill` is the one-time `[ADDED:]` stamp that replaced
the daily bump, which ADR 0005 retired along with the `BUMPED` field and
the `TaskBumped` event: rank is computed from the files rather than
accumulated in them, so btodo has nothing to write once a day.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .journal import Journal, new_task_id
from .parser import Task, TodoFile, parse, parse_date, serialize, set_field
from .repeat import next_due
from .view import discover_lists

ADDED_EVENT = 'TaskAdded'
COMPLETED_EVENT = 'TaskCompleted'
DATE_FIELDS = ('DUE',)
COMPLETED_LOG = 'completed.md'
DONE_STATUS = 'DONE'
ANCESTRY_SEPARATOR = ' > '
# Field order for a completed.md entry. btodo authors those lines, so
# unlike a task line they are canonical, and they carry only SCHEMA.md's
# own grammar: `BUMPED` is retired, `ADDED` and `ID` are btodo
# extensions the log format knows nothing about.
LOG_FIELDS = ('P', 'LOE', 'DUE', 'REPEAT', 'TAGS')


class SelectionError(Exception):
    """A selector did not name exactly one open task.

    Carries the candidate titles when the match is ambiguous: the fix is
    always a longer selector or the task's `[ID:]`.
    """


@dataclass
class Match:
    """One open task, the list it lives in, and its ancestry."""

    path: Path
    doc: TodoFile
    trail: list[Task]

    @property
    def task(self) -> Task:
        return self.trail[-1]


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


def _set_fields(raw: str, updates: dict[str, str]) -> str:
    """Apply several field edits to one raw line, in order."""
    for name, value in updates.items():
        raw = set_field(raw, name, value)
    return raw


def _is_checklist_item(task: Task) -> bool:
    """A child carrying no fields: plain text, not an entity of its own.

    SCHEMA.md keeps these out of `completed.md`, and they must never be
    given an `[ID:]` -- carrying a field is exactly what distinguishes a
    subtask from a checklist item, so injecting one would silently
    promote the line.
    """
    return bool(task.indent) and not task.fields


def _stream_task(trail: list[Task]) -> Task:
    """The task whose event stream owns a mutation on `trail`'s target.

    Usually the target itself. A checklist item cannot hold an `[ID:]`,
    so its events are recorded against the nearest ancestor that can --
    at worst the top-level task, which never is one.
    """
    return next(
        task for task in reversed(trail) if not _is_checklist_item(task)
    )


def _identify(task: Task, ids: dict[int, str]) -> str:
    """The task's `[ID:]`, allocating one on first mediated mutation."""
    return ids.setdefault(task.raw_index, task.task_id or new_task_id())


# --- Completion -----------------------------------------------------


def _lists(directory: Path) -> Iterator[tuple[Path, TodoFile]]:
    for path in discover_lists(directory):
        yield path, parse(path.read_text())


def _descend(tasks: list[Task], trail: list[Task]) -> Iterator[list[Task]]:
    """Every task at any depth, each with its ancestry trail."""
    for task in tasks:
        found = [*trail, task]
        yield found
        yield from _descend(task.children, found)


def _selects(task: Task, selector: str) -> bool:
    return task.task_id == selector or selector.lower() in task.title.lower()


def find_task(directory: Path, selector: str) -> Match:
    """The one open task `selector` names, by `[ID:]` or title text.

    Searches every discovered list, parked ones included, at every
    depth: subtasks have no `[ID:]` until btodo first touches them, so
    title matching is the only way to reach one.

    Raises
    ------
    SelectionError
        If nothing matches, or more than one task does.
    """
    matches = [
        Match(path, doc, trail)
        for path, doc in _lists(directory)
        for trail in _descend(doc.tasks, [])
        if not trail[-1].done and _selects(trail[-1], selector)
    ]
    by_id = [match for match in matches if match.task.task_id == selector]
    matches = by_id or matches

    if not matches:
        raise SelectionError(f'no open task matches {selector!r}')
    if len(matches) > 1:
        titles = ', '.join(repr(match.task.title) for match in matches)
        raise SelectionError(
            f'{selector!r} matches {len(matches)} open tasks: {titles}'
        )
    return matches[0]


def _completed_trails(match: Match) -> list[list[Task]]:
    """Ancestry trails for the target and each ancestor it finishes.

    A task is complete when all its children are checked (SCHEMA.md), so
    checking the last open child completes the parent, and that may
    complete its parent in turn. Deepest first, which is the order the
    completions get logged.
    """
    trails = [match.trail]
    for depth in reversed(range(len(match.trail) - 1)):
        parent, child = match.trail[depth], match.trail[depth + 1]
        if not all(c.done or c is child for c in parent.children):
            break
        trails.append(match.trail[: depth + 1])
    return trails


def _block_indices(task: Task) -> set[int]:
    """Every line the task owns: its own, its notes, its children's."""
    indices = {task.raw_index, *task.note_indices}
    for child in task.children:
        indices |= _block_indices(child)
    return indices


def _drop_lines(lines: list[str], drop: set[int]) -> list[str]:
    """Remove lines, collapsing the blank run a removed block leaves.

    Items are separated by a blank line in some lists and not in
    others, so the rule is symmetric rather than positional: only when
    the removal would leave two blanks adjacent does one of them go.
    """
    if not drop:
        return lines
    before, after = min(drop) - 1, max(drop) + 1
    if (
        before >= 0
        and after < len(lines)
        and not lines[before].strip()
        and not lines[after].strip()
    ):
        drop = drop | {after}
    return [line for index, line in enumerate(lines) if index not in drop]


def _log_entry(path: Path, trail: list[Task], status: str, today: date) -> str:
    """One `completed.md` record: date, category, status, ancestry."""
    task = trail[-1]
    fields = ' '.join(
        f'[{name}:{task.fields[name]}]'
        for name in LOG_FIELDS
        if name in task.fields
    )
    ancestry = ANCESTRY_SEPARATOR.join(item.title for item in trail)
    entry = f'{today.isoformat()} | {path.stem} | {status} | {ancestry}'
    return f'{entry} {fields}' if fields else entry


def _append_log(directory: Path, entries: list[str]) -> None:
    """Append to `completed.md`, which is append-only (SCHEMA.md)."""
    if not entries:
        return
    path = directory / COMPLETED_LOG
    existing = path.read_text() if path.exists() else ''
    lead = '' if not existing or existing.endswith('\n') else '\n'
    with path.open('a', encoding='utf-8') as handle:
        handle.write(lead + '\n'.join(entries) + '\n')


def _mark_done(raw: str) -> str:
    """Check the box on a raw line, leaving the rest of it alone."""
    return raw.replace('- [ ]', '- [x]', 1)


def complete(directory: Path, selector: str, today: date) -> list[str]:
    """Complete the task `selector` names. Returns the log entries.

    Follows SCHEMA.md: the completion is logged to `completed.md` with
    its full `Parent > Child` ancestry, the item is checked off, and the
    whole block goes once the top-level task is done -- unless it
    repeats, in which case it stays with a recomputed `DUE`. Completing
    the last open child completes its parent too, so a finished block
    never lingers half-checked.

    Parameters
    ----------
    directory : Path
        The source directory: its lists, its `completed.md`, its
        journal.
    selector : str
        A task `[ID:]` or part of a title.
    today : date
        The completion date, in the user's local day.

    Returns
    -------
    list of str
        The `completed.md` entries written, deepest task first. Empty
        when the target was a checklist item, which SCHEMA.md does not
        log.

    Raises
    ------
    SelectionError
        If `selector` does not name exactly one open task.
    RepeatError
        If a completed recurring task carries a `[REPEAT:]` btodo
        cannot read. Raised before anything is written.
    """
    match = find_task(directory, selector)
    trails = _completed_trails(match)
    root = match.trail[0]
    root_done = len(trails[-1]) == 1
    rescheduled = (
        next_due(root.repeat, today) if root_done and root.repeat else None
    )

    ids: dict[int, str] = {}
    streams = [_identify(_stream_task(trail), ids) for trail in trails]
    lines = list(match.doc.lines)

    if root_done:
        drop = _block_indices(root)
        if rescheduled is not None:
            # The recurrence is the same task rescheduled, so it keeps
            # its id, its notes and its `[ADDED:]`, which ADR 0005
            # writes once and never updates. Children do not carry
            # over.
            drop -= {root.raw_index, *root.note_indices}
            lines[root.raw_index] = _set_fields(
                root.raw,
                {
                    'DUE': rescheduled.isoformat(),
                    'ID': ids[root.raw_index],
                },
            )
        lines = _drop_lines(lines, drop)
    else:
        for index, task_id in ids.items():
            lines[index] = set_field(lines[index], 'ID', task_id)
        for trail in trails:
            index = trail[-1].raw_index
            lines[index] = _mark_done(lines[index])

    entries = [
        _log_entry(match.path, trail, DONE_STATUS, today)
        for trail in trails
        if not _is_checklist_item(trail[-1])
    ]

    match.doc.lines = lines
    match.path.write_text(serialize(match.doc))
    _append_log(directory, entries)

    journal = Journal(directory)
    for trail, stream in zip(trails, streams):
        task = trail[-1]
        delta: dict[str, list[Any]] = {'done': [False, True]}
        if task is root and rescheduled is not None:
            delta['DUE'] = [root.due, rescheduled.isoformat()]
        journal.append(
            COMPLETED_EVENT,
            f'task/{stream}',
            {
                'delta': delta,
                # Pre-state, as everywhere here: the delta says what
                # changed, the snapshot says what it changed from.
                'snapshot': task_snapshot(task),
                'ancestry': ANCESTRY_SEPARATOR.join(
                    item.title for item in trail
                ),
            },
            actor='agent',
            source_file=match.path.name,
        )

    return entries


# --- Backfill -------------------------------------------------------


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

        doc.lines[task.raw_index] = _set_fields(task.raw, updates)
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
