import os
import re
import json
import math
import string
import random
import asyncio
from urllib.parse import urlencode
from typing import Optional, Dict, List, Set
from abc import ABC, abstractmethod

import backoff
import aiohttp
import aiofiles
import jikanpy
import bs4

from . import cache_dir, loop
from .utils import jitter, backoff_handler
from .scheduler import AllPagesScheduler, JustAddedScheduler
from .logging import logger, asynclogger
from .jobs import Job, UpdatableRange


# Lock to make sure that only one Job is being processed at a time
# Could alternatively modify the TCPSession passed to aiohttp.ClientSession
# to limit the simultaneous connections, but since both requests
# (to localhost:jikan_port and MyAnimeList) are being rate limited
# by the same remote endpoint, this makes more sense.
requesting = asyncio.Lock()


class AbstractCache(ABC):
    """
    A class which interacts with the underlying JSON files for each cache
    """

    REQUEST_SLEEP_TIME = 4

    def __init__(self, dry_run: bool = False):
        """
        :param dry_run: do a dry run - don't make any requests or dump files, just print what would happen
        """

        self.cache: Dict[str, Set] = {}
        self.dry_run: Optional[bool] = dry_run
        self.scheduler = None

    async def dump(self) -> None:
        """
        Dump the current cache to the cache JSON file
        """
        if self.dry_run:
            await asynclogger.info(f"[Dry Run] Dumping cache to {self.path}")
        else:
            # convert sets to lists
            converted_cache = {k: sorted(self.cache[k]) for k in self.cache}
            async with aiofiles.open(self.path, mode="w") as f:
                json_str = json.dumps(converted_cache, indent=4)
                await f.write(json_str)

    async def read(self) -> None:
        """
        Read from the cache JSON file, if it exists
        Else, create a new dictionary that represents the cache
        """
        try:
            async with aiofiles.open(self.path, mode="r") as f:
                cache_str = await f.read()
                self.cache = json.loads(cache_str)
                self.cache = {
                    k: set(self.cache[k]) for k in self.cache
                }  # convert to sets for faster lookup
        except (FileNotFoundError, json.JSONDecodeError) as error_reading_cache:
            await asynclogger.warning(str(error_reading_cache))
            await asynclogger.info("Setting cache to default, empty cache")
            self._set_default_cache()

    async def delete(self):
        """Deletes the cache.json file"""
        if os.path.exists(self.path):
            if not self.dry_run:
                await asynclogger.info(f"Deleting {self.path}")
                os.remove(self.path)
            else:
                await asynclogger.info(f"[Dry Run] Deleting {self.path}")
        else:
            await asynclogger.info(f"{self.path} does not exist.")

    @property
    def path(self) -> str:
        return os.path.join(cache_dir, f"{self.scheduler.endpoint}_cache.json")

    @abstractmethod
    def _set_default_cache(self) -> None:
        """
        Sets the default cache fot this request type
        """
        raise NotImplementedError

    @abstractmethod
    def __contains__(self, item) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def request_page(self):
        """
        Does an request (API/parses) to get the information for a page
        """
        raise NotImplementedError

    @abstractmethod
    def add(self, item: int) -> bool:
        """
        Adds an id to the cache
        :param item: The id to be added to cache
        :return:
        """
        raise NotImplementedError

    @abstractmethod
    async def process_job(self, job: Job) -> None:
        """
        Processes, requests and saves items into cache
        """
        raise NotImplementedError


