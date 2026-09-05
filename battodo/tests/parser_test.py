from datetime import date
from unittest import TestCase

from ..parser import TaskNode, TodoDocument, parse_date

OPEN_DOC = """# Work

<!-- Active: Mon-Fri -->

## Open

<!-- Add items here. -->

- [ ] Alpha [P:95] [BUMPED:2026-08-08] [ADDED:2026-07-01] [LOE:8] [TAGS:a,b]
      A note line, six-space indented.
  - [ ] Sub one [LOE:3]
    - [ ] Checklist item
  - [ ] Plain checklist child

- [x] Beta [P:3] [DUE:2026-01-01] [REPEAT:14d]

## Done
"""

# Line indices into OPEN_DOC.
ALPHA_INDEX = 8
NOTE_INDEX = 9
BETA_INDEX = 14
APPEND_INDEX = 15
BETA = '- [x] Beta [P:3] [DUE:2026-01-01] [REPEAT:14d]'


class TaskNodeTests(TestCase):
    """Unit tests for battodo.parser.TaskNode."""

    def setUp(t) -> None:
        t.tk = TaskNode(
            raw_index=2,
            indent=0,
            done=False,
            title='A task',
            fields={'P': '2', 'LOE': '1'},
            raw='- [ ] A task [P:2] [LOE:1]',
            # Default: children=[],
            # Default: note_indices=[],
        )

    def test_loe(t) -> None:
        with t.subTest('an integer value reads as a number'):
            t.assertEqual(t.tk.loe, 1)

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            t.assertIsNone(t.tk.loe)

        with t.subTest('#51: a value that is not an integer raises'):
            t.tk.fields = {'LOE': '?'}
            with t.assertRaises(ValueError) as caught:
                _ = t.tk.loe
            t.assertEqual(
                str(caught.exception),
                "invalid literal for int() with base 10: '?'",
            )

    def test_due(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'DUE': '2026-01-01'}
            t.assertEqual(t.tk.due, '2026-01-01')

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            t.assertIsNone(t.tk.due)

    def test_added(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'ADDED': '2026-07-01'}
            t.assertEqual(t.tk.added, '2026-07-01')

        with t.subTest('a hand-written task carries none'):
            t.tk.fields = {}
            t.assertIsNone(t.tk.added)

    def test_repeat(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'REPEAT': '14d'}
            t.assertEqual(t.tk.repeat, '14d')

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            t.assertIsNone(t.tk.repeat)

    def test_task_id(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'ID': 'zz01ab'}
            t.assertEqual(t.tk.task_id, 'zz01ab')

        with t.subTest('a task btodo has never touched carries none'):
            t.tk.fields = {}
            t.assertIsNone(t.tk.task_id)

    def test_tags(t) -> None:
        with t.subTest('a comma-separated value splits'):
            t.tk.fields = {'TAGS': 'first,second'}
            t.assertEqual(t.tk.tags, ['first', 'second'])

        with t.subTest('an empty entry is dropped'):
            t.tk.fields = {'TAGS': 'first,,second,'}
            t.assertEqual(t.tk.tags, ['first', 'second'])

        with t.subTest('an absent field gives no tags'):
            t.tk.fields = {}
            t.assertEqual(t.tk.tags, [])

    def test_is_subtask(t) -> None:
        with t.subTest('a top-level task is not a subtask'):
            t.assertFalse(t.tk.is_subtask)

        with t.subTest('an indented task carrying a field is'):
            t.tk.indent = 2
            t.assertTrue(t.tk.is_subtask)

        with t.subTest('one carrying none is a checklist item'):
            t.tk.fields = {}
            t.assertFalse(t.tk.is_subtask)

    def test_raw_index(t) -> None:
        t.assertEqual(t.tk.raw_index, 2)

    def test_children(t) -> None:
        t.assertEqual(t.tk.children, [])

    def test_note_indices(t) -> None:
        t.assertEqual(t.tk.note_indices, [])


class ParseDateTests(TestCase):
    """Unit tests for battodo.parser.parse_date."""

    def test_parse_date(t) -> None:
        cases = {
            '2026-08-08': date(2026, 8, 8),
            'YYYY-MM-DD': None,
            'not a date': None,
            '': None,
            None: None,
        }
        for value, expected in cases.items():
            with t.subTest(str(value)):
                t.assertEqual(parse_date(value), expected)


