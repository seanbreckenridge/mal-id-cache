import os
import datetime
import json
import time
from typing import Dict, Optional
from abc import ABC, abstractmethod

import aiofiles

from . import state_dir
from .utils import load_dictionary, dump_dictionary
from .jobs import RequestType, Job, UpdatableRange
from .logging import asynclogger


class AbstractScheduler(ABC):
    """
    A class to keep track of when last page ranges of requests were requested.
    """

    def __init__(
        self,
        request_type: RequestType,
        request_ranges: Dict[int, int],
        dry_run: bool = False,
    ):
        """
        :param request_ranges: A dictionary that describes how often each range from 1-key should be requested
        Specifying -1 as the first param indicates all pages
        """

        self.request_type: RequestType = request_type
        self.ranges: Dict[int, int] = request_ranges
        self.state: Dict = {}
        self.dry_run = dry_run

    @property
    def endpoint(self):
        return RequestType.describe(self.request_type)

    @property
    def path(self):
        return os.path.join(state_dir, f"{self.endpoint}_state.json")

    async def read_state(self):
        """Reads from the JSON state, creates keys if needed"""

        contents: Dict = {}

        # read from state.json if it exists
        if os.path.exists(self.path):
            async with aiofiles.open(self.path, mode="r") as state_f:
                try:
                    contents_str = await state_f.read()
                    contents = load_dictionary(json.loads(contents_str))
                except json.decoder.JSONDecodeError:
                    contents = {}
                    await asynclogger.warning(f"Could not parse JSON from {self.path}")

        # uses pages passed in __init__ for ranges to check
        # using previous values if possible
        for pages, period in self.ranges.items():
            if pages not in contents:
                await asynclogger.debug(
                    "[{}] Setting previous run time for {} pages to epoch time".format(
                        RequestType.describe(self.request_type), pages
                    )
                )
                self.state[pages] = {
                    "every_x_seconds": int(period),
                    "prev": 0,  # unix epoch
                }
            else:
                self.state[pages] = {
                    "every_x_seconds": int(period),
                    "prev": contents[pages]["prev"],
                }

    async def dump_state(self):
        """Dumps the current state to state.json"""

        if self.dry_run:
            await asynclogger.info(
                f"[Dry Run] Dumping state to {self.path}: {self.state}"
            )
        else:
            json_dict = dump_dictionary(self.state)
            json_str = json.dumps(json_dict)
            async with aiofiles.open(self.path, mode="w") as state_f:
                await state_f.write(json_str)

    async def delete(self):
        """Deletes the state.json file"""
        if os.path.exists(self.path):
            if not self.dry_run:
                await asynclogger.info(f"Deleting {self.path}")
                os.remove(self.path)
            else:
                await asynclogger.info(f"[Dry Run] Deleting {self.path}")
        else:
            await asynclogger.info(f"{self.path} does not exist.")

    async def force_update(self, rewind_n_seconds):
        """
        Update the last updated time for page ranges in the state to now
        i.e. state would be same as right after we re-initialized all pages
        """
        await self.read_state()
        for pages, period in self.state.items():
            rewind_to = int(time.time()) - rewind_n_seconds
            await asynclogger.info(
                "Setting last checked time for {} pages for {} to {}".format(
                    pages,
                    self.__class__.__name__,
                    datetime.datetime.fromtimestamp(rewind_to),
                )
            )
            period["prev"] = rewind_to  # set all 'prev' times to now
        await self.dump_state()

    @abstractmethod
    async def prepare_request(self):
        raise NotImplementedError

    @abstractmethod
    async def finished_requesting(self) -> None:
        raise NotImplementedError


class JustAddedScheduler(AbstractScheduler):
    """
    Ranges of pages of just added entries are requested, since approvals can be on
    any page near the just added page, but not necessarily on the first
    """

    async def prepare_request(self) -> Optional[Job]:
        """
        :return: A Job for the current range that needs to be checked. None if no pages need to be checked.
        """
        max_pages = 0
        await self.read_state()
        for pages, metadata in self.state.items():
            if time.time() - metadata["prev"] > metadata["every_x_seconds"]:
                if pages < 0:  # sentinel values
                    max_pages = pages
                    break
                elif pages > max_pages:
                    max_pages = pages
        if max_pages == 0:
            return None
        else:
            return Job(self.request_type, max_pages)

    async def finished_requesting(self, r: UpdatableRange):  # type: ignore
        """Updates the State after requests are done"""
        for pages, metadata in self.state.items():
            if r.infinite:
                metadata["prev"] = int(time.time())
            elif (
                r.current_page >= pages != -1
            ):  # current_page tells us how many were requested
                metadata["prev"] = int(time.time())
        await self.dump_state()


class AllPagesScheduler(AbstractScheduler):
    """
    For endpoints which don't have a Just Added page, the 'letter' endpoints are used
    """

    async def prepare_request(self) -> Optional[Job]:
        """
        :return: A Job if all pages need to be checked, else None
        """
        job = None
        await self.read_state()
        if time.time() - self.state[-1]["prev"] > self.state[-1]["every_x_seconds"]:
            job = Job(self.request_type, -1)
        return job

    async def finished_requesting(self):
        self.state[-1]["prev"] = int(time.time())  # only one item exists in state obj
        await self.dump_state()
