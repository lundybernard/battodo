from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock

from ..lists import COUNT_ERROR, category_order, discover_lists, item_count


def md(name: str, text: str) -> MagicMock:
    """A stand-in file: one that can be read, and can be sorted."""
    path = MagicMock(spec=Path)
    path.name = name
    path.read_text.return_value = text
    path.__lt__.side_effect = lambda other: name < other.name
    return path


class DiscoverListsTests(TestCase):
    """Unit tests for battodo.lists.discover_lists."""

    def setUp(t) -> None:
        t.work = md('work.md', '# W\n\n## Open\n\n- [ ] A\n')
        t.backlog = md('backlog.md', '## Open\n\n- [ ] B\n')
        t.prose = md('SCHEMA.md', '# Schema\n\nprose, and no open section\n')
        t.dir = Mock(spec=Path)
        t.dir.is_dir.return_value = True
        t.dir.glob.return_value = [t.work, t.prose, t.backlog]

    def test_open_section(t) -> None:
        ret = discover_lists(t.dir)

        with t.subTest('a list is a file carrying an open section'):
            t.assertEqual(ret, [t.backlog, t.work])

        with t.subTest('which is what an ad-hoc name is admitted on'):
            t.assertIn(t.backlog, ret)

        with t.subTest('prose without one is not a list'):
            t.assertNotIn(t.prose, ret)

    def test_order(t) -> None:
        ret = discover_lists(t.dir)

        t.assertEqual(
            [path.name for path in ret],
            ['backlog.md', 'work.md'],
        )

    def test_markdown(t) -> None:
        discover_lists(t.dir)
        # Only markdown is ever considered.
        t.dir.glob.assert_called_with('*.md')

    def test_absent(t) -> None:
        t.dir.is_dir.return_value = False

        ret = discover_lists(t.dir)

        with t.subTest('a directory that is not there yields nothing'):
            t.assertEqual(ret, [])

        with t.subTest('and is not searched at all'):
            t.dir.glob.assert_not_called()


class CategoryOrderTests(TestCase):
    """Unit tests for battodo.lists.category_order."""

    def test_named(t) -> None:
        ret = sorted(['career', 'work', 'chores'], key=category_order)
        # The named categories lead, in their own order.
        t.assertEqual(ret, ['work', 'chores', 'career'])

    def test_ad_hoc(t) -> None:
        ret = sorted(['van', 'career', 'arts'], key=category_order)
        # An ad-hoc name follows the named ones, alphabetically.
        t.assertEqual(ret, ['career', 'arts', 'van'])


class ItemCountTests(TestCase):
    """Unit tests for battodo.lists.item_count."""

    def test_number(t) -> None:
        ret = item_count('2')
        t.assertEqual(ret, 2)

    def test_rejected(t) -> None:
        for value in ('0', '-1', 'five', ''):
            with (
                t.subTest(f'{value!r} is not a count'),
                t.assertRaises(ValueError) as caught,
            ):
                item_count(value)

            t.assertIn(COUNT_ERROR, str(caught.exception))