class TodoDocumentTests(TestCase):
    """Unit tests for battodo.parser.TodoDocument."""

    maxDiff = None

    def setUp(t) -> None:
        t.td = TodoDocument(OPEN_DOC)

    def test_lines(t) -> None:
        with t.subTest('the source, split verbatim'):
            t.assertEqual(t.td.lines, OPEN_DOC.split('\n'))

        with t.subTest('addressed by the index a task carries'):
            t.assertEqual(t.td.lines[BETA_INDEX], BETA)

    def test_tasks(t) -> None:
        with t.subTest('the open section, top level in file order'):
            t.assertEqual(
                [task.title for task in t.td.tasks], ['Alpha', 'Beta']
            )

        with t.subTest('the check mark decides done'):
            t.assertEqual([task.done for task in t.td.tasks], [False, True])

        with t.subTest('fields parse off the line, and leave the title'):
            t.assertEqual(
                t.td.tasks[0].fields,
                {
                    'P': '95',
                    'BUMPED': '2026-08-08',
                    'ADDED': '2026-07-01',
                    'LOE': '8',
                    'TAGS': 'a,b',
                },
            )

        with t.subTest('a task addresses its own line'):
            t.assertEqual(t.td.tasks[0].raw_index, ALPHA_INDEX)
            t.assertEqual(t.td.tasks[0].raw, t.td.lines[ALPHA_INDEX])

        with t.subTest('children nest by indent, at any depth'):
            sub, checklist = t.td.tasks[0].children
            t.assertTrue(sub.is_subtask)
            t.assertFalse(checklist.is_subtask)
            t.assertEqual(
                [task.title for task in sub.children],
                ['Checklist item'],
            )

        with t.subTest('a note line is an index on its task, not a child'):
            t.assertEqual(t.td.tasks[0].note_indices, [NOTE_INDEX])

        with t.subTest('a section that is not Open yields no task'):
            outside = TodoDocument(
                '# H\n\n- [ ] Loose\n\n## Done\n\n- [ ] Shut\n'
            )
            t.assertEqual(outside.tasks, [])

    def test_text(t) -> None:
        with t.subTest('the source, byte for byte, until a method writes'):
            t.assertEqual(t.td.text, OPEN_DOC)

        with t.subTest('and the lines as they stand after one'):
            t.td.set_field(BETA_INDEX, 'ID', 'zz01ab')
            t.assertEqual(
                t.td.text,
                OPEN_DOC.replace(BETA, f'{BETA} [ID:zz01ab]'),
            )

    def test_set_field(t) -> None:
        bumped = BETA.replace('[P:3]', '[P:2]')

        with t.subTest('an existing field is replaced where it stands'):
            t.assertEqual(t.td.set_field(BETA_INDEX, 'P', '2'), bumped)

        with t.subTest('the edited line is stored, not only returned'):
            t.assertEqual(t.td.lines[BETA_INDEX], bumped)

        with t.subTest('an absent field is appended after the last'):
            t.assertEqual(
                t.td.set_field(BETA_INDEX, 'ID', 'zz01ab'),
                f'{bumped} [ID:zz01ab]',
            )

        with t.subTest('a trailing-whitespace line does not gain a gap'):
            spaced = TodoDocument('## Open\n- [ ] X [P:2]   \n')
            t.assertEqual(
                spaced.set_field(1, 'ID', 'zz01ab'),
                '- [ ] X [P:2] [ID:zz01ab]',
            )

    def test_set_title(t) -> None:
        renamed = BETA.replace('Beta', 'Gamma')

        with t.subTest('the title changes, every field keeps its place'):
            t.assertEqual(t.td.set_title(BETA_INDEX, 'Gamma'), renamed)

        with t.subTest('the edited line is stored, not only returned'):
            t.assertEqual(t.td.lines[BETA_INDEX], renamed)

        with t.subTest('a fieldless line is the title alone, indent kept'):
            bare = TodoDocument('## Open\n  - [ ] X\n')
            t.assertEqual(bare.set_title(1, 'Y'), '  - [ ] Y')

        with t.subTest('a line that is not a task is rejected'):
            with t.assertRaises(ValueError) as caught:
                t.td.set_title(NOTE_INDEX, 'Gamma')
            t.assertEqual(
                str(caught.exception),
                "not a task line: '      A note line, six-space indented.'",
            )

    def test_append_open(t) -> None:
        entry = '- [ ] New [P:1]'

        with t.subTest('the entry lands last in the open section'):
            t.assertEqual(t.td.append_open(entry), APPEND_INDEX)
            t.assertEqual(t.td.lines[APPEND_INDEX], entry)

        with t.subTest('every other line keeps its text and order'):
            expected = OPEN_DOC.split('\n')
            expected.insert(APPEND_INDEX, entry)
            t.assertEqual(t.td.lines, expected)

        with t.subTest('an empty section takes the entry under its heading'):
            empty = TodoDocument('# Work\n\n## Open\n\n## Done\n')
            t.assertEqual(empty.append_open(entry), 3)
            t.assertEqual(
                empty.lines,
                ['# Work', '', '## Open', entry, '', '## Done', ''],
            )

        with (
            t.subTest('a file with no open section raises'),
            t.assertRaises(StopIteration),
        ):
            TodoDocument('# Work\n\n## Done\n').append_open(entry)
