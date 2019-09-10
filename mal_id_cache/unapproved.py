
from typing import List, Optional, Set
import asyncio

import aiohttp
import backoff
import bs4

from . import loop
from .cache import JustAddedCache
from .logging import asynclogger

class Unapproved:
    """
    Class to parse the unapproved entry page
    """

    WAIT_TIME = 20
    ERR_WAIT_TIME = 120
    RELATION_ID_PAGE = "https://myanimelist.net/info.php?search=%25%25%25&go=relationids&divname=relationGen1"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:68.0) Gecko/20100101 Firefox/68.0"
    CSS_TABLE_SELECTOR = "div.normal_header + table"

    def __init__(self, session: aiohttp.ClientSession, anime_cache: JustAddedCache, manga_cache: JustAddedCache, dry_run: bool = False):
        self.session: aiohttp.ClientSession = session
        self.dry_run = dry_run
        self.anime_cache = anime_cache
        self.manga_cache = manga_cache
        self._html_response = None
        self._html_text = None
        self._anime: Optional[List[int]] = None
        self._manga: Optional[List[int]] = None

    @property
    def is_parsed(self):
        return self._anime is not None and self._manga is not None

    @backoff.on_exception(backoff.constant, aiohttp.ClientResponseError, interval=ERR_WAIT_TIME, max_tries=10, jitter=None)
    async def _request(self):
        if self.dry_run:
            await asynclogger("[Dry Run] Requesting {}".format(self.RELATION_ID_PAGE))
        else:
            self._html_response = await self.session.get(self.RELATION_ID_PAGE, headers={"User-Agent": self.USER_AGENT})
            self._html_response.raise_for_status()
            await asyncio.sleep(self.WAIT_TIME)
            self._html_text = await self._html_response.text()

    async def _parse(self):
        if self._html_response is None:
            await self._request()
        if not self.is_parsed:
            await loop.run_in_executor(None, self.parse_page)

    def parse_page(self):
        soup = bs4.BeautifulSoup(self._html_text, 'html.parser')
        tables = soup.select(self.CSS_TABLE_SELECTOR)
        if len(tables) != 2:
            raise RuntimeError("Could not find anime and manga tables on {}".format(self.RELATION_ID_PAGE))
        anime_anchors = tables[0].find_all('a')
        manga_anchors = tables[1].find_all('a')
        self._anime = list(map(lambda a: int(a.text), anime_anchors))
        self._manga = list(map(lambda a: int(a.text), manga_anchors))

    async def anime(self) -> List[int]:
        if not self.is_parsed:
            await self._parse()
        approved_entries: Set = self.anime_cache.cache["sfw"] | self.anime_cache.cache["nsfw"]
        return sorted(set(self._anime) - approved_entries)

    async def manga(self) -> List[int]:
        if not self.is_parsed:
            await self._parse()
        approved_entries: Set = self.manga_cache.cache["sfw"] | self.manga_cache.cache["nsfw"]
        return sorted(set(self._manga) - approved_entries)
