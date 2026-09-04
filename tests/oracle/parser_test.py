"""Characterization tests for the parser surface in `battodo.parser`.

Temporary scaffolding for the conversion to a document object. The
suite pins what the module functions do, then asserts the new object
answers the same. It is deleted with the functions it pins.

It records behavior, so a defect it finds is pinned rather than fixed:
`TaskNode.loe` raises on a non-integer value (#51).
"""

from unittest import TestCase

from battodo.parser import (
    TaskNode,
    TodoFile,
    append_open,
    parse,
    serialize,
    set_field,
    set_title,
)

# One list, holding every construct the parser branches on: fields in
# two orders, a note line, a comment inside the section, three levels of
# nesting, a fieldless checklist item, a checked task, a placeholder
# effort value, and a task outside the open section.
ROLES = """# Roles

## Open

<!-- Add items here. -->

- [ ] First task [P:4] [LOE:2] [DUE:2026-08-01] [ID:zz01ab] [TAGS:first,second]
      A note line under the first task.
  - [ ] Child task [LOE:3]
    - [ ] Grandchild task
  - [ ] Checklist item
- [ ] Placeholder effort task [LOE:?]
- [x] Checked task [P:1] [REPEAT:14d] [ADDED:2026-07-01]

## Done

- [ ] Closed task [P:9]
"""


