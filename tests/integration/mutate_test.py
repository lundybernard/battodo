"""Contract tests for the write objects, against real files.

Inputs are real directories holding real todo lists. Each object
derives the list text, the log entries and the journal events from
them, and this layer asserts those values. Interaction checks stay in
the isolation tests beside the code.
"""

from datetime import date
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.journal import Journal
from battodo.mutate import (
    Addition,
    Annotation,
    Backfill,
    Changeset,
    CompletedLog,
    Completion,
    Event,
    ListError,
    Scratch,
    SubtaskAddition,
    Update,
)
from battodo.repeat import RepeatError
from battodo.selector import SelectionError
from battodo.task import Task

TODAY = date(2026, 8, 8)
# A completion day the user gives, earlier than TODAY.
GIVEN_DAY = date(2026, 8, 1)
# A list holding every case the writes tell apart. The titles name the
# role each line plays.
A_LIST = """# A list

## Open

- [ ] A task [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]
      A note that stays put.
  - [ ] A subtask of it [LOE:2]
  - [ ] A checklist item
- [ ] A task with no id [P:2]
- [ ] A recurring task [P:3] [DUE:2026-08-05] [REPEAT:7d] [ID:rr01ab]
  - [ ] A subtask that does not recur [LOE:1]

- [ ] A task between blank lines [P:1] [ID:bb01cd]

## Done
"""
A_TASK = '- [ ] A task [P:4] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx]'
A_CHILD = '  - [ ] A subtask of it [LOE:2]'
NO_ID_TASK = '- [ ] A task with no id [P:2]'
RENAMED_TASK = (
    '- [ ] A renamed task [P:5] [LOE:8] [ADDED:2026-07-06] [ID:9o71lx] '
    '[DUE:2026-09-01]'
)
# A description, and its lines as a top-level task carries them.
DESCRIPTION = 'A first line.\n  A second line.'
DESCRIPTION_LINES = ['      A first line.', '      A second line.']
# A recurring task with a description line and a child, before and
# after its completion on TODAY.
DESCRIBED_RECURRENCE = (
    '## Open\n'
    '- [ ] A described recurring task [DUE:2026-08-05] [REPEAT:7d] '
    '[ID:dr01ab]\n'
    '      A description line.\n'
    '  - [ ] A subtask that does not recur [LOE:1]\n'
)
RESCHEDULED_RECURRENCE = (
    '## Open\n'
    '- [ ] A described recurring task [DUE:2026-08-15] [REPEAT:7d] '
    '[ID:dr01ab]\n'
    '      A description line.\n'
)
# The attributes of a note.
A_NOTE = {'note': 'Waiting on the vendor'}
# A second list, its open section empty.
ANOTHER_LIST = '# Another list\n\n## Open\n'
# A list whose one task carries an `[ID:]` with nothing in it.
EMPTY_ID_TASK = '- [ ] A task with an empty id [P:2] [ID:]'
EMPTY_ID_LIST = f'## Open\n\n{EMPTY_ID_TASK}\n'
# A list whose task has no id and two checklist items, so a write to one
# item leaves the task in the list. The titles name the role each line
# plays.
OWNER_LIST = (
    '## Open\n\n- [ ] A checklist owner with no id [P:3]\n'
    '  - [ ] A checklist item to write\n'
    '  - [ ] A checklist item that stays open\n'
)
# The owner as the file states it before a write.
OWNER_SNAPSHOT = {
    'title': 'A checklist owner with no id',
    'done': False,
    'fields': {'P': '3'},
}


