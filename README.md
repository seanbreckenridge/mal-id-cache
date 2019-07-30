# mal-id-cache

[cache.json](./cache.json) is a cache of all current [MAL](https://myanimelist.net/) (MyAnimeList) anime ids.

The JSON file is structured like:

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

Since MAL's IDs are not contiguous, and the "Just Added" page doesn't necessarily list the most recently added - just the latest IDs, sometimes newly approved anime will appear a couple pages in. This makes it somewhat annoying to maintain a cache of MAL IDs.

The most obvious application for this cache is to use the cache to choose an entry at random.

This is not meant to be a cache of all the data on MAL, it only lists IDs and whether the entry is SFW/NSFW.

This will be updated whenever a new entry is added.

Since Github doesn't allow you to serve large files without an authenticated token, the easiest way to download this and keep it updated is to `git clone https://github.com/seanbreckenridge/mal-id-cache` and have a script that `git pull`s periodically.

##### Implementation Notes

This checks ranges of the Just Added page periodically, ordered by most recent ID

It checks the first 2 pages every ~30 minutes, the first 8 every 8 hours, the first 20 every 2 days and completely deletes and re-creates the cache every 15 days (incase entries are deleted or merged).

If it finds an entry on any page, it extends how far it searches by `(5 + (current_page / 5)`.

### Installation

If for some reason, you'd like to set up your own instance:

To setup the cache, we have to use a local [Jikan](https://github.com/jikan-me/jikan) instance since the remote one would cache requests for too long. See [here](https://github.com/jikan-me/jikan-rest) for how to set that up.

After Finishing Step 1 on that page:

```
git clone https://github.com/seanbreckenridge/mal-id-cache
cd mal-id-cache
pipenv install
git clone https://github.com/jikan-me/jikan-rest
cp env.dist jikan-rest/.env
cd jikan-rest
composer install
php artisan key:generate
```

Start the server: `php -S localhost:8000 -t jikan-rest/public >> logs/jikan-requests.log 2>&1`

`pipenv shell` to enter the virtualenv

Generate and keep the cache updated: `python3 generate.py run`

Theres also a wrapper script, [run](./run), which will restart `python3 generate.py run` incase of network failure

If you're trying to debug, you can modify how long the the jikan requests last in cache by modifying the `CACHE_EXPIRE` variables in [env.dist](./env.dist) (and jikan-rest/.env), or delete the cache for `jikan-rest` by doing:

`rm -rf jikan-rest/storage/framework/cache/*`


#### Manga Cache

I'm currently not maintaining a cache of manga id's, since there are a lot more and its a less common problem. However, if you want to generate a cache of manga id's, you can change [this line](https://github.com/seanbreckenridge/mal-id-cache/blob/409772c997103e53c98a612892297833377cb58d/generate.py#L97) to `manga` instead of `anime`, and change the name of the file [here](https://github.com/seanbreckenridge/mal-id-cache/blob/f6078957cae9452bebcf6f1163465562e1695429/generate.py#L21) to something like `manga_cache.json`.
