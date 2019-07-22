#!/usr/bin/env bash

# kills the jikan instance if it exists
kill $(ps -e | grep jikan-rest/public | grep -v grep | cut -d" " -f 1)
