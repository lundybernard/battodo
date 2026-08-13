import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipIf

from ..journal import Journal
from ..mutate import (
    ListError,
    SelectionError,
    add_task,
    backfill_all,
    backfill_file,
    complete,
    find_task,
    scratch,
    task_snapshot,
)
from ..parser import parse
from ..repeat import RepeatError

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


# Shapes taken from the live lists: legacy inflated P, retired BUMPED,
# 6-space notes beside 2-space subtasks, a fieldless checklist, an
# em-dash title, blank-separated blocks in one file and none in another,
# and a template carrying a literal date placeholder.
WORK = """# Work

<!-- Active: Mon–Fri 09:00–17:00 | Blocked by: chores -->

## Open

- [ ] Casablanca — continue implementation [P:95] [BUMPED:2026-08-08] \
[LOE:8] [TAGS:casablanca,rabbitmq] [ADDED:2026-07-01] [ID:9o71lx]
      RabbitMQ client, partly built. Lots of tests still to implement.

- [ ] Trip prep [P:12] [LOE:8] [ADDED:2026-07-01] [ID:tr1p00]
  - [ ] Prepare computer bag [LOE:1]
    - [x] Charger
    - [ ] Power supply
  - [ ] Book hotel [LOE:2]
  - [ ] Pack cooler [LOE:1]
    - [ ] Ice packs
    - [ ] Water bottles
  - [x] Pack tools [LOE:2]

- [ ] Ship the docs [P:33] [DUE:2026-07-27] [LOE:1] [ADDED:2026-07-01] \
[ID:sf41tf]

- [ ] Captain's log [P:66] [DUE:2026-08-07] [REPEAT:weekly:fri] [LOE:2] \
[TAGS:career] [ADDED:2026-07-01] [ID:cpt007]
      Scan GitHub activity, then draft the entries.
  - [ ] Draft entries [LOE:1]

## Done
"""

CHORES = """# Chores

## Open

- [ ] Pay credit cards [P:83] [BUMPED:2026-08-08] [DUE:2026-06-24] \
[REPEAT:15d] [LOE:1] [TAGS:finance] [ADDED:2026-07-01] [ID:sn75q7]
- [ ] Build workbench [P:64] [BUMPED:2026-08-08] [LOE:5] \
[TAGS:home,build,workshop] [ADDED:2026-07-01] [ID:vrr7m8]
  - [x] Build plan + material cost estimate [LOE:2]
  - [ ] Buy lumber [LOE:2]
- [ ] Chip the brush pile [P:89] [BUMPED:2026-08-08] [LOE:3] [TAGS:yard] \
[ADDED:2026-07-01] [ID:zwyx7b]
- [ ] Water the plants [P:5] [REPEAT:sometimes] [ADDED:2026-07-01] \
[ID:wtr001]

## Done
"""

TEMPLATE = """# Van trip prep

## Open

- [ ] Reserve campsite [P:4] [DUE:YYYY-MM-DD] [LOE:2]
"""

COMPLETED = """# Completed Tasks

<!-- Append-only log. Never edit or delete entries. -->
2026-07-27 | chores | DONE | Build workbench > Build plan [LOE:2]
"""


def write_lists(directory: Path) -> None:
    (directory / 'work.md').write_text(WORK)
    (directory / 'chores.md').write_text(CHORES)
    (directory / 'van-trip-prep-template.md').write_text(TEMPLATE)
    (directory / 'completed.md').write_text(COMPLETED)


