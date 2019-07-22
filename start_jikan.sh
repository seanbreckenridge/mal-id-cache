#!/usr/bin/env bash

# if the jikan instance doesn't exist, start it

ps -ef | grep "jikan-rest/public" | grep -v "grep" && echo "jikan is already running!" || php -S localhost:8000 -t jikan-rest/public >> logs/jikan-requests.log 2>&1 &
