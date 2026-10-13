from datetime import datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch, sentinel

from ..lib import (
    add_item,
    annotate_item,
    backfill_items,
    complete_item,
    get_completed,
    get_history,
    get_item,
    get_view,
    update_item,
)

SRC = 'battodo.lib'
# The configured `~/a-source-dir` as every function resolves it.
SOURCE = Path.home() / 'a-source-dir'


class GetViewTests(TestCase):
    """Unit tests for battodo.lib.get_view."""

    def setUp(t):
        for target in ('Selection', 'View'):
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.selection = t.Selection.from_config.return_value

        t.now = sentinel.now
        t.conf = Mock(spec=['view', 'format'])
        t.conf.format = 'text'

    def test_selection(t):
        get_view(t.conf, t.now, show_all=True)
        # The configuration is decoded once, by the selection.
        t.Selection.from_config.assert_called_once_with(
            t.conf,
            t.now,
            show_all=True,
        )

    def test_text(t):
        rendered = get_view(t.conf, t.now, show_all=True)
        t.View.assert_called_once_with(t.selection)
        t.assertEqual(rendered, t.View.return_value.text)

    @patch(f'{SRC}.SelectionJsonView', autospec=True)
    def test_json(t, selection_json_view):
        t.conf.format = 'json'

        rendered = get_view(t.conf, t.now, show_all=True)

        selection_json_view.assert_called_once_with(t.selection)
        t.assertEqual(rendered, selection_json_view.return_value.json)
        # The JSON view serializes the selection; the text view is not
        # built.
        t.View.assert_not_called()

    def test_unknown_format(t):
        t.conf.format = 'xml'

        with t.assertRaises(ValueError) as caught:
            get_view(t.conf, t.now, show_all=True)

        t.assertEqual(
            str(caught.exception),
            "unknown format 'xml'; choose one of text, json",
        )


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

    def test_digest(t):
        get_completed(t.conf, t.now, period='a period')
        # The configuration is decoded once, by the digest.
        t.Digest.from_config.assert_called_once_with(
            t.conf,
            t.now,
            period='a period',
        )

    def test_text(t):
        rendered = get_completed(t.conf, t.now, period='a period')
        t.DigestView.assert_called_once_with(t.digest)
        t.assertEqual(rendered, t.DigestView.return_value.text)

    @patch(f'{SRC}.DigestJsonView', autospec=True)
    def test_json(t, digest_json_view):
        t.conf.format = 'json'

        rendered = get_completed(t.conf, t.now, period='a period')

        digest_json_view.assert_called_once_with(t.digest)
        t.assertEqual(rendered, digest_json_view.return_value.json)
        # The JSON view serializes the digest; the text view is not built.
        t.DigestView.assert_not_called()

    def test_unknown_format(t):
        t.conf.format = 'xml'

        with t.assertRaises(ValueError) as caught:
            get_completed(t.conf, t.now, period='a period')

        t.assertEqual(
            str(caught.exception),
            "unknown format 'xml'; choose one of text, json",
        )


class GetItemTests(TestCase):
    """Unit tests for battodo.lib.get_item."""

    def setUp(t):
        patches = ['Item', 'ItemView']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.item = t.Item.from_config.return_value

        t.now = sentinel.now
        t.conf = Mock(spec=['format'])
        t.conf.format = 'text'

    def test_item(t):
        get_item(t.conf, t.now, selector='a selector')
        # The configuration is decoded once, by the item.
        t.Item.from_config.assert_called_once_with(
            t.conf,
            t.now,
            selector='a selector',
        )

    def test_text(t):
        rendered = get_item(t.conf, t.now, selector='a selector')
        t.ItemView.assert_called_once_with(t.item)
        t.assertEqual(rendered, t.ItemView.return_value.text)

    @patch(f'{SRC}.ItemJsonView', autospec=True)
    def test_json(t, item_json_view):
        t.conf.format = 'json'

        rendered = get_item(t.conf, t.now, selector='a selector')

        item_json_view.assert_called_once_with(t.item)
        t.assertEqual(rendered, item_json_view.return_value.json)
        # The JSON view serializes the item; the text view is not built.
        t.ItemView.assert_not_called()

    def test_unknown_format(t):
        t.conf.format = 'xml'

        with t.assertRaises(ValueError) as caught:
            get_item(t.conf, t.now, selector='a selector')

        t.assertEqual(
            str(caught.exception),
            "unknown format 'xml'; choose one of text, json",
        )


