import sys

import os
import logging

from aiologger import Logger
from aiologger.formatters.base import Formatter
from aiologger.handlers.streams import AsyncStreamHandler
from aiologger.handlers.files import AsyncFileHandler

from . import loop, logs_dir

FMT_STR = "%(asctime)s %(levelno)s %(process)d %(message)s"

formatter = Formatter(fmt=FMT_STR)
asynclogger = Logger(loop=loop)

# non-async logger for non-async functions (e.g. exception handler)
logger = logging.getLogger("mal_id_cache")

if not asynclogger.handlers:

    # async setup
    # log to stdout
    asynclogger.add_handler(
        AsyncStreamHandler(
            stream=sys.stdout, formatter=formatter, level=logging.DEBUG, loop=loop
        )
    )

    fh = AsyncFileHandler(filename=os.path.join(logs_dir, "cache.log"), loop=loop)
    # despite AsyncFileHandler being a subclass, it doesn't accept the overridden kwargs
    fh.formatter = formatter
    fh.level = logging.DEBUG
    asynclogger.add_handler(fh)

    # sync setup
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(os.path.join(logs_dir, "cache.log"))
    # format
    formatter = logging.Formatter(FMT_STR)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # log to stderr
    logger.addHandler(logging.StreamHandler())
