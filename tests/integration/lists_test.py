"""Contract tests for list discovery, against real files.

Inputs are a real directory holding real todo lists. This layer
asserts state; interaction checks stay in the isolation tests beside
the code.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.lists import discover_lists

PARKED = '<!-- battodo:parked -->'
# A document with a longer heading that starts with `## Open`.
LONGER_HEADING = '# Longer heading\n\n## Open-prefixed heading\n'
# A document that shows the list format in a fenced example.
GUIDE = '# Guide\n\n```markdown\n## Open\n\n- [ ] fenced example task\n```\n'


def source_dir(t: TestCase) -> Path:
    """An empty source directory, removed when the test ends."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    return Path(tmp.name)


def write(source: Path, name: str, *items: str, parked: bool = False) -> Path:
    """Write the list `name`, holding `items` in its open section."""
    marker = f'{PARKED}\n\n' if parked else ''
    path = source / f'{name}.md'
    body = '\n'.join(items)
    path.write_text(
        f'# {name}\n\n{marker}## Open\n\n{body}\n',
        encoding='utf-8',
    )
    return path


class DiscoverListsTests(TestCase):
    """Contract tests for battodo.lists.discover_lists."""

    def setUp(t) -> None:
        t.source = source_dir(t)

    def test_lists(t) -> None:
        career = write(t.source, 'career', '- [ ] A visible task [P:2]')
        study = write(
            t.source,
            'study',
            '- [ ] A parked task [P:2]',
            parked=True,
        )

        ret = discover_lists(t.source)

        # Every list is found, in name order.
        t.assertEqual(ret, [career, study])

    def test_open_section(t) -> None:
        write(t.source, 'career', '- [ ] A visible task [P:2]')
        loose = t.source / 'notes.md'
        loose.write_text('# Notes\n\nNothing open here.\n', encoding='utf-8')
        longer = t.source / 'longer-heading.md'
        longer.write_text(LONGER_HEADING, encoding='utf-8')
        guide = t.source / 'format-guide.md'
        guide.write_text(GUIDE, encoding='utf-8')

        ret = discover_lists(t.source)

        with t.subTest('a file with no open section is not a list'):
            t.assertNotIn(loose, ret)

        with t.subTest('nor is one whose heading only starts with Open'):
            t.assertNotIn(longer, ret)

        with t.subTest('nor is one whose open heading is a fenced example'):
            t.assertNotIn(guide, ret)

    def test_absent(t) -> None:
        ret = discover_lists(t.source / 'absent')
        t.assertEqual(ret, [])
