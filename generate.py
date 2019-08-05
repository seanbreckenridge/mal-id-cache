#!/usr/bin/env python3

import os
import time
import random
import json
import logging

import backoff
import click
import pickledb
import jikanpy
from git import Repo

# setup global path/objects and logging

root_dir = os.path.abspath(os.path.dirname(__file__))
logs_dir = os.path.join(root_dir, 'logs')
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)
db_file = os.path.join(root_dir, 'cache.json')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(os.path.join(logs_dir, "cache.log"))
# format
formatter = logging.Formatter(
    "%(asctime)s %(levelno)s %(process)d %(message)s")
fh.setFormatter(formatter)
# log to stderr
logger.addHandler(logging.StreamHandler())
# and to the log file
logger.addHandler(fh)
j = jikanpy.Jikan("http://localhost:8000/v3/")


class IndentedPickleDB(pickledb.PickleDB):

    # Make sure lines are indented so that git diff's are small
    def dump(self):
        with open(self.loco, 'wt') as loco_f:
            loco_f.write(json.dumps(self.db, indent=4))
        return True

    # sort the list
    def lsort(self, name):
        self.db[name].sort()
        self.dump()


db = IndentedPickleDB(location=db_file, auto_dump=False, sig=True)


class req_range:
    """Since we extend whenever we find an entry, these aren't incredibly important
    Most entries are added in the 0-4 page range, and theres a huge addition of entries
    the page_range extensions will catch anything past ~20/30
    """
    class two:
        val = 2
        time = 60 * 30  # 30 minutes

    class eight:
        val = 8
        time = 60 * 60 * 8  # 8 hours
        last = 0

    class twenty:
        val = 20
        time = 60 * 60 * 24 * 2  # 2 days
        last = 0

    class all:
        val = "all"
        time = 60 * 60 * 24 * 15  # 15 days
        last = 0


def _hdlr(details):
    logger.debug("Backing off {wait:0.1f} seconds afters {tries} tries with {args} {kwargs}".format(**details))


@backoff.on_exception(
    backoff.expo,  # exponential backoff
    (jikanpy.exceptions.JikanException,
     jikanpy.exceptions.APIException),
    max_tries=15,
    on_backoff=lambda details: _hdlr(details))
def get_search_page(p, nsfw):
    resp = j.search(
        'anime',
        '',  # query string
        page=p,
        parameters={
            'genre': 12,
            'genre_exclude': 1 if nsfw else 0,
            'order_by': 'id',
            'sort': 'desc'})
    return resp


@click.group()
def cli():
    pass


def update_req_range(found_new_entries: bool,
                     current_page: int, page_range: int, *, is_nsfw: bool):
    """Helper for updating the page range. If page range is higher, increases the amount we extend by"""
    if found_new_entries:
        extend_by = 3 + int(current_page / 5)
        page_range_before_extend = page_range
        if current_page + extend_by > page_range:
            page_range = current_page + extend_by
        if page_range != page_range_before_extend:
            logger.debug(
                "[{}]Extending search from {} to {}".format(
                    "NSFW" if is_nsfw else "SFW",
                    page_range_before_extend,
                    page_range))
    return page_range


def add_from_page(type, page):
    """If any new entries exist, adds them from the 'page' for the 'type' ('sfw'/'nsfw')
    for that page.

    returns the number of results on the page (typically 50), and if we found new entries
    """
    found_new_entries = False
    prev_cache = db.lgetall(type)
    results = []
    try:
        results = get_search_page(
            page, nsfw=True if type == 'nsfw' else False)['results']
    except Exception as e:
        logger.error(str(e), exc_info=True)
        raise e
    for r in results:
        if r["mal_id"] not in prev_cache:
            found_new_entries = True
            logger.info(
                f"Found new entry (id:{r['mal_id']}, {r['title']}) on page {page}")
            db.ladd(type, r['mal_id'])
    db.dump()
    return len(results), found_new_entries


@cli.command(
    name="run", help="Periodically check if new entries exist. Runs until stopped")
def loop():

    for type in ['sfw', 'nsfw']:
        if db.get(type) is False:
            db.lcreate(type)

    while True:
        # Initialize 'state' values to 0, (i.e. its Jan 1. 1970, so if needed,
        # req_range 2/8/20 are checked
        req_range.eight.last = req_range.twenty.last = req_range.all.last = 0

        # assume we're checking 2 pages
        req_type = req_range.two
        page_range = req_type.val

        logger.debug("[loop] Checking state")
        # read times from 'state' file
        if os.path.exists("state"):
            with open("state", "r") as last_scraped:
                req_range.eight.last, req_range.twenty.last, req_range.all.last = list(
                    map(int, last_scraped.read().strip().splitlines()))

        # check if we should be checking more than 2 pages
        for rt in [req_range.eight, req_range.twenty, req_range.all]:
            if int(time.time() - rt.last) > rt.time:
                req_type = rt
                page_range = rt.val

        logger.debug("[loop] checking {} pages".format(page_range))

        # delete cache if we're checking for deleted/merged entries
        if req_type == req_range.all:
            db.db['sfw'] = []
            db.db['nsfw'] = []
            db.dump()
            req_type = req_range.twenty

        # Check NSFW
        current_page = 1
        result_count = 1
        # while we're under our page range and we havent checked every page
        # check 1/2 of normal page range since NSFW entries are less common
        page_range = req_type.val / 2
        while current_page <= page_range and result_count > 0:

            logger.debug(f"[loop][NSFW] checking page {current_page}")
            result_count, found_new_entries = add_from_page(
                'nsfw', current_page)
            page_range = update_req_range(
                found_new_entries, current_page, page_range, is_nsfw=True)
            current_page += 1

        # Check SFW
        current_page = 1
        result_count = 1
        page_range = req_type.val
        # while we're under our page range and we havent checked every page
        while current_page <= page_range and result_count > 0:
            logger.debug(f"[loop][SFW] checking page {current_page}")
            result_count, found_new_entries = add_from_page(
                'sfw', current_page)
            page_range = update_req_range(
                found_new_entries, current_page, page_range, is_nsfw=False)
            current_page += 1

        # will only write req_range for sfw
        last_scraped = [
            req_range.eight.last,
            req_range.twenty.last,
            req_range.all.last]

        # at the time of writing this, there are 293 SFW pages
        # its incredibly unlikely any approved entries will apear after page 250
        # so its fine to use it as a magic number
        # if we've checked all entries
        if current_page > 250:
            last_scraped[2] = int(time.time())
        # if we extended past the thresholds because we found new entries
        # we dont have to check for larger ranges when we typically would
        if page_range >= req_range.twenty.val:
            last_scraped[1] = int(time.time())
        if page_range >= req_range.eight.val:
            last_scraped[0] = int(time.time())

        with open('state', 'w') as state_f:
            state_f.write("\n".join(map(str, last_scraped)))

        # sort id lists
        db.lsort('sfw')
        db.lsort('nsfw')

        commit()

        sleep_for = int(60 * random.uniform(27, 35))
        logger.debug("Sleeping for {}m{}s".format(*divmod(sleep_for, 60)))
        time.sleep(sleep_for)  # sleep for around 30 minutes


def commit():
    repo = Repo(root_dir)
    if 'cache.json' in [i.a_path for i in repo.index.diff(None)]:
        logger.debug(
            "[git] cache.json has been changed, commiting files and pushing")
        repo.git.add('cache.json')
        repo.index.commit("cache.json update")
        origin = repo.remote(name='origin')
        origin.push()
    else:
        logger.debug("[git] cache.json is unchanged")


if __name__ == "__main__":
    cli()
