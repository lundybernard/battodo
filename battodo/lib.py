"""The functions a UI calls to do one whole job.

Each takes the resolved configuration, then the command inputs as
keyword arguments, and returns finished output, so a UI holds only its
own input and display. A keyword of None means that the input was not
given. A script imports the same functions.

Every code path a UI executes runs through this module. The names its
own input handling needs are re-exported here: the zone of the clock,
the periods, the formats, and the count check. Startup wiring stays
out: a UI reads its logging configuration from `logconf`.
"""

from datetime import datetime
from pathlib import Path

from batconf import Configuration

from .completed import (
    DEFAULT_PERIOD,
    PERIODS,
    Digest,
    DigestJsonView,
    DigestView,
)
from .conf import TZ
from .item import Item, ItemJsonView, ItemView
from .lists import item_count
from .mutate import (
    Addition,
    Annotation,
    Backfill,
    Completion,
    Scratch,
    SubtaskAddition,
    SuppliedAttributes,
    Update,
)
from .task import Task
from .view import Selection, SelectionJsonView, View

__all__ = [
    'DEFAULT_PERIOD',
    'FORMATS',
    'PERIODS',
    'TZ',
    'add_item',
    'annotate_item',
    'backfill_items',
    'complete_item',
    'get_completed',
    'get_item',
    'get_view',
    'item_count',
    'scratch_item',
    'update_item',
]

# The output forms a command that prints can take.
FORMATS = ('text', 'json')


def _source(conf: Configuration) -> Path:
    """The source directory the configuration names, `~` expanded."""
    return Path(conf.view.source_dir).expanduser()


def _is_json(conf: Configuration) -> bool:
    """Whether the configuration asks for the machine-readable form.

    Raises
    ------
    ValueError
        The configured format is not one of FORMATS.
    """
    form = conf.format
    if form not in FORMATS:
        raise ValueError(
            f'unknown format {form!r}; choose one of {", ".join(FORMATS)}'
        )
    return form == 'json'


def _supplied(fields: dict[str, str | None]) -> dict[str, str]:
    """The fields of `fields` that hold a value. None means not given."""
    return {
        name: value
        for name, value in fields.items()
            if value is not None
    }  # fmt: skip


def get_view(
    conf: Configuration,
    now: datetime,
    *,
    show_all: bool,
) -> str:
    """The view the configuration asks for.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `format` chooses the form.
    now : datetime
        The clock, which decides both the active set and every rank.
    show_all : bool
        Whether to show every item, whatever the time window and the
        item count.

    Returns
    -------
    str
        The rendered view, or the selection as JSON, without a
        trailing newline.

    Raises
    ------
    SourceError
        The source directory is missing, or holds no todo lists.
    ValueError
        The configured item count is not a whole number of one or more,
        or the configured format is not one of FORMATS.
    """
    selection = Selection.from_config(conf, now, show_all=show_all)
    if _is_json(conf):
        return SelectionJsonView(selection).json
    return View(selection).text


def get_completed(conf: Configuration, now: datetime, *, period: str) -> str:
    """The completed digest of `period`.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `format` chooses the form.
    now : datetime
        The clock, whose local day ends the period.
    period : str
        One of PERIODS.

    Returns
    -------
    str
        The rendered digest, or the digest as JSON, without a trailing
        newline.

    Raises
    ------
    CompletedError
        The source directory holds no completed log.
    ValueError
        `period` has no definition, or the configured format is not
        one of FORMATS.
    """
    digest = Digest.from_config(conf, now, period=period)
    if _is_json(conf):
        return DigestJsonView(digest).json
    return DigestView(digest).text


def get_item(conf: Configuration, now: datetime, *, selector: str) -> str:
    """The one item `selector` names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `format` chooses the form.
    now : datetime
        The clock, whose local day decides the rank.
    selector : str
        Names the item.

    Returns
    -------
    str
        The rendered item, or the item as JSON, without a trailing
        newline.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    ValueError
        The configured format is not one of FORMATS.
    """
    item = Item.from_config(conf, now, selector=selector)
    if _is_json(conf):
        return ItemJsonView(item).json
    return ItemView(item).text


def add_item(
    conf: Configuration,
    now: datetime,
    *,
    list_name: str,
    title: str,
    parent: str | None = None,
    priority: str | None = None,
    loe: str | None = None,
    due: str | None = None,
    repeat: str | None = None,
    tags: str | None = None,
    description: str | None = None,
    attrs: str | None = None,
    note: str | None = None,
) -> str:
    """Write the task the inputs describe.

    Only the field inputs that are not None are written.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day is the add date. A subtask carries
        no add date, so none is written for one.
    list_name : str
        The list that receives the task.
    title : str
        The title of the task.
    parent : str or None
        A selector. The task becomes a subtask of the task it names.
    priority, loe, due, repeat, tags : str or None
        The values of the `P`, `LOE`, `DUE`, `REPEAT` and `TAGS`
        fields.
    description : str or None
        The description of the task, one description line per line.
    attrs : str or None
        The attributes of the add, as `key=value` segments.
    note : str or None
        A note, which enters the attributes under the key `note`.

    Returns
    -------
    str
        The written entry and the file that holds it, one per line.

    Raises
    ------
    ListError
        `list_name` names no list.
    SelectionError
        The parent does not name exactly one open task.
    ValueError
        The attributes do not read, a supplied field is unreadable, the
        title holds a line break, a description line is refused, or the
        parent cannot hold a subtask. Raised before anything is written.
    """
    checked = SuppliedAttributes(attrs, note).checked
    source = _source(conf)
    fields = _supplied(
        {
            'P': priority,
            'LOE': loe,
            'DUE': due,
            'REPEAT': repeat,
            'TAGS': tags,
        }
    )
    addition: Addition | SubtaskAddition
    if parent is None:
        addition = Addition(
            source,
            list_name,
            title,
            fields,
            now.date(),
            description=description,
            attrs=checked,
        )
    else:
        addition = SubtaskAddition(
            Task(source, parent, now.date()),
            list_name,
            title,
            fields,
            description=description,
            attrs=checked,
        )
    addition.write()
    return f'{addition.entry}\n{addition.path}'


