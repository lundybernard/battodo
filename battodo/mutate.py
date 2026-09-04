"""Markdown mutations that also record events (ADR 0004, ADR 0005).

Every mutation edits the raw task line in place and appends an event, so
the markdown stays authoritative while the journal accumulates history.
A file with nothing to change is not rewritten at all, so file sync
sees no change.

`add_task` and `add_subtask` create rather than edit. A new top-level
task lands as the last entry of a named list's `## Open` section,
carrying only the fields the caller gave it plus the `[ADDED:]` and
`[ID:]` btodo owns. A subtask lands last in its parent's block, one
indent level deeper: the markdown states the relation by indentation,
and the event names the parent by id.

`complete` implements SCHEMA.md's completion rules: log the ancestry to
`completed.md`, mark `[x]`, remove the block once the whole thing is
done, and reschedule a recurring task instead of deleting it. `scratch`
is the same plumbing for abandoning a task rather than finishing it:
the block goes, the log records it as SCRATCHED, and nothing cascades
or reschedules. `update_task` edits a task in place: it writes the
fields and the title it is given and touches nothing else. `backfill`
stamps `[ADDED:]` once on every task that lacks it.
"""

from datetime import date
from pathlib import Path
from typing import Any

from .journal import Journal, new_task_id
from .lists import discover_lists
from .parser import (
    OPEN_HEADING,
    TaskNode,
    TodoFile,
    append_open,
    parse,
    parse_date,
    serialize,
    set_field,
    set_title,
)
from .repeat import next_due
from .selector import TaskRecord, TaskSelection

ADDED_EVENT = 'TaskAdded'
COMPLETED_EVENT = 'TaskCompleted'
SCRATCHED_EVENT = 'TaskScratched'
UPDATED_EVENT = 'TaskUpdated'
DATE_FIELDS = ('DUE',)
COMPLETED_LOG = 'completed.md'
DONE_STATUS = 'DONE'
SCRATCHED_STATUS = 'SCRATCHED'
ANCESTRY_SEPARATOR = ' > '
# SCHEMA.md's own field grammar, in SCHEMA.md's order. `BUMPED` is
# retired; `ADDED` and `ID` are btodo extensions and so are not in it.
# Whatever btodo authors -- a `completed.md` record, a brand new task
# line -- is written in this order, which is what makes those lines
# canonical where hand-written ones keep whatever order they came with.
SCHEMA_FIELDS = ('P', 'LOE', 'DUE', 'REPEAT', 'TAGS')
LOE_VALUES = ('1', '2', '3', '5', '8')
# SCHEMA.md indents every level by two spaces.
SUBTASK_INDENT = 2
# The fields a top-level task owns. SCHEMA.md gives a subtask no `P` of
# its own, and only the root task is rescheduled, so a `[REPEAT:]` on a
# child never fires.
ROOT_ONLY_FIELDS = ('P', 'REPEAT')


class ListError(Exception):
    """No discovered list in the source directory carries that name.

    Raised rather than creating the file: `btodo add` writes to lists
    the user already keeps, and a typo that silently spawns `wrk.md`
    hides the task instead of filing it.
    """


def task_snapshot(task: TaskNode) -> dict[str, Any]:
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


def _is_checklist_item(task: TaskNode) -> bool:
    """A child carrying no fields: plain text, not an entity of its own.

    SCHEMA.md keeps these out of `completed.md`, and they must never be
    given an `[ID:]` -- carrying a field is exactly what distinguishes a
    subtask from a checklist item, so injecting one would silently
    promote the line.
    """
    return bool(task.indent) and not task.fields


def _stream_task(ancestry: list[TaskNode]) -> TaskNode:
    """The task whose event stream owns a mutation on `ancestry`'s target.

    Usually the target itself. A checklist item cannot hold an `[ID:]`,
    so its events are recorded against the nearest ancestor that can --
    at worst the top-level task, which never is one.
    """
    return next(
        task for task in reversed(ancestry) if not _is_checklist_item(task)
    )


def _block_indices(task: TaskNode) -> set[int]:
    """Every line the task owns: its own, its notes, its children's."""
    indices = {task.raw_index, *task.note_indices}
    for child in task.children:
        indices |= _block_indices(child)
    return indices