class FindTaskTests(TestCase):
    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        write_lists(t.dir)

    def test_find_task(t) -> None:
        with t.subTest('by [ID:]'):
            match = find_task(t.dir, 'sn75q7')
            t.assertEqual(match.task.title, 'Pay credit cards')
            t.assertEqual(match.path.name, 'chores.md')

        with t.subTest('by part of a title, case-insensitively'):
            t.assertEqual(
                find_task(t.dir, 'brush PILE').task.title,
                'Chip the brush pile',
            )

        with t.subTest('a subtask, which has no id to be found by'):
            match = find_task(t.dir, 'Power supply')
            t.assertEqual(
                [task.title for task in match.trail],
                ['Trip prep', 'Prepare computer bag', 'Power supply'],
            )

        with (
            t.subTest('checked tasks are not candidates'),
            t.assertRaises(SelectionError),
        ):
            find_task(t.dir, 'Pack tools')

        with t.subTest('an [ID:] wins over a title that mentions it'):
            (t.dir / 'extra.md').write_text(
                '## Open\n\n- [ ] Chase invoice zz01ab [P:1]\n'
                '- [ ] File taxes [P:2] [ID:zz01ab]\n'
            )
            t.assertEqual(find_task(t.dir, 'zz01ab').task.title, 'File taxes')


class MutationTests(TestCase):
    """A fixture source directory the mutation suites share."""

    def setUp(t) -> None:
        t.tmp = TemporaryDirectory()
        t.addCleanup(t.tmp.cleanup)
        t.dir = Path(t.tmp.name)
        t.reset()

    def reset(t) -> None:
        """Fresh lists and an empty journal, for the next subTest."""
        write_lists(t.dir)
        (t.dir / '.journal' / 'log.jsonl').unlink(missing_ok=True)

    def logged(t) -> list[str]:
        """The completed.md entries this run appended."""
        text = (t.dir / 'completed.md').read_text()
        return text[len(COMPLETED) :].splitlines()

    def line(t, name: str, needle: str) -> str:
        return next(
            line
            for line in (t.dir / name).read_text().split('\n')
            if needle in line
        )


