"""Contract tests for the digest API, against real files.

One test per public name, one subtest per code path. The source is a
real directory holding a real `completed.md`. This layer asserts return
values; interaction checks stay in the isolation tests beside the code.
"""

from datetime import datetime, timezone
from json import loads
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from battodo.completed import CompletedError, Digest, DigestView

# Wednesday. The week reaches back to 2026-07-30, the month to
# 2026-08-01.
NOW = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)
LOG = """\
# Completed Tasks

<!-- YYYY-MM-DD | CATEGORY | DONE | TITLE [P:N] -->
2026-07-29 | work | DONE | Land the parser rewrite [P:4]
2026-08-05 | work | DONE | Update the log [P:25] [TAGS:worklog]
2026-07-31 | van | DONE | Rebuild the galley shelf [LOE:2]
2026-08-04 | work | SCRATCHED | Rewrite the formula again
2026-08-04 | chores | DONE | Deck > Chip the brush pile [LOE:2]
"""


class LogDirTests(TestCase):
    """Base: a source directory holding the log, removed at the end."""

    def setUp(t) -> None:
        tmp = TemporaryDirectory()
        t.addCleanup(tmp.cleanup)
        t.source = Path(tmp.name)
        (t.source / 'completed.md').write_text(LOG, encoding='utf-8')


class RenderedDigestTests(LogDirTests):
    def rendered(t, source: Path, period: str) -> str:
        """The digest `source` renders for `period`, at the pinned hour."""
        return DigestView(Digest(source, NOW, period=period)).text

    def test_rendered_digest(t) -> None:
        digest = t.rendered(t.source, 'week')

        with t.subTest('the period, its span, and how much it holds'):
            t.assertIn(
                'Completed week: 2026-07-30 to 2026-08-05 — 3 done', digest
            )

        with t.subTest('each category heads its own table'):
            t.assertIn('── Chores ', digest)

        with t.subTest('a record shows its date and its ancestry'):
            t.assertIn('  2026-08-04  Deck > Chip the brush pile', digest)

        with t.subTest('a record outside the period is left out'):
            t.assertNotIn('Land the parser rewrite', digest)

        with t.subTest('and so is an abandoned one'):
            t.assertNotIn('Rewrite the formula again', digest)

        with t.subTest('a shorter period reads as one day'):
            t.assertIn(
                'Completed today: 2026-08-05 — 1 done',
                t.rendered(t.source, 'today'),
            )

        with t.subTest('and the month reaches back to its first day'):
            month = t.rendered(t.source, 'month')
            t.assertIn(
                'Completed month: 2026-08-01 to 2026-08-05 — 2 done', month
            )

        with (
            t.subTest('a source with no log is an error'),
            TemporaryDirectory() as bare,
        ):
            with t.assertRaises(CompletedError) as caught:
                t.rendered(Path(bare), 'week')
            t.assertIn(bare, str(caught.exception))

        with (
            t.subTest('so is a period with no definition'),
            t.assertRaises(ValueError),
        ):
            t.rendered(t.source, 'fortnight')


class DigestDocumentTests(LogDirTests):
    def test_digest_document(t) -> None:
        data = loads(Digest(t.source, NOW, period='week').json)

        with t.subTest('the period and its span'):
            t.assertEqual(data['period'], 'week')
            t.assertEqual(data['start'], '2026-07-30')
            t.assertEqual(data['end'], '2026-08-05')

        with t.subTest('the count is every record the period holds'):
            t.assertEqual(data['total'], 3)

        with t.subTest('grouped by category, in the view order'):
            t.assertEqual(
                [group['name'] for group in data['categories']],
                ['work', 'chores', 'van'],
            )

        with t.subTest('a title keeps its ancestry and loses its fields'):
            t.assertEqual(
                data['categories'][1]['entries'],
                [
                    {
                        'date': '2026-08-04',
                        'title': 'Deck > Chip the brush pile',
                    }
                ],
            )