def _identify(task: TaskNode, ids: dict[int, str]) -> str:
    """The task's `[ID:]`, allocating one on first mediated mutation."""
    return ids.setdefault(task.raw_index, task.task_id or new_task_id())


# --- Creation -------------------------------------------------------


def _resolve_list(directory: Path, name: str) -> Path:
    """The discovered list whose filename stem is `name`.

    Parked lists count: parking opts a file out of *views*, not out of
    being written to.

    Raises
    ------
    ListError
        If no discovered list carries that stem.
    """
    lists = discover_lists(directory)
    found = next((path for path in lists if path.stem == name), None)
    if found is None:
        stems = ', '.join(path.stem for path in lists)
        raise ListError(
            f'no list named {name!r} in {directory}; available: {stems}'
        )
    return found


def _checked_values(fields: dict[str, str]) -> dict[str, str]:
    """The supplied fields, validated and normalised.

    Runs before anything is written, so a bad value costs nothing. Only
    the values with a grammar btodo actually depends on are checked --
    a `TAGS` string is free-form and cannot be wrong. `REPEAT` is left
    to `_checked_fields`, which has the day a schedule needs.
    """
    checked = dict(fields)
    priority = checked.get('P')
    if priority is not None and not priority.isdigit():
        raise ValueError(f'P must be a whole number, not {priority!r}')

    loe = checked.get('LOE')
    if loe is not None and loe not in LOE_VALUES:
        raise ValueError(
            f'LOE must be one of {", ".join(LOE_VALUES)}, not {loe!r}'
        )

    due = checked.get('DUE')
    if due is not None:
        parsed = parse_date(due)
        if parsed is None:
            raise ValueError(f'DUE must be an ISO date, not {due!r}')
        # Normalised, not passed through: `date.fromisoformat` accepts
        # more spellings on newer interpreters, and a line's meaning
        # must not depend on which one wrote it.
        checked['DUE'] = parsed.isoformat()
    return checked


def _checked_fields(fields: dict[str, str], today: date) -> dict[str, str]:
    """`_checked_values`, and a `REPEAT` the scheduler reads."""
    checked = _checked_values(fields)
    repeat = checked.get('REPEAT')
    if repeat is not None:
        # Validated by scheduling it and throwing the answer away: the
        # repeat parser is the only definition of a readable spec, and
        # an unreadable one must fail before a task carries it.
        next_due(repeat, today)
    return checked


def _added_payload(entry: str, written: dict[str, str]) -> dict[str, Any]:
    """The `TaskAdded` payload for a line btodo has just created."""
    return {
        'delta': {name: [None, value] for name, value in written.items()},
        # Post-state, unlike every other event here: an add has no
        # prior state for a snapshot to describe. Taken from the line
        # as written, so it records the file, not the intent.
        'snapshot': task_snapshot(parse(f'{OPEN_HEADING}\n{entry}').tasks[0]),
    }


def _refuse_checklist_item(task: TaskNode) -> None:
    """Reject a task that carries no field of its own.

    Raises
    ------
    ValueError
        If `task` is a checklist item. Any field written to one, an
        `[ID:]` included, promotes it to a subtask (SCHEMA.md).
    """
    if _is_checklist_item(task):
        raise ValueError(
            f'{task.title!r} is a checklist item: a field written to it '
            'would promote it to a subtask'
        )


def _refuse_root_fields(fields: dict[str, str]) -> None:
    """Reject the fields a child line must not carry.

    Raises
    ------
    ValueError
        If `fields` names one. Nothing reads such a field on a child,
        so writing it would read as a change that never happened.
    """
    for name in ROOT_ONLY_FIELDS:
        if name in fields:
            raise ValueError(
                f'{name} belongs to the top-level task, not to a subtask'
            )


