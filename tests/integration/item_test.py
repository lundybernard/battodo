"""Contract tests for the single-item read, against real files.

One test per public name, one subtest per code path. Inputs are real
directories that hold real todo lists. This layer asserts return
values; interaction checks stay in the isolation tests beside the code.
"""

from datetime import datetime
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.conf import TZ
from battodo.item import Item, ItemJsonView, ItemView
from battodo.task import Task

# Chosen so the rank comes out whole: the task is one month old and one
# week from due, so the rank is 4 x 1.0 for the due date x 2.0 for age.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)

WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [DUE:2026-08-12] [TAGS:yard,summer] \
[ADDED:2026-07-06] [ID:9o71lx]
      A description of the deck.
      Its second line.
  - [ ] Chip the brush [LOE:2]
  - [ ] Sweep
  - [x] Buy the lumber [LOE:1]
- [ ] Undated task [P:2]
- [ ] Soon task [P:1] [DUE:2026-08-09] [ADDED:2026-07-25]

## Done
"""

# A list whose one subtask repeats.
REPEATING_CHORES = (
    '## Open\n'
    '- [ ] A chore [P:2] [ID:ch01ab]\n'
    '  - [ ] A repeating step [DUE:2026-08-12] [REPEAT:7d] [ID:rs01ab]\n'
)

DECK_TEXT = """Deck rebuild
  list         work
  id           9o71lx
  rank         8.0
  P            4.0
  LOE          8
  DUE          2026-08-12
  TAGS         yard, summer
  ADDED        2026-07-06
  description  A description of the deck.
               Its second line.
  subtasks
    [ ] Chip the brush [LOE:2]
    [ ] Sweep
    [x] Buy the lumber [LOE:1]"""

UNDATED_TEXT = """Undated task
  list  work
  id    -
  rank  2.0
  P     2.0"""

# Ranked 1.952 on the day of NOW, which a view row shows as 2.0. The
# published rank, 1.95, would show as 1.9.
SOON_TEXT = """Soon task
  list   work
  id     -
  rank   2.0
  P      1.0
  DUE    2026-08-09
  ADDED  2026-07-25"""


class ItemJsonViewTests(TestCase):
    """Contract tests for battodo.item.ItemJsonView.json."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = source_dir(t)

    def test_json(t) -> None:
        with t.subTest('the item, its fields, and its children'):
            ret = ItemJsonView(read(t.source, '9o71lx')).json
            t.assertEqual(
                loads(ret),
                {
                    'list': 'work',
                    'id': '9o71lx',
                    'title': 'Deck rebuild',
                    'done': False,
                    'rank': 8.0,
                    'priority': 4.0,
                    'loe': 8,
                    'due': '2026-08-12',
                    'added': '2026-07-06',
                    'repeat': None,
                    'tags': ['yard', 'summer'],
                    'description': 'A description of the deck.\nIts second line.',
                    'subtasks': [
                        {
                            'id': None,
                            'title': 'Chip the brush',
                            'done': False,
                            'loe': 2,
                            'due': None,
                            'repeat': None,
                            'tags': [],
                            'description': None,
                            'subtasks': [],
                        },
                        {
                            'id': None,
                            'title': 'Sweep',
                            'done': False,
                            'loe': None,
                            'due': None,
                            'repeat': None,
                            'tags': [],
                            'description': None,
                            'subtasks': [],
                        },
                        {
                            'id': None,
                            'title': 'Buy the lumber',
                            'done': True,
                            'loe': 1,
                            'due': None,
                            'repeat': None,
                            'tags': [],
                            'description': None,
                            'subtasks': [],
                        },
                    ],
                },
            )

        with t.subTest('an absent field is null, not missing'):
            ret = ItemJsonView(read(t.source, 'Undated')).json
            t.assertEqual(
                loads(ret),
                {
                    'list': 'work',
                    'id': None,
                    'title': 'Undated task',
                    'done': False,
                    'rank': 2.0,
                    'priority': 2.0,
                    'loe': None,
                    'due': None,
                    'added': None,
                    'repeat': None,
                    'tags': [],
                    'description': None,
                    'subtasks': [],
                },
            )

        with t.subTest('a repeating subtask carries its repeat'):
            listed = t.source / 'chores.md'
            listed.write_text(REPEATING_CHORES, encoding='utf-8')

            ret = ItemJsonView(read(t.source, 'ch01ab')).json

            (subtask,) = loads(ret)['subtasks']
            t.assertEqual(subtask['repeat'], '7d')


class ItemViewTests(TestCase):
    """Contract tests for battodo.item.ItemView.text."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = source_dir(t)

    def test_text(t) -> None:
        with t.subTest('every stored field, the description, the children'):
            ret = ItemView(read(t.source, '9o71lx')).text
            t.assertEqual(ret, DECK_TEXT)

        with t.subTest('part of a title selects the same task'):
            ret = ItemView(read(t.source, 'deck')).text
            t.assertEqual(ret, DECK_TEXT)

        with t.subTest('absent fields and a childless task are left out'):
            ret = ItemView(read(t.source, 'Undated')).text
            t.assertEqual(ret, UNDATED_TEXT)

        with t.subTest('the rank reads as a view row shows it'):
            ret = ItemView(read(t.source, 'Soon')).text
            t.assertEqual(ret, SOON_TEXT)


def source_dir(t: TestCase) -> Path:
    """A source directory holding the list, removed when the test ends."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    source = Path(tmp.name)
    (source / 'work.md').write_text(WORK, encoding='utf-8')
    return source


def read(source: Path, selector: str) -> Item:
    """The item `selector` names in `source`, ranked on the day of NOW."""
    task = Task(
        source,
        selector,
        NOW.date(),
    )
    return Item(task)
