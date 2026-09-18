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
            ret = t.tk.loe
            t.assertEqual(ret, 1)

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            ret = t.tk.loe
            t.assertIsNone(ret)

        with t.subTest('a value that is not an integer reads as absent'):
            t.tk.fields = {'LOE': '?'}
            ret = t.tk.loe
            t.assertIsNone(ret)

    def test_due(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'DUE': '2026-01-01'}
            ret = t.tk.due
            t.assertEqual(ret, '2026-01-01')

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            ret = t.tk.due
            t.assertIsNone(ret)

    def test_added(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'ADDED': '2026-07-01'}
            ret = t.tk.added
            t.assertEqual(ret, '2026-07-01')

        with t.subTest('a hand-written task carries none'):
            t.tk.fields = {}
            ret = t.tk.added
            t.assertIsNone(ret)

    def test_repeat(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'REPEAT': '14d'}
            ret = t.tk.repeat
            t.assertEqual(ret, '14d')

        with t.subTest('an absent field reads as absent'):
            t.tk.fields = {}
            ret = t.tk.repeat
            t.assertIsNone(ret)

    def test_task_id(t) -> None:
        with t.subTest('the field reads back as it stands'):
            t.tk.fields = {'ID': 'zz01ab'}
            ret = t.tk.task_id
            t.assertEqual(ret, 'zz01ab')

        with t.subTest('a task btodo has never touched carries none'):
            t.tk.fields = {}
            ret = t.tk.task_id
            t.assertIsNone(ret)

    def test_tags(t) -> None:
        with t.subTest('a comma-separated value splits'):
            t.tk.fields = {'TAGS': 'first,second'}
            ret = t.tk.tags
            t.assertEqual(ret, ['first', 'second'])

        with t.subTest('an empty entry is dropped'):
            t.tk.fields = {'TAGS': 'first,,second,'}
            ret = t.tk.tags
            t.assertEqual(ret, ['first', 'second'])

        with t.subTest('an absent field gives no tags'):
            t.tk.fields = {}
            ret = t.tk.tags
            t.assertEqual(ret, [])

    def test_is_subtask(t) -> None:
        with t.subTest('a top-level task is not a subtask'):
            ret = t.tk.is_subtask
            t.assertFalse(ret)

        with t.subTest('an indented task carrying a field is'):
            t.tk.indent = 2
            ret = t.tk.is_subtask
            t.assertTrue(ret)

        with t.subTest('one carrying none is a checklist item'):
            t.tk.fields = {}
            ret = t.tk.is_subtask
            t.assertFalse(ret)

    def test_raw_index(t) -> None:
        ret = t.tk.raw_index
        t.assertEqual(ret, 2)

    def test_children(t) -> None:
        ret = t.tk.children
        t.assertEqual(ret, [])

    def test_note_indices(t) -> None:
        ret = t.tk.note_indices
        t.assertEqual(ret, [])


class ParseDateTests(TestCase):
    """Unit tests for battodo.parser.parse_date."""

    def test_date(t) -> None:
        ret = parse_date('2026-08-08')
        t.assertEqual(ret, date(2026, 8, 8))

    def test_unreadable(t) -> None:
        for value in ('YYYY-MM-DD', 'not a date', '', None):
            with t.subTest(str(value)):
                ret = parse_date(value)
                t.assertIsNone(ret)