class GetHistoryTests(TestCase):
    """Unit tests for battodo.lib.get_history."""

    def setUp(t):
        patches = ['TaskHistory', 'HistoryView']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.history = t.TaskHistory.from_config.return_value

        t.now = sentinel.now
        t.conf = Mock(spec=['format'])
        t.conf.format = 'text'

    def test_history(t):
        get_history(t.conf, t.now, selector='a selector')
        # The configuration is decoded once, by the history.
        t.TaskHistory.from_config.assert_called_once_with(
            t.conf,
            t.now,
            selector='a selector',
        )

    def test_text(t):
        rendered = get_history(t.conf, t.now, selector='a selector')
        t.HistoryView.assert_called_once_with(t.history)
        t.assertEqual(rendered, t.HistoryView.return_value.text)

    @patch(f'{SRC}.HistoryJsonView', autospec=True)
    def test_json(t, history_json_view):
        t.conf.format = 'json'

        rendered = get_history(t.conf, t.now, selector='a selector')

        history_json_view.assert_called_once_with(t.history)
        t.assertEqual(rendered, history_json_view.return_value.json)
        # The JSON view serializes the history; the text view is not built.
        t.HistoryView.assert_not_called()

    def test_unknown_format(t):
        t.conf.format = 'xml'

        with t.assertRaises(ValueError) as caught:
            get_history(t.conf, t.now, selector='a selector')

        t.assertEqual(
            str(caught.exception),
            "unknown format 'xml'; choose one of text, json",
        )


class AddItemTests(TestCase):
    """Unit tests for battodo.lib.add_item."""

    def setUp(t):
        patches = ['Addition', 'SubtaskAddition', 'Task', 'SuppliedAttributes']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.addition = t.Addition.return_value
        t.addition.path = Path('~/a-source-dir/a-list.md')
        t.addition.entry = '- [ ] A task title [P:4] [ID:ab12cd]'

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.inputs = {
            'list_name': 'a-list',
            'title': 'A task title',
            'priority': '4',
            'loe': '2',
            'due': '2026-09-01',
            'repeat': '15d',
            'tags': 'yard,summer',
            'description': 'A description',
        }

    def test_forwarded(t):
        add_item(t.conf, t.now, **t.inputs)
        t.Addition.assert_called_once_with(
            SOURCE,
            'a-list',
            'A task title',
            {
                'P': '4',
                'LOE': '2',
                'DUE': '2026-09-01',
                'REPEAT': '15d',
                'TAGS': 'yard,summer',
            },
            t.today,
            description='A description',
            attrs=t.SuppliedAttributes.return_value.checked,
        )

    def test_attributes(t):
        with t.subTest('the attribute inputs are read'):
            add_item(
                t.conf,
                t.now,
                **t.inputs,
                attrs='cost=45.00',
                note='a note',
            )
            t.SuppliedAttributes.assert_called_once_with(
                'cost=45.00', 'a note'
            )

        with t.subTest('left off, both are None'):
            t.SuppliedAttributes.reset_mock()

            add_item(t.conf, t.now, **t.inputs)

            t.SuppliedAttributes.assert_called_once_with(None, None)

        with t.subTest('a refusal comes before the add is built'):
            t.Addition.reset_mock()
            t.SuppliedAttributes.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                add_item(t.conf, t.now, **t.inputs)

            t.Addition.assert_not_called()

    def test_written(t):
        add_item(t.conf, t.now, **t.inputs)
        t.addition.write.assert_called_once_with()

    def test_result(t):
        written = add_item(t.conf, t.now, **t.inputs)
        # A P-less add ranks near 0 and will not show in a view, so
        # this is the only confirmation of the write.
        t.assertEqual(written, f'{t.addition.entry}\n{t.addition.path}')

    def test_no_fields(t):
        add_item(t.conf, t.now, list_name='a-list', title='A task title')

        args, kwargs = t.Addition.call_args

        t.assertEqual(args[3], {})
        t.assertIsNone(kwargs['description'])

    def test_subtask(t):
        addition = t.SubtaskAddition.return_value
        addition.path = Path('~/a-source-dir/a-list.md')
        addition.entry = '  - [ ] A subtask title [LOE:2] [ID:cd34ef]'

        written = add_item(
            t.conf,
            t.now,
            list_name='a-list',
            title='A subtask title',
            parent='9o71lx',
            loe='2',
            description='A description',
        )

        with t.subTest('a parent sends the add to a subtask'):
            t.Addition.assert_not_called()
            t.SubtaskAddition.assert_called_once_with(
                t.Task.return_value,
                'a-list',
                'A subtask title',
                {'LOE': '2'},
                description='A description',
                attrs=t.SuppliedAttributes.return_value.checked,
            )

        with t.subTest('the parent is the task its selector names'):
            t.Task.assert_called_once_with(SOURCE, '9o71lx', t.today)

        with t.subTest('the subtask is written'):
            addition.write.assert_called_once_with()

        with t.subTest('the subtask line and its file come back'):
            t.assertEqual(written, f'{addition.entry}\n{addition.path}')


