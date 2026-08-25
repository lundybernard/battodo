"""The functions a UI calls to do one whole job.

Each takes the resolved configuration and returns finished output, so
a UI holds only its own input and display. A script imports the same
functions.

Every code path a UI executes runs through this module. The names its
own input handling needs are re-exported here: the zone of the clock,
the periods, and the count check. Startup wiring stays out: a UI reads
its logging configuration from `logconf`.

The interface is provisional: what a function takes, a configuration
or plain arguments, is not settled.
"""

from datetime import datetime
from pathlib import Path

from batconf import Configuration

from .completed import DEFAULT_PERIOD, PERIODS, Digest, DigestView
from .item import build_item, build_item_json
from .mutate import add_subtask, add_task, complete, update_task
from .view import TZ, Selection, View, item_count

__all__ = [
    'DEFAULT_PERIOD',
    'PERIODS',
    'TZ',
    'add_item',
    'complete_item',
    'get_completed',
    'get_item',
    'get_view',
    'item_count',
    'update_item',
]

# The SCHEMA.md fields an add can write, by the option that supplies
# each. Every one is optional.
ADD_FIELDS = {
    'P': 'priority',
    'LOE': 'loe',
    'DUE': 'due',
    'REPEAT': 'repeat',
    'TAGS': 'tags',
}
# The subset an update writes. `LOE` and `REPEAT` are left out: R3
# names neither, and a changed `REPEAT` reschedules the task on its
# next completion, which is a decision of its own.
UPDATE_FIELDS = {'P': 'priority', 'DUE': 'due', 'TAGS': 'tags'}


def _source(conf: Configuration) -> Path:
    """The source directory the configuration names, `~` expanded."""
    return Path(conf.view.source_dir).expanduser()


def _fields(conf: Configuration, options: dict[str, str]) -> dict[str, str]:
    """The fields `options` names and the configuration carries.

    An option the user left off is absent from the Configuration
    rather than None, so only the supplied ones are passed on.
    """
    return {
        name: value
        for name, option in options.items()
        if (value := getattr(conf, option, None)) is not None
    }


def get_view(conf: Configuration, now: datetime) -> str:
    """The view the configuration asks for.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `format` chooses the form.
    now : datetime
        The clock, which decides both the active set and every rank.

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
        The configured item count is not a whole number of one or more.
    """
    selection = Selection.from_config(conf, now)
    if getattr(conf, 'format', 'text') == 'json':
        return selection.json
    return View(selection).text


def get_completed(conf: Configuration, now: datetime) -> str:
    """The completed digest the configuration asks for.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `format` chooses the form.
    now : datetime
        The clock, whose local day ends the period.

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
        The configured period has no definition.
    """
    digest = Digest.from_config(conf, now)
    if getattr(conf, 'format', 'text') == 'json':
        return digest.json
    return DigestView(digest).text


def get_item(conf: Configuration, now: datetime) -> str:
    """The one item the configuration names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `selector` names the item and
        `format` chooses the form.
    now : datetime
        The clock, whose local day decides the rank.

    Returns
    -------
    str
        The rendered item, or the item as JSON, without a trailing
        newline.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    """
    build = (
        build_item_json
        if getattr(conf, 'format', 'text') == 'json'
        else build_item
    )
    return build(_source(conf), conf.selector, now)


def add_item(conf: Configuration, now: datetime) -> str:
    """Write the task the configuration describes.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `list` and `title` name the task,
        and `parent` makes it a subtask of the task named there. Each
        ADD_FIELDS option the user supplied is written.
    now : datetime
        The clock, whose local day is the add date. A subtask carries
        no add date, so none is derived for one.

    Returns
    -------
    str
        The written entry and the file that holds it, one per line.

    Raises
    ------
    ListError
        The configured list does not exist.
    SelectionError
        The parent does not name exactly one open task.
    ValueError
        A supplied field is unreadable, or the parent cannot hold a
        subtask. Raised before anything is written.
    """
    source = _source(conf)
    fields = _fields(conf, ADD_FIELDS)
    parent = getattr(conf, 'parent', None)
    if parent is None:
        path, entry = add_task(
            source, conf.list, conf.title, fields, now.date()
        )
    else:
        path, entry = add_subtask(
            source, conf.list, parent, conf.title, fields
        )
    return f'{entry}\n{path}'


def update_item(conf: Configuration, now: datetime) -> str:
    """Rewrite the task the configuration names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `selector` names the task, `title`
        renames it, and each UPDATE_FIELDS option the user supplied is
        written.
    now : datetime
        The clock, whose local day validates a `REPEAT`.

    Returns
    -------
    str
        The written entry and the file that holds it, one per line.

    Raises
    ------
    SelectionError
        The selector does not name exactly one open task.
    ValueError
        Nothing was named to change, the task cannot carry a field, or
        a supplied value is unreadable. Raised before anything is
        written.
    """
    path, entry = update_task(
        _source(conf),
        conf.selector,
        _fields(conf, UPDATE_FIELDS),
        now.date(),
        title=getattr(conf, 'title', None),
    )
    return f'{entry}\n{path}'


def complete_item(conf: Configuration, now: datetime) -> str:
    """Complete the task the configuration names.

    Parameters
    ----------
    conf : Configuration
        The resolved configuration. `selector` names the task.
    now : datetime
        The clock, whose local day stamps the log.

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
    """
    entries = complete(_source(conf), conf.selector, now.date())
    return '\n'.join(entries) if entries else 'checked off'
