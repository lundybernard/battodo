from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from ..lib import TOP_N, build_json, build_view

SRC = 'battodo.view.lib'


def autopatch(case: TestCase, target: str) -> Mock:
    """Stand in for `target`, put back when `case` finishes."""
    patcher = patch(f'{SRC}.{target}', autospec=True)
    double = patcher.start()
    case.addCleanup(patcher.stop)
    return double


class ComposedTests(TestCase):
    """Base: the pieces the two functions put together, all stood in for."""

    def setUp(t) -> None:
        t.Selection = autopatch(t, 'Selection')
        t.View = autopatch(t, 'View')
        t.directory = Path('~/todo')
        t.now = datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc)


class BuildViewTests(ComposedTests):
    def test_build_view(t) -> None:
        with t.subTest('what comes back is the rendered view'):
            rendered = build_view(t.directory, t.now, show_all=False)
            t.assertEqual(rendered, t.View.return_value.text)

        with t.subTest('the source and the clock reach the selection'):
            t.Selection.assert_called_once_with(
                t.directory, t.now, show_all=False, top_n=TOP_N
            )

        with t.subTest('which the view is laid out from'):
            t.View.assert_called_once_with(t.Selection.return_value, 0)

        with t.subTest('a limit and a width are passed along when given'):
            t.Selection.reset_mock()
            t.View.reset_mock()

            build_view(t.directory, t.now, show_all=True, top_n=2, width=100)

            t.Selection.assert_called_once_with(
                t.directory, t.now, show_all=True, top_n=2
            )
            t.View.assert_called_once_with(t.Selection.return_value, 100)


class BuildJsonTests(ComposedTests):
    def test_build_json(t) -> None:
        with t.subTest('what comes back is the selection, serialized'):
            serialized = build_json(t.directory, t.now, show_all=False)
            t.assertEqual(serialized, t.Selection.return_value.json)

        with t.subTest('the source and the clock reach the selection'):
            t.Selection.assert_called_once_with(
                t.directory, t.now, show_all=False, top_n=TOP_N
            )

        with t.subTest('nothing is laid out for a terminal'):
            t.View.assert_not_called()

        with t.subTest('a limit is passed along when given'):
            t.Selection.reset_mock()

            build_json(t.directory, t.now, show_all=True, top_n=2)

            t.Selection.assert_called_once_with(
                t.directory, t.now, show_all=True, top_n=2
            )