class CompleteTests(MutationTests):
    def test_complete(t) -> None:
        with t.subTest('a finished top-level task loses its whole block'):
            complete(t.dir, 'Chip the brush pile', TODAY)
            text = (t.dir / 'chores.md').read_text()
            t.assertNotIn('Chip the brush pile', text)
            t.assertIn('- [ ] Water the plants', text)

        with t.subTest('untouched lines survive byte-identically'):
            t.reset()
            complete(t.dir, 'Casablanca', TODAY)
            kept = [
                line
                for index, line in enumerate(WORK.split('\n'))
                # the task, its note, and the blank the removal orphans
                if index not in {6, 7, 8}
            ]
            t.assertEqual((t.dir / 'work.md').read_text(), '\n'.join(kept))

        with t.subTest('completing the last open child empties the block'):
            t.reset()
            complete(t.dir, 'Buy lumber', TODAY)
            text = (t.dir / 'chores.md').read_text()
            t.assertNotIn('Build workbench', text)
            t.assertNotIn('Buy lumber', text)
            t.assertIn('- [ ] Chip the brush pile', text)

        with t.subTest('a cascade that stops checks lines off in place'):
            t.reset()
            complete(t.dir, 'Power supply', TODAY)
            lines = (t.dir / 'work.md').read_text().split('\n')
            t.assertIn('    - [x] Power supply', lines)
            t.assertRegex(
                t.line('work.md', 'Prepare computer bag'),
                r'^  - \[x\] Prepare computer bag \[LOE:1\] \[ID:\w{6}\]$',
            )
            t.assertIn('  - [ ] Book hotel [LOE:2]', lines)
            t.assertIn(
                '- [ ] Trip prep [P:12] [LOE:8] [ADDED:2026-07-01] '
                '[ID:tr1p00]',
                lines,
            )

        with t.subTest('a checklist item alone gets no [ID:], its owner does'):
            t.reset()
            complete(t.dir, 'Ice packs', TODAY)
            lines = (t.dir / 'work.md').read_text().split('\n')
            t.assertIn('    - [x] Ice packs', lines)
            t.assertIn('    - [ ] Water bottles', lines)
            t.assertRegex(
                t.line('work.md', 'Pack cooler'),
                r'^  - \[ \] Pack cooler \[LOE:1\] \[ID:\w{6}\]$',
            )

        with t.subTest('a recurring task is rescheduled, not removed'):
            t.reset()
            complete(t.dir, 'Pay credit cards', TODAY)
            t.assertEqual(
                t.line('chores.md', 'Pay credit cards'),
                '- [ ] Pay credit cards [P:83] [BUMPED:2026-08-08] '
                '[DUE:2026-08-23] [REPEAT:15d] [LOE:1] [TAGS:finance] '
                '[ADDED:2026-07-01] [ID:sn75q7]',
            )

        with t.subTest('a parent completed early takes its children along'):
            t.reset()
            t.assertEqual(
                complete(t.dir, 'Trip prep', TODAY),
                ['2026-08-08 | work | DONE | Trip prep [P:12] [LOE:8]'],
            )
            text = (t.dir / 'work.md').read_text()
            # SCHEMA.md removes the block, parent and all; the open
            # children go with it and are not logged individually.
            t.assertNotIn('Trip prep', text)
            t.assertNotIn('Book hotel', text)

        with t.subTest('a recurrence keeps its notes, drops its children'):
            t.reset()
            complete(t.dir, "Captain's log", TODAY)
            text = (t.dir / 'work.md').read_text()
            t.assertIn('[DUE:2026-08-14] [REPEAT:weekly:fri]', text)
            t.assertIn('      Scan GitHub activity, then draft', text)
            t.assertNotIn('Draft entries', text)

    def test_complete_log(t) -> None:
        with t.subTest('date, category, status, title, and fields'):
            t.assertEqual(
                complete(t.dir, 'Chip the brush pile', TODAY),
                [
                    (
                        '2026-08-08 | chores | DONE | Chip the brush pile '
                        '[P:89] [LOE:3] [TAGS:yard]'
                    )
                ],
            )
            t.assertEqual(len(t.logged()), 1)

        with t.subTest('a recurrence logs the DUE it was completed against'):
            t.reset()
            t.assertEqual(
                t.logged(),
                [],
            )
            complete(t.dir, 'Pay credit cards', TODAY)
            t.assertEqual(
                t.logged(),
                [
                    (
                        '2026-08-08 | chores | DONE | Pay credit cards '
                        '[P:83] [LOE:1] [DUE:2026-06-24] [REPEAT:15d] '
                        '[TAGS:finance]'
                    )
                ],
            )

        with t.subTest('ancestry with a line per completion, deepest first'):
            t.reset()
            complete(t.dir, 'Buy lumber', TODAY)
            t.assertEqual(
                t.logged(),
                [
                    (
                        '2026-08-08 | chores | DONE | Build workbench > '
                        'Buy lumber [LOE:2]'
                    ),
                    (
                        '2026-08-08 | chores | DONE | Build workbench '
                        '[P:64] [LOE:5] [TAGS:home,build,workshop]'
                    ),
                ],
            )

        with t.subTest('checklist items are not logged, their parent is'):
            t.reset()
            t.assertEqual(
                complete(t.dir, 'Power supply', TODAY),
                [
                    (
                        '2026-08-08 | work | DONE | Trip prep > '
                        'Prepare computer bag [LOE:1]'
                    )
                ],
            )

        with t.subTest('a checklist item that finishes nothing logs nothing'):
            t.reset()
            t.assertEqual(complete(t.dir, 'Ice packs', TODAY), [])
            t.assertEqual((t.dir / 'completed.md').read_text(), COMPLETED)

        with t.subTest('appended to a log that has no trailing newline'):
            t.reset()
            (t.dir / 'completed.md').write_text(COMPLETED.rstrip('\n'))
            complete(t.dir, 'Chip the brush pile', TODAY)
            text = (t.dir / 'completed.md').read_text()
            t.assertTrue(text.startswith(COMPLETED))
            t.assertTrue(text.endswith('[TAGS:yard]\n'))

        with t.subTest('created when there is no log yet'):
            t.reset()
            (t.dir / 'completed.md').unlink()
            complete(t.dir, 'Chip the brush pile', TODAY)
            t.assertTrue(
                (t.dir / 'completed.md')
                .read_text()
                .startswith('2026-08-08 | chores | DONE |')
            )

    def test_complete_journal(t) -> None:
        with t.subTest('one TaskCompleted per completion, deepest first'):
            complete(t.dir, 'Buy lumber', TODAY)
            events = Journal(t.dir).read()
            t.assertEqual([e['type'] for e in events], ['TaskCompleted'] * 2)
            t.assertEqual(
                [e['payload']['ancestry'] for e in events],
                ['Build workbench > Buy lumber', 'Build workbench'],
            )
            t.assertEqual(events[1]['stream_id'], 'task/vrr7m8')
            t.assertEqual(
                events[0]['metadata'],
                {'actor': 'agent', 'source_file': 'chores.md'},
            )

        with t.subTest('delta and pre-state snapshot'):
            t.assertEqual(
                Journal(t.dir).read()[0]['payload'],
                {
                    'delta': {'done': [False, True]},
                    'snapshot': {
                        'title': 'Buy lumber',
                        'done': False,
                        'fields': {'LOE': '2'},
                    },
                    'ancestry': 'Build workbench > Buy lumber',
                },
            )

        with t.subTest('a reschedule records the due date it moved to'):
            t.reset()
            complete(t.dir, 'Pay credit cards', TODAY)
            t.assertEqual(
                Journal(t.dir).read()[0]['payload']['delta'],
                {'done': [False, True], 'DUE': ['2026-06-24', '2026-08-23']},
            )

        with t.subTest('a checklist item records on its parent stream'):
            t.reset()
            complete(t.dir, 'Power supply', TODAY)
            events = Journal(t.dir).read()
            streams = {e['stream_id'] for e in events}
            t.assertEqual(len(streams), 1)
            t.assertIn(
                streams.pop().removeprefix('task/'),
                t.line('work.md', 'Prepare computer bag'),
            )

    def test_complete_errors(t) -> None:
        before = (t.dir / 'chores.md').read_text()

        with t.subTest('nothing matches'):
            with t.assertRaises(SelectionError) as caught:
                complete(t.dir, 'nonexistent', TODAY)
            t.assertIn("'nonexistent'", str(caught.exception))

        with t.subTest('several tasks match'):
            with t.assertRaises(SelectionError) as caught:
                complete(t.dir, 'the', TODAY)
            t.assertIn('matches 3 open tasks', str(caught.exception))

        with t.subTest(
            'an unreadable REPEAT stops before anything is written'
        ):
            with t.assertRaises(RepeatError):
                complete(t.dir, 'Water the plants', TODAY)
            t.assertEqual((t.dir / 'chores.md').read_text(), before)
            t.assertEqual((t.dir / 'completed.md').read_text(), COMPLETED)
            t.assertEqual(Journal(t.dir).read(), [])


