from datetime import date
from unittest import TestCase

from ..parser import (
    Task,
    parse,
    parse_date,
    serialize,
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


class TestParse(TestCase):
    def setUp(t) -> None:
        t.doc = parse(OPEN_DOC)

    def test_tasks(t) -> None:
        with t.subTest('top-level only'):
            t.assertEqual(len(t.doc.tasks), 2)
            t.assertEqual(
                [task.title for task in t.doc.tasks], ['Alpha', 'Beta']
            )

        with t.subTest('done flag'):
            t.assertFalse(t.doc.tasks[0].done)
            t.assertTrue(t.doc.tasks[1].done)

        with t.subTest('fields parsed'):
            alpha = t.doc.tasks[0]
            t.assertEqual(alpha.priority, 95)
            t.assertEqual(alpha.loe, 8)
            t.assertIsNone(alpha.due)
            t.assertEqual(alpha.bumped, '2026-08-08')
            t.assertEqual(alpha.added, '2026-07-01')
            t.assertEqual(alpha.tags, ['a', 'b'])
            t.assertIsNone(alpha.task_id)

        with t.subTest('added is absent on hand-written tasks'):
            doc = parse('## Open\n\n- [ ] Bare\n')
            t.assertIsNone(doc.tasks[0].added)

        with t.subTest('due and repeat'):
            beta = t.doc.tasks[1]
            t.assertEqual(beta.due, '2026-01-01')
            t.assertEqual(beta.repeat, '14d')

        with t.subTest('missing priority defaults to zero'):
            doc = parse('## Open\n\n- [ ] Bare\n')
            t.assertEqual(doc.tasks[0].priority, 0)
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


class TestSerialize(TestCase):
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


class TestTask(TestCase):
    def setUp(t) -> None:
        t.tk = parse('## Open\n\n- [ ] X [P:2] [LOE:1]\n').tasks[0]

    def test_replace_field(t) -> None:
        with t.subTest('existing field replaced in place'):
            t.assertEqual(
                t.tk.replace_field('P', '3'), '- [ ] X [P:3] [LOE:1]'
            )

        with t.subTest('other fields keep their position'):
            t.assertEqual(
                t.tk.replace_field('LOE', '5'), '- [ ] X [P:2] [LOE:5]'
            )

        with t.subTest('absent field appended at end'):
            t.assertEqual(
                t.tk.replace_field('ID', 'zz01'),
                '- [ ] X [P:2] [LOE:1] [ID:zz01]',
            )

    def test_is_subtask(t) -> None:
        with t.subTest('top-level task is not a subtask'):
            t.assertFalse(t.tk.is_subtask)

        with t.subTest('child with a field is a subtask'):
            doc = parse('## Open\n\n- [ ] P\n  - [ ] C [LOE:1]\n')
            t.assertTrue(doc.tasks[0].children[0].is_subtask)

    def test_raw_index(t) -> None:
        t.assertEqual(t.tk.raw_index, 2)


class TestParseDate(TestCase):
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


class TestTaskDataclass(TestCase):
    def test_defaults(t) -> None:
        task = Task(raw_index=0, indent=0, done=False, title='T', fields={})
        t.assertEqual(task.children, [])
        t.assertEqual(task.note_indices, [])
        t.assertEqual(task.priority, 0)
