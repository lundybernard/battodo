from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ..journal import Journal
from ..mutate import (
    bump_all,
    bump_file,
    task_snapshot,
)
from ..parser import parse

LIST = """# Work

## Open

- [ ] No due [P:4]
- [ ] Overdue [P:2] [DUE:2026-01-01]
- [ ] Already bumped [P:7] [BUMPED:2026-08-08]
- [ ] Bumped earlier [P:7] [BUMPED:2026-08-01]
- [ ] Future [P:1] [DUE:2999-01-01]
- [x] Done [P:5]
  - [ ] Child should not bump [LOE:2]

## Done
"""

TODAY = date(2026, 8, 8)


class TestTaskSnapshot(TestCase):
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


class TestBumpFile(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.path = t.dir / 'work.md'
        t.path.write_text(LIST)
        t.journal = Journal(t.dir)

    def test_bump_file(t) -> None:
        bumped = bump_file(t.path, TODAY, t.journal)
        text = t.path.read_text()

        with t.subTest('eligible items bumped'):
            t.assertEqual(
                sorted(bumped), ['Bumped earlier', 'No due', 'Overdue']
            )

        with t.subTest('priority incremented and BUMPED stamped'):
            t.assertIn('- [ ] No due [P:5] [BUMPED:2026-08-08]', text)
            t.assertIn('[P:3] [DUE:2026-01-01] [BUMPED:2026-08-08]', text)

        with t.subTest('existing BUMPED replaced in place'):
            t.assertIn('- [ ] Bumped earlier [P:8] [BUMPED:2026-08-08]', text)

        with t.subTest('already bumped today untouched'):
            t.assertIn('- [ ] Already bumped [P:7] [BUMPED:2026-08-08]', text)

        with t.subTest('future-dated not bumped'):
            t.assertIn('- [ ] Future [P:1] [DUE:2999-01-01]', text)

        with t.subTest('completed not bumped'):
            t.assertIn('- [x] Done [P:5]', text)

        with t.subTest('children never bump'):
            t.assertIn('  - [ ] Child should not bump [LOE:2]', text)

        with t.subTest('ids injected lazily on first mediated mutation'):
            doc = parse(text)
            touched = [x for x in doc.tasks if x.title in bumped]
            t.assertTrue(all(x.task_id for x in touched))
            untouched = next(x for x in doc.tasks if x.title == 'Future')
            t.assertIsNone(untouched.task_id)

        with t.subTest('unrelated lines preserved'):
            t.assertTrue(text.startswith('# Work\n'))
            t.assertTrue(text.endswith('## Done\n'))

    def test_bump_file_journal(t) -> None:
        bump_file(t.path, TODAY, t.journal)
        events = t.journal.read()

        with t.subTest('one event per bumped task'):
            t.assertEqual(len(events), 3)
            t.assertEqual({e['type'] for e in events}, {'TaskBumped'})

        with t.subTest('payload carries delta and snapshot'):
            event = next(
                e
                for e in events
                if e['payload']['snapshot']['title'] == 'No due'
            )
            t.assertEqual(event['payload']['delta']['P'], [4, 5])
            t.assertEqual(
                event['payload']['delta']['BUMPED'], [None, '2026-08-08']
            )
            t.assertEqual(event['payload']['snapshot']['fields']['P'], '4')

        with t.subTest('stream id uses the injected task id'):
            t.assertTrue(events[0]['stream_id'].startswith('task/'))

        with t.subTest('metadata names the source file'):
            t.assertEqual(events[0]['metadata']['source_file'], 'work.md')

    def test_bump_file_idempotent_per_day(t) -> None:
        bump_file(t.path, TODAY, t.journal)
        first = t.path.read_text()
        t.assertEqual(bump_file(t.path, TODAY, t.journal), [])
        t.assertEqual(t.path.read_text(), first)

    def test_bump_file_unchanged_file_not_rewritten(t) -> None:
        path = t.dir / 'empty.md'
        path.write_text('## Open\n\n- [x] Done [P:1]\n')
        before = path.read_text()
        t.assertEqual(bump_file(path, TODAY, t.journal), [])
        t.assertEqual(path.read_text(), before)


class TestBumpAll(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)

    def test_bump_all(t) -> None:
        (t.dir / 'work.md').write_text('## Open\n\n- [ ] W [P:1]\n')
        (t.dir / 'backlog.md').write_text('## Open\n\n- [ ] B [P:1]\n')
        (t.dir / 'SCHEMA.md').write_text('# Schema\n\nprose\n')

        result = bump_all(t.dir, TODAY)

        with t.subTest('covers ad-hoc lists, fixing the hard-coded bug'):
            t.assertEqual(result, {'backlog.md': ['B'], 'work.md': ['W']})

        with t.subTest('non-list markdown untouched'):
            t.assertEqual(
                (t.dir / 'SCHEMA.md').read_text(), '# Schema\n\nprose\n'
            )

        with t.subTest('journal written to the source directory'):
            t.assertEqual(len(Journal(t.dir).read()), 2)

        with t.subTest('files with nothing to bump are omitted'):
            t.assertEqual(bump_all(t.dir, TODAY), {})
