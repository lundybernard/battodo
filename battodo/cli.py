import argparse
import logging
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path
from sys import exit

from battodo.conf import get_config
from battodo.example.cli import example_cli
from battodo.lib import hello_world
from battodo.logconf import logging_config
from battodo.mutate import backfill_all
from battodo.view import TZ, build_view

dictConfig(logging_config)
log = logging.getLogger('root')


def BATCLI(ARGS=None):
    p = argparser()
    # Execute
    # get only the first command in args
    args = p.parse_args(ARGS, NestedNameSpace())
    conf = get_config(
        cli_args=args,
        config_file=args.config_file,
        config_env=args.config_env,
    )
    Commands.set_log_level(args)
    # execute function set for parsed command
    try:
        args.func(conf)
    # Top-level CLI boundary: any command failure becomes a message plus
    # usage help, never a traceback.
    except Exception as exp:  # noqa: BLE001
        print(exp)
        p.print_help()
        exit(1)
    exit(0)


class NestedNameSpace(argparse.Namespace):
    def __setattr__(self, name, value):
        if '.' in name:
            group, name = name.split('.', 1)
            ns = getattr(self, group, NestedNameSpace())
            setattr(ns, name, value)
            self.__dict__[group] = ns
        else:
            self.__dict__[name] = value


def argparser():
    p = argparse.ArgumentParser(
        description='Utility for executing various btodo tasks',
        usage='btodo [<args>] <command>',
    )
    p.set_defaults(func=get_help(p))

    p.add_argument(
        '-v',
        '--verbose',
        help='enable INFO output',
        action='store_const',
        dest='loglevel',
        const=logging.INFO,
    )
    p.add_argument(
        '--debug',
        help='enable DEBUG output',
        action='store_const',
        dest='loglevel',
        const=logging.DEBUG,
    )
    p.add_argument(
        '-c',
        '--conf',
        '--config_file',
        dest='config_file',
        default=None,
        help='specify a config file to get environment details from.'
        ' default=./config.yaml',
    )
    p.add_argument(
        '-e',
        '--env',
        '--config_environment',
        dest='config_env',
        default=None,
        help='specify the remote environment to use from the config file',
    )

    # Add a subparser to handle sub-commands
    commands = p.add_subparsers(
        dest='command',
        title='commands',
        description='for additonal details on each command use: '
        '"btodo {command name} --help"',
    )
    # hello args
    hello = commands.add_parser(
        'hello',
        description='execute command hello',
        help='for details use hello --help',
    )
    hello.set_defaults(func=Commands.hello)

    view = commands.add_parser(
        'view',
        description='show open items for the currently active categories',
        help='for details use view --help',
    )
    view.set_defaults(func=Commands.view)
    view.add_argument(
        '--all',
        dest='show_all',
        action='store_true',
        help='show every open item, not just the top few per category',
    )

    backfill = commands.add_parser(
        'backfill',
        description='one-time migration: stamp [ADDED:today] on tasks '
        'that predate the field',
        help='for details use backfill --help',
    )
    backfill.set_defaults(func=Commands.backfill)

    # Add a subparser from a module
    commands.add_parser(
        'example',
        help='example module commands',
        add_help=False,
        parents=[example_cli()],
    )

    return p


def get_help(parser):
    def help(args):
        parser.print_help()

    return help


class Commands:
    @staticmethod
    def hello(conf):
        print(hello_world())

    @staticmethod
    def backfill(conf):
        source = Path(conf.view.source_dir).expanduser()
        result = backfill_all(source, datetime.now(TZ).date())
        for name, titles in sorted(result.items()):
            print(f'{name}: stamped {len(titles)}')
        if not result:
            print('nothing to backfill')

    @staticmethod
    def view(conf):
        source = Path(conf.view.source_dir).expanduser()
        print(
            build_view(
                source,
                datetime.now(TZ),
                show_all=bool(getattr(conf, 'show_all', False)),
            )
        )

    @staticmethod
    def set_log_level(conf):
        if conf.loglevel:
            log.setLevel(conf.loglevel)
        else:
            log.setLevel(logging.ERROR)
