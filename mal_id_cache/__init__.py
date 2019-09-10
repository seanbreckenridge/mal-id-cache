import os
import pathlib
import asyncio

# get event loop
loop = asyncio.get_event_loop()

# setup global path/objects and logging
home_dir = os.path.abspath(pathlib.Path().home())
root_dir = os.path.join(home_dir, ".mal-id-cache")
repo_dir = os.path.join(root_dir, "repo")
logs_dir = os.path.join(root_dir, "logs")
state_dir = os.path.join(root_dir, "state")
cache_dir = os.path.join(repo_dir, "cache")

for app_dir in [root_dir, logs_dir, cache_dir, state_dir]:
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)

default_config_file = os.path.join(repo_dir, "default_config.toml")
