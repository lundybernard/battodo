import argparse
import logging
import sys
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path
from sys import exit

from battodo.conf import CONFIG_ROOT, get_config
from battodo.lib import (
    DEFAULT_PERIOD,
    PERIODS,
    TZ,
    add_item,
    complete_item,
    get_completed,
    get_item,
    get_view,
    item_count,
    scratch_item,
    update_item,
)
from battodo.logconf import logging_config
from battodo.messages import MESSAGES
from battodo.mutate import backfill_all

dictConfig(logging_config)
log = logging.getLogger('root')


def BATCLI(ARGS=None):
    p = argparser()
    # Execute
    # get only the first command in args
    args = p.parse_args(ARGS)
    conf = get_config(
        cli_args=args,
        config_file_name=args.config_file,
        config_env=args.config_env,
    )
    Commands.set_log_level(args)
    # execute function set for parsed command
    try:
        args.func(conf)
    # Top-level CLI boundary: any command failure becomes a message on
    # stderr, never a traceback. stdout carries the command's output and
    # nothing else, so a consumer can parse it unconditionally; the help
    # dump is left to argparse, which owns actual usage errors.
    except Exception as exp:  # noqa: BLE001
        print(exp, file=sys.stderr)
        exit(1)
    exit(0)


def argparser():
    p = argparse.ArgumentParser(
        description=MESSAGES['cli.description'],
        usage=MESSAGES['cli.usage'],
    )
    p.set_defaults(func=get_help(p))

    p.add_argument(
        '-v',
        '--verbose',
        help=MESSAGES['cli.verbose.help'],
        action='store_const',
        dest='loglevel',
        const=logging.INFO,
    )
    p.add_argument(
        '--debug',
        help=MESSAGES['cli.debug.help'],
        action='store_const',
        dest='loglevel',
        const=logging.DEBUG,
    )
    p.add_argument(
        '-c',
        '--conf',
        '--config_file',
        dest='config_file',
        help=MESSAGES['cli.config_file.help'],
    )
    p.add_argument(
        '-e',
        '--env',
        '--config_environment',
        dest='config_env',
        help=MESSAGES['cli.config_env.help'],
    )

    # Add a subparser to handle sub-commands
    commands = p.add_subparsers(
        title=MESSAGES['cli.commands.title'],
        description=MESSAGES['cli.commands.description'],
    )
    view = commands.add_parser(
        'view',
        description=MESSAGES['view.description'],
        help=MESSAGES['view.help'],
    )
    view.set_defaults(func=Commands.view)
    # Arguments read back through the Configuration are named for their
    # dotted config path: batconf looks up `{path}.{key}` as one flat
    # attribute (batconf.sources.argparse.NamespaceConfig), never the
    # bare dest. Arguments read straight off `args` stay unprefixed.
    view.add_argument(
        '--all',
        dest=f'{CONFIG_ROOT}.show_all',
        action='store_true',
        help=MESSAGES['view.all.help'],
    )
    view.add_argument(
        '--top',
        dest=f'{CONFIG_ROOT}.view.top',
        type=checked_count,
        help=MESSAGES['view.top.help'],
    )
    view.add_argument(
        '--format',
        dest=f'{CONFIG_ROOT}.format',
        choices=('text', 'json'),
        default='text',
        help=MESSAGES['view.format.help'],
    )

    add = commands.add_parser(
        'add',
        description=MESSAGES['add.description'],
        help=MESSAGES['add.help'],
    )
    add.set_defaults(func=Commands.add)
    add.add_argument(
        f'{CONFIG_ROOT}.list',
        metavar=MESSAGES['add.list.metavar'],
        help=MESSAGES['add.list.help'],
    )
    add.add_argument(
        f'{CONFIG_ROOT}.title',
        metavar=MESSAGES['add.title.metavar'],
        help=MESSAGES['add.title.help'],
    )
    add.add_argument(
        '-p',
        '--priority',
        dest=f'{CONFIG_ROOT}.priority',
        help=MESSAGES['add.priority.help'],
    )
    add.add_argument(
        '--loe',
        dest=f'{CONFIG_ROOT}.loe',
        help=MESSAGES['add.loe.help'],
    )
    add.add_argument(
        '--due',
        dest=f'{CONFIG_ROOT}.due',
        help=MESSAGES['add.due.help'],
    )
    add.add_argument(
        '--repeat',
        dest=f'{CONFIG_ROOT}.repeat',
        help=MESSAGES['add.repeat.help'],
    )
    add.add_argument(
        '--tags',
        dest=f'{CONFIG_ROOT}.tags',
        help=MESSAGES['add.tags.help'],
    )
    add.add_argument(
        '--parent',
        dest=f'{CONFIG_ROOT}.parent',
        help=MESSAGES['add.parent.help'],
    )

    show = commands.add_parser(
        'show',
        description=MESSAGES['show.description'],
        help=MESSAGES['show.help'],
    )
    show.set_defaults(func=Commands.show)
    show.add_argument(
        f'{CONFIG_ROOT}.selector',
        metavar=MESSAGES['show.selector.metavar'],
        help=MESSAGES['show.selector.help'],
    )
    show.add_argument(
        '--format',
        dest=f'{CONFIG_ROOT}.format',
        choices=('text', 'json'),
        default='text',
        help=MESSAGES['show.format.help'],
    )

    update = commands.add_parser(
        'update',
        description=MESSAGES['update.description'],
        help=MESSAGES['update.help'],
    )
    update.set_defaults(func=Commands.update)
    update.add_argument(
        f'{CONFIG_ROOT}.selector',
        metavar=MESSAGES['update.selector.metavar'],
        help=MESSAGES['update.selector.help'],
    )
    update.add_argument(
        '-p',
        '--priority',
        dest=f'{CONFIG_ROOT}.priority',
        help=MESSAGES['update.priority.help'],
    )
    update.add_argument(
        '--due',
        dest=f'{CONFIG_ROOT}.due',
        help=MESSAGES['update.due.help'],
    )
    update.add_argument(
        '--tags',
        dest=f'{CONFIG_ROOT}.tags',
        help=MESSAGES['update.tags.help'],
    )
    update.add_argument(
        '--title',
        dest=f'{CONFIG_ROOT}.title',
        help=MESSAGES['update.title.help'],
    )

    done = commands.add_parser(
        'done',
        description=MESSAGES['done.description'],
        help=MESSAGES['done.help'],
    )
    done.set_defaults(func=Commands.done)
    done.add_argument(
        f'{CONFIG_ROOT}.selector',
        metavar=MESSAGES['done.selector.metavar'],
        help=MESSAGES['done.selector.help'],
    )

    drop = commands.add_parser(
        'scratch',
        description=MESSAGES['scratch.description'],
        help=MESSAGES['scratch.help'],
    )
    drop.set_defaults(func=Commands.scratch)
    drop.add_argument(
        f'{CONFIG_ROOT}.selector',
        metavar=MESSAGES['scratch.selector.metavar'],
        help=MESSAGES['scratch.selector.help'],
    )

    backfill = commands.add_parser(
        'backfill',
        description=MESSAGES['backfill.description'],
        help=MESSAGES['backfill.help'],
    )
    backfill.set_defaults(func=Commands.backfill)

    completed = commands.add_parser(
        'completed',
        description=MESSAGES['completed.description'],
        help=MESSAGES['completed.help'],
    )
    completed.set_defaults(func=Commands.completed)
    completed.add_argument(
        f'{CONFIG_ROOT}.period',
        nargs='?',
        choices=PERIODS,
        default=DEFAULT_PERIOD,
        metavar=MESSAGES['completed.period.metavar'],
        help=MESSAGES['completed.period.help'],
    )
    completed.add_argument(
        '--format',
        dest=f'{CONFIG_ROOT}.format',
        choices=('text', 'json'),
        default='text',
        help=MESSAGES['completed.format.help'],
    )

    return p


