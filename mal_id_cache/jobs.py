from uuid import uuid4
from enum import IntEnum
from typing import Dict, Optional, Union

from .logging import asynclogger

class RequestType(IntEnum):
    NOT_SET = 0
    ANIME = 1
    MANGA = 2
    CHARACTER = 3
    PERSON = 4

    @staticmethod
    def describe(request_type: int) -> str:
        return REQUEST_DESCRIPTION_CONVERTER[request_type]

    @staticmethod
    def from_request_char(request_type: str) -> int:
        """
        Raises a KeyError if the request type string didn't exist

        :param request_type: a, m, p, or c, specifying type from local socket
        :return: Request type IntEnum
        """
        return {v[:1]: k for k, v in REQUEST_DESCRIPTION_CONVERTER.items()}[
            request_type
        ]


REQUEST_DESCRIPTION_CONVERTER: Dict[int, str] = {
    RequestType.ANIME: "anime",
    RequestType.MANGA: "manga",
    RequestType.PERSON: "character",
    RequestType.CHARACTER: "people",
}


class Job:
    """A request to check pages for a request type."""

    def __init__(
        self, request_type: Union[RequestType, int], pages: Optional[int] = -1
    ):
        self.uuid: str = uuid4().hex[:12]
        self.request_type = request_type
        if self.request_type in [RequestType.ANIME, RequestType.MANGA]:
            self.pages = pages
        elif self.request_type in [RequestType.CHARACTER, RequestType.PERSON]:
            self.pages = -1  # character and person requests can only accept all pages
        else:
            raise RuntimeError(f"Request Type '{request_type}' is not supported.")

    def __repr__(self):
        description = {-1: "all", -2: "unapproved"}.get(self.pages, self.pages)
        return "{}(uuid={}, request_type={}, pages={})".format(
            self.__class__.__name__,
            self.uuid,
            RequestType.describe(self.request_type),
            description,
        )

    __str__ = __repr__

    @classmethod
    def from_network_request_string(cls, request_str: str):
        """
        >>> "a51"
        (1, 51)
        >>> "c-1"
        (3, -1)
        """
        request_type_str, pages = request_str[:1], request_str[1:]
        return cls(RequestType.from_request_char(request_type_str), int(pages))


class UpdatableRange:
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