class ScratchTests(MutationTests):
    def test_scratch(t) -> None:
        with t.subTest('the block goes, untouched lines byte-identically'):
            scratch(t.dir, 'Casablanca', TODAY)
            kept = [
                line
                for index, line in enumerate(WORK.split('\n'))
                if index not in {6, 7, 8}
            ]
            t.assertEqual((t.dir / 'work.md').read_text(), '\n'.join(kept))

        with t.subTest('a subtask goes without touching its parent'):
            t.reset()
            scratch(t.dir, 'Book hotel', TODAY)
            text = (t.dir / 'work.md').read_text()
            t.assertNotIn('Book hotel', text)
            t.assertIn(
                '- [ ] Trip prep [P:12] [LOE:8] [ADDED:2026-07-01] '
                '[ID:tr1p00]',
                text,
            )
            t.assertIn('  - [ ] Prepare computer bag [LOE:1]\n', text)

        with t.subTest('a checklist item goes, its owner gains an [ID:]'):
            t.reset()
            scratch(t.dir, 'Ice packs', TODAY)
            text = (t.dir / 'work.md').read_text()
            t.assertNotIn('Ice packs', text)
            t.assertIn('    - [ ] Water bottles', text)
            t.assertRegex(
                t.line('work.md', 'Pack cooler'),
                r'^  - \[ \] Pack cooler \[LOE:1\] \[ID:\w{6}\]$',
            )

        with t.subTest('a recurring task is abandoned, not rescheduled'):
            t.reset()
            scratch(t.dir, 'Pay credit cards', TODAY)
            t.assertNotIn(
                'Pay credit cards', (t.dir / 'chores.md').read_text()
            )

    def test_scratch_log(t) -> None:
        with t.subTest('one SCRATCHED entry, with ancestry and fields'):
            t.assertEqual(
                scratch(t.dir, 'Book hotel', TODAY),
                [
                    (
                        '2026-08-08 | work | SCRATCHED | Trip prep > '
                        'Book hotel [LOE:2]'
                    )
                ],
            )
            t.assertEqual(len(t.logged()), 1)

        with t.subTest('checklist items are not logged'):
            t.reset()
            t.assertEqual(scratch(t.dir, 'Ice packs', TODAY), [])
            t.assertEqual((t.dir / 'completed.md').read_text(), COMPLETED)

    def test_scratch_journal(t) -> None:
        with t.subTest('TaskScratched on the task, no cascade'):
            scratch(t.dir, 'Casablanca', TODAY)
            events = Journal(t.dir).read()
            t.assertEqual(len(events), 1)
            t.assertEqual(events[0]['type'], 'TaskScratched')
            t.assertEqual(events[0]['stream_id'], 'task/9o71lx')
            t.assertEqual(
                events[0]['metadata'],
                {'actor': 'agent', 'source_file': 'work.md'},
            )
            t.assertEqual(
                events[0]['payload']['delta'], {'removed': [False, True]}
            )

        with t.subTest('ancestry and pre-state snapshot'):
            t.reset()
            scratch(t.dir, 'Book hotel', TODAY)
            payload = Journal(t.dir).read()[0]['payload']
            t.assertEqual(payload['ancestry'], 'Trip prep > Book hotel')
            t.assertEqual(
                payload['snapshot'],
                {
                    'title': 'Book hotel',
                    'done': False,
                    'fields': {'LOE': '2'},
                },
            )

        with t.subTest('a checklist item records on its parent stream'):
            t.reset()
            scratch(t.dir, 'Ice packs', TODAY)
            stream = Journal(t.dir).read()[0]['stream_id']
            t.assertIn(
                stream.removeprefix('task/'), t.line('work.md', 'Pack cooler')
            )


