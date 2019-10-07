#!/usr/bin/env python3

import sys
import json
import signal
import asyncio
import traceback
from contextlib import suppress
from typing import List, Dict, Optional, Any, Callable

import click
import aiohttp
import jikanpy
import toml
from git import Repo

from . import default_config_file, repo_dir, loop
from .scheduler import AbstractScheduler, JustAddedScheduler, AllPagesScheduler
from .cache import AbstractCache, JustAddedCache, AllPagesCache
from .logging import logger, asynclogger
from .jobs import RequestType, Job
from .utils import load_dictionary
from .unapproved import Unapproved

schedules: Dict[RequestType, Optional[AbstractScheduler]] = {
    RequestType.ANIME: None,
    RequestType.MANGA: None,
    RequestType.CHARACTER: None,
    RequestType.PERSON: None,
}

cachers: Dict[RequestType, Optional[AbstractCache]] = {
    RequestType.ANIME: None,
    RequestType.MANGA: None,
    RequestType.CHARACTER: None,
    RequestType.PERSON: None,
}

unapproved_instance: Optional[Unapproved] = None


# https://stackoverflow.com/a/43941592
class Global:
    """
    Global Configuration
    """

    _conf: Dict[str, Any] = {
        "jikan_url": "",
        "anime_ranges": {},
        "manga_ranges": {},
        "person_ranges": {},
        "character_ranges": {},
        "server_port": None,
        "loop_period": 300,  # default, overridden in load_defaults
    }

    @staticmethod
    def config(name):
        return Global._conf[name]

    @staticmethod
    def set(name, value):
        if name in Global._conf:
            Global._conf[name] = value
        else:
            raise NameError("Name not accepted in set() method")

    @staticmethod
    def load_defaults(file_location: str, dry_run: bool):
        with open(file_location) as f:
            default_conf = toml.load(f)
        Global.set("jikan_url", default_conf["jikan_url"])
        Global.set("server_port", int(default_conf["server_port"]))
        Global.set("loop_period", int(default_conf["loop_period"]))
        Global.set("anime_ranges", load_dictionary(default_conf["anime"]))
        Global.set("manga_ranges", load_dictionary(default_conf["manga"]))
        Global.set("character_ranges", load_dictionary(default_conf["character"]))
        Global.set("person_ranges", load_dictionary(default_conf["person"]))


def exception_handler(func: Callable, context: Dict) -> None:
    """

    :param func: A function that can be run in the try/except
    :param context: dict with context for the couroutine
    """
    msg = context.get("exception", context["message"])
    logger.exception(f"Exception Handler Caught exception: {msg}")
    logger.exception(context)
    asyncio.create_task(graceful_shutdown())  # cant await in non-async


# make sure to pass return_exceptions=True for asnycio.gather
async def handle_gather(results: List[Any]):
    """Handles an iterable of results from asnycio.gather"""
    for result in results:
        if isinstance(result, Exception):
            if isinstance(result, asyncio.CancelledError):
                await asynclogger.warning("Ignoring asyncio.CancelledError")
            else:
                await asynclogger.exception(
                    f"Gather Handler Caught exception: [{result.__class__.__name__}] {result}"
                )
                await asynclogger.exception(
                    "".join(traceback.format_tb(result.__traceback__))
                )


async def graceful_shutdown(shutdown_signal: Optional[signal.Signals] = None) -> None:
    global unapproved_instance
    if shutdown_signal is not None:
        await asynclogger.info(f"Received exit signal: {shutdown_signal.name}")
    await asynclogger.info("Shutting down...")
    # Close socket if it exists

    # cancel unapproved decay loop
    if unapproved_instance:
        unapproved_instance.decay_task.cancel()
        with suppress(asyncio.CancelledError):
            await unapproved_instance.decay_task  # wait for task to finish cancelling

    # Cancel remaining tasks
    pending_tasks = [
        t
        for t in asyncio.all_tasks(loop=loop)
        if t is not asyncio.current_task(loop=loop)
    ]
    if pending_tasks:
        await asynclogger.info(f"Cancelling {len(pending_tasks)} tasks")
        for t in pending_tasks:
            t.cancel()

    # https://stackoverflow.com/questions/52505794/python-asyncio-how-to-wait-for-a-cancelled-shielded-task
    # shield json dumps etc

    await handle_gather(
        await asyncio.gather(*pending_tasks, loop=loop, return_exceptions=True)
    )
    await asynclogger.info("Shutdown complete")
    # Stop Loop
    loop.stop()


