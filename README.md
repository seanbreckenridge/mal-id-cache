# mal-id-cache

This code doesn't run anymore, the anime and manga cache information is back filled from [Hiyori-API/checker_mal](https://github.com/Hiyori-API/checker_mal). I plan to keep this updated for the forseeable future, though [HiyoriDB](https://github.com/Hiyori-API/HiyoriDB) will eventually be a nicer and more complete replacement.

---

This is a cache of anime and manga ids on [MAL](https://myanimelist.net).

#### NOTE: Since April 2nd 2020, MAL updated how characters/persons on their site are laid out making the People/Characters much more difficult to check for updates. The `people.json` and `character.json` files will remain unchanged for the forseeable future, they are up to date as of March 31st, 2020.

If you want a (somewhat) random character or person, you can request a random anime/manga using the cache files here, then pick a random character/staff member from that entry.

[cache](./cache) includes anime, manga, person and character IDs.

The JSON files for anime/manga are structured like:

```
{
    "sfw": [
        1,
        5,
        ....

    ],
    "nsfw": [
        188,
        203,
        ...    
    ]
}
```

For person/character:

```
{
    "ids": [
        1,
        2,
        ...
    ]
}
```

### Raison d'être

The reason this exists is because there's currently no easy way to get a list of all the approved entries on MAL.

Whenever an entry requested to be added (by a user), it gets an ID and is listed "on the website" - unlisted; at this point no one can add it to their list.

If a moderator approves the entry, it keeps the same ID and becomes an entry that people can view publicly.

If its denied, the ID disappears and becomes a 404, leaving a 'gap' in the IDs for MAL. At the time of writing this, the most recently approved anime ID is 40134, but there are less than 17000 anime entries on MAL.

There have been a few cases where IDs are re-used for others, but that is not the common case.

This uses the [Just Added](https://myanimelist.net/anime.php?o=9&c%5B0%5D=a&c%5B1%5D=d&cv=2&w=1) page on MAL to find new entries, but all that page is is a search on the entire database reverse sorted by IDs. New entries may appear on the 2nd, 3rd, or even 20th page, if a moderator took a long time to get around to it.

The most obvious application for this cache is to use the cache to choose an entry at random.

This will be updated whenever a new entry is added.

You can either clone this repo to your system and set up a script that `git pull`s periodically, or download the raw json files directly from [`cache`](./cache) (though that means you have no way of knowing when the file is updated)

Check [the config file](./default_config.toml) for how often this checks different ranges of IDs.

### Installation

If you'd like to set up your own instance:

To create and maintain the cache, we have to use a local [Jikan](https://github.com/jikan-me/jikan) instance since the remote (api.jikan.moe) would cache requests for too long. See [here](https://github.com/jikan-me/jikan-rest) for how to set that up.

After Finishing Step 1 on that page (Installing Dependencies):

```
# Clone Repo
mkdir ~/.mal-id-cache
git clone https://github.com/seanbreckenridge/mal-id-cache ~/.mal-id-cache/repo
cd ~/.mal-id-cache/repo
# Install python dependencies (see below for alternatives)
pipenv install -r requirements.txt
pipenv shell
# Install mal_id_cache script
python3 setup.py install
# Clone jikan-rest (into this directory is fine, though you can have it somewhere else)
git clone https://github.com/jikan-me/jikan-rest
cp env.dist jikan-rest/.env  # Copy environment settings (for cache expiry config)
cd jikan-rest
composer install
php artisan key:generate  # Generate APP_KEY
cd ~/.mal-id-cache
mal_id_cache --init-dir  # Setup directory structure at ~/.mal-id-cache
```


How you install python requirements is up to you, you can import it into a [`pipenv`](https://realpython.com/pipenv-guide/) using the command above, create a virtualenv and install it there, or just install them directly into the global modules.

Start the jikan-rest server: `php -S localhost:8000 -t jikan-rest/public >> ~/.mal-id-cache/logs/jikan-requests.log 2>&1`

This stores 'state' files at `~/.mal-id-cache/state` which keep track of when each page range defined in the [config](./default_config.toml) were last run.

You can run `mal_id_cache` on its own, which checks the state once, or with the `--loop/--server` flags, to check periodically.

```
Usage: mal_id_cache [OPTIONS]

  Caches IDs for MyAnimeList

Options:
  --config-file PATH              Override the default .toml config file
  --dry-run / --no-dry-run        Don't affect local files or make requests,
                                  log actions instead
  --loop / --no-loop              Run the process till stopped, checking for
                                  new entries periodically
  --server / --no-server          --loop, and open a socket (default port:
                                  32287) to listen for requests from other
                                  processes
  --init-dir                      Make sure directories at ~/.mal-id-cache are
                                  setup properly and exit
  --initialize                    Initialize each cache -- deletes and re-
                                  requests everything.
  --force-state INTEGER           Update all 'last checked' times for the
                                  state files to 'n' seconds ago
  --delete                        Delete the cache and state files if they
                                  exist and exit
  --unapproved [table|json|count]
                                  Prints unapproved entries on MAL and exits.
                                  'json' saves a file to current directory.
                                  Assumes cache is built.
  --commit                        If the cache/*_cache.json files have
                                  changed, push them to the remote git
                                  repository
  --help                          Show this message and exit.
```

If you have this forked/are pushing to a git repo, that can be done like: `mal_id_cache --loop --commit` (which is what [`update_loop.sh`](./update_loop.sh) does).

#### Thanks

Thanks to [lynn root/mayhem mandril](https://github.com/econchick/mayhem), for some asyncio best practices.
