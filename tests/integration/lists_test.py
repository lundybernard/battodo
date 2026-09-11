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

        ret = discover_lists(t.source)

        # A file with no open section is not a list.
        t.assertNotIn(loose, ret)

    def test_absent(t) -> None:
        ret = discover_lists(t.source / 'absent')
        t.assertEqual(ret, [])
