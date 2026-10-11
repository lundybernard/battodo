from datetime import date, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from ..task import Task

SRC = 'battodo.task'
TODAY = date(2026, 8, 5)
# An arbitrary configured directory, and the same path expanded. No
# test reads it: nothing here reaches the filesystem.
CONFIGURED = '~/fake/todo/path'
SOURCE = Path.home() / 'fake/todo/path'


class TaskTests(TestCase):
    """Unit tests for battodo.task.Task."""

    def setUp(t):
        for target in ('TaskSelection', 'parse_date'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.tk = Task(Path(CONFIGURED), 'a selector', TODAY)
        t.selection = MagicMock(spec=['record'])
        t.selection.record = MagicMock(spec=['path', 'doc', 'ancestry'])

        t.now = Mock(spec=datetime)
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = CONFIGURED

    def test_from_config(t):
        task = Task.from_config(t.conf, t.now, selector='a selector')

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(task.directory, Path(CONFIGURED))

        with t.subTest('the selector names the task'):
            t.assertEqual(task.selector, 'a selector')

        with t.subTest('and the clock gives the day it is logged under'):
            t.assertEqual(task.today, t.now.date.return_value)

        with t.subTest('a given date is that day instead'):
            task = Task.from_config(
                t.conf,
                t.now,
                selector='a selector',
                date='2026-07-20',
            )

            t.parse_date.assert_called_once_with('2026-07-20')
            t.assertEqual(task.today, t.parse_date.return_value)

        with t.subTest('a date btodo cannot read is refused'):
            t.parse_date.return_value = None
            with t.assertRaises(ValueError):
                Task.from_config(
                    t.conf,
                    t.now,
                    selector='a selector',
                    date='yesterday',
                )

    def test_source(t):
        ret = t.tk.source
        t.assertEqual(ret, SOURCE)

    def test_path(t):
        t.tk.selection = t.selection
        ret = t.tk.path
        t.assertIs(ret, t.selection.record.path)

    def test_doc(t):
        t.tk.selection = t.selection
        ret = t.tk.doc
        t.assertIs(ret, t.selection.record.doc)

    def test_ancestry(t):
        t.tk.selection = t.selection
        ret = t.tk.ancestry
        t.assertIs(ret, t.selection.record.ancestry)

    def test_node(t):
        t.tk.selection = t.selection
        t.selection.record.ancestry = ['a parent', 'the task']

        ret = t.tk.node

        t.assertEqual(ret, 'the task')

    def test_selection(t):
        with t.subTest('the selector is looked up in the source'):
            ret = t.tk.selection

            t.assertIs(ret, t.TaskSelection.return_value)
            t.TaskSelection.assert_called_once_with(SOURCE, 'a selector')

        with t.subTest('and a second read costs no second lookup'):
            ret = t.tk.selection

            t.assertIs(ret, t.TaskSelection.return_value)
            t.TaskSelection.assert_called_once_with(SOURCE, 'a selector')