class UpdateItemTests(TestCase):
    """Unit tests for battodo.lib.update_item."""

    def setUp(t):
        patches = ['Update', 'Task', 'SuppliedAttributes']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.update = t.Update.return_value
        t.update.path = Path('~/a-source-dir/a-list.md')
        t.update.entry = '- [ ] A task title [P:4] [ID:ab12cd]'
        # An open task answers the selector.
        t.Task.return_value.selection = Mock(spec=['records'])
        t.Task.return_value.selection.records = [sentinel.record]

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'
        t.inputs = {
            'selector': 'a selector',
            'priority': '4',
            'due': '2026-09-01',
            'repeat': '14d',
            'title': 'A task title',
            'description': 'A description',
            'list_name': 'another-list',
            'with_subtasks': True,
        }

    def test_forwarded(t):
        update_item(t.conf, t.now, **t.inputs)

        t.Task.assert_called_once_with(SOURCE, 'a selector', t.today)
        t.Update.assert_called_once_with(
            t.Task.return_value,
            {'P': '4', 'DUE': '2026-09-01', 'REPEAT': '14d'},
            title='A task title',
            description='A description',
            attrs=t.SuppliedAttributes.return_value.checked,
            list_name='another-list',
            with_subtasks=True,
        )

    def test_attributes(t):
        with t.subTest('the attribute inputs are read'):
            update_item(
                t.conf,
                t.now,
                **t.inputs,
                attrs='cost=45.00',
                note='a note',
            )
            t.SuppliedAttributes.assert_called_once_with(
                'cost=45.00', 'a note'
            )

        with t.subTest('left off, both are None'):
            t.SuppliedAttributes.reset_mock()

            update_item(t.conf, t.now, **t.inputs)

            t.SuppliedAttributes.assert_called_once_with(None, None)

        with t.subTest('a refusal comes before the task is built'):
            t.Task.reset_mock()
            t.SuppliedAttributes.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                update_item(t.conf, t.now, **t.inputs)

            t.Task.assert_not_called()

    def test_written(t):
        update_item(t.conf, t.now, **t.inputs)
        t.update.write.assert_called_once_with()

    def test_result(t):
        written = update_item(t.conf, t.now, **t.inputs)
        t.assertEqual(written, f'{t.update.entry}\n{t.update.path}')

    @patch(f'{SRC}.Reopen', autospec=True)
    def test_closed(t, reopen):
        t.Task.return_value.selection.records = []
        reopen.return_value.path = Path('~/a-source-dir/a-list.md')
        reopen.return_value.entry = '- [ ] A task title [P:4] [ID:ab12cd]'

        ret = update_item(t.conf, t.now, **t.inputs)

        # No open task answers: the reopen of a closed one, in the zone
        # of the clock.
        t.Update.assert_not_called()
        reopen.assert_called_once_with(
            t.Task.return_value,
            t.now.tzinfo,
            {'P': '4', 'DUE': '2026-09-01', 'REPEAT': '14d'},
            title='A task title',
            description='A description',
            attrs=t.SuppliedAttributes.return_value.checked,
            list_name='another-list',
            with_subtasks=True,
        )
        reopen.return_value.write.assert_called_once_with()
        t.assertEqual(
            ret,
            f'{reopen.return_value.entry}\n{reopen.return_value.path}',
        )

    def test_option_left_off(t):
        update_item(
            t.conf,
            t.now,
            selector='a selector',
            tags='a-tag,another-tag',
        )

        # An option left off names no change to that field.
        args, kwargs = t.Update.call_args
        t.assertEqual(args[1], {'TAGS': 'a-tag,another-tag'})
        t.assertIsNone(kwargs['title'])
        t.assertIsNone(kwargs['description'])
        t.assertIsNone(kwargs['list_name'])
        t.assertFalse(kwargs['with_subtasks'])


