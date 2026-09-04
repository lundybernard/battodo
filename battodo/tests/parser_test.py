from datetime import date
from unittest import TestCase

from ..parser import (
    TaskNode,
    TodoDocument,
    append_open,
    parse,
    parse_date,
    serialize,
    set_field,
    set_title,
)

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


class ParseTests(TestCase):
    """Unit tests for battodo.parser.parse."""

    def setUp(t) -> None:
        t.doc = parse(OPEN_DOC)

    def test_tasks(t) -> None:
        with t.subTest('top-level only'):
            t.assertEqual(len(t.doc.tasks), 2)
            t.assertEqual(
                [task.title for task in t.doc.tasks],
                ['Alpha', 'Beta'],
            )

        with t.subTest('done flag'):
            t.assertFalse(t.doc.tasks[0].done)
            t.assertTrue(t.doc.tasks[1].done)

        with t.subTest('fields parsed'):
            alpha = t.doc.tasks[0]
            t.assertEqual(alpha.loe, 8)
            t.assertIsNone(alpha.due)
            t.assertEqual(alpha.added, '2026-07-01')

        with t.subTest('retired BUMPED still parses, so titles stay clean'):
            # Nothing reads it since ADR 0005, but the live files are
            # full of it and it must not leak into the title.
            t.assertEqual(alpha.fields['BUMPED'], '2026-08-08')
            t.assertEqual(alpha.title, 'Alpha')
            t.assertEqual(alpha.tags, ['a', 'b'])
            t.assertIsNone(alpha.task_id)

        with t.subTest('added is absent on hand-written tasks'):
            doc = parse('## Open\n\n- [ ] Bare\n')
            t.assertIsNone(doc.tasks[0].added)

        with t.subTest('due and repeat'):
            beta = t.doc.tasks[1]
            t.assertEqual(beta.due, '2026-01-01')
            t.assertEqual(beta.repeat, '14d')

        with t.subTest('a task with no fields has no tags'):
            doc = parse('## Open\n\n- [ ] Bare\n')
            t.assertEqual(doc.tasks[0].tags, [])

        with t.subTest('id field'):
            doc = parse('## Open\n\n- [ ] Tagged [ID:abc123]\n')
            t.assertEqual(doc.tasks[0].task_id, 'abc123')
            t.assertEqual(doc.tasks[0].title, 'Tagged')

        with t.subTest('outside Open section ignored'):
            doc = parse('# H\n\n- [ ] Not in open\n\n## Done\n\n- [ ] Nope\n')
            t.assertEqual(doc.tasks, [])

    def test_children(t) -> None:
        alpha = t.doc.tasks[0]

        with t.subTest('subtask vs checklist'):
            t.assertEqual(len(alpha.children), 2)
            sub, checklist = alpha.children
            t.assertEqual(sub.title, 'Sub one')
            t.assertTrue(sub.is_subtask)
            t.assertEqual(checklist.title, 'Plain checklist child')
            t.assertFalse(checklist.is_subtask)

        with t.subTest('nesting is recursive'):
            sub = alpha.children[0]
            t.assertEqual(len(sub.children), 1)
            t.assertEqual(sub.children[0].title, 'Checklist item')

        with t.subTest('notes are not children'):
            # the six-space note line attaches to Alpha, not as a subtask
            t.assertEqual(len(alpha.note_indices), 1)
            note = t.doc.lines[alpha.note_indices[0]]
            t.assertEqual(note.strip(), 'A note line, six-space indented.')

        with t.subTest('a done task has no children here'):
            t.assertEqual(t.doc.tasks[1].children, [])

    def test_lines(t) -> None:
        t.assertEqual(t.doc.lines, OPEN_DOC.split('\n'))


class SerializeTests(TestCase):
    """Unit tests for battodo.parser.serialize."""

    def test_serialize(t) -> None:
        cases = {
            'full document': OPEN_DOC,
            'no trailing newline': '## Open\n\n- [ ] X [P:1]',
            'empty': '',
            'crlf-free blank lines': '## Open\n\n\n\n',
            'trailing whitespace': '## Open\n- [ ] X [P:1]   \n',
            'no open section': '# Title\n\nprose\n',
        }
        for name, text in cases.items():
            with t.subTest(name):
                t.assertEqual(serialize(parse(text)), text)