def add_task(
    directory: Path,
    list_name: str,
    title: str,
    fields: dict[str, str],
    today: date,
) -> tuple[Path, str]:
    """Add a top-level task to `list_name`. Returns the path and line.

    The task is appended as the last entry of the list's `## Open`
    section; every other line is left exactly as it was. Only the fields
    the caller supplied are written -- an absent `P` means 0 to the
    parser, so inventing a default would silently rank the task.
    `[ADDED:]` and `[ID:]` are always stamped: rank is computed from the
    add date (ADR 0005), and a task btodo created has no reason to wait
    for the lazy id injection the hand-written ones get.

    Parameters
    ----------
    directory : Path
        The source directory: its lists and its journal.
    list_name : str
        A list's filename stem, e.g. `chores` for `chores.md`.
    title : str
        The task title, without fields.
    fields : dict
        SCHEMA.md field names to values, as strings. Any of `P`, `LOE`,
        `DUE`, `REPEAT`, `TAGS`; all optional.
    today : date
        The add date, in the user's local day.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the task line as written.

    Raises
    ------
    ListError
        If `list_name` names no discovered list.
    ValueError
        If a supplied `P`, `LOE` or `DUE` is unreadable. `RepeatError`,
        a ValueError, covers `REPEAT`. Raised before anything is
        written.
    """
    path = _resolve_list(directory, list_name)
    checked = _checked_fields(fields, today)
    written = {
        **{name: checked[name] for name in SCHEMA_FIELDS if name in checked},
        'ADDED': today.isoformat(),
        'ID': new_task_id(),
    }
    # Built by the same field-append path every other mutation uses, on
    # a line that starts out carrying none.
    entry = _set_fields(f'- [ ] {title}', written)

    doc = parse(path.read_text())
    doc.lines = append_open(doc.lines, entry)
    path.write_text(serialize(doc))

    Journal(directory).append(
        ADDED_EVENT,
        f'task/{written["ID"]}',
        _added_payload(entry, written),
        actor='agent',
        source_file=path.name,
    )
    return path, entry


def add_subtask(
    directory: Path,
    list_name: str,
    parent: str,
    title: str,
    fields: dict[str, str],
) -> tuple[Path, str]:
    """Add a subtask under `parent`. Returns the path and the line.

    The child lands last in its parent's block, one indent level
    deeper, and carries an `[ID:]` of its own. Indentation is the
    file's only statement of the relation; the `TaskAdded` payload
    names the parent by id. A parent carrying no `[ID:]` is stamped
    first, on an event of its own, so no line this writes goes
    unrecorded in a completed run.

    Parameters
    ----------
    directory : Path
        The source directory: its lists and its journal.
    list_name : str
        A list's filename stem, e.g. `chores` for `chores.md`.
    parent : str
        The parent task's `[ID:]` or part of its title. It must name a
        task in `list_name`.
    title : str
        The subtask title, without fields.
    fields : dict
        SCHEMA.md field names to values, as strings. Any of `LOE`,
        `DUE`, `TAGS`; all optional. No `[ADDED:]` is stamped: rank
        reads the add date, and only a top-level task is ranked.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the subtask line as written.

    Raises
    ------
    ListError
        If `list_name` names no discovered list.
    SelectionError
        If `parent` does not name exactly one open task.
    ValueError
        If a supplied value is unreadable, if `fields` carries a field
        the top-level task owns, or if `parent` names a checklist item
        or a task in another list. Raised before anything is written.
    """
    path = _resolve_list(directory, list_name)
    _refuse_root_fields(fields)
    # `REPEAT` is refused above, so no supplied value needs a day.
    checked = _checked_values(fields)

    record = TaskSelection(directory, parent).record
    if record.path != path:
        raise ValueError(
            f'{parent!r} names a task in {record.path.name}, not {path.name}'
        )

    task = record.task
    _refuse_checklist_item(task)
    stamped = task.task_id is None
    parent_id = task.task_id or new_task_id()
    written = {
        **{name: checked[name] for name in SCHEMA_FIELDS if name in checked},
        'ID': new_task_id(),
    }
    indent = ' ' * (task.indent + SUBTASK_INDENT)
    entry = _set_fields(f'{indent}- [ ] {title}', written)

    lines = list(record.doc.lines)
    if stamped:
        lines[task.raw_index] = set_field(task.raw, 'ID', parent_id)
    # After every line the parent owns -- its notes, its children and
    # theirs -- which makes the new child the last of them.
    lines.insert(max(_block_indices(task)) + 1, entry)
    record.doc.lines = lines
    path.write_text(serialize(record.doc))

    journal = Journal(directory)
    if stamped:
        journal.append(
            UPDATED_EVENT,
            f'task/{parent_id}',
            {
                'delta': {'ID': [None, parent_id]},
                'snapshot': task_snapshot(task),
            },
            actor='agent',
            source_file=path.name,
        )
    journal.append(
        ADDED_EVENT,
        f'task/{written["ID"]}',
        {**_added_payload(entry, written), 'parent': parent_id},
        actor='agent',
        source_file=path.name,
    )
    return path, entry


