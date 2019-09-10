from uuid import uuid4
from enum import IntEnum
from typing import Dict, Optional, Union


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
        self.uuid = uuid4().hex[:12]
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
