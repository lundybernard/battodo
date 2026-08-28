from datetime import date, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

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
        for target in ('TaskSelection', 'complete', 'parse_date'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.tk = Task(Path(CONFIGURED), 'brush pile', TODAY)

        t.now = Mock(spec=datetime)
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = CONFIGURED
        t.conf.selector = 'brush pile'

    def dated(t, value):
        """The same configuration, carrying a completion date."""
        conf = Mock(spec=['view', 'selector', 'date'])
        conf.view = t.conf.view
        conf.selector = t.conf.selector
        conf.date = value
        return conf

    def test_from_config(t):
        task = Task.from_config(t.conf, t.now)

        with t.subTest('the source directory is left unexpanded'):
            t.assertEqual(task.directory, Path(CONFIGURED))

        with t.subTest('the selector names the task'):
            t.assertEqual(task.selector, 'brush pile')

        with t.subTest('and the clock gives the day it is logged under'):
            t.assertEqual(task.today, t.now.date.return_value)

        with t.subTest('a configured date is that day instead'):
            conf = t.dated('2026-07-20')

            task = Task.from_config(conf, t.now)

            t.parse_date.assert_called_once_with('2026-07-20')
            t.assertEqual(task.today, t.parse_date.return_value)

        with t.subTest('a date btodo cannot read is refused'):
            t.parse_date.return_value = None

            with t.assertRaises(ValueError):
                Task.from_config(t.dated('yesterday'), t.now)

    def test_source(t):
        t.assertEqual(t.tk.source, SOURCE)

    def test_record(t):
        with t.subTest('the selector is looked up in the source'):
            t.assertIs(t.tk.record, t.TaskSelection.return_value.record)
            t.TaskSelection.assert_called_once_with(SOURCE, 'brush pile')

        with t.subTest('and a second read costs no second lookup'):
            t.assertIs(t.tk.record, t.TaskSelection.return_value.record)
            t.TaskSelection.assert_called_once_with(SOURCE, 'brush pile')

    def test_complete(t):
        t.tk.complete()

        t.complete.assert_called_once_with(SOURCE, 'brush pile', TODAY)

    def test_completed(t):
        with t.subTest('a task that was not completed logged nothing'):
            t.assertEqual(t.tk.completed, [])

        with t.subTest('the entries the write returned'):
            t.complete.return_value = ['2026-08-05 | work | DONE | Deck']

            t.tk.complete()

            t.assertEqual(t.tk.completed, ['2026-08-05 | work | DONE | Deck'])