# --- Completion -----------------------------------------------------


def _completed_ancestries(record: TaskRecord) -> list[list[TaskNode]]:
    """Ancestries for the target and each ancestor it finishes.

    A task is complete when all its children are checked (SCHEMA.md), so
    checking the last open child completes the parent, and that may
    complete its parent in turn. Deepest first, which is the order the
    completions get logged.
    """
    ancestries = [record.ancestry]
    for depth in reversed(range(len(record.ancestry) - 1)):
        parent, child = (
            record.ancestry[depth],
            record.ancestry[depth + 1],
        )
        if not all(c.done or c is child for c in parent.children):
            break
        ancestries.append(record.ancestry[: depth + 1])
    return ancestries


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


def _format_ancestry(ancestry: list[TaskNode]) -> str:
    """The `Parent > Child` path SCHEMA.md logs a nested task under."""
    return ANCESTRY_SEPARATOR.join(task.title for task in ancestry)


def _log_entry(
    path: Path,
    ancestry: list[TaskNode],
    status: str,
    today: date,
) -> str:
    """One `completed.md` record: date, category, status, ancestry."""
    task = ancestry[-1]
    fields = ' '.join(
        f'[{name}:{task.fields[name]}]'
        for name in SCHEMA_FIELDS
        if name in task.fields
    )
    entry = (
        f'{today.isoformat()} | {path.stem} | {status} | '
        f'{_format_ancestry(ancestry)}'
    )
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
    record = TaskSelection(directory, selector).record
    ancestries = _completed_ancestries(record)
    root = record.ancestry[0]
    root_done = len(ancestries[-1]) == 1
    rescheduled = (
        next_due(root.repeat, today) if root_done and root.repeat else None
    )

    ids: dict[int, str] = {}
    streams = [
        _identify(_stream_task(ancestry), ids) for ancestry in ancestries
    ]
    lines = list(record.doc.lines)

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
        for ancestry in ancestries:
            index = ancestry[-1].raw_index
            lines[index] = _mark_done(lines[index])

    entries = [
        _log_entry(record.path, ancestry, DONE_STATUS, today)
        for ancestry in ancestries
        if not _is_checklist_item(ancestry[-1])
    ]

    record.doc.lines = lines
    record.path.write_text(serialize(record.doc))
    _append_log(directory, entries)

    journal = Journal(directory)
    for ancestry, stream in zip(ancestries, streams):
        task = ancestry[-1]
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
                'ancestry': _format_ancestry(ancestry),
            },
            actor='agent',
            source_file=record.path.name,
        )

    return entries


