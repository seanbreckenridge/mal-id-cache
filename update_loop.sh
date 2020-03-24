#!/usr/bin/env bash

# make sure we're in the current directory
CUR_DIR="$(dirname "${BASH_SOURCE[0]}")"
cd "$CUR_DIR"

exec pipenv run mal_id_cache --loop --commit

