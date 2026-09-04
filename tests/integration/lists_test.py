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


class DiscoverListsTests(TestCase):
    """Contract tests for battodo.lists.discover_lists."""

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)

    def write(t, name: str, *items: str, parked: bool = False) -> Path:
        """Write the list `name`, holding `items` in its open section."""
        marker = f'{PARKED}\n\n' if parked else ''
        path = t.source / f'{name}.md'
        body = '\n'.join(items)
        path.write_text(
            f'# {name}\n\n{marker}## Open\n\n{body}\n',
            encoding='utf-8',
        )
        return path

    def test_discover_lists(t) -> None:
        career = t.write('career', '- [ ] A visible task [P:2]')
        study = t.write('study', '- [ ] A parked task [P:2]', parked=True)
        loose = t.source / 'notes.md'
        loose.write_text('# Notes\n\nNothing open here.\n', encoding='utf-8')

        found = discover_lists(t.source)

        with t.subTest('every list is found, in name order'):
            t.assertEqual(found, [career, study])

        with t.subTest('a file with no open section is not a list'):
            t.assertNotIn(loose, found)

        with t.subTest('a directory that is not there yields nothing'):
            t.assertEqual(discover_lists(t.source / 'absent'), [])
