# mal-id-cache

Anime and manga cache information is back filled from [Hiyori-API/checker_mal](https://github.com/Hiyori-API/checker_mal). I plan to keep this updated for the forseeable future, though [HiyoriDB](https://github.com/Hiyori-API/HiyoriDB) will eventually be a nicer and more complete replacement.

---

This is a cache of anime and manga ids on [MAL](https://myanimelist.net).

Since April 2nd 2020, MAL updated how characters/persons on their site are laid out making the People/Characters much more difficult to check for updates. The `people.json` and `character.json` files will remain unchanged for the forseeable future, they are up to date as of March 31st, 2020.

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