def checked_count(value: str) -> str:
    """Check a count given on the command line; it stays a string.

    Every configuration value is a string, whichever source carries it.

    Raises
    ------
    argparse.ArgumentTypeError
        The value is not a whole number of one or more.
    """
    try:
        item_count(value)
    except ValueError as exp:
        raise argparse.ArgumentTypeError(str(exp)) from exp
    return value


def get_help(parser):
    def help(args):
        parser.print_help()

    return help


class Commands:
    @staticmethod
    def add(conf):
        print(add_item(conf, datetime.now(TZ)))

    @staticmethod
    def show(conf):
        print(get_item(conf, datetime.now(TZ)))

    @staticmethod
    def update(conf):
        print(update_item(conf, datetime.now(TZ)))

    @staticmethod
    def done(conf):
        print(complete_item(conf, datetime.now(TZ)))

    @staticmethod
    def scratch(conf):
        print(scratch_item(conf, datetime.now(TZ)))

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
        print(get_view(conf, datetime.now(TZ)))

    @staticmethod
    def completed(conf):
        print(get_completed(conf, datetime.now(TZ)))

    @staticmethod
    def set_log_level(conf):
        if conf.loglevel:
            log.setLevel(conf.loglevel)
        else:
            log.setLevel(logging.ERROR)