class JustAddedCache(AbstractCache):
    """
    Interface to request and add IDs to a 'JustAdded' (e.g. anime, manga) cache
    """

    def __init__(
        self,
        scheduler: JustAddedScheduler,
        jikan: jikanpy.AioJikan,
        dry_run: bool = False,
    ):

        super().__init__(dry_run=dry_run)
        self.jikan_instance: jikanpy.AioJikan = jikan
        self.scheduler: JustAddedScheduler = scheduler

    def __contains__(self, item: int) -> bool:
        return item in self.cache["sfw"] or item in self.cache["nsfw"]

    def _set_default_cache(self) -> None:
        self.cache = {"sfw": set(), "nsfw": set()}

    async def request_page(
        self, page: int, job: Job, nsfw: bool = False
    ) -> List[int]:  # type: ignore
        """
        Requests a page using the local Jikan-REST instance

        :param page: The page to request, starting from 1
        :param job: propagated Job object, to make logs easier to track
        :param nsfw: whether this should filter out nsfw IDs or include them
        :return: the IDs from the response dictionary from jikan
        """
        response = await self._request(page, job, nsfw)
        await asyncio.sleep(jitter(self.REQUEST_SLEEP_TIME))
        return list(map(lambda r: r["mal_id"], response["results"]))

    @backoff.on_exception(
        backoff.fibo,
        jikanpy.APIException,
        max_tries=10,
        on_backoff=lambda details: backoff_handler(
            details
        ),  # backoff checks whether or not this is async/await
    )
    async def _request(self, page, job, nsfw):
        """
        Handles backing off on 'APIError's (429 Errors)
        """
        await asynclogger.debug(
            "[{}][{}][Page {}]".format("NSFW" if nsfw else "SFW", job.uuid, page)
        )
        return await self.jikan_instance.search(
            search_type=self.scheduler.endpoint,
            query="",  # query string
            page=page,
            parameters={
                "genre": 12,
                "genre_exclude": int(nsfw),
                "order_by": "id",
                "sort": "desc",
            },
        )

    def add(self, item: int, nsfw: bool) -> bool:  # type: ignore
        """
        Adds an ID to the cache

        :param item: The ID to be saved to cache
        :param nsfw: Specifies which cache to add this to.
        :return: False if the ID was already in cache, True if this was a new entry
        """
        if item in self:
            return False
        self.cache["nsfw" if nsfw else "sfw"].add(int(item))
        return True

    async def process_job(self, job: Job):
        """
        Check a number of search pages SFW specified by Job, and 1/3rd those pages for NSFW
        Save to cache json files

        :param job: A Job that specifies the SFW search range
        """

        # set default for dry-run
        updatable: UpdatableRange = UpdatableRange(job.pages)
        # These should be done in order, since we're rate limited by MAL anyways
        async with requesting:  # make sure/wait till no other jobs are requesting from MAL currently
            await asynclogger.info(f"Processing {job}")
            if self.dry_run:
                await asynclogger.debug(f"[Dry Run][{job}]")
            else:
                nsfw_pages = sfw_pages = job.pages
                # Ratio of SFW:NSFW is far more than 3:1, don't have to request the same amount of pages for both.
                if job.pages > 0:
                    nsfw_pages = math.ceil(nsfw_pages / 3)
                await self._process_job_type(
                    initial_pages=nsfw_pages, job=job, nsfw=True
                )
                updatable = await self._process_job_type(
                    initial_pages=sfw_pages, job=job, nsfw=False
                )
        # Save to cache
        await asynclogger.info(f"{job}: writing to cache")
        await self.dump()
        await self.scheduler.finished_requesting(updatable)

    async def _process_job_type(
        self, initial_pages: int, job: Job, nsfw: bool = False
    ) -> UpdatableRange:
        """
        Does API requests and extends range if it finds new entries

        :param initial_pages: Pages to search, specified by Job
        :param job: Metadata for the Task
        :param nsfw: Whether this should search nsfw pages or not
        """
        updatable = UpdatableRange(check_till=initial_pages)
        for page in updatable:
            ids = await self.request_page(page, nsfw=nsfw, job=job)
            if not ids:  # for infinite/toggleable searches, stop when there are no more entries
                return updatable
            for item in ids:
                if self.add(item=item, nsfw=nsfw):
                    await updatable.found_entry_on_page(page)
                    if not updatable.infinite:
                        await asynclogger.debug(
                            f"Found new entry ({item}) on page {page}"
                        )
        return updatable