class SetFieldTests(TestCase):
    """Unit tests for battodo.parser.set_field."""

    def test_set_field(t) -> None:
        raw = '- [ ] X [P:2] [LOE:1]'

        with t.subTest('existing field replaced in place'):
            t.assertEqual(set_field(raw, 'P', '3'), '- [ ] X [P:3] [LOE:1]')

        with t.subTest('other fields keep their position'):
            t.assertEqual(set_field(raw, 'LOE', '5'), '- [ ] X [P:2] [LOE:5]')

        with t.subTest('absent field appended at the end'):
            t.assertEqual(
                set_field(raw, 'ID', 'zz01ab'),
                '- [ ] X [P:2] [LOE:1] [ID:zz01ab]',
            )

        with t.subTest('edits chain onto an already-edited line'):
            t.assertEqual(
                set_field(set_field(raw, 'DUE', '2026-08-23'), 'ID', 'zz01ab'),
                '- [ ] X [P:2] [LOE:1] [DUE:2026-08-23] [ID:zz01ab]',
            )

        with t.subTest('a trailing-whitespace line does not gain a gap'):
            t.assertEqual(
                set_field('- [ ] X [P:2]   ', 'ID', 'zz01ab'),
                '- [ ] X [P:2] [ID:zz01ab]',
            )


class SetTitleTests(TestCase):
    """Unit tests for battodo.parser.set_title."""

    def test_set_title(t) -> None:
        with t.subTest('the title changes, every field keeps its place'):
            t.assertEqual(
                set_title('- [ ] X [P:2] [LOE:1]', 'Y'),
                '- [ ] Y [P:2] [LOE:1]',
            )

        with t.subTest('a fieldless line is the title alone'):
            t.assertEqual(set_title('- [ ] X', 'Y'), '- [ ] Y')

        with t.subTest('indent and check mark are preserved'):
            t.assertEqual(
                set_title('  - [x] X [LOE:1]', 'Y'),
                '  - [x] Y [LOE:1]',
            )

        with (
            t.subTest('a line that is not a task is rejected'),
            t.assertRaises(ValueError),
        ):
            set_title('      A note line', 'Y')


class TaskNodeTests(TestCase):
    """Unit tests for battodo.parser.TaskNode."""

    def setUp(t) -> None:
        t.tk = parse('## Open\n\n- [ ] X [P:2] [LOE:1]\n').tasks[0]

    def test_is_subtask(t) -> None:
        with t.subTest('top-level task is not a subtask'):
            t.assertFalse(t.tk.is_subtask)

        with t.subTest('child with a field is a subtask'):
            doc = parse('## Open\n\n- [ ] P\n  - [ ] C [LOE:1]\n')
            t.assertTrue(doc.tasks[0].children[0].is_subtask)

    def test_raw_index(t) -> None:
        t.assertEqual(t.tk.raw_index, 2)

    def test_defaults(t) -> None:
        task = TaskNode(
            raw_index=0,
            indent=0,
            done=False,
            title='T',
            fields={},
        )
        t.assertEqual(task.children, [])
        t.assertEqual(task.note_indices, [])


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


class AppendOpenTests(TestCase):
    """Unit tests for battodo.parser.append_open."""

    def test_append_open(t) -> None:
        entry = '- [ ] New [P:1]'

        with t.subTest('lands after the last entry of the Open section'):
            lines = append_open(OPEN_DOC.split('\n'), entry)
            expected = OPEN_DOC.split('\n')
            expected.insert(expected.index('## Done') - 1, entry)
            t.assertEqual(lines, expected)

        with t.subTest('the source list is left alone'):
            t.assertEqual(len(OPEN_DOC.split('\n')), len(lines) - 1)

        with t.subTest('a note or child line is still the last entry'):
            doc = '## Open\n\n- [ ] A [P:1]\n  - [ ] Child [LOE:1]\n'
            t.assertEqual(
                append_open(doc.split('\n'), entry),
                [
                    '## Open',
                    '',
                    '- [ ] A [P:1]',
                    '  - [ ] Child [LOE:1]',
                    entry,
                    '',
                ],
            )

        with t.subTest('an empty Open section takes the first entry'):
            doc = '# Work\n\n## Open\n\n## Done\n'
            t.assertEqual(
                append_open(doc.split('\n'), entry),
                ['# Work', '', '## Open', entry, '', '## Done', ''],
            )


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
