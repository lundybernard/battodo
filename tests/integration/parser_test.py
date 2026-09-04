"""Contract tests for parse-to-serialize byte identity (ADR 0004).

The markdown files stay authoritative and hand-edited, so btodo must
never reformat a file it did not mean to change. This suite pins that
guarantee against the committed list fixtures and against every shape
the parser distinguishes. It outlives the property refactor.
"""

from pathlib import Path
from unittest import TestCase

from battodo.parser import parse, serialize

TODO_DIR = Path(__file__).parent.parent / 'behavioral' / 'data' / 'todo'

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
    return serialize(parse(text))


class RoundTripTests(TestCase):
    """Contract tests for battodo.parser round-trip byte identity."""

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
