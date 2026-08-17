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

from battodo.item import build_item, build_item_json
from battodo.view import TZ

# Chosen so the rank comes out whole: the task is one month old and one
# week from due, so urgency is 1 + 1.0 + 0.5 and the rank is 4 x 2.5.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=TZ)

WORK = """# Work

## Open

- [ ] Deck rebuild [P:4] [LOE:8] [DUE:2026-08-12] [TAGS:yard,summer] \
[ADDED:2026-07-06] [ID:9o71lx]
      A note, which the read does not publish.
  - [ ] Chip the brush [LOE:2]
  - [ ] Sweep
  - [x] Buy the lumber [LOE:1]
- [ ] Undated task [P:2]

## Done
"""

DECK_TEXT = """Deck rebuild
  list   work
  id     9o71lx
  rank   10.0
  P      4.0
  LOE    8
  DUE    2026-08-12
  TAGS   yard, summer
  ADDED  2026-07-06
  subtasks
    [ ] Chip the brush [LOE:2]
    [ ] Sweep
    [x] Buy the lumber [LOE:1]"""

UNDATED_TEXT = """Undated task
  list  work
  id    -
  rank  2.0
  P     2.0"""


class ItemReadTests(TestCase):
    maxDiff = None

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        (t.source / 'work.md').write_text(WORK, encoding='utf-8')

    def test_build_item(t) -> None:
        with t.subTest('every stored field, then the children'):
            t.assertEqual(build_item(t.source, '9o71lx', NOW), DECK_TEXT)

        with t.subTest('part of a title selects the same task'):
            t.assertEqual(build_item(t.source, 'deck', NOW), DECK_TEXT)

        with t.subTest('absent fields and a childless task are left out'):
            t.assertEqual(build_item(t.source, 'Undated', NOW), UNDATED_TEXT)

    def test_build_item_json(t) -> None:
        with t.subTest('the item, its fields, and its children'):
            t.assertEqual(
                loads(build_item_json(t.source, '9o71lx', NOW)),
                {
                    'list': 'work',
                    'id': '9o71lx',
                    'title': 'Deck rebuild',
                    'done': False,
                    'rank': 10.0,
                    'priority': 4.0,
                    'loe': 8,
                    'due': '2026-08-12',
                    'added': '2026-07-06',
                    'repeat': None,
                    'tags': ['yard', 'summer'],
                    'subtasks': [
                        {
                            'id': None,
                            'title': 'Chip the brush',
                            'done': False,
                            'loe': 2,
                            'due': None,
                            'tags': [],
                            'subtasks': [],
                        },
                        {
                            'id': None,
                            'title': 'Sweep',
                            'done': False,
                            'loe': None,
                            'due': None,
                            'tags': [],
                            'subtasks': [],
                        },
                        {
                            'id': None,
                            'title': 'Buy the lumber',
                            'done': True,
                            'loe': 1,
                            'due': None,
                            'tags': [],
                            'subtasks': [],
                        },
                    ],
                },
            )

        with t.subTest('an absent field is null, not missing'):
            data = loads(build_item_json(t.source, 'Undated', NOW))
            t.assertIsNone(data['id'])
            t.assertIsNone(data['due'])
            t.assertEqual(data['subtasks'], [])