@click.command(name="run", help="Caches IDs for MyAnimeList")
@click.option(
    "--config-file",
    multiple=False,
    required=False,
    default=default_config_file,
    type=click.Path(exists=True, readable=True),
    help="Override the default .toml config file",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    is_flag=True,
    required=False,
    help="Don't affect local files or make requests, log actions instead",
)
@click.option(
    "--loop/--no-loop",
    "do_loop",
    default=False,
    is_flag=True,
    required=False,
    help="Run the process till stopped, checking for new entries periodically",
)
@click.option(
    "--server/--no-server",
    default=False,
    is_flag=True,
    required=False,
    help="--loop, and open a socket (default port: 32287) to listen for requests from other processes",
)
@click.option(
    "--init-dir",
    default=False,
    is_flag=True,
    required=False,
    help="Make sure directories at ~/.mal-id-cache are setup properly and exit",
)
@click.option(
    "--initialize",
    default=False,
    is_flag=True,
    required=False,
    help="Initialize each cache -- deletes and re-requests everything.",
)
@click.option(
    "--force-state",
    "force_state",
    type=int,
    required=False,
    help="Update all 'last checked' times for the state files to 'n' seconds ago",
)
@click.option(
    "--delete",
    "delete",
    default=False,
    is_flag=True,
    required=False,
    help="Delete the cache and state files if they exist and exit",
)
@click.option(
    "--unapproved",
    "print_unapproved",
    type=click.Choice(["table", "json", "count"]),
    required=False,
    help="Prints unapproved entries on MAL and exits. 'json' saves a file to current directory. Assumes cache is built.",
)
@click.option(
    "--commit",
    "push_commit",
    default=False,
    is_flag=True,
    required=False,
    help="If the cache/*_cache.json files have changed, push them to the remote git repository"
)
def run_wrapper(
    config_file,
    dry_run,
    do_loop,
    server,
    init_dir,
    initialize,
    force_state,
    delete,
    print_unapproved,
    push_commit,
):
    """Main click command wrapper"""
    loop.run_until_complete(
        run(
            config_file,
            dry_run,
            do_loop,
            server,
            init_dir,
            initialize,
            force_state,
            delete,
            print_unapproved,
            push_commit,
        )
    )