class AddTaskTests(MutationTests):
    def task_id(t, line: str) -> str:
        return parse(f'## Open\n{line}\n').tasks[0].fields['ID']

    def test_add_task(t) -> None:
        with t.subTest('only supplied fields, plus the stamps btodo owns'):
            path, line = add_task(
                t.dir, 'chores', 'Water it', {'P': '4'}, TODAY
            )
            t.assertEqual(path, t.dir / 'chores.md')
            t.assertRegex(
                line,
                r'^- \[ \] Water it \[P:4\] \[ADDED:2026-08-08\] '
                r'\[ID:\w{6}\]$',
            )

        with t.subTest('appended to Open, every other line byte-identical'):
            expected = CHORES.split('\n')
            expected.insert(expected.index('## Done') - 1, line)
            t.assertEqual(path.read_text(), '\n'.join(expected))

        with t.subTest('fields are written in SCHEMA.md order'):
            t.reset()
            _, line = add_task(
                t.dir,
                'chores',
                'Water it',
                {
                    'TAGS': 'yard,summer',
                    'DUE': '2026-09-01',
                    'P': '4',
                    'REPEAT': '15d',
                    'LOE': '2',
                },
                TODAY,
            )
            t.assertRegex(
                line,
                r'^- \[ \] Water it \[P:4\] \[LOE:2\] \[DUE:2026-09-01\] '
                r'\[REPEAT:15d\] \[TAGS:yard,summer\] \[ADDED:2026-08-08\] '
                r'\[ID:\w{6}\]$',
            )

        with t.subTest('a list ending on its Open section keeps its newline'):
            t.reset()
            path, line = add_task(
                t.dir, 'van-trip-prep-template', 'X', {}, TODAY
            )
            expected = TEMPLATE.split('\n')
            expected.insert(-1, line)
            t.assertEqual(path.read_text(), '\n'.join(expected))

        with t.subTest('a parked list is a valid target'):
            t.reset()
            (t.dir / 'backlog.md').write_text(
                '<!-- battodo:parked -->\n\n## Open\n\n- [ ] B [P:1]\n'
            )
            path, line = add_task(t.dir, 'backlog', 'Someday', {}, TODAY)
            t.assertIn(line, path.read_text())

    def test_add_task_journal(t) -> None:
        _, line = add_task(
            t.dir,
            'chores',
            'Water it',
            {'P': '4', 'DUE': '2026-09-01'},
            TODAY,
        )
        task_id = t.task_id(line)
        (event,) = Journal(t.dir).read()

        with t.subTest('one TaskAdded on the new task stream'):
            t.assertEqual(event['type'], 'TaskAdded')
            t.assertEqual(event['stream_id'], f'task/{task_id}')
            t.assertEqual(
                event['metadata'],
                {'actor': 'agent', 'source_file': 'chores.md'},
            )

        with t.subTest('every written field, against nothing'):
            fields = {
                'P': '4',
                'DUE': '2026-09-01',
                'ADDED': '2026-08-08',
                'ID': task_id,
            }
            t.assertEqual(
                event['payload'],
                {
                    'delta': {
                        name: [None, value] for name, value in fields.items()
                    },
                    'snapshot': {
                        'title': 'Water it',
                        'done': False,
                        'fields': fields,
                    },
                },
            )

    @skipIf(
        sys.version_info < (3, 11),
        'before 3.11 fromisoformat reads only the canonical spelling',
    )
    def test_add_task_normalises_the_due_date(t) -> None:
        """A line must not record which interpreter wrote it.

        `date.fromisoformat` accepts more spellings on newer versions,
        so what the user typed is re-rendered rather than passed on.
        """
        _, line = add_task(t.dir, 'chores', 'X', {'DUE': '20260901'}, TODAY)

        t.assertIn('[DUE:2026-09-01]', line)
        t.assertIn(line, (t.dir / 'chores.md').read_text())

    def test_add_task_errors(t) -> None:
        with t.subTest('an unknown list names the directory and the stems'):
            with t.assertRaises(ListError) as caught:
                add_task(t.dir, 'wrk', 'X', {}, TODAY)
            message = str(caught.exception)
            t.assertIn(str(t.dir), message)
            t.assertIn(
                'available: chores, van-trip-prep-template, work', message
            )
            t.assertFalse((t.dir / 'wrk.md').exists())

        # Each message must name the field, the rule it broke, and the
        # value that broke it: the fix is always a re-typed argument.
        bad = (
            ({'DUE': 'tomorrow'}, r"DUE must be an ISO date, not 'tomorrow'"),
            ({'REPEAT': 'sometimes'}, r"REPEAT value: 'sometimes'"),
            ({'LOE': '4'}, r"LOE must be one of 1, 2, 3, 5, 8, not '4'"),
            ({'P': 'high'}, r"P must be a whole number, not 'high'"),
        )
        for fields, expected in bad:
            name = next(iter(fields))
            with (
                t.subTest(f'{name} is rejected'),
                t.assertRaisesRegex(ValueError, expected),
            ):
                add_task(t.dir, 'chores', 'X', fields, TODAY)

        with t.subTest('a rejected add writes nothing at all'):
            t.assertEqual((t.dir / 'chores.md').read_text(), CHORES)
            t.assertEqual(Journal(t.dir).read(), [])
