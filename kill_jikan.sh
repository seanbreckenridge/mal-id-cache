#!/usr/bin/env bash

kill $(ps -e | grep jikan-rest/public | grep -v grep | cut -d" " -f 1)
