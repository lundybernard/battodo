"""Characterization tests for the view selection and its rendering.

Temporary scaffolding for the conversion of `battodo.view.selection` to
property objects. The suite pins the hour windows, the document a
selection publishes for a generated list file, and the table rendered
from that document. It is deleted when the conversion lands.

The behavioral goldens pin one rendered instant byte for byte, so this
suite covers what they cannot reach: every hour of a week, and list
files drawn from the schema grammar. The cases the hand-written suites
carry ride along as an explicit example.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from json import loads
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from hypothesis import example, given, settings
from hypothesis import strategies as st

from battodo.view.render import RULE, View
from battodo.view.selection import ALWAYS_ACTIVE, TOP_N, Selection

from ..property.strategies import document, grammar

# Wednesday mid-morning, the instant the durable suites pin: the work
# window is open and the chores window is shut.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
# The active set at NOW, in the order the document publishes it.
ACTIVE_AT_NOW = ['career', 'events', 'study', 'work']
HEADER_AT_NOW = (
    'Wednesday 2026-08-05 10:30 — active: career, events, study, work'
)
# The one list a generated source holds. `career` stays active at every
# hour, so a pin over generated input never depends on the clock.
CATEGORY = 'career'
# The width every rendered pin lays out in. The layout probes the
# terminal, which reads COLUMNS first.
WIDTH = '80'
# The windows the view opens, as a table: the category, the weekday
# numbers it opens on, and the hours it stays open on them.
WINDOWS = (
    ('work', range(5), range(9, 17)),
    ('chores', range(5), range(17, 21)),
    ('chores', range(5, 7), range(10, 20)),
)
# A Monday, so a weekday number added to it names that day.
WEEK_START = date(2026, 8, 3)
# A stand-in for a source directory. The active set is a fact about the
# clock, so the window cases read it without going near a file.
SOURCE = Path('a-source-dir')
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
# The cases the durable suites name, as one list file: an open task, a
# finished one, a recurrence ahead of today, a one-off ahead of today, a
# late recurrence, one due today, and a date the parser cannot read.
KNOWN_LINES = [
    '- [ ] An open task [P:2]',
    '- [x] A finished task [P:2]',
    '- [ ] A later recurrence [P:2] [DUE:2026-09-01] [REPEAT:7d]',
    '- [ ] A later one-off [P:2] [DUE:2026-09-01]',
    '- [ ] A late recurrence [P:2] [DUE:2026-08-04] [REPEAT:7d]',
    '- [ ] A recurrence due today [P:2] [DUE:2026-08-05] [REPEAT:7d]',
    '- [ ] A placeholder due date [P:2] [DUE:YYYY-MM-DD] [REPEAT:7d]',
]


def opens(day: int, hour: int) -> set[str]:
    """The categories the window table opens on `day` at `hour`."""
    names = set(ALWAYS_ACTIVE)
    for name, days, hours in WINDOWS:
        if day in days and hour in hours:
            names.add(name)
    return names


LIST_FILES = st.lists(grammar.task_lines, max_size=8)


@contextmanager
def source(lines: list[str]) -> Iterator[Path]:
    """A source directory holding `lines` as its one list file."""
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        path = directory / f'{CATEGORY}.md'
        path.write_text(document(lines), encoding='utf-8')
        yield directory


def titles(out: list[str]) -> list[str]:
    """The category title each heading line in `out` carries."""
    opener = f'{RULE * 2} '
    found = []
    for line in out:
        if line.startswith(opener):
            found.append(line[len(opener) :].rstrip(RULE).rstrip())
    return found


class SelectionTests(TestCase):
    """Characterization tests for battodo.view.selection.Selection."""

    maxDiff = None

    def test_active(t) -> None:
        for day in range(7):
            for hour in range(24):
                with t.subTest(day=day, hour=hour):
                    when = datetime.combine(
                        WEEK_START + timedelta(days=day),
                        time(hour),
                        timezone.utc,
                    )

                    ret = Selection(SOURCE, when, show_all=False).active

                    t.assertEqual(ret, opens(day, hour))

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_json(t, lines: list[str]) -> None:
        with source(lines) as directory:
            selection = Selection(directory, NOW, show_all=False)

            ret = loads(selection.json)

        t.assertEqual(list(ret), ['date', 'active', 'categories'])
        t.assertEqual(ret['date'], '2026-08-05')
        t.assertEqual(ret['active'], ACTIVE_AT_NOW)
        categories = ret['categories']
        t.assertEqual(
            [list(category) for category in categories],
            [['name', 'hidden', 'tasks']] * len(categories),
        )
        t.assertEqual(
            [category['name'] for category in categories],
            [CATEGORY] * len(categories),
        )
        for category in categories:
            shown = category['tasks']
            # A category with nothing open is left out altogether, and
            # one holding anything back is filled to the limit first.
            t.assertGreater(len(shown), 0)
            t.assertLessEqual(len(shown), TOP_N)
            if category['hidden']:
                t.assertEqual(len(shown), TOP_N)
            t.assertEqual(
                [list(task) for task in shown],
                [TASK_FIELDS] * len(shown),
            )
            ranks = [task['rank'] for task in shown]
            t.assertEqual(ranks, sorted(ranks, reverse=True))


class ViewTests(TestCase):
    """Characterization tests for battodo.view.render.View."""

    maxDiff = None

    @settings(deadline=None)
    @example(lines=KNOWN_LINES)
    @given(LIST_FILES)
    def test_text(t, lines: list[str]) -> None:
        with source(lines) as directory:
            selection = Selection(directory, NOW, show_all=False)
            categories = selection.categories

            with patch.dict(environ, {'COLUMNS': WIDTH}):
                ret = View(selection).text

        out = ret.split('\n')
        t.assertEqual(out[0], HEADER_AT_NOW)
        t.assertEqual(titles(out), [CATEGORY.capitalize()] * len(categories))
        # A table is a blank line, a heading, the column names, a line
        # per task shown, and one more where it holds any back.
        spent = sum(
            3 + len(category.shown) + bool(category.hidden)
            for category in categories
        )
        t.assertEqual(len(out), 1 + spent)
