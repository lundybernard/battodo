"""The agent manual that `btodo skill` prints from the installed package.

The run starts in an empty sandbox directory, so the manual comes from
the package, never from the working directory.
"""

from unittest import TestCase

from .cli_runner import run_cli


class SkillCommandTests(TestCase):
    """CLI tests for the output of the `skill` command."""

    def test_skill(t) -> None:
        out, err, code = run_cli(['skill'], {})

        with t.subTest('the run succeeds and reports nothing on stderr'):
            t.assertEqual(err, '')
            t.assertEqual(code, 0)

        with t.subTest('the manual opens at its title, after the frontmatter'):
            t.assertRegex(out, r'\A# BatTodo\n')

        with t.subTest('and no link leads out of the printed text'):
            # A relative link into the checkout resolves nowhere once
            # the manual prints; an anchor into the manual stays.
            t.assertNotRegex(out, r'\]\((?!#)')