class TodoDocumentTests(TestCase):
    """Unit tests for battodo.parser.TodoDocument."""

    maxDiff = None

    def setUp(t) -> None:
        t.td = TodoDocument(OPEN_DOC)

    def test_lines(t) -> None:
        ret = t.td.lines

        with t.subTest('the source, split verbatim'):
            t.assertEqual(ret, OPEN_DOC.split('\n'))

        with t.subTest('addressed by the index a task carries'):
            t.assertEqual(ret[BETA_INDEX], BETA)

    def test_tasks(t) -> None:
        ret = t.td.tasks

        with t.subTest('the open section, top level in file order'):
            titles = [task.title for task in ret]
            t.assertEqual(titles, ['Alpha', 'Beta'])

        with t.subTest('the check mark decides done'):
            flags = [task.done for task in ret]
            t.assertEqual(flags, [False, True])

        with t.subTest('fields parse off the line, and leave the title'):
            fields = ret[0].fields

            t.assertEqual(
                fields,
                {
                    'P': '95',
                    'BUMPED': '2026-08-08',
                    'ADDED': '2026-07-01',
                    'LOE': '8',
                    'TAGS': 'a,b',
                },
            )

        with t.subTest('a task addresses its own line'):
            t.assertEqual(ret[0].raw_index, ALPHA_INDEX)
            t.assertEqual(ret[0].raw, t.td.lines[ALPHA_INDEX])

        with t.subTest('children nest by indent, at any depth'):
            sub, checklist = ret[0].children
            titles = [task.title for task in sub.children]

            t.assertTrue(sub.is_subtask)
            t.assertFalse(checklist.is_subtask)
            t.assertEqual(titles, ['Checklist item'])

        with t.subTest('a note line is an index on its task, not a child'):
            t.assertEqual(ret[0].note_indices, [NOTE_INDEX])

        with t.subTest('a section that is not Open yields no task'):
            outside = TodoDocument(
                '# H\n\n- [ ] Loose\n\n## Done\n\n- [ ] Shut\n'
            )

            outside_tasks = outside.tasks

            t.assertEqual(outside_tasks, [])

    def test_text(t) -> None:
        with t.subTest('the source, byte for byte, until a method writes'):
            ret = t.td.text
            t.assertEqual(ret, OPEN_DOC)

        with t.subTest('and the lines as they stand after one'):
            t.td.set_field(BETA_INDEX, 'ID', 'zz01ab')

            ret = t.td.text

            t.assertEqual(
                ret,
                OPEN_DOC.replace(BETA, f'{BETA} [ID:zz01ab]'),
            )

    def test_set_field(t) -> None:
        bumped = BETA.replace('[P:3]', '[P:2]')

        with t.subTest('an existing field is replaced where it stands'):
            ret = t.td.set_field(BETA_INDEX, 'P', '2')
            t.assertEqual(ret, bumped)

        with t.subTest('the edited line is stored, not only returned'):
            t.assertEqual(t.td.lines[BETA_INDEX], bumped)

        with t.subTest('an absent field is appended after the last'):
            ret = t.td.set_field(BETA_INDEX, 'ID', 'zz01ab')
            t.assertEqual(ret, f'{bumped} [ID:zz01ab]')

        with t.subTest('a trailing-whitespace line does not gain a gap'):
            spaced = TodoDocument('## Open\n- [ ] X [P:2]   \n')
            ret = spaced.set_field(1, 'ID', 'zz01ab')
            t.assertEqual(ret, '- [ ] X [P:2] [ID:zz01ab]')

    def test_set_title(t) -> None:
        renamed = BETA.replace('Beta', 'Gamma')

        with t.subTest('the title changes, every field keeps its place'):
            ret = t.td.set_title(BETA_INDEX, 'Gamma')
            t.assertEqual(ret, renamed)

        with t.subTest('the edited line is stored, not only returned'):
            t.assertEqual(t.td.lines[BETA_INDEX], renamed)

        with t.subTest('a fieldless line is the title alone, indent kept'):
            bare = TodoDocument('## Open\n  - [ ] X\n')
            ret = bare.set_title(1, 'Y')
            t.assertEqual(ret, '  - [ ] Y')

        with t.subTest('a line that is not a task is rejected'):
            with t.assertRaises(ValueError) as caught:
                t.td.set_title(NOTE_INDEX, 'Gamma')

            t.assertEqual(
                str(caught.exception),
                "not a task line: '      A note line, six-space indented.'",
            )

    def test_append_open(t) -> None:
        entry = '- [ ] New [P:1]'
        expected = OPEN_DOC.split('\n')
        expected.insert(APPEND_INDEX, entry)

        ret = t.td.append_open(entry)

        with t.subTest('the entry lands last in the open section'):
            t.assertEqual(ret, APPEND_INDEX)
            t.assertEqual(t.td.lines[APPEND_INDEX], entry)

        with t.subTest('every other line keeps its text and order'):
            t.assertEqual(t.td.lines, expected)

        with t.subTest('an empty section takes the entry under its heading'):
            empty = TodoDocument('# Work\n\n## Open\n\n## Done\n')

            empty_ret = empty.append_open(entry)

            t.assertEqual(empty_ret, 3)
            t.assertEqual(
                empty.lines,
                ['# Work', '', '## Open', entry, '', '## Done', ''],
            )

        with t.subTest('a file with no open section raises'):
            headless = TodoDocument('# Work\n\n## Done\n')
            with t.assertRaises(StopIteration):
                headless.append_open(entry)
