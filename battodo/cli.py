import argparse
import logging
from logging.config import dictConfig
from sys import exit

from battodo.conf import get_config

from battodo.example.cli import example_cli
from battodo.logconf import logging_config
from battodo.lib import hello_world


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
    except Exception as exp:
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
        '-v', '--verbose',
        help='enable INFO output',
        action='store_const',
        dest='loglevel',
        const=logging.INFO
    )
    p.add_argument(
        '--debug',
        help='enable DEBUG output',
        action='store_const',
        dest='loglevel',
        const=logging.DEBUG,
    )
    p.add_argument(
        '-c', '--conf', '--config_file',
        dest='config_file',
        default=None,
        help='specify a config file to get environment details from.'
             ' default=./config.yaml',
    )
    p.add_argument(
        '-e', '--env', '--config_environment',
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
    def set_log_level(conf):
        if conf.loglevel:
            log.setLevel(conf.loglevel)
        else:
            log.setLevel(logging.ERROR)
