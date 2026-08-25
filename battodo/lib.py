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

from batconf import Configuration

from .completed import DEFAULT_PERIOD, PERIODS, Digest, DigestView
from .view import TZ, Selection, View, item_count

__all__ = [
    'DEFAULT_PERIOD',
    'PERIODS',
    'TZ',
    'get_completed',
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