async def run(
    config_file,
    dry_run,
    do_loop,
    server,
    init_dir,
    initialize,
    force_state,
    delete,
    print_unapproved,
    push_commit,
):
    """Check state and update cache, if needed"""
    global schedules, cachers, unapproved_instance

    if init_dir:
        await asynclogger.info("Directories have been initialized")
        # Directories are initialized in __init__.py, exit
        await graceful_shutdown()
        sys.exit(0)

    # Load configuration
    Global.load_defaults(config_file, dry_run)

    # Set Exception Handlers
    # SIGTERM finish any processes in queue (pkill pid, kill pid)
    # SIGKILL kill instantly (kill -9 pid)
    # SIGINT Ctrl C
    signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(
            s, lambda s=s: asyncio.create_task(graceful_shutdown(s))
        )
    loop.set_exception_handler(exception_handler)

    # Initialize Schedules
    schedules[RequestType.ANIME] = JustAddedScheduler(
        request_type=RequestType.ANIME,
        request_ranges=Global.config("anime_ranges"),
        dry_run=dry_run,
    )
    schedules[RequestType.MANGA] = JustAddedScheduler(
        request_type=RequestType.MANGA,
        request_ranges=Global.config("manga_ranges"),
        dry_run=dry_run,
    )
    schedules[RequestType.CHARACTER] = AllPagesScheduler(
        request_type=RequestType.CHARACTER,
        request_ranges=Global.config("character_ranges"),
        dry_run=dry_run,
    )
    schedules[RequestType.PERSON] = AllPagesScheduler(
        request_type=RequestType.PERSON,
        request_ranges=Global.config("person_ranges"),
        dry_run=dry_run,
    )

    # Initialize Cache/Request Sessions
    session = aiohttp.ClientSession()
    jikan_instance = jikanpy.AioJikan(
        selected_base=Global.config("jikan_url"), session=session
    )
    cachers[RequestType.ANIME] = JustAddedCache(
        scheduler=schedules[RequestType.ANIME], jikan=jikan_instance, dry_run=dry_run
    )
    cachers[RequestType.MANGA] = JustAddedCache(
        scheduler=schedules[RequestType.MANGA], jikan=jikan_instance, dry_run=dry_run
    )
    cachers[RequestType.PERSON] = AllPagesCache(
        scheduler=schedules[RequestType.PERSON], session=session, dry_run=dry_run
    )
    cachers[RequestType.CHARACTER] = AllPagesCache(
        scheduler=schedules[RequestType.CHARACTER], session=session, dry_run=dry_run
    )

    # initialize unapproved metadata singleton (don't run request unless needed)
    unapproved_instance = Unapproved(
        session=session,
        anime_cache=cachers[RequestType.ANIME],
        manga_cache=cachers[RequestType.MANGA],
        dry_run=dry_run,
    )

    # Set state to 'force_state' seconds in the past and exit if --force-state was passed
    if force_state is not None:
        for s in schedules.values():
            await asynclogger.info(f"Updating state for {s.__class__.__name__}")
            await s.force_update(rewind_n_seconds=force_state)
        await graceful_shutdown()
        sys.exit(0)

    # Initialize (Read JSON) Cache/Request objects
    for c in cachers.values():
        await c.read()

    # Re-initialize/Initialize the cache if --re-initialize or --initialize was passed
    if delete or initialize:
        # Delete state files
        for s in schedules.values():
            await s.delete()
        # Delete cache files
        for c in cachers.values():
            await c.delete()

    if delete:
        await graceful_shutdown()
        sys.exit(0)

    if initialize:
        for req_type in cachers:
            await cachers[req_type].process_job(Job(request_type=req_type, pages=-1), unapproved_instance)
        await graceful_shutdown()
        sys.exit(0)

    if print_unapproved is not None:
        anime = await unapproved_instance.anime()
        manga = await unapproved_instance.manga()
        if print_unapproved == "count":
            click.echo("Unapproved anime count: {}".format(len(anime)))
            click.echo("Unapproved manga count: {}".format(len(manga)))
        elif print_unapproved == "json":
            with open("unapproved_mal_ids.json", 'w') as u_json_fp:
                json.dump({"unapproved_anime": anime, "unapproved_manga": manga}, u_json_fp)
            click.echo("Wrote results to 'unapproved_mal_ids.json' in this directory.")
        else:
            click.echo("===== ANIME =====")
            click.echo(
                "\n".join(map(lambda i: f"https://myanimelist.net/anime/{i}", anime))
            )
            click.echo("===== MANGA =====")
            click.echo(
                "\n".join(map(lambda i: f"https://myanimelist.net/manga/{i}", manga))
            )
        loop.stop()
        sys.exit(0)

    # Start, taking passed flags into consideration
    if do_loop or server:
        wait_time = Global.config("loop_period")
        if server:
            await asynclogger.info(
                "Opening server on socket {}...".format(Global.conf("server_port"))
            )
        else:
            await asynclogger.info(
                "Starting loop, checking state every {} seconds...".format(wait_time)
            )
        while True:
            await once(push_commit)
            await asyncio.sleep(wait_time)
    else:
        await asynclogger.info("Checking if anything needs to be updated...")
        await once(push_commit)
        await graceful_shutdown()


async def once(push_commit: bool):
    """
    Runs and 'main loop' once
    Adds any tasks that should be run, waits for task completing

    push_commit: the --commit flag was passed when starting, push any changes to remote git
    """
    global schedules, cachers
    for schedule in schedules.values():
        job: Optional[Job] = await schedule.prepare_request()
        if job is not None:
            await cachers[job.request_type].process_job(job, unapproved_instance)
    if push_commit:
        await commit()


async def commit():
    global cachers
    repo = Repo(repo_dir)
    relative_cache_files = [f"cache/{c.scheduler.endpoint}_cache.json" for c in cachers.values()] # e.g. cache/anime_cache.json
    dirty_files = set(relative_cache_files).intersection([i.a_path for i in repo.index.diff(None)])
    if dirty_files:
        await asynclogger.debug("json files which have been modified: {}".format(dirty_files))
        for d_f in dirty_files:
            repo.git.add(d_f)
        repo.index.commit("cache updates")
        remote = repo.remote(name="origin")
        remote.push()  # !!!!! requires you to have a SSH key set up, else it will prompt for a password every time


if __name__ == "__main__":
    run_wrapper()
