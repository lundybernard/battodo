"""Every string the CLI displays, keyed by a stable id.

Pure data: no logic, no imports, no formatting. The parser in `cli.py`
holds the structure -- flags, dests, choices, defaults -- and looks its
wording up here, so a translation is a second catalog rather than a
second parser.

Ids are `{command}.{argument}.{kind}`, or `{command}.{kind}` for a
screen; the top-level parser is the command named `cli`, so nothing a
subcommand may later be called can collide with it. Ids are the stable
half of the pair: the wording may be reworded freely, but renaming a
key breaks the lookup that reads it.

Excluded from mutation testing (`do_not_mutate` in pyproject.toml).
Mutating display text produces no behaviour to assert on, while every
lookup that reaches in here stays under mutation -- a mangled key is a
`KeyError` the moment the parser is built.
"""

MESSAGES = {
    # The top-level screen.
    'cli.description': 'Utility for executing various btodo tasks',
    'cli.usage': 'btodo [<args>] <command>',
    'cli.verbose.help': 'enable INFO output',
    'cli.debug.help': 'enable DEBUG output',
    'cli.config_file.help': 'read config from this file. without it,'
    ' ./battodo.toml and then the XDG user config file are searched',
    'cli.config_env.help': 'specify the remote environment to use from the'
    ' config file',
    'cli.commands.title': 'commands',
    'cli.commands.description': 'for additonal details on each command use: '
    '"btodo {command name} --help"',
    # view
    'view.description': 'show open items for the currently active categories',
    'view.help': 'for details use view --help',
    'view.all.help': (
        'show every open item, and every category, not just those active now'
    ),
    'view.top.help': (
        'how many items a category shows, 1 or more; overrides the'
        ' configured view.top, and --all outranks it'
    ),
    'view.format.help': 'output format: text for a terminal, json for agents',
    # add
    'add.description': 'add a task to a list, or under a parent task',
    'add.help': 'for details use add --help',
    'add.list.metavar': 'list',
    'add.list.help': "the list's filename stem, e.g. chores for chores.md",
    'add.title.metavar': 'title',
    'add.title.help': 'the task title, without any [FIELD:] markup',
    'add.priority.help': 'priority multiplier, 0 and up; absent reads as 0',
    'add.loe.help': 'level of effort: 1, 2, 3, 5 or 8',
    'add.due.help': 'due date, YYYY-MM-DD',
    'add.repeat.help': 'recurrence: Nd, Nw, weekly:DAY or monthly:N',
    'add.tags.help': 'comma-separated tags',
    'add.parent.help': 'add under this task, in the same list: its [ID:]'
    ' value, or part of its title',
    # show
    'show.description': 'show one item: its fields and its subtasks',
    'show.help': 'for details use show --help',
    'show.selector.metavar': 'selector',
    'show.selector.help': "the task's [ID:] value, or part of its title",
    'show.format.help': 'output format: text for a terminal, json for agents',
    # update
    'update.description': 'change the fields or the title of one task',
    'update.help': 'for details use update --help',
    'update.selector.metavar': 'selector',
    'update.selector.help': "the task's [ID:] value, or part of its title",
    'update.priority.help': 'new priority multiplier, 0 and up',
    'update.due.help': 'new due date, YYYY-MM-DD',
    'update.tags.help': 'replacement comma-separated tags',
    'update.title.help': 'new title, without any [FIELD:] markup',
    # done
    'done.description': 'complete a task and log it to completed.md',
    'done.help': 'for details use done --help',
    'done.selector.metavar': 'selector',
    'done.selector.help': "the task's [ID:] value, or part of its title",
    # scratch
    'scratch.description': 'abandon a task: remove it and log it as SCRATCHED',
    'scratch.help': 'for details use scratch --help',
    'scratch.selector.metavar': 'selector',
    'scratch.selector.help': "the task's [ID:] value, or part of its title",
    # backfill
    'backfill.description': 'one-time migration: stamp [ADDED:today] on '
    'tasks that predate the field',
    'backfill.help': 'for details use backfill --help',
    # completed
    'completed.description': 'digest the completed log for one period',
    'completed.help': 'for details use completed --help',
    'completed.period.metavar': 'period',
    'completed.period.help': 'how far back to read: today, week or month;'
    ' default week',
    'completed.format.help': 'output format: text for a terminal, json for'
    ' agents',
}
