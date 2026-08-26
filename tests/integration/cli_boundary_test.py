"""Contract test for the import boundary of the CLI.

Every code path a UI executes runs through `battodo.lib`, so the CLI
imports that interface and nothing else of the package except the
wiring `ALLOWED` names. The source is read rather than the loaded
module: an import inside a function body binds the collaborator all
the same.
"""

import ast
from collections.abc import Iterator
from pathlib import Path
from unittest import TestCase

from battodo import cli

PACKAGE = 'battodo'
# The interface, and the wiring a UI starts itself with: the
# configuration it resolves, the display strings, and the logging
# setup. Wiring is not domain surface, so it does not pass through lib.
ALLOWED = frozenset({'lib', 'conf', 'messages', 'logconf'})


def reached(node: ast.AST) -> Iterator[str]:
    """Every dotted path one import statement reaches."""
    if isinstance(node, ast.Import):
        yield from (alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        # A relative import names the package it is written in.
        root = node.module or ''
        if node.level:
            root = f'{PACKAGE}.{root}'.rstrip('.')
        yield from (f'{root}.{alias.name}' for alias in node.names)


def imported_modules(source: str) -> set[str]:
    """The package modules `source` imports, by first component."""
    return {
        path.split('.')[1]
        for node in ast.walk(ast.parse(source))
        for path in reached(node)
        if path.split('.')[0] == PACKAGE and '.' in path
    }


class CliImportBoundaryTests(TestCase):
    """Unit tests for battodo.cli."""

    def test_imports(t):
        source = Path(cli.__file__).read_text(encoding='utf-8')

        t.assertEqual(imported_modules(source) - ALLOWED, set())