class ParsedListTests(TestCase):
    """Characterization tests for the parser surface in battodo.parser."""

    maxDiff = None

    def setUp(t) -> None:
        t.doc = parse(ROLES)
        t.first = t.doc.tasks[0]

    def test_parse(t) -> None:
        with t.subTest('every line is kept, verbatim and in order'):
            t.assertEqual(t.doc.lines, ROLES.split('\n'))

        with t.subTest('only the open section yields tasks'):
            t.assertEqual(
                [task.title for task in t.doc.tasks],
                ['First task', 'Placeholder effort task', 'Checked task'],
            )

        with t.subTest('a task addresses its own line by index'):
            t.assertEqual(t.first.raw_index, 6)
            t.assertEqual(t.first.raw, t.doc.lines[6])
            t.assertEqual(t.first.indent, 0)

        with t.subTest('the check mark decides done'):
            t.assertEqual(
                [task.done for task in t.doc.tasks],
                [False, False, True],
            )

        with t.subTest('fields leave the title, whatever their order'):
            t.assertEqual(
                t.first.fields,
                {
                    'P': '4',
                    'LOE': '2',
                    'DUE': '2026-08-01',
                    'ID': 'zz01ab',
                    'TAGS': 'first,second',
                },
            )

        with t.subTest('children nest by indent, at any depth'):
            child, checklist = t.first.children
            t.assertEqual(child.title, 'Child task')
            t.assertEqual(checklist.title, 'Checklist item')
            t.assertEqual(
                [task.title for task in child.children],
                ['Grandchild task'],
            )

        with t.subTest('a note line is an index on its task, not a child'):
            t.assertEqual(t.first.note_indices, [7])

        with t.subTest('a comment line is neither'):
            t.assertEqual(
                [index for task in t.doc.tasks for index in task.note_indices],
                [7],
            )

    def test_serialize(t) -> None:
        cases = {
            'the fixture list': ROLES,
            'no trailing newline': '## Open\n\n- [ ] First task [P:1]',
            'nothing at all': '',
            'blank runs': '## Open\n\n\n\n',
            'trailing whitespace': '## Open\n- [ ] First task [P:1]   \n',
            'no open section': '# Roles\n\nProse only.\n',
        }
        for name, text in cases.items():
            with t.subTest(name):
                t.assertEqual(serialize(parse(text)), text)

    def test_set_field(t) -> None:
        raw = '- [ ] First task [P:2] [LOE:1]'
        cases = {
            'an existing field is replaced where it stands': (
                ('P', '3'),
                '- [ ] First task [P:3] [LOE:1]',
            ),
            'a following field keeps its position': (
                ('LOE', '5'),
                '- [ ] First task [P:2] [LOE:5]',
            ),
            'an absent field is appended after the last': (
                ('ID', 'zz01ab'),
                '- [ ] First task [P:2] [LOE:1] [ID:zz01ab]',
            ),
        }
        for name, (edit, expected) in cases.items():
            with t.subTest(name):
                t.assertEqual(set_field(raw, *edit), expected)

        with t.subTest('trailing whitespace is dropped by an append'):
            t.assertEqual(
                set_field('- [ ] First task [P:2]   ', 'ID', 'zz01ab'),
                '- [ ] First task [P:2] [ID:zz01ab]',
            )

        with t.subTest('edits chain on an already-edited line'):
            t.assertEqual(
                set_field(set_field(raw, 'DUE', '2026-08-23'), 'ID', 'zz01ab'),
                '- [ ] First task [P:2] [LOE:1] [DUE:2026-08-23] [ID:zz01ab]',
            )

    def test_set_title(t) -> None:
        cases = {
            'the title changes, every field keeps its place': (
                ('- [ ] First task [P:2] [LOE:1]', 'Second task'),
                '- [ ] Second task [P:2] [LOE:1]',
            ),
            'a fieldless line is the title alone': (
                ('- [ ] First task', 'Second task'),
                '- [ ] Second task',
            ),
            'indent and check mark survive': (
                ('  - [x] First task [LOE:1]', 'Second task'),
                '  - [x] Second task [LOE:1]',
            ),
        }
        for name, (edit, expected) in cases.items():
            with t.subTest(name):
                t.assertEqual(set_title(*edit), expected)

        with t.subTest('a line that is not a task is rejected'):
            note = t.doc.lines[7]
            with t.assertRaises(ValueError) as caught:
                set_title(note, 'Second task')
            t.assertEqual(str(caught.exception), f'not a task line: {note!r}')

    def test_append_open(t) -> None:
        entry = '- [ ] Added task [P:1]'

        with t.subTest('the entry lands after the last line of the section'):
            lines = append_open(t.doc.lines, entry)
            expected = list(t.doc.lines)
            expected.insert(13, entry)
            t.assertEqual(lines, expected)

        with t.subTest('the argument list is left alone'):
            t.assertEqual(t.doc.lines, ROLES.split('\n'))

        with t.subTest('an empty section takes the entry under its heading'):
            t.assertEqual(
                append_open(['# Roles', '', '## Open', '', '## Done'], entry),
                ['# Roles', '', '## Open', entry, '', '## Done'],
            )

        with (
            t.subTest('a file with no open section raises'),
            t.assertRaises(StopIteration),
        ):
            append_open(['# Roles', '', '## Done'], entry)

    def test_task_node(t) -> None:
        checked = t.doc.tasks[2]
        child, checklist = t.first.children

        with t.subTest('the typed field readers'):
            t.assertEqual(t.first.loe, 2)
            t.assertEqual(t.first.due, '2026-08-01')
            t.assertEqual(t.first.task_id, 'zz01ab')
            t.assertEqual(t.first.tags, ['first', 'second'])
            t.assertEqual(checked.repeat, '14d')
            t.assertEqual(checked.added, '2026-07-01')

        with t.subTest('an absent field reads as absent'):
            t.assertIsNone(checked.due)
            t.assertIsNone(checked.loe)
            t.assertIsNone(t.first.added)
            t.assertIsNone(t.first.repeat)
            t.assertIsNone(child.task_id)
            t.assertEqual(checklist.tags, [])

        with t.subTest('a child carrying a field is a subtask'):
            t.assertFalse(t.first.is_subtask)
            t.assertTrue(child.is_subtask)
            t.assertFalse(checklist.is_subtask)

        with t.subTest('#51: a non-integer effort raises, it does not read'):
            with t.assertRaises(ValueError) as caught:
                _ = t.doc.tasks[1].loe
            t.assertEqual(
                str(caught.exception),
                "invalid literal for int() with base 10: '?'",
            )

        with t.subTest('a hand-built node has no children and no notes'):
            node = TaskNode(
                raw_index=0,
                indent=0,
                done=False,
                title='First task',
                fields={},
                # Default: raw='',
            )
            t.assertEqual(node.raw, '')
            t.assertEqual(node.children, [])
            t.assertEqual(node.note_indices, [])

    def test_todo_file(t) -> None:
        with t.subTest('lines and tasks are the whole container'):
            t.assertEqual(
                t.doc, TodoFile(lines=t.doc.lines, tasks=t.doc.tasks)
            )

        with t.subTest('a container with no tasks is the default'):
            t.assertEqual(TodoFile(lines=[]).tasks, [])
