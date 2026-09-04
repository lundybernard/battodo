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

    def test_discover_lists(t) -> None:
        with t.subTest('a list is a file carrying an open section'):
            t.assertEqual(discover_lists(t.dir), [t.backlog, t.work])

        with t.subTest('which is what an ad-hoc name is admitted on'):
            t.assertIn(t.backlog, discover_lists(t.dir))

        with t.subTest('prose without one is not a list'):
            t.assertNotIn(t.prose, discover_lists(t.dir))

        with t.subTest('they come back in name order'):
            t.assertEqual(
                [path.name for path in discover_lists(t.dir)],
                ['backlog.md', 'work.md'],
            )

        with t.subTest('and only markdown is ever considered'):
            t.dir.glob.assert_called_with('*.md')

        with t.subTest('a directory that is not there yields nothing'):
            t.dir.is_dir.return_value = False
            t.assertEqual(discover_lists(t.dir), [])

        with t.subTest('and is not searched at all'):
            t.dir.glob.reset_mock()
            discover_lists(t.dir)
            t.dir.glob.assert_not_called()


class CategoryOrderTests(TestCase):
    """Unit tests for battodo.lists.category_order."""

    def test_category_order(t) -> None:
        with t.subTest('the named categories lead, in their own order'):
            t.assertEqual(
                sorted(['career', 'work', 'chores'], key=category_order),
                ['work', 'chores', 'career'],
            )

        with t.subTest('an ad-hoc name follows them, alphabetically'):
            t.assertEqual(
                sorted(['van', 'career', 'arts'], key=category_order),
                ['career', 'arts', 'van'],
            )


class ItemCountTests(TestCase):
    """Unit tests for battodo.lists.item_count."""

    def test_item_count(t) -> None:
        with t.subTest('a configured count is read as a number'):
            t.assertEqual(item_count('2'), 2)

        for value in ('0', '-1', 'five', ''):
            with (
                t.subTest(f'{value!r} is not a count'),
                t.assertRaises(ValueError) as caught,
            ):
                item_count(value)
            t.assertIn(COUNT_ERROR, str(caught.exception))
