"""Property tests for `battodo.view`, driven by Hypothesis.

Each case writes a generated list file, then asserts what the view
publishes about it. The suite is higher-order: it runs outside the
coverage and mutation gates.

Every expectation is derived from the clock or from the generated
input, never from the code under test, so the assertions state what the
output holds for any list file rather than what it happened to return.
The cases began as the selection slice's oracle and outlived it (R4).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from json import loads
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from unittest.mock import patch

from hypothesis import example, given, settings
from hypothesis import strategies as st

from battodo.view import RANK_PLACES, TOP_N, Selection, View

from .strategies import document, grammar

# Wednesday mid-morning: the work window is open and the chores window
# is shut.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
# The one list a generated source holds. A named category no hour shuts
# keeps a case independent of the clock.
CATEGORY = 'career'
# The width the layout probes, through the variable the terminal size
# reads first. Wide enough that the task column never reaches its
# floor, so no line has to overrun the width.
WIDTH = 80
# The mark a task line carries while it is open.
OPEN_MARK = '- [ ] '
# The character a table rules its headings with, as the renderer draws
# it. Held here so a case reads the table as a terminal would.
RULE = '─'
# The fields of one published task, in the order they are listed.
TASK_FIELDS = [
    'id',
    'title',
    'rank',
    'priority',
    'loe',
    'due',
    'added',
    'repeat',
    'tags',
    'subtasks',
]
# One list file covering the cases the hand-written suites name: an
# open task, a finished one, a recurrence ahead of today, a one-off
# ahead of today, a late recurrence, one due today, and a date the
# parser cannot read.
KNOWN_LINES = [
    '- [ ] An open task [P:2]',
    '- [x] A finished task [P:2]',
    '- [ ] A later recurrence [P:2] [DUE:2026-09-01] [REPEAT:7d]',
    '- [ ] A later one-off [P:2] [DUE:2026-09-01]',
    '- [ ] A late recurrence [P:2] [DUE:2026-08-04] [REPEAT:7d]',
    '- [ ] A recurrence due today [P:2] [DUE:2026-08-05] [REPEAT:7d]',
    '- [ ] A placeholder due date [P:2] [DUE:YYYY-MM-DD] [REPEAT:7d]',
]
# More open tasks than a category shows, so every case reaches the
# abridging path and the count of what it holds back.
ABRIDGED_LINES = [
    f'- [ ] Open task {number} [P:{number}]' for number in range(1, 8)
]

LIST_FILES = st.lists(grammar.task_lines, max_size=8)


def fuzz(test: Callable[..., None]) -> Callable[..., None]:
    """Run `test` on the two fixed list files, then on generated ones."""
    return settings(deadline=None)(
        example(lines=KNOWN_LINES)(
            example(lines=ABRIDGED_LINES)(given(LIST_FILES)(test))
        )
    )


def published(lines: list[str]) -> dict[str, Any]:
    """The document a view of the list file `lines` publishes."""
    with source(lines) as directory:
        return loads(Selection(directory, NOW, show_all=False).json)


@contextmanager
def source(lines: list[str]) -> Iterator[Path]:
    """A source directory holding `lines` as its one list file."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        path = directory / f'{CATEGORY}.md'
        path.write_text(document(lines), encoding='utf-8')
        yield directory


def shown_tasks(publication: dict[str, Any]) -> list[dict[str, Any]]:
    """Every task `publication` shows, across its categories."""
    return [
        task
        for category in publication['categories']
        for task in category['tasks']
    ]


def open_lines(lines: list[str]) -> int:
    """How many of `lines` are task lines left open, at any depth."""
    return len([line for line in lines if line.lstrip().startswith(OPEN_MARK)])


def headings(out: list[str]) -> list[str]:
    """The heading line each table in `out` opens with.

    Every other line of a table is indented, and the header leads the
    whole view, so a heading is the only line below it with text in the
    first column.
    """
    return [line for line in out[1:] if line and not line.startswith(' ')]


class SelectionTests(TestCase):
    """Property tests for battodo.view.Selection.json."""

    maxDiff = None

    @fuzz
    def test_document_shape(t, lines: list[str]) -> None:
        ret = published(lines)

        t.assertEqual(list(ret), ['date', 'active', 'categories'])
        t.assertEqual(ret['date'], NOW.date().isoformat())
        t.assertEqual(ret['active'], sorted(set(ret['active'])))

        categories = ret['categories']
        shown = shown_tasks(ret)

        t.assertEqual(
            [list(category) for category in categories],
            [['name', 'hidden', 'tasks']] * len(categories),
        )
        t.assertEqual(
            [category['name'] for category in categories],
            [CATEGORY] * len(categories),
        )
        t.assertEqual(
            [list(task) for task in shown],
            [TASK_FIELDS] * len(shown),
        )

    @fuzz
    def test_category_limits(t, lines: list[str]) -> None:
        ret = published(lines)

        categories = ret['categories']
        shown = shown_tasks(ret)
        hidden = sum(category['hidden'] for category in categories)

        # The case writes one list file, so a view of it publishes one
        # category at most. What that category holds is the whole
        # publication.
        t.assertLessEqual(len(categories), 1)
        # A category with nothing open is left out altogether, and one
        # holding anything back is filled to the limit first.
        t.assertEqual(bool(shown), bool(categories))
        t.assertEqual(len(shown), min(len(shown) + hidden, TOP_N))
        # A category accounts for no more than the case wrote open.
        t.assertLessEqual(len(shown) + hidden, open_lines(lines))

    @fuzz
    def test_task_rank(t, lines: list[str]) -> None:
        ret = published(lines)

        ranks = [task['rank'] for task in shown_tasks(ret)]

        t.assertEqual(ranks, sorted(ranks, reverse=True))
        t.assertEqual(ranks, [round(rank, RANK_PLACES) for rank in ranks])


class ViewTests(TestCase):
    """Property tests for battodo.view.View.text."""

    maxDiff = None

    @fuzz
    @patch.dict(environ, {'COLUMNS': str(WIDTH)})
    def test_text(t, lines: list[str]) -> None:
        with source(lines) as directory:
            selection = Selection(directory, NOW, show_all=False)
            publication = loads(selection.json)

            ret = View(selection).text

        out = ret.split('\n')
        active = ', '.join(publication['active'])
        t.assertEqual(
            out[0],
            f'{NOW:%A} {publication["date"]} {NOW:%H:%M} — active: {active}',
        )

        categories = publication['categories']

        t.assertEqual(
            [heading.strip(f'{RULE} ') for heading in headings(out)],
            [CATEGORY.capitalize()] * len(categories),
        )
        # A table is a blank line, a heading, the column names, a line
        # per task shown, and one more where it holds tasks back.
        spent = sum(
            3 + len(category['tasks']) + bool(category['hidden'])
            for category in categories
        )
        t.assertEqual(len(out), 1 + spent)
        t.assertEqual([line for line in out if len(line) > WIDTH], [])
