from random import random
from typing import Dict

from .logging import asynclogger

def load_dictionary(d: Dict):
    """
    Make sure the keys of a dictionary are integers
    """
    return {int(k): v for k, v in d.items()}


def dump_dictionary(d: Dict):
    """
    Make sure the keys of a dictionary are strings
    """
    return {str(k): v for k, v in d.items()}


def jitter(time: int) -> float:
    """
    Adds jitter (slightly randomizes) an integer
    """
    return time + (random() * (1 + time // 5))


async def backoff_handler(details):
    log_str = "Backing off {wait:0.1f} seconds afters {tries} tries with {args} {kwargs}".format(
        **details
    )
    await asynclogger.info(log_str)