def update_item(
    conf: Configuration,
    now: datetime,
    *,
    selector: str,
    title: str | None = None,
    priority: str | None = None,
    due: str | None = None,
    tags: str | None = None,
    description: str | None = None,
    attrs: str | None = None,
    note: str | None = None,
) -> str:
    """Rewrite the task `selector` names.

    Only the inputs that are not None are written. An update writes
    no `LOE` and no `REPEAT`: R3 names neither, and a changed `REPEAT`
    reschedules the task on its next completion, which is a decision
    of its own.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day validates a `REPEAT`.
    selector : str
        Names the task.
    title : str or None
        The new title.
    priority, due, tags : str or None
        The new values of the `P`, `DUE` and `TAGS` fields.
    description : str or None
        The new description, one description line per line. An empty
        one clears the description.
    attrs : str or None
        The attributes of the update, as `key=value` segments.
    note : str or None
        A note, which enters the attributes under the key `note`.

    Returns
    -------
    str
        The written entry and the file that holds it, one per line.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    ValueError
        The attributes do not read, nothing was named to change, the
        task cannot carry a field, a supplied value is unreadable, the
        title holds a line break, or a description line is refused.
        Raised before anything is written.
    """
    checked = SuppliedAttributes(attrs, note).checked
    update = Update(
        Task(_source(conf), selector, now.date()),
        _supplied({'P': priority, 'DUE': due, 'TAGS': tags}),
        title=title,
        description=description,
        attrs=checked,
    )
    update.write()
    return f'{update.entry}\n{update.path}'


def complete_item(
    conf: Configuration,
    now: datetime,
    *,
    selector: str,
    date: str | None = None,
    attrs: str | None = None,
    note: str | None = None,
) -> str:
    """Complete the task `selector` names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day stamps the log when `date` is None.
    selector : str
        Names the task.
    date : str or None
        The ISO day the task was completed.
    attrs : str or None
        The attributes of the completion, as `key=value` segments.
    note : str or None
        A note, which enters the attributes under the key `note`.

    Returns
    -------
    str
        The logged entries, one per line. A checklist item is checked
        off without a log entry, and says so instead.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    RepeatError
        A completed recurring task carries a `[REPEAT:]` btodo cannot
        read. Raised before anything is written.
    ValueError
        The attributes do not read, a checklist item is given
        attributes, or `date` is not an ISO date. Raised before
        anything is written.
    """
    checked = SuppliedAttributes(attrs, note).checked
    task = Task.from_config(conf, now, selector=selector, date=date)
    completion = Completion(task, attrs=checked)
    completion.write()
    entries = completion.entries
    return '\n'.join(entries) if entries else 'checked off'


def scratch_item(
    conf: Configuration,
    now: datetime,
    *,
    selector: str,
    attrs: str | None = None,
    note: str | None = None,
) -> str:
    """Drop the task `selector` names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day stamps the log.
    selector : str
        Names the task.
    attrs : str or None
        The attributes of the scratch, as `key=value` segments.
    note : str or None
        A note, which enters the attributes under the key `note`.

    Returns
    -------
    str
        The logged entries, one per line. A checklist item is dropped
        without a log entry, and says so instead.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    ValueError
        The attributes do not read, or a checklist item is given
        attributes. Raised before anything is written.
    """
    checked = SuppliedAttributes(attrs, note).checked
    task = Task(_source(conf), selector, now.date())
    scratch = Scratch(task, attrs=checked)
    scratch.write()
    entries = scratch.entries
    return '\n'.join(entries) if entries else 'dropped'


def annotate_item(
    conf: Configuration,
    now: datetime,
    *,
    selector: str,
    text: str | None = None,
    attrs: str | None = None,
) -> str:
    """Note the task `selector` names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day the task is read under.
    selector : str
        Names the task.
    text : str or None
        The note, which enters the attributes under the key `note`.
    attrs : str or None
        The attributes of the note, as `key=value` segments.

    Returns
    -------
    str
        The task line as written and the file that holds it, one per
        line.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    ValueError
        The attributes do not read, the note carries nothing, or the
        task is a checklist item. Raised before anything is written.
    """
    checked = SuppliedAttributes(attrs, text).checked
    task = Task(_source(conf), selector, now.date())
    annotation = Annotation(task, checked)
    annotation.write()
    return f'{annotation.entry}\n{annotation.path}'


def backfill_items(conf: Configuration, now: datetime) -> str:
    """Stamp an add date on every task in the source that lacks one.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. Only the source directory is read.
    now : datetime
        The clock, whose local day is stamped.

    Returns
    -------
    str
        A count for each list that changed, one per line, by list
        name. A run that stamped nothing says so instead.
    """
    backfill = Backfill(_source(conf), now.date())
    backfill.write()
    stamped = backfill.lists
    if not stamped:
        return 'nothing to backfill'
    return '\n'.join(
        f'{listed.path.name}: stamped {len(listed.tasks)}'
        for listed in stamped
    )
