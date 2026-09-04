"""The todo lists of a source directory: which files, and how they show.

A file is a todo list if it holds an `## Open` heading (ADR 0004).
Every reader of a source directory finds its lists here.
"""

from pathlib import Path

from .parser import OPEN_HEADING

CATEGORY_ORDER = ['work', 'chores', 'study', 'career', 'events']
# What a rejected item count reports, wherever it was configured.
COUNT_ERROR = 'the item count must be a whole number of 1 or more'


def discover_lists(directory: Path) -> list[Path]:
    """Every markdown file in `directory` that is a todo list.

    The predicate is the presence of a `## Open` heading, so an ad-hoc
    list such as backlog.md is found, while SCHEMA.md, CLAUDE.md and
    the differently-formatted completed.md are not.

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


def category_order(name: str) -> tuple[int, str]:
    """Where a category sorts among the others.

    The named categories lead, in their own order; everything else
    follows alphabetically, which is the only order an ad-hoc list can
    be given.
    """
    known = name in CATEGORY_ORDER
    return (
        CATEGORY_ORDER.index(name) if known else len(CATEGORY_ORDER),
        name,
    )


def item_count(value: str) -> int:
    """Decode a count of items, from whichever source configured it.

    Raises
    ------
    ValueError
        The value is not a whole number of one or more.
    """
    count = int(value) if value.isdecimal() else 0
    if count < 1:
        raise ValueError(f'{COUNT_ERROR}: {value}')
    return count
