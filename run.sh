#!/bin/sh
cd "$(dirname "$0")"
exec python3 server.py >> data/server.log 2>&1