def scratch(directory: Path, selector: str, today: date) -> list[str]:
    """Drop the task `selector` names without completing it.

    The whole block goes -- the task, its notes, its children -- and
    nothing cascades: abandoning one child says nothing about its
    parent, which stays open.

    SCHEMA.md logs a scratch only for a task genuinely accepted in an
    earlier session, and silently drops proposals culled in the session
    that produced them. btodo cannot see that difference; by the time an
    item is written to a list it can only be treated as accepted, so
    every scratch is logged.

    Parameters
    ----------
    directory : Path
        The source directory: its lists, its `completed.md`, its
        journal.
    selector : str
        A task `[ID:]` or part of a title.
    today : date
        The date the task was abandoned, in the user's local day.

    Returns
    -------
    list of str
        The one `completed.md` entry written, or none for a checklist
        item, which SCHEMA.md does not log.

    Raises
    ------
    SelectionError
        If `selector` does not name exactly one open task.
    """
    record = TaskSelection(directory, selector).record
    task = record.task
    stream = _stream_task(record.ancestry)
    stream_id = stream.task_id or new_task_id()

    lines = list(record.doc.lines)
    if stream is not task:
        # A checklist item cannot hold an id, so the event belongs to
        # the ancestor's stream and the ancestor's line is the one that
        # has to carry it.
        lines[stream.raw_index] = set_field(
            lines[stream.raw_index],
            'ID',
            stream_id,
        )
    lines = _drop_lines(lines, _block_indices(task))

    entries = (
        []
        if _is_checklist_item(task)
        else [
            _log_entry(record.path, record.ancestry, SCRATCHED_STATUS, today)
        ]
    )

    record.doc.lines = lines
    record.path.write_text(serialize(record.doc))
    _append_log(directory, entries)

    Journal(directory).append(
        SCRATCHED_EVENT,
        f'task/{stream_id}',
        {
            'delta': {'removed': [False, True]},
            'snapshot': task_snapshot(task),
            'ancestry': _format_ancestry(record.ancestry),
        },
        actor='agent',
        source_file=record.path.name,
    )
    return entries


# --- Update ---------------------------------------------------------


def update_task(
    directory: Path,
    selector: str,
    fields: dict[str, str],
    today: date,
    title: str | None = None,
) -> tuple[Path, str]:
    """Rewrite the task `selector` names. Returns the path and line.

    Only the fields named are written; the rest of the line, and every
    other line in the file, is left exactly as it was. An `[ID:]` is
    stamped where the task has none, so the caller can address it by id
    from here on.

    Subtasks are reached at any depth, and the event then carries the
    `Parent > Child` ancestry. A checklist item is refused: writing a
    field to one promotes it to a subtask (SCHEMA.md).

    Parameters
    ----------
    directory : Path
        The source directory: its lists and its journal.
    selector : str
        A task `[ID:]` or part of a title.
    fields : dict
        SCHEMA.md field names to values, as strings.
    today : date
        The user's local day, which validates a `REPEAT`.
    title : str, optional
        A new title. The fields on the line keep their positions.

    Returns
    -------
    tuple of (Path, str)
        The list written to, and the task line as written.

    Raises
    ------
    SelectionError
        If `selector` does not name exactly one open task.
    ValueError
        If nothing was named to change, if the task is a checklist
        item, if `fields` carries a field the top-level task owns, or
        if a supplied value is unreadable. Raised before anything is
        written.
    """
    if not fields and title is None:
        raise ValueError('nothing to update: name a field or a title')
    checked = _checked_fields(fields, today)

    record = TaskSelection(directory, selector).record
    task = record.task
    nested = len(record.ancestry) > 1
    _refuse_checklist_item(task)
    if nested:
        _refuse_root_fields(fields)

    task_id = task.task_id or new_task_id()
    written = dict(checked)
    if not task.task_id:
        written['ID'] = task_id
    entry = _set_fields(task.raw, written)
    if title is not None:
        entry = set_title(entry, title)

    delta: dict[str, list[Any]] = {
        name: [task.fields.get(name), value] for name, value in written.items()
    }
    if title is not None:
        delta['title'] = [task.title, title]

    payload: dict[str, Any] = {
        'delta': delta,
        # Pre-state, as everywhere but an add: the delta says what
        # changed, the snapshot says what it changed from.
        'snapshot': task_snapshot(task),
    }
    if nested:
        # Only a child needs it. A top-level task's ancestry is its own
        # title, which the snapshot already carries.
        payload['ancestry'] = _format_ancestry(record.ancestry)

    record.doc.lines[task.raw_index] = entry
    record.path.write_text(serialize(record.doc))

    Journal(directory).append(
        UPDATED_EVENT,
        f'task/{task_id}',
        payload,
        actor='agent',
        source_file=record.path.name,
    )
    return record.path, entry


# --- Backfill -------------------------------------------------------


def _needs_added(task: TaskNode) -> bool:
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
