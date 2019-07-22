#!/usr/bin/env bash

ps -ef | grep -rin "jikan-rest/public" | grep -v "grep" || php -S localhost:8000 -t jikan-rest/public >> logs/jikan-requests.log 2>&1 &
