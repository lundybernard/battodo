from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch, sentinel

from battodo.lib import (
    add_item,
    backfill_items,
    complete_item,
    get_completed,
    get_item,
    get_view,
    scratch_item,
    update_item,
)

SRC = 'battodo.lib'
# The configured `~/todo` as every function resolves it.
SOURCE = Path.home() / 'todo'


class GetViewTests(TestCase):
    """Unit tests for battodo.lib.get_view."""

    def setUp(t):
        for target in ('Selection', 'View'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.selection = t.Selection.from_config.return_value

        t.now = sentinel.now
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_get_view(t):
        with t.subTest('the configuration is decoded once, by the selection'):
            rendered = get_view(t.conf, t.now)

            t.Selection.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which a human reads as a rendered view'):
            t.View.assert_called_once_with(t.selection)
            t.assertEqual(rendered, t.View.return_value.text)

        with t.subTest('and a machine reads as the same selection, as JSON'):
            t.conf.format = 'json'

            t.assertEqual(get_view(t.conf, t.now), t.selection.json)

        with t.subTest('which is serialized, never rendered'):
            t.View.assert_called_once()

        with t.subTest('an unconfigured format is the human view'):
            conf = Mock(spec=['view'])

            t.assertEqual(get_view(conf, t.now), t.View.return_value.text)


class GetCompletedTests(TestCase):
    """Unit tests for battodo.lib.get_completed."""

    def setUp(t):
        for target in ('Digest', 'DigestView'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.digest = t.Digest.from_config.return_value

        t.now = sentinel.now
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_get_completed(t):
        with t.subTest('the configuration is decoded once, by the digest'):
            rendered = get_completed(t.conf, t.now)

            t.Digest.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which a human reads as a rendered digest'):
            t.DigestView.assert_called_once_with(t.digest)
            t.assertEqual(rendered, t.DigestView.return_value.text)

        with t.subTest('and a machine reads as the same digest, as JSON'):
            t.conf.format = 'json'

            t.assertEqual(get_completed(t.conf, t.now), t.digest.json)

        with t.subTest('which is serialized, never rendered'):
            t.DigestView.assert_called_once()

        with t.subTest('an unconfigured format is the human digest'):
            conf = Mock(spec=['view'])

            t.assertEqual(
                get_completed(conf, t.now), t.DigestView.return_value.text
            )


class GetItemTests(TestCase):
    """Unit tests for battodo.lib.get_item."""

    def setUp(t):
        for target in ('build_item', 'build_item_json'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.now = sentinel.now
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'format'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'
        t.conf.format = 'text'

    def test_get_item(t):
        with t.subTest('the human form is the default'):
            built = get_item(t.conf, t.now)

            args = t.build_item.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.now)
            t.assertEqual(built, t.build_item.return_value)

        with t.subTest('json format is serialized instead'):
            t.conf.format = 'json'

            built = get_item(t.conf, t.now)

            t.assertEqual(t.build_item_json.call_args[0][1], 'brush pile')
            t.assertEqual(built, t.build_item_json.return_value)

        with t.subTest('which is serialized, never rendered'):
            t.build_item.assert_called_once()

        with t.subTest('an unconfigured format is the human form'):
            conf = Mock(spec=['view', 'selector'])
            conf.view.source_dir = '~/todo'
            conf.selector = 'brush pile'

            get_item(conf, t.now)

            t.assertEqual(t.build_item.call_count, 2)


class AddItemTests(TestCase):
    """Unit tests for battodo.lib.add_item."""

    def setUp(t):
        for target in ('add_task', 'add_subtask'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)

        t.path = Path('~/todo/chores.md')
        t.entry = '- [ ] Water it [P:4] [ADDED:2026-08-08] [ID:ab12cd]'
        t.add_task.return_value = (t.path, t.entry)
        t.add_subtask.return_value = (t.path, t.entry)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        # spec models batconf: an argument the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'list', 'title', 'priority', 'due'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.list = 'chores'
        t.conf.title = 'Water it'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'

    def test_add_item(t):
        with t.subTest('list, title and supplied fields are forwarded'):
            written = add_item(t.conf, t.now)

            args = t.add_task.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'chores')
            t.assertEqual(args[2], 'Water it')
            t.assertEqual(args[3], {'P': '4', 'DUE': '2026-09-01'})
            t.assertEqual(args[4], t.today)

        with t.subTest('the created line and its file come back'):
            # A P-less add ranks near 0 and will not show in a view, so
            # this is the only confirmation of the write.
            t.assertEqual(written, f'{t.entry}\n{t.path}')

        with t.subTest('an add with no fields writes none'):
            t.add_task.reset_mock()
            conf = Mock(spec=['view', 'list', 'title'])
            conf.view.source_dir = '~/todo'
            conf.list = 'chores'
            conf.title = 'Water it'

            add_item(conf, t.now)

            t.assertEqual(t.add_task.call_args[0][3], {})

        with t.subTest('a parent sends the add to the subtask path'):
            t.add_task.reset_mock()
            t.now.date.reset_mock()
            conf = Mock(spec=['view', 'list', 'title', 'parent', 'loe'])
            conf.view.source_dir = '~/todo'
            conf.list = 'work'
            conf.title = 'Buy lumber'
            conf.parent = '9o71lx'
            conf.loe = '2'

            written = add_item(conf, t.now)

            t.add_task.assert_not_called()
            args = t.add_subtask.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'work')
            t.assertEqual(args[2], '9o71lx')
            t.assertEqual(args[3], 'Buy lumber')
            t.assertEqual(args[4], {'LOE': '2'})

        with t.subTest('a subtask carries no add date, so none is derived'):
            t.now.date.assert_not_called()

        with t.subTest('the subtask line and its file come back'):
            t.assertEqual(written, f'{t.entry}\n{t.path}')


