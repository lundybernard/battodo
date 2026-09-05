"""Contract tests for round-trip byte identity (ADR 0004).

The markdown files stay authoritative and hand-edited, so btodo must
never reformat a file it did not mean to change. This suite pins that
guarantee against the committed list fixtures and against every shape
the parser distinguishes. It outlives the property refactor.
"""

from pathlib import Path
from unittest import TestCase

from battodo.parser import TodoDocument

TODO_DIR = Path(__file__).parent.parent / 'behavioral' / 'data' / 'todo'
WORK = TODO_DIR / 'work.md'
# The first open task of `work.md`, and the same line once btodo
# stamps an id on it.
OVERDUE_INDEX = 4
OVERDUE = '- [ ] Overdue task [P:4] [LOE:2] [DUE:2026-08-01]'
STAMPED = f'{OVERDUE} [ID:zz01ab]'
# The line an appended entry takes: after the last open entry, and
# before the blank run that precedes the next heading.
APPENDED_INDEX = 15

# Every construct the parser branches on, one case each. The titles
# name the role the line plays, not any real task.
SHAPES = {
    'blank runs between entries': (
        '# Roles\n\n## Open\n\n\n- [ ] First task [P:1]\n\n\n\n'
        '- [ ] Second task [P:2]\n\n## Done\n'
    ),
    'nested children': (
        '## Open\n\n- [ ] Parent task [P:1]\n'
        '  - [ ] Child task [LOE:2]\n'
        '    - [ ] Grandchild task [LOE:1]\n'
    ),
    'checklist items and note lines': (
        '## Open\n\n- [ ] Parent task [P:1]\n'
        '      A note line under the parent.\n'
        '  - [ ] Checklist item\n'
    ),
    'fields in any order': (
        '## Open\n\n- [ ] First task [LOE:2] [P:1] [DUE:2026-01-01]\n'
        '- [ ] Second task [DUE:2026-01-02] [TAGS:a,b] [P:3] [LOE:1]\n'
    ),
    'trailing whitespace': '## Open\n\n- [ ] First task [P:1]   \n   \n',
    'no trailing newline': '## Open\n\n- [ ] First task [P:1]',
    'a checked task': '## Open\n\n- [x] First task [P:1]\n\n## Done\n',
    'a comment line after a task': (
        '## Open\n\n- [ ] First task [P:1]\n<!-- Not a note. -->\n'
    ),
    'no open section': '# Roles\n\nProse, and no section at all.\n',
    'an empty document': '',
}


def round_trip(text: str) -> str:
    """Return `text` as the parser gives it back."""
    return TodoDocument(text).text


class RoundTripTests(TestCase):
    """Contract tests for battodo.parser.TodoDocument byte identity."""

    maxDiff = None

    def test_list_files(t) -> None:
        paths = sorted(TODO_DIR.glob('*.md'))
        t.assertTrue(paths, f'no fixture lists in {TODO_DIR}')
        for path in paths:
            with t.subTest(path.name):
                text = path.read_text(encoding='utf-8')
                t.assertEqual(round_trip(text), text)

    def test_parsed_shapes(t) -> None:
        for name, text in SHAPES.items():
            with t.subTest(name):
                t.assertEqual(round_trip(text), text)


class TodoDocumentTests(TestCase):
    """Contract tests for battodo.parser.TodoDocument, against a real list."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = WORK.read_text(encoding='utf-8')
        t.td = TodoDocument(t.source)

    def test_lines(t) -> None:
        with t.subTest('every line of the file, verbatim and in order'):
            t.assertEqual(t.td.lines, t.source.split('\n'))

        with t.subTest('addressed by the index a task carries'):
            t.assertEqual(t.td.lines[OVERDUE_INDEX], OVERDUE)

    def test_tasks(t) -> None:
        with t.subTest('the open section, top level in file order'):
            t.assertEqual(
                [task.title for task in t.td.tasks],
                [
                    'Overdue task',
                    'Due today task',
                    'Legacy priority task',
                    (
                        'A very long task title that the task column '
                        'has to clip to fit'
                    ),
                    'Placeholder due date task',
                    'Lowest ranked task',
                    'Completed task',
                    'Future recurring task',
                ],
            )

        with t.subTest('a task addresses its own line'):
            first = t.td.tasks[0]
            t.assertEqual(first.raw_index, OVERDUE_INDEX)
            t.assertEqual(first.raw, OVERDUE)

        with t.subTest('children hang off the task they are indented under'):
            t.assertEqual(
                [task.title for task in t.td.tasks[2].children],
                [
                    'Open checklist item',
                    'Open subtask',
                    'Completed checklist item',
                ],
            )

        with t.subTest('a section that is not Open yields no task'):
            t.assertNotIn(
                'Task outside the open section',
                [task.title for task in t.td.tasks],
            )

    def test_text(t) -> None:
        with t.subTest('the source, byte for byte, until a method writes'):
            t.assertEqual(t.td.text, t.source)

        with t.subTest('and the edited file after one'):
            t.td.set_field(OVERDUE_INDEX, 'ID', 'zz01ab')
            t.assertEqual(t.td.text, t.source.replace(OVERDUE, STAMPED))

    def test_set_field(t) -> None:
        with t.subTest('an absent field is appended, and the line returned'):
            t.assertEqual(
                t.td.set_field(OVERDUE_INDEX, 'ID', 'zz01ab'),
                STAMPED,
            )
            t.assertEqual(t.td.lines[OVERDUE_INDEX], STAMPED)

        with t.subTest('an existing field is replaced where it stands'):
            t.assertEqual(
                t.td.set_field(OVERDUE_INDEX, 'P', '2'),
                STAMPED.replace('[P:4]', '[P:2]'),
            )

    def test_set_title(t) -> None:
        with t.subTest('the title changes, every field keeps its place'):
            t.assertEqual(
                t.td.set_title(OVERDUE_INDEX, 'Renamed task'),
                OVERDUE.replace('Overdue task', 'Renamed task'),
            )
            t.assertEqual(
                t.td.lines[OVERDUE_INDEX],
                OVERDUE.replace('Overdue task', 'Renamed task'),
            )

        with t.subTest('a line that is not a task is rejected'):
            with t.assertRaises(ValueError) as caught:
                t.td.set_title(0, 'Renamed task')
            t.assertEqual(
                str(caught.exception),
                "not a task line: '# Work'",
            )

    def test_append_open(t) -> None:
        entry = '- [ ] Added task [P:1]'

        with t.subTest('the entry lands last in the open section'):
            t.assertEqual(t.td.append_open(entry), APPENDED_INDEX)
            t.assertEqual(t.td.lines[APPENDED_INDEX], entry)

        with t.subTest('and every other line keeps its text and order'):
            expected = t.source.split('\n')
            expected.insert(APPENDED_INDEX, entry)
            t.assertEqual(t.td.text, '\n'.join(expected))
