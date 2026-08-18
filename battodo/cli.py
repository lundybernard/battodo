import argparse
import logging
import sys
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path
from sys import exit

from battodo.completed import DEFAULT_PERIOD, PERIODS
from battodo.conf import CONFIG_ROOT, get_config
from battodo.item import build_item, build_item_json
from battodo.lib import get_completed, get_view
from battodo.logconf import logging_config
from battodo.messages import MESSAGES
from battodo.mutate import (
    add_task,
    backfill_all,
    complete,
    scratch,
    update_task,
)
from battodo.view import TZ, item_count

dictConfig(logging_config)
log = logging.getLogger('root')

# The SCHEMA.md fields `add` can write, by the option that supplies
# each. Every one is optional, and an option the user left off is
# *absent* from the Configuration rather than None, so they are read
# with `getattr` and only the supplied ones are passed on.
ADD_FIELDS = {
    'P': 'priority',
    'LOE': 'loe',
    'DUE': 'due',
    'REPEAT': 'repeat',
    'TAGS': 'tags',
}
# The subset `update` writes, read the same way. `LOE` and `REPEAT` are
# left out: R3 names neither, and a changed `REPEAT` reschedules the
# task on its next completion, which is a decision of its own.
UPDATE_FIELDS = {'P': 'priority', 'DUE': 'due', 'TAGS': 'tags'}


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
        source = Path(conf.view.source_dir).expanduser()
        fields = {
            name: value
            for name, option in ADD_FIELDS.items()
            if (value := getattr(conf, option, None)) is not None
        }
        path, entry = add_task(
            source,
            conf.list,
            conf.title,
            fields,
            datetime.now(TZ).date(),
        )
        # Echoed because a P-less task ranks near 0 and so will not
        # appear in a view: this is the only confirmation of the write.
        print(entry)
        print(path)

    @staticmethod
    def show(conf):
        source = Path(conf.view.source_dir).expanduser()
        build = (
            build_item_json
            if getattr(conf, 'format', 'text') == 'json'
            else build_item
        )
        print(build(source, conf.selector, datetime.now(TZ)))

    @staticmethod
    def update(conf):
        source = Path(conf.view.source_dir).expanduser()
        fields = {
            name: value
            for name, option in UPDATE_FIELDS.items()
            if (value := getattr(conf, option, None)) is not None
        }
        path, entry = update_task(
            source,
            conf.selector,
            fields,
            datetime.now(TZ).date(),
            title=getattr(conf, 'title', None),
        )
        print(entry)
        print(path)

    @staticmethod
    def done(conf):
        source = Path(conf.view.source_dir).expanduser()
        entries = complete(source, conf.selector, datetime.now(TZ).date())
        # A checklist item is checked off without a completed.md entry.
        print('\n'.join(entries) if entries else 'checked off')

    @staticmethod
    def scratch(conf):
        source = Path(conf.view.source_dir).expanduser()
        entries = scratch(source, conf.selector, datetime.now(TZ).date())
        # A checklist item is dropped without a completed.md entry.
        print('\n'.join(entries) if entries else 'dropped')

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