class UpdateItemTests(TestCase):
    """Unit tests for battodo.lib.update_item."""

    def setUp(t):
        patcher = patch(f'{SRC}.update_task', autospec=True)
        t.update_task = patcher.start()
        t.addCleanup(patcher.stop)

        t.path = Path('~/todo/chores.md')
        t.entry = '- [ ] Water it [P:4] [ID:ab12cd]'
        t.update_task.return_value = (t.path, t.entry)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        # spec models batconf: an option the user did not supply is
        # absent from the Configuration, not None.
        t.conf = Mock(spec=['view', 'selector', 'priority', 'due', 'title'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'
        t.conf.priority = '4'
        t.conf.due = '2026-09-01'
        t.conf.title = 'Water it'

    def test_update_item(t):
        with t.subTest('selector, supplied fields and title are forwarded'):
            written = update_item(t.conf, t.now)

            args, kwargs = t.update_task.call_args
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], {'P': '4', 'DUE': '2026-09-01'})
            t.assertEqual(args[3], t.today)
            t.assertEqual(kwargs['title'], 'Water it')

        with t.subTest('the written line and its file come back'):
            t.assertEqual(written, f'{t.entry}\n{t.path}')

        with t.subTest('an option left off names no change to that field'):
            t.update_task.reset_mock()
            conf = Mock(spec=['view', 'selector', 'tags'])
            conf.view.source_dir = '~/todo'
            conf.selector = 'brush pile'
            conf.tags = 'yard,summer'

            update_item(conf, t.now)

            args, kwargs = t.update_task.call_args
            t.assertEqual(args[2], {'TAGS': 'yard,summer'})
            t.assertIsNone(kwargs['title'])


class CompleteItemTests(TestCase):
    """Unit tests for battodo.lib.complete_item."""

    def setUp(t):
        patcher = patch(f'{SRC}.Task', autospec=True)
        t.Task = patcher.start()
        t.addCleanup(patcher.stop)
        # autospec builds `from_config` from its signature, so its
        # return value carries no spec. The instance mock does, so the
        # classmethod is pointed at that.
        t.task = t.Task.return_value
        t.Task.from_config.return_value = t.task

        t.now = sentinel.now
        # The task decodes the configuration, so this call reads no
        # value off it. The spec still names what a `done` carries.
        t.conf = Mock(spec=['view', 'selector'])

    def test_complete_item(t):
        with t.subTest('the completed.md entries come back, one per line'):
            # Completing the last open child completes its parent too,
            # so one call can log more than one entry.
            t.task.completed = [
                '2026-08-08 | chores | DONE | Deck > Chip it',
                '2026-08-08 | chores | DONE | Deck',
            ]

            logged = complete_item(t.conf, t.now)

            t.assertEqual(
                logged,
                '2026-08-08 | chores | DONE | Deck > Chip it\n'
                '2026-08-08 | chores | DONE | Deck',
            )

        with t.subTest('the configuration is decoded once, by the task'):
            t.Task.from_config.assert_called_once_with(t.conf, t.now)

        with t.subTest('which the call then completes'):
            t.task.complete.assert_called_once_with()

        with t.subTest('an item that is not logged says so'):
            t.task.completed = []

            t.assertEqual(complete_item(t.conf, t.now), 'checked off')


class ScratchItemTests(TestCase):
    """Unit tests for battodo.lib.scratch_item."""

    def setUp(t):
        patcher = patch(f'{SRC}.scratch', autospec=True)
        t.scratch = patcher.start()
        t.addCleanup(patcher.stop)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view', 'selector'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'
        t.conf.selector = 'brush pile'

    def test_scratch_item(t):
        with t.subTest('the completed.md entries come back, one per line'):
            t.scratch.return_value = [
                '2026-08-08 | chores | SCRATCHED | Deck > Chip',
                '2026-08-08 | chores | SCRATCHED | Deck',
            ]

            logged = scratch_item(t.conf, t.now)

            t.assertEqual(
                logged,
                '2026-08-08 | chores | SCRATCHED | Deck > Chip\n'
                '2026-08-08 | chores | SCRATCHED | Deck',
            )

        with t.subTest('selector, source dir and local day are forwarded'):
            args = t.scratch.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], 'brush pile')
            t.assertEqual(args[2], t.today)

        with t.subTest('an item that is not logged says so'):
            t.scratch.return_value = []

            t.assertEqual(scratch_item(t.conf, t.now), 'dropped')


class BackfillItemsTests(TestCase):
    """Unit tests for battodo.lib.backfill_items."""

    def setUp(t):
        patcher = patch(f'{SRC}.backfill_all', autospec=True)
        t.backfill_all = patcher.start()
        t.addCleanup(patcher.stop)

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/todo'

    def test_backfill_items(t):
        with t.subTest('a count comes back per changed list, in order'):
            t.backfill_all.return_value = {
                'work.md': ['a', 'b'],
                'chores.md': ['c'],
            }

            stamped = backfill_items(t.conf, t.now)

            t.assertEqual(stamped, 'chores.md: stamped 1\nwork.md: stamped 2')

        with t.subTest('the source dir and the local day are forwarded'):
            args = t.backfill_all.call_args[0]
            t.assertEqual(args[0], SOURCE)
            t.assertEqual(args[1], t.today)

        with t.subTest('a run that stamped nothing says so'):
            t.backfill_all.return_value = {}

            t.assertEqual(backfill_items(t.conf, t.now), 'nothing to backfill')
