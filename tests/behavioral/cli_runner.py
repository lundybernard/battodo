"""Run the console entry point in process and capture what it wrote.

In process rather than as a subprocess: every golden depends on the
clock, and a subprocess's clock cannot be pinned.

Not named `*_test.py`, so the discovery pattern imports it without
collecting it.
"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from os import environ
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
        Environment variables to set for the run, and only for it.
        The user config directory is an empty one unless `env` names
        another, so no config file of the host reaches the run.

    Raises
    ------
    AssertionError
        If the entry point returns without exiting.
    """
    out, err = StringIO(), StringIO()
    try:
        with (
            TemporaryDirectory() as config_home,
            patch.dict(environ, {'XDG_CONFIG_HOME': config_home} | env),
            redirect_stdout(out),
            redirect_stderr(err),
        ):
            BATCLI(args)
    except SystemExit as exit:
        return out.getvalue(), err.getvalue(), exit.code
    raise AssertionError('the entry point returned without exiting')
