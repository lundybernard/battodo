"""Run the console entry point in process and capture what it wrote.

In process rather than as a subprocess: every golden depends on the
clock, and a subprocess's clock cannot be pinned.

Not named `*_test.py`, so the discovery pattern imports it without
collecting it.
"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from os import chdir, environ, getcwd
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from battodo.cli import BATCLI


def run_cli(args: list[str], env: dict[str, str]) -> tuple[str, str, Any]:
    """Run `args` with `env` set. Returns stdout, stderr and the code.

    Parameters
    ----------
    args : list of str
        The command line, without the program name.
    env : dict
        The whole environment of the run: the host's environment is
        cleared first. The run starts in an empty sandbox directory,
        and searches that sandbox for the user config file unless
        `env` names another, so no config file of the host reaches
        the run.

    Raises
    ------
    AssertionError
        If the entry point returns without exiting.
    """
    out, err = StringIO(), StringIO()
    cwd = getcwd()
    try:
        with (
            TemporaryDirectory() as sandbox,
            patch.dict(
                environ,
                {'XDG_CONFIG_HOME': sandbox} | env,
                clear=True,
            ),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            try:
                chdir(sandbox)
                BATCLI(args)
            finally:
                chdir(cwd)
    except SystemExit as exit:
        return out.getvalue(), err.getvalue(), exit.code
    raise AssertionError('the entry point returned without exiting')