class AllPagesCache(AbstractCache):
    """
    Interface to request and add IDs to a 'AllPages' (e.g. person, character) cache using letter endpoints
    """

    REQUEST_SLEEP_TIME = 10
    LINK_CSS_SELECTOR = "#content > table tr > td > a"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:68.0) Gecko/20100101 Firefox/68.0"
    LETTER_ENDPOINTS = "." + string.ascii_lowercase

    def __init__(
        self,
        scheduler: AllPagesScheduler,
        session: aiohttp.ClientSession,
        dry_run: bool = False,
    ):

        super().__init__(dry_run=dry_run)
        self.session: aiohttp.ClientSession = session
        self.scheduler: AllPagesScheduler = scheduler
        self.base_url: str = f"https://myanimelist.net/{self.scheduler.endpoint}.php"

    def __contains__(self, item: int):
        return int in self.cache["ids"]

    def _set_default_cache(self) -> None:
        self.cache = {"ids": set()}

    def add(self, item: int) -> bool:
        """
        Adds an ID to the cache

        :param item: The ID to be saved to cache
        :return: False if the ID was already in cache, True if this was a new entry
        """
        if item in self:
            return False
        self.cache["ids"].add(int(item))
        return True

    async def process_job(self, job: Job) -> None:
        """
        Request all pages for the request type.
        Save to cache json files
        """

        async with requesting:
            await asynclogger.info(f"Processing {job}")
            if self.dry_run:
                await asynclogger.debug(f"[Dry Run][{job.uuid}] Requesting all pages")
            else:
                choices = self.LETTER_ENDPOINTS
                for letter in random.sample(choices, len(choices)):
                    ids = await self.request_page(letter=letter, job=job)
                    for item in ids:
                        self.add(item=item)
        # Save to cache
        await asynclogger.info(f"{job.uuid}: writing to cache")
        await self.dump()
        await self.scheduler.finished_requesting()

    async def request_page(self, letter: str, job: Job) -> List[int]:  # type: ignore
        """
        Request and Parse a letter endpoint page from MAL

        Allowed letter values: jikanpy.parameters.SEARCH_PARAMS["letter"]

        :param letter: The letter endpoint to parse from MAL
        :param job: Metadata for this Task
        :return: A list of MAL IDs on that page
        """
        if letter not in jikanpy.parameters.SEARCH_PARAMS["letter"]:
            jikanpy.ClientException(f"Invalid letter passed: {letter}")
        return await self._parse(await self._request(letter=letter, job=job))

    @backoff.on_exception(
        backoff.fibo,
        aiohttp.ClientResponseError,
        max_tries=10,
        on_backoff=lambda details: backoff_handler(details),
    )
    async def _request(self, letter: str, job) -> Optional[aiohttp.ClientResponse]:
        """
        Handles requesting/backing off on aiohttp.ClientSession.get calls
        Makes sure that the response code is valid before returning

        :return: The corresponding response object
        """
        url: str = self.base_url + "?{}".format(urlencode({"letter": letter}))
        await asynclogger.debug(f"[{job.uuid}][Letter {letter}]")
        resp: aiohttp.ClientResponse = await self.session.get(
            url, headers={"User-Agent": self.USER_AGENT}
        )
        if resp.status > 400:
            await asynclogger.debug("Status: {} for URL: {}".format(resp.status, url))
        await asyncio.sleep(jitter(self.REQUEST_SLEEP_TIME))
        if resp.status == 404 and letter == ".":
            await asynclogger.debug("Ignoring 404 for . (punctuation) endpoint")
            return None
        else:
            resp.raise_for_status()  # Raise an aiohttp.ClientResponseError if the response status is 400 or higher.
        return resp

    async def _parse(self, response: Optional[aiohttp.ClientResponse]) -> List[int]:
        """
        Parses the HTML from the MyAnimeList table

        :param response: The aiohttp.ClientResponse object
        :return: A list of MAL integers for this page
        """
        if response is None:
            return []
        response_text: str = await response.text()
        return await loop.run_in_executor(None, self.bs4_parse, response_text)

    def bs4_parse(self, response_text: str) -> List[int]:
        """
        Synchronous function that parses IDs from a letter endpoint request
        :param response_text: corresponding response text from the request
        :return: The list of MAL integers for the request
        """
        # parse DOM
        soup = bs4.BeautifulSoup(response_text, "html.parser")
        # extract a elements
        anchor_els = soup.select(self.LINK_CSS_SELECTOR)
        # extract links
        links = []
        for a in anchor_els:
            try:
                links.append(a["href"])
            except KeyError:
                logger.warning("Could not extract href from {}".format(str(a)))
        # get IDs from links
        ids = []
        regex = f"{self.scheduler.endpoint}/(\d+)"
        for link in links:
            match = re.search(regex, link)
            if match is None:
                logger.warning(f"Couldn't find an ID in {link}")
            else:
                try:
                    ids.append(int(match.group(1)))
                except ValueError:
                    logger.warning(f"Could not convert to int from {match.group(1)}")
        return ids