class AdditionTests(TestCase):
    """Contract tests for battodo.mutate.Addition."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.ad = Addition(
            t.source,
            'a-list',
            'A new task',
            {'TAGS': 'a-tag', 'P': '3'},
            TODAY,
        )

    def test_write(t) -> None:
        t.ad.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the add derives, the journal its event.
        t.assertEqual(written, t.ad.text)
        t.assertEqual(journaled(t.source), as_journaled(t.ad.events))

    def test_path(t) -> None:
        with t.subTest('the list whose file the name stems'):
            ret = t.ad.path
            t.assertEqual(ret, t.source / 'a-list.md')

        with t.subTest('a name no list carries'):
            missing = Addition(t.source, 'a-missing-list', 'X', {}, TODAY)

            with t.assertRaises(ListError) as caught:
                _ = missing.path

            t.assertEqual(
                str(caught.exception),
                f"no list named 'a-missing-list' in {t.source}; "
                'available: a-list, another-list',
            )

    def test_text(t) -> None:
        with t.subTest('the task last in Open, every other line kept'):
            ret = t.ad.text
            t.assertEqual(ret, with_line(A_LIST, 13, t.ad.entry))

        with t.subTest('an empty open section takes it under its heading'):
            empty = Addition(t.source, 'another-list', 'X', {}, TODAY)
            ret = empty.text
            t.assertEqual(ret, f'{ANOTHER_LIST}{empty.entry}\n')

        with t.subTest('a description goes under the task line'):
            described = described_addition(t.source, DESCRIPTION)

            ret = described.text

            lines = [described.entry, *DESCRIPTION_LINES]
            t.assertEqual(ret, with_lines(A_LIST, 13, lines))

        with t.subTest('an empty description writes no line'):
            undescribed = described_addition(t.source, '')

            ret = undescribed.text

            t.assertEqual(ret, with_line(A_LIST, 13, undescribed.entry))

        with t.subTest('a description with a blank line is refused'):
            blank = described_addition(t.source, 'A line.\n\nA line.')

            with t.assertRaises(ValueError) as caught:
                _ = blank.text

            t.assertEqual(
                str(caught.exception),
                "description line '' is blank",
            )

        refused = {
            'a priority that is not a number': (
                {'P': 'high'},
                "P must be a whole number, not 'high'",
            ),
            'a level of effort off the scale': (
                {'LOE': '4'},
                "LOE must be one of 1, 2, 3, 5, 8, not '4'",
            ),
            'a due date that does not read': (
                {'DUE': 'someday'},
                "DUE must be an ISO date, not 'someday'",
            ),
            'a recurrence the scheduler cannot read': (
                {'REPEAT': 'often'},
                "unrecognised REPEAT value: 'often'",
            ),
        }
        for name, (fields, message) in refused.items():
            with t.subTest(name):
                refusal = Addition(t.source, 'a-list', 'X', fields, TODAY)

                with t.assertRaises(ValueError) as caught:
                    _ = refusal.text

                t.assertEqual(str(caught.exception), message)

        broken = {
            'a title with a line feed': (
                'A new\ntask',
                "title must hold no line break, not 'A new\\ntask'",
            ),
            'a title with a carriage return': (
                'A new\rtask',
                "title must hold no line break, not 'A new\\rtask'",
            ),
        }
        for name, (title, message) in broken.items():
            with t.subTest(name):
                refusal = Addition(t.source, 'a-list', title, {}, TODAY)

                with t.assertRaises(ValueError) as caught:
                    _ = refusal.text

                t.assertEqual(str(caught.exception), message)

    def test_entry(t) -> None:
        ret = t.ad.entry
        # The supplied fields in SCHEMA.md order, then the stamps.
        t.assertRegex(
            ret,
            r'^- \[ \] A new task \[P:3\] \[TAGS:a-tag\] '
            r'\[ADDED:2026-08-08\] \[ID:[0-9a-z]{6}\]$',
        )

    def test_events(t) -> None:
        with t.subTest('one TaskAdded, on the stream of the new task'):
            task_id = id_on(t.ad.entry)

            (ret,) = t.ad.events

            t.assertEqual(
                ret,
                (
                    'TaskAdded',
                    f'task/{task_id}',
                    {
                        'delta': {
                            'P': [None, '3'],
                            'TAGS': [None, 'a-tag'],
                            'ADDED': [None, '2026-08-08'],
                            'ID': [None, task_id],
                        },
                        'snapshot': {
                            'title': 'A new task',
                            'done': False,
                            'fields': {
                                'P': '3',
                                'TAGS': 'a-tag',
                                'ADDED': '2026-08-08',
                                'ID': task_id,
                            },
                        },
                    },
                ),
            )

        with t.subTest('the snapshot holds the description, not the delta'):
            described = described_addition(t.source, DESCRIPTION)

            (ret,) = described.events

            t.assertEqual(
                ret.payload['snapshot']['description'],
                'A first line.\nA second line.',
            )
            t.assertNotIn('description', ret.payload['delta'])

        with t.subTest('the attributes go on its event'):
            added = Addition(
                t.source,
                'a-list',
                'A new task',
                {},
                TODAY,
                attrs={'cost': '45.00'},
            )

            (event,) = added.events

            t.assertEqual(event.payload['attrs'], {'cost': '45.00'})

    def test_block(t) -> None:
        with t.subTest('the task line alone, where it has no description'):
            ret = t.ad.block
            t.assertEqual(ret, t.ad.entry)

        with t.subTest('and its description lines under it'):
            described = described_addition(t.source, DESCRIPTION)

            ret = described.block

            lines = [described.entry, *DESCRIPTION_LINES]
            t.assertEqual(ret, '\n'.join(lines))

    def test_description_lines(t) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.ad.description_lines
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description, stripped'):
            described = described_addition(t.source, DESCRIPTION)
            ret = described.description_lines
            t.assertEqual(ret, ['A first line.', 'A second line.'])


class SubtaskAdditionTests(TestCase):
    """Contract tests for battodo.mutate.SubtaskAddition."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.sa = SubtaskAddition(
            Task(t.source, '9o71lx', TODAY),
            'a-list',
            'A new subtask',
            {'LOE': '2'},
        )

    def test_write(t) -> None:
        t.sa.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the add derives, the journal its event.
        t.assertEqual(written, t.sa.text)
        t.assertEqual(journaled(t.source), as_journaled(t.sa.events))

    def test_path(t) -> None:
        ret = t.sa.path
        t.assertEqual(ret, t.source / 'a-list.md')

    def test_text(t) -> None:
        with t.subTest('last in its parent block, one level deeper'):
            ret = t.sa.text
            t.assertEqual(ret, with_line(A_LIST, 8, t.sa.entry))

        with t.subTest('a parent with no id is stamped first'):
            unidentified = subtask(t.source, 'A task with no id')

            ret = unidentified.text

            stamp = f'{NO_ID_TASK} [ID:{unidentified.parent_id}]'
            expected = A_LIST.replace(NO_ID_TASK, stamp)
            t.assertEqual(ret, with_line(expected, 9, unidentified.entry))

        with t.subTest('a description goes under the subtask line'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)

            ret = described.text

            lines = [
                described.entry,
                '        A first line.',
                '        A second line.',
            ]
            t.assertEqual(ret, with_lines(A_LIST, 8, lines))

        with t.subTest('a subtask nests one level under a subtask'):
            deeper = subtask(t.source, 'A subtask of it')
            ret = deeper.entry
            t.assertRegex(
                ret,
                r'^    - \[ \] A new subtask \[ID:[0-9a-z]{6}\]$',
            )

        refused = {
            'a list no file carries': (
                subtask(t.source, '9o71lx', list_name='a-missing-list'),
                ListError,
                "no list named 'a-missing-list'",
            ),
            'a field only the top-level task carries': (
                subtask(t.source, '9o71lx', fields={'P': '3'}),
                ValueError,
                'P belongs to the top-level task, not to a subtask',
            ),
            'a parent in another list': (
                subtask(t.source, '9o71lx', list_name='another-list'),
                ValueError,
                "'9o71lx' names a task in a-list.md, not another-list.md",
            ),
            'a checklist item, which a field would promote': (
                subtask(t.source, 'A checklist item'),
                ValueError,
                "'A checklist item' is a checklist item",
            ),
            'a parent no selector reaches': (
                subtask(t.source, 'nothing'),
                SelectionError,
                "no open task matches 'nothing'",
            ),
            'a title with a line break': (
                subtask(t.source, '9o71lx', title='A new\nsubtask'),
                ValueError,
                'title must hold no line break',
            ),
            'a description line that reads as a heading': (
                subtask(t.source, '9o71lx', description='## A heading'),
                ValueError,
                "description line '## A heading' reads as a heading",
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

        with t.subTest('a parent whose id is empty is stamped too'):
            unrecorded = under_an_empty_id(t.source)

            ret = unrecorded.text

            stamp = EMPTY_ID_TASK.replace(
                '[ID:]',
                f'[ID:{unrecorded.parent_id}]',
            )
            t.assertEqual(ret, f'## Open\n\n{stamp}\n{unrecorded.entry}\n')

    def test_entry(t) -> None:
        ret = t.sa.entry
        t.assertRegex(ret, r'^  - \[ \] A new subtask \[LOE:2\] \[ID:\w{6}\]$')

    def test_block(t) -> None:
        with t.subTest('the subtask line alone, where it has no description'):
            ret = t.sa.block
            t.assertEqual(ret, t.sa.entry)

        with t.subTest('and its description lines under it'):
            described = subtask(t.source, '9o71lx', description='A line.')
            ret = described.block
            t.assertEqual(ret, f'{described.entry}\n        A line.')

    def test_description_lines(t) -> None:
        with t.subTest('none, where no description is given'):
            ret = t.sa.description_lines
            t.assertEqual(ret, [])

        with t.subTest('the lines of the description, stripped'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)
            ret = described.description_lines
            t.assertEqual(ret, ['A first line.', 'A second line.'])

    def test_events(t) -> None:
        with t.subTest('one TaskAdded, which names the parent by id'):
            child_id = id_on(t.sa.entry)

            (ret,) = t.sa.events

            t.assertEqual(
                ret,
                (
                    'TaskAdded',
                    f'task/{child_id}',
                    {
                        'delta': {'LOE': [None, '2'], 'ID': [None, child_id]},
                        'snapshot': {
                            'title': 'A new subtask',
                            'done': False,
                            'fields': {'LOE': '2', 'ID': child_id},
                        },
                        'parent': '9o71lx',
                    },
                ),
            )

        with t.subTest('the snapshot carries the description'):
            described = subtask(t.source, '9o71lx', description=DESCRIPTION)

            (event,) = described.events

            t.assertEqual(
                event.payload['snapshot']['description'],
                'A first line.\nA second line.',
            )

        with t.subTest('a parent stamped first records the stamp first'):
            unidentified = subtask(t.source, 'A task with no id')

            stamp, added = unidentified.events

            parent_id = unidentified.parent_id
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{parent_id}',
                    {
                        'delta': {'ID': [None, parent_id]},
                        'snapshot': {
                            'title': 'A task with no id',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )
            t.assertEqual(added.payload['parent'], parent_id)

        with t.subTest('the attributes go on the TaskAdded alone'):
            unidentified = SubtaskAddition(
                Task(t.source, 'A task with no id', TODAY),
                'a-list',
                'A new subtask',
                {},
                attrs={'cost': '45.00'},
            )

            stamp, added = unidentified.events

            t.assertNotIn('attrs', stamp.payload)
            t.assertEqual(added.payload['attrs'], {'cost': '45.00'})

        with t.subTest('a parent whose id is empty is stamped first too'):
            unrecorded = under_an_empty_id(t.source)

            streams = [event.stream for event in unrecorded.events]

            t.assertEqual(
                streams,
                [
                    f'task/{unrecorded.parent_id}',
                    f'task/{unrecorded.task_id}',
                ],
            )


class UpdateTests(TestCase):
    """Contract tests for battodo.mutate.Update."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.up = Update(
            Task(t.source, '9o71lx', TODAY),
            {'P': '5', 'DUE': '2026-09-01'},
            title='A renamed task',
        )

    def test_write(t) -> None:
        t.up.write()

        written = (t.source / 'a-list.md').read_text(encoding='utf-8')

        # The list holds the text the update derives, the journal its
        # event.
        t.assertEqual(written, t.up.text)
        t.assertEqual(journaled(t.source), as_journaled(t.up.events))

    def test_text(t) -> None:
        with t.subTest('the fields and title written, every other line kept'):
            ret = t.up.text
            t.assertEqual(ret, A_LIST.replace(A_TASK, RENAMED_TASK))

        with t.subTest('a task with no id is given one'):
            unidentified = Update(
                Task(t.source, 'A task with no id', TODAY),
                {'P': '5'},
            )

            ret = unidentified.text

            line = f'- [ ] A task with no id [P:5] [ID:{unidentified.task_id}]'
            t.assertEqual(ret, A_LIST.replace(NO_ID_TASK, line))

        with t.subTest('a description replaces the description lines'):
            described = described_update(t.source, '9o71lx', DESCRIPTION)

            ret = described.text

            replaced = with_lines(without(A_LIST, 5), 5, DESCRIPTION_LINES)
            t.assertEqual(ret, replaced)

        with t.subTest('an empty description clears them'):
            cleared = described_update(t.source, '9o71lx', '')
            ret = cleared.text
            t.assertEqual(ret, without(A_LIST, 5))

        with t.subTest('a task with none takes them before its children'):
            described = described_update(t.source, 'rr01ab', DESCRIPTION)
            ret = described.text
            t.assertEqual(ret, with_lines(A_LIST, 10, DESCRIPTION_LINES))

        refused = {
            'an update that names nothing': (
                Update(Task(t.source, '9o71lx', TODAY), {}),
                ValueError,
                'nothing to update',
            ),
            'a value that does not read': (
                Update(Task(t.source, '9o71lx', TODAY), {'DUE': 'x'}),
                ValueError,
                "DUE must be an ISO date, not 'x'",
            ),
            'a field only the top-level task carries': (
                Update(Task(t.source, 'A subtask of', TODAY), {'P': '5'}),
                ValueError,
                'P belongs to the top-level task',
            ),
            'a checklist item, which a field would promote': (
                Update(
                    Task(t.source, 'A checklist item', TODAY),
                    {'DUE': '2026-09-01'},
                ),
                ValueError,
                'is a checklist item',
            ),
            'a selector that names no task': (
                Update(Task(t.source, 'nothing', TODAY), {'P': '5'}),
                SelectionError,
                "no open task matches 'nothing'",
            ),
            'a title with a line break': (
                Update(
                    Task(t.source, '9o71lx', TODAY),
                    {},
                    title='A renamed\rtask',
                ),
                ValueError,
                'title must hold no line break',
            ),
            'a description line that reads as a task': (
                described_update(t.source, '9o71lx', '- [ ] A task'),
                ValueError,
                r"description line '- \[ \] A task' reads as a task line",
            ),
            'a checklist item, which takes no description': (
                described_update(t.source, 'A checklist item', 'A line.'),
                ValueError,
                'is a checklist item',
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

    def test_entry(t) -> None:
        ret = t.up.entry
        t.assertEqual(ret, RENAMED_TASK)

    def test_events(t) -> None:
        with t.subTest('one TaskUpdated: what changed, and from what'):
            ret = t.up.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskUpdated',
                        'task/9o71lx',
                        {
                            'delta': {
                                'P': ['4', '5'],
                                'DUE': [None, '2026-09-01'],
                                'title': ['A task', 'A renamed task'],
                            },
                            'snapshot': {
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                            },
                        },
                    )
                ],
            )

        with t.subTest('a description, against the one it replaced'):
            described = described_update(t.source, '9o71lx', DESCRIPTION)

            (event,) = described.events

            t.assertEqual(
                event.payload['delta'],
                {
                    'description': [
                        'A note that stays put.',
                        'A first line.\nA second line.',
                    ],
                },
            )

        with t.subTest('a cleared description, against null'):
            cleared = described_update(t.source, '9o71lx', '')

            (event,) = cleared.events

            t.assertEqual(
                event.payload['delta'],
                {'description': ['A note that stays put.', None]},
            )

        with t.subTest('a subtask records where it sits, and its new id'):
            child = Update(
                Task(t.source, 'A subtask of it', TODAY),
                {'DUE': '2026-09-01'},
            )

            (event,) = child.events

            t.assertEqual(event.stream, f'task/{child.task_id}')
            t.assertEqual(event.payload['delta']['ID'], [None, child.task_id])
            t.assertEqual(
                event.payload['ancestry'],
                'A task > A subtask of it',
            )

        with t.subTest('the attributes go on its event'):
            updated = Update(
                Task(t.source, '9o71lx', TODAY),
                {'P': '5'},
                attrs={'cost': '45.00'},
            )

            (event,) = updated.events

            t.assertEqual(event.payload['attrs'], {'cost': '45.00'})


class CompletionTests(TestCase):
    """Contract tests for battodo.mutate.Completion."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)

    def test_write(t) -> None:
        with t.subTest('the list, the log and the journal hold its values'):
            completion = completion_of(t.source, 'A subtask that does not')

            completion.write()

            written = (t.source / 'a-list.md').read_text(encoding='utf-8')
            logged = (t.source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(written, completion.text)
            t.assertEqual(logged, '\n'.join(completion.entries) + '\n')
            t.assertEqual(
                journaled(t.source),
                as_journaled(completion.events),
            )

        with t.subTest('each journal line it appends names the given day'):
            source = a_source(t)
            task = Task(source, 'A subtask that does not', GIVEN_DAY)

            Completion(task).write()

            appended = Journal(source).events
            days = [event['payload']['completed_on'] for event in appended]
            t.assertEqual(days, ['2026-08-01', '2026-08-01'])

        with t.subTest('the journal line of a checklist item marks it'):
            source = a_source(t)

            completion_of(source, 'A checklist item').write()

            (event,) = Journal(source).events
            t.assertIs(event['payload']['checklist_item'], True)

        with t.subTest('a checklist item journals its owner stamp first'):
            completion = completion_of(
                an_owner_source(t), 'A checklist item to write'
            )

            completion.write()

            stream = f'task/{completion.ids[2]}'
            t.assertEqual(
                journaled(completion.source),
                [('TaskUpdated', stream), ('TaskCompleted', stream)],
            )

    def test_text(t) -> None:
        with t.subTest('a finished top-level task loses its line'):
            completed = completion_of(t.source, 'A task with no id')
            ret = completed.text
            t.assertEqual(ret, without(A_LIST, 8))

        with t.subTest('a block between blank lines takes one along'):
            completed = completion_of(t.source, 'bb01cd')
            ret = completed.text
            t.assertEqual(ret, without(A_LIST, 12, 13))

        with t.subTest('a child is stamped and checked, its parent stays'):
            completed = completion_of(t.source, 'A subtask of it')

            ret = completed.text

            child_id = completed.ids[6]
            line = f'  - [x] A subtask of it [LOE:2] [ID:{child_id}]'
            t.assertEqual(ret, A_LIST.replace(A_CHILD, line))

        with t.subTest('the last open child finishes a recurring parent'):
            completed = completion_of(t.source, 'A subtask that does not')

            ret = completed.text

            # The recurrence keeps its line, gains its next due date, and
            # loses its children.
            rescheduled = A_LIST.replace('2026-08-05', '2026-08-15')
            t.assertEqual(ret, without(rescheduled, 10))

        with t.subTest('a recurrence that does not read is refused'):
            odd = t.source / 'a-list.md'
            odd.write_text('## Open\n- [ ] An odd one [REPEAT:often]\n')
            completed = completion_of(t.source, 'An odd one')

            with t.assertRaises(RepeatError) as caught:
                _ = completed.text

            t.assertEqual(
                str(caught.exception),
                "unrecognised REPEAT value: 'often'",
            )

        with t.subTest('a rescheduled task keeps its description lines'):
            described = t.source / 'a-list.md'
            described.write_text(DESCRIBED_RECURRENCE, encoding='utf-8')
            completed = completion_of(t.source, 'dr01ab')

            ret = completed.text

            t.assertEqual(ret, RESCHEDULED_RECURRENCE)

    def test_entries(t) -> None:
        with t.subTest('the task and each ancestor it ends, deepest first'):
            completed = completion_of(t.source, 'A subtask that does not')
            ret = completed.entries
            t.assertEqual(
                ret,
                [
                    (
                        '2026-08-08 | a-list | DONE | A recurring task > '
                        'A subtask that does not recur [LOE:1]'
                    ),
                    (
                        '2026-08-08 | a-list | DONE | A recurring task [P:3] '
                        '[DUE:2026-08-05] [REPEAT:7d]'
                    ),
                ],
            )

        with t.subTest('a checklist item is not logged'):
            completed = completion_of(t.source, 'A checklist item')
            ret = completed.entries
            t.assertEqual(ret, [])

    def test_events(t) -> None:
        with t.subTest('one TaskCompleted a completion, deepest first'):
            completed = completion_of(t.source, 'A subtask that does not')

            child, parent = completed.events

            t.assertEqual(child.type, 'TaskCompleted')
            t.assertEqual(
                child.payload['ancestry'],
                'A recurring task > A subtask that does not recur',
            )
            t.assertEqual(child.payload['completed_on'], '2026-08-08')
            t.assertEqual(
                parent,
                (
                    'TaskCompleted',
                    'task/rr01ab',
                    {
                        'delta': {
                            'done': [False, True],
                            'DUE': ['2026-08-05', '2026-08-15'],
                        },
                        'snapshot': {
                            'title': 'A recurring task',
                            'done': False,
                            'fields': {
                                'P': '3',
                                'DUE': '2026-08-05',
                                'REPEAT': '7d',
                                'ID': 'rr01ab',
                            },
                        },
                        'ancestry': 'A recurring task',
                        'completed_on': '2026-08-08',
                    },
                ),
            )

        with t.subTest('a checklist item lands on its owner stream'):
            completed = completion_of(t.source, 'A checklist item')

            (ret,) = completed.events

            t.assertEqual(ret.stream, 'task/9o71lx')
            t.assertEqual(ret.payload['ancestry'], 'A task > A checklist item')
            t.assertIs(ret.payload['checklist_item'], True)

        with t.subTest('an owner with no id is stamped first, on its own'):
            completed = completion_of(
                an_owner_source(t), 'A checklist item to write'
            )

            stamp, item = completed.events

            task_id = completed.ids[2]
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{task_id}',
                    {
                        'delta': {'ID': [None, task_id]},
                        'snapshot': OWNER_SNAPSHOT,
                    },
                ),
            )
            t.assertEqual(item.stream, f'task/{task_id}')

        with t.subTest('the attributes go on the named task alone'):
            completed = completion_of(
                t.source,
                'A subtask that does not',
                attrs={'cost': '45.00'},
            )

            child, parent = completed.events

            t.assertEqual(child.payload['attrs'], {'cost': '45.00'})
            t.assertNotIn('attrs', parent.payload)

        with t.subTest('a checklist item takes no attributes'):
            completed = completion_of(
                t.source,
                'A checklist item',
                attrs={'note': 'a note'},
            )

            with t.assertRaises(ValueError) as caught:
                _ = completed.events

            t.assertEqual(
                str(caught.exception),
                'a checklist item takes no attributes',
            )


class ScratchTests(TestCase):
    """Contract tests for battodo.mutate.Scratch."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.sc = Scratch(Task(t.source, '9o71lx', TODAY))

    def test_write(t) -> None:
        with t.subTest('the list, the log and the journal hold its values'):
            t.sc.write()

            written = (t.source / 'a-list.md').read_text(encoding='utf-8')
            logged = (t.source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(written, t.sc.text)
            t.assertEqual(logged, '\n'.join(t.sc.entries) + '\n')
            t.assertEqual(journaled(t.source), as_journaled(t.sc.events))

        with t.subTest('the journal line of a checklist item marks it'):
            source = a_source(t)

            Scratch(Task(source, 'A checklist', TODAY)).write()

            (event,) = Journal(source).events
            t.assertIs(event['payload']['checklist_item'], True)

        with t.subTest('a checklist item journals its owner stamp first'):
            source = an_owner_source(t)
            scratched = Scratch(
                Task(source, 'A checklist item to write', TODAY)
            )

            scratched.write()

            stream = f'task/{scratched.stream_id}'
            t.assertEqual(
                journaled(source),
                [('TaskUpdated', stream), ('TaskScratched', stream)],
            )

    def test_text(t) -> None:
        with t.subTest('the task, its note and its children go'):
            ret = t.sc.text
            t.assertEqual(ret, without(A_LIST, 4, 5, 6, 7))

        with t.subTest('a subtask goes, and its parent stays'):
            scratched = Scratch(Task(t.source, 'A subtask of', TODAY))
            ret = scratched.text
            t.assertEqual(ret, without(A_LIST, 6))

    def test_entries(t) -> None:
        with t.subTest('one SCRATCHED record, with its path and fields'):
            scratched = Scratch(Task(t.source, 'A subtask of', TODAY))
            ret = scratched.entries
            t.assertEqual(
                ret,
                [
                    (
                        '2026-08-08 | a-list | SCRATCHED | A task > '
                        'A subtask of it [LOE:2]'
                    )
                ],
            )

        with t.subTest('a checklist item is not logged'):
            scratched = Scratch(Task(t.source, 'A checklist', TODAY))
            ret = scratched.entries
            t.assertEqual(ret, [])

    def test_events(t) -> None:
        with t.subTest('one TaskScratched, on the stream of the task'):
            ret = t.sc.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskScratched',
                        'task/9o71lx',
                        {
                            'delta': {'removed': [False, True]},
                            'snapshot': {
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                            },
                            'ancestry': 'A task',
                        },
                    )
                ],
            )

        with t.subTest('an owner with no id is stamped first, on its own'):
            task = Task(an_owner_source(t), 'A checklist item to write', TODAY)
            scratched = Scratch(task)

            stamp, item = scratched.events

            task_id = scratched.stream_id
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{task_id}',
                    {
                        'delta': {'ID': [None, task_id]},
                        'snapshot': OWNER_SNAPSHOT,
                    },
                ),
            )
            t.assertEqual(item.stream, f'task/{task_id}')

        with t.subTest('the attributes go on its event'):
            task = Task(t.source, '9o71lx', TODAY)
            scratched = Scratch(task, attrs={'cost': '45.00'})

            (event,) = scratched.events

            t.assertEqual(event.payload['attrs'], {'cost': '45.00'})

        with t.subTest('a checklist item takes no attributes'):
            task = Task(t.source, 'A checklist', TODAY)
            scratched = Scratch(task, attrs={'note': 'a note'})

            with t.assertRaises(ValueError) as caught:
                _ = scratched.events

            t.assertEqual(
                str(caught.exception),
                'a checklist item takes no attributes',
            )


class AnnotationTests(TestCase):
    """Contract tests for battodo.mutate.Annotation."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        t.an = annotation_of(t.source, '9o71lx')

    def test_write(t) -> None:
        with t.subTest('the list and the journal hold its values'):
            unidentified = annotation_of(t.source, 'A task with no id')

            unidentified.write()

            written = (t.source / 'a-list.md').read_text(encoding='utf-8')
            t.assertEqual(written, unidentified.text)
            t.assertEqual(
                journaled(t.source),
                as_journaled(unidentified.events),
            )

        with t.subTest('a task with an id: the list is not written again'):
            source = a_source(t)
            path = source / 'a-list.md'
            # A known mtime, so a rewrite shows without a wait.
            utime(path, ns=(0, 0))
            noted = annotation_of(source, '9o71lx')

            noted.write()

            t.assertEqual(path.stat().st_mtime_ns, 0)
            t.assertEqual(journaled(source), as_journaled(noted.events))

    def test_text(t) -> None:
        with t.subTest('a task with an id: the list as read'):
            ret = t.an.text
            t.assertEqual(ret, A_LIST)

        with t.subTest('a task with no id is given one'):
            unidentified = annotation_of(t.source, 'A task with no id')

            ret = unidentified.text

            line = f'{NO_ID_TASK} [ID:{unidentified.task_id}]'
            t.assertEqual(ret, A_LIST.replace(NO_ID_TASK, line))

        refused = {
            'a note that carries nothing, before the selector': (
                Annotation(Task(t.source, 'nothing', TODAY), {}),
                ValueError,
                'nothing to note: give a note or an attribute',
            ),
            'a checklist item, which takes no attributes': (
                annotation_of(t.source, 'A checklist item'),
                ValueError,
                'a checklist item takes no attributes',
            ),
            'a selector that names no open task': (
                annotation_of(t.source, 'nothing'),
                SelectionError,
                "no open task matches 'nothing'",
            ),
        }
        for name, (refusal, error, message) in refused.items():
            with t.subTest(name), t.assertRaisesRegex(error, message):
                _ = refusal.text

    def test_entry(t) -> None:
        ret = t.an.entry
        t.assertEqual(ret, A_TASK)

    def test_events(t) -> None:
        with t.subTest('one TaskAnnotated, on the stream of the task'):
            ret = t.an.events
            t.assertEqual(
                ret,
                [
                    (
                        'TaskAnnotated',
                        'task/9o71lx',
                        {
                            'snapshot': {
                                'title': 'A task',
                                'done': False,
                                'fields': {
                                    'P': '4',
                                    'LOE': '8',
                                    'ADDED': '2026-07-06',
                                    'ID': '9o71lx',
                                },
                                'description': 'A note that stays put.',
                            },
                            'attrs': {'note': 'Waiting on the vendor'},
                        },
                    )
                ],
            )

        with t.subTest('a task with no id is stamped first, on its own'):
            unidentified = annotation_of(t.source, 'A task with no id')

            stamp, annotated = unidentified.events

            task_id = unidentified.task_id
            t.assertEqual(
                stamp,
                (
                    'TaskUpdated',
                    f'task/{task_id}',
                    {
                        'delta': {'ID': [None, task_id]},
                        'snapshot': {
                            'title': 'A task with no id',
                            'done': False,
                            'fields': {'P': '2'},
                        },
                    },
                ),
            )
            t.assertEqual(annotated.stream, f'task/{task_id}')

        with t.subTest('a subtask records where it sits'):
            child = annotation_of(t.source, 'A subtask of it')

            _, annotated = child.events

            t.assertEqual(
                annotated.payload['ancestry'],
                'A task > A subtask of it',
            )


class BackfillTests(TestCase):
    """Contract tests for battodo.mutate.Backfill."""

    maxDiff = None

    def setUp(t) -> None:
        t.source = a_source(t)
        (t.source / 'a-template.md').write_text(
            '## Open\n- [ ] A task dated YYYY-MM-DD [DUE:YYYY-MM-DD]\n',
            encoding='utf-8',
        )

    def test_write(t) -> None:
        backfill = Backfill(t.source, TODAY)

        backfill.write()

        (listed,) = backfill.lists
        written = listed.path.read_text(encoding='utf-8')
        # The one list with a task to stamp holds the text its backfill
        # derives, and the journal holds its events.
        t.assertEqual(written, listed.text)
        t.assertEqual(journaled(t.source), as_journaled(listed.events))

    def test_lists(t) -> None:
        (ret,) = Backfill(t.source, TODAY).lists

        with t.subTest('only a list with an undated task to stamp'):
            t.assertEqual(ret.path, t.source / 'a-list.md')
            t.assertEqual(
                [task.title for task in ret.tasks],
                [
                    'A task with no id',
                    'A recurring task',
                    'A task between blank lines',
                ],
            )

        with t.subTest('each gains its add date, and an id if it has none'):
            stamped = (
                A_LIST.replace(
                    NO_ID_TASK,
                    f'{NO_ID_TASK} [ADDED:2026-08-08] [ID:{ret.ids[8]}]',
                )
                .replace('[ID:rr01ab]', '[ID:rr01ab] [ADDED:2026-08-08]')
                .replace('[ID:bb01cd]', '[ID:bb01cd] [ADDED:2026-08-08]')
            )
            t.assertEqual(ret.text, stamped)

        with t.subTest('one TaskAdded a stamp, marked as a backfill'):
            t.assertEqual(
                [event.stream for event in ret.events],
                [f'task/{ret.ids[8]}', 'task/rr01ab', 'task/bb01cd'],
            )
            t.assertEqual(
                ret.events[0].payload,
                {
                    'delta': {'ADDED': [None, '2026-08-08']},
                    'snapshot': {
                        'title': 'A task with no id',
                        'done': False,
                        'fields': {'P': '2'},
                    },
                    'backfilled': True,
                },
            )


class CompletedLogTests(TestCase):
    """Contract tests for battodo.mutate.CompletedLog."""

    def setUp(t) -> None:
        t.source = a_source(t)
        t.cl = CompletedLog(t.source)
        t.path = t.source / 'completed.md'

    def test_append(t) -> None:
        with t.subTest('a log not there yet is created to hold them'):
            t.cl.append(['a record', 'another record'])
            ret = t.path.read_text(encoding='utf-8')
            t.assertEqual(ret, 'a record\nanother record\n')

        with t.subTest('a log that ends mid-line gains a newline first'):
            t.path.write_text('# A log', encoding='utf-8')

            t.cl.append(['a record'])

            ret = t.path.read_text(encoding='utf-8')
            t.assertEqual(ret, '# A log\na record\n')

        with t.subTest('no record leaves an absent log absent'):
            t.path.unlink()
            t.cl.append([])
            t.assertFalse(t.path.exists())


class ChangesetTests(TestCase):
    """Contract tests for battodo.mutate.Changeset."""

    def setUp(t) -> None:
        t.source = a_source(t)
        t.path = t.source / 'a-list.md'
        t.cs = Changeset(
            'the list as written\n',
            ['a record'],
            [Event('TaskAdded', 'task/zz01ab', {'delta': {}})],
            t.path,
            t.source,
        )

    def test_write(t) -> None:
        with t.subTest('the list, the log and the journal take its values'):
            t.cs.write()

            written = t.path.read_text(encoding='utf-8')
            logged = (t.source / 'completed.md').read_text(encoding='utf-8')
            (event,) = Journal(t.source).events
            t.assertEqual(written, 'the list as written\n')
            t.assertEqual(logged, 'a record\n')
            t.assertEqual(
                (event['type'], event['stream_id'], event['payload']),
                ('TaskAdded', 'task/zz01ab', {'delta': {}}),
            )
            t.assertEqual(
                event['metadata'],
                {'actor': 'agent', 'source_file': 'a-list.md'},
            )

        with t.subTest('a list that holds the text already is not written'):
            source = a_source(t)
            path = source / 'a-list.md'
            # A known mtime, so a rewrite shows without a wait.
            utime(path, ns=(0, 0))
            unchanged = Changeset(
                A_LIST,
                ['a record'],
                [Event('TaskAdded', 'task/zz01ab', {'delta': {}})],
                path,
                source,
            )

            unchanged.write()

            logged = (source / 'completed.md').read_text(encoding='utf-8')
            t.assertEqual(path.stat().st_mtime_ns, 0)
            t.assertEqual(logged, 'a record\n')
            t.assertEqual(journaled(source), [('TaskAdded', 'task/zz01ab')])


def a_source(t: TestCase) -> Path:
    """A source directory holding both lists, removed at the end."""
    tmp = TemporaryDirectory()
    t.addCleanup(tmp.cleanup)
    source = Path(tmp.name)
    (source / 'a-list.md').write_text(A_LIST, encoding='utf-8')
    (source / 'another-list.md').write_text(ANOTHER_LIST, encoding='utf-8')
    return source


def an_owner_source(t: TestCase) -> Path:
    """A source directory holding both lists and the owner list."""
    source = a_source(t)
    owner = source / 'an-owner-list.md'
    owner.write_text(OWNER_LIST, encoding='utf-8')
    return source


def with_line(text: str, index: int, line: str) -> str:
    """`text` with `line` inserted at `index`."""
    lines = text.split('\n')
    lines.insert(index, line)
    return '\n'.join(lines)


def with_lines(text: str, index: int, lines: list[str]) -> str:
    """`text` with `lines` inserted in order from `index`."""
    found = text.split('\n')
    found[index:index] = lines
    return '\n'.join(found)


def described_addition(source: Path, description: str) -> Addition:
    """A new task in `a-list` that carries `description`."""
    return Addition(
        source,
        'a-list',
        'A new task',
        {},
        TODAY,
        description=description,
    )


def described_update(source: Path, selector: str, description: str) -> Update:
    """An update that names only a description."""
    return Update(Task(source, selector, TODAY), {}, description=description)


def id_on(line: str) -> str:
    """The `[ID:]` value a write stamped on `line`."""
    return line.split('[ID:')[1].removesuffix(']')


def subtask(
    source: Path,
    parent: str,
    *,
    list_name: str = 'a-list',
    fields: dict[str, str] | None = None,
    title: str = 'A new subtask',
    description: str | None = None,
) -> SubtaskAddition:
    """A new subtask under the task `parent` names."""
    return SubtaskAddition(
        Task(source, parent, TODAY),
        list_name,
        title,
        fields or {},
        description=description,
    )


def without(text: str, *indices: int) -> str:
    """`text` without the lines at `indices`."""
    return '\n'.join(
        line
        for index, line in enumerate(text.split('\n'))
            if index not in indices
    )  # fmt: skip


def completion_of(
    source: Path,
    selector: str,
    attrs: dict[str, str] | None = None,
) -> Completion:
    """The completion of the task `selector` names."""
    return Completion(Task(source, selector, TODAY), attrs=attrs)


def annotation_of(source: Path, selector: str) -> Annotation:
    """A note on the task `selector` names."""
    return Annotation(Task(source, selector, TODAY), A_NOTE)


def under_an_empty_id(source: Path) -> SubtaskAddition:
    """A new subtask under a parent whose `[ID:]` holds nothing."""
    list_file = source / 'an-empty-id-list.md'
    list_file.write_text(EMPTY_ID_LIST, encoding='utf-8')
    return subtask(
        source,
        'A task with an empty id',
        list_name='an-empty-id-list',
    )


def journaled(source: Path) -> list[tuple[str, str]]:
    """The type and stream of each event the journal of `source` holds."""
    return [
        (event['type'], event['stream_id']) for event in Journal(source).events
    ]


def as_journaled(events: list[Event]) -> list[tuple[str, str]]:
    """The type and stream of each of `events`."""
    return [(event.type, event.stream) for event in events]
