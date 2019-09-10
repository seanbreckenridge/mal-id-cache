from random import random
from typing import Optional, Dict

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
    Applies jitter (slightly randomizes) a time given
    """
    return time + (random() * (1 + time // 5))


async def backoff_handler(details):
    log_str = "Backing off {wait:0.1f} seconds afters {tries} tries with {args} {kwargs}".format(
        **details
    )
    await asynclogger.info(log_str)


class UpdateableRange:
    def __init__(self, check_till: int, extend_by: int = 8):
        """
        A generator that can be updated while iterating; returns integers that correspond
        to pages to check till we don't find a page in either:
            self.check_till
            or self.check_till + last_page_an_entry_was_found_on + extend_by

        check_till == -1 signifies an infinite range
        In that case, code that is requesting pages sequentially
        should 'break' when there are no more entries

        check_till == -2 signifies a toggleable infinite range.
        This is to keep checking pages till we reach the page that corresponds to
        the oldest unapproved entry. In that case, the range should keep returning
        entries until its told to stop (toggle_off())

        :param check_till: The amount of pages this range should return
        :param extend_by: The amount this range should extend by if we find a new entry
        """

        self.current_page: int = 0  # increments before returning first item
        self.check_till: int = check_till
        self.extend_by: int = extend_by
        self.infinite = False
        self.is_toggleable = False
        self._is_toggled = True  # return pages till this is False

        if check_till == -1:
            self.infinite = True
        if check_till == -2:
            self.is_toggleable = True

    async def found_entry_on_page(self, n: int) -> None:
        """
        Updates the range when an entry is found on a page.

        :param n: The page a new entry was found on
        :return: None
        """
        if not self.infinite:
            # Toggleable entries already have a built cache, they should be
            # checking for approved entries and logging them
            extend_till = n + self.extend_by
            if extend_till > self.check_till:
                await asynclogger.info(
                    f"Extending search from {self.check_till} till {extend_till}"
                )
                self.check_till = extend_till

    def toggle_off(self):
        self._is_toggled = False

    def __iter__(self):
        return self

    def __next__(self) -> int:
        if (
            self.infinite
            or (self.is_toggleable and self._is_toggled)
            or self.current_page < self.check_till

        ):
            self.current_page += 1
            return self.current_page
        else:
            raise StopIteration
