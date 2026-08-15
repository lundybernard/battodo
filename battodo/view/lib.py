"""The two forms a view takes, as plain functions.

These are what a consumer calls -- the CLI, a script, anything else.
They compose a selection with its table rendering, or serialize it
directly, and hand back the finished text, so no caller has to know
the classes underneath.
"""

from datetime import datetime
from pathlib import Path

from .render import View
from .selection import TOP_N, Selection


def build_view(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int = TOP_N,
    width: int = 0,
) -> str:
    """Render the tables for every category `directory` shows now.

    Parameters
    ----------
    directory : Path
        The source directory, `~` unexpanded.
    now : datetime
        The clock, which decides both the active set and every rank.
    show_all : bool
        Keep every task rather than the top `top_n` per category.
    top_n : int, optional
        How many tasks survive per category when `show_all` is false.
    width : int, optional
        Terminal width to lay the columns out in; 0 probes the terminal
        (80 columns when there is none, e.g. a pipe).

    Returns
    -------
    str
        The rendered view, without a trailing newline.

    Raises
    ------
    SourceError
        The directory is missing, or holds no todo lists.
    """
    selection = Selection(directory, now, show_all=show_all, top_n=top_n)
    return View(selection, width).text


def build_json(
    directory: Path,
    now: datetime,
    *,
    show_all: bool,
    top_n: int = TOP_N,
) -> str:
    """Serialize the same selection `build_view` renders.

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
        A JSON document; see `Selection.data` for its shape.

    Raises
    ------
    SourceError
        The directory is missing, or holds no todo lists.
    """
    selection = Selection(directory, now, show_all=show_all, top_n=top_n)
    return selection.json