class CompleteItemTests(TestCase):
    """Unit tests for battodo.lib.complete_item."""

    def setUp(t):
        patches = ['Task', 'Completion', 'SuppliedAttributes']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        # autospec builds `from_config` from its signature, so its
        # return value carries no spec. The instance mock does, so the
        # classmethod is pointed at that.
        t.task = t.Task.return_value
        t.Task.from_config.return_value = t.task
        t.completion = t.Completion.return_value
        t.completion.entries = []

        t.now = sentinel.now
        # The task decodes the configuration, so this call reads no
        # value off it.
        t.conf = Mock(spec=['view'])

    def test_result(t):
        # Completing the last open child completes its parent too, so
        # one call can log more than one entry.
        t.completion.entries = [
            '2026-08-08 | a-list | DONE | A parent > A child',
            '2026-08-08 | a-list | DONE | A parent',
        ]

        logged = complete_item(t.conf, t.now, selector='a selector')

        t.assertEqual(
            logged,
            '2026-08-08 | a-list | DONE | A parent > A child\n'
            '2026-08-08 | a-list | DONE | A parent',
        )

    def test_task(t):
        complete_item(t.conf, t.now, selector='a selector', date='a date')

        with t.subTest('the task decodes the configuration and the inputs'):
            t.Task.from_config.assert_called_once_with(
                t.conf,
                t.now,
                selector='a selector',
                date='a date',
            )

        with t.subTest('which the completion is built on'):
            t.Completion.assert_called_once_with(
                t.task,
                attrs=t.SuppliedAttributes.return_value.checked,
                scratched=False,
            )

        with t.subTest('a date left off is None'):
            t.Task.from_config.reset_mock()

            complete_item(t.conf, t.now, selector='a selector')

            t.Task.from_config.assert_called_once_with(
                t.conf,
                t.now,
                selector='a selector',
                date=None,
            )

        with t.subTest('a scratch closes the task without completing it'):
            t.Completion.reset_mock()

            complete_item(t.conf, t.now, selector='a selector', scratch=True)

            t.Completion.assert_called_once_with(
                t.task,
                attrs=t.SuppliedAttributes.return_value.checked,
                scratched=True,
            )

    def test_attributes(t):
        with t.subTest('the attribute inputs are read'):
            complete_item(
                t.conf,
                t.now,
                selector='a selector',
                attrs='cost=45.00',
                note='a note',
            )
            t.SuppliedAttributes.assert_called_once_with(
                'cost=45.00', 'a note'
            )

        with t.subTest('left off, both are None'):
            t.SuppliedAttributes.reset_mock()

            complete_item(t.conf, t.now, selector='a selector')

            t.SuppliedAttributes.assert_called_once_with(None, None)

        with t.subTest('a refusal comes before the task is built'):
            t.Task.from_config.reset_mock()
            t.SuppliedAttributes.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                complete_item(t.conf, t.now, selector='a selector')

            t.Task.from_config.assert_not_called()

    def test_written(t):
        complete_item(t.conf, t.now, selector='a selector')
        t.completion.write.assert_called_once_with()

    def test_nothing_logged(t):
        with t.subTest('a checklist item is checked off'):
            logged = complete_item(t.conf, t.now, selector='a selector')
            t.assertEqual(logged, 'checked off')

        with t.subTest('and a scratched one is dropped'):
            logged = complete_item(
                t.conf, t.now, selector='a selector', scratch=True
            )
            t.assertEqual(logged, 'dropped')


