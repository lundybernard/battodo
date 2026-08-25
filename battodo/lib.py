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
from .view import TZ, Selection, View, item_count

__all__ = [
    'DEFAULT_PERIOD',
    'PERIODS',
    'TZ',
    'get_completed',
    'get_item',
    'get_view',
    'item_count',
]


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
    return build(Path(conf.view.source_dir).expanduser(), conf.selector, now)
