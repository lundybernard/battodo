import logging

logging_config = {
    'version': 1,
    # Loggers exist before this config is applied: every library
    # imported above the dictConfig call already made its own. Leave
    # them alone rather than silencing them.
    'disable_existing_loggers': False,
    'formatters': {
        'f': {'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'},
        'thread_formatter': {
            'format': (
                '%(asctime)s %(threadName)-12s %(levelname)-8s %(message)s'
            )
        },
    },
    'handlers': {
        'h': {'class': 'logging.StreamHandler', 'formatter': 'f'},
        'thread_handler': {
            'class': 'logging.StreamHandler',
            'formatter': 'thread_formatter',
        },
    },
    'loggers': {
        'root': {'handlers': ['h'], 'level': logging.DEBUG},
        'mod': {'handlers': ['h'], 'level': logging.DEBUG},
        'thread': {'handlers': ['thread_handler'], 'level': logging.DEBUG},
    },
}