class AnnotateItemTests(TestCase):
    """Unit tests for battodo.lib.annotate_item."""

    def setUp(t):
        patches = ['Annotation', 'Task', 'SuppliedAttributes']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.annotation = t.Annotation.return_value
        t.annotation.path = Path('~/a-source-dir/a-list.md')
        t.annotation.entry = '- [ ] A task title [ID:ab12cd]'

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'

    def test_forwarded(t):
        annotate_item(t.conf, t.now, selector='a selector', text='a note')

        t.Task.assert_called_once_with(SOURCE, 'a selector', t.today)
        t.Annotation.assert_called_once_with(
            t.Task.return_value,
            t.SuppliedAttributes.return_value.checked,
        )

    def test_attributes(t):
        with t.subTest('the text enters as the note'):
            annotate_item(
                t.conf,
                t.now,
                selector='a selector',
                text='a note',
                attrs='cost=45.00',
            )
            t.SuppliedAttributes.assert_called_once_with(
                'cost=45.00', 'a note'
            )

        with t.subTest('left off, both are None'):
            t.SuppliedAttributes.reset_mock()
            annotate_item(t.conf, t.now, selector='a selector')
            t.SuppliedAttributes.assert_called_once_with(None, None)

        with t.subTest('a refusal comes before the task is built'):
            t.Task.reset_mock()
            t.SuppliedAttributes.side_effect = ValueError('refused')

            with t.assertRaises(ValueError):
                annotate_item(t.conf, t.now, selector='a selector')

            t.Task.assert_not_called()

    def test_written(t):
        annotate_item(t.conf, t.now, selector='a selector', text='a note')
        t.annotation.write.assert_called_once_with()

    def test_result(t):
        written = annotate_item(
            t.conf,
            t.now,
            selector='a selector',
            text='a note',
        )

        t.assertEqual(written, f'{t.annotation.entry}\n{t.annotation.path}')


class BackfillItemsTests(TestCase):
    """Unit tests for battodo.lib.backfill_items."""

    def setUp(t):
        patches = ['Backfill']
        for target in patches:
            patcher = patch(f'{SRC}.{target}', autospec=True)
            setattr(t, target, patcher.start())
            t.addCleanup(patcher.stop)
        t.backfill = t.Backfill.return_value
        t.backfill.lists = []

        t.now = Mock(spec=datetime)
        t.today = t.now.date.return_value
        t.conf = Mock(spec=['view'])
        t.conf.view = Mock(spec=['source_dir'])
        t.conf.view.source_dir = '~/a-source-dir'

    def test_result(t):
        t.backfill.lists = [
            stamped('a-list.md', 2),
            stamped('another-list.md', 1),
        ]

        ret = backfill_items(t.conf, t.now)

        # A count per changed list, in name order.
        t.assertEqual(ret, 'a-list.md: stamped 2\nanother-list.md: stamped 1')

    def test_forwarded(t):
        backfill_items(t.conf, t.now)
        t.Backfill.assert_called_once_with(SOURCE, t.today)

    def test_written(t):
        backfill_items(t.conf, t.now)
        t.backfill.write.assert_called_once_with()

    def test_nothing_stamped(t):
        ret = backfill_items(t.conf, t.now)
        t.assertEqual(ret, 'nothing to backfill')


def stamped(name: str, count: int) -> Mock:
    """A list backfill: its file, and the tasks it stamps."""
    backfill = Mock(spec=['path', 'tasks'])
    backfill.path = Path(name)
    backfill.tasks = [sentinel.task] * count
    return backfill
