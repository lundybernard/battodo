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
    TodoDocument,
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
    """Characterization tests for the parser surface, old and new."""

    maxDiff = None

    def setUp(t) -> None:
        t.doc = parse(ROLES)
        t.first = t.doc.tasks[0]
        t.td = TodoDocument(ROLES)

    def test_parse(t) -> None:
        ret = parse(ROLES)

        with t.subTest('every line is kept, verbatim and in order'):
            t.assertEqual(ret.lines, ROLES.split('\n'))

        with t.subTest('only the open section yields tasks'):
            titles = [task.title for task in ret.tasks]

            t.assertEqual(
                titles,
                ['First task', 'Placeholder effort task', 'Checked task'],
            )

        with t.subTest('a task addresses its own line by index'):
            first = ret.tasks[0]

            t.assertEqual(first.raw_index, 6)
            t.assertEqual(first.raw, ret.lines[6])
            t.assertEqual(first.indent, 0)

        with t.subTest('the check mark decides done'):
            flags = [task.done for task in ret.tasks]

            t.assertEqual(flags, [False, False, True])

        with t.subTest('fields leave the title, whatever their order'):
            fields = ret.tasks[0].fields

            t.assertEqual(
                fields,
                {
                    'P': '4',
                    'LOE': '2',
                    'DUE': '2026-08-01',
                    'ID': 'zz01ab',
                    'TAGS': 'first,second',
                },
            )

        with t.subTest('children nest by indent, at any depth'):
            child, checklist = ret.tasks[0].children
            titles = [task.title for task in child.children]

            t.assertEqual(child.title, 'Child task')
            t.assertEqual(checklist.title, 'Checklist item')
            t.assertEqual(titles, ['Grandchild task'])

        with t.subTest('a note line is an index on its task, not a child'):
            t.assertEqual(ret.tasks[0].note_indices, [7])

        with t.subTest('a comment line is neither'):
            indices = [
                index for task in ret.tasks for index in task.note_indices
            ]

            t.assertEqual(indices, [7])

        with t.subTest('the object derives the same lines and tasks'):
            td_lines = t.td.lines
            td_tasks = t.td.tasks

            t.assertEqual(td_lines, ret.lines)
            t.assertEqual(td_tasks, ret.tasks)

        with t.subTest('a line no task owns is no note, in both'):
            cases = {
                'a comment after a task': (
                    '## Open\n\n- [ ] First task [P:1]\n<!-- Not a note. -->\n'
                ),
                'prose before any task': (
                    '## Open\n\nProse, before any task.\n- [ ] First task\n'
                ),
            }

            for name, text in cases.items():
                tasks = parse(text).tasks
                td_tasks = TodoDocument(text).tasks

                t.assertEqual(tasks[0].note_indices, [], name)
                t.assertEqual(td_tasks[0].note_indices, [], name)

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
            with t.subTest(f'{name}, both implementations'):
                td = TodoDocument(text)

                ret = serialize(parse(text))
                td_ret = td.text

                t.assertEqual(ret, text)
                t.assertEqual(td_ret, text)

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
            with t.subTest(f'{name}, both implementations'):
                td = TodoDocument(raw)

                ret = set_field(raw, *edit)
                td_ret = td.set_field(0, *edit)

                t.assertEqual(ret, expected)
                t.assertEqual(td_ret, expected)

        with t.subTest('trailing whitespace is dropped by an append'):
            spaced = '- [ ] First task [P:2]   '
            td = TodoDocument(spaced)

            ret = set_field(spaced, 'ID', 'zz01ab')
            td_ret = td.set_field(0, 'ID', 'zz01ab')

            t.assertEqual(ret, '- [ ] First task [P:2] [ID:zz01ab]')
            t.assertEqual(td_ret, '- [ ] First task [P:2] [ID:zz01ab]')

        with t.subTest('edits chain on an already-edited line'):
            dated = set_field(raw, 'DUE', '2026-08-23')

            ret = set_field(dated, 'ID', 'zz01ab')

            t.assertEqual(
                ret,
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

        for name, ((raw, title), expected) in cases.items():
            with t.subTest(f'{name}, both implementations'):
                td = TodoDocument(raw)

                ret = set_title(raw, title)
                td_ret = td.set_title(0, title)

                t.assertEqual(ret, expected)
                t.assertEqual(td_ret, expected)

        with t.subTest('a line that is not a task is rejected, by both'):
            note = t.doc.lines[7]
            td = TodoDocument(note)

            with t.assertRaises(ValueError) as caught:
                set_title(note, 'Second task')

            with t.assertRaises(ValueError) as td_caught:
                td.set_title(0, 'Second task')

            t.assertEqual(str(caught.exception), f'not a task line: {note!r}')
            t.assertEqual(
                str(td_caught.exception), f'not a task line: {note!r}'
            )

    def test_append_open(t) -> None:
        entry = '- [ ] Added task [P:1]'

        with t.subTest('the entry lands after the last line of the section'):
            expected = list(t.doc.lines)
            expected.insert(13, entry)

            ret = append_open(t.doc.lines, entry)

            t.assertEqual(ret, expected)

        with t.subTest('the argument list is left alone'):
            t.assertEqual(t.doc.lines, ROLES.split('\n'))

        with t.subTest('the object inserts it at the same index'):
            expected = append_open(t.doc.lines, entry)

            td_ret = t.td.append_open(entry)

            t.assertEqual(td_ret, 13)
            t.assertEqual(t.td.lines, expected)

        with t.subTest('an empty section takes the entry under its heading'):
            empty = ['# Roles', '', '## Open', '', '## Done']
            td = TodoDocument('\n'.join(empty))

            ret = append_open(empty, entry)
            td_ret = td.append_open(entry)

            t.assertEqual(
                ret,
                ['# Roles', '', '## Open', entry, '', '## Done'],
            )
            t.assertEqual(td_ret, 3)

        with t.subTest('a file with no open section raises, in both'):
            td = TodoDocument('# Roles\n\n## Done')

            with t.assertRaises(StopIteration):
                append_open(['# Roles', '', '## Done'], entry)

            with t.assertRaises(StopIteration):
                td.append_open(entry)

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

        with t.subTest('#51: a non-integer effort raises in both, unread'):
            for task in (t.doc.tasks[1], t.td.tasks[1]):
                with t.assertRaises(ValueError) as caught:
                    _ = task.loe

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
            ret = TodoFile(lines=t.doc.lines, tasks=t.doc.tasks)

            t.assertEqual(t.doc, ret)

        with t.subTest('a container with no tasks is the default'):
            ret = TodoFile(lines=[])

            t.assertEqual(ret.tasks, [])

        with t.subTest('the object serializes from the same lines'):
            expected = serialize(t.doc)

            td_ret = t.td.text

            t.assertEqual(td_ret, expected)
