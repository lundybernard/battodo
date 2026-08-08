from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ..journal import Journal
from ..mutate import (
    backfill_all,
    backfill_file,
    task_snapshot,
)
from ..parser import parse

LIST = """# Work

## Open

- [ ] No added [P:4]
- [ ] Legacy priority [P:95] [BUMPED:2026-08-08]
- [ ] Already added [P:3] [ADDED:2026-01-05]
- [ ] Placeholder [P:6] [DUE:YYYY-MM-DD]
- [x] Done [P:5]
  - [ ] Child is never stamped [LOE:2]

## Done
"""

TODAY = date(2026, 8, 8)


class TaskSnapshotTests(TestCase):
    def test_task_snapshot(t) -> None:
        task = parse('## Open\n\n- [ ] X [P:2] [TAGS:a]\n').tasks[0]
        t.assertEqual(
            task_snapshot(task),
            {
                'title': 'X',
                'done': False,
                'fields': {'P': '2', 'TAGS': 'a'},
            },
        )


class BackfillFileTests(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.path = t.dir / 'work.md'
        t.path.write_text(LIST)
        t.journal = Journal(t.dir)

    def test_backfill_file(t) -> None:
        stamped = backfill_file(t.path, TODAY, t.journal)
        text = t.path.read_text()

        with t.subTest('every open top-level task lacking ADDED'):
            t.assertEqual(sorted(stamped), ['Legacy priority', 'No added'])

        with t.subTest('the field is appended, nothing else moves'):
            t.assertIn('- [ ] No added [P:4] [ADDED:2026-08-08]', text)
            t.assertIn(
                '- [ ] Legacy priority [P:95] [BUMPED:2026-08-08] '
                '[ADDED:2026-08-08]',
                text,
            )

        with t.subTest('an existing ADDED is never overwritten'):
            t.assertIn('- [ ] Already added [P:3] [ADDED:2026-01-05]', text)

        with t.subTest('a line btodo cannot fully read is left alone'):
            # The trip-prep template carries literal [DUE:YYYY-MM-DD].
            t.assertIn('- [ ] Placeholder [P:6] [DUE:YYYY-MM-DD]\n', text)

        with t.subTest('completed and child tasks are not stamped'):
            t.assertIn('- [x] Done [P:5]', text)
            t.assertIn('  - [ ] Child is never stamped [LOE:2]', text)

        with t.subTest('ids injected lazily on first mediated mutation'):
            doc = parse(text)
            touched = [x for x in doc.tasks if x.title in stamped]
            t.assertTrue(all(x.task_id for x in touched))
            untouched = next(x for x in doc.tasks if x.title == 'Placeholder')
            t.assertIsNone(untouched.task_id)

        with t.subTest('unrelated lines preserved'):
            t.assertTrue(text.startswith('# Work\n'))
            t.assertTrue(text.endswith('## Done\n'))

    def test_backfill_file_journal(t) -> None:
        backfill_file(t.path, TODAY, t.journal)
        events = t.journal.read()

        with t.subTest('one event per stamped task'):
            t.assertEqual(len(events), 2)
            t.assertEqual({e['type'] for e in events}, {'TaskAdded'})

        with t.subTest('payload carries delta, snapshot, and the caveat'):
            event = next(
                e
                for e in events
                if e['payload']['snapshot']['title'] == 'No added'
            )
            t.assertEqual(
                event['payload']['delta']['ADDED'], [None, '2026-08-08']
            )
            t.assertEqual(event['payload']['snapshot']['fields']['P'], '4')
            t.assertTrue(event['payload']['backfilled'])

        with t.subTest('stream id uses the injected task id'):
            t.assertTrue(events[0]['stream_id'].startswith('task/'))

        with t.subTest('metadata names the source file'):
            t.assertEqual(events[0]['metadata']['source_file'], 'work.md')

    def test_backfill_file_runs_once(t) -> None:
        backfill_file(t.path, TODAY, t.journal)
        first = t.path.read_text()
        t.assertEqual(backfill_file(t.path, TODAY, t.journal), [])
        t.assertEqual(t.path.read_text(), first)

    def test_backfill_file_unchanged_file_not_rewritten(t) -> None:
        path = t.dir / 'empty.md'
        path.write_text('## Open\n\n- [x] Done [P:1]\n')
        before = path.read_text()
        t.assertEqual(backfill_file(path, TODAY, t.journal), [])
        t.assertEqual(path.read_text(), before)


class BackfillAllTests(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)

    def test_backfill_all(t) -> None:
        (t.dir / 'work.md').write_text('## Open\n\n- [ ] W [P:1]\n')
        (t.dir / 'backlog.md').write_text(
            '<!-- battodo:parked -->\n\n## Open\n\n- [ ] B [P:1]\n'
        )
        (t.dir / 'SCHEMA.md').write_text('# Schema\n\nprose\n')

        result = backfill_all(t.dir, TODAY)

        with t.subTest('covers every discovered list, parked ones included'):
            t.assertEqual(result, {'backlog.md': ['B'], 'work.md': ['W']})

        with t.subTest('non-list markdown untouched'):
            t.assertEqual(
                (t.dir / 'SCHEMA.md').read_text(), '# Schema\n\nprose\n'
            )

        with t.subTest('journal written to the source directory'):
            t.assertEqual(len(Journal(t.dir).read()), 2)

        with t.subTest('a second run is a no-op'):
            t.assertEqual(backfill_all(t.dir, TODAY), {})
